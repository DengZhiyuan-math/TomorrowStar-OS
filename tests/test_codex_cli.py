from __future__ import annotations

import json
import os
import shutil
import subprocess
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
    assert runner.calls[-1][0][-1] == prompt
    assert "UNRELATED_SECRET" not in runner.calls[-1][1]["env"]
    assert secret not in result.model_dump_json()
    assert "<redacted:OPENAI_API_KEY>" in result.redacted_stderr
    assert result.raw_stdout_jsonl == process.stdout
    assert result.structured_result == {"status": "ok"}
    assert result.model_identity.model_alias == "gpt-5.6-luna"
    assert result.model_drift_limitation is not None
    assert result.sanitized_argv[-1].startswith("<prompt:sha256:")


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
    with pytest.raises(CodexCLIError):
        run_codex_exec(_config(tmp_path), "prompt", runner=FakeRunner(process))


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

    assert "uv run --locked career-evidence run create" in document
    assert "uv run --locked career-evidence replay" in document
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
