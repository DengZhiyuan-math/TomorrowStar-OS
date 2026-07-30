"""Narrow, shell-free Codex CLI adapter for the opt-in live technical gate."""

from __future__ import annotations

import json
import os
import subprocess
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .validation.hashing import sha256_digest
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


class CodexCLIError(RuntimeError):
    """Raised when the CLI boundary cannot produce a valid technical-gate result."""


def _resolved_workspace_path(path: Path, *, label: str) -> Path:
    if path.is_symlink():
        raise CodexCLIError(f"{label} cannot be a symlink")
    try:
        return path.resolve(strict=True)
    except OSError as exc:
        raise CodexCLIError(f"{label} does not exist") from exc


def _validate_paths(config: CodexCLIConfig) -> tuple[Path, Path]:
    workspace = _resolved_workspace_path(config.workspace, label="workspace")
    if not workspace.is_dir():
        raise CodexCLIError("workspace must be a directory")
    output_schema = _resolved_workspace_path(config.output_schema, label="output schema")
    if not output_schema.is_file() or not output_schema.is_relative_to(workspace):
        raise CodexCLIError("output schema must be a regular file inside workspace")
    try:
        schema = json.loads(output_schema.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CodexCLIError("output schema must contain valid JSON") from exc
    if not isinstance(schema, dict):
        raise CodexCLIError("output schema must be a JSON object")
    return workspace, output_schema


def build_codex_exec_argv(config: CodexCLIConfig, prompt: str) -> list[str]:
    """Build the fixed read-only argument vector with no shell interpretation."""
    workspace, output_schema = _validate_paths(config)
    if not prompt.strip():
        raise CodexCLIError("prompt cannot be blank")
    model = config.immutable_snapshot or config.requested_model
    return [
        config.executable,
        "exec",
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
        prompt,
    ]


def _allowlisted_environment(source: Mapping[str, str]) -> dict[str, str]:
    return {key: source[key] for key in ALLOWED_ENVIRONMENT_KEYS if key in source}


def _redact(text: str, environment: Mapping[str, str]) -> str:
    redacted = text
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


def run_codex_exec(
    config: CodexCLIConfig,
    prompt: str,
    *,
    runner: ProcessRunner = subprocess.run,
    environment: Mapping[str, str] | None = None,
    timeout_seconds: int = 300,
) -> CodexCLIResult:
    """Run Codex with an allowlisted environment and retain its raw event stream."""
    workspace, output_schema = _validate_paths(config)
    argv = build_codex_exec_argv(config, prompt)
    source_environment = os.environ if environment is None else environment
    child_environment = _allowlisted_environment(source_environment)
    started_at = datetime.now(UTC)

    version_process = runner(
        [config.executable, "--version"],
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

    process = runner(
        argv,
        shell=False,
        cwd=workspace,
        env=child_environment,
        capture_output=True,
        text=True,
        check=False,
        timeout=timeout_seconds,
    )
    completed_at = datetime.now(UTC)
    redacted_stderr = _redact(process.stderr, child_environment)
    if process.returncode != 0:
        raise CodexCLIError(
            f"Codex exec failed with exit code {process.returncode}: {redacted_stderr}"
        )
    _, structured_result = _parse_jsonl(process.stdout)
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
        output_schema_hash=sha256_digest(output_schema.read_bytes()),
    )
