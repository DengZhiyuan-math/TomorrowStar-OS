"""Synthetic regressions for completed actions, one-send permits and cancellation."""

import json
import os
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

import pytest
from test_application_worker import job
from test_application_worker import service as _service
from test_career_portal_http import portal as _portal
from test_hosted_ats import PDF, forwarding_route, live_service, prepare
from test_worker_stability import native_runner as _native_runner
from worker_preview_support import advance_until, running_preview, stop_worker

from career_evidence_graph import hosted_ats
from career_evidence_graph.application_worker import start_run
from career_evidence_graph.application_worker_browser import ApplicationRunner
from career_evidence_graph.ats_forms import FORMS
from career_evidence_graph.career_portal_data import PortalDataError

service = _service
native_runner = _native_runner
portal = _portal


def test_portal_accepts_static_resource_burst_before_dispatch(portal):
    from contextlib import ExitStack
    from http.client import HTTPResponse
    from socket import create_connection
    from threading import Thread

    from career_evidence_graph.career_portal import create_server

    # Queue the document and its static resource burst before dispatch starts.
    with (
        create_server(portal.applications, portal.career, port=0) as server,
        ExitStack() as sockets,
    ):
        pending = [
            sockets.enter_context(create_connection(server.server_address, timeout=0.5))
            for _ in range(8)
        ]
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            for connection in pending:
                connection.settimeout(3)
                connection.sendall(
                    (
                        "GET /static/worker.js HTTP/1.0\r\n"
                        f"Host: 127.0.0.1:{server.server_port}\r\n\r\n"
                    ).encode()
                )
                response = HTTPResponse(connection)
                response.begin()
                assert response.status == 200 and b"WorkerPreview" in response.read()
        finally:
            server.shutdown()
            thread.join(timeout=3)
            assert not thread.is_alive()


def report(name, facts):
    destination = os.environ.get("TS_WORKER_REPORT_DIR")
    if destination:
        path = Path(destination)
        path.mkdir(parents=True, exist_ok=True)
        (path / (name + ".json")).write_text(json.dumps(facts, indent=2) + "\n")


@pytest.mark.parametrize("change", ["withdraw", "value", "scope", "unrelated"])
def test_handed_off_page_rechecks_only_changed_inputs_without_reclaiming_it(
    service, monkeypatch, change
):
    from career_evidence_graph.application_worker import digest

    service.request("prepare", {"jobs": [job(service, 1), job(service, 2)]})
    answer = service.store.answers.put_answer(
        {"question": "Full name", "value": "Synthetic Person", "scope": {}, "state": "confirmed"}
    )
    start_run(service.store)
    state = service.store.load()
    current, other = state["jobs"]
    current.update(
        status="ready_for_review",
        handed_off=True,
        page_open=True,
        handoff={"status": "complete", "source": "user_requested_handoff"},
        answer_refs=[{"key": answer["key"], "revision": digest(answer), "field_id": "name"}],
    )
    other.update(status="ready_for_review", page_open=False)
    service.store.save(state)
    before = deepcopy(current)
    runner = ApplicationRunner(service.store, None, service.fixture_origin)

    class HumanPage:
        content = "Synthetic manual edits that the worker must retain."

        def is_closed(self):
            return False

    page = HumanPage()
    identifier = current["application_id"]
    runner.pages[identifier] = page
    runner.page_ids[page] = "synthetic-manual-page"
    runner.handed_off_pages.add(page)
    monkeypatch.setattr(
        runner, "process", lambda *_: pytest.fail("Manual ownership must be retained")
    )
    edited_answer = (
        service.store.answers.put_answer(
            {"question": "Unrelated answer", "value": "Old", "scope": {}, "state": "confirmed"}
        )
        if change == "unrelated"
        else answer
    )
    change_payload = {
        "withdraw": {"withdraw": True},
        "value": {"value": "Synthetic Corrected Person"},
        "scope": {"value": answer["value"], "scope": {"company": current["company"]}},
        "unrelated": {"value": "New"},
    }[change]
    service.request(
        "library",
        {"key": edited_answer["key"], "revision": digest(edited_answer), **change_payload},
    )

    runner.tick()

    snapshot = service.snapshot()
    changed, untouched = snapshot["jobs"]
    if change == "unrelated":
        assert changed["status"] == "ready_for_review" and changed["reason"] == ""
    else:
        assert changed["status"] == "needs_recheck" and changed["reason"] == "answer_changed"
    assert changed["handed_off"] and changed["handoff"] == before["handoff"]
    assert changed["answer_refs"] == before["answer_refs"]
    assert changed["observations"] == before["observations"]
    assert changed["page_current"] and changed["page_open"]
    assert runner.pages[identifier] is page and page in runner.handed_off_pages
    assert page.content == "Synthetic manual edits that the worker must retain."
    assert untouched["status"] == "ready_for_review" and untouched["reason"] == ""
    assert snapshot["commands"] == []


