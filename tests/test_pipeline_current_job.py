"""A real intake and WorkerService retain skipped jobs while selecting one current job."""

import base64
import time
from copy import deepcopy

import pytest
from test_application_intake import message, page
from test_application_pipeline import Flow
from test_pipeline_recommendation_queue import drive
from test_worker_backend_recovery import backend as backend

from career_evidence_graph.application_intake import ApplicationIntakeService
from career_evidence_graph.application_pipeline import ApplicationPipeline
from career_evidence_graph.application_worker import WorkerService
from career_evidence_graph.career_portal_data import ApplicationStore, PortalDataError


@pytest.fixture
def current_pipeline(tmp_path, monkeypatch):
    (tmp_path / "applications").mkdir()
    apps = ApplicationStore(tmp_path / "applications")
    urls = [f"https://www.linkedin.com/jobs/view/{10000 + i}" for i in (1, 2, 3)]
    intake = ApplicationIntakeService(
        apps,
        tmp_path / "intake",
        reader=lambda *_a, **_k: {
            "status": "readable",
            "emails": [message(links=urls)],
            "provenance": {},
        },
        fetcher=lambda url: (
            page(url)
            | {
                "final_url": f"https://jobs.lever.co/synthetic-{url[-1]}/00000000-0000-0000-0000-{int(url[-1]):012d}",
                "redirects": [
                    {
                        "url": url,
                        "status": 302,
                        "location": f"https://jobs.lever.co/synthetic-{url[-1]}/00000000-0000-0000-0000-{int(url[-1]):012d}",
                    }
                ],
                "job_fields": {
                    "title": "Engineer",
                    "company": "Synthetic",
                    "location": "Zurich, Switzerland",
                },
            }
        ),
    )
    worker = WorkerService(
        apps,
        tmp_path / "worker",
        live=True,
        single_flow_root=tmp_path / "flow",
        single_career_root=tmp_path / "career",
        single_validator=lambda *_a, **_k: None,
    )
    monkeypatch.setattr(worker, "spawn", lambda: None)

    class RealWorkerFlow(Flow):
        def prepare_worker(self, identifier, revision, country, send_confirmed, **options):
            task = self.tasks[identifier]
            app = apps.get_application(identifier)
            worker.request(
                "prepare",
                {
                    "workflow": "single",
                    "send_confirmed": True,
                    "jobs": [
                        {
                            "application_id": identifier,
                            "revision": app["revision"],
                            "country": country,
                            "filename": "synthetic.pdf",
                            "file_base64": base64.b64encode(b"%PDF-1.4 synthetic").decode(),
                            "single_binding": {"task_id": identifier},
                        }
                    ],
                },
            )
            task.update(
                status="queued",
                worker_ref={
                    "batch_id": worker.snapshot()["batch_id"],
                    "job_id": identifier,
                    "status": "queued",
                },
            )
            return deepcopy(task)

        def worker_action(self, identifier, revision, operation, payload):
            worker.request(operation, payload | {"application_id": identifier})
            status = next(
                row["status"]
                for row in worker.snapshot()["jobs"]
                if row["application_id"] == identifier
            )
            if self.tasks[identifier]["worker_ref"] is not None:
                self.tasks[identifier]["worker_ref"]["status"] = status
            return deepcopy(self.tasks[identifier])

    flow = RealWorkerFlow(tmp_path / "flow", apps, worker)
    pipeline = ApplicationPipeline(flow, intake, worker, interval=100)
    try:
        yield pipeline, flow, intake, worker
    finally:
        pipeline.close()
        intake.close()


def test_skip_advances_one_job_and_return_restores_original_task_and_page(current_pipeline):
    pipeline, flow, _intake, worker = current_pipeline
    pipeline.start(request_id="start")
    first = drive(pipeline, "filling")
    worker_state = worker.store.load()
    original = worker_state["jobs"][0]
    original.update(
        status="needs_recheck",
        page_open=True,
        intent={"action": "upload", "attempt_id": "unknown-first"},
    )
    worker.store.save(worker_state)
    pipeline._tick()
    pipeline.skip_current(request_id="skip-first")
    second = drive(pipeline, "filling")
    assert second["active_task_id"] != first["active_task_id"]
    assert len(flow.tasks) == 2 and worker.store.load()["jobs"][0] == original
    pipeline.skip_current(request_id="skip-second")
    returned = pipeline.return_to(first["items"][0]["application_id"], request_id="return-first")
    assert returned["active_task_id"] == first["active_task_id"]
    assert worker.store.load()["current_job_id"] == original["application_id"]
    assert worker.store.load()["jobs"][0] == original and len(flow.tasks) == 2
    calls = deepcopy(flow.calls)
    pipeline._tick()
    assert flow.calls == calls and returned["control"] == "paused"


@pytest.mark.parametrize(
    "conclusion,next_job", [("success", True), ("rejected", False), ("unknown", False)]
)
def test_only_confirmed_success_advances_queue_without_cancelling_old_page(
    current_pipeline, conclusion, next_job
):
    pipeline, flow, _intake, worker = current_pipeline
    pipeline.start(request_id="result-start")
    first = drive(pipeline, "filling")
    state = worker.store.load()
    state["jobs"][0].update(
        status="ready_for_review",
        page_open=True,
        handed_off=True,
        submission_observation={
            "request_id": "readback-result",
            "status": "observed",
            "conclusion": conclusion,
        },
        manual_submission={"source": "read_only_browser_result"}
        if conclusion == "success"
        else None,
    )
    worker.store.save(state)
    # Existing worker command owns the proof; pipeline only consumes its durable result.
    pipeline._tick()
    if next_job:
        second = drive(pipeline, "filling")
        assert second["active_task_id"] != first["active_task_id"] and len(flow.tasks) == 2
        assert worker.store.load()["jobs"][0]["page_open"] is True
        assert worker.store.load()["jobs"][0]["status"] != "cancelled"
        assert pipeline.snapshot()["items"][0]["status"] == "completed"
    else:
        for _ in range(3):
            pipeline._tick()
        assert pipeline.snapshot()["control"] == "paused"
        assert (
            pipeline.snapshot()["active_task_id"] == first["active_task_id"]
            and len(flow.tasks) == 1
        )


