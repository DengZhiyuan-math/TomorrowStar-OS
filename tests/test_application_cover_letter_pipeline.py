"""Letter stage outcomes stop the Pipeline; late optional deliveries keep page ownership."""

import json
import threading
from uuid import uuid4

import pytest
from test_application_cover_letter_flow import change_saved_task, wait_for
from test_application_pipeline import advance
from test_application_pipeline import environment as environment
from test_career_portal_http import _running_portal
from test_career_portal_http import portal as portal
from test_cover_letter_content import phase, result

from career_evidence_graph._vendor import job_apply_store as helper
from career_evidence_graph.application_cover_letter import adopted_letter, generate_cover_letter
from career_evidence_graph.application_flow import ApplicationFlowService
from career_evidence_graph.career_portal_data import PortalDataError
from career_evidence_graph.validation.hashing import record_digest as digest


@pytest.mark.parametrize("scenario", ["reviewed", "paused_again", "scheduled_continue"])
def test_paused_current_letter_retry_http_writes_and_reviews_only_the_letter(
    portal, tmp_path, scenario
):
    with _running_portal(
        portal.applications,
        portal.career,
        flow_root=tmp_path / "flow",
        worker_root=tmp_path / "worker",
    ) as active:
        flow = active.server.application_flow_service
        pipeline = active.server.application_pipeline_service
        app = flow.applications.create_application(
            {"company": "Synthetic", "role_title": "Engineer", "job_description": "Build services."}
        )
        task = flow.create(app["id"], app["revision"])
        flow.callbacks["analysis"] = lambda _: {
            "id": "analysis",
            "application_id": app["id"],
            "job_brief": {"job": {"job_description": app["job_description"]}},
            "material_packet": {},
            "inference_result": {},
        }
        flow.start(task["id"], task["revision"], "analysis")
        task = wait_for(flow, task["id"], lambda row: row["status"] == "analysis_ready")

        def past_materials(row):
            row["status"] = "draft_ready"
            row["automatic_materials"] = True
            row["draft_id"] = "resume"
            row["stages"]["resume"] = {"status": "complete", "attempt_id": "a" * 32}
            row["stages"]["letter"] = {"status": "failed", "attempt_id": "b" * 32}
            row["artifacts"].append(
                {
                    "stage": "resume",
                    "attempt_id": "a" * 32,
                    "result": {"id": "resume", "content_revision": "a" * 64},
                    "inputs": row["inputs"],
                    "adopted": True,
                }
            )

        change_saved_task(flow, task["id"], past_materials)
        task = flow.task_snapshot(task["id"])
        with flow.applications.write_lock():
            state = json.loads(pipeline.path.read_bytes())
            recommendation = "application:" + app["id"]
            state.update(
                id=uuid4().hex,
                queue_mode=True,
                current_recommendation_id=recommendation,
                mail_poll_at=10**12,
                active_task_id=task["id"],
                items=[
                    {
                        "recommendation_id": recommendation,
                        "application_id": app["id"],
                        "task_id": task["id"],
                        "status": "needs_input",
                    }
                ],
                status="needs_input",
                wait_reason="resume_author_input_required",
            )
            if scenario == "scheduled_continue":
                state["model_resend"] = {"task_id": task["id"], "stage": "resume", "due": 10**12}
            state["revision"] = digest(
                {key: value for key, value in state.items() if key != "revision"}
            )
            helper.atomic_write_json(pipeline.path, state)

        calls = []
        entered, release = threading.Event(), threading.Event()

        def model(_config, prompt, **_options):
            called = phase(prompt)
            calls.append(called)
            if called == "review-schema.json":
                return result({"supported": True, "reason": "Supported expression."})
            if scenario == "paused_again":
                entered.set()
                assert release.wait(5)
            return result(
                {
                    "language": "en",
                    "paragraphs": [
                        {
                            "id": "motivation",
                            "kind": "motivation",
                            "text": "I would like to build reliable services.",
                            "source_ids": [],
                            "source_quotes": [],
                        }
                    ],
                }
            )

        def letter(request):
            return generate_cover_letter(
                flow.root / "cover-letters" / request["stages"]["letter"]["attempt_id"],
                app,
                flow.fixed_writing_inputs(request),
                sources={"items": []},
                runner=model,
                admit_call=lambda: flow.resume_call_allowed(request, "letter"),
            )

        def consistency(request):
            calls.append("pair consistency")
            return {
                "status": "passed",
                "resume_content_revision": "a" * 64,
                "letter_content_revision": adopted_letter(request)["content_revision"],
            }

        flow.callbacks.update(letter=letter, material_consistency=consistency)
        before_queue = pipeline.path.read_bytes()
        before_worker = pipeline.worker.store.path.read_bytes()
        status, _, response = active.request(
            "POST",
            "/api/flow/start",
            body=json.dumps(
                {
                    "task_id": task["id"],
                    "task_revision": task["revision"],
                    "stage": "letter",
                    "retry": True,
                }
            ).encode(),
            headers=active.write_headers(),
        )
        assert status == 200, response
        if scenario == "paused_again":
            assert entered.wait(5)
            try:
                pipeline.pause()
            finally:
                release.set()
        done = wait_for(
            flow,
            task["id"],
            lambda row: row["stages"]["letter"]["status"] not in {"queued", "running"},
        )
        if scenario == "paused_again":
            assert done["stages"]["letter"]["status"] == "failed", done["stages"]["letter"]
            assert adopted_letter(done) is None
            assert calls == ["schema.json"]
        else:
            assert done["stages"]["letter"]["status"] == "complete", done["stages"]["letter"]
            assert adopted_letter(done)["grounding"]["supported"] is True
            assert calls == ["schema.json", "review-schema.json"]
        assert done["status"] == task["status"]
        assert {k: v for k, v in done["stages"].items() if k != "letter"} == {
            k: v for k, v in task["stages"].items() if k != "letter"
        }
        assert done.get("material_consistency") == task.get("material_consistency")
        if scenario == "scheduled_continue":
            expected = json.loads(before_queue)
            expected.pop("model_resend")
            expected.pop("revision")
            current_queue = json.loads(pipeline.path.read_bytes())
            current_queue.pop("revision")
            assert current_queue == expected
        else:
            assert pipeline.path.read_bytes() == before_queue
        assert pipeline.worker.store.path.read_bytes() == before_worker
        if scenario == "reviewed":
            pipeline.continue_current(request_id="continue-after-letter-review")
            wait_for(
                flow,
                task["id"],
                lambda row: row.get("material_consistency", {}).get("status") == "passed",
            )
            assert calls == ["schema.json", "review-schema.json", "pair consistency"]


