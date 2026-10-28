"""Loopback binding and complete-source presentation use synthetic records only."""

import json
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace

import pytest
from test_application_flow import wait_for
from test_application_information import answer, write_library
from test_career_portal_http import portal as portal
from test_job_explanation_browser import explanation_portal, reveal_control
from test_portal_workflow_browser import browser_page as browser_page
from test_preparation_entry import post, snapshot

from career_evidence_graph.application_information import (
    material_information_library,
    read_information_library,
)
from career_evidence_graph.career_portal_data import ApplicationStore


@contextmanager
def generated_portal(portal, tmp_path, monkeypatch):
    project = tmp_path / "latex-base"
    project.mkdir()
    (project / "main.tex").write_text(
        r"\documentclass{article}\begin{document}Original\end{document}"
    )
    job = ApplicationStore(portal.applications).create_application(
        {
            "company": "Synthetic",
            "role_title": "Engineer",
            "job_description": "Build Python services.",
        }
    )
    with explanation_portal(portal, tmp_path) as (active, work):
        _, task = post(
            active, "create", {"application_id": job["id"], "application_revision": job["revision"]}
        )
        service = active.server.application_flow_service
        # The group-review fixture resumes a saved pre-JSON full-TeX task.
        with service.applications.write_lock():
            state = service._load()
            service._task(state, task["id"]).pop("material_contract", None)
            service._save(state)
        task = service.snapshot(task["id"])["active_task"]
        post(
            active,
            "start",
            {"task_id": task["id"], "task_revision": task["revision"], "stage": "analysis"},
        )
        task = wait_for(service, task["id"], lambda row: row["status"] == "analysis_ready")
        calls, drafts = [], {}

        def generate(application_id, revision, **kwargs):
            calls.append(kwargs)
            group = {
                "id": "synthetic",
                "title": "Synthetic project",
                "original": "Original fact",
                "rewritten": "JD-specific wording",
                "sources": [{"source_id": "synthetic-source"}],
                "attribution": ["User"],
                "reason": "Relevant Python evidence",
            }
            result = {
                "id": "a" * 32,
                "kind": "draft",
                "origin": "generated_latex",
                "factual_review": "pending",
                "draft_sha256": "b" * 64,
                "application_id": application_id,
                "revision": revision,
                "analysis_binding": {"analysis_id": kwargs["analysis"]["id"]},
                "task_inputs": kwargs["task_inputs"],
                "resume_configuration_revision": kwargs["task_inputs"][
                    "resume_configuration_revision"
                ],
                "base_checkpoint": kwargs["latex_base"],
                "source_checkpoint": {
                    "project_root": str(tmp_path / "generated"),
                    "main": "main.tex",
                    "files": {"main.tex": "c" * 64},
                    "source_revision": "d" * 64,
                    "archive_sha256": "e" * 64,
                },
                "latex_source": (
                    r"\documentclass{article}\begin{document}JD-specific wording\end{document}"
                ),
                "review_groups": [group],
                "omitted_groups": [group | {"title": "Omitted project", "reason": "Less relevant"}],
                "verification_queue": [
                    group | {"title": "Unverified project", "reason": "Attribution unresolved"}
                ],
            }
            drafts[result["id"]] = result
            return result

        monkeypatch.setattr(active.server.application_resume_store, "generate_for_task", generate)
        monkeypatch.setattr(
            active.server.application_resume_store, "draft", lambda identifier: drafts[identifier]
        )
        yield active, task, project, calls, work


def bind_generate(active, task, project):
    status, task = post(
        active,
        "bind-latex-base",
        {
            "task_id": task["id"],
            "task_revision": task["revision"],
            "project_root": str(project),
            "main": "main.tex",
        },
    )
    assert status == 200, task
    status, _ = post(
        active,
        "start",
        {"task_id": task["id"], "task_revision": task["revision"], "stage": "resume"},
    )
    assert status == 200
    task = wait_for(
        active.server.application_flow_service,
        task["id"],
        lambda row: row["status"] in {"draft_ready", "failed"},
    )
    assert task["status"] == "draft_ready", task
    return task


