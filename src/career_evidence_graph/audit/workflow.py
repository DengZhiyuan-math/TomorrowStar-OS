from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from ..domain.fixtures import SealedFixtureRecord, load_sealed_fixture, verify_source_manifest
from ..validation.hashing import canonical_json_bytes, sha256_digest
from .models import (
    ArtifactFact,
    AssistanceRound,
    AttributionConflict,
    AuditAction,
    AuditAnswer,
    AuditAttribution,
    AuditConclusion,
    AuditCoverage,
    AuditQuestion,
    AuditSnapshot,
    ConclusionEntry,
    ConclusionReview,
    ResponsibilityRound,
)
from .store import AuditStore


class AuditWorkflowError(ValueError):
    """A rejected audit action or selected-fixture reference."""


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
    contribution = next((x for x in fixture.contributions if x.id == contribution_id), None)
    if contribution is None:
        raise AuditWorkflowError("selected Contribution is missing")
    claims = {x.id: x for x in fixture.claims}
    evidence = {x.id: x for x in fixture.evidence}
    missing_claims = [claim_id for claim_id in contribution.claim_ids if claim_id not in claims]
    if missing_claims:
        raise AuditWorkflowError(
            f"selected Contribution references missing claim: {missing_claims[0]}"
        )
    links = [x for x in fixture.claim_evidence_links if x.claim_id in contribution.claim_ids]
    if not links:
        raise AuditWorkflowError("Contribution has no linked evidence")
    for link in links:
        if link.claim_id not in claims:
            raise AuditWorkflowError(f"selected link references missing claim: {link.claim_id}")
        if link.evidence_id not in evidence:
            raise AuditWorkflowError(
                f"selected link references missing evidence: {link.evidence_id}"
            )
    identities = [(link.evidence_id, link.section_locator) for link in links]
    if len(identities) != len(set(identities)):
        raise AuditWorkflowError("duplicate evidence link")
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
            key=lambda x: (x.evidence_id, x.source_locator),
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


def start_audit(
    *,
    workspace: Path,
    fixture_path: Path,
    manifest_path: Path,
    contribution_id: str,
    audit_id: str | None = None,
    action_id: str | None = None,
) -> AuditSnapshot:
    facts, limitations = inspect_contribution(fixture_path, manifest_path, contribution_id)
    aid = audit_id or f"audit-{uuid4().hex[:12]}"
    question = _question("implementation", "hard", 0, facts)
    snapshot = AuditSnapshot(
        audit_id=aid,
        contribution_id=contribution_id,
        status="active",
        questions=(question,),
        inspected_facts=facts,
        limitations=limitations,
        coverage=(AuditCoverage(area_id="implementation"),),
    )
    AuditStore(workspace).save(snapshot, action_id=action_id)
    return snapshot


def _question(
    area: str, difficulty: str, follow_up: int, facts: tuple[ArtifactFact, ...]
) -> AuditQuestion:
    reference = facts[0].source_locator if facts else "selected Contribution"
    reason = (
        "The project record establishes bounded artifact facts, but personal capability "
        "remains unverified."
    )

    prompts = {
        (
            "implementation",
            "hard",
        ): (
            "What design trade-off did you personally make, and how did you verify "
            "the result under failure conditions?"
        ),
        (
            "implementation",
            "intermediate",
        ): "What implementation change did you personally make, and how did you check its result?",
        ("implementation", "simple"): "Which implementation step did you personally complete?",
        (
            "debugging",
            "hard",
        ): "How did you isolate and repair the most difficult failure in this Contribution?",
        (
            "debugging",
            "intermediate",
        ): "What symptom did you investigate, and what change fixed it?",
        (
            "operation",
            "hard",
        ): "How would you operate and verify this Contribution when its external dependency fails?",
        (
            "operation",
            "intermediate",
        ): "What operational check did you personally run after delivery?",
        (
            "responsibility",
            "hard",
        ): "Which decisions, integration, and acceptance of this result were yours?",
        (
            "assistance",
            "hard",
        ): (
            "Did a coding agent or third party assist with decisions, generation, "
            "modification, debugging, testing, or acceptance?"
        ),
    }
    return AuditQuestion(
        id=f"question-{area}-{difficulty}-{follow_up}",
        reason=reason,
        prompt=prompts[(area, difficulty)],
        area=area,
        area_id=area,
        difficulty=difficulty,
        inspection_reference=reference,
        follow_up_count=follow_up,
    )


_AREA_ORDER = ("implementation", "debugging", "operation", "responsibility", "assistance")


