"""Synthetic scheduling contracts through the worker's public tick/pump loop."""

import json
import os
import time
from pathlib import Path

import pytest
from test_generic_worker import FIELDS, native_form
from worker_preview_support import advance_until


def record_metrics(name, **facts):
    destination = os.environ.get("TS_WAIT_SCHEDULE_REPORT_DIR")
    if destination:
        path = Path(destination)
        path.mkdir(parents=True, exist_ok=True)
        (path / f"{name}.json").write_text(json.dumps(facts, indent=2) + "\n")


@pytest.mark.worker_browser
def test_verified_field_progress_yields_events_without_a_fixed_idle_wait(tmp_path, monkeypatch):
    with native_form(tmp_path, monkeypatch, FIELDS) as (service, runner, job, posts):
        advance_until(
            service,
            runner,
            lambda row: any(
                o.get("action") == "fill" and o.get("verified") for o in row["observations"]
            ),
        )
        current = service.store.load()["jobs"][0]
        assert any(o.get("action") == "fill" and o.get("verified") for o in current["observations"])
        began = time.monotonic()
        runner.pump()
        assert time.monotonic() - began < 0.15
        assert posts == []
        assert current["intent"] is None
        advance_until(
            service,
            runner,
            lambda row: (
                sum(
                    o.get("action") == "fill" and bool(o.get("verified"))
                    for o in row["observations"]
                )
                == 2
            ),
        )
        began = time.monotonic()
        runner.pump()
        assert time.monotonic() - began < 0.15


@pytest.mark.worker_browser
def test_opening_a_page_then_waiting_for_required_input_uses_idle_budget(tmp_path, monkeypatch):
    html = (
        FIELDS.replace(
            "name='person' required", "name='person' required value='Synthetic Person'"
        ).replace(
            "type='email' required", "type='email' required value='synthetic@example.invalid'"
        )
        + "<label>Unknown required answer *<input required></label>"
    )
    with native_form(tmp_path, monkeypatch, html) as (service, runner, job, posts):
        advance_until(service, runner, lambda row: row["status"] == "needs_input")
        assert service.store.load()["jobs"][0]["status"] == "needs_input", service.store.load()[
            "jobs"
        ][0]["reason"]
        began = time.monotonic()
        runner.pump()
        assert 0.2 <= time.monotonic() - began < 1
        assert posts == []


@pytest.mark.worker_browser
@pytest.mark.parametrize("command", ["pause", "cancel"])
def test_control_received_between_ticks_stops_without_another_field(tmp_path, monkeypatch, command):
    with native_form(tmp_path, monkeypatch, FIELDS) as (service, runner, job, posts):
        advance_until(
            service,
            runner,
            lambda row: any(
                o.get("action") == "fill" and o.get("verified") for o in row["observations"]
            ),
        )
        before = service.store.load()["jobs"][0]["observations"]
        service.request(command, {"controller": "synthetic-controller"})
        began = time.monotonic()
        runner.pump()
        runner.tick()
        state = service.store.load()
        stop_response = time.monotonic() - began
        assert stop_response < 0.5
        assert state["control"] == ("paused" if command == "pause" else "cancelled")
        assert len(
            [o for o in state["jobs"][0]["observations"] if o.get("action") == "fill"]
        ) == len([o for o in before if o.get("action") == "fill"])
        began = time.monotonic()
        runner.pump()
        assert 0.2 <= time.monotonic() - began < 1
        assert posts == []
        record_metrics(command, stop_response_ms=stop_response * 1000, no_extra_fill=True)


@pytest.mark.worker_browser
def test_page_event_queued_between_ticks_is_observed_before_another_fill(tmp_path, monkeypatch):
    with native_form(tmp_path, monkeypatch, FIELDS) as (service, runner, job, posts):
        advance_until(
            service,
            runner,
            lambda row: any(
                o.get("action") == "fill" and o.get("verified") for o in row["observations"]
            ),
        )
        page = runner.pages[job["application_id"]]

        def close_on_request(route):
            route.abort()
            page.close()

        page.route("**/close-between-ticks", close_on_request)
        page.evaluate("setTimeout(() => fetch('/close-between-ticks'), 20)")
        # Model the external tick gap. Production must dispatch the pending event.
        time.sleep(0.05)
        runner.pump()
        runner.tick()
        current = service.store.load()["jobs"][0]
        assert current["status"] == "needs_recheck"
        assert current["reason"] in {"page_closed", "page_lost"}
        assert len([o for o in current["observations"] if o.get("action") == "fill"]) == 1
        assert posts == []


@pytest.mark.worker_browser
def test_pending_forbidden_request_is_dispatched_and_blocked_during_busy_pump(
    tmp_path, monkeypatch
):
    with native_form(tmp_path, monkeypatch, FIELDS) as (service, runner, job, posts):
        advance_until(
            service,
            runner,
            lambda row: any(
                o.get("action") == "fill" and o.get("verified") for o in row["observations"]
            ),
        )
        page = runner.pages[job["application_id"]]
        page.evaluate("setTimeout(() => fetch('/submit', {method:'POST'}).catch(() => {}), 0)")
        runner.pump()
        runner.tick()
        current = service.store.load()["jobs"][0]
        assert current["status"] == "needs_recheck"
        assert current["reason"] == "unverified_send_path"
        assert len([o for o in current["observations"] if o.get("action") == "fill"]) == 1
        assert posts == []


@pytest.mark.worker_browser
@pytest.mark.parametrize("close", ["context", "browser"])
def test_closed_transport_returns_to_bounded_fault_idle(tmp_path, monkeypatch, close):
    with native_form(tmp_path, monkeypatch, FIELDS) as (service, runner, job, posts):
        advance_until(
            service,
            runner,
            lambda row: any(
                o.get("action") == "fill" and o.get("verified") for o in row["observations"]
            ),
        )
        if close == "context":
            runner.context.close()
        else:
            runner.context.browser.close()
        began = time.monotonic()
        runner.pump()
        runner.tick()
        current = service.store.load()
        assert current["control"] == "paused"
        assert current["jobs"][0]["status"] == "needs_recheck"
        assert (
            len([o for o in current["jobs"][0]["observations"] if o.get("action") == "fill"]) == 1
        )
        assert 0.2 <= time.monotonic() - began < 1
        assert posts == []


@pytest.mark.worker_browser
@pytest.mark.parametrize("heartbeat_age", [86400, -10])
def test_ui_heartbeat_age_does_not_interrupt_verified_field_progress(
    tmp_path, monkeypatch, heartbeat_age
):
    with native_form(tmp_path, monkeypatch, FIELDS) as (service, runner, job, posts):
        advance_until(
            service,
            runner,
            lambda row: any(
                o.get("action") == "fill" and o.get("verified") for o in row["observations"]
            ),
        )
        state = service.store.load()
        state["heartbeat_at"] = time.time() - heartbeat_age
        service.store.save(state)
        runner.pump()
        advance_until(
            service,
            runner,
            lambda row: (
                sum(
                    o.get("action") == "fill" and bool(o.get("verified"))
                    for o in row["observations"]
                )
                == 2
            ),
        )
        current = service.store.load()
        assert current["control"] == "running"
        assert current["worker_error"] == ""
        assert (
            len([o for o in current["jobs"][0]["observations"] if o.get("action") == "fill"]) == 2
        )
        service.request("pause", {"controller": "synthetic-controller"})
        service.request("heartbeat", {"controller": "synthetic-controller"})
        runner.tick()
        assert service.store.load()["control"] == "paused"
        assert posts == []
