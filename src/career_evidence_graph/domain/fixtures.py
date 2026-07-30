"""Pinned, document-only STOA fixture source boundary.

This module deliberately treats repository documents as untrusted proposals.
It never reads a repository working tree and never lets documentary content
establish a person's responsibility or capability.
"""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from pydantic import Field, ValidationError, model_validator

from ..validation.hashing import canonical_json_bytes, sha256_digest
from ..validation.models import CorrectionRecord, StrictModel
from ..validation.replay import replay_recorded_response
from ..validation.store import FormalRunStorageError, FormalRunStore, load_charter
from .invariants import validate_career_evidence_fixture
from .models import (
    COMMIT_PATTERN,
    SHA256_PATTERN,
    CareerEvidenceFixture,
    ClaimEvidenceLink,
    Contribution,
    ContributionClaim,
    Evidence,
    EvidenceKind,
    Experience,
    ProofLimit,
    Skill,
)


class SourceScopeError(ValueError):
    """A source is outside the fixed document-only STOA boundary."""


class StoaRepositoryPin(StrictModel):
    schema_version: Literal["stoa-repository-pin/v1"] = "stoa-repository-pin/v1"
    id: Literal["stoa-backend", "stoa-frontend", "stoa-infra", "stoa-docs"]
    repository_path: str = Field(min_length=1)
    pinned_commit: str = Field(pattern=COMMIT_PATTERN)


class PermittedDocument(StrictModel):
    schema_version: Literal["permitted-document/v1"] = "permitted-document/v1"
    id: str = Field(pattern=r"^src-stoa-[a-z0-9-]+$")
    repository_id: Literal["stoa-backend", "stoa-frontend", "stoa-infra", "stoa-docs"]
    pinned_commit: str = Field(pattern=COMMIT_PATTERN)
    tracked_path: str = Field(min_length=1)
    source_kind: EvidenceKind
    proof_limit: ProofLimit
    section_locator_policy: Literal["markdown-heading-or-document"]
    content_sha256: str = Field(pattern=SHA256_PATTERN)
    personal_claim_proof: Literal["none"]

    @model_validator(mode="after")
    def validate_proof_limit(self) -> PermittedDocument:
        expected = {
            "plan": "intent_or_assignment",
            "handoff": "recorded_delivery",
            "acceptance_record": "recorded_delivery",
            "audit": "observed_state_defects_limitations",
            "user_confirmation": "personal_responsibility_and_claimed_capability",
        }[self.source_kind]
        if self.proof_limit != expected or self.personal_claim_proof != "none":
            raise ValueError("document proof role must remain non-personal and bounded")
        return self


class SourceManifest(StrictModel):
    schema_version: Literal["stoa-source-manifest/v1"] = "stoa-source-manifest/v1"
    repositories: tuple[StoaRepositoryPin, ...] = Field(min_length=4, max_length=4)
    documents: tuple[PermittedDocument, ...] = Field(min_length=10, max_length=10)

    @model_validator(mode="after")
    def validate_unique_entries(self) -> SourceManifest:
        if len({repository.id for repository in self.repositories}) != 4:
            raise ValueError("repository IDs must be unique")
        if len({document.id for document in self.documents}) != 10:
            raise ValueError("document IDs must be unique")
        if (
            len({(document.repository_id, document.tracked_path) for document in self.documents})
            != 10
        ):
            raise ValueError("document repository/path pairs must be unique")
        return self


class SourceManifestVerification(StrictModel):
    schema_version: Literal["source-manifest-verification/v1"] = "source-manifest-verification/v1"
    valid: Literal[True] = True
    repository_count: int = Field(ge=0)
    document_count: int = Field(ge=0)
    manifest_hash: str = Field(pattern=SHA256_PATTERN)


