"""Late read-only missing questions cannot replace newer local decisions."""

from copy import deepcopy

import pytest
from test_application_worker import job
from test_application_worker import service as service
from test_current_email_correction import email_flow as email_flow
from test_flow_retained_review import retained_flow as retained_flow

from career_evidence_graph.application_execution import (
    automated_owner,
    release_execution,
    reserve_execution,
)
from career_evidence_graph.application_worker import start_run
from career_evidence_graph.application_worker_browser import ApplicationRunner


def waiting(service, *, additional=False):
    service.request("prepare", {"jobs": [job(service, 1), job(service, 2)]})
    service.request("resume", {"controller": "synthetic-controller"})
    state = service.store.load()
    question = {
        "id": "sponsorship",
        "question": "Will you now or in the future require visa sponsorship?",
        "options": ["Yes", "No"],
        "required": True,
        "type": "select",
        "value": "",
        "valid": False,
    }
    questions = [question]
    if additional:
        questions.append({**question, "id": "start", "question": "Start date", "options": []})
    for current in state["jobs"]:
        current.update(
            status="needs_input", reason="missing_answers", questions=deepcopy(questions)
        )
    service.store.save(state)
    sampled = deepcopy(state["jobs"][0])
    runner = ApplicationRunner(service.store, None, service.fixture_origin)
    service.request("pause", {"controller": "synthetic-controller"})
    return runner, sampled, state["batch_id"], questions


def publish(runner, sampled, batch, questions, *, stop=False):
    changes = {"questions": questions}
    if stop:
        changes.update(status="needs_input", reason="missing_answers", intent=None)
    runner.update(sampled, batch, **changes)


def answer(service, sampled, *, only_this=False):
    service.request(
        "answer",
        {
            "application_id": sampled["application_id"],
            "question_id": "sponsorship",
            "value": "Yes",
            "scope": {"country": "CHE"},
            "only_this": only_this,
        },
    )


@pytest.mark.parametrize("late_questions", [False, True])
@pytest.mark.parametrize("only_this", [False, True])
def test_saved_answer_queue_survives_both_late_missing_publications(
    service, late_questions, only_this
):
    runner, sampled, batch, questions = waiting(service)
    if not late_questions:
        publish(runner, sampled, batch, questions)
    answer(service, sampled, only_this=only_this)
    queued = service.store.load()
    assert queued["control"] == "paused"
    assert queued["jobs"][0]["status"] == "queued" and queued["jobs"][0]["questions"] == []
    if only_this:
        assert queued["jobs"][1]["status"] == "needs_input"
    library = deepcopy(service.store.library())
    if late_questions:
        publish(runner, sampled, batch, questions)
        assert service.store.load()["jobs"][0]["questions"] == []
    publish(runner, sampled, batch, questions, stop=True)
    after = service.store.load()
    assert after["control"] == "paused" and after["commands"] == queued["commands"]
    assert after["jobs"][0]["status"] == "queued" and after["jobs"][0]["questions"] == []
    assert after["jobs"][0]["intent"] is None
    assert service.store.library() == library and runner.temporary == {}


def test_partial_answer_keeps_only_the_genuinely_missing_question(service):
    runner, sampled, batch, questions = waiting(service, additional=True)
    answer(service, sampled)
    publish(runner, sampled, batch, questions)
    publish(runner, sampled, batch, questions, stop=True)
    after = service.store.load()
    assert after["control"] == "paused"
    assert after["jobs"][0]["status"] == "needs_input"
    assert after["jobs"][0]["questions"] == [questions[1]]


def test_other_country_answer_does_not_remove_this_jobs_question(service):
    runner, sampled, batch, questions = waiting(service)
    service.store.answers.put_answer(
        {
            "question": questions[0]["question"],
            "value": "Yes",
            "scope": {"country": "USA"},
            "state": "confirmed",
        }
    )
    publish(runner, sampled, batch, questions, stop=True)
    after = service.store.load()
    assert after["control"] == "paused"
    assert after["jobs"][0]["status"] == "needs_input"
    assert after["jobs"][0]["questions"] == questions