def _build_conclusion(snapshot: AuditSnapshot) -> AuditConclusion | None:
    """Build the Phase 3 prose proposal only after every area has a terminal state."""
    coverage = {item.area_id: item for item in snapshot.coverage}
    if any(
        coverage.get(area) is None or coverage[area].status == "pending" for area in _AREA_ORDER
    ):
        return None
    entries: list[ConclusionEntry] = []
    artifact_refs = tuple(f.evidence_id for f in snapshot.inspected_facts)
    for area in _AREA_ORDER:
        item = coverage[area]
        answer_refs = tuple(
            answer.question_id
            for answer in snapshot.answers
            if answer.question_id.startswith(f"question-{area}-")
        )
        level = item.difficulty_reached or "unresolved"
        if item.status == "verified":
            strongest = (
                f"The user established {level}-level {area} capability for this Contribution."
            )
            verification = "audit-verified"
        elif item.status == "skipped":
            strongest = "No audited capability was established; the user skipped this area."
            verification = "self-assessed-unverified"
        else:
            strongest = f"No {area} capability was established from the available answers."
            verification = "unresolved"
        basis = answer_refs or ("unresolved",)
        responsibility = (
            snapshot.responsibility_round.ownership
            if snapshot.responsibility_round
            else "unresolved"
        )
        assistance = (
            snapshot.assistance_round.assistance if snapshot.assistance_round else "unresolved"
        )
        conflicts = (
            tuple(c.user_claim for c in snapshot.attribution_conflicts)
            if area == "responsibility"
            else ()
        )
        gaps = tuple(snapshot.limitations) + ((item.self_rating,) if item.self_rating else ())
        entries.append(
            ConclusionEntry(
                id=f"entry-{area}",
                area=area,
                strongest_capability=strongest,
                next_higher_not_established=(
                    f"The next higher {area} capability is not established by this audit."
                ),
                basis=basis,
                artifact_references=artifact_refs,
                answer_references=answer_refs,
                source_type="answer-only" if answer_refs else "documentary-context-only",
                responsibility_boundary=(
                    f"Responsibility is {responsibility}; it is not inferred "
                    "from artifact proximity."
                ),
                assistance_boundary=(
                    f"Assistance is {assistance}; assistance does not establish mastery."
                ),
                verification=verification,
                conflicts=conflicts,
                unresolved_gaps=gaps,
            )
        )
    payload = {
        "entries": [entry.model_dump(mode="json") for entry in entries],
        "whole_review": "pending",
    }
    proposal_hash = sha256_digest(canonical_json_bytes(payload))
    return AuditConclusion(
        entries=tuple(entries),
        original_proposal_hash=proposal_hash,
        effective_conclusion_hash=proposal_hash,
        original_proposal=payload,
    )


def _effective_hash(entries: tuple[ConclusionEntry, ...], whole_review: str) -> str:
    return sha256_digest(
        canonical_json_bytes(
            {
                "entries": [entry.model_dump(mode="json") for entry in entries],
                "whole_review": whole_review,
            }
        )
    )


def _classify_ownership(text: str) -> str:
    value = text.casefold()
    if "不是我" in value:
        return "other-person-owned"
    matches = {
        "user-owned": any(
            token in value
            for token in (
                "i owned",
                "i implemented",
                "i was responsible",
                "i did",
                "我负责",
                "我做",
                "我实现",
            )
        ),
        "team-owned": any(
            token in value for token in ("team owned", "team did", "the team", "团队负责", "团队做")
        ),
        "other-person-owned": any(
            token in value
            for token in ("not me", "someone else", "other person", "不是我", "他人负责", "别人做")
        ),
    }
    found = [kind for kind, matched in matches.items() if matched]
    return found[0] if len(found) == 1 else "unresolved"


def _classify_assistance(text: str) -> str:
    value = text.casefold()
    matches = {
        "none": any(
            token in value
            for token in (
                "no outside assistance",
                "no assistance",
                "without assistance",
                "没有外部协助",
                "没有协助",
                "无协助",
            )
        ),
        "coding-agent-assisted": any(
            token in value
            for token in ("coding agent", "codex", "chatgpt", "gpt", "编码代理", "代码代理")
        ),
        "third-party-assisted": any(
            token in value
            for token in ("third party", "external consultant", "第三方协助", "外部顾问")
        ),
    }
    found = [kind for kind, matched in matches.items() if matched]
    return found[0] if len(found) == 1 else "unresolved"


