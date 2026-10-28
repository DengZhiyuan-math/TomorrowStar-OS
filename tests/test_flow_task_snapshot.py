"""A scheduler reads one task without projecting unrelated historical work."""

import pytest
from test_application_flow import application as application

from career_evidence_graph.application_flow import ApplicationFlowService
from career_evidence_graph.career_portal_data import PortalDataError


def test_task_snapshot_matches_full_projection_and_is_detached(application, tmp_path):
    applications, job = application
    flow = ApplicationFlowService(applications, tmp_path / "flow")
    try:
        task = flow.create(job["id"], job["revision"])
        before = flow.path.read_bytes()
        expected = flow.snapshot(task["id"])["active_task"]
        actual = flow.task_snapshot(task["id"])
        assert actual == expected
        actual["stages"]["analysis"]["status"] = "changed"
        assert flow.task_snapshot(task["id"]) == expected
        assert flow.path.read_bytes() == before
    finally:
        flow.close()


def test_task_snapshot_only_observes_selected_worker(application, tmp_path):
    applications, job = application
    observed = []

    def unavailable(task):
        observed.append(task["id"])
        raise PortalDataError("synthetic_worker_unavailable", "Unavailable", 409)

    flow = ApplicationFlowService(
        applications, tmp_path / "flow", callbacks={"worker_reference": unavailable}
    )
    try:
        first = flow.create(job["id"], job["revision"])
        second = flow.create(job["id"], job["revision"], force_new=True)
        with applications.write_lock():
            state = flow._load()
            for task in state["tasks"]:
                task["worker_ref"] = {"batch_id": task["id"], "job_id": job["id"]}
            flow._save(state)
        before = flow.path.read_bytes()
        expected = flow.snapshot(second["id"])["active_task"]
        assert observed == [first["id"], second["id"]]
        observed.clear()
        assert flow.task_snapshot(second["id"]) == expected
        assert observed == [second["id"]]
        assert expected["worker_ref"]["status"] == "needs_recheck"
        assert flow.path.read_bytes() == before
    finally:
        flow.close()


def test_task_snapshot_keeps_existing_handoff_checks(application, tmp_path):
    applications, job = application
    flow = ApplicationFlowService(applications, tmp_path / "flow", preparation_only=True)
    try:
        task = flow.create(job["id"], job["revision"])
        with applications.write_lock():
            state = flow._load()
            state["tasks"][0]["codex_handoff_ref"] = {"task_id": "retained-handoff"}
            flow._save(state)
        before = flow.path.read_bytes()
        expected = flow.snapshot(task["id"])["active_task"]
        assert flow.task_snapshot(task["id"]) == expected
        assert expected["status"] == "needs_recheck"
        assert expected["codex_handoff_ref"]["status"] == "needs_recheck"
        assert flow.path.read_bytes() == before
    finally:
        flow.close()


def test_missing_task_snapshot_uses_existing_error(application, tmp_path):
    applications, _job = application
    flow = ApplicationFlowService(applications, tmp_path / "flow")
    try:
        with pytest.raises(PortalDataError) as expected:
            flow.snapshot("a" * 32)
        with pytest.raises(PortalDataError) as actual:
            flow.task_snapshot("a" * 32)
        assert (actual.value.code, actual.value.status) == (
            expected.value.code,
            expected.value.status,
        )
    finally:
        flow.close()
