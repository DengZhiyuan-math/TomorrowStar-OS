"""Flow owns effective qualifications and supplies material state to read clients."""

import pytest
from test_application_flow import application as application
from test_application_flow import wait_for
from test_job_explanations import requirement

from career_evidence_graph.application_flow import ApplicationFlowService, task_eligibility
from career_evidence_graph.career_portal_data import PortalDataError


def test_explicit_user_denial_overrides_supported_analysis_without_rewriting_it(
    application, tmp_path
):
    applications, job = application
    flow = ApplicationFlowService(
        applications,
        tmp_path / "flow",
        preparation_only=True,
        callbacks={
            "analysis": lambda _: {
                "id": "saved-analysis",
                "requirements": [requirement("Work permit", judgment="supported", hard=True)],
            },
            "resume": lambda _: pytest.fail("User denial must stop preparation"),
        },
    )
    try:
        task = flow.create(job["id"], job["revision"])
        flow.start(task["id"], task["revision"], "analysis")
        task = wait_for(flow, task["id"], lambda t: t["status"] == "analysis_ready")
        clarified = flow.clarify_condition(
            task["id"], task["revision"], 0, False, "The applicant explicitly denies this permit."
        )
        assert task_eligibility(clarified, bind_inputs=True)["status"] == "conflict"
        assert clarified["artifacts"][0]["result"]["requirements"][0]["judgment"] == ("supported")
        with pytest.raises(PortalDataError) as error:
            flow.start(clarified["id"], clarified["revision"], "resume")
        assert error.value.code == "flow_qualification_required"
    finally:
        flow.close()


def test_material_projection_is_derived_without_changing_task_state(application, tmp_path):
    applications, job = application
    flow = ApplicationFlowService(applications, tmp_path / "flow")
    try:
        task = flow.create(job["id"], job["revision"])
        before = flow.path.read_bytes()
        observed = flow.snapshot(task["id"])
        assert observed["local_materials"] is False
        assert "local_materials" not in observed["active_task"]
        assert observed["active_task"]["revision"] == task["revision"]
        assert flow.path.read_bytes() == before
    finally:
        flow.close()
