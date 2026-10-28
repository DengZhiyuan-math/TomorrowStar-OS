"""Codex authority follows a backend kernel generation, never UI polling."""

import fcntl
import os
from copy import deepcopy

import pytest
from test_single_application_worker import single_worker as single_worker
from test_worker_codex_assistance import retained_assistance_page as retained_assistance_page
from test_worker_codex_stop import stop_progress

from career_evidence_graph import application_worker
from career_evidence_graph._vendor import job_apply_store as helper
from career_evidence_graph.career_portal_data import PortalDataError


@pytest.fixture
def backend_page(retained_assistance_page, monkeypatch):
    service, identifier = retained_assistance_page
    identity = {
        "pid": os.getpid(),
        "uid": os.getuid(),
        "started_seconds": 1_700_000_000,
        "started_microseconds": 123,
        "executable": "/synthetic/python",
    }
    monkeypatch.setattr(
        application_worker,
        "process_identity",
        lambda pid: deepcopy(identity) if pid == os.getpid() else None,
    )
    return service, identifier, identity


def request_scope(service, identifier):
    return service.request(
        "request-assistance",
        {
            "application_id": identifier,
            "binding": service.assistance_context(identifier)["binding"],
            "request_id": "request-one",
        },
    )


def test_context_is_pure_and_request_publishes_the_bound_backend_generation(backend_page):
    service, identifier, identity = backend_page
    before = service.store.path.read_bytes()
    service.assistance_context(identifier)
    assert service.store.path.read_bytes() == before
    assert "backend_authority" not in service.store.load()

    request_scope(service, identifier)

    state = service.store.load()
    authority = state["backend_authority"]
    assert authority["status"] == "active"
    assert authority["process"] == identity
    assert len(authority["instance_id"]) == 32
    assert state["jobs"][0]["assistance"]["backend_authority"] == {
        "instance_id": authority["instance_id"],
        "process": identity,
    }
    assert service.assistance_context(identifier)["assistance_ref"]["backend_authority"] == {
        "instance_id": authority["instance_id"],
        "process": identity,
    }


def test_ui_heartbeat_expiry_does_not_expire_the_live_backend(backend_page):
    service, identifier, _identity = backend_page
    request_scope(service, identifier)
    state = service.store.load()
    state["heartbeat_at"] = 0
    state["lease_seconds"] = 1
    service.store.save(state)
    before = service.store.path.read_bytes()

    assert application_worker.assistance_backend_permitted(state, state["jobs"][0]["assistance"])

    assert service.store.path.read_bytes() == before


@pytest.mark.parametrize("change", ["birth", "executable", "unreadable", "new-instance"])
def test_claim_cannot_bind_another_backend_generation(backend_page, monkeypatch, change):
    service, identifier, identity = backend_page
    request_scope(service, identifier)
    reference = service.assistance_context(identifier)["assistance_ref"]
    before = service.store.path.read_bytes()
    if change == "birth":
        identity["started_microseconds"] += 1
    elif change == "executable":
        identity["executable"] = "/synthetic/replaced-python"
    elif change == "unreadable":
        monkeypatch.setattr(application_worker, "process_identity", lambda pid: None)
    else:
        service = application_worker.WorkerService(
            service.store.applications,
            service.store.root,
            live=True,
            single_flow_root=service.store.single_flow_root,
            single_career_root=service.store.single_career_root,
            single_validator=service.store.single_validator,
        )

    with pytest.raises(PortalDataError):
        service.request(
            "claim-assistance",
            {"application_id": identifier, "assistance_ref": reference, "request_id": "claim-one"},
        )

    assert service.store.path.read_bytes() == before


@pytest.mark.parametrize("change", ["status", "birth", "instance", "timestamp", "shape"])
def test_malformed_saved_backend_authority_is_rejected(backend_page, change):
    service, identifier, _identity = backend_page
    request_scope(service, identifier)
    state = service.store.load()
    authority = state["backend_authority"]
    if change == "status":
        authority["status"] = []
    elif change == "birth":
        authority["process"]["started_seconds"] = True
    elif change == "instance":
        authority["instance_id"] = "other"
    elif change == "timestamp":
        authority["published_at"] = False
    else:
        authority["unexpected"] = True
    helper.atomic_write_json(service.store.path, state)

    with pytest.raises(ValueError):
        service.store.load()