@pytest.mark.worker_browser
def test_completed_actions_are_not_replayed_after_restart(tmp_path, monkeypatch):
    monkeypatch.setenv("PLAYWRIGHT_BROWSERS_PATH", "0")
    with running_preview(tmp_path, 1) as p:
        p.seed("Will you now or in the future require visa sponsorship?", "No", {"country": "USA"})
        p.prepare(["USA"])
        p.post("resume", controller=p.controller)
        first = p.wait(lambda s: s["jobs"][0]["status"] == "ready_for_review")
        old = p.store.load()["jobs"][0]
        before = len(p.events()["uploads"])
        fills = sum(o.get("action") == "fill" and o.get("verified") for o in old["observations"])
        assert before == 1 and fills == 3 and old["intent"] is None
        stop_worker(p)
        p.worker.spawn()
        restarted = p.wait(
            lambda s: (
                s["runtime"]["id"] != first["runtime"]["id"]
                and s["jobs"][0]["status"] == "needs_recheck"
            )
        )
        assert restarted["control"] == "paused" and len(p.events()["uploads"]) == before
        p.post("recheck", application_id=old["application_id"], acknowledge=True)
        p.post("resume", controller=p.controller)
        final = p.wait(lambda s: s["jobs"][0]["status"] in {"ready_for_review", "needs_recheck"})
        current = p.store.load()["jobs"][0]
        after_fills = sum(
            o.get("action") == "fill" and o.get("verified") for o in current["observations"]
        )
        report(
            "completed-restart",
            {
                "uploads_before": before,
                "uploads_after": len(p.events()["uploads"]),
                "fills_before": fills,
                "fills_after": after_fills,
                "old_run": first["runtime"]["id"],
                "new_run": final["runtime"]["id"],
                "status": current["status"],
                "reason": current["reason"],
                "automatic_submissions": len(p.events()["submissions"]),
                "real_ats_calls": 0,
            },
        )
        assert len(p.events()["uploads"]) == before and after_fills == fills
        assert current["status"] == "needs_recheck"
        assert current["reason"] == "recovered_result_not_visible"
        assert not p.events()["submissions"]


UPLOAD_HTML = """<title>Synthetic - Engineer</title>
<div class='posting-headline'><h2>Engineer</h2></div><form id='application-form'>
<div class='file-upload' aria-labelledby='upload-label-resume' aria-required='true'>
<div id='upload-label-resume'>Resume/CV *</div><input id='resume' name='resume' type='file'>
</div><span class='resume-upload-working' style='display:none'></span>
<span class='resume-upload-failure' style='display:none'></span></form><script>
const file=document.querySelector('#resume');file.onchange=async()=>{
  const data=new FormData();data.append('accountId','public-account');
  data.append('resume',file.files[0]);
  document.querySelector('.resume-upload-working').style.display='block';
  for(let n=0;n<(window.retryUploads?2:1);n++){
    try {await fetch('/parseResume',{method:'POST',body:data});} catch(error) {}
  }
  document.querySelector('.resume-upload-working').style.display='none';
  document.body.dataset.done='true';
};</script>"""


def intercept_uploads(context, runner, sent, denied, response="ok", html=UPLOAD_HTML):
    from playwright.sync_api import Error

    def intercept(route):
        dispatched = False

        def fetch(**options):
            nonlocal dispatched
            assert options == {"max_redirects": 0, "max_retries": 0, "timeout": 10000}
            dispatched = True
            if route.request.method == "POST":
                sent.append(route.request.url)
                if response == "lost":
                    raise Error("Synthetic response lost after dispatch")
                return SimpleNamespace(
                    status=503 if response == "http_error" else 200, dispose=lambda: None
                )
            return SimpleNamespace(status=200, dispose=lambda: None)

        def fulfill(*, response):
            if route.request.method == "POST":
                route.fulfill(status=response.status, json={})
            else:
                route.fulfill(status=response.status, body=html, content_type="text/html")

        def abort(reason):
            if not dispatched:
                denied.append(route.request.method)
            route.abort(reason)

        runner._live_guard(
            SimpleNamespace(request=route.request, fetch=fetch, fulfill=fulfill, abort=abort)
        )

    context.route("**/*", intercept)


