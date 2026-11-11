"""Reviewed match corrections append evidence without replacing existing application materials."""

import json
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest
from test_application_flow import wait_for
from test_application_information import tree_bytes
from test_career_portal_http import portal as portal
from test_job_explanation_browser import explanation_portal

from career_evidence_graph.application_explanations import adopted_analysis
from career_evidence_graph.application_flow import job_input_revision
from career_evidence_graph.application_resume import career_source_snapshot
from career_evidence_graph.application_worker import digest
from career_evidence_graph.career_portal_data import (
    ApplicationStore,
    CareerCatalog,
    PortalDataError,
)

REQUIREMENT = "Implement a Python service."


def saved_latex_material(instance, job, work):
    """Restore legacy LaTeX lineage, isolating only model/compile boundaries."""
    flow = instance.server.application_flow_service
    store = instance.server.application_resume_store
    sources = career_source_snapshot(store.catalog)
    identity = sources["profile_source"]["id"] + ":profile.identity"
    source = next(row for row in sources["items"] if row["resume_eligible"])
    project = flow.root.parent / "match-latex-template"
    project.mkdir()
    (project / "main.tex").write_text(
        "\\documentclass[a4paper]{article}\n\\begin{document}\n"
        "Synthetic Person\n\\section*{Python service}\n"
        "Implemented a Python service.\n\\end{document}\n"
    )
    output = {
        "groups": [
            {
                "title": "Identity",
                "start_line": 1,
                "end_line": 1,
                "source_ids": [identity],
                "latex": "Synthetic Person\n",
                "disposition": "include",
                "reason": "Confirmed synthetic identity",
            },
            {
                "title": "Python service",
                "start_line": 2,
                "end_line": 3,
                "source_ids": [source["source_id"]],
                "latex": "\\section*{Python service}\nImplemented a Python service.\n",
                "disposition": "include",
                "reason": "Literal user contribution",
            },
        ],
        "limitations": [],
    }
    store.model_runner = lambda *_args, **_kwargs: SimpleNamespace(
        structured_result=output, model_dump=lambda **_kwargs: {"synthetic": True}
    )

    def compile_latex(binding):
        work["exports"].append(binding)
        return {
            "build": {"main": binding["main"], "exit": 0, "pdf_updated": True},
            "pdf": (
                Path(__file__).parent / "fixtures/pdf-export/current-template.pdf"
            ).read_bytes(),
        }

    store.prism_client = SimpleNamespace(
        configuration=lambda: {"synthetic": "latex-compile-boundary"}, compile=compile_latex
    )
    task = flow.create(job["id"], job["revision"])
    # This fixture replays pre-JSON material history for match preservation.
    # New default content tasks must never generate these recorded TeX groups.
    with flow.applications.write_lock():
        state = flow._load()
        flow._task(state, task["id"]).pop("material_contract", None)
        flow._save(state)
    task = flow.snapshot(task["id"])["active_task"]
    flow.start(task["id"], task["revision"], "analysis")
    task = wait_for(flow, task["id"], lambda row: row["status"] == "analysis_ready")
    task = flow.prepare_automatic_materials(task["id"], task["revision"], str(project), "main.tex")
    for stage, expected in [("resume", "draft_ready"), ("export", "materials_ready")]:
        flow.start(task["id"], task["revision"], stage)
        task = wait_for(flow, task["id"], lambda row, status=expected: row["status"] == status)
    return task


@pytest.fixture
def retained_match(portal, tmp_path):
    job = ApplicationStore(portal.applications).create_application(
        {
            "company": "Synthetic Match Review",
            "role_title": "Python Engineer",
            "job_description": "Implement reliable Python services.",
        }
    )
    unknown = {
        "text": REQUIREMENT,
        "importance": "required",
        "judgment": "unknown",
        "hard_condition": False,
        "explanation": "Original source correspondence was not verified.",
        "source_ids": [],
        "citations": [],
        "claim_scope": "unknown",
    }
    with explanation_portal(portal, tmp_path, extra_requirements={job["company"]: [unknown]}) as (
        instance,
        work,
    ):
        task = saved_latex_material(instance, job, work)
        flow = instance.server.application_flow_service
        sources = career_source_snapshot(CareerCatalog(portal.career))
        library = {"career_library": {"status": "available", "revision": "c" * 64}}
        flow.information_provider = lambda: deepcopy(library)
        flow.recheck_source_provider = lambda application_id: deepcopy(sources)
        with flow.applications.write_lock():
            state = flow._load()
            row = flow._task(state, task["id"])
            row["codex_handoff_ref"] = {
                "kind": "executor_report",
                "task_id": "retained-upload",
                "status": "ready_for_review",
                "filename": "Synthetic_Final_CV.pdf",
            }
            row["manual_edits"] = {"resume_wording": "Retained user wording."}
            row["history"] = [{"event": "uploaded", "receipt": "already-saved"}]
            flow._save(state)
        task = flow.witness(task["id"])[1]
        other = flow.applications.create_application(
            {
                "company": "Unrelated Employer",
                "role_title": "Other Engineer",
                "job_description": "Another retained job.",
            }
        )
        flow.create(other["id"], other["revision"])
        yield instance, flow, job, task, sources, library, work


def write_review(flow, job, task, sources, library, **changes):
    identifier = uuid4().hex
    item = next(row for row in sources["items"] if row["resume_eligible"])
    document = {
        "schema_version": "match-recheck/v1",
        "application_id": job["id"],
        "task_id": task["id"],
        "base_analysis_id": task["analysis_id"],
        "base_analysis_revision": digest(adopted_analysis(task)),
        "job_binding": job_input_revision(job),
        "library_revision": library["career_library"]["revision"],
        "source_snapshot_revision": sources["revision"],
        "reviewer": "codex",
        "amendments": [
            {
                "requirement_index": 1,
                "requirement_text": REQUIREMENT,
                "judgment": "supported",
                "explanation": "The retained contribution explicitly records implementation.",
                "citations": [{"source_id": item["source_id"], "quote": item["text"]}],
            }
        ],
    } | changes
    path = flow.root / "match-rechecks" / identifier / "review.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(document))
    return identifier, path, document


