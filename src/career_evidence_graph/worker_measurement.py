"""Private, observational preparation records. No action or recovery authority."""

from __future__ import annotations

import fcntl
import hashlib
import json
import math
import os
import re
import time
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

_CLOCK = uuid4().hex
_SCOPE = ContextVar("worker_measurement_scope", default=None)
_LOG = ContextVar("worker_measurement_log", default=None)


def current_measurements():
    return _LOG.get()


_FIELDS = {
    "episode_id",
    "application_id",
    "revision",
    "batch_id",
    "run_id",
    "attempt_id",
    "stage",
    "span_id",
    "parent_span",
    "elapsed_ms",
    "result",
    "reason",
    "category",
    "cache",
    "model_mode",
    "usage",
    "usage_state",
    "fee",
    "currency",
    "fee_state",
    "tool",
    "operation",
    "dispatch",
    "request_group",
    "affected_jobs",
    "source",
    "status",
    "pending_sync",
    "intent_pending",
    "source_sha256",
    "runtime_mode",
    "resume_source",
}
_TEXT_FIELDS = _FIELDS - {
    "elapsed_ms",
    "usage",
    "fee",
    "pending_sync",
    "intent_pending",
    "affected_jobs",
}
_TOKEN_FIELDS = {"input_tokens", "output_tokens", "cached_input_tokens"}


def _valid_record(row: object) -> bool:
    """Validate records before their fields enter indexes or timeline arithmetic."""
    if not isinstance(row, dict) or row.get("schema_version") != "worker-measurement/v1":
        return False
    if any(
        not isinstance(row.get(key), str) or not row[key]
        for key in ("kind", "event_id", "utc", "clock_id")
    ):
        return False
    if type(row.get("monotonic_ns")) is not int or row["monotonic_ns"] < 0:
        return False
    required = {
        "episode_start": ("episode_id",),
        "stage_start": ("stage", "span_id"),
        "stage_end": ("stage", "span_id", "result"),
        "action_start": ("attempt_id",),
        "action_result": ("attempt_id",),
        "cache": ("cache",),
        "intervention_request": ("request_group",),
        "resume_preparation_start": ("request_group", "application_id", "revision"),
        "resume_preparation_ready": ("request_group", "application_id", "source_sha256", "source"),
        "resume_confirmation_request": ("request_group", "application_id", "revision", "reason"),
        "resume_confirmation_accept": ("request_group", "application_id", "revision"),
    }.get(row["kind"], ())
    if any(not isinstance(row.get(key), str) or not row[key] for key in required):
        return False
    if any(
        value is not None and not isinstance(value, str)
        for key, value in row.items()
        if key in _TEXT_FIELDS
    ):
        return False
    if row["kind"] == "stage_end" and row.get("elapsed_ms") is None:
        return False
    for key in ("elapsed_ms", "fee"):
        value = row.get(key)
        if value is not None and (
            type(value) not in {int, float}
            or value < 0
            or isinstance(value, float)
            and not math.isfinite(value)
        ):
            return False
    if any(type(row[key]) is not bool for key in ("pending_sync", "intent_pending") if key in row):
        return False
    if "affected_jobs" in row and (
        not isinstance(row["affected_jobs"], list)
        or any(not isinstance(item, str) for item in row["affected_jobs"])
    ):
        return False
    usage = row.get("usage")
    return (
        usage is None
        or isinstance(usage, dict)
        and all(
            key in _TOKEN_FIELDS and type(value) is int and value >= 0
            for key, value in usage.items()
        )
    )


