"""Career corrections retain the complete manual source outside affected groups."""

import json
from copy import deepcopy
from types import SimpleNamespace

import pytest
from test_application_flow import wait_for
from test_application_resume import task_resume as task_resume
from test_automatic_material_reuse_edit import complete_portal as complete_portal
from test_career_portal_http import Portal
from test_full_latex_generation import full_latex as full_latex
from test_full_latex_generation import generate

from career_evidence_graph.application_prism import source_snapshot
from career_evidence_graph.application_resume import career_source_snapshot
from career_evidence_graph.career_portal_data import PortalDataError


def test_career_correction_preserves_unaffected_manual_groups(full_latex):
    store, job, _, analysis, calls, _, _, inputs = full_latex
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
    document = store.catalog.root / "contributions/project-1.md"
    document.write_text(document.read_text().replace("built 1 Python", "built 11 Python"))
    snapshot = career_source_snapshot(store.catalog)
    current_analysis = deepcopy(analysis) | {"source_snapshot_revision": snapshot["revision"]}
    requests = []

    def model(_config, prompt, **_options):
        payload = json.loads(prompt[prompt.index("{") :])
        requests.append(payload)
        groups = []
        for group in manual["review_groups"]:
            begin = next(
                r["line_number"]
                for r in payload["body_lines"]
                if r["text"] == f"% TomorrowStar group {group['id']} begin\n"
            )
            end = next(
                r["line_number"]
                for r in payload["body_lines"]
                if r["text"] == f"% TomorrowStar group {group['id']} end\n"
            )
            text = group["rewritten"].replace("built 1 Python", "built 11 Python")
            # A general rewriter tries to erase this valid manual wording.
            text = text.replace(
                "Built 6 Python services; analyzed strategy.",
                "Analyzed strategy; built 6 Python services.",
            )
            groups.append(
                {
                    "title": group["title"],
                    "start_line": begin,
                    "end_line": end,
                    "source_ids": [s["source_id"] for s in group["sources"]],
                    "latex": text,
                    "disposition": "include",
                    "reason": "Synthetic current career correction",
                }
            )
        return SimpleNamespace(
            structured_result={"groups": groups, "limitations": []},
            model_dump=lambda **_: {"synthetic": True},
        )

    store.model_runner = model
    result = store.generate_for_task(
        job["id"],
        job["revision"],
        source_snapshot=snapshot,
        analysis=current_analysis,
        draft_only=True,
        task_inputs={"sources_revision": snapshot["revision"], "policy": "v1.0"},
        latex_base=source_snapshot(store.root / manual["id"] / "project", "main.tex"),
        retained_draft=manual,
    )
    assert "built 11 Python services." in result["latex_source"]
    assert "Built 6 Python services; analyzed strategy." in result["latex_source"]
    assert not result["verification_queue"]
    assert store.draft(manual["id"])["latex_source"] == manual_text
    assert store.draft(original["id"])["latex_source"] == original["latex_source"]
    assert len(requests) == 1 and len(calls) == 1


def test_retained_refresh_rejects_a_different_complete_base(full_latex):
    store, job, sources, analysis, _, project, _, inputs = full_latex
    original = generate(full_latex)
    # Matching body text does not authorize discarding the saved full preamble.
    main = project / "main.tex"
    main.write_text(original["latex_source"].replace("article", "report"))
    with pytest.raises(PortalDataError) as caught:
        store.generate_for_task(
            job["id"],
            job["revision"],
            source_snapshot=sources,
            analysis=analysis,
            draft_only=True,
            task_inputs=inputs,
            latex_base=source_snapshot(project, "main.tex"),
            retained_draft=original,
        )
    assert caught.value.code == "resume_latex_invalid"


def test_missing_career_reference_does_not_retain_obsolete_manual_content(full_latex):
    store, job, _, analysis, _, _, _, _ = full_latex
    original = generate(full_latex)
    (store.catalog.root / "contributions/project-1.md").unlink()
    snapshot = career_source_snapshot(store.catalog)
    store.model_runner = lambda *_args, **_options: pytest.fail(
        "Missing facts need source resolution"
    )
    with pytest.raises(PortalDataError) as caught:
        store.generate_for_task(
            job["id"],
            job["revision"],
            source_snapshot=snapshot,
            analysis=analysis | {"source_snapshot_revision": snapshot["revision"]},
            draft_only=True,
            task_inputs={"sources_revision": snapshot["revision"]},
            latex_base=original["source_checkpoint"],
            retained_draft=original,
        )
    assert caught.value.code == "resume_latex_invalid"
    assert store.draft(original["id"])["latex_source"] == original["latex_source"]


