"""The normal preparation endpoint reuses accepted PDF bytes internally."""

from types import SimpleNamespace

import pytest
from test_application_flow import wait_for
from test_application_match import model_output, model_runner
from test_career_portal_http import _running_portal
from test_career_portal_http import portal as portal
from test_existing_latex import authorize, export, import_existing
from test_existing_latex import existing_latex as existing_latex
from test_preparation_entry import post, snapshot
from test_standalone_prism_review import FakePrism

from career_evidence_graph.application_information import read_information_library
from career_evidence_graph.application_match import analyze_job
from career_evidence_graph.application_prism import PrismClient
from career_evidence_graph.application_resume import career_source_snapshot
from career_evidence_graph.career_portal_data import ApplicationStore, CareerCatalog


def historical_task(flow, task):
    """Seed a persisted pre-JSON task for the retained PDF-reuse Interface."""
    with flow.applications.write_lock():
        saved = flow._load()
        flow._task(saved, task["id"]).pop("material_contract", None)
        flow._save(saved)
    return flow.snapshot(task["id"])["active_task"]


@pytest.fixture
def application(tmp_path):
    root = tmp_path / "applications"
    root.mkdir()
    applications = ApplicationStore(root)
    job = applications.create_application(
        {
            "company": "Synthetic Origin",
            "role_title": "ML Engineer",
            "job_description": "Build reliable Python services and evaluate training experiments.",
        }
    )
    return applications, job


