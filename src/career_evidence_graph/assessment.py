"""Offline, contribution-grounded Phase 4 assessment calibration seam."""

from __future__ import annotations

import json
import os
import re
import stat
import tempfile
from pathlib import Path
from typing import Any

from pydantic import ValidationError, model_validator

from .audit.decision import RecordedDecisionPort
from .audit.models import AuditAction, AuditSnapshot, BoundaryDecision, ProbePlan
from .audit.store import AuditStorageError, AuditStore
from .audit.workflow import AuditWorkflowError, start_audit, transition_audit
from .domain.models import (
    AdmissionDecision,
    AggregationPolicy,
    AssessmentLineage,
    AssessmentSourceEnvelope,
    CalibratedUserSkillResult,
    ContributionSkillAssessment,
    DurationEvidence,
    MasteryAnchorFit,
    SkillResolutionDecision,
)
from .validation.hashing import canonical_json_bytes, sha256_digest
from .validation.models import StrictModel


class AssessmentWorkflowError(RuntimeError):
    """Assessment authority could not establish a valid calibrated result."""


class AssessmentStorageError(RuntimeError):
    """Trusted-local assessment persistence rejected a record or path."""


class AssessmentRun(StrictModel):
    schema_version: str = "assessment-run/v1"
    proposal: ContributionSkillAssessment
    admission: AdmissionDecision
    result: CalibratedUserSkillResult

    @model_validator(mode="after")
    def validate_links(self) -> AssessmentRun:
        if self.admission.assessment_id != self.proposal.id:
            raise ValueError("admission must reference proposal")
        if self.result.baseline_assessment_id != self.proposal.id:
            raise ValueError("result baseline must reference proposal")
        if self.result.policy_version != self.admission.policy_version:
            raise ValueError("result and admission policy must match")
        return self


_RUN_ID = re.compile(r"^assessment-[a-z0-9-]+$")