def test_unstructured_context_change_rechecks_its_cited_group(full_latex):
    store, job, _, analysis, calls, _, output, _ = full_latex
    original = generate(full_latex)
    document = store.catalog.root / "contributions/project-1.md"
    document.write_text(
        document.read_text() + "\n## Additional context\n\nDelivery is not yet verified.\n"
    )
    snapshot = career_source_snapshot(store.catalog)
    output["groups"][1]["disposition"] = "verify"
    output["groups"][1]["reason"] = "Additional current context conflicts with completed delivery"
    result = store.generate_for_task(
        job["id"],
        job["revision"],
        source_snapshot=snapshot,
        analysis=analysis | {"source_snapshot_revision": snapshot["revision"]},
        draft_only=True,
        task_inputs={"sources_revision": snapshot["revision"]},
        latex_base=original["source_checkpoint"],
        retained_draft=original,
    )
    assert len(calls) == 2
    assert [row["title"] for row in result["verification_queue"]] == ["Project 1"]
    assert store.draft(original["id"])["latex_source"] == original["latex_source"]


def missing_context_impact(_config, prompt, **_options):
    payload = json.loads(prompt[prompt.index("{") :])
    assert payload["update_context"]["source_context_changed"] is True
    return SimpleNamespace(
        structured_result={
            "groups": payload["update_context"]["retained_groups"],
            "limitations": [],
        },
        model_dump=lambda **_: {"synthetic": True},
    )


def test_unmapped_consumed_context_without_impact_judgment_keeps_manual_source(full_latex):
    store, job, _, analysis, _, _, _, _ = full_latex
    original = generate(full_latex)
    document = store.catalog.root / "contributions/keyword.md"
    document.write_text(
        document.read_text()
        + "\n## Additional context\n\nDelivery was performed by another person.\n"
    )
    snapshot = career_source_snapshot(store.catalog)
    store.model_runner = missing_context_impact
    with pytest.raises(PortalDataError) as caught:
        store.generate_for_task(
            job["id"],
            job["revision"],
            source_snapshot=snapshot,
            analysis=analysis | {"source_snapshot_revision": snapshot["revision"]},
            draft_only=True,
            task_inputs={"sources_revision": snapshot["revision"]},
            latex_base=original["source_checkpoint"],
            retained_draft=original,
        )
    assert caught.value.code == "resume_latex_invalid"
    assert store.draft(original["id"])["latex_source"] == original["latex_source"]


@pytest.mark.parametrize("category", ["research", "masterThesis"])
def test_unmapped_research_link_without_impact_judgment_cannot_silently_reuse(
    full_latex,
    category,
):
    data = list(full_latex)
    store, job, _, analysis, calls, _, _, _ = data
    profile = store.catalog.root / "sources/profile.json"
    initial = json.loads(profile.read_text())
    initial[category] = [
        {
            "name": "Synthetic Research",
            "points": [],
            "links": [{"label": "Evidence", "href": "https://evidence.example.test/user-owned"}],
        }
    ]
    profile.write_text(json.dumps(initial))
    snapshot = career_source_snapshot(store.catalog)
    assert snapshot["profile"]["master_thesis" if category == "masterThesis" else category]
    data[2] = snapshot
    data[3] = analysis | {"source_snapshot_revision": snapshot["revision"]}
    data[7] = {"sources_revision": snapshot["revision"], "policy": "v1.0"}
    original = generate(tuple(data))
    assert any("user-owned" in doc.get("content", "") for doc in calls[0]["document_context"])
    initial[category][0]["links"][0]["href"] = "https://evidence.example.test/another-person"
    profile.write_text(json.dumps(initial))
    snapshot = career_source_snapshot(store.catalog)
    store.model_runner = missing_context_impact
    with pytest.raises(PortalDataError) as caught:
        store.generate_for_task(
            job["id"],
            job["revision"],
            source_snapshot=snapshot,
            analysis=data[3] | {"source_snapshot_revision": snapshot["revision"]},
            draft_only=True,
            task_inputs={"sources_revision": snapshot["revision"]},
            latex_base=original["source_checkpoint"],
            retained_draft=original,
        )
    assert caught.value.code == "resume_latex_invalid"
    assert store.draft(original["id"])["latex_source"] == original["latex_source"]


