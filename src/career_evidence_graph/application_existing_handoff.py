"""Read an existing executor report; never initialize or run an executor."""

import time
from copy import deepcopy
from pathlib import Path

from ._vendor import job_apply_store as helper
from .application_automation import application_key
from .application_handoff import CodexHandoffService
from .career_portal_data import PortalDataError
from .validation.hashing import record_digest as digest


def read_existing(applications, task, handoff_root, handoff_task_id, handoff_task_revision):
    service = CodexHandoffService(applications, Path(handoff_root), existing_only=True)
    reference = service.existing_reference(handoff_task_id, handoff_task_revision)
    current = applications.get_application(task["application_id"])
    if (
        reference["application_id"] != task["application_id"]
        or application_key(reference["job_url"]) != application_key(current["url"])
        or reference["file_sha256"] != task.get("resume_sha256")
    ):
        raise PortalDataError("flow_handoff_mismatch", "既有上传与当前岗位或 PDF 不符。", 409)
    return reference


def attach(flow, task_id, task_revision, handoff_root, handoff_task_id, handoff_task_revision):
    from .application_flow import _material_pending

    with flow.applications.write_lock():
        flow._writable()
        state, task = flow._read_checked(task_id, task_revision)
        if task.get("codex_handoff_attempt") or task.get("codex_handoff_restart"):
            raise PortalDataError("flow_handoff_bound", "当前填写尝试已绑定，请读取本次结果。", 409)
        if (
            not flow.preparation_only
            or task.get("worker_ref")
            or task.get("status") != "materials_ready"
            or _material_pending(task)
            or task.get("worker_preparation", {}).get("status") == "pending"
            or not task.get("materials_confirmed")
            or flow._group_guard_change(task)
            or any(stage["status"] != "complete" for stage in task["stages"].values())
        ):
            raise PortalDataError(
                "flow_materials_required", "请先核验当前完整材料和未知操作。", 409
            )
        verifier = flow.callbacks.get("verify_materials")
        if verifier is None:
            raise PortalDataError("flow_materials_required", "当前 PDF 暂不能核验。", 409)
        flow._fresh(task)
        verifier(deepcopy(task))
        reference = read_existing(
            flow.applications, task, handoff_root, handoff_task_id, handoff_task_revision
        )
        previous = task.get("codex_handoff_ref")
        if previous:
            if previous == reference:
                return deepcopy(task)
            raise PortalDataError(
                "flow_handoff_conflict", "任务已接入另一上传记录，请先核验。", 409
            )
        task["codex_handoff_ref"] = reference
        task.setdefault("codex_handoff_history", []).append(
            {
                "action": "attached_existing_handoff",
                "at": time.time(),
                "task_id": reference["task_id"],
                "task_revision": reference["task_revision"],
                "readback_revision": reference["readback_revision"],
                "human_reviewed": False,
            }
        )
        flow._save(state)
        return deepcopy(task)


def _materials_key(task):
    return digest(
        {
            key: task.get(key)
            for key in (
                "application_id",
                "job_binding",
                "inputs",
                "draft_id",
                "draft_sha256",
                "resume_id",
                "resume_sha256",
                "material_binding",
            )
        }
    )


def _check_materials(flow, task):
    from .application_flow import _material_pending

    if (
        not flow.preparation_only
        or task.get("worker_ref")
        or task.get("status") != "materials_ready"
        or _material_pending(task)
        or task.get("worker_preparation", {}).get("status") == "pending"
        or not task.get("materials_confirmed")
        or flow._group_guard_change(task)
        or any(stage["status"] != "complete" for stage in task["stages"].values())
    ):
        raise PortalDataError("flow_materials_required", "请先核验当前材料和未知操作。", 409)
    verifier = flow.callbacks.get("verify_materials")
    if verifier is None:
        raise PortalDataError("flow_materials_required", "当前 PDF 暂不能核验。", 409)
    flow._fresh(task)
    verifier(deepcopy(task))


def _binding(task):
    return task.get("codex_handoff_ref") or task.get("codex_handoff_attempt")


def _information_root(flow, task):
    value = flow.information_library_root
    if value is None:
        inputs = task["inputs"]
        if flow.input_provider is not None:
            application = flow.applications.get_application(task["application_id"])
            inputs = flow._identity(application)
        if "information_library_root" not in inputs:
            return None
        value = inputs["information_library_root"]
    if not isinstance(value, (str, Path)) or not str(value).strip():
        raise PortalDataError("information_library_unavailable", "当前信息库目录未配置。", 409)
    path = Path(value).expanduser()
    if not path.is_absolute() or path.resolve() != path:
        raise PortalDataError("information_library_unavailable", "当前信息库目录不能核验。", 409)
    return path


