"""Backend lifecycle retains the original worker owner and its current page."""

import fcntl
import json
import os
import subprocess
import time
from copy import deepcopy
from types import SimpleNamespace

import pytest
from test_application_single_binding import bound_single, make_bound_single
from test_career_portal_http import portal as portal
from test_single_application_worker import single_worker as single_worker

from career_evidence_graph.application_pipeline import ApplicationPipeline
from career_evidence_graph.application_worker import digest, start_run
from career_evidence_graph.application_worker_browser import ApplicationRunner
from career_evidence_graph.career_portal import create_server


@pytest.fixture
def backend(tmp_path, monkeypatch, *, job_url=None, server_options=None):
    applications, root, career, _, _ = (
        bound_single.__wrapped__(tmp_path)
        if job_url is None
        else make_bound_single(tmp_path, job_url=job_url)
    )
    subprocess.run(["git", "init", "--quiet", str(career)], check=True)
    path = root / "flow.json"
    state = json.loads(path.read_text())
    task = state["tasks"][0]
    task.update(
        status="materials_ready",
        worker_ref=None,
        stages={"analysis": {"status": "complete"}, "resume": {"status": "complete"}},
    )
    task["revision"] = digest({k: v for k, v in task.items() if k != "revision"})
    path.write_text(json.dumps(state))
    # Drive the production tick explicitly; no scheduler timing changes the evidence.
    monkeypatch.setattr(ApplicationPipeline, "_run", lambda self, _: self._closed.wait())
    servers = []

    def open_backend():
        server = create_server(
            applications.root,
            career,
            write_admission_policy="development",
            flow_root=root,
            worker_root=tmp_path / "worker",
            worker_live=True,
            **(server_options or {}),
        )
        servers.append(server)
        monkeypatch.setattr(
            server.worker_service, "spawn", lambda: pytest.fail("Must retain the original worker")
        )
        return server

    owner = open_backend()
    task = owner.application_flow_service.prepare_worker(task["id"], task["revision"], "CHE", True)
    worker = owner.worker_service
    run_id = start_run(worker.store)
    state = worker.store.load()
    state.update(control="running", controller="pipeline-controller")
    state["jobs"][0].update(
        status="filling", reason="", page_open=True, manual_fields={}, manual_attachments=[]
    )
    state["jobs"][0]["page_observation"] = {
        "run_id": run_id,
        "page_id": "original-page",
        "event": "observed",
        "at": time.time(),
    }
    worker.store.save(state)
    pipeline = owner.application_pipeline_service
    policy = pipeline._load()
    policy.update(
        queue_mode=True,
        id="synthetic-pipeline",
        control="running",
        status="filling",
        controller="pipeline-controller",
        active_task_id=task["id"],
        worker_batch_id=state["batch_id"],
        worker_runtime_id=run_id,
        current_recommendation_id="synthetic-recommendation",
        mail_poll_at=time.time() + 600,
    )
    pipeline._save(policy)
    descriptor = os.open(worker.store.root / ".worker.lock", os.O_CREAT | os.O_RDWR, 0o600)
    fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
    worker.store.worker_lock_descriptor = descriptor
    context = SimpleNamespace(
        on=lambda *_: None, browser=None, route=lambda *_: None, route_web_socket=lambda *_: None
    )
    runner = ApplicationRunner(worker.store, context)
    monkeypatch.setattr(runner, "observe", lambda *_: {"fields": []})
    page = SimpleNamespace(context=context, is_closed=lambda: False)

    # Use a real owner map with a hashable original page handle.
    class Page:
        context = page.context

        def is_closed(self):
            return False

    page = Page()
    runner.pages[task["application_id"]] = page
    runner.page_ids[page] = "original-page"
    try:
        yield owner, open_backend, runner, page
    finally:
        for server in reversed(servers):
            server.server_close()
        os.close(descriptor)


def test_server_close_reopen_requires_original_owner_readback_then_keeps_run_page_and_material(
    backend,
):
    owner, reopen, runner, page = backend
    before = deepcopy(owner.worker_service.store.load())
    original = before["jobs"][0]
    owner.server_close()
    stopped = runner.store.load()
    assert stopped["control"] == "paused"
    assert not runner.permitted(stopped, page)
    assert stopped["jobs"] == before["jobs"]
    new = reopen()
    pipeline = new.application_pipeline_service
    pipeline._tick()
    pending = runner.store.load()
    assert pending["control"] == "paused"
    assert pending["commands"][0]["action"] == "recover-backend"
    runner.commands(pending)
    runner.persist(pending)
    pipeline._tick()
    after = runner.store.load()
    assert after["control"] == "running"
    assert after["runtime"]["id"] == before["runtime"]["id"] == runner.run_id
    assert runner.pages[original["application_id"]] is page
    assert after["jobs"] == before["jobs"]
    assert pipeline.snapshot()["status"] == "filling"


