"""Durable Codex revocation preserves its reservation and uncertain effects."""

from copy import deepcopy

import pytest
from test_single_application_worker import single_worker as single_worker
from test_worker_codex_assistance import retained_assistance_page as retained_assistance_page

from career_evidence_graph._vendor import job_apply_store as helper
from career_evidence_graph.application_worker_browser import ApplicationRunner
from career_evidence_graph.career_portal_data import PortalDataError


@pytest.fixture
def claimed_assistance(retained_assistance_page):
    service, identifier = retained_assistance_page
    service.request(
        "request-assistance",
        {
            "application_id": identifier,
            "binding": service.assistance_context(identifier)["binding"],
            "request_id": "request-one",
        },
    )
    reference = service.assistance_context(identifier)["assistance_ref"]
    service.request(
        "claim-assistance",
        {"application_id": identifier, "assistance_ref": reference, "request_id": "claim-one"},
    )
    return service, identifier, reference


def test_pause_durably_revokes_before_the_original_page_owner_stops(claimed_assistance):
    service, identifier, reference = claimed_assistance
    paused = service.request("pause", {"controller": "synthetic-controller"})

    assistance = paused["jobs"][0]["assistance"]
    assert paused["control"] == "paused"
    assert assistance["status"] == "stopping"
    assert assistance["active_writer"] == "codex"
    assert assistance["stop"]["tools_revoked"] is True
    assert assistance["stop"]["local_tools_drained"] is False
    assert assistance["stop"]["native_turn_status"] == "unknown"
    assert service.assistance_context(identifier)["assistance_ref"] == reference


def test_process_stop_keeps_native_and_page_effects_unknown(claimed_assistance):
    service, identifier, reference = claimed_assistance
    state = service.store.load()
    intent = {"action": "fill", "attempt_id": "unresolved-original-action"}
    state["jobs"][0]["intent"] = deepcopy(intent)
    service.store.save(state)
    paused = service.request("pause", {"controller": "synthetic-controller"})
    request_id = paused["jobs"][0]["assistance"]["stop"]["request_id"]

    result = service.record_assistance_stop(
        identifier,
        reference,
        {
            "tools_revoked": True,
            "local_tools_drained": True,
            "process_stopped": True,
            "native_turn_id": "original-turn",
            "native_turn_status": "unknown",
            "stop_status": "stopped",
        },
        request_id=request_id,
    )

    assistance = result["jobs"][0]["assistance"]
    assert assistance["status"] == "stopped"
    assert assistance["stop"]["native_turn_status"] == "unknown"
    assert assistance["active_writer"] == "codex"
    assert result["jobs"][0]["intent"] == intent
    assert result["control"] == "paused"


@pytest.mark.parametrize(
    "operation", ["cancel", "cancel-job", "suspend-backend", "skip-current", "select-current"]
)
def test_all_stopping_controls_preserve_the_original_reservation(claimed_assistance, operation):
    service, identifier, reference = claimed_assistance
    if operation == "suspend-backend":
        state = service.store.load()
        service.suspend_backend(
            pipeline_id="synthetic-pipeline",
            controller="synthetic-controller",
            batch_id=state["batch_id"],
            application_id=identifier,
        )
    else:
        service.request(
            operation,
            {
                "controller": "synthetic-controller",
                "application_id": identifier,
                "request_id": "stop-control",
            },
        )
    assistance = service.store.load()["jobs"][0]["assistance"]
    assert assistance["status"] == "stopping"
    assert assistance["active_writer"] == "codex"
    assert assistance["stop"]["tools_revoked"] is True
    assert assistance["stop"]["local_tools_drained"] is False
    assert service.assistance_context(identifier)["assistance_ref"] == reference


def stop_progress(**changes):
    return {
        "tools_revoked": True,
        "local_tools_drained": True,
        "process_stopped": True,
        "native_turn_id": None,
        "native_turn_status": "idle",
        "stop_status": "stopped",
        **changes,
    }


@pytest.mark.parametrize(
    "changes",
    [
        {"tools_revoked": False},
        {"local_tools_drained": False},
        {"local_tools_drained": 1},
        {"process_stopped": False},
        {"native_turn_status": "running"},
        {"native_turn_status": "running", "stop_status": "unknown"},
        {"native_turn_status": []},
        {"stop_status": []},
        {"native_turn_id": ""},
    ],
)
def test_invalid_stop_evidence_cannot_report_drained(claimed_assistance, changes):
    service, identifier, reference = claimed_assistance
    paused = service.request("pause", {"controller": "synthetic-controller"})
    request_id = paused["jobs"][0]["assistance"]["stop"]["request_id"]
    before = service.store.path.read_bytes()

    with pytest.raises(PortalDataError):
        service.record_assistance_stop(
            identifier, reference, stop_progress(**changes), request_id=request_id
        )

    assert service.store.path.read_bytes() == before


