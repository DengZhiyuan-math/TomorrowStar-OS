"""New career context is assessed against retained actual TeX before a local merge."""

import json
from copy import deepcopy
from types import SimpleNamespace

import pytest
from test_application_resume import task_resume as task_resume
from test_full_latex_generation import full_latex as full_latex
from test_full_latex_generation import generate
from test_pending_tex_merge import pending_manual as pending_manual

from career_evidence_graph.application_flow import job_input_revision
from career_evidence_graph.application_resume import career_source_snapshot
from career_evidence_graph.career_portal_data import PortalDataError


@pytest.fixture
def manual_context(full_latex):
    store = full_latex[0]
    draft = generate(full_latex)
    editable = store.prepare_group_review(
        draft["id"], draft["draft_sha256"], task_inputs=full_latex[-1]
    )
    manual = store.save_automatic_source(
        editable["id"],
        editable["draft_sha256"],
        task_inputs=full_latex[-1],
        latex_source=editable["latex_source"].replace(
            "Analyzed strategy; built 6 Python services.",
            "Built 6 Python services; analyzed strategy.",
        ),
    )
    return full_latex, manual


def refresh_context(data, parent, *, modify=None):
    store, job, _, analysis, _, _, _, inputs = data
    job = store.applications.get_application(job["id"])
    snapshot = career_source_snapshot(store.catalog)
    requests = []

    def model(_config, prompt, **_options):
        payload = json.loads(prompt[prompt.index("{") :])
        requests.append(payload)
        result = {
            "groups": deepcopy(payload["update_context"]["retained_groups"]),
            "limitations": [],
            "affected_group_indexes": [],
            "context_impact_reason": "Added context does not change the retained claims.",
        }
        if modify:
            modify(result, payload)
        return SimpleNamespace(
            structured_result=result,
            model_dump=lambda **_: {"synthetic": True, "structured_result": result},
        )

    store.model_runner = model
    result = store.generate_for_task(
        job["id"],
        job["revision"],
        source_snapshot=snapshot,
        analysis=analysis
        | {
            "source_snapshot_revision": snapshot["revision"],
            "jd_revision": job_input_revision(job),
        },
        draft_only=True,
        task_inputs=inputs | {"sources_revision": snapshot["revision"]},
        latex_base=parent["source_checkpoint"],
        retained_draft=parent,
    )
    return result, requests


def test_unrelated_unmapped_context_preserves_actual_manual_tex_and_is_not_reassessed(
    manual_context,
):
    data, manual = manual_context
    path = data[0].catalog.root / "contributions/keyword.md"
    path.write_text(path.read_text() + "\n## Additional context\n\nUnrelated operational notes.\n")
    updated, requests = refresh_context(data, manual)
    assert len(requests) == 1
    assert requests[0]["update_context"]["source_context_changed"] is True
    assert updated["latex_source"] == manual["latex_source"]
    assert not updated["verification_queue"]
    repeated, requests = refresh_context(data, updated)
    assert requests == []
    assert repeated["latex_source"] == manual["latex_source"]
    assert data[0].draft(manual["id"])["latex_source"] == manual["latex_source"]


def add_source(data):
    path = data[0].catalog.root / "contributions/new-operations.md"
    path.write_text(
        "# Additional operations\n\n## Scope\n\nOperated recovery systems.\n\n"
        "## Responsibility attribution\n\n| Area | Attribution |\n| --- | --- |\n"
        "| Operation | User |\n"
    )
    return path