def test_close_backend_revokes_authority_and_keeps_the_original_page_and_intent(backend_page):
    service, identifier, _identity = backend_page
    request_scope(service, identifier)
    reference = service.assistance_context(identifier)["assistance_ref"]
    service.request(
        "claim-assistance",
        {"application_id": identifier, "assistance_ref": reference, "request_id": "claim-one"},
    )
    state = service.store.load()
    state["jobs"][0]["intent"] = {"action": "fill", "attempt_id": "unresolved-before-close"}
    service.store.save(state)

    service.close_backend()

    closed = service.store.load()
    assert closed["control"] == "paused"
    assert closed["backend_authority"]["status"] == "revoked"
    assert closed["jobs"][0]["page_open"] is True
    assert closed["jobs"][0]["intent"] == state["jobs"][0]["intent"]
    assert closed["jobs"][0]["assistance"]["status"] == "stopping"
    assert closed["jobs"][0]["assistance"]["active_writer"] == "codex"
    assert not application_worker.assistance_backend_permitted(
        closed, closed["jobs"][0]["assistance"]
    )
    before = service.store.path.read_bytes()
    service.close_backend()
    assert service.store.path.read_bytes() == before
    with pytest.raises(PortalDataError) as stopped:
        service.request("resume", {"controller": "synthetic-controller"})
    assert stopped.value.code == "backend_closed"


def test_suspend_revokes_authority_and_close_preserves_its_recovery_receipt(backend_page):
    service, identifier, _identity = backend_page
    request_scope(service, identifier)
    state = service.store.load()
    receipt = service.suspend_backend(
        pipeline_id="synthetic-pipeline",
        controller="synthetic-controller",
        batch_id=state["batch_id"],
        application_id=identifier,
    )

    suspended = service.store.load()
    assert suspended["backend_authority"]["status"] == "revoked"
    assert receipt["status"] == "suspended"
    service.close_backend()
    assert service.store.load()["backend_recovery"] == receipt


def test_old_reference_cannot_revoke_a_new_backend_authority(backend_page):
    service, identifier, _identity = backend_page
    request_scope(service, identifier)
    reference = service.assistance_context(identifier)["assistance_ref"]
    state = service.store.load()
    before = deepcopy(state)
    stale = deepcopy(reference)
    stale["backend_authority"]["instance_id"] = "0" * 32

    assert not application_worker.revoke_backend_authority(state, reference=stale)
    assert state == before
    assert application_worker.revoke_backend_authority(state, reference=reference)
    assert state["backend_authority"]["status"] == "revoked"


@pytest.mark.parametrize("unknown", [False, True])
def test_backend_recovery_waits_for_the_old_assistance_to_stop(backend_page, unknown):
    service, identifier, _identity = backend_page
    request_scope(service, identifier)
    reference = service.assistance_context(identifier)["assistance_ref"]
    state = service.store.load()
    receipt = service.suspend_backend(
        pipeline_id="synthetic-pipeline",
        controller="synthetic-controller",
        batch_id=state["batch_id"],
        application_id=identifier,
    )
    if unknown:
        stop = service.store.load()["jobs"][0]["assistance"]["stop"]
        service.record_assistance_stop(
            identifier,
            reference,
            stop_progress(
                local_tools_drained=False,
                process_stopped=False,
                native_turn_status="unknown",
                stop_status="unknown",
            ),
            request_id=stop["request_id"],
        )

    result = service.recover_backend(receipt["request_id"], "synthetic-pipeline")

    assert result["status"] == ("needs_recheck" if unknown else "suspended")
    assert result["reason"] == ("assistance_stop_unknown" if unknown else "assistance_stop_pending")
    assert service.store.load()["commands"] == []
    assert service.store.load()["jobs"][0]["page_open"] is True


