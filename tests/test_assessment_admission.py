"""Fail-closed admission contracts for contribution-Skill proposals."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from career_evidence_graph.assessment import (
    AssessmentRun,
    AssessmentStore,
    AssessmentWorkflowError,
    aggregate_skill,
    decide_admission,
    reassess_from_new_evidence,
    review_assessment,
    run_assessment,
)
from career_evidence_graph.domain.models import (
    MASTERY_ANCHORS,
    AggregationPolicy,
    AssessmentAdmissionStatus,
    ContributionSkillAssessment,
)

ROOT = Path(__file__).parents[1]
CORPUS = ROOT / "validation/calibration/phase-04/corpus.json"
POLICIES = ROOT / "validation/calibration/phase-04/policies.json"
LAUNCHER = ROOT / "scripts/run_career_evidence.py"


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


def _anchor_payload(mastery: int) -> dict[str, object]:
    anchor = next(
        item
        for item in MASTERY_ANCHORS
        if mastery in range(item.inclusive_range[0], item.inclusive_range[1] + 1)
    )
    return {
        "anchor_id": anchor.anchor_id,
        "anchor_range": list(anchor.inclusive_range),
        "anchor_text": anchor.capability_text,
        "anchor_basis": "The fixture independently establishes the stated capability band.",
        "exact_score_basis": "The integer fixture score remains inside the accepted anchor.",
        "next_anchor_not_established": "The next capability anchor remains unestablished.",
    }


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
        mastery_anchor_fit=_anchor_payload(mastery),
        exact_score_basis="The integer fixture score remains inside the accepted anchor.",
    )

    admission = decide_admission(proposal, _policy(policy, 60 if policy.endswith("60") else 70))

    assert admission.admission_status == expected
    assert (
        proposal.demonstrated_mastery,
        proposal.skill_centrality,
        proposal.evidence_confidence,
    ) == (
        mastery,
        80,
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


def _review(
    record: AssessmentRun,
    *,
    proposal: ContributionSkillAssessment | None = None,
    outcome: str = "confirm",
    **changes: object,
) -> AssessmentRun:
    return review_assessment(
        record,
        policy=_policy("policy-04-baseline-60", 60),
        expected_effective_hash=record.effective_assessment_hash,
        reviewer_id="reviewer-a",
        review_reason="I inspected the attribution, capability anchor, and each judgment basis.",
        attribution_checked=True,
        anchor_fit_checked=True,
        all_judgments_checked=True,
        accepted_assessment=proposal or record.proposal,
        outcome=outcome,
        **changes,
    )


@pytest.mark.parametrize(
    "changes",
    (
        {"attribution_checked": False},
        {"anchor_fit_checked": False},
        {"all_judgments_checked": False},
        {"reviewer_id": ""},
        {"review_reason": ""},
        {"expected_effective_hash": "sha256:" + "0" * 64},
    ),
)
def test_review_fails_closed_without_every_substantive_acknowledgment(
    tmp_path: Path, changes: dict[str, object]
) -> None:
    record = run_assessment(
        workspace=tmp_path,
        corpus_path=CORPUS,
        policies_path=POLICIES,
        audit_id="audit-e2e",
        policy_version="policy-04-baseline-60",
    )

    with pytest.raises(AssessmentWorkflowError, match="review"):
        _review(record, **changes)

    assert AssessmentStore(tmp_path).read("assessment-audit-e2e-04-baseline-60") == record


def test_confirm_and_correction_preserve_original_proposal_and_ordered_review_hashes(
    tmp_path: Path,
) -> None:
    record = run_assessment(
        workspace=tmp_path,
        corpus_path=CORPUS,
        policies_path=POLICIES,
        audit_id="audit-e2e",
        policy_version="policy-04-baseline-60",
    )
    edited_payload = record.proposal.model_dump(mode="json")
    edited_payload["skill_centrality"] = 79
    edited = ContributionSkillAssessment.model_validate(edited_payload)

    corrected = _review(record, proposal=edited, outcome="edit")
    confirmed = _review(corrected)

    assert corrected.original_proposal == record.proposal
    assert corrected.original_proposal_hash == record.original_proposal_hash
    assert [item.sequence for item in confirmed.reviews] == [1, 2]
    assert confirmed.reviews[0].before_effective_hash == record.effective_assessment_hash
    assert confirmed.reviews[0].after_effective_hash == corrected.effective_assessment_hash
    assert confirmed.reviews[1].before_effective_hash == corrected.effective_assessment_hash
    assert confirmed.reviews[1].after_effective_hash == confirmed.effective_assessment_hash
    assert confirmed.proposal.skill_centrality == 79


def test_insufficient_review_and_later_evidence_preserve_immutable_versions(tmp_path: Path) -> None:
    record = run_assessment(
        workspace=tmp_path,
        corpus_path=CORPUS,
        policies_path=POLICIES,
        audit_id="audit-e2e",
        policy_version="policy-04-baseline-60",
    )
    withheld = _review(record, outcome="insufficient-basis")
    later = reassess_from_new_evidence(
        withheld,
        policy=_policy("policy-04-baseline-60", 60),
        source_audit_id="audit-later-evidence",
        proposal=withheld.proposal,
    )

    assert withheld.admission.admission_status == "unverified-candidate"
    assert withheld.result is None
    assert later.versions[-1].previous_version_hash == withheld.version_hash
    assert later.versions[-1].source_audit_id == "audit-later-evidence"
    assert later.versions[0].original_proposal_hash == record.original_proposal_hash


def _run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(LAUNCHER), *args],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )


def test_pending_and_review_cli_require_complete_payload_without_leaking_answers(tmp_path: Path) -> None:
    record = run_assessment(
        workspace=tmp_path,
        corpus_path=CORPUS,
        policies_path=POLICIES,
        audit_id="audit-e2e",
        policy_version="policy-04-baseline-60",
    )
    pending_proposal = _proposal(
        tmp_path,
        demonstrated_mastery=70,
        evidence_confidence=59,
        mastery_anchor_fit=_anchor_payload(70),
        exact_score_basis="The integer fixture score remains inside the accepted anchor.",
    )
    pending = AssessmentRun(
        proposal=pending_proposal,
        admission=decide_admission(pending_proposal, _policy("policy-04-baseline-60", 60)),
    )
    store = AssessmentStore(tmp_path)
    store.replace("assessment-audit-e2e-04-baseline-60", pending)
    payload_path = tmp_path / "accepted-assessment.json"
    payload_path.write_text(json.dumps(pending_proposal.model_dump(mode="json")), encoding="utf-8")

    listed = _run("assessment", "pending", "--workspace", str(tmp_path))
    assert listed.returncode == 0, listed.stderr
    assert "direct_review_request" in listed.stdout
    assert "demonstrated_mastery_basis" in listed.stdout
    assert "RAW_INTERVIEW_SENTINEL" not in listed.stdout

    incomplete = _run(
        "assessment",
        "review",
        "--workspace",
        str(tmp_path),
        "--run-id",
        "assessment-audit-e2e-04-baseline-60",
        "--expected-effective-hash",
        pending.effective_assessment_hash,
        "--reviewer",
        "reviewer-a",
        "--reason",
        "valid reason",
        "--assessment-json",
        str(payload_path),
    )
    assert incomplete.returncode == 2
    assert "assessment_workflow_error" in incomplete.stderr
