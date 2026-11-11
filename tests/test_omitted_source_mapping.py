"""Manual omissions keep source coverage without restoring employer-facing content."""

import json
from copy import deepcopy
from types import SimpleNamespace

import pytest
from test_application_resume import task_resume as task_resume
from test_full_latex_generation import full_latex as full_latex
from test_full_latex_generation import generate

from career_evidence_graph.application_group_review import _marked
from career_evidence_graph.application_resume import career_source_snapshot


@pytest.fixture
def omitted_tex(full_latex):
    store, _, _, _, _, _, _, inputs = full_latex
    original = generate(full_latex)
    editable = store.prepare_group_review(
        original["id"], original["draft_sha256"], task_inputs=inputs
    )
    omitted = next(group for group in editable["review_groups"] if group["title"] == "Project 3")
    text = (
        editable["latex_source"]
        .replace(_marked([omitted]), "")
        .replace(
            "Analyzed strategy; built 6 Python services.",
            "Built 6 Python services; analyzed strategy.",
        )
    )
    manual = store.save_automatic_source(
        editable["id"], editable["draft_sha256"], task_inputs=inputs, latex_source=text
    )
    return full_latex, original, manual, omitted


def refresh(data, parent, *, modify=None):
    store, job, _, analysis, _, _, _, inputs = data
    sources = career_source_snapshot(store.catalog)
    requests = []

    def model(_config, prompt, **_options):
        payload = json.loads(prompt[prompt.index("{") :])
        requests.append(payload)
        groups = deepcopy(payload["update_context"]["retained_groups"])
        output = {"groups": groups, "limitations": []}
        if modify:
            modify(output)
        return SimpleNamespace(structured_result=output, model_dump=lambda **_: {"synthetic": True})

    store.model_runner = model
    result = store.generate_for_task(
        job["id"],
        job["revision"],
        source_snapshot=sources,
        analysis=analysis | {"source_snapshot_revision": sources["revision"]},
        draft_only=True,
        task_inputs=inputs | {"sources_revision": sources["revision"]},
        latex_base=parent["source_checkpoint"],
        retained_draft=parent,
    )
    return result, requests


def test_omitted_source_update_after_a_refresh_keeps_actual_tex_without_model(omitted_tex):
    data, original, manual, omitted = omitted_tex
    first, requests = refresh(data, manual)
    assert requests == []
    assert first["omitted_groups"] == []
    path = data[0].catalog.root / "contributions/project-3.md"
    path.write_text(path.read_text().replace("3 Python services", "33 Python services"))
    second, requests = refresh(data, first)
    assert requests == []
    assert second["latex_source"] == manual["latex_source"]
    assert "Project 3" not in second["latex_source"]
    assert "Built 6 Python services; analyzed strategy." in second["latex_source"]
    assert data[0].draft(original["id"])["latex_source"] == original["latex_source"]
    assert data[0].draft(manual["id"])["omitted_groups"][0]["id"] == omitted["id"]


def change_source(data, number, *, delete=False, context=False):
    path = data[0].catalog.root / f"contributions/project-{number}.md"
    if delete:
        path.unlink()
    elif context:
        path.write_text(
            path.read_text() + "\n## Additional context\n\nDelivery by another person.\n"
        )
    else:
        path.write_text(path.read_text().replace(f"{number} Python", f"{number}{number} Python"))


def test_repeated_omitted_updates_preserve_minimal_private_mapping(omitted_tex):
    data, _, manual, omitted = omitted_tex
    first, _ = refresh(data, manual)
    change_source(data, 3)
    second, _ = refresh(data, first)
    change_source(data, 3, context=True)
    third, requests = refresh(data, second)
    assert requests == []
    assert third["latex_source"] == manual["latex_source"]
    saved = json.loads((data[0].root / third["id"] / "draft.json").read_text())
    assert saved["omitted_source_mapping"] == {
        omitted["id"]: [
            {key: source[key] for key in ("source_id", "source_name")}
            for source in omitted["sources"]
        ]
    }
    assert "omitted_source_mapping" not in third
    assert saved["omitted_groups"] == []
    assert saved["pending_merge"]["draft_id"] == second["id"]