class CandidateContribution(StrictModel):
    schema_version: Literal["candidate-contribution/v1"] = "candidate-contribution/v1"
    id: str = Field(pattern=r"^contrib-stoa-[a-z0-9-]+$")
    outcome_group_id: str = Field(pattern=r"^outcome-[a-z0-9-]+$")
    summary: str = Field(min_length=1)
    claim_ids: tuple[str, ...] = Field(min_length=1)
    completion_status: Literal["delivered", "partial", "unresolved"]
    limitations: tuple[str, ...] = Field(min_length=1)


class CandidateFact(StrictModel):
    schema_version: Literal["candidate-fact/v1"] = "candidate-fact/v1"
    id: str = Field(pattern=r"^claim-stoa-[a-z0-9-]+$")
    contribution_id: str = Field(pattern=r"^contrib-stoa-[a-z0-9-]+$")
    statement: str = Field(min_length=1)
    documentary_status: Literal["document-derived-non-personal"]
    responsibility: Literal["unconfirmed"]
    assistance: Literal["unconfirmed"]
    completion_status: Literal["delivered", "partial", "unresolved"]
    evidence_ids: tuple[str, ...] = Field(min_length=1)
    limitations: tuple[str, ...] = Field(min_length=1)
    conflicting_source_entry_ids: tuple[str, ...] = ()


class CandidateEvidence(StrictModel):
    schema_version: Literal["candidate-evidence/v1"] = "candidate-evidence/v1"
    id: str = Field(pattern=r"^evid-stoa-[a-z0-9-]+$")
    source_entry_id: str = Field(pattern=r"^src-stoa-[a-z0-9-]+$")
    section_locator: str = Field(min_length=1)
    proof_limit: ProofLimit


class SourceSectionDisposition(StrictModel):
    schema_version: Literal["source-section-disposition/v1"] = "source-section-disposition/v1"
    source_entry_id: str = Field(pattern=r"^src-stoa-[a-z0-9-]+$")
    section_locator: str = Field(min_length=1)
    disposition: Literal["used", "background-only", "conflict", "excluded-with-reason"]
    proof_limit_reason: str = Field(min_length=1)
    has_assessment_lineage: Literal[False] = False


class BackgroundContext(StrictModel):
    schema_version: Literal["background-context/v1"] = "background-context/v1"
    source_entry_id: str = Field(pattern=r"^src-stoa-[a-z0-9-]+$")
    description: str = Field(min_length=1)
    background_only: Literal[True] = True


class CandidateLedger(StrictModel):
    schema_version: Literal["stoa-candidate-ledger/v1"] = "stoa-candidate-ledger/v1"
    experience_id: Literal["exp-stoa"] = "exp-stoa"
    experience_type: Literal["project"] = "project"
    title: str = Field(min_length=1)
    documentary_status: Literal["document-derived-non-personal"]
    contributions: tuple[CandidateContribution, ...] = Field(min_length=1)
    claims: tuple[CandidateFact, ...] = Field(min_length=1)
    evidence: tuple[CandidateEvidence, ...] = Field(min_length=1)
    source_section_dispositions: tuple[SourceSectionDisposition, ...] = Field(min_length=1)
    background_context: tuple[BackgroundContext, ...] = ()

    @model_validator(mode="after")
    def validate_candidate_lineage(self) -> CandidateLedger:
        contribution_ids = {item.id for item in self.contributions}
        claim_ids = {item.id for item in self.claims}
        evidence_ids = {item.id for item in self.evidence}
        if len(contribution_ids) != len(self.contributions) or len(claim_ids) != len(self.claims):
            raise ValueError("candidate contribution and claim IDs must be unique")
        if len(evidence_ids) != len(self.evidence):
            raise ValueError("candidate Evidence IDs must be unique")
        if any(claim.contribution_id not in contribution_ids for claim in self.claims):
            raise ValueError("claim references an unknown contribution")
        if (
            any(set(contribution.claim_ids) - claim_ids for contribution in self.contributions)
            or {claim.contribution_id for claim in self.claims} != contribution_ids
        ):
            raise ValueError("contribution claim lineage is incomplete")
        if any(set(claim.evidence_ids) - evidence_ids for claim in self.claims):
            raise ValueError("claim references unknown Evidence")
        evidence_identity = {(item.source_entry_id, item.section_locator) for item in self.evidence}
        if len(evidence_identity) != len(self.evidence):
            raise ValueError("duplicate Evidence source identity")
        background_ids = {item.source_entry_id for item in self.background_context}
        evidence_source_ids = {evidence.source_entry_id for evidence in self.evidence}
        if evidence_source_ids & background_ids:
            raise ValueError("planned-only background cannot create Evidence lineage")
        return self


