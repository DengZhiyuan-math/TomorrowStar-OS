"""Human versions and final PDFs retain local provenance without upstream re-review."""

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest
from test_application_resume import task_resume as task_resume
from test_full_latex_generation import full_latex as full_latex
from test_p05_generation import complete, submit
from test_p05_generation import fixed as fixed

from career_evidence_graph import application_experience_latex as generation
from career_evidence_graph.application_worker import digest
from career_evidence_graph.career_portal_data import PortalDataError


@pytest.fixture
def material(fixed):
    store = fixed[0][0]
    candidate = complete(fixed)
    generation.review_generation(
        store,
        fixed[1]["id"],
        candidate_sha256=candidate["candidate_sha256"],
        reviewer_id="final-reviewer",
        passed=True,
        issues=[],
    )
    draft = generation.adopt_generation(store, fixed[1]["id"])
    calls = []

    def runner(config, prompt, **kwargs):
        calls.append(prompt)
        return SimpleNamespace(structured_result={"patches": [], "notices": []})

    class Prism:
        def open(self, binding):
            return "http://127.0.0.1:8799/"

        def compile(self, binding):
            pytest.fail("P06 must never request a build")

        def apply_proofread(self, binding, expected, replacement):
            main = Path(binding["project_root"]) / binding["main"]
            assert main.read_text() == expected
            main.write_text(replacement)

        def read_compiled(self, binding):
            from career_evidence_graph.application_prism import dependency_snapshot

            current = dependency_snapshot(
                Path(binding["project_root"]), binding["main"], binding["files"]
            )
            raw = (Path(__file__).parent / "fixtures/pdf-export/current-template.pdf").read_bytes()
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

    store.model_runner = runner
    store.prism_client = Prism()
    return store, draft, calls


def test_explicit_prism_return_preserves_human_facts_layout_and_prior_ai_review(
    material, monkeypatch
):
    store, parent, calls = material
    session = store.begin_prism_edit(
        parent["id"], parent["draft_sha256"], task_inputs=parent["task_inputs"]
    )
    assert session["status"] == "editing"
    assert calls == []
    source = Path(session["project_root"]) / session["main"]
    edited = parent["latex_source"].replace(
        "\\begin{document}", "\\begin{document}\nA new HUMAN fact in custom order.\n"
    )
    edited = edited.replace("\\begin{document}", "\\setlength{\\parindent}{7pt}\n\\begin{document}")
    source.write_text(edited)
    monkeypatch.setattr(store, "_task_current", lambda *a, **k: pytest.fail("No upstream recheck"))
    result = store.finish_prism_edit(session["id"])
    assert result["latex_source"] == edited
    assert result["material_version_contract"] == "local-material/v1"
    assert result["upstream_final_review"] == parent["final_review"]
    assert "final_review" not in result
    assert len(calls) == 1
    assert store.finish_prism_edit(session["id"])["id"] == result["id"]
    assert len(calls) == 1
    assert store.draft(parent["id"])["latex_source"] == parent["latex_source"]


def test_new_user_edit_during_proofreading_is_never_overwritten(material):
    store, parent, calls = material
    session = store.begin_prism_edit(
        parent["id"], parent["draft_sha256"], task_inputs=parent["task_inputs"]
    )
    source = Path(session["project_root"]) / session["main"]
    captured = source.read_text()

    def runner(*args, **kwargs):
        source.write_text(captured + "\n% a newer human edit\n")
        return SimpleNamespace(structured_result={"patches": [], "notices": []})

    store.model_runner = runner
    result = store.finish_prism_edit(session["id"])
    assert result["prism_edit"]["status"] == "source_changed"
    assert source.read_text().endswith("% a newer human edit\n")
    assert result["latex_source"] == captured
    assert store.draft(result["id"])["latex_source"] == captured


def test_missing_proofreader_retains_manual_version_without_implicit_retry(material):
    store, parent, calls = material
    session = store.begin_prism_edit(
        parent["id"], parent["draft_sha256"], task_inputs=parent["task_inputs"]
    )
    count = []

    def unavailable(*args, **kwargs):
        count.append(True)
        raise OSError("synthetic unavailable")

    store.model_runner = unavailable
    result = store.finish_prism_edit(session["id"])
    assert result["prism_edit"]["status"] == "proofreading_unavailable"
    assert result["latex_source"] == parent["latex_source"]
    assert store.finish_prism_edit(session["id"])["id"] == result["id"]
    assert count == [True]


def test_final_pdf_read_ignores_live_library_jd_config_and_unrelated_files(material, monkeypatch):
    store, draft, calls = material
    result = store.capture_compiled_pdf(
        draft["id"], draft["draft_sha256"], task_inputs=draft["task_inputs"], export_id=uuid4().hex
    )
    root = Path(draft["source_checkpoint"]["project_root"])
    (root / "unrelated-notes.md").write_text("unrelated")
    (root / draft["source_checkpoint"]["main"]).write_text("new manual version not yet exported")
    monkeypatch.setattr(store, "configuration", lambda: pytest.fail("No current config gate"))
    monkeypatch.setattr(store, "_task_current", lambda *a, **k: pytest.fail("No current sources"))
    store.prism_client.read_compiled = lambda *a: pytest.fail("History read cannot contact Prism")
    store.pdf_inspector = lambda *a: pytest.fail("Historical bytes already validated at adoption")
    assert store.read_export(result["id"])["pdf_sha256"] == result["pdf_sha256"]
    assert store.pdf(result["id"]).startswith(b"%PDF-")
    assert calls == []


