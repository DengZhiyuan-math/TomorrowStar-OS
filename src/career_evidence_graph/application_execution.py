"""Persistent single-executor ownership shared by Codex and automated lanes.

Reservations never expire. A crashed executor keeps ownership until its matching
owner explicitly releases it after page and pending-action reconciliation.
"""

from __future__ import annotations

import hashlib
import time
from pathlib import Path

from ._vendor import job_apply_store as helper
from .career_portal_data import ApplicationStore, PortalDataError


def _record(applications: ApplicationStore, application_id: str, owner: str, lane: str):
    if (
        lane not in {"codex", "automated"}
        or not isinstance(owner, str)
        or not owner.strip()
        or len(owner) > 1000
        or not isinstance(application_id, str)
        or not application_id
    ):
        raise PortalDataError("execution_invalid", "执行者身份或执行通道无效。", 409)
    directory = applications.root / ".execution"
    if directory.is_symlink():
        raise PortalDataError("execution_invalid", "执行占用目录不能是符号链接。", 409)
    if directory.exists() and not directory.is_dir():
        raise PortalDataError("execution_invalid", "执行占用目录无效。", 409)
    path = directory / (hashlib.sha256(application_id.encode()).hexdigest() + ".json")
    if path.is_symlink():
        raise PortalDataError("execution_invalid", "执行占用记录不能是符号链接。", 409)
    try:
        record = helper.read_json_object(path, "execution ownership") if path.exists() else {}
    except (ValueError, OSError, helper.StoreError) as exc:
        raise PortalDataError("execution_invalid", "执行占用记录损坏，请先核验。", 409) from exc
    if record and (
        record.get("application_id") != application_id
        or record.get("schemaVersion") != 1
        or not isinstance(record.get("active"), bool)
        or record.get("lane") not in {"codex", "automated"}
        or not isinstance(record.get("owner"), str)
        or not record["owner"]
    ):
        raise PortalDataError("execution_invalid", "执行占用记录损坏，请先核验。", 409)
    return path, record


def reserve_execution(
    applications: ApplicationStore, application_id: str, owner: str, lane: str
) -> dict:
    """Reserve idempotently; an active different owner or lane always blocks."""
    with applications.write_lock():
        path, record = _record(applications, application_id, owner, lane)
        path.parent.mkdir(mode=0o700, exist_ok=True)
        if record.get("active"):
            require_execution(applications, application_id, owner, lane)
            return record
        history = record.get("history", []) + (
            [{k: v for k, v in record.items() if k != "history"}] if record else []
        )
        record = {
            "schemaVersion": 1,
            "application_id": application_id,
            "owner": owner,
            "lane": lane,
            "active": True,
            "reserved_at": time.time(),
            "history": history,
        }
        helper.atomic_write_json(path, record)
        return record


def require_execution(
    applications: ApplicationStore, application_id: str, owner: str, lane: str
) -> dict:
    """Verify exact persistent ownership before any browser mutation."""
    with applications.write_lock():
        _, record = _record(applications, application_id, owner, lane)
        if not record.get("active"):
            raise PortalDataError("execution_missing", "岗位没有有效执行占用，请先准备任务。", 409)
        if record.get("owner") != owner or record.get("lane") != lane:
            raise PortalDataError(
                "execution_conflict", "岗位已被另一执行者占用，请先完成交接。", 409
            )
        return record


def release_execution(
    applications: ApplicationStore, application_id: str, owner: str, lane: str
) -> None:
    """Release the exact owner only, preserving its receipt in the same record."""
    with applications.write_lock():
        path, record = _record(applications, application_id, owner, lane)
        if not record:
            raise PortalDataError("execution_missing", "岗位没有执行占用记录。", 409)
        if record["owner"] != owner or record["lane"] != lane:
            if any(
                isinstance(receipt, dict)
                and receipt.get("owner") == owner
                and receipt.get("lane") == lane
                and receipt.get("active") is False
                for receipt in record.get("history", [])
            ):
                # A delayed state write may finish after a different lane has
                # claimed the job. Confirm the old release without touching it.
                return
            raise PortalDataError("execution_conflict", "岗位已被另一执行者占用。", 409)
        if record["active"]:
            helper.atomic_write_json(path, {**record, "active": False, "released_at": time.time()})


def automated_owner(root: Path, batch_id: str, application_id: str) -> str:
    """Stable across worker restarts; distinct for every runtime and batch."""
    raw = f"{root.resolve()}\0{batch_id}\0{application_id}"
    return "automated:" + hashlib.sha256(raw.encode()).hexdigest()


