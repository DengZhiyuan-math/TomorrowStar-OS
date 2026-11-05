"""Durable email-to-review progression owned by the App backend."""

from __future__ import annotations

import fcntl
import json
import os
import re
import threading
import time
from contextlib import contextmanager
from contextvars import ContextVar
from copy import deepcopy
from pathlib import Path
from urllib.parse import urlsplit
from uuid import uuid4

from ._vendor import job_apply_store as helper
from .application_eligibility import task_eligibility
from .application_explanations import adopted_analysis
from .application_flow import (
    legacy_analysis_failure as _known_analysis_failure,
)
from .application_flow import pipeline_http_entry
from .application_input_binding import job_input_revision
from .application_match_refresh import match_refresh_running, require_no_other_match_refresh
from .application_match_scoring import calculate_match_score, combined_score, score_tier
from .career_portal_data import PortalDataError
from .job_screening import application_country, application_route, screen_applications
from .validation.hashing import record_digest as digest

PROTOCOL = "application-pipeline/v1"
POLICY = "email-to-manual-submit/v1"
QUEUE_ASSERTION_LOG = "queue-state-assertions.jsonl"
# Seconds a current result read may stay pending before it is asked again.
RESULT_READ_WAIT = 30


def queue_state(state):
    """Read-only projection of the queue control fields (batch 1-D, before C4)."""
    return {
        key: state.get(key)
        for key in ("control", "status", "resume_status", "wait_reason", "active_task_id")
    }


# Flow material edits that first confirm the current job's Worker stop.
MATERIAL_EDIT_ACTIONS = {
    "edit-material",
    "capture-material-tex",
    "reconcile-material-edit",
    "begin-automatic-edit",
    "save-automatic-source",
    "begin-prism-edit",
    "finish-prism-edit",
    "capture-prism-result",
}
MATERIAL_EDIT_STOPPING = {
    "worker_running": "正在暂停当前填写，原页与材料保留；请稍后再保存修改。",
    "assistance_stopping": "正在确认 Codex 已停止操作原页，原页与材料保留；请稍后再保存修改。",
    "pending_intent": "原页仍有结果未明的动作，需先核验原页；材料修改暂不保存。",
    "continuation_pending": "原页继续操作尚在核验，请稍后再保存修改。",
}


_EXPORT_ENVIRONMENT_FAILURES = frozenset(
    {
        "prism_unavailable",
        "prism_not_running",
        "prism_result_unavailable",
        "resume_compiler_unavailable",
        "resume_export_failed",
    }
)


def _mismatch(eligibility):
    """The JD's hard conditions the saved facts do not meet, as listed to the user."""
    return [row["text"] for row in eligibility["conditions"] if row["status"] == "conflict"][:3]


