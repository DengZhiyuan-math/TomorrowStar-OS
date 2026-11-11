from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from career_evidence_graph.audit.decision import (
    FakeDecisionPort,
    RecordedDecisionPort,
    validate_boundary_decision,
    validate_probe_plan,
)
from career_evidence_graph.audit.models import (
    ArtifactFact,
    AuditQuestion,
    BoundaryDecision,
    ProbeArea,
    ProbePlan,
)

FACT = ArtifactFact(
    evidence_id="evidence-stoa-01",
    source_locator="README.md#authorization",
    statement="The contribution added an authorization boundary for student records.",
)


def _area() -> ProbeArea:
    return ProbeArea(
        area_id="implementation",
        inspected_fact_ids=(FACT.evidence_id,),
        unverified_capability="implementation choices at an authorization boundary",
        demanding_prompt="Explain the design trade-off you made at the authorization boundary.",
        intermediate_prompt=(
            "Which authorization change did you implement and how did you check it?"
        ),
        simple_prompt="Which authorization step did you personally complete?",
        immediately_higher_capability="independently defending the boundary under failure",
    )


def _plan() -> ProbePlan:
    return ProbePlan(
        contribution_id="contrib-stoa-authorization-boundary",
        areas=(_area(),),
    )


def _question() -> AuditQuestion:
    return AuditQuestion(
        id="question-implementation-hard-0",
        reason=(
            "README.md#authorization records an authorization boundary; "
            "implementation choices remain unverified."
        ),
        prompt=_area().demanding_prompt,
        area="implementation",
        area_id="implementation",
        inspection_reference=FACT.source_locator,
    )


def test_probe_plan_requires_fact_bound_relevant_capability_ladder() -> None:
    plan = validate_probe_plan(_plan(), (FACT,))

    assert plan.areas[0].inspected_fact_ids == (FACT.evidence_id,)
    assert plan.areas[0].demanding_prompt != plan.areas[0].simple_prompt


@pytest.mark.parametrize("area_id", ["responsibility", "assistance"])
def test_probe_plan_rejects_attribution_identifiers_as_capability_areas(area_id: str) -> None:
    with pytest.raises(ValidationError, match="Input should be"):
        ProbeArea(**(_area().model_dump() | {"area_id": area_id}))


def test_probe_plan_rejects_uncited_or_extra_area_facts() -> None:
    with pytest.raises(ValueError, match="unknown inspected fact"):
        validate_probe_plan(
            ProbePlan(
                contribution_id="contrib-stoa-authorization-boundary",
                areas=(
                    ProbeArea(
                        **(_area().model_dump() | {"inspected_fact_ids": ("evidence-other",)})
                    ),
                ),
            ),
            (FACT,),
        )
    with pytest.raises(ValidationError):
        ProbePlan(
            contribution_id="contrib-stoa-authorization-boundary",
            areas=(_area(),),
            unexpected="injected",  # type: ignore[call-arg]
        )


def test_boundary_decision_binds_exact_question_and_answer_before_establishing() -> None:
    question = _question()
    answer = "I chose explicit checks and tested the denied path."
    decision = BoundaryDecision(
        question_id=question.id,
        answer=answer,
        outcome="established",
        rationale="The answer describes a concrete choice and denied-path test.",
        strongest_capability="implementing explicit authorization checks",
        next_higher_not_established="independently defending the boundary under failure",
    )

    assert (
        validate_boundary_decision(decision, question=question, answer=answer, area=_area())
        == decision
    )

    with pytest.raises(ValueError, match="answer does not match"):
        validate_boundary_decision(
            decision,
            question=question,
            answer="arbitrary non-empty text",
            area=_area(),
        )


@pytest.mark.parametrize("outcome", ["incomplete", "attribution-signal"])
def test_non_established_decisions_cannot_smuggle_a_capability_boundary(outcome: str) -> None:
    with pytest.raises(ValidationError, match="only established"):
        BoundaryDecision(
            question_id=_question().id,
            answer="not me",
            outcome=outcome,
            rationale="The answer does not establish a capability boundary.",
            strongest_capability="injected claim",
            next_higher_not_established="injected boundary",
        )


def test_recorded_and_fake_ports_are_deterministic_and_live_is_opt_in() -> None:
    plan = _plan()
    question = _question()
    answer = "I did not make this part."
    signal = BoundaryDecision(
        question_id=question.id,
        answer=answer,
        outcome="attribution-signal",
        rationale="The answer denies personal responsibility.",
    )
    recorded = RecordedDecisionPort(plan=plan, decisions={(question.id, answer): signal})

    assert recorded.plan_probe("contrib-stoa-authorization-boundary", (FACT,)) == plan
    assert recorded.decide_boundary(question, answer) == signal
    assert FakeDecisionPort().decide_boundary(question, answer).outcome == "attribution-signal"


def test_checked_in_schemas_exist_and_are_json_objects() -> None:
    for name in ("audit-probe-plan.schema.json", "audit-boundary-decision.schema.json"):
        schema = json.loads((Path("validation/schemas") / name).read_text(encoding="utf-8"))
        assert schema["type"] == "object"
        assert schema["additionalProperties"] is False
