"""Job interpretation resumes from durable evidence without a repeated provider call."""

import json
from copy import deepcopy

import pytest
from test_application_job_brief import application as application
from test_application_job_brief import output as output
from test_application_job_brief import runner_for
from test_application_match import model_runner
from test_matching_stage_recovery import terminal_model_failure

from career_evidence_graph.application_job_brief import create_job_brief
from career_evidence_graph.career_portal_data import PortalDataError
from career_evidence_graph.codex_cli import output_validation_marker
from career_evidence_graph.validation.hashing import sha256_digest


def test_complete_brief_is_adopted_into_a_new_attempt_without_calling_again(
    tmp_path, application, output
):
    calls = []
    old = tmp_path / "old"
    expected = create_job_brief(application, old, runner=runner_for(output, calls))
    before = {path.name: path.read_bytes() for path in old.iterdir()}
    actual = create_job_brief(
        application, tmp_path / "new", runner=runner_for(output, calls), resume_from=old
    )
    assert actual == expected
    assert len(calls) == 1
    assert {path.name: path.read_bytes() for path in old.iterdir()} == before
    assert (tmp_path / "new/job-brief.json").exists()


def test_known_failed_brief_can_start_one_new_provider_attempt(tmp_path, application, output):
    old = tmp_path / "old"

    def failed(*args, **kwargs):
        raise terminal_model_failure("Synthetic confirmed terminal CLI failure")

    with pytest.raises(PortalDataError):
        create_job_brief(application, old, runner=failed)
    calls, dispatched = [], []
    result = create_job_brief(
        application,
        tmp_path / "retry",
        runner=runner_for(output, calls),
        resume_from=old,
        on_dispatch=lambda: dispatched.append(True),
    )
    assert result["business_object"] == "Pricing and risk decisions"
    assert len(calls) == 1
    assert dispatched == [True]
    assert (tmp_path / "retry/job-brief.json").exists()


def test_interrupted_brief_is_sent_again_once(tmp_path, application, output):
    # An unknown model result has no outside effect; the retry sends it again
    # (Model Call Record, decided 2026-11-09).
    old = tmp_path / "old"

    def interrupted(*args, **kwargs):
        raise KeyboardInterrupt

    with pytest.raises(KeyboardInterrupt):
        create_job_brief(application, old, runner=interrupted)
    before = {path.name: path.read_bytes() for path in old.iterdir()}
    calls = []
    result = create_job_brief(
        application, tmp_path / "new", runner=runner_for(output, calls), resume_from=old
    )
    assert result["business_object"] == "Pricing and risk decisions"
    assert len(calls) == 1
    assert {path.name: path.read_bytes() for path in old.iterdir()} == before


def test_saved_success_is_validated_locally_if_final_brief_was_not_published(
    tmp_path, application, output
):
    old = tmp_path / "old"
    calls = []
    expected = create_job_brief(application, old, runner=model_runner(output, calls))
    (old / "job-brief.json").unlink()
    before = {path.name: path.read_bytes() for path in old.iterdir()}
    dispatched = []
    actual = create_job_brief(
        application,
        tmp_path / "new",
        runner=model_runner(output, calls),
        resume_from=old,
        on_dispatch=lambda: dispatched.append(True),
    )
    assert actual == expected
    assert len([call for call in calls if call[-1] != "--version"]) == 1
    assert dispatched == []
    assert {path.name: path.read_bytes() for path in old.iterdir()} == before


@pytest.mark.parametrize("artifact", ["job-brief-prompt.json", "job-brief-schema.json", "hash"])
def test_raw_brief_replay_rejects_changed_prompt_or_schema_without_a_model_retry(
    tmp_path, application, output, artifact
):
    old = tmp_path / "old"
    calls = []
    create_job_brief(application, old, runner=model_runner(output, calls))
    (old / "job-brief.json").unlink()
    if artifact == "hash":
        path = old / "job-brief-result.json"
        saved = json.loads(path.read_text())
        saved["prompt_hash"] = "sha256:" + "0" * 64
        path.write_text(json.dumps(saved))
    else:
        (old / artifact).write_text("{}")
    with pytest.raises(PortalDataError) as error:
        create_job_brief(
            application, tmp_path / "new", runner=model_runner(output, calls), resume_from=old
        )
    assert error.value.code == "job_brief_invalid"
    assert len([call for call in calls if call[-1] != "--version"]) == 1


