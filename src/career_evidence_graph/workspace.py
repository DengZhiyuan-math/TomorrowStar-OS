"""One explicit, private workspace boundary for career-source custody."""

from __future__ import annotations

import os
import stat
import uuid
from contextlib import suppress
from pathlib import Path


class PrivateWorkspaceError(ValueError):
    """The selected private workspace is unsafe."""


class PrivateWorkspace:
    """Resolve one existing non-symlink workspace and its semantic namespaces."""

    def __init__(self, path: Path) -> None:
        if path.is_symlink() or not path.is_dir():
            raise PrivateWorkspaceError("career-source-workspace-unsafe")
        self.root = path.resolve(strict=True)

    def child(self, *parts: str) -> Path:
        candidate = self.root
        for part in parts:
            component = Path(part)
            if component.is_absolute() or ".." in component.parts:
                raise PrivateWorkspaceError("career-source-path-unsafe")
            candidate = candidate / component
            if candidate.exists() and candidate.is_symlink():
                raise PrivateWorkspaceError("career-source-path-unsafe")
        existing_parent = candidate
        while not existing_parent.exists():
            existing_parent = existing_parent.parent
        if existing_parent.is_symlink() or not existing_parent.resolve().is_relative_to(self.root):
            raise PrivateWorkspaceError("career-source-path-unsafe")
        return candidate

    @staticmethod
    def _validate_parts(parts: tuple[str, ...]) -> None:
        if not parts:
            raise PrivateWorkspaceError("career-source-path-unsafe")
        for part in parts:
            component = Path(part)
            if component.name != part or component.is_absolute() or ".." in component.parts:
                raise PrivateWorkspaceError("career-source-path-unsafe")

    def _directory_fd(self, parts: tuple[str, ...], *, create: bool) -> int:
        self._validate_parts(parts)
        flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
        try:
            descriptor = os.open(self.root, flags)
            for part in parts:
                if create:
                    with suppress(FileExistsError):
                        os.mkdir(part, mode=0o700, dir_fd=descriptor)
                child = os.open(part, flags, dir_fd=descriptor)
                os.close(descriptor)
                descriptor = child
            return descriptor
        except OSError as exc:
            with suppress(UnboundLocalError):
                os.close(descriptor)
            raise PrivateWorkspaceError("career-source-path-unsafe") from exc

    def _revalidate_directory(self, descriptor: int, parts: tuple[str, ...]) -> None:
        """Reject a namespace that was replaced after its descriptor was opened."""
        current = self._directory_fd(parts, create=False)
        try:
            if os.fstat(descriptor)[:2] != os.fstat(current)[:2]:
                raise PrivateWorkspaceError("career-source-path-unsafe")
        finally:
            os.close(current)

    def read_regular_bytes(self, *parts: str) -> bytes:
        self._validate_parts(parts)
        parent = self._directory_fd(tuple(parts[:-1]), create=False)
        try:
            descriptor = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW, dir_fd=parent)
            try:
                size = os.fstat(descriptor).st_size
                if not stat.S_ISREG(os.fstat(descriptor).st_mode):
                    raise PrivateWorkspaceError("career-source-path-unsafe")
                chunks: list[bytes] = []
                remaining = size
                while remaining:
                    chunk = os.read(descriptor, remaining)
                    if not chunk:
                        raise PrivateWorkspaceError("career-source-path-unsafe")
                    chunks.append(chunk)
                    remaining -= len(chunk)
                return b"".join(chunks)
            finally:
                os.close(descriptor)
        except OSError as exc:
            raise PrivateWorkspaceError("career-source-path-unsafe") from exc
        finally:
            os.close(parent)

    def write_new_regular_bytes(self, *parts: str, payload: bytes) -> bool:
        """Create one private regular file through verified no-follow descriptors."""
        self._validate_parts(parts)
        parent_parts = tuple(parts[:-1])
        parent = self._directory_fd(parent_parts, create=True)
        try:
            self._revalidate_directory(parent, parent_parts)
            try:
                descriptor = os.open(
                    parts[-1],
                    os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                    0o600,
                    dir_fd=parent,
                )
            except FileExistsError:
                return False
            try:
                offset = 0
                while offset < len(payload):
                    offset += os.write(descriptor, payload[offset:])
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
            return True
        except OSError as exc:
            raise PrivateWorkspaceError("career-source-path-unsafe") from exc
        finally:
            os.close(parent)

    def unlink_regular(self, *parts: str) -> None:
        self._validate_parts(parts)
        parent_parts = tuple(parts[:-1])
        parent = self._directory_fd(parent_parts, create=False)
        try:
            self._revalidate_directory(parent, parent_parts)
            entry = os.stat(parts[-1], dir_fd=parent, follow_symlinks=False)
            if not stat.S_ISREG(entry.st_mode):
                raise PrivateWorkspaceError("career-source-path-unsafe")
            os.unlink(parts[-1], dir_fd=parent)
        except OSError as exc:
            raise PrivateWorkspaceError("career-source-path-unsafe") from exc
        finally:
            os.close(parent)

    @staticmethod
    def _write_descriptor(descriptor: int, payload: bytes) -> None:
        offset = 0
        while offset < len(payload):
            offset += os.write(descriptor, payload[offset:])
        os.fsync(descriptor)

    def replace_regular_bytes(self, *parts: str, payload: bytes) -> None:
        """Atomically replace one leaf only while its parent descriptor is unchanged."""
        self._validate_parts(parts)
        parent_parts = tuple(parts[:-1])
        parent = self._directory_fd(parent_parts, create=True)
        temporary = f".{parts[-1]}.{uuid.uuid4().hex}"
        try:
            self._revalidate_directory(parent, parent_parts)
            descriptor = os.open(
                temporary,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                0o600,
                dir_fd=parent,
            )
            try:
                self._write_descriptor(descriptor, payload)
            finally:
                os.close(descriptor)
            self._revalidate_directory(parent, parent_parts)
            os.replace(temporary, parts[-1], src_dir_fd=parent, dst_dir_fd=parent)
        except OSError as exc:
            raise PrivateWorkspaceError("career-source-path-unsafe") from exc
        finally:
            try:
                os.unlink(temporary, dir_fd=parent)
            except FileNotFoundError:
                pass
            finally:
                os.close(parent)

    def create_only_bundle_regular_bytes(
        self, *parts: str, bundle_name: str, filename: str, payload: bytes
    ) -> None:
        """Publish one manifest bundle without following a mutable namespace path."""
        self._validate_parts(parts)
        self._validate_parts((bundle_name, filename))
        parent_parts = tuple(parts)
        parent = self._directory_fd(parent_parts, create=True)
        temporary = f".{bundle_name}.{uuid.uuid4().hex}"
        try:
            self._revalidate_directory(parent, parent_parts)
            os.mkdir(temporary, mode=0o700, dir_fd=parent)
            bundle = os.open(temporary, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent)
            try:
                descriptor = os.open(
                    filename,
                    os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                    0o600,
                    dir_fd=bundle,
                )
                try:
                    self._write_descriptor(descriptor, payload)
                finally:
                    os.close(descriptor)
            finally:
                os.close(bundle)
            self._revalidate_directory(parent, parent_parts)
            os.rename(temporary, bundle_name, src_dir_fd=parent, dst_dir_fd=parent)
        except OSError as exc:
            raise PrivateWorkspaceError("career-source-path-unsafe") from exc
        finally:
            try:
                bundle = os.open(
                    temporary, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent
                )
            except FileNotFoundError:
                bundle = None
            if bundle is not None:
                try:
                    os.unlink(filename, dir_fd=bundle)
                except FileNotFoundError:
                    pass
                finally:
                    os.close(bundle)
                with suppress(FileNotFoundError):
                    os.rmdir(temporary, dir_fd=parent)
            os.close(parent)
