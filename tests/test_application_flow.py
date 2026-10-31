"""Single-job stages retain private state without replaying provider work."""

import os
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

from career_evidence_graph.application_flow import ApplicationFlowService, task_eligibility
from career_evidence_graph.career_portal_data import ApplicationStore, PortalDataError


@pytest.fixture
def application(tmp_path):
    directory = tmp_path / "applications"
    directory.mkdir()
    applications = ApplicationStore(directory)
    job = applications.create_application(
        {
            "company": "Synthetic Employer",
            "role_title": "ML Engineer",
            "job_description": "Build reliable Python systems.",
        }
    )
    return applications, job


def wait_for(service, task_id, predicate):
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline:
        task = service.snapshot(task_id)["active_task"]
        if predicate(task):
            return task
        time.sleep(0.01)
    pytest.fail("Background stage did not reach the expected state")


def test_cancelled_preparation_duplicate_allows_original_to_continue_without_replay(
    application, tmp_path
):
    from test_job_explanations import requirement

    applications, job = application
    calls = []
    flow = ApplicationFlowService(
        applications,
        tmp_path / "flow",
        preparation_only=True,
        callbacks={
            "analysis": lambda task: (
                calls.append(("analysis", task["id"]))
                or {"id": "analysis-v1", "requirements": [requirement()]}
            ),
            "resume": lambda task: (
                calls.append(("resume", task["id"]))
                or {"id": "draft-v1", "kind": "draft", "draft_sha256": "a" * 64}
            ),
        },
    )
    try:
        original = flow.create(job["id"], job["revision"])
        flow.start(original["id"], original["revision"], "analysis")
        original = wait_for(flow, original["id"], lambda row: row["status"] == "analysis_ready")
        duplicate = flow.create(job["id"], job["revision"], force_new=True)
        cancelled = flow.cancel(duplicate["id"], duplicate["revision"])
        before = flow.snapshot()
        assert before["active_task"] == original
        assert before["explanations"][0]["task_id"] == original["id"]
        assert flow.create(job["id"], job["revision"]) == original
        assert flow.snapshot() == before
        resumed = flow.start(original["id"], original["revision"], "analysis")
        assert resumed == original
        assert flow.snapshot() == before
        assert flow.snapshot(duplicate["id"])["active_task"] == cancelled
        assert calls == [("analysis", original["id"])]
        with pytest.raises(PortalDataError) as error:
            flow.start(cancelled["id"], cancelled["revision"], "analysis")
        assert error.value.code == "flow_cancelled"
        flow.start(original["id"], original["revision"], "resume")
        continued = wait_for(flow, original["id"], lambda row: row["status"] == "draft_ready")
        assert continued["analysis_id"] == original["analysis_id"]
        assert continued["artifacts"][: len(original["artifacts"])] == original["artifacts"]
        assert flow.snapshot(duplicate["id"])["active_task"] == cancelled
        assert calls == [("analysis", original["id"]), ("resume", original["id"])]
    finally:
        flow.close()


@pytest.mark.parametrize(
    "blocker",
    [
        "draft",
        "needs_recheck",
        "cancelled_unknown_stage",
        "cancelled_running_stage",
        "cancelled_export_recovery",
        "cancelled_group",
        "cancelled_worker",
        "cancelled_worker_ref",
        "cancelled_material_update",
        "cancelled_material_binding",
    ],
)
def test_newer_live_or_unresolved_preparation_task_still_blocks_original(
    application, tmp_path, blocker
):
    applications, job = application
    calls = []
    flow = ApplicationFlowService(
        applications,
        tmp_path / "flow",
        preparation_only=True,
        callbacks={"analysis": lambda task: calls.append(task["id"]) or {"id": "unexpected"}},
    )
    try:
        original = flow.create(job["id"], job["revision"])
        duplicate = flow.create(job["id"], job["revision"], force_new=True)
        with applications.write_lock():
            state = flow._load()
            row = flow._task(state, duplicate["id"])
            row["status"] = "cancelled" if blocker.startswith("cancelled_") else blocker
            if blocker == "cancelled_unknown_stage":
                row["stages"]["resume"]["status"] = "needs_recheck"
            elif blocker == "cancelled_running_stage":
                row["stages"]["resume"]["status"] = "running"
            elif blocker == "cancelled_export_recovery":
                row["export_recoveries"] = [
                    {
                        "status": "needs_recheck",
                        "operation_kind": "reuse_completed_review",
                        "prior_export_stage": {"status": "needs_recheck"},
                    }
                ]
            elif blocker == "cancelled_group":
                row["group_read"] = {"status": "needs_recheck"}
            elif blocker == "cancelled_worker":
                row["worker_preparation"] = {"status": "pending"}
            elif blocker == "cancelled_worker_ref":
                row["worker_ref"] = {"batch_id": "batch-v1", "job_id": job["id"]}
                row["worker_preparation"] = {"status": "complete"}
            elif blocker == "cancelled_material_update":
                row["material_update"] = {"status": "needs_recheck"}
            elif blocker == "cancelled_material_binding":
                row["material_binding_error"] = "flow_materials_changed"
            flow._save(state)
        before = flow.snapshot()
        with pytest.raises(PortalDataError) as error:
            flow._fresh(original, stage="analysis")
        assert error.value.code == "flow_inputs_stale"
        with pytest.raises(PortalDataError) as error:
            flow.start(original["id"], original["revision"], "analysis")
        assert error.value.code in {"flow_inputs_stale", "flow_batch_recheck_required"}
        assert flow.snapshot() == before
        assert calls == []
        if blocker.startswith("cancelled_"):
            with pytest.raises(PortalDataError):
                flow.create(job["id"], job["revision"])
            assert flow.snapshot() == before
    finally:
        flow.close()


