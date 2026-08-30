"""Candidate-only, immutable custody for synthetic career-source inputs."""

from __future__ import annotations

import json
import os
import re
import subprocess
import tempfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from .domain.models import (
    CareerSourceCapture,
    CareerSourceTransformation,
    CareerSourceUniverse,
    DeclarationBoundCurrentCapturePointer,
    DerivedOutputManifest,
    WorkspaceMigrationReceipt,
    WorkspaceMigrationRequest,
)
from .validation.hashing import canonical_json_bytes, sha256_digest
from .validation.store import (
    FormalRunStorageError,
    atomic_write_canonical_json,
    create_only_canonical_bundle,
)
from .workspace import PrivateWorkspace, PrivateWorkspaceError

_SAFE_ID = re.compile(r"^[a-z][a-z0-9]*(?:[._-][a-z0-9]+)*$")
_UNSAFE_CODEPOINTS = frozenset({"\u200b", "\u200c", "\u200d", "\u2060", "\ufeff"})
_MAX_SOURCE_BYTES = 262144
_GIT_OID_LENGTHS = {"sha1": 40, "sha256": 64}
_CUSTODY_RETENTION_REF = "refs/career-evidence/custody"
_SEMANTIC_NAMESPACES = (
    ("declaration-manifests", re.compile(r"declarations/[a-z][a-z0-9._-]*/manifest\.json")),
    ("declaration-current", re.compile(r"declarations/current\.json")),
    ("capture-manifests", re.compile(r"captures/[a-z][a-z0-9._-]*/manifest\.json")),
    ("current-captures", re.compile(r"current-captures/[a-z][a-z0-9._-]*\.json")),
    ("transformation-manifests", re.compile(r"transformations/[a-z][a-z0-9._-]*/manifest\.json")),
    ("migration-receipts", re.compile(r"migration-receipts/[a-z][a-z0-9._-]*/manifest\.json")),
    ("derived-outputs", re.compile(r"derived-outputs/[0-9a-f]{64}/manifest\.json")),
)


@dataclass(frozen=True)
class _MigrationPreflight:
    """Verified request data kept private until an explicit later finalizer."""

    request: WorkspaceMigrationRequest
    baseline_blobs: dict[str, bytes]
    captures: dict[str, CareerSourceCapture]
    transformations: dict[str, CareerSourceTransformation]
    output_bytes: dict[str, bytes]


