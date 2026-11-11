"""The browser test driver must not turn a wait into permission to retry."""

from copy import deepcopy
from types import SimpleNamespace

import pytest
from worker_preview_support import advance_until


def driver(jobs):
    state = {"control": "running", "controller": "original", "heartbeat_at": 1, "jobs": jobs}
    calls = []

    def tick():
        calls.append("tick")
        jobs[-1].update(status="ready_for_review", reason="")

    service = SimpleNamespace(store=SimpleNamespace(load=lambda: deepcopy(state)))
    runner = SimpleNamespace(pages={}, tick=tick, pump=lambda: calls.append("pump"))
    return service, runner, state, calls


def test_unknown_job_stops_without_another_tick_or_control_change():
    job = {
        "application_id": "blocked",
        "status": "needs_recheck",
        "reason": "action_result_unknown",
        "intent": {"attempt_id": "retained"},
    }
    service, runner, state, calls = driver([job])
    before = deepcopy(state)
    with pytest.raises(pytest.fail.Exception, match="different stop"):
        advance_until(service, runner, lambda row: row["status"] == "ready_for_review")
    assert calls == [] and state == before


def test_expected_unknown_is_read_without_advancing_it():
    job = {"application_id": "blocked", "status": "needs_recheck", "reason": "unknown"}
    service, runner, state, calls = driver([job])
    before = deepcopy(state)
    assert advance_until(service, runner, lambda row: row["status"] == "needs_recheck") == job
    assert calls == [] and state == before


def test_wait_only_observes_the_explicit_job_and_preserves_controller():
    blocked = {"application_id": "blocked", "status": "needs_recheck", "reason": "unknown"}
    target = {"application_id": "target", "status": "queued", "reason": ""}
    service, runner, state, calls = driver([blocked, target])
    before = deepcopy(blocked)
    result = advance_until(
        service,
        runner,
        lambda row: row["status"] == "ready_for_review",
        application_id="target",
    )
    assert result["application_id"] == "target" and calls == ["tick", "pump"]
    assert state | {"jobs": []} == {
        "control": "running",
        "controller": "original",
        "heartbeat_at": 1,
        "jobs": [],
    }
    assert blocked == before
