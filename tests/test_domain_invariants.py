"""Deterministic regression coverage for Contribution-only mastery boundaries."""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

import pytest

from career_evidence_graph.domain.invariants import (
    FixtureValidationError,
    collect_invariant_violations,
    mastery_snapshot_bytes,
    normalize_skill_metadata,
    validate_career_evidence_fixture,
)
from career_evidence_graph.domain.models import (
    CareerEvidenceFixture,
    OntologyRelation,
    Skill,
    SkillAlias,
)
from career_evidence_graph.validation.hashing import canonical_json_bytes


def _payload() -> dict[str, object]:
    return json.loads(Path("tests/fixtures/domain_fixture.json").read_text(encoding="utf-8"))


def _fixture(payload: dict[str, object]) -> CareerEvidenceFixture:
    return CareerEvidenceFixture.model_validate(payload)


def _codes(fixture: CareerEvidenceFixture) -> list[str]:
    return [item.code for item in collect_invariant_violations(fixture)]


def _violation_bytes(fixture: CareerEvidenceFixture) -> bytes:
    return canonical_json_bytes(
        tuple(item.model_dump(mode="json") for item in collect_invariant_violations(fixture))
    )


@pytest.mark.parametrize(
    "source_kind",
    (
        "experience",
        "credential",
        "title",
        "repository",
        "resume-skill-list",
        "ontology-relation",
    ),
)
def test_direct_mastery_sources_are_rejected_with_the_same_sole_code(source_kind: str):
    payload = _payload()
    payload["assessments"][0]["lineage"]["source_kind"] = source_kind  # type: ignore[index]

    assert _codes(_fixture(payload)) == ["assessment.direct-source-forbidden"]


def test_contribution_lineage_is_the_only_admitted_source_kind():
    assert _codes(_fixture(_payload())) == []


@pytest.mark.parametrize(
    ("mutation", "expected_codes"),
    (
        (
            lambda payload: payload["assessments"].append(  # type: ignore[index]
                deepcopy(payload["assessments"][0])  # type: ignore[index]
            ),
            ["assessment.duplicate_id"],
        ),
        (
            lambda payload: payload["claim_evidence_links"].append(  # type: ignore[index]
                deepcopy(payload["claim_evidence_links"][0])  # type: ignore[index]
            ),
            ["claim_evidence_link.duplicate"],
        ),
        (
            lambda payload: (
                payload["assessments"][0].update(  # type: ignore[index]
                    {"contribution_id": "contribution.missing"}
                ),
                payload["assessments"][0]["lineage"].update(  # type: ignore[index]
                    {"contribution_id": "contribution.missing"}
                ),
            ),
            ["assessment.contribution_missing"],
        ),
    ),
)
def test_lineage_and_evidence_duplicates_have_one_stable_rejection(
    mutation, expected_codes: list[str]
):
    payload = _payload()
    mutation(payload)

    assert _codes(_fixture(payload)) == expected_codes


@pytest.mark.parametrize(
    ("claim_update", "expected_code"),
    (
        ({"responsibility": "team"}, "assessment.definite_claim_not_user"),
        ({"confirmation_status": "unconfirmed"}, "assessment.definite_claim_unconfirmed"),
        ({"completion_status": "unresolved"}, "assessment.definite_claim_unresolved"),
        ({"assistance": "codex_assisted"}, "assessment.definite_claim_assisted"),
    ),
)
def test_definite_conclusions_preserve_claim_attribution_and_assistance(
    claim_update: dict[str, str], expected_code: str
):
    payload = _payload()
    payload["assessments"][0]["assessment_status"] = "reviewed"  # type: ignore[index]
    payload["claims"][0].update(claim_update)  # type: ignore[index]

    assert _codes(_fixture(payload)) == [expected_code]


def test_assessment_basis_requires_a_resolved_evidence_link() -> None:
    payload = _payload()
    claim = deepcopy(payload["claims"][0])  # type: ignore[index]
    claim["id"] = "claim.unlinked"  # type: ignore[index]
    payload["claims"].append(claim)  # type: ignore[index]
    payload["contributions"][0]["claim_ids"].append("claim.unlinked")  # type: ignore[index]
    payload["assessments"][0]["basis_claim_ids"] = ["claim.unlinked"]  # type: ignore[index]

    assert _codes(_fixture(payload)) == ["assessment.basis_claim_evidence_missing"]


