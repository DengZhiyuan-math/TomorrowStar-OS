"""Immutable, standalone LaTeX/PDF review receipts; no application execution."""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
import re
import stat
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from ._vendor import job_apply_store as helper
from .application_prism import (
    PrismClient,
    _source_versions,
    archive_sources,
    refresh_source_snapshot,
    source_snapshot,
    validate_archive,
)
from .application_resume import ApplicationResumeStore
from .career_portal_data import PortalDataError


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _object(pairs):
    result = dict(pairs)
    if len(result) != len(pairs):
        raise ValueError("duplicate fields")
    return result


def _safe_path(path):
    if (
        not path.is_absolute()
        or ".." in path.parts
        or any(part.is_symlink() for part in (path, *path.parents))
    ):
        raise ValueError("redirected path")


def _read(path, limit):
    _safe_path(path)
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(descriptor, "rb") as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or not 1 <= info.st_size <= limit:
            raise ValueError("invalid file")
        raw = stream.read(limit + 1)
    if len(raw) > limit:
        raise ValueError("file exceeds limit")
    return raw


def _json(path, limit=128_000):
    return json.loads(_read(path, limit), object_pairs_hook=_object)


def _failure(code="prism_review_needs_recheck", message="审阅回执尚未核验，请保留当前版本与尝试。"):
    return PortalDataError(code, message, 409)


def configured_source_binding(config_path: Path) -> dict:
    """Read the explicitly selected LaTeX source without opening or compiling it."""
    config = _json(Path(config_path), 16_384)
    if (
        not isinstance(config, dict)
        or set(config) != {"project_root", "main"}
        or any(not isinstance(value, str) or not value.strip() for value in config.values())
    ):
        raise ValueError("invalid configuration")
    return source_snapshot(Path(config["project_root"]), config["main"])


