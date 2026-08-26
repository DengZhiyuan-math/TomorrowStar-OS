from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parents[1]
LAUNCHER = ROOT / "scripts" / "run_career_evidence.py"
FIXTURE = ROOT / "validation/fixtures/stoa/v1/known-good.json"


def run_cli(*args: str, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    import os

    return subprocess.run(
        [sys.executable, str(LAUNCHER), *args],
        cwd=ROOT,
        capture_output=True,
        text=True,
        env=os.environ | (env or {}),
    )


def test_audit_offline_tracer_starts_pauses_and_resumes(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    started = run_cli(
        "audit",
        "start",
        "--workspace",
        str(workspace),
        "--fixture",
        str(FIXTURE),
        "--contribution-id",
        "contrib-stoa-authorization-boundary",
    )
    assert started.returncode == 0, started.stderr
    first = json.loads(started.stdout)
    assert first["question"]["reason"]
    assert first["question"]["prompt"]
    audit_id = first["audit_id"]

    answered = run_cli(
        "audit",
        "answer",
        "--workspace",
        str(workspace),
        "--audit-id",
        audit_id,
        "--answer",
        "I chose and verified the boundary.",
    )
    assert answered.returncode == 0, answered.stderr
    paused = run_cli("audit", "pause", "--workspace", str(workspace), "--audit-id", audit_id)
    assert paused.returncode == 0, paused.stderr
    resumed = run_cli("audit", "resume", "--workspace", str(workspace), "--audit-id", audit_id)
    assert resumed.returncode == 0, resumed.stderr
    assert json.loads(resumed.stdout)["audit_id"] == audit_id


def test_audit_workflow_errors_are_structured_and_do_not_write(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    started = run_cli(
        "audit",
        "start",
        "--workspace",
        str(workspace),
        "--fixture",
        str(FIXTURE),
        "--contribution-id",
        "contrib-stoa-authorization-boundary",
    )
    audit_id = json.loads(started.stdout)["audit_id"]
    snapshot_path = workspace / "audits" / audit_id / "snapshot.json"
    before = snapshot_path.read_bytes()
    rejected = run_cli("audit", "resume", "--workspace", str(workspace), "--audit-id", audit_id)
    assert rejected.returncode == 2
    assert json.loads(rejected.stderr)["error"] == "audit_workflow_error"
    assert "Traceback" not in rejected.stderr
    assert snapshot_path.read_bytes() == before
