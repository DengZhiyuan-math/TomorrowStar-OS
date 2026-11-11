"""A skipped match callback retains execution ownership until it physically returns."""

import json
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from threading import Event
from uuid import uuid4

import pytest
from test_application_flow import wait_for
from test_career_portal_http import _running_portal
from test_career_portal_http import portal as portal
from test_match_recheck_preservation import original_fields
from test_match_recheck_preservation import retained_match as retained_match
from test_normal_match_refresh import setup_callback

from career_evidence_graph.career_portal_data import PortalDataError


def post(active, path, payload):
    status, _, raw = active.request(
        "POST", path, body=json.dumps(payload).encode(), headers=active.write_headers()
    )
    return status, json.loads(raw)


@pytest.fixture
def refresh_queue(retained_match, tmp_path):
    _, source, job, task, sources, library, work = retained_match
    with _running_portal(
        source.applications.root,
        retained_match[0].career,
        flow_root=tmp_path / "default-flow",
        worker_root=tmp_path / "default-worker",
    ) as active:
        flow = active.server.application_flow_service
        pipeline = active.server.application_pipeline_service
        flow.input_provider = source.input_provider
        flow.information_provider = source.information_provider
        with flow.applications.write_lock():
            state = deepcopy(source._load())
            state["mode"] = "application"
            flow._save(state)
        setup_callback((active, flow, job, task, sources, library, work))
        pipeline._poll_mail = lambda state: None
        other = flow.applications.create_application(
            {
                "company": "Next Synthetic Employer",
                "role_title": "Software Engineer",
                "url": "https://jobs.lever.co/synthetic/00000000-0000-0000-0000-000000000001",
                "location": "Zurich, Switzerland",
                "job_description": "Build reliable Python systems.",
            }
        )
        with pipeline._guard, flow.applications.write_lock():
            state = pipeline._load()
            state.update(
                id=uuid4().hex,
                queue_mode=True,
                status="needs_input",
                control="paused",
                active_task_id=task["id"],
                current_recommendation_id="application:" + job["id"],
                items=[
                    {
                        "recommendation_id": "application:" + job["id"],
                        "application_id": job["id"],
                        "task_id": task["id"],
                        "status": "needs_input",
                    }
                ],
            )
            pipeline._save(state)
        status, admitted = post(
            active,
            "/api/pipeline/admit",
            {
                "request_id": "admit-next",
                "application_id": other["id"],
                "application_revision": other["revision"],
            },
        )
        assert status == 200, admitted
        yield active, flow, pipeline, job, task, other


