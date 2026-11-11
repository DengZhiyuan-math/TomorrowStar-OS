"""Synthetic stability contracts. No private records or real ATS requests."""

import json
import os
import time
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

import pytest
from owned_cdp_fake import OwnedCDPFake
from test_application_worker import job
from test_application_worker import service as _service

from career_evidence_graph.application_page_scope import PAGE_SCOPE
from career_evidence_graph.application_worker import WorkerService, start_run
from career_evidence_graph.career_portal_data import PortalDataError

service = _service


@pytest.fixture
def retained_live_page(tmp_path, monkeypatch):
    from test_hosted_ats import live_service, prepare

    now = time.time()
    monkeypatch.setattr("career_evidence_graph.application_worker.time.time", lambda: now)
    original = live_service(tmp_path, monkeypatch)
    prepared = prepare(original)
    run_id = start_run(original.store)
    state = original.store.load()
    current = state["jobs"][0]
    current.update(
        status="needs_recheck",
        reason="action_result_unknown",
        page_open=False,
        intent={"action": "open", "attempt_id": "synthetic-open-attempt", "run_id": run_id},
        page_observation={
            "run_id": run_id,
            "page_id": "synthetic-retained-page",
            "event": "observed",
            "at": now,
        },
    )
    original.store.save(state)
    # A replacement control server does not own or restart the existing worker.
    server = WorkerService(original.store.applications, original.store.root, live=True)
    monkeypatch.setattr(server, "spawn", lambda: pytest.fail("Review must not spawn a worker"))
    assert server.process is None
    return server, prepared["application_id"]


@pytest.mark.parametrize("status,page_age", [("needs_recheck", 0), ("needs_input", 3600)])
def test_new_server_can_review_fresh_retained_page_after_open_timeout(
    retained_live_page, status, page_age
):
    server, identifier = retained_live_page
    state = server.store.load()
    state["jobs"][0]["status"] = status
    state["jobs"][0]["page_observation"]["at"] -= page_age
    server.store.save(state)
    before = deepcopy(server.store.load())
    snapshot = server.snapshot()
    assert snapshot["runtime_status"]["observation"] == "current"
    assert snapshot["runtime_status"]["process"] == "unknown"
    assert snapshot["jobs"][0]["page_current"] is True

    result = server.request("review", {"application_id": identifier, "acknowledge": True})

    persisted = server.store.load()
    current = persisted["jobs"][0]
    assert result["jobs"][0]["manual_intervention"] is True
    assert current["handed_off"] is True
    assert current["handoff"]["status"] == "pending"
    assert current["handoff"]["run_id"] == before["runtime"]["id"]
    assert current["page_open"] is False
    assert current["page_observation"] == before["jobs"][0]["page_observation"]
    assert current["intent"] == before["jobs"][0]["intent"]
    assert persisted["commands"] == [{"action": "review", "id": identifier}]
    assert persisted["control"] == "paused"
    assert persisted["runtime"] == before["runtime"]


@pytest.mark.parametrize("page_open", [False, True])
@pytest.mark.parametrize(
    "change",
    [
        "stale_runtime",
        "future_runtime",
        "different_run",
        "closed",
        "crashed",
        "missing_page_id",
        "blank_page_id",
        "missing_observation",
        "exited_runtime",
        "page_lost",
        "page_closed",
        "page_crashed",
    ],
)
def test_partial_review_rejects_unverified_original_page(retained_live_page, page_open, change):
    server, identifier = retained_live_page
    state = server.store.load()
    current = state["jobs"][0]
    current["page_open"] = page_open
    page = current["page_observation"]
    if change == "stale_runtime":
        state["runtime"]["observed_at"] -= PAGE_SCOPE.window
    elif change == "future_runtime":
        state["runtime"]["observed_at"] += 1
    elif change == "different_run":
        page["run_id"] = "different-synthetic-runtime"
    elif change in {"closed", "crashed"}:
        page["event"] = change
    elif change == "missing_page_id":
        page.pop("page_id")
    elif change == "blank_page_id":
        page["page_id"] = " "
    elif change == "missing_observation":
        current.pop("page_observation")
    elif change in {"page_lost", "page_closed", "page_crashed"}:
        current["reason"] = change
    else:
        server.process = SimpleNamespace(pid=state["runtime"]["pid"], poll=lambda: -9)
        server.process_run_id = state["runtime"]["id"]
    server.store.save(state)
    before = server.store.path.read_bytes()

    assert server.snapshot()["jobs"][0]["page_current"] is False
    with pytest.raises(PortalDataError) as error:
        server.request("review", {"application_id": identifier, "acknowledge": True})

    assert error.value.code == "not_ready"
    assert server.store.path.read_bytes() == before


def test_existing_worker_reviews_the_retained_handle_without_reopening(retained_live_page):
    from career_evidence_graph.application_worker_browser import ApplicationRunner

    server, identifier = retained_live_page
    before = deepcopy(server.store.load()["jobs"][0])
    events = []

    class Page:
        def is_closed(self):
            return False

        def unroute(self, pattern, handler):
            events.append(("unroute", pattern, handler))

        def bring_to_front(self):
            events.append(("front",))

    page = Page()
    guard = object()
    existing_worker = ApplicationRunner(server.store, None)
    existing_worker.pages[identifier] = page
    existing_worker.page_ids[page] = before["page_observation"]["page_id"]
    existing_worker.guards[identifier] = guard
    server.request("review", {"application_id": identifier, "acknowledge": True})

    existing_worker.tick()

    current = server.store.load()["jobs"][0]
    assert existing_worker.pages[identifier] is page
    assert page in existing_worker.handed_off_pages
    assert events == [("unroute", "**/*", guard), ("front",)]
    assert current["handoff"]["status"] == "complete"
    assert current["intent"] == before["intent"]
    assert current["page_open"] is False
    assert current["page_observation"]["page_id"] == before["page_observation"]["page_id"]
    assert server.store.load()["commands"] == []
    with pytest.raises(PortalDataError) as error:
        server.request("recheck", {"application_id": identifier, "acknowledge": True})
    assert error.value.code == "action_unresolved"
    server.request(
        "resolve-action",
        {
            "application_id": identifier,
            "intent_ref": before["intent"]["attempt_id"],
            "conclusion": "not_applied",
            "source": "Synthetic original page inspected; no form data sent.",
        },
    )
    server.request(
        "recheck",
        {
            "application_id": identifier,
            "acknowledge": True,
            "reclaim": True,
            "handoff_source": "Synthetic original page and unknown action checked.",
        },
    )
    existing_worker.tick()
    state = server.store.load()
    assert existing_worker.pages[identifier] is page
    assert state["jobs"][0]["page_open"] is False
    assert state["jobs"][0]["intent"] is None
    assert state["jobs"][0]["handed_off"] is False
    assert state["control"] == "paused"
    # Later input waits retain the same review path without an open intent.
    state["jobs"][0].update(status="needs_input", reason="missing_answers")
    server.store.save(state)
    server.request("review", {"application_id": identifier, "acknowledge": True})
    existing_worker.tick()
    assert existing_worker.pages[identifier] is page
    assert server.store.load()["jobs"][0]["handoff"]["status"] == "complete"


