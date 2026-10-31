"""Private single-job stage orchestration; browser progress stays in the worker."""

from __future__ import annotations

import fcntl
import hashlib
import queue
import re
import threading
import time
from contextlib import contextmanager, nullcontext
from contextvars import ContextVar
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

from ._vendor import job_apply_store as helper
from .application_information import COUNTRIES
from .application_storage import private_root
from .career_portal_data import ApplicationStore, PortalDataError
from .validation.hashing import record_digest as digest

_PIPELINE_HTTP_ENTRY = ContextVar("pipeline_http_entry", default=None)


@contextmanager
def pipeline_http_entry(flow, checker):
    """Carry an HTTP admission check to the actual locked Flow mutation."""
    token = _PIPELINE_HTTP_ENTRY.set((flow, checker))
    try:
        yield
    finally:
        _PIPELINE_HTTP_ENTRY.reset(token)


def _analysis_has_no_outputs(task):
    """A failure cannot be a fresh rejection after content or external work."""
    return bool(
        task.get("artifacts") == []
        and task.get("materials_confirmed") is False
        and all(
            task.get(key) is None
            for key in (
                "analysis_id",
                "resume_id",
                "resume_sha256",
                "draft_id",
                "draft_sha256",
                "worker_ref",
                "send_approval",
                "worker_preparation",
                "material_binding",
                "material_acceptance",
            )
        )
        and all(
            value == {"status": "pending"}
            for name, value in task.get("stages", {}).items()
            if name != "analysis"
        )
    )


def legacy_analysis_failure(task):
    """Only a rejected internal analysis with no adopted output can be skipped."""
    stages = task.get("stages")
    if not isinstance(stages, dict) or not isinstance(stages.get("analysis"), dict):
        return False
    stage = stages["analysis"]
    return bool(
        task.get("status") == "failed"
        and stage.get("status") == "failed"
        and stage.get("error_code")
        in {
            "match_model_invalid",
            "match_requirement_conflict",
            "match_source_invalid",
            "match_attribution_invalid",
        }
        and isinstance(stage.get("attempt_id"), str)
        and re.fullmatch(r"[a-f0-9]{32}", stage["attempt_id"])
        and set(stage) == {"status", "error_code", "attempt_id"}
        and _analysis_has_no_outputs(task)
    )


def _analysis_outcome(task, *, known_attempt_failure=False):
    """Interpret Flow-owned attempt metadata without authorizing a new attempt."""
    stage = task.get("stages", {}).get("analysis", {})
    legacy_skippable = legacy_analysis_failure(task)
    # The legacy skip policy keeps its original code and exact field set.
    # Modern validation failures only classify a same-job input wait.
    # retrieval_execution_incomplete also wraps reader timeouts; its code alone
    # cannot establish a known rejected result. Only the saved attempt can prove
    # it ended without an unknown model result, whatever code the stage recorded.
    modern_rejected = bool(
        task.get("status") == stage.get("status") == "failed"
        and stage.get("error_code")
        in {
            *([stage.get("error_code")] if known_attempt_failure else []),
            "match_model_invalid",
            "match_requirement_conflict",
            "match_source_invalid",
            "match_attribution_invalid",
            "match_inference_invalid",
            "retrieval_invalid",
            "job_brief_invalid",
            # A refused recovery calls nothing; the next attempt re-checks the records.
            "match_resume_invalid",
        }
        and isinstance(stage.get("attempt_id"), str)
        and re.fullmatch(r"[a-f0-9]{32}", stage["attempt_id"])
        and isinstance(stage.get("analysis_input_revision"), str)
        and re.fullmatch(r"[a-f0-9]{64}", stage["analysis_input_revision"])
        and set(stage)
        <= {
            "status",
            "error_code",
            "attempt_id",
            "analysis_input_revision",
            "resume_from_attempt_id",
        }
        and (
            "resume_from_attempt_id" not in stage
            or isinstance(stage["resume_from_attempt_id"], str)
            and re.fullmatch(r"[a-f0-9]{32}", stage["resume_from_attempt_id"])
        )
        and _analysis_has_no_outputs(task)
    )
    internal_only = not any(
        task.get(key)
        for key in (
            "codex_handoff_ref",
            "codex_handoff_attempt",
            "material_update",
            "material_binding_error",
            "export_recoveries",
        )
    ) and task.get("group_read", {}).get("status") not in {"running", "needs_recheck"}
    status, recovery = "unknown", "needs_recheck"
    if (legacy_skippable or modern_rejected) and internal_only:
        status, recovery = "rejected", "needs_input"
    elif task.get("status") == "draft" and stage.get("status") == "pending":
        status, recovery = "pending", "wait"
    elif (
        task.get("status") == "stale"
        and task.get("input_epoch", 0) > 0
        and task.get("materials_confirmed") is False
        and all(value == {"status": "pending"} for value in task["stages"].values())
        and all(
            task.get(key) is None
            for key in (
                "analysis_id",
                "resume_id",
                "resume_sha256",
                "draft_id",
                "draft_sha256",
                "worker_ref",
                "cover_letter",
            )
        )
    ):
        # Application-mode input updates retain "stale" and old artifacts, but
        # explicitly clear every current stage and output before a fresh analysis.
        status, recovery = "pending", "wait"
    elif task.get("status") == "analyzing" and stage.get("status") in {"queued", "running"}:
        status, recovery = "running", "wait"
    elif task.get("status") == "analysis_ready" and stage.get("status") == "complete":
        from .application_explanations import adopted_analysis

        if adopted_analysis(task) is not None:
            status, recovery = "ready", "continue"
    return {
        "schema_version": "analysis-outcome/v1",
        "task_id": task["id"],
        "task_revision": task["revision"],
        "status": status,
        "error_code": stage.get("error_code"),
        "attempt_id": stage.get("attempt_id"),
        "recovery": recovery,
        "legacy_skippable": legacy_skippable,
    }


def _preparation_request_replayed(task, request_id, expected_attempt_id=None):
    if request_id is None:
        return False
    if not isinstance(request_id, str) or not 1 <= len(request_id) <= 100:
        raise PortalDataError("invalid_request", "继续请求缺少有效标识。", 400)
    attempts = [
        row for row in task.get("preparation_attempts", []) if row["request_id"] == request_id
    ]
    if not attempts:
        return False
    if any(
        row["inputs"] != task["inputs"]
        or row["job_binding"] != task["job_binding"]
        or row["input_epoch"] != task.get("input_epoch", 0)
        for row in attempts
    ) or (
        expected_attempt_id is not None
        and not any(row["previous_attempt_id"] == expected_attempt_id for row in attempts)
    ):
        raise PortalDataError(
            "flow_preparation_request_conflict",
            "此继续请求已绑定其他准备输入或尝试。",
            409,
        )
    return True


def _record_preparation_attempt(task, stage, attempt_id, previous_attempt_id, request_id):
    """Retain actual reservations; current stage records remain the lifecycle authority."""
    if request_id is not None:
        task.setdefault("preparation_attempts", []).append(
            {
                "stage": stage,
                "attempt_id": attempt_id,
                "previous_attempt_id": previous_attempt_id,
                "request_id": request_id,
                "inputs": deepcopy(task["inputs"]),
                "job_binding": task["job_binding"],
                "input_epoch": task.get("input_epoch", 0),
            }
        )


def _preparation_progress(task, analysis):
    """Project saved preparation only; an execution status cannot overwrite it."""
    resume = deepcopy(task.get("stages", {}).get("resume", {"status": "pending"}))
    export = deepcopy(task.get("stages", {}).get("export", {"status": "pending"}))
    letter = deepcopy(task.get("cover_letter") or {"status": "not_started"})
    consistency = deepcopy(task.get("material_consistency") or {"status": "not_started"})
    update = task.get("material_update") or {"status": "not_started"}
    material_update = {
        key: deepcopy(update[key])
        for key in ("id", "status", "error_code", "error_message")
        if key in update
    }
    if update.get("candidate"):
        material_update["candidate"] = {
            key: deepcopy(update["candidate"][key])
            for key in (
                "draft_id",
                "draft_sha256",
                "resume_id",
                "resume_sha256",
                "stages",
                "cover_letter",
                "material_consistency",
            )
            if key in update["candidate"]
        }
    update_pending = bool(task.get("material_update")) and update.get("status") != "complete"
    analysis = deepcopy(analysis)
    if task.get("analysis_id") and any(
        row.get("stage") == "analysis"
        and row.get("adopted")
        and row.get("result", {}).get("id") == task["analysis_id"]
        for row in task.get("artifacts", [])
    ):
        analysis.update(status="ready", recovery="continue")
    phase = (
        "materials"
        if analysis["status"] == "ready" or task.get("origin") == "existing_latex"
        else "analysis"
    )
    status, reason, message = "not_started", None, None
    continuation = None
    available = bool(task.get("resume_id") and task.get("resume_sha256"))
    material_ready = (
        available
        and not update_pending
        and (
            task["status"] in {"resume_ready", "materials_ready"}
            or task.get("worker_ref")
            and resume.get("status") == "complete"
            and export.get("status") in {"pending", "complete"}
        )
        and not any(
            part.get("status") in {"queued", "running", "failed", "needs_recheck"}
            for part in (resume, export)
        )
    )
    if task["status"] == "cancelled":
        status, reason = "cancelled", "preparation_cancelled"
    elif update_pending:
        status, reason = {
            "staged": ("waiting", "material_update_pending"),
            "preparing": ("running", None),
            "awaiting_page": ("waiting", "material_page_update_required"),
            "committing": ("running", None),
            "bound": ("waiting", "material_page_update_required"),
        }.get(update.get("status"), ("needs_recheck", "material_update_unknown"))
        message = update.get("error_message")
    elif phase == "analysis":
        status = {"pending": "not_started", "running": "running", "rejected": "waiting"}.get(
            analysis["status"], "needs_recheck"
        )
        if status in {"waiting", "needs_recheck"}:
            reason = "analysis_input_required" if status == "waiting" else "analysis_result_unknown"
    elif resume.get("status") == "needs_recheck" or export.get("status") == "needs_recheck":
        status, reason = "needs_recheck", "material_result_unknown"
    elif letter["status"] == "needs_recheck":
        status, reason = "needs_recheck", "cover_letter_result_unknown"
    elif consistency["status"] in {"conflict", "failed", "needs_recheck"}:
        status = "needs_recheck" if consistency["status"] == "needs_recheck" else "waiting"
        reason = "material_consistency_required"
    elif resume.get("status") == "failed" and resume.get("error_code") in {
        "resume_author_material_required",
        "resume_author_failed",
    }:
        status, reason = "waiting", "resume_author_input_required"
        message = "简历写作需要处理对应经历，已保留完成片段和原稿。"
        if resume["error_code"] == "resume_author_failed":
            continuation = {"task_id": task["id"], "attempt_id": resume.get("attempt_id")}
    elif export.get("status") == "failed" or (
        resume.get("status") == "failed" and resume.get("error_code") != "resume_author_paused"
    ):
        status, reason = "failed", "material_result_unknown"
    elif task.get("experience_handoff") and task["status"] == "needs_input":
        status, reason = "running", "codex_resume_required"
    elif any(
        part.get("status") in {"queued", "running"}
        for part in (resume, export, letter, consistency)
    ) or task["status"] in {"resume_generating", "exporting"}:
        status = "running"
    elif material_ready:
        status = "ready"
    elif (
        task["status"] in {"analysis_ready", "draft_ready"}
        or resume.get("error_code") == "resume_author_paused"
    ):
        status = "not_started"
    else:
        status, reason = "needs_recheck", "material_result_unknown"
    return {
        "task_id": task["id"],
        "task_revision": task["revision"],
        "status": status,
        "phase": phase,
        "wait_reason": reason,
        "message": message,
        "analysis": analysis,
        "resume": resume,
        "export": export,
        "cover_letter": letter,
        "material_consistency": consistency,
        "material_update": material_update,
        "can_prepare_execution": bool(material_ready) and status in {"ready", "running"},
        "continuation": continuation,
        "can_continue": continuation is not None
        or task["status"]
        in {"resume_generating", "draft_ready", "resume_ready", "materials_ready"},
        "execution_ref": deepcopy(task.get("worker_ref")),
        "task": deepcopy(task),
    }


def job_input_revision(application: dict) -> str:
    """Bind the complete JD and job fields without unrelated application notes."""
    return digest(
        {
            key: application.get(key, "")
            for key in ("company", "role_title", "location", "job_description")
        }
    )


def analysis_input_binding(inputs):
    """Keep documentary analysis independent of contact and material-only inputs."""
    material_keys = {
        "resume_configuration_revision",
        "qualification_information_revision",
        "presentation_feedback_revision",
    }
    if "information_library_root" in inputs:
        # Canonical bindings identify the contact projection and its source root.
        # Legacy unscoped library revisions may include qualification facts.
        material_keys |= {"information_library_revision", "information_library_root"}
    return {key: value for key, value in inputs.items() if key not in material_keys}


def retained_configuration_inputs(task, inputs, *, completed_stages=None):
    """Keep completed results bound to the configuration that produced them."""
    resolved = deepcopy(inputs)
    from .application_existing_materials import retained_presentation_input

    retained_presentation_input(task, resolved)
    if "qualification_information_revision" in task["inputs"]:
        # Preserve the historical receipt bytes from the former over-broad binding.
        # Current qualification facts are checked live, not as PDF/analysis inputs.
        resolved["qualification_information_revision"] = task["inputs"][
            "qualification_information_revision"
        ]
    if completed_stages is None:
        completed_stages = {
            key
            for key, value in task.get("stages", {}).items()
            if value.get("status") == "complete"
        }
    if (
        "resume" in completed_stages
        and "information_library_revision" not in task["inputs"]
        and isinstance(task.get("resume_id"), str)
        and bool(task["resume_id"])
        and isinstance(task.get("resume_sha256"), str)
        and re.fullmatch(r"[a-f0-9]{64}", task["resume_sha256"]) is not None
        and not task.get("export_recoveries")
        and task.get("group_read", {}).get("status") not in {"running", "needs_recheck"}
        and not any(
            stage.get("status") in {"queued", "running", "needs_recheck"}
            for stage in task.get("stages", {}).values()
        )
    ):
        # Only known completed PDF bytes can predate this binding. Imported drafts
        # and unknown exports must still compare every newly observed fact input.
        resolved.pop("information_library_revision", None)
        resolved.pop("information_library_root", None)
    configuration_keys = {
        "account_context_revision",
        "analysis_configuration_revision",
        "resume_configuration_revision",
        "historical_benchmark_revision",
    }
    unchanged = {k: v for k, v in resolved.items() if k not in configuration_keys} == {
        k: v for k, v in task["inputs"].items() if k not in configuration_keys
    }
    analysis_unchanged = {
        k: v for k, v in analysis_input_binding(resolved).items() if k not in configuration_keys
    } == {
        k: v
        for k, v in analysis_input_binding(task["inputs"]).items()
        if k not in configuration_keys
    }
    for stage in ("analysis", "resume"):
        if stage in completed_stages and (unchanged or stage == "analysis" and analysis_unchanged):
            keys = (f"{stage}_configuration_revision",)
            if stage == "analysis":
                # Local credential refreshes are operational changes, not changes
                # to the JD, applicant facts or already generated content.
                keys += ("historical_benchmark_revision", "account_context_revision")
            for key in keys:
                if key in task["inputs"]:
                    resolved[key] = task["inputs"][key]
                else:
                    resolved.pop(key, None)
    return resolved


def qualification_status(requirements, conditions):
    """Aggregate effective child facts using the retained original group relation."""
    if any("scoring_framework" in row for row in requirements):
        from .application_match_scoring import calculate_match_score

        effective = deepcopy(requirements)
        for condition in conditions:
            effective[condition["requirement_index"]]["judgment"] = {
                "supported": "supported",
                "conflict": "gap",
                "needs_input": "unknown",
            }[condition["status"]]
        return calculate_match_score(effective)["eligibility"]
    statuses = {row["status"] for row in conditions}
    return (
        "conflict"
        if "conflict" in statuses
        else "needs_input"
        if "needs_input" in statuses
        else "supported"
        if conditions
        else "not_specified"
    )


def task_eligibility(task: dict, *, bind_inputs=False) -> dict:
    """Keep applicant clarifications separate from the documentary match score."""
    analysis = next(
        (
            row["result"]
            for row in reversed(task.get("artifacts", []))
            if row.get("stage") == "analysis"
            and row.get("adopted")
            and row.get("result", {}).get("id") == task.get("analysis_id")
        ),
        None,
    )
    if analysis is None:
        return {"status": "analysis_required", "conditions": []}
    conditions = []
    analysis_revisions = set()
    if bind_inputs:
        projection = analysis_input_binding(task["inputs"])
        analysis_revisions.add(digest(projection))
        if "qualification_information_revision" in task["inputs"]:
            analysis_revisions.add(
                digest(
                    projection
                    | {
                        "qualification_information_revision": task["inputs"][
                            "qualification_information_revision"
                        ]
                    }
                )
            )
    for index, requirement in enumerate(analysis.get("requirements", [])):
        if not requirement.get("hard_condition"):
            continue
        resolution = next(
            (
                row
                for row in reversed(task.get("hard_condition_resolutions", []))
                if row.get("analysis_id") == task["analysis_id"]
                and type(row.get("requirement_index")) is int
                and row["requirement_index"] == index
                and row.get("confirmed") is True
                and row.get("verified_by") == "user"
                and type(row.get("eligible")) is bool
                and isinstance(row.get("source"), str)
                and bool(row["source"].strip())
                and (
                    not bind_inputs
                    or (
                        row["analysis_input_revision"] in analysis_revisions
                        if "analysis_input_revision" in row
                        else row.get("input_revision")
                        == digest(
                            {
                                k: v
                                for k, v in task["inputs"].items()
                                if k != "resume_configuration_revision"
                            }
                        )
                    )
                )
            ),
            None,
        )
        judgment = requirement.get("judgment")
        status = (
            "conflict"
            if judgment == "gap"
            else ("supported" if resolution["eligible"] else "conflict")
            if resolution
            else "supported"
            if judgment == "supported"
            else "needs_input"
        )
        conditions.append(
            {
                "requirement_index": index,
                "text": requirement["text"],
                "judgment": judgment,
                "status": status,
                "resolution": deepcopy(resolution),
            }
        )
    return {
        "status": qualification_status(analysis.get("requirements", []), conditions),
        "conditions": conditions,
    }


def local_materials(task):
    """Compatibility entry for the Resume-owned material contract projection."""
    from .application_resume import local_materials as material_contract

    return material_contract(task)


def retire_local_materials(task):
    keys = ("material_version_contract", "prism_edit", "material_source_state", "prism_capture")
    if any(key in task for key in keys):
        task.setdefault("material_version_history", []).append(
            {key: deepcopy(task.get(key)) for key in (*keys, "draft_id", "resume_id", "inputs")}
        )
        for key in keys:
            task.pop(key, None)


def _material_pending(task):
    return bool(
        task.get("material_binding_error")
        or task.get("export_recoveries")
        or task.get("group_read", {}).get("status") in {"running", "needs_recheck"}
        or any(
            stage["status"] in {"queued", "running", "failed", "needs_recheck"}
            for stage in task.get("stages", {}).values()
        )
        or task.get("material_update", {}).get("status") not in {None, "complete"}
    )


def stat_tokens(paths):
    """File identity tokens that detect a change between two reads without a scan lock."""
    tokens = []
    for path in sorted(paths):
        try:
            meta = path.lstat()
            tokens.append(
                (
                    str(path),
                    meta.st_dev,
                    meta.st_ino,
                    meta.st_size,
                    meta.st_mtime_ns,
                    meta.st_ctime_ns,
                )
            )
        except FileNotFoundError:
            tokens.append((str(path), None))
    return tokens


def latest_preparation_task(tasks, application_id=None):
    """Keep settled cancellations in history without superseding current work."""
    return next(
        (
            row
            for row in reversed(tasks)
            if (application_id is None or row["application_id"] == application_id)
            and (
                row["status"] != "cancelled"
                or row.get("worker_ref")
                or row.get("codex_handoff_ref")
                or row.get("codex_handoff_attempt")
                or row.get("material_binding_error")
                or row.get("material_update", {}).get("status") not in {None, "complete"}
                or row.get("export_recoveries")
                or row.get("group_read", {}).get("status") in {"running", "needs_recheck"}
                or row.get("worker_preparation", {}).get("status") == "pending"
                or any(
                    item["status"] in {"queued", "running", "needs_recheck"}
                    for item in row["stages"].values()
                )
            )
        ),
        None,
    )


def material_task_view(task):
    """Read material facts, recognizing only identifiable old page-status copies."""
    if not isinstance(task, dict):
        return task
    view = deepcopy(task)
    if task.get("status") in {"cancelled", "failed", "stale", "export_failed"}:
        return view
    if _material_pending(task):
        view["status"] = "needs_recheck"
        return view
    reference = task.get("worker_ref") or {}
    if not isinstance(reference, dict):
        return view
    legacy_page = (
        task.get("status") in {"queued", "filling", "needs_input", "ready_for_review"}
        and task["status"] == reference.get("status")
    ) or (
        task.get("status") == "needs_recheck"
        and task.get("reason") == "flow_restarted"
        and reference.get("status") == "filling"
    )
    if (
        legacy_page
        and isinstance(reference.get("batch_id"), str)
        and reference["batch_id"]
        and reference.get("job_id") == task.get("application_id")
        and task.get("materials_confirmed") is True
        and isinstance(task.get("resume_id"), str)
        and re.fullmatch(r"[a-f0-9]{32}", task["resume_id"]) is not None
        and isinstance(task.get("resume_sha256"), str)
        and re.fullmatch(r"[a-f0-9]{64}", task["resume_sha256"]) is not None
        and task.get("stages")
        and all(stage["status"] == "complete" for stage in task["stages"].values())
    ):
        # The saved revision and bytes remain the existing material identity.
        view["status"] = "materials_ready"
    return view


