"""App exit stops the whole chain: backend -> worker -> driver daemon and Chrome."""

import json
import os
import select
import signal
import subprocess
import sys
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace

import pytest
from test_application_worker import service as _service

from career_evidence_graph import cua_driver

service = _service
SERVER = Path(__file__).parents[1] / "macos/server.py"
BACKEND = """
import json, runpy, subprocess, sys
from http.server import BaseHTTPRequestHandler, HTTPServer
from career_evidence_graph.application_worker import WorkerService
module = runpy.run_path(sys.argv[1])
serve = module["serve_with_parent_pipe"]
serve.__globals__["WORKER_STOP_SECONDS"] = 1
child = (
    "import signal, sys, time\\n"
    + ("signal.signal(signal.SIGTERM, signal.SIG_IGN)\\n" if sys.argv[2] == "ignore" else "")
    + "print(json.dumps({'event': 'child_ready'}), flush=True)\\n"
    + "time.sleep(60)\\n"
)
class Worker:
    _backend_closed = False
    stop_process = WorkerService.stop_process
worker = Worker()
worker.process = subprocess.Popen(
    [sys.executable, "-c", "import json\\n" + child], start_new_session=True
)
server = HTTPServer(("127.0.0.1", 0), BaseHTTPRequestHandler)
server.worker_service = worker
def record(event, **values):
    print(json.dumps({"event": event, **{k: v for k, v in values.items() if v is not None}}),
          flush=True)
serve(server, None, {"event": "ready", "worker": worker.process.pid}, record_event=record)
print(json.dumps({"event": "closed", "spawn_refused": worker._backend_closed}), flush=True)
"""


def alive(pid):
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    return True


@pytest.mark.parametrize(
    ("trigger", "child"), [("parent_pipe_eof", "default"), ("sigterm", "ignore")]
)
def test_backend_stop_terminates_its_worker_and_escalates_when_ignored(trigger, child):
    process = subprocess.Popen(
        [sys.executable, "-c", BACKEND, str(SERVER), child],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        text=True,
    )
    events, worker = [], None
    try:
        while "child_ready" not in events or worker is None:
            assert select.select([process.stdout], [], [], 10)[0], events
            row = json.loads(process.stdout.readline())
            events.append(row["event"])
            worker = row.get("worker", worker)
        if trigger == "sigterm":
            process.send_signal(signal.SIGTERM)
        else:
            process.stdin.close()
        output, _ = process.communicate(timeout=20)
    finally:
        if process.poll() is None:
            process.kill()
    events += [json.loads(line)["event"] for line in output.splitlines()]
    assert process.returncode == 0
    expected = ["backend_shutdown_requested", "worker_terminate_requested"]
    if child == "ignore":
        expected.append("worker_kill_requested")
    expected += ["worker_exit_confirmed", "backend_shutdown_complete", "closed"]
    assert [event for event in events if event in expected] == expected
    assert not alive(worker)


def test_stop_process_without_a_running_worker_only_fences_spawn():
    from career_evidence_graph.application_worker import WorkerService

    events = []
    stand_in = SimpleNamespace(_backend_closed=False, process=None)
    WorkerService.stop_process(stand_in, events.append)
    assert stand_in._backend_closed and events == []


