"""Attach known completed experience materials without replaying generation or export."""

from __future__ import annotations

import time
from copy import deepcopy

from .application_experience_latex import FEEDBACK_KEY
from .career_portal_data import PortalDataError
from .validation.hashing import record_digest as digest


def _invalid():
    return PortalDataError(
        "flow_existing_materials_mismatch",
        "已有终稿与原岗位或人工底稿不符，请保留记录并核验。",
        409,
    )


def attach(flow, task_id, task_revision, generation_id, export_id):
    """Bind checked existing files in one Flow save, preserving previous versions."""
    with flow.applications.write_lock():
        flow._writable()
        state = flow._load()
        task = flow._task(state, task_id)
        existing = next(
            (
                row
                for row in task.get("material_reconnections", [])
                if row["generation_id"] == generation_id and row["export_id"] == export_id
            ),
            None,
        )
        if task["revision"] != task_revision and (
            not existing or existing["previous_revision"] != task_revision
        ):
            raise PortalDataError("conflict", "任务已变化，请重新读取。", 409)
        flow._batch_guard_change(state, task)
        batch = state.get("preparation_batch") or {}
        if (
            not flow.preparation_only
            or batch.get("control") in {"running", "needs_recheck"}
            or task["status"] in {"cancelled", "needs_recheck"}
            or task.get("worker_ref")
            or (task.get("codex_handoff_ref") and not existing)
            or task.get("material_binding_error")
            or task.get("material_update", {}).get("status") not in {None, "complete"}
            or task.get("worker_preparation", {}).get("status") == "pending"
            or task["stages"]["analysis"]["status"] != "complete"
            or any(
                stage["status"] in {"queued", "running", "needs_recheck"}
                for stage in task["stages"].values()
            )
        ):
            raise PortalDataError(
                "flow_existing_materials_blocked", "先核验现有操作，不能替换原任务材料。", 409
            )
        flow._fresh(task)
        callback = flow.callbacks.get("existing_experience_materials")
        if callback is None:
            raise PortalDataError("flow_stage_unavailable", "已有材料核验服务尚未连接。", 409)
        checked = callback(deepcopy(task), generation_id, export_id)
        draft, exported = checked["draft"], checked["export"]
        flow._fresh(task)
        if existing:
            if (
                task.get("draft_id") != draft["id"]
                or task.get("draft_sha256") != draft["draft_sha256"]
                or task.get("resume_id") != exported["id"]
                or task.get("resume_sha256") != exported["pdf_sha256"]
                or task.get("inputs") != draft["task_inputs"]
                or task.get("status") != "materials_ready"
            ):
                raise _invalid()
            return deepcopy(task)
        previous = deepcopy(task)
        task.update(
            inputs=deepcopy(draft["task_inputs"]),
            input_epoch=task.get("input_epoch", 0) + (task["inputs"] != draft["task_inputs"]),
            origin="generated_latex",
            automatic_materials=True,
            factual_review="pending",
            draft_id=draft["id"],
            draft_sha256=draft["draft_sha256"],
            draft_review=None,
            source_checkpoint=deepcopy(draft["source_checkpoint"]),
            base_checkpoint=deepcopy(draft["base_checkpoint"]),
            prism={k: v for k, v in draft["source_checkpoint"].items() if k != "archive_sha256"}
            | {"draft_id": draft["id"], "draft_sha256": draft["draft_sha256"]},
        )
        task.pop("experience_handoff", None)
        task.pop("pdf_reuse", None)
        task.pop("material_acceptance", None)
        task["stages"]["resume"] = {
            "status": "complete",
            "artifact_id": draft["id"],
            "latex_base": deepcopy(draft["base_checkpoint"]),
        }
        task["stages"]["export"] = {
            "status": "complete",
            "attempt_id": exported["id"],
            "artifact_id": exported["id"],
            "configuration_revision": exported["export_configuration_revision"],
        }
        task["artifacts"].extend(
            {"stage": stage, "adopted": True, "inputs": deepcopy(task["inputs"]), "result": result}
            for stage, result in (("resume", draft), ("export", exported))
        )
        flow._adopt_export(task, exported)
        receipt = {
            "generation_id": generation_id,
            "export_id": export_id,
            "previous_revision": previous["revision"],
            "previous": {
                k: v
                for k, v in previous.items()
                if k not in {"artifacts", "revision", "material_reconnections"}
            },
            "input_revision": digest(task["inputs"]),
            FEEDBACK_KEY: task["inputs"].get(FEEDBACK_KEY),
            "candidate_sha256": checked["generation"]["review"]["candidate_sha256"],
            "lineage": checked.get("lineage", "retained_draft"),
            "at": time.time(),
        }
        task.setdefault("material_reconnections", []).append(receipt)
        # The callback has already verified both immutable artifacts and current
        # editor/source bytes. The binding is technical, with no human acceptance.
        task["material_binding"] = {
            "actor": "system",
            "human_reviewed": False,
            "scope": "current_pdf_materials",
            "resume_id": task["resume_id"],
            "pdf_sha256": task["resume_sha256"],
            "input_revision": digest(task["inputs"]),
            "draft_id": task["draft_id"],
            "draft_sha256": task["draft_sha256"],
            "at": time.time(),
        }
        task.update(status="materials_ready", materials_confirmed=True)
        flow._batch_after(state, task)
        flow._save(state)
        return deepcopy(task)
