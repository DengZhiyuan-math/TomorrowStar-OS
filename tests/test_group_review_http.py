"""Loopback grouped review uses explicit writes; status and preview reads are inert."""

from copy import deepcopy

from test_career_portal_http import portal as portal
from test_full_latex_http import bind_generate, generated_portal
from test_preparation_entry import post, snapshot

from career_evidence_graph.application_prism import source_snapshot


def test_http_group_review_binds_same_source_and_keeps_material_gate(portal, tmp_path, monkeypatch):
    with generated_portal(portal, tmp_path, monkeypatch) as (active, task, base, calls, work):
        task = bind_generate(active, task, base)
        store = active.server.application_resume_store
        original = store.draft
        generated = original(task["draft_id"])
        project = tmp_path / "review-working"
        project.mkdir()
        (project / "main.tex").write_text(generated["latex_source"])
        prepared = deepcopy(generated)
        prepared.update(
            id="f" * 32,
            source_checkpoint=source_snapshot(project, "main.tex"),
            group_session={"id": "session"},
            group_context_revision="context",
        )
        prepared["review_groups"][0]["review_fingerprint"] = "9" * 64
        drafts = {prepared["id"]: prepared}
        reads = []
        monkeypatch.setattr(
            store, "draft", lambda key: drafts[key] if key in drafts else original(key)
        )
        monkeypatch.setattr(
            store, "prepare_group_review", lambda *args, **kwargs: prepared, raising=False
        )
        monkeypatch.setattr(
            store,
            "group_review_state",
            lambda key: {
                "status": "ready",
                "live_source_revision": source_snapshot(project, "main.tex")["source_revision"],
            },
            raising=False,
        )

        def capture(*args, **kwargs):
            reads.append(kwargs)
            revised = deepcopy(prepared)
            revised.update(
                id="e" * 32,
                draft_sha256="3" * 64,
                group_preview={
                    "id": "preview",
                    "source_revision": prepared["source_checkpoint"]["source_revision"],
                },
                verified_unchanged_group_ids=[],
            )
            drafts[revised["id"]] = revised
            return {"draft": revised, "preview": revised["group_preview"], "status": "ready"}

        monkeypatch.setattr(store, "capture_group_review", capture, raising=False)
        monkeypatch.setattr(
            store, "group_preview_pdf", lambda *args: b"%PDF synthetic", raising=False
        )
        status, task = post(
            active, "begin-group-review", {"task_id": task["id"], "task_revision": task["revision"]}
        )
        assert status == 200 and task["prism"]["project_root"] == str(project)
        assert (
            snapshot(active)["group_review"]["live_source_revision"]
            == task["prism"]["source_revision"]
        )
        assert not reads
        status, task = post(
            active,
            "capture-group-review",
            {
                "task_id": task["id"],
                "task_revision": task["revision"],
                "expected_source_revision": task["prism"]["source_revision"],
            },
        )
        assert status == 200 and len(reads) == 1
        preview_path = f"/api/flow/group-previews/{task['draft_id']}/preview/pdf"
        assert active.request("GET", preview_path)[0] == 200
        assert snapshot(active)["draft_integrity"]["status"] == "valid"
        assert len(reads) == 1
        status, task = post(
            active,
            "review-group",
            {
                "task_id": task["id"],
                "task_revision": task["revision"],
                "draft_id": task["draft_id"],
                "draft_sha256": task["draft_sha256"],
                "group_id": "synthetic",
                "review_fingerprint": "9" * 64,
            },
        )
        assert status == 200 and task["factual_review"] == "groups_reviewed"
        assert not task["materials_confirmed"] and task["resume_id"] is None
        assert (
            post(
                active,
                "export-pdf",
                {
                    "task_id": task["id"],
                    "task_revision": task["revision"],
                    "draft_id": task["draft_id"],
                    "draft_sha256": task["draft_sha256"],
                },
            )[0]
            == 200
        )
        # Exact grouped review now authorizes binding; this fake draft is not a
        # valid immutable store candidate and cannot become approved material.
        assert not snapshot(active)["active_task"]["materials_confirmed"]
        assert not snapshot(active)["active_task"]["worker_ref"]
        assert (
            active.request("GET", "/api/flow/group-previews/" + "0" * 32 + "/preview/pdf")[0] == 404
        )
        assert len(reads) == 1 and not work["exports"]


def test_group_ui_exposes_one_confirmation_per_group_and_technical_preview(portal):
    status, _, raw = portal.request("GET", "/static/application_flow.js")
    assert status == 200
    text = raw.decode()
    for phrase in [
        "确认此经历组的事实与责任归属",
        "当前技术预览 PDF",
        "核验已有预览回执",
        "新增有来源的经历组",
        "选择已存在的事实来源与责任归属",
    ]:
        assert phrase in text
    assert "review_fingerprint:group.review_fingerprint" in text
    assert 'task.group_mapping?.status!=="ready"' in text
