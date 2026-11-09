"""Model Call Record: one model call's prompt, schema, result and verdict.

Each call lives in its own directory. The calling stage saves the prompt and
schema files first; ``send`` then calls the runner and always leaves a result
file, whether the runner answered or raised. ``verdict`` reads those files back
as one of five outcomes, so no stage guesses a call's fate from missing files.
See CONTEXT.md, "Model Call Record".
"""

from __future__ import annotations

import json
import re
import subprocess
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from ._vendor import job_apply_store as helper
from .career_portal_data import PortalDataError
from .validation.hashing import record_digest as digest

REJECTION = "validation-failure.json"


class Verdict(StrEnum):
    NOT_SENT = "not_sent"
    KNOWN_FAILURE = "known_failure"
    UNKNOWN = "unknown"
    ANSWERED = "answered"
    REJECTED = "rejected"


@dataclass(frozen=True)
class Files:
    """The existing file names of one kind of call directory."""

    prompt: str
    schema: str
    result: str


EVALUATION = Files("context-input.json", "match-schema.json", "model-result.json")
JOB_BRIEF = Files("job-brief-prompt.json", "job-brief-schema.json", "job-brief-result.json")
PAGE = Files("prompt.json", "schema.json", "result.json")


def send(
    directory: Path, files: Files, runner, config, prompt: str, *, before_send=None, **options
):
    """Call the runner once and record its answer or failure in ``files.result``.

    ``before_send`` runs immediately before the call. An admission refusal it
    raises is recorded like a runner error, so the record shows nothing was sent.
    A runner error is recorded and re-raised unchanged for the stage to report.
    A local refusal (``PortalDataError``, e.g. a recorded answer that no longer
    matches its input) is not a call outcome and leaves no result file.
    """
    try:
        if before_send is not None:
            before_send()
        result = runner(config, prompt, **options)
    except PortalDataError:
        raise
    except Exception as error:
        helper.atomic_write_json(Path(directory) / files.result, failure_receipt(error))
        raise
    helper.atomic_write_json(Path(directory) / files.result, result.model_dump(mode="json"))
    return result


def failure_receipt(error) -> dict:
    return {
        "status": "failed",
        "error_type": type(error).__name__,
        "raw_stdout_jsonl": _error_text(error, "raw_stdout_jsonl", "output"),
        "redacted_stderr": _error_text(error, "redacted_stderr", "stderr"),
    }


def _error_text(error, primary, fallback):
    value = getattr(error, primary, getattr(error, fallback, "")) or ""
    return value.decode("utf-8", errors="replace") if isinstance(value, bytes) else str(value)


def failure_code(error, default="match_model_unavailable"):
    """Name a runner failure the same way in every stage."""
    if isinstance(
        error, FileNotFoundError
    ) or "configured Codex CLI executable is unavailable" in str(error):
        return "match_cli_missing"
    if isinstance(error, subprocess.TimeoutExpired) or "timed out" in str(error).casefold():
        return "match_model_timeout"
    stderr = _error_text(error, "redacted_stderr", "stderr")
    if re.search(r"not logged in|login required|not authenticated|unauthorized", stderr, re.I):
        return "match_cli_auth_required"
    return default


def verdict(directory: Path, files: Files) -> Verdict:
    """Read one call directory's outcome from its saved files."""
    directory = Path(directory)
    result = directory / files.result
    if result.exists() or result.is_symlink():
        try:
            receipt = helper.read_json_object(result, "model call result")
        except (OSError, ValueError, helper.StoreError):
            return Verdict.UNKNOWN
        if receipt.get("status") == "failed":
            if not is_known_failure(directory, receipt):
                return Verdict.UNKNOWN
            if receipt["error_type"] == "_CallNotAdmitted":
                return Verdict.NOT_SENT
            return Verdict.KNOWN_FAILURE
        rejection = directory / REJECTION
        return (
            Verdict.REJECTED if rejection.exists() or rejection.is_symlink() else Verdict.ANSWERED
        )
    # The prompt is saved before any call; without it nothing was sent.
    if any(
        (directory / name).exists() or (directory / name).is_symlink()
        for name in (files.prompt, files.schema)
    ):
        return Verdict.UNKNOWN
    return Verdict.NOT_SENT


def is_known_failure(directory: Path, receipt: dict) -> bool:
    """A failed receipt proves the model turn ended without an answer to adopt.

    A catch-all failed shell does not prove that the model turn terminated.
    """
    directory = Path(directory)
    if (
        set(receipt) != {"status", "error_type", "raw_stdout_jsonl", "redacted_stderr"}
        or not all(isinstance(value, str) for value in receipt.values())
        or receipt.get("status") != "failed"
    ):
        return False
    if receipt["error_type"] == "_CallNotAdmitted":
        return _refused_before_send(directory, receipt)
    if receipt["error_type"] not in {"CodexCLIError", "TimeoutExpired"}:
        return False
    try:
        events = [
            json.loads(line) for line in receipt["raw_stdout_jsonl"].splitlines() if line.strip()
        ]
    except ValueError:
        return False
    if all(isinstance(event, dict) for event in events) and {
        event.get("type") for event in events
    } <= {"thread.started", "turn.started"}:
        # A read-only analysis call that ended without any output has nothing to adopt;
        # the user's Continue may run it again (approved 2026-10-31).
        return True
    if receipt["error_type"] != "CodexCLIError":
        return False
    if len(events) != 4 or not all(isinstance(event, dict) for event in events):
        return False
    message = events[2].get("message")
    return (
        set(events[0]) == {"type", "thread_id"}
        and events[0].get("type") == "thread.started"
        and isinstance(events[0].get("thread_id"), str)
        and bool(events[0]["thread_id"].strip())
        and events[1] == {"type": "turn.started"}
        and isinstance(message, str)
        and bool(message.strip())
        and events[2] == {"type": "error", "message": message}
        and events[3] == {"type": "turn.failed", "error": {"message": message}}
    )


def _refused_before_send(directory: Path, receipt: dict) -> bool:
    """An admission refusal is proven by the analysis' dispatch-stopped receipt."""
    schema = next(
        (
            path
            for name in ("match-schema.json", "job-brief-schema.json", "schema.json")
            if (path := directory / name).is_file()
        ),
        None,
    )
    if schema is None or receipt["raw_stdout_jsonl"] != "" or receipt["redacted_stderr"] != "":
        return False
    for root in (directory, *list(directory.parents)[:3]):
        stopped_path = root / "dispatch-stopped.json"
        if not stopped_path.is_file() or stopped_path.is_symlink():
            continue
        try:
            stopped = helper.read_json_object(stopped_path, "stop")
            if root.name == "analysis":
                request_revision = digest(
                    helper.read_json_object(root.parent / "intent.json", "intent")
                )
            else:
                requests = list((root.parent / "requests").glob(f"*/{root.name}.json"))
                if len(requests) != 1:
                    return False
                request = helper.read_json_object(requests[0], "analysis request")
                request_revision = digest(
                    {key: value for key, value in request.items() if key != "revision"}
                )
                if request.get("revision") != request_revision:
                    return False
        except (OSError, ValueError, helper.StoreError):
            return False
        return (
            stopped.get("schema_version") == "analysis-dispatch-stopped/v1"
            and stopped.get("new_call_dispatched") is False
            and stopped.get("undispatched_schema") == str(schema.relative_to(root))
            and stopped.get("request_revision") == request_revision
            and stopped.get("revision")
            == digest({key: value for key, value in stopped.items() if key != "revision"})
        )
    return False
