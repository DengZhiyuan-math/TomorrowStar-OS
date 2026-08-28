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
    review_assessment,
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


def _reviewed_user_truth_run(tmp_path: Path, **changes: object):
    """Build real reviewed authority with an immutable D-10 review version."""
    proposal = _assessment(tmp_path, **changes)
    payload = proposal.model_dump(mode="json")
    payload["source_envelope"]["authority_label"] = "reviewed-user-truth"
    payload["origin_status"] = "audit-verified"
    reviewed_candidate = ContributionSkillAssessment.model_validate(payload)
    record = build_assessment_run(
        reviewed_candidate,
        decide_admission(reviewed_candidate, _policy()),
    )
    return review_assessment(
        record,
        policy=_policy(),
        expected_effective_hash=record.effective_assessment_hash,
        reviewer_id="reviewer-a",
        review_reason="I checked attribution, anchor fit, and all judgment bases.",
        attribution_checked=True,
        anchor_fit_checked=True,
        all_judgments_checked=True,
        accepted_assessment=reviewed_candidate,
    )


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


def test_mixed_authority_promotion_cannot_elevate_reviewed_user_truth(tmp_path: Path) -> None:
    """Derived calibration support must not lend a user-truth result its missing anchor."""
    reviewed = _reviewed_user_truth_run(
        tmp_path,
        id="assessment-reviewed-baseline",
        contribution_id="contribution-reviewed-baseline",
        context="authorization module delivery",
    )
    derived = _runs(tmp_path)[1]
    decision = _decision((reviewed, derived))

    with pytest.raises(AssessmentWorkflowError, match="promotion"):
        aggregate_user_skills((reviewed, derived), promotion_decisions=(decision,))

    baseline = aggregate_user_skills((reviewed,))
    assert baseline[0].mastery == 60
    assert baseline[0].authority_label == "reviewed-user-truth"


def test_routine_unflagged_baseline_does_not_require_substantive_review(tmp_path: Path) -> None:
    """D-05 keeps an audit-verified baseline independent of a promotion review gate."""
    proposal = _assessment(tmp_path, id="assessment-routine-unflagged")
    payload = proposal.model_dump(mode="json")
    payload["source_envelope"]["authority_label"] = "reviewed-user-truth"
    payload["origin_status"] = "audit-verified"
    payload["assessment_status"] = "partial"
    routine = ContributionSkillAssessment.model_validate(payload)
    record = build_assessment_run(routine, decide_admission(routine, _policy()))

    result = aggregate_user_skills((record,))[0]

    assert record.admission.admission_status.value == "admitted"
    assert routine.substantive_review_complete is False
    assert result.mastery == 60
    assert result.authority_label == "reviewed-user-truth"


def test_reviewed_user_truth_promotion_accepts_only_retained_review_lineage(
    tmp_path: Path,
) -> None:
    first = _reviewed_user_truth_run(
        tmp_path,
        id="assessment-reviewed-complex-implementation",
        contribution_id="contribution-reviewed-complex-implementation",
        context="authorization module delivery",
    )
    second = _reviewed_user_truth_run(
        tmp_path,
        id="assessment-reviewed-decision-defense",
        contribution_id="contribution-reviewed-decision-defense",
        context="production incident follow-up",
    )

    result = aggregate_user_skills(
        (first, second), promotion_decisions=(_decision((first, second)),)
    )[0]

    assert result.mastery == 70
    assert result.authority_label == "reviewed-user-truth"
    assert all(
        record.versions[-1].effective_assessment == record.proposal for record in (first, second)
    )


def test_derived_calibration_promotion_stays_in_its_own_authority_partition(
    tmp_path: Path,
) -> None:
    runs = _runs(tmp_path)
    results = aggregate_user_skills(runs, promotion_decisions=(_decision(runs),))

    assert results[0].mastery == 70
    assert results[0].authority_label == "derived-counterfactual"


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