class ApplicationPipeline:
    """A persistent mail queue with one current job and manual final submission."""

    def __init__(self, flow, intake, worker, *, interval=1, takeover_unavailable_reason=None):
        self.flow, self.intake, self.worker = flow, intake, worker
        # Automatic takeover is on but could not be configured at startup (MC-22).
        self.takeover_unavailable_reason = takeover_unavailable_reason
        self.path = Path(flow.root) / "pipeline.json"
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        lock_path = self.path.with_suffix(".lock")
        if self.path.is_symlink() or lock_path.is_symlink():
            raise PortalDataError("pipeline_invalid", "自动流程记录不能使用符号链接。", 409)
        self._guard = threading.RLock()
        self._closed = threading.Event()
        self._saved_control = None
        self._runtime_error = ""
        self._refresh_entry = ContextVar("pipeline_paused_refresh_entry", default=None)
        self._preparation_serial = 0
        self._lock_file = lock_path.open("a")
        try:
            fcntl.flock(self._lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
            self._owner = bool(getattr(flow, "_owner", True))
        except BlockingIOError:
            self._owner = False
        with self.flow.applications.write_lock():
            if not self.path.exists():
                if not self._owner:
                    raise PortalDataError("pipeline_busy", "自动流程正在初始化。", 409)
                self._save(
                    {
                        "schemaVersion": 1,
                        "protocol": PROTOCOL,
                        "policy_version": POLICY,
                        "control": "paused",
                        "status": "idle",
                        "id": None,
                        "request_id": None,
                        "intake_run_id": None,
                        "items": [],
                        "active_task_id": None,
                        "notification": None,
                        "authorization": None,
                        "transmission_authorization": None,
                    }
                )
            state = self._load()
            if (
                self._owner
                and state["control"] == "running"
                and (
                    not state.get("queue_mode")
                    or state["status"]
                    in {"starting_email", "starting_source", "preparing", "admitting_worker"}
                )
            ):
                self._stop(state, "interrupted", "App 已重启，保留原进度；先核验未完成结果。")
        self._verifier = self.verify_authorization
        if self._owner:
            flow.callbacks["verify_automation_authorization"] = self._verifier
        # Flow consults this permit from the first tick, so register it before the thread.
        flow.callbacks["preparation_allowed"] = self.preparation_allowed
        self._thread = None
        if self._owner:
            self._thread = threading.Thread(
                target=self._run, args=(interval,), name="application-pipeline", daemon=True
            )
            self._thread.start()

    def _load(self):
        if self.path.is_symlink():
            raise PortalDataError("pipeline_invalid", "自动流程记录不能使用符号链接。", 409)
        state = helper.read_json_object(self.path, "application pipeline")
        if (
            state.get("schemaVersion") != 1
            or state.get("protocol") != PROTOCOL
            or state.get("policy_version") != POLICY
            or state.get("control") not in {"running", "paused"}
            or not isinstance(state.get("items"), list)
            or state.get("revision") != digest({k: v for k, v in state.items() if k != "revision"})
        ):
            raise PortalDataError("pipeline_invalid", "自动流程记录尚不能核验。", 409)
        return state

    def _save(self, state):
        with self.flow.applications.write_lock():
            if self.path.is_symlink():
                raise PortalDataError("pipeline_invalid", "自动流程记录不能使用符号链接。", 409)
            self._assert_resume_cleared(state)
            state["revision"] = digest({k: v for k, v in state.items() if k != "revision"})
            helper.atomic_write_json(self.path, state)
            self._saved_control = state.get("control")

    def _assert_resume_cleared(self, state):
        """A save that resumes the queue must not keep the old wait fields."""
        previous = self._saved_control
        if previous is None:
            try:
                previous = helper.read_json_object(self.path, "application pipeline").get("control")
            except (OSError, ValueError, helper.StoreError):
                previous = None
        if previous == "paused" and state.get("control") == "running":
            leftover = [key for key in ("wait_reason", "resume_status") if key in state]
            if leftover:
                self._queue_assertion("resume_kept_wait_fields", state, leftover)

    def _queue_assertion(self, code, state, fields):
        """Record a queue-state inconsistency privately; never raises, never transitions."""
        row = {"code": code, "fields": fields, "state": queue_state(state), "at": time.time()}
        try:
            path = self.path.with_name(QUEUE_ASSERTION_LOG)
            if path.is_symlink():
                return
            descriptor = os.open(
                path, os.O_WRONLY | os.O_CREAT | os.O_APPEND | os.O_NOFOLLOW, 0o600
            )
            with os.fdopen(descriptor, "a", encoding="utf-8") as handle:
                handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
        except (OSError, TypeError, ValueError):
            pass

    def snapshot(self):
        with self._guard, self.flow.applications.write_lock():
            state = deepcopy(self._load())
            try:
                state["can_resume_matching"] = (
                    self._matching_failure_for_recovery(state) is not None
                    or self._language_wait_for_recovery(state) is not None
                    or self._material_wait_for_recovery(state)
                    or self._country_wait_for_recovery(state)
                )
            except (OSError, ValueError, TypeError, KeyError):
                state["can_resume_matching"] = False
            try:
                applications = (
                    {row["id"]: row for row in self.flow.applications.list_applications()}
                    if state["items"]
                    else {}
                )
            except (OSError, PortalDataError):
                # An unrelated malformed legacy note need not hide readable labels.
                applications = None
            for item in state["items"]:
                try:
                    application = (
                        applications.get(item["application_id"])
                        if applications is not None
                        else self.flow.applications.get_application(item["application_id"])
                    )
                    if application is not None:
                        item.update(
                            company=application["company"], role_title=application["role_title"]
                        )
                except PortalDataError:
                    pass
            try:
                retained_recommendations = {
                    item.get("recommendation_id") for item in state["items"]
                } | set(state.get("closed_postings", []))
                recommendations = self.intake.snapshot().get("recommendations", [])
                state["pending_recommendations"] = [
                    row
                    for row in recommendations
                    if row["id"] != state.get("current_recommendation_id")
                    and row["id"] not in retained_recommendations
                ]
            except (OSError, ValueError, TypeError, KeyError, PortalDataError, helper.StoreError):
                recommendations = []
                state["pending_recommendations"] = []
                state["mail_intake_error"] = "intake_unavailable"
            # A job skipped before it had an application (no full JD, a source
            # conflict) is labelled from its recommendation, else its source host.
            by_id = {row.get("id"): row for row in recommendations if isinstance(row, dict)}
            for item in state["items"]:
                row = by_id.get(item.get("recommendation_id"))
                if item.get("company") or row is None:
                    continue
                item.update(
                    company=row.get("company") or "", role_title=row.get("role_title") or ""
                )
                url = row.get("jd_source_url") or row.get("url") or row.get("mail_url") or ""
                item["source_host"] = (urlsplit(url).hostname or "") if isinstance(url, str) else ""
            return state | {
                "notice": self._notice(state),
                "enabled": self._owner and not self._closed.is_set() and not self._runtime_error,
                "runtime_error": self._runtime_error,
                "current_cancellation": next(
                    (
                        deepcopy(row)
                        for row in reversed(state.get("cancellations", []))
                        if state.get("active_task_id") == row["task_id"]
                        or state.get("active_task_id") is None
                        and not state.get("id")
                        and not state["items"]
                    ),
                    None,
                ),
            }

    @contextmanager
    def manual_entry(self, action, payload=None):
        """Check Flow at its locked mutation; keep intake admission synchronous."""
        if action == "flow:refresh-match":
            with self.flow.applications.write_lock():
                state = self._load()
                entry = None
                if (state.get("id") or state["items"]) and isinstance(payload, dict):
                    entry = {
                        "pipeline_id": state.get("id"),
                        "controller": state.get("controller"),
                        "task_id": payload.get("task_id"),
                        "request_id": payload.get("request_id"),
                        "task_revision": payload.get("task_revision"),
                        "serial": self._preparation_serial,
                        "refresh": None,
                    }
            token = self._refresh_entry.set(entry)
            try:
                with pipeline_http_entry(
                    self.flow,
                    lambda: self._check_material_branch_entry(payload, execution=True),
                ):
                    yield
            finally:
                self._refresh_entry.reset(token)
            return
        if action in {
            "flow:start-cover-letter",
            "flow:retry-material-consistency",
            "flow:recheck-cover-letter",
            "flow:recheck-material-consistency",
            "flow:recheck-resume-author",
        }:
            with pipeline_http_entry(
                self.flow,
                lambda: self._check_material_branch_entry(
                    payload,
                    execution=action
                    in {
                        "flow:start-cover-letter",
                        "flow:retry-material-consistency",
                    },
                ),
            ):
                yield
            return
        restricted = action in {
            "flow:create",
            "flow:import-latex",
            "flow:start",
            "flow:export-pdf",
            "flow:prepare-worker",
            "flow:cancel",
            "recommendations:select",
            "recommendations:acquire",
            "recommendations:refresh",
            "recommendations:continue",
        } or (
            action == "flow:worker-action"
            and isinstance(payload, dict)
            and payload.get("operation") in {"resume", "continue-current", "recheck"}
        )
        if not restricted:
            yield
            return
        if action.startswith("flow:"):
            with pipeline_http_entry(self.flow, self._check_manual_entry):
                yield
            return
        with self._guard, self.flow.applications.write_lock():
            self._check_manual_entry()
            yield

    def _check_manual_entry(self):
        # The caller holds the application lock. Never take _guard here: Flow
        # calls this while mutating and Pipeline already uses _guard -> app.
        if not self._owner or self._closed.is_set() or self._runtime_error:
            raise PortalDataError("pipeline_unavailable", "自动流程暂不可用，原任务保留。", 409)
        state = self._load()
        if state.get("id") or state["items"]:
            raise PortalDataError(
                "pipeline_entry_required",
                "请通过自动申请队列接纳岗位，并使用当前岗位继续。原任务与页面保留。",
                409,
            )

    def preparation_allowed(self, task_id, *, refresh=None):
        """Read preparation authority; Flow may already hold the application lock."""
        if not isinstance(task_id, str) or not task_id:
            return False
        try:
            with self.flow.applications.write_lock():
                if not self._owner or self._closed.is_set() or self._runtime_error:
                    return False
                state = self._load()
                if not state.get("id") and not state["items"] and not state.get("active_task_id"):
                    return True
                if (
                    refresh is None
                    and state.get("active_task_id") is None
                    and state["control"] == "running"
                    and state["status"] == "matching"
                ):
                    item = self._matching_item(state)
                    return bool(
                        item and item["status"] == "matching" and item.get("task_id") == task_id
                    )
                if state.get("active_task_id") != task_id:
                    return False
                if refresh is not None:
                    return state["control"] == "paused" and self._paused_refresh_allowed(
                        state, task_id, refresh
                    )
                return state["control"] == "running"
        except (PortalDataError, OSError, ValueError):
            return False

    def _paused_refresh_allowed(self, state, task_id, refresh):
        entry = self._refresh_entry.get()
        if (
            entry is None
            or not isinstance(refresh, tuple)
            or len(refresh) != 2
            or not isinstance(refresh[0], str)
            or refresh[0] != entry["request_id"]
            or not isinstance(refresh[1], str)
            or not refresh[1]
            or entry["serial"] != self._preparation_serial
            or entry["pipeline_id"] != state.get("id")
            or entry["controller"] != state.get("controller")
            or entry["task_id"] != task_id
            or not isinstance(entry["task_revision"], str)
            or not entry["task_revision"]
        ):
            return False
        if entry["refresh"] is None:
            entry["refresh"] = refresh
        return refresh == entry["refresh"]

    def _check_material_branch_entry(self, payload, *, execution=False):
        # Flow invokes this while holding the application lock. Do not acquire
        # _guard in the inverse order used by the running Pipeline.
        if not self._owner or self._closed.is_set() or self._runtime_error:
            raise PortalDataError("pipeline_unavailable", "自动流程暂不可用，原任务保留。", 409)
        state = self._load()
        if not state.get("id") and not state["items"]:
            return
        if (
            not isinstance(payload, dict)
            or not state.get("active_task_id")
            or payload.get("task_id") != state["active_task_id"]
            or state["control"] != "paused"
        ):
            raise PortalDataError(
                "pipeline_current_material_required",
                "请暂停当前岗位后仅恢复本岗材料；其他岗位保持顺序等待。",
                409,
            )
        if execution:
            require_no_other_match_refresh(self.flow, payload["task_id"])

    def flow_control(self, action, payload):
        """Route a current-job Flow control through the named Pipeline controls.

        Material edits on a bound current job first confirm the Worker stop. Returns
        None when the request is not a Pipeline control and stays with Flow.
        """
        if action in MATERIAL_EDIT_ACTIONS:
            # A current Worker batch first confirms its stop; preparation edits pass through.
            state = self.snapshot()
            if (
                isinstance(payload, dict)
                and state.get("worker_batch_id")
                and state.get("active_task_id") == payload.get("task_id")
            ):
                # Routes without a request id use their exact payload, so a retry is the same edit.
                gate = self.begin_material_edit(
                    payload["task_id"],
                    payload.get("task_revision"),
                    request_id=payload.get("request_id") or "material-edit-" + digest(payload)[:32],
                )
                if gate["edit_gate"] != "ready":
                    raise PortalDataError(
                        "material_edit_stopping",
                        MATERIAL_EDIT_STOPPING[gate["edit_gate_reason"]],
                        409,
                    )
            return None
        if action != "worker-action":
            return None
        operation, options = payload.get("operation"), payload.get("payload")
        if (
            set(payload) != {"task_id", "task_revision", "operation", "payload"}
            or operation not in {"pause", "skip-current", "select-current", "observe-result"}
            or not isinstance(options, dict)
        ):
            return None
        state = self.snapshot()
        current = state.get("active_task_id") == payload["task_id"]
        if operation == "pause":
            # A pause outside a usable Pipeline still reaches the Worker directly.
            if not (state["enabled"] and current):
                return None
            result = self.pause()
        elif not (state.get("id") or state["items"]):
            return None
        elif operation == "select-current":
            application_id = self.flow.task_snapshot(payload["task_id"])["application_id"]
            result = self.return_to(application_id, request_id=options.get("request_id"))
        elif not current:
            raise PortalDataError("current_job_changed", "当前岗位已变化。", 409)
        elif operation == "skip-current":
            result = self.skip_current(request_id=options.get("request_id"))
        else:
            result = self.observe_result(request_id=options.get("request_id"))
        return self.flow.task_snapshot(payload["task_id"]) | {"pipeline": result}

    @contextmanager
    def _control(self):
        with self._guard, self.flow.applications.write_lock():
            if not self._owner or self._closed.is_set() or self._runtime_error:
                raise PortalDataError("pipeline_unavailable", "自动流程暂不可用。", 409)
            yield self._load()

    @staticmethod
    def _request_id(request_id):
        if not isinstance(request_id, str) or not 1 <= len(request_id) <= 100:
            raise PortalDataError("pipeline_request_invalid", "自动流程请求标识无效。")

    def admit(self, payload):
        """Admit one recommendation or application into the sequential queue."""
        with self._control() as state:
            return self._admit(state, payload)

    def pause(self):
        """Pause the Pipeline and its own Worker; materials and the original page stay."""
        with self._control() as state:
            self._preparation_serial += 1
            self._pause_owned_worker(state)
            if state["control"] == "running":
                state["resume_status"] = state["status"]
                self._stop(state, "paused", "自动流程已暂停，已有资料与原页保留。")
            return self.snapshot()

    def capture_mail(self, *, request_id):
        """Collect recommendation mail only; no job work starts."""
        with self._control() as state:
            self._request_id(request_id)
            return self._capture_mail(state, request_id)

    def continue_current(self, *, request_id, **reclaim):
        """One Continue for the current job; unknown results still wait.

        ``reclaim=True`` with ``handoff_source`` is the user's confirmation that a page
        handed to them may return to the automatic layer; it runs the Worker's own
        recheck before this Continue (queue mode had no other way back, 2026-11-03).
        """
        return self._current("continue", {"request_id": request_id, **reclaim})

    def skip_current(self, *, request_id):
        """Retain the current job and its page, then select the next one."""
        return self._current("skip", {"request_id": request_id})

    def return_to(self, application_id, *, request_id):
        """Restore one skipped job with its original task and page."""
        return self._current("return", {"request_id": request_id, "application_id": application_id})

    def observe_result(self, *, request_id):
        """Read the original page's submission result without writing to it."""
        return self._current("observe-result", {"request_id": request_id})

    def begin_material_edit(self, task_id, task_revision, *, request_id):
        """Stop the current job's writers; Flow saves an edit only after a confirmed stop."""
        with self._control() as state:
            self._request_id(request_id)
            gate = state.get("material_edit_gate") or {}
            task = self._task(state) if state.get("active_task_id") == task_id else None
            if task is None or task["revision"] != task_revision:
                raise PortalDataError(
                    "current_job_changed", "当前岗位已变化，原页与材料保留。", 409
                )
            repeat = (
                gate.get("request_id") == request_id
                and gate["task_id"] == task_id
                and gate["task_revision"] == task_revision
            )
            if not repeat:
                self._preparation_serial += 1
                self._pause_owned_worker(state)
                if state["control"] == "running":
                    state["resume_status"] = state["status"]
                    self._stop(state, "paused", "已暂停当前岗位以修改材料，原页与材料保留。")
            current, job, reason = self._edit_stop(state, task)
            if reason:
                if repeat:
                    # A confirmed stop that no longer holds is not reused.
                    del state["material_edit_gate"]
                    self._save(state)
                return {"edit_gate": "stopping", "edit_gate_reason": reason}
            if repeat:
                return {"edit_gate": "ready"}
            state["material_edit_gate"] = {
                "request_id": request_id,
                "task_id": task_id,
                "task_revision": task_revision,
                "batch_id": current["batch_id"],
                "run_id": (current.get("runtime") or {}).get("id"),
                "page_id": (job.get("page_observation") or {}).get("page_id"),
                "confirmed_at": time.time(),
            }
            self._save(state)
            return {"edit_gate": "ready"}

    def _edit_stop(self, state, task):
        """Read the owned Worker; a reason means its writers have not confirmed a stop."""
        from .application_worker import assistance_stop_pending

        reader = (
            getattr(self.flow, "callbacks", {}).get("bound_worker_state") or self.worker.snapshot
        )
        current = reader()
        job = next(
            (
                row
                for row in current.get("jobs", [])
                if row["application_id"] == task["application_id"]
            ),
            None,
        )
        if job is None or current.get("batch_id") != state.get("worker_batch_id"):
            raise PortalDataError("current_job_changed", "当前岗位已变化，原页与材料保留。", 409)
        reason = (
            "worker_running"
            if current.get("control") != "paused"
            else "assistance_stopping"
            if assistance_stop_pending(job)
            else "pending_intent"
            if job.get("intent")
            else "continuation_pending"
            if (job.get("continuation") or {}).get("status") == "pending"
            else None
        )
        return current, job, reason

    def _current(self, action, payload):
        with self._control() as state:
            if action == "continue":
                # One Continue consumes the edit stop; its journal path stays unchanged.
                state.pop("material_edit_gate", None)
            return self._current_request(state, action, payload)

    def start(self, *, request_id):
        """Start the email cycle once, or resume the current job's retained wait."""
        with self._control() as state:
            self._request_id(request_id)
            if any(row["request_id"] == request_id for row in state.get("history", [])):
                return self.snapshot()
            if state["id"]:
                if request_id == state["request_id"]:
                    return self.snapshot()
                if any(
                    row.get("request_id") == request_id
                    for row in state.get("matching_recoveries", [])
                ):
                    return self.snapshot()
                require_no_other_match_refresh(self.flow, state.get("active_task_id"))
                if self._country_wait_for_recovery(state):
                    self._preparation_serial += 1
                    task = self._task(state)
                    application = self.flow.applications.get_application(task["application_id"])
                    resume = "generating_resume"
                    if (
                        application_country(application.get("location")) is not None
                        and job_input_revision(application) != task["job_binding"]
                    ):
                        task = self.flow.update_inputs(
                            task["id"], task["revision"], application["revision"]
                        )
                        self.flow.prepare(task["id"], task["revision"], analysis_only=True)
                        item = next(
                            row for row in state["items"] if row.get("task_id") == task["id"]
                        )
                        item.update(status="matching", score=None, reason="")
                        resume = "matching"
                    state.setdefault("matching_recoveries", []).append(
                        {
                            "request_id": request_id,
                            "at": time.time(),
                            "task_id": state["active_task_id"],
                            "reason": "application_country_required",
                        }
                    )
                    state.pop("resume_status", None)
                    state.pop("wait_reason", None)
                    state.update(control="running", status=resume, notification=None)
                    self._save(state)
                    return self.snapshot()
                if self._material_wait_for_recovery(state):
                    self._preparation_serial += 1
                    resume = "generating_resume"
                    if state.get("wait_reason") == "material_facts_required":
                        task = self._task(state)
                        application = self.flow.applications.get_application(task["application_id"])
                        task = self.flow.update_inputs(
                            task["id"], task["revision"], application["revision"]
                        )
                        if task.get("analysis_id") is None:
                            self.flow.prepare(task["id"], task["revision"], analysis_only=True)
                            item = next(
                                row for row in state["items"] if row.get("task_id") == task["id"]
                            )
                            item.update(status="matching", score=None, reason="")
                            resume = "matching"
                    state.setdefault("matching_recoveries", []).append(
                        {
                            "request_id": request_id,
                            "at": time.time(),
                            "task_id": state["active_task_id"],
                            "reason": state["wait_reason"],
                        }
                    )
                    state.pop("resume_status", None)
                    state.pop("wait_reason", None)
                    state.update(control="running", status=resume, notification=None)
                    self._save(state)
                    return self.snapshot()
                waiting = self._language_wait_for_recovery(state)
                if waiting is not None:
                    self._preparation_serial += 1
                    waiting.update(status="pending", reason="")
                    waiting.pop("reason_code", None)
                    state.setdefault("matching_recoveries", []).append(
                        {
                            "request_id": request_id,
                            "at": time.time(),
                            "application_id": waiting["application_id"],
                            "reason": "language_information_required",
                        }
                    )
                    state.pop("resume_status", None)
                    state.update(control="running", status="matching", notification=None)
                    self._save(state)
                    return self.snapshot()
                if self._recover_known_matching_failure(state, request_id):
                    self._preparation_serial += 1
                    return self.snapshot()
                if state["status"] == "paused" and state.get("resume_status"):
                    self._preparation_serial += 1
                    if state["resume_status"] in {
                        "filling",
                        "needs_input",
                        "preparing",
                        "starting_worker",
                        "admitting_worker",
                    }:
                        self._stop(
                            state, "needs_recheck", "原填写页面已暂停，请先核验；不会自动重放。"
                        )
                        return self.snapshot()
                    state.update(
                        control="running", status=state.pop("resume_status"), notification=None
                    )
                    self._save(state)
                    return self.snapshot()
                if state["status"] not in {
                    "no_matches",
                    "expired",
                    "interrupted",
                    "blocked",
                } or not self._can_restart(state):
                    raise PortalDataError(
                        "pipeline_exists", "原自动流程仍有记录，请先核验其进度。", 409
                    )
                history = state.get("history", [])
                archive = self.path.parent / "pipeline-history" / f"{state['id']}.json"
                if archive.is_symlink() or archive.parent.is_symlink():
                    raise PortalDataError("pipeline_invalid", "历史流程目录不能使用符号链接。", 409)
                helper.atomic_write_json(
                    archive, {key: value for key, value in state.items() if key != "history"}
                )
                history.append(
                    {
                        "id": state["id"],
                        "request_id": state["request_id"],
                        "status": state["status"],
                        "path": str(archive.relative_to(self.path.parent)),
                    }
                )
                state = {
                    "schemaVersion": 1,
                    "protocol": PROTOCOL,
                    "policy_version": POLICY,
                    "intake_run_id": None,
                    "items": [row for row in state["items"] if row["status"] == "admitted"],
                    "active_task_id": None,
                    "notification": None,
                    "transmission_authorization": None,
                    "mail_capture_requests": state.get("mail_capture_requests", []),
                    "admission_requests": state.get("admission_requests", []),
                    "history": history,
                }
            self._preparation_serial += 1
            state.update(
                id=uuid4().hex,
                request_id=request_id,
                control="running",
                status="selecting_job"
                if any(row["status"] == "admitted" for row in state["items"])
                else "reading_email",
                controller=uuid4().hex,
                started_at=time.time(),
                queue_mode=hasattr(self.intake, "store"),
                current_recommendation_id=None,
                mail_poll_at=0,
                authorization={
                    "id": uuid4().hex,
                    "verified_by": "user",
                    "scope": "this_email_cycle",
                    "existing_facts": True,
                    "generated_pdf": True,
                    "final_submit": "manual",
                    "at": time.time(),
                },
            )
            self._save(state)
            return self.snapshot()

    def complete_material_update(self, update_id):
        """Clear only this completed update's own wait pointers after Flow adoption."""
        from .application_bound_materials import failure, read_commit_journal

        with self._guard, self.flow.applications.write_lock():
            state = self._load()
            journal = read_commit_journal(self.flow.root, update_id)
            if (
                not self._owner
                or self._closed.is_set()
                or self._runtime_error
                or state["control"] != "running"
                or state.get("active_task_id") != journal["task_id"]
                or state.get("worker_batch_id") != journal["batch_id"]
                or state.get("material_update_id") not in {None, update_id}
                or self.flow.material_update_progress(journal["task_id"], update_id)["status"]
                != "complete"
            ):
                raise failure("bound_material_journal_conflict")
            if state.get("material_update_id") == update_id:
                state.pop("material_update_id", None)
                state.pop("material_update_continue_request_id", None)
                state.pop("wait_reason", None)
                self._save(state)
            return deepcopy(state)

    def resume_material_commit(self, update_id, request_id):
        """Project an accepted Continue's local recovery context without saving it."""
        from .application_bound_materials import failure

        with self._guard, self.flow.applications.write_lock():
            if not isinstance(request_id, str) or not request_id:
                raise failure("bound_material_journal_conflict")
            state, _ = self._checked_material_authorization(update_id, resume_request_id=request_id)
            state.update(control="running", status="continuing_worker", notification=None)
            return deepcopy(state)

    def validate_material_authorization(self, update_id, *, resume_request_id=None):
        """Check the existing local authorization participant without saving it."""
        with self._guard, self.flow.applications.write_lock():
            self._checked_material_authorization(update_id, resume_request_id=resume_request_id)
            return {"material_update_id": update_id, "status": "ready"}

    def commit_material_authorization(self, update_id, *, resume_request_id=None):
        """Adopt only this Pipeline's exact retained old/new authorization."""
        with self._guard, self.flow.applications.write_lock():
            state, journal = self._checked_material_authorization(
                update_id, resume_request_id=resume_request_id
            )
            changed = False
            if digest(state.get("transmission_authorization")) != digest(journal["new_receipt"]):
                state.setdefault("transmission_authorization_history", []).append(
                    deepcopy(journal["old_receipt"])
                )
                state["transmission_authorization"] = deepcopy(journal["new_receipt"])
                changed = True
            if state["control"] != "running":
                state.update(control="running", status="continuing_worker", notification=None)
                changed = True
            if changed:
                self._save(state)
            return deepcopy(state)

    def _checked_material_authorization(self, update_id, *, resume_request_id=None):
        from .application_bound_materials import failure, read_commit_journal

        state = self._load()
        journal = read_commit_journal(self.flow.root, update_id)
        old, new = journal["old_receipt"], journal["new_receipt"]
        grant = state.get("authorization") or {}
        latest = (state.get("current_requests") or [{}])[-1]
        recovery = (
            resume_request_id is not None
            and latest.get("request_id") == resume_request_id
            and latest.get("action") == "continue"
            and latest.get("status") == "dispatching"
        )
        if (
            not self._owner
            or self._closed.is_set()
            or self._runtime_error
            or resume_request_id is not None
            and not recovery
            or state["control"] != "running"
            and not recovery
            or state.get("active_task_id") != journal["task_id"]
            or state.get("worker_batch_id") != journal["batch_id"]
            or state.get("material_update_id") != update_id
            or digest(state.get("transmission_authorization")) not in {digest(old), digest(new)}
            or digest(
                {
                    key: value
                    for key, value in old.items()
                    if key not in {"inputs", "resume_id", "resume_sha256"}
                }
            )
            != digest(
                {
                    key: value
                    for key, value in new.items()
                    if key not in {"inputs", "resume_id", "resume_sha256"}
                }
            )
            or new.get("pipeline_id") != state.get("id")
            or new.get("task_id") != journal["task_id"]
            or new.get("application_id") != journal["application_id"]
            or new.get("intake_run_id") != state.get("intake_run_id")
            or new.get("policy_version") != POLICY
            or new.get("authorization_id") != grant.get("id")
            or grant.get("verified_by") != "user"
            or grant.get("scope") != "this_email_cycle"
            or grant.get("existing_facts") is not True
            or grant.get("generated_pdf") is not True
            or grant.get("final_submit") != "manual"
            or any(
                new.get(key) != journal["new"].get(key)
                for key in ("inputs", "resume_id", "resume_sha256")
            )
        ):
            raise failure("bound_material_journal_conflict")
        return state, journal

    def cancel_current(self, task_id=None, task_revision=None, *, request_id):
        """Cancel preparation and execution, retaining each owner's actual result."""
        if (
            not isinstance(request_id, str)
            or not 1 <= len(request_id) <= 100
            or (task_id is None) != (task_revision is None)
            or task_id is not None
            and (
                not isinstance(task_id, str)
                or not task_id
                or not isinstance(task_revision, str)
                or not task_revision
            )
        ):
            raise PortalDataError("pipeline_request_invalid", "取消请求标识或任务版本无效。", 409)
        with self._guard:
            with self.flow.applications.write_lock():
                if not self._owner or self._closed.is_set() or self._runtime_error:
                    raise PortalDataError("pipeline_unavailable", "自动流程暂不可用。", 409)
                state = self._load()
                identifier = task_id or state.get("active_task_id")
                if not identifier or state.get("active_task_id") not in {None, identifier}:
                    raise PortalDataError(
                        "pipeline_current_changed", "当前岗位已变化，原记录保留。", 409
                    )
                if state.get("active_task_id") is None and (
                    state.get("id") or state["items"] or task_id is None
                ):
                    raise PortalDataError(
                        "pipeline_entry_required"
                        if task_id is not None and (state.get("id") or state["items"])
                        else "pipeline_current_missing",
                        "当前没有选中的岗位，请通过自动申请队列操作。",
                        409,
                    )
                task = self.flow.task_snapshot(identifier)
                receipt = next(
                    (
                        row
                        for row in state.get("cancellations", [])
                        if row["request_id"] == request_id
                    ),
                    None,
                )
                if receipt is not None:
                    if receipt["task_id"] != identifier or (
                        task_revision is not None and task_revision != receipt["task_revision"]
                    ):
                        raise PortalDataError(
                            "pipeline_request_invalid", "取消请求已用于其他任务版本。", 409
                        )
                    if receipt["status"] == "complete":
                        return self.snapshot()
                else:
                    if task_revision is not None and task_revision != task["revision"]:
                        raise PortalDataError(
                            "flow_task_changed", "任务版本已变化，请保留原记录。", 409
                        )
                    reference = task.get("worker_ref")
                    if reference or task.get("worker_preparation", {}).get("status") == "pending":
                        try:
                            execution = self.worker.snapshot()
                        except (PortalDataError, OSError, ValueError):
                            execution = {}
                        batch_id = reference["batch_id"] if reference else execution.get("batch_id")
                        reference = {
                            "batch_id": batch_id,
                            "run_id": (execution.get("runtime") or {}).get("id")
                            if execution.get("batch_id") == batch_id
                            else None,
                        }
                    receipt = {
                        "request_id": request_id,
                        "task_id": identifier,
                        "task_revision": task["revision"],
                        "application_id": task["application_id"],
                        "worker_ref": reference,
                        "worker_status": "pending" if reference else "not_started",
                        "preparation_status": "pending",
                        "status": "pending",
                        "at": time.time(),
                    }
                    state.setdefault("cancellations", []).append(receipt)
                self._preparation_serial += 1
                state.update(control="paused", status="cancelling")
                self._save(state)

            reference = receipt["worker_ref"]
            progress = None
            if reference:
                try:
                    progress = self.worker.cancellation_progress(
                        receipt["application_id"],
                        expected_batch_id=reference["batch_id"],
                        expected_run_id=reference["run_id"],
                        expected_task_id=receipt["task_id"],
                    )
                    if progress["status"] == "active":
                        self.worker.cancel_execution(
                            receipt["application_id"],
                            expected_batch_id=reference["batch_id"],
                            expected_run_id=reference["run_id"],
                            expected_task_id=receipt["task_id"],
                        )
                        progress = self.worker.cancellation_progress(
                            receipt["application_id"],
                            expected_batch_id=reference["batch_id"],
                            expected_run_id=reference["run_id"],
                            expected_task_id=receipt["task_id"],
                        )
                    receipt["worker_status"] = progress["status"]
                    receipt.pop("worker_error", None)
                except (PortalDataError, OSError, ValueError) as error:
                    progress = None
                    receipt.update(
                        worker_status="unknown",
                        worker_error=getattr(error, "code", type(error).__name__),
                    )
            try:
                task = self.flow.task_snapshot(identifier)
                if task["status"] != "cancelled" or progress is not None:
                    self.flow.cancel_preparation(
                        identifier,
                        task["revision"],
                        **({"execution_cancellation": progress} if progress is not None else {}),
                    )
                receipt["preparation_status"] = "cancelled"
                receipt.pop("preparation_error", None)
            except (PortalDataError, OSError, ValueError) as error:
                receipt.update(
                    preparation_status="unknown",
                    preparation_error=getattr(error, "code", type(error).__name__),
                )
            with self.flow.applications.write_lock():
                state = self._load()
                saved = next(
                    (
                        row
                        for row in state.get("cancellations", [])
                        if row["request_id"] == request_id and row["task_id"] == identifier
                    ),
                    None,
                )
                if saved is None:
                    raise PortalDataError(
                        "pipeline_cancellation_changed", "取消记录已变化，原结果保留。", 409
                    )
                saved.update(receipt)
                self._finish_cancellation(state, saved)
                return self.snapshot()

    def _finish_cancellation(self, state, receipt):
        complete = receipt["preparation_status"] == "cancelled" and receipt["worker_status"] in {
            "not_started",
            "stopped",
        }
        stopping = (
            receipt["preparation_status"] == "cancelled" and receipt["worker_status"] == "stopping"
        )
        receipt["status"] = "complete" if complete else "stopping" if stopping else "partial"
        if state.get("active_task_id") == receipt["task_id"] or (
            state.get("active_task_id") is None and not state.get("id") and not state["items"]
        ):
            state.update(
                control="paused",
                status="cancelled" if complete else "cancelling" if stopping else "needs_recheck",
            )
            self._notify(
                state,
                state["status"],
                "当前岗位已取消，原页面与历史保留。"
                if complete
                else "取消已请求；其余停止结果仍待核验，原页面与历史保留。",
            )
        self._save(state)

    def _reconcile_cancellation(self, state):
        if not state.get("cancellations"):
            return False
        with self.flow.applications.write_lock():
            latest = self._load()
            state.clear()
            state.update(latest)
            receipt = next(
                (
                    row
                    for row in reversed(state.get("cancellations", []))
                    if row["task_id"] == state.get("active_task_id")
                    or state.get("active_task_id") is None
                    and not state.get("id")
                    and not state["items"]
                ),
                None,
            )
            if receipt is None:
                return False
            if receipt["status"] == "complete":
                return True
            changed = False
            reference = receipt.get("worker_ref")
            if reference:
                try:
                    progress = self.worker.cancellation_progress(
                        receipt["application_id"],
                        expected_batch_id=reference["batch_id"],
                        expected_run_id=reference["run_id"],
                        expected_task_id=receipt["task_id"],
                    )
                    if receipt["worker_status"] != progress["status"]:
                        receipt["worker_status"] = progress["status"]
                        changed = True
                except (PortalDataError, OSError, ValueError):
                    if receipt["worker_status"] != "unknown":
                        receipt["worker_status"] = "unknown"
                        changed = True
            if (
                receipt["preparation_status"] != "cancelled"
                and self.flow.task_snapshot(receipt["task_id"])["status"] == "cancelled"
            ):
                receipt["preparation_status"] = "cancelled"
                changed = True
            if changed:
                self._finish_cancellation(state, receipt)
            return True

    def _admit(self, state, payload):
        """Retain explicit user selections in the existing queue; never switch work."""
        if not hasattr(self.intake, "store") or state.get("id") and not state.get("queue_mode"):
            raise PortalDataError(
                "pipeline_queue_unavailable", "原流程记录需先核验，尚不能接纳新岗位。", 409
            )
        if not isinstance(payload, dict):
            raise PortalDataError("pipeline_request_invalid", "请选择有效岗位。", 409)
        target = "application" if "application_id" in payload else "recommendation"
        expected = {"request_id", f"{target}_id", f"{target}_revision"}
        if set(payload) != expected or any(
            not isinstance(value, str) or not 1 <= len(value) <= 100 for value in payload.values()
        ):
            raise PortalDataError("pipeline_request_invalid", "请选择有效岗位版本。", 409)
        requests = state.setdefault("admission_requests", [])
        previous = next(
            (row for row in requests if row["request_id"] == payload["request_id"]), None
        )
        if previous is not None:
            if previous != payload:
                raise PortalDataError("pipeline_request_invalid", "请求标识已用于其他岗位。", 409)
            return self.snapshot()
        identifier = payload[f"{target}_id"]
        recommendations = self.intake.snapshot()["recommendations"]
        if target == "application":
            application = self.flow.applications.get_application(identifier)
            revision = application["revision"]
            canonical = next(
                (
                    row
                    for row in recommendations
                    if (row.get("existing_application") or {}).get("id") == identifier
                ),
                None,
            )
            recommendation_id = canonical["id"] if canonical else f"application:{identifier}"
            existing = next(
                (
                    row
                    for row in state["items"]
                    if row.get("application_id") == identifier
                    or row.get("recommendation_id") == recommendation_id
                ),
                None,
            )
        else:
            recommendation = next(
                (row for row in recommendations if row["id"] == identifier),
                None,
            )
            if recommendation is None:
                raise PortalDataError("pipeline_source_invalid", "找不到此岗位来源。", 409)
            revision = recommendation["revision"]
            recommendation_id = identifier
            existing = next(
                (
                    row
                    for row in state["items"]
                    if row.get("recommendation_id") == identifier
                    or row.get("application_id") is not None
                    and row.get("application_id")
                    == (recommendation.get("existing_application") or {}).get("id")
                ),
                None,
            )
        if revision != payload[f"{target}_revision"]:
            raise PortalDataError(
                "pipeline_inputs_changed", "岗位版本已变化，请读取最新状态。", 409
            )
        if existing is None:
            # Materialize only ordering records. JD acquisition and Flow creation
            # still happen when this record becomes the one current job.
            before_target = recommendations
            if not recommendation_id.startswith("application:"):
                before_target = recommendations[
                    : next(
                        i for i, row in enumerate(recommendations) if row["id"] == recommendation_id
                    )
                ]
            seen = {row.get("recommendation_id") for row in state["items"]}
            seen |= set(state.get("closed_postings", []))
            applications = {
                row.get("application_id") for row in state["items"] if row.get("application_id")
            }
            for row in before_target:
                if (
                    row["id"] in seen
                    or (row.get("existing_application") or {}).get("id") in applications
                ):
                    continue
                state["items"].append(
                    {
                        "recommendation_id": row["id"],
                        "application_id": None,
                        "task_id": None,
                        "status": "admitted",
                        "score": None,
                    }
                )
                seen.add(row["id"])
            state["items"].append(
                {
                    "recommendation_id": recommendation_id,
                    "application_id": identifier
                    if recommendation_id.startswith("application:")
                    else None,
                    "task_id": None,
                    "status": "admitted",
                    "score": None,
                }
            )
        requests.append(deepcopy(payload))
        self._save(state)
        return self.snapshot()

    def redo_current(self, *, request_id):
        """Start the cancelled current job again as a new task; the old one stays history.

        Only after its cancel completed. Flow creates a new task for an application
        whose task was cancelled, so the job is analysed under current rules and its
        materials are prepared anew. Continue never revives a cancelled job.
        """
        with self._control() as state:
            self._request_id(request_id)
            requests = state.setdefault("current_requests", [])
            if any(row["request_id"] == request_id for row in requests):
                return self.snapshot()
            cancelled = next(
                (
                    row
                    for row in reversed(state.get("cancellations", []))
                    if state.get("active_task_id") is not None
                    and row["task_id"] == state["active_task_id"]
                ),
                None,
            )
            item = next(
                (
                    row
                    for row in state["items"]
                    if cancelled is not None and row.get("task_id") == cancelled["task_id"]
                ),
                None,
            )
            if cancelled is None or cancelled["status"] != "complete" or item is None:
                raise PortalDataError(
                    "pipeline_redo_unavailable", "只有已完成取消的当前岗位可以重做。", 409
                )
            for key in (
                "reason",
                "reason_code",
                "score_tier",
                "score_analysis_id",
                "score_decision",
                "analysis_attempt_id",
                "task_revision",
            ):
                item.pop(key, None)
            item.update(task_id=None, status="pending", score=None, fresh_job_brief=True)
            requests.append(
                {
                    "request_id": request_id,
                    "action": "redo",
                    "task_id": cancelled["task_id"],
                    "status": "complete",
                    "at": time.time(),
                }
            )
            for key in ("wait_reason", "resume_status"):
                state.pop(key, None)
            self._preparation_serial += 1
            state.update(
                active_task_id=None, control="running", status="matching", notification=None
            )
            self._save(state)
            return self.snapshot()

    def _current_request(self, state, action, payload):
        expected = {"request_id", "application_id"} if action == "return" else {"request_id"}
        if action == "continue" and isinstance(payload, dict) and "reclaim" in payload:
            expected = {"request_id", "reclaim", "handoff_source"}
        if (
            not state.get("queue_mode")
            or not isinstance(payload, dict)
            or set(payload) != expected
            or not isinstance(payload.get("request_id"), str)
            or not 1 <= len(payload["request_id"]) <= 100
            or "reclaim" in expected
            and (
                payload["reclaim"] is not True
                or not isinstance(payload["handoff_source"], str)
                or not 1 <= len(payload["handoff_source"].strip()) <= 1000
            )
        ):
            raise PortalDataError("pipeline_request_invalid", "请使用当前岗位操作。", 409)
        if action == "continue" and any(
            row["task_id"] == state.get("active_task_id") for row in state.get("cancellations", [])
        ):
            raise PortalDataError(
                "pipeline_current_cancelled", "当前岗位已请求取消，原页面与记录保留。", 409
            )
        requests = state.setdefault("current_requests", [])
        if any(row["request_id"] == payload["request_id"] for row in requests):
            return self.snapshot()
        if action == "continue":
            require_no_other_match_refresh(self.flow, state.get("active_task_id"))
        if action == "return":
            target = next(
                (
                    row
                    for row in state["items"]
                    if (
                        row.get("application_id") == payload["application_id"]
                        or row.get("recommendation_id") == payload["application_id"]
                    )
                    and row["status"] == "skipped"
                ),
                None,
            )
            if target is None or not target.get("pipeline_context"):
                raise PortalDataError("pipeline_return_unavailable", "找不到可返回的原岗位。", 409)
        elif state.get("current_recommendation_id") is None:
            resume = state.get("resume_status") if state["status"] == "paused" else state["status"]
            mail_wait = action == "continue" and self._mail_wait_for_recovery(state)
            if mail_wait:
                resume = "reading_email"
            if action == "continue" and resume in {
                "waiting_for_mail",
                "selecting_job",
                "reading_email",
            }:
                self._preparation_serial += 1
                requests.append(
                    {
                        "request_id": payload["request_id"],
                        "action": action,
                        "status": "complete",
                        "at": time.time(),
                    }
                )
                state.pop("resume_status", None)
                if mail_wait:
                    state.pop("wait_reason", None)
                state.update(control="running", status=resume, notification=None)
                self._save(state)
                return self.snapshot()
            raise PortalDataError("pipeline_current_missing", "当前没有选中的岗位。", 409)
        if action in {"continue", "skip", "return"}:
            self._preparation_serial += 1
        receipt = {
            "request_id": payload["request_id"],
            "action": action,
            "status": "dispatching",
            "at": time.time(),
        }
        requests.append(receipt)
        self._save(state)
        try:
            if action == "skip":
                self._leave_current(state, payload["request_id"])
            elif action == "return":
                if state.get("current_recommendation_id") is not None:
                    self._leave_current(state, payload["request_id"] + ":leave")
                context = deepcopy(target["pipeline_context"])
                state.update(context)
                state.update(
                    current_recommendation_id=target["recommendation_id"], control="paused"
                )
                target["status"] = target.pop("retained_status")
                if target.get("reason") == "low_match_score":
                    # Returning a low-score job is the user's decision to proceed.
                    target["score_decision"] = target.get("score_analysis_id")
                if state.get("worker_batch_id"):
                    task = self._task(state)
                    self.flow.worker_action(
                        task["id"],
                        task["revision"],
                        "select-current",
                        {"request_id": payload["request_id"]},
                    )
                self._save(state)
            elif action == "continue":
                if state.get("wait_reason") in {
                    "cover_letter_result_unknown",
                    "material_result_unknown",
                } and (
                    self._retry_unknown_writing(state, payload["request_id"])
                    and state.get("wait_reason") == "material_result_unknown"
                    and not state.get("worker_batch_id")
                ):
                    state.pop("wait_reason", None)
                    state.pop("resume_status", None)
                    state.update(control="running", status="generating_resume", notification=None)
                    receipt["status"] = "complete"
                    self._save(state)
                    return self.snapshot()
                if state.get("wait_reason") in {
                    "cover_letter_result_unknown",
                    "material_consistency_required",
                }:
                    if any(
                        self.flow.cover_letter_outcome(item["task_id"])["status"] == "needs_recheck"
                        or (
                            hasattr(self.flow, "material_consistency_outcome")
                            and self.flow.material_consistency_outcome(item["task_id"])["status"]
                            in {"conflict", "failed", "needs_recheck"}
                        )
                        for item in state["items"]
                        if item.get("task_id")
                    ):
                        self._stop(
                            state, "needs_recheck", "材料结果仍待核验或冲突未处理，请保留原回执。"
                        )
                        return self.snapshot()
                    state.pop("wait_reason", None)
                    resume = state.pop("cover_letter_resume_status", "generating_resume")
                    if not state.get("worker_batch_id"):
                        state.update(control="running", status=resume, notification=None)
                        receipt["status"] = "complete"
                        self._save(state)
                        return self.snapshot()
                if not state.get("worker_batch_id"):
                    receipt["status"] = "complete"
                    if state.get("wait_reason") == "score_approval":
                        # Continue on a score approval wait approves this analysis.
                        task = self._task(state)
                        item = next(
                            row for row in state["items"] if row.get("task_id") == task["id"]
                        )
                        item["score_decision"] = item.get("score_analysis_id")
                        state.pop("wait_reason", None)
                        state.pop("resume_status", None)
                        state.update(control="running", status="matching", notification=None)
                        self._save(state)
                        return self.snapshot()
                    if state.get("wait_reason") == "resume_author_input_required":
                        task = self._task(state)
                        progress = self.flow.progress(task["id"])
                        continuation = progress["continuation"]
                        if continuation is not None:
                            state["resume_author_retry"] = continuation | {
                                "request_id": payload["request_id"]
                            }
                        if progress["can_continue"]:
                            state.pop("wait_reason", None)
                            state.pop("resume_status", None)
                            state.update(
                                control="running", status="generating_resume", notification=None
                            )
                        self._save(state)
                        return self.snapshot()
                    if state.get("wait_reason") in {
                        "analysis_input_required",
                        "analysis_result_unknown",
                    }:
                        outcome = self.flow.analysis_outcome(state["active_task_id"])
                        # A known rejected output left nothing behind; this Continue is
                        # the user's explicit retry. Unknown results still never replay.
                        if outcome["status"] == "rejected" and not outcome["legacy_skippable"]:
                            task = self._task(state)
                            application = self.flow.applications.get_application(
                                task["application_id"]
                            )
                            # An App update changes the analysis configuration; the
                            # retry rebinds current inputs, archiving the rejection.
                            task = self.flow.update_inputs(
                                task["id"], task["revision"], application["revision"]
                            )
                            if task["stages"]["analysis"]["status"] == "failed":
                                self.flow.start(
                                    task["id"],
                                    task["revision"],
                                    "analysis",
                                    retry=True,
                                    _continuation_request_id=payload["request_id"],
                                )
                            else:
                                self.flow.prepare(
                                    task["id"],
                                    task["revision"],
                                    request_id=payload["request_id"],
                                    analysis_only=True,
                                )
                            outcome = self.flow.analysis_outcome(task["id"])
                        if outcome["status"] in {"ready", "running"}:
                            state.pop("wait_reason", None)
                            state.pop("resume_status", None)
                            state.update(control="running", status="matching", notification=None)
                        else:
                            state["wait_reason"] = (
                                "analysis_result_unknown"
                                if outcome["status"] == "unknown"
                                else "analysis_input_required"
                            )
                            self._stop(
                                state,
                                "needs_recheck"
                                if outcome["status"] == "unknown"
                                else "needs_input",
                                "当前岗位分析仍需处理或核验，保留原任务；不会自动重放。",
                            )
                        self._save(state)
                        return self.snapshot()
                    if state.get("wait_reason") == "precision_adjustment":
                        task = self._task(state)
                        item = next(
                            row for row in state["items"] if row.get("task_id") == task["id"]
                        )
                        if (
                            item.get("application_route") != "manual"
                            or task.get("worker_ref")
                            or task["status"]
                            not in {"draft_ready", "resume_ready", "materials_ready"}
                        ):
                            raise PortalDataError(
                                "pipeline_precision_unavailable",
                                "当前精准调整材料尚不能继续，请保留原稿并核验当前状态。",
                                409,
                            )
                        item["precision_adjustment"] = {
                            "request_id": payload["request_id"],
                            "task_id": task["id"],
                            "task_revision": task["revision"],
                            "draft_sha256": task.get("draft_sha256"),
                            "resume_sha256": task.get("resume_sha256"),
                            "at": time.time(),
                        }
                        state.pop("wait_reason", None)
                        state.pop("resume_status", None)
                        state.update(
                            control="running", status="generating_resume", notification=None
                        )
                        self._save(state)
                        return self.snapshot()
                    if (
                        self._material_wait_for_recovery(state)
                        or self._country_wait_for_recovery(state)
                        or self._language_wait_for_recovery(state) is not None
                        or self._matching_failure_for_recovery(state) is not None
                    ):
                        self._save(state)
                        return self.start(request_id=payload["request_id"])
                    if not state.get("active_task_id"):
                        if state["control"] == "paused" and state["status"] == "needs_input":
                            record = next(
                                (
                                    row
                                    for row in self.intake.snapshot()["recommendations"]
                                    if row["id"] == state["current_recommendation_id"]
                                ),
                                None,
                            )
                            if (
                                record
                                and record.get("acquisition_checkpoint") == "failed"
                                and (state.get("source_receipt") or {}).get("status")
                                not in {"dispatching", "needs_recheck"}
                            ):
                                state["source_receipt"] = {
                                    "recommendation_id": record["id"],
                                    "recommendation_revision": record["revision"],
                                    "status": "selected",
                                    "retry_request_id": payload["request_id"],
                                }
                        state.update(
                            control="running", status="acquiring_source", notification=None
                        )
                    elif state["status"] in {"matching", "generating_resume"}:
                        state.update(control="running", notification=None)
                    else:
                        self._save(state)
                        return self.start(request_id=payload["request_id"])
                    self._save(state)
                    return self.snapshot()
                task = self._task(state)
                from .application_worker import material_edit_pending

                # This Continue is explicit; a durable checkpoint lifts an old stop
                # before a material update reads the Worker (2026-10-31).
                if hasattr(self.worker, "lift_checkpoint_stop"):
                    self.worker.lift_checkpoint_stop()
                if state.get("material_update_id"):
                    from .application_bound_materials import recover_pending_commit

                    if recover_pending_commit(self, state, task, request_id=payload["request_id"]):
                        task = self._task(state)
                        receipt = next(
                            row
                            for row in state["current_requests"]
                            if row["request_id"] == payload["request_id"]
                        )
                current = self.worker.snapshot()
                current_job = next(
                    row
                    for row in current["jobs"]
                    if row["application_id"] == task["application_id"]
                )
                if material_edit_pending(current_job):
                    raise PortalDataError(
                        "material_edit_needs_recheck", "材料编辑尚未完成，请保留原稿核验。", 409
                    )
                if current_job.get("handed_off") and payload.get("reclaim") is True:
                    from .application_worker import manual_submission_unresolved

                    if manual_submission_unresolved(current_job):
                        raise PortalDataError(
                            "submission_result_unknown",
                            "人工提交结果仍未知，请保留原页继续观察；不会收回或重填。",
                            409,
                        )
                    # The Worker's own user-confirmed recheck: a confirmed submission,
                    # an unresolved action or a missing source still refuses it.
                    self.flow.worker_action(
                        task["id"],
                        task["revision"],
                        "recheck",
                        {
                            "reclaim": True,
                            "handoff_source": payload["handoff_source"],
                            "acknowledge": True,
                        },
                    )
                    task = self._task(state)
                    current_job = next(
                        row
                        for row in self.worker.snapshot()["jobs"]
                        if row["application_id"] == task["application_id"]
                    )
                if state.get("wait_reason") == "precision_adjustment":
                    item = next(row for row in state["items"] if row.get("task_id") == task["id"])
                    current = self.worker.snapshot()
                    job = next(
                        row
                        for row in current["jobs"]
                        if row["application_id"] == task["application_id"]
                    )
                    precision = job.get("precision_preparation") or {}
                    if (
                        item.get("application_route") != "manual"
                        or precision.get("status") != "ready"
                        or precision.get("task_id") != task["id"]
                        or precision.get("authorization_id") != state["authorization"]["id"]
                        or current["control"] != "paused"
                    ):
                        raise PortalDataError(
                            "pipeline_precision_unavailable", "精准材料或原页待核验。", 409
                        )
                    item["precision_adjustment"] = {
                        "request_id": payload["request_id"],
                        "task_id": task["id"],
                        "task_revision": task["revision"],
                        "draft_sha256": task.get("draft_sha256"),
                        "resume_sha256": task.get("resume_sha256"),
                        "at": time.time(),
                    }
                    state.pop("wait_reason", None)
                    self._save(state)
                if getattr(self.flow, "callbacks", {}).get("bound_material_candidate"):
                    from .application_bound_materials import begin as begin_material_update

                    if begin_material_update(self.flow, task["id"], payload["request_id"]):
                        task = self._task(state)
                        state.update(
                            control="running",
                            status="continuing_worker",
                            notification=None,
                            wait_reason="material_update",
                            material_update_id=task["material_update"]["id"],
                            material_update_continue_request_id=payload["request_id"],
                        )
                        receipt["status"] = "complete"
                        self._save(state)
                        return self.snapshot()
                    task = self._task(state)
                held = current_job.get("assistance") or {}
                if (
                    held.get("status") == "stopped"
                    and (held.get("stop") or {}).get("reason") == "native_turn_completed"
                    and "outcome" not in held
                    and "superseded" not in held
                    and current_job["status"] in {"queued", "filling"}
                ):
                    # A finished takeover outside a wait lost its outcome save. The
                    # Worker's own Continue lifts the stop and re-adopts that report;
                    # continue-current would wait for script writes that never return.
                    state.update(
                        control="running", status="filling", notification=None, last_heartbeat=0
                    )
                    self._save(state)
                    self.flow.worker_action(
                        task["id"], task["revision"], "resume", {"controller": state["controller"]}
                    )
                else:
                    state.update(control="running", status="continuing_worker", notification=None)
                    self._save(state)
                    request = {
                        "request_id": payload["request_id"],
                        "controller": state["controller"],
                    }
                    try:
                        self.flow.worker_action(
                            task["id"], task["revision"], "continue-current", request
                        )
                    except PortalDataError as error:
                        if error.code != "page_lost":
                            raise
                        # APP-13: the original page is gone; a new run opens a new one,
                        # at the job's corrected link when the user changed it.
                        task = self._rebind_job_url(state, task)
                        self.flow.worker_action(
                            task["id"], task["revision"], "reopen-current", request
                        )
                        state.update(status="filling", worker_runtime_id=None, last_heartbeat=0)
            else:
                if not state.get("worker_batch_id"):
                    raise PortalDataError(
                        "pipeline_result_unavailable", "当前岗位尚无原申请页。", 409
                    )
                task = self._task(state)
                self.flow.worker_action(
                    task["id"],
                    task["revision"],
                    "observe-result",
                    {"request_id": payload["request_id"]},
                )
                state.update(control="paused", status="observing_result")
        except (PortalDataError, OSError, ValueError, TypeError) as error:
            receipt = next(
                (
                    row
                    for row in state["current_requests"]
                    if row["request_id"] == payload["request_id"]
                ),
                receipt,
            )
            receipt.update(
                status="needs_recheck", error_code=getattr(error, "code", type(error).__name__)
            )
            if getattr(error, "location", None):
                receipt["error_location"] = error.location
            self._stop(state, "needs_recheck", str(error))
            raise
        receipt = next(
            (
                row
                for row in state["current_requests"]
                if row["request_id"] == payload["request_id"]
            ),
            receipt,
        )
        receipt["status"] = "complete"
        self._save(state)
        return self.snapshot()

    def _leave_current(self, state, request_id):
        item = next(
            (
                row
                for row in state["items"]
                if row.get("recommendation_id") == state["current_recommendation_id"]
            ),
            None,
        )
        if item is None:
            item = {
                "recommendation_id": state["current_recommendation_id"],
                "application_id": None,
                "task_id": None,
                "status": "source_wait",
                "score": None,
            }
            state["items"].append(item)
        keys = (
            "status",
            "active_task_id",
            "source_receipt",
            "transmission_authorization",
            "worker_batch_id",
            "worker_runtime_id",
            "resume_status",
            "wait_reason",
            "cover_letter_resume_status",
            "pending_optional_cover_letter",
            "notification",
        )
        item["pipeline_context"] = {key: deepcopy(state.get(key)) for key in keys}
        item["retained_status"] = item["status"]
        if state.get("active_task_id") and hasattr(self.flow, "cancel_cover_letter"):
            self.flow.cancel_cover_letter(state["active_task_id"])
        if state.get("worker_batch_id"):
            task = self._task(state)
            self.flow.worker_action(
                task["id"], task["revision"], "skip-current", {"request_id": request_id}
            )
        item["status"] = "skipped"
        for key in keys:
            state.pop(key, None)
        state.update(
            current_recommendation_id=None,
            active_task_id=None,
            transmission_authorization=None,
            notification=None,
            control="running",
            status="selecting_job",
        )
        self._save(state)

    def _capture_mail(self, state, request_id):
        captures = state.setdefault("mail_capture_requests", [])
        if any(row["request_id"] == request_id for row in captures):
            return self.snapshot()
        if state["status"] in {"reading_email", "starting_email"} or state.get("resume_status") in {
            "reading_email",
            "starting_email",
        }:
            raise PortalDataError(
                "mail_capture_busy", "原邮件读取结果尚待采用，请保留其进度。", 409
            )
        intake = self.intake.snapshot()
        if intake.get("status") == "running" and (
            intake.get("capture_only") is not True or intake.get("operation") == "source"
        ):
            raise PortalDataError("mail_capture_busy", "已有岗位读取正在进行，请保留其进度。", 409)
        receipt = {"request_id": request_id, "status": "dispatching", "at": time.time()}
        captures.append(receipt)
        self._save(state)
        try:
            observed = (
                intake
                if intake.get("status") == "running"
                else self.intake.refresh(capture_only=True)
            )
        except (OSError, ValueError, TypeError, PortalDataError) as error:
            receipt.update(
                status="needs_recheck", error_code=getattr(error, "code", type(error).__name__)
            )
            self._save(state)
            raise
        receipt.update(status="started", intake_run_id=observed.get("run_id"))
        self._save(state)
        return self.snapshot()

    def _matching_failure_for_recovery(self, state):
        """Read-only proof for continuing the same local matching cycle."""
        if (
            state.get("queue_mode")
            or state["status"] != "needs_recheck"
            or state["control"] != "paused"
            or state.get("active_task_id")
            or state.get("worker_batch_id")
            or state.get("transmission_authorization")
            or (state.get("notification") or {}).get("message")
            != "岗位已有其他阶段或未知结果，保留原任务。"
        ):
            return None
        matching = [row for row in state["items"] if row["status"] == "matching"]
        if len(matching) != 1 or not matching[0].get("task_id"):
            return None
        tasks = {task["id"]: task for task in self.flow.snapshot()["tasks"]}
        failed = tasks.get(matching[0]["task_id"], {})
        if not _known_analysis_failure(failed):
            return None
        for row in state["items"]:
            if row.get("task_id") is None:
                if row["status"] not in {"pending", "excluded"}:
                    return None
                continue
            task = tasks.get(row["task_id"], {})
            if (
                task.get("application_id") != row["application_id"]
                or any(
                    task.get(key) is not None
                    for key in (
                        "worker_ref",
                        "send_approval",
                        "worker_preparation",
                        "resume_id",
                        "resume_sha256",
                        "draft_id",
                        "draft_sha256",
                        "material_binding",
                        "material_acceptance",
                    )
                )
                or task.get("materials_confirmed") is True
                or any(
                    stage.get("status") in {"queued", "running", "needs_recheck"}
                    for stage in task.get("stages", {}).values()
                )
                or any(
                    value != {"status": "pending"}
                    for name, value in task.get("stages", {}).items()
                    if name != "analysis"
                )
                or any(
                    artifact.get("stage") != "analysis" for artifact in task.get("artifacts", [])
                )
                or task.get("status") == "analysis_ready"
                and adopted_analysis(task) is None
                or task.get("status") not in {"analysis_ready", "failed"}
                or task.get("status") == "failed"
                and not _known_analysis_failure(task)
            ):
                return None
        return failed if self._matching_source_retained(state) else None

    def _matching_source_retained(self, state):
        if state.get("queue_mode"):
            record = next(
                (
                    row
                    for row in self.intake.snapshot()["recommendations"]
                    if row["id"] == state.get("current_recommendation_id")
                ),
                None,
            )
            return bool(
                record
                and record.get("existing_application")
                and any(
                    row["application_id"] == record["existing_application"]["id"]
                    and row.get("recommendation_id") == record["id"]
                    for row in state["items"]
                )
            )
        run_id = state.get("intake_run_id")
        if not isinstance(run_id, str) or re.fullmatch(r"[a-f0-9]{32}", run_id) is None:
            return False
        try:
            identifiers = self.intake.source_delivery(run_id)["application_ids"]
        except (OSError, ValueError, TypeError, KeyError, PortalDataError, helper.StoreError):
            return False
        return identifiers == [row["application_id"] for row in state["items"]]

    def _language_wait_for_recovery(self, state):
        if (
            state["status"] != "needs_input"
            or state["control"] != "paused"
            or state.get("resume_status") != "matching"
            or state.get("active_task_id")
            or state.get("worker_batch_id")
            or state.get("transmission_authorization")
        ):
            return None
        waiting = [row for row in state["items"] if row["status"] == "needs_input"]
        if (
            len(waiting) != 1
            or waiting[0].get("task_id") is not None
            or waiting[0].get("reason_code") != "language_information_required"
            or not self._matching_source_retained(state)
        ):
            return None
        return waiting[0]

    def _recover_known_matching_failure(self, state, request_id):
        failed = self._matching_failure_for_recovery(state)
        if failed is None:
            return False
        state.setdefault("matching_recoveries", []).append(
            {
                "request_id": request_id,
                "at": time.time(),
                "failed_task_id": failed["id"],
                "task_revision": failed["revision"],
            }
        )
        state.update(control="running", status="matching", notification=None)
        self._save(state)
        return True

    def _mail_wait_for_recovery(self, state):
        marked_wait = (
            state.get("resume_status") == "reading_email"
            and state.get("wait_reason") == "mail_capture_incomplete"
        )
        legacy_wait = "resume_status" not in state and "wait_reason" not in state
        if (
            state["status"] != "needs_input"
            or state["control"] != "paused"
            or not state.get("id")
            or not state.get("queue_mode")
            or any(
                row.get("status") != "admitted" or row.get("task_id") is not None
                for row in state["items"]
            )
            or state.get("current_recommendation_id")
            or state.get("active_task_id")
            or state.get("worker_batch_id")
            or state.get("transmission_authorization")
            or state.get("source_receipt")
            or not (marked_wait or legacy_wait)
        ):
            return False
        intake = self.intake.snapshot()
        if intake.get("capture_only") is not True or intake.get("operation") not in {
            "mail",
            "continue",
            "mail_cleanup",
        }:
            return False
        run_id = state.get("intake_run_id")
        if not isinstance(run_id, str) or re.fullmatch(r"[a-f0-9]{32}", run_id) is None:
            return False
        if marked_wait:
            return True
        # Old bootstrap waits have no markers. Their retained request identifies
        # capture-only mail without relying on a notification or a later run ID.
        path = self.intake.root / "runs" / run_id / "request.json"
        if any(part.is_symlink() for part in (path, path.parent, path.parent.parent)):
            return False
        try:
            request = helper.read_json_object(path, "retained mail capture request")
        except (OSError, ValueError, TypeError, helper.StoreError):
            return False
        return (
            request.get("run_id") == run_id
            and request.get("capture_only") is True
            and request.get("operation") in {"mail", "continue", "mail_cleanup"}
        )

    def _country_wait_for_recovery(self, state):
        marked_wait = (
            state.get("resume_status") == "generating_resume"
            and state.get("wait_reason") == "application_country_required"
        )
        # Older completed-material waits predate both recovery markers.
        legacy_wait = "resume_status" not in state and "wait_reason" not in state
        if (
            state["status"] != "needs_input"
            or state["control"] != "paused"
            or not (marked_wait or legacy_wait)
            or not state.get("active_task_id")
            or state.get("worker_batch_id")
            or state.get("transmission_authorization")
        ):
            return False
        task = self._task(state)
        return task["status"] in {"resume_ready", "materials_ready"} and not task.get("worker_ref")

    def _retry_unknown_writing(self, state, request_id):
        """Re-run résumé or letter writing calls with unknown results (approved 2026-10-31).

        Writing only drafts text; the unknown attempts stay in the task history.
        """
        task, retried = self._task(state), False
        resume = task["stages"].get("resume", {})
        # A refused assembly keeps its finished fragments; the retry re-assembles them.
        if (
            resume.get("status") == "needs_recheck"
            and resume.get("error_code") == "resume_author_needs_recheck"
        ) or (
            resume.get("status") == "failed"
            and resume.get("error_code") == "resume_latex_invalid"
            and (task.get("experience_handoff") or {}).get("status") != "adopted"
        ):
            retried = True
            task = self.flow.start(
                task["id"],
                task["revision"],
                "resume",
                retry=True,
                _continuation_request_id=request_id,
            )
        export = task["stages"].get("export", {})
        if export.get("status") == "failed" and export.get("error_code") in {
            "resume_pdf_source_defect",
            *_EXPORT_ENVIRONMENT_FAILURES,
        }:
            retried = True
            # A defective source is rewritten; an unreachable compiler is only retried.
            task = self.flow.start(
                task["id"],
                task["revision"],
                "resume" if export["error_code"] == "resume_pdf_source_defect" else "export",
                retry=True,
                _continuation_request_id=request_id,
            )
        if (task.get("cover_letter") or {}).get("status") == "needs_recheck":
            retried = True
            try:
                # A locally saved letter is adopted without calling the writer again.
                self.flow.recheck_cover_letter(task["id"], task["revision"])
            except PortalDataError:
                self.flow.start_cover_letter(
                    task["id"], retry=True, _continuation_request_id=request_id
                )
        return retried

    def _material_wait_for_recovery(self, state):
        if (
            state["status"] != "needs_input"
            or state["control"] != "paused"
            or state.get("resume_status") != "generating_resume"
            or state.get("wait_reason") not in {"material_base_required", "material_facts_required"}
            or not state.get("active_task_id")
            or state.get("worker_batch_id")
            or state.get("transmission_authorization")
        ):
            return False
        task = self._task(state)
        if state.get("wait_reason") == "material_facts_required":
            return (
                task["status"] in {"draft_ready", "analysis_ready", "stale", "draft"}
                and not task.get("worker_ref")
                and not any(
                    row.get("status") in {"queued", "running", "needs_recheck"}
                    for row in task["stages"].values()
                )
            )
        return task["status"] == "analysis_ready" and not task.get("worker_ref")

    def _can_restart(self, state):
        if any(
            job.get("status") != "cancelled" or job.get("page_open") or job.get("intent")
            for job in self.worker.snapshot().get("jobs", [])
        ):
            return False
        if self.intake.snapshot()["status"] == "running":
            return False
        tasks = self.flow.snapshot().get("tasks", [])
        identifiers = {row.get("task_id") for row in state["items"]}
        return not any(
            task.get("worker_ref")
            or task.get("status") == "needs_recheck"
            or any(
                stage.get("status") in {"queued", "running", "needs_recheck"}
                for stage in task.get("stages", {}).values()
            )
            for task in tasks
            if task["id"] in identifiers
        )

    def _notify(self, state, status, message):
        state["notification"] = {
            "id": uuid4().hex,
            "status": status,
            "title": "申请页面等待最终确认" if status == "ready_for_review" else "自动流程需要处理",
            "message": message[:1000],
            "task_id": state.get("active_task_id"),
            "at": time.time(),
        }

    def _stop(self, state, status, message):
        if not state.get("resume_status"):
            self._queue_assertion("stop_without_resume_status", state, ["resume_status"])
        state.update(control="paused", status=status)
        self._notify(state, status, message)
        self._save(state)

    def _task(self, state):
        return self.flow.task_snapshot(state["active_task_id"])

    def _task_by_id(self, item):
        return self.flow.task_snapshot(item["task_id"])

    def _check_posting(self, state, item, application):
        """Read a LinkedIn job once before matching (decided 2026-10-31).

        A closed posting is marked closed and an Easy Apply or Indeed Apply one keeps
        its job board; each leaves the queue with its reason. An open one moves to the
        employer's page.
        Returns the application to continue with, or None when the job was left.
        """
        from .indeed_job_source import apply_route
        from .job_listing_links import employer_url, posting_status

        listing = application.get("listing_url") or application["url"]
        status, target = posting_status(listing)
        if status is None:
            # An Indeed job's route was read with its page (2026-11-05).
            record = next(
                (
                    row
                    for row in self.intake.snapshot().get("recommendations", [])
                    if row["id"] == item["recommendation_id"]
                ),
                None,
            )
            status = "indeed_apply" if apply_route(record) == "indeed_apply" else None
        today = time.strftime("%Y-%m-%d")
        changes, reason = {}, None
        if status == "closed":
            reason = "posting_closed"
            changes = {
                "status": "closed",
                "next_action": f"领英显示岗位已停止招聘（{today} 自动核对）。",
            }
        elif status == "easy_apply":
            reason = "easy_apply_only"
            changes = {
                "next_action": "只能在领英站内申请（Easy Apply），自动流程不能填写；"
                "需要时请自己在领英投递。"
            }
        elif status == "indeed_apply":
            reason = "indeed_apply_only"
            changes = {
                "next_action": "只能在 Indeed 站内申请（Indeed Apply），自动流程不能填写；"
                "需要时请自己在 Indeed 投递。"
            }
        elif status == "open" and listing == application["url"]:
            final = employer_url(target)
            if final:
                changes = {"url": final, "listing_url": listing}
        if changes:
            application = self.flow.applications.update_application(
                application["id"], changes, application["revision"]
            )
        if reason is None:
            return application
        item["reason"] = reason
        if state.get("queue_mode") and state.get("current_recommendation_id"):
            self._leave_current(state, f"{reason}:{item['recommendation_id']}")
        else:
            item["status"] = "skipped"
            self._save(state)
        return None

    def _rebind_job_url(self, state, task):
        """Move this cycle's send authorization to the link the user corrected.

        Only the destination changes; the old receipt stays history. JD, analysis
        and materials stay bound, and the new run's checks still compare them.
        """
        url = self.flow.applications.get_application(task["application_id"])["url"]
        receipt = state["transmission_authorization"]
        if not url or url == receipt["job_url"]:
            return task
        state.setdefault("transmission_authorization_history", []).append(deepcopy(receipt))
        receipt["job_url"] = url
        self._save(state)
        self.flow.rebind_job_url(task["id"], task["revision"], deepcopy(receipt))
        return self._task(state)

    def _pause_owned_worker(self, state):
        if not state.get("active_task_id") or not state.get("worker_batch_id"):
            return
        # Control reads remain available while a local journal is between its
        # old/new material bindings. Actual pause sends keep the ordinary checks.
        reader = (
            getattr(self.flow, "callbacks", {}).get("bound_worker_state") or self.worker.snapshot
        )
        current = reader()
        if (
            state.get("active_task_id")
            and (
                current.get("control") == "running"
                or any(
                    (job.get("continuation") or {}).get("status") == "pending"
                    for job in current.get("jobs", [])
                )
                or (current.get("backend_recovery") or {}).get("status") in {"suspended", "pending"}
            )
            and current.get("controller") == state.get("controller")
            and current.get("batch_id") == state.get("worker_batch_id")
        ):
            task = self._task(state)
            self.flow.worker_action(
                task["id"], task["revision"], "pause", {"controller": state["controller"]}
            )

    def _run(self, interval):
        while not self._closed.wait(interval):
            try:
                self._tick()
            except Exception:
                self._runtime_error = "pipeline_checkpoint_unavailable"
                self._closed.set()
                try:
                    with self._guard:
                        state = self._load()
                        self._pause_owned_worker(state)
                        self._stop(state, "needs_recheck", "自动流程记录未能核验，已停止自动动作。")
                except Exception:
                    pass

    def _tick(self):
        with self._guard:
            if self._closed.is_set() or not self._owner:
                return
            state = self._load()
            if state.get("status") == "recovering_worker":
                if state.get("queue_mode") and state.get("id"):
                    self._poll_mail(state)
                self._recover_worker(state)
                return
            if state.get("queue_mode") and state.get("id"):
                self._poll_mail(state)
            if self._reconcile_cancellation(state):
                return
            if (
                state.get("queue_mode")
                and state.get("id")
                and state.get("worker_batch_id")
                and state["status"] != "continuing_worker"
            ):
                self._observe_submission(state)
            if state["control"] != "running":
                return
            try:
                self._advance(state)
            except PortalDataError as error:
                # The private record keeps which check stopped the job (2026-10-31).
                state["last_stop_error"] = {
                    "code": error.code,
                    "location": getattr(error, "location", None),
                    "at": time.time(),
                }
                self._pause_owned_worker(state)
                self._stop(state, "needs_recheck", str(error))

    def _poll_mail(self, state):
        """Capture alone may run while a job waits; source work stays sequential."""
        # Selection runs right after a capture completes; a real capture outlasts the
        # 60 s poll, so restarting one here would hold selection behind it indefinitely.
        # A paused step resuming into selection or a source would wait on it too; a
        # stopped mail read is the one wait this capture recovers.
        after_mail = {"selecting_job", "starting_source", "acquiring_source"}
        if (
            state["status"] in after_mail | {"reading_email", "starting_email"}
            or state.get("resume_status") in after_mail
            or state.get("mail_capture_error")
            or time.time() < state.get("mail_poll_at", 0)
        ):
            return
        intake = self.intake.snapshot()
        if intake["status"] == "running":
            return
        state["mail_poll_at"] = time.time() + 60
        state["automatic_capture"] = {"status": "dispatching", "at": time.time()}
        self._save(state)
        try:
            result = self.intake.refresh(capture_only=True)
        except (OSError, ValueError, TypeError, PortalDataError) as error:
            state["mail_capture_error"] = getattr(error, "code", type(error).__name__)
            state["automatic_capture"]["status"] = "needs_recheck"
        else:
            state["automatic_capture"].update(status="started", run_id=result["run_id"])
        self._save(state)

    def _queue(self, state):
        intake = self.intake.snapshot()
        if state["status"] == "reading_email":
            if state["intake_run_id"] is None:
                if intake["status"] == "running":
                    if (
                        intake.get("capture_only") is not True
                        or intake.get("operation") == "source"
                    ):
                        self._stop(state, "blocked", "已有岗位读取正在进行，保留原读取进度。")
                        return
                    result = intake
                else:
                    state["status"] = "starting_email"
                    self._save(state)
                    result = self.intake.refresh(capture_only=True)
                state.update(
                    intake_run_id=result["run_id"],
                    status="reading_email",
                    mail_poll_at=time.time() + 60,
                )
                self._save(state)
                return
            if intake.get("capture_only") is not True or intake.get("operation") == "source":
                self._stop(state, "needs_recheck", "邮件读取范围已变化，保留原进度。")
                return
            if intake["status"] == "running":
                return
            if intake["status"] not in {"complete", "no_matches"}:
                state.update(resume_status="reading_email", wait_reason="mail_capture_incomplete")
                self._stop(state, "needs_input", "邮件收录尚未完成，请先处理本次读取原因。")
                return
            state["status"] = "selecting_job"
            self._save(state)
            return
        if state["status"] in {"selecting_job", "waiting_for_mail"}:
            admitted = next((row for row in state["items"] if row["status"] == "admitted"), None)
            if admitted is not None:
                if admitted["application_id"]:
                    admitted["status"] = "pending"
                    state.update(
                        current_recommendation_id=admitted["recommendation_id"], status="matching"
                    )
                else:
                    record = next(
                        row
                        for row in intake["recommendations"]
                        if row["id"] == admitted["recommendation_id"]
                    )
                    state.update(
                        current_recommendation_id=record["id"],
                        status="acquiring_source",
                        source_receipt={
                            "recommendation_id": record["id"],
                            "recommendation_revision": record["revision"],
                            "status": "selected",
                        },
                    )
                self._save(state)
                return
            if intake["status"] == "running":
                return
            seen = {row.get("recommendation_id") for row in state["items"]}
            seen |= set(state.get("closed_postings", []))
            applications = {
                row.get("application_id") for row in state["items"] if row.get("application_id")
            }
            record = next(
                (
                    row
                    for row in intake["recommendations"]
                    if row["id"] not in seen
                    and (row.get("existing_application") or {}).get("id") not in applications
                ),
                None,
            )
            if record is None:
                if state["status"] != "waiting_for_mail":
                    state["status"] = "waiting_for_mail"
                    self._save(state)
                return
            state.update(
                current_recommendation_id=record["id"],
                status="acquiring_source",
                source_receipt={
                    "recommendation_id": record["id"],
                    "recommendation_revision": record["revision"],
                    "status": "selected",
                },
            )
            self._save(state)
            return
        record = next(
            (
                row
                for row in intake["recommendations"]
                if row["id"] == state.get("current_recommendation_id")
            ),
            None,
        )
        if record is None:
            raise PortalDataError("pipeline_source_invalid", "当前岗位来源不能核验。", 409)
        checkpoint = record.get("acquisition_checkpoint")
        if intake["status"] == "running":
            return
        retry = bool(
            checkpoint == "failed"
            and state["source_receipt"]["status"] == "selected"
            and state["source_receipt"].get("retry_request_id")
        )
        unknown = checkpoint == "needs_recheck" or (
            checkpoint == "failed"
            and state["source_receipt"]["status"] in {"dispatching", "needs_recheck"}
        )
        if unknown or (checkpoint == "failed" and not retry):
            self._stop(
                state,
                "needs_recheck" if unknown else "needs_input",
                "当前岗位取源结果待核验。"
                if unknown
                else "Indeed 要求人工验证：点继续会重开岗位页，请在弹出的 Chrome 窗口完成验证。"
                if record.get("source_error_code") == "verification_required"
                else "当前岗位未取得完整 JD，请处理原因后继续重试、补充来源或跳过。",
            )
            return
        if record["jd_completeness"] != "full":
            if state["source_receipt"]["status"] != "selected":
                self._stop(state, "needs_recheck", "当前岗位取源结果尚不能核验，保留原记录。")
                return
            state["status"] = "starting_source"
            state["source_receipt"]["status"] = "dispatching"
            self._save(state)
            try:
                result = (
                    self.intake.acquire(record["id"], record["revision"], retry=True)
                    if retry
                    else self.intake.acquire(record["id"], record["revision"])
                )
            except (OSError, ValueError, TypeError, PortalDataError) as error:
                state["source_receipt"].update(
                    status="needs_recheck", error_code=getattr(error, "code", type(error).__name__)
                )
                self._stop(state, "needs_recheck", "当前岗位取源发起结果待核验，保留原记录。")
                return
            state["source_receipt"].update(status="started", run_id=result["run_id"])
            state["status"] = "acquiring_source"
            self._save(state)
            return
        try:
            selected = self.intake.select(record["id"], record["revision"])
        except PortalDataError as error:
            if error.code != "recommendation_posting_closed":
                raise
            # A closed posting leaves the queue unlisted and creates no record.
            closed = state.setdefault("closed_postings", [])
            if record["id"] not in closed:
                closed.append(record["id"])
            state["items"] = [
                row for row in state["items"] if row.get("recommendation_id") != record["id"]
            ]
            state.pop("source_receipt", None)
            state.update(current_recommendation_id=None, status="selecting_job")
            self._save(state)
            return
        state["source_receipt"]["status"] = "adopted"
        item = next(
            (row for row in state["items"] if row.get("recommendation_id") == record["id"]), None
        )
        if item is None:
            item = {"recommendation_id": record["id"]}
            state["items"].append(item)
        item.update(
            application_id=selected["application"]["id"], task_id=None, status="pending", score=None
        )
        state["status"] = "matching"
        self._save(state)

    def _advance(self, state):
        backfill = [
            item
            for item in state["items"]
            if item.get("reason") == "flow_eligibility_required" and "mismatch" not in item
        ]
        for item in backfill:
            # Jobs stopped before 2026-11-05 learn which hard conditions they miss.
            try:
                item["mismatch"] = _mismatch(task_eligibility(self._task_by_id(item)))
            except (OSError, PortalDataError, KeyError, TypeError, ValueError):
                item["mismatch"] = []
        if backfill:
            self._save(state)
        if match_refresh_running(self.flow, other_than=state.get("active_task_id")):
            # Skip releases adoption, not the callback's physical execution slot.
            return
        if hasattr(self.flow, "cover_letter_outcome"):
            outcomes = (
                self.flow.material_outcomes(
                    item["task_id"] for item in state["items"] if item.get("task_id")
                )
                if hasattr(self.flow, "material_outcomes")
                else None
            )
            for item in state["items"]:
                if not item.get("task_id"):
                    continue
                letter = (
                    {"status": outcomes[item["task_id"]]["cover_letter"]}
                    if outcomes is not None
                    else self.flow.cover_letter_outcome(item["task_id"])
                )
                consistency = (
                    {"status": outcomes[item["task_id"]]["material_consistency"]}
                    if outcomes is not None
                    else self.flow.material_consistency_outcome(item["task_id"])
                    if hasattr(self.flow, "material_consistency_outcome")
                    else {}
                )
                if consistency.get("status") == "needs_recheck" or (
                    item.get("status") != "skipped"
                    and consistency.get("status") in {"conflict", "failed"}
                ):
                    self._pause_owned_worker(state)
                    state.setdefault("cover_letter_resume_status", state["status"])
                    state["wait_reason"] = "material_consistency_required"
                    self._stop(
                        state,
                        "needs_recheck"
                        if consistency["status"] == "needs_recheck"
                        else "needs_input",
                        "两份材料存在事实冲突，请处理对应正文。"
                        if consistency["status"] == "conflict"
                        else "两份材料一致性检查尚未启动，请重试本地排队阶段。"
                        if consistency["status"] == "failed"
                        else "两份材料一致性调用结果未知，请核验原回执。",
                    )
                    return
                if letter["status"] == "needs_recheck":
                    self._pause_owned_worker(state)
                    state.setdefault("cover_letter_resume_status", state["status"])
                    state["wait_reason"] = "cover_letter_result_unknown"
                    self._stop(state, "needs_recheck", "求职信调用结果未知，请核验原尝试。")
                    return
                if item.get("status") == "skipped" and (
                    letter["status"] in {"queued", "running"}
                    or consistency.get("status") in {"queued", "running"}
                ):
                    # Skip stops adoption, but the next job must not overlap an
                    # author call which is still held by the previous job.
                    return
        if state.get("queue_mode") and state["status"] in {
            "reading_email",
            "selecting_job",
            "waiting_for_mail",
            "acquiring_source",
        }:
            self._queue(state)
            return
        if state["status"] == "reading_email":
            if state["intake_run_id"] is None:
                with self.flow.applications.write_lock():
                    if self.intake.snapshot()["status"] == "running":
                        self._stop(state, "blocked", "邮件读取已有任务；保留原读取进度。")
                        return
                    # The shared lock binds the new run to this admission; a manual
                    # historical refresh cannot occupy the gap before refresh().
                    state["status"] = "starting_email"
                    self._save(state)
                    result = self.intake.refresh(max_results=3, max_candidates=10)
                run_id = result.get("run_id")
                if not isinstance(run_id, str) or re.fullmatch(r"[a-f0-9]{32}", run_id) is None:
                    raise PortalDataError("pipeline_intake_invalid", "邮件读取身份不能核验。", 409)
                state.update(intake_run_id=run_id, status="reading_email")
                self._save(state)
                return
            result = self.intake.snapshot()
            if result.get("run_id") != state["intake_run_id"]:
                self._stop(state, "needs_recheck", "邮件读取范围已变化；保留本次记录。")
                return
            if result["status"] == "running":
                return
            if result["status"] not in {"complete", "partial", "no_matches"}:
                self._stop(state, "needs_input", "邮件读取未完成，请查看本次读取原因。")
                return
            identifiers = self.intake.source_delivery(state["intake_run_id"])["application_ids"]
            if len(identifiers) > 10:
                raise PortalDataError("pipeline_source_invalid", "本次岗位超出读取范围。", 409)
            state["items"] = [
                {"application_id": identifier, "task_id": None, "status": "pending", "score": None}
                for identifier in identifiers
            ]
            if not identifiers:
                self._stop(state, "no_matches", "本次邮件没有取得可分析的完整岗位 JD。")
                return
            state["status"] = "matching"
            self._save(state)
            return
        if state["status"] == "matching":
            self._match(state)
            return
        if state["status"] in {"generating_resume", "preparing", "awaiting_native_check"}:
            self._materials(state)
            return
        if state["status"] == "continuing_worker":
            if state.get("material_update_id"):
                from .application_bound_materials import advance as advance_material_update

                if advance_material_update(self, state):
                    return
            current = self.worker.snapshot()
            task = self._task(state)
            job = next(
                (row for row in current["jobs"] if row["application_id"] == task["application_id"]),
                {},
            )
            continuation = job.get("continuation") or {}
            if continuation.get("status") == "pending":
                return
            if continuation.get("status") != "verified":
                self._stop(state, "needs_recheck", "当前原页继续结果待核验，保留人工修改。")
                return
            state.update(
                status="filling",
                worker_runtime_id=(current.get("runtime") or {}).get("id"),
                last_heartbeat=0,
            )
            self._save(state)
            return
        if state["status"] == "starting_worker":
            self._start_worker(state)
            return
        if (
            state["status"] in {"filling", "needs_input"}
            or state["status"] == "ready_for_review"
            and state.get("pending_optional_cover_letter")
        ) and state.get("worker_batch_id"):
            self._observe_worker(state)

    @staticmethod
    def _matching_item(state):
        return next(
            (
                row
                for row in state["items"]
                if row["status"] in {"pending", "matching", "matched"}
                and (
                    not state.get("queue_mode")
                    or row.get("recommendation_id") == state.get("current_recommendation_id")
                )
            ),
            None,
        )

    def _match(self, state):
        item = self._matching_item(state)
        if item is None:
            if state.get("queue_mode") and any(
                row.get("recommendation_id") == state.get("current_recommendation_id")
                and row["status"] == "excluded"
                for row in state["items"]
            ):
                state.update(current_recommendation_id=None, status="selecting_job")
                self._save(state)
                return
            self._stop(state, "needs_input", "本次岗位均不满足自动准备条件，原因已逐岗保存。")
            return
        if item["status"] == "matched":
            # Four score tiers (decided 2026-10-31); a decision binds to its analysis.
            tier = item.get("score_tier", "auto")
            decided = item.get("score_decision") == item.get("score_analysis_id")
            if tier == "skip" and not decided:
                item["reason"] = "low_match_score"
                if state.get("queue_mode") and state.get("current_recommendation_id"):
                    state["active_task_id"] = item["task_id"]
                    self._leave_current(state, "low-score:" + item["task_id"])
                else:
                    item["status"] = "skipped"
                self._save(state)
                return
            if tier == "approve" and not decided:
                state.update(active_task_id=item["task_id"], wait_reason="score_approval")
                self._stop(
                    state,
                    "needs_input",
                    "匹配分在待审批区间或两个模型分差较大：请查看匹配概览，点继续即批准生成材料。",
                )
                return
            if tier == "manual" and item.get("application_route") != "manual":
                item.update(
                    application_route="manual",
                    route_reasons=[*item.get("route_reasons", []), "匹配分达到 75 以上"],
                )
            state.update(active_task_id=item["task_id"], status="generating_resume")
            self._save(state)
            return
        application = self.flow.applications.get_application(item["application_id"])
        if item["task_id"] is None and not item.get("posting_checked"):
            item["posting_checked"] = True
            application = self._check_posting(state, item, application)
            if application is None:
                return
        if item["task_id"] is None:
            screening = next(
                row["screening"]
                for row in screen_applications(
                    self.flow.applications.list_applications(),
                    application_id=application["id"],
                    language_levels=self.worker.store.language_levels,
                    allow_generic=self.worker.generic,
                )
                if row["id"] == application["id"]
            )
            route, route_reasons = screening["application_route"], screening["route_reasons"]
            if screening["language_needs_input"]:
                # Language uncertainty must not replace an explicit hold or the
                # saved precision decision; it still stops eligible current work.
                route, route_reasons = application_route(
                    application, relevant=screening["target_relevant"]
                )
            item.update(application_route=route, route_reasons=route_reasons)
            excluded = (
                screening["category"] in {"recorded", "excluded"}
                or not screening["worker_supported"]
                or route in {"hold", "excluded", "recorded"}
            )
            if screening["language_needs_input"] and not excluded:
                item.update(
                    status="needs_input",
                    reason=screening["reasons"],
                    reason_code="language_information_required",
                )
                state["resume_status"] = "matching"
                self._stop(state, "needs_input", "当前岗位的适用语言信息需确认，其他岗位保持等待。")
                return
            if not screening["worker_preparable"] or excluded:
                item.update(
                    status="excluded",
                    reason=route_reasons
                    if route == "hold"
                    else screening["reasons"] or route_reasons,
                )
                self._save(state)
                return
            task = self.flow.create(
                application["id"],
                application["revision"],
                **({"fresh_job_brief": True} if item.pop("fresh_job_brief", False) else {}),
            )
            item["task_id"] = task["id"]
            item["status"] = "matching"
            self._save(state)
        task = self.flow.task_snapshot(item["task_id"])
        outcome = self.flow.analysis_outcome(task["id"]) if state.get("queue_mode") else None
        if outcome is not None and outcome["task_revision"] != task["revision"]:
            # A changed attempt must be observed on the next tick before acting.
            return
        analysis_status = (
            outcome["status"]
            if outcome
            else {"draft": "pending", "analysis_ready": "ready", "analyzing": "running"}.get(
                task["status"], "unknown"
            )
        )
        if analysis_status == "pending":
            self.flow.prepare(task["id"], task["revision"], analysis_only=True)
        elif analysis_status == "ready":
            analysis = adopted_analysis(task)
            score, models = combined_score(
                calculate_match_score(analysis["requirements"]), analysis, analysis["requirements"]
            )
            item["score"] = score
            item.update(
                score_tier=score_tier(score, needs_review=bool(models and models["needs_review"])),
                score_analysis_id=task["analysis_id"],
            )
            eligibility = task_eligibility(task)
            eligible = eligibility["status"] in {"supported", "not_specified", "needs_input"}
            item.update(
                status="matched" if eligible and score["lower"] is not None else "needs_input",
                reason="" if eligible else "flow_eligibility_required",
            )
            item.pop("mismatch", None)
            if not eligible:
                item["mismatch"] = _mismatch(eligibility)
            if item["status"] == "needs_input":
                state.update(
                    active_task_id=task["id"],
                    wait_reason="qualification_conflict"
                    if not eligible
                    else "match_evidence_required",
                )
                self._stop(
                    state, "needs_input", "当前岗位的资格或匹配依据需核验，其他岗位保持等待。"
                )
                return
            self._save(state)
        elif outcome is not None and outcome["status"] == "rejected":
            item.update(
                reason=outcome["error_code"],
                analysis_attempt_id=outcome["attempt_id"],
                task_revision=outcome["task_revision"],
            )
            state.update(
                active_task_id=task["id"],
                resume_status="matching",
                wait_reason="analysis_input_required",
            )
            self._stop(
                state,
                "needs_input",
                "当前岗位分析未通过校验，请处理已保存的失败原因；其他岗位保持等待。",
            )
        elif outcome is None and _known_analysis_failure(task):
            item.update(
                status="analysis_failed",
                reason=task["stages"]["analysis"]["error_code"],
                analysis_attempt_id=task["stages"]["analysis"]["attempt_id"],
                task_revision=task["revision"],
            )
            self._save(state)
        elif analysis_status != "running":
            if outcome is not None:
                state.update(
                    active_task_id=task["id"],
                    resume_status="matching",
                    wait_reason="analysis_result_unknown",
                )
            self._stop(state, "needs_recheck", "岗位已有其他阶段或未知结果，保留原任务。")

    def _materials(self, state):
        with self.flow.applications.write_lock():
            task = self._task(state)
            continuation = state.pop("resume_author_retry", None)
            if continuation is not None:
                # The old durable queue receipt is an opaque Flow continuation reference.
                # Consume it once even if its original attempt is no longer current.
                self._save(state)
                if continuation.get("task_id") == task["id"]:
                    self.flow.continue_preparation(
                        task["id"],
                        task["revision"],
                        request_id=continuation["request_id"],
                        expected_attempt_id=continuation.get("attempt_id"),
                    )
                    return
            progress = self.flow.prepare(task["id"], task["revision"])
            task = progress["task"]
            reason = progress["wait_reason"]
            if progress["status"] in {"waiting", "needs_recheck", "failed", "cancelled"}:
                state.update(resume_status="generating_resume", wait_reason=reason)
                self._stop(
                    state,
                    "needs_input" if progress["status"] == "waiting" else "needs_recheck",
                    progress["message"] or "材料生成未完成，保留原任务和结果。",
                )
                return
            if reason != state.get("wait_reason"):
                if reason is None:
                    state.pop("wait_reason", None)
                else:
                    state["wait_reason"] = reason
                self._save(state)
            if not progress["can_prepare_execution"]:
                return
        item = next(row for row in state["items"] if row.get("task_id") == task["id"])
        application = self.flow.applications.get_application(task["application_id"])
        country = application_country(application.get("location"))
        if country is None:
            state.update(
                resume_status="generating_resume", wait_reason="application_country_required"
            )
            self._stop(state, "needs_input", "岗位来源未明确唯一申请国家；请补充该岗位地点。")
            return
        existing = self.worker.snapshot()
        if hasattr(self.worker, "check_new_current_job"):
            self.worker.check_new_current_job()
        elif any(
            job.get("status") != "cancelled" or job.get("page_open") or job.get("intent")
            for job in existing.get("jobs", [])
        ):
            self._stop(state, "blocked", "已有申请任务或保留的原页，请先核验原任务。")
            return
        receipt = {
            "policy_version": POLICY,
            "authorization_id": state["authorization"]["id"],
            "pipeline_id": state["id"],
            "intake_run_id": state["intake_run_id"],
            "task_id": task["id"],
            "application_id": task["application_id"],
            "job_url": application["url"],
            "analysis_id": task["analysis_id"],
            "job_binding": task["job_binding"],
            "inputs": deepcopy(task["inputs"]),
            "resume_id": task["resume_id"],
            "resume_sha256": task["resume_sha256"],
            "country": country,
        }
        if item.get("application_route") == "manual" and not item.get("precision_adjustment"):
            receipt["precision_preparation"] = True
        state.update(transmission_authorization=receipt, status="preparing")
        self._save(state)
        try:
            prepared = self.flow.prepare_worker(
                task["id"], task["revision"], country, True, automation_authorization=receipt
            )
        except PortalDataError as error:
            after = self._task(state)
            if error.code == "installed_write_preflight_required" and after == task:
                state["status"] = "awaiting_native_check"
                self._save(state)
                return
            raise
        state.update(
            worker_batch_id=prepared["worker_ref"]["batch_id"],
            status="starting_worker",
            notification=None,
        )
        self._save(state)

    def verify_authorization(self, receipt, task):
        # Called under the application lock by prepare; never acquire the runner
        # guard here, because the runner acquires these locks in the other order.
        with self.flow.applications.write_lock():
            state = self._load()
            return self._verify_binding(state, receipt, task)

    def _verify_binding(self, state, receipt, task):
        return bool(
            self._owner
            and not self._closed.is_set()
            and not self._runtime_error
            and state["control"] == "running"
            and state["status"] in {"preparing", "awaiting_native_check"}
            and isinstance(receipt, dict)
            and receipt == state.get("transmission_authorization")
            and receipt.get("authorization_id") == (state.get("authorization") or {}).get("id")
            and receipt.get("pipeline_id") == state["id"]
            and receipt.get("intake_run_id") == state["intake_run_id"]
            and state["active_task_id"] == task["id"] == receipt.get("task_id")
            and receipt.get("job_url")
            == self.flow.applications.get_application(task["application_id"])["url"]
            and any(
                row["task_id"] == task["id"]
                and row["status"] == "matched"
                and row["application_id"] == task["application_id"]
                for row in state["items"]
            )
            and all(
                receipt.get(key) == task.get(key)
                for key in (
                    "application_id",
                    "analysis_id",
                    "job_binding",
                    "inputs",
                    "resume_id",
                    "resume_sha256",
                )
            )
        )

    def _start_worker(self, state):
        task = self._task(state)
        current = self.worker.snapshot()
        job = next(
            (
                row
                for row in current.get("jobs", [])
                if row["application_id"] == task["application_id"]
            ),
            None,
        )
        if (
            current.get("batch_id") != state["worker_batch_id"]
            or "current_job_id" in current
            and current["current_job_id"] != task["application_id"]
            or job is None
            or job["status"] != "queued"
            or job.get("page_open")
            or job.get("intent")
            or job.get("handed_off")
            or current["control"] != "paused"
        ):
            self._stop(state, "needs_recheck", "填写准备结果已变化，保留原页与任务。")
            return
        state["status"] = "admitting_worker"
        self._save(state)
        try:
            self.flow.worker_action(
                task["id"], task["revision"], "resume", {"controller": state["controller"]}
            )
        except PortalDataError as error:
            after = self.worker.snapshot()
            if error.code == "installed_write_preflight_required" and after == current:
                state["status"] = "starting_worker"
                self._save(state)
                return
            raise
        # The new run registers after this call; its first observation records its ID.
        state.update(status="filling", worker_runtime_id=None, last_heartbeat=0)
        self._save(state)

    def _observe_submission(self, state):
        current = self.worker.snapshot()
        if "current_job_id" not in current or not state.get("active_task_id"):
            return
        task = self._task(state)
        job = next(
            (row for row in current["jobs"] if row["application_id"] == task["application_id"]), {}
        )
        if current.get("current_job_id") != task["application_id"]:
            return
        observed = job.get("submission_observation") or {}
        conclusion = observed.get("conclusion")
        if observed.get("status") == "observed" and conclusion == "success":
            if (
                not job.get("manual_submission")
                or job.get("sync_error")
                or job.get("pending_status")
            ):
                self._stop(state, "needs_recheck", "成功结果尚未完成本地记录，保留原页核验。")
                return
            self._leave_current(state, "completed-" + observed["request_id"])
            item = next(row for row in state["items"] if row.get("task_id") == task["id"])
            item["status"] = "completed"
            self._save(state)
            return
        if observed.get("status") == "observed" and conclusion in {"rejected", "unknown"}:
            if state.get("observed_result_request") != observed["request_id"]:
                state["observed_result_request"] = observed["request_id"]
                self._stop(
                    state,
                    "needs_input" if conclusion == "rejected" else "needs_recheck",
                    "网站明确拒绝本次提交，请在当前原页处理。"
                    if conclusion == "rejected"
                    else "提交结果尚不明确，保留原页；不会重填、重传或重交。",
                )
            return
        if (
            state["status"] not in {"ready_for_review", "observing_result"}
            or not job.get("handed_off")
            or (job.get("handoff") or {}).get("status") != "complete"
            or self._result_read_awaited(current, job, observed)
            or time.time() < state.get("result_poll_at", 0)
        ):
            return
        state["result_poll_at"] = time.time() + 5
        self._save(state)
        try:
            self.flow.worker_action(
                task["id"], task["revision"], "observe-result", {"request_id": uuid4().hex}
            )
        except PortalDataError as error:
            self._stop(state, "needs_recheck", str(error))

    @staticmethod
    def _result_read_awaited(current, job, observed):
        """Wait only for this run's and page's own recent result read.

        A pending read from an earlier run or page, or one left unserved, is never
        settled; waiting on it stopped every later result poll, so the user's Submit
        went unrecorded (2026-11-03: a 19:01 read held until 22:52 and after). The
        Worker moves the replaced read to its history.
        """
        if observed.get("status") != "pending":
            return False
        at = observed.get("at")
        return bool(
            observed.get("run_id") == (current.get("runtime") or {}).get("id")
            and observed.get("page_id") == (job.get("page_observation") or {}).get("page_id")
            and type(at) in {int, float}
            and 0 <= time.time() - at < RESULT_READ_WAIT
        )

    def _observe_worker(self, state):
        if state.get("material_update_id"):
            from .application_bound_materials import advance as advance_material_update

            advance_material_update(self, state)
        current = self.worker.snapshot()
        task = self._task(state)
        job = next(
            (
                row
                for row in current.get("jobs", [])
                if row["application_id"] == task["application_id"]
            ),
            None,
        )
        runtime_id = (current.get("runtime") or {}).get("id")
        if (
            current.get("batch_id") != state["worker_batch_id"]
            or "current_job_id" in current
            and current["current_job_id"] != task["application_id"]
            or job is None
            or current.get("controller") != state["controller"]
            or state.get("worker_runtime_id") is not None
            and runtime_id != state["worker_runtime_id"]
        ):
            self._stop(state, "needs_recheck", "填写控制权或运行身份已变化，已停止后台控制。")
            return
        if current["control"] != "running" and self._begin_backend_recovery(
            state, task, runtime_id
        ):
            return
        precision = job.get("precision_preparation") or {}
        if precision.get("status") == "ready" and job.get("reason") == "precision_adjustment":
            if (
                precision.get("task_id") != task["id"]
                or precision.get("authorization_id") != (state.get("authorization") or {}).get("id")
                or precision.get("run_id") != runtime_id
                or precision.get("page_id") != (job.get("page_observation") or {}).get("page_id")
                or current["control"] != "paused"
                or job.get("intent")
            ):
                self._stop(state, "needs_recheck", "精准材料准备的原页回执已变化。")
                return
            state["wait_reason"] = "precision_adjustment"
            self._stop(
                state, "needs_input", "精准岗位已完成当前已知必要材料初稿，请按需调整后一次继续。"
            )
            return
        if job["status"] == "needs_input":
            if (
                precision.get("status") == "preparing"
                or precision
                and job.get("reason") == "material_field_mapping_required"
            ):
                self._pause_owned_worker(state)
                state["wait_reason"] = job.get("reason") or "missing_materials"
                self._stop(
                    state, "needs_input", "当前已知必要材料仍缺少重要资料，请在原页补充后继续。"
                )
                return
            if job.get("intent"):
                self._pause_owned_worker(state)
                self._stop(state, "needs_recheck", "待补充岗位仍有未决动作，请核验原页。")
                return
            if (state.get("notification") or {}).get("status") != "needs_input":
                self._notify(state, "needs_input", "申请页面需要补充已有信息库中没有的事实。")
            state["status"] = "needs_input"
            self._save(state)
        elif state["status"] in {"needs_input", "ready_for_review"} and job["status"] == "filling":
            state.pop("pending_optional_cover_letter", None)
            state.update(status="filling", notification=None)
            self._save(state)
        takeover = (
            self._request_takeover(state, task, job, runtime_id, current)
            if job["status"] == "needs_recheck"
            else None
        )
        optional_pending = (
            job["status"] == "ready_for_review"
            and current["control"] == "running"
            and not job.get("handed_off")
            and not job.get("manual_intervention")
            and not job.get("manual_submission")
            and not job.get("intent")
            and (job.get("cover_letter_delivery") or {}).get("status") in {"queued", "running"}
            and (job.get("cover_letter_delivery") or {}).get("requirement") == "optional"
            and bool((job.get("cover_letter_delivery") or {}).get("selected_fields"))
            and (task.get("cover_letter") or {}).get("status") in {"queued", "running", "ready"}
        )
        if optional_pending:
            if not state.get("pending_optional_cover_letter"):
                state.update(status="ready_for_review", pending_optional_cover_letter=True)
                self._notify(
                    state,
                    "ready_for_review",
                    "必需材料已就绪；可选求职信仍在准备，将在保留的原页补充。最终提交由你完成。",
                )
                self._save(state)
        elif takeover is not True and job["status"] in {
            "ready_for_review",
            "needs_recheck",
            "cancelled",
        }:
            state.pop("pending_optional_cover_letter", None)
            self._pause_owned_worker(state)
            task = self._task(state)
            if (
                state.get("queue_mode")
                and "current_job_id" in current
                and job["status"] == "ready_for_review"
                and not job.get("handed_off")
            ):
                self.flow.worker_action(
                    task["id"],
                    task["revision"],
                    "review",
                    {"actor": "system", "human_reviewed": False},
                )
            messages = {
                "ready_for_review": "申请页面已填写完成，请到原申请网站确认并最终提交。",
                "needs_input": "申请页面需要补充已有信息库中没有的事实。",
                "needs_recheck": "申请页面动作结果未明，已停止自动操作，请复核原页。",
                "cancelled": "原申请任务已取消，自动流程已停止。",
            }
            self._stop(state, job["status"], takeover or messages[job["status"]])
            return
        if current["control"] != "running":
            self._stop(state, "needs_recheck", "填写已暂停，保留原页；不会自动重放。")
            return
        if state.get("worker_runtime_id") is None and runtime_id:
            state["worker_runtime_id"] = runtime_id
            self._save(state)
        if time.time() - state.get("last_heartbeat", 0) >= 4:
            self.flow.worker_action(
                task["id"], task["revision"], "heartbeat", {"controller": state["controller"]}
            )
            state["last_heartbeat"] = time.time()
            self._save(state)

    def _request_takeover(self, state, task, job, runtime_id, current):
        """True while this job's one system takeover runs; an error message keeps its reason.

        Missing facts and a switched-off takeover have no candidate, so the ordinary
        needs_recheck stop applies; a recorded capability failure or a takeover that is
        on but could not be configured keeps its own reason.
        """
        if self._takeover_live((state.get("takeover_request") or {}).get("request_id"), job):
            return True
        assistance = job.get("assistance") or {}
        reader = getattr(self.worker, "takeover_candidate", None)
        if reader is None:
            return None
        expected = {
            "expected_batch_id": state["worker_batch_id"],
            "expected_run_id": runtime_id,
            "expected_task_id": task["id"],
        }
        try:
            blocker = reader(task["application_id"], **expected)
            failed = (assistance.get("dispatch") or {}).get("failed_code")
            if blocker is None and failed and job.get("reason") == failed:
                # A capability failure is not retried; its own reason stays visible.
                return f"Codex 接管暂不可用（{failed}），已保留原页与资料；不会自动重试。"
            if (
                blocker is None
                and self.takeover_unavailable_reason
                and reader(task["application_id"], **expected, hypothetical=True) is not None
            ):
                # The configuration is fixed at startup, like every App setting.
                return (
                    f"自动接管不可用：{self.takeover_unavailable_reason}。"
                    "已保留原页与资料；处理后重新打开工作台，再点一次 Continue 继续。"
                )
            if blocker is None:
                return None
            key = {k: v for k, v in blocker.items() if k != "observed_at"}
            # One request per blocker, explicit Continue and takeover slot; a repeat
            # is idempotent, while a slot after a released checkpoint gets a new id.
            # The takeover record trims settled history (2026-11-02), so its length
            # alone no longer separates slots; the record's generation counter does.
            generation = job.get("assistance_generation", 0)
            key.update(
                resume_serial=current.get("resume_serial", 0),
                previous=assistance.get("id"),
                history=len(job.get("assistance_history", [])),
                **({"generation": generation} if generation else {}),
            )
            request_id = "takeover-" + digest(key)[:32]
            state["takeover_request"] = {
                "request_id": request_id,
                "blocker": blocker,
                "at": time.time(),
            }
            # Publish the fixed request before the Worker reserves the writer.
            self._save(state)
            receipt = self.worker.request_takeover(
                task["application_id"],
                **expected,
                blocker=blocker,
                request_id=request_id,
            )
            live = next(
                (
                    row
                    for row in self.worker.snapshot().get("jobs", [])
                    if row["application_id"] == task["application_id"]
                ),
                {},
            )
            if receipt["dispatch"]["request_id"] != request_id or not self._takeover_live(
                request_id, live
            ):
                # Never report a released or stopped record as a running takeover.
                raise PortalDataError(
                    "assistance_takeover_unavailable",
                    "接管请求没有建立新的操作范围，保留原页。",
                    409,
                )
        except PortalDataError as error:
            if state.get("takeover_request"):
                state["takeover_request"]["error_code"] = error.code
            return str(error)
        # The App accepts notifications only on waits, so a running takeover is
        # described on its request and the notification stays empty.
        state["takeover_request"].update(
            title="已交给 Codex 接续", message="已自动交给 Codex 接续原页"
        )
        state["notification"] = None
        self._save(state)
        return True

    def _notice(self, state):
        """The page notice: the wait notification, else a takeover only while it holds the job."""
        notification = state.get("notification")
        if notification:
            return {
                "kind": "wait",
                "title": notification.get("title"),
                "message": notification.get("message"),
            }
        request = state.get("takeover_request") or {}
        if not request.get("title") or self.worker is None:
            return None
        application_id = next(
            (
                item.get("application_id")
                for item in state["items"]
                if item.get("task_id") == state.get("active_task_id")
            ),
            None,
        )
        try:
            job = next(
                (
                    row
                    for row in self.worker.snapshot().get("jobs", [])
                    if row["application_id"] == application_id
                ),
                {},
            )
            live = self._takeover_live(request.get("request_id"), job)
        except (OSError, ValueError, TypeError, KeyError, PortalDataError, helper.StoreError):
            live = False
        return (
            {"kind": "takeover", "title": request["title"], "message": request["message"]}
            if live
            else None
        )

    @staticmethod
    def _takeover_live(request_id, job):
        """This request's takeover still holds the job: claimed, or a finished turn returning."""
        assistance = job.get("assistance") or {}
        dispatch = assistance.get("dispatch") or {}
        stop = assistance.get("stop")
        return bool(
            request_id
            and dispatch.get("request_id") == request_id
            and job.get("reason") == dispatch["blocker"]["code"]
            and "failed_code" not in dispatch
            and "superseded" not in assistance
            and "outcome" not in assistance
            and (
                assistance["status"] in {"requested", "claimed"}
                and stop is None
                or (stop or {}).get("reason") == "native_turn_completed"
            )
        )

    def _begin_backend_recovery(self, state, task, runtime_id):
        candidate_reader = getattr(self.worker, "backend_recovery_candidate", None)
        if candidate_reader is None:
            return False
        candidate = candidate_reader(
            task["application_id"],
            expected_batch_id=state["worker_batch_id"],
            expected_run_id=runtime_id,
            expected_task_id=task["id"],
        )
        if candidate is None:
            return False
        request = state.get("backend_recovery_request")
        if not request or digest(request.get("candidate")) != digest(candidate):
            request = {
                "request_id": candidate.get("recovery_request_id") or uuid4().hex,
                "candidate": candidate,
            }
            state["backend_recovery_request"] = request
            # Publish the fixed request before asking the original Worker to act.
            self._save(state)
        receipt = self.worker.request_backend_recovery(
            task["application_id"],
            pipeline_id=state["id"],
            expected_batch_id=state["worker_batch_id"],
            expected_run_id=runtime_id,
            expected_task_id=task["id"],
            expected_assistance_ref=candidate["assistance_ref"],
            request_id=request["request_id"],
        )
        state.update(status="recovering_worker", backend_recovery_id=receipt["request_id"])
        self._save(state)
        self._recover_worker(state)
        return True

    def _recover_worker(self, state):
        receipt = self.worker.recover_backend(state.get("backend_recovery_id"), state["id"])
        if receipt is None or receipt["status"] in {"cancelled", "needs_recheck"}:
            self._stop(state, "needs_recheck", "原运行尚未核验，保留原页和现有进度。")
        elif receipt["status"] == "verified":
            state.update(status="filling", control="running", worker_runtime_id=receipt["run_id"])
            self._save(state)

    def close(self):
        with self._guard:
            if self._owner and not self._closed.is_set():
                try:
                    state = self._load()
                    receipt = None
                    if (
                        state.get("queue_mode")
                        and state["control"] == "running"
                        and state["status"] in {"filling", "recovering_worker"}
                        and hasattr(self.worker, "suspend_backend")
                    ):
                        receipt = self.worker.suspend_backend(
                            pipeline_id=state["id"],
                            controller=state.get("controller"),
                            batch_id=state.get("worker_batch_id"),
                            application_id=self._task(state)["application_id"],
                        )
                    if receipt:
                        state.update(
                            status="recovering_worker", backend_recovery_id=receipt["request_id"]
                        )
                        self._save(state)
                    elif state["status"] != "recovering_worker":
                        self._pause_owned_worker(state)
                    if (
                        not receipt
                        and state["status"] != "recovering_worker"
                        and state["control"] == "running"
                        and (not state.get("queue_mode") or state.get("worker_batch_id"))
                    ):
                        self._stop(
                            state, "interrupted", "App 已关闭，自动流程保持暂停并保留原进度。"
                        )
                finally:
                    self._closed.set()
            else:
                self._closed.set()
        if self._thread is not None:
            self._thread.join(timeout=0.5)
        if self._thread is None or not self._thread.is_alive():
            self._lock_file.close()