@pytest.mark.parametrize("fault", ["page_lost", "browser_disconnected"])
def test_worker_fault_overrides_the_last_retained_page_observation(retained_live_page, fault):
    from career_evidence_graph.application_worker_browser import ApplicationRunner

    server, identifier = retained_live_page
    before = deepcopy(server.store.load()["jobs"][0]["page_observation"])
    existing_worker = ApplicationRunner(server.store, None)
    if fault == "page_lost":

        class ClosedPage:
            def is_closed(self):
                return True

        page = ClosedPage()
        existing_worker.pages[identifier] = page
        existing_worker.page_ids[page] = before["page_id"]
    else:
        existing_worker.event("browser_disconnected")

    existing_worker.tick()

    snapshot = server.snapshot()
    assert snapshot["runtime_status"]["observation"] == "current"
    assert snapshot["jobs"][0]["reason"] == fault
    if fault == "page_lost":
        assert snapshot["jobs"][0]["page_observation"] == before
    else:
        assert snapshot["jobs"][0]["page_observation"]["event"] == "browser_disconnected"
    assert snapshot["jobs"][0]["page_current"] is False
    with pytest.raises(PortalDataError) as error:
        server.request("review", {"application_id": identifier, "acknowledge": True})
    assert error.value.code == "not_ready"


@pytest.mark.parametrize("change,code", [("unconfirmed", "not_ready"), ("file", "file_changed")])
def test_retained_page_review_keeps_confirmation_and_material_guards(
    retained_live_page, change, code
):
    server, identifier = retained_live_page
    if change == "file":
        path = server.store.load()["jobs"][0]["file_path"]
        Path(path).write_bytes(b"%PDF-1.4 Different synthetic material")
    before = server.store.path.read_bytes()
    with pytest.raises(PortalDataError) as error:
        server.request(
            "review", {"application_id": identifier, "acknowledge": change != "unconfirmed"}
        )
    assert error.value.code == code
    assert server.store.path.read_bytes() == before


def test_runtime_history_freshness_and_managed_exit(service, monkeypatch):
    service.request("prepare", {"jobs": [job(service)]})
    assert service.snapshot()["runtime_status"]["observation"] == "historical"
    old_id = start_run(service.store)
    state = service.store.load()
    state["jobs"][0].update(
        page_open=True,
        page_observation={
            "run_id": old_id,
            "page_id": "synthetic-page",
            "event": "observed",
            "at": time.time(),
        },
    )
    service.store.save(state)
    assert service.snapshot()["jobs"][0]["page_current"]
    monkeypatch.setattr(
        "career_evidence_graph.application_worker.time.time",
        lambda: state["runtime"]["observed_at"] + PAGE_SCOPE.window,
    )
    assert service.snapshot()["runtime_status"]["observation"] == "stale"
    assert not service.snapshot()["jobs"][0]["page_current"]
    service.process = SimpleNamespace(pid=os.getpid(), poll=lambda: -9)
    assert service.snapshot()["runtime_status"]["exit_code"] == -9
    assert service.snapshot()["runtime_status"]["observation"] == "exited"
    # A reused PID, without the parent child handle, establishes no exit fact.
    service.process = None
    assert service.snapshot()["runtime_status"]["process"] == "unknown"
    assert service.snapshot()["runtime_status"]["exit_code"] is None
    new_id = start_run(service.store)
    assert new_id != old_id
    current = service.store.load()
    assert current["runtime_history"][0]["id"] == old_id
    assert current["control"] == "paused"
    assert not current["jobs"][0]["page_open"]


def test_startup_manifest_is_retained_when_disk_changes(service, monkeypatch):
    start_run(service.store)
    original = deepcopy(service.store.load()["runtime"]["source"])
    # The disk read is reused while a file's stat is unchanged; a changed file reads anew.
    monkeypatch.setattr(
        "career_evidence_graph.application_worker._file_sha256", lambda path: "changed"
    )
    state = service.snapshot()
    assert state["runtime"]["source"] == original
    assert not state["runtime_status"]["source_matches_disk"]


def test_corrupt_checkpoint_is_not_repaired(service):
    service.store.path.write_text('{"schemaVersion":1,"control":"broken"}')
    before = service.store.path.read_bytes()
    with pytest.raises(ValueError):
        service.snapshot()
    assert service.store.path.read_bytes() == before


def test_legacy_checkpoint_remains_historical(service):
    state = service.store.load()
    state.update(worker_pid=os.getpid(), worker_heartbeat=time.time())
    service.store.save(state)
    assert service.snapshot()["runtime_status"]["observation"] == "historical"
    assert json.loads(service.store.path.read_text()) == state


