"""Existing executor reports reconnect without replay or submission."""

import hashlib
import subprocess
from copy import deepcopy

import pytest
from test_application_handoff import SHA, act, handoff, prepare, ready  # noqa: F401, F811

from career_evidence_graph.application_flow import ApplicationFlowService
from career_evidence_graph.application_handoff import CodexHandoffService
from career_evidence_graph.career_portal_data import PortalDataError


@pytest.fixture
def linked(handoff, tmp_path, monkeypatch):  # noqa: F811
    service, store, app = handoff
    task = prepare(service, app)
    reply = act(service, task, "claim", owner="synthetic-executor")
    task = ready(service, reply["active_task"], reply["claim_token"])
    calls = []
    flow = ApplicationFlowService(
        store,
        tmp_path / "flow",
        preparation_only=True,
        callbacks={
            "verify_materials": lambda task: calls.append("verify"),
            "analysis": lambda task: pytest.fail("No model replay"),
            "resume": lambda task: pytest.fail("No generation replay"),
            "export": lambda task: pytest.fail("No Prism replay"),
            "prepare_worker": lambda task: pytest.fail("No worker replay"),
        },
    )
    original = flow.create(app["id"], app["revision"])
    with store.write_lock():
        state = flow._load()
        row = flow._task(state, original["id"])
        for stage in row["stages"].values():
            stage["status"] = "complete"
        row.update(
            status="materials_ready",
            materials_confirmed=True,
            resume_id="a" * 32,
            resume_sha256=SHA,
        )
        flow._save(state)
    original = deepcopy(row)
    monkeypatch.setattr(
        subprocess, "Popen", lambda *a, **kw: pytest.fail("No browser/model process")
    )
    yield flow, service, original, task, calls
    flow.close()


def attach(flow, original, task, root):
    return flow.request(
        "attach-existing-handoff",
        {
            "task_id": original["id"],
            "task_revision": original["revision"],
            "handoff_root": str(root),
            "handoff_task_id": task["id"],
            "handoff_task_revision": task["revision"],
        },
    )


def files(root):
    return {
        str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in root.rglob("*")
        if path.is_file()
    }


def test_attach_preserves_handoff_and_reopens_same_flow(linked):
    flow, service, original, report, calls = linked
    before = files(service.root)
    attached = attach(flow, original, report, service.root)
    assert attached["status"] == "materials_ready"
    assert attached["worker_ref"] is None
    assert attached["artifacts"] == original["artifacts"]
    assert attached["codex_handoff_ref"]["kind"] == "executor_report"
    assert attached["codex_handoff_ref"]["human_reviewed"] is False
    assert "_claim_token" not in str(attached)
    assert "Synthetic Person" not in str(attached)
    assert attach(flow, attached, report, service.root) == attached
    assert len(attached["codex_handoff_history"]) == 1
    projected = flow.snapshot(original["id"])["active_task"]
    assert projected["status"] == "ready_for_review"
    assert projected["revision"] == attached["revision"]
    flow.close()
    reopened = ApplicationFlowService(
        flow.applications, flow.root, callbacks=flow.callbacks, preparation_only=True
    )
    try:
        assert reopened.snapshot(original["id"])["active_task"] == projected
        for operation, extra in [
            ("start", {"stage": "analysis"}),
            ("prepare-worker", {"country": "CHE", "send_confirmed": True}),
        ]:
            with pytest.raises(PortalDataError):
                reopened.request(
                    operation,
                    {"task_id": attached["id"], "task_revision": attached["revision"], **extra},
                )
    finally:
        reopened.close()
    assert files(service.root) == before
    assert calls


@pytest.mark.parametrize(
    "change",
    [
        "job",
        "pdf",
        "fields",
        "missing",
        "attachment",
        "claim",
        "token",
        "status",
        "active",
        "source",
        "executor",
        "page",
        "reservation",
        "owner",
    ],
)
def test_reject_invalid_existing_report(linked, change):
    flow, service, original, report, _ = linked
    state = service._load()
    task = state["tasks"][0]
    evidence = task["readbacks"][-1]
    if change == "job":
        task["application_id"] = "another-job"
    elif change == "pdf":
        task["file_sha256"] = "b" * 64
    elif change == "fields":
        evidence["fields"] = []
    elif change == "missing":
        evidence["missing"] = ["Required field"]
    elif change == "attachment":
        evidence["attachment"]["sha256"] = "b" * 64
    elif change == "claim":
        task["claim"] = None
    elif change == "token":
        task.pop("_claim_token")
    elif change == "status":
        task["status"] = "needs_recheck"
    elif change == "active":
        task["active"] = False
    elif change == "source":
        evidence["source"] = ""
    elif change == "executor":
        evidence["executor"] = "different"
    elif change == "page":
        evidence["page_url"] = "https://example.com/other"
    elif change == "reservation":
        task["reservation_pending"] = True
    elif change == "owner":
        record = next((flow.applications.root / ".execution").glob("*.json"))
        record.unlink()
    service._save(state)
    with pytest.raises(PortalDataError):
        attach(flow, original, task, service.root)
    assert flow.witness(original["id"])[1] == original


