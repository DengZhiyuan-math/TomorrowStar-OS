"""Backend shutdown revokes Codex before waiting for upper-level cleanup."""

from threading import Event, Thread

from test_worker_backend_recovery import backend as backend


def test_codex_is_revoked_before_a_blocked_pipeline_close(backend, monkeypatch):
    owner, _, _, _ = backend
    worker = owner.worker_service
    state = worker.store.load()
    job = state["jobs"][0]
    job["form_state"] = {
        "binding": {
            "run_id": state["runtime"]["id"],
            "page_id": job["page_observation"]["page_id"],
            "document_token": "shutdown-synthetic-document",
            "step": job["job_url"],
        }
    }
    worker.store.save(state)
    worker.request(
        "request-assistance",
        {
            "application_id": job["application_id"],
            "binding": worker.assistance_context(job["application_id"])["binding"],
            "request_id": "shutdown-before-claim",
        },
    )
    entered, release = Event(), Event()
    close = owner.application_pipeline_service.close

    def blocked_close():
        entered.set()
        assert release.wait(2)
        close()

    monkeypatch.setattr(owner.application_pipeline_service, "close", blocked_close)
    thread = Thread(target=owner.server_close, daemon=True)
    thread.start()
    try:
        assert entered.wait(1)
        during = worker.store.load()
        assert during["backend_authority"]["status"] == "revoked"
        assert during["jobs"][0]["assistance"]["status"] == "stopping"
        # Preserve the existing running state for suspend_backend's recovery intent.
        assert during["control"] == "running"
    finally:
        release.set()
        thread.join(timeout=3)
        assert not thread.is_alive()
