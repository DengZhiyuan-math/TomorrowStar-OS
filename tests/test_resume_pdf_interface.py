"""PDF lifecycle boundaries preserve original attempts and material identities."""

import hashlib
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest
from test_application_flow import application as application
from test_application_prism import compiling_editor
from test_application_resume import task_resume as task_resume
from test_canonical_career_sources import canonical as canonical
from test_full_latex_generation import full_latex as full_latex
from test_imported_content_mapping import import_mapped
from test_imported_content_mapping import mapped_import as mapped_import
from test_j08_flow_combination import finish_json_writing, start_json_writing
from test_j08_flow_combination import json_flow as json_flow
from test_p05_generation import fixed as fixed
from test_p06_versions import material as material
from test_resume_export import export_draft as export_draft

from career_evidence_graph.application_prism import dependency_snapshot, source_snapshot
from career_evidence_graph.career_portal_data import PortalDataError


def export_task(draft, attempt_id):
    return {
        "id": "5" * 32,
        "application_id": draft["application_id"],
        "analysis_id": draft["analysis_binding"].get("analysis_id"),
        "draft_id": draft["id"],
        "draft_sha256": draft["draft_sha256"],
        "inputs": deepcopy(draft["task_inputs"]),
        "origin": draft["origin"],
        "source_checkpoint": deepcopy(draft["source_checkpoint"]),
        "base_checkpoint": deepcopy(draft.get("base_checkpoint")),
        "latex_base": deepcopy(draft.get("base_checkpoint")),
        "generation_contract": draft.get("generation_contract"),
        "material_version_contract": draft.get("material_version_contract"),
        "automatic_materials": True,
        "artifacts": [{"stage": "resume", "adopted": True, "result": deepcopy(draft)}],
        "stages": {"resume": {}, "export": {"attempt_id": attempt_id}},
    }


def test_reconcile_missing_attempt_never_captures_automatic_pdf(material):
    store, draft, calls = material
    attempt_id = uuid4().hex
    task = export_task(draft, attempt_id)
    store.prism_client.read_compiled = lambda *_: pytest.fail("Reconcile cannot capture a PDF")
    before = {p: p.read_bytes() for p in store.root.rglob("*") if p.is_file()}

    with pytest.raises(PortalDataError) as error:
        store.reconcile_build(task)

    assert error.value.code == "resume_export_needs_recheck"
    assert not (store.root / attempt_id).exists()
    assert before == {p: p.read_bytes() for p in store.root.rglob("*") if p.is_file()}
    assert calls == []


def test_saved_pdf_read_and_reconcile_ignore_later_live_source(material):
    store, draft, calls = material
    attempt_id = uuid4().hex
    saved = store.capture_compiled_pdf(
        draft["id"], draft["draft_sha256"], task_inputs=draft["task_inputs"], export_id=attempt_id
    )
    task = export_task(draft, attempt_id)
    project = Path(draft["source_checkpoint"]["project_root"])
    (project / draft["source_checkpoint"]["main"]).write_text("Later human source")
    store.prism_client.read_compiled = lambda *_: pytest.fail("Read must not contact Prism")
    store.configuration = lambda: pytest.fail("Saved output does not use current settings")
    before = {p: p.read_bytes() for p in store.root.rglob("*") if p.is_file()}

    assert store.read_pdf(saved) == saved
    assert store.reconcile_build(task) == saved
    assert before == {p: p.read_bytes() for p in store.root.rglob("*") if p.is_file()}
    assert calls == []


def test_capture_task_uses_original_automatic_build_and_reuses_completed_result(material):
    store, draft, calls = material
    attempt_id = uuid4().hex
    task = export_task(draft, attempt_id)
    observed = []
    reader = store.prism_client.read_compiled

    def read_compiled(binding):
        observed.append(binding)
        return reader(binding)

    store.prism_client.read_compiled = read_compiled
    assert not (store.root / attempt_id).exists()
    result = store.capture_compiled_pdf(task, request_id=attempt_id)
    assert result["draft_id"] == draft["id"]
    assert len(observed) == 1
    assert store.capture_compiled_pdf(task, request_id=attempt_id) == result
    assert store.build_pdf(task) == result
    assert len(observed) == 1
    assert calls == []


