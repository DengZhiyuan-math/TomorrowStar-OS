"""Legacy recheck hands verified current state to the existing form planner."""

from copy import deepcopy
from time import time
from types import SimpleNamespace

import pytest
from test_p07_runner import field, job_for, retained_runner

from career_evidence_graph import application_form_runner as flow
from career_evidence_graph.application_materials import SupplementalMaterials
from career_evidence_graph.career_portal_data import PortalDataError
from career_evidence_graph.validation.hashing import record_digest as digest


@pytest.mark.parametrize(
    "change,expected_retry",
    [
        ("none", True),
        ("third_value", False),
        ("answer_revision", False),
        ("desired_value", False),
        ("document", False),
        ("outer_identity", False),
        ("shape", False),
        ("prior_nonempty", False),
        ("missing_before", False),
        ("missing_document", False),
        ("empty_document", False),
        ("missing_shape", False),
        ("missing_reference", False),
        ("missing_run", False),
        ("missing_page", False),
        ("empty_reference", False),
        ("missing_reference_key", False),
        ("missing_reference_revision", False),
        ("missing_expected", False),
        ("empty_desired", False),
        ("false_desired", True),
        ("pending", False),
        ("unknown", False),
        ("manual_stop", False),
        ("intervention", False),
        ("parser_waiting", False),
        ("already_written", False),
        ("manual_keep", False),
    ],
)
def test_only_same_bound_unsaved_value_can_be_replanned(change, expected_retry):
    actual = field("saved@example.invalid")
    if change in {"missing_expected", "empty_desired"}:
        actual["value"] = None
    elif change == "false_desired":
        actual.update(value=False, type="checkbox")
    job, observed = job_for([actual])
    reference = {"key": "email", "revision": "one"}
    proposed = actual["value"]
    binding = job["form_state"]["binding"]
    intent = {
        "action": "fill",
        "attempt_id": "original",
        "form_protocol": "form-state/v1",
        "form_binding": deepcopy(binding),
        "run_id": binding["run_id"],
        "page_id": binding["page_id"],
        "field_id": actual["id"],
        "field_type": actual["type"],
        "field_shape": digest(
            {key: actual.get(key) for key in ("id", "type", "question", "options", "required")}
        ),
        "before_value": "",
        "expected_value": actual["value"],
        "answer_ref": deepcopy(reference),
    }
    resolution = {"intent_ref": "original", "intent": intent, "conclusion": "not_applied"}
    job["action_resolutions"] = [resolution]
    if change == "third_value":
        actual["value"] = "human@example.invalid"
    elif change == "answer_revision":
        reference["revision"] = "two"
    elif change == "desired_value":
        proposed = "new@example.invalid"
    elif change == "document":
        binding["document_token"] = "new-document"
    elif change == "outer_identity":
        intent["page_id"] = "old-page"
    elif change == "shape":
        actual["required"] = False
    elif change == "prior_nonempty":
        intent["before_value"] = "human@example.invalid"
    elif change == "missing_before":
        intent.pop("before_value")
    elif change == "missing_document":
        binding.pop("document_token")
        intent["form_binding"].pop("document_token")
    elif change == "empty_document":
        binding["document_token"] = intent["form_binding"]["document_token"] = ""
    elif change == "missing_shape":
        intent.pop("field_shape")
    elif change == "missing_reference":
        intent.pop("answer_ref")
    elif change == "missing_run":
        binding.pop("run_id")
        intent["form_binding"].pop("run_id")
        intent.pop("run_id")
    elif change == "missing_page":
        binding.pop("page_id")
        intent["form_binding"].pop("page_id")
        intent.pop("page_id")
    elif change == "empty_reference":
        reference.clear()
        intent["answer_ref"].clear()
    elif change == "missing_reference_key":
        reference.pop("key")
        intent["answer_ref"].pop("key")
    elif change == "missing_reference_revision":
        reference.pop("revision")
        intent["answer_ref"].pop("revision")
    elif change == "missing_expected":
        intent.pop("expected_value")
    elif change == "pending":
        job["intent"] = {"action": "fill", "attempt_id": "unknown"}
    elif change == "unknown":
        job["action_resolutions"] = []
    elif change == "manual_stop":
        job["action_resolutions"].append({**resolution, "conclusion": "manual_stop"})
    elif change == "intervention":
        job["form_state"]["intervention_pending"] = True
    elif change == "parser_waiting":
        job["form_state"]["parser"]["status"] = "waiting"
    elif change == "already_written":
        flow.note_write(job, actual, actual["value"], reference)
    elif change == "manual_keep":
        job["form_state"]["choices"] = {
            "keep": {
                "field_id": actual["id"],
                "binding": deepcopy(binding),
                "proposed_value": proposed,
                "source": deepcopy(reference),
                "value": actual["value"],
                "action": "keep",
            }
        }
    before = deepcopy(job)
    latest = {row["intent_ref"]: row for row in job["action_resolutions"]}
    retries = [row["intent"] for row in latest.values() if row["conclusion"] == "not_applied"]

    fills, kept = flow.plan(job, observed, [(actual, proposed, reference)], retry_intents=retries)

    assert bool(fills) is expected_retry
    if expected_retry:
        assert fills == [(actual, proposed, reference)] and kept == []
        # Completion is recorded through the existing write receipt; the old
        # failed attempt cannot make the same field a retry again.
        flow.note_write(job, actual, proposed, reference)
        assert (
            flow.plan(job, observed, [(actual, proposed, reference)], retry_intents=retries)[0]
            == []
        )
    assert job.get("intent") == before.get("intent")
    assert job["action_resolutions"] == before["action_resolutions"]
    if change in {"third_value", "desired_value"}:
        assert job["form_state"]["differences"]


