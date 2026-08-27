"""Artifact-aware, single-Contribution capability interview transitions."""

from __future__ import annotations

import re
from pathlib import Path
from uuid import uuid4

from ..domain.fixtures import SealedFixtureRecord, load_sealed_fixture, verify_source_manifest
from .decision import (
    AuditDecisionPort,
    FakeDecisionPort,
    validate_boundary_decision,
    validate_probe_plan,
)
from .models import (
    ArtifactFact,
    AttributionConflict,
    AttributionRecord,
    AuditAction,
    AuditAnswer,
    AuditAttribution,
    AuditConclusion,
    AuditCoverage,
    AuditQuestion,
    AuditSnapshot,
    ConclusionEntry,
    ConclusionReview,
    ProbeArea,
    conclusion_lineage_digest,
    effective_conclusion_digest,
    original_proposal_digest,
)
from .store import AuditStore


class AuditWorkflowError(ValueError):
    """A rejected audit action or selected-fixture reference."""


_PROMPT_NORMALIZATION = re.compile(r"\W+", flags=re.UNICODE)
_UNSAFE_PROMPT = re.compile(
    r"\b(isn't it|is it true|clearly|obviously|according to (?:the )?(?:record|artifact)|"
    r"what does (?:the )?(?:record|artifact|document) (?:say|show))\b",
    flags=re.IGNORECASE,
)
_DIFFICULTY_ORDER = {"hard": "intermediate", "intermediate": "simple", "simple": None}


def canonical_assistance(value: str) -> str:
    """Map vendor-era labels to the stable provider-neutral audit vocabulary."""
    return {
        "none": "none",
        "codex_assisted": "coding-agent-assisted",
        "coding-agent-assisted": "coding-agent-assisted",
        "third_party": "third-party-assisted",
        "third-party-assisted": "third-party-assisted",
    }.get(value, "unresolved")


def parse_assistance(value: str) -> str:
    """Read legacy bytes without rewriting them; callers choose canonical writes."""
    return canonical_assistance(value)


def _fixture(path: Path):
    load_sealed_fixture(path, path.parent)
    return SealedFixtureRecord.model_validate_json(path.read_bytes()).fixture


def inspect_contribution(
    fixture_path: Path, manifest_path: Path, contribution_id: str
) -> tuple[tuple[ArtifactFact, ...], tuple[str, ...]]:
    verify_source_manifest(manifest_path)
    fixture = _fixture(fixture_path)
    contribution = next(
        (item for item in fixture.contributions if item.id == contribution_id), None
    )
    if contribution is None:
        raise AuditWorkflowError("selected Contribution is missing")
    claims = {claim.id: claim for claim in fixture.claims}
    evidence = {item.id: item for item in fixture.evidence}
    missing_claims = [claim_id for claim_id in contribution.claim_ids if claim_id not in claims]
    if missing_claims:
        raise AuditWorkflowError(
            f"selected Contribution references missing claim: {missing_claims[0]}"
        )
    links = [
        item for item in fixture.claim_evidence_links if item.claim_id in contribution.claim_ids
    ]
    if not links:
        raise AuditWorkflowError("Contribution has no linked evidence")
    for link in links:
        if link.evidence_id not in evidence:
            raise AuditWorkflowError("selected link references missing evidence")
    facts = tuple(
        sorted(
            (
                ArtifactFact(
                    evidence_id=evidence[link.evidence_id].id,
                    source_locator=link.section_locator,
                    statement=claims[link.claim_id].statement,
                )
                for link in links
            ),
            key=lambda item: (item.evidence_id, item.source_locator),
        )
    )
    limitations = tuple(
        sorted(
            {
                limitation
                for claim_id in contribution.claim_ids
                for limitation in claims[claim_id].limitations
            }
        )
    )
    return facts, limitations


def _prompt_key(prompt: str) -> str:
    return _PROMPT_NORMALIZATION.sub("", prompt).casefold()


