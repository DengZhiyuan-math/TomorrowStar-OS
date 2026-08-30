"""Candidate-only, immutable custody for synthetic career-source inputs."""

from __future__ import annotations

import json
import re
import subprocess
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
_GIT_OID_LENGTHS = {"sha1": 40, "sha256": 64}
_SEMANTIC_NAMESPACES = (
    ("declaration-manifests", re.compile(r"declarations/[a-z][a-z0-9._-]*/manifest\.json")),
    ("declaration-current", re.compile(r"declarations/current\.json")),
    ("capture-manifests", re.compile(r"captures/[a-z][a-z0-9._-]*/manifest\.json")),
    ("current-captures", re.compile(r"current-captures/[a-z][a-z0-9._-]*\.json")),
    ("transformation-manifests", re.compile(r"transformations/[a-z][a-z0-9._-]*/manifest\.json")),
    ("migration-receipts", re.compile(r"migration-receipts/[a-z][a-z0-9._-]*/manifest\.json")),
    ("derived-outputs", re.compile(r"derived-outputs/[a-z][a-z0-9._-]*/manifest\.json")),
)


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
            if not isinstance(source_bytes, bytes) or stored.content_hash != sha256_digest(
                source_bytes
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

    def _git(self, *args: str) -> bytes:
        """Run a redacted Git query only in the selected private workspace."""
        try:
            completed = subprocess.run(
                ["git", *args],
                cwd=self.workspace.root,
                check=False,
                capture_output=True,
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
            object_type = self._git("cat-file", "-t", expected_workspace_commit).decode(
                "ascii"
            ).strip()
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
        return any(pattern.fullmatch(relative) for _, pattern in _SEMANTIC_NAMESPACES)

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
            and _SAFE_ID.fullmatch(parts[1]) is not None
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
        capture_values = tuple(
            self._read_capture(path.name) for path in captures.iterdir()
        ) if captures.exists() else ()
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
                if set(value) != {"capture_id"} or not isinstance(value["capture_id"], str):
                    raise ValueError
                capture = self._read_capture(value["capture_id"])
                if capture.source_id != source_id:
                    raise ValueError
                actual_sources.add(source_id)
        except (OSError, ValueError, json.JSONDecodeError, CareerSourceError) as exc:
            raise CareerSourceError("career-source-snapshot-invalid") from exc
        if actual_sources != expected_sources:
            raise CareerSourceError("career-source-snapshot-invalid")
        return capture_values

    def _verify_raw_objects(self, captures: tuple[CareerSourceCapture, ...]) -> int:
        expected = {capture.content_hash.removeprefix("sha256:") for capture in captures}
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

    def verify(self, *, expected_workspace_commit: str) -> dict[str, object]:
        """Authenticate the current source snapshot against one exact Git commit."""
        committed = self._commit_blob_inventory(expected_workspace_commit)
        working = self._working_blob_inventory()
        if committed != working:
            raise CareerSourceError("career-source-snapshot-invalid")
        if not committed:
            return {
                "candidate_only": True,
                "raw_byte_count": self._verify_raw_objects(()),
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
            transformations = self.root / "transformations"
            if transformations.exists():
                if transformations.is_symlink() or not transformations.is_dir():
                    raise ValueError
                for path in transformations.iterdir():
                    if path.is_symlink() or not path.is_dir():
                        raise ValueError
                    self.verify_transformation(
                        json.loads((path / "manifest.json").read_text(encoding="utf-8"))
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
            "raw_byte_count": self._verify_raw_objects(capture_values),
            "semantic_entry_count": len(committed),
        }

    def _read_declaration(self, revision_id: str) -> CareerSourceUniverse:
        try:
            manifest = self.root / "declarations" / self._safe_id(revision_id) / "manifest.json"
            return CareerSourceUniverse.model_validate_json(manifest.read_bytes())
        except (OSError, ValueError, ValidationError) as exc:
            raise CareerSourceError("career-source-declaration-invalid") from exc