@pytest.mark.parametrize(
    "failure", ["none", "new_document", "refresh_failed", "foreign_context", "old_run", "old_page"]
)
def test_recheck_acknowledges_only_successful_original_page_readback(
    tmp_path, monkeypatch, failure
):
    runner, page, job, batch = retained_runner(tmp_path, monkeypatch)
    context = object()
    runner.context = context
    page.context = object() if failure == "foreign_context" else context
    page.is_closed = lambda: False
    original = {"fields": [field("")], "document_token": "document"}
    flow.capture(runner, page, job, batch, original)
    state = runner.store.load()
    job = state["jobs"][0]
    job["form_state"]["intervention_pending"] = True
    if failure == "old_run":
        job["form_state"]["binding"]["run_id"] = "old-run"
    elif failure == "old_page":
        job["form_state"]["binding"]["page_id"] = "old-page"
    job["action_resolutions"] = [
        {"intent_ref": "original", "intent": {"action": "fill"}, "conclusion": "not_applied"}
    ]
    runner.store.save(state)
    before = runner.store.path.read_bytes()
    history = deepcopy(job["action_resolutions"])
    calls = []

    def refresh(observed_page, _resolutions):
        calls.append(observed_page)
        if failure == "refresh_failed":
            raise ValueError("Synthetic readback unavailable")

    runner.drafts[page] = SimpleNamespace(refresh=refresh)
    observed = {
        "fields": [field("human@example.invalid")],
        "document_token": "new-document" if failure == "new_document" else "document",
        "user_activity": {"email": 1},
    }
    monkeypatch.setattr(runner, "observe_pending", lambda *_: deepcopy(observed))
    if failure == "refresh_failed":
        with pytest.raises(ValueError, match="Synthetic readback unavailable"):
            runner._command(state, {"action": "recheck", "id": job["application_id"]})
        assert runner.store.path.read_bytes() == before
    elif failure in {"foreign_context", "old_run", "old_page"}:
        with pytest.raises(PortalDataError):
            runner._command(state, {"action": "recheck", "id": job["application_id"]})
        assert runner.store.path.read_bytes() == before
        assert calls == []
    else:
        runner._command(state, {"action": "recheck", "id": job["application_id"]})
        assert calls == [page]
        assert not job["form_state"].get("intervention_pending")
        assert job["form_state"]["parser"]["status"] == "waiting"
        assert job["action_resolutions"] == history
        if failure == "new_document":
            # The command loop persists its outer state after capture's write.
            # It must retain the previous document's original baseline too.
            runner.persist(state)
            retained = runner.store.load()["jobs"][0]
            assert retained["form_history"][-1]["baseline"] == {"email": field("")}
            assert retained["form_state"]["binding"]["document_token"] == "new-document"
        fills, kept = flow.plan(
            job, observed, [(observed["fields"][0], "saved@example.invalid", {"key": "saved"})]
        )
        assert fills == kept == [] and job["form_state"]["differences"]


