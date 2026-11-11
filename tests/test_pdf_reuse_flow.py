"""Internal accepted-PDF reuse preserves exact materials without another review."""

import hashlib
import threading

import pytest
from test_application_flow import application as application
from test_application_flow import wait_for
from test_full_latex_flow import bind
from test_job_explanations import requirement

from career_evidence_graph.application_flow import ApplicationFlowService
from career_evidence_graph.application_prism import source_snapshot
from career_evidence_graph.career_portal_data import PortalDataError


@pytest.fixture
def reuse_flow(application, tmp_path):
    applications, job = application
    project = tmp_path / "base"
    project.mkdir()
    (project / "main.tex").write_text("Synthetic complete source")
    pdf = tmp_path / "accepted.pdf"
    pdf.write_bytes(b"%PDF-1.4\nSynthetic previously accepted PDF\n%%EOF\n")
    service = ApplicationFlowService(
        applications,
        tmp_path / "flow",
        preparation_only=True,
        input_provider=lambda identifier: {
            "application_revision": applications.get_application(identifier)["revision"],
            "inputs": {"resume_configuration_revision": "f" * 64, "library": "reviewed-v1"},
        },
        callbacks={
            "analysis": lambda _: {"id": "analysis", "requirements": [requirement()]},
            "prism_source": source_snapshot,
            "export": lambda _: pytest.fail("Original PDF must not be compiled or exported"),
        },
    )
    task = service.create(job["id"], job["revision"])
    service.start(task["id"], task["revision"], "analysis")
    task = wait_for(service, task["id"], lambda row: row["status"] == "analysis_ready")
    task = bind(service, task, project)
    try:
        yield service, task, pdf
    finally:
        service.close()


def reuse_candidate(task, pdf):
    return {
        "id": "a" * 32,
        "kind": "accepted_pdf_reuse",
        "pdf_sha256": hashlib.sha256(pdf.read_bytes()).hexdigest(),
        "application_id": task["application_id"],
        "analysis_binding": {"analysis_id": task["analysis_id"]},
        "resume_configuration_revision": task["inputs"]["resume_configuration_revision"],
        "reuse_binding": {"source_task_id": "b" * 32, "accepted_pdf": "synthetic-v1"},
    }


def test_verified_original_pdf_is_ready_without_generation_export_or_repeat_confirmation(
    reuse_flow,
):
    service, task, pdf = reuse_flow
    original_bytes = pdf.read_bytes()
    calls = []

    def select(request):
        calls.append("select")
        return reuse_candidate(request, pdf)

    def verify(request, result):
        calls.append("verify")
        assert result["application_id"] == request["application_id"]
        assert result["pdf_sha256"] == hashlib.sha256(original_bytes).hexdigest()
        assert pdf.read_bytes() == original_bytes

    service.callbacks.update(resume=select, verify_pdf_reuse=verify)
    service.start(task["id"], task["revision"], "resume")
    ready = wait_for(
        service, task["id"], lambda row: row["status"] in {"materials_ready", "failed"}
    )
    assert ready["status"] == "materials_ready"
    assert ready["materials_confirmed"] is True
    assert ready["resume_id"] == "a" * 32
    assert ready["resume_sha256"] == hashlib.sha256(original_bytes).hexdigest()
    assert ready["pdf_reuse"] == {
        "source_task_id": "b" * 32,
        "accepted_pdf": "synthetic-v1",
    }
    assert not ready.get("material_reviews")
    assert not ready.get("material_acceptance")
    assert not ready.get("draft_id")
    assert calls == ["select", "verify", "verify"]
    assert pdf.read_bytes() == original_bytes
    service.close()
    reopened = ApplicationFlowService(
        service.applications,
        service.root,
        preparation_only=True,
        callbacks=service.callbacks,
        input_provider=service.input_provider,
    )
    try:
        saved = reopened.snapshot(task["id"])["active_task"]
        assert saved["status"] == "materials_ready"
        assert saved["materials_confirmed"] is True
        assert saved["pdf_reuse"] == ready["pdf_reuse"]
    finally:
        reopened.close()


@pytest.mark.parametrize("verification", ["missing", "reject"])
def test_unverified_or_forged_reuse_cannot_bypass_pdf_confirmation(reuse_flow, verification):
    service, task, pdf = reuse_flow
    service.callbacks["resume"] = lambda request: reuse_candidate(request, pdf)
    if verification == "reject":

        def reject(_request, _result):
            raise PortalDataError("pdf_reuse_invalid", "Synthetic invalid source acceptance", 409)

        service.callbacks["verify_pdf_reuse"] = reject
    service.start(task["id"], task["revision"], "resume")
    failed = wait_for(service, task["id"], lambda row: row["status"] == "failed")
    assert failed["materials_confirmed"] is False
    assert failed["resume_id"] is None
    assert not failed.get("pdf_reuse")
    assert not any(row["adopted"] for row in failed["artifacts"] if row["stage"] == "resume")


