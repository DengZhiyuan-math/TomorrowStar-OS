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
            expected = json.loads(events.splitlines()[-1])["hash"]
            actual = sha256_digest(canonical_json_bytes(value) + b"\n")
            if expected != actual:
                raise AuditStorageError("audit snapshot hash mismatch")
            return snapshot
        except (OSError, json.JSONDecodeError, KeyError, ValueError) as exc:
            raise AuditStorageError("audit snapshot is corrupt") from exc

    def update(self, snapshot: AuditSnapshot) -> None:
        path = self.path(snapshot.audit_id)
        if not path.is_dir():
            raise AuditStorageError("audit does not exist")
        data = canonical_json_bytes(snapshot.model_dump(mode="json")) + b"\n"
        fd, name = tempfile.mkstemp(dir=path, prefix="snapshot.")
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(name, path / "snapshot.json")
            with (path / "events.jsonl").open("a", encoding="utf-8") as events:
                events.write(
                    json.dumps({"hash": sha256_digest(data), "event": "updated"}, sort_keys=True)
                    + "\n"
                )
        finally:
            Path(name).unlink(missing_ok=True)
