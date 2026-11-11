# ruff: noqa: E501

from __future__ import annotations

from copy import deepcopy
from typing import Literal

from pydantic import Field, field_validator, model_serializer, model_validator

from ..validation.hashing import canonical_json_bytes, sha256_digest
from ..validation.models import StrictModel

AuditStatus = Literal["active", "paused", "reviewing", "completed", "rejected"]
AuditArea = Literal[
    "project-overview",
    "technical-design",
    "implementation",
    "research-development",
    "debugging",
    "operation",
    "organization",
    "collaboration",
    "responsibility",
    "assistance",
]
Difficulty = Literal["hard", "intermediate", "simple"]
QuestionLayer = Literal["project-overview", "project-depth", "transfer"]
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


class CandidateSkillLink(StrictModel):
    """A source-bound Skill suggestion for one Experience Candidate, never an assessment."""

    schema_version: Literal["candidate-skill-link/v1"] = "candidate-skill-link/v1"
    id: str = Field(pattern=r"^candidate-skill-[a-z0-9-]+$")
    experience_candidate_id: str = Field(pattern=r"^experience-candidate-[a-z0-9-]+$")
    source_id: str = Field(pattern=r"^[a-z][a-z0-9._-]+$")
    capture_hash: str = Field(pattern=r"^sha256:[a-f0-9]{64}$")
    source_locator: str = Field(min_length=1)
    candidate_text: str = Field(min_length=1)
    extraction_version: str = Field(min_length=1)


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
    turn: Literal["capability", "ownership", "assistance"] = "capability"
    capability_area_id: CapabilityArea | None = None
    candidate_skill_link_ids: tuple[str, ...] = ()
    recall_reminder: str | None = None
    evaluation_criteria: tuple[str, ...] = ()
    question_layer: QuestionLayer | None = None
    changed_condition: str | None = Field(default=None, min_length=1)

    @model_serializer(mode="wrap")
    def serialize_without_empty_candidate_context(self, handler):
        data = handler(self)
        if not self.candidate_skill_link_ids:
            data.pop("candidate_skill_link_ids", None)
        if self.recall_reminder is None:
            data.pop("recall_reminder", None)
        if not self.evaluation_criteria:
            data.pop("evaluation_criteria", None)
        if self.question_layer is None:
            data.pop("question_layer", None)
        if self.changed_condition is None:
            data.pop("changed_condition", None)
        return data


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
    candidate_skill_link_ids: tuple[str, ...] = ()
    evaluation_criteria: dict[Difficulty, tuple[str, ...]] = Field(default_factory=dict)
    changed_condition: str | None = Field(default=None, min_length=1)

    @model_validator(mode="after")
    def distinct_ladder_prompts(self) -> ProbeArea:
        prompts = (self.demanding_prompt, self.intermediate_prompt, self.simple_prompt)
        if len(set(prompts)) != len(prompts):
            raise ValueError("capability ladder prompts must be distinct")
        if len(self.candidate_skill_link_ids) != len(set(self.candidate_skill_link_ids)):
            raise ValueError("candidate Skill Link IDs must be unique")
        if self.evaluation_criteria:
            if set(self.evaluation_criteria) != {"hard", "intermediate", "simple"}:
                raise ValueError("evaluation criteria must cover all three difficulties")
            if any(
                not criteria or any(not criterion.strip() for criterion in criteria)
                for criteria in self.evaluation_criteria.values()
            ):
                raise ValueError("evaluation criteria must contain observable requirements")
        return self

    @model_serializer(mode="wrap")
    def serialize_without_empty_candidate_context(self, handler):
        data = handler(self)
        if not self.candidate_skill_link_ids:
            data.pop("candidate_skill_link_ids", None)
        if not self.evaluation_criteria:
            data.pop("evaluation_criteria", None)
        if self.changed_condition is None:
            data.pop("changed_condition", None)
        return data


class ProbePlan(StrictModel):
    """Validated set of only Contribution-relevant capability questions."""

    schema_version: Literal["audit-probe-plan/v1"] = "audit-probe-plan/v1"
    contribution_id: str = Field(pattern=r"^contrib-[a-z0-9-]+$")
    areas: tuple[ProbeArea, ...] = Field(min_length=1)
    question_layer: Literal["project-depth", "transfer"] | None = None

    @model_validator(mode="after")
    def unique_capability_areas(self) -> ProbePlan:
        if len({area.area_id for area in self.areas}) != len(self.areas):
            raise ValueError("capability areas must be unique")
        if self.question_layer == "transfer" and any(
            area.changed_condition is None or not area.changed_condition.strip()
            for area in self.areas
        ):
            raise ValueError("transfer questions require an explicit changed condition")
        if self.question_layer == "project-depth" and any(
            area.changed_condition is not None for area in self.areas
        ):
            raise ValueError("changed conditions belong to transfer, not project-depth")
        return self

    @model_serializer(mode="wrap")
    def serialize_without_empty_layer(self, handler):
        data = handler(self)
        if self.question_layer is None:
            data.pop("question_layer", None)
        return data