def test_assessed_contribution_must_be_listed_by_its_experience() -> None:
    payload = _payload()
    claim = deepcopy(payload["claims"][0])  # type: ignore[index]
    claim["id"] = "claim.orphan"  # type: ignore[index]
    claim["contribution_id"] = "contribution.orphan"  # type: ignore[index]
    payload["claims"].append(claim)  # type: ignore[index]
    contribution = deepcopy(payload["contributions"][0])  # type: ignore[index]
    contribution["id"] = "contribution.orphan"  # type: ignore[index]
    contribution["claim_ids"] = ["claim.orphan"]  # type: ignore[index]
    payload["contributions"].append(contribution)  # type: ignore[index]
    evidence_link = deepcopy(payload["claim_evidence_links"][0])  # type: ignore[index]
    evidence_link["claim_id"] = "claim.orphan"  # type: ignore[index]
    payload["claim_evidence_links"].append(evidence_link)  # type: ignore[index]
    assessment = deepcopy(payload["assessments"][0])  # type: ignore[index]
    assessment["id"] = "assessment.orphan"  # type: ignore[index]
    assessment["contribution_id"] = "contribution.orphan"  # type: ignore[index]
    assessment["lineage"]["contribution_id"] = "contribution.orphan"  # type: ignore[index]
    assessment["basis_claim_ids"] = ["claim.orphan"]  # type: ignore[index]
    payload["assessments"].append(assessment)  # type: ignore[index]
    payload["user_skill_views"][0]["assessment_ids"].append("assessment.orphan")  # type: ignore[index]

    assert _codes(_fixture(payload)) == ["experience.contribution_unlisted"]


def test_user_skill_views_require_exactly_one_view_for_each_assessed_skill():
    payload = _payload()
    payload["user_skill_views"].append(deepcopy(payload["user_skill_views"][0]))  # type: ignore[index]

    assert _codes(_fixture(payload)) == ["user-skill.duplicate"]


def test_zero_assessments_allow_zero_views_but_reject_a_synthetic_view():
    payload = _payload()
    payload["assessments"] = []
    payload["user_skill_views"] = []
    assert _codes(_fixture(payload)) == []

    payload = _payload()
    payload["assessments"] = []
    assert _codes(_fixture(payload)) == [
        "user-skill.assessment_missing",
        "user-skill.without-assessment",
    ]


def test_view_for_an_unassessed_skill_is_rejected_without_creating_mastery():
    payload = _payload()
    payload["user_skill_views"][0]["skill_id"] = "skill.unassessed"  # type: ignore[index]

    assert _codes(_fixture(payload)) == [
        "user-skill.missing",
        "user-skill.skill_mismatch",
        "user-skill.skill_missing",
        "user-skill.without-assessment",
    ]


def test_assessment_and_view_cannot_share_an_undeclared_skill_reference() -> None:
    payload = _payload()
    payload["assessments"][0]["skill_id"] = "skill.missing"  # type: ignore[index]
    payload["user_skill_views"][0]["skill_id"] = "skill.missing"  # type: ignore[index]

    assert _codes(_fixture(payload)) == [
        "assessment.skill_missing",
        "user-skill.skill_missing",
    ]


def test_user_skill_view_has_no_supporting_score_dimensions():
    view = _fixture(_payload()).user_skill_views[0]

    assert set(view.model_fields_set).isdisjoint(
        {"confidence", "duration", "recency", "context", "jd_match"}
    )
    assert view.mastery == 0
    assert view.policy_marker == "fixture-test-expectation"


def test_repeated_and_shuffled_validation_is_sorted_and_does_not_mutate_input():
    payload = _payload()
    payload["assessments"].append(deepcopy(payload["assessments"][0]))  # type: ignore[index]
    payload["assessments"][-1]["id"] = "assessment.duplicate"  # type: ignore[index]
    payload["assessments"][-1]["lineage"]["source_kind"] = "repository"  # type: ignore[index]
    original_bytes = canonical_json_bytes(payload)
    fixture = _fixture(payload)

    first = _violation_bytes(fixture)
    second = _violation_bytes(fixture)
    shuffled = deepcopy(payload)
    shuffled["assessments"].reverse()  # type: ignore[index]

    assert first == second == _violation_bytes(_fixture(shuffled))
    assert original_bytes == canonical_json_bytes(payload)
    assert first == _violation_bytes(fixture)