def test_confirmed_stop_only_queues_fresh_original_owner_verification(backend_page):
    service, identifier, _identity = backend_page
    request_scope(service, identifier)
    reference = service.assistance_context(identifier)["assistance_ref"]
    descriptor = os.open(service.store.root / ".worker.lock", os.O_CREAT | os.O_RDWR, 0o600)
    fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
    try:
        state = service.store.load()
        receipt = service.suspend_backend(
            pipeline_id="synthetic-pipeline",
            controller="synthetic-controller",
            batch_id=state["batch_id"],
            application_id=identifier,
        )
        waiting = service.recover_backend(receipt["request_id"], "synthetic-pipeline")
        assert waiting["status"] == "suspended"
        stop = service.store.load()["jobs"][0]["assistance"]["stop"]
        service.record_assistance_stop(
            identifier, reference, stop_progress(), request_id=stop["request_id"]
        )

        verification = service.recover_backend(receipt["request_id"], "synthetic-pipeline")

        assert verification["status"] == "pending"
        assert "reason" not in verification
        after = service.store.load()
        assert after["control"] == "paused"
        assert after["backend_authority"]["status"] == "revoked"
        assert after["commands"] == [
            {"action": "recover-backend", "id": identifier, "request_id": receipt["request_id"]}
        ]
    finally:
        os.close(descriptor)


def test_new_worker_keeps_the_old_claim_unknown_and_cannot_recreate_its_page(backend_page):
    service, identifier, _identity = backend_page
    request_scope(service, identifier)
    reference = service.assistance_context(identifier)["assistance_ref"]
    service.request(
        "claim-assistance",
        {"application_id": identifier, "assistance_ref": reference, "request_id": "claim-one"},
    )
    previous = service.store.load()

    application_worker.start_run(service.store)

    restarted = service.store.load()
    assistance = restarted["jobs"][0]["assistance"]
    assert restarted["runtime"]["id"] != previous["runtime"]["id"]
    assert restarted["control"] == "paused"
    assert restarted["jobs"][0]["page_open"] is False
    assert assistance["status"] == "stop_unknown"
    assert assistance["stop"]["local_tools_drained"] is False
    assert assistance["stop"]["process_stopped"] is False
    assert assistance["binding"] == reference["binding"]
    assert assistance["active_writer"] == "codex"
    assert restarted["backend_authority"]["status"] == "revoked"
    assert not application_worker.assistance_backend_permitted(restarted, assistance)


def test_old_assistance_cannot_be_classified_as_a_never_opened_queue(backend_page):
    service, identifier, _identity = backend_page
    request_scope(service, identifier)
    state = service.store.load()
    state["jobs"][0].update(status="queued", page_open=False)
    state["jobs"][0].pop("page_observation")
    service.store.save(state)

    application_worker.start_run(service.store)

    restarted = service.store.load()
    assert restarted["control"] == "paused"
    assert restarted["jobs"][0]["status"] == "needs_recheck"
    assert restarted["jobs"][0]["reason"] == "worker_restarted"


@pytest.mark.parametrize("change", ["birth", "pid", "uid", "executable", "instance", "unreadable"])
def test_each_tool_admission_rechecks_the_frozen_backend_identity(
    backend_page, monkeypatch, change
):
    service, identifier, identity = backend_page
    request_scope(service, identifier)
    state = service.store.load()
    if change == "birth":
        identity["started_seconds"] += 1
    elif change == "pid":
        identity["pid"] += 1
    elif change == "uid":
        identity["uid"] += 1
    elif change == "executable":
        identity["executable"] = "/synthetic/replaced-python"
    elif change == "instance":
        state["backend_authority"]["instance_id"] = "0" * 32
    else:
        monkeypatch.setattr(application_worker, "process_identity", lambda pid: None)
    before = service.store.path.read_bytes()

    assert not application_worker.assistance_backend_permitted(
        state, state["jobs"][0]["assistance"]
    )

    assert service.store.path.read_bytes() == before


def test_old_authorityless_record_is_readable_but_cannot_be_claimed(backend_page):
    service, identifier, _identity = backend_page
    request_scope(service, identifier)
    state = service.store.load()
    state.pop("backend_authority")
    state["jobs"][0]["assistance"].pop("backend_authority")
    service.store.save(state)
    before = service.store.path.read_bytes()
    context = service.assistance_context(identifier)
    assert "backend_authority" not in context["assistance_ref"]
    assert not application_worker.assistance_backend_permitted(state, context["assistance_ref"])
    with pytest.raises(PortalDataError):
        service.request(
            "claim-assistance",
            {
                "application_id": identifier,
                "assistance_ref": context["assistance_ref"],
                "request_id": "legacy-claim",
            },
        )
    assert service.store.path.read_bytes() == before