class ReviewDecision(StrictModel):
    schema_version: Literal["review-decision/v1"] = "review-decision/v1"
    status: Literal["pending", "accepted", "edited", "rejected", "unresolved"]
    reviewer_note: str | None = None


class CandidateReviewItem(StrictModel):
    schema_version: Literal["candidate-review-item/v1"] = "candidate-review-item/v1"
    candidate_id: str = Field(pattern=r"^claim-stoa-[a-z0-9-]+$")
    fact: ReviewDecision
    attribution_assistance: ReviewDecision
    evidence_links: ReviewDecision
    completion: ReviewDecision
    limitations_conflicts: ReviewDecision
    fixture_score_range: ReviewDecision


class CandidateReviewRecord(StrictModel):
    schema_version: Literal["stoa-candidate-review/v1"] = "stoa-candidate-review/v1"
    candidate_ledger_hash: str = Field(pattern=SHA256_PATTERN)
    items: tuple[CandidateReviewItem, ...] = Field(min_length=1)
    reviewer_id: str | None = None
    checkpoint_summary_hash: str | None = Field(default=None, pattern=SHA256_PATTERN)
    reviewed_at: datetime | None = None
    corrections: tuple[CorrectionRecord, ...] = ()


class ReviewStatus(StrictModel):
    schema_version: Literal["stoa-review-status/v1"] = "stoa-review-status/v1"
    sealable: bool
    pending_ids_by_group: dict[str, tuple[str, ...]]


class SealedFixtureRecord(StrictModel):
    """A known-good envelope tied to one verified FormalRunStore bundle."""

    schema_version: Literal["sealed-stoa-known-good/v1"] = "sealed-stoa-known-good/v1"
    formal_run_id: str = Field(min_length=1)
    confirmed_result_hash: str = Field(pattern=SHA256_PATTERN)
    source_manifest_hash: str = Field(pattern=SHA256_PATTERN)
    review_hash: str = Field(pattern=SHA256_PATTERN)
    checkpoint_summary_hash: str = Field(pattern=SHA256_PATTERN)
    fixture: CareerEvidenceFixture


_CONFIRMED_REVIEWER_ID = "zhdeng"
_CONFIRMED_REVIEWED_AT = datetime(2026, 7, 30, tzinfo=UTC)
_FIXTURE_NOTICE = (
    "This sealed STOA fixture records human-confirmed fixture test expectations only. "
    "It makes no calibration, aggregation, confidence-admission, JD, resume, product, "
    "application, interview, hiring, or effectiveness conclusion."
)


_REPOSITORIES = {
    "stoa-backend": (
        "/Users/zhdeng/stoa-backend",
        "84e93dae35dfde2c2e07fac6faf714b2d61c8377",
    ),
    "stoa-frontend": (
        "/Users/zhdeng/stoa-frontend",
        "42955a9ed38cfca868febffa752459ec27a88a30",
    ),
    "stoa-infra": (
        "/Users/zhdeng/stoa-infra",
        "6d545ad8cae8d2fe67087f298d9d5fc7cc29b3f6",
    ),
    "stoa-docs": (
        "/Users/zhdeng/stoa-docs",
        "53c91971572a52bf4bfdc68aebd8393f3080a76d",
    ),
}
_DOCUMENT_PATHS = {
    ("stoa-backend", "docs/audit/full-project-audit.md"),
    ("stoa-backend", "docs/build-week-2026/BUILD-WEEK-EVIDENCE.md"),
    ("stoa-backend", "docs/build-week-2026/OWNER-HANDOFF.zh-CN.md"),
    ("stoa-frontend", "docs/qa/development-artifact-audit.md"),
    ("stoa-frontend", "docs/production/production-readiness.md"),
    ("stoa-frontend", "docs/release/next-stage-backlog.md"),
    ("stoa-docs", "PLAN.md"),
    ("stoa-docs", "ADR.md"),
    ("stoa-docs", "DEPLOYMENT.md"),
    ("stoa-infra", "README.md"),
}