def run_worker(service, monkeypatch, tmp_path, call):
    from career_evidence_graph import application_worker_browser as browser

    cleanup = []
    context = SimpleNamespace(pages=[], set_default_timeout=lambda _value: None)

    @contextmanager
    def playwright():
        yield SimpleNamespace()

    @contextmanager
    def session(_playwright, _runtime, **_kwargs):
        try:
            yield context, SimpleNamespace()
        finally:
            # Stands in for managed_cua_browser closing its driver and Chrome.
            cleanup.append("driver_and_chrome_closed")

    class Runner:
        def __init__(self, store, received_context, origin, *, cua):
            self.context = received_context

        tick = staticmethod(call)

        def event(self, kind):
            pass

        def pump(self):
            pass

    monkeypatch.setattr(browser, "sync_playwright", playwright)
    monkeypatch.setattr(browser, "managed_cua_browser", session)
    monkeypatch.setattr(browser, "ApplicationRunner", Runner)
    monkeypatch.setattr(browser, "sync_login_state", lambda _root, _context, seen: seen)
    monkeypatch.setattr(browser, "STOP_GRACE_SECONDS", 0.2)
    monkeypatch.setattr(browser, "PARENT_POLL_SECONDS", 0.02)
    runtime_root = tmp_path / "runtime"
    arguments = [
        "--applications",
        str(service.store.applications.root),
        "--runtime",
        str(runtime_root),
        "--live",
        "--cua",
    ]
    handler = signal.getsignal(signal.SIGTERM)
    result = browser.main(arguments)
    assert signal.getsignal(signal.SIGTERM) == handler
    state = browser.WorkerStore(service.store.applications, runtime_root, live=True).load()
    return result, state, cleanup


def test_worker_term_interrupts_a_stuck_call_and_still_closes_the_browser_session(
    service, monkeypatch, tmp_path
):
    def tick():
        signal.getsignal(signal.SIGTERM)(signal.SIGTERM, None)
        # A call that never checks the stop request, like the busy wait after a dead driver.
        until = time.monotonic() + 5
        while time.monotonic() < until:
            time.sleep(0.01)
        pytest.fail("the stop request did not leave the stuck call")

    started = time.monotonic()
    result, state, cleanup = run_worker(service, monkeypatch, tmp_path, tick)
    assert time.monotonic() - started < 3
    assert result == 2
    assert state["control"] == "paused" and state["worker_error"] == "KeyboardInterrupt"
    assert cleanup == ["driver_and_chrome_closed"]


def test_worker_stops_itself_when_its_parent_disappears(service, monkeypatch, tmp_path):
    orphaned, ticks = threading.Event(), []
    real_parent = os.getppid
    monkeypatch.setattr(os, "getppid", lambda: 1 if orphaned.is_set() else real_parent())

    def tick():
        ticks.append(1)
        orphaned.set()
        assert len(ticks) < 500, "the orphaned worker kept running"
        time.sleep(0.01)

    result, state, cleanup = run_worker(service, monkeypatch, tmp_path, tick)
    assert result is None
    assert state["control"] == "paused" and state["worker_error"] == "worker_stopped"
    assert cleanup == ["driver_and_chrome_closed"]


def synthetic_process(tmp_path, *, ignore_term=False):
    process = subprocess.Popen(
        [
            sys.executable,
            "-c",
            (
                "import signal\nsignal.signal(signal.SIGTERM, signal.SIG_IGN)\n"
                if ignore_term
                else ""
            )
            + "import time\nprint('ready', flush=True)\ntime.sleep(60)\n",
        ],
        stdout=subprocess.PIPE,
        text=True,
    )
    assert process.stdout.readline() == "ready\n"
    # Reap promptly so a finished stand-in is not seen as a live zombie.
    threading.Thread(target=process.wait, daemon=True).start()
    return process