def test_validate_wrapper_reports_all_ordered_invariant_violations():
    payload = _payload()
    payload["user_skill_views"].append(deepcopy(payload["user_skill_views"][0]))  # type: ignore[index]
    payload["assessments"][0]["lineage"]["source_kind"] = "title"  # type: ignore[index]

    with pytest.raises(FixtureValidationError) as error:
        validate_career_evidence_fixture(_fixture(payload))

    assert [(item.code, item.path) for item in error.value.violations] == sorted(
        (item.code, item.path) for item in error.value.violations
    )


def _skills() -> tuple[Skill, ...]:
    return (
        Skill(id="skill.python", name="Python"),
        Skill(id="skill.pydata", name="Python data tools"),
    )


def _alias(alias: str, skill_id: str = "skill.python") -> SkillAlias:
    return SkillAlias(
        alias=alias,
        skill_id=skill_id,
        ontology_source_id="mind-tech-ontology",
        pinned_revision="a" * 40,
    )


def _relation(
    relation_kind: str = "dependency", target_skill_id: str = "skill.pydata"
) -> OntologyRelation:
    return OntologyRelation(
        source_skill_id="skill.python",
        target_skill_id=target_skill_id,
        relation_kind=relation_kind,  # type: ignore[arg-type]
        ontology_source_id="mind-tech-ontology",
        pinned_revision="a" * 40,
    )


def test_ontology_empty_metadata_and_fixture_mastery_are_noops():
    fixture = _fixture(_payload())
    before = mastery_snapshot_bytes(fixture)

    assert normalize_skill_metadata(_skills()) == ()
    assert before == mastery_snapshot_bytes(fixture)


def test_ontology_alias_normalization_is_unicode_case_whitespace_stable_and_reviewable():
    aliases = (_alias("  P\u00fdTHON  "), _alias("py\u0301thon"))

    records = normalize_skill_metadata(_skills(), aliases=aliases)

    assert len(records) == 1
    assert records[0].original_text == "  P\u00fdTHON  "
    assert records[0].normalized_text == "p\u00fdthon"
    assert records[0].matched_alias == "  P\u00fdTHON  "
    assert records[0].candidate_skill_ids == ("skill.python",)
    assert records[0].ontology_source_id == "mind-tech-ontology"
    assert records[0].pinned_revision == "a" * 40
    assert records[0].review_status == "matched"
    serialized_records = tuple(record.model_dump(mode="json") for record in records)
    reordered_records = tuple(
        record.model_dump(mode="json")
        for record in normalize_skill_metadata(_skills(), aliases=tuple(reversed(aliases)))
    )
    assert canonical_json_bytes(serialized_records) == canonical_json_bytes(reordered_records)


def test_ontology_ambiguous_aliases_are_sorted_and_require_review_without_mastery():
    aliases = (_alias("py", "skill.pydata"), _alias("PY", "skill.python"))
    fixture = _fixture(_payload())
    before = mastery_snapshot_bytes(fixture)

    records = normalize_skill_metadata(_skills(), aliases=aliases)

    assert records[0].candidate_skill_ids == ("skill.pydata", "skill.python")
    assert records[0].review_status == "review-required"
    assert mastery_snapshot_bytes(fixture) == before


@pytest.mark.parametrize(
    "relations",
    (
        (_relation(),),
        (_relation("implies_knowledge"),),
        (_relation(), _relation()),
        (_relation("implies_knowledge"), _relation()),
    ),
)
def test_ontology_relations_are_descriptive_metadata_and_cannot_change_mastery(relations):
    fixture = _fixture(_payload())
    before = mastery_snapshot_bytes(fixture)

    records = normalize_skill_metadata(_skills(), ontology_relations=relations)

    assert records
    assert all(record.review_status == "descriptive-only" for record in records)
    assert mastery_snapshot_bytes(fixture) == before


def test_ontology_normalizer_has_no_fixture_or_score_parameters():
    parameters = normalize_skill_metadata.__code__.co_varnames[
        : normalize_skill_metadata.__code__.co_argcount
    ]

    assert set(parameters) == {"skills", "aliases", "ontology_relations"}