def _validate_new_question(question: AuditQuestion, previous: tuple[AuditQuestion, ...]) -> None:
    if question.prompt.count("?") + question.prompt.count("？") != 1:
        raise AuditWorkflowError("audit question must contain one focused question")
    if _UNSAFE_PROMPT.search(question.prompt):
        raise AuditWorkflowError("audit question is leading or artifact-answerable")
    if not question.inspection_reference or not question.reason.strip():
        raise AuditWorkflowError("audit question needs an inspected fact and reason")
    if _prompt_key(question.prompt) in {_prompt_key(item.prompt) for item in previous}:
        raise AuditWorkflowError("audit question repeats an earlier prompt")


def _area_for(snapshot: AuditSnapshot, area_id: str) -> ProbeArea:
    if snapshot.probe_plan is None:
        raise AuditWorkflowError("audit snapshot has no validated probe plan")
    area = next((item for item in snapshot.probe_plan.areas if item.area_id == area_id), None)
    if area is None:
        raise AuditWorkflowError("active capability area is not in the probe plan")
    return area


def _fact_for(snapshot: AuditSnapshot, area: ProbeArea) -> ArtifactFact:
    facts = {fact.evidence_id: fact for fact in snapshot.inspected_facts}
    try:
        return facts[area.inspected_fact_ids[0]]
    except KeyError as exc:
        raise AuditWorkflowError("probe plan fact is absent from the audit snapshot") from exc


def _capability_prompt(area: ProbeArea, difficulty: str) -> str:
    return {
        "hard": area.demanding_prompt,
        "intermediate": area.intermediate_prompt,
        "simple": area.simple_prompt,
    }[difficulty]


def _capability_question(
    snapshot: AuditSnapshot,
    area: ProbeArea,
    difficulty: str,
    follow_up_count: int,
) -> AuditQuestion:
    fact = _fact_for(snapshot, area)
    prompt = _capability_prompt(area, difficulty)
    if follow_up_count:
        prompt = f"Can you give one concrete example that clarifies this: {prompt.rstrip('?？')}?"
    elif any(
        item.turn == "capability"
        and item.capability_area_id == area.area_id
        and item.difficulty == difficulty
        for item in snapshot.questions
    ):
        prompt = f"Now focus only on your capability boundary: {prompt}"
    if prompt.count("?") + prompt.count("？") == 0:
        prompt = f"Can you explain this capability: {prompt.rstrip('.')}?"
    question = AuditQuestion(
        id=f"question-{area.area_id}-{difficulty}-{follow_up_count}-{len(snapshot.questions)}",
        reason=(
            f"{fact.source_locator} records: {fact.statement} "
            f"The capability {area.unverified_capability} remains unverified."
        ),
        prompt=prompt,
        area=area.area_id,
        area_id=area.area_id,
        capability_area_id=area.area_id,
        difficulty=difficulty,
        inspection_reference=fact.source_locator,
        follow_up_count=follow_up_count,
    )
    _validate_new_question(question, snapshot.questions)
    return question


def _attribution_question(snapshot: AuditSnapshot, area: ProbeArea, turn: str) -> AuditQuestion:
    fact = _fact_for(snapshot, area)
    if turn == "ownership":
        prompt = (
            "Who owned the relevant work: you, the team, another person, or is that unresolved?"
        )
        reason = (
            f"{fact.source_locator} records: {fact.statement} "
            "The personal responsibility boundary remains unverified."
        )
    else:
        prompt = (
            "Was any design, code generation, modification, debugging, testing, or final "
            "acceptance assisted by a coding agent or third party; if so, which parts?"
        )
        reason = "Responsibility was asked separately; the assistance boundary remains unverified."
    question = AuditQuestion(
        id=f"question-{area.area_id}-{turn}-{len(snapshot.questions)}",
        reason=reason,
        prompt=prompt,
        area=area.area_id,
        area_id=area.area_id,
        capability_area_id=area.area_id,
        difficulty="hard",
        inspection_reference=fact.source_locator,
        turn=turn,
    )
    _validate_new_question(question, snapshot.questions)
    return question


def _replace_coverage(snapshot: AuditSnapshot, updated: AuditCoverage) -> tuple[AuditCoverage, ...]:
    coverage = list(snapshot.coverage)
    index = next((i for i, item in enumerate(coverage) if item.area_id == updated.area_id), None)
    if index is None:
        coverage.append(updated)
    else:
        coverage[index] = updated
    return tuple(coverage)


