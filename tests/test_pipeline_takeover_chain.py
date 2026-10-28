"""MC-08/MC-09 synthetic chain: Pipeline auto-dispatch, Codex return, second takeover, faults."""

import time
from copy import deepcopy
from types import SimpleNamespace

import pytest
from test_single_application_worker import single_worker as single_worker
from test_worker_assistance_return_service import (
    COUNTRY_CLICK,
    Adapter,
    RunningAdapter,
    complete_page,
    make_report,
    returning,
    select_country,
    unknown_country_intent,
)
from test_worker_codex_assistance import block
from test_worker_codex_assistance import retained_assistance_page as retained_assistance_page
from test_worker_native_takeover import native_page as native_page

from career_evidence_graph._vendor import job_apply_store as helper
from career_evidence_graph.application_pipeline import POLICY, PROTOCOL, ApplicationPipeline
from career_evidence_graph.validation.hashing import record_digest as digest

_ = returning, native_page, single_worker, retained_assistance_page
PHONE_CLICK = (("native-type", "browser_click", {"role": "textbox", "name": "Phone"}),)


class ChainFlow:
    """Only the Flow surface the Pipeline reads while one Worker job is filling."""

    def __init__(self, root, worker, task):
        self.root, self.worker, self.applications = root, worker, worker.store.applications
        self.callbacks, self.task = {}, task

    def task_snapshot(self, task_id):
        return deepcopy(self.task) if task_id == self.task["id"] else None

    def snapshot(self, task_id=None):
        return {"tasks": [deepcopy(self.task)], "active_task": deepcopy(self.task)}

    def worker_action(self, task_id, revision, operation, payload):
        assert (task_id, revision) == (self.task["id"], self.task["revision"])
        self.worker.request(operation, payload | {"application_id": self.task["application_id"]})
        return deepcopy(self.task)

    def cancel_preparation(self, task_id, revision, **options):
        """Flow only stops its own preparation; the Pipeline stops the Worker."""
        assert (task_id, revision) == (self.task["id"], self.task["revision"])
        self.task["status"] = "cancelled"
        self.task["cancel_options"] = deepcopy(options)
        return deepcopy(self.task)


class Intake:
    def snapshot(self):
        return {"status": "idle", "recommendations": []}


