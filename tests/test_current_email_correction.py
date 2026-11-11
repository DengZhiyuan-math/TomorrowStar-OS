"""Current-job email corrections retain independent old-action evidence."""

from copy import deepcopy
from threading import Thread

import pytest
from test_flow_retained_review import retained_flow as retained_flow
from test_portal_workflow_browser import browser_page as browser_page

from career_evidence_graph.application_worker import digest
from career_evidence_graph.career_portal_data import PortalDataError


@pytest.fixture
def email_flow(retained_flow):
    owner, _, task = retained_flow
    worker = owner.worker_service
    state = worker.store.load()
    job = state["jobs"][0]
    old = {
        "key": "one-use",
        "question": "email",
        "value": "old@example.invalid",
        "scope": {"application_id": task["application_id"]},
        "state": "confirmed",
    }
    old_ref = {"key": "one-use", "revision": digest(old), "fact": "email"}
    job["intent"] = {
        "action": "fill",
        "attempt_id": "synthetic-email-fill",
        "run_id": state["runtime"]["id"],
        "page_id": job["page_observation"]["page_id"],
        "field_id": "observed-email-field",
        "fact": "email",
        "answer_ref": old_ref,
    }
    job["questions"] = []
    worker.store.save(state)
    binding = {
        "application_id": task["application_id"],
        "task_id": task["id"],
        "batch_id": state["batch_id"],
        "job_url": job["job_url"],
        "run_id": state["runtime"]["id"],
        "page_id": job["page_observation"]["page_id"],
        "field_id": "observed-email-field",
    }
    return owner, task, binding


def flow_action(owner, operation, payload):
    task = owner.application_flow_service.snapshot()["active_task"]
    return owner.application_flow_service.request(
        "worker-action",
        {
            "task_id": task["id"],
            "task_revision": task["revision"],
            "operation": operation,
            "payload": payload,
        },
    )


def test_flow_records_email_correction_when_no_missing_email_without_resolving_old_action(
    email_flow,
):
    owner, task, binding = email_flow
    worker = owner.worker_service
    before = deepcopy(worker.store.load())
    library = worker.store.library()
    pdf = owner.application_resume_store.pdf(task["resume_id"])

    flow_action(
        owner,
        "correct-email",
        {"binding": binding, "value": "new@example.invalid"},
    )

    current = worker.snapshot()
    job = current["jobs"][0]
    assert current["control"] == "paused" and current["commands"] == []
    assert job["status"] == "needs_recheck"
    assert job["intent"] == before["jobs"][0]["intent"]
    assert job.get("action_resolutions", []) == []
    assert job["answer_refs"] == before["jobs"][0]["answer_refs"]
    assert worker.store.library() == library
    assert owner.application_resume_store.pdf(task["resume_id"]) == pdf
    assert job["email_corrections"][-1]["value"] == "new@example.invalid"
    assert job["email_corrections"][-1]["binding"] == binding
    assert job["email_corrections"][-1]["scope"] == {"application_id": task["application_id"]}
    assert job["email_correction_status"] == "staged"


@pytest.mark.parametrize("conclusion", ["current_matches", "not_applied"])
def test_only_explicit_resolved_recheck_queues_email_for_existing_worker_once(
    email_flow, conclusion
):
    owner, task, binding = email_flow
    worker = owner.worker_service
    pending = deepcopy(worker.store.load()["jobs"][0]["intent"])
    flow_action(owner, "correct-email", {"binding": binding, "value": "new@example.invalid"})
    with pytest.raises(PortalDataError) as error:
        flow_action(owner, "recheck", {"acknowledge": True})
    assert error.value.code == "action_unresolved"
    assert worker.snapshot()["commands"] == []
    flow_action(
        owner,
        "resolve-action",
        {
            "intent_ref": pending["attempt_id"],
            "conclusion": conclusion,
            "source": "User inspected the original synthetic email field.",
        },
    )

    flow_action(owner, "recheck", {"acknowledge": True})

    result = worker.snapshot()
    current = result["jobs"][0]
    assert result["control"] == "paused"
    assert current["intent"] is None
    assert current["answer_refs"] == []
    assert current["action_resolutions"][-1]["intent"] == pending
    assert current["action_resolutions"][-1]["conclusion"] == conclusion
    assert current["email_correction_status"] == "queued"
    assert [c for c in result["commands"] if c["action"] == "one-use"] == [
        {
            "action": "one-use",
            "id": task["application_id"],
            "fact": "email",
            "value": "new@example.invalid",
        }
    ]
    assert not any(event.get("action") == "fill" for event in current["observations"])
    flow_action(owner, "recheck", {"acknowledge": True})
    assert len([c for c in worker.snapshot()["commands"] if c["action"] == "one-use"]) == 1


