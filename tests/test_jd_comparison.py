"""Offline tracer for one schema-only JD comparison.

The packets in this file are deliberately synthetic contract probes, not Phase
5 JD fixtures or a description of any real role.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from career_evidence_graph.assessment import (
    AssessmentStore,
    build_assessment_run,
    decide_admission,
    load_policy,
    run_assessment,
)
from career_evidence_graph.domain.models import ContributionSkillAssessment
from career_evidence_graph.validation.hashing import sha256_digest

ROOT = Path(__file__).parents[1]
CORPUS = ROOT / "validation/calibration/phase-04/corpus.json"
POLICIES = ROOT / "validation/calibration/phase-04/policies.json"
LAUNCHER = ROOT / "scripts/run_career_evidence.py"


def _write_reviewed_user_truth(workspace: Path) -> None:
    """Persist one complete synthetic reviewed-user-truth assessment sidecar."""
    seed = run_assessment(
        workspace=workspace,
        corpus_path=CORPUS,
        policies_path=POLICIES,
        audit_id="audit-e2e",
        policy_version="policy-04-baseline-60",
    ).proposal
    payload = seed.model_dump(mode="json")
    payload["source_envelope"]["authority_label"] = "reviewed-user-truth"
    payload["assessment_status"] = "reviewed"
    payload["origin_status"] = "audit-verified"
    assessment = ContributionSkillAssessment.model_validate(payload)
    record = build_assessment_run(
        assessment,
        decide_admission(assessment, load_policy(POLICIES, "policy-04-baseline-60")),
    )
    AssessmentStore(workspace).replace("assessment-audit-e2e-04-baseline-60", record)


def _write_packet(path: Path) -> None:
    source = b"schema-only requirement"
    source_hash = sha256_digest(source)
    payload = {
        "schema_version": "accepted-jd-packet/v1",
        "packet_id": "packet-schema-only",
        "raw_source": {
            "schema_version": "jd-raw-source/v1",
            "source_id": "source-schema-only",
            "utf8_text": source.decode("utf-8"),
            "source_hash": source_hash,
        },
        "recorded_proposal": {
            "schema_version": "jd-recorded-proposal/v1",
            "proposal_id": "proposal-schema-only",
            "source_hash": source_hash,
            "raw_source_id": "source-schema-only",
        },
        "requirements": [
            {
                "schema_version": "jd-requirement/v1",
                "requirement_id": "requirement-schema-only",
                "source_span": {
                    "schema_version": "jd-source-span/v1",
                    "start_byte": 0,
                    "end_byte": len(source),
                    "text_hash": source_hash,
                },
                "skill_ids": ["skill.authorization-boundary-verification"],
                "decision_critical": True,
                "priority": "required",
                "core_hard": True,
            }
        ],
    }
    path.write_text(json.dumps(payload), encoding="utf-8")


def _write_policy(path: Path) -> None:
    path.write_text(
        json.dumps(
            {
                "schema_version": "jd-match-policy/v1",
                "policy_version": "schema-only-policy",
                "required_weight": 1,
                "preferred_weight": 1,
                "partially_supported_percent": 50,
                "customized_min_score": 70,
                "standard_min_score": 40,
                "missing_core_cap": 39,
                "evidence_strong_min_confidence": 80,
            }
        ),
        encoding="utf-8",
    )


def _run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(LAUNCHER), *args],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )


def test_schema_only_packet_reaches_checkout_cli_without_mutating_reviewed_graph(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    packet = tmp_path / "packet.json"
    policy = tmp_path / "policy.json"
    _write_reviewed_user_truth(workspace)
    _write_packet(packet)
    _write_policy(policy)

    before = AssessmentStore(workspace).path("assessment-audit-e2e-04-baseline-60").read_bytes()
    completed = _run(
        "jd",
        "analyze",
        "--workspace",
        str(workspace),
        "--packet",
        str(packet),
        "--policy",
        str(policy),
    )

    assert completed.returncode == 0, completed.stderr
    emitted = json.loads(completed.stdout)
    assert 0 <= emitted["score"] <= 100
    assert emitted["route"] in {"customized-resume", "standard-resume", "abandon"}
    assert emitted["judgments"][0]["status"] in {
        "supported",
        "partially-supported",
        "unsupported",
        "uncertain",
    }
    assert emitted["report"]["concise"]
    assert emitted["report"]["technical"]
    assert emitted["graph_hash_before"] == emitted["graph_hash_after"]
    assert (
        AssessmentStore(workspace).path("assessment-audit-e2e-04-baseline-60").read_bytes()
        == before
    )