def test_new_eligible_source_merges_only_affected_actual_group_and_becomes_mapped(manual_context):
    data, manual = manual_context
    path = add_source(data)

    def change(result, payload):
        row = result["groups"][1]
        row["latex"] += "Operated recovery systems.\n"
        row["source_ids"] += [
            source["source_id"]
            for source in payload["sources"]
            if source["title"] == "Additional operations"
        ]
        result["groups"][6]["latex"] = "Unwanted replacement\n"
        result["affected_group_indexes"] = [1]
        result["context_impact_reason"] = "New owned operations evidence affects Project 1."

    updated, requests = refresh_context(data, manual, modify=change)
    assert "Operated recovery systems." in updated["latex_source"]
    assert "Built 6 Python services; analyzed strategy." in updated["latex_source"]
    assert "Unwanted replacement" not in updated["latex_source"]
    assert not updated["verification_queue"]
    assert len(updated["review_groups"][1]["sources"]) == 2
    assert (
        requests[0]["update_context"]["source_context_changes"]["documents"][0]["previous"] is None
    )
    path.write_text(path.read_text().replace("Operated recovery", "Maintained recovery"))

    def correct(result, _payload):
        result["groups"][1]["latex"] = result["groups"][1]["latex"].replace(
            "Operated recovery", "Maintained recovery"
        )

    corrected, requests = refresh_context(data, updated, modify=correct)
    assert requests[0]["update_context"]["source_context_changed"] is False
    assert requests[0]["update_context"]["source_affected_group_indexes"] == [1]
    assert "Maintained recovery systems." in corrected["latex_source"]
    assert "Built 6 Python services; analyzed strategy." in corrected["latex_source"]


@pytest.mark.parametrize(
    "damage",
    [
        "missing_indexes",
        "bool_index",
        "duplicate_index",
        "negative_index",
        "large_index",
        "missing_reason",
        "empty_reason",
        "wrong_reason",
        "missing_span",
        "duplicate_span",
        "new_span",
        "bool_span",
        "unknown_source",
        "unchanged_source",
        "duplicate_source",
        "removed_source",
    ],
)
def test_unmapped_context_requires_bounded_complete_impact_result(manual_context, damage):
    data, manual = manual_context
    add_source(data)

    def corrupt(result, payload):
        result["affected_group_indexes"] = [1]
        if damage == "missing_indexes":
            result.pop("affected_group_indexes")
        elif damage in {"bool_index", "duplicate_index", "negative_index", "large_index"}:
            result["affected_group_indexes"] = {
                "bool_index": [True],
                "duplicate_index": [1, 1],
                "negative_index": [-1],
                "large_index": [7],
            }[damage]
        elif damage == "missing_reason":
            result.pop("context_impact_reason")
        elif damage in {"empty_reason", "wrong_reason"}:
            result["context_impact_reason"] = "  " if damage == "empty_reason" else []
        elif damage == "missing_span":
            result["groups"].pop()
        elif damage == "duplicate_span":
            result["groups"][-1] = deepcopy(result["groups"][1])
        elif damage in {"new_span", "bool_span"}:
            result["groups"][1]["start_line"] = 99 if damage == "new_span" else True
        elif damage == "removed_source":
            result["groups"][1]["source_ids"] = []
        else:
            identifiers = result["groups"][1]["source_ids"]
            if damage == "duplicate_source":
                identifiers.append(identifiers[0])
            elif damage == "unknown_source":
                identifiers.append("invented")
            else:
                # A different unchanged, previously unused ID is incomparable
                # with the nonempty set of this round's new IDs.
                identifiers.append(
                    next(
                        source["source_id"]
                        for source in payload["sources"]
                        if source["title"] == "Service operations"
                    )
                )

    with pytest.raises(PortalDataError) as caught:
        refresh_context(data, manual, modify=corrupt)
    assert caught.value.code == "resume_latex_invalid"
    assert data[0].draft(manual["id"])["latex_source"] == manual["latex_source"]


