"""Regression coverage for sealed-STOA one-fault fixture mutations."""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

import pytest
from pydantic import ValidationError

from career_evidence_graph.domain.fixtures import (
    FixtureMutationCase,
    FixtureMutationError,
    MutationOperation,
    SealedFixtureRecord,
    load_fixture_mutation_case,
    validate_mutation_case,
    validate_mutation_suite,
)
from career_evidence_graph.validation.hashing import canonical_json_bytes

ROOT = Path(__file__).resolve().parents[1]
KNOWN_GOOD = ROOT / "validation/fixtures/stoa/v1/known-good.json"
KNOWN_BAD_DIR = ROOT / "validation/fixtures/stoa/v1/known-bad"
FORMAL_RUN = ROOT / "validation/fixtures/stoa/v1/formal-runs/stoa-known-good"

EXPECTED_CODES = {
    "direct-mastery-experience": "assessment.direct-source-forbidden",
    "direct-mastery-title": "assessment.direct-source-forbidden",
    "direct-mastery-repository": "assessment.direct-source-forbidden",
    "direct-mastery-resume-skill-list": "assessment.direct-source-forbidden",
    "direct-mastery-ontology": "assessment.direct-source-forbidden",
    "wrong-responsibility": "assessment.definite_claim_not_user",
    "obscured-codex-assistance": "assessment.definite_claim_assisted",
    "duplicate-evidence-link": "claim_evidence_link.duplicate",
    "missing-contribution-lineage": "assessment.contribution_missing",
    "missing-assessment-basis": "assessment.basis_claim_missing",
    "dimension-confusion": "assessment.dimension_confusion",
    "score-below-zero": "assessment.score_out_of_range",
    "score-above-hundred": "assessment.score_out_of_range",
    "missing-context": "assessment.context_missing",
    "missing-duration": "assessment.duration_missing",
    "ontology-mastery-change": "assessment.ontology_mastery_change",
}


def _sealed() -> SealedFixtureRecord:
    return SealedFixtureRecord.model_validate_json(KNOWN_GOOD.read_bytes())


def _formal_bytes() -> dict[str, bytes]:
    return {
        path.relative_to(FORMAL_RUN).as_posix(): path.read_bytes()
        for path in sorted(FORMAL_RUN.rglob("*"))
        if path.is_file()
    }


def _cases() -> list[FixtureMutationCase]:
    return [
        load_fixture_mutation_case(path)
        for path in sorted(KNOWN_BAD_DIR.glob("*.json"), reverse=True)
    ]


def test_checked_in_cases_are_the_complete_sealed_one_fault_inventory() -> None:
    sealed = _sealed()
    case_paths = sorted(KNOWN_BAD_DIR.glob("*.json"))
    assert {path.stem for path in case_paths} == set(EXPECTED_CODES)

    cases = _cases()
    assert {case.case_id for case in cases} == set(EXPECTED_CODES)
    assert all(case.base_fixture_hash == sealed.confirmed_result_hash for case in cases)
    assert all(len(case.operations) == 1 for case in cases)
    assert {case.case_id: case.expected_code for case in cases} == EXPECTED_CODES


def test_empty_duplicate_and_multiple_operation_declarations_reject_before_mutation() -> None:
    case = _cases()[0]
    payload = case.model_dump(mode="json")
    payload["operations"] = []
    with pytest.raises(ValidationError):
        FixtureMutationCase.model_validate(payload)

    payload = case.model_dump(mode="json")
    payload["operations"] = [payload["operations"][0], payload["operations"][0]]
    with pytest.raises(ValidationError):
        FixtureMutationCase.model_validate(payload)

    payload = case.model_dump(mode="json")
    payload["operations"] = [
        payload["operations"][0],
        {
            "schema_version": "fixture-mutation-operation/v1",
            "kind": "duplicate-evidence-link",
        },
    ]
    with pytest.raises(ValidationError):
        FixtureMutationCase.model_validate(payload)


def test_every_case_is_one_declared_failure_and_preserves_all_accepted_bytes() -> None:
    sealed = _sealed()
    known_good_before = KNOWN_GOOD.read_bytes()
    formal_before = _formal_bytes()
    base_before = canonical_json_bytes(sealed.fixture.model_dump(mode="json"))

    results = [validate_mutation_case(sealed, case) for case in _cases()]

    assert [(result.case_id, result.actual_codes) for result in results] == [
        (case_id, (expected_code,)) for case_id, expected_code in sorted(EXPECTED_CODES.items())
    ]
    assert all(result.valid is True for result in results)
    assert KNOWN_GOOD.read_bytes() == known_good_before
    assert _formal_bytes() == formal_before
    assert canonical_json_bytes(sealed.fixture.model_dump(mode="json")) == base_before


@pytest.mark.parametrize(
    "case_id",
    [
        "direct-mastery-experience",
        "direct-mastery-title",
        "direct-mastery-repository",
        "direct-mastery-resume-skill-list",
        "direct-mastery-ontology",
    ],
)
def test_direct_source_cases_each_return_the_same_sole_stable_code(case_id: str) -> None:
    result = validate_mutation_case(_sealed(), next(case for case in _cases() if case.case_id == case_id))

    assert result.actual_codes == ("assessment.direct-source-forbidden",)


def test_suite_order_and_results_are_byte_identical_across_repeated_and_shuffled_inputs() -> None:
    sealed = _sealed()
    first = validate_mutation_suite(sealed, _cases())
    second = validate_mutation_suite(sealed, list(reversed(_cases())))

    assert first.model_dump(mode="json") == second.model_dump(mode="json")
    assert canonical_json_bytes(first.model_dump(mode="json")) == canonical_json_bytes(
        second.model_dump(mode="json")
    )
    assert [result.case_id for result in first.results] == sorted(EXPECTED_CODES)


def test_base_hash_mismatch_does_not_apply_a_mutation() -> None:
    sealed = _sealed()
    case = _cases()[0]
    mismatch = case.model_copy(update={"base_fixture_hash": "sha256:" + "0" * 64})
    before = canonical_json_bytes(sealed.fixture.model_dump(mode="json"))

    with pytest.raises(FixtureMutationError, match="base hash"):
        validate_mutation_case(sealed, mismatch)

    assert canonical_json_bytes(sealed.fixture.model_dump(mode="json")) == before


def test_mutation_operations_are_closed_not_general_json_patches() -> None:
    operation = _cases()[0].operations[0]
    payload = deepcopy(operation.model_dump(mode="json"))
    payload["path"] = "fixture.claims.0.responsibility"

    with pytest.raises(ValidationError):
        MutationOperation.model_validate(payload)
