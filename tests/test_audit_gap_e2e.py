from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parents[1]
LAUNCHER = ROOT / "scripts" / "run_career_evidence.py"
FIXTURE = ROOT / "validation/fixtures/stoa/v1/known-good.json"
MANIFEST = FIXTURE.with_name("source-manifest.json")


def _run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(LAUNCHER), *args],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )


def _json(result: subprocess.CompletedProcess[str]) -> dict[str, object]:
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def _mutate(
    workspace: Path, audit_id: str, action: str, action_id: str, head: str, *extra: str
) -> dict[str, object]:
    return _json(
        _run(
            "audit",
            action,
            "--workspace",
            str(workspace),
            "--audit-id",
            audit_id,
            "--action-id",
            action_id,
            "--expected-event-hash",
            head,
            *extra,
        )
    )


def _contains_key(value: object, key: str) -> bool:
    if isinstance(value, dict):
        return key in value or any(_contains_key(item, key) for item in value.values())
    if isinstance(value, list):
        return any(_contains_key(item, key) for item in value)
    return False


def test_repaired_audit_cli_journey_preserves_custody_and_reopens(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    inspection = _json(
        _run(
            "audit",
            "inspect",
            "--fixture",
            str(FIXTURE),
            "--manifest",
            str(MANIFEST),
            "--contribution-id",
            "contrib-stoa-authorization-boundary",
        )
    )
    assert inspection["facts"] and inspection["limitations"]

    started = _json(
        _run(
            "audit",
            "start",
            "--workspace",
            str(workspace),
            "--fixture",
            str(FIXTURE),
            "--contribution-id",
            "contrib-stoa-authorization-boundary",
            "--audit-id",
            "audit-e2e",
            "--action-id",
            "start-e2e",
        )
    )
    audit_id = str(started["audit_id"])
    head = str(started["event_hash"])
    audit_path = workspace / "audits" / audit_id

    first = _mutate(
        workspace,
        audit_id,
        "answer",
        "answer-implementation",
        head,
        "--answer",
        "I designed and verified the authorization boundary.",
    )
    head = str(first["event_hash"])
    paused = _mutate(workspace, audit_id, "pause", "pause-e2e", head)
    head = str(paused["event_hash"])
    custody_names = ("snapshot.json", "events.jsonl", "accepted-results.json")
    before_invalid = {name: (audit_path / name).read_bytes() for name in custody_names}
    invalid = _run(
        "audit",
        "answer",
        "--workspace",
        str(workspace),
        "--audit-id",
        audit_id,
        "--action-id",
        "answer-while-paused",
        "--expected-event-hash",
        head,
        "--answer",
        "This must not be accepted.",
    )
    assert invalid.returncode == 2
    assert json.loads(invalid.stderr)["error"] == "audit_workflow_error"
    assert "Traceback" not in invalid.stderr
    assert before_invalid == {name: (audit_path / name).read_bytes() for name in before_invalid}
    resumed = _mutate(workspace, audit_id, "resume", "resume-e2e", head)
    head = str(resumed["event_hash"])

    for action_id, answer in (
        ("answer-debugging", "I isolated and repaired the dependency failure."),
        ("answer-operation", "I operated and checked the recovery path."),
        ("answer-responsibility", "I owned the implementation decisions and acceptance."),
        ("answer-assistance", "编码代理协助了实现。"),
    ):
        accepted = _mutate(workspace, audit_id, "answer", action_id, head, "--answer", answer)
        head = str(accepted["event_hash"])

    reviewing = accepted["snapshot"]
    assert reviewing["status"] == "reviewing"
    assert reviewing["attribution"] == {
        "assistance": "coding-agent-assisted",
        "model": None,
        "ownership": "user-owned",
        "schema_version": "audit-attribution/v1",
        "tool": None,
    }
    conclusion = reviewing["conclusion"]
    original_proposal = conclusion["original_proposal"]
    original_hash = conclusion["original_proposal_hash"]
    effective_hash = conclusion["effective_conclusion_hash"]

    edited = _mutate(
        workspace,
        audit_id,
        "review-entry",
        "edit-implementation",
        head,
        "--entry-id",
        "entry-implementation",
        "--decision",
        "edit",
        "--correction",
        "Clarified independently owned boundary decision.",
        "--reason",
        "Make the capability boundary precise.",
        "--reviewer",
        "reviewer-e2e",
        "--expected-effective-conclusion-hash",
        effective_hash,
    )
    head = str(edited["event_hash"])
    edited_conclusion = edited["snapshot"]["conclusion"]
    assert edited_conclusion["original_proposal"] == original_proposal
    assert edited_conclusion["original_proposal_hash"] == original_hash
    assert edited_conclusion["effective_conclusion_hash"] != effective_hash

    before_stale = {name: (audit_path / name).read_bytes() for name in custody_names}
    stale = _run(
        "audit",
        "review-entry",
        "--workspace",
        str(workspace),
        "--audit-id",
        audit_id,
        "--action-id",
        "stale-entry-review",
        "--expected-event-hash",
        head,
        "--entry-id",
        "entry-debugging",
        "--decision",
        "confirm",
        "--reason",
        "This stale request must not write.",
        "--reviewer",
        "reviewer-e2e",
        "--expected-effective-conclusion-hash",
        effective_hash,
    )
    assert stale.returncode == 2
    assert json.loads(stale.stderr)["error"] == "audit_workflow_error"
    assert "Traceback" not in stale.stderr
    assert before_stale == {name: (audit_path / name).read_bytes() for name in before_stale}

    current_effective = str(edited_conclusion["effective_conclusion_hash"])
    for entry_id in (
        "entry-debugging",
        "entry-operation",
        "entry-responsibility",
        "entry-assistance",
    ):
        confirmed = _mutate(
            workspace,
            audit_id,
            "review-entry",
            f"confirm-{entry_id}",
            head,
            "--entry-id",
            entry_id,
            "--decision",
            "confirm",
            "--reason",
            "Confirmed against the answered audit record.",
            "--reviewer",
            "reviewer-e2e",
            "--expected-effective-conclusion-hash",
            current_effective,
        )
        head = str(confirmed["event_hash"])
        current_effective = str(confirmed["snapshot"]["conclusion"]["effective_conclusion_hash"])

    completed = _mutate(
        workspace,
        audit_id,
        "review-conclusion",
        "confirm-whole-conclusion",
        head,
        "--decision",
        "confirm",
        "--reason",
        "All capability boundaries have been reviewed.",
        "--reviewer",
        "reviewer-e2e",
        "--expected-effective-conclusion-hash",
        current_effective,
    )
    assert completed["snapshot"]["status"] == "completed"

    replay = _mutate(
        workspace,
        audit_id,
        "review-conclusion",
        "confirm-whole-conclusion",
        head,
        "--decision",
        "confirm",
        "--reason",
        "All capability boundaries have been reviewed.",
        "--reviewer",
        "reviewer-e2e",
        "--expected-effective-conclusion-hash",
        current_effective,
    )
    assert replay == completed

    reopened = _json(
        _run(
            "audit",
            "review-conclusion",
            "--workspace",
            str(workspace),
            "--audit-id",
            audit_id,
            "--action-id",
            "confirm-whole-conclusion",
            "--expected-event-hash",
            head,
            "--decision",
            "confirm",
            "--reason",
            "All capability boundaries have been reviewed.",
            "--reviewer",
            "reviewer-e2e",
            "--expected-effective-conclusion-hash",
            current_effective,
        )
    )
    assert reopened == completed
    persisted = json.loads((audit_path / "snapshot.json").read_text(encoding="utf-8"))
    for deferred in ("mastery", "confidence", "aggregation", "jd", "provider", "database"):
        assert not _contains_key(persisted, deferred)

    competing = _json(
        _run(
            "audit",
            "start",
            "--workspace",
            str(workspace),
            "--fixture",
            str(FIXTURE),
            "--contribution-id",
            "contrib-stoa-authorization-boundary",
            "--audit-id",
            "audit-e2e-cas",
            "--action-id",
            "start-e2e-cas",
        )
    )
    competing_head = str(competing["event_hash"])
    accepted_competing = _mutate(
        workspace,
        "audit-e2e-cas",
        "answer",
        "accepted-cas-answer",
        competing_head,
        "--answer",
        "I made the first accepted change.",
    )
    competing_path = workspace / "audits" / "audit-e2e-cas"
    before_loser = {name: (competing_path / name).read_bytes() for name in custody_names}
    loser = _run(
        "audit",
        "pause",
        "--workspace",
        str(workspace),
        "--audit-id",
        "audit-e2e-cas",
        "--action-id",
        "stale-competing-action",
        "--expected-event-hash",
        competing_head,
    )
    assert loser.returncode == 2
    assert "stale expected event hash" in loser.stderr
    assert before_loser == {name: (competing_path / name).read_bytes() for name in custody_names}
    assert accepted_competing["snapshot"]["status"] == "active"

    tampered = _json(
        _run(
            "audit",
            "start",
            "--workspace",
            str(workspace),
            "--fixture",
            str(FIXTURE),
            "--contribution-id",
            "contrib-stoa-authorization-boundary",
            "--audit-id",
            "audit-e2e-tamper",
            "--action-id",
            "start-e2e-tamper",
        )
    )
    tampered_path = workspace / "audits" / "audit-e2e-tamper"
    (tampered_path / "events.jsonl").write_text("", encoding="utf-8")
    tamper_read = _run(
        "audit",
        "pause",
        "--workspace",
        str(workspace),
        "--audit-id",
        "audit-e2e-tamper",
        "--action-id",
        "tampered-pause",
        "--expected-event-hash",
        str(tampered["event_hash"]),
    )
    assert tamper_read.returncode == 2
    assert "audit event chain is empty" in tamper_read.stderr
    assert "Traceback" not in tamper_read.stderr

    interrupted = _json(
        _run(
            "audit",
            "start",
            "--workspace",
            str(workspace),
            "--fixture",
            str(FIXTURE),
            "--contribution-id",
            "contrib-stoa-authorization-boundary",
            "--audit-id",
            "audit-e2e-recovery",
            "--action-id",
            "start-e2e-recovery",
        )
    )
    recovery_path = workspace / "audits" / "audit-e2e-recovery"
    staged = {name: (recovery_path / name).read_bytes().hex() for name in custody_names}
    (recovery_path / "snapshot.json").write_text("{}", encoding="utf-8")
    (recovery_path / "publication-journal.json").write_text(
        json.dumps(staged, sort_keys=True), encoding="utf-8"
    )
    recovered = _mutate(
        workspace,
        "audit-e2e-recovery",
        "pause",
        "recovered-pause",
        str(interrupted["event_hash"]),
    )
    assert recovered["snapshot"]["status"] == "paused"
    assert not (recovery_path / "publication-journal.json").exists()
