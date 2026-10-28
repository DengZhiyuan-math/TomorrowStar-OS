"""Original-owner recovery reads the retained page without restoring a writer."""

import fcntl
import os
import threading
import time

import pytest
from test_single_application_worker import single_worker as single_worker
from test_worker_codex_assistance import retained_assistance_page as retained_assistance_page
from test_worker_codex_observation import owned_codex_page as owned_codex_page
from test_worker_codex_stop import stop_progress

from career_evidence_graph import application_worker, application_worker_browser
from career_evidence_graph._vendor import job_apply_store as helper


@pytest.fixture
def stopped_original_owner(owned_codex_page, monkeypatch, request):
    service, runner, page, reference, calls = owned_codex_page
    descriptor = os.open(service.store.root / ".worker.lock", os.O_CREAT | os.O_RDWR, 0o600)
    fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
    service.store.worker_lock_descriptor = descriptor
    identifier = reference["binding"]["application_id"]
    state = service.store.load()
    state["jobs"][0]["manual_fields"] = {"preserved": {"value": "original human edit"}}
    state["jobs"][0]["manual_attachments"] = [{"name": "original human attachment.pdf"}]
    service.store.save(state)
    lost = getattr(request, "param", None) == "lost"
    if lost:
        monkeypatch.setattr(application_worker, "process_identity", lambda pid: None)
        application_worker.mark_assistance_backend_lost(state, reference)
        service.store.save(state)
    else:
        receipt = service.suspend_backend(
            pipeline_id="synthetic-pipeline",
            controller="synthetic-controller",
            batch_id=state["batch_id"],
            application_id=identifier,
        )
    stop = service.store.load()["jobs"][0]["assistance"]["stop"]
    service.record_assistance_stop(
        identifier, reference, stop_progress(), request_id=stop["request_id"]
    )
    if lost:
        reopened = application_worker.WorkerService(
            service.store.applications,
            service.store.root,
            live=True,
            single_flow_root=service.store.single_flow_root,
            single_career_root=service.store.single_career_root,
            single_validator=service.store.single_validator,
        )
        monkeypatch.setattr(reopened, "spawn", lambda: pytest.fail("Keep the original owner"))
        reopened.request_backend_recovery(
            identifier,
            pipeline_id="synthetic-pipeline",
            expected_batch_id=state["batch_id"],
            expected_run_id=state["runtime"]["id"],
            expected_assistance_ref=reference,
            request_id="lost-recovery",
        )
        service = reopened
    else:
        service.recover_backend(receipt["request_id"], "synthetic-pipeline")
    monkeypatch.setattr(
        runner,
        "observe",
        lambda *_: pytest.fail("The legacy scanner must not run under Codex ownership"),
    )
    try:
        yield service, runner, page, reference, calls
    finally:
        os.close(descriptor)


def test_stopped_codex_recovery_reads_original_page_and_waits_for_handoff(stopped_original_owner):
    service, runner, page, reference, calls = stopped_original_owner
    before = service.store.load()
    state = service.store.load()
    runner.commands(state)
    runner.persist(state)
    assert not calls

    runner.service_backend_recovery()

    after = service.store.load()
    receipt = after["backend_recovery"]
    assert receipt["page_verified"] is True
    assert receipt["status"] == "needs_recheck"
    assert receipt["reason"] == "assistance_handoff_required"
    assert after["control"] == "paused"
    assert runner.pages[reference["binding"]["application_id"]] is page
    assert after["jobs"][0]["manual_fields"] == before["jobs"][0]["manual_fields"]
    assert after["jobs"][0]["manual_attachments"] == before["jobs"][0]["manual_attachments"]
    assert after["jobs"][0]["assistance"] == before["jobs"][0]["assistance"]
    assert after["backend_authority"]["status"] == "revoked"
    assert not after["commands"]
    assert not runner.permitted(after, page)
    assert sum(call[0] == "screenshot" for call in calls) == 1
    capture_calls = list(calls)
    runner.service_backend_recovery()
    assert calls == capture_calls


def test_recovery_capture_has_a_deadline(stopped_original_owner, monkeypatch):
    service, runner, page, _reference, _calls = stopped_original_owner
    page._cdp_test_wire.delays["Page.getFrameTree"] = 0.08
    deadline = application_worker_browser.browser_deadline
    monkeypatch.setattr(
        application_worker_browser, "browser_deadline", lambda _seconds: deadline(0.02)
    )
    state = service.store.load()
    runner.commands(state)
    runner.persist(state)

    runner.service_backend_recovery()

    receipt = service.store.load()["backend_recovery"]
    assert receipt["status"] == "needs_recheck"
    assert receipt.get("page_verified") is not True