@pytest.mark.parametrize("completion", ["success", "known_failure", "unknown_failure"])
def test_skip_waits_for_original_callback_then_progresses_without_another_continue(
    refresh_queue, completion
):
    active, flow, pipeline, job, task, other = refresh_queue
    entered, release, analysis_entered = Event(), Event(), Event()
    timeline, match_calls = [], []
    callback = flow.callbacks["refresh_match"]

    def refresh(*args, **kwargs):
        match_calls.append(args)
        timeline.append("refresh-start")
        entered.set()
        assert release.wait(10)
        timeline.append("refresh-end")
        if completion == "known_failure":
            raise PortalDataError("match_model_invalid", "Synthetic known failure", 409)
        if completion == "unknown_failure":
            raise OSError("Synthetic lost model response")
        return callback(*args, **kwargs)

    def analyze(request):
        timeline.append("next-analysis-start")
        analysis_entered.set()
        raise PortalDataError("synthetic_analysis_stop", "Synthetic stop", 409)

    flow.callbacks["refresh_match"] = refresh
    flow.callbacks["analysis"] = analyze
    request_id = uuid4().hex
    payload = {
        "task_id": task["id"],
        "task_revision": task["revision"],
        "request_id": request_id,
    }
    original = original_fields(flow.task_snapshot(task["id"]))
    headers = active.write_headers()
    with ThreadPoolExecutor(max_workers=1) as executor:
        pending = executor.submit(
            active.request,
            "POST",
            "/api/flow/refresh-match",
            body=json.dumps(payload).encode(),
            headers=headers,
        )
        try:
            assert entered.wait(5)
            status, skipped = post(
                active, "/api/pipeline/skip", {"request_id": "skip-during-refresh"}
            )
            assert status == 200, skipped
            assert skipped["current_recommendation_id"] is None
            assert skipped["active_task_id"] is None
            assert skipped["items"][0]["status"] == "skipped"
            assert original_fields(flow.task_snapshot(task["id"])) == original
            for _ in range(3):
                pipeline._tick()
            assert not any(row["application_id"] == other["id"] for row in flow.snapshot()["tasks"])
            assert not analysis_entered.is_set()
            assert timeline == ["refresh-start"]
            assert active.request("GET", "/api/flow/state")[0] == 200
            assert active.request("GET", "/api/pipeline/state")[0] == 200
        finally:
            release.set()
        response = pending.result(timeout=10)
    assert response[0] == (500 if completion == "unknown_failure" else 409), response[2]
    assert len(match_calls) == 1
    assert original_fields(flow.task_snapshot(task["id"])) == original
    for _ in range(3):
        pipeline._tick()
    assert analysis_entered.wait(5), pipeline.snapshot()
    assert timeline.index("refresh-end") < timeline.index("next-analysis-start")
    assert len(match_calls) == 1
    intent = flow.root / "match-refreshes" / request_id / "intent.json"
    assert intent.exists()
    status, returned = post(
        active,
        "/api/pipeline/return",
        {"request_id": "return-original", "application_id": job["id"]},
    )
    assert status == 200 and returned["active_task_id"] == task["id"], returned
    status, replay = post(active, "/api/flow/refresh-match", payload)
    assert status == (200 if completion == "success" else 409), replay
    assert len(match_calls) == 1


@pytest.mark.parametrize("entry", ["analysis", "continue-current"])
def test_direct_other_job_execution_waits_but_same_job_reads_remain_available(refresh_queue, entry):
    active, flow, pipeline, job, task, other = refresh_queue
    entered, release, work_entered = Event(), Event(), Event()
    callback = flow.callbacks["refresh_match"]
    calls = []
    target = next(row for row in flow.snapshot()["tasks"] if row["id"] != task["id"])
    reference = {"batch_id": "synthetic", "job_id": target["application_id"], "status": "filling"}
    if entry == "continue-current":
        with flow.applications.write_lock():
            state = flow._load()
            flow._task(state, target["id"])["worker_ref"] = reference
            flow._save(state)
        target = flow.task_snapshot(target["id"])

    def refresh(*args, **kwargs):
        entered.set()
        assert release.wait(10)
        return callback(*args, **kwargs)

    def analyze(request):
        calls.append(request["id"])
        work_entered.set()
        raise PortalDataError("synthetic_analysis_stop", "Synthetic stop", 409)

    def control(request, operation, payload):
        calls.append((request["id"], operation))
        work_entered.set()
        return reference

    flow.callbacks["refresh_match"] = refresh
    flow.callbacks["analysis"] = analyze
    flow.callbacks["control_worker"] = control
    payload = {"task_id": task["id"], "task_revision": task["revision"], "request_id": uuid4().hex}
    headers = active.write_headers()
    with ThreadPoolExecutor(max_workers=1) as executor:
        pending = executor.submit(
            active.request,
            "POST",
            "/api/flow/refresh-match",
            body=json.dumps(payload).encode(),
            headers=headers,
        )
        try:
            assert entered.wait(5)
            original = flow.task_snapshot(target["id"])
            with pytest.raises(PortalDataError) as rejected:
                if entry == "analysis":
                    flow.start(target["id"], target["revision"], "analysis")
                else:
                    flow.worker_action(target["id"], target["revision"], entry, {})
            assert rejected.value.code == "match_refresh_other_job_running"
            assert flow.task_snapshot(target["id"]) == original
            assert calls == []
            assert active.request("GET", "/api/flow/state")[0] == 200
        finally:
            release.set()
        assert pending.result(timeout=10)[0] == 200
    if entry == "analysis":
        flow.start(target["id"], target["revision"], "analysis")
    else:
        flow.worker_action(target["id"], target["revision"], entry, {})
    assert work_entered.wait(5)
    assert len(calls) == 1


