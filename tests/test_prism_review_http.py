"""Preparation adopts the PDF built from the explicitly bound local LaTeX source."""

from test_application_flow import wait_for
from test_application_prism import compiling_editor
from test_career_portal_http import portal as portal
from test_job_explanation_browser import explanation_portal
from test_pdf_export_http import export_payload
from test_preparation_entry import post, snapshot

from career_evidence_graph.career_portal_data import ApplicationStore


def test_bound_latex_source_reaches_technical_export_without_factual_confirmation(
    portal, tmp_path, monkeypatch
):
    project = tmp_path / "latex"
    project.mkdir()
    main = project / "main.tex"
    main.write_text(r"\documentclass{article}\begin{document}Synthetic\end{document}")
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
        assert task["draft_review"] is None
        assert snapshot(active)["prism"]["status"] == "current"
        status, task = post(
            active, "open-prism", {"task_id": task["id"], "task_revision": task["revision"]}
        )
        assert status == 200 and task["prism"]["editor_url"].startswith("http://127.0.0.1:")
        status, task = post(active, "authorize-latex-export", export_payload(task))
        assert status == 200, task
        assert post(active, "export-pdf", export_payload(task))[0] == 200
        task = wait_for(
            active.server.application_flow_service,
            task["id"],
            lambda row: row["status"] in {"resume_ready", "export_failed", "needs_recheck"},
        )
        assert task["status"] == "resume_ready", task
        assert task["materials_confirmed"] is False
        assert task["draft_review"] is None
        assert task["export_authorization"]["scope"] == "technical_export"
        assert active.request("GET", f"/api/flow/resumes/{task['resume_id']}/pdf")[0] == 200
        assert not work["exports"]
        assert len([request for request in requests if request[0] == "POST"]) == 1
        main.write_text("Synthetic user edit after preview")
        state = snapshot(active)
        assert state["prism"]["status"] == "changed"
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
