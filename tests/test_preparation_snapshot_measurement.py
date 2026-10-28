"""Preparation GETs project state; committed deliveries own measurement requests."""

from copy import deepcopy
from threading import Event

import pytest
from test_application_flow import wait_for
from test_career_portal_http import portal as portal
from test_full_latex_http import bind_generate, generated_portal
from test_job_explanation_browser import explanation_portal
from test_pdf_export_http import create_authorized_latex, export_payload
from test_preparation_entry import post, snapshot

from career_evidence_graph.application_prism import source_snapshot
from career_evidence_graph.career_portal_data import ApplicationStore
from career_evidence_graph.worker_measurement import MeasurementLog


def existing_job(portal):
    return ApplicationStore(portal.applications).create_application(
        {
            "company": "Synthetic",
            "role_title": "Engineer",
            "job_description": "Build Python services.",
        }
    )


def test_pdf_delivery_records_request_before_get_and_get_never_reads_measurements(
    portal, tmp_path, monkeypatch
):
    job = existing_job(portal)
    with explanation_portal(portal, tmp_path) as (active, _):
        task = create_authorized_latex(active, job)
        assert post(active, "export-pdf", export_payload(task))[0] == 200
        flow = active.server.application_flow_service
        task = wait_for(flow, task["id"], lambda row: row["status"] == "resume_ready")
        log = active.server.application_resume_store.measurements
        events = log.read()
        assert len([e for e in events if e["kind"] == "resume_confirmation_request"]) == 1
        retained = log.path.read_bytes()
        reopened = MeasurementLog(log.root)
        reopened.confirmation_requested(task["id"], task["resume_sha256"])
        assert log.path.read_bytes() == retained

        def unexpected_read():
            pytest.fail("GET must not scan the measurement history")

        monkeypatch.setattr(log, "read", unexpected_read)
        for _ in range(2):
            state = snapshot(active)
            assert state["pdf_integrity"]["status"] == "valid"
            assert state["active_task"]["revision"] == task["revision"]
        assert log.path.read_bytes() == retained


def test_failed_pdf_save_cannot_record_confirmation_request(portal, tmp_path, monkeypatch):
    job = existing_job(portal)
    with explanation_portal(portal, tmp_path) as (active, _):
        task = create_authorized_latex(active, job)
        flow = active.server.application_flow_service
        original = flow._save
        rejected = Event()

        def fail_completed_export(state):
            if any(row.get("resume_id") for row in state["tasks"]):
                rejected.set()
                raise OSError("synthetic checkpoint failure")
            return original(state)

        monkeypatch.setattr(flow, "_save", fail_completed_export)
        assert post(active, "export-pdf", export_payload(task))[0] == 200
        assert rejected.wait(3)
        flow._thread.join(timeout=3)
        assert not flow._thread.is_alive()
        assert not any(
            event["kind"] == "resume_confirmation_request"
            for event in active.server.application_resume_store.measurements.read()
        )


@pytest.mark.parametrize("measurement_error", [OSError, ValueError, TypeError])
def test_pdf_measurement_failure_cannot_stop_saved_delivery(
    portal, tmp_path, monkeypatch, measurement_error
):
    job = existing_job(portal)
    with explanation_portal(portal, tmp_path) as (active, _):
        task = create_authorized_latex(active, job)
        log = active.server.application_resume_store.measurements

        def fail_measurement(*args, **kwargs):
            raise measurement_error("synthetic measurement failure")

        monkeypatch.setattr(log, "confirmation_requested", fail_measurement)
        assert post(active, "export-pdf", export_payload(task))[0] == 200
        flow = active.server.application_flow_service
        task = wait_for(flow, task["id"], lambda row: row["status"] == "resume_ready")
        state = snapshot(active)
        assert state["active_task"]["revision"] == task["revision"]
        assert state["pdf_integrity"]["status"] == "valid"
        assert not state["runtime_error"]
        assert log.incomplete is True


@pytest.mark.parametrize(
    "save_fails,measurement_fails", [(False, False), (True, False), (False, True)]
)
def test_group_delivery_records_only_after_save_and_get_stays_read_only(
    portal, tmp_path, monkeypatch, save_fails, measurement_fails
):
    with generated_portal(portal, tmp_path, monkeypatch) as (active, task, base, _, _):
        task = bind_generate(active, task, base)
        flow = active.server.application_flow_service
        store = active.server.application_resume_store
        original_draft = store.draft
        prepared = deepcopy(original_draft(task["draft_id"]))
        project = tmp_path / "group-project"
        project.mkdir()
        (project / "main.tex").write_text(prepared["latex_source"])
        prepared.update(
            id="f" * 32,
            source_checkpoint=source_snapshot(project, "main.tex"),
            group_session={"id": "synthetic-session"},
            group_context_revision="synthetic-context",
        )
        prepared["review_groups"][0]["review_fingerprint"] = "9" * 64
        monkeypatch.setattr(
            store,
            "draft",
            lambda identifier: (
                prepared if identifier == prepared["id"] else original_draft(identifier)
            ),
        )
        monkeypatch.setattr(store, "prepare_group_review", lambda *args, **kwargs: prepared)
        original_save = flow._save

        def save(state):
            if save_fails and any(
                row.get("group_read", {}).get("status") == "complete" for row in state["tasks"]
            ):
                raise OSError("synthetic group checkpoint failure")
            return original_save(state)

        monkeypatch.setattr(flow, "_save", save)
        log = store.measurements
        if measurement_fails:

            def fail_measurement(*args, **kwargs):
                raise OSError("synthetic measurement failure")

            monkeypatch.setattr(log, "confirmation_requested", fail_measurement)
        status, _ = post(
            active, "begin-group-review", {"task_id": task["id"], "task_revision": task["revision"]}
        )
        assert status == (500 if save_fails else 200)
        requests = [e for e in log.read() if e["kind"] == "resume_confirmation_request"]
        assert len(requests) == (0 if save_fails or measurement_fails else 1)
        retained = log.path.read_bytes() if log.path.exists() else None

        def unexpected_read():
            pytest.fail("GET must not scan the measurement history")

        monkeypatch.setattr(log, "read", unexpected_read)
        state = snapshot(active)
        assert state["draft_integrity"]["status"] == "valid"
        if not save_fails:
            assert state["active_task"]["group_read"]["status"] == "complete"
        if measurement_fails:
            assert log.incomplete is True
        assert (log.path.read_bytes() if log.path.exists() else None) == retained
