"""Prism PDF adoption retains the exact LaTeX source and existing review bindings."""

import hashlib
from pathlib import Path

import pytest
from test_application_prism import compiling_editor
from test_application_resume import task_resume as task_resume
from test_native_pdf_inspection import native_pdf_inspector as native_pdf_inspector
from test_resume_export import export_draft as export_draft

from career_evidence_graph.application_prism import source_snapshot
from career_evidence_graph.career_portal_data import PortalDataError


def test_prism_export_saves_same_source_and_pdf_without_calling_the_html_exporter(
    export_draft, tmp_path, monkeypatch
):
    store, job, draft, inputs, calls = export_draft
    project = tmp_path / "review"
    project.mkdir()
    main = project / "main.tex"
    main.write_text("Synthetic reviewed LaTeX source")
    binding = source_snapshot(project, "main.tex")
    draft = store.import_latex_for_task(
        job["id"], job["revision"], task_inputs=inputs, prism=binding
    )
    store.exporter = lambda *_: pytest.fail("Bound LaTeX must not reach the HTML exporter")
    with compiling_editor(project, monkeypatch) as requests:
        result = store.export_for_draft(
            draft["id"],
            draft["draft_sha256"],
            task_inputs=inputs,
            export_id="1" * 32,
            prism=binding,
        )
    directory = store.root / result["id"]
    assert result["prism_source_revision"] == binding["source_revision"]
    assert (
        result["pdf_sha256"] == hashlib.sha256((directory / "resume.pdf").read_bytes()).hexdigest()
    )
    assert (directory / "resume.tex").read_bytes() == main.read_bytes()
    assert not (directory / "resume.html").exists()
    original = {path: path.read_bytes() for path in directory.iterdir()}
    main.write_text("Later user edit")
    assert store.read_export(result["id"])["prism_source_revision"] == binding["source_revision"]
    assert original == {path: path.read_bytes() for path in directory.iterdir()}
    assert not calls
    assert len([request for request in requests if request[0] == "POST"]) == 1


def test_unknown_prism_compile_is_not_reclassified_or_replayed_when_local_manifest_is_absent(
    export_draft, tmp_path, monkeypatch
):
    store, job, draft, inputs, _ = export_draft
    project = tmp_path / "review"
    project.mkdir()
    (project / "main.tex").write_text("Synthetic reviewed source")
    binding = source_snapshot(project, "main.tex")
    draft = store.import_latex_for_task(
        job["id"], job["revision"], task_inputs=inputs, prism=binding
    )
    running = []
    with compiling_editor(
        project, monkeypatch, on_build=lambda: running.append(True), disconnect_build=True
    ) as requests:
        with pytest.raises(PortalDataError) as error:
            store.export_for_draft(
                draft["id"],
                draft["draft_sha256"],
                task_inputs=inputs,
                export_id="1" * 32,
                prism=binding,
            )
        assert error.value.code == "resume_export_needs_recheck"
        assert running == [True]
        assert not (store.root / ("1" * 32) / "export.json").exists()
        for _ in range(2):
            with pytest.raises(PortalDataError) as pending:
                store.reconcile_export(
                    "1" * 32,
                    draft_id=draft["id"],
                    draft_sha256=draft["draft_sha256"],
                    task_inputs=inputs,
                )
            assert pending.value.code == "resume_export_needs_recheck"
        assert len([request for request in requests if request[0] == "POST"]) == 1


def test_compressed_prism_pdf_exports_and_reopens_without_rebuilding(
    export_draft, tmp_path, monkeypatch, native_pdf_inspector
):
    store, job, draft, inputs, calls = export_draft
    store.pdf_inspector = native_pdf_inspector
    project = tmp_path / "compressed-review"
    project.mkdir()
    (project / "main.tex").write_text("Synthetic compressed PDF source")
    binding = source_snapshot(project, "main.tex")
    draft = store.import_latex_for_task(
        job["id"], job["revision"], task_inputs=inputs, prism=binding
    )
    raw = (Path(__file__).parent / "fixtures/pdf-export/tectonic-compressed.pdf").read_bytes()
    with compiling_editor(project, monkeypatch, pdf_bytes=raw) as requests:
        result = store.export_for_draft(
            draft["id"],
            draft["draft_sha256"],
            task_inputs=inputs,
            export_id="2" * 32,
            prism=binding,
        )
        assert native_pdf_inspector(raw) == 4
        assert result["pdf_sha256"] == hashlib.sha256(raw).hexdigest()
        assert result["prism_source_revision"] == binding["source_revision"]
        before = {path: path.read_bytes() for path in store.root.rglob("*") if path.is_file()}
        (project / "main.tex").write_text("Later edited synthetic source")
        assert store.read_export(result["id"]) == result
        assert (
            store.reconcile_export(
                result["id"],
                draft_id=draft["id"],
                draft_sha256=draft["draft_sha256"],
                task_inputs=inputs,
            )
            == result
        )
        assert before == {
            path: path.read_bytes() for path in store.root.rglob("*") if path.is_file()
        }
        assert len([request for request in requests if request[0] == "POST"]) == 1
    assert not calls


def test_unavailable_prism_pdf_inspection_retains_unknown_attempt_without_recompile(
    export_draft, tmp_path, monkeypatch
):
    store, job, draft, inputs, _ = export_draft

    def unavailable(_raw):
        raise PortalDataError(
            "resume_pdf_inspection_unavailable", "Synthetic unavailable PDFKit", 409
        )

    store.pdf_inspector = unavailable
    project = tmp_path / "pending-inspection"
    project.mkdir()
    (project / "main.tex").write_text("Synthetic pending inspection")
    binding = source_snapshot(project, "main.tex")
    draft = store.import_latex_for_task(
        job["id"], job["revision"], task_inputs=inputs, prism=binding
    )
    with compiling_editor(project, monkeypatch) as requests:
        with pytest.raises(PortalDataError) as error:
            store.export_for_draft(
                draft["id"],
                draft["draft_sha256"],
                task_inputs=inputs,
                export_id="3" * 32,
                prism=binding,
            )
        assert error.value.code == "resume_export_needs_recheck"
        directory = store.root / ("3" * 32)
        assert (directory / "resume.pdf").is_file()
        assert not (directory / "export.json").exists()
        before = {path: path.read_bytes() for path in directory.iterdir()}
        with pytest.raises(PortalDataError) as pending:
            store.reconcile_export(
                "3" * 32,
                draft_id=draft["id"],
                draft_sha256=draft["draft_sha256"],
                task_inputs=inputs,
            )
        assert pending.value.code == "resume_export_needs_recheck"
        assert before == {path: path.read_bytes() for path in directory.iterdir()}
        assert len([request for request in requests if request[0] == "POST"]) == 1