def test_pause_can_save_during_page_io_and_discards_the_capture(stopped_original_owner):
    service, runner, page, _reference, _calls = stopped_original_owner
    state = service.store.load()
    runner.commands(state)
    runner.persist(state)
    completed = threading.Event()
    saved_during_capture, errors, threads = [], [], []

    def pause():
        try:
            service.request("pause", {"controller": "synthetic-controller"})
        except Exception as error:
            errors.append(error)
        finally:
            completed.set()

    def during_screenshot():
        thread = threading.Thread(target=pause, daemon=True)
        threads.append(thread)
        thread.start()
        saved_during_capture.append(completed.wait(timeout=1))

    page.screenshot_hook = during_screenshot
    runner.service_backend_recovery()
    for thread in threads:
        thread.join(timeout=2)

    assert not errors
    assert saved_during_capture == [True]
    after = service.store.load()
    assert after["control"] == "paused"
    assert after["backend_recovery"]["status"] == "cancelled"
    assert after["backend_recovery"].get("page_verified") is not True
    assert not after["commands"]


def test_pause_after_deferral_retires_the_old_command_without_reading(stopped_original_owner):
    service, runner, _page, _reference, calls = stopped_original_owner
    state = service.store.load()
    runner.commands(state)
    runner.persist(state)
    service.request("pause", {"controller": "synthetic-controller"})

    runner.service_backend_recovery()

    after = service.store.load()
    assert after["backend_recovery"]["status"] == "cancelled"
    assert not calls
    assert not after["commands"]


@pytest.mark.parametrize("change", ["document", "run", "lock", "deadline", "material"])
def test_recovery_cannot_verify_a_changed_original_scope(stopped_original_owner, change):
    service, runner, page, _reference, _calls = stopped_original_owner
    state = service.store.load()
    runner.commands(state)
    runner.persist(state)
    state = service.store.load()
    if change == "document":
        page.token = "same-url-new-document"
    elif change == "run":
        state["runtime"]["id"] = "0" * 32
    elif change == "lock":
        path = service.store.root / ".worker.lock"
        path.unlink()
        path.touch(mode=0o600)
    elif change == "deadline":
        state["backend_recovery"]["requested_at"] -= 16
    else:
        state["jobs"][0]["file_sha256"] = "0" * 64
    service.store.save(state)

    runner.service_backend_recovery()

    after = service.store.load()
    assert after["control"] == "paused"
    assert after["backend_recovery"]["status"] == "needs_recheck"
    assert after["backend_recovery"].get("page_verified") is not True
    assert not after["commands"]


@pytest.mark.parametrize("change", ["timestamp", "source", "frame", "reference", "data", "flag"])
def test_saved_recovery_observation_is_validated(stopped_original_owner, change):
    service, runner, _page, _reference, _calls = stopped_original_owner
    state = service.store.load()
    runner.commands(state)
    runner.persist(state)
    runner.service_backend_recovery()
    state = service.store.load()
    receipt = state["backend_recovery"]
    proof = receipt["page_verification"]
    if change == "timestamp":
        proof["at"] = False
    elif change == "source":
        proof["worker_source"] = "0" * 64
    elif change == "frame":
        proof["document"]["loader_id"] = None
    elif change == "reference":
        proof["assistance_ref"]["generation"] = True
    elif change == "data":
        proof["data"]["url"] = "https://another.example.invalid"
    else:
        receipt["page_verified"] = False
    helper.atomic_write_json(service.store.path, state)

    with pytest.raises(ValueError):
        service.store.load()


def test_normal_tick_services_recovery_after_releasing_the_checkpoint_lock(stopped_original_owner):
    service, runner, page, _reference, _calls = stopped_original_owner
    completed = threading.Event()
    observed = []
    threads = []

    def during_screenshot():
        def pause():
            service.request("pause", {"controller": "synthetic-controller"})
            completed.set()

        thread = threading.Thread(target=pause, daemon=True)
        threads.append(thread)
        thread.start()
        observed.append(completed.wait(timeout=1))

    page.screenshot_hook = during_screenshot

    runner.tick()

    for thread in threads:
        thread.join(timeout=2)
    assert observed == [True]
    after = service.store.load()
    assert after["control"] == "paused"
    assert after["backend_recovery"]["status"] == "cancelled"
    assert after["backend_recovery"].get("page_verified") is not True