@pytest.mark.parametrize("preparation_only", [False, True])
def test_default_task_projection_retains_all_cancelled_history(
    application, tmp_path, preparation_only
):
    applications, job = application
    flow = ApplicationFlowService(
        applications, tmp_path / "flow", preparation_only=preparation_only
    )
    try:
        original = flow.create(job["id"], job["revision"])
        duplicate = flow.create(job["id"], job["revision"], force_new=True)
        cancelled = flow.cancel(duplicate["id"], duplicate["revision"])
        assert flow.snapshot()["active_task"]["id"] == (
            original["id"] if preparation_only else cancelled["id"]
        )
        flow.cancel(original["id"], original["revision"])
        saved = flow.snapshot()
        assert saved["active_task"] == cancelled
        assert len(saved["tasks"]) == 2
        assert all(row["status"] == "cancelled" for row in saved["tasks"])
        if preparation_only:
            assert saved["explanations"][0]["task_id"] == cancelled["id"]
            successor = flow.create(job["id"], job["revision"])
            assert successor["id"] not in {original["id"], cancelled["id"]}
            assert len(flow.snapshot()["tasks"]) == 3
    finally:
        flow.close()


@pytest.mark.parametrize("failure", [None, "country", "verification", "save"])
def test_prepare_binds_current_pdf_automatically_without_claiming_human_review(
    application, tmp_path, monkeypatch, failure
):
    applications, original = application
    job = applications.update_application(
        original["id"], {"url": "https://example.com/jobs/synthetic"}, original["revision"]
    )
    prepared, verified = [], []

    def verify(task):
        verified.append(task["resume_sha256"])
        if failure == "verification":
            raise PortalDataError("flow_materials_changed", "Changed PDF", 409)

    service = ApplicationFlowService(
        applications,
        tmp_path / "flow",
        callbacks={
            "analysis": lambda _: {"id": "analysis-v1", "requirements": []},
            "resume": lambda _: {"id": "resume-v1", "pdf_sha256": "a" * 64},
            "verify_materials": verify,
            "prepare_worker": lambda task, country: (
                prepared.append(task)
                or {"batch_id": "batch-v1", "job_id": job["id"], "status": "queued"}
            ),
        },
    )
    try:
        task = service.create(job["id"], job["revision"])
        service.start(task["id"], task["revision"], "analysis")
        task = wait_for(service, task["id"], lambda row: row["status"] == "analysis_ready")
        service.start(task["id"], task["revision"], "resume")
        task = wait_for(service, task["id"], lambda row: row["status"] == "resume_ready")
        if failure == "save":

            def fail_save(_):
                raise OSError("Synthetic persistence failure")

            monkeypatch.setattr(service, "_save", fail_save)
        if failure:
            with pytest.raises((PortalDataError, OSError)):
                service.prepare_worker(
                    task["id"], task["revision"], "" if failure == "country" else "CHE", True
                )
            saved = service.snapshot(task["id"])["active_task"]
            assert saved["status"] == "resume_ready" and not saved["materials_confirmed"]
            assert not saved.get("material_binding") and not prepared
        else:
            task = service.prepare_worker(task["id"], task["revision"], "CHE", True)
            assert task["status"] == "queued" and task["materials_confirmed"]
            assert task["material_binding"]["actor"] == "system"
            assert task["material_binding"]["human_reviewed"] is False
            assert task["material_binding"]["pdf_sha256"] == "a" * 64
            assert not task.get("material_reviews")
            assert len(prepared) == 1 and verified
    finally:
        service.close()


def test_hard_condition_clarification_preserves_score_and_records_actual_user_fact(
    application, tmp_path
):
    applications, job = application
    report = {
        "id": "analysis-v1",
        "score": {"lower": 0, "upper": 100, "coverage": 0, "eligibility": "needs_input"},
        "requirements": [
            {"text": "Work permission", "judgment": "unknown", "hard_condition": True},
            {"text": "Python", "judgment": "unknown", "hard_condition": False},
        ],
    }
    service = ApplicationFlowService(
        applications, tmp_path / "flow", callbacks={"analysis": lambda _: report}
    )
    try:
        task = service.create(job["id"], job["revision"])
        service.start(task["id"], task["revision"], "analysis")
        task = wait_for(service, task["id"], lambda row: row["status"] == "analysis_ready")
        assert task_eligibility(task)["status"] == "needs_input"
        for index in (1, 2, -1):
            with pytest.raises(PortalDataError) as error:
                service.clarify_condition(task["id"], task["revision"], index, True, "A fact")
            assert error.value.code == "flow_condition_invalid"
        task = service.request(
            "clarify-condition",
            {
                "task_id": task["id"],
                "task_revision": task["revision"],
                "requirement_index": 0,
                "eligible": True,
                "source": "I hold the required permit for this job's country.",
            },
        )
        assert task_eligibility(task)["status"] == "supported"
        assert task["artifacts"][0]["result"]["score"] == report["score"]
        assert task["hard_condition_resolutions"][-1]["verified_by"] == "user"
        task = service.clarify_condition(
            task["id"], task["revision"], 0, False, "Correction: this permit is not valid there."
        )
        assert task_eligibility(task)["status"] == "conflict"
        assert len(task["hard_condition_resolutions"]) == 2
    finally:
        service.close()


def test_known_hard_conflict_cannot_be_cleared_by_unknown_condition_confirmation():
    task = {
        "analysis_id": "a",
        "artifacts": [
            {
                "stage": "analysis",
                "adopted": True,
                "result": {
                    "id": "a",
                    "requirements": [{"text": "Permit", "hard_condition": True, "judgment": "gap"}],
                },
            }
        ],
        "hard_condition_resolutions": [
            {
                "analysis_id": "a",
                "requirement_index": 0,
                "confirmed": True,
                "eligible": True,
                "verified_by": "user",
                "source": "A fact",
            }
        ],
    }
    assert task_eligibility(task)["status"] == "conflict"


