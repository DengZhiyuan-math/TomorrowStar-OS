"""An interrupted local journal converges before strict information reads."""

import fcntl
import json
import os
import time
from copy import deepcopy
from uuid import uuid4

import pytest
from test_application_resume import task_resume as task_resume
from test_bound_material_update import bound_pipeline as bound_pipeline
from test_bound_material_update import request_material_update
from test_full_latex_generation import full_latex as full_latex

from career_evidence_graph._vendor import job_apply_store as helper
from career_evidence_graph.application_worker import start_run
from career_evidence_graph.career_portal_data import PortalDataError
from career_evidence_graph.validation.hashing import record_digest as digest


@pytest.fixture
def interrupted_commit(bound_pipeline, monkeypatch):
    server, store, calls = bound_pipeline
    flow, worker, pipeline = (
        server.application_flow_service,
        server.worker_service,
        server.application_pipeline_service,
    )
    run_id = start_run(worker.store)
    descriptor = os.open(worker.store.root / ".worker.lock", os.O_CREAT | os.O_RDWR, 0o600)
    fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
    worker.store.worker_lock_descriptor = descriptor
    try:
        pipeline.pause()
        current = worker.store.load()
        job = current["jobs"][0]
        job.update(
            page_open=True,
            status="ready_for_review",
            reason="final_submit_manual",
            page_observation={"run_id": run_id, "page_id": "retained-page", "at": time.time()},
        )
        worker.store.save(current)
        request_material_update(flow)
        pipeline.continue_current(request_id="prepare-before-local-crash")
        deadline = time.monotonic() + 3
        while True:
            task = flow.snapshot()["active_task"]
            if task.get("material_update", {}).get("status") != "preparing":
                break
            assert time.monotonic() < deadline
            time.sleep(0.01)
        assert task["material_update"]["status"] == "awaiting_page"
        candidate = deepcopy(task["material_update"]["candidate"])
        pipeline._tick()
        current = worker.store.load()
        job = current["jobs"][0]
        assert job["material_update"]["status"] == "inspect_pending"
        info = os.fstat(descriptor)
        job["material_update"].update(
            status="page_verified",
            page_receipt={
                "run_id": run_id,
                "page_id": "retained-page",
                "worker_lock": {"device": info.st_dev, "inode": info.st_ino},
            },
        )
        worker.store.save(current)
        original_save = flow._save
        interrupted = []

        def save_then_crash(state):
            original_save(state)
            if (
                any(
                    row.get("material_update", {}).get("status") == "committing"
                    for row in state["tasks"]
                )
                and not interrupted
            ):
                interrupted.append(True)
                raise OSError("synthetic crash after Flow material adoption")

        monkeypatch.setattr(flow, "_save", save_then_crash)
        with pytest.raises(OSError, match="after Flow"):
            pipeline._tick()
        monkeypatch.setattr(flow, "_save", original_save)
        assert interrupted
        with pytest.raises(PortalDataError) as blocked:
            worker.snapshot()
        assert blocked.value.code == "single_information_invalid"
        task = flow.snapshot()["active_task"]
        assert task["resume_id"] == candidate["resume_id"]
        assert (
            worker.store.load()["jobs"][0]["single_binding"]["resume_id"] != candidate["resume_id"]
        )
        path = flow.root / "material-updates" / (task["material_update"]["id"] + ".json")
        yield server, store, calls, candidate, path
    finally:
        os.close(descriptor)


def test_public_continue_recovers_exact_journal_before_strict_snapshot(
    interrupted_commit, monkeypatch
):
    server, store, calls, candidate, path = interrupted_commit
    flow, worker, pipeline = (
        server.application_flow_service,
        server.worker_service,
        server.application_pipeline_service,
    )
    before = worker.store.load()
    compiles, writes = len(store.prism_client.calls), len(calls)
    monkeypatch.setitem(
        flow.callbacks,
        "bound_material_candidate",
        lambda *_: pytest.fail("Recovery must reuse the saved candidate"),
    )
    pipeline.pause()
    state = pipeline.continue_current(request_id="recover-existing-local-journal")
    assert state["status"] == "continuing_worker" and state["control"] == "running"
    current = worker.snapshot()
    job = current["jobs"][0]
    worker.store.check_single(job, current)
    assert job["single_binding"]["resume_id"] == candidate["resume_id"]
    assert job["file_sha256"] == candidate["resume_sha256"]
    assert job["material_update"]["status"] == "bound"
    assert flow.snapshot()["active_task"]["material_update"]["status"] == "bound"
    assert json.loads(path.read_text())["status"] == "bound"
    assert current["control"] == "paused" and current["commands"] == before["commands"]
    assert (len(store.prism_client.calls), len(calls)) == (compiles, writes)