def test_late_compile_result_does_not_adopt_over_new_human_source(material):
    store, draft, calls = material
    reader = store.prism_client.read_compiled

    def late(binding):
        result = reader(binding)
        (Path(binding["project_root"]) / binding["main"]).write_text("a newer source")
        return result

    store.prism_client.read_compiled = late
    export_id = uuid4().hex
    with pytest.raises(PortalDataError):
        store.capture_compiled_pdf(
            draft["id"],
            draft["draft_sha256"],
            task_inputs=draft["task_inputs"],
            export_id=export_id,
        )
    assert not (store.root / export_id / "export.json").exists()


def test_saved_pdf_tamper_is_rejected_without_recompile(material):
    store, draft, calls = material
    result = store.capture_compiled_pdf(
        draft["id"], draft["draft_sha256"], task_inputs=draft["task_inputs"], export_id=uuid4().hex
    )
    (store.root / result["id"] / "resume.pdf").write_bytes(b"%PDF-1.4 corrupt")
    with pytest.raises(PortalDataError):
        store.pdf(result["id"])


def test_manual_version_archive_and_patch_history_are_verified(material):
    store, draft, calls = material
    session = store.begin_prism_edit(
        draft["id"], draft["draft_sha256"], task_inputs=draft["task_inputs"]
    )
    result = store.finish_prism_edit(session["id"])
    directory = store.root / result["id"]
    raw = json.loads((directory / "draft.json").read_text())
    raw["proofreading"]["after_sha256"] = digest("different")
    from career_evidence_graph._vendor import job_apply_store as helper

    helper.atomic_write_json(directory / "draft.json", raw)
    helper.atomic_write_json(
        directory / "draft-integrity.json",
        {
            "schemaVersion": 1,
            "id": result["id"],
            "sha256": hashlib.sha256((directory / "draft.json").read_bytes()).hexdigest(),
        },
    )
    with pytest.raises(PortalDataError):
        store.draft(result["id"])


@pytest.mark.parametrize("save_conflict", [False, True])
def test_small_proofread_patch_uses_conditional_save_and_preserves_history(material, save_conflict):
    store, parent, calls = material
    session = store.begin_prism_edit(
        parent["id"], parent["draft_sha256"], task_inputs=parent["task_inputs"]
    )
    main = Path(session["project_root"]) / session["main"]
    manual = parent["latex_source"].replace(
        "\\end{document}", "we recieve reliable output.\n\\end{document}"
    )
    main.write_text(manual)
    offset = manual.index("recieve")
    patch = {
        "start": offset,
        "end": offset + 7,
        "before": "recieve",
        "after": "receive",
        "kind": "spelling",
        "reason": "Clear spelling error",
    }
    store.model_runner = lambda *a, **k: SimpleNamespace(
        structured_result={"patches": [patch], "notices": []}
    )
    if save_conflict:

        def changed(*args):
            main.write_text(manual + "\n% newer user save\n")
            raise PortalDataError("prism_edit_needs_recheck", "synthetic conflict", 409)

        store.prism_client.apply_proofread = changed
    result = store.finish_prism_edit(session["id"])
    assert store.draft(parent["id"])["latex_source"] == parent["latex_source"]
    if save_conflict:
        assert result["prism_edit"]["status"] == "source_changed"
        assert main.read_text().endswith("% newer user save\n")
        assert result["latex_source"] == manual
    else:
        assert result["prism_edit"]["status"] == "complete"
        assert result["latex_source"] == manual.replace("recieve", "receive")
        assert main.read_text() == result["latex_source"]
        assert result["proofreading"]["patches"] == [patch]
        assert store.draft(result["id"])["latex_source"] == result["latex_source"]


@pytest.mark.parametrize(
    "field,value",
    [
        ("status", "failed"),
        ("cancelled", True),
        ("timed_out", True),
        ("exit", 1),
        ("diagnostics", [{"severity": "error", "message": "tool failed"}]),
        ("diagnostics", None),
    ],
)
def test_only_complete_success_receipt_can_be_adopted(material, field, value):
    store, draft, calls = material
    reader = store.prism_client.read_compiled

    def failed(binding):
        result = reader(binding)
        result["build"][field] = value
        return result

    store.prism_client.read_compiled = failed
    with pytest.raises(PortalDataError):
        store.capture_compiled_pdf(
            draft["id"],
            draft["draft_sha256"],
            task_inputs=draft["task_inputs"],
            export_id=uuid4().hex,
        )


