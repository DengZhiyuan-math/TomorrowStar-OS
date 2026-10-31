"""Pure JSON contracts for resume facts, scoped writing and content revisions.

Contract versions are v1; validation uses the installed Pydantic v2. These
contracts prove structure and reference scope, never the truth of model wording.
No function reads libraries, invokes a writer, renders TeX or persists revisions.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, TypeAdapter, model_validator

Text = Annotated[str, StringConstraints(min_length=1, pattern=r"\S")]


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, revalidate_instances="always")


class Source(Contract):
    id: Text
    locator: Text


class ExperienceFact(Contract):
    id: Text
    text: Text
    source_refs: list[Text] = Field(min_length=1)
    responsibility: Literal["user", "team", "other_person", "agent_assisted", "third_party"]
    status: Literal["planned", "in_progress", "completed", "unknown"]
    scope: Text


class ExperienceFacts(Contract):
    schema_version: Literal["experience-facts/v1"]
    revision: Text
    experience_id: Text
    candidate_id: Text
    title: Text
    role: Text | None = None
    organization: Text | None = None
    start: Text | None = None
    end: Text | None = None
    location: Text | None = None
    sources: list[Source]
    facts: list[ExperienceFact]

    @model_validator(mode="after")
    def validate_fact_sources(self):
        source_ids = [source.id for source in self.sources]
        _unique(source_ids, "source ID")
        _unique([fact.id for fact in self.facts], "fact ID")
        for fact in self.facts:
            _references(fact.source_refs, source_ids)
        return self


class ExperienceFactV2(Contract):
    id: Text
    text: Text
    # agent_assisted remains only until the per-experience review separates agent
    # work (agent) from assisted user or team work.
    responsibility: Literal["user", "team", "other_person", "agent", "agent_assisted"]
    status: Literal["planned", "in_progress", "completed", "unknown"]
    source_refs: list[Text] = Field(min_length=1)


class ContextItem(Contract):
    """Sourced background for an Experience; never the user's own activity."""

    id: Text
    text: Text
    source_refs: list[Text] = Field(min_length=1)


class ExperienceFactsV2(Contract):
    """Only attributes every Experience shares; anything particular is a fact."""

    schema_version: Literal["experience-facts/v2"]
    revision: Text
    experience_id: Text
    title: Text
    role: Text | None = None
    organization: Text | None = None
    location: Text | None = None
    start: Text | None = None
    end: Text | None = None
    sources: list[Source]
    facts: list[ExperienceFactV2]
    context: list[ContextItem]

    @model_validator(mode="after")
    def validate_fact_sources(self):
        source_ids = [source.id for source in self.sources]
        _unique(source_ids, "source ID")
        _unique([item.id for item in (*self.facts, *self.context)], "fact ID")
        for item in (*self.facts, *self.context):
            _references(item.source_refs, source_ids)
        return self


StoredExperienceFacts = TypeAdapter(
    Annotated[ExperienceFacts | ExperienceFactsV2, Field(discriminator="schema_version")]
)


def upgrade_experience_facts(content):
    """Move v1 content to v2 without losing text: returns content and its scope notes.

    Third-party facts become context; each fact's free-text scope becomes a pending
    archive note until the per-experience review rewrites real boundaries as facts.
    """
    content = ExperienceFacts.model_validate(content).model_dump(mode="json")
    facts, context, notes = [], [], []
    for fact in content.pop("facts"):
        note = {"fact_id": fact["id"], "text": fact.pop("scope"), "status": "pending"}
        if fact["responsibility"] == "third_party":
            # Context carries no status field; the archive note keeps the old value.
            note["context_status"] = fact["status"]
            context.append({key: fact[key] for key in ("id", "text", "source_refs")})
        else:
            facts.append(fact)
        notes.append(note)
    upgraded = ExperienceFactsV2.model_validate(
        {key: value for key, value in content.items() if key != "candidate_id"}
        | {"schema_version": "experience-facts/v2", "facts": facts, "context": context}
    ).model_dump(mode="json")
    return upgraded, notes