def test_unreadable_backend_identity_does_not_publish_authority(backend_page, monkeypatch):
    service, identifier, _identity = backend_page
    monkeypatch.setattr(application_worker, "process_identity", lambda pid: None)
    before = service.store.path.read_bytes()
    with pytest.raises(PortalDataError) as unavailable:
        request_scope(service, identifier)
    assert unavailable.value.code == "backend_authority_unavailable"
    assert service.store.path.read_bytes() == before
    assert "backend_authority" not in service.store.load()


@pytest.mark.parametrize("operation", ["begin_backend_close", "close_backend"])
def test_close_save_failure_fences_the_backend_without_claiming_a_saved_stop(
    backend_page, monkeypatch, operation
):
    service, identifier, _identity = backend_page
    request_scope(service, identifier)
    before = service.store.path.read_bytes()
    original = helper.atomic_write_json

    def fail(path, data):
        if path == service.store.path:
            raise OSError("synthetic backend close checkpoint failure")
        return original(path, data)

    monkeypatch.setattr(helper, "atomic_write_json", fail)
    with pytest.raises(OSError):
        getattr(service, operation)()
    assert service.store.path.read_bytes() == before
    assert service.store.stop_reason() == "checkpoint_unavailable"
    with pytest.raises(PortalDataError) as closed:
        service.request("resume", {"controller": "synthetic-controller"})
    assert closed.value.code == "backend_closed"


@pytest.mark.parametrize("operation", ["begin_backend_close", "close_backend"])
@pytest.mark.parametrize("owner_closing", [False, True])
def test_reader_close_does_not_revoke_or_pause_the_active_backend(
    backend_page, operation, owner_closing
):
    owner, identifier, _identity = backend_page
    request_scope(owner, identifier)
    reference = owner.assistance_context(identifier)["assistance_ref"]
    if owner_closing:
        owner.begin_backend_close()
    reader = application_worker.WorkerService(
        owner.store.applications,
        owner.store.root,
        live=True,
        single_flow_root=owner.store.single_flow_root,
        single_career_root=owner.store.single_career_root,
        single_validator=owner.store.single_validator,
    )
    before = owner.store.path.read_bytes()

    getattr(reader, operation)()

    assert owner.store.path.read_bytes() == before
    state = owner.store.load()
    assert state["control"] == "running"
    if owner_closing:
        receipt = owner.suspend_backend(
            pipeline_id="synthetic-pipeline",
            controller="synthetic-controller",
            batch_id=state["batch_id"],
            application_id=identifier,
        )
        assert receipt["status"] == "suspended"
    else:
        assert state["backend_authority"]["status"] == "active"
        assert application_worker.assistance_backend_permitted(state, reference)
        owner.request(
            "claim-assistance",
            {
                "application_id": identifier,
                "assistance_ref": reference,
                "request_id": "owner-claim",
            },
        )


def test_begin_close_revokes_before_waiting_without_destroying_suspend_inputs(backend_page):
    service, identifier, _identity = backend_page
    request_scope(service, identifier)
    state = service.store.load()

    assert service.begin_backend_close() is True

    fenced = service.store.load()
    assert fenced["control"] == "running"
    assert fenced["backend_authority"]["status"] == "revoked"
    assert fenced["jobs"][0]["assistance"]["status"] == "stopping"
    receipt = service.suspend_backend(
        pipeline_id="synthetic-pipeline",
        controller="synthetic-controller",
        batch_id=state["batch_id"],
        application_id=identifier,
    )
    assert receipt["status"] == "suspended"
    before = service.store.path.read_bytes()
    service.close_backend()
    assert service.store.path.read_bytes() == before