def handed_over(current_pipeline, monkeypatch):
    """A ready job whose original page the runner handed to the user."""
    import time
    from types import SimpleNamespace

    from career_evidence_graph.application_form_state import (
        COMPLETE_WINDOW,
        MIN_SAMPLES,
        SAMPLE_INTERVAL,
        sample,
    )
    from career_evidence_graph.application_worker import start_run
    from career_evidence_graph.application_worker_browser import ApplicationRunner

    pipeline, _flow, _intake, worker = current_pipeline
    pipeline.start(request_id="direct-submit")
    first = drive(pipeline, "filling")
    run_id = start_run(worker.store)
    state = worker.store.load()
    current = state["jobs"][0]
    observed = {
        "document_token": "original-document",
        "parser": {"status": "complete", "signal": "synthetic-parser-complete"},
        "validation_errors": [],
        "fields": [
            {
                "id": "resume",
                "type": "file",
                "question": "Resume",
                "required": True,
                "valid": True,
                "value": "",
                "filename": current["filename"],
                "file_sha256": current["file_sha256"],
            }
        ],
    }
    binding = {
        "run_id": run_id,
        "page_id": "original-page",
        "step": current["job_url"] + "/apply",
        "document_token": observed["document_token"],
    }
    # This fixture begins at an already-ready form, after real policy intervals.
    # The runner still must read the original page again before handing it over.
    span = max(COMPLETE_WINDOW, SAMPLE_INTERVAL * (MIN_SAMPLES - 1))
    now = time.time()
    form = None
    for index in range(MIN_SAMPLES):
        form = sample(
            form,
            observed,
            binding=binding,
            now=now - span + index * span / (MIN_SAMPLES - 1),
        )
    assert form["parser"]["status"] == "stable"
    current["form_state"] = form
    current.update(
        status="ready_for_review",
        page_open=True,
        page_observation={
            "run_id": run_id,
            "page_id": "original-page",
            "event": "observed",
            "at": state["runtime"]["observed_at"],
        },
    )
    state.update(control="running", controller=pipeline._load()["controller"])
    worker.store.save(state)
    pipeline._tick()
    assert pipeline.snapshot()["status"] == "ready_for_review"
    handoff = worker.store.load()["jobs"][0]["handoff"]
    assert handoff["source"] == "automatic_submit_wait" and handoff["actor"] == "system"
    assert handoff["human_reviewed"] is False
    runner = ApplicationRunner(worker.store, None)

    class OriginalPage:
        context = None

        def is_closed(self):
            return False

        def unroute(self, *_args):
            pass

        def bring_to_front(self):
            pass

    page = OriginalPage()
    page.url = current["job_url"] + "/apply"
    runner.pages[current["application_id"]] = page
    runner.page_ids[page] = "original-page"
    runner.guards[current["application_id"]] = object()
    observed_pages = []

    def observe_original(target, job):
        assert target is page
        assert job["application_id"] == current["application_id"]
        observed_pages.append(target)
        return deepcopy(observed)

    monkeypatch.setattr(runner, "observe", observe_original)
    state = worker.store.load()
    runner.commands(state)
    runner.persist(state)
    assert page in runner.handed_off_pages
    assert observed_pages == [page]
    assert worker.store.load()["jobs"][0]["form_state"]["binding"] == binding
    return SimpleNamespace(
        pipeline=pipeline,
        worker=worker,
        runner=runner,
        page=page,
        current=current,
        first=first,
        observed=observed,
    )


def test_ready_automatically_hands_original_page_to_user_and_observes_their_submit(
    current_pipeline, monkeypatch
):
    from types import SimpleNamespace

    ready = handed_over(current_pipeline, monkeypatch)
    pipeline, worker, runner, page = ready.pipeline, ready.worker, ready.runner, ready.page
    current, first = ready.current, ready.first

    # Only the user causes the final request. The runner just observes and permits it.
    class Request:
        method = "POST"
        url = current["job_url"] + "/apply"
        frame = SimpleNamespace(page=page)

    request = Request()
    allowed = []
    runner._live_guard_request(
        SimpleNamespace(request=request, continue_=lambda: allowed.append(True))
    )
    runner.transport(request, "response", 302)
    runner.transport(request, "requestfinished")
    assert allowed == [True]
    monkeypatch.setattr(
        runner,
        "read_submission_page",
        lambda *_: {
            "url": "https://jobs.lever.co/confirmation",
            "messages": ["Your application has been submitted."],
            "has_form": False,
        },
    )
    pipeline.observe_result(request_id="observe-human-result")
    state = worker.store.load()
    runner.commands(state)
    runner.persist(state)
    pipeline._tick()
    second = drive(pipeline, "filling")
    assert second["active_task_id"] != first["active_task_id"]
    assert (
        worker.store.load()["jobs"][0]["manual_submission"]["source"] == "read_only_browser_result"
    )


