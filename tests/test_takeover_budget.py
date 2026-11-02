"""The takeover deadline budget: baseline-derived values and cross-layer invariants."""

from __future__ import annotations

from dataclasses import replace

import pytest

from career_evidence_graph.application_takeover_budget import (
    CURRENT_DRIVER_ADMISSION_TTL,
    DEFAULT_BUDGET,
    MEASURED,
    PLANNED,
    TakeoverBudget,
)

# The batch-0 baseline table (worker.log P95, 2026-11-02); stop, thread/start and
# startup had no samples.
BASELINE = {
    "thread_start": {"n": 0, "p95": None},
    "admission_wait": {"n": 16, "p95": 11.38},
    "status_poll": {"n": 80, "p95": 5.88},
    "page_read": {"n": 43, "p95": 2.02},
    "stop_confirm": {"n": 0, "p95": None},
}


def test_default_budget_is_twice_the_measured_p95_and_planned_elsewhere():
    budget = TakeoverBudget.from_baseline(BASELINE)
    assert budget == DEFAULT_BUDGET
    assert (budget.admission, budget.status_poll, budget.scope_window) == (23.0, 12.0, 6.0)
    assert (budget.stop, budget.thread_start, budget.startup) == (10.0, 45.0, 30.0)
    assert MEASURED.isdisjoint(PLANNED)
    assert TakeoverBudget.from_dict(budget.to_dict()) == budget


def test_default_budget_fits_the_installed_driver_admission_time():
    """Until the driver reads its admission time, one poll plus admit fits its 15 s."""
    assert DEFAULT_BUDGET.driver_admission_ttl == CURRENT_DRIVER_ADMISSION_TTL == 15
    assert DEFAULT_BUDGET.status_poll + DEFAULT_BUDGET.admit <= 15
    # The old status poll (the client's whole 15 s) left no time to admit at all.
    with pytest.raises(ValueError, match="admission"):
        replace(DEFAULT_BUDGET, status_poll=15.0)


@pytest.mark.parametrize(
    ("change", "message"),
    [
        ({"stop": 30.0}, "control deadline exceeds the driver action bound"),
        ({"status_poll": 16.0}, "control deadline exceeds the driver action bound"),
        ({"admission": 10.0}, "admission"),
        ({"tool_call": 30.0}, "Codex abandons a tool call"),
        ({"startup": 45.0}, "thread/start ends before"),
        ({"request": 31.0}, "outlasts the startup bound"),
        ({"driver_timeout": 121.0, "tool_call": 200.0}, "client's limit"),
        ({"scope_window": 0}, "finite and positive"),
        ({"admit": float("nan")}, "finite and positive"),
    ],
)
def test_inconsistent_budget_is_refused_at_construction(change, message):
    with pytest.raises(ValueError, match=message):
        replace(DEFAULT_BUDGET, **change)


def test_a_rebuilt_driver_admission_time_lets_a_longer_status_read_fit():
    budget = replace(DEFAULT_BUDGET, driver_admission_ttl=23.0, status_poll=15.0, admit=5.0)
    assert budget.status_poll + budget.admit <= budget.admission


def test_budget_checks_the_real_driver_action_bound():
    assert DEFAULT_BUDGET.fits_driver(15)
    assert not DEFAULT_BUDGET.fits_driver(11.9)
    assert not DEFAULT_BUDGET.fits_driver(float("inf"))


@pytest.mark.parametrize(
    "record",
    [
        None,
        {},
        DEFAULT_BUDGET.to_dict() | {"protocol": "other"},
        DEFAULT_BUDGET.to_dict() | {"extra": 1},
        DEFAULT_BUDGET.to_dict() | {"stop": 99},
    ],
)
def test_saved_budget_record_must_be_one_consistent_budget(record):
    with pytest.raises((TypeError, ValueError)):
        TakeoverBudget.from_dict(record)
