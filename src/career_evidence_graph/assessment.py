"""Offline, contribution-grounded Phase 4 assessment calibration seam."""

from __future__ import annotations

import json
import os
import re
import stat
import tempfile
from pathlib import Path
from typing import Any

from pydantic import Field, ValidationError, model_validator

from .audit.decision import RecordedDecisionPort
from .audit.models import AuditAction, AuditSnapshot, BoundaryDecision, ProbePlan
from .audit.store import AuditStorageError, AuditStore
from .audit.workflow import AuditWorkflowError, start_audit, transition_audit
from .domain.invariants import _normalized_text, normalize_skill_metadata, validate_user_skill
from .domain.models import (
    MASTERY_ANCHORS,
    AdmissionDecision,
    AggregationPolicy,
    AnchorPromotionDecision,
    AssessmentAdmissionStatus,
    AssessmentJudgmentBasis,
    AssessmentLineage,
    AssessmentReview,
    AssessmentSourceEnvelope,
    AssessmentVersion,
    CalibratedUserSkillResult,
    CalibrationCaseResult,
    ContributionSkillAssessment,
    DurationEvidence,
    MasteryAnchorFit,
    OntologyRelation,
    PolicyActivation,
    PolicyComparison,
    PolicyHistory,
    PolicyRunResult,
    Skill,
    SkillAlias,
    SkillNormalizationRecord,
    SkillPolicyDelta,
    SkillResolutionDecision,
    SpecificSkillProposal,
)
from .validation.hashing import canonical_json_bytes, sha256_digest
from .validation.models import StrictModel


class AssessmentWorkflowError(RuntimeError):
    """Assessment authority could not establish a valid calibrated result."""


class AssessmentStorageError(RuntimeError):
    """Trusted-local assessment persistence rejected a record or path."""


def resolve_skill_candidate(
    candidate_text: str,
    *,
    skills: tuple[Skill, ...],
    aliases: tuple[SkillAlias, ...] = (),
    ontology_relations: tuple[OntologyRelation, ...] = (),
) -> SkillNormalizationRecord:
    """Resolve one candidate through the single deterministic normalizer contract.

    A missing, ambiguous, or descriptive match stays review-only.  This helper
    only selects existing normalization metadata; it never creates a Skill or
    changes any mastery value.
    """
    normalized_candidate = _normalized_text(candidate_text)
    records = normalize_skill_metadata(skills, aliases, ontology_relations)
    matching = [record for record in records if record.normalized_text == normalized_candidate]
    if matching:
        return matching[0]
    return SkillNormalizationRecord(
        original_text=candidate_text,
        normalized_text=normalized_candidate,
        review_status="unmatched",
    )


def _entry_evidence_ids(snapshot: AuditSnapshot, entry_id: str) -> tuple[str, ...]:
    """Return the completed audit's evidence IDs for an eligible conclusion entry."""
    if snapshot.conclusion is None:
        return ()
    entry = next((item for item in snapshot.conclusion.entries if item.id == entry_id), None)
    if entry is None or entry.verification != "audit-verified" or entry.review != "confirmed":
        return ()
    referenced = set(entry.artifact_references)
    evidence_ids = {
        fact.evidence_id
        for fact in snapshot.inspected_facts
        if not referenced or fact.evidence_id in referenced or fact.source_locator in referenced
    }
    return tuple(sorted(evidence_ids))


def propose_assessments(
    *,
    snapshot: AuditSnapshot,
    fixture_hash: str,
    source_manifest_hash: str,
    skills: tuple[Skill, ...],
    candidates_by_entry: dict[str, tuple[str, ...]],
    aliases: tuple[SkillAlias, ...] = (),
    ontology_relations: tuple[OntologyRelation, ...] = (),
) -> tuple[SpecificSkillProposal, ...]:
    """Produce one proposal per directly supported, automatically resolved Skill.

    The caller supplies candidate wording attached to a reviewed conclusion
    entry.  Only a completed, whole-confirmed audit and entry-level confirmed
    capability can supply a proposal.  Candidates that need human review stay
    outside this score-eligible output until an explicit D-03 resolution is
    recorded elsewhere.
    """
    if snapshot.status != "completed" or snapshot.conclusion is None:
        return ()
    if snapshot.conclusion.whole_review != "confirmed" or not snapshot.conclusion_lineage_hash:
        return ()

    proposals: list[SpecificSkillProposal] = []
    for entry_id in sorted(candidates_by_entry):
        entry = next((item for item in snapshot.conclusion.entries if item.id == entry_id), None)
        evidence_ids = _entry_evidence_ids(snapshot, entry_id)
        if entry is None or not evidence_ids:
            continue
        attribution = tuple(
            sorted(
                record.area_id
                for record in snapshot.attribution_records
                if record.area_id == entry.area
                and record.ownership == "user-owned"
                and record.assistance != "unresolved"
            )
        )
        answer_ids = tuple(
            sorted(
                {
                    reference.removeprefix("answer:")
                    for reference in entry.answer_references
                    if reference.startswith("answer:question-")
                }
            )
        )
        if not attribution or not answer_ids:
            continue
        for candidate_text in sorted(set(candidates_by_entry[entry_id]), key=_normalized_text):
            record = resolve_skill_candidate(
                candidate_text,
                skills=skills,
                aliases=aliases,
                ontology_relations=ontology_relations,
            )
            if record.review_status != "matched" or len(record.candidate_skill_ids) != 1:
                continue
            skill_id = record.candidate_skill_ids[0]
            proposal_id = f"proposal-{snapshot.audit_id}-{entry_id}-{skill_id}"
            proposals.append(
                SpecificSkillProposal(
                    proposal_id=proposal_id,
                    skill_id=skill_id,
                    contribution_id=snapshot.contribution_id,
                    audit_id=snapshot.audit_id,
                    fixture_hash=fixture_hash,
                    source_manifest_hash=source_manifest_hash,
                    conclusion_lineage_hash=snapshot.conclusion_lineage_hash,
                    conclusion_entry_ids=(entry_id,),
                    evidence_ids=evidence_ids,
                    answer_question_ids=answer_ids,
                    attribution_area_ids=attribution,
                    normalization_record_hash=sha256_digest(canonical_json_bytes(record)),
                )
            )
    return tuple(sorted(proposals, key=lambda item: (item.skill_id, item.contribution_id)))


def _assessment_digest(assessment: ContributionSkillAssessment) -> str:
    return sha256_digest(canonical_json_bytes(assessment))