@pytest.mark.worker_browser
@pytest.mark.parametrize("shift_fields", [False, True])
def test_completed_upload_on_new_native_page_is_not_replayed(tmp_path, monkeypatch, shift_fields):
    from playwright.sync_api import sync_playwright

    service = live_service(tmp_path, monkeypatch, lever_uploads=True)
    initial = prepare(service)
    if shift_fields:
        service.store.answers.put_answer(
            {
                "question": "Email",
                "value": "synthetic@example.invalid",
                "scope": {},
                "state": "confirmed",
                "source": "synthetic",
            }
        )
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True, channel="chromium")
        try:
            counts = []
            for index in range(2):
                context = browser.new_context(offline=True)
                start_run(service.store)
                runner = ApplicationRunner(service.store, context)
                sent, denied = [], []
                html = UPLOAD_HTML
                if shift_fields:
                    email = (
                        "<label for='email'>Email *</label><input id='email' type='email' required>"
                    )
                    extra = (
                        "<label for='nickname'>Nickname</label><input id='nickname'>"
                        if index
                        else ""
                    )
                    html = html.replace(
                        "<div class='file-upload'", extra + email + "<div class='file-upload'"
                    )
                intercept_uploads(context, runner, sent, denied, html=html)
                if index:
                    assert service.store.load()["control"] == "paused"
                    service.request(
                        "recheck",
                        {"application_id": initial["application_id"], "acknowledge": True},
                    )
                service.request("resume", {"controller": "synthetic-controller"})
                if not index:
                    advance_until(service, runner, lambda row: row["status"] == "ready_for_review")
                else:
                    # A restart cannot reclaim a document from the prior runtime.
                    for _ in range(4):
                        runner.tick()
                current = service.store.load()["jobs"][0]
                counts.append(len(sent))
                if not index:
                    assert current["status"] == "ready_for_review" and current["intent"] is None
                else:
                    assert current["status"] == "needs_recheck"
                    assert current["reason"] == "page_changed"
                assert sum(
                    o.get("action") == "fill" and o.get("verified") for o in current["observations"]
                ) == int(shift_fields)
                context.close()
            report(
                "completed-native-upload-" + str(shift_fields),
                {
                    "uploads_by_run": counts,
                    "shift_fields": shift_fields,
                    "verified_fills_after": int(shift_fields),
                    "real_ats_calls": 0,
                },
            )
            assert counts == [1, 0]
        finally:
            browser.close()


@pytest.mark.worker_browser
@pytest.mark.parametrize("response", ["http_error", "lost", "ok"])
def test_site_retry_cannot_reuse_an_upload_attempt(tmp_path, monkeypatch, response):
    from playwright.sync_api import sync_playwright

    service = live_service(tmp_path, monkeypatch, lever_uploads=True)
    current = prepare(service)
    start_run(service.store)
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True, channel="chromium")
        try:
            context = browser.new_context(offline=True)
            runner = ApplicationRunner(service.store, context)
            sent, denied = [], []
            intercept_uploads(context, runner, sent, denied, response)
            page = context.new_page()
            runner.pages[current["application_id"]] = page
            page.goto(hosted_ats.page_url(current))
            page.evaluate("window.retryUploads = true")
            resume = hosted_ats.observe(page, current)["fields"][0]
            service.request("resume", {"controller": "synthetic-controller"})
            assert runner.authorize(
                current,
                service.store.load()["batch_id"],
                {"action": "upload", "sha256": current["file_sha256"]},
            )
            runner.upload_job = current
            hosted_ats.control(page, resume).set_input_files(
                {"name": "resume.pdf", "mimeType": "application/pdf", "buffer": PDF}
            )
            page.locator('body[data-done="true"]').wait_for(timeout=3000)
            runner.upload_job = None
            for _ in range(3):
                runner.tick()
            durable = service.store.load()["jobs"][0]
            report(
                "one-attempt-" + response,
                {
                    "allowed_upload_requests": len(sent),
                    "blocked_methods": denied,
                    "intent": durable["intent"],
                    "status": durable["status"],
                    "dispatches": [
                        o
                        for o in durable["observations"]
                        if o.get("stage") == "dispatch_authorized"
                    ],
                    "real_ats_calls": 0,
                },
            )
            assert len(sent) == 1 and denied == ["POST"]
            assert durable["intent"] and durable["status"] == "needs_recheck"
            assert (
                sum(o.get("stage") == "dispatch_authorized" for o in durable["observations"]) == 1
            )
        finally:
            browser.close()


