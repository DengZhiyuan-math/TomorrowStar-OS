"""Preparation drafts are reviewable without a PDF or application permission."""

import pytest
from test_application_flow import application as application
from test_application_flow import wait_for
from test_job_explanations import requirement

from career_evidence_graph.application_flow import ApplicationFlowService
from career_evidence_graph.career_portal_data import PortalDataError


def test_preparation_adopts_draft_without_pdf_and_records_explicit_version_review(
    application, tmp_path
):
    applications, job = application
    checked = []
    service = ApplicationFlowService(
        applications,
        tmp_path / "flow",
        preparation_only=True,
        callbacks={
            "analysis": lambda _: {"id": "a", "requirements": [requirement()]},
            "resume": lambda _: {
                "id": "d",
                "kind": "draft",
                "draft_sha256": "a" * 64,
                "model_mode": "unknown",
            },
            "verify_draft": lambda task: checked.append(task["draft_id"]),
        },
    )
    try:
        task = service.create(job["id"], job["revision"])
        service.start(task["id"], task["revision"], "analysis")
        task = wait_for(service, task["id"], lambda row: row["status"] == "analysis_ready")
        service.start(task["id"], task["revision"], "resume")
        task = wait_for(service, task["id"], lambda row: row["status"] in {"draft_ready", "failed"})
        assert task["status"] == "draft_ready"
        assert task["draft_id"] == "d" and task["resume_id"] is None
        assert task["resume_sha256"] is None and task["materials_confirmed"] is False
        assert not task.get("draft_review")
        with pytest.raises(PortalDataError):
            service.confirm_materials(task["id"], task["revision"], "d", "a" * 64)
        task = service.request(
            "review-draft",
            {
                "task_id": task["id"],
                "task_revision": task["revision"],
                "draft_id": "d",
                "draft_sha256": "a" * 64,
            },
        )
        assert task["draft_review"]["status"] == "reviewed"
        assert task["draft_review"]["actor"] == "user"
        assert task["draft_review"]["model_mode"] == "unknown"
        assert task["draft_review"]["scope"] == "draft_review"
        assert checked == ["d"] and task["materials_confirmed"] is False
        review = task["draft_review"]
        task = service.update_inputs(
            task["id"],
            task["revision"],
            job["revision"],
            inputs={"sources_revision": "new-sources"},
        )
        assert task.get("draft_review") is None
        assert task["draft_reviews"] == [review]
    finally:
        service.close()


def test_explicit_other_resume_language_pauses_before_generation(application, tmp_path):
    applications, original = application
    job = applications.update_application(
        original["id"],
        {"job_description": "Build Python services. Please submit your CV in French."},
        original["revision"],
    )
    calls = []
    service = ApplicationFlowService(
        applications,
        tmp_path / "flow",
        preparation_only=True,
        callbacks={
            "analysis": lambda _: {"id": "a", "requirements": [requirement()]},
            "resume": lambda _: calls.append("generated"),
        },
    )
    try:
        task = service.create(job["id"], job["revision"])
        service.start(task["id"], task["revision"], "analysis")
        task = wait_for(service, task["id"], lambda row: row["status"] == "analysis_ready")
        with pytest.raises(PortalDataError) as error:
            service.start(task["id"], task["revision"], "resume")
        assert error.value.code == "flow_resume_language_required"
        policy = service.snapshot(task["id"])["resume_language"]
        assert policy["status"] == "needs_input" and policy["language"] is None
        assert "French" in policy["requirements"][0]["text"]
        assert calls == []
    finally:
        service.close()


