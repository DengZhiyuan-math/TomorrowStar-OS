"""Offline tracer for one schema-only JD comparison.

The packets in this file are deliberately synthetic contract probes, not Phase
5 JD fixtures or a description of any real role.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from career_evidence_graph import jd as jd_module
from career_evidence_graph.assessment import (
    AssessmentStore,
    build_assessment_run,
    decide_admission,
    load_policy,
    review_assessment,
    run_assessment,
)
from career_evidence_graph.domain.models import (
    AcceptedJDPacket,
    ContributionSkillAssessment,
    JDMatchPolicy,
)
from career_evidence_graph.jd import JDIntakeStore, compare_accepted_jd, prepare_jd_intake
from career_evidence_graph.validation.hashing import canonical_json_bytes, sha256_digest

ROOT = Path(__file__).parents[1]
CORPUS = ROOT / "validation/calibration/phase-04/corpus-review-safe-v1.json"
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
    payload["origin_status"] = "audit-verified"
    assessment = ContributionSkillAssessment.model_validate(payload)
    policy = load_policy(POLICIES, "policy-04-baseline-60")
    record = build_assessment_run(
        assessment,
        decide_admission(assessment, policy),
    )
    record = review_assessment(
        record,
        policy=policy,
        expected_effective_hash=record.effective_assessment_hash,
        reviewer_id="synthetic-reviewer",
        review_reason="Checked attribution, anchor fit, and all judgment bases.",
        attribution_checked=True,
        anchor_fit_checked=True,
        all_judgments_checked=True,
        accepted_assessment=assessment,
    )
    AssessmentStore(workspace).replace("assessment-audit-e2e-04-baseline-60", record)


def _write_packet(path: Path) -> None:
    packet = _packet_with_requirements(
        [{"requirement_id": "requirement-schema-only", "core_hard": True}]
    )
    path.write_text(packet.model_dump_json(), encoding="utf-8")


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
    proposal = json.dumps(
        {
            "source_hash": source_hash,
            "raw_source_id": "source-schema-only",
            "proposal_kind": "schema-only-contract-probe",
            "requirements": packet_requirements,
        },
        sort_keys=True,
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


def _accept_packet(workspace: Path, packet_path: Path) -> None:
    packet = AcceptedJDPacket.model_validate_json(packet_path.read_bytes())
    intake = prepare_jd_intake(
        packet.raw_source.utf8_text.encode("utf-8"),
        packet.raw_source.source_id,
        packet_path.read_bytes(),
    )
    store = JDIntakeStore(workspace)
    prepared = store.prepare(intake)
    store.accept(prepared["source_hash"], prepared["proposal_hash"])


def test_schema_only_packet_reaches_checkout_cli_without_mutating_reviewed_graph(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    packet = tmp_path / "packet.json"
    policy = tmp_path / "policy.json"
    _write_reviewed_user_truth(workspace)
    _write_packet(packet)
    _write_policy(policy)
    _accept_packet(workspace, packet)

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


@pytest.mark.parametrize("state", ("unprepared", "prepared", "other-workspace"))
def test_analysis_requires_acceptance_of_exact_packet_in_its_workspace(
    tmp_path: Path, state: str
) -> None:
    workspace = tmp_path / "workspace"
    packet = tmp_path / "packet.json"
    policy = tmp_path / "policy.json"
    _write_reviewed_user_truth(workspace)
    _write_packet(packet)
    _write_policy(policy)
    if state == "prepared":
        value = AcceptedJDPacket.model_validate_json(packet.read_bytes())
        JDIntakeStore(workspace).prepare(
            prepare_jd_intake(
                value.raw_source.utf8_text.encode("utf-8"),
                value.raw_source.source_id,
                packet.read_bytes(),
            )
        )
    elif state == "other-workspace":
        other_workspace = tmp_path / "other-workspace"
        other_workspace.mkdir()
        _accept_packet(other_workspace, packet)
    before = {str(path): path.read_bytes() for path in workspace.rglob("*") if path.is_file()}

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

    assert completed.returncode == 2
    assert completed.stdout == ""
    assert json.loads(completed.stderr)["error"] == "jd-accepted-missing"
    assert {
        str(path): path.read_bytes() for path in workspace.rglob("*") if path.is_file()
    } == before


@pytest.mark.parametrize(
    ("change", "error"),
    (
        ("missing-manifest", "jd-accepted-invalid"),
        ("manifest-list", "jd-accepted-invalid"),
        ("manifest-not-accepted", "jd-accepted-invalid"),
        ("manifest-source-hash", "jd-accepted-invalid"),
        ("manifest-proposal-hash", "jd-accepted-invalid"),
        ("manifest-packet-id", "jd-accepted-invalid"),
        ("manifest-schema", "jd-accepted-invalid"),
        ("stored-packet", "jd-accepted-invalid"),
        ("input-packet-id", "jd-accepted-packet-mismatch"),
        ("input-proposal-id", "jd-accepted-packet-mismatch"),
        ("manifest-symlink", "jd-accepted-unsafe"),
        ("accepted-parent-symlink", "jd-private-root-unsafe"),
    ),
)
def test_analysis_reopens_and_checks_the_complete_acceptance_record(
    tmp_path: Path, change: str, error: str
) -> None:
    workspace = tmp_path / "workspace"
    packet = tmp_path / "packet.json"
    policy = tmp_path / "policy.json"
    _write_reviewed_user_truth(workspace)
    _write_packet(packet)
    _write_policy(policy)
    _accept_packet(workspace, packet)
    accepted_root = JDIntakeStore(workspace).root / "accepted"
    manifest_path = next(accepted_root.glob("*/manifest.json"))
    if change == "missing-manifest":
        manifest_path.unlink()
    elif change == "manifest-list":
        manifest_path.write_text("[]")
    elif change.startswith("manifest-") and change != "manifest-symlink":
        field, value = {
            "manifest-not-accepted": ("accepted", False),
            "manifest-source-hash": ("source_hash", sha256_digest(b"different source")),
            "manifest-proposal-hash": ("proposal_hash", sha256_digest(b"different proposal")),
            "manifest-packet-id": ("packet_id", "packet-other"),
            "manifest-schema": ("schema_version", "jd-prepared-intake/v1"),
        }[change]
        manifest = json.loads(manifest_path.read_bytes())
        manifest[field] = value
        manifest_path.write_text(json.dumps(manifest))
    elif change == "stored-packet":
        stored_packet_path = manifest_path.parent / "packet.json"
        stored_packet = json.loads(stored_packet_path.read_bytes())
        stored_packet["requirements"][0]["minimum_mastery"] = 99
        stored_packet_path.write_text(json.dumps(stored_packet))
    elif change in {"input-packet-id", "input-proposal-id"}:
        payload = json.loads(packet.read_bytes())
        if change == "input-packet-id":
            payload["packet_id"] = "packet-not-accepted"
        else:
            payload["recorded_proposal"]["proposal_id"] = "proposal-not-accepted"
        packet.write_text(json.dumps(payload))
    elif change == "manifest-symlink":
        external = tmp_path / "manifest-copy.json"
        external.write_bytes(manifest_path.read_bytes())
        manifest_path.unlink()
        manifest_path.symlink_to(external)
    else:
        external = tmp_path / "accepted-copy"
        accepted_root.rename(external)
        accepted_root.symlink_to(external, target_is_directory=True)

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

    assert completed.returncode == 2
    assert completed.stdout == ""
    assert json.loads(completed.stderr)["error"] == error


def test_analysis_selects_only_the_exact_confirmed_interpretation(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    original_path = tmp_path / "original.json"
    corrected_path = tmp_path / "corrected.json"
    policy = tmp_path / "policy.json"
    _write_reviewed_user_truth(workspace)
    original = _packet_with_requirements([{"minimum_mastery": 1}])
    corrected = _packet_with_requirements([{"minimum_mastery": 99}])
    original_path.write_text(original.model_dump_json())
    corrected_path.write_text(corrected.model_dump_json())
    _write_policy(policy)
    _accept_packet(workspace, original_path)
    store = JDIntakeStore(workspace)
    prepared = store.prepare(
        prepare_jd_intake(
            corrected.raw_source.utf8_text.encode("utf-8"),
            corrected.raw_source.source_id,
            corrected_path.read_bytes(),
        )
    )
    arguments = ("jd", "analyze", "--workspace", str(workspace), "--policy", str(policy))

    unaccepted = _run(*arguments, "--packet", str(corrected_path))
    assert unaccepted.returncode == 2
    assert unaccepted.stdout == ""
    assert json.loads(unaccepted.stderr)["error"] == "jd-accepted-missing"
    store.accept(prepared["source_hash"], prepared["proposal_hash"])
    original_result = _run(*arguments, "--packet", str(original_path))
    corrected_result = _run(*arguments, "--packet", str(corrected_path))

    assert original_result.returncode == corrected_result.returncode == 0
    assert json.loads(original_result.stdout)["judgments"][0]["status"] == "supported"
    assert json.loads(corrected_result.stdout)["judgments"][0]["status"] == "partially-supported"


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

    linked_group = compare_accepted_jd(
        _packet_with_requirements(
            [
                {
                    "core_hard": True,
                    "evidence_strong_eligible": True,
                    "linked_requirement_group_id": "group-schema-only",
                    "minimum_mastery": 1,
                },
                {
                    "linked_requirement_group_id": "group-schema-only",
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
    assert linked_group.route_reason == "evidence-strong-match"


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


def test_missing_evidence_stays_distinct_from_uncertainty(tmp_path: Path, monkeypatch) -> None:
    workspace = tmp_path / "workspace"
    _write_reviewed_user_truth(workspace)
    records, results, _graph_hash = jd_module.load_reviewed_user_graph(workspace)
    source_envelope = records[0].proposal.source_envelope.model_copy(update={"evidence_ids": ()})
    record = records[0].model_copy(
        update={
            "proposal": records[0].proposal.model_copy(update={"source_envelope": source_envelope})
        }
    )
    result = results[0].model_copy(update={"source_envelope": source_envelope})
    graph_hash = sha256_digest(canonical_json_bytes(jd_module._graph_payload((record,), (result,))))
    monkeypatch.setattr(
        jd_module, "load_reviewed_user_graph", lambda _workspace: ((record,), (result,), graph_hash)
    )

    analysis = compare_accepted_jd(
        _packet_with_requirements([{"minimum_mastery": 1}]), workspace, _policy()
    )

    assert analysis.judgments[0].status == "uncertain"
    assert analysis.gaps[0].kind == "missing-evidence"


@pytest.mark.parametrize(
    ("field", "expectation", "gap_kind"),
    (
        ("stated_strength", "Expert knowledge is required.", "missing-evidence"),
        ("responsibility_expectation", "Own the release decision.", "missing-evidence"),
        ("context_expectation", "An unverified production context.", "context-mismatch"),
        ("seniority_expectation", "Senior engineer.", "missing-evidence"),
        ("duration_expectation", "Five years of verified practice.", "missing-evidence"),
        ("experience_expectation", "Two completed migrations.", "missing-evidence"),
    ),
)
def test_unverified_conditions_cannot_be_supported_by_mastery_alone(
    tmp_path: Path, field: str, expectation: str, gap_kind: str
) -> None:
    workspace = tmp_path / "workspace"
    _write_reviewed_user_truth(workspace)
    packet = _packet_with_requirements(
        [
            {
                "minimum_mastery": 1,
                field: expectation,
                "core_hard": True,
                "evidence_strong_eligible": True,
            }
        ]
    )
    result = compare_accepted_jd(packet, workspace, _policy())

    assert result.judgments[0].status == "uncertain"
    assert result.gaps[0].kind == gap_kind
    assert expectation in result.gaps[0].detail
    assert result.core_cap_applied
    assert result.route_trigger != "evidence-strong-match"
    assert result.graph_hash_before == result.graph_hash_after


def test_verified_context_can_support_the_requirement(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    _write_reviewed_user_truth(workspace)
    _records, results, _graph_hash = jd_module.load_reviewed_user_graph(workspace)
    context = results[0].supporting_contexts[0]

    result = compare_accepted_jd(
        _packet_with_requirements([{"minimum_mastery": 1, "context_expectation": context}]),
        workspace,
        _policy(),
    )

    assert result.judgments[0].status == "supported"
    assert result.gaps == ()
    assert result.graph_hash_before == result.graph_hash_after


def test_each_unverified_condition_remains_in_the_report(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    _write_reviewed_user_truth(workspace)
    result = compare_accepted_jd(
        _packet_with_requirements(
            [
                {
                    "minimum_mastery": 1,
                    "duration_expectation": "Five verified years.",
                    "responsibility_expectation": "Own the release decision.",
                }
            ]
        ),
        workspace,
        _policy(),
    )

    assert result.judgments[0].status == "uncertain"
    assert "Five verified years." in result.gaps[0].detail
    assert "Own the release decision." in result.gaps[0].detail