def test_backend_loss_pauses_only_the_bound_scope_and_retains_its_unknown_effects(backend_page):
    service, identifier, identity = backend_page
    request_scope(service, identifier)
    reference = service.assistance_context(identifier)["assistance_ref"]
    service.request(
        "claim-assistance",
        {"application_id": identifier, "assistance_ref": reference, "request_id": "claim-one"},
    )
    state = service.store.load()
    state["jobs"][0]["intent"] = {"action": "upload", "attempt_id": "inflight-before-loss"}
    state["jobs"][0].update(status="needs_recheck", reason="action_result_unknown")
    identity["started_microseconds"] += 1

    assert application_worker.mark_assistance_backend_lost(state, reference)
    service.store.save(state)

    lost = service.store.load()
    assert lost["control"] == "paused"
    assert lost["jobs"][0]["reason"] == "action_result_unknown"
    assert lost["jobs"][0]["intent"] == state["jobs"][0]["intent"]
    assert lost["jobs"][0]["assistance"]["backend_loss"]["was_running"] is True
    assert lost["jobs"][0]["assistance"]["status"] == "stopping"
    assert lost["backend_authority"]["status"] == "revoked"


def test_backend_loss_exposes_a_pure_fixed_recovery_candidate(backend_page):
    service, identifier, identity = backend_page
    request_scope(service, identifier)
    reference = service.assistance_context(identifier)["assistance_ref"]
    state = service.store.load()
    identity["started_microseconds"] += 1
    application_worker.mark_assistance_backend_lost(state, reference)
    service.store.save(state)
    before = service.store.path.read_bytes()

    candidate = service.backend_recovery_candidate(
        identifier,
        expected_batch_id=state["batch_id"],
        expected_run_id=state["runtime"]["id"],
        expected_task_id="synthetic-task",
    )

    assert candidate == {
        "application_id": identifier,
        "batch_id": state["batch_id"],
        "run_id": state["runtime"]["id"],
        "task_id": "synthetic-task",
        "assistance_ref": reference,
        "reason": "backend_authority_lost",
    }
    assert service.store.path.read_bytes() == before
    assert service.store.load()["jobs"][0]["reason"] == "backend_authority_lost"


@pytest.fixture
def lost_backend(backend_page, monkeypatch):
    original, identifier, identity = backend_page
    request_scope(original, identifier)
    reference = original.assistance_context(identifier)["assistance_ref"]
    original.request(
        "claim-assistance",
        {"application_id": identifier, "assistance_ref": reference, "request_id": "claim-one"},
    )
    state = original.store.load()
    identity["started_microseconds"] += 1
    application_worker.mark_assistance_backend_lost(state, reference)
    original.store.save(state)
    stop = state["jobs"][0]["assistance"]["stop"]
    original.record_assistance_stop(
        identifier,
        reference,
        stop_progress(native_turn_status="unknown"),
        request_id=stop["request_id"],
    )
    descriptor = os.open(original.store.root / ".worker.lock", os.O_CREAT | os.O_RDWR, 0o600)
    fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
    reopened = application_worker.WorkerService(
        original.store.applications,
        original.store.root,
        live=True,
        single_flow_root=original.store.single_flow_root,
        single_career_root=original.store.single_career_root,
        single_validator=original.store.single_validator,
    )
    monkeypatch.setattr(reopened, "spawn", lambda: pytest.fail("Never replace the original owner"))
    arguments = {
        "pipeline_id": "synthetic-reopened-pipeline",
        "expected_batch_id": state["batch_id"],
        "expected_run_id": state["runtime"]["id"],
        "expected_assistance_ref": reference,
        "request_id": "reopen-one",
    }
    try:
        yield reopened, identifier, arguments
    finally:
        os.close(descriptor)


def test_hard_loss_reopen_only_queues_a_fixed_original_owner_challenge(lost_backend):
    reopened, identifier, arguments = lost_backend
    before = reopened.store.load()

    receipt = reopened.request_backend_recovery(identifier, **arguments)

    assert receipt["status"] == "pending"
    assert receipt["assistance_ref"] == arguments["expected_assistance_ref"]
    assert receipt["request_id"] == arguments["request_id"]
    after = reopened.store.load()
    assert after["backend_authority"] == before["backend_authority"]
    assert after["jobs"] == before["jobs"]
    assert after["control"] == "paused"
    assert after["commands"] == [
        {"action": "recover-backend", "id": identifier, "request_id": arguments["request_id"]}
    ]
    checkpoint = reopened.store.path.read_bytes()
    assert reopened.request_backend_recovery(identifier, **arguments) == receipt
    assert reopened.store.path.read_bytes() == checkpoint