def test_export_id_cannot_be_reused_for_a_different_source_version(material):
    store, parent, calls = material
    first = store.capture_compiled_pdf(
        parent["id"],
        parent["draft_sha256"],
        task_inputs=parent["task_inputs"],
        export_id=uuid4().hex,
    )
    session = store.begin_prism_edit(
        parent["id"], parent["draft_sha256"], task_inputs=parent["task_inputs"]
    )
    main = Path(session["project_root"]) / session["main"]
    main.write_text(main.read_text() + "\n% new user version\n")
    later = store.finish_prism_edit(session["id"])
    with pytest.raises(PortalDataError):
        store.capture_compiled_pdf(
            later["id"],
            later["draft_sha256"],
            task_inputs=later["task_inputs"],
            export_id=first["id"],
        )
    second = store.capture_compiled_pdf(
        later["id"], later["draft_sha256"], task_inputs=later["task_inputs"], export_id=uuid4().hex
    )
    assert store.read_export(first["id"])["draft_id"] == parent["id"]
    assert store.read_export(second["id"])["draft_id"] == later["id"]


def test_mutable_edit_receipt_cannot_redirect_a_completed_result(material):
    store, parent, calls = material
    first = store.begin_prism_edit(
        parent["id"], parent["draft_sha256"], task_inputs=parent["task_inputs"]
    )
    store.finish_prism_edit(first["id"])
    second = store.begin_prism_edit(
        parent["id"], parent["draft_sha256"], task_inputs=parent["task_inputs"]
    )
    other = store.finish_prism_edit(second["id"])
    path = store.root / first["id"] / "edit-session.json"
    value = json.loads(path.read_text())
    value["draft_id"] = other["id"]
    path.write_text(json.dumps(value))
    with pytest.raises(PortalDataError):
        store.finish_prism_edit(first["id"])


def test_multifile_text_is_preserved_without_claiming_complete_proofreading(material):
    store, parent, calls = material
    edit = store.begin_prism_edit(
        parent["id"], parent["draft_sha256"], task_inputs=parent["task_inputs"]
    )
    main = Path(edit["project_root"]) / edit["main"]
    text = parent["latex_source"].replace("\\end{document}", "\\input{section}\n\\end{document}")
    main.write_text(text)
    result = store.finish_prism_edit(edit["id"])
    assert result["prism_edit"]["status"] == "proofreading_unavailable"
    assert result["latex_source"] == text
    assert calls == []


def test_manual_version_is_a_retained_successor_base_with_omission_history(fixed):
    store = fixed[0][0]
    for index in range(5):
        submit(fixed, index)
    context = generation.writer_context(store, fixed[1]["id"], "experience-6")
    group = dict(context["groups"][0], disposition="omit", reason="Retain original omission")
    generation.submit_fragment(
        store,
        fixed[1]["id"],
        "experience-6",
        input_revision=context["input_revision"],
        groups=[group],
        used_refs=context["source_ids"],
        issues=[],
        writer_id="writer-6",
    )
    candidate = generation.assemble_generation(store, fixed[1]["id"])
    generation.review_generation(
        store,
        fixed[1]["id"],
        candidate_sha256=candidate["candidate_sha256"],
        reviewer_id="final-reviewer",
        passed=True,
        issues=[],
    )
    parent = generation.adopt_generation(store, fixed[1]["id"])
    store.prism_client = SimpleNamespace(open=lambda binding: "http://127.0.0.1:8799/")
    store.model_runner = lambda *a, **k: SimpleNamespace(
        structured_result={"patches": [], "notices": []}
    )
    edit = store.begin_prism_edit(
        parent["id"], parent["draft_sha256"], task_inputs=parent["task_inputs"]
    )
    main = Path(edit["project_root"]) / edit["main"]
    manual_text = main.read_text().replace(
        "\\end{document}", "Human custom wording.\n\\end{document}"
    )
    main.write_text(manual_text)
    manual = store.finish_prism_edit(edit["id"])
    assert manual["retained_omissions"][0]["title"] == "Project 6"
    state = generation.prepare_generation(
        store,
        fixed[0][1]["id"],
        fixed[0][1]["revision"],
        source_snapshot=fixed[0][2],
        analysis=fixed[0][3],
        task_inputs=fixed[0][7],
        latex_base=manual["source_checkpoint"],
        retained_draft=manual,
    )
    context = generation.generation_context(store, state["id"])
    generation.configure_generation(
        store,
        state["id"],
        groups=context["retained_output"]["groups"],
        experiences=[],
        organization_plan={
            "summary_focus": "Retain human wording",
            "ordering_rationale": "Keep manual order",
        },
    )
    candidate = generation.assemble_generation(store, state["id"])
    assert candidate["latex_source"] == manual_text
    generation.review_generation(
        store,
        state["id"],
        candidate_sha256=candidate["candidate_sha256"],
        reviewer_id="next-final-reviewer",
        passed=True,
        issues=[],
    )
    result = generation.adopt_generation(store, state["id"])
    assert result["latex_source"] == manual_text
    assert result["retained_omissions"][0]["title"] == "Project 6"
    assert "Project 6" not in result["latex_source"]