def experience_facts_v1(content, notes=()):
    """Read either version as v1 facts until the Matching View replaces this shape.

    Pending notes keep the old scope text visible to matching until reviewed.
    """
    content = StoredExperienceFacts.validate_python(content).model_dump(mode="json")
    if content["schema_version"] == "experience-facts/v1":
        return content
    scope = {note["fact_id"]: note["text"] for note in notes if note["status"] == "pending"}
    statuses = {note["fact_id"]: note.get("context_status", "unknown") for note in notes}
    rows = [
        fact | {"scope": scope.get(fact["id"], "Recorded experience fact.")}
        for fact in content["facts"]
    ] + [
        item
        | {
            "responsibility": "third_party",
            "status": statuses.get(item["id"], "unknown"),
            "scope": scope.get(item["id"], "Experience background; not the user's activity."),
        }
        for item in content["context"]
    ]
    return {
        key: value
        for key, value in content.items()
        if key not in {"schema_version", "facts", "context"}
    } | {
        "schema_version": "experience-facts/v1",
        "candidate_id": content["experience_id"],
        "facts": rows,
    }


class Inference(Contract):
    id: Text
    candidate_id: Text
    text: Text
    fact_refs: list[Text] = Field(min_length=1)


def _unique(values, label):
    if len(values) != len(set(values)):
        raise ValueError(f"duplicate {label}")


def _references(values, allowed):
    _unique(values, "reference")
    if not set(values) <= set(allowed):
        raise ValueError("reference does not belong to the delivered snapshot")


class WritingAssignment(Contract):
    schema_version: Literal["experience-assignment/v1"]
    assignment_revision: Text
    experience_id: Text
    candidate_id: Text
    experience: ExperienceFacts
    inferences: list[Inference]
    allowed_fact_refs: list[Text]
    allowed_inference_refs: list[Text]
    writing_requirements: list[Text]

    @model_validator(mode="after")
    def validate_scope(self):
        experience = self.experience
        if (self.experience_id, self.candidate_id) != (
            experience.experience_id,
            experience.candidate_id,
        ):
            raise ValueError("assignment canonical candidate identity does not match")
        fact_ids = [fact.id for fact in experience.facts]
        inference_ids = [inference.id for inference in self.inferences]
        _unique(inference_ids, "inference ID")
        _references(self.allowed_fact_refs, fact_ids)
        _references(self.allowed_inference_refs, inference_ids)
        for inference in self.inferences:
            if inference.candidate_id != self.candidate_id:
                raise ValueError("inference reference belongs to another candidate")
            _references(inference.fact_refs, self.allowed_fact_refs)
        return self


class Link(Contract):
    label: Text
    url: Text


class ContentItem(Contract):
    id: Text
    text: Text
    fact_refs: list[Text] = Field(default_factory=list)
    inference_refs: list[Text] = Field(default_factory=list)
    origin: Literal["ai", "human"] = "ai"
    edit_source: Text | None = None
    protected: bool = False
    links: list[Link] = Field(default_factory=list)


# Provenance belongs to the program; a writer's schema never offers these fields.
PROGRAM_OWNED_ITEM_FIELDS = ("origin", "edit_source", "protected")


def writer_schema(schema):
    """Remove program-owned item provenance from a writer's output schema."""
    schema = deepcopy(schema)
    item = schema.get("$defs", {}).get("ContentItem", {})
    for key in PROGRAM_OWNED_ITEM_FIELDS:
        item.get("properties", {}).pop(key, None)
        if key in item.get("required", []):
            item["required"].remove(key)
    return schema


class ExperienceFragment(Contract):
    schema_version: Literal["experience-writing/v1"]
    assignment_revision: Text
    experience_id: Text
    candidate_id: Text
    status: Literal["complete"]
    items: list[ContentItem] = Field(min_length=1)


class MaterialRequest(Contract):
    id: Text
    field: Literal["facts", "title", "role", "organization", "start", "end", "location"]
    detail: Text
    fact_refs: list[Text] = Field(default_factory=list)


