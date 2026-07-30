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