@pytest.fixture
def native_runner(service, monkeypatch):
    from playwright.sync_api import sync_playwright

    from career_evidence_graph.application_worker_browser import ApplicationRunner
    from career_evidence_graph.application_worker_fixtures import create_fixture_server

    items = [job(service, 1), job(service, 2)]
    server = create_fixture_server(
        service.store.applications.list_applications(), service.store.root
    )
    service.fixture_origin = f"http://127.0.0.1:{server.server_port}"
    service.request("prepare", {"jobs": items})
    for question, value in (
        ("Full name", "Synthetic Person"),
        ("Email address", "synthetic@example.invalid"),
    ):
        service.store.answers.put_answer(
            {"question": question, "value": value, "scope": {}, "state": "confirmed"}
        )
    monkeypatch.setenv("PLAYWRIGHT_BROWSERS_PATH", "0")
    try:
        with sync_playwright() as pw:
            context = pw.chromium.launch_persistent_context(
                str(service.store.root / "profile"), headless=True, service_workers="block"
            )
            context.set_default_timeout(4000)
            for blank in context.pages:
                blank.close()
            start_run(service.store)
            runner = ApplicationRunner(service.store, context, service.fixture_origin)
            service.request("resume", {"controller": "synthetic-controller"})
            deadline = time.monotonic() + 15
            while True:
                current = service.store.load()
                if all(
                    item["status"] == "needs_input"
                    and item["reason"] == "missing_answers"
                    and item["intent"] is None
                    and any(question["id"] == "sponsorship" for question in item["questions"])
                    for item in current["jobs"]
                ):
                    break
                assert all(
                    item["status"] not in {"needs_recheck", "cancelled"} for item in current["jobs"]
                ), current["jobs"]
                assert time.monotonic() < deadline, current["jobs"]
                service.request("heartbeat", {"controller": "synthetic-controller"})
                runner.tick()
                runner.pump()
            yield service, runner, context
            context.close()
    finally:
        server.shutdown()
        server.server_close()


def finish_other(service, runner):
    other = service.store.load()["jobs"][1]
    service.request(
        "answer",
        {
            "application_id": other["application_id"],
            "question_id": "sponsorship",
            "value": "No",
            "scope": {"application_id": other["application_id"], "country": "CHE"},
        },
    )
    deadline = time.monotonic() + 15
    while True:
        current = service.store.load()
        other = current["jobs"][1]
        if other["status"] == "ready_for_review":
            break
        assert other["status"] not in {"needs_recheck", "cancelled"}, other["reason"]
        assert time.monotonic() < deadline, other["reason"]
        service.request("heartbeat", {"controller": "synthetic-controller"})
        runner.tick()
        runner.pages[other["application_id"]].wait_for_timeout(250)
    assert current["jobs"][1]["status"] == "ready_for_review"
    assert (
        runner.pages[other["application_id"]].locator("#email").input_value()
        == "synthetic@example.invalid"
    )
    events = json.loads((service.store.root / "fixture-events.json").read_text())
    # Upload precedes filling; the first job may have uploaded before its page closed.
    uploads = events["uploads"]
    surviving = [upload for upload in uploads if upload["id"] == other["application_id"]]
    assert len(surviving) == 1 and surviving[0]["sha256"] == other["file_sha256"]
    assert len({upload["id"] for upload in uploads}) == len(uploads)
    assert events["submissions"] == []


@pytest.mark.worker_browser
@pytest.mark.parametrize("order", ["before_wait", "during_wait", "command"])
def test_native_page_close_isolated(native_runner, order):
    service, runner, context = native_runner
    identifier = service.store.load()["jobs"][0]["application_id"]
    page = runner.pages[identifier]
    began = time.monotonic()
    if order == "before_wait":
        page.close()
        runner.pump()
    elif order == "during_wait":
        # The idle dispatcher waits longer than the short turn after progress.
        # Enter the actual idle state before scheduling a close during that wait.
        runner.tick()
        assert not runner.work_progressed

        def close_during_wait(route):
            route.abort()
            page.close()

        page.route("**/fault-close", close_during_wait)
        page.evaluate("setTimeout(() => fetch('/fault-close'), 50)")
        runner.pump()
    else:
        state = service.store.load()
        state["jobs"][0]["status"] = "cancelled"
        state["commands"] = [{"action": "release", "id": identifier}]
        service.store.save(state)
        page.close()
    runner.tick()
    state = service.store.load()
    assert not state["jobs"][0]["page_open"]
    assert state["jobs"][0]["observations"][-1]["event"] == "page_closed"
    assert time.monotonic() - began < 2
    finish_other(service, runner)


def inject_native_crash(page):
    from playwright.sync_api import Error

    from career_evidence_graph.application_worker_browser import browser_deadline

    # Terminate the current renderer without the variable fatal-crash handling path.
    # The real Page crash event still establishes the fault; ERR_ABORTED alone does not.
    with browser_deadline(1):
        result = page.context.new_cdp_session(page).send("Page.navigate", {"url": "chrome://kill"})
    if result.get("errorText"):
        raise Error(result["errorText"])


