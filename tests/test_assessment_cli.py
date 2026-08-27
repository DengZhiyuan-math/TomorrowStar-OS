"""Black-box calibration tracer coverage for the Phase 4 assessment seam."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from career_evidence_graph.assessment import run_assessment


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
