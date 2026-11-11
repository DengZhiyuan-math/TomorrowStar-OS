"""Single-operation deadline and resource ownership, without a browser process."""

import asyncio
import importlib.metadata
import signal
import time
from types import SimpleNamespace

import pytest
from playwright.sync_api import Error, TimeoutError

from career_evidence_graph import owned_browser_cdp as cdp


def test_bridge_uses_the_locked_playwright_contract():
    assert importlib.metadata.version("playwright") == "1.63.0"


@pytest.fixture
def wire(monkeypatch):
    loop = asyncio.new_event_loop()
    calls, events, futures = [], {}, []
    connection = SimpleNamespace(
        _loop=loop, on=lambda name, callback: events.setdefault(name, callback)
    )

    class Channel:
        async def send(self, method, timeout, params=None):
            calls.append((method, timeout(None), params))
            future = loop.create_future()
            futures.append(future)
            try:
                return await asyncio.shield(future)
            except asyncio.CancelledError:
                # Locked PW waits for the original response in its abort path.
                await asyncio.shield(future)
                raise

    channel = Channel()
    impl = SimpleNamespace(
        _channel=channel,
        _connection=connection,
        is_closed=lambda: False,
        once=lambda name, callback: events.setdefault("context_" + name, callback),
    )
    context = SimpleNamespace(_impl_obj=impl)
    page = SimpleNamespace(_impl_obj=impl, context=context, _sync=loop.run_until_complete)
    context._sync = loop.run_until_complete
    monkeypatch.setattr(cdp, "from_channel", lambda value: value)
    yield SimpleNamespace(
        loop=loop,
        page=page,
        impl=impl,
        context=context,
        channel=channel,
        connection=connection,
        calls=calls,
        futures=futures,
        events=events,
    )
    for future in futures:
        if not future.done():
            future.set_exception(RuntimeError("synthetic connection closed"))
    if "close" in events:
        events["close"]()
    loop.run_until_complete(asyncio.sleep(0))
    loop.run_until_complete(asyncio.sleep(0))
    for task in asyncio.all_tasks(loop):
        task.cancel()
    loop.run_until_complete(asyncio.sleep(0))
    loop.close()


def test_expired_budget_sends_nothing(wire):
    with pytest.raises(Error):
        cdp.OwnedCDP(wire.page, seconds=0).__enter__()
    assert wire.calls == []


def test_silent_open_read_returns_and_blocks_new_proof_until_late_completion(wire):
    wire.loop.call_later(0.001, lambda: wire.futures[0].set_result(wire.impl))
    session = cdp.OwnedCDP(wire.page, seconds=0.03).__enter__()
    started = time.monotonic()
    with pytest.raises(Error):
        session.send("Page.getFrameTree")
    assert time.monotonic() - started < 0.2
    state = cdp._state(wire.page)
    assert len(state.pending) == 1
    with pytest.raises(Error, match="pending"):
        cdp.OwnedCDP(wire.page).__enter__()
    assert len(wire.calls) == 2
    wire.futures[1].set_result({"late": "never adopted"})
    wire.loop.run_until_complete(asyncio.sleep(0))
    wire.loop.run_until_complete(asyncio.sleep(0))
    assert not state.pending
    assert len(wire.calls) == 2


def test_late_acquire_is_retained_and_gets_one_bounded_detach(wire):
    with pytest.raises(Error):
        cdp.OwnedCDP(wire.page, seconds=0.01).__enter__()
    state = cdp._state(wire.page)
    assert len(state.pending) == 1
    assert not next(iter(state.pending)).cancelling()
    wire.futures[0].set_result(wire.impl)
    wire.loop.run_until_complete(asyncio.sleep(0.01))
    assert [call[0] for call in wire.calls] == ["newCDPSession", "detach"]
    assert wire.impl in state.resources.values()
    wire.futures[1].set_result(None)
    wire.loop.run_until_complete(asyncio.sleep(0.01))
    assert not state.pending and not state.resources


def test_close_consumes_never_returned_acquire_without_new_cleanup(wire):
    with pytest.raises(Error):
        cdp.OwnedCDP(wire.page, seconds=0.01).__enter__()
    state = cdp._state(wire.page)
    wire.events["close"]()
    wire.futures[0].set_exception(RuntimeError("closed"))
    wire.loop.run_until_complete(asyncio.sleep(0.01))
    assert not state.pending and not state.resources
    assert [call[0] for call in wire.calls] == ["newCDPSession"]


def test_absolute_budget_is_shared_and_no_expired_second_send(wire):
    wire.loop.call_later(0.015, lambda: wire.futures[0].set_result(wire.impl))
    session = cdp.OwnedCDP(wire.page, seconds=0.03).__enter__()
    wire.loop.call_later(0.005, lambda: wire.futures[1].set_result({"first": True}))
    assert session.send("Page.getFrameTree") == {"first": True}
    assert 0 < wire.calls[1][1] < wire.calls[0][1]
    time.sleep(0.02)
    with pytest.raises(Error):
        session.send("Page.getFrameTree")
    assert len(wire.calls) == 2


