"""Local file adapters for career documents and the Hermes application-note format.

The application format is compatible with the separate job application's tracker
``hermes.skills.manual_job_profile``. No legacy code, mailbox client or private
seed data is imported. Application JSON is canonical; original notes remain
preserved import evidence.
"""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
import re
import stat
import subprocess
import sys
import tempfile
from collections import OrderedDict
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, date, datetime
from pathlib import Path
from threading import RLock
from uuid import uuid4

STATUS_LABELS = {
    "drafting": "准备投递",
    "applied": "已投递",
    "confirmation_received": "已确认收到",
    "waiting": "等待回复",
    "recruiter_replied": "招聘方已回复",
    "interview_scheduled": "面试已安排",
    "assessment_pending": "待完成测评",
    "assessment_submitted": "测评已提交",
    "offer": "已获 Offer",
    "rejected": "未通过",
    "withdrawn": "已撤回",
    "follow_up_optional": "可跟进",
    "likely_no_response": "可能无回复",
    "no_response": "无回复",
}
TRACKS = (
    "AI/ML",
    "Quant",
    "Research",
    "Education",
    "Software Engineering",
    "Data Science",
    "Other",
)
APPLICATION_DECISIONS = {
    "application_strategy": {"", "batch", "manual", "hold"},
    "jd_match": {"", "strong", "possible", "weak"},
    "evidence_match": {"", "direct", "transferable", "missing"},
    "personal_priority": {"", "high", "normal", "low"},
    "target_company": {"", "target", "normal"},
    "compensation_priority": {"", "exceptional", "normal"},
}
_ACTION_STATUSES = {
    "drafting",
    "recruiter_replied",
    "interview_scheduled",
    "assessment_pending",
    "follow_up_optional",
}
_TEXT_FIELDS = (
    {
        "company",
        "role_title",
        "status",
        "track",
        "location",
        "url",
        "application_date",
        "deadline",
        "contact",
        "contact_email",
        "source",
        "resume_version",
        "next_action",
        "notes",
        "job_description",
    }
    | APPLICATION_DECISIONS.keys()
    | {"strategy_notes"}
)
_BOOL_FIELDS = {"needs_action", "referral_used", "cover_letter_used"}
_BODY_FIELDS = {
    "next_action": "Next Action",
    "notes": "Hermes Notes",
    "job_description": "Job Description",
    "strategy_notes": "Application Strategy",
}
_TRACKER_HEADINGS = {
    "Application Strategy",
    "Snapshot",
    "Next Action",
    "Fit Notes",
    "Hermes Notes",
    "Job Description",
    "Email Extract",
    "Email Text",
    "Job Description / Email Draft",
    "Source Email Content",
    "Outcome Email",
    "Raw Text",
    "History",
}
_SECTION_BOUNDARY = re.compile(
    r"(?m)^## ("
    + "|".join(re.escape(heading) for heading in sorted(_TRACKER_HEADINGS))
    + r")[ \t]*\r?$"
)
_BODY_BLOCKS = {
    heading: f"<!-- career-portal:{field.replace('_', '-')}:v1 -->"
    for field, heading in _BODY_FIELDS.items()
}
_KEY = re.compile(r"^([A-Za-z_][A-Za-z0-9_-]*):(?:[ \t]*(.*))$")


class PortalDataError(ValueError):
    """A content-free failure suitable for the local HTTP boundary."""

    def __init__(self, code: str, message: str, status: int = 400) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status


def _identifier(relative: str) -> str:
    return hashlib.sha256(relative.encode("utf-8")).hexdigest()[:24]


