"""Bound original-Page reads through the locked Playwright 1.63 channel bridge.

Only one protocol operation is owned by each task. A timed-out proof never
continues from a late response. Pending tasks/resources belong to the existing
connection until their exact response or connection close; no browser is created.
"""

import asyncio
import signal
import time
from contextlib import contextmanager, suppress
from contextvars import ContextVar

from playwright._impl._connection import from_channel
from playwright.sync_api import Error

READ_METHODS = frozenset(
    {
        "Page.getFrameTree",
        "Page.createIsolatedWorld",
        "Runtime.evaluate",
        "Runtime.getProperties",
        "Runtime.releaseObject",
        "Target.getTargetInfo",
    }
)
_ACTIVE_DEADLINE = ContextVar("owned_browser_deadline", default=None)


@contextmanager
def browser_budget(seconds):
    """Keep an existing caller scope's absolute budget after its alarm expires."""
    parents = _ACTIVE_DEADLINE.get() or ()
    budget = Deadline(seconds)
    if parents:
        budget.end = min(budget.end, parents[-1].end)
    token = _ACTIVE_DEADLINE.set((*parents, budget))
    try:
        yield budget
    finally:
        _ACTIVE_DEADLINE.reset(token)


@contextmanager
def pause_browser_budget():
    """Model time is excluded once from each still-live browser parent scope."""
    parents = _ACTIVE_DEADLINE.get() or ()
    started = time.monotonic()
    live = [budget for budget in parents if budget.end > started]
    token = _ACTIVE_DEADLINE.set(None)
    try:
        yield
    finally:
        elapsed = time.monotonic() - started
        for budget in live:
            budget.end += elapsed
            budget.paused += elapsed
        _ACTIVE_DEADLINE.reset(token)


class Deadline:
    def __init__(self, seconds):
        self.end = time.monotonic() + seconds
        self.paused = 0

    def remaining(self, _unused=None):
        remaining = self.end - time.monotonic()
        if remaining <= 0:
            raise Error("owned_browser_read_timeout")
        return remaining * 1000


@contextmanager
def _safe_alarm(deadline):
    """Suspend only around an already bounded call; charge, never freeze, time."""
    started = time.monotonic()
    previous = signal.setitimer(signal.ITIMER_REAL, 0)
    parents = _ACTIVE_DEADLINE.get() or ()
    if parents:
        deadline.end = min(deadline.end, parents[-1].end)
    if previous[0]:
        deadline.end = min(deadline.end, started + previous[0])
    try:
        deadline.remaining()
        yield
    finally:
        if previous[0]:
            remaining = previous[0] - (time.monotonic() - started)
            if remaining > 0:
                signal.setitimer(signal.ITIMER_REAL, remaining, previous[1])
            else:
                # Raising here is on the caller's stack, after _sync returned.
                # Never rearm an expired alarm into the next dispatcher switch.
                raise Error("owned_browser_outer_timeout")


class _ConnectionState:
    def __init__(self, connection):
        self.pending = set()
        self.resources = {}
        self.resource_contexts = {}
        self.contexts = set()
        self.background = set()
        self.failed_resources = set()
        self.closed = False
        connection.on("close", self.close)

    def close(self, *_args):
        self.closed = True
        self.resources.clear()
        self.resource_contexts.clear()
        self.failed_resources.clear()
        # Connection.cleanup completes the actual protocol futures. Their done
        # callbacks consume outcomes; close does not assert native input drain.
        owned = tuple(self.pending | self.background)
        if not owned:
            return
        loop = owned[0].get_loop()
        if loop.is_running() or loop.is_closed():
            return
        # Locked stop_sync emits close after stopping this loop, immediately
        # before __exit__ cancels tasks. Consume only these already-owned reads
        # while their completed protocol futures can still run their callbacks.
        deadline = Deadline(0.1)
        try:
            with _safe_alarm(deadline):
                done, _ = loop.run_until_complete(
                    asyncio.wait(owned, timeout=deadline.remaining() / 1000)
                )
                for task in done:
                    _consume(task)
                    self.pending.discard(task)
                    self.background.discard(task)
        except Error:
            # An exhausted caller cannot fund cleanup. Keep unresolved ownership.
            pass

    def retain(self, session, context):
        if self.closed or context.is_closed():
            return False
        self.resources[id(session)] = session
        self.resource_contexts[id(session)] = id(context)
        session.once("close", lambda *_args: self.released(session))
        if id(context) not in self.contexts:
            self.contexts.add(id(context))

            def context_closed(*_args):
                for key, owner in list(self.resource_contexts.items()):
                    if owner == id(context):
                        self.resources.pop(key, None)
                        self.resource_contexts.pop(key, None)
                        self.failed_resources.discard(key)
                self.contexts.discard(id(context))

            context.once("close", context_closed)
        return True

    def released(self, session):
        self.resources.pop(id(session), None)
        self.resource_contexts.pop(id(session), None)
        self.failed_resources.discard(id(session))


def _state(owner):
    connection = owner._impl_obj._connection
    state = getattr(connection, "_tomorrowstar_cdp_state", None)
    if state is None:
        state = _ConnectionState(connection)
        connection._tomorrowstar_cdp_state = state
    return state


def _consume(task):
    with suppress(Exception, asyncio.CancelledError):
        task.result()


