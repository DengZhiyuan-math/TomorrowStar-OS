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
from career_evidence_graph.domain.models import (
    AcceptedJDPacket,
    ContributionSkillAssessment,
    JDMatchPolicy,
)
from career_evidence_graph.jd import compare_accepted_jd
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
            "proposal_json": json.dumps(
                {
                    "source_hash": source_hash,
                    "raw_source_id": "source-schema-only",
                    "proposal_kind": "schema-only-contract-probe",
                },
                sort_keys=True,
            ),
            "proposal_hash": sha256_digest(
                json.dumps(
                    {
                        "source_hash": source_hash,
                        "raw_source_id": "source-schema-only",
                        "proposal_kind": "schema-only-contract-probe",
                    },
                    sort_keys=True,
                ).encode("utf-8")
            ),
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


def _packet_with_requirements(requirements: list[dict[str, object]]) -> AcceptedJDPacket:
    """Build a content-free accepted packet with one reconstructable span per probe."""
    source = b"probe-a|probe-b|probe-c|probe-d"
    source_hash = sha256_digest(source)
    proposal = json.dumps(
        {
            "source_hash": source_hash,
            "raw_source_id": "source-schema-only",
            "proposal_kind": "schema-only-contract-probe",
        },
        sort_keys=True,
    )
    spans = ((0, 7), (8, 15), (16, 23), (24, len(source)))
    packet_requirements: list[dict[str, object]] = []
    for index, requirement in enumerate(requirements):
        start_byte, end_byte = spans[index]
        packet_requirements.append(
            {
                "schema_version": "jd-requirement/v1",
                "requirement_id": f"requirement-{index + 1}",
                "source_span": {
                    "schema_version": "jd-source-span/v1",
                    "start_byte": start_byte,
                    "end_byte": end_byte,
                    "text_hash": sha256_digest(source[start_byte:end_byte]),
                },
                "decision_critical": True,
                "priority": "required",
                "skill_ids": ["skill.authorization-boundary-verification"],
                **requirement,
            }
        )
    return AcceptedJDPacket.model_validate(
        {
            "schema_version": "accepted-jd-packet/v1",
            "packet_id": "packet-schema-only-expanded",
            "raw_source": {
                "schema_version": "jd-raw-source/v1",
                "source_id": "source-schema-only",
                "utf8_text": source.decode("utf-8"),
                "source_hash": source_hash,
            },
            "recorded_proposal": {
                "schema_version": "jd-recorded-proposal/v1",
                "proposal_id": "proposal-schema-only-expanded",
                "source_hash": source_hash,
                "raw_source_id": "source-schema-only",
                "proposal_json": proposal,
                "proposal_hash": sha256_digest(proposal.encode("utf-8")),
            },
            "requirements": packet_requirements,
        }
    )


def _policy(**overrides: int) -> JDMatchPolicy:
    values = {
        "schema_version": "jd-match-policy/v1",
        "policy_version": "schema-only-policy-expanded",
        "required_weight": 1,
        "preferred_weight": 1,
        "partially_supported_percent": 50,
        "customized_min_score": 70,
        "standard_min_score": 40,
        "missing_core_cap": 39,
        "evidence_strong_min_confidence": 0,
    }
    values.update(overrides)
    return JDMatchPolicy.model_validate(values)


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


def test_scoring_uses_inclusive_thresholds_and_core_cap_without_mutating_graph(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    _write_reviewed_user_truth(workspace)
    threshold_packet = _packet_with_requirements(
        [
            {"minimum_mastery": 1},
            {
                "priority": "preferred",
                "skill_ids": ["skill.unsupported-schema-only"],
            },
        ]
    )

    at_customized_boundary = compare_accepted_jd(
        threshold_packet,
        workspace,
        _policy(required_weight=7, preferred_weight=3),
    )
    assert at_customized_boundary.raw_score == 70
    assert at_customized_boundary.route == "customized-resume"

    at_standard_boundary = compare_accepted_jd(
        threshold_packet,
        workspace,
        _policy(required_weight=2, preferred_weight=3),
    )
    assert at_standard_boundary.raw_score == 40
    assert at_standard_boundary.route == "standard-resume"

    capped = compare_accepted_jd(
        _packet_with_requirements(
                [
                    {
                        "core_hard": True,
                        "skill_ids": ["skill.unsupported-schema-only"],
                    },
                {"priority": "preferred", "minimum_mastery": 1},
            ]
        ),
        workspace,
        _policy(required_weight=1, preferred_weight=9),
    )
    assert capped.raw_score == 90
    assert capped.score == 39
    assert capped.route == "abandon"
    assert capped.graph_hash_before == capped.graph_hash_after


def test_evidence_strong_exception_requires_every_ordered_skill_constituent(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    _write_reviewed_user_truth(workspace)

    positive = compare_accepted_jd(
        _packet_with_requirements(
            [
                {
                    "core_hard": True,
                    "evidence_strong_eligible": True,
                    "minimum_mastery": 1,
                },
                {
                    "priority": "preferred",
                    "skill_ids": ["skill.unsupported-schema-only"],
                },
            ]
        ),
        workspace,
        _policy(),
    )
    assert positive.raw_score == 50
    assert positive.ordinary_route == "standard-resume"
    assert positive.route == "customized-resume"
    assert positive.route_reason == "evidence-strong-match"

    negative = compare_accepted_jd(
        _packet_with_requirements(
            [
                {
                    "core_hard": True,
                    "evidence_strong_eligible": True,
                    "skill_ids": [
                        "skill.authorization-boundary-verification",
                        "skill.unsupported-schema-only",
                    ],
                    "minimum_mastery": 1,
                }
            ]
        ),
        workspace,
        _policy(),
    )
    assert negative.route == "abandon"
    assert negative.route_reason != "evidence-strong-match"


def test_report_projects_typed_gaps_and_canonical_evidence_selection(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    _write_reviewed_user_truth(workspace)
    result = compare_accepted_jd(
        _packet_with_requirements(
            [
                {"minimum_mastery": 100, "context_expectation": "schema-only-context-mismatch"},
                {"minimum_mastery": 100},
                {"skill_ids": ["skill.unsupported-schema-only"]},
            ]
        ),
        workspace,
        _policy(),
    )

    assert {gap.kind for gap in result.gaps} >= {
        "missing-capability",
        "context-mismatch",
        "uncertainty",
    }
    assert result.report.header_score == result.score
    assert result.report.header_route == result.route
    assert result.report.decision_critical_requirement_ids == (
        "requirement-1",
        "requirement-2",
        "requirement-3",
    )
    assert result.report.expanded_requirement_ids == result.report.decision_critical_requirement_ids
    assert result.report.technical.startswith("Read-only comparison")