def _review_conclusion(snapshot: AuditSnapshot, action: AuditAction) -> AuditSnapshot:
    conclusion = snapshot.conclusion
    if conclusion is None:
        raise AuditWorkflowError("coverage is incomplete; conclusion is not available")
    if action.expected_effective_conclusion_hash != conclusion.effective_conclusion_hash:
        raise AuditWorkflowError("stale expected effective conclusion hash")
    if action.action == "review-entry":
        entry = next((item for item in conclusion.entries if item.id == action.entry_id), None)
        if entry is None:
            raise AuditWorkflowError("review entry is missing")
        if entry.review in {"confirmed", "rejected"}:
            terminal = next(
                (
                    review
                    for review in reversed(snapshot.conclusion_reviews)
                    if review.target == "entry" and review.entry_id == entry.id
                ),
                None,
            )
            if terminal and (
                terminal.outcome == action.decision
                and terminal.reviewer_id == action.reviewer_id
                and terminal.reason == action.reason
            ):
                return snapshot
            raise AuditWorkflowError("review target already has a terminal review")
        entries = tuple(
            item.model_copy(
                update={
                    "review": {
                        "edit": "edited",
                        "confirm": "confirmed",
                        "reject": "rejected",
                    }[action.decision or "reject"],
                    "correction": action.correction
                    if action.decision == "edit"
                    else item.correction,
                }
            )
            if item.id == entry.id
            else item
            for item in conclusion.entries
        )
        whole_review = conclusion.whole_review
        status = "reviewing"
    elif action.decision == "confirm":
        reviewed_entries = {
            review.entry_id
            for review in snapshot.conclusion_reviews
            if review.target == "entry" and review.outcome in {"confirm", "edit"}
        }
        if any(
            entry.review not in {"confirmed", "edited"} and entry.id not in reviewed_entries
            for entry in conclusion.entries
        ):
            raise AuditWorkflowError(
                "whole confirmation requires every entry to be confirmed or edited"
            )
        entries = conclusion.entries
        whole_review = "confirmed"
        status = "completed"
    else:
        entries = conclusion.entries
        whole_review = "rejected"
        status = "rejected"
    after_hash = _effective_hash(entries, whole_review)
    review = ConclusionReview(
        review_id=f"review-{uuid4().hex[:12]}",
        target="entry" if action.action == "review-entry" else "whole-conclusion",
        outcome=action.decision or "reject",
        reviewer_id=action.reviewer_id or "",
        reason=action.reason or "",
        original_proposal_hash=conclusion.original_proposal_hash,
        expected_event_hash=action.expected_event_hash,
        expected_effective_conclusion_hash=action.expected_effective_conclusion_hash,
        before_effective_hash=conclusion.effective_conclusion_hash,
        after_effective_hash=after_hash,
        entry_id=action.entry_id,
        correction=action.correction,
        original_proposal=conclusion.original_proposal,
    )
    updated_conclusion = conclusion.model_copy(
        update={
            "entries": entries,
            "whole_review": whole_review,
            "effective_conclusion_hash": after_hash,
            "review_reason": action.reason,
        }
    )
    return snapshot.model_copy(
        update={
            "status": status,
            "conclusion": updated_conclusion,
            "conclusion_reviews": snapshot.conclusion_reviews + (review,),
            "accepted_action_ids": snapshot.accepted_action_ids
            + ((action.action_id,) if action.action_id else ()),
        }
    )


