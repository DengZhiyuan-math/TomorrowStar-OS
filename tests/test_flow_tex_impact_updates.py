"""Source and JD refreshes use the last adopted TeX instead of rewriting valid text."""

import json
import re
from copy import deepcopy
from types import SimpleNamespace

import pytest
from test_application_flow import wait_for
from test_application_resume import task_resume as task_resume
from test_automatic_material_reuse_edit import complete_portal as complete_portal
from test_full_latex_generation import full_latex as full_latex

from career_evidence_graph.application_resume import career_source_snapshot
from career_evidence_graph.career_portal_data import PortalDataError


@pytest.fixture
def update_model(full_latex):
    store = full_latex[0]
    initial = store.model_runner
    state = {"active": False, "affected": [1], "requests": [], "verify": False}

    def model(config, prompt, **kwargs):
        if not state["active"]:
            return initial(config, prompt, **kwargs)
        payload = json.loads(prompt[prompt.index("{") :])
        state["requests"].append(payload)
        groups = deepcopy(payload["update_context"]["retained_groups"])
        groups[1]["latex"] = groups[1]["latex"].replace(
            "Analyzed strategy; built 1 Python services.",
            "Built 1 Python services; analyzed strategy.",
        )
        # An unrelated model rewrite must not erase the saved manual wording.
        groups[6]["latex"] = groups[6]["latex"].replace(
            "Built 6 Python services; analyzed strategy.",
            "Analyzed strategy; built 6 Python services.",
        )
        if state["verify"]:
            groups[1].update(disposition="verify", reason="Important responsibility conflict")
        return SimpleNamespace(
            structured_result={
                "groups": groups,
                "limitations": [],
                "affected_group_indexes": state["affected"],
            },
            model_dump=lambda **_: {"synthetic": True},
        )

    store.model_runner = model
    return state


@pytest.fixture
def update_portal(update_model, complete_portal):
    return (*complete_portal, update_model)


def refresh_tex(flow, task, job):
    task = flow.update_inputs(task["id"], task["revision"], job["revision"])
    if task["analysis_id"] is None:
        flow.start(task["id"], task["revision"], "analysis")
        task = wait_for(flow, task["id"], lambda row: row["status"] == "analysis_ready")
    flow.start(task["id"], task["revision"], "resume")
    return wait_for(flow, task["id"], lambda row: row["status"] in {"draft_ready", "failed"})


def save_manual_wording(flow, store, task):
    task = flow.begin_automatic_edit(task["id"], task["revision"])
    text = store.draft(task["draft_id"])["latex_source"].replace(
        "Analyzed strategy; built 6 Python services.",
        "Built 6 Python services; analyzed strategy.",
    )
    return flow.save_automatic_source(
        task["id"], task["revision"], task["prism"]["source_revision"], text
    )


def test_unprinted_profile_update_keeps_unedited_adopted_tex_without_model(complete_portal):
    server, store, original, generation = complete_portal
    flow = server.application_flow_service
    old_draft = store.draft(original["draft_id"])
    old_pdf = store.pdf(original["resume_id"])
    profile = store.catalog.get_evidence(
        career_source_snapshot(store.catalog)["profile_source"]["id"]
    )
    store.catalog.update_evidence(
        profile["id"],
        profile["revision"],
        json.dumps(json.loads(profile["content"]) | {"title": "Updated unprinted headline"}),
        actor="user",
        source="Explicit synthetic profile correction",
    )
    job = store.applications.get_application(original["application_id"])
    task = flow.update_inputs(original["id"], original["revision"], job["revision"])
    flow.start(task["id"], task["revision"], "analysis")
    task = wait_for(flow, task["id"], lambda row: row["status"] == "analysis_ready")
    flow.start(task["id"], task["revision"], "resume")
    task = wait_for(flow, task["id"], lambda row: row["status"] in {"draft_ready", "failed"})
    assert task["status"] == "draft_ready", task["stages"]
    assert len(generation) == 1
    assert store.draft(task["draft_id"])["latex_source"] == old_draft["latex_source"]
    assert store.draft(original["draft_id"]) == old_draft
    assert store.pdf(original["resume_id"]) == old_pdf


