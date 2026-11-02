"""The original-page scope: one freshness rule, renewed around slow reads."""

from __future__ import annotations

import pytest

from career_evidence_graph.application_page_scope import PAGE_SCOPE, PageScope
from career_evidence_graph.application_takeover_budget import DEFAULT_BUDGET

# Batch-0 baseline: a page read P95 2.02 s, but the observation was 7.2-7.4 s old
# when checked; 10 of 24 real `assistance_binding_changed` were that age alone.
SLOW_CHECK = 7.4


def observed(at, *, run="run-1"):
    state = {"runtime": {"id": run, "observed_at": at}}
    job = {"page_observation": {"run_id": run, "page_id": "page", "at": at}}
    return state, job


def test_window_comes_from_the_budget():
    assert PAGE_SCOPE.window == DEFAULT_BUDGET.scope_window == 6.0


@pytest.mark.parametrize("window", [6.0, 15.0])
def test_a_slow_read_without_renewal_depends_on_the_window(window):
    state, job = observed(100.0)
    check = PageScope(window).current(state, job, 100.0 + SLOW_CHECK)
    assert check.valid is (window == 15.0)
    if not check.valid:
        assert check.changed == "runtime_observation"


@pytest.mark.parametrize("window", [6.0, 15.0])
def test_renewal_before_and_after_each_read_keeps_a_slow_read_current(window):
    scope = PageScope(window)
    state, job = observed(100.0)
    now = 100.0
    for read in (2.0, 2.0, 3.4):  # one check sequence of 7.4 s in total
        assert scope.current(state, job, now).valid
        scope.refresh(state, job, now, run_id="run-1")  # before the read
        now += read
        assert scope.current(state, job, now).valid
        scope.refresh(state, job, now, run_id="run-1")  # after the read
    assert now - 100.0 == pytest.approx(SLOW_CHECK)
    assert scope.current(state, job, now).valid


def test_each_part_reports_what_changed():
    state, job = observed(100.0)
    job["page_observation"]["at"] = 90.0
    assert PAGE_SCOPE.current(state, job, 101.0).changed == "page_observation"
    assert PAGE_SCOPE.current(state, job, 99.0).changed == "clock"
    assert PAGE_SCOPE.current({}, job, 101.0).changed == "runtime_observation"
    assert PAGE_SCOPE.current(state, {}, 101.0).changed == "page_observation"


def test_refresh_renews_only_this_run():
    state, job = observed(100.0)
    assert not PAGE_SCOPE.refresh(state, job, 105.0, run_id="another-run")
    assert state["runtime"]["observed_at"] == 100.0
    job["page_observation"]["run_id"] = "older-run"
    assert PAGE_SCOPE.refresh(state, job, 105.0, run_id="run-1")
    assert state["runtime"]["observed_at"] == 105.0
    assert job["page_observation"]["at"] == 100.0  # another run's page is never renewed


def test_refresh_is_due_only_after_a_second():
    state, job = observed(100.0)
    assert not PAGE_SCOPE.refresh_due(state, job, 100.5)
    assert PAGE_SCOPE.refresh_due(state, job, 101.5)


def captured(at, *, page="page"):
    return {"status": "captured", "at": at, "observed_at": at, "binding": {"page_id": page}}


def test_a_delivery_snapshot_follows_the_observation_its_pump_renewed():
    # Batch-0 baseline: the driver status read behind the native scope attestation
    # (P95 5.88 s) and the event pump's tick (P95 1.2 s) run between a capture and
    # its delivery check (real run 2026-11-02: "Original-page JSON context expired").
    state, job = observed(100.0)
    snapshot = captured(100.0)
    now = 100.0 + 5.9
    PAGE_SCOPE.refresh(state, job, now, run_id="run-1")  # the pump before delivery
    assert PAGE_SCOPE.renew_snapshot(snapshot, state, job, run_id="run-1")
    assert snapshot["at"] == snapshot["observed_at"] == job["page_observation"]["at"] == now
    assert not PAGE_SCOPE.renew_snapshot(snapshot, state, job, run_id="run-1")


@pytest.mark.parametrize(
    "change",
    ["another_run", "another_page", "not_captured", "older_observation", "no_observation"],
)
def test_a_snapshot_is_renewed_only_from_its_own_pages_later_observation(change):
    state, job = observed(105.0)
    snapshot = captured(100.0)
    if change == "another_run":
        job["page_observation"]["run_id"] = "older-run"
    elif change == "another_page":
        snapshot["binding"]["page_id"] = "other-page"
    elif change == "not_captured":
        snapshot["status"] = "unavailable"
    elif change == "older_observation":
        job["page_observation"]["at"] = 99.0
    elif change == "no_observation":
        job = {}
    assert not PAGE_SCOPE.renew_snapshot(snapshot, state, job, run_id="run-1")
    assert snapshot["at"] == snapshot["observed_at"] == 100.0
