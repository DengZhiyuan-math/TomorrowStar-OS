"""Preparation is persisted before publishing a current Worker job."""

import pytest
from test_application_resume import task_resume as task_resume
from test_bound_material_update import bound_pipeline as bound_pipeline
from test_full_latex_generation import full_latex as full_latex


@pytest.mark.parametrize(
    "bound_pipeline,manual",
    [({"application_strategy": "manual", "stop_at": "needs_input"}, True), ({}, False)],
    indirect=["bound_pipeline"],
)
def test_the_original_worker_is_published_with_its_precision_write_boundary(bound_pipeline, manual):
    server, _store, _calls = bound_pipeline
    worker, pipeline, flow = (
        server.worker_service,
        server.application_pipeline_service,
        server.application_flow_service,
    )
    state = worker.store.load()
    assert len(state["jobs"]) == 1
    job = state["jobs"][0]
    task = flow.snapshot()["active_task"]
    assert not job["page_open"] and not job["intent"]
    assert pipeline.snapshot().get("wait_reason") != "precision_adjustment"
    if manual:
        assert job["precision_preparation"]["status"] == "preparing"
        assert job["precision_preparation"]["task_id"] == task["id"]
        assert (
            job["precision_preparation"]["authorization_id"]
            == pipeline.snapshot()["authorization"]["id"]
        )
    else:
        assert "precision_preparation" not in job
    assert task["send_approval"]["human_reviewed"] is False
    worker.store.check_single(job, state)