@pytest.mark.parametrize("stale", ["old_run", "old_page", "expired"])
def test_a_stale_pending_result_read_does_not_stop_observing_the_users_submit(
    current_pipeline, monkeypatch, stale
):
    """2026-11-03: a 19:01 pending read from an earlier run was never settled; every
    later ready job skipped its result polls, so the user's 22:52 Submit was not seen.
    """
    import time

    ready = handed_over(current_pipeline, monkeypatch)
    pipeline, worker = ready.pipeline, ready.worker
    state = worker.store.load()
    job = state["jobs"][0]
    old = {
        "request_id": "stale-request",
        "status": "pending",
        "at": time.time() - (3600 if stale == "expired" else 10),
        "run_id": "earlier-run" if stale == "old_run" else state["runtime"]["id"],
        "page_id": "earlier-page" if stale == "old_page" else job["page_observation"]["page_id"],
    }
    job["submission_observation"] = dict(old)
    # The user's Submit settled after that read; only then is the page read again.
    job["observations"].append(
        {"kind": "manual_submit", "stage": "requestfinished", "at": time.time() - 5}
    )
    worker.store.save(state)
    drive(pipeline, "ready_for_review")
    job = worker.store.load()["jobs"][0]
    assert job["submission_observation"]["request_id"] != "stale-request"
    assert job["submission_observation"]["status"] == "pending"
    assert old in job["submission_observation_history"]
    commands = worker.store.load()["commands"]
    assert [c["request_id"] for c in commands if c["action"] == "observe-result"] == [
        job["submission_observation"]["request_id"]
    ]


def test_the_result_page_is_not_read_before_the_users_submit(current_pipeline, monkeypatch):
    ready = handed_over(current_pipeline, monkeypatch)
    pipeline, worker = ready.pipeline, ready.worker
    drive(pipeline, "ready_for_review")
    pipeline._tick()
    commands = worker.store.load()["commands"]
    assert not [c for c in commands if c["action"] == "observe-result"]


def test_a_current_pending_result_read_is_awaited(current_pipeline, monkeypatch):
    import time

    ready = handed_over(current_pipeline, monkeypatch)
    pipeline, worker = ready.pipeline, ready.worker
    state = worker.store.load()
    job = state["jobs"][0]
    job["submission_observation"] = {
        "request_id": "current-request",
        "status": "pending",
        "at": time.time(),
        "run_id": state["runtime"]["id"],
        "page_id": job["page_observation"]["page_id"],
    }
    worker.store.save(state)
    drive(pipeline, "ready_for_review")
    assert worker.store.load()["jobs"][0]["submission_observation"]["request_id"] == (
        "current-request"
    )


def test_source_wait_skip_return_reuses_current_pointer_and_continue_retries_source(
    current_pipeline,
):
    pipeline, flow, intake, _worker = current_pipeline
    original = intake.fetcher
    calls = []
    allow_retry = []

    def fetch(url):
        calls.append(url)
        if url.endswith("10001") and not allow_retry:
            return page(url, status="unavailable", completeness="unknown")
        return original(url)

    intake.fetcher = fetch
    pipeline.start(request_id="source-wait")
    waiting = drive(pipeline, "needs_input")
    first_id = waiting["current_recommendation_id"]
    pipeline.skip_current(request_id="skip-source")
    second = drive(pipeline, "filling")
    # A job skipped before it had an application is still labelled in the list.
    skipped = next(row for row in second["items"] if row["recommendation_id"] == first_id)
    record = next(row for row in intake.snapshot()["recommendations"] if row["id"] == first_id)
    assert "application_id" not in skipped or skipped["application_id"] is None
    assert (skipped["company"], skipped["role_title"]) == (record["company"], record["role_title"])
    assert skipped["source_host"] == "www.linkedin.com"
    pipeline.return_to(first_id, request_id="return-source")
    pipeline.continue_current(request_id="source-still-failed")
    drive(pipeline, "needs_input")
    assert len(calls) == 3
    allow_retry.append(True)
    pipeline.continue_current(request_id="source-now-captured")
    returned = drive(pipeline, "filling")
    assert returned["current_recommendation_id"] == first_id and len(flow.tasks) == 2
    assert returned["active_task_id"] != second["active_task_id"]
    assert sum(row.get("recommendation_id") == first_id for row in returned["items"]) == 1
    assert len(calls) == 4


def test_an_indeed_verification_stop_says_the_user_completes_it(current_pipeline):
    pipeline, _flow, intake, _worker = current_pipeline
    original = intake.fetcher

    def fetch(url):
        if url.endswith("10001"):
            held = page(url, status="login_required", completeness="unknown")
            return held | {"error_code": "verification_required"}
        return original(url)

    intake.fetcher = fetch
    pipeline.start(request_id="verification")
    waiting = drive(pipeline, "needs_input")
    assert "Indeed 要求人工验证" in waiting["notification"]["message"]