def test_build_legacy_pdf_reuses_original_attempt_after_lost_response(
    export_draft, tmp_path, monkeypatch
):
    store, application, _, inputs, calls = export_draft
    project = tmp_path / "legacy-prism"
    project.mkdir()
    main = project / "main.tex"
    main.write_text("Synthetic manually imported resume")
    binding = source_snapshot(project, "main.tex")
    draft = store.import_latex_for_task(
        application["id"], application["revision"], task_inputs=inputs, prism=binding
    )
    task = export_task(draft, uuid4().hex)
    task["automatic_materials"] = False
    task["prism"] = binding | {
        "draft_id": draft["id"],
        "draft_sha256": draft["draft_sha256"],
    }

    with compiling_editor(project, monkeypatch) as requests:
        result = store.build_pdf(task)
        main.write_text("Later manual source retained after the build")
        assert store.build_pdf(task) == result
        assert store.reconcile_build(task) == result
        assert store.read_pdf(result) == result
        assert len([request for request in requests if request[0] == "POST"]) == 1
    assert calls == []


@pytest.mark.parametrize("field", ["application_id", "draft_sha256", "source_checkpoint", "inputs"])
def test_capture_rejects_wrong_material_binding_before_contacting_prism(material, field):
    store, draft, _ = material
    task = export_task(draft, uuid4().hex)
    task[field] = {"different": "binding"} if isinstance(task[field], dict) else "0" * 64
    store.prism_client.read_compiled = lambda *_: pytest.fail(
        "Wrong reference must not reach Prism"
    )
    with pytest.raises(PortalDataError):
        store.capture_compiled_pdf(task)
    assert not (store.root / task["stages"]["export"]["attempt_id"]).exists()


@pytest.mark.parametrize("field", ["application_id", "pdf_sha256", "draft_id", "source_checkpoint"])
def test_read_pdf_rejects_changed_adopted_reference(material, field):
    store, draft, _ = material
    saved = store.capture_compiled_pdf(
        draft["id"], draft["draft_sha256"], task_inputs=draft["task_inputs"], export_id=uuid4().hex
    )
    changed = deepcopy(saved)
    changed[field] = {"different": "binding"} if isinstance(saved[field], dict) else "0" * 64
    with pytest.raises(PortalDataError) as error:
        store.read_pdf(changed)
    assert error.value.code == "flow_materials_changed"


def test_build_unknown_original_attempt_never_starts_another_compile(
    export_draft, tmp_path, monkeypatch
):
    store, application, _, inputs, _ = export_draft
    project = tmp_path / "unknown-prism"
    project.mkdir()
    (project / "main.tex").write_text("Synthetic unknown build")
    binding = source_snapshot(project, "main.tex")
    draft = store.import_latex_for_task(
        application["id"], application["revision"], task_inputs=inputs, prism=binding
    )
    task = export_task(draft, uuid4().hex)
    task["automatic_materials"] = False
    task["prism"] = binding | {
        "draft_id": draft["id"],
        "draft_sha256": draft["draft_sha256"],
    }
    with compiling_editor(project, monkeypatch, disconnect_build=True) as requests:
        for operation in (store.build_pdf, store.reconcile_build, store.build_pdf):
            with pytest.raises(PortalDataError) as error:
                operation(task)
            assert error.value.code == "resume_export_needs_recheck"
        assert len([request for request in requests if request[0] == "POST"]) == 1


def test_new_request_id_cannot_replace_an_unknown_registered_build(
    export_draft, tmp_path, monkeypatch
):
    store, application, _, inputs, _ = export_draft
    project = tmp_path / "registered-unknown-prism"
    project.mkdir()
    (project / "main.tex").write_text("Synthetic registered unknown build")
    binding = source_snapshot(project, "main.tex")
    draft = store.import_latex_for_task(
        application["id"], application["revision"], task_inputs=inputs, prism=binding
    )
    task = export_task(draft, uuid4().hex)
    task["automatic_materials"] = False
    task["prism"] = binding | {
        "draft_id": draft["id"],
        "draft_sha256": draft["draft_sha256"],
    }
    other_attempt = uuid4().hex
    with compiling_editor(project, monkeypatch, disconnect_build=True) as requests:
        with pytest.raises(PortalDataError):
            store.build_pdf(task)
        with pytest.raises(PortalDataError):
            store.build_pdf(task, request_id=other_attempt)
        assert len([request for request in requests if request[0] == "POST"]) == 1
    assert not (store.root / other_attempt).exists()