@pytest.mark.parametrize("kind", ["pending", "temporary", "other-job", "invalid-option"])
def test_one_use_answers_are_read_without_consuming_commands_or_persisting_them(service, kind):
    runner, sampled, batch, questions = waiting(service)
    state = service.store.load()
    current = state["jobs"][0]
    current.update(status="queued", reason="", questions=[])
    identifier = (
        state["jobs"][1]["application_id"] if kind == "other-job" else current["application_id"]
    )
    record = {
        "key": "one-use",
        "question": "sponsorship_now_future",
        "value": "Yes",
        "scope": {"application_id": identifier},
        "state": "confirmed",
    }
    if kind == "temporary":
        runner.temporary[identifier] = {"sponsorship_now_future": record}
    else:
        state["commands"].append(
            {
                "action": "one-use",
                "id": identifier,
                "fact": "sponsorship_now_future",
                "value": "Maybe" if kind == "invalid-option" else "Yes",
            }
        )
    service.store.save(state)
    temporary = deepcopy(runner.temporary)
    before = deepcopy(service.store.load())
    publish(runner, sampled, batch, questions, stop=True)
    after = service.store.load()
    assert after["control"] == "paused" and after["commands"] == before["commands"]
    assert runner.temporary == temporary and service.store.library() == []
    if kind in {"pending", "temporary"}:
        assert after["jobs"][0]["status"] == "queued" and after["jobs"][0]["questions"] == []
    else:
        assert after["jobs"][0]["status"] == "needs_input"
        assert after["jobs"][0]["questions"] == questions


@pytest.mark.parametrize(
    "changed",
    [
        "unknown",
        "successor",
        "ready",
        "handoff",
        "cancelled",
        "batch",
        "selection",
        "run",
        "form",
        "owner",
    ],
)
def test_late_missing_result_cannot_replace_a_newer_stop_or_execution_context(service, changed):
    runner, sampled, batch, questions = waiting(service)
    state = service.store.load()
    current = state["jobs"][0]
    current.update(status="queued", reason="", questions=[])
    if changed == "unknown":
        current.update(status="needs_recheck", reason="browser_result_unknown")
    elif changed == "successor":
        current.update(status="filling", intent={"action": "upload", "attempt_id": "new-attempt"})
    elif changed == "ready":
        current.update(status="ready_for_review")
    elif changed == "handoff":
        current.update(handed_off=True)
    elif changed == "cancelled":
        current.update(status="cancelled")
    elif changed == "batch":
        state["batch_id"] = "c" * 32
    elif changed == "selection":
        for row in state["jobs"]:
            row["workflow"] = "single"
        state["current_job_id"] = state["jobs"][1]["application_id"]
    elif changed == "form":
        current["form_state"] = {"binding": {"document_token": "new-document"}}
    service.store.save(state)
    if changed == "run":
        start_run(service.store)
    elif changed == "owner":
        owner = automated_owner(service.store.root, batch, sampled["application_id"])
        release_execution(service.store.applications, sampled["application_id"], owner, "automated")
        reserve_execution(
            service.store.applications, sampled["application_id"], "new-human-owner", "codex"
        )
    before = service.store.path.read_bytes()
    publish(runner, sampled, batch, questions)
    publish(runner, sampled, batch, questions, stop=True)
    assert service.store.path.read_bytes() == before