@pytest.mark.worker_browser
@pytest.mark.parametrize("during_action", [False, True])
def test_native_page_crash_isolated(native_runner, monkeypatch, during_action):
    from playwright.sync_api import Error

    service, runner, context = native_runner
    state = service.store.load()
    current = state["jobs"][0]
    page = runner.pages[current["application_id"]]
    crash_started = None
    crash_times = []

    def record_crash():
        if crash_started is not None:
            crash_times.append(time.monotonic() - crash_started)

    page.on("crash", record_crash)
    if during_action:
        service.request(
            "answer",
            {
                "application_id": current["application_id"],
                "question_id": "sponsorship",
                "value": "No",
                "scope": {"country": "CHE", "application_id": current["application_id"]},
            },
        )
        original_authorize = runner.authorize

        def crash_after_intent(job, batch_id, intent):
            nonlocal crash_started
            permitted = original_authorize(job, batch_id, intent)
            if permitted and job["application_id"] == current["application_id"]:
                crash_started = time.monotonic()
                with page.expect_event("crash", timeout=1500), pytest.raises(Error):
                    inject_native_crash(page)
            return permitted

        monkeypatch.setattr(runner, "authorize", crash_after_intent)
        deadline = time.monotonic() + 12
        while crash_started is None:
            service.request("heartbeat", {"controller": "synthetic-controller"})
            runner.tick()
            if crash_started is None:
                pending = service.store.load()["jobs"][0]
                assert pending["status"] not in {"needs_recheck", "cancelled"}, pending["reason"]
                assert time.monotonic() < deadline, pending["reason"]
                page.wait_for_timeout(250)
    else:
        crash_started = time.monotonic()
        with page.expect_event("crash", timeout=1500), pytest.raises(Error):
            inject_native_crash(page)
    runner.pump()
    runner.tick()
    # A timeout raised inside authorize() is an Error caught by runner.tick().
    # Assert the actual event deadline outside that catch boundary as well.
    assert crash_times and crash_times[-1] < 1.5
    result = service.store.load()["jobs"][0]
    assert result["status"] == "needs_recheck"
    assert result["page_observation"]["event"] == "page_crashed"
    assert result["reason"] in (
        {"page_crashed", "action_result_unknown"} if during_action else {"page_crashed"}
    )
    assert not page.is_closed()  # A crash is not a close observation.
    if during_action:
        assert result["intent"]["action"] == "fill" and result["intent"]["attempt_id"]
    else:
        assert result["intent"] is None
    # Measure isolation from the actual renderer fault, excluding parser setup.
    assert time.monotonic() - crash_started < 2
    retained_intent = deepcopy(result["intent"])
    finish_other(service, runner)
    assert service.store.load()["jobs"][0]["intent"] == retained_intent


@pytest.mark.worker_browser
@pytest.mark.parametrize("command", ["review", "release", "recheck", "front"])
def test_native_command_failure_stays_local(native_runner, monkeypatch, command):
    from playwright.sync_api import Error

    service, runner, _ = native_runner
    state = service.store.load()
    current = state["jobs"][0]
    page = runner.pages[current["application_id"]]
    current.update(status="ready_for_review", manual_intervention=True)
    state["commands"] = [
        {"action": "review" if command == "front" else command, "id": current["application_id"]}
    ]
    service.store.save(state)
    method = (
        "close" if command == "release" else "bring_to_front" if command == "front" else "unroute"
    )
    monkeypatch.setattr(
        page, method, lambda *args, **kwargs: (_ for _ in ()).throw(Error("synthetic command race"))
    )
    runner.tick()
    current = service.store.load()["jobs"][0]
    assert current["reason"] == "page_command_failed"
    if command in {"review", "front"}:
        assert current["handed_off"] and current["handoff"]["status"] == "unknown"
    finish_other(service, runner)


@pytest.mark.parametrize("age", [0, 59.99, 60, 60.01, 86400, -1])
def test_ui_heartbeat_age_does_not_revoke_healthy_action_or_request(service, monkeypatch, age):
    from career_evidence_graph.application_worker_browser import ApplicationRunner
    from career_evidence_graph.ats_forms import FORMS

    service.request("prepare", {"jobs": [job(service)]})
    service.request("resume", {"controller": "synthetic-controller"})
    state = service.store.load()
    current = state["jobs"][0]
    runner = ApplicationRunner(service.store, None, service.fixture_origin)
    monkeypatch.setattr(
        "career_evidence_graph.application_worker_browser.time.time",
        lambda: state["heartbeat_at"] + age,
    )
    intent = {"action": "upload", "sha256": current["file_sha256"]}
    assert runner.authorize(current, state["batch_id"], intent) is True
    counts = {"allowed": 0, "blocked": 0}
    route = SimpleNamespace(
        request=type(
            "Request",
            (),
            {
                "method": "POST",
                "url": service.fixture_origin
                + FORMS["lever"].upload_path(current["application_id"]),
            },
        )(),
        fetch=lambda **kwargs: (
            SimpleNamespace(status=200, dispose=lambda: None)
            if kwargs == {"max_redirects": 0, "max_retries": 0, "timeout": 10000}
            else pytest.fail("Unbounded forwarding")
        ),
        fulfill=lambda **_: counts.update(allowed=counts["allowed"] + 1),
        abort=lambda _: counts.update(blocked=counts["blocked"] + 1),
    )
    runner._guard(current["application_id"])(route)
    assert counts == {"allowed": 1, "blocked": 0}
    assert service.store.load()["control"] == "running"


@pytest.mark.worker_browser
@pytest.mark.parametrize("fault", ["context", "browser"])
@pytest.mark.parametrize("phase", ["no_pages", "paused", "intent"])
def test_native_common_fault_stops_batch(native_runner, fault, phase):
    from career_evidence_graph.career_portal_data import PortalDataError

    service, runner, context = native_runner
    retained_uploads = json.loads((service.store.root / "fixture-events.json").read_text())[
        "uploads"
    ]
    if phase == "no_pages":
        for page in list(context.pages):
            page.close()
        runner.tick()
    elif phase == "paused":
        service.request("pause", {"controller": "synthetic-controller"})
    else:
        state = service.store.load()
        state["jobs"][0]["intent"] = {"action": "upload", "attempt_id": "synthetic-common"}
        service.store.save(state)
    began = time.monotonic()
    if fault == "context":
        context.close()
    else:
        context.browser.close()
    runner.tick()
    state = service.store.load()
    assert state["control"] == "paused"
    assert state["worker_error"] in {"context_closed", "browser_disconnected"}
    assert not any(j["page_current"] for j in service.snapshot()["jobs"])
    assert time.monotonic() - began < 2
    assert not runner.authorize(state["jobs"][0], state["batch_id"], {"action": "fill"})
    with pytest.raises(PortalDataError) as error:
        service.request("resume", {"controller": "synthetic-controller"})
    assert error.value.code == "runtime_lost"
    events = json.loads((service.store.root / "fixture-events.json").read_text())
    assert events["uploads"] == retained_uploads and events["submissions"] == []