@pytest.mark.parametrize("judgment", ["unknown", "gap"])
def test_worker_preparation_keeps_unknown_qualification_without_repeated_confirmation(
    application, tmp_path, judgment
):
    applications, original = application
    job = applications.update_application(
        original["id"], {"url": "https://example.com/jobs/synthetic"}, original["revision"]
    )
    calls = []
    report = {
        "id": "analysis-v1",
        "requirements": [{"text": "Required permit", "hard_condition": True, "judgment": judgment}],
    }

    def prepare(task, country):
        calls.append((task["send_approval"], country))
        return {"batch_id": "batch-v1", "job_id": job["id"], "status": "queued"}

    controls = []

    def control(task, operation, payload):
        controls.append(operation)
        return {
            "batch_id": "batch-v1",
            "job_id": job["id"],
            "status": "cancelled" if operation == "cancel-job" else "filling",
        }

    service = ApplicationFlowService(
        applications,
        tmp_path / "flow",
        callbacks={
            "analysis": lambda _: report,
            "resume": lambda _: {"id": "resume-v1", "pdf_sha256": "a" * 64},
            "prepare_worker": prepare,
            "control_worker": control,
            "verify_materials": lambda _: None,
        },
    )
    try:
        task = service.create(job["id"], job["revision"])
        service.start(task["id"], task["revision"], "analysis")
        task = wait_for(service, task["id"], lambda row: row["status"] == "analysis_ready")
        service.start(task["id"], task["revision"], "resume")
        task = wait_for(service, task["id"], lambda row: row["status"] == "resume_ready")
        if judgment == "gap":
            with pytest.raises(PortalDataError) as error:
                service.prepare_worker(task["id"], task["revision"], "CHE", True)
            assert error.value.code == "flow_eligibility_required"
            assert not calls and not controls
            assert task_eligibility(task)["status"] == "conflict"
            return
        assert task_eligibility(task)["status"] == "needs_input"
        for country, confirmation in (("", True), ("CHE", False)):
            with pytest.raises(PortalDataError):
                service.prepare_worker(task["id"], task["revision"], country, confirmation)
        task = service.request(
            "prepare-worker",
            {
                "task_id": task["id"],
                "task_revision": task["revision"],
                "country": "CHE",
                "send_confirmed": True,
            },
        )
        assert task["status"] == "queued"
        assert task_eligibility(task)["status"] == "needs_input"
        assert task.get("hard_condition_resolutions", []) == []
        assert task["worker_ref"]["batch_id"] == "batch-v1"
        assert calls[0][0]["job_url"] == job["url"]
        assert calls[0][0]["resume_sha256"] == "a" * 64
        assert calls[0][1] == "CHE"
        assert len(calls) == 1
        task = service.worker_action(task["id"], task["revision"], "resume", {})
        assert task["status"] == "filling"
        assert task_eligibility(task)["status"] == "needs_input"
        state = service._load()
        current = next(row for row in state["tasks"] if row["id"] == task["id"])
        current["artifacts"][0]["result"]["requirements"][0]["judgment"] = "gap"
        service._save(state)
        task = service.snapshot(task["id"])["active_task"]
        with pytest.raises(PortalDataError) as error:
            service.worker_action(task["id"], task["revision"], "resume", {})
        assert error.value.code == "flow_eligibility_required"
        assert controls == ["resume"]
        task = service.cancel(task["id"], task["revision"])
        assert controls == ["resume"]
        assert task["status"] == "cancelled"
        assert task["worker_ref"] == {"batch_id": "batch-v1", "job_id": job["id"]}
        task = service.observe_worker(
            task["id"],
            task["revision"],
            {
                "batch_id": "batch-v1",
                "job_id": job["id"],
                "status": "ready_for_review",
            },
        )
        assert task["status"] == "cancelled"
        with pytest.raises(PortalDataError) as error:
            service.worker_action(task["id"], task["revision"], "resume", {})
        assert error.value.code == "flow_cancelled"
        assert controls == ["resume"]
    finally:
        service.close()


def test_preparation_cancel_retains_an_unreconciled_published_worker(application, tmp_path):
    applications, original = application
    job = applications.update_application(
        original["id"], {"url": "https://example.com/jobs/synthetic"}, original["revision"]
    )
    published, controls = [], []

    def prepare(task, country):
        published.append({"batch_id": "prepared-v1", "job_id": job["id"], "status": "queued"})
        raise OSError("Synthetic failure after worker publication")

    def control(task, operation, payload):
        controls.append(operation)
        published[0]["status"] = "cancelled"
        return published[0]

    service = ApplicationFlowService(
        applications,
        tmp_path / "flow",
        callbacks={
            "analysis": lambda _: {"id": "a", "requirements": []},
            "resume": lambda _: {"id": "r", "pdf_sha256": "b" * 64},
            "prepare_worker": prepare,
            "control_worker": control,
        },
    )
    try:
        task = service.create(job["id"], job["revision"])
        for stage, ready in (("analysis", "analysis_ready"), ("resume", "resume_ready")):
            service.start(task["id"], task["revision"], stage)
            task = wait_for(service, task["id"], lambda row, ready=ready: row["status"] == ready)
        task = service.confirm_materials(task["id"], task["revision"], "r", "b" * 64)
        with pytest.raises(OSError):
            service.prepare_worker(task["id"], task["revision"], "CHE", True)
        task = service.snapshot(task["id"])["active_task"]
        assert task["worker_ref"] is None and task["worker_preparation"]["status"] == "pending"
        task = service.cancel(task["id"], task["revision"])
        assert task["status"] == "cancelled"
        assert published[0]["status"] == "queued" and controls == []
        assert task["worker_ref"] is None and task["worker_preparation"]["status"] == "pending"
    finally:
        service.close()