def reject_mixed_execution_root(root: Path, other_marker: str) -> None:
    """Reject overlapping lane roots before creating any state or answer library."""
    root = root.resolve()
    if any(
        (ancestor / other_marker).exists() or (ancestor / other_marker).is_symlink()
        for ancestor in (root, *root.parents)
    ) or any(root.rglob(other_marker)):
        raise ValueError("Keep Codex handoff and automated worker stores separate.")


def write_admission_reason(receipt, stage, state, task, job, now, *, country=None):
    """Admit a requested stage, separately from diagnostic readiness and user consent."""
    if (
        stage not in {"prepare", "resume", "recheck", "answer", "library", "heartbeat"}
        or receipt["package"].get("status") != "verified"
        or receipt["package"].get("loaded_mapping") != "verified"
        or receipt["controller"].get("source_matches_disk") is not True
        or receipt["controller"].get("ui_matches_disk") is not True
        or receipt["native_host"].get("state") != "verified"
        or receipt["native_host"].get("session_open") is not True
        or type(receipt["native_host"].get("invalidation_epoch")) is not int
        or receipt["native_host"].get("invalidation_epoch", -1) < 0
        or receipt["native_host"].get("bridge_binding_verified") is not True
        or receipt["inputs"].get("state") != "current"
        or not (
            receipt["inputs"].get("materials_confirmed") is True
            or stage == "prepare"
            and receipt["inputs"].get("materials_current") is True
            and (task or {}).get("status") in {"resume_ready", "materials_ready"}
            and not (task or {}).get("worker_ref")
        )
        or receipt["inputs"].get("qualification")
        not in {"supported", "not_specified", "needs_input"}
        or not task
        or task.get("status") == "cancelled"
        or state.get("control")
        != ("running" if stage in {"answer", "library", "heartbeat"} else "paused")
        or state.get("commands")
        or receipt["worker"].get("last_error")
        or "worker_storage_stopped" in receipt.get("reasons", ())
    ):
        return "installed_evidence_required"
    if stage == "prepare":
        if (
            receipt["inputs"].get("pending_prepare")
            or state.get("runtime") is not None
            or state.get("worker_pid") is not None
            or any(
                row.get("page_open")
                or row.get("page_observation")
                or row.get("intent")
                or row.get("manual_submission")
                or row.get("handed_off")
                for row in state.get("jobs", ())
            )
        ):
            return "prepare_has_retained_work"
        existing = state.get("jobs", ())
        if existing and not all(row.get("status") == "cancelled" for row in existing):
            binding = (job or {}).get("single_binding") or {}
            if (
                len(existing) != 1
                or not job
                or job.get("workflow") != "single"
                or job.get("status") != "queued"
                or job.get("country") != country
                or job.get("observations")
                or job.get("answer_refs")
                or job.get("questions")
                or binding.get("task_id") != task.get("id")
                or binding.get("country") != country
                or binding.get("job_url") != job.get("job_url")
                or job.get("file_sha256") != task.get("resume_sha256")
                or any(
                    binding.get(key) != task.get(key)
                    for key in (
                        "job_binding",
                        "inputs",
                        "analysis_id",
                        "resume_id",
                        "resume_sha256",
                    )
                )
            ):
                return "prepare_existing_batch_unverified"
        return None
    if not receipt["inputs"].get("send_scope_confirmed") or not job:
        return "send_scope_unverified"
    runtime = state.get("runtime")
    if runtime is None:
        if stage != "resume":
            return "worker_runtime_required"
        if (
            receipt["inputs"].get("owned_process_alive")
            or state.get("worker_pid") is not None
            or any(
                row.get("status") != "queued"
                or row.get("handed_off")
                or row.get("page_open")
                or row.get("page_observation")
                or row.get("intent")
                or row.get("manual_submission")
                or row.get("observations")
                or row.get("answer_refs")
                or row.get("questions")
                for row in state.get("jobs", ())
            )
        ):
            return "bootstrap_has_retained_work"
        return None
    # An unknown/stale old runtime is never a new-run fallback.
    if (
        receipt["worker"].get("process") != "managed"
        or not runtime.get("loaded_engine_revision")
        or not 0 <= now - runtime.get("observed_at", 0) < 6
        or receipt["compatibility"].get("commands", {}).get(stage) != "supported"
        or not receipt["compatibility"].get("basis")
        or job.get("manual_submission")
    ):
        return "retained_resume_evidence_required"
    if stage in {"resume", "recheck"} and (
        receipt["page"].get("state") != "current"
        or not 0 <= now - (receipt["page"].get("observed_at") or 0) < 10
    ):
        return "retained_page_evidence_required"
    if stage == "resume" and (
        job.get("intent")
        or job.get("handed_off")
        or job.get("status") not in {"queued", "filling", "needs_input"}
    ):
        return "retained_action_unresolved"
    return None
