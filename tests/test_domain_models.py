from __future__ import annotations

from copy import deepcopy

import pytest
from pydantic import ValidationError

from career_evidence_graph.domain.invariants import (
    FixtureValidationError,
    validate_career_evidence_fixture,
)
from career_evidence_graph.domain.models import (
    CareerEvidenceFixture,
    Contribution,
    ContributionClaim,
    ContributionSkillAssessment,
    DurationEvidence,
    Evidence,
    Experience,
)


def _fixture_payload() -> dict[str, object]:
    return {
        "schema_version": "career-evidence-fixture/v1",
        "fixture_notice": "Synthetic contract exercise; not calibrated mastery.",
        "experiences": [
            {
                "id": "experience.synthetic",
                "experience_type": "project",
                "title": "Synthetic validation tracer",
                "contribution_ids": ["contribution.delivery"],
            }
        ],
        "contributions": [
            {
                "id": "contribution.delivery",
                "experience_id": "experience.synthetic",
                "summary": "A synthetic auditable outcome.",
                "claim_ids": ["claim.delivery"],
            }
        ],
        "claims": [
            {
                "id": "claim.delivery",
                "contribution_id": "contribution.delivery",
                "statement": "A synthetic claim with explicit limits.",
                "responsibility": "user",
                "assistance": "none",
                "confirmation_status": "confirmed",
                "completion_status": "delivered",
                "limitations": ["Synthetic fixture only."],
            }
        ],
        "evidence": [
            {
                "id": "evidence.synthetic",
                "kind": "acceptance_record",
                "proof_limit": "recorded_delivery",
                "repository": "synthetic/repository",
                "pinned_commit": "a" * 40,
                "tracked_path": "docs/acceptance.md",
                "section_locator": "# synthetic-result",
                "content_hash": "sha256:" + "b" * 64,
            }
        ],
        "claim_evidence_links": [
            {
                "claim_id": "claim.delivery",
                "evidence_id": "evidence.synthetic",
                "section_locator": "# synthetic-result",
            }
        ],
        "skills": [{"id": "skill.validation", "name": "Validation"}],
        "assessments": [
            {
                "id": "assessment.validation",
                "skill_id": "skill.validation",
                "contribution_id": "contribution.delivery",
                "lineage": {
                    "source_kind": "contribution",
                    "contribution_id": "contribution.delivery",
                },
                "demonstrated_mastery": 0,
                "skill_centrality": 100,
                "evidence_confidence": 37,
                "context": "Synthetic contract fixture.",
                "duration": {"state": "not_verified"},
                "basis_claim_ids": ["claim.delivery"],
                "assessment_status": "partial",
            }
        ],
        "user_skill_views": [
            {
                "skill_id": "skill.validation",
                "assessment_ids": ["assessment.validation"],
                "fixture_notice": "Non-calibrated test view.",
            }
        ],
    }


def _assessment_payload() -> dict[str, object]:
    return _fixture_payload()["assessments"][0]  # type: ignore[index, return-value]


@pytest.mark.parametrize(
    "experience_type",
    [
        "employment",
        "project",
        "research",
        "publication",
        "education",
        "teaching",
        "open_source",
        "internship",
        "related",
    ],
)
def test_supported_experience_types_keep_distinguishable_contribution_ids(experience_type: str):
    experience = Experience(
        id="experience.history",
        experience_type=experience_type,  # type: ignore[arg-type]
        title="Representative history",
        contribution_ids=("contribution.first", "contribution.second"),
    )

    assert experience.contribution_ids == ("contribution.first", "contribution.second")


def test_experience_rejects_unknown_type_blank_or_duplicate_contribution_ids():
    with pytest.raises(ValidationError):
        Experience(
            id="experience.history",
            experience_type="credential",  # type: ignore[arg-type]
            title="Representative history",
            contribution_ids=("contribution.first",),
        )
    with pytest.raises(ValidationError):
        Experience(
            id="experience.history",
            experience_type="project",
            title="Representative history",
            contribution_ids=("",),
        )
    with pytest.raises(ValidationError, match="unique"):
        Experience(
            id="experience.history",
            experience_type="project",
            title="Representative history",
            contribution_ids=("contribution.first", "contribution.first"),
        )


def test_contribution_requires_a_valid_parent_and_distinct_claim_children():
    with pytest.raises(ValidationError):
        Contribution(
            id="contribution.delivery",
            experience_id="",
            summary="A concrete outcome.",
            claim_ids=("claim.delivery",),
        )
    with pytest.raises(ValidationError):
        Contribution(
            id="contribution.delivery",
            experience_id="experience.synthetic",
            summary="A concrete outcome.",
            claim_ids=("",),
        )


