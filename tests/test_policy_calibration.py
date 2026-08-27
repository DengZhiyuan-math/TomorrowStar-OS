"""Deterministic Phase 4 policy-calibration contracts."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from career_evidence_graph.assessment import (
    AssessmentWorkflowError,
    compare_policy_runs,
    load_policy_history,
    run_calibration_policy,
)
from career_evidence_graph.validation.hashing import sha256_digest

ROOT = Path(__file__).parents[1]
CORPUS = ROOT / "validation/calibration/phase-04/corpus.json"
POLICIES = ROOT / "validation/calibration/phase-04/policies.json"


def test_corpus_expansion_preserves_the_sole_real_audit_and_labels_derivations() -> None:
    payload = json.loads(CORPUS.read_text(encoding="utf-8"))

    assert payload["audit_id"] == "audit-e2e"
    assert payload["candidate"]["authority_label"] == "derived-counterfactual"
    assert payload["fixture_hash"] == (
        "sha256:5b9cf494e08e97384168ccfa9d4b134ff35bb48d85038de82fcb6a148ce8011d"
    )
    assert sha256_digest((ROOT / payload["fixture_path"]).read_bytes()) == payload["fixture_hash"]
    assert (
        sha256_digest((ROOT / payload["source_manifest_path"]).read_bytes())
        == payload["source_manifest_hash"]
    )
    cases = payload["calibration_cases"]
    assert {case["coverage"] for case in cases} >= {
        "high-centrality-low-mastery",
        "low-centrality-high-mastery",
        "high-mastery-low-confidence",
        "cross-skill-evidence-reuse",
        "same-skill-duplicate",
        "incidental-volume",
        "self-rating",
        "assisted-responsibility",
        "allowed-promotion",
        "denied-promotion",
        "threshold-equality",
        "reviewer-disagreement",
    }
    assert all(
        case["authority_label"] in {"derived-counterfactual", "synthetic-negative"}
        for case in cases
    )
    assert all(case["parent_case_id"] == "audit-e2e" for case in cases)
    assert all(case["simulated_calibration_input"] is True for case in cases)


def test_candidate_contract_preserves_exact_integer_boundaries_and_d10_deferrals() -> None:
    policies = json.loads(POLICIES.read_text(encoding="utf-8"))
    by_version = {policy["policy_version"]: policy for policy in policies["policies"]}

    assert set(by_version) == {"policy-04-baseline-60", "policy-04-conservative-70"}
    assert all(policy["high_mastery_min"] == 70 for policy in by_version.values())
    assert by_version["policy-04-baseline-60"]["strict_confidence_min"] == 60
    assert by_version["policy-04-conservative-70"]["strict_confidence_min"] == 70
    assert "exact inclusive integers" in policies["integer_semantics"]
    assert "remain deferred" in policies["d10_overrides"]


def test_candidates_use_identical_input_and_compare_without_activation(tmp_path: Path) -> None:
    baseline = run_calibration_policy(
        workspace=tmp_path,
        corpus_path=CORPUS,
        policies_path=POLICIES,
        policy_version="policy-04-baseline-60",
    )
    conservative = run_calibration_policy(
        workspace=tmp_path,
        corpus_path=CORPUS,
        policies_path=POLICIES,
        policy_version="policy-04-conservative-70",
    )
    comparison = compare_policy_runs(
        workspace=tmp_path,
        baseline=baseline,
        candidate=conservative,
    )

    assert baseline.input_hashes == conservative.input_hashes
    assert baseline.policy_hash != conservative.policy_hash
    assert baseline.result_hash != conservative.result_hash
    assert comparison.input_hashes == baseline.input_hashes
    assert comparison.comparison_hash.startswith("sha256:")
    assert comparison.active_policy_version is None
    assert comparison.run_variance == 0
    assert set(comparison.reviewer_disagreements) == {
        "case-high-mastery-low-confidence",
        "case-reviewer-disagreement",
    }
    assert "false-deferral:case-threshold-equality" in comparison.regressions
    assert any(
        delta.case_id == "case-threshold-equality"
        and delta.admission_change
        and delta.baseline_admission == "admitted"
        and delta.candidate_admission == "pending-confirmation"
        for delta in comparison.skill_deltas
    )
    assert all(
        item.admission_status == "pending-confirmation"
        for item in baseline.case_results
        if item.case_id in {"case-self-rating", "case-assisted-responsibility"}
    )
    assert load_policy_history(tmp_path).active_pointer is None


def test_runs_are_immutable_and_same_policy_replay_is_identical(tmp_path: Path) -> None:
    first = run_calibration_policy(
        workspace=tmp_path,
        corpus_path=CORPUS,
        policies_path=POLICIES,
        policy_version="policy-04-baseline-60",
    )
    second = run_calibration_policy(
        workspace=tmp_path,
        corpus_path=CORPUS,
        policies_path=POLICIES,
        policy_version="policy-04-baseline-60",
    )

    assert first.result_hash == second.result_hash
    history = load_policy_history(tmp_path)
    assert [item.result_hash for item in history.runs] == [first.result_hash]
    with pytest.raises(AssessmentWorkflowError, match="input hashes"):
        compare_policy_runs(
            workspace=tmp_path,
            baseline=first,
            candidate=first.model_copy(update={"input_hashes": ("sha256:" + "0" * 64,)}),
        )