def test_retained_snapshot_drift_cannot_hide_new_unstructured_context(full_latex):
    store, job, _, analysis, _, _, _, _ = full_latex
    original = generate(full_latex)
    document = store.catalog.root / "contributions/project-1.md"
    document.write_text(
        document.read_text() + "\n## Additional context\n\nDelivery not yet verified.\n"
    )
    snapshot = career_source_snapshot(store.catalog)
    historical = store.root / original["id"] / "source-snapshot.json"
    damaged = json.loads(historical.read_text())
    damaged["documents"] = snapshot["documents"]
    historical.write_text(json.dumps(damaged))
    store.model_runner = lambda *_args, **_options: pytest.fail(
        "Drifted retained snapshot must stop"
    )
    with pytest.raises(PortalDataError) as caught:
        store.generate_for_task(
            job["id"],
            job["revision"],
            source_snapshot=snapshot,
            analysis=analysis | {"source_snapshot_revision": snapshot["revision"]},
            draft_only=True,
            task_inputs={"sources_revision": snapshot["revision"]},
            latex_base=original["source_checkpoint"],
            retained_draft=original,
        )
    assert caught.value.code == "resume_latex_invalid"


def test_http_profile_correction_reanalyzes_and_keeps_manual_career_content(complete_portal):
    from threading import Thread

    server, store, original, calls = complete_portal
    flow = server.application_flow_service
    task = flow.begin_automatic_edit(original["id"], original["revision"])
    manual_text = store.draft(task["draft_id"])["latex_source"].replace(
        "Analyzed strategy; built 6 Python services.", "Built 6 Python services; analyzed strategy."
    )
    task = flow.save_automatic_source(
        task["id"], task["revision"], task["prism"]["source_revision"], manual_text
    )
    manual = store.draft(task["draft_id"])
    old_pdf = store.pdf(original["resume_id"])
    store.model_runner = lambda *_args, **_options: pytest.fail(
        "Unchanged career groups need no model"
    )
    portal = Portal(server, store.applications.root, store.catalog.root)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        evidence = next(
            row
            for row in store.catalog.list_evidence()
            if row["source_name"] == "sources/profile.json"
        )
        status, _, raw = portal.request("GET", "/api/evidence/" + evidence["id"])
        assert status == 200
        detail = json.loads(raw)
        status, _, raw = portal.request(
            "PATCH",
            "/api/evidence/" + evidence["id"],
            body=json.dumps(
                {
                    "revision": detail["revision"],
                    "content": json.dumps(
                        json.loads(detail["content"])
                        | {"title": "Updated synthetic career headline"}
                    ),
                    "source": "Explicit synthetic correction",
                }
            ).encode(),
            headers=portal.write_headers(),
        )
        assert status == 200, raw
        assert len(json.loads(raw)["history"]) == 1
        job = store.applications.get_application(original["application_id"])
        status, _, raw = portal.request(
            "POST",
            "/api/flow/update-inputs",
            body=json.dumps(
                {
                    "task_id": task["id"],
                    "task_revision": task["revision"],
                    "application_revision": job["revision"],
                }
            ).encode(),
            headers=portal.write_headers(),
        )
        assert status == 200, raw
        task = json.loads(raw)
        assert task["analysis_id"] is None
        flow.start(task["id"], task["revision"], "analysis")
        task = wait_for(flow, task["id"], lambda row: row["status"] == "analysis_ready")
        assert task["analysis_id"] != original["analysis_id"]
        flow.start(task["id"], task["revision"], "resume")
        task = wait_for(
            flow, task["id"], lambda row: row["status"] in {"draft_ready", "failed", "stale"}
        )
        assert task["status"] == "draft_ready", task["stages"]
        flow.start(task["id"], task["revision"], "export")
        task = wait_for(
            flow,
            task["id"],
            lambda row: row["status"] in {"materials_ready", "failed", "needs_recheck"},
        )
        assert task["status"] == "materials_ready", task["stages"]
        current = store.read_export(task["resume_id"])
        assert "Updated synthetic career headline" not in current["latex_source"]
        assert "Built 6 Python services; analyzed strategy." in current["latex_source"]
        assert store.draft(manual["id"])["latex_source"] == manual_text
        assert store.pdf(original["resume_id"]) == old_pdf
        assert len(calls) == 1
        assert len([a for a in task["artifacts"] if a["stage"] == "analysis"]) == 2
    finally:
        server.shutdown()
        thread.join(timeout=5)