def test_queued_recovery_waits_without_page_io_while_tools_are_not_drained(owned_codex_page):
    service, runner, _page, reference, calls = owned_codex_page
    state = service.store.load()
    receipt = service.suspend_backend(
        pipeline_id="synthetic-pipeline",
        controller="synthetic-controller",
        batch_id=state["batch_id"],
        application_id=reference["binding"]["application_id"],
    )
    # Fault injection represents a command queued before a newer revocation checkpoint.
    state = service.store.load()
    state["backend_recovery"].update(status="pending", requested_at=time.time())
    state["commands"].append(
        {
            "action": "recover-backend",
            "id": reference["binding"]["application_id"],
            "request_id": receipt["request_id"],
        }
    )
    service.store.save(state)
    runner.commands(state)
    runner.persist(state)

    runner.service_backend_recovery()

    after = service.store.load()
    assert after["control"] == "paused"
    assert after["backend_recovery"]["status"] == "pending"
    assert after["jobs"][0]["assistance"]["stop"]["local_tools_drained"] is False
    assert calls == []
    assert after["commands"]


@pytest.mark.parametrize("stopped_original_owner", ["lost"], indirect=True)
def test_hard_loss_challenge_reaches_the_original_page_without_resuming_writes(
    stopped_original_owner,
):
    service, runner, page, reference, calls = stopped_original_owner

    runner.tick()

    after = service.store.load()
    assert after["backend_recovery"].get("page_verified") is True
    assert after["backend_recovery"]["reason"] == "assistance_handoff_required"
    assert after["control"] == "paused"
    assert after["jobs"][0]["status"] == "needs_recheck"
    assert after["jobs"][0]["reason"] == "backend_authority_lost"
    assert after["jobs"][0]["assistance"]["active_writer"] == "codex"
    assert runner.pages[reference["binding"]["application_id"]] is page
    assert sum(call[0] == "screenshot" for call in calls) == 1


@pytest.mark.parametrize("stopped_original_owner", ["lost"], indirect=True)
def test_new_recovery_request_cannot_reuse_a_verified_page_that_is_now_lost(stopped_original_owner):
    service, runner, _page, reference, _calls = stopped_original_owner
    runner.tick()
    state = service.store.load()
    assert state["backend_recovery"]["page_verified"] is True
    old = state["backend_recovery"]
    state["jobs"][0].update(page_open=False, reason="page_lost")
    service.store.save(state)

    receipt = service.request_backend_recovery(
        reference["binding"]["application_id"],
        pipeline_id="synthetic-pipeline",
        expected_batch_id=state["batch_id"],
        expected_run_id=state["runtime"]["id"],
        expected_assistance_ref=reference,
        request_id="new-lost-recovery",
    )

    assert receipt["request_id"] == "new-lost-recovery"
    assert receipt["status"] == "needs_recheck"
    assert receipt["reason"] == "page_lost"
    assert receipt.get("page_verified") is not True
    assert service.store.load()["backend_recovery_history"][-1] == old


@pytest.mark.parametrize("change", ["id", "generation"])
def test_pending_receipt_cannot_be_rebound_to_another_assistance_generation(
    stopped_original_owner, change
):
    service, runner, _page, _reference, calls = stopped_original_owner
    state = service.store.load()
    runner.commands(state)
    runner.persist(state)
    state = service.store.load()
    assistance = state["jobs"][0]["assistance"]
    if change == "id":
        assistance["id"] = "0" * 32
    else:
        assistance["generation"] += 1
    service.store.save(state)

    runner.service_backend_recovery()

    after = service.store.load()
    assert after["control"] == "paused"
    assert after["backend_recovery"].get("page_verified") is not True
    assert after["backend_recovery"]["reason"] == "assistance_generation_changed"
    assert not calls


def test_legacy_codex_receipt_requires_a_fresh_bound_challenge(stopped_original_owner):
    service, runner, _page, reference, calls = stopped_original_owner
    state = service.store.load()
    state["backend_recovery"].pop("assistance_ref")
    original_id = state["backend_recovery"]["request_id"]
    service.store.save(state)
    runner.commands(state)
    runner.persist(state)
    runner.service_backend_recovery()
    old = service.store.load()
    assert old["backend_recovery"]["reason"] == "backend_recovery_unbound"
    assert not calls
    candidate = service.backend_recovery_candidate(
        reference["binding"]["application_id"],
        expected_batch_id=state["batch_id"],
        expected_run_id=state["runtime"]["id"],
    )
    assert candidate["reason"] == "backend_recovery_unbound"
    assert "recovery_request_id" not in candidate

    receipt = service.request_backend_recovery(
        reference["binding"]["application_id"],
        pipeline_id="synthetic-pipeline",
        expected_batch_id=state["batch_id"],
        expected_run_id=state["runtime"]["id"],
        expected_assistance_ref=reference,
        request_id="fresh-bound-challenge",
    )
    assert receipt["request_id"] != original_id
    assert receipt["assistance_ref"] == reference
    runner.tick()
    after = service.store.load()
    assert after["backend_recovery"]["page_verified"] is True
    assert after["backend_recovery_history"][-1]["request_id"] == original_id
    assert after["control"] == "paused"
