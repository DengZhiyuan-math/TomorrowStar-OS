"""Deterministic regression coverage for Contribution-only mastery boundaries."""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

import pytest

from career_evidence_graph.domain.invariants import (
    FixtureValidationError,
    collect_invariant_violations,
    validate_career_evidence_fixture,
)
from career_evidence_graph.domain.models import CareerEvidenceFixture
from career_evidence_graph.validation.hashing import canonical_json_bytes


def _payload() -> dict[str, object]:
    return json.loads(
        Path("tests/fixtures/domain_fixture.json").read_text(encoding="utf-8")
    )


def _fixture(payload: dict[str, object]) -> CareerEvidenceFixture:
    return CareerEvidenceFixture.model_validate(payload)


def _codes(fixture: CareerEvidenceFixture) -> list[str]:
    return [item.code for item in collect_invariant_violations(fixture)]


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
            ["assessment.basis_claim_mismatch", "assessment.contribution_missing"],
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
    assert _codes(_fixture(payload)) == ["user-skill.without-assessment"]


def test_view_for_an_unassessed_skill_is_rejected_without_creating_mastery():
    payload = _payload()
    payload["user_skill_views"][0]["skill_id"] = "skill.unassessed"  # type: ignore[index]

    assert _codes(_fixture(payload)) == ["user-skill.without-assessment"]


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

    first = canonical_json_bytes(collect_invariant_violations(fixture))
    second = canonical_json_bytes(collect_invariant_violations(fixture))
    shuffled = deepcopy(payload)
    shuffled["assessments"].reverse()  # type: ignore[index]

    assert first == second == canonical_json_bytes(
        collect_invariant_violations(_fixture(shuffled))
    )
    assert original_bytes == canonical_json_bytes(payload)
    expected = tuple(
        sorted(collect_invariant_violations(fixture), key=lambda item: (item.code, item.path))
    )
    assert first == canonical_json_bytes(expected)


def test_validate_wrapper_reports_all_ordered_invariant_violations():
    payload = _payload()
    payload["user_skill_views"].append(deepcopy(payload["user_skill_views"][0]))  # type: ignore[index]
    payload["assessments"][0]["lineage"]["source_kind"] = "title"  # type: ignore[index]

    with pytest.raises(FixtureValidationError) as error:
        validate_career_evidence_fixture(_fixture(payload))

    assert [(item.code, item.path) for item in error.value.violations] == sorted(
        (item.code, item.path) for item in error.value.violations
    )
