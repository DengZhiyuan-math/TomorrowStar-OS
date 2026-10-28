from __future__ import annotations

import json
import os
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from career_evidence_graph.codex_cli import (
    CodexCLIConfig,
    CodexCLIError,
    build_codex_exec_argv,
    run_codex_exec,
)
from career_evidence_graph.validation.store import (
    FormalRunStorageError,
    FormalRunStore,
    load_charter,
)


def _schema(workspace: Path) -> Path:
    path = workspace / "result.schema.json"
    path.write_text(
        json.dumps({"type": "object", "required": ["status"]}),
        encoding="utf-8",
    )
    return path


def _config(workspace: Path) -> CodexCLIConfig:
    return CodexCLIConfig(
        schema_version="codex-cli-config/v1",
        workspace=workspace,
        output_schema=_schema(workspace),
        drift_limitation_reason="Alias may drift; raw JSONL is retained.",
    )


class FakeRunner:
    def __init__(self, exec_process: subprocess.CompletedProcess[str]) -> None:
        self.exec_process = exec_process
        self.calls: list[tuple[list[str], dict[str, object]]] = []

    def __call__(self, argv, **kwargs):
        self.calls.append((argv, kwargs))
        if argv == ["codex", "--version"]:
            return subprocess.CompletedProcess(argv, 0, "codex-cli 0.146.0\n", "")
        return self.exec_process


def _success_process() -> subprocess.CompletedProcess[str]:
    event = {
        "type": "item.completed",
        "item": {"type": "agent_message", "text": '{"status":"ok"}'},
    }
    return subprocess.CompletedProcess(["codex", "exec"], 0, f"{json.dumps(event)}\n", "")


def _success_process_with_untrusted_model_claim() -> subprocess.CompletedProcess[str]:
    events = [
        {"type": "turn.started", "model": "attacker-claimed-snapshot"},
        {
            "type": "item.completed",
            "item": {"type": "agent_message", "text": '{"status":"ok"}'},
        },
    ]
    stdout = "".join(f"{json.dumps(event)}\n" for event in events)
    return subprocess.CompletedProcess(["codex", "exec"], 0, stdout, "")


def test_argv_locks_luna_medium_json_schema_workspace_and_read_only(tmp_path):
    prompt = 'Return JSON; $(touch /tmp/nope); "quoted"'

    argv = build_codex_exec_argv(_config(tmp_path), prompt)

    assert argv[:2] == ["codex", "exec"]
    assert argv[argv.index("--model") + 1] == "gpt-5.6-luna"
    assert argv[argv.index("--config") + 1] == 'model_reasoning_effort="medium"'
    assert "--json" in argv
    assert argv[argv.index("--output-schema") + 1] == str(
        (tmp_path / "result.schema.json").resolve()
    )
    assert argv[argv.index("--cd") + 1] == str(tmp_path.resolve())
    assert argv[argv.index("--sandbox") + 1] == "read-only"
    assert argv[-1] == prompt


def test_argv_excludes_every_out_of_scope_or_privilege_expanding_surface(tmp_path):
    argv = build_codex_exec_argv(_config(tmp_path), "prompt")
    forbidden = {
        "--add-dir",
        "--dangerously-bypass-approvals-and-sandbox",
        "--image",
        "--oss",
        "--output-last-message",
        "danger-full-access",
        "resume",
        "review",
    }

    assert forbidden.isdisjoint(argv)