def test_http_forwards_explicit_base_and_existing_library_without_export(
    portal, tmp_path, monkeypatch
):
    with generated_portal(portal, tmp_path, monkeypatch) as (active, task, project, calls, work):
        before = (project / "main.tex").read_bytes()
        task = bind_generate(active, task, project)
        assert calls[0]["latex_base"] == task["latex_base"]
        assert (
            calls[0]["information_library"]["revision"]
            == task["inputs"]["information_library_revision"]
        )
        assert snapshot(active)["draft_integrity"]["status"] == "valid"
        status, _, body = active.request("GET", f"/api/flow/drafts/{task['draft_id']}")
        assert status == 200 and b"latex_source" in body
        assert not work["exports"] and (project / "main.tex").read_bytes() == before
        payload = {
            "task_id": task["id"],
            "task_revision": task["revision"],
            "draft_id": task["draft_id"],
            "draft_sha256": task["draft_sha256"],
        }
        for action in ("review-draft", "export-pdf", "authorize-latex-export"):
            assert post(active, action, payload)[0] == 409
        assert (
            post(
                active,
                "confirm-materials",
                {
                    "task_id": task["id"],
                    "task_revision": task["revision"],
                    "resume_id": task["draft_id"],
                    "resume_sha256": task["draft_sha256"],
                },
            )[0]
            == 409
        )
        assert not task.get("worker_ref") and not task["materials_confirmed"]


def test_http_real_full_latex_store_saves_two_projects_and_reuses_confirmed_identity(
    portal, tmp_path, monkeypatch
):
    """Exercise the actual store and full generator; only the model transport is fake."""
    library_root = tmp_path / "existing-information"
    identity_key, identity = answer("Full name", "Synthetic Person", scope={"company": "Synthetic"})
    write_library(library_root, answers={identity_key: identity})
    library_before = (library_root / "answers.json").read_bytes()
    base = tmp_path / "complete-latex-base"
    base.mkdir()
    original = (
        "\\documentclass[a4paper]{article}\n\\begin{document}\n"
        "Synthetic Person\n"
        "\\section*{Synthetic Python service}\nImplemented a Python service.\n"
        "\\section*{Synthetic operations project}\nOperated Python services.\n"
        "\\end{document}\n"
    )
    (base / "main.tex").write_text(original)
    (base / "style-note.txt").write_text("Preserve ancillary source bytes")
    base_before = {path.name: path.read_bytes() for path in base.iterdir()}
    job = ApplicationStore(portal.applications).create_application(
        {
            "company": "Synthetic",
            "role_title": "Engineer",
            "job_description": "Build and operate Python services.",
        }
    )
    library_revision = material_information_library(job, read_information_library(library_root))[
        "revision"
    ]
    with explanation_portal(portal, tmp_path, information_library_root=library_root) as (
        active,
        work,
    ):
        (portal.career / "contributions/operations.md").write_text(
            "# Synthetic operations project\n\n## Scope\nOperated Python services.\n\n"
            "## Responsibility attribution\n| Work | Owner |\n| --- | --- |\n"
            "| Operations | User |\n\n## Boundaries\nNo team-wide ownership claim.\n"
        )
        model_payloads = []

        def model(config, prompt, **kwargs):
            payload = json.loads(prompt[prompt.index("{") :])
            model_payloads.append(payload)
            sources = {row["title"]: row for row in payload["sources"]}
            groups = [
                {
                    "title": "Confirmed identity",
                    "start_line": 1,
                    "end_line": 1,
                    "source_ids": ["answer:" + identity_key],
                    "latex": "Synthetic Person\n",
                    "disposition": "include",
                    "reason": "Reuse applicable confirmed identity",
                }
            ]
            for title, start, text in (
                ("Synthetic Python service", 2, "Implemented a Python service."),
                ("Synthetic operations project", 4, "Operated Python services."),
            ):
                groups.append(
                    {
                        "title": title,
                        "start_line": start,
                        "end_line": start + 1,
                        "source_ids": [sources[title]["source_id"]],
                        "latex": f"\\section*{{{title}}}\n{text}\n",
                        "disposition": "include",
                        "reason": "Relevant documented Python work",
                    }
                )
            return SimpleNamespace(
                structured_result={"groups": groups, "limitations": []},
                model_dump=lambda **kwargs: {"synthetic": True},
            )

        store = active.server.application_resume_store
        monkeypatch.setattr(store, "model_runner", model)
        store.model_mode = "synthetic"
        status, task = post(
            active, "create", {"application_id": job["id"], "application_revision": job["revision"]}
        )
        assert status == 200
        # Exercise the historical full-TeX contract, not new JSON generation.
        service = active.server.application_flow_service
        with service.applications.write_lock():
            state = service._load()
            service._task(state, task["id"]).pop("material_contract", None)
            service._save(state)
        task = service.snapshot(task["id"])["active_task"]
        assert (
            post(
                active,
                "start",
                {"task_id": task["id"], "task_revision": task["revision"], "stage": "analysis"},
            )[0]
            == 200
        )
        task = wait_for(
            active.server.application_flow_service,
            task["id"],
            lambda row: row["status"] == "analysis_ready",
        )
        analysis_id = task["analysis_id"]
        task = bind_generate(active, task, base)
        assert task["analysis_id"] == analysis_id
        assert task["latex_base"]["project_root"] == str(base)
        assert task["inputs"]["information_library_revision"] == library_revision
        assert snapshot(active)["draft_integrity"]["status"] == "valid"
        status, _, body = active.request("GET", f"/api/flow/drafts/{task['draft_id']}")
        assert status == 200
        draft = json.loads(body)
        assert draft["origin"] == "generated_latex" and draft["factual_review"] == "pending"
        assert len(draft["review_groups"]) == 3
        assert "\\section*{Synthetic Python service}" in draft["latex_source"]
        assert "\\section*{Synthetic operations project}" in draft["latex_source"]
        assert draft["latex_source"].startswith("\\documentclass[a4paper]{article}")
        assert draft["latex_source"].endswith("\\end{document}\n")
        assert draft["information_library_revision"] == library_revision
        identity_source = draft["review_groups"][0]["sources"][0]
        assert identity_source["source_id"] == "answer:" + identity_key
        assert identity_source["confirmation_state"] == "confirmed"
        saved_project = Path(draft["source_checkpoint"]["project_root"])
        assert saved_project != base
        assert (saved_project / "main.tex").read_text() == draft["latex_source"]
        assert (saved_project / "style-note.txt").read_bytes() == base_before["style-note.txt"]
        assert {path.name: path.read_bytes() for path in base.iterdir()} == base_before
        assert (library_root / "answers.json").read_bytes() == library_before
        assert model_payloads[0]["base"] == original and len(model_payloads) == 1
        assert not work["exports"] and not list(store.root.rglob("*.pdf"))
        payload = {
            "task_id": task["id"],
            "task_revision": task["revision"],
            "draft_id": task["draft_id"],
            "draft_sha256": task["draft_sha256"],
        }
        for action in ("review-draft", "export-pdf", "authorize-latex-export"):
            assert post(active, action, payload)[0] == 409
        assert (
            post(
                active,
                "confirm-materials",
                {
                    "task_id": task["id"],
                    "task_revision": task["revision"],
                    "resume_id": task["draft_id"],
                    "resume_sha256": task["draft_sha256"],
                },
            )[0]
            == 409
        )
        assert task["resume_id"] is None and not task["materials_confirmed"]
        assert not task.get("worker_ref")


