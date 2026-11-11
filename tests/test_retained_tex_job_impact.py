"""JD changes update only affected groups in the adopted complete TeX source."""

import json
from types import SimpleNamespace

import pytest
from test_application_resume import task_resume as task_resume
from test_full_latex_generation import full_latex as full_latex
from test_full_latex_generation import generate

from career_evidence_graph.application_flow import job_input_revision
from career_evidence_graph.application_prism import source_snapshot


@pytest.fixture
def retained_tex(full_latex):
    store, job, sources, analysis, calls, _, _, inputs = full_latex
    original = generate(full_latex)
    editable = store.prepare_group_review(
        original["id"], original["draft_sha256"], task_inputs=inputs
    )
    manual_text = editable["latex_source"].replace(
        "Analyzed strategy; built 6 Python services.", "Built 6 Python services; analyzed strategy."
    )
    manual = store.save_automatic_source(
        editable["id"], editable["draft_sha256"], task_inputs=inputs, latex_source=manual_text
    )
    return store, job, sources, analysis, calls, inputs, original, manual


def refresh(data, *, job_change, affected, modify=None):
    store, job, sources, analysis, calls, inputs, _, manual = data
    job = store.applications.update_application(job["id"], job_change, job["revision"])
    requests = []

    def model(config, prompt, **_options):
        payload = json.loads(prompt[prompt.index("{") :])
        requests.append(payload)
        groups = []
        for group in manual["review_groups"]:
            begin = next(
                row["line_number"]
                for row in payload["body_lines"]
                if row["text"] == f"% TomorrowStar group {group['id']} begin\n"
            )
            end = next(
                row["line_number"]
                for row in payload["body_lines"]
                if row["text"] == f"% TomorrowStar group {group['id']} end\n"
            )
            groups.append(
                {
                    "title": group["title"],
                    "start_line": begin,
                    "end_line": end,
                    "source_ids": [source["source_id"] for source in group["sources"]],
                    "latex": group["rewritten"],
                    "disposition": "include",
                    "reason": "Changed JD emphasis only",
                }
            )
        result = {"groups": groups, "limitations": [], "affected_group_indexes": affected}
        if modify:
            modify(result)
        requests[-1]["test_schema"] = json.loads(config.output_schema.read_text())
        return SimpleNamespace(structured_result=result, model_dump=lambda **_: {"synthetic": True})

    store.model_runner = model
    result = store.generate_for_task(
        job["id"],
        job["revision"],
        source_snapshot=sources,
        analysis=analysis | {"jd_revision": job_input_revision(job)},
        draft_only=True,
        task_inputs=inputs,
        latex_base=source_snapshot(store.root / manual["id"] / "project", "main.tex"),
        retained_draft=manual,
    )
    return result, requests


def test_new_jd_requirement_updates_one_group_and_preserves_manual_others(retained_tex):
    def modify(result):
        result["groups"][1]["latex"] = result["groups"][1]["latex"].replace(
            "Analyzed strategy; built 1 Python services.",
            "Built 1 Python services; analyzed strategy.",
        )
        result["groups"][6]["latex"] = result["groups"][6]["latex"].replace(
            "Built 6 Python services; analyzed strategy.",
            "Analyzed strategy; built 6 Python services.",
        )

    result, requests = refresh(
        retained_tex,
        job_change={"job_description": "Operate service systems. Emphasize Python."},
        affected=[1],
        modify=modify,
    )
    assert "Built 1 Python services; analyzed strategy." in result["latex_source"]
    assert "Built 6 Python services; analyzed strategy." in result["latex_source"]
    assert len(requests) == 1
    context = requests[0]["update_context"]
    assert context["previous_job"]["job_description"] == "Operate service systems."
    assert context["current_job"]["job_description"].endswith("Emphasize Python.")
    assert context["source_affected_group_indexes"] == []
    store, _, _, _, calls, _, original, manual = retained_tex
    assert len(calls) == 1
    assert store.draft(original["id"])["latex_source"] == original["latex_source"]
    assert store.draft(manual["id"])["latex_source"] == manual["latex_source"]
    for index, group in enumerate(manual["review_groups"]):
        if index != 1:
            assert group["rewritten"] in result["latex_source"]


def test_jd_refresh_rejects_regrouping_even_outside_selected_changes(retained_tex):
    from career_evidence_graph.career_portal_data import PortalDataError

    def regroup(result):
        result["groups"][6]["end_line"] -= 1

    with pytest.raises(PortalDataError) as caught:
        refresh(
            retained_tex,
            job_change={"job_description": "Emphasize strategy."},
            affected=[1],
            modify=regroup,
        )
    assert caught.value.code == "resume_latex_invalid"
    store, _, _, _, _, _, _, manual = retained_tex
    assert store.draft(manual["id"])["latex_source"] == manual["latex_source"]