@pytest.mark.parametrize("change", ["none", "other_owner", "other_batch"])
def test_pause_partial_commit_uses_owned_control_without_library_or_actions(
    interrupted_commit, monkeypatch, change
):
    server, _, _, _, _ = interrupted_commit
    flow, worker, pipeline = (
        server.application_flow_service,
        server.worker_service,
        server.application_pipeline_service,
    )
    current = worker.store.load()
    if change != "none":
        current["control"] = "running"
        current["controller" if change == "other_owner" else "batch_id"] = "other-owner-or-batch"
        worker.store.save(current)
    with monkeypatch.context() as guards:
        guards.setattr(
            worker, "snapshot", lambda: pytest.fail("Pause must not read the information library")
        )
        guards.setattr(
            flow,
            "worker_action",
            lambda *_args, **_kwargs: pytest.fail(
                "This paused or foreign Worker must not receive an action"
            ),
        )
        state = pipeline.pause()
    assert state["control"] == "paused"
    assert worker.store.load() == current


@pytest.mark.parametrize("fault", ["conflict", "cancelled", "other_task", "unknown_journal"])
def test_journal_recovery_rejects_nonexact_or_cancelled_state(
    interrupted_commit, monkeypatch, fault
):
    server, store, calls, _, path = interrupted_commit
    flow, worker, pipeline = (
        server.application_flow_service,
        server.worker_service,
        server.application_pipeline_service,
    )
    if fault in {"conflict", "cancelled"}:
        current = worker.store.load()
        current["jobs"][0]["filename" if fault == "conflict" else "status"] = (
            "different.pdf" if fault == "conflict" else "cancelled"
        )
        worker.store.save(current)
    else:
        journal = json.loads(path.read_text())
        journal["task_id" if fault == "other_task" else "status"] = (
            "another-task" if fault == "other_task" else "unknown"
        )
        journal["revision"] = digest(
            {key: value for key, value in journal.items() if key != "revision"}
        )
        helper.atomic_write_json(path, journal)
    before = (flow.path.read_bytes(), worker.store.path.read_bytes(), path.read_bytes())
    compiles, writes = len(store.prism_client.calls), len(calls)
    monkeypatch.setitem(
        flow.callbacks,
        "bound_material_candidate",
        lambda *_: pytest.fail("A bad journal cannot create another candidate"),
    )
    pipeline.pause()
    with pytest.raises(PortalDataError):
        pipeline.continue_current(request_id="reject-" + fault)
    state = pipeline.snapshot()
    assert state["control"] == "paused" and state["status"] == "needs_recheck"
    assert (flow.path.read_bytes(), worker.store.path.read_bytes(), path.read_bytes()) == before
    assert (len(store.prism_client.calls), len(calls)) == (compiles, writes)


def test_completed_explicit_edit_does_not_repeat_material_work_on_continue(
    bound_pipeline, monkeypatch
):
    server, store, calls = bound_pipeline
    flow, worker, pipeline = (
        server.application_flow_service,
        server.worker_service,
        server.application_pipeline_service,
    )
    with flow.applications.write_lock():
        state = flow._load()
        task = flow._task(state, pipeline.snapshot()["active_task_id"])
        # Replay the retained record of an explicit edit that already completed.
        task["material_update"] = {
            "id": uuid4().hex,
            "status": "complete",
            "explicit_source": True,
            "inputs": deepcopy(task["inputs"]),
            "old": deepcopy(task),
            "created_at": time.time(),
        }
        task["status"] = "needs_recheck"
        flow._save(state)
        retained = deepcopy(task)
    before = (len(store.prism_client.calls), len(calls))
    actions = []
    with monkeypatch.context() as guards:
        guards.setattr(flow, "worker_action", lambda *args: actions.append(args))
        result = pipeline.continue_current(request_id="continue-after-completed-edit")
        pipeline.continue_current(request_id="continue-after-completed-edit")
    assert result["status"] == "continuing_worker"
    assert [args[2] for args in actions] == ["continue-current"]
    assert flow.task_snapshot(retained["id"])["material_update"] == retained["material_update"]
    assert (len(store.prism_client.calls), len(calls)) == before
    assert worker.store.load()["control"] == "running"