def letter_outcomes(flow):
    """The fake Flow reads letter stages as ``ApplicationFlowService.material_outcomes``."""
    flow.material_outcomes = lambda task_ids: {
        task_id: {
            "letter": flow.tasks[task_id]
            .get("stages", {})
            .get("letter", {})
            .get("status", "not_started"),
            "material_consistency": "not_started",
        }
        for task_id in task_ids
    }


def test_unknown_optional_author_stops_already_running_page(environment):
    pipeline, flow, _, worker, _ = environment
    pipeline.start(request_id="letter-unknown")
    state = advance(pipeline, "filling")
    identifier = state["active_task_id"]
    flow.tasks[identifier].setdefault("stages", {})["letter"] = {"status": "needs_recheck"}
    letter_outcomes(flow)
    pipeline._tick()
    stopped = pipeline.snapshot()
    assert stopped["control"] == "paused"
    assert stopped["status"] == "needs_recheck"
    assert stopped["wait_reason"] == "cover_letter_result_unknown"
    assert worker.state["control"] == "paused"
    assert stopped["active_task_id"] == identifier
    assert len(worker.state["jobs"]) == 1


def test_page_ready_retains_authority_until_late_optional_delivery(environment):
    pipeline, flow, _, worker, _ = environment
    pipeline.start(request_id="letter-late")
    state = advance(pipeline, "filling")
    identifier = state["active_task_id"]
    flow.tasks[identifier].setdefault("stages", {})["letter"] = {"status": "running"}
    job = worker.state["jobs"][0]
    job.update(
        status="ready_for_review",
        cover_letter_delivery={
            "status": "running",
            "requirement": "optional",
            "selected_fields": [["letter", ""]],
        },
    )
    pipeline._tick()
    ready = pipeline.snapshot()
    assert ready["status"] == "ready_for_review"
    assert ready["control"] == "running"
    assert ready["pending_optional_cover_letter"]
    assert worker.state["control"] == "running"
    assert ("worker_pause", identifier) not in flow.calls
    assert ("worker_review", identifier) not in flow.calls
    # The browser wakes this same page when the adopted letter arrives.
    flow.tasks[identifier]["stages"]["letter"]["status"] = "complete"
    flow.tasks[identifier]["letter_id"] = "letter"
    flow.tasks[identifier]["artifacts"].append(
        {"stage": "letter", "adopted": True, "result": {"id": "letter"}}
    )
    job["status"] = "filling"
    pipeline._tick()
    assert pipeline.snapshot()["status"] == "filling"
    assert not pipeline.snapshot().get("pending_optional_cover_letter")
    job["status"] = "ready_for_review"
    job["cover_letter_delivery"]["status"] = "ready"
    pipeline._tick()
    assert pipeline.snapshot()["status"] == "ready_for_review"
    assert pipeline.snapshot()["control"] == "paused"
    assert worker.state["control"] == "paused"


def test_absent_cover_letter_destination_does_not_delay_ready_page(environment):
    pipeline, flow, _, worker, _ = environment
    pipeline.start(request_id="letter-absent")
    state = advance(pipeline, "filling")
    flow.tasks[state["active_task_id"]].setdefault("stages", {})["letter"] = {"status": "running"}
    worker.state["jobs"][0].update(
        status="ready_for_review",
        cover_letter_delivery={"status": "running", "requirement": "none", "selected_fields": []},
    )
    pipeline._tick()
    assert pipeline.snapshot()["status"] == "ready_for_review"
    assert pipeline.snapshot()["control"] == "paused"
    assert not pipeline.snapshot().get("pending_optional_cover_letter")


@pytest.mark.parametrize(
    "action",
    [
        "flow:start",
        "flow:refresh-match",
        "flow:retry-material-consistency",
        "flow:recheck-material-consistency",
        "flow:recheck-resume-author",
    ],
)
@pytest.mark.parametrize("current,paused", [(False, True), (True, False), (True, True)])
def test_manual_material_author_admission_keeps_current_job_and_paused_control(
    environment, action, current, paused
):
    pipeline, flow, _, _, _ = environment
    pipeline.start(request_id="branch-admission")
    state = advance(pipeline, "filling")
    target = state["active_task_id"] if current else "another-task"
    if paused:
        pipeline.pause()
    flow._runtime_error, flow._owner, flow._closed = "", True, threading.Event()
    # A manual letter retry is a Flow start of the letter stage.
    payload = {"task_id": target} | (
        {"stage": "letter", "retry": True} if action == "flow:start" else {}
    )
    with pipeline.manual_entry(action, payload):
        if current and paused:
            ApplicationFlowService._writable(flow)
        else:
            with pytest.raises(PortalDataError) as rejected:
                ApplicationFlowService._writable(flow)
            assert rejected.value.code == "pipeline_current_material_required"
