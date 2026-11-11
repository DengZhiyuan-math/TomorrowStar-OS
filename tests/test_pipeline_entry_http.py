"""The default queue owns admission without disabling retained task reads."""

import json
from copy import deepcopy
from threading import Event, Thread

import pytest
from test_application_intake import message, page, ready
from test_application_resume import task_resume as task_resume
from test_automatic_material_editor_browser import serving
from test_automatic_material_reuse_edit import complete_portal as complete_portal
from test_career_portal_http import Portal, _running_portal
from test_career_portal_http import portal as portal
from test_full_latex_generation import full_latex as full_latex

from career_evidence_graph.application_intake import ApplicationIntakeService
from career_evidence_graph.career_portal_data import ApplicationStore


def post(active, path, payload):
    status, _, raw = active.request(
        "POST", path, body=json.dumps(payload).encode(), headers=active.write_headers()
    )
    return status, json.loads(raw)


def test_admitted_job_prevents_another_direct_flow_without_starting_work(portal, tmp_path):
    applications = ApplicationStore(portal.applications)
    first, second = [
        applications.create_application(
            {
                "company": f"Synthetic Employer {index}",
                "role_title": "Service Engineer",
                "url": f"https://example.invalid/jobs/{index}",
                "location": "Zurich, Switzerland",
                "job_description": "Build reliable Python services.",
            }
        )
        for index in (1, 2)
    ]
    with _running_portal(
        portal.applications,
        portal.career,
        flow_root=tmp_path / "entry-flow",
        worker_root=tmp_path / "entry-worker",
    ) as active:
        status, admitted = post(
            active,
            "/api/pipeline/admit",
            {
                "request_id": "explicit-first-job",
                "application_id": first["id"],
                "application_revision": first["revision"],
            },
        )
        assert status == 200, admitted
        assert admitted["control"] == "paused" and admitted["active_task_id"] is None
        flow = active.server.application_flow_service
        before = flow.snapshot()
        assert before["tasks"] == []
        status, rejected = post(
            active,
            "/api/flow/create",
            {"application_id": second["id"], "application_revision": second["revision"]},
        )
        assert status == 409 and rejected["error"] == "pipeline_entry_required", rejected
        assert flow.snapshot() == before
        assert active.server.application_pipeline_service.snapshot() == admitted
        assert active.request("GET", "/api/flow/state")[0] == 200
        assert active.request("GET", f"/api/applications/{second['id']}")[0] == 200


@pytest.mark.parametrize(
    "action,details",
    [
        ("start", {"stage": "analysis"}),
        ("prepare-worker", {"country": "CHE", "send_confirmed": True}),
        ("cancel", {}),
        ("worker-action", {"operation": "resume", "payload": {"controller": "legacy"}}),
        ("worker-action", {"operation": "recheck", "payload": {"controller": "legacy"}}),
    ],
)
def test_queued_job_uses_pipeline_for_execution_but_keeps_legacy_task_updates(
    portal, tmp_path, action, details
):
    application = ApplicationStore(portal.applications).create_application(
        {
            "company": "Retained Synthetic Employer",
            "role_title": "Service Engineer",
            "url": "https://example.invalid/jobs/retained",
            "job_description": "Build reliable Python services.",
        }
    )
    with _running_portal(
        portal.applications,
        portal.career,
        flow_root=tmp_path / "retained-flow",
        worker_root=tmp_path / "retained-worker",
        flow_analyzer=lambda *_: pytest.fail("A legacy endpoint must not launch analysis"),
    ) as active:
        status, task = post(
            active,
            "/api/flow/create",
            {
                "application_id": application["id"],
                "application_revision": application["revision"],
            },
        )
        assert status == 200, task
        status, admitted = post(
            active,
            "/api/pipeline/admit",
            {
                "request_id": "retain-existing-task",
                "application_id": application["id"],
                "application_revision": application["revision"],
            },
        )
        assert status == 200, admitted
        payload = {"task_id": task["id"], "task_revision": task["revision"]}
        status, rejected = post(active, f"/api/flow/{action}", payload | details)
        assert status == 409 and rejected["error"] == "pipeline_entry_required", rejected
        status, unchanged = post(
            active,
            "/api/flow/update-inputs",
            payload | {"application_revision": application["revision"]},
        )
        assert status == 200 and unchanged == task
        assert active.request("GET", f"/api/flow/{task['id']}")[0] == 200
        status, paused = post(active, "/api/pipeline/pause", {})
        assert status == 200 and paused["control"] == "paused"
        assert active.server.application_flow_service.snapshot(task["id"])["active_task"] == task