def _same_material_task(flow, task, child, binding):
    application = flow.applications.get_application(task["application_id"])
    if (
        child["application_id"] != task["application_id"]
        or application_key(child["job_url"]) != application_key(application["url"])
        or child["file_sha256"] != task.get("resume_sha256")
        or child["file_sha256"] != binding.get("file_sha256")
        or child["filename"] != binding.get("filename")
    ):
        raise PortalDataError("flow_handoff_mismatch", "填写尝试与当前岗位或 PDF 不符。", 409)


def restart(flow, task_id, task_revision):
    """Prepare a fresh execution from saved materials, not an old browser session."""
    with flow.applications.write_lock():
        flow._writable()
        state = flow._load()
        task = flow._task(state, task_id)
        attempt = task.get("codex_handoff_attempt")
        pending = task.get("codex_handoff_restart")
        _check_materials(flow, task)
        information_root = _information_root(flow, task)
        information_path = str(information_root) if information_root is not None else None
        if (
            not pending
            and attempt
            and attempt.get("origin_task_revision") == task_revision
            and attempt.get("material_key") == _materials_key(task)
        ):
            if information_path and attempt.get("information_library_root") != information_path:
                raise PortalDataError(
                    "flow_information_changed", "信息库来源已变化，请核验当前尝试。", 409
                )
            # A lost successful response does not create another execution.
            return deepcopy(task)
        if pending:
            if (
                task_revision not in {task["revision"], pending["origin_task_revision"]}
                or pending["material_key"] != _materials_key(task)
                or pending["binding_key"] != digest(_binding(task))
                or pending.get("information_library_root") != information_path
            ):
                raise PortalDataError("conflict", "重开请求或材料已变化，请读取当前任务。", 409)
        else:
            if task["revision"] != task_revision:
                raise PortalDataError("conflict", "任务已变化，请重新读取。", 409)
            previous = _binding(task)
            if not previous:
                raise PortalDataError(
                    "flow_handoff_required", "当前任务没有可复用的填写记录。", 409
                )
            reader = CodexHandoffService(
                flow.applications, Path(previous["root"]), existing_only=True
            )
            child = next(
                (row for row in reader.snapshot()["tasks"] if row["id"] == previous["task_id"]),
                None,
            )
            if child is None:
                raise PortalDataError("handoff_not_found", "原填写记录不存在，请保留材料。", 409)
            _same_material_task(flow, task, child, previous)
            if task.get("codex_handoff_ref") and child["revision"] != previous["task_revision"]:
                raise PortalDataError("flow_handoff_changed", "原填写记录已变化，请先核验。", 409)
            if child["status"] != "ready_for_review":
                raise PortalDataError(
                    "handoff_not_ready", "原填写结果尚未明确，不能建立新尝试。", 409
                )
            predecessor = {
                "root": previous["root"],
                "task_id": child["id"],
                "task_revision": child["revision"],
                "application_id": child["application_id"],
                "job_url": child["job_url"],
                "filename": child["filename"],
                "file_sha256": child["file_sha256"],
            }
            pending = {
                "origin_task_revision": task_revision,
                "request_id": digest({"flow_id": task_id, "flow_revision": task_revision}),
                "predecessor": predecessor,
                "binding_key": digest(previous),
                "material_key": _materials_key(task),
                "information_library_root": information_path,
            }
            # Retain the existing reference until the child preparation is known.
            task["codex_handoff_restart"] = pending
            flow._save(state)
        predecessor = pending["predecessor"]
        service = CodexHandoffService(
            flow.applications,
            Path(predecessor["root"]),
            information_library_root=information_root,
        )
        reply = service.request(
            "restart",
            {
                "task_id": predecessor["task_id"],
                "task_revision": predecessor["task_revision"],
                "request_id": pending["request_id"],
            },
        )
        child = reply.get("active_task")
        if (
            not child
            or child.get("reuse_context", {}).get("predecessor_id") != predecessor["task_id"]
            or child.get("reuse_context", {}).get("request_id") != pending["request_id"]
        ):
            raise PortalDataError("flow_handoff_mismatch", "新的填写尝试尚未完整核验。", 409)
        _same_material_task(flow, task, child, predecessor)
        if information_path and child.get("information_library_root") != information_path:
            raise PortalDataError("flow_information_changed", "新的填写尝试信息库来源不符。", 409)
        task.setdefault("codex_handoff_history", []).append(
            {
                "action": "fresh_page_attempt_prepared",
                "at": time.time(),
                "previous": deepcopy(_binding(task)),
                "predecessor": deepcopy(predecessor),
                "successor_id": child["id"],
                "request_id": pending["request_id"],
            }
        )
        task.pop("codex_handoff_ref", None)
        task["codex_handoff_attempt"] = {
            "root": predecessor["root"],
            "task_id": child["id"],
            "request_id": pending["request_id"],
            "origin_task_revision": pending["origin_task_revision"],
            "application_id": child["application_id"],
            "job_url": child["job_url"],
            "filename": child["filename"],
            "file_sha256": child["file_sha256"],
            "material_key": pending["material_key"],
            "information_library_root": child.get("information_library_root"),
        }
        task.pop("codex_handoff_restart", None)
        flow._save(state)
        return deepcopy(task)