@pytest.mark.parametrize("platform", ["lever", "greenhouse"])
def test_synthetic_upload_attempt_is_consumed_before_dispatch(service, platform):
    service.request("prepare", {"jobs": [job(service)]})
    service.request("resume", {"controller": "synthetic-controller"})
    state = service.store.load()
    current = state["jobs"][0]
    runner = ApplicationRunner(service.store, None, service.fixture_origin)
    assert runner.authorize(
        current, state["batch_id"], {"action": "upload", "sha256": current["file_sha256"]}
    )
    outcomes = []
    for index in range(3):
        if index == 2:
            # A recreated guard must also honor the saved dispatch evidence.
            runner.persist(service.store.load())
            runner = ApplicationRunner(service.store, None, service.fixture_origin)
        route = forwarding_route(
            request=type(
                "Request",
                (),
                {
                    "method": "POST",
                    "url": service.fixture_origin
                    + FORMS[platform].upload_path(current["application_id"]),
                },
            )(),
        )
        runner._guard(current["application_id"], platform)(route)
        outcomes.append(route.outcome)
    assert outcomes == ["allowed", "blocked", "blocked"]
    assert service.store.load()["jobs"][0]["intent"]


@pytest.mark.parametrize("fault", ["synthetic_checkpoint", "live_checkpoint", "live_answers"])
def test_upload_guard_storage_errors_block_dispatch_and_retain_intent(
    service, tmp_path, monkeypatch, fault
):
    from test_hosted_ats import multipart

    if fault.startswith("live"):
        live_root = tmp_path / "live"
        live_root.mkdir()
        service = live_service(live_root, monkeypatch, lever_uploads=True)
        current = prepare(service)
        controller = "synthetic-live-controller"
    else:
        service.request("prepare", {"jobs": [job(service)]})
        current = service.store.load()["jobs"][0]
        controller = "synthetic-controller"
    start_run(service.store)
    service.request("resume", {"controller": controller})
    runner = ApplicationRunner(service.store, None, service.fixture_origin)
    page = object()
    runner.pages[current["application_id"]] = page
    assert runner.authorize(
        current,
        service.store.load()["batch_id"],
        {"action": "upload", "sha256": current["file_sha256"]},
    )
    intent = deepcopy(service.store.load()["jobs"][0]["intent"])
    if fault.startswith("live"):
        runner.upload_job = current
        url = "https://jobs.lever.co/parseResume"
    else:
        url = service.fixture_origin + FORMS["lever"].upload_path(current["application_id"])
    request = SimpleNamespace(
        method="POST",
        url=url,
        frame=SimpleNamespace(page=page),
        resource_type="fetch",
        headers={"content-type": "multipart/form-data; boundary=bound"},
        post_data_buffer=multipart(),
    )
    outcomes = []
    route = forwarding_route(request, allowed="sent")
    path = service.store.answers.answers_path if fault == "live_answers" else service.store.path
    valid_bytes = path.read_bytes()
    path.write_bytes(b'{"broken":')

    runner._guard(current["application_id"])(route)
    outcomes.append(route.outcome)

    assert outcomes == ["blocked"]
    assert runner.storage_stopped and service.store.stop_path.exists()
    assert path.read_bytes() == b'{"broken":'
    assert runner.pages[current["application_id"]] is page
    path.write_bytes(valid_bytes)
    assert service.store.load()["jobs"][0]["intent"] == intent


def cancelled_upload(service, conclusion="not_applied"):
    service.request("prepare", {"jobs": [job(service)]})
    service.request("resume", {"controller": "synthetic-controller"})
    state = service.store.load()
    current = state["jobs"][0]
    runner = ApplicationRunner(service.store, None, service.fixture_origin)
    assert runner.authorize(
        current, state["batch_id"], {"action": "upload", "sha256": current["file_sha256"]}
    )
    current = service.snapshot()["jobs"][0]
    service.request("cancel-job", {"application_id": current["application_id"]})
    service.request("pause", {"controller": "synthetic-controller"})
    if conclusion:
        service.request(
            "resolve-action",
            {
                "application_id": current["application_id"],
                "intent_ref": current["intent_ref"],
                "conclusion": conclusion,
                "source": "Synthetic authoritative readback",
            },
        )
    return {
        "application_id": current["application_id"],
        "intent_ref": current["intent_ref"],
        "acknowledge": True,
    }


