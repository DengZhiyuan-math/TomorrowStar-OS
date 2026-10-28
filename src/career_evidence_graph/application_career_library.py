"""Read an explicitly bound career/GitHub library without changing material inputs."""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import subprocess
from copy import deepcopy
from pathlib import Path

from .application_source_reuse import fact_source_projection
from .career_experience_import import pending_materials
from .career_experiences import ExperienceStore, material_identity
from .career_portal_data import PortalDataError
from .validation.hashing import record_digest as digest

MAX_DOCUMENT_BYTES = 2_000_000
MAX_CAPTURE_BYTES = 8_000_000


def _read(path: Path, limit=MAX_DOCUMENT_BYTES) -> bytes:
    if (
        not path.is_absolute()
        or ".." in path.parts
        or any(part.is_symlink() for part in (path, *path.parents))
    ):
        raise ValueError("Unsafe library path.")
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(descriptor, "rb") as source:
        before = os.fstat(source.fileno())
        if not stat.S_ISREG(before.st_mode) or before.st_size > limit:
            raise ValueError("Oversized or invalid library document.")
        raw = source.read(limit + 1)
        after = os.fstat(source.fileno())

    def identity(info):
        return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns)

    if len(raw) > limit or identity(before) != identity(after):
        raise ValueError("Library document changed during reading.")
    return raw


def _bound(root, binding, limit=MAX_DOCUMENT_BYTES):
    relative = Path(binding["path"])
    if relative.is_absolute() or ".." in relative.parts or not relative.parts:
        raise ValueError("Invalid relative source path.")
    raw = _read(root / relative, limit)
    expected = binding["sha256"].removeprefix("sha256:")
    if len(expected) != 64 or hashlib.sha256(raw).hexdigest() != expected:
        raise ValueError("Library source hash mismatch.")
    return raw


def _pointer(value, pointer):
    if not isinstance(pointer, str) or (pointer and not pointer.startswith("/")):
        raise ValueError("Expected an RFC 6901 pointer.")
    for token in pointer.split("/")[1:]:
        token = token.replace("~1", "/").replace("~0", "~")
        if isinstance(value, list):
            if not token.isdecimal() or (len(token) > 1 and token.startswith("0")):
                raise ValueError("Invalid JSON array pointer.")
            value = value[int(token)]
        else:
            value = value[token]
    return value


def _registry(root, descriptor):
    binding = descriptor.get("source_registry")
    if binding is None:
        return {}
    value = json.loads(_bound(root, binding))
    value = value.get("registry", value)
    sources = value["sources"]
    if not isinstance(sources, list) or len(sources) > 10_000:
        raise ValueError("Invalid source registry.")
    result = {source["source_id"]: source for source in sources}
    if len(result) != len(sources):
        raise ValueError("Duplicate source identities.")
    return result


def _thin_record(identifier, row, bound):
    facts = row.get("confirmed_identity_facts", {})
    summary = next(
        (
            value
            for value in (row.get("accepted_reading_summary"), row.get("summary"))
            if isinstance(value, str) and value.strip()
        ),
        "",
    )
    candidate = row.get("candidate")
    description = next(
        (
            value
            for value in (
                (candidate.get("description") if isinstance(candidate, dict) else None),
                row.get("description"),
            )
            if isinstance(value, str) and value.strip()
        ),
        "",
    )
    title = str(row["title"]).strip().casefold()
    descriptive = any(
        value.strip().lstrip("#").strip().casefold() not in {"", title}
        for value in (summary, description)
    )
    # This is discovery context only. Exact cited facts are loaded on selection.
    return {
        "candidate_id": identifier,
        "title": row["title"],
        "category": row.get("formal_category"),
        "record_class": row["record_class"],
        "summary": summary[:2000],
        "description": description[:1000],
        "confirmed_facts_summary": json.dumps(facts, ensure_ascii=False, sort_keys=True)[:6000],
        "source_count": len(row.get("source_links", [])),
        "has_bound_evidence": bound,
        "read_status": "indexed_not_read",
        "authority": "Discovery only; retrieve exact source before citing.",
        "index_status": "legacy_context" if descriptive else "pending",
        "detail_entry": "/api/career-library/" + identifier,
        "requires_body_discovery": not (descriptive),
    }


def _capture_text(raw, locator):
    """Resolve supported locators without guessing at unknown syntax."""
    if raw.startswith(b"%PDF-") or b"\0" in raw:
        raise _CaptureError("unsupported_content_format")
    text = raw.decode("utf-8")
    if locator in ("", "document", "$"):
        return text
    if locator.startswith("/"):
        return json.dumps(_pointer(json.loads(text), locator), ensure_ascii=False, sort_keys=True)
    lines = re.fullmatch(r"(?:[^#]+#)?L([1-9][0-9]*)(?:-L?([1-9][0-9]*))?", locator)
    if lines:
        start, end = int(lines[1]), int(lines[2] or lines[1])
        values = text.splitlines(keepends=True)
        if end < start or end > len(values):
            raise ValueError("Source line range unavailable.")
        return "".join(values[start - 1 : end])
    if re.fullmatch(r"(?:\$\.)?[A-Za-z_][A-Za-z_0-9-]*(?:\.[A-Za-z_][A-Za-z_0-9-]*)*", locator):
        value = json.loads(text)
        for key in locator.removeprefix("$.").split("."):
            value = value[key]
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    raise ValueError("Unsupported source locator.")


