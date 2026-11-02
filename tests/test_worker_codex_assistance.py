"""Codex ownership metadata cannot enable browser execution."""

import time
from copy import deepcopy

import pytest
from test_single_application_worker import single_worker as single_worker
from test_worker_current_job import prepare

from career_evidence_graph._vendor import job_apply_store as helper
from career_evidence_graph.application_worker import start_run
from career_evidence_graph.application_worker_browser import ApplicationRunner
from career_evidence_graph.career_portal_data import PortalDataError


@pytest.fixture
def retained_assistance_page(single_worker):
    service, item, _, _ = single_worker
    prepare(service, item)
    service.request("resume", {"controller": "synthetic-controller"})
    run_id = start_run(service.store)
    state = service.store.load()
    job = state["jobs"][0]
    job.update(status="filling", page_open=True)
    job["page_observation"] = {
        "run_id": run_id,
        "page_id": "retained-page",
        "event": "observed",
        "at": time.time(),
    }
    job["form_state"] = {
        "binding": {
            "run_id": run_id,
            "page_id": "retained-page",
            "document_token": "original-document",
            "step": job["job_url"],
        }
    }
    service.store.save(state)
    return service, item["application_id"]


def test_request_stops_script_metadata_without_pausing_the_user(retained_assistance_page):
    service, identifier = retained_assistance_page
    context = service.assistance_context(identifier)
    before = service.store.path.read_bytes()
    assert context["assistance_ref"] is None
    assert service.store.path.read_bytes() == before

    payload = {
        "application_id": identifier,
        "binding": context["binding"],
        "request_id": "original-request",
    }
    result = service.request("request-assistance", payload)
    assert result["control"] == "running"
    assistance = result["jobs"][0]["assistance"]
    assert assistance["active_writer"] == "none"
    assert assistance["page_writes_enabled"] is False
    assert service.assistance_context(identifier)["assistance_ref"]["binding"] == payload["binding"]
    assert not ApplicationRunner(service.store, None).permitted(service.store.load())


def test_repeated_request_and_claim_reserve_one_writer(retained_assistance_page):
    service, identifier = retained_assistance_page
    payload = {
        "application_id": identifier,
        "binding": service.assistance_context(identifier)["binding"],
        "request_id": "original-request",
    }
    first = service.request("request-assistance", payload)["jobs"][0]["assistance"]
    again = service.request("request-assistance", payload)["jobs"][0]["assistance"]
    assert first == again
    ref = service.assistance_context(identifier)["assistance_ref"]
    claim = {"application_id": identifier, "assistance_ref": ref, "request_id": "claim-one"}
    first = service.request("claim-assistance", claim)["jobs"][0]["assistance"]
    again = service.request("claim-assistance", claim)["jobs"][0]["assistance"]
    assert first == again
    assert first["active_writer"] == "codex"
    assert first["generation"] == 1
    assert first["page_writes_enabled"] is False
    assert not ApplicationRunner(service.store, None).permitted(service.store.load())
    with pytest.raises(PortalDataError):
        service.request("request-assistance", {**payload, "request_id": "another-request"})
    with pytest.raises(PortalDataError):
        service.request("claim-assistance", {**claim, "request_id": "another-claim"})


def test_reservation_fences_pending_review_and_script_authorization(retained_assistance_page):
    service, identifier = retained_assistance_page
    service.request(
        "request-assistance",
        {
            "application_id": identifier,
            "binding": service.assistance_context(identifier)["binding"],
            "request_id": "original-request",
        },
    )
    writes = []

    class Page:
        def is_closed(self):
            return False

        def unroute(self, *_):
            writes.append("guard removed")

        def bring_to_front(self):
            writes.append("human handoff")

    page = Page()
    runner = ApplicationRunner(service.store, None)
    runner.pages[identifier] = page
    runner.guards[identifier] = object()
    state = service.store.load()
    current = state["jobs"][0]
    current["manual_intervention"] = True
    state["commands"] = [{"action": "review", "id": identifier}]
    service.store.save(state)
    assert not runner.authorize(deepcopy(current), state["batch_id"], {"action": "fill"})
    assert service.store.load()["control"] == "running"
    runner.commands(state)
    assert writes == []
    assert page not in runner.handed_off_pages
    assert state["commands"] == [{"action": "review", "id": identifier}]
    assert not current["handed_off"]


@pytest.mark.parametrize(
    "change",
    [
        {"page_writes_enabled": True},
        {"active_writer": "script"},
        {"generation": True},
        {"generation": 0},
        {"status": "complete"},
        {"binding": {}},
    ],
)
def test_invalid_ownership_metadata_is_rejected_on_read(retained_assistance_page, change):
    service, identifier = retained_assistance_page
    service.request(
        "request-assistance",
        {
            "application_id": identifier,
            "binding": service.assistance_context(identifier)["binding"],
            "request_id": "original-request",
        },
    )
    state = service.store.load()
    state["jobs"][0]["assistance"].update(change)
    helper.atomic_write_json(service.store.path, state)
    with pytest.raises(ValueError, match="assistance"):
        service.assistance_context(identifier)


