"""A default sequential queue never treats an analysis failure as a next-job decision."""

import json
import subprocess
import threading
import time

import pytest
from test_application_intake import message, page
from test_application_material_packet import long_text, snapshot
from test_application_pipeline import Worker
from test_pipeline_recommendation_queue import queue_environment as queue_environment

from career_evidence_graph.application_flow import ApplicationFlowService
from career_evidence_graph.application_intake import ApplicationIntakeService
from career_evidence_graph.application_material_packet import prepare_material_packet
from career_evidence_graph.application_pipeline import ApplicationPipeline
from career_evidence_graph.career_portal_data import ApplicationStore, PortalDataError
from career_evidence_graph.codex_cli import CodexCLIError


@pytest.mark.parametrize(
    ("error_code", "expected_status"),
    [
        ("match_model_invalid", "needs_input"),
        ("match_result_needs_recheck", "needs_recheck"),
        ("reader_cli_timeout", "needs_recheck"),
        ("reader_subprocess_timeout", "needs_recheck"),
    ],
)
def test_default_queue_holds_modern_failed_analysis_without_retry_or_next_job(
    tmp_path, error_code, expected_status
):
    (tmp_path / "applications").mkdir()
    applications = ApplicationStore(tmp_path / "applications")
    fetched, analysis_calls, reader_calls, selections = [], [], [], []
    reader_timeout = error_code.startswith("reader_")
    stage_error = "retrieval_execution_incomplete" if reader_timeout else error_code

    def timed_out_reader(*_args, **_kwargs):
        reader_calls.append(error_code)
        if error_code == "reader_cli_timeout":
            raise CodexCLIError("Codex CLI timed out")
        raise subprocess.TimeoutExpired("synthetic-reader", 180)

    def reader(_directory, **_options):
        return {
            "status": "readable",
            "emails": [
                message("first", ["https://www.linkedin.com/jobs/view/10000"]),
                message("second", ["https://www.linkedin.com/jobs/view/10001"]),
            ],
            "provenance": {},
        }

    def fetcher(url):
        fetched.append(url)
        return page(url) | {
            "job_fields": {
                "title": "Systems Engineer",
                "company": "Synthetic Employer",
                "location": "Zurich, Switzerland",
            }
        }

    def analyze(task):
        analysis_calls.append(task["id"])
        if reader_timeout:
            return prepare_material_packet(
                applications.get_application(task["application_id"]),
                snapshot(long_text()),
                tmp_path / "reader-attempt",
                runner=timed_out_reader,
                requirements=[
                    {"text": "Validate risk", "importance": "required", "hard_condition": False}
                ],
            )
        raise PortalDataError(error_code, "Saved failed or unknown analysis", 409)

    intake = ApplicationIntakeService(
        applications, tmp_path / "intake", reader=reader, fetcher=fetcher
    )
    select = intake.select

    def observe_select(*args):
        selections.append(args)
        return select(*args)

    intake.select = observe_select
    flow = ApplicationFlowService(applications, tmp_path / "flow", callbacks={"analysis": analyze})
    pipeline = ApplicationPipeline(flow, intake, Worker(), interval=0.01)
    try:
        pipeline.start(request_id="default-current-job")
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            state = pipeline.snapshot()
            if state["control"] == "paused" and state["status"] == expected_status:
                break
            threading.Event().wait(0.01)
        else:
            pytest.fail("The current failed analysis was not retained")
        task = flow.snapshot()["active_task"]
        assert task["stages"]["analysis"]["error_code"] == stage_error
        if reader_timeout:
            packet = json.loads((tmp_path / "reader-attempt/material-packet.json").read_text())
            assert packet["status"] == "failed"
            assert "pending_call" not in packet
            assert reader_calls == [error_code]
        assert task["stages"]["analysis"]["analysis_input_revision"]
        assert state["active_task_id"] == task["id"]
        assert state["wait_reason"] == (
            "analysis_input_required"
            if expected_status == "needs_input"
            else "analysis_result_unknown"
        )
        outcome = flow.analysis_outcome(task["id"])
        assert outcome["status"] == ("rejected" if expected_status == "needs_input" else "unknown")
        assert outcome["recovery"] == expected_status
        assert outcome["legacy_skippable"] is False
        current = state["current_recommendation_id"]
        threading.Event().wait(0.05)
        assert pipeline.snapshot()["current_recommendation_id"] == current
        assert len(flow.snapshot()["tasks"]) == len(analysis_calls) == 1
        assert fetched == ["https://www.linkedin.com/jobs/view/10000"]
        assert len(applications.list_applications()) == 1
        # Continue retries a known rejected output once (installed MC-11: a pipeline
        # job had no other retry); it cannot guess that an unknown result allows one.
        retried = expected_status == "needs_input"
        pipeline.continue_current(request_id="observe-retained-failure")
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            resumed = pipeline.snapshot()
            if resumed["control"] == "paused":
                break
            threading.Event().wait(0.01)
        assert resumed["status"] == expected_status
        assert resumed["current_recommendation_id"] == current
        assert len(flow.snapshot()["tasks"]) == 1
        assert len(analysis_calls) == (2 if retried else 1)
        attempts = flow.snapshot()["active_task"].get("analysis_attempts", [])
        assert len(attempts) == (1 if retried else 0)
        assert fetched == ["https://www.linkedin.com/jobs/view/10000"]
        assert len(selections) == 1
        assert reader_calls == ([error_code] if reader_timeout else [])
    finally:
        pipeline.close()
        flow.close()
        intake.close()


