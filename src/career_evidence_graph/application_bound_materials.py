"""A paused original-page transaction for changing its bound resume version."""

from __future__ import annotations

import hashlib
import re
import time
from copy import deepcopy
from pathlib import Path

from .application_worker import (
    assistance_stop_pending,
    manual_submission_unresolved,
)
from .career_portal_data import PortalDataError
from .validation.hashing import record_digest as digest

MATERIAL_KEYS = (
    "inputs",
    "analysis_id",
    "job_binding",
    "draft_id",
    "draft_sha256",
    "resume_id",
    "resume_sha256",
    "source_checkpoint",
    "prism",
    "base_checkpoint",
    "latex_base",
    "manual_source",
    "manual_latex_base",
    "material_binding",
    "send_approval",
    "worker_ref",
)


def failure(
    code="bound_material_update_changed", message="原页材料更新状态已变化，请保留原记录核验。"
):
    return PortalDataError(code, message, 409)


def read_commit_journal(root, update_id):
    """Read the one retained v1 journal; callers cannot supply another file path."""
    from ._vendor import job_apply_store as helper

    if not isinstance(update_id, str) or re.fullmatch(r"[a-f0-9]{32}", update_id) is None:
        raise failure("bound_material_journal_invalid")
    root = Path(root)
    path = root / "material-updates" / (update_id + ".json")
    if root.is_symlink() or path.parent.is_symlink() or path.is_symlink():
        raise failure("bound_material_journal_invalid")
    journal = helper.read_json_object(path, "material update journal")
    if (
        type(journal.get("schemaVersion")) is not int
        or journal.get("schemaVersion") != 1
        or journal.get("id") != update_id
        or journal.get("status") not in {"committing", "bound"}
        or journal.get("revision") != digest({k: v for k, v in journal.items() if k != "revision"})
        or any(
            not isinstance(journal.get(key), dict)
            for key in ("old", "new", "old_job", "new_job", "old_receipt", "new_receipt")
        )
        or any(
            not isinstance(journal.get(key), str) or not journal[key]
            for key in ("task_id", "application_id", "batch_id")
        )
        or journal["application_id"] != journal["new"].get("application_id")
        or journal["task_id"] != journal["new"].get("id")
    ):
        raise failure("bound_material_journal_invalid")
    return journal


def binding(task):
    value = {key: deepcopy(task.get(key)) for key in MATERIAL_KEYS}
    if isinstance(value.get("worker_ref"), dict):
        value["worker_ref"] = {key: value["worker_ref"].get(key) for key in ("batch_id", "job_id")}
    return value


def current_inputs(flow, task):
    return flow.material_update_inputs(task)


def paused_job(flow, task):
    """Legacy coordinator view; Worker owns its read-only permission checks."""
    from .application_worker import checked_material_preparation_job

    try:
        flow.check_available()
    except PortalDataError as error:
        raise failure(
            "bound_material_pause_required", "请保持当前原岗位暂停并先核验未知动作。"
        ) from error
    callback = flow.callbacks.get("bound_worker_state")
    state = callback() if callback else {}
    job = checked_material_preparation_job(
        state,
        task["application_id"],
        expected_batch_id=(task.get("worker_ref") or {}).get("batch_id"),
        expected_task_id=task.get("id"),
    )
    return state, job


def begin(flow, task_id, request_id):
    return flow.begin_material_update(task_id, request_id)


def inspect_request(pipeline, state, task):
    flow, worker = pipeline.flow, pipeline.worker
    update = task["material_update"]
    with flow.applications.write_lock():
        current, job = paused_job(flow, task)
        old_job = deepcopy(job)
        if not job.get("page_open"):
            raise failure("page_lost")
        mirror = job.get("material_update") or {}
        if mirror.get("id") == update["id"]:
            return
        if mirror:
            job.setdefault("material_update_history", []).append(deepcopy(mirror))
        job["material_update"] = {
            "id": update["id"],
            "request_id": update["request_id"],
            "status": "inspect_pending",
            "old_sha256": job["file_sha256"],
            "old_binding": deepcopy(job["single_binding"]),
            "old_file_path": job["file_path"],
            "requested_at": time.time(),
        }
        job["material_update"]["old_job_revision"] = digest(old_job)
        current["commands"].append(
            {
                "action": "inspect-material-update",
                "id": job["application_id"],
                "request_id": update["request_id"],
                "material_update_id": update["id"],
            }
        )
        worker.store.save(current)


