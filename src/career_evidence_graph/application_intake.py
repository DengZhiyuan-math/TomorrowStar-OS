"""Explicit background source intake saves documentary jobs without application workers."""

from __future__ import annotations

import fcntl
import os
import queue
import re
import threading
from copy import deepcopy
from datetime import UTC, date, datetime, timedelta
from inspect import Parameter, signature
from pathlib import Path
from urllib.parse import urlsplit
from uuid import uuid4

from ._vendor import job_apply_store as helper
from .application_gmail import (
    RECOMMENDATION_QUERY,
    process_recommendation_email,
    read_recommendation_emails,
    validate_recommendation_query,
)
from .application_jd_extract import extract_job_fields
from .application_job_source import _url
from .application_recommendations import (
    RecommendationStore,
    normalize_message,
    recommendation_key,
)
from .application_storage import private_root
from .career_portal_data import PortalDataError
from .indeed_job_source import fetch_job_source_or_browser
from .validation.hashing import record_digest as digest
from .workable_uploads import job_shortcode


def _canonical(url):
    key = recommendation_key(url)
    if key is None or key[0] not in {"linkedin", "indeed"}:
        return None
    if key[0] == "linkedin":
        return f"https://www.linkedin.com/jobs/view/{key[1]}"
    if urlsplit(url).path.rstrip("/") not in {
        "/viewjob",
        "/m/viewjob",
        "/rc/clk",
        "/rc/clk/dl",
        "/pagead/clk",
        "/jobs",
    }:
        return None
    host = urlsplit(url).hostname or ""
    if re.fullmatch(r"(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)*indeed\.com", host) is None:
        return None
    return f"https://{host}/viewjob?jk={key[1]}"


def _explicit_pasted_job_url(text):
    """Adopt only an explicit application link with one unambiguous job identity."""
    candidates = {}
    for value in re.findall(r"https://[^\s<>\"']+", text):
        try:
            value = _url(value.rstrip(".,;)>]"))
        except ValueError:
            continue
        key = recommendation_key(value)
        if key is not None and (key[0] != "generic" or job_shortcode(value) is not None):
            candidates.setdefault(key, value)
    if len(candidates) != 1:
        return ""
    explicit = re.findall(
        r"(?im)^\s*(?:apply(?:\s+(?:at|here|url|link))?|application(?:\s+(?:url|link))?"
        r"|申请(?:链接|地址)|投递(?:链接|地址))\s*[:：]?\s*(https://[^\s<>\"']+)",
        text,
    )
    for value in explicit:
        try:
            value = _url(value.rstrip(".,;)>]"))
        except ValueError:
            continue
        if recommendation_key(value) in candidates:
            return value
    return ""


class _MailboxResultUnknown(Exception):
    """An external mailbox operation needs readback before retry."""


