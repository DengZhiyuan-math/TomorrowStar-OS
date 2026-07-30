"""Strict, contribution-grounded career evidence contracts.

These contracts record evidence and review state.  They deliberately do not
derive a person's capability from a document, title, repository, or ontology.
"""

from __future__ import annotations

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
AssistanceKind = Literal["none", "codex_assisted", "third_party"]
ConfirmationStatus = Literal["confirmed", "unconfirmed", "rejected"]
CompletionStatus = Literal["delivered", "partial", "planned_only", "unresolved"]
EvidenceKind = Literal["plan", "handoff", "acceptance_record", "audit", "user_confirmation"]
ProofLimit = Literal[
    "intent_or_assignment",
    "recorded_delivery",
    "observed_state_defects_limitations",
    "personal_responsibility_and_claimed_capability",
]


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
    source_kind: Literal["contribution"]
    contribution_id: Identifier = Field(pattern=ID_PATTERN)


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
    assessment_status: Literal["partial", "unresolved", "reviewed"]

    @model_validator(mode="after")
    def validate_lineage_and_basis(self) -> ContributionSkillAssessment:
        if self.lineage.contribution_id != self.contribution_id:
            raise ValueError("lineage contribution_id must match assessment contribution_id")
        if not self.context.strip():
            raise ValueError("context cannot be blank")
        _unique_ids(self.basis_claim_ids, "basis_claim_ids")
        return self


class UserSkillView(StrictModel):
    schema_version: Literal["user-skill-view/v1"] = "user-skill-view/v1"
    skill_id: Identifier = Field(pattern=ID_PATTERN)
    assessment_ids: tuple[Identifier, ...] = Field(min_length=1)
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
    assessments: tuple[ContributionSkillAssessment, ...] = Field(min_length=1)
    user_skill_views: tuple[UserSkillView, ...] = Field(min_length=1)


class InvariantViolation(StrictModel):
    schema_version: Literal["invariant-violation/v1"] = "invariant-violation/v1"
    code: str = Field(pattern=r"^[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)+$")
    path: str = Field(min_length=1)


class FixtureValidationResult(StrictModel):
    schema_version: Literal["fixture-validation-result/v1"] = "fixture-validation-result/v1"
    valid: Literal[True] = True
    fixture_hash: str = Field(pattern=SHA256_PATTERN)
    experience_count: int = Field(ge=0)
    contribution_count: int = Field(ge=0)
    assessment_count: int = Field(ge=0)
    user_skill_count: int = Field(ge=0)
