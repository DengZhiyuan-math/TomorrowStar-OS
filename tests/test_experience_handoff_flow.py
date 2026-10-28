"""Codex handoffs wait durably and rejoin the existing material stage."""

from copy import deepcopy
from types import SimpleNamespace

import pytest
from test_application_flow import application as application
from test_application_flow import wait_for
from test_full_latex_flow import bind, candidate
from test_full_latex_flow import latex_flow as latex_flow

from career_evidence_graph.application_pipeline import ApplicationPipeline
from career_evidence_graph.career_portal_data import PortalDataError


def handoff(task):
    return {
        "id": "generation-1",
        "kind": "experience_handoff",
        "status": "codex_required",
        "application_id": task["application_id"],
        "analysis_binding": {"analysis_id": task["analysis_id"]},
        "experiences": [{"experience_id": "exp-synthetic", "title": "Synthetic project"}],
    }


def begin(data):
    service, task, project = data
    task = bind(service, task, project)
    service.start(task["id"], task["revision"], "resume")
    return wait_for(service, task["id"], lambda row: row["status"] in {"needs_input", "failed"})


def test_handoff_retains_base_and_waits_without_draft_or_pdf_fingerprints(latex_flow):
    service, _, project = latex_flow
    calls = []
    service.callbacks["resume"] = lambda task: calls.append(task["id"]) or handoff(task)
    original = (project / "main.tex").read_bytes()
    task = begin(latex_flow)
    assert task["status"] == "needs_input"
    assert task["stages"]["resume"]["status"] == "pending"
    assert task["stages"]["resume"]["generation_id"] == "generation-1"
    assert task["experience_handoff"]["kind"] == "experience_handoff"
    assert task["draft_id"] is None and task["resume_id"] is None
    assert task["artifacts"][-1]["adopted"] is False
    assert service.snapshot(task["id"])["experience_generation"]["id"] == "generation-1"
    assert calls == [task["id"]]
    assert (project / "main.tex").read_bytes() == original


def test_progress_reads_live_state_and_only_adopted_generation_resumes(latex_flow):
    service, _, _ = latex_flow
    calls = []

    def generate(task):
        calls.append(task["id"])
        return handoff(task) if len(calls) == 1 else candidate(task)

    service.callbacks["resume"] = generate
    task = begin(latex_flow)
    progress = deepcopy(task["experience_handoff"])
    service.callbacks["experience_generation"] = lambda _: progress
    request = {
        "task_id": task["id"],
        "task_revision": task["revision"],
        "generation_id": "generation-1",
    }
    with pytest.raises(PortalDataError, match="Codex") as error:
        service.request("resume-experience-generation", request)
    assert error.value.code == "flow_generation_not_adopted"
    progress["status"] = "review_required"
    assert service.snapshot(task["id"])["experience_generation"]["status"] == "review_required"
    # Reading live generation progress must not change the persisted task revision.
    assert service.snapshot(task["id"])["active_task"]["revision"] == task["revision"]
    progress["status"] = "adopted"
    service.request("resume-experience-generation", request)
    task = wait_for(service, task["id"], lambda row: row["status"] == "draft_ready")
    assert task["draft_id"] == "d"
    assert "experience_handoff" not in task
    assert len(calls) == 2
    assert task["automatic_materials"] is True
    assert task["stages"]["export"]["status"] == "pending"
    checked = []
    service.verify_prism_source = lambda _: None
    service.callbacks["verify_draft"] = lambda current: checked.append(current["draft_id"])
    # The internally reviewed generation uses the existing automatic export gate.
    # No legacy user group-review receipt is required.
    service._reviewed_draft(task)
    assert checked == ["d"]


def test_resume_rejects_other_generation_without_dispatch(latex_flow):
    service, _, _ = latex_flow
    service.callbacks["resume"] = handoff
    task = begin(latex_flow)
    with pytest.raises(PortalDataError) as error:
        service.request(
            "resume-experience-generation",
            {
                "task_id": task["id"],
                "task_revision": task["revision"],
                "generation_id": "other-generation",
            },
        )
    assert error.value.code == "flow_generation_mismatch"
    assert service.snapshot(task["id"])["active_task"]["revision"] == task["revision"]


def test_pipeline_keeps_same_job_running_without_redispatch_or_user_approval(latex_flow):
    service, _, _ = latex_flow
    calls = []
    service.callbacks["resume"] = lambda task: calls.append(task["id"]) or handoff(task)
    task = begin(latex_flow)
    before = service.path.read_bytes()
    writes = []
    owner = SimpleNamespace(
        flow=service,
        _task=lambda state: service.progress(state["active_task_id"])["task"],
        _save=lambda state: writes.append(deepcopy(state)),
        _stop=lambda *args: pytest.fail("The existing handoff needs no new stop or approval"),
    )
    state = {"control": "running", "status": "generating_resume", "active_task_id": task["id"]}
    ApplicationPipeline._materials(owner, state)
    ApplicationPipeline._materials(owner, state)
    assert state == {
        "control": "running",
        "status": "generating_resume",
        "active_task_id": task["id"],
        "wait_reason": "codex_resume_required",
    }
    assert len(writes) == 1
    assert calls == [task["id"]]
    assert service.path.read_bytes() == before
    assert service.progress(task["id"])["task"]["experience_handoff"] == task["experience_handoff"]