def _coverage(snapshot: AuditSnapshot, area_id: str) -> AuditCoverage:
    item = next((item for item in snapshot.coverage if item.area_id == area_id), None)
    if item is None:
        raise AuditWorkflowError("active capability coverage is missing")
    return item


def _replace_attribution(
    snapshot: AuditSnapshot, updated: AttributionRecord
) -> tuple[AttributionRecord, ...]:
    records = list(snapshot.attribution_records)
    index = next((i for i, item in enumerate(records) if item.area_id == updated.area_id), None)
    if index is None:
        records.append(updated)
    else:
        records[index] = updated
    return tuple(records)


def _attribution(snapshot: AuditSnapshot, area_id: str) -> AttributionRecord:
    return next(
        (item for item in snapshot.attribution_records if item.area_id == area_id),
        AttributionRecord(area_id=area_id),
    )


def _classify_ownership(text: str) -> str:
    value = text.casefold()
    matches = {
        "user-owned": ("i owned", "i was responsible", "我负责", "我做", "我实现"),
        "team-owned": ("team owned", "the team", "团队负责", "团队做"),
        "other-person-owned": ("not me", "不是我", "other person", "someone else", "他人负责"),
    }
    found = [kind for kind, terms in matches.items() if any(term in value for term in terms)]
    return found[0] if len(found) == 1 else "unresolved"


def _classify_assistance(text: str) -> tuple[str, tuple[str, ...], str | None, str | None]:
    value = text.casefold()
    if any(
        term in value
        for term in (
            "no assistance",
            "no outside assistance",
            "without assistance",
            "没有协助",
            "无协助",
        )
    ):
        return "none", (), None, None
    scope = tuple(
        label
        for label, terms in {
            "design": ("design", "设计"),
            "generation": ("generate", "generation", "生成"),
            "modification": ("modify", "modification", "修改"),
            "debugging": ("debug", "调试"),
            "testing": ("test", "测试"),
            "acceptance": ("acceptance", "验收"),
        }.items()
        if any(term in value for term in terms)
    )
    if any(term in value for term in ("codex", "coding agent", "chatgpt", "代码代理", "编码代理")):
        tool = "Codex" if "codex" in value else None
        return "coding-agent-assisted", scope, tool, None
    if any(term in value for term in ("consultant", "third party", "第三方", "外部协助")):
        return "third-party-assisted", scope, None, None
    return "unresolved", scope, None, None


def _active_question(snapshot: AuditSnapshot) -> AuditQuestion:
    active = [question for question in snapshot.questions if question.status == "unanswered"]
    if len(active) != 1:
        raise AuditWorkflowError("audit must have exactly one active question")
    return active[0]


def _next_area_question(snapshot: AuditSnapshot) -> AuditQuestion | None:
    if snapshot.probe_plan is None:
        raise AuditWorkflowError("audit snapshot has no validated probe plan")
    for area in snapshot.probe_plan.areas:
        coverage = _coverage(snapshot, area.area_id)
        if coverage.status == "pending" and coverage.attribution_stage == "none":
            return _capability_question(snapshot, area, "hard", 0)
    return None


def _with_next_or_terminal(snapshot: AuditSnapshot) -> AuditSnapshot:
    next_question = _next_area_question(snapshot)
    if next_question is None:
        return _enter_reviewing(snapshot)
    return snapshot.model_copy(update={"questions": (*snapshot.questions, next_question)})


def _conflict_messages(snapshot: AuditSnapshot) -> tuple[str, ...]:
    return tuple(
        f"Artifact says: {conflict.artifact_claim}; user says: {conflict.user_claim}"
        for conflict in snapshot.attribution_conflicts
    )


def _entry_basis(snapshot: AuditSnapshot, area_id: str) -> tuple[tuple[str, ...], tuple[str, ...]]:
    questions = tuple(
        question for question in snapshot.questions if question.capability_area_id == area_id
    )
    answer_ids = {answer.question_id for answer in snapshot.answers}
    answer_references = tuple(
        f"answer:{question.id}" for question in questions if question.id in answer_ids
    )
    area = _area_for(snapshot, area_id)
    artifact_references = tuple(
        _fact_for(snapshot, area).source_locator for _ in area.inspected_fact_ids[:1]
    )
    return artifact_references, answer_references


