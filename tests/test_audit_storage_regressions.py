from __future__ import annotations

from pathlib import Path

import pytest

from career_evidence_graph.audit.store import AuditStorageError, AuditStore
from career_evidence_graph.audit.models import AuditAction
from career_evidence_graph.audit.workflow import transition_audit
from career_evidence_graph.audit.workflow import start_audit

ROOT = Path(__file__).parents[1]
FIXTURE = ROOT / "validation/fixtures/stoa/v1/known-good.json"
MANIFEST = FIXTURE.with_name("source-manifest.json")


def test_complete_event_chain_rejects_historical_tampering(tmp_path: Path) -> None:
    snapshot = start_audit(
        workspace=tmp_path,
        fixture_path=FIXTURE,
        manifest_path=MANIFEST,
        contribution_id="contrib-stoa-authorization-boundary",
        audit_id="audit-tamper",
    )
    events = AuditStore(tmp_path).path(snapshot.audit_id) / "events.jsonl"
    events.write_text("", encoding="utf-8")
    with pytest.raises(AuditStorageError):
        AuditStore(tmp_path).read(snapshot.audit_id)


def test_complete_event_chain_rejects_deleted_earlier_record(tmp_path: Path) -> None:
    store = AuditStore(tmp_path)
    snapshot = start_audit(
        workspace=tmp_path,
        fixture_path=FIXTURE,
        manifest_path=MANIFEST,
        contribution_id="contrib-stoa-authorization-boundary",
        audit_id="audit-delete-first",
    )
    head = store.latest_event_hash(snapshot.audit_id)
    action = AuditAction(
        action="answer",
        answer="I designed it.",
        action_id="action-answer-one",
        expected_event_hash=head,
    )
    store.transact(
        snapshot.audit_id, action, lambda current: transition_audit(store, current, action)
    )
    events = store.path(snapshot.audit_id) / "events.jsonl"
    events.write_bytes(b"\n".join(events.read_bytes().splitlines()[1:]) + b"\n")
    with pytest.raises(AuditStorageError, match="corrupt"):
        store.latest_event_hash(snapshot.audit_id)


def test_event_and_result_tampering_fail_closed(tmp_path: Path) -> None:
    snapshot = start_audit(
        workspace=tmp_path,
        fixture_path=FIXTURE,
        manifest_path=MANIFEST,
        contribution_id="contrib-stoa-authorization-boundary",
        audit_id="audit-result-tamper",
    )
    result = AuditStore(tmp_path).path(snapshot.audit_id) / "accepted-results.json"
    result.write_text("[]\n", encoding="utf-8")
    with pytest.raises(AuditStorageError, match="incomplete"):
        AuditStore(tmp_path).read(snapshot.audit_id)
