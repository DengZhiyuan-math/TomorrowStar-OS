"""JD comparison accepts substantive current reviews, not authority labels alone."""

from pathlib import Path

import pytest
from test_jd_comparison import POLICIES, _write_reviewed_user_truth

from career_evidence_graph.assessment import (
    AssessmentRun,
    AssessmentStore,
    aggregate_skill,
    aggregate_user_skills,
    build_assessment_run,
    decide_admission,
    load_policy,
    review_assessment,
)
from career_evidence_graph.domain.models import ContributionSkillAssessment
from career_evidence_graph.jd import JDComparisonError, load_reviewed_user_graph
from career_evidence_graph.validation.hashing import canonical_json_bytes, sha256_digest

RUN_ID = "assessment-audit-e2e-04-baseline-60"


def _review(record: AssessmentRun, outcome: str = "confirm", **changes: object) -> AssessmentRun:
    payload = record.proposal.model_dump(mode="json")
    payload.update(changes)
    return review_assessment(
        record,
        policy=load_policy(POLICIES, "policy-04-baseline-60"),
        expected_effective_hash=record.effective_assessment_hash,
        reviewer_id="synthetic-reviewer",
        review_reason="Check attribution, anchor fit, and every judgment basis.",
        attribution_checked=True,
        anchor_fit_checked=True,
        all_judgments_checked=True,
        accepted_assessment=ContributionSkillAssessment.model_validate(payload),
        outcome=outcome,
    )


@pytest.mark.parametrize(
    ("status", "review_complete"),
    (("partial", False), ("unresolved", True), ("reviewed", False)),
)
def test_unreviewed_admitted_baseline_cannot_enter_reviewed_jd_graph(
    tmp_path: Path, status: str, review_complete: bool
) -> None:
    _write_reviewed_user_truth(tmp_path)
    store = AssessmentStore(tmp_path)
    payload = store.read(RUN_ID).proposal.model_dump(mode="json")
    payload.update(assessment_status=status, substantive_review_complete=review_complete)
    proposal = ContributionSkillAssessment.model_validate(payload)
    policy = load_policy(POLICIES, "policy-04-baseline-60")
    record = build_assessment_run(proposal, decide_admission(proposal, policy))
    assert record.admission.admission_status == "admitted"
    assert aggregate_user_skills((record,))[0].mastery == 60
    store.replace(RUN_ID, record)

    with pytest.raises(JDComparisonError, match="reviewed user graph"):
        load_reviewed_user_graph(tmp_path)


def test_review_flags_without_retained_review_cannot_enter_jd_graph(tmp_path: Path) -> None:
    _write_reviewed_user_truth(tmp_path)
    store = AssessmentStore(tmp_path)
    payload = store.read(RUN_ID).proposal.model_dump(mode="json")
    payload.update(assessment_status="reviewed", substantive_review_complete=True)
    proposal = ContributionSkillAssessment.model_validate(payload)
    policy = load_policy(POLICIES, "policy-04-baseline-60")
    store.replace(RUN_ID, build_assessment_run(proposal, decide_admission(proposal, policy)))

    with pytest.raises(JDComparisonError, match="reviewed user graph"):
        load_reviewed_user_graph(tmp_path)


def test_derived_origin_cannot_become_user_truth_by_reviewing_its_label(tmp_path: Path) -> None:
    _write_reviewed_user_truth(tmp_path)
    store = AssessmentStore(tmp_path)
    payload = store.read(RUN_ID).proposal.model_dump(mode="json")
    payload["origin_status"] = "derived-counterfactual"
    proposal = ContributionSkillAssessment.model_validate(payload)
    policy = load_policy(POLICIES, "policy-04-baseline-60")
    record = build_assessment_run(proposal, decide_admission(proposal, policy))
    reviewed = _review(record)
    store.replace(RUN_ID, reviewed)

    with pytest.raises(JDComparisonError, match="reviewed user graph"):
        load_reviewed_user_graph(tmp_path)


def test_review_without_original_version_cannot_enter_jd_graph(tmp_path: Path) -> None:
    _write_reviewed_user_truth(tmp_path)
    store = AssessmentStore(tmp_path)
    payload = store.read(RUN_ID).model_dump(mode="json")
    latest = payload["versions"][-1]
    latest["previous_version_hash"] = None
    latest["version_hash"] = sha256_digest(
        canonical_json_bytes({key: value for key, value in latest.items() if key != "version_hash"})
    )
    payload.update(versions=[latest], version_hash=latest["version_hash"])
    store.replace(RUN_ID, AssessmentRun.model_validate(payload))

    with pytest.raises(JDComparisonError, match="reviewed user graph"):
        load_reviewed_user_graph(tmp_path)


