"""Pending groups merge into the latest actual TeX without undoing manual edits."""

import hashlib
import json
from copy import deepcopy
from types import SimpleNamespace

import pytest
from test_application_resume import task_resume as task_resume
from test_application_source_reuse import retained_capture as retained_capture
from test_full_latex_generation import full_latex as full_latex
from test_full_latex_generation import generate

from career_evidence_graph.application_flow import job_input_revision
from career_evidence_graph.application_prism import source_snapshot
from career_evidence_graph.application_resume import career_source_snapshot
from career_evidence_graph.career_portal_data import PortalDataError


def test_pending_candidate_is_rechecked_without_losing_later_manual_wording(full_latex):
    store, job, sources, analysis, _, _, output, inputs = full_latex
    output["groups"][1]["disposition"] = "verify"
    output["groups"][1]["reason"] = "Important responsibility conflict"
    pending = generate(full_latex)
    editable = store.prepare_group_review(
        pending["id"], pending["draft_sha256"], task_inputs=inputs
    )
    manual = store.save_automatic_source(
        editable["id"],
        editable["draft_sha256"],
        task_inputs=inputs,
        latex_source=editable["latex_source"].replace(
            "Analyzed strategy; built 6 Python services.",
            "Built 6 Python services; analyzed strategy.",
        ),
    )
    requests = []

    def model(config, prompt, **_options):
        payload = json.loads(prompt[prompt.index("{") :])
        requests.append(payload)
        groups = deepcopy(payload["update_context"]["retained_groups"])
        for group in groups:
            group["disposition"] = "include"
            group["reason"] = "Resolved responsibility using existing source"
            if group["title"] == "Project 6":
                group["latex"] = group["latex"].replace(
                    "Built 6 Python services; analyzed strategy.",
                    "Analyzed strategy; built 6 Python services.",
                )
        return SimpleNamespace(
            structured_result={"groups": groups, "limitations": []},
            model_dump=lambda **_: {"synthetic": True},
        )

    store.model_runner = model
    result = store.generate_for_task(
        job["id"],
        job["revision"],
        source_snapshot=sources,
        analysis=analysis,
        draft_only=True,
        task_inputs=inputs,
        latex_base=source_snapshot(
            store.root / manual["id"] / "project",
            "main.tex",
            source_policy="generated-latex-project/v1",
        ),
        retained_draft=manual,
    )
    assert requests[0]["update_context"]["pending_group_indexes"] == [1]
    assert "Project 1" in result["latex_source"]
    assert "Built 6 Python services; analyzed strategy." in result["latex_source"]
    assert result["verification_queue"] == []
    assert store.draft(manual["id"])["latex_source"] == manual["latex_source"]
    assert (
        result["base_checkpoint"]["source_revision"]
        == manual["source_checkpoint"]["source_revision"]
    )
    assert store.draft(result["id"])["latex_source"] == result["latex_source"]


@pytest.fixture
def pending_manual(full_latex):
    store, _, _, _, _, _, output, inputs = full_latex
    output["groups"][1]["disposition"] = "verify"
    output["groups"][1]["reason"] = "Important responsibility conflict"
    pending = generate(full_latex)
    editable = store.prepare_group_review(
        pending["id"], pending["draft_sha256"], task_inputs=inputs
    )
    manual = store.save_automatic_source(
        editable["id"],
        editable["draft_sha256"],
        task_inputs=inputs,
        latex_source=editable["latex_source"].replace(
            "Analyzed strategy; built 6 Python services.",
            "Built 6 Python services; analyzed strategy.",
        ),
    )
    return full_latex, pending, manual