@pytest.mark.parametrize(
    "change", ["document", "material", "answers", "run", "pause", "cancel", "skip", "resume"]
)
def test_changed_saved_scope_rejects_old_claim_and_new_request(retained_assistance_page, change):
    service, identifier = retained_assistance_page
    request = {
        "application_id": identifier,
        "binding": service.assistance_context(identifier)["binding"],
        "request_id": "original-request",
    }
    service.request("request-assistance", request)
    ref = service.assistance_context(identifier)["assistance_ref"]
    if change in {"pause", "cancel", "resume"}:
        service.request(
            "cancel" if change == "cancel" else "pause", {"controller": "synthetic-controller"}
        )
        if change == "resume":
            service.request("resume", {"controller": "synthetic-controller"})
    elif change == "skip":
        service.request("skip-current", {"application_id": identifier, "request_id": "skip-one"})
    else:
        state = service.store.load()
        current = state["jobs"][0]
        if change == "document":
            current["form_state"]["binding"]["document_token"] = "new-document-same-url"
        elif change == "material":
            current["file_sha256"] = "a" * 64
        elif change == "answers":
            current["answer_refs"] = [{"key": "new-confirmed-answer", "revision": "new"}]
        else:
            state["runtime"]["id"] = "new-run"
        service.store.save(state)
    before = service.store.path.read_bytes()
    with pytest.raises(PortalDataError):
        service.request(
            "claim-assistance",
            {"application_id": identifier, "assistance_ref": ref, "request_id": "claim-one"},
        )
    fresh_binding = service.assistance_context(identifier)["binding"]
    for request_id in ["original-request", "fresh-request"]:
        with pytest.raises(PortalDataError):
            service.request(
                "request-assistance",
                {**request, "binding": fresh_binding, "request_id": request_id},
            )
    assert service.store.path.read_bytes() == before
    assert service.store.load()["jobs"][0]["assistance"]["active_writer"] == "none"


@pytest.mark.parametrize("pending", ["intent", "command", "transport", "manual_result"])
def test_pending_effects_cannot_be_bypassed_with_a_new_request(retained_assistance_page, pending):
    service, identifier = retained_assistance_page
    state = service.store.load()
    current = state["jobs"][0]
    intent = {"action": "upload", "attempt_id": "unresolved-upload"}
    if pending == "intent":
        current["intent"] = intent
    elif pending == "command":
        state["commands"] = [{"action": "continue-current", "id": identifier}]
    elif pending == "manual_result":
        current["submission_observation"] = {"conclusion": "unknown"}
    else:
        current["observations"].append(
            {
                "stage": "requestfailed",
                "application_id": identifier,
                "batch_id": state["batch_id"],
                "run_id": state["runtime"]["id"],
                "intent": intent,
            }
        )
    service.store.save(state)
    binding = service.assistance_context(identifier)["binding"]
    before = service.store.path.read_bytes()
    for request_id in ["first-request", "different-request"]:
        with pytest.raises(PortalDataError):
            service.request(
                "request-assistance",
                {"application_id": identifier, "binding": binding, "request_id": request_id},
            )
    assert service.store.path.read_bytes() == before


@pytest.mark.parametrize("change", ["generation", "id", "document", "write_flag", "job"])
def test_forged_claim_does_not_change_the_saved_reservation(retained_assistance_page, change):
    service, identifier = retained_assistance_page
    service.request(
        "request-assistance",
        {
            "application_id": identifier,
            "binding": service.assistance_context(identifier)["binding"],
            "request_id": "original-request",
        },
    )
    ref = service.assistance_context(identifier)["assistance_ref"]
    target = identifier
    if change == "generation":
        ref["generation"] += 1
    elif change == "id":
        ref["id"] = "f" * 32
    elif change == "document":
        ref["binding"]["document_token"] = "different-document"
    elif change == "write_flag":
        ref["page_writes_enabled"] = True
    else:
        target = "another-application"
    before = service.store.path.read_bytes()
    with pytest.raises(PortalDataError):
        service.request(
            "claim-assistance",
            {"application_id": target, "assistance_ref": ref, "request_id": "claim-one"},
        )
    assert service.store.path.read_bytes() == before


@pytest.mark.parametrize("operation", ["request-assistance", "claim-assistance"])
def test_failed_conditional_save_never_adopts_the_new_writer(
    retained_assistance_page, monkeypatch, operation
):
    service, identifier = retained_assistance_page
    payload = {
        "application_id": identifier,
        "binding": service.assistance_context(identifier)["binding"],
        "request_id": "original-request",
    }
    if operation == "claim-assistance":
        service.request("request-assistance", payload)
        payload = {
            "application_id": identifier,
            "assistance_ref": service.assistance_context(identifier)["assistance_ref"],
            "request_id": "claim-one",
        }
    before = service.store.path.read_bytes()
    original = helper.atomic_write_json

    def fail(path, data):
        if path == service.store.path:
            raise OSError("synthetic checkpoint failure")
        return original(path, data)

    monkeypatch.setattr(helper, "atomic_write_json", fail)
    with pytest.raises(OSError):
        service.request(operation, payload)
    assert service.store.path.read_bytes() == before
    assert service.store.stop_reason() == "checkpoint_unavailable"
    saved = service.store.load()["jobs"][0].get("assistance")
    assert saved is None or saved["active_writer"] == "none"


