"""Narrow, shell-free Codex CLI adapter for the opt-in live technical gate."""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .validation.hashing import canonical_json_bytes, record_digest, sha256_digest
from .validation.models import (
    CodexCLIConfig,
    CodexCLIResult,
    ModelDriftLimitation,
    ModelIdentity,
)

ProcessRunner = Callable[..., subprocess.CompletedProcess[str]]

ALLOWED_ENVIRONMENT_KEYS = {
    "CODEX_API_KEY",
    "CODEX_HOME",
    "HOME",
    "HTTPS_PROXY",
    "HTTP_PROXY",
    "LANG",
    "LC_ALL",
    "LOGNAME",
    "NO_PROXY",
    "OPENAI_API_KEY",
    "PATH",
    "SHELL",
    "SSL_CERT_FILE",
    "TMPDIR",
    "USER",
}
SECRET_ENVIRONMENT_KEYS = {"CODEX_API_KEY", "OPENAI_API_KEY"}
# The App's dedicated Codex HOME (MC-21); when set it replaces HOME and CODEX_HOME.
CODEX_HOME_ENVIRONMENT = "TOMORROWSTAR_CODEX_HOME"
# Context a user's own Codex home would add to every call (instructions, configuration with
# MCP servers or developer instructions, hooks, prompts, skills, memories, rules). Codex itself
# installs only its bundled system skills (skills/.system) into a fresh home. Sign-in
# (auth.json) is stored here, so the user signs in once inside this home.
_USER_CONTEXT = (
    "AGENTS.md",
    "AGENTS.override.md",
    "config.toml",
    "hooks.json",
    "prompts",
    "skills",
    "memories",
    "rules",
    ".agents",
)


class CodexCLIError(RuntimeError):
    """Raised when the CLI boundary cannot produce a valid technical-gate result."""

    def __init__(self, message: str, *, raw_stdout_jsonl: str = "", redacted_stderr: str = ""):
        super().__init__(message)
        self.raw_stdout_jsonl = raw_stdout_jsonl
        self.redacted_stderr = redacted_stderr


def validate_codex_executable(value: str | Path) -> str:
    try:
        path = Path(value).expanduser()
        if not path.is_absolute() or not path.is_file() or not os.access(path, os.X_OK):
            raise CodexCLIError("configured Codex CLI executable is unavailable")
        return str(path.resolve())
    except (OSError, RuntimeError) as error:
        raise CodexCLIError("configured Codex CLI executable is unavailable") from error


def validate_codex_home(value: str | Path) -> str:
    """Return a dedicated Codex HOME that cannot add the user's own context (entry names only)."""
    try:
        home = Path(value)
        user = Path.home().resolve()
        if not home.is_absolute() or home.is_symlink() or not home.is_dir():
            raise CodexCLIError("dedicated Codex home is unavailable")
        if home.resolve() == user:
            raise CodexCLIError("dedicated Codex home is unavailable")
        if (home / ".codex").is_symlink():
            raise CodexCLIError("dedicated Codex home contains personal context")
        for folder in (home, home / ".codex"):
            for name in _USER_CONTEXT:
                entry = folder / name
                if name == "skills" and entry.is_dir() and not entry.is_symlink():
                    children = list(entry.iterdir())
                    if any(c.name != ".system" or c.is_symlink() for c in children):
                        raise CodexCLIError("dedicated Codex home contains personal context")
                elif entry.exists() or entry.is_symlink():
                    raise CodexCLIError("dedicated Codex home contains personal context")
        return str(home.resolve())
    except OSError as error:
        raise CodexCLIError("dedicated Codex home is unavailable") from error


def _resolved_workspace_path(path: Path, *, label: str) -> Path:
    if path.is_symlink():
        raise CodexCLIError(f"{label} cannot be a symlink")
    try:
        return path.resolve(strict=True)
    except OSError as exc:
        raise CodexCLIError(f"{label} does not exist") from exc