@pytest.mark.parametrize("timestamp", ["expired", "future", None, "invalid"])
def test_owner_checks_recovery_deadline_without_waiting_for_backend_tick(
    backend, monkeypatch, timestamp
):
    owner, reopen, runner, page = backend
    owner.server_close()
    reopen().application_pipeline_service._tick()
    state = runner.store.load()
    now = state["backend_recovery"]["requested_at"]
    state["backend_recovery"]["requested_at"] = (
        now - 16 if timestamp == "expired" else now + 1 if timestamp == "future" else timestamp
    )
    monkeypatch.setattr(time, "time", lambda: now)
    runner.commands(state)
    runner.persist(state)
    after = runner.store.load()
    assert after["control"] == "paused"
    assert after["backend_recovery"]["status"] == "needs_recheck"
    assert runner.pages[after["current_job_id"]] is page


def test_recovery_cannot_enable_writes_if_readback_outlives_its_deadline(backend, monkeypatch):
    owner, reopen, runner, page = backend
    owner.server_close()
    reopen().application_pipeline_service._tick()
    state = runner.store.load()
    now = state["backend_recovery"]["requested_at"]
    clock = [now]
    monkeypatch.setattr(time, "time", lambda: clock[0])

    def slow_observation(*_):
        clock[0] = now + 16
        return {"fields": []}

    monkeypatch.setattr(runner, "observe", slow_observation)
    runner.commands(state)
    runner.persist(state)
    after = runner.store.load()
    assert after["control"] == "paused"
    assert after["backend_recovery"]["status"] == "needs_recheck"
    assert not runner.permitted(after, page)


def test_reopened_backend_close_revokes_old_command_and_can_recover_again(backend):
    owner, reopen, runner, page = backend
    owner.server_close()
    second = reopen()
    second.application_pipeline_service._tick()
    stale_command = deepcopy(runner.store.load()["commands"][0])
    second.server_close()
    state = runner.store.load()
    assert state["backend_recovery"]["request_id"] != stale_command["request_id"]
    runner._command(state, stale_command)
    runner.persist(state)
    assert runner.store.load()["control"] == "paused"
    third = reopen()
    third.application_pipeline_service._tick()
    state = runner.store.load()
    runner.commands(state)
    runner.persist(state)
    third.application_pipeline_service._tick()
    assert runner.store.load()["control"] == "running"
    assert runner.pages[state["current_job_id"]] is page


def test_new_worker_restarts_only_a_never_opened_single_current_queue(single_worker):
    service, item, _, _ = single_worker
    service.request("prepare", {"workflow": "single", "send_confirmed": True, "jobs": [item]})
    service.request("resume", {"controller": "synthetic-controller"})
    old_run = start_run(service.store)
    before = deepcopy(service.store.load()["jobs"])
    new_run = start_run(service.store)
    after = service.store.load()
    assert new_run != old_run
    assert after["control"] == "running"
    assert after["jobs"] == before


@pytest.mark.parametrize(
    "status,reason,intent,handed_off",
    [
        ("needs_input", "important_answer_missing", None, False),
        ("needs_input", "user_authentication", None, False),
        ("ready_for_review", "", None, True),
        (
            "needs_recheck",
            "action_result_unknown",
            {"action": "upload", "attempt_id": "pending"},
            False,
        ),
    ],
)
def test_backend_reopen_preserves_explicit_wait_and_unknown(
    backend, status, reason, intent, handed_off
):
    owner, reopen, runner, page = backend
    state = runner.store.load()
    state["control"] = "paused"
    state["jobs"][0].update(status=status, reason=reason, intent=intent, handed_off=handed_off)
    runner.store.save(state)
    pipeline = owner.application_pipeline_service
    policy = pipeline._load()
    policy.update(control="paused", status=status)
    pipeline._save(policy)
    before = deepcopy(state["jobs"])
    owner.server_close()
    new = reopen()
    new.application_pipeline_service._tick()
    after = runner.store.load()
    assert after["control"] == "paused" and after["jobs"] == before
    assert not after.get("backend_recovery") and not after["commands"]
    assert runner.pages[before[0]["application_id"]] is page


