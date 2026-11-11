"""Preparation admission and Flow share the same settled-cancellation boundary."""

import json

from test_career_portal_http import _running_portal
from test_career_portal_http import portal as portal

from career_evidence_graph.career_portal_data import ApplicationStore


def test_readiness_keeps_original_current_after_settled_duplicate_cancellation(portal, tmp_path):
    job = ApplicationStore(portal.applications).create_application(
        {
            "company": "Synthetic Employer",
            "role_title": "Python Engineer",
            "job_description": "Build Python systems.",
        }
    )
    with _running_portal(
        portal.applications,
        portal.career,
        flow_root=tmp_path / "preparation",
        preparation_only=True,
    ) as active:
        flow = active.server.application_flow_service
        original = flow.create(job["id"], job["revision"])

        def input_state():
            status, _, body = active.request("GET", "/api/flow/readiness/" + original["id"])
            assert status == 200
            return json.loads(body)["inputs"]["state"]

        assert input_state() == "current"
        duplicate = flow.create(job["id"], job["revision"], force_new=True)
        assert input_state() == "stale"
        cancelled = flow.cancel(duplicate["id"], duplicate["revision"])
        assert input_state() == "current"
        assert flow.snapshot(original["id"])["active_task"] == original
        assert flow.snapshot(duplicate["id"])["active_task"] == cancelled
        with flow.applications.write_lock():
            saved = flow._load()
            row = flow._task(saved, duplicate["id"])
            row["stages"]["resume"]["status"] = "needs_recheck"
            flow._save(saved)
        assert input_state() == "stale"