def test_old_records_keep_script_semantics_and_dispatch_rechecks_writer(retained_assistance_page):
    service, identifier = retained_assistance_page
    runner = ApplicationRunner(service.store, None)
    state = service.store.load()
    assert "assistance" not in state["jobs"][0]
    assert runner.permitted(state)
    service.request(
        "request-assistance",
        {
            "application_id": identifier,
            "binding": service.assistance_context(identifier)["binding"],
            "request_id": "original-request",
        },
    )
    # A queued sender cannot use an earlier decision after a reservation is saved.
    state = service.store.load()
    state["jobs"][0]["intent"] = {"action": "fill", "attempt_id": "stale-sender"}
    service.store.save(state)
    dispatched = []
    with (
        pytest.raises(PortalDataError, match="待执行动作"),
        runner.dispatch_current(state["jobs"][0], state["batch_id"], state["jobs"][0]["intent"]),
    ):
        dispatched.append(True)
    assert dispatched == []


@pytest.mark.parametrize("operation", ["request-assistance", "claim-assistance"])
def test_existing_task_admission_can_deny_metadata_changes(retained_assistance_page, operation):
    service, identifier = retained_assistance_page
    payload = {
        "application_id": identifier,
        "binding": service.assistance_context(identifier)["binding"],
        "request_id": "original-request",
    }
    if operation == "claim-assistance":
        service.request("request-assistance", payload)
        payload = {
            "application_id": identifier,
            "assistance_ref": service.assistance_context(identifier)["assistance_ref"],
            "request_id": "claim-one",
        }

    def deny(_operation):
        raise PortalDataError("current_task_changed", "Synthetic changed task.", 409)

    service.validate_write_preflight = deny
    before = service.store.path.read_bytes()
    with pytest.raises(PortalDataError, match="Synthetic changed task"):
        service.request(operation, payload)
    assert service.store.path.read_bytes() == before


# MC-08 S1: a technical blocker dispatches one system-claimed Codex takeover.

DISPATCHABLE = [
    "unsupported_control",
    "unsupported_structure",
    "unsupported_attachments",
    "unsupported_attachment_transport",
    "ambiguous_option",
    "user_authentication",
    "route_change_forbidden",
    "parser_failed",
    "parser_unstable",
    "action_result_unknown",
    "upload_result_unknown",
    "draft_result_unknown",
    "draft_result_unverified",
    "public_read_result_unknown",
    "browser_result_unknown",
    # select_fill_route: no script route for a read-only combobox (route_decision, not_sent).
    "cua_unavailable",
]
ROUTE_REASONS = {"unsupported_control", "route_change_forbidden", "cua_unavailable"}
NOT_DISPATCHABLE = [
    "page_lost",
    "page_closed",
    "page_crashed",
    "page_released",
    "page_capacity",
    "checkpoint_unavailable",
    "form_changed",
    "identity_changed",
    "page_changed",
    "navigation_changed",
    "submission_result_unknown",
    "handoff_unknown",
    "browser_connection_unknown",
    "material_readback_unknown",
    "material_edit_needs_recheck",
    "answer_changed",
    "manual_submit_required",
    "generic_disabled",
    "unverified_send_path",
    "unsupported_action",
    "page_command_failed",
    "backend_authority_lost",
    "backend_closed",
    "email_correction_pending",
    "duplicate_application",
    "cua_owner_unknown",
    "recovery_order_unknown",
    "assistance_return_unverified",
    "assistance_completion_unverified",
    "assistance_scope_lost",
]
QUESTION_FLOW = [
    "missing_answers",
    "form_differences",
    "material_field_mapping_required",
    "precision_adjustment",
]


def takeover_service(service, monkeypatch):
    from test_worker_native_assistance import native_service

    return native_service(service, monkeypatch)


def block(
    service, reason, *, field="country", status="needs_recheck", intent=None, **state_changes
):
    state = service.store.load()
    job = state["jobs"][0]
    job.update(status=status, reason=reason, intent=intent)
    job["page_observation"]["at"] = time.time()
    state["runtime"]["observed_at"] = time.time()
    if reason in ROUTE_REASONS:
        job["observations"].append(
            {
                "action": "route_decision",
                "stage": "fill",
                "field_id": field,
                "selected_executor": "manual",
                "executor": None,
                "route_reason": reason,
                "dispatch": "not_sent",
                "dispatch_scope": "proposed_fill",
                "page_id": job["page_observation"]["page_id"],
                "run_id": state["runtime"]["id"],
                "at": time.time(),
            }
        )
    state.update(state_changes)
    service.store.save(state)
    return state


def expected(service):
    state = service.store.load()
    return {
        "expected_batch_id": state["batch_id"],
        "expected_run_id": state["runtime"]["id"],
        "expected_task_id": (state["jobs"][0].get("single_binding") or {}).get("task_id"),
    }


def take_over(service, identifier, request_id):
    blocker = service.takeover_candidate(identifier, **expected(service))
    assert blocker is not None
    return service.request_takeover(
        identifier, **expected(service), blocker=blocker, request_id=request_id
    )


