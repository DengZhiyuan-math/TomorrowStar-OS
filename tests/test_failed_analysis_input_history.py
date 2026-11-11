"""Input refresh preserves failed analysis evidence before replacing its binding."""

from copy import deepcopy

import pytest
from test_application_flow import application as application
from test_application_flow import wait_for

from career_evidence_graph.application_flow import ApplicationFlowService
from career_evidence_graph.career_portal_data import PortalDataError


def test_changed_inputs_retain_failed_analysis_with_original_job_and_source_binding(
    application, tmp_path
):
    applications, job = application
    calls = []

    def analyze(task):
        calls.append(deepcopy(task))
        raise PortalDataError("match_model_invalid", "Synthetic failed analysis")

    flow = ApplicationFlowService(applications, tmp_path / "flow", callbacks={"analysis": analyze})
    try:
        task = flow.create(job["id"], job["revision"], inputs={"sources_revision": "sources-v1"})
        flow.start(task["id"], task["revision"], "analysis")
        failed = wait_for(flow, task["id"], lambda row: row["status"] == "failed")
        changed_job = applications.update_application(
            job["id"], {"job_description": "Review reliable Python systems."}, job["revision"]
        )

        updated = flow.update_inputs(
            failed["id"],
            failed["revision"],
            changed_job["revision"],
            {"sources_revision": "sources-v2"},
        )

        assert updated["stages"]["analysis"] == {"status": "pending"}
        assert updated["analysis_attempts"] == [
            {
                "stage": failed["stages"]["analysis"],
                "inputs": failed["inputs"],
                "job_binding": failed["job_binding"],
            }
        ]
        assert updated["job_binding"] != failed["job_binding"]
        assert updated["inputs"] == {"sources_revision": "sources-v2"}
        assert len(calls) == 1
        history = deepcopy(updated["analysis_attempts"])
        for source_revision in ("sources-v2", "sources-v3"):
            updated = flow.update_inputs(
                updated["id"],
                updated["revision"],
                changed_job["revision"],
                {"sources_revision": source_revision},
            )
            assert updated["analysis_attempts"] == history
        flow.start(updated["id"], updated["revision"], "analysis")
        latest = wait_for(flow, updated["id"], lambda row: row["status"] == "failed")
        assert "resume_from_attempt_id" not in calls[-1]["stages"]["analysis"]
        assert latest["analysis_attempts"] == history
    finally:
        flow.close()


def test_unchanged_failed_analysis_retains_retry_guard_and_archives_once_on_retry(
    application, tmp_path
):
    applications, job = application
    calls = []

    def analyze(task):
        calls.append(deepcopy(task))
        raise PortalDataError("match_model_invalid", "Synthetic failed analysis")

    flow = ApplicationFlowService(applications, tmp_path / "flow", callbacks={"analysis": analyze})
    try:
        task = flow.create(job["id"], job["revision"], inputs={"sources_revision": "sources-v1"})
        flow.start(task["id"], task["revision"], "analysis")
        failed = wait_for(flow, task["id"], lambda row: row["status"] == "failed")
        updated = flow.update_inputs(
            failed["id"], failed["revision"], job["revision"], failed["inputs"]
        )
        assert updated["stages"]["analysis"] == failed["stages"]["analysis"]
        assert updated.get("analysis_attempts", []) == []
        assert len(calls) == 1
        with pytest.raises(PortalDataError) as caught:
            flow.start(updated["id"], updated["revision"], "analysis")
        assert caught.value.code == "flow_retry_required"
        flow.start(updated["id"], updated["revision"], "analysis", retry=True)
        retried = wait_for(flow, updated["id"], lambda row: row["status"] == "failed")
        assert (
            calls[-1]["stages"]["analysis"]["resume_from_attempt_id"]
            == (failed["stages"]["analysis"]["attempt_id"])
        )
        assert retried["analysis_attempts"] == [
            {
                "stage": failed["stages"]["analysis"],
                "inputs": failed["inputs"],
                "job_binding": failed["job_binding"],
            }
        ]
    finally:
        flow.close()
