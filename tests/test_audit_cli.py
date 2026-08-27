from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parents[1]
LAUNCHER = ROOT / "scripts" / "run_career_evidence.py"
FIXTURE = ROOT / "validation/fixtures/stoa/v1/known-good.json"


def run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(LAUNCHER), *args],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )


def test_checkout_source_cli_inspects_snapshot_and_resumes_one_action_at_a_time(tmp_path: Path):
    workspace = tmp_path / "workspace"
    start = (
        "audit",
        "start",
        "--workspace",
        str(workspace),
        "--fixture",
        str(FIXTURE),
        "--contribution-id",
        "contrib-stoa-authorization-boundary",
        "--audit-id",
        "audit-cli",
    )
    started = run_cli(*start)
    assert started.returncode == 0, started.stderr
    audit_id = json.loads(started.stdout)["audit_id"]
    snapshot_path = workspace / "audits" / f"{audit_id}.json"
    assert snapshot_path.is_file()

    paused = run_cli("audit", "pause", "--workspace", str(workspace), "--audit-id", audit_id)
    assert paused.returncode == 0, paused.stderr
    resumed = run_cli("audit", "resume", "--workspace", str(workspace), "--audit-id", audit_id)
    assert resumed.returncode == 0, resumed.stderr
    inspected = run_cli("audit", "inspect", "--workspace", str(workspace), "--audit-id", audit_id)
    assert inspected.returncode == 0, inspected.stderr
    snapshot = json.loads(inspected.stdout)["snapshot"]
    assert snapshot["audit_id"] == audit_id
    assert snapshot["inspected_facts"]
    assert snapshot["questions"]
    assert snapshot["coverage"]


def test_invalid_action_and_corrupt_snapshot_return_stable_errors_without_writes(
    tmp_path: Path,
) -> None:
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
        "--audit-id",
        "audit-cli-invalid",
    )
    audit_id = json.loads(started.stdout)["audit_id"]
    snapshot_path = workspace / "audits" / f"{audit_id}.json"
    before = snapshot_path.read_bytes()

    invalid = run_cli("audit", "resume", "--workspace", str(workspace), "--audit-id", audit_id)
    assert invalid.returncode == 2
    assert json.loads(invalid.stderr)["error"] == "audit_workflow_error"
    assert snapshot_path.read_bytes() == before

    snapshot_path.write_text("{bad}", encoding="utf-8")
    corrupt = run_cli("audit", "pause", "--workspace", str(workspace), "--audit-id", audit_id)
    assert corrupt.returncode == 2
    assert json.loads(corrupt.stderr)["error"] == "audit_storage_error"
    assert snapshot_path.read_text(encoding="utf-8") == "{bad}"


def test_cli_skip_contribution_rejects_a_stale_question_target(tmp_path: Path) -> None:
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
        "--audit-id",
        "audit-cli-stale-skip",
    )
    audit_id = json.loads(started.stdout)["audit_id"]
    snapshot_path = workspace / "audits" / f"{audit_id}.json"
    before = snapshot_path.read_bytes()

    rejected = run_cli(
        "audit",
        "skip-contribution",
        "--workspace",
        str(workspace),
        "--audit-id",
        audit_id,
        "--answer",
        "self rating: 6/10",
        "--question-id",
        "question-stale",
    )

    assert rejected.returncode == 2
    assert json.loads(rejected.stderr)["error"] == "audit_workflow_error"
    assert snapshot_path.read_bytes() == before