def continue_serial(service):
    state = service.store.load()
    state["resume_serial"] = state.get("resume_serial", 0) + 1
    service.store.save(state)


def end_in_wait(service, wait="assistance_return_unverified"):
    from test_worker_assistance_return import stop_native

    ref = service.assistance_context(service.store.load()["jobs"][0]["application_id"])[
        "assistance_ref"
    ]
    stop_native(service, ref)
    state = service.store.load()
    state["jobs"][0].update(status="needs_recheck", reason=wait)
    service.store.save(state)
    return ref


def release(service, kind="script_checkpoint"):
    from test_worker_assistance_return import make_outcome, make_report

    from career_evidence_graph.application_worker import (
        adopt_assistance_outcome,
        adopt_assistance_report,
    )

    ref = end_in_wait(service)
    state = service.store.load()
    job = state["jobs"][0]
    report = make_report(
        status="ready_for_review" if kind == "filling_complete" else "blocked_segment_resolved"
    )
    assert adopt_assistance_report(job, ref, report, request_id="stop-one")
    service.store.save(state)
    state = service.store.load()
    job = state["jobs"][0]
    outcome = make_outcome(state, kind)
    if kind == "filling_complete":
        outcome["return_count"] = job.get("assistance_return_count", 0)
    assert adopt_assistance_outcome(state, job, ref, outcome)
    service.store.save(state)
    return service.store.load()["jobs"][0]


@pytest.mark.parametrize(
    "reason",
    DISPATCHABLE + NOT_DISPATCHABLE + QUESTION_FLOW,
)
def test_takeover_candidate_classifies_reasons(retained_assistance_page, monkeypatch, reason):
    from career_evidence_graph.application_worker import technical_blocker

    service, identifier = retained_assistance_page
    native = takeover_service(service, monkeypatch)
    status = "needs_input" if reason in QUESTION_FLOW else "needs_recheck"
    state = block(native, reason, status=status)
    blocker = native.takeover_candidate(identifier, **expected(native))
    assert blocker == technical_blocker(state, state["jobs"][0], native.native_assistance_policy)
    if reason not in DISPATCHABLE:
        assert blocker is None
        return
    job = state["jobs"][0]
    assert blocker == {
        "code": reason,
        "field_id": "country" if reason in ROUTE_REASONS else None,
        "page_id": job["page_observation"]["page_id"],
        "run_id": state["runtime"]["id"],
        "observed_at": job["page_observation"]["at"],
    }


def test_takeover_candidate_none_when_native_policy_off(retained_assistance_page):
    from career_evidence_graph.application_worker import technical_blocker

    service, identifier = retained_assistance_page
    state = block(service, "unsupported_control")
    assert technical_blocker(state, state["jobs"][0], None) is None
    assert service.takeover_candidate(identifier, **expected(service)) is None
    before = service.store.path.read_bytes()
    with pytest.raises(PortalDataError):
        service.request_takeover(
            identifier,
            **expected(service),
            blocker={
                "code": "unsupported_control",
                "field_id": "country",
                "page_id": state["jobs"][0]["page_observation"]["page_id"],
                "run_id": state["runtime"]["id"],
                "observed_at": state["jobs"][0]["page_observation"]["at"],
            },
            request_id="takeover-one",
        )
    assert service.store.path.read_bytes() == before


def test_request_takeover_claims_once_without_user_claim(retained_assistance_page, monkeypatch):
    service, identifier = retained_assistance_page
    native = takeover_service(service, monkeypatch)
    block(native, "unsupported_control")
    blocker = native.takeover_candidate(identifier, **expected(native))
    serial = native.store.load().get("resume_serial", 0)
    result = native.request_takeover(
        identifier, **expected(native), blocker=blocker, request_id="takeover-one"
    )
    assistance = native.store.load()["jobs"][0]["assistance"]
    assert assistance["protocol"] == "codex-assistance/native/v1"
    assert assistance["status"] == "claimed"
    assert assistance["active_writer"] == "codex"
    assert assistance["request_id"] == assistance["claim_request_id"] == "takeover-one"
    assert assistance["generation"] == 1
    assert set(assistance["dispatch"]) == {
        "request_id",
        "blocker",
        "requested_at",
        "continue_serial",
    }
    assert assistance["dispatch"]["request_id"] == "takeover-one"
    assert assistance["dispatch"]["blocker"] == blocker
    assert assistance["dispatch"]["continue_serial"] == serial
    assert result["assistance_ref"] == native.assistance_context(identifier)["assistance_ref"]
    assert result["dispatch"] == assistance["dispatch"]
    assert not ApplicationRunner(native.store, None).permitted(native.store.load())

    before = native.store.path.read_bytes()
    again = native.request_takeover(
        identifier, **expected(native), blocker=blocker, request_id="takeover-one"
    )
    assert again == result
    assert native.store.path.read_bytes() == before
    assert native.takeover_candidate(identifier, **expected(native)) is None
    with pytest.raises(PortalDataError) as error:
        native.request_takeover(
            identifier, **expected(native), blocker=blocker, request_id="another-takeover"
        )
    assert error.value.code == "assistance_request_conflict"
    assert native.store.path.read_bytes() == before

    state = native.store.load()
    state["jobs"][0]["assistance"]["dispatch"]["extra"] = True
    helper.atomic_write_json(native.store.path, state)
    with pytest.raises(ValueError, match="assistance"):
        native.store.load()