def transition_audit(
    store: AuditStore, snapshot: AuditSnapshot, action: AuditAction
) -> AuditSnapshot:
    allowed_actions = {
        "active": {"answer", "skip", "pause"},
        "paused": {"resume"},
        "reviewing": {"review-entry", "review-conclusion"},
        "completed": set(),
        "rejected": set(),
    }
    if action.action not in allowed_actions[snapshot.status]:
        raise AuditWorkflowError(
            "coverage is incomplete or action "
            f"{action.action} is not allowed while audit is {snapshot.status}"
        )
    if action.action_id and action.action_id in snapshot.accepted_action_ids:
        return snapshot
    if action.action in {"review-entry", "review-conclusion"}:
        if not action.expected_event_hash:
            raise AuditWorkflowError("review requires expected event hash")
        return _review_conclusion(snapshot, action)
    if action.expected_snapshot_hash:
        actual = sha256_digest(canonical_json_bytes(snapshot.model_dump(mode="json")))
        if action.expected_snapshot_hash != actual:
            raise AuditWorkflowError("stale audit snapshot; optimistic concurrency check failed")
    questions = list(snapshot.questions)
    answers = list(snapshot.answers)
    if action.action == "pause":
        if snapshot.conclusion is not None or not any(q.status == "unanswered" for q in questions):
            raise AuditWorkflowError("pause requires unfinished coverage without a conclusion")
        return snapshot.model_copy(update={"status": "paused"})
    if action.action == "resume":
        if snapshot.conclusion is not None or not any(q.status == "unanswered" for q in questions):
            raise AuditWorkflowError("resume requires unfinished coverage without a conclusion")
        return snapshot.model_copy(update={"status": "active"})
    if action.action in {"answer", "skip"}:
        q = next((q for q in questions if q.status == "unanswered"), None)
        if q is None:
            raise AuditWorkflowError("no unanswered question")
        is_skip = action.action == "skip"
        questions[questions.index(q)] = q.model_copy(
            update={"status": "skipped" if is_skip else "answered"}
        )
        answers.append(
            AuditAnswer(
                question_id=q.id, answer=action.answer or "skipped", skipped=action.action == "skip"
            )
        )
        coverage = list(snapshot.coverage)
        current = next((c for c in coverage if c.area_id == (q.area_id or q.area)), None)
        if current is None:
            current = AuditCoverage(area_id=q.area)
            coverage.append(current)
        text = action.answer or "skipped"
        incomplete = any(
            token in text.lower()
            for token in ("不知道", "不清楚", "不完整", "不确定", "don't know")
        )
        if is_skip:
            coverage[coverage.index(current)] = current.model_copy(
                update={"status": "skipped", "self_rating": text}
            )
            next_area = {
                "implementation": "debugging",
                "debugging": "operation",
                "operation": "responsibility",
                "responsibility": "assistance",
            }.get(q.area)
            if next_area:
                questions.append(_question(next_area, "hard", 0, snapshot.inspected_facts))
        elif incomplete and q.follow_up_count == 0:
            follow = _question(q.area, q.difficulty, 1, snapshot.inspected_facts)
            questions.append(follow)
        elif incomplete:
            lower = {"hard": "intermediate", "intermediate": "simple", "simple": "simple"}[
                q.difficulty
            ]
            if lower == "simple" and q.difficulty == "simple":
                coverage[coverage.index(current)] = current.model_copy(
                    update={"status": "unresolved", "difficulty_reached": q.difficulty}
                )
            else:
                questions.append(_question(q.area, lower, 0, snapshot.inspected_facts))
        else:
            coverage[coverage.index(current)] = current.model_copy(
                update={"status": "verified", "difficulty_reached": q.difficulty}
            )
            if q.area == "implementation":
                questions.append(_question("debugging", "hard", 0, snapshot.inspected_facts))
            elif q.area == "debugging":
                questions.append(_question("operation", "hard", 0, snapshot.inspected_facts))
            elif q.area == "operation":
                questions.append(_question("responsibility", "hard", 0, snapshot.inspected_facts))
            elif q.area == "responsibility":
                questions.append(_question("assistance", "hard", 0, snapshot.inspected_facts))
        attribution = snapshot.attribution
        if q.area == "responsibility":
            ownership = _classify_ownership(text)
            rr = ResponsibilityRound(answer=text, ownership=ownership)
            attribution = AuditAttribution(ownership=ownership, assistance="unresolved")
        else:
            rr = snapshot.responsibility_round
        ar = snapshot.assistance_round
        if q.area == "assistance":
            kind = _classify_assistance(text)
            ar = AssistanceRound(answer=text, assistance=kind)
            attribution = AuditAttribution(
                ownership=(attribution.ownership if attribution else "unresolved"), assistance=kind
            )
        conflicts = list(snapshot.attribution_conflicts)
        if (
            q.area == "responsibility"
            and ownership == "other-person-owned"
            and snapshot.inspected_facts
        ):
            conflicts.append(
                AttributionConflict(
                    artifact_claim=snapshot.inspected_facts[0].statement, user_claim=text
                )
            )
        updated = snapshot.model_copy(
            update={
                "questions": tuple(questions),
                "answers": tuple(answers),
                "attribution": attribution,
                "coverage": tuple(coverage),
                "responsibility_round": rr,
                "assistance_round": ar,
                "attribution_conflicts": tuple(conflicts),
                "accepted_action_ids": snapshot.accepted_action_ids
                + ((action.action_id,) if action.action_id else ()),
            }
        )
        conclusion = _build_conclusion(updated)
        return updated.model_copy(
            update={"conclusion": conclusion, "status": "reviewing" if conclusion else "active"}
        )
    raise AuditWorkflowError("invalid audit transition")
