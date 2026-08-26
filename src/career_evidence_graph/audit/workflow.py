from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from ..domain.fixtures import SealedFixtureRecord, load_sealed_fixture, verify_source_manifest
from ..validation.hashing import canonical_json_bytes, sha256_digest
from .models import ArtifactFact, AuditAction, AuditAnswer, AuditAttribution, AuditConclusion, AuditQuestion, AuditSnapshot, ConclusionEntry
from .store import AuditStore, AuditStorageError


def _fixture(path: Path):
    load_sealed_fixture(path, path.parent)
    return SealedFixtureRecord.model_validate_json(path.read_bytes()).fixture


def inspect_contribution(fixture_path: Path, manifest_path: Path, contribution_id: str) -> tuple[tuple[ArtifactFact, ...], tuple[str, ...]]:
    verify_source_manifest(manifest_path)
    fixture = _fixture(fixture_path)
    contribution = next((x for x in fixture.contributions if x.id == contribution_id), None)
    if contribution is None: raise ValueError("selected Contribution is missing")
    claims = {x.id: x for x in fixture.claims}
    links = [x for x in fixture.claim_evidence_links if x.claim_id in contribution.claim_ids]
    evidence = {x.id: x for x in fixture.evidence}
    if not links: raise ValueError("Contribution has no linked evidence")
    facts = tuple(sorted((ArtifactFact(evidence_id=evidence[l.evidence_id].id, source_locator=l.section_locator, statement=claims[l.claim_id].statement) for l in links), key=lambda x: (x.evidence_id, x.source_locator)))
    limitations = tuple(sorted({limitation for claim_id in contribution.claim_ids for limitation in claims[claim_id].limitations}))
    return facts, limitations


def start_audit(*, workspace: Path, fixture_path: Path, manifest_path: Path, contribution_id: str, audit_id: str | None = None) -> AuditSnapshot:
    facts, limitations = inspect_contribution(fixture_path, manifest_path, contribution_id)
    aid = audit_id or f"audit-{uuid4().hex[:12]}"
    question = AuditQuestion(id="question-implementation", reason="The project record establishes bounded artifact facts, but personal capability remains unverified.", prompt="What design decision did you personally make, and how did you verify it worked?", area="implementation")
    snapshot = AuditSnapshot(audit_id=aid, contribution_id=contribution_id, status="active", questions=(question,), inspected_facts=facts, limitations=limitations)
    AuditStore(workspace).save(snapshot)
    return snapshot


def transition_audit(store: AuditStore, snapshot: AuditSnapshot, action: AuditAction) -> AuditSnapshot:
    questions = list(snapshot.questions); answers = list(snapshot.answers)
    if action.action == "pause": return snapshot.model_copy(update={"status": "paused"})
    if action.action == "resume":
        if snapshot.status != "paused": raise ValueError("audit is not paused")
        return snapshot.model_copy(update={"status": "active"})
    if action.action in {"answer", "skip"}:
        q = next((q for q in questions if q.status == "unanswered"), None)
        if q is None: raise ValueError("no unanswered question")
        questions[questions.index(q)] = q.model_copy(update={"status": "skipped" if action.action == "skip" else "answered"})
        answers.append(AuditAnswer(question_id=q.id, answer=action.answer or "skipped", skipped=action.action == "skip"))
        attribution = snapshot.attribution
        if q.area == "implementation": attribution = AuditAttribution(ownership="unresolved", assistance="unresolved")
        entry = ConclusionEntry(id="entry-implementation", area="implementation", strongest_capability="The user's boundary requires review.", next_higher_not_established="A higher capability is not established.", basis=tuple(f.evidence_id for f in snapshot.inspected_facts) or ("user-answer",), responsibility_boundary="Unresolved pending separate attribution turns.", assistance_boundary="Unresolved pending separate assistance turn.", verification="unresolved")
        conclusion = AuditConclusion(entries=(entry,), original_proposal_hash=sha256_digest(canonical_json_bytes(entry.model_dump(mode="json"))))
        return snapshot.model_copy(update={"questions": tuple(questions), "answers": tuple(answers), "attribution": attribution, "conclusion": conclusion})
    if action.action == "review-entry" and snapshot.conclusion:
        entries = list(snapshot.conclusion.entries); entry = next(x for x in entries if x.id == action.entry_id)
        entries[entries.index(entry)] = entry.model_copy(update={"review": {"confirm": "confirmed", "edit": "edited", "reject": "rejected"}[action.decision or "reject"], "correction": action.correction})
        return snapshot.model_copy(update={"conclusion": snapshot.conclusion.model_copy(update={"entries": tuple(entries)})})
    if action.action == "review-conclusion" and snapshot.conclusion:
        return snapshot.model_copy(update={"conclusion": snapshot.conclusion.model_copy(update={"whole_review": "confirmed" if action.decision == "confirm" else "rejected", "review_reason": action.reason})})
    raise ValueError("invalid audit transition")
