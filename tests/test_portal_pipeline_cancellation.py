"""Existing App HTTP cancellation uses the owning Pipeline coordinator."""

import json
from threading import Thread

import pytest
from test_career_portal_http import Portal
from test_worker_backend_recovery import backend as backend


@pytest.mark.parametrize("unknown_effect", [False, True])
def test_legacy_flow_cancel_cancels_execution_and_preparation_through_pipeline(
    backend, tmp_path, unknown_effect
):
    owner, _, _, _ = backend
    pipeline = owner.application_pipeline_service
    flow = owner.application_flow_service
    task = flow.task_snapshot(pipeline.snapshot()["active_task_id"])
    if unknown_effect:
        state = owner.worker_service.store.load()
        state["jobs"][0]["intent"] = {"action": "upload", "attempt_id": "unresolved-before-cancel"}
        owner.worker_service.store.save(state)
    client = Portal(owner, owner.worker_service.store.applications.root, tmp_path / "career")
    thread = Thread(target=owner.serve_forever, daemon=True)
    thread.start()
    try:
        status, _, raw = client.request(
            "POST",
            "/api/flow/cancel",
            body=json.dumps({"task_id": task["id"], "task_revision": task["revision"]}).encode(),
            headers=client.write_headers(),
        )
        assert status == 200, raw
        response = json.loads(raw)
        assert response["status"] == "cancelled"
        assert response["cancellation"]["status"] == ("partial" if unknown_effect else "complete")
        assert owner.worker_service.store.load()["jobs"][0]["status"] == "cancelled"
        assert flow.task_snapshot(task["id"])["status"] == "cancelled"
        assert pipeline.snapshot()["current_cancellation"]["status"] == (
            "partial" if unknown_effect else "complete"
        )
        assert pipeline.snapshot()["active_task_id"] == task["id"]
    finally:
        owner.shutdown()
        thread.join(timeout=2)