def _commit(pipeline, state, task, worker_state, job):
    """Journal all three exact local bindings before the first local adoption."""
    from ._vendor import job_apply_store as helper
    from .application_single_binding import valid_send_approval
    from .application_worker import assistance_reference

    flow = pipeline.flow
    update = task["material_update"]
    if update["old"].get("send_approval", {}).get(
        "verified_by"
    ) != "workflow_policy" or not valid_send_approval(update["old"], flow.root):
        raise failure("bound_material_authorization_required", "本次材料更新没有当前自动流程授权。")
    if not pipeline._owner or pipeline._closed.is_set() or state.get("control") != "running":
        raise failure("bound_material_update_paused")
    if (
        state.get("active_task_id") != task["id"]
        or state.get("worker_batch_id") != worker_state["batch_id"]
        or update["inputs"] != current_inputs(flow, task)
        or job.get("intent")
        or job["material_update"].get("status") != "page_verified"
    ):
        raise failure()
    candidate = deepcopy(update["candidate"])
    flow.check_inputs_current(candidate)
    flow.callbacks["verify_materials"](candidate)
    from .application_explanations import qualification_for

    if qualification_for(
        candidate,
        flow.applications.get_application(task["application_id"]),
        flow.information_provider(),
    )["status"] not in {"supported", "not_specified", "needs_input"}:
        raise failure("flow_qualification_required")
    receipt = deepcopy(state["transmission_authorization"])
    receipt.update(
        inputs=deepcopy(candidate["inputs"]),
        resume_id=candidate["resume_id"],
        resume_sha256=candidate["resume_sha256"],
    )
    candidate["send_approval_history"] = [
        *task.get("send_approval_history", []),
        deepcopy(task["send_approval"]),
    ]
    candidate["send_approval"] = deepcopy(task["send_approval"]) | {
        "inputs": deepcopy(candidate["inputs"]),
        "resume_id": candidate["resume_id"],
        "resume_sha256": candidate["resume_sha256"],
        "authorization": receipt,
        "material_update_id": update["id"],
        "at": time.time(),
    }
    candidate.update(
        status="needs_recheck",
        worker_ref=binding(task)["worker_ref"],
        material_update_history=deepcopy(task.get("material_update_history", [])),
    )
    candidate["material_update"] = deepcopy(update) | {"status": "committing"}
    candidate["material_update"].pop("candidate", None)
    candidate["material_update"]["page_receipt"] = deepcopy(job["material_update"]["page_receipt"])
    new_job = {
        "single_binding": deepcopy(job["single_binding"])
        | {key: deepcopy(candidate[key]) for key in ("inputs", "resume_id", "resume_sha256")},
        "file_path": str(flow.root / "resumes" / candidate["resume_id"] / "resume.pdf"),
        "file_sha256": candidate["resume_sha256"],
        "filename": job["filename"],
        "material_update": deepcopy(job["material_update"])
        | {"status": "bound", "new_sha256": candidate["resume_sha256"]},
    }
    raw = Path(new_job["file_path"]).read_bytes()
    if (
        hashlib.sha256(raw).hexdigest() != new_job["file_sha256"]
        or not raw.startswith(b"%PDF-")
        or len(raw) > 700000
    ):
        raise failure("flow_materials_changed")
    journal = {
        "schemaVersion": 1,
        "id": update["id"],
        "status": "committing",
        "task_id": task["id"],
        "batch_id": worker_state["batch_id"],
        "application_id": job["application_id"],
        "execution_claim": assistance_reference(job["assistance"])
        if job.get("assistance")
        else None,
        "worker_controller": worker_state.get("controller"),
        "worker_resume_serial": worker_state.get("resume_serial", 0),
        "old": binding(task),
        "new": candidate,
        "old_job": {key: deepcopy(job.get(key)) for key in new_job},
        "new_job": new_job,
        "old_receipt": deepcopy(state["transmission_authorization"]),
        "new_receipt": receipt,
    }
    path = flow.root / "material-updates" / (update["id"] + ".json")
    path.parent.mkdir(mode=0o700, exist_ok=True)
    helper.atomic_write_json(path, journal | {"revision": digest(journal)})
    recover_commit(pipeline, state, path)