@pytest.mark.parametrize("delete", [False, True])
def test_omitted_document_context_and_deletion_do_not_restore_text(omitted_tex, delete):
    data, _, manual, _ = omitted_tex
    first, _ = refresh(data, manual)
    change_source(data, 3, delete=delete, context=not delete)
    second, requests = refresh(data, first)
    assert requests == []
    assert second["latex_source"] == manual["latex_source"]


def test_missing_active_source_still_stops_even_with_omission_mapping(omitted_tex):
    from career_evidence_graph.career_portal_data import PortalDataError

    data, _, manual, _ = omitted_tex
    first, _ = refresh(data, manual)
    change_source(data, 6, delete=True)
    with pytest.raises(PortalDataError) as caught:
        refresh(data, first)
    assert caught.value.code == "resume_latex_invalid"
    assert data[0].draft(first["id"])["latex_source"] == manual["latex_source"]


def rebind_omitted(data, parent, omitted, *, disposition="omit"):
    source = next(group for group in parent["review_groups"] if group["title"] == "Project 6")
    return data[0].edit_group_review(
        parent["id"],
        parent["draft_sha256"],
        task_inputs=data[-1],
        payload={
            "group_id": omitted["id"],
            "title": "Shared service context",
            "latex": "Analyzed strategy; built 6 Python services.\n",
            "source_ids": [ref["source_id"] for ref in source["sources"]],
            "disposition": disposition,
        },
    )


def test_shared_source_updates_active_group_despite_omitted_coverage(omitted_tex):
    data, _, manual, omitted = omitted_tex
    edited = rebind_omitted(data, manual, omitted)
    first, _ = refresh(data, edited)
    change_source(data, 6)

    def update(output):
        for row in output["groups"]:
            if row["title"] == "Project 6":
                row["latex"] = row["latex"].replace("6 Python", "66 Python")
            if row["title"] == "Project 5":
                row["latex"] = row["latex"].replace("built 5", "built 55")

    second, requests = refresh(data, first, modify=update)
    assert len(requests) == 1
    assert requests[0]["update_context"]["source_affected_group_indexes"] == [5]
    assert all(
        row["title"] != "Shared service context"
        for row in requests[0]["update_context"]["retained_groups"]
    )
    assert "Built 66 Python services; analyzed strategy." in second["latex_source"]
    assert "built 5 Python" in second["latex_source"]
    assert "built 55 Python" not in second["latex_source"]
    assert "Shared service context" not in second["latex_source"]


def test_current_omitted_source_edit_does_not_recover_old_root_references(omitted_tex):
    data, _, manual, omitted = omitted_tex
    edited = rebind_omitted(data, manual, omitted)
    first, _ = refresh(data, edited)
    change_source(data, 3)

    def no_impact(output):
        output["affected_group_indexes"] = []
        output["context_impact_reason"] = "Old omitted source is unrelated to actual retained TeX."

    second, requests = refresh(data, first, modify=no_impact)
    assert len(requests) == 1
    assert requests[0]["update_context"]["source_context_changed"] is True
    assert second["latex_source"] == first["latex_source"]
    saved = json.loads((data[0].root / first["id"] / "draft.json").read_text())
    current_ids = {source["source_id"] for source in edited["omitted_groups"][0]["sources"]}
    assert {
        source["source_id"] for source in saved["omitted_source_mapping"][omitted["id"]]
    } == current_ids


def test_reintroduced_group_updates_as_active_and_retains_other_manual_wording(omitted_tex):
    data, _, manual, omitted = omitted_tex
    store = data[0]
    restored = store.edit_group_review(
        manual["id"],
        manual["draft_sha256"],
        task_inputs=data[-1],
        payload={
            "group_id": omitted["id"],
            "title": omitted["title"],
            "latex": omitted["rewritten"],
            "source_ids": [source["source_id"] for source in omitted["sources"]],
            "disposition": "include",
        },
    )
    first, _ = refresh(data, restored)
    change_source(data, 3)

    def update(output):
        for row in output["groups"]:
            if row["title"] == "Project 3":
                row["latex"] = row["latex"].replace("3 Python", "33 Python")

    second, requests = refresh(data, first, modify=update)
    assert len(requests) == 1
    assert "built 33 Python" in second["latex_source"]
    assert "Built 6 Python services; analyzed strategy." in second["latex_source"]