def test_request_takeover_rejects_a_changed_blocker(retained_assistance_page, monkeypatch):
    service, identifier = retained_assistance_page
    native = takeover_service(service, monkeypatch)
    block(native, "unsupported_control")
    blocker = native.takeover_candidate(identifier, **expected(native))
    before = native.store.path.read_bytes()
    with pytest.raises(PortalDataError):
        native.request_takeover(
            identifier,
            **expected(native),
            blocker=blocker | {"field_id": "phone"},
            request_id="takeover-one",
        )
    assert native.store.path.read_bytes() == before


def test_second_takeover_after_released_checkpoint_gets_next_generation(
    retained_assistance_page, monkeypatch
):
    from test_worker_assistance_return import make_outcome, make_report, not_adopted_rows

    from career_evidence_graph.application_worker import (
        adopt_assistance_outcome,
        adopt_assistance_report,
    )

    service, identifier = retained_assistance_page
    native = takeover_service(service, monkeypatch)
    block(native, "unsupported_control")
    take_over(native, identifier, "takeover-one")
    first = release(native)
    assert first["assistance"]["status"] == "released"
    assert first["assistance_return_count"] == 1

    block(native, "unsupported_control", field="phone")
    result = take_over(native, identifier, "takeover-two")
    job = native.store.load()["jobs"][0]
    assert job["assistance"]["generation"] == 2
    assert job["assistance"]["id"] != first["assistance"]["id"]
    assert job["assistance"]["status"] == "claimed"
    assert job["assistance"]["dispatch"]["blocker"]["field_id"] == "phone"
    assert job["assistance_history"] == [first["assistance"]]
    assert native.takeover_candidate(identifier, **expected(native)) is None
    delivery = native.assistance_delivery(identifier, result["assistance_ref"])
    assert delivery["next_step"]["kind"] == "complete_remaining_fields"

    ref = end_in_wait(native)
    state = native.store.load()
    job = state["jobs"][0]
    assert adopt_assistance_report(job, ref, make_report(), request_id="stop-one")
    native.store.save(state)
    state = native.store.load()
    job = state["jobs"][0]
    assert adopt_assistance_outcome(state, job, ref, make_outcome(state))
    assert "outcome" not in job["assistance"]
    assert not_adopted_rows(job)[-1]["reason"] == "assistance_return_limit"


def test_one_takeover_per_continue_serial(retained_assistance_page, monkeypatch):
    service, identifier = retained_assistance_page
    native = takeover_service(service, monkeypatch)
    block(native, "unsupported_control")
    take_over(native, identifier, "takeover-one")
    end_in_wait(native)
    assert native.takeover_candidate(identifier, **expected(native)) is None
    block(native, "unsupported_control")
    assert native.takeover_candidate(identifier, **expected(native)) is None

    continue_serial(native)
    block(native, "unsupported_control")
    take_over(native, identifier, "takeover-two")
    state = native.store.load()
    job = state["jobs"][0]
    assert job["assistance"]["generation"] == 2
    assert job["assistance"]["dispatch"]["continue_serial"] == state["resume_serial"]
    assert len(job["assistance_history"]) == 1

    end_in_wait(native)
    block(native, "unsupported_control")
    assert native.takeover_candidate(identifier, **expected(native)) is None
    continue_serial(native)
    block(native, "unsupported_control")
    assert native.takeover_candidate(identifier, **expected(native)) is not None


def stop_unknown(job):
    """Record the Adapter's unconfirmed stop through the record's own stop adoption."""
    from career_evidence_graph.application_worker import (
        adopt_assistance_stop,
        assistance_reference,
    )

    assistance = job["assistance"]
    progress = {
        "tools_revoked": True,
        "local_tools_drained": False,
        "process_stopped": False,
        "native_turn_id": None,
        "native_turn_status": "unknown",
        "stop_status": "unknown",
    }
    assert adopt_assistance_stop(
        job,
        assistance_reference(assistance),
        progress,
        request_id=assistance["stop"]["request_id"],
    )


@pytest.mark.parametrize(
    "change", ["superseded", "stopping", "stop_unknown", "filling_complete", "paused", "storage"]
)
def test_takeover_refused_when_superseded_stopping_or_filling_complete(
    retained_assistance_page, monkeypatch, change
):
    from career_evidence_graph.application_worker import revoke_assistance

    service, identifier = retained_assistance_page
    native = takeover_service(service, monkeypatch)
    if change not in {"paused", "storage"}:
        block(native, "unsupported_control")
        take_over(native, identifier, "takeover-one")
    if change == "superseded":
        end_in_wait(native)
        state = native.store.load()
        assert revoke_assistance(state["jobs"][0], reason="user_paused")
        native.store.save(state)
    elif change in {"stopping", "stop_unknown"}:
        state = native.store.load()
        job = state["jobs"][0]
        assert revoke_assistance(job, reason="native_turn_completed")
        if change == "stop_unknown":
            stop_unknown(job)
        native.store.save(state)
    elif change == "filling_complete":
        release(native, "filling_complete")
    continue_serial(native)
    if change == "paused":
        block(native, "unsupported_control", control="paused")
    else:
        block(native, "unsupported_control")
    if change == "storage":
        native.store.block_storage()
    assert native.takeover_candidate(identifier, **expected(native)) is None
    state = native.store.load()
    blocker = {
        "code": "unsupported_control",
        "field_id": "country",
        "page_id": state["jobs"][0]["page_observation"]["page_id"],
        "run_id": state["runtime"]["id"],
        "observed_at": state["jobs"][0]["page_observation"]["at"],
    }
    before = native.store.path.read_bytes()
    with pytest.raises(PortalDataError):
        native.request_takeover(
            identifier, **expected(native), blocker=blocker, request_id="takeover-two"
        )
    assert native.store.path.read_bytes() == before