class PrismReviewStore:
    """Only explicit capture compiles. Reads preserve existing versions and tasks."""

    def __init__(
        self,
        root: Path,
        config_path: Path | None = None,
        client=None,
        pdf_inspector=None,
        *,
        binding_provider=None,
    ):
        self.root = Path(root)
        self.config_path = Path(config_path) if config_path is not None else None
        self.binding_provider = binding_provider
        self.client = client if client is not None else PrismClient()
        self.pdf_inspector = pdf_inspector

    def _page_count(self, pdf):
        if not isinstance(pdf, bytes) or not 1 <= len(pdf) <= 700_000:
            raise _failure("resume_pdf_invalid", "PDF 文件大小或结构不能核验。")
        if self.pdf_inspector is None:
            ApplicationResumeStore._validate_export_pdf(pdf)
            pages = len(re.findall(rb"/Type\s*/Page\b", pdf))
        else:
            try:
                pages = self.pdf_inspector(pdf)
            except PortalDataError:
                raise
            except Exception as error:
                raise _failure() from error
        if type(pages) is not int or pages < 1:
            raise _failure("resume_pdf_invalid", "PDF 页数不能核验。")
        return pages

    def _binding(self):
        try:
            if self.binding_provider is not None:
                binding = self.binding_provider()
                if (
                    not isinstance(binding, dict)
                    or set(binding)
                    not in (
                        {"project_root", "main", "files", "source_revision"},
                        {"project_root", "main", "files", "source_revision", "source_policy"},
                    )
                    or not isinstance(binding["project_root"], str)
                ):
                    raise ValueError("invalid source binding")
                current = refresh_source_snapshot(binding)
                if current != binding:
                    raise ValueError("source binding changed")
                return current
            if self.config_path is None:
                raise FileNotFoundError("no review configuration")
            return configured_source_binding(self.config_path)
        except FileNotFoundError as error:
            raise _failure(
                "prism_review_not_configured", "请先配置专用 LaTeX 简历项目。"
            ) from error
        except (OSError, ValueError, TypeError, UnicodeError, RecursionError) as error:
            if isinstance(error, PortalDataError):
                raise
            raise _failure("prism_review_config_invalid", "简历审阅配置不能核验。") from error

    def binding(self):
        """Read and validate the current binding without creating any review files."""
        return self._binding()

    def _directory(self, version_id):
        if not isinstance(version_id, str) or not re.fullmatch(r"[a-f0-9]{32}", version_id):
            raise ValueError("invalid version")
        directory = self.root / version_id
        _safe_path(directory)
        return directory

    def _receipt(self, version_id):
        directory = self._directory(version_id)
        intent = _json(directory / "intent.json")
        receipt = _json(directory / "version.json")
        if (
            not isinstance(intent, dict)
            or not isinstance(receipt, dict)
            or set(intent)
            != {"schemaVersion", "id", "created_at", "binding", "source_sha256", "archive_sha256"}
            or intent["schemaVersion"] != 1
            or intent["id"] != version_id
            or not isinstance(intent["created_at"], str)
            or not isinstance(intent["binding"], dict)
            or set(intent["binding"])
            not in (
                {"project_root", "main", "files", "source_revision"},
                {"project_root", "main", "files", "source_revision", "source_policy"},
            )
            or set(receipt) != set(intent) | {"pdf_sha256", "build_sha256", "page_count"}
            or any(receipt[key] != value for key, value in intent.items())
        ):
            raise ValueError("invalid receipt")
        datetime.fromisoformat(intent["created_at"].replace("Z", "+00:00"))
        source = _read(directory / "resume.tex", 4_000_000)
        archive = _read(directory / "latex-sources.json", 48_000_000)
        pdf = _read(directory / "resume.pdf", 700_000)
        build_raw = _read(directory / "build.json", 4096)
        build = json.loads(build_raw, object_pairs_hook=_object)
        pages = self._page_count(pdf)
        if (
            _sha(source) != intent["source_sha256"]
            or _sha(archive) != intent["archive_sha256"]
            or validate_archive(archive, intent["binding"]) != source
            or _sha(pdf) != receipt["pdf_sha256"]
            or _sha(build_raw) != receipt["build_sha256"]
            or pages != receipt["page_count"]
            or type(receipt["page_count"]) is not int
            or pages < 1
            or not isinstance(build, dict)
            or build.get("source_revision") != intent["binding"]["source_revision"]
            or build.get("main") != intent["binding"]["main"]
            or type(build.get("exit")) is not int
            or build["exit"] != 0
            or build.get("pdf_updated") is not True
        ):
            raise ValueError("receipt bytes changed")
        version = {
            key: receipt[key]
            for key in (
                "id",
                "created_at",
                "source_sha256",
                "archive_sha256",
                "pdf_sha256",
                "page_count",
            )
        }
        version.update(
            main=intent["binding"]["main"],
            source_revision=intent["binding"]["source_revision"],
            review_status="pending_human_review",
        )
        return version, source, pdf, archive, intent["binding"]

    def _history(self):
        versions, pending = [], []
        _safe_path(self.root)
        if self.root.exists():
            if not self.root.is_dir():
                raise ValueError("invalid review root")
            for directory in self.root.iterdir():
                if directory.name == ".capture.lock":
                    continue
                try:
                    self._directory(directory.name)
                    versions.append(self._receipt(directory.name)[0])
                except (OSError, ValueError, TypeError, KeyError, UnicodeError, RecursionError):
                    # Known compile/PDF rejection allows explicit retry; unknown requests do not.
                    try:
                        failed = _json(directory / "failed.json", 4096)
                    except (OSError, ValueError, TypeError, UnicodeError, RecursionError):
                        failed = None
                    if (
                        failed
                        not in (
                            {"code": "resume_export_failed", "id": directory.name},
                            {"code": "resume_pdf_invalid", "id": directory.name},
                        )
                        or (directory / "version.json").exists()
                    ):
                        pending.append(directory.name)
        versions.sort(key=lambda item: (item["created_at"], item["id"]), reverse=True)
        return versions, sorted(pending)

    def state(self):
        """Read saved source and immutable receipts without compiling or creating files."""
        error, binding = None, None
        try:
            versions, pending = self._history()
        except (OSError, ValueError, TypeError, KeyError, UnicodeError, RecursionError):
            versions, pending = [], ["unknown"]
        try:
            binding = self._binding()
        except PortalDataError as exc:
            error = {"code": exc.code, "message": str(exc)}
        latest = versions[0] if versions else None
        changed = bool(
            latest and binding and latest["source_revision"] != binding["source_revision"]
        )
        if pending:
            status = "needs_recheck"
        elif error:
            status = (
                "unconfigured"
                if error["code"] == "prism_review_not_configured"
                else "source_unavailable"
            )
        else:
            status = "source_changed" if changed else "ready" if latest else "empty"
        return {
            "status": status,
            "latest": latest,
            "versions": versions,
            "live_source_revision": binding["source_revision"] if binding else None,
            "source_changed": changed,
            "main": binding["main"] if binding else None,
            "pending_attempt_id": pending[0] if pending else None,
            "review_status": "pending_human_review",
            "error": error,
        }

    def editor(self):
        return self.client.open(self._binding())

    def capture(self, expected_source_revision):
        """Strictly compile this saved source once and retain its explicit review version."""
        try:
            _safe_path(self.root)
            self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
            descriptor = os.open(
                self.root / ".capture.lock", os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600
            )
            with os.fdopen(descriptor, "rb") as lock:
                try:
                    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except BlockingIOError as error:
                    raise _failure(
                        "prism_review_busy", "已有一次简历读取正在进行，请保留该尝试。"
                    ) from error
                return self._capture(expected_source_revision)
        except PortalDataError:
            raise
        except (
            OSError,
            ValueError,
            TypeError,
            KeyError,
            UnicodeError,
            AttributeError,
            RecursionError,
        ) as error:
            raise _failure() from error

    def _capture(self, expected_source_revision):
        _versions, pending = self._history()
        if pending:
            raise _failure()
        binding = self._binding()
        if (
            not isinstance(expected_source_revision, str)
            or expected_source_revision != binding["source_revision"]
        ):
            raise _failure("prism_source_changed", "LaTeX 源已变化，请重新读取当前源版本。")
        root = Path(binding["project_root"])
        identities = _source_versions(root, binding["files"])
        archive = archive_sources(binding)
        source = validate_archive(archive, binding)
        identifier = uuid4().hex
        directory = self._directory(identifier)
        directory.mkdir(mode=0o700)
        intent = {
            "schemaVersion": 1,
            "id": identifier,
            "created_at": datetime.now(UTC)
            .isoformat(timespec="microseconds")
            .replace("+00:00", "Z"),
            "binding": binding,
            "source_sha256": _sha(source),
            "archive_sha256": _sha(archive),
        }
        helper.atomic_write_json(directory / "intent.json", intent)
        for filename, raw in (("resume.tex", source), ("latex-sources.json", archive)):
            self._write(directory / filename, raw)
        try:
            compiled = self.client.compile(binding)
        except PortalDataError as error:
            if error.code == "resume_export_failed":
                helper.atomic_write_json(
                    directory / "failed.json", {"id": identifier, "code": error.code}
                )
                raise
            raise _failure() from error
        except Exception as error:
            raise _failure() from error
        if (
            compiled.get("source_revision") != binding["source_revision"]
            or refresh_source_snapshot(binding) != binding
            or _source_versions(root, binding["files"]) != identities
            or self._binding() != binding
        ):
            raise _failure()
        pdf = compiled["pdf"]
        if not isinstance(pdf, bytes):
            raise _failure()
        build = compiled["build"] | {"source_revision": binding["source_revision"]}
        self._write(directory / "resume.pdf", pdf)
        helper.atomic_write_json(directory / "build.json", build)
        if (
            build.get("main") != binding["main"]
            or type(build.get("exit")) is not int
            or build["exit"] != 0
            or build.get("pdf_updated") is not True
        ):
            raise _failure()
        try:
            pages = self._page_count(pdf)
        except PortalDataError as error:
            if error.code == "resume_pdf_invalid":
                helper.atomic_write_json(
                    directory / "failed.json", {"id": identifier, "code": error.code}
                )
            raise
        receipt = intent | {
            "pdf_sha256": _sha(pdf),
            "build_sha256": _sha(_read(directory / "build.json", 4096)),
            "page_count": pages,
        }
        helper.atomic_write_json(directory / "version.json", receipt)
        self._receipt(identifier)
        return self.state()

    @staticmethod
    def _write(path, raw):
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())

    def reconcile(self, version_id=None):
        """Read back a completed receipt. Missing receipts never justify another build."""
        try:
            state = self.state()
            identifier = version_id or state["pending_attempt_id"]
            if identifier is not None:
                self._receipt(identifier)
            if state["status"] == "needs_recheck":
                raise ValueError("incomplete attempt")
            return state
        except (OSError, ValueError, KeyError, TypeError, UnicodeError, RecursionError) as error:
            raise _failure() from error

    def source(self, version_id):
        try:
            return self._receipt(version_id)[1]
        except (OSError, ValueError, KeyError, TypeError, UnicodeError, RecursionError) as error:
            raise _failure() from error

    def version(self, version_id):
        """Read immutable version metadata and its validated archived source binding."""
        try:
            receipt = self._receipt(version_id)
            return receipt[0] | {"binding": receipt[4]}
        except (OSError, ValueError, KeyError, TypeError, UnicodeError, RecursionError) as error:
            raise _failure() from error

    def archive(self, version_id):
        """Read the bounded immutable source archive after complete receipt validation."""
        try:
            return self._receipt(version_id)[3]
        except (OSError, ValueError, KeyError, TypeError, UnicodeError, RecursionError) as error:
            raise _failure() from error

    def build(self, version_id):
        """Read a validated strict-build record without starting another build."""
        try:
            self._receipt(version_id)
            return _json(self._directory(version_id) / "build.json", 4096)
        except (OSError, ValueError, KeyError, TypeError, UnicodeError, RecursionError) as error:
            raise _failure() from error

    def pdf(self, version_id):
        try:
            return self._receipt(version_id)[2]
        except (OSError, ValueError, KeyError, TypeError, UnicodeError, RecursionError) as error:
            raise _failure() from error