@pytest.mark.parametrize("changed", ["unknown", "batch"])
def test_process_stops_after_rejected_question_publication(service, monkeypatch, changed):
    import time

    from career_evidence_graph import application_form_runner as form_flow
    from career_evidence_graph.application_form_state import sample

    runner, sampled, batch, _ = waiting(service)
    service.request("resume", {"controller": "synthetic-controller"})
    page = type("ObservedPage", (), {"url": sampled["job_url"]})()
    runner.pages[sampled["application_id"]] = page
    runner.page_ids[page] = "original-page"
    observed = {
        "fields": [
            {
                "id": "resume",
                "question": "Resume",
                "type": "file",
                "resume": True,
                "value": sampled["filename"],
                "filename": sampled["filename"],
                "file_sha256": sampled["file_sha256"],
                "valid": True,
                "required": True,
                "multiple": False,
                "options": [],
                "draft_path": "",
            }
        ],
        "upload": {
            "state": "complete",
            "sha256": sampled["file_sha256"],
            "name": sampled["filename"],
        },
        "document_token": "original-document",
        "parser": {"status": "complete"},
    }
    binding = {
        "run_id": runner.run_id,
        "page_id": runner.page_ids[page],
        "document_token": observed["document_token"],
        "step": page.url,
    }
    form = None
    now = time.time()
    for offset in (-1, -0.75, -0.5):
        form = sample(form, observed, binding=binding, now=now + offset)
    state = service.store.load()
    state["jobs"][0].update(status="filling", reason="", questions=[], form_state=form)
    service.store.save(state)
    sampled = deepcopy(state["jobs"][0])
    monkeypatch.setattr(runner, "observe", lambda *_: deepcopy(observed))
    save_plan = form_flow.save_plan
    stopped = []

    def stop_after_plan(*args, **kwargs):
        save_plan(*args, **kwargs)
        latest = service.store.load()
        if changed == "unknown":
            latest["jobs"][0].update(status="needs_recheck", reason="browser_result_unknown")
        else:
            latest["batch_id"] = "d" * 32
        service.store.save(latest)
        stopped.append(deepcopy(latest))

    monkeypatch.setattr(form_flow, "save_plan", stop_after_plan)
    finished = []
    finish_materials = runner.finish_materials

    def record_finish(*args, **kwargs):
        finished.append(kwargs.get("upload_only", False))
        return finish_materials(*args, **kwargs)

    monkeypatch.setattr(runner, "finish_materials", record_finish)
    runner.process(sampled, batch)
    assert stopped
    # The already verified attachment is read once before the plan is published.
    # Rejected publication cannot continue into final readiness or another action.
    assert finished == [True]
    assert service.store.load() == stopped[0]
    assert runner.sent_requests == set()


def test_pure_ready_result_cannot_replace_a_public_email_correction_stop(email_flow):
    owner, _, binding = email_flow
    worker = owner.worker_service
    state = worker.store.load()
    current = state["jobs"][0]
    old_intent = deepcopy(current["intent"])
    current["answer_refs"] = [{**old_intent["answer_ref"], "field_id": binding["field_id"]}]
    current["observations"].append(
        {
            "action": "fill",
            "verified": True,
            "field_id": binding["field_id"],
            "run_id": binding["run_id"],
            "intent": old_intent,
        }
    )
    current.update(status="filling", reason="", intent=None)
    worker.store.save(state)
    sampled = deepcopy(current)
    runner = ApplicationRunner(worker.store, None)
    worker.request(
        "correct-email",
        {
            "application_id": current["application_id"],
            "binding": binding,
            "value": "new@example.invalid",
        },
    )
    stopped = worker.store.load()
    assert stopped["control"] == "paused"
    assert stopped["jobs"][0]["status"] == "needs_recheck"
    assert stopped["jobs"][0]["reason"] == "email_correction_pending"
    assert stopped["jobs"][0]["intent"] is None
    before = worker.store.path.read_bytes()
    runner.update(sampled, state["batch_id"], status="ready_for_review", reason="", intent=None)
    assert worker.store.path.read_bytes() == before
    assert runner.sent_requests == set()


@pytest.mark.parametrize("explicit", [False, True])
def test_actual_late_completion_still_records_its_receipt_after_cancel(service, explicit):
    runner, sampled, batch, _ = waiting(service)
    service.request("resume", {"controller": "synthetic-controller"})
    intent = {"action": "upload", "sha256": sampled["file_sha256"]}
    assert runner.authorize(sampled, batch, intent)
    sampled = deepcopy(service.store.load()["jobs"][0])
    service.request("cancel-job", {"application_id": sampled["application_id"]})
    stopped = service.store.load()
    runner.update(
        sampled,
        batch,
        **({"completed_intent": intent} if explicit else {}),
        status="ready_for_review",
        reason="",
        intent=None,
    )
    after = service.store.load()
    assert after["control"] == stopped["control"]
    assert after["jobs"][0]["status"] == "cancelled"
    receipt = after["jobs"][0]["observations"][-1]
    assert receipt["action"] == "action_result" and receipt["result"] == "verified"
    assert receipt["intent"] == intent
    assert runner.sent_requests == set()
