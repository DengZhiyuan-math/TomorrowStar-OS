"""PDF export is a separate, resumable stage over an explicitly reviewed draft."""

import threading

import pytest
from test_application_flow import application as application
from test_application_flow import wait_for
from test_job_explanations import requirement

from career_evidence_graph.application_flow import ApplicationFlowService
from career_evidence_graph.career_portal_data import PortalDataError


@pytest.fixture
def reviewed_draft(application, tmp_path):
    applications, job = application
    calls = []

    def export(task):
        calls.append("export")
        return {
            "id": task["stages"]["export"]["attempt_id"],
            "kind": "pdf",
            "draft_id": task["draft_id"],
            "draft_sha256": task["draft_sha256"],
            "pdf_sha256": "b" * 64,
            "export_configuration_revision": "export-v1",
        }

    service = ApplicationFlowService(
        applications,
        tmp_path / "flow",
        preparation_only=True,
        callbacks={
            "analysis": lambda _: {"id": "a", "requirements": [requirement()]},
            "resume": lambda _: (
                calls.append("generate") or {"id": "d", "kind": "draft", "draft_sha256": "a" * 64}
            ),
            "verify_draft": lambda _: None,
            "verify_materials": lambda _: None,
            "export": export,
            "export_configuration": lambda: "export-v1",
        },
    )
    try:
        task = service.create(job["id"], job["revision"])
        service.start(task["id"], task["revision"], "analysis")
        task = wait_for(service, task["id"], lambda row: row["status"] == "analysis_ready")
        service.start(task["id"], task["revision"], "resume")
        task = wait_for(service, task["id"], lambda row: row["status"] == "draft_ready")
        yield service, task, calls
    finally:
        service.close()


def export_request(service, task, **extra):
    return service.request(
        "export-pdf",
        {
            "task_id": task["id"],
            "task_revision": task["revision"],
            "draft_id": task["draft_id"],
            "draft_sha256": task["draft_sha256"],
            **extra,
        },
    )


def review(service, task):
    return service.review_draft(
        task["id"], task["revision"], task["draft_id"], task["draft_sha256"]
    )


def test_export_requires_review_and_preserves_draft_without_model_reentry(reviewed_draft):
    service, task, calls = reviewed_draft
    with pytest.raises(PortalDataError) as error:
        export_request(service, task)
    assert error.value.code == "flow_draft_review_required"
    task = review(service, task)
    reviewed = task["draft_review"]
    export_request(service, task)
    task = wait_for(service, task["id"], lambda row: row["status"] == "materials_ready")
    assert task["draft_id"] == "d" and task["draft_review"] == reviewed
    assert task["resume_id"] != task["draft_id"]
    assert task["resume_sha256"] == "b" * 64 and task["materials_confirmed"]
    assert task["material_binding"]["actor"] == "system"
    assert task["material_binding"]["human_reviewed"] is False
    assert not task.get("material_reviews")
    assert task["artifacts"][-1]["stage"] == "export"
    assert task["artifacts"][-1]["adopted"] is True
    assert calls == ["generate", "export"]


def test_known_export_failure_requires_explicit_retry_and_keeps_review(reviewed_draft):
    service, task, calls = reviewed_draft
    task = review(service, task)
    original = service.callbacks["export"]

    def fail(_):
        calls.append("failed-export")
        raise PortalDataError("resume_export_failed", "Synthetic renderer failure", 503)

    service.callbacks["export"] = fail
    export_request(service, task)
    task = wait_for(service, task["id"], lambda row: row["status"] == "export_failed")
    assert task["draft_review"]["status"] == "reviewed" and task["resume_id"] is None
    with pytest.raises(PortalDataError) as error:
        export_request(service, task)
    assert error.value.code == "flow_retry_required"
    service.callbacks["export"] = original
    export_request(service, task, retry=True)
    task = wait_for(service, task["id"], lambda row: row["status"] == "materials_ready")
    assert calls == ["generate", "failed-export", "export"]


@pytest.mark.parametrize("completed", [True, False])
def test_unknown_export_requires_read_only_reconciliation_before_retry(reviewed_draft, completed):
    service, task, calls = reviewed_draft
    task = review(service, task)
    original = service.callbacks["export"]
    receipts = {}

    def unknown(task):
        receipts["result"] = original(task)
        raise PortalDataError("resume_export_needs_recheck", "Synthetic unknown publication", 409)

    service.callbacks["export"] = unknown
    service.callbacks["reconcile_export"] = lambda task: (
        receipts["result"]
        if completed
        else {
            "status": "not_complete",
            "id": task["stages"]["export"]["attempt_id"],
        }
    )
    export_request(service, task)
    task = wait_for(service, task["id"], lambda row: row["status"] == "needs_recheck")
    for stage in ("export", "resume"):
        with pytest.raises(PortalDataError) as error:
            service.start(task["id"], task["revision"], stage, retry=True)
        assert error.value.code == "flow_export_recheck_required"
    task = service.request(
        "recheck-export",
        {
            "task_id": task["id"],
            "task_revision": task["revision"],
        },
    )
    assert task["status"] == ("materials_ready" if completed else "export_failed")
    assert calls == ["generate", "export"]
    if completed:
        assert task["artifacts"][-1]["reconciled"]
    else:
        service.callbacks["export"] = original
        export_request(service, task, retry=True)
        wait_for(service, task["id"], lambda row: row["status"] == "materials_ready")
        assert calls == ["generate", "export", "export"]


