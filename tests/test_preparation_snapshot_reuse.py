"""One status read shares career evidence but the next read detects saved changes."""

import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Event, Lock

from test_application_flow import wait_for
from test_career_portal_http import portal as portal
from test_job_explanation_browser import explanation_portal
from test_pdf_export_http import SyntheticLatexClient, create_authorized_latex, export_payload
from test_preparation_entry import post, snapshot

from career_evidence_graph import application_preparation, application_runtime, career_portal
from career_evidence_graph.career_portal_data import ApplicationStore, PortalDataError


def test_loaded_revision_is_stable_across_hash_seeds():
    code = (
        "import sys; sys.path.insert(0, sys.argv[1]); "
        "from career_evidence_graph.career_portal import _loaded_preparation_revision; "
        "print(_loaded_preparation_revision())"
    )
    revisions = [
        subprocess.check_output(
            [sys.executable, "-s", "-B", "-c", code, str(Path(career_portal.__file__).parents[1])],
            env={"PYTHONHASHSEED": str(seed)},
            text=True,
            timeout=10,
        ).strip()
        for seed in (1, 2, 3)
    ]
    assert len(set(revisions)) == 1


def test_pdf_status_builds_one_career_snapshot_per_request(portal, tmp_path, monkeypatch):
    job = ApplicationStore(portal.applications).create_application(
        {"company": "Synthetic", "role_title": "Engineer", "job_description": "Build Python."}
    )
    with explanation_portal(portal, tmp_path) as (active, work):
        active.server.application_resume_store.prism_client = SyntheticLatexClient()
        task = create_authorized_latex(active, job)
        assert post(active, "export-pdf", export_payload(task))[0] == 200
        task = wait_for(
            active.server.application_flow_service,
            task["id"],
            lambda row: row["status"] == "resume_ready",
        )
        original = application_runtime.career_source_snapshot
        scans = []

        def measured(catalog, **kwargs):
            scans.append(catalog)
            return original(catalog, **kwargs)

        monkeypatch.setattr(application_runtime, "career_source_snapshot", measured)
        state = snapshot(active)
        assert state["pdf_integrity"]["status"] == "valid"
        assert len(scans) == 1
        scans.clear()
        assert active.request("GET", "/api/flow/drafts/" + task["draft_id"])[0] == 200
        assert active.request("GET", "/api/flow/exports/" + task["resume_id"])[0] == 200
        assert not scans
        original_task = state["active_task"]
        document = portal.career / "contributions/python.md"
        document.write_text(document.read_text().replace("Python service", "Python adapter"))
        scans.clear()
        changed = snapshot(active)
        assert len(scans) == 1
        assert changed["preparation"]["checks"]["draft"]["status"] == "stale"
        assert changed["active_task"] == original_task
        status, _, raw = active.request("GET", f"/api/flow/resumes/{task['resume_id']}/pdf")
        assert status == 200 and raw.startswith(b"%PDF-")


def test_failed_status_read_does_not_hide_changes_from_export_guard(portal, tmp_path, monkeypatch):
    job = ApplicationStore(portal.applications).create_application(
        {"company": "Synthetic", "role_title": "Engineer", "job_description": "Build Python."}
    )
    with explanation_portal(portal, tmp_path) as (active, work):
        task = create_authorized_latex(active, job)

        def fail_projection(**_arguments):
            raise PortalDataError("synthetic_projection_failure", "Synthetic failure", 503)

        with monkeypatch.context() as patch:
            patch.setattr(application_preparation, "preparation_checks", fail_projection)
            assert active.request("GET", "/api/flow/state")[0] == 503
        document = portal.career / "contributions/python.md"
        document.write_text(document.read_text().replace("Python service", "Python adapter"))
        assert post(active, "export-pdf", export_payload(task))[0] == 409
        assert not work["exports"]
        assert snapshot(active)["active_task"] == task


def test_concurrent_status_reads_do_not_share_source_observations(portal, tmp_path, monkeypatch):
    job = ApplicationStore(portal.applications).create_application(
        {"company": "Synthetic", "role_title": "Engineer", "job_description": "Build Python."}
    )
    with explanation_portal(portal, tmp_path) as (active, _work):
        create_authorized_latex(active, job)
        original = application_runtime.career_source_snapshot
        captured, release, lock = Event(), Event(), Lock()
        scans = []

        def measured(catalog, **kwargs):
            observation = original(catalog, **kwargs)
            with lock:
                first = not scans
                scans.append(observation["revision"])
            if first:
                captured.set()
                assert release.wait(3)
            return observation

        monkeypatch.setattr(application_runtime, "career_source_snapshot", measured)
        with ThreadPoolExecutor(max_workers=2) as pool:
            first_read = pool.submit(snapshot, active)
            try:
                assert captured.wait(3)
                document = portal.career / "contributions/python.md"
                document.write_text(
                    document.read_text().replace("Python service", "Python adapter")
                )
                second_read = pool.submit(snapshot, active)
            finally:
                release.set()
            first, second = first_read.result(), second_read.result()
        assert first["preparation"]["checks"]["draft"]["status"] == "available"
        assert second["preparation"]["checks"]["draft"]["status"] == "stale"
        assert len(scans) == 2 and scans[0] != scans[1]
