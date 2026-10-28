"""Loopback review-to-PDF binding keeps material approval an explicit user write."""

from copy import deepcopy
from uuid import uuid4

from test_application_flow import wait_for
from test_career_portal_http import portal as portal
from test_full_latex_http import bind_generate, generated_portal
from test_preparation_entry import post, snapshot

from career_evidence_graph.application_prism import source_snapshot
from career_evidence_graph.application_worker import digest


def prepare_reviewed(active, task, tmp_path, monkeypatch):
    store = active.server.application_resume_store
    original = store.draft
    draft = deepcopy(original(task["draft_id"]))
    project = tmp_path / "review-working"
    project.mkdir()
    (project / "main.tex").write_text(draft["latex_source"])
    draft.update(
        id=uuid4().hex,
        source_checkpoint=source_snapshot(project, "main.tex"),
        group_session={"id": "session"},
        group_context_revision="context",
    )
    draft["review_groups"][0]["review_fingerprint"] = "9" * 64
    drafts = {draft["id"]: draft}
    monkeypatch.setattr(store, "draft", lambda key: drafts.get(key) or original(key))
    monkeypatch.setattr(store, "prepare_group_review", lambda *a, **k: draft)
    monkeypatch.setattr(
        store,
        "group_review_state",
        lambda key: {
            "status": "ready",
            "pending_attempt_id": None,
            "live_source_revision": source_snapshot(project, "main.tex")["source_revision"],
        },
    )

    def capture(*a, **k):
        updated = deepcopy(draft)
        updated.update(
            id=uuid4().hex,
            draft_sha256=digest("captured"),
            group_preview={
                "id": uuid4().hex,
                "source_revision": draft["source_checkpoint"]["source_revision"],
            },
            verified_unchanged_group_ids=[],
        )
        drafts[updated["id"]] = updated
        return {"draft": updated, "status": "ready"}

    monkeypatch.setattr(store, "capture_group_review", capture)
    for action, extra in [
        ("begin-group-review", {}),
        (
            "capture-group-review",
            {"expected_source_revision": draft["source_checkpoint"]["source_revision"]},
        ),
    ]:
        status, task = post(
            active, action, {"task_id": task["id"], "task_revision": task["revision"], **extra}
        )
        assert status == 200, task
    for group in drafts[task["draft_id"]]["review_groups"]:
        status, task = post(
            active,
            "review-group",
            {
                "task_id": task["id"],
                "task_revision": task["revision"],
                "draft_id": task["draft_id"],
                "draft_sha256": task["draft_sha256"],
                "group_id": group["id"],
                "review_fingerprint": group["review_fingerprint"],
            },
        )
        assert status == 200, task
    return task, drafts[task["draft_id"]], project


def install_export(active, task, draft, monkeypatch):
    flow = active.server.application_flow_service
    store = active.server.application_resume_store
    exports = {}
    requests = []

    def export(**kwargs):
        from career_evidence_graph.application_group_review import group_review_snapshot

        requests.append(kwargs)
        result = {
            key: deepcopy(draft.get(key))
            for key in [
                "application_id",
                "analysis_binding",
                "task_inputs",
                "resume_configuration_revision",
                "source_checkpoint",
                "origin",
            ]
        }
        result.update(
            id=kwargs["export_id"],
            kind="pdf",
            draft_id=draft["id"],
            draft_sha256=draft["draft_sha256"],
            pdf_sha256="f" * 64,
            export_configuration_revision=flow._export_configuration(task),
            prism_source_revision=draft["source_checkpoint"]["source_revision"],
            group_review=group_review_snapshot(draft, task["inputs"], kwargs["group_reviews"]),
            source_review={},
            items=[],
            factual_review="groups_reviewed",
            file_base64="JVBERiBzeW50aGV0aWM=",
        )
        exports[result["id"]] = result
        return result

    monkeypatch.setattr(store, "export_for_draft", export)
    monkeypatch.setattr(store, "read_export", lambda key: deepcopy(exports[key]))
    return requests


def test_http_exact_group_receipts_reach_binding_and_separate_pdf_confirmation(
    portal, tmp_path, monkeypatch
):
    with generated_portal(portal, tmp_path, monkeypatch) as (active, task, base, calls, work):
        task = bind_generate(active, task, base)
        task, draft, project = prepare_reviewed(active, task, tmp_path, monkeypatch)
        flow = active.server.application_flow_service
        requests = install_export(active, task, draft, monkeypatch)
        status, _ = post(
            active,
            "export-pdf",
            {
                "task_id": task["id"],
                "task_revision": task["revision"],
                "draft_id": task["draft_id"],
                "draft_sha256": task["draft_sha256"],
            },
        )
        assert status == 200
        task = wait_for(
            flow,
            task["id"],
            lambda r: r["status"] in {"materials_ready", "export_failed", "needs_recheck"},
        )
        assert task["status"] == "materials_ready", task
        assert requests[0]["group_reviews"] == task["group_reviews"] and task["materials_confirmed"]
        assert task["material_binding"]["human_reviewed"] is False
        assert active.request("GET", f"/api/flow/exports/{task['resume_id']}")[0] == 200
        assert len(requests) == 1 and len(calls) == 1 and not work["exports"]
        status, confirmed = post(
            active,
            "confirm-materials",
            {
                "task_id": task["id"],
                "task_revision": task["revision"],
                "resume_id": task["resume_id"],
                "resume_sha256": task["resume_sha256"],
            },
        )
        assert status == 200, confirmed
        assert confirmed["materials_confirmed"] and confirmed["status"] == "materials_ready"
        assert snapshot(active)["mode"] == "preparation" and not confirmed["worker_ref"]
        assert (
            post(
                active,
                "prepare-worker",
                {
                    "task_id": confirmed["id"],
                    "task_revision": confirmed["revision"],
                    "country": "CH",
                    "send_confirmed": True,
                },
            )[0]
            == 409
        )
        (project / "main.tex").write_text(draft["latex_source"] + " changed")
        assert (
            post(
                active,
                "confirm-materials",
                {
                    "task_id": confirmed["id"],
                    "task_revision": confirmed["revision"],
                    "resume_id": confirmed["resume_id"],
                    "resume_sha256": confirmed["resume_sha256"],
                },
            )[0]
            == 409
        )


def test_ui_keeps_group_review_and_preview_without_pdf_confirmation_gate(portal):
    status, _, raw = portal.request("GET", "/static/application_flow.js")
    assert status == 200
    text = raw.decode()
    for phrase in [
        "绑定完整源与新 PDF",
        "核验已绑定 PDF 回执",
        "打开最终 PDF",
        "最终简历 PDF",
        "系统已保存当前 PDF",
    ]:
        assert phrase in text
    for removed in ("flow-reviewed-pdf", "flow-confirm-materials", "/api/flow/confirm-materials"):
        assert removed not in text
    assert 'task.factual_review !== "groups_reviewed"' in text