@pytest.mark.parametrize("affected", [[-1], [7], [1, 1], [True], "1", None])
def test_jd_refresh_rejects_invalid_or_duplicate_affected_indexes(retained_tex, affected):
    from career_evidence_graph.career_portal_data import PortalDataError

    with pytest.raises(PortalDataError) as caught:
        refresh(
            retained_tex, job_change={"job_description": "Prioritize strategy."}, affected=affected
        )
    assert caught.value.code == "resume_latex_invalid"


def test_unrelated_job_metadata_preserves_all_actual_manual_tex(retained_tex):
    result, requests = refresh(retained_tex, job_change={"location": "Synthetic City"}, affected=[])
    assert result["latex_source"] == retained_tex[-1]["latex_source"]
    assert len(requests) == 1


def test_removed_requirement_changes_only_the_relevant_group(retained_tex):
    def modify(result):
        result["groups"][1]["latex"] = result["groups"][1]["latex"].replace(
            "Analyzed strategy; built 1 Python services.", "Built 1 Python services."
        )

    result, _ = refresh(
        retained_tex,
        job_change={"job_description": "Build Python services."},
        affected=[1],
        modify=modify,
    )
    assert "Built 1 Python services." in result["latex_source"]
    assert "Built 6 Python services; analyzed strategy." in result["latex_source"]


def test_important_jd_conflict_is_queued_for_verification(retained_tex):
    def conflict(result):
        result["groups"][1]["disposition"] = "verify"
        result["groups"][1]["reason"] = (
            "The JD requests personal delivery; retained facts need resolution"
        )

    result, _ = refresh(
        retained_tex,
        job_change={"job_description": "Require verified personal Python delivery."},
        affected=[1],
        modify=conflict,
    )
    assert [group["title"] for group in result["verification_queue"]] == ["Project 1"]
    assert "Built 6 Python services; analyzed strategy." in result["latex_source"]


def test_malformed_model_span_stops_with_a_recoverable_error(retained_tex):
    from career_evidence_graph.career_portal_data import PortalDataError

    def damage(result):
        result["groups"][6]["start_line"] = []

    with pytest.raises(PortalDataError) as caught:
        refresh(
            retained_tex,
            job_change={"job_description": "Prioritize strategy."},
            affected=[1],
            modify=damage,
        )
    assert caught.value.code == "resume_latex_invalid"


def rewrite_checkpoint(store, draft, *, job_context):
    import hashlib

    path = store.root / draft["id"] / "draft.json"
    saved = json.loads(path.read_text())
    if job_context is None:
        saved.pop("job_context", None)
    else:
        saved["job_context"] = job_context
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
    return store.draft(draft["id"])


def test_legacy_source_without_old_job_context_is_kept_for_the_same_jd(retained_tex):
    data = list(retained_tex)
    data[-1] = rewrite_checkpoint(data[0], data[-1], job_context=None)
    result, requests = refresh(data, job_change={"notes": "Unrelated note"}, affected=[])
    assert result["latex_source"] == data[-1]["latex_source"]
    assert requests == []


def test_legacy_source_without_old_job_context_stops_a_changed_jd(retained_tex):
    from career_evidence_graph.career_portal_data import PortalDataError

    data = list(retained_tex)
    data[-1] = rewrite_checkpoint(data[0], data[-1], job_context=None)
    with pytest.raises(PortalDataError) as caught:
        refresh(data, job_change={"job_description": "Prioritize strategy."}, affected=[])
    assert caught.value.code == "resume_latex_invalid"


def test_saved_job_context_must_match_its_analysis_binding(retained_tex):
    from career_evidence_graph.career_portal_data import PortalDataError

    store, _, _, _, _, _, original, _ = retained_tex
    with pytest.raises(PortalDataError) as caught:
        rewrite_checkpoint(store, original, job_context={"job_description": "Invented old JD"})
    assert caught.value.code == "resume_draft_invalid"


def test_damaged_retained_job_context_cannot_be_silently_reused(retained_tex):
    from career_evidence_graph.career_portal_data import PortalDataError

    data = list(retained_tex)
    data[-1] = rewrite_checkpoint(data[0], data[-1], job_context={"company": "Corrupted"})
    with pytest.raises(PortalDataError) as caught:
        refresh(data, job_change={"notes": "Unrelated note"}, affected=[])
    assert caught.value.code == "resume_latex_invalid"
