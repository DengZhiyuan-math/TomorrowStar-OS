"""Deterministic no-inflation aggregation contracts."""

from __future__ import annotations

from pathlib import Path

from career_evidence_graph.assessment import (
    aggregate_user_skills,
    aggregation_snapshot_bytes,
    build_assessment_run,
    decide_admission,
    run_assessment,
)
from career_evidence_graph.domain.models import (
    MASTERY_ANCHORS,
    AggregationPolicy,
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
    if "demonstrated_mastery" in changes:
        score = int(changes["demonstrated_mastery"])
        anchor = next(
            item
            for item in MASTERY_ANCHORS
            if item.inclusive_range[0] <= score <= item.inclusive_range[1]
        )
        payload["mastery_anchor_fit"] = {
            "anchor_id": anchor.anchor_id,
            "anchor_range": list(anchor.inclusive_range),
            "anchor_text": anchor.capability_text,
            "anchor_basis": "The fixture establishes this exact capability band.",
            "exact_score_basis": "The fixture keeps an integer inside this anchor.",
            "next_anchor_not_established": "The next anchor is not established.",
        }
    if "contribution_id" in changes:
        payload["lineage"]["contribution_id"] = changes["contribution_id"]
        payload["source_envelope"]["contribution_id"] = changes["contribution_id"]
    return ContributionSkillAssessment.model_validate(payload)


def _run(tmp_path: Path, **changes: object):
    assessment = _assessment(tmp_path, **changes)
    return build_assessment_run(assessment, decide_admission(assessment, _policy()))


def _routine_user_truth_run(tmp_path: Path, **changes: object):
    """Build a D-05 baseline without applying a promotion-only review requirement."""
    assessment = _assessment(tmp_path, **changes)
    payload = assessment.model_dump(mode="json")
    payload["source_envelope"]["authority_label"] = "reviewed-user-truth"
    payload["origin_status"] = "audit-verified"
    payload["assessment_status"] = "partial"
    user_truth = ContributionSkillAssessment.model_validate(payload)
    return build_assessment_run(user_truth, decide_admission(user_truth, _policy()))


def test_traceable_aggregate_keeps_one_sorted_result_and_strongest_admitted_baseline(
    tmp_path: Path,
) -> None:
    lower = _run(
        tmp_path,
        id="assessment-lower-boundary",
        demonstrated_mastery=60,
        context="bounded authorization maintenance",
    )
    stronger = _run(
        tmp_path,
        id="assessment-stronger-boundary",
        demonstrated_mastery=69,
        context="independent authorization implementation",
    )

    results = aggregate_user_skills((stronger, lower))

    assert len(results) == 1
    result = results[0]
    assert result.skill_id == stronger.proposal.skill_id
    assert result.mastery == 69
    assert result.anchor_id == "anchor-55-69"
    assert result.policy_version == "policy-04-baseline-60"
    assert result.baseline_assessment_id == "assessment-stronger-boundary"
    assert result.admitted_assessment_ids == (
        "assessment-lower-boundary",
        "assessment-stronger-boundary",
    )
    assert result.promotion_decision is None
    assert result.supporting_contexts == (
        "bounded authorization maintenance",
        "independent authorization implementation",
    )


def test_no_inflation_from_duplicate_assessment_contribution_or_incidental_uses(
    tmp_path: Path,
) -> None:
    baseline = _run(tmp_path, id="assessment-baseline")
    duplicate_assessment = _run(tmp_path, id="assessment-duplicate-assessment")
    duplicate_contribution = _run(
        tmp_path,
        id="assessment-duplicate-contribution",
        context=baseline.proposal.context,
    )
    incidental_runs = tuple(
        _run(
            tmp_path,
            id=f"assessment-incidental-{index}",
            contribution_id=f"contribution-incidental-{index}",
            context=f"incidental authorization mention {index}",
            demonstrated_mastery=20,
            skill_centrality=1,
        )
        for index in range(8)
    )

    original = aggregate_user_skills((baseline,))
    expanded = aggregate_user_skills(
        (baseline, duplicate_assessment, duplicate_contribution, *incidental_runs)
    )

    assert aggregation_snapshot_bytes(expanded) == aggregation_snapshot_bytes(original)
    assert expanded[0].mastery == baseline.proposal.demonstrated_mastery
    assert expanded[0].anchor_id == "anchor-55-69"
    assert expanded[0].suppressed_duplicate_relationships


def test_same_evidence_can_support_two_skills_without_same_skill_weighting(
    tmp_path: Path,
) -> None:
    first = _run(tmp_path, id="assessment-skill-one")
    second = _run(tmp_path, id="assessment-skill-two", skill_id="skill-other-exact")

    results = aggregate_user_skills((first, second))

    assert [result.skill_id for result in results] == [
        "skill-other-exact",
        first.proposal.skill_id,
    ]
    assert all(result.mastery == 60 for result in results)
    assert all(not result.suppressed_duplicate_relationships for result in results)


def test_same_evidence_keeps_two_reviewed_user_truth_skills_independent(
    tmp_path: Path,
) -> None:
    first = _routine_user_truth_run(tmp_path, id="assessment-user-truth-skill-one")
    second = _routine_user_truth_run(
        tmp_path,
        id="assessment-user-truth-skill-two",
        skill_id="skill-other-exact",
    )

    results = aggregate_user_skills((first, second))

    assert [result.skill_id for result in results] == [
        "skill-other-exact",
        first.proposal.skill_id,
    ]
    assert all(result.authority_label == "reviewed-user-truth" for result in results)
    assert all(result.mastery == 60 for result in results)
    assert all(not result.suppressed_duplicate_relationships for result in results)