def _conclusion_entry(snapshot: AuditSnapshot, coverage: AuditCoverage) -> ConclusionEntry:
    artifact_references, answer_references = _entry_basis(snapshot, coverage.area_id)
    conflicts = _conflict_messages(snapshot)
    record = _attribution(snapshot, coverage.area_id)
    if coverage.status == "verified":
        if (
            coverage.attribution_stage != "complete"
            or record.ownership_answer is None
            or record.assistance_answer is None
            or coverage.strongest_capability is None
            or coverage.next_higher_not_established is None
        ):
            raise AuditWorkflowError(
                "verified conclusion requires terminal boundary plus ownership and assistance"
            )
        return ConclusionEntry(
            id=f"entry-{coverage.area_id}",
            area=coverage.area_id,
            strongest_capability=coverage.strongest_capability,
            next_higher_not_established=coverage.next_higher_not_established,
            basis=(*artifact_references, *answer_references),
            artifact_references=artifact_references,
            answer_references=answer_references,
            source_type="artifact-and-answer",
            responsibility_boundary=f"{record.ownership}: {record.ownership_answer}",
            assistance_boundary=f"{record.assistance}: {record.assistance_answer}",
            verification="audit-verified",
            conflicts=conflicts,
            unresolved_gaps=tuple(
                limitation for limitation in snapshot.limitations if limitation not in conflicts
            ),
        )
    if coverage.status == "skipped":
        rating = coverage.self_rating or ""
        return ConclusionEntry(
            id=f"entry-{coverage.area_id}",
            area=coverage.area_id,
            basis=answer_references or ("self-rating supplied without an audit answer",),
            artifact_references=artifact_references,
            answer_references=answer_references,
            source_type="answer-only",
            responsibility_boundary="unresolved: Contribution interview was skipped",
            assistance_boundary="unresolved: Contribution interview was skipped",
            verification="self-assessed-unverified",
            conflicts=conflicts,
            unresolved_gaps=(
                "No capability boundary was audited.",
                "Responsibility and assistance were not established.",
            ),
            self_rating=rating,
        )
    return ConclusionEntry(
        id=f"entry-{coverage.area_id}",
        area=coverage.area_id,
        basis=answer_references or ("no terminal capability answer",),
        artifact_references=artifact_references,
        answer_references=answer_references,
        source_type="answer-only",
        responsibility_boundary=(
            f"{record.ownership}: {record.ownership_answer}"
            if record.ownership_answer
            else "unresolved: no ownership answer"
        ),
        assistance_boundary=(
            f"{record.assistance}: {record.assistance_answer}"
            if record.assistance_answer
            else "unresolved: no assistance answer"
        ),
        verification="unresolved",
        conflicts=conflicts,
        unresolved_gaps=(
            "No capability boundary was established.",
            "Attribution remains unresolved where no separate turn was completed.",
        ),
    )


def _enter_reviewing(snapshot: AuditSnapshot) -> AuditSnapshot:
    entries = tuple(_conclusion_entry(snapshot, coverage) for coverage in snapshot.coverage)
    original_proposal = {
        "entries": [entry.model_dump(mode="json") for entry in entries],
        "whole_review": "pending",
    }
    original_hash = original_proposal_digest(original_proposal)
    conclusion = AuditConclusion(
        entries=entries,
        original_proposal=original_proposal,
        original_proposal_hash=original_hash,
        effective_conclusion_hash=effective_conclusion_digest(entries, "pending"),
    )
    return snapshot.model_copy(
        update={
            "status": "reviewing",
            "conclusion": conclusion,
            "conclusion_lineage_hash": conclusion_lineage_digest(conclusion, ()),
        }
    )