def attach(flow, task, identifier, library):
    return flow.attach_match_recheck(
        task["id"], task["revision"], identifier, library["career_library"]["revision"]
    )


def original_fields(task):
    return {
        key: deepcopy(value)
        for key, value in task.items()
        if key not in {"revision", "updated_at", "match_rechecks"}
    }


def test_append_match_review_keeps_original_flow_pdf_handoff_manual_edits_and_history(
    retained_match,
):
    instance, flow, job, task, sources, library, work = retained_match
    identifier, _, _ = write_review(flow, job, task, sources, library)
    pdf = flow.root / "resumes" / task["resume_id"] / "resume.pdf"
    pdf_before = pdf.read_bytes()
    calls, exports = deepcopy(work["calls"]), deepcopy(work["exports"])
    other_tasks = [flow.witness(row["id"])[1] for row in flow.snapshot()["tasks"][1:]]
    version_files = {
        key: value for key, value in tree_bytes(flow.root).items() if key != "flow.json"
    }
    original = flow.snapshot(task["id"])["active_explanation"]
    assert original["score"]["lower"] == 50
    attach(flow, task, identifier, library)
    current = flow.witness(task["id"])[1]
    assert original_fields(current) == original_fields(task)
    assert len(current["match_rechecks"]) == 1
    assert current["analysis_id"] == task["analysis_id"]
    explanation = flow.snapshot(task["id"])["active_explanation"]
    assert explanation["score"]["lower"] == 100
    assert explanation["reasons"][1]["judgment"] == "supported"
    assert adopted_analysis(current) == adopted_analysis(task)
    assert [flow.witness(row["id"])[1] for row in other_tasks] == other_tasks
    current_files = tree_bytes(flow.root)
    assert all(current_files.get(key) == value for key, value in version_files.items())
    assert pdf.read_bytes() == pdf_before
    assert work["calls"] == calls and work["exports"] == exports


@pytest.mark.parametrize(
    "change",
    [
        {"application_id": "other-job"},
        {"task_id": "other-task"},
        {"base_analysis_id": "other-analysis"},
        {"base_analysis_revision": "f" * 64},
        {"job_binding": "f" * 64},
        {"library_revision": "f" * 64},
        {"source_snapshot_revision": "f" * 64},
    ],
)
def test_other_job_or_stale_review_is_rejected_without_mutating_existing_materials(
    retained_match, change
):
    _, flow, job, task, sources, library, _ = retained_match
    identifier, _, _ = write_review(flow, job, task, sources, library, **change)
    before = tree_bytes(flow.root)
    with pytest.raises(PortalDataError):
        attach(flow, task, identifier, library)
    assert tree_bytes(flow.root) == before


@pytest.mark.parametrize("tamper", ["quote", "source_id", "requirement_text", "index"])
def test_review_source_tampering_is_rejected_before_adoption(retained_match, tamper):
    _, flow, job, task, sources, library, _ = retained_match
    identifier, path, review = write_review(flow, job, task, sources, library)
    row = review["amendments"][0]
    if tamper == "quote":
        row["citations"][0]["quote"] = "A quotation absent from the verified source."
    elif tamper == "source_id":
        row["citations"][0]["source_id"] = "unrelated-source"
    elif tamper == "requirement_text":
        row["requirement_text"] = "A different requirement."
    else:
        row["requirement_index"] = 999
    path.write_text(json.dumps(review))
    before = tree_bytes(flow.root)
    with pytest.raises(PortalDataError):
        attach(flow, task, identifier, library)
    assert tree_bytes(flow.root) == before


def test_same_review_replay_is_idempotent_and_does_not_duplicate_history(retained_match):
    _, flow, job, task, sources, library, work = retained_match
    identifier, _, _ = write_review(flow, job, task, sources, library)
    attach(flow, task, identifier, library)
    before = tree_bytes(flow.root)
    attach(flow, task, identifier, library)
    assert tree_bytes(flow.root) == before
    assert len(flow.witness(task["id"])[1]["match_rechecks"]) == 1
    assert len(work["exports"]) == 1


def test_changed_current_library_cannot_keep_old_recheck_as_current_match(retained_match):
    _, flow, job, task, sources, library, _ = retained_match
    identifier, _, _ = write_review(flow, job, task, sources, library)
    attach(flow, task, identifier, library)
    before = tree_bytes(flow.root)
    library["career_library"]["revision"] = "d" * 64
    explanation = flow.snapshot(task["id"])["active_explanation"]
    assert explanation["score"]["lower"] == 50
    assert tree_bytes(flow.root) == before


def test_ineligible_source_cannot_support_match_amendment(retained_match):
    _, flow, job, task, sources, library, _ = retained_match
    identifier, path, review = write_review(flow, job, task, sources, library)
    source_id = review["amendments"][0]["citations"][0]["source_id"]
    item = next(row for row in sources["items"] if row["source_id"] == source_id)
    item["resume_eligible"] = False
    sources["revision"] = digest(
        {key: value for key, value in sources.items() if key != "revision"}
    )
    review["source_snapshot_revision"] = sources["revision"]
    path.write_text(json.dumps(review))
    before = tree_bytes(flow.root)
    with pytest.raises(PortalDataError):
        attach(flow, task, identifier, library)
    assert tree_bytes(flow.root) == before
