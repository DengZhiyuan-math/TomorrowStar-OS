from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def _run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "career_evidence_graph.cli", *args],
        check=False,
        capture_output=True,
        text=True,
    )


def _write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value), encoding="utf-8")


def test_offline_cli_crosses_real_storage_and_replay_boundaries(tmp_path, charter_path):
    inputs = tmp_path / "inputs"
    workspace = tmp_path / "workspace"
    inputs.mkdir()
    raw_response = inputs / "raw.json"
    proposal = inputs / "proposal.json"
    expected = inputs / "expected.json"
    result = {
        "trace_kind": "synthetic-plumbing-only",
        "functional_chain_connected": True,
    }
    _write_json(raw_response, {"provider_called": False, "result": result})
    _write_json(proposal, {"proposed": result})
    _write_json(expected, result)

    validated = _run("validate-charter", str(charter_path))
    assert validated.returncode == 0, validated.stderr

    created = _run(
        "run",
        "create",
        "--workspace",
        str(workspace),
        "--charter",
        str(charter_path),
        "--run-id",
        "tracer-001",
        "--raw-response",
        str(raw_response),
        "--proposal",
        str(proposal),
        "--expected-result",
        str(expected),
    )
    assert created.returncode == 0, created.stderr
    assert (workspace / "formal-runs" / "tracer-001" / "manifest.json").is_file()

    verified = _run("run", "verify", "--workspace", str(workspace), "--run-id", "tracer-001")
    assert verified.returncode == 0, verified.stderr

    replayed = _run("replay", "--workspace", str(workspace), "--run-id", "tracer-001")
    assert replayed.returncode == 0, replayed.stderr
    assert json.loads(replayed.stdout)["matched"] is True


def test_duplicate_run_is_rejected_without_overwrite(tmp_path, charter_path):
    value_path = tmp_path / "value.json"
    _write_json(value_path, {"result": {"ok": True}})
    expected_path = tmp_path / "expected.json"
    _write_json(expected_path, {"ok": True})
    base = (
        "run",
        "create",
        "--workspace",
        str(tmp_path / "workspace"),
        "--charter",
        str(charter_path),
        "--run-id",
        "same-run",
        "--raw-response",
        str(value_path),
        "--proposal",
        str(expected_path),
        "--expected-result",
        str(expected_path),
    )
    assert _run(*base).returncode == 0
    manifest_path = tmp_path / "workspace/formal-runs/same-run/manifest.json"
    original = manifest_path.read_bytes()

    duplicate = _run(*base)

    assert duplicate.returncode == 2
    assert manifest_path.read_bytes() == original
