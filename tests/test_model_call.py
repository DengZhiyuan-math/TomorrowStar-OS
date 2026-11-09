"""Model Call Record scenarios, driven through send and verdict with fake runners."""

import json
import subprocess
from types import SimpleNamespace

import pytest

from career_evidence_graph import model_call
from career_evidence_graph.career_portal_data import PortalDataError
from career_evidence_graph.codex_cli import CodexCLIError
from career_evidence_graph.model_call import PAGE, Verdict

STARTED = "\n".join(
    json.dumps(event)
    for event in ({"type": "thread.started", "thread_id": "t-1"}, {"type": "turn.started"})
)


def answering(output):
    calls = []

    def runner(config, prompt, **options):
        calls.append(prompt)
        return SimpleNamespace(
            model_dump=lambda **_: {"status": "completed", "structured_result": output}
        )

    runner.calls = calls
    return runner


def raising(error):
    calls = []

    def runner(config, prompt, **options):
        calls.append(prompt)
        raise error

    runner.calls = calls
    return runner


@pytest.fixture
def call_dir(tmp_path):
    """A call directory whose stage already saved its prompt and schema."""
    (tmp_path / PAGE.prompt).write_text(json.dumps({"prompt": "p"}))
    (tmp_path / PAGE.schema).write_text("{}")
    return tmp_path


def test_nothing_saved_means_nothing_was_sent(tmp_path):
    assert model_call.verdict(tmp_path, PAGE) is Verdict.NOT_SENT


def test_an_answer_is_recorded(call_dir):
    result = model_call.send(call_dir, PAGE, answering({"x": 1}), None, "p")

    assert result.model_dump()["structured_result"] == {"x": 1}
    assert json.loads((call_dir / PAGE.result).read_text())["status"] == "completed"
    assert model_call.verdict(call_dir, PAGE) is Verdict.ANSWERED


def test_a_stage_rejection_marks_the_answer_rejected(call_dir):
    model_call.send(call_dir, PAGE, answering({"x": 1}), None, "p")
    (call_dir / model_call.REJECTION).write_text("{}")

    assert model_call.verdict(call_dir, PAGE) is Verdict.REJECTED


def test_a_failure_before_any_output_is_known(call_dir):
    error = CodexCLIError("boom", raw_stdout_jsonl=STARTED, redacted_stderr="")

    with pytest.raises(CodexCLIError):
        model_call.send(call_dir, PAGE, raising(error), None, "p")

    assert model_call.verdict(call_dir, PAGE) is Verdict.KNOWN_FAILURE


def test_a_timeout_after_output_began_is_unknown(call_dir):
    partial = STARTED + "\n" + json.dumps({"type": "item.started", "item": {}})
    error = CodexCLIError("Codex CLI timed out", raw_stdout_jsonl=partial)

    with pytest.raises(CodexCLIError):
        model_call.send(call_dir, PAGE, raising(error), None, "p")

    assert model_call.verdict(call_dir, PAGE) is Verdict.UNKNOWN


def test_a_crash_after_the_prompt_was_saved_is_unknown(call_dir):
    # The App closed during the call: the prompt exists, its result never arrived.
    assert model_call.verdict(call_dir, PAGE) is Verdict.UNKNOWN


def test_an_admission_refusal_is_recorded_and_nothing_is_called(call_dir):
    runner = answering({"x": 1})

    def refuse():
        raise CodexCLIError("Analysis dispatch is no longer admitted")

    with pytest.raises(CodexCLIError):
        model_call.send(call_dir, PAGE, runner, None, "p", before_send=refuse)

    assert runner.calls == []
    assert json.loads((call_dir / PAGE.result).read_text())["status"] == "failed"


def test_a_local_refusal_leaves_no_result(call_dir):
    with pytest.raises(PortalDataError):
        model_call.send(
            call_dir, PAGE, raising(PortalDataError("match_resume_invalid", "x", 409)), None, "p"
        )

    assert not (call_dir / PAGE.result).exists()


def test_raw_timeout_output_is_kept_as_text(call_dir):
    error = subprocess.TimeoutExpired(["codex"], 1, output=b"partial")

    with pytest.raises(subprocess.TimeoutExpired):
        model_call.send(call_dir, PAGE, raising(error), None, "p")

    receipt = json.loads((call_dir / PAGE.result).read_text())
    assert receipt["error_type"] == "TimeoutExpired"
    assert receipt["raw_stdout_jsonl"] == "partial"


@pytest.mark.parametrize(
    ("error", "code"),
    [
        (FileNotFoundError("codex"), "match_cli_missing"),
        (subprocess.TimeoutExpired(["codex"], 1), "match_model_timeout"),
        (CodexCLIError("x", redacted_stderr="Not logged in"), "match_cli_auth_required"),
        (CodexCLIError("x"), "job_brief_unavailable"),
    ],
)
def test_failure_codes_are_shared(error, code):
    assert model_call.failure_code(error, "job_brief_unavailable") == code