@pytest.mark.parametrize("change", ["add", "remove", "company", "role_title", "location"])
def test_jd_update_changes_only_affected_tex_and_keeps_manual_wording(update_portal, change):
    server, store, original, generation, model = update_portal
    flow = server.application_flow_service
    manual = save_manual_wording(flow, store, original)
    old = store.draft(manual["draft_id"])
    job = store.applications.get_application(original["application_id"])
    if change in {"add", "remove"}:
        value = (
            job["job_description"] + " Emphasize Python implementation."
            if change == "add"
            else "Build Python services."
        )
        fields = {"job_description": value}
    else:
        fields = {change: "Changed target metadata"}
        model["affected"] = []
    model["active"] = True
    job = store.applications.update_application(job["id"], fields, job["revision"])
    task = refresh_tex(flow, manual, job)
    assert task["status"] == "draft_ready", task["stages"]
    current = store.draft(task["draft_id"])
    assert "Built 6 Python services; analyzed strategy." in current["latex_source"]
    for index, _group in enumerate(current["review_groups"]):
        if index not in model["affected"]:
            identifier = old["review_groups"][index]["id"]
            pattern = (
                rf"(?ms)^% TomorrowStar group {identifier} begin\n"
                rf".*?^% TomorrowStar group {identifier} end\n"
            )
            assert (
                re.search(pattern, current["latex_source"])[0]
                == re.search(pattern, old["latex_source"])[0]
            )
    if model["affected"]:
        assert "Built 1 Python services; analyzed strategy." in current["latex_source"]
    assert store.draft(manual["draft_id"]) == old
    assert len(model["requests"]) == len(generation) == 1
    flow.start(task["id"], task["revision"], "export")
    exported = wait_for(
        flow,
        task["id"],
        lambda row: row["status"] in {"materials_ready", "failed", "needs_recheck"},
    )
    assert exported["status"] == "materials_ready", exported["stages"]


def test_jd_conflict_preserves_manual_history_and_stops_before_export(update_portal):
    server, store, original, _generation, model = update_portal
    flow = server.application_flow_service
    manual = save_manual_wording(flow, store, original)
    old = store.draft(manual["draft_id"])
    job = store.applications.get_application(original["application_id"])
    job = store.applications.update_application(
        job["id"],
        {"job_description": job["job_description"] + " Personal delivery required."},
        job["revision"],
    )
    model.update(active=True, verify=True)
    task = refresh_tex(flow, manual, job)
    assert task["status"] == "draft_ready", task["stages"]
    assert [g["title"] for g in store.draft(task["draft_id"])["verification_queue"]] == [
        "Project 1"
    ]
    compiles = len(store.prism_client.calls)
    with pytest.raises(PortalDataError):
        flow.start(task["id"], task["revision"], "export")
    assert len(store.prism_client.calls) == compiles
    assert store.draft(manual["draft_id"]) == old


@pytest.mark.parametrize("complete_portal", [{"confirmed_email": True}], indirect=True)
def test_contact_correction_preserves_manual_tex_without_rewriting_career_groups(complete_portal):
    from career_evidence_graph.application_full_latex import retained_contact_plan

    server, store, original, generation = complete_portal
    flow = server.application_flow_service
    manual = save_manual_wording(flow, store, original)
    retained = store.draft(manual["draft_id"])
    server.worker_service.store.answers.put_answer(
        {
            "question": "Email",
            "value": "new@example.invalid",
            "state": "confirmed",
            "scope": {"application_id": original["application_id"]},
        }
    )
    requests = []

    def model(config, prompt, **kwargs):
        payload = json.loads(prompt[prompt.index("{") :])
        requests.append(payload)
        output = retained_contact_plan(retained, payload["base"], payload["sources"])
        output["groups"][6]["latex"] = output["groups"][6]["latex"].replace(
            "Built 6 Python services; analyzed strategy.",
            "Analyzed strategy; built 6 Python services.",
        )
        return SimpleNamespace(structured_result=output, model_dump=lambda **_: {"synthetic": True})

    store.model_runner = model
    job = store.applications.get_application(original["application_id"])
    task = refresh_tex(flow, manual, job)
    assert task["status"] == "draft_ready", task["stages"]
    current = store.draft(task["draft_id"])
    assert "new@example.invalid" in current["latex_source"]
    assert "Built 6 Python services; analyzed strategy." in current["latex_source"]
    assert not requests
    assert len(generation) == 1
    assert store.draft(manual["draft_id"]) == retained


def test_manual_edit_after_jd_refresh_keeps_verified_base_and_exports(update_portal):
    server, store, original, _generation, model = update_portal
    flow = server.application_flow_service
    manual = save_manual_wording(flow, store, original)
    job = store.applications.get_application(original["application_id"])
    job = store.applications.update_application(
        job["id"], {"location": "Updated synthetic location"}, job["revision"]
    )
    model.update(active=True, affected=[])
    task = refresh_tex(flow, manual, job)
    assert task["status"] == "draft_ready", task["stages"]
    editable = flow.begin_automatic_edit(task["id"], task["revision"])
    text = store.draft(editable["draft_id"])["latex_source"].replace(
        "Built 6 Python services; analyzed strategy.",
        "Built 6 Python services and analyzed strategy.",
    )
    saved = flow.save_automatic_source(
        editable["id"], editable["revision"], editable["prism"]["source_revision"], text
    )
    flow.start(saved["id"], saved["revision"], "export")
    exported = wait_for(
        flow,
        saved["id"],
        lambda row: row["status"] in {"materials_ready", "failed", "needs_recheck"},
    )
    assert exported["status"] == "materials_ready", exported["stages"]
    assert (
        "Built 6 Python services and analyzed strategy."
        in store.read_export(exported["resume_id"])["latex_source"]
    )


