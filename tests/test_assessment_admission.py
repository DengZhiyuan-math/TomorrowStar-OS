"""Fail-closed admission contracts for contribution-Skill proposals."""

from __future__ import annotations

from pathlib import Path

import pytest

from career_evidence_graph.assessment import (
    AssessmentWorkflowError,
    aggregate_skill,
    decide_admission,
    run_assessment,
)
from career_evidence_graph.domain.models import (
    AggregationPolicy,
    AssessmentAdmissionStatus,
    ContributionSkillAssessment,
)

ROOT = Path(__file__).parents[1]
CORPUS = ROOT / "validation/calibration/phase-04/corpus.json"
POLICIES = ROOT / "validation/calibration/phase-04/policies.json"


def _proposal(tmp_path: Path, **changes: object) -> ContributionSkillAssessment:
    """Build a valid sealed tracer proposal, then validate a complete replacement."""
    record = run_assessment(
        workspace=tmp_path,
        corpus_path=CORPUS,
        policies_path=POLICIES,
        audit_id="audit-e2e",
        policy_version="policy-04-baseline-60",
    )
    payload = record.proposal.model_dump(mode="json")
    payload.update(changes)
    return ContributionSkillAssessment.model_validate(payload)


def _policy(version: str, confidence: int) -> AggregationPolicy:
    return AggregationPolicy(
        policy_version=version,
        high_mastery_min=70,
        strict_confidence_min=confidence,
        activation_status="candidate",
        notice="Fixture policy; calibration activation remains unresolved.",
    )


@pytest.mark.parametrize(
    ("policy", "mastery", "confidence", "expected"),
    (
        ("policy-04-baseline-60", 69, 59, "admitted"),
        ("policy-04-baseline-60", 70, 59, "pending-confirmation"),
        ("policy-04-baseline-60", 70, 60, "admitted"),
        ("policy-04-conservative-70", 70, 69, "pending-confirmation"),
        ("policy-04-conservative-70", 70, 70, "admitted"),
    ),
)
def test_admission_boundaries_are_integer_exact_and_never_mutate_judgments(
    tmp_path: Path, policy: str, mastery: int, confidence: int, expected: str
) -> None:
    proposal = _proposal(
        tmp_path,
        demonstrated_mastery=mastery,
        evidence_confidence=confidence,
        mastery_anchor_fit={
            "anchor_id": "anchor-60-79",
            "anchor_range": [60, 79],
            "observable_capability": "Validated capability band fixture.",
        },
    )

    admission = decide_admission(proposal, _policy(policy, 60 if policy.endswith("60") else 70))

    assert admission.admission_status == expected
    assert (proposal.demonstrated_mastery, proposal.skill_centrality, proposal.evidence_confidence) == (
        mastery,
        55,
        confidence,
    )
    if expected != "admitted":
        with pytest.raises(AssessmentWorkflowError, match="only admitted"):
            aggregate_skill(proposal, admission)


@pytest.mark.parametrize(
    ("origin_status", "attribution_status", "assistance_status"),
    (
        ("self-assessed-unverified", "resolved", "resolved"),
        ("audit-verified", "unresolved", "resolved"),
        ("audit-verified", "resolved", "unresolved"),
    ),
)
def test_flagged_provenance_stays_pending_without_altering_the_proposal(
    tmp_path: Path,
    origin_status: str,
    attribution_status: str,
    assistance_status: str,
) -> None:
    proposal = _proposal(
        tmp_path,
        origin_status=origin_status,
        attribution_status=attribution_status,
        assistance_status=assistance_status,
    )

    admission = decide_admission(proposal, _policy("policy-04-baseline-60", 60))

    assert admission.admission_status == AssessmentAdmissionStatus.PENDING_CONFIRMATION
    assert proposal.origin_status == origin_status
    assert proposal.attribution_status == attribution_status
    assert proposal.assistance_status == assistance_status


def test_insufficient_review_is_retained_as_an_unverified_candidate(tmp_path: Path) -> None:
    proposal = _proposal(tmp_path)

    admission = decide_admission(
        proposal,
        _policy("policy-04-baseline-60", 60),
        review_outcome="insufficient-basis",
    )

    assert admission.admission_status == "unverified-candidate"
    assert admission.reason_code == "insufficient-basis"
    assert proposal.demonstrated_mastery == 60
