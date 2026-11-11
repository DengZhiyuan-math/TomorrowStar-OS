"""Saved manual omissions remain mapped when their source documents change."""

import json
import re
from copy import deepcopy
from types import SimpleNamespace

from test_application_flow import wait_for
from test_application_resume import task_resume as task_resume
from test_automatic_material_reuse_edit import complete_portal as complete_portal
from test_flow_tex_impact_updates import refresh_tex, save_manual_wording
from test_full_latex_generation import full_latex as full_latex


def test_manual_omission_survives_multiple_source_updates_after_a_jd_refresh(complete_portal):
    server, store, original, generation = complete_portal
    flow = server.application_flow_service
    manual = save_manual_wording(flow, store, original)
    draft = store.draft(manual["draft_id"])
    omitted = next(group for group in draft["review_groups"] if group["title"] == "Project 3")
    pattern = (
        rf"(?ms)^% TomorrowStar group {omitted['id']} begin\n"
        rf".*?^% TomorrowStar group {omitted['id']} end\n"
    )
    text, count = re.subn(pattern, "", draft["latex_source"])
    assert count == 1
    saved = flow.save_automatic_source(
        manual["id"], manual["revision"], manual["prism"]["source_revision"], text
    )
    saved_draft = store.draft(saved["draft_id"])
    assert [group["title"] for group in saved_draft["omitted_groups"]] == ["Project 3"]
    calls = []

    def model(config, prompt, **kwargs):
        payload = json.loads(prompt[prompt.index("{") :])
        calls.append(payload)
        groups = deepcopy(payload["update_context"]["retained_groups"])
        for group in groups:
            if group["title"] == "Project 6":
                group["latex"] = (
                    "\\section*{Project 6}\nAnalyzed strategy; built 6 Python services.\n"
                )
        return SimpleNamespace(
            structured_result={"groups": groups, "limitations": [], "affected_group_indexes": []},
            model_dump=lambda **_: {"synthetic": True},
        )

    store.model_runner = model
    job = store.applications.get_application(original["application_id"])
    job = store.applications.update_application(
        job["id"], {"location": "Updated synthetic location"}, job["revision"]
    )
    task = refresh_tex(flow, saved, job)
    assert task["status"] == "draft_ready", task["stages"]
    first = store.draft(task["draft_id"])
    assert first["latex_source"] == text
    assert len(calls) == len(generation) == 1
    document = store.catalog.root / "contributions/project-3.md"
    for before, after in [(3, 33), (33, 333)]:
        document.write_text(
            document.read_text().replace(f"built {before} Python", f"built {after} Python")
        )
        task = refresh_tex(flow, task, job)
        assert task["status"] == "draft_ready", task["stages"]
        current = store.draft(task["draft_id"])
        assert current["latex_source"] == text
        assert "Project 3" not in current["latex_source"]
        assert "Built 6 Python services; analyzed strategy." in current["latex_source"]
        assert not current["verification_queue"]
        assert len(calls) == len(generation) == 1
    assert store.draft(saved["draft_id"]) == saved_draft
    assert store.draft(first["id"]) == first
    flow.start(task["id"], task["revision"], "export")
    exported = wait_for(
        flow,
        task["id"],
        lambda row: row["status"] in {"materials_ready", "failed", "needs_recheck"},
    )
    assert exported["status"] == "materials_ready", exported["stages"]
    assert store.read_export(exported["resume_id"])["latex_source"] == text