class NeedsMaterialFragment(Contract):
    schema_version: Literal["experience-writing/v1"]
    assignment_revision: Text
    experience_id: Text
    candidate_id: Text
    status: Literal["needs_material"]
    requests: list[MaterialRequest] = Field(min_length=1)


WritingResult = Annotated[ExperienceFragment | NeedsMaterialFragment, Field(discriminator="status")]


def validate_fragment(payload, assignment) -> dict:
    """Validate a writer response against its fixed delivered assignment."""
    assigned = WritingAssignment.model_validate(assignment)
    result = TypeAdapter(WritingResult).validate_python(payload)
    if (result.experience_id, result.candidate_id, result.assignment_revision) != (
        assigned.experience_id,
        assigned.candidate_id,
        assigned.assignment_revision,
    ):
        raise ValueError("fragment identity or assignment revision does not match")
    if isinstance(result, NeedsMaterialFragment):
        _unique([request.id for request in result.requests], "request ID")
        for request in result.requests:
            _references(request.fact_refs, [fact.id for fact in assigned.experience.facts])
        return result.model_dump(mode="json")
    _unique([item.id for item in result.items], "item ID")
    for item in result.items:
        if item.origin != "ai" or item.protected or item.edit_source is not None:
            raise ValueError("writer cannot set human provenance or protection")
        if not item.fact_refs and not item.inference_refs:
            raise ValueError("AI item requires a per-item reference")
        _unique(item.fact_refs, "reference")
        _unique(item.inference_refs, "reference")
        if not set(item.fact_refs) <= set(assigned.allowed_fact_refs) or not set(
            item.inference_refs
        ) <= set(assigned.allowed_inference_refs):
            raise ValueError("item reference is outside the delivered assignment")
    return result.model_dump(mode="json")


class Contact(Contract):
    label: Text
    url: Text | None = None


class Profile(Contract):
    name: Text
    contacts: list[Contact] = Field(default_factory=list)


class Education(Contract):
    id: Text
    institution: Text
    qualification: Text
    start: Text | None = None
    end: Text | None = None
    status: Literal["in_progress", "completed", "incomplete", "unknown"] | None = None
    details: list[Text] = Field(default_factory=list)


class ResumeExperience(Contract):
    id: Text
    candidate_id: Text
    title: Text
    role: Text | None = None
    organization: Text | None = None
    start: Text | None = None
    end: Text | None = None
    location: Text | None = None
    items: list[ContentItem] = Field(min_length=1)


def _validate_content_items(content, fixed_ids=()):
    ids = list(fixed_ids)
    ids.extend(experience.id for experience in content.experiences)
    items = content.summary + content.skills
    if getattr(content, "headline", None) is not None:
        items = [content.headline, *items]
    for experience in content.experiences:
        items += experience.items
    ids.extend(item.id for item in items)
    _unique(ids, "content ID")
    _unique([experience.candidate_id for experience in content.experiences], "candidate ID")
    for item in items:
        if item.origin == "human":
            if not item.protected or not item.edit_source:
                raise ValueError("human content needs protected edit provenance")
        elif not item.fact_refs and not item.inference_refs:
            raise ValueError("AI item needs a per-item reference")
        _unique(item.fact_refs, "reference")
        _unique(item.inference_refs, "reference")
    return content


class ResumeContent(Contract):
    schema_version: Literal["resume-content/v1"]
    revision: Text
    application_id: Text
    profile: Profile
    education: list[Education]
    summary: list[ContentItem] = Field(default_factory=list)
    skills: list[ContentItem] = Field(default_factory=list)
    experiences: list[ResumeExperience]

    @model_validator(mode="after")
    def validate_items(self):
        return _validate_content_items(self, [education.id for education in self.education])


class TemplateResumeContent(Contract):
    """Variable wording only; fixed identity and education remain in the TeX template."""

    schema_version: Literal["resume-template-content/v1"]
    revision: Text
    application_id: Text
    template_revision: Text
    headline: ContentItem | None = Field(default=None, exclude_if=lambda value: value is None)
    summary: list[ContentItem] = Field(default_factory=list)
    skills: list[ContentItem] = Field(default_factory=list)
    experiences: list[ResumeExperience]

    @model_validator(mode="after")
    def validate_items(self):
        return _validate_content_items(self)