def test_later_transport_loss_does_not_erase_an_observed_native_terminal(claimed_assistance):
    service, identifier, reference = claimed_assistance
    paused = service.request("pause", {"controller": "synthetic-controller"})
    request_id = paused["jobs"][0]["assistance"]["stop"]["request_id"]
    service.record_assistance_stop(
        identifier,
        reference,
        stop_progress(
            local_tools_drained=False,
            process_stopped=False,
            native_turn_id="original-turn",
            native_turn_status="interrupted",
            stop_status="stopping",
        ),
        request_id=request_id,
    )

    result = service.record_assistance_stop(
        identifier,
        reference,
        stop_progress(native_turn_status="unknown"),
        request_id=request_id,
    )

    stop = result["jobs"][0]["assistance"]["stop"]
    assert stop["native_turn_id"] == "original-turn"
    assert stop["native_turn_status"] == "interrupted"
    assert stop["stop_status"] == "stopped"


def test_skip_cannot_admit_a_second_job_until_the_old_tools_are_stopped(claimed_assistance):
    service, identifier, reference = claimed_assistance
    service.request("skip-current", {"application_id": identifier, "request_id": "skip-one"})
    state = service.store.load()
    request_id = state["jobs"][0]["assistance"]["stop"]["request_id"]

    with pytest.raises(PortalDataError) as blocked:
        service.check_new_current_job()
    assert blocked.value.code == "assistance_stop_pending"

    service.record_assistance_stop(identifier, reference, stop_progress(), request_id=request_id)
    service.check_new_current_job()
    assert service.store.load()["jobs"][0]["assistance"]["active_writer"] == "codex"


def test_legacy_batch_replacement_cannot_discard_an_unconfirmed_stop(claimed_assistance):
    service, identifier, _reference = claimed_assistance
    service.request("cancel", {"controller": "synthetic-controller"})
    state = service.store.load()
    state["jobs"][0]["page_open"] = False
    service.store.save(state)
    before = service.store.path.read_bytes()

    with pytest.raises(PortalDataError) as blocked:
        service.request("prepare", {})

    assert blocked.value.code == "assistance_stop_pending"
    assert service.store.path.read_bytes() == before


def test_repeated_stop_and_late_progress_cannot_restore_a_writer(claimed_assistance):
    service, identifier, reference = claimed_assistance
    first = service.request("pause", {"controller": "synthetic-controller"})
    request_id = first["jobs"][0]["assistance"]["stop"]["request_id"]
    before = deepcopy(first["jobs"][0]["assistance"])
    again = service.request("pause", {"controller": "synthetic-controller"})
    assert again["jobs"][0]["assistance"] == before
    service.record_assistance_stop(identifier, reference, stop_progress(), request_id=request_id)
    stopped = service.store.path.read_bytes()
    service.record_assistance_stop(identifier, reference, stop_progress(), request_id=request_id)
    service.record_assistance_stop(
        identifier,
        reference,
        stop_progress(
            local_tools_drained=False,
            process_stopped=False,
            native_turn_status="unknown",
            stop_status="stopping",
        ),
        request_id=request_id,
    )
    assert service.store.path.read_bytes() == stopped
    service.request("resume", {"controller": "synthetic-controller"})
    assert not ApplicationRunner(service.store, None).permitted(service.store.load())
    with pytest.raises(PortalDataError):
        service.request(
            "claim-assistance",
            {"application_id": identifier, "assistance_ref": reference, "request_id": "claim-one"},
        )


@pytest.mark.parametrize("change", ["request", "generation", "turn", "boolean-generation"])
def test_stale_stop_receipt_does_not_change_the_original_scope(claimed_assistance, change):
    service, identifier, reference = claimed_assistance
    first = service.request("pause", {"controller": "synthetic-controller"})
    request_id = first["jobs"][0]["assistance"]["stop"]["request_id"]
    if change == "request":
        request_id = "different-stop"
    elif change == "generation":
        reference["generation"] += 1
    elif change == "boolean-generation":
        reference["generation"] = True
    else:
        service.record_assistance_stop(
            identifier,
            reference,
            stop_progress(
                local_tools_drained=False,
                process_stopped=False,
                native_turn_id="original-turn",
                native_turn_status="running",
                stop_status="stopping",
            ),
            request_id=request_id,
        )
    before = service.store.path.read_bytes()
    with pytest.raises(PortalDataError):
        service.record_assistance_stop(
            identifier,
            reference,
            stop_progress(native_turn_id="different-turn" if change == "turn" else None),
            request_id=request_id,
        )
    assert service.store.path.read_bytes() == before