def _source_scope_error(detail: str) -> SourceScopeError:
    return SourceScopeError(f"source-scope: {detail}")


def _validate_manifest_scope(manifest: SourceManifest) -> None:
    observed_repositories = {
        repository.id: (repository.repository_path, repository.pinned_commit)
        for repository in manifest.repositories
    }
    if observed_repositories != _REPOSITORIES:
        raise _source_scope_error("repository pins or local paths differ from the fixed inventory")
    observed_documents = {
        (document.repository_id, document.tracked_path) for document in manifest.documents
    }
    if observed_documents != _DOCUMENT_PATHS:
        raise _source_scope_error("document paths differ from the fixed inventory")
    for document in manifest.documents:
        if (
            document.tracked_path.startswith("/")
            or ".." in Path(document.tracked_path).parts
            or document.tracked_path.endswith((".py", ".ts", ".tsx", ".js", ".json", ".env"))
        ):
            raise _source_scope_error("unsafe or implementation path")
        if document.pinned_commit != _REPOSITORIES[document.repository_id][1]:
            raise _source_scope_error("document pin differs from repository pin")


def _read_pinned_git_object(repository_path: str, commit: str, tracked_path: str) -> bytes:
    try:
        result = subprocess.run(
            ["git", "-C", repository_path, "show", f"{commit}:{tracked_path}"],
            check=False,
            capture_output=True,
            env={"PATH": os.defpath, "LC_ALL": "C", "LANG": "C"},
        )
    except OSError as exc:
        raise _source_scope_error(f"pinned Git-object read failed: {exc}") from exc
    if result.returncode != 0:
        raise _source_scope_error("pinned Git object is missing or unreadable")
    return result.stdout


def verify_source_manifest(path: Path) -> SourceManifestVerification:
    """Verify every permitted document by its immutable Git object bytes only."""
    try:
        manifest = SourceManifest.model_validate_json(path.read_bytes())
    except (OSError, ValidationError) as exc:
        raise _source_scope_error(f"manifest is invalid: {exc}") from exc
    _validate_manifest_scope(manifest)
    for document in manifest.documents:
        repository_path, expected_commit = _REPOSITORIES[document.repository_id]
        if document.pinned_commit != expected_commit:
            raise _source_scope_error("document pin differs from fixed commit")
        object_bytes = _read_pinned_git_object(
            repository_path, document.pinned_commit, document.tracked_path
        )
        if sha256_digest(object_bytes) != document.content_sha256:
            raise _source_scope_error("pinned document content hash mismatch")
    return SourceManifestVerification(
        repository_count=len(manifest.repositories),
        document_count=len(manifest.documents),
        manifest_hash=sha256_digest(canonical_json_bytes(manifest)),
    )


def _candidate_ledger_hash(ledger: CandidateLedger) -> str:
    return sha256_digest(canonical_json_bytes(ledger))


