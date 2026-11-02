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