def test_requested_but_unclaimed_scope_still_requires_stop_confirmation(retained_assistance_page):
    service, identifier = retained_assistance_page
    service.request(
        "request-assistance",
        {
            "application_id": identifier,
            "binding": service.assistance_context(identifier)["binding"],
            "request_id": "never-claimed",
        },
    )
    reference = service.assistance_context(identifier)["assistance_ref"]
    paused = service.request("pause", {"controller": "synthetic-controller"})
    assistance = paused["jobs"][0]["assistance"]
    assert assistance["status"] == "stopping" and assistance["active_writer"] == "none"
    result = service.record_assistance_stop(
        identifier,
        reference,
        stop_progress(),
        request_id=assistance["stop"]["request_id"],
    )
    assert result["jobs"][0]["assistance"]["status"] == "stopped"
    assert result["jobs"][0]["assistance"]["active_writer"] == "none"


@pytest.mark.parametrize("phase", ["revoke", "record-stop"])
def test_failed_checkpoint_does_not_publish_stop_evidence(claimed_assistance, monkeypatch, phase):
    service, identifier, reference = claimed_assistance
    if phase == "record-stop":
        paused = service.request("pause", {"controller": "synthetic-controller"})
        request_id = paused["jobs"][0]["assistance"]["stop"]["request_id"]
    before = service.store.path.read_bytes()
    original = helper.atomic_write_json

    def fail(path, data):
        if path == service.store.path:
            raise OSError("synthetic stop checkpoint failure")
        return original(path, data)

    monkeypatch.setattr(helper, "atomic_write_json", fail)
    with pytest.raises(OSError):
        if phase == "revoke":
            service.request("pause", {"controller": "synthetic-controller"})
        else:
            service.record_assistance_stop(
                identifier, reference, stop_progress(), request_id=request_id
            )
    assert service.store.path.read_bytes() == before
    assert service.store.stop_reason() == "checkpoint_unavailable"


@pytest.mark.parametrize("change", ["batch", "run", "task"])
def test_conditional_cancel_cannot_cancel_a_new_execution(claimed_assistance, change):
    service, identifier, _reference = claimed_assistance
    state = service.store.load()
    before = service.store.path.read_bytes()
    with pytest.raises(PortalDataError) as blocked:
        service.cancel_execution(
            identifier,
            expected_batch_id="previous-batch" if change == "batch" else state["batch_id"],
            expected_run_id="previous-run" if change == "run" else state["runtime"]["id"],
            **({"expected_task_id": "previous-task"} if change == "task" else {}),
        )
    assert blocked.value.code == "worker_execution_changed"
    assert service.store.path.read_bytes() == before


@pytest.mark.parametrize("unresolved_intent", [False, True])
def test_cancellation_projection_owns_stop_and_unknown_effect_meanings(
    claimed_assistance, unresolved_intent
):
    service, identifier, reference = claimed_assistance
    state = service.store.load()
    if unresolved_intent:
        state["jobs"][0]["intent"] = {"action": "upload", "attempt_id": "unknown-upload"}
        service.store.save(state)
    binding = {
        "expected_batch_id": state["batch_id"],
        "expected_run_id": state["runtime"]["id"],
    }

    def stale_materials(*args, **kwargs):
        raise PortalDataError("stale_materials", "Synthetic obsolete inputs", 409)

    service.validate_write_preflight = stale_materials
    assert service.cancellation_progress(identifier, **binding)["status"] == "active"
    cancelled = service.cancel_execution(identifier, **binding)
    projection = cancelled["execution_cancellation"]
    assert projection == {
        "application_id": identifier,
        "batch_id": state["batch_id"],
        "run_id": state["runtime"]["id"],
        "task_id": "synthetic-task",
        "status": "unknown" if unresolved_intent else "stopping",
    }
    stop = cancelled["jobs"][0]["assistance"]["stop"]
    service.record_assistance_stop(
        identifier, reference, stop_progress(), request_id=stop["request_id"]
    )
    before = service.store.path.read_bytes()
    assert service.cancellation_progress(identifier, **binding)["status"] == (
        "unknown" if unresolved_intent else "stopped"
    )
    assert service.store.path.read_bytes() == before