@pytest.mark.parametrize("conclusion", ["current_matches", "not_applied"])
@pytest.mark.parametrize("submitted", [False, True])
def test_cancelled_action_settlement_preserves_history_and_allows_new_batch(
    service, conclusion, submitted
):
    payload = cancelled_upload(service, conclusion)
    state = service.store.load()
    state["jobs"][0]["handed_off"] = True
    service.store.save(state)
    if submitted:
        service.request("submitted", payload)
        service.request("receipt", {**payload, "locator": "Synthetic employer receipt"})
    original = deepcopy(service.store.load()["jobs"][0])
    service.request("settle-cancelled", payload)
    settled = deepcopy(service.store.load()["jobs"][0])
    assert settled["status"] == "cancelled" and settled["intent"] is None
    assert settled["handed_off"] is True and settled["action_resolutions"]
    assert service.store.load()["control"] == "paused" and not service.store.load()["commands"]
    assert settled["observations"][-1]["intent"] == original["intent"]
    assert settled["manual_submission"] == original["manual_submission"]
    assert settled["receipt"] == original["receipt"]
    with pytest.raises(PortalDataError) as error:
        service.request("recheck", payload)
    assert error.value.code == "cancelled_job"
    service.request("prepare", {"jobs": [job(service, 2)]})
    final = service.store.load()
    assert final["jobs"][0]["application_id"] != payload["application_id"]
    assert final["control"] == "paused" and final["batch_history"][-1]["jobs"][0] == settled
    report(
        f"cancelled-{conclusion}-{submitted}",
        {
            "old_status": settled["status"],
            "intent_cleared": settled["intent"] is None,
            "handoff_preserved": settled["handed_off"],
            "new_batch_control": final["control"],
            "history_preserved": final["batch_history"][-1]["jobs"][0] == settled,
        },
    )


@pytest.mark.parametrize(
    "condition,code",
    [
        ("unresolved", "action_unresolved"),
        ("manual_stop", "action_unresolved"),
        ("open_page", "pages_retained"),
        ("wrong_intent", "action_resolution_required"),
        ("no_ack", "settlement_required"),
        ("active_job", "not_cancelled"),
    ],
)
def test_cancelled_settlement_rejects_unsafe_inputs_without_mutation(service, condition, code):
    payload = cancelled_upload(
        service,
        None
        if condition == "unresolved"
        else "manual_stop"
        if condition == "manual_stop"
        else "not_applied",
    )
    state = service.store.load()
    if condition == "open_page":
        state["jobs"][0]["page_open"] = True
    elif condition == "active_job":
        state["jobs"][0]["status"] = "needs_recheck"
    elif condition == "wrong_intent":
        payload["intent_ref"] = "stale-attempt"
    elif condition == "no_ack":
        payload["acknowledge"] = False
    service.store.save(state)
    before = service.store.path.read_bytes()
    with pytest.raises(PortalDataError) as error:
        service.request("settle-cancelled", payload)
    assert error.value.code == code and service.store.path.read_bytes() == before


def test_cancelled_settlement_checkpoint_failure_retains_old_intent(service, monkeypatch):
    from career_evidence_graph.application_worker import helper

    payload = cancelled_upload(service)
    before = service.store.path.read_bytes()
    original = helper.atomic_write_json

    def fail(path, value):
        if path == service.store.path:
            raise OSError("Synthetic settlement checkpoint failure")
        return original(path, value)

    monkeypatch.setattr(helper, "atomic_write_json", fail)
    with pytest.raises(OSError):
        service.request("settle-cancelled", payload)
    assert service.store.path.read_bytes() == before
    retained = service.store.load()["jobs"][0]
    assert retained["status"] == "cancelled" and retained["intent"]
    assert retained["action_resolutions"][-1]["conclusion"] == "not_applied"
    assert service.snapshot()["control"] == "paused"


def test_cancelled_inflight_verified_result_is_retained_without_reviving(service):
    payload = cancelled_upload(service, None)
    state = service.store.load()
    current = deepcopy(state["jobs"][0])
    intent = deepcopy(current["intent"])
    runner = ApplicationRunner(service.store, None, service.fixture_origin)
    runner.update(current, state["batch_id"], intent=None, status="ready_for_review")
    settled = service.store.load()["jobs"][0]
    assert settled["status"] == "cancelled" and settled["intent"] is None
    assert settled["observations"][-1]["intent"] == intent
    assert settled["observations"][-1]["result"] == "verified"
    service.request("prepare", {"jobs": [job(service, 2)]})
    assert service.store.load()["batch_history"][-1]["jobs"][0] == settled
    assert service.store.load()["jobs"][0]["application_id"] != payload["application_id"]


