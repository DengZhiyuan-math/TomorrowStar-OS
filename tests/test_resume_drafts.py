"""LaTeX preparation retains reviewable checkpoints before PDF compilation."""

import hashlib
import json

import pytest
from test_application_resume import task_resume as task_resume
from test_full_latex_generation import full_latex as full_latex
from test_full_latex_generation import generate

from career_evidence_graph.application_prism import source_snapshot
from career_evidence_graph.career_portal_data import PortalDataError


@pytest.fixture
def latex_checkpoint(task_resume, tmp_path):
    store, job, sources, _, calls = task_resume
    inputs = {"career_source_revision": sources["revision"], "policy": "v1.0"}
    project = tmp_path / "checkpoint-source"
    project.mkdir()
    (project / "main.tex").write_text(
        "\\documentclass[a4paper]{article}\n\\begin{document}\n"
        "Synthetic Person\n\\section*{Recovery design}\n"
        "Defined a recovery protocol.\n\\end{document}\n"
    )
    binding = source_snapshot(project, "main.tex")
    result = store.import_latex_for_task(
        job["id"], job["revision"], task_inputs=inputs, prism=binding
    )
    return store, job, result, inputs, calls


def test_preparation_saves_reviewable_latex_draft_without_exporting_pdf(full_latex):
    store, _, _, _, calls, _, _, inputs = full_latex
    result = generate(full_latex)
    assert result["kind"] == "draft"
    assert result["origin"] == "generated_latex"
    assert result["review_status"] == "review_required"
    assert result["language"] == "en"
    assert result["task_inputs"] == inputs
    assert len(calls) == 1
    assert not list(store.root.glob("*/resume.pdf"))
    raw = (store.root / result["id"] / "draft.json").read_bytes()
    assert result["draft_sha256"] == hashlib.sha256(raw).hexdigest()
    assert json.loads(raw)["task_inputs"] == inputs
    assert store.draft(result["id"]) == {
        key: value for key, value in result.items() if key != "measurement_id"
    }


@pytest.mark.parametrize(
    "jd, status",
    [
        ("Please submit your CV in English.", "default_english"),
        ("Submit your resume in German.", "needs_input"),
        ("Envoyez votre CV en français.", "needs_input"),
        ("Bitte den Lebenslauf auf Deutsch einreichen.", "needs_input"),
        ("Submit your CV in English or German.", "default_english"),
        ("CV en français ou en anglais requis.", "default_english"),
        ("Submit your CV in English and German.", "needs_input"),
        ("German B2 required. Upload your CV in PDF format.", "default_english"),
        ("Fluent English and German required.", "default_english"),
        ("Please submit your English-language resume.", "default_english"),
        ("A German-language CV is required.", "needs_input"),
        ("The resume language must be German.", "needs_input"),
        ("German CV required; English proficiency preferred.", "needs_input"),
        ("Your CV must be in both English and German.", "needs_input"),
        ("Submit your CV in English as well as German.", "needs_input"),
        ("Your CV must be German.", "needs_input"),
        ("Please submit your CV translated into German.", "needs_input"),
        ("Submit your CV in Japanese.", "needs_input"),
        ("Submit your CV in Swedish.", "needs_input"),
        ("Submit your CV in English and German or French.", "needs_input"),
        ("请提交法文简历。", "needs_input"),
        ("请提交英文简历。", "default_english"),
        ("Upload your CV in our online portal.", "default_english"),
        ("Your CV should demonstrate proficiency in German.", "default_english"),
        ("The CV must show experience in French markets.", "default_english"),
        ("The resume language must be Swedish.", "needs_input"),
        ("Submit your CV in English and Swedish.", "needs_input"),
        ("Your CV must be PDF format.", "default_english"),
        ("Your CV must be Swedish.", "needs_input"),
        ("Submit your CV in one PDF file.", "default_english"),
        ("CV must be submitted in a single PDF document.", "default_english"),
        ("Please submit your CV in reverse chronological order.", "default_english"),
        ("Please upload your resume in a single column.", "default_english"),
        ("Send your CV in response to this advertisement.", "default_english"),
        ("A Swedish CV is required.", "needs_input"),
        ("Please submit your CVs in English and German.", "needs_input"),
        ("French and English CVs are required.", "needs_input"),
    ],
)
def test_only_explicit_resume_language_requirements_pause_generation(jd, status):
    from career_evidence_graph.application_draft import resume_language_policy

    result = resume_language_policy(jd)
    assert result["status"] == status
    assert result["language"] == ("en" if status == "default_english" else None)
    if status == "needs_input":
        assert result["requirements"][0]["text"] == jd


def test_non_english_submission_requirement_stops_before_model(full_latex):
    from career_evidence_graph.application_flow import job_input_revision

    store, job, _, analysis, calls, _, _, _ = full_latex
    job = store.applications.update_application(
        job["id"], {"job_description": "Submit your CV in German."}, job["revision"]
    )
    analysis["jd_revision"] = job_input_revision(job)
    updated = list(full_latex)
    updated[1] = job
    with pytest.raises(PortalDataError) as failure:
        generate(updated)
    assert failure.value.code == "resume_language_needs_input"
    assert calls == []
    assert not list(store.root.glob("*/draft.json"))


@pytest.mark.parametrize("mutation", ["bytes", "integrity", "symlink", "oversized", "foreign_id"])
def test_draft_read_rejects_damaged_or_redirected_checkpoints(latex_checkpoint, mutation, tmp_path):
    store, _, result, _, calls = latex_checkpoint
    directory = store.root / result["id"]
    if mutation == "bytes":
        (directory / "draft.json").write_bytes(b"{}")
    elif mutation == "integrity":
        (directory / "draft-integrity.json").write_text("{}")
    elif mutation == "symlink":
        foreign = tmp_path / "foreign.json"
        foreign.write_bytes((directory / "draft.json").read_bytes())
        (directory / "draft.json").unlink()
        (directory / "draft.json").symlink_to(foreign)
    elif mutation == "oversized":
        (directory / "draft.json").write_bytes(b" " * 4_000_001)
    else:
        integrity = json.loads((directory / "draft-integrity.json").read_text())
        integrity["id"] = "f" * 32
        (directory / "draft-integrity.json").write_text(json.dumps(integrity))
    with pytest.raises(PortalDataError) as failure:
        store.draft(result["id"])
    assert failure.value.code == "resume_draft_invalid"
    assert calls == []


def test_reading_saved_draft_does_not_recompute_or_mutate_it(latex_checkpoint):
    store, _, result, _, calls = latex_checkpoint
    before = {path: path.read_bytes() for path in store.root.rglob("*") if path.is_file()}
    store.model_runner = lambda *_: pytest.fail("A read must not call a model.")
    reopened = store.draft(result["id"])
    assert reopened["draft_sha256"] == result["draft_sha256"]
    assert before == {path: path.read_bytes() for path in store.root.rglob("*") if path.is_file()}
    assert calls == []
