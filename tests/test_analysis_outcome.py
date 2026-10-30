"""The Flow owns analysis attempt certainty and a read-only recovery delivery."""

import pytest
from test_application_flow import application as application
from test_application_flow import wait_for

from career_evidence_graph.application_flow import ApplicationFlowService
from career_evidence_graph.career_portal_data import PortalDataError


@pytest.mark.parametrize(
    ("error_code", "certainty"),
    [
        ("match_model_invalid", "rejected"),
        ("match_requirement_conflict", "rejected"),
        ("match_source_invalid", "rejected"),
        ("match_attribution_invalid", "rejected"),
        ("match_inference_invalid", "rejected"),
        ("retrieval_invalid", "rejected"),
        ("job_brief_invalid", "rejected"),
        ("match_resume_invalid", "rejected"),
        ("retrieval_execution_incomplete", "unknown"),
        ("match_model_unavailable", "unknown"),
        ("match_timeout", "unknown"),
        ("match_result_needs_recheck", "unknown"),
        ("flow_stage_failed", "unknown"),
    ],
)
def test_modern_failed_analysis_delivers_certainty_without_retry(
    application, tmp_path, error_code, certainty
):
    applications, job = application
    calls = []

    def analyze(task):
        calls.append(task["id"])
        raise PortalDataError(error_code, "Synthetic retained analysis failure", 409)

    flow = ApplicationFlowService(applications, tmp_path / "flow", callbacks={"analysis": analyze})
    try:
        task = flow.create(job["id"], job["revision"])
        flow.start(task["id"], task["revision"], "analysis")
        task = wait_for(flow, task["id"], lambda row: row["status"] == "failed")
        before = flow.path.read_bytes()
        outcome = flow.analysis_outcome(task["id"])
        assert outcome == {
            "schema_version": "analysis-outcome/v1",
            "task_id": task["id"],
            "task_revision": task["revision"],
            "status": certainty,
            "error_code": error_code,
            "attempt_id": task["stages"]["analysis"]["attempt_id"],
            "recovery": "needs_input" if certainty == "rejected" else "needs_recheck",
            "legacy_skippable": False,
        }
        outcome["status"] = "mutated"
        assert flow.analysis_outcome(task["id"])["status"] == certainty
        assert flow.path.read_bytes() == before
        assert calls == [task["id"]]
    finally:
        flow.close()


@pytest.mark.parametrize(
    ("attempt_status", "certainty"), [("failed", "rejected"), ("needs_recheck", "unknown")]
)
def test_a_saved_size_refusal_is_rejected_only_when_its_attempt_proves_it(
    application, tmp_path, attempt_status, certainty
):
    applications, job = application

    def analyze(_task):
        raise PortalDataError("retrieval_execution_incomplete", "Synthetic reading failure", 409)

    class Attempts:
        def progress(self, attempt_id):
            return {"attempt_id": attempt_id, "status": attempt_status}

    flow = ApplicationFlowService(applications, tmp_path / "flow", callbacks={"analysis": analyze})
    try:
        task = flow.create(job["id"], job["revision"])
        flow.start(task["id"], task["revision"], "analysis")
        task = wait_for(flow, task["id"], lambda row: row["status"] == "failed")
        assert flow.analysis_outcome(task["id"])["status"] == "unknown"
        # The same code also wraps reader timeouts; only the saved attempt can
        # show that every reading call was receipted before the size refusal.
        flow.analysis = Attempts()
        assert flow.analysis_outcome(task["id"])["status"] == certainty
        assert flow.progress(task["id"])["analysis"]["status"] == certainty
    finally:
        flow.close()