class ApplicationIntakeService:
    """One private writer and one serial runner, started only by refresh()."""

    def __init__(
        self,
        applications,
        root: Path,
        *,
        reader=read_recommendation_emails,
        fetcher=fetch_job_source_or_browser,
        extractor=extract_job_fields,
        processed_label=None,
        mailbox=process_recommendation_email,
    ):
        if processed_label is not None and (
            not isinstance(processed_label, str)
            or not 1 <= len(processed_label.strip()) <= 225
            or not processed_label.isprintable()
            or processed_label.upper() in {"INBOX", "TRASH", "SPAM", "UNREAD", "SENT", "DRAFT"}
        ):
            raise PortalDataError("gmail_processing_invalid", "请配置专用的邮件处理标签。")
        self.processed_label, self.mailbox = processed_label, mailbox
        self.mail_processing_error = ""
        self.applications = applications
        self.root = private_root(Path(root))
        if self.root.is_relative_to(applications.root) or applications.root.is_relative_to(
            self.root
        ):
            raise PortalDataError("intake_root_conflict", "推荐目录与投递记录目录须独立。", 409)
        self.path = self.root / "intake.json"
        self.reader, self.fetcher, self.extractor = reader, fetcher, extractor
        self._closed = threading.Event()
        self._owner_guard = threading.Lock()
        self._admission_guard = threading.Lock()
        self._queue = queue.Queue()
        self._thread = None
        self._runtime_error = ""
        try:
            descriptor = os.open(
                self.root / ".intake.lock", os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600
            )
            self._lock_file = os.fdopen(descriptor, "a")
            try:
                fcntl.flock(self._lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
                self._owner = True
            except BlockingIOError:
                self._owner = False
            with self.applications.write_lock():
                if self.path.exists() or self.path.is_symlink():
                    self._load()
                elif self._owner:
                    self._save(
                        {
                            "schemaVersion": 1,
                            "applications_root": str(applications.root),
                            "status": "idle",
                            "run_id": None,
                            "error_code": "",
                            "reader_status": None,
                            "message_count": 0,
                            "candidate_count": 0,
                            "skipped_count": 0,
                            "max_results": None,
                            "max_candidates": None,
                        }
                    )
                else:
                    raise PortalDataError(
                        "intake_busy", "推荐读取器正在初始化，请重新读取状态。", 409
                    )
                self.store = RecommendationStore(self.root / "recommendations", applications)
                self.store.snapshot()
                if self._owner:
                    self._interrupt()
        except BaseException:
            if hasattr(self, "_lock_file"):
                self._lock_file.close()
            raise
        if self._owner:
            self._thread = threading.Thread(
                target=self._run, name="application-intake", daemon=True
            )
            self._thread.start()

    def _load(self):
        try:
            if self.path.is_symlink():
                raise ValueError("unsafe-state")
            state = helper.read_json_object(self.path, "application intake")
            if (
                state.get("schemaVersion") != 1
                or state.get("applications_root") != str(self.applications.root)
                or state.get("status")
                not in {
                    "idle",
                    "running",
                    "complete",
                    "no_matches",
                    "unavailable",
                    "failed",
                    "interrupted",
                    "partial",
                }
                or (state.get("status") != "idle" and state.get("run_id") is None)
                or (
                    state.get("run_id") is not None
                    and re.fullmatch(r"[a-f0-9]{32}", state.get("run_id", "")) is None
                )
                or not isinstance(state.get("error_code"), str)
                or state.get("reader_status") not in {None, "readable", "no_matches", "unavailable"}
                or any(
                    type(state.get(field)) is not int or state[field] < 0
                    for field in ("message_count", "candidate_count", "skipped_count")
                )
                or any(
                    state.get(field) is not None
                    and (type(state[field]) is not int or not 1 <= state[field] <= maximum)
                    for field, maximum in (("max_results", 10), ("max_candidates", 20))
                )
                or state.get("revision")
                != digest({key: value for key, value in state.items() if key != "revision"})
            ):
                raise ValueError("invalid-state")
            return state
        except (OSError, ValueError, TypeError, helper.StoreError) as error:
            raise PortalDataError(
                "intake_invalid", "推荐读取状态不能核验，请保留原件。", 409
            ) from error

    def _save(self, state):
        if self.path.is_symlink():
            raise PortalDataError("intake_invalid", "推荐读取状态不能使用符号链接。", 409)
        state["revision"] = digest(
            {key: value for key, value in state.items() if key != "revision"}
        )
        helper.atomic_write_json(self.path, state)

    def _interrupt(self):
        state = self._load()
        if state["status"] == "running":
            state.update(status="interrupted", error_code="intake_interrupted")
            if state.get("operation") == "ingest" and state.get("job"):
                state["job"].update(status="needs_recheck", error_code="intake_interrupted")
                self._save_job(state["job"])
            self._save(state)

    def _writable(self):
        if self._runtime_error:
            raise PortalDataError(
                "intake_storage_failed", "推荐状态保存失败，请保留记录并重开核验。", 503
            )
        if self._closed.is_set() or not self._owner:
            raise PortalDataError("intake_busy", "推荐读取器暂不可用，请重新读取状态。", 409)

    @staticmethod
    def _mail_processing(state):
        """Select account-local checkpoints without rewriting older account history."""
        identity = state.get("paging", {}).get("scope", {}).get("mailbox_identity")
        return {
            key: row
            for key, row in state.get("mail_processing", {}).items()
            if row.get("mailbox_identity") == identity
        }

    def source_delivery(self, run_id):
        """Read one saved run's application delivery without acquiring sources again."""
        try:
            if not isinstance(run_id, str) or re.fullmatch(r"[a-f0-9]{32}", run_id) is None:
                raise ValueError("invalid source run")
            path = self.root / "runs" / run_id / "source-chain.json"
            if any(part.is_symlink() for part in (path, path.parent, path.parent.parent)):
                raise ValueError("redirected source receipt")
            chain = helper.read_json_object(path, "saved intake source delivery")
            version = chain.get("schemaVersion", 1)
            if (
                type(version) is not int
                or version != 1
                or not isinstance(chain.get("sources"), list)
            ):
                raise ValueError("invalid source receipt")
            identifiers = []
            for row in chain["sources"]:
                if not isinstance(row, dict):
                    raise ValueError("invalid source entry")
                if row.get("save_status") != "saved":
                    continue
                identifier = row.get("application_id")
                if not isinstance(identifier, str) or not identifier.strip():
                    raise ValueError("invalid saved application")
                if identifier not in identifiers:
                    identifiers.append(identifier)
            return {
                "schema_version": "intake-source-delivery/v1",
                "run_id": run_id,
                "application_ids": identifiers,
            }
        except (OSError, ValueError, TypeError, KeyError, helper.StoreError) as error:
            raise PortalDataError(
                "intake_source_invalid", "本次已保存的岗位来源不能核验；保留原记录。", 409
            ) from error

    def snapshot(self):
        with self.applications.write_lock():
            state = deepcopy(self._load())
            paging = state.get("paging", {})
            records = self.store.snapshot()["recommendations"]
            pending = paging.get("pending_candidates", [])
            state["progress"] = {
                "pages": paging.get("pages", 0),
                "has_more": bool(paging.get("next_page_token")),
                "pending_candidates": len(pending),
                "incomplete_messages": len(paging.get("incomplete_messages", [])),
                "unread_messages": len(paging.get("unread_message_ids", [])),
                "range_incomplete": bool(paging.get("range_incomplete")),
                "window": paging.get("scope", {}).get("window", ""),
                "account_verified": bool(paging.get("scope", {}).get("mailbox_identity"))
                and not paging.get("scope_invalid"),
                "can_continue": bool(paging)
                and not paging.get("scope_invalid")
                and (
                    bool(pending or paging.get("next_page_token"))
                    or state["status"] in {"failed", "unavailable", "interrupted"}
                ),
                "source_complete": sum(
                    r.get("acquisition_checkpoint") == "complete" for r in records
                ),
                "source_failed": sum(r.get("acquisition_checkpoint") == "failed" for r in records),
                "source_needs_recheck": sum(
                    r.get("acquisition_checkpoint") == "needs_recheck" for r in records
                ),
            }
            # Raw cursor, account context and message IDs belong only in private state.
            processing = self._mail_processing(state)
            state.pop("mail_processing", None)
            state["progress"].update(
                mail_captured=len(processing),
                mail_labeled=sum(row["label_status"] == "complete" for row in processing.values()),
                mail_archived=sum(
                    row["archive_status"] == "complete" for row in processing.values()
                ),
                mail_needs_recheck=sum(
                    "needs_recheck" in {row["label_status"], row["archive_status"]}
                    for row in processing.values()
                ),
                mail_label_configured=self.processed_label is not None,
                mail_processing_error=self.mail_processing_error,
            )
            if state.get("capture_only"):
                state["progress"]["can_continue"] = (
                    bool(paging)
                    and not paging.get("scope_invalid")
                    and (
                        bool(paging.get("next_page_token"))
                        or bool(state["progress"]["mail_needs_recheck"])
                        or state["status"] in {"failed", "unavailable", "interrupted"}
                    )
                )
            state.pop("paging", None)
            return state | {
                "enabled": self._owner and not self._closed.is_set() and not self._runtime_error,
                "runtime_error": self._runtime_error,
                "recommendations": records,
            }

    def _job_path(self, request_id):
        path = self.root / "ingestions" / f"{request_id}.json"
        if path.is_symlink() or path.parent.is_symlink():
            raise PortalDataError("intake_invalid", "岗位整理日志不能核验。", 409)
        return path

    def _save_job(self, job):
        helper.atomic_write_json(self._job_path(job["request_id"]), job | {"revision": digest(job)})

    def _read_job(self, request_id):
        path = self._job_path(request_id)
        if not path.exists():
            return None
        saved = helper.read_json_object(path, "source intake")
        revision = saved.pop("revision", None)
        if revision != digest(saved) or saved.get("request_id") != request_id:
            raise PortalDataError("intake_invalid", "岗位整理日志不能核验。", 409)
        return saved

    def ingest(self, *, request_id, text=None, url=None):
        """Persist admission before queued IO. A repeated request never replays IO."""
        if (
            not isinstance(request_id, str)
            or re.fullmatch(r"[a-f0-9]{32}", request_id) is None
            or (text is None) == (url is None)
            or (
                text is not None
                and (not isinstance(text, str) or not 1 <= len(text.strip()) <= 180000)
            )
        ):
            raise PortalDataError("invalid_intake_request", "请粘贴完整 JD 或提供一个岗位链接。")
        if url is not None:
            try:
                url = _url(url)
            except ValueError as error:
                raise PortalDataError(
                    "invalid_intake_request", "请提供公开 HTTPS 岗位链接。"
                ) from error
        source = {"text": text, "url": url}
        with self.applications.write_lock():
            self._writable()
            prior = self._read_job(request_id)
            if prior:
                if prior["input_revision"] != digest(source):
                    raise PortalDataError(
                        "intake_conflict", "同一次整理的来源已改变，请先核验记录。", 409
                    )
                return self.snapshot() | {"job": prior}
            state = self._load()
            if state["status"] == "running":
                raise PortalDataError("intake_busy", "已有岗位整理或读取正在运行。", 409)
            job = {
                "request_id": request_id,
                "input_revision": digest(source),
                "status": "running",
                "source_kind": "pasted-jd" if text is not None else "job-page",
                "application_id": None,
                "error_code": "",
                "missing_fields": [],
                "fields": {"job_description": text or "", "url": url or ""},
            }
            run_id = uuid4().hex
            self._artifact(self.root / "runs" / run_id / "input.json", source)
            self._save_job(job)
            state.update(
                status="running", run_id=run_id, operation="ingest", error_code="", job=job
            )
            # The private run request retains the original input before any external work.
            self._save(state)
            self._queue.put(deepcopy(state) | {"input": source})
            return self.snapshot()

    def reconcile_job(self, request_id):
        if not isinstance(request_id, str) or re.fullmatch(r"[a-f0-9]{32}", request_id) is None:
            raise PortalDataError("invalid_intake_request", "岗位整理标识无效。")
        with self.applications.write_lock():
            self._writable()
            job = self._read_job(request_id)
            if not job:
                raise PortalDataError("intake_not_found", "找不到此整理记录。", 404)
            state = self._load()
            if (
                job["status"] == "needs_recheck"
                and job.get("error_code") == "intake_interrupted"
                and not job.get("recommendation_id")
                and not (
                    state["status"] == "running"
                    and state.get("job", {}).get("request_id") == request_id
                )
            ):
                # Selection is admitted only after recommendation_id is durably saved.
                # The exclusive intake owner proves the interrupted runner has exited.
                job.update(status="failed", error_code="intake_interrupted_before_save")
                self._save_job(job)
                if state.get("job", {}).get("request_id") == request_id:
                    state.update(job=job, status="failed", error_code=job["error_code"])
                    self._save(state)
            if job.get("recommendation_id") and job["status"] == "needs_recheck":
                selected = self.store.reconcile_selection(job["recommendation_id"])
                if selected:
                    job.update(
                        status="saved", application_id=selected["application"]["id"], error_code=""
                    )
                    self._save_job(job)
                    state = self._load()
                    if state.get("job", {}).get("request_id") == request_id:
                        state.update(job=job, status="complete", error_code="")
                        self._save(state)
            return self.snapshot() | {"job": job}

    def _perform_ingest(self, request, run):
        source, job = request["input"], deepcopy(request["job"])
        if source["text"] is not None:
            explicit_url = _explicit_pasted_job_url(source["text"])
            capture = {"body_text": source["text"], "url": explicit_url, "final_url": explicit_url}
        else:
            capture = self.fetcher(source["url"])
            if not isinstance(capture, dict):
                raise ValueError("invalid-page")
        capture = capture | {
            "source_kind": job["source_kind"],
            "captured_at": datetime.now(UTC).isoformat(),
        }
        self._artifact(run / "source.json", capture)
        with self.applications.write_lock():
            if not self._admit(request):
                return
            job["fields"] = {
                "job_description": capture.get("body_text", ""),
                "url": capture.get("final_url", capture.get("url", source.get("url") or "")),
            }
            self._save_job(job)
            state = self._load()
            state["job"] = job
            self._save(state)
        if source["url"] is not None and capture.get("acquisition_status") != "available":
            job.update(
                status="needs_input",
                error_code=capture.get("error_code") or "intake_source_unavailable",
            )
        else:
            structured = capture.get("job_fields", {})
            if capture.get("jd_completeness") == "full" and all(
                isinstance(structured.get(key), str) and structured[key].strip()
                for key in ("company", "title")
            ):
                fields = {
                    "company": structured["company"],
                    "role_title": structured["title"],
                    "location": structured.get("location", ""),
                    "is_full_jd": True,
                }
                fields.update(
                    {
                        key: structured[key]
                        for key in ("datePosted", "validThrough", "baseSalary", "employmentType")
                        if key in structured
                    }
                )
            else:
                fields = self.extractor(capture.get("body_text", ""), run / "extraction")
            job["fields"] = fields | {
                "job_description": capture.get("body_text", ""),
                "url": capture.get("final_url", capture.get("url", "")),
            }
            job["missing_fields"] = [
                key
                for key in ("company", "role_title")
                if not isinstance(fields.get(key), str) or not fields[key].strip()
            ]
            if job["missing_fields"] or not fields.get("is_full_jd"):
                job.update(status="needs_input", error_code="intake_source_incomplete")
            else:
                with self.applications.write_lock():
                    if not self._admit(request):
                        return
                    record = self.store.import_document(capture, fields)
                    job.update(recommendation_id=record["id"], status="needs_recheck")
                    self._save_job(job)
                    state = self._load()
                    state["job"] = job
                    self._save(state)
                    selected = self.store.select(record["id"], record["revision"])
                    job.update(status="saved", application_id=selected["application"]["id"])
        with self.applications.write_lock():
            if self._admit(request):
                self._save_job(job)
                state = self._load()
                state.update(status="complete", job=job, error_code=job["error_code"])
                self._save(state)

    def _scope(self, *, query=None, window_context=None, after=None, before=None):
        from .application_preparation import preparation_inputs

        if after is not None or before is not None:
            try:
                start, end = date.fromisoformat(after), date.fromisoformat(before)
                if start >= end or query is not None:
                    raise ValueError("invalid-range")
            except (TypeError, ValueError) as error:
                raise PortalDataError("intake_range_invalid", "请指定有序的起止日期。") from error
            query = RECOMMENDATION_QUERY.replace(
                "newer_than:7d",
                f"after:{int(datetime.combine(start, datetime.min.time(), UTC).timestamp())} "
                f"before:{int(datetime.combine(end, datetime.min.time(), UTC).timestamp())}",
            )
            window_context = f"{start.isoformat()} — {end.isoformat()} (UTC)"
        if query is None:
            end = datetime.now(UTC).date() + timedelta(days=1)
            return self._scope(after=(end - timedelta(days=7)).isoformat(), before=end.isoformat())
        query = validate_recommendation_query(query)
        window = window_context or query.split(" (from:", 1)[0]
        if not isinstance(window, str) or not 1 <= len(window) <= 256:
            raise PortalDataError("intake_range_invalid", "读取范围标识无效。")
        return {
            "query": query,
            "window": window,
            "account": preparation_inputs(self.applications.root)["account_context_revision"],
        }

    def refresh(
        self,
        max_results=3,
        max_candidates=10,
        *,
        query=None,
        window_context=None,
        after=None,
        before=None,
        capture_only=False,
    ):
        if (
            type(capture_only) is not bool
            or type(max_results) is not int
            or not 1 <= max_results <= 10
            or type(max_candidates) is not int
            or not 1 <= max_candidates <= 20
        ):
            raise PortalDataError(
                "intake_limit_invalid", "邮件数须为 1 至 10，岗位数须为 1 至 20。"
            )
        with self.applications.write_lock():
            self._writable()
            state = self._load()
            if state["status"] != "running":
                scope = self._scope(
                    query=query, window_context=window_context, after=after, before=before
                )
                state.update(
                    status="running",
                    run_id=uuid4().hex,
                    error_code="",
                    reader_status=None,
                    message_count=0,
                    candidate_count=0,
                    skipped_count=0,
                    max_results=max_results,
                    max_candidates=max_candidates,
                    operation="mail",
                    capture_only=capture_only,
                    paging={
                        "scope": scope,
                        "next_page_token": None,
                        "pages": 0,
                        "seen_message_ids": [],
                        "pending_candidates": [
                            row["id"]
                            for row in self.store.snapshot()["recommendations"]
                            if not row.get("existing_application")
                        ]
                        if capture_only
                        else [],
                        "incomplete_messages": [],
                        "unread_message_ids": [],
                    },
                )
                state.pop("replay_reader", None)
                self._save(state)
                self._queue.put(deepcopy(state))
            return self.snapshot()

    def continue_read(
        self, *, revision=None, query=None, window_context=None, after=None, before=None
    ):
        with self.applications.write_lock():
            self._writable()
            state = self._load()
            if revision is not None and revision != state["revision"]:
                raise PortalDataError("intake_conflict", "读取进度已变化，请重新读取状态。", 409)
            paging = state.get("paging")
            if not paging:
                raise PortalDataError(
                    "intake_cursor_unavailable", "旧读取没有可核验续点，请明确更新推荐。", 409
                )
            previous = paging["scope"]
            current = self._scope(
                query=query or (previous["query"] if after is None and before is None else None),
                window_context=window_context or previous["window"],
                after=after,
                before=before,
            )
            if current != {
                key: value for key, value in previous.items() if key != "mailbox_identity"
            } or paging.get("scope_invalid"):
                raise PortalDataError(
                    "intake_scope_changed", "账号、查询或时间范围已变化，请重新更新推荐。", 409
                )
            if state["status"] == "running":
                return self.snapshot()
            if not (
                paging.get("pending_candidates")
                or paging.get("next_page_token")
                or state["status"] in {"failed", "unavailable", "interrupted"}
                or any(
                    "needs_recheck" in {row["label_status"], row["archive_status"]}
                    for row in self._mail_processing(state).values()
                )
            ):
                raise PortalDataError(
                    "intake_range_complete", "当前范围没有可继续的页；未完整邮件须单独补齐。", 409
                )
            previous_run = state["run_id"]
            replay = self.root / "runs" / previous_run / "reader-result.json"
            state.update(status="running", error_code="", run_id=uuid4().hex, operation="continue")
            if (
                paging.get("adopted_run_id") != previous_run
                and replay.is_file()
                and helper.read_json_object(replay, "retained reader result").get("status")
                in {"readable", "no_matches"}
            ):
                state["replay_reader"] = str(replay.relative_to(self.root))
            else:
                state.pop("replay_reader", None)
            if (
                state.get("capture_only")
                and not paging.get("next_page_token")
                and paging.get("adopted_run_id") == previous_run
            ):
                state["operation"] = "mail_cleanup"
            self._save(state)
            self._queue.put(deepcopy(state))
            return self.snapshot()

    def select(self, identifier, revision):
        with self.applications.write_lock():
            self._writable()
            return self.store.select(identifier, revision)

    def _artifact(self, path, payload):
        if any(parent.is_symlink() for parent in (path, *path.parents)) or path.exists():
            raise PortalDataError(
                "intake_capture_invalid", "推荐捕获须使用新的独立文件，请保留原件。", 409
            )
        helper.atomic_write_json(path, payload)

    def _admit(self, request):
        """Admit one external operation; close rejects new admissions, not in-flight IO."""
        with self.applications.write_lock():
            state = self._load()
            with self._admission_guard:
                return (
                    not self._closed.is_set()
                    and self._owner
                    and state["status"] == "running"
                    and state["run_id"] == request["run_id"]
                )

    def acquire(self, identifier, revision, *, retry=False):
        """Explicitly obtain one persisted candidate, independently of mail paging."""
        if (
            type(retry) is not bool
            or not isinstance(identifier, str)
            or re.fullmatch(r"[a-f0-9]{32}", identifier) is None
            or not isinstance(revision, str)
            or re.fullmatch(r"[a-f0-9]{64}", revision) is None
        ):
            raise PortalDataError("invalid_intake_request", "请明确确认是否重试。")
        with self.applications.write_lock():
            self._writable()
            state = self._load()
            if state["status"] == "running":
                raise PortalDataError("intake_busy", "已有读取或岗位取源正在运行。", 409)
            row = next(
                (r for r in self.store.snapshot()["recommendations"] if r["id"] == identifier), None
            )
            if row is None:
                raise PortalDataError("recommendation_not_found", "找不到此岗位推荐。", 404)
            if row["revision"] != revision:
                raise PortalDataError(
                    "recommendation_conflict", "岗位已变化，请读取最新状态。", 409
                )
            if row.get("acquisition_checkpoint") == "needs_recheck":
                raise PortalDataError(
                    "intake_source_needs_recheck", "请先核验已保存的取源结果。", 409
                )
            if row.get("acquisition_checkpoint") == "failed" and not retry:
                raise PortalDataError("intake_source_retry_required", "请明确重试此岗位取源。", 409)
            state.update(
                status="running",
                return_status=state["status"],
                run_id=uuid4().hex,
                operation="source",
                source_id=identifier,
                source_retry=retry,
                max_results=state["max_results"] or 3,
                max_candidates=state["max_candidates"] or 10,
                error_code="",
            )
            self._save(state)
            self._queue.put(deepcopy(state))
            return self.snapshot()

    def reconcile_source(self, identifier):
        if not isinstance(identifier, str) or re.fullmatch(r"[a-f0-9]{32}", identifier) is None:
            raise PortalDataError("invalid_intake_request", "岗位标识无效。")
        with self.applications.write_lock():
            self._writable()
            self.store.reconcile_acquisition(identifier)
            return self.snapshot()

    def _acquire_candidate(self, request, row, run, index, *, retry=False):
        if not self._admit(request):
            return None
        attempt = self.store.begin_acquisition(row["id"], row["revision"], retry=retry)
        if attempt["status"] != "fetch" or not self._admit(request):
            return {"recommendation_id": row["id"], "checkpoint": attempt["status"], "reused": True}
        canonical = _canonical(row.get("mail_url", row["url"])) or row["url"]
        try:
            capture = self.fetcher(canonical)
            if not isinstance(capture, dict):
                raise ValueError("invalid-page")
        except Exception:
            capture = {
                "capture_id": uuid4().hex,
                "url": canonical,
                "final_url": canonical,
                "body_text": "",
                "jd_completeness": "unknown",
                "acquisition_status": "unavailable",
                "source_format": "page",
                "job_fields": {},
                "redirects": [],
                "error_code": "intake_fetch_failed",
            }
        capture.setdefault("captured_at", datetime.now(UTC).isoformat())
        # The per-job receipt survives even if the later batch progress write fails.
        self.store.finish_acquisition(row["id"], attempt["attempt_id"], capture)
        self._artifact(run / "pages" / f"{index}.json", capture)
        return {
            "recommendation_id": row["id"],
            "page_capture_id": capture.get("capture_id"),
            "page_capture_revision": digest(capture),
            "page_path": f"pages/{index}.json",
            "captured_at": capture["captured_at"],
            "canonical_url": canonical,
        }

    def _save_complete_candidate(self, identifier):
        """Organizing a complete JD saves a note; it grants no material or worker authority."""
        with self.applications.write_lock():
            row = next(
                (
                    item
                    for item in self.store.snapshot()["recommendations"]
                    if item["id"] == identifier
                ),
                None,
            )
            if row is None or row.get("jd_completeness") != "full":
                return {"save_status": "needs_input"}
            try:
                result = self.store.select(row["id"], row["revision"])
                return {"save_status": "saved", "application_id": result["application"]["id"]}
            except PortalDataError as error:
                return {"save_status": "needs_recheck", "save_error_code": error.code}

    def _perform(self, request):
        run = self.root / "runs" / request["run_id"]
        self._artifact(run / "request.json", request)
        if not self._admit(request):
            return
        if request.get("operation") == "mail_cleanup":
            self._finish_capture(request, run, None)
            return
        if request.get("operation") == "ingest":
            self._perform_ingest(request, run)
            return
        if request.get("operation") == "source":
            row = next(
                r
                for r in self.store.snapshot()["recommendations"]
                if r["id"] == request["source_id"]
            )
            self._acquire_candidate(request, row, run, 0, retry=request.get("source_retry", False))
            if self._admit(request):
                self._save_complete_candidate(row["id"])
            with self.applications.write_lock():
                if self._admit(request):
                    state = self._load()
                    state.update(status=request["return_status"], error_code="")
                    self._save(state)
            return
        paging = deepcopy(request.get("paging", {}))
        scope = paging.get("scope", {})
        pending = list(paging.get("pending_candidates", []))
        chain, messages, result = [], [], None
        save_conflict = False
        if not (
            request.get("operation") == "continue" and pending and not request.get("capture_only")
        ):
            replay = request.get("replay_reader")
            if replay:
                path = self.root / replay
                if path.is_symlink() or not path.is_relative_to(self.root):
                    raise ValueError("invalid-reader-replay")
                result = helper.read_json_object(path, "retained reader result")
            else:
                if not self._admit(request):
                    return
                options = {
                    "max_results": request["max_results"],
                    "query": scope["query"],
                    "page_token": paging.get("next_page_token"),
                    "account_context": scope["account"],
                    "window_context": scope["window"],
                    "verify_account": True,
                    "expected_mailbox_identity": scope.get("mailbox_identity"),
                    "admit_search": lambda: self._admit(request),
                }
                parameters = signature(self.reader).parameters
                if not any(p.kind == Parameter.VAR_KEYWORD for p in parameters.values()):
                    if options["page_token"] and "page_token" not in parameters:
                        raise PortalDataError(
                            "intake_adapter_incomplete", "当前读取器不支持续读。", 409
                        )
                    options = {key: value for key, value in options.items() if key in parameters}
                result = self.reader(run / "reader", **options)
            self._artifact(run / "reader-result.json", result)
            if (
                not isinstance(result, dict)
                or result.get("status") not in {"readable", "no_matches", "unavailable"}
                or not isinstance(result.get("emails"), list)
            ):
                raise ValueError("invalid-reader")
            if result["status"] == "unavailable":
                with self.applications.write_lock():
                    if self._admit(request):
                        state = self._load()
                        state.update(
                            status="unavailable",
                            reader_status="unavailable",
                            error_code="gmail_unavailable",
                        )
                        if result.get("reason") in {
                            "gmail_account_changed",
                            "mailbox_identity_changed",
                        }:
                            state["paging"].update(
                                next_page_token=None, scope_invalid=True, range_incomplete=True
                            )
                            state["error_code"] = "gmail_account_changed"
                        self._save(state)
                return
            messages = [normalize_message(raw) for raw in result["emails"]]
            if (
                len(messages) > request["max_results"]
                or len({m["message_id"] for m in messages}) != len(messages)
                or any(len(m["links"]) > 100 for m in messages)
                or (result["status"] != "readable" and messages)
            ):
                raise ValueError("invalid-reader")
            provenance = result.get("provenance", {})
            mailbox_identity = provenance.get("mailbox_identity")
            if mailbox_identity is not None and (
                not isinstance(mailbox_identity, str)
                or re.fullmatch(r"[a-f0-9]{64}", mailbox_identity) is None
                or scope.get("mailbox_identity", mailbox_identity) != mailbox_identity
            ):
                raise ValueError("mailbox-identity-mismatch")
            if (
                self.reader is read_recommendation_emails
                and provenance.get("account_identity_status") != "verified"
            ):
                raise ValueError("mailbox-identity-unverified")
            token = provenance.get("next_page_token") or None
            if token is not None and (not isinstance(token, str) or len(token) > 4096):
                raise ValueError("invalid-cursor")
            if token and token in [
                paging.get("next_page_token"),
                *paging.get("visited_page_tokens", []),
            ]:
                raise ValueError("cursor-stalled")
            if any(
                provenance.get(key) not in {None, expected}
                for key, expected in (
                    ("account_context", scope["account"]),
                    ("window_context", scope["window"]),
                    ("query", scope["query"]),
                )
            ):
                raise ValueError("reader-scope-mismatch")
            if mailbox_identity is not None:
                for mail in messages:
                    mail["mailbox_identity"] = mailbox_identity
            jobs, identifiers = [], []
            for mail_index, mail in enumerate(messages):
                mail_fields = {}
                mail_identities = {recommendation_key(link) for link in mail["links"]} - {None}
                if (
                    not request.get("capture_only")
                    and len(mail_identities) == 1
                    and mail["body_completeness"] == "full"
                    and mail["body_scope"] == "job_description"
                ):
                    known = self.store.snapshot()["recommendations"]
                    existing = next(
                        (
                            item
                            for item in known
                            if item.get("jd_completeness") == "full"
                            and item.get("job_description") == mail["body_text"]
                            and any(_canonical(link) == item["url"] for link in mail["links"])
                        ),
                        None,
                    )
                    if existing:
                        mail_fields = {
                            "company": existing["company"],
                            "role_title": existing["role_title"],
                            "location": existing.get("location", ""),
                            "is_full_jd": True,
                        }
                    elif self._admit(request):
                        mail_fields = self.extractor(
                            mail["body_text"], run / "mail-facts" / str(mail_index)
                        )
                mail_full = bool(
                    mail_fields.get("is_full_jd")
                    and all(mail_fields.get(key) for key in ("company", "role_title"))
                )
                for link in mail["links"]:
                    canonical = _canonical(link)
                    if canonical is None:
                        continue
                    identifier = digest(recommendation_key(canonical))[:32]
                    if identifier not in identifiers:
                        identifiers.append(identifier)
                    jobs.append(
                        {
                            "message_id": mail["message_id"],
                            "mail_url": link,
                            "url": canonical,
                            "company": mail_fields.get("company", "") if mail_full else "",
                            "role_title": mail_fields.get("role_title", "") if mail_full else "",
                            "job_description": mail["body_text"] if mail_full else "",
                            "location": mail_fields.get("location", "") if mail_full else "",
                            "jd_completeness": "full" if mail_full else "unknown",
                            "documentary_fields": mail_fields if mail_full else {},
                            "context": mail["subject"],
                            "context_kind": "email_subject",
                        }
                    )
            with self.applications.write_lock():
                if not self._admit(request):
                    return
                self.store.import_messages(messages, jobs)
                state = self._load()
                paging = state["paging"]
                if mailbox_identity is not None:
                    paging["scope"]["mailbox_identity"] = mailbox_identity
                paging["seen_message_ids"] = list(
                    dict.fromkeys(
                        [*paging["seen_message_ids"], *(m["message_id"] for m in messages)]
                    )
                )
                incomplete = {
                    m["message_id"]: "body_incomplete"
                    for m in messages
                    if m["body_completeness"] != "full"
                }
                previous_incomplete = {
                    r["message_id"]: r["reason"] for r in paging["incomplete_messages"]
                }
                for mail in messages:
                    previous_incomplete.pop(mail["message_id"], None)
                previous_incomplete.update(incomplete)
                paging["incomplete_messages"] = [
                    {"message_id": key, "reason": value}
                    for key, value in previous_incomplete.items()
                ]
                full_ids = {m["message_id"] for m in messages if m["body_completeness"] == "full"}
                paging["unread_message_ids"] = [
                    identifier
                    for identifier in dict.fromkeys(
                        [
                            *paging["unread_message_ids"],
                            *provenance.get("unread_message_ids", []),
                        ]
                    )
                    if identifier not in full_ids
                ]
                paging.setdefault("visited_page_tokens", []).append(paging.get("next_page_token"))
                paging.update(
                    next_page_token=token,
                    pages=paging["pages"] + 1,
                    range_incomplete=bool(provenance.get("has_more") and not token),
                    adopted_run_id=request["run_id"],
                )
                pending = list(dict.fromkeys([*paging["pending_candidates"], *identifiers]))
                paging["pending_candidates"] = pending
                state.update(
                    message_count=len(paging["seen_message_ids"]), reader_status=result["status"]
                )
                if request.get("capture_only"):
                    processing = state.setdefault("mail_processing", {})
                    for mail in messages:
                        if mail["body_completeness"] == "full":
                            checkpoint_key = digest(
                                {
                                    "mailbox_identity": mailbox_identity,
                                    "message_id": mail["message_id"],
                                }
                            )
                            existing = any(
                                row.get("mailbox_identity") == mailbox_identity
                                and row.get("message_id", key) == mail["message_id"]
                                for key, row in processing.items()
                            )
                            if existing:
                                continue
                            processing.setdefault(
                                checkpoint_key,
                                {
                                    "message_id": mail["message_id"],
                                    "label_status": "pending",
                                    "archive_status": "pending",
                                    "label_name": self.processed_label,
                                    "mailbox_identity": mailbox_identity,
                                },
                            )
                self._save(state)
        if request.get("capture_only"):
            self._finish_capture(request, run, result)
            return
        selected, remaining = (
            pending[: request["max_candidates"]],
            pending[request["max_candidates"] :],
        )
        for index, identifier in enumerate(selected):
            if not self._admit(request):
                return
            records = self.store.snapshot()["recommendations"]
            row = next((r for r in records if r["id"] == identifier), None)
            if row is None:
                # A proved redirect can merge this pending ID into a completed job.
                row = next(
                    (
                        r
                        for r in records
                        if r.get("acquisition_checkpoint") == "complete"
                        and r.get("canonical_key")
                        and digest(r["canonical_key"])[:32] == identifier
                    ),
                    None,
                )
            if row is None:
                raise ValueError("missing-candidate")
            acquired = self._acquire_candidate(request, row, run, index)
            if acquired and self._admit(request):
                acquired.update(self._save_complete_candidate(row["id"]))
                save_conflict = save_conflict or acquired.get("save_status") == "needs_recheck"
            if acquired:
                sources = [
                    s
                    for s in row["source_messages"]
                    if not messages or s["message_id"] in {m["message_id"] for m in messages}
                ]
                chain.extend(
                    acquired | {"message_id": s["message_id"], "mail_url": s["url"]}
                    for s in sources
                )
            with self.applications.write_lock():
                if not self._admit(request):
                    return
                state = self._load()
                state["paging"]["pending_candidates"] = [
                    p for p in state["paging"]["pending_candidates"] if p != identifier
                ]
                self._save(state)
        self._artifact(
            run / "source-chain.json",
            {
                "schemaVersion": 1,
                "reader": "reader" if result is not None else None,
                "reader_result_revision": digest(result) if result is not None else None,
                "provenance": result.get("provenance", {}) if result else {},
                "sources": chain,
            },
        )
        with self.applications.write_lock():
            if not self._admit(request):
                return
            state = self._load()
            paging = state["paging"]
            incomplete = bool(
                paging["next_page_token"]
                or paging["pending_candidates"]
                or paging["incomplete_messages"]
                or paging["unread_message_ids"]
                or paging.get("range_incomplete")
            )
            state.update(
                status="partial"
                if incomplete or save_conflict
                else "complete"
                if state["message_count"]
                else "no_matches",
                candidate_count=len(selected),
                skipped_count=len(remaining),
                error_code="recommendation_source_conflict" if save_conflict else "",
            )
            self._save(state)

    def _process_captured_mail(self, request, run):
        if self.processed_label is None:
            return
        state = self._load()
        for identifier, checkpoint in self._mail_processing(state).items():
            if not self._admit(request):
                return
            if checkpoint["label_status"] == checkpoint["archive_status"] == "complete":
                continue
            label = checkpoint.get("label_name") or self.processed_label
            checkpoint["label_name"] = label
            options = {
                "message_id": checkpoint.get("message_id", identifier),
                "label_name": label,
                "expected_mailbox_identity": checkpoint.get("mailbox_identity"),
            }

            def call(operation, options=options):
                if not self._admit(request):
                    raise _MailboxResultUnknown("intake-interrupted")
                try:
                    result = self.mailbox(
                        run / "mail-processing" / uuid4().hex, operation=operation, **options
                    )
                except Exception as error:
                    raise _MailboxResultUnknown("mailbox-result-unknown") from error
                if not isinstance(result, dict) or result.get("status") != "complete":
                    raise _MailboxResultUnknown("mailbox-result-unknown")
                return result

            try:
                actual = call("inspect")
                for operation, field in (("label", "labeled"), ("archive", "archived")):
                    key = operation + "_status"
                    if type(actual.get(field)) is not bool:
                        raise _MailboxResultUnknown("mailbox-state-unknown")
                    if not actual[field]:
                        checkpoint[key] = "needs_recheck"
                        with self.applications.write_lock():
                            current = self._load()
                            current["mail_processing"][identifier] = checkpoint
                            self._save(current)
                        call(operation)
                        actual = call("inspect")
                        if actual.get(field) is not True:
                            raise _MailboxResultUnknown("mailbox-change-unverified")
                    checkpoint[key] = "complete"
                    with self.applications.write_lock():
                        current = self._load()
                        current["mail_processing"][identifier] = checkpoint
                        self._save(current)
            except _MailboxResultUnknown:
                key = (
                    "label_status" if checkpoint["label_status"] != "complete" else "archive_status"
                )
                checkpoint[key] = "needs_recheck"
                with self.applications.write_lock():
                    current = self._load()
                    current["mail_processing"][identifier] = checkpoint
                    self._save(current)

    def _finish_capture(self, request, run, result):
        """Finish this saved page, then automatically read the next bounded API page."""
        self._process_captured_mail(request, run)
        self._artifact(
            run / "source-chain.json",
            {
                "schemaVersion": 1,
                "reader": "reader",
                "reader_result_revision": digest(result) if result is not None else None,
                "provenance": result.get("provenance", {}) if result else {},
                "sources": [],
            },
        )
        with self.applications.write_lock():
            if not self._admit(request):
                return
            state = self._load()
            paging = state["paging"]
            if paging.get("next_page_token"):
                state.update(run_id=uuid4().hex, operation="mail")
                state.pop("replay_reader", None)
                self._save(state)
                self._queue.put(deepcopy(state))
                return
            incomplete = bool(
                paging["incomplete_messages"]
                or paging["unread_message_ids"]
                or paging.get("range_incomplete")
                or any(
                    "needs_recheck" in {row["label_status"], row["archive_status"]}
                    for row in self._mail_processing(state).values()
                )
            )
            state.update(
                status="partial"
                if incomplete
                else "complete"
                if state["message_count"]
                else "no_matches",
                candidate_count=len(paging["pending_candidates"]),
                skipped_count=0,
            )
            self._save(state)

    def _run(self):
        try:
            while not self._closed.is_set():
                request = self._queue.get()
                if request is None:
                    return
                try:
                    self._perform(request)
                except Exception as error:
                    try:
                        with self.applications.write_lock():
                            if self._closed.is_set():
                                return
                            state = self._load()
                            if (
                                state["run_id"] == request["run_id"]
                                and state["status"] == "running"
                            ):
                                state.update(status="failed", error_code="intake_failed")
                                if request.get("operation") == "ingest":
                                    job = state["job"]
                                    job.update(
                                        status="needs_recheck"
                                        if job.get("recommendation_id")
                                        else "failed",
                                        error_code=error.code
                                        if isinstance(error, PortalDataError)
                                        else "intake_failed",
                                    )
                                    self._save_job(job)
                                self._save(state)
                    except Exception:
                        self._runtime_error = "intake_storage_failed"
                        return
        finally:
            self._release_owner()

    def _release_owner(self):
        with self._owner_guard:
            if not self._lock_file.closed:
                self._lock_file.close()
            self._owner = False

    def close(self):
        with self._admission_guard:
            self._closed.set()
        self._queue.put(None)
        if self._owner:
            try:
                with self.applications.write_lock():
                    self._interrupt()
            except Exception:
                self._runtime_error = "intake_storage_failed"
        if self._thread is not None:
            self._thread.join(timeout=0.05)
        if self._thread is None or not self._thread.is_alive():
            self._release_owner()