def regenerate(
    data, manual, *, disposition="include", source_change=False, job_change=False, modify=None
):
    store, job, sources, analysis, _, _, _, inputs = data
    if source_change:
        path = store.catalog.root / "contributions/project-1.md"
        path.write_text(path.read_text().replace("1 Python services", "11 Python services"))
        sources = career_source_snapshot(store.catalog)
        analysis = analysis | {"source_snapshot_revision": sources["revision"]}
        inputs = inputs | {"sources_revision": sources["revision"]}
    if job_change:
        job = store.applications.update_application(
            job["id"], {"job_description": "Emphasize Python strategy."}, job["revision"]
        )
        analysis = analysis | {"jd_revision": job_input_revision(job)}
    requests = []

    def model(config, prompt, **_options):
        payload = json.loads(prompt[prompt.index("{") :])
        requests.append(payload)
        groups = deepcopy(payload["update_context"]["retained_groups"])
        for index, group in enumerate(groups):
            group["reason"] = (
                "Resolved existing responsibility"
                if disposition == "include"
                else "Important conflict remains"
            )
            group["disposition"] = (
                disposition
                if index in payload["update_context"]["pending_group_indexes"]
                else "include"
            )
            if source_change and group["title"] == "Project 1":
                group["latex"] = group["latex"].replace("1 Python services", "11 Python services")
            if group["title"] == "Project 6":
                group["latex"] = group["latex"].replace(
                    "Built 6 Python services; analyzed strategy.",
                    "Analyzed strategy; built 6 Python services.",
                )
        output = {"groups": groups, "limitations": []}
        if modify:
            modify(output)
        if job_change:
            output["affected_group_indexes"] = []
        return SimpleNamespace(structured_result=output, model_dump=lambda **_: {"synthetic": True})

    store.model_runner = model
    result = store.generate_for_task(
        job["id"],
        job["revision"],
        source_snapshot=sources,
        analysis=analysis,
        draft_only=True,
        task_inputs=inputs,
        latex_base=deepcopy(manual["source_checkpoint"]),
        retained_draft=manual,
    )
    return result, requests


@pytest.mark.parametrize(
    "source_change,job_change", [(False, False), (True, False), (False, True), (True, True)]
)
def test_pending_merge_unions_fact_and_job_changes(pending_manual, source_change, job_change):
    data, pending, manual = pending_manual
    result, requests = regenerate(data, manual, source_change=source_change, job_change=job_change)
    assert result["verification_queue"] == []
    assert "Built 6 Python services; analyzed strategy." in result["latex_source"]
    assert ("built 11 Python services." if source_change else "built 1 Python services.") in result[
        "latex_source"
    ]
    assert len(requests) == 1
    assert requests[0]["update_context"]["pending_group_indexes"] == [1]
    store = data[0]
    assert store.draft(pending["id"])["latex_source"] == pending["latex_source"]
    assert store.draft(manual["id"])["latex_source"] == manual["latex_source"]
    saved = json.loads((store.root / result["id"] / "draft.json").read_text())
    assert saved["pending_merge"] == {
        "policy": "pending-tex-merge/v1",
        "draft_id": manual["id"],
        "draft_sha256": manual["draft_sha256"],
    }
    assert (store.root / result["id"] / "base-sources.json").read_bytes() == (
        store.root / manual["id"] / "latex-sources.json"
    ).read_bytes()


def test_remaining_pending_conflict_survives_repeated_merges(pending_manual):
    data, _, manual = pending_manual
    first, requests = regenerate(data, manual, disposition="verify")
    assert [group["title"] for group in first["verification_queue"]] == ["Project 1"]
    assert "Project 1" not in first["latex_source"]
    second, requests = regenerate(data, first, disposition="verify")
    assert [group["title"] for group in second["verification_queue"]] == ["Project 1"]
    assert "Built 6 Python services; analyzed strategy." in second["latex_source"]
    assert requests[0]["update_context"]["pending_group_indexes"] == [1]
    assert data[0].draft(second["id"])["latex_source"] == second["latex_source"]


def test_pending_merge_keeps_manual_deletion_and_reordering(pending_manual):
    data, _, manual = pending_manual
    store, *_ = data
    groups = manual["review_groups"]
    # Reorder two present projects and explicitly remove another while pending remains absent.
    text = manual["latex_source"]
    from career_evidence_graph.application_group_review import _marked

    text = text.replace(_marked([groups[2]]), "")
    left, right = _marked([groups[3]]), _marked([groups[4]])
    text = (
        text.replace(left, "TEMPORARY_GROUP").replace(right, left).replace("TEMPORARY_GROUP", right)
    )
    edited = store.save_automatic_source(
        manual["id"], manual["draft_sha256"], task_inputs=data[-1], latex_source=text
    )
    result, _ = regenerate(data, edited)
    assert "Project 3" not in result["latex_source"]
    assert result["latex_source"].index("Project 5") < result["latex_source"].index("Project 4")
    assert "Project 1" in result["latex_source"]
    assert "Built 6 Python services; analyzed strategy." in result["latex_source"]


