"""Black-box calibration tracer coverage for the Phase 4 assessment seam."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from career_evidence_graph.assessment import AssessmentStorageError, AssessmentStore, run_assessment

ROOT = Path(__file__).parents[1]
CORPUS = ROOT / "validation/calibration/phase-04/corpus.json"
POLICIES = ROOT / "validation/calibration/phase-04/policies.json"
LAUNCHER = ROOT / "scripts/run_career_evidence.py"


def _run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(LAUNCHER), *args],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )


def test_tracer_requires_the_checked_in_calibration_authorities(tmp_path: Path) -> None:
    """The first offline case is explicitly synthetic, never reviewed user truth."""
    result = run_assessment(
        workspace=tmp_path,
        corpus_path=CORPUS,
        policies_path=POLICIES,
        audit_id="audit-e2e",
        policy_version="policy-04-baseline-60",
    )

    assert result.result.source_envelope.authority_label == "derived-counterfactual"
    assert result.result.source_envelope.audit_id == "audit-e2e"
    assert result.result.policy_version == "policy-04-baseline-60"
    assert result.result.mastery == 60
    assert result.admission.admission_status == "admitted"


def test_tracer_cli_persists_explicitly_synthetic_calibration_result(tmp_path: Path) -> None:
    completed = _run("assessment", "run", "--workspace", str(tmp_path))
    assert completed.returncode == 0, completed.stderr
    emitted = json.loads(completed.stdout)
    assert emitted["result"]["authority_label"] == "derived-counterfactual"
    assert emitted["result"]["mastery"] == 60
    assert emitted["result"]["admitted_assessment_ids"] == [
        "assessment-authorization-boundary-verification"
    ]

    reopened = _run(
        "assessment",
        "inspect",
        "--workspace",
        str(tmp_path),
        "--run-id",
        "assessment-audit-e2e-04-baseline-60",
    )
    assert reopened.returncode == 0, reopened.stderr
    assert json.loads(reopened.stdout) == emitted


def test_inspect_rejects_cross_linked_records_without_leaking_a_raw_answer(tmp_path: Path) -> None:
    """A sidecar contains one proposal chain, never a hidden second assessment."""
    record = run_assessment(
        workspace=tmp_path,
        corpus_path=CORPUS,
        policies_path=POLICIES,
        audit_id="audit-e2e",
        policy_version="policy-04-baseline-60",
    )
    run_id = "assessment-audit-e2e-04-baseline-60"
    store = AssessmentStore(tmp_path)
    payload = json.loads(store.path(run_id).read_text(encoding="utf-8"))
    payload["result"]["admitted_assessment_ids"].append("assessment-unrelated")
    payload["proposal"]["context"] = "RAW_INTERVIEW_SENTINEL"
    store.path(run_id).write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(AssessmentStorageError, match="corrupt"):
        store.read(run_id)

    inspected = _run("assessment", "inspect", "--workspace", str(tmp_path), "--run-id", run_id)
    assert inspected.returncode == 2
    assert "assessment_storage_error" in inspected.stderr
    assert "RAW_INTERVIEW_SENTINEL" not in inspected.stderr
    assert "RAW_INTERVIEW_SENTINEL" not in inspected.stdout
    assert record.result.baseline_assessment_id not in {"assessment-unrelated"}