@pytest.mark.worker_browser
def test_complete_source_and_group_dispositions_are_readable_without_review_shortcut(
    portal, tmp_path, monkeypatch, browser_page
):
    from playwright.sync_api import expect

    with generated_portal(portal, tmp_path, monkeypatch) as (active, task, project, calls, work):
        page = browser_page
        page.goto(active.origin + "/#flow")
        reveal_control(page, page.get_by_label("完整简历底稿目录", exact=True))
        page.get_by_label("完整简历底稿目录", exact=True).fill(str(project))
        page.get_by_label("完整简历底稿主文件", exact=True).fill("main.tex")
        page.locator("#flow-bind-latex-base").click()
        expect(page.locator("#flow-start-resume")).to_have_text("生成完整 LaTeX 岗位版本")
        page.locator("#flow-start-resume").click()
        expect(page.locator("#flow-draft")).to_contain_text("完整 LaTeX 岗位版本")
        page.locator("#flow-full-latex-source summary").click()
        expect(page.locator("#flow-full-latex-source")).to_contain_text("JD-specific wording")
        for identifier, text in (
            ("flow-review-groups", "Synthetic project"),
            ("flow-omitted-groups", "Omitted project"),
            ("flow-verification-queue", "Unverified project"),
        ):
            expect(page.locator(f"#{identifier}")).to_contain_text(text)
        page.locator("#flow-review-groups summary").click()
        for text in ("Original fact", "JD-specific wording", "synthetic-source", "User"):
            expect(page.locator("#flow-review-groups")).to_contain_text(text)
        expect(page.locator("#flow-review-draft")).to_have_count(0)
        expect(page.locator("#flow-export-pdf")).to_have_count(0)
        expect(page.locator("#flow-confirm-materials")).to_have_count(0)
        expect(page.locator("#flow-worker")).to_have_count(0)
        page.reload()
        expect(page.locator("#flow-full-latex-source")).to_contain_text("JD-specific wording")
        assert len(calls) == 1 and not work["exports"]