@pytest.mark.parametrize("invalid", ["schema", "semantic"])
def test_known_invalid_brief_can_be_replaced_without_replaying_forever(
    tmp_path, application, output, invalid
):
    old = tmp_path / "old"
    calls = []
    bad = {} if invalid == "schema" else deepcopy(output)
    if invalid == "semantic":
        bad["groups"][0]["jd_quote"] = "Unrecorded duty"
    with pytest.raises(PortalDataError) as error:
        create_job_brief(application, old, runner=model_runner(bad, calls))
    assert error.value.code == "job_brief_invalid"
    before = {path.name: path.read_bytes() for path in old.iterdir()}
    dispatched = []
    result = create_job_brief(
        application,
        tmp_path / "retry",
        runner=model_runner(output, calls),
        resume_from=old,
        on_dispatch=lambda: dispatched.append(True),
    )
    assert result["business_object"] == "Pricing and risk decisions"
    assert dispatched == [True]
    assert len([call for call in calls if call[-1] != "--version"]) == 2
    assert {path.name: path.read_bytes() for path in old.iterdir()} == before
    assert (old / "validation-failure.json").is_file()


def test_brief_rejected_under_an_earlier_prompt_is_asked_again(tmp_path, application, output):
    # 2026-11-04: after a prompt update, retrying a rejected brief failed before any
    # model call; a rejected brief is never adopted, so the retry asks again.
    old = tmp_path / "old"
    calls = []
    bad = deepcopy(output)
    bad["groups"][0]["jd_quote"] = "Unrecorded duty"
    with pytest.raises(PortalDataError):
        create_job_brief(application, old, runner=model_runner(bad, calls))
    # A consistent record of that earlier prompt: its answer and rejection bind to it.
    earlier = "an earlier prompt"
    (old / "job-brief-prompt.json").write_text(json.dumps({"prompt": earlier}))
    saved = json.loads((old / "job-brief-result.json").read_text())
    saved["prompt_hash"] = sha256_digest(earlier.encode())
    (old / "job-brief-result.json").write_text(json.dumps(saved))
    marker = output_validation_marker(
        saved, earlier, old / "job-brief-schema.json", "job_brief_invalid"
    )
    (old / "validation-failure.json").write_text(json.dumps(marker))
    result = create_job_brief(
        application, tmp_path / "retry", runner=model_runner(output, calls), resume_from=old
    )
    assert result["business_object"] == "Pricing and risk decisions"
    assert len([call for call in calls if call[-1] != "--version"]) == 2


@pytest.mark.parametrize("invalid", ["schema", "semantic"])
def test_invalid_raw_brief_without_marker_is_checked_locally_before_a_later_retry(
    tmp_path, application, output, invalid
):
    calls = []
    old = tmp_path / "old"
    bad = {} if invalid == "schema" else deepcopy(output)
    if invalid == "semantic":
        bad["groups"][0]["jd_quote"] = "Unrecorded duty"
    with pytest.raises(PortalDataError):
        create_job_brief(application, old, runner=model_runner(bad, calls))
    (old / "validation-failure.json").unlink()
    before = {path.name: path.read_bytes() for path in old.iterdir()}
    checked = tmp_path / "checked"
    dispatched = []
    with pytest.raises(PortalDataError) as error:
        create_job_brief(
            application,
            checked,
            runner=model_runner(output, calls),
            resume_from=old,
            on_dispatch=lambda: dispatched.append(True),
        )
    assert error.value.code == "job_brief_invalid"
    assert dispatched == []
    assert (checked / "validation-failure.json").is_file()
    assert (checked / "job-brief-result.json").read_bytes() == before["job-brief-result.json"]
    assert {path.name: path.read_bytes() for path in old.iterdir()} == before
    result = create_job_brief(
        application,
        tmp_path / "retry",
        runner=model_runner(output, calls),
        resume_from=checked,
        on_dispatch=lambda: dispatched.append(True),
    )
    assert result["business_object"] == "Pricing and risk decisions"
    assert dispatched == [True]
    assert len([call for call in calls if call[-1] != "--version"]) == 2


@pytest.mark.parametrize("damaged", ["validation-failure.json", "job-brief-result.json"])
def test_invalid_brief_marker_cannot_authorize_retry_of_damaged_receipts(
    tmp_path, application, output, damaged
):
    calls = []
    old = tmp_path / "old"
    with pytest.raises(PortalDataError):
        create_job_brief(application, old, runner=model_runner({}, calls))
    (old / damaged).write_text("{}")
    with pytest.raises(PortalDataError) as error:
        create_job_brief(
            application, tmp_path / "new", runner=model_runner(output, calls), resume_from=old
        )
    assert error.value.code == "job_brief_invalid"
    assert len([call for call in calls if call[-1] != "--version"]) == 1