class ApplicationFlowService:
    """One job runner, with independently retained authors for the current job."""

    def __init__(
        self,
        applications: ApplicationStore,
        root: Path,
        *,
        callbacks=None,
        input_provider=None,
        information_provider=None,
        information_library_root: Path | None = None,
        recheck_source_provider=None,
        preparation_only=False,
    ):
        self.applications = applications
        self.root = private_root(root)
        if self.root.is_relative_to(applications.root) or applications.root.is_relative_to(
            self.root
        ):
            raise PortalDataError("flow_root_conflict", "任务目录与投递记录目录须独立。", 409)
        self.path = self.root / "flow.json"
        self.callbacks = dict(callbacks or {})
        self.input_provider = input_provider
        self.information_provider = information_provider
        self.information_library_root = information_library_root
        self.recheck_source_provider = recheck_source_provider
        self.preparation_only = preparation_only
        from .application_material_batch import MaterialBatch

        self.material_batch = MaterialBatch(self) if preparation_only else None
        self._closed = threading.Event()
        self._runtime_error = ""
        self._owner_guard = threading.Lock()
        self._queue = queue.Queue()
        self._running_stage_task_id = None
        self._letter_threads = {}
        lock_path = self.root / ".flow.lock"
        if lock_path.is_symlink():
            raise PortalDataError("flow_invalid", "任务锁不能使用符号链接。", 409)
        self._lock_file = lock_path.open("a")
        try:
            fcntl.flock(self._lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
            self._owner = True
        except BlockingIOError:
            self._owner = False
        try:
            with applications.write_lock():
                if not self.path.exists():
                    self._save(
                        {
                            "schemaVersion": 1,
                            **({"mode": "preparation"} if preparation_only else {}),
                            "applications_root": str(applications.root),
                            "tasks": [],
                        }
                    )
                else:
                    self._load()
                if self._owner:
                    self._recover()
        except BaseException:
            self._lock_file.close()
            raise
        self._thread = None
        if self._owner:
            self._thread = threading.Thread(target=self._run, name="application-flow", daemon=True)
            self._thread.start()

    def _load(self):
        if self.path.is_symlink():
            raise PortalDataError("flow_invalid", "任务快照不能使用符号链接。", 409)
        try:
            state = helper.read_json_object(self.path, "application flow")
            valid = (
                state["schemaVersion"] == 1
                and state["applications_root"] == str(self.applications.root)
                and isinstance(state["tasks"], list)
                and isinstance(state.get("manual_order", []), list)
                and all(isinstance(item, str) and item for item in state.get("manual_order", []))
                and len(set(state.get("manual_order", []))) == len(state.get("manual_order", []))
                and all(
                    re.fullmatch(r"[a-f0-9]{32}", task["id"])
                    and task["status"]
                    in {
                        "draft",
                        "analyzing",
                        "analysis_ready",
                        "resume_generating",
                        "resume_ready",
                        "draft_ready",
                        "exporting",
                        "export_failed",
                        "materials_ready",
                        "failed",
                        "cancelled",
                        "stale",
                        "queued",
                        "filling",
                        "needs_input",
                        "needs_recheck",
                        "ready_for_review",
                    }
                    and (
                        set(task["stages"]) == {"analysis", "resume"}
                        or (self.preparation_only or task.get("automatic_materials") is True)
                        and set(task["stages"]) == {"analysis", "resume", "export"}
                    )
                    and all(
                        stage["status"]
                        in {
                            "pending",
                            "queued",
                            "running",
                            "complete",
                            "failed",
                            "cancelled",
                            "needs_recheck",
                        }
                        for stage in task["stages"].values()
                    )
                    and isinstance(task["inputs"], dict)
                    and type(task.get("input_epoch", 0)) is int
                    and task.get("input_epoch", 0) >= 0
                    and isinstance(task["artifacts"], list)
                    and isinstance(task.get("recovery_history", []), list)
                    and isinstance(task.get("export_recoveries", []), list)
                    and all(
                        isinstance(record, dict)
                        and record.get("status") == "needs_recheck"
                        and record.get("operation_kind") == "reuse_completed_review"
                        and isinstance(record.get("prior_export_stage"), dict)
                        and record["prior_export_stage"].get("status") == "needs_recheck"
                        for record in task.get("export_recoveries", [])
                    )
                    and all(
                        isinstance(record, dict)
                        and record["stage"] in {"analysis", "resume", "export"}
                        and record["previous_status"] in {"queued", "running"}
                        and record["status"] in {"failed", "needs_recheck"}
                        and isinstance(record["reason"], str)
                        and bool(record["reason"])
                        and (
                            record["attempt_id"] is None
                            or isinstance(record["attempt_id"], str)
                            and bool(record["attempt_id"])
                        )
                        and type(record["input_epoch"]) is int
                        and 0 <= record["input_epoch"] <= task.get("input_epoch", 0)
                        and isinstance(record["inputs_revision"], str)
                        and re.fullmatch(r"[a-f0-9]{64}", record["inputs_revision"]) is not None
                        and isinstance(record["job_binding"], str)
                        and re.fullmatch(r"[a-f0-9]{64}", record["job_binding"]) is not None
                        and type(record["at"]) in {int, float}
                        and 0 <= record["at"] < float("inf")
                        for record in task.get("recovery_history", [])
                    )
                    and isinstance(task["materials_confirmed"], bool)
                    and self.valid_material_acceptance(task)
                    and task["revision"]
                    == digest({k: v for k, v in task.items() if k != "revision"})
                    for task in state["tasks"]
                )
            )
        except (OSError, ValueError, KeyError, TypeError, helper.StoreError) as exc:
            raise PortalDataError("flow_invalid", "任务快照不能核验，请保留原件。", 409) from exc
        if not valid:
            raise PortalDataError("flow_invalid", "任务快照不能核验，请保留原件。", 409)
        expected_mode = "preparation" if self.preparation_only else "application"
        if state.get("mode", "application") != expected_mode:
            raise PortalDataError(
                "flow_mode_mismatch", "准备任务与原申请须使用独立目录，请保留原记录。", 409
            )
        if self.material_batch:
            self.material_batch.validate(state)
        return state

    def adopted_artifact(self, stage, identifier, *, kind=None):
        """Read an isolated historical result without projecting current inputs."""
        with self.applications.write_lock():
            return deepcopy(
                next(
                    (
                        artifact["result"]
                        for task in self._load()["tasks"]
                        for artifact in task["artifacts"]
                        if artifact.get("adopted")
                        and artifact.get("stage") == stage
                        and (kind is None or artifact.get("result", {}).get("kind") == kind)
                        and artifact.get("result", {}).get("id") == identifier
                    ),
                    None,
                )
            )

    def _save(self, state):
        if self.material_batch:
            self.material_batch.seal(state)
        records = [("snapshots", task) for task in state["tasks"]]
        if state.get("preparation_batch"):
            records.append(("batch-snapshots", state["preparation_batch"]))
        for folder, task in records:
            binding = task.get("material_binding")
            if binding and (
                not task["materials_confirmed"]
                or binding.get("resume_id") != task.get("resume_id")
                or binding.get("pdf_sha256") != task.get("resume_sha256")
                or binding.get("input_revision") != digest(task["inputs"])
            ):
                task.pop("material_binding")
            task["revision"] = digest({k: v for k, v in task.items() if k != "revision"})
            directory = self.root / folder / task["id"]
            if any(path.is_symlink() for path in (directory.parent, directory)):
                raise PortalDataError("flow_invalid", "历史任务目录不能使用符号链接。", 409)
            path = directory / f"{task['revision']}.json"
            if path.is_symlink():
                raise PortalDataError("flow_invalid", "历史任务快照不能使用符号链接。", 409)
            if not path.exists():
                helper.atomic_write_json(path, task)
            elif helper.read_json_object(path, "historical application flow") != task:
                raise PortalDataError("flow_invalid", "历史任务快照不能核验，请保留原件。", 409)
        helper.atomic_write_json(self.path, state)

    def _recover(self, reason="flow_interrupted"):
        state = self._load()
        changed = self.material_batch.recover(state) if self.material_batch else False
        for task in state["tasks"]:
            letter = task.get("cover_letter") or {}
            if letter.get("status") in {"queued", "running"}:
                letter.update(
                    status="failed" if letter["status"] == "queued" else "needs_recheck",
                    error_code="letter_not_started"
                    if letter["status"] == "queued"
                    else "letter_generation_interrupted",
                )
                changed = True
            consistency = task.get("material_consistency") or {}
            if consistency.get("status") in {"queued", "running"}:
                consistency.update(
                    status="failed" if consistency["status"] == "queued" else "needs_recheck",
                    error_code="material_consistency_not_started"
                    if consistency["status"] == "queued"
                    else "material_consistency_interrupted",
                )
                changed = True
            if task.get("prism_edit", {}).get("opening"):
                task["prism_edit"].update(status="open_failed", opening=False)
                task["material_source_state"] = "open_failed"
                changed = True
            update = task.get("material_update") or {}
            if update.get("status") == "preparing":
                update.update(
                    status="needs_recheck", error_code="bound_material_preparation_interrupted"
                )
                changed = True
            if (
                (self.preparation_only or task.get("automatic_materials"))
                and task.get("origin") != "existing_latex"
                and task["status"] == "resume_ready"
                and not task["materials_confirmed"]
                and task["stages"].get("export", {}).get("status") == "complete"
            ):
                # A saved PDF is not proof that its automatic binding completed.
                task.update(status="needs_recheck", material_binding_error="flow_interrupted")
                task["stages"]["export"].update(
                    status="needs_recheck", error_code="flow_interrupted"
                )
                changed = True
            if task.get("group_read", {}).get("status") == "running":
                # Only a capture can have an external compilation receipt to reconcile.
                unknown = task["group_read"].get("operation", "group_capture") == "group_capture"
                task["group_read"].update(
                    status="needs_recheck" if unknown else "failed",
                    error_code="flow_interrupted",
                )
                task["status"] = "needs_recheck" if unknown else "draft_ready"
                changed = True
            for name, stage in task["stages"].items():
                if stage["status"] in {"queued", "running"}:
                    unstarted = name == "export" and stage["status"] == "queued"
                    status = "needs_recheck" if name == "export" and not unstarted else "failed"
                    recovery_reason = "flow_export_not_started" if unstarted else reason
                    task.setdefault("recovery_history", []).append(
                        {
                            "stage": name,
                            "previous_status": stage["status"],
                            "status": status,
                            "reason": recovery_reason,
                            "attempt_id": stage.get("attempt_id"),
                            "input_epoch": task.get("input_epoch", 0),
                            "inputs_revision": digest(task["inputs"]),
                            "job_binding": task["job_binding"],
                            "at": time.time(),
                        }
                    )
                    stage.update(status=status, error_code=recovery_reason)
                    task["status"] = "export_failed" if unstarted else status
                    changed = True
        if self.material_batch:
            before = digest(state.get("preparation_batch"))
            for task in state["tasks"]:
                self._batch_after(state, task)
            changed = changed or before != digest(state.get("preparation_batch"))
        if changed:
            self._save(state)

    def _task(self, state, task_id):
        return (
            next((task for task in state["tasks"] if task["id"] == task_id), None)
            or self._missing()
        )

    def _missing(self):
        raise PortalDataError("flow_not_found", "找不到此岗位任务。", 404)

    def _writable(self):
        entry = _PIPELINE_HTTP_ENTRY.get()
        checker = entry[1] if entry is not None and entry[0] is self else None
        with self.applications.write_lock() if checker is not None else nullcontext():
            if self._runtime_error:
                raise PortalDataError(
                    self._runtime_error, "任务快照保存失败，请保留记录并重开核验。", 503
                )
            if self._closed.is_set() or not self._owner:
                raise PortalDataError(
                    "flow_runtime_busy", "任务执行器暂不可用，请重新读取状态。", 409
                )
            if checker is not None:
                checker()

    def _identity(self, application, inputs=None):
        if self.input_provider is not None:
            current = self.input_provider(application["id"])
            if (
                not isinstance(current, dict)
                or current.get("application_revision") != application["revision"]
                or not isinstance(current.get("inputs"), dict)
            ):
                raise PortalDataError("flow_inputs_mismatch", "资料版本不能核验，请重新读取。", 409)
            resolved = current["inputs"]
            if inputs is not None and inputs != resolved:
                raise PortalDataError("flow_inputs_mismatch", "请求资料版本与当前资料不符。", 409)
        else:
            resolved = inputs or {}
        return deepcopy(resolved)

    def configure_analysis(self, analysis, *, source_provider, benchmark_provider):
        """Connect the Analysis owner; task admission and history remain here."""
        if not callable(source_provider) or not callable(benchmark_provider):
            raise ValueError("Analysis input providers must be callable")
        self.analysis = analysis
        self._analysis_sources = source_provider
        self._analysis_benchmark = benchmark_provider
        self.callbacks.update(
            analysis=self.prepare_analysis,
            reuse_analysis=self.reuse_task_analysis,
            refresh_match=self.refresh_task_analysis,
        )

    def witness(self, task_id=None):
        """Return the saved state and one task copy for read-only comparison."""
        state = self._load()
        return state, deepcopy(self._task(state, task_id)) if task_id else None

    def material_tasks(self):
        """Material lineage views; they do not depend on observing an old browser page."""
        with self.applications.write_lock():
            return [material_task_view(task) for task in self._load()["tasks"]]

    def reuses_base_sources(self, application_id, base_revision, *, state=None):
        """Whether retained materials stay bound to the unsupplemented career sources."""
        task = latest_preparation_task((state or self._load())["tasks"], application_id)
        # Supplemental matching facts do not rewrite unchanged retained materials.
        return bool(
            task
            and task["status"] in {"draft_ready", "resume_ready", "materials_ready"}
            and (task.get("draft_id") or task.get("resume_id"))
            and task["inputs"].get("sources_revision") == base_revision
        )

    def ready_cover_letter_content(self, application_id, analysis_id):
        """The latest ready letter content for the same job analysis, if any."""
        with self.applications.write_lock():
            for task in reversed(self._load()["tasks"]):
                if (
                    task["application_id"] == application_id
                    and task.get("analysis_id") == analysis_id
                ):
                    branch = task.get("cover_letter") or {}
                    return (
                        deepcopy(branch["result"]["content"])
                        if branch.get("status") == "ready"
                        else None
                    )
        return None

    def adopted_resume_content(self, task_id):
        """The adopted resume content of one task, for its sibling letter."""
        with self.applications.write_lock():
            current = self._task(self._load(), task_id)
            return next(
                (
                    deepcopy(row["result"]["resume_content"])
                    for row in reversed(current["artifacts"])
                    if row.get("stage") == "resume"
                    and row.get("adopted")
                    and row.get("result", {}).get("resume_content")
                ),
                None,
            )

    def cover_letter_call_allowed(self, task_id, attempt_id):
        """Check the saved letter attempt before each letter author call."""
        with self.applications.write_lock():
            current = self._task(self._load(), task_id)
            branch = current.get("cover_letter") or {}
            return (
                not self._closed.is_set()
                and current["status"] != "cancelled"
                and branch.get("attempt_id") == attempt_id
                and not branch.get("cancel_requested")
            )

    def read_draft(self, identifier):
        """Read one adopted resume draft."""
        record = self.adopted_artifact("resume", identifier, kind="draft")
        if record is None:
            raise PortalDataError("flow_draft_not_found", "找不到已保存的岗位草稿。", 404)
        return self._materials.read(record)

    def verify_draft(self, task):
        """Verify the task's saved draft bytes against its adopted record."""
        saved = self.read_draft(task["draft_id"])
        self._materials.verify_for_task(task, material=saved)

    def read_export(self, identifier):
        """Read one adopted PDF export or verified PDF reuse."""
        resumes = self._materials
        record = self.adopted_artifact("export", identifier)
        if record is None:
            record = self.adopted_artifact("resume", identifier, kind="accepted_pdf_reuse")
            if record is None:
                record = self.adopted_artifact("resume", identifier, kind="checked_pdf_reuse")
            if record is None:
                raise PortalDataError("flow_export_not_found", "找不到已采用的 PDF 导出。", 404)
            task = next(
                (
                    row
                    for row in self.material_tasks()
                    if row.get("resume_id") == identifier and row.get("pdf_reuse")
                ),
                None,
            )
            if task is None:
                raise PortalDataError("flow_materials_changed", "材料采用关系已变化。", 409)
            return resumes.read_reuse(task, record, self.material_tasks())
        return resumes.read_pdf(record)

    def verify_materials(self, task):
        """Verify the task's final PDF against its adopted lineage."""
        if local_materials(task):
            # The last successful PDF remains readable during later source
            # edits, unavailable services and upstream configuration changes.
            saved = self.read_export(task["resume_id"])
            if (
                saved.get("application_id") != task["application_id"]
                or saved.get("pdf_sha256") != task["resume_sha256"]
            ):
                raise PortalDataError("flow_materials_changed", "最终 PDF 归档不能核验。", 409)
            return
        if task.get("pdf_reuse"):
            saved = self.read_export(task["resume_id"])
            if (
                saved.get("reuse_binding") != task["pdf_reuse"]
                or saved.get("pdf_sha256") != task["resume_sha256"]
            ):
                raise PortalDataError("flow_materials_changed", "材料采用关系已变化。", 409)
            return
        if self.preparation_only or task.get("automatic_materials"):
            self._reviewed_draft(task)
            saved = self.read_export(task["resume_id"])
            if (
                saved.get("draft_id") != task.get("draft_id")
                or saved.get("draft_sha256") != task.get("draft_sha256")
                or saved.get("task_inputs") != task["inputs"]
                or saved.get("pdf_sha256") != task["resume_sha256"]
                or saved.get("export_configuration_revision") != self._export_configuration(task)
                or task.get("prism")
                and saved.get("prism_source_revision") != task["prism"]["source_revision"]
            ):
                raise PortalDataError(
                    "flow_materials_changed",
                    "PDF 或导出配置已变化，请保留旧版并明确重试导出。",
                    409,
                )
            if (
                not task.get("automatic_materials")
                and task.get("origin") == "generated_latex"
                and saved.get("group_review") != self._reviewed_groups(task)
            ):
                raise PortalDataError(
                    "flow_materials_changed", "分组审核与此完整源 PDF 绑定不符。", 409
                )
            return
        if (
            hashlib.sha256(self._materials.pdf(task["resume_id"])).hexdigest()
            != task["resume_sha256"]
        ):
            raise PortalDataError(
                "flow_materials_changed", "PDF 内容已变化，请保留旧版并重新生成材料。", 409
            )

    def verify_latex_base(self, task):
        """Raise when the task's bound LaTeX base no longer matches its source."""
        from .application_resume import verify_latex_base

        return verify_latex_base(task, self.callbacks.get("prism_source"))

    def verify_prism_source(self, task):
        """Raise when the task's bound LaTeX/Prism source has changed."""
        from .application_resume import verify_prism_source

        return verify_prism_source(task, self.callbacks.get("prism_source"))

    def check_inputs_current(self, task):
        """Raise when the job or material inputs no longer match the task."""
        return self._fresh(task)

    def check_available(self):
        """Raise when this Flow cannot currently report Worker progress."""
        if self._runtime_error:
            raise PortalDataError(
                self._runtime_error, "任务快照保存失败，请保留记录并重开核验。", 503
            )
        if self._closed.is_set():
            raise PortalDataError("flow_runtime_busy", "任务执行器暂不可用，请重新读取状态。", 409)

    def read_checked_task(self, task_id, task_revision):
        """Read one task at the expected revision without taking the write lock."""
        return self._read_checked(task_id, task_revision)[1]

    def writable_task(self, task_id, task_revision=None):
        """Read one writable task; a revision also requires it to be current and not handed off."""
        if task_revision is None:
            self._writable()
            return self._task(self._load(), task_id)
        return self._checked(task_id, task_revision)[1]

    def configure_materials(
        self, resumes, *, automatic_author=True, review=None, template_config=None
    ):
        """Connect the Resume, CoverLetter and consistency owners to this Flow.

        Requires ``configure_analysis`` first. Callback keys are the established
        Flow seams; material admission and lineage checks remain here.
        """
        from .application_cover_letter import CoverLetterModule
        from .application_information import (
            material_information_library,
            read_information_library,
        )
        from .application_material_consistency import MaterialConsistencyModule
        from .application_prism import PrismClient
        from .application_prism import source_snapshot as prism_source_snapshot
        from .codex_cli import run_codex_exec

        self._materials = resumes
        analysis, sources = self.analysis, self._analysis_sources
        resumes.cover_letter_provider = self.ready_cover_letter_content

        def material_information(application):
            return material_information_library(
                application, read_information_library(self.information_library_root)
            )

        def with_preview(result, identifier=None):
            return result | {"preview_url": f"/api/flow/resumes/{identifier or result['id']}/pdf"}

        def execute_generation(handoff, task, *, allow_calls=True):
            return (
                resumes.execute_generation(
                    handoff, admit_call=lambda: self.resume_call_allowed(task)
                )
                if allow_calls
                else resumes.reconcile_generation(handoff)
            )

        def generate_resume(task):
            fixed = self.fixed_writing_inputs(task)
            if fixed is None and (
                retained_configuration_inputs(
                    task, self.input_provider(task["application_id"])["inputs"]
                )
                != task["inputs"]
            ):
                raise PortalDataError(
                    "flow_inputs_stale", "岗位或材料配置已变化，请更新任务。", 409
                )
            complete_materials = self.preparation_only or task.get("automatic_materials")
            result = resumes.prepare(
                task,
                fixed,
                source_provider=lambda selected: (
                    analysis.read_sources(selected) if selected is not None else sources()
                ),
                information_provider=material_information,
                reuse_tasks=self.material_tasks,
                complete_materials=complete_materials,
                automatic_author=automatic_author,
                admit_call=lambda: self.resume_call_allowed(task),
            )
            return (
                result
                if fixed is not None
                or complete_materials
                or result.get("kind") == "experience_handoff"
                else with_preview(result)
            )

        def material_runner(*args, **kwargs):
            return (resumes.model_runner or run_codex_exec)(*args, **kwargs)

        letters = CoverLetterModule(
            self.root / "cover-letters",
            lambda selected: analysis.read_sources(selected),
            runner=material_runner,
        )
        consistency = MaterialConsistencyModule(
            self.root / "material-consistency", runner=material_runner
        )

        def generate_cover_letter(task):
            attempt = task["cover_letter"]["attempt_id"]
            return letters.prepare(
                task,
                self.fixed_writing_inputs(task),
                sibling_content_provider=lambda: self.adopted_resume_content(task["id"]),
                admit_call=lambda: self.cover_letter_call_allowed(task["id"], attempt),
            )

        def read_existing_experience_materials(task, generation_id, export_id):
            from .application_experience_latex import read_completed

            checked = read_completed(resumes, task, generation_id, export_id)
            return checked | {"export": with_preview(checked["export"], export_id)}

        def draft_arguments(task):
            return {"task_inputs": task["inputs"]}

        def export_pdf(task, *, reconcile=False):
            result = resumes.reconcile_build(task) if reconcile else resumes.build_pdf(task)
            return result if result.get("status") == "not_complete" else with_preview(result)

        bound_inputs = {"source_provider": sources, "information_provider": material_information}
        self.callbacks.update(
            resume_author_result=lambda task: execute_generation(
                task["experience_handoff"], task, allow_calls=False
            ),
            resume=generate_resume,
            retained_draft=resumes.retained_career_draft,
            verify_prepared_resume=resumes.validate_prepared,
            cover_letter=generate_cover_letter,
            cover_letter_result=lambda task: letters.read(task, self.fixed_writing_inputs(task)),
            material_consistency=lambda task: consistency.check(
                task, self.fixed_writing_inputs(task)
            ),
            material_consistency_result=lambda task: consistency.read(
                task, self.fixed_writing_inputs(task)
            ),
            experience_generation=lambda task: resumes.progress_generation(
                task["experience_handoff"]
            ),
            existing_experience_materials=read_existing_experience_materials,
            verify_pdf_reuse=lambda task, result: resumes.verify_reuse(
                task, result, self.material_tasks()
            ),
            verify_draft=self.verify_draft,
            automatic_edit_prepare=lambda task: resumes.prepare_group_review(
                task["draft_id"], task["draft_sha256"], **draft_arguments(task)
            ),
            automatic_source_save=lambda task, text: resumes.save_automatic_source(
                task["draft_id"], task["draft_sha256"], **draft_arguments(task), latex_source=text
            ),
            prism_edit_begin=lambda task: resumes.begin_prism_edit(
                task["draft_id"], task["draft_sha256"], **draft_arguments(task)
            ),
            prism_edit_finish=lambda task: resumes.finish_prism_edit(task["prism_edit"]["id"]),
            prism_edit_state=lambda identifier: resumes.prism_edit_state(identifier),
            prism_result_capture=lambda task, export_id: with_preview(
                resumes.capture_compiled_pdf(task, request_id=export_id), export_id
            ),
            prism_source=prism_source_snapshot,
            automatic_latex_base=lambda task: resumes.select_template(
                task,
                template_config=template_config,
                template_root=self.root / "resume-templates",
                review_binding_provider=review._binding if review is not None else None,
                material_tasks=self.material_tasks,
            ),
            export=export_pdf,
            reconcile_export=lambda task: export_pdf(task, reconcile=True),
            export_configuration=resumes.export_configuration_revision,
            verify_materials=self.verify_materials,
            bound_resume_draft=lambda task: resumes.prepare_bound_draft(task, **bound_inputs),
            bound_edit_prepare=lambda task: resumes.prepare_bound_edit(task, **bound_inputs),
            bound_candidate_source=resumes.verify_bound_candidate_source,
            bound_material_candidate=self.prepare_bound_candidate,
        )
        if not self.preparation_only:
            self.callbacks["prism_export_configuration"] = lambda: digest(
                (resumes.prism_client or PrismClient()).configuration()
            )
            return

        def prism_client():
            return resumes.prism_client if resumes.prism_client is not None else PrismClient()

        self.callbacks.update(
            group_prepare=lambda task: resumes.prepare_group_review(
                task["draft_id"], task["draft_sha256"], **draft_arguments(task)
            ),
            group_capture=lambda task, **kwargs: resumes.capture_group_review(
                task["draft_id"], task["draft_sha256"], **draft_arguments(task), **kwargs
            ),
            group_edit=lambda task, payload: resumes.edit_group_review(
                task["draft_id"], task["draft_sha256"], **draft_arguments(task), payload=payload
            ),
            group_state=lambda task: resumes.group_review_state(task["draft_id"]),
            prism_open=lambda binding: prism_client().open(binding),
            prism_export_configuration=lambda: digest(prism_client().configuration()),
            import_latex=lambda task, source: resumes.import_latex_for_task(
                task["application_id"],
                task["application_revision"],
                task_inputs=task["inputs"],
                prism=source,
            ),
        )
        if review is not None:

            def adopt_review_snapshot(task, **arguments):
                self.verify_draft(task)
                self.verify_prism_source(task)
                return with_preview(
                    resumes.adopt_review_snapshot(
                        task["draft_id"],
                        task["draft_sha256"],
                        task_inputs=task["inputs"],
                        review_store=review,
                        **arguments,
                    )
                )

            self.callbacks["adopt_review_snapshot"] = adopt_review_snapshot

    def _analysis_report(self, progress):
        if progress["status"] != "complete":
            raise PortalDataError(
                progress.get("error_code") or "match_result_needs_recheck",
                "原岗位分析尚未核验，未重复模型请求。",
                409,
            )
        return self.analysis.read(progress["result_ref"])

    def prepare_analysis(self, task):
        from .application_benchmark import compare_benchmark

        application = self._fresh(task, stage="analysis")
        sources = self._analysis_sources()
        benchmark, benchmark_revision = self._analysis_benchmark(sources)
        if (
            job_input_revision(application) != task["inputs"]["jd_revision"]
            or sources["revision"] != task["inputs"]["sources_revision"]
            or benchmark_revision != task["inputs"]["historical_benchmark_revision"]
            or self.analysis.configuration_revision()
            != task["inputs"]["analysis_configuration_revision"]
        ):
            raise PortalDataError("flow_inputs_stale", "岗位或资料配置已变化，请更新任务。", 409)
        attempt = task["stages"]["analysis"]
        candidates = [
            previous["stage"]["attempt_id"]
            for previous in reversed(task.get("analysis_attempts", []))
            if previous.get("job_binding") == task["job_binding"]
            and previous.get("inputs", {}).get("sources_revision")
            == task["inputs"]["sources_revision"]
            and isinstance(previous.get("stage", {}).get("attempt_id"), str)
            and re.fullmatch(r"[a-f0-9]{32}", previous["stage"]["attempt_id"])
        ]
        progress = self.analysis.prepare(
            application,
            sources,
            request_id=attempt.get("attempt_id") or uuid4().hex,
            resume_from=attempt.get("resume_from_attempt_id"),
            recovery_candidates=candidates,
            admit_call=lambda: self.analysis_call_allowed(task),
        )
        result = self._analysis_report(progress)
        self._fresh(task, stage="analysis")
        return result | {"historical_reference": compare_benchmark(result.get("score"), benchmark)}

    def reuse_task_analysis(self, task, resolved):
        from .application_benchmark import compare_benchmark

        previous = next(
            (
                row["result"]
                for row in reversed(task["artifacts"])
                if row["stage"] == "analysis"
                and row["adopted"]
                and row["result"]["id"] == task["analysis_id"]
            ),
            None,
        )
        if previous is None:
            return None
        application = self.applications.get_application(task["application_id"])
        sources = self._analysis_sources()
        if (
            sources["revision"] != resolved.get("sources_revision")
            or self._identity(application) != resolved
        ):
            raise PortalDataError("flow_inputs_stale", "资料已变化，请保留原分析并重新读取。", 409)
        progress = self.analysis.reuse(application, sources, previous, request_id=uuid4().hex)
        if progress is None:
            return None
        result = self._analysis_report(progress)
        current = self.applications.get_application(task["application_id"])
        if self._identity(current) != resolved:
            raise PortalDataError("flow_inputs_stale", "资料已变化，请保留原分析并重新读取。", 409)
        benchmark, _ = self._analysis_benchmark(sources)
        return result | {"historical_reference": compare_benchmark(result.get("score"), benchmark)}

    def refresh_task_analysis(self, application, requirements, directory, **options):
        """Adapt the retained match-refresh journal to its Analysis executor."""
        from .application_match_refresh import _read

        previous = options.pop("resume_from", None)
        intent = _read(directory.parent / "intent.json")
        with self.applications.write_lock():
            task = deepcopy(self._task(self._load(), intent["task_id"]))
        return self.analysis.prepare_refresh(
            application,
            self._analysis_sources(),
            request_id=directory.parent.name,
            requirements=requirements,
            resume_request_id=previous.parent.name if previous is not None else None,
            admit_call=lambda: self.analysis_call_allowed(
                task, refresh=(directory.parent.name, digest(intent))
            ),
            **options,
        )

    def analysis_call_allowed(self, expected, *, refresh=None):
        """Read the current task's control immediately before a new model dispatch."""
        if self._closed.is_set() or self._runtime_error:
            return False
        try:
            with self.applications.write_lock():
                state = self._load()
                task = self._task(state, expected["id"])
                if (
                    self._closed.is_set()
                    or task["status"] == "cancelled"
                    or task["job_binding"] != expected["job_binding"]
                    or analysis_input_binding(task["inputs"])
                    != analysis_input_binding(expected["inputs"])
                ):
                    return False
                if refresh is None:
                    if task["stages"]["analysis"].get("attempt_id") != expected["stages"][
                        "analysis"
                    ].get("attempt_id"):
                        return False
                else:
                    from .application_match_refresh import _read

                    intent = _read(self.root / "match-refreshes" / refresh[0] / "intent.json")
                    if (
                        task["revision"] != expected["revision"]
                        or intent.get("task_revision") != expected["revision"]
                        or task.get("analysis_id") != expected.get("analysis_id")
                        or digest(intent) != refresh[1]
                    ):
                        return False
                if self.material_batch and not self.material_batch.guard_admission(state, task):
                    return False
                permit = self.callbacks.get("preparation_allowed")
                if permit is None:
                    return True
                if refresh is not None:
                    import inspect

                    try:
                        inspect.signature(permit).bind(task["id"], refresh=refresh)
                    except TypeError:
                        return permit(task["id"]) is True
                    return permit(task["id"], refresh=refresh) is True
                return permit(task["id"]) is True
        except (OSError, ValueError, KeyError, TypeError, helper.StoreError):
            return False

    def _retain_stopped_analysis(self, task, request, attempt_id):
        """Keep a proven local dispatch refusal resumable through normal Continue."""
        analysis = getattr(self, "analysis", None)
        try:
            stopped = analysis is not None and analysis.progress(attempt_id)["status"] == "stopped"
        except (OSError, ValueError, PortalDataError):
            stopped = False
        if not stopped:
            return False
        previous = deepcopy(task["stages"]["analysis"])
        previous.update(status="failed", error_code="flow_preparation_stopped")
        task.setdefault("analysis_attempts", []).append(
            {
                "stage": previous,
                "inputs": deepcopy(request["inputs"]),
                "job_binding": request["job_binding"],
            }
        )
        task["stages"]["analysis"] = {"status": "pending"}
        task["status"] = "draft"
        return True

    def fixed_writing_inputs(self, task):
        """Resolve only a task's adopted analysis and saved fixed writing handoff."""
        analysis = next(
            (
                row["result"]
                for row in reversed(task.get("artifacts", []))
                if row.get("stage") == "analysis"
                and row.get("adopted")
                and row.get("result", {}).get("id") == task.get("analysis_id")
            ),
            None,
        )
        saved = task.get("experience_handoff") or {}
        fixed_handoff = saved.get("generation_contract") in {
            "fixed-writing/v1",
            "content-writing/v1",
        }
        fixed_analysis = isinstance(analysis, dict) and all(
            isinstance(analysis.get(key), dict)
            for key in ("job_brief", "material_packet", "inference_result")
        )
        if not (fixed_handoff or fixed_analysis):
            return None
        if analysis is None:
            raise PortalDataError(
                "flow_analysis_required", "固定写作须对应本任务已采用的岗位分析。", 409
            )
        if fixed_handoff:
            reader = self.callbacks.get("experience_generation")
            if reader is None:
                raise PortalDataError(
                    "flow_generation_mismatch", "固定经历交付读取入口不可用。", 409
                )
            current = reader(deepcopy(task))
            if (
                current.get("generation_contract") != saved.get("generation_contract")
                or current.get("id") != saved.get("id")
                or current.get("application_id") != task["application_id"]
                or current.get("analysis_binding", {}).get("analysis_id") != task["analysis_id"]
                or current.get("fixed_inputs_revision") != saved.get("fixed_inputs_revision")
            ):
                raise PortalDataError(
                    "flow_generation_mismatch", "固定经历交付与本任务、岗位或分析不符。", 409
                )
            return {"analysis": analysis, "handoff": current}
        if analysis.get("application_id") != task["application_id"]:
            raise PortalDataError("flow_generation_mismatch", "固定分析与本岗位不符。", 409)
        return {"analysis": analysis, "handoff": None}

    def _fresh(self, task, *, stage=None):
        if self.preparation_only:
            latest = latest_preparation_task(self._load()["tasks"], task["application_id"])
            if (
                latest is None
                or latest["id"] != task["id"]
                or (
                    latest.get("input_epoch", 0) != task.get("input_epoch", 0)
                    and (
                        stage != "analysis"
                        or latest["job_binding"] != task["job_binding"]
                        or analysis_input_binding(latest["inputs"])
                        != analysis_input_binding(task["inputs"])
                    )
                )
            ):
                raise PortalDataError(
                    "flow_inputs_stale", "当前岗位已有更新的任务或输入，请保留旧结果。", 409
                )
        if local_materials(task) and stage != "analysis":
            return self.applications.get_application(task["application_id"])
        fixed = self.fixed_writing_inputs(task) if stage in {"resume", "export"} else None
        application = self.applications.get_application(task["application_id"])
        if fixed is not None:
            # The adopted delivery owns these inputs; unrelated live changes do
            # not reinterpret its JD, material selection or generation settings.
            return {**application, **fixed["analysis"].get("job_brief", {}).get("job", {})}
        inputs = self._identity(application, None if self.input_provider else task["inputs"])
        inputs = retained_configuration_inputs(task, inputs)
        expected = task["inputs"]
        if stage == "analysis":
            inputs, expected = analysis_input_binding(inputs), analysis_input_binding(expected)
        elif self.preparation_only and task.get("origin") == "existing_latex":
            inputs = {k: v for k, v in inputs.items() if k != "resume_configuration_revision"}
            expected = {k: v for k, v in expected.items() if k != "resume_configuration_revision"}
        if job_input_revision(application) != task["job_binding"] or inputs != expected:
            raise PortalDataError("flow_inputs_stale", "JD 或职业资料已变化，请更新任务。", 409)
        if stage != "analysis" and task.get("latex_base"):
            self.verify_latex_base(task)
        return application

    def request(self, action, payload):
        if action.startswith("batch-") and self.material_batch:
            return self.material_batch.request(action, payload)
        fields = {
            "create": ({"application_id", "application_revision"}, {"inputs"}),
            "start": ({"task_id", "task_revision", "stage"}, {"retry"}),
            "start-cover-letter": ({"task_id", "task_revision"}, {"retry"}),
            "recheck-cover-letter": ({"task_id", "task_revision"}, set()),
            "recheck-resume-author": ({"task_id", "task_revision"}, set()),
            "recheck-material-consistency": ({"task_id", "task_revision"}, set()),
            "retry-material-consistency": ({"task_id", "task_revision"}, set()),
            "refresh-match": ({"task_id", "task_revision", "request_id"}, {"resume_request_id"}),
            "reconcile-failed-match-refresh": ({"task_id", "task_revision", "request_id"}, set()),
            "attach-match-recheck": (
                {"task_id", "task_revision", "analysis_id", "library_revision"},
                set(),
            ),
            "resume-experience-generation": ({"task_id", "task_revision", "generation_id"}, set()),
            "attach-experience-materials": (
                {"task_id", "task_revision", "generation_id", "export_id"},
                set(),
            ),
            "restart-existing-handoff": ({"task_id", "task_revision"}, set()),
            "attach-existing-handoff": (
                {
                    "task_id",
                    "task_revision",
                    "handoff_root",
                    "handoff_task_id",
                    "handoff_task_revision",
                },
                set(),
            ),
            "cancel": ({"task_id", "task_revision"}, set()),
            "update-inputs": (
                {"task_id", "task_revision", "application_revision"},
                {"inputs"},
            ),
            "confirm-materials": (
                {"task_id", "task_revision", "resume_id", "resume_sha256"},
                set(),
            ),
            "record-retained-material-acceptance": (
                {
                    "task_id",
                    "task_revision",
                    "resume_id",
                    "resume_sha256",
                    "source_sha256",
                    "approval_record",
                },
                set(),
            ),
            "begin-group-review": ({"task_id", "task_revision"}, set()),
            "begin-automatic-edit": ({"task_id", "task_revision"}, set()),
            "begin-prism-edit": ({"task_id", "task_revision"}, set()),
            "finish-prism-edit": ({"task_id", "task_revision"}, set()),
            "capture-prism-result": ({"task_id", "task_revision"}, set()),
            "save-automatic-source": (
                {"task_id", "task_revision", "expected_source_revision", "latex_source"},
                set(),
            ),
            "capture-group-review": (
                {"task_id", "task_revision", "expected_source_revision"},
                set(),
            ),
            "recheck-group-review": ({"task_id", "task_revision"}, set()),
            "review-group": (
                {
                    "task_id",
                    "task_revision",
                    "draft_id",
                    "draft_sha256",
                    "group_id",
                    "review_fingerprint",
                },
                set(),
            ),
            "edit-review-group": ({"task_id", "task_revision", "payload"}, set()),
            "review-draft": ({"task_id", "task_revision", "draft_id", "draft_sha256"}, set()),
            "export-pdf": ({"task_id", "task_revision", "draft_id", "draft_sha256"}, {"retry"}),
            "recheck-export": ({"task_id", "task_revision"}, set()),
            "adopt-review-snapshot": (
                {"task_id", "task_revision", "review_version_id", "expected_pdf_sha256"},
                set(),
            ),
            "bind-prism": ({"task_id", "task_revision", "project_root", "main"}, set()),
            "bind-latex-base": ({"task_id", "task_revision", "project_root", "main"}, set()),
            "refresh-prism": ({"task_id", "task_revision"}, set()),
            "open-prism": ({"task_id", "task_revision"}, set()),
            "import-latex": (
                {"application_id", "application_revision", "project_root", "main"},
                set(),
            ),
            "authorize-latex-export": (
                {"task_id", "task_revision", "draft_id", "draft_sha256"},
                set(),
            ),
            "clarify-condition": (
                {"task_id", "task_revision", "requirement_index", "eligible", "source"},
                set(),
            ),
            "prepare-worker": (
                {"task_id", "task_revision", "country", "send_confirmed"},
                set(),
            ),
            "worker-action": (
                {"task_id", "task_revision", "operation", "payload"},
                set(),
            ),
            "reorder": ({"application_id", "direction", "order_revision"}, set()),
        }
        if action not in fields or not isinstance(payload, dict):
            raise PortalDataError("invalid_flow_request", "任务请求无效。")
        required, optional = fields[action]
        if not required <= payload.keys() or not payload.keys() <= required | optional:
            raise PortalDataError("invalid_flow_request", "任务请求字段无效。")
        for key, value in payload.items():
            if key == "inputs":
                valid = isinstance(value, dict) and all(
                    isinstance(k, str) and isinstance(v, str) and v for k, v in value.items()
                )
            elif key in {"payload", "approval_record"}:
                valid = isinstance(value, dict)
            elif key in {"retry", "eligible", "send_confirmed"}:
                valid = isinstance(value, bool)
            elif key == "requirement_index":
                valid = type(value) is int and value >= 0
            else:
                valid = isinstance(value, str) and bool(value.strip())
            if not valid:
                raise PortalDataError("invalid_flow_request", "任务请求字段无效。")
        entry = _PIPELINE_HTTP_ENTRY.get()
        if entry is not None and entry[0] is self:
            self._writable()
        return getattr(self, action.replace("-", "_"))(**payload)

    def _checked(self, task_id, task_revision, *, allow_existing_handoff=False):
        self._writable()
        state, task = self._read_checked(task_id, task_revision)
        if (
            task.get("codex_handoff_ref") or task.get("codex_handoff_attempt")
        ) and not allow_existing_handoff:
            raise PortalDataError(
                "flow_handoff_bound", "已有上传记录已接回；请保留表单并由用户完成最终 Submit。", 409
            )
        return state, task

    def _read_checked(self, task_id, task_revision):
        state = self._load()
        task = self._task(state, task_id)
        if task["revision"] != task_revision:
            raise PortalDataError("conflict", "任务已变化，请重新读取。", 409)
        return state, task

    def _batch_after(self, state, task):
        if self.material_batch and task.get("origin") != "existing_latex":
            self.material_batch.after_task(state, task)

    @staticmethod
    def _group_guard_change(task, *, allow_prism_edit=False):
        if not allow_prism_edit and task.get("prism_edit", {}).get("status") in {
            "editing",
            "finishing",
            "open_failed",
        }:
            raise PortalDataError(
                "prism_edit_active", "正在 Prism 中人工编辑；请明确完成编辑后返回校对。", 409
            )
        if task.get("export_recoveries"):
            raise PortalDataError(
                "flow_export_recheck_required",
                "原 Prism 请求结果仍未知；复用快照不能授权执行或替换源。",
                409,
            )
        if task.get("group_read", {}).get("status") in {"running", "needs_recheck"}:
            raise PortalDataError(
                "flow_group_recheck_required",
                "先核验本次预览结果，不能开始另一操作或替换原任务。",
                409,
            )

    def _batch_guard_change(self, state, task, *, allow_prism_edit=False):
        self._group_guard_change(task, allow_prism_edit=allow_prism_edit)
        batch = state.get("preparation_batch")
        if (
            batch
            and batch.get("active_task_id") == task["id"]
            and (
                task["status"] == "needs_recheck"
                or task["stages"].get("export", {}).get("status") == "needs_recheck"
                or batch.get("control") == "needs_recheck"
            )
        ):
            raise PortalDataError(
                "flow_batch_recheck_required", "先核验当前未知结果，不能通过改状态绕过。", 409
            )

    def cancel(self, task_id, task_revision):
        """Compatibility name for preparation cancellation; execution belongs to Pipeline."""
        return self.cancel_preparation(task_id, task_revision)

    def cancel_preparation(self, task_id, task_revision, *, execution_cancellation=None):
        """Stop this preparation while retaining execution references and unknown effects."""
        with self.applications.write_lock():
            state, task = self._checked(task_id, task_revision, allow_existing_handoff=True)
            previous = deepcopy(task)
            if execution_cancellation is not None:
                execution = execution_cancellation
                reference = task.get("worker_ref")
                if (
                    not isinstance(execution, dict)
                    or execution.get("application_id") != task["application_id"]
                    or execution.get("task_id") != task["id"]
                    or not isinstance(execution.get("batch_id"), str)
                    or not execution["batch_id"]
                    or execution.get("run_id") is not None
                    and (not isinstance(execution["run_id"], str) or not execution["run_id"])
                    or execution.get("status") not in {"stopping", "stopped", "unknown"}
                    or reference
                    and (
                        reference["batch_id"] != execution["batch_id"]
                        or reference["job_id"] != task["application_id"]
                    )
                    or not reference
                    and task.get("worker_preparation", {}).get("status") != "pending"
                ):
                    raise PortalDataError(
                        "flow_worker_mismatch", "停止结果与原准备任务不符，保留原引用。", 409
                    )
                if reference is None:
                    task["worker_ref"] = {
                        "batch_id": execution["batch_id"],
                        "job_id": task["application_id"],
                    }
                if task.get("worker_preparation", {}).get("status") == "pending":
                    task["worker_preparation"] = {"status": "complete"}
            if task.get("origin") == "existing_latex" and task["stages"].get("export", {}).get(
                "status"
            ) in {"running", "needs_recheck"}:
                raise PortalDataError(
                    "flow_export_recheck_required",
                    "Prism 导出已开始或结果未知，请保留原尝试并核验回执。",
                    409,
                )
            self._batch_guard_change(
                state,
                task,
                allow_prism_edit=task.get("prism_edit", {}).get("status") == "editing"
                and not task.get("prism_edit", {}).get("opening"),
            )
            task.update(status="cancelled", materials_confirmed=False)
            letter = task.get("cover_letter") or {}
            if letter.get("status") in {"queued", "running"}:
                letter["cancel_requested"] = True
            self._cancel_material_consistency(task)
            for stage in task["stages"].values():
                if stage["status"] in {"queued", "running"}:
                    stage["status"] = "cancelled"
            if task == previous:
                return deepcopy(task)
            self._batch_after(state, task)
            self._save(state)
            return deepcopy(task)

    def material_update_progress(self, task_id, update_id):
        """Read the exact local material update; it does not recreate pending work."""
        from .application_bound_materials import binding, failure, read_commit_journal

        with self.applications.write_lock():
            journal = read_commit_journal(self.root, update_id)
            task = self._task(self._load(), task_id)
            if (
                journal["task_id"] != task_id
                or task["status"] == "cancelled"
                or task.get("material_update", {}).get("id") != update_id
                or digest(binding(task)) != digest(binding(journal["new"]))
                or any(
                    digest(task.get(key)) != digest(journal["new"].get(key))
                    for key in (
                        "input_epoch",
                        "stages",
                        "worker_preparation",
                        "codex_handoff_ref",
                        "codex_handoff_attempt",
                    )
                )
            ):
                raise failure("bound_material_journal_conflict")
            return {
                "task_id": task_id,
                "material_update_id": update_id,
                "status": task["material_update"]["status"],
            }

    def complete_material_update(self, task_id, update_id, *, execution):
        """Adopt only the original Worker's completed page-update delivery."""
        from .application_bound_materials import failure, read_commit_journal

        with self.applications.write_lock():
            self._writable()
            journal = read_commit_journal(self.root, update_id)
            progress = self.material_update_progress(task_id, update_id)
            state = self._load()
            task = self._task(state, task_id)
            receipt = journal["new_job"]["material_update"]["page_receipt"]
            if (
                not isinstance(execution, dict)
                or execution.get("status") != "complete"
                or execution.get("task_id") != task_id
                or execution.get("material_update_id") != update_id
                or execution.get("application_id") != task["application_id"]
                or execution.get("batch_id") != journal["batch_id"]
                or execution.get("run_id") != receipt.get("run_id")
                or progress["status"] not in {"bound", "complete"}
            ):
                raise failure("bound_material_journal_conflict")
            if progress["status"] != "complete":
                task["material_update"]["status"] = "complete"
                if (
                    task["status"] == "needs_recheck"
                    and task.get("materials_confirmed")
                    and task.get("resume_id")
                    and all(stage["status"] == "complete" for stage in task["stages"].values())
                    and not _material_pending(task)
                ):
                    task["status"] = "materials_ready"
                self._save(state)
            return {"task_id": task_id, "material_update_id": update_id, "status": "complete"}

    def _check_material_preparation(self, task):
        """Consume the Worker's read-only permission for this fixed preparation."""
        if self._closed.is_set() or task["status"] == "cancelled":
            raise PortalDataError("flow_cancelled", "准备任务已取消，原候选和材料已保留。", 409)
        callback = self.callbacks.get("bound_material_preparation")
        if callback is None:
            # Retain old injected callbacks through the same Worker-owned checker.
            from .application_bound_materials import paused_job

            paused_job(self, task)
            return
        reference = task.get("worker_ref") or {}
        if reference.get("job_id", task["application_id"]) != task["application_id"]:
            raise PortalDataError("flow_worker_mismatch", "执行记录与岗位任务不符。", 409)
        callback(
            {
                "application_id": task["application_id"],
                "task_id": task["id"],
                "batch_id": reference.get("batch_id"),
            }
        )

    @staticmethod
    def _stage_material_update(task, inputs):
        from .application_bound_materials import failure

        previous = task.get("material_update")
        if previous and previous["status"] not in {"complete", "staged"}:
            raise failure("bound_material_update_pending")
        if previous and previous.get("inputs") == inputs and previous["status"] == "staged":
            return previous
        if previous:
            task.setdefault("material_update_history", []).append(deepcopy(previous))
        old = deepcopy(task)
        old.pop("material_update", None)
        old.pop("material_update_history", None)
        update = {
            "id": uuid4().hex,
            "status": "staged",
            "inputs": deepcopy(inputs),
            "old": old,
            "created_at": time.time(),
        }
        if previous and previous.get("status") == "staged" and previous.get("editable_draft"):
            update["editable_draft"] = deepcopy(previous["editable_draft"])
            update["explicit_source"] = previous.get("explicit_source", False)
        task["material_update"] = update
        task["status"] = "needs_recheck"
        return update

    def material_update_inputs(self, task):
        from .application_bound_materials import failure

        app = self.applications.get_application(task["application_id"])
        inputs = retained_configuration_inputs(task, self._identity(app, None))
        # A completed generator setting belongs to these retained materials, including
        # during a contact-only change. It is not an implicit regeneration request.
        for key in ("analysis_configuration_revision", "resume_configuration_revision"):
            if key in task["inputs"]:
                inputs[key] = task["inputs"][key]
        if (
            job_input_revision(app) != task["job_binding"]
            or analysis_input_binding(inputs) != analysis_input_binding(task["inputs"])
            or inputs.get("information_library_root")
            != task["inputs"].get("information_library_root")
        ):
            raise failure(
                "bound_material_analysis_changed", "岗位或职业依据已变化，不能作为联系方式更新。"
            )
        return inputs

    def _editable_material_update(self, state, task, text=None, expected=None):
        from .application_bound_materials import failure

        self._check_material_preparation(task)
        inputs = self.material_update_inputs(task)
        update = task.get("material_update")
        if update is None or update["status"] == "complete":
            update = self._stage_material_update(task, inputs)
        if update["status"] != "staged":
            raise failure("bound_material_update_pending")
        projected = deepcopy(task)
        projected.pop("material_update", None)
        draft = update.get("editable_draft")
        if draft:
            projected.update(
                draft_id=draft["id"],
                draft_sha256=draft["draft_sha256"],
                source_checkpoint=draft["source_checkpoint"],
                inputs=deepcopy(draft["task_inputs"]),
                base_checkpoint=deepcopy(draft["base_checkpoint"]),
            )
            projected["prism"] = {
                k: v for k, v in draft["source_checkpoint"].items() if k != "archive_sha256"
            } | {"draft_id": draft["id"], "draft_sha256": draft["draft_sha256"]}
        if text is None:
            if draft is None:
                projected["material_update"] = deepcopy(update)
                draft = self.callbacks["bound_edit_prepare"](projected)
        else:
            if draft is None or draft["source_checkpoint"]["source_revision"] != expected:
                raise failure("prism_source_changed")
            draft = self.callbacks["automatic_source_save"](projected, text)
        update["editable_draft"] = draft
        if text is not None:
            update["explicit_source"] = True
        self._save(state)
        return deepcopy(task)

    def begin_material_update(self, task_id, request_id):
        from .application_bound_materials import failure

        with self.applications.write_lock():
            self._writable()
            state = self._load()
            task = self._task(state, task_id)
            if self._closed.is_set() or task["status"] == "cancelled":
                raise failure("flow_cancelled", "准备任务已取消，原候选和材料已保留。")
            if task.get("prism_edit", {}).get("status") in {"editing", "finishing"}:
                raise failure("prism_edit_pending", "请先完成当前 Prism 编辑并核验已有结果。")
            inputs = self.material_update_inputs(task)
            update = task.get("material_update")
            if update and update["status"] not in {"staged", "complete", "needs_recheck"}:
                self._check_material_preparation(task)
                return True
            if inputs == task["inputs"] and not (
                update and update["status"] != "complete" and update.get("explicit_source")
            ):
                if update and update.get("status") == "staged":
                    # Merely opening an independent editor does not change the
                    # current resume or require the user to approve an unchanged PDF.
                    update["status"] = "unchanged"
                    task.setdefault("material_update_history", []).append(deepcopy(update))
                    task.pop("material_update")
                    task["status"] = update["old"]["status"]
                    self._save(state)
                return False
            self._check_material_preparation(task)
            if update and update["status"] == "needs_recheck":
                candidate = update.get("candidate") or {}
                if (
                    candidate.get("stages", {}).get("export", {}).get("status") == "running"
                    and update["inputs"] == inputs
                ):
                    update.setdefault("recovery_history", []).append(
                        {
                            "status": update["status"],
                            "error_code": update.get("error_code"),
                            "at": time.time(),
                            "export_attempt_id": candidate["stages"]["export"]["attempt_id"],
                        }
                    )
                    update.update(status="preparing", reconcile_export=True)
                    self._save(state)
                    self._queue.put((task_id, "bound-material", update["id"]))
                    return True
                if (
                    not candidate
                    and update.get("error_code") == "bound_material_preparation_interrupted"
                ):
                    update.setdefault("recovery_history", []).append(
                        {
                            "status": update["status"],
                            "error_code": update["error_code"],
                            "at": time.time(),
                        }
                    )
                    update["status"] = "staged"
                else:
                    raise failure(update.get("error_code", "bound_material_update_unknown"))
            if update is None or update["status"] == "complete":
                update = self._stage_material_update(task, inputs)
            update.update(status="preparing", request_id=request_id, inputs=inputs)
            self.callbacks["verify_materials"](update["old"])
            self._save(state)
            self._queue.put((task_id, "bound-material", update["id"]))
            return True

    def _prepare_material_update(self, task_id, identifier):
        """Make the independent candidate outside the application write lock."""
        from .application_bound_materials import failure

        candidate = None
        try:
            with self.applications.write_lock():
                state = self._load()
                task = self._task(state, task_id)
                update = task.get("material_update") or {}
                if (
                    self._closed.is_set()
                    or not self._owner
                    or self._runtime_error
                    or task["status"] == "cancelled"
                    or update.get("id") != identifier
                    or update.get("status") != "preparing"
                ):
                    return
                self._check_material_preparation(task)
                if self.material_update_inputs(task) != update["inputs"]:
                    raise failure()
                request = deepcopy(task)
            candidate = self.callbacks["bound_material_candidate"](request)
            with self.applications.write_lock():
                state = self._load()
                task = self._task(state, task_id)
                update = task.get("material_update") or {}
                if (
                    self._closed.is_set()
                    or task["status"] == "cancelled"
                    or update.get("id") != identifier
                    or update.get("status") != "preparing"
                    or self.material_update_inputs(task) != request["material_update"]["inputs"]
                ):
                    raise failure()
                self._check_material_preparation(task)
                known = {
                    (row["stage"], row.get("result", {}).get("id")) for row in task["artifacts"]
                }
                task["artifacts"].extend(
                    deepcopy(
                        [
                            row
                            for row in candidate["artifacts"]
                            if (row["stage"], row.get("result", {}).get("id")) not in known
                        ]
                    )
                )
                self._save(state)
                self._bind_current_materials(candidate)
                update.update(status="awaiting_page", candidate=candidate)
                self._save(state)
        except Exception as error:
            with self.applications.write_lock():
                state = self._load()
                task = self._task(state, task_id)
                update = task.get("material_update") or {}
                if update.get("id") == identifier:
                    if (
                        isinstance(candidate, dict)
                        and isinstance(candidate.get("artifacts"), list)
                        and all(
                            isinstance(row, dict)
                            and isinstance(row.get("stage"), str)
                            and isinstance(row.get("result"), dict)
                            for row in candidate["artifacts"]
                        )
                    ):
                        original = {
                            (row["stage"], row.get("result", {}).get("id"))
                            for row in request["artifacts"]
                        }
                        retained = {
                            (row["stage"], row.get("result", {}).get("id")): row
                            for row in task["artifacts"]
                        }
                        for row in candidate["artifacts"]:
                            key = row["stage"], row.get("result", {}).get("id")
                            if key not in original:
                                if key in retained:
                                    retained[key]["adopted"] = False
                                else:
                                    task["artifacts"].append(deepcopy(row) | {"adopted": False})
                        update["candidate"] = deepcopy(candidate)
                    update.update(
                        status="needs_recheck",
                        error_code=getattr(error, "code", "bound_material_prepare_unknown"),
                        error_message=str(error),
                    )
                    self._save(state)

    def validate_material_candidate(self, task_id, update_id, *, bound=False):
        """Check this participant without exposing or changing another owner's state."""
        with self.applications.write_lock():
            self._checked_material_candidate(task_id, update_id, bound=bound)
            return {"task_id": task_id, "material_update_id": update_id, "status": "ready"}

    def commit_material_candidate(self, task_id, update_id, *, bound=False):
        """Adopt this Flow's exact saved candidate, without resolving another owner's state."""
        with self.applications.write_lock():
            _, state, task, candidate, current, new_binding = self._checked_material_candidate(
                task_id, update_id, bound=bound
            )
            status = "bound" if bound else "committing"
            if digest(current) == digest(new_binding):
                if task["material_update"]["status"] in {status, "bound", "complete"}:
                    return deepcopy(task)
                task["material_update"]["status"] = status
            else:
                candidate["worker_ref"] = new_binding["worker_ref"]
                candidate["material_update"]["status"] = status
                state["tasks"][state["tasks"].index(task)] = candidate
                task = candidate
            self._save(state)
            return deepcopy(task)

    def _checked_material_candidate(self, task_id, update_id, *, bound):
        from .application_bound_materials import binding, failure, read_commit_journal

        self._writable()
        journal = read_commit_journal(self.root, update_id)
        state = self._load()
        task = self._task(state, task_id)
        current = binding(task)
        new_binding = binding(journal["new"])
        if (
            self._closed.is_set()
            or journal["task_id"] != task_id
            or task["application_id"] != journal["application_id"]
            or task["status"] == "cancelled"
            or not task.get("materials_confirmed")
            or task.get("material_update", {}).get("id") != update_id
            or digest(current) not in {digest(journal["old"]), digest(new_binding)}
            or bound
            and journal["status"] != "bound"
        ):
            raise failure("bound_material_journal_conflict")
        candidate = deepcopy(journal["new"])
        update = candidate.get("material_update") or {}
        original = update.get("old") or {}
        expected = candidate if digest(current) == digest(new_binding) else original
        if any(
            digest(task.get(key)) != digest(expected.get(key))
            for key in (
                "input_epoch",
                "stages",
                "worker_preparation",
                "codex_handoff_ref",
                "codex_handoff_attempt",
            )
        ):
            raise failure("bound_material_journal_conflict")
        approval = candidate.get("send_approval") or {}
        approval_changes = {
            "inputs",
            "resume_id",
            "resume_sha256",
            "authorization",
            "material_update_id",
            "at",
        }
        if (
            candidate.get("status") != "needs_recheck"
            or update.get("id") != update_id
            or update.get("status") != "committing"
            or digest(binding(original)) != digest(journal["old"])
            or digest(new_binding["worker_ref"]) != digest(journal["old"].get("worker_ref"))
            or approval.get("authorization") != journal["new_receipt"]
            or approval.get("material_update_id") != update_id
            or any(
                approval.get(key) != candidate.get(key)
                for key in ("inputs", "resume_id", "resume_sha256")
            )
            or digest(
                {key: value for key, value in approval.items() if key not in approval_changes}
            )
            != digest(
                {
                    key: value
                    for key, value in original.get("send_approval", {}).items()
                    if key not in approval_changes
                }
            )
        ):
            raise failure("bound_material_journal_conflict")
        if digest(current) != digest(new_binding):
            prepared = task["material_update"].get("candidate")
            revised = {
                "send_approval_history",
                "send_approval",
                "status",
                "worker_ref",
                "material_update_history",
                "material_update",
                "revision",
            }
            if not isinstance(prepared, dict) or digest(
                {key: value for key, value in candidate.items() if key not in revised}
            ) != digest({key: value for key, value in prepared.items() if key not in revised}):
                raise failure("bound_material_journal_conflict")
            for key in (
                "cover_letter",
                "cover_letter_history",
                "material_consistency",
                "material_consistency_history",
            ):
                if digest(task.get(key)) == digest(original.get(key)):
                    continue
                if digest(candidate.get(key)) not in {
                    digest(original.get(key)),
                    digest(task.get(key)),
                }:
                    raise failure("bound_material_journal_conflict")
                if key in task:
                    candidate[key] = deepcopy(task[key])
                else:
                    candidate.pop(key, None)
        self._fresh(candidate)
        verifier = self.callbacks.get("verify_materials")
        if verifier is None:
            raise failure("flow_materials_changed")
        verifier(candidate)
        return journal, state, task, candidate, current, new_binding

    def update_inputs(self, task_id, task_revision, application_revision, inputs=None):
        with self.applications.write_lock():
            state, task = self._checked(task_id, task_revision)
            if task.get("origin") == "existing_latex":
                raise PortalDataError(
                    "flow_latex_reimport_required",
                    "请重新接入当前岗位和 LaTeX 版本，保留原导出回执。",
                    409,
                )
            self._batch_guard_change(state, task)
            if task["status"] == "cancelled":
                raise PortalDataError("flow_cancelled", "任务已取消，请建立新任务。", 409)
            application = self.applications.get_application(task["application_id"])
            if application["revision"] != application_revision:
                raise PortalDataError("conflict", "投递记录已变化，请重新打开。", 409)
            resolved = self._identity(application, inputs)
            resolved = retained_configuration_inputs(task, resolved)
            changed = (
                resolved != task["inputs"] or job_input_revision(application) != task["job_binding"]
            )
            if changed and (
                task.get("cover_letter", {}).get("status") in {"queued", "running", "needs_recheck"}
                or task.get("worker_preparation", {}).get("status") == "pending"
                or any(
                    stage.get("status") == "needs_recheck"
                    or name in {"resume", "export"}
                    and stage.get("status") in {"queued", "running"}
                    for name, stage in task["stages"].items()
                )
            ):
                raise PortalDataError(
                    "flow_update_inflight",
                    "材料生成、导出或填写准备尚未核验，先保留原尝试及结果。",
                    409,
                )
            analysis_resolved = analysis_input_binding(resolved)
            analysis_expected = analysis_input_binding(task["inputs"])
            if self.preparation_only and "information_library_root" not in resolved:
                # Preserve the original preparation-only library refresh contract.
                analysis_resolved.pop("information_library_revision", None)
                analysis_expected.pop("information_library_revision", None)
            analysis_changed = (
                job_input_revision(application) != task["job_binding"]
                or analysis_resolved != analysis_expected
            )
            reused_analysis = None
            reuse = self.callbacks.get("reuse_analysis")
            # The adapter checks consumed facts and semantic configuration. App
            # fingerprints must not hide an otherwise reusable completed analysis.
            if (
                analysis_changed
                and reuse is not None
                and not task.get("worker_ref")
                and task["stages"]["analysis"]["status"] == "complete"
                and task.get("analysis_id")
                and job_input_revision(application) == task["job_binding"]
                and analysis_resolved.get("sources_revision")
                != analysis_expected.get("sources_revision")
                and {
                    k: v
                    for k, v in analysis_resolved.items()
                    if k
                    not in {
                        "sources_revision",
                        "historical_benchmark_revision",
                        "analysis_configuration_revision",
                    }
                }
                == {
                    k: v
                    for k, v in analysis_expected.items()
                    if k
                    not in {
                        "sources_revision",
                        "historical_benchmark_revision",
                        "analysis_configuration_revision",
                    }
                }
            ):
                reused_analysis = reuse(deepcopy(task), deepcopy(resolved))
                analysis_changed = reused_analysis is None
            if changed and task.get("worker_ref") and not analysis_changed:
                self._stage_material_update(task, resolved)
                self._save(state)
                return self._worker_view(task)
            if reused_analysis is not None:
                from .application_information import condition_information_binding

                library = self.information_provider() if self.information_provider else {}
                for condition in task_eligibility(task, bind_inputs=True)["conditions"]:
                    resolution = condition.get("resolution")
                    if not resolution or not resolution.get("qualification_basis"):
                        continue
                    if resolution["qualification_basis"] != (
                        condition_information_binding(condition, application, library)
                    ):
                        continue
                    task.setdefault("hard_condition_resolutions", []).append(
                        deepcopy(resolution)
                        | {
                            "analysis_id": reused_analysis["id"],
                            "analysis_input_revision": digest(analysis_input_binding(resolved)),
                            "input_revision": digest(
                                {
                                    k: v
                                    for k, v in resolved.items()
                                    if k != "resume_configuration_revision"
                                }
                            ),
                            "inherited_from": {
                                "analysis_id": task["analysis_id"],
                                "resolution_revision": digest(resolution),
                            },
                        }
                    )
                task["artifacts"].append(
                    {
                        "stage": "analysis",
                        "attempt_id": task["stages"]["analysis"].get("attempt_id"),
                        "result": reused_analysis,
                        "inputs": deepcopy(resolved),
                        "adopted": True,
                        "reuse": True,
                    }
                )
                task["analysis_id"] = reused_analysis["id"]
                task["stages"]["analysis"]["artifact_id"] = reused_analysis["id"]
            if changed and analysis_changed and task["stages"]["analysis"]["status"] == "failed":
                task.setdefault("analysis_attempts", []).append(
                    {
                        "stage": deepcopy(task["stages"]["analysis"]),
                        "inputs": deepcopy(task["inputs"]),
                        "job_binding": task["job_binding"],
                    }
                )
            if changed:
                retire_local_materials(task)
            task.update(
                application_revision=application_revision,
                inputs=resolved,
                job_description=application.get("job_description", ""),
                job_binding=job_input_revision(application),
            )
            if changed:
                if analysis_changed and task.get("cover_letter"):
                    task.setdefault("cover_letter_history", []).append(task.pop("cover_letter"))
                task["input_epoch"] = task.get("input_epoch", 0) + 1
                task.update(
                    resume_id=None,
                    resume_sha256=None,
                    materials_confirmed=False,
                    draft_id=None,
                    draft_sha256=None,
                    draft_review=None,
                )
                task.pop("pdf_reuse", None)
                task.pop("experience_handoff", None)
                task["stages"]["resume"] = {"status": "pending"}
                if "export" in task["stages"]:
                    task["stages"]["export"] = {"status": "pending"}
                if analysis_changed:
                    task["analysis_id"] = None
                    task["stages"]["analysis"] = {"status": "pending"}
                analysis_status = task["stages"]["analysis"]["status"]
                task["status"] = (
                    "needs_recheck"
                    if task["worker_ref"]
                    else "analysis_ready"
                    if analysis_status == "complete"
                    else "analyzing"
                    if analysis_status in {"queued", "running"}
                    else "draft"
                    if self.preparation_only and analysis_status == "pending"
                    else "stale"
                )
            elif (
                self.preparation_only
                and task["status"] == "stale"
                and task["stages"]["analysis"]["status"] == "pending"
                and not task.get("worker_ref")
                and not any(
                    stage["status"] in {"queued", "running", "needs_recheck"}
                    for stage in task["stages"].values()
                )
            ):
                self._fresh(task, stage="analysis")
                task["status"] = "draft"
            self._batch_after(state, task)
            self._save(state)
            return self._worker_view(task)

    def confirm_materials(self, task_id, task_revision, resume_id, resume_sha256):
        with self.applications.write_lock():
            state, task = self._checked(task_id, task_revision)
            if task.get("origin") == "existing_latex":
                raise PortalDataError(
                    "flow_factual_review_required",
                    "已有 LaTeX 仍需分组事实审核与新 PDF 确认；真实申请仍暂停。",
                    409,
                )
            self._fresh(task)
            if task.get("origin") == "generated_latex":
                self._reviewed_groups(task)
            if (
                task["status"] not in {"resume_ready", "materials_ready"}
                or task["resume_id"] != resume_id
                or task["resume_sha256"] != resume_sha256
            ):
                raise PortalDataError("flow_materials_mismatch", "请确认当前版本的岗位简历。", 409)
            verifier = self.callbacks.get("verify_materials")
            if verifier:
                verifier(task)
            if task.get("origin") == "generated_latex":
                review = self._reviewed_groups(task)
                exported = next(
                    (
                        row["result"]
                        for row in reversed(task["artifacts"])
                        if row.get("adopted")
                        and row.get("stage") == "export"
                        and row.get("result", {}).get("id") == resume_id
                    ),
                    {},
                )
                if exported.get("group_review") != review:
                    raise PortalDataError(
                        "flow_materials_changed", "当前分组审核与此 PDF 绑定不符。", 409
                    )
                task.setdefault("material_reviews", []).append(
                    {
                        "id": uuid4().hex,
                        "resume_id": resume_id,
                        "pdf_sha256": resume_sha256,
                        "draft_id": task["draft_id"],
                        "draft_sha256": task["draft_sha256"],
                        "group_review_revision": review["revision"],
                        "source_revision": review["source_revision"],
                        "preview_id": review["preview_id"],
                        "reviewed": [
                            "complete_pdf_content",
                            "pdf_layout",
                            "full_source_consistency",
                        ],
                        "input_revision": digest(task["inputs"]),
                        "actor": "user",
                        "scope": "current_pdf_materials",
                        "at": time.time(),
                    }
                )
            task.update(materials_confirmed=True, status="materials_ready")
            self._batch_after(state, task)
            self._save(state)
            observer = self.callbacks.get("observe_confirmation")
            if observer:
                observer(deepcopy(task))
            return deepcopy(task)

    @staticmethod
    def _valid_approval_record(record):
        try:
            return (
                isinstance(record, dict)
                and set(record) == {"sha256", "accepted_at", "statement"}
                and isinstance(record["sha256"], str)
                and re.fullmatch(r"[a-f0-9]{64}", record["sha256"]) is not None
                and isinstance(record["accepted_at"], str)
                and re.fullmatch(
                    r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|\+00:00)",
                    record["accepted_at"],
                )
                is not None
                and datetime.fromisoformat(record["accepted_at"].replace("Z", "+00:00")).utcoffset()
                == timedelta(0)
                and isinstance(record["statement"], str)
                and 1 <= len(record["statement"]) <= 4000
                and bool(record["statement"].strip())
                and not any(
                    ord(character) < 32 and character not in "\n\t"
                    for character in record["statement"]
                )
            )
        except (ValueError, TypeError):
            return False

    @classmethod
    def valid_material_acceptance(cls, task):
        """Whether a task's retained human material receipt is absent or exactly bound to it."""
        receipt = task.get("material_acceptance")
        if receipt is None:
            return True
        try:
            expected = {
                "schemaVersion": 1,
                "kind": "retained_human_material_acceptance",
                "human_actor": "user",
                "task_id": task["id"],
                "application_id": task["application_id"],
                "application_revision": task["application_revision"],
                "job_binding": task["job_binding"],
                "inputs_revision": digest(task["inputs"]),
                "input_epoch": task.get("input_epoch", 0),
                "draft_id": task["draft_id"],
                "draft_sha256": task["draft_sha256"],
                "source_revision": task["prism"]["source_revision"],
                "source_sha256": task["prism"]["files"][task["prism"]["main"]],
                "resume_id": task["resume_id"],
                "pdf_sha256": task["resume_sha256"],
            }
            return (
                isinstance(receipt, dict)
                and set(receipt)
                == set(expected)
                | {
                    "revision",
                    "task_revision_before_record",
                    "export_manifest_sha256",
                    "approval_record",
                    "operator_record",
                }
                and all(receipt.get(key) == value for key, value in expected.items())
                and task.get("origin") == "existing_latex"
                and task.get("factual_review") == "pending"
                and cls._valid_approval_record(receipt["approval_record"])
                and all(
                    isinstance(receipt[key], str) and re.fullmatch(r"[a-f0-9]{64}", receipt[key])
                    for key in ("task_revision_before_record", "export_manifest_sha256", "revision")
                )
                and receipt["revision"]
                == digest({key: value for key, value in receipt.items() if key != "revision"})
                and set(receipt["operator_record"]) == {"actor", "operation", "recorded_at"}
                and receipt["operator_record"]["actor"] == "codex"
                and receipt["operator_record"]["operation"] == "record_existing_human_decision"
                and cls._valid_approval_record(
                    {
                        "sha256": "0" * 64,
                        "accepted_at": receipt["operator_record"]["recorded_at"],
                        "statement": "recorded",
                    }
                )
            )
        except (KeyError, TypeError, ValueError):
            return False

    def _retained_material_current(self, task):
        if (
            not self.preparation_only
            or task.get("origin") != "existing_latex"
            or task.get("status") not in {"resume_ready", "materials_ready"}
            or task.get("worker_ref")
            or task.get("worker_preparation", {}).get("status") == "pending"
            or task.get("group_read", {}).get("status") in {"running", "needs_recheck"}
            or any(
                stage["status"] in {"queued", "running", "needs_recheck"}
                for stage in task["stages"].values()
            )
            or task["stages"].get("export", {}).get("status") != "complete"
        ):
            raise PortalDataError(
                "flow_retained_material_blocked", "当前任务不能记录既有材料决定。", 409
            )
        self._fresh(task)
        self._reviewed_draft(task)
        source = self.verify_prism_source(task)
        exported = next(
            (
                row["result"]
                for row in reversed(task["artifacts"])
                if row.get("adopted")
                and row.get("stage") == "export"
                and row.get("result", {}).get("id") == task.get("resume_id")
            ),
            None,
        )
        verifier = self.callbacks.get("verify_materials")
        if (
            not exported
            or verifier is None
            or not isinstance(exported.get("export_manifest_sha256"), str)
            or not re.fullmatch(r"[a-f0-9]{64}", exported["export_manifest_sha256"])
            or exported.get("pdf_sha256") != task["resume_sha256"]
            or exported.get("task_inputs") != task["inputs"]
        ):
            raise PortalDataError("flow_materials_changed", "已采用材料回执不能核验。", 409)
        self._export_result(task, exported)
        verifier(deepcopy(task))
        self._read_checked(task["id"], task["revision"])
        self._fresh(task)
        self._export_result(task, exported)
        if (
            self.verify_prism_source(task) != source
            or task.get("material_acceptance", {}).get(
                "export_manifest_sha256", exported["export_manifest_sha256"]
            )
            != exported["export_manifest_sha256"]
        ):
            raise PortalDataError("flow_materials_changed", "核验期间材料或既有决定已变化。", 409)
        return source, exported

    def record_retained_material_acceptance(
        self, task_id, task_revision, resume_id, resume_sha256, source_sha256, approval_record
    ):
        """Record an existing human decision; this operation performs no new review."""
        if any(
            not isinstance(value, str) or re.fullmatch(pattern, value) is None
            for value, pattern in (
                (task_id, r"[a-f0-9]{32}"),
                (task_revision, r"[a-f0-9]{64}"),
                (resume_id, r"[a-f0-9]{32}"),
                (resume_sha256, r"[a-f0-9]{64}"),
                (source_sha256, r"[a-f0-9]{64}"),
            )
        ):
            raise PortalDataError("flow_materials_mismatch", "既有材料决定的版本不能核验。", 409)
        with self.applications.write_lock():
            self._writable()
            state = self._load()
            task = self._task(state, task_id)
            previous = task.get("material_acceptance")
            if task_revision not in {
                task["revision"],
                (previous or {}).get("task_revision_before_record"),
            }:
                raise PortalDataError("conflict", "任务版本已变化，请核验既有决定。", 409)
            source, exported = self._retained_material_current(task)
            if (
                resume_id != task["resume_id"]
                or resume_sha256 != task["resume_sha256"]
                or source_sha256 != source["files"][source["main"]]
                or not self._valid_approval_record(approval_record)
            ):
                raise PortalDataError(
                    "flow_materials_mismatch", "既有决定与当前源和 PDF 不符。", 409
                )
            if previous:
                if (
                    previous["approval_record"] != approval_record
                    or previous["export_manifest_sha256"] != exported["export_manifest_sha256"]
                ):
                    raise PortalDataError("conflict", "已有材料决定不能替换，请保留原回执。", 409)
                return deepcopy(task)
            receipt = {
                "schemaVersion": 1,
                "kind": "retained_human_material_acceptance",
                "human_actor": "user",
                "task_id": task_id,
                "task_revision_before_record": task_revision,
                "application_id": task["application_id"],
                "application_revision": task["application_revision"],
                "job_binding": task["job_binding"],
                "inputs_revision": digest(task["inputs"]),
                "input_epoch": task.get("input_epoch", 0),
                "draft_id": task["draft_id"],
                "draft_sha256": task["draft_sha256"],
                "source_revision": source["source_revision"],
                "source_sha256": source_sha256,
                "resume_id": resume_id,
                "pdf_sha256": resume_sha256,
                "export_manifest_sha256": exported["export_manifest_sha256"],
                "approval_record": deepcopy(approval_record),
                "operator_record": {
                    "actor": "codex",
                    "operation": "record_existing_human_decision",
                    "recorded_at": datetime.now(UTC)
                    .isoformat(timespec="microseconds")
                    .replace("+00:00", "Z"),
                },
            }
            receipt["revision"] = digest(receipt)
            task.update(
                material_acceptance=receipt, materials_confirmed=True, status="materials_ready"
            )
            self._batch_after(state, task)
            self._save(state)
            return deepcopy(task)

    def _group_task(self, task):
        self._fresh(task)
        if (
            not self.preparation_only
            or task.get("origin") != "generated_latex"
            or not task.get("draft_id")
            or task.get("worker_ref")
            or task["status"] == "cancelled"
            or any(
                stage["status"] in {"queued", "running", "needs_recheck"}
                for stage in task["stages"].values()
            )
        ):
            raise PortalDataError(
                "flow_group_review_blocked",
                "当前完整 LaTeX 版本不能分组审阅，请先核验已有阶段。",
                409,
            )

    @staticmethod
    def _group_draft(task):
        return next(
            (
                row["result"]
                for row in reversed(task["artifacts"])
                if row.get("adopted")
                and row.get("stage") == "resume"
                and row.get("result", {}).get("id") == task.get("draft_id")
            ),
            None,
        )

    def _adopt_group_draft(self, task, result):
        if (
            result.get("origin") != "generated_latex"
            or result.get("kind") != "draft"
            or result.get("task_inputs") != task["inputs"]
            or result.get("base_checkpoint") != task.get("base_checkpoint")
        ):
            raise PortalDataError(
                "flow_group_draft_mismatch", "分组版本与本岗资料或底稿不符。", 409
            )
        old = self._group_draft(task) or {}
        same_draft = old.get("id") == result.get("id") and old.get("draft_sha256") == result.get(
            "draft_sha256"
        )
        if (
            same_draft
            and task.get("group_mapping", {}).get("status") == "ready"
            and task.get("factual_review") == "groups_reviewed"
            and task.get("status") != "needs_recheck"
        ):
            return
        # Mapping failure suspends active confirmations but does not erase the
        # exact old-version receipts; a later verified capture may reuse them.
        previous = list(reversed(task.get("group_review_history", []))) + task.get(
            "group_reviews", []
        )
        old_groups = {group["id"]: group for group in old.get("review_groups", [])}
        receipts = []
        unchanged = set(result.get("verified_unchanged_group_ids", []))
        from .application_group_review import fixed_education_groups

        fixed_ids = {group["id"] for group in fixed_education_groups(result)}
        for group in result.get("review_groups", []):
            if group["id"] in fixed_ids:
                continue
            receipt = next(
                (
                    row
                    for row in previous
                    if row["group_id"] == group["id"]
                    and row["draft_id"] == old.get("id")
                    and row["draft_sha256"] == old.get("draft_sha256")
                    and row["input_revision"] == digest(task["inputs"])
                    and row.get("verified_by") == "user"
                    and row.get("source_revision")
                    == old.get("source_checkpoint", {}).get("source_revision")
                    and row["review_fingerprint"] == group.get("review_fingerprint")
                ),
                None,
            )
            if (
                receipt
                and (same_draft or group["id"] in unchanged)
                and old_groups.get(group["id"], {}).get("review_fingerprint")
                == group.get("review_fingerprint")
                and bool(old.get("group_context_revision"))
                and old.get("group_context_revision") == result.get("group_context_revision")
            ):
                if same_draft:
                    receipts.append(deepcopy(receipt))
                    continue
                inherited = deepcopy(receipt) | {
                    "id": uuid4().hex,
                    "draft_id": result["id"],
                    "draft_sha256": result["draft_sha256"],
                    "inherited_from": {
                        "receipt_id": receipt["id"],
                        "draft_id": receipt["draft_id"],
                        "draft_sha256": receipt["draft_sha256"],
                    },
                    "source_revision": result["source_checkpoint"]["source_revision"],
                    "preview_id": (result.get("group_preview") or {}).get("id"),
                    "at": time.time(),
                }
                receipts.append(inherited)
                task.setdefault("group_review_history", []).append(deepcopy(inherited))
        task["group_reviews"] = receipts
        task.update(
            draft_id=result["id"],
            draft_sha256=result["draft_sha256"],
            source_checkpoint=deepcopy(result["source_checkpoint"]),
            prism=deepcopy(result["source_checkpoint"])
            | {"draft_id": result["id"], "draft_sha256": result["draft_sha256"]},
            factual_review="pending",
            draft_review=None,
            resume_id=None,
            resume_sha256=None,
            materials_confirmed=False,
            status="draft_ready",
        )
        if not same_draft:
            task["artifacts"].append(
                {"stage": "resume", "adopted": True, "result": deepcopy(result)}
            )
        task["stages"]["resume"] = {
            "status": "complete",
            "artifact_id": result["id"],
            **{k: v for k, v in task["stages"]["resume"].items() if k == "latex_base"},
        }
        task["stages"]["export"] = {"status": "pending"}
        task["group_mapping"] = {"status": "ready"}
        self._group_completion(task, result)

    @staticmethod
    def _group_completion(task, draft):
        from .application_group_review import fixed_education_groups, has_unresolved_education

        fixed_ids = {group["id"] for group in fixed_education_groups(draft)}
        groups = draft.get("review_groups", [])
        reviewed = {
            row["group_id"]
            for row in task.get("group_reviews", [])
            if row["draft_id"] == draft["id"] and row["draft_sha256"] == draft["draft_sha256"]
        }
        task["factual_review"] = (
            "groups_reviewed"
            if (
                groups
                and not has_unresolved_education(draft)
                and (draft.get("group_preview") or {}).get("source_revision")
                == draft.get("source_checkpoint", {}).get("source_revision")
                and all(g["id"] in reviewed or g["id"] in fixed_ids for g in groups)
            )
            else "pending"
        )

    def _group_operation(
        self,
        task_id,
        task_revision,
        callback_name,
        *,
        payload=None,
        expected_source_revision=None,
        reconcile=False,
    ):
        with self.applications.write_lock():
            state, task = self._checked(task_id, task_revision)
            self._group_task(task)
            prior = task.get("group_read", {})
            if reconcile:
                if prior.get("status") != "needs_recheck":
                    raise PortalDataError(
                        "flow_group_recheck_required", "当前没有待核验的预览。", 409
                    )
                expected_source_revision = prior.get("expected_source_revision")
            else:
                self._group_guard_change(task)
            if callback_name != "group_prepare" and not self._group_draft(task).get(
                "group_session"
            ):
                raise PortalDataError(
                    "flow_group_session_required", "请先建立独立的分组审阅版本。", 409
                )
            callback = self.callbacks.get(callback_name)
            if callback is None:
                raise PortalDataError("prism_unavailable", "分组审阅服务尚未连接。", 409)
            attempt = uuid4().hex
            task["group_read"] = {
                "status": "running",
                "attempt_id": attempt,
                "expected_source_revision": expected_source_revision,
                "operation": callback_name,
            }
            self._save(state)
            request = deepcopy(task)
        outcome = None
        try:
            if callback_name == "group_capture":
                outcome = callback(
                    request, expected_source_revision=expected_source_revision, reconcile=reconcile
                )
            elif callback_name == "group_edit":
                outcome = {"draft": callback(request, payload), "status": "ready"}
            else:
                outcome = {"draft": callback(request), "status": "ready"}
            with self.applications.write_lock():
                state = self._load()
                task = self._task(state, task_id)
                if (
                    task.get("group_read", {}).get("attempt_id") != attempt
                    or task.get("revision") != request.get("revision")
                    or task.get("draft_id") != request.get("draft_id")
                    or task["inputs"] != request["inputs"]
                    or task.get("input_epoch", 0) != request.get("input_epoch", 0)
                ):
                    raise PortalDataError(
                        "flow_inputs_stale", "审阅期间任务已变化，请保留结果核验。", 409
                    )
                self._fresh(task)
                if outcome.get("draft"):
                    self._adopt_group_draft(task, outcome["draft"])
                else:
                    task.update(
                        group_reviews=[],
                        factual_review="pending",
                        draft_review=None,
                        materials_confirmed=False,
                        status="draft_ready",
                    )
                    task["group_mapping"] = {
                        "status": "mapping_required",
                        "message": outcome.get("mapping_error"),
                        "preview": outcome.get("preview"),
                    }
                task["group_read"] = {"status": "complete", "attempt_id": attempt}
                self._batch_after(state, task)
                self._save(state)
                observer = self.callbacks.get("observe_group_requests")
                if observer and outcome.get("draft"):
                    observer(deepcopy(task), deepcopy(outcome["draft"]))
                return deepcopy(task)
        except BaseException as error:
            with self.applications.write_lock():
                state = self._load()
                task = self._task(state, task_id)
                if task.get("group_read", {}).get("attempt_id") == attempt:
                    # Capture may already have produced a durable external receipt.
                    unknown = callback_name == "group_capture" and (
                        reconcile
                        or outcome is not None
                        or not isinstance(error, PortalDataError)
                        or error.code in {"prism_review_needs_recheck", "prism_review_busy"}
                    )
                    task["group_read"].update(
                        status="needs_recheck" if unknown else "failed",
                        error_code=getattr(error, "code", "flow_group_failed"),
                    )
                    if unknown:
                        task.update(
                            status="needs_recheck",
                            factual_review="pending",
                            materials_confirmed=False,
                        )
                    self._batch_after(state, task)
                    self._save(state)
            raise

    def begin_group_review(self, task_id, task_revision):
        return self._group_operation(task_id, task_revision, "group_prepare")

    def capture_group_review(self, task_id, task_revision, expected_source_revision):
        return self._group_operation(
            task_id,
            task_revision,
            "group_capture",
            expected_source_revision=expected_source_revision,
        )

    def recheck_group_review(self, task_id, task_revision):
        return self._group_operation(task_id, task_revision, "group_capture", reconcile=True)

    def edit_review_group(self, task_id, task_revision, payload):
        return self._group_operation(task_id, task_revision, "group_edit", payload=payload)

    def review_group(
        self, task_id, task_revision, draft_id, draft_sha256, group_id, review_fingerprint
    ):
        with self.applications.write_lock():
            state, task = self._checked(task_id, task_revision)
            self._group_task(task)
            self._group_guard_change(task)
            draft = self._group_draft(task)
            preview = (draft or {}).get("group_preview") or {}
            if (
                draft_id != task["draft_id"]
                or draft_sha256 != task["draft_sha256"]
                or task.get("group_mapping", {}).get("status") != "ready"
                or not preview
                or preview.get("source_revision") != task["prism"]["source_revision"]
            ):
                raise PortalDataError(
                    "flow_group_preview_required", "请先读取同源预览，再确认当前经历组。", 409
                )
            self.verify_prism_source(task)
            verifier = self.callbacks.get("verify_draft")
            if verifier:
                verifier(task)
            group = next((g for g in draft.get("review_groups", []) if g["id"] == group_id), None)
            if not group or group.get("review_fingerprint") != review_fingerprint:
                raise PortalDataError("flow_group_changed", "经历组已变化，请核对当前版本。", 409)
            from .application_group_review import fixed_education_groups

            if group_id in {item["id"] for item in fixed_education_groups(draft)}:
                # Reuse a documentary fact without inventing a human decision.
                return deepcopy(task)
            receipt = {
                "id": uuid4().hex,
                "group_id": group_id,
                "review_fingerprint": review_fingerprint,
                "draft_id": draft_id,
                "draft_sha256": draft_sha256,
                "input_revision": digest(task["inputs"]),
                "source_revision": task["prism"]["source_revision"],
                "preview_id": preview["id"],
                "verified_by": "user",
                "at": time.time(),
            }
            existing = next(
                (r for r in task.get("group_reviews", []) if r.get("group_id") == group_id), None
            )
            if existing and all(
                existing.get(k) == receipt.get(k)
                for k in (
                    "group_id",
                    "review_fingerprint",
                    "draft_id",
                    "draft_sha256",
                    "input_revision",
                    "source_revision",
                    "preview_id",
                    "verified_by",
                )
            ):
                return deepcopy(task)
            task.update(
                resume_id=None, resume_sha256=None, materials_confirmed=False, status="draft_ready"
            )
            task["stages"]["export"] = {"status": "pending"}
            task["group_reviews"] = [
                r for r in task.get("group_reviews", []) if r["group_id"] != group_id
            ] + [receipt]
            task.setdefault("group_review_history", []).append(deepcopy(receipt))
            self._group_completion(task, draft)
            self._batch_after(state, task)
            self._save(state)
            observer = self.callbacks.get("observe_group_confirmation")
            if observer:
                observer(deepcopy(task), deepcopy(group))
            return deepcopy(task)

    def prepare_automatic_materials(
        self,
        task_id,
        task_revision,
        project_root=None,
        main=None,
        *,
        retained_draft_id=None,
        retained_draft_sha256=None,
    ):
        """Select an existing base for ordinary technical generation, without human review."""
        with self.applications.write_lock():
            state, task = self._checked(task_id, task_revision)
            self._batch_guard_change(state, task)
            retained = None
            if retained_draft_id is not None or retained_draft_sha256 is not None:
                if (
                    not isinstance(retained_draft_id, str)
                    or re.fullmatch(r"[a-f0-9]{32}", retained_draft_id) is None
                    or not isinstance(retained_draft_sha256, str)
                    or re.fullmatch(r"[a-f0-9]{64}", retained_draft_sha256) is None
                ):
                    raise PortalDataError("flow_draft_mismatch", "人工内容基线版本不能核验。", 409)
                retained = {"id": retained_draft_id, "draft_sha256": retained_draft_sha256}
            if task.get("automatic_materials"):
                if retained is not None and retained != task.get("retained_baseline"):
                    raise PortalDataError(
                        "flow_latex_base_blocked", "已绑定材料不能替换人工基线。", 409
                    )
                self._fresh(task)
                return deepcopy(task)
            if (
                task.get("origin") == "existing_latex"
                or task.get("worker_ref")
                or task["status"] in {"cancelled", "needs_recheck"}
                or task["stages"]["analysis"]["status"] != "complete"
                or any(
                    row["status"] in {"queued", "running", "needs_recheck"}
                    for row in task["stages"].values()
                )
            ):
                raise PortalDataError(
                    "flow_latex_base_blocked", "请先完成分析并核验已有阶段。", 409
                )
            self._fresh(task, stage="analysis")
            reader = self.callbacks.get("prism_source")
            binding = task.get("latex_base")
            if project_root is not None or main is not None:
                if reader is None or not project_root or not main:
                    raise PortalDataError(
                        "flow_latex_base_required", "请提供已有完整 LaTeX 底稿。", 409
                    )
                options = (
                    {"source_policy": "generated-latex-project/v1"}
                    if task.get("material_contract") == "content-writing/v1"
                    else {}
                )
                binding = reader(Path(project_root), main, **options)
            if binding is None:
                provider = self.callbacks.get("automatic_latex_base")
                binding = provider(deepcopy(task)) if provider else None
            if not binding:
                raise PortalDataError(
                    "flow_latex_base_required", "缺少已有完整 LaTeX 底稿，请补充。", 409
                )
            if retained is not None:
                provider = self.callbacks.get("retained_draft")
                baseline = (
                    provider(deepcopy(task) | {"retained_baseline": retained}) if provider else None
                )
                from .application_resume import validate_retained_template

                validate_retained_template(task, baseline, binding)
                task["retained_baseline"] = retained
            if task.get("latex_base") and task["latex_base"] != binding:
                task.setdefault("latex_base_history", []).append(deepcopy(task["latex_base"]))
            task.update(automatic_materials=True, latex_base=deepcopy(binding))
            task["stages"].setdefault("export", {"status": "pending"})
            self.verify_latex_base(task)
            self._save(state)
            return deepcopy(task)

    def bind_latex_base(self, task_id, task_revision, project_root, main):
        """Bind an explicitly selected existing source without compiling or generating."""
        with self.applications.write_lock():
            state, task = self._checked(task_id, task_revision)
            self._batch_guard_change(state, task)
            if (
                not self.preparation_only
                or task.get("origin") == "existing_latex"
                or task["status"] in {"cancelled", "needs_recheck"}
                or task.get("worker_ref")
                or task.get("worker_preparation", {}).get("status") == "pending"
                or task["stages"]["analysis"]["status"] != "complete"
                or any(
                    stage["status"] in {"queued", "running", "needs_recheck"}
                    for stage in task["stages"].values()
                )
            ):
                raise PortalDataError(
                    "flow_latex_base_blocked",
                    "当前任务不能更换底稿，请先完成分析并核验已有阶段。",
                    409,
                )
            self._fresh(task, stage="analysis")
            callback = self.callbacks.get("prism_source")
            if callback is None:
                raise PortalDataError("prism_unavailable", "LaTeX 源读取服务尚未连接。", 409)
            options = (
                {"source_policy": "generated-latex-project/v1"}
                if task.get("material_contract") == "content-writing/v1"
                else {}
            )
            binding = callback(Path(project_root), main, **options)
            if binding == task.get("latex_base"):
                return deepcopy(task)
            if task.get("latex_base"):
                task.setdefault("latex_base_history", []).append(deepcopy(task["latex_base"]))
            if task.get("prism"):
                task.setdefault("prism_history", []).append(task.pop("prism"))
            task.update(
                latex_base=binding,
                input_epoch=task.get("input_epoch", 0) + 1,
                status="analysis_ready",
                draft_id=None,
                draft_sha256=None,
                draft_review=None,
                resume_id=None,
                resume_sha256=None,
                materials_confirmed=False,
            )
            for key in ("origin", "factual_review", "source_checkpoint", "base_checkpoint"):
                task.pop(key, None)
            task.pop("experience_handoff", None)
            task["stages"]["resume"] = {"status": "pending"}
            task["stages"]["export"] = {"status": "pending"}
            self._batch_after(state, task)
            self._save(state)
            return deepcopy(task)

    def _prism_editable(self, task):
        self._fresh(task)
        self._group_guard_change(task)
        if (
            not (self.preparation_only or task.get("automatic_materials"))
            or not task.get("draft_id")
            or task.get("worker_ref")
            or task["status"] == "cancelled"
            or any(
                stage["status"] in {"queued", "running", "needs_recheck"}
                for stage in task["stages"].values()
            )
        ):
            raise PortalDataError(
                "prism_review_blocked", "当前任务不能更换审阅源，请先核验已有阶段。", 409
            )

    def begin_prism_edit(self, task_id, task_revision):
        """Hand the existing project to the user until an explicit return."""
        with self.applications.write_lock():
            state, task = self._checked(task_id, task_revision)
            session = task.get("prism_edit") or {}
            if session.get("status") in {"editing", "finishing"}:
                return deepcopy(task)
            if (
                not task.get("automatic_materials")
                or task.get("origin") != "generated_latex"
                or not task.get("draft_id")
                or task["status"] == "cancelled"
                or any(
                    stage["status"] in {"queued", "running"} for stage in task["stages"].values()
                )
            ):
                raise PortalDataError("prism_edit_blocked", "当前材料不能进入人工编辑。", 409)
            if task.get("worker_ref"):
                self._check_material_preparation(task)
                update = self._stage_material_update(task, self.material_update_inputs(task))
                # The original page continues to own its old PDF until the
                # existing material-update transaction verifies and commits it.
                update.pop("candidate", None)
                update.pop("editable_draft", None)
            callback = self.callbacks.get("prism_edit_begin")
            if callback is None:
                raise PortalDataError("prism_unavailable", "Prism 人工编辑暂不可用。", 409)
            if session:
                task.setdefault("prism_edit_history", []).append(deepcopy(session))
            opening_id = uuid4().hex
            task["prism_edit"] = {
                "id": opening_id,
                "status": "editing",
                "opening": True,
                "parent_draft_id": task["draft_id"],
                "parent_draft_sha256": task["draft_sha256"],
            }
            task["material_source_state"] = "editing"
            self._save(state)
            request = deepcopy(task)
        try:
            session = callback(request)
        except Exception as error:
            with self.applications.write_lock():
                state = self._load()
                task = self._task(state, task_id)
                if task.get("prism_edit", {}).get("id") == opening_id:
                    task["prism_edit"].update(
                        status="open_failed",
                        error_code=getattr(error, "code", "prism_open_unknown"),
                    )
                    task["material_source_state"] = "open_failed"
                    self._save(state)
            raise
        with self.applications.write_lock():
            state = self._load()
            task = self._task(state, task_id)
            if (
                task["status"] == "cancelled"
                or task.get("prism_edit", {}).get("id") != opening_id
                or task.get("draft_id") != request["draft_id"]
                or task.get("draft_sha256") != request["draft_sha256"]
                or not isinstance(session, dict)
                or session.get("status") != "editing"
                or session.get("parent_draft_id") != task["draft_id"]
                or session.get("parent_draft_sha256") != task["draft_sha256"]
                or session.get("task_inputs") != task["inputs"]
                or not isinstance(session.get("id"), str)
            ):
                raise PortalDataError("prism_edit_mismatch", "人工编辑交接版本不符。", 409)
            task["prism_edit"] = deepcopy(session)
            self._save(state)
            return deepcopy(task)

    def finish_prism_edit(self, task_id, task_revision):
        """Read one explicit return; do not repeat content review or compilation."""
        with self.applications.write_lock():
            state, task = self._checked(task_id, task_revision)
            if task["status"] == "cancelled":
                raise PortalDataError("flow_cancelled", "任务已取消，人工源与旧终稿已保留。", 409)
            session = task.get("prism_edit") or {}
            if session.get("opening"):
                raise PortalDataError(
                    "prism_edit_opening", "正在连接原 Prism 项目，请等待读回。", 409
                )
            if session.get("status") not in {"editing", "finishing"}:
                return deepcopy(task)
            callback = self.callbacks.get("prism_edit_finish")
            if callback is None:
                raise PortalDataError("prism_unavailable", "人工编辑返回暂不可用。", 409)
            if task.get("worker_ref"):
                self._check_material_preparation(task)
            task["prism_edit"]["status"] = "finishing"
            task["material_source_state"] = "proofreading"
            self._save(state)
            request = deepcopy(task)
        try:
            result = callback(request)
        except Exception as error:
            with self.applications.write_lock():
                state = self._load()
                task = self._task(state, task_id)
                if task.get("prism_edit", {}).get("id") == session["id"]:
                    task["prism_edit"]["error_code"] = getattr(
                        error, "code", "prism_edit_result_unknown"
                    )
                    task["material_source_state"] = "return_needs_recheck"
                    self._save(state)
            raise
        with self.applications.write_lock():
            state = self._load()
            task = self._task(state, task_id)
            finished = result.get("prism_edit") or {}
            if (
                task["status"] == "cancelled"
                or task.get("prism_edit", {}).get("id") != session["id"]
                or task.get("prism_edit", {}).get("status") != "finishing"
                or task.get("draft_id") != request["draft_id"]
                or task.get("draft_sha256") != request["draft_sha256"]
                or finished.get("id") != session["id"]
                or finished.get("status")
                not in {"complete", "proofreading_unavailable", "source_changed"}
                or result.get("kind") != "draft"
                or result.get("material_version_contract") != "local-material/v1"
                or result.get("application_id") != task["application_id"]
                or result.get("task_inputs") != task["inputs"]
            ):
                raise PortalDataError("prism_edit_mismatch", "人工返回与当前材料版本不符。", 409)
            if task.get("worker_ref") and task.get("material_update"):
                update = task["material_update"]
                update.update(
                    editable_draft={
                        key: deepcopy(value) for key, value in result.items() if key != "prism_edit"
                    },
                    explicit_source=True,
                )
                task["prism_edit"] = deepcopy(finished)
                task["material_source_state"] = (
                    "unexported_changes" if finished["status"] == "complete" else finished["status"]
                )
                task["artifacts"].append(
                    {
                        "stage": "resume",
                        "adopted": False,
                        "inputs": deepcopy(task["inputs"]),
                        "result": deepcopy(result),
                    }
                )
                self._save(state)
                return deepcopy(task)
            task.update(
                draft_id=result["id"],
                draft_sha256=result["draft_sha256"],
                source_checkpoint=deepcopy(result["source_checkpoint"]),
                material_version_contract="local-material/v1",
                prism_edit=deepcopy(finished),
                material_source_state=(
                    "unexported_changes" if finished["status"] == "complete" else finished["status"]
                ),
            )
            from .application_resume import material_prism_binding

            task["prism"] = material_prism_binding(result)
            task["stages"]["resume"] = {"status": "complete", "artifact_id": result["id"]}
            task["stages"]["export"] = {"status": "pending"}
            task["artifacts"].append(
                {
                    "stage": "resume",
                    "adopted": True,
                    "inputs": deepcopy(task["inputs"]),
                    "result": deepcopy(result),
                }
            )
            self._save(state)
            return deepcopy(task)

    def capture_prism_result(self, task_id, task_revision):
        """Adopt an existing successful result; this action never starts a build."""
        with self.applications.write_lock():
            state, task = self._checked(task_id, task_revision)
            self._group_guard_change(task)
            if not local_materials(task) or task["status"] == "cancelled":
                raise PortalDataError("prism_result_blocked", "当前材料没有本地结果接回入口。", 409)
            callback = self.callbacks.get("prism_result_capture")
            if callback is None:
                raise PortalDataError("prism_unavailable", "Prism 结果读取暂不可用。", 409)
            if any(stage["status"] in {"queued", "running"} for stage in task["stages"].values()):
                raise PortalDataError("prism_result_blocked", "请等待当前材料操作完成。", 409)
            request = deepcopy(task)
            update = task.get("material_update") or {}
            bound_edit = update.get("editable_draft") if task.get("worker_ref") else None
            if task.get("worker_ref") and (not bound_edit or update.get("status") != "staged"):
                raise PortalDataError(
                    "prism_bound_edit_required",
                    "原页已绑定当前 PDF；请先完成 Prism 编辑，再接回候选并继续原页。",
                    409,
                )
            if bound_edit:
                self._adopt_automatic_edit(request, bound_edit)
                request["material_version_contract"] = "local-material/v1"
                request.pop("material_update", None)
            previous = task.get("prism_capture") or {}
            retry = (
                bound_edit
                and previous.get("status") in {"reading", "waiting"}
                and all(
                    previous.get(key) == request.get(key) for key in ("draft_id", "draft_sha256")
                )
            )
            export_id = previous["id"] if retry else uuid4().hex
            task["prism_capture"] = {
                "id": export_id,
                "status": "reading",
                "draft_id": request["draft_id"],
                "draft_sha256": request["draft_sha256"],
            }
            request["prism_capture"] = deepcopy(task["prism_capture"])
            self._save(state)
        try:
            result = callback(request, export_id)
        except Exception as error:
            with self.applications.write_lock():
                state = self._load()
                task = self._task(state, task_id)
                if task.get("prism_capture", {}).get("id") == export_id:
                    task["prism_capture"].update(
                        status="waiting", error_code=getattr(error, "code", "prism_result_unknown")
                    )
                    task["material_source_state"] = "waiting_for_result"
                    self._save(state)
            raise
        with self.applications.write_lock():
            state = self._load()
            task = self._task(state, task_id)
            artifact = {
                "stage": "export",
                "adopted": False,
                "inputs": deepcopy(request["inputs"]),
                "attempt_id": export_id,
                "result": deepcopy(result),
            }
            task["artifacts"].append(artifact)
            current_edit = (task.get("material_update") or {}).get("editable_draft")
            current_draft = current_edit if bound_edit else task
            if (
                task["status"] == "cancelled"
                or task.get("prism_capture", {}).get("id") != export_id
                or not current_draft
                or (current_draft.get("id") if bound_edit else current_draft.get("draft_id"))
                != request["draft_id"]
                or current_draft.get("draft_sha256") != request["draft_sha256"]
                or task.get("prism_edit", {}).get("status") in {"editing", "finishing"}
            ):
                self._save(state)
                raise PortalDataError(
                    "prism_result_changed", "较旧结果已保留，不能覆盖新材料。", 409
                )
            checking = deepcopy(request) if bound_edit else deepcopy(task)
            checking["stages"]["export"] = {"status": "running", "attempt_id": export_id}
            self._export_result(checking, result)
            if bound_edit:
                checking["prism_capture"]["status"] = "complete"
                checking["artifacts"].append(deepcopy(artifact) | {"adopted": True})
                self._adopt_export(checking, result)
                # Archive adoption is separate from replacing the original
                # page's active material binding.
                artifact["adopted"] = True
                self._save(state)
                self._bind_current_materials(checking)
                task["material_update"]["candidate"] = checking
                task["prism_capture"]["status"] = "complete"
                task["material_source_state"] = "candidate_ready"
                self._save(state)
                return deepcopy(task)
            task["stages"]["export"] = checking["stages"]["export"]
            artifact["adopted"] = True
            task["prism_capture"]["status"] = "complete"
            self._adopt_export(task, result)
            self._save_material_result(state, task)
            return deepcopy(task)

    def begin_automatic_edit(self, task_id, task_revision):
        """Open an independently saved complete source; no group acceptance is recorded."""
        with self.applications.write_lock():
            state, task = self._checked(task_id, task_revision)
            self._group_guard_change(task)
            if task.get("worker_ref") and task.get("automatic_materials"):
                return self._worker_view(self._editable_material_update(state, task))
            self._prism_editable(task)
            if not task.get("automatic_materials") or task.get("origin") != "generated_latex":
                raise PortalDataError(
                    "flow_automatic_edit_required", "当前任务没有可编辑的完整源。", 409
                )
            self.verify_prism_source(task)
            if (self._group_draft(task) or {}).get("group_session"):
                return deepcopy(task)
            callback = self.callbacks.get("automatic_edit_prepare")
            if callback is None:
                raise PortalDataError("flow_stage_unavailable", "完整源编辑暂不可用。", 409)
            result = callback(deepcopy(task))
            self._adopt_automatic_edit(task, result)
            self._save(state)
            return deepcopy(task)

    def save_automatic_source(self, task_id, task_revision, expected_source_revision, latex_source):
        """Retain one explicit manual source edit without overwriting old source or PDF."""
        with self.applications.write_lock():
            state, task = self._checked(task_id, task_revision)
            self._group_guard_change(task)
            if task.get("worker_ref") and task.get("automatic_materials"):
                return self._worker_view(
                    self._editable_material_update(
                        state, task, latex_source, expected_source_revision
                    )
                )
            self._prism_editable(task)
            if not task.get("automatic_materials") or task.get("origin") != "generated_latex":
                raise PortalDataError(
                    "flow_automatic_edit_required", "请先打开当前完整源编辑版本。", 409
                )
            source = self.verify_prism_source(task)
            if source is None or source["source_revision"] != expected_source_revision:
                raise PortalDataError(
                    "prism_source_changed", "源版本已变化，请保留编辑并重新读取。", 409
                )
            if (self._group_draft(task) or {}).get("latex_source") == latex_source:
                return deepcopy(task)
            callback = self.callbacks.get("automatic_source_save")
            if callback is None:
                raise PortalDataError("flow_stage_unavailable", "完整源保存暂不可用。", 409)
            result = callback(deepcopy(task), latex_source)
            self._adopt_automatic_edit(task, result)
            task["manual_source"] = deepcopy(result["manual_source"])
            from .application_resume import material_source_binding

            task["manual_latex_base"] = material_source_binding(result)
            self._save(state)
            return deepcopy(task)

    @staticmethod
    def _adopt_automatic_edit(task, result):
        from .application_resume import material_prism_binding

        if (
            result.get("kind") != "draft"
            or result.get("origin") != "generated_latex"
            or result.get("task_inputs") != task["inputs"]
            or result.get("base_checkpoint") != task.get("base_checkpoint")
        ):
            raise PortalDataError("flow_draft_mismatch", "编辑版本与当前岗位或来源不符。", 409)
        task.update(
            draft_id=result["id"],
            draft_sha256=result["draft_sha256"],
            draft_review=None,
            source_checkpoint=deepcopy(result["source_checkpoint"]),
            prism=material_prism_binding(result),
            status="draft_ready",
            resume_id=None,
            resume_sha256=None,
            materials_confirmed=False,
            factual_review="pending",
        )
        task.pop("material_binding", None)
        task.pop("pdf_reuse", None)
        task["stages"]["resume"] = {
            "status": "complete",
            "artifact_id": result["id"],
            **{k: v for k, v in task["stages"]["resume"].items() if k == "latex_base"},
        }
        task["stages"]["export"] = {"status": "pending"}
        task["artifacts"].append(
            {
                "stage": "resume",
                "adopted": True,
                "inputs": deepcopy(task["inputs"]),
                "result": deepcopy(result),
            }
        )

    def _bound_material_draft(self, task):
        update = task["material_update"]
        old = update["old"]
        result, material_fields = self.callbacks["bound_resume_draft"](task)
        candidate = deepcopy(old)
        candidate.update(
            inputs=deepcopy(update["inputs"]), input_epoch=old.get("input_epoch", 0) + 1
        )
        candidate.update(material_fields)
        self._adopt_automatic_edit(candidate, result)
        return candidate

    def prepare_bound_candidate(self, task):
        """Build a separate candidate, retaining its original export attempt."""
        update = task["material_update"]
        old = update["old"]
        prepared = update.get("candidate") or {}
        edited = update.get("editable_draft") or {}
        if (
            update.get("explicit_source")
            and prepared.get("stages", {}).get("export", {}).get("status") == "complete"
            and prepared.get("inputs") == update["inputs"]
            and prepared.get("draft_id") == edited.get("id")
            and prepared.get("draft_sha256") == edited.get("draft_sha256")
        ):
            self.callbacks["bound_candidate_source"](prepared)
            self.callbacks["verify_materials"](prepared)
            return deepcopy(prepared)
        if update.get("reconcile_export"):
            candidate = deepcopy(update["candidate"])
            export_id = candidate["stages"]["export"]["attempt_id"]
            exported = self.callbacks["reconcile_export"](candidate)
            if exported.get("status") == "not_complete":
                raise PortalDataError(
                    "resume_export_needs_recheck", "原导出尝试仍未完成，请保留回执。", 409
                )
        else:
            candidate = self._bound_material_draft(task)
            export_id = uuid4().hex
            candidate["stages"]["export"] = {
                "status": "running",
                "attempt_id": export_id,
                "configuration_revision": self._export_configuration(candidate),
            }
            # Save the original export attempt before its external side effect.
            with self.applications.write_lock():
                state = self._load()
                current = self._task(state, task["id"])
                active = current.get("material_update") or {}
                try:
                    if (
                        self._closed.is_set()
                        or current["status"] == "cancelled"
                        or active.get("id") != update["id"]
                        or active.get("status") != "preparing"
                        or self.material_update_inputs(current) != update["inputs"]
                    ):
                        raise PortalDataError(
                            "bound_material_update_changed", "材料更新已变化。", 409
                        )
                    self._check_material_preparation(current)
                except Exception:
                    # The completed source is historical evidence, even when a
                    # later cancellation or permission change prevents its build.
                    current["artifacts"].extend(
                        deepcopy(row) | {"adopted": False}
                        for row in candidate["artifacts"][len(old["artifacts"]) :]
                    )
                    self._save(state)
                    raise
                current["artifacts"].extend(
                    deepcopy(candidate["artifacts"][len(old["artifacts"]) :])
                )
                active["candidate"] = deepcopy(candidate)
                self._save(state)
            exported = self.callbacks["export"](candidate)
        self._export_result(candidate, exported)
        self._adopt_export(candidate, exported)
        candidate["artifacts"].append(
            {
                "stage": "export",
                "attempt_id": export_id,
                "adopted": True,
                "inputs": deepcopy(candidate["inputs"]),
                "result": exported,
            }
        )
        return candidate

    def import_latex(self, application_id, application_revision, project_root, main):
        """Create a dedicated preparation task around immutable existing source bytes."""
        with self.applications.write_lock():
            self._writable()
            if not self.preparation_only:
                raise PortalDataError(
                    "flow_preparation_required", "已有 LaTeX 接入仅用于材料准备。", 409
                )
            state = self._load()
            for prior in state["tasks"]:
                if prior["application_id"] == application_id:
                    if prior.get("codex_handoff_ref") or prior.get("codex_handoff_attempt"):
                        raise PortalDataError(
                            "flow_handoff_bound", "已有上传记录已接回；请保留原任务和附件。", 409
                        )
                    self._group_guard_change(prior)
            batch = state.get("preparation_batch")
            if (batch and batch.get("control") != "cancelled") or any(
                row.get("export_recoveries")
                or row.get("worker_ref")
                or any(
                    stage["status"] in {"queued", "running", "needs_recheck"}
                    for stage in row["stages"].values()
                )
                for row in state["tasks"]
            ):
                raise PortalDataError(
                    "flow_latex_import_blocked",
                    "先保留并核验已有任务，不能替换活动批次或未知结果。",
                    409,
                )
            callback = self.callbacks.get("import_latex")
            snapshot = self.callbacks.get("prism_source")
            if callback is None or snapshot is None:
                raise PortalDataError("prism_unavailable", "已有 LaTeX 接入服务尚未连接。", 409)
            source = snapshot(Path(project_root), main)
            application = self.applications.get_application(application_id)
            if application["revision"] != application_revision:
                raise PortalDataError("conflict", "投递记录已变化，请重新打开。", 409)
            task = self._new_task(application, self._identity(application))
            task.update(
                origin="existing_latex",
                factual_review="pending",
                draft_review=None,
                export_authorization=None,
                import_status={"status": "pending"},
            )
            state["tasks"].append(task)
            self._save(state)
            try:
                result = callback(deepcopy(task), deepcopy(source))
                self._validate_latex_import(result, task, source)
                if snapshot(Path(project_root), main) != source:
                    raise PortalDataError(
                        "prism_source_changed", "LaTeX 源已变化，请重新接入。", 409
                    )
                state, task = self._checked(task["id"], task["revision"])
                self._fresh(task)
            except Exception as error:
                state, failed = self._checked(task["id"], task["revision"])
                code = (
                    error.code if isinstance(error, PortalDataError) else "flow_latex_import_failed"
                )
                failed.update(
                    status="failed", import_status={"status": "failed", "error_code": code}
                )
                failed["stages"]["resume"] = {"status": "failed", "error_code": code}
                self._save(state)
                raise
            task.update(
                source_checkpoint=deepcopy(result["source_checkpoint"]),
                draft_id=result["id"],
                draft_sha256=result["draft_sha256"],
                status="draft_ready",
                import_status={"status": "complete"},
                prism=source | {"draft_id": result["id"], "draft_sha256": result["draft_sha256"]},
            )
            task["stages"]["resume"] = {"status": "complete", "artifact_id": result["id"]}
            task["stages"]["export"] = {"status": "pending"}
            task["artifacts"].append(
                {
                    "stage": "resume",
                    "attempt_id": result["id"],
                    "result": result,
                    "inputs": deepcopy(task["inputs"]),
                    "adopted": True,
                }
            )
            self._save(state)
            return deepcopy(task)

    @staticmethod
    def _validate_latex_import(result, task, source):
        if (
            not isinstance(result, dict)
            or result.get("kind") != "draft"
            or result.get("origin") != "existing_latex"
            or result.get("factual_review") != "pending"
            or result.get("model_mode") != "not_used"
            or result.get("application_id") != task["application_id"]
            or result.get("revision") != task["application_revision"]
            or result.get("analysis_binding") != {}
            or result.get("task_inputs") != task["inputs"]
            or not isinstance(result.get("id"), str)
            or re.fullmatch(r"[a-f0-9]{32}", result["id"]) is None
            or not isinstance(result.get("draft_sha256"), str)
            or re.fullmatch(r"[a-f0-9]{64}", result["draft_sha256"]) is None
            or any(result.get("source_checkpoint", {}).get(k) != v for k, v in source.items())
        ):
            raise PortalDataError(
                "flow_draft_mismatch", "已有 LaTeX 检查点与岗位或源版本不符。", 409
            )

    def authorize_latex_export(self, task_id, task_revision, draft_id, draft_sha256):
        with self.applications.write_lock():
            state, task = self._checked(task_id, task_revision)
            self._prism_editable(task)
            if (
                task.get("origin") != "existing_latex"
                or task.get("draft_id") != draft_id
                or task.get("draft_sha256") != draft_sha256
            ):
                raise PortalDataError("flow_draft_mismatch", "请核验当前接入的 LaTeX 版本。", 409)
            self.verify_prism_source(task)
            verifier = self.callbacks.get("verify_draft")
            if verifier is None:
                raise PortalDataError("flow_draft_unavailable", "草稿检查点暂不能核验。", 409)
            verifier(deepcopy(task))
            task["export_authorization"] = {
                "status": "authorized",
                "scope": "technical_export",
                "actor": "user",
                "factual_review": "pending",
                "draft_id": draft_id,
                "draft_sha256": draft_sha256,
                "input_revision": digest(task["inputs"]),
                "prism_source_revision": task["prism"]["source_revision"],
                "at": time.time(),
            }
            task.setdefault("export_authorizations", []).append(
                deepcopy(task["export_authorization"])
            )
            self._save(state)
            return deepcopy(task)

    def bind_prism(self, task_id, task_revision, project_root, main):
        with self.applications.write_lock():
            state, task = self._checked(task_id, task_revision)
            self._prism_editable(task)
            if task.get("origin") == "existing_latex":
                raise PortalDataError(
                    "flow_latex_reimport_required", "请重新接入保存后的 LaTeX，旧版会保留。", 409
                )
            if task.get("origin") == "generated_latex":
                raise PortalDataError(
                    "flow_group_review_required",
                    "请使用分组审阅读取当前完整 LaTeX，保留分组审核记录。",
                    409,
                )
            callback = self.callbacks.get("prism_source")
            if callback is None:
                raise PortalDataError("prism_unavailable", "LaTeX 审阅服务尚未连接。", 409)
            binding = callback(Path(project_root), main) | {
                "draft_id": task["draft_id"],
                "draft_sha256": task["draft_sha256"],
            }
            if task.get("prism") and all(
                task["prism"].get(key) == value for key, value in binding.items()
            ):
                return deepcopy(task)
            if task.get("prism"):
                task.setdefault("prism_history", []).append(deepcopy(task["prism"]))
            task.update(
                prism=binding,
                draft_review=None,
                status="draft_ready",
                resume_id=None,
                resume_sha256=None,
                materials_confirmed=False,
            )
            task["stages"]["export"] = {"status": "pending"}
            self._save(state)
            return deepcopy(task)

    def refresh_prism(self, task_id, task_revision):
        state, task = self._read_checked(task_id, task_revision)
        binding = task.get("prism")
        if not binding:
            raise PortalDataError("prism_binding_required", "请先绑定专用 LaTeX 项目。", 409)
        return self.bind_prism(task_id, task_revision, binding["project_root"], binding["main"])

    def open_prism(self, task_id, task_revision):
        with self.applications.write_lock():
            state, task = self._checked(task_id, task_revision)
            self._prism_editable(task)
            if not task.get("prism") or not self.callbacks.get("prism_open"):
                raise PortalDataError("prism_unavailable", "请先绑定并启动专用 Prism 项目。", 409)
            url = self.callbacks["prism_open"](deepcopy(task["prism"]))
            task["prism"]["editor_url"] = url
            self._save(state)
            return deepcopy(task)

    def _export_configuration(self, task):
        if local_materials(task):
            return "local-material/v1"
        callback = self.callbacks.get(
            "prism_export_configuration" if task.get("prism") else "export_configuration"
        )
        if callback is None:
            raise PortalDataError("flow_stage_unavailable", "导出配置暂不能核验。", 409)
        return callback()

    def review_draft(self, task_id, task_revision, draft_id, draft_sha256):
        with self.applications.write_lock():
            state, task = self._checked(task_id, task_revision)
            if task.get("origin") in {"existing_latex", "generated_latex"}:
                raise PortalDataError(
                    "flow_factual_review_required",
                    "完整 LaTeX 需按经历分组审核；当前入口不能替代。",
                    409,
                )
            self._fresh(task)
            if (
                not self.preparation_only
                or task["status"] != "draft_ready"
                or task.get("draft_id") != draft_id
                or task.get("draft_sha256") != draft_sha256
            ):
                raise PortalDataError("flow_draft_mismatch", "请审阅当前版本的岗位草稿。", 409)
            verifier = self.callbacks.get("verify_draft")
            if verifier is None:
                raise PortalDataError("flow_draft_unavailable", "草稿暂不能核验，请保留记录。", 409)
            verifier(deepcopy(task))
            self.verify_prism_source(task)
            result = next(
                row["result"]
                for row in reversed(task["artifacts"])
                if row.get("adopted")
                and row["stage"] == "resume"
                and row["result"]["id"] == draft_id
            )
            task["draft_review"] = {
                "status": "reviewed",
                "draft_id": draft_id,
                "draft_sha256": draft_sha256,
                "analysis_id": task["analysis_id"],
                "input_revision": digest(task["inputs"]),
                "actor": "user",
                "scope": "draft_review",
                "model_mode": result.get("model_mode", "unknown"),
                "at": time.time(),
            }
            if task.get("prism"):
                task["draft_review"]["prism_source_revision"] = task["prism"]["source_revision"]
            task.setdefault("draft_reviews", []).append(deepcopy(task["draft_review"]))
            self._batch_after(state, task)
            self._save(state)
            return deepcopy(task)

    def _reviewed_groups(self, task):
        from .application_group_review import group_review_snapshot

        self._group_guard_change(task)
        draft = self._group_draft(task)
        if (
            not self.preparation_only
            or task.get("origin") != "generated_latex"
            or task.get("group_mapping", {}).get("status") != "ready"
            or not draft
            or task.get("factual_review") != "groups_reviewed"
        ):
            raise PortalDataError(
                "flow_factual_review_required", "请先完成当前完整 LaTeX 的逐组事实审核。", 409
            )
        self.verify_prism_source(task)
        state = self.callbacks.get("group_state")
        if state is None:
            raise PortalDataError("flow_group_review_unavailable", "分组预览暂不能核验。", 409)
        current = state(deepcopy(task))
        if (
            current.get("pending_attempt_id")
            or current.get("live_source_revision") != task["prism"]["source_revision"]
        ):
            raise PortalDataError(
                "flow_group_preview_required", "请核验当前源与同源预览回执。", 409
            )
        verifier = self.callbacks.get("verify_draft")
        if verifier is None:
            raise PortalDataError("flow_draft_unavailable", "草稿暂不能核验。", 409)
        verifier(deepcopy(task))
        return group_review_snapshot(draft, task["inputs"], task.get("group_reviews", []))

    def _reviewed_draft(self, task):
        if local_materials(task):
            verifier = self.callbacks.get("verify_draft")
            if verifier is None:
                raise PortalDataError("flow_draft_unavailable", "草稿归档暂不能核验。", 409)
            verifier(deepcopy(task))
            return
        if task.get("automatic_materials") and task.get("origin") == "generated_latex":
            self.verify_prism_source(task)
            verifier = self.callbacks.get("verify_draft")
            if verifier is None:
                raise PortalDataError("flow_draft_unavailable", "草稿暂不能核验。", 409)
            verifier(deepcopy(task))
            return
        if task.get("origin") == "generated_latex":
            self._reviewed_groups(task)
            return
        review = task.get("draft_review") or {}
        self.verify_prism_source(task)
        if task.get("origin") == "existing_latex":
            authorization = task.get("export_authorization") or {}
            if (
                not self.preparation_only
                or not task.get("prism")
                or any(
                    authorization.get(key) != value
                    for key, value in {
                        "status": "authorized",
                        "scope": "technical_export",
                        "actor": "user",
                        "factual_review": "pending",
                        "draft_id": task.get("draft_id"),
                        "draft_sha256": task.get("draft_sha256"),
                        "input_revision": digest(task["inputs"]),
                        "prism_source_revision": task["prism"]["source_revision"],
                    }.items()
                )
            ):
                raise PortalDataError(
                    "flow_latex_export_authorization_required",
                    "请确认仅对当前 LaTeX 版本执行技术导出核验。",
                    409,
                )
            verifier = self.callbacks.get("verify_draft")
            if verifier is None:
                raise PortalDataError("flow_draft_unavailable", "草稿检查点暂不能核验。", 409)
            verifier(deepcopy(task))
            return
        if (
            task.get("prism")
            and review.get("prism_source_revision") != task["prism"]["source_revision"]
        ):
            raise PortalDataError("flow_draft_review_required", "请审阅当前 LaTeX 源版本。", 409)
        if not self.preparation_only or any(
            review.get(key) != value
            for key, value in {
                "status": "reviewed",
                "actor": "user",
                "scope": "draft_review",
                "draft_id": task.get("draft_id"),
                "draft_sha256": task.get("draft_sha256"),
                "analysis_id": task.get("analysis_id"),
                "input_revision": digest(task["inputs"]),
            }.items()
        ):
            raise PortalDataError("flow_draft_review_required", "请先审阅当前版本的岗位草稿。", 409)
        verifier = self.callbacks.get("verify_draft")
        if verifier is None or not task.get("draft_id") or not task.get("draft_sha256"):
            raise PortalDataError("flow_draft_unavailable", "草稿暂不能核验，请保留记录。", 409)
        verifier(deepcopy(task))

    def export_pdf(self, task_id, task_revision, draft_id, draft_sha256, *, retry=False):
        with self.applications.write_lock():
            _, task = self._checked(task_id, task_revision)
            if task.get("draft_id") != draft_id or task.get("draft_sha256") != draft_sha256:
                raise PortalDataError("flow_draft_mismatch", "请导出当前已审阅草稿。", 409)
            return self.start(task_id, task_revision, "export", retry=retry)

    def _export_result(self, task, result):
        stage = task["stages"]["export"]
        if result.get("material_version_contract") == "local-material/v1":
            if (
                not local_materials(task)
                or result.get("kind") != "pdf"
                or result.get("id") != stage.get("attempt_id")
                or result.get("application_id") != task["application_id"]
                or result.get("draft_id") != task.get("draft_id")
                or result.get("draft_sha256") != task.get("draft_sha256")
                or result.get("task_inputs") != task["inputs"]
                or result.get("source_checkpoint") != task.get("source_checkpoint")
                or not isinstance(result.get("pdf_sha256"), str)
                or re.fullmatch(r"[a-f0-9]{64}", result["pdf_sha256"]) is None
            ):
                raise PortalDataError("flow_export_mismatch", "已有 PDF 结果与当前源不符。", 409)
            return
        if stage.get("operation_kind") == "reuse_completed_review":
            if (
                result.get("operation_kind") != "reuse_completed_review"
                or result.get("review_snapshot_reuse") != stage.get("review_snapshot_reuse")
                or not result.get("review_snapshot_reuse")
            ):
                raise PortalDataError("flow_export_mismatch", "复用快照标识与本次记录不符。", 409)
        elif "operation_kind" in result or "review_snapshot_reuse" in result:
            raise PortalDataError("flow_export_mismatch", "导出操作类型与本次记录不符。", 409)
        if (
            result.get("export_configuration_revision") != self._export_configuration(task)
            or result.get("export_configuration_revision")
            != task["stages"]["export"]["configuration_revision"]
        ):
            raise PortalDataError(
                "flow_export_configuration_changed", "导出配置已变化，请保留旧版并明确重试。", 409
            )
        if (
            result.get("kind") != "pdf"
            or result.get("id") != task["stages"]["export"]["attempt_id"]
            or result.get("draft_id") != task.get("draft_id")
            or result.get("draft_sha256") != task.get("draft_sha256")
            or not isinstance(result.get("pdf_sha256"), str)
            or not re.fullmatch(r"[a-f0-9]{64}", result["pdf_sha256"])
        ):
            raise PortalDataError("flow_export_mismatch", "PDF 与本次草稿导出不符。", 409)
        self._reviewed_draft(task)
        if task.get("automatic_materials") and result.get("automatic_materials") is not True:
            raise PortalDataError("flow_export_mismatch", "自动导出回执类型不符。", 409)
        if (
            not task.get("automatic_materials")
            and task.get("origin") == "generated_latex"
            and result.get("group_review") != self._reviewed_groups(task)
        ):
            raise PortalDataError(
                "flow_export_mismatch", "PDF 未绑定当前完整源与逐组审核回执。", 409
            )

    def _adopt_export(self, task, result):
        if result.get("material_version_contract") == "local-material/v1":
            if task.get("resume_id") and task["resume_id"] != result["id"]:
                task.setdefault("final_pdf_history", []).append(
                    {"resume_id": task["resume_id"], "pdf_sha256": task["resume_sha256"]}
                )
            task["material_version_contract"] = "local-material/v1"
            task["material_source_state"] = "current"
        task["stages"]["export"].update(status="complete", artifact_id=result["id"])
        task["stages"]["export"].pop("error_code", None)
        task.update(
            resume_id=result["id"],
            resume_sha256=result["pdf_sha256"],
            status="resume_ready",
            materials_confirmed=False,
        )

    def _bind_current_materials(self, task):
        """Save a technical binding without adding a human acceptance record."""
        verifier = self.callbacks.get("verify_materials")
        if (
            not isinstance(task.get("resume_id"), str)
            or not task["resume_id"]
            or not isinstance(task.get("resume_sha256"), str)
            or not re.fullmatch(r"[a-f0-9]{64}", task["resume_sha256"])
            or verifier is None
        ):
            raise PortalDataError("flow_materials_required", "当前 PDF 暂不能核验。", 409)
        self._fresh(task)
        verifier(deepcopy(task))
        task["material_binding"] = {
            "actor": "system",
            "human_reviewed": False,
            "scope": "current_pdf_materials",
            "resume_id": task["resume_id"],
            "pdf_sha256": task["resume_sha256"],
            "input_revision": digest(task["inputs"]),
            "draft_id": task.get("draft_id"),
            "draft_sha256": task.get("draft_sha256"),
            "at": time.time(),
        }
        task.update(materials_confirmed=True, status="materials_ready")
        task.pop("material_binding_error", None)

    def _save_material_result(self, state, task):
        # Verification reads the adopted immutable result from the saved flow.
        self._save(state)
        if (
            (self.preparation_only or task.get("automatic_materials"))
            and task.get("origin") != "existing_latex"
            and task["status"] == "resume_ready"
        ):
            try:
                self._bind_current_materials(task)
            except (PortalDataError, OSError, ValueError) as error:
                task.update(
                    status="needs_recheck",
                    materials_confirmed=False,
                    material_binding_error=getattr(error, "code", "flow_materials_changed"),
                )
                task.pop("material_binding", None)
                task["stages"]["export"].update(
                    status="needs_recheck", error_code=task["material_binding_error"]
                )
            self._batch_after(state, task)
            self._save(state)
        observer = self.callbacks.get("observe_material_requests")
        if observer and task.get("resume_id") and not task.get("materials_confirmed"):
            observer(deepcopy(task), deepcopy(state["tasks"]))

    def adopt_review_snapshot(self, task_id, task_revision, review_version_id, expected_pdf_sha256):
        """Reuse a known snapshot while retaining the original unknown request."""
        with self.applications.write_lock():
            state, task = self._checked(task_id, task_revision)
            if (
                not self.preparation_only
                or task.get("origin") != "existing_latex"
                or task["status"] != "needs_recheck"
                or task["stages"].get("export", {}).get("status") != "needs_recheck"
                or task.get("worker_ref")
                or task.get("worker_preparation", {}).get("status") == "pending"
                or task.get("export_recoveries")
                or task.get("group_read", {}).get("status") in {"running", "needs_recheck"}
                or any(
                    stage["status"] in {"queued", "running"} for stage in task["stages"].values()
                )
                or not isinstance(review_version_id, str)
                or not re.fullmatch(r"[a-f0-9]{32}", review_version_id)
                or not isinstance(expected_pdf_sha256, str)
                or not re.fullmatch(r"[a-f0-9]{64}", expected_pdf_sha256)
            ):
                raise PortalDataError(
                    "flow_export_recheck_required", "当前任务不能复用严格快照。", 409
                )
            self._fresh(task)
            self._reviewed_draft(task)
            callback = self.callbacks.get("adopt_review_snapshot")
            if callback is None:
                raise PortalDataError("flow_stage_unavailable", "严格快照绑定服务尚未连接。", 409)
            prior = deepcopy(task["stages"]["export"])
            export_id = uuid4().hex
            result = callback(
                deepcopy(task),
                export_id=export_id,
                review_version_id=review_version_id,
                prior_export_id=prior["attempt_id"],
                expected_pdf_sha256=expected_pdf_sha256,
            )
            state, task = self._checked(task_id, task_revision)
            self._fresh(task)
            self._reviewed_draft(task)
            reuse = result.get("review_snapshot_reuse") if isinstance(result, dict) else None
            if (
                not isinstance(result, dict)
                or result.get("operation_kind") != "reuse_completed_review"
                or result.get("origin") != "existing_latex"
                or result.get("factual_review") != "pending"
                or result.get("application_id") != task["application_id"]
                or result.get("revision") != task["application_revision"]
                or result.get("task_inputs") != task["inputs"]
                or result.get("pdf_sha256") != expected_pdf_sha256
                or not isinstance(reuse, dict)
                or set(reuse) != {"schemaVersion", "kind", "receipt_sha256"}
                or reuse.get("schemaVersion") != 1
                or reuse.get("kind") != "known_snapshot_reuse"
                or not isinstance(reuse.get("receipt_sha256"), str)
                or not re.fullmatch(r"[a-f0-9]{64}", reuse["receipt_sha256"])
            ):
                raise PortalDataError("flow_export_mismatch", "严格快照与当前任务不符。", 409)
            task["stages"]["export"] = prior | {
                "attempt_id": export_id,
                "operation_kind": "reuse_completed_review",
                "review_snapshot_reuse": deepcopy(reuse),
            }
            self._export_result(task, result)
            task.setdefault("export_recoveries", []).append(
                {
                    "status": "needs_recheck",
                    "prior_export_stage": prior,
                    "replacement_export_id": export_id,
                    "operation_kind": "reuse_completed_review",
                    "review_version_id": review_version_id,
                    "expected_pdf_sha256": expected_pdf_sha256,
                    "review_snapshot_reuse": deepcopy(reuse),
                    "input_epoch": task.get("input_epoch", 0),
                    "inputs_revision": digest(task["inputs"]),
                    "at": time.time(),
                }
            )
            task["artifacts"].append(
                {
                    "stage": "export",
                    "attempt_id": export_id,
                    "result": result,
                    "inputs": deepcopy(task["inputs"]),
                    "adopted": True,
                }
            )
            self._adopt_export(task, result)
            self._save_material_result(state, task)
            return deepcopy(task)

    def recheck_export(self, task_id, task_revision):
        with self.applications.write_lock():
            state, task = self._checked(task_id, task_revision)
            if task["status"] == "cancelled":
                raise PortalDataError("flow_cancelled", "任务已取消，请保留原导出。", 409)
            self._reviewed_draft(task)
            stage = task["stages"].get("export", {})
            callback = self.callbacks.get("reconcile_export")
            if stage.get("status") != "needs_recheck" or callback is None:
                raise PortalDataError("flow_export_recheck_required", "当前无待核验导出。", 409)
            result = callback(deepcopy(task))
            fresh = True
            try:
                self._fresh(task)
            except PortalDataError as error:
                if error.code != "flow_inputs_stale":
                    raise
                fresh = False
            if (
                isinstance(result, dict)
                and result.get("status") == "not_complete"
                and result.get("id") == stage.get("attempt_id")
            ):
                if task.get("prism"):
                    raise PortalDataError(
                        "resume_export_needs_recheck",
                        "Prism 编译可能仍在运行，缺少完成回执不能重试，请保留原尝试。",
                        409,
                    )
                stage.update(status="failed", error_code="resume_export_not_complete")
                task["status"] = "export_failed"
            else:
                if not isinstance(result, dict):
                    raise PortalDataError("resume_export_needs_recheck", "导出记录不能核验。", 409)
                try:
                    self._export_result(task, result)
                except PortalDataError as error:
                    if error.code != "flow_export_configuration_changed":
                        raise
                    stage.update(status="failed", error_code=error.code)
                    task["status"] = "export_failed"
                else:
                    task["artifacts"].append(
                        {
                            "stage": "export",
                            "attempt_id": stage["attempt_id"],
                            "result": result,
                            "inputs": deepcopy(task["inputs"]),
                            "adopted": fresh,
                            "reconciled": True,
                        }
                    )
                    if fresh:
                        self._adopt_export(task, result)
            if not fresh:
                stage.update(status="failed", error_code="flow_inputs_stale")
                task["status"] = "stale"
            task["export_recheck"] = {
                "attempt_id": stage["attempt_id"],
                "draft_id": task["draft_id"],
                "draft_sha256": task["draft_sha256"],
                "input_epoch": task.get("input_epoch", 0),
                "status": stage["status"],
            }
            self._batch_after(state, task)
            self._save_material_result(state, task)
            return deepcopy(task)

    def refresh_match(self, task_id, task_revision, request_id, *, resume_request_id=None):
        from .application_match_refresh import refresh_match

        return refresh_match(
            self, task_id, task_revision, request_id, resume_request_id=resume_request_id
        )

    def reconcile_failed_match_refresh(self, task_id, task_revision, request_id):
        from .application_match_refresh import reconcile_failed_match_refresh

        return reconcile_failed_match_refresh(self, task_id, task_revision, request_id)

    def attach_match_recheck(self, task_id, task_revision, analysis_id, library_revision):
        from .application_match_recheck import attach_match_recheck

        return attach_match_recheck(self, task_id, task_revision, analysis_id, library_revision)

    def clarify_condition(self, task_id, task_revision, requirement_index, eligible, source):
        with self.applications.write_lock():
            state, task = self._checked(task_id, task_revision)
            self._batch_guard_change(state, task)
            if task["status"] == "cancelled":
                raise PortalDataError("flow_cancelled", "任务已取消，请建立新任务。", 409)
            application = self._fresh(task, stage="analysis")
            if task["worker_ref"]:
                raise PortalDataError(
                    "flow_materials_in_use", "已有填写任务，请先核验原任务及其资格条件。", 409
                )
            condition = next(
                (
                    row
                    for row in task_eligibility(task)["conditions"]
                    if row["requirement_index"] == requirement_index
                    and row["judgment"]
                    in (
                        {"unknown", "partial", "supported"}
                        if self.preparation_only
                        else {"unknown", "partial"}
                    )
                ),
                None,
            )
            if (
                type(requirement_index) is not int
                or condition is None
                or type(eligible) is not bool
                or not isinstance(source, str)
                or not 1 <= len(source.strip()) <= 1000
            ):
                raise PortalDataError(
                    "flow_condition_invalid", "请针对当前未知硬条件确认实际情况和依据。", 409
                )
            from .application_information import condition_information_binding

            qualification_basis = (
                condition_information_binding(condition, application, self.information_provider())
                if self.information_provider
                else None
            )
            task.setdefault("hard_condition_resolutions", []).append(
                {
                    "analysis_id": task["analysis_id"],
                    "requirement_index": requirement_index,
                    "eligible": eligible,
                    "confirmed": True,
                    "verified_by": "user",
                    "source": source.strip(),
                    **({"qualification_basis": qualification_basis} if qualification_basis else {}),
                    **(
                        {"analysis_input_revision": digest(analysis_input_binding(task["inputs"]))}
                        if "information_library_root" in task["inputs"]
                        else {}
                    ),
                    "input_revision": digest(
                        {
                            k: v
                            for k, v in task["inputs"].items()
                            if k != "resume_configuration_revision"
                        }
                    ),
                    "at": time.time(),
                }
            )
            if self.preparation_only:
                task["input_epoch"] = task.get("input_epoch", 0) + 1
                task.update(
                    resume_id=None,
                    resume_sha256=None,
                    materials_confirmed=False,
                    draft_id=None,
                    draft_sha256=None,
                    draft_review=None,
                )
                task.pop("experience_handoff", None)
                task["stages"]["resume"] = {"status": "pending"}
                if "export" in task["stages"]:
                    task["stages"]["export"] = {"status": "pending"}
                task["status"] = "analysis_ready"
            self._batch_after(state, task)
            self._save(state)
            return deepcopy(task)

    def configure_worker(self, worker, *, pdf_reader, target_provider):
        """Compose trusted Worker dependencies; Flow owns task and material delivery."""

        def legacy_reference(task, execution):
            reference, view = execution["reference"], execution["view"]
            return self._worker_reference(
                task,
                {
                    "batch_id": reference["batch_id"],
                    "job_id": reference["application_id"],
                    **{key: view[key] for key in ("status", "reason", "handed_off", "page_open")},
                },
            )

        def execution_reference(task):
            previous = task.get("worker_ref")
            if previous is not None and (
                not isinstance(previous, dict)
                or previous.get("job_id") != task["application_id"]
                or not isinstance(previous.get("batch_id"), str)
                or not previous["batch_id"]
            ):
                raise PortalDataError("flow_worker_mismatch", "执行记录与岗位任务不符。", 409)
            try:
                return worker.execution_reference(
                    task["application_id"],
                    task["id"],
                    expected_batch_id=previous["batch_id"] if previous else None,
                )
            except PortalDataError as error:
                if error.code in {"worker_execution_changed", "job_not_found"}:
                    raise PortalDataError(
                        "flow_worker_mismatch", "执行记录与岗位任务不符。", 409
                    ) from error
                raise

        def prepare(task, country):
            application = self.applications.get_application(task["application_id"])
            target = target_provider(application)
            binding = {
                "schemaVersion": 1,
                "task_id": task["id"],
                "job_binding": task["job_binding"],
                "inputs": deepcopy(task["inputs"]),
                "analysis_id": task["analysis_id"],
                "resume_id": task["resume_id"],
                "resume_sha256": task["resume_sha256"],
                "job_url": target["job_url"],
                "country": country,
                "send_confirmed": True,
                "hard_condition_resolutions": deepcopy(task.get("hard_condition_resolutions", [])),
            }
            return legacy_reference(
                task,
                worker.prepare_execution(
                    application["id"], application["revision"], binding, pdf_reader=pdf_reader
                ),
            )

        def control(task, operation, payload):
            if payload.get("application_id", task["application_id"]) != task["application_id"]:
                raise PortalDataError("flow_worker_mismatch", "填写操作不能更换岗位。", 409)
            payload = {
                key: deepcopy(value) for key, value in payload.items() if key != "application_id"
            }
            execution = execution_reference(task)
            command = (
                worker.select_execution
                if operation in {"skip-current", "select-current"}
                else worker.control_execution
            )
            return legacy_reference(task, command(execution["reference"], operation, payload))

        self.callbacks.update(
            prepare_worker=prepare,
            control_worker=control,
            worker_reference=lambda task: legacy_reference(task, execution_reference(task)),
            bound_worker_state=worker.store.load,
            bound_material_preparation=lambda reference: worker.check_material_preparation(
                reference["application_id"],
                reference["task_id"],
                expected_batch_id=reference["batch_id"],
            ),
        )

    def _worker_reference(self, task, worker):
        if (
            not isinstance(worker, dict)
            or any(
                not isinstance(worker.get(key), str) or not worker[key]
                for key in ("batch_id", "job_id", "status")
            )
            or worker["job_id"] != task["application_id"]
            or task.get("worker_ref")
            and (
                not isinstance(task["worker_ref"], dict)
                or task["worker_ref"].get("batch_id") != worker["batch_id"]
                or task["worker_ref"].get("job_id") != worker["job_id"]
            )
            or worker["status"]
            not in {
                "queued",
                "filling",
                "needs_input",
                "needs_recheck",
                "ready_for_review",
                "cancelled",
            }
        ):
            raise PortalDataError("flow_worker_mismatch", "执行记录与岗位任务不符。", 409)
        return deepcopy(worker)

    def _worker_view(self, task, reference=None):
        """Project the bound worker without changing material state or its revision."""
        view = deepcopy(task)
        previous = task.get("worker_ref")
        if not previous:
            return view
        try:
            if reference is None:
                callback = self.callbacks.get("worker_reference")
                if callback is None:
                    raise PortalDataError("flow_worker_unavailable", "填写状态暂不能核验。", 409)
                reference = callback(deepcopy(task))
            reference = self._worker_reference(task, reference)
            if any(previous[key] != reference[key] for key in ("batch_id", "job_id")):
                raise PortalDataError("flow_worker_mismatch", "执行记录与岗位任务不符。", 409)
        except (
            PortalDataError,
            OSError,
            ValueError,
            TypeError,
            KeyError,
            helper.StoreError,
        ) as error:
            reference = {
                key: previous[key]
                for key in ("batch_id", "job_id")
                if isinstance(previous, dict) and key in previous
            }
            reference.update(
                status="needs_recheck", reason=getattr(error, "code", "flow_worker_unavailable")
            )
        view["worker_ref"] = deepcopy(reference)
        material_wait = (
            _material_pending(task)
            or not task.get("materials_confirmed")
            or not task.get("resume_id")
        )
        if task["status"] in {
            "materials_ready",
            "queued",
            "filling",
            "needs_input",
            "needs_recheck",
            "ready_for_review",
        }:
            view["status"] = "needs_recheck" if material_wait else reference["status"]
        return view

    def prepare_worker(
        self, task_id, task_revision, country, send_confirmed, *, automation_authorization=None
    ):
        """Bind the current PDF and prepare it; starting remains an explicit action."""
        preflight = self.callbacks.get("write_preflight")
        with (
            preflight(
                "prepare", task_id, task_revision, country=country, send_confirmed=send_confirmed
            )
            if preflight
            else nullcontext()
        ):
            return self._prepare_worker(
                task_id,
                task_revision,
                country,
                send_confirmed,
                automation_authorization=automation_authorization,
            )

    def _prepare_worker(
        self, task_id, task_revision, country, send_confirmed, *, automation_authorization=None
    ):
        if self.preparation_only:
            raise PortalDataError("flow_preparation_only", "此入口只准备材料。", 409)
        with self.applications.write_lock():
            state, task = self._checked(task_id, task_revision)
            self._group_guard_change(task)
            self._check_other_match_pending(task)
            if automation_authorization is not None:
                checker = self.callbacks.get("verify_automation_authorization")
                if (
                    not checker
                    or not checker(automation_authorization, deepcopy(task))
                    or automation_authorization.get("country") != country
                ):
                    raise PortalDataError(
                        "flow_automation_authorization_invalid", "自动流程授权与本岗材料不符。", 409
                    )
            validator = self.callbacks.get("validate_write_preflight")
            admitted = validator("prepare") if validator else False
            application = (
                self.applications.get_application(task["application_id"])
                if admitted
                else self._fresh(task)
            )
            automatic_binding = task["status"] == "resume_ready" and not task["worker_ref"]
            if not automatic_binding and (
                not task["materials_confirmed"]
                or task["status"] != "materials_ready"
                or task["worker_ref"]
            ):
                raise PortalDataError(
                    "flow_materials_required", "请先确认当前材料并核验已有执行。", 409
                )
            if country not in COUNTRIES or send_confirmed is not True:
                raise PortalDataError(
                    "flow_send_confirmation_required", "请确认申请国家和该岗位的材料发送。", 409
                )
            if task_eligibility(task)["status"] not in {
                "supported",
                "not_specified",
                "needs_input",
            }:
                raise PortalDataError(
                    "flow_eligibility_required", "资格存在冲突或评估尚未取得，不能启动填写。", 409
                )
            if not application.get("url"):
                raise PortalDataError("flow_job_url_required", "请先补齐该岗位的申请链接。", 409)
            callback = self.callbacks.get("prepare_worker")
            if callback is None:
                raise PortalDataError("flow_worker_unavailable", "自动填写暂不可用。", 409)
            verifier = self.callbacks.get("verify_materials")
            if automatic_binding:
                self._bind_current_materials(task)
            elif verifier and not admitted:
                verifier(task)
            task["send_approval"] = {
                "country": country,
                "job_url": application["url"],
                "resume_id": task["resume_id"],
                "resume_sha256": task["resume_sha256"],
                "analysis_id": task["analysis_id"],
                "inputs": deepcopy(task["inputs"]),
                "confirmed": True,
                "verified_by": "user",
                "at": time.time(),
            }
            if automation_authorization is not None:
                task["send_approval"].update(
                    actor="system",
                    verified_by="workflow_policy",
                    human_reviewed=False,
                    authorization=deepcopy(automation_authorization),
                )
            task["worker_preparation"] = {"status": "pending"}
            self._save(state)
            worker = callback(deepcopy(task), country)
            reference = self._worker_reference(task, worker)
            task["worker_ref"] = {key: reference[key] for key in ("batch_id", "job_id")}
            task["worker_preparation"] = {"status": "complete"}
            self._save(state)
            return self._worker_view(task, reference)

    def bind_worker(self, task_id, task_revision, worker):
        """Internal adapter call after the existing worker prepares exact materials."""
        if self.preparation_only:
            raise PortalDataError("flow_preparation_only", "此入口只准备材料。", 409)
        with self.applications.write_lock():
            state, task = self._checked(task_id, task_revision)
            self._fresh(task)
            if (
                not task["materials_confirmed"]
                or task["status"] != "materials_ready"
                or task["worker_ref"]
            ):
                raise PortalDataError(
                    "flow_materials_required", "请先确认当前材料并核验已有执行。", 409
                )
            verifier = self.callbacks.get("verify_materials")
            if verifier:
                verifier(task)
            reference = self._worker_reference(task, worker)
            task["worker_ref"] = {key: reference[key] for key in ("batch_id", "job_id")}
            self._save(state)
            return self._worker_view(task, reference)

    def worker_action(self, task_id, task_revision, operation, payload):
        preflight = self.callbacks.get("write_preflight")
        with (
            preflight(operation, task_id, task_revision)
            if preflight
            and operation
            in {
                "resume",
                "recheck",
                "answer",
                "heartbeat",
                "provide-material",
                "retry-cover-letter-file",
                "recheck-cover-letter-file",
                "resolve-form-differences",
            }
            else nullcontext()
        ):
            return self._worker_action(task_id, task_revision, operation, payload)

    def _worker_action(self, task_id, task_revision, operation, payload):
        if self.preparation_only:
            raise PortalDataError("flow_preparation_only", "此入口只准备材料。", 409)
        allowed = {
            "resume",
            "pause",
            "heartbeat",
            "answer",
            "provide-material",
            "retry-cover-letter-file",
            "recheck-cover-letter-file",
            "correct-email",
            "resolve-form-differences",
            "review",
            "recheck",
            "release",
            "retry-sync",
            "resolve-action",
            "cancel-job",
            "settle-cancelled",
            "observe-page",
            "inspect-handoff",
            "verify-handoff",
            "skip-current",
            "select-current",
            "continue-current",
            "observe-result",
        }
        with self.applications.write_lock():
            observer_review = (
                operation == "review"
                and not self._owner
                and not self._closed.is_set()
                and not self._runtime_error
            )
            state, task = (
                self._read_checked(task_id, task_revision)
                if observer_review
                or operation in {"observe-page", "inspect-handoff", "verify-handoff"}
                else self._checked(task_id, task_revision)
            )
            # Existing-page review uses the worker's full single-binding check.
            # A duplicate input scan here can starve its heartbeat under this lock.
            callback = self.callbacks.get("control_worker")
            if not task["worker_ref"] or callback is None:
                raise PortalDataError("flow_worker_unavailable", "请先准备当前填写任务。", 409)
            if operation not in allowed or not isinstance(payload, dict):
                raise PortalDataError("invalid_flow_request", "填写操作无效。")
            if operation in {"resume", "continue-current"}:
                self._group_guard_change(task)
                self._check_other_match_pending(task)
            if operation == "resume":
                if task["status"] == "cancelled":
                    raise PortalDataError("flow_cancelled", "任务已取消，请核验原页面。", 409)
                validator = self.callbacks.get("validate_write_preflight")
                if not (validator("resume") if validator else False):
                    self._fresh(task)
                if task_eligibility(task)["status"] not in {
                    "supported",
                    "not_specified",
                    "needs_input",
                }:
                    raise PortalDataError(
                        "flow_eligibility_required",
                        "资格存在冲突或评估尚未取得，不能继续填写。",
                        409,
                    )
            if operation in {"resume", "review", "recheck"}:
                verifier = self.callbacks.get("verify_materials")
                if verifier:
                    verifier(task)
            reference = self._worker_reference(task, callback(deepcopy(task), operation, payload))
            # Worker commands own their own persistence. Observations and page
            # actions do not revise Flow materials or copy page execution state.
            return self._worker_view(task, reference)

    def observe_worker(self, task_id, task_revision, worker):
        """Validate a current observation and return it without changing Flow."""
        with self.applications.write_lock():
            _state, task = self._read_checked(task_id, task_revision)
            observed = self._worker_reference(task, worker)
            previous = task["worker_ref"]
            if previous is None or any(
                previous[key] != observed[key] for key in ("batch_id", "job_id")
            ):
                raise PortalDataError("flow_worker_mismatch", "执行记录与岗位任务不符。", 409)
            return self._worker_view(task, observed)

    def create(self, application_id, application_revision, *, inputs=None, force_new=False):
        self._writable()
        with self.applications.write_lock():
            self._writable()
            application = self.applications.get_application(application_id)
            if application["revision"] != application_revision:
                raise PortalDataError("conflict", "投递记录已变化，请重新打开。", 409)
            state = self._load()
            bound = next(
                (
                    row
                    for row in reversed(state["tasks"])
                    if row["application_id"] == application_id
                    and (row.get("codex_handoff_ref") or row.get("codex_handoff_attempt"))
                ),
                None,
            )
            if bound:
                # Uploaded form state survives input changes and explicit new-task requests.
                # The normal snapshot revalidates the reference and pauses stale inputs.
                return deepcopy(bound)
            resolved = self._identity(application, inputs)
            for prior in state["tasks"]:
                if prior["application_id"] == application_id:
                    self._group_guard_change(prior)
            if state.get("preparation_batch") and any(
                task["status"] == "needs_recheck"
                or task["stages"].get("export", {}).get("status") == "needs_recheck"
                for task in state["tasks"]
            ):
                raise PortalDataError(
                    "flow_batch_recheck_required", "先核验原任务，不能用新任务替换未知结果。", 409
                )
            if self.preparation_only:
                latest = latest_preparation_task(state["tasks"], application_id)
                if latest and latest["status"] == "cancelled":
                    raise PortalDataError(
                        "flow_inputs_stale", "已取消任务仍有待核验操作，请先核对原结果。", 409
                    )
                candidates = [latest] if latest else []
            else:
                candidates = state["tasks"]
            for task in candidates:
                if task["application_id"] != application_id:
                    continue
                if task.get("origin") == "existing_latex":
                    break
                if (
                    not force_new
                    and task["job_binding"] == job_input_revision(application)
                    and task["inputs"] == retained_configuration_inputs(task, resolved)
                    and task["status"] != "cancelled"
                ):
                    return deepcopy(task)
                if self.preparation_only:
                    break
            task = self._new_task(application, resolved)
            state["tasks"].append(task)
            self._save(state)
            return deepcopy(task)

    @staticmethod
    def _new_task(application, inputs):
        return {
            "id": uuid4().hex,
            "application_id": application["id"],
            "application_revision": application["revision"],
            "job_description": application.get("job_description", ""),
            "material_contract": "content-writing/v1",
            "job_binding": job_input_revision(application),
            "inputs": inputs,
            "input_epoch": 0,
            "status": "draft",
            "stages": {"analysis": {"status": "pending"}, "resume": {"status": "pending"}},
            "analysis_id": None,
            "resume_id": None,
            "resume_sha256": None,
            "materials_confirmed": False,
            "worker_ref": None,
            "artifacts": [],
            "created_at": time.time(),
        }

    def _known_attempt_failure(self, task):
        stage, analysis = task["stages"]["analysis"], getattr(self, "analysis", None)
        if stage.get("status") != "failed" or analysis is None:
            return False
        try:
            # A recoverable attempt holds a complete saved answer, never an unknown one.
            return analysis.reconcile(stage["attempt_id"])["status"] in {"failed", "recoverable"}
        except (PortalDataError, KeyError, TypeError):
            return False

    def analysis_outcome(self, task_id):
        """Deliver saved analysis certainty; never project, refresh or retry work."""
        with self.applications.write_lock():
            task = self._task(self._load(), task_id)
            return _analysis_outcome(task, known_attempt_failure=self._known_attempt_failure(task))

    def progress(self, task_id):
        """Read preparation progress without dispatching or inspecting execution."""
        with self.applications.write_lock():
            task = self._task(self._load(), task_id)
            return _preparation_progress(
                task,
                _analysis_outcome(task, known_attempt_failure=self._known_attempt_failure(task)),
            )

    def prepare(self, task_id, task_revision, *, request_id=None, analysis_only=False):
        """Advance one necessary preparation stage; Pipeline owns the next-job decision."""
        with self.applications.write_lock():
            progress = self.progress(task_id)
            task = progress["task"]
            if _preparation_request_replayed(task, request_id):
                return progress
            request = {"_continuation_request_id": request_id} if request_id is not None else {}
            if task["revision"] != task_revision:
                raise PortalDataError("conflict", "任务已变化，请重新读取。", 409)
            if progress["status"] == "cancelled":
                raise PortalDataError("flow_cancelled", "任务已取消，请建立新任务。", 409)
            if progress["phase"] == "analysis":
                if progress["analysis"]["status"] == "pending":
                    self.start(task_id, task_revision, "analysis", **request)
                return self.progress(task_id)
            if analysis_only or task.get("worker_ref"):
                return progress
            resume = progress["resume"]
            if (
                resume.get("status") == "failed"
                and resume.get("error_code") == "resume_author_paused"
            ):
                self.start(task_id, task_revision, "resume", retry=True, **request)
                return self.progress(task_id)
            if progress["status"] in {"waiting", "needs_recheck"}:
                return progress
            if (
                task["status"] in {"draft_ready", "resume_ready", "materials_ready"}
                and not task.get("cover_letter")
                and "cover_letter" in self.callbacks
            ):
                task = self.start_cover_letter(task_id, task_revision, **request)
                task_revision = task["revision"]
            try:
                if task["status"] == "analysis_ready":
                    task = self.prepare_automatic_materials(task_id, task_revision)
                    self.start(task_id, task["revision"], "resume", **request)
                elif task["status"] == "draft_ready":
                    self.start(task_id, task_revision, "export", **request)
            except PortalDataError as error:
                reasons = {
                    "flow_latex_base_required": "material_base_required",
                    "resume_group_verification_required": "material_facts_required",
                }
                if error.code not in reasons:
                    raise
                return self.progress(task_id) | {
                    "status": "waiting",
                    "wait_reason": reasons[error.code],
                    "message": error.message,
                    "can_prepare_execution": False,
                }
            return self.progress(task_id)

    def continue_preparation(self, task_id, task_revision, *, request_id, expected_attempt_id=None):
        """Continue only an explicitly selected known failure; unknown work is retained."""
        if not isinstance(request_id, str) or not 1 <= len(request_id) <= 100:
            raise PortalDataError("invalid_request", "继续请求缺少有效标识。", 400)
        with self.applications.write_lock():
            progress = self.progress(task_id)
            task = progress["task"]
            if _preparation_request_replayed(task, request_id, expected_attempt_id):
                # A lost response cannot authorize a retry of a later failed attempt.
                return progress
            if progress["task_revision"] != task_revision:
                raise PortalDataError("conflict", "任务已变化，请重新读取。", 409)
            continuation = progress["continuation"]
            if continuation is not None:
                if (
                    expected_attempt_id is not None
                    and continuation["attempt_id"] != expected_attempt_id
                ):
                    return progress
                self.start(
                    task_id,
                    task_revision,
                    "resume",
                    retry=True,
                    _continuation_request_id=request_id,
                )
                return self.progress(task_id)
            if expected_attempt_id is not None:
                return progress
            return self.prepare(task_id, task_revision, request_id=request_id)

    def reconcile_preparation(self, task_id, task_revision, *, request_id):
        """Read an original material receipt; this never starts a new build or author."""
        progress = self.progress(task_id)
        if progress["task_revision"] != task_revision:
            raise PortalDataError("conflict", "任务已变化，请重新读取。", 409)
        if progress["status"] == "cancelled":
            return progress
        if progress["resume"].get("status") == "needs_recheck" and progress["task"].get(
            "experience_handoff"
        ):
            self.recheck_resume_author(task_id, task_revision)
        elif progress["export"].get("status") == "needs_recheck":
            self.recheck_export(task_id, task_revision)
        elif progress["cover_letter"]["status"] == "needs_recheck":
            self.recheck_cover_letter(task_id, task_revision)
        elif progress["material_consistency"]["status"] == "needs_recheck":
            self.recheck_material_consistency(task_id, task_revision)
        return self.progress(task_id)

    def task_snapshot(self, task_id):
        """Project one task with current Worker/handoff checks and no history projection."""
        from .application_existing_handoff import project

        with self.applications.write_lock():
            task = self._task(self._load(), task_id)
            return project(self, self._worker_view(task))

    def snapshot(self, task_id=None):
        with self.applications.write_lock():
            state = deepcopy(self._load())
            from .application_existing_handoff import project

            state["tasks"] = [project(self, self._worker_view(task)) for task in state["tasks"]]
            active = self._task(state, task_id) if task_id else None
            if not task_id:
                if self.preparation_only:
                    active = latest_preparation_task(state["tasks"])
                active = active or next(iter(reversed(state["tasks"])), None)
            if not task_id and self.material_batch:
                batch = state.get("preparation_batch") or {}
                if batch.get("active_task_id"):
                    active = self._task(state, batch["active_task_id"])
            snapshot = state | {
                "enabled": True,
                "active_task": active,
                "local_materials": bool(active and local_materials(active)),
                "eligibility": task_eligibility(active)
                if active and not self.preparation_only
                else None,
                "runtime_error": self._runtime_error,
            }
            if active and active.get("experience_handoff"):
                reader = self.callbacks.get("experience_generation")
                try:
                    snapshot["experience_generation"] = (
                        reader(deepcopy(active))
                        if reader
                        else deepcopy(active["experience_handoff"])
                    )
                except (PortalDataError, OSError, ValueError) as error:
                    snapshot["experience_generation"] = {
                        "id": active["experience_handoff"]["id"],
                        "status": "unavailable",
                        "error_code": getattr(error, "code", "flow_generation_unavailable"),
                    }
            if self.preparation_only:
                from .application_draft import resume_language_policy

                snapshot["resume_language"] = (
                    resume_language_policy(active["job_description"]) if active else None
                )
                snapshot["preparation_batch"] = self.material_batch.snapshot(state)
                snapshot.update(self._explanations(state))
                explanation = next(
                    (
                        row
                        for row in snapshot["explanations"]
                        if active and row["task_id"] == active["id"]
                    ),
                    None,
                )
                if explanation is None and active:
                    explanation = self._explanation(
                        self.applications.get_application(active["application_id"]),
                        active,
                        self.information_provider()
                        if self.fixed_writing_inputs(active) is None and self.information_provider
                        else None,
                    )
                snapshot["active_explanation"] = explanation
                if explanation:
                    snapshot["eligibility"] = explanation["qualification"]
            return snapshot

    def _explanations(self, state):
        from .application_preparation import PREPARATION_POLICY_VERSION

        library = None
        library_read = False
        rows = []
        for application in self.applications.list_applications():
            if not application.get("job_description", "").strip():
                continue
            task = next(
                (t for t in reversed(state["tasks"]) if t["application_id"] == application["id"]),
                None,
            )
            if self.preparation_only:
                task = latest_preparation_task(state["tasks"], application["id"]) or task
            if (task is None or self.fixed_writing_inputs(task) is None) and not library_read:
                library = self.information_provider() if self.information_provider else None
                library_read = True
            rows.append(self._explanation(application, task, library))
        rows.sort(
            key=lambda row: (
                -(row["score"]["lower"])
                if row["fresh"] and row["score"] and row["score"]["lower"] is not None
                else float("inf")
            )
        )
        manual = state.get("manual_order", [])
        if manual:
            positions = {identifier: index for index, identifier in enumerate(manual)}
            rows.sort(key=lambda row: positions.get(row["application_id"], len(positions)))
        return {
            "policy_version": PREPARATION_POLICY_VERSION,
            "explanations": rows,
            "order_mode": "manual" if manual else "match",
            "order_revision": digest([(r["application_id"], r["revision"]) for r in rows]),
        }

    def _explanation(self, application, task, library):
        from .application_explanations import job_explanation
        from .application_preparation import PREPARATION_POLICY_VERSION

        fixed = self.fixed_writing_inputs(task) if task else None
        if fixed is not None:
            application = {**application, **fixed["analysis"].get("job_brief", {}).get("job", {})}
        unavailable = False
        try:
            current = (
                task["inputs"]
                if fixed is not None
                else (
                    self._identity(application, None if self.input_provider else task["inputs"])
                    if task
                    else {}
                )
            )
        except (PortalDataError, OSError, ValueError, helper.StoreError):
            current, unavailable = {"unavailable": "current_inputs_unverifiable"}, True
        result = job_explanation(
            application,
            task,
            current_inputs=current,
            library=None if fixed is not None else library,
            source_provider=None if fixed is not None else self.recheck_source_provider,
            policy_version=PREPARATION_POLICY_VERSION,
            fixed_delivery=fixed is not None,
        )
        if unavailable:
            result["limitations"].insert(0, "此岗当前资料暂不能核验，请保留进度后重新读取。")
            result["revision"] = digest({k: v for k, v in result.items() if k != "revision"})
        return result

    def reorder(self, application_id, direction, order_revision):
        if not self.preparation_only or direction not in {"up", "down"}:
            raise PortalDataError("invalid_flow_request", "请明确选择上移或下移岗位。")
        with self.applications.write_lock():
            self._writable()
            state = self._load()
            current = self._explanations(state)
            if current["order_revision"] != order_revision:
                raise PortalDataError("conflict", "岗位排序或分析已变化，请读取最新状态。", 409)
            identifiers = [r["application_id"] for r in current["explanations"]]
            if application_id not in identifiers:
                raise PortalDataError("flow_not_found", "找不到可调整的岗位。", 404)
            position = identifiers.index(application_id)
            target = position + (-1 if direction == "up" else 1)
            if 0 <= target < len(identifiers):
                previous = list(identifiers)
                identifiers[position], identifiers[target] = (
                    identifiers[target],
                    identifiers[position],
                )
                state["manual_order"] = identifiers
                state.setdefault("order_events", []).append(
                    {
                        "application_id": application_id,
                        "direction": direction,
                        "previous": previous,
                        "current": identifiers,
                        "reason": "user_manual_order",
                        "at": time.time(),
                    }
                )
                self._save(state)
            return self.snapshot()

    def attach_experience_materials(self, task_id, task_revision, generation_id, export_id):
        from .application_existing_materials import attach

        return attach(self, task_id, task_revision, generation_id, export_id)

    def attach_existing_handoff(
        self, task_id, task_revision, handoff_root, handoff_task_id, handoff_task_revision
    ):
        from .application_existing_handoff import attach

        return attach(
            self, task_id, task_revision, handoff_root, handoff_task_id, handoff_task_revision
        )

    def restart_existing_handoff(self, task_id, task_revision):
        from .application_existing_handoff import restart

        return restart(self, task_id, task_revision)

    def resume_experience_generation(self, task_id, task_revision, generation_id):
        """Consume an adopted Codex generation through the existing resume stage."""
        with self.applications.write_lock():
            state, task = self._checked(task_id, task_revision)
            handoff = task.get("experience_handoff") or {}
            resume_stage = task["stages"]["resume"]
            failed_author = (
                task["status"] == "failed"
                and resume_stage.get("status") == "failed"
                and resume_stage.get("error_code")
                in {
                    "resume_author_failed",
                    "resume_author_material_required",
                    "resume_author_paused",
                }
            )
            if handoff.get("id") != generation_id or not (
                task["status"] == "needs_input"
                and resume_stage["status"] == "pending"
                or failed_author
            ):
                raise PortalDataError(
                    "flow_generation_mismatch", "经历生成与当前任务不符，请读取最新进度。", 409
                )
            reader = self.callbacks.get("experience_generation")
            current = reader(deepcopy(task)) if reader else handoff
            if current.get("id") != generation_id or current.get("status") != "adopted":
                raise PortalDataError(
                    "flow_generation_not_adopted", "Codex 尚未完成组装、终审与采用。", 409
                )
            if failed_author:
                resume_stage.update(status="pending")
                resume_stage.pop("error_code", None)
                task["status"] = "needs_input"
                self._save(state)
                task_revision = task["revision"]
            self.start(task_id, task_revision, "resume")
            state = self._load()
            task = self._task(state, task_id)
            # Only a current, internally reviewed Codex generation enters this path.
            task["automatic_materials"] = True
            task["stages"].setdefault("export", {"status": "pending"})
            self._save(state)
            return deepcopy(task)

    def _letter_binding(self, task):
        fixed = self.fixed_writing_inputs(task)
        if fixed is None:
            raise PortalDataError(
                "letter_fixed_inputs_required", "求职信需要本岗已采用的固定资料。", 409
            )
        analysis = fixed["analysis"]
        analysis_id = task["analysis_id"]
        previous = task.get("cover_letter") or {}
        if (
            previous.get("status") == "ready"
            and previous.get("analysis_id") != analysis_id
            and previous.get("job_binding") == task["job_binding"]
        ):
            prior = next(
                (
                    row["result"]
                    for row in task.get("artifacts", [])
                    if row.get("stage") == "analysis"
                    and row.get("adopted")
                    and row.get("result", {}).get("id") == previous.get("analysis_id")
                ),
                None,
            )
            if prior and all(
                prior.get(key) == analysis.get(key)
                for key in ("jd_revision", "job_brief", "material_packet", "inference_result")
            ):
                analysis_id = previous["analysis_id"]
        return digest(
            {
                "analysis_id": analysis_id,
                "job_binding": analysis.get("jd_revision"),
                **{
                    key: analysis[key]
                    for key in ("job_brief", "material_packet", "inference_result")
                },
            }
        )

    def _check_other_match_pending(self, task):
        from .application_match_refresh import require_no_other_match_refresh

        require_no_other_match_refresh(self, task["id"])

    def _check_other_material_pending(self, state, task):
        self._check_other_match_pending(task)
        if any(
            row["id"] != task["id"]
            and (
                row.get("cover_letter", {}).get("status") in {"queued", "running", "needs_recheck"}
                or row.get("material_consistency", {}).get("status")
                in {"queued", "running", "needs_recheck"}
            )
            for row in state["tasks"]
        ):
            raise PortalDataError(
                "letter_other_job_pending", "原岗位求职信仍在运行或结果未知，请先核验。", 409
            )

    def _check_other_execution_pending(self, state, task):
        self._check_other_material_pending(state, task)
        if self._running_stage_task_id not in {None, task["id"]} or any(
            row["id"] != task["id"]
            and any(
                stage.get("status") in {"queued", "running", "needs_recheck", "unknown"}
                for stage in row["stages"].values()
            )
            for row in state["tasks"]
        ):
            raise PortalDataError(
                "flow_other_job_running", "原岗位阶段仍在执行或结果未知，其他岗位须等待。", 409
            )

    def _reserve_cover_letter(self, state, task, *, retry=False, _continuation_request_id=None):
        if (
            "cover_letter" not in self.callbacks
            or task.get("material_contract") != "content-writing/v1"
            or not (self.preparation_only or task.get("automatic_materials"))
            or task.get("origin") == "existing_latex"
        ):
            return None
        if self.fixed_writing_inputs(task) is None:
            return None
        previous = task.get("cover_letter") or {}
        binding = self._letter_binding(task)
        # Writing only drafts text; the user's explicit retry may run an unknown letter
        # call again (approved 2026-10-31). The unknown attempt stays in history.
        if previous.get("status") == "needs_recheck" and not retry:
            raise PortalDataError(
                "letter_generation_needs_recheck", "求职信调用结果未知，先核验原尝试。", 409
            )
        if previous.get("status") in {"queued", "running"}:
            return None
        if previous.get("fixed_inputs_revision") == binding and (
            previous.get("status") == "ready" or not retry
        ):
            return None
        self._check_other_material_pending(state, task)
        if previous:
            task.setdefault("cover_letter_history", []).append(deepcopy(previous))
        attempt = uuid4().hex
        task["cover_letter"] = {
            "status": "queued",
            "attempt_id": attempt,
            "analysis_id": task["analysis_id"],
            "job_binding": task["job_binding"],
            "fixed_inputs_revision": binding,
        }
        if retry and previous.get("status") in {"failed", "needs_recheck"}:
            task["cover_letter"]["retry_from_attempt_id"] = previous["attempt_id"]
        _record_preparation_attempt(
            task, "cover_letter", attempt, previous.get("attempt_id"), _continuation_request_id
        )
        return attempt

    def _launch_cover_letter(self, task_id, attempt):
        if attempt is None:
            return
        self._letter_threads = {
            key: thread for key, thread in self._letter_threads.items() if thread.is_alive()
        }
        thread = threading.Thread(
            target=self._run_cover_letter,
            args=(task_id, attempt),
            name="application-cover-letter",
            daemon=True,
        )
        self._letter_threads[attempt] = thread
        thread.start()

    def start_cover_letter(
        self, task_id, task_revision=None, *, retry=False, _continuation_request_id=None
    ):
        """Start only a missing letter; a completed resume is never regenerated."""
        with self.applications.write_lock():
            self._writable()
            state = self._load()
            task = self._task(state, task_id)
            if task_revision is not None and task["revision"] != task_revision:
                raise PortalDataError("conflict", "任务已变化，请重新读取。", 409)
            if task["status"] == "cancelled":
                raise PortalDataError("flow_cancelled", "任务已取消，请保留原材料。", 409)
            self._fresh(task, stage="resume")
            previous = task.get("cover_letter") or {}
            if (
                retry
                and previous.get("status") == "cancelled"
                and previous.get("job_binding") == task["job_binding"]
                and previous.get("fixed_inputs_revision") == self._letter_binding(task)
            ):
                retained = next(
                    (
                        row["result"]
                        for row in reversed(task["artifacts"])
                        if row.get("stage") == "cover_letter"
                        and row.get("attempt_id") == previous.get("attempt_id")
                        and row.get("adopted") is False
                        and row.get("result", {}).get("status") == "ready"
                    ),
                    None,
                )
                if retained is not None:
                    self._check_other_material_pending(state, task)
                    self._check_letter_result(task, retained)
                    previous.update(status="ready", result=deepcopy(retained))
                    previous.pop("cancel_requested", None)
                    previous.pop("error_code", None)
                    task["artifacts"].append(
                        {
                            "stage": "cover_letter",
                            "attempt_id": previous["attempt_id"],
                            "result": deepcopy(retained),
                            "inputs": deepcopy(task["inputs"]),
                            "adopted": True,
                            "reused_after_cancel": True,
                        }
                    )
                    consistency = task.get("material_consistency") or {}
                    if consistency.get("status") == "cancelled" and consistency.get(
                        "cancel_requested"
                    ):
                        consistency.pop("pair_revision", None)
                    self._reserve_material_consistency(task)
                    self._save(state)
                    return deepcopy(task)
            attempt = self._reserve_cover_letter(
                state, task, retry=retry, _continuation_request_id=_continuation_request_id
            )
            self._save(state)
            self._launch_cover_letter(task_id, attempt)
            return deepcopy(task)

    def adopt_cover_letter_successor(
        self,
        task_id,
        *,
        expected_attempt_id,
        expected_content_revision,
        content,
        source_binding,
        request_id,
    ):
        """Publish one scoped human body and reserve its new consistency pair."""
        import hashlib

        from .application_cover_letter import validate_letter

        with self.applications.write_lock():
            self._writable()
            state = self._load()
            task = self._task(state, task_id)
            branch = task.get("cover_letter") or {}
            current = branch.get("result") or {}
            try:
                value = validate_letter(content)
            except (ValueError, TypeError) as error:
                raise PortalDataError(
                    "material_changed", "人工求职信正文或版本不能核验。", 409
                ) from error
            if (
                not isinstance(request_id, str)
                or re.fullmatch(r"[a-f0-9]{32}", request_id) is None
                or task.get("status") == "cancelled"
                or not isinstance(source_binding, dict)
                or not isinstance(source_binding.get("application"), dict)
                or source_binding.get("manual_edit") is not True
                or value["application_id"] != task["application_id"]
                or source_binding.get("application", {}).get("id") != task["application_id"]
                or any(
                    row["origin"] != "human" or row["protected"] is not True
                    for row in value["paragraphs"]
                )
                or branch.get("status") != "ready"
                or branch.get("attempt_id") != expected_attempt_id
            ):
                raise PortalDataError("material_changed", "人工求职信与原申请尝试不符。", 409)
            if branch.get("human_edit_id") == request_id:
                if digest(current.get("content")) == digest(value) and digest(
                    current.get("source_binding")
                ) == digest(source_binding):
                    return deepcopy(current)
                raise PortalDataError(
                    "material_changed", "该编辑标识已有不同正文，新稿已保留。", 409
                )
            original_content = current.get("content") or {}
            original_binding = current.get("source_binding") or {}
            if (
                current.get("content_revision") != expected_content_revision
                or original_content.get("revision") != expected_content_revision
                or any(
                    value.get(key) != original_content.get(key)
                    for key in ("application_id", "job_revision", "inputs_revision", "language")
                )
                or digest({key: row for key, row in source_binding.items() if key != "manual_edit"})
                != digest(
                    {key: row for key, row in original_binding.items() if key != "manual_edit"}
                )
            ):
                raise PortalDataError(
                    "material_changed", "申请级求职信版本已变化，人工新稿已保留。", 409
                )
            branch.setdefault("content_history", []).append(deepcopy(current))
            body = "\n\n".join(row["text"] for row in value["paragraphs"])
            branch["result"] = {
                **current,
                "content": deepcopy(value),
                "content_revision": value["revision"],
                "text": body,
                "text_sha256": hashlib.sha256(body.encode()).hexdigest(),
                "paragraphs": deepcopy(value["paragraphs"]),
                "actor": "user",
                "source_binding": deepcopy(source_binding),
            }
            branch["result"].pop("grounding", None)
            branch["human_edit_id"] = request_id
            self._reserve_material_consistency(task)
            self._save(state)
            return deepcopy(branch["result"])

    def cancel_cover_letter(self, task_id):
        """Stop adoption, retaining an in-flight call until its outcome is known."""
        with self.applications.write_lock():
            self._writable()
            state = self._load()
            task = self._task(state, task_id)
            letter = task.get("cover_letter") or {}
            if task.get("material_consistency", {}).get("status") == "needs_recheck":
                raise PortalDataError(
                    "material_consistency_needs_recheck",
                    "原一致性调用结果未知，先核验原尝试。",
                    409,
                )
            if letter.get("status") == "needs_recheck":
                raise PortalDataError(
                    "letter_generation_needs_recheck", "求职信调用结果未知，先核验原尝试。", 409
                )
            if letter.get("status") in {"queued", "running"}:
                letter["cancel_requested"] = True
            self._cancel_material_consistency(task)
            self._save(state)
            return deepcopy(letter)

    def cover_letter_outcome(self, task_id):
        with self.applications.write_lock():
            task = self._task(self._load(), task_id)
            return deepcopy(task.get("cover_letter") or {"status": "not_started"})

    @staticmethod
    def _check_letter_result(request, result):
        import hashlib

        from .application_cover_letter import validate_letter

        if (
            not isinstance(result, dict)
            or result.get("kind") != "cover_letter"
            or result.get("status") != "ready"
            or result.get("attempt_id") != request["cover_letter"]["attempt_id"]
            or not isinstance(result.get("id"), str)
            or re.fullmatch(r"[a-f0-9]{64}", result.get("content_revision", "")) is None
            or result.get("content", {}).get("inputs_revision")
            != request["cover_letter"]["fixed_inputs_revision"]
            or result.get("content", {}).get("application_id") != request["application_id"]
            or result.get("content", {}).get("revision") != result.get("content_revision")
        ):
            raise PortalDataError("letter_result_invalid", "求职信结果与当前内容版本不符。", 409)
        content = validate_letter(result["content"])
        text = "\n\n".join(row["text"] for row in content["paragraphs"])
        if (
            result.get("text") != text
            or result.get("text_sha256") != hashlib.sha256(text.encode()).hexdigest()
        ):
            raise PortalDataError("letter_result_invalid", "求职信正文与内容版本不符。", 409)
        digest(result)

    def recheck_cover_letter(self, task_id, task_revision):
        """Adopt an exact persisted receipt without another author/reviewer call."""
        with self.applications.write_lock():
            state, task = self._checked(task_id, task_revision)
            letter = task.get("cover_letter") or {}
            if letter.get("status") == "ready":
                return deepcopy(task)
            if letter.get("status") != "needs_recheck" or any(
                thread.is_alive() for thread in self._letter_threads.values()
            ):
                raise PortalDataError(
                    "letter_recheck_unavailable", "求职信尚不能核验，保留原尝试。", 409
                )
            reader = self.callbacks.get("cover_letter_result")
            if reader is None:
                raise PortalDataError(
                    "letter_generation_needs_recheck", "求职信原回执暂不可读。", 409
                )
            result = reader(deepcopy(task))
            self._check_letter_result(task, result)
            if (
                self._letter_binding(task) != letter["fixed_inputs_revision"]
                or task["job_binding"] != letter["job_binding"]
            ):
                raise PortalDataError(
                    "letter_result_invalid", "求职信原回执的固定资料已变化。", 409
                )
            adopt = not letter.get("cancel_requested") and task["status"] != "cancelled"
            task["artifacts"].append(
                {
                    "stage": "cover_letter",
                    "attempt_id": letter["attempt_id"],
                    "result": deepcopy(result),
                    "inputs": deepcopy(task["inputs"]),
                    "adopted": adopt,
                    "reconciled": True,
                }
            )
            if adopt:
                letter.update(status="ready", result=deepcopy(result))
            else:
                letter["status"] = "cancelled"
            letter.pop("error_code", None)
            self._reserve_material_consistency(task)
            self._save(state)
            return deepcopy(task)

    def _run_cover_letter(self, task_id, attempt):
        try:
            with self.applications.write_lock():
                if self._closed.is_set():
                    return
                state = self._load()
                task = self._task(state, task_id)
                letter = task.get("cover_letter") or {}
                if letter.get("attempt_id") != attempt or letter.get("status") != "queued":
                    return
                if letter.get("cancel_requested") or task["status"] == "cancelled":
                    letter["status"] = "cancelled"
                    self._save(state)
                    return
                letter["status"] = "running"
                self._save(state)
                request = deepcopy(task)
            result, error_code, known_failure = None, None, False
            try:
                candidate = self.callbacks["cover_letter"](request)
                self._check_letter_result(request, candidate)
                result = candidate
            except Exception as error:
                error_code = getattr(error, "code", "letter_generation_needs_recheck")
                known_failure = error_code == "letter_generation_failed"
            with self.applications.write_lock():
                state = self._load()
                task = self._task(state, task_id)
                letter = task.get("cover_letter") or {}
                active = (
                    not self._closed.is_set()
                    and letter.get("attempt_id") == attempt
                    and letter.get("status") == "running"
                    and not letter.get("cancel_requested")
                    and task["status"] != "cancelled"
                    and task["job_binding"] == request["job_binding"]
                )
                if active:
                    try:
                        active = (
                            self._letter_binding(task)
                            == request["cover_letter"]["fixed_inputs_revision"]
                        )
                    except (PortalDataError, KeyError, ValueError):
                        active = False
                if result is not None:
                    task["artifacts"].append(
                        {
                            "stage": "cover_letter",
                            "attempt_id": attempt,
                            "result": result,
                            "inputs": request["inputs"],
                            "adopted": active and error_code is None,
                        }
                    )
                if letter.get("attempt_id") == attempt and letter.get("status") == "running":
                    if error_code:
                        letter.update(
                            status="failed" if known_failure else "needs_recheck",
                            error_code=error_code,
                        )
                    elif active:
                        letter.update(status="ready", result=deepcopy(result))
                    elif letter.get("status") == "running":
                        letter["status"] = "cancelled"
                self._reserve_material_consistency(task)
                self._save(state)
            self._run_material_consistency(task_id)
        except (OSError, ValueError, PortalDataError, helper.StoreError):
            self._runtime_error = "flow_checkpoint_unavailable"
            self._closed.set()
            self._queue.put(None)
        finally:
            if self._closed.is_set():
                self._release_owner()

    def resume_call_allowed(self, expected):
        """Check the saved task and preparation control before each author call."""
        if self._closed.is_set() or self._runtime_error:
            return False
        try:
            with self.applications.write_lock():
                state = self._load()
                task = self._task(state, expected["id"])
                if (
                    self._closed.is_set()
                    or task["status"] == "cancelled"
                    or task["job_binding"] != expected["job_binding"]
                    or task["inputs"] != expected["inputs"]
                    or task["stages"]["resume"].get("attempt_id")
                    != expected["stages"]["resume"].get("attempt_id")
                ):
                    return False
                if self.material_batch and not self.material_batch.guard_admission(state, task):
                    return False
                permit = self.callbacks.get("preparation_allowed")
                return permit(task["id"]) is True if permit is not None else True
        except (OSError, ValueError, KeyError, TypeError, helper.StoreError, PortalDataError):
            return False

    def recheck_resume_author(self, task_id, task_revision):
        with self.applications.write_lock():
            state, task = self._checked(task_id, task_revision)
            handoff = task.get("experience_handoff") or {}
            reader = self.callbacks.get("resume_author_result")
            if (
                task["stages"]["resume"].get("status") != "needs_recheck"
                or not handoff.get("id")
                or reader is None
            ):
                raise PortalDataError(
                    "resume_author_needs_recheck", "简历作者原回执尚不能核验。", 409
                )
            result = reader(deepcopy(task))
            if (
                not isinstance(result, dict)
                or result.get("kind") != "draft"
                or not result.get("id")
                or re.fullmatch(r"[a-f0-9]{64}", result.get("draft_sha256", "")) is None
            ):
                raise PortalDataError(
                    "resume_author_needs_recheck", "简历作者本地采用回执不完整。", 409
                )
            task["stages"]["resume"]["status"] = "pending"
            task["stages"]["resume"].pop("error_code", None)
            task["status"] = "needs_input"
            self._save(state)
            return self.resume_experience_generation(task_id, task["revision"], handoff["id"])

    @staticmethod
    def _consistency_pair(task):
        letter = (task.get("cover_letter") or {}).get("result") or {}
        resume = next(
            (
                row["result"]
                for row in reversed(task.get("artifacts", []))
                if row.get("stage") == "resume"
                and row.get("adopted")
                and row.get("result", {}).get("id") == task.get("draft_id")
            ),
            {},
        )
        resume_revision = resume.get("content_revision") or (
            resume.get("resume_content") or {}
        ).get("revision")
        if not resume_revision or not letter.get("content_revision"):
            return None
        return {
            "resume_content_revision": resume_revision,
            "letter_content_revision": letter["content_revision"],
        }

    def material_consistency_outcome(self, task_id):
        with self.applications.write_lock():
            task = self._task(self._load(), task_id)
            return deepcopy(task.get("material_consistency") or {"status": "not_started"})

    def material_outcomes(self, task_ids):
        """Read queue safety statuses once, without projecting all historical pages."""
        wanted = set(task_ids)
        with self.applications.write_lock():
            return {
                task["id"]: {
                    key: (task.get(key) or {}).get("status", "not_started")
                    for key in ("cover_letter", "material_consistency")
                }
                for task in self._load()["tasks"]
                if task["id"] in wanted
            }

    def _reserve_material_consistency(self, task):
        """Reserve under the material adoption lock before exposing the second result."""
        pair = self._consistency_pair(task)
        previous = task.get("material_consistency") or {}
        if (
            "material_consistency" not in self.callbacks
            or pair is None
            or task["status"] == "cancelled"
            or previous.get("status") in {"running", "needs_recheck"}
            or previous.get("pair_revision") == digest(pair)
        ):
            return
        if previous:
            retired = deepcopy(previous)
            if retired.get("status") == "queued":
                retired.update(status="superseded", adopted=False)
            task.setdefault("material_consistency_history", []).append(retired)
        attempt = uuid4().hex
        task["material_consistency"] = {
            "status": "queued",
            "attempt_id": attempt,
            "pair_revision": digest(pair),
            **pair,
        }
        request_path = self.root / "material-consistency-attempts" / attempt / "request.json"
        helper.atomic_write_json(request_path, deepcopy(task))
        self._queue.put((task["id"], "material-consistency", attempt))

    @staticmethod
    def _cancel_material_consistency(task):
        current = task.get("material_consistency") or {}
        if current.get("status") == "queued":
            task.setdefault("material_consistency_history", []).append(deepcopy(current))
            current.update(status="cancelled", cancel_requested=True)
        elif current.get("status") == "running":
            current["cancel_requested"] = True

    def _run_material_consistency(self, task_id):
        callback = self.callbacks.get("material_consistency")
        if callback is None:
            return
        with self.applications.write_lock():
            if self._closed.is_set():
                return
            state = self._load()
            task = self._task(state, task_id)
            pair = self._consistency_pair(task)
            previous = task.get("material_consistency") or {}
            if (
                pair is not None
                and task["status"] != "cancelled"
                and previous.get("status") == "queued"
                and previous.get("pair_revision") != digest(pair)
            ):
                self._reserve_material_consistency(task)
                self._save(state)
                return
            if (
                pair is None
                or task["status"] == "cancelled"
                or previous.get("status") != "queued"
                or previous.get("pair_revision") != digest(pair)
            ):
                return
            attempt = previous["attempt_id"]
            previous["status"] = "running"
            self._save(state)
            request = deepcopy(task)
        try:
            result = callback(request)
            if (
                not isinstance(result, dict)
                or result.get("status") not in {"passed", "conflict"}
                or any(result.get(key) != value for key, value in pair.items())
            ):
                raise ValueError("material pair response does not match")
            digest(result)
            error_code = None
        except Exception as error:
            result = None
            error_code = getattr(error, "code", "material_consistency_needs_recheck")
        with self.applications.write_lock():
            state = self._load()
            task = self._task(state, task_id)
            current = task.get("material_consistency") or {}
            same_attempt = current.get("attempt_id") == attempt
            active = (
                not self._closed.is_set()
                and same_attempt
                and self._consistency_pair(task) == pair
                and task["status"] != "cancelled"
                and not current.get("cancel_requested")
            )
            if same_attempt and error_code:
                current.update(status="needs_recheck", error_code=error_code)
            elif active:
                current.update(status=result["status"], result=result)
            elif result is not None:
                task.setdefault("material_consistency_history", []).append(
                    {**pair, "result": result, "adopted": False, "attempt_id": attempt}
                )
                if same_attempt and not self._closed.is_set():
                    if current.get("cancel_requested") or task["status"] == "cancelled":
                        current["status"] = "cancelled"
                    else:
                        current["status"] = "superseded"
                        self._reserve_material_consistency(task)
            self._save(state)

    def recheck_material_consistency(self, task_id, task_revision):
        with self.applications.write_lock():
            state, task = self._checked(task_id, task_revision)
            current = task.get("material_consistency") or {}
            reader = self.callbacks.get("material_consistency_result")
            if current.get("status") != "needs_recheck" or reader is None:
                raise PortalDataError(
                    "material_consistency_needs_recheck", "两份材料的一致性回执尚不能核验。", 409
                )
            request_path = (
                self.root / "material-consistency-attempts" / current["attempt_id"] / "request.json"
            )
            original = helper.read_json_object(request_path, "original material pair")
            pair = self._consistency_pair(original)
            if pair is None or digest(pair) != current["pair_revision"]:
                raise PortalDataError(
                    "material_consistency_needs_recheck", "原一致性输入版本不能核验。", 409
                )
            result = reader(original)
            if result.get("status") not in {"passed", "conflict"} or any(
                result.get(key) != value for key, value in pair.items()
            ):
                raise PortalDataError(
                    "material_consistency_needs_recheck", "两份材料的一致性回执版本不符。", 409
                )
            cancelled = current.get("cancel_requested") or task["status"] == "cancelled"
            if self._consistency_pair(task) == pair and not cancelled:
                current.update(status=result["status"], result=result)
            else:
                task.setdefault("material_consistency_history", []).append(
                    {
                        **pair,
                        "result": result,
                        "adopted": False,
                        "attempt_id": current["attempt_id"],
                    }
                )
                current["status"] = "cancelled" if cancelled else "superseded"
            current.pop("error_code", None)
            self._reserve_material_consistency(task)
            self._save(state)
            return deepcopy(task)

    def retry_material_consistency(self, task_id, task_revision):
        """Only a durably queued, never-admitted check permits a new call."""
        with self.applications.write_lock():
            state, task = self._checked(task_id, task_revision)
            current = task.get("material_consistency") or {}
            if not (
                current.get("status") == "failed"
                and current.get("error_code") == "material_consistency_not_started"
                or current.get("status") == "cancelled"
                and current.get("cancel_requested")
            ):
                raise PortalDataError(
                    "material_consistency_needs_recheck", "原一致性调用须核验，不能重放。", 409
                )
            self._check_other_material_pending(state, task)
            current.pop("pair_revision", None)
            self._reserve_material_consistency(task)
            self._save(state)
            return deepcopy(task)

    def start(self, task_id, task_revision, stage, *, retry=False, _continuation_request_id=None):
        self._writable()
        if stage not in self.callbacks or stage not in {"analysis", "resume", "export"}:
            raise PortalDataError("flow_stage_unavailable", "此任务阶段暂不可用。", 409)
        with self.applications.write_lock():
            self._writable()
            state = self._load()
            task = self._task(state, task_id)
            self._check_other_match_pending(task)
            if task.get("codex_handoff_ref") or task.get("codex_handoff_attempt"):
                raise PortalDataError(
                    "flow_handoff_bound",
                    "已有上传记录已接回；请保留表单并由用户完成最终 Submit。",
                    409,
                )
            self._group_guard_change(task)
            if task.get("origin") == "existing_latex" and stage != "export":
                raise PortalDataError(
                    "flow_latex_technical_only",
                    "已有 LaTeX 任务只执行技术导出，不运行分析或生成。",
                    409,
                )
            if self.material_batch:
                self.material_batch.guard_start(state, task, stage)
            if task["status"] == "cancelled":
                raise PortalDataError("flow_cancelled", "任务已取消，请建立新任务。", 409)
            if stage == "resume" and task.get("worker_ref"):
                raise PortalDataError(
                    "flow_materials_in_use", "已有填写任务绑定材料，请保留原页更新。", 409
                )
            application = self._fresh(task, stage=stage)
            current = task["stages"].get(stage, {"status": "pending"})
            regenerate = stage in {"resume", "export"} and current["status"] == "complete" and retry
            if stage == "export":
                self._reviewed_draft(task)
                if current["status"] == "needs_recheck":
                    raise PortalDataError(
                        "flow_export_recheck_required", "导出结果未明，请先核验回执。", 409
                    )
            if stage == "resume" and task["stages"].get("export", {}).get("status") in {
                "queued",
                "running",
                "needs_recheck",
            }:
                raise PortalDataError(
                    "flow_export_recheck_required", "导出尚未确定，请先核验本次导出。", 409
                )
            author_retry = (
                stage == "resume"
                and current["status"] == "needs_recheck"
                and retry
                and current.get("error_code") == "resume_author_needs_recheck"
            )
            if author_retry and task.get("experience_handoff"):
                # The unadopted handoff keeps the plan it was built with; the retry builds
                # a new one from current inputs, and the old one stays in history.
                task.setdefault("experience_handoff_history", []).append(
                    task.pop("experience_handoff")
                )
            if stage == "resume" and current["status"] == "needs_recheck" and not author_retry:
                raise PortalDataError(
                    "flow_resume_recheck_required", "写作结果尚未核验，请先保留并核对原交付。", 409
                )
            if current["status"] in {"queued", "running"} or (
                current["status"] == "complete" and not regenerate
            ):
                return deepcopy(task)
            if task["revision"] != task_revision:
                raise PortalDataError("conflict", "任务已变化，请重新读取。", 409)
            if stage == "resume" and task["stages"]["analysis"]["status"] != "complete":
                raise PortalDataError("flow_analysis_required", "请先完成当前岗位分析。", 409)
            fixed_writing = (
                self.fixed_writing_inputs(task) if stage in {"resume", "export"} else None
            )
            content_writing = False
            if fixed_writing is not None:
                from .application_writing import is_content_delivery

                content_writing = is_content_delivery(fixed_writing["analysis"])
            if (
                fixed_writing is not None
                and fixed_writing["handoff"] is not None
                and fixed_writing["handoff"].get("status") != "adopted"
                and not (
                    stage == "resume"
                    and current.get("status") == "failed"
                    and current.get("error_code")
                    in {"resume_author_paused", "resume_author_failed"}
                    and retry
                )
            ):
                raise PortalDataError(
                    "flow_generation_not_adopted", "经历写作尚未采用，请先完成或核验原交付。", 409
                )
            if fixed_writing is not None and self.preparation_only:
                from .application_draft import resume_language_policy

                if (
                    resume_language_policy(application.get("job_description", ""))["status"]
                    == "needs_input"
                ):
                    raise PortalDataError(
                        "flow_resume_language_required",
                        "岗位明确要求其他简历语言，请先提示并单独处理。",
                        409,
                    )
                if task_eligibility(task, bind_inputs=True)["status"] not in {
                    "supported",
                    "not_specified",
                }:
                    raise PortalDataError(
                        "flow_qualification_required", "请先补齐或核验本岗已交付的必需资格。", 409
                    )
            if (
                stage in {"resume", "export"}
                and fixed_writing is None
                and self.preparation_only
                and task.get("origin") != "existing_latex"
            ):
                from .application_draft import resume_language_policy

                if (
                    resume_language_policy(application.get("job_description", ""))["status"]
                    == "needs_input"
                ):
                    raise PortalDataError(
                        "flow_resume_language_required",
                        "岗位明确要求其他简历语言，请先提示并单独处理。",
                        409,
                    )
                library = self.information_provider() if self.information_provider else None
                if self._explanation(application, task, library)["qualification"]["status"] not in {
                    "supported",
                    "not_specified",
                }:
                    raise PortalDataError(
                        "flow_qualification_required", "请先补齐或核验本岗的必需资格。", 409
                    )
            if stage == "resume" and task["worker_ref"]:
                raise PortalDataError(
                    "flow_materials_in_use", "已有填写任务绑定材料，请先核验原任务和附件。", 409
                )
            task["application_revision"] = application["revision"]
            if current["status"] == "failed" and not retry:
                raise PortalDataError("flow_retry_required", "此阶段失败，请明确重试。", 409)
            attempt_id = uuid4().hex
            task["stages"][stage] = {"status": "queued", "attempt_id": attempt_id}
            if stage == "resume" and current["status"] == "failed" and retry:
                for key in ("regenerate", "retained_draft"):
                    if key in current:
                        task["stages"][stage][key] = deepcopy(current[key])
            if stage == "analysis":
                binding = digest(analysis_input_binding(task["inputs"]))
                task["stages"][stage]["analysis_input_revision"] = binding
                if current["status"] == "failed":
                    task.setdefault("analysis_attempts", []).append(
                        {
                            "stage": deepcopy(current),
                            "inputs": deepcopy(task["inputs"]),
                            "job_binding": task["job_binding"],
                        }
                    )
                    if current.get("analysis_input_revision") == binding:
                        task["stages"][stage]["resume_from_attempt_id"] = current["attempt_id"]
            if (
                stage == "resume"
                and task.get("latex_base")
                and not content_writing
                and not regenerate
                and task.get("experience_handoff", {}).get("generation_contract")
                not in {"fixed-writing/v1", "content-writing/v1"}
            ):
                from .application_resume import retained_preparation_base

                base = retained_preparation_base(task, self.callbacks.get("retained_draft"))
                if base:
                    task["stages"][stage]["latex_base"] = base
            if stage == "export":
                task["stages"][stage]["configuration_revision"] = self._export_configuration(task)
                if not local_materials(task):
                    task.update(resume_id=None, resume_sha256=None, materials_confirmed=False)
            if regenerate and stage == "resume":
                # Explicit regeneration uses today's generator settings. Completed
                # artifact bindings remain immutable in the retained history.
                if task.get("draft_id"):
                    task["stages"][stage]["retained_draft"] = {
                        "id": task["draft_id"],
                        "draft_sha256": task["draft_sha256"],
                    }
                if task.get("experience_handoff"):
                    delivery = self.fixed_writing_inputs(task)
                    previous = delivery["handoff"] if delivery else task["experience_handoff"]
                    if delivery and previous.get("status") != "adopted":
                        raise PortalDataError(
                            "flow_generation_not_adopted",
                            "经历交付尚未采用，请先完成或核验原写作任务。",
                            409,
                        )
                    task.setdefault("experience_handoff_history", []).append(deepcopy(previous))
                    task.pop("experience_handoff")
                retire_local_materials(task)
                latest_inputs = self._identity(
                    application, None if self.input_provider else task["inputs"]
                )
                configuration_key = "resume_configuration_revision"
                if configuration_key in latest_inputs:
                    task["inputs"][configuration_key] = latest_inputs[configuration_key]
                else:
                    task["inputs"].pop(configuration_key, None)
                task.pop("pdf_reuse", None)
                if task.get("prism"):
                    task.setdefault("prism_history", []).append(task.pop("prism"))
                task["input_epoch"] = task.get("input_epoch", 0) + 1
                batch = state.get("preparation_batch")
                if batch and batch.get("active_task_id") == task["id"]:
                    row = next(
                        item
                        for item in batch["items"]
                        if item["item_id"] == batch["active_item_id"]
                    )
                    row.setdefault("binding_history", []).append(
                        {"task_id": task["id"], "input_epoch": row["task_input_epoch"]}
                    )
                    row["task_input_epoch"] = task["input_epoch"]
                task["stages"][stage]["regenerate"] = True
                task.update(
                    resume_id=None,
                    resume_sha256=None,
                    materials_confirmed=False,
                    draft_id=None,
                    draft_sha256=None,
                    draft_review=None,
                )
                if "export" in task["stages"]:
                    task["stages"]["export"] = {"status": "pending"}
            task["status"] = (
                "analyzing"
                if stage == "analysis"
                else "exporting"
                if stage == "export"
                else "resume_generating"
            )
            letter_attempt = (
                self._reserve_cover_letter(
                    state,
                    task,
                    # An approved writing retry also re-runs an unknown letter call.
                    retry=author_retry,
                    _continuation_request_id=_continuation_request_id,
                )
                if stage == "resume"
                else None
            )
            _record_preparation_attempt(
                task, stage, attempt_id, current.get("attempt_id"), _continuation_request_id
            )
            self._save(state)
            if stage == "resume":
                observer = self.callbacks.get("observe_preparation_started")
                if observer:
                    observer(deepcopy(task))
            self._queue.put((task_id, stage, attempt_id))
            self._launch_cover_letter(task_id, letter_attempt)
            return deepcopy(task)

    def _run(self):
        try:
            self._run_tasks()
        except (OSError, ValueError, PortalDataError, helper.StoreError):
            self._runtime_error = "flow_checkpoint_unavailable"
            self._closed.set()
            try:
                with self.applications.write_lock():
                    self._recover(self._runtime_error)
            except (OSError, ValueError, PortalDataError, helper.StoreError):
                pass
        finally:
            self._release_owner()

    def _verify_pdf_reuse(self, task, result):
        verifier = self.callbacks.get("verify_pdf_reuse")
        if (
            not (self.preparation_only or task.get("automatic_materials"))
            or verifier is None
            or task.get("worker_ref")
            or task["stages"]["resume"].get("regenerate")
            or result.get("application_id") != task["application_id"]
            or result.get("analysis_binding", {}).get("analysis_id") != task["analysis_id"]
            or result.get("resume_configuration_revision")
            != task["inputs"].get("resume_configuration_revision")
            or not isinstance(result.get("reuse_binding"), dict)
        ):
            raise PortalDataError("flow_materials_mismatch", "当前材料采用关系不能核验。", 409)
        verifier(deepcopy(task), deepcopy(result))

    def _run_tasks(self):
        while not self._closed.is_set():
            item = self._queue.get()
            if item is None or self._closed.is_set():
                return
            task_id, stage, attempt_id = item
            if stage == "material-consistency":
                self._run_material_consistency(task_id)
                continue
            if stage == "bound-material":
                self._prepare_material_update(task_id, attempt_id)
                continue
            if stage == "batch" and self.material_batch:
                self.material_batch.advance(task_id, attempt_id)
                continue
            with self.applications.write_lock():
                if self._closed.is_set():
                    return
                state = self._load()
                task = self._task(state, task_id)
                if (
                    task["stages"][stage].get("attempt_id") != attempt_id
                    or task["stages"][stage]["status"] != "queued"
                ):
                    continue
                if self.material_batch and not self.material_batch.guard_admission(state, task):
                    continue
                task["stages"][stage]["status"] = "running"
                self._save(state)
                request = deepcopy(task)
                self._running_stage_task_id = task_id
            result = None
            failed_handoff = None
            try:
                self._fresh(request, stage=stage)
                candidate = self.callbacks[stage](request)
                if (
                    not isinstance(candidate, dict)
                    or not isinstance(candidate.get("id"), str)
                    or not candidate["id"]
                ):
                    raise PortalDataError("flow_result_invalid", "阶段结果缺少有效身份。", 409)
                digest(candidate)
                handoff = stage == "resume" and candidate.get("kind") == "experience_handoff"
                if handoff:
                    if candidate.get("status") not in {
                        "codex_required",
                        "writing_required",
                        "review_required",
                        "adopted",
                    }:
                        raise PortalDataError(
                            "flow_result_invalid", "经历生成进度缺少有效状态。", 409
                        )
                else:
                    fingerprint = (
                        "draft_sha256"
                        if (self.preparation_only or request.get("automatic_materials"))
                        and candidate.get("kind") == "draft"
                        else "pdf_sha256"
                    )
                    if stage in {"resume", "export"} and (
                        not isinstance(candidate.get(fingerprint), str)
                        or re.fullmatch(r"[a-f0-9]{64}", candidate[fingerprint]) is None
                    ):
                        raise PortalDataError(
                            "flow_result_invalid", "简历结果缺少有效文件指纹。", 409
                        )
                    if stage == "export":
                        self._export_result(request, candidate)
                    reused_pdf = stage == "resume" and candidate.get("kind") in {
                        "accepted_pdf_reuse",
                        "checked_pdf_reuse",
                    }
                    if reused_pdf:
                        self._verify_pdf_reuse(request, candidate)
                    if stage == "resume" and not reused_pdf:
                        from .application_resume import validate_prepared_result

                        validator = self.callbacks.get("verify_prepared_resume")
                        if validator:
                            validator(request, candidate)
                        else:
                            validate_prepared_result(request, candidate)
                result = candidate
                error_code = None
            except Exception as error:
                failed_handoff = getattr(error, "experience_handoff", None)
                error_code = (
                    error.code
                    if isinstance(error, PortalDataError)
                    else "resume_export_needs_recheck"
                    if stage == "export"
                    else "flow_stage_failed"
                )
            finally:
                with self.applications.write_lock():
                    self._running_stage_task_id = None
            with self.applications.write_lock():
                if self._closed.is_set():
                    return
                state = self._load()
                task = self._task(state, task_id)
                active = (
                    task["stages"][stage].get("attempt_id") == attempt_id
                    and task["stages"][stage]["status"] == "running"
                )
                if active and error_code is None:
                    try:
                        self._fresh(request, stage=stage)
                        if stage == "export":
                            self._export_result(request, result)
                        if stage == "resume" and result.get("kind") in {
                            "accepted_pdf_reuse",
                            "checked_pdf_reuse",
                        }:
                            self._verify_pdf_reuse(request, result)
                            self._fresh(request, stage=stage)
                    except Exception as error:
                        error_code = (
                            error.code
                            if isinstance(error, PortalDataError)
                            else "flow_stage_failed"
                        )
                if result is not None:
                    task["artifacts"].append(
                        {
                            "stage": stage,
                            "attempt_id": attempt_id,
                            "result": result,
                            "inputs": request["inputs"],
                            "adopted": active
                            and not error_code
                            and result.get("kind") != "experience_handoff",
                        }
                    )
                if not active:
                    self._batch_after(state, task)
                    self._save(state)
                    continue
                if error_code:
                    if (
                        stage == "analysis"
                        and error_code == "flow_preparation_stopped"
                        and self._retain_stopped_analysis(task, request, attempt_id)
                    ):
                        self._batch_after(state, task)
                        self._save(state)
                        continue
                    if stage == "resume" and isinstance(failed_handoff, dict):
                        task["experience_handoff"] = deepcopy(failed_handoff)
                    uncertain = (
                        error_code == "resume_author_needs_recheck"
                        or stage == "export"
                        and error_code
                        in {
                            "resume_export_needs_recheck",
                            "flow_export_mismatch",
                            "flow_result_invalid",
                        }
                    )
                    task["stages"][stage].update(
                        status="needs_recheck" if uncertain else "failed", error_code=error_code
                    )
                    task["status"] = (
                        "needs_recheck"
                        if uncertain
                        else "stale"
                        if error_code == "flow_inputs_stale"
                        else "export_failed"
                        if stage == "export"
                        else "failed"
                    )
                    self._batch_after(state, task)
                    self._save(state)
                    continue
                if stage == "resume" and result.get("kind") == "experience_handoff":
                    task["experience_handoff"] = deepcopy(result)
                    task["stages"][stage].update(status="pending", generation_id=result["id"])
                    task["stages"][stage].pop("regenerate", None)
                    task["status"] = "needs_input"
                    self._batch_after(state, task)
                    self._save(state)
                    continue
                if stage == "resume":
                    task.pop("experience_handoff", None)
                task["stages"][stage].update(status="complete", artifact_id=result["id"])
                if stage == "export":
                    self._adopt_export(task, result)
                elif stage == "resume" and result.get("kind") in {
                    "accepted_pdf_reuse",
                    "checked_pdf_reuse",
                }:
                    task.update(
                        resume_id=result["id"],
                        resume_sha256=result["pdf_sha256"],
                        pdf_reuse=deepcopy(result["reuse_binding"]),
                        draft_id=None,
                        draft_sha256=None,
                        draft_review=None,
                        materials_confirmed=True,
                        status="materials_ready",
                    )
                elif (
                    stage == "resume"
                    and (self.preparation_only or task.get("automatic_materials"))
                    and result.get("kind") == "draft"
                ):
                    task.update(
                        draft_id=result["id"],
                        draft_sha256=result["draft_sha256"],
                        draft_review=None,
                        resume_id=None,
                        resume_sha256=None,
                        materials_confirmed=False,
                        status="draft_ready",
                    )
                    from .application_resume import prepared_material_state

                    task.update(
                        prepared_material_state(
                            result, automatic_materials=bool(task.get("automatic_materials"))
                        )
                    )
                else:
                    task[f"{stage}_id"] = result["id"]
                    task["status"] = f"{stage}_ready"
                if stage == "resume" and result.get("kind") != "draft":
                    task["resume_sha256"] = result.get("pdf_sha256")
                self._batch_after(state, task)
                self._reserve_material_consistency(task)
                self._save_material_result(state, task)
                if stage in {"resume", "export"} and task.get("resume_id"):
                    observer = self.callbacks.get("observe_pdf_ready")
                    if observer:
                        observer(deepcopy(task))
            if stage in {"resume", "export"}:
                self._run_material_consistency(task_id)

    def _release_owner(self):
        with self._owner_guard:
            current = threading.current_thread()
            if any(
                thread is not current and thread.is_alive()
                for thread in [self._thread, *self._letter_threads.values()]
                if thread is not None
            ):
                return
            if not self._lock_file.closed:
                fcntl.flock(self._lock_file, fcntl.LOCK_UN)
                self._lock_file.close()

    def close(self):
        try:
            with self.applications.write_lock():
                if not self._closed.is_set():
                    self._closed.set()
                    self._queue.put(None)
                    if self._owner:
                        self._recover()
        finally:
            if self._thread is not None:
                self._thread.join(timeout=0.2)
            for thread in list(self._letter_threads.values()):
                thread.join(timeout=0.2)
            if self._thread is None or not self._thread.is_alive():
                self._release_owner()