def test_new_context_unions_pending_source_and_jd_impact(pending_manual):
    data, _, manual = pending_manual
    add_source(data)
    path = data[0].catalog.root / "contributions/project-2.md"
    path.write_text(path.read_text().replace("2 Python", "22 Python"))
    job = data[1]
    data[0].applications.update_application(
        job["id"], {"job_description": "Emphasize service recovery and strategy."}, job["revision"]
    )

    def change(result, payload):
        result["affected_group_indexes"] = [3]
        result["groups"][1]["disposition"] = "include"
        result["groups"][1]["reason"] = "Resolved current ownership."
        result["groups"][2]["latex"] = result["groups"][2]["latex"].replace("2 Python", "22 Python")
        result["groups"][3]["latex"] += "Operated recovery systems.\n"
        result["groups"][3]["source_ids"] += [
            source["source_id"]
            for source in payload["sources"]
            if source["title"] == "Additional operations"
        ]
        result["groups"][6]["latex"] = "Ignored unrelated replacement\n"

    updated, requests = refresh_context(data, manual, modify=change)
    update = requests[0]["update_context"]
    assert update["source_context_changed"] is True
    assert update["job_changed"] is True
    assert update["pending_group_indexes"] == [1]
    assert update["source_affected_group_indexes"] == [2]
    assert "Project 1" in updated["latex_source"]
    assert "built 22 Python" in updated["latex_source"]
    assert "Operated recovery systems." in updated["latex_source"]
    assert "Built 6 Python services; analyzed strategy." in updated["latex_source"]
    assert not updated["verification_queue"]


def test_unmapped_responsibility_conflict_stays_verify_and_keeps_other_manual_content(
    manual_context,
):
    data, manual = manual_context
    path = data[0].catalog.root / "contributions/keyword.md"
    path.write_text(
        path.read_text() + "\n## Additional context\n\nProject 2 was delivered by another person.\n"
    )

    def conflict(result, _payload):
        result["affected_group_indexes"] = [2]
        result["groups"][2]["disposition"] = "verify"
        result["groups"][2]["reason"] = "New context conflicts with personal delivery attribution."

    updated, _ = refresh_context(data, manual, modify=conflict)
    assert [group["title"] for group in updated["verification_queue"]] == ["Project 2"]
    assert "Project 2" not in updated["latex_source"]
    assert "Built 6 Python services; analyzed strategy." in updated["latex_source"]


@pytest.mark.parametrize("change", ["add", "change", "delete"])
def test_unmapped_raw_document_context_has_explicit_before_after_without_new_capability_ids(
    manual_context,
    change,
):
    data, manual = manual_context
    path = data[0].catalog.root / "sources/additional-context.md"
    if change != "add":
        path.write_text("# Additional context\n\nOriginal external evidence locator.\n")
        manual, _ = refresh_context(data, manual)
    if change == "delete":
        path.unlink()
    else:
        path.write_text("# Additional context\n\nChanged external evidence locator.\n")
    updated, requests = refresh_context(data, manual)
    update = requests[0]["update_context"]
    assert update["unmapped_current_source_ids"] == []
    assert (
        update["source_context_changes"]["documents"][0]["source_name"]
        == "sources/additional-context.md"
    )
    previous = update["source_context_changes"]["documents"][0]["previous"]
    assert (previous is None) == (change == "add")
    current = [
        doc
        for doc in requests[0]["document_context"]
        if doc["source_name"] == "sources/additional-context.md"
    ]
    assert bool(current) == (change != "delete")
    assert updated["latex_source"] == manual["latex_source"]


@pytest.mark.parametrize("category", ["research", "masterThesis"])
def test_profile_link_context_is_reassessed_without_becoming_capability_evidence(
    manual_context,
    category,
):
    data, manual = manual_context
    path = data[0].catalog.root / "sources/profile.json"
    profile = json.loads(path.read_text())
    profile[category] = [
        {
            "name": "Synthetic research",
            "points": [],
            "links": [{"label": "Evidence", "href": "https://evidence.example.test/user-owned"}],
        }
    ]
    path.write_text(json.dumps(profile))
    first, requests = refresh_context(data, manual)
    update = requests[0]["update_context"]
    assert update["source_context_changes"]["previous_profile_context"] is not None
    assert "profile_context" not in first
    assert first["latex_source"] == manual["latex_source"]
    profile[category][0]["links"][0]["href"] = "https://evidence.example.test/another-person"
    path.write_text(json.dumps(profile))
    second, requests = refresh_context(data, first)
    update = requests[0]["update_context"]
    assert "user-owned" in json.dumps(update["source_context_changes"]["previous_profile_context"])
    assert "another-person" in json.dumps(requests[0]["document_context"])
    assert second["latex_source"] == manual["latex_source"]