def test_codex_filling_complete_projects_manual_submit_wait_not_submitted(current_pipeline):
    import hashlib
    import json
    import time

    from career_evidence_graph.application_worker import (
        CODEX_NATIVE_ASSISTANCE,
        assistance_completion,
        start_run,
    )

    def sha(value):
        return hashlib.sha256(
            json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()

    pipeline, _flow, _intake, worker = current_pipeline
    pipeline.start(request_id="codex-complete")
    drive(pipeline, "filling")
    run_id = start_run(worker.store)
    state = worker.store.load()
    current = state["jobs"][0]
    now = time.time()
    # Every schema property is present, as the Adapter's report check requires.
    claimed = {
        "status": "ready_for_review",
        "summary": "Form filled",
        "unresolved_action_ids": [],
        "fields": [],
        "next_step": None,
    }
    report = {
        "protocol": "assistance-report/v1",
        "request_id": "report-one",
        "native_turn_id": "turn-one",
        "received_at": now - 5,
        "claimed": claimed,
        "claimed_sha256": sha(claimed),
    }
    current["assistance"] = {
        "protocol": CODEX_NATIVE_ASSISTANCE,
        "id": "a" * 32,
        "generation": 1,
        "request_id": "native-request",
        "claim_request_id": "native-claim",
        "status": "released",
        "active_writer": "script",
        "binding": {
            "application_id": current["application_id"],
            "batch_id": state["batch_id"],
            "run_id": run_id,
            "page_id": "original-page",
            "document_token": "original-document",
            "step": current["job_url"] + "/apply",
            "controller": pipeline._load()["controller"],
            "resume_serial": state.get("resume_serial", 0),
            "material_revision": "b" * 64,
            "answer_revision": "c" * 64,
        },
        "page_writes_enabled": True,
        "native_policy_digest": "d" * 64,
        "stop": {
            "request_id": "stop-one",
            "reason": "native_turn_completed",
            "requested_at": now - 6,
            "tools_revoked": True,
            "local_tools_drained": True,
            "process_stopped": True,
            "native_turn_id": "turn-one",
            "native_turn_status": "completed",
            "stop_status": "stopped",
            "observed_at": now - 4,
        },
        "report": report,
        "outcome": {
            "protocol": "assistance-outcome/v1",
            "kind": "filling_complete",
            "report_sha256": sha(report),
            "stop_request_id": "stop-one",
            "session_reclaimed_at": now - 3,
            "page_verification": {
                "at": now - 2,
                "document": {
                    "frame_id": "frame",
                    "loader_id": "loader",
                    "url": current["job_url"] + "/apply",
                },
                "fields": [
                    {
                        "id": "resume",
                        "required": True,
                        "valid": True,
                        "value_empty": False,
                        "file_count": 1,
                    }
                ],
                "worker_source": "e" * 64,
            },
            "verified": {"materials": [], "optional_failures": []},
            "attributed_fields": [{"field_id": "resume", "call_id": "call-one"}],
            "return_count": 0,
            "adopted_at": now - 1,
        },
    }
    # The script parser never reached stability; Codex's verified outcome is the evidence.
    current["form_state"] = {
        "binding": {
            "run_id": run_id,
            "page_id": "original-page",
            "document_token": "original-document",
            "step": current["job_url"] + "/apply",
        }
    }
    current.update(
        status="ready_for_review",
        page_open=True,
        page_observation={
            "run_id": run_id,
            "page_id": "original-page",
            "event": "observed",
            "at": state["runtime"]["observed_at"],
        },
    )
    state.update(control="running", controller=pipeline._load()["controller"])
    worker.store.save(state)
    assert assistance_completion(worker.store.load()["jobs"][0]) is not None

    pipeline._tick()

    snapshot = pipeline.snapshot()
    assert snapshot["status"] == "ready_for_review"
    saved = worker.store.load()["jobs"][0]
    assert saved["handoff"]["source"] == "automatic_submit_wait"
    assert saved["handoff"]["actor"] == "system" and saved["handoff"]["human_reviewed"] is False
    assert saved["status"] == "ready_for_review"
    assert not saved.get("manual_submission")
    assert snapshot["items"][0]["status"] != "completed"
    application = worker.store.applications.get_application(saved["application_id"])
    assert application["status"] == "drafting"


@pytest.mark.parametrize("held", ["claimed", "turn_completed"])
def test_repeated_pause_cancel_skip_do_not_restore_revoked_takeover(backend, held):
    import time
    from contextlib import suppress

    from career_evidence_graph.application_worker import script_writes_allowed
    from career_evidence_graph.career_portal_data import PortalDataError

    owner, _reopen, _runner, _page = backend
    pipeline, worker = owner.application_pipeline_service, owner.worker_service
    state = worker.store.load()
    job = state["jobs"][0]
    identifier = job["application_id"]
    job["form_state"] = {
        "binding": {
            "run_id": state["runtime"]["id"],
            "page_id": job["page_observation"]["page_id"],
            "document_token": "takeover-synthetic-document",
            "step": job["job_url"],
        }
    }
    worker.store.save(state)
    worker.request(
        "request-assistance",
        {
            "application_id": identifier,
            "binding": worker.assistance_context(identifier)["binding"],
            "request_id": "takeover-request",
        },
    )
    reference = worker.assistance_context(identifier)["assistance_ref"]
    worker.request(
        "claim-assistance",
        {"application_id": identifier, "assistance_ref": reference, "request_id": "takeover"},
    )
    if held == "turn_completed":
        # A finished native turn whose report was never adopted still holds the writer.
        state = worker.store.load()
        now = time.time()
        state["jobs"][0]["assistance"].update(
            status="stopped",
            stop={
                "request_id": "turn-stop",
                "reason": "native_turn_completed",
                "requested_at": now,
                "tools_revoked": True,
                "local_tools_drained": True,
                "process_stopped": True,
                "native_turn_id": "native-turn",
                "native_turn_status": "completed",
                "stop_status": "stopped",
                "observed_at": now,
            },
        )
        worker.store.save(state)
    revoked = []

    def assert_revoked():
        state = worker.store.load()
        assistance = state["jobs"][0]["assistance"]
        assert assistance["active_writer"] == "codex"
        assert assistance["status"] in {"stopping", "stopped"}
        assert "outcome" not in assistance
        assert not script_writes_allowed(state, identifier)
        if held == "turn_completed":
            assert assistance["stop"]["reason"] == "native_turn_completed"
            assert assistance["superseded"]["reason"] == "user_paused"
        else:
            assert assistance["stop"]["reason"] == "user_paused"
            assert "superseded" not in assistance
        revoked.append((assistance["stop"]["request_id"], assistance.get("superseded")))
        assert revoked[0] == revoked[-1]

    pipeline.pause()
    assert_revoked()
    # Late stop evidence from the revoked turn only drains it; it never returns a writer.
    worker.record_assistance_stop(
        identifier,
        worker.assistance_context(identifier)["assistance_ref"],
        {
            "tools_revoked": True,
            "local_tools_drained": True,
            "process_stopped": True,
            "native_turn_id": None,
            "native_turn_status": "idle",
            "stop_status": "stopped",
        },
        request_id=revoked[0][0],
    )
    assert_revoked()
    controls = (
        lambda: pipeline.pause(),
        lambda: pipeline.pause(),
        lambda: pipeline.skip_current(request_id="skip-revoked"),
        lambda: pipeline.skip_current(request_id="skip-revoked"),
        lambda: pipeline.return_to("synthetic-recommendation", request_id="return-revoked"),
        lambda: pipeline.continue_current(request_id="continue-revoked"),
        lambda: pipeline.cancel_current(request_id="cancel-revoked"),
        lambda: pipeline.cancel_current(request_id="cancel-revoked"),
        lambda: pipeline.pause(),
    )
    for control in controls:
        with suppress(PortalDataError):
            control()
        assert_revoked()


# MC-08 S3: the running Pipeline hands one technical blocker to one Codex takeover.


@pytest.fixture
def dispatch_pipeline(current_pipeline, monkeypatch):
    """The same real Worker and intake, with the Pipeline thread on a short interval."""
    from test_worker_native_assistance import POLICY

    from career_evidence_graph import cua_driver

    idle, flow, intake, worker = current_pipeline
    idle.close()
    monkeypatch.setattr(cua_driver, "_NATIVE_HANDOFF_DRIVER_SHA256", POLICY["driver_sha256"])
    pipeline = ApplicationPipeline(flow, intake, worker, interval=0.02)
    try:
        yield pipeline, flow, intake, worker
    finally:
        pipeline.close()


def _until(predicate, timeout=5.0):
    import time

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        value = predicate()
        if value:
            return value
        time.sleep(0.01)
    pytest.fail("condition not reached")


def _native(worker, monkeypatch, enabled=True):
    from test_worker_native_assistance import POLICY

    monkeypatch.setattr(worker, "native_assistance_policy", deepcopy(POLICY) if enabled else None)


def _filling_on_retained_page(pipeline, worker, request_id):
    import time

    from career_evidence_graph.application_worker import start_run

    pipeline.start(request_id=request_id)
    first = _until(lambda: (s := pipeline.snapshot())["status"] == "filling" and s)
    run_id = start_run(worker.store)
    with worker.store.applications.write_lock():
        state = worker.store.load()
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
        worker.store.save(state)
    return first


def _block(worker, reason, **options):
    from test_worker_codex_assistance import block

    with worker.store.applications.write_lock():
        return block(worker, reason, **options)


def _assistance(worker):
    return worker.store.load()["jobs"][0].get("assistance")


def _claimed(worker):
    assistance = _assistance(worker)
    return assistance if assistance and assistance["status"] == "claimed" else None


def _end_turn_in_wait(worker):
    from test_worker_codex_assistance import end_in_wait

    with worker.store.applications.write_lock():
        end_in_wait(worker)


def test_technical_blocker_requests_one_takeover_and_keeps_current_job(
    dispatch_pipeline, monkeypatch
):
    pipeline, flow, _intake, worker = dispatch_pipeline
    _native(worker, monkeypatch)
    first = _filling_on_retained_page(pipeline, worker, "dispatch-start")
    _block(worker, "unsupported_control")
    assistance = _until(lambda: _claimed(worker))
    state = pipeline.snapshot()
    request = state["takeover_request"]
    assert request["request_id"].startswith("takeover-") and len(request["request_id"]) == 41
    assert assistance["dispatch"]["request_id"] == request["request_id"]
    assert assistance["claim_request_id"] == request["request_id"]
    assert assistance["active_writer"] == "codex" and assistance["generation"] == 1
    assert request["blocker"] == assistance["dispatch"]["blocker"]
    assert request["title"] == "已交给 Codex 接续"
    assert request["message"] == "已自动交给 Codex 接续原页"
    # macos/App.swift rejects a notification while the status is not a wait.
    assert state["notification"] is None
    assert state["control"] == "running" and state["status"] == "filling"
    assert state["active_task_id"] == first["active_task_id"] and len(flow.tasks) == 1
    current = worker.store.load()
    assert current["control"] == "running" and current["controller"] == state["controller"]
    assert current["current_job_id"] == current["jobs"][0]["application_id"]


def test_default_off_blocker_stops_needs_recheck_without_assistance(dispatch_pipeline):
    pipeline, flow, _intake, worker = dispatch_pipeline
    first = _filling_on_retained_page(pipeline, worker, "default-off-start")
    _block(worker, "unsupported_control")
    state = _until(lambda: (s := pipeline.snapshot())["control"] == "paused" and s)
    assert state["status"] == "needs_recheck" and "takeover_request" not in state
    assert state["active_task_id"] == first["active_task_id"] and len(flow.tasks) == 1
    current = worker.store.load()
    assert "assistance" not in current["jobs"][0] and current["control"] == "paused"


@pytest.mark.parametrize(
    "reason,status,intent,dispatched",
    [
        ("missing_answers", "needs_input", False, False),
        ("user_authentication", "needs_recheck", False, True),
        ("action_result_unknown", "needs_recheck", True, True),
    ],
)
def test_missing_facts_do_not_dispatch_but_login_and_unknown_do(
    dispatch_pipeline, monkeypatch, reason, status, intent, dispatched
):
    import time

    pipeline, _flow, _intake, worker = dispatch_pipeline
    _native(worker, monkeypatch)
    _filling_on_retained_page(pipeline, worker, "classify-" + reason)
    pending = None
    if intent:
        pending = {
            "action": "fill",
            "attempt_id": "unknown-fill",
            "field_id": "country",
            "run_id": worker.store.load()["runtime"]["id"],
            "page_id": "retained-page",
        }
    _block(worker, reason, status=status, intent=deepcopy(pending))
    if dispatched:
        assistance = _until(lambda: _claimed(worker))
        assert assistance["dispatch"]["blocker"]["code"] == reason
        assert pipeline.snapshot()["control"] == "running"
        assert worker.store.load()["jobs"][0]["intent"] == pending
        return
    state = _until(lambda: (s := pipeline.snapshot())["status"] == "needs_input" and s)
    time.sleep(0.2)
    assert _assistance(worker) is None and "takeover_request" not in pipeline.snapshot()
    assert state["notification"]["status"] == "needs_input"


def test_waiting_during_takeover_only_collects_mail(dispatch_pipeline, monkeypatch):
    pipeline, flow, intake, worker = dispatch_pipeline
    _native(worker, monkeypatch)
    first = _filling_on_retained_page(pipeline, worker, "takeover-wait-start")
    _block(worker, "unsupported_control")
    assistance = _until(lambda: _claimed(worker))
    beat = worker.store.load()["heartbeat_at"]
    pipeline.capture_mail(request_id="capture-during-takeover")
    # The controller heartbeat continues while Codex holds the original page.
    _until(lambda: worker.store.load()["heartbeat_at"] > beat, timeout=8)
    state = pipeline.snapshot()
    assert state["control"] == "running" and state["status"] == "filling"
    assert state["active_task_id"] == first["active_task_id"] and len(flow.tasks) == 1
    assert len(state["items"]) == 1
    assert [row["status"] for row in state["mail_capture_requests"]] == ["started"]
    assert _assistance(worker) == assistance
    assert worker.store.load()["control"] == "running"
    assert len(worker.store.load()["jobs"]) == 1


def test_repeated_ticks_send_one_takeover_request(dispatch_pipeline, monkeypatch):
    import time

    pipeline, _flow, _intake, worker = dispatch_pipeline
    _native(worker, monkeypatch)
    _filling_on_retained_page(pipeline, worker, "repeat-start")
    calls = []
    original = worker.request_takeover

    def counted(*args, **kwargs):
        calls.append(kwargs["request_id"])
        return original(*args, **kwargs)

    monkeypatch.setattr(worker, "request_takeover", counted)
    _block(worker, "unsupported_control")
    assistance = _until(lambda: _claimed(worker))
    request = pipeline.snapshot()["takeover_request"]
    time.sleep(0.3)
    assert calls == [request["request_id"]]
    assert _assistance(worker) == assistance
    assert "assistance_history" not in worker.store.load()["jobs"][0]
    assert pipeline.snapshot()["takeover_request"] == request


def test_continue_after_wait_allows_one_new_takeover_only(dispatch_pipeline, monkeypatch):
    import time

    from career_evidence_graph.application_worker import adopt_assistance_stop

    pipeline, flow, _intake, worker = dispatch_pipeline
    _native(worker, monkeypatch)
    _filling_on_retained_page(pipeline, worker, "continue-start")
    _block(worker, "unsupported_control")
    first = _until(lambda: _claimed(worker))
    identifier = worker.store.load()["jobs"][0]["application_id"]
    # Pause mid-takeover; the Worker drains Codex and waits for one Continue.
    pipeline.pause()
    with worker.store.applications.write_lock():
        state = worker.store.load()
        job = state["jobs"][0]
        assert job["assistance"]["stop"]["reason"] == "user_paused"
        assert adopt_assistance_stop(
            job,
            worker.assistance_context(identifier)["assistance_ref"],
            {
                "tools_revoked": True,
                "local_tools_drained": True,
                "process_stopped": True,
                "native_turn_id": None,
                "native_turn_status": "idle",
                "stop_status": "stopped",
            },
            request_id=job["assistance"]["stop"]["request_id"],
        )
        job.update(status="needs_recheck", reason="assistance_paused")
        worker.store.save(state)
    time.sleep(0.2)
    assert _assistance(worker)["generation"] == 1
    pipeline.continue_current(request_id="continue-after-takeover-wait")
    with worker.store.applications.write_lock():
        # The original runner verifies the original page for this one Continue.
        state = worker.store.load()
        job = state["jobs"][0]
        assert job["continuation"]["status"] == "pending"
        job["continuation"]["status"] = "verified"
        job.update(status="queued", reason="")
        state.update(
            control="running", commands=[], resume_serial=state.get("resume_serial", 0) + 1
        )
        worker.store.save(state)
    _until(lambda: pipeline.snapshot()["status"] == "filling")
    _block(worker, "unsupported_control")
    second = _until(lambda: (a := _claimed(worker)) and a["generation"] == 2 and a)
    assert second["dispatch"]["request_id"] != first["dispatch"]["request_id"]
    assert pipeline.snapshot()["takeover_request"]["request_id"] == second["claim_request_id"]
    # That takeover ends in a wait; without another Continue no third one starts.
    _end_turn_in_wait(worker)
    state = _until(lambda: (s := pipeline.snapshot())["control"] == "paused" and s)
    assert state["status"] == "needs_recheck"
    time.sleep(0.2)
    job = worker.store.load()["jobs"][0]
    assert job["assistance"]["generation"] == 2
    assert [row["generation"] for row in job["assistance_history"]] == [1]
    assert len(flow.tasks) == 1


def _verify_continue(worker):
    """The original runner's one verification of the original page after Continue."""
    with worker.store.applications.write_lock():
        state = worker.store.load()
        job = state["jobs"][0]
        assert job["continuation"]["status"] == "pending"
        job["continuation"]["status"] = "verified"
        job.update(status="queued", reason="")
        state.update(
            control="running", commands=[], resume_serial=state.get("resume_serial", 0) + 1
        )
        worker.store.save(state)


@pytest.mark.parametrize(
    "wait", ["assistance_return_unverified", "assistance_completion_unverified"]
)
def test_natural_wait_then_continue_sends_exactly_one_new_takeover(
    dispatch_pipeline, monkeypatch, wait
):
    import time

    from test_worker_codex_assistance import end_in_wait

    pipeline, flow, _intake, worker = dispatch_pipeline
    _native(worker, monkeypatch)
    _filling_on_retained_page(pipeline, worker, "natural-" + wait)
    calls = []
    original = worker.request_takeover

    def counted(*args, **kwargs):
        calls.append(kwargs["request_id"])
        return original(*args, **kwargs)

    monkeypatch.setattr(worker, "request_takeover", counted)
    _block(worker, "unsupported_control")
    first = _until(lambda: _claimed(worker))
    with worker.store.applications.write_lock():
        end_in_wait(worker, wait)
    _until(lambda: (s := pipeline.snapshot())["control"] == "paused" and s)
    # The same blocker reappearing without Continue sends nothing.
    _block(worker, "unsupported_control")
    time.sleep(0.2)
    assert calls == [first["claim_request_id"]]
    pipeline.continue_current(request_id="continue-after-" + wait)
    _verify_continue(worker)
    _until(lambda: pipeline.snapshot()["status"] == "filling")
    _block(worker, "unsupported_control")
    second = _until(lambda: (a := _claimed(worker)) and a["generation"] == 2 and a)
    assert second["claim_request_id"] != first["claim_request_id"]
    with worker.store.applications.write_lock():
        end_in_wait(worker, wait)
    _until(lambda: (s := pipeline.snapshot())["control"] == "paused" and s)
    _block(worker, "unsupported_control")
    time.sleep(0.2)
    assert calls == [first["claim_request_id"], second["claim_request_id"]]
    job = worker.store.load()["jobs"][0]
    assert job["assistance"]["generation"] == 2
    assert [row["generation"] for row in job["assistance_history"]] == [1]
    assert len(flow.tasks) == 1


def test_same_fieldless_blocker_after_released_checkpoint_gets_a_new_takeover(
    dispatch_pipeline, monkeypatch
):
    from test_worker_codex_assistance import release

    pipeline, _flow, _intake, worker = dispatch_pipeline
    _native(worker, monkeypatch)
    _filling_on_retained_page(pipeline, worker, "fieldless-start")
    _block(worker, "user_authentication")
    first = _until(lambda: _claimed(worker))
    assert first["dispatch"]["blocker"]["field_id"] is None
    with worker.store.applications.write_lock():
        # Codex returns a checkpoint; the script resumes on the same page, run and serial.
        release(worker)
        state = worker.store.load()
        state["jobs"][0].update(status="filling", reason="")
        worker.store.save(state)
    _block(worker, "user_authentication")
    second = _until(lambda: (a := _claimed(worker)) and a["generation"] == 2 and a)
    assert second["claim_request_id"] != first["claim_request_id"]
    assert pipeline.snapshot()["takeover_request"]["request_id"] == second["claim_request_id"]
    # A third occurrence after that second (non-returning) takeover is not dispatched.
    with worker.store.applications.write_lock():
        _end_turn_in_wait(worker)
    state = _until(lambda: (s := pipeline.snapshot())["control"] == "paused" and s)
    assert state["status"] == "needs_recheck"


def test_capability_failure_wait_shows_its_specific_reason_and_is_not_resent(
    dispatch_pipeline, monkeypatch
):
    import time

    from career_evidence_graph.application_worker import record_takeover_failure, revoke_assistance

    pipeline, _flow, _intake, worker = dispatch_pipeline
    _native(worker, monkeypatch)
    _filling_on_retained_page(pipeline, worker, "capability-start")
    calls = []
    original = worker.request_takeover
    monkeypatch.setattr(
        worker,
        "request_takeover",
        lambda *a, **k: calls.append(k["request_id"]) or original(*a, **k),
    )
    _block(worker, "unsupported_control")
    first = _until(lambda: _claimed(worker))
    with worker.store.applications.write_lock():
        # The runner's capability failure: kept on the dispatch, the job waits with its code.
        state = worker.store.load()
        job = state["jobs"][0]
        request_id = first["claim_request_id"]
        record_takeover_failure(job, request_id=request_id, code="codex_app_server_unavailable")
        revoke_assistance(job, reason="assistance_unavailable", request_id="stop-" + request_id)
        job.update(status="needs_recheck", reason="codex_app_server_unavailable")
        worker.store.save(state)
    state = _until(lambda: (s := pipeline.snapshot())["control"] == "paused" and s)
    assert state["status"] == "needs_recheck"
    assert "codex_app_server_unavailable" in state["notification"]["message"]
    assert "动作结果未明" not in state["notification"]["message"]
    time.sleep(0.2)
    assert calls == [request_id]


def test_takeover_receipt_for_another_record_is_not_reported_as_running(
    dispatch_pipeline, monkeypatch
):
    pipeline, _flow, _intake, worker = dispatch_pipeline
    _native(worker, monkeypatch)
    _filling_on_retained_page(pipeline, worker, "stale-receipt-start")
    monkeypatch.setattr(
        worker,
        "request_takeover",
        lambda *a, **k: {"assistance_ref": None, "dispatch": {"request_id": "old-released"}},
    )
    _block(worker, "unsupported_control")
    state = _until(lambda: (s := pipeline.snapshot())["control"] == "paused" and s)
    assert state["status"] == "needs_recheck"
    assert state["takeover_request"]["error_code"] == "assistance_takeover_unavailable"
    assert state["notification"]["message"] == "接管请求没有建立新的操作范围，保留原页。"


def test_computer_use_fills_in_chrome_and_the_users_submit_moves_on(
    current_pipeline, monkeypatch, tmp_path
):
    """2026-11-08: the isolated Worker browser is replaced by Codex Computer Use."""
    from career_evidence_graph import application_computer_use

    pipeline, _flow, _intake, worker = current_pipeline
    pipeline.computer_use = {"executable": "/bin/codex", "root": tmp_path / "cu"}
    contexts = []

    def fill(executable, context, root, **options):
        contexts.append(context)
        return {
            "status": "ready_for_review",
            "summary": "filled",
            "filled": [],
            "unanswered": [],
        }

    monkeypatch.setattr(application_computer_use, "run_fill", fill)
    monkeypatch.setattr(
        worker.store, "_native_answer_reference", lambda job: {"confirmed_answers": []}
    )
    pipeline.start(request_id="start")
    first = drive(pipeline, "ready_for_review")
    (context,) = contexts
    assert context["job_url"] and context["resume_path"].endswith("synthetic.pdf")
    # The Worker's own browser never started for this job.
    assert worker.store.load()["control"] == "paused"
    assert first["control"] == "paused" and first["computer_use"]["report"]["status"] == (
        "ready_for_review"
    )
    after = pipeline.record_submitted(request_id="submitted-1")
    done = next(row for row in after["items"] if row.get("task_id") == first["active_task_id"])
    assert done["status"] == "completed" and done["submitted_by"] == "user"
    assert after["active_task_id"] != first["active_task_id"] and "computer_use" not in after


def test_a_skipped_job_the_user_submitted_is_recorded_as_applied(current_pipeline):
    """2026-11-08: Harmattan and Overstory were submitted by hand after the queue
    had left them, yet stayed listed as skipped with their old stop reason."""
    pipeline, flow, _intake, _worker = current_pipeline
    pipeline.start(request_id="start")
    first = drive(pipeline, "filling")
    pipeline.skip_current(request_id="skip-first")
    application_id = next(
        row["application_id"]
        for row in pipeline.snapshot()["items"]
        if row.get("task_id") == first["active_task_id"]
    )
    after = pipeline.mark_submitted(application_id=application_id, request_id="mark-1")
    item = next(row for row in after["items"] if row.get("application_id") == application_id)
    assert item["status"] == "completed" and item["submitted_by"] == "user"
    assert flow.applications.get_application(application_id)["status"] == "applied"
    # Repeating it changes nothing; the current job cannot be marked this way.
    assert (
        pipeline.mark_submitted(application_id=application_id, request_id="mark-2")["items"]
        == after["items"]
    )
    current = pipeline.snapshot()
    current_id = next(
        (
            row.get("application_id")
            for row in current["items"]
            if row.get("recommendation_id") == current.get("current_recommendation_id")
        ),
        None,
    )
    if current_id:
        with pytest.raises(PortalDataError):
            pipeline.mark_submitted(application_id=current_id, request_id="mark-3")


def test_a_confirmation_mail_records_the_computer_use_submission(
    current_pipeline, monkeypatch, tmp_path
):
    """2026-11-08: Keyrock's success page was not read; its confirmation mail is."""
    from career_evidence_graph import application_computer_use

    pipeline, flow, _intake, worker = current_pipeline
    searches = []

    def confirmations(company, since):
        searches.append(company)
        return [
            {
                "from": f"{company} <no-reply@example.invalid>",
                "subject": f"Thank you for applying to {company}",
                "body_text": "",
            }
        ]

    pipeline.computer_use = {
        "executable": "/bin/codex",
        "root": tmp_path / "cu",
        "confirmations": confirmations,
    }
    monkeypatch.setattr(
        application_computer_use,
        "run_fill",
        lambda *a, **k: {
            "status": "ready_for_review",
            "summary": "",
            "filled": [],
            "unanswered": [],
        },
    )
    monkeypatch.setattr(
        worker.store, "_native_answer_reference", lambda job: {"confirmed_answers": []}
    )
    pipeline.start(request_id="start")
    first = drive(pipeline, "ready_for_review")
    for _ in range(200):
        pipeline._tick()
        item = next(
            row
            for row in pipeline.snapshot()["items"]
            if row.get("task_id") == first["active_task_id"]
        )
        if item["status"] == "completed":
            break
        time.sleep(0.01)
    assert item["status"] == "completed" and item["submitted_by"] == "confirmation_email"
    assert searches and flow.applications.get_application(item["application_id"])["status"] == (
        "applied"
    )