class ResumePlan(Contract):
    schema_version: Literal["resume-plan/v1"]
    application_id: Text
    profile: Profile
    education: list[Education]
    summary: list[ContentItem] = Field(default_factory=list)
    skills: list[ContentItem] = Field(default_factory=list)
    assignments: list[WritingAssignment] = Field(min_length=1)


class TemplateResumePlan(Contract):
    schema_version: Literal["resume-template-plan/v1"]
    application_id: Text
    template_revision: Text
    headline: ContentItem | None = Field(default=None, exclude_if=lambda value: value is None)
    summary: list[ContentItem] = Field(default_factory=list)
    skills: list[ContentItem] = Field(default_factory=list)
    assignments: list[WritingAssignment] = Field(min_length=1)


ResumePlanContract = Annotated[
    ResumePlan | TemplateResumePlan, Field(discriminator="schema_version")
]
ResumeContentContract = Annotated[
    ResumeContent | TemplateResumeContent, Field(discriminator="schema_version")
]


def validate_plan(payload) -> ResumePlan | TemplateResumePlan:
    """Validate variable template plans and preserved historical complete plans."""
    return TypeAdapter(ResumePlanContract).validate_python(payload)


class RetainedItem(Contract):
    experience_id: Text
    item: ContentItem


class RetainedContent(Contract):
    schema_version: Literal["resume-retained/v1"]
    application_id: Text
    items: list[RetainedItem]


def content_revision(payload) -> str:
    # Share the existing deterministic JSON identity instead of a second hash policy.
    from .validation.hashing import record_digest as digest

    if isinstance(payload, BaseModel):
        payload = payload.model_dump(mode="json")
    return digest({key: value for key, value in payload.items() if key != "revision"})


def validate_content(payload) -> ResumeContent | TemplateResumeContent:
    """Validate shape and exact normalized content identity before rendering."""
    content = TypeAdapter(ResumeContentContract).validate_python(payload)
    if content.revision != content_revision(content):
        raise ValueError("content revision does not match its fields")
    return content


def assemble_content(plan, fragments, retained=None) -> dict:
    """Assemble in program-owned plan order, without changing input objects."""
    planned = validate_plan(plan)
    parsed = [TypeAdapter(WritingResult).validate_python(fragment) for fragment in fragments]
    ids = [fragment.experience_id for fragment in parsed]
    _unique(ids, "fragment experience ID")
    assignment_ids = [assignment.experience_id for assignment in planned.assignments]
    _unique(assignment_ids, "assignment experience ID")
    _unique([assignment.candidate_id for assignment in planned.assignments], "candidate ID")
    if set(ids) != set(assignment_ids):
        raise ValueError("fragment set must exactly match assigned experiences")
    results = {fragment.experience_id: fragment.model_dump(mode="json") for fragment in parsed}
    all_fact_refs = [ref for assigned in planned.assignments for ref in assigned.allowed_fact_refs]
    all_inference_refs = [
        ref for assigned in planned.assignments for ref in assigned.allowed_inference_refs
    ]
    _unique(all_fact_refs, "fact ID across assignments")
    _unique(all_inference_refs, "inference ID across assignments")
    global_items = planned.summary + planned.skills
    if getattr(planned, "headline", None) is not None:
        global_items = [planned.headline, *global_items]
    for item in global_items:
        if item.origin != "ai" or item.protected or item.edit_source is not None:
            raise ValueError("global writer cannot set human provenance or protection")
        _references(item.fact_refs, all_fact_refs)
        _references(item.inference_refs, all_inference_refs)
    experiences = []
    for assigned in planned.assignments:
        result = validate_fragment(results[assigned.experience_id], assigned)
        if result["status"] != "complete":
            raise ValueError("experience still needs material")
        facts = assigned.experience
        experiences.append(
            ResumeExperience(
                id=facts.experience_id,
                candidate_id=facts.candidate_id,
                title=facts.title,
                role=facts.role,
                organization=facts.organization,
                start=facts.start,
                end=facts.end,
                location=facts.location,
                items=result["items"],
            )
        )
    if retained is not None:
        saved = RetainedContent.model_validate(retained)
        if saved.application_id != planned.application_id:
            raise ValueError("retained content belongs to another application")
        _unique([entry.item.id for entry in saved.items], "retained item ID")
        by_id = {experience.id: experience for experience in experiences}
        assigned_by_id = {
            assignment.experience_id: assignment for assignment in planned.assignments
        }
        for entry in saved.items:
            if entry.experience_id not in by_id:
                raise ValueError("retained content targets an unassigned experience")
            item = entry.item
            if item.origin != "human" or not item.protected or not item.edit_source:
                raise ValueError("retained content requires protected human provenance")
            scope = assigned_by_id[entry.experience_id]
            _references(item.fact_refs, [fact.id for fact in scope.experience.facts])
            _references(item.inference_refs, [inference.id for inference in scope.inferences])
            target = by_id[entry.experience_id]
            for index, existing in enumerate(target.items):
                if existing.id == item.id:
                    target.items[index] = item
                    break
            else:
                target.items.append(item)
    content_model = (
        TemplateResumeContent if isinstance(planned, TemplateResumePlan) else ResumeContent
    )
    fixed = (
        {
            "schema_version": "resume-template-content/v1",
            "template_revision": planned.template_revision,
            "headline": planned.headline,
        }
        if isinstance(planned, TemplateResumePlan)
        else {
            "schema_version": "resume-content/v1",
            "profile": planned.profile,
            "education": planned.education,
        }
    )
    content = content_model(
        **fixed,
        revision="pending",
        application_id=planned.application_id,
        summary=planned.summary,
        skills=planned.skills,
        experiences=experiences,
    ).model_dump(mode="json")
    content["revision"] = content_revision(content)
    return content


