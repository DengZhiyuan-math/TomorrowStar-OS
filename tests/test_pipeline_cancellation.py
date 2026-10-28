"""The Pipeline cancels one job; Flow only cancels its preparation."""

from copy import deepcopy
from types import SimpleNamespace

import pytest
from test_application_flow import application as application
from test_pipeline_current_job import current_pipeline as current_pipeline
from test_pipeline_recommendation_queue import drive

from career_evidence_graph.application_flow import ApplicationFlowService
from career_evidence_graph.application_pipeline import ApplicationPipeline
from career_evidence_graph.application_worker import WorkerService, start_run
from career_evidence_graph.career_portal_data import PortalDataError


@pytest.fixture
def cancellable_pipeline(current_pipeline, monkeypatch):
    pipeline, flow, intake, worker = current_pipeline

    def cancel_preparation(identifier, revision, **_options):
        assert flow.tasks[identifier]["revision"] == revision
        if "execution_cancellation" in _options:
            assert _options["execution_cancellation"]["status"] in {
                "stopping",
                "stopped",
                "unknown",
            }
        flow.calls.append(("cancel-preparation", identifier))
        flow.tasks[identifier]["status"] = "cancelled"
        return deepcopy(flow.tasks[identifier])

    monkeypatch.setattr(flow, "cancel_preparation", cancel_preparation, raising=False)
    return pipeline, flow, intake, worker


def test_preparation_cancel_never_controls_the_worker(application, tmp_path):
    applications, job = application
    controls = []
    flow = ApplicationFlowService(
        applications,
        tmp_path / "flow",
        callbacks={"control_worker": lambda *args: controls.append(args)},
    )
    try:
        task = flow.create(job["id"], job["revision"])
        result = flow.cancel_preparation(task["id"], task["revision"])
        assert result["status"] == "cancelled"
        assert controls == []
        assert flow.task_snapshot(task["id"])["status"] == "cancelled"
    finally:
        flow.close()


@pytest.mark.parametrize("unknown", [False, True])
def test_pipeline_cancel_retains_current_job_and_unknown_page_effect(cancellable_pipeline, unknown):
    pipeline, flow, _, worker = cancellable_pipeline
    pipeline.start(request_id="begin-cancelled-job")
    first = drive(pipeline, "filling")
    task_id = first["active_task_id"]
    state = worker.store.load()
    state["jobs"][0].update(
        page_open=True,
        intent={"action": "upload", "attempt_id": "unresolved-before-cancel"} if unknown else None,
    )
    worker.store.save(state)

    result = pipeline.cancel_current(
        task_id, flow.tasks[task_id]["revision"], request_id="cancel-current-job"
    )
    assert result["control"] == "paused"
    assert result["status"] == ("needs_recheck" if unknown else "cancelled")
    assert result["active_task_id"] == task_id
    assert len(flow.tasks) == 1
    stopped = worker.store.load()["jobs"][0]
    assert stopped["status"] == "cancelled" and stopped["page_open"] is True
    assert stopped["intent"] == (
        {"action": "upload", "attempt_id": "unresolved-before-cancel"} if unknown else None
    )
    assert result["current_cancellation"]["status"] == ("partial" if unknown else "complete")
    pipeline._tick()
    assert pipeline.snapshot()["active_task_id"] == task_id


