"""Model Call Record: one model call's prompt, schema, result and verdict.

Each call lives in its own directory. The calling stage saves the prompt and
schema files first; ``send`` then calls the runner and always leaves a result
file, whether the runner answered or raised. ``verdict`` reads those files back
as one of five outcomes, so no stage guesses a call's fate from missing files.
Given an earlier call's directory, ``send`` reuses its answer when the question
is identical and asks again otherwise. See CONTEXT.md, "Model Call Record".
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
from .codex_cli import CodexCLIError, output_validation_marker, validate_recorded_result
from .validation.hashing import record_digest as digest
from .validation.hashing import sha256_digest

REJECTION = "validation-failure.json"
NOT_SENT_RECEIPT = {"status": "not_sent", "reason": "damaged_earlier_record"}


class DamagedRecord(Exception):
    """The earlier call's saved files do not agree with each other."""


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
    directory: Path,
    files: Files,
    runner,
    config,
    prompt: str,
    *,
    previous: Path | None = None,
    before_send=None,
    **options,
):
    """Call the runner once and record its answer or failure in ``files.result``.

    With ``previous``, an earlier call's answer to the identical question is
    recorded here instead, without calling or running ``before_send``; see
    ``recorded_answer`` for when that applies and what it raises.
    ``before_send`` runs immediately before the call. An admission refusal it
    raises is recorded like a runner error, so the record shows nothing was sent.
    A runner error is recorded and re-raised unchanged for the stage to report.
    A local refusal (``PortalDataError``) is not a call outcome and leaves no
    result file.
    """
    if previous is not None:
        try:
            answer = recorded_answer(previous, files, prompt, config)
        except DamagedRecord:
            # Refused before sending: the record says so, so it never reads as unknown.
            helper.atomic_write_json(Path(directory) / files.result, NOT_SENT_RECEIPT)
            raise
        if answer is not None:
            helper.atomic_write_json(Path(directory) / files.result, answer.model_dump(mode="json"))
            return answer
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


def recorded_answer(previous: Path, files: Files, prompt: str, config):
    """The earlier call's answer when it was asked this identical question.

    Identical means the same prompt, output schema and model. Returns None when a
    new call is due: no answer was recorded, the answer was rejected, or the
    question differs. Raises as ``earlier_answer`` does.
    """
    answer = earlier_answer(previous, files)
    if answer is None:
        return None
    try:
        same_question = (
            answer.prompt_hash == sha256_digest(prompt.encode())
            and answer.output_schema_hash == sha256_digest(Path(config.output_schema).read_bytes())
            and answer.requested_configuration.get("model") == config.requested_model
        )
    except OSError as error:
        raise DamagedRecord(str(previous)) from error
    return answer if same_question else None


def earlier_answer(previous: Path, files: Files):
    """The earlier call's checked answer, or None when it has none to offer.

    None means no answer was recorded (not sent, a known failure, or an unknown
    outcome) or the answer was rejected; the call is then sent again. An unknown
    outcome is resent because a model call has no effect outside the App, and an
    earlier attempt is only resumed after it ended. Raises DamagedRecord when the
    saved answer, prompt, schema or rejection do not agree. Stages call this
    before saving a new attempt, so a damaged record is never copied into it.
    """
    previous = Path(previous)
    state = verdict(previous, files)
    if state in {Verdict.NOT_SENT, Verdict.KNOWN_FAILURE, Verdict.UNKNOWN}:
        return None
    try:
        if any((previous / name).is_symlink() for name in (files.prompt, files.schema)):
            raise DamagedRecord(str(previous))
        saved = helper.read_json_object(previous / files.result, "model call result")
        asked = helper.read_json_object(previous / files.prompt, "model call prompt")["prompt"]
        answer = validate_recorded_result(
            saved, prompt=asked, output_schema=previous / files.schema
        )
        if state is Verdict.REJECTED:
            marker = helper.read_json_object(previous / REJECTION, "model call rejection")
            if marker != output_validation_marker(
                answer, asked, previous / files.schema, marker.get("error_code")
            ):
                raise DamagedRecord(str(previous))
            return None
    except (OSError, KeyError, TypeError, ValueError, CodexCLIError, helper.StoreError) as error:
        raise DamagedRecord(str(previous)) from error
    return answer


def ended_without_answer(directory: Path) -> bool:
    """A saved call under ``directory`` was sent and produced no answer.

    That is a known failure or an unknown outcome; a refusal before sending is
    not. Only meaningful once the attempt holding ``directory`` has ended.
    """
    directory = Path(directory)
    return any(
        verdict(prompt.parent, files) in {Verdict.KNOWN_FAILURE, Verdict.UNKNOWN}
        for files in (PAGE, JOB_BRIEF, EVALUATION)
        for prompt in directory.rglob(files.prompt)
        if not prompt.is_symlink()
    )


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


def input_too_large(error) -> bool:
    """The CLI refused the input as over its length limit; resending cannot help."""
    return "input_too_large" in _error_text(error, "redacted_stderr", "stderr")


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
    if result.is_symlink():
        # A result that is not this directory's own file is never adopted.
        return Verdict.UNKNOWN
    if result.exists():
        try:
            receipt = helper.read_json_object(result, "model call result")
        except (OSError, ValueError, helper.StoreError):
            return Verdict.UNKNOWN
        if receipt == NOT_SENT_RECEIPT:
            return Verdict.NOT_SENT
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