@pytest.mark.parametrize("mode", ["saved", "live", "markers_only"])
def test_unresolved_candidate_never_discards_later_manual_tex(update_portal, mode):
    from pathlib import Path

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
    conflict = refresh_tex(flow, manual, job)
    editable = flow.begin_automatic_edit(conflict["id"], conflict["revision"])
    text = store.draft(editable["draft_id"])["latex_source"].replace(
        "Built 6 Python services; analyzed strategy.",
        "Built 6 Python services and analyzed strategy.",
    )
    changed = editable
    project = Path(editable["prism"]["project_root"]) / "main.tex"
    if mode == "saved":
        changed = flow.save_automatic_source(
            editable["id"], editable["revision"], editable["prism"]["source_revision"], text
        )
        project = Path(changed["prism"]["project_root"]) / "main.tex"
    elif mode == "live":
        project.write_text(text)
    model.update(verify=False)
    job = store.applications.update_application(
        job["id"],
        {"job_description": "Build Python services without the prior requirement."},
        job["revision"],
    )
    task = flow.update_inputs(changed["id"], changed["revision"], job["revision"])
    flow.start(task["id"], task["revision"], "analysis")
    task = wait_for(flow, task["id"], lambda row: row["status"] == "analysis_ready")
    if mode in {"saved", "markers_only"}:
        flow.start(task["id"], task["revision"], "resume")
        task = wait_for(flow, task["id"], lambda row: row["status"] in {"draft_ready", "failed"})
        assert task["status"] == "draft_ready", task["stages"]
        assert not store.draft(task["draft_id"])["verification_queue"]
        expected = (
            "Built 6 Python services and analyzed strategy."
            if mode == "saved"
            else "Built 6 Python services; analyzed strategy."
        )
        assert expected in store.draft(task["draft_id"])["latex_source"]
        return
    before = flow.path.read_bytes()
    requests = len(model["requests"])
    with pytest.raises(PortalDataError) as caught:
        flow.start(task["id"], task["revision"], "resume")
    assert caught.value.code == (
        "resume_group_verification_required" if mode == "saved" else "prism_source_changed"
    )
    assert flow.path.read_bytes() == before
    assert len(model["requests"]) == requests
    assert "Built 6 Python services and analyzed strategy." in project.read_text()


def test_source_and_jd_updates_merge_their_affected_groups_into_latest_tex(update_portal):
    server, store, original, _generation, model = update_portal
    flow = server.application_flow_service
    manual = save_manual_wording(flow, store, original)
    original_runner = store.model_runner

    def model_with_source_correction(config, prompt, **kwargs):
        result = original_runner(config, prompt, **kwargs)
        if model["active"]:
            groups = result.structured_result["groups"]
            groups[1]["latex"] = groups[1]["latex"].replace("Built 1 Python", "Built 11 Python")
            groups[2]["latex"] = groups[2]["latex"].replace(
                "Analyzed strategy; built 2 Python services.",
                "Built 2 Python services; analyzed strategy.",
            )
        return result

    store.model_runner = model_with_source_correction
    document = store.catalog.root / "contributions/project-1.md"
    document.write_text(document.read_text().replace("built 1 Python", "built 11 Python"))
    job = store.applications.get_application(original["application_id"])
    job = store.applications.update_application(
        job["id"],
        {"job_description": job["job_description"] + " Emphasize strategy."},
        job["revision"],
    )
    model.update(active=True, affected=[2])
    task = refresh_tex(flow, manual, job)
    assert task["status"] == "draft_ready", task["stages"]
    source = store.draft(task["draft_id"])["latex_source"]
    assert model["requests"][-1]["update_context"]["source_affected_group_indexes"] == [1]
    assert "Built 11 Python services; analyzed strategy." in source
    assert "Built 2 Python services; analyzed strategy." in source
    assert "Built 6 Python services; analyzed strategy." in source
    # A second metadata change must start from the newly adopted complete TeX.
    job = store.applications.update_application(
        job["id"], {"location": "Another synthetic city"}, job["revision"]
    )
    model["affected"] = []
    task = refresh_tex(flow, task, job)
    assert task["status"] == "draft_ready", task["stages"]
    assert store.draft(task["draft_id"])["latex_source"] == source