def test_outer_alarm_expires_at_safe_boundary_without_rearming(wire):
    observed = []
    previous = signal.signal(signal.SIGALRM, lambda *_: observed.append("unsafe signal"))
    signal.setitimer(signal.ITIMER_REAL, 0.02)
    try:
        with pytest.raises(Error):
            cdp.OwnedCDP(wire.page, seconds=1).__enter__()
        assert observed == []
        assert signal.getitimer(signal.ITIMER_REAL)[0] == 0
        assert wire.calls[0][1] <= 20
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous)


def test_cleanup_failure_cannot_publish_success(wire):
    wire.loop.call_later(0.001, lambda: wire.futures[0].set_result(wire.impl))
    with pytest.raises(Error), cdp.OwnedCDP(wire.page, cleanup_seconds=0.01):
        pass
    assert cdp._state(wire.page).resources
    assert [call[0] for call in wire.calls] == ["newCDPSession", "detach"]


def test_acquired_resource_survives_expiry_on_sync_return(wire):
    def delayed_return(coroutine):
        value = wire.loop.run_until_complete(coroutine)
        time.sleep(0.03)
        return value

    wire.page._sync = delayed_return
    wire.loop.call_later(0.001, lambda: wire.futures[0].set_result(wire.impl))
    signal.setitimer(signal.ITIMER_REAL, 0.02)
    try:
        with pytest.raises(Error):
            cdp.OwnedCDP(wire.page).__enter__()
        assert wire.impl in cdp._state(wire.page).resources.values()
        wire.loop.run_until_complete(asyncio.sleep(0.01))
        assert [call[0] for call in wire.calls] == ["newCDPSession", "detach"]
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)


def test_late_acquire_after_context_close_does_not_detach_again(wire):
    with pytest.raises(Error):
        cdp.OwnedCDP(wire.page, seconds=0.01).__enter__()
    wire.impl.is_closed = lambda: True
    wire.futures[0].set_result(wire.impl)
    wire.loop.run_until_complete(asyncio.sleep(0.01))
    assert not cdp._state(wire.page).resources
    assert [call[0] for call in wire.calls] == ["newCDPSession"]


def test_unconfirmed_cleanup_cannot_accumulate_new_sessions(wire):
    wire.loop.call_later(0.001, lambda: wire.futures[0].set_result(wire.impl))
    session = cdp.OwnedCDP(wire.page).__enter__()
    wire.loop.call_later(0.001, lambda: wire.futures[1].set_exception(TimeoutError("detach")))
    with pytest.raises(Error):
        session.detach()
    with pytest.raises(Error, match="pending"):
        cdp.OwnedCDP(wire.page).__enter__()
    assert len(wire.calls) == 2


def test_screenshot_keeps_exact_options_and_discards_late_result(wire):
    options = []

    async def take(**kwargs):
        options.append(kwargs)
        future = wire.loop.create_future()
        wire.futures.append(future)
        try:
            return await asyncio.shield(future)
        except asyncio.CancelledError:
            await asyncio.shield(future)
            raise

    wire.impl.screenshot = take
    with pytest.raises(Error):
        cdp.screenshot(wire.page, cdp.Deadline(0.01))
    assert options[0] == {
        "type": "png",
        "timeout": 2000,
        "animations": "allow",
        "caret": "initial",
        "scale": "css",
    }
    assert len(cdp._state(wire.page).pending) == 1
    wire.futures[0].set_result(b"late image")
    wire.loop.run_until_complete(asyncio.sleep(0.01))
    assert not cdp._state(wire.page).pending
    assert len(options) == 1


def test_nested_outer_budget_is_not_restarted_or_rearmed(wire):
    from playwright.sync_api import Error

    from career_evidence_graph.application_worker_browser import browser_deadline

    started = time.monotonic()
    with pytest.raises(Error), browser_deadline(0.02), browser_deadline(1):
        cdp.OwnedCDP(wire.page, seconds=1).__enter__()
    assert time.monotonic() - started < 0.2
    assert signal.getitimer(signal.ITIMER_REAL)[0] == 0
    assert 0 < wire.calls[0][1] <= 20


def test_unexpired_outer_alarm_charges_elapsed_time(wire):
    wire.loop.call_later(0.02, lambda: wire.futures[0].set_result(wire.impl))
    signal.setitimer(signal.ITIMER_REAL, 1)
    try:
        cdp.OwnedCDP(wire.page).__enter__()
        assert 0.5 < signal.getitimer(signal.ITIMER_REAL)[0] < 0.99
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)


def test_no_input_channel_is_exposed(wire):
    wire.loop.call_later(0.001, lambda: wire.futures[0].set_result(wire.impl))
    session = cdp.OwnedCDP(wire.page).__enter__()
    with pytest.raises(ValueError):
        session.send("Input.insertText", {"text": "must not send"})
    assert len(wire.calls) == 1


