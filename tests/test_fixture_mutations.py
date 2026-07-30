"""Regression coverage for sealed-STOA one-fault fixture mutations."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from copy import deepcopy
from pathlib import Path

import pytest
from pydantic import ValidationError

from career_evidence_graph import cli
from career_evidence_graph.domain.fixtures import (
    FixtureMutationCase,
    FixtureMutationError,
    FixtureMutationResult,
    FixtureMutationSuiteResult,
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
LAUNCHER = ROOT / "scripts" / "run_career_evidence.py"

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

    assert sorted((result.case_id, result.actual_codes) for result in results) == [
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
    case = next(case for case in _cases() if case.case_id == case_id)
    result = validate_mutation_case(_sealed(), case)

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


def _validate_suite_cli(known_good: Path, known_bad_dir: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            str(LAUNCHER),
            "fixture",
            "validate-suite",
            "--known-good",
            str(known_good),
            "--known-bad-dir",
            str(known_bad_dir),
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )


def test_fixture_validate_suite_cli_emits_the_stable_complete_json_report() -> None:
    completed = _validate_suite_cli(KNOWN_GOOD, KNOWN_BAD_DIR)

    assert completed.returncode == 0, completed.stderr
    report = json.loads(completed.stdout)
    assert report["valid"] is True
    assert report["base_fixture_hash"] == _sealed().confirmed_result_hash
    assert report["case_count"] == 16
    assert [result["case_id"] for result in report["results"]] == sorted(EXPECTED_CODES)
    assert all(result["valid"] is True for result in report["results"])
    assert all(result["actual_codes"] == [result["expected_code"]] for result in report["results"])


@pytest.mark.parametrize("fault", ["missing-good", "tampered-good", "base-mismatch", "extra-case"])
def test_fixture_validate_suite_cli_fails_closed_without_editing_fixtures(
    tmp_path: Path, fault: str
) -> None:
    copied_good = tmp_path / "known-good.json"
    copied_bad = tmp_path / "known-bad"
    shutil.copytree(KNOWN_BAD_DIR, copied_bad)
    if fault == "missing-good":
        known_good = tmp_path / "missing.json"
    elif fault == "tampered-good":
        shutil.copy2(KNOWN_GOOD, copied_good)
        copied_good.write_text('{"tampered":true}\n', encoding="utf-8")
        known_good = copied_good
    elif fault == "base-mismatch":
        case_path = copied_bad / "direct-mastery-title.json"
        case = json.loads(case_path.read_text(encoding="utf-8"))
        case["base_fixture_hash"] = "sha256:" + "0" * 64
        case_path.write_text(json.dumps(case), encoding="utf-8")
        known_good = KNOWN_GOOD
    else:
        shutil.copy2(copied_bad / "direct-mastery-title.json", copied_bad / "unexpected-case.json")
        known_good = KNOWN_GOOD

    known_good_before = KNOWN_GOOD.read_bytes()
    expected_tampered_good = copied_good.read_bytes() if copied_good.exists() else None
    expected_cases = {path.name: path.read_bytes() for path in sorted(copied_bad.glob("*.json"))}
    completed = _validate_suite_cli(known_good, copied_bad)

    assert completed.returncode == 2
    assert KNOWN_GOOD.read_bytes() == known_good_before
    if expected_tampered_good is not None:
        assert copied_good.read_bytes() == expected_tampered_good
    assert {
        path.name: path.read_bytes() for path in sorted(copied_bad.glob("*.json"))
    } == expected_cases


def test_fixture_validate_suite_cli_rejects_a_multi_error_result_without_writing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sealed = _sealed()
    before = KNOWN_GOOD.read_bytes()
    multi_error = FixtureMutationResult(
        valid=False,
        base_fixture_hash=sealed.confirmed_result_hash,
        case_id="dimension-confusion",
        mutation_kind="dimension-confusion",
        expected_code="assessment.dimension_confusion",
        actual_codes=("assessment.first", "assessment.second"),
    )
    monkeypatch.setattr(
        cli,
        "validate_mutation_suite",
        lambda sealed, cases: FixtureMutationSuiteResult(
            valid=False,
            base_fixture_hash=sealed.confirmed_result_hash,
            case_count=len(cases),
            results=(multi_error,),
        ),
    )

    assert (
        cli.main(
            [
                "fixture",
                "validate-suite",
                "--known-good",
                str(KNOWN_GOOD),
                "--known-bad-dir",
                str(KNOWN_BAD_DIR),
            ]
        )
        == 2
    )
    assert KNOWN_GOOD.read_bytes() == before
