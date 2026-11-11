"""Preparation batches use loopback authorization and existing source receipts."""

import json
import time
from types import SimpleNamespace

import pytest
from test_application_flow import wait_for
from test_application_intake import message, page, ready
from test_career_portal_http import portal as portal
from test_job_explanation_browser import explanation_portal
from test_pdf_export_http import SyntheticLatexClient, export_payload
from test_preparation_entry import post, snapshot

from career_evidence_graph.career_portal_data import ApplicationStore, PortalDataError


def wait_batch(active, predicate):
    deadline = time.monotonic() + 4
    while time.monotonic() < deadline:
        state = snapshot(active)
        if predicate(state):
            return state
        time.sleep(0.01)
    pytest.fail("Synthetic material batch did not reach the expected state")


def control(active, batch, operation):
    return post(
        active,
        "batch-control",
        {
            "batch_id": batch["id"],
            "batch_revision": batch["revision"],
            "operation": operation,
        },
    )


def refresh_synthetic(active):
    service = active.server.application_intake_service
    reads, captures = [], []

    def reader(directory, **options):
        reads.append(options)
        return {"status": "readable", "emails": [message()], "provenance": {"source": "synthetic"}}

    def fetcher(url):
        captures.append(url)
        return page(url)

    service.reader, service.fetcher = reader, fetcher
    status, _, raw = active.request(
        "POST", "/api/recommendations/refresh", body=b"{}", headers=active.write_headers()
    )
    assert status == 200, raw
    state = ready(service)
    assert state["status"] == "complete"
    return state["recommendations"][0], reads, captures


