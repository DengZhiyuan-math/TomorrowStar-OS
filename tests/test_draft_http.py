"""Draft review uses loopback authorization and exact persisted draft bytes."""

import hashlib
import json

import pytest
from test_career_portal_http import portal as portal
from test_job_explanation_browser import explanation_portal
from test_preparation_entry import post, snapshot

from career_evidence_graph.career_portal_data import ApplicationStore


@pytest.fixture(autouse=True)
def isolated_connection(tmp_path, monkeypatch):
    monkeypatch.setenv("CODEX_HOME", str(tmp_path / "synthetic-codex"))
    monkeypatch.delenv("CODEX_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)


def import_latex_draft(active, job, tmp_path):
    """Persist actual local TeX through the supported HTTP import boundary."""
    project = tmp_path / ("latex-" + job["id"])
    project.mkdir()
    (project / "main.tex").write_text(
        r"\documentclass{article}\begin{document}Synthetic existing CV\end{document}"
    )
    status, task = post(
        active,
        "import-latex",
        {
            "application_id": job["id"],
            "application_revision": job["revision"],
            "project_root": str(project),
            "main": "main.tex",
        },
    )
    assert status == 200, task
    assert task["origin"] == "existing_latex"
    return task


def test_draft_routes_require_loopback_authorization_and_map_review_status(portal, tmp_path):
    job = ApplicationStore(portal.applications).create_application(
        {
            "company": "Synthetic",
            "role_title": "Engineer",
            "job_description": "Build Python services.",
        }
    )
    with explanation_portal(portal, tmp_path) as (active, _):
        task = import_latex_draft(active, job, tmp_path)
        assert task["status"] == "draft_ready"
        status, _, raw = active.request("GET", "/api/flow/drafts/" + task["draft_id"])
        assert status == 200, raw
        assert json.loads(raw)["id"] == task["draft_id"]
        assert snapshot(active)["draft_integrity"]["status"] == "valid"
        payload = {
            "task_id": task["id"],
            "task_revision": task["revision"],
            "draft_id": task["draft_id"],
            "draft_sha256": task["draft_sha256"],
        }
        assert (
            active.request("POST", "/api/flow/review-draft", body=json.dumps(payload).encode())[0]
            == 403
        )
        assert post(active, "review-draft", payload | {"draft_sha256": "f" * 64})[0] == 409
        assert post(active, "review-draft", payload | {"accepted": True})[0] == 400
        assert post(active, "review-draft", payload)[0] == 409
        assert post(active, "authorize-latex-export", payload)[0] == 200


@pytest.mark.parametrize("damage", ["bytes", "self_consistent_integrity"])
def test_corrupted_draft_routes_return_conflict(portal, tmp_path, damage):
    job = ApplicationStore(portal.applications).create_application(
        {
            "company": "Synthetic",
            "role_title": "Engineer",
            "job_description": "Build Python services.",
        }
    )
    with explanation_portal(portal, tmp_path) as (active, _):
        task = import_latex_draft(active, job, tmp_path)
        directory = active.server.application_resume_store.root / task["draft_id"]
        path = directory / "draft.json"
        if damage == "bytes":
            path.write_bytes(b'{"unverified":"changed"}')
        else:
            content = json.loads(path.read_bytes())
            content["limitations"].append("A changed claim absent from the adopted artifact.")
            path.write_text(json.dumps(content))
            (directory / "draft-integrity.json").write_text(
                json.dumps(
                    {
                        "schemaVersion": 1,
                        "id": task["draft_id"],
                        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                    }
                )
            )
        assert active.request("GET", "/api/flow/drafts/" + task["draft_id"])[0] == 409
        state = snapshot(active)
        assert state["draft_integrity"]["status"] == "invalid"
        assert state["preparation"]["checks"]["draft"]["status"] == "invalid"
        status, _ = post(
            active,
            "review-draft",
            {
                "task_id": task["id"],
                "task_revision": task["revision"],
                "draft_id": task["draft_id"],
                "draft_sha256": task["draft_sha256"],
            },
        )
        assert status == 409
        status, _ = post(
            active,
            "authorize-latex-export",
            {
                "task_id": task["id"],
                "task_revision": task["revision"],
                "draft_id": task["draft_id"],
                "draft_sha256": task["draft_sha256"],
            },
        )
        assert status == 409


def test_another_jobs_draft_routes_return_conflict(portal, tmp_path):
    applications = ApplicationStore(portal.applications)
    jobs = [
        applications.create_application(
            {"company": name, "role_title": "Engineer", "job_description": "Build Python services."}
        )
        for name in ("First", "Second")
    ]
    with explanation_portal(portal, tmp_path) as (active, _):
        tasks = []
        for job in jobs:
            tasks.append(import_latex_draft(active, job, tmp_path))
        first, second = tasks
        status, _ = post(
            active,
            "review-draft",
            {
                "task_id": first["id"],
                "task_revision": first["revision"],
                "draft_id": second["draft_id"],
                "draft_sha256": second["draft_sha256"],
            },
        )
        assert status == 409
        status, _ = post(
            active,
            "authorize-latex-export",
            {
                "task_id": first["id"],
                "task_revision": first["revision"],
                "draft_id": second["draft_id"],
                "draft_sha256": second["draft_sha256"],
            },
        )
        assert status == 409
