"""One takeover's deadline budget: every layer's deadline derived from one checked value.

The Worker creates it when it dispatches a takeover and keeps it on the dispatch; the
Adapter, the driver's control requests and the original-page scope window read their
deadlines from it. Construction rejects a budget whose downstream deadlines do not fit
their upstream ones, so a mismatch is refused before a takeover starts, not found as a
runtime ``ValueError`` in the middle of one.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass, fields

TAKEOVER_BUDGET = "takeover-budget/v1"
# Measured on the real chain (batch 0 baseline, 2026-11-02, worker.log P95):
# admission wait 11.38 s, status poll 5.88 s, page read 2.02 s, page age 7.21 s.
# Each measured deadline is about twice its P95. Stop, thread/start and startup had
# no samples; theirs are planned values, kept until a real run measures them.
MEASURED = frozenset({"admission", "status_poll", "scope_window"})
PLANNED = frozenset({"stop", "thread_start", "startup"})
# The current signed driver holds a write for host admission for a fixed 15 s
# (HOST_ADMISSION_TTL in trusted_handoff.rs); a rebuilt driver reads `admission`.
CURRENT_DRIVER_ADMISSION_TTL = 23.0
CURRENT_DRIVER_GRANT_WAIT = 30.0
MAX_DRIVER_TIMEOUT = 120.0


@dataclass(frozen=True)
class TakeoverBudget:
    """Seconds per deadline; ``validate`` holds the cross-layer invariants."""

    # The driver holds a Codex write this long for the Worker's admission.
    admission: float = 23.0
    # One handoff_status control read while Codex holds control.
    status_poll: float = 12.0
    # One admit_call control request after the Worker's own checks.
    admit: float = 3.0
    # Each stop step: revoke, turn/interrupt, process and reader waits.
    stop: float = 10.0
    # Codex thread/start, which includes starting the takeover tool server.
    thread_start: float = 45.0
    # Codex's own startup bound for the takeover tool server (MCP startup_timeout_sec).
    startup: float = 30.0
    # Codex's bound for one takeover tool call (MCP tool_timeout_sec).
    tool_call: float = 60.0
    # Other app-server requests.
    request: float = 10.0
    # The native session's own action bound; every control deadline fits inside it.
    driver_timeout: float = 15.0
    # The admission time the installed driver actually gives a write.
    driver_admission_ttl: float = CURRENT_DRIVER_ADMISSION_TTL
    # How old the original-page observation may be when a takeover read is checked.
    # About twice the measured page age (P95 7.21 s): one admission's own decision
    # took 7 s (status poll and event pump), and the 6 s window revoked healthy
    # takeovers on BCG and Harmattan (2026-11-05). Document checks stay per read.
    scope_window: float = 14.0
    # How long the driver's embedded receiver waits for the host's grant after it
    # publishes the rendezvous (its pending TTL); the host's ready-to-yield chain
    # measured over the earlier 10 s wait (2026-11-02).
    grant_wait: float = CURRENT_DRIVER_GRANT_WAIT

    def __post_init__(self):
        self.validate()

    def validate(self):
        values = asdict(self)
        if any(
            type(value) not in (int, float) or not math.isfinite(value) or value <= 0
            for value in values.values()
        ):
            raise ValueError("Every takeover deadline must be finite and positive")
        problems = [
            message
            for broken, message in (
                (
                    self.driver_timeout > MAX_DRIVER_TIMEOUT,
                    "the driver action bound exceeds the client's limit",
                ),
                (
                    max(self.status_poll, self.admit, self.stop) > self.driver_timeout,
                    "a control deadline exceeds the driver action bound",
                ),
                (
                    self.status_poll + self.admit > min(self.admission, self.driver_admission_ttl),
                    "one status read and its admission do not fit the driver's admission time",
                ),
                (
                    self.grant_wait <= self.driver_timeout + self.scope_window,
                    "the receiver stops waiting before one yield call and its page check finish",
                ),
                (
                    self.tool_call < self.admission + self.driver_timeout,
                    "Codex abandons a tool call before admission and its action can finish",
                ),
                (
                    self.startup >= self.thread_start,
                    "thread/start ends before the tool server's own startup can fail",
                ),
                (
                    self.request > self.startup,
                    "an ordinary request outlasts the startup bound",
                ),
            )
            if broken
        ]
        if problems:
            raise ValueError("Inconsistent takeover budget: " + "; ".join(problems))

    def fits_driver(self, action_timeout):
        """True when the native session's real action bound is this budget's."""
        return (
            type(action_timeout) in (int, float)
            and math.isfinite(action_timeout)
            and action_timeout >= max(self.status_poll, self.admit, self.stop)
        )

    def to_dict(self):
        return {"protocol": TAKEOVER_BUDGET, **asdict(self)}

    @classmethod
    def from_dict(cls, value):
        names = {field.name for field in fields(cls)}
        if (
            not isinstance(value, dict)
            or value.get("protocol") != TAKEOVER_BUDGET
            or not set(value) - {"protocol"} <= names
        ):
            raise ValueError("Invalid takeover budget")
        # A dispatch saved before a deadline was declared keeps that deadline's
        # default; refusing it would refuse the whole in-flight job on an update
        # (2026-11-02: grant_wait).
        return cls(**{name: value[name] for name in names if name in value})

    @classmethod
    def from_baseline(cls, latency, **overrides):
        """Twice each measured P95 (whole seconds), where a sample exists; planned otherwise.

        ``latency`` is the baseline table (``{"admission_wait": {"p95": ...}, ...}``).
        """

        def doubled(name, default):
            p95 = (latency.get(name) or {}).get("p95")
            return (
                float(math.ceil(2 * p95)) if isinstance(p95, (int, float)) and p95 > 0 else default
            )

        defaults = cls.__dataclass_fields__
        page_read = (latency.get("page_read") or {}).get("p95")
        page_age = (latency.get("page_age") or {}).get("p95")
        values = {
            "admission": doubled("admission_wait", defaults["admission"].default),
            "status_poll": doubled("status_poll", defaults["status_poll"].default),
            "stop": doubled("stop_confirm", defaults["stop"].default),
            "thread_start": doubled("thread_start", defaults["thread_start"].default),
            "scope_window": min(
                max(
                    6.0,
                    2 * page_read if isinstance(page_read, (int, float)) else 0,
                    2 * page_age if isinstance(page_age, (int, float)) else 0,
                ),
                # The receiver must outwait one yield call and its page check.
                CURRENT_DRIVER_GRANT_WAIT - defaults["driver_timeout"].default - 1,
            )
            if isinstance(page_read, (int, float)) or isinstance(page_age, (int, float))
            else defaults["scope_window"].default,
        }
        return cls(**(values | overrides))


DEFAULT_BUDGET = TakeoverBudget()


def valid_budget_record(value):
    try:
        TakeoverBudget.from_dict(value)
    except (TypeError, ValueError):
        return False
    return True