def test_cancellation_waits_for_codex_and_reconciles_without_another_user_request(
    cancellable_pipeline,
):
    import time

    pipeline, flow, _, worker = cancellable_pipeline
    pipeline.start(request_id="begin-draining-job")
    first = drive(pipeline, "filling")
    task_id = first["active_task_id"]
    run_id = start_run(worker.store)
    state = worker.store.load()
    state["control"] = "running"
    job = state["jobs"][0]
    job.update(status="filling", page_open=True)
    job["page_observation"] = {
        "run_id": run_id,
        "page_id": "retained-page",
        "event": "observed",
        "at": time.time(),
    }
    job["form_state"] = {
        "binding": {
            "run_id": run_id,
            "page_id": "retained-page",
            "document_token": "retained-document",
            "step": job["job_url"],
        }
    }
    worker.store.save(state)
    identifier = job["application_id"]
    worker.request(
        "request-assistance",
        {
            "application_id": identifier,
            "binding": worker.assistance_context(identifier)["binding"],
            "request_id": "draining-assistance",
        },
    )
    reference = worker.assistance_context(identifier)["assistance_ref"]
    worker.request(
        "claim-assistance",
        {
            "application_id": identifier,
            "assistance_ref": reference,
            "request_id": "draining-claim",
        },
    )
    result = pipeline.cancel_current(request_id="cancel-draining-job")
    assert result["current_cancellation"]["status"] == "stopping"
    assert result["current_cancellation"]["worker_status"] == "stopping"
    stop = worker.store.load()["jobs"][0]["assistance"]["stop"]
    worker.record_assistance_stop(
        identifier,
        reference,
        {
            "tools_revoked": True,
            "local_tools_drained": True,
            "process_stopped": True,
            "native_turn_id": None,
            "native_turn_status": "idle",
            "stop_status": "stopped",
        },
        request_id=stop["request_id"],
    )
    pipeline._tick()
    completed = pipeline.snapshot()
    assert completed["current_cancellation"]["status"] == "complete"
    assert completed["status"] == "cancelled" and completed["active_task_id"] == task_id
    assert flow.calls.count(("cancel-preparation", task_id)) == 1


def test_partial_preparation_cancel_reuses_confirmed_worker_stop(cancellable_pipeline, monkeypatch):
    import threading

    pipeline, flow, _, worker = cancellable_pipeline
    pipeline.start(request_id="begin-partial-cancel")
    drive(pipeline, "filling")
    cancel = flow.cancel_preparation
    stop = worker.cancel_execution
    attempted = []

    def stop_without_application_lock(*args, **kwargs):
        acquired = threading.Event()

        def check_lock():
            with flow.applications.write_lock():
                acquired.set()

        thread = threading.Thread(target=check_lock)
        thread.start()
        try:
            assert acquired.wait(1), (
                "Pipeline must release its application lock before Worker control"
            )
        finally:
            thread.join(timeout=1)
        attempted.append("worker")
        return stop(*args, **kwargs)

    def fail_once(*args, **options):
        if "preparation" not in attempted:
            attempted.append("preparation")
            raise PortalDataError("synthetic_preparation_stop_failed", "Synthetic failure", 409)
        return cancel(*args, **options)

    monkeypatch.setattr(worker, "cancel_execution", stop_without_application_lock)
    monkeypatch.setattr(flow, "cancel_preparation", fail_once)
    payload = {"request_id": "partial-cancel"}
    result = pipeline.cancel_current(**payload)
    assert result["current_cancellation"]["status"] == "partial"
    assert result["current_cancellation"]["worker_status"] == "stopped"
    assert worker.store.load()["jobs"][0]["status"] == "cancelled"
    completed = pipeline.cancel_current(**payload)
    assert completed["current_cancellation"]["status"] == "complete"
    assert attempted.count("worker") == 1
    before = deepcopy(flow.calls)
    assert pipeline.cancel_current(**payload) == completed
    assert flow.calls == before


def test_continue_cannot_revive_a_cancelled_current_job(cancellable_pipeline):
    pipeline, _, _, worker = cancellable_pipeline
    pipeline.start(request_id="begin-no-revive")
    drive(pipeline, "filling")
    pipeline.cancel_current(request_id="cancel-no-revive")
    before = worker.store.path.read_bytes()
    with pytest.raises(PortalDataError) as error:
        pipeline.continue_current(request_id="continue-cancelled")
    assert error.value.code == "pipeline_current_cancelled"
    assert worker.store.path.read_bytes() == before


def test_worker_cancel_failure_does_not_hide_successful_preparation_stop(
    cancellable_pipeline, monkeypatch
):
    pipeline, flow, _, worker = cancellable_pipeline
    pipeline.start(request_id="begin-worker-failure")
    current = drive(pipeline, "filling")

    def fail(*_a, **_k):
        raise PortalDataError("synthetic_worker_stop_failed", "Synthetic failure", 409)

    monkeypatch.setattr(worker, "cancel_execution", fail)
    result = pipeline.cancel_current(request_id="cancel-worker-failure")
    receipt = result["current_cancellation"]
    assert receipt["status"] == "partial" and receipt["worker_status"] == "unknown"
    assert receipt["worker_error"] == "synthetic_worker_stop_failed"
    assert receipt["preparation_status"] == "cancelled"
    assert flow.tasks[current["active_task_id"]]["status"] == "cancelled"
    assert result["control"] == "paused" and result["status"] == "needs_recheck"
    assert result["active_task_id"] == current["active_task_id"]