def test_submitted_application_record_cannot_accept_email_correction(email_flow):
    owner, task, binding = email_flow
    store = owner.worker_service.store
    app = store.applications.get_application(task["application_id"])
    store.applications.update_application(app["id"], {"status": "applied"}, app["revision"])
    before = store.path.read_bytes()
    with pytest.raises(PortalDataError) as error:
        flow_action(owner, "correct-email", {"binding": binding, "value": "new@example.invalid"})
    assert error.value.code == "already_submitted"
    assert store.path.read_bytes() == before


@pytest.mark.parametrize(
    "value",
    [None, True, "", "broken", "two@@example.invalid", "x@y.invalid\n", "a" * 255 + "@x.invalid"],
)
def test_malformed_email_is_rejected_without_mutation(email_flow, value):
    owner, _, binding = email_flow
    store = owner.worker_service.store
    before = store.path.read_bytes()
    with pytest.raises(PortalDataError) as error:
        flow_action(owner, "correct-email", {"binding": binding, "value": value})
    assert error.value.code == "email_required"
    assert store.path.read_bytes() == before


@pytest.mark.parametrize(
    "part", ["application_id", "task_id", "batch_id", "job_url", "run_id", "page_id", "field_id"]
)
def test_correction_cannot_replace_a_binding_from_the_current_flow(email_flow, part):
    owner, _, binding = email_flow
    store = owner.worker_service.store
    before = store.path.read_bytes()
    with pytest.raises(PortalDataError) as error:
        flow_action(
            owner,
            "correct-email",
            {"binding": binding | {part: "different"}, "value": "new@example.invalid"},
        )
    assert error.value.code == "email_correction_target_changed"
    assert store.path.read_bytes() == before


@pytest.mark.parametrize(
    "mutation",
    [
        "running",
        "cancelled-control",
        "cancelled-job",
        "manual-submission",
        "missing-field",
        "ambiguous-field",
        "stale-page",
        "closed-page",
        "old-intent-page",
        "old-intent-run",
        "batch-workflow",
    ],
)
def test_correction_requires_paused_current_unique_single_job_email(email_flow, mutation):
    owner, _, binding = email_flow
    store = owner.worker_service.store
    state = store.load()
    job = state["jobs"][0]
    if mutation == "running":
        state["control"] = "running"
    elif mutation == "cancelled-control":
        state["control"] = "cancelled"
    elif mutation == "cancelled-job":
        job["status"] = "cancelled"
    elif mutation == "manual-submission":
        job["manual_submission"] = {"source": "user_confirmation"}
    elif mutation == "missing-field":
        job["intent"] = None
    elif mutation == "ambiguous-field":
        job["answer_refs"] = [
            {
                "fact": "email",
                "field_id": "another-email-field",
                "key": "one-use",
                "revision": "f" * 64,
            }
        ]
    elif mutation == "stale-page":
        state["runtime"]["observed_at"] = 1
    elif mutation == "closed-page":
        job["page_observation"]["event"] = "closed"
    elif mutation == "old-intent-page":
        job["intent"]["page_id"] = "previous-page"
    elif mutation == "old-intent-run":
        job["intent"]["run_id"] = "previous-run"
    elif mutation == "batch-workflow":
        job["workflow"] = "batch"
    store.save(state)
    before = store.path.read_bytes()
    with pytest.raises(PortalDataError):
        flow_action(owner, "correct-email", {"binding": binding, "value": "new@example.invalid"})
    assert store.path.read_bytes() == before


@pytest.mark.parametrize("mutation", ["run", "page", "field", "running", "cancelled", "submitted"])
def test_staged_correction_does_not_transfer_after_its_target_or_control_changes(
    email_flow, mutation
):
    owner, _, binding = email_flow
    store = owner.worker_service.store
    flow_action(owner, "correct-email", {"binding": binding, "value": "new@example.invalid"})
    flow_action(
        owner,
        "resolve-action",
        {
            "intent_ref": "synthetic-email-fill",
            "conclusion": "current_matches",
            "source": "User inspected old value.",
        },
    )
    state = store.load()
    job = state["jobs"][0]
    if mutation == "run":
        state["runtime"]["id"] = "successor-run"
        job["page_observation"]["run_id"] = "successor-run"
    elif mutation == "page":
        job["page_observation"]["page_id"] = "successor-page"
    elif mutation == "field":
        job["intent"]["field_id"] = "successor-field"
    elif mutation == "running":
        state["control"] = "running"
    elif mutation == "cancelled":
        job["status"] = "cancelled"
    elif mutation == "submitted":
        job["manual_submission"] = {"source": "user_confirmation"}
    store.save(state)
    before = store.path.read_bytes()
    with pytest.raises(PortalDataError):
        flow_action(owner, "recheck", {"acknowledge": True})
    assert store.path.read_bytes() == before
    assert store.load()["commands"] == []


