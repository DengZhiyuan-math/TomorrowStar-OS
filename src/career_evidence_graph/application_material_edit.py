"""Checked local reads and independent human versions of prepared supplemental drafts."""

import hashlib
from pathlib import Path

from .career_portal_data import PortalDataError


def _edit_letter_content(worker, old, text, request_id):
    """Map the exact fixed text regions and change only the semantic body."""
    from .application_cover_letter import edit_delivered_letter
    from .application_materials import read_cover_letter_template

    template = read_cover_letter_template(worker.store, old["source_binding"]["application"])
    return edit_delivered_letter(old, text, template, request_id=request_id)


def read_material_pdf(flow, worker, binding, task_id, material_id):
    """Read the current bound material by ID; browser input never selects a path."""
    if flow.preparation_only or worker is None:
        raise PortalDataError("flow_worker_unavailable", "当前任务没有附稿执行记录。", 409)
    with flow.applications.write_lock():
        task = flow.witness(task_id)[1]
        state = worker.store.load()
        binding(state, task)
        job = next(row for row in state["jobs"] if row["application_id"] == task["application_id"])
        found = [
            item
            for item in [*job.get("materials", []), *job.get("material_history", [])]
            if item.get("id") == material_id
        ]
        if len(found) != 1 or not found[0].get("file_path"):
            raise PortalDataError("material_not_found", "找不到此岗位的附稿 PDF。", 404)
        material = worker.store.verify_material(found[0], job)
        raw = Path(material["file_path"]).read_bytes()
        if hashlib.sha256(raw).hexdigest() != material["sha256"]:
            raise PortalDataError("material_changed", "附稿 PDF 已变化，请保留原版本。", 409)
        return raw


def _edit_target(flow, worker, binding, task_id, revision=None):
    from .application_worker import (
        assistance_stop_pending,
        manual_submission_unresolved,
        unresolved_write_failure,
    )

    if flow.preparation_only or worker is None or worker._backend_closed:
        raise PortalDataError("flow_worker_unavailable", "附稿编辑暂不可用，请保留原稿。", 409)
    task = flow.writable_task(task_id, revision)
    state = worker.store.load()
    binding(state, task)
    job = next(row for row in state["jobs"] if row["application_id"] == task["application_id"])
    precision = job.get("precision_preparation") or {}
    if (
        task.get("status") == "cancelled"
        or worker.store.stop_reason()
        or state.get("control") != "paused"
        or state.get("current_job_id") != job["application_id"]
        or job.get("status") != "needs_input"
        or job.get("intent")
        or job.get("handed_off")
        or job.get("manual_submission")
        or manual_submission_unresolved(job)
        or assistance_stop_pending(job)
        or any(unresolved_write_failure(row, job, state) for row in job.get("observations", []))
        or precision.get("status") != "ready"
        or precision.get("task_id") != task_id
        or precision.get("run_id") != (state.get("runtime") or {}).get("id")
        or precision.get("page_id") != (job.get("page_observation") or {}).get("page_id")
    ):
        raise PortalDataError(
            "material_edit_pause_required", "请保持精准调整暂停并先核验未知动作。", 409
        )
    worker.store.check_single(job, state)
    target = {
        "batch_id": state["batch_id"],
        "task_id": task_id,
        "application_id": job["application_id"],
        "run_id": precision["run_id"],
        "page_id": precision["page_id"],
        "document_token": precision["document_token"],
    }
    return state, job, target