@pytest.mark.parametrize("changed", ["cancel", "inputs", "qualification"])
def test_late_draft_cannot_be_adopted_after_its_attempt_or_facts_change(
    application, tmp_path, changed
):
    import threading

    applications, job = application
    inputs = {"sources_revision": "source-v1"}
    entered, release = threading.Event(), threading.Event()
    calls = []

    def generate(_):
        calls.append("generate")
        entered.set()
        assert release.wait(2)
        return {"id": "late-draft", "kind": "draft", "draft_sha256": "a" * 64}

    service = ApplicationFlowService(
        applications,
        tmp_path / "flow",
        preparation_only=True,
        input_provider=lambda _: {"application_revision": job["revision"], "inputs": inputs},
        callbacks={
            "analysis": lambda _: {
                "id": "a",
                "requirements": [requirement("Work permit", judgment="unknown", hard=True)],
            },
            "resume": generate,
        },
    )
    try:
        task = service.create(job["id"], job["revision"])
        service.start(task["id"], task["revision"], "analysis")
        task = wait_for(service, task["id"], lambda row: row["status"] == "analysis_ready")
        task = service.clarify_condition(
            task["id"], task["revision"], 0, True, "Synthetic confirmed fact."
        )
        service.start(task["id"], task["revision"], "resume")
        assert entered.wait(2)
        task = service.snapshot(task["id"])["active_task"]
        if changed == "cancel":
            service.cancel(task["id"], task["revision"])
        elif changed == "inputs":
            attempt_id = task["stages"]["resume"]["attempt_id"]
            before = service.path.read_bytes()
            inputs["sources_revision"] = "source-v2"
            with pytest.raises(PortalDataError) as error:
                service.update_inputs(task["id"], task["revision"], job["revision"])
            assert error.value.code == "flow_update_inflight" and error.value.status == 409
            assert service.path.read_bytes() == before
        else:
            service.clarify_condition(task["id"], task["revision"], 0, False, "Corrected fact.")
        release.set()
        task = wait_for(
            service, task["id"], lambda row: any(a["stage"] == "resume" for a in row["artifacts"])
        )
        if changed == "inputs":
            # APP-04: a source revision during generation does not stale the late
            # draft; only the explicit sync, refused while it ran, adopts the revision.
            artifact = task["artifacts"][-1]
            assert artifact["attempt_id"] == attempt_id and artifact["adopted"] is True
            assert artifact["inputs"]["sources_revision"] == "source-v1"
            assert task["draft_id"] == "late-draft"
            task = service.update_inputs(task["id"], task["revision"], job["revision"])
            assert task["inputs"]["sources_revision"] == "source-v2"
            assert task["stages"]["analysis"]["status"] == "pending"
            assert task["stages"]["resume"]["status"] == "pending"
            assert calls == ["generate"]
            return
        assert task["artifacts"][-1]["adopted"] is False
        assert task.get("draft_id") is None and task["resume_id"] is None
        assert task["materials_confirmed"] is False and not task.get("draft_review")
        assert calls == ["generate"]
    finally:
        release.set()
        service.close()


def test_preparation_policy_change_invalidates_completed_analysis_without_erasing_history(
    application, tmp_path
):
    applications, job = application
    inputs = {"preparation_policy_revision": "policy-v1"}
    calls = []
    service = ApplicationFlowService(
        applications,
        tmp_path / "flow",
        preparation_only=True,
        input_provider=lambda _: {"application_revision": job["revision"], "inputs": inputs},
        callbacks={
            "analysis": lambda _: (
                calls.append("analysis")
                or {"id": f"analysis-{len(calls)}", "requirements": [requirement()]}
            ),
        },
    )
    try:
        task = service.create(job["id"], job["revision"])
        service.start(task["id"], task["revision"], "analysis")
        task = wait_for(service, task["id"], lambda row: row["status"] == "analysis_ready")
        artifacts = task["artifacts"]
        inputs["preparation_policy_revision"] = "policy-v2"
        before = service.path.read_bytes()
        with pytest.raises(PortalDataError) as error:
            service.start(task["id"], task["revision"], "analysis")
        assert error.value.code == "flow_inputs_stale"
        assert service.path.read_bytes() == before and calls == ["analysis"]
        task = service.update_inputs(task["id"], task["revision"], job["revision"])
        assert task["analysis_id"] is None and task["stages"]["analysis"]["status"] == "pending"
        assert task["artifacts"] == artifacts and calls == ["analysis"]
        service.start(task["id"], task["revision"], "analysis")
        task = wait_for(service, task["id"], lambda row: row["status"] == "analysis_ready")
        assert task["analysis_id"] == "analysis-2" and calls == ["analysis", "analysis"]
        assert task["artifacts"][: len(artifacts)] == artifacts
    finally:
        service.close()