@pytest.mark.parametrize("explicit_stop", [None, "pause", "skip-return"])
def test_suspend_publication_cut_reuses_the_old_receipt_but_respects_user_wait(
    backend_page, explicit_stop
):
    service, identifier, identity = backend_page
    request_scope(service, identifier)
    reference = service.assistance_context(identifier)["assistance_ref"]
    state = service.store.load()
    receipt = service.suspend_backend(
        pipeline_id="synthetic-pipeline",
        controller="synthetic-controller",
        batch_id=state["batch_id"],
        application_id=identifier,
    )
    identity["started_microseconds"] += 1
    state = service.store.load()
    application_worker.mark_assistance_backend_lost(state, reference)
    service.store.save(state)
    if explicit_stop == "pause":
        service.request("pause", {"controller": "synthetic-controller"})
    elif explicit_stop == "skip-return":
        service.request("skip-current", {"application_id": identifier, "request_id": "skip-one"})
        service.request(
            "select-current", {"application_id": identifier, "request_id": "return-one"}
        )
    before = service.store.path.read_bytes()

    candidate = service.backend_recovery_candidate(
        identifier,
        expected_batch_id=state["batch_id"],
        expected_run_id=state["runtime"]["id"],
    )

    if explicit_stop is None:
        assert candidate["recovery_request_id"] == receipt["request_id"]
        assert candidate["reason"] == "backend_closed"
    else:
        assert candidate is None
    assert service.store.path.read_bytes() == before


def test_backend_loss_stops_the_same_reserved_execution_after_a_new_ui_controller(backend_page):
    service, identifier, identity = backend_page
    request_scope(service, identifier)
    reference = service.assistance_context(identifier)["assistance_ref"]
    service.request("resume", {"controller": "different-ui-controller"})
    state = service.store.load()
    identity["started_microseconds"] += 1

    application_worker.mark_assistance_backend_lost(state, reference)

    assert state["control"] == "paused"
    assert state["jobs"][0]["reason"] == "backend_authority_lost"
    assert state["jobs"][0]["assistance"]["backend_loss"]["automatic_recovery"] is False


def test_ui_silence_is_not_recorded_as_backend_loss(backend_page):
    service, identifier, _identity = backend_page
    request_scope(service, identifier)
    state = service.store.load()
    state["heartbeat_at"] = 0
    reference = service.assistance_context(identifier)["assistance_ref"]
    before = deepcopy(state)

    assert not application_worker.mark_assistance_backend_lost(state, reference)

    assert state == before


@pytest.mark.parametrize("when", ["before-loss", "after-loss"])
def test_explicit_pause_never_becomes_an_automatic_recovery(backend_page, when):
    service, identifier, identity = backend_page
    request_scope(service, identifier)
    reference = service.assistance_context(identifier)["assistance_ref"]
    if when == "before-loss":
        service.request("pause", {"controller": "synthetic-controller"})
    state = service.store.load()
    identity["started_microseconds"] += 1
    application_worker.mark_assistance_backend_lost(state, reference)
    service.store.save(state)
    if when == "after-loss":
        service.request("pause", {"controller": "synthetic-controller"})
    state = service.store.load()
    before = service.store.path.read_bytes()

    assert (
        service.backend_recovery_candidate(
            identifier, expected_batch_id=state["batch_id"], expected_run_id=state["runtime"]["id"]
        )
        is None
    )
    with pytest.raises(PortalDataError) as blocked:
        service.request_backend_recovery(
            identifier,
            pipeline_id="synthetic-pipeline",
            expected_batch_id=state["batch_id"],
            expected_run_id=state["runtime"]["id"],
            expected_assistance_ref=reference,
            request_id="not-an-automatic-resume",
        )
    assert blocked.value.code == "backend_recovery_not_automatic"
    assert service.store.path.read_bytes() == before


@pytest.mark.parametrize("change", ["batch", "run", "reference", "task"])
def test_new_backend_cannot_challenge_another_saved_execution(lost_backend, change):
    reopened, identifier, arguments = lost_backend
    arguments = deepcopy(arguments)
    if change == "batch":
        arguments["expected_batch_id"] = "0" * 32
    elif change == "run":
        arguments["expected_run_id"] = "0" * 32
    elif change == "task":
        arguments["expected_task_id"] = "different-task"
    else:
        arguments["expected_assistance_ref"]["generation"] = True
    before = reopened.store.path.read_bytes()

    with pytest.raises(PortalDataError):
        reopened.request_backend_recovery(identifier, **arguments)

    assert reopened.store.path.read_bytes() == before


