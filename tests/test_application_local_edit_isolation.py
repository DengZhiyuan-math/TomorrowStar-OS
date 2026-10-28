"""A saved application revision does not correct either documentary library."""

import re
from copy import deepcopy

import pytest
from test_application_flow import wait_for
from test_application_resume import task_resume as task_resume
from test_automatic_material_reuse_edit import complete_portal as complete_portal
from test_full_latex_generation import full_latex as full_latex
from test_installed_write_admission import bytes_under

from career_evidence_graph.application_flow import job_input_revision
from career_evidence_graph.application_information import (
    material_information_library,
    read_information_library,
)
from career_evidence_graph.application_prism import source_snapshot
from career_evidence_graph.application_resume import career_source_snapshot


@pytest.mark.parametrize("complete_portal", [{"confirmed_email": True}], indirect=True)
def test_application_edit_keeps_libraries_and_independent_generation_separate(
    complete_portal, full_latex
):
    server, store, original, generation = complete_portal
    flow = server.application_flow_service
    answers = server.worker_service.store.answers
    career_before = bytes_under(store.catalog.root)
    information_before = bytes_under(answers.root)
    historical_draft = store.draft(original["draft_id"])
    historical_export = store.read_export(original["resume_id"])
    base_before = bytes_under(full_latex[5])

    task = flow.begin_automatic_edit(original["id"], original["revision"])
    draft = store.draft(task["draft_id"])
    omitted = next(group for group in draft["review_groups"] if group["title"] == "Project 3")
    pattern = (
        rf"(?ms)^% TomorrowStar group {omitted['id']} begin\n"
        rf".*?^% TomorrowStar group {omitted['id']} end\n"
    )
    edited_source, count = re.subn(pattern, "", draft["latex_source"])
    assert count == 1
    edited_source = edited_source.replace(
        "Analyzed strategy; built 6 Python services.",
        "Built 6 Python services; analyzed strategy.",
    )
    task = flow.save_automatic_source(
        task["id"], task["revision"], task["prism"]["source_revision"], edited_source
    )
    saved = store.draft(task["draft_id"])
    assert saved["application_id"] == original["application_id"]
    assert saved["latex_source"] == edited_source
    assert [group["title"] for group in saved["omitted_groups"]] == ["Project 3"]
    assert bytes_under(store.catalog.root) == career_before
    assert bytes_under(answers.root) == information_before

    # This is independent preparation via the public store, not an active B Flow
    # or the separately allowed, explicitly checked cross-job material reuse path.
    second_job = store.applications.create_application(
        {
            "company": "Independent synthetic employer",
            "role_title": "Service Engineer",
            "location": "Zurich, Switzerland",
            "job_description": "Build Python services and operate reliable service systems.",
        }
    )
    sources = career_source_snapshot(store.catalog)
    analysis = deepcopy(full_latex[3]) | {
        "id": "independent-second-analysis",
        "application_id": second_job["id"],
        "application_revision": second_job["revision"],
        "jd_revision": job_input_revision(second_job),
        "source_snapshot_revision": sources["revision"],
    }
    library = material_information_library(second_job, read_information_library(answers.root))
    output = full_latex[6]
    # A's confirmed email is application-scoped, so B uses the original identity.
    output["groups"][0]["source_ids"] = output["groups"][0]["source_ids"][:1]
    output["groups"][0]["latex"] = "Synthetic Person\n"
    independent = store.generate_for_task(
        second_job["id"],
        second_job["revision"],
        source_snapshot=sources,
        analysis=analysis,
        draft_only=True,
        task_inputs={
            **full_latex[7],
            "information_library_revision": library["revision"],
        },
        latex_base=source_snapshot(full_latex[5], "main.tex"),
        information_library=library,
    )
    assert independent["application_id"] == second_job["id"]
    assert independent["id"] != saved["id"]
    assert "\\section*{Project 3}" in independent["latex_source"]
    assert "Analyzed strategy; built 6 Python services." in independent["latex_source"]
    assert "Built 6 Python services; analyzed strategy." not in independent["latex_source"]
    assert "job@example.invalid" not in independent["latex_source"]
    assert "job@example.invalid" not in str(generation[-1]["sources"])
    assert generation[-1]["base"] == (full_latex[5] / "main.tex").read_text()
    assert len(generation) == 2
    assert bytes_under(store.catalog.root) == career_before
    assert bytes_under(answers.root) == information_before
    assert bytes_under(full_latex[5]) == base_before

    flow.start(task["id"], task["revision"], "export")
    continued = wait_for(
        flow,
        task["id"],
        lambda row: row["status"] in {"materials_ready", "failed", "needs_recheck"},
    )
    assert continued["status"] == "materials_ready", continued["stages"]
    assert store.read_export(continued["resume_id"])["latex_source"] == edited_source
    assert store.draft(saved["id"]) == saved
    assert store.draft(original["draft_id"]) == historical_draft
    assert store.read_export(original["resume_id"]) == historical_export
    assert bytes_under(store.catalog.root) == career_before
    assert bytes_under(answers.root) == information_before
    assert (
        answers.find_answer("Email", {"application_id": original["application_id"]})["value"]
        == "job@example.invalid"
    )
    assert answers.find_answer("Email", {"application_id": second_job["id"]}) is None
