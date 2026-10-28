"""Loopback LaTeX export binds technical authorization, receipts and exact PDF bytes."""

import json
from pathlib import Path

import pytest
from test_application_flow import wait_for
from test_career_portal_http import portal as portal
from test_job_explanation_browser import explanation_portal
from test_preparation_entry import post, snapshot

from career_evidence_graph.career_portal_data import ApplicationStore


@pytest.fixture(autouse=True)
def isolated_connection(tmp_path, monkeypatch):
    monkeypatch.setenv("CODEX_HOME", str(tmp_path / "synthetic-codex"))
    monkeypatch.delenv("CODEX_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)


class SyntheticLatexClient:
    """Compile-boundary fake; source capture and HTTP adoption remain real."""

    def __init__(self, on_compile=lambda: None):
        self.revision = 1
        self.on_compile = on_compile

    def configuration(self):
        return {"renderer": "synthetic-latex", "revision": self.revision}

    def compile(self, binding):
        self.on_compile()
        return {
            "build": {"main": binding["main"], "exit": 0, "pdf_updated": True},
            "pdf": (
                Path(__file__).parent / "fixtures/pdf-export/current-template.pdf"
            ).read_bytes(),
        }


def create_authorized_latex(active, job):
    store = active.server.application_resume_store
    if store.prism_client is None:
        store.prism_client = SyntheticLatexClient()
    project = store.root.parent / ("latex-" + job["id"])
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
    status, task = post(active, "authorize-latex-export", export_payload(task))
    assert status == 200, task
    assert task["origin"] == "existing_latex" and task["draft_review"] is None
    return task


def export_payload(task, **extra):
    return {
        "task_id": task["id"],
        "task_revision": task["revision"],
        "draft_id": task["draft_id"],
        "draft_sha256": task["draft_sha256"],
        **extra,
    }


@pytest.mark.parametrize("damage", ["pdf_bytes", "manifest_bytes"])
def test_export_routes_require_authorization_and_preview_only_adopted_bytes(
    portal, tmp_path, damage
):
    job = ApplicationStore(portal.applications).create_application(
        {
            "company": "Synthetic",
            "role_title": "Engineer",
            "job_description": "Build Python services.",
        }
    )
    with explanation_portal(portal, tmp_path) as (active, _):
        active.server.application_resume_store.prism_client = SyntheticLatexClient()
        task = create_authorized_latex(active, job)
        payload = export_payload(task)
        assert (
            active.request("POST", "/api/flow/export-pdf", body=json.dumps(payload).encode())[0]
            == 403
        )
        assert post(active, "export-pdf", payload | {"draft_sha256": "f" * 64})[0] == 409
        assert post(active, "export-pdf", payload)[0] == 200
        service = active.server.application_flow_service
        task = wait_for(service, task["id"], lambda row: row["status"] == "resume_ready")
        identifier = task["resume_id"]
        assert active.request("GET", f"/api/flow/resumes/{identifier}/pdf")[0] == 200
        assert active.request("GET", f"/api/flow/resumes/{task['draft_id']}/pdf")[0] != 200
        assert snapshot(active)["pdf_integrity"]["status"] == "valid"
        path = active.server.application_resume_store.root / identifier / "resume.pdf"
        original = path.read_bytes()
        if damage == "pdf_bytes":
            path.write_bytes(original + b"corrupted")
        else:
            manifest = path.parent / "export.json"
            manifest.write_text(json.dumps(json.loads(manifest.read_text()), indent=3))
        assert active.request("GET", f"/api/flow/resumes/{identifier}/pdf")[0] == 409
        assert snapshot(active)["pdf_integrity"]["status"] == "invalid"
        assert snapshot(active)["draft_integrity"]["status"] == "valid"
        assert snapshot(active)["preparation"]["checks"]["draft"]["status"] == "available"
        assert (
            post(
                active,
                "confirm-materials",
                {
                    "task_id": task["id"],
                    "task_revision": task["revision"],
                    "resume_id": identifier,
                    "resume_sha256": task["resume_sha256"],
                },
            )[0]
            == 409
        )


def test_renderer_change_can_only_reexport_without_regenerating_draft(portal, tmp_path):
    job = ApplicationStore(portal.applications).create_application(
        {
            "company": "Synthetic",
            "role_title": "Engineer",
            "job_description": "Build Python services.",
        }
    )
    with explanation_portal(portal, tmp_path) as (active, work):
        store = active.server.application_resume_store
        store.prism_client = SyntheticLatexClient()
        task = create_authorized_latex(active, job)
        calls = list(work["calls"])
        post(active, "export-pdf", export_payload(task))
        service = active.server.application_flow_service
        task = wait_for(service, task["id"], lambda row: row["status"] == "resume_ready")
        old_id, draft_id, review = task["resume_id"], task["draft_id"], task["draft_review"]
        old = (store.root / old_id / "resume.pdf").read_bytes()
        store.prism_client.revision += 1
        state = snapshot(active)
        assert state["draft_integrity"]["status"] == "valid"
        assert state["pdf_integrity"]["status"] == "invalid"
        assert (
            post(
                active,
                "confirm-materials",
                {
                    "task_id": task["id"],
                    "task_revision": task["revision"],
                    "resume_id": old_id,
                    "resume_sha256": task["resume_sha256"],
                },
            )[0]
            == 409
        )
        assert post(active, "export-pdf", export_payload(task, retry=True))[0] == 200
        task = wait_for(service, task["id"], lambda row: row["status"] == "resume_ready")
        assert task["resume_id"] != old_id
        assert task["draft_id"] == draft_id and task["draft_review"] == review
        assert (store.root / old_id / "resume.pdf").read_bytes() == old
        assert active.request("GET", f"/api/flow/resumes/{old_id}/pdf")[0] == 200
        assert work["calls"] == calls


def test_orphan_export_and_other_jobs_draft_cannot_be_previewed_or_adopted(portal, tmp_path):
    apps = ApplicationStore(portal.applications)
    jobs = [
        apps.create_application(
            {
                "company": company,
                "role_title": "Engineer",
                "job_description": "Build Python services.",
            }
        )
        for company in ("Synthetic A", "Synthetic B")
    ]
    with explanation_portal(portal, tmp_path) as (active, _):
        store = active.server.application_resume_store
        store.prism_client = SyntheticLatexClient()
        first = create_authorized_latex(active, jobs[0])
        second = create_authorized_latex(active, jobs[1])
        assert (
            post(
                active,
                "export-pdf",
                export_payload(second)
                | {
                    "draft_id": first["draft_id"],
                    "draft_sha256": first["draft_sha256"],
                },
            )[0]
            == 409
        )
        orphan = store.export_for_draft(
            first["draft_id"],
            first["draft_sha256"],
            task_inputs=first["inputs"],
            export_id="e" * 32,
            prism=first["prism"],
        )
        assert active.request("GET", f"/api/flow/resumes/{orphan['id']}/pdf")[0] == 404
        assert (
            post(
                active,
                "confirm-materials",
                {
                    "task_id": second["id"],
                    "task_revision": second["revision"],
                    "resume_id": orphan["id"],
                    "resume_sha256": orphan["pdf_sha256"],
                },
            )[0]
            == 409
        )


def test_unknown_manifest_publication_is_reconciled_without_a_second_export(
    portal,
    tmp_path,
    monkeypatch,
):
    from career_evidence_graph.application_resume import helper

    job = ApplicationStore(portal.applications).create_application(
        {
            "company": "Synthetic",
            "role_title": "Engineer",
            "job_description": "Build Python services.",
        }
    )
    with explanation_portal(portal, tmp_path) as (active, work):
        store = active.server.application_resume_store
        exports = []

        store.prism_client = SyntheticLatexClient(on_compile=lambda: exports.append("compile"))
        task = create_authorized_latex(active, job)
        calls = list(work["calls"])
        original = helper.atomic_write_json

        def lost_receipt(path, value):
            original(path, value)
            if path.name == "export.json":
                raise OSError("Synthetic unknown manifest publication")

        monkeypatch.setattr(helper, "atomic_write_json", lost_receipt)
        assert post(active, "export-pdf", export_payload(task))[0] == 200
        service = active.server.application_flow_service
        task = wait_for(service, task["id"], lambda row: row["status"] == "needs_recheck")
        candidate = task["stages"]["export"]["attempt_id"]
        assert active.request("GET", f"/api/flow/resumes/{candidate}/pdf")[0] == 404
        assert post(active, "export-pdf", export_payload(task, retry=True))[0] == 409
        status, task = post(
            active,
            "recheck-export",
            {
                "task_id": task["id"],
                "task_revision": task["revision"],
            },
        )
        assert status == 200 and task["status"] == "resume_ready"
        assert task["resume_id"] == candidate
        assert len(exports) == 1 and work["calls"] == calls
        assert active.request("GET", f"/api/flow/resumes/{candidate}/pdf")[0] == 200
