"""Existing LaTeX can be tested locally without inventing factual review or analysis."""

import hashlib
import threading

import pytest
from test_application_flow import application as application
from test_application_flow import wait_for
from test_application_prism import compiling_editor

from career_evidence_graph.application_flow import ApplicationFlowService
from career_evidence_graph.application_prism import PrismClient, source_snapshot
from career_evidence_graph.application_resume import ApplicationResumeStore
from career_evidence_graph.application_worker import digest
from career_evidence_graph.career_portal_data import CareerCatalog, PortalDataError


@pytest.fixture
def existing_latex(application, tmp_path):
    applications, job = application
    project = tmp_path / "existing-project"
    project.mkdir()
    (project / "main.tex").write_text("Synthetic existing LaTeX source")
    catalog = tmp_path / "career"
    catalog.mkdir()
    store = ApplicationResumeStore(applications, CareerCatalog(catalog), tmp_path / "resumes")
    store.model_runner = lambda *_args, **_kwargs: pytest.fail("No model calls on import")
    store.exporter = lambda *_: pytest.fail("Imported LaTeX cannot use HTML export")

    def verify(task):
        saved = store.draft(task["draft_id"])
        assert saved["draft_sha256"] == task["draft_sha256"]
        assert saved["source_checkpoint"] == task["source_checkpoint"]
        assert saved["task_inputs"] == task["inputs"]

    service = ApplicationFlowService(
        applications,
        tmp_path / "flow",
        preparation_only=True,
        input_provider=lambda _: {"application_revision": job["revision"], "inputs": {"v": "1"}},
        callbacks={
            "prism_source": source_snapshot,
            "import_latex": lambda task, prism: store.import_latex_for_task(
                task["application_id"],
                task["application_revision"],
                task_inputs=task["inputs"],
                prism=prism,
            ),
            "verify_draft": verify,
            "prism_export_configuration": lambda: digest(PrismClient().configuration()),
            "export": lambda task: store.export_for_draft(
                task["draft_id"],
                task["draft_sha256"],
                task_inputs=task["inputs"],
                export_id=task["stages"]["export"]["attempt_id"],
                prism=service.verify_prism_source(task),
            ),
            "reconcile_export": lambda task: store.reconcile_export(
                task["stages"]["export"]["attempt_id"],
                draft_id=task["draft_id"],
                draft_sha256=task["draft_sha256"],
                task_inputs=task["inputs"],
            ),
        },
    )
    try:
        yield service, store, job, project
    finally:
        service.close()


def import_existing(service, job, project):
    return service.request(
        "import-latex",
        {
            "application_id": job["id"],
            "application_revision": job["revision"],
            "project_root": str(project),
            "main": "main.tex",
        },
    )


def authorize(service, task):
    return service.request(
        "authorize-latex-export",
        {
            "task_id": task["id"],
            "task_revision": task["revision"],
            "draft_id": task["draft_id"],
            "draft_sha256": task["draft_sha256"],
        },
    )


def export(service, task):
    return service.export_pdf(task["id"], task["revision"], task["draft_id"], task["draft_sha256"])


def test_import_and_technical_export_do_not_claim_analysis_or_factual_review(
    existing_latex,
    monkeypatch,
):
    service, store, job, project = existing_latex
    task = import_existing(service, job, project)
    draft = store.draft(task["draft_id"])
    assert task["origin"] == draft["origin"] == "existing_latex"
    assert task["analysis_id"] is None and draft["analysis_binding"] == {}
    assert task["draft_review"] is None and task["materials_confirmed"] is False
    assert draft["model_mode"] == "not_used" and draft["items"] == []
    assert draft["factual_review"] == "pending"
    assert draft["language"] == "und"
    with pytest.raises(PortalDataError) as pending:
        export(service, task)
    assert pending.value.code == "flow_latex_export_authorization_required"
    task = authorize(service, task)
    assert task["export_authorization"]["scope"] == "technical_export"
    assert task["draft_review"] is None and not task.get("draft_reviews")
    with compiling_editor(project, monkeypatch) as requests:
        export(service, task)
        task = wait_for(service, task["id"], lambda row: row["status"] == "resume_ready")
        result = store.read_export(task["resume_id"])
        assert result["origin"] == "existing_latex" and result["factual_review"] == "pending"
        assert result["source_checkpoint"] == draft["source_checkpoint"]
        assert (
            result["pdf_sha256"]
            == hashlib.sha256(
                (store.root / task["resume_id"] / "resume.pdf").read_bytes()
            ).hexdigest()
        )
        assert (
            store.reconcile_export(
                task["resume_id"],
                draft_id=task["draft_id"],
                draft_sha256=task["draft_sha256"],
                task_inputs=task["inputs"],
            )
            == result
        )
        assert len([r for r in requests if r[0] == "POST"]) == 1
    with pytest.raises(PortalDataError) as no_factual_acceptance:
        service.confirm_materials(
            task["id"], task["revision"], task["resume_id"], task["resume_sha256"]
        )
    assert no_factual_acceptance.value.code == "flow_factual_review_required"


