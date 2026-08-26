# ruff: noqa: E501

from __future__ import annotations

import fcntl
import json
import os
import re
import tempfile
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path

from ..validation.hashing import canonical_json_bytes, sha256_digest
from .models import AcceptedActionResult, AuditAction, AuditEventRecord, AuditSnapshot


class AuditStorageError(RuntimeError):
    pass


class AuditStore:
    """One locked, verified authority for snapshots, event history, and replay results."""

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

    @contextmanager
    def _locked(self, audit_id: str) -> Iterator[None]:
        self._safe(audit_id)
        locks = self.root / ".locks"
        locks.mkdir(parents=True, exist_ok=True)
        lock = locks / f"{audit_id}.lock"
        if lock.is_symlink():
            raise AuditStorageError("audit lock is unsafe")
        if not lock.exists():
            fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            os.close(fd)
        os.chmod(lock, 0o600)
        with lock.open("a+b") as handle:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)

    @staticmethod
    def _snapshot_hash(snapshot: AuditSnapshot) -> str:
        return sha256_digest(canonical_json_bytes(snapshot.model_dump(mode="json")))

    @staticmethod
    def _snapshot_bytes(snapshot: AuditSnapshot) -> bytes:
        return canonical_json_bytes(snapshot.model_dump(mode="json")) + b"\n"

    @staticmethod
    def _atomic(path: Path, data: bytes) -> None:
        fd, temporary = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.")
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, path)
            directory = os.open(path.parent, os.O_RDONLY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
        finally:
            Path(temporary).unlink(missing_ok=True)

    def _audit_path(self, audit_id: str) -> Path:
        path = self.path(audit_id)
        if path.is_symlink() or not path.is_dir() or path.resolve().parent != self.root.resolve():
            raise AuditStorageError("audit path is unsafe")
        return path

    def _recover_locked(self, path: Path) -> None:
        journal = path / "publication-journal.json"
        if not journal.exists():
            return
        try:
            staged = json.loads(journal.read_bytes())
            for name in ("snapshot.json", "events.jsonl", "accepted-results.json"):
                self._atomic(path / name, bytes.fromhex(staged[name]))
        except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
            raise AuditStorageError("audit publication journal is corrupt") from exc
        journal.unlink()

    def _publish_locked(self, path: Path, snapshot: bytes, events: bytes, results: bytes) -> None:
        journal = path / "publication-journal.json"
        staged = {
            "snapshot.json": snapshot.hex(),
            "events.jsonl": events.hex(),
            "accepted-results.json": results.hex(),
        }
        self._atomic(journal, canonical_json_bytes(staged) + b"\n")
        self._recover_locked(path)

    def _read_locked(
        self, audit_id: str
    ) -> tuple[AuditSnapshot, list[AuditEventRecord], dict[str, AcceptedActionResult]]:
        path = self._audit_path(audit_id)
        try:
            self._recover_locked(path)
            snapshot = AuditSnapshot.model_validate_json((path / "snapshot.json").read_bytes())
            lines = (path / "events.jsonl").read_bytes().splitlines()
            if not lines:
                raise AuditStorageError("audit event chain is empty")
            events = [AuditEventRecord.model_validate_json(line) for line in lines]
            for sequence, event in enumerate(events):
                if event.sequence != sequence or (
                    sequence and event.prev_event_hash != events[sequence - 1].event_hash
                ):
                    raise AuditStorageError("audit event chain is corrupt")
            if events[-1].snapshot_hash != self._snapshot_hash(snapshot):
                raise AuditStorageError("audit snapshot hash mismatch")
            raw_results = json.loads((path / "accepted-results.json").read_bytes())
            if not isinstance(raw_results, list):
                raise AuditStorageError("accepted result index is corrupt")
            results = {
                item.action_id: item
                for item in map(AcceptedActionResult.model_validate, raw_results)
            }
            if len(results) != len(raw_results):
                raise AuditStorageError("accepted action IDs are duplicated")
            if set(results) != {event.action_id for event in events}:
                raise AuditStorageError("accepted result index is incomplete")
            by_hash = {event.event_hash: event for event in events}
            for result in results.values():
                event = by_hash.get(result.event_hash)
                if (
                    event is None
                    or event.action_id != result.action_id
                    or event.action_digest != result.action_digest
                    or event.snapshot_hash != result.result_snapshot_hash
                ):
                    raise AuditStorageError("accepted result is not event anchored")
            return snapshot, events, results
        except (OSError, ValueError, json.JSONDecodeError, TypeError) as exc:
            if isinstance(exc, AuditStorageError):
                raise
            raise AuditStorageError("audit snapshot is corrupt") from exc

    def save(self, snapshot: AuditSnapshot, *, action_id: str | None = None) -> None:
        action_id = action_id or f"start-{snapshot.audit_id.removeprefix('audit-')}"
        with self._locked(snapshot.audit_id):
            target = self.path(snapshot.audit_id)
            if target.exists():
                raise AuditStorageError("audit already exists")
            self.root.mkdir(parents=True, exist_ok=True)
            target.mkdir(mode=0o700)
            digest = sha256_digest(canonical_json_bytes({"action": "start"}))
            event = AuditEventRecord.create(
                sequence=0,
                action_type="start",
                action_id=action_id,
                action_digest=digest,
                snapshot_hash=self._snapshot_hash(snapshot),
                prev_event_hash=None,
            )
            result = AcceptedActionResult(
                action_id=action_id,
                action_digest=digest,
                event_hash=event.event_hash,
                result_snapshot_hash=event.snapshot_hash,
                result_snapshot=snapshot.model_dump(mode="json"),
            )
            self._publish_locked(
                target,
                self._snapshot_bytes(snapshot),
                canonical_json_bytes(event.model_dump(mode="json")) + b"\n",
                canonical_json_bytes([result.model_dump(mode="json")]) + b"\n",
            )

    def read_versioned(self, audit_id: str) -> tuple[AuditSnapshot, str]:
        with self._locked(audit_id):
            snapshot, events, _ = self._read_locked(audit_id)
            return snapshot, events[-1].event_hash

    def read(self, audit_id: str) -> AuditSnapshot:
        return self.read_versioned(audit_id)[0]

    def latest_event_hash(self, audit_id: str) -> str:
        return self.read_versioned(audit_id)[1]

    def transact(
        self,
        audit_id: str,
        action: AuditAction,
        transition: Callable[[AuditSnapshot], AuditSnapshot],
    ) -> tuple[AuditSnapshot, bool]:
        if not action.action_id or not action.expected_event_hash:
            raise AuditStorageError("audit action ID and expected event hash are required")
        with self._locked(audit_id):
            snapshot, events, results = self._read_locked(audit_id)
            digest = action.semantic_digest()
            old = results.get(action.action_id)
            if old:
                if old.action_digest != digest:
                    raise AuditStorageError("audit action ID digest collision")
                return AuditSnapshot.model_validate(old.result_snapshot), True
            if action.expected_event_hash != events[-1].event_hash:
                raise AuditStorageError("stale expected event hash")
            updated = transition(snapshot)
            event = AuditEventRecord.create(
                sequence=len(events),
                action_type=action.action,
                action_id=action.action_id,
                action_digest=digest,
                snapshot_hash=self._snapshot_hash(updated),
                prev_event_hash=events[-1].event_hash,
            )
            result = AcceptedActionResult(
                action_id=action.action_id,
                action_digest=digest,
                event_hash=event.event_hash,
                result_snapshot_hash=event.snapshot_hash,
                result_snapshot=updated.model_dump(mode="json"),
            )
            path = self._audit_path(audit_id)
            event_bytes = (
                (path / "events.jsonl").read_bytes()
                + canonical_json_bytes(event.model_dump(mode="json"))
                + b"\n"
            )
            all_results = [item.model_dump(mode="json") for item in results.values()] + [
                result.model_dump(mode="json")
            ]
            self._publish_locked(
                path,
                self._snapshot_bytes(updated),
                event_bytes,
                canonical_json_bytes(all_results) + b"\n",
            )
            return updated, False

    def update(self, snapshot: AuditSnapshot, *, expected_event_hash: str | None = None) -> None:
        """Compatibility for existing direct workflow tests; CLI always calls transact."""
        head = expected_event_hash or self.latest_event_hash(snapshot.audit_id)
        action = AuditAction(
            action="answer",
            answer="legacy update",
            action_id=f"legacy-{self._snapshot_hash(snapshot)[7:19]}",
            expected_event_hash=head,
        )
        self.transact(snapshot.audit_id, action, lambda _current: snapshot)