class MeasurementLog:
    """Append safe metadata in an already validated private root."""

    def __init__(self, root: Path):
        self.root = root
        self.path = root / "measurements.jsonl"
        self.incomplete = False
        self._states = {}
        retained = self.read()
        self._requests = {
            event["request_group"] for event in retained if event["kind"] == "intervention_request"
        }
        self._categories = {
            e.get("episode_id"): e.get("category") for e in retained if e.get("kind") == "state"
        }

    def event(self, kind: str, **fields) -> None:
        record = {
            "schema_version": "worker-measurement/v1",
            "event_id": uuid4().hex,
            "kind": kind,
            "utc": datetime.now(UTC).isoformat(),
            "monotonic_ns": time.monotonic_ns(),
            "clock_id": _CLOCK,
            **{k: v for k, v in ((_SCOPE.get() or {}) | fields).items() if k in _FIELDS},
        }
        try:
            fd = os.open(self.path, os.O_CREAT | os.O_APPEND | os.O_RDWR | os.O_NOFOLLOW, 0o600)
            with os.fdopen(fd, "a", encoding="utf-8") as stream:
                if os.fstat(stream.fileno()).st_nlink != 1:
                    raise OSError("Measurement file is not exclusively owned")
                fcntl.flock(stream, fcntl.LOCK_EX)
                size = os.fstat(stream.fileno()).st_size
                if size and os.pread(stream.fileno(), 1, size - 1) != b"\n":
                    stream.write("\n")
                stream.write(json.dumps(record, ensure_ascii=False, allow_nan=False) + "\n")
                stream.flush()
        except (OSError, ValueError, TypeError):
            self.incomplete = True
            try:
                fd = os.open(
                    self.root / ".measurement-incomplete",
                    os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW,
                    0o600,
                )
                os.close(fd)
            except OSError:
                pass

    def read(self) -> list[dict]:
        try:
            fd = os.open(self.path, os.O_RDONLY | os.O_NOFOLLOW)
            with os.fdopen(fd, "rb") as stream:
                if os.fstat(stream.fileno()).st_nlink != 1:
                    raise OSError("Measurement file is not exclusively owned")
                fcntl.flock(stream, fcntl.LOCK_SH)
                records = []
                for line in stream:
                    if not line.strip():
                        continue
                    try:
                        row = json.loads(line.decode("utf-8"))
                        if not _valid_record(row):
                            raise ValueError("Invalid measurement record")
                    except ValueError:
                        self.incomplete = True
                        continue
                    records.append(row)
                return records
        except FileNotFoundError:
            return []
        except (OSError, ValueError):
            self.incomplete = True
            return []

    def begin(self, application_id: str, *, episode_id=None, **fields) -> str:
        if isinstance(episode_id, str) and re.fullmatch(r"[a-f0-9]{32}", episode_id):
            existing = [e for e in self.read() if e.get("episode_id") == episode_id]
            if any(
                e.get("application_id") == application_id and e.get("kind") == "episode_start"
                for e in existing
            ) and not any(e.get("category") == "terminal" for e in existing):
                return episode_id
        episode_id = uuid4().hex
        self.event("episode_start", episode_id=episode_id, application_id=application_id, **fields)
        return episode_id

    @staticmethod
    def _resume_key(value: str) -> str:
        return hashlib.sha256(value.encode("utf-8")).hexdigest()

    def preparation_started(self, task_id: str, input_revision: str) -> str:
        """Start before retrieval; resume the same unfinished input after reopen."""
        task, revision = self._resume_key(task_id), self._resume_key(input_revision)
        events = self.read()
        finished = {e["request_group"] for e in events if e["kind"] == "resume_preparation_ready"}
        for event in reversed(events):
            if (
                event["kind"] == "resume_preparation_start"
                and event["application_id"] == task
                and event["revision"] == revision
                and event["request_group"] not in finished
            ):
                return event["request_group"]
        episode = uuid4().hex
        self.event(
            "resume_preparation_start",
            episode_id=None,
            request_group=episode,
            application_id=task,
            revision=revision,
        )
        return episode

    def preparation_ready(
        self, episode_id: str, *, task_id: str, pdf_sha256: str, inherited: bool
    ) -> None:
        """Finish only when the adopted PDF is viewable, independently of acceptance."""
        task = self._resume_key(task_id)
        events = self.read()
        if not any(
            e["kind"] == "resume_preparation_start"
            and e["request_group"] == episode_id
            and e["application_id"] == task
            for e in events
        ) or any(
            e["kind"] == "resume_preparation_ready" and e["request_group"] == episode_id
            for e in events
        ):
            return
        self.event(
            "resume_preparation_ready",
            episode_id=None,
            request_group=episode_id,
            application_id=task,
            source_sha256=self._resume_key(pdf_sha256),
            source="inherited" if inherited else "generated",
        )

    def confirmation_requested(
        self, task_id: str, content_revision: str, *, already_accepted: bool = False
    ) -> None:
        """Observe one logical request, never repeated snapshots of the same request."""
        self._confirmation(
            "resume_confirmation_request", task_id, content_revision, already_accepted
        )

    def confirmation_accepted(self, task_id: str, content_revision: str) -> None:
        self._confirmation("resume_confirmation_accept", task_id, content_revision, False)

    def _confirmation(self, kind, task_id, content_revision, already_accepted):
        task, revision = self._resume_key(task_id), self._resume_key(content_revision)
        group = self._resume_key(json.dumps([task, revision]))
        events = self.read()
        if any(e["kind"] == kind and e.get("request_group") == group for e in events):
            return
        repeated = already_accepted or any(
            e["kind"] == "resume_confirmation_accept" and e["revision"] == revision for e in events
        )
        self.event(
            kind,
            episode_id=None,
            request_group=group,
            application_id=task,
            revision=revision,
            reason="repeat" if repeated else "new",
        )

    def reuse_summary(self) -> dict:
        """Internal end-to-end observations; never reconstruct time across processes."""
        events = self.read()
        starts = {e["request_group"]: e for e in events if e["kind"] == "resume_preparation_start"}
        rows = []
        seen = set()
        for end in events:
            if end["kind"] != "resume_preparation_ready" or end["request_group"] in seen:
                continue
            seen.add(end["request_group"])
            start = starts.get(end["request_group"])
            if not start or start["application_id"] != end["application_id"]:
                continue
            complete = (
                start["clock_id"] == end["clock_id"]
                and end["monotonic_ns"] >= start["monotonic_ns"]
            )
            rows.append(
                {
                    "episode_id": end["request_group"],
                    "task_id": start["application_id"],
                    "input_revision": start["revision"],
                    "pdf_sha256": end["source_sha256"],
                    "inherited": end["source"] == "inherited",
                    "clock_complete": complete,
                    "total_ms": (end["monotonic_ns"] - start["monotonic_ns"]) / 1e6
                    if complete
                    else None,
                }
            )
        requests = [e for e in events if e["kind"] == "resume_confirmation_request"]
        return {
            "schema_version": "resume-reuse-measurement-summary/v1",
            "preparations": rows,
            "confirmation_requests": len(requests),
            "confirmation_acceptances": sum(
                e["kind"] == "resume_confirmation_accept" for e in events
            ),
            "repeat_confirmation_requests": sum(e["reason"] == "repeat" for e in requests),
            "incomplete": self.incomplete or (self.root / ".measurement-incomplete").exists(),
        }

    @contextmanager
    def stage(self, stage: str, **fields):
        parent = _SCOPE.get() or {}
        span = {
            **parent,
            **fields,
            "stage": stage,
            "span_id": uuid4().hex,
            "parent_span": parent.get("span_id"),
        }
        token = _SCOPE.set(span)
        log_token = _LOG.set(self)
        self.event("stage_start")
        started = time.monotonic_ns()
        result = {"result": "passed"}
        try:
            yield result
        except BaseException as exc:
            result.update(
                result="unknown" if stage in {"model", "fill", "upload", "cua"} else "failed",
                reason=getattr(exc, "code", type(exc).__name__),
            )
            raise
        finally:
            self.event("stage_end", elapsed_ms=(time.monotonic_ns() - started) / 1e6, **result)
            _SCOPE.reset(token)
            _LOG.reset(log_token)

    def usage(self, raw: str) -> None:
        try:
            completed = [
                e
                for line in raw.splitlines()
                if line.strip() and (e := json.loads(line)).get("type") == "turn.completed"
            ]
            usage = completed[0].get("usage") if len(completed) == 1 else None
            valid = isinstance(usage, dict) and all(
                k in _TOKEN_FIELDS and type(v) is int and v >= 0 for k, v in usage.items()
            )
            usage = usage if valid and usage else None
        except (ValueError, AttributeError, TypeError):
            usage = None
        self.event(
            "model_usage",
            usage=usage,
            usage_state="observed" if usage else "unknown",
            fee=None,
            currency=None,
            fee_state="unknown",
        )

    def request_group(self, group: str, **fields) -> None:
        if group not in self._requests:
            self.event("intervention_request", request_group=group, **fields)
            self._requests.add(group)

    def track(self, state: dict) -> None:
        for job in state.get("jobs", []):
            if not job.get("measurement_id"):
                continue
            if not isinstance(job["measurement_id"], str) or not re.fullmatch(
                r"[a-f0-9]{32}", job["measurement_id"]
            ):
                self.incomplete = True
                continue
            category = "queue"
            if job["status"] == "cancelled":
                category = "unobserved" if job.get("intent") else "terminal"
            elif (
                job["status"] == "ready_for_review"
                and job.get("page_open")
                and not job.get("intent")
                and not job.get("pending_sync")
                and not job.get("sync_error")
            ):
                category = "terminal"
            elif state.get("worker_error"):
                category = "outage"
            elif state["control"] != "running":
                explicit_pause = (_SCOPE.get() or {}).get("operation") == "pause"
                category = (
                    "pause"
                    if explicit_pause or self._categories.get(job["measurement_id"]) == "pause"
                    else "user_wait"
                )
            elif job["status"] in {"needs_input", "needs_recheck", "ready_for_review"}:
                category = "user_wait"
            row = {
                "episode_id": job["measurement_id"],
                "application_id": job["application_id"],
                "batch_id": state["batch_id"],
                "run_id": state.get("runtime", {}).get("id"),
                "source_sha256": state.get("runtime", {}).get("source", {}).get("sha256"),
                "status": job["status"],
                "category": category,
                "reason": job.get("reason", ""),
                "pending_sync": bool(job.get("pending_sync") or job.get("sync_error")),
                "intent_pending": bool(job.get("intent")),
            }
            signature = json.dumps(row, sort_keys=True)
            if self._states.get(job["measurement_id"]) != signature:
                self.event("state", **row)
                self._states[job["measurement_id"]] = signature
            self._categories[job["measurement_id"]] = category
            if job["status"] == "needs_recheck" or row["pending_sync"]:
                intent = job.get("intent") or {}
                group = (
                    job["measurement_id"]
                    + ":"
                    + (intent.get("attempt_id") or row["reason"] or "sync")
                )
                self.request_group(
                    group,
                    episode_id=job["measurement_id"],
                    reason=row["reason"] or "sync",
                    batch_id=state["batch_id"],
                )

    def summary(self) -> dict:
        """Report measured intervals; missing clocks and costs stay unknown."""
        events = self.read()
        starts = [e for e in events if e["kind"] == "episode_start"]
        episode_ids = {e["episode_id"] for e in starts}
        unlinked = any(e.get("episode_id") and e["episode_id"] not in episode_ids for e in events)

        def span_key(event):
            return tuple(event.get(key) for key in ("episode_id", "span_id", "clock_id", "stage"))

        stage_starts = {span_key(e): e for e in events if e["kind"] == "stage_start"}
        stage_ends = {span_key(e): e for e in events if e["kind"] == "stage_end"}
        unmatched_episodes = {key[0] for key in stage_starts.keys() ^ stage_ends.keys()}
        startups = [
            (e, stage_ends[key])
            for key, e in stage_starts.items()
            if e.get("stage") == "runtime_start" and not e.get("episode_id") and key in stage_ends
        ]

        rows = []
        for start in starts:
            records = [e for e in events if e.get("episode_id") == start["episode_id"]]
            terminals = [
                e for e in records if e["kind"] == "state" and e.get("category") == "terminal"
            ]
            end = terminals[0] if terminals else records[-1]
            states = [e for e in records if e["kind"] == "state"]
            last = states[-1] if states else {}
            outcome = (
                "ready"
                if terminals and end.get("status") == "ready_for_review"
                else "cancelled"
                if last.get("status") == "cancelled"
                else "blocked"
                if last.get("status") in {"needs_input", "needs_recheck"}
                else "failed"
                if any(e["kind"] == "stage_end" and e.get("result") == "failed" for e in records)
                else "incomplete"
            )
            pairs = [
                (e, stage_ends[span_key(e)])
                for e in records
                if e["kind"] == "stage_start" and span_key(e) in stage_ends
            ]
            clocks = {e["clock_id"] for e in records}
            runs = {e["run_id"] for e in records if e.get("run_id")}
            complete_clock = (
                len(clocks) == 1 and len(runs) <= 1 and end["monotonic_ns"] >= start["monotonic_ns"]
            )
            times = dict.fromkeys(
                ("auto", "queue", "user_wait", "pause", "outage", "unobserved"), 0.0
            )
            wall = None
            if complete_clock:
                low, high = start["monotonic_ns"], end["monotonic_ns"]
                shared_boundaries = [
                    {**e, "kind": "boundary"}
                    for a, b in startups
                    for e in (a, b)
                    if e["clock_id"] == start["clock_id"] and low <= e["monotonic_ns"] <= high
                ]
                ordered = sorted(
                    [e for e in records if low <= e["monotonic_ns"] <= high] + shared_boundaries,
                    key=lambda e: e["monotonic_ns"],
                )
                category = "queue"
                for left, right in zip(ordered, ordered[1:], strict=False):
                    if left["kind"] == "state":
                        category = left.get("category", "unobserved")
                    midpoint = (left["monotonic_ns"] + right["monotonic_ns"]) / 2
                    active = any(
                        a["monotonic_ns"] <= midpoint < b["monotonic_ns"] for a, b in pairs
                    )
                    initializing = any(
                        a["clock_id"] == start["clock_id"]
                        and a["monotonic_ns"] <= midpoint < b["monotonic_ns"]
                        for a, b in startups
                    )
                    bucket = (
                        "auto"
                        if active
                        else "queue"
                        if initializing
                        else category
                        if category in times
                        else "unobserved"
                    )
                    times[bucket] += (right["monotonic_ns"] - left["monotonic_ns"]) / 1e6
                wall = (high - low) / 1e6
            else:
                # Keep within-process durations without pretending they reconstruct wall time.
                for a, b in pairs:
                    if not a.get("parent_span"):
                        times["auto"] += b["elapsed_ms"]
                times["unobserved"] = None
            usages = [e.get("usage") for e in records if e["kind"] == "model_usage"]
            usage = usages[0] if len(usages) == 1 and usages[0] else None
            action_starts = {e["attempt_id"]: e for e in records if e["kind"] == "action_start"}
            actions = []
            seen_actions = set()
            for e in records:
                if e["kind"] != "action_result" or e["attempt_id"] in seen_actions:
                    continue
                seen_actions.add(e["attempt_id"])
                origin = action_starts.get(e["attempt_id"])
                actions.append(
                    {
                        "stage": e.get("stage"),
                        "result": e.get("result"),
                        "elapsed_ms": (e["monotonic_ns"] - origin["monotonic_ns"]) / 1e6
                        if origin and origin["clock_id"] == e["clock_id"]
                        else None,
                    }
                )
            rows.append(
                {
                    "episode_id": start["episode_id"],
                    "application_id": start.get("application_id"),
                    "resume_source": start.get("resume_source"),
                    "outcome": outcome,
                    "wall_ms": wall,
                    "time_ms": times,
                    "clock_complete": complete_clock,
                    "measurement_complete": complete_clock
                    and start["episode_id"] not in unmatched_episodes
                    and not self.incomplete
                    and not (self.root / ".measurement-incomplete").exists(),
                    "stages": [
                        {
                            "stage": a["stage"],
                            "elapsed_ms": b["elapsed_ms"],
                            "result": b["result"],
                            "parent_span": a.get("parent_span"),
                        }
                        for a, b in pairs
                    ],
                    "actions": actions,
                    "cache": [e["cache"] for e in records if e["kind"] == "cache"],
                    "model_calls": sum(
                        e.get("stage") == "model" and e.get("model_mode") == "real"
                        for e in records
                        if e["kind"] == "stage_start"
                    ),
                    "synthetic_model_calls": sum(
                        e.get("stage") == "model" and e.get("model_mode") == "synthetic"
                        for e in records
                        if e["kind"] == "stage_start"
                    ),
                    "model_calls_unknown": sum(
                        e.get("stage") == "model" and e.get("model_mode") == "unknown"
                        for e in records
                        if e["kind"] == "stage_start"
                    ),
                    "cua_dispatch": {
                        status: sum(
                            e.get("dispatch") == status
                            for e in records
                            if e["kind"] == "stage_end" and e.get("stage") == "cua"
                        )
                        for status in ("acknowledged", "not_sent", "unknown")
                    },
                    "cua_calls": sum(
                        e.get("stage") == "cua" for e in records if e["kind"] == "stage_start"
                    ),
                    "usage": usage,
                    "fee": None,
                    "fee_state": "unknown",
                    "human_active_ms": None,
                    "intent_pending": last.get("intent_pending", False),
                }
            )
        shared = [e for e in events if not e.get("episode_id") and e["kind"] == "stage_end"]
        return {
            "schema_version": "worker-measurement-summary/v1",
            "episodes": rows,
            "shared_stages": [
                {k: e.get(k) for k in ("stage", "tool", "elapsed_ms", "result", "batch_id")}
                for e in shared
            ],
            "intervention_requests": len(
                {e["request_group"] for e in events if e["kind"] == "intervention_request"}
            ),
            "user_operations": [
                {k: e.get(k) for k in ("operation", "request_group", "source")}
                for e in events
                if e["kind"] == "user_operation"
            ],
            "incomplete": unlinked
            or bool(unmatched_episodes)
            or self.incomplete
            or (self.root / ".measurement-incomplete").exists(),
        }