@pytest.mark.parametrize("change", ["same_value_activity", "other_field_activity", "document"])
def test_late_activity_or_document_change_prevents_same_value_retry(tmp_path, monkeypatch, change):
    runner, page, job, batch = retained_runner(tmp_path, monkeypatch)
    runner.store.answers.put_answer(
        {
            "question": "Email",
            "value": "synthetic@example.invalid",
            "scope": {},
            "state": "confirmed",
        }
    )
    actual = field(
        "synthetic@example.invalid", options=[], multiple=False, resume=False, draft_path="email"
    )
    observed = {
        "fields": [actual],
        "stage": "form",
        "document_token": "document",
        "parser": {"status": "complete"},
        "user_activity": {},
    }
    now = time()
    for moment in (now, now + 0.25, now + 0.5):
        monkeypatch.setattr(flow.time, "time", lambda moment=moment: moment)
        flow.capture(runner, page, job, batch, observed)
    state = runner.store.load()
    job = state["jobs"][0]
    reference = runner.store.resolve(actual, job, runner.temporary)[1]
    intent = {
        "action": "fill",
        "attempt_id": "failed-attempt",
        "form_protocol": "form-state/v1",
        "form_binding": deepcopy(job["form_state"]["binding"]),
        "run_id": runner.run_id,
        "page_id": runner.page_ids[page],
        "field_id": actual["id"],
        "field_type": actual["type"],
        "field_shape": digest(
            {key: actual.get(key) for key in ("id", "type", "question", "options", "required")}
        ),
        "before_value": "",
        "expected_value": actual["value"],
        "answer_ref": reference,
        "executor": "playwright",
        "input_route": "dom",
    }
    job["action_resolutions"] = [
        {"intent_ref": intent["attempt_id"], "intent": intent, "conclusion": "not_applied"}
    ]
    state["control"] = "running"
    runner.store.save(state)
    monkeypatch.setattr(runner, "observe", lambda *_: deepcopy(observed))
    monkeypatch.setattr(runner, "check_inputs", lambda *_args, **_options: None)
    monkeypatch.setattr(runner, "finish_materials", lambda *_args, **_options: False)
    monkeypatch.setattr(SupplementalMaterials, "prepare", lambda *_args, **_options: True)
    monkeypatch.setattr(
        "career_evidence_graph.application_worker_browser.select_fill_route",
        lambda *_: {
            "executor": "playwright",
            "input_route": "dom",
            "route_reason": "supported_synthetic_field",
        },
    )
    sent = []

    class ReachedDispatch(Exception):
        pass

    def begin(*_args):
        sent.append(True)
        raise ReachedDispatch

    runner.drafts[page] = SimpleNamespace(saved=lambda *_: False, begin=begin)
    authorize = runner.authorize

    def late_change(*args):
        allowed = authorize(*args)
        if allowed:
            if change == "document":
                observed["document_token"] = "replacement-document"
            else:
                observed["user_activity"][
                    "email" if change == "same_value_activity" else "name"
                ] = 1
        return allowed

    monkeypatch.setattr(runner, "authorize", late_change)
    error = None
    try:
        runner.process(job, batch)
    except ReachedDispatch:
        pass
    except PortalDataError as caught:
        error = caught
    assert sent == [], "A late trusted event or new document must stop the original planned write"
    assert error is not None and error.code == "form_changed"