def test_changed_saved_source_requires_new_checkpoint_and_keeps_previous_pdf(
    existing_latex,
    monkeypatch,
):
    service, store, job, project = existing_latex
    first = authorize(service, import_existing(service, job, project))
    with compiling_editor(project, monkeypatch):
        export(service, first)
        first = wait_for(service, first["id"], lambda row: row["status"] == "resume_ready")
    original = store.read_export(first["resume_id"])
    before = {p: p.read_bytes() for p in store.root.rglob("*") if p.is_file()}
    (project / "main.tex").write_text("Synthetic saved source version two")
    with pytest.raises(PortalDataError) as changed:
        export(service, first)
    assert changed.value.code == "prism_source_changed"
    with pytest.raises(PortalDataError) as cannot_replace:
        service.refresh_prism(first["id"], first["revision"])
    assert cannot_replace.value.code == "flow_latex_reimport_required"
    second = import_existing(service, job, project)
    assert second["id"] != first["id"] and second["draft_id"] != first["draft_id"]
    assert (
        second["source_checkpoint"]["source_revision"]
        != first["source_checkpoint"]["source_revision"]
    )
    assert second["export_authorization"] is None and second["draft_review"] is None
    assert store.read_export(first["resume_id"]) == original
    assert all(path.read_bytes() == raw for path, raw in before.items())
    assert len(service.snapshot()["tasks"]) == 2


def test_unknown_compile_cannot_be_replayed_or_replaced_by_new_import(
    existing_latex,
    monkeypatch,
):
    service, store, job, project = existing_latex
    task = authorize(service, import_existing(service, job, project))
    with compiling_editor(project, monkeypatch, disconnect_build=True) as requests:
        export(service, task)
        task = wait_for(service, task["id"], lambda row: row["status"] == "needs_recheck")
        before = {p: p.read_bytes() for p in store.root.rglob("*") if p.is_file()}
        with pytest.raises(PortalDataError) as pending:
            service.recheck_export(task["id"], task["revision"])
        assert pending.value.code == "resume_export_needs_recheck"
        with pytest.raises(PortalDataError):
            service.export_pdf(
                task["id"], task["revision"], task["draft_id"], task["draft_sha256"], retry=True
            )
        with pytest.raises(PortalDataError) as replacement:
            import_existing(service, job, project)
        assert replacement.value.code == "flow_latex_import_blocked"
        with pytest.raises(PortalDataError) as changed_inputs:
            service.update_inputs(task["id"], task["revision"], job["revision"])
        assert changed_inputs.value.code == "flow_latex_reimport_required"
        current = service.snapshot(task["id"])["active_task"]
        assert current["stages"]["export"] == task["stages"]["export"]
        assert len(service.snapshot()["tasks"]) == 1
        assert before == {p: p.read_bytes() for p in store.root.rglob("*") if p.is_file()}
        assert len([r for r in requests if r[0] == "POST"]) == 1


def test_imported_draft_cannot_fall_back_to_html_or_run_generation(existing_latex):
    service, store, job, project = existing_latex
    task = import_existing(service, job, project)
    with pytest.raises(PortalDataError) as html:
        store.export_for_draft(
            task["draft_id"], task["draft_sha256"], task_inputs=task["inputs"], export_id="f" * 32
        )
    assert html.value.code == "resume_html_retired"
    assert not (store.root / ("f" * 32)).exists()
    with pytest.raises(PortalDataError) as review:
        service.review_draft(task["id"], task["revision"], task["draft_id"], task["draft_sha256"])
    assert review.value.code == "flow_factual_review_required"
    for stage in ("analysis", "resume"):
        service.callbacks[stage] = lambda _: pytest.fail("No generation on imported tasks")
        with pytest.raises(PortalDataError) as generation:
            service.start(task["id"], task["revision"], stage)
        assert generation.value.code == "flow_latex_technical_only"


