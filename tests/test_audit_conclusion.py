from __future__ import annotations

from pathlib import Path

import pytest

from career_evidence_graph.audit.models import AuditAction
from career_evidence_graph.audit.store import AuditStore
from career_evidence_graph.audit.workflow import AuditWorkflowError, start_audit, transition_audit

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
        audit_id="audit-conclusion",
    )
    answers = {
        "implementation": "I designed and verified the boundary.",
        "debugging": "I isolated the failure and repaired it.",
        "operation": "I operated and checked the dependency failure.",
        "responsibility": "I owned the decisions and acceptance.",
        "assistance": "没有外部协助。",
    }
    for _area, answer in answers.items():
        snap = transition_audit(store, snap, AuditAction(action="answer", answer=answer))
        store.update(snap)
    return store.read("audit-conclusion")


def test_incomplete_coverage_blocks_conclusion(tmp_path: Path):
    snap = start_audit(
        workspace=tmp_path,
        fixture_path=FIXTURE,
        manifest_path=MANIFEST,
        contribution_id="contrib-stoa-authorization-boundary",
        audit_id="audit-incomplete",
    )
    with pytest.raises(ValueError, match="coverage"):
        transition_audit(
            AuditStore(tmp_path),
            snap,
            AuditAction(
                action="review-conclusion",
                decision="confirm",
                reason="确认",
                reviewer_id="reviewer",
            ),
        )
    assert snap.conclusion is None


def test_conclusion_order_and_unicode_are_stable(tmp_path: Path):
    snap = _complete(tmp_path)
    assert [entry.area for entry in snap.conclusion.entries] == [
        "implementation",
        "debugging",
        "operation",
        "responsibility",
        "assistance",
    ]
    assert all(entry.basis for entry in snap.conclusion.entries)
    assert all(entry.next_higher_not_established for entry in snap.conclusion.entries)
    assert snap.assistance_round.answer == "没有外部协助。"
    dumped = snap.model_dump(mode="json")
    assert not any(key in dumped for key in ("mastery", "confidence", "aggregation", "jd_match"))


def test_skipped_self_rating_is_opaque_unverified_text(tmp_path: Path):
    snap = start_audit(
        workspace=tmp_path,
        fixture_path=FIXTURE,
        manifest_path=MANIFEST,
        contribution_id="contrib-stoa-authorization-boundary",
        audit_id="audit-skip",
    )
    snap = transition_audit(
        AuditStore(tmp_path), snap, AuditAction(action="skip", answer="自评 7/10 — 不确定")
    )
    assert snap.coverage[0].self_rating == "自评 7/10 — 不确定"
    assert snap.conclusion is None


def test_no_numeric_assessment_dimension_in_verified_entry(tmp_path: Path):
    snap = _complete(tmp_path)
    for entry in snap.conclusion.entries:
        assert not hasattr(entry, "mastery")
        assert entry.verification == "audit-verified"


def test_duplicate_terminal_review_is_idempotent(tmp_path: Path):
    snap = _complete(tmp_path)
    store = AuditStore(tmp_path)
    action = AuditAction(
        action="review-entry",
        entry_id="entry-implementation",
        decision="confirm",
        reason="同意",
        reviewer_id="reviewer",
        expected_event_hash=store.latest_event_hash(snap.audit_id),
    )
    updated = transition_audit(store, snap, action)
    repeated = transition_audit(store, updated, action)
    assert repeated == updated


def test_entry_edits_preserve_proposal_and_require_current_effective_hash(tmp_path: Path):
    snap = _complete(tmp_path)
    store = AuditStore(tmp_path)
    original_proposal = snap.conclusion.original_proposal
    original_hash = snap.conclusion.original_proposal_hash
    before_hash = snap.conclusion.effective_conclusion_hash
    edited = transition_audit(
        store,
        snap,
        AuditAction(
            action="review-entry",
            entry_id="entry-implementation",
            decision="edit",
            correction="Corrected boundary.",
            reason="clarify the established capability",
            reviewer_id="reviewer",
            expected_event_hash=store.latest_event_hash(snap.audit_id),
            expected_effective_conclusion_hash=before_hash,
        ),
    )
    assert edited.status == "reviewing"
    assert edited.conclusion.original_proposal == original_proposal
    assert edited.conclusion.original_proposal_hash == original_hash
    assert edited.conclusion.effective_conclusion_hash != before_hash
    review = edited.conclusion_reviews[-1]
    assert review.before_effective_hash == before_hash
    assert review.after_effective_hash == edited.conclusion.effective_conclusion_hash
    with pytest.raises(AuditWorkflowError, match="effective conclusion hash"):
        transition_audit(
            store,
            edited,
            AuditAction(
                action="review-entry",
                entry_id="entry-debugging",
                decision="confirm",
                reason="stale review",
                reviewer_id="reviewer",
                expected_event_hash=store.latest_event_hash(snap.audit_id),
                expected_effective_conclusion_hash=before_hash,
            ),
        )
