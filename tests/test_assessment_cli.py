"""Black-box calibration tracer coverage for the Phase 4 assessment seam."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest
from test_assessment_admission import _later_corpus

from career_evidence_graph.assessment import (
    AssessmentStorageError,
    AssessmentStore,
    build_assessment_run,
    decide_admission,
    load_policy,
    propose_assessment,
    run_assessment,
)
from career_evidence_graph.audit.store import AuditStore
from career_evidence_graph.domain.models import ContributionSkillAssessment

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


def test_aggregate_cli_emits_one_sorted_traceable_result_per_skill(tmp_path: Path) -> None:
    run = _run("assessment", "run", "--workspace", str(tmp_path))
    assert run.returncode == 0, run.stderr

    aggregated = _run("assessment", "aggregate", "--workspace", str(tmp_path))

    assert aggregated.returncode == 0, aggregated.stderr
    emitted = json.loads(aggregated.stdout)
    assert [result["skill_id"] for result in emitted["results"]] == [
        "skill.authorization-boundary-verification"
    ]
    result = emitted["results"][0]
    assert result["baseline_assessment_id"] == "assessment-authorization-boundary-verification"
    assert result["admitted_assessment_ids"] == ["assessment-authorization-boundary-verification"]
    assert result["policy_version"] == "policy-04-baseline-60"
    assert result["suppressed_duplicate_relationships"] == []


def test_aggregate_cli_labels_unadmitted_derived_records_as_calibration_only(
    tmp_path: Path,
) -> None:
    initial = run_assessment(
        workspace=tmp_path,
        corpus_path=CORPUS,
        policies_path=POLICIES,
        audit_id="audit-e2e",
        policy_version="policy-04-baseline-60",
    )
    payload = initial.proposal.model_dump(mode="json")
    payload["attribution_status"] = "unresolved"
    proposal = ContributionSkillAssessment.model_validate(payload)
    unadmitted = build_assessment_run(
        proposal,
        decide_admission(proposal, load_policy(POLICIES, "policy-04-baseline-60")),
    )
    AssessmentStore(tmp_path).replace("assessment-audit-e2e-04-baseline-60", unadmitted)

    aggregated = _run("assessment", "aggregate", "--workspace", str(tmp_path))

    assert aggregated.returncode == 0, aggregated.stderr
    excluded = json.loads(aggregated.stdout)["excluded"]
    assert excluded[0]["authority_label"] == "derived-counterfactual"
    assert excluded[0]["disposition"] == "calibration-only"


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


def test_review_cli_records_every_substantive_acknowledgment_and_hash(tmp_path: Path) -> None:
    run = _run("assessment", "run", "--workspace", str(tmp_path))
    assert run.returncode == 0, run.stderr
    initial = json.loads(run.stdout)
    accepted_path = tmp_path / "accepted-assessment.json"
    accepted_path.write_text(json.dumps(initial["proposal"]), encoding="utf-8")

    reviewed = _run(
        "assessment",
        "review",
        "--workspace",
        str(tmp_path),
        "--run-id",
        "assessment-audit-e2e-04-baseline-60",
        "--expected-effective-hash",
        initial["effective_assessment_hash"],
        "--reviewer",
        "reviewer-a",
        "--reason",
        "I checked attribution, the accepted anchor, and all three judgment bases.",
        "--assessment-json",
        str(accepted_path),
        "--attribution-checked",
        "--anchor-fit-checked",
        "--all-judgments-checked",
    )

    assert reviewed.returncode == 0, reviewed.stderr
    emitted = json.loads(reviewed.stdout)
    review = emitted["reviews"][-1]
    assert review["attribution_checked"] is True
    assert review["anchor_fit_checked"] is True
    assert review["all_judgments_checked"] is True
    assert review["before_effective_hash"] == initial["effective_assessment_hash"]
    assert review["after_effective_hash"] == emitted["effective_assessment_hash"]
    assert emitted["original_proposal_hash"] == initial["original_proposal_hash"]


def test_rerun_after_insufficient_review_is_byte_idempotent(tmp_path: Path) -> None:
    """A normal retry cannot replace a D-10 insufficient-basis decision."""
    initial = _run("assessment", "run", "--workspace", str(tmp_path))
    assert initial.returncode == 0, initial.stderr
    proposal_path = tmp_path / "accepted-assessment.json"
    proposal_path.write_text(json.dumps(json.loads(initial.stdout)["proposal"]), encoding="utf-8")

    reviewed = _run(
        "assessment",
        "review",
        "--workspace",
        str(tmp_path),
        "--run-id",
        "assessment-audit-e2e-04-baseline-60",
        "--expected-effective-hash",
        json.loads(initial.stdout)["effective_assessment_hash"],
        "--reviewer",
        "reviewer-a",
        "--reason",
        "The available evidence is insufficient to substantively confirm this assessment.",
        "--assessment-json",
        str(proposal_path),
        "--outcome",
        "insufficient-basis",
        "--attribution-checked",
        "--anchor-fit-checked",
        "--all-judgments-checked",
    )
    assert reviewed.returncode == 0, reviewed.stderr
    before = AssessmentStore(tmp_path).path("assessment-audit-e2e-04-baseline-60").read_bytes()

    rerun = _run("assessment", "run", "--workspace", str(tmp_path))

    assert rerun.returncode == 0, rerun.stderr
    assert rerun.stdout == reviewed.stdout
    assert (
        AssessmentStore(tmp_path).path("assessment-audit-e2e-04-baseline-60").read_bytes() == before
    )
    emitted = json.loads(rerun.stdout)
    assert emitted["admission"]["admission_status"] == "unverified-candidate"
    assert emitted["admission"]["reason_code"] == "insufficient-basis"
    assert emitted["result"] is None


def test_explicit_reassess_rejects_stale_hash_without_mutating_sidecar(tmp_path: Path) -> None:
    initial = _run("assessment", "run", "--workspace", str(tmp_path))
    assert initial.returncode == 0, initial.stderr
    proposal_path = tmp_path / "reassessment.json"
    proposal_path.write_text(json.dumps(json.loads(initial.stdout)["proposal"]), encoding="utf-8")
    sidecar = AssessmentStore(tmp_path).path("assessment-audit-e2e-04-baseline-60")
    before = sidecar.read_bytes()

    stale = _run(
        "assessment",
        "reassess",
        "--workspace",
        str(tmp_path),
        "--run-id",
        "assessment-audit-e2e-04-baseline-60",
        "--later-corpus",
        str(tmp_path / "missing-corpus.json"),
        "--source-audit-id",
        "audit-later-evidence",
        "--expected-current-version-hash",
        "sha256:" + "0" * 64,
        "--assessment-json",
        str(proposal_path),
    )

    assert stale.returncode == 2
    assert "assessment_workflow_error" in stale.stderr
    assert sidecar.read_bytes() == before


def test_reassess_cli_rejects_fabricated_audit_and_authority_without_mutation(
    tmp_path: Path,
) -> None:
    initial = _run("assessment", "run", "--workspace", str(tmp_path))
    assert initial.returncode == 0, initial.stderr
    later_corpus = _later_corpus(tmp_path)
    payload = json.loads(initial.stdout)["proposal"]
    payload["source_envelope"]["audit_id"] = "audit-fabricated"
    payload["source_envelope"]["authority_label"] = "reviewed-user-truth"
    payload["assessment_status"] = "reviewed"
    proposal_path = tmp_path / "fabricated-reassessment.json"
    proposal_path.write_text(json.dumps(payload), encoding="utf-8")
    sidecar = AssessmentStore(tmp_path).path("assessment-audit-e2e-04-baseline-60")
    before = sidecar.read_bytes()

    rejected = _run(
        "assessment",
        "reassess",
        "--workspace",
        str(tmp_path),
        "--run-id",
        "assessment-audit-e2e-04-baseline-60",
        "--later-corpus",
        str(later_corpus),
        "--source-audit-id",
        "audit-fabricated",
        "--expected-current-version-hash",
        json.loads(initial.stdout)["version_hash"],
        "--assessment-json",
        str(proposal_path),
    )

    assert rejected.returncode == 2
    assert "assessment_workflow_error" in rejected.stderr
    assert sidecar.read_bytes() == before


def test_reassess_cli_appends_a_materialized_later_audit_version(tmp_path: Path) -> None:
    initial = _run("assessment", "run", "--workspace", str(tmp_path))
    assert initial.returncode == 0, initial.stderr
    later_corpus = _later_corpus(tmp_path)
    later_proposal = propose_assessment(
        snapshot=AuditStore(tmp_path).read("audit-later-evidence"),
        corpus=json.loads(later_corpus.read_text(encoding="utf-8")),
        root=later_corpus.parents[3],
    )
    proposal_path = tmp_path / "later-reassessment.json"
    proposal_path.write_text(json.dumps(later_proposal.model_dump(mode="json")), encoding="utf-8")

    reassessed = _run(
        "assessment",
        "reassess",
        "--workspace",
        str(tmp_path),
        "--run-id",
        "assessment-audit-e2e-04-baseline-60",
        "--later-corpus",
        str(later_corpus),
        "--source-audit-id",
        "audit-later-evidence",
        "--expected-current-version-hash",
        json.loads(initial.stdout)["version_hash"],
        "--assessment-json",
        str(proposal_path),
    )

    assert reassessed.returncode == 0, reassessed.stderr
    emitted = json.loads(reassessed.stdout)
    assert len(emitted["versions"]) == 2
    assert emitted["versions"][0] == json.loads(initial.stdout)["versions"][0]
    assert emitted["versions"][-1]["source_audit_id"] == "audit-later-evidence"
    assert emitted["versions"][-1]["reviews"] == []
    assert emitted["proposal"]["source_envelope"]["authority_label"] == "derived-counterfactual"


@pytest.mark.parametrize(
    ("path", "value"),
    (
        (("source_envelope", "authority_label"), "reviewed-user-truth"),
        (("source_envelope", "audit_snapshot_hash"), "sha256:" + "0" * 64),
        (("origin_status",), "self-assessed-unverified"),
        (("assessment_status",), "reviewed"),
        (("id",), "assessment-caller-forged"),
        (("skill_id",), "skill.caller-forged"),
        (("contribution_id",), "contrib-stoa-content-privacy-integrity"),
        (("lineage", "contribution_id"), "contrib-stoa-content-privacy-integrity"),
    ),
)
def test_reassess_cli_rejects_each_caller_identity_permutation_without_mutation(
    tmp_path: Path, path: tuple[str, ...], value: str
) -> None:
    initial = _run("assessment", "run", "--workspace", str(tmp_path))
    assert initial.returncode == 0, initial.stderr
    later_corpus = _later_corpus(tmp_path)
    later_proposal = propose_assessment(
        snapshot=AuditStore(tmp_path).read("audit-later-evidence"),
        corpus=json.loads(later_corpus.read_text(encoding="utf-8")),
        root=later_corpus.parents[3],
    )
    payload = later_proposal.model_dump(mode="json")
    target = payload
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value
    proposal_path = tmp_path / "mutated-reassessment.json"
    proposal_path.write_text(json.dumps(payload), encoding="utf-8")
    sidecar = AssessmentStore(tmp_path).path("assessment-audit-e2e-04-baseline-60")
    before = sidecar.read_bytes()

    rejected = _run(
        "assessment",
        "reassess",
        "--workspace",
        str(tmp_path),
        "--run-id",
        "assessment-audit-e2e-04-baseline-60",
        "--later-corpus",
        str(later_corpus),
        "--source-audit-id",
        "audit-later-evidence",
        "--expected-current-version-hash",
        json.loads(initial.stdout)["version_hash"],
        "--assessment-json",
        str(proposal_path),
    )

    assert rejected.returncode == 2
    assert "assessment_workflow_error" in rejected.stderr
    assert sidecar.read_bytes() == before


def test_calibration_cli_compares_activates_and_reopens_redacted_history(tmp_path: Path) -> None:
    compared = _run("assessment", "compare", "--workspace", str(tmp_path))
    assert compared.returncode == 0, compared.stderr
    comparison = json.loads(compared.stdout)
    assert comparison["active_policy_version"] is None

    activated = _run(
        "assessment",
        "activate",
        "--workspace",
        str(tmp_path),
        "--policy-version",
        "policy-04-conservative-70",
        "--policy-hash",
        comparison["candidate_policy_hash"],
        "--result-hash",
        comparison["candidate_result_hash"],
        "--comparison-hash",
        comparison["comparison_hash"],
        "--reviewer",
        "zhdeng",
        "--reason",
        "Use a conservative initial calibration: boundary cases remain pending human confirmation.",
        "--limitation",
        (
            "This is an initial calibration policy and must be re-evaluated after additional "
            "real audited samples accumulate."
        ),
        "--prior-policy-version",
        "null",
        "--prior-result-hash",
        "null",
        "--expected-active-pointer",
        "absent",
    )
    assert activated.returncode == 0, activated.stderr
    activation = json.loads(activated.stdout)
    assert activation["activated_policy_version"] == "policy-04-conservative-70"

    history = _run("assessment", "history", "--workspace", str(tmp_path))
    assert history.returncode == 0, history.stderr
    emitted = json.loads(history.stdout)
    assert emitted["active_pointer"] == activation["activation_hash"]
    assert emitted["activations"] == [activation]
    assert "RAW_INTERVIEW_SENTINEL" not in history.stdout