@pytest.mark.parametrize("action", ["cancel", "update", "config"])
def test_late_export_is_not_adopted_after_cancel_input_or_renderer_change(reviewed_draft, action):
    service, task, calls = reviewed_draft
    inputs = dict(task["inputs"])
    if action == "update":
        application = service.applications.get_application(task["application_id"])
        service.input_provider = lambda _: {
            "application_revision": application["revision"],
            "inputs": inputs,
        }
    task = review(service, task)
    entered, release = threading.Event(), threading.Event()
    original = service.callbacks["export"]

    def delayed(task):
        entered.set()
        assert release.wait(3)
        return original(task)

    service.callbacks["export"] = delayed
    export_request(service, task)
    try:
        assert entered.wait(3)
        task = service.snapshot(task["id"])["active_task"]
        if action == "cancel":
            service.cancel(task["id"], task["revision"])
        elif action == "update":
            attempt_id = task["stages"]["export"]["attempt_id"]
            before = service.path.read_bytes()
            inputs["source"] = "changed"
            with pytest.raises(PortalDataError) as error:
                service.update_inputs(
                    task["id"], task["revision"], application["revision"], inputs=inputs
                )
            assert error.value.code == "flow_update_inflight" and error.value.status == 409
            assert service.path.read_bytes() == before
        else:
            service.callbacks["export_configuration"] = lambda: "export-v2"
    finally:
        release.set()
    task = wait_for(service, task["id"], lambda row: row["status"] != "exporting")
    # Wait for the old candidate to return even after cancellation changed the visible status.
    task = wait_for(
        service,
        task["id"],
        lambda row: (
            any(artifact["stage"] == "export" for artifact in row["artifacts"])
            or row["status"] == "export_failed"
        ),
    )
    assert task["resume_id"] is None and not task["materials_confirmed"]
    assert not any(a["adopted"] for a in task["artifacts"] if a["stage"] == "export")
    if action == "update":
        assert task["stages"]["export"]["attempt_id"] == attempt_id
        assert task["stages"]["export"]["status"] == "failed"
        assert task["stages"]["export"]["error_code"] == "flow_inputs_stale"
        artifact = task["artifacts"][-1]
        assert artifact["attempt_id"] == attempt_id and artifact["inputs"] == {}
        assert calls == ["generate", "export"]
        artifacts = task["artifacts"]
        task = service.update_inputs(task["id"], task["revision"], application["revision"])
        assert task["inputs"] == inputs and task["artifacts"] == artifacts
        assert task["stages"]["export"]["status"] == "pending"
        assert calls == ["generate", "export"]


@pytest.mark.parametrize("written", [False, True])
def test_ambiguous_flow_adoption_save_reopens_without_rendering_again(reviewed_draft, written):
    service, task, calls = reviewed_draft
    task = review(service, task)
    save, original = service._save, service.callbacks["export"]
    receipt = {}
    failed = threading.Event()

    def export(task):
        receipt["result"] = original(task)
        return receipt["result"]

    def uncertain_save(state):
        if not failed.is_set() and any(
            t["stages"].get("export", {}).get("status") == "complete" for t in state["tasks"]
        ):
            failed.set()
            if written:
                save(state)
            raise OSError("Synthetic uncertain atomic flow save")
        save(state)

    service.callbacks["export"] = export
    service.callbacks["reconcile_export"] = lambda _: receipt["result"]
    service._save = uncertain_save
    export_request(service, task)
    assert failed.wait(3)
    service.close()
    reopened = ApplicationFlowService(
        service.applications, service.root, preparation_only=True, callbacks=service.callbacks
    )
    try:
        task = reopened.snapshot(task["id"])["active_task"]
        assert task["status"] == "needs_recheck" and not task["materials_confirmed"]
        assert bool(task["resume_id"]) is written
        task = reopened.recheck_export(task["id"], task["revision"])
        assert task["status"] == "materials_ready" and task["materials_confirmed"]
        assert task["material_binding"]["actor"] == "system"
        assert task["material_binding"]["human_reviewed"] is False
        assert not task.get("material_reviews")
        assert calls == ["generate", "export"]
    finally:
        reopened.close()


def test_reconciliation_cannot_revive_a_cancelled_unknown_export(reviewed_draft):
    service, task, _ = reviewed_draft
    task = review(service, task)
    result = {}
    original = service.callbacks["export"]

    def unknown(task):
        result["saved"] = original(task)
        raise PortalDataError("resume_export_needs_recheck", "Unknown publication", 409)

    service.callbacks["export"] = unknown
    service.callbacks["reconcile_export"] = lambda _: result["saved"]
    export_request(service, task)
    task = wait_for(service, task["id"], lambda row: row["status"] == "needs_recheck")
    task = service.cancel(task["id"], task["revision"])
    with pytest.raises(PortalDataError) as error:
        service.recheck_export(task["id"], task["revision"])
    assert error.value.code == "flow_cancelled"
    assert service.snapshot(task["id"])["active_task"]["resume_id"] is None


def test_reopening_a_persisted_queue_before_admission_allows_manual_export_retry(
    reviewed_draft,
    monkeypatch,
):
    service, task, calls = reviewed_draft
    task = review(service, task)
    # Simulate process exit after the durable queued snapshot, before queue admission.
    monkeypatch.setattr(service._queue, "put", lambda _: None)
    task = export_request(service, task)
    assert task["stages"]["export"]["status"] == "queued"
    monkeypatch.undo()
    service.close()
    reopened = ApplicationFlowService(
        service.applications, service.root, preparation_only=True, callbacks=service.callbacks
    )
    try:
        task = reopened.snapshot(task["id"])["active_task"]
        assert task["status"] == "export_failed"
        assert task["stages"]["export"]["error_code"] == "flow_export_not_started"
        export_request(reopened, task, retry=True)
        wait_for(reopened, task["id"], lambda row: row["status"] == "materials_ready")
        assert calls == ["generate", "export"]
    finally:
        reopened.close()