def test_stage_starts_once_and_reopening_only_observes(application, tmp_path):
    applications, job = application
    entered, release = threading.Event(), threading.Event()
    calls = []

    def analyze(task):
        calls.append(task["id"])
        entered.set()
        assert release.wait(3)
        return {"id": "synthetic-analysis", "summary": "Source-bound comparison"}

    service = ApplicationFlowService(
        applications, tmp_path / "flow", callbacks={"analysis": analyze}
    )
    try:
        task = service.create(job["id"], job["revision"], inputs={"sources_revision": "v1"})
        assert task["job_description"] == "Build reliable Python systems."
        started = service.start(task["id"], task["revision"], "analysis")
        assert entered.wait(3)
        duplicate = service.start(task["id"], started["revision"], "analysis")
        assert (
            duplicate["stages"]["analysis"]["attempt_id"]
            == started["stages"]["analysis"]["attempt_id"]
        )
        assert service.snapshot(task["id"])["active_task"]["id"] == task["id"]
        release.set()
        complete = wait_for(service, task["id"], lambda row: row["status"] == "analysis_ready")
        assert complete["analysis_id"] == "synthetic-analysis"
        assert (
            service.start(task["id"], complete["revision"], "analysis")["analysis_id"]
            == "synthetic-analysis"
        )
    finally:
        release.set()
        service.close()
    observer = ApplicationFlowService(
        applications, tmp_path / "flow", callbacks={"analysis": analyze}
    )
    try:
        assert observer.snapshot(task["id"])["active_task"]["analysis_id"] == "synthetic-analysis"
        assert calls == [task["id"]]
    finally:
        observer.close()


def test_request_rejects_forged_fields_and_stale_mutation(application, tmp_path):
    applications, job = application
    service = ApplicationFlowService(applications, tmp_path / "flow")
    try:
        task = service.request(
            "create",
            {"application_id": job["id"], "application_revision": job["revision"], "inputs": {}},
        )
        with pytest.raises(PortalDataError) as error:
            service.request(
                "cancel",
                {"task_id": task["id"], "task_revision": task["revision"], "worker_ref": {}},
            )
        assert error.value.code == "invalid_flow_request"
        with pytest.raises(PortalDataError) as error:
            service.request(
                "bind-worker", {"task_id": task["id"], "task_revision": task["revision"]}
            )
        assert error.value.code == "invalid_flow_request"
        with pytest.raises(PortalDataError) as error:
            service.cancel(task["id"], "stale")
        assert error.value.code == "conflict"
        stopped = service.request(
            "cancel", {"task_id": task["id"], "task_revision": task["revision"]}
        )
        assert stopped["status"] == "cancelled"
    finally:
        service.close()


def test_failed_stage_retries_only_on_explicit_request_and_runner_stays_serial(
    application, tmp_path
):
    applications, job = application
    calls = []
    entered, release = threading.Event(), threading.Event()

    def analyze(task):
        calls.append(task["id"])
        if len(calls) == 1:
            raise PortalDataError("codex_unavailable", "Synthetic failure")
        entered.set()
        assert release.wait(3)
        return {"id": "analysis-" + task["id"]}

    service = ApplicationFlowService(
        applications, tmp_path / "flow", callbacks={"analysis": analyze}
    )
    try:
        first = service.create(job["id"], job["revision"])
        service.start(first["id"], first["revision"], "analysis")
        failed = wait_for(service, first["id"], lambda row: row["status"] == "failed")
        assert failed["stages"]["analysis"]["error_code"] == "codex_unavailable"
        with pytest.raises(PortalDataError) as error:
            service.start(first["id"], failed["revision"], "analysis")
        assert error.value.code == "flow_retry_required"
        service.start(first["id"], failed["revision"], "analysis", retry=True)
        assert entered.wait(3)
        other_job = applications.create_application(
            {
                "company": "Other Synthetic",
                "role_title": "Engineer",
                "job_description": "Use Python.",
            }
        )
        other = service.create(other_job["id"], other_job["revision"])
        service.start(other["id"], other["revision"], "analysis")
        assert calls == [first["id"], first["id"]]
        release.set()
        wait_for(service, other["id"], lambda row: row["status"] == "analysis_ready")
        assert calls == [first["id"], first["id"], other["id"]]
    finally:
        release.set()
        service.close()


def test_cancelled_stage_cannot_publish_late_result_or_restart_implicitly(application, tmp_path):
    applications, job = application
    entered, release = threading.Event(), threading.Event()

    def analyze(task):
        entered.set()
        assert release.wait(3)
        return {"id": "late-analysis"}

    service = ApplicationFlowService(
        applications, tmp_path / "flow", callbacks={"analysis": analyze}
    )
    try:
        task = service.create(job["id"], job["revision"])
        service.start(task["id"], task["revision"], "analysis")
        assert entered.wait(3)
        current = service.snapshot(task["id"])["active_task"]
        cancelled = service.cancel(task["id"], current["revision"])
        release.set()
        stopped = wait_for(service, task["id"], lambda row: bool(row["artifacts"]))
        assert stopped["status"] == "cancelled"
        assert stopped["analysis_id"] is None
        assert stopped["artifacts"][0]["adopted"] is False
        with pytest.raises(PortalDataError) as error:
            service.start(task["id"], cancelled["revision"], "analysis")
        assert error.value.code == "flow_cancelled"
    finally:
        release.set()
        service.close()


