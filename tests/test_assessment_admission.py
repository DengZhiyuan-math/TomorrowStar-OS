"""Fail-closed admission contracts for contribution-Skill proposals."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from career_evidence_graph.assessment import (
    AssessmentRun,
    AssessmentStore,
    AssessmentWorkflowError,
    aggregate_skill,
    build_assessment_run,
    decide_admission,
    propose_assessment,
    reassess_from_new_evidence,
    review_assessment,
    run_assessment,
)
from career_evidence_graph.audit.decision import RecordedDecisionPort
from career_evidence_graph.audit.models import (
    AuditAction,
    AuditConclusion,
    AuditSnapshot,
    BoundaryDecision,
    ProbePlan,
    conclusion_lineage_digest,
    effective_conclusion_digest,
)
from career_evidence_graph.audit.store import AuditStore
from career_evidence_graph.audit.workflow import start_audit, transition_audit
from career_evidence_graph.domain.fixtures import resolve_checkpoint_summary
from career_evidence_graph.domain.models import (
    MASTERY_ANCHORS,
    AggregationPolicy,
    AssessmentAdmissionStatus,
    ContributionSkillAssessment,
)
from career_evidence_graph.validation.hashing import canonical_json_bytes, sha256_digest

ROOT = Path(__file__).parents[1]
CORPUS = ROOT / "validation/calibration/phase-04/corpus.json"
POLICIES = ROOT / "validation/calibration/phase-04/policies.json"
LAUNCHER = ROOT / "scripts/run_career_evidence.py"


def _proposal(tmp_path: Path, **changes: object) -> ContributionSkillAssessment:
    """Build a valid sealed tracer proposal, then validate a complete replacement."""
    record = run_assessment(
        workspace=tmp_path,
        corpus_path=CORPUS,
        policies_path=POLICIES,
        audit_id="audit-e2e",
        policy_version="policy-04-baseline-60",
    )
    payload = record.proposal.model_dump(mode="json")
    payload.update(changes)
    return ContributionSkillAssessment.model_validate(payload)


def _policy(version: str, confidence: int) -> AggregationPolicy:
    return AggregationPolicy(
        policy_version=version,
        high_mastery_min=70,
        strict_confidence_min=confidence,
        activation_status="candidate",
        notice="Fixture policy; calibration activation remains unresolved.",
    )


def _anchor_payload(mastery: int) -> dict[str, object]:
    anchor = next(
        item
        for item in MASTERY_ANCHORS
        if mastery in range(item.inclusive_range[0], item.inclusive_range[1] + 1)
    )
    return {
        "anchor_id": anchor.anchor_id,
        "anchor_range": list(anchor.inclusive_range),
        "anchor_text": anchor.capability_text,
        "anchor_basis": "The fixture independently establishes the stated capability band.",
        "exact_score_basis": "The integer fixture score remains inside the accepted anchor.",
        "next_anchor_not_established": "The next capability anchor remains unestablished.",
    }


def _later_corpus(workspace: Path) -> Path:
    """Create a real, completed later audit in the production corpus layout."""
    root = workspace / "later-root"
    corpus_path = root / "validation/calibration/phase-04/later-corpus.json"
    corpus_path.parent.mkdir(parents=True)
    fixture = root / "validation/fixtures/stoa/v1/known-good.json"
    manifest = root / "validation/fixtures/stoa/v1/source-manifest.json"
    shutil.copytree(ROOT / "validation/fixtures/stoa/v1", fixture.parent)
    checkpoint_summary = Path(
        ".planning/phases/02-domain-contracts-stoa-fixture-and-deterministic-invariants/"
        "02-04-SUMMARY.md"
    )
    (root / checkpoint_summary).parent.mkdir(parents=True)
    shutil.copy2(resolve_checkpoint_summary(ROOT), root / checkpoint_summary)
    corpus = json.loads(CORPUS.read_text(encoding="utf-8"))
    corpus["audit_id"] = "audit-later-evidence"
    journey = corpus["audit_journey"]
    plan = ProbePlan.model_validate(journey["probe_plan"])
    decisions = tuple(BoundaryDecision.model_validate(item) for item in journey["decisions"])
    port = RecordedDecisionPort(
        plan=plan,
        decisions={(item.question_id, item.answer): item for item in decisions},
    )
    snapshot = start_audit(
        workspace=workspace,
        fixture_path=fixture,
        manifest_path=manifest,
        contribution_id=corpus["contribution_id"],
        audit_id=corpus["audit_id"],
        decision_port=port,
    )
    for action_value in journey["actions"]:
        snapshot = transition_audit(
            snapshot, AuditAction.model_validate(action_value), decision_port=port
        )
        AuditStore(workspace).replace(snapshot)
    corpus["audit_snapshot_hash"] = sha256_digest(canonical_json_bytes(snapshot) + b"\n")
    corpus["conclusion_lineage_hash"] = snapshot.conclusion_lineage_hash
    corpus["effective_conclusion_hash"] = snapshot.conclusion.effective_conclusion_hash
    corpus_path.write_text(json.dumps(corpus), encoding="utf-8")
    return corpus_path


def _audit_tree_snapshot(workspace: Path) -> tuple[bool, tuple[tuple[str, str, bytes], ...]]:
    """Capture audit-root existence and every persisted entry without creating it."""
    root = workspace / "audits"
    if not root.exists():
        return False, ()
    entries: list[tuple[str, str, bytes]] = []
    for path in sorted(root.rglob("*"), key=lambda item: item.relative_to(root).as_posix()):
        relative = path.relative_to(root).as_posix()
        if path.is_dir():
            entries.append((relative, "directory", b""))
        else:
            entries.append((relative, "file", path.read_bytes()))
    return True, tuple(entries)


@pytest.mark.parametrize(
    ("policy", "mastery", "confidence", "expected"),
    (
        ("policy-04-baseline-60", 69, 59, "admitted"),
        ("policy-04-baseline-60", 70, 59, "pending-confirmation"),
        ("policy-04-baseline-60", 70, 60, "admitted"),
        ("policy-04-conservative-70", 70, 69, "pending-confirmation"),
        ("policy-04-conservative-70", 70, 70, "admitted"),
    ),
)
def test_admission_boundaries_are_integer_exact_and_never_mutate_judgments(
    tmp_path: Path, policy: str, mastery: int, confidence: int, expected: str
) -> None:
    proposal = _proposal(
        tmp_path,
        demonstrated_mastery=mastery,
        evidence_confidence=confidence,
        mastery_anchor_fit=_anchor_payload(mastery),
        exact_score_basis="The integer fixture score remains inside the accepted anchor.",
    )

    admission = decide_admission(proposal, _policy(policy, 60 if policy.endswith("60") else 70))

    assert admission.admission_status == expected
    assert (
        proposal.demonstrated_mastery,
        proposal.skill_centrality,
        proposal.evidence_confidence,
    ) == (
        mastery,
        80,
        confidence,
    )
    if expected != "admitted":
        with pytest.raises(AssessmentWorkflowError, match="only admitted"):
            aggregate_skill(proposal, admission)


@pytest.mark.parametrize(
    ("origin_status", "attribution_status", "assistance_status"),
    (
        ("self-assessed-unverified", "resolved", "resolved"),
        ("audit-verified", "unresolved", "resolved"),
        ("audit-verified", "resolved", "unresolved"),
    ),
)
def test_flagged_provenance_stays_pending_without_altering_the_proposal(
    tmp_path: Path,
    origin_status: str,
    attribution_status: str,
    assistance_status: str,
) -> None:
    proposal = _proposal(
        tmp_path,
        origin_status=origin_status,
        attribution_status=attribution_status,
        assistance_status=assistance_status,
    )

    admission = decide_admission(proposal, _policy("policy-04-baseline-60", 60))

    assert admission.admission_status == AssessmentAdmissionStatus.PENDING_CONFIRMATION
    assert proposal.origin_status == origin_status
    assert proposal.attribution_status == attribution_status
    assert proposal.assistance_status == assistance_status


def test_insufficient_review_is_retained_as_an_unverified_candidate(tmp_path: Path) -> None:
    proposal = _proposal(tmp_path)

    admission = decide_admission(
        proposal,
        _policy("policy-04-baseline-60", 60),
        review_outcome="insufficient-basis",
    )

    assert admission.admission_status == "unverified-candidate"
    assert admission.reason_code == "insufficient-basis"
    assert proposal.demonstrated_mastery == 60


def _review(
    record: AssessmentRun,
    *,
    proposal: ContributionSkillAssessment | None = None,
    outcome: str = "confirm",
    **changes: object,
) -> AssessmentRun:
    arguments: dict[str, object] = {
        "expected_effective_hash": record.effective_assessment_hash,
        "reviewer_id": "reviewer-a",
        "review_reason": "I inspected the attribution, capability anchor, and each judgment basis.",
        "attribution_checked": True,
        "anchor_fit_checked": True,
        "all_judgments_checked": True,
        "accepted_assessment": proposal or record.proposal,
        "outcome": outcome,
    }
    arguments.update(changes)
    return review_assessment(record, policy=_policy("policy-04-baseline-60", 60), **arguments)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "changes",
    (
        {"attribution_checked": False},
        {"anchor_fit_checked": False},
        {"all_judgments_checked": False},
        {"reviewer_id": ""},
        {"review_reason": ""},
        {"expected_effective_hash": "sha256:" + "0" * 64},
    ),
)
def test_review_fails_closed_without_every_substantive_acknowledgment(
    tmp_path: Path, changes: dict[str, object]
) -> None:
    record = run_assessment(
        workspace=tmp_path,
        corpus_path=CORPUS,
        policies_path=POLICIES,
        audit_id="audit-e2e",
        policy_version="policy-04-baseline-60",
    )

    with pytest.raises(AssessmentWorkflowError, match="review"):
        _review(record, **changes)

    assert AssessmentStore(tmp_path).read("assessment-audit-e2e-04-baseline-60") == record


def test_confirm_and_correction_preserve_original_proposal_and_ordered_review_hashes(
    tmp_path: Path,
) -> None:
    record = run_assessment(
        workspace=tmp_path,
        corpus_path=CORPUS,
        policies_path=POLICIES,
        audit_id="audit-e2e",
        policy_version="policy-04-baseline-60",
    )
    edited_payload = record.proposal.model_dump(mode="json")
    edited_payload["skill_centrality"] = 79
    edited = ContributionSkillAssessment.model_validate(edited_payload)

    corrected = _review(record, proposal=edited, outcome="edit")
    confirmed = _review(corrected)

    assert corrected.original_proposal == record.proposal
    assert corrected.original_proposal_hash == record.original_proposal_hash
    assert [item.sequence for item in confirmed.reviews] == [1, 2]
    assert confirmed.reviews[0].before_effective_hash == record.effective_assessment_hash
    assert confirmed.reviews[0].after_effective_hash == corrected.effective_assessment_hash
    assert confirmed.reviews[1].before_effective_hash == corrected.effective_assessment_hash
    assert confirmed.reviews[1].after_effective_hash == confirmed.effective_assessment_hash
    assert confirmed.proposal.skill_centrality == 79


def test_two_edits_retain_immutable_versions_and_reopen(tmp_path: Path) -> None:
    record = run_assessment(
        workspace=tmp_path,
        corpus_path=CORPUS,
        policies_path=POLICIES,
        audit_id="audit-e2e",
        policy_version="policy-04-baseline-60",
    )
    first_payload = record.proposal.model_dump(mode="json")
    first_payload["skill_centrality"] = 79
    first_edit = _review(
        record,
        proposal=ContributionSkillAssessment.model_validate(first_payload),
        outcome="edit",
    )
    second_payload = first_edit.proposal.model_dump(mode="json")
    second_payload["skill_centrality"] = 83
    second_edit = _review(
        first_edit,
        proposal=ContributionSkillAssessment.model_validate(second_payload),
        outcome="edit",
    )

    assert len(second_edit.versions) == 3
    assert [item.version_id for item in second_edit.versions] == [
        f"assessment-version-{record.proposal.id}-1",
        f"assessment-version-{record.proposal.id}-2",
        f"assessment-version-{record.proposal.id}-3",
    ]
    assert [item.effective_assessment.skill_centrality for item in second_edit.versions] == [
        record.proposal.skill_centrality,
        79,
        83,
    ]
    assert second_edit.versions[1].previous_version_hash == second_edit.versions[0].version_hash
    assert second_edit.versions[2].previous_version_hash == second_edit.versions[1].version_hash
    assert [len(item.reviews) for item in second_edit.versions] == [0, 1, 2]
    assert second_edit.proposal == second_edit.versions[-1].effective_assessment

    store = AssessmentStore(tmp_path)
    store.replace("assessment-audit-e2e-04-baseline-60", second_edit)
    assert store.read("assessment-audit-e2e-04-baseline-60") == second_edit


def test_insufficient_review_and_later_evidence_preserve_immutable_versions(tmp_path: Path) -> None:
    record = run_assessment(
        workspace=tmp_path,
        corpus_path=CORPUS,
        policies_path=POLICIES,
        audit_id="audit-e2e",
        policy_version="policy-04-baseline-60",
    )
    withheld = _review(record, outcome="insufficient-basis")
    later_corpus = _later_corpus(tmp_path)
    later_snapshot = AuditStore(tmp_path).read("audit-later-evidence")
    later_proposal = propose_assessment(
        snapshot=later_snapshot,
        corpus=json.loads(later_corpus.read_text(encoding="utf-8")),
        root=later_corpus.parents[3],
    )
    before_audits = _audit_tree_snapshot(tmp_path)
    later = reassess_from_new_evidence(
        withheld,
        policy=_policy("policy-04-baseline-60", 60),
        source_audit_id="audit-later-evidence",
        expected_current_version_hash=withheld.version_hash,
        proposal=later_proposal,
        workspace=tmp_path,
        later_corpus_path=later_corpus,
    )

    assert withheld.admission.admission_status == "unverified-candidate"
    assert withheld.result is None
    assert later.versions[-1].previous_version_hash == withheld.version_hash
    assert later.versions[-1].source_audit_id == "audit-later-evidence"
    assert later.versions[0].original_proposal_hash == record.original_proposal_hash
    assert later.versions[0] == withheld.versions[0]
    assert later.versions[-1].reviews == ()
    assert _audit_tree_snapshot(tmp_path) == before_audits


def test_reassessment_rejects_caller_fabricated_custody_and_authority(tmp_path: Path) -> None:
    record = run_assessment(
        workspace=tmp_path,
        corpus_path=CORPUS,
        policies_path=POLICIES,
        audit_id="audit-e2e",
        policy_version="policy-04-baseline-60",
    )
    later_corpus = _later_corpus(tmp_path)
    forged = record.proposal.model_dump(mode="json")
    forged["source_envelope"]["audit_id"] = "audit-fabricated"
    forged["source_envelope"]["authority_label"] = "reviewed-user-truth"
    forged["assessment_status"] = "reviewed"
    proposal = ContributionSkillAssessment.model_validate(forged)

    with pytest.raises(AssessmentWorkflowError, match="corpus does not authorize"):
        reassess_from_new_evidence(
            record,
            policy=_policy("policy-04-baseline-60", 60),
            source_audit_id="audit-fabricated",
            expected_current_version_hash=record.version_hash,
            proposal=proposal,
            workspace=tmp_path,
            later_corpus_path=later_corpus,
        )

    assert len(record.versions) == 1


def test_reassessment_rejects_stale_hash_before_later_corpus_loading(tmp_path: Path) -> None:
    record = run_assessment(
        workspace=tmp_path,
        corpus_path=CORPUS,
        policies_path=POLICIES,
        audit_id="audit-e2e",
        policy_version="policy-04-baseline-60",
    )
    sidecar = AssessmentStore(tmp_path).path("assessment-audit-e2e-04-baseline-60")
    before_sidecar = sidecar.read_bytes()
    before_audits = _audit_tree_snapshot(tmp_path)

    with pytest.raises(AssessmentWorkflowError, match="stale"):
        reassess_from_new_evidence(
            record,
            policy=_policy("policy-04-baseline-60", 60),
            source_audit_id="audit-later-evidence",
            expected_current_version_hash="sha256:" + "0" * 64,
            proposal=record.proposal,
            workspace=tmp_path,
            later_corpus_path=tmp_path / "missing-corpus.json",
        )
    assert sidecar.read_bytes() == before_sidecar
    assert _audit_tree_snapshot(tmp_path) == before_audits


def test_reassessment_rejects_detached_later_audit_without_any_workspace_mutation(
    tmp_path: Path,
) -> None:
    """A reassessment may read only a later audit already stored in its own workspace."""
    victim = tmp_path / "victim"
    authority = tmp_path / "authority"
    record = run_assessment(
        workspace=victim,
        corpus_path=CORPUS,
        policies_path=POLICIES,
        audit_id="audit-e2e",
        policy_version="policy-04-baseline-60",
    )
    later_corpus = _later_corpus(authority)
    later_proposal = propose_assessment(
        snapshot=AuditStore(authority).read("audit-later-evidence"),
        corpus=json.loads(later_corpus.read_text(encoding="utf-8")),
        root=later_corpus.parents[3],
    )
    sidecar = AssessmentStore(victim).path("assessment-audit-e2e-04-baseline-60")
    before_sidecar = sidecar.read_bytes()
    before_audits = _audit_tree_snapshot(victim)

    with pytest.raises(AssessmentWorkflowError, match="audit"):
        reassess_from_new_evidence(
            record,
            policy=_policy("policy-04-baseline-60", 60),
            source_audit_id="audit-later-evidence",
            expected_current_version_hash=record.version_hash,
            proposal=later_proposal,
            workspace=victim,
            later_corpus_path=later_corpus,
        )

    assert sidecar.read_bytes() == before_sidecar
    assert _audit_tree_snapshot(victim) == before_audits


@pytest.mark.parametrize("case", ("missing", "corrupt", "incomplete", "unconfirmed", "custody"))
def test_reassessment_rejects_invalid_later_audits_without_any_workspace_mutation(
    tmp_path: Path, case: str
) -> None:
    """Every no-replay audit failure leaves both persistence roots byte-identical."""
    record = run_assessment(
        workspace=tmp_path,
        corpus_path=CORPUS,
        policies_path=POLICIES,
        audit_id="audit-e2e",
        policy_version="policy-04-baseline-60",
    )
    later_corpus = _later_corpus(tmp_path)
    later_payload = json.loads(later_corpus.read_text(encoding="utf-8"))
    source_audit_id = "audit-later-evidence"
    audit_store = AuditStore(tmp_path)
    audit_path = audit_store.path(source_audit_id)
    if case == "missing":
        source_audit_id = "audit-missing-evidence"
        later_payload["audit_id"] = source_audit_id
        later_corpus.write_text(json.dumps(later_payload), encoding="utf-8")
    elif case == "corrupt":
        audit_path.write_text("{not-json", encoding="utf-8")
    elif case == "incomplete":
        payload = audit_store.read(source_audit_id).model_dump(mode="json")
        payload["status"] = "reviewing"
        audit_store.replace(AuditSnapshot.model_validate(payload))
    elif case == "unconfirmed":
        snapshot = audit_store.read(source_audit_id)
        assert snapshot.conclusion is not None
        conclusion_payload = snapshot.conclusion.model_dump(mode="json")
        conclusion_payload["whole_review"] = "pending"
        conclusion_payload["effective_conclusion_hash"] = effective_conclusion_digest(
            snapshot.conclusion.entries, "pending"
        )
        conclusion = AuditConclusion.model_validate(conclusion_payload)
        payload = snapshot.model_dump(mode="json")
        payload["conclusion"] = conclusion.model_dump(mode="json")
        payload["conclusion_reviews"] = []
        payload["conclusion_lineage_hash"] = conclusion_lineage_digest(conclusion, ())
        audit_store.replace(AuditSnapshot.model_validate(payload))
    else:
        later_payload["audit_snapshot_hash"] = "sha256:" + "0" * 64
        later_corpus.write_text(json.dumps(later_payload), encoding="utf-8")
    proposal = record.proposal
    sidecar = AssessmentStore(tmp_path).path("assessment-audit-e2e-04-baseline-60")
    before_sidecar = sidecar.read_bytes()
    before_audits = _audit_tree_snapshot(tmp_path)

    with pytest.raises(AssessmentWorkflowError):
        reassess_from_new_evidence(
            record,
            policy=_policy("policy-04-baseline-60", 60),
            source_audit_id=source_audit_id,
            expected_current_version_hash=record.version_hash,
            proposal=proposal,
            workspace=tmp_path,
            later_corpus_path=later_corpus,
        )

    assert sidecar.read_bytes() == before_sidecar
    assert _audit_tree_snapshot(tmp_path) == before_audits


def _run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(LAUNCHER), *args],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )


def test_pending_and_review_cli_require_complete_payload_without_leaking_answers(
    tmp_path: Path,
) -> None:
    run_assessment(
        workspace=tmp_path,
        corpus_path=CORPUS,
        policies_path=POLICIES,
        audit_id="audit-e2e",
        policy_version="policy-04-baseline-60",
    )
    pending_proposal = _proposal(
        tmp_path,
        demonstrated_mastery=70,
        evidence_confidence=59,
        mastery_anchor_fit=_anchor_payload(70),
        exact_score_basis="The integer fixture score remains inside the accepted anchor.",
    )
    pending = build_assessment_run(
        pending_proposal,
        decide_admission(pending_proposal, _policy("policy-04-baseline-60", 60)),
    )
    store = AssessmentStore(tmp_path)
    store.replace("assessment-audit-e2e-04-baseline-60", pending)
    payload_path = tmp_path / "accepted-assessment.json"
    payload_path.write_text(json.dumps(pending_proposal.model_dump(mode="json")), encoding="utf-8")

    listed = _run("assessment", "pending", "--workspace", str(tmp_path))
    assert listed.returncode == 0, listed.stderr
    assert "direct_review_request" in listed.stdout
    assert "demonstrated_mastery_basis" in listed.stdout
    assert "RAW_INTERVIEW_SENTINEL" not in listed.stdout

    incomplete = _run(
        "assessment",
        "review",
        "--workspace",
        str(tmp_path),
        "--run-id",
        "assessment-audit-e2e-04-baseline-60",
        "--expected-effective-hash",
        pending.effective_assessment_hash,
        "--reviewer",
        "reviewer-a",
        "--reason",
        "valid reason",
        "--assessment-json",
        str(payload_path),
    )
    assert incomplete.returncode == 2
    assert "assessment_workflow_error" in incomplete.stderr
