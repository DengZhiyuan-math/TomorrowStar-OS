"""Paired next-anchor promotion goldens."""

from __future__ import annotations

from pathlib import Path

import pytest

from career_evidence_graph.assessment import (
    AssessmentWorkflowError,
    aggregate_user_skills,
    build_assessment_run,
    decide_admission,
    promotion_input_hash,
    run_assessment,
    validate_anchor_promotion,
)
from career_evidence_graph.domain.models import (
    AggregationPolicy,
    AnchorPromotionDecision,
    ContributionSkillAssessment,
)

ROOT = Path(__file__).parents[1]
CORPUS = ROOT / "validation/calibration/phase-04/corpus.json"
POLICIES = ROOT / "validation/calibration/phase-04/policies.json"


def _policy() -> AggregationPolicy:
    return AggregationPolicy(
        policy_version="policy-04-baseline-60",
        high_mastery_min=70,
        strict_confidence_min=60,
        activation_status="candidate",
        notice="Fixture policy; calibration activation remains unresolved.",
    )


def _assessment(tmp_path: Path, **changes: object) -> ContributionSkillAssessment:
    seed = run_assessment(
        workspace=tmp_path,
        corpus_path=CORPUS,
        policies_path=POLICIES,
        audit_id="audit-e2e",
        policy_version="policy-04-baseline-60",
    ).proposal
    payload = seed.model_dump(mode="json")
    payload.update(changes)
    if "contribution_id" in changes:
        payload["lineage"]["contribution_id"] = changes["contribution_id"]
        payload["source_envelope"]["contribution_id"] = changes["contribution_id"]
    return ContributionSkillAssessment.model_validate(payload)


def _runs(tmp_path: Path):
    first = _assessment(
        tmp_path,
        id="assessment-complex-implementation",
        contribution_id="contribution-complex-implementation",
        context="authorization module delivery",
    )
    second = _assessment(
        tmp_path,
        id="assessment-decision-defense",
        contribution_id="contribution-decision-defense",
        context="production incident follow-up",
    )
    return (
        build_assessment_run(first, decide_admission(first, _policy())),
        build_assessment_run(second, decide_admission(second, _policy())),
    )


def _decision(runs, **changes: object) -> AnchorPromotionDecision:
    assessments = tuple(run.proposal for run in runs)
    payload: dict[str, object] = {
        "decision_id": "promotion-authorization-complexity",
        "policy_version": "policy-04-baseline-60",
        "policy_input_hash": promotion_input_hash(
            assessments, policy_version="policy-04-baseline-60"
        ),
        "skill_id": assessments[0].skill_id,
        "target_anchor_id": "anchor-70-79",
        "promoted_score": 70,
        "assessment_ids": [assessment.id for assessment in assessments],
        "distinct_behaviors": [
            "independent-complex-problem",
            "decisions-explained",
            "decisions-defended",
        ],
        "behavior_assessment_ids": [
            assessments[0].id,
            assessments[1].id,
            assessments[1].id,
        ],
        "behavior_audit_bases": [
            assessments[0].judgment_basis.demonstrated_mastery_basis,
            assessments[1].judgment_basis.demonstrated_mastery_basis,
            assessments[1].judgment_basis.demonstrated_mastery_basis,
        ],
        "distinct_contexts": [assessment.context for assessment in assessments],
        "rationale": (
            "assessment-complex-implementation establishes the complex problem; "
            "assessment-decision-defense establishes explained and defended decisions."
        ),
    }
    payload.update(changes)
    return AnchorPromotionDecision.model_validate(payload)


def test_next_anchor_promotion_requires_named_distinct_credible_support(tmp_path: Path) -> None:
    runs = _runs(tmp_path)
    decision = _decision(runs)

    validated = validate_anchor_promotion(decision, tuple(run.proposal for run in runs))
    results = aggregate_user_skills(runs, promotion_decisions=(decision,))

    assert validated == decision
    assert results[0].mastery == 70
    assert results[0].anchor_id == "anchor-70-79"
    assert results[0].promotion_decision == decision
    assert results[0].baseline_assessment_id == "assessment-complex-implementation"


@pytest.mark.parametrize(
    "changes",
    (
        {"target_anchor_id": "anchor-80-89", "promoted_score": 80},
        {"distinct_behaviors": ["independent-complex-problem", "decisions-explained"]},
        {
            "distinct_contexts": [
                "authorization module delivery",
                "authorization module delivery",
            ]
        },
        {"promoted_score": 71},
    ),
)
def test_denied_promotions_leave_the_strongest_baseline_unchanged(
    tmp_path: Path, changes: dict[str, object]
) -> None:
    runs = _runs(tmp_path)
    decision = _decision(runs, **changes)

    with pytest.raises(AssessmentWorkflowError, match="promotion"):
        validate_anchor_promotion(decision, tuple(run.proposal for run in runs))

    baseline = aggregate_user_skills(runs)
    assert baseline[0].mastery == 60
    assert baseline[0].anchor_id == "anchor-55-69"
