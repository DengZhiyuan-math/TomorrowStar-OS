"""Test-only channel facade for existing synchronous synthetic Page fixtures.

The production bridge never falls back to public unbounded CDP methods. This
facade keeps the fixtures' existing semantic hooks while exposing the locked
channel contract. Delayed responses are cooperative, as a real protocol wait is.
"""

import asyncio
from types import SimpleNamespace

from playwright.sync_api import TimeoutError


class OwnedCDPFake:
    def __init__(self, page):
        self.page = page
        self.loop = asyncio.new_event_loop()
        self.delays = {}
        self.handlers = {}
        self.context_handlers = {}
        self.closed = False
        self.connection = SimpleNamespace(on=self.on, _loop=self.loop)
        page_impl = SimpleNamespace(_connection=self.connection)
        context_impl = SimpleNamespace(
            _connection=self.connection,
            is_closed=lambda: self.closed,
            once=lambda name, callback: self.context_handlers.setdefault(name, []).append(callback),
        )
        page_impl._channel = SimpleNamespace(_object=page_impl)
        context_impl._channel = self.Channel(self, context_impl)
        page_impl.screenshot = self.screenshot
        context_impl.wait_for_event = self.wait_for_event
        page._impl_obj = page_impl
        page.context._impl_obj = context_impl
        page._sync = self.loop.run_until_complete
        page.context._sync = self.loop.run_until_complete
        page._cdp_test_wire = self

    def on(self, name, callback):
        self.handlers.setdefault(name, []).append(callback)

    class Channel:
        def __init__(self, wire, owner, session=None):
            self.wire = wire
            self._object = owner
            self.session = session
            self.handlers = {}

        async def send(self, method, timeout, params=None):
            assert timeout(None) > 0
            operation = params["method"] if method == "send" else method
            await asyncio.sleep(self.wire.delays.get(operation, 0))
            if method == "newCDPSession":
                assert params == {"page": self.wire.page._impl_obj._channel}
                session = self.wire.page.context.new_cdp_session(self.wire.page)
                owner = SimpleNamespace(_connection=self.wire.connection, _was_collected=False)
                channel = type(self)(self.wire, owner, session)
                owner._channel = channel
                owner.once = lambda name, callback: channel.handlers.setdefault(name, []).append(
                    callback
                )
                return channel
            if method == "send":
                arguments = params.get("params")
                if arguments is None:
                    return self.session.send(operation)
                return self.session.send(operation, arguments)
            if method == "detach":
                result = self.session.detach()
                for callback in self.handlers.pop("close", ()):
                    callback()
                return result
            raise AssertionError(method)

    async def screenshot(self, **options):
        await asyncio.sleep(self.delays.get("screenshot", 0))
        return self.page.screenshot(**options)

    async def wait_for_event(self, event, *, timeout):
        assert event == "close" and timeout > 0
        await asyncio.sleep(timeout / 1000)
        raise TimeoutError("Synthetic close event timeout")

    def close(self):
        self.closed = True
        for callback in self.context_handlers.pop("close", ()):
            callback()
        for callback in self.handlers.get("close", ()):
            callback()
        tasks = asyncio.all_tasks(self.loop)
        for task in tasks:
            task.cancel()
        if tasks:
            self.loop.run_until_complete(asyncio.gather(*tasks, return_exceptions=True))
        self.loop.run_until_complete(asyncio.sleep(0))
        assert not asyncio.all_tasks(self.loop)
        self.loop.close()