def test_capability_failure_is_not_redispatched(retained_assistance_page, monkeypatch):
    from career_evidence_graph.application_worker import record_takeover_failure

    service, identifier = retained_assistance_page
    native = takeover_service(service, monkeypatch)
    block(native, "unsupported_control")
    take_over(native, identifier, "takeover-one")
    state = native.store.load()
    job = state["jobs"][0]
    with pytest.raises(PortalDataError):
        record_takeover_failure(job, request_id="another-takeover", code="cua_unavailable")
    assert record_takeover_failure(job, request_id="takeover-one", code="cua_unavailable")
    assert not record_takeover_failure(job, request_id="takeover-one", code="cua_unavailable")
    native.store.save(state)
    assert native.store.load()["jobs"][0]["assistance"]["dispatch"]["failed_code"] == (
        "cua_unavailable"
    )
    end_in_wait(native, "cua_unavailable")

    continue_serial(native)
    block(native, "unsupported_control")
    assert native.takeover_candidate(identifier, **expected(native)) is None
    block(native, "unsupported_control", field="phone")
    assert native.takeover_candidate(identifier, **expected(native))["field_id"] == "phone"


def test_unknown_result_takeover_carries_pending_action(retained_assistance_page, monkeypatch):
    service, identifier = retained_assistance_page
    native = takeover_service(service, monkeypatch)
    run_id = native.store.load()["runtime"]["id"]
    intent = {
        "action": "fill",
        "attempt_id": "unknown-fill",
        "field_id": "country",
        "run_id": run_id,
        "page_id": "retained-page",
    }
    block(native, "unsupported_control", intent=deepcopy(intent))
    assert native.takeover_candidate(identifier, **expected(native)) is None

    block(native, "action_result_unknown", intent=deepcopy(intent))
    blocker = native.takeover_candidate(identifier, **expected(native))
    assert blocker["code"] == "action_result_unknown"
    assert blocker["field_id"] == "country"
    result = native.request_takeover(
        identifier, **expected(native), blocker=blocker, request_id="takeover-one"
    )
    job = native.store.load()["jobs"][0]
    assert job["intent"] == intent
    assert job["assistance"]["status"] == "claimed"
    delivery = native.assistance_delivery(identifier, result["assistance_ref"])
    pending = [row for row in delivery["pending_actions"] if row["action_id"] == "unknown-fill"]
    assert pending and pending[0]["status"] == "unknown"
    assert pending[0]["source_ref"] == {"record": "intent"}
    assert delivery["blocker"]["code"] == "action_result_unknown"
    assert delivery["next_step"]["kind"] == "reconcile_pending_actions"
    assert native.store.load()["jobs"][0]["intent"] == intent


def resume(service):
    return service.request("resume", {"controller": "synthetic-controller"})


@pytest.mark.parametrize("change", ["stopped", "superseded", "stopping", "stop_unknown"])
def test_continue_archives_stopped_takeover_and_restores_script_writes(
    retained_assistance_page, monkeypatch, change
):
    from career_evidence_graph.application_worker import revoke_assistance, script_writes_allowed

    service, identifier = retained_assistance_page
    native = takeover_service(service, monkeypatch)
    block(native, "unsupported_control")
    take_over(native, identifier, "takeover-one")
    if change in {"stopped", "superseded"}:
        end_in_wait(native)
    else:
        state = native.store.load()
        job = state["jobs"][0]
        assert revoke_assistance(job, reason="native_turn_completed")
        if change == "stop_unknown":
            stop_unknown(job)
        job.update(status="needs_recheck", reason="assistance_stop_pending")
        native.store.save(state)
    if change == "superseded":
        native.request("pause", {"controller": "synthetic-controller"})
        assert "superseded" in native.store.load()["jobs"][0]["assistance"]
    before = native.store.load()
    assert not script_writes_allowed(before)
    resume(native)
    state = native.store.load()
    job = state["jobs"][0]
    assert state["resume_serial"] == before.get("resume_serial", 0) + 1
    if change in {"stopping", "stop_unknown"}:
        assert job["assistance"] == before["jobs"][0]["assistance"]
        assert job["status"] == "needs_recheck"
        assert state["control"] == "paused"
        assert "assistance_history" not in job
        return
    assert "assistance" not in job
    assert job["assistance_history"] == [before["jobs"][0]["assistance"]]
    assert script_writes_allowed(state)
    assert (job["status"], job["reason"]) == ("queued", "")
    assert state["control"] == "running"
    assert native.assistance_context(identifier)["assistance_ref"] is None


