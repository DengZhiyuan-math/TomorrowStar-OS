"""Private documentary recommendation intake; selecting a job never submits it."""

from __future__ import annotations

import json
import re
from copy import deepcopy
from datetime import UTC, datetime
from html import unescape
from html.parser import HTMLParser
from pathlib import Path
from uuid import uuid4

from ._vendor import job_apply_store as helper
from .application_automation import application_key, recommendation_key, record_label
from .application_storage import private_root
from .career_portal_data import PortalDataError
from .validation.hashing import record_digest as digest


def _clean(value: str) -> str:
    return re.sub(r"[\u200b-\u200d\u2060\ufeff]", "", unescape(value)).strip()


class _MailHTML(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.text, self.links, self.blocked = [], [], 0

    def handle_starttag(self, tag, attributes):
        if tag in {"script", "style"}:
            self.blocked += 1
        if not self.blocked and tag == "a":
            self.links.extend(value for key, value in attributes if key == "href" and value)
        if tag in {"p", "br", "div", "li"}:
            self.text.append("\n")

    def handle_endtag(self, tag):
        if tag in {"script", "style"}:
            self.blocked = max(0, self.blocked - 1)

    def handle_data(self, data):
        if not self.blocked:
            self.text.append(data)


def normalize_message(raw: dict) -> dict:
    """Convert an explicit mail envelope to inert text without loading resources."""
    if (
        not isinstance(raw, dict)
        or not isinstance(raw.get("message_id"), str)
        or not raw["message_id"].strip()
    ):
        raise PortalDataError("recommendation_message_invalid", "邮件缺少可核验的 message ID。")
    if any(
        not isinstance(raw.get(field, ""), str)
        for field in (
            "message_id",
            "thread_id",
            "received_at",
            "from",
            "subject",
            "body_text",
            "body_html",
            "snippet",
        )
    ) or not isinstance(raw.get("links", []), list):
        raise PortalDataError("recommendation_message_invalid", "邮件字段格式不能核验。")
    identity = raw.get("mailbox_identity")
    if identity is not None and (
        not isinstance(identity, str) or re.fullmatch(r"[a-f0-9]{64}", identity) is None
    ):
        raise PortalDataError("recommendation_message_invalid", "邮件账户来源不能核验。")
    parser = _MailHTML()
    if isinstance(raw.get("body_html"), str):
        parser.feed(raw["body_html"])
    text = raw.get("body_text")
    has_body = isinstance(text, str) or bool(raw.get("body_html"))
    if not isinstance(text, str):
        text = "".join(parser.text) if raw.get("body_html") else raw.get("snippet", "")
    if not isinstance(text, str):
        raise PortalDataError("recommendation_message_invalid", "邮件正文格式不能核验。")
    text = _clean(text)
    links = [*raw.get("links", []), *parser.links, *re.findall(r"https://[^\s<>\"']+", text)]
    links = list(
        dict.fromkeys(_clean(link).rstrip(".,;)>]") for link in links if isinstance(link, str))
    )
    completeness = raw.get("body_completeness", "unknown") if has_body else "excerpt"
    if not isinstance(completeness, str):
        completeness = "unknown"
    scope = raw.get("body_scope", "message")
    return {
        **{
            key: raw.get(key, "")
            for key in ("message_id", "thread_id", "received_at", "from", "subject")
        },
        **({"mailbox_identity": identity} if identity is not None else {}),
        "body_text": text,
        "body_completeness": completeness
        if completeness in {"full", "excerpt", "unknown"}
        else "unknown",
        "body_scope": "job_description" if scope == "job_description" else "message",
        "links": [link for link in links if application_key(link) is not None],
    }


def _same_job_text(body: str, description: str) -> bool:
    """A re-read posting states the same JD as a saved note.

    2026-11-08 (Mistral): only heading case, two dropped inline links and the
    reader's appended structured fields differed. Those, punctuation and whitespace
    are ignored; every word of the description must still match, in order.
    """
    from .application_job_source import STRUCTURED_FIELDS

    labels = {label.casefold() for _key, label in STRUCTURED_FIELDS}

    def words(text):
        blocks = [block for block in re.split(r"\n\s*\n", text.strip()) if block.strip()]
        while blocks and blocks[-1].strip().splitlines()[0].strip().casefold() in labels:
            blocks.pop()
        text = re.sub(r"https?://\S+", " ", " ".join(blocks))
        return re.sub(r"[\W_]+", " ", text).casefold().split()

    return bool(words(description)) and words(body) == words(description)


def _same_full_text(body: str, description: str) -> bool:
    """The complete captured JD scope cannot be replaced by an extracted substring."""
    return bool(description.strip()) and " ".join(description.split()) == " ".join(body.split())


def _same_identity(first, second) -> bool:
    key = recommendation_key(first)
    return key is not None and key == recommendation_key(second)


def _page_identity(page: dict, mail_url: str, target_url: str, source_url: str) -> bool:
    """Accept a different final job identity only through an observed redirect chain."""
    origin = recommendation_key(page.get("url"))
    final = recommendation_key(page.get("final_url", page.get("url")))
    if origin is None or final is None or origin != recommendation_key(mail_url):
        return False
    current = origin
    redirects = page.get("redirects", [])
    if not isinstance(redirects, list):
        return False
    for hop in redirects:
        if (
            not isinstance(hop, dict)
            or type(hop.get("status")) is not int
            or hop.get("status") not in {301, 302, 303, 307, 308}
            or recommendation_key(hop.get("url")) != current
        ):
            return False
        current = recommendation_key(hop.get("location"))
        if current is None:
            return False
    return (
        current == final
        and recommendation_key(target_url) == final
        and recommendation_key(source_url) in {origin, final}
    )


def _listed_at(application, key) -> bool:
    """The job's board link, or the board page its employer link was resolved from."""
    return key is not None and key in {
        recommendation_key(application.get("url")),
        recommendation_key(application.get("listing_url")),
    }


def _same_saved_facts(record, application, *, same_source=False) -> bool:
    """The saved application still states this recommendation's facts.

    ``same_source``: the application was saved from this very recommendation
    revision. Its LinkedIn link then resolved to the employer's own apply page
    (APP-02) keeps its identity; company, role, location and JD still compare.
    """
    board = recommendation_key(record.get("url"))
    resolved_offsite = (
        same_source
        and board is not None
        and board[0] == "linkedin"
        and (recommendation_key(application.get("url")) or ("",))[0] != "linkedin"
    )
    return (
        (
            resolved_offsite
            or record.get("url", "") == application.get("url", "")
            or _same_identity(record.get("url"), application.get("url"))
            or _listed_at(application, recommendation_key(record.get("url")))
        )
        and all(
            str(record.get(field, "")).strip() == str(application.get(field, "")).strip()
            for field in ("company", "role_title", "location")
        )
        and _same_job_text(
            record.get("job_description", ""), application.get("job_description", "")
        )
    )


def _possible_duplicate(record, application) -> bool:
    labels = tuple(record_label(record.get(field)) for field in ("company", "role_title"))
    return (
        recommendation_key(application.get("url")) is None
        and all(labels)
        and labels
        == tuple(record_label(application.get(field)) for field in ("company", "role_title"))
    )


class RecommendationStore:
    """Keep mail captures private and leave existing application notes authoritative."""

    def __init__(self, capture_root: Path, applications) -> None:
        self.root = private_root(capture_root)
        self.applications = applications

    def _state(self) -> dict:
        path = self.root / "recommendations.json"
        if not path.exists() and not path.is_symlink():
            return {"schemaVersion": 1, "recommendations": []}
        try:
            if path.is_symlink():
                raise ValueError("unsafe-state")
            state = json.loads(path.read_text(encoding="utf-8"))
            if (
                not isinstance(state, dict)
                or state.get("schemaVersion") != 1
                or not isinstance(state.get("recommendations"), list)
            ):
                raise ValueError("invalid-state")
            for row in state["recommendations"]:
                if (
                    not isinstance(row, dict)
                    or not re.fullmatch(r"[a-f0-9]{32}", row.get("id", ""))
                    or row.get("revision")
                    != digest({key: value for key, value in row.items() if key != "revision"})
                ):
                    raise ValueError("record-changed")
            return state
        except (OSError, ValueError, TypeError) as error:
            raise PortalDataError(
                "recommendation_state_invalid", "推荐记录不能核验，请保留原件并检查保存状态。", 409
            ) from error

    def _capture(self, folder: str, payload: dict) -> str:
        revision = digest(payload)
        path = self.root / folder / f"{revision}.json"
        try:
            if path.is_symlink() or path.parent.is_symlink():
                raise ValueError("unsafe-capture")
            if path.exists():
                if digest(json.loads(path.read_text(encoding="utf-8"))) != revision:
                    raise ValueError("capture-changed")
            else:
                helper.atomic_write_json(path, payload)
        except (OSError, ValueError) as error:
            raise PortalDataError(
                "recommendation_capture_invalid", "原始捕获不能核验，已保留原件。", 409
            ) from error
        return revision

    def _record(self, identifier: str) -> dict:
        record = next(
            (row for row in self._state()["recommendations"] if row["id"] == identifier), None
        )
        if record is None:
            raise PortalDataError("recommendation_not_found", "找不到此岗位推荐。", 404)
        return record

    def _acquisition_path(self, identifier: str) -> Path:
        if not isinstance(identifier, str) or not re.fullmatch(r"[a-f0-9]{32}", identifier):
            raise PortalDataError("recommendation_not_found", "找不到此岗位推荐。", 404)
        path = self.root / "acquisitions" / f"{identifier}.json"
        if path.is_symlink() or path.parent.is_symlink():
            raise PortalDataError(
                "recommendation_capture_invalid", "岗位获取日志不能核验，请保留原件。", 409
            )
        return path

    def _acquisition(self, identifier: str) -> dict | None:
        path = self._acquisition_path(identifier)
        if not path.exists():
            return None
        try:
            attempt = json.loads(path.read_text(encoding="utf-8"))
            if (
                not isinstance(attempt, dict)
                or attempt.get("recommendation_id") != identifier
                or not re.fullmatch(r"[a-f0-9]{32}", attempt.get("attempt_id", ""))
                or attempt.get("status") not in {"pending", "captured", "saved"}
                or attempt.get("revision")
                != digest({key: value for key, value in attempt.items() if key != "revision"})
            ):
                raise ValueError("invalid-acquisition")
            return attempt
        except (OSError, ValueError, TypeError) as error:
            raise PortalDataError(
                "recommendation_capture_invalid", "岗位获取日志不能核验，请保留原件。", 409
            ) from error

    def _save_acquisition(self, attempt: dict) -> None:
        attempt = {key: value for key, value in attempt.items() if key != "revision"}
        helper.atomic_write_json(
            self._acquisition_path(attempt["recommendation_id"]),
            attempt | {"revision": digest(attempt)},
        )

    def begin_acquisition(self, identifier: str, revision: str, *, retry=False) -> dict:
        """Checkpoint before HTTP; an unresolved previous request never retries."""
        with self.applications.write_lock():
            record = self._record(identifier)
            if record["revision"] != revision:
                raise PortalDataError(
                    "recommendation_conflict", "岗位推荐已更新，请重新核验。", 409
                )
            attempt = self._acquisition(identifier)
            if attempt and attempt["status"] != "saved":
                status = "needs_recheck"
            elif record["jd_completeness"] == "full":
                status = "complete"
            elif attempt and not retry:
                status = "failed"
            else:
                attempt = {
                    "attempt_id": uuid4().hex,
                    "recommendation_id": identifier,
                    "recommendation_revision": revision,
                    "status": "pending",
                    "started_at": datetime.now(UTC).isoformat(),
                }
                self._save_acquisition(attempt)
                return {
                    "status": "fetch",
                    "attempt_id": attempt["attempt_id"],
                    "recommendation": record,
                }
            return {"status": status, "recommendation": record}

    def finish_acquisition(self, identifier: str, attempt_id: str, capture: dict) -> dict:
        """Retain one response before publishing its per-job result."""
        with self.applications.write_lock():
            record = self._record(identifier)
            attempt = self._acquisition(identifier)
            if not attempt or attempt["attempt_id"] != attempt_id or attempt["status"] != "pending":
                raise PortalDataError(
                    "recommendation_acquisition_conflict", "岗位获取记录已改变，请先核验。", 409
                )
            known_keys = (
                {recommendation_key(record["url"])}
                | {recommendation_key(row["url"]) for row in record["source_messages"]}
            ) - {None}
            if (
                not isinstance(capture, dict)
                or recommendation_key(capture.get("url")) not in known_keys
            ):
                raise PortalDataError(
                    "recommendation_source_invalid", "岗位获取结果与原始候选身份不符。", 409
                )
            capture = deepcopy(capture)
            capture.setdefault("captured_at", datetime.now(UTC).isoformat())
            try:
                capture_revision = self._capture("pages", capture)
                attempt.update(status="captured", capture_revision=capture_revision)
                self._save_acquisition(attempt)
                return self.reconcile_acquisition(identifier)
            except (OSError, PortalDataError) as error:
                raise PortalDataError(
                    "recommendation_acquisition_save_unknown",
                    "岗位获取保存结果待核验，已保留记录；请先核验，不自动重取。",
                    409,
                ) from error

    def reconcile_acquisition(self, identifier: str) -> dict:
        """Apply a retained HTTP receipt locally; never repeat a network request."""
        with self.applications.write_lock():
            record = self._record(identifier)
            attempt = self._acquisition(identifier)
            if not attempt or attempt["status"] != "captured":
                return self.snapshot()
            try:
                revision = attempt["capture_revision"]
                path = self.root / "pages" / f"{revision}.json"
                if (
                    not re.fullmatch(r"[a-f0-9]{64}", revision)
                    or path.is_symlink()
                    or path.parent.is_symlink()
                ):
                    raise ValueError("unsafe-capture")
                capture = json.loads(path.read_text(encoding="utf-8"))
                if digest(capture) != revision:
                    raise ValueError("capture-changed")
                messages = []
                for source in record["source_messages"]:
                    path = self.root / "captures" / f"{source['capture_id']}.json"
                    if path.is_symlink() or path.parent.is_symlink():
                        raise ValueError("unsafe-capture")
                    raw = json.loads(path.read_text(encoding="utf-8"))
                    if digest(raw) != source["capture_id"]:
                        raise ValueError("capture-changed")
                    messages.append(raw)
            except (OSError, ValueError, KeyError, TypeError) as error:
                raise PortalDataError(
                    "recommendation_capture_invalid", "岗位原始捕获不能核验，请保留原件。", 409
                ) from error
            fields = capture.get("job_fields", {})
            full = (
                capture.get("acquisition_status") == "available"
                and capture.get("jd_completeness") == "full"
                and capture.get("source_format") == "job_posting"
                and isinstance(fields, dict)
                and all(
                    isinstance(fields.get(key), str) and fields[key].strip()
                    for key in ("title", "company")
                )
            )
            jobs = [
                {
                    "message_id": source["message_id"],
                    "mail_url": source["url"],
                    "url": capture.get("final_url", capture["url"]),
                    "jd_source_url": capture["url"],
                    "jd_source_kind": "page",
                    "page_capture_id": capture.get("capture_id", ""),
                    "company": fields["company"] if full else record.get("company", ""),
                    "role_title": fields["title"] if full else record.get("role_title", ""),
                    "location": fields.get("location", "") if full else record.get("location", ""),
                    "job_description": capture.get("body_text", "") if full else "",
                    "documentary_fields": deepcopy(fields) if full else {},
                    "jd_completeness": "full" if full else "unknown",
                }
                for source in record["source_messages"]
            ]
            self._import_messages(messages, jobs, page_captures=[capture])
            attempt["status"] = "saved"
            self._save_acquisition(attempt)
            return self.snapshot()

    def import_messages(self, messages: list[dict], jobs: list[dict], *, page_captures=()) -> dict:
        with self.applications.write_lock():
            return self._import_messages(messages, jobs, page_captures=page_captures)

    def _import_messages(self, messages: list[dict], jobs: list[dict], *, page_captures) -> dict:
        state = self._state()
        indexed = {row["id"]: row for row in state["recommendations"]}
        by_message = {}
        for raw in messages:
            message = normalize_message(raw)
            capture_id = self._capture("captures", raw)
            message["capture_id"] = capture_id
            by_message[message["message_id"]] = message
        pages = {}
        for page in page_captures:
            if (
                not isinstance(page, dict)
                or any(
                    not isinstance(page.get(field), str)
                    for field in ("capture_id", "url", "body_text")
                )
                or not page["capture_id"]
                or application_key(page["url"]) is None
            ):
                raise PortalDataError(
                    "recommendation_capture_invalid", "页面捕获缺少可核验的来源或正文。", 409
                )
            revision = self._capture("pages", page)
            pages[page["capture_id"]] = deepcopy(page) | {"revision": revision}
        for job in jobs:
            if (
                not isinstance(job, dict)
                or not isinstance(job.get("message_id"), str)
                or job["message_id"] not in by_message
            ):
                raise PortalDataError(
                    "recommendation_source_invalid", "岗位未绑定本次捕获的邮件来源。", 409
                )
            message = by_message[job["message_id"]]
            if any(
                not isinstance(job.get(field, ""), str)
                for field in (
                    "url",
                    "company",
                    "role_title",
                    "job_description",
                    "location",
                    "mail_url",
                    "jd_source_url",
                    "jd_source_kind",
                    "page_capture_id",
                )
            ):
                raise PortalDataError("recommendation_job_invalid", "推荐岗位字段格式不能核验。")
            job = deepcopy(job)
            job["url"] = _clean(job.get("url", ""))
            mail_url = _clean(job.get("mail_url", job["url"]))
            mail_key = recommendation_key(mail_url)
            if mail_url not in message["links"] and (
                mail_key is None
                or not any(recommendation_key(link) == mail_key for link in message["links"])
            ):
                raise PortalDataError(
                    "recommendation_source_invalid", "岗位链接未出现在捕获的邮件中。", 409
                )
            key = recommendation_key(job["url"])
            identifier = digest(key or {"message_id": job["message_id"], "url": job["url"]})[:32]
            identities = {key, mail_key} - {None}
            matches = [
                row
                for row in indexed.values()
                if recommendation_key(row["url"]) in identities
                or any(
                    recommendation_key(source["url"]) in identities
                    for source in row["source_messages"]
                )
            ]
            prior = next(
                (
                    row
                    for row in matches
                    if any(
                        recommendation_key(source["url"]) == mail_key
                        for source in row["source_messages"]
                    )
                ),
                matches[0] if matches else None,
            )
            if prior:
                identifier = prior["id"]
            provenance = {
                key: message.get(key, "")
                for key in (
                    "message_id",
                    "thread_id",
                    "received_at",
                    "from",
                    "subject",
                    "capture_id",
                )
            }
            if "mailbox_identity" in message:
                provenance["mailbox_identity"] = message["mailbox_identity"]
            provenance["url"] = mail_url
            provenance["body_completeness"] = message["body_completeness"]
            previous = indexed.get(identifier, {})
            provenance_rows = previous.get("source_messages", [])
            if provenance not in provenance_rows:
                provenance_rows = [*provenance_rows, provenance]
            description = job.get("job_description", "")
            completeness = "excerpt" if description else "unknown"
            source_kind = job.get("jd_source_kind", "mail")
            source = {
                "kind": "mail",
                "capture_id": message["capture_id"],
                "revision": message["capture_id"],
            }
            status = "available"
            if source_kind == "page":
                page = pages.get(job.get("page_capture_id"))
                status = page.get("acquisition_status", "unavailable") if page else "unavailable"
                if page:
                    source = {
                        "kind": "page",
                        **{key: page[key] for key in ("capture_id", "url", "revision")},
                    }
                full = (
                    bool(page)
                    and status == "available"
                    and page.get("jd_completeness") == "full"
                    and _page_identity(
                        page, mail_url, job["url"], job.get("jd_source_url", job["url"])
                    )
                    and _same_full_text(page.get("body_text", ""), description)
                )
            else:
                full = (
                    message["body_completeness"] == "full"
                    and message["body_scope"] == "job_description"
                    and _same_identity(mail_url, job["url"])
                    and _same_full_text(message["body_text"], description)
                )
            if job.get("jd_completeness") == "full" and full:
                completeness = "full"
                for duplicate_id, duplicate in list(indexed.items()):
                    if duplicate_id == identifier or recommendation_key(duplicate["url"]) != key:
                        continue
                    attempt = self._acquisition(duplicate_id)
                    if attempt and attempt["status"] != "saved":
                        continue  # Preserve any unresolved parallel request for explicit recheck.
                    for provenance_row in duplicate["source_messages"]:
                        if provenance_row not in provenance_rows:
                            provenance_rows = [*provenance_rows, provenance_row]
                    indexed.pop(duplicate_id)
            record = (
                previous
                | deepcopy(job)
                | {
                    "id": identifier,
                    "canonical_key": list(key) if key else None,
                    "source_messages": provenance_rows,
                    "jd_completeness": completeness,
                    "jd_source": source,
                    "jd_scope": "captured_body" if completeness == "full" else None,
                    "acquisition_status": status,
                    "captured_at": page.get("captured_at", "")
                    if source_kind == "page" and page
                    else "",
                    "source_error_code": page.get("error_code", "")
                    if source_kind == "page" and page
                    else "",
                }
            )
            if previous.get("jd_completeness") == "full" and completeness != "full":
                for field in (
                    "company",
                    "role_title",
                    "location",
                    "url",
                    "canonical_key",
                    "mail_url",
                    "job_description",
                    "documentary_fields",
                    "jd_completeness",
                    "jd_source",
                    "jd_source_kind",
                    "jd_source_url",
                    "page_capture_id",
                    "jd_scope",
                    "acquisition_status",
                    "captured_at",
                    "source_error_code",
                ):
                    if field in previous:
                        record[field] = previous[field]
                    else:
                        record.pop(field, None)
            record.pop("revision", None)
            record["revision"] = digest(record)
            indexed[identifier] = record
        state["recommendations"] = list(indexed.values())
        helper.atomic_write_json(self.root / "recommendations.json", state)
        return self.snapshot() | {"messages": list(by_message.values())}

    def import_document(self, capture: dict, fields: dict) -> dict:
        """Save one explicit paste/page capture without inventing a mail envelope."""
        with self.applications.write_lock():
            if (
                capture.get("source_kind") not in {"pasted-jd", "job-page"}
                or not isinstance(capture.get("body_text"), str)
                or not capture["body_text"].strip()
                or not all(
                    isinstance(fields.get(key), str) and fields[key].strip()
                    for key in ("company", "role_title")
                )
            ):
                raise PortalDataError("intake_source_invalid", "岗位来源或关键字段不完整。", 409)
            revision = self._capture("documents", capture)
            url = capture.get("final_url", capture.get("url", ""))
            key = recommendation_key(url) or ("documentary", url or digest(capture["body_text"]))
            identifier = digest(key)[:32]
            row = {
                "id": identifier,
                "company": fields["company"],
                "role_title": fields["role_title"],
                "location": fields.get("location", ""),
                "url": url,
                "job_description": capture["body_text"],
                "jd_completeness": "full",
                "jd_source": {"kind": "document", "revision": revision, "url": url},
                "source_kind": capture["source_kind"],
                "source_messages": [],
                "canonical_key": list(key),
                "captured_at": capture["captured_at"],
                "acquisition_status": "available",
                "documentary_fields": deepcopy(fields),
            }
            row["revision"] = digest(row)
            state = self._state()
            prior = next(
                (item for item in state["recommendations"] if item["id"] == identifier), None
            )
            if prior:
                if any(
                    prior.get(key) != row.get(key)
                    for key in ("company", "role_title", "job_description")
                ):
                    raise PortalDataError(
                        "intake_source_changed",
                        "同一岗位的来源内容已变化，新原文已保留，已有记录待核验。",
                        409,
                    )
                return prior
            state["recommendations"].append(row)
            helper.atomic_write_json(self.root / "recommendations.json", state)
            return row

    def snapshot(self) -> dict:
        state = self._state()
        applications = self.applications.list_applications()
        by_job, by_id, unlinked = {}, {}, {}
        for application in applications:
            by_id.setdefault(application["id"], application)
            key = recommendation_key(application["url"])
            if key is not None:
                by_job.setdefault(key, application)
            listing = recommendation_key(application.get("listing_url"))
            if listing is not None:
                by_job.setdefault(listing, application)
            else:
                labels = tuple(
                    record_label(application.get(field)) for field in ("company", "role_title")
                )
                if all(labels):
                    unlinked.setdefault(labels, []).append(application)
        for record in state["recommendations"]:
            attempt = self._acquisition(record["id"])
            record["acquisition_checkpoint"] = (
                "needs_recheck"
                if attempt and attempt["status"] != "saved"
                else "complete"
                if record["jd_completeness"] == "full"
                else "failed"
                if attempt
                else "not_started"
            )
            key = recommendation_key(record["url"])
            application = by_job.get(key)
            same_source = False
            if application is None and record.get("source_kind"):
                journal = self.root / "selections" / f"{record['id']}.json"
                if (
                    journal.is_file()
                    and not journal.is_symlink()
                    and not journal.parent.is_symlink()
                ):
                    saved = helper.read_json_object(journal, "job selection")
                    identifier = saved.get("application_id")
                    application = by_id.get(identifier) if isinstance(identifier, str) else None
                    same_source = saved.get("recommendation_revision") == record["revision"]
            record["existing_application"] = (
                {field: application[field] for field in ("id", "revision", "status")}
                if application
                else None
            )
            journal = self.root / "selections" / f"{record['id']}.json"
            record["selection_status"] = (
                "source_conflict"
                if application
                and not _same_saved_facts(record, application, same_source=same_source)
                else "saved"
                if application
                else "needs_recheck"
                if journal.exists() or journal.is_symlink() or journal.parent.is_symlink()
                else "unselected"
            )
            record["possible_applications"] = [
                {field: row[field] for field in ("id", "revision", "status")}
                | {"basis": "company_role"}
                for row in unlinked.get(
                    tuple(record_label(record.get(field)) for field in ("company", "role_title")),
                    [],
                )
            ]
        return state

    def reconcile_selection(self, identifier: str) -> dict | None:
        """Read an existing creation receipt; never create or retry a missing write."""
        with self.applications.write_lock():
            record = self._record(identifier)
            journal = self.root / "selections" / f"{identifier}.json"
            if not journal.is_file() or journal.is_symlink() or journal.parent.is_symlink():
                return None
            attempt = helper.read_json_object(journal, "job selection")
            request_id = attempt.get("request_id", "")
            if not isinstance(request_id, str) or re.fullmatch(r"[a-f0-9]{32}", request_id) is None:
                raise PortalDataError("recommendation_needs_recheck", "保存日志不能核验。", 409)
            application = next(
                (
                    row
                    for row in self.applications.list_applications()
                    if row["source_name"]
                    in {f"application-{request_id}.md", f"application-{request_id}.json"}
                ),
                None,
            )
            if (
                application is None
                or application.get("url") != record.get("url", "")
                or not _same_saved_facts(record, application)
            ):
                return None
            helper.atomic_write_json(
                journal, attempt | {"status": "saved", "application_id": application["id"]}
            )
            return {
                "recommendation_id": identifier,
                "application": application,
                "created": False,
                "reconciled": True,
            }

    def select(self, identifier: str, revision: str) -> dict:
        with self.applications.write_lock():
            return self._select(identifier, revision)

    def _select(self, identifier: str, revision: str) -> dict:
        record = next(
            (row for row in self._state()["recommendations"] if row["id"] == identifier), None
        )
        if record is None:
            raise PortalDataError("recommendation_not_found", "找不到此岗位推荐。", 404)
        if record["revision"] != revision:
            raise PortalDataError("recommendation_conflict", "岗位推荐已更新，请重新核验。", 409)
        attempt = self._acquisition(identifier)
        if attempt and attempt["status"] != "saved":
            raise PortalDataError(
                "recommendation_acquisition_needs_recheck",
                "岗位获取结果待核验，请先核验已保存的原始来源。",
                409,
            )
        if record["jd_completeness"] != "full":
            raise PortalDataError(
                "recommendation_jd_incomplete", "推荐仅有摘要或来源未知，请先取得原 JD 全文。", 409
            )
        source = record["jd_source"]
        folder = (
            "pages"
            if source["kind"] == "page"
            else "documents"
            if source["kind"] == "document"
            else "captures"
        )
        path = self.root / folder / f"{source['revision']}.json"
        try:
            if path.is_symlink() or path.parent.is_symlink():
                raise ValueError("unsafe-capture")
            captured = json.loads(path.read_text(encoding="utf-8"))
            if digest(captured) != source["revision"]:
                raise ValueError("capture-changed")
        except (OSError, ValueError) as error:
            raise PortalDataError(
                "recommendation_source_changed", "JD 来源捕获已改变或不可读，请重新核验原件。", 409
            ) from error
        mail = normalize_message(captured) if source["kind"] == "mail" else None
        body = mail["body_text"] if mail else captured.get("body_text", "")
        mail_url = record.get("mail_url", record["url"])
        identity_valid = (
            captured.get("source_kind") in {"pasted-jd", "job-page"}
            and captured.get("final_url", captured.get("url", "")) == record["url"]
            if source["kind"] == "document"
            else _page_identity(captured, mail_url, record["url"], source["url"])
            if source["kind"] == "page"
            else mail["body_completeness"] == "full"
            and mail["body_scope"] == "job_description"
            and _same_identity(mail_url, record["url"])
            and any(_same_identity(link, mail_url) for link in mail["links"])
        )
        if not identity_valid:
            raise PortalDataError(
                "recommendation_source_changed", "JD 来源与目标岗位身份不符，请重新核验原件。", 409
            )
        if not _same_full_text(body, record["job_description"]):
            raise PortalDataError(
                "recommendation_source_changed", "JD 与来源捕获不符，请重新核验原件。", 409
            )
        key = recommendation_key(record["url"])
        if key is None and source["kind"] == "document":
            key = ("documentary", record["url"] or digest(body))
        if key is None:
            raise PortalDataError(
                "recommendation_identity_unknown", "岗位链接缺少可核验的岗位标识。", 409
            )
        applications = self.applications.list_applications()
        journal = self.root / "selections" / f"{identifier}.json"
        if journal.exists() and not journal.is_symlink() and not journal.parent.is_symlink():
            saved = helper.read_json_object(journal, "job selection")
            if saved.get("application_id"):
                application = self.applications.get_application(saved["application_id"])
                same_source = saved.get("recommendation_revision") == record["revision"]
                if not _same_saved_facts(record, application, same_source=same_source):
                    raise PortalDataError(
                        "recommendation_source_conflict",
                        "新来源与已有岗位记录不符，原件已保留。",
                        409,
                    )
                return {
                    "recommendation_id": identifier,
                    "application": application,
                    "created": False,
                }
        for application in applications:
            if _listed_at(application, key):
                if not _same_saved_facts(record, application):
                    raise PortalDataError(
                        "recommendation_source_conflict",
                        "新来源与已有岗位记录不符，原件已保留。",
                        409,
                    )
                return {
                    "recommendation_id": identifier,
                    "application": application,
                    "created": False,
                }
        if any(_possible_duplicate(record, application) for application in applications):
            raise PortalDataError(
                "recommendation_duplicate_uncertain",
                "已有相同公司岗位但链接缺失的申请，请先核验是否重复。",
                409,
            )
        journal = self.root / "selections" / f"{identifier}.json"
        if journal.parent.is_symlink():
            raise PortalDataError(
                "recommendation_capture_invalid", "保存日志目录不能核验，请保留原件。", 409
            )
        if journal.exists() or journal.is_symlink():
            raise PortalDataError(
                "recommendation_needs_recheck", "前次保存结果尚不能核验，请先检查已有申请。", 409
            )
        from .indeed_job_source import employer_apply_url
        from .job_listing_links import employer_url, posting_status

        # One read of a LinkedIn job before any record exists (2026-11-05): a closed
        # posting creates no application; an open one opens on the employer's page.
        status, target = posting_status(record.get("url", ""))
        if status == "closed":
            raise PortalDataError(
                "recommendation_posting_closed", "领英显示岗位已停止招聘，未建申请记录。", 409
            )
        origin = record.get("source_kind", "gmail-recommendation")
        attempt = {
            "request_id": digest({"source": origin, "job": key})[:32],
            "recommendation_id": identifier,
            "recommendation_revision": revision,
            "status": "pending",
        }
        helper.atomic_write_json(journal, attempt)
        # A job board link becomes the employer's own page when it can be resolved.
        apply_url = employer_apply_url(record) or (
            employer_url(target) if status == "open" else None
        )
        try:
            application = self.applications.create_application(
                {
                    key: record.get(key, "")
                    for key in ("company", "role_title", "location", "url", "job_description")
                }
                | {"source": origin}
                | ({"url": apply_url, "listing_url": record["url"]} if apply_url else {})
                | (
                    {
                        "deadline": str(
                            record.get("documentary_fields", {}).get("deadline")
                            or record.get("documentary_fields", {}).get("validThrough")
                            or ""
                        )
                    }
                    if record.get("documentary_fields")
                    else {}
                )
                | (
                    {
                        "notes": "Source facts: "
                        + json.dumps(record["documentary_fields"], ensure_ascii=False)
                    }
                    if record.get("documentary_fields")
                    else {}
                ),
                request_id=attempt["request_id"],
            )
        except (OSError, PortalDataError) as error:
            helper.atomic_write_json(journal, attempt | {"status": "needs_recheck"})
            application = next(
                (row for row in self.applications.list_applications() if _listed_at(row, key)),
                None,
            )
            if application is not None:
                helper.atomic_write_json(
                    journal, attempt | {"status": "saved", "application_id": application["id"]}
                )
                return {
                    "recommendation_id": identifier,
                    "application": application,
                    "created": False,
                    "reconciled": True,
                }
            raise PortalDataError(
                "recommendation_save_unknown",
                "保存结果不确定，已保留记录；请先核验，不自动重试。",
                409,
            ) from error
        helper.atomic_write_json(
            journal, attempt | {"status": "saved", "application_id": application["id"]}
        )
        return {"recommendation_id": identifier, "application": application, "created": True}
