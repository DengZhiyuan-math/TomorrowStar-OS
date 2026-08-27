"""Strict, contribution-grounded career evidence contracts.

These contracts record evidence and review state.  They deliberately do not
derive a person's capability from a document, title, repository, or ontology.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Literal

from pydantic import Field, model_validator

from ..validation.models import StrictModel

ID_PATTERN = r"^[a-z][a-z0-9]*(?:[._-][a-z0-9]+)*$"
SHA256_PATTERN = r"^sha256:[0-9a-f]{64}$"
COMMIT_PATTERN = r"^[0-9a-f]{40}$"
MONTH_PATTERN = r"^\d{4}-(0[1-9]|1[0-2])$"
Identifier = Annotated[str, Field(pattern=ID_PATTERN)]

ExperienceType = Literal[
    "employment",
    "project",
    "research",
    "publication",
    "education",
    "teaching",
    "open_source",
    "internship",
    "related",
]
ResponsibilityKind = Literal["user", "team", "other_person", "non_responsibility"]
# ``codex_assisted`` remains accepted only for sealed legacy fixture reads.
# New audit records use the provider-neutral vocabulary in audit.models.
AssistanceKind = Literal[
    "none", "codex_assisted", "third_party", "coding-agent-assisted", "third-party-assisted"
]
ConfirmationStatus = Literal["confirmed", "unconfirmed", "rejected"]
CompletionStatus = Literal["delivered", "partial", "planned_only", "unresolved"]
EvidenceKind = Literal["plan", "handoff", "acceptance_record", "audit", "user_confirmation"]
ProofLimit = Literal[
    "intent_or_assignment",
    "recorded_delivery",
    "observed_state_defects_limitations",
    "personal_responsibility_and_claimed_capability",
]
AssessmentSourceKind = Literal[
    "contribution",
    "experience",
    "credential",
    "title",
    "repository",
    "resume-skill-list",
    "ontology-relation",
]


class AssessmentAdmissionStatus(StrEnum):
    """Whether a proposal may enter formal user-level mastery."""

    ADMITTED = "admitted"
    PENDING_CONFIRMATION = "pending-confirmation"
    UNVERIFIED_CANDIDATE = "unverified-candidate"


def _unique_ids(values: tuple[str, ...], field_name: str) -> tuple[str, ...]:
    if len(values) != len(set(values)):
        raise ValueError(f"{field_name} must contain unique identifiers")
    return values


class Experience(StrictModel):
    schema_version: Literal["experience/v1"] = "experience/v1"
    id: Identifier = Field(pattern=ID_PATTERN)
    experience_type: ExperienceType
    title: str = Field(min_length=1)
    contribution_ids: tuple[Identifier, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_contribution_ids(self) -> Experience:
        _unique_ids(self.contribution_ids, "contribution_ids")
        return self


class Contribution(StrictModel):
    schema_version: Literal["contribution/v1"] = "contribution/v1"
    id: Identifier = Field(pattern=ID_PATTERN)
    experience_id: Identifier = Field(pattern=ID_PATTERN)
    summary: str = Field(min_length=1)
    claim_ids: tuple[Identifier, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_claim_ids(self) -> Contribution:
        _unique_ids(self.claim_ids, "claim_ids")
        return self


class ContributionClaim(StrictModel):
    schema_version: Literal["contribution-claim/v1"] = "contribution-claim/v1"
    id: Identifier = Field(pattern=ID_PATTERN)
    contribution_id: Identifier = Field(pattern=ID_PATTERN)
    statement: str = Field(min_length=1)
    responsibility: ResponsibilityKind
    assistance: AssistanceKind
    confirmation_status: ConfirmationStatus
    completion_status: CompletionStatus
    limitations: tuple[str, ...] = Field(min_length=1)


class Evidence(StrictModel):
    schema_version: Literal["evidence/v1"] = "evidence/v1"
    id: Identifier = Field(pattern=ID_PATTERN)
    kind: EvidenceKind
    proof_limit: ProofLimit
    repository: str = Field(min_length=1)
    pinned_commit: str = Field(pattern=COMMIT_PATTERN)
    tracked_path: str = Field(min_length=1)
    section_locator: str = Field(min_length=1)
    content_hash: str = Field(pattern=SHA256_PATTERN)

    @model_validator(mode="after")
    def validate_proof_limit(self) -> Evidence:
        expected = {
            "plan": "intent_or_assignment",
            "handoff": "recorded_delivery",
            "acceptance_record": "recorded_delivery",
            "audit": "observed_state_defects_limitations",
            "user_confirmation": "personal_responsibility_and_claimed_capability",
        }[self.kind]
        if self.proof_limit != expected:
            raise ValueError(f"{self.kind} evidence requires proof_limit={expected}")
        return self


class ClaimEvidenceLink(StrictModel):
    schema_version: Literal["claim-evidence-link/v1"] = "claim-evidence-link/v1"
    claim_id: Identifier = Field(pattern=ID_PATTERN)
    evidence_id: Identifier = Field(pattern=ID_PATTERN)
    section_locator: str = Field(min_length=1)


class Skill(StrictModel):
    schema_version: Literal["skill/v1"] = "skill/v1"
    id: Identifier = Field(pattern=ID_PATTERN)
    name: str = Field(min_length=1)


class SkillAlias(StrictModel):
    """Pinned ontology alias metadata; never evidence of capability."""

    schema_version: Literal["skill-alias/v1"] = "skill-alias/v1"
    alias: str = Field(min_length=1)
    skill_id: Identifier = Field(pattern=ID_PATTERN)
    ontology_source_id: str = Field(min_length=1)
    pinned_revision: str = Field(pattern=COMMIT_PATTERN)


class OntologyRelation(StrictModel):
    """Descriptive ontology adjacency with its own pinned provenance."""

    schema_version: Literal["ontology-relation/v1"] = "ontology-relation/v1"
    source_skill_id: Identifier = Field(pattern=ID_PATTERN)
    target_skill_id: Identifier = Field(pattern=ID_PATTERN)
    relation_kind: Literal["dependency", "implies_knowledge"]
    ontology_source_id: str = Field(min_length=1)
    pinned_revision: str = Field(pattern=COMMIT_PATTERN)


class SkillNormalizationRecord(StrictModel):
    """Reviewable normalization output, deliberately separate from mastery records."""

    schema_version: Literal["skill-normalization-record/v1"] = "skill-normalization-record/v1"
    original_text: str = Field(min_length=1)
    normalized_text: str = Field(min_length=1)
    matched_alias: str | None = None
    candidate_skill_ids: tuple[Identifier, ...] = ()
    ontology_source_id: str | None = None
    pinned_revision: str | None = Field(default=None, pattern=COMMIT_PATTERN)
    review_status: Literal["matched", "review-required", "unmatched", "descriptive-only"]
    relation_kind: Literal["dependency", "implies_knowledge"] | None = None


class DurationEvidence(StrictModel):
    schema_version: Literal["duration-evidence/v1"] = "duration-evidence/v1"
    state: Literal["verified", "not_verified", "unavailable"]
    start_month: str | None = Field(default=None, pattern=MONTH_PATTERN)
    end_month: str | None = Field(default=None, pattern=MONTH_PATTERN)

    @model_validator(mode="after")
    def validate_month_range(self) -> DurationEvidence:
        if (self.start_month is None) != (self.end_month is None):
            raise ValueError("start_month and end_month must appear together")
        if self.start_month and self.end_month and self.end_month < self.start_month:
            raise ValueError("end_month must not precede start_month")
        return self


class AssessmentLineage(StrictModel):
    schema_version: Literal["assessment-lineage/v1"] = "assessment-lineage/v1"
    source_kind: AssessmentSourceKind
    contribution_id: Identifier = Field(pattern=ID_PATTERN)


class MasteryAnchor(StrictModel):
    """One accepted, schema-versioned capability anchor from the project contract."""

    schema_version: Literal["mastery-anchor/v1"] = "mastery-anchor/v1"
    anchor_id: str = Field(pattern=r"^anchor-[0-9]{1,3}-[0-9]{1,3}$")
    inclusive_range: tuple[int, int]
    capability_text: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_identity_and_range(self) -> MasteryAnchor:
        low, high = self.inclusive_range
        if not 0 <= low <= high <= 100:
            raise ValueError("inclusive_range must be inside 0 through 100")
        if self.anchor_id != f"anchor-{low}-{high}":
            raise ValueError("anchor_id must name inclusive_range")
        return self


MASTERY_ANCHORS: tuple[MasteryAnchor, ...] = (
    MasteryAnchor(
        anchor_id="anchor-0-19",
        inclusive_range=(0, 19),
        capability_text="Exposure only; cannot complete a practical task",
    ),
    MasteryAnchor(
        anchor_id="anchor-20-39",
        inclusive_range=(20, 39),
        capability_text=(
            "Understands fundamentals; can complete simple tasks with explicit guidance"
        ),
    ),
    MasteryAnchor(
        anchor_id="anchor-40-54",
        inclusive_range=(40, 54),
        capability_text="Can complete bounded practical tasks with documentation or guidance",
    ),
    MasteryAnchor(
        anchor_id="anchor-55-69",
        inclusive_range=(55, 69),
        capability_text="Can independently complete common, well-bounded practical tasks",
    ),
    MasteryAnchor(
        anchor_id="anchor-70-79",
        inclusive_range=(70, 79),
        capability_text=(
            "Can independently handle complex problems and explain and defend decisions"
        ),
    ),
    MasteryAnchor(
        anchor_id="anchor-80-89",
        inclusive_range=(80, 89),
        capability_text=(
            "Can own a complete module or system, including failures, trade-offs, and maintenance"
        ),
    ),
    MasteryAnchor(
        anchor_id="anchor-90-95",
        inclusive_range=(90, 95),
        capability_text=(
            "Has repeatedly carried advanced responsibility in multiple real contexts "
            "and can guide others"
        ),
    ),
    MasteryAnchor(
        anchor_id="anchor-96-100",
        inclusive_range=(96, 100),
        capability_text="Rare; sustained, broad, and strongly verified expert capability",
    ),
)


class MasteryAnchorFit(StrictModel):
    """Observable capability anchor and the score selected within it."""

    schema_version: Literal["mastery-anchor-fit/v1"] = "mastery-anchor-fit/v1"
    anchor_id: str = Field(pattern=r"^anchor-[0-9]{1,3}-[0-9]{1,3}$")
    anchor_range: tuple[int, int]
    anchor_text: str = Field(min_length=1)
    anchor_basis: str = Field(min_length=1)
    exact_score_basis: str = Field(min_length=1)
    next_anchor_not_established: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_range(self) -> MasteryAnchorFit:
        low, high = self.anchor_range
        if not 0 <= low <= high <= 100:
            raise ValueError("anchor_range must be inside 0 through 100")
        if self.anchor_id != f"anchor-{low}-{high}":
            raise ValueError("anchor_id must name anchor_range")
        expected = next(
            (item for item in MASTERY_ANCHORS if item.anchor_id == self.anchor_id), None
        )
        if expected is None or expected.inclusive_range != self.anchor_range:
            raise ValueError("anchor_id must be an accepted mastery anchor")
        if self.anchor_text != expected.capability_text:
            raise ValueError("anchor_text must exactly match the accepted anchor")
        for value in (self.anchor_basis, self.exact_score_basis, self.next_anchor_not_established):
            if not value.strip():
                raise ValueError("mastery anchor bases cannot be blank")
        return self


class AssessmentJudgmentBasis(StrictModel):
    """Independent observable bases for the three non-interchangeable judgments."""

    schema_version: Literal["assessment-judgment-basis/v1"] = "assessment-judgment-basis/v1"
    demonstrated_mastery_basis: str = Field(min_length=1)
    skill_centrality_basis: str = Field(min_length=1)
    evidence_confidence_basis: str = Field(min_length=1)

    @model_validator(mode="after")
    def reject_blank_bases(self) -> AssessmentJudgmentBasis:
        for value in (
            self.demonstrated_mastery_basis,
            self.skill_centrality_basis,
            self.evidence_confidence_basis,
        ):
            if not value.strip():
                raise ValueError("assessment judgment bases cannot be blank")
        return self


class AssessmentSourceEnvelope(StrictModel):
    """Hash-bound assessment provenance, distinct from reviewed user truth."""

    schema_version: Literal["assessment-source-envelope/v1"] = "assessment-source-envelope/v1"
    authority_label: Literal["reviewed-user-truth", "derived-counterfactual"]
    audit_id: str = Field(pattern=r"^audit-[a-z0-9-]+$")
    audit_snapshot_hash: str = Field(pattern=SHA256_PATTERN)
    fixture_hash: str = Field(pattern=SHA256_PATTERN)
    source_manifest_hash: str = Field(pattern=SHA256_PATTERN)
    conclusion_lineage_hash: str = Field(pattern=SHA256_PATTERN)
    effective_conclusion_hash: str = Field(pattern=SHA256_PATTERN)
    contribution_id: Identifier = Field(pattern=ID_PATTERN)
    evidence_ids: tuple[Identifier, ...] = Field(min_length=1)
    question_ids: tuple[str, ...] = Field(min_length=1)
    answer_ids: tuple[str, ...] = Field(min_length=1)
    attribution_hash: str = Field(pattern=SHA256_PATTERN)

    @model_validator(mode="after")
    def validate_source_ids(self) -> AssessmentSourceEnvelope:
        _unique_ids(self.evidence_ids, "evidence_ids")
        _unique_ids(self.question_ids, "question_ids")
        _unique_ids(self.answer_ids, "answer_ids")
        return self


class SkillResolutionDecision(StrictModel):
    """Explicit D-03 Skill normalization authority for an assessment candidate."""

    schema_version: Literal["skill-resolution-decision/v1"] = "skill-resolution-decision/v1"
    decision_id: Identifier = Field(pattern=ID_PATTERN)
    candidate_skill_id: Identifier = Field(pattern=ID_PATTERN)
    resolution: Literal["confirmed-existing-skill", "created-specific-skill"]
    authority_label: Literal["human-reviewed", "synthetic-calibration"]
    reviewer_id: str = Field(min_length=1)
    reason: str = Field(min_length=1)


class SpecificSkillProposal(StrictModel):
    """A score-eligible, independently traceable Contribution--Skill candidate."""

    schema_version: Literal["specific-skill-proposal/v1"] = "specific-skill-proposal/v1"
    proposal_id: Identifier = Field(pattern=ID_PATTERN)
    skill_id: Identifier = Field(pattern=ID_PATTERN)
    contribution_id: Identifier = Field(pattern=ID_PATTERN)
    audit_id: str = Field(pattern=r"^audit-[a-z0-9-]+$")
    fixture_hash: str = Field(pattern=SHA256_PATTERN)
    source_manifest_hash: str = Field(pattern=SHA256_PATTERN)
    conclusion_lineage_hash: str = Field(pattern=SHA256_PATTERN)
    conclusion_entry_ids: tuple[str, ...] = Field(min_length=1)
    evidence_ids: tuple[Identifier, ...] = Field(min_length=1)
    answer_question_ids: tuple[str, ...] = Field(min_length=1)
    attribution_area_ids: tuple[str, ...] = Field(min_length=1)
    normalization_record_hash: str = Field(pattern=SHA256_PATTERN)

    @model_validator(mode="after")
    def validate_independent_source_custody(self) -> SpecificSkillProposal:
        _unique_ids(self.conclusion_entry_ids, "conclusion_entry_ids")
        _unique_ids(self.evidence_ids, "evidence_ids")
        _unique_ids(self.answer_question_ids, "answer_question_ids")
        _unique_ids(self.attribution_area_ids, "attribution_area_ids")
        return self


class AdmissionDecision(StrictModel):
    schema_version: Literal["assessment-admission-decision/v1"] = "assessment-admission-decision/v1"
    assessment_id: Identifier = Field(pattern=ID_PATTERN)
    policy_version: str = Field(min_length=1)
    admission_status: AssessmentAdmissionStatus
    reason: str = Field(min_length=1)
    reason_code: Literal[
        "numeric-policy",
        "high-mastery-low-confidence",
        "provenance-review-required",
        "insufficient-basis",
    ]


class AggregationPolicy(StrictModel):
    """Candidate calibration policy; never an implicitly active product policy."""

    schema_version: Literal["aggregation-policy/v1"] = "aggregation-policy/v1"
    policy_version: str = Field(min_length=1)
    high_mastery_min: int = Field(ge=0, le=100)
    strict_confidence_min: int = Field(ge=0, le=100)
    activation_status: Literal["candidate", "active"] = "candidate"
    notice: str = Field(min_length=1)


class CalibrationCaseResult(StrictModel):
    """One deterministic calibration input evaluated under a candidate policy."""

    schema_version: Literal["calibration-case-result/v1"] = "calibration-case-result/v1"
    case_id: Identifier = Field(pattern=ID_PATTERN)
    skill_id: Identifier = Field(pattern=ID_PATTERN)
    mastery: int = Field(ge=0, le=100)
    band: str = Field(pattern=r"^anchor-[0-9]{1,3}-[0-9]{1,3}$")
    admission_status: AssessmentAdmissionStatus
    calibration_decision: Literal["admit", "defer"]
    reviewer_disagreement: bool
    regression_labels: tuple[str, ...] = ()


class PolicyRunResult(StrictModel):
    """Content-addressed execution of exactly one candidate policy."""

    schema_version: Literal["policy-run-result/v1"] = "policy-run-result/v1"
    policy_version: str = Field(min_length=1)
    input_hashes: tuple[str, ...] = Field(min_length=1)
    policy_hash: str = Field(pattern=SHA256_PATTERN)
    run_sequence: int = Field(ge=1)
    case_results: tuple[CalibrationCaseResult, ...] = Field(min_length=1)
    result_hash: str = Field(pattern=SHA256_PATTERN)

    @model_validator(mode="after")
    def validate_case_identity(self) -> PolicyRunResult:
        _unique_ids(tuple(item.case_id for item in self.case_results), "case_results")
        return self


class SkillPolicyDelta(StrictModel):
    """Exact per-case, per-Skill policy effect; no averaged threshold behavior."""

    schema_version: Literal["skill-policy-delta/v1"] = "skill-policy-delta/v1"
    case_id: Identifier = Field(pattern=ID_PATTERN)
    skill_id: Identifier = Field(pattern=ID_PATTERN)
    mastery_delta: int
    band_change: bool
    admission_change: bool
    baseline_admission: AssessmentAdmissionStatus
    candidate_admission: AssessmentAdmissionStatus


class PolicyComparison(StrictModel):
    """A non-activating, same-input candidate comparison."""

    schema_version: Literal["policy-comparison/v1"] = "policy-comparison/v1"
    input_hashes: tuple[str, ...] = Field(min_length=1)
    baseline_policy_version: str = Field(min_length=1)
    baseline_result_hash: str = Field(pattern=SHA256_PATTERN)
    candidate_policy_version: str = Field(min_length=1)
    candidate_result_hash: str = Field(pattern=SHA256_PATTERN)
    skill_deltas: tuple[SkillPolicyDelta, ...]
    reviewer_disagreements: tuple[Identifier, ...] = ()
    run_variance: int = Field(ge=0)
    regressions: tuple[str, ...] = ()
    active_policy_version: None = None
    comparison_hash: str = Field(pattern=SHA256_PATTERN)


class PolicyHistory(StrictModel):
    """Immutable calibration evidence; the active pointer is intentionally optional."""

    schema_version: Literal["policy-history/v1"] = "policy-history/v1"
    runs: tuple[PolicyRunResult, ...] = ()
    comparisons: tuple[PolicyComparison, ...] = ()
    active_pointer: str | None = None


class ContributionSkillAssessment(StrictModel):
    schema_version: Literal["contribution-skill-assessment/v1"] = "contribution-skill-assessment/v1"
    id: Identifier = Field(pattern=ID_PATTERN)
    skill_id: Identifier = Field(pattern=ID_PATTERN)
    contribution_id: Identifier = Field(pattern=ID_PATTERN)
    lineage: AssessmentLineage
    demonstrated_mastery: int = Field(ge=0, le=100)
    skill_centrality: int = Field(ge=0, le=100)
    evidence_confidence: int = Field(ge=0, le=100)
    context: str = Field(min_length=1)
    duration: DurationEvidence
    basis_claim_ids: tuple[Identifier, ...] = Field(min_length=1)
    assessment_status: Literal["partial", "unresolved", "reviewed", "derived-counterfactual"]
    # These inputs remain separate from the three judgments.  They preserve the
    # Phase 3 audit boundary and are evaluated by admission, never by score mutation.
    origin_status: Literal[
        "audit-verified", "self-assessed-unverified", "derived-counterfactual"
    ] = "audit-verified"
    attribution_status: Literal["resolved", "unresolved", "disputed"] = "resolved"
    assistance_status: Literal["resolved", "unresolved"] = "resolved"
    substantive_review_complete: bool = False
    mastery_anchor_fit: MasteryAnchorFit | None = None
    exact_score_basis: str | None = None
    judgment_basis: AssessmentJudgmentBasis | None = None
    source_envelope: AssessmentSourceEnvelope | None = None

    @model_validator(mode="after")
    def validate_lineage_and_basis(self) -> ContributionSkillAssessment:
        if self.lineage.contribution_id != self.contribution_id:
            raise ValueError("lineage contribution_id must match assessment contribution_id")
        if not self.context.strip():
            raise ValueError("context cannot be blank")
        _unique_ids(self.basis_claim_ids, "basis_claim_ids")
        effective_fields = (
            self.mastery_anchor_fit,
            self.exact_score_basis,
            self.judgment_basis,
            self.source_envelope,
        )
        if any(value is not None for value in effective_fields) and not all(
            value is not None for value in effective_fields
        ):
            raise ValueError(
                "effective assessments require anchor, score basis, and source envelope"
            )
        if self.mastery_anchor_fit is not None:
            low, high = self.mastery_anchor_fit.anchor_range
            if not low <= self.demonstrated_mastery <= high:
                raise ValueError("demonstrated mastery must fall inside its anchor")
            if not self.exact_score_basis or not self.exact_score_basis.strip():
                raise ValueError("exact_score_basis cannot be blank")
        return self


class AssessmentReview(StrictModel):
    """One immutable D-10-complete review of an assessment's effective value."""

    schema_version: Literal["assessment-review/v1"] = "assessment-review/v1"
    review_id: str = Field(pattern=r"^assessment-review-[a-z0-9-]+$")
    outcome: Literal["confirm", "edit", "insufficient-basis"]
    reviewer_id: str = Field(min_length=1)
    reason: str = Field(min_length=1)
    attribution_checked: bool
    anchor_fit_checked: bool
    all_judgments_checked: bool
    sequence: int = Field(ge=1)
    before_effective_hash: str = Field(pattern=SHA256_PATTERN)
    after_effective_hash: str = Field(pattern=SHA256_PATTERN)

    @model_validator(mode="after")
    def require_substantive_acknowledgments(self) -> AssessmentReview:
        if not all((self.attribution_checked, self.anchor_fit_checked, self.all_judgments_checked)):
            raise ValueError("assessment review requires all substantive acknowledgments")
        return self


