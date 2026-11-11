"""Pure, bounded ATS parser observations and conservative field decisions.

The quiet windows are conservative local defaults, not an ATS completion guarantee.
No browser operations, persistence, retries, or model calls belong in this module.
"""

from __future__ import annotations

import hashlib
import json
import re
from copy import deepcopy
from datetime import date

SAMPLE_INTERVAL = 0.25
QUIET_WINDOW = 1.0
COMPLETE_WINDOW = 0.5
MIN_SAMPLES = 3
PARSER_TIMEOUT = 30.0


def _text(value) -> str:
    return " ".join(str("" if value is None else value).split())


def _telephone(value: str) -> str | None:
    if not re.fullmatch(r"\+?[\d ()\-.]+", value):
        return None
    digits = re.sub(r"[ ()\-.]", "", value)
    if digits.startswith("00"):
        digits = "+" + digits[2:]
    return digits if 7 <= len(digits.lstrip("+")) <= 15 else None


def _date(value: str) -> date | None:
    parts = re.fullmatch(r"(\d{1,4})[-/](\d{1,2})[-/](\d{1,4})", value)
    if not parts:
        return None
    a, b, c = map(int, parts.groups())
    if len(parts[1]) == 4:
        year, month, day = a, b, c
    elif len(parts[3]) == 4 and a > 12 >= b:
        year, month, day = c, b, a
    elif len(parts[3]) == 4 and b > 12 >= a:
        year, month, day = c, a, b
    else:
        return None
    try:
        return date(year, month, day)
    except ValueError:
        return None


def _email(value: str) -> str | None:
    if not re.fullmatch(r"[^\s@]+@[^\s@]+", value):
        return None
    local, domain = value.rsplit("@", 1)
    return local + "@" + "".join(char.lower() if "A" <= char <= "Z" else char for char in domain)


def equivalent(field: dict, a, b) -> bool:
    """Compare explicit meaning; do not infer country codes or ambiguous dates."""
    left, right = _text(a), _text(b)
    if left == right:
        return True
    kind = field.get("type", field.get("kind", "text"))
    normalizer = {"tel": _telephone, "email": _email, "date": _date}.get(kind)
    if normalizer:
        normalized = normalizer(left)
        return normalized is not None and normalized == normalizer(right)
    return False


def _filled(field: dict) -> str:
    return _text(field.get("filename") if field.get("type") == "file" else field.get("value"))


def decision(field: dict, proposed, *, baseline: dict | None = None, choice=None) -> str:
    """Keep existing facts; only blanks permit an unrequested fill.

    Explicit user choices require a revision-bound caller and are not accepted here.
    """
    if choice is not None:
        raise ValueError("Apply explicit choices only after checking the observed revision")
    current, desired = _filled(field), _text(proposed)
    if baseline and _filled(baseline) and not equivalent(field, _filled(baseline), current):
        return "difference"
    if equivalent(field, current, desired):
        return "keep"
    if not current:
        return "fill" if desired else "keep"
    # Invalid text alone cannot prove that the parser, rather than the user,
    # supplied it. Nonempty repairs use the same explicit application choice.
    return "difference"


def sample(prior: dict | None, observed: dict, *, binding: dict, now: float) -> dict:
    """Return a new observation state; preserve caller metadata only on this page/step."""
    same = bool(prior and prior.get("binding") == binding)
    state = deepcopy(prior) if same else {"schema": "form-state/v1", "binding": deepcopy(binding)}
    snapshot = {
        "fields": sorted(deepcopy(observed.get("fields", [])), key=lambda field: field["id"]),
        "retained_resume": deepcopy(observed.get("retained_resume", [])),
        "upload": deepcopy(observed.get("upload", {})),
        "validation_errors": deepcopy(observed.get("validation_errors", [])),
        "user_activity": deepcopy(observed.get("user_activity", {})),
    }
    digest = hashlib.sha256(
        json.dumps(snapshot, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    ).hexdigest()
    changed = state.get("snapshot_sha256") != digest
    state["revision"] = state.get("revision", 0) + int(changed)
    baseline = state.setdefault("baseline", {})
    for field in snapshot["fields"]:
        baseline.setdefault(field["id"], deepcopy(field))
    state.setdefault("upload_baseline", deepcopy(snapshot["upload"]))
    state.setdefault(
        "attachment_baseline",
        deepcopy([field for field in snapshot["fields"] if field.get("type") == "file"])
        + deepcopy(snapshot["retained_resume"]),
    )
    signal = observed.get("parser") or {}
    status = signal.get("status", "unknown")
    old = state.get("parser", {})
    starts_episode = old.get("status") == "stable" and (changed or status == "active")
    started = now if not old or starts_episode else old["started_at"]
    quiet_reset = (
        changed or old.get("observed_status") == "active" or status != old.get("observed_status")
    )
    stable_since = now if quiet_reset or old.get("stable_since") is None else old["stable_since"]
    last_sample = old.get("last_sample_at")
    counted = last_sample is None or now - last_sample >= SAMPLE_INTERVAL
    samples = 1 if quiet_reset else old.get("samples", 0) + int(counted)
    if status == "active":
        stable_since, samples = None, 0
    elapsed = now - started
    stable = (
        status not in {"active", "failed"}
        and stable_since is not None
        and now - stable_since >= (COMPLETE_WINDOW if status == "complete" else QUIET_WINDOW)
        and samples >= MIN_SAMPLES
    )
    failed = status == "failed" or not stable and elapsed >= PARSER_TIMEOUT
    state["snapshot"] = snapshot
    state["snapshot_sha256"] = digest
    state["parser"] = {
        "status": "failed" if failed else "stable" if stable else "waiting",
        "reason": "parser_failed" if status == "failed" else "parser_unstable" if failed else "",
        "signal": signal.get("signal", ""),
        "observed_status": status,
        "started_at": started,
        "stable_since": stable_since,
        "last_sample_at": now if counted or quiet_reset else last_sample,
        "samples": samples,
    }
    return state
