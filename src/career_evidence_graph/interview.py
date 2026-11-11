"""Inventory-bound project interviews using the existing Contribution audit engine."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Literal

from pydantic import Field, model_validator

from .audit.decision import AuditDecisionPort, FakeDecisionPort, validate_project_interview_plan
from .audit.models import (
    ArtifactFact,
    AuditAction,
    AuditAnswer,
    AuditQuestion,
    AuditSnapshot,
    BoundaryDecision,
    ProjectInterviewPlan,
)
from .audit.workflow import begin_inspected_audit, transition_audit
from .validation.hashing import canonical_json_bytes, sha256_digest
from .validation.models import StrictModel
from .validation.store import atomic_write_canonical_json, create_only_canonical_bundle
from .workspace import open_private_workspace

HASH = r"^sha256:[a-f0-9]{64}$"
ID = r"^[a-z][a-z0-9._-]+$"


class SourceReference(StrictModel):
    source_id: str = Field(pattern=ID)
    capture_hash: str = Field(pattern=HASH)


class SourceFact(ArtifactFact):
    source: SourceReference


class InventoryEntry(StrictModel):
    outcome: Literal["confirmed", "unresolved", "excluded-with-reason", "merged", "edited", "split"]
    sources: tuple[SourceReference, ...]


class InventoryContext(StrictModel):
    """Result of the selected private operator's complete accepted-seal verification."""

    accepted_inventory_hash: str = Field(pattern=HASH)
    inventory_revision_hash: str = Field(pattern=HASH)
    entries: dict[str, InventoryEntry]


class ContributionContext(StrictModel):
    contribution_id: str = Field(pattern=r"^contrib-[a-z0-9-]+$")
    experience_id: str = Field(pattern=ID)
    inventory_revision_hash: str = Field(pattern=HASH)
    scope: str = Field(min_length=1)
    facts: tuple[SourceFact, ...] = Field(min_length=1)
    prior_questions: tuple[AuditQuestion, ...] = ()
    prior_answers: tuple[AuditAnswer, ...] = ()
    responsibility_notes: tuple[str, ...] = ()

    @model_validator(mode="after")
    def prior_answer_context(self):
        ids = {q.id for q in self.prior_questions}
        if len(ids) != len(self.prior_questions) or any(
            a.question_id not in ids for a in self.prior_answers
        ):
            raise ValueError("prior answers require their original questions")
        return self

    def inspected_facts(self) -> tuple[ArtifactFact, ...]:
        return tuple(
            ArtifactFact.model_validate(f.model_dump(exclude={"source"})) for f in self.facts
        )


class ProjectInterviewSnapshot(StrictModel):
    schema_version: Literal["project-interview-snapshot/v1"] = "project-interview-snapshot/v1"
    interview_id: str = Field(pattern=r"^interview-[a-z0-9-]+$")
    accepted_inventory_hash: str = Field(pattern=HASH)
    inventory_revision_hash: str = Field(pattern=HASH)
    plan: ProjectInterviewPlan
    contexts: tuple[ContributionContext, ...]
    readiness_review: dict[str, object] | None = None
    status: Literal["active", "paused", "reviewing", "completed", "rejected"] = "active"
    overview_answers: tuple[AuditAnswer, ...] = ()
    overview_context_requests: tuple[AuditAnswer, ...] = ()
    overview_decisions: tuple[BoundaryDecision, ...] = ()
    overview_review: Literal["pending", "confirmed", "rejected"] = "pending"
    overview_review_reason: str | None = None
    overview_reviewer_id: str | None = None
    audits: tuple[AuditSnapshot, ...] = ()
    plan_hash: str = Field(pattern=HASH)

    @property
    def active_layer(self) -> str | None:
        if not self.overview_answers:
            return "project-overview"
        for audit in self.audits:
            if audit.status == "active":
                return audit.probe_plan.question_layer
        if len(self.audits) < len(self.plan.depth_plans):
            return "project-depth"
        if len(self.audits) < len(self.plan.depth_plans) + len(self.plan.transfer_plans):
            return "transfer"
        return None

    @model_validator(mode="after")
    def retained_binding(self):
        if self.plan_hash != sha256_digest(canonical_json_bytes(self.plan)):
            raise ValueError("interview plan changed")
        facts = {c.contribution_id: c.inspected_facts() for c in self.contexts}
        validate_project_interview_plan(
            self.plan, experience_id=self.plan.experience_id, facts_by_contribution=facts
        )
        if any(
            c.inventory_revision_hash != self.inventory_revision_hash
            or c.experience_id != self.plan.experience_id
            for c in self.contexts
        ):
            raise ValueError("interview context binding changed")
        if len(facts) != len(self.contexts):
            raise ValueError("interview has duplicate Contribution contexts")
        plans = (*self.plan.depth_plans, *self.plan.transfer_plans)
        if len(self.audits) > len(plans) or any(
            a.probe_plan != p for a, p in zip(self.audits, plans, strict=False)
        ):
            raise ValueError("interview audits do not preserve planned layer order")
        return self