def test_catching_timeout_does_not_restart_an_existing_outer_scope(wire):
    from career_evidence_graph.application_worker_browser import browser_deadline

    with browser_deadline(0.01):
        with pytest.raises(Error):
            cdp.OwnedCDP(wire.page).__enter__()
        assert len(wire.calls) == 1
        with pytest.raises(Error):
            cdp.OwnedCDP(wire.page).__enter__()
        assert len(wire.calls) == 1


def test_cleanup_after_outer_expiry_is_queued_without_extending_caller(wire):
    from career_evidence_graph.application_worker_browser import browser_deadline

    wire.loop.call_later(0.001, lambda: wire.futures[0].set_result(wire.impl))
    started = time.monotonic()
    with pytest.raises(Error), browser_deadline(0.02), cdp.OwnedCDP(wire.page) as session:
        session.send("Page.getFrameTree")
    assert time.monotonic() - started < 0.2
    state = cdp._state(wire.page)
    assert state.resources and state.background
    assert len(wire.calls) == 2


def test_model_pause_preserves_nested_parents_without_double_extension(wire):
    from career_evidence_graph.application_worker_browser import (
        browser_deadline,
        pause_browser_deadline,
    )

    with browser_deadline(0.1), browser_deadline(0.08):
        parents = cdp._ACTIVE_DEADLINE.get()
        ends = [budget.end for budget in parents]
        started = time.monotonic()
        with pause_browser_deadline(), pause_browser_deadline():
            time.sleep(0.12)
            with cdp.browser_budget(0.01) as independent:
                time.sleep(0.02)
                with pytest.raises(Error):
                    independent.remaining()
        elapsed = time.monotonic() - started
        assert all(
            abs(budget.end - before - elapsed) < 0.01
            for budget, before in zip(parents, ends, strict=False)
        )
        wire.loop.call_later(0.001, lambda: wire.futures[0].set_result(wire.impl))
        cdp.OwnedCDP(wire.page).__enter__()
        assert signal.getitimer(signal.ITIMER_REAL)[0] > 0.04


def test_model_pause_does_not_resurrect_an_expired_parent():
    with cdp.browser_budget(0) as expired:
        end = expired.end
        with cdp.pause_browser_budget():
            time.sleep(0.01)
        assert expired.end == end
        with pytest.raises(Error):
            expired.remaining()


def test_exact_session_close_releases_only_that_unconfirmed_resource(wire):
    callbacks = {}
    first = SimpleNamespace(once=lambda name, callback: callbacks.setdefault("first", callback))
    other = SimpleNamespace(once=lambda name, callback: callbacks.setdefault("other", callback))
    state = cdp._state(wire.page)
    state.retain(first, wire.impl)
    state.retain(other, wire.impl)
    state.failed_resources.update((id(first), id(other)))
    callbacks["first"]()
    assert id(first) not in state.resources and id(first) not in state.failed_resources
    assert state.resources[id(other)] is other and id(other) in state.failed_resources


@pytest.mark.parametrize("expired", [False, True])
def test_event_pump_distinguishes_absent_event_from_exhausted_outer_budget(wire, expired):
    from career_evidence_graph.application_worker_browser import ApplicationRunner, browser_deadline

    async def wait_for_event(_event, *, timeout):
        await asyncio.sleep(timeout / 1000)
        raise TimeoutError("normal absent event")

    wire.impl.wait_for_event = wait_for_event
    runner = SimpleNamespace(
        shared_fault=None,
        work_progressed=True,
        context=wire.context,
        events=[],
        run_id="synthetic",
        page_ids={},
    )
    runner.event = lambda kind: ApplicationRunner.event(runner, kind)
    with browser_deadline(0.001 if expired else 1):
        ApplicationRunner.pump(runner)
    if expired:
        assert runner.shared_fault == "browser_connection_unknown"
        assert [event["event"] for event in runner.events] == ["browser_connection_unknown"]
    else:
        assert runner.shared_fault is None and runner.events == []


def test_connection_close_consumes_only_its_completed_protocol_tasks(wire):
    with pytest.raises(Error):
        cdp.OwnedCDP(wire.page, seconds=0.01).__enter__()
    state = cdp._state(wire.page)
    unrelated = wire.loop.create_task(asyncio.sleep(100))
    wire.futures[0].set_exception(RuntimeError("connection already closed"))
    wire.events["close"]()
    assert state.closed and not state.pending and not state.background
    assert not unrelated.done() and not unrelated.cancelling()


def test_connection_close_cannot_extend_expired_ambient_budget(wire):
    with pytest.raises(Error):
        cdp.OwnedCDP(wire.page, seconds=0.01).__enter__()
    state = cdp._state(wire.page)
    with cdp.browser_budget(0):
        started = time.monotonic()
        wire.events["close"]()
        assert time.monotonic() - started < 0.05
        assert state.pending  # No false drain proof after the budget expired.
    assert state.closed