@pytest.mark.worker_browser
def test_human_page_must_be_released_before_cancelled_settlement(native_runner):
    service, runner, _ = native_runner
    current = service.store.load()["jobs"][0]
    identifier = current["application_id"]
    service.request(
        "answer",
        {"application_id": identifier, "question_id": "sponsorship", "value": "No"},
    )
    runner.tick()
    advance_until(service, runner, lambda row: row["status"] == "ready_for_review")
    service.request("review", {"application_id": identifier})
    runner.tick()
    state = service.store.load()
    current = state["jobs"][0]
    # Model a late unknown result after the valid page was handed to the user.
    current.update(status="needs_recheck", reason="action_result_unknown")
    current["intent"] = {
        "action": "upload",
        "attempt_id": "synthetic-cancelled-human",
        "sha256": current["file_sha256"],
    }
    service.store.save(state)
    human_page = runner.pages[identifier]
    other_page = runner.pages[state["jobs"][1]["application_id"]]
    before = human_page.locator("#name").input_value()
    service.request("pause", {"controller": "synthetic-controller"})
    service.request("cancel-job", {"application_id": identifier})
    service.request(
        "resolve-action",
        {
            "application_id": identifier,
            "intent_ref": "synthetic-cancelled-human",
            "conclusion": "not_applied",
            "source": "Synthetic authoritative upload readback",
        },
    )
    payload = {
        "application_id": identifier,
        "intent_ref": "synthetic-cancelled-human",
        "acknowledge": True,
    }
    with pytest.raises(PortalDataError) as error:
        service.request("settle-cancelled", payload)
    assert error.value.code == "pages_retained"
    assert human_page in runner.handed_off_pages
    assert not human_page.is_closed() and human_page.locator("#name").input_value() == before
    requests_before = json.loads((service.store.root / "fixture-events.json").read_text())
    service.request("release", {"application_id": identifier})
    runner.tick()
    service.request("settle-cancelled", payload)
    runner.tick()
    settled = service.store.load()["jobs"][0]
    assert human_page.is_closed() and not other_page.is_closed()
    assert settled["status"] == "cancelled" and settled["handed_off"] and settled["intent"] is None
    assert service.store.load()["control"] == "paused"
    assert json.loads((service.store.root / "fixture-events.json").read_text()) == requests_before
    report(
        "cancelled-human-page",
        {
            "closed_after_explicit_release": human_page.is_closed(),
            "other_page_retained": not other_page.is_closed(),
            "new_browser_requests": 0,
            "status": settled["status"],
            "handoff_preserved": settled["handed_off"],
        },
    )


@pytest.mark.worker_browser
def test_workbench_settles_cancelled_action_without_resuming(tmp_path, monkeypatch):
    from playwright.sync_api import expect, sync_playwright

    monkeypatch.setenv("PLAYWRIGHT_BROWSERS_PATH", "0")
    with running_preview(tmp_path, 1) as p:
        p.prepare(["USA"])
        state = p.store.load()
        current = state["jobs"][0]
        current.update(
            status="cancelled",
            intent={
                "action": "upload",
                "attempt_id": "ui-cancelled",
                "sha256": current["file_sha256"],
            },
        )
        p.store.save(state)
        p.post(
            "resolve-action",
            application_id=current["application_id"],
            intent_ref="ui-cancelled",
            conclusion="not_applied",
            source="Synthetic authoritative server readback",
        )
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True, channel="chromium")
            try:
                page = browser.new_page()
                page.goto(p.origin + "/#applications")
                card = page.locator(f'[data-job-id="{current["application_id"]}"]')
                settle = card.get_by_role("button", name="结算已取消岗位", exact=True)
                expect(settle).to_be_visible(timeout=10000)
                settle.click()
                page.locator("#confirmation-continue").click()
                settled = p.wait(lambda s: s["jobs"][0]["intent"] is None)
                assert (
                    settled["control"] == "paused" and settled["jobs"][0]["status"] == "cancelled"
                )
                expect(card.get_by_text("已取消", exact=True)).to_be_visible()
                expect(settle).to_have_count(0)
                p.post("prepare", jobs=[job(p.worker, 2)])
                assert p.store.load()["batch_history"][-1]["jobs"][0]["intent"] is None
                assert p.store.load()["control"] == "paused" and p.events()["uploads"] == []
                assert p.events()["submissions"] == []
            finally:
                browser.close()


def try_recheck(service, identifier):
    try:
        service.request(
            "recheck",
            {
                "application_id": identifier,
                "acknowledge": True,
                "reclaim": True,
                "handoff_source": "Synthetic explicit ownership check after cancellation",
            },
        )
    except PortalDataError as error:
        return error.code
    return None