def test_failed_blocker_stays_blocked_after_continue_but_new_blocker_dispatches(
    retained_assistance_page, monkeypatch
):
    from career_evidence_graph.application_worker import record_takeover_failure

    service, identifier = retained_assistance_page
    native = takeover_service(service, monkeypatch)
    block(native, "unsupported_control")
    take_over(native, identifier, "takeover-one")
    state = native.store.load()
    assert record_takeover_failure(
        state["jobs"][0], request_id="takeover-one", code="native_assistance_unavailable"
    )
    native.store.save(state)
    end_in_wait(native, "native_assistance_unavailable")
    resume(native)
    job = native.store.load()["jobs"][0]
    assert "assistance" not in job
    assert job["assistance_history"][0]["dispatch"]["failed_code"] == (
        "native_assistance_unavailable"
    )

    block(native, "unsupported_control")
    assert native.takeover_candidate(identifier, **expected(native)) is None
    block(native, "unsupported_control", field="phone")
    take_over(native, identifier, "takeover-two")
    assistance = native.store.load()["jobs"][0]["assistance"]
    assert assistance["generation"] == 2
    assert assistance["dispatch"]["blocker"]["field_id"] == "phone"


def test_pause_then_continue_allows_one_new_takeover(retained_assistance_page, monkeypatch):
    service, identifier = retained_assistance_page
    native = takeover_service(service, monkeypatch)
    block(native, "unsupported_control")
    take_over(native, identifier, "takeover-one")
    end_in_wait(native)
    native.request("pause", {"controller": "synthetic-controller"})
    resume(native)
    block(native, "unsupported_control")
    take_over(native, identifier, "takeover-two")
    end_in_wait(native)
    block(native, "unsupported_control")
    assert native.takeover_candidate(identifier, **expected(native)) is None
    resume(native)
    block(native, "unsupported_control")
    assert native.takeover_candidate(identifier, **expected(native)) is not None

    native.request("cancel", {"controller": "synthetic-controller"})
    block(native, "unsupported_control", status="cancelled")
    assert native.takeover_candidate(identifier, **expected(native)) is None


def test_unknown_takeover_admits_only_the_referenced_intent(retained_assistance_page, monkeypatch):
    from test_worker_assistance_return import make_outcome, make_report, not_adopted_rows
    from test_worker_native_assistance import journal_scope, prepare_journal

    from career_evidence_graph.application_worker import (
        adopt_assistance_outcome,
        adopt_assistance_report,
        digest,
    )

    service, identifier = retained_assistance_page
    native = takeover_service(service, monkeypatch)
    run_id = native.store.load()["runtime"]["id"]
    intent = {
        "action": "fill",
        "attempt_id": "unknown-fill",
        "field_id": "country",
        "run_id": run_id,
        "page_id": "retained-page",
    }
    block(native, "action_result_unknown", intent=deepcopy(intent))
    take_over(native, identifier, "takeover-one")
    dispatch = native.store.load()["jobs"][0]["assistance"]["dispatch"]
    assert dispatch["pending_intent_ref"] == digest(intent)

    # Adoption keeps waiting while the referenced intent is still unsettled.
    ref = end_in_wait(native)
    state = native.store.load()
    job = state["jobs"][0]
    assert adopt_assistance_report(job, ref, make_report(), request_id="stop-one")
    native.store.save(state)
    state = native.store.load()
    job = state["jobs"][0]
    assert adopt_assistance_outcome(state, job, ref, make_outcome(state))
    assert "outcome" not in job["assistance"]
    assert not_adopted_rows(job)[-1]["reason"] == "assistance_pending_intent"
    assert job["intent"] == intent

    resume(native)
    block(native, "action_result_unknown", intent=deepcopy(intent))
    result = take_over(native, identifier, "takeover-two")
    ref = result["assistance_ref"]
    prepare_journal(native, ref)
    assert native.store.load()["jobs"][0]["intent"] == intent

    for change in ["other_intent", "foreign_failure"]:
        state = native.store.load()
        job = state["jobs"][0]
        if change == "other_intent":
            job["intent"] = intent | {"attempt_id": "another-fill"}
        else:
            job["observations"].append(
                {
                    "stage": "requestfailed",
                    "application_id": identifier,
                    "batch_id": state["batch_id"],
                    "run_id": run_id,
                    "intent": {"action": "upload", "attempt_id": "foreign-upload"},
                }
            )
        state["runtime"]["observed_at"] = time.time()
        job["page_observation"]["at"] = time.time()
        native.store.save(state)
        with pytest.raises(PortalDataError):
            native.store.record_native_handoff(
                ref,
                request_id=f"journal-{change}",
                phase="prepared",
                scope=journal_scope(native, ref),
                expected_worker_source=state["runtime"]["source"]["sha256"],
            )
        state = native.store.load()
        state["jobs"][0]["intent"] = deepcopy(intent)
        state["jobs"][0]["observations"] = [
            row
            for row in state["jobs"][0]["observations"]
            if (row.get("intent") or {}).get("attempt_id") != "foreign-upload"
        ]
        native.store.save(state)