class _CaptureError(ValueError):
    def __init__(self, status):
        self.status = status
        super().__init__(status)


def _file_bytes(capture, relative, expected):
    """Read only the inventory's declared file or pinned local Git object."""
    path = Path(relative)
    if path.is_absolute() or ".." in path.parts or "\\" in relative or not path.parts:
        raise _CaptureError("unsupported_locator")
    for retained in capture.get("retained_source_files", []):
        origin = str(retained.get("origin", ""))
        if retained.get("file_hash") == expected and (
            origin == relative or origin.endswith("/" + relative)
        ):
            raw = retained["utf8"].encode("utf-8")
            if len(raw) <= MAX_DOCUMENT_BYTES and hashlib.sha256(
                raw
            ).hexdigest() == expected.removeprefix("sha256:"):
                return raw, origin
            raise _CaptureError("hash_mismatch")
    entries = [row for row in capture.get("files", []) if row.get("path") == relative]
    if len(entries) != 1 or entries[0].get("sha256") != expected:
        raise _CaptureError("hash_mismatch")
    if (
        entries[0].get("type") != "file"
        or entries[0].get("size", MAX_DOCUMENT_BYTES + 1) > MAX_DOCUMENT_BYTES
    ):
        raise _CaptureError("unavailable")
    configured = Path(capture.get("project", {}).get("configured_path", ""))
    if not configured.is_absolute() or ".." in configured.parts:
        raise _CaptureError("unavailable")
    # The captured project declaration may use a root alias. Descendant links are forbidden.
    root = configured.resolve(strict=True)
    file_path = root / path
    if any(part.is_symlink() for part in (file_path, *file_path.parents)):
        raise _CaptureError("unavailable")
    try:
        raw = _read(file_path)
        if hashlib.sha256(raw).hexdigest() == expected.removeprefix("sha256:"):
            return raw, str(file_path)
    except (OSError, ValueError):
        pass
    head = capture.get("git", {}).get("head", "")
    if not isinstance(head, str) or re.fullmatch(r"[a-f0-9]{40}|[a-f0-9]{64}", head) is None:
        raise _CaptureError("unpinned_git_revision")
    environment = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}
    environment.update(GIT_NO_REPLACE_OBJECTS="1", GIT_CONFIG_NOSYSTEM="1")
    command = ["git", "--no-pager", "-C", str(root), "cat-file"]
    try:
        size = subprocess.run(
            command + ["-s", head + ":" + relative],
            check=True,
            capture_output=True,
            timeout=5,
            env=environment,
        )
        if not size.stdout.strip().isdigit() or int(size.stdout) > MAX_DOCUMENT_BYTES:
            raise _CaptureError("unavailable")
        result = subprocess.run(
            command + ["blob", head + ":" + relative],
            check=True,
            capture_output=True,
            timeout=5,
            env=environment,
        )
    except (OSError, subprocess.SubprocessError):
        raise _CaptureError("unavailable") from None
    if len(result.stdout) > MAX_DOCUMENT_BYTES or hashlib.sha256(
        result.stdout
    ).hexdigest() != expected.removeprefix("sha256:"):
        raise _CaptureError("hash_mismatch")
    return result.stdout, str(file_path)


def _legacy_presentation_tex(text):
    """Detect document macros while retaining literal paths and mathematical evidence.

    Custom template macros take braced arguments, so the boundary is syntax rather
    than a fixed list of résumé macro names. Mathematical expressions are valid
    documentary facts and are not presentation-only experience records.
    """
    prose = re.sub(
        r"\\begin\{(equation|align|gather|multline|displaymath|math)\*?\}.*?"
        r"\\end\{\1\*?\}",
        "",
        text,
        flags=re.DOTALL,
    )
    prose = re.sub(
        r"\$\$.*?\$\$|(?<!\\)\$[^$]*?(?<!\\)\$|\\\(.*?\\\)|\\\[.*?\\\]", "", prose, flags=re.DOTALL
    )
    math_commands = {
        "frac",
        "dfrac",
        "tfrac",
        "sqrt",
        "mathbf",
        "mathrm",
        "mathit",
        "mathsf",
        "mathbb",
        "mathcal",
        "operatorname",
        "text",
        "overline",
        "underline",
        "vec",
        "hat",
        "bar",
        "dot",
        "ddot",
        "tilde",
        "widehat",
        "TeX",
        "LaTeX",
        "n",
        "r",
        "t",
    }
    for command in re.finditer(r"\\([A-Za-z@]+)\*?(?:\s*\[[^\]\n]*\])?\s*(?=\{)", prose):
        if command[1] not in math_commands:
            return True
    return bool(re.search(r"\\(?:item|hfill|vfill|newpage|clearpage|maketitle|noindent)\b", prose))