class AssessmentVersion(StrictModel):
    """Immutable source-audit version containing a complete assessment lineage."""

    schema_version: Literal["assessment-version/v1"] = "assessment-version/v1"
    version_id: str = Field(pattern=r"^assessment-version-[a-z0-9-]+$")
    source_audit_id: str = Field(pattern=r"^audit-[a-z0-9-]+$")
    previous_version_hash: str | None = Field(default=None, pattern=SHA256_PATTERN)
    original_proposal: ContributionSkillAssessment
    original_proposal_hash: str = Field(pattern=SHA256_PATTERN)
    effective_assessment: ContributionSkillAssessment
    effective_assessment_hash: str = Field(pattern=SHA256_PATTERN)
    admission: AdmissionDecision
    reviews: tuple[AssessmentReview, ...] = ()
    version_hash: str = Field(pattern=SHA256_PATTERN)


class AnchorPromotionDecision(StrictModel):
    """A separate, hash-bound request to prove only the next capability anchor."""

    schema_version: Literal["anchor-promotion-decision/v1"] = "anchor-promotion-decision/v1"
    decision_id: Identifier = Field(pattern=ID_PATTERN)
    policy_version: str = Field(min_length=1)
    policy_input_hash: str = Field(pattern=SHA256_PATTERN)
    skill_id: Identifier = Field(pattern=ID_PATTERN)
    target_anchor_id: str = Field(pattern=r"^anchor-[0-9]{1,3}-[0-9]{1,3}$")
    promoted_score: int = Field(ge=0, le=100)
    assessment_ids: tuple[Identifier, ...] = Field(min_length=2)
    distinct_behaviors: tuple[str, ...] = Field(min_length=1)
    behavior_assessment_ids: tuple[Identifier, ...] = Field(min_length=1)
    behavior_audit_bases: tuple[str, ...] = Field(min_length=1)
    distinct_contexts: tuple[str, ...] = Field(min_length=2)
    rationale: str = Field(min_length=1)
    exact_score_basis: str | None = None

    @model_validator(mode="after")
    def validate_distinct_support(self) -> AnchorPromotionDecision:
        _unique_ids(self.assessment_ids, "assessment_ids")
        if not all(value.strip() for value in self.distinct_behaviors + self.behavior_audit_bases):
            raise ValueError("promotion behavior and audit bases cannot be blank")
        if not self.rationale.strip() or (
            self.exact_score_basis is not None and not self.exact_score_basis.strip()
        ):
            raise ValueError("promotion rationale and exact score basis cannot be blank")
        return self


