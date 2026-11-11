"""Existing LaTeX has a job-bound technical export without factual approval."""

import json

from test_application_flow import wait_for
from test_application_prism import compiling_editor
from test_career_portal_http import portal as portal
from test_job_explanation_browser import explanation_portal
from test_pdf_export_http import export_payload
from test_preparation_entry import post, snapshot

from career_evidence_graph.career_portal_data import ApplicationStore


def test_existing_latex_is_exported_and_read_without_model_or_factual_review(
    portal, tmp_path, monkeypatch
):
    project = tmp_path / "latex"
    project.mkdir()
    (project / "main.tex").write_text(
        r"\documentclass{article}\begin{document}Synthetic existing CV\end{document}"
    )
    job = ApplicationStore(portal.applications).create_application(
        {
            "company": "Synthetic",
            "role_title": "Engineer",
            "job_description": "Build Python services.",
        }
    )
    with (
        compiling_editor(project, monkeypatch) as requests,
        explanation_portal(portal, tmp_path) as (active, work),
    ):
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
        assert task["draft_review"] is None and task["analysis_id"] is None
        assert task["factual_review"] == "pending"
        assert post(active, "export-pdf", export_payload(task))[0] == 409
        status, task = post(active, "authorize-latex-export", export_payload(task))
        assert status == 200, task
        assert task["export_authorization"]["scope"] == "technical_export"
        assert post(active, "export-pdf", export_payload(task))[0] == 200
        task = wait_for(
            active.server.application_flow_service,
            task["id"],
            lambda row: row["status"] in {"resume_ready", "export_failed", "needs_recheck"},
        )
        assert task["status"] == "resume_ready", task
        state = snapshot(active)
        assert state["draft_integrity"]["status"] == "valid"
        assert state["pdf_integrity"]["status"] == "valid"
        assert state["active_task"]["draft_review"] is None
        status, _, raw = active.request("GET", "/api/flow/drafts/" + task["draft_id"])
        assert status == 200, raw
        assert json.loads(raw)["origin"] == "existing_latex"
        status, _, raw = active.request("GET", f"/api/flow/exports/{task['resume_id']}")
        assert status == 200, raw
        receipt = json.loads(raw)
        assert receipt["origin"] == "existing_latex"
        assert receipt["factual_review"] == "pending"
        assert receipt["prism_source_revision"] == task["prism"]["source_revision"]
        assert "file_base64" not in receipt
        assert active.request("GET", f"/api/flow/resumes/{task['resume_id']}/pdf")[0] == 200
        assert not work["calls"] and not work["exports"]
        assert len([request for request in requests if request[0] == "POST"]) == 1
        assert (
            post(
                active,
                "confirm-materials",
                {
                    "task_id": task["id"],
                    "task_revision": task["revision"],
                    "resume_id": task["resume_id"],
                    "resume_sha256": task["resume_sha256"],
                },
            )[0]
            == 409
        )
        assert not snapshot(active)["active_task"]["materials_confirmed"]