@pytest.mark.parametrize("action", ["select", "acquire", "refresh", "continue"])
def test_admitted_recommendation_cannot_start_an_independent_intake(portal, tmp_path, action):
    reads, fetches = [], []

    def reader(*_, **__):
        reads.append("capture")
        return {"status": "readable", "emails": [message()], "provenance": {}}

    def fetch(url):
        fetches.append(url)
        return page(url)

    def factory(applications, root):
        return ApplicationIntakeService(applications, root, reader=reader, fetcher=fetch)

    with _running_portal(
        portal.applications,
        portal.career,
        flow_root=tmp_path / "recommendation-flow",
        worker_root=tmp_path / "recommendation-worker",
        flow_intake_factory=factory,
    ) as active:
        status, captured = post(active, "/api/recommendations/refresh", {"capture_only": True})
        assert status == 200, captured
        intake = active.server.application_intake_service
        original = ready(intake)
        recommendation = original["recommendations"][0]
        status, admitted = post(
            active,
            "/api/pipeline/admit",
            {
                "request_id": "retain-recommendation",
                "recommendation_id": recommendation["id"],
                "recommendation_revision": recommendation["revision"],
            },
        )
        assert status == 200, admitted
        payload = (
            {"id": recommendation["id"], "revision": recommendation["revision"]}
            if action in {"select", "acquire"}
            else {"revision": original["revision"]}
            if action == "continue"
            else {"capture_only": True}
        )
        status, rejected = post(active, f"/api/recommendations/{action}", payload)
        assert status == 409 and rejected["error"] == "pipeline_entry_required", rejected
        assert intake.snapshot() == original
        assert active.server.application_pipeline_service.snapshot() == admitted
        assert reads == ["capture"] and fetches == []
        assert active.server.application_flow_service.snapshot()["tasks"] == []
        assert ApplicationStore(portal.applications).list_applications() == []


def test_legacy_pdf_export_cannot_start_a_stage_after_pipeline_admission(complete_portal):
    server, store, original, generation = complete_portal
    flow, pipeline = server.application_flow_service, server.application_pipeline_service
    edited = flow.begin_automatic_edit(original["id"], original["revision"])
    application = store.applications.get_application(original["application_id"])
    admitted = pipeline.admit(
        {
            "request_id": "retain-pdf-stage-owner",
            "application_id": application["id"],
            "application_revision": application["revision"],
        }
    )
    before = deepcopy(flow.snapshot()["tasks"])
    old_pdf = store.pdf(original["resume_id"])
    compiles = len(store.prism_client.calls)
    with serving(server):
        active = Portal(server, store.applications.root, store.catalog.root)
        status, rejected = post(
            active,
            "/api/flow/export-pdf",
            {
                "task_id": edited["id"],
                "task_revision": edited["revision"],
                "draft_id": edited["draft_id"],
                "draft_sha256": edited["draft_sha256"],
            },
        )
        assert status == 409 and rejected["error"] == "pipeline_entry_required", rejected
        assert flow.snapshot()["tasks"] == before
        assert pipeline.snapshot() == admitted
        assert store.pdf(original["resume_id"]) == old_pdf
        assert len(generation) == 1 and len(store.prism_client.calls) == compiles


def test_queued_legacy_entry_rechecks_a_later_admission_before_creating_flow(
    portal, tmp_path, monkeypatch
):
    application = ApplicationStore(portal.applications).create_application(
        {
            "company": "Late Admission Synthetic Employer",
            "role_title": "Service Engineer",
            "url": "https://example.invalid/jobs/late-admission",
            "job_description": "Build reliable Python services.",
        }
    )
    with _running_portal(
        portal.applications,
        portal.career,
        flow_root=tmp_path / "late-flow",
        worker_root=tmp_path / "late-worker",
    ) as active:
        flow = active.server.application_flow_service
        entered, release = Event(), Event()
        original = flow.request

        def delayed(action, payload):
            if action == "create":
                entered.set()
                assert release.wait(3)
            return original(action, payload)

        monkeypatch.setattr(flow, "request", delayed)
        headers = active.write_headers()
        results = []
        request = Thread(
            target=lambda: results.append(
                active.request(
                    "POST",
                    "/api/flow/create",
                    body=json.dumps(
                        {
                            "application_id": application["id"],
                            "application_revision": application["revision"],
                        }
                    ).encode(),
                    headers=headers,
                )
            ),
            daemon=True,
        )
        try:
            request.start()
            assert entered.wait(3)
            status, admitted = post(
                active,
                "/api/pipeline/admit",
                {
                    "request_id": "admission-wins-before-flow",
                    "application_id": application["id"],
                    "application_revision": application["revision"],
                },
            )
            assert status == 200, admitted
            release.set()
            request.join(3)
            assert not request.is_alive()
            assert results[0][0] == 409
            assert json.loads(results[0][2])["error"] == "pipeline_entry_required"
            assert flow.snapshot()["tasks"] == []
            assert active.server.application_pipeline_service.snapshot() == admitted
        finally:
            release.set()
            request.join(3)