class CalibratedUserSkillResult(StrictModel):
    """One specific-Skill calibration output with no evidence-volume bonus."""

    schema_version: Literal["calibrated-user-skill-result/v1"] = "calibrated-user-skill-result/v1"
    result_id: Identifier = Field(pattern=ID_PATTERN)
    skill_id: Identifier = Field(pattern=ID_PATTERN)
    mastery: int = Field(ge=0, le=100)
    anchor_id: str = Field(pattern=r"^anchor-[0-9]{1,3}-[0-9]{1,3}$")
    policy_version: str = Field(min_length=1)
    baseline_assessment_id: Identifier = Field(pattern=ID_PATTERN)
    admitted_assessment_ids: tuple[Identifier, ...] = Field(min_length=1)
    source_envelope: AssessmentSourceEnvelope
    authority_label: Literal["reviewed-user-truth", "derived-counterfactual"]
    aggregation_rationale: str = Field(min_length=1)
    promotion_decision: AnchorPromotionDecision | None = None
    supporting_contexts: tuple[str, ...] = ()
    suppressed_duplicate_relationships: tuple[str, ...] = ()

    @model_validator(mode="after")
    def validate_baseline(self) -> CalibratedUserSkillResult:
        _unique_ids(self.admitted_assessment_ids, "admitted_assessment_ids")
        if self.baseline_assessment_id not in self.admitted_assessment_ids:
            raise ValueError("baseline assessment must be admitted")
        if self.authority_label != self.source_envelope.authority_label:
            raise ValueError("result authority must retain source authority")
        anchor = next((item for item in MASTERY_ANCHORS if item.anchor_id == self.anchor_id), None)
        if anchor is None or not (
            anchor.inclusive_range[0] <= self.mastery <= anchor.inclusive_range[1]
        ):
            raise ValueError("result mastery must fall inside its anchor")
        if self.promotion_decision is not None:
            if self.promotion_decision.skill_id != self.skill_id:
                raise ValueError("promotion decision must name the result Skill")
            if self.promotion_decision.policy_version != self.policy_version:
                raise ValueError("promotion decision must name the result policy")
        return self