def test_user_pause_during_backend_recovery_cancels_queued_resume(backend):
    owner, reopen, runner, page = backend
    owner.server_close()
    pipeline = reopen().application_pipeline_service
    pipeline._tick()
    pipeline.pause()
    state = runner.store.load()
    runner.commands(state)
    runner.persist(state)
    assert runner.store.load()["control"] == "paused"
    assert not runner.permitted(runner.store.load(), page)


def test_explicitly_paused_never_opened_queue_stays_paused_without_invented_unknown(single_worker):
    service, item, _, _ = single_worker
    service.request("prepare", {"workflow": "single", "send_confirmed": True, "jobs": [item]})
    start_run(service.store)
    before = deepcopy(service.store.load()["jobs"])
    start_run(service.store)
    after = service.store.load()
    assert after["control"] == "paused"
    assert after["jobs"] == before


def test_server_reopen_can_start_a_new_owner_only_before_any_page_or_action(backend, monkeypatch):
    owner, reopen, runner, _page = backend
    state = runner.store.load()
    state["jobs"][0].update(status="queued", page_open=False)
    state["jobs"][0].pop("page_observation")
    runner.store.save(state)
    old_run = runner.run_id
    owner.server_close()
    fcntl.flock(runner.store.worker_lock_descriptor, fcntl.LOCK_UN)
    new = reopen()
    launches = []
    monkeypatch.setattr(
        new.worker_service, "spawn", lambda: launches.append(start_run(new.worker_service.store))
    )
    pipeline = new.application_pipeline_service
    pipeline._tick()
    pipeline._tick()
    after = new.worker_service.store.load()
    assert len(launches) == 1 and launches[0] != old_run
    assert after["control"] == "running" and after["jobs"][0]["status"] == "queued"
    assert not after["jobs"][0]["page_open"]
    assert pipeline.snapshot()["status"] == "filling"
    assert pipeline.snapshot()["worker_runtime_id"] == launches[0]


@pytest.mark.parametrize(
    "evidence", ["profile", "retained_page", "completed_action", "manual_final", "intent"]
)
def test_cold_restart_does_not_infer_ownership_from_queued_label(single_worker, evidence):
    service, item, _, _ = single_worker
    service.request("prepare", {"workflow": "single", "send_confirmed": True, "jobs": [item]})
    service.request("resume", {"controller": "synthetic-controller"})
    start_run(service.store)
    state = service.store.load()
    job = state["jobs"][0]
    if evidence == "profile":
        (service.store.root / "browser-profile").mkdir()
    elif evidence == "retained_page":
        job.update(
            page_open=True,
            page_observation={
                "run_id": "old",
                "page_id": "old",
                "event": "observed",
                "at": time.time(),
            },
        )
    elif evidence == "completed_action":
        job["observations"].append({"action": "fill", "field_id": "name", "result": "confirmed"})
    elif evidence == "manual_final":
        job["observations"].append(
            {
                "kind": "manual_submit",
                "stage": "request",
                "request_id": "human-final",
                "application_id": item["application_id"],
            }
        )
    else:
        job["intent"] = {"action": "upload", "attempt_id": "unresolved"}
    service.store.save(state)
    before = deepcopy(job)
    start_run(service.store)
    after = service.store.load()
    assert after["control"] == "paused"
    assert after["jobs"][0]["status"] == "needs_recheck"
    assert after["jobs"][0]["intent"] == before["intent"]
    assert after["jobs"][0]["observations"][: len(before["observations"])] == before["observations"]


def test_lost_original_owner_never_reopens_old_url_as_a_new_page(backend):
    owner, reopen, runner, page = backend
    owner.server_close()
    fcntl.flock(runner.store.worker_lock_descriptor, fcntl.LOCK_UN)
    pipeline = reopen().application_pipeline_service
    pipeline._tick()
    assert pipeline.snapshot()["status"] == "needs_recheck"
    assert runner.store.load()["control"] == "paused"
    assert runner.pages[runner.store.load()["jobs"][0]["application_id"]] is page