def recover_pending_commit(pipeline, state, task, *, request_id):
    """Resume only this Continue's existing local journal before strict reads."""
    update = task.get("material_update") or {}
    if (
        not update
        or state.get("material_update_id") != update.get("id")
        or update.get("status") not in {"awaiting_page", "committing"}
    ):
        return False
    path = pipeline.flow.root / "material-updates" / (update["id"] + ".json")
    if not path.exists():
        return False
    # The public Continue holds the Pipeline and application locks. Recovery
    # converges local records only; all original owner/material checks still run.
    resumed = pipeline.resume_material_commit(update["id"], request_id)
    state.clear()
    state.update(resumed)
    recover_commit(pipeline, state, path, resume_request_id=request_id)
    return True


def recover_commit(pipeline, state, path, *, resume_request_id=None):
    """Converge only exact old/new local states; never dispatch a browser action."""
    from ._vendor import job_apply_store as helper

    flow, worker = pipeline.flow, pipeline.worker
    path = Path(path)
    if path != flow.root / "material-updates" / (path.stem + ".json"):
        raise failure("bound_material_journal_invalid")
    journal = read_commit_journal(flow.root, path.stem)
    if (
        journal.get("schemaVersion") != 1
        or journal.get("status") not in {"committing", "bound"}
        or journal.get("revision") != digest({k: v for k, v in journal.items() if k != "revision"})
        or journal.get("task_id") != state.get("active_task_id")
        or journal.get("application_id") != journal["new"].get("application_id")
    ):
        raise failure("bound_material_journal_invalid")
    task = flow.witness(journal["task_id"])[1]
    current = worker.store.load()
    job = next(row for row in current["jobs"] if row["application_id"] == journal["application_id"])
    if (
        state.get("control") != "running"
        or current.get("control") != "paused"
        or current.get("controller") != state.get("controller")
        or current.get("batch_id") != journal["batch_id"]
        or current.get("current_job_id") != job["application_id"]
        or job.get("intent")
        or job.get("status") == "cancelled"
        or task.get("status") == "cancelled"
        or not task.get("materials_confirmed")
        or job.get("manual_submission")
        or manual_submission_unresolved(job)
        or assistance_stop_pending(job)
        or task.get("material_update", {}).get("id") != journal["id"]
        or job.get("material_update", {}).get("id") != journal["id"]
        or binding(task) not in (journal["old"], binding(journal["new"]))
        or {key: job.get(key) for key in journal["new_job"]}
        not in (journal["old_job"], journal["new_job"])
        or state.get("transmission_authorization")
        not in (journal["old_receipt"], journal["new_receipt"])
    ):
        raise failure("bound_material_journal_conflict")
    from .application_execution import automated_owner, require_execution
    from .application_worker import worker_lock_is_held

    receipt = journal["new_job"]["material_update"]["page_receipt"]
    if (
        receipt.get("run_id") != (current.get("runtime") or {}).get("id")
        or receipt.get("page_id") != (job.get("page_observation") or {}).get("page_id")
        or not worker_lock_is_held(worker.store.root, receipt.get("worker_lock"))
    ):
        raise failure("bound_material_owner_unknown")
    require_execution(
        flow.applications,
        job["application_id"],
        automated_owner(worker.store.root, current["batch_id"], job["application_id"]),
        "automated",
    )
    flow.validate_material_candidate(journal["task_id"], journal["id"])
    worker.validate_material_update(
        journal["application_id"], journal["id"], expected_batch_id=journal["batch_id"]
    )
    pipeline.validate_material_authorization(journal["id"], resume_request_id=resume_request_id)
    flow.commit_material_candidate(journal["task_id"], journal["id"])
    worker.commit_material_update(
        journal["application_id"], journal["id"], expected_batch_id=journal["batch_id"]
    )
    adopted = pipeline.commit_material_authorization(
        journal["id"], resume_request_id=resume_request_id
    )
    state.clear()
    state.update(adopted)
    # The ordinary validator is the final gate; no generic old-hash exception.
    journal["status"] = "bound"
    journal.pop("revision", None)
    helper.atomic_write_json(path, journal | {"revision": digest(journal)})
    flow.commit_material_candidate(journal["task_id"], journal["id"], bound=True)
    worker.verify_material_update(
        journal["application_id"], journal["id"], expected_batch_id=journal["batch_id"]
    )