def load_candidate_packet(
    candidates_path: Path, review_path: Path
) -> tuple[CandidateLedger, CandidateReviewRecord]:
    """Load an unsealed candidate packet after verifying its source boundary."""
    verify_source_manifest(candidates_path.with_name("source-manifest.json"))
    try:
        candidates = CandidateLedger.model_validate_json(candidates_path.read_bytes())
        review = CandidateReviewRecord.model_validate_json(review_path.read_bytes())
    except (OSError, ValidationError) as exc:
        raise _source_scope_error(f"candidate packet is invalid: {exc}") from exc

    manifest = SourceManifest.model_validate_json(
        candidates_path.with_name("source-manifest.json").read_bytes()
    )
    manifest_by_id = {document.id: document for document in manifest.documents}
    disposition_ids = {item.source_entry_id for item in candidates.source_section_dispositions}
    if len(disposition_ids) != len(
        candidates.source_section_dispositions
    ) or disposition_ids != set(manifest_by_id):
        raise _source_scope_error("candidate source coverage is incomplete or duplicated")
    for evidence in candidates.evidence:
        source = manifest_by_id.get(evidence.source_entry_id)
        if source is None or source.proof_limit != evidence.proof_limit:
            raise _source_scope_error("Evidence source or proof limit is not permitted")
    planned_source_ids = {
        document.id for document in manifest.documents if document.source_kind == "plan"
    }
    background_ids = {item.source_entry_id for item in candidates.background_context}
    if not planned_source_ids <= background_ids:
        raise _source_scope_error("planned-only sources must remain background-only")
    if any(evidence.source_entry_id in planned_source_ids for evidence in candidates.evidence):
        raise _source_scope_error("planned-only source cannot enter assessment lineage")
    if review.candidate_ledger_hash != _candidate_ledger_hash(candidates):
        raise _source_scope_error("review is not bound to this candidate ledger")
    candidate_ids = {claim.id for claim in candidates.claims}
    review_ids = {item.candidate_id for item in review.items}
    if len(review_ids) != len(review.items) or review_ids != candidate_ids:
        raise _source_scope_error("review must include one item per candidate claim")
    return candidates, review


_REVIEW_GROUPS = (
    "fact",
    "attribution_assistance",
    "evidence_links",
    "completion",
    "limitations_conflicts",
    "fixture_score_range",
)


def evaluate_review_status(
    candidates: CandidateLedger, review: CandidateReviewRecord
) -> ReviewStatus:
    """Return deterministic pending IDs without treating test expectations as mastery."""
    candidate_ids = {claim.id for claim in candidates.claims}
    if {item.candidate_id for item in review.items} != candidate_ids:
        raise _source_scope_error("review candidate IDs do not match the candidate ledger")
    pending = {
        group: tuple(
            item.candidate_id for item in review.items if getattr(item, group).status == "pending"
        )
        for group in _REVIEW_GROUPS
    }
    missing_authority = (
        review.reviewer_id is None
        or review.checkpoint_summary_hash is None
        or review.reviewed_at is None
    )
    corrections_by_id = {item.correction_id for item in review.corrections}
    required_corrections = {
        f"correction-{item.candidate_id}-attribution-assistance" for item in review.items
    }
    if review.reviewer_id is not None and not required_corrections <= corrections_by_id:
        missing_authority = True
    return ReviewStatus(
        sealable=not any(pending.values()) and not missing_authority,
        pending_ids_by_group=pending,
    )


def _confirmed_decisions(candidates: CandidateLedger) -> tuple[CandidateReviewItem, ...]:
    """Return only the six explicit decisions recorded in the Plan 02-04 checkpoint."""
    candidates_by_id = {claim.id: claim for claim in candidates.claims}
    expected_ids = {
        "claim-stoa-authorization-boundary",
        "claim-stoa-content-privacy-integrity",
        "claim-stoa-verifiable-delivery-evidence",
        "claim-stoa-frontend-readiness-boundary",
    }
    if set(candidates_by_id) != expected_ids:
        raise _source_scope_error("checkpoint response does not cover the exact candidate set")
    return tuple(
        CandidateReviewItem(
            candidate_id=candidate_id,
            fact=ReviewDecision(status="accepted"),
            attribution_assistance=ReviewDecision(status="edited"),
            evidence_links=ReviewDecision(status="accepted"),
            completion=ReviewDecision(status="accepted"),
            limitations_conflicts=ReviewDecision(status="accepted"),
            fixture_score_range=ReviewDecision(
                status="unresolved",
                reviewer_note=(
                    "No numeric range; fixture-only test value, not capability calibration."
                ),
            ),
        )
        for candidate_id in sorted(candidates_by_id)
    )