class UserSkillView(StrictModel):
    schema_version: Literal["user-skill-view/v1"] = "user-skill-view/v1"
    skill_id: Identifier = Field(pattern=ID_PATTERN)
    mastery: int = Field(default=0, ge=0, le=100)
    assessment_ids: tuple[Identifier, ...] = Field(min_length=1)
    expectation_status: Literal["fixture-test-expectation"] = "fixture-test-expectation"
    policy_marker: Literal["fixture-test-expectation"] = "fixture-test-expectation"
    # Retained only to load the phase-02 tracer fixture; it is not a score dimension.
    fixture_notice: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_assessment_ids(self) -> UserSkillView:
        _unique_ids(self.assessment_ids, "assessment_ids")
        return self


class CareerEvidenceFixture(StrictModel):
    schema_version: Literal["career-evidence-fixture/v1"]
    fixture_notice: str = Field(min_length=1)
    experiences: tuple[Experience, ...] = Field(min_length=1)
    contributions: tuple[Contribution, ...] = Field(min_length=1)
    claims: tuple[ContributionClaim, ...] = Field(min_length=1)
    evidence: tuple[Evidence, ...] = Field(min_length=1)
    claim_evidence_links: tuple[ClaimEvidenceLink, ...] = Field(min_length=1)
    skills: tuple[Skill, ...] = Field(min_length=1)
    assessments: tuple[ContributionSkillAssessment, ...] = ()
    user_skill_views: tuple[UserSkillView, ...] = ()


class InvariantViolation(StrictModel):
    schema_version: Literal["invariant-violation/v1"] = "invariant-violation/v1"
    code: str = Field(pattern=r"^[a-z][a-z0-9_-]*(?:\.[a-z][a-z0-9_-]*)+$")
    path: str = Field(min_length=1)


class FixtureValidationResult(StrictModel):
    schema_version: Literal["fixture-validation-result/v1"] = "fixture-validation-result/v1"
    valid: Literal[True] = True
    fixture_hash: str = Field(pattern=SHA256_PATTERN)
    experience_count: int = Field(ge=0)
    contribution_count: int = Field(ge=0)
    assessment_count: int = Field(ge=0)
    user_skill_count: int = Field(ge=0)