def test_profile_document_name_switch_uses_actual_previous_raw_context(manual_context):
    data, manual = manual_context
    path = data[0].catalog.root / "sources/profile.json"
    profile = json.loads(path.read_text())
    profile["research"] = [
        {
            "name": "Synthetic research",
            "points": [],
            "links": [
                {"label": "Original evidence", "href": "https://evidence.example.test/original"}
            ],
        }
    ]
    path.write_text(json.dumps(profile))
    first, _ = refresh_context(data, manual)
    fallback = data[0].catalog.root / "reports/public-site/site-content.json"
    fallback.parent.mkdir(parents=True)
    fallback.write_text(json.dumps({"schema_version": "public-site-source/v1", "profile": profile}))
    path.unlink()
    second, requests = refresh_context(data, first)
    delta = requests[0]["update_context"]["source_context_changes"]
    assert "Original evidence" in json.dumps(delta["previous_profile_context"])
    assert delta["current_profile_source_name"] == "reports/public-site/site-content.json"
    assert second["latex_source"] == manual["latex_source"]


@pytest.mark.parametrize(
    "profile",
    [
        {"name": "Synthetic Person"},
        {
            "name": "Synthetic Person",
            "links": [{"label": "Email", "href": "mailto:new@example.invalid"}],
        },
    ],
)
def test_profile_source_appearance_is_assessed_without_old_profile_document(full_latex, profile):
    data = list(full_latex)
    path = data[0].catalog.root / "sources/profile.json"
    path.unlink()
    snapshot = career_source_snapshot(data[0].catalog)
    data[2] = snapshot
    data[3] = data[3] | {"source_snapshot_revision": snapshot["revision"]}
    data[-1] = data[-1] | {"sources_revision": snapshot["revision"]}
    data[6]["groups"][0]["source_ids"] = []
    data[6]["groups"][0]["disposition"] = "verify"
    original = generate(tuple(data))
    path.write_text(json.dumps(profile))
    updated, requests = refresh_context(data, original)
    delta = requests[0]["update_context"]["source_context_changes"]
    assert delta["previous_profile_context"] is None
    assert delta["current_profile_source_name"] == "sources/profile.json"
    assert "Project 6" in updated["latex_source"]
    assert [group["title"] for group in updated["verification_queue"]] == ["Identity"]
    assert updated["verification_queue"][0]["sources"] == []
    assert "new@example.invalid" not in updated["latex_source"]
    assert data[0].draft(original["id"])["latex_source"] == original["latex_source"]


def test_profile_disappearance_is_assessed_without_parsing_missing_document(manual_context):
    data, manual = manual_context
    (data[0].catalog.root / "sources/profile.json").unlink()
    updated, requests = refresh_context(data, manual)
    delta = requests[0]["update_context"]["source_context_changes"]
    assert delta["previous_profile_context"] is not None
    assert delta["current_profile_source_name"] is None
    assert "Built 6 Python services; analyzed strategy." in updated["latex_source"]
    assert [group["title"] for group in updated["verification_queue"]] == ["Identity"]


def test_unused_source_deletion_is_assessed_without_restoring_or_deleting_manual_groups(
    manual_context,
):
    data, manual = manual_context
    (data[0].catalog.root / "contributions/keyword.md").unlink()
    updated, requests = refresh_context(data, manual)
    update = requests[0]["update_context"]
    assert update["unmapped_current_source_ids"] == []
    assert (
        update["source_context_changes"]["sources"][0]["previous"]["title"] == "Service operations"
    )
    assert updated["latex_source"] == manual["latex_source"]