def test_unreadable_shared_state_latches_stop_without_repair(service, monkeypatch):
    from career_evidence_graph.application_worker_browser import ApplicationRunner

    service.request("prepare", {"jobs": [job(service)]})
    service.request("resume", {"controller": "synthetic-controller"})
    state = service.store.load()
    runner = ApplicationRunner(service.store, None, service.fixture_origin)
    service.store.path.write_text('{"schemaVersion":1,"control":"broken"}')
    before = service.store.path.read_bytes()
    runner.tick()
    assert runner.storage_stopped
    assert service.store.path.read_bytes() == before
    # External restoration alone never reauthorizes the old running state.
    service.store.save(state)
    assert not runner.authorize(state["jobs"][0], state["batch_id"], {"action": "upload"})
    assert service.snapshot()["control"] == "paused"


@pytest.mark.parametrize("location", ["checkpoint", "answers"])
def test_invalid_json_stops_actions_and_retains_pages_and_intent(service, monkeypatch, location):
    from career_evidence_graph.application_worker import digest
    from career_evidence_graph.application_worker_browser import ApplicationRunner

    service.request("prepare", {"jobs": [job(service, 1), job(service, 2)]})
    answer = service.store.answers.put_answer(
        {"question": "Full name", "value": "Synthetic Person", "scope": {}, "state": "confirmed"}
    )
    start_run(service.store)
    service.request("resume", {"controller": "synthetic-controller"})
    state = service.store.load()
    intent = {"action": "upload", "attempt_id": "synthetic-retained-upload"}
    state["jobs"][0].update(intent=intent, status="filling", page_open=True)
    state["jobs"][1].update(
        status="ready_for_review",
        answer_refs=[{"key": answer["key"], "revision": digest(answer), "field_id": "name"}],
    )
    state["commands"] = [{"action": "answers-changed"}]
    service.store.save(state)
    runner = ApplicationRunner(service.store, None, service.fixture_origin)

    class RetainedPage:
        def is_closed(self):
            return False

    page = RetainedPage()
    identifier = state["jobs"][0]["application_id"]
    runner.pages[identifier] = page
    monkeypatch.setattr(runner, "process", lambda *_: pytest.fail("Storage failure must stop work"))
    path = service.store.path if location == "checkpoint" else service.store.answers.answers_path
    valid_bytes = path.read_bytes()
    path.write_bytes(b'{"broken":')

    runner.tick()

    assert runner.storage_stopped and service.store.stop_path.exists()
    assert path.read_bytes() == b'{"broken":'
    assert runner.pages[identifier] is page and not page.is_closed()
    # Repairing storage does not grant permission to repeat the retained action.
    path.write_bytes(valid_bytes)
    runner.tick()
    stopped = service.store.load()
    assert stopped["control"] == "paused"
    assert stopped["worker_error"] == "checkpoint_unavailable"
    assert stopped["jobs"][0]["intent"] == intent
    assert stopped["jobs"][0]["status"] == "needs_recheck"
    assert stopped["jobs"][0]["reason"] == "checkpoint_unavailable"
    assert not runner.authorize(stopped["jobs"][0], stopped["batch_id"], {"action": "upload"})
    assert runner.pages[identifier] is page and not page.is_closed()


def test_main_keeps_pumping_after_checkpoint_json_breaks(tmp_path, monkeypatch, request):
    from career_evidence_graph import application_worker_browser as browser

    applications = tmp_path / "applications"
    applications.mkdir()
    runtime = tmp_path / "worker"
    lifecycle = []
    pumps = []

    class Context:
        pages = []
        browser = None

        def on(self, *_args):
            pass

        def set_default_timeout(self, *_args):
            pass

        def wait_for_event(self, *_args, **_kwargs):
            pumps.append("events_pumped")
            assert (runtime / ".worker-stop.json").exists()
            assert (runtime / "run.json").read_bytes() == b'{"broken":'
            if len(pumps) == 2:
                raise KeyboardInterrupt

            async def absent_event():
                raise browser.TimeoutError("Synthetic event wait")

            return absent_event()

    context = Context()
    request.addfinalizer(OwnedCDPFake(SimpleNamespace(context=context)).close)
    context._impl_obj.wait_for_event = context.wait_for_event

    class Playwright:
        chromium = SimpleNamespace(launch_persistent_context=lambda *_args, **_kwargs: context)

        def __enter__(self):
            lifecycle.append("entered")
            return self

        def __exit__(self, kind, *_args):
            lifecycle.append(kind.__name__ if kind else "normal_exit")

    class FaultRunner(browser.ApplicationRunner):
        def tick(self):
            self.store.path.write_bytes(b'{"broken":')
            super().tick()
            assert self.storage_stopped

    monkeypatch.setattr(browser, "sync_playwright", Playwright)
    monkeypatch.setattr(browser, "ApplicationRunner", FaultRunner)
    result = browser.main(
        [
            "--applications",
            str(applications),
            "--runtime",
            str(runtime),
            "--fixture-origin",
            "http://127.0.0.1:9999",
        ]
    )
    assert result == 2
    assert pumps == ["events_pumped", "events_pumped"]
    assert lifecycle == ["entered", "KeyboardInterrupt"]
    assert (runtime / "run.json").read_bytes() == b'{"broken":'


def test_unknown_intent_cannot_be_overwritten_or_cleared_by_acknowledge(service):
    from career_evidence_graph.application_worker_browser import ApplicationRunner
    from career_evidence_graph.career_portal_data import PortalDataError

    service.request("prepare", {"jobs": [job(service)]})
    service.request("resume", {"controller": "synthetic-controller"})
    state = service.store.load()
    current = state["jobs"][0]
    intent = {"action": "upload", "attempt_id": "retained-unknown"}
    current.update(intent=intent, status="filling")
    service.store.save(state)
    runner = ApplicationRunner(service.store, None, service.fixture_origin)
    assert not runner.authorize(current, state["batch_id"], {"action": "upload"})
    runner.tick()
    assert service.store.load()["jobs"][0]["intent"] == intent
    assert service.store.load()["jobs"][0]["status"] == "needs_recheck"
    with pytest.raises(PortalDataError) as error:
        service.request(
            "recheck", {"application_id": current["application_id"], "acknowledge": True}
        )
    assert error.value.code == "action_unresolved"
    assert service.store.load()["jobs"][0]["intent"] == intent