@pytest.mark.parametrize(
    "modification",
    [
        "legacy",
        "retry",
        "adopted",
        "material",
        "uncertain",
        "invalid_metadata",
        "unknown_metadata",
        "invalid_retry",
        "handoff",
        "update",
    ],
)
def test_failure_delivery_separates_legacy_skip_and_unknown_outputs(
    application, tmp_path, modification
):
    applications, job = application
    flow = ApplicationFlowService(applications, tmp_path / "flow")
    try:
        task = flow.create(job["id"], job["revision"])
        with applications.write_lock():
            state = flow._load()
            current = flow._task(state, task["id"])
            current["status"] = "failed"
            stage = {
                "status": "failed",
                "error_code": "match_model_invalid",
                "attempt_id": "a" * 32,
            }
            if modification != "legacy":
                stage["analysis_input_revision"] = "b" * 64
            if modification == "retry":
                stage["resume_from_attempt_id"] = "c" * 32
            elif modification == "adopted":
                current["analysis_id"] = "retained-analysis"
                current["artifacts"] = [
                    {"stage": "analysis", "adopted": True, "result": {"id": "retained-analysis"}}
                ]
            elif modification == "material":
                current["worker_ref"] = {"batch_id": "retained-worker"}
            elif modification == "uncertain":
                stage["status"] = "needs_recheck"
            elif modification == "invalid_metadata":
                stage["analysis_input_revision"] = "unverified"
            elif modification == "invalid_retry":
                stage["resume_from_attempt_id"] = "unverified"
            elif modification == "unknown_metadata":
                stage["unverified_result"] = True
            elif modification == "handoff":
                current["codex_handoff_ref"] = {"task_id": "retained"}
            elif modification == "update":
                current["material_update"] = {"status": "needs_recheck"}
            current["stages"]["analysis"] = stage
            flow._save(state)
        before = flow.path.read_bytes()
        outcome = flow.analysis_outcome(task["id"])
        assert outcome["status"] == (
            "rejected" if modification in {"legacy", "retry"} else "unknown"
        )
        assert outcome["legacy_skippable"] is (modification == "legacy")
        assert flow.path.read_bytes() == before
    finally:
        flow.close()


def test_delivery_reads_task_without_snapshot_projection_or_provider(
    application, tmp_path, monkeypatch
):
    applications, job = application
    calls = []
    flow = ApplicationFlowService(applications, tmp_path / "flow")
    try:
        task = flow.create(job["id"], job["revision"])
        monkeypatch.setattr(
            flow, "snapshot", lambda *_: pytest.fail("Outcome must not project the full Flow")
        )
        flow.information_provider = lambda: calls.append("information")
        flow.source_provider = lambda *_: calls.append("source")
        before = flow.path.read_bytes()
        outcome = flow.analysis_outcome(task["id"])
        assert outcome["status"] == "pending"
        assert outcome["recovery"] == "wait"
        assert outcome["task_revision"] == task["revision"]
        assert calls == []
        assert flow.path.read_bytes() == before
        with pytest.raises(PortalDataError) as error:
            flow.analysis_outcome("missing")
        assert error.value.code == "flow_not_found"
    finally:
        flow.close()


def test_running_and_ready_are_saved_attempt_outcomes(application, tmp_path):
    from threading import Event

    applications, job = application
    entered, release = Event(), Event()
    calls = []

    def analyze(task):
        calls.append(task["id"])
        entered.set()
        assert release.wait(3)
        return {"id": "delivered-analysis", "requirements": []}

    flow = ApplicationFlowService(applications, tmp_path / "flow", callbacks={"analysis": analyze})
    try:
        task = flow.create(job["id"], job["revision"])
        flow.start(task["id"], task["revision"], "analysis")
        assert entered.wait(3)
        before = flow.path.read_bytes()
        running = flow.analysis_outcome(task["id"])
        assert running["status"] == "running"
        assert running["recovery"] == "wait"
        assert running["attempt_id"]
        assert flow.path.read_bytes() == before
        release.set()
        task = wait_for(flow, task["id"], lambda row: row["status"] == "analysis_ready")
        before = flow.path.read_bytes()
        ready = flow.analysis_outcome(task["id"])
        assert ready["status"] == "ready" and ready["recovery"] == "continue"
        assert ready["task_revision"] == task["revision"]
        assert ready["attempt_id"] == running["attempt_id"]
        assert calls == [task["id"]]
        assert flow.path.read_bytes() == before
    finally:
        release.set()
        flow.close()


def test_ready_without_adopted_delivery_is_unknown(application, tmp_path):
    applications, job = application
    flow = ApplicationFlowService(applications, tmp_path / "flow")
    try:
        task = flow.create(job["id"], job["revision"])
        with applications.write_lock():
            state = flow._load()
            current = flow._task(state, task["id"])
            current["status"] = "analysis_ready"
            current["stages"]["analysis"] = {"status": "complete", "artifact_id": "absent"}
            flow._save(state)
        before = flow.path.read_bytes()
        outcome = flow.analysis_outcome(task["id"])
        assert outcome["status"] == "unknown" and outcome["recovery"] == "needs_recheck"
        assert flow.path.read_bytes() == before
    finally:
        flow.close()