@pytest.mark.parametrize("ignore_term", [False, True])
def test_owned_session_failure_still_stops_the_chrome_its_dead_driver_launched(
    tmp_path, monkeypatch, ignore_term
):
    chrome = synthetic_process(tmp_path, ignore_term=ignore_term)
    profile = tmp_path / "cua-profiles" / "isolated-synthetic"
    record = {"click_route": "dom_event"}

    class Client:
        session = "synthetic-owner"
        failed = True

        def call(self, name, arguments, **kwargs):
            assert name == "browser_prepare"
            profile.mkdir()
            (profile / "SingletonLock").symlink_to(f"synthetic-{chrome.pid}")
            (profile / "DevToolsActivePort").write_text("9222\n/devtools/browser/synthetic\n")
            return {"action": "launched_isolated_browser", "prepared_pid": chrome.pid}

    @contextmanager
    def client(*args, **kwargs):
        # The driver is gone: it cannot close the Chrome it launched.
        yield Client(), {"source": {"pid": 7}}

    def app_state(pid, **kwargs):
        assert pid == chrome.pid
        state = {"pid": pid, "launch_date": 1, "hidden": True, "active": False}
        return {**state, "windows": []} if kwargs.get("windows") else state

    monkeypatch.setattr(cua_driver, "managed_cua_client", client)
    monkeypatch.setattr(cua_driver, "mac_chrome_state", app_state)
    # The loopback listener differs, so startup fails after the Chrome identity is known.
    monkeypatch.setattr(cua_driver.subprocess, "check_output", lambda *a, **k: "n127.0.0.1:1\n")
    try:
        with (
            pytest.raises(cua_driver.PortalDataError) as error,
            cua_driver.managed_owned_cua_browser(
                None, tmp_path, tmp_path / "unused-driver", {}, record, []
            ),
        ):
            pytest.fail("A mismatched listener must not enter the runtime")
        assert error.value.code == "cua_binding_ambiguous"
        until = time.monotonic() + 2
        while chrome.returncode is None and time.monotonic() < until:
            time.sleep(0.02)
        assert chrome.returncode == (-signal.SIGKILL if ignore_term else -signal.SIGTERM)
        saved = json.loads((tmp_path / "cua-runtime.json").read_text())
        assert saved["pid"] == chrome.pid and saved["closed"] is False
    finally:
        if chrome.poll() is None:
            chrome.kill()


def test_owned_chrome_stop_skips_a_reused_pid(tmp_path, monkeypatch):
    other = synthetic_process(tmp_path)

    def changed(pid, **kwargs):
        raise cua_driver.PortalDataError("cua_visibility_unknown", "synthetic", 409)

    monkeypatch.setattr(cua_driver, "mac_chrome_state", changed)
    try:
        with pytest.raises(cua_driver.PortalDataError):
            cua_driver.stop_owned_chrome(other.pid, 1)
        assert other.poll() is None
    finally:
        other.kill()


def test_driver_daemon_is_terminated_when_its_stop_command_fails(tmp_path, monkeypatch):
    script = tmp_path / "synthetic-driver.py"
    driver = tmp_path / "synthetic-driver"
    driver.write_text(f'#!/bin/sh\nexec "{sys.executable}" "{script}" "$@"\n')
    script.write_text(
        "import pathlib, sys, time\n"
        "socket = pathlib.Path(sys.argv[sys.argv.index('--socket') + 1])\n"
        "if sys.argv[1] == 'serve':\n"
        "    socket.touch()\n"
        "    time.sleep(60)\n"
        "sys.exit(1)\n"
    )
    driver.chmod(0o700)
    started = []
    original = cua_driver.subprocess.Popen

    def popen(*args, **kwargs):
        process = original(*args, **kwargs)
        started.append(process)
        return process

    class Client:
        def __init__(self, *args, **kwargs):
            pass

        def call(self, name, arguments, **kwargs):
            return {"accessibility": False}

        def close(self):
            pass

    monkeypatch.setattr(cua_driver.subprocess, "Popen", popen)
    monkeypatch.setattr(cua_driver, "CuaMcpClient", Client)
    socket = str(tmp_path / "driver.sock")
    with (
        open(tmp_path / "cua.log", "w") as log,
        pytest.raises(cua_driver.PortalDataError) as error,
        cua_driver.managed_cua_client(driver, socket, {}, log, dict(os.environ), embedded=True),
    ):
        pytest.fail("A driver without permissions must not be used")
    assert error.value.code == "cua_cleanup_unknown"
    assert started[0].args[1] == "serve"
    assert all(process.poll() is not None for process in started)
