from __future__ import annotations

import json
from pathlib import Path

import pytest

from career_evidence_graph.audit.models import AuditAction
from career_evidence_graph.audit.store import AuditStorageError, AuditStore
from career_evidence_graph.audit.workflow import start_audit, transition_audit

ROOT = Path(__file__).parents[1]
FIXTURE = ROOT / "validation/fixtures/stoa/v1/known-good.json"
MANIFEST = FIXTURE.with_name("source-manifest.json")


@pytest.mark.phase03_gap_probe
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


@pytest.mark.phase03_gap_probe
def test_snapshot_event_publication_recovers_after_interruption(tmp_path: Path) -> None:
    snapshot = start_audit(
        workspace=tmp_path,
        fixture_path=FIXTURE,
        manifest_path=MANIFEST,
        contribution_id="contrib-stoa-authorization-boundary",
        audit_id="audit-recovery",
    )
    path = AuditStore(tmp_path).path(snapshot.audit_id)
    staged = {
        name: (path / name).read_bytes().hex()
        for name in ("snapshot.json", "events.jsonl", "accepted-results.json")
    }
    (path / "snapshot.json").write_text("{}", encoding="utf-8")
    (path / "publication-journal.json").write_bytes(
        json.dumps(staged, sort_keys=True).encode("utf-8")
    )
    recovered = AuditStore(tmp_path).read(snapshot.audit_id)
    assert recovered.audit_id == snapshot.audit_id
    assert not (path / "publication-journal.json").exists()


@pytest.mark.phase03_gap_probe
def test_all_mutations_require_cas_and_competing_writer_loses(tmp_path: Path) -> None:
    store = AuditStore(tmp_path)
    snapshot = start_audit(
        workspace=tmp_path,
        fixture_path=FIXTURE,
        manifest_path=MANIFEST,
        contribution_id="contrib-stoa-authorization-boundary",
        audit_id="audit-cas",
    )
    with pytest.raises(AuditStorageError, match="required"):
        store.transact(
            snapshot.audit_id,
            AuditAction(action="answer", answer="I designed it."),
            lambda current: current,
        )
    head = store.latest_event_hash(snapshot.audit_id)
    accepted = AuditAction(
        action="answer",
        answer="I designed it.",
        action_id="cas-winner",
        expected_event_hash=head,
    )
    updated, replayed = store.transact(
        snapshot.audit_id, accepted, lambda current: transition_audit(store, current, accepted)
    )
    assert not replayed
    before_loser = (store.path(snapshot.audit_id) / "snapshot.json").read_bytes()
    stale = AuditAction(
        action="pause",
        action_id="cas-loser",
        expected_event_hash=head,
    )
    with pytest.raises(AuditStorageError, match="stale"):
        store.transact(
            snapshot.audit_id, stale, lambda current: transition_audit(store, current, stale)
        )
    assert store.read(snapshot.audit_id) == updated
    assert (store.path(snapshot.audit_id) / "snapshot.json").read_bytes() == before_loser


@pytest.mark.phase03_gap_probe
def test_review_replay_resolves_identity_before_stale_head(tmp_path: Path) -> None:
    store = AuditStore(tmp_path)
    snapshot = start_audit(
        workspace=tmp_path,
        fixture_path=FIXTURE,
        manifest_path=MANIFEST,
        contribution_id="contrib-stoa-authorization-boundary",
        audit_id="audit-review-replay",
    )
    for index, answer in enumerate(
        (
            "I designed it.",
            "I repaired it.",
            "I operated it.",
            "I owned it.",
            "No outside assistance.",
        )
    ):
        action = AuditAction(
            action="answer",
            answer=answer,
            action_id=f"answer-{index}",
            expected_event_hash=store.latest_event_hash(snapshot.audit_id),
        )
        snapshot, replayed = store.transact(
            snapshot.audit_id,
            action,
            lambda current, action=action: transition_audit(store, current, action),
        )
        assert not replayed
    review = AuditAction(
        action="review-entry",
        entry_id="entry-implementation",
        decision="confirm",
        reason="Confirmed against the audit record.",
        reviewer_id="reviewer",
        action_id="review-implementation",
        expected_event_hash=store.latest_event_hash(snapshot.audit_id),
        expected_effective_conclusion_hash=snapshot.conclusion.effective_conclusion_hash,
    )
    reviewed, replayed = store.transact(
        snapshot.audit_id, review, lambda current: transition_audit(store, current, review)
    )
    assert not replayed
    later = AuditAction(
        action="review-entry",
        entry_id="entry-debugging",
        decision="confirm",
        reason="Confirmed against the audit record.",
        reviewer_id="reviewer",
        action_id="review-debugging",
        expected_event_hash=store.latest_event_hash(snapshot.audit_id),
        expected_effective_conclusion_hash=reviewed.conclusion.effective_conclusion_hash,
    )
    store.transact(
        snapshot.audit_id, later, lambda current: transition_audit(store, current, later)
    )
    replayed_snapshot, replayed = store.transact(
        snapshot.audit_id, review, lambda current: transition_audit(store, current, review)
    )
    assert replayed
    assert replayed_snapshot == reviewed