def _project_attempt(flow, task):
    view = deepcopy(task)
    attempt = task["codex_handoff_attempt"]
    try:
        if task["status"] == "cancelled":
            view["codex_handoff_attempt"] = {
                **attempt,
                "status": "unavailable",
                "reason": "flow_cancelled",
                "current_attempt": True,
            }
            return view
        _check_materials(flow, task)
        reader = CodexHandoffService(flow.applications, Path(attempt["root"]), existing_only=True)
        child = reader.existing_attempt(attempt["task_id"])
        _same_material_task(flow, task, child, attempt)
        if flow.information_library_root is not None:
            information_path = str(_information_root(flow, task))
            if child.get("information_library_root") != information_path:
                raise PortalDataError("flow_information_changed", "当前信息库来源已变化。", 409)
        view["codex_handoff_attempt"] = {
            **attempt,
            "status": child["status"],
            "task_revision": child["revision"],
            "prompt": child["prompt"],
            "reuse_field_count": len(child.get("reuse_context", {}).get("fields", [])),
            "current_attempt": True,
        }
        if child["status"] == "ready_for_review":
            view["codex_handoff_ref"] = read_existing(
                flow.applications,
                task,
                attempt["root"],
                child["id"],
                child["revision"],
            )
            view["status"] = "ready_for_review"
        elif child["status"] in {"needs_input", "needs_recheck"}:
            view["status"] = child["status"]
        elif child["status"] in {"submitted", "confirmed", "cancelled"}:
            view["status"] = "needs_recheck"
    except (PortalDataError, OSError, ValueError, KeyError, TypeError, helper.StoreError) as error:
        view["status"] = "needs_recheck"
        view["codex_handoff_attempt"] = {
            **attempt,
            "status": "needs_recheck",
            "reason": getattr(error, "code", "flow_handoff_unavailable"),
            "current_attempt": True,
        }
    return view


def project(flow, task, *, copy=True):
    """``copy=False`` returns a shallow view: only top-level keys are replaced."""
    from .application_flow import _material_pending

    view = deepcopy(task) if copy else dict(task)
    if task.get("codex_handoff_restart"):
        view["codex_handoff_restart"] = {
            **task["codex_handoff_restart"],
            "status": "preparing",
        }
        view.pop("codex_handoff_ref", None)
        if task["status"] != "cancelled":
            view["status"] = "needs_recheck"
        return view
    if task.get("codex_handoff_attempt"):
        return _project_attempt(flow, task)
    reference = task.get("codex_handoff_ref")
    if not reference:
        return view
    try:
        if (
            task.get("worker_ref")
            or task["status"] != "materials_ready"
            or _material_pending(task)
            or task.get("worker_preparation", {}).get("status") == "pending"
            or not task.get("materials_confirmed")
            or flow._group_guard_change(task)
            or any(stage["status"] != "complete" for stage in task["stages"].values())
        ):
            raise PortalDataError("flow_materials_required", "当前材料待核验。", 409)
        flow._fresh(task)
        flow.callbacks["verify_materials"](deepcopy(task))
        current = read_existing(
            flow.applications,
            task,
            reference["root"],
            reference["task_id"],
            reference["task_revision"],
        )
        if current != reference:
            raise PortalDataError("flow_handoff_changed", "既有上传引用已变化。", 409)
        view["codex_handoff_ref"] = current
        view["status"] = "ready_for_review"
    except (PortalDataError, OSError, ValueError, KeyError, TypeError, helper.StoreError) as error:
        view["status"] = "needs_recheck"
        view["codex_handoff_ref"] = {
            **reference,
            "status": "needs_recheck",
            "reason": getattr(error, "code", "flow_handoff_unavailable"),
        }
    return view
