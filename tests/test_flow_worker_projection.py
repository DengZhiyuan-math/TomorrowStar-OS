"""Worker page observations are derived without revising Flow material records."""

import json
from copy import deepcopy

import pytest
from test_worker_backend_recovery import backend as backend

from career_evidence_graph.application_flow_store import assemble, read_flow_state
from career_evidence_graph.application_worker import digest


def test_reopen_ignores_legacy_page_copy_without_revising_completed_flow(backend):
    owner, reopen, runner, page = backend
    flow = owner.application_flow_service
    state = read_flow_state(flow.path.parent)
    task = state["tasks"][0]
    task.update(status="filling")
    task["worker_ref"].update(status="filling", reason="stale copied reason")
    task["revision"] = digest({key: value for key, value in task.items() if key != "revision"})
    owner.server_close()
    flow.path.write_text(json.dumps(state))
    before = flow.path.read_bytes()
    worker_before = deepcopy(runner.store.load())
    current = reopen()
    observed = current.application_flow_service.snapshot(task["id"])["active_task"]
    assert flow.path.read_bytes() == before
    assert observed["revision"] == task["revision"]
    assert observed["status"] == "filling"
    assert observed["worker_ref"]["reason"] == worker_before["jobs"][0]["reason"]
    assert observed["stages"] == task["stages"]
    assert runner.pages[task["application_id"]] is page
    assert runner.store.load()["jobs"] == worker_before["jobs"]


def test_worker_reads_and_explicit_pause_do_not_write_page_copies_to_flow(backend):
    owner, _reopen, runner, page = backend
    flow, worker = owner.application_flow_service, owner.worker_service
    persisted = read_flow_state(flow.path.parent)["tasks"][0]
    assert persisted["status"] == "materials_ready"
    assert persisted["worker_ref"] == {
        "batch_id": worker.store.load()["batch_id"],
        "job_id": persisted["application_id"],
    }
    before = flow.path.read_bytes()
    current = worker.store.load()
    job = current["jobs"][0]
    job.update(status="needs_input", reason="missing_current_answer")
    job["manual_fields"] = {"cover": "Human entered text"}
    worker.store.save(current)
    observed = flow.snapshot(persisted["id"])["active_task"]
    assert observed["status"] == "needs_input"
    assert observed["worker_ref"]["reason"] == "missing_current_answer"
    assert observed["revision"] == persisted["revision"]
    assert flow.path.read_bytes() == before
    receipt = flow.observe_worker(observed["id"], observed["revision"], observed["worker_ref"])
    assert receipt == observed
    assert flow.path.read_bytes() == before
    paused = flow.worker_action(
        observed["id"], observed["revision"], "pause", {"controller": current["controller"]}
    )
    assert paused["revision"] == observed["revision"]
    assert paused["worker_ref"]["status"] == worker.store.load()["jobs"][0]["status"]
    assert flow.path.read_bytes() == before
    assert runner.pages[persisted["application_id"]] is page
    assert worker.store.load()["jobs"][0]["manual_fields"] == {"cover": "Human entered text"}


def test_http_observation_tracks_worker_without_writing_flow(backend):
    from threading import Thread

    from test_career_portal_http import Portal

    owner, _reopen, runner, page = backend
    flow, worker = owner.application_flow_service, owner.worker_service
    before = flow.path.read_bytes()
    task = assemble(flow.root, json.loads(before))["tasks"][0]
    state = worker.store.load()
    state["jobs"][0].update(status="ready_for_review", reason="final_submit_manual")
    worker.store.save(state)
    portal = Portal(owner, flow.applications.root, runner.store.root.parent / "career")
    thread = Thread(target=owner.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True)
    thread.start()
    try:
        for _ in range(2):
            status, _, raw = portal.request("GET", "/api/flow/state")
            assert status == 200, raw
            observed = json.loads(raw)
            assert observed["active_task"]["status"] == "ready_for_review"
            assert observed["active_task"]["worker_ref"]["reason"] == "final_submit_manual"
            assert observed["active_task"]["revision"] == task["revision"]
            assert observed["worker"]["jobs"][0]["status"] == "ready_for_review"
            assert flow.path.read_bytes() == before
        assert runner.pages[task["application_id"]] is page
    finally:
        owner.shutdown()
        thread.join(3)


@pytest.mark.parametrize("copied_status", ["needs_recheck", "ready_for_review"])
def test_worker_ready_does_not_hide_material_update_needing_recheck(backend, copied_status):
    owner, _reopen, _runner, _page = backend
    flow, worker = owner.application_flow_service, owner.worker_service
    state = read_flow_state(flow.path.parent)
    task = state["tasks"][0]
    task.update(
        status=copied_status,
        material_update={"status": "needs_recheck", "error_code": "retained_material_unknown"},
    )
    task["revision"] = digest({key: value for key, value in task.items() if key != "revision"})
    flow.path.write_text(json.dumps(state))
    before = flow.path.read_bytes()
    worker_state = worker.store.load()
    worker_state["jobs"][0].update(status="ready_for_review", reason="final_submit_manual")
    worker.store.save(worker_state)
    observed = flow.snapshot(task["id"])["active_task"]
    assert observed["status"] == "needs_recheck"
    assert observed["worker_ref"]["status"] == "ready_for_review"
    assert observed["material_update"] == task["material_update"]
    assert observed["revision"] == task["revision"]
    assert flow.path.read_bytes() == before


@pytest.mark.parametrize("missing", ["batch_id", "job_id", "both"])
def test_incomplete_worker_reference_is_read_only_and_unavailable(backend, missing):
    from threading import Thread

    from test_career_portal_http import Portal

    owner, _reopen, runner, _page = backend
    flow, worker = owner.application_flow_service, owner.worker_service
    state = read_flow_state(flow.path.parent)
    task = state["tasks"][0]
    if missing == "both":
        task["worker_ref"] = {"status": "filling"}
    else:
        task["worker_ref"].pop(missing)
    task["revision"] = digest({key: value for key, value in task.items() if key != "revision"})
    flow.path.write_text(json.dumps(state))
    before = flow.path.read_bytes()
    worker_before = worker.store.load()
    observed = flow.snapshot(task["id"])["active_task"]
    assert observed["status"] == "needs_recheck"
    assert observed["worker_ref"]["reason"] == "flow_worker_mismatch"
    for key in ("batch_id", "job_id"):
        assert observed["worker_ref"].get(key) == task["worker_ref"].get(key)
    portal = Portal(owner, flow.applications.root, runner.store.root.parent / "career")
    thread = Thread(target=owner.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True)
    thread.start()
    try:
        status, _, raw = portal.request("GET", "/api/flow/state")
        assert status == 200, raw
        shown = json.loads(raw)
        assert shown["worker"]["enabled"] is False
        assert shown["worker"]["error"] == "flow_worker_mismatch"
        assert shown["active_task"]["revision"] == task["revision"]
        assert flow.path.read_bytes() == before
        assert worker.store.load()["jobs"] == worker_before["jobs"]
    finally:
        owner.shutdown()
        thread.join(3)