class ProjectInterviewPlan(StrictModel):
    """An overview followed by separate Contribution depth and transfer audits."""

    schema_version: Literal["project-interview-plan/v1"] = "project-interview-plan/v1"
    experience_id: str = Field(min_length=1)
    overview: AuditQuestion
    depth_plans: tuple[ProbePlan, ...] = Field(min_length=1)
    transfer_plans: tuple[ProbePlan, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def three_distinct_layers(self) -> ProjectInterviewPlan:
        if (
            self.overview.question_layer != "project-overview"
            or self.overview.area != "project-overview"
            or self.overview.status != "unanswered"
            or not self.overview.evaluation_criteria
            or any(not criterion.strip() for criterion in self.overview.evaluation_criteria)
        ):
            raise ValueError(
                "overview requires an unanswered project-overview question and criteria"
            )
        for plans, layer in (
            (self.depth_plans, "project-depth"),
            (self.transfer_plans, "transfer"),
        ):
            if len({plan.contribution_id for plan in plans}) != len(plans):
                raise ValueError("interview layer contains duplicate Contributions")
            if any(plan.question_layer != layer for plan in plans):
                raise ValueError(
                    "interview plans must preserve depth and transfer as distinct layers"
                )
            if any(not area.evaluation_criteria for plan in plans for area in plan.areas):
                raise ValueError("interview plans require predeclared criteria at every difficulty")
        if {p.contribution_id for p in self.depth_plans} != {
            p.contribution_id for p in self.transfer_plans
        }:
            raise ValueError("depth and transfer plans must cover the same selected Contributions")
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
    strongest_capability: str | None = Field(default=None, min_length=1)
    next_higher_not_established: str | None = Field(default=None, min_length=1)
    basis: tuple[str, ...] = Field(min_length=1)
    artifact_references: tuple[str, ...] = ()
    answer_references: tuple[str, ...] = ()
    candidate_skill_link_ids: tuple[str, ...] = ()
    source_type: Literal["artifact-and-answer", "answer-only", "documentary-context-only"] = (
        "answer-only"
    )
    responsibility_boundary: str = Field(min_length=1)
    assistance_boundary: str = Field(min_length=1)
    verification: Literal["audit-verified", "self-assessed-unverified", "unresolved"]
    conflicts: tuple[str, ...] = ()
    unresolved_gaps: tuple[str, ...] = ()
    review: Literal["pending", "edited", "confirmed", "rejected"] = "pending"
    correction: str | None = None
    self_rating: str | None = None

    @model_validator(mode="after")
    def truthful_verification_boundary(self) -> ConclusionEntry:
        boundary = (self.strongest_capability, self.next_higher_not_established)
        if self.verification == "audit-verified" and not all(boundary):
            raise ValueError("verified entries require both capability boundaries")
        if self.verification == "self-assessed-unverified":
            if not self.self_rating:
                raise ValueError("self-assessed entries require the verbatim self-rating")
            if any(boundary):
                raise ValueError("self-assessed entries cannot manufacture capability boundaries")
        return self

    @model_serializer(mode="wrap")
    def serialize_without_empty_candidate_context(self, handler):
        data = handler(self)
        if not self.candidate_skill_link_ids:
            data.pop("candidate_skill_link_ids", None)
        return data


def original_proposal_digest(original_proposal: dict[str, object]) -> str:
    """Return the content identity of the immutable review proposal."""
    return sha256_digest(canonical_json_bytes(original_proposal))


def effective_conclusion_digest(entries: tuple[ConclusionEntry, ...], whole_review: str) -> str:
    """Return the content identity of the current, reviewable conclusion."""
    return sha256_digest(
        canonical_json_bytes(
            {
                "entries": [entry.model_dump(mode="json") for entry in entries],
                "whole_review": whole_review,
            }
        )
    )


class AuditConclusion(StrictModel):
    schema_version: Literal["audit-conclusion/v1"] = "audit-conclusion/v1"
    entries: tuple[ConclusionEntry, ...] = Field(min_length=1)
    whole_review: Literal["pending", "confirmed", "rejected"] = "pending"
    original_proposal: dict[str, object]
    original_proposal_hash: str = Field(pattern=r"^sha256:[a-f0-9]{64}$")
    effective_conclusion_hash: str = Field(pattern=r"^sha256:[a-f0-9]{64}$")

    @field_validator("original_proposal", mode="before")
    @classmethod
    def copy_original_proposal(cls, value: object) -> object:
        """Avoid retaining a mutable proposal owned by the caller."""
        return deepcopy(value)

    @model_validator(mode="after")
    def hashes_match_conclusion_content(self) -> AuditConclusion:
        if self.original_proposal_hash != original_proposal_digest(self.original_proposal):
            raise ValueError("original proposal hash does not match its content")
        if self.effective_conclusion_hash != effective_conclusion_digest(
            self.entries, self.whole_review
        ):
            raise ValueError("effective conclusion hash does not match its content")
        return self


class ConclusionReview(StrictModel):
    schema_version: Literal["audit-conclusion-review/v1"] = "audit-conclusion-review/v1"
    review_id: str = Field(pattern=r"^review-[a-z0-9-]+$")
    target: Literal["entry", "whole-conclusion"]
    outcome: Literal["confirm", "edit", "reject"]
    reviewer_id: str = Field(min_length=1)
    reason: str = Field(min_length=1)
    entry_id: str | None = None
    correction: str | None = None
    sequence: int = Field(ge=1)
    before_effective_hash: str = Field(pattern=r"^sha256:[a-f0-9]{64}$")
    after_effective_hash: str = Field(pattern=r"^sha256:[a-f0-9]{64}$")


def conclusion_lineage_digest(
    conclusion: AuditConclusion, reviews: tuple[ConclusionReview, ...]
) -> str:
    """Return the canonical identity of an immutable conclusion review trail."""
    return sha256_digest(
        canonical_json_bytes(
            {
                "original_proposal_hash": conclusion.original_proposal_hash,
                "effective_conclusion_hash": conclusion.effective_conclusion_hash,
                "reviews": [review.model_dump(mode="json") for review in reviews],
            }
        )
    )


class AuditAction(StrictModel):
    schema_version: Literal["audit-action/v1"] = "audit-action/v1"
    action: Literal[
        "answer",
        "request-context",
        "skip",
        "skip-contribution",
        "pause",
        "resume",
        "review-entry",
        "review-conclusion",
    ]
    answer: str | None = None
    question_id: str | None = None
    entry_id: str | None = None
    decision: Literal["confirm", "edit", "reject"] | None = None
    correction: str | None = None
    reason: str | None = None
    reviewer_id: str | None = None

    @model_validator(mode="after")
    def valid_payload(self) -> AuditAction:
        if (
            self.action in {"answer", "request-context", "skip", "skip-contribution"}
            and not self.answer
        ):
            raise ValueError("answer/skip requires answer")
        if self.action == "review-entry" and (not self.entry_id or not self.decision):
            raise ValueError("entry review requires entry_id and decision")
        if self.action in {"review-entry", "review-conclusion"} and (
            not self.decision or not self.reason or not self.reviewer_id
        ):
            raise ValueError("review requires decision, reviewer_id, and reason")
        if self.action == "review-entry" and self.decision == "edit" and not self.correction:
            raise ValueError("entry edit requires correction")
        if self.action == "review-conclusion" and self.decision == "edit":
            raise ValueError("whole-conclusion review may only confirm or reject")
        return self


class AuditSnapshot(StrictModel):
    schema_version: Literal["audit-snapshot/v1", "audit-snapshot/v2", "audit-snapshot/v3"] = (
        "audit-snapshot/v1"
    )
    audit_id: str = Field(pattern=r"^audit-[a-z0-9-]+$")
    contribution_id: str = Field(pattern=r"^contrib-[a-z0-9-]+$")
    experience_candidate_id: str | None = Field(
        default=None, pattern=r"^experience-candidate-[a-z0-9-]+$"
    )
    candidate_skill_links: tuple[CandidateSkillLink, ...] = ()
    status: AuditStatus
    questions: tuple[AuditQuestion, ...] = ()
    answers: tuple[AuditAnswer, ...] = ()
    context_requests: tuple[AuditAnswer, ...] = ()
    inspected_facts: tuple[ArtifactFact, ...] = ()
    limitations: tuple[str, ...] = ()
    contradictions: tuple[str, ...] = ()
    attribution: AuditAttribution | None = None
    conclusion: AuditConclusion | None = None
    coverage: tuple[AuditCoverage, ...] = ()
    probe_plan: ProbePlan | None = None
    decisions: tuple[BoundaryDecision, ...] = ()
    attribution_records: tuple[AttributionRecord, ...] = ()
    responsibility_round: ResponsibilityRound | None = None
    assistance_round: AssistanceRound | None = None
    attribution_conflicts: tuple[AttributionConflict, ...] = ()
    conclusion_reviews: tuple[ConclusionReview, ...] = ()
    conclusion_lineage_hash: str | None = Field(default=None, pattern=r"^sha256:[a-f0-9]{64}$")

    @model_validator(mode="after")
    def conclusion_lineage_matches_content(self) -> AuditSnapshot:
        if self.context_requests:
            if self.schema_version != "audit-snapshot/v3":
                raise ValueError("context requests require audit snapshot v3")
            if any(
                request.question_id not in {q.id for q in self.questions} or request.skipped
                for request in self.context_requests
            ):
                raise ValueError(
                    "context requests must reference retained questions and cannot be skips"
                )
        referenced_candidate_link_ids = {
            link_id
            for area in (self.probe_plan.areas if self.probe_plan else ())
            for link_id in area.candidate_skill_link_ids
        }
        referenced_candidate_link_ids.update(
            link_id for question in self.questions for link_id in question.candidate_skill_link_ids
        )
        if self.conclusion:
            referenced_candidate_link_ids.update(
                link_id
                for entry in self.conclusion.entries
                for link_id in entry.candidate_skill_link_ids
            )
        if self.schema_version == "audit-snapshot/v1" and (
            self.experience_candidate_id is not None
            or self.candidate_skill_links
            or referenced_candidate_link_ids
        ):
            raise ValueError("candidate Skill context requires audit snapshot v2")
        if self.candidate_skill_links:
            if self.experience_candidate_id is None:
                raise ValueError("candidate Skill Links require an Experience Candidate")
            if len({link.id for link in self.candidate_skill_links}) != len(
                self.candidate_skill_links
            ):
                raise ValueError("candidate Skill Link IDs must be unique")
            if any(
                link.experience_candidate_id != self.experience_candidate_id
                for link in self.candidate_skill_links
            ):
                raise ValueError(
                    "candidate Skill Links must match the selected Experience Candidate"
                )
        if referenced_candidate_link_ids - {link.id for link in self.candidate_skill_links}:
            raise ValueError("audit snapshot references a missing Candidate Skill Link")
        if self.conclusion is None:
            if self.conclusion_reviews or self.conclusion_lineage_hash is not None:
                raise ValueError("conclusion lineage requires a conclusion")
            return self

        expected_sequence = list(range(1, len(self.conclusion_reviews) + 1))
        if [review.sequence for review in self.conclusion_reviews] != expected_sequence:
            raise ValueError("conclusion reviews must have contiguous ordered sequences")
        for previous, current in zip(
            self.conclusion_reviews, self.conclusion_reviews[1:], strict=False
        ):
            if previous.after_effective_hash != current.before_effective_hash:
                raise ValueError("conclusion reviews must form a contiguous effective-hash lineage")
        if self.conclusion_reviews and (
            self.conclusion_reviews[-1].after_effective_hash
            != self.conclusion.effective_conclusion_hash
        ):
            raise ValueError("conclusion review lineage does not reach the effective conclusion")

        if self.conclusion_lineage_hash != conclusion_lineage_digest(
            self.conclusion, self.conclusion_reviews
        ):
            raise ValueError("conclusion lineage hash does not match its content")
        return self

    @model_serializer(mode="wrap")
    def serialize_candidate_context_only_in_v2(self, handler):
        data = handler(self)
        if self.schema_version == "audit-snapshot/v1":
            data.pop("experience_candidate_id", None)
            data.pop("candidate_skill_links", None)
        if not self.context_requests:
            data.pop("context_requests", None)
        return data


class AuditCoverage(StrictModel):
    schema_version: Literal["audit-coverage/v1"] = "audit-coverage/v1"
    area_id: str = Field(min_length=1)
    status: CoverageStatus = "pending"
    difficulty_reached: Difficulty | None = None
    self_rating: str | None = None
    strongest_capability: str | None = None
    next_higher_not_established: str | None = None
    attribution_stage: Literal["none", "ownership", "assistance", "complete"] = "none"
    resume_difficulty: Difficulty | None = None
    resume_follow_up_count: int | None = Field(default=None, ge=0, le=1)


class AttributionRecord(StrictModel):
    """Separate per-capability ownership then assistance evidence."""

    schema_version: Literal["audit-attribution-record/v1"] = "audit-attribution-record/v1"
    area_id: CapabilityArea
    ownership_answer: str | None = None
    ownership: Literal["user-owned", "team-owned", "other-person-owned", "unresolved"] = (
        "unresolved"
    )
    assistance_answer: str | None = None
    assistance: Literal["none", "coding-agent-assisted", "third-party-assisted", "unresolved"] = (
        "unresolved"
    )
    assistance_scope: tuple[str, ...] = ()
    tool: str | None = None
    model: str | None = None


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