@pytest.mark.parametrize("damage", ["sha", "parent", "archive"])
def test_pending_merge_validates_immutable_parent_lineage(pending_manual, damage):
    data, _, manual = pending_manual
    store = data[0]
    result, _ = regenerate(data, manual)
    path = store.root / result["id"] / "draft.json"
    raw = json.loads(path.read_text())
    if damage == "sha":
        raw["pending_merge"]["draft_sha256"] = "0" * 64
    elif damage == "parent":
        raw["pending_merge"]["draft_id"] = result["id"]
    else:
        raw["base_checkpoint"]["archive_sha256"] = "0" * 64
    path.write_text(json.dumps(raw))
    (path.parent / "draft-integrity.json").write_text(
        json.dumps(
            {
                "schemaVersion": 1,
                "id": result["id"],
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            }
        )
    )
    with pytest.raises(PortalDataError) as caught:
        store.draft(result["id"])
    assert caught.value.code == "resume_draft_invalid"


@pytest.mark.parametrize("method", ["group_edit", "capture"])
def test_pending_merge_uses_latest_public_editor_version(pending_manual, method):
    from pathlib import Path

    from test_standalone_prism_review import FakePrism

    data, _, manual = pending_manual
    store = data[0]
    group = next(group for group in manual["review_groups"] if group["title"] == "Project 5")
    text = group["rewritten"].replace(
        "Analyzed strategy; built 5 Python services.", "Built 5 Python services; analyzed strategy."
    )
    if method == "group_edit":
        edited = store.edit_group_review(
            manual["id"],
            manual["draft_sha256"],
            task_inputs=data[-1],
            payload={
                "group_id": group["id"],
                "title": group["title"],
                "latex": text,
                "source_ids": [source["source_id"] for source in group["sources"]],
            },
        )
    else:
        path = Path(manual["source_checkpoint"]["project_root"]) / "main.tex"
        path.write_text(manual["latex_source"].replace(group["rewritten"], text))
        store.group_prism_client = FakePrism()
        state = store.group_review_state(manual["id"])
        captured = store.capture_group_review(
            manual["id"],
            manual["draft_sha256"],
            task_inputs=data[-1],
            expected_source_revision=state["live_source_revision"],
        )
        assert captured["status"] == "ready"
        edited = captured["draft"]
    result, _ = regenerate(data, edited)
    assert "Built 5 Python services; analyzed strategy." in result["latex_source"]
    assert "Built 6 Python services; analyzed strategy." in result["latex_source"]
    assert "Project 1" in result["latex_source"]


def test_new_unresolved_group_without_sources_stays_pending(pending_manual):
    data, _, manual = pending_manual
    store = data[0]
    edited = store.edit_group_review(
        manual["id"],
        manual["draft_sha256"],
        task_inputs=data[-1],
        payload={
            "title": "New unresolved statement",
            "latex": "Analyzed service strategy.\n",
            "source_ids": [],
        },
    )
    result, requests = regenerate(data, edited)
    assert [group["title"] for group in result["verification_queue"]] == [
        "New unresolved statement"
    ]
    assert result["verification_queue"][0]["sources"] == []
    assert requests[0]["update_context"]["pending_group_indexes"] == [1, 7]
    assert "Analyzed service strategy." not in result["latex_source"]


def test_pending_merge_preserves_added_supported_group(pending_manual):
    data, _, manual = pending_manual
    store = data[0]
    group = manual["review_groups"][-1]
    edited = store.edit_group_review(
        manual["id"],
        manual["draft_sha256"],
        task_inputs=data[-1],
        payload={
            "title": "Additional service context",
            "latex": "Analyzed strategy and built Python services.\n",
            "source_ids": [source["source_id"] for source in group["sources"]],
        },
    )
    result, _ = regenerate(data, edited)
    assert result["latex_source"].endswith(
        "Analyzed strategy and built Python services.\n\n% TomorrowStar group "
        + edited["review_groups"][-1]["id"]
        + " end\n\\end{document}\n"
    )
    assert "Built 6 Python services; analyzed strategy." in result["latex_source"]