@pytest.mark.worker_browser
def test_real_original_page_fields_and_attachment_survive_backend_reopen(backend, monkeypatch):
    from pathlib import Path

    from playwright.sync_api import sync_playwright

    owner, reopen, old_runner, _transport_page = backend
    monkeypatch.setenv("PLAYWRIGHT_BROWSERS_PATH", "0")
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True, channel="chromium")
        try:
            context = browser.new_context(offline=True)
            runner = ApplicationRunner(old_runner.store, context)
            sent = []
            context.route(
                "**/*",
                lambda route: (
                    sent.append(route.request.method)
                    or route.fulfill(
                        status=200,
                        content_type="text/html",
                        body=(
                            f"<title>{job['company']} - {job['role_title']}</title>"
                            '<form id="application-form"><label for="name">Full name</label>'
                            '<input id="name" name="name" value="Previous value">'
                            '<label for="resume">Resume</label>'
                            '<input id="resume" name="resume" type="file"></form>'
                        ),
                    )
                ),
            )
            job = runner.store.load()["jobs"][0]
            page = context.new_page()
            page.goto(job["job_url"] + "/apply")
            runner.pages[job["application_id"]] = page
            runner.page_ids[page] = "original-page"
            pdf = Path(job["file_path"]).read_bytes()
            owner.server_close()
            assert runner.store.load()["control"] == "paused"
            # These two actions represent human edits while the backend is closed.
            page.locator("#name").fill("Human edit")
            page.locator("#resume").set_input_files(job["file_path"])
            pipeline = reopen().application_pipeline_service
            pipeline._tick()
            state = runner.store.load()
            runner.commands(state)
            runner.persist(state)
            pipeline._tick()
            after = runner.store.load()
            assert after["control"] == "running", (after.get("backend_recovery") or {}).get(
                "reason"
            )
            assert after["runtime"]["id"] == runner.run_id == old_runner.run_id
            assert runner.pages[job["application_id"]] is page and len(context.pages) == 1
            assert page.locator("#name").input_value() == "Human edit"
            assert page.locator("#resume").evaluate("el => el.files[0].name") == job["filename"]
            assert Path(job["file_path"]).read_bytes() == pdf
            assert sent == ["GET"]
        finally:
            browser.close()


def test_unresponsive_owner_stops_recovery_and_late_command_cannot_resume(backend, monkeypatch):
    from career_evidence_graph import application_worker

    owner, reopen, runner, page = backend
    owner.server_close()
    pipeline = reopen().application_pipeline_service
    pipeline._tick()
    requested = runner.store.load()["backend_recovery"]["at"]
    monkeypatch.setattr(application_worker.time, "time", lambda: requested + 16)
    pipeline._tick()
    state = runner.store.load()
    runner.commands(state)
    runner.persist(state)
    assert pipeline.snapshot()["status"] == "needs_recheck"
    assert pipeline.snapshot()["notification"]
    assert runner.store.load()["control"] == "paused"
    assert not runner.permitted(runner.store.load(), page)


def test_warm_recovery_reads_and_keeps_manual_values_before_resuming(backend, monkeypatch):
    owner, reopen, runner, page = backend
    owner.server_close()
    fields = [
        {"id": "name", "type": "text", "value": "Human edit while backend closed", "valid": True},
        {"id": "resume", "type": "file", "filename": "human-resume.pdf", "file_sha256": "f" * 64},
    ]
    reads = []
    monkeypatch.setattr(
        runner,
        "observe",
        lambda original, _: reads.append(original) or {"fields": deepcopy(fields)},
    )
    pipeline = reopen().application_pipeline_service
    pipeline._tick()
    state = runner.store.load()
    runner.commands(state)
    runner.persist(state)
    pipeline._tick()
    after = runner.store.load()
    assert reads == [page]
    assert after["control"] == "running"
    assert after["jobs"][0]["manual_fields"]["name"] == fields[0]
    assert after["jobs"][0]["manual_attachments"] == [fields[1]]


def test_backend_closing_before_the_first_owner_starts_keeps_initial_queue_recoverable(
    single_worker, monkeypatch
):
    service, item, _, _ = single_worker
    service.request("prepare", {"workflow": "single", "send_confirmed": True, "jobs": [item]})
    service.request("resume", {"controller": "synthetic-controller"})
    receipt = service.suspend_backend(
        pipeline_id="before-first-owner",
        controller="synthetic-controller",
        batch_id=service.store.load()["batch_id"],
        application_id=item["application_id"],
    )
    monkeypatch.setattr(service, "spawn", lambda: start_run(service.store))
    service.recover_backend(receipt["request_id"], "before-first-owner")
    assert service.store.load()["control"] == "running"
    assert service.store.load()["jobs"][0]["status"] == "queued"


