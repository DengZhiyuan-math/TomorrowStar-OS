"""One job's Codex takeover record: its transitions, history and the takeover limit.

The Worker keeps the record in its checkpoint (``job["assistance"]`` and
``job["assistance_history"]``); every change to it goes through this Module. It
depends on no Worker, Adapter or browser code, so each of them can rely on it.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
import time
from copy import deepcopy
from uuid import uuid4

from .career_portal_data import PortalDataError

ASSISTANCE_REPORT = "assistance-report/v1"
# User/system controls after which a late Codex report can only remain history.
ASSISTANCE_CONTROL_REASONS = frozenset(
    {
        "user_paused",
        "cancelled",
        "skip-current",
        "select-current",
        "worker_restarted",
        "backend_closed",
        "backend_authority_lost",
    }
)
TAKEOVER_UNKNOWN_REASONS = frozenset(
    {
        "action_result_unknown",
        "upload_result_unknown",
        "draft_result_unknown",
        "draft_result_unverified",
        "public_read_result_unknown",
        "browser_result_unknown",
    }
)
# What the script cannot handle goes to Codex; missing facts stay needs_input.
TAKEOVER_REASONS = TAKEOVER_UNKNOWN_REASONS | {
    "unsupported_control",
    "unsupported_structure",
    "unsupported_attachments",
    "unsupported_attachment_transport",
    "ambiguous_option",
    "user_authentication",
    "route_change_forbidden",
    "parser_failed",
    "parser_unstable",
}
# select_fill_route uses this code when the script has no route for a control; only that
# current not-sent route decision dispatches. A Cua/driver failure itself never does.
TAKEOVER_ROUTE_REASONS = frozenset({"cua_unavailable"})
TAKEOVER_CODES = TAKEOVER_REASONS | TAKEOVER_ROUTE_REASONS
# Each takeover still needs the user's Continue. The limit counts only rows that can
# still matter: an unsettled stop, or a failed blocker that is never re-sent. Settled
# rows keep a short recent tail; generations come from their own counter (2026-11-02:
# repeated repairs used up all 32, then 64, settled rows on one real job).
ASSISTANCE_HISTORY_LIMIT = 64
SETTLED_HISTORY_RETAINED = 16
_CODE = re.compile(r"[a-z][a-z0-9_]{0,99}")

# Report text limits live in the schema itself. Strict outputs enforce `pattern`
# while generating; they reject `maxLength`, so the model reads each bound from its
# `description` and `report_matches` enforces it. The Adapter's check and the
# Worker's adoption check are this one schema.
# Excludes controls and the invisible separators copied page text carries; `isprintable`
# below remains the final check for any rarer unprintable character.
# Non-ASCII members are literal characters (JSON escapes them), not regex `\\u` escapes,
# which some regex dialects lack.
_LINE = "^[^\\x00-\\x1f\x7f-\xa0\xad ᠎ -‏ -  -⁯　﻿]+$"
MAX_REPORT_CHARS = 65_536


def _text(limit):
    return {
        "type": "string",
        "maxLength": limit,
        "pattern": _LINE,
        "description": f"Non-empty single-line printable text, at most {limit} characters.",
    }


_ID = _text(128)
REPORT_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "status": {
            "type": "string",
            "enum": [
                "blocked_segment_resolved",
                "ready_for_review",
                "needs_input",
                "needs_recheck",
            ],
        },
        "summary": {
            "type": "string",
            "maxLength": 2000,
            "description": "At most 2000 characters.",
        },
        "unresolved_action_ids": {"type": "array", "items": _ID, "maxItems": 1000},
        "fields": {
            "type": "array",
            "maxItems": 1000,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {"field_id": _ID, "state": _text(64)},
                "required": ["field_id", "state"],
            },
        },
        "next_step": {
            "anyOf": [
                {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "kind": _text(64),
                        "field_id": dict(
                            _ID,
                            type=["string", "null"],
                            description="Null when no next field is named; otherwise "
                            "non-empty single-line printable text, at most 128 characters.",
                        ),
                    },
                    "required": ["kind", "field_id"],
                },
                {"type": "null"},
            ]
        },
    },
    # Strict structured outputs require every property; optional ones are nullable.
    "required": ["status", "summary", "unresolved_action_ids", "fields", "next_step"],
}


def report_matches(value, schema=REPORT_SCHEMA):
    """Check the small JSON Schema subset used by `REPORT_SCHEMA`."""
    if "anyOf" in schema:
        return any(report_matches(value, option) for option in schema["anyOf"])
    if schema["type"] == "null":
        return value is None
    if isinstance(schema["type"], list):
        # Only nullable scalars use a type list.
        (kind,) = set(schema["type"]) - {"null"}
        return value is None or report_matches(value, dict(schema, type=kind))
    if schema["type"] == "string":
        return (
            isinstance(value, str)
            and value in schema.get("enum", (value,))
            and len(value) <= schema.get("maxLength", len(value))
            and (
                "pattern" not in schema
                or bool(re.fullmatch(schema["pattern"], value))
                and value.isprintable()
            )
        )
    if schema["type"] == "array":
        return (
            isinstance(value, list)
            and len(value) <= schema["maxItems"]
            and all(report_matches(item, schema["items"]) for item in value)
        )
    properties = schema["properties"]
    return (
        isinstance(value, dict)
        and set(schema["required"]) <= set(value) <= set(properties)
        and all(report_matches(item, properties[key]) for key, item in value.items())
    )


def canonical_sha256(value):
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    ).hexdigest()


def bounded_text(value, limit=200):
    return isinstance(value, str) and 1 <= len(value) <= limit and value.isprintable()


def valid_timestamp(value):
    return type(value) in (int, float) and math.isfinite(value) and value > 0


def valid_assistance_report(report):
    """A Codex claim, strictly shaped; it is never evidence of a verified page."""
    try:
        return bool(
            isinstance(report, dict)
            and set(report)
            == {
                "protocol",
                "request_id",
                "native_turn_id",
                "received_at",
                "claimed",
                "claimed_sha256",
            }
            and report["protocol"] == ASSISTANCE_REPORT
            and bounded_text(report["request_id"])
            and bounded_text(report["native_turn_id"])
            and valid_timestamp(report["received_at"])
            and report_matches(report["claimed"])
            and report["claimed_sha256"] == canonical_sha256(report["claimed"])
            and len(json.dumps(report, sort_keys=True, separators=(",", ":"))) <= MAX_REPORT_CHARS
        )
    except (KeyError, TypeError, ValueError, RecursionError):
        return False


def valid_takeover_blocker(blocker, binding):
    return bool(
        isinstance(blocker, dict)
        and set(blocker) == {"code", "field_id", "page_id", "run_id", "observed_at"}
        and blocker["code"] in TAKEOVER_CODES
        and (blocker["field_id"] is None or isinstance(blocker["field_id"], str))
        and blocker["page_id"] == binding["page_id"]
        and blocker["run_id"] == binding["run_id"]
        and valid_timestamp(blocker["observed_at"])
    )


def valid_takeover_dispatch(dispatch, assistance):
    keys = {"request_id", "blocker", "requested_at", "continue_serial"}
    return bool(
        isinstance(dispatch, dict)
        and keys <= set(dispatch) <= keys | {"failed_code", "pending_intent_ref"}
        and isinstance(assistance.get("binding"), dict)
        and dispatch["request_id"] == assistance["claim_request_id"]
        and valid_takeover_blocker(dispatch["blocker"], assistance["binding"])
        and valid_timestamp(dispatch["requested_at"])
        and type(dispatch["continue_serial"]) is int
        and dispatch["continue_serial"] == assistance["binding"]["resume_serial"]
        and (
            "failed_code" not in dispatch
            or isinstance(dispatch["failed_code"], str)
            and _CODE.fullmatch(dispatch["failed_code"])
        )
        and (
            "pending_intent_ref" not in dispatch
            or dispatch["blocker"]["code"] in TAKEOVER_UNKNOWN_REASONS
            and isinstance(dispatch["pending_intent_ref"], str)
            and re.fullmatch(r"[a-f0-9]{64}", dispatch["pending_intent_ref"])
        )
    )


_STOP_STATUSES = {"stopping": "stopping", "stopped": "stopped", "unknown": "stop_unknown"}


def valid_assistance_stop(stop, status):
    if not isinstance(stop, dict) or set(stop) != {
        "request_id",
        "reason",
        "requested_at",
        "tools_revoked",
        "local_tools_drained",
        "process_stopped",
        "native_turn_id",
        "native_turn_status",
        "stop_status",
        "observed_at",
    }:
        return False
    return bool(
        bounded_text(stop["request_id"], 200)
        and isinstance(stop["reason"], str)
        and 1 <= len(stop["reason"]) <= 100
        and valid_timestamp(stop["requested_at"])
        and stop["tools_revoked"] is True
        and type(stop["local_tools_drained"]) is bool
        and type(stop["process_stopped"]) is bool
        and (
            stop["native_turn_id"] is None
            or isinstance(stop["native_turn_id"], str)
            and 1 <= len(stop["native_turn_id"]) <= 200
            and stop["native_turn_id"].isprintable()
        )
        and isinstance(stop["native_turn_status"], str)
        and stop["native_turn_status"]
        in {"idle", "running", "completed", "interrupted", "failed", "unknown"}
        and not (stop["process_stopped"] and stop["native_turn_status"] == "running")
        and isinstance(stop["stop_status"], str)
        and _STOP_STATUSES.get(stop["stop_status"]) == status
        and (stop["observed_at"] is None or valid_timestamp(stop["observed_at"]))
        and (
            stop["stop_status"] != "stopped"
            or stop["local_tools_drained"] is True
            and stop["process_stopped"] is True
        )
    )


def stop_proven(assistance):
    """The one definition of a proven stop: no Codex tool can still reach the page.

    Tools are revoked, local tool calls drained and the native process stopped. A
    record without a takeover (None or empty) has nothing left to stop.
    """
    if not assistance:
        return True
    stop = assistance.get("stop") or {}
    return (
        assistance.get("status") in {"stopped", "released"}
        and stop.get("tools_revoked") is True
        and stop.get("local_tools_drained") is True
        and stop.get("process_stopped") is True
    )


def assistance_stop_pending(job):
    return not stop_proven(job.get("assistance"))


def _counted(row):
    """A history row the limit counts: an unsettled stop, or a failed blocker."""
    return bool((row.get("dispatch") or {}).get("failed_code")) or not stop_proven(row)


def counted_rows(job):
    """Rows that hold the takeover limit, including the current record."""
    assistance = job.get("assistance")
    rows = [*job.get("assistance_history", []), *([assistance] if assistance else [])]
    return sum(_counted(row) for row in rows)


def capacity_left(job):
    return counted_rows(job) < ASSISTANCE_HISTORY_LIMIT


def valid_history(history):
    """The retained history bound; a settled row beyond its short tail is never kept."""
    return (
        isinstance(history, list)
        and sum(_counted(row) for row in history if isinstance(row, dict))
        <= ASSISTANCE_HISTORY_LIMIT
        and len(history) <= ASSISTANCE_HISTORY_LIMIT + SETTLED_HISTORY_RETAINED
    )


def valid_generation_counter(job):
    value = job.get("assistance_generation", 0)
    return type(value) is int and 0 <= value < 2**63


def next_generation(job):
    """A monotonic generation; it never depends on how many rows are retained."""
    rows = [*job.get("assistance_history", []), job.get("assistance") or {}]
    return 1 + max(
        job.get("assistance_generation", 0),
        *(row.get("generation", 0) for row in rows),
    )


def archive(job, row):
    """Move one settled-or-retired record to history, keeping every counted row.

    Only the oldest settled rows beyond a short recent tail are dropped; the
    generation counter keeps their numbers.
    """
    job["assistance_generation"] = max(job.get("assistance_generation", 0), row["generation"])
    history = [*job.get("assistance_history", []), row]
    settled = [index for index, entry in enumerate(history) if not _counted(entry)]
    dropped = set(settled[: max(0, len(settled) - SETTLED_HISTORY_RETAINED)])
    job["assistance_history"] = [
        entry for index, entry in enumerate(history) if index not in dropped
    ]


def begin(job, assistance):
    """Make a new record current; the previous one, if any, becomes history."""
    previous = job.get("assistance")
    if previous:
        archive(job, deepcopy(previous))
    job["assistance"] = assistance
    job["assistance_generation"] = max(
        job.get("assistance_generation", 0), assistance["generation"]
    )
    return assistance


def request_conflict(job, request_id):
    """True when a retained row already used this takeover request id."""
    return any(
        (row.get("dispatch") or {}).get("request_id") == request_id
        for row in job.get("assistance_history", [])
    )


def failed_blocker(job, blocker):
    identity = [blocker[key] for key in ("code", "field_id", "page_id")]
    assistance = job.get("assistance")
    return any(
        (row.get("dispatch") or {}).get("failed_code")
        and [row["dispatch"]["blocker"][key] for key in ("code", "field_id", "page_id")] == identity
        for row in [*job.get("assistance_history", []), *([assistance] if assistance else [])]
    )


def takeover_slot(state, job, blocker):
    """One takeover per blocker: after a released checkpoint, or once per explicit Continue."""
    assistance = job.get("assistance")
    if not capacity_left(job) or failed_blocker(job, blocker):
        return False
    if not assistance:
        return True
    if "superseded" in assistance or not stop_proven(assistance):
        return False
    if assistance["status"] == "released":
        return assistance["outcome"]["kind"] == "script_checkpoint"
    serial = (assistance.get("dispatch") or {}).get(
        "continue_serial", assistance["binding"]["resume_serial"]
    )
    return assistance["status"] == "stopped" and state.get("resume_serial", 0) > serial


def record_takeover_failure(job, *, request_id, code):
    """Keep a Codex capability failure on its dispatch so the same blocker is not re-sent."""
    dispatch = (job.get("assistance") or {}).get("dispatch")
    if (
        not dispatch
        or dispatch["request_id"] != request_id
        or not isinstance(code, str)
        or _CODE.fullmatch(code) is None
    ):
        raise PortalDataError("assistance_generation_changed", "接管派发引用已改变。", 409)
    if "failed_code" in dispatch:
        return False
    dispatch["failed_code"] = code
    return True


def revoke_assistance(job, *, reason, request_id=None):
    """Revoke the original scope without releasing its writer reservation."""
    assistance = job.get("assistance")
    if not assistance:
        return False
    changed = False
    loss = assistance.get("backend_loss")
    if (
        loss
        and loss["automatic_recovery"]
        and reason
        in {"user_paused", "cancelled", "skip-current", "select-current", "worker_restarted"}
    ):
        loss["automatic_recovery"] = False
        changed = True
    if "stop" in assistance:
        if (
            "outcome" not in assistance
            and "superseded" not in assistance
            and reason in ASSISTANCE_CONTROL_REASONS
            and assistance["stop"]["reason"] not in ASSISTANCE_CONTROL_REASONS
        ):
            assistance["superseded"] = {"reason": reason, "at": time.time()}
            changed = True
        return changed
    assistance.update(
        status="stopping",
        stop={
            "request_id": request_id or uuid4().hex,
            "reason": reason,
            "requested_at": time.time(),
            "tools_revoked": True,
            "local_tools_drained": False,
            "process_stopped": False,
            "native_turn_id": None,
            "native_turn_status": "unknown",
            "stop_status": "stopping",
            "observed_at": None,
        },
    )
    return True


def archive_stopped_assistance(job):
    """On Continue, retain a proven-stopped takeover wait as history so the script rechecks.

    A stopped record outside a wait stays: its lost outcome save may be re-adopted.
    """
    assistance = job.get("assistance")
    reason = job.get("reason") or ""
    failed = ((assistance or {}).get("dispatch") or {}).get("failed_code")
    if (
        not assistance
        or job["status"] != "needs_recheck"
        or not (reason in TAKEOVER_CODES or reason.startswith("assistance_") or reason == failed)
        or assistance["status"] != "stopped"
        or not stop_proven(assistance)
        or "backend_loss" in assistance
        or (assistance.get("superseded") or {}).get("reason") not in (None, "user_paused")
        or job.get("handed_off")
    ):
        return False
    archive(job, deepcopy(assistance))
    del job["assistance"]
    job.update(status="queued", reason="")
    return True


def retire_for_reopen(job):
    """Retire the closed page's takeover; return the unconfirmed stop it carried, if any.

    Reopen runs only after the old run exited and its native driver went with it, so
    nothing can still be in flight. An unconfirmed stop is kept for the reopen record.
    """
    row = job.pop("assistance", None)
    if not row:
        return None
    retired_stop = None
    if row["status"] not in {"stopped", "released"}:
        retired_stop = deepcopy(row["stop"])
        row["stop"].update(stop_status="stopped", local_tools_drained=True, observed_at=time.time())
        row["status"] = "stopped"
    archive(job, row)
    return retired_stop
