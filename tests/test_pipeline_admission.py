"""Manual jobs enter the existing pipeline queue without changing current work."""

from copy import deepcopy

from test_pipeline_recommendation_queue import drive
from test_pipeline_recommendation_queue import queue_environment as queue_environment


def test_admitting_another_recommendation_retains_current_job_without_creating_flow(
    queue_environment,
):
    pipeline, flow, intake, worker, *_ = queue_environment
    pipeline.start(request_id="start-admission")
    before = drive(pipeline, "generating_resume")
    recommendations = intake.snapshot()["recommendations"]
    row = recommendations[2]
    calls = deepcopy(flow.calls)
    result = pipeline.admit(
        {
            "request_id": "choose-next",
            "recommendation_id": row["id"],
            "recommendation_revision": row["revision"],
        }
    )
    assert result["current_recommendation_id"] == before["current_recommendation_id"]
    assert result["active_task_id"] == before["active_task_id"]
    assert result["control"] == before["control"]
    assert flow.calls == calls and len(flow.tasks) == 1
    pipeline.skip_current(request_id="skip-current-admission")
    after = drive(pipeline, "generating_resume")
    assert after["current_recommendation_id"] == recommendations[1]["id"]
    pipeline.skip_current(request_id="skip-second-admission")
    third = drive(pipeline, "generating_resume")
    assert third["current_recommendation_id"] == row["id"]
    assert len(flow.tasks) == 3


def test_manual_application_is_retained_before_start_and_has_one_idempotent_admission(
    queue_environment,
):
    pipeline, flow, _intake, _worker, *_ = queue_environment
    application = flow.applications.create_application(
        {
            "company": "Manual",
            "role_title": "Engineer",
            "url": "https://jobs.lever.co/manual/00000000-0000-0000-0000-000000000001",
            "location": "Zurich, Switzerland",
            "job_description": "Python systems",
        }
    )
    payload = {
        "request_id": "manual-jd",
        "application_id": application["id"],
        "application_revision": application["revision"],
    }
    saved = pipeline.admit(payload)
    assert saved["control"] == "paused" and saved["active_task_id"] is None
    assert flow.calls == []
    assert pipeline.admit(payload)["items"] == saved["items"]
    from career_evidence_graph.application_pipeline import ApplicationPipeline

    pipeline.close()
    reopened = ApplicationPipeline(flow, _intake, _worker, interval=100)
    try:
        assert reopened.snapshot()["items"] == saved["items"]
        assert reopened.admit(payload)["items"] == saved["items"]
        reopened.start(request_id="start-manual")
        current = drive(reopened, "generating_resume")
        assert current["active_task_id"] == application["id"]
        assert len(current["items"]) == 1 and len(flow.tasks) == 1
    finally:
        reopened.close()


def test_admission_rejects_stale_and_conflicting_request_without_changing_current(
    queue_environment,
):
    import pytest

    from career_evidence_graph.career_portal_data import PortalDataError

    pipeline, flow, intake, _worker, *_ = queue_environment
    pipeline.start(request_id="admission-conflicts")
    drive(pipeline, "generating_resume")
    rows = intake.snapshot()["recommendations"]
    payload = {
        "request_id": "duplicate",
        "recommendation_id": rows[2]["id"],
        "recommendation_revision": rows[2]["revision"],
    }
    with pytest.raises(PortalDataError, match="版本已变化"):
        pipeline.admit(payload | {"recommendation_revision": "stale"})
    before = pipeline.snapshot()
    assert len(before["items"]) == 1
    pipeline.admit(payload)
    with pytest.raises(PortalDataError, match="请求标识已用于其他岗位"):
        pipeline.admit(payload | {"recommendation_id": rows[3]["id"]})
    assert pipeline.snapshot()["current_recommendation_id"] == before["current_recommendation_id"]
    assert len(flow.tasks) == 1


def test_capture_in_progress_waits_before_acquiring_admitted_next_job(queue_environment):
    from threading import Event

    from test_application_intake import ready

    pipeline, flow, intake, _worker, _reads, fetches, *_ = queue_environment
    pipeline.start(request_id="capture-barrier-start")
    drive(pipeline, "generating_resume")
    row = intake.snapshot()["recommendations"][1]
    pipeline.admit(
        {
            "request_id": "admit-before-capture",
            "recommendation_id": row["id"],
            "recommendation_revision": row["revision"],
        }
    )
    entered, release = Event(), Event()

    def reader(*_args, **_kwargs):
        entered.set()
        assert release.wait(10)
        return {"status": "readable", "emails": [], "provenance": {}}

    intake.reader = reader
    try:
        pipeline.capture_mail(request_id="capture-barrier")
        assert entered.wait(3)
        pipeline.skip_current(request_id="capture-barrier-skip")
        pipeline._tick()
        pipeline._tick()
        waiting = pipeline.snapshot()
        assert waiting["control"] == "running" and waiting["status"] == "acquiring_source"
        assert len(fetches) == 1 and len(flow.tasks) == 1
        release.set()
        ready(intake)
        current = drive(pipeline, "generating_resume")
        assert current["current_recommendation_id"] == row["id"]
        assert len(fetches) == 2 and len(flow.tasks) == 2
    finally:
        release.set()
