"""Immutable filesystem storage for narrow offline formal-run bundles."""

from __future__ import annotations

import json
import os
import re
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from .hashing import canonical_json_bytes, sha256_digest
from .models import FormalRunManifest, ValidationCharter

RUN_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
PAYLOAD_FILES = ("raw_response.json", "proposal.json", "expected_result.json")


class FormalRunStorageError(RuntimeError):
    """Raised when a formal bundle cannot be safely created or verified."""


def _load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise FormalRunStorageError(f"cannot read valid JSON from {path.name}") from exc


def load_charter(path: Path) -> ValidationCharter:
    """Load a charter using its strict schema."""
    try:
        return ValidationCharter.model_validate(_load_json(path.resolve(strict=True)))
    except (OSError, ValidationError) as exc:
        raise FormalRunStorageError("invalid validation charter") from exc


class FormalRunStore:
    """Create and verify bundles under one resolved workspace boundary."""

    def __init__(self, workspace: Path) -> None:
        self.workspace = workspace.resolve()
        self.runs_root = self.workspace / "formal-runs"

    def _run_path(self, run_id: str) -> Path:
        if not RUN_ID_PATTERN.fullmatch(run_id):
            raise FormalRunStorageError("run_id contains unsafe path characters")
        candidate = (self.runs_root / run_id).resolve()
        if candidate.parent != self.runs_root.resolve():
            raise FormalRunStorageError("run destination escapes the formal-runs root")
        return candidate

    @staticmethod
    def _write_json(path: Path, value: Any) -> None:
        data = canonical_json_bytes(value) + b"\n"
        path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary_name = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.")
        try:
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary_name, path)
        except BaseException:
            Path(temporary_name).unlink(missing_ok=True)
            raise

    def create(
        self,
        *,
        run_id: str,
        charter: ValidationCharter,
        raw_response: Any,
        proposal: Any,
        expected_result: Any,
    ) -> FormalRunManifest:
        """Atomically publish a new immutable offline tracer bundle."""
        destination = self._run_path(run_id)
        self.runs_root.mkdir(parents=True, exist_ok=True)
        if destination.exists():
            raise FormalRunStorageError(f"formal run already exists: {run_id}")

        temporary = Path(tempfile.mkdtemp(dir=self.runs_root, prefix=f".{run_id}."))
        try:
            values = {
                "raw_response.json": raw_response,
                "proposal.json": proposal,
                "expected_result.json": expected_result,
            }
            manifest_hashes: dict[str, str] = {}
            for filename, value in values.items():
                self._write_json(temporary / filename, value)
                manifest_hashes[filename] = sha256_digest((temporary / filename).read_bytes())
            manifest = FormalRunManifest(
                schema_version="formal-run/v1",
                run_id=run_id,
                run_kind="synthetic-offline-tracer",
                created_at=datetime.now(UTC),
                charter_version=charter.charter_version,
                input_hashes={
                    "charter": sha256_digest(canonical_json_bytes(charter)),
                },
                content_manifest=manifest_hashes,
                replay_mode="exact-recorded-response",
            )
            self._write_json(temporary / "manifest.json", manifest)
            try:
                os.rename(temporary, destination)
            except FileExistsError as exc:
                raise FormalRunStorageError(f"formal run already exists: {run_id}") from exc
            return manifest
        finally:
            if temporary.exists():
                for child in temporary.iterdir():
                    child.unlink()
                temporary.rmdir()

    def verify(self, run_id: str) -> FormalRunManifest:
        """Fail closed unless all declared bundle bytes match their manifest."""
        run_path = self._run_path(run_id)
        if not run_path.is_dir() or run_path.is_symlink():
            raise FormalRunStorageError(f"formal run does not exist safely: {run_id}")
        try:
            manifest = FormalRunManifest.model_validate(_load_json(run_path / "manifest.json"))
        except ValidationError as exc:
            raise FormalRunStorageError("formal run manifest is invalid") from exc
        if manifest.run_id != run_id:
            raise FormalRunStorageError("manifest run_id does not match its directory")
        if set(manifest.content_manifest) != set(PAYLOAD_FILES):
            raise FormalRunStorageError("manifest does not declare the exact payload set")
        for filename, expected_hash in manifest.content_manifest.items():
            payload_path = (run_path / filename).resolve(strict=True)
            if payload_path.parent != run_path.resolve() or payload_path.is_symlink():
                raise FormalRunStorageError("payload path escapes or aliases the run directory")
            if sha256_digest(payload_path.read_bytes()) != expected_hash:
                raise FormalRunStorageError(f"payload hash mismatch: {filename}")
        return manifest

    def payload(self, run_id: str, filename: str) -> Any:
        """Return a verified declared payload."""
        manifest = self.verify(run_id)
        if filename not in manifest.content_manifest:
            raise FormalRunStorageError("undeclared payload requested")
        return _load_json(self._run_path(run_id) / filename)