def _version_digest(version: AssessmentVersion) -> str:
    payload = version.model_dump(mode="json", exclude={"version_hash"})
    return sha256_digest(canonical_json_bytes(payload))


def _validate_review_lineage(reviews: tuple[AssessmentReview, ...], effective_hash: str) -> None:
    if [review.sequence for review in reviews] != list(range(1, len(reviews) + 1)):
        raise ValueError("assessment reviews must have contiguous ordered sequences")
    for previous, current in zip(reviews, reviews[1:], strict=False):
        if previous.after_effective_hash != current.before_effective_hash:
            raise ValueError("assessment reviews must form a contiguous effective-hash lineage")
    if reviews and reviews[-1].after_effective_hash != effective_hash:
        raise ValueError("assessment review lineage does not reach the effective assessment")


class AssessmentRun(StrictModel):
    schema_version: str = "assessment-run/v1"
    proposal: ContributionSkillAssessment
    admission: AdmissionDecision
    result: CalibratedUserSkillResult | None = None
    original_proposal: ContributionSkillAssessment
    original_proposal_hash: str
    effective_assessment_hash: str
    reviews: tuple[AssessmentReview, ...] = ()
    versions: tuple[AssessmentVersion, ...] = Field(min_length=1)
    version_hash: str

    @model_validator(mode="after")
    def validate_links(self) -> AssessmentRun:
        if self.admission.assessment_id != self.proposal.id:
            raise ValueError("admission must reference proposal")
        if self.original_proposal_hash != _assessment_digest(self.original_proposal):
            raise ValueError("original proposal hash does not match its content")
        if self.effective_assessment_hash != _assessment_digest(self.proposal):
            raise ValueError("effective assessment hash does not match its content")
        _validate_review_lineage(self.reviews, self.effective_assessment_hash)
        previous_hash: str | None = None
        for version in self.versions:
            if version.previous_version_hash != previous_hash:
                raise ValueError("assessment versions must form a contiguous immutable lineage")
            if version.original_proposal_hash != _assessment_digest(version.original_proposal):
                raise ValueError("version original proposal hash does not match its content")
            if version.effective_assessment_hash != _assessment_digest(
                version.effective_assessment
            ):
                raise ValueError("version effective assessment hash does not match its content")
            _validate_review_lineage(version.reviews, version.effective_assessment_hash)
            if version.version_hash != _version_digest(version):
                raise ValueError("assessment version hash does not match its content")
            previous_hash = version.version_hash
        latest = self.versions[-1]
        if (
            self.version_hash != latest.version_hash
            or self.original_proposal != latest.original_proposal
            or self.original_proposal_hash != latest.original_proposal_hash
            or self.proposal != latest.effective_assessment
            or self.effective_assessment_hash != latest.effective_assessment_hash
            or self.admission != latest.admission
            or self.reviews != latest.reviews
        ):
            raise ValueError("current assessment must match the latest immutable version")
        if self.admission.admission_status != AssessmentAdmissionStatus.ADMITTED:
            if self.result is not None:
                raise ValueError("non-admitted proposals cannot carry an aggregate result")
            return self
        if self.result is None:
            raise ValueError("admitted proposal requires an aggregate result")
        if self.result.baseline_assessment_id != self.proposal.id:
            raise ValueError("result baseline must reference proposal")
        if self.result.admitted_assessment_ids != (self.proposal.id,):
            raise ValueError("result admitted assessments must exactly match the proposal")
        if self.result.policy_version != self.admission.policy_version:
            raise ValueError("result and admission policy must match")
        if self.result.skill_id != self.proposal.skill_id:
            raise ValueError("result Skill must match the proposal")
        if self.result.mastery != self.proposal.demonstrated_mastery:
            raise ValueError("result mastery must match the admitted proposal")
        if self.result.source_envelope != self.proposal.source_envelope:
            raise ValueError("result source envelope must match the proposal")
        return self


def _make_version(
    *,
    version_id: str,
    source_audit_id: str,
    previous_version_hash: str | None,
    original_proposal: ContributionSkillAssessment,
    effective_assessment: ContributionSkillAssessment,
    admission: AdmissionDecision,
    reviews: tuple[AssessmentReview, ...],
) -> AssessmentVersion:
    effective_hash = _assessment_digest(effective_assessment)
    draft = AssessmentVersion(
        version_id=version_id,
        source_audit_id=source_audit_id,
        previous_version_hash=previous_version_hash,
        original_proposal=original_proposal,
        original_proposal_hash=_assessment_digest(original_proposal),
        effective_assessment=effective_assessment,
        effective_assessment_hash=effective_hash,
        admission=admission,
        reviews=reviews,
        version_hash="sha256:" + "0" * 64,
    )
    return AssessmentVersion.model_validate(
        {**draft.model_dump(mode="json"), "version_hash": _version_digest(draft)}
    )


def _record_from_versions(
    versions: tuple[AssessmentVersion, ...], result: CalibratedUserSkillResult | None
) -> AssessmentRun:
    current = versions[-1]
    return AssessmentRun(
        proposal=current.effective_assessment,
        admission=current.admission,
        result=result,
        original_proposal=current.original_proposal,
        original_proposal_hash=current.original_proposal_hash,
        effective_assessment_hash=current.effective_assessment_hash,
        reviews=current.reviews,
        versions=versions,
        version_hash=current.version_hash,
    )


def build_assessment_run(
    proposal: ContributionSkillAssessment, admission: AdmissionDecision
) -> AssessmentRun:
    """Make an initial versioned record, retaining even a non-admitted proposal."""
    result = (
        aggregate_skill(proposal, admission)
        if admission.admission_status == AssessmentAdmissionStatus.ADMITTED
        else None
    )
    source_audit_id = (
        proposal.source_envelope.audit_id
        if proposal.source_envelope is not None
        else "audit-unavailable"
    )
    version = _make_version(
        version_id=f"assessment-version-{proposal.id}-1",
        source_audit_id=source_audit_id,
        previous_version_hash=None,
        original_proposal=proposal,
        effective_assessment=proposal,
        admission=admission,
        reviews=(),
    )
    return _record_from_versions((version,), result)


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


def list_assessment_runs(workspace: Path) -> tuple[tuple[str, AssessmentRun], ...]:
    """Read all safe current assessment sidecars in deterministic run-ID order."""
    store = AssessmentStore(workspace)
    if not store.root.exists():
        return ()
    if store.root.is_symlink() or not store.root.is_dir():
        raise AssessmentStorageError("assessment root is directly linked or unsafe")
    records: list[tuple[str, AssessmentRun]] = []
    for path in sorted(store.root.glob("*.json")):
        run_id = path.stem
        store._safe(run_id)
        records.append((run_id, store.read(run_id)))
    return tuple(records)


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