def test_source_update_invalidates_downstream_but_preserves_old_artifacts(application, tmp_path):
    applications, job = application
    identity = {
        "application_revision": job["revision"],
        "inputs": {"jd_revision": "jd-v1", "sources_revision": "sources-v1"},
    }
    calls = []

    def analyze(task):
        calls.append("analysis")
        return {"id": "analysis-v1"}

    def resume(task):
        calls.append("resume")
        return {"id": "resume-v1", "pdf_sha256": "a" * 64}

    service = ApplicationFlowService(
        applications,
        tmp_path / "flow",
        callbacks={"analysis": analyze, "resume": resume},
        input_provider=lambda identifier: identity,
    )
    try:
        task = service.create(job["id"], job["revision"])
        assert task["inputs"] == identity["inputs"]
        service.start(task["id"], task["revision"], "analysis")
        analyzed = wait_for(service, task["id"], lambda row: row["status"] == "analysis_ready")
        service.start(task["id"], analyzed["revision"], "resume")
        drafted = wait_for(service, task["id"], lambda row: row["status"] == "resume_ready")
        confirmed = service.confirm_materials(
            task["id"], drafted["revision"], "resume-v1", "a" * 64
        )
        assert confirmed["materials_confirmed"] is True
        identity["inputs"] = {"jd_revision": "jd-v1", "sources_revision": "sources-v2"}
        refreshed = service.update_inputs(
            task["id"], confirmed["revision"], job["revision"], identity["inputs"]
        )
        assert refreshed["status"] == "stale"
        assert refreshed["analysis_id"] is None
        assert refreshed["resume_id"] is None
        assert refreshed["materials_confirmed"] is False
        assert [row["result"]["id"] for row in refreshed["artifacts"]] == [
            "analysis-v1",
            "resume-v1",
        ]
        assert calls == ["analysis", "resume"]
        with pytest.raises(PortalDataError) as error:
            service.create(job["id"], job["revision"], inputs={"sources_revision": "forged"})
        assert error.value.code == "flow_inputs_mismatch"
    finally:
        service.close()


def test_resume_configuration_change_preserves_completed_analysis_and_materials(
    application, tmp_path
):
    applications, job = application
    identity = {
        "application_revision": job["revision"],
        "inputs": {"sources_revision": "sources-v1", "resume_configuration_revision": "v1"},
    }
    calls = []

    def analyze(task):
        calls.append("analysis")
        return {"id": "analysis-v1"}

    def resume(task):
        calls.append("resume")
        return {"id": "resume-v1", "pdf_sha256": "a" * 64}

    service = ApplicationFlowService(
        applications,
        tmp_path / "resume-config-flow",
        callbacks={"analysis": analyze, "resume": resume},
        input_provider=lambda _: identity,
    )
    try:
        task = service.create(job["id"], job["revision"])
        service.start(task["id"], task["revision"], "analysis")
        analyzed = wait_for(service, task["id"], lambda row: row["status"] == "analysis_ready")
        service.start(task["id"], analyzed["revision"], "resume")
        drafted = wait_for(service, task["id"], lambda row: row["status"] == "resume_ready")
        confirmed = service.confirm_materials(
            task["id"], drafted["revision"], "resume-v1", "a" * 64
        )
        identity["inputs"]["resume_configuration_revision"] = "v2"
        assert service.start(task["id"], confirmed["revision"], "analysis")["analysis_id"]
        assert calls == ["analysis", "resume"]
        service.confirm_materials(task["id"], confirmed["revision"], "resume-v1", "a" * 64)
        refreshed = service.update_inputs(task["id"], confirmed["revision"], job["revision"])
        assert refreshed["status"] == "materials_ready"
        assert refreshed["analysis_id"] == "analysis-v1"
        assert refreshed["stages"]["analysis"]["status"] == "complete"
        assert refreshed["stages"]["resume"]["status"] == "complete"
        assert refreshed["resume_id"] == "resume-v1"
        assert refreshed["resume_sha256"] == "a" * 64
        assert refreshed["materials_confirmed"] is True
        assert len(refreshed["artifacts"]) == 2
    finally:
        service.close()


@pytest.mark.parametrize("changed_field", ["sources_revision", "resume_configuration_revision"])
def test_updating_inputs_cannot_revive_a_cancelled_task(application, tmp_path, changed_field):
    applications, job = application
    identity = {
        "application_revision": job["revision"],
        "inputs": {"sources_revision": "v1", "resume_configuration_revision": "v1"},
    }
    calls = []
    service = ApplicationFlowService(
        applications,
        tmp_path / "cancelled-flow",
        callbacks={"analysis": lambda _: {"id": "analysis-v1"}, "resume": calls.append},
        input_provider=lambda _: identity,
    )
    try:
        task = service.create(job["id"], job["revision"])
        service.start(task["id"], task["revision"], "analysis")
        task = wait_for(service, task["id"], lambda row: row["status"] == "analysis_ready")
        cancelled = service.cancel(task["id"], task["revision"])
        identity["inputs"][changed_field] = "v2"
        with pytest.raises(PortalDataError) as error:
            service.update_inputs(task["id"], cancelled["revision"], job["revision"])
        assert error.value.code == "flow_cancelled"
        assert service.snapshot(task["id"])["active_task"] == cancelled
        assert calls == []
    finally:
        service.close()