@pytest.fixture(autouse=True)
def synthetic_context(tmp_path, monkeypatch):
    monkeypatch.setenv("CODEX_HOME", str(tmp_path / "synthetic-codex"))
    monkeypatch.delenv("CODEX_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)


def test_saving_explicit_batch_is_authorized_versioned_and_does_no_work(portal, tmp_path):
    applications = ApplicationStore(portal.applications)
    jobs = [
        applications.create_application(
            {
                "company": company,
                "role_title": "Engineer",
                "job_description": "Build Python services.",
            }
        )
        for company in ("Synthetic A", "Synthetic B")
    ]
    with explanation_portal(portal, tmp_path) as (active, work):
        payload = {
            "request_id": "a" * 32,
            "items": [
                {"kind": "application", "id": job["id"], "revision": job["revision"]}
                for job in jobs
            ],
        }
        assert (
            active.request("POST", "/api/flow/batch-create", body=json.dumps(payload).encode())[0]
            == 403
        )
        status, batch = post(active, "batch-create", payload)
        assert status == 200 and batch["control"] == "paused"
        assert len(batch["items"]) == 2
        assert post(active, "batch-create", payload) == (200, batch)
        assert post(active, "batch-create", payload | {"request_id": "b" * 32})[0] == 409
        saved = snapshot(active)
        assert saved["preparation_batch"]["id"] == batch["id"]
        assert saved["tasks"] == [] and work["calls"] == [] and work["exports"] == []
        assert active.server.worker_service is None


def test_mail_source_selection_requires_latex_without_html_fallback(portal, tmp_path):
    with explanation_portal(portal, tmp_path) as (active, work):
        row, reads, captures = refresh_synthetic(active)
        saved_jobs = ApplicationStore(portal.applications).list_applications()
        assert len(reads) == len(captures) == len(saved_jobs) == 1
        assert row["selection_status"] == "saved"
        assert saved_jobs[0]["id"] == row["existing_application"]["id"]
        assert saved_jobs[0]["job_description"] == row["job_description"]
        assert snapshot(active)["tasks"] == []
        assert work["calls"] == work["exports"] == []
        status, batch = post(
            active,
            "batch-create",
            {
                "request_id": "b" * 32,
                "items": [{"kind": "recommendation", "id": row["id"], "revision": row["revision"]}],
            },
        )
        assert status == 200 and batch["control"] == "paused"
        assert control(active, batch, "resume")[0] == 200
        state = wait_batch(
            active,
            lambda s: (
                (s.get("active_task") or {}).get("stages", {}).get("resume", {}).get("status")
                == "failed"
            ),
        )
        task = state["active_task"]
        assert task["material_contract"] == "content-writing/v1"
        assert task["stages"]["resume"]["error_code"] == "resume_content_material_required"
        assert not task.get("resume_id") and not task.get("draft_id")
        assert not work["exports"]
        assert len(reads) == len(captures) == len(state["tasks"]) == 1
        assert sum("exec" in call for call in work["calls"]) == 1
        assert active.server.worker_service is None
        current_jobs = ApplicationStore(portal.applications).list_applications()
        assert len(current_jobs) == 1 and current_jobs[0]["id"] == saved_jobs[0]["id"]
        assert current_jobs[0]["job_description"] == row["job_description"]


def test_existing_job_with_different_captured_jd_is_deferred_without_overwrite_or_model(
    portal,
    tmp_path,
):
    with explanation_portal(portal, tmp_path) as (active, work):
        row, _, _ = refresh_synthetic(active)
        applications = ApplicationStore(portal.applications)
        saved = applications.get_application(row["existing_application"]["id"])
        existing = applications.update_application(
            saved["id"],
            {"job_description": "A distinct previously saved JD that needs reconciliation."},
            saved["revision"],
        )
        _, batch = post(
            active,
            "batch-create",
            {
                "request_id": "c" * 32,
                "items": [{"kind": "recommendation", "id": row["id"], "revision": row["revision"]}],
            },
        )
        assert control(active, batch, "resume")[0] == 200
        state = wait_batch(
            active, lambda s: s["preparation_batch"]["items"][0]["status"] == "deferred"
        )
        item = state["preparation_batch"]["items"][0]
        assert item["reason"] == "recommendation_source_conflict"
        assert applications.get_application(existing["id"]) == existing
        assert len(applications.list_applications()) == 1
        assert (
            active.server.application_intake_service.snapshot()["recommendations"][0][
                "selection_status"
            ]
            == "source_conflict"
        )
        assert active.server.worker_service is None
        assert state["tasks"] == [] and work["calls"] == work["exports"] == []


def test_unknown_export_cannot_be_skipped_and_remains_reconcilable_after_jd_changes(
    portal,
    tmp_path,
):
    applications = ApplicationStore(portal.applications)
    job = applications.create_application(
        {
            "company": "Synthetic",
            "role_title": "Engineer",
            "job_description": "Build Python services.",
        }
    )
    with explanation_portal(portal, tmp_path) as (active, _):
        store = active.server.application_resume_store
        exports = []

        store.prism_client = SyntheticLatexClient(on_compile=lambda: exports.append("compile"))
        project = tmp_path / "batch-latex"
        project.mkdir()
        (project / "main.tex").write_text(
            "\\documentclass{article}\n\\begin{document}\nSynthetic Person\n"
            "\\section*{Experience}\nImplemented a Python service.\n\\end{document}\n"
        )

        def generate_model(config, prompt, **kwargs):
            payload = json.loads(prompt[prompt.index("{") :])
            identity = next(s for s in payload["sources"] if s.get("source_kind") == "identity")
            work_source = next(
                s
                for s in payload["sources"]
                if s["source_id"] in payload["analysis_selected_source_ids"]
            )
            return SimpleNamespace(
                structured_result={
                    "groups": [
                        {
                            "title": "Identity",
                            "start_line": 1,
                            "end_line": 1,
                            "source_ids": [identity["source_id"]],
                            "latex": "Synthetic Person\n",
                            "disposition": "include",
                            "reason": "Preserve fixed identity",
                        },
                        {
                            "title": "Experience",
                            "start_line": 2,
                            "end_line": 3,
                            "source_ids": [work_source["source_id"]],
                            "latex": "\\section*{Experience}\nImplemented a Python service.\n",
                            "disposition": "include",
                            "reason": "Preserve documented service work",
                        },
                    ],
                    "limitations": [],
                },
                model_dump=lambda **kwargs: {"synthetic": True},
            )

        store.model_runner = generate_model
        service = active.server.application_flow_service
        task = service.create(job["id"], job["revision"])
        # Resume an existing full-TeX task to test historical export recovery.
        with service.applications.write_lock():
            state = service._load()
            service._task(state, task["id"]).pop("material_contract", None)
            service._save(state)
        task = service.snapshot(task["id"])["active_task"]
        service.start(task["id"], task["revision"], "analysis")
        task = wait_for(service, task["id"], lambda row: row["status"] == "analysis_ready")
        task = service.prepare_automatic_materials(
            task["id"], task["revision"], str(project), "main.tex"
        )
        service.start(task["id"], task["revision"], "resume")
        task = wait_for(service, task["id"], lambda row: row["status"] in {"draft_ready", "failed"})
        assert task["status"] == "draft_ready", task
        assert task["origin"] == "generated_latex"
        assert not list(store.root.rglob("*.html"))
        original = store.export_for_draft

        def unknown(*args, **kwargs):
            original(*args, **kwargs)
            raise PortalDataError("resume_export_needs_recheck", "Synthetic lost publication", 409)

        store.export_for_draft = unknown
        _, batch = post(
            active,
            "batch-create",
            {
                "request_id": "d" * 32,
                "items": [
                    {"kind": "application", "id": job["id"], "revision": job["revision"]},
                ],
            },
        )
        assert control(active, batch, "resume")[0] == 200
        state = wait_batch(active, lambda s: s["preparation_batch"]["active_task_id"] == task["id"])
        task = state["active_task"]
        assert post(active, "export-pdf", export_payload(task))[0] == 200
        state = wait_batch(active, lambda s: s["active_task"]["status"] == "needs_recheck")
        task = state["active_task"]
        for action, extra in (
            ("cancel", {}),
            ("update-inputs", {"application_revision": job["revision"]}),
            (
                "clarify-condition",
                {"requirement_index": 0, "eligible": True, "source": "Synthetic"},
            ),
        ):
            status, result = post(
                active,
                action,
                {
                    "task_id": task["id"],
                    "task_revision": task["revision"],
                    **extra,
                },
            )
            assert status == 409 and result["error"] == "flow_batch_recheck_required"
        assert (
            post(
                active,
                "create",
                {"application_id": job["id"], "application_revision": job["revision"]},
            )[0]
            == 409
        )
        applications.update_application(
            job["id"], {"job_description": "An updated Python JD."}, job["revision"]
        )
        status, result = post(
            active,
            "recheck-export",
            {
                "task_id": task["id"],
                "task_revision": task["revision"],
            },
        )
        assert status == 200, result
        assert result["status"] == "stale" and result["resume_id"] is None
        assert result["export_recheck"]["status"] == "failed"
        assert len(exports) == 1
