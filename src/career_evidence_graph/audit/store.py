"""Trusted-local persistence for one resumable audit snapshot."""

from __future__ import annotations

import json
import os
import re
import stat
import tempfile
from pathlib import Path

from pydantic import ValidationError

from ..validation.hashing import canonical_json_bytes
from .models import AuditSnapshot


class AuditStorageError(RuntimeError):
    """Raised when an ordinary local snapshot operation cannot complete safely."""


_AUDIT_ID = re.compile(r"audit-[a-z0-9-]+$")


class AuditStore:
    """Store exactly one strict JSON snapshot for each trusted-local audit ID."""

    def __init__(self, workspace: Path) -> None:
        self.workspace = workspace

    @staticmethod
    def _safe(audit_id: str) -> None:
        if not _AUDIT_ID.fullmatch(audit_id):
            raise AuditStorageError("unsafe audit ID")

    @property
    def root(self) -> Path:
        return self.workspace / "audits"

    def path_for(self, audit_id: str) -> Path:
        self._safe(audit_id)
        path = self.root / f"{audit_id}.json"
        if path.parent != self.root:
            raise AuditStorageError("unsafe audit path")
        return path

    def path(self, audit_id: str) -> Path:
        """Return the canonical record path for diagnostics and tests."""
        return self.path_for(audit_id)

    def _ensure_root(self) -> Path:
        try:
            self.root.mkdir(mode=0o700, parents=True, exist_ok=True)
        except OSError as exc:
            raise AuditStorageError("audit workspace is unavailable") from exc
        if self.root.is_symlink() or not self.root.is_dir():
            raise AuditStorageError("audit root is directly linked or unsafe")
        return self.root

    @staticmethod
    def _admit_record(path: Path) -> None:
        try:
            info = path.lstat()
        except FileNotFoundError as exc:
            raise AuditStorageError("audit snapshot is missing") from exc
        except OSError as exc:
            raise AuditStorageError("audit snapshot is unavailable") from exc
        if stat.S_ISLNK(info.st_mode) or info.st_nlink != 1:
            raise AuditStorageError("audit snapshot is directly linked")
        if not stat.S_ISREG(info.st_mode):
            raise AuditStorageError("audit snapshot is unsafe")

    @staticmethod
    def _validate(snapshot: AuditSnapshot) -> AuditSnapshot:
        try:
            return AuditSnapshot.model_validate(snapshot.model_dump(mode="json"))
        except ValidationError as exc:
            raise AuditStorageError("audit snapshot is invalid") from exc

    @staticmethod
    def _snapshot_bytes(snapshot: AuditSnapshot) -> bytes:
        return canonical_json_bytes(snapshot.model_dump(mode="json")) + b"\n"

    @staticmethod
    def _atomic_replace(path: Path, data: bytes) -> None:
        descriptor = -1
        temporary_name: str | None = None
        try:
            descriptor, temporary_name = tempfile.mkstemp(
                dir=path.parent, prefix=f".{path.name}.", suffix=".tmp"
            )
            with os.fdopen(descriptor, "wb") as handle:
                descriptor = -1
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary_name, path)
            directory = os.open(path.parent, os.O_RDONLY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
        except OSError as exc:
            raise AuditStorageError("audit snapshot replacement failed") from exc
        finally:
            if descriptor >= 0:
                os.close(descriptor)
            if temporary_name is not None:
                Path(temporary_name).unlink(missing_ok=True)

    def create(self, snapshot: AuditSnapshot) -> None:
        snapshot = self._validate(snapshot)
        self._ensure_root()
        path = self.path_for(snapshot.audit_id)
        if path.is_symlink():
            raise AuditStorageError("audit snapshot is directly linked")
        if path.exists():
            raise AuditStorageError("audit snapshot already exists")
        self._atomic_replace(path, self._snapshot_bytes(snapshot))

    def read(self, audit_id: str) -> AuditSnapshot:
        self._ensure_root()
        path = self.path_for(audit_id)
        self._admit_record(path)
        try:
            snapshot = AuditSnapshot.model_validate_json(path.read_bytes())
        except (OSError, ValidationError, ValueError, json.JSONDecodeError) as exc:
            raise AuditStorageError("audit snapshot is corrupt") from exc
        if snapshot.audit_id != audit_id:
            raise AuditStorageError("audit snapshot ID does not match its record")
        return snapshot

    def replace(self, snapshot: AuditSnapshot) -> None:
        snapshot = self._validate(snapshot)
        self._ensure_root()
        path = self.path_for(snapshot.audit_id)
        self._admit_record(path)
        self._atomic_replace(path, self._snapshot_bytes(snapshot))
