"""Pending factual groups can be refreshed without discarding later manual TeX."""

import pytest
from test_application_flow import wait_for
from test_application_resume import task_resume as task_resume
from test_automatic_material_reuse_edit import complete_portal as complete_portal
from test_flow_tex_impact_updates import refresh_tex, save_manual_wording
from test_flow_tex_impact_updates import update_model as update_model
from test_flow_tex_impact_updates import update_portal as update_portal
from test_full_latex_generation import full_latex as full_latex


@pytest.mark.parametrize("correction", ["jd", "source"])
def test_saved_manual_edit_merges_with_resolved_pending_group(update_portal, correction):
    server, store, original, _generation, model = update_portal
    flow = server.application_flow_service
    manual = save_manual_wording(flow, store, original)
    job = store.applications.get_application(original["application_id"])
    job = store.applications.update_application(
        job["id"],
        {"job_description": job["job_description"] + " Personal delivery required."},
        job["revision"],
    )
    model.update(active=True, verify=True)
    pending = refresh_tex(flow, manual, job)
    pending_draft = store.draft(pending["draft_id"])
    assert [g["title"] for g in pending_draft["verification_queue"]] == ["Project 1"]
    editable = flow.begin_automatic_edit(pending["id"], pending["revision"])
    text = store.draft(editable["draft_id"])["latex_source"].replace(
        "Built 6 Python services; analyzed strategy.",
        "Built 6 Python services and analyzed strategy.",
    )
    saved = flow.save_automatic_source(
        editable["id"], editable["revision"], editable["prism"]["source_revision"], text
    )
    saved_draft = store.draft(saved["draft_id"])
    model.update(verify=False)
    if correction == "source":
        original_runner = store.model_runner

        def corrected_model(config, prompt, **kwargs):
            result = original_runner(config, prompt, **kwargs)
            for group in result.structured_result["groups"]:
                if group["title"] == "Project 1":
                    group["latex"] = group["latex"].replace("Built 1 Python", "Built 11 Python")
            return result

        store.model_runner = corrected_model
        document = store.catalog.root / "contributions/project-1.md"
        document.write_text(document.read_text().replace("built 1 Python", "built 11 Python"))
    else:
        job = store.applications.update_application(
            job["id"],
            {"job_description": "Build Python services without the prior requirement."},
            job["revision"],
        )
    task = refresh_tex(flow, saved, job)
    assert task["status"] == "draft_ready", task["stages"]
    result = store.draft(task["draft_id"])
    assert not result["verification_queue"]
    expected = (
        "Built 11 Python services; analyzed strategy."
        if correction == "source"
        else "Built 1 Python services; analyzed strategy."
    )
    assert expected in result["latex_source"]
    assert "Built 6 Python services and analyzed strategy." in result["latex_source"]
    assert result["latex_source"].index("Project 1") < result["latex_source"].index("Project 2")
    assert store.draft(saved["draft_id"]) == saved_draft
    assert store.draft(pending["draft_id"]) == pending_draft
    flow.start(task["id"], task["revision"], "export")
    exported = wait_for(
        flow,
        task["id"],
        lambda row: row["status"] in {"materials_ready", "failed", "needs_recheck"},
    )
    assert exported["status"] == "materials_ready", exported["stages"]


def test_remaining_conflict_keeps_manual_edits_until_a_later_resolved_refresh(update_portal):
    from career_evidence_graph.career_portal_data import PortalDataError

    server, store, original, _generation, model = update_portal
    flow = server.application_flow_service
    manual = save_manual_wording(flow, store, original)
    job = store.applications.get_application(original["application_id"])
    job = store.applications.update_application(
        job["id"],
        {"job_description": job["job_description"] + " Personal delivery required."},
        job["revision"],
    )
    model.update(active=True, verify=True)
    pending = refresh_tex(flow, manual, job)
    editable = flow.begin_automatic_edit(pending["id"], pending["revision"])
    text = store.draft(editable["draft_id"])["latex_source"].replace(
        "Built 6 Python services; analyzed strategy.",
        "Built 6 Python services and analyzed strategy.",
    )
    saved = flow.save_automatic_source(
        editable["id"], editable["revision"], editable["prism"]["source_revision"], text
    )
    job = store.applications.update_application(
        job["id"], {"location": "Synthetic location correction"}, job["revision"]
    )
    model["affected"] = []
    task = refresh_tex(flow, saved, job)
    assert task["status"] == "draft_ready", task["stages"]
    current = store.draft(task["draft_id"])
    assert [g["title"] for g in current["verification_queue"]] == ["Project 1"]
    assert "Project 1" not in current["latex_source"]
    assert "Built 6 Python services and analyzed strategy." in current["latex_source"]
    compiles = len(store.prism_client.calls)
    with pytest.raises(PortalDataError) as caught:
        flow.start(task["id"], task["revision"], "export")
    assert caught.value.code == "resume_group_verification_required"
    assert len(store.prism_client.calls) == compiles

    # A new manual change on an already merged pending result must survive again.
    editable = flow.begin_automatic_edit(task["id"], task["revision"])
    text = store.draft(editable["draft_id"])["latex_source"].replace(
        "Analyzed strategy; built 5 Python services.",
        "Built 5 Python services; analyzed strategy.",
    )
    saved = flow.save_automatic_source(
        editable["id"], editable["revision"], editable["prism"]["source_revision"], text
    )
    job = store.applications.update_application(
        job["id"],
        {"job_description": "Build Python services without the prior requirement."},
        job["revision"],
    )
    model["verify"] = False
    task = refresh_tex(flow, saved, job)
    assert task["status"] == "draft_ready", task["stages"]
    result = store.draft(task["draft_id"])
    assert not result["verification_queue"]
    assert "Built 5 Python services; analyzed strategy." in result["latex_source"]
    assert "Built 6 Python services and analyzed strategy." in result["latex_source"]
    assert "Built 1 Python services; analyzed strategy." in result["latex_source"]
    assert store.draft(saved["draft_id"])["latex_source"] == text