def advance(pipeline, state):
    """Advance one bounded local phase of the original Continue request."""
    flow, worker = pipeline.flow, pipeline.worker
    with flow.applications.write_lock():
        task = flow.task_snapshot(state["active_task_id"])
        update = task.get("material_update") or {}
        if not update or state.get("material_update_id") != update.get("id"):
            return False
        path = flow.root / "material-updates" / (update["id"] + ".json")
        if path.exists() and update["status"] in {"awaiting_page", "committing"}:
            recover_commit(pipeline, state, path)
            return True
        if update["status"] == "preparing":
            return True
        if update["status"] == "needs_recheck":
            raise failure(update.get("error_code", "bound_material_update_unknown"))
        if update["status"] == "awaiting_page":
            inspect_request(pipeline, state, task)
            current, job = paused_job(flow, task)
            mirror = job.get("material_update") or {}
            if mirror.get("status") == "inspect_pending":
                import math

                requested = mirror.get("requested_at")
                if (
                    type(requested) not in {int, float}
                    or not math.isfinite(requested)
                    or not 0 <= time.time() - requested <= 15
                ):
                    raise failure("bound_material_inspection_expired")
                if not current.get("worker_pid") or not current.get("runtime"):
                    raise failure("bound_material_owner_unknown")
                return True
            if mirror.get("status") != "page_verified":
                raise failure(mirror.get("error_code", "bound_material_page_unknown"))
            _commit(pipeline, state, task, current, job)
            return True
        if update["status"] == "bound":
            current = worker.store.load()
            job = next(
                row for row in current["jobs"] if row["application_id"] == task["application_id"]
            )
            progress = worker.material_update_progress(
                task["application_id"], update["id"], expected_batch_id=current["batch_id"]
            )
            if progress["status"] == "complete":
                flow.complete_material_update(task["id"], update["id"], execution=progress)
                completed = pipeline.complete_material_update(update["id"])
                state.clear()
                state.update(completed)
                return False
            continuation_id = state.get("material_update_continue_request_id", update["request_id"])
            if (
                not job.get("continuation")
                or job["continuation"].get("request_id") != continuation_id
            ):
                worker.request(
                    "continue-current",
                    {
                        "application_id": job["application_id"],
                        "request_id": continuation_id,
                        "controller": state["controller"],
                    },
                )
            return False
        return False


def document_token(page):
    return page.evaluate("""() => {
      if (!window.__tomorrowstarMaterialDocument) {
        window.__tomorrowstarMaterialDocument = crypto.randomUUID();
      }
      return window.__tomorrowstarMaterialDocument;
    }""")


