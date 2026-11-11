"""One Continue resumes the same job after a TeX factual conflict is corrected."""

from copy import deepcopy

import pytest
from test_pipeline_recommendation_queue import drive
from test_pipeline_recommendation_queue import queue_environment as queue_environment

from career_evidence_graph.application_flow import job_input_revision
from career_evidence_graph.career_portal_data import PortalDataError


@pytest.mark.parametrize("conflict_stage", ["resume", "export"])
@pytest.mark.parametrize("reanalysis_required", [False, True])
def test_tex_fact_wait_and_one_continue_resume_only_the_current_job(
    queue_environment, monkeypatch, conflict_stage, reanalysis_required
):
    pipeline, flow, _intake, worker, _reads, fetches, _messages = queue_environment
    original_create, original_start = flow.create, flow.start
    material_attempts, updates = [], []
    correction = {"facts_revision": "initial", "resolved": False}

    def create(identifier, revision):
        task = original_create(identifier, revision)
        flow.tasks[identifier]["stages"] = {
            stage: {"status": "pending"} for stage in ("analysis", "resume", "export")
        }
        return flow.snapshot(task["id"])["active_task"]

    def start(identifier, revision, stage):
        if stage in {"resume", "export"}:
            material_attempts.append(stage)
            if stage == conflict_stage and not correction["resolved"]:
                raise PortalDataError(
                    "resume_group_verification_required",
                    "Synthetic TeX contribution responsibility conflict",
                    409,
                )
        return original_start(identifier, revision, stage)

    def update_inputs(identifier, revision, application_revision):
        task = flow.tasks[identifier]
        application = flow.applications.get_application(identifier)
        assert revision == task["revision"]
        assert application_revision == application["revision"]
        updates.append((identifier, application_revision, correction["facts_revision"]))
        task["inputs"] = {
            "jd_revision": job_input_revision(application),
            "facts_revision": correction["facts_revision"],
        }
        task["job_binding"] = job_input_revision(application)
        task["revision"] += "u"
        if reanalysis_required:
            task.update(status="draft", analysis_id=None)
        return deepcopy(task)

    monkeypatch.setattr(flow, "create", create)
    monkeypatch.setattr(flow, "start", start)
    monkeypatch.setattr(flow, "update_inputs", update_inputs, raising=False)
    pipeline.start(request_id="tex-conflict")
    waiting = drive(pipeline, "needs_input")
    identifier = waiting["active_task_id"]
    assert waiting["control"] == "paused"
    assert waiting["wait_reason"] == "material_facts_required"
    assert waiting["resume_status"] == "generating_resume"
    assert waiting["can_resume_matching"] is True
    assert flow.tasks[identifier]["status"] == (
        "analysis_ready" if conflict_stage == "resume" else "draft_ready"
    )
    assert worker.snapshot()["jobs"] == []
    assert len(flow.tasks) == 1 and len(fetches) == 1
    assert not any(name == "prepare" for name, _ in flow.calls)
    assert len(waiting["pending_recommendations"]) == 15

    before = deepcopy(flow.calls), list(material_attempts)
    for _ in range(3):
        pipeline._tick()
    assert (flow.calls, material_attempts) == before
    assert pipeline.snapshot()["status"] == "needs_input"

    # A real saved JD correction requires fresh analysis. A manual TeX-only
    # correction retains its analysis and goes directly to the remaining stage.
    application = flow.applications.get_application(identifier)
    if reanalysis_required:
        application = flow.applications.update_application(
            identifier,
            {"job_description": application["job_description"] + " Verify delivery ownership."},
            application["revision"],
        )
    correction.update(facts_revision="corrected", resolved=True)
    resumed = pipeline.continue_current(request_id="tex-facts-corrected")
    assert resumed["active_task_id"] == identifier
    assert resumed["status"] == ("matching" if reanalysis_required else "generating_resume")
    assert resumed["control"] == "running"
    assert "wait_reason" not in resumed
    assert updates == [(identifier, application["revision"], "corrected")]
    assert flow.tasks[identifier]["inputs"]["facts_revision"] == "corrected"

    calls_after_continue = deepcopy(flow.calls), list(material_attempts), list(updates)
    assert pipeline.continue_current(request_id="tex-facts-corrected") == resumed
    assert (flow.calls, material_attempts, updates) == calls_after_continue
    filling = drive(pipeline, "filling")
    assert filling["active_task_id"] == identifier
    assert filling["current_recommendation_id"] == waiting["current_recommendation_id"]
    assert len(flow.tasks) == 1 and len(fetches) == 1
    assert len(filling["pending_recommendations"]) == 15
    assert [name for name, _ in flow.calls].count("analysis") == (2 if reanalysis_required else 1)
    assert [name for name, _ in flow.calls].count("prepare") == 1
    assert material_attempts.count(conflict_stage) == 2
    assert worker.snapshot()["jobs"][0]["application_id"] == identifier
    assert worker.snapshot()["jobs"][0]["status"] == "filling"

    before_duplicate = deepcopy(flow.calls), list(material_attempts), list(updates)
    pipeline.continue_current(request_id="tex-facts-corrected")
    assert (flow.calls, material_attempts, updates) == before_duplicate
