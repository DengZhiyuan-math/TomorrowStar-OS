"""A new input generation cannot revive an older preparation task."""

import threading

from test_application_flow import application as application
from test_application_flow import wait_for

from career_evidence_graph.application_flow import ApplicationFlowService


def test_returning_to_input_a_creates_a_new_generation_instead_of_reusing_old_a(
    application, tmp_path
):
    applications, job = application
    service = ApplicationFlowService(applications, tmp_path / "flow", preparation_only=True)
    try:
        first = service.create(job["id"], job["revision"], inputs={"sources": "A"})
        second = service.create(job["id"], job["revision"], inputs={"sources": "B"})
        current = service.create(job["id"], job["revision"], inputs={"sources": "A"})
        assert len({first["id"], second["id"], current["id"]}) == 3
        assert service.create(job["id"], job["revision"], inputs={"sources": "A"}) == current
        assert current["artifacts"] == []
    finally:
        service.close()


def test_returning_to_a_does_not_adopt_an_earlier_running_a_result(application, tmp_path):
    applications, job = application
    entered, release = threading.Event(), threading.Event()

    def analyze(_):
        entered.set()
        assert release.wait(3)
        return {"id": "old-analysis", "requirements": []}

    service = ApplicationFlowService(
        applications, tmp_path / "flow", preparation_only=True, callbacks={"analysis": analyze}
    )
    try:
        first = service.create(job["id"], job["revision"], inputs={"sources": "A"})
        service.start(first["id"], first["revision"], "analysis")
        assert entered.wait(3)
        service.create(job["id"], job["revision"], inputs={"sources": "B"})
        current = service.create(job["id"], job["revision"], inputs={"sources": "A"})
        release.set()
        first = wait_for(service, first["id"], lambda task: bool(task["artifacts"]))
        assert first["artifacts"][-1]["adopted"] is False
        assert first["analysis_id"] is None
        assert service.snapshot(current["id"])["active_task"]["artifacts"] == []
    finally:
        release.set()
        service.close()


def test_observed_a_to_b_to_a_updates_keep_old_attempt_unadopted(application, tmp_path):
    applications, job = application
    entered, release = threading.Event(), threading.Event()
    calls = []

    def analyze(_):
        calls.append("analysis")
        entered.set()
        assert release.wait(3)
        return {"id": f"analysis-{len(calls)}", "requirements": []}

    service = ApplicationFlowService(
        applications, tmp_path / "flow", preparation_only=True, callbacks={"analysis": analyze}
    )
    try:
        task = service.create(job["id"], job["revision"], inputs={"sources": "A"})
        service.start(task["id"], task["revision"], "analysis")
        assert entered.wait(3)
        task = service.snapshot(task["id"])["active_task"]
        for value in ("B", "A"):
            task = service.update_inputs(
                task["id"], task["revision"], job["revision"], inputs={"sources": value}
            )
        assert task["input_epoch"] == 2
        release.set()
        task = wait_for(service, task["id"], lambda row: bool(row["artifacts"]))
        assert task["analysis_id"] is None and task["artifacts"][-1]["adopted"] is False
        service.start(task["id"], task["revision"], "analysis")
        task = wait_for(service, task["id"], lambda row: row["status"] == "analysis_ready")
        assert task["analysis_id"] == "analysis-2" and len(calls) == 2
    finally:
        release.set()
        service.close()