def test_import_is_not_available_in_explicit_application_mode(application, tmp_path):
    applications, job = application
    service = ApplicationFlowService(applications, tmp_path / "single-job")
    try:
        with pytest.raises(PortalDataError) as mode:
            import_existing(service, job, tmp_path)
        assert mode.value.code == "flow_preparation_required"
        assert service.snapshot()["tasks"] == []
    finally:
        service.close()


def test_import_archive_is_verified_before_authorization_or_export(existing_latex):
    service, store, job, project = existing_latex
    task = import_existing(service, job, project)
    (store.root / task["draft_id"] / "latex-sources.json").write_text("{}")
    with pytest.raises(PortalDataError) as invalid:
        authorize(service, task)
    assert invalid.value.code == "resume_draft_invalid"
    with pytest.raises(PortalDataError) as invalid_export:
        store.export_for_draft(
            task["draft_id"],
            task["draft_sha256"],
            task_inputs=task["inputs"],
            export_id="f" * 32,
            prism=task["prism"],
        )
    assert invalid_export.value.code == "resume_draft_invalid"
    assert not (store.root / ("f" * 32)).exists()


def test_standard_task_creation_does_not_reuse_technical_import_for_batch_generation(
    existing_latex,
):
    service, _, job, project = existing_latex
    original = service.create(job["id"], job["revision"])
    imported = import_existing(service, job, project)
    standard = service.create(job["id"], job["revision"])
    assert standard["id"] not in {original["id"], imported["id"]}
    assert not standard.get("origin") and standard["analysis_id"] is None
    assert standard["stages"]["analysis"]["status"] == "pending"


def test_cancel_cannot_retire_running_or_unknown_imported_compile(existing_latex, monkeypatch):
    service, _, job, project = existing_latex
    task = authorize(service, import_existing(service, job, project))
    started, release = threading.Event(), threading.Event()

    def building():
        started.set()
        assert release.wait(3)

    with compiling_editor(
        project, monkeypatch, on_build=building, disconnect_build=True
    ) as requests:
        try:
            export(service, task)
            assert started.wait(3)
            running = service.snapshot(task["id"])["active_task"]
            assert running["stages"]["export"]["status"] == "running"
            attempt = running["stages"]["export"]["attempt_id"]
            with pytest.raises(PortalDataError) as cancellation:
                service.cancel(running["id"], running["revision"])
            assert cancellation.value.code == "flow_export_recheck_required"
            with pytest.raises(PortalDataError) as replacement:
                import_existing(service, job, project)
            assert replacement.value.code == "flow_latex_import_blocked"
        finally:
            release.set()
        unknown = wait_for(service, task["id"], lambda row: row["status"] == "needs_recheck")
        assert unknown["stages"]["export"]["attempt_id"] == attempt
        with pytest.raises(PortalDataError) as cancellation:
            service.cancel(unknown["id"], unknown["revision"])
        assert cancellation.value.code == "flow_export_recheck_required"
        with pytest.raises(PortalDataError):
            import_existing(service, job, project)
        assert len([row for row in requests if row[0] == "POST"]) == 1


def test_failed_import_retains_technical_scope_and_original_history(existing_latex):
    service, store, job, project = existing_latex
    previous = import_existing(service, job, project)
    before = {p: p.read_bytes() for p in store.root.rglob("*") if p.is_file()}

    def failed_import(*_):
        persisted = service.snapshot()["active_task"]
        assert persisted["origin"] == "existing_latex"
        assert persisted["import_status"]["status"] == "pending"
        raise PortalDataError("prism_source_changed", "Synthetic concurrent saved edit", 409)

    service.callbacks["import_latex"] = failed_import
    with pytest.raises(PortalDataError) as failure:
        import_existing(service, job, project)
    assert failure.value.code == "prism_source_changed"
    failed = service.snapshot()["active_task"]
    assert failed["id"] != previous["id"]
    assert failed["origin"] == "existing_latex" and failed["status"] == "failed"
    assert failed["import_status"] == {"status": "failed", "error_code": "prism_source_changed"}
    assert failed["draft_review"] is None and not failed.get("draft_id")
    for stage in ("analysis", "resume"):
        service.callbacks[stage] = lambda _: pytest.fail("Failed imports cannot start models")
        with pytest.raises(PortalDataError) as forbidden:
            service.start(failed["id"], failed["revision"], stage)
        assert forbidden.value.code == "flow_latex_technical_only"
    assert all(path.read_bytes() == raw for path, raw in before.items())
    assert service.snapshot(previous["id"])["active_task"] == previous