@pytest.mark.parametrize("conclusion", ["not_applied", "manual_stop"])
@pytest.mark.parametrize("ordering", ["forward", "backward", "legacy_early", "legacy_late"])
def test_completion_and_resolution_keep_attempt_order(service, monkeypatch, conclusion, ordering):
    cancelled_upload(service, conclusion)
    state = service.store.load()
    current = deepcopy(state["jobs"][0])
    resolution = current["action_resolutions"][-1]
    if ordering.startswith("legacy"):
        state["jobs"][0]["action_resolutions"][-1].pop("observation_count", None)
        service.store.save(state)
    # The response may complete after a wall-clock correction. New checkpoints
    # must use the append order, while old checkpoints retain their time evidence.
    completed_at = resolution["at"] + (-60 if ordering == "backward" else 60)
    monkeypatch.setattr(
        "career_evidence_graph.application_worker_browser.time.time", lambda: completed_at
    )
    runner = ApplicationRunner(service.store, None, service.fixture_origin)
    runner.update(current, state["batch_id"], intent=None, status="ready_for_review")
    saved = service.store.load()
    if ordering == "legacy_late":
        saved["jobs"][0]["action_resolutions"][-1]["at"] = completed_at + 60
        service.store.save(saved)
    before = service.store.path.read_bytes()
    result = ApplicationRunner.recovered_upload(service.store.load()["jobs"][0])
    assert result is (ordering != "legacy_late")
    assert service.store.path.read_bytes() == before
    assert service.store.load()["jobs"][0]["status"] == "cancelled"


@pytest.mark.worker_browser
@pytest.mark.parametrize("conclusion", ["not_applied", "manual_stop"])
def test_later_verified_upload_survives_earlier_resolution(tmp_path, monkeypatch, conclusion):
    from playwright.sync_api import sync_playwright

    service = live_service(tmp_path, monkeypatch, lever_uploads=True)
    initial = prepare(service)
    identifier = initial["application_id"]
    first = None
    counts = []
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True, channel="chromium")
        try:
            for index in range(2):
                context = browser.new_context(offline=True)
                start_run(service.store)
                runner = ApplicationRunner(service.store, context)
                sent, denied = [], []
                intercept_uploads(context, runner, sent, denied)
                if index == 0:
                    original_track = runner.track_request

                    def resolve_inflight(request, current, kind, track=original_track):
                        accepted = track(request, current, kind)
                        if accepted and kind == "resume_parse":
                            # The permit is consumed. The synthetic endpoint has not
                            # applied the already-authorized request or replied yet.
                            intent = service.store.load()["jobs"][0]["intent"]
                            service.request(
                                "resolve-action",
                                {
                                    "application_id": identifier,
                                    "intent_ref": intent["attempt_id"],
                                    "conclusion": conclusion,
                                    "source": "Synthetic readback before pending upload is applied",
                                },
                            )
                        return accepted

                    runner.track_request = resolve_inflight
                else:
                    assert service.store.load()["control"] == "paused"
                    service.request("recheck", {"application_id": identifier, "acknowledge": True})
                service.request("resume", {"controller": "synthetic-controller"})
                for _ in range(4):
                    runner.tick()
                current = service.store.load()["jobs"][0]
                counts.append(len(sent))
                if index == 0:
                    first = deepcopy(current)
                    result = next(
                        o
                        for o in first["observations"]
                        if o.get("action") == "action_result"
                        and o.get("result") == "verified"
                        and o.get("intent", {}).get("action") == "upload"
                    )
                    resolution = first["action_resolutions"][0]
                    assert result["intent"]["attempt_id"] == resolution["intent_ref"]
                    assert result["at"] > resolution["at"]
                    assert first["intent"] is None
                context.close()
            report(
                "late-result-" + conclusion,
                {
                    "uploads_by_run": counts,
                    "first_resolution": resolution,
                    "later_verified_result": result,
                    "first_completed_intent": first["intent"],
                    "completed_upload_recognized": ApplicationRunner.recovered_upload(first),
                    "first_status": first["status"],
                    "second_status": current["status"],
                    "second_reason": current["reason"],
                    "second_active_intent": current["intent"],
                    "real_ats_calls": 0,
                    "automatic_final_requests": 0,
                },
            )
            assert counts == [1, 0], "A later verified completion must prevent replay after restart"
        finally:
            browser.close()


