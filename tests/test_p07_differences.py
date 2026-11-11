"""Concentrated ATS choices are bound local checkpoints, never library updates."""

import time
from copy import deepcopy

import pytest
from test_application_worker import job
from test_application_worker import service as service
from test_flow_retained_review import retained_flow as retained_flow
from test_portal_workflow_browser import browser_page as browser_page

from career_evidence_graph.application_worker import start_run
from career_evidence_graph.career_portal_data import PortalDataError


@pytest.fixture
def differences(service, monkeypatch):
    service.request("prepare", {"jobs": [job(service)]})
    start_run(service.store)
    state = service.store.load()
    current = state["jobs"][0]
    state["current_job_id"] = current["application_id"]
    state["runtime"].update(id="synthetic-run", observed_at=time.time())
    current.update(
        status="needs_input", reason="form_differences", page_open=True, workflow="single"
    )
    monkeypatch.setattr(service.store, "check_single", lambda *args, **kwargs: None)
    current["page_observation"] = {
        "run_id": "synthetic-run",
        "page_id": "synthetic-page",
        "event": "observed",
    }
    current["form_state"] = {
        "schema": "form-state/v1",
        "binding": {"run_id": "synthetic-run", "page_id": "synthetic-page", "step": "contact"},
        "revision": 1,
        "snapshot_sha256": "b" * 64,
        "parser": {"status": "stable"},
        "snapshot": {"validation_errors": []},
        "differences": [
            {
                "id": "email-difference",
                "field_id": "email",
                "question": "Email",
                "current_value": "human@example.invalid",
                "proposed_value": "record@example.invalid",
                "baseline_value": "human@example.invalid",
                "source": {"kind": "confirmed", "id": "synthetic-fact"},
                "important": True,
                "reason": "nonempty_conflict",
            }
        ],
        "choices": {},
    }
    service.store.save(state)
    return service, current


def payload(current, action="keep", **extra):
    form = current["form_state"]
    return {
        "application_id": current["application_id"],
        "binding": deepcopy(form["binding"]),
        "revision": form["revision"],
        "choices": [{"difference_id": "email-difference", "action": action, **extra}],
    }


@pytest.mark.parametrize(
    "action,value",
    [
        ("keep", "human@example.invalid"),
        ("use", "record@example.invalid"),
        ("edit", "edited@example.invalid"),
    ],
)
def test_concentrated_choice_is_local_and_does_not_continue(
    differences, monkeypatch, action, value
):
    service, current = differences
    before = deepcopy(service.store.load())
    library = service.store.library()
    monkeypatch.setattr(service, "spawn", lambda: pytest.fail("must not launch worker"))
    result = service.request(
        "resolve-form-differences",
        payload(current, action, **({"value": value} if action == "edit" else {})),
    )
    saved = result["jobs"][0]["form_state"]
    choice = saved["choices"]["email-difference"]
    assert choice["value"] == value
    assert choice["action"] == action
    assert choice["field_id"] == "email"
    assert choice["current_value"] == "human@example.invalid"
    assert choice["proposed_value"] == "record@example.invalid"
    assert choice["source"] == current["form_state"]["differences"][0]["source"]
    assert choice["snapshot_sha256"] == current["form_state"]["snapshot_sha256"]
    assert choice["binding"] == current["form_state"]["binding"]
    assert saved["differences"][0]["id"] == "email-difference"
    assert result["commands"] == before["commands"] == []
    assert result["control"] == before["control"] == "paused"
    assert result["jobs"][0]["answer_refs"] == before["jobs"][0]["answer_refs"]
    assert service.store.library() == library


@pytest.mark.parametrize(
    "change",
    [
        "revision",
        "binding",
        "current_job",
        "intent",
        "cancelled",
        "submitted",
        "page",
        "parser",
        "application_status",
    ],
)
def test_choice_rejects_changed_or_unavailable_target_without_mutation(differences, change):
    service, current = differences
    request = payload(current)
    state = service.store.load()
    saved = state["jobs"][0]
    if change == "revision":
        request["revision"] = 0
    elif change == "binding":
        request["binding"]["step"] = "other"
    elif change == "current_job":
        state["current_job_id"] = None
    elif change == "intent":
        saved["intent"] = {"action": "upload"}
    elif change == "cancelled":
        saved["status"] = "cancelled"
    elif change == "submitted":
        saved["manual_submission"] = {"at": time.time()}
    elif change == "application_status":
        application = service.store.applications.get_application(current["application_id"])
        service.store.applications.update_application(
            application["id"], {"status": "applied"}, application["revision"]
        )
    elif change == "page":
        saved["page_observation"]["page_id"] = "another-page"
    elif change == "parser":
        saved["form_state"]["parser"]["status"] = "active"
    service.store.save(state)
    before = service.store.path.read_bytes()
    with pytest.raises(PortalDataError):
        service.request("resolve-form-differences", request)
    assert service.store.path.read_bytes() == before


@pytest.mark.parametrize(
    "choices",
    [
        [],
        [{"difference_id": "absent", "action": "keep"}],
        [{"difference_id": "email-difference", "action": "other"}],
        [{"difference_id": "email-difference", "action": "edit", "value": None}],
        [{"difference_id": "email-difference", "action": "keep"}] * 2,
    ],
)
def test_malformed_choice_batch_does_not_partially_save(differences, choices):
    service, current = differences
    request = payload(current) | {"choices": choices}
    before = service.store.path.read_bytes()
    with pytest.raises(PortalDataError):
        service.request("resolve-form-differences", request)
    assert service.store.path.read_bytes() == before


