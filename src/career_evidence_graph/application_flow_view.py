"""Read-only page projection of Flow, assembled by Runtime; it never starts work."""

from __future__ import annotations

from copy import deepcopy

from .career_portal_data import PortalDataError

_RUNNING = {"queued", "running"}


def preparation_activity(task):
    """Project the saved stage records so the page does not classify them itself."""
    if not task:
        return None
    statuses = {stage.get("status") for stage in task.get("stages", {}).values()}
    return {
        "task_id": task["id"],
        "task_revision": task["revision"],
        "status": "running"
        if statuses & _RUNNING
        else "needs_recheck"
        if "needs_recheck" in statuses
        else "idle",
    }


class FlowView:
    """Project the Flow page state; old keys keep their shape, new keys are additive.

    Exception (2026-11-05): in application mode ``tasks`` lists only the active task
    whole; the others carry ``TASK_BRIEF_KEYS``, all the page reads of them.
    """

    def __init__(self, runtime, *, analysis_injected=False, resume_injected=False):
        self.runtime = runtime
        self.analysis_injected, self.resume_injected = analysis_injected, resume_injected

    def state(self, task_id=None) -> dict:
        runtime = self.runtime
        token = runtime.source_read.set({})
        try:
            return self._project(task_id)
        finally:
            runtime.source_read.reset(token)

    def _project(self, task_id):
        runtime = self.runtime
        flow, worker, review = runtime.flow, runtime.worker, runtime.review
        flow_resumes, preparation_only = runtime.flow_resumes, runtime.preparation_only
        if flow is None:
            return {"enabled": False}
        from .application_flow import local_materials
        from .application_match import match_configuration

        # Progress belongs to the same saved task revision as the snapshot.
        with flow.applications.write_lock():
            state = flow.snapshot(task_id, brief_tasks=True)
            task = state["active_task"]
            try:
                progress = flow.progress(task["id"]) if task else None
            except (PortalDataError, KeyError, TypeError, ValueError):
                # The additive progress never hides the old projection.
                progress = None
        if progress is not None:
            progress.pop("task")
        state["mode"] = "preparation" if preparation_only else "application"
        cli_available = match_configuration()["executable_status"] == "available"
        state["capabilities"] = {
            "codex_cli": "available" if cli_available else "unavailable",
            "analysis": self.analysis_injected or cli_available,
            "resume": self.resume_injected or cli_available,
            "worker": worker is not None,
        }
        if preparation_only:
            from .application_preparation import preparation_checks

            state["runtime"] = deepcopy(runtime.identity)
            fresh = True
            materials_valid = True
            state["draft_integrity"] = None
            state["pdf_integrity"] = None
            state["review_snapshots"] = []
            state["prism"] = {
                "status": "not_bound",
                "message": "尚未绑定 LaTeX 项目；当前使用原草稿导出路径。",
            }
            if task:
                if (
                    task.get("origin") == "generated_latex"
                    and task.get("draft_id")
                    and not local_materials(task)
                ):
                    try:
                        state["group_review"] = flow_resumes.group_review_state(task["draft_id"])
                    except (PortalDataError, OSError, ValueError) as error:
                        state["group_review"] = {"status": "unavailable", "message": str(error)}
                if task.get("prism"):
                    try:
                        flow.verify_prism_source(task)
                        state["prism"] = {
                            "status": "current",
                            "message": "当前 LaTeX 源版本与绑定一致；审阅和导出使用此源。",
                        }
                    except PortalDataError as error:
                        state["prism"] = {
                            "status": "changed"
                            if error.code == "prism_source_changed"
                            else "unavailable",
                            "message": str(error),
                        }
                try:
                    flow.check_inputs_current(task)
                except (PortalDataError, OSError, ValueError):
                    fresh = False
                if (
                    review is not None
                    and fresh
                    and task.get("origin") == "existing_latex"
                    and task["stages"]["export"]["status"] == "needs_recheck"
                    and state["prism"]["status"] == "current"
                ):
                    try:
                        binding = {
                            key: task["prism"][key]
                            for key in ("project_root", "main", "files", "source_revision")
                        }
                        versions = review.state()["versions"] if review.binding() == binding else []
                        for metadata in versions:
                            version = review.version(metadata["id"])
                            if version.pop("binding") == binding:
                                state["review_snapshots"].append(version)
                    except (PortalDataError, OSError, ValueError, KeyError):
                        state["review_snapshots"] = []
                if task.get("resume_id"):
                    try:
                        flow.verify_materials(task)
                        state["pdf_integrity"] = {
                            "status": "valid",
                            "message": (
                                "PDF 字节与此前用户接受的材料一致；原决定已保留，真实申请继续暂停。"
                            )
                            if task.get("material_acceptance") and task.get("materials_confirmed")
                            else "PDF 字节与当前 LaTeX 技术导出一致；事实审核仍待完成。"
                            if task.get("origin") == "existing_latex"
                            else "PDF 字节与当前已审阅草稿的导出一致。",
                        }
                    except (PortalDataError, OSError, ValueError):
                        state["pdf_integrity"] = {
                            "status": "invalid",
                            "message": "当前 PDF 不能核验，请保留记录并明确重试导出。",
                        }
                if task.get("draft_id"):
                    try:
                        flow.verify_draft(task)
                        state["draft_integrity"] = {
                            "status": "valid",
                            "message": "草稿字节与本任务版本一致；内容仍需审阅。",
                        }
                    except (PortalDataError, OSError, ValueError):
                        materials_valid = False
                        state["draft_integrity"] = {
                            "status": "invalid",
                            "message": "当前草稿不能核验，请保留记录后明确重新生成。",
                        }
            state["preparation"] = {
                "checks": preparation_checks(
                    sources=(
                        {
                            "items": next(
                                (
                                    row.get("result", {}).get("available_review_sources", [])
                                    for row in reversed(task.get("artifacts", []))
                                    if row.get("result", {}).get("id") == task.get("draft_id")
                                ),
                                [],
                            ),
                            "profile": {},
                            "coverage": {"unavailable_documents": []},
                        }
                        if task and flow.fixed_writing_inputs(task) is not None
                        else runtime.flow_sources()
                    ),
                    configuration=match_configuration(),
                    intake=runtime.intake,
                    resumes=flow_resumes,
                    task=task,
                    fresh=fresh,
                    materials_valid=materials_valid,
                ),
            }
            if state["pdf_integrity"] and state["pdf_integrity"]["status"] == "invalid":
                state["preparation"]["checks"]["pdf"] = state["pdf_integrity"]
        unavailable = runtime.worker_unavailable
        state["worker"] = {
            "enabled": False,
            **({"error": unavailable.code, "message": str(unavailable)} if unavailable else {}),
        }
        if worker and task and task.get("worker_ref"):
            try:
                flow.check_available()
                observed = worker.snapshot()
                flow.callbacks["worker_reference"](task)
                state["worker"] = observed | {
                    "jobs": [
                        j for j in observed["jobs"] if j["application_id"] == task["application_id"]
                    ],
                    "input_items": [
                        item
                        | {"jobs": [j for j in item["jobs"] if j["id"] == task["application_id"]]}
                        for item in observed.get("input_items", [])
                        if any(j["id"] == task["application_id"] for j in item["jobs"])
                    ],
                }
            except (PortalDataError, OSError, ValueError) as error:
                state["worker"] = {
                    "enabled": False,
                    "error": error.code
                    if isinstance(error, PortalDataError)
                    else "flow_worker_unavailable",
                    "message": "填写状态暂不能核验；保留原任务和页面。",
                }
        state["progress"] = progress
        state["preparation_activity"] = preparation_activity(task)
        return state
