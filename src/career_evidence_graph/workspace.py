"""Small direct workspace helpers for a private career-source registry."""

from __future__ import annotations

import json
import re
import subprocess
from datetime import date, datetime
from pathlib import Path

from .validation.hashing import sha256_digest
from .validation.store import atomic_write_canonical_json

_ID = re.compile(r"^[a-z][a-z0-9]*(?:[._-][a-z0-9]+)*$")
_HASH = re.compile(r"^sha256:[0-9a-f]{64}$")
_AVAILABILITY = frozenset(
    {
        "available",
        "temporarily-unavailable",
        "permanently-lost",
        "access-restricted",
        "never-created",
        "location-unknown",
        "user-declined",
    }
)
_SOURCE_TYPES = frozenset(
    {
        "document",
        "self-reported",
        "formal-credential",
        "repository",
        "web-snapshot",
        "cloud-export",
        "audit-record",
        "examination-record",
    }
)


class WorkspaceError(ValueError):
    """A content-free workspace or registry failure."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


def open_private_workspace(path: Path, *, public_root: Path | None = None) -> Path:
    """Return a separate private Git worktree without reading its Git history."""
    if path.is_symlink() or not path.is_dir():
        raise WorkspaceError("private-workspace-invalid")
    root = _git_root(path)
    public = _git_root(public_root or Path(__file__).resolve().parents[2])
    if root == public or root.is_relative_to(public) or public.is_relative_to(root):
        raise WorkspaceError("private-workspace-not-separate")
    return root


def declare_sources(workspace: Path, declaration: dict[str, object]) -> dict[str, object]:
    """Create the one small registry that declares candidate-provided sources."""
    root = open_private_workspace(workspace)
    registry = _registry_path(root)
    if registry.exists():
        raise WorkspaceError("registry-already-exists")
    _validate_declaration(declaration)
    _write_registry(root, declaration)
    return {"authority": "candidate-only", "source_count": len(declaration["sources"])}


def capture_source(
    workspace: Path, source_id: str, payload: bytes, *, captured_at: str
) -> dict[str, object]:
    """Create raw bytes once, then publish their hash and capture time on one source."""
    root = open_private_workspace(workspace)
    registry = _load_registry(root)
    source = _source(registry, source_id)
    if source.get("availability") != "available":
        raise WorkspaceError("source-unavailable")
    if "capture" in source:
        raise WorkspaceError("capture-already-recorded")
    if not isinstance(payload, bytes) or not payload:
        raise WorkspaceError("capture-invalid")
    _parse_datetime(captured_at)
    raw_root = _raw_vault(root)
    digest = sha256_digest(payload)
    raw_path = raw_root / digest.removeprefix("sha256:")
    if raw_path.exists() or raw_path.is_symlink():
        raise WorkspaceError("raw-already-exists")
    try:
        with raw_path.open("xb") as handle:
            handle.write(payload)
    except OSError as exc:
        raise WorkspaceError("raw-write-failed") from exc
    source["capture"] = {"content_hash": digest, "captured_at": captured_at}
    _write_registry(root, registry)
    return {"authority": "candidate-only", "captured": True}


def record_derived_mapping(
    workspace: Path,
    source_id: str,
    *,
    input_hash: str,
    output_hash: str,
    transformer_identity: str,
    transformer_version: str,
    locator: str | None = None,
) -> dict[str, object]:
    """Record optional caller-supplied derivation lineage without creating output bytes."""
    root = open_private_workspace(workspace)
    registry = _load_registry(root)
    source = _source(registry, source_id)
    capture = source.get("capture")
    if not isinstance(capture, dict) or capture.get("content_hash") != input_hash:
        raise WorkspaceError("derived-input-invalid")
    if "derived" in source or not _HASH.fullmatch(output_hash):
        raise WorkspaceError("derived-mapping-invalid")
    if not isinstance(transformer_identity, str) or not transformer_identity:
        raise WorkspaceError("derived-mapping-invalid")
    if not isinstance(transformer_version, str) or not transformer_version:
        raise WorkspaceError("derived-mapping-invalid")
    if locator is not None and (not isinstance(locator, str) or not locator):
        raise WorkspaceError("derived-mapping-invalid")
    derived: dict[str, object] = {
        "input_hash": input_hash,
        "output_hash": output_hash,
        "transformer": {"identity": transformer_identity, "version": transformer_version},
    }
    if locator is not None:
        derived["locator"] = locator
    source["derived"] = derived
    _write_registry(root, registry)
    return {"authority": "candidate-only", "derived_mapping_recorded": True}


def workspace_status(workspace: Path) -> dict[str, object]:
    """Return content-free registry counts for a private workspace."""
    registry = _load_registry(open_private_workspace(workspace))
    sources = registry["sources"]
    assert isinstance(sources, list)
    return {
        "authority": "candidate-only",
        "source_count": len(sources),
        "unavailable_source_count": sum(
            source.get("availability") != "available"
            for source in sources
            if isinstance(source, dict)
        ),
    }


def _git_root(path: Path) -> Path:
    try:
        result = subprocess.run(
            ["git", "-C", str(path), "rev-parse", "--show-toplevel"],
            check=True,
            capture_output=True,
            text=True,
        )
        root = Path(result.stdout.strip()).resolve(strict=True)
    except (OSError, subprocess.CalledProcessError, ValueError) as exc:
        raise WorkspaceError("private-workspace-not-git") from exc
    if root.is_symlink() or not root.is_dir():
        raise WorkspaceError("private-workspace-invalid")
    return root


def _registry_path(root: Path) -> Path:
    evidence = root / ".career-evidence"
    if evidence.exists() and evidence.is_symlink():
        raise WorkspaceError("private-path-invalid")
    return evidence / "registry.json"


def _raw_vault(root: Path) -> Path:
    ignored = root / ".gitignore"
    try:
        ignored_lines = ignored.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise WorkspaceError("raw-vault-not-ignored") from exc
    if ".career-evidence/raw/" not in {line.strip() for line in ignored_lines}:
        raise WorkspaceError("raw-vault-not-ignored")
    evidence = root / ".career-evidence"
    raw = evidence / "raw"
    if any(path.is_symlink() for path in (evidence, raw)):
        raise WorkspaceError("private-path-invalid")
    try:
        raw.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise WorkspaceError("private-path-invalid") from exc
    return raw


def _load_registry(root: Path) -> dict[str, object]:
    registry_path = _registry_path(root)
    if registry_path.is_symlink():
        raise WorkspaceError("private-path-invalid")
    try:
        value = json.loads(registry_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise WorkspaceError("registry-invalid") from exc
    if not isinstance(value, dict):
        raise WorkspaceError("registry-invalid")
    _validate_declaration(value)
    return value


def _write_registry(root: Path, registry: dict[str, object]) -> None:
    registry_path = _registry_path(root)
    try:
        registry_path.parent.mkdir(parents=True, exist_ok=True)
        if registry_path.is_symlink():
            raise WorkspaceError("private-path-invalid")
        atomic_write_canonical_json(registry_path, registry)
    except WorkspaceError:
        raise
    except OSError as exc:
        raise WorkspaceError("registry-write-failed") from exc


def _validate_declaration(value: dict[str, object]) -> None:
    try:
        if set(value) != {"cutoff", "categories", "sources"}:
            raise ValueError
        cutoff = value["cutoff"]
        categories = value["categories"]
        sources = value["sources"]
        if not isinstance(cutoff, str):
            raise ValueError
        date.fromisoformat(cutoff)
        if (
            not isinstance(categories, list)
            or not categories
            or any(
                not isinstance(category, str) or not _ID.fullmatch(category)
                for category in categories
            )
        ):
            raise ValueError
        if len(categories) != len(set(categories)) or not isinstance(sources, list) or not sources:
            raise ValueError
        source_ids: set[str] = set()
        for source in sources:
            if not isinstance(source, dict) or set(source) - {
                "source_id",
                "category",
                "source_type",
                "availability",
                "unavailability_reason",
                "capture",
                "derived",
            }:
                raise ValueError
            source_id = source.get("source_id")
            category = source.get("category")
            availability = source.get("availability")
            if (
                not isinstance(source_id, str)
                or not _ID.fullmatch(source_id)
                or source_id in source_ids
                or category not in categories
                or source.get("source_type") not in _SOURCE_TYPES
                or availability not in _AVAILABILITY
            ):
                raise ValueError
            reason = source.get("unavailability_reason")
            if availability == "available":
                if reason is not None:
                    raise ValueError
            elif not isinstance(reason, str) or not reason:
                raise ValueError
            _validate_capture(source.get("capture"))
            _validate_derived(source.get("derived"))
            source_ids.add(source_id)
    except (TypeError, ValueError):
        raise WorkspaceError("registry-invalid") from None


def _validate_capture(value: object) -> None:
    if value is None:
        return
    if not isinstance(value, dict) or set(value) != {"content_hash", "captured_at"}:
        raise ValueError
    if not isinstance(value["content_hash"], str) or not _HASH.fullmatch(value["content_hash"]):
        raise ValueError
    if not isinstance(value["captured_at"], str):
        raise ValueError
    _parse_datetime(value["captured_at"])


def _validate_derived(value: object) -> None:
    if value is None:
        return
    if not isinstance(value, dict) or set(value) - {
        "input_hash",
        "output_hash",
        "transformer",
        "locator",
    }:
        raise ValueError
    if not all(
        isinstance(value.get(key), str) and _HASH.fullmatch(value[key])
        for key in ("input_hash", "output_hash")
    ):
        raise ValueError
    transformer = value.get("transformer")
    if not isinstance(transformer, dict) or set(transformer) != {"identity", "version"}:
        raise ValueError
    if not all(isinstance(transformer[key], str) and transformer[key] for key in transformer):
        raise ValueError
    if "locator" in value and (not isinstance(value["locator"], str) or not value["locator"]):
        raise ValueError


def _source(registry: dict[str, object], source_id: str) -> dict[str, object]:
    if not isinstance(source_id, str) or not _ID.fullmatch(source_id):
        raise WorkspaceError("source-not-declared")
    sources = registry["sources"]
    assert isinstance(sources, list)
    for source in sources:
        if isinstance(source, dict) and source.get("source_id") == source_id:
            return source
    raise WorkspaceError("source-not-declared")


def _parse_datetime(value: str) -> None:
    try:
        if datetime.fromisoformat(value).tzinfo is None:
            raise ValueError
    except ValueError:
        raise WorkspaceError("capture-invalid") from None
