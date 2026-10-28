"""Explicit known-author recovery preserves completed fragments and never loops."""

import json

import pytest
from test_application_flow import wait_for
from test_application_resume_author import author_output, response
from test_canonical_career_sources import canonical as canonical
from test_j08_flow_combination import json_flow as json_flow
from test_j08_flow_combination import start_json_writing
from test_pipeline_current_job import current_pipeline as current_pipeline
from test_pipeline_recommendation_queue import drive

from career_evidence_graph import application_experience_latex as generation
from career_evidence_graph.application_resume_author import execute_content_generation
from career_evidence_graph.career_portal_data import PortalDataError


def test_known_bad_second_author_retries_only_rejected_fragment(json_flow):
    case = json_flow
    task = start_json_writing(case)
    identifier = task["experience_handoff"]["id"]
    calls = []
    failed = False

    def runner(config, prompt, **kwargs):
        nonlocal failed
        request = json.loads(prompt.split("\n", 1)[1])
        role = request["role"]
        calls.append(role)
        if role.startswith("experience-") and len(calls) == 3 and not failed:
            failed = True
            return response({"invalid": "synthetic rejected fragment"})
        return response(author_output(request))

    with pytest.raises(PortalDataError) as rejected:
        execute_content_generation(case.store, identifier, runner=runner)
    assert rejected.value.code == "resume_author_failed"
    before = generation.generation_state(case.store, identifier)
    assert len(before["completed_experience_ids"]) == 1
    first_id = before["completed_experience_ids"][0]
    first_fragment = generation.writer_context(case.store, identifier, first_id)[
        "previous_fragment"
    ]
    with case.flow.applications.write_lock():
        state = case.flow._load()
        current = case.flow._task(state, task["id"])
        current["status"] = "failed"
        current["stages"]["resume"].update(status="failed", error_code="resume_author_failed")
        case.flow._save(state)
    case.flow.callbacks["resume"] = lambda request: execute_content_generation(
        case.store, identifier, runner=runner
    )
    current = case.flow.task_snapshot(task["id"])
    case.flow.start(task["id"], current["revision"], "resume", retry=True)
    done = wait_for(case.flow, task["id"], lambda row: row["status"] == "draft_ready")
    assert done["draft_id"] == identifier
    assert calls.count("plan") == calls.count("review") == 1
    assert len([role for role in calls if role.startswith("experience-")]) == 3
    assert (
        generation.writer_context(case.store, identifier, first_id)["previous_fragment"]
        == first_fragment
    )


def test_material_required_resumes_only_after_original_external_generation_adopted(json_flow):
    case = json_flow
    task = start_json_writing(case)
    identifier = task["experience_handoff"]["id"]
    with case.flow.applications.write_lock():
        state = case.flow._load()
        current = case.flow._task(state, task["id"])
        current["status"] = "failed"
        current["stages"]["resume"].update(
            status="failed", error_code="resume_author_material_required"
        )
        case.flow._save(state)
    current = case.flow.task_snapshot(task["id"])
    with pytest.raises(PortalDataError) as missing:
        case.flow.resume_experience_generation(task["id"], current["revision"], identifier)
    assert missing.value.code == "flow_generation_not_adopted"
    execute_content_generation(
        case.store,
        identifier,
        runner=lambda config, prompt, **kwargs: response(
            author_output(json.loads(prompt.split("\n", 1)[1]))
        ),
    )
    current = case.flow.task_snapshot(task["id"])
    case.flow.resume_experience_generation(task["id"], current["revision"], identifier)
    done = wait_for(case.flow, task["id"], lambda row: row["status"] == "draft_ready")
    assert done["draft_id"] == identifier


def test_pipeline_known_author_retry_is_armed_once_per_continue(current_pipeline, monkeypatch):
    pipeline, flow, _, _ = current_pipeline
    pipeline.start(request_id="known-author-recovery")
    state = drive(pipeline, "generating_resume")
    task = flow.tasks[state["active_task_id"]]
    task["status"] = "failed"
    task.setdefault("stages", {})["resume"] = {
        "status": "failed",
        "error_code": "resume_author_failed",
        "attempt_id": "original-attempt",
    }
    pipeline._tick()
    assert pipeline.snapshot()["wait_reason"] == "resume_author_input_required"
    calls = []

    def retry(identifier, revision, stage, *, retry=False, _continuation_request_id=None):
        assert retry and stage == "resume"
        assert _continuation_request_id in {"explicit-known-retry", "another-explicit-retry"}
        calls.append(identifier)
        task["stages"]["resume"]["attempt_id"] = f"failed-again-{len(calls)}"

    monkeypatch.setattr(flow, "start", retry)
    pipeline._tick()
    assert calls == []
    pipeline.continue_current(request_id="explicit-known-retry")
    pipeline._tick()
    assert calls == [task["id"]]
    pipeline._tick()
    assert pipeline.snapshot()["control"] == "paused"
    pipeline._tick()
    pipeline.continue_current(request_id="explicit-known-retry")
    pipeline._tick()
    assert calls == [task["id"]]
    pipeline.continue_current(request_id="another-explicit-retry")
    pipeline._tick()
    assert calls == [task["id"], task["id"]]
