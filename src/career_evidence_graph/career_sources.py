"""Candidate-only, immutable custody for synthetic career-source inputs."""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

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
            revision_id = self._safe_id(str(declaration["revision_id"]))
            categories = tuple(declaration["categories"])
            sources = tuple(declaration["sources"])
            if not categories or not sources or declaration.get("authority") != "candidate-only":
                raise ValueError
            category_ids = [self._safe_id(str(item["category_id"])) for item in categories]
            source_ids = [self._safe_id(str(item["source_id"])) for item in sources]
            if (
                len(category_ids) != len(set(category_ids))
                or len(source_ids) != len(set(source_ids))
            ):
                raise ValueError
            if any(str(item["category_id"]) not in category_ids for item in sources):
                raise ValueError
        except (KeyError, TypeError, ValueError) as exc:
            raise CareerSourceError("career-source-declaration-invalid") from exc
        self._ensure_root()
        declarations = self.root / "declarations"
        declarations.mkdir(exist_ok=True)
        try:
            create_only_canonical_bundle(declarations, revision_id, {"manifest.json": declaration})
            atomic_write_canonical_json(declarations / "current.json", declaration)
        except FormalRunStorageError as exc:
            raise CareerSourceError("career-source-declaration-already-exists") from exc
        return {
            "authority": "candidate-only",
            "created_skill_count": 0,
            "unavailable_source_count": sum(
                item.get("availability") != "available" for item in sources
            ),
        }

    def _capture_path(self, capture_id: str) -> Path:
        return self.root / "captures" / self._safe_id(capture_id)

    def capture(self, capture: dict[str, Any], source_bytes: bytes) -> dict[str, Any]:
        try:
            capture_id = self._safe_id(str(capture["capture_id"]))
            self._safe_id(str(capture["source_id"]))
            if capture.get("authority") != "candidate-only" or not isinstance(source_bytes, bytes):
                raise ValueError
        except (KeyError, TypeError, ValueError) as exc:
            raise CareerSourceError("career-source-capture-invalid") from exc
        self._ensure_root()
        captures = self.root / "captures"
        captures.mkdir(exist_ok=True)
        raw_path = self.raw_root / capture_id
        if raw_path.exists() or raw_path.is_symlink():
            raise CareerSourceError("career-source-capture-already-exists")
        manifest = dict(capture)
        manifest["content_hash"] = manifest.get("content_hash") or sha256_digest(source_bytes)
        try:
            create_only_canonical_bundle(captures, capture_id, {"manifest.json": manifest})
            raw_path.write_bytes(source_bytes)
        except (FormalRunStorageError, OSError) as exc:
            raise CareerSourceError("career-source-capture-already-exists") from exc
        return manifest

    def verify_capture(self, capture: dict[str, Any]) -> None:
        capture_id = self._safe_id(str(capture.get("capture_id", "")))
        path = self._capture_path(capture_id) / "manifest.json"
        try:
            stored = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise CareerSourceError("career-source-capture-invalid") from exc
        if canonical_json_bytes(stored) != canonical_json_bytes(capture):
            raise CareerSourceError("career-source-capture-lineage-invalid")

    def transform(self, transformation: dict[str, Any]) -> dict[str, Any]:
        try:
            transformation_id = self._safe_id(str(transformation["transformation_id"]))
            capture_id = self._safe_id(str(transformation["input_capture_id"]))
            if (
                transformation.get("authority") != "candidate-only"
                or not self._capture_path(capture_id).is_dir()
            ):
                raise ValueError
        except (KeyError, TypeError, ValueError) as exc:
            raise CareerSourceError("career-source-transformation-invalid") from exc
        self._ensure_root()
        transformations = self.root / "transformations"
        transformations.mkdir(exist_ok=True)
        try:
            create_only_canonical_bundle(
                transformations, transformation_id, {"manifest.json": transformation}
            )
        except FormalRunStorageError as exc:
            raise CareerSourceError("career-source-transformation-already-exists") from exc
        return transformation

    def verify_transformation(self, transformation: dict[str, Any]) -> None:
        transformation_id = self._safe_id(str(transformation.get("transformation_id", "")))
        try:
            stored = json.loads(
                (self.root / "transformations" / transformation_id / "manifest.json").read_text()
            )
        except (OSError, json.JSONDecodeError) as exc:
            raise CareerSourceError("career-source-transformation-invalid") from exc
        if canonical_json_bytes(stored) != canonical_json_bytes(transformation):
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