def test_resume_only_configuration_change_during_analysis_does_not_discard_its_result(
    application, tmp_path
):
    applications, job = application
    identity = {
        "application_revision": job["revision"],
        "inputs": {"sources_revision": "sources-v1", "resume_configuration_revision": "v1"},
    }
    entered, release = threading.Event(), threading.Event()

    def analyze(task):
        entered.set()
        assert release.wait(3)
        return {"id": "analysis-v1"}

    service = ApplicationFlowService(
        applications,
        tmp_path / "analysis-config-flow",
        callbacks={"analysis": analyze, "resume": lambda _: {"id": "resume-v1"}},
        input_provider=lambda _: identity,
    )
    try:
        task = service.create(job["id"], job["revision"])
        service.start(task["id"], task["revision"], "analysis")
        assert entered.wait(3)
        identity["inputs"]["resume_configuration_revision"] = "v2"
        release.set()
        analyzed = wait_for(
            service, task["id"], lambda row: row["status"] in {"analysis_ready", "stale"}
        )
        assert analyzed["status"] == "analysis_ready"
        assert analyzed["analysis_id"] == "analysis-v1"
        with pytest.raises(PortalDataError) as error:
            service.start(task["id"], analyzed["revision"], "resume")
        assert error.value.code == "flow_inputs_stale"
        updated = service.update_inputs(task["id"], analyzed["revision"], job["revision"])
        assert updated["analysis_id"] == "analysis-v1"
    finally:
        release.set()
        service.close()


def test_explicit_resume_regeneration_clears_approval_and_keeps_completed_versions(
    application, tmp_path
):
    applications, job = application
    entered, release = threading.Event(), threading.Event()
    calls = []

    def resume(task):
        calls.append(task["stages"]["resume"].get("regenerate", False))
        if len(calls) == 2:
            entered.set()
            assert release.wait(3)
        return {"id": f"resume-v{len(calls)}", "pdf_sha256": "a" * 64}

    service = ApplicationFlowService(
        applications,
        tmp_path / "regenerate-flow",
        callbacks={"analysis": lambda _: {"id": "analysis-v1"}, "resume": resume},
    )
    try:
        task = service.create(job["id"], job["revision"])
        service.start(task["id"], task["revision"], "analysis")
        analyzed = wait_for(service, task["id"], lambda row: row["status"] == "analysis_ready")
        service.start(task["id"], analyzed["revision"], "resume")
        drafted = wait_for(service, task["id"], lambda row: row["status"] == "resume_ready")
        confirmed = service.confirm_materials(
            task["id"], drafted["revision"], "resume-v1", "a" * 64
        )
        repeated = service.start(task["id"], confirmed["revision"], "resume")
        assert repeated["resume_id"] == "resume-v1" and calls == [False]
        regenerating = service.start(task["id"], confirmed["revision"], "resume", retry=True)
        assert not regenerating["materials_confirmed"]
        assert regenerating["resume_id"] is None
        assert entered.wait(3)
        service.start(task["id"], regenerating["revision"], "resume", retry=True)
        assert calls == [False, True]
        release.set()
        generated = wait_for(service, task["id"], lambda row: row["status"] == "resume_ready")
        assert generated["resume_id"] == "resume-v2"
        assert not generated["materials_confirmed"]
        assert generated["analysis_id"] == "analysis-v1"
        assert [row["result"]["id"] for row in generated["artifacts"]] == [
            "analysis-v1",
            "resume-v1",
            "resume-v2",
        ]
    finally:
        release.set()
        service.close()


def test_note_only_change_preserves_analysis_but_jd_change_during_model_is_stale(
    application, tmp_path
):
    applications, job = application
    entered, release = threading.Event(), threading.Event()

    def analyze(task):
        entered.set()
        assert release.wait(3)
        return {"id": "old-jd-result"}

    service = ApplicationFlowService(
        applications, tmp_path / "flow", callbacks={"analysis": analyze}
    )
    try:
        task = service.create(job["id"], job["revision"])
        note = applications.update_application(
            job["id"], {"notes": "Local note only"}, job["revision"]
        )
        service.start(task["id"], task["revision"], "analysis")
        assert entered.wait(3)
        applications.update_application(
            job["id"], {"job_description": "A different role."}, note["revision"]
        )
        release.set()
        stale = wait_for(service, task["id"], lambda row: row["status"] == "stale")
        assert stale["analysis_id"] is None
        assert stale["artifacts"][0]["result"]["id"] == "old-jd-result"
        assert stale["artifacts"][0]["adopted"] is False
    finally:
        release.set()
        service.close()


def test_shutdown_and_reopen_do_not_publish_or_repeat_interrupted_model(application, tmp_path):
    applications, job = application
    entered, release = threading.Event(), threading.Event()
    calls = []

    def analyze(task):
        calls.append(task["id"])
        entered.set()
        assert release.wait(3)
        return {"id": "interrupted-result"}

    service = ApplicationFlowService(
        applications, tmp_path / "flow", callbacks={"analysis": analyze}
    )
    task = service.create(job["id"], job["revision"])
    service.start(task["id"], task["revision"], "analysis")
    assert entered.wait(3)
    service.close()
    observer = ApplicationFlowService(
        applications, tmp_path / "flow", callbacks={"analysis": analyze}
    )
    try:
        interrupted = observer.snapshot(task["id"])["active_task"]
        assert interrupted["status"] == "failed"
        assert interrupted["stages"]["analysis"]["error_code"] == "flow_interrupted"
        release.set()
        assert observer.snapshot(task["id"])["active_task"]["analysis_id"] is None
        assert calls == [task["id"]]
    finally:
        release.set()
        observer.close()


