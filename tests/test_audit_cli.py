# ruff: noqa: E501

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
        "--action-id",
        "action-start-one",
    )
    assert started.returncode == 0, started.stderr
    first = json.loads(started.stdout)
    assert first["question"]["reason"]
    assert first["question"]["prompt"]
    audit_id = first["audit_id"]
    head = first["event_hash"]

    answered = run_cli(
        "audit",
        "answer",
        "--workspace",
        str(workspace),
        "--audit-id",
        audit_id,
        "--answer",
        "I chose and verified the boundary.",
        "--action-id",
        "action-answer-one",
        "--expected-event-hash",
        head,
    )
    assert answered.returncode == 0, answered.stderr
    answer_head = json.loads(answered.stdout)["event_hash"]
    paused = run_cli(
        "audit",
        "pause",
        "--workspace",
        str(workspace),
        "--audit-id",
        audit_id,
        "--action-id",
        "action-pause-one",
        "--expected-event-hash",
        answer_head,
    )
    assert paused.returncode == 0, paused.stderr
    pause_head = json.loads(paused.stdout)["event_hash"]
    resumed = run_cli(
        "audit",
        "resume",
        "--workspace",
        str(workspace),
        "--audit-id",
        audit_id,
        "--action-id",
        "action-resume-one",
        "--expected-event-hash",
        pause_head,
    )
    assert resumed.returncode == 0, resumed.stderr
    assert json.loads(resumed.stdout)["snapshot"]["audit_id"] == audit_id


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
        "--action-id",
        "action-start-invalid",
    )
    audit_id = json.loads(started.stdout)["audit_id"]
    snapshot_path = workspace / "audits" / audit_id / "snapshot.json"
    before = snapshot_path.read_bytes()
    rejected = run_cli(
        "audit",
        "resume",
        "--workspace",
        str(workspace),
        "--audit-id",
        audit_id,
        "--action-id",
        "action-resume-invalid",
        "--expected-event-hash",
        json.loads(started.stdout)["event_hash"],
    )
    assert rejected.returncode == 2
    assert json.loads(rejected.stderr)["error"] == "audit_workflow_error"
    assert "Traceback" not in rejected.stderr
    assert snapshot_path.read_bytes() == before


def test_exact_action_replay_is_byte_identical_and_stale_new_action_fails(tmp_path: Path) -> None:
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
        "--action-id",
        "action-start-replay",
    )
    first = json.loads(started.stdout)
    command = (
        "audit",
        "answer",
        "--workspace",
        str(workspace),
        "--audit-id",
        first["audit_id"],
        "--answer",
        "I chose and verified the boundary.",
        "--action-id",
        "action-answer-replay",
        "--expected-event-hash",
        first["event_hash"],
    )
    accepted = run_cli(*command)
    snapshot_path = workspace / "audits" / first["audit_id"] / "snapshot.json"
    after_accept = snapshot_path.read_bytes()
    replayed = run_cli(*command)
    assert accepted.returncode == replayed.returncode == 0
    assert accepted.stdout == replayed.stdout
    assert snapshot_path.read_bytes() == after_accept
    stale = run_cli(
        "audit",
        "pause",
        "--workspace",
        str(workspace),
        "--audit-id",
        first["audit_id"],
        "--action-id",
        "action-pause-stale",
        "--expected-event-hash",
        first["event_hash"],
    )
    assert stale.returncode == 2
    assert "stale expected event hash" in stale.stderr
