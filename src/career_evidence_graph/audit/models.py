# ruff: noqa: E501

from __future__ import annotations

from typing import Literal

from pydantic import Field, model_validator

from ..validation.models import StrictModel

AuditStatus = Literal["active", "paused", "reviewing", "completed", "rejected"]
AuditArea = Literal["implementation", "debugging", "operation", "responsibility", "assistance"]
Difficulty = Literal["hard", "intermediate", "simple"]
CoverageStatus = Literal["pending", "verified", "skipped", "unresolved"]
CapabilityArea = Literal[
    "technical-design",
    "implementation",
    "research-development",
    "debugging",
    "operation",
    "organization",
    "collaboration",
]


class ArtifactFact(StrictModel):
    schema_version: Literal["audit-artifact-fact/v1"] = "audit-artifact-fact/v1"
    evidence_id: str = Field(pattern=r"^[a-z][a-z0-9-]+$")
    source_locator: str = Field(min_length=1)
    statement: str = Field(min_length=1)


class AuditQuestion(StrictModel):
    schema_version: Literal["audit-question/v1"] = "audit-question/v1"
    id: str = Field(pattern=r"^question-[a-z0-9-]+$")
    reason: str = Field(min_length=1)
    prompt: str = Field(min_length=1)
    area: AuditArea
    status: Literal["unanswered", "answered", "skipped"] = "unanswered"
    area_id: str | None = None
    difficulty: Difficulty = "hard"
    inspection_reference: str | None = None
    follow_up_count: int = Field(default=0, ge=0, le=1)


class ProbeArea(StrictModel):
    """One fact-grounded capability ladder selected for a Contribution."""

    schema_version: Literal["audit-probe-area/v1"] = "audit-probe-area/v1"
    area_id: CapabilityArea
    inspected_fact_ids: tuple[str, ...] = Field(min_length=1)
    unverified_capability: str = Field(min_length=1)
    demanding_prompt: str = Field(min_length=1)
    intermediate_prompt: str = Field(min_length=1)
    simple_prompt: str = Field(min_length=1)
    immediately_higher_capability: str = Field(min_length=1)

    @model_validator(mode="after")
    def distinct_ladder_prompts(self) -> ProbeArea:
        prompts = (self.demanding_prompt, self.intermediate_prompt, self.simple_prompt)
        if len(set(prompts)) != len(prompts):
            raise ValueError("capability ladder prompts must be distinct")
        return self


