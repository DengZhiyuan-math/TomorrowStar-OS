"""A cancelled preparation keeps late source evidence without starting a build."""

import time
from copy import deepcopy

import pytest
from test_application_flow import wait_for
from test_application_resume import task_resume as task_resume
from test_bound_material_update import bound_pipeline as bound_pipeline
from test_full_latex_generation import full_latex as full_latex

from career_evidence_graph.application_information import put_information_answer
from career_evidence_graph.application_worker import start_run


def test_cancel_after_retained_draft_prevents_build_and_keeps_unadopted_source(
    bound_pipeline, monkeypatch
):
    server, store, _calls = bound_pipeline
    flow, worker, pipeline = (
        server.application_flow_service,
        server.worker_service,
        server.application_pipeline_service,
    )
    start_run(worker.store)
    pipeline.pause()
    original = flow.snapshot()["active_task"]
    compiles = len(store.prism_client.calls)
    material_prepare = flow.callbacks["bound_resume_draft"]
    returned = []

    def cancel_after_draft(task):
        result = material_prepare(task)
        returned.append(result[0])
        current = flow.task_snapshot(task["id"])
        flow.cancel_preparation(current["id"], current["revision"])
        return result

    monkeypatch.setitem(flow.callbacks, "bound_resume_draft", cancel_after_draft)
    put_information_answer(
        worker.store.answers,
        {
            "question": "Email",
            "value": "updated@example.invalid",
            "state": "confirmed",
            "scope": {},
        },
    )
    pipeline.continue_current(request_id="cancel-before-candidate-export")
    task = wait_for(
        flow,
        original["id"],
        lambda row: row.get("material_update", {}).get("status") != "preparing",
    )
    assert len(returned) == 1
    assert task["status"] == "cancelled"
    assert task["resume_id"] == original["resume_id"]
    assert task["draft_id"] == original["draft_id"]
    assert len(store.prism_client.calls) == compiles
    assert store.read(returned[0]["id"]) == returned[0]
    retained = [row for row in task["artifacts"] if row["result"].get("id") == returned[0]["id"]]
    assert len(retained) == 1
    assert retained[0]["adopted"] is False


@pytest.mark.parametrize("bound_pipeline", [{"stop_at": "generating_resume"}], indirect=True)
def test_default_queue_prepares_and_starts_one_execution_through_its_owner(
    bound_pipeline, monkeypatch
):
    server, _store, _calls = bound_pipeline
    flow, worker, pipeline = (
        server.application_flow_service,
        server.worker_service,
        server.application_pipeline_service,
    )
    prepare, control = worker.prepare_execution, worker.control_execution
    preparations, controls = [], []

    def prepare_execution(application_id, revision, binding, **kwargs):
        preparations.append((application_id, deepcopy(binding)))
        return prepare(application_id, revision, binding, **kwargs)

    def control_execution(reference, operation, payload):
        controls.append((deepcopy(reference), operation))
        return control(reference, operation, payload)

    monkeypatch.setattr(worker, "prepare_execution", prepare_execution)
    monkeypatch.setattr(worker, "control_execution", control_execution)
    deadline = time.monotonic() + 5
    while pipeline.snapshot()["status"] != "filling":
        pipeline._tick()
        assert time.monotonic() < deadline, pipeline.snapshot()
        time.sleep(0.01)
    current = pipeline.snapshot()
    progress = flow.progress(current["active_task_id"])
    task = progress["task"]
    assert len(preparations) == 1
    application_id, binding = preparations[0]
    assert application_id == task["application_id"]
    assert binding["task_id"] == task["id"]
    assert binding["resume_id"] == task["resume_id"]
    assert binding["resume_sha256"] == task["resume_sha256"]
    assert binding["inputs"] == task["inputs"]
    assert [operation for _, operation in controls] == ["resume"]
    assert controls[0][0]["task_id"] == task["id"]
    assert len(worker.store.load()["jobs"]) == 1
    assert set(task["worker_ref"]) == {"batch_id", "job_id"}
    assert progress["status"] == "ready"
    assert progress["execution_ref"] == task["worker_ref"]