def test_waiting_for_original_owner_still_captures_mail_without_acquiring_a_job(
    backend, monkeypatch
):
    owner, reopen, _runner, _page = backend
    owner.server_close()
    pipeline = reopen().application_pipeline_service
    captured = []
    monkeypatch.setattr(
        pipeline.intake,
        "refresh",
        lambda **options: captured.append(options) or {"run_id": "capture-during-recovery"},
    )
    monkeypatch.setattr(
        pipeline.intake, "acquire", lambda *_: pytest.fail("Recovery cannot acquire another job")
    )
    state = pipeline._load()
    state["mail_poll_at"] = 0
    pipeline._save(state)
    pipeline._tick()
    assert captured == [{"capture_only": True}]
    assert pipeline.snapshot()["status"] == "recovering_worker"


def test_shutdown_stops_admitted_flow_writes_and_repeated_close_keeps_recovery_receipt(backend):
    from threading import Thread

    from career_evidence_graph.career_portal_data import PortalDataError

    owner, reopen, runner, _page = backend
    thread = Thread(target=owner.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True)
    thread.start()
    try:
        owner.shutdown()
        thread.join(3)
        receipt = deepcopy(runner.store.load()["backend_recovery"])
        pipeline = owner.application_pipeline_service
        task = owner.application_flow_service.snapshot(pipeline._load()["active_task_id"])[
            "active_task"
        ]
        with pytest.raises(PortalDataError):
            owner.application_flow_service.request(
                "worker-action",
                {
                    "task_id": task["id"],
                    "task_revision": task["revision"],
                    "operation": "resume",
                    "payload": {"controller": "pipeline-controller"},
                },
            )
        owner.server_close()
        assert runner.store.load()["backend_recovery"] == receipt
        reopened = reopen().application_pipeline_service
        reopened._tick()
        state = runner.store.load()
        runner.commands(state)
        runner.persist(state)
        reopened._tick()
        assert runner.store.load()["control"] == "running"
    finally:
        if thread.is_alive():
            owner.shutdown()
            thread.join(3)


def test_legacy_admitted_resume_cannot_undo_server_shutdown(portal, tmp_path, monkeypatch):
    from threading import Event, Thread

    from test_application_worker import job
    from test_career_portal_http import _running_portal

    with _running_portal(
        portal.applications, portal.career, worker_root=tmp_path / "legacy-worker"
    ) as active:
        worker = active.server.worker_service
        launches = []
        monkeypatch.setattr(worker, "spawn", lambda: launches.append(True))
        monkeypatch.setattr(worker, "fixture_origin", "http://127.0.0.1:9999")
        worker.request("prepare", {"jobs": [job(worker)]})
        worker.request("resume", {"controller": "legacy-controller"})
        launches.clear()
        headers = active.write_headers()
        admitted, release = Event(), Event()
        original = worker.request

        def held(operation, payload):
            if operation == "resume":
                admitted.set()
                assert release.wait(3)
            return original(operation, payload)

        monkeypatch.setattr(worker, "request", held)
        results = []
        requester = Thread(
            target=lambda: results.append(
                active.request(
                    "POST",
                    "/api/worker/resume",
                    body=json.dumps({"controller": "legacy-controller"}).encode(),
                    headers=headers,
                )
            ),
            daemon=True,
        )
        try:
            requester.start()
            assert admitted.wait(3)
            active.server.shutdown()
            assert worker.store.load()["control"] == "paused"
            release.set()
            requester.join(3)
            assert not requester.is_alive()
            assert worker.store.load()["control"] == "paused", results
            assert results[0][0] == 409
            assert launches == []
        finally:
            release.set()
            requester.join(3)


def test_late_cold_owner_stays_paused_until_another_backend_reopens(backend):
    owner, reopen, old_runner, _page = backend
    state = old_runner.store.load()
    state["jobs"][0].update(status="queued", page_open=False)
    state["jobs"][0].pop("page_observation")
    old_runner.store.save(state)
    owner.server_close()
    # This models a child which was launched earlier but starts after backend exit.
    new_run = start_run(old_runner.store)
    after = old_runner.store.load()
    assert after["control"] == "paused" and after["backend_recovery"]["status"] == "suspended"
    assert after["runtime"]["id"] == new_run
    runner = ApplicationRunner(old_runner.store, None)
    pipeline = reopen().application_pipeline_service
    pipeline._tick()
    state = runner.store.load()
    runner.commands(state)
    runner.persist(state)
    pipeline._tick()
    assert runner.store.load()["control"] == "running"
    assert pipeline.snapshot()["worker_runtime_id"] == new_run