def attachment_snapshot(runner, page, job, observed):
    """Use bytes or an exact previously verified remote attachment identity."""
    files = [deepcopy(field) for field in observed["fields"] if field["type"] == "file"]
    resumes = [field for field in files if field.get("resume") or field["id"] == "resume"]
    if len(resumes) != 1 or resumes[0].get("multiple"):
        raise failure("bound_resume_control_changed")
    resume = resumes[0]
    path = resume.get("draft_path", "")
    draft = runner.drafts.get(page)
    remote = None
    if draft:
        evidence = draft.files.get(path, {})
        actual = draft.fields.get(path, {}).get("fieldValue")
        if actual:
            if (
                not isinstance(actual, dict)
                or actual.get("id") != evidence.get("attachment_id")
                or evidence.get("sha256") != job["file_sha256"]
                or evidence.get("filename") != job["filename"]
                or actual.get("filename") != job["filename"]
            ):
                raise failure("bound_resume_identity_unknown")
            remote = {"attachment_id": actual["id"], "sha256": evidence["sha256"]}
    workable = runner.workable.get(page)
    if workable and not workable.handle:
        container = page.locator('[data-ui="resume"]')
        if container.count() != 1:
            raise failure("bound_resume_identity_unknown")
        actual = container.evaluate("""element => ({
            names:[...element.querySelectorAll('[data-id="filename"]')]
              .filter(node=>node.getClientRects().length).map(node=>node.textContent.trim()).filter(Boolean),
            links:[...element.querySelectorAll('[data-action="view"]')]
              .filter(node=>node.getClientRects().length).map(node=>node.getAttribute('href'))})""")
        if actual["names"] or actual["links"]:
            raise failure("bound_resume_identity_unknown")
    if workable and workable.handle:
        if workable.attachment(page) is None and not workable.remote_sha256:
            raise failure("bound_resume_identity_unknown")
        if workable.remote_sha256 != job["file_sha256"]:
            raise failure("bound_resume_identity_unknown")
        remote = {"handle": deepcopy(workable.handle), "sha256": workable.remote_sha256}
    local_sha = resume.get("file_sha256")
    upload = observed.get("upload", {})
    if not runner.live and upload.get("state") == "complete":
        remote = {"sha256": upload.get("sha256"), "filename": upload.get("name")}
    selected = bool(resume.get("filename") or local_sha or remote)
    if selected and (
        local_sha
        and local_sha != job["file_sha256"]
        or not local_sha
        and not remote
        or remote
        and remote.get("sha256") != job["file_sha256"]
    ):
        raise failure("bound_resume_identity_unknown")
    if selected and not runner.recovered_upload(job):
        raise failure("bound_resume_upload_unbound")
    if not selected and runner.recovered_upload(job):
        raise failure("bound_resume_not_visible")
    return {
        "resume": {
            key: resume.get(key)
            for key in ("id", "draft_path", "filename", "file_sha256", "multiple")
        },
        "remote": remote,
        "empty": not selected,
        "others": [
            {
                key: field.get(key)
                for key in ("id", "draft_path", "filename", "file_sha256", "multiple")
            }
            for field in files
            if field["id"] != resume["id"]
        ],
    }


def inspect_runner(runner, state, job, page, command):
    import os

    from .application_execution import automated_owner, require_execution
    from .application_single_binding import _read
    from .application_worker import worker_lock_is_held

    update = (job or {}).get("material_update") or {}
    if (
        update.get("id") != command.get("material_update_id")
        or update.get("status") != "inspect_pending"
    ):
        return
    descriptor = getattr(runner.store, "worker_lock_descriptor", None)
    stat = os.fstat(descriptor) if descriptor is not None else None
    lock = {"device": stat.st_dev, "inode": stat.st_ino} if stat else None
    if (
        state.get("control") != "paused"
        or state.get("current_job_id") != job["application_id"]
        or state.get("worker_pid") != os.getpid()
        or not worker_lock_is_held(runner.store.root, lock)
        or (state.get("runtime") or {}).get("id") != runner.run_id
        or page is None
        or page.is_closed()
        or page.context is not runner.context
        or runner.page_ids.get(page) != (job.get("page_observation") or {}).get("page_id")
        or runner.shared_fault
        or runner.storage_stopped
        or runner.store.stop_reason()
        or page in runner.page_faults
        or page in runner.blocked_pages
        or job.get("intent")
        or manual_submission_unresolved(
            {**job, "observations": [*job["observations"], *runner.transports]}
        )
    ):
        raise failure("bound_material_owner_unknown")
    require_execution(
        runner.store.applications,
        job["application_id"],
        automated_owner(runner.store.root, state["batch_id"], job["application_id"]),
        "automated",
    )
    saved = _read(runner.store.single_flow_root / "flow.json")
    task = next(row for row in saved["tasks"] if row["id"] == job["single_binding"]["task_id"])
    transaction = task.get("material_update") or {}
    if (
        task.get("revision") != digest({k: v for k, v in task.items() if k != "revision"})
        or transaction.get("id") != update["id"]
        or transaction.get("status") != "awaiting_page"
        or binding(task) != binding(transaction["old"])
        or job["single_binding"] != update["old_binding"]
        or job["file_sha256"] != update["old_sha256"]
        or hashlib.sha256(Path(job["file_path"]).read_bytes()).hexdigest() != update["old_sha256"]
    ):
        raise failure()
    refresh_original_attachments(runner, page, job)
    observed = runner.observe(page, job)
    receipt = {
        "run_id": runner.run_id,
        "page_id": runner.page_ids[page],
        "url": page.url,
        "document_token": document_token(page),
        "worker_lock": lock,
        "attachments": attachment_snapshot(runner, page, job, observed),
        "observed": observed,
        "verified_at": time.time(),
    }
    from .application_worker import precision_preparation_pending

    if precision_preparation_pending(job) and receipt["attachments"]["empty"]:
        if any(
            intent.get("action") == "upload" and not intent.get("material_id")
            for intent in runner.verified_intents(job)
        ):
            raise failure("bound_resume_not_visible")
        update["upload_mode"] = "first_upload"
    update.update(status="page_verified", page_receipt=receipt)