def test_insufficient_review_cannot_be_re_admitted_as_reviewed_truth(tmp_path: Path) -> None:
    _write_reviewed_user_truth(tmp_path)
    store = AssessmentStore(tmp_path)
    withheld = _review(store.read(RUN_ID), outcome="insufficient-basis")
    assert withheld.admission.admission_status == "unverified-candidate"
    policy = load_policy(POLICIES, "policy-04-baseline-60")
    admission = decide_admission(withheld.proposal, policy)
    assert admission.admission_status == "admitted"
    payload = withheld.model_dump(mode="json")
    payload["admission"] = admission.model_dump(mode="json")
    payload["result"] = aggregate_skill(withheld.proposal, admission).model_dump(mode="json")
    latest = payload["versions"][-1]
    latest["admission"] = payload["admission"]
    latest["version_hash"] = sha256_digest(
        canonical_json_bytes({key: value for key, value in latest.items() if key != "version_hash"})
    )
    payload["version_hash"] = latest["version_hash"]
    store.replace(RUN_ID, AssessmentRun.model_validate(payload))

    with pytest.raises(JDComparisonError, match="reviewed user graph"):
        load_reviewed_user_graph(tmp_path)


def test_old_version_review_cannot_authorize_unreviewed_current_version(tmp_path: Path) -> None:
    _write_reviewed_user_truth(tmp_path)
    store = AssessmentStore(tmp_path)
    reviewed = store.read(RUN_ID)
    renewed = build_assessment_run(reviewed.proposal, reviewed.admission)
    payload = renewed.model_dump(mode="json")
    latest = payload["versions"][-1]
    latest.update(
        version_id=f"assessment-version-{renewed.proposal.id}-3",
        previous_version_hash=reviewed.version_hash,
    )
    latest["version_hash"] = sha256_digest(
        canonical_json_bytes({key: value for key, value in latest.items() if key != "version_hash"})
    )
    payload.update(
        versions=[*[version.model_dump(mode="json") for version in reviewed.versions], latest],
        version_hash=latest["version_hash"],
    )
    store.replace(RUN_ID, AssessmentRun.model_validate(payload))
    current = store.read(RUN_ID)
    assert current.versions[-2].reviews
    assert not current.reviews

    with pytest.raises(JDComparisonError, match="reviewed user graph"):
        load_reviewed_user_graph(tmp_path)


@pytest.mark.parametrize("origin", ("audit-verified", "self-assessed-unverified"))
@pytest.mark.parametrize("outcome", ("confirm", "edit"))
def test_substantive_review_preserves_legal_origin_and_enters_jd_graph(
    tmp_path: Path, origin: str, outcome: str
) -> None:
    _write_reviewed_user_truth(tmp_path)
    store = AssessmentStore(tmp_path)
    payload = store.read(RUN_ID).proposal.model_dump(mode="json")
    payload.update(
        origin_status=origin, assessment_status="partial", substantive_review_complete=False
    )
    proposal = ContributionSkillAssessment.model_validate(payload)
    policy = load_policy(POLICIES, "policy-04-baseline-60")
    record = build_assessment_run(proposal, decide_admission(proposal, policy))
    changes = {"skill_centrality": 79} if outcome == "edit" else {}
    reviewed = _review(record, outcome, **changes)
    store.replace(RUN_ID, reviewed)
    before = store.path(RUN_ID).read_bytes()

    records, results, _graph_hash = load_reviewed_user_graph(tmp_path)

    assert records == (reviewed,)
    assert records[0].proposal.origin_status == origin
    assert records[0].reviews[-1].outcome == outcome
    assert records[0].proposal.substantive_review_complete is True
    assert results[0].mastery == 60
    assert store.path(RUN_ID).read_bytes() == before


def test_insufficient_basis_review_stays_outside_reviewed_jd_graph(tmp_path: Path) -> None:
    _write_reviewed_user_truth(tmp_path)
    store = AssessmentStore(tmp_path)
    withheld = _review(store.read(RUN_ID), outcome="insufficient-basis")
    store.replace(RUN_ID, withheld)

    with pytest.raises(JDComparisonError, match="reviewed user graph"):
        load_reviewed_user_graph(tmp_path)

    assert store.read(RUN_ID) == withheld
