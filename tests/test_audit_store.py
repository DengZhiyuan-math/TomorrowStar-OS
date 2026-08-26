from __future__ import annotations

from pathlib import Path

import pytest

from career_evidence_graph.audit.models import AuditAction
from career_evidence_graph.audit.store import AuditStorageError, AuditStore
from career_evidence_graph.audit.workflow import start_audit, transition_audit

ROOT = Path(__file__).parents[1]
FIXTURE = ROOT / "validation/fixtures/stoa/v1/known-good.json"
MANIFEST = FIXTURE.with_name("source-manifest.json")


def _complete(tmp_path: Path):
    store = AuditStore(tmp_path)
    snap = start_audit(
        workspace=tmp_path,
        fixture_path=FIXTURE,
        manifest_path=MANIFEST,
        contribution_id="contrib-stoa-authorization-boundary",
        audit_id="audit-store",
    )
    for index, answer in enumerate(
        (
            "I designed it.",
            "I repaired it.",
            "I operated it.",
            "I owned it.",
            "没有外部协助",
        )
    ):
        action = AuditAction(
            action="answer",
            answer=answer,
            action_id=f"store-answer-{index}",
            expected_event_hash=store.latest_event_hash(snap.audit_id),
        )
        snap, replayed = store.transact(
            snap.audit_id,
            action,
            lambda current, action=action: transition_audit(store, current, action),
        )
        assert not replayed
    return store, store.read("audit-store")


def test_review_appends_immutable_lineage_and_preserves_original_bytes(tmp_path: Path):
    store, snap = _complete(tmp_path)
    original = (store.path(snap.audit_id) / "snapshot.json").read_bytes()
    expected = store.latest_event_hash(snap.audit_id)
    action = AuditAction(
        action="review-entry",
        entry_id="entry-implementation",
        decision="edit",
        correction="更正：由我完成。",
        reason="责任边界需要修正。",
        reviewer_id="审查者",
        action_id="store-review-implementation",
        expected_event_hash=expected,
        expected_effective_conclusion_hash=snap.conclusion.effective_conclusion_hash,
    )
    reviewed, replayed = store.transact(
        snap.audit_id, action, lambda current: transition_audit(store, current, action)
    )
    assert not replayed
    assert (store.path(snap.audit_id) / "snapshot.json").read_bytes() != original
    reread = store.read(snap.audit_id)
    assert reread.conclusion_reviews[0].reviewer_id == "审查者"
    assert reread.conclusion_reviews[0].correction == "更正：由我完成。"


@pytest.mark.phase03_original_probe
def test_stale_or_tampered_review_fails_closed(tmp_path: Path):
    store, snap = _complete(tmp_path)
    action = AuditAction(
        action="review-conclusion",
        decision="confirm",
        reason="确认",
        reviewer_id="r",
        expected_event_hash="sha256:" + "0" * 64,
        expected_effective_conclusion_hash=snap.conclusion.effective_conclusion_hash,
    )
    with pytest.raises(ValueError, match="whole confirmation"):
        transition_audit(store, snap, action)
    events = store.path(snap.audit_id) / "events.jsonl"
    events.write_text(events.read_text(encoding="utf-8") + "{bad}\n", encoding="utf-8")
    with pytest.raises(AuditStorageError, match="corrupt"):
        store.read(snap.audit_id)


def test_symlinked_workspace_fails_closed(tmp_path: Path):
    store, _ = _complete(tmp_path)
    link = tmp_path / "alias"
    link.symlink_to(tmp_path, target_is_directory=True)
    with pytest.raises(AuditStorageError):
        AuditStore(link).read("audit-store")


def test_stale_effective_review_hash_preserves_review_and_conclusion_bytes(tmp_path: Path):
    store, snap = _complete(tmp_path)
    audit_path = store.path(snap.audit_id)
    custody_names = ("snapshot.json", "events.jsonl", "accepted-results.json")
    before = {name: (audit_path / name).read_bytes() for name in custody_names}
    action = AuditAction(
        action="review-entry",
        entry_id="entry-implementation",
        decision="confirm",
        reason="review stale projection",
        reviewer_id="reviewer",
        expected_event_hash=store.latest_event_hash(snap.audit_id),
        expected_effective_conclusion_hash="sha256:" + "0" * 64,
    )
    with pytest.raises(ValueError, match="stale expected effective conclusion hash"):
        transition_audit(store, snap, action)
    assert before == {name: (audit_path / name).read_bytes() for name in custody_names}