async def _operation(
    state,
    channel,
    method,
    params,
    deadline,
    *,
    cleanup=False,
    acquisition_context=None,
    cleanup_resource=None,
):
    if (
        state.closed
        or (state.pending or state.background or state.failed_resources)
        and not cleanup
    ):
        raise Error("owned_browser_read_pending")
    seconds = deadline.remaining() / 1000
    task = asyncio.create_task(channel.send(method, deadline.remaining, params))
    state.pending.add(task)

    def completed(done):
        state.pending.discard(done)
        if cleanup_resource is not None and not done.cancelled() and done.exception() is None:
            state.released(cleanup_resource)
        _consume(done)

    task.add_done_callback(completed)
    done, _ = await asyncio.wait({task}, timeout=seconds)
    if done and time.monotonic() < deadline.end:
        result = task.result()
        if method == "newCDPSession":
            result = from_channel(result)
            if not state.retain(result, acquisition_context):
                raise Error("owned_browser_context_closed")
        return result
    if method == "newCDPSession":
        # Do not cancel an acquisition: abort can discard a real late session.
        def late_acquire(done):
            try:
                session = from_channel(done.result())
            except (Exception, asyncio.CancelledError):
                return
            if not state.retain(session, acquisition_context):
                return
            _queue_detach(state, session)

        task.add_done_callback(late_acquire)
    # Keep the single raw read task until its response/connection close. Actively
    # cancelling it enters Playwright's unbounded abort wait and a second stop
    # cancellation can leave its protocol future unconsumed. No proof continues.
    raise Error("owned_browser_read_timeout")


async def _late_detach(state, session):
    try:
        await _operation(
            state,
            session._channel,
            "detach",
            None,
            Deadline(1),
            cleanup=True,
            cleanup_resource=session,
        )
    except Exception:
        if id(session) in state.resources:
            state.failed_resources.add(id(session))
        return
    state.released(session)


def _queue_detach(state, session):
    if state.closed or id(session) not in state.resources:
        return
    task = session._connection._loop.create_task(_late_detach(state, session))
    state.background.add(task)

    def cleaned(finished):
        state.background.discard(finished)
        _consume(finished)

    task.add_done_callback(cleaned)


class OwnedCDP:
    def __init__(self, page, *, seconds=5, cleanup_seconds=1):
        self.page = page
        self.deadline = Deadline(seconds)
        self.cleanup_seconds = cleanup_seconds
        self.state = _state(page)
        self.session = None

    def _call(self, channel, method, params=None, *, cleanup=False):
        deadline = Deadline(self.cleanup_seconds) if cleanup else self.deadline
        result = None
        try:
            with _safe_alarm(deadline):
                result = self.page._sync(
                    _operation(
                        self.state,
                        channel,
                        method,
                        params,
                        deadline,
                        cleanup=cleanup,
                        acquisition_context=self.page.context._impl_obj,
                        cleanup_resource=self.session if cleanup else None,
                    )
                )
            return result
        except BaseException:
            if method == "newCDPSession" and result is not None:
                # The safe caller-side alarm check may expire after acquisition.
                # Ownership is already registered; queue only its exact cleanup.
                _queue_detach(self.state, result)
            raise

    def __enter__(self):
        self.session = self._call(
            self.page.context._impl_obj._channel,
            "newCDPSession",
            {"page": self.page._impl_obj._channel},
        )
        return self

    def send(self, method, params=None):
        if method not in READ_METHODS:
            raise ValueError("Unsupported original-Page read")
        arguments = {"method": method}
        if params is not None:
            arguments["params"] = params
        return self._call(self.session._channel, "send", arguments)

    def detach(self):
        parents = _ACTIVE_DEADLINE.get() or ()
        if parents and time.monotonic() >= parents[-1].end:
            # Retain/queue exact cleanup without extending the exhausted caller.
            _queue_detach(self.state, self.session)
            raise Error("owned_browser_outer_timeout")
        try:
            self._call(self.session._channel, "detach", cleanup=True)
        except BaseException:
            if id(self.session) in self.state.resources:
                self.state.failed_resources.add(id(self.session))
            raise
        self.state.released(self.session)

    def __exit__(self, *_error):
        self.detach()


async def _public_read(state, coroutine, deadline):
    """Internal wait shared only by the two fixed public reads below."""
    try:
        seconds = deadline.remaining() / 1000
    except BaseException:
        coroutine.close()
        raise
    task = asyncio.create_task(coroutine)
    state.pending.add(task)

    def completed(done):
        state.pending.discard(done)
        _consume(done)

    task.add_done_callback(completed)
    done, _ = await asyncio.wait({task}, timeout=seconds)
    if done and time.monotonic() < deadline.end:
        return task.result()
    raise Error("owned_browser_read_timeout")


def screenshot(page, deadline):
    state = _state(page)
    if state.closed or state.pending or state.background or state.failed_resources:
        raise Error("owned_browser_read_pending")
    with _safe_alarm(deadline):
        return page._sync(
            _public_read(
                state,
                page._impl_obj.screenshot(
                    type="png",
                    timeout=2000,
                    animations="allow",
                    caret="initial",
                    scale="css",
                ),
                deadline,
            )
        )


def pump_events(context, milliseconds):
    # Public event waiting has its own local timer. Keep a positive budget and
    # allow it while a read is pending so revocation/close can still progress.
    deadline = Deadline(milliseconds / 1000 + 0.1)
    with _safe_alarm(deadline):
        return context._sync(
            _public_read(
                _state(context),
                context._impl_obj.wait_for_event(
                    "close", timeout=min(milliseconds, deadline.remaining())
                ),
                deadline,
            )
        )