def test_each_new_explicit_edit_still_starts_one_distinct_update(bound_pipeline, monkeypatch):
    server, store, calls = bound_pipeline
    flow, pipeline = server.application_flow_service, server.application_pipeline_service
    pipeline.pause()
    task_id = pipeline.snapshot()["active_task_id"]
    queued, prepared, identifiers = [], [], []
    with monkeypatch.context() as guards:
        guards.setattr(flow._queue, "put", queued.append)

        def prepare(task):
            prepared.append(task["material_update"]["id"])
            return {
                "id": "e" * 32,
                "draft_sha256": "f" * 64,
                "source_checkpoint": deepcopy(task["source_checkpoint"]),
                "task_inputs": deepcopy(task["inputs"]),
                "base_checkpoint": deepcopy(task["base_checkpoint"]),
            }

        guards.setitem(flow.callbacks, "bound_edit_prepare", prepare)
        guards.setitem(
            flow.callbacks,
            "automatic_source_save",
            lambda task, _text: {
                "id": task["draft_id"],
                "draft_sha256": task["draft_sha256"],
                "source_checkpoint": deepcopy(task["source_checkpoint"]),
                "task_inputs": deepcopy(task["inputs"]),
                "base_checkpoint": deepcopy(task["base_checkpoint"]),
            },
        )
        for number in range(2):
            task = flow.task_snapshot(task_id)
            task = flow.begin_automatic_edit(task_id, task["revision"])
            update = task["material_update"]
            flow.save_automatic_source(
                task_id,
                task["revision"],
                update["editable_draft"]["source_checkpoint"]["source_revision"],
                f"Synthetic explicit edit {number}",
            )
            assert flow.begin_material_update(task_id, f"new-explicit-{number}")
            assert flow.begin_material_update(task_id, f"same-inflight-{number}")
            with flow.applications.write_lock():
                state = flow._load()
                task = flow._task(state, task_id)
                identifiers.append(task["material_update"]["id"])
                task["material_update"]["status"] = "complete"
                flow._save(state)
    assert len(set(identifiers)) == 2 and prepared == identifiers
    assert [item[2] for item in queued] == identifiers
    assert len(store.prism_client.calls) == 1 and len(calls) == 1


def test_continue_after_edit_reuses_original_journal_and_page(interrupted_commit, monkeypatch):
    server, store, calls, candidate, path = interrupted_commit
    flow, worker, pipeline = (
        server.application_flow_service,
        server.worker_service,
        server.application_pipeline_service,
    )
    task = flow.task_snapshot(pipeline.snapshot()["active_task_id"])
    journal = json.loads(path.read_text())
    old_binding = deepcopy(worker.store.load()["jobs"][0]["single_binding"])
    monkeypatch.setitem(
        flow.callbacks,
        "bound_material_candidate",
        lambda *_: pytest.fail("Continue after an edit must reuse the saved candidate"),
    )
    gate = pipeline.begin_material_edit(task["id"], task["revision"], request_id="edit-confirm")
    assert gate == {"edit_gate": "ready"}
    confirmed = pipeline.snapshot()["material_edit_gate"]
    assert confirmed["page_id"] == "retained-page" and confirmed["task_id"] == task["id"]
    # Until Continue adopts it, the old Worker binding stays the bound one.
    assert worker.store.load()["jobs"][0]["single_binding"] == old_binding
    state = pipeline.continue_current(request_id="continue-after-confirmed-edit")
    assert state["status"] == "continuing_worker" and "material_edit_gate" not in state
    assert state["material_update_id"] == journal["id"]
    current = worker.snapshot()
    job = current["jobs"][0]
    assert job["single_binding"]["resume_id"] == candidate["resume_id"]
    assert job["page_observation"]["page_id"] == "retained-page"
    assert json.loads(path.read_text())["id"] == journal["id"]
    assert sorted(path.parent.iterdir()) == [path]