def test_worker_reference_requires_current_observation_without_retrying_external_actions(
    application, tmp_path
):
    applications, job = application
    callbacks = {
        "analysis": lambda task: {"id": "analysis-v1"},
        "resume": lambda task: {"id": "resume-v1", "pdf_sha256": "b" * 64},
    }
    service = ApplicationFlowService(applications, tmp_path / "flow", callbacks=callbacks)
    try:
        task = service.create(job["id"], job["revision"])
        with pytest.raises(PortalDataError) as error:
            service.bind_worker(
                task["id"],
                task["revision"],
                {"batch_id": "batch-1", "job_id": job["id"], "status": "filling"},
            )
        assert error.value.code == "flow_materials_required"
        service.start(task["id"], task["revision"], "analysis")
        task = wait_for(service, task["id"], lambda row: row["status"] == "analysis_ready")
        service.start(task["id"], task["revision"], "resume")
        task = wait_for(service, task["id"], lambda row: row["status"] == "resume_ready")
        task = service.confirm_materials(task["id"], task["revision"], "resume-v1", "b" * 64)
        task = service.bind_worker(
            task["id"],
            task["revision"],
            {"batch_id": "batch-1", "job_id": job["id"], "status": "filling"},
        )
        with pytest.raises(PortalDataError) as error:
            service.observe_worker(
                task["id"],
                task["revision"],
                {"batch_id": "another-batch", "job_id": job["id"], "status": "ready_for_review"},
            )
        assert error.value.code == "flow_worker_mismatch"
        task = service.observe_worker(
            task["id"],
            task["revision"],
            {
                "batch_id": "batch-1",
                "job_id": job["id"],
                "status": "needs_recheck",
                "reason": "action_result_unknown",
            },
        )
        assert task["status"] == "needs_recheck"
        assert task["worker_ref"]["reason"] == "action_result_unknown"
    finally:
        service.close()
    observer = ApplicationFlowService(applications, tmp_path / "flow", callbacks=callbacks)
    try:
        retained = observer.snapshot(task["id"])["active_task"]
        assert retained["status"] == "needs_recheck"
        assert retained["worker_ref"] == {
            "batch_id": "batch-1",
            "job_id": job["id"],
            "status": "needs_recheck",
            "reason": "flow_worker_unavailable",
        }
    finally:
        observer.close()


def test_task_snapshots_are_retained_and_second_service_cannot_start_work(application, tmp_path):
    applications, job = application
    service = ApplicationFlowService(applications, tmp_path / "flow")
    observer = ApplicationFlowService(applications, tmp_path / "flow")
    try:
        task = service.create(job["id"], job["revision"])
        original = tmp_path / "flow" / "snapshots" / task["id"] / f"{task['revision']}.json"
        saved = original.read_bytes()
        stopped = service.cancel(task["id"], task["revision"])
        assert original.read_bytes() == saved
        assert observer.snapshot(task["id"])["active_task"]["revision"] == stopped["revision"]
        with pytest.raises(PortalDataError) as error:
            observer.create(job["id"], job["revision"])
        assert error.value.code == "flow_runtime_busy"
    finally:
        observer.close()
        service.close()


def test_process_exit_recovers_running_stage_as_interrupted_without_replay(application, tmp_path):
    applications, job = application
    script = """
import os, sys, threading
from pathlib import Path
from career_evidence_graph.application_flow import ApplicationFlowService
from career_evidence_graph.career_portal_data import ApplicationStore
applications = ApplicationStore(Path(sys.argv[1]))
service = ApplicationFlowService(
    applications, Path(sys.argv[2]), callbacks={"analysis": lambda task: os._exit(0)}
)
task = service.create(sys.argv[3], sys.argv[4])
service.start(task["id"], task["revision"], "analysis")
threading.Event().wait(3)
os._exit(2)
"""
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            script,
            str(applications.root),
            str(tmp_path / "flow"),
            job["id"],
            job["revision"],
        ],
        env=os.environ | {"PYTHONPATH": str(Path(__file__).resolve().parents[1] / "src")},
        capture_output=True,
        timeout=5,
    )
    assert result.returncode == 0
    calls = []
    service = ApplicationFlowService(
        applications,
        tmp_path / "flow",
        callbacks={"analysis": lambda task: calls.append(task["id"])},
    )
    try:
        task = service.snapshot()["active_task"]
        assert task["status"] == "failed"
        assert task["stages"]["analysis"]["error_code"] == "flow_interrupted"
        assert calls == []
    finally:
        service.close()


def test_background_storage_failure_rejects_later_work_instead_of_abandoning_queue(
    application, tmp_path, monkeypatch
):
    from career_evidence_graph._vendor import job_apply_store as helper

    applications, job = application
    original = helper.atomic_write_json
    failed = threading.Event()

    def write(path, payload):
        if threading.current_thread().name == "application-flow" and not failed.is_set():
            failed.set()
            raise OSError("Synthetic storage outage")
        return original(path, payload)

    service = ApplicationFlowService(
        applications, tmp_path / "flow", callbacks={"analysis": lambda task: {"id": "result"}}
    )
    monkeypatch.setattr(helper, "atomic_write_json", write)
    try:
        task = service.create(job["id"], job["revision"])
        service.start(task["id"], task["revision"], "analysis")
        interrupted = wait_for(service, task["id"], lambda row: row["status"] == "failed")
        assert interrupted["stages"]["analysis"]["error_code"] == "flow_checkpoint_unavailable"
        assert service.snapshot()["runtime_error"] == "flow_checkpoint_unavailable"
        with pytest.raises(PortalDataError) as error:
            service.create(job["id"], job["revision"])
        assert error.value.code == "flow_checkpoint_unavailable"
    finally:
        service.close()


