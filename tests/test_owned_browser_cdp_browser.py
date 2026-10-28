"""Real locked Playwright transport on one synthetic Page; no native/model/input."""

import contextlib
import gc
import json
import os
import time
from pathlib import Path

import pytest
from playwright.sync_api import Error, TimeoutError, sync_playwright

from career_evidence_graph.application_worker_browser import browser_deadline
from career_evidence_graph.owned_browser_cdp import OwnedCDP, _state, pump_events

pytestmark = pytest.mark.worker_browser


@pytest.fixture
def original_page():
    loop_failures = []
    with sync_playwright() as playwright:
        options = (
            {} if Path(playwright.chromium.executable_path).is_file() else {"channel": "chrome"}
        )
        marker = os.environ.get("TS_PUMP_PROBE_MARKER", "owned-cdp-test")
        browser = playwright.chromium.launch(
            headless=True, args=[f"--ts-inflight-pump-probe={marker}"], **options
        )
        try:
            context = browser.new_context()
            context.route("**/*", lambda route: route.abort())
            page = context.new_page()
            page._impl_obj._loop.set_exception_handler(
                lambda _loop, failure: loop_failures.append(failure)
            )
            page.set_content("<!doctype html><title>Owned read</title><p>synthetic</p>")
            output = os.environ.get("TS_PUMP_PROBE_OUTPUT")
            if output:
                root = Path(output)
                (root / "ready.json").write_text(json.dumps({"pid": os.getpid(), "marker": marker}))
                deadline = time.monotonic() + 10
                while not (root / "go").exists():
                    assert time.monotonic() < deadline
                    time.sleep(0.01)
            yield playwright, browser, page
            if browser.is_connected():
                context.close()
        finally:
            if browser.is_connected():
                browser.close()
    gc.collect()
    assert not loop_failures


def hold_response(connection, monkeypatch, operation):
    original_send = connection._send_message_to_server
    original_dispatch = connection.dispatch
    exact = {"id": None, "held": None, "sends": 0}

    def send(owner, method, params, *args, **kwargs):
        callback = original_send(owner, method, params, *args, **kwargs)
        if (
            method == operation
            or operation == "read"
            and method == "send"
            and params.get("method") == "Page.getFrameTree"
        ):
            exact["sends"] += 1
            if exact["id"] is None:
                exact["id"] = callback.id
        return callback

    def dispatch(message):
        if message.get("id") == exact["id"] and exact["id"] is not None:
            exact["held"] = message
            return
        original_dispatch(message)

    monkeypatch.setattr(connection, "_send_message_to_server", send)
    monkeypatch.setattr(connection, "dispatch", dispatch)
    return exact, original_dispatch


@pytest.mark.parametrize("operation", ["read", "newCDPSession"])
def test_missing_response_is_bounded_and_late_result_only_cleans_up(
    original_page, monkeypatch, operation
):
    _, _, page = original_page
    connection = page._impl_obj._connection
    session = OwnedCDP(page).__enter__() if operation == "read" else None
    state = _state(page)
    with monkeypatch.context() as patch:
        exact, deliver = hold_response(connection, patch, operation)
        adopted = []
        status = "unknown"
        started = time.monotonic()
        with pytest.raises(Error), browser_deadline(0.15):
            if session is None:
                adopted.append(OwnedCDP(page, seconds=0.2).__enter__())
            else:
                adopted.append(session.send("Page.getFrameTree"))
        assert time.monotonic() - started < 1
        assert not page._impl_obj._dispatcher_fiber.dead
        assert state.pending and exact["held"] is not None
        assert not any(task.cancelling() for task in state.pending)
        with pytest.raises(Error, match="pending"):
            OwnedCDP(page).__enter__()
        with contextlib.suppress(TimeoutError):
            pump_events(page.context, 25)
        assert page.title() == "Owned read"
        connection._loop.call_soon(deliver, exact["held"])
        deadline = time.monotonic() + 2
        while state.pending or state.background:
            assert time.monotonic() < deadline
            with contextlib.suppress(TimeoutError):
                pump_events(page.context, 10)
        assert adopted == [] and status == "unknown" and exact["sends"] == 1
        assert exact["id"] not in connection._callbacks
    if session is not None:
        session.detach()
    assert not state.resources
    with OwnedCDP(page) as fresh:
        assert fresh.send("Page.getFrameTree")["frameTree"]["frame"]["url"] == page.url
    assert page.context.pages == [page]


def test_no_response_task_is_consumed_at_connection_close(original_page, monkeypatch):
    playwright, browser, page = original_page
    connection = page._impl_obj._connection
    session = OwnedCDP(page, seconds=0.1).__enter__()
    state = _state(page)
    with monkeypatch.context() as patch:
        exact, _ = hold_response(connection, patch, "read")
        with pytest.raises(Error):
            session.send("Page.getFrameTree")
        assert state.pending and exact["held"] is not None
        page.context.close()
        assert not state.resources
        browser.close()
    playwright.stop()
    assert state.closed and not state.pending and not state.background


def test_busy_renderer_read_timeout_keeps_dispatcher_and_original_document(original_page):
    _, _, page = original_page
    with OwnedCDP(page) as initial:
        expected = initial.send("Page.getFrameTree")["frameTree"]["frame"]
    started_busy = []
    page.on("console", lambda message: started_busy.append(message.text))
    page.evaluate("""() => setTimeout(() => {
        console.log('busy'); const end=Date.now()+1700;
        while(Date.now()<end){} console.log('done');
    }, 20)""")
    while "busy" not in started_busy:
        page.wait_for_timeout(5)
    with (
        pytest.raises(Error),
        browser_deadline(0.1),
        OwnedCDP(page, seconds=0.2) as session,
    ):
        exact_closed = []
        session.session.once("close", lambda *_: exact_closed.append(True))
        session.send("Page.getFrameTree")
    assert not page._impl_obj._dispatcher_fiber.dead
    page.wait_for_timeout(25)
    state = _state(page)
    cleanup_was_unconfirmed = False
    deadline = time.monotonic() + 3
    while "done" not in started_busy or state.pending or state.background or state.resources:
        cleanup_was_unconfirmed |= bool(state.failed_resources)
        assert time.monotonic() < deadline
        with contextlib.suppress(TimeoutError):
            pump_events(page.context, 10)
    assert cleanup_was_unconfirmed
    assert exact_closed == [True]
    with OwnedCDP(page) as fresh:
        observed = fresh.send("Page.getFrameTree")["frameTree"]["frame"]
    assert all(observed[key] == expected[key] for key in ("id", "loaderId", "url"))
    assert page.context.pages == [page]
    assert not state.resources
