"""Candidate-only, immutable custody for synthetic career-source inputs."""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from .domain.models import CareerSourceCapture, CareerSourceTransformation, CareerSourceUniverse
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
        self.root = self.workspace.child(".career-evidence", "sources")
        self.raw_root = self.workspace.child(".career-evidence", "raw")

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
        return self.root / "captures" / self._safe_id(capture_id)

    def _raw_path(self, content_hash: str) -> Path:
        return self.raw_root / content_hash.removeprefix("sha256:")

    def _read_capture(self, capture_id: str) -> CareerSourceCapture:
        bundle = self._capture_path(capture_id)
        manifest = bundle / "manifest.json"
        try:
            if bundle.is_symlink() or not bundle.is_dir():
                raise ValueError
            if {path.name for path in bundle.iterdir()} != {"manifest.json"}:
                raise ValueError
            value = json.loads(manifest.read_text(encoding="utf-8"))
            capture = CareerSourceCapture.model_validate(value)
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
            current = json.loads(
                (self.root / "declarations/current.json").read_text(encoding="utf-8")
            )
            universe = CareerSourceUniverse.model_validate(current)
            datetime.fromisoformat(capture.acquired_at)
        except (OSError, ValueError, json.JSONDecodeError, ValidationError) as exc:
            raise CareerSourceError("career-source-capture-lineage-invalid") from exc
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
            stored = CareerSourceCapture.model_validate(capture)
            capture_id = self._safe_id(stored.capture_id)
            if (
                not isinstance(source_bytes, bytes)
                or stored.content_hash != sha256_digest(source_bytes)
            ):
                raise ValueError
        except (TypeError, ValueError) as exc:
            raise CareerSourceError("career-source-capture-invalid") from exc
        self._ensure_root()
        captures = self.root / "captures"
        captures.mkdir(exist_ok=True)
        try:
            current = json.loads(
                (self.root / "declarations/current.json").read_text(encoding="utf-8")
            )
            universe = CareerSourceUniverse.model_validate(current)
        except (OSError, json.JSONDecodeError, ValidationError) as exc:
            raise CareerSourceError("career-source-declaration-invalid") from exc
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
            current_root = self.root / "current-captures"
            current_root.mkdir(exist_ok=True)
            atomic_write_canonical_json(
                current_root / f"{stored.source_id}.json", {"capture_id": stored.capture_id}
            )
        except (FormalRunStorageError, OSError) as exc:
            raise CareerSourceError("career-source-capture-already-exists") from exc
        return stored.model_dump(mode="json")

    def verify_capture(self, capture: dict[str, Any]) -> None:
        try:
            expected = CareerSourceCapture.model_validate(capture)
            stored = self._verify_capture(expected.capture_id, ancestry=frozenset())
        except (TypeError, ValueError) as exc:
            raise CareerSourceError("career-source-capture-invalid") from exc
        if canonical_json_bytes(stored) != canonical_json_bytes(expected):
            raise CareerSourceError("career-source-capture-lineage-invalid")

    def transform(self, transformation: dict[str, Any]) -> dict[str, Any]:
        try:
            stored = CareerSourceTransformation.model_validate(transformation)
            transformation_id = self._safe_id(stored.transformation_id)
            capture = self._verify_capture(stored.input_capture_id, ancestry=frozenset())
            if capture.content_hash != stored.input_hash:
                raise ValueError
        except (TypeError, ValueError) as exc:
            raise CareerSourceError("career-source-transformation-invalid") from exc
        self._ensure_root()
        transformations = self.root / "transformations"
        transformations.mkdir(exist_ok=True)
        try:
            create_only_canonical_bundle(
                transformations,
                transformation_id,
                {"manifest.json": stored.model_dump(mode="json")},
            )
        except FormalRunStorageError as exc:
            raise CareerSourceError("career-source-transformation-already-exists") from exc
        return stored.model_dump(mode="json")

    def verify_transformation(self, transformation: dict[str, Any]) -> None:
        try:
            expected = CareerSourceTransformation.model_validate(transformation)
            manifest = self.root / "transformations" / expected.transformation_id / "manifest.json"
            stored = CareerSourceTransformation.model_validate(
                json.loads(manifest.read_text(encoding="utf-8"))
            )
            capture = self._verify_capture(stored.input_capture_id, ancestry=frozenset())
        except (OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise CareerSourceError("career-source-transformation-invalid") from exc
        if (
            manifest.is_symlink()
            or stored.transformation_id != expected.transformation_id
            or capture.content_hash != stored.input_hash
            or canonical_json_bytes(stored) != canonical_json_bytes(expected)
        ):
            raise CareerSourceError("career-source-transformation-lineage-invalid")

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
            "schema_version": "career-source-capture/v1",
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

    def prepare_raw_vault(self) -> Path:
        """Create the ignored raw boundary only after full symlink checks."""
        self._ensure_root()
        return self.raw_root

    def safe_status(self) -> dict[str, object]:
        if not self.root.exists():
            return {
                "candidate_only": True,
                "capture_count": 0,
                "declaration_present": False,
                "source_revision_count": 0,
                "transformation_count": 0,
            }
        captures = self.root / "captures"
        transformations = self.root / "transformations"
        return {
            "candidate_only": True,
            "capture_count": len(tuple(captures.glob("*"))) if captures.is_dir() else 0,
            "declaration_present": (self.root / "declarations" / "current.json").is_file(),
            "transformation_count": (
                len(tuple(transformations.glob("*"))) if transformations.is_dir() else 0
            ),
        }