@pytest.mark.parametrize("change", ["stop", "intent", "page", "lock", "stopping", "material"])
def test_reopen_waits_on_uncertain_effects_or_an_unverified_original_owner(lost_backend, change):
    reopened, identifier, arguments = lost_backend
    state = reopened.store.load()
    job = state["jobs"][0]
    if change in {"stop", "stopping"}:
        job["assistance"]["status"] = "stop_unknown" if change == "stop" else "stopping"
        job["assistance"]["stop"].update(
            stop_status="unknown" if change == "stop" else "stopping",
            local_tools_drained=False,
            process_stopped=False,
        )
    elif change == "intent":
        job["intent"] = {"action": "upload", "attempt_id": "unknown-original-upload"}
        job["reason"] = "action_result_unknown"
    elif change == "page":
        job.update(page_open=False, reason="page_lost")
    elif change == "material":
        job["file_sha256"] = "0" * 64
    else:
        path = reopened.store.root / ".worker.lock"
        path.unlink()
        path.touch(mode=0o600)
    reopened.store.save(state)

    receipt = reopened.request_backend_recovery(identifier, **arguments)

    assert receipt["status"] == ("suspended" if change == "stopping" else "needs_recheck")
    assert (
        receipt["reason"]
        == {
            "stop": "assistance_stop_unknown",
            "intent": "action_result_unknown",
            "page": "page_lost",
            "lock": "backend_owner_unavailable",
            "stopping": "assistance_stop_pending",
            "material": "assistance_binding_changed",
        }[change]
    )
    after = reopened.store.load()
    assert not after["commands"]
    assert after["jobs"] == state["jobs"]
    assert after["backend_authority"] == state["backend_authority"]


def test_candidate_does_not_recreate_a_missing_execution_directory(lost_backend):
    reopened, identifier, arguments = lost_backend
    directory = reopened.store.applications.root / ".execution"
    directory.rename(directory.parent.parent / "retained-execution-history")
    before = sorted(str(path) for path in reopened.store.applications.root.rglob("*"))

    assert (
        reopened.backend_recovery_candidate(
            identifier,
            expected_batch_id=arguments["expected_batch_id"],
            expected_run_id=arguments["expected_run_id"],
        )
        is None
    )

    assert sorted(str(path) for path in reopened.store.applications.root.rglob("*")) == before


def test_copied_worker_root_cannot_challenge_the_original_execution(lost_backend, tmp_path):
    original, identifier, arguments = lost_backend
    copied_root = tmp_path / "different-worker-root"
    copied_root.mkdir()
    (copied_root / "run.json").write_bytes(original.store.path.read_bytes())
    other = application_worker.WorkerService(
        original.store.applications,
        copied_root,
        live=True,
        single_flow_root=original.store.single_flow_root,
        single_career_root=original.store.single_career_root,
        single_validator=original.store.single_validator,
    )
    before = other.store.path.read_bytes()

    assert (
        other.backend_recovery_candidate(
            identifier,
            expected_batch_id=arguments["expected_batch_id"],
            expected_run_id=arguments["expected_run_id"],
        )
        is None
    )
    with pytest.raises(PortalDataError) as blocked:
        other.request_backend_recovery(identifier, **arguments)

    assert blocked.value.code == "execution_conflict"
    assert other.store.path.read_bytes() == before


def test_old_loss_candidate_cannot_claim_a_new_backend_authority(lost_backend):
    reopened, identifier, arguments = lost_backend
    state = reopened.store.load()
    state["backend_authority"].update(instance_id="0" * 32, status="active", revoked_at=None)
    reopened.store.save(state)
    before = reopened.store.path.read_bytes()

    assert (
        reopened.backend_recovery_candidate(
            identifier,
            expected_batch_id=arguments["expected_batch_id"],
            expected_run_id=arguments["expected_run_id"],
        )
        is None
    )

    assert reopened.store.path.read_bytes() == before