@pytest.mark.skipif(shutil.which("codex") is None, reason="Codex CLI is not installed")
def test_installed_cli_accepts_the_locked_reasoning_config_syntax():
    result = subprocess.run(
        [
            "codex",
            "exec",
            "--config",
            'model_reasoning_effort="medium"',
            "--help",
        ],
        shell=False,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr


def test_runner_uses_shell_false_redacts_secrets_and_retains_raw_jsonl(tmp_path):
    prompt = "sensitive prompt $(whoami)"
    secret = "sentinel-secret-value"
    process = _success_process()
    process.stderr = f"diagnostic accidentally included {secret}"
    runner = FakeRunner(process)

    result = run_codex_exec(
        _config(tmp_path),
        prompt,
        runner=runner,
        environment={
            "PATH": "/usr/bin",
            "HOME": "/tmp/home",
            "OPENAI_API_KEY": secret,
            "UNRELATED_SECRET": "must-not-be-passed",
        },
    )

    assert all(kwargs["shell"] is False for _, kwargs in runner.calls)
    assert runner.calls[-1][0][-1] == "-"
    assert runner.calls[-1][1]["input"] == prompt
    assert "UNRELATED_SECRET" not in runner.calls[-1][1]["env"]
    assert secret not in result.model_dump_json()
    assert "<redacted:OPENAI_API_KEY>" in result.redacted_stderr
    assert result.raw_stdout_jsonl == process.stdout
    assert result.structured_result == {"status": "ok"}
    assert result.model_identity.model_alias == "gpt-5.6-luna"
    assert result.model_drift_limitation is not None
    assert result.sanitized_argv[-1].startswith("<prompt:sha256:")


def test_prompt_larger_than_argument_limit_uses_dedicated_subprocess_input(tmp_path):
    prompt = "Synthetic large prompt\n" + "中文" * os.sysconf("SC_ARG_MAX")
    runner = FakeRunner(_success_process())
    result = run_codex_exec(_config(tmp_path), prompt, runner=runner)

    version_argv, version_options = runner.calls[0]
    argv, options = runner.calls[1]
    assert version_argv == ["codex", "--version"]
    assert "input" not in version_options
    assert len(prompt.encode()) > os.sysconf("SC_ARG_MAX")
    assert argv[-1] == "-" and prompt not in argv
    assert sum(len(argument.encode()) + 1 for argument in argv) < os.sysconf("SC_ARG_MAX")
    assert options["input"] == prompt and options["text"] is True
    assert "stdin" not in options
    assert result.sanitized_argv[-1] == f"<prompt:{result.prompt_hash}>"
    assert result.structured_result == {"status": "ok"}


@pytest.mark.parametrize("change", ["edit", "delete", "symlink", "snapshot-edit"])
def test_schema_changed_during_call_cannot_be_sealed_with_success(tmp_path, change):
    config = _config(tmp_path)
    schema_before = config.output_schema.read_bytes()
    used_schemas = []
    raw = (
        '{"type":"turn.completed","usage":{"input_tokens":37,"output_tokens":11}}\n'
        '{"type":"structured_result","result":{"status":"ok"}}\n'
    )

    def changing_schema(argv, **kwargs):
        if argv[-1] == "--version":
            return subprocess.CompletedProcess(argv, 0, "codex-cli synthetic\n", "")
        selected = Path(argv[argv.index("--output-schema") + 1])
        used_schemas.append(selected.read_bytes())
        if change == "edit":
            config.output_schema.write_text('{"type":"object","required":["changed"]}')
            assert selected.read_bytes() == schema_before
        elif change == "snapshot-edit":
            selected.chmod(0o600)
            selected.write_text("{}")
        else:
            config.output_schema.unlink()
            if change == "symlink":
                config.output_schema.symlink_to(selected)
        return subprocess.CompletedProcess(argv, 0, raw, "Synthetic diagnostic openai-secret")

    with pytest.raises(CodexCLIError, match="schema changed") as raised:
        run_codex_exec(
            config,
            "Synthetic prompt",
            runner=changing_schema,
            environment={"OPENAI_API_KEY": "openai-secret"},
        )

    assert used_schemas == [schema_before]
    assert raised.value.raw_stdout_jsonl == raw
    assert raised.value.redacted_stderr == "Synthetic diagnostic <redacted:OPENAI_API_KEY>"
    assert not list(tmp_path.glob(".codex-schema-*"))


@pytest.mark.parametrize("outcome", ["timeout", "nonzero"])
def test_failed_schema_drift_call_retains_partial_usage_and_cleans_snapshot(tmp_path, outcome):
    config = _config(tmp_path)
    raw = (
        '{"type":"turn.completed","usage":{"input_tokens":37,"output_tokens":11}}\n'
        '{"type":"error","message":"Synthetic openai-secret"}\n'
    )

    def failing_call(argv, **kwargs):
        if argv[-1] == "--version":
            return subprocess.CompletedProcess(argv, 0, "codex-cli synthetic\n", "")
        config.output_schema.write_text("{}")
        if outcome == "timeout":
            raise subprocess.TimeoutExpired(
                argv, kwargs["timeout"], output=raw.encode(), stderr=b"openai-secret"
            )
        return subprocess.CompletedProcess(argv, 1, raw, "openai-secret")

    with pytest.raises(CodexCLIError) as raised:
        run_codex_exec(
            config,
            "Synthetic prompt",
            runner=failing_call,
            environment={"OPENAI_API_KEY": "openai-secret"},
        )

    assert raised.value.raw_stdout_jsonl == raw.replace(
        "openai-secret", "<redacted:OPENAI_API_KEY>"
    )
    assert raised.value.redacted_stderr == "<redacted:OPENAI_API_KEY>"
    assert not list(tmp_path.glob(".codex-schema-*"))


@pytest.mark.parametrize("change", ["edit", "delete", "symlink"])
def test_schema_drift_before_exec_stops_the_call(tmp_path, change):
    config = _config(tmp_path)
    calls = []

    def changing_before_exec(argv, **kwargs):
        calls.append(argv)
        if change == "edit":
            config.output_schema.write_text("{}")
        else:
            original = config.output_schema.read_bytes()
            config.output_schema.unlink()
            if change == "symlink":
                replacement = tmp_path / "replacement.schema.json"
                replacement.write_bytes(original)
                config.output_schema.symlink_to(replacement)
        return subprocess.CompletedProcess(argv, 0, "codex-cli synthetic\n", "")

    with pytest.raises(CodexCLIError, match="schema changed"):
        run_codex_exec(config, "Synthetic prompt", runner=changing_before_exec)

    assert calls == [["codex", "--version"]]
    assert not list(tmp_path.glob(".codex-schema-*"))


def test_success_hash_binds_to_the_actual_private_schema_snapshot(tmp_path):
    config = _config(tmp_path)
    snapshots = []

    def checking_schema(argv, **kwargs):
        if argv[-1] == "--version":
            return subprocess.CompletedProcess(argv, 0, "codex-cli synthetic\n", "")
        selected = Path(argv[argv.index("--output-schema") + 1])
        assert selected != config.output_schema
        assert selected.is_relative_to(config.workspace)
        assert selected.read_bytes() == b'{"type": "object", "required": ["status"]}'
        assert selected.stat().st_mode & 0o777 == 0o400
        snapshots.append(selected)
        return _success_process()

    result = run_codex_exec(config, "Synthetic prompt", runner=checking_schema)

    assert result.output_schema_hash == (
        "sha256:54ae0f996c6b27bd8a2b46ba66366b5819b658462c2c2abedf06ba7509f8d450"
    )
    assert not snapshots[0].exists()
    assert config.output_schema.read_bytes() == b'{"type": "object", "required": ["status"]}'


def test_untrusted_event_cannot_claim_an_immutable_model_snapshot(tmp_path):
    result = run_codex_exec(
        _config(tmp_path),
        "prompt",
        runner=FakeRunner(_success_process_with_untrusted_model_claim()),
    )

    assert result.model_identity.resolved_snapshot is None
    assert result.model_drift_limitation is not None


@pytest.mark.parametrize(
    "process",
    (
        subprocess.CompletedProcess(["codex"], 2, "", "failed"),
        subprocess.CompletedProcess(["codex"], 0, "not-json\n", ""),
        subprocess.CompletedProcess(["codex"], 0, '{"type":"turn.completed"}\n', ""),
    ),
)
def test_nonzero_malformed_or_missing_result_never_succeeds(tmp_path, process):
    with pytest.raises(CodexCLIError) as raised:
        run_codex_exec(_config(tmp_path), "prompt", runner=FakeRunner(process))
    assert raised.value.raw_stdout_jsonl == process.stdout


def test_failed_structured_call_retains_redacted_error_events(tmp_path):
    secret = "sentinel-failed-call-secret"
    stdout = json.dumps({"type": "error", "message": f"invalid schema {secret}"}) + "\n"
    process = subprocess.CompletedProcess(["codex"], 1, stdout, f"diagnostic {secret}")
    with pytest.raises(CodexCLIError) as raised:
        run_codex_exec(
            _config(tmp_path),
            "prompt",
            runner=FakeRunner(process),
            environment={"OPENAI_API_KEY": secret},
        )
    assert "invalid schema" in raised.value.raw_stdout_jsonl
    assert secret not in raised.value.raw_stdout_jsonl + raised.value.redacted_stderr


@pytest.mark.parametrize("phase", ["version", "exec"])
@pytest.mark.parametrize("output_type", ["text", "bytes", "none"])
def test_timeout_retains_decoded_redacted_partial_output(tmp_path, phase, output_type):
    raw = (
        '{"type":"error","message":"Synthetic 模型输出 openai-secret codex-secret"}\n'
        '{"type":"turn.completed","usage":{"input_tokens":37,"output_tokens":11}}\n'
    )
    stderr = "Synthetic 诊断 openai-secret codex-secret"
    calls = []

    def timed_out(argv, **kwargs):
        calls.append(argv)
        if phase == "exec" and argv[-1] == "--version":
            return subprocess.CompletedProcess(argv, 0, "codex-cli synthetic\n", "")
        output = raw if output_type == "text" else raw.encode() if output_type == "bytes" else None
        error = (
            stderr if output_type == "text" else stderr.encode() if output_type == "bytes" else None
        )
        raise subprocess.TimeoutExpired(argv, kwargs["timeout"], output=output, stderr=error)

    with pytest.raises(CodexCLIError, match="timed out") as raised:
        run_codex_exec(
            _config(tmp_path),
            "Synthetic private prompt",
            runner=timed_out,
            environment={"OPENAI_API_KEY": "openai-secret", "CODEX_API_KEY": "codex-secret"},
        )

    expected_raw = raw.replace("openai-secret", "<redacted:OPENAI_API_KEY>").replace(
        "codex-secret", "<redacted:CODEX_API_KEY>"
    )
    expected_stderr = stderr.replace("openai-secret", "<redacted:OPENAI_API_KEY>").replace(
        "codex-secret", "<redacted:CODEX_API_KEY>"
    )
    assert raised.value.raw_stdout_jsonl == (expected_raw if output_type != "none" else "")
    assert raised.value.redacted_stderr == (expected_stderr if output_type != "none" else "")
    assert "Synthetic private prompt" not in str(raised.value)
    assert len(calls) == (2 if phase == "exec" else 1)


def test_explicit_codex_executable_works_without_terminal_path(tmp_path):
    executable = tmp_path / "installed-cli"
    executable.write_text(
        '#!/bin/sh\nif [ "$1" = "--version" ]; then echo "codex-cli synthetic"; '
        'else echo \'{"type":"structured_result","result":{"status":"ok"}}\'; fi\n'
    )
    executable.chmod(0o700)

    result = run_codex_exec(
        _config(tmp_path),
        "Synthetic prompt",
        environment={
            "PATH": "/usr/bin:/bin:/usr/sbin:/sbin",
            "TOMORROWSTAR_CODEX_EXECUTABLE": str(executable),
        },
    )

    assert result.structured_result == {"status": "ok"}
    assert result.cli_version == "codex-cli synthetic"
    assert result.sanitized_argv[0] == str(executable)


def test_exec_completes_without_consuming_the_native_parent_input_pipe(tmp_path):
    config = _config(tmp_path)
    cli_script = tmp_path / "synthetic-cli.py"
    cli_script.write_text(
        "import json, os, sys\n"
        "if sys.argv[1:] == ['--version']:\n"
        "    print('codex-cli synthetic')\n"
        "else:\n"
        "    prompt = sys.stdin.read()\n"
        "    assert sys.argv[-1] == '-'\n"
        "    assert len(prompt.encode()) > os.sysconf('SC_ARG_MAX')\n"
        "    assert prompt == 'Synthetic stdin prompt\\n' + '中文' * os.sysconf('SC_ARG_MAX')\n"
        "    print(json.dumps({'type': 'structured_result', 'result': {'status': 'ok'}}))\n"
    )
    executable = tmp_path / "synthetic-cli"
    executable.write_text(
        f'#!/bin/sh\nexec {shlex.quote(sys.executable)} {shlex.quote(str(cli_script))} "$@"\n'
    )
    executable.chmod(0o700)
    parent_script = (
        "import json, os, sys\n"
        f"sys.path.insert(0, {str(Path(__file__).resolve().parents[1] / 'src')!r})\n"
        "from career_evidence_graph.codex_cli import "
        "CodexCLIConfig, CodexCLIError, run_codex_exec\n"
        f"config = CodexCLIConfig.model_validate_json({config.model_dump_json()!r})\n"
        "try:\n"
        "    prompt = 'Synthetic stdin prompt\\n' + '中文' * os.sysconf('SC_ARG_MAX')\n"
        "    result = run_codex_exec(config, prompt, timeout_seconds=1)\n"
        "except CodexCLIError as exc:\n"
        "    print(json.dumps({'error': str(exc), 'stdout': exc.raw_stdout_jsonl, "
        "'stderr': exc.redacted_stderr}))\n"
        "else:\n"
        "    print(json.dumps({'result': result.structured_result, "
        "'parent_input': sys.stdin.readline().strip()}))\n"
    )

    # Keep the native host's input pipe open throughout the CLI invocation.
    with subprocess.Popen(
        [sys.executable, "-c", parent_script],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env={
            **os.environ,
            "TOMORROWSTAR_CODEX_EXECUTABLE": str(executable),
        },
    ) as parent:
        assert parent.stdin is not None
        parent.stdin.write("Synthetic parent monitor input\n")
        parent.stdin.flush()
        try:
            parent.wait(timeout=5)
        finally:
            if parent.poll() is None:
                parent.kill()
                parent.wait(timeout=5)
        assert parent.stdout is not None
        assert parent.stderr is not None
        assert parent.returncode == 0, parent.stderr.read()
        report = json.loads(parent.stdout.read())

    assert report == {
        "result": {"status": "ok"},
        "parent_input": "Synthetic parent monitor input",
    }


@pytest.mark.parametrize("target", ["relative", "missing", "directory", "not-executable"])
def test_invalid_configured_codex_is_rejected_before_any_process(tmp_path, target):
    selected = tmp_path / target
    if target == "directory":
        selected.mkdir()
    elif target == "not-executable":
        selected.write_text("Synthetic data")
        selected.chmod(0o600)
    runner = FakeRunner(_success_process())
    with pytest.raises(CodexCLIError, match="executable is unavailable"):
        run_codex_exec(
            _config(tmp_path),
            "Synthetic prompt",
            runner=runner,
            environment={
                "TOMORROWSTAR_CODEX_EXECUTABLE": "codex" if target == "relative" else str(selected)
            },
        )
    assert runner.calls == []


def test_schema_and_workspace_symlink_escapes_are_rejected(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    outside = tmp_path / "outside.schema.json"
    outside.write_text("{}", encoding="utf-8")
    linked = workspace / "linked.schema.json"
    linked.symlink_to(outside)

    with pytest.raises(CodexCLIError, match="symlink"):
        build_codex_exec_argv(
            CodexCLIConfig(
                schema_version="codex-cli-config/v1",
                workspace=workspace,
                output_schema=linked,
                drift_limitation_reason="Alias drift.",
            ),
            "prompt",
        )


def test_live_store_rejects_alias_without_drift_limitation(tmp_path, charter_path):
    result = run_codex_exec(
        _config(tmp_path),
        "prompt",
        runner=FakeRunner(_success_process()),
    )
    store = FormalRunStore(tmp_path)
    raw_response = {
        "raw_jsonl": result.raw_stdout_jsonl,
        "result": result.structured_result,
    }
    lineage = {
        "fixture": {},
        "artifacts": [],
        "prompt": {},
        "model": {},
        "configuration": {},
        "policy": {},
        "reviewer": {},
    }

    with pytest.raises(FormalRunStorageError, match="drift limitation"):
        store.create(
            run_id="invalid-live",
            charter=load_charter(charter_path),
            raw_response=raw_response,
            proposal=result.structured_result,
            confirmed_result=result.structured_result,
            lineage_inputs=lineage,
            execution_mode="live-reexecution",
            codex_cli_result=result,
            model_identity=result.model_identity,
            model_drift_limitation=None,
        )

    assert not (tmp_path / "formal-runs/invalid-live").exists()


def test_successful_live_metadata_is_immutable_and_verifiable(tmp_path, charter_path):
    result = run_codex_exec(
        _config(tmp_path),
        "prompt",
        runner=FakeRunner(_success_process()),
    )
    store = FormalRunStore(tmp_path)
    raw_response = {
        "raw_jsonl": result.raw_stdout_jsonl,
        "result": result.structured_result,
    }
    lineage = {
        "fixture": {},
        "artifacts": [],
        "prompt": {"hash": result.prompt_hash},
        "model": result.model_identity.model_dump(mode="json"),
        "configuration": result.requested_configuration,
        "policy": {},
        "reviewer": {},
    }

    manifest = store.create(
        run_id="valid-live",
        charter=load_charter(charter_path),
        raw_response=raw_response,
        proposal=result.structured_result,
        confirmed_result=result.structured_result,
        lineage_inputs=lineage,
        execution_mode="live-reexecution",
        limitations=["technical gate only"],
        codex_cli_result=result,
        model_identity=result.model_identity,
        model_drift_limitation=result.model_drift_limitation,
    )

    assert store.verify("valid-live") == manifest
    assert manifest.model_identity == result.model_identity
    assert manifest.model_drift_limitation == result.model_drift_limitation
    assert (
        store.payload("valid-live", "codex_cli_result.json")["raw_stdout_jsonl"]
        == result.raw_stdout_jsonl
    )


def test_live_store_rejects_raw_jsonl_mismatch(tmp_path, charter_path):
    result = run_codex_exec(
        _config(tmp_path),
        "prompt",
        runner=FakeRunner(_success_process()),
    )

    with pytest.raises(FormalRunStorageError, match="raw JSONL does not match"):
        FormalRunStore(tmp_path).create(
            run_id="mismatch",
            charter=load_charter(charter_path),
            raw_response={
                "raw_jsonl": "different",
                "result": result.structured_result,
            },
            proposal=result.structured_result,
            confirmed_result=result.structured_result,
            lineage_inputs={
                "fixture": {},
                "artifacts": [],
                "prompt": {},
                "model": {},
                "configuration": {},
                "policy": {},
                "reviewer": {},
            },
            execution_mode="live-reexecution",
            codex_cli_result=result,
            model_identity=result.model_identity,
            model_drift_limitation=result.model_drift_limitation,
        )


def test_operator_documentation_keeps_live_claims_bounded_and_commands_separate():
    document = Path("docs/validation-runs.md").read_text(encoding="utf-8")

    assert "uv run --locked python scripts/run_career_evidence.py run create" in document
    assert "uv run --locked python scripts/run_career_evidence.py replay" in document
    assert "CAREER_EVIDENCE_ENABLE_LIVE_MODEL=1" in document
    assert "--model gpt-5.6-luna" in document
    assert 'model_reasoning_effort="medium"' in document
    assert "--sandbox read-only" in document
    assert "Neither result proves" in document
    assert "résumé submissions, interviews, or hiring outcomes" in document


@pytest.mark.live_model
@pytest.mark.skipif(
    os.environ.get("CAREER_EVIDENCE_ENABLE_LIVE_MODEL") != "1",
    reason="requires explicit live-model opt-in",
)
def test_opt_in_live_luna_medium_smoke():
    if shutil.which("codex") is None:
        pytest.skip("Codex CLI is not installed")
    workspace = Path.cwd()
    config = CodexCLIConfig(
        schema_version="codex-cli-config/v1",
        workspace=workspace,
        output_schema=workspace / "validation/schemas/technical-gate-result.schema.json",
        drift_limitation_reason="Alias may drift; this smoke retains raw JSONL.",
    )

    result = run_codex_exec(
        config,
        'Return exactly the JSON object {"status":"ok"}. Do not inspect files or call tools.',
    )

    assert result.structured_result == {"status": "ok"}
    assert result.requested_configuration["model"] == "gpt-5.6-luna"
    assert result.requested_configuration["reasoning_effort"] == "medium"


def _dedicated_home(tmp_path: Path) -> Path:
    home = tmp_path / "codex-home"
    # Codex installs its bundled system skills here at startup; they are not user context.
    (home / ".codex/skills/.system").mkdir(parents=True)
    return home


def test_dedicated_codex_home_replaces_the_user_home(tmp_path):
    # MC-21: the App's model calls must not read the user's own ~/.codex context.
    home = _dedicated_home(tmp_path)
    runner = FakeRunner(_success_process())
    run_codex_exec(
        _config(tmp_path),
        "prompt",
        runner=runner,
        environment={
            "PATH": "/usr/bin",
            "HOME": "/Users/synthetic-user",
            "CODEX_HOME": "/Users/synthetic-user/.codex",
            "TOMORROWSTAR_CODEX_HOME": str(home),
        },
    )
    for _, kwargs in runner.calls:
        assert kwargs["env"]["HOME"] == str(home.resolve())
        assert "CODEX_HOME" not in kwargs["env"]


@pytest.mark.parametrize(
    "entry",
    [
        "AGENTS.md",
        "AGENTS.override.md",
        ".agents",
        ".codex/AGENTS.md",
        ".codex/AGENTS.override.md",
        ".codex/config.toml",
        ".codex/hooks.json",
        ".codex/prompts",
        ".codex/skills/personal-skill",
        ".codex/memories",
        ".codex/rules",
    ],
)
def test_dedicated_codex_home_with_personal_context_fails_closed(tmp_path, entry):
    home = _dedicated_home(tmp_path)
    target = home / entry
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("context") if target.suffix in {".md", ".toml", ".json"} else target.mkdir()
    runner = FakeRunner(_success_process())
    with pytest.raises(CodexCLIError, match="dedicated Codex home"):
        run_codex_exec(
            _config(tmp_path),
            "prompt",
            runner=runner,
            environment={"PATH": "/usr/bin", "TOMORROWSTAR_CODEX_HOME": str(home)},
        )
    assert runner.calls == []


@pytest.mark.parametrize("home", ["missing", "user-home", "relative"])
def test_unusable_dedicated_codex_home_never_falls_back(tmp_path, home):
    value = {
        "missing": str(tmp_path / "missing"),
        "user-home": str(Path.home()),
        "relative": "codex-home",
    }[home]
    runner = FakeRunner(_success_process())
    with pytest.raises(CodexCLIError, match="dedicated Codex home"):
        run_codex_exec(
            _config(tmp_path),
            "prompt",
            runner=runner,
            environment={"PATH": "/usr/bin", "TOMORROWSTAR_CODEX_HOME": value},
        )
    assert runner.calls == []


@pytest.mark.parametrize("link", [".codex", ".codex/skills/.system"])
def test_dedicated_codex_home_rejects_symlinked_context(tmp_path, link):
    home = _dedicated_home(tmp_path)
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    target = home / link
    shutil.rmtree(target)
    target.symlink_to(elsewhere, target_is_directory=True)
    runner = FakeRunner(_success_process())
    with pytest.raises(CodexCLIError, match="dedicated Codex home"):
        run_codex_exec(
            _config(tmp_path),
            "prompt",
            runner=runner,
            environment={"PATH": "/usr/bin", "TOMORROWSTAR_CODEX_HOME": str(home)},
        )
    assert runner.calls == []


def test_exec_ignores_user_configuration_and_cross_run_state(tmp_path):
    argv = build_codex_exec_argv(_config(tmp_path), "prompt")
    assert {"--ignore-user-config", "--ignore-rules"} <= set(argv)
    disabled = {argv[index + 1] for index, value in enumerate(argv) if value == "--disable"}
    assert disabled == {"memories", "apps", "plugins", "hooks"}


def test_signed_out_dedicated_codex_home_stops_before_the_model_call(tmp_path):
    home = _dedicated_home(tmp_path)

    class SignedOut(FakeRunner):
        def __call__(self, argv, **kwargs):
            if argv[1:] == ["login", "status"]:
                self.calls.append((argv, kwargs))
                return subprocess.CompletedProcess(argv, 1, "", "Not logged in\n")
            return super().__call__(argv, **kwargs)

    runner = SignedOut(_success_process())
    with pytest.raises(CodexCLIError, match="not signed in") as raised:
        run_codex_exec(
            _config(tmp_path),
            "prompt",
            runner=runner,
            environment={"PATH": "/usr/bin", "TOMORROWSTAR_CODEX_HOME": str(home)},
        )
    assert str(home.resolve()) in str(raised.value)
    assert "Not logged in" in raised.value.redacted_stderr
    assert all(argv[1] != "exec" for argv, _ in runner.calls)


def test_account_revision_follows_the_dedicated_codex_home(tmp_path, monkeypatch):
    from career_evidence_graph.application_preparation import preparation_inputs

    home = _dedicated_home(tmp_path)
    user = tmp_path / "user-codex"
    user.mkdir()
    monkeypatch.setenv("CODEX_HOME", str(user))
    monkeypatch.setenv("TOMORROWSTAR_CODEX_HOME", str(home))
    original = preparation_inputs(tmp_path)["account_context_revision"]
    (user / "auth.json").write_text("{}")
    assert preparation_inputs(tmp_path)["account_context_revision"] == original
    (home / ".codex/auth.json").write_text("{}")
    assert preparation_inputs(tmp_path)["account_context_revision"] != original
