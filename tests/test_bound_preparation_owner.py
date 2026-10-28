"""Bound preparation preserves cancellation and its original material candidate."""

import threading

import pytest
from test_application_resume import task_resume as task_resume
from test_bound_material_update import bound_pipeline as bound_pipeline
from test_full_latex_generation import full_latex as full_latex

from career_evidence_graph.application_flow import ApplicationFlowService
from career_evidence_graph.application_information import put_information_answer
from career_evidence_graph.application_worker import start_run
from career_evidence_graph.career_portal_data import PortalDataError


@pytest.fixture
def queued_bound_preparation(bound_pipeline, monkeypatch):
    server, store, calls = bound_pipeline
    flow, worker, pipeline = (
        server.application_flow_service,
        server.worker_service,
        server.application_pipeline_service,
    )
    start_run(worker.store)
    pipeline.pause()
    original = flow.task_snapshot(pipeline.snapshot()["active_task_id"])
    put_information_answer(
        worker.store.answers,
        {
            "question": "Email",
            "value": "updated@example.invalid",
            "state": "confirmed",
            "scope": {},
        },
    )
    queued = []
    put, get = flow._queue.put, flow._queue.get
    monkeypatch.setattr(
        flow._queue, "put", lambda item: put(item) if item is None else queued.append(item)
    )
    assert flow.begin_material_update(original["id"], "reserved-bound-preparation")
    assert len(queued) == 1 and queued[0][1] == "bound-material"

    def dispatch():
        """Release the held item to Flow's own run loop and wait until it asks for more."""
        idle = threading.Event()

        def next_item(*args, **kwargs):
            idle.set()
            return get(*args, **kwargs)

        monkeypatch.setattr(flow._queue, "get", next_item)
        put(queued[0])
        assert idle.wait(30)

    return flow, worker, store, calls, original, dispatch


def test_cancelled_queued_candidate_does_not_dispatch_material_work(
    queued_bound_preparation, monkeypatch
):
    flow, worker, store, calls, original, dispatch = queued_bound_preparation
    dispatched = []

    def unexpected(request):
        dispatched.append(request["id"])
        raise PortalDataError("synthetic_material_stop", "No material work should start", 409)

    monkeypatch.setitem(flow.callbacks, "bound_material_candidate", unexpected)
    current = flow.task_snapshot(original["id"])
    flow.cancel_preparation(current["id"], current["revision"])
    before_worker = worker.store.path.read_bytes()
    before_calls = len(calls), len(store.prism_client.calls)
    dispatch()
    current = flow.task_snapshot(original["id"])
    assert dispatched == []
    assert current["status"] == "cancelled"
    assert current["resume_id"] == original["resume_id"]
    assert current["material_update"]["status"] != "awaiting_page"
    assert worker.store.path.read_bytes() == before_worker
    assert (len(calls), len(store.prism_client.calls)) == before_calls
    before_flow = flow.path.read_bytes()
    with pytest.raises(PortalDataError) as rejected:
        flow.begin_material_update(original["id"], "cannot-revive-cancelled-preparation")
    assert rejected.value.code == "flow_cancelled"
    assert flow.path.read_bytes() == before_flow


@pytest.mark.parametrize("interruption", ["cancel", "worker_resume"])
def test_cancel_during_candidate_preparation_retains_result_without_adoption(
    queued_bound_preparation, monkeypatch, interruption
):
    flow, worker, store, _calls, original, dispatch = queued_bound_preparation
    prepare = flow.callbacks["bound_material_candidate"]
    completed = []
    worker_after_interrupt = []

    def finish_after_cancel(request):
        result = prepare(request)
        completed.append(result)
        if interruption == "cancel":
            current = flow.task_snapshot(original["id"])
            flow.cancel_preparation(current["id"], current["revision"])
        else:
            state = worker.store.load()
            state["control"] = "running"
            worker.store.save(state)
        worker_after_interrupt.append(worker.store.path.read_bytes())
        return result

    monkeypatch.setitem(flow.callbacks, "bound_material_candidate", finish_after_cancel)
    dispatch()
    current = flow.task_snapshot(original["id"])
    candidate = completed[0]
    assert current["status"] == ("cancelled" if interruption == "cancel" else "needs_recheck")
    assert current["material_update"]["status"] == "needs_recheck"
    assert current["material_update"]["candidate"]["resume_id"] == candidate["resume_id"]
    assert current["resume_id"] == original["resume_id"]
    assert store.read_pdf(candidate["resume_id"])["pdf_sha256"] == candidate["resume_sha256"]
    artifact = next(
        row for row in current["artifacts"] if row["result"].get("id") == candidate["resume_id"]
    )
    assert artifact["adopted"] is False
    assert worker.store.path.read_bytes() == worker_after_interrupt[0]