@pytest.mark.parametrize("change", ["new_document", "profile_context"])
def test_unmapped_context_without_impact_judgment_still_stops_with_omitted_coverage(
    omitted_tex, change
):
    from career_evidence_graph.career_portal_data import PortalDataError

    data, _, manual, _ = omitted_tex
    first, _ = refresh(data, manual)
    if change == "new_document":
        path = data[0].catalog.root / "contributions/keyword.md"
        path.write_text(path.read_text() + "\n## Added context\n\nOther-person delivery.\n")
    else:
        path = data[0].catalog.root / "sources/profile.json"
        profile = json.loads(path.read_text())
        profile["research"] = [
            {
                "name": "Synthetic context",
                "points": [],
                "links": [
                    {"label": "Evidence", "href": "https://evidence.example.test/other-person"}
                ],
            }
        ]
        path.write_text(json.dumps(profile))
    with pytest.raises(PortalDataError) as caught:
        refresh(data, first)
    assert caught.value.code == "resume_latex_invalid"


def rewrite_draft(store, draft, modify):
    import hashlib

    path = store.root / draft["id"] / "draft.json"
    saved = json.loads(path.read_text())
    modify(saved)
    path.write_text(json.dumps(saved))
    (path.parent / "draft-integrity.json").write_text(
        json.dumps(
            {
                "schemaVersion": 1,
                "id": draft["id"],
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            }
        )
    )


@pytest.mark.parametrize("damage", ["coverage", "remove", "parent", "parent_sha"])
def test_rehashed_omission_metadata_and_parent_tampering_are_rejected(omitted_tex, damage):
    from career_evidence_graph.career_portal_data import PortalDataError

    data, _, manual, omitted = omitted_tex
    store = data[0]
    first, _ = refresh(data, manual)

    def modify(saved):
        if damage == "coverage":
            saved["omitted_source_mapping"][omitted["id"]][0]["source_id"] = "invented"
        elif damage == "remove":
            saved.pop("omitted_source_mapping")
        elif damage == "parent":
            saved["pending_merge"]["draft_id"] = first["id"]
        else:
            saved["pending_merge"]["draft_sha256"] = "0" * 64

    rewrite_draft(store, first, modify)
    with pytest.raises(PortalDataError) as caught:
        store.draft(first["id"])
    assert caught.value.code == "resume_draft_invalid"


def test_legacy_pending_merge_recovers_omission_mapping_from_actual_parent(omitted_tex):
    data, _, manual, _ = omitted_tex
    store = data[0]
    first, _ = refresh(data, manual)

    def legacy(saved):
        saved["pending_merge"]["policy"] = "pending-tex-merge/v1"
        saved.pop("omitted_source_mapping")

    rewrite_draft(store, first, legacy)
    first = store.draft(first["id"])
    # A second historical merge may already have lost omitted_groups too.
    second, _ = refresh(data, first)
    rewrite_draft(store, second, legacy)
    second = store.draft(second["id"])
    change_source(data, 3)
    third, requests = refresh(data, second)
    assert requests == []
    assert third["latex_source"] == manual["latex_source"]
    saved = json.loads((store.root / third["id"] / "draft.json").read_text())
    assert saved["pending_merge"]["policy"] == "pending-tex-merge/v2"
    assert saved["omitted_source_mapping"]


def test_initial_model_omission_also_keeps_coverage_across_updates(full_latex):
    store, _, _, _, calls, _, output, _ = full_latex
    output["groups"][3]["disposition"] = "omit"
    output["groups"][3]["reason"] = "Irrelevant for the current application"
    original = generate(full_latex)
    first, _ = refresh(full_latex, original)
    change_source(full_latex, 3)
    second, requests = refresh(full_latex, first)
    assert requests == []
    assert len(calls) == 1
    assert second["latex_source"] == original["latex_source"]
    assert "Project 3" not in second["latex_source"]
    assert store.draft(original["id"])["omitted_groups"][0]["title"] == "Project 3"