@pytest.mark.worker_browser
def test_workbench_displays_unknown_action_and_runtime_history(tmp_path, monkeypatch):
    from playwright.sync_api import expect, sync_playwright
    from worker_preview_support import running_preview, stop_worker

    monkeypatch.setenv("PLAYWRIGHT_BROWSERS_PATH", "0")
    with running_preview(tmp_path, 1) as p:
        p.prepare(["CHE"])
        p.post("resume", controller=p.controller)
        p.wait(lambda state: state["jobs"][0]["status"] == "needs_input")
        retained_uploads = p.events()["uploads"]
        p.post("pause", controller=p.controller)
        with p.store.applications.write_lock():
            state = p.store.load()
            state["jobs"][0].update(
                status="needs_recheck",
                reason="upload_result_unknown",
                intent={"action": "upload", "attempt_id": "synthetic-unknown"},
            )
            state["jobs"][0]["observations"].append(
                {
                    "attempt_id": "synthetic-unknown",
                    "stage": "response",
                    "kind": "upload",
                    "http_status": 503,
                }
            )
            p.store.save(state)
        # Expose the live handoff control; the worker remains loopback-fixture-bound.
        p.worker.live = True
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            try:
                page = browser.new_page()
                page.goto(p.origin + "/#applications")
                root = page.locator("#worker-root")
                expect(root).to_contain_text("启动版本")
                expect(root).to_contain_text("结果待核验")
                expect(root).to_contain_text("HTTP 503")
                expect(root).to_contain_text("自动层不会重传")
                expect(root.get_by_role("region", name="证据与下一步")).to_contain_text(
                    "定位原页，核验故障点并记录具体结论与来源"
                )
                expect(root.get_by_role("button", name="核验后重新接管")).to_be_disabled()
                with p.store.applications.write_lock():
                    crashed = p.store.load()
                    crashed["jobs"][0]["reason"] = "page_crashed"
                    p.store.save(crashed)
                expect(root.get_by_role("region", name="证据与下一步")).to_contain_text(
                    "原页已报告崩溃"
                )
                expect(root.get_by_role("button", name="定位原页并核验", exact=True)).to_be_hidden()
                with p.store.applications.write_lock():
                    available = p.store.load()
                    available["jobs"][0]["reason"] = ""
                    p.store.save(available)
                root.get_by_role("button", name="定位原页并核验", exact=True).click()
                with page.expect_response(
                    lambda response: (
                        response.url.endswith("/api/worker/review")
                        and response.request.method == "POST"
                    )
                ) as review_response:
                    page.get_by_role("button", name="定位原页并人工核验", exact=True).click()
                assert review_response.value.status == 200, review_response.value.text()
                handed_off = p.wait(
                    lambda state: state["jobs"][0].get("handoff", {}).get("status") == "complete"
                )
                assert handed_off["mode"] == "synthetic"
                assert handed_off["jobs"][0]["intent"]["attempt_id"] == "synthetic-unknown"
                assert handed_off["jobs"][0]["status"] == "needs_recheck"
                assert handed_off["control"] == "paused"
                p.post("resume", controller=p.controller)
                # Visibility changes refresh state; they do not issue pause on their own.
                page.evaluate(
                    "Object.defineProperty(document, 'hidden', {configurable:true,value:true});"
                    "document.dispatchEvent(new Event('visibilitychange'))"
                )
                assert p.store.load()["control"] == "running"
                with p.store.applications.write_lock():
                    checkpoint = p.store.load()
                    checkpoint["heartbeat_at"] = time.time() - 61
                    observed_at = checkpoint["runtime"]["observed_at"]
                    p.store.save(checkpoint)
                # An old UI heartbeat does not revoke a healthy retained worker.
                refreshed = p.wait(lambda s: s["runtime"]["observed_at"] > observed_at)
                assert refreshed["control"] == "running"
                assert refreshed["jobs"][0]["intent"]["attempt_id"] == "synthetic-unknown"
                p.post("pause", controller=p.controller)
                page.evaluate(
                    "Object.defineProperty(document, 'hidden', {configurable:true,value:false});"
                    "document.dispatchEvent(new Event('visibilitychange'))"
                )
                assert p.store.load()["control"] == "paused"
                stop_worker(p)
                expect(root).to_contain_text("受管 worker 已退出", timeout=5000)
                expect(root.get_by_role("region", name="证据与下一步")).not_to_contain_text(
                    "当前受管原页"
                )
                assert p.events()["uploads"] == retained_uploads
                assert p.events()["submissions"] == []
            finally:
                browser.close()


def test_handoff_stops_authorization_before_browser_command(service):
    from career_evidence_graph.application_worker_browser import ApplicationRunner

    service.request("prepare", {"jobs": [job(service)]})
    service.request("resume", {"controller": "synthetic-controller"})
    state = service.store.load()
    current = state["jobs"][0]
    current.update(status="ready_for_review", page_open=True)
    service.store.save(state)
    identifier = current["application_id"]
    service.request("review", {"application_id": identifier})
    stopped = service.store.load()["jobs"][0]
    assert stopped["handed_off"] and stopped["handoff"]["status"] == "pending"
    runner = ApplicationRunner(service.store, None, service.fixture_origin)
    assert not runner.authorize(current, state["batch_id"], {"action": "fill"})
    runner.tick()
    stopped = service.store.load()["jobs"][0]
    assert stopped["handed_off"] and stopped["handoff"]["status"] == "unknown"