def _validate_paths(config: CodexCLIConfig) -> tuple[Path, Path, bytes]:
    workspace = _resolved_workspace_path(config.workspace, label="workspace")
    if not workspace.is_dir():
        raise CodexCLIError("workspace must be a directory")
    output_schema = _resolved_workspace_path(config.output_schema, label="output schema")
    if not output_schema.is_file() or not output_schema.is_relative_to(workspace):
        raise CodexCLIError("output schema must be a regular file inside workspace")
    try:
        schema_bytes = output_schema.read_bytes()
        schema = json.loads(schema_bytes.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CodexCLIError("output schema must contain valid JSON") from exc
    if not isinstance(schema, dict):
        raise CodexCLIError("output schema must be a JSON object")
    return workspace, output_schema, schema_bytes


def build_codex_exec_argv(
    config: CodexCLIConfig, prompt: str, *, allow_non_repository: bool = False
) -> list[str]:
    """Build the fixed read-only argument vector with no shell interpretation."""
    workspace, output_schema, _ = _validate_paths(config)
    if not prompt.strip():
        raise CodexCLIError("prompt cannot be blank")
    model = config.immutable_snapshot or config.requested_model
    return [
        config.executable,
        "exec",
        # No user configuration, rules, hooks, plugins or account apps, and no memories that
        # would carry one application's context into later calls.
        "--ignore-user-config",
        "--ignore-rules",
        *(argument for feature in _EXEC_DISABLED for argument in ("--disable", feature)),
        "--model",
        model,
        "--config",
        'model_reasoning_effort="medium"',
        "--json",
        "--output-schema",
        str(output_schema),
        "--cd",
        str(workspace),
        "--sandbox",
        "read-only",
        *(["--skip-git-repo-check"] if allow_non_repository else []),
        prompt,
    ]


_EXEC_DISABLED = ("memories", "apps", "plugins", "hooks")


def _allowlisted_environment(source: Mapping[str, str]) -> dict[str, str]:
    environment = {key: source[key] for key in ALLOWED_ENVIRONMENT_KEYS if key in source}
    if CODEX_HOME_ENVIRONMENT in source:
        environment["HOME"] = validate_codex_home(source[CODEX_HOME_ENVIRONMENT])
        environment.pop("CODEX_HOME", None)
    return environment


def _redact(text: str | bytes | None, environment: Mapping[str, str]) -> str:
    redacted = text.decode("utf-8", errors="replace") if isinstance(text, bytes) else text or ""
    for key in SECRET_ENVIRONMENT_KEYS:
        value = environment.get(key)
        if value:
            redacted = redacted.replace(value, f"<redacted:{key}>")
    return redacted


def _structured_result(events: list[dict[str, Any]]) -> Any | None:
    result: Any | None = None
    for event in events:
        if event.get("type") == "structured_result" and "result" in event:
            result = event["result"]
            continue
        item = event.get("item")
        if (
            isinstance(item, dict)
            and item.get("type") == "agent_message"
            and isinstance(item.get("text"), str)
        ):
            try:
                result = json.loads(item["text"])
            except json.JSONDecodeError:
                continue
    return result


def _parse_jsonl(raw_stdout: str) -> tuple[list[dict[str, Any]], Any]:
    events: list[dict[str, Any]] = []
    for line_number, line in enumerate(raw_stdout.splitlines(), start=1):
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError as exc:
            raise CodexCLIError(f"Codex JSONL event {line_number} is malformed") from exc
        if not isinstance(event, dict):
            raise CodexCLIError(f"Codex JSONL event {line_number} is not an object")
        events.append(event)
    if not events:
        raise CodexCLIError("Codex returned no JSONL events")
    result = _structured_result(events)
    if result is None:
        raise CodexCLIError("Codex returned no required structured result")
    return events, result


def validate_recorded_result(value, *, prompt: str, output_schema: Path) -> CodexCLIResult:
    """Adopt a complete native response only for its original prompt and schema.

    This checks the invocation receipt, not the meaning or business schema of its
    output. Each calling stage still owns that validation. No process is started.
    """
    try:
        if not isinstance(prompt, str) or not prompt.strip() or not isinstance(output_schema, Path):
            raise CodexCLIError("Recorded Codex input binding is invalid")
        payload = value.model_dump(mode="json") if isinstance(value, CodexCLIResult) else value
        result = CodexCLIResult.model_validate(payload)
        if (
            output_schema.is_symlink()
            or result.prompt_hash != sha256_digest(prompt.encode())
            or result.output_schema_hash != sha256_digest(output_schema.read_bytes())
            or canonical_json_bytes(_parse_jsonl(result.raw_stdout_jsonl)[1])
            != canonical_json_bytes(result.structured_result)
        ):
            raise CodexCLIError("Recorded Codex response differs from its native input or output")
        return result
    except (OSError, TypeError, ValueError) as error:
        raise CodexCLIError("Recorded Codex response cannot be verified") from error


def output_validation_marker(result, prompt, schema_path, error_code):
    """Bind a known business-output failure to one complete native response."""
    try:
        checked = validate_recorded_result(result, prompt=prompt, output_schema=schema_path)
    except CodexCLIError:
        return None
    return {
        "schema_version": "model-output-validation-failure/v1",
        "result_revision": record_digest(checked.model_dump(mode="json")),
        "prompt_hash": checked.prompt_hash,
        "output_schema_hash": checked.output_schema_hash,
        "error_code": error_code,
    }


def require_codex_sign_in(
    executable: str, home: str | Path, *, runner=subprocess.run, timeout: int = 5
) -> None:
    """Check once that the dedicated home is signed in (the takeover's startup check)."""
    environment = {
        "HOME": validate_codex_home(home),
        "PATH": "/usr/bin:/bin:/usr/sbin:/sbin",
        "LANG": "en_US.UTF-8",
    }
    _require_signed_in(runner, executable, environment["HOME"], environment, timeout=timeout)


def _require_signed_in(runner, executable, workspace, environment, *, timeout=30) -> None:
    """Stop before the model call when the dedicated home has no sign-in; never fall back."""
    status = runner(
        [executable, "login", "status"],
        shell=False,
        cwd=workspace,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
        timeout=timeout,
    )
    if status.returncode != 0:
        home = environment["HOME"]
        raise CodexCLIError(
            "dedicated Codex home is not signed in; sign in once with: "
            f"env -u CODEX_HOME HOME='{home}' '{executable}' login",
            redacted_stderr=_redact(status.stderr or status.stdout, environment),
        )


def _check_schema_unchanged(path: Path, original: bytes) -> None:
    try:
        unchanged = not path.is_symlink() and path.read_bytes() == original
    except OSError:
        unchanged = False
    if not unchanged:
        raise CodexCLIError("Codex output schema changed during the call")


def run_codex_exec(
    config: CodexCLIConfig,
    prompt: str,
    *,
    runner: ProcessRunner = subprocess.run,
    environment: Mapping[str, str] | None = None,
    timeout_seconds: int = 300,
    allow_non_repository: bool = False,
) -> CodexCLIResult:
    """Run Codex with an allowlisted environment and retain its raw event stream."""
    workspace, output_schema, schema_bytes = _validate_paths(config)
    argv = build_codex_exec_argv(config, prompt, allow_non_repository=allow_non_repository)
    # A dedicated input pipe avoids argv limits and preserves the native EOF monitor.
    argv[-1] = "-"
    # The CLI reads an immutable copy; later source edits cannot alter this call's schema.
    with tempfile.TemporaryDirectory(prefix=".codex-schema-", dir=workspace) as directory:
        snapshot = Path(directory) / "output.schema.json"
        snapshot.write_bytes(schema_bytes)
        snapshot.chmod(0o400)
        argv[argv.index("--output-schema") + 1] = str(snapshot)
        source_environment = os.environ if environment is None else environment
        if "TOMORROWSTAR_CODEX_EXECUTABLE" in source_environment:
            argv[0] = validate_codex_executable(source_environment["TOMORROWSTAR_CODEX_EXECUTABLE"])
        child_environment = _allowlisted_environment(source_environment)
        started_at = datetime.now(UTC)

        try:
            version_process = runner(
                [argv[0], "--version"],
                shell=False,
                cwd=workspace,
                env=child_environment,
                capture_output=True,
                text=True,
                check=False,
                timeout=30,
            )
            if version_process.returncode != 0:
                raise CodexCLIError("unable to capture Codex CLI version")
            cli_version = (version_process.stdout or version_process.stderr).strip()
            if not cli_version:
                raise CodexCLIError("Codex CLI version output is empty")
            if CODEX_HOME_ENVIRONMENT in source_environment:
                _require_signed_in(runner, argv[0], workspace, child_environment)

            _check_schema_unchanged(output_schema, schema_bytes)
            process = runner(
                argv,
                shell=False,
                input=prompt,
                cwd=workspace,
                env=child_environment,
                capture_output=True,
                text=True,
                check=False,
                timeout=timeout_seconds,
            )
        except subprocess.TimeoutExpired as exc:
            raise CodexCLIError(
                "Codex CLI timed out",
                raw_stdout_jsonl=_redact(exc.output, child_environment),
                redacted_stderr=_redact(exc.stderr, child_environment),
            ) from exc
        completed_at = datetime.now(UTC)
        redacted_stderr = _redact(process.stderr, child_environment)
        if process.returncode != 0:
            raise CodexCLIError(
                f"Codex exec failed with exit code {process.returncode}: {redacted_stderr}",
                raw_stdout_jsonl=_redact(process.stdout, child_environment),
                redacted_stderr=redacted_stderr,
            )
        try:
            _check_schema_unchanged(output_schema, schema_bytes)
            _check_schema_unchanged(snapshot, schema_bytes)
            _, structured_result = _parse_jsonl(process.stdout)
        except CodexCLIError as exc:
            raise CodexCLIError(
                str(exc),
                raw_stdout_jsonl=_redact(process.stdout, child_environment),
                redacted_stderr=redacted_stderr,
            ) from exc
        # Subprocess output is untrusted evidence and cannot promote an alias into an
        # immutable identity. Only an operator-configured snapshot crosses that boundary.
        resolved_snapshot = config.immutable_snapshot
        model_identity = ModelIdentity(
            schema_version="model-identity/v1",
            model_alias=config.requested_model,
            resolved_snapshot=resolved_snapshot,
        )
        drift_limitation = (
            None
            if resolved_snapshot
            else ModelDriftLimitation(
                schema_version="model-drift-limitation/v1",
                reason=config.drift_limitation_reason,
                raw_response_retained=True,
            )
        )
        sanitized_argv = [*argv[:-1], f"<prompt:{sha256_digest(prompt.encode())}>"]
        return CodexCLIResult(
            schema_version="codex-cli-result/v1",
            started_at=started_at,
            completed_at=completed_at,
            cli_version=cli_version,
            sanitized_argv=sanitized_argv,
            exit_code=process.returncode,
            raw_stdout_jsonl=process.stdout,
            redacted_stderr=redacted_stderr,
            structured_result=structured_result,
            requested_configuration={
                "model": config.requested_model,
                "reasoning_effort": config.reasoning_effort,
                "sandbox": config.sandbox,
            },
            model_identity=model_identity,
            model_drift_limitation=drift_limitation,
            prompt_hash=sha256_digest(prompt.encode()),
            output_schema_hash=sha256_digest(schema_bytes),
        )
