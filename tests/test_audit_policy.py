from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import pytest

from career_evidence_graph.audit.decision import AuditDecisionPort
from career_evidence_graph.audit.models import (
    ArtifactFact,
    AuditAction,
    AuditQuestion,
    BoundaryDecision,
    ProbeArea,
    ProbePlan,
)
from career_evidence_graph.audit.workflow import AuditWorkflowError, start_audit, transition_audit

FIXTURE = Path("validation/fixtures/stoa/v1/known-good.json")
MANIFEST = FIXTURE.parent / "source-manifest.json"


class ScriptedDecisions(AuditDecisionPort):
    def __init__(self, plan: ProbePlan) -> None:
        self.plan = plan

    def plan_probe(self, contribution_id: str, facts: tuple[ArtifactFact, ...]) -> ProbePlan:
        assert contribution_id == self.plan.contribution_id
        assert facts
        return self.plan

    def decide_boundary(self, question: AuditQuestion, answer: str) -> BoundaryDecision:
        if answer == "this was not my work":
            return BoundaryDecision(
                question_id=question.id,
                answer=answer,
                outcome="attribution-signal",
                rationale="The answer denies personal responsibility.",
            )
        if answer == "I can explain the authorization trade-off":
            return BoundaryDecision(
                question_id=question.id,
                answer=answer,
                outcome="established",
                rationale="The answer explains a concrete implementation trade-off.",
                strongest_capability="implementing explicit authorization checks",
                next_higher_not_established="independently defending the boundary under failure",
            )
        return BoundaryDecision(
            question_id=question.id,
            answer=answer,
            outcome="incomplete",
            rationale="The answer does not establish the current capability boundary.",
        )


def _plan() -> ProbePlan:
    return ProbePlan(
        contribution_id="contrib-stoa-authorization-boundary",
        areas=(
            ProbeArea(
                area_id="implementation",
                inspected_fact_ids=("evid-stoa-build-week",),
                unverified_capability=("implementation choices at the authorization boundary"),
                demanding_prompt=(
                    "Which authorization trade-off did you personally make under failure?"
                ),
                intermediate_prompt="Which authorization change did you make and verify?",
                simple_prompt="Which authorization step did you personally complete?",
                immediately_higher_capability="independently defending the boundary under failure",
            ),
        ),
    )


def _start(tmp_path):
    port = ScriptedDecisions(_plan())
    return start_audit(
        workspace=tmp_path,
        fixture_path=FIXTURE,
        manifest_path=MANIFEST,
        contribution_id="contrib-stoa-authorization-boundary",
        audit_id=f"audit-policy-{uuid4().hex[:8]}",
        decision_port=port,
    ), port


def test_first_question_uses_one_exact_fact_and_unverified_capability(tmp_path) -> None:
    snapshot, _ = _start(tmp_path)
    question = snapshot.questions[0]

    assert question.turn == "capability"
    assert question.inspection_reference in question.reason
    assert "implementation choices at the authorization boundary" in question.reason
    assert question.difficulty == "hard"


def test_nonempty_answer_is_incomplete_until_boundary_decision_establishes_it(tmp_path) -> None:
    snapshot, port = _start(tmp_path)
    snapshot = transition_audit(
        snapshot, AuditAction(action="answer", answer="I worked on it."), decision_port=port
    )

    assert snapshot.coverage[0].status == "pending"
    assert snapshot.questions[-1].difficulty == "hard"
    assert snapshot.questions[-1].follow_up_count == 1


def test_incomplete_gets_one_followup_then_descends_and_dont_know_descends(tmp_path) -> None:
    snapshot, port = _start(tmp_path)
    snapshot = transition_audit(
        snapshot, AuditAction(action="answer", answer="partial"), decision_port=port
    )
    follow_up = snapshot.questions[-1]
    snapshot = transition_audit(
        snapshot, AuditAction(action="answer", answer="still partial"), decision_port=port
    )
    assert snapshot.questions[-1].difficulty == "intermediate"
    assert snapshot.questions[-1].prompt != follow_up.prompt

    snapshot, port = _start(tmp_path)
    snapshot = transition_audit(
        snapshot, AuditAction(action="answer", answer="不知道"), decision_port=port
    )
    assert snapshot.questions[-1].difficulty == "intermediate"
    assert snapshot.questions[-1].follow_up_count == 0


def test_area_and_contribution_skip_preserve_only_verbatim_unverified_self_rating(tmp_path) -> None:
    snapshot, port = _start(tmp_path)
    snapshot = transition_audit(
        snapshot, AuditAction(action="skip", answer="self rating: 7/10"), decision_port=port
    )
    assert snapshot.coverage[0].status == "skipped"
    assert snapshot.coverage[0].self_rating == "self rating: 7/10"
    assert snapshot.status == "reviewing"

    snapshot, port = _start(tmp_path)
    snapshot = transition_audit(
        snapshot,
        AuditAction(action="skip-contribution", answer="我选择自评 6/10"),
        decision_port=port,
    )
    assert {item.status for item in snapshot.coverage} == {"skipped"}
    assert {item.self_rating for item in snapshot.coverage} == {"我选择自评 6/10"}


def test_skip_contribution_rejects_a_stale_question_target(tmp_path) -> None:
    snapshot, port = _start(tmp_path)

    with pytest.raises(AuditWorkflowError, match="target does not match"):
        transition_audit(
            snapshot,
            AuditAction(
                action="skip-contribution",
                answer="self rating: 6/10",
                question_id="question-stale",
            ),
            decision_port=port,
        )


def test_question_guard_rejects_repeated_multipart_and_leading_prompt(tmp_path) -> None:
    snapshot, _ = _start(tmp_path)
    question = snapshot.questions[0]
    from career_evidence_graph.audit import workflow

    with pytest.raises(AuditWorkflowError, match="repeats"):
        workflow._validate_new_question(question, snapshot.questions)
    with pytest.raises(AuditWorkflowError, match="focused"):
        workflow._validate_new_question(
            question.model_copy(update={"prompt": "What changed? Why did it change?"}), ()
        )
    with pytest.raises(AuditWorkflowError, match="focused"):
        workflow._validate_new_question(
            question.model_copy(update={"prompt": "Describe the authorization change."}), ()
        )
    with pytest.raises(AuditWorkflowError, match="focused"):
        workflow._validate_new_question(
            question.model_copy(update={"prompt": "List the implementation steps."}), ()
        )
    with pytest.raises(AuditWorkflowError, match="leading"):
        workflow._validate_new_question(
            question.model_copy(update={"prompt": "Clearly you owned this, isn't it?"}), ()
        )