def _revision(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _scalar(value: str) -> object:
    value = value.strip()
    if not value:
        return ""
    if value.startswith(('"', "[")):
        try:
            return json.loads(value)
        except ValueError:
            return value
    if value.startswith("'") and value.endswith("'"):
        return value[1:-1].replace("''", "'")
    if value in {"true", "false"}:
        return value == "true"
    return value


def _parse_note(raw: bytes) -> tuple[list[str], int, dict[str, object]]:
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise PortalDataError("invalid-note", "记录不是有效的 UTF-8 文件。") from exc
    lines = text.splitlines(keepends=True)
    if not lines or lines[0].strip() != "---":
        raise PortalDataError("invalid-note", "记录缺少应用属性。")
    end = next((i for i in range(1, len(lines)) if lines[i].strip() == "---"), None)
    if end is None:
        raise PortalDataError("invalid-note", "记录属性没有正确结束。")
    fields: dict[str, object] = {}
    previous_key = ""
    for line in lines[1:end]:
        match = _KEY.match(line.rstrip("\r\n"))
        if match:
            key, value = match.groups()
            if key in fields:
                raise PortalDataError("duplicate-property", "记录含重复属性；请先在原文件中核对。")
            fields[key] = _scalar(value)
            previous_key = key
        elif previous_key == "career_evidence_links" and line.lstrip().startswith("- "):
            if fields[previous_key] == "":
                fields[previous_key] = []
            if not isinstance(fields[previous_key], list):
                raise PortalDataError("invalid-links", "经历关联格式无效。")
            fields[previous_key].append(_scalar(line.lstrip()[2:]))
    if fields.get("type") != "job_application":
        raise PortalDataError("not-application", "文件不是投递记录。")
    return lines, end, fields


def _section_end(body: str, heading: str) -> int:
    # Only unmarked legacy JDs need the ambiguous History compatibility rule.
    marker = _BODY_BLOCKS["Job Description"]
    marked_jd = body.lstrip().startswith((marker + "\n", marker + "\r\n"))
    return next(
        (
            m.start()
            for m in _SECTION_BOUNDARY.finditer(body)
            if heading != "Job Description" or marked_jd or m[1] != "History"
        ),
        len(body),
    )


def _section(body: str, heading: str) -> str:
    match = re.search(rf"(?m)^## {re.escape(heading)}[ \t]*\r?$", body)
    if match is None:
        return ""
    following = body[match.end() :]
    value = following[: _section_end(following, heading)].strip()
    if value.splitlines()[:1] == [_BODY_BLOCKS[heading]]:
        return re.sub(r"(?m)^ {4}", "", value.partition("\n")[2]).strip()
    return value


def _text(fields: dict[str, object], name: str, default: str = "") -> str:
    value = fields.get(name, default)
    return value if isinstance(value, str) else str(value)


def _application(path: Path, raw: bytes) -> dict[str, object]:
    lines, end, fields = _parse_note(raw)
    body = "".join(lines[end + 1 :])
    status = _text(fields, "status", _text(fields, "current_status", "drafting"))
    links = fields.get("career_evidence_links", [])
    result: dict[str, object] = {
        "id": _identifier(path.name),
        "revision": _revision(raw),
        "source_name": path.name,
        "status": status,
        "next_action": _section(body, "Next Action") or _text(fields, "required_next_action"),
        "notes": _section(body, "Hermes Notes"),
        "job_description": _section(body, "Job Description"),
        "strategy_notes": _section(body, "Application Strategy"),
        "linked_evidence": links if isinstance(links, list) else [],
        "needs_action": fields.get("needs_action", status in _ACTION_STATUSES) is True,
        "referral_used": fields.get("referral_used") is True,
        "cover_letter_used": fields.get("cover_letter_used") is True,
        "content": body,
    }
    for field in _TEXT_FIELDS - _BODY_FIELDS.keys() - {"status"}:
        result[field] = _text(fields, field)
    return result


def _validate_changes(data: dict[str, object], *, creating: bool = False) -> dict[str, object]:
    if not isinstance(data, dict) or data.keys() - (
        _TEXT_FIELDS | _BOOL_FIELDS | {"linked_evidence"}
    ):
        raise PortalDataError("invalid-fields", "请只提交支持的投递字段。")
    clean = dict(data)
    for key, value in clean.items():
        if key in _TEXT_FIELDS:
            maximum = (
                200_000 if key == "job_description" else 20_000 if key in _BODY_FIELDS else 2_000
            )
            if not isinstance(value, str) or len(value) > maximum or "\x00" in value:
                raise PortalDataError("invalid-field", "字段类型或长度不符合要求。")
            if key not in _BODY_FIELDS and ("\n" in value or "\r" in value):
                raise PortalDataError("invalid-field", "属性字段必须为单行文本。")
            clean[key] = value.strip()
        elif key in _BOOL_FIELDS and not isinstance(value, bool):
            raise PortalDataError("invalid-field", "开关字段必须为布尔值。")
        elif key == "linked_evidence" and (
            not isinstance(value, list)
            or len(value) > 100
            or any(
                not isinstance(item, str) or re.fullmatch(r"[a-f0-9]{24}", item) is None
                for item in value
            )
            or len(set(value)) != len(value)
        ):
            raise PortalDataError("invalid-links", "经历关联格式无效。")
    if "status" in clean and clean["status"] not in STATUS_LABELS:
        raise PortalDataError("invalid-status", "请选择支持的投递状态。")
    for key, choices in APPLICATION_DECISIONS.items():
        if key in clean and clean[key] not in choices:
            raise PortalDataError("invalid-decision", "请选择支持的岗位评价和投递方式。")
    if (
        "url" in clean
        and clean["url"]
        and not re.match(r"^https?://[^\s]+$", str(clean["url"]), re.I)
    ):
        raise PortalDataError("invalid-url", "职位链接需要使用 HTTP 或 HTTPS 地址。")
    if "application_date" in clean and clean["application_date"]:
        try:
            date.fromisoformat(str(clean["application_date"]))
        except ValueError as exc:
            raise PortalDataError("invalid-date", "投递日期需要使用 YYYY-MM-DD 格式。") from exc
    for key in ("company", "role_title"):
        if (creating or key in clean) and not clean.get(key):
            raise PortalDataError("missing-field", "请填写公司和岗位。")
    return clean


def _write_file(path: Path, raw: bytes, *, replace: bool) -> None:
    """Publish complete bytes atomically; creation never overwrites an existing note."""
    descriptor, temporary = tempfile.mkstemp(prefix=".tomorrowstar-", dir=path.parent)
    temporary_path = Path(temporary)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        if replace:
            os.replace(temporary_path, path)
        else:
            os.link(temporary_path, path)
    finally:
        temporary_path.unlink(missing_ok=True)


def _check_root(root: Path) -> None:
    try:
        safe = root.is_dir() and not root.is_symlink() and root.resolve(strict=True) == root
    except (OSError, RuntimeError):
        safe = False
    if not safe:
        raise PortalDataError("source-unavailable", "数据目录暂不可用，请检查本地连接。", 503)


class ApplicationStore:
    """Versioned JSON application records with a preserved legacy-note adapter."""

    def __init__(self, root: Path) -> None:
        self.root = Path(root).expanduser().resolve()
        if not self.root.is_dir():
            raise PortalDataError("tracker-missing", "投递记录目录不存在。", 404)
        self._lock = RLock()
        self._write_descriptor: int | None = None

    @contextmanager
    def write_lock(self):
        """Serialize cooperating portal/worker writes; external editors do not use this lock."""
        with self._lock:
            if self._write_descriptor is not None:
                yield
                return
            descriptor = os.open(
                self.root / ".tomorrowstar-write.lock",
                os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW,
                0o600,
            )
            try:
                fcntl.flock(descriptor, fcntl.LOCK_EX)
                self._write_descriptor = descriptor
                yield
            finally:
                self._write_descriptor = None
                os.close(descriptor)

    @staticmethod
    def _json_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("Duplicate JSON property")
            result[key] = value
        return result

    def _json(self, path: Path, raw: bytes) -> dict[str, object]:
        try:
            payload = json.loads(raw, object_pairs_hook=self._json_object)
            record = payload["record"]
            identifier = payload["id"]
            if (
                payload.get("schema_version") != "application-record/v1"
                or not isinstance(record, dict)
                or re.fullmatch(r"[a-f0-9]{24}", identifier) is None
                or set(record) != _TEXT_FIELDS | _BOOL_FIELDS | {"linked_evidence", "content"}
                or not isinstance(record["content"], str)
            ):
                raise ValueError
            _validate_changes({key: value for key, value in record.items() if key != "content"})
            legacy = payload.get("legacy_source")
            if legacy is not None and (
                not isinstance(legacy, dict)
                or set(legacy) != {"name", "revision", "record_revision"}
                or not isinstance(legacy["name"], str)
                or any(
                    not isinstance(legacy[key], str)
                    or re.fullmatch(r"[a-f0-9]{64}", legacy[key]) is None
                    for key in ("revision", "record_revision")
                )
            ):
                raise ValueError
            if "creation_request_sha256" in payload and (
                not isinstance(payload["creation_request_sha256"], str)
                or re.fullmatch(r"[a-f0-9]{64}", payload["creation_request_sha256"]) is None
            ):
                raise ValueError
            if "import_parent_revision" in payload and (
                not legacy
                or not isinstance(payload["import_parent_revision"], str)
                or re.fullmatch(r"[a-f0-9]{64}", payload["import_parent_revision"]) is None
            ):
                raise ValueError
            source_name = legacy["name"] if legacy else path.name
            if (
                Path(source_name).name != source_name
                or identifier != _identifier(source_name)
                or (
                    legacy
                    and (
                        not source_name.endswith(".md")
                        or Path(source_name).with_suffix(".json").name != path.name
                    )
                )
                or (not legacy and path.suffix != ".json")
            ):
                raise ValueError
        except (ValueError, TypeError, KeyError, PortalDataError) as exc:
            raise PortalDataError(
                "invalid-application-json", "投递 JSON 记录无效，请保留原文件并核验。", 409
            ) from exc
        result = {**record, "id": identifier, "revision": _revision(raw), "source_name": path.name}
        if legacy:
            source = self.root / legacy["name"]
            result["legacy_source_name"] = legacy["name"]
            result["legacy_source_changed"] = (
                source.is_symlink()
                or not source.is_file()
                or _revision(source.read_bytes()) != legacy["revision"]
            )
        return result

    def _records(self) -> Iterator[tuple[Path, dict[str, object] | None]]:
        """Verify each JSON once; leave unadopted Markdown parsing to its caller."""
        _check_root(self.root)
        paths = sorted(self.root.glob("*.json"))
        if any(path.is_symlink() or not path.is_file() for path in paths):
            raise PortalDataError(
                "invalid-application-json", "投递 JSON 记录不可核验，请保留原文件。", 409
            )
        adopted = set()
        for path in paths:
            row = self._json(path, path.read_bytes())
            adopted.add(row["id"])
            yield path, row
        for path in sorted(self.root.glob("*.md")):
            if path.is_file() and not path.is_symlink() and _identifier(path.name) not in adopted:
                yield path, None

    def _paths(self) -> list[Path]:
        return [path for path, _ in self._records()]

    def _find(self, identifier: str) -> tuple[Path, dict[str, object] | None]:
        if not isinstance(identifier, str) or re.fullmatch(r"[a-f0-9]{24}", identifier) is None:
            raise PortalDataError("application-not-found", "投递记录不存在。", 404)
        found = None
        for path, record in self._records():
            saved_id = record["id"] if record is not None else _identifier(path.name)
            if saved_id == identifier and found is None:
                found = path, record
        # Exhaust the scan so unrelated malformed JSON still fails closed.
        if found is not None:
            return found
        raise PortalDataError("application-not-found", "投递记录不存在。", 404)

    def _read(self, path: Path, raw: bytes) -> dict[str, object]:
        return self._json(path, raw) if path.suffix == ".json" else _application(path, raw)

    def list_applications(self) -> list[dict[str, object]]:
        records = []
        for path, record in self._records():
            try:
                if record is None:
                    record = self._read(path, path.read_bytes())
            except PortalDataError as exc:
                if exc.code == "not-application":
                    continue
                raise
            record.pop("content")
            records.append(record)

        def sort_key(row: dict[str, object]) -> tuple[int, str]:
            try:
                ordinal = date.fromisoformat(str(row["application_date"])).toordinal()
            except ValueError:
                ordinal = 0
            return ordinal, str(row["company"])

        return sorted(records, key=sort_key, reverse=True)

    def get_application(self, identifier: str) -> dict[str, object]:
        path, record = self._find(identifier)
        return record if record is not None else self._read(path, path.read_bytes())

    @staticmethod
    def _payload(record: dict[str, object], **metadata: object) -> dict[str, object]:
        return {
            "schema_version": "application-record/v1",
            "id": record["id"],
            "record": {
                key: value
                for key, value in record.items()
                if key
                not in {
                    "id",
                    "revision",
                    "source_name",
                    "legacy_source_name",
                    "legacy_source_changed",
                }
            },
            **metadata,
        }

    @staticmethod
    def _encode(payload: dict[str, object]) -> bytes:
        return (json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode(
            "utf-8"
        )

    def _archive(self, identifier: str, path: Path, raw: bytes) -> None:
        backup_dir = self.root / ".tomorrowstar-history" / identifier
        for directory in (backup_dir.parent, backup_dir):
            if directory.is_symlink():
                raise PortalDataError("unsafe-backup", "备份目录不能使用符号链接。")
            directory.mkdir(exist_ok=True)
        backup = backup_dir / f"{_revision(raw)}{path.suffix}"
        if backup.exists():
            if backup.is_symlink() or backup.read_bytes() != raw:
                raise PortalDataError("backup-conflict", "原记录备份冲突，未保存修改。", 409)
        else:
            _write_file(backup, raw, replace=False)

    def create_application(
        self, data: dict[str, object], *, request_id: str | None = None
    ) -> dict[str, object]:
        _check_root(self.root)
        clean = _validate_changes(data, creating=True)
        if request_id is not None and (
            not isinstance(request_id, str) or re.fullmatch(r"[a-f0-9]{32}", request_id) is None
        ):
            raise PortalDataError("invalid-save-request", "保存请求标识无效，请重新打开记录。")
        record: dict[str, object] = {key: "" for key in _TEXT_FIELDS}
        record.update({key: False for key in _BOOL_FIELDS})
        record.update(
            {
                "status": "drafting",
                "track": "Other",
                "application_date": date.today().isoformat(),
                "source": "manual",
                "content": "",
                "linked_evidence": [],
            }
        )
        record.update(clean)
        record["needs_action"] = clean.get("needs_action", record["status"] in _ACTION_STATUSES)
        stem = re.sub(
            r"[^\w-]+", "-", str(record["company"]) + "-" + str(record["role_title"])
        ).strip("-")[:100]
        path = self.root / (
            f"application-{request_id}.json"
            if request_id
            else f"{record['application_date']}-{stem}-{uuid4().hex[:8]}.json"
        )
        record["id"] = _identifier(path.name)
        request_hash = hashlib.sha256(
            json.dumps(clean, sort_keys=True, ensure_ascii=False).encode("utf-8")
        ).hexdigest()
        metadata = {"creation_request_sha256": request_hash} if request_id else {}
        with self.write_lock():
            _check_root(self.root)
            if request_id:
                legacy = path.with_suffix(".md")
                if path.is_symlink() or legacy.is_symlink():
                    raise PortalDataError("unsafe-save-request", "保存记录需要人工核验。", 409)
                existing = path if path.exists() else legacy if legacy.exists() else None
                if existing:
                    saved = existing.read_bytes()
                    existing_record = self._read(existing, saved)
                    saved_hash = (
                        json.loads(saved).get("creation_request_sha256")
                        if existing.suffix == ".json"
                        else _parse_note(saved)[2].get("creation_request_sha256")
                    )
                    if saved_hash != request_hash:
                        raise PortalDataError(
                            "save-request-conflict",
                            "同一次保存的内容已改变，请先核验已有记录。",
                            409,
                        )
                    return existing_record
            raw = self._encode(self._payload(record, **metadata))
            _write_file(path, raw, replace=False)
        return self._json(path, raw)

    @staticmethod
    def _legacy_fields(raw: bytes) -> dict[str, object]:
        lines, end, fields = _parse_note(raw)
        supported = (
            _TEXT_FIELDS
            | _BOOL_FIELDS
            | {"career_evidence_links", "current_status", "required_next_action"}
        )
        for index, line in enumerate(lines[1:end], start=1):
            match = _KEY.match(line.rstrip("\r\n"))
            if match and match[1] in supported:
                key = match[1]
                following = index + 1 < end and lines[index + 1].startswith((" ", "\t"))
                if key != "career_evidence_links" and (
                    str(fields[key]).startswith(("|", ">"))
                    or following
                    or isinstance(fields[key], (dict, list))
                ):
                    raise PortalDataError(
                        "complex-property", "此属性使用多行格式，请在原文件中编辑。"
                    )
                if key in _BOOL_FIELDS and not isinstance(fields[key], bool):
                    raise PortalDataError("invalid-field", "开关字段必须为布尔值。")
        return fields

    def preview_application_import(
        self, identifier: str, *, expected_revision: str
    ) -> dict[str, object]:
        """Inspect the legacy-to-JSON mapping without a lock file or data writes."""
        path, _ = self._find(identifier)
        raw = path.read_bytes()
        before = self._read(path, raw)
        if before["revision"] != expected_revision:
            raise PortalDataError("revision-conflict", "记录已更新，请刷新后预览。", 409)
        payload = json.loads(raw) if path.suffix == ".json" else {}
        legacy = payload.get("legacy_source")
        source = self.root / legacy["name"] if legacy else path
        if path.suffix == ".json" and not legacy:
            return {"status": "current", "id": identifier, "expected_revision": expected_revision}
        if source.is_symlink() or not source.is_file():
            raise PortalDataError("source-unavailable", "原记录暂不可用，请保留 JSON 记录。", 409)
        source_raw = source.read_bytes()
        fields = self._legacy_fields(source_raw)
        record = self._payload(_application(source, source_raw))["record"]
        mapped = (
            _TEXT_FIELDS
            | _BOOL_FIELDS
            | {
                "career_evidence_links",
                "current_status",
                "required_next_action",
                "creation_request_sha256",
            }
        )
        return {
            "schema_version": "application-import-preview/v1",
            "status": "conflict"
            if legacy
            and before["legacy_source_changed"]
            and _revision(self._encode(payload["record"])) != legacy["record_revision"]
            else "ready",
            "id": identifier,
            "expected_revision": expected_revision,
            "source_name": source.name,
            "source_revision": _revision(source_raw),
            "target_name": source.with_suffix(".json").name,
            "record": record,
            "mapped_properties": sorted(set(fields) & mapped),
            "unmapped_properties": sorted(set(fields) - mapped),
            "original_bytes_preserved": True,
        }

    def import_application(self, identifier: str, *, expected_revision: str) -> dict[str, object]:
        """Explicitly adopt a legacy note; conflicting newer JSON requires manual reconciliation."""
        with self.write_lock():
            path, _ = self._find(identifier)
            raw = path.read_bytes()
            before = self._read(path, raw)
            if not expected_revision or _revision(raw) != expected_revision:
                if path.suffix == ".json":
                    saved = json.loads(raw)
                    provenance = saved.get("legacy_source")
                    if (
                        provenance
                        and expected_revision
                        in {provenance["revision"], saved.get("import_parent_revision")}
                        and not before["legacy_source_changed"]
                        and _revision(self._encode(saved["record"]))
                        == provenance["record_revision"]
                    ):
                        return before
                raise PortalDataError(
                    "revision-conflict", "记录已在其他地方更新，请刷新后重试。", 409
                )
            if path.suffix == ".json":
                payload = json.loads(raw)
                legacy = payload.get("legacy_source")
                if not legacy:
                    return before
                source = self.root / legacy["name"]
                if source.is_symlink() or not source.is_file():
                    raise PortalDataError(
                        "source-unavailable", "原记录暂不可用，请保留 JSON 记录。", 409
                    )
                source_raw = source.read_bytes()
                if _revision(source_raw) == legacy["revision"]:
                    return before
                if _revision(self._encode(payload["record"])) != legacy["record_revision"]:
                    raise PortalDataError(
                        "source-import-conflict", "JSON 与原记录均已修改，请先人工合并。", 409
                    )
                self._legacy_fields(source_raw)
                imported = _application(source, source_raw)
                self._archive(identifier, path, raw)
                target = path
                metadata = {
                    key: value
                    for key, value in payload.items()
                    if key not in {"schema_version", "id", "record", "legacy_source"}
                }
            else:
                source, source_raw, imported = path, raw, before
                target = path.with_suffix(".json")
                fields = self._legacy_fields(raw)
                metadata = (
                    {"creation_request_sha256": fields["creation_request_sha256"]}
                    if "creation_request_sha256" in fields
                    else {}
                )
            # Bind one published import to its prior JSON revision. This lets a
            # retry adopt the result after publication interrupted its response.
            metadata["import_parent_revision"] = _revision(raw)
            payload = self._payload(
                imported,
                **metadata,
                legacy_source={
                    "name": source.name,
                    "revision": _revision(source_raw),
                    "record_revision": _revision(self._encode(self._payload(imported)["record"])),
                },
            )
            self._archive(identifier, source, source_raw)
            if source.is_symlink() or source.read_bytes() != source_raw or path.read_bytes() != raw:
                raise PortalDataError(
                    "revision-conflict", "记录已在其他地方更新，请刷新后重试。", 409
                )
            encoded = self._encode(payload)
            result = self._json(target, encoded)
            _write_file(target, encoded, replace=target == path)
            return result

    def update_application(
        self, identifier: str, changes: dict[str, object], expected_revision: str
    ) -> dict[str, object]:
        clean = _validate_changes(changes)
        with self.write_lock():
            path, _ = self._find(identifier)
            raw = path.read_bytes()
            if not expected_revision or _revision(raw) != expected_revision:
                raise PortalDataError(
                    "revision-conflict", "记录已在其他地方更新，请刷新后重试。", 409
                )
            before = self._read(path, raw)
            after = {**before, **clean}
            if "status" in clean and "needs_action" not in clean:
                after["needs_action"] = clean["status"] in _ACTION_STATUSES
            if after == before:
                return before
            if path.suffix == ".json":
                payload = json.loads(raw)
                payload["record"] = self._payload(after)["record"]
                target = path
            else:
                target = path.with_suffix(".json")
                payload = self._payload(
                    after,
                    legacy_source={
                        "name": path.name,
                        "revision": _revision(raw),
                        "record_revision": _revision(self._encode(self._payload(before)["record"])),
                    },
                )
                fields = self._legacy_fields(raw)
                if "creation_request_sha256" in fields:
                    payload["creation_request_sha256"] = fields["creation_request_sha256"]
            self._archive(identifier, path, raw)
            if path.is_symlink() or path.read_bytes() != raw:
                raise PortalDataError(
                    "revision-conflict", "记录已在其他地方更新，请刷新后重试。", 409
                )
            updated = self._encode(payload)
            result = self._json(target, updated)
            _write_file(target, updated, replace=target == path)
            return result


class CareerCatalog:
    """Read documentary career material without granting assessment authority."""

    _DOCUMENT_CACHE_MAX_BYTES = 32 * 1024 * 1024
    _DOCUMENT_CACHE_MAX_ITEMS = 2048
    _KINDS = {
        "reports": "report",
        "contributions": "contribution",
        "skill-graph": "skill",
        "sources": "source",
    }

    def __init__(self, workspace: Path) -> None:
        self.root = Path(workspace).expanduser().resolve()
        if not self.root.is_dir():
            raise PortalDataError("career-missing", "经历工作区不存在。", 404)
        self._document_cache: OrderedDict[Path, tuple[tuple[int, ...], str]] = OrderedDict()
        self._document_cache_lock = RLock()
        self._writes = ApplicationStore(self.root)

    def _paths(self) -> list[tuple[Path, str]]:
        _check_root(self.root)
        found = []
        for folder, kind in self._KINDS.items():
            base = self.root / folder
            if not base.is_dir() or base.is_symlink():
                continue
            for path in sorted(base.rglob("*")):
                if path.suffix not in {".md", ".json"} or not path.is_file():
                    continue
                relative = path.relative_to(self.root)
                if any(part.startswith(".") for part in relative.parts):
                    continue
                if path.is_symlink() or any(
                    parent.is_symlink()
                    for parent in path.parents
                    if parent != self.root and parent.is_relative_to(self.root)
                ):
                    continue
                found.append((path, kind))
        with self._document_cache_lock:
            current = {path for path, _ in found}
            for path in self._document_cache.keys() - current:
                del self._document_cache[path]
        return found

    def _document_content(self, path: Path) -> str:
        with self._document_cache_lock:
            try:
                fingerprint = _document_fingerprint(path, self.root)
            except PortalDataError:
                self._document_cache.pop(path, None)
                raise
            cached = self._document_cache.get(path)
            # Membership changes do not alter a stable file's bytes. Ancestor metadata
            # guards actual reads below, without invalidating unchanged sibling files.
            identity = fingerprint[:7]
            if cached is not None and cached[0] == identity:
                self._document_cache.move_to_end(path)
                return cached[1]
            self._document_cache.pop(path, None)
            content = _read_document(path, expected_identity=identity)
            if _document_fingerprint(path, self.root) != fingerprint:
                raise PortalDataError(
                    "document-unavailable", "文档在读取期间发生变化，请刷新重试。", 503
                )
            self._document_cache[path] = (identity, content)
            # Bound process-local memory; obsolete paths are also pruned on every scan.
            while (
                len(self._document_cache) > self._DOCUMENT_CACHE_MAX_ITEMS
                or sum(sys.getsizeof(row[1]) for row in self._document_cache.values())
                > self._DOCUMENT_CACHE_MAX_BYTES
            ):
                self._document_cache.popitem(last=False)
            return content

    def _record(self, path: Path, kind: str, *, detail: bool) -> dict[str, object]:
        relative = path.relative_to(self.root).as_posix()
        available = not _is_cloud_placeholder(path)
        record: dict[str, object] = {
            "id": _identifier(relative),
            "title": path.stem.replace("-", " "),
            "kind": kind,
            "status": "documentary",
            "summary": "职业经历资料；投递按已保存事实复用。"
            if available
            else "云端文件，请先下载到本地。",
            "source_name": relative,
            "available": available,
        }
        if detail:
            content = self._document_content(path)
            heading = re.search(r"(?m)^# (.+)$", content)
            if heading:
                record["title"] = heading.group(1).strip()
            record["content"] = content
            record["revision"] = _revision(content.encode("utf-8"))
            protected = re.search(
                r'(?mi)^\s*["\']?(?:schema_version|schemaVersion|sealed|source[-_]custody)["\']?\s*:',
                content,
            )
            if path.suffix == ".json":
                try:
                    document = json.loads(content)
                    protected = protected or any(
                        marker in document
                        for marker in (
                            "schema_version",
                            "schemaVersion",
                            "sealed",
                            "source_custody",
                        )
                    )
                except (ValueError, TypeError):
                    protected = True
            record["editable"] = bool(
                kind == "source"
                and not protected
                and (path.suffix == ".md" or relative == "sources/profile.json")
            )
            history = self.root / ".tomorrowstar-career-history" / str(record["id"])
            record["history"] = []
            if history.is_symlink() or history.parent.is_symlink():
                raise PortalDataError("unsafe-backup", "历史目录不能使用符号链接。")
            for event in sorted(history.glob("*/requested.json")):
                if event.is_symlink() or event.parent.is_symlink():
                    raise PortalDataError("unsafe-backup", "历史记录不能使用符号链接。")
                item = json.loads(event.read_text(encoding="utf-8"))
                applied = event.parent / "applied.json"
                if applied.is_symlink():
                    raise PortalDataError("unsafe-backup", "历史记录不能使用符号链接。")
                item["status"] = "applied" if applied.is_file() else "needs_recheck"
                record["history"].append(item)
            record["history"].sort(key=lambda event: (event["at"], event["event_id"]))
        return record

    def update_evidence(
        self,
        identifier: str,
        revision: str,
        content: str,
        *,
        actor: str = "user",
        source: str = "explicit-career-correction",
    ) -> dict[str, object]:
        """Correct a current source document without editing research records."""
        try:
            updated = content.encode("utf-8") if isinstance(content, str) else b""
        except UnicodeError as exc:
            raise PortalDataError("invalid-document", "经历文档必须是有效的 UTF-8。") from exc
        if not updated.strip() or len(updated) > 2_000_000:
            raise PortalDataError("invalid-document", "请提供有效的完整经历文档。")
        if not all(isinstance(value, str) and value.strip() for value in (actor, source)):
            raise PortalDataError("invalid-source", "请保留更正来源和操作者。")
        with self._writes.write_lock():
            before = self.get_evidence(identifier)
            if not before["editable"]:
                raise PortalDataError(
                    "career-read-only", "此记录是研究或历史对象，请更正当前经历源文档。", 409
                )
            if before["revision"] != revision:
                raise PortalDataError("revision-conflict", "记录已更新，请刷新后重试。", 409)
            path = self.root / str(before["source_name"])
            _document_fingerprint(path, self.root)
            raw = path.read_bytes()
            if _revision(raw) != revision:
                raise PortalDataError("revision-conflict", "记录已更新，请刷新后重试。", 409)
            if path.suffix == ".json":
                try:
                    if not isinstance(json.loads(content), dict):
                        raise ValueError
                except ValueError as exc:
                    raise PortalDataError(
                        "invalid-document", "职业档案必须是有效的 JSON 对象。"
                    ) from exc
            if updated == raw:
                return before
            history = self.root / ".tomorrowstar-career-history" / identifier
            for directory in (history.parent, history):
                if directory.is_symlink():
                    raise PortalDataError("unsafe-backup", "历史目录不能使用符号链接。")
                directory.mkdir(exist_ok=True)
            event_dir = history / str(uuid4())
            event_dir.mkdir()
            backup = event_dir / ("before" + path.suffix)
            event = {
                "event_id": event_dir.name,
                "at": datetime.now(UTC).isoformat(),
                "source_name": before["source_name"],
                "actor": actor,
                "source": source,
                "before_revision": revision,
                "after_revision": _revision(updated),
                "backup": backup.relative_to(self.root).as_posix(),
            }
            _write_file(backup, raw, replace=False)
            encoded = json.dumps(event, ensure_ascii=False, sort_keys=True).encode("utf-8")
            _write_file(event_dir / "requested.json", encoded, replace=False)
            _document_fingerprint(path, self.root)
            if path.read_bytes() != raw:
                raise PortalDataError("revision-conflict", "记录已更新，请刷新后重试。", 409)
            _write_file(path, updated, replace=True)
            _write_file(event_dir / "applied.json", encoded, replace=False)
            return self.get_evidence(identifier)

    def list_evidence(self) -> list[dict[str, object]]:
        return [self._record(path, kind, detail=False) for path, kind in self._paths()]

    def get_evidence(self, identifier: str) -> dict[str, object]:
        for path, kind in self._paths():
            if _identifier(path.relative_to(self.root).as_posix()) == identifier:
                return self._record(path, kind, detail=True)
        raise PortalDataError("evidence-not-found", "经历文档不存在。", 404)


def _is_cloud_placeholder(path: Path) -> bool:
    # macOS exposes FileProvider placeholders without downloading their contents.
    return bool(getattr(path.stat(), "st_flags", 0) & getattr(stat, "SF_DATALESS", 0))


def _document_identity(metadata: os.stat_result) -> tuple[int, ...]:
    return (
        metadata.st_dev,
        metadata.st_ino,
        metadata.st_mode,
        metadata.st_size,
        metadata.st_mtime_ns,
        metadata.st_ctime_ns,
        getattr(metadata, "st_flags", 0),
    )


def _document_fingerprint(path: Path, root: Path) -> tuple[int, ...]:
    """Check current availability and path safety before reusing document bytes."""
    _check_root(root)
    try:
        parents = []
        for parent in path.parents:
            directory = parent.lstat()
            if not stat.S_ISDIR(directory.st_mode):
                raise OSError("unsafe document parent")
            parents.extend((directory.st_dev, directory.st_ino, directory.st_mode))
        metadata = path.lstat()
        if not stat.S_ISREG(metadata.st_mode):
            raise OSError("unsafe document")
        if _is_cloud_placeholder(path):
            raise PortalDataError(
                "document-unavailable", "文件尚未下载。请在 Finder 中下载原文件，再刷新重试。", 503
            )
        return (*_document_identity(metadata), *parents)
    except OSError as exc:
        raise PortalDataError(
            "document-unavailable", "文件暂时无法读取。请确认文件已下载到本地，再刷新重试。", 503
        ) from exc


def _read_document(path: Path, *, expected_identity: tuple[int, ...] | None = None) -> str:
    """Bound cloud-file reads without leaving blocked threads in the HTTP process."""
    if _is_cloud_placeholder(path):
        raise PortalDataError(
            "document-unavailable", "文件尚未下载。请在 Finder 中下载原文件，再刷新重试。", 503
        )
    maximum_size = 2_000_000
    metadata = path.stat()
    if metadata.st_size > maximum_size:
        raise PortalDataError("document-too-large", "文档较大，请在原工作区中打开。", 413)
    if expected_identity is None:
        expected_identity = _document_identity(metadata)
    try:
        result = subprocess.run(
            [
                sys.executable,
                "-I",
                "-B",
                "-c",
                "import os,sys\n"
                "def identity(value):\n"
                " return (value.st_dev,value.st_ino,value.st_mode,value.st_size,"
                "value.st_mtime_ns,value.st_ctime_ns,getattr(value,'st_flags',0))\n"
                "expected=tuple(map(int,sys.argv[1:-1]))\n"
                "fd=os.open(sys.argv[-1],os.O_RDONLY|getattr(os,'O_NOFOLLOW',0))\n"
                "with os.fdopen(fd,'rb') as stream:\n"
                " if identity(os.fstat(stream.fileno()))!=expected: sys.exit(1)\n"
                " content=stream.read(2000001)\n"
                " if identity(os.fstat(stream.fileno()))!=expected: sys.exit(1)\n"
                " sys.stdout.buffer.write(content)",
                *(str(value) for value in expected_identity),
                str(path),
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            timeout=3,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise PortalDataError(
            "document-unavailable", "文件暂时无法读取。请确认文件已下载到本地，再刷新重试。", 503
        ) from exc
    if result.returncode:
        raise PortalDataError(
            "document-unavailable", "文件暂时无法读取。请确认文件已下载到本地，再刷新重试。", 503
        )
    if len(result.stdout) > maximum_size:
        raise PortalDataError("document-too-large", "文档较大，请在原工作区中打开。", 413)
    try:
        return result.stdout.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise PortalDataError("invalid-document", "经历文档不是有效的 UTF-8 文件。") from exc
