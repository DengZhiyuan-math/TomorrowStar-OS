"""Every model stage adopts the same input-bound native response contract."""

import json
from copy import deepcopy

import pytest
from test_application_job_brief import application as application
from test_application_job_brief import output as output
from test_application_job_brief import runner_for
from test_codex_cli import FakeRunner, _config, _success_process
from test_requirement_retrieval import inputs as inputs
from test_requirement_retrieval import model_runner, relevant

from career_evidence_graph import codex_cli
from career_evidence_graph.application_job_brief import create_job_brief
from career_evidence_graph.application_retrieval import plan_retrieval
from career_evidence_graph.career_portal_data import PortalDataError


def test_recorded_native_output_is_validated_without_starting_a_process(tmp_path):
    config = _config(tmp_path)
    prompt = "Return the known result."
    result = codex_cli.run_codex_exec(
        config, prompt, runner=FakeRunner(_success_process()), environment={}
    )
    before = deepcopy(result.model_dump(mode="json"))
    accepted = codex_cli.validate_recorded_result(
        before, prompt=prompt, output_schema=config.output_schema
    )
    assert accepted.structured_result == {"status": "ok"}
    assert before == result.model_dump(mode="json")


@pytest.mark.parametrize("change", ["parsed", "raw", "prompt", "schema"])
def test_recorded_response_rejects_inconsistent_native_result_or_input(tmp_path, change):
    config = _config(tmp_path)
    prompt = "Return the known result."
    result = codex_cli.run_codex_exec(
        config, prompt, runner=FakeRunner(_success_process()), environment={}
    ).model_dump(mode="json")
    if change == "parsed":
        result["structured_result"] = {"status": "tampered"}
    elif change == "raw":
        result["raw_stdout_jsonl"] = "not JSONL"
    elif change == "prompt":
        prompt = "Different input."
    else:
        config.output_schema.write_text('{"type":"array"}')
    with pytest.raises(codex_cli.CodexCLIError):
        codex_cli.validate_recorded_result(
            result, prompt=prompt, output_schema=config.output_schema
        )


def test_recorded_json_boolean_and_number_cannot_be_substituted(tmp_path):
    config = _config(tmp_path)
    prompt = "Return the known result."
    result = codex_cli.run_codex_exec(
        config, prompt, runner=FakeRunner(_success_process()), environment={}
    ).model_dump(mode="json")
    result["raw_stdout_jsonl"] = json.dumps({"type": "structured_result", "result": {"value": 1}})
    result["structured_result"] = {"value": True}
    with pytest.raises(codex_cli.CodexCLIError):
        codex_cli.validate_recorded_result(
            result, prompt=prompt, output_schema=config.output_schema
        )


def test_incomplete_retrieval_cannot_adopt_tampered_parsed_choices(inputs, tmp_path):
    application, snapshot = inputs
    old = plan_retrieval(
        application, snapshot, tmp_path / "original", runner=model_runner(relevant, [])
    )
    from pathlib import Path

    original = Path(old["directory"])
    (original / "plan.json").rename(original / "completed-plan-backup.json")
    result_path = original / "page-0001/result.json"
    result = json.loads(result_path.read_text())
    result["structured_result"]["selections"][0]["candidate_id"] = "ordinary"
    result_path.write_text(json.dumps(result))
    retained = result_path.read_bytes()
    with pytest.raises(PortalDataError) as caught:
        plan_retrieval(
            application,
            snapshot,
            tmp_path / "continued",
            resume_from=original,
            runner=lambda *_args, **_kwargs: pytest.fail("No model replay is allowed"),
        )
    assert caught.value.code == "retrieval_invalid"
    assert result_path.read_bytes() == retained


def test_incomplete_job_brief_cannot_adopt_tampered_parsed_interpretation(
    application, output, tmp_path
):
    original = tmp_path / "original"
    create_job_brief(application, original, runner=runner_for(output, []))
    (original / "job-brief.json").rename(original / "completed-brief-backup.json")
    result_path = original / "job-brief-result.json"
    result = json.loads(result_path.read_text())
    result["structured_result"]["business_object"] = "Tampered interpretation"
    result_path.write_text(json.dumps(result))
    retained = result_path.read_bytes()
    with pytest.raises(PortalDataError) as caught:
        create_job_brief(
            application,
            tmp_path / "continued",
            resume_from=original,
            runner=lambda *_args, **_kwargs: pytest.fail("No model replay is allowed"),
        )
    assert caught.value.code == "job_brief_invalid"
    assert result_path.read_bytes() == retained