class PatchTarget(Contract):
    item_id: Text
    fields: list[Literal["text", "links"]] = Field(min_length=1)


class ItemChange(Contract):
    item_id: Text
    field: Literal["text", "links"]
    expected: Text | list[Link]
    value: Text | list[Link]

    @model_validator(mode="after")
    def validate_field_type(self):
        for value in (self.expected, self.value):
            if (self.field == "text") != isinstance(value, str):
                raise ValueError("patch value type does not match field")
        return self


class ContentPatch(Contract):
    schema_version: Literal["resume-content-patch/v1"]
    base_revision: Text
    changes: list[ItemChange] = Field(min_length=1)


def apply_content_patch(base, patch, *, allowed_targets) -> dict:
    """Apply local text/link changes with revision and old-value preconditions.

    Semantic review cannot change identity, education, provenance, references or
    protected human wording. Human corrections use their own later edit workflow.
    """
    content = validate_content(base).model_dump(mode="json")
    edits = ContentPatch.model_validate(patch)
    if edits.base_revision != content["revision"]:
        raise ValueError("patch base content revision does not match")
    trusted = TypeAdapter(list[PatchTarget]).validate_python(allowed_targets)
    _unique([target.item_id for target in trusted], "patch target")
    _unique([(change.item_id, change.field) for change in edits.changes], "patch field")
    allowed = {target.item_id: target.fields for target in trusted}
    items = content["summary"] + content["skills"]
    if content.get("headline") is not None:
        items = [content["headline"], *items]
    for experience in content["experiences"]:
        items += experience["items"]
    by_id = {item["id"]: item for item in items}
    for change in edits.changes:
        if change.item_id not in by_id or change.field not in allowed.get(change.item_id, []):
            raise ValueError("patch target or field is outside allowed content")
        item = by_id[change.item_id]
        if item["origin"] == "human" or item["protected"]:
            raise ValueError("patch cannot change protected human content")
        values = change.model_dump(mode="json")
        if item[change.field] != values["expected"]:
            raise ValueError("patch expected old value does not match")
        item[change.field] = values["value"]
    result = TypeAdapter(ResumeContentContract).validate_python(content).model_dump(mode="json")
    result["revision"] = content_revision(result)
    return result