class ProjectInterviewAdapter:
    """A trusted-local operator supplies one verifier; all actions recheck its current seal."""

    def __init__(self, workspace: Path, *, inventory_loader: Callable[[], InventoryContext]):
        self.workspace = open_private_workspace(workspace)
        self.inventory_loader = inventory_loader

    def _path(self, interview_id: str) -> Path:
        import re

        if not re.fullmatch(r"interview-[a-z0-9-]+", interview_id):
            raise ValueError("unsafe interview ID")
        root = self.workspace / "interviews"
        if root.is_symlink() or (root / interview_id).is_symlink():
            raise ValueError("interview path is linked")
        return root / interview_id / "snapshot.json"

    def verify_binding(self, snapshot: ProjectInterviewSnapshot) -> InventoryContext:
        inventory = self.inventory_loader()
        if (
            inventory.accepted_inventory_hash != snapshot.accepted_inventory_hash
            or inventory.inventory_revision_hash != snapshot.inventory_revision_hash
        ):
            raise ValueError("stale accepted inventory binding")
        for context in snapshot.contexts:
            entry = inventory.entries.get(context.experience_id)
            if entry is None or entry.outcome != "confirmed":
                raise ValueError("Experience identity is not accepted for Contribution review")
            if any(f.source not in entry.sources for f in context.facts):
                raise ValueError("Contribution fact is outside accepted source bindings")
        return inventory

    def read(self, interview_id: str) -> ProjectInterviewSnapshot:
        path = self._path(interview_id)
        if path.is_symlink():
            raise ValueError("interview snapshot is linked")
        return ProjectInterviewSnapshot.model_validate_json(path.read_bytes())

    def start(
        self,
        interview_id: str,
        plan: ProjectInterviewPlan,
        contexts: tuple[ContributionContext, ...],
        *,
        readiness_review: dict[str, object] | None = None,
    ) -> ProjectInterviewSnapshot:
        inventory = self.inventory_loader()
        snapshot = ProjectInterviewSnapshot(
            interview_id=interview_id,
            plan=plan,
            contexts=contexts,
            accepted_inventory_hash=inventory.accepted_inventory_hash,
            inventory_revision_hash=inventory.inventory_revision_hash,
            plan_hash=sha256_digest(canonical_json_bytes(plan)),
            readiness_review=readiness_review,
        )
        self.verify_binding(snapshot)
        path = self._path(interview_id)
        create_only_canonical_bundle(path.parent.parent, interview_id, {"snapshot.json": snapshot})
        return snapshot

    @staticmethod
    def _prior_attribution(
        snapshot: ProjectInterviewSnapshot, context: ContributionContext
    ) -> tuple[tuple[AuditQuestion, ...], tuple[AuditAnswer, ...]]:
        questions = list(context.prior_questions)
        answers = list(context.prior_answers)
        for prior in snapshot.audits:
            if prior.contribution_id != context.contribution_id:
                continue
            for coverage in prior.coverage:
                questions = [
                    q for q in questions if (q.capability_area_id or q.area) != coverage.area_id
                ]
                record = next(
                    (r for r in prior.attribution_records if r.area_id == coverage.area_id), None
                )
                entry = (
                    next((e for e in prior.conclusion.entries if e.area == coverage.area_id), None)
                    if prior.conclusion
                    else None
                )
                if (
                    record is None
                    or prior.status == "rejected"
                    or prior.attribution_conflicts
                    or "unresolved" in (record.ownership, record.assistance)
                    or (entry and (entry.review == "rejected" or entry.correction is not None))
                ):
                    continue
                for turn, text in (
                    ("ownership", record.ownership_answer),
                    ("assistance", record.assistance_answer),
                ):
                    pair = next(
                        (
                            (q, a)
                            for q in reversed(prior.questions)
                            for a in prior.answers
                            if q.turn == turn
                            and (q.capability_area_id or q.area) == coverage.area_id
                            and a.question_id == q.id
                            and a.answer == text
                        ),
                        None,
                    )
                    if pair:
                        question, answer = pair
                        questions.append(
                            question.model_copy(
                                update={
                                    "reason": f"{prior.audit_id}: {question.reason}",
                                }
                            )
                        )
                        answers.append(answer)
        return tuple(questions), tuple(answers)

    @staticmethod
    def _advance(snapshot: ProjectInterviewSnapshot) -> ProjectInterviewSnapshot:
        if not snapshot.overview_answers or any(a.status == "active" for a in snapshot.audits):
            return snapshot
        plans = (*snapshot.plan.depth_plans, *snapshot.plan.transfer_plans)
        if len(snapshot.audits) == len(plans):
            return snapshot.model_copy(update={"status": "reviewing"})
        plan = plans[len(snapshot.audits)]
        context = next(c for c in snapshot.contexts if c.contribution_id == plan.contribution_id)
        prior_questions, prior_answers = ProjectInterviewAdapter._prior_attribution(
            snapshot, context
        )
        audit = begin_inspected_audit(
            contribution_id=plan.contribution_id,
            facts=context.inspected_facts(),
            plan=plan,
            audit_id=f"audit-{snapshot.interview_id}-{len(snapshot.audits) + 1}",
            limitations=context.responsibility_notes,
            prior_questions=prior_questions,
            prior_answers=prior_answers,
        )
        return snapshot.model_copy(update={"audits": (*snapshot.audits, audit)})

    def act(
        self,
        interview_id: str,
        action: AuditAction,
        *,
        decision_port: AuditDecisionPort | None = None,
        audit_id: str | None = None,
    ) -> ProjectInterviewSnapshot:
        snapshot = self.read(interview_id)
        self.verify_binding(snapshot)
        if action.action == "pause" and snapshot.status == "active":
            updated = snapshot.model_copy(update={"status": "paused"})
        elif action.action == "resume" and snapshot.status == "paused":
            updated = snapshot.model_copy(update={"status": "active"})
        elif snapshot.status == "active" and snapshot.active_layer == "project-overview":
            question = snapshot.plan.overview
            if action.question_id not in (None, question.id):
                raise ValueError("overview action targets another question")
            if action.action not in {"answer", "skip", "request-context"}:
                raise ValueError("invalid overview action")
            answer = AuditAnswer(
                question_id=question.id, answer=action.answer, skipped=action.action == "skip"
            )
            if action.action == "request-context":
                updated = snapshot.model_copy(
                    update={
                        "overview_context_requests": (*snapshot.overview_context_requests, answer)
                    }
                )
            else:
                decisions = snapshot.overview_decisions
                if action.action == "answer":
                    decision = (decision_port or FakeDecisionPort()).decide_boundary(
                        question, action.answer
                    )
                    from .audit.decision import validate_boundary_decision

                    validate_boundary_decision(decision, question=question, answer=action.answer)
                    decisions = (*decisions, decision)
                updated = self._advance(
                    snapshot.model_copy(
                        update={"overview_answers": (answer,), "overview_decisions": decisions}
                    )
                )
        elif snapshot.status in {"active", "reviewing"}:
            if action.action == "review-conclusion" and audit_id is None:
                if snapshot.active_layer is not None or any(
                    a.status not in {"completed", "rejected"} for a in snapshot.audits
                ):
                    raise ValueError("review each layer conclusion before the project conclusion")
                updated = snapshot.model_copy(
                    update={
                        "overview_review": "confirmed"
                        if action.decision == "confirm"
                        else "rejected",
                        "overview_review_reason": action.reason,
                        "overview_reviewer_id": action.reviewer_id,
                        "status": "completed" if action.decision == "confirm" else "rejected",
                    }
                )
            else:
                index = next(
                    (
                        i
                        for i, a in enumerate(snapshot.audits)
                        if a.audit_id == audit_id or (audit_id is None and a.status == "active")
                    ),
                    None,
                )
                if index is None:
                    raise ValueError("select an active or reviewable layer audit")
                audits = list(snapshot.audits)
                audits[index] = transition_audit(audits[index], action, decision_port=decision_port)
                updated = self._advance(snapshot.model_copy(update={"audits": tuple(audits)}))
        else:
            raise ValueError("action is not allowed in this interview state")
        updated = ProjectInterviewSnapshot.model_validate(updated.model_dump(mode="json"))
        self.verify_binding(updated)
        atomic_write_canonical_json(self._path(interview_id), updated)
        return updated

    def queue(self) -> list[dict[str, object]]:
        inventory = self.inventory_loader()
        sessions = [
            self.read(p.name)
            for p in sorted((self.workspace / "interviews").glob("interview-*"))
            if p.is_dir()
        ]
        queue = []
        for eid, entry in sorted(inventory.entries.items()):
            interviews = [
                {
                    "id": s.interview_id,
                    "status": s.status,
                    "layer": s.active_layer,
                    "stale": (
                        s.accepted_inventory_hash != inventory.accepted_inventory_hash
                        or s.inventory_revision_hash != inventory.inventory_revision_hash
                    ),
                }
                for s in sessions
                if s.plan.experience_id == eid
            ]
            reason = entry.outcome
            if entry.outcome == "confirmed":
                current = [i for i in interviews if not i["stale"]]
                if not current:
                    reason = "stale-interview-binding" if interviews else "not-audited"
                elif any(i["status"] in {"active", "paused"} for i in current):
                    reason = "interview-in-progress"
                elif any(i["status"] == "reviewing" for i in current):
                    reason = "review-pending"
                else:
                    reason = (
                        "reviewed"
                        if any(i["status"] == "completed" for i in current)
                        else "rejected"
                    )
            queue.append(
                {
                    "experience_id": eid,
                    "inventory_outcome": entry.outcome,
                    "interviews": interviews,
                    "reason": reason,
                }
            )
        return queue