@pytest.mark.parametrize(
    ("kind", "proof_limit"),
    [
        ("plan", "intent_or_assignment"),
        ("handoff", "recorded_delivery"),
        ("acceptance_record", "recorded_delivery"),
        ("audit", "observed_state_defects_limitations"),
        ("user_confirmation", "personal_responsibility_and_claimed_capability"),
    ],
)
def test_evidence_has_exact_proof_limit_and_pinned_section_identity(kind: str, proof_limit: str):
    evidence = Evidence(
        id="evidence.document",
        kind=kind,  # type: ignore[arg-type]
        proof_limit=proof_limit,  # type: ignore[arg-type]
        repository="owner/repository",
        pinned_commit="a" * 40,
        tracked_path="docs/source.md",
        section_locator="# section",
        content_hash="sha256:" + "b" * 64,
    )

    assert evidence.proof_limit == proof_limit


def test_evidence_rejects_wrong_proof_limit_or_unpinned_locator_components():
    payload = {
        "id": "evidence.document",
        "kind": "audit",
        "proof_limit": "recorded_delivery",
        "repository": "owner/repository",
        "pinned_commit": "a" * 40,
        "tracked_path": "docs/source.md",
        "section_locator": "# section",
        "content_hash": "sha256:" + "b" * 64,
    }
    with pytest.raises(ValidationError, match="requires proof_limit"):
        Evidence.model_validate(payload)

    for field, value in (
        ("pinned_commit", "a" * 39),
        ("tracked_path", ""),
        ("section_locator", ""),
        ("content_hash", "sha256:not-a-content-hash"),
    ):
        invalid = payload | {
            "kind": "audit",
            "proof_limit": "observed_state_defects_limitations",
            field: value,
        }
        with pytest.raises(ValidationError):
            Evidence.model_validate(invalid)


@pytest.mark.parametrize("responsibility", ["user", "team", "other_person", "non_responsibility"])
@pytest.mark.parametrize("assistance", ["none", "codex_assisted", "third_party"])
def test_claim_responsibility_and_assistance_are_independent(responsibility: str, assistance: str):
    claim = ContributionClaim(
        id="claim.delivery",
        contribution_id="contribution.delivery",
        statement="A claim with declared attribution.",
        responsibility=responsibility,  # type: ignore[arg-type]
        assistance=assistance,  # type: ignore[arg-type]
        confirmation_status="unconfirmed",
        completion_status="partial",
        limitations=("Requires review.",),
    )

    assert (claim.responsibility, claim.assistance) == (responsibility, assistance)


@pytest.mark.parametrize("values", [(0, 100, 37), (100, 0, 63)])
def test_assessment_score_dimensions_accept_independent_inclusive_boundaries(
    values: tuple[int, int, int],
):
    payload = deepcopy(_assessment_payload())
    payload["demonstrated_mastery"], payload["skill_centrality"], payload["evidence_confidence"] = (
        values
    )

    assessment = ContributionSkillAssessment.model_validate(payload)

    assert (
        assessment.demonstrated_mastery,
        assessment.skill_centrality,
        assessment.evidence_confidence,
    ) == values


@pytest.mark.parametrize(
    "field", ["demonstrated_mastery", "skill_centrality", "evidence_confidence"]
)
@pytest.mark.parametrize("value", [-1, 101])
def test_assessment_rejects_each_out_of_range_score_independently(field: str, value: int):
    payload = deepcopy(_assessment_payload())
    payload[field] = value

    with pytest.raises(ValidationError):
        ContributionSkillAssessment.model_validate(payload)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("context", ""),
        ("context", "   "),
        ("duration", None),
        ("basis_claim_ids", []),
    ],
)
def test_assessment_rejects_blank_or_null_required_semantics(field: str, value: object):
    payload = deepcopy(_assessment_payload())
    payload[field] = value

    with pytest.raises(ValidationError):
        ContributionSkillAssessment.model_validate(payload)


def test_duration_requires_an_explicit_state_and_a_complete_optional_month_range():
    with pytest.raises(ValidationError):
        DurationEvidence.model_validate({})
    with pytest.raises(ValidationError, match="appear together"):
        DurationEvidence.model_validate({"state": "verified", "start_month": "2025-01"})
    with pytest.raises(ValidationError, match="must not precede"):
        DurationEvidence.model_validate(
            {"state": "verified", "start_month": "2025-02", "end_month": "2025-01"}
        )


@pytest.mark.parametrize(
    ("collection", "invariant_collection"),
    [
        ("contributions", "contribution"),
        ("claims", "claim"),
        ("evidence", "evidence"),
    ],
)
def test_fixture_rejects_duplicate_global_record_ids(collection: str, invariant_collection: str):
    payload = deepcopy(_fixture_payload())
    records = payload[collection]  # type: ignore[index]
    records.append(deepcopy(records[0]))  # type: ignore[union-attr,index]

    fixture = CareerEvidenceFixture.model_validate(payload)

    with pytest.raises(FixtureValidationError, match="invalid") as exc_info:
        validate_career_evidence_fixture(fixture)
    assert [violation.code for violation in exc_info.value.violations] == [
        f"{invariant_collection}.duplicate_id"
    ]


def test_models_reject_unknown_fields_at_each_strict_boundary():
    payload = deepcopy(_fixture_payload())
    payload["surprise"] = True

    with pytest.raises(ValidationError):
        CareerEvidenceFixture.model_validate(payload)