def test_cross_job_email_correction_is_rejected_by_current_flow(email_flow):
    owner, _, binding = email_flow
    store = owner.worker_service.store
    before = store.path.read_bytes()
    with pytest.raises(PortalDataError) as error:
        flow_action(
            owner,
            "correct-email",
            {"application_id": "another-job", "binding": binding, "value": "new@example.invalid"},
        )
    assert error.value.code == "flow_worker_mismatch"
    assert store.path.read_bytes() == before


@pytest.mark.parametrize("proof", ["fill", "current_matches"])
def test_confirmed_email_reference_can_be_corrected_and_blocks_resume_until_recheck(
    email_flow, proof
):
    owner, _, binding = email_flow
    store = owner.worker_service.store
    state = store.load()
    job = state["jobs"][0]
    job["answer_refs"] = [{**job["intent"]["answer_ref"], "field_id": binding["field_id"]}]
    if proof == "fill":
        job["observations"].append(
            {
                "action": "fill",
                "verified": True,
                "field_id": binding["field_id"],
                "run_id": binding["run_id"],
                "intent": deepcopy(job["intent"]),
            }
        )
    else:
        job["action_resolutions"] = [
            {
                "intent_ref": job["intent"]["attempt_id"],
                "conclusion": "current_matches",
                "run_id": binding["run_id"],
                "intent": deepcopy(job["intent"]),
                "source": "User inspected current original field.",
            }
        ]
    job.update(status="ready_for_review", reason="", intent=None)
    store.save(state)

    flow_action(owner, "correct-email", {"binding": binding, "value": "new@example.invalid"})

    result = owner.worker_service.snapshot()
    assert result["jobs"][0]["status"] == "needs_recheck"
    assert result["control"] == "paused" and result["commands"] == []
    assert result["jobs"][0]["answer_refs"][0]["revision"] == job["answer_refs"][0]["revision"]


def test_historical_email_reference_cannot_bind_to_a_new_runtime_or_page(email_flow):
    owner, _, _ = email_flow
    worker = owner.worker_service
    state = worker.store.load()
    job = state["jobs"][0]
    old_intent = deepcopy(job["intent"])
    job["answer_refs"] = [{**old_intent["answer_ref"], "field_id": old_intent["field_id"]}]
    job["observations"].append(
        {
            "action": "fill",
            "verified": True,
            "field_id": old_intent["field_id"],
            "run_id": old_intent["run_id"],
            "intent": old_intent,
        }
    )
    job["intent"] = None
    state["runtime"]["id"] = "new-runtime"
    job["page_observation"].update(run_id="new-runtime", page_id="new-page")
    worker.store.save(state)
    assert worker.snapshot()["jobs"][0]["email_correction_target"] is None


@pytest.mark.parametrize("change", ["restarted-run", "page", "field", "closed-page"])
def test_queued_email_correction_cannot_be_rechecked_against_a_changed_target(email_flow, change):
    from career_evidence_graph.application_worker import start_run

    owner, _, binding = email_flow
    worker = owner.worker_service
    flow_action(owner, "correct-email", {"binding": binding, "value": "new@example.invalid"})
    flow_action(
        owner,
        "resolve-action",
        {
            "intent_ref": "synthetic-email-fill",
            "conclusion": "current_matches",
            "source": "User inspected original synthetic field.",
        },
    )
    flow_action(owner, "recheck", {"acknowledge": True})
    assert worker.snapshot()["jobs"][0]["email_correction_status"] == "queued"
    if change == "restarted-run":
        run = start_run(worker.store)
    state = worker.store.load()
    job = state["jobs"][0]
    if change == "restarted-run":
        job["page_observation"].update(run_id=run, page_id="new-page")
        assert state["commands"] == []
    elif change == "page":
        job["page_observation"]["page_id"] = "new-page"
    elif change == "field":
        job["answer_refs"] = [
            {"fact": "email", "field_id": "new-field", "key": "one-use", "revision": "f" * 64}
        ]
    else:
        job["page_observation"]["event"] = "closed"
    worker.store.save(state)
    before = worker.store.path.read_bytes()
    with pytest.raises(PortalDataError) as error:
        flow_action(owner, "recheck", {"acknowledge": True})
    assert error.value.code == "email_correction_target_changed"
    assert worker.store.path.read_bytes() == before