def test_new_unattributed_source_cannot_be_added_to_retained_group(manual_context):
    data, manual = manual_context
    path = add_source(data)
    path.write_text(
        path.read_text().replace("| Operation | User |", "| Operation | Other person |")
    )

    def cite(result, payload):
        result["affected_group_indexes"] = [1]
        result["groups"][1]["source_ids"].append(
            next(
                source["source_id"]
                for source in payload["sources"]
                if source["title"] == "Additional operations"
            )
        )

    with pytest.raises(PortalDataError) as caught:
        refresh_context(data, manual, modify=cite)
    assert caught.value.code == "resume_latex_invalid"


def test_new_evidence_still_cannot_promote_unsupported_numeric_claim(manual_context):
    data, manual = manual_context
    add_source(data)

    def unsupported(result, payload):
        result["affected_group_indexes"] = [1]
        result["groups"][1]["latex"] += "Operated 999 recovery systems.\n"
        result["groups"][1]["source_ids"].append(
            next(
                source["source_id"]
                for source in payload["sources"]
                if source["title"] == "Additional operations"
            )
        )

    updated, _ = refresh_context(data, manual, modify=unsupported)
    assert [group["title"] for group in updated["verification_queue"]] == ["Project 1"]
    assert updated["verification_queue"][0]["reason"].startswith("unsupported_literal:")
    assert "999" not in updated["latex_source"]
    assert "Built 6 Python services; analyzed strategy." in updated["latex_source"]


def test_new_raw_context_can_map_existing_eligible_evidence_without_changing_its_scope(
    manual_context,
):
    data, manual = manual_context
    path = data[0].catalog.root / "contributions/keyword.md"
    path.write_text(
        path.read_text() + "\n## Additional context\n\nThese operations belong to Project 1.\n"
    )

    def relate(result, payload):
        result["affected_group_indexes"] = [1]
        result["groups"][1]["latex"] += "Built service systems.\n"
        result["groups"][1]["source_ids"].append(
            next(
                source["source_id"]
                for source in payload["sources"]
                if source["title"] == "Service operations"
            )
        )
        result["context_impact_reason"] = (
            "New relation associates existing owned service evidence with Project 1."
        )

    updated, requests = refresh_context(data, manual, modify=relate)
    update = requests[0]["update_context"]
    assert update["source_context_changes"]["sources"] == []
    assert len(update["unmapped_current_source_ids"]) == 1
    assert "Built service systems." in updated["latex_source"]
    assert "Built 6 Python services; analyzed strategy." in updated["latex_source"]
    assert not updated["verification_queue"]
    path.write_text(
        path.read_text().replace("Built service systems.", "Maintained service systems.")
    )

    def correct(result, _payload):
        result["groups"][1]["latex"] = result["groups"][1]["latex"].replace(
            "Built service systems.", "Maintained service systems."
        )

    corrected, requests = refresh_context(data, updated, modify=correct)
    assert requests[0]["update_context"]["source_context_changed"] is False
    assert requests[0]["update_context"]["source_affected_group_indexes"] == [1]
    assert "Maintained service systems." in corrected["latex_source"]


def test_profile_switch_cannot_add_new_identity_source_to_work_group(manual_context):
    data, manual = manual_context
    path = data[0].catalog.root / "sources/profile.json"
    profile = json.loads(path.read_text())
    fallback = data[0].catalog.root / "reports/public-site/site-content.json"
    fallback.parent.mkdir(parents=True)
    fallback.write_text(json.dumps({"schema_version": "public-site-source/v1", "profile": profile}))
    path.unlink()

    def cite_identity(result, payload):
        result["affected_group_indexes"] = [1]
        result["groups"][1]["source_ids"].append(
            next(
                source["source_id"]
                for source in payload["sources"]
                if source.get("source_kind") == "identity"
            )
        )

    with pytest.raises(PortalDataError) as caught:
        refresh_context(data, manual, modify=cite_identity)
    assert caught.value.code == "resume_latex_invalid"
    assert data[0].draft(manual["id"])["latex_source"] == manual["latex_source"]
