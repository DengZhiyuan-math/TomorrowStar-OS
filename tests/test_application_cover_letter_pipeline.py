"""Late optional letters retain page ownership without blocking ready materials."""

import threading

import pytest
from test_application_pipeline import advance
from test_application_pipeline import environment as environment

from career_evidence_graph.application_flow import ApplicationFlowService
from career_evidence_graph.career_portal_data import PortalDataError


def test_unknown_optional_author_stops_already_running_page(environment):
    pipeline, flow, _, worker, _ = environment
    pipeline.start(request_id="letter-unknown")
    state = advance(pipeline, "filling")
    identifier = state["active_task_id"]
    flow.tasks[identifier]["cover_letter"] = {"status": "needs_recheck"}
    flow.cover_letter_outcome = lambda task_id: flow.tasks[task_id].get(
        "cover_letter", {"status": "not_started"}
    )
    pipeline._tick()
    stopped = pipeline.snapshot()
    assert stopped["control"] == "paused"
    assert stopped["status"] == "needs_recheck"
    assert stopped["wait_reason"] == "cover_letter_result_unknown"
    assert worker.state["control"] == "paused"
    assert stopped["active_task_id"] == identifier
    assert len(worker.state["jobs"]) == 1


def test_page_ready_retains_authority_until_late_optional_delivery(environment):
    pipeline, flow, _, worker, _ = environment
    pipeline.start(request_id="letter-late")
    state = advance(pipeline, "filling")
    identifier = state["active_task_id"]
    flow.tasks[identifier]["cover_letter"] = {"status": "running"}
    job = worker.state["jobs"][0]
    job.update(
        status="ready_for_review",
        cover_letter_delivery={
            "status": "running",
            "requirement": "optional",
            "selected_fields": [["letter", ""]],
        },
    )
    pipeline._tick()
    ready = pipeline.snapshot()
    assert ready["status"] == "ready_for_review"
    assert ready["control"] == "running"
    assert ready["pending_optional_cover_letter"]
    assert worker.state["control"] == "running"
    assert ("worker_pause", identifier) not in flow.calls
    assert ("worker_review", identifier) not in flow.calls
    # The browser wakes this same page when the independently adopted letter arrives.
    flow.tasks[identifier]["cover_letter"]["status"] = "ready"
    job["status"] = "filling"
    pipeline._tick()
    assert pipeline.snapshot()["status"] == "filling"
    assert not pipeline.snapshot().get("pending_optional_cover_letter")
    job["status"] = "ready_for_review"
    job["cover_letter_delivery"]["status"] = "ready"
    pipeline._tick()
    assert pipeline.snapshot()["status"] == "ready_for_review"
    assert pipeline.snapshot()["control"] == "paused"
    assert worker.state["control"] == "paused"


def test_absent_cover_letter_destination_does_not_delay_ready_page(environment):
    pipeline, flow, _, worker, _ = environment
    pipeline.start(request_id="letter-absent")
    state = advance(pipeline, "filling")
    flow.tasks[state["active_task_id"]]["cover_letter"] = {"status": "running"}
    worker.state["jobs"][0].update(
        status="ready_for_review",
        cover_letter_delivery={"status": "running", "requirement": "none", "selected_fields": []},
    )
    pipeline._tick()
    assert pipeline.snapshot()["status"] == "ready_for_review"
    assert pipeline.snapshot()["control"] == "paused"
    assert not pipeline.snapshot().get("pending_optional_cover_letter")


@pytest.mark.parametrize(
    "action",
    [
        "flow:start-cover-letter",
        "flow:refresh-match",
        "flow:retry-material-consistency",
        "flow:recheck-cover-letter",
        "flow:recheck-material-consistency",
        "flow:recheck-resume-author",
    ],
)
@pytest.mark.parametrize("current,paused", [(False, True), (True, False), (True, True)])
def test_manual_material_author_admission_keeps_current_job_and_paused_control(
    environment, action, current, paused
):
    pipeline, flow, _, _, _ = environment
    pipeline.start(request_id="branch-admission")
    state = advance(pipeline, "filling")
    target = state["active_task_id"] if current else "another-task"
    if paused:
        pipeline.pause()
    flow._runtime_error, flow._owner, flow._closed = "", True, threading.Event()
    with pipeline.manual_entry(action, {"task_id": target}):
        if current and paused:
            ApplicationFlowService._writable(flow)
        else:
            with pytest.raises(PortalDataError) as rejected:
                ApplicationFlowService._writable(flow)
            assert rejected.value.code == "pipeline_current_material_required"
