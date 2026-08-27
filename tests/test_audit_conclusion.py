from __future__ import annotations

from pathlib import Path

import pytest

from career_evidence_graph.audit.decision import RecordedDecisionPort
from career_evidence_graph.audit.models import AuditAction, BoundaryDecision, ProbeArea, ProbePlan
from career_evidence_graph.audit.workflow import AuditWorkflowError, start_audit, transition_audit

ROOT = Path(__file__).parents[1]
FIXTURE = ROOT / "validation/fixtures/stoa/v1/known-good.json"
MANIFEST = FIXTURE.with_name("source-manifest.json")


def _port() -> RecordedDecisionPort:
    area = ProbeArea(
        area_id="implementation",
        inspected_fact_ids=("evid-stoa-backend-audit",),
        unverified_capability="authorization-boundary implementation",
        demanding_prompt="How did you defend the authorization boundary under failure?",
        intermediate_prompt="Which authorization boundary did you implement and check?",
        simple_prompt="Which authorization implementation step did you complete?",
        immediately_higher_capability="independently defending authorization failures",
    )
    plan = ProbePlan(contribution_id="contrib-stoa-authorization-boundary", areas=(area,))
    return RecordedDecisionPort(plan=plan, decisions={})


def _started(tmp_path: Path, audit_id: str = "audit-conclusion"):
    return start_audit(
        workspace=tmp_path,
        fixture_path=FIXTURE,
        manifest_path=MANIFEST,
        contribution_id="contrib-stoa-authorization-boundary",
        audit_id=audit_id,
        decision_port=_port(),
    )


def _established(tmp_path: Path):
    snapshot = _started(tmp_path)
    question = snapshot.questions[-1]
    answer = "I chose the authorization boundary and verified its failure behavior."
    port = _port()
    port._decisions[(question.id, answer)] = BoundaryDecision(
        question_id=question.id,
        answer=answer,
        outcome="established",
        rationale="Recorded fixture establishes the capability boundary.",
        strongest_capability="implementing and verifying the authorization boundary",
        next_higher_not_established="independently defending authorization failures",
    )
    snapshot = transition_audit(
        snapshot, AuditAction(action="answer", answer=answer), decision_port=port
    )
    snapshot = transition_audit(
        snapshot,
        AuditAction(action="answer", answer="I owned the design decisions and final acceptance."),
    )
    return transition_audit(
        snapshot,
        AuditAction(action="answer", answer="No outside assistance."),
    )


def test_verified_entry_requires_terminal_boundary_and_both_attribution_turns(tmp_path: Path):
    snapshot = _started(tmp_path)
    question = snapshot.questions[-1]
    answer = "I chose the authorization boundary and verified its failure behavior."
    port = _port()
    port._decisions[(question.id, answer)] = BoundaryDecision(
        question_id=question.id,
        answer=answer,
        outcome="established",
        rationale="Recorded fixture establishes the capability boundary.",
        strongest_capability="implementing and verifying the authorization boundary",
        next_higher_not_established="independently defending authorization failures",
    )
    ownership = transition_audit(
        snapshot, AuditAction(action="answer", answer=answer), decision_port=port
    )
    assert ownership.questions[-1].turn == "ownership"
    assistance = transition_audit(
        ownership,
        AuditAction(action="answer", answer="I owned the design decisions and final acceptance."),
    )
    assert assistance.questions[-1].turn == "assistance"
    assert assistance.conclusion is None

    completed = transition_audit(
        assistance, AuditAction(action="answer", answer="No outside assistance.")
    )
    entry = completed.conclusion.entries[0]
    assert completed.status == "reviewing"
    assert entry.area == "implementation"
    assert entry.verification == "audit-verified"
    assert entry.artifact_references and entry.answer_references
    assert entry.responsibility_boundary.startswith("user-owned:")
    assert entry.assistance_boundary.startswith("none:")


def test_reviews_preserve_immutable_proposal_and_append_ordered_lineage(tmp_path: Path):
    snapshot = _established(tmp_path)
    original = snapshot.conclusion.original_proposal
    original_hash = snapshot.conclusion.original_proposal_hash
    initial_effective_hash = snapshot.conclusion.effective_conclusion_hash

    edited = transition_audit(
        snapshot,
        AuditAction(
            action="review-entry",
            entry_id="entry-implementation",
            decision="edit",
            correction="Clarified independently owned boundary decision.",
            reason="Make the boundary precise.",
            reviewer_id="reviewer",
        ),
    )
    assert edited.conclusion.original_proposal == original
    assert edited.conclusion.original_proposal_hash == original_hash
    assert edited.conclusion.effective_conclusion_hash != initial_effective_hash
    assert edited.conclusion_reviews[-1].sequence == 1
    assert edited.conclusion_reviews[-1].before_effective_hash == initial_effective_hash

    rejected = transition_audit(
        edited,
        AuditAction(
            action="review-conclusion",
            decision="reject",
            reason="Need a new interview before accepting this conclusion.",
            reviewer_id="reviewer",
        ),
    )
    assert rejected.status == "rejected"
    assert rejected.conclusion.original_proposal == original
    assert [review.sequence for review in rejected.conclusion_reviews] == [1, 2]
    assert rejected.conclusion_reviews[-1].target == "whole-conclusion"


def test_whole_contribution_skip_is_verbatim_self_assessed_and_unverified(tmp_path: Path):
    snapshot = _started(tmp_path, "audit-whole-skip")
    rating = "自评 7/10 — 我不想进行访谈"
    skipped = transition_audit(snapshot, AuditAction(action="skip-contribution", answer=rating))
    entry = skipped.conclusion.entries[0]
    assert skipped.status == "reviewing"
    assert entry.verification == "self-assessed-unverified"
    assert entry.self_rating == rating
    assert entry.strongest_capability is None
    assert entry.next_higher_not_established is None
    assert entry.responsibility_boundary.startswith("unresolved")
    assert entry.assistance_boundary.startswith("unresolved")
    dumped = skipped.model_dump(mode="json")
    assert "mastery" not in dumped and "confidence" not in dumped and "jd_match" not in dumped


def test_review_action_is_unavailable_before_a_conclusion_exists(tmp_path: Path):
    snapshot = _started(tmp_path)
    with pytest.raises(AuditWorkflowError, match="not allowed"):
        transition_audit(
            snapshot,
            AuditAction(
                action="review-conclusion",
                decision="confirm",
                reason="too early",
                reviewer_id="reviewer",
            ),
        )
