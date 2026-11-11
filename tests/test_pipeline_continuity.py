"""Healthy application progression has no whole-cycle deadline."""

from test_application_pipeline import advance
from test_application_pipeline import environment as environment

from career_evidence_graph.career_portal_data import PortalDataError


def test_healthy_current_job_continues_after_twenty_minutes(environment, monkeypatch):
    pipeline, flow, _intake, worker, _jobs = environment
    pipeline.start(request_id="continuous-work")
    current = advance(pipeline, "filling")
    previous_calls = len(flow.calls)
    monkeypatch.setattr(
        "career_evidence_graph.application_pipeline.time.time",
        lambda: current["started_at"] + 3600,
    )
    pipeline._tick()
    after = pipeline.snapshot()
    assert after["status"] == "filling" and after["control"] == "running"
    assert worker.snapshot()["control"] == "running"
    assert [call[0] for call in flow.calls[previous_calls:]] == ["worker_heartbeat"]
    pipeline.pause()
    assert pipeline.snapshot()["control"] == "paused"
    assert worker.snapshot()["control"] == "paused"


def test_current_job_reaches_submit_wait_before_analyzing_the_next(environment):
    pipeline, flow, _intake, worker, jobs = environment
    pipeline.start(request_id="persistent-job-order")
    current = advance(pipeline, "filling")
    assert current["active_task_id"] == jobs[0]["id"]
    assert [call for call in flow.calls if call[0] == "analysis"] == [("analysis", jobs[0]["id"])]
    assert current["items"][1]["status"] == "pending"
    assert jobs[1]["id"] not in flow.tasks
    worker.state["jobs"][0].update(status="ready_for_review", page_open=True)
    waiting = advance(pipeline, "ready_for_review")
    before = list(flow.calls)
    pipeline._tick()
    assert pipeline.snapshot()["active_task_id"] == jobs[0]["id"]
    assert pipeline.snapshot()["items"] == waiting["items"]
    assert flow.calls == before and worker.snapshot()["jobs"][0]["page_open"] is True


def test_pipeline_uses_complete_draft_export_before_worker(environment, monkeypatch):
    pipeline, flow, _intake, _worker, _jobs = environment
    original = flow.start
    stages = []

    def prepare_automatic(identifier, _revision):
        flow.tasks[identifier]["automatic_materials"] = True
        return flow.snapshot(identifier)["active_task"]

    def start(identifier, revision, stage):
        task = flow.tasks[identifier]
        if stage == "resume":
            assert task.get("automatic_materials") is True
            stages.append("full_draft")
            task.update(status="draft_ready", draft_id="draft", draft_sha256="a" * 64)
            return flow.snapshot(identifier)["active_task"]
        if stage == "export":
            stages.append("checked_export")
            task.update(status="materials_ready", resume_id="pdf", resume_sha256="b" * 64)
            return flow.snapshot(identifier)["active_task"]
        return original(identifier, revision, stage)

    monkeypatch.setattr(flow, "prepare_automatic_materials", prepare_automatic, raising=False)
    monkeypatch.setattr(flow, "start", start)
    pipeline.start(request_id="complete-materials")
    advance(pipeline, "filling")
    assert stages == ["full_draft", "checked_export"]
    assert sum(call[0] == "prepare" for call in flow.calls) == 1


def test_missing_base_waits_and_one_continue_uses_newly_available_base(environment, monkeypatch):
    pipeline, flow, _intake, worker, _jobs = environment
    available = []

    def prepare_automatic(identifier, _revision):
        if not available:
            raise PortalDataError(
                "flow_latex_base_required", "Synthetic existing base required", 409
            )
        flow.tasks[identifier]["automatic_materials"] = True
        return flow.snapshot(identifier)["active_task"]

    monkeypatch.setattr(flow, "prepare_automatic_materials", prepare_automatic, raising=False)
    pipeline.start(request_id="material-base-wait")
    waiting = advance(pipeline, "needs_input")
    assert waiting["control"] == "paused"
    assert worker.snapshot()["jobs"] == []
    assert not any(call[0] in {"resume", "prepare"} for call in flow.calls)
    previous_calls = list(flow.calls)
    pipeline.start(request_id=waiting["request_id"])
    pipeline._tick()
    assert pipeline.snapshot()["status"] == "needs_input" and flow.calls == previous_calls
    available.append(True)
    resumed = pipeline.start(request_id="base-now-available")
    assert resumed["active_task_id"] == waiting["active_task_id"]
    assert pipeline.start(request_id="base-now-available") == resumed
    advance(pipeline, "filling")
    assert sum(call[0] == "resume" for call in flow.calls) == 1