class ProbePlan(StrictModel):
    """Validated set of only Contribution-relevant capability questions."""

    schema_version: Literal["audit-probe-plan/v1"] = "audit-probe-plan/v1"
    contribution_id: str = Field(pattern=r"^contrib-stoa-[a-z0-9-]+$")
    areas: tuple[ProbeArea, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def unique_capability_areas(self) -> ProbePlan:
        if len({area.area_id for area in self.areas}) != len(self.areas):
            raise ValueError("capability areas must be unique")
        return self


class BoundaryDecision(StrictModel):
    """A data-only decision bound to the exact displayed question and answer."""

    schema_version: Literal["audit-boundary-decision/v1"] = "audit-boundary-decision/v1"
    question_id: str = Field(pattern=r"^question-[a-z0-9-]+$")
    answer: str = Field(min_length=1)
    outcome: Literal["established", "incomplete", "attribution-signal"]
    rationale: str = Field(min_length=1)
    strongest_capability: str | None = None
    next_higher_not_established: str | None = None

    @model_validator(mode="after")
    def capability_boundary_only_on_established(self) -> BoundaryDecision:
        fields = (self.strongest_capability, self.next_higher_not_established)
        if self.outcome == "established" and not all(fields):
            raise ValueError("established decision requires both capability boundaries")
        if self.outcome != "established" and any(fields):
            raise ValueError("only established decisions may include capability boundaries")
        return self


class AuditAnswer(StrictModel):
    schema_version: Literal["audit-answer/v1"] = "audit-answer/v1"
    question_id: str = Field(pattern=r"^question-[a-z0-9-]+$")
    answer: str = Field(min_length=1)
    skipped: bool = False


class AuditAttribution(StrictModel):
    schema_version: Literal["audit-attribution/v1"] = "audit-attribution/v1"
    ownership: Literal["user-owned", "team-owned", "other-person-owned", "unresolved"]
    assistance: Literal["none", "coding-agent-assisted", "third-party-assisted", "unresolved"]
    tool: str | None = None
    model: str | None = None


class ConclusionEntry(StrictModel):
    schema_version: Literal["audit-conclusion-entry/v1"] = "audit-conclusion-entry/v1"
    id: str = Field(pattern=r"^entry-[a-z0-9-]+$")
    area: str = Field(min_length=1)
    strongest_capability: str = Field(min_length=1)
    next_higher_not_established: str = Field(min_length=1)
    basis: tuple[str, ...] = Field(min_length=1)
    artifact_references: tuple[str, ...] = ()
    answer_references: tuple[str, ...] = ()
    source_type: Literal["answer-only", "documentary-context-only"] = "answer-only"
    responsibility_boundary: str = Field(min_length=1)
    assistance_boundary: str = Field(min_length=1)
    verification: Literal["audit-verified", "self-assessed-unverified", "unresolved"]
    conflicts: tuple[str, ...] = ()
    unresolved_gaps: tuple[str, ...] = ()
    review: Literal["pending", "edited", "confirmed", "rejected"] = "pending"
    correction: str | None = None


class AuditConclusion(StrictModel):
    schema_version: Literal["audit-conclusion/v1"] = "audit-conclusion/v1"
    entries: tuple[ConclusionEntry, ...] = Field(min_length=1)
    whole_review: Literal["pending", "confirmed", "rejected"] = "pending"
    original_proposal: dict[str, object]
    review_reason: str | None = None


class ConclusionReview(StrictModel):
    schema_version: Literal["audit-conclusion-review/v1"] = "audit-conclusion-review/v1"
    review_id: str = Field(pattern=r"^review-[a-z0-9-]+$")
    target: Literal["entry", "whole-conclusion"]
    outcome: Literal["confirm", "edit", "reject"]
    reviewer_id: str = Field(min_length=1)
    reason: str = Field(min_length=1)
    entry_id: str | None = None
    correction: str | None = None


class AuditAction(StrictModel):
    schema_version: Literal["audit-action/v1"] = "audit-action/v1"
    action: Literal["answer", "skip", "pause", "resume", "review-entry", "review-conclusion"]
    answer: str | None = None
    question_id: str | None = None
    entry_id: str | None = None
    decision: Literal["confirm", "edit", "reject"] | None = None
    correction: str | None = None
    reason: str | None = None
    reviewer_id: str | None = None

    @model_validator(mode="after")
    def valid_payload(self) -> AuditAction:
        if self.action in {"answer", "skip"} and not self.answer:
            raise ValueError("answer/skip requires answer")
        if self.action == "review-entry" and (not self.entry_id or not self.decision):
            raise ValueError("entry review requires entry_id and decision")
        if self.action in {"review-entry", "review-conclusion"} and (
            not self.decision or not self.reason or not self.reviewer_id
        ):
            raise ValueError("review requires decision, reviewer_id, and reason")
        if self.action == "review-entry" and self.decision == "edit" and not self.correction:
            raise ValueError("entry edit requires correction")
        return self


class AuditSnapshot(StrictModel):
    schema_version: Literal["audit-snapshot/v1"] = "audit-snapshot/v1"
    audit_id: str = Field(pattern=r"^audit-[a-z0-9-]+$")
    contribution_id: str = Field(pattern=r"^contrib-stoa-[a-z0-9-]+$")
    status: AuditStatus
    questions: tuple[AuditQuestion, ...] = Field(min_length=1)
    answers: tuple[AuditAnswer, ...] = ()
    inspected_facts: tuple[ArtifactFact, ...] = ()
    limitations: tuple[str, ...] = ()
    contradictions: tuple[str, ...] = ()
    attribution: AuditAttribution | None = None
    conclusion: AuditConclusion | None = None
    coverage: tuple[AuditCoverage, ...] = ()
    responsibility_round: ResponsibilityRound | None = None
    assistance_round: AssistanceRound | None = None
    attribution_conflicts: tuple[AttributionConflict, ...] = ()
    conclusion_reviews: tuple[ConclusionReview, ...] = ()


class AuditCoverage(StrictModel):
    schema_version: Literal["audit-coverage/v1"] = "audit-coverage/v1"
    area_id: str = Field(min_length=1)
    status: CoverageStatus = "pending"
    difficulty_reached: Difficulty | None = None
    self_rating: str | None = None


class ResponsibilityRound(StrictModel):
    schema_version: Literal["responsibility-round/v1"] = "responsibility-round/v1"
    answer: str = Field(min_length=1)
    ownership: Literal["user-owned", "team-owned", "other-person-owned", "unresolved"]


class AssistanceRound(StrictModel):
    schema_version: Literal["assistance-round/v1"] = "assistance-round/v1"
    answer: str = Field(min_length=1)
    assistance: Literal["none", "coding-agent-assisted", "third-party-assisted", "unresolved"]
    tool: str | None = None
    model: str | None = None


class AttributionConflict(StrictModel):
    schema_version: Literal["attribution-conflict/v1"] = "attribution-conflict/v1"
    artifact_claim: str = Field(min_length=1)
    user_claim: str = Field(min_length=1)
    resolution: Literal["unresolved"] = "unresolved"