@pytest.mark.parametrize("changed", ["worker", "inputs"])
def test_queued_candidate_rechecks_current_permission_and_inputs_before_dispatch(
    queued_bound_preparation, monkeypatch, changed
):
    flow, worker, _store, _calls, original, dispatch = queued_bound_preparation
    dispatched = []

    def unexpected(request):
        dispatched.append(request["id"])
        raise PortalDataError(
            "synthetic_material_stop", "Worker no longer permits preparation", 409
        )

    monkeypatch.setitem(flow.callbacks, "bound_material_candidate", unexpected)
    if changed == "worker":
        state = worker.store.load()
        state["control"] = "running"
        worker.store.save(state)
    else:
        put_information_answer(
            worker.store.answers,
            {
                "question": "Email",
                "value": "newer@example.invalid",
                "state": "confirmed",
                "scope": {},
            },
        )
    before_worker = worker.store.path.read_bytes()
    dispatch()
    current = flow.task_snapshot(original["id"])
    assert dispatched == []
    assert current["material_update"]["status"] == "needs_recheck"
    assert current["material_update"]["error_code"] == (
        "bound_material_pause_required" if changed == "worker" else "bound_material_update_changed"
    )
    assert current["resume_id"] == original["resume_id"]
    assert worker.store.path.read_bytes() == before_worker


@pytest.mark.parametrize("reference", ["same", "application", "task", "batch"])
def test_worker_preparation_permission_is_bound_and_read_only(queued_bound_preparation, reference):
    flow, worker, store, calls, original, _dispatch = queued_bound_preparation
    scope = {
        "application_id": original["application_id"],
        "task_id": original["id"],
        "expected_batch_id": original["worker_ref"]["batch_id"],
    }
    if reference != "same":
        scope[
            {"application": "application_id", "task": "task_id", "batch": "expected_batch_id"}[
                reference
            ]
        ] = "other-reference"
    before = flow.path.read_bytes(), worker.store.path.read_bytes()
    before_calls = len(calls), len(store.prism_client.calls)
    if reference == "same":
        assert worker.check_material_preparation(**scope) is None
    else:
        with pytest.raises(PortalDataError) as rejected:
            worker.check_material_preparation(**scope)
        assert rejected.value.code == "bound_material_pause_required"
    assert (flow.path.read_bytes(), worker.store.path.read_bytes()) == before
    assert (len(calls), len(store.prism_client.calls)) == before_calls


def test_second_flow_cannot_schedule_the_current_bound_preparation(queued_bound_preparation):
    flow, worker, store, calls, original, _dispatch = queued_bound_preparation
    other = ApplicationFlowService(
        flow.applications,
        flow.root,
        callbacks=flow.callbacks,
        input_provider=flow.input_provider,
    )
    before = flow.path.read_bytes(), worker.store.path.read_bytes()
    before_calls = len(calls), len(store.prism_client.calls)
    try:
        with pytest.raises(PortalDataError) as rejected:
            other.begin_material_update(original["id"], "second-controller")
        assert rejected.value.code == "flow_runtime_busy"
        assert (flow.path.read_bytes(), worker.store.path.read_bytes()) == before
        assert (len(calls), len(store.prism_client.calls)) == before_calls
    finally:
        other.close()


def test_invalid_candidate_delivery_remains_local_unknown(queued_bound_preparation, monkeypatch):
    flow, worker, _store, _calls, original, dispatch = queued_bound_preparation
    monkeypatch.setitem(flow.callbacks, "bound_material_candidate", lambda request: {})
    before_worker = worker.store.path.read_bytes()
    dispatch()
    current = flow.task_snapshot(original["id"])
    assert current["material_update"]["status"] == "needs_recheck"
    assert current["material_update"]["error_code"] == "bound_material_prepare_unknown"
    assert current["resume_id"] == original["resume_id"]
    assert worker.store.path.read_bytes() == before_worker
