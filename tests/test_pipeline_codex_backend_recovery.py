"""A reopened Pipeline recovers a lost backend without inventing a second writer."""

from pathlib import Path

import pytest
from test_worker_backend_recovery import backend as backend

from career_evidence_graph import application_worker
from career_evidence_graph.application_pipeline import ApplicationPipeline
from career_evidence_graph.application_worker import WorkerService, mark_assistance_backend_lost


def _reopen_after_loss(backend, monkeypatch, explicit_pause):
    owner, _, runner, original_page = backend
    worker = owner.worker_service
    old_pipeline = owner.application_pipeline_service
    state = worker.store.load()
    job = state["jobs"][0]
    identifier = job["application_id"]
    job["form_state"] = {
        "binding": {
            "run_id": state["runtime"]["id"],
            "page_id": job["page_observation"]["page_id"],
            "document_token": "lost-backend-synthetic-document",
            "step": job["job_url"],
        }
    }
    worker.store.save(state)
    worker.request(
        "request-assistance",
        {
            "application_id": identifier,
            "binding": worker.assistance_context(identifier)["binding"],
            "request_id": "before-ungraceful-exit",
        },
    )
    reference = worker.assistance_context(identifier)["assistance_ref"]
    worker.request(
        "claim-assistance",
        {
            "application_id": identifier,
            "assistance_ref": reference,
            "request_id": "claim-before-exit",
        },
    )
    # Inject the same kernel-identity failure exercised by the real EOF/TERM/KILL cases.
    monkeypatch.setattr(application_worker, "process_identity", lambda _pid: None)
    state = worker.store.load()
    assert mark_assistance_backend_lost(state, reference)
    worker.store.save(state)
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
        request_id=state["jobs"][0]["assistance"]["stop"]["request_id"],
    )
    if explicit_pause:
        worker.request("pause", {"controller": state["controller"]})
    assert "backend_recovery" not in worker.store.load()
    # Model abrupt loss of the scheduler lock without invoking close/suspend/finally.
    old_pipeline._closed.set()
    old_pipeline._thread.join(timeout=1)
    old_pipeline._lock_file.close()
    context = worker.store.single_context()
    reopened_worker = WorkerService(
        worker.store.applications,
        worker.store.root,
        live=True,
        single_flow_root=Path(context["flow_root"]),
        single_career_root=Path(context["career_root"]),
        single_validator=worker.store.single_validator,
    )
    monkeypatch.setattr(reopened_worker, "spawn", lambda: pytest.fail("Must retain original owner"))
    reopened = ApplicationPipeline(old_pipeline.flow, old_pipeline.intake, reopened_worker)
    return reopened, worker, runner, original_page, identifier


@pytest.mark.parametrize("explicit_pause", [False, True])
def test_reopen_without_old_close_receipt_requests_only_original_owner_readback(
    backend, monkeypatch, explicit_pause
):
    reopened, worker, runner, original_page, identifier = _reopen_after_loss(
        backend, monkeypatch, explicit_pause
    )
    try:
        reopened._tick()
        after = reopened.snapshot()
        saved = worker.store.load()
        if explicit_pause:
            assert after["status"] == "needs_recheck"
            assert saved.get("commands") == []
            assert "backend_recovery" not in saved
        else:
            assert after["status"] == "recovering_worker"
            assert after["backend_recovery_id"] == saved["backend_recovery"]["request_id"]
            assert saved["backend_recovery"]["status"] in {"suspended", "pending"}
            assert saved["backend_recovery"]["binding"]["runtime"]["id"] == runner.run_id
        assert saved["control"] == "paused"
        assert saved["backend_authority"]["status"] == "revoked"
        assert saved["jobs"][0]["assistance"]["active_writer"] == "codex"
        assert runner.pages[identifier] is original_page
    finally:
        reopened.close()


@pytest.mark.parametrize("failure", ["before_intent", "lost_reply", "after_worker_receipt"])
def test_recovery_save_boundaries_do_not_publish_or_replay_an_unrecorded_request(
    backend, monkeypatch, failure
):
    reopened, worker, _, _, _ = _reopen_after_loss(backend, monkeypatch, False)
    save = reopened._save
    request_recovery = reopened.worker.request_backend_recovery
    calls = []
    failed = False

    def save_once(state):
        nonlocal failed
        if not failed and (
            failure == "before_intent"
            and state.get("backend_recovery_request")
            or failure == "after_worker_receipt"
            and state["status"] == "recovering_worker"
        ):
            failed = True
            raise OSError("synthetic recovery checkpoint unavailable")
        return save(state)

    def recovery_once(*args, **kwargs):
        nonlocal failed
        result = request_recovery(*args, **kwargs)
        calls.append(result["request_id"])
        if failure == "lost_reply" and not failed:
            failed = True
            raise OSError("synthetic recovery response lost")
        return result

    monkeypatch.setattr(reopened, "_save", save_once)
    monkeypatch.setattr(reopened.worker, "request_backend_recovery", recovery_once)
    before = worker.store.path.read_bytes()
    try:
        with pytest.raises(OSError):
            reopened._tick()
        if failure == "before_intent":
            assert calls == []
            assert worker.store.path.read_bytes() == before
        else:
            assert len(calls) == 1
        reopened._tick()
        after = reopened.snapshot()
        saved = worker.store.load()
        assert after["status"] == "recovering_worker"
        assert after["backend_recovery_id"] == saved["backend_recovery"]["request_id"]
        assert set(calls) == {after["backend_recovery_id"]}
        assert len(saved["commands"]) == 1
        assert saved["commands"][0]["request_id"] == after["backend_recovery_id"]
        assert saved["control"] == "paused"
        assert saved["jobs"][0]["assistance"]["active_writer"] == "codex"
    finally:
        monkeypatch.setattr(reopened, "_save", save)
        monkeypatch.setattr(reopened.worker, "request_backend_recovery", request_recovery)
        reopened.close()
