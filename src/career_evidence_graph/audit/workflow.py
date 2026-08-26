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
    ResponsibilityRound,
)
from .store import AuditStore


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
        raise ValueError("selected Contribution is missing")
    claims = {x.id: x for x in fixture.claims}
    links = [x for x in fixture.claim_evidence_links if x.claim_id in contribution.claim_ids]
    evidence = {x.id: x for x in fixture.evidence}
    if not links:
        raise ValueError("Contribution has no linked evidence")
    identities = [(link.evidence_id, link.section_locator) for link in links]
    if len(identities) != len(set(identities)):
        raise ValueError("duplicate evidence link")
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
    AuditStore(workspace).save(snapshot)
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
        basis = tuple(dict.fromkeys((*answer_refs, *artifact_refs))) or ("unresolved",)
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
                source_type="artifact-and-answer"
                if artifact_refs and answer_refs
                else ("artifact-only" if artifact_refs else "answer-only"),
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
    payload = {"entries": [entry.model_dump(mode="json") for entry in entries]}
    return AuditConclusion(
        entries=tuple(entries), original_proposal_hash=sha256_digest(canonical_json_bytes(payload))
    )


def transition_audit(
    store: AuditStore, snapshot: AuditSnapshot, action: AuditAction
) -> AuditSnapshot:
    if action.expected_snapshot_hash:
        actual = sha256_digest(canonical_json_bytes(snapshot.model_dump(mode="json")))
        if action.expected_snapshot_hash != actual:
            raise ValueError("stale audit snapshot; optimistic concurrency check failed")
    if action.action_id and action.action_id in snapshot.accepted_action_ids:
        return snapshot
    questions = list(snapshot.questions)
    answers = list(snapshot.answers)
    if action.action == "pause":
        return snapshot.model_copy(update={"status": "paused"})
    if action.action == "resume":
        if snapshot.status != "paused":
            raise ValueError("audit is not paused")
        return snapshot.model_copy(update={"status": "active"})
    if action.action in {"answer", "skip"}:
        q = next((q for q in questions if q.status == "unanswered"), None)
        if q is None:
            raise ValueError("no unanswered question")
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
            ownership = (
                "other-person-owned"
                if "不是我" in text
                else (
                    "team-owned"
                    if "团队" in text
                    else ("user-owned" if "我" in text else "unresolved")
                )
            )
            rr = ResponsibilityRound(answer=text, ownership=ownership)
            attribution = AuditAttribution(ownership=ownership, assistance="unresolved")
        else:
            rr = snapshot.responsibility_round
        ar = snapshot.assistance_round
        if q.area == "assistance":
            kind = (
                "coding-agent-assisted"
                if any(x in text.lower() for x in ("agent", "codex", "gpt", "coding"))
                else (
                    "third-party-assisted"
                    if "第三方" in text
                    else ("none" if "没有" in text or "无" in text else "unresolved")
                )
            )
            ar = AssistanceRound(answer=text, assistance=kind)
            attribution = AuditAttribution(
                ownership=(attribution.ownership if attribution else "unresolved"), assistance=kind
            )
        conflicts = list(snapshot.attribution_conflicts)
        if q.area == "responsibility" and "不是我" in text and snapshot.inspected_facts:
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
        return updated.model_copy(update={"conclusion": conclusion})
    if action.action == "review-entry" and snapshot.conclusion:
        entries = list(snapshot.conclusion.entries)
        entry = next(x for x in entries if x.id == action.entry_id)
        entries[entries.index(entry)] = entry.model_copy(
            update={
                "review": {"confirm": "confirmed", "edit": "edited", "reject": "rejected"}[
                    action.decision or "reject"
                ],
                "correction": action.correction,
            }
        )
        return snapshot.model_copy(
            update={
                "conclusion": snapshot.conclusion.model_copy(update={"entries": tuple(entries)})
            }
        )
    if action.action == "review-conclusion" and snapshot.conclusion:
        return snapshot.model_copy(
            update={
                "conclusion": snapshot.conclusion.model_copy(
                    update={
                        "whole_review": "confirmed" if action.decision == "confirm" else "rejected",
                        "review_reason": action.reason,
                    }
                )
            }
        )
    if action.action == "review-conclusion" and snapshot.conclusion is None:
        raise ValueError("coverage is incomplete; conclusion is not available")
    raise ValueError("invalid audit transition")