def continue_current(service, identifier, request_id):
    state = service.store.load()
    state["runtime"]["observed_at"] = time.time()
    service.store.save(state)
    return service.request(
        "continue-current",
        {
            "application_id": identifier,
            "request_id": request_id,
            "controller": "synthetic-controller",
        },
    )


def runner_continued(service):
    """The runner's verified continue-current: original page rechecked, control running."""
    state = service.store.load()
    state["commands"] = []
    state.update(control="running", resume_serial=state.get("resume_serial", 0) + 1)
    service.store.save(state)


@pytest.mark.parametrize(
    "wait", ["assistance_return_unverified", "assistance_completion_unverified"]
)
def test_continue_current_after_natural_wait_archives_and_allows_one_new_takeover(
    retained_assistance_page, monkeypatch, wait
):
    from career_evidence_graph.application_worker import script_writes_allowed

    service, identifier = retained_assistance_page
    native = takeover_service(service, monkeypatch)
    block(native, "unsupported_control")
    take_over(native, identifier, "takeover-one")
    end_in_wait(native, wait)
    native.request("pause", {"controller": "synthetic-controller"})
    paused = native.store.load()["jobs"][0]["assistance"]
    assert paused["superseded"]["reason"] == "user_paused"

    continue_current(native, identifier, "continue-one")
    state = native.store.load()
    job = state["jobs"][0]
    assert "assistance" not in job
    assert job["assistance_history"] == [paused]
    assert script_writes_allowed(state, identifier)
    assert [row["action"] for row in state["commands"]] == ["continue-current"]

    runner_continued(native)
    block(native, "unsupported_control")
    take_over(native, identifier, "takeover-two")
    assert native.store.load()["jobs"][0]["assistance"]["generation"] == 2

    end_in_wait(native, wait)
    block(native, "unsupported_control")
    assert native.takeover_candidate(identifier, **expected(native)) is None
    native.request("pause", {"controller": "synthetic-controller"})
    continue_current(native, identifier, "continue-two")
    runner_continued(native)
    block(native, "unsupported_control")
    assert native.takeover_candidate(identifier, **expected(native)) is not None


def test_continue_current_keeps_cancel_superseded_and_lost_save_records(
    retained_assistance_page, monkeypatch
):
    service, identifier = retained_assistance_page
    native = takeover_service(service, monkeypatch)
    block(native, "unsupported_control")
    take_over(native, identifier, "takeover-one")
    end_in_wait(native)
    # Outside a wait (e.g. a lost outcome save) the stopped record stays re-adoptable.
    state = native.store.load()
    state["jobs"][0].update(status="filling", reason="")
    native.store.save(state)
    continue_current(native, identifier, "continue-one")
    assert "assistance" in native.store.load()["jobs"][0]


@pytest.mark.parametrize("context", ["no_route_decision", "later_route_decision", "sent"])
def test_cua_capability_failure_without_a_current_no_route_decision_is_not_dispatched(
    retained_assistance_page, monkeypatch, context
):
    """A Cua/driver failure is a capability failure; only "no script route" dispatches."""
    service, identifier = retained_assistance_page
    native = takeover_service(service, monkeypatch)
    state = block(native, "cua_unavailable")
    job = state["jobs"][0]
    decision = job["observations"][-1]
    if context == "no_route_decision":
        job["observations"].remove(decision)
    elif context == "later_route_decision":
        job["observations"].append(
            decision | {"field_id": "phone", "route_reason": "supported_cua_readonly"}
        )
    else:
        decision["dispatch"] = "sent"
    native.store.save(state)
    assert native.takeover_candidate(identifier, **expected(native)) is None


def test_one_job_continues_after_100_takeovers_and_keeps_its_failed_blocker(
    retained_assistance_page, monkeypatch
):
    """Settled takeovers never use up the limit; a failed blocker is still never re-sent."""
    from career_evidence_graph.application_takeover_record import SETTLED_HISTORY_RETAINED
    from career_evidence_graph.application_worker import record_takeover_failure

    service, identifier = retained_assistance_page
    native = takeover_service(service, monkeypatch)
    block(native, "unsupported_control", field="email")
    take_over(native, identifier, "takeover-failed")
    state = native.store.load()
    assert record_takeover_failure(
        state["jobs"][0], request_id="takeover-failed", code="native_assistance_unavailable"
    )
    native.store.save(state)
    end_in_wait(native, "native_assistance_unavailable")
    for index in range(100):
        resume(native)
        block(native, "unsupported_control")
        take_over(native, identifier, f"takeover-{index}")
        end_in_wait(native)
    job = native.store.load()["jobs"][0]
    assert job["assistance"]["generation"] == 101
    assert len(job["assistance_history"]) <= 1 + SETTLED_HISTORY_RETAINED
    resume(native)
    block(native, "unsupported_control")
    assert native.takeover_candidate(identifier, **expected(native)) is not None
    block(native, "unsupported_control", field="email")
    assert native.takeover_candidate(identifier, **expected(native)) is None