def test_pending_merge_preserves_retained_documentary_education(full_latex, retained_capture):
    import shutil

    store, _, _, analysis, _, project, output, inputs = full_latex
    case = retained_capture
    if case["catalog"].root != store.catalog.root:
        shutil.copytree(case["catalog"].root / ".retained", store.catalog.root / ".retained")
    (store.catalog.root / "sources/profile.json").write_text(
        json.dumps({"name": "Synthetic Person", **case["profile"]})
    )
    manifest = deepcopy(case["manifest"])
    manifest["groups"][1]["context_source_ids"] = [output["groups"][1]["source_ids"][0]]
    (store.catalog.root / "sources/retained-resume-sources.json").write_text(json.dumps(manifest))
    sources = career_source_snapshot(store.catalog)
    retained = sources["retained_materials"]
    (project / "main.tex").write_text(case["source"])
    output["groups"] = [
        {
            "title": "Education",
            "start_line": 1,
            "end_line": 2,
            "source_ids": [retained[0]["source_id"]],
            "latex": "PhD awarded.\n",
            "disposition": "omit",
            "reason": "Model must preserve fixed education",
        },
        {
            "title": "Service",
            "start_line": 3,
            "end_line": 4,
            "source_ids": [retained[1]["source_id"]],
            "latex": retained[1]["text"],
            "disposition": "verify",
            "reason": "Important work wording conflict",
        },
    ]
    data = list(full_latex)
    data[2] = sources
    analysis["source_snapshot_revision"] = inputs["sources_revision"] = sources["revision"]
    generated = generate(data)
    prepared = store.prepare_group_review(
        generated["id"], generated["draft_sha256"], task_inputs=inputs
    )
    result, requests = regenerate(data, prepared)
    assert result["verification_queue"] == []
    assert "PhD in progress" in result["latex_source"]
    assert "Expected July 2028" in result["latex_source"]
    assert "awarded" not in result["latex_source"]
    assert result["review_groups"][0]["content_policy"] == "fixed_education"
    before = json.loads((store.root / generated["id"] / "draft.json").read_text())[
        "generation_sources"
    ]
    after = json.loads((store.root / result["id"] / "draft.json").read_text())["generation_sources"]
    assert [source for source in before if source.get("retained_receipt_revision")] == [
        source for source in after if source.get("retained_receipt_revision")
    ]
    assert len(requests) == 1
    assert store.draft(result["id"])["latex_source"] == result["latex_source"]
    followup = store.prepare_group_review(result["id"], result["draft_sha256"], task_inputs=inputs)
    assert store.draft(followup["id"])["latex_source"] == followup["latex_source"]
    continued, _ = regenerate(data, followup, job_change=True)
    assert continued["verification_queue"] == []
    assert "PhD in progress" in continued["latex_source"]
    assert "Expected July 2028" in continued["latex_source"]
    assert store.draft(continued["id"])["latex_source"] == continued["latex_source"]


def test_latest_pending_group_edit_uses_its_current_wording_and_references(pending_manual):
    data, _, manual = pending_manual
    store = data[0]
    pending = manual["verification_queue"][0]
    other = manual["review_groups"][-1]
    edited = store.edit_group_review(
        manual["id"],
        manual["draft_sha256"],
        task_inputs=data[-1],
        payload={
            "group_id": pending["id"],
            "title": "Latest pending wording",
            "latex": "Analyzed strategy; built 99 Python services.\n",
            "source_ids": [source["source_id"] for source in other["sources"]],
        },
    )
    assert (
        edited["verification_queue"][0]["rewritten"]
        == "Analyzed strategy; built 99 Python services.\n"
    )

    def resolve(output):
        row = next(row for row in output["groups"] if row["title"] == "Latest pending wording")
        row["latex"] = row["latex"].replace("99 Python services", "6 Python services")

    result, requests = regenerate(data, edited, modify=resolve)
    rows = requests[0]["update_context"]["retained_groups"]
    latest = next(row for row in rows if row["title"] == "Latest pending wording")
    assert "99 Python services" in latest["latex"]
    assert latest["source_ids"] == [source["source_id"] for source in other["sources"]]
    assert result["verification_queue"] == []
    assert "99 Python services" not in result["latex_source"]
    assert "Built 6 Python services; analyzed strategy." in result["latex_source"]


def test_pending_generated_draft_without_editor_session_is_restored(full_latex):
    store, _, _, _, _, _, output, _ = full_latex
    output["groups"][1]["disposition"] = "verify"
    pending = generate(full_latex)
    result, requests = regenerate(full_latex, pending)
    assert requests[0]["update_context"]["pending_group_indexes"] == [1]
    assert result["verification_queue"] == []
    assert "Project 1" in result["latex_source"]
    assert store.draft(result["id"])["latex_source"] == result["latex_source"]