def _until(predicate, timeout=5.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        value = predicate()
        if value:
            return value
        time.sleep(0.01)
    pytest.fail("condition not reached")


@pytest.fixture
def chain(returning, tmp_path):
    ctx = returning
    worker = ctx.service
    identifier = ctx.ref["binding"]["application_id"]
    with worker.store.applications.write_lock():
        # Start from the script's own run: the fixture's manual read-only claim is not used.
        state = worker.store.load()
        job = state["jobs"][0]
        job.pop("assistance")
        job.pop("native_handoff_runs", None)
        worker.store.save(state)
        state = worker.store.load()
    task = {
        "id": state["jobs"][0]["single_binding"]["task_id"],
        "application_id": identifier,
        "revision": "chain-task-v1",
        "status": "filling",
        "worker_ref": {"batch_id": state["batch_id"], "job_id": identifier, "status": "filling"},
    }
    root = tmp_path / "chain-flow"
    root.mkdir()
    record = {
        "schemaVersion": 1,
        "protocol": PROTOCOL,
        "policy_version": POLICY,
        "control": "running",
        "status": "filling",
        "id": "chain-pipeline",
        "request_id": "chain-start",
        "intake_run_id": None,
        "items": [
            {
                "application_id": identifier,
                "recommendation_id": "chain-recommendation",
                "task_id": task["id"],
                "status": "filling",
                "score": None,
            }
        ],
        "active_task_id": task["id"],
        "notification": None,
        "authorization": None,
        "transmission_authorization": None,
        "queue_mode": True,
        "controller": state["controller"],
        "current_recommendation_id": "chain-recommendation",
        "worker_batch_id": state["batch_id"],
        "worker_runtime_id": state["runtime"]["id"],
        "mail_poll_at": time.time() + 600,
    }
    record["revision"] = digest(record)
    helper.atomic_write_json(root / "pipeline.json", record)
    pipeline = ApplicationPipeline(ChainFlow(root, worker, task), Intake(), worker, interval=0.02)
    try:
        yield SimpleNamespace(**vars(ctx), pipeline=pipeline, identifier=identifier)
    finally:
        pipeline.close()


def _job(ctx):
    return ctx.service.store.load()["jobs"][0]


def _turn(ctx, *, planned, effect, report):
    adapter = Adapter(ctx.page, ctx.client, planned=list(planned), effect=effect, report=report)
    ctx.runner.codex_assist = adapter
    return adapter


def test_auto_dispatch_return_second_takeover_and_manual_submit_wait(chain):
    ctx = chain
    worker, pipeline, runner = ctx.service, ctx.pipeline, ctx.runner

    # 1. The script cannot handle Country; the Pipeline dispatches one takeover.
    with worker.store.applications.write_lock():
        block(worker, "unsupported_control", field="country")
    first = _until(
        lambda: (_job(ctx).get("assistance") or {}).get("status") == "claimed" and _job(ctx)
    )
    assert first["assistance"]["generation"] == 1
    assert (
        pipeline.snapshot()["takeover_request"]["request_id"]
        == first["assistance"]["claim_request_id"]
    )

    # 2. The real runner starts it once; Codex resolves the segment and returns to the script.
    adapter = _turn(ctx, planned=COUNTRY_CLICK, effect=select_country, report=make_report())
    runner.tick()
    returned = _job(ctx)
    assert adapter.kwargs["request_id"] == first["assistance"]["claim_request_id"]
    assert returned["assistance"]["status"] == "released"
    assert returned["assistance"]["outcome"]["kind"] == "script_checkpoint"
    assert returned["status"] == "filling" and returned["assistance_return_count"] == 1
    assert pipeline.snapshot()["control"] == "running"

    # 3. The script continues to Phone, which it also cannot handle: one more takeover.
    with worker.store.applications.write_lock():
        complete_page(ctx)
        block(worker, "unsupported_control", field="phone")
    second = _until(
        lambda: (
            (_job(ctx).get("assistance") or {}).get("generation") == 2
            and _job(ctx)["assistance"]["status"] == "claimed"
            and _job(ctx)
        )
    )
    assert second["assistance"]["dispatch"]["blocker"]["field_id"] == "phone"
    assert second["assistance"]["claim_request_id"] != first["assistance"]["claim_request_id"]

    # 4. Codex fills the rest (one return was already used) and reports completion.
    def fill_phone(page):
        page.fields[2]["value"] = "+41 44 000 00 00"

    adapter = _turn(
        ctx, planned=PHONE_CLICK, effect=fill_phone, report=make_report("ready_for_review")
    )
    runner.tick()
    assert adapter.kwargs["delivery"]["next_step"]["kind"] == "complete_remaining_fields"
    completed = _job(ctx)
    assert completed["assistance"]["outcome"]["kind"] == "filling_complete"
    assert completed["status"] == "ready_for_review"

    # 5. The Pipeline hands the original page to the user for the manual Submit wait.
    state = _until(lambda: (s := pipeline.snapshot())["status"] == "ready_for_review" and s)
    assert state["control"] == "paused" and state["notification"]["status"] == "ready_for_review"
    reviewed = []
    runner.cua.review = lambda original, *, pump: reviewed.append(original)
    runner.guards[ctx.identifier] = object()
    ctx.page.unroute = lambda pattern, guard: None
    ctx.page.bring_to_front = lambda: None
    current = worker.store.load()
    assert [row["action"] for row in current["commands"]] == ["review"]
    runner.commands(current)
    runner.persist(current)
    job = _job(ctx)
    assert reviewed == [ctx.page]
    assert job["handed_off"] is True and job["handoff"]["status"] == "complete"
    assert job["handoff"]["source"] == "automatic_submit_wait"
    assert job["handoff"]["actor"] == "system" and job["handoff"]["human_reviewed"] is False
    assert not job.get("manual_submission")
    assert [row["generation"] for row in job["assistance_history"]] == [1]
    assert pipeline.snapshot()["items"][0]["status"] != "completed"


# MC-09 S12: controls and faults inside the same chain, through the named Pipeline controls.


def _claimed(ctx, generation=1):
    def current():
        assistance = _job(ctx).get("assistance") or {}
        return (
            assistance.get("status") == "claimed"
            and assistance.get("generation") == generation
            and assistance
        )

    return _until(current)


def _dispatch(ctx, field="country", reason="unsupported_control", generation=1, **options):
    with ctx.service.store.applications.write_lock():
        block(ctx.service, reason, field=field, **options)
    return _claimed(ctx, generation)


def _running(ctx):
    """Start the claimed takeover once; its native turn keeps running until stopped."""
    adapter = RunningAdapter(
        ctx.page, ctx.client, planned=[], effect=lambda page: None, report=make_report()
    )
    starts, stops = [], []
    start, stop = adapter.start_takeover, adapter.stop
    adapter.start_takeover = lambda ref, **kw: starts.append(kw["request_id"]) or start(ref, **kw)
    adapter.stop = lambda run_id, **kw: stops.append(kw["request_id"]) or stop(run_id, **kw)
    ctx.runner.codex_assist = adapter
    ctx.runner.tick()
    assert _job(ctx)["assistance"]["status"] == "claimed" and "stop" not in _job(ctx)["assistance"]
    assert ctx.runner._assistance_run is not None
    return SimpleNamespace(adapter=adapter, starts=starts, stops=stops)


def _drain(ctx, ticks=3):
    for _ in range(ticks):
        ctx.runner.tick()


def _first_return(ctx):
    """Steps 1-3 of the chain: first takeover returns, the script reaches Phone."""
    first = _dispatch(ctx)
    _turn(ctx, planned=COUNTRY_CLICK, effect=select_country, report=make_report())
    ctx.runner.tick()
    assert _job(ctx)["assistance"]["outcome"]["kind"] == "script_checkpoint"
    with ctx.service.store.applications.write_lock():
        complete_page(ctx)
    return first


def _counted_requests(ctx, monkeypatch):
    calls = []
    original = ctx.service.request_takeover

    def counted(*args, **kwargs):
        calls.append(kwargs["request_id"])
        return original(*args, **kwargs)

    monkeypatch.setattr(ctx.service, "request_takeover", counted)
    return calls


def test_cancel_during_claimed_takeover_stops_codex_and_keeps_page_and_unknown(chain, monkeypatch):
    ctx = chain
    calls = _counted_requests(ctx, monkeypatch)
    _snapshot, intent = unknown_country_intent(ctx)
    with ctx.service.store.applications.write_lock():
        state = ctx.service.store.load()
        state["jobs"][0]["page_observation"]["at"] = time.time()
        ctx.service.store.save(state)
    first = _claimed(ctx)
    assert first["dispatch"]["pending_intent_ref"] == digest(intent)
    run = _running(ctx)
    fields = deepcopy(ctx.page.fields)

    result = ctx.pipeline.cancel_current(request_id="cancel-during-takeover")
    # The referenced unknown action keeps the cancellation partial, never "complete".
    receipt = result["current_cancellation"]
    assert (receipt["status"], receipt["worker_status"]) == ("partial", "unknown")
    assert receipt["preparation_status"] == "cancelled"
    _drain(ctx)
    time.sleep(0.2)
    job = _job(ctx)
    # Codex was stopped on the original page by one stop request; nothing was replayed.
    assert run.starts == [first["claim_request_id"]]
    assert run.stops and set(run.stops) == {job["assistance"]["stop"]["request_id"]}
    assert job["assistance"]["status"] == "stopped"
    assert job["assistance"]["stop"]["reason"] == "cancelled"
    assert job["assistance"]["stop"]["stop_status"] == "stopped"
    assert job["status"] == "cancelled" and job["intent"] == intent
    assert ctx.runner.pages[ctx.identifier] is ctx.page and ctx.page.fields == fields
    # No automatic next job and no further takeover.
    state = ctx.pipeline.snapshot()
    assert state["status"] == "needs_recheck" and state["control"] == "paused"
    assert state["active_task_id"] == ctx.pipeline.flow.task["id"] and len(state["items"]) == 1
    assert calls == [first["claim_request_id"]]
    assert [row["action"] for row in ctx.service.store.load()["commands"]] == []


def _verify_continue(ctx):
    """The original runner's one verification of the original page after Continue."""
    with ctx.service.store.applications.write_lock():
        state = ctx.service.store.load()
        job = state["jobs"][0]
        assert job["continuation"]["status"] == "pending"
        job["continuation"]["status"] = "verified"
        job.update(status="queued", reason="")
        state.update(
            control="running", commands=[], resume_serial=state.get("resume_serial", 0) + 1
        )
        ctx.service.store.save(state)


def test_skip_then_return_restores_the_same_page_and_takeover_history(chain, monkeypatch):
    ctx = chain
    calls = _counted_requests(ctx, monkeypatch)
    first = _dispatch(ctx)
    run = _running(ctx)
    ctx.pipeline.skip_current(request_id="skip-during-takeover")
    _drain(ctx)
    job = _job(ctx)
    assert job["assistance"]["stop"]["reason"] == "skip-current"
    assert job["assistance"]["stop"]["stop_status"] == "stopped"
    assert run.stops and set(run.stops) == {job["assistance"]["stop"]["request_id"]}
    skipped = deepcopy(job)
    state = ctx.pipeline.snapshot()
    assert state["active_task_id"] is None
    assert [row["status"] for row in state["items"]] == ["skipped"]

    returned = ctx.pipeline.return_to(ctx.identifier, request_id="return-after-skip")
    assert returned["active_task_id"] == ctx.pipeline.flow.task["id"]
    assert returned["control"] == "paused"
    _drain(ctx)
    job = _job(ctx)
    assert ctx.service.store.load()["current_job_id"] == ctx.identifier
    # The same page, the same stopped takeover record and no new claim or turn.
    assert ctx.runner.pages[ctx.identifier] is ctx.page
    assert job["assistance"] == skipped["assistance"]
    assert job.get("assistance_history", []) == skipped.get("assistance_history", [])
    assert run.starts == [first["claim_request_id"]]
    time.sleep(0.2)
    assert calls == [first["claim_request_id"]]

    # One Continue on the returned job lets the script recheck; its next blocker gets
    # exactly one new takeover, which this runner actually starts.
    ctx.pipeline.continue_current(request_id="continue-after-return")
    _verify_continue(ctx)
    _until(lambda: ctx.pipeline.snapshot()["status"] == "filling")
    second = _dispatch(ctx, generation=2)
    assert [row["generation"] for row in _job(ctx)["assistance_history"]] == [1]
    adapter = _turn(ctx, planned=COUNTRY_CLICK, effect=select_country, report=make_report())
    ctx.runner.tick()
    assert adapter.kwargs is not None, "the returned job's new takeover was never started"
    assert adapter.kwargs["request_id"] == second["claim_request_id"]
    assert calls == [first["claim_request_id"], second["claim_request_id"]]


def test_pause_during_second_takeover_then_one_continue_allows_one_more(chain, monkeypatch):
    ctx = chain
    _first_return(ctx)
    calls = _counted_requests(ctx, monkeypatch)
    second = _dispatch(ctx, field="phone", generation=2)
    run = _running(ctx)
    ctx.pipeline.pause()
    _drain(ctx)
    job = _job(ctx)
    assert job["assistance"]["stop"]["reason"] == "user_paused" and len(run.stops) == 1
    assert (job["status"], job["reason"]) == ("needs_recheck", "assistance_paused")
    # The same blocker without a Continue sends nothing.
    with ctx.service.store.applications.write_lock():
        block(ctx.service, "unsupported_control", field="phone")
    time.sleep(0.2)
    assert calls == [second["claim_request_id"]]

    ctx.pipeline.continue_current(request_id="continue-second-takeover")
    _verify_continue(ctx)
    _until(lambda: ctx.pipeline.snapshot()["status"] == "filling")
    third = _dispatch(ctx, field="phone", generation=3)
    assert third["claim_request_id"] != second["claim_request_id"]
    assert calls == [second["claim_request_id"], third["claim_request_id"]]

    # Codex must finish this one: the single return was used by the first takeover.
    def fill_phone(page):
        page.fields[2]["value"] = "+41 44 000 00 00"

    adapter = _turn(
        ctx, planned=PHONE_CLICK, effect=fill_phone, report=make_report("ready_for_review")
    )
    ctx.runner.tick()
    assert adapter.kwargs["delivery"]["next_step"]["kind"] == "complete_remaining_fields"
    assert _job(ctx)["assistance"]["outcome"]["kind"] == "filling_complete"
    time.sleep(0.2)
    job = _job(ctx)
    assert [row["generation"] for row in job["assistance_history"]] == [1, 2]
    assert calls == [second["claim_request_id"], third["claim_request_id"]]


def test_material_edit_during_takeover_stops_writers_before_the_gate_opens(chain):
    ctx = chain
    _dispatch(ctx)
    run = _running(ctx)
    task = ctx.pipeline.flow.task
    flow_task = deepcopy(task)
    flow_files = {path: path.read_bytes() for path in ctx.pipeline.flow.root.iterdir()}
    flow_files.pop(ctx.pipeline.flow.root / "pipeline.json")
    gate = ctx.pipeline.begin_material_edit(task["id"], task["revision"], request_id="edit-gate")
    assert gate == {"edit_gate": "stopping", "edit_gate_reason": "assistance_stopping"}
    assert "material_edit_gate" not in ctx.pipeline.snapshot()
    # Until the runner has proven Codex stopped, the same request stays stopping.
    again = ctx.pipeline.begin_material_edit(task["id"], task["revision"], request_id="edit-gate")
    assert again["edit_gate"] == "stopping"
    assert ctx.pipeline.flow.task == flow_task
    _drain(ctx)
    stop = _job(ctx)["assistance"]["stop"]
    assert stop["reason"] == "user_paused" and stop["stop_status"] == "stopped"
    assert run.stops == [stop["request_id"]]
    ready = ctx.pipeline.begin_material_edit(task["id"], task["revision"], request_id="edit-gate")
    assert ready == {"edit_gate": "ready"}
    saved = ctx.pipeline.snapshot()["material_edit_gate"]
    assert (
        saved["task_id"] == task["id"]
        and saved["page_id"] == _job(ctx)["page_observation"]["page_id"]
    )
    # Opening the gate edits nothing in Flow; the candidate save is Flow's own step.
    assert ctx.pipeline.flow.task == flow_task
    after = {path: path.read_bytes() for path in ctx.pipeline.flow.root.iterdir()}
    after.pop(ctx.pipeline.flow.root / "pipeline.json")
    assert after == flow_files


def test_backend_reopen_mid_takeover_keeps_one_executor(chain, monkeypatch):
    ctx = chain
    first = _dispatch(ctx)
    run = _running(ctx)
    calls = _counted_requests(ctx, monkeypatch)
    ctx.pipeline.close()
    _drain(ctx)
    # Closing the backend stops Codex on the original page and keeps the job.
    stopped = deepcopy(_job(ctx)["assistance"])
    assert stopped["stop"]["reason"] == "backend_closed"
    assert stopped["stop"]["stop_status"] == "stopped"
    assert run.stops and set(run.stops) == {stopped["stop"]["request_id"]}
    reopened = ApplicationPipeline(ctx.pipeline.flow, Intake(), ctx.service, interval=0.02)
    try:
        _drain(ctx)
        time.sleep(0.3)
        _drain(ctx)
        state = reopened.snapshot()
        assert state["control"] == "paused" and state["status"] == "interrupted"
        assert state["active_task_id"] == ctx.pipeline.flow.task["id"]
        # No second claim, turn or writer after the reopen.
        assert calls == [] and run.starts == [first["claim_request_id"]]
        assert _job(ctx)["assistance"] == stopped
        assert ctx.runner.pages[ctx.identifier] is ctx.page

        # One Continue on the reopened backend: the script rechecks, and its next
        # blocker gets one new takeover that the same runner actually starts.
        reopened.continue_current(request_id="continue-after-reopen")
        _verify_continue(ctx)
        _until(lambda: reopened.snapshot()["status"] == "filling")
        second = _dispatch(ctx, generation=2)
        adapter = _turn(ctx, planned=COUNTRY_CLICK, effect=select_country, report=make_report())
        ctx.runner.tick()
        assert adapter.kwargs is not None, "the reopened job's new takeover was never started"
        assert adapter.kwargs["request_id"] == second["claim_request_id"]
        assert calls == [second["claim_request_id"]]
    finally:
        reopened.close()


def test_lost_start_ack_keeps_one_claim_and_never_redispatches(chain, monkeypatch):
    from career_evidence_graph.application_codex_assist import AssistRunProgress

    ctx = chain
    calls = _counted_requests(ctx, monkeypatch)
    first = _dispatch(ctx)
    adapter = RunningAdapter(
        ctx.page, ctx.client, planned=[], effect=lambda page: None, report=make_report()
    )
    starts, stops = [], []
    start, stop = adapter.start_takeover, adapter.stop

    def lost_ack(ref, **kwargs):
        starts.append(kwargs["request_id"])
        start(ref, **kwargs)
        # The real Adapter keeps a lost turn/start acknowledgement as an unknown run.
        return SimpleNamespace(run_id="adapter-native-run", status="unknown")

    adapter.start_takeover = lost_ack
    adapter.progress = lambda run_id: AssistRunProgress(
        run_id=run_id,
        status="unknown",
        tools_revoked=True,
        local_tools_drained=True,
        native_turn_id=None,
        native_turn_status="idle",
    )
    adapter.stop = lambda run_id, **kw: stops.append(kw["request_id"]) or stop(run_id, **kw)
    ctx.runner.codex_assist = adapter
    for _ in range(5):
        ctx.runner.tick()
    time.sleep(0.3)
    for _ in range(3):
        ctx.runner.tick()
    job = _job(ctx)
    assert starts == [first["claim_request_id"]]
    assert job["assistance"]["generation"] == 1
    assert job["assistance"]["claim_request_id"] == first["claim_request_id"]
    assert calls == [first["claim_request_id"]]
    assert "outcome" not in job["assistance"]
    assert ctx.runner.pages[ctx.identifier] is ctx.page
    # The unknown run was revoked and stopped once; the job waits for the user.
    stop = job["assistance"]["stop"]
    assert (job["status"], job["reason"]) == ("needs_recheck", "assistance_scope_lost")
    assert stop["stop_status"] == "stopped" and stops == [stop["request_id"]]
    assert ctx.runner._assistance_run is None
    state = _until(lambda: (s := ctx.pipeline.snapshot())["control"] == "paused" and s)
    assert state["status"] == "needs_recheck"
    time.sleep(0.2)
    assert calls == [first["claim_request_id"]] and starts == [first["claim_request_id"]]


def test_unavailable_automatic_takeover_waits_with_its_reason(chain):
    # MC-22: takeover is on but could not be configured at startup (e.g. the dedicated Codex
    # home is not signed in): the job stops and says why, instead of the generic recheck text.
    ctx = chain
    worker, pipeline = ctx.service, ctx.pipeline
    worker.native_assistance_policy = None
    pipeline.takeover_unavailable_reason = "Codex 专用目录未登录"
    with worker.store.applications.write_lock():
        block(worker, "unsupported_control", field="country")
    state = _until(lambda: pipeline.snapshot()["status"] == "needs_recheck" and pipeline.snapshot())
    message = state["notification"]["message"]
    assert "自动接管不可用" in message and "Codex 专用目录未登录" in message
    # The configuration is fixed at startup, like every App setting.
    assert "重新打开工作台" in message
    assert "assistance" not in _job(ctx)


def test_unavailable_reason_is_not_shown_for_a_blocker_takeover_would_not_handle(chain):
    # A blocker with an unresolved script intent never dispatches a takeover, so the
    # ordinary stop text applies even while takeover is on but unavailable.
    ctx = chain
    worker, pipeline = ctx.service, ctx.pipeline
    worker.native_assistance_policy = None
    pipeline.takeover_unavailable_reason = "Codex 专用目录未登录"
    with worker.store.applications.write_lock():
        block(
            worker,
            "unsupported_control",
            field="country",
            intent={"field_id": "country", "action": "fill", "attempt_id": "pending-write"},
        )
    state = _until(lambda: pipeline.snapshot()["status"] == "needs_recheck" and pipeline.snapshot())
    assert "自动接管不可用" not in state["notification"]["message"]
