from __future__ import annotations

import json
import os
import re
import tempfile
from pathlib import Path
from typing import Any

from ..validation.hashing import canonical_json_bytes, sha256_digest
from .models import AuditSnapshot


class AuditStorageError(RuntimeError):
    pass


class AuditStore:
    def __init__(self, workspace: Path) -> None:
        if workspace.is_symlink():
            raise AuditStorageError("workspace path is unsafe")
        self.root = workspace.resolve() / "audits"

    @staticmethod
    def _safe(audit_id: str) -> None:
        if not re.fullmatch(r"audit-[a-z0-9-]+", audit_id):
            raise AuditStorageError("unsafe audit_id")

    def path(self, audit_id: str) -> Path:
        self._safe(audit_id)
        return self.root / audit_id

    def save(self, snapshot: AuditSnapshot) -> None:
        destination = self.path(snapshot.audit_id)
        self.root.mkdir(parents=True, exist_ok=True)
        if destination.exists():
            raise AuditStorageError("audit already exists")
        temporary = Path(tempfile.mkdtemp(dir=self.root, prefix=f".{snapshot.audit_id}."))
        try:
            data = canonical_json_bytes(snapshot.model_dump(mode="json")) + b"\n"
            fd, name = tempfile.mkstemp(dir=temporary, prefix="snapshot.")
            with os.fdopen(fd, "wb") as handle:
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(name, temporary / "snapshot.json")
            (temporary / "events.jsonl").write_text(
                json.dumps({"hash": sha256_digest(data), "event": "created"}, sort_keys=True)
                + "\n",
                encoding="utf-8",
            )
            os.rename(temporary, destination)
        except FileExistsError as exc:
            raise AuditStorageError("audit already exists") from exc
        finally:
            if temporary.exists():
                for child in temporary.iterdir():
                    child.unlink(missing_ok=True)
                temporary.rmdir()

    def read(self, audit_id: str) -> AuditSnapshot:
        path = self.path(audit_id)
        if path.is_symlink() or not path.is_dir() or path.resolve().parent != self.root.resolve():
            raise AuditStorageError("audit path is unsafe")
        try:
            value: Any = json.loads((path / "snapshot.json").read_text(encoding="utf-8"))
            snapshot = AuditSnapshot.model_validate(value)
            events = (path / "events.jsonl").read_text(encoding="utf-8")
            event_lines = events.splitlines()
            if not event_lines:
                raise AuditStorageError("audit event chain is empty")
            records = [json.loads(line) for line in event_lines]
            if any("hash" not in record or "event" not in record for record in records):
                raise AuditStorageError("audit event chain is corrupt")
            expected = records[-1]["hash"]
            actual = sha256_digest(canonical_json_bytes(value) + b"\n")
            if expected != actual:
                raise AuditStorageError("audit snapshot hash mismatch")
            return snapshot
        except (OSError, json.JSONDecodeError, KeyError, ValueError) as exc:
            raise AuditStorageError("audit snapshot is corrupt") from exc

    def latest_event_hash(self, audit_id: str) -> str:
        path = self.path(audit_id)
        if path.is_symlink() or not path.is_dir() or path.resolve().parent != self.root.resolve():
            raise AuditStorageError("audit path is unsafe")
        try:
            raw = (path / "events.jsonl").read_bytes()
            lines = raw.splitlines()
            if not lines:
                raise AuditStorageError("audit event chain is empty")
            record = json.loads(lines[-1])
            if "hash" not in record or "event" not in record:
                raise AuditStorageError("audit event chain is corrupt")
            return sha256_digest(lines[-1] + b"\n")
        except (OSError, json.JSONDecodeError, KeyError) as exc:
            raise AuditStorageError("audit event chain is corrupt") from exc

    def update(self, snapshot: AuditSnapshot, *, expected_event_hash: str | None = None) -> None:
        path = self.path(snapshot.audit_id)
        if not path.is_dir():
            raise AuditStorageError("audit does not exist")
        if (
            expected_event_hash is not None
            and self.latest_event_hash(snapshot.audit_id) != expected_event_hash
        ):
            raise AuditStorageError("stale expected event hash")
        data = canonical_json_bytes(snapshot.model_dump(mode="json")) + b"\n"
        fd, name = tempfile.mkstemp(dir=path, prefix="snapshot.")
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(name, path / "snapshot.json")
            record = {"event": "updated", "hash": sha256_digest(data)}
            with (path / "events.jsonl").open("a", encoding="utf-8") as events:
                events.write(json.dumps(record, sort_keys=True) + "\n")
        finally:
            Path(name).unlink(missing_ok=True)