def _append_review(
    snapshot: AuditSnapshot,
    *,
    target: str,
    outcome: str,
    reviewer_id: str,
    reason: str,
    entry_id: str | None = None,
    correction: str | None = None,
) -> AuditSnapshot:
    if snapshot.conclusion is None:
        raise AuditWorkflowError("review requires a conclusion")
    before_hash = snapshot.conclusion.effective_conclusion_hash
    entries = list(snapshot.conclusion.entries)
    whole_review = snapshot.conclusion.whole_review
    if target == "entry":
        index = next((i for i, entry in enumerate(entries) if entry.id == entry_id), None)
        if index is None:
            raise AuditWorkflowError("selected conclusion entry is missing")
        review = {"confirm": "confirmed", "edit": "edited", "reject": "rejected"}[outcome]
        entries[index] = entries[index].model_copy(
            update={"review": review, "correction": correction}
        )
    else:
        whole_review = {"confirm": "confirmed", "reject": "rejected"}[outcome]
    ordered_entries = tuple(entries)
    after_hash = effective_conclusion_digest(ordered_entries, whole_review)
    conclusion = snapshot.conclusion.model_copy(
        update={
            "entries": ordered_entries,
            "whole_review": whole_review,
            "effective_conclusion_hash": after_hash,
        }
    )
    review = ConclusionReview(
        review_id=f"review-{len(snapshot.conclusion_reviews) + 1}",
        target=target,
        outcome=outcome,
        reviewer_id=reviewer_id,
        reason=reason,
        entry_id=entry_id,
        correction=correction,
        sequence=len(snapshot.conclusion_reviews) + 1,
        before_effective_hash=before_hash,
        after_effective_hash=after_hash,
    )
    status = snapshot.status
    if target == "whole-conclusion":
        status = "completed" if outcome == "confirm" else "rejected"
    reviews = (*snapshot.conclusion_reviews, review)
    return snapshot.model_copy(
        update={
            "status": status,
            "conclusion": conclusion,
            "conclusion_reviews": reviews,
            "conclusion_lineage_hash": conclusion_lineage_digest(conclusion, reviews),
        }
    )


def start_audit(
    *,
    workspace: Path,
    fixture_path: Path,
    manifest_path: Path,
    contribution_id: str,
    audit_id: str | None = None,
    decision_port: AuditDecisionPort | None = None,
) -> AuditSnapshot:
    facts, limitations = inspect_contribution(fixture_path, manifest_path, contribution_id)
    port = decision_port or FakeDecisionPort()
    plan = validate_probe_plan(port.plan_probe(contribution_id, facts), facts)
    aid = audit_id or f"audit-{uuid4().hex[:12]}"
    base = AuditSnapshot(
        audit_id=aid,
        contribution_id=contribution_id,
        status="active",
        questions=(),
        inspected_facts=facts,
        limitations=limitations,
        probe_plan=plan,
        coverage=tuple(AuditCoverage(area_id=area.area_id) for area in plan.areas),
    )
    first = _next_area_question(base)
    if first is None:
        raise AuditWorkflowError("validated probe plan contains no capability questions")
    snapshot = base.model_copy(update={"questions": (first,)})
    AuditStore(workspace).create(snapshot)
    return snapshot


def _answer_question(
    snapshot: AuditSnapshot, question: AuditQuestion, answer: str
) -> AuditSnapshot:
    questions = list(snapshot.questions)
    questions[questions.index(question)] = question.model_copy(update={"status": "answered"})
    return snapshot.model_copy(
        update={
            "questions": tuple(questions),
            "answers": (*snapshot.answers, AuditAnswer(question_id=question.id, answer=answer)),
        }
    )


def _skip_area(snapshot: AuditSnapshot, question: AuditQuestion, self_rating: str) -> AuditSnapshot:
    questions = list(snapshot.questions)
    questions[questions.index(question)] = question.model_copy(update={"status": "skipped"})
    coverage = _coverage(snapshot, question.capability_area_id or question.area)
    skipped = coverage.model_copy(
        update={"status": "skipped", "self_rating": self_rating, "attribution_stage": "none"}
    )
    updated = snapshot.model_copy(
        update={
            "questions": tuple(questions),
            "answers": (
                *snapshot.answers,
                AuditAnswer(question_id=question.id, answer=self_rating, skipped=True),
            ),
            "coverage": _replace_coverage(snapshot, skipped),
        }
    )
    return _with_next_or_terminal(updated)


