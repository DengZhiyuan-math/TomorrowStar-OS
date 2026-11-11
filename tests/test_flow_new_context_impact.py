"""New context is assessed against actual manual TeX through the automatic flow."""

import json
import re
from copy import deepcopy
from types import SimpleNamespace

from test_application_flow import wait_for
from test_application_resume import task_resume as task_resume
from test_automatic_material_reuse_edit import complete_portal as complete_portal
from test_flow_tex_impact_updates import refresh_tex, save_manual_wording
from test_full_latex_generation import full_latex as full_latex


def test_unrelated_new_context_keeps_manual_tex_and_exports_current_materials(complete_portal):
    server, store, original, generation = complete_portal
    flow = server.application_flow_service
    task = save_manual_wording(flow, store, original)
    manual = store.draft(task["draft_id"])
    old_pdf = store.pdf(original["resume_id"])
    document = store.catalog.root / "contributions/keyword.md"
    document.write_text(
        document.read_text() + "\n## Additional context\n\nUnrelated project note.\n"
    )
    requests = []

    def model(config, prompt, **_options):
        payload = json.loads(prompt[prompt.index("{") :])
        requests.append(payload)
        groups = deepcopy(payload["update_context"]["retained_groups"])
        for group in groups:
            group["latex"] = group["latex"].replace(
                "Built 6 Python services; analyzed strategy.",
                "Analyzed strategy; built 6 Python services.",
            )
        return SimpleNamespace(
            structured_result={
                "groups": groups,
                "limitations": [],
                "affected_group_indexes": [],
                "context_impact_reason": "The note is unrelated to claims in the actual TeX.",
            },
            model_dump=lambda **_: {"synthetic": True},
        )

    store.model_runner = model
    job = store.applications.get_application(original["application_id"])
    task = refresh_tex(flow, task, job)
    assert task["status"] == "draft_ready", task["stages"]
    current = store.draft(task["draft_id"])
    assert current["latex_source"] == manual["latex_source"]
    assert len(requests) == len(generation) == 1
    assert store.draft(manual["id"]) == manual
    assert store.pdf(original["resume_id"]) == old_pdf
    flow.start(task["id"], task["revision"], "export")
    exported = wait_for(
        flow,
        task["id"],
        lambda row: row["status"] in {"materials_ready", "failed", "needs_recheck"},
    )
    assert exported["status"] == "materials_ready", exported["stages"]
    assert store.read_export(exported["resume_id"])["latex_source"] == manual["latex_source"]


def test_new_supported_context_merges_only_affected_tex_and_keeps_manual_omission(complete_portal):
    server, store, original, generation = complete_portal
    flow = server.application_flow_service
    task = save_manual_wording(flow, store, original)
    editable = store.draft(task["draft_id"])
    omitted = next(g for g in editable["review_groups"] if g["title"] == "Project 3")
    pattern = (
        rf"(?ms)^% TomorrowStar group {omitted['id']} begin\n"
        rf".*?^% TomorrowStar group {omitted['id']} end\n"
    )
    text, count = re.subn(pattern, "", editable["latex_source"])
    assert count == 1
    task = flow.save_automatic_source(
        task["id"], task["revision"], task["prism"]["source_revision"], text
    )
    manual = store.draft(task["draft_id"])
    path = store.catalog.root / "contributions/supporting-delivery.md"
    path.write_text(
        "# Supporting delivery\n\n## Scope\n\n"
        "Analyzed strategy and built 11 Python services for Project 1.\n\n"
        "## Responsibility attribution\n\n| Area | Attribution |\n| --- | --- |\n"
        "| Delivery | User |\n"
    )
    requests = []
    target = {"count": 11}

    def model(_config, prompt, **_options):
        payload = json.loads(prompt[prompt.index("{") :])
        requests.append(payload)
        groups = deepcopy(payload["update_context"]["retained_groups"])
        support = next(s for s in payload["sources"] if s["title"] == "Supporting delivery")
        for group in groups:
            if group["title"] == "Project 1":
                group["latex"] = re.sub(
                    r"built [0-9]+ Python", f"built {target['count']} Python", group["latex"]
                )
                if support["source_id"] not in group["source_ids"]:
                    group["source_ids"].append(support["source_id"])
            if group["title"] == "Project 6":
                group["latex"] = group["latex"].replace(
                    "Built 6 Python services; analyzed strategy.",
                    "Analyzed strategy; built 6 Python services.",
                )
        return SimpleNamespace(
            structured_result={
                "groups": groups,
                "limitations": [],
                "affected_group_indexes": [1],
                "context_impact_reason": "The new user-owned source qualifies Project 1 delivery.",
            },
            model_dump=lambda **_: {"synthetic": True},
        )

    store.model_runner = model
    job = store.applications.get_application(original["application_id"])
    task = refresh_tex(flow, task, job)
    assert task["status"] == "draft_ready", task["stages"]
    merged = store.draft(task["draft_id"])
    assert not merged["verification_queue"]
    assert "built 11 Python services" in merged["latex_source"]
    assert "Project 3" not in merged["latex_source"]
    for group in manual["review_groups"]:
        if group["title"] != "Project 1":
            marker = (
                rf"(?ms)^% TomorrowStar group {group['id']} begin\n"
                rf".*?^% TomorrowStar group {group['id']} end\n"
            )
            assert re.search(marker, merged["latex_source"])[0] == re.search(marker, text)[0]
    path.write_text(path.read_text().replace("11 Python", "111 Python"))
    target["count"] = 111
    task = refresh_tex(flow, task, job)
    assert task["status"] == "draft_ready", task["stages"]
    updated = store.draft(task["draft_id"])
    assert "built 111 Python services" in updated["latex_source"]
    assert "Built 6 Python services; analyzed strategy." in updated["latex_source"]
    assert "Project 3" not in updated["latex_source"]
    assert len(requests) == 2 and len(generation) == 1
    assert store.draft(manual["id"]) == manual
    assert store.draft(merged["id"]) == merged
    flow.start(task["id"], task["revision"], "export")
    exported = wait_for(
        flow,
        task["id"],
        lambda row: row["status"] in {"materials_ready", "failed", "needs_recheck"},
    )
    assert exported["status"] == "materials_ready", exported["stages"]
    assert store.read_export(exported["resume_id"])["latex_source"] == updated["latex_source"]