@pytest.mark.worker_browser
def test_native_human_page_survives_other_fault_pause_and_sync_retry(native_runner):
    service, runner, _ = native_runner
    state = service.store.load()
    first, second = state["jobs"]
    page = runner.pages[first["application_id"]]
    service.request(
        "answer",
        {
            "application_id": first["application_id"],
            "question_id": "sponsorship",
            "value": "No",
            "scope": {"application_id": first["application_id"], "country": "CHE"},
        },
    )
    deadline = time.monotonic() + 15
    while True:
        current = service.store.load()["jobs"][0]
        if current["status"] == "ready_for_review":
            break
        assert current["status"] not in {"needs_recheck", "cancelled"}, current["reason"]
        assert time.monotonic() < deadline, current["reason"]
        service.request("heartbeat", {"controller": "synthetic-controller"})
        runner.tick()
        page.wait_for_timeout(250)
    service.request("review", {"application_id": first["application_id"]})
    runner.tick()
    assert service.store.load()["jobs"][0]["handoff"]["status"] == "complete"
    before = page.locator("#name").input_value()
    runner.pages[second["application_id"]].close()
    service.request("pause", {"controller": "synthetic-controller"})
    runner.tick()
    assert not page.is_closed() and page.locator("#name").input_value() == before
    state = service.store.load()
    current = state["jobs"][0]
    changed = service.store.applications.update_application(
        current["application_id"], {"notes": "Retained external edit"}, current["revision"]
    )
    service.store.sync(current, "Synthetic result pending synchronization")
    assert current["sync_error"] == "revision-conflict"
    service.store.save(state)
    events_before = json.loads((service.store.root / "fixture-events.json").read_text())
    service.request(
        "retry-sync",
        {
            "application_id": current["application_id"],
            "revision": changed["revision"],
            "acknowledge": True,
        },
    )
    runner.tick()
    assert page.locator("#name").input_value() == before
    assert json.loads((service.store.root / "fixture-events.json").read_text()) == events_before
    app = service.store.applications.get_application(current["application_id"])
    assert app["notes"] == "Retained external edit"
    service.request("submitted", {"application_id": current["application_id"], "acknowledge": True})
    assert service.store.load()["jobs"][0]["receipt"] is None
    service.request(
        "receipt",
        {"application_id": current["application_id"], "locator": "synthetic user-verified receipt"},
    )
    current = service.store.load()["jobs"][0]
    assert current["manual_submission"]["source"] == "user_confirmation"
    assert current["receipt"]["source"] == "user_verified_receipt"


@pytest.mark.parametrize("conclusion", ["current_matches", "not_applied", "manual_stop"])
def test_resolution_is_durable_before_intent_clear(service, conclusion):
    from career_evidence_graph.career_portal_data import PortalDataError

    service.request("prepare", {"jobs": [job(service)]})
    state = service.store.load()
    current = state["jobs"][0]
    original = {
        "action": "upload",
        "attempt_id": "synthetic-unknown",
        "sha256": current["file_sha256"],
    }
    current.update(status="needs_recheck", intent=original)
    service.store.save(state)
    service.request(
        "resolve-action",
        {
            "application_id": current["application_id"],
            "intent_ref": "synthetic-unknown",
            "conclusion": conclusion,
            "source": "Synthetic current server readback",
        },
    )
    stored = service.store.load()["jobs"][0]
    assert stored["intent"] == original
    assert stored["action_resolutions"][-1]["intent"] == original
    assert stored["action_resolutions"][-1]["verified_by"] == "user"
    if conclusion == "manual_stop":
        with pytest.raises(PortalDataError) as error:
            service.request(
                "recheck", {"application_id": current["application_id"], "acknowledge": True}
            )
        assert error.value.code == "action_unresolved"
        assert service.store.load()["jobs"][0]["intent"] == original
    else:
        service.request(
            "recheck", {"application_id": current["application_id"], "acknowledge": True}
        )
        stored = service.store.load()["jobs"][0]
        assert stored["intent"] is None and stored["status"] == "queued"
        assert stored["action_resolutions"][-1]["intent"] == original
    assert service.store.load()["control"] == "paused"


@pytest.mark.parametrize("change", ["source", "intent_ref", "conclusion"])
def test_resolution_rejects_unbound_or_empty_evidence(service, change):
    from career_evidence_graph.career_portal_data import PortalDataError

    service.request("prepare", {"jobs": [job(service)]})
    state = service.store.load()
    current = state["jobs"][0]
    current["intent"] = {"action": "fill", "attempt_id": "current-unknown"}
    service.store.save(state)
    payload = {
        "application_id": current["application_id"],
        "intent_ref": "current-unknown",
        "conclusion": "current_matches",
        "source": "Synthetic verified current value",
    }
    payload[change] = ""
    before = service.store.path.read_bytes()
    with pytest.raises(PortalDataError) as error:
        service.request("resolve-action", payload)
    assert error.value.code == "action_resolution_required"
    assert service.store.path.read_bytes() == before


def test_unknown_handoff_cannot_be_reclaimed_by_generic_ack(service):
    from career_evidence_graph.career_portal_data import PortalDataError

    service.request("prepare", {"jobs": [job(service)]})
    state = service.store.load()
    state["jobs"][0].update(handed_off=True, status="needs_recheck", handoff={"status": "unknown"})
    service.store.save(state)
    with pytest.raises(PortalDataError) as error:
        service.request(
            "recheck", {"application_id": state["jobs"][0]["application_id"], "acknowledge": True}
        )
    assert error.value.code == "handoff_review_required"
    assert service.store.load()["jobs"][0]["handed_off"]


def test_recovery_checkpoint_failure_preserves_resolution_and_old_intent(service, monkeypatch):
    from career_evidence_graph.application_worker import helper

    service.request("prepare", {"jobs": [job(service)]})
    state = service.store.load()
    current = state["jobs"][0]
    current.update(
        status="needs_recheck",
        intent={
            "action": "upload",
            "attempt_id": "synthetic-old",
            "sha256": current["file_sha256"],
        },
    )
    service.store.save(state)
    service.request(
        "resolve-action",
        {
            "application_id": current["application_id"],
            "intent_ref": "synthetic-old",
            "conclusion": "not_applied",
            "source": "Synthetic authoritative readback",
        },
    )
    before = service.store.path.read_bytes()
    original = helper.atomic_write_json

    def fail(path, value):
        if path == service.store.path:
            raise OSError("synthetic recovery write failure")
        return original(path, value)

    monkeypatch.setattr(helper, "atomic_write_json", fail)
    with pytest.raises(OSError):
        service.request(
            "recheck", {"application_id": current["application_id"], "acknowledge": True}
        )
    assert service.store.path.read_bytes() == before
    retained = service.store.load()["jobs"][0]
    assert retained["intent"] and retained["action_resolutions"][-1]["source"]
    assert service.snapshot()["control"] == "paused"