def test_normal_resume_entry_serves_original_accepted_pdf_without_extra_confirmation(
    existing_latex, portal, tmp_path, monkeypatch
):
    previous, store, job, project = existing_latex
    contributions = portal.career / "contributions"
    contributions.mkdir()
    (contributions / "python.md").write_text(
        "# Synthetic Python service\n\n## Scope\nImplemented a Python service.\n\n"
        "## Responsibility attribution\n| Work | Owner |\n| --- | --- |\n"
        "| Implementation | User |\n\n## Boundaries\nNo GPU training claim.\n"
    )
    store.catalog = CareerCatalog(portal.career)
    canonical = {
        "sources_revision": career_source_snapshot(store.catalog)["revision"],
        "information_library_revision": read_information_library(None)["revision"],
    }
    previous.input_provider = lambda _: {
        "application_revision": job["revision"],
        "inputs": canonical,
    }
    client = FakePrism()
    client.configuration = lambda: PrismClient().configuration()
    store.prism_client = client
    origin = authorize(previous, import_existing(previous, job, project))
    export(previous, origin)
    origin = wait_for(previous, origin["id"], lambda row: row["status"] == "resume_ready")
    previous.callbacks["verify_materials"] = lambda task: store.read_export(task["resume_id"])
    origin = previous.request(
        "record-retained-material-acceptance",
        {
            "task_id": origin["id"],
            "task_revision": origin["revision"],
            "resume_id": origin["resume_id"],
            "resume_sha256": origin["resume_sha256"],
            "source_sha256": origin["prism"]["files"][origin["prism"]["main"]],
            "approval_record": {
                "sha256": "c" * 64,
                "accepted_at": "2026-10-19T12:30:00Z",
                "statement": "Synthetic user accepted this exact PDF content and layout.",
            },
        },
    )
    original_pdf = store.pdf(origin["resume_id"])
    previous.close()
    model_calls = []
    outputs = iter(
        [
            {
                "profiles": [
                    {
                        "id": origin["id"],
                        "content": "Python services and training experiments",
                        "core_work_confirmed": True,
                        "locators": ["Build reliable Python services"],
                    }
                ],
                "task_ids": [origin["id"]],
            },
            {
                "approved": True,
                "source_task_id": origin["id"],
                "reason": "Accepted PDF sufficiently covers current JD and facts.",
            },
        ]
    )

    def semantic_runner(*_args, **_kwargs):
        model_calls.append("semantic")
        return SimpleNamespace(structured_result=next(outputs))

    store.model_runner = semantic_runner
    monkeypatch.setattr(
        store,
        "generate_for_task",
        lambda *_args, **_kwargs: pytest.fail("Reuse hit must bypass normal generation"),
    )

    def analyzer(application, sources, directory):
        return analyze_job(
            application, sources, directory, runner=model_runner(model_output(sources), [])
        )

    target = previous.applications.create_application(
        {
            "company": "Synthetic Target",
            "role_title": "Research Engineer",
            "job_description": (
                "Build Python services and evaluate reliable machine learning experiments."
            ),
        }
    )
    with _running_portal(
        previous.applications.root,
        portal.career,
        flow_root=previous.root,
        flow_resume_factory=lambda *_: store,
        flow_analyzer=analyzer,
        preparation_only=True,
    ) as active:
        status, task = post(
            active,
            "create",
            {"application_id": target["id"], "application_revision": target["revision"]},
        )
        assert status == 200, task
        service = active.server.application_flow_service
        task = historical_task(service, task)
        status, response = post(
            active,
            "start",
            {"task_id": task["id"], "task_revision": task["revision"], "stage": "analysis"},
        )
        assert status == 200, response
        task = wait_for(service, task["id"], lambda row: row["status"] == "analysis_ready")
        status, response = post(
            active,
            "start",
            {"task_id": task["id"], "task_revision": task["revision"], "stage": "resume"},
        )
        assert status == 200, response
        task = wait_for(
            service, task["id"], lambda row: row["status"] in {"materials_ready", "failed"}
        )
        assert task["status"] == "materials_ready", task
        assert task["materials_confirmed"] is True
        assert not task.get("material_reviews")
        assert not task.get("material_acceptance")
        state = snapshot(active)
        assert state["pdf_integrity"]["status"] == "valid", state["pdf_integrity"]
        status, _headers, raw = active.request("GET", f"/api/flow/resumes/{task['resume_id']}/pdf")
        assert status == 200, response
        assert raw == original_pdf
        assert model_calls == ["semantic", "semantic"]
        assert store.pdf(origin["resume_id"]) == original_pdf
        measurements = store.measurements.reuse_summary()
        assert len(measurements["preparations"]) == 1
        observation = measurements["preparations"][0]
        assert observation["clock_complete"] is True
        assert observation["inherited"] is True
        assert observation["total_ms"] >= 0
        assert measurements["confirmation_requests"] == 0
        assert measurements["repeat_confirmation_requests"] == 0
    with _running_portal(
        previous.applications.root,
        portal.career,
        flow_root=previous.root,
        flow_resume_factory=lambda *_: store,
        flow_analyzer=analyzer,
        preparation_only=True,
    ) as reopened:
        state = snapshot(reopened)
        assert state["active_task"]["id"] == task["id"]
        assert state["active_task"]["materials_confirmed"] is True
        assert state["pdf_integrity"]["status"] == "valid"
        status, _headers, raw = reopened.request(
            "GET", f"/api/flow/resumes/{task['resume_id']}/pdf"
        )
        assert status == 200 and raw == original_pdf
        assert model_calls == ["semantic", "semantic"]


def test_no_accepted_history_uses_existing_generation_without_semantic_lookup(
    portal, tmp_path, monkeypatch
):
    from test_full_latex_http import bind_generate, generated_portal

    with generated_portal(portal, tmp_path, monkeypatch) as (active, task, project, calls, work):
        task = historical_task(active.server.application_flow_service, task)
        store = active.server.application_resume_store
        generated = bind_generate(active, task, project)
        assert generated["status"] == "draft_ready"
        assert generated["materials_confirmed"] is False
        assert not generated.get("pdf_reuse")
        assert len(calls) == 1
        assert not (store.root / ".pdf-reuse-index").exists()
        assert not work["exports"]
        observations = store.measurements.reuse_summary()
        assert observations["preparations"] == []
        assert observations["confirmation_requests"] == 0
        assert observations["repeat_confirmation_requests"] == 0