def test_existing_runner_consumes_correction_while_paused_and_keeps_other_one_use_answers(
    email_flow,
):
    from career_evidence_graph.application_worker_browser import ApplicationRunner

    owner, task, binding = email_flow
    worker = owner.worker_service
    assert worker.process is None
    library_before = worker.store.library()
    state = worker.store.load()
    state["commands"].append(
        {
            "action": "one-use",
            "id": task["application_id"],
            "fact": "name",
            "value": "Synthetic Person",
        }
    )
    worker.store.save(state)
    runner = ApplicationRunner(worker.store, None)
    runner.tick()
    assert worker.store.library() == library_before
    flow_action(owner, "correct-email", {"binding": binding, "value": "new@example.invalid"})
    flow_action(
        owner,
        "resolve-action",
        {
            "intent_ref": "synthetic-email-fill",
            "conclusion": "current_matches",
            "source": "User inspected old value.",
        },
    )
    flow_action(owner, "recheck", {"acknowledge": True})

    runner.tick()

    result = worker.snapshot()
    job = result["jobs"][0]
    assert result["control"] == "paused" and result["commands"] == []
    assert (
        worker.store.resolve({"question": "Email"}, job, runner.temporary)[0]
        == "new@example.invalid"
    )
    assert (
        worker.store.resolve({"question": "Full name"}, job, runner.temporary)[0]
        == "Synthetic Person"
    )
    assert worker.store.resolve({"question": "Email"}, job) is None
    assert job["answer_refs"] == []
    assert job["email_correction_status"] == "queued"
    assert not any(event.get("action") == "fill" for event in job["observations"])
    flow_action(owner, "recheck", {"acknowledge": True})
    assert not any(c["action"] == "one-use" for c in worker.snapshot()["commands"])


def test_email_correction_keeps_each_record_and_queues_only_latest_confirmed_value(email_flow):
    owner, _, binding = email_flow
    flow_action(owner, "correct-email", {"binding": binding, "value": "first@example.invalid"})
    flow_action(owner, "correct-email", {"binding": binding, "value": "latest@example.invalid"})
    state = owner.worker_service.snapshot()
    assert [row["value"] for row in state["jobs"][0]["email_corrections"]] == [
        "first@example.invalid",
        "latest@example.invalid",
    ]
    assert state["commands"] == []
    flow_action(
        owner,
        "resolve-action",
        {
            "intent_ref": "synthetic-email-fill",
            "conclusion": "current_matches",
            "source": "User inspected old value.",
        },
    )
    flow_action(owner, "recheck", {"acknowledge": True})
    assert [
        c["value"] for c in owner.worker_service.snapshot()["commands"] if c["action"] == "one-use"
    ] == ["latest@example.invalid"]


@pytest.mark.worker_browser
def test_email_correction_ui_survives_missing_question_without_resuming(email_flow, browser_page):
    from playwright.sync_api import expect

    owner, _, _ = email_flow
    thread = Thread(target=owner.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True)
    thread.start()
    try:
        page = browser_page
        page.goto(f"http://127.0.0.1:{owner.server_address[1]}/#flow")
        page.locator("#flow-worker-diagnostics > summary").click()
        expect(page.get_by_label("仅本岗位的新邮箱", exact=True)).to_be_visible()
        page.get_by_label("仅本岗位的新邮箱", exact=True).fill("new@example.invalid")
        page.get_by_role("button", name="记录本岗位邮箱更正", exact=True).click()
        expect(page.locator("#flow-email-correction")).to_contain_text("本岗位邮箱更正记录：")
        expect(page.locator("#flow-email-correction")).to_contain_text("更正记录不代替旧动作结论")
        state = owner.worker_service.snapshot()
        assert state["control"] == "paused" and state["commands"] == []
        assert state["jobs"][0]["intent"]["attempt_id"] == "synthetic-email-fill"
        assert state["jobs"][0]["email_corrections"][-1]["value"] == "new@example.invalid"
        page.reload()
        expect(page.locator("#flow-email-correction")).to_contain_text("new@example.invalid")
    finally:
        owner.shutdown()
        thread.join(timeout=3)