def edit_material(flow, worker, binding, payload, *, captured_source=None):
    """Reserve once, write outside the application lock, and adopt by exact version."""
    import re
    from copy import deepcopy

    from ._vendor import job_apply_store as helper
    from .validation.hashing import record_digest as digest

    required = {
        "task_id",
        "task_revision",
        "material_id",
        "expected_text_sha256",
        "text",
        "request_id",
    }
    if (
        not isinstance(payload, dict)
        or set(payload) != required
        or any(
            not isinstance(payload.get(key), str)
            or re.fullmatch("[a-f0-9]{32}", payload[key]) is None
            for key in ("task_id", "material_id", "request_id")
        )
        or not isinstance(payload["text"], str)
        or not payload["text"].strip()
        or len(payload["text"]) > 16000
    ):
        raise PortalDataError("invalid_material_edit", "请提供当前附稿版本和完整正文。", 400)
    request_id = payload["request_id"]
    request_sha = digest(payload)
    with flow.applications.write_lock():
        state, job, target = _edit_target(
            flow, worker, binding, payload["task_id"], payload["task_revision"]
        )
        previous = job.get("material_edit") or {}
        if (
            previous.get("request_id") == request_id
            and previous.get("request_sha256") == request_sha
        ):
            if previous.get("status") == "complete":
                return deepcopy(previous)
            raise PortalDataError(
                "material_edit_needs_recheck", "该编辑尝试结果尚未核验，不会重新导出。", 409
            )
        if previous.get("status") in {"preparing", "needs_recheck"}:
            raise PortalDataError(
                "material_edit_needs_recheck", "先核验已有编辑尝试，原稿已保留。", 409
            )
        found = [row for row in job.get("materials", []) if row.get("id") == payload["material_id"]]
        if len(found) != 1:
            raise PortalDataError("material_changed", "附稿版本已变化，请保留编辑并重新读取。", 409)
        old = deepcopy(worker.store.verify_material(found[0], job))
        if old.get("kind") not in {"motivation_text", "cover_letter"} or not old.get("text"):
            raise PortalDataError("material_not_editable", "此材料当前不支持正文编辑。", 409)
        if old.get("text_sha256") != payload["expected_text_sha256"] or hashlib.sha256(
            old["text"].encode()
        ).hexdigest() != old.get("text_sha256"):
            raise PortalDataError("material_changed", "附稿正文版本已变化，请保留编辑。", 409)
        letter_edit = (
            _edit_letter_content(worker, old, payload["text"], request_id)
            if old.get("letter_content")
            else None
        )
        directory = worker.store.root / "materials" / request_id
        if directory.exists():
            raise PortalDataError(
                "material_edit_needs_recheck", "此编辑目录已有原尝试，不会覆盖。", 409
            )
        if previous:
            job.setdefault("material_edit_history", []).append(deepcopy(previous))
        edit = {
            "request_id": request_id,
            "request_sha256": request_sha,
            "status": "preparing",
            "target": target,
            "old_material_id": old["id"],
            "old_sha256": digest(old),
            "new_material_id": request_id,
            "text_sha256": hashlib.sha256(payload["text"].encode()).hexdigest(),
        }
        if captured_source is not None:
            edit["captured_source"] = captured_source
        job["material_edit"] = deepcopy(edit)
        worker.store.save(state)
        directory.mkdir(parents=True)
        helper.atomic_write_json(
            directory / "intent.json", {"edit": edit, "old": old, "text": payload["text"]}
        )
    try:
        saved = deepcopy(old)
        saved.update(
            id=request_id,
            attempt_id=request_id,
            actor="user",
            human_reviewed=False,
            text=payload["text"],
            text_sha256=hashlib.sha256(payload["text"].encode()).hexdigest(),
            parent_material_id=old["id"],
            source_binding=deepcopy(old["source_binding"]),
        )
        saved["source_binding"]["manual_edit"] = True
        for key in ("checks", "grounding", "paragraphs"):
            saved.pop(key, None)
        (directory / "draft.txt").write_text(payload["text"], encoding="utf-8")
        if saved["kind"] == "cover_letter":
            if old.get("letter_content"):
                saved.update(letter_edit)
                for key in (
                    "file_path",
                    "filename",
                    "sha256",
                    "file_sha256",
                    "build",
                    "build_revision",
                    "tex_path",
                    "tex_sha256",
                ):
                    saved.pop(key, None)
            else:
                from .application_materials import export_material_pdf

                saved.update(export_material_pdf(directory, payload["text"].split("\n\n")))
                if "file_sha256" in saved:
                    saved["file_sha256"] = saved["sha256"]
        helper.atomic_write_json(directory / "material.json", saved)
        with flow.applications.write_lock():
            state, job, current_target = _edit_target(flow, worker, binding, payload["task_id"])
            return _adopt_material(worker, current_target, edit, saved, flow=flow)
    except Exception:
        with flow.applications.write_lock():
            state = worker.store.load()
            job = next(
                (row for row in state["jobs"] if row["application_id"] == target["application_id"]),
                None,
            )
            if job is not None and job.get("material_edit") == edit:
                job["material_edit"]["status"] = "needs_recheck"
                worker.store.save(state)
        raise


def _adopt_material(worker, target, edit, saved, *, flow=None):
    checked = worker.validate_material_successor(
        target["application_id"], target=target, edit=edit, material=saved
    )
    if checked["edit"]["status"] == "complete":
        return checked["edit"]
    old = checked["old_material"]
    if saved.get("letter_content"):
        flow.adopt_cover_letter_successor(
            target["task_id"],
            expected_attempt_id=old["letter_attempt_id"],
            expected_content_revision=old["content_revision"],
            content=saved["letter_content"],
            source_binding=saved["source_binding"],
            request_id=edit["request_id"],
        )
    return worker.commit_material_successor(
        target["application_id"], target=target, edit=edit, material=saved
    )