def load_policy(policies_path: Path, policy_version: str) -> AggregationPolicy:
    """Read one versioned candidate policy through the sole calibration loader."""
    return _policy(policies_path, policy_version)


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
            judgment_basis=AssessmentJudgmentBasis.model_validate(candidate["judgment_basis"]),
            source_envelope=source,
        )
    except (KeyError, TypeError, ValueError, ValidationError) as exc:
        raise AssessmentWorkflowError("assessment proposal is invalid") from exc


def decide_admission(
    proposal: ContributionSkillAssessment,
    policy: AggregationPolicy,
    *,
    review_outcome: str | None = None,
) -> AdmissionDecision:
    """Apply an explicit replaceable confidence policy without changing mastery."""
    if review_outcome == "insufficient-basis":
        status = AssessmentAdmissionStatus.UNVERIFIED_CANDIDATE
        reason = "reviewer retained the proposal but found its basis insufficient"
        reason_code = "insufficient-basis"
    elif (
        proposal.origin_status == "self-assessed-unverified"
        or proposal.attribution_status in {"unresolved", "disputed"}
        or proposal.assistance_status == "unresolved"
    ) and not proposal.substantive_review_complete:
        status = AssessmentAdmissionStatus.PENDING_CONFIRMATION
        reason = "provenance requires a substantive review before formal admission"
        reason_code = "provenance-review-required"
    elif (
        not proposal.substantive_review_complete
        and proposal.demonstrated_mastery >= policy.high_mastery_min
        and proposal.evidence_confidence < policy.strict_confidence_min
    ):
        status = AssessmentAdmissionStatus.PENDING_CONFIRMATION
        reason = "high mastery requires confirmation under this candidate policy"
        reason_code = "high-mastery-low-confidence"
    else:
        status = AssessmentAdmissionStatus.ADMITTED
        reason = "proposal meets the candidate policy's admission rule"
        reason_code = "numeric-policy"
    return AdmissionDecision(
        assessment_id=proposal.id,
        policy_version=policy.policy_version,
        admission_status=status,
        reason=reason,
        reason_code=reason_code,
    )