@pytest.mark.parametrize("pending", ["review", "partial_review", "recheck", "release_error"])
def test_pending_commands_preserve_cancelled_status(service, tmp_path, monkeypatch, pending):
    from playwright.sync_api import Error

    if pending == "partial_review":
        partial_root = tmp_path / "partial-review"
        partial_root.mkdir()
        service = live_service(partial_root, monkeypatch)
        prepare(service)
        start_run(service.store)
    else:
        service.request("prepare", {"jobs": [job(service)]})
    state = service.store.load()
    current = state["jobs"][0]
    identifier = current["application_id"]
    current.update(
        status="needs_input" if pending == "partial_review" else "ready_for_review", page_open=True
    )
    if pending == "partial_review":
        current["page_observation"] = {
            "run_id": state["runtime"]["id"],
            "page_id": "synthetic-partial-review-page",
            "event": "observed",
            "at": state["runtime"]["observed_at"],
        }
    service.store.save(state)
    runner = ApplicationRunner(service.store, None, service.fixture_origin)

    class Page:
        def is_closed(self):
            return False

        def close(self):
            raise Error("Synthetic native page close failure")

    runner.pages[identifier] = Page()
    if pending in {"review", "partial_review"}:
        service.request("review", {"application_id": identifier, "acknowledge": True})
    elif pending == "recheck":
        service.request("recheck", {"application_id": identifier, "acknowledge": True})
    service.request("cancel-job", {"application_id": identifier})
    if pending == "release_error":
        service.request("release", {"application_id": identifier})
    before = deepcopy(service.store.load()["jobs"][0])
    runner.tick()
    after = deepcopy(service.store.load()["jobs"][0])
    rejection = try_recheck(service, identifier)
    report(
        "cancelled-command-" + pending,
        {
            "status_before_command": before["status"],
            "status_after_command": after["status"],
            "reason": after["reason"],
            "handoff": after.get("handoff"),
            "handed_off": after["handed_off"],
            "recheck_rejected_code": rejection,
            "status_after_recheck": service.store.load()["jobs"][0]["status"],
            "automatic_final_requests": 0,
            "real_ats_calls": 0,
        },
    )
    assert after["status"] == "cancelled", "Pending commands must not revive a cancelled job"
    assert rejection == "cancelled_job"
    assert after["handed_off"] == before["handed_off"]
    assert service.store.load()["control"] == "paused"


@pytest.mark.worker_browser
def test_native_release_failure_preserves_cancelled_status(native_runner, monkeypatch):
    from playwright.sync_api import Error

    service, runner, _ = native_runner
    state = service.store.load()
    pending = deepcopy(state["jobs"][0])
    assert runner.authorize(
        pending, state["batch_id"], {"action": "upload", "sha256": pending["file_sha256"]}
    )
    service.request("pause", {"controller": "synthetic-controller"})
    identifier = service.store.load()["jobs"][0]["application_id"]
    page = runner.pages[identifier]
    other = service.store.load()["jobs"][1]["application_id"]
    service.request("cancel-job", {"application_id": identifier})
    intent = deepcopy(service.store.load()["jobs"][0]["intent"])
    payload = {
        "application_id": identifier,
        "intent_ref": intent["attempt_id"],
        "acknowledge": True,
    }
    service.request(
        "resolve-action",
        {**payload, "conclusion": "not_applied", "source": "Synthetic current readback"},
    )
    events_path = service.store.root / "fixture-events.json"
    events_before = events_path.read_bytes()
    original_close = page.close

    def close_error():
        raise Error("Synthetic native page close failure")

    monkeypatch.setattr(page, "close", close_error)
    service.request("release", {"application_id": identifier})
    runner.tick()
    after = deepcopy(service.store.load()["jobs"][0])
    rejection = try_recheck(service, identifier)
    report(
        "cancelled-native-release-error",
        {
            "status_after_command": after["status"],
            "reason": after["reason"],
            "recheck_rejected_code": rejection,
            "status_after_recheck": service.store.load()["jobs"][0]["status"],
            "target_page_retained": not page.is_closed(),
            "other_page_retained": not runner.pages[other].is_closed(),
            "real_ats_calls": 0,
        },
    )
    assert after["status"] == "cancelled", "A page command error must retain cancellation"
    assert rejection == "cancelled_job"
    assert after["intent"] == intent and after["observations"][-1]["event"] == "page_command_failed"
    with pytest.raises(PortalDataError) as error:
        service.request("settle-cancelled", payload)
    assert error.value.code == "pages_retained"
    monkeypatch.setattr(page, "close", original_close)
    service.request("release", {"application_id": identifier})
    runner.tick()
    service.request("settle-cancelled", payload)
    settled = deepcopy(service.store.load()["jobs"][0])
    assert settled["status"] == "cancelled" and settled["intent"] is None
    assert page.is_closed() and not runner.pages[other].is_closed()
    service.request("cancel-job", {"application_id": other})
    service.request("release", {"application_id": other})
    runner.tick()
    # Keep the final page-close observations as part of the old job history.
    settled = deepcopy(service.store.load()["jobs"][0])
    service.request("prepare", {"jobs": [job(service, 3)]})
    final = service.store.load()
    assert final["control"] == "paused" and final["batch_history"][-1]["jobs"][0] == settled
    assert events_path.read_bytes() == events_before
    report(
        "cancelled-native-release-settlement-history",
        {
            "status_after_settlement": settled["status"],
            "history_preserved": True,
            "new_batch_control": final["control"],
            "new_browser_requests": 0,
            "manual_owner_preserved": settled["handed_off"] == after["handed_off"],
        },
    )