@pytest.mark.parametrize("operation", ["build_pdf", "reconcile_build"])
def test_explicit_build_identity_cannot_select_another_completed_capture(material, operation):
    store, draft, _ = material
    task = export_task(draft, uuid4().hex)
    capture_id = uuid4().hex
    saved = store.capture_compiled_pdf(task, request_id=capture_id)
    assert saved["id"] == capture_id
    with pytest.raises(PortalDataError) as error:
        getattr(store, operation)(task, request_id=capture_id)
    assert error.value.code == "resume_export_needs_recheck"
    assert not (store.root / task["stages"]["export"]["attempt_id"]).exists()


@pytest.mark.parametrize("field", ["content_revision", "template_revision", "renderer_revision"])
def test_read_pdf_checks_current_content_identity(json_flow, field):
    task, _ = finish_json_writing(json_flow, start_json_writing(json_flow))
    saved = json_flow.store.capture_compiled_pdf(task, request_id=uuid4().hex)
    assert field in saved
    reference = deepcopy(saved)
    reference[field] = "0" * 64
    with pytest.raises(PortalDataError) as error:
        json_flow.store.read_pdf(reference)
    assert error.value.code == "flow_materials_changed"


def test_mapped_import_successors_and_unmapped_tex_keep_distinct_pdf_versions(mapped_import):
    store, _, project, _ = mapped_import
    parent = import_mapped(mapped_import)
    raw = (Path(__file__).parent / "fixtures/pdf-export/current-template.pdf").read_bytes()

    def read_compiled(binding):
        current = dependency_snapshot(
            Path(binding["project_root"]), binding["main"], binding["files"]
        )
        return {
            "binding": current,
            "pdf": raw,
            "build": {
                "schema_version": "prism-build-result/v1",
                "status": "complete",
                "id": uuid4().hex,
                "main": current["main"],
                "files": current["files"],
                "exit": 0,
                "pdf_updated": True,
                "diagnostics": [],
                "cancelled": False,
                "timed_out": False,
                "pdf_sha256": hashlib.sha256(raw).hexdigest(),
            },
        }

    store.prism_client = SimpleNamespace(
        open=lambda _: "http://127.0.0.1:8799/", read_compiled=read_compiled
    )
    store.model_runner = lambda *_a, **_k: SimpleNamespace(
        structured_result={"patches": [], "notices": []}
    )
    results = []
    previous = parent
    for original, replacement, status in (
        ("Participated in planning a validation workflow.", "Human verified workflow.", "mapped"),
        ("Fixed Applicant", "New human identity", "unmerged"),
    ):
        session = store.begin_prism_edit(
            previous["id"], previous["draft_sha256"], task_inputs=previous["task_inputs"]
        )
        main = project / "main.tex"
        main.write_text(main.read_text().replace(original, replacement))
        child = store.finish_prism_edit(session["id"])
        assert child["content_reconciliation"]["status"] == status
        task = export_task(child, uuid4().hex)
        results.append(store.build_pdf(task))
        previous = child
    assert results[0]["draft_id"] != results[1]["draft_id"]
    assert store.read_pdf(results[0])["draft_id"] == results[0]["draft_id"]
    assert store.read_pdf(results[1])["draft_id"] == previous["id"]
    for field in ("parent_content_ref", "content_reconciliation"):
        assert field in results[1]
        changed = deepcopy(results[1])
        changed[field] = {"unrelated": "version"}
        with pytest.raises(PortalDataError) as error:
            store.read_pdf(changed)
        assert error.value.code == "flow_materials_changed"
    assert "resume_content" not in previous
    assert "New human identity" in previous["latex_source"]
    assert store.draft(parent["id"]) == parent


def test_pdf_integrity_is_revalidated_by_the_owner(material):
    store, draft, _ = material
    task = export_task(draft, uuid4().hex)
    result = store.capture_compiled_pdf(task)
    pdf = store.root / result["id"] / "resume.pdf"
    pdf.write_bytes(pdf.read_bytes() + b"changed")
    with pytest.raises(PortalDataError) as error:
        store.read_pdf(result)
    assert error.value.code == "resume_export_needs_recheck"
    with pytest.raises(PortalDataError):
        store.reconcile_build(task)