def aggregate_skill(
    proposal: ContributionSkillAssessment, admission: AdmissionDecision
) -> CalibratedUserSkillResult:
    """Use the strongest admitted assessment exactly; never add a volume bonus."""
    if (
        admission.admission_status != AssessmentAdmissionStatus.ADMITTED
        or proposal.source_envelope is None
    ):
        raise AssessmentWorkflowError("only admitted assessments can enter an aggregate")
    return CalibratedUserSkillResult(
        result_id=f"result-{proposal.id}",
        skill_id=proposal.skill_id,
        mastery=proposal.demonstrated_mastery,
        anchor_id=proposal.mastery_anchor_fit.anchor_id,
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


def _anchor_for_score(score: int) -> str:
    """Return the one accepted inclusive anchor containing an exact integer score."""
    return next(
        anchor.anchor_id
        for anchor in MASTERY_ANCHORS
        if anchor.inclusive_range[0] <= score <= anchor.inclusive_range[1]
    )


def deduplicate_skill_support(
    assessments: tuple[ContributionSkillAssessment, ...],
) -> tuple[str, ...]:
    """Report repeated same-Skill support without deleting legitimate lineage."""
    first_by_support: dict[tuple[str, tuple[str, ...], str], str] = {}
    suppressed: list[str] = []
    for assessment in sorted(assessments, key=lambda item: item.id):
        if assessment.source_envelope is None:
            raise AssessmentWorkflowError("effective assessment lacks source envelope")
        identity = (
            assessment.contribution_id,
            tuple(sorted(assessment.source_envelope.evidence_ids)),
            _normalized_text(assessment.context),
        )
        original_id = first_by_support.setdefault(identity, assessment.id)
        if original_id != assessment.id:
            suppressed.append(f"same-skill-support:{original_id}:{assessment.id}")
    return tuple(suppressed)


def aggregation_snapshot_bytes(results: tuple[CalibratedUserSkillResult, ...]) -> bytes:
    """Serialize only canonical mastery and anchor facts for no-inflation checks."""
    return canonical_json_bytes(
        [
            {
                "skill_id": result.skill_id,
                "mastery": result.mastery,
                "anchor_id": result.anchor_id,
            }
            for result in sorted(results, key=lambda item: item.skill_id)
        ]
    )


NEXT_ANCHOR_PROMOTION_RUBRIC_VERSION = "anchor-promotion-rubric/v1"
NEXT_ANCHOR_PROMOTION_BEHAVIORS: dict[str, frozenset[str]] = {
    "anchor-20-39": frozenset({"fundamentals-explained", "guided-simple-task"}),
    "anchor-40-54": frozenset({"bounded-practical-task", "named-documentation-or-guidance"}),
    "anchor-55-69": frozenset({"independent-common-bounded-task"}),
    "anchor-70-79": frozenset(
        {
            "independent-complex-problem",
            "decisions-explained",
            "decisions-defended",
        }
    ),
    "anchor-80-89": frozenset(
        {
            "complete-module-or-system-delivery",
            "failure-handling",
            "trade-offs",
            "maintenance-ownership",
        }
    ),
    "anchor-90-95": frozenset(
        {
            "advanced-responsibility-context-one",
            "advanced-responsibility-context-two",
            "guidance-of-another-person",
        }
    ),
    "anchor-96-100": frozenset(
        {
            "sustained-breadth",
            "advanced-responsibility",
            "failure-tradeoff-maintenance-ownership",
            "guidance-of-another-person",
            "strongly-verified-expert-behavior",
        }
    ),
}


def promotion_input_hash(
    assessments: tuple[ContributionSkillAssessment, ...], *, policy_version: str
) -> str:
    """Hash the candidate policy and full admitted assessment inputs a decision cites."""
    return sha256_digest(
        canonical_json_bytes(
            {
                "rubric_version": NEXT_ANCHOR_PROMOTION_RUBRIC_VERSION,
                "policy_version": policy_version,
                "assessments": [
                    assessment.model_dump(mode="json")
                    for assessment in sorted(assessments, key=lambda item: item.id)
                ],
            }
        )
    )


def validate_anchor_promotion(
    decision: AnchorPromotionDecision,
    admitted_assessments: tuple[ContributionSkillAssessment, ...],
) -> AnchorPromotionDecision:
    """Fail closed unless a decision proves exactly the next observable anchor."""
    if len(admitted_assessments) < 2:
        raise AssessmentWorkflowError("promotion requires at least two admitted assessments")
    if any(assessment.skill_id != decision.skill_id for assessment in admitted_assessments):
        raise AssessmentWorkflowError("promotion requires one exact same Skill")
    if any(
        assessment.source_envelope is None
        or assessment.attribution_status != "resolved"
        or assessment.assistance_status != "resolved"
        or assessment.judgment_basis is None
        for assessment in admitted_assessments
    ):
        raise AssessmentWorkflowError("promotion requires resolved, credible audit support")
    if decision.policy_input_hash != promotion_input_hash(
        admitted_assessments, policy_version=decision.policy_version
    ):
        raise AssessmentWorkflowError("promotion policy input hash is stale")
    assessments_by_id = {assessment.id: assessment for assessment in admitted_assessments}
    if not set(decision.assessment_ids).issubset(assessments_by_id):
        raise AssessmentWorkflowError("promotion cites a non-admitted assessment")
    cited = tuple(assessments_by_id[assessment_id] for assessment_id in decision.assessment_ids)
    if len({assessment.contribution_id for assessment in cited}) < 2:
        raise AssessmentWorkflowError("promotion requires distinct Contributions")
    cited_contexts = {_normalized_text(assessment.context) for assessment in cited}
    decision_contexts = tuple(_normalized_text(context) for context in decision.distinct_contexts)
    if (
        len(set(decision_contexts)) != len(decision_contexts)
        or len(decision_contexts) < 2
        or set(decision_contexts) != cited_contexts
    ):
        raise AssessmentWorkflowError("promotion requires distinct real contexts")
    if (
        len(decision.distinct_behaviors) != len(decision.behavior_assessment_ids)
        or len(decision.distinct_behaviors) != len(decision.behavior_audit_bases)
        or len(set(decision.distinct_behaviors)) != len(decision.distinct_behaviors)
    ):
        raise AssessmentWorkflowError("promotion behavior bindings must be distinct and complete")
    for assessment_id, audit_basis in zip(
        decision.behavior_assessment_ids, decision.behavior_audit_bases, strict=True
    ):
        assessment = assessments_by_id.get(assessment_id)
        if assessment is None or assessment.id not in decision.assessment_ids:
            raise AssessmentWorkflowError("promotion behavior cites a non-admitted assessment")
        if assessment.judgment_basis is None or (
            audit_basis != assessment.judgment_basis.demonstrated_mastery_basis
        ):
            raise AssessmentWorkflowError("promotion behavior is not bound to its audit basis")
    baseline = max(
        sorted(admitted_assessments, key=lambda assessment: assessment.id),
        key=lambda assessment: assessment.demonstrated_mastery,
    )
    anchor_index = next(
        (
            index
            for index, anchor in enumerate(MASTERY_ANCHORS)
            if anchor.inclusive_range[0]
            <= baseline.demonstrated_mastery
            <= anchor.inclusive_range[1]
        ),
        None,
    )
    if anchor_index is None or anchor_index + 1 >= len(MASTERY_ANCHORS):
        raise AssessmentWorkflowError("promotion has no next anchor")
    target = MASTERY_ANCHORS[anchor_index + 1]
    if decision.target_anchor_id != target.anchor_id:
        raise AssessmentWorkflowError("promotion may target only the immediate next anchor")
    if not target.inclusive_range[0] <= decision.promoted_score <= target.inclusive_range[1]:
        raise AssessmentWorkflowError("promotion score escapes the target anchor")
    if decision.promoted_score > target.inclusive_range[0] and decision.exact_score_basis is None:
        raise AssessmentWorkflowError("promotion above the target lower bound needs reviewed basis")
    if set(decision.distinct_behaviors) != NEXT_ANCHOR_PROMOTION_BEHAVIORS[target.anchor_id]:
        raise AssessmentWorkflowError("promotion does not establish every target behavior")
    required_contributions = 3 if target.anchor_id == "anchor-96-100" else 2
    required_contexts = 3 if target.anchor_id == "anchor-96-100" else 2
    if len({assessment.contribution_id for assessment in cited}) < required_contributions:
        raise AssessmentWorkflowError("promotion lacks required distinct Contributions")
    if len(cited_contexts) < required_contexts:
        raise AssessmentWorkflowError("promotion lacks required distinct real contexts")
    return decision


def aggregate_user_skills(
    records: tuple[AssessmentRun, ...],
    *,
    promotion_decisions: tuple[AnchorPromotionDecision, ...] = (),
) -> tuple[CalibratedUserSkillResult, ...]:
    """Aggregate current admitted assessments by exact Skill without numeric pile-up."""
    admitted_by_skill: dict[str, list[ContributionSkillAssessment]] = {}
    policy_by_skill: dict[str, str] = {}
    for record in records:
        proposal = record.proposal
        if record.admission.assessment_id != proposal.id:
            raise AssessmentWorkflowError("admission does not bind the effective assessment")
        if record.admission.admission_status != AssessmentAdmissionStatus.ADMITTED:
            continue
        if proposal.source_envelope is None or proposal.mastery_anchor_fit is None:
            raise AssessmentWorkflowError("admitted assessment lacks effective lineage")
        policy = policy_by_skill.setdefault(proposal.skill_id, record.admission.policy_version)
        if policy != record.admission.policy_version:
            raise AssessmentWorkflowError("one exact Skill requires one aggregation policy")
        admitted_by_skill.setdefault(proposal.skill_id, []).append(proposal)

    decisions_by_skill = {decision.skill_id: decision for decision in promotion_decisions}
    if len(decisions_by_skill) != len(promotion_decisions):
        raise AssessmentWorkflowError("only one promotion decision may exist per exact Skill")
    results: list[CalibratedUserSkillResult] = []
    for skill_id in sorted(admitted_by_skill):
        admitted = tuple(sorted(admitted_by_skill[skill_id], key=lambda item: item.id))
        baseline = max(admitted, key=lambda item: item.demonstrated_mastery)
        contexts = tuple(sorted({assessment.context for assessment in admitted}))
        decision = decisions_by_skill.get(skill_id)
        if decision is not None:
            validate_anchor_promotion(decision, admitted)
        mastery = decision.promoted_score if decision is not None else baseline.demonstrated_mastery
        result = CalibratedUserSkillResult(
            result_id=f"result-{skill_id}",
            skill_id=skill_id,
            mastery=mastery,
            anchor_id=_anchor_for_score(mastery),
            policy_version=policy_by_skill[skill_id],
            baseline_assessment_id=baseline.id,
            admitted_assessment_ids=tuple(assessment.id for assessment in admitted),
            source_envelope=baseline.source_envelope,
            authority_label=baseline.source_envelope.authority_label,
            aggregation_rationale=(
                "Calibration baseline equals the strongest admitted assessment; no count, "
                "confidence, centrality, or evidence-volume bonus was applied."
            ),
            promotion_decision=decision,
            supporting_contexts=contexts,
            suppressed_duplicate_relationships=deduplicate_skill_support(admitted),
        )
        results.append(validate_user_skill(result, admitted))
    return tuple(results)


def _reviewed_assessment(
    current: ContributionSkillAssessment, accepted: ContributionSkillAssessment
) -> ContributionSkillAssessment:
    """Validate a complete replacement without permitting provenance rewriting."""
    if (
        accepted.id != current.id
        or accepted.skill_id != current.skill_id
        or accepted.contribution_id != current.contribution_id
        or accepted.lineage != current.lineage
        or accepted.source_envelope != current.source_envelope
        or accepted.origin_status != current.origin_status
    ):
        raise AssessmentWorkflowError("review cannot rewrite assessment provenance")
    if (
        accepted.mastery_anchor_fit is None
        or accepted.exact_score_basis is None
        or accepted.judgment_basis is None
        or accepted.source_envelope is None
    ):
        raise AssessmentWorkflowError("review requires a complete judgment and all bases")
    payload = accepted.model_dump(mode="json")
    payload["assessment_status"] = "reviewed"
    payload["substantive_review_complete"] = True
    try:
        return ContributionSkillAssessment.model_validate(payload)
    except ValidationError as exc:
        raise AssessmentWorkflowError("accepted assessment payload is invalid") from exc


def review_assessment(
    record: AssessmentRun,
    *,
    policy: AggregationPolicy,
    expected_effective_hash: str,
    reviewer_id: str,
    review_reason: str,
    attribution_checked: bool,
    anchor_fit_checked: bool,
    all_judgments_checked: bool,
    accepted_assessment: ContributionSkillAssessment,
    outcome: str = "confirm",
) -> AssessmentRun:
    """Append one hash-bound, D-10-complete correction or confirmation."""
    if expected_effective_hash != record.effective_assessment_hash:
        raise AssessmentWorkflowError("review expected effective hash is stale")
    if not reviewer_id.strip() or not review_reason.strip():
        raise AssessmentWorkflowError("review requires a reviewer and reason")
    if not all((attribution_checked, anchor_fit_checked, all_judgments_checked)):
        raise AssessmentWorkflowError("review requires all substantive acknowledgments")
    if outcome not in {"confirm", "edit", "insufficient-basis"}:
        raise AssessmentWorkflowError("review outcome is invalid")

    effective = _reviewed_assessment(record.proposal, accepted_assessment)
    admission = decide_admission(
        effective,
        policy,
        review_outcome="insufficient-basis" if outcome == "insufficient-basis" else None,
    )
    before = record.effective_assessment_hash
    after = _assessment_digest(effective)
    review = AssessmentReview(
        review_id=f"assessment-review-{effective.id}-{len(record.reviews) + 1}",
        outcome=outcome,
        reviewer_id=reviewer_id,
        reason=review_reason,
        attribution_checked=attribution_checked,
        anchor_fit_checked=anchor_fit_checked,
        all_judgments_checked=all_judgments_checked,
        sequence=len(record.reviews) + 1,
        before_effective_hash=before,
        after_effective_hash=after,
    )
    latest = record.versions[-1]
    version = _make_version(
        version_id=latest.version_id,
        source_audit_id=latest.source_audit_id,
        previous_version_hash=latest.previous_version_hash,
        original_proposal=latest.original_proposal,
        effective_assessment=effective,
        admission=admission,
        reviews=(*record.reviews, review),
    )
    result = (
        aggregate_skill(effective, admission)
        if admission.admission_status == AssessmentAdmissionStatus.ADMITTED
        else None
    )
    return _record_from_versions((*record.versions[:-1], version), result)


def reassess_from_new_evidence(
    record: AssessmentRun,
    *,
    policy: AggregationPolicy,
    source_audit_id: str,
    expected_current_version_hash: str,
    proposal: ContributionSkillAssessment,
) -> AssessmentRun:
    """Create a later source-audit version and renew admission without overwriting history."""
    if expected_current_version_hash != record.version_hash:
        raise AssessmentWorkflowError("reassessment expected current version hash is stale")
    if not re.fullmatch(r"audit-[a-z0-9-]+", source_audit_id):
        raise AssessmentWorkflowError("later evidence source audit is invalid")
    if source_audit_id == record.versions[-1].source_audit_id:
        raise AssessmentWorkflowError("later evidence source audit must differ from the current audit")
    if proposal.id != record.proposal.id or proposal.skill_id != record.proposal.skill_id:
        raise AssessmentWorkflowError("reassessment must retain the same assessment and Skill")
    payload = proposal.model_dump(mode="json")
    payload["substantive_review_complete"] = False
    try:
        renewed_proposal = ContributionSkillAssessment.model_validate(payload)
    except ValidationError as exc:
        raise AssessmentWorkflowError("later evidence proposal is invalid") from exc
    admission = decide_admission(renewed_proposal, policy)
    version = _make_version(
        version_id=f"assessment-version-{renewed_proposal.id}-{len(record.versions) + 1}",
        source_audit_id=source_audit_id,
        previous_version_hash=record.version_hash,
        original_proposal=renewed_proposal,
        effective_assessment=renewed_proposal,
        admission=admission,
        reviews=(),
    )
    result = (
        aggregate_skill(renewed_proposal, admission)
        if admission.admission_status == AssessmentAdmissionStatus.ADMITTED
        else None
    )
    return _record_from_versions((*record.versions, version), result)


def list_pending_assessments(workspace: Path) -> tuple[tuple[str, AssessmentRun], ...]:
    """Return all retained, non-admitted records for reviewer inspection."""
    store = AssessmentStore(workspace)
    if not store.root.exists():
        return ()
    store._ensure_root()
    records: list[tuple[str, AssessmentRun]] = []
    for path in sorted(store.root.glob("assessment-*.json")):
        run_id = path.stem
        record = store.read(run_id)
        if record.admission.admission_status != AssessmentAdmissionStatus.ADMITTED:
            records.append((run_id, record))
    return tuple(records)


def run_assessment(
    *, workspace: Path, corpus_path: Path, policies_path: Path, audit_id: str, policy_version: str
) -> AssessmentRun:
    """Run and persist the one offline, explicitly synthetic calibration tracer."""
    corpus = _load_json(corpus_path)
    root = _repository_root(corpus_path)
    snapshot = _materialize_audit(workspace=workspace, corpus=corpus, root=root, audit_id=audit_id)
    proposal = propose_assessment(snapshot=snapshot, corpus=corpus, root=root)
    admission = decide_admission(proposal, _policy(policies_path, policy_version))
    record = build_assessment_run(proposal, admission)
    run_id = f"assessment-{audit_id}-{policy_version.removeprefix('policy-')}"
    store = AssessmentStore(workspace)
    try:
        store.create(run_id, record)
    except AssessmentStorageError as exc:
        if "already exists" not in str(exc):
            raise
        existing = store.read(run_id)
        first_version = existing.versions[0]
        if (
            first_version.original_proposal != proposal
            or first_version.admission.policy_version != admission.policy_version
        ):
            raise AssessmentWorkflowError(
                "existing assessment run does not match the requested audit and policy identity"
            )
        return existing
    return store.read(run_id)


def _calibration_root(workspace: Path) -> Path:
    """Resolve the intentionally small, trusted-local calibration sidecar root."""
    if workspace.is_symlink():
        raise AssessmentStorageError("calibration workspace cannot be a symlink")
    return workspace.resolve() / "policy-calibration"


def _policy_history_path(workspace: Path) -> Path:
    return _calibration_root(workspace) / "history.json"


def _write_calibration_json(path: Path, value: Any) -> None:
    """Atomically publish canonical calibration history without overwriting a run payload."""
    if path.is_symlink() or (path.parent.exists() and path.parent.is_symlink()):
        raise AssessmentStorageError("calibration history path cannot be a symlink")
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.")
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(canonical_json_bytes(value) + b"\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_name, path)
    except BaseException:
        Path(temporary_name).unlink(missing_ok=True)
        raise


def load_policy_history(workspace: Path) -> PolicyHistory:
    """Load strict, local calibration history; an absent sidecar has no active policy."""
    path = _policy_history_path(workspace)
    if not path.exists():
        return PolicyHistory()
    if path.is_symlink():
        raise AssessmentStorageError("policy calibration history cannot be a symlink")
    try:
        history = PolicyHistory.model_validate_json(path.read_bytes())
    except (OSError, ValidationError) as exc:
        raise AssessmentStorageError("policy calibration history is corrupt") from exc
    try:
        _validate_policy_history(history)
    except AssessmentWorkflowError as exc:
        raise AssessmentStorageError("policy calibration history is corrupt") from exc
    return history


def _calibration_input_hashes(
    *,
    fixture_hash: str,
    source_manifest_hash: str,
    audit_snapshot_hash: str,
    conclusion_lineage_hash: str,
    effective_conclusion_hash: str,
    calibration_cases: list[Any],
) -> tuple[str, ...]:
    """Bind every policy run to verified fixture, manifest, and audit identities."""
    return (
        fixture_hash,
        source_manifest_hash,
        audit_snapshot_hash,
        conclusion_lineage_hash,
        effective_conclusion_hash,
        sha256_digest(canonical_json_bytes(calibration_cases)),
    )


def _policy_for_calibration(policies_path: Path, policy_version: str) -> AggregationPolicy:
    payload = _load_json(policies_path)
    candidates = payload.get("policies") if isinstance(payload, dict) else None
    if not isinstance(candidates, list):
        raise AssessmentWorkflowError("calibration policies are invalid")
    matches = [item for item in candidates if item.get("policy_version") == policy_version]
    if len(matches) != 1:
        raise AssessmentWorkflowError("calibration policy is missing or ambiguous")
    try:
        policy = AggregationPolicy.model_validate(matches[0])
    except ValidationError as exc:
        raise AssessmentWorkflowError("calibration policy is invalid") from exc
    if policy.activation_status != "candidate":
        raise AssessmentWorkflowError("only inactive candidate policies may be compared")
    return policy


def _calibration_case_result(
    case: dict[str, Any], policy: AggregationPolicy
) -> CalibrationCaseResult:
    """Apply only explicit integer admission rules to one simulated calibration input."""
    required = {
        "case_id",
        "skill_id",
        "authority_label",
        "parent_case_id",
        "deterministic_transform",
        "simulated_calibration_input",
        "mastery",
        "evidence_confidence",
        "coverage",
    }
    if not required.issubset(case) or case.get("authority_label") not in {
        "derived-counterfactual",
        "synthetic-negative",
    }:
        raise AssessmentWorkflowError("calibration case lacks explicit derived authority")
    if (
        case.get("parent_case_id") != "audit-e2e"
        or case.get("simulated_calibration_input") is not True
    ):
        raise AssessmentWorkflowError("calibration case is not bound to the sole real audit")
    mastery = case.get("mastery")
    confidence = case.get("evidence_confidence")
    if (
        type(mastery) is not int
        or type(confidence) is not int
        or not 0 <= mastery <= 100
        or not 0 <= confidence <= 100
    ):
        raise AssessmentWorkflowError("calibration values must be exact integers")
    anchor = next(
        (
            item
            for item in MASTERY_ANCHORS
            if item.inclusive_range[0] <= mastery <= item.inclusive_range[1]
        ),
        None,
    )
    if anchor is None:
        raise AssessmentWorkflowError("calibration mastery has no accepted anchor")
    force_defer = case.get("d10_override") is True
    numeric_defer = mastery >= policy.high_mastery_min and confidence < policy.strict_confidence_min
    admission = (
        AssessmentAdmissionStatus.PENDING_CONFIRMATION
        if force_defer or numeric_defer
        else AssessmentAdmissionStatus.ADMITTED
    )
    return CalibrationCaseResult(
        case_id=str(case["case_id"]),
        skill_id=str(case["skill_id"]),
        mastery=mastery,
        band=anchor.anchor_id,
        admission_status=admission,
        calibration_decision=(
            "defer" if admission != AssessmentAdmissionStatus.ADMITTED else "admit"
        ),
        reviewer_disagreement=bool(case.get("reviewer_disagreement", False)),
        regression_labels=tuple(str(item) for item in case.get("regression_labels", ())),
    )


def _policy_run_hash(
    *,
    policy_snapshot: AggregationPolicy,
    input_hashes: tuple[str, ...],
    case_results: tuple[CalibrationCaseResult, ...],
) -> str:
    policy_hash = _policy_hash(policy_snapshot)
    return sha256_digest(
        canonical_json_bytes(
            {
                "policy_version": policy_snapshot.policy_version,
                "input_hashes": input_hashes,
                "policy_hash": policy_hash,
                "case_results": [item.model_dump(mode="json") for item in case_results],
            }
        )
    )


def _policy_hash(policy_snapshot: AggregationPolicy) -> str:
    return sha256_digest(canonical_json_bytes(policy_snapshot))


def _write_policy_history(workspace: Path, history: PolicyHistory) -> None:
    _validate_policy_history(history)
    _write_calibration_json(_policy_history_path(workspace), history.model_dump(mode="json"))


def run_calibration_policy(
    *, workspace: Path, corpus_path: Path, policies_path: Path, policy_version: str
) -> PolicyRunResult:
    """Run one inactive policy on immutable calibration inputs and retain its result once."""
    corpus = _load_json(corpus_path)
    if (
        not isinstance(corpus, dict)
        or corpus.get("schema_version") != "assessment-calibration-corpus/v1"
    ):
        raise AssessmentWorkflowError("calibration corpus is invalid")
    root = _repository_root(corpus_path)
    fixture = root / str(corpus.get("fixture_path", ""))
    manifest = root / str(corpus.get("source_manifest_path", ""))
    fixture_hash = sha256_digest(fixture.read_bytes())
    if fixture_hash != corpus.get("fixture_hash"):
        raise AssessmentWorkflowError("sealed fixture hash does not match corpus")
    source_manifest_hash = sha256_digest(manifest.read_bytes())
    if source_manifest_hash != corpus.get("source_manifest_hash"):
        raise AssessmentWorkflowError("source manifest hash does not match corpus")
    audit_id = corpus.get("audit_id")
    if not isinstance(audit_id, str):
        raise AssessmentWorkflowError("calibration corpus audit ID is invalid")
    snapshot = _materialize_audit(
        workspace=workspace,
        corpus=corpus,
        root=root,
        audit_id=audit_id,
    )
    policy = _policy_for_calibration(policies_path, policy_version)
    cases = corpus.get("calibration_cases")
    if not isinstance(cases, list) or not cases:
        raise AssessmentWorkflowError("calibration corpus has no cases")
    case_results = tuple(
        sorted(
            (_calibration_case_result(case, policy) for case in cases if isinstance(case, dict)),
            key=lambda item: item.case_id,
        )
    )
    if len(case_results) != len(cases):
        raise AssessmentWorkflowError("calibration cases must be objects")
    input_hashes = _calibration_input_hashes(
        fixture_hash=fixture_hash,
        source_manifest_hash=source_manifest_hash,
        audit_snapshot_hash=sha256_digest(canonical_json_bytes(snapshot) + b"\n"),
        conclusion_lineage_hash=str(snapshot.conclusion_lineage_hash),
        effective_conclusion_hash=snapshot.conclusion.effective_conclusion_hash,
        calibration_cases=cases,
    )
    policy_hash = _policy_hash(policy)
    result_hash = _policy_run_hash(
        policy_snapshot=policy,
        input_hashes=input_hashes,
        case_results=case_results,
    )
    history = load_policy_history(workspace)
    existing = next((item for item in history.runs if item.result_hash == result_hash), None)
    if existing is not None:
        return existing
    run = PolicyRunResult(
        policy_version=policy_version,
        policy_snapshot=policy,
        input_hashes=input_hashes,
        policy_hash=policy_hash,
        run_sequence=len(history.runs) + 1,
        case_results=case_results,
        result_hash=result_hash,
    )
    _write_policy_history(
        workspace,
        PolicyHistory(
            runs=(*history.runs, run),
            comparisons=history.comparisons,
            activations=history.activations,
            active_pointer=history.active_pointer,
        ),
    )
    return run


def _comparison_hash(
    *,
    baseline: PolicyRunResult,
    candidate: PolicyRunResult,
    deltas: tuple[SkillPolicyDelta, ...],
    disagreements: tuple[str, ...],
    regressions: tuple[str, ...],
) -> str:
    return sha256_digest(
        canonical_json_bytes(
            {
                "baseline_result_hash": baseline.result_hash,
                "candidate_result_hash": candidate.result_hash,
                "input_hashes": baseline.input_hashes,
                "skill_deltas": [item.model_dump(mode="json") for item in deltas],
                "reviewer_disagreements": disagreements,
                "run_variance": 0,
                "regressions": regressions,
            }
        )
    )


def compare_policy_runs(
    *, workspace: Path, baseline: PolicyRunResult, candidate: PolicyRunResult
) -> PolicyComparison:
    """Compare two retained candidate runs without changing an active policy pointer."""
    if baseline.input_hashes != candidate.input_hashes:
        raise AssessmentWorkflowError("policy runs must use identical input hashes")
    baseline_by_case = {item.case_id: item for item in baseline.case_results}
    candidate_by_case = {item.case_id: item for item in candidate.case_results}
    if baseline_by_case.keys() != candidate_by_case.keys():
        raise AssessmentWorkflowError("policy runs must retain identical calibration cases")
    deltas = tuple(
        SkillPolicyDelta(
            case_id=case_id,
            skill_id=baseline_by_case[case_id].skill_id,
            mastery_delta=candidate_by_case[case_id].mastery - baseline_by_case[case_id].mastery,
            band_change=candidate_by_case[case_id].band != baseline_by_case[case_id].band,
            admission_change=(
                candidate_by_case[case_id].admission_status
                != baseline_by_case[case_id].admission_status
            ),
            baseline_admission=baseline_by_case[case_id].admission_status,
            candidate_admission=candidate_by_case[case_id].admission_status,
        )
        for case_id in sorted(baseline_by_case)
    )
    disagreements = tuple(
        item.case_id for item in baseline.case_results if item.reviewer_disagreement
    )
    regressions = tuple(
        sorted(
            {
                *(
                    f"false-deferral:{delta.case_id}"
                    for delta in deltas
                    if delta.baseline_admission == AssessmentAdmissionStatus.ADMITTED
                    and delta.candidate_admission != AssessmentAdmissionStatus.ADMITTED
                ),
                *(label for item in baseline.case_results for label in item.regression_labels),
            }
        )
    )
    comparison_hash = _comparison_hash(
        baseline=baseline,
        candidate=candidate,
        deltas=deltas,
        disagreements=disagreements,
        regressions=regressions,
    )
    history = load_policy_history(workspace)
    existing = next(
        (item for item in history.comparisons if item.comparison_hash == comparison_hash), None
    )
    if existing is not None:
        return existing
    comparison = PolicyComparison(
        input_hashes=baseline.input_hashes,
        baseline_policy_version=baseline.policy_version,
        baseline_result_hash=baseline.result_hash,
        candidate_policy_version=candidate.policy_version,
        candidate_result_hash=candidate.result_hash,
        skill_deltas=deltas,
        reviewer_disagreements=disagreements,
        run_variance=0,
        regressions=regressions,
        comparison_hash=comparison_hash,
    )
    _write_policy_history(
        workspace,
        PolicyHistory(
            runs=history.runs,
            comparisons=(*history.comparisons, comparison),
            activations=history.activations,
            active_pointer=history.active_pointer,
        ),
    )
    return comparison


def _activation_hash(activation: PolicyActivation) -> str:
    return sha256_digest(
        canonical_json_bytes(activation.model_dump(mode="json", exclude={"activation_hash"}))
    )


def _validate_policy_history(history: PolicyHistory) -> None:
    """Verify retained runs, comparisons, and human authority before using a pointer."""
    for run in history.runs:
        policy_hash = _policy_hash(run.policy_snapshot)
        if run.policy_hash != policy_hash:
            raise AssessmentWorkflowError("policy run hash does not match its policy snapshot")
        if run.result_hash != _policy_run_hash(
            policy_snapshot=run.policy_snapshot,
            input_hashes=run.input_hashes,
            case_results=run.case_results,
        ):
            raise AssessmentWorkflowError("policy run result hash does not match its content")

    for comparison in history.comparisons:
        baseline = next(
            (item for item in history.runs if item.result_hash == comparison.baseline_result_hash),
            None,
        )
        candidate = next(
            (item for item in history.runs if item.result_hash == comparison.candidate_result_hash),
            None,
        )
        if baseline is None or candidate is None:
            raise AssessmentWorkflowError("policy comparison has no retained results")
        if (
            baseline.policy_version != comparison.baseline_policy_version
            or candidate.policy_version != comparison.candidate_policy_version
            or baseline.input_hashes != candidate.input_hashes
            or comparison.input_hashes != baseline.input_hashes
        ):
            raise AssessmentWorkflowError(
                "policy comparison ancestry does not match retained results"
            )
        if comparison.comparison_hash != _comparison_hash(
            baseline=baseline,
            candidate=candidate,
            deltas=comparison.skill_deltas,
            disagreements=comparison.reviewer_disagreements,
            regressions=comparison.regressions,
        ):
            raise AssessmentWorkflowError("policy comparison hash does not match its content")

    runs = {item.result_hash: item for item in history.runs}
    comparisons = {item.comparison_hash: item for item in history.comparisons}
    previous: PolicyActivation | None = None
    for activation in history.activations:
        if activation.activation_hash != _activation_hash(activation):
            raise AssessmentWorkflowError("policy activation hash does not match its content")
        comparison = comparisons.get(activation.comparison_hash)
        if comparison is None:
            raise AssessmentWorkflowError("policy activation has no retained comparison")
        run = runs.get(activation.result_hash)
        if run is None or (
            run.policy_version != activation.activated_policy_version
            or run.policy_hash != activation.policy_hash
        ):
            raise AssessmentWorkflowError("policy activation has no matching retained result")
        selected_pair = (activation.activated_policy_version, activation.result_hash)
        compared_pairs = {
            (comparison.baseline_policy_version, comparison.baseline_result_hash),
            (comparison.candidate_policy_version, comparison.candidate_result_hash),
        }
        if selected_pair not in compared_pairs:
            raise AssessmentWorkflowError(
                "policy activation selects a policy outside its comparison"
            )
        if previous is None:
            if not (
                activation.prior_policy_version is None
                and activation.prior_result_hash is None
                and activation.expected_active_pointer == "absent"
            ):
                raise AssessmentWorkflowError(
                    "first policy activation must use the bootstrap tuple"
                )
        elif (
            activation.prior_policy_version != previous.activated_policy_version
            or activation.prior_result_hash != previous.result_hash
            or activation.expected_active_pointer != previous.activation_hash
        ):
            raise AssessmentWorkflowError("policy activation replacement ancestry is stale")
        previous = activation
    if previous is not None and history.active_pointer != previous.activation_hash:
        raise AssessmentWorkflowError("policy history pointer does not reach its latest activation")


def activate_policy(
    *,
    workspace: Path,
    policy_version: str,
    policy_hash: str,
    result_hash: str,
    comparison_hash: str,
    reviewer_id: str,
    activation_reason: str,
    limitations: tuple[str, ...],
    prior_policy_version: str | None,
    prior_result_hash: str | None,
    expected_active_pointer: str,
) -> PolicyActivation:
    """Append a human-selected policy decision, failing closed on stale authority."""
    history = load_policy_history(workspace)
    try:
        draft = PolicyActivation(
            activated_policy_version=policy_version,
            policy_hash=policy_hash,
            result_hash=result_hash,
            comparison_hash=comparison_hash,
            reviewer_id=reviewer_id,
            activation_reason=activation_reason,
            limitations=limitations,
            prior_policy_version=prior_policy_version,
            prior_result_hash=prior_result_hash,
            expected_active_pointer=expected_active_pointer,
            activation_hash="sha256:" + "0" * 64,
        )
    except ValidationError as exc:
        raise AssessmentWorkflowError("policy activation request is invalid") from exc

    bootstrap = draft.expected_active_pointer == "absent"
    if bootstrap:
        if history.active_pointer is not None or history.activations:
            raise AssessmentWorkflowError("active policy pointer already exists")
    else:
        current = history.activations[-1] if history.activations else None
        if current is None or history.active_pointer != expected_active_pointer:
            raise AssessmentWorkflowError("policy activation pointer is stale")
        if (
            current.activated_policy_version != prior_policy_version
            or current.result_hash != prior_result_hash
        ):
            raise AssessmentWorkflowError("policy activation ancestry is stale")

    activation = PolicyActivation.model_validate(
        {
            **draft.model_dump(mode="json"),
            "activation_hash": _activation_hash(draft),
        }
    )
    updated = PolicyHistory(
        runs=history.runs,
        comparisons=history.comparisons,
        activations=(*history.activations, activation),
        active_pointer=activation.activation_hash,
    )
    _write_policy_history(workspace, updated)
    return activation