def test_stale_execution_binding_still_cancels_only_the_original_preparation(cancellable_pipeline):
    pipeline, flow, _, worker = cancellable_pipeline
    pipeline.start(request_id="begin-stale-worker")
    current = drive(pipeline, "filling")
    state = worker.store.load()
    state["batch_id"] = "f" * 32
    worker.store.save(state)
    before = worker.store.path.read_bytes()
    result = pipeline.cancel_current(request_id="cancel-stale-worker")
    assert result["current_cancellation"]["status"] == "partial"
    assert result["current_cancellation"]["worker_error"] == "worker_execution_changed"
    assert result["current_cancellation"]["preparation_status"] == "cancelled"
    assert flow.tasks[current["active_task_id"]]["status"] == "cancelled"
    assert worker.store.path.read_bytes() == before


def test_cancel_recovers_a_published_worker_before_the_flow_reference_was_saved(
    application, tmp_path, monkeypatch
):
    import base64

    from test_application_flow import wait_for

    applications, original = application
    job = applications.update_application(
        original["id"],
        {"url": "https://jobs.lever.co/synthetic/00000000-0000-0000-0000-000000000001"},
        original["revision"],
    )

    def publish_then_fail(task, country):
        worker.request(
            "prepare",
            {
                "workflow": "single",
                "send_confirmed": True,
                "jobs": [
                    {
                        "application_id": job["id"],
                        "revision": job["revision"],
                        "country": country,
                        "filename": "synthetic.pdf",
                        "file_base64": base64.b64encode(b"%PDF-1.4 synthetic").decode(),
                        "single_binding": {"task_id": task["id"]},
                    }
                ],
            },
        )
        raise OSError("Synthetic publication acknowledgement lost")

    flow = ApplicationFlowService(
        applications,
        tmp_path / "flow",
        callbacks={
            "analysis": lambda _: {"id": "analysis", "requirements": []},
            "resume": lambda _: {"id": "resume", "pdf_sha256": "b" * 64},
            "prepare_worker": publish_then_fail,
        },
    )
    worker = WorkerService(
        applications,
        tmp_path / "worker",
        live=True,
        single_flow_root=flow.root,
        single_career_root=tmp_path / "career",
        single_validator=lambda *_a, **_k: None,
    )
    monkeypatch.setattr(worker, "spawn", lambda: None)
    intake = SimpleNamespace(snapshot=lambda: {"recommendations": [], "status": "idle"})
    pipeline = ApplicationPipeline(flow, intake, worker, interval=100)
    try:
        task = flow.create(job["id"], job["revision"])
        for stage, ready in (("analysis", "analysis_ready"), ("resume", "resume_ready")):
            flow.start(task["id"], task["revision"], stage)
            task = wait_for(flow, task["id"], lambda row, ready=ready: row["status"] == ready)
        task = flow.confirm_materials(task["id"], task["revision"], "resume", "b" * 64)
        with pytest.raises(OSError):
            flow.prepare_worker(task["id"], task["revision"], "CHE", True)
        task = flow.task_snapshot(task["id"])
        assert task["worker_ref"] is None and task["worker_preparation"]["status"] == "pending"
        result = pipeline.cancel_current(
            task["id"], task["revision"], request_id="cancel-lost-bind"
        )
        assert result["current_cancellation"]["status"] == "complete"
        saved = flow.task_snapshot(task["id"])
        assert saved["status"] == "cancelled"
        assert saved["worker_ref"]["batch_id"] == worker.store.load()["batch_id"]
        assert saved["worker_preparation"]["status"] == "complete"
        assert worker.store.load()["jobs"][0]["status"] == "cancelled"
    finally:
        pipeline.close()
        flow.close()