class CareerSourceError(ValueError):
    """A career-source operation failed without disclosing private data."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


class CareerSourceStore:
    """The only career-source custody store; it cannot create capability authority."""

    def __init__(self, workspace: Path) -> None:
        try:
            self.workspace = PrivateWorkspace(workspace)
        except PrivateWorkspaceError as exc:
            raise CareerSourceError(exc.args[0]) from exc
        self.root = self.workspace.root / ".career-evidence" / "sources"
        self.raw_root = self.workspace.root / ".career-evidence" / "raw"

    @staticmethod
    def _safe_id(value: str) -> str:
        if not _SAFE_ID.fullmatch(value):
            raise CareerSourceError("career-source-id-invalid")
        return value

    def _ensure_root(self) -> None:
        for path in (self.root.parent, self.root, self.raw_root):
            if path.is_symlink():
                raise CareerSourceError("career-source-private-root-unsafe")
            path.mkdir(exist_ok=True)
            if path.resolve() != path:
                raise CareerSourceError("career-source-private-root-unsafe")

    def declare(self, declaration: dict[str, Any]) -> dict[str, Any]:
        try:
            universe = CareerSourceUniverse.model_validate(declaration)
            revision_id = self._safe_id(universe.revision_id)
        except (TypeError, ValueError) as exc:
            raise CareerSourceError("career-source-declaration-invalid") from exc
        self._ensure_root()
        declarations = self.root / "declarations"
        declarations.mkdir(exist_ok=True)
        predecessor = universe.predecessor_revision_id
        if predecessor is not None and not (declarations / predecessor / "manifest.json").is_file():
            raise CareerSourceError("career-source-declaration-predecessor-missing")
        try:
            create_only_canonical_bundle(
                declarations,
                revision_id,
                {"manifest.json": json.loads(universe.canonical_bytes())},
            )
            atomic_write_canonical_json(
                declarations / "current.json", json.loads(universe.canonical_bytes())
            )
        except FormalRunStorageError as exc:
            raise CareerSourceError("career-source-declaration-already-exists") from exc
        return {
            "authority": "candidate-only",
            "created_skill_count": 0,
            "unavailable_source_count": sum(
                source.availability.value != "available" for source in universe.sources
            ),
        }

    def _capture_path(self, capture_id: str) -> Path:
        return self._semantic_path(f"captures/{self._safe_id(capture_id)}/manifest.json").parent

    def _raw_path(self, content_hash: str) -> Path:
        digest = content_hash.removeprefix("sha256:")
        if not re.fullmatch(r"[0-9a-f]{64}", digest):
            raise CareerSourceError("career-source-capture-invalid")
        return self.raw_root / digest

    def _declaration_binding(self) -> tuple[CareerSourceUniverse, str]:
        try:
            current_path = self._semantic_path("declarations/current.json")
            current = CareerSourceUniverse.model_validate_json(current_path.read_bytes())
            revision = self._read_declaration(current.revision_id)
            if canonical_json_bytes(revision) != canonical_json_bytes(current):
                raise ValueError
        except (CareerSourceError, OSError, ValidationError, ValueError) as exc:
            raise CareerSourceError("career-source-declaration-invalid") from exc
        return revision, sha256_digest(revision.canonical_bytes())

    def _read_capture(self, capture_id: str) -> CareerSourceCapture:
        bundle = self._capture_path(capture_id)
        manifest = bundle / "manifest.json"
        try:
            if bundle.is_symlink() or not bundle.is_dir():
                raise ValueError
            if {path.name for path in bundle.iterdir()} != {"manifest.json"}:
                raise ValueError
            value = json.loads(
                self._semantic_path(f"captures/{capture_id}/manifest.json").read_text(
                    encoding="utf-8"
                )
            )
            if value.get("schema_version") == "career-source-capture/v1":
                raise CareerSourceError("career-source-capture-migration-required")
            capture = CareerSourceCapture.model_validate(value)
        except CareerSourceError:
            raise
        except (OSError, json.JSONDecodeError, ValidationError) as exc:
            raise CareerSourceError("career-source-capture-invalid") from exc
        if manifest.is_symlink() or capture.capture_id != capture_id:
            raise CareerSourceError("career-source-capture-lineage-invalid")
        return capture

    def _verify_capture(self, capture_id: str, *, ancestry: frozenset[str]) -> CareerSourceCapture:
        if capture_id in ancestry:
            raise CareerSourceError("career-source-capture-lineage-cycle")
        capture = self._read_capture(capture_id)
        raw_path = self._raw_path(capture.content_hash)
        if raw_path.is_symlink() or not raw_path.is_file():
            raise CareerSourceError("career-source-capture-raw-invalid")
        if sha256_digest(raw_path.read_bytes()) != capture.content_hash:
            raise CareerSourceError("career-source-capture-raw-invalid")
        try:
            universe = self._read_declaration(capture.declaration_revision_id)
            datetime.fromisoformat(capture.acquired_at)
        except (CareerSourceError, OSError, ValueError, ValidationError) as exc:
            raise CareerSourceError("career-source-capture-lineage-invalid") from exc
        if sha256_digest(universe.canonical_bytes()) != capture.declaration_hash:
            raise CareerSourceError("career-source-capture-lineage-invalid")
        if capture.source_id not in {source.source_id for source in universe.sources}:
            raise CareerSourceError("career-source-capture-source-undeclared")
        if capture.predecessor_capture_id is not None:
            parent = self._verify_capture(
                capture.predecessor_capture_id, ancestry=ancestry | {capture_id}
            )
            if parent.source_id != capture.source_id:
                raise CareerSourceError("career-source-capture-predecessor-invalid")
        return capture

    def capture(self, capture: dict[str, Any], source_bytes: bytes) -> dict[str, Any]:
        try:
            if capture.get("schema_version") == "career-source-capture/v1":
                raise CareerSourceError("career-source-capture-migration-required")
            universe, declaration_hash = self._declaration_binding()
            payload = dict(capture)
            supplied_binding = {
                key: payload.pop(key)
                for key in ("declaration_revision_id", "declaration_hash")
                if key in payload
            }
            expected_binding = {
                "declaration_revision_id": universe.revision_id,
                "declaration_hash": declaration_hash,
            }
            if supplied_binding and supplied_binding != expected_binding:
                raise ValueError
            payload.update(expected_binding)
            stored = CareerSourceCapture.model_validate(payload)
            capture_id = self._safe_id(stored.capture_id)
            if not isinstance(source_bytes, bytes) or stored.content_hash != sha256_digest(
                source_bytes
            ):
                raise ValueError
        except CareerSourceError:
            raise
        except (TypeError, ValueError) as exc:
            raise CareerSourceError("career-source-capture-invalid") from exc
        self._ensure_root()
        captures = self.workspace.child(".career-evidence", "sources", "captures")
        captures.mkdir(exist_ok=True)
        if stored.source_id not in {source.source_id for source in universe.sources}:
            raise CareerSourceError("career-source-capture-source-undeclared")
        if stored.predecessor_capture_id is not None:
            parent = self._verify_capture(stored.predecessor_capture_id, ancestry=frozenset())
            if parent.source_id != stored.source_id:
                raise CareerSourceError("career-source-capture-predecessor-invalid")
        raw_path = self._raw_path(stored.content_hash)
        if raw_path.is_symlink():
            raise CareerSourceError("career-source-capture-raw-unsafe")
        try:
            if not raw_path.exists():
                with raw_path.open("xb") as raw_file:
                    raw_file.write(source_bytes)
            elif sha256_digest(raw_path.read_bytes()) != stored.content_hash:
                raise CareerSourceError("career-source-capture-raw-invalid")
            create_only_canonical_bundle(
                captures, capture_id, {"manifest.json": stored.model_dump(mode="json")}
            )
            current_root = self.workspace.child(".career-evidence", "sources", "current-captures")
            current_root.mkdir(exist_ok=True)
            atomic_write_canonical_json(
                self._semantic_path(f"current-captures/{stored.source_id}.json"),
                DeclarationBoundCurrentCapturePointer(
                    source_id=stored.source_id,
                    capture_id=stored.capture_id,
                    content_hash=stored.content_hash,
                    declaration_revision_id=stored.declaration_revision_id,
                    declaration_hash=stored.declaration_hash,
                ).model_dump(mode="json"),
            )
        except (FormalRunStorageError, OSError) as exc:
            raise CareerSourceError("career-source-capture-already-exists") from exc
        return stored.model_dump(mode="json")

    def verify_capture(self, capture: dict[str, Any]) -> None:
        try:
            if capture.get("schema_version") == "career-source-capture/v1":
                raise CareerSourceError("career-source-capture-migration-required")
            expected = CareerSourceCapture.model_validate(capture)
            stored = self._verify_capture(expected.capture_id, ancestry=frozenset())
        except CareerSourceError:
            raise
        except (TypeError, ValueError) as exc:
            raise CareerSourceError("career-source-capture-invalid") from exc
        if canonical_json_bytes(stored) != canonical_json_bytes(expected):
            raise CareerSourceError("career-source-capture-lineage-invalid")

    def current_capture(self, source_id: str) -> CareerSourceCapture:
        """Resolve one source through its exact strict current-capture pointer."""
        source_id = self._safe_id(source_id)
        try:
            pointer_path = self._semantic_path(f"current-captures/{source_id}.json")
            value = json.loads(pointer_path.read_text(encoding="utf-8"))
            pointer = DeclarationBoundCurrentCapturePointer.model_validate(value)
            capture = self._verify_capture(pointer.capture_id, ancestry=frozenset())
        except CareerSourceError:
            raise
        except (OSError, ValueError, json.JSONDecodeError, ValidationError) as exc:
            raise CareerSourceError("career-source-current-capture-invalid") from exc
        if (
            pointer.source_id != source_id
            or pointer.capture_id != capture.capture_id
            or pointer.content_hash != capture.content_hash
            or pointer.declaration_revision_id != capture.declaration_revision_id
            or pointer.declaration_hash != capture.declaration_hash
        ):
            raise CareerSourceError("career-source-current-capture-invalid")
        return capture

    def _derived_output_path(self, output_hash: str) -> Path:
        digest = output_hash.removeprefix("sha256:")
        if not re.fullmatch(r"[0-9a-f]{64}", digest):
            raise CareerSourceError("career-source-transformation-invalid")
        return self._semantic_path(f"derived-outputs/{digest}/manifest.json")

    def transform(
        self, transformation: dict[str, Any], output_bytes: bytes | None = None
    ) -> dict[str, Any]:
        try:
            if transformation.get("schema_version") == "career-source-transformation/v1":
                raise CareerSourceError("career-source-transformation-migration-required")
            payload = dict(transformation)
            capture = self._verify_capture(payload["input_capture_id"], ancestry=frozenset())
            if output_bytes is None:
                output_bytes = self._raw_path(capture.content_hash).read_bytes()
            if not isinstance(output_bytes, bytes):
                raise ValueError
            expected = {
                "source_id": capture.source_id,
                "input_hash": capture.content_hash,
                "declaration_revision_id": capture.declaration_revision_id,
                "declaration_hash": capture.declaration_hash,
                "output_hash": sha256_digest(output_bytes),
                "output_byte_count": len(output_bytes),
            }
            supplied = {key: payload.pop(key) for key in expected if key in payload}
            if any(supplied[key] != expected[key] for key in supplied):
                raise ValueError
            payload.update(expected)
            stored = CareerSourceTransformation.model_validate(payload)
            transformation_id = self._safe_id(stored.transformation_id)
        except CareerSourceError:
            raise
        except (OSError, TypeError, ValueError, KeyError) as exc:
            raise CareerSourceError("career-source-transformation-invalid") from exc
        self._ensure_root()
        transformations = self.workspace.child(".career-evidence", "sources", "transformations")
        transformations.mkdir(exist_ok=True)
        try:
            transformation_manifest = self._semantic_path(
                f"transformations/{transformation_id}/manifest.json"
            )
            if transformation_manifest.exists():
                raise FormalRunStorageError("transformation already exists")
            raw_path = self._raw_path(stored.output_hash)
            if raw_path.is_symlink():
                raise OSError
            if not raw_path.exists():
                with raw_path.open("xb") as raw_file:
                    raw_file.write(output_bytes)
            elif sha256_digest(raw_path.read_bytes()) != stored.output_hash:
                raise OSError
            output_manifest = DerivedOutputManifest(
                output_hash=stored.output_hash,
                byte_count=stored.output_byte_count,
            )
            output_path = self._derived_output_path(stored.output_hash)
            if output_path.exists():
                existing_output = DerivedOutputManifest.model_validate_json(
                    output_path.read_bytes()
                )
                if canonical_json_bytes(existing_output) != canonical_json_bytes(output_manifest):
                    raise FormalRunStorageError("derived output already exists")
            else:
                output_root = output_path.parent.parent
                output_root.mkdir(exist_ok=True)
                create_only_canonical_bundle(
                    output_root,
                    stored.output_hash.removeprefix("sha256:"),
                    {"manifest.json": output_manifest.model_dump(mode="json")},
                )
            create_only_canonical_bundle(
                transformations,
                transformation_id,
                {"manifest.json": stored.model_dump(mode="json")},
            )
        except (FormalRunStorageError, OSError, ValidationError) as exc:
            raise CareerSourceError("career-source-transformation-already-exists") from exc
        return stored.model_dump(mode="json")

    def verify_transformation(self, transformation: dict[str, Any]) -> None:
        try:
            if transformation.get("schema_version") == "career-source-transformation/v1":
                raise CareerSourceError("career-source-transformation-migration-required")
            expected = CareerSourceTransformation.model_validate(transformation)
            manifest = self._semantic_path(
                f"transformations/{expected.transformation_id}/manifest.json"
            )
            stored = CareerSourceTransformation.model_validate(
                json.loads(manifest.read_text(encoding="utf-8"))
            )
            capture = self._verify_capture(stored.input_capture_id, ancestry=frozenset())
            output_manifest = DerivedOutputManifest.model_validate_json(
                self._derived_output_path(stored.output_hash).read_bytes()
            )
            output_bytes = self._raw_path(stored.output_hash).read_bytes()
        except CareerSourceError:
            raise
        except (OSError, TypeError, ValueError, json.JSONDecodeError, ValidationError) as exc:
            raise CareerSourceError("career-source-transformation-invalid") from exc
        if (
            manifest.is_symlink()
            or stored.transformation_id != expected.transformation_id
            or stored.source_id != capture.source_id
            or capture.content_hash != stored.input_hash
            or capture.declaration_revision_id != stored.declaration_revision_id
            or capture.declaration_hash != stored.declaration_hash
            or output_manifest.output_hash != stored.output_hash
            or output_manifest.byte_count != stored.output_byte_count
            or sha256_digest(output_bytes) != stored.output_hash
            or len(output_bytes) != stored.output_byte_count
            or canonical_json_bytes(stored) != canonical_json_bytes(expected)
        ):
            raise CareerSourceError("career-source-transformation-lineage-invalid")

    def _migration_baseline(
        self, request: WorkspaceMigrationRequest
    ) -> tuple[
        dict[str, CareerSourceCapture],
        dict[str, CareerSourceTransformation],
        dict[str, DeclarationBoundCurrentCapturePointer],
        dict[str, bytes],
    ]:
        """Load a complete legacy inventory only from the requested commit snapshot."""
        try:
            blobs = self._commit_blob_inventory(request.baseline_commit)
            working = self._working_blob_inventory()
            if any(working.get(path) != value for path, value in blobs.items()):
                raise ValueError
            declarations: dict[str, CareerSourceUniverse] = {}
            captures: dict[str, CareerSourceCapture] = {}
            transformations: dict[str, CareerSourceTransformation] = {}
            pointers: dict[str, DeclarationBoundCurrentCapturePointer] = {}
            outputs: dict[str, DerivedOutputManifest] = {}
            for relative, payload in blobs.items():
                parts = tuple(relative.split("/"))
                if parts[:1] == ("declarations",) and parts[1:] != ("current.json",):
                    if len(parts) != 3 or parts[2] != "manifest.json":
                        raise ValueError
                    declaration = CareerSourceUniverse.model_validate_json(payload)
                    if declaration.revision_id != parts[1]:
                        raise ValueError
                    declarations[declaration.revision_id] = declaration
                elif parts[:1] == ("captures",):
                    if len(parts) != 3 or parts[2] != "manifest.json":
                        raise ValueError
                    capture = CareerSourceCapture.model_validate_json(payload)
                    if capture.capture_id != parts[1]:
                        raise ValueError
                    captures[capture.capture_id] = capture
                elif parts[:1] == ("transformations",):
                    if len(parts) != 3 or parts[2] != "manifest.json":
                        raise ValueError
                    transformation = CareerSourceTransformation.model_validate_json(payload)
                    if transformation.transformation_id != parts[1]:
                        raise ValueError
                    transformations[transformation.transformation_id] = transformation
                elif parts[:1] == ("current-captures",):
                    if len(parts) != 2:
                        raise ValueError
                    pointer = DeclarationBoundCurrentCapturePointer.model_validate_json(payload)
                    if pointer.source_id != Path(parts[1]).stem:
                        raise ValueError
                    pointers[pointer.source_id] = pointer
                elif parts[:1] == ("derived-outputs",):
                    if len(parts) != 3 or parts[2] != "manifest.json":
                        raise ValueError
                    output = DerivedOutputManifest.model_validate_json(payload)
                    if output.output_hash.removeprefix("sha256:") != parts[1]:
                        raise ValueError
                    outputs[output.output_hash] = output
            if not captures or set(pointers) != {
                capture.source_id for capture in captures.values()
            }:
                raise ValueError
            for capture in captures.values():
                declaration = declarations[capture.declaration_revision_id]
                if (
                    sha256_digest(declaration.canonical_bytes()) != capture.declaration_hash
                    or capture.source_id not in {source.source_id for source in declaration.sources}
                    or (
                        capture.predecessor_capture_id is not None
                        and capture.predecessor_capture_id not in captures
                    )
                ):
                    raise ValueError
            for pointer in pointers.values():
                capture = captures[pointer.capture_id]
                if (
                    pointer.content_hash != capture.content_hash
                    or pointer.declaration_revision_id != capture.declaration_revision_id
                    or pointer.declaration_hash != capture.declaration_hash
                ):
                    raise ValueError
            if set(outputs) != {value.output_hash for value in transformations.values()}:
                raise ValueError
            for transformation in transformations.values():
                capture = captures[transformation.input_capture_id]
                output = outputs[transformation.output_hash]
                if (
                    transformation.source_id != capture.source_id
                    or transformation.input_hash != capture.content_hash
                    or transformation.declaration_revision_id != capture.declaration_revision_id
                    or transformation.declaration_hash != capture.declaration_hash
                    or transformation.predecessor_capture_id not in (None, capture.capture_id)
                    or output.byte_count != transformation.output_byte_count
                ):
                    raise ValueError
            self._verify_raw_objects(tuple(captures.values()), frozenset(outputs))
        except (CareerSourceError, KeyError, ValueError, ValidationError) as exc:
            raise CareerSourceError("career-source-migration-request-invalid") from exc
        return captures, transformations, pointers, blobs

    @staticmethod
    def _migration_chains(
        captures: dict[str, CareerSourceCapture],
        pointers: dict[str, DeclarationBoundCurrentCapturePointer],
    ) -> tuple[tuple[str, tuple[str, ...], bool], ...]:
        """Partition all retained predecessor chains, including non-current history."""
        try:
            found: list[tuple[str, tuple[str, ...], bool]] = []
            for source_id in sorted(pointers):
                source_captures = {
                    capture_id: capture
                    for capture_id, capture in captures.items()
                    if capture.source_id == source_id
                }
                children: dict[str, list[str]] = {capture_id: [] for capture_id in source_captures}
                for capture in source_captures.values():
                    if capture.predecessor_capture_id is not None:
                        if capture.predecessor_capture_id not in source_captures:
                            raise ValueError
                        children[capture.predecessor_capture_id].append(capture.capture_id)
                if any(len(values) > 1 for values in children.values()):
                    raise ValueError
                roots = sorted(
                    capture_id
                    for capture_id, capture in source_captures.items()
                    if capture.predecessor_capture_id is None
                )
                visited: set[str] = set()
                for root in roots:
                    chain = [root]
                    while children[chain[-1]]:
                        chain.append(children[chain[-1]][0])
                    if any(capture_id in visited for capture_id in chain):
                        raise ValueError
                    visited.update(chain)
                    found.append(
                        (source_id, tuple(chain), pointers[source_id].capture_id == chain[-1])
                    )
                if (
                    visited != set(source_captures)
                    or sum(item[2] for item in found if item[0] == source_id) != 1
                ):
                    raise ValueError
            return tuple(found)
        except (KeyError, ValueError) as exc:
            raise CareerSourceError("career-source-migration-request-invalid") from exc

    def _retained_output_bytes(self, *, locator: str, output_hash: str) -> bytes:
        """Authenticate one supplied regular raw-vault object without echoing its path."""
        try:
            parts = tuple(locator.split("/"))
            if (
                len(parts) != 2
                or parts[0] != "raw"
                or parts[1] != output_hash.removeprefix("sha256:")
            ):
                raise ValueError
            path = self.workspace.child(".career-evidence", *parts)
            if (
                path.is_symlink()
                or not path.is_file()
                or not path.resolve(strict=True).is_relative_to(self.raw_root.resolve(strict=True))
            ):
                raise ValueError
            payload = path.read_bytes()
            if sha256_digest(payload) != output_hash:
                raise ValueError
            return payload
        except (OSError, PrivateWorkspaceError, ValueError) as exc:
            raise CareerSourceError("career-source-migration-request-invalid") from exc

    def _migration_preflight(self, request: dict[str, Any]) -> _MigrationPreflight:
        """Validate all baseline records and retained outputs before any stage write."""
        try:
            parsed = WorkspaceMigrationRequest.model_validate(request)
            captures, transformations, pointers, baseline_blobs = self._migration_baseline(parsed)
            actual_chains = self._migration_chains(captures, pointers)
            requested_chains = {
                (chain.source_id, tuple(chain.legacy_capture_ids)): chain for chain in parsed.chains
            }
            if set(requested_chains) != {
                (source_id, capture_ids) for source_id, capture_ids, _ in actual_chains
            }:
                raise ValueError
            capture_requests = {item.legacy_capture_id: item for item in parsed.captures}
            if set(capture_requests) != set(captures):
                raise ValueError
            successor_capture_ids: set[str] = set()
            for source_id, legacy_ids, is_current_head in actual_chains:
                chain = requested_chains[(source_id, legacy_ids)]
                mapped_successors = tuple(
                    capture_requests[item].successor_capture_id for item in legacy_ids
                )
                if (
                    tuple(chain.successor_capture_ids) != mapped_successors
                    or chain.is_current_head is not is_current_head
                    or chain.legacy_current_capture_id != pointers[source_id].capture_id
                    or chain.successor_current_capture_id != mapped_successors[-1]
                ):
                    raise ValueError
                successor_capture_ids.update(mapped_successors)
            if successor_capture_ids & set(captures):
                raise ValueError
            for capture_id, capture in captures.items():
                item = capture_requests[capture_id]
                if (
                    item.declaration_revision_id != capture.declaration_revision_id
                    or item.declaration_hash != capture.declaration_hash
                ):
                    raise ValueError
            transformation_requests = {
                item.legacy_transformation_id: item for item in parsed.transformations
            }
            if set(transformation_requests) != set(transformations):
                raise ValueError
            if {item.successor_transformation_id for item in parsed.transformations} & set(
                transformations
            ):
                raise ValueError
            output_bytes: dict[str, bytes] = {}
            for transformation_id, transformation in transformations.items():
                item = transformation_requests[transformation_id]
                if (
                    item.input_capture_id != transformation.input_capture_id
                    or item.output_hash != transformation.output_hash
                ):
                    raise ValueError
                output_bytes[transformation_id] = self._retained_output_bytes(
                    locator=item.retained_output_locator, output_hash=transformation.output_hash
                )
        except (CareerSourceError, KeyError, TypeError, ValueError, ValidationError) as exc:
            if (
                isinstance(exc, CareerSourceError)
                and exc.code == "career-source-migration-request-invalid"
            ):
                raise
            raise CareerSourceError("career-source-migration-request-invalid") from exc
        preflight = _MigrationPreflight(
            parsed, baseline_blobs, captures, transformations, output_bytes
        )
        self._validate_migration_overlay(preflight)
        return preflight

    @staticmethod
    def _migration_stage_values(
        preflight: _MigrationPreflight,
    ) -> tuple[
        dict[str, CareerSourceCapture],
        dict[str, CareerSourceTransformation],
        WorkspaceMigrationReceipt,
    ]:
        """Derive the complete successor graph without touching the workspace."""
        capture_requests = {item.legacy_capture_id: item for item in preflight.request.captures}
        transformation_requests = {
            item.legacy_transformation_id: item for item in preflight.request.transformations
        }
        successors: dict[str, CareerSourceCapture] = {}
        for legacy_id, legacy in preflight.captures.items():
            predecessor = legacy.predecessor_capture_id
            successors[legacy_id] = legacy.model_copy(
                update={
                    "capture_id": capture_requests[legacy_id].successor_capture_id,
                    "predecessor_capture_id": (
                        None
                        if predecessor is None
                        else capture_requests[predecessor].successor_capture_id
                    ),
                }
            )
        successor_transformations: dict[str, CareerSourceTransformation] = {}
        for legacy_id, legacy in preflight.transformations.items():
            item = transformation_requests[legacy_id]
            successor_transformations[legacy_id] = legacy.model_copy(
                update={
                    "transformation_id": item.successor_transformation_id,
                    "input_capture_id": capture_requests[
                        legacy.input_capture_id
                    ].successor_capture_id,
                    "predecessor_capture_id": capture_requests[
                        legacy.input_capture_id
                    ].successor_capture_id,
                }
            )
        receipt = WorkspaceMigrationReceipt(
            receipt_id=preflight.request.receipt_id,
            baseline_commit=preflight.request.baseline_commit,
            staged_at=preflight.request.staged_at,
            chains=preflight.request.chains,
            captures=preflight.request.captures,
            transformations=preflight.request.transformations,
        )
        return successors, successor_transformations, receipt

    def _validate_migration_overlay(self, preflight: _MigrationPreflight) -> None:
        """Allow retries only over exact deterministic files derived from the request."""
        try:
            successors, transformations, receipt = self._migration_stage_values(preflight)
            expected: dict[str, object] = {
                f"captures/{value.capture_id}/manifest.json": value.model_dump(mode="json")
                for value in successors.values()
            }
            expected.update(
                {
                    f"transformations/{value.transformation_id}/manifest.json": value.model_dump(
                        mode="json"
                    )
                    for value in transformations.values()
                }
            )
            expected.update(
                {
                    f"derived-outputs/{value.output_hash.removeprefix('sha256:')}/manifest.json": (
                        DerivedOutputManifest(
                            output_hash=value.output_hash,
                            byte_count=len(preflight.output_bytes[legacy_id]),
                        ).model_dump(mode="json")
                    )
                    for legacy_id, value in transformations.items()
                }
            )
            expected[f"migration-receipts/{receipt.receipt_id}/manifest.json"] = receipt.model_dump(
                mode="json"
            )
            working = self._working_blob_inventory()
            if set(preflight.baseline_blobs) - set(working):
                raise ValueError
            for path, payload in working.items():
                if path in preflight.baseline_blobs:
                    if payload != preflight.baseline_blobs[path]:
                        raise ValueError
                elif path not in expected or canonical_json_bytes(
                    json.loads(payload.decode("utf-8"))
                ) != canonical_json_bytes(expected[path]):
                    raise ValueError
        except (OSError, ValueError, json.JSONDecodeError, ValidationError) as exc:
            raise CareerSourceError("career-source-migration-request-invalid") from exc

    def preflight_workspace_migration(self, request: dict[str, Any]) -> dict[str, object]:
        """Authenticate a complete private migration input graph without writing it."""
        preflight = self._migration_preflight(request)
        return {
            "candidate_only": True,
            "capture_count": len(preflight.captures),
            "transformation_count": len(preflight.transformations),
            "output_byte_count": sum(len(value) for value in preflight.output_bytes.values()),
        }

    @staticmethod
    def _stage_bundle(root: Path, bundle_id: str, value: object) -> None:
        """Publish one deterministic bundle or accept its byte-identical retry state."""
        destination = root / bundle_id / "manifest.json"
        try:
            if destination.exists():
                if (
                    destination.is_symlink()
                    or {item.name for item in destination.parent.iterdir()} != {"manifest.json"}
                    or canonical_json_bytes(json.loads(destination.read_text(encoding="utf-8")))
                    != canonical_json_bytes(value)
                ):
                    raise ValueError
                return
            create_only_canonical_bundle(root, bundle_id, {"manifest.json": value})
        except (FormalRunStorageError, OSError, ValueError, json.JSONDecodeError) as exc:
            raise CareerSourceError("career-source-migration-staging-invalid") from exc

    def stage_workspace_migration(
        self, request: dict[str, Any], *, fail_after: str | None = None
    ) -> dict[str, object]:
        """Stage all successors without moving pointers or creating Git authority."""
        preflight = self._migration_preflight(request)
        successors, successor_transformations, receipt = self._migration_stage_values(preflight)
        try:
            self._ensure_root()
            capture_root = self.workspace.child(".career-evidence", "sources", "captures")
            for successor in successors.values():
                self._stage_bundle(
                    capture_root, successor.capture_id, successor.model_dump(mode="json")
                )
            if fail_after == "captures":
                raise CareerSourceError("career-source-migration-staging-interrupted")
            output_root = self.workspace.child(".career-evidence", "sources", "derived-outputs")
            for legacy_id, transformation in successor_transformations.items():
                output = DerivedOutputManifest(
                    output_hash=transformation.output_hash,
                    byte_count=len(preflight.output_bytes[legacy_id]),
                )
                self._stage_bundle(
                    output_root,
                    transformation.output_hash.removeprefix("sha256:"),
                    output.model_dump(mode="json"),
                )
            if fail_after == "outputs":
                raise CareerSourceError("career-source-migration-staging-interrupted")
            transformation_root = self.workspace.child(
                ".career-evidence", "sources", "transformations"
            )
            for successor in successor_transformations.values():
                self._stage_bundle(
                    transformation_root,
                    successor.transformation_id,
                    successor.model_dump(mode="json"),
                )
            if fail_after == "transformations":
                raise CareerSourceError("career-source-migration-staging-interrupted")
            receipt_root = self.workspace.child(".career-evidence", "sources", "migration-receipts")
            self._stage_bundle(receipt_root, receipt.receipt_id, receipt.model_dump(mode="json"))
            if fail_after == "receipt":
                raise CareerSourceError("career-source-migration-staging-interrupted")
        except CareerSourceError:
            raise
        except (OSError, PrivateWorkspaceError) as exc:
            raise CareerSourceError("career-source-migration-staging-invalid") from exc
        return {
            "candidate_only": True,
            "staged": True,
            "capture_count": len(successors),
            "transformation_count": len(successor_transformations),
        }

    def _git_object_format(self) -> tuple[str, int]:
        try:
            object_format = self._git("rev-parse", "--show-object-format").decode("ascii").strip()
            return object_format, _GIT_OID_LENGTHS[object_format]
        except (UnicodeDecodeError, KeyError, CareerSourceError) as exc:
            raise CareerSourceError("career-source-retention-ref-invalid") from exc

    def _retention_ref_value(self, oid_length: int) -> str | None:
        """Read the one retention ref without treating it as verification authority."""
        try:
            completed = subprocess.run(
                ["git", "rev-parse", "--verify", "--quiet", _CUSTODY_RETENTION_REF],
                cwd=self.workspace.root,
                check=False,
                capture_output=True,
            )
        except OSError as exc:
            raise CareerSourceError("career-source-retention-ref-invalid") from exc
        if completed.returncode == 1:
            return None
        if completed.returncode != 0:
            raise CareerSourceError("career-source-retention-ref-invalid")
        try:
            value = completed.stdout.decode("ascii").strip()
        except UnicodeDecodeError as exc:
            raise CareerSourceError("career-source-retention-ref-invalid") from exc
        if not re.fullmatch(rf"[0-9a-f]{{{oid_length}}}", value):
            raise CareerSourceError("career-source-retention-ref-invalid")
        return value

    @staticmethod
    def _pointer_bytes(capture: CareerSourceCapture) -> bytes:
        return canonical_json_bytes(
            DeclarationBoundCurrentCapturePointer(
                source_id=capture.source_id,
                capture_id=capture.capture_id,
                content_hash=capture.content_hash,
                declaration_revision_id=capture.declaration_revision_id,
                declaration_hash=capture.declaration_hash,
            ).model_dump(mode="json")
        ) + b"\n"

    def _replace_pointer_if_exact(self, path: Path, expected: bytes, replacement: bytes) -> bool:
        """Make an operator-owned pointer change only from its exact known bytes."""
        try:
            if path.read_bytes() != expected:
                raise ValueError
            atomic_write_canonical_json(path, json.loads(replacement.decode("utf-8")))
            return True
        except (OSError, ValueError, json.JSONDecodeError, FormalRunStorageError) as exc:
            raise CareerSourceError("career-source-workspace-drift") from exc

    def _restore_attempt_pointers(self, changed: list[tuple[Path, bytes, bytes]]) -> None:
        """Never overwrite a third-party value while undoing a failed attempt."""
        for path, legacy, successor in reversed(changed):
            try:
                if path.read_bytes() == successor:
                    atomic_write_canonical_json(path, json.loads(legacy.decode("utf-8")))
            except (OSError, ValueError, json.JSONDecodeError, FormalRunStorageError):
                # A later verification catches any unsupported external writer without disclosure.
                continue

    def _deterministic_migration_commit(
        self,
        *,
        preflight: _MigrationPreflight,
        successors: dict[str, CareerSourceCapture],
        transformations: dict[str, CareerSourceTransformation],
        receipt: WorkspaceMigrationReceipt,
        pointer_values: dict[str, bytes],
    ) -> str:
        """Build an unreachable child commit with a private temporary index only."""
        staged_paths = [
            *(
                f".career-evidence/sources/captures/{value.capture_id}/manifest.json"
                for value in successors.values()
            ),
            *(
                f".career-evidence/sources/transformations/{value.transformation_id}/manifest.json"
                for value in transformations.values()
            ),
            *(
                f".career-evidence/sources/derived-outputs/{value.output_hash.removeprefix('sha256:')}/manifest.json"
                for value in transformations.values()
            ),
            f".career-evidence/sources/migration-receipts/{receipt.receipt_id}/manifest.json",
        ]
        timestamp = preflight.request.staged_at
        try:
            datetime.fromisoformat(timestamp)
        except ValueError as exc:
            raise CareerSourceError("career-source-migration-request-invalid") from exc
        with tempfile.TemporaryDirectory(prefix="career-source-index-") as temporary:
            index_path = str(Path(temporary) / "index")
            environment = {"GIT_INDEX_FILE": index_path}
            self._git("read-tree", preflight.request.baseline_commit, environment=environment)
            self._git("add", "--", *staged_paths, environment=environment)
            for source_id, value in sorted(pointer_values.items()):
                blob = self._git(
                    "hash-object", "-w", "--stdin", input_bytes=value, environment=environment
                ).decode("ascii").strip()
                self._git(
                    "update-index",
                    "--add",
                    "--cacheinfo",
                    f"100644,{blob},.career-evidence/sources/current-captures/{source_id}.json",
                    environment=environment,
                )
            tree = self._git("write-tree", environment=environment).decode("ascii").strip()
            identity = {
                "GIT_AUTHOR_NAME": "career-evidence-custody",
                "GIT_AUTHOR_EMAIL": "career-evidence-custody@invalid",
                "GIT_AUTHOR_DATE": timestamp,
                "GIT_COMMITTER_NAME": "career-evidence-custody",
                "GIT_COMMITTER_EMAIL": "career-evidence-custody@invalid",
                "GIT_COMMITTER_DATE": timestamp,
            }
            return self._git(
                "commit-tree",
                tree,
                "-p",
                preflight.request.baseline_commit,
                "-m",
                "career-source custody migration",
                environment=environment | identity,
            ).decode("ascii").strip()

    def adjudicate_workspace_migration(
        self,
        request: dict[str, Any],
        *,
        expected_workspace_commit: str,
        expected_retention_ref_oid: str,
        fail_after: str | None = None,
    ) -> dict[str, object]:
        """Finalize one complete migration through the sole expected-old ref CAS."""
        preflight = self._migration_preflight(request)
        if expected_workspace_commit != preflight.request.baseline_commit:
            raise CareerSourceError("career-source-migration-request-invalid")
        _, oid_length = self._git_object_format()
        if not re.fullmatch(rf"[0-9a-f]{{{oid_length}}}", expected_retention_ref_oid):
            raise CareerSourceError("career-source-retention-ref-invalid")
        self.stage_workspace_migration(request)
        preflight = self._migration_preflight(request)
        successors, transformations, receipt = self._migration_stage_values(preflight)
        successor_by_id = {value.capture_id: value for value in successors.values()}
        pointer_changes: list[tuple[Path, bytes, bytes]] = []
        pointer_values: dict[str, bytes] = {}
        for chain in preflight.request.chains:
            if not chain.is_current_head:
                continue
            legacy = preflight.captures[chain.legacy_current_capture_id]
            successor = successor_by_id[chain.successor_current_capture_id]
            if legacy.source_id != chain.source_id or successor.source_id != chain.source_id:
                raise CareerSourceError("career-source-migration-request-invalid")
            pointer_values[chain.source_id] = self._pointer_bytes(successor)
        candidate = self._deterministic_migration_commit(
            preflight=preflight,
            successors=successors,
            transformations=transformations,
            receipt=receipt,
            pointer_values=pointer_values,
        )
        if not re.fullmatch(rf"[0-9a-f]{{{oid_length}}}", candidate):
            raise CareerSourceError("career-source-migration-finalization-invalid")
        actual_ref = self._retention_ref_value(oid_length)
        zero = "0" * oid_length
        if actual_ref == candidate:
            if any(
                self._semantic_path(f"current-captures/{source_id}.json").read_bytes() != value
                for source_id, value in pointer_values.items()
            ):
                raise CareerSourceError("career-source-workspace-drift")
            self.verify(expected_workspace_commit=candidate)
            return {"adjudicated": True, "candidate_only": True, "workspace_commit": candidate}
        if actual_ref is None:
            if expected_retention_ref_oid != zero:
                raise CareerSourceError("career-source-retention-ref-stale")
        elif actual_ref != expected_retention_ref_oid:
            raise CareerSourceError("career-source-retention-ref-stale")
        for source_id, successor in sorted(pointer_values.items()):
            path = self._semantic_path(f"current-captures/{source_id}.json")
            legacy_capture_id = next(
                chain.legacy_current_capture_id
                for chain in preflight.request.chains
                if chain.source_id == source_id and chain.is_current_head
            )
            legacy = self._pointer_bytes(preflight.captures[legacy_capture_id])
            current = path.read_bytes()
            if current == successor:
                continue
            if current != legacy:
                raise CareerSourceError("career-source-workspace-drift")
            self._replace_pointer_if_exact(path, legacy, successor)
            pointer_changes.append((path, legacy, successor))
        try:
            self.verify(expected_workspace_commit=candidate)
            if fail_after == "before-ref":
                raise CareerSourceError("career-source-migration-finalization-interrupted")
            try:
                completed = subprocess.run(
                    [
                        "git",
                        "update-ref",
                        _CUSTODY_RETENTION_REF,
                        candidate,
                        expected_retention_ref_oid,
                    ],
                    cwd=self.workspace.root,
                    check=False,
                    capture_output=True,
                )
            except OSError as exc:
                raise CareerSourceError("career-source-retention-ref-invalid") from exc
            if completed.returncode != 0:
                raise CareerSourceError("career-source-retention-ref-stale")
        except CareerSourceError:
            self._restore_attempt_pointers(pointer_changes)
            raise
        if self._retention_ref_value(oid_length) != candidate:
            raise CareerSourceError("career-source-retention-ref-stale")
        self.verify(expected_workspace_commit=candidate)
        return {"adjudicated": True, "candidate_only": True, "workspace_commit": candidate}

    def capture_duplicates(
        self, first: dict[str, Any], second: dict[str, Any], source_bytes: bytes
    ) -> dict[str, Any]:
        self.capture(first, source_bytes)
        self.capture(second, source_bytes)
        return {"logical_source_count": 2, "created_fact_count": 0, "created_confidence_count": 0}

    def run_synthetic_tracer(
        self, *, declaration: dict[str, Any], source_bytes: bytes, transformation: dict[str, Any]
    ) -> dict[str, Any]:
        self.declare(declaration)
        capture = {
            "schema_version": "career-source-capture/v2",
            "capture_id": transformation["input_capture_id"],
            "source_id": declaration["sources"][0]["source_id"],
            "content_hash": transformation["input_hash"],
            "acquired_at": datetime.now(UTC).isoformat(),
            "method": "synthetic-text",
            "predecessor_capture_id": None,
            "authority": "candidate-only",
        }
        self.capture(capture, source_bytes)
        self.transform(transformation)
        return {
            "authority": "candidate-only",
            "created_assessment_count": 0,
            "created_mastery_count": 0,
        }

    def validate_source_bytes(self, source: bytes, _label: str) -> dict[str, int]:
        """Validate supported raw bytes without treating their text as instructions."""
        if not source:
            raise CareerSourceError("career-source-empty")
        if len(source) > _MAX_SOURCE_BYTES:
            raise CareerSourceError("career-source-too-large")
        try:
            text = source.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise CareerSourceError("career-source-invalid-utf8") from exc
        if "\x00" in text or any(character in text for character in _UNSAFE_CODEPOINTS):
            raise CareerSourceError("career-source-unsafe-control")
        return {"provider_invocations": 0, "command_invocations": 0}

    def scan_public_payload(self, payload: str, sentinels: tuple[str, ...]) -> None:
        """Reject synthetic leak probes without reaching into a private workspace."""
        if any(sentinel in payload for sentinel in sentinels):
            raise CareerSourceError("career-source-public-disclosure")

    @staticmethod
    def scan_public_tree(
        paths: tuple[Path, ...], *, public_root: Path, sentinels: tuple[str, ...]
    ) -> None:
        """Fail closed on synthetic private artifacts in declared public paths only."""
        try:
            root = public_root.resolve(strict=True)
            for path in paths:
                if path.is_symlink() or not path.is_file():
                    raise ValueError
                relative = path.resolve(strict=True).relative_to(root)
                if relative.parts[:2] == (".career-evidence", "raw"):
                    raise ValueError
                payload = path.read_bytes()
                if len(payload) > _MAX_SOURCE_BYTES or any(
                    sentinel.encode("utf-8") in payload for sentinel in sentinels
                ):
                    raise ValueError
        except (OSError, ValueError) as exc:
            raise CareerSourceError("career-source-public-disclosure") from exc

    def prepare_raw_vault(self) -> Path:
        """Create the ignored raw boundary only after full symlink checks."""
        self._ensure_root()
        return self.raw_root

    def safe_status(self) -> dict[str, object]:
        empty_status = {
            "backup_state": "not-configured",
            "candidate_only": True,
            "capture_count": 0,
            "declaration_present": False,
            "source_revision_count": 0,
            "transformation_count": 0,
        }
        if not self.root.exists():
            return empty_status
        if self.root.parent.is_symlink() or self.root.is_symlink() or not self.root.is_dir():
            raise CareerSourceError("career-source-private-root-unsafe")
        declarations = self.root / "declarations"
        captures = self.root / "captures"
        transformations = self.root / "transformations"
        return {
            "backup_state": "not-configured",
            "candidate_only": True,
            "capture_count": len(tuple(captures.glob("*"))) if captures.is_dir() else 0,
            "declaration_present": (declarations / "current.json").is_file(),
            "source_revision_count": (
                len(tuple(path for path in declarations.iterdir() if path.is_dir()))
                if declarations.is_dir()
                else 0
            ),
            "transformation_count": (
                len(tuple(transformations.glob("*"))) if transformations.is_dir() else 0
            ),
        }

    def _git(
        self,
        *args: str,
        input_bytes: bytes | None = None,
        environment: dict[str, str] | None = None,
    ) -> bytes:
        """Run a redacted Git query only in the selected private workspace."""
        try:
            completed = subprocess.run(
                ["git", *args],
                cwd=self.workspace.root,
                check=False,
                capture_output=True,
                input=input_bytes,
                env=os.environ | (environment or {}),
            )
        except OSError as exc:
            raise CareerSourceError("career-source-snapshot-anchor-invalid") from exc
        if completed.returncode != 0:
            raise CareerSourceError("career-source-snapshot-anchor-invalid")
        return completed.stdout

    def _commit_blob_inventory(self, expected_workspace_commit: str) -> dict[str, bytes]:
        """Load exact source blobs from one caller-selected commit object."""
        try:
            object_format = self._git("rev-parse", "--show-object-format").decode("ascii").strip()
            oid_length = _GIT_OID_LENGTHS[object_format]
        except (UnicodeDecodeError, KeyError, CareerSourceError) as exc:
            raise CareerSourceError("career-source-snapshot-anchor-invalid") from exc
        if not re.fullmatch(rf"[0-9a-f]{{{oid_length}}}", expected_workspace_commit):
            raise CareerSourceError("career-source-snapshot-anchor-invalid")
        try:
            top_level = Path(
                self._git("rev-parse", "--show-toplevel").decode("utf-8").strip()
            ).resolve(strict=True)
            object_type = (
                self._git("cat-file", "-t", expected_workspace_commit).decode("ascii").strip()
            )
        except (OSError, UnicodeDecodeError, CareerSourceError) as exc:
            raise CareerSourceError("career-source-snapshot-anchor-invalid") from exc
        if top_level != self.workspace.root or object_type != "commit":
            raise CareerSourceError("career-source-snapshot-anchor-invalid")
        raw_entries = self._git(
            "ls-tree", "-rz", "--full-tree", expected_workspace_commit, "--", ".career-evidence"
        )
        blobs: dict[str, bytes] = {}
        for entry in raw_entries.split(b"\0"):
            if not entry:
                continue
            try:
                header, raw_path = entry.split(b"\t", maxsplit=1)
                mode, object_type, object_id = header.decode("ascii").split(" ")
                path = raw_path.decode("utf-8")
            except (UnicodeDecodeError, ValueError) as exc:
                raise CareerSourceError("career-source-snapshot-invalid") from exc
            if path.startswith(".career-evidence/raw/"):
                raise CareerSourceError("career-source-snapshot-invalid")
            if not path.startswith(".career-evidence/sources/"):
                continue
            if mode != "100644" or object_type != "blob":
                raise CareerSourceError("career-source-snapshot-invalid")
            relative = path.removeprefix(".career-evidence/sources/")
            if not relative or relative in blobs or not self._is_semantic_path(relative):
                raise CareerSourceError("career-source-snapshot-invalid")
            blobs[relative] = self._git("cat-file", "blob", object_id)
        return blobs

    @staticmethod
    def _is_semantic_path(relative: str) -> bool:
        if not any(pattern.fullmatch(relative) for _, pattern in _SEMANTIC_NAMESPACES):
            return False
        parts = tuple(relative.split("/"))
        if parts == ("declarations", "current.json"):
            return True
        if parts[0] == "current-captures":
            return _SAFE_ID.fullmatch(Path(parts[1]).stem) is not None
        if parts[0] == "derived-outputs":
            return re.fullmatch(r"[0-9a-f]{64}", parts[1]) is not None
        return _SAFE_ID.fullmatch(parts[1]) is not None

    @staticmethod
    def _is_semantic_directory(relative: str) -> bool:
        parts = tuple(relative.split("/"))
        if len(parts) == 1:
            return parts[0] in {
                "declarations",
                "captures",
                "current-captures",
                "transformations",
                "migration-receipts",
                "derived-outputs",
            }
        return (
            len(parts) == 2
            and parts[0]
            in {
                "declarations",
                "captures",
                "transformations",
                "migration-receipts",
                "derived-outputs",
            }
            and (
                re.fullmatch(r"[0-9a-f]{64}", parts[1]) is not None
                if parts[0] == "derived-outputs"
                else _SAFE_ID.fullmatch(parts[1]) is not None
            )
        )

    def _semantic_path(self, relative: str) -> Path:
        if not self._is_semantic_path(relative):
            raise CareerSourceError("career-source-snapshot-invalid")
        try:
            return self.workspace.child(".career-evidence", "sources", *relative.split("/"))
        except PrivateWorkspaceError as exc:
            raise CareerSourceError("career-source-snapshot-invalid") from exc

    def _working_blob_inventory(self) -> dict[str, bytes]:
        """Collect regular source files without following a mutable symlink."""
        if not self.root.exists():
            return {}
        if self.root.is_symlink() or not self.root.is_dir():
            raise CareerSourceError("career-source-snapshot-invalid")
        blobs: dict[str, bytes] = {}
        try:
            for path in self.root.rglob("*"):
                if path.is_symlink():
                    raise ValueError
                if path.is_file():
                    relative = path.relative_to(self.root).as_posix()
                    blobs[relative] = self._semantic_path(relative).read_bytes()
                elif not path.is_dir() or not self._is_semantic_directory(
                    path.relative_to(self.root).as_posix()
                ):
                    raise ValueError
        except (OSError, ValueError) as exc:
            raise CareerSourceError("career-source-snapshot-invalid") from exc
        return blobs

    def _verify_current_captures(self) -> tuple[CareerSourceCapture, ...]:
        captures = self.root / "captures"
        capture_values = (
            tuple(self._read_capture(path.name) for path in captures.iterdir())
            if captures.exists()
            else ()
        )
        expected_sources = {capture.source_id for capture in capture_values}
        pointers = self.root / "current-captures"
        if not pointers.exists():
            if expected_sources:
                raise CareerSourceError("career-source-snapshot-invalid")
            return capture_values
        actual_sources: set[str] = set()
        try:
            for pointer in pointers.iterdir():
                relative = f"current-captures/{pointer.name}"
                if (
                    pointer.is_symlink()
                    or not pointer.is_file()
                    or not self._is_semantic_path(relative)
                ):
                    raise ValueError
                source_id = pointer.stem
                value = json.loads(self._semantic_path(relative).read_text(encoding="utf-8"))
                pointer_value = DeclarationBoundCurrentCapturePointer.model_validate(value)
                capture = self._verify_capture(pointer_value.capture_id, ancestry=frozenset())
                if (
                    pointer_value.source_id != source_id
                    or pointer_value.capture_id != capture.capture_id
                    or pointer_value.content_hash != capture.content_hash
                    or pointer_value.declaration_revision_id != capture.declaration_revision_id
                    or pointer_value.declaration_hash != capture.declaration_hash
                ):
                    raise ValueError
                actual_sources.add(source_id)
        except (OSError, ValueError, json.JSONDecodeError, CareerSourceError) as exc:
            raise CareerSourceError("career-source-snapshot-invalid") from exc
        if actual_sources != expected_sources:
            raise CareerSourceError("career-source-snapshot-invalid")
        return capture_values

    def _verify_raw_objects(
        self, captures: tuple[CareerSourceCapture, ...], output_hashes: frozenset[str]
    ) -> int:
        expected = {capture.content_hash.removeprefix("sha256:") for capture in captures}
        expected.update(output_hash.removeprefix("sha256:") for output_hash in output_hashes)
        if not self.raw_root.exists():
            if expected:
                raise CareerSourceError("career-source-snapshot-invalid")
            return 0
        if self.raw_root.is_symlink() or not self.raw_root.is_dir():
            raise CareerSourceError("career-source-snapshot-invalid")
        total = 0
        found: set[str] = set()
        try:
            for raw_path in self.raw_root.iterdir():
                if raw_path.is_symlink() or not raw_path.is_file() or raw_path.name not in expected:
                    raise ValueError
                payload = raw_path.read_bytes()
                if sha256_digest(payload) != f"sha256:{raw_path.name}":
                    raise ValueError
                found.add(raw_path.name)
                total += len(payload)
        except (OSError, ValueError) as exc:
            raise CareerSourceError("career-source-snapshot-invalid") from exc
        if found != expected:
            raise CareerSourceError("career-source-snapshot-invalid")
        return total

    def _verify_transformation_inventory(self) -> frozenset[str]:
        """Require one valid manifest for every transformation and derived byte object."""
        transformations = self.root / "transformations"
        transformation_values: list[CareerSourceTransformation] = []
        if transformations.exists():
            if transformations.is_symlink() or not transformations.is_dir():
                raise CareerSourceError("career-source-snapshot-invalid")
            for path in transformations.iterdir():
                if (
                    path.is_symlink()
                    or not path.is_dir()
                    or not self._is_semantic_directory(path.relative_to(self.root).as_posix())
                    or {child.name for child in path.iterdir()} != {"manifest.json"}
                ):
                    raise CareerSourceError("career-source-snapshot-invalid")
                manifest = self._semantic_path(f"transformations/{path.name}/manifest.json")
                transformation = CareerSourceTransformation.model_validate_json(
                    manifest.read_bytes()
                )
                self.verify_transformation(transformation.model_dump(mode="json"))
                transformation_values.append(transformation)

        outputs = self.root / "derived-outputs"
        output_values: dict[str, DerivedOutputManifest] = {}
        if outputs.exists():
            if outputs.is_symlink() or not outputs.is_dir():
                raise CareerSourceError("career-source-snapshot-invalid")
            for path in outputs.iterdir():
                relative = path.relative_to(self.root).as_posix()
                if (
                    path.is_symlink()
                    or not path.is_dir()
                    or not self._is_semantic_directory(relative)
                    or {child.name for child in path.iterdir()} != {"manifest.json"}
                ):
                    raise CareerSourceError("career-source-snapshot-invalid")
                manifest = self._semantic_path(f"derived-outputs/{path.name}/manifest.json")
                output = DerivedOutputManifest.model_validate_json(manifest.read_bytes())
                if output.output_hash.removeprefix("sha256:") != path.name:
                    raise CareerSourceError("career-source-snapshot-invalid")
                output_values[output.output_hash] = output

        referenced = frozenset(value.output_hash for value in transformation_values)
        if set(output_values) != referenced:
            raise CareerSourceError("career-source-snapshot-invalid")
        return referenced

    def _is_git_ancestor(self, ancestor: str, descendant: str) -> bool:
        try:
            completed = subprocess.run(
                ["git", "merge-base", "--is-ancestor", ancestor, descendant],
                cwd=self.workspace.root,
                check=False,
                capture_output=True,
            )
        except OSError as exc:
            raise CareerSourceError("career-source-snapshot-invalid") from exc
        if completed.returncode not in {0, 1}:
            raise CareerSourceError("career-source-snapshot-invalid")
        return completed.returncode == 0

    def _receipt_baseline_records(
        self, receipt: WorkspaceMigrationReceipt
    ) -> tuple[dict[str, CareerSourceCapture], dict[str, CareerSourceTransformation]]:
        """Read immutable legacy records only from a receipt's committed baseline."""
        try:
            captures: dict[str, CareerSourceCapture] = {}
            transformations: dict[str, CareerSourceTransformation] = {}
            for relative, payload in self._commit_blob_inventory(receipt.baseline_commit).items():
                parts = tuple(relative.split("/"))
                if parts[:1] == ("captures",):
                    capture = CareerSourceCapture.model_validate_json(payload)
                    if parts != ("captures", capture.capture_id, "manifest.json"):
                        raise ValueError
                    captures[capture.capture_id] = capture
                elif parts[:1] == ("transformations",):
                    transformation = CareerSourceTransformation.model_validate_json(payload)
                    if parts != (
                        "transformations",
                        transformation.transformation_id,
                        "manifest.json",
                    ):
                        raise ValueError
                    transformations[transformation.transformation_id] = transformation
            if not captures or set(
                item.legacy_capture_id for item in receipt.captures
            ) != set(captures):
                raise ValueError
            if set(item.legacy_transformation_id for item in receipt.transformations) != set(
                transformations
            ):
                raise ValueError
            return captures, transformations
        except (CareerSourceError, ValueError, ValidationError) as exc:
            raise CareerSourceError("career-source-snapshot-invalid") from exc

    def _verified_descendant_contains(
        self, *, capture: CareerSourceCapture, source_id: str, expected_ancestor: str
    ) -> bool:
        """Walk an authenticated same-source predecessor chain with cycle detection."""
        seen: set[str] = set()
        current = capture
        while True:
            if current.source_id != source_id or current.capture_id in seen:
                raise CareerSourceError("career-source-snapshot-invalid")
            if current.capture_id == expected_ancestor:
                return True
            seen.add(current.capture_id)
            if current.predecessor_capture_id is None:
                return False
            current = self._verify_capture(
                current.predecessor_capture_id, ancestry=frozenset(seen)
            )

    def _verify_migration_receipts(
        self,
        *,
        expected_workspace_commit: str,
        capture_values: tuple[CareerSourceCapture, ...],
    ) -> None:
        """Keep receipts immutable while accepting verified same-source recapture descendants."""
        receipt_root = self.root / "migration-receipts"
        if not receipt_root.exists():
            return
        if receipt_root.is_symlink() or not receipt_root.is_dir():
            raise CareerSourceError("career-source-snapshot-invalid")
        current_by_source = {
            capture.source_id: self.current_capture(capture.source_id)
            for capture in capture_values
        }
        capture_by_id = {capture.capture_id: capture for capture in capture_values}
        transformation_root = self.root / "transformations"
        try:
            for receipt_path in receipt_root.iterdir():
                if (
                    receipt_path.is_symlink()
                    or not receipt_path.is_dir()
                    or {item.name for item in receipt_path.iterdir()} != {"manifest.json"}
                ):
                    raise ValueError
                receipt = WorkspaceMigrationReceipt.model_validate_json(
                    (receipt_path / "manifest.json").read_bytes()
                )
                if receipt.receipt_id != receipt_path.name or not self._is_git_ancestor(
                    receipt.baseline_commit, expected_workspace_commit
                ):
                    raise ValueError
                legacy_captures, legacy_transformations = self._receipt_baseline_records(receipt)
                capture_mapping = {
                    item.legacy_capture_id: item.successor_capture_id for item in receipt.captures
                }
                if set(capture_mapping) != set(legacy_captures):
                    raise ValueError
                for legacy_id, successor_id in capture_mapping.items():
                    legacy = legacy_captures[legacy_id]
                    expected = legacy.model_copy(
                        update={
                            "capture_id": successor_id,
                            "predecessor_capture_id": (
                                None
                                if legacy.predecessor_capture_id is None
                                else capture_mapping[legacy.predecessor_capture_id]
                            ),
                        }
                    )
                    if successor_id not in capture_by_id or canonical_json_bytes(
                        capture_by_id[successor_id]
                    ) != canonical_json_bytes(expected):
                        raise ValueError
                receipt_sources = {chain.source_id for chain in receipt.chains}
                if set(current_by_source) != receipt_sources:
                    raise ValueError
                for chain in receipt.chains:
                    if not self._verified_descendant_contains(
                        capture=current_by_source[chain.source_id],
                        source_id=chain.source_id,
                        expected_ancestor=chain.successor_current_capture_id,
                    ):
                        raise ValueError
                transformation_mapping = {
                    item.legacy_transformation_id: item.successor_transformation_id
                    for item in receipt.transformations
                }
                if set(transformation_mapping) != set(legacy_transformations):
                    raise ValueError
                for legacy_id, successor_id in transformation_mapping.items():
                    legacy = legacy_transformations[legacy_id]
                    expected = legacy.model_copy(
                        update={
                            "transformation_id": successor_id,
                            "input_capture_id": capture_mapping[legacy.input_capture_id],
                            "predecessor_capture_id": capture_mapping[legacy.input_capture_id],
                        }
                    )
                    manifest = transformation_root / successor_id / "manifest.json"
                    if (
                        manifest.is_symlink()
                        or not manifest.is_file()
                        or canonical_json_bytes(
                            CareerSourceTransformation.model_validate_json(manifest.read_bytes())
                        )
                        != canonical_json_bytes(expected)
                    ):
                        raise ValueError
        except (CareerSourceError, OSError, ValueError, ValidationError) as exc:
            raise CareerSourceError("career-source-snapshot-invalid") from exc

    def verify(self, *, expected_workspace_commit: str) -> dict[str, object]:
        """Authenticate the current source snapshot against one exact Git commit."""
        committed = self._commit_blob_inventory(expected_workspace_commit)
        working = self._working_blob_inventory()
        if committed != working:
            raise CareerSourceError("career-source-snapshot-invalid")
        if not committed:
            return {
                "candidate_only": True,
                "raw_byte_count": self._verify_raw_objects((), frozenset()),
                "semantic_entry_count": 0,
            }
        try:
            declarations = self.root / "declarations"
            current = json.loads((declarations / "current.json").read_text(encoding="utf-8"))
            universe = CareerSourceUniverse.model_validate(current)
            revision = self._read_declaration(universe.revision_id)
            if canonical_json_bytes(revision) != canonical_json_bytes(universe):
                raise ValueError
            capture_values = self._verify_current_captures()
            for capture in capture_values:
                self._verify_capture(capture.capture_id, ancestry=frozenset())
            output_hashes = self._verify_transformation_inventory()
            self._verify_migration_receipts(
                expected_workspace_commit=expected_workspace_commit,
                capture_values=capture_values,
            )
        except (
            CareerSourceError,
            OSError,
            ValueError,
            json.JSONDecodeError,
            ValidationError,
        ) as exc:
            if isinstance(exc, CareerSourceError):
                raise CareerSourceError("career-source-snapshot-invalid") from exc
            raise CareerSourceError("career-source-snapshot-invalid") from exc
        return {
            "candidate_only": True,
            "raw_byte_count": self._verify_raw_objects(capture_values, output_hashes),
            "semantic_entry_count": len(committed),
        }

    def _read_declaration(self, revision_id: str) -> CareerSourceUniverse:
        try:
            manifest = self.root / "declarations" / self._safe_id(revision_id) / "manifest.json"
            return CareerSourceUniverse.model_validate_json(manifest.read_bytes())
        except (OSError, ValueError, ValidationError) as exc:
            raise CareerSourceError("career-source-declaration-invalid") from exc