def test_same_job_control_and_capture_remain_available_during_refresh(refresh_queue):
    active, flow, pipeline, job, task, other = refresh_queue
    entered, release = Event(), Event()
    callback = flow.callbacks["refresh_match"]
    control_calls, mail_calls = [], []
    reference = {"batch_id": "synthetic", "job_id": job["id"], "status": "filling"}
    with flow.applications.write_lock():
        state = flow._load()
        current = flow._task(state, task["id"])
        current["worker_ref"] = reference
        current.pop("codex_handoff_ref", None)
        current.pop("codex_handoff_attempt", None)
        flow._save(state)
    task = flow.task_snapshot(task["id"])

    def refresh(*args, **kwargs):
        entered.set()
        assert release.wait(10)
        return callback(*args, **kwargs)

    def control(request, operation, payload):
        control_calls.append((request["id"], operation))
        return reference

    def capture(**kwargs):
        mail_calls.append(kwargs)
        return {"run_id": "synthetic-mail", "status": "complete"}

    flow.callbacks["refresh_match"] = refresh
    flow.callbacks["control_worker"] = control
    pipeline.intake.refresh = capture
    payload = {"task_id": task["id"], "task_revision": task["revision"], "request_id": uuid4().hex}
    headers = active.write_headers()
    with ThreadPoolExecutor(max_workers=1) as executor:
        pending = executor.submit(
            active.request,
            "POST",
            "/api/flow/refresh-match",
            body=json.dumps(payload).encode(),
            headers=headers,
        )
        try:
            assert entered.wait(5)
            flow.worker_action(task["id"], task["revision"], "continue-current", {})
            assert control_calls == [(task["id"], "continue-current")]
            status, captured = post(
                active, "/api/pipeline/capture", {"request_id": "capture-while-matching"}
            )
            assert status == 200, captured
            assert mail_calls == [{"capture_only": True}]
            assert captured["active_task_id"] == task["id"]
            assert not any(row["application_id"] == other["id"] for row in flow.snapshot()["tasks"])
        finally:
            release.set()
        assert pending.result(timeout=10)[0] == 200


def test_direct_second_refresh_cannot_overlap_first_callback(retained_match):
    _, flow, job, task, *_ = retained_match
    other = next(row for row in flow.snapshot()["tasks"] if row["id"] != task["id"])
    flow.start(other["id"], other["revision"], "analysis")
    other = wait_for(flow, other["id"], lambda row: row["status"] == "analysis_ready")
    setup_callback(retained_match)
    callback = flow.callbacks["refresh_match"]
    entered, release = Event(), Event()
    calls = []

    def refresh(application, *args, **kwargs):
        calls.append(application["id"])
        if application["id"] == job["id"]:
            entered.set()
            assert release.wait(10)
            return callback(application, *args, **kwargs)
        raise PortalDataError("synthetic_second_callback_entered", "second callback entered", 409)

    flow.callbacks["refresh_match"] = refresh
    second_id = uuid4().hex
    with ThreadPoolExecutor(max_workers=1) as executor:
        pending = executor.submit(flow.refresh_match, task["id"], task["revision"], uuid4().hex)
        try:
            assert entered.wait(5)
            with pytest.raises(PortalDataError) as rejected:
                flow.refresh_match(other["id"], other["revision"], second_id)
            assert rejected.value.code == "match_refresh_other_job_running"
            assert calls == [job["id"]]
            assert not (flow.root / "match-refreshes" / second_id).exists()
        finally:
            release.set()
        assert pending.result(timeout=10)["id"] == task["id"]
    with pytest.raises(PortalDataError) as allowed:
        flow.refresh_match(other["id"], other["revision"], second_id)
    assert allowed.value.code == "synthetic_second_callback_entered"
    assert calls == [job["id"], other["application_id"]]