def test_reference_change_projects_pause_without_mutation(linked):
    flow, service, original, report, _ = linked
    attached = attach(flow, original, report, service.root)
    state = service._load()
    state["tasks"][0]["readbacks"][-1]["source"] += "; later recheck"
    service._save(state)
    before = files(service.root)
    task = flow.snapshot(original["id"])["active_task"]
    assert task["status"] == "needs_recheck"
    assert task["codex_handoff_ref"]["status"] == "needs_recheck"
    assert flow.witness(original["id"])[1] == attached
    assert files(service.root) == before


def test_missing_root_is_never_initialized(handoff, tmp_path):  # noqa: F811
    _, store, _ = handoff
    missing = tmp_path / "missing"
    with pytest.raises(PortalDataError):
        CodexHandoffService(store, missing, existing_only=True)
    assert not missing.exists()
    missing.mkdir()
    with pytest.raises(PortalDataError):
        CodexHandoffService(store, missing, existing_only=True)
    assert list(missing.iterdir()) == []


def test_existing_reader_cannot_write_or_initialize_answers(linked):
    _, service, _, report, _ = linked
    reader = CodexHandoffService(service.applications, service.root, existing_only=True)
    before = files(service.root)
    assert (
        reader.existing_reference(report["id"], report["revision"])["status"] == "ready_for_review"
    )
    with pytest.raises(PortalDataError):
        reader.request("claim", {})
    assert files(service.root) == before


def test_bound_flow_remains_original_after_input_changes_and_force_new(linked):
    flow, service, original, report, _ = linked
    attached = attach(flow, original, report, service.root)
    application = flow.applications.get_application(original["application_id"])
    changed = flow.applications.update_application(
        application["id"], {"job_description": "Changed role inputs"}, application["revision"]
    )
    for force_new in (False, True):
        assert (
            flow.create(
                changed["id"],
                changed["revision"],
                inputs={"new_configuration": "updated"},
                force_new=force_new,
            )
            == attached
        )
    assert len(flow.snapshot()["tasks"]) == 1
    assert flow.snapshot(original["id"])["active_task"]["status"] == "needs_recheck"
    with pytest.raises(PortalDataError) as error:
        flow.import_latex(changed["id"], changed["revision"], "/unused", "main.tex")
    assert error.value.code == "flow_handoff_bound"
    assert len(flow.snapshot()["tasks"]) == 1


def test_normal_cancel_preserves_uploaded_reference_and_never_releases_executor(linked):
    flow, service, original, report, _ = linked
    attached = attach(flow, original, report, service.root)
    before = files(service.root)
    cancelled = flow.cancel(attached["id"], attached["revision"])
    assert cancelled["status"] == "cancelled"
    assert cancelled["codex_handoff_ref"] == attached["codex_handoff_ref"]
    assert cancelled["codex_handoff_history"] == attached["codex_handoff_history"]
    assert files(service.root) == before


def test_corrupt_report_projects_pause_instead_of_breaking_snapshot(linked):
    flow, service, original, report, _ = linked
    attached = attach(flow, original, report, service.root)
    state = service._load()
    state["tasks"][0]["readbacks"] = ["damaged"]
    service._save(state)
    assert flow.snapshot(attached["id"])["active_task"]["status"] == "needs_recheck"


def test_pending_worker_preparation_blocks_attach(linked):
    flow, service, original, report, _ = linked
    state = flow._load()
    task = state["tasks"][0]
    task["worker_preparation"] = {"status": "pending"}
    flow._save(state)
    with pytest.raises(PortalDataError) as error:
        attach(flow, task, report, service.root)
    assert error.value.code == "flow_materials_required"


def test_portal_existing_material_callback_normalizes_pdf_route(tmp_path, monkeypatch):
    from career_evidence_graph import application_experience_latex
    from career_evidence_graph.career_portal import create_server

    applications, career = tmp_path / "applications", tmp_path / "career"
    applications.mkdir()
    career.mkdir()
    subprocess.run(["git", "init", "--quiet", str(career)], check=True)
    export_id = "c" * 32
    checked = {
        "export": {"id": export_id, "preview_url": f"/api/resumes/{export_id}/pdf"},
        "draft": {"id": "retained"},
    }
    original = deepcopy(checked)
    reads = []

    def read_completed(store, task, generation_id, identifier):
        reads.append((task, generation_id, identifier))
        return checked

    monkeypatch.setattr(application_experience_latex, "read_completed", read_completed)
    server = create_server(applications, career, flow_root=tmp_path / "flow", preparation_only=True)
    try:
        result = server.application_flow_service.callbacks["existing_experience_materials"](
            {"id": "task"}, "generation", export_id
        )
        assert result["export"]["preview_url"] == f"/api/flow/resumes/{export_id}/pdf"
        assert result["draft"] == original["draft"]
        assert checked == original
        assert reads == [({"id": "task"}, "generation", export_id)]
    finally:
        server.application_flow_service.close()
        server.server_close()