def test_default_queue_keeps_legacy_rejection_on_same_job_and_resumes_only_delivered_repair(
    queue_environment,
):
    from copy import deepcopy

    from test_application_pipeline import fail_analysis
    from test_pipeline_recommendation_queue import drive

    pipeline, flow, intake, _worker, _reads, fetched, _messages = queue_environment
    original_start = flow.start
    failures = set()
    fail_analysis(flow, failures)
    # Jobs arrive after capture, so reject every first analysis in this Adapter.
    failure = flow.start

    def fail_first(identifier, revision, stage):
        failures.add(identifier)
        return failure(identifier, revision, stage)

    flow.start = fail_first
    pipeline.start(request_id="legacy-record-default-mode")
    waiting = drive(pipeline, "needs_input")
    task_id = waiting["active_task_id"]
    current = waiting["current_recommendation_id"]
    assert flow.analysis_outcome(task_id)["legacy_skippable"] is True
    assert waiting["items"][0]["status"] == "matching"
    before = deepcopy(flow.calls)
    selected = []
    select = intake.select

    def observe_select(*args):
        selected.append(args)
        return select(*args)

    intake.select = observe_select
    for request_id in ("unchanged-once", "unchanged-twice"):
        retained = pipeline.continue_current(request_id=request_id)
        pipeline._tick()
        assert retained["status"] == "needs_input"
        assert retained["current_recommendation_id"] == current
    assert flow.calls == before
    assert selected == []
    assert fetched == ["https://www.linkedin.com/jobs/view/10000"]
    assert len(flow.tasks) == 1
    # A separate explicit repair produces a delivered result. Continue observes
    # that result and does not initiate another analysis itself.
    original_start(task_id, flow.tasks[task_id]["revision"], "analysis")
    repaired = flow.analysis_outcome(task_id)
    assert repaired["status"] == "ready"
    calls_after_repair = deepcopy(flow.calls)
    resumed = pipeline.continue_current(request_id="adopt-explicit-repair")
    assert resumed["status"] == "matching" and resumed["control"] == "running"
    pipeline._tick()
    assert pipeline.snapshot()["items"][0]["status"] == "matched"
    assert flow.calls == calls_after_repair
    assert pipeline.snapshot()["current_recommendation_id"] == current
    assert selected == []


def test_default_queue_waits_for_matching_outcome_task_revision(queue_environment):
    from test_pipeline_recommendation_queue import drive

    pipeline, flow, _intake, _worker, _reads, fetched, _messages = queue_environment
    observed = flow.analysis_outcome

    def previous_outcome(task_id):
        return observed(task_id) | {"task_revision": "previous-revision"}

    flow.analysis_outcome = previous_outcome
    pipeline.start(request_id="revision-bound-outcome")
    drive(pipeline, "matching")
    pipeline._tick()
    assert len(flow.tasks) == 1
    assert not any(stage == "analysis" for stage, _ in flow.calls)
    assert fetched == ["https://www.linkedin.com/jobs/view/10000"]
    flow.analysis_outcome = observed
    pipeline._tick()
    assert sum(stage == "analysis" for stage, _ in flow.calls) == 1


def test_continue_retries_rejected_analysis_after_an_app_update_changed_its_configuration(
    tmp_path,
):
    (tmp_path / "applications").mkdir()
    applications = ApplicationStore(tmp_path / "applications")
    inputs = {"analysis_configuration_revision": "before-update"}
    analysis_calls = []

    def reader(_directory, **_options):
        return {
            "status": "readable",
            "emails": [message("first", ["https://www.linkedin.com/jobs/view/10000"])],
            "provenance": {},
        }

    def analyze(task):
        analysis_calls.append(task["inputs"]["analysis_configuration_revision"])
        raise PortalDataError("job_brief_invalid", "Saved rejected analysis", 409)

    intake = ApplicationIntakeService(
        applications,
        tmp_path / "intake",
        reader=reader,
        fetcher=lambda url: page(url) | {"job_fields": {"title": "Engineer", "company": "Co"}},
    )
    flow = ApplicationFlowService(
        applications,
        tmp_path / "flow",
        input_provider=lambda identifier: {
            "application_revision": applications.get_application(identifier)["revision"],
            "inputs": dict(inputs),
        },
        callbacks={"analysis": analyze},
    )
    pipeline = ApplicationPipeline(flow, intake, Worker(), interval=0.01)

    def paused(after):
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            state = pipeline.snapshot()
            if state["control"] == "paused" and len(analysis_calls) >= after:
                return state
            threading.Event().wait(0.01)
        pytest.fail("The rejected analysis was not retained")

    try:
        pipeline.start(request_id="first-run")
        assert paused(1)["wait_reason"] == "analysis_input_required"
        # Installed MC-11: the update changed the engine hash inside the analysis
        # configuration, so the old task looked stale and Continue never retried.
        inputs["analysis_configuration_revision"] = "after-update"
        pipeline.continue_current(request_id="retry-after-update")
        state = paused(2)
        assert analysis_calls == ["before-update", "after-update"]
        assert state["wait_reason"] == "analysis_input_required"
        assert len(flow.snapshot()["tasks"]) == 1
        assert len(flow.snapshot()["active_task"]["analysis_attempts"]) == 1
    finally:
        pipeline.close()
        flow.close()
        intake.close()