def verify_original_page(runner, page, job, *, attachments=True, expected_intent=None):
    update = job.get("material_update") or {}
    if update.get("status") != "bound":
        return
    receipt = update["page_receipt"]
    if (
        page.url != receipt["url"]
        or runner.run_id != receipt["run_id"]
        or runner.page_ids.get(page) != receipt["page_id"]
        or document_token(page) != receipt["document_token"]
    ):
        raise failure("bound_material_document_changed")
    if attachments:
        current_upload = any(
            intent.get("material_update_id") == update["id"]
            and intent.get("action") == "upload"
            and intent.get("sha256") == job["file_sha256"]
            for intent in runner.verified_intents(job)
        )
        if update.get("upload_mode") == "first_upload":
            observed = runner.observe(page, job)
            current = attachment_snapshot(runner, page, job, observed)
            old = receipt["attachments"]
            if (
                current["resume"]["id"] != old["resume"]["id"]
                or current["resume"]["draft_path"] != old["resume"]["draft_path"]
            ):
                raise failure("bound_material_attachment_changed")
            expected_others = {item["id"]: item for item in old["others"]}
            if set(expected_others) != {item["id"] for item in current["others"]}:
                raise failure("bound_material_attachment_changed")
            for actual in current["others"]:
                if actual == expected_others[actual["id"]]:
                    continue
                question = next(
                    field for field in observed["fields"] if field["id"] == actual["id"]
                )
                material = runner.store.field_material(question, job)
                if (
                    not material
                    or actual.get("file_sha256") != material.get("sha256")
                    or actual.get("filename") != material.get("filename")
                    or not any(
                        intent.get("action") == "upload"
                        and intent.get("material_id") == material["id"]
                        and intent.get("field_id") == actual["id"]
                        and intent.get("sha256") == material["sha256"]
                        for intent in runner.verified_intents(job)
                    )
                ):
                    raise failure("bound_material_attachment_changed")
            if current_upload:
                if current["empty"]:
                    raise failure("bound_material_attachment_changed")
                return True
            if (
                not current["empty"]
                or current["resume"] != old["resume"]
                or current["remote"] != old["remote"]
            ):
                raise failure("bound_material_attachment_changed")
            return
        if update["old_sha256"] == job["file_sha256"] or current_upload:
            refresh_original_attachments(runner, page, job)
            current = attachment_snapshot(runner, page, job, runner.observe(page, job))
            old = receipt["attachments"]
            if (
                current["empty"]
                or current["resume"]["id"] != old["resume"]["id"]
                or current["resume"]["draft_path"] != old["resume"]["draft_path"]
                or current["others"] != old["others"]
            ):
                raise failure("bound_material_attachment_changed")
            return True
        old_job = deepcopy(job) | {
            "file_sha256": update["old_sha256"],
            "file_path": update["old_file_path"],
        }
        refresh_original_attachments(runner, page, old_job, expected_intent=expected_intent)
        if (
            attachment_snapshot(runner, page, old_job, runner.observe(page, old_job))
            != receipt["attachments"]
        ):
            raise failure("bound_material_attachment_changed")