def reconcile_material_edit(flow, worker, binding, payload):
    """Read a completed local candidate once; never repeat export or resume filling."""
    import json
    import re
    from copy import deepcopy

    if (
        not isinstance(payload, dict)
        or set(payload) != {"task_id", "task_revision", "request_id"}
        or any(
            not isinstance(payload.get(key), str)
            or re.fullmatch("[a-f0-9]{32}", payload[key]) is None
            for key in ("task_id", "request_id")
        )
    ):
        raise PortalDataError("invalid_material_edit", "请核验原附稿保存尝试。", 400)
    with flow.applications.write_lock():
        state, job, target = _edit_target(
            flow, worker, binding, payload["task_id"], payload["task_revision"]
        )
        edit = job.get("material_edit") or {}
        if edit.get("request_id") != payload["request_id"] or edit.get("target") != target:
            raise PortalDataError("material_edit_changed", "原附稿保存尝试或原岗已变化。", 409)
        if edit.get("status") == "complete":
            return deepcopy(edit)
        if edit.get("status") != "needs_recheck":
            raise PortalDataError("material_edit_needs_recheck", "附稿仍在准备，尚不能核验。", 409)
        directory = worker.store.root / "materials" / edit["request_id"]
        try:
            if directory.is_symlink() or any(
                (directory / name).is_symlink()
                for name in ("intent.json", "material.json", "draft.txt")
            ):
                raise ValueError("candidate links")
            saved = json.loads((directory / "material.json").read_text())
            worker.validate_material_successor(
                target["application_id"], target=target, edit=edit, material=saved
            )
        except (OSError, ValueError, KeyError, TypeError) as exc:
            if isinstance(exc, PortalDataError) and exc.code == "cover_letter_tex_changed":
                raise
            raise PortalDataError(
                "material_edit_needs_recheck",
                "本地附稿结果未完整核验，原稿已保留，不会重新导出。",
                409,
            ) from exc
        return _adopt_material(worker, target, edit, saved, flow=flow)


def capture_material_tex(flow, worker, binding, payload):
    """Capture uniquely mapped local body edits through the existing human-save path."""
    import json
    import re

    from ._vendor import job_apply_store as helper
    from .application_cover_letter import reconcile_letter_tex, render_cover_letter
    from .application_materials import read_cover_letter_template
    from .validation.hashing import record_digest as digest

    required = {
        "task_id",
        "task_revision",
        "material_id",
        "expected_content_revision",
        "request_id",
    }
    if (
        not isinstance(payload, dict)
        or set(payload) != required
        or any(
            not isinstance(payload.get(key), str)
            or re.fullmatch(r"[a-f0-9]{32}", payload[key]) is None
            for key in ("task_id", "material_id", "request_id")
        )
    ):
        raise PortalDataError("invalid_material_edit", "请提供当前求职信和内容版本。", 400)
    with flow.applications.write_lock():
        _, job, _ = _edit_target(
            flow, worker, binding, payload["task_id"], payload["task_revision"]
        )
        old = next(
            (row for row in job.get("materials", []) if row.get("id") == payload["material_id"]),
            None,
        )
        if (
            not old
            or not old.get("letter_content")
            or not old.get("tex_path")
            or old.get("content_revision") != payload["expected_content_revision"]
        ):
            raise PortalDataError("material_changed", "求职信源或正文版本不能核验。", 409)
        worker.store.verify_material(old, job)
        source = Path(old["tex_path"])
        if (
            source.is_symlink()
            or not source.resolve().is_relative_to((worker.store.root / "materials").resolve())
            or source.stat().st_size > 2_000_000
        ):
            raise PortalDataError("cover_letter_tex_changed", "求职信源位置不能核验。", 409)
        raw = source.read_bytes()
        template = read_cover_letter_template(worker.store, old["source_binding"]["application"])
        mapped = reconcile_letter_tex(old["letter_content"], template, raw.decode("utf-8"))
        capture = {"path": str(source), "sha256": hashlib.sha256(raw).hexdigest()}
        evidence = worker.store.root / "material-source-edits" / payload["request_id"]
        intent = {"request": payload, "source": capture, "old_material_revision": digest(old)}
        if evidence.is_symlink() or evidence.parent.is_symlink():
            raise PortalDataError("material_edit_needs_recheck", "源修改记录不能重定向。", 409)
        if evidence.exists():
            if json.loads((evidence / "intent.json").read_text()) != intent:
                raise PortalDataError(
                    "material_edit_needs_recheck", "已有不同的源修改记录，请保留核对。", 409
                )
        else:
            evidence.mkdir(parents=True)
            helper.atomic_write_json(evidence / "intent.json", intent)
            (evidence / "edited-main.tex").write_bytes(raw)
            (evidence / "source.diff").write_text(mapped["diff"], encoding="utf-8")
        if mapped["status"] != "ready":
            raise PortalDataError(
                "letter_tex_mapping_required", "修改不能唯一映射到正文，完整源和差异已保留。", 409
            )
        text = render_cover_letter(mapped["content"], template)["text"]
        edit = {
            "task_id": payload["task_id"],
            "task_revision": payload["task_revision"],
            "material_id": old["id"],
            "expected_text_sha256": old["text_sha256"],
            "request_id": payload["request_id"],
            "text": text,
        }
    return edit_material(flow, worker, binding, edit, captured_source=capture)