def _review_corrections(candidates: CandidateLedger) -> tuple[CorrectionRecord, ...]:
    proposal = candidates.model_dump(mode="json")
    proposal_hash = sha256_digest(canonical_json_bytes(proposal))
    return tuple(
        CorrectionRecord(
            schema_version="correction-record/v1",
            correction_id=f"correction-{claim.id}-attribution-assistance",
            created_at=_CONFIRMED_REVIEWED_AT,
            original_proposal=proposal,
            original_proposal_hash=proposal_hash,
            correction={
                "candidate_id": claim.id,
                "group": "attribution_assistance",
                "responsibility": "user",
                "assistance": "codex_assisted",
            },
            reviewer_id=_CONFIRMED_REVIEWER_ID,
            reason=(
                "User stated they personally and independently completed it with Codex "
                "assistance; this ownership and assistance does not establish mastery."
            ),
        )
        for claim in sorted(candidates.claims, key=lambda value: value.id)
    )


def _reviewed_fixture(candidates: CandidateLedger) -> CareerEvidenceFixture:
    """Build the confirmed, contribution-grounded fixture without adding mastery values."""
    manifest = SourceManifest.model_validate_json(
        Path("validation/fixtures/stoa/v1/source-manifest.json").read_bytes()
    )
    documents = {item.id: item for item in manifest.documents}
    evidence = tuple(
        Evidence(
            id=item.id,
            kind=documents[item.source_entry_id].source_kind,
            proof_limit=item.proof_limit,
            repository=documents[item.source_entry_id].repository_id,
            pinned_commit=documents[item.source_entry_id].pinned_commit,
            tracked_path=documents[item.source_entry_id].tracked_path,
            section_locator=item.section_locator,
            content_hash=documents[item.source_entry_id].content_sha256,
        )
        for item in candidates.evidence
    )
    fixture = CareerEvidenceFixture(
        schema_version="career-evidence-fixture/v1",
        fixture_notice=_FIXTURE_NOTICE,
        experiences=(
            Experience(
                id=candidates.experience_id,
                experience_type=candidates.experience_type,
                title="STOA human-reviewed fixture experience",
                contribution_ids=tuple(item.id for item in candidates.contributions),
            ),
        ),
        contributions=tuple(
            Contribution(
                id=item.id,
                experience_id=candidates.experience_id,
                summary=item.summary,
                claim_ids=item.claim_ids,
            )
            for item in candidates.contributions
        ),
        claims=tuple(
            ContributionClaim(
                id=item.id,
                contribution_id=item.contribution_id,
                statement=item.statement,
                responsibility="user",
                assistance="codex_assisted",
                confirmation_status="confirmed",
                completion_status=item.completion_status,
                limitations=item.limitations,
            )
            for item in candidates.claims
        ),
        evidence=evidence,
        claim_evidence_links=tuple(
            ClaimEvidenceLink(
                claim_id=claim.id,
                evidence_id=evidence_id,
                section_locator=next(
                    evidence.section_locator
                    for evidence in candidates.evidence
                    if evidence.id == evidence_id
                ),
            )
            for claim in candidates.claims
            for evidence_id in claim.evidence_ids
        ),
        skills=(Skill(id="skill-stoa-reviewed-fixture", name="STOA reviewed fixture"),),
    )
    validate_career_evidence_fixture(fixture)
    return fixture


