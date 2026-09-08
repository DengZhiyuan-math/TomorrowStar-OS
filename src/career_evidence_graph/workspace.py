"""Small direct workspace helpers for a private career-source registry."""

from __future__ import annotations

import json
import re
import subprocess
from copy import deepcopy
from datetime import date, datetime
from pathlib import Path

from .validation.hashing import canonical_json_bytes, sha256_digest
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


def record_self_report_source_successor(
    workspace: Path,
    *,
    parent_registry_hash: str,
    source_id: str,
    statement: bytes,
    captured_at: str,
) -> dict[str, object]:
    """Append one captured self-report through an immutable Source-universe successor."""
    root = open_private_workspace(workspace)
    parent = _load_registry_by_hash(root, parent_registry_hash)
    if not isinstance(source_id, str) or not _ID.fullmatch(source_id):
        raise WorkspaceError("source-not-declared")
    if not isinstance(statement, bytes) or not statement:
        raise WorkspaceError("capture-invalid")
    _parse_datetime(captured_at)
    if any(source.get("source_id") == source_id for source in parent["sources"]):
        raise WorkspaceError("source-already-declared")

    digest = sha256_digest(statement)
    raw_path = _raw_vault(root) / digest.removeprefix("sha256:")
    if raw_path.exists() or raw_path.is_symlink():
        raise WorkspaceError("raw-already-exists")
    try:
        with raw_path.open("xb") as handle:
            handle.write(statement)
    except OSError as exc:
        raise WorkspaceError("raw-write-failed") from exc

    successor = deepcopy(parent)
    categories = successor["categories"]
    assert isinstance(categories, list)
    if "self-reports" not in categories:
        categories.append("self-reports")
    sources = successor["sources"]
    assert isinstance(sources, list)
    sources.append(
        {
            "source_id": source_id,
            "category": "self-reports",
            "source_type": "self-reported",
            "availability": "available",
            "capture": {"content_hash": digest, "captured_at": captured_at},
        }
    )
    _validate_declaration(successor)
    successor_hash = _registry_hash(successor)
    _write_source_universe_successor(
        root,
        successor_hash,
        {
            "schema_version": "source-universe-successor/v1",
            "authority": "candidate-only",
            "parent_registry_hash": parent_registry_hash,
            "registry": successor,
        },
    )
    return {
        "authority": "candidate-only",
        "parent_registry_hash": parent_registry_hash,
        "registry_hash": successor_hash,
        "source_id": source_id,
    }


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


def load_source_universe_snapshot(
    workspace: Path,
    *,
    public_root: Path | None = None,
    registry_hash: str | None = None,
) -> dict[str, object]:
    """Return one detached registry snapshot with every referenced capture verified."""
    root = open_private_workspace(workspace, public_root=public_root)
    registry = _load_registry_by_hash(root, registry_hash)
    evidence = root / ".career-evidence"
    raw_root = evidence / "raw"
    if any(path.is_symlink() for path in (evidence, raw_root)):
        raise WorkspaceError("private-path-invalid")
    captures: dict[str, bytes] = {}
    sources = registry["sources"]
    assert isinstance(sources, list)
    for source in sources:
        assert isinstance(source, dict)
        capture = source.get("capture")
        if not isinstance(capture, dict):
            continue
        source_id = source["source_id"]
        digest = capture["content_hash"]
        assert isinstance(source_id, str) and isinstance(digest, str)
        raw_path = raw_root / digest.removeprefix("sha256:")
        if raw_path.is_symlink() or not raw_path.is_file():
            raise WorkspaceError("capture-integrity-invalid")
        try:
            payload = raw_path.read_bytes()
        except OSError as exc:
            raise WorkspaceError("capture-integrity-invalid") from exc
        if sha256_digest(payload) != digest:
            raise WorkspaceError("capture-integrity-invalid")
        captures[source_id] = payload
    detached = deepcopy(registry)
    return {
        "authority": "candidate-only",
        "registry_hash": _registry_hash(detached),
        "registry": detached,
        "captures": captures,
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


def _source_universe_revision_path(root: Path, registry_hash: str) -> Path:
    if not isinstance(registry_hash, str) or not _HASH.fullmatch(registry_hash):
        raise WorkspaceError("source-universe-revision-invalid")
    evidence = root / ".career-evidence"
    revisions = evidence / "source-universe-revisions"
    if any(path.is_symlink() for path in (evidence, revisions)):
        raise WorkspaceError("private-path-invalid")
    return revisions / f"{registry_hash.removeprefix('sha256:')}.json"


def _registry_hash(registry: dict[str, object]) -> str:
    return sha256_digest(canonical_json_bytes(registry))


def _load_registry_by_hash(root: Path, registry_hash: str | None) -> dict[str, object]:
    current = _load_registry(root)
    current_hash = _registry_hash(current)
    if registry_hash is None or registry_hash == current_hash:
        return current
    if not isinstance(registry_hash, str) or not _HASH.fullmatch(registry_hash):
        raise WorkspaceError("source-universe-revision-invalid")
    revision_path = _source_universe_revision_path(root, registry_hash)
    if revision_path.is_symlink():
        raise WorkspaceError("private-path-invalid")
    try:
        revision = json.loads(revision_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise WorkspaceError("source-universe-revision-invalid") from exc
    if (
        not isinstance(revision, dict)
        or set(revision) != {"schema_version", "authority", "parent_registry_hash", "registry"}
        or revision.get("schema_version") != "source-universe-successor/v1"
        or revision.get("authority") != "candidate-only"
        or not isinstance(revision.get("parent_registry_hash"), str)
        or not _HASH.fullmatch(revision["parent_registry_hash"])
        or not isinstance(revision.get("registry"), dict)
    ):
        raise WorkspaceError("source-universe-revision-invalid")
    successor = revision["registry"]
    _validate_declaration(successor)
    if _registry_hash(successor) != registry_hash:
        raise WorkspaceError("source-universe-revision-invalid")
    _load_registry_by_hash(root, revision["parent_registry_hash"])
    return successor


def _write_source_universe_successor(
    root: Path, registry_hash: str, successor: dict[str, object]
) -> None:
    path = _source_universe_revision_path(root, registry_hash)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.is_symlink():
            raise WorkspaceError("private-path-invalid")
        with path.open("xb") as handle:
            handle.write(canonical_json_bytes(successor) + b"\n")
    except WorkspaceError:
        raise
    except FileExistsError as exc:
        raise WorkspaceError("source-universe-revision-already-exists") from exc
    except OSError as exc:
        raise WorkspaceError("source-universe-revision-write-failed") from exc


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
