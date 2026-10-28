"""Private operational experience facts and their lightweight discovery directory.

These records describe saved career facts. They do not grant skill scores or
assessment authority. Immutable versions retain original material provenance.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
from collections.abc import Callable
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from pydantic import ValidationError

from .application_resume_content import ExperienceFacts
from .career_portal_data import ApplicationStore, PortalDataError, _check_root, _write_file

_MAX_TEXT = 2_000_000
_MAX_RECORD = 32_000_000
_MAX_DIRECTORY = 64_000_000
_METADATA_STRINGS = {
    "category",
    "institution",
    "dates",
    "status",
    "import_status",
    "source_revision",
}
_METADATA_LISTS = {"aliases", "related_ids", "links", "unavailable_sources", "manual_fields"}
_ROLES = {"primary", "supplement", "artifact", "generated", "history"}


def _invalid() -> PortalDataError:
    return PortalDataError("invalid-experience", "经历记录格式无效。")


def _text(value: object, *, required: bool = False, maximum: int = _MAX_TEXT) -> str:
    if not isinstance(value, str) or (required and not value.strip()):
        raise _invalid()
    try:
        if len(value.encode("utf-8")) > maximum:
            raise _invalid()
    except UnicodeEncodeError as exc:
        raise _invalid() from exc
    return value


def _identifier(value: object) -> str:
    return _text(value, required=True, maximum=1024)


def _json_bytes(value: object) -> bytes:
    try:
        raw = json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False).encode("utf-8")
    except (TypeError, ValueError, UnicodeEncodeError) as exc:
        raise _invalid() from exc
    if len(raw) > _MAX_RECORD:
        raise _invalid()
    return raw


def _content(value: object, candidate_id: str, title: str, *, verify: bool = False) -> dict:
    try:
        clean = ExperienceFacts.model_validate(value).model_dump(mode="json")
    except ValidationError as exc:
        raise _invalid() from exc
    if clean["candidate_id"] != candidate_id or clean["title"] != title:
        raise _invalid()
    revision = hashlib.sha256(
        _json_bytes({key: item for key, item in clean.items() if key != "revision"})
    ).hexdigest()
    if verify and clean["revision"] != revision:
        raise _invalid()
    clean["revision"] = revision
    return clean


def _metadata(value: object) -> dict[str, object]:
    if value is None:
        return {}
    if not isinstance(value, dict) or value.keys() - (_METADATA_STRINGS | _METADATA_LISTS):
        raise _invalid()
    clean: dict[str, object] = {}
    for key, item in value.items():
        if key in _METADATA_STRINGS:
            clean[key] = _text(item)
        else:
            if not isinstance(item, list):
                raise _invalid()
            clean[key] = [_text(part) for part in item]
    if clean.get("import_status", "complete") not in {"complete", "pending"}:
        raise _invalid()
    return clean


def _materials(value: object) -> list[dict[str, object]]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise _invalid()
    seen: set[str] = set()
    result = []
    for item in value:
        if not isinstance(item, dict):
            raise _invalid()
        identifier = _identifier(item.get("id"))
        if (
            identifier in seen
            or not isinstance(item.get("role"), str)
            or item["role"] not in _ROLES
        ):
            raise _invalid()
        seen.add(identifier)
        _text(item.get("source_name"), required=True)
        _text(item.get("text"))
        if "derived_from" in item:
            derived = item["derived_from"]
            if isinstance(derived, list):
                for source in derived:
                    _identifier(source)
            else:
                _identifier(derived)
        # Round-trip extra source locators, attribution and boundary annotations.
        result.append(json.loads(_json_bytes(item)))
    return result


def _identity(value: os.stat_result) -> tuple[int, ...]:
    return (
        value.st_dev,
        value.st_ino,
        value.st_mode,
        value.st_size,
        value.st_mtime_ns,
        value.st_ctime_ns,
    )


def _normalized(text: str) -> str:
    return " ".join(text.split())


def material_identity(material: dict) -> tuple[str, str]:
    """Share a text read only when its recorded factual context also agrees."""
    representation = {
        "id",
        "source_name",
        "text",
        "role",
        "derived_from",
        "source_revision",
        "locator",
        "source_managed",
        "source_key",
    }
    context = {key: value for key, value in material.items() if key not in representation}
    return _normalized(material["text"]), json.dumps(context, ensure_ascii=False, sort_keys=True)


def _derive(payload: dict[str, object]) -> dict[str, object]:
    content = payload.get("content")
    if content is not None:
        texts = [content[key] for key in ("title", "role", "organization") if content[key]]
        for fact in content["facts"]:
            texts.extend(fact[key] for key in ("text", "scope", "status", "responsibility"))
        substantive = " ".join(fact["text"] for fact in content["facts"])
    else:
        texts = [payload["body"]]
        paragraphs = re.split(r"\n\s*\n", payload["body"])
        substantive = next(
            (part for part in paragraphs if part.strip() and not part.lstrip().startswith("#")),
            payload["body"],
        )
    groups: dict[tuple[str, str], dict[str, object]] = {}
    for material in payload["materials"]:
        if material["role"] in {"generated", "history"}:
            continue
        normalized = material_identity(material)
        group = groups.get(normalized)
        if group is None:
            group = {"canonical_id": material["id"], "source_ids": [], "sources": []}
            groups[normalized] = group
            texts.append(material["text"])
        group["source_ids"].append(material["id"])
        group["sources"].append(
            {key: material[key] for key in ("id", "role", "derived_from") if key in material}
        )
    return {
        "summary": _normalized(substantive)[:500],
        "retrieval_terms": sorted(set(re.findall(r"[\w+#.-]+", "\n".join(texts).casefold()))),
        "material_groups": list(groups.values()),
    }


class ExperienceStore:
    """Save canonical facts before publishing their directory pointers.

    ``derive`` is an optional deterministic index callback. An indexing failure
    leaves a visible pending row and preserves the saved facts for later repair.
    Legacy bodies remain readable; structured revisions never revert to bodies.
    """

    def __init__(
        self,
        root: Path,
        *,
        derive: Callable[[dict[str, object]], dict[str, object]] | None = None,
    ) -> None:
        selected = Path(root).expanduser()
        if selected.is_symlink():
            raise PortalDataError("source-unavailable", "数据目录暂不可用。", 503)
        self.root = selected.resolve()
        _check_root(self.root)
        self.base = self.root / ".tomorrowstar-experiences"
        self._writes = ApplicationStore(self.root)
        self._derive = derive or _derive

    def _safe(self, path: Path) -> None:
        _check_root(self.root)
        try:
            relative = path.relative_to(self.root)
            current = self.root
            for part in relative.parts[:-1]:
                current /= part
                if not stat.S_ISDIR(current.lstat().st_mode):
                    raise OSError("unsafe directory")
        except (OSError, ValueError) as exc:
            raise PortalDataError("experience-unavailable", "经历记录暂不可用。", 503) from exc

    def _read(self, path: Path, *, maximum: int = _MAX_RECORD) -> dict[str, object]:
        self._safe(path)
        try:
            before = path.lstat()
            if not stat.S_ISREG(before.st_mode) or before.st_size > maximum:
                raise OSError("unsafe file")
            descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
            with os.fdopen(descriptor, "rb") as stream:
                opened = os.fstat(stream.fileno())
                if _identity(opened) != _identity(before):
                    raise OSError("changed file")
                raw = stream.read(maximum + 1)
                if len(raw) > maximum or _identity(os.fstat(stream.fileno())) != _identity(opened):
                    raise OSError("changed file")
            self._safe(path)
            if _identity(path.lstat()) != _identity(before):
                raise OSError("changed file")
            value = json.loads(raw)
            if not isinstance(value, dict):
                raise ValueError("invalid record")
            return value
        except (OSError, ValueError, UnicodeError) as exc:
            raise PortalDataError("experience-unavailable", "经历记录暂不可用。", 503) from exc

    def _mkdir(self, path: Path) -> None:
        self._safe(path)
        try:
            path.mkdir(exist_ok=True)
            if not stat.S_ISDIR(path.lstat().st_mode):
                raise OSError("unsafe directory")
        except OSError as exc:
            raise PortalDataError("experience-unavailable", "经历记录暂不可用。", 503) from exc

    @contextmanager
    def _write_lock(self):
        try:
            with self._writes.write_lock():
                yield
        except OSError as exc:
            raise PortalDataError("experience-unavailable", "经历记录暂不可用。", 503) from exc

    def directory(self) -> dict[str, dict[str, object]]:
        """Read discovery rows only; no canonical body or source material text."""
        _check_root(self.root)
        if not os.path.lexists(self.base):
            return {}
        self._safe(self.base / "directory.json")
        path = self.base / "directory.json"
        if not os.path.lexists(path):
            return {}
        value = self._read(path, maximum=_MAX_DIRECTORY)
        for identifier, row in value.items():
            if not isinstance(row, dict) or row.get("candidate_id") != identifier:
                raise _invalid()
            self._entry(identifier, row)
        return value

    def _entry(self, identifier: str, row: dict[str, object]) -> Path:
        revision = row.get("revision")
        if not isinstance(revision, str) or re.fullmatch(r"[a-f0-9]{64}", revision) is None:
            raise _invalid()
        folder = hashlib.sha256(_identifier(identifier).encode("utf-8")).hexdigest()
        path = self.base / folder / f"{revision}.json"
        if row.get("detail_entry") != path.relative_to(self.root).as_posix():
            raise _invalid()
        return path

    def get(self, candidate_id: str) -> dict[str, object]:
        """Return the complete original record, including source provenance."""
        identifier = _identifier(candidate_id)
        row = self.directory().get(identifier)
        if row is None:
            raise PortalDataError("experience-not-found", "经历记录不存在。", 404)
        payload = self._read(self._entry(identifier, row))
        digest = hashlib.sha256(
            _json_bytes({key: value for key, value in payload.items() if key != "revision"})
        ).hexdigest()
        if (
            payload.get("candidate_id") != identifier
            or payload.get("revision") != row["revision"]
            or digest != row["revision"]
        ):
            raise _invalid()
        if "schema_version" in payload or "content" in payload:
            required = {
                "schema_version",
                "content",
                "candidate_id",
                "title",
                "metadata",
                "materials",
                "origin",
                "input_revision",
                "actor",
                "previous_revision",
                "saved_at",
                "event_id",
                "revision",
            }
            if (
                payload.get("schema_version") != "experience-record/v2"
                or not required <= payload.keys()
                or payload.keys() - required - {"migration"}
                or not isinstance(payload["metadata"], dict)
                or not isinstance(payload["materials"], list)
            ):
                raise _invalid()
            _text(payload["title"], required=True)
            _content(payload.get("content"), identifier, payload.get("title"), verify=True)
            _metadata(payload.get("metadata"))
            _materials(payload.get("materials"))
            for key in ("origin", "actor", "saved_at", "event_id"):
                _text(payload[key], required=True, maximum=1024)
            _text(payload["input_revision"], maximum=1024)
            previous = _text(payload["previous_revision"], maximum=64)
            if previous and re.fullmatch(r"[a-f0-9]{64}", previous) is None:
                raise _invalid()
            if "migration" in payload and not isinstance(payload["migration"], dict):
                raise _invalid()
        return payload

    def save(
        self,
        candidate_id: str,
        *,
        title: str,
        body: str | None = None,
        content: dict[str, object] | None = None,
        metadata: dict[str, object] | None = None,
        materials: list[dict[str, object]] | None = None,
        expected_revision: str | None = None,
        origin: str = "user",
        input_revision: str = "",
        actor: str = "user",
        migration: dict[str, object] | None = None,
    ) -> dict[str, object]:
        """Create a record or update it with its exact current revision."""
        identifier = _identifier(candidate_id)
        if (body is None) == (content is None):
            raise _invalid()
        payload: dict[str, object] = {
            "candidate_id": identifier,
            "title": _text(title, required=True),
            "metadata": _metadata(metadata),
            "materials": _materials(materials),
            "origin": _text(origin, required=True, maximum=1024),
            "input_revision": _text(input_revision, maximum=1024),
            "actor": _text(actor, required=True, maximum=1024),
        }
        if content is not None:
            payload["schema_version"] = "experience-record/v2"
            payload["content"] = _content(content, identifier, payload["title"])
        else:
            payload["body"] = _text(body, required=True)
        if migration is not None:
            if not isinstance(migration, dict) or content is None:
                raise _invalid()
            payload["migration"] = json.loads(_json_bytes(migration))
        _json_bytes(payload)
        with self._write_lock():
            rows = self.directory()
            previous = rows.get(identifier)
            if (previous is not None and expected_revision != previous["revision"]) or (
                previous is None and expected_revision is not None
            ):
                raise PortalDataError("revision-conflict", "经历已更新，请刷新后重试。", 409)
            if previous is not None:
                previous_content = self.get(identifier).get("content")
                if previous_content is not None and (
                    content is None
                    or payload["content"]["experience_id"] != previous_content["experience_id"]
                ):
                    raise _invalid()
            payload["previous_revision"] = previous["revision"] if previous else ""
            payload["saved_at"] = datetime.now(UTC).isoformat()
            payload["event_id"] = uuid4().hex
            payload["revision"] = hashlib.sha256(_json_bytes(payload)).hexdigest()
            self._mkdir(self.base)
            folder = self.base / hashlib.sha256(identifier.encode("utf-8")).hexdigest()
            self._mkdir(folder)
            version = folder / f"{payload['revision']}.json"
            _write_file(version, _json_bytes(payload), replace=False)
            row = {
                "candidate_id": identifier,
                "title": payload["title"],
                **payload["metadata"],
                "summary": "",
                "retrieval_terms": [],
                "material_groups": [],
                "detail_entry": version.relative_to(self.root).as_posix(),
                "revision": payload["revision"],
                "origin": payload["origin"],
                "input_revision": payload["input_revision"],
                "index_status": "pending",
            }
            if content is not None:
                row["content_schema"] = payload["content"]["schema_version"]
            try:
                derived = self._derive(json.loads(_json_bytes(payload)))
                row.update(
                    {key: derived[key] for key in ("summary", "retrieval_terms", "material_groups")}
                )
                if payload["metadata"].get("import_status") != "pending":
                    row["index_status"] = "ready"
                _json_bytes(row)
            except Exception:
                # The original facts are saved; failure must not hide the experience.
                row.update(
                    summary="", retrieval_terms=[], material_groups=[], index_status="pending"
                )
            rows[identifier] = row
            path = self.base / "directory.json"
            self._safe(path)
            if os.path.lexists(path) and not stat.S_ISREG(path.lstat().st_mode):
                raise PortalDataError("experience-unavailable", "经历记录暂不可用。", 503)
            raw = json.dumps(rows, ensure_ascii=False, sort_keys=True, allow_nan=False).encode(
                "utf-8"
            )
            if len(raw) > _MAX_DIRECTORY:
                raise PortalDataError("experience-unavailable", "经历目录较大，请整理后重试。", 413)
            _write_file(path, raw, replace=os.path.lexists(path))
            return payload