def _enter_attribution(
    snapshot: AuditSnapshot,
    question: AuditQuestion,
    coverage: AuditCoverage,
    *,
    resume: bool,
) -> AuditSnapshot:
    area = _area_for(snapshot, question.capability_area_id or question.area)
    revised = coverage.model_copy(
        update={
            "attribution_stage": "ownership",
            "resume_difficulty": question.difficulty if resume else None,
            "resume_follow_up_count": question.follow_up_count if resume else None,
        }
    )
    updated = snapshot.model_copy(update={"coverage": _replace_coverage(snapshot, revised)})
    return updated.model_copy(
        update={
            "questions": (*updated.questions, _attribution_question(updated, area, "ownership"))
        }
    )


def _answer_capability(
    snapshot: AuditSnapshot,
    question: AuditQuestion,
    answer: str,
    decision_port: AuditDecisionPort,
) -> AuditSnapshot:
    area = _area_for(snapshot, question.capability_area_id or question.area)
    decision = validate_boundary_decision(
        decision_port.decide_boundary(question, answer), question=question, answer=answer, area=area
    )
    updated = _answer_question(snapshot, question, answer)
    updated = updated.model_copy(update={"decisions": (*updated.decisions, decision)})
    coverage = _coverage(updated, area.area_id)
    if decision.outcome == "attribution-signal":
        return _enter_attribution(updated, question, coverage, resume=True)
    if decision.outcome == "established":
        established = coverage.model_copy(
            update={
                "difficulty_reached": question.difficulty,
                "strongest_capability": decision.strongest_capability,
                "next_higher_not_established": decision.next_higher_not_established,
            }
        )
        updated = updated.model_copy(update={"coverage": _replace_coverage(updated, established)})
        return _enter_attribution(updated, question, established, resume=False)
    unknown = answer.casefold() in {"不知道", "不清楚", "i don't know", "don't know"}
    if question.follow_up_count == 0 and not unknown:
        follow = _capability_question(updated, area, question.difficulty, 1)
        return updated.model_copy(update={"questions": (*updated.questions, follow)})
    lower = _DIFFICULTY_ORDER[question.difficulty]
    if lower is not None:
        next_question = _capability_question(updated, area, lower, 0)
        return updated.model_copy(update={"questions": (*updated.questions, next_question)})
    unresolved = coverage.model_copy(
        update={
            "status": "unresolved",
            "difficulty_reached": "simple",
            "attribution_stage": "complete",
        }
    )
    return _with_next_or_terminal(
        updated.model_copy(update={"coverage": _replace_coverage(updated, unresolved)})
    )


def _answer_ownership(
    snapshot: AuditSnapshot, question: AuditQuestion, answer: str
) -> AuditSnapshot:
    area_id = question.capability_area_id or question.area
    area = _area_for(snapshot, area_id)
    record = _attribution(snapshot, area_id)
    ownership = _classify_ownership(answer)
    updated_record = record.model_copy(update={"ownership_answer": answer, "ownership": ownership})
    coverage = _coverage(snapshot, area_id).model_copy(update={"attribution_stage": "assistance"})
    conflicts = snapshot.attribution_conflicts
    if ownership == "other-person-owned":
        conflicts = (
            *conflicts,
            AttributionConflict(
                artifact_claim=_fact_for(snapshot, area).statement, user_claim=answer
            ),
        )
    updated = _answer_question(snapshot, question, answer).model_copy(
        update={
            "attribution_records": _replace_attribution(snapshot, updated_record),
            "coverage": _replace_coverage(snapshot, coverage),
            "attribution_conflicts": conflicts,
        }
    )
    assistance_question = _attribution_question(updated, area, "assistance")
    return updated.model_copy(update={"questions": (*updated.questions, assistance_question)})