def _saved_experience(root, identifier, *, user_saved=False):
    experience = ExperienceStore(root).get(identifier)
    if user_saved and experience["origin"] != "user":
        raise PortalDataError("experience-unavailable", "已保存经历的来源身份不能核验。", 503)
    return experience


class CareerLibrary:
    """A thin identity index plus demand-read, hash-bound documentary captures."""

    def __init__(self, manifest: Path | None):
        self.manifest = Path(manifest).expanduser().absolute() if manifest else None

    def save_experience(self, candidate_id, **changes):
        """Save explicit career content; résumé wording never enters this API implicitly."""
        if "migration" in changes:
            raise PortalDataError(
                "experience-import-required", "经历来源覆盖记录只能通过显式导入生成。", 409
            )
        _, root, _, current = self._load()
        if candidate_id not in current:
            raise PortalDataError("experience-not-found", "经历不存在。", 404)
        store = ExperienceStore(root)
        if candidate_id in store.directory():
            before = store.get(candidate_id)
            explicit_content_edit = (
                "body" in changes and changes["body"] != before.get("body")
            ) or (
                isinstance(changes.get("content"), dict)
                and any(
                    changes["content"].get(key) != value
                    for key, value in before.get("content", {}).items()
                    if key != "revision"
                )
            )
            if "content" not in before and "content" in changes:
                raise PortalDataError(
                    "experience-import-required", "请先校验经历来源的结构化导入覆盖。", 409
                )
            if "content" in before:
                changes.setdefault("content", before["content"])
                changes.setdefault("migration", before.get("migration"))
            elif "content" not in changes:
                changes.setdefault("body", before["body"])
            supplied_metadata = changes.get("metadata", {})
            metadata = {**before["metadata"], **supplied_metadata}
            metadata["manual_fields"] = sorted(
                (
                    set(before["metadata"].get("manual_fields", []))
                    | changes.get("metadata", {}).keys()
                )
                - {"manual_fields", "import_status", "unavailable_sources"}
            )
            changes["metadata"] = metadata
            if explicit_content_edit:
                metadata["unavailable_sources"] = supplied_metadata.get("unavailable_sources", [])
            else:
                metadata["unavailable_sources"] = before["metadata"].get("unavailable_sources", [])
            metadata["import_status"] = supplied_metadata.get(
                "import_status",
                before["metadata"].get("import_status", "complete")
                if not explicit_content_edit
                else "complete",
            )
            if not explicit_content_edit and before["metadata"].get("import_status") == "pending":
                metadata["import_status"] = "pending"
            changes.setdefault("title", before["title"])
            historical = [
                {**item, "role": "history"}
                if item.get("source_managed")
                and (item["role"] == "primary" or "materials" in changes)
                else item
                for item in before["materials"]
                if item.get("source_managed") or "materials" not in changes
            ]
            explicit = changes.get("materials", [])
            identifiers = {item["id"] for item in explicit}
            changes["materials"] = explicit + [
                item for item in historical if item["id"] not in identifiers
            ]
            changes.setdefault("input_revision", before["input_revision"])
            if "content" in changes and pending_materials(changes):
                metadata["import_status"] = "pending"
        return store.save(candidate_id, **changes)

    def preview_experience_import(self, candidate_id, request):
        """Validate explicit source mappings without modifying any stored record."""
        from .career_experience_import import prepare_experience_import

        return prepare_experience_import(self.read_experience(candidate_id), request)

    def import_experience(self, candidate_id, request):
        """Publish a fully covered explicit import through the existing CAS store."""
        plan = self.preview_experience_import(candidate_id, request)
        if not plan["ready"]:
            raise PortalDataError("experience-import-incomplete", "经历导入仍有未处理来源。", 409)
        before = self.read_experience(candidate_id)
        _, root, _, _ = self._load()
        return ExperienceStore(root).save(
            candidate_id,
            title=plan["content"]["title"],
            content=plan["content"],
            migration=plan["migration"],
            metadata={
                **before["metadata"],
                "import_status": "pending"
                if before["metadata"].get("unavailable_sources")
                or (
                    before["metadata"].get("import_status") == "pending"
                    and not pending_materials(before)
                )
                else "complete",
            },
            materials=before["materials"],
            expected_revision=plan["expected_revision"],
            input_revision=before["input_revision"],
            origin="user",
            actor="structured-import",
        )

    def read_experience(self, candidate_id):
        _, root, _, current = self._load()
        if candidate_id not in current:
            raise PortalDataError("experience-not-found", "经历不存在。", 404)
        return _saved_experience(
            root,
            candidate_id,
            user_saved=current[candidate_id].get("application_saved_only", False),
        )

    def sync_experiences(self, candidate_ids=None):
        """Organize saved sources once, then refresh only changed experience inputs.

        Copy literal source sections rather than inventing a narrative. A later
        explicit edit owns the body; source refreshes retain that text and history.
        No source/research manifest or existing application material is rewritten.
        """
        descriptor, root, _, current = self._load()
        selected = set(current) if candidate_ids is None else set(candidate_ids)
        if not selected <= current.keys():
            raise PortalDataError("experience-not-found", "请选择当前经历。", 404)
        registry = _registry(root, descriptor)
        store = ExperienceStore(root)
        directory = store.directory()
        updated, unchanged, pending = [], [], []
        for identifier in sorted(selected):
            row = current[identifier]
            signature = digest(
                {
                    "record": row,
                    "evidence": [
                        value
                        for value in descriptor.get("evidence", [])
                        if value["candidate_id"] == identifier
                    ],
                    "sources": {
                        link["source_id"]: registry.get(link["source_id"])
                        for link in row.get("source_links", [])
                    },
                }
            )
            previous = directory.get(identifier)
            if (
                previous
                and previous.get("input_revision") == signature
                and previous.get("index_status") == "ready"
            ):
                unchanged.append(identifier)
                continue
            before = store.get(identifier) if previous else None
            metadata = {
                "category": row.get("formal_category") or "",
                "aliases": row.get("aliases", []),
                "related_ids": row.get("related_ids", []),
                "links": row.get("links", []),
                "import_status": "complete",
                "unavailable_sources": [],
            }
            facts = row.get("confirmed_identity_facts", {})
            for field in ("institution", "dates", "status"):
                value = facts.get(field, row.get(field, ""))
                metadata[field] = value if isinstance(value, str) else json.dumps(value)
            materials = []
            try:
                historical_keys = (
                    {
                        item["source_key"]
                        for item in before["materials"]
                        if item.get("source_managed") and item["role"] in {"primary", "history"}
                    }
                    if before and ("content" in before or before["origin"] != "imported")
                    else set()
                )
                snapshot = self.snapshot_for_analysis(
                    {"documents": [], "items": []},
                    [identifier],
                    _use_experiences=False,
                    _skip_source_keys=historical_keys,
                )
                failed = snapshot["career_library"]["unavailable_sources"]
                metadata["import_status"] = "pending" if failed else "complete"
                metadata["unavailable_sources"] = [
                    str(
                        item.get("source_id")
                        or item.get("source_name")
                        or item.get("path")
                        or identifier
                    )
                    for item in failed
                ]
                for item in snapshot["items"]:
                    materials.append(
                        {
                            "id": item["source_id"],
                            "source_name": item["source_name"],
                            "text": item["text"],
                            "role": "primary",
                            "locator": item["locator"],
                            "source_revision": item["source_revision"],
                            "attribution": item["attribution"],
                            "boundaries": item["boundaries"],
                            "source_managed": True,
                            "source_key": "identity:" + identifier
                            if item["source_name"] == descriptor["catalog"]["path"]
                            and item["locator"].startswith("/records/")
                            else item.get(
                                "registered_source_key",
                                item["source_name"] + ":" + item["locator"],
                            ),
                        }
                    )
            except PortalDataError:
                metadata["import_status"] = "pending"
                metadata["unavailable_sources"] = [identifier]
            sections, seen = [], set()
            for material in materials:
                key = material_identity(material)
                if key not in seen:
                    sections.append(
                        "## "
                        + material["source_name"]
                        + "\n\n"
                        + "Attribution: "
                        + material["attribution"]
                        + "\n\n"
                        + "Scope: "
                        + material["boundaries"]
                        + "\n\n"
                        + material["text"]
                    )
                    seen.add(key)
            body = "# " + row["title"] + "\n\n" + "\n\n".join(sections)
            if not sections:
                body += json.dumps(facts, ensure_ascii=False, sort_keys=True)
            title, origin = row["title"], "imported"
            if before and ("content" in before or before["origin"] != "imported"):
                body, title, origin = before.get("body"), before["title"], before["origin"]
                # Refresh supplements without restoring superseded primary facts.
                manual_fields = [
                    field
                    for field in before["metadata"].get("manual_fields", [])
                    if field not in {"manual_fields", "import_status", "unavailable_sources"}
                ]
                metadata.update({field: before["metadata"][field] for field in manual_fields})
                metadata["manual_fields"] = manual_fields
                previous_sources = {
                    item["source_key"]: item
                    for item in before["materials"]
                    if item.get("source_managed")
                }
                refreshed = []
                for item in materials:
                    old = previous_sources.get(item["source_key"])
                    historical = old and old["role"] in {"primary", "history"}
                    refreshed.append({**item, "role": "history" if historical else "supplement"})
                new_keys = {item["source_key"] for item in refreshed}
                materials = refreshed + [
                    item
                    for item in before["materials"]
                    if not item.get("source_managed")
                    or (item["role"] == "history" and item["source_key"] not in new_keys)
                ]
            content = before.get("content") if before else None
            if content is not None and pending_materials(
                {"materials": materials, "migration": before.get("migration", {})}
            ):
                metadata["import_status"] = "pending"
            store.save(
                identifier,
                title=title,
                **(
                    {"content": content, "migration": before.get("migration")}
                    if content is not None
                    else {"body": body}
                ),
                metadata=metadata,
                materials=materials,
                expected_revision=before["revision"] if before else None,
                origin=origin,
                input_revision=signature,
                actor="source-sync",
            )
            updated.append(identifier)
            if store.directory()[identifier]["index_status"] != "ready":
                pending.append(identifier)
        return {"updated": updated, "unchanged": unchanged, "pending": pending}

    def _load(self):
        if self.manifest is None:
            raise ValueError("No library configured.")
        descriptor = json.loads(_read(self.manifest))
        if descriptor.get("schema_version") != 1:
            raise ValueError("Unsupported library manifest.")
        root = Path(descriptor["root"])
        if (
            not root.is_absolute()
            or not root.is_dir()
            or any(part.is_symlink() for part in (root, *root.parents))
        ):
            raise ValueError("Invalid library root.")
        raw = _bound(root, descriptor["catalog"])
        catalog = json.loads(raw)
        records = catalog["records"]
        if not isinstance(records, list) or len(records) > 10_000:
            raise ValueError("Invalid career index.")
        current = {
            row["candidate_id"]: row
            for row in records
            if row.get("record_class") == "current-confirmed-identity"
        }
        # Application facts saved explicitly by the user do not require a research
        # assessment successor. Preserve the original research record and decision.
        catalog_rows = {row["candidate_id"]: row for row in records}
        try:
            saved_experiences = ExperienceStore(root).directory()
        except (OSError, ValueError):
            # The index reports this failure through its existing directory status.
            saved_experiences = {}
        for identifier, saved in saved_experiences.items():
            if identifier not in current and saved.get("origin") == "user":
                current[identifier] = {
                    **catalog_rows.get(identifier, {}),
                    "candidate_id": identifier,
                    "title": saved["title"],
                    "application_saved_only": True,
                    "record_class": catalog_rows.get(identifier, {}).get(
                        "record_class", "application-saved-experience"
                    ),
                }
        bindings = descriptor.get("evidence", [])
        if not isinstance(bindings, list) or len(bindings) > 128:
            raise ValueError("Invalid evidence bindings.")
        if any(binding.get("candidate_id") not in current for binding in bindings):
            raise ValueError("Evidence must belong to a current indexed identity.")
        _registry(root, descriptor)
        return descriptor, root, catalog, current

    def index(self):
        if self.manifest is None:
            return {"status": "unconfigured", "records": [], "revision": digest(None)}
        try:
            descriptor, root, catalog, current = self._load()
            bound = {
                row["candidate_id"]
                for row in descriptor.get("evidence", [])
                if row.get("role") != "generated"
            }
            registry = _registry(root, descriptor)
            if descriptor.get("source_registry"):
                bound.update(
                    identifier
                    for identifier, row in current.items()
                    if any(
                        link.get("source_id") in registry and link.get("role") != "generated"
                        for link in row.get("source_links", [])
                    )
                )
            records = [
                _thin_record(
                    identifier,
                    row,
                    identifier in bound
                    or any(
                        link.get("source_id") in registry and link.get("role") != "generated"
                        for link in row.get("source_links", [])
                    ),
                )
                for identifier, row in current.items()
            ]
            directory_error = False
            try:
                directory = ExperienceStore(root).directory()
            except (OSError, ValueError):
                directory, directory_error = {}, True
            records = [
                {
                    **{
                        key: value
                        for key, value in record.items()
                        if record["candidate_id"] not in directory
                        or key not in {"confirmed_facts_summary", "description"}
                    },
                    **directory.get(record["candidate_id"], {}),
                }
                for record in records
            ]
            bound.update(set(directory) & current.keys())
            for record in records:
                if record["candidate_id"] in directory:
                    record["has_bound_evidence"] = True
                    record["requires_body_discovery"] = (
                        record.get("index_status") != "ready"
                        or not str(record.get("summary", "")).strip()
                        or not record.get("retrieval_terms")
                    )
            # Discovery verifies the directory and manifest bindings, not every source body.
            unavailable = []
            identity = {"manifest": descriptor, "catalog": catalog}
            if directory or directory_error:
                identity["experiences"] = directory
                identity["directory_error"] = directory_error
            if unavailable:
                identity["unavailable_sources"] = unavailable
            revision = digest(identity)
            return {
                "status": "unavailable" if directory_error else "available",
                "revision": revision,
                "root": str(root),
                "catalog": descriptor["catalog"],
                "records": records,
                "experience_directory_status": "unavailable" if directory_error else "available",
                "coverage": {
                    "indexed_records": len(catalog["records"]),
                    "current_records": len(current),
                    "bound_candidates": len(bound),
                    "unbound_candidates": len(current) - len(bound),
                    "loaded_evidence": 0,
                    "unavailable_sources": unavailable,
                },
                "authority": (
                    "Documentary identity and source evidence; no skill mastery inference."
                ),
            }
        except (OSError, ValueError, KeyError, TypeError, UnicodeError, RecursionError):
            return {"status": "unavailable", "records": [], "revision": digest("unavailable")}

    def snapshot_for_analysis(
        self, base_snapshot, candidate_ids=None, *, _use_experiences=True, _skip_source_keys=()
    ):
        """Load only explicitly selected candidate records and their bound captures."""
        try:
            descriptor, root, catalog, current = self._load()
            bindings = descriptor.get("evidence", [])
            directory = ExperienceStore(root).directory() if _use_experiences else {}
            selected = (
                (
                    set()
                    if descriptor.get("source_registry") or directory
                    else {row["candidate_id"] for row in bindings}
                )
                if candidate_ids is None
                else set(candidate_ids)
            )
            if not selected <= current.keys():
                raise ValueError("Select current candidate IDs only.")
            requested = set(selected)
            snapshot = (
                fact_source_projection(base_snapshot)
                if _use_experiences
                else deepcopy(base_snapshot)
            )
            documents, items, unavailable = [], [], []
            source_reads = []
            identity_reads = []
            capture_cache = {}
            registry = _registry(root, descriptor)
            pending = list(sorted(selected))
            while pending:
                identifier = pending.pop()
                for related in directory.get(identifier, {}).get("related_ids", []):
                    if related in selected:
                        continue
                    if related not in current:
                        outcome = {
                            "candidate_id": related,
                            "related_from": identifier,
                            "status": "related_identity_unavailable",
                        }
                        unavailable.append(outcome)
                        source_reads.append(dict(outcome))
                        continue
                    selected.add(related)
                    pending.append(related)
            managed = selected & directory.keys()

            def append_source(binding, text, attribution, boundaries):
                if (
                    _use_experiences
                    and "fact_id" not in binding.get("record_context", {})
                    and _legacy_presentation_tex(text)
                ):
                    snapshot.setdefault("retained_materials", []).append(
                        {**deepcopy(binding), "text": text, "import_status": "import_pending"}
                    )
                    outcome = {
                        "candidate_id": binding["candidate_id"],
                        "locator": binding.get("locator", binding.get("pointer", "document")),
                        "status": "legacy_tex_import_pending",
                    }
                    unavailable.append(outcome)
                    source_reads.append(dict(outcome))
                    return
                revision = binding["sha256"].removeprefix("sha256:")
                identifier = "career-library:" + digest(binding)
                name = binding["path"]
                locator = binding.get("locator", binding.get("pointer", "document"))
                documents.append(
                    {
                        "id": identifier,
                        "source_name": name,
                        "kind": "source",
                        "available": True,
                        "revision": revision,
                        "content": text,
                    }
                )
                items.append(
                    {
                        "title": binding.get("title", current[binding["candidate_id"]]["title"]),
                        "text": text,
                        "source_id": identifier + ":" + locator,
                        "evidence_id": identifier,
                        "source_name": name,
                        "source_revision": revision,
                        "locator": locator,
                        "attribution": attribution,
                        "boundaries": boundaries,
                        "review_status": "documentary",
                        "resume_eligible": True,
                        "documentary_only": True,
                        "rewrite_allowed": False,
                        "candidate_id": binding["candidate_id"],
                        **(
                            {"record_context": deepcopy(binding["record_context"])}
                            if "record_context" in binding
                            else {}
                        ),
                        **(
                            {
                                "registered_source_id": binding["registered_source_id"],
                                "registered_source_key": binding["registered_source_key"],
                            }
                            if "registered_source_id" in binding
                            else {}
                        ),
                        **(
                            {
                                "requested_locator": binding["requested_locator"],
                                "source_read_status": "read_whole_document",
                            }
                            if "requested_locator" in binding
                            else {}
                        ),
                        **(
                            {"source_capture_revision": binding["capture_sha256"]}
                            if "capture_sha256" in binding
                            else {}
                        ),
                    }
                )

            for identifier in sorted(managed):
                try:
                    experience = _saved_experience(
                        root,
                        identifier,
                        user_saved=current[identifier].get("application_saved_only", False),
                    )
                    if "content" in experience:
                        facts = experience["content"]
                        contents = []
                        for fact in facts["facts"]:
                            context = {
                                "experience_id": facts["experience_id"],
                                "candidate_id": identifier,
                                "experience_revision": experience["revision"],
                                "content_revision": facts["revision"],
                                "sources": deepcopy(facts["sources"]),
                                "title": facts["title"],
                                **{
                                    key: facts.get(key)
                                    for key in ("role", "organization", "start", "end", "location")
                                },
                                "fact_id": fact["id"],
                                **{
                                    key: fact[key]
                                    for key in ("responsibility", "status", "scope", "source_refs")
                                },
                            }
                            contents.append(
                                (
                                    "facts/" + fact["id"],
                                    fact["text"],
                                    "Responsibility: " + fact["responsibility"],
                                    "Status: " + fact["status"] + "; scope: " + fact["scope"],
                                    context,
                                )
                            )
                    else:
                        # The primary body supersedes the original loose source candidates.
                        content = experience["body"]
                        context = {
                            "title": experience["title"],
                            "metadata": experience["metadata"],
                        }
                        default_attribution = (
                            "Saved career facts; preserve personal and team roles as recorded."
                        )
                        default_boundaries = (
                            "Preserve roles, dates, status and actual results; "
                            "no mastery inference."
                        )
                        contents = [
                            ("body", content, default_attribution, default_boundaries, context)
                        ]
                        seen = {material_identity({"text": experience["body"]})}
                        for material in experience["materials"]:
                            if material["role"] in {"history", "generated"} or (
                                material["role"] == "primary" and material.get("source_managed")
                            ):
                                continue
                            key = material_identity(material)
                            if key[0] and key not in seen:
                                material_context = {
                                    **context,
                                    "material": {
                                        key: value
                                        for key, value in material.items()
                                        if key != "text"
                                    },
                                }
                                contents.append(
                                    (
                                        material["id"],
                                        material["text"],
                                        material.get("attribution", default_attribution),
                                        material.get("boundaries", default_boundaries),
                                        material_context,
                                    )
                                )
                                seen.add(key)
                    for locator, text, attribution, boundaries, record_context in contents:
                        append_source(
                            {
                                "candidate_id": identifier,
                                "title": experience["title"],
                                "path": directory[identifier]["detail_entry"],
                                "sha256": digest(
                                    {
                                        "text": text,
                                        "record_context": record_context,
                                        "attribution": attribution,
                                        "boundaries": boundaries,
                                    }
                                ),
                                "locator": locator,
                                "record_context": record_context,
                            },
                            text,
                            attribution,
                            boundaries,
                        )
                    source_reads.append({"candidate_id": identifier, "status": "read"})
                    if "content" in experience:
                        for material in pending_materials(experience):
                            outcome = {
                                "candidate_id": identifier,
                                "material_id": material["id"],
                                "source_name": material["source_name"],
                                "status": "structured_import_pending",
                            }
                            unavailable.append(outcome)
                            source_reads.append(dict(outcome))
                    if experience["metadata"].get("import_status") == "pending":
                        outcome = {"candidate_id": identifier, "status": "import_pending"}
                        unavailable.append(outcome)
                        source_reads.append(dict(outcome))
                    for source in experience["metadata"].get("unavailable_sources", []):
                        outcome = {
                            "candidate_id": identifier,
                            "source_id": source,
                            "status": "unavailable",
                        }
                        unavailable.append(outcome)
                        source_reads.append(dict(outcome))
                except (OSError, ValueError):
                    outcome = {"candidate_id": identifier, "status": "unavailable"}
                    unavailable.append(outcome)
                    source_reads.append(dict(outcome))

            for index, row in enumerate(catalog["records"]):
                identifier = row.get("candidate_id")
                if (
                    identifier not in selected
                    or identifier in managed
                    or "identity:" + identifier in _skip_source_keys
                ):
                    continue
                binding = {
                    **descriptor["catalog"],
                    "candidate_id": identifier,
                    "pointer": f"/records/{index}",
                    "locator": f"/records/{index}",
                }
                identity_reads.append({"candidate_id": identifier, "status": "read_identity"})
                append_source(
                    binding,
                    json.dumps(
                        {
                            key: row[key]
                            for key in (
                                "candidate_id",
                                "title",
                                "formal_category",
                                "record_class",
                                "confirmed_identity_facts",
                                "uncertainty_notes",
                            )
                            if key in row
                        }
                        if descriptor.get("source_registry")
                        else row,
                        ensure_ascii=False,
                        sort_keys=True,
                    ),
                    "Confirmed record identity; responsibility only as explicitly documented.",
                    "Identity, discovery and repository names alone do not prove personal coding, "
                    "autonomy, completion or mastery. "
                    + " ".join(row.get("uncertainty_notes", [])),
                )
            for identifier in sorted(selected):
                if identifier in managed:
                    continue
                row = current[identifier]
                for link in (
                    row.get("source_links", []) if descriptor.get("source_registry") else []
                ):
                    outcome = {
                        "candidate_id": identifier,
                        "source_id": link.get("source_id"),
                        "locator": link.get("locator"),
                        "status": "unavailable",
                    }
                    if link.get("role") == "discovery-only":
                        outcome["status"] = "discovery_only"
                        source_reads.append(outcome)
                        continue
                    if link.get("role") == "generated":
                        outcome["status"] = "generated_not_indexed"
                        source_reads.append(outcome)
                        continue
                    if (
                        link["source_id"] + ":" + link.get("locator", "document")
                        in _skip_source_keys
                    ):
                        continue
                    try:
                        source = registry[link["source_id"]]
                        capture_hash = source["capture"]["content_hash"]
                        if source.get("availability") != "available":
                            raise ValueError("Registered capture unavailable.")
                        binding = {
                            "candidate_id": identifier,
                            "registered_source_id": link["source_id"],
                            "registered_source_key": link["source_id"]
                            + ":"
                            + link.get("locator", "document"),
                            "path": ".career-evidence/raw/" + capture_hash.removeprefix("sha256:"),
                            "sha256": capture_hash,
                            "locator": link.get("locator", "document"),
                        }
                        if capture_hash not in capture_cache:
                            try:
                                raw = _bound(root, binding, MAX_CAPTURE_BYTES)
                            except ValueError as exc:
                                raise _CaptureError(
                                    "hash_mismatch"
                                    if "hash mismatch" in str(exc)
                                    else "unavailable"
                                ) from exc
                            capture_cache[capture_hash] = raw
                        raw = capture_cache[capture_hash]
                        if link["content_identity"] != capture_hash:
                            aggregate = json.loads(raw)
                            if not isinstance(aggregate, dict):
                                raise _CaptureError("unsupported_content_format")
                            relative, marker, fragment = binding["locator"].partition("#")
                            if not marker:
                                raise _CaptureError("unsupported_locator")
                            raw, name = _file_bytes(aggregate, relative, link["content_identity"])
                            binding.update(
                                path=name,
                                sha256=link["content_identity"],
                                locator=fragment,
                                capture_sha256=capture_hash,
                            )
                        try:
                            text = _capture_text(raw, binding["locator"])
                        except _CaptureError:
                            raise
                        except UnicodeError as exc:
                            raise _CaptureError("unsupported_content_format") from exc
                        except ValueError as exc:
                            if binding.get("capture_sha256") and binding["path"].endswith(
                                (".js", ".ts")
                            ):
                                text = raw.decode("utf-8")
                                binding.update(
                                    requested_locator=binding["locator"], locator="captured_file"
                                )
                                outcome["whole_document"] = True
                            else:
                                raise _CaptureError("unsupported_locator") from exc
                        attribution = (
                            "Registered documentary capture; "
                            "responsibility only as explicitly recorded."
                        )
                        boundaries = (
                            "Preserve planned work, team attribution and unaudited duties; "
                            "no mastery inference."
                        )
                        if link.get("role") == "discovery-only":
                            outcome["status"] = "discovery_only"
                        else:
                            append_source(binding, text, attribution, boundaries)
                            outcome["status"] = (
                                "read_whole_document" if outcome.get("whole_document") else "read"
                            )
                    except _CaptureError as exc:
                        outcome["status"] = exc.status
                        unavailable.append(dict(outcome))
                    except (OSError, UnicodeError, ValueError, KeyError, TypeError, IndexError):
                        unavailable.append(dict(outcome))
                    source_reads.append(outcome)
            for binding in bindings:
                if binding["candidate_id"] not in selected or binding["candidate_id"] in managed:
                    continue
                if binding.get("role") == "generated":
                    continue
                source_key = (
                    binding["path"]
                    + ":"
                    + binding.get("locator", binding.get("pointer", "document"))
                )
                if source_key in _skip_source_keys:
                    continue
                outcome = {
                    "candidate_id": binding["candidate_id"],
                    "path": binding.get("path"),
                    "status": "unavailable",
                }
                try:
                    raw = _bound(root, binding)
                    text = raw.decode("utf-8")
                    if "pointer" in binding:
                        text = json.dumps(
                            _pointer(json.loads(text), binding["pointer"]),
                            ensure_ascii=False,
                            sort_keys=True,
                        )
                    append_source(
                        binding,
                        text,
                        binding.get("attribution", "Documentary source; authorship not inferred."),
                        binding.get(
                            "boundaries", "No personal responsibility or mastery inferred."
                        ),
                    )
                    outcome["status"] = "read"
                except (OSError, UnicodeError, ValueError, KeyError, TypeError, IndexError):
                    unavailable.append(dict(outcome))
                source_reads.append(outcome)
            source_reads.extend(identity_reads)
            source_reads.extend(
                {"candidate_id": identifier, "status": "indexed_not_read"}
                for identifier in sorted(current.keys() - selected)
            )
            snapshot["documents"].extend(documents)
            snapshot["items"].extend(items)
            if descriptor.get("application_policy") == "trusted-library/v1":
                snapshot["application_library_policy"] = "trusted-library/v1"
                for item in items:
                    item["application_trusted"] = True
                    item["resume_eligible"] = True
                    item.setdefault(
                        "boundaries", "Preserve the recorded role, project status and facts."
                    )

            index = self.index()
            if index["status"] != "available":
                raise ValueError("Career directory unavailable.")
            snapshot["career_library"] = {
                "status": "available",
                "root": str(root),
                "revision": index["revision"],
                "catalog": descriptor["catalog"],
                "canonical_sources": bool(descriptor.get("source_registry") or directory),
                "records": index.get("records", []),
                "source_reads": source_reads,
                "requested_candidate_ids": sorted(requested),
                "selected_candidate_ids": sorted(selected),
                "loaded_sources": len(items),
                "unavailable_sources": unavailable,
            }
            snapshot["coverage"] = {
                **snapshot.get("coverage", {}),
                "total_documents": len(snapshot["documents"]),
                "available_documents": sum(row["available"] for row in snapshot["documents"]),
                "career_library": snapshot["career_library"],
            }
            snapshot.pop("revision", None)
            snapshot["revision"] = digest(snapshot)
            return snapshot
        except (OSError, ValueError, KeyError, TypeError, UnicodeError, RecursionError) as exc:
            raise PortalDataError(
                "career_library_unavailable", "经历与 GitHub 库暂不能安全读取。", 409
            ) from exc
