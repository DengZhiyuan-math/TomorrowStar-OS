"""The original page's observation window: one freshness rule and one timestamp writer.

A takeover may read or act on the original page only while the Worker's own
observation of it is recent: the run's ``runtime.observed_at`` and the job's
``page_observation.at``. Every check reads them through `PageScope.current`, and
every write goes through `PageScope.refresh`, which the page thread calls before and
after each read that may take more than a second. A captured snapshot of the page
carries its own capture time; `PageScope.renew_snapshot` lets it follow the
observation a later check renewed, so the snapshot has no second freshness clock.
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass

from .application_takeover_budget import DEFAULT_BUDGET

# A refresh is due once an observation is this old; cheaper checks skip the save.
REFRESH_AFTER = 1.0


@dataclass(frozen=True)
class ScopeCheck:
    valid: bool
    # The first part that is no longer current, or None.
    changed: str | None
    runtime_age: float | None
    page_age: float | None


def _finite(value):
    return type(value) in (int, float) and math.isfinite(value)


def _age(now, at):
    if not _finite(at):
        return None
    return now - at


@dataclass(frozen=True)
class PageScope:
    """How old the original-page observation may be; the window comes from the budget."""

    window: float = DEFAULT_BUDGET.scope_window

    def current(self, state, job, now=None) -> ScopeCheck:
        """Whether the run and page observations are both recent, and which one is not."""
        now = time.time() if now is None else now
        runtime_age = _age(now, (state.get("runtime") or {}).get("observed_at"))
        page_age = _age(now, ((job or {}).get("page_observation") or {}).get("at"))
        for name, age in (("runtime_observation", runtime_age), ("page_observation", page_age)):
            if age is None:
                return ScopeCheck(False, name, runtime_age, page_age)
            if age < 0:
                return ScopeCheck(False, "clock", runtime_age, page_age)
            if age >= self.window:
                return ScopeCheck(False, name, runtime_age, page_age)
        return ScopeCheck(True, None, runtime_age, page_age)

    def runtime_current(self, state, now=None):
        now = time.time() if now is None else now
        age = _age(now, (state.get("runtime") or {}).get("observed_at"))
        return age is not None and 0 <= age < self.window

    def page_current(self, job, now=None):
        now = time.time() if now is None else now
        age = _age(now, ((job or {}).get("page_observation") or {}).get("at"))
        return age is not None and 0 <= age < self.window

    @staticmethod
    def refresh(state, job=None, now=None, *, run_id=None):
        """The one writer of both observation times; True when anything changed.

        Only the page thread that holds the original page calls it, for its own run;
        a page observation of another run is never renewed.
        """
        now = time.time() if now is None else now
        runtime = state.get("runtime")
        if not runtime or run_id is not None and runtime.get("id") != run_id:
            return False
        changed = False
        if runtime.get("observed_at") != now:
            runtime["observed_at"] = now
            changed = True
        page = (job or {}).get("page_observation")
        if page and page.get("run_id") == runtime.get("id") and page.get("at") != now:
            page["at"] = now
            changed = True
        return changed

    @staticmethod
    def renew_snapshot(snapshot, state, job, *, run_id) -> bool:
        """Carry the page observation a check just renewed into a captured snapshot.

        A snapshot's ``at``/``observed_at`` are its capture time, but the driver
        status read and the event pump between a capture and its delivery outlast
        the window (status poll P95 5.9 s, tick P95 1.2 s; real run 2026-11-02). The
        page thread calls this right after a pump that re-read the original frame
        against the snapshot's document, so the snapshot follows that observation:
        never an older one, another run's, or another page's.
        """
        runtime = state.get("runtime") or {}
        page = (job or {}).get("page_observation") or {}
        at = page.get("at")
        if (
            not isinstance(snapshot, dict)
            or snapshot.get("status") != "captured"
            or run_id is None
            or runtime.get("id") != run_id
            or page.get("run_id") != run_id
            or page.get("page_id") != (snapshot.get("binding") or {}).get("page_id")
            or not _finite(at)
            or not _finite(snapshot.get("at"))
            or at < snapshot["at"]
        ):
            return False
        if snapshot["at"] == at and snapshot.get("observed_at") == at:
            return False
        snapshot["at"] = snapshot["observed_at"] = at
        return True

    @staticmethod
    def refresh_due(state, job, now=None):
        now = time.time() if now is None else now
        ages = (
            _age(now, (state.get("runtime") or {}).get("observed_at")),
            _age(now, ((job or {}).get("page_observation") or {}).get("at")),
        )
        return any(age is None or not 0 <= age < REFRESH_AFTER for age in ages)


PAGE_SCOPE = PageScope()