def test_blocked_native_call_has_finite_deadline_and_retains_intent(service, monkeypatch):
    import signal

    from career_evidence_graph.application_worker_browser import ApplicationRunner

    service.request("prepare", {"jobs": [job(service)]})
    service.request("resume", {"controller": "synthetic-controller"})
    runner = ApplicationRunner(service.store, None, service.fixture_origin)
    runner.action_timeout = 0.02
    previous = signal.getsignal(signal.SIGALRM)

    def blocked(job, batch_id):
        assert runner.authorize(job, batch_id, {"action": "upload", "sha256": job["file_sha256"]})
        time.sleep(1)
        pytest.fail("An unbounded native call must not reach the next action")

    monkeypatch.setattr(runner, "process", blocked)
    began = time.monotonic()
    runner.tick()
    current = service.store.load()["jobs"][0]
    assert current["status"] == "needs_recheck" and current["intent"]["attempt_id"]
    assert time.monotonic() - began < 0.5
    assert signal.getsignal(signal.SIGALRM) == previous
    assert signal.getitimer(signal.ITIMER_REAL)[0] == 0


@pytest.mark.worker_browser
def test_independent_worker_survives_native_first_page_close(tmp_path, monkeypatch):
    import socket

    from playwright.sync_api import sync_playwright
    from worker_preview_support import running_preview

    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
    monkeypatch.setenv("PLAYWRIGHT_BROWSERS_PATH", "0")
    with running_preview(tmp_path, 2, cdp_port=port) as p:
        p.prepare(["CHE", "CHE"])
        p.post("resume", controller=p.controller)
        state = p.wait(lambda s: all(j["status"] == "needs_input" for j in s["jobs"]))
        retained_uploads = p.events()["uploads"]
        assert len(retained_uploads) == 2
        assert {item["id"] for item in retained_uploads} == {
            item["application_id"] for item in state["jobs"]
        }
        with sync_playwright() as pw:
            browser = pw.chromium.connect_over_cdp(f"http://127.0.0.1:{port}", timeout=4000)
            pages = browser.contexts[0].pages
            assert len(pages) == 2
            identifier = state["jobs"][0]["application_id"]
            first = next(page for page in pages if identifier in page.url)
            second = next(page for page in pages if page != first)
            first.close()
            result = p.wait(lambda s: s["jobs"][0]["reason"] == "page_closed", timeout=2)
            assert result["jobs"][0]["page_observation"]["run_id"] == result["runtime"]["id"]
            assert p.worker.process.poll() is None
            p.post(
                "answer",
                application_id=state["jobs"][1]["application_id"],
                question_id="sponsorship",
                value="No",
                scope={"application_id": state["jobs"][1]["application_id"], "country": "CHE"},
            )
            p.wait(lambda s: s["jobs"][1]["status"] == "ready_for_review")
            assert second.locator("#email").input_value() == "synthetic@example.invalid"
            assert p.events()["uploads"] == retained_uploads
            assert p.events()["submissions"] == []
            assert p.worker.process.poll() is None


def test_startup_source_drift_rejects_run_publication(service):
    before = service.store.path.read_bytes()
    with pytest.raises(ValueError, match="source changed"):
        start_run(service.store, expected_sources={})
    assert service.store.path.read_bytes() == before


def test_pid_reuse_never_binds_old_child_exit_to_new_run(service):
    start_run(service.store)
    service.process = SimpleNamespace(pid=os.getpid(), poll=lambda: -9)
    old = service.snapshot()["runtime"]["id"]
    assert service.process_run_id == old
    start_run(service.store)
    result = service.snapshot()
    assert result["runtime"]["id"] != old
    assert result["runtime_status"]["exit_code"] is None
    assert result["runtime_status"]["process"] == "unknown"


@pytest.mark.parametrize("change", ["clock", "commands", "intent"])
def test_malformed_checkpoint_is_retained_and_stops_actions(service, change):
    from career_evidence_graph.application_worker_browser import ApplicationRunner

    service.request("prepare", {"jobs": [job(service)]})
    state = service.store.load()
    runner = ApplicationRunner(service.store, None, service.fixture_origin)
    if change == "clock":
        state["heartbeat_at"] = "invalid"
    elif change == "commands":
        state["commands"] = [{"action": "unsupported"}]
    else:
        state["jobs"][0]["intent"] = ["invalid"]
    service.store.path.write_text(json.dumps(state))
    before = service.store.path.read_bytes()
    runner.tick()
    assert runner.storage_stopped
    assert service.store.path.read_bytes() == before
    with pytest.raises(ValueError):
        service.snapshot()


def test_action_resolution_cannot_revive_cancelled_job(service):
    from career_evidence_graph.application_worker_browser import ApplicationRunner
    from career_evidence_graph.career_portal_data import PortalDataError

    service.request("prepare", {"jobs": [job(service)]})
    service.request("resume", {"controller": "synthetic-controller"})
    runner = ApplicationRunner(service.store, None, service.fixture_origin)
    state = service.store.load()
    current = state["jobs"][0]
    assert runner.authorize(current, state["batch_id"], {"action": "open"})
    current = service.snapshot()["jobs"][0]
    service.request("cancel-job", {"application_id": current["application_id"]})
    service.request(
        "resolve-action",
        {
            "application_id": current["application_id"],
            "intent_ref": current["intent_ref"],
            "conclusion": "not_applied",
            "source": "Synthetic authoritative readback",
        },
    )
    retained = service.store.load()["jobs"][0]
    assert retained["status"] == "cancelled" and retained["intent"]
    with pytest.raises(PortalDataError) as error:
        service.request(
            "recheck", {"application_id": current["application_id"], "acknowledge": True}
        )
    assert error.value.code == "cancelled_job"
