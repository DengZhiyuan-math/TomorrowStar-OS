from __future__ import annotations

from pathlib import Path

import pytest

from career_evidence_graph.audit import workflow
from career_evidence_graph.audit.models import AuditAction
from career_evidence_graph.audit.store import AuditStore
from career_evidence_graph.audit.workflow import (
    AuditWorkflowError,
    inspect_contribution,
    start_audit,
    transition_audit,
)

ROOT = Path(__file__).parents[1]
FIXTURE = ROOT / "validation/fixtures/stoa/v1/known-good.json"
MANIFEST = FIXTURE.with_name("source-manifest.json")


def _start(tmp_path: Path, audit_id: str = "audit-regression"):
    return start_audit(
        workspace=tmp_path,
        fixture_path=FIXTURE,
        manifest_path=MANIFEST,
        contribution_id="contrib-stoa-authorization-boundary",
        audit_id=audit_id,
    )


def _complete(tmp_path: Path, audit_id: str = "audit-complete"):
    store = AuditStore(tmp_path)
    snapshot = _start(tmp_path, audit_id)
    for answer in (
        "I designed and verified the boundary.",
        "I isolated and repaired the failure.",
        "I operated and checked the dependency failure.",
        "I owned the decisions and acceptance.",
        "No outside assistance.",
    ):
        snapshot = transition_audit(store, snapshot, AuditAction(action="answer", answer=answer))
        store.update(snapshot)
    return store, snapshot


def test_paused_and_terminal_lifecycle_actions_fail_closed(tmp_path: Path):
    store = AuditStore(tmp_path)
    active = _start(tmp_path)
    paused = transition_audit(store, active, AuditAction(action="pause"))
    with pytest.raises(AuditWorkflowError, match="not allowed"):
        transition_audit(store, paused, AuditAction(action="answer", answer="not allowed"))
    resumed = transition_audit(store, paused, AuditAction(action="resume"))
    with pytest.raises(AuditWorkflowError, match="not allowed"):
        transition_audit(store, resumed, AuditAction(action="resume"))

    store, reviewing = _complete(tmp_path, "audit-terminal")
    assert reviewing.status == "reviewing"
    for entry in reviewing.conclusion.entries:
        reviewing = transition_audit(
            store,
            reviewing,
            AuditAction(
                action="review-entry",
                entry_id=entry.id,
                decision="confirm",
                reason="entry accepted",
                reviewer_id="reviewer",
                expected_event_hash=store.latest_event_hash(reviewing.audit_id),
                expected_effective_conclusion_hash=reviewing.conclusion.effective_conclusion_hash,
            ),
        )
        store.update(reviewing)
    completed = transition_audit(
        store,
        reviewing,
        AuditAction(
            action="review-conclusion",
            decision="confirm",
            reason="all entries accepted",
            reviewer_id="reviewer",
            expected_event_hash=store.latest_event_hash(reviewing.audit_id),
            expected_effective_conclusion_hash=reviewing.conclusion.effective_conclusion_hash,
        ),
    )
    assert completed.status == "completed"
    with pytest.raises(AuditWorkflowError, match="not allowed"):
        transition_audit(store, completed, AuditAction(action="pause"))


def test_supported_english_and_chinese_attribution_are_equivalent(tmp_path: Path):
    store = AuditStore(tmp_path)
    english = _start(tmp_path, "audit-english")
    chinese = _start(tmp_path, "audit-chinese")
    for answer in (
        "I implemented it.",
        "I debugged it.",
        "I operated it.",
        "I owned it.",
        "No outside assistance.",
    ):
        english = transition_audit(store, english, AuditAction(action="answer", answer=answer))
    for answer in ("我实现了它。", "我调试了它。", "我运行了它。", "我负责它。", "没有外部协助。"):
        chinese = transition_audit(store, chinese, AuditAction(action="answer", answer=answer))
    assert english.attribution == chinese.attribution
    assert english.attribution.ownership == "user-owned"
    assert english.attribution.assistance == "none"


def test_bilingual_attribution_is_equivalent(tmp_path: Path):
    test_supported_english_and_chinese_attribution_are_equivalent(tmp_path)


def test_conclusion_basis_separates_documentary_context(tmp_path: Path):
    store = AuditStore(tmp_path)
    snapshot = _start(tmp_path)
    for action, answer in (
        ("answer", "I designed it."),
        ("skip", "I cannot establish debugging capability."),
        ("skip", "I cannot establish operational capability."),
        ("answer", "I owned it."),
        ("answer", "No outside assistance."),
    ):
        snapshot = transition_audit(store, snapshot, AuditAction(action=action, answer=answer))
    skipped = next(entry for entry in snapshot.conclusion.entries if entry.area == "debugging")
    assert skipped.artifact_references
    assert skipped.answer_references
    assert skipped.basis == skipped.answer_references
    assert skipped.source_type == "answer-only"


def test_area_basis_separates_documentary_context(tmp_path: Path):
    test_conclusion_basis_separates_documentary_context(tmp_path)


def test_missing_claim_or_evidence_reference_fails_closed(tmp_path: Path, monkeypatch):
    fixture = workflow._fixture(FIXTURE)
    contribution = fixture.contributions[0].model_copy(
        update={"claim_ids": ("claim-does-not-exist",)}
    )
    malformed = fixture.model_copy(
        update={"contributions": (contribution, *fixture.contributions[1:])}
    )
    monkeypatch.setattr(workflow, "_fixture", lambda _: malformed)
    with pytest.raises(AuditWorkflowError, match="claim"):
        inspect_contribution(FIXTURE, MANIFEST, "contrib-stoa-authorization-boundary")


def test_missing_reference_fails_closed(tmp_path: Path, monkeypatch):
    test_missing_claim_or_evidence_reference_fails_closed(tmp_path, monkeypatch)


def test_review_actions_update_canonical_conclusion_state(tmp_path: Path):
    store, snapshot = _complete(tmp_path, "audit-canonical-review")
    proposal = snapshot.conclusion.original_proposal
    original_hash = snapshot.conclusion.original_proposal_hash
    before_hash = snapshot.conclusion.effective_conclusion_hash
    edited = transition_audit(
        store,
        snapshot,
        AuditAction(
            action="review-entry",
            entry_id="entry-implementation",
            decision="edit",
            correction="Corrected capability boundary.",
            reason="clarify scope",
            reviewer_id="reviewer",
            expected_event_hash=store.latest_event_hash(snapshot.audit_id),
            expected_effective_conclusion_hash=before_hash,
        ),
    )
    assert edited.status == "reviewing"
    assert edited.conclusion.original_proposal == proposal
    assert edited.conclusion.original_proposal_hash == original_hash
    assert edited.conclusion.effective_conclusion_hash != before_hash
    assert edited.conclusion_reviews[-1].before_effective_hash == before_hash
    assert (
        edited.conclusion_reviews[-1].after_effective_hash
        == edited.conclusion.effective_conclusion_hash
    )
    with pytest.raises(AuditWorkflowError, match="effective conclusion hash"):
        transition_audit(
            store,
            edited,
            AuditAction(
                action="review-entry",
                entry_id="entry-debugging",
                decision="confirm",
                reason="stale",
                reviewer_id="reviewer",
                expected_event_hash=store.latest_event_hash(snapshot.audit_id),
                expected_effective_conclusion_hash=before_hash,
            ),
        )