class AssessmentStore:
    """One strict, atomic sidecar record per trusted-local assessment run."""

    def __init__(self, workspace: Path) -> None:
        self.workspace = workspace

    @property
    def root(self) -> Path:
        return self.workspace / "assessments"

    @staticmethod
    def _safe(run_id: str) -> None:
        if not _RUN_ID.fullmatch(run_id):
            raise AssessmentStorageError("unsafe assessment ID")

    def path_for(self, run_id: str) -> Path:
        self._safe(run_id)
        path = self.root / f"{run_id}.json"
        if path.parent != self.root:
            raise AssessmentStorageError("unsafe assessment path")
        return path

    def path(self, run_id: str) -> Path:
        return self.path_for(run_id)

    def _ensure_root(self) -> None:
        try:
            self.root.mkdir(mode=0o700, parents=True, exist_ok=True)
        except OSError as exc:
            raise AssessmentStorageError("assessment workspace is unavailable") from exc
        if self.root.is_symlink() or not self.root.is_dir():
            raise AssessmentStorageError("assessment root is directly linked or unsafe")

    @staticmethod
    def _admit(path: Path) -> None:
        try:
            info = path.lstat()
        except FileNotFoundError as exc:
            raise AssessmentStorageError("assessment record is missing") from exc
        except OSError as exc:
            raise AssessmentStorageError("assessment record is unavailable") from exc
        if stat.S_ISLNK(info.st_mode) or info.st_nlink != 1:
            raise AssessmentStorageError("assessment record is directly linked")
        if not stat.S_ISREG(info.st_mode):
            raise AssessmentStorageError("assessment record is unsafe")

    @staticmethod
    def _validate(record: AssessmentRun) -> AssessmentRun:
        try:
            return AssessmentRun.model_validate(record.model_dump(mode="json"))
        except ValidationError as exc:
            raise AssessmentStorageError("assessment record is invalid") from exc

    @staticmethod
    def _atomic_replace(path: Path, data: bytes) -> None:
        descriptor = -1
        temporary_name: str | None = None
        try:
            descriptor, temporary_name = tempfile.mkstemp(
                dir=path.parent, prefix=f".{path.name}.", suffix=".tmp"
            )
            with os.fdopen(descriptor, "wb") as handle:
                descriptor = -1
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary_name, path)
            directory = os.open(path.parent, os.O_RDONLY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
        except OSError as exc:
            raise AssessmentStorageError("assessment record replacement failed") from exc
        finally:
            if descriptor >= 0:
                os.close(descriptor)
            if temporary_name is not None:
                Path(temporary_name).unlink(missing_ok=True)

    def create(self, run_id: str, record: AssessmentRun) -> None:
        record = self._validate(record)
        self._ensure_root()
        path = self.path_for(run_id)
        if path.is_symlink():
            raise AssessmentStorageError("assessment record is directly linked")
        if path.exists():
            raise AssessmentStorageError("assessment record already exists")
        self._atomic_replace(path, canonical_json_bytes(record) + b"\n")

    def read(self, run_id: str) -> AssessmentRun:
        self._ensure_root()
        path = self.path_for(run_id)
        self._admit(path)
        try:
            record = AssessmentRun.model_validate_json(path.read_bytes())
        except (OSError, ValidationError, ValueError, json.JSONDecodeError) as exc:
            raise AssessmentStorageError("assessment record is corrupt") from exc
        return self._validate(record)

    def replace(self, run_id: str, record: AssessmentRun) -> None:
        record = self._validate(record)
        self._ensure_root()
        path = self.path_for(run_id)
        self._admit(path)
        self._atomic_replace(path, canonical_json_bytes(record) + b"\n")


def _load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        raise AssessmentWorkflowError("calibration input is invalid") from exc
    if not isinstance(value, dict):
        raise AssessmentWorkflowError("calibration input must be an object")
    return value


def _repository_root(corpus_path: Path) -> Path:
    try:
        return corpus_path.parents[3]
    except IndexError as exc:
        raise AssessmentWorkflowError("corpus path is outside calibration layout") from exc


def _materialize_audit(
    *, workspace: Path, corpus: dict[str, Any], root: Path, audit_id: str
) -> AuditSnapshot:
    if audit_id != corpus.get("audit_id"):
        raise AssessmentWorkflowError("corpus does not authorize requested audit")
    store = AuditStore(workspace)
    try:
        snapshot = store.read(audit_id)
    except AuditStorageError:
        journey = corpus.get("audit_journey")
        if not isinstance(journey, dict):
            raise AssessmentWorkflowError("corpus has no auditable journey") from None
        try:
            plan = ProbePlan.model_validate(journey["probe_plan"])
            decisions = tuple(
                BoundaryDecision.model_validate(item) for item in journey["decisions"]
            )
            port = RecordedDecisionPort(
                plan=plan,
                decisions={(item.question_id, item.answer): item for item in decisions},
            )
            fixture = root / str(corpus["fixture_path"])
            manifest = root / str(corpus["source_manifest_path"])
            snapshot = start_audit(
                workspace=workspace,
                fixture_path=fixture,
                manifest_path=manifest,
                contribution_id=str(corpus["contribution_id"]),
                audit_id=audit_id,
                decision_port=port,
            )
            for action_value in journey["actions"]:
                action = AuditAction.model_validate(action_value)
                snapshot = transition_audit(snapshot, action, decision_port=port)
                store.replace(snapshot)
        except (KeyError, TypeError, ValidationError, AuditWorkflowError, AuditStorageError) as exc:
            raise AssessmentWorkflowError("corpus audit journey is invalid") from exc
    if snapshot.status != "completed" or snapshot.conclusion is None:
        raise AssessmentWorkflowError("audit is not completed with a conclusion")
    if snapshot.conclusion.whole_review != "confirmed":
        raise AssessmentWorkflowError("audit conclusion is not confirmed")
    expected_bytes = canonical_json_bytes(snapshot) + b"\n"
    if sha256_digest(expected_bytes) != corpus.get("audit_snapshot_hash"):
        raise AssessmentWorkflowError("audit snapshot hash does not match corpus")
    if snapshot.conclusion_lineage_hash != corpus.get("conclusion_lineage_hash"):
        raise AssessmentWorkflowError("audit conclusion lineage does not match corpus")
    if snapshot.conclusion.effective_conclusion_hash != corpus.get("effective_conclusion_hash"):
        raise AssessmentWorkflowError("audit effective conclusion does not match corpus")
    return snapshot


def _policy(policies_path: Path, policy_version: str) -> AggregationPolicy:
    payload = _load_json(policies_path)
    try:
        policies = [AggregationPolicy.model_validate(item) for item in payload["policies"]]
    except (KeyError, TypeError, ValidationError) as exc:
        raise AssessmentWorkflowError("policy artifact is invalid") from exc
    for policy in policies:
        if policy.policy_version == policy_version:
            return policy
    raise AssessmentWorkflowError("requested policy is not in the calibration artifact")


def propose_assessment(
    *, snapshot: AuditSnapshot, corpus: dict[str, Any], root: Path
) -> ContributionSkillAssessment:
    """Construct one D-01/D-06 proposal from the exact completed audit only."""
    candidate = corpus.get("candidate")
    if not isinstance(candidate, dict) or snapshot.conclusion is None:
        raise AssessmentWorkflowError("calibration candidate is invalid")
    try:
        resolution = SkillResolutionDecision.model_validate(candidate["skill_resolution"])
    except (KeyError, ValidationError) as exc:
        raise AssessmentWorkflowError("specific Skill resolution is invalid") from exc
    if resolution.authority_label != "synthetic-calibration":
        raise AssessmentWorkflowError(
            "derived candidate requires explicit synthetic calibration authority"
        )
    if resolution.candidate_skill_id == "skill-stoa-reviewed-fixture":
        raise AssessmentWorkflowError("broad fixture marker is not scoreable")
    if resolution.candidate_skill_id != candidate.get("skill_id"):
        raise AssessmentWorkflowError("Skill resolution does not bind the candidate")
    if candidate.get("authority_label") != "derived-counterfactual":
        raise AssessmentWorkflowError("candidate must retain derived-counterfactual authority")
    fixture = root / str(corpus["fixture_path"])
    manifest = root / str(corpus["source_manifest_path"])
    if sha256_digest(fixture.read_bytes()) != corpus.get("fixture_hash"):
        raise AssessmentWorkflowError("sealed fixture hash does not match corpus")
    if sha256_digest(manifest.read_bytes()) != corpus.get("source_manifest_hash"):
        raise AssessmentWorkflowError("source manifest hash does not match corpus")
    source = AssessmentSourceEnvelope(
        authority_label="derived-counterfactual",
        audit_id=snapshot.audit_id,
        audit_snapshot_hash=str(corpus["audit_snapshot_hash"]),
        fixture_hash=str(corpus["fixture_hash"]),
        source_manifest_hash=str(corpus["source_manifest_hash"]),
        conclusion_lineage_hash=str(snapshot.conclusion_lineage_hash),
        effective_conclusion_hash=snapshot.conclusion.effective_conclusion_hash,
        contribution_id=snapshot.contribution_id,
        evidence_ids=tuple(fact.evidence_id for fact in snapshot.inspected_facts),
        question_ids=tuple(question.id for question in snapshot.questions),
        answer_ids=tuple(f"answer:{answer.question_id}" for answer in snapshot.answers),
        attribution_hash=sha256_digest(canonical_json_bytes(snapshot.attribution)),
    )
    try:
        return ContributionSkillAssessment(
            id=str(candidate["assessment_id"]),
            skill_id=resolution.candidate_skill_id,
            contribution_id=snapshot.contribution_id,
            lineage=AssessmentLineage(
                source_kind="contribution", contribution_id=snapshot.contribution_id
            ),
            demonstrated_mastery=int(candidate["demonstrated_mastery"]),
            skill_centrality=int(candidate["skill_centrality"]),
            evidence_confidence=int(candidate["evidence_confidence"]),
            context=str(candidate["context"]),
            duration=DurationEvidence.model_validate(candidate["duration"]),
            basis_claim_ids=tuple(candidate["basis_claim_ids"]),
            assessment_status="derived-counterfactual",
            mastery_anchor_fit=MasteryAnchorFit.model_validate(candidate["mastery_anchor_fit"]),
            exact_score_basis=str(candidate["exact_score_basis"]),
            source_envelope=source,
        )
    except (KeyError, TypeError, ValueError, ValidationError) as exc:
        raise AssessmentWorkflowError("assessment proposal is invalid") from exc


def decide_admission(
    proposal: ContributionSkillAssessment, policy: AggregationPolicy
) -> AdmissionDecision:
    """Apply an explicit replaceable confidence policy without changing mastery."""
    if proposal.demonstrated_mastery >= policy.high_mastery_min and (
        proposal.evidence_confidence < policy.strict_confidence_min
    ):
        status = "pending-confirmation"
        reason = "high mastery requires confirmation under this candidate policy"
    else:
        status = "admitted"
        reason = "proposal meets the candidate policy's admission rule"
    return AdmissionDecision(
        assessment_id=proposal.id,
        policy_version=policy.policy_version,
        admission_status=status,
        reason=reason,
    )


def aggregate_skill(
    proposal: ContributionSkillAssessment, admission: AdmissionDecision
) -> CalibratedUserSkillResult:
    """Use the strongest admitted assessment exactly; never add a volume bonus."""
    if admission.admission_status != "admitted" or proposal.source_envelope is None:
        raise AssessmentWorkflowError("only admitted assessments can enter an aggregate")
    return CalibratedUserSkillResult(
        result_id=f"result-{proposal.id}",
        skill_id=proposal.skill_id,
        mastery=proposal.demonstrated_mastery,
        policy_version=admission.policy_version,
        baseline_assessment_id=proposal.id,
        admitted_assessment_ids=(proposal.id,),
        source_envelope=proposal.source_envelope,
        authority_label=proposal.source_envelope.authority_label,
        aggregation_rationale=(
            "Calibration baseline equals the strongest admitted assessment; no count, "
            "confidence, centrality, or evidence-volume bonus was applied."
        ),
    )


def run_assessment(
    *, workspace: Path, corpus_path: Path, policies_path: Path, audit_id: str, policy_version: str
) -> AssessmentRun:
    """Run and persist the one offline, explicitly synthetic calibration tracer."""
    corpus = _load_json(corpus_path)
    root = _repository_root(corpus_path)
    snapshot = _materialize_audit(workspace=workspace, corpus=corpus, root=root, audit_id=audit_id)
    proposal = propose_assessment(snapshot=snapshot, corpus=corpus, root=root)
    admission = decide_admission(proposal, _policy(policies_path, policy_version))
    result = aggregate_skill(proposal, admission)
    record = AssessmentRun(proposal=proposal, admission=admission, result=result)
    run_id = f"assessment-{audit_id}-{policy_version.removeprefix('policy-')}"
    store = AssessmentStore(workspace)
    try:
        store.create(run_id, record)
    except AssessmentStorageError as exc:
        if "already exists" not in str(exc):
            raise
        store.replace(run_id, record)
    return store.read(run_id)