def test_reopened_service_cannot_retry_until_closed_service_finishes_its_model(
    application, tmp_path
):
    applications, job = application
    entered, release, exited = threading.Event(), threading.Event(), threading.Event()
    calls = []

    def analyze(task):
        calls.append(task["id"])
        entered.set()
        assert release.wait(3)
        exited.set()
        return {"id": "retired-result"}

    first = ApplicationFlowService(applications, tmp_path / "flow", callbacks={"analysis": analyze})
    task = first.create(job["id"], job["revision"])
    first.start(task["id"], task["revision"], "analysis")
    assert entered.wait(3)
    first.close()
    second = ApplicationFlowService(
        applications, tmp_path / "flow", callbacks={"analysis": analyze}
    )
    try:
        row = second.snapshot(task["id"])["active_task"]
        with pytest.raises(PortalDataError) as error:
            second.start(task["id"], row["revision"], "analysis", retry=True)
        assert error.value.code == "flow_runtime_busy"
        assert calls == [task["id"]]
    finally:
        second.close()
        release.set()
        assert exited.wait(3)
        first.close()
    third = ApplicationFlowService(applications, tmp_path / "flow", callbacks={"analysis": analyze})
    try:
        row = third.snapshot(task["id"])["active_task"]
        third.start(task["id"], row["revision"], "analysis", retry=True)
        wait_for(third, task["id"], lambda row: row["status"] == "analysis_ready")
        assert calls == [task["id"], task["id"]]
    finally:
        third.close()


def test_completed_results_keep_original_model_binding_across_configuration_updates(
    application, tmp_path
):
    applications, job = application
    identity = {
        "application_revision": job["revision"],
        "inputs": {
            "sources_revision": "sources-v1",
            "analysis_configuration_revision": "analysis-model-v1",
            "resume_configuration_revision": "resume-model-v1",
        },
    }
    calls = []
    service = ApplicationFlowService(
        applications,
        tmp_path / "model-change-flow",
        callbacks={
            "analysis": lambda task: calls.append("analysis") or {"id": "analysis-v1"},
            "resume": lambda task: (
                calls.append("resume")
                or {
                    "id": "resume-v1"
                    if task["inputs"]["resume_configuration_revision"] == "resume-model-v1"
                    else "resume-v2",
                    "pdf_sha256": "a" * 64,
                }
            ),
        },
        input_provider=lambda _: identity,
    )
    try:
        task = service.create(job["id"], job["revision"])
        service.start(task["id"], task["revision"], "analysis")
        task = wait_for(service, task["id"], lambda row: row["status"] == "analysis_ready")
        service.start(task["id"], task["revision"], "resume")
        task = wait_for(service, task["id"], lambda row: row["status"] == "resume_ready")
        task = service.confirm_materials(task["id"], task["revision"], "resume-v1", "a" * 64)
        original_inputs = dict(task["inputs"])
        original_artifacts = list(task["artifacts"])
        identity["inputs"] = identity["inputs"] | {
            "analysis_configuration_revision": "analysis-model-v2",
            "resume_configuration_revision": "resume-model-v2",
        }
        updated = service.update_inputs(task["id"], task["revision"], job["revision"])
        assert updated["status"] == "materials_ready"
        assert updated["inputs"] == original_inputs
        assert updated["artifacts"] == original_artifacts
        assert updated["resume_id"] == "resume-v1" and updated["materials_confirmed"]
        assert service.create(job["id"], job["revision"])["id"] == task["id"]
        assert service.start(task["id"], updated["revision"], "resume")["resume_id"] == "resume-v1"
        assert calls == ["analysis", "resume"]
        service.start(task["id"], updated["revision"], "resume", retry=True)
        regenerated = wait_for(service, task["id"], lambda row: row["status"] == "resume_ready")
        assert regenerated["resume_id"] == "resume-v2"
        assert regenerated["inputs"]["resume_configuration_revision"] == "resume-model-v2"
        assert regenerated["inputs"]["analysis_configuration_revision"] == "analysis-model-v1"
        assert regenerated["artifacts"][:2] == original_artifacts
        assert regenerated["artifacts"][-1]["inputs"]["resume_configuration_revision"] == (
            "resume-model-v2"
        )
        assert calls == ["analysis", "resume", "resume"]
    finally:
        service.close()


def test_a_failed_material_stage_keeps_its_reason(application, tmp_path):
    applications, job = application

    def resume(_):
        raise PortalDataError("resume_latex_invalid", "正文括号不平衡，不能保存为完整简历。", 409)

    service = ApplicationFlowService(
        applications,
        tmp_path / "flow",
        callbacks={
            "analysis": lambda _: {"id": "analysis-v1", "requirements": []},
            "resume": resume,
        },
    )
    try:
        task = service.create(job["id"], job["revision"])
        service.start(task["id"], task["revision"], "analysis")
        task = wait_for(service, task["id"], lambda row: row["status"] == "analysis_ready")
        service.start(task["id"], task["revision"], "resume")
        task = wait_for(service, task["id"], lambda row: row["status"] == "failed")
        # Installed MC-11: the Hexagon résumé failed with only an error code; the
        # page and the operator had no way to tell which check refused it.
        assert task["stages"]["resume"]["error_message"] == "正文括号不平衡，不能保存为完整简历。"
        assert "error_message" not in task["stages"]["analysis"]
    finally:
        service.close()


def test_only_the_latest_normal_recheck_keeps_its_full_result():
    from career_evidence_graph.application_flow import compact_match_rechecks

    task = {
        "match_rechecks": [
            {"id": "a", "method": "normal_analysis", "result": {"r": 1}},
            {"id": "m", "method": "manual", "result": {"r": 2}},
            {"id": "b", "method": "normal_analysis", "result": {"r": 3}},
        ]
    }
    compact_match_rechecks(task)
    assert [row.get("result") for row in task["match_rechecks"]] == [None, {"r": 2}, {"r": 3}]
