"""Pinned, document-only STOA fixture source boundary.

This module deliberately treats repository documents as untrusted proposals.
It never reads a repository working tree and never lets documentary content
establish a person's responsibility or capability.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Literal

from pydantic import Field, ValidationError, model_validator

from ..validation.hashing import canonical_json_bytes, sha256_digest
from ..validation.models import StrictModel
from .models import COMMIT_PATTERN, SHA256_PATTERN, EvidenceKind, ProofLimit


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


class ReviewStatus(StrictModel):
    schema_version: Literal["stoa-review-status/v1"] = "stoa-review-status/v1"
    sealable: bool
    pending_ids_by_group: dict[str, tuple[str, ...]]


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
    return ReviewStatus(sealable=not any(pending.values()), pending_ids_by_group=pending)