@pytest.mark.parametrize(
    "condition",
    [
        "parser",
        "validation",
        "intent",
        "unresolved",
        "pending_use",
        "changed_current",
        "changed_source",
        "changed_proposed",
        "changed_binding",
        "intervention",
        "required_invalid",
    ],
)
def test_review_stops_before_handoff_until_new_form_evidence_is_complete(differences, condition):
    service, current = differences
    service.request("resolve-form-differences", payload(current))
    job_state = service.store.load()["jobs"][0]
    form = job_state["form_state"]
    if condition == "intervention":
        form["intervention_pending"] = True
    elif condition == "required_invalid":
        form["snapshot"]["fields"] = [{"required": True, "valid": False}]
    elif condition == "parser":
        form["parser"]["status"] = "active"
    elif condition == "validation":
        form["snapshot"]["validation_errors"] = ["Email invalid"]
    elif condition == "intent":
        job_state["intent"] = {"action": "upload"}
    elif condition == "unresolved":
        form["choices"] = {}
    elif condition == "pending_use":
        form["choices"]["email-difference"].update(action="use", value="record@example.invalid")
    elif condition == "changed_current":
        form["differences"][0]["current_value"] = "late@example.invalid"
    elif condition == "changed_source":
        form["differences"][0]["source"] = "different fact"
    elif condition == "changed_proposed":
        form["differences"][0]["proposed_value"] = "new@example.invalid"
    elif condition == "changed_binding":
        form["binding"]["step"] = "next-step"
    with pytest.raises(PortalDataError) as error:
        service._check_review(job_state)
    assert error.value.code == "form_review_pending"


@pytest.mark.parametrize("action", ["keep", "use", "edit"])
def test_review_accepts_current_choice_and_field_readback(differences, action):
    service, current = differences
    service.request(
        "resolve-form-differences",
        payload(
            current, action, **({"value": "edited@example.invalid"} if action == "edit" else {})
        ),
    )
    job_state = service.store.load()["jobs"][0]
    form = job_state["form_state"]
    form["differences"][0]["current_value"] = form["choices"]["email-difference"]["value"]
    form["revision"] += 1
    service._check_review(job_state)


def test_legacy_review_without_form_state_keeps_existing_contract(differences):
    service, current = differences
    current.pop("form_state")
    service._check_review(current)


@pytest.fixture
def flow_differences(retained_flow):
    owner, _, task = retained_flow
    worker = owner.worker_service
    state = worker.store.load()
    current = state["jobs"][0]
    current.update(status="needs_input", reason="form_differences", page_open=True, intent=None)
    current["form_state"] = {
        "schema": "form-state/v1",
        "binding": {
            "run_id": state["runtime"]["id"],
            "page_id": current["page_observation"]["page_id"],
            "step": "contact",
        },
        "revision": 1,
        "snapshot_sha256": "c" * 64,
        "parser": {"status": "stable"},
        "snapshot": {"validation_errors": []},
        "choices": {},
        "differences": [
            {
                "id": "email-difference",
                "field_id": "email",
                "question": "Email",
                "current_value": "human@example.invalid",
                "proposed_value": "record@example.invalid",
                "baseline_value": "human@example.invalid",
                "source": "Confirmed synthetic fact",
                "important": True,
                "reason": "nonempty_conflict",
            },
            {
                "id": "phone-difference",
                "field_id": "phone",
                "question": "Phone",
                "current_value": "+41 00",
                "proposed_value": "+41 11",
                "baseline_value": "+41 00",
                "source": None,
                "important": True,
                "reason": "nonempty_conflict",
            },
        ],
    }
    worker.store.save(state)
    return owner, task, current


def test_single_flow_accepts_concentrated_choices_without_answer_library_or_commands(
    flow_differences,
):
    from test_current_email_correction import flow_action

    owner, _, current = flow_differences
    worker = owner.worker_service
    library = worker.store.library()
    request = payload(current)
    request["choices"].append(
        {"difference_id": "phone-difference", "action": "edit", "value": "+41 22"}
    )
    flow_action(owner, "resolve-form-differences", request)
    state = worker.snapshot()
    assert state["commands"] == [] and state["control"] == "paused"
    assert state["jobs"][0]["form_state"]["choices"]["phone-difference"]["value"] == "+41 22"
    assert worker.store.library() == library


@pytest.mark.worker_browser
def test_single_flow_ui_batches_differences_and_retains_choices_after_reload(
    flow_differences, browser_page
):
    from threading import Thread

    from playwright.sync_api import expect

    owner, _, _ = flow_differences
    worker = owner.worker_service
    thread = Thread(target=owner.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True)
    thread.start()
    try:
        page = browser_page
        page.goto(f"http://127.0.0.1:{owner.server_address[1]}/#flow")
        section = page.locator("#flow-form-differences")
        expect(section).to_be_visible()
        expect(section).to_contain_text("来源未知")
        page.get_by_label("Email的差异选择", exact=True).select_option("keep")
        page.get_by_label("Phone的差异选择", exact=True).select_option("edit")
        page.get_by_label("Phone的手动值", exact=True).fill("+41 22")
        page.get_by_role("button", name="保存本次集中选择", exact=True).click()
        expect(section).to_contain_text("已记录本次选择")
        state = worker.snapshot()
        assert state["commands"] == [] and state["control"] == "paused"
        assert state["jobs"][0]["form_state"]["choices"]["phone-difference"]["value"] == "+41 22"
        page.reload()
        expect(page.get_by_label("Email的差异选择", exact=True)).to_have_value("keep")
        expect(page.get_by_label("Phone的手动值", exact=True)).to_have_value("+41 22")
    finally:
        owner.shutdown()
        thread.join(timeout=3)