def refreshed_contact_fields(runner, job):
    """Release only a system field still equal to its archived old canonical answer."""
    from .application_information import CONTACT_FACTS, fact_for, read_information_history
    from .application_single_binding import _read

    for field_id, field in list(job.get("manual_fields", {}).items()):
        if fact_for(field["question"]) not in CONTACT_FACTS:
            continue
        fresh = runner.store.resolve(field, job, runner.temporary)
        if not fresh or fresh[0] == field.get("value"):
            continue
        previous = next(
            (
                row.get("intent", {}).get("answer_ref")
                for row in reversed(job["observations"])
                if row.get("action") == "fill"
                and row.get("verified")
                and row.get("field_id") == field_id
            ),
            None,
        )
        if previous and previous.get("key"):
            for event in read_information_history(
                runner.store.answers_for(job).root, key=previous["key"]
            ):
                if event.get("before_revision") != previous.get("revision"):
                    continue
                record = _read(runner.store.answers_for(job).root / event["backup"])["answers"].get(
                    previous["key"]
                )
                if (
                    record
                    and digest(record) == previous["revision"]
                    and record.get("value") == field.get("value")
                ):
                    job["manual_fields"].pop(field_id)
                    break
        if field_id in job["manual_fields"]:
            raise failure(
                "bound_contact_manual_conflict",
                "原页人工联系方式与更正值不同，请保留当前字段并核对。",
            )


def refresh_original_attachments(runner, page, job, *, expected_intent=None):
    """Read the old remote attachment again; cached success cannot prove identity."""
    draft = runner.drafts.get(page)
    if draft:
        expected = {path: deepcopy(value) for path, value in draft.files.items()}
        draft.job = job
        draft.refresh(page, runner.effective_action_results(job))
        if any(
            draft.files.get(path, {}).get("attachment_id") != value.get("attachment_id")
            for path, value in expected.items()
        ):
            raise failure("bound_material_attachment_changed")
    workable = runner.workable.get(page)
    if workable and workable.handle:
        from .application_worker import unresolved_write_failure

        state = runner.store.load()
        current = next(
            row for row in state["jobs"] if row["application_id"] == job["application_id"]
        )
        update = current.get("material_update") or {}
        if (
            current.get("intent") != expected_intent
            or manual_submission_unresolved(
                {**current, "observations": [*current["observations"], *runner.transports]}
            )
            or any(unresolved_write_failure(row, current, state) for row in runner.transports)
            or expected_intent is not None
            and (
                update.get("status") != "bound"
                or expected_intent.get("action") != "upload"
                or expected_intent.get("kind") != "resume"
                or expected_intent.get("material_update_id") != update.get("id")
                or expected_intent.get("sha256") != current["file_sha256"]
                or expected_intent.get("replaces_sha256") != update.get("old_sha256")
                or expected_intent.get("run_id") != runner.run_id
                or expected_intent.get("page_id") != runner.page_ids.get(page)
                or not runner.permitted(state, page)
                or current["status"] != "filling"
                or current["handed_off"]
            )
        ):
            raise failure("bound_material_owner_unknown")
        previous_job = workable.job
        workable.job = job
        workable.sent.discard("workable_readback")
        workable.remote_sha256 = ""
        runner.bound_material_read = {
            "page": page,
            "application_id": job["application_id"],
            "material_update_id": job["material_update"]["id"],
            "sha256": job["file_sha256"],
            "intent": deepcopy(expected_intent),
        }
        try:
            workable.readback(page)
        finally:
            runner.bound_material_read = None
            workable.job = previous_job
