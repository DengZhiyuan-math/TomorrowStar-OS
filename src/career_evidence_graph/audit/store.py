# ruff: noqa: E501

from __future__ import annotations

import fcntl
import json
import os
import re
import secrets
import stat
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path

from ..validation.hashing import canonical_json_bytes, sha256_digest
from .models import AcceptedActionResult, AuditAction, AuditEventRecord, AuditSnapshot


class AuditStorageError(RuntimeError):
    pass


_DIR_FLAGS = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
_READ_FLAGS = os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC
_WRITE_FLAGS = os.O_RDWR | os.O_NOFOLLOW | os.O_CLOEXEC


class AuditStore:
    """One descriptor-anchored authority for snapshots, events, and replay results."""

    def __init__(self, workspace: Path) -> None:
        self.workspace = workspace

    @staticmethod
    def _safe(audit_id: str) -> None:
        if not re.fullmatch(r"audit-[a-z0-9-]+", audit_id):
            raise AuditStorageError("unsafe audit_id")

    @staticmethod
    def _same_inode(left: os.stat_result, right: os.stat_result) -> bool:
        return (left.st_dev, left.st_ino) == (right.st_dev, right.st_ino)

    @staticmethod
    def _admit_regular(fd: int, *, label: str) -> None:
        info = os.fstat(fd)
        unsafe_mode = info.st_mode & (stat.S_ISUID | stat.S_ISGID | stat.S_IWGRP | stat.S_IWOTH)
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_uid != os.geteuid()
            or info.st_nlink != 1
            or unsafe_mode
        ):
            raise AuditStorageError(f"{label} is unsafe")

    @staticmethod
    def _admit_new_regular(fd: int, *, label: str) -> None:
        AuditStore._admit_regular(fd, label=label)
        if stat.S_IMODE(os.fstat(fd).st_mode) != 0o600:
            raise AuditStorageError(f"{label} is unsafe")

    @staticmethod
    def _binding(parent_fd: int, name: str, child_fd: int, *, label: str) -> None:
        try:
            entry = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
        except OSError as exc:
            raise AuditStorageError(f"{label} binding changed") from exc
        if not AuditStore._same_inode(entry, os.fstat(child_fd)):
            raise AuditStorageError(f"{label} binding changed")

    @staticmethod
    def _mkdir_open(parent_fd: int, name: str, *, label: str) -> int:
        try:
            try:
                os.mkdir(name, mode=0o700, dir_fd=parent_fd)
                os.fsync(parent_fd)
            except FileExistsError:
                pass
            fd = os.open(name, _DIR_FLAGS, dir_fd=parent_fd)
        except OSError as exc:
            raise AuditStorageError(f"{label} is unsafe") from exc
        try:
            AuditStore._binding(parent_fd, name, fd, label=label)
            return fd
        except BaseException:
            os.close(fd)
            raise

    @staticmethod
    def _open_dir(parent_fd: int, name: str, *, label: str) -> int:
        try:
            fd = os.open(name, _DIR_FLAGS, dir_fd=parent_fd)
        except OSError as exc:
            raise AuditStorageError(f"{label} is unsafe") from exc
        try:
            AuditStore._binding(parent_fd, name, fd, label=label)
            return fd
        except BaseException:
            os.close(fd)
            raise

    @contextmanager
    def _root_session(self) -> Iterator[tuple[int, int]]:
        """Hold workspace and audits identities for one public operation."""
        try:
            self.workspace.mkdir(mode=0o700, parents=True, exist_ok=True)
            workspace_fd = os.open(self.workspace, _DIR_FLAGS)
        except OSError as exc:
            raise AuditStorageError("workspace path is unsafe") from exc
        try:
            root_fd = self._mkdir_open(workspace_fd, "audits", label="audit root")
            try:
                self._binding(workspace_fd, "audits", root_fd, label="audit root")
                yield workspace_fd, root_fd
                self._binding(workspace_fd, "audits", root_fd, label="audit root")
            finally:
                os.close(root_fd)
        finally:
            os.close(workspace_fd)

    def _assert_root(self, workspace_fd: int, root_fd: int) -> None:
        self._binding(workspace_fd, "audits", root_fd, label="audit root")

    def _assert_audit(self, root_fd: int, audit_id: str, audit_fd: int) -> None:
        self._binding(root_fd, audit_id, audit_fd, label="audit path")

    def path(self, audit_id: str) -> Path:
        """Return a checked diagnostic locator; production operations keep descriptors."""
        self._safe(audit_id)
        with self._root_session() as (workspace_fd, root_fd):
            audit_fd = self._open_dir(root_fd, audit_id, label="audit path")
            try:
                self._assert_root(workspace_fd, root_fd)
                self._assert_audit(root_fd, audit_id, audit_fd)
            finally:
                os.close(audit_fd)
        return self.workspace / "audits" / audit_id

    @contextmanager
    def _locked(self, audit_id: str) -> Iterator[tuple[int, int]]:
        self._safe(audit_id)
        with self._root_session() as (workspace_fd, root_fd):
            self._assert_root(workspace_fd, root_fd)
            locks_fd = self._mkdir_open(root_fd, ".locks", label="audit locks")
            try:
                self._assert_root(workspace_fd, root_fd)
                lock_name = f"{audit_id}.lock"
                try:
                    lock_fd = os.open(
                        lock_name,
                        _WRITE_FLAGS | os.O_CREAT | os.O_EXCL,
                        0o600,
                        dir_fd=locks_fd,
                    )
                    self._admit_new_regular(lock_fd, label="audit lock")
                except FileExistsError:
                    try:
                        lock_fd = os.open(lock_name, _WRITE_FLAGS, dir_fd=locks_fd)
                    except OSError as exc:
                        raise AuditStorageError("audit lock is unsafe") from exc
                    self._admit_regular(lock_fd, label="audit lock")
                except OSError as exc:
                    raise AuditStorageError("audit lock is unsafe") from exc
                try:
                    self._binding(locks_fd, lock_name, lock_fd, label="audit lock")
                    self._admit_regular(lock_fd, label="audit lock")
                    fcntl.flock(lock_fd, fcntl.LOCK_EX)
                    try:
                        self._assert_root(workspace_fd, root_fd)
                        self._admit_regular(lock_fd, label="audit lock")
                        yield workspace_fd, root_fd
                        self._assert_root(workspace_fd, root_fd)
                        self._binding(locks_fd, lock_name, lock_fd, label="audit lock")
                        self._admit_regular(lock_fd, label="audit lock")
                    finally:
                        fcntl.flock(lock_fd, fcntl.LOCK_UN)
                finally:
                    os.close(lock_fd)
            finally:
                os.close(locks_fd)

    @staticmethod
    def _snapshot_hash(snapshot: AuditSnapshot) -> str:
        return sha256_digest(canonical_json_bytes(snapshot.model_dump(mode="json")))

    @staticmethod
    def _snapshot_bytes(snapshot: AuditSnapshot) -> bytes:
        return canonical_json_bytes(snapshot.model_dump(mode="json")) + b"\n"

    @staticmethod
    def _read_file(audit_fd: int, name: str) -> bytes:
        try:
            fd = os.open(name, _READ_FLAGS, dir_fd=audit_fd)
        except OSError as exc:
            raise AuditStorageError("audit file is unsafe") from exc
        try:
            AuditStore._admit_regular(fd, label="audit file")
            chunks: list[bytes] = []
            while block := os.read(fd, 65536):
                chunks.append(block)
            AuditStore._admit_regular(fd, label="audit file")
            return b"".join(chunks)
        finally:
            os.close(fd)

    @staticmethod
    def _admit_destination(audit_fd: int, name: str) -> None:
        try:
            fd = os.open(name, _READ_FLAGS, dir_fd=audit_fd)
        except FileNotFoundError:
            return
        except OSError as exc:
            raise AuditStorageError("audit file is unsafe") from exc
        try:
            AuditStore._admit_regular(fd, label="audit file")
        finally:
            os.close(fd)

    @staticmethod
    def _atomic(audit_fd: int, name: str, data: bytes) -> None:
        AuditStore._admit_destination(audit_fd, name)
        temporary = f".{name}.{secrets.token_hex(16)}.tmp"
        fd = -1
        try:
            fd = os.open(
                temporary,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC,
                0o600,
                dir_fd=audit_fd,
            )
            AuditStore._admit_new_regular(fd, label="audit temporary")
            view = memoryview(data)
            while view:
                view = view[os.write(fd, view) :]
            os.fsync(fd)
            AuditStore._admit_new_regular(fd, label="audit temporary")
            os.close(fd)
            fd = -1
            AuditStore._admit_destination(audit_fd, name)
            os.replace(temporary, name, src_dir_fd=audit_fd, dst_dir_fd=audit_fd)
            os.fsync(audit_fd)
        except OSError as exc:
            raise AuditStorageError("audit publication failed") from exc
        finally:
            if fd >= 0:
                os.close(fd)
            try:
                os.unlink(temporary, dir_fd=audit_fd)
            except FileNotFoundError:
                pass
            except OSError as exc:
                raise AuditStorageError("audit publication cleanup failed") from exc

    def _open_audit(self, root_fd: int, audit_id: str, *, create: bool) -> int:
        if create:
            try:
                os.mkdir(audit_id, mode=0o700, dir_fd=root_fd)
                os.fsync(root_fd)
            except FileExistsError as exc:
                raise AuditStorageError("audit already exists") from exc
            except OSError as exc:
                raise AuditStorageError("audit path is unsafe") from exc
        return self._open_dir(root_fd, audit_id, label="audit path")

    def _recover_locked(
        self, workspace_fd: int, root_fd: int, audit_id: str, audit_fd: int
    ) -> None:
        self._assert_root(workspace_fd, root_fd)
        self._assert_audit(root_fd, audit_id, audit_fd)
        try:
            journal = self._read_file(audit_fd, "publication-journal.json")
        except AuditStorageError as exc:
            try:
                os.stat("publication-journal.json", dir_fd=audit_fd, follow_symlinks=False)
            except FileNotFoundError:
                return
            raise exc
        try:
            staged = json.loads(journal)
            for name in ("snapshot.json", "events.jsonl", "accepted-results.json"):
                self._assert_root(workspace_fd, root_fd)
                self._assert_audit(root_fd, audit_id, audit_fd)
                self._atomic(audit_fd, name, bytes.fromhex(staged[name]))
            self._admit_destination(audit_fd, "publication-journal.json")
            os.unlink("publication-journal.json", dir_fd=audit_fd)
            os.fsync(audit_fd)
            self._assert_root(workspace_fd, root_fd)
            self._assert_audit(root_fd, audit_id, audit_fd)
        except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
            raise AuditStorageError("audit publication journal is corrupt") from exc

    def _publish_locked(
        self,
        workspace_fd: int,
        root_fd: int,
        audit_id: str,
        audit_fd: int,
        snapshot: bytes,
        events: bytes,
        results: bytes,
    ) -> None:
        self._assert_root(workspace_fd, root_fd)
        self._assert_audit(root_fd, audit_id, audit_fd)
        staged = {
            "snapshot.json": snapshot.hex(),
            "events.jsonl": events.hex(),
            "accepted-results.json": results.hex(),
        }
        self._atomic(audit_fd, "publication-journal.json", canonical_json_bytes(staged) + b"\n")
        self._recover_locked(workspace_fd, root_fd, audit_id, audit_fd)

    def _read_locked(
        self, workspace_fd: int, root_fd: int, audit_id: str, audit_fd: int
    ) -> tuple[AuditSnapshot, list[AuditEventRecord], dict[str, AcceptedActionResult]]:
        try:
            self._recover_locked(workspace_fd, root_fd, audit_id, audit_fd)
            snapshot = AuditSnapshot.model_validate_json(self._read_file(audit_fd, "snapshot.json"))
            lines = self._read_file(audit_fd, "events.jsonl").splitlines()
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
            raw_results = json.loads(self._read_file(audit_fd, "accepted-results.json"))
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
            self._assert_root(workspace_fd, root_fd)
            self._assert_audit(root_fd, audit_id, audit_fd)
            return snapshot, events, results
        except (OSError, ValueError, json.JSONDecodeError, TypeError) as exc:
            if isinstance(exc, AuditStorageError):
                raise
            raise AuditStorageError("audit snapshot is corrupt") from exc

    def save(self, snapshot: AuditSnapshot, *, action_id: str | None = None) -> None:
        action_id = action_id or f"start-{snapshot.audit_id.removeprefix('audit-')}"
        with self._locked(snapshot.audit_id) as (workspace_fd, root_fd):
            audit_fd = self._open_audit(root_fd, snapshot.audit_id, create=True)
            try:
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
                    workspace_fd,
                    root_fd,
                    snapshot.audit_id,
                    audit_fd,
                    self._snapshot_bytes(snapshot),
                    canonical_json_bytes(event.model_dump(mode="json")) + b"\n",
                    canonical_json_bytes([result.model_dump(mode="json")]) + b"\n",
                )
            finally:
                os.close(audit_fd)

    def read_versioned(self, audit_id: str) -> tuple[AuditSnapshot, str]:
        with self._locked(audit_id) as (workspace_fd, root_fd):
            audit_fd = self._open_audit(root_fd, audit_id, create=False)
            try:
                snapshot, events, _ = self._read_locked(workspace_fd, root_fd, audit_id, audit_fd)
                return snapshot, events[-1].event_hash
            finally:
                os.close(audit_fd)

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
        with self._locked(audit_id) as (workspace_fd, root_fd):
            audit_fd = self._open_audit(root_fd, audit_id, create=False)
            try:
                snapshot, events, results = self._read_locked(
                    workspace_fd, root_fd, audit_id, audit_fd
                )
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
                event_bytes = (
                    self._read_file(audit_fd, "events.jsonl")
                    + canonical_json_bytes(event.model_dump(mode="json"))
                    + b"\n"
                )
                all_results = [item.model_dump(mode="json") for item in results.values()] + [
                    result.model_dump(mode="json")
                ]
                self._publish_locked(
                    workspace_fd,
                    root_fd,
                    audit_id,
                    audit_fd,
                    self._snapshot_bytes(updated),
                    event_bytes,
                    canonical_json_bytes(all_results) + b"\n",
                )
                return updated, False
            finally:
                os.close(audit_fd)

    def update(self, snapshot: AuditSnapshot, *, expected_event_hash: str | None = None) -> None:
        """Publish a caller-prepared replacement only at the caller-held event head."""
        if not expected_event_hash:
            raise AuditStorageError("expected event hash is required")
        action = AuditAction(
            action="answer",
            answer="legacy update",
            action_id=f"legacy-{self._snapshot_hash(snapshot)[7:19]}",
            expected_event_hash=expected_event_hash,
        )
        self.transact(snapshot.audit_id, action, lambda _current: snapshot)
