"""Completed job materials survive unrelated maintenance configuration changes."""

from test_installed_write_admission_http import (
    business_bytes,
    installed_portal,
    post,
    prepare_payload,
)

from career_evidence_graph.career_portal_data import ApplicationStore


def test_research_benchmark_does_not_invalidate_current_job_preparation(tmp_path, monkeypatch):
    with installed_portal(tmp_path, monkeypatch) as (portal, task, _, starts):
        directory = portal.career / ".tomorrowstar-match-history"
        directory.mkdir(exist_ok=True)
        (directory / "current.json").write_text('{"synthetic": "unrelated research metadata"}')
        retained = portal.state()["applications"]

        status, shown = post(portal, "prepare-worker", prepare_payload(task))

        assert status == 200, shown
        state = portal.server.worker_service.store.load()
        assert state["control"] == "paused" and not state.get("runtime")
        assert len(state["jobs"]) == 1
        assert state["jobs"][0]["file_sha256"] == task["resume_sha256"]
        assert starts == []
        assert portal.state()["applications"] == retained
        current = portal.server.application_flow_service.snapshot()["active_task"]
        assert current["analysis_id"] == task["analysis_id"]
        assert current["resume_id"] == task["resume_id"]
        assert current["resume_sha256"] == task["resume_sha256"]
        assert current["inputs"] == task["inputs"]


def test_benchmark_retention_does_not_hide_changed_job_facts(tmp_path, monkeypatch):
    # The job identity still binds the materials; a career source revision does
    # not (APP-04), as test_research_benchmark... shows for unrelated metadata.
    with installed_portal(tmp_path, monkeypatch) as (portal, task, _, starts):
        directory = portal.career / ".tomorrowstar-match-history"
        directory.mkdir(exist_ok=True)
        (directory / "current.json").write_text('{"synthetic": "unrelated research metadata"}')
        applications = ApplicationStore(portal.applications)
        app = applications.get_application(task["application_id"])
        applications.update_application(
            app["id"], {"job_description": "Build different services."}, app["revision"]
        )
        retained = business_bytes(portal)

        status, shown = post(portal, "prepare-worker", prepare_payload(task))

        assert status == 409 and shown["error"] == "flow_inputs_stale"
        assert business_bytes(portal) == retained
        assert starts == []
