"""Repeat native crash injection with the original deadlines and assertions."""

import os
import signal
import subprocess
import time
from contextlib import suppress
from threading import Timer

import pytest
from test_application_worker import service as _service
from test_worker_recovery_regressions import report
from test_worker_stability import inject_native_crash as _inject_crash
from test_worker_stability import native_runner as _native_runner
from test_worker_stability import test_native_page_crash_isolated as _existing_crash

service = _service
native_runner = _native_runner


@pytest.mark.worker_browser
@pytest.mark.parametrize("during_action", [False, True])
@pytest.mark.parametrize("trial", range(2))
def test_direct_crash_keeps_original_timing_and_isolation(
    native_runner, monkeypatch, during_action, trial
):
    worker, runner, _context = native_runner
    page = runner.pages[worker.store.load()["jobs"][0]["application_id"]]
    began = time.monotonic()
    events = []
    page.on("crash", lambda: events.append(time.monotonic() - began))
    outcome = "passed"
    try:
        _existing_crash(native_runner, monkeypatch, during_action)
    except BaseException as error:
        outcome = type(error).__name__ + ": " + str(error)
        raise
    finally:
        report(
            f"direct-crash-{trial}-{during_action}",
            {
                "outcome": outcome,
                "event_seconds": events,
                "original_event_deadline_ms": 1500,
                "original_diagnosis_deadline_seconds": 2,
                "injection_command_deadline_seconds": 1,
                "job": worker.store.load()["jobs"][0],
                "real_ats_calls": 0,
            },
        )


@pytest.mark.worker_browser
def test_renderer_exit_after_short_pause_keeps_original_deadlines(tmp_path, monkeypatch):
    from playwright.sync_api import Error, sync_playwright

    monkeypatch.setenv("PLAYWRIGHT_BROWSERS_PATH", "0")
    with sync_playwright() as pw:
        profile = tmp_path / "profile"
        context = pw.chromium.launch_persistent_context(str(profile), headless=True)
        page = context.pages[0]
        page.set_content("<p>Synthetic renderer deadline regression</p>")
        session = context.browser.new_browser_cdp_session()
        processes = session.send("SystemInfo.getProcessInfo")["processInfo"]
        renderers = [int(row["id"]) for row in processes if row["type"] == "renderer"]
        assert len(renderers) == 1
        pid = renderers[0]

        def identity():
            result = subprocess.run(
                ["ps", "-p", str(pid), "-o", "pid=,ppid=,lstart="],
                capture_output=True,
                text=True,
                check=False,
            )
            return result.stdout.strip() if result.returncode == 0 else ""

        bound = identity()
        assert bound and int(bound.split()[0]) == pid
        owner = int(bound.split()[1])
        args = subprocess.check_output(["ps", "-p", str(owner), "-o", "args="], text=True)
        assert "--user-data-dir=" + str(profile) in args

        def resume():
            if identity() == bound:
                with suppress(ProcessLookupError):
                    os.kill(pid, signal.SIGCONT)

        events, began, outcome = [], time.monotonic(), "passed"
        page.on("crash", lambda: events.append(time.monotonic() - began))
        assert identity() == bound
        os.kill(pid, signal.SIGSTOP)
        timer = Timer(1.25, resume)
        timer.start()
        try:
            with page.expect_event("crash", timeout=1500), pytest.raises(Error):
                _inject_crash(page)
            assert events and events[-1] < 1.5
            assert time.monotonic() - began < 2
            assert not page.is_closed()
        except BaseException as error:
            outcome = type(error).__name__ + ": " + str(error)
            raise
        finally:
            timer.join(timeout=3)
            resume()
            report(
                "native-short-pause-deadline",
                {
                    "outcome": outcome,
                    "event_seconds": events,
                    "original_event_deadline_ms": 1500,
                    "original_diagnosis_deadline_seconds": 2,
                    "owned_renderer_pid": pid,
                    "owned_launch_identity": bound,
                    "bounded_renderer_stop_seconds": 1.25,
                    "real_ats_calls": 0,
                },
            )
            context.close()