def materialize_review_decisions(
    candidates: CandidateLedger,
    checkpoint_decisions: CandidateReviewRecord,
    checkpoint_summary_bytes: bytes,
) -> tuple[CandidateReviewRecord, CareerEvidenceFixture]:
    """Materialize exactly the confirmed six-group checkpoint response.

    The pending candidate packet is intentionally accepted only when it is bound to the
    same ledger.  No absent checkpoint group receives a default or favorable inference.
    """
    if checkpoint_decisions.candidate_ledger_hash != _candidate_ledger_hash(candidates):
        raise _source_scope_error("checkpoint response is not bound to the candidate ledger")
    if b"review-confirmed: zhdeng" not in checkpoint_summary_bytes:
        raise _source_scope_error(
            "checkpoint confirmation is absent or belongs to another reviewer"
        )
    review = CandidateReviewRecord(
        candidate_ledger_hash=_candidate_ledger_hash(candidates),
        items=_confirmed_decisions(candidates),
        reviewer_id=_CONFIRMED_REVIEWER_ID,
        checkpoint_summary_hash=sha256_digest(checkpoint_summary_bytes),
        reviewed_at=_CONFIRMED_REVIEWED_AT,
        corrections=_review_corrections(candidates),
    )
    if not evaluate_review_status(candidates, review).sealable:
        raise _source_scope_error("complete checkpoint response is unexpectedly unsealable")
    return review, _reviewed_fixture(candidates)


def write_materialized_review(path: Path, review: CandidateReviewRecord) -> None:
    """Atomically replace only the initial all-pending review packet.

    A materialized review is immutable input for sealing.  This narrow replacement
    exists solely to turn the checked-in unreviewed packet into the recorded human
    decision; a second materialization fails closed rather than overwriting review truth.
    """
    try:
        existing = CandidateReviewRecord.model_validate_json(path.read_bytes())
    except (OSError, ValidationError) as exc:
        raise _source_scope_error(f"existing review is invalid: {exc}") from exc
    if existing.reviewer_id is not None or any(
        getattr(item, group).status != "pending"
        for item in existing.items
        for group in _REVIEW_GROUPS
    ):
        raise _source_scope_error("recorded review already exists and cannot be overwritten")
    temporary = path.with_name(f".{path.name}.tmp")
    try:
        temporary.write_bytes(canonical_json_bytes(review.model_dump(mode="json")))
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def _validation_root(manifest_path: Path) -> Path:
    """Locate the project root from validation/fixtures/stoa/v1/source-manifest.json."""
    try:
        validation_dir = manifest_path.resolve().parents[3]
    except IndexError as exc:
        raise _source_scope_error("source manifest has no validation-root parent") from exc
    if validation_dir.name != "validation":
        raise _source_scope_error("source manifest must live below validation/fixtures/stoa/v1")
    return validation_dir.parent


def _publish_known_good(path: Path, value: SealedFixtureRecord) -> None:
    """Publish a canonical file once; permit only exact idempotent recovery."""
    expected = canonical_json_bytes(value.model_dump(mode="json"))
    if path.exists():
        try:
            observed = canonical_json_bytes(json.loads(path.read_text(encoding="utf-8")))
        except (OSError, json.JSONDecodeError) as exc:
            raise FormalRunStorageError("known-good output is unreadable or non-canonical") from exc
        if observed != expected:
            raise FormalRunStorageError("known-good output already exists with divergent bytes")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.")
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(expected + b"\n")
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.link(temporary, path)
        except FileExistsError:
            observed = canonical_json_bytes(json.loads(path.read_text(encoding="utf-8")))
            if observed != expected:
                raise FormalRunStorageError(
                    "known-good output already exists with divergent bytes"
                ) from None
        finally:
            temporary.unlink(missing_ok=True)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise


def seal_reviewed_fixture(
    *,
    workspace: Path,
    run_id: str,
    manifest_path: Path,
    candidates: CandidateLedger,
    review: CandidateReviewRecord,
    checkpoint_summary_bytes: bytes,
    output_path: Path,
):
    """Seal a complete human review through a verified, provider-free formal run."""
    source_verification = verify_source_manifest(manifest_path)
    if review.checkpoint_summary_hash != sha256_digest(checkpoint_summary_bytes):
        raise _source_scope_error("review checkpoint summary hash has drifted")
    if review.reviewer_id != _CONFIRMED_REVIEWER_ID:
        raise _source_scope_error("known-good requires the confirmed human reviewer")
    if not evaluate_review_status(candidates, review).sealable:
        raise _source_scope_error("incomplete review cannot be sealed")
    fixture = _reviewed_fixture(candidates)
    fixture_result = validate_career_evidence_fixture(fixture)
    root = _validation_root(manifest_path)
    charter = load_charter(root / "validation/charter/v1.json")
    proposal = candidates.model_dump(mode="json")
    confirmed_result = fixture.model_dump(mode="json")
    store = FormalRunStore(workspace)
    run_path = store.runs_root / run_id
    if run_path.exists():
        stored_manifest = store.verify(run_id)
        if store.payload(run_id, "confirmed_result.json") != confirmed_result:
            raise FormalRunStorageError("existing formal run does not match reviewed fixture")
        if not replay_recorded_response(store, run_id).matched:
            raise FormalRunStorageError("existing formal run cannot replay exactly")
    else:
        stored_manifest = store.create(
            run_id=run_id,
            charter=charter,
            raw_response={"result": confirmed_result},
            proposal=proposal,
            confirmed_result=confirmed_result,
            lineage_inputs={
                "fixture": {"hash": fixture_result.fixture_hash},
                "artifacts": {"source_manifest_hash": source_verification.manifest_hash},
                "prompt": {"kind": "none"},
                "model": {"kind": "none"},
                "configuration": {"mode": "offline"},
                "policy": {"fixture_notice": _FIXTURE_NOTICE},
                "reviewer": {
                    "reviewer_id": review.reviewer_id,
                    "checkpoint_summary_hash": review.checkpoint_summary_hash,
                },
            },
            corrections=list(review.corrections),
            limitations=[
                "Fixture score/range values remain unresolved test expectations, not mastery.",
                (
                    "Partial delivery and source conflicts remain visible; "
                    "no effectiveness conclusion follows."
                ),
                _FIXTURE_NOTICE,
            ],
        )
        store.verify(run_id)
        if not replay_recorded_response(store, run_id).matched:
            raise FormalRunStorageError("new formal run cannot replay exactly")
    record = SealedFixtureRecord(
        formal_run_id=stored_manifest.run_id,
        confirmed_result_hash=fixture_result.fixture_hash,
        source_manifest_hash=source_verification.manifest_hash,
        review_hash=sha256_digest(canonical_json_bytes(review)),
        checkpoint_summary_hash=review.checkpoint_summary_hash,
        fixture=fixture,
    )
    _publish_known_good(output_path, record)
    return fixture_result


def load_sealed_fixture(path: Path, workspace: Path):
    """Load known-good only when it still matches its verified immutable bundle."""
    try:
        sealed = SealedFixtureRecord.model_validate_json(path.read_bytes())
    except (OSError, ValidationError) as exc:
        raise FormalRunStorageError("known-good fixture is invalid") from exc
    store = FormalRunStore(workspace)
    store.verify(sealed.formal_run_id)
    confirmed = store.payload(sealed.formal_run_id, "confirmed_result.json")
    if canonical_json_bytes(confirmed) != canonical_json_bytes(sealed.fixture):
        raise FormalRunStorageError("known-good fixture differs from formal confirmed result")
    result = validate_career_evidence_fixture(sealed.fixture)
    if result.fixture_hash != sealed.confirmed_result_hash:
        raise FormalRunStorageError("known-good confirmed-result hash is invalid")
    if not replay_recorded_response(store, sealed.formal_run_id).matched:
        raise FormalRunStorageError("known-good formal run does not replay exactly")
    return result