@pytest.mark.parametrize("kind", ["readback", "late_failure", "successor_intent"])
def test_recheck_retains_transport_and_unknown_state_after_command_loop_save(
    tmp_path, monkeypatch, kind
):
    runner, page, job, batch = retained_runner(tmp_path, monkeypatch)
    runner.context = page.context = object()
    page.is_closed = lambda: False
    observed = {"fields": [field("")], "document_token": "document"}
    flow.capture(runner, page, job, batch, observed)
    state = runner.store.load()
    job = state["jobs"][0]
    job["action_resolutions"] = [
        {"intent_ref": "original", "intent": {"action": "fill"}, "conclusion": "not_applied"}
    ]
    runner.store.save(state)
    intent = {
        "action": "fill",
        "attempt_id": "late-unknown",
        "run_id": runner.run_id,
        "page_id": runner.page_ids[page],
    }
    successor = {**intent, "attempt_id": "successor-unknown"}
    event = {
        "application_id": job["application_id"],
        "batch_id": batch,
        "run_id": runner.run_id,
        "request_id": "readback-during-refresh",
        "stage": "requestfinished" if kind == "readback" else "requestfailed",
        **({} if kind == "readback" else {"intent": intent}),
    }

    def refresh(_page, _results):
        runner.transports.append(deepcopy(event))
        if kind == "successor_intent":
            job.update(
                intent=deepcopy(successor), status="needs_recheck", reason="successor_unknown"
            )

    runner.drafts[page] = SimpleNamespace(refresh=refresh)
    monkeypatch.setattr(runner, "observe_pending", lambda *_: deepcopy(observed))
    with runner.store.applications.write_lock():
        runner._command(state, {"action": "recheck", "id": job["application_id"]})
        assert runner.transports == []
        runner.persist(state)
    retained = runner.store.load()["jobs"][0]
    assert event in retained["observations"]
    assert retained["action_resolutions"] == job["action_resolutions"]
    if kind == "late_failure":
        assert retained["intent"] == intent
        assert (
            retained["status"] == "needs_recheck" and retained["reason"] == "draft_result_unknown"
        )
    elif kind == "successor_intent":
        assert retained["intent"] == successor
        assert retained["status"] == "needs_recheck" and retained["reason"] == "successor_unknown"


@pytest.mark.parametrize(
    "action,failed_write",
    [("continue-current", False), ("continue-current", True), ("review", True)],
)
def test_current_page_commands_keep_transport_and_unknown_state(
    tmp_path, monkeypatch, action, failed_write
):
    runner, page, job, batch = retained_runner(tmp_path, monkeypatch)
    runner.context = page.context = object()
    page.is_closed = lambda: False
    page.unroute = lambda *_: pytest.fail("An unknown write cannot release the page guard")
    page.bring_to_front = lambda: pytest.fail("An unknown write cannot finish a page handoff")
    original = {"fields": [field("")], "document_token": "original-document"}
    flow.capture(runner, page, job, batch, original)
    state = runner.store.load()
    job = state["jobs"][0]
    controller = "synthetic-controller"
    state.update(control="paused", controller=controller, current_job_id=job["application_id"])
    job["workflow"] = "single"
    # Input admission has separate coverage; this case exercises one loaded
    # current-job command state through capture and the final outer save.
    monkeypatch.setattr(runner, "check_inputs", lambda *_args, **_options: None)
    job.update(status="ready_for_review" if action == "review" else "needs_recheck", page_open=True)
    command = {"action": action, "id": job["application_id"]}
    if action == "continue-current":
        job["continuation"] = {
            "request_id": "current-page-continue",
            "status": "pending",
            "run_id": runner.run_id,
            "page_id": runner.page_ids[page],
        }
        command.update(request_id="current-page-continue", controller=controller)
    state["commands"] = [command]
    runner.store.save(state)
    intent = {
        "action": "fill",
        "attempt_id": "late-unknown",
        "run_id": runner.run_id,
        "page_id": runner.page_ids[page],
    }
    event = {
        "application_id": job["application_id"],
        "batch_id": batch,
        "run_id": runner.run_id,
        "request_id": "readback-before-current-command",
        "stage": "requestfailed" if failed_write else "requestfinished",
        **({"intent": intent} if failed_write else {}),
    }
    observed = {
        "fields": [field("human@example.invalid")],
        "document_token": "new-document",
        "user_activity": {"email": 1},
    }
    monkeypatch.setattr(runner, "observe", lambda *_: deepcopy(observed))
    monkeypatch.setattr(runner, "observe_pending", lambda *_: deepcopy(observed))
    runner.transports.append(deepcopy(event))
    with runner.store.applications.write_lock():
        runner.commands(state)
        runner.persist(state)
    retained = runner.store.load()["jobs"][0]
    assert event in retained["observations"]
    assert retained["form_history"][-1]["baseline"] == {"email": field("")}
    assert retained["form_state"]["binding"]["document_token"] == "new-document"
    if failed_write:
        assert retained["intent"] == intent
        assert retained["status"] == "needs_recheck"
        assert retained["reason"] == "action_result_unknown"
        if action == "review":
            assert retained["handoff"]["status"] == "unknown"
            assert retained["handoff"].get("human_reviewed") is not True
        else:
            assert not retained["handed_off"]
    else:
        assert retained["intent"] is None
        assert retained["continuation"]["status"] == "verified"