def _answer_assistance(
    snapshot: AuditSnapshot, question: AuditQuestion, answer: str
) -> AuditSnapshot:
    area_id = question.capability_area_id or question.area
    record = _attribution(snapshot, area_id)
    assistance, scope, tool, model = _classify_assistance(answer)
    updated_record = record.model_copy(
        update={
            "assistance_answer": answer,
            "assistance": assistance,
            "assistance_scope": scope,
            "tool": tool,
            "model": model,
        }
    )
    prior = _coverage(snapshot, area_id)
    complete = prior.model_copy(update={"attribution_stage": "complete"})
    updated = _answer_question(snapshot, question, answer).model_copy(
        update={
            "attribution_records": _replace_attribution(snapshot, updated_record),
            "coverage": _replace_coverage(snapshot, complete),
            "attribution": AuditAttribution(
                ownership=updated_record.ownership,
                assistance=updated_record.assistance,
                tool=tool,
                model=model,
            ),
        }
    )
    if prior.resume_difficulty is not None:
        area = _area_for(updated, area_id)
        resumed = _capability_question(
            updated, area, prior.resume_difficulty, prior.resume_follow_up_count or 0
        )
        reopened = complete.model_copy(
            update={
                "attribution_stage": "none",
                "resume_difficulty": None,
                "resume_follow_up_count": None,
            }
        )
        return updated.model_copy(
            update={
                "coverage": _replace_coverage(updated, reopened),
                "questions": (*updated.questions, resumed),
            }
        )
    verified = complete.model_copy(update={"status": "verified"})
    return _with_next_or_terminal(
        updated.model_copy(update={"coverage": _replace_coverage(updated, verified)})
    )


def transition_audit(
    snapshot: AuditSnapshot,
    action: AuditAction,
    *,
    decision_port: AuditDecisionPort | None = None,
) -> AuditSnapshot:
    """Apply one user action; decision ports never own snapshot writes or transitions."""
    allowed = {
        "active": {"answer", "skip", "skip-contribution", "pause"},
        "paused": {"resume"},
        "reviewing": {"review-entry", "review-conclusion"},
        "completed": set(),
        "rejected": set(),
    }
    if action.action not in allowed[snapshot.status]:
        raise AuditWorkflowError(
            f"action {action.action} is not allowed while audit is {snapshot.status}"
        )
    if action.action == "pause":
        _active_question(snapshot)
        return snapshot.model_copy(update={"status": "paused"})
    if action.action == "resume":
        _active_question(snapshot)
        return snapshot.model_copy(update={"status": "active"})
    if action.action == "skip-contribution":
        active = _active_question(snapshot)
        if action.question_id is not None and action.question_id != active.id:
            raise AuditWorkflowError("supplied question target does not match the active question")
        questions = tuple(
            item.model_copy(update={"status": "skipped"}) if item.status == "unanswered" else item
            for item in snapshot.questions
        )
        coverage = tuple(
            item.model_copy(
                update={
                    "status": "skipped",
                    "self_rating": action.answer,
                    "attribution_stage": "none",
                }
            )
            for item in snapshot.coverage
        )
        return _enter_reviewing(
            snapshot.model_copy(
                update={
                    "questions": questions,
                    "answers": (
                        *snapshot.answers,
                        AuditAnswer(
                            question_id=active.id, answer=action.answer or "", skipped=True
                        ),
                    ),
                    "coverage": coverage,
                }
            )
        )
    if action.action == "review-entry":
        return _append_review(
            snapshot,
            target="entry",
            outcome=action.decision or "",
            entry_id=action.entry_id,
            correction=action.correction,
            reviewer_id=action.reviewer_id or "",
            reason=action.reason or "",
        )
    if action.action == "review-conclusion":
        return _append_review(
            snapshot,
            target="whole-conclusion",
            outcome=action.decision or "",
            reviewer_id=action.reviewer_id or "",
            reason=action.reason or "",
        )
    question = _active_question(snapshot)
    if action.question_id is not None and action.question_id != question.id:
        raise AuditWorkflowError("supplied question target does not match the active question")
    if action.action == "skip":
        if question.turn != "capability":
            raise AuditWorkflowError("only a capability area may be skipped")
        return _skip_area(snapshot, question, action.answer or "")
    answer = action.answer or ""
    if question.turn == "ownership":
        return _answer_ownership(snapshot, question, answer)
    if question.turn == "assistance":
        return _answer_assistance(snapshot, question, answer)
    return _answer_capability(snapshot, question, answer, decision_port or FakeDecisionPort())