@pytest.mark.parametrize("change", ["cancel", "inputs"])
def test_selector_finishing_after_cancel_or_input_change_cannot_adopt(reuse_flow, change):
    service, task, pdf = reuse_flow
    entered, release = threading.Event(), threading.Event()

    def select(request):
        entered.set()
        assert release.wait(2)
        return reuse_candidate(request, pdf)

    service.callbacks.update(resume=select, verify_pdf_reuse=lambda *_: None)
    service.start(task["id"], task["revision"], "resume")
    try:
        assert entered.wait(2)
        if change == "cancel":
            running = service.snapshot(task["id"])["active_task"]
            service.cancel(task["id"], running["revision"])
        else:
            provider = service.input_provider
            service.input_provider = lambda identifier: (
                provider(identifier)
                | {"inputs": {"library": "reviewed-v2", "resume_configuration_revision": "f" * 64}}
            )
        release.set()
        saved = wait_for(
            service,
            task["id"],
            lambda row: any(artifact["stage"] == "resume" for artifact in row["artifacts"]),
        )
        assert saved["status"] == ("cancelled" if change == "cancel" else "stale")
        assert saved["materials_confirmed"] is False
        assert saved["resume_id"] is None
        assert not saved.get("pdf_reuse")
        assert saved["artifacts"][-1]["adopted"] is False
    finally:
        release.set()


def test_input_change_during_verification_is_rechecked_before_adoption(reuse_flow):
    service, task, pdf = reuse_flow
    provider = service.input_provider

    def verify(_request, _result):
        service.input_provider = lambda identifier: (
            provider(identifier)
            | {"inputs": {"library": "reviewed-v2", "resume_configuration_revision": "f" * 64}}
        )

    service.callbacks.update(
        resume=lambda request: reuse_candidate(request, pdf), verify_pdf_reuse=verify
    )
    service.start(task["id"], task["revision"], "resume")
    saved = wait_for(service, task["id"], lambda row: row["status"] == "stale")
    assert saved["materials_confirmed"] is False
    assert saved["resume_id"] is None
    assert saved["artifacts"][-1]["adopted"] is False


def test_explicit_regeneration_cannot_reuse_previously_accepted_pdf(reuse_flow):
    service, task, pdf = reuse_flow
    service.callbacks.update(
        resume=lambda request: reuse_candidate(request, pdf), verify_pdf_reuse=lambda *_: None
    )
    service.start(task["id"], task["revision"], "resume")
    ready = wait_for(service, task["id"], lambda row: row["status"] == "materials_ready")
    service.start(ready["id"], ready["revision"], "resume", retry=True)
    saved = wait_for(service, task["id"], lambda row: row["status"] == "failed")
    assert saved["materials_confirmed"] is False
    assert saved["resume_id"] is None
    assert not saved.get("pdf_reuse")
    assert not any(
        row["adopted"]
        for row in saved["artifacts"]
        if row["attempt_id"] == saved["stages"]["resume"]["attempt_id"]
    )


def test_changed_inputs_clear_current_reuse_and_keep_original_artifact_history(reuse_flow):
    service, task, pdf = reuse_flow
    service.callbacks.update(
        resume=lambda request: reuse_candidate(request, pdf), verify_pdf_reuse=lambda *_: None
    )
    service.start(task["id"], task["revision"], "resume")
    ready = wait_for(service, task["id"], lambda row: row["status"] == "materials_ready")
    provider = service.input_provider
    service.input_provider = lambda identifier: (
        provider(identifier)
        | {"inputs": {"library": "reviewed-v2", "resume_configuration_revision": "f" * 64}}
    )
    updated = service.update_inputs(ready["id"], ready["revision"], ready["application_revision"])
    assert updated["materials_confirmed"] is False
    assert updated["resume_id"] is None
    assert not updated.get("pdf_reuse")
    assert any(
        row["result"]["kind"] == "accepted_pdf_reuse"
        for row in updated["artifacts"]
        if row["stage"] == "resume"
    )


def test_unknown_pdf_result_cannot_skip_full_latex_review(reuse_flow):
    service, task, pdf = reuse_flow
    service.callbacks.update(
        resume=lambda request: reuse_candidate(request, pdf) | {"kind": "unverified_pdf"},
        verify_pdf_reuse=lambda *_: pytest.fail("Unknown result must not reach reuse verification"),
    )
    service.start(task["id"], task["revision"], "resume")
    failed = wait_for(service, task["id"], lambda row: row["status"] == "failed")
    assert failed["materials_confirmed"] is False
    assert failed["resume_id"] is None
    assert not failed.get("pdf_reuse")
