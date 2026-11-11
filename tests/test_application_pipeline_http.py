"""Automatic workflow controls retain loopback authorization and mode boundaries."""

import json
import time

import pytest
from test_application_intake import message, ready
from test_career_portal_http import _running_portal
from test_career_portal_http import portal as portal
from test_worker_backend_recovery import backend as backend

from career_evidence_graph.application_intake import ApplicationIntakeService


def test_pipeline_capture_authenticates_and_does_not_start_job_execution(portal, tmp_path):
    reads = []

    def factory(applications, root):
        return ApplicationIntakeService(
            applications,
            root,
            reader=lambda *_a, **_k: (
                reads.append(True)
                or {"status": "readable", "emails": [message()], "provenance": {}}
            ),
            fetcher=lambda *_: pytest.fail("capture must not acquire a JD"),
            extractor=lambda *_: pytest.fail("capture must not start an analysis"),
        )

    with _running_portal(
        portal.applications,
        portal.career,
        flow_root=tmp_path / "flow",
        worker_root=tmp_path / "worker",
        flow_intake_factory=factory,
    ) as active:
        payload = json.dumps({"request_id": "capture-api"}).encode()
        assert active.request("POST", "/api/pipeline/capture", body=payload)[0] == 403
        assert reads == []
        status, _, raw = active.request(
            "POST", "/api/pipeline/capture", body=payload, headers=active.write_headers()
        )
        assert status == 200, raw
        assert ready(active.server.application_intake_service)["status"] == "complete"
        status, _, raw = active.request("GET", "/api/pipeline/state")
        shown = json.loads(raw)
        assert status == 200 and shown["status"] == "idle" and shown["control"] == "paused"
        assert len(shown["pending_recommendations"]) == 1
        assert active.server.application_flow_service.snapshot()["tasks"] == []
        assert active.server.worker_service.snapshot()["jobs"] == []
        assert (
            active.request(
                "POST", "/api/pipeline/capture", body=payload, headers=active.write_headers()
            )[0]
            == 200
        )
        assert reads == [True]


def test_material_only_entry_exposes_disabled_automation_without_starting_work(portal, tmp_path):
    with _running_portal(
        portal.applications, portal.career, flow_root=tmp_path / "flow", preparation_only=True
    ) as active:
        status, _, raw = active.request("GET", "/api/pipeline/state")
        assert status == 200, raw
        state = json.loads(raw)
        assert state["protocol"] == "application-pipeline/v1"
        assert state["enabled"] is False
        assert active.server.application_intake_service.snapshot()["status"] == "idle"
        assert active.server.application_flow_service.snapshot()["tasks"] == []


def test_one_authorized_start_reads_mail_in_backend_and_waits_without_ui_polling(portal, tmp_path):
    reads = []

    def reader(root, **options):
        reads.append(options)
        return {"status": "no_matches", "emails": [], "provenance": {}}

    def factory(applications, root):
        return ApplicationIntakeService(applications, root, reader=reader)

    with _running_portal(
        portal.applications,
        portal.career,
        flow_root=tmp_path / "flow",
        worker_root=tmp_path / "worker",
        flow_intake_factory=factory,
    ) as active:
        body = json.dumps({"request_id": "a" * 32}).encode()
        assert active.request("POST", "/api/pipeline/start", body=body)[0] == 403
        assert reads == []
        status, _, raw = active.request(
            "POST", "/api/pipeline/start", body=body, headers=active.write_headers()
        )
        assert status == 200, raw
        deadline = time.monotonic() + 8
        service = active.server.application_pipeline_service
        # Only read the service here; no route refresh or client heartbeat drives work.
        while time.monotonic() < deadline:
            state = service.snapshot()
            if state["status"] == "waiting_for_mail":
                break
            time.sleep(0.02)
        else:
            pytest.fail("Backend did not reach the persistent mail wait")
        assert state["status"] == "waiting_for_mail" and state["control"] == "running", state
        assert len(reads) == 1 and reads[0]["max_results"] == 3
        assert state["notification"] is None
        status, _, raw = active.request(
            "POST", "/api/pipeline/start", body=body, headers=active.write_headers()
        )
        assert status == 200, raw
        repeated = json.loads(raw)
        assert repeated["id"] == state["id"] and repeated["notification"] is None
        assert repeated["status"] == "waiting_for_mail" and repeated["control"] == "running"
        assert len(reads) == 1
        assert active.server.application_flow_service.snapshot()["tasks"] == []
        for operation in ("submit", "recheck", "cancel", "release"):
            status, _, _ = active.request(
                "POST",
                "/api/pipeline/" + operation,
                body=b"{}",
                headers=active.write_headers(),
            )
            assert status == 400


def _served(owner, tmp_path):
    from threading import Thread

    from test_career_portal_http import Portal

    client = Portal(owner, owner.worker_service.store.applications.root, tmp_path / "career")
    thread = Thread(target=owner.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True)
    thread.start()
    return client, thread


def _control_view(owner, result):
    """The durable current-job projection that a control may change."""
    if isinstance(result, str):
        return result
    state = owner.application_pipeline_service.snapshot()
    worker = owner.worker_service.store.load()
    return {
        "control": state["control"],
        "status": state["status"],
        "resume_status": state.get("resume_status"),
        "current": state.get("current_recommendation_id"),
        "active_task": state.get("active_task_id") is not None,
        "items": [(row["recommendation_id"], row["status"]) for row in state["items"]],
        "requests": [(row["action"], row["status"]) for row in state.get("current_requests", [])],
        "worker_control": worker["control"],
        "worker_current": worker.get("current_job_id") is not None,
        "selections": [row["operation"] for row in worker.get("selection_history", [])],
    }


CONTROL_SEQUENCE = (
    ("pause", {}),
    ("skip", {"request_id": "skip-one"}),
    ("skip", {"request_id": "skip-one"}),
    ("return", {"request_id": "return-one", "application_id": "synthetic-recommendation"}),
    ("continue", {"request_id": "continue-one"}),
)


@pytest.mark.parametrize("entry", ["named", "http"])
def test_named_controls_match_http_controls(backend, tmp_path, entry):
    from career_evidence_graph.career_portal_data import PortalDataError

    owner, _reopen, _runner, _page = backend
    pipeline = owner.application_pipeline_service
    named = {
        "pause": lambda _payload: pipeline.pause(),
        "skip": lambda payload: pipeline.skip_current(**payload),
        "return": lambda payload: pipeline.return_to(
            payload["application_id"], request_id=payload["request_id"]
        ),
        "continue": lambda payload: pipeline.continue_current(**payload),
    }
    client, thread = _served(owner, tmp_path)
    views = []
    try:
        for action, payload in CONTROL_SEQUENCE:
            if entry == "named":
                try:
                    result = named[action](payload)
                except PortalDataError as error:
                    result = error.code
            else:
                status, _, raw = client.request(
                    "POST",
                    "/api/pipeline/" + action,
                    body=json.dumps(payload).encode(),
                    headers=client.write_headers(),
                )
                result = json.loads(raw) if status == 200 else json.loads(raw)["error"]
            views.append(_control_view(owner, result))
    finally:
        owner.shutdown()
        thread.join(timeout=2)
    paused, skipped, repeated, returned, continued = views
    assert paused["control"] == "paused" and paused["status"] == "paused"
    assert paused["resume_status"] == "filling" and paused["worker_control"] == "paused"
    assert skipped["current"] is None and skipped["status"] == "selecting_job"
    assert skipped["items"] == [("synthetic-recommendation", "skipped")]
    assert skipped["selections"] == ["skip-current"] and not skipped["worker_current"]
    assert repeated == skipped
    assert returned["current"] == "synthetic-recommendation" and returned["active_task"]
    assert returned["control"] == "paused" and returned["worker_current"]
    assert returned["selections"] == ["skip-current", "select-current"]
    assert returned["requests"] == [("skip", "complete"), ("return", "complete")]
    # Continue hands the original page back to the Worker once; it does not resume blindly.
    assert continued == returned | {
        "control": "running",
        "status": "continuing_worker",
        "requests": returned["requests"] + [("continue", "complete")],
    }


def test_flow_worker_pause_routes_through_pipeline_pause(backend, tmp_path):
    owner, _reopen, _runner, _page = backend
    pipeline = owner.application_pipeline_service
    task = owner.application_flow_service.task_snapshot(pipeline.snapshot()["active_task_id"])
    client, thread = _served(owner, tmp_path)
    try:
        # The page-unload and "pause filling" UI path use this same Worker request.
        status, _, raw = client.request(
            "POST",
            "/api/flow/worker-action",
            body=json.dumps(
                {
                    "task_id": task["id"],
                    "task_revision": task["revision"],
                    "operation": "pause",
                    "payload": {"controller": "pipeline-controller"},
                }
            ).encode(),
            headers=client.write_headers(),
        )
        state = pipeline.snapshot()
    finally:
        owner.shutdown()
        thread.join(timeout=2)
    assert status == 200, raw
    assert state["control"] == "paused" and state["status"] == "paused"
    assert state["resume_status"] == "filling" and state["active_task_id"] == task["id"]
    assert owner.worker_service.store.load()["control"] == "paused"
    assert json.loads(raw)["pipeline"]["status"] == "paused"


def test_flow_worker_skip_routes_through_pipeline_skip(backend, tmp_path):
    owner, _reopen, _runner, _page = backend
    pipeline = owner.application_pipeline_service
    task = owner.application_flow_service.task_snapshot(pipeline.snapshot()["active_task_id"])
    client, thread = _served(owner, tmp_path)
    try:
        status, _, raw = client.request(
            "POST",
            "/api/flow/worker-action",
            body=json.dumps(
                {
                    "task_id": task["id"],
                    "task_revision": task["revision"],
                    "operation": "skip-current",
                    "payload": {"request_id": "worker-skip"},
                }
            ).encode(),
            headers=client.write_headers(),
        )
        state = pipeline.snapshot()
    finally:
        owner.shutdown()
        thread.join(timeout=2)
    assert status == 200, raw
    assert state["current_recommendation_id"] is None and state["active_task_id"] is None
    assert [row["status"] for row in state["items"]] == ["skipped"]
    assert state["current_requests"][0]["request_id"] == "worker-skip"


# MC-08 S5: Pipeline confirms the stop before Flow saves an edited material candidate.


def _claimed_codex(owner):
    worker = owner.worker_service
    state = worker.store.load()
    job = state["jobs"][0]
    identifier = job["application_id"]
    job["form_state"] = {
        "binding": {
            "run_id": state["runtime"]["id"],
            "page_id": job["page_observation"]["page_id"],
            "document_token": "edit-gate-document",
            "step": job["job_url"],
        }
    }
    worker.store.save(state)
    worker.request(
        "request-assistance",
        {
            "application_id": identifier,
            "binding": worker.assistance_context(identifier)["binding"],
            "request_id": "edit-gate-request",
        },
    )
    reference = worker.assistance_context(identifier)["assistance_ref"]
    worker.request(
        "claim-assistance",
        {"application_id": identifier, "assistance_ref": reference, "request_id": "edit-gate"},
    )
    return identifier


def _edit_payload(task, request_id="e" * 32):
    return {
        "task_id": task["id"],
        "task_revision": task["revision"],
        "material_id": "c" * 32,
        "expected_text_sha256": "d" * 64,
        "text": "Synthetic edited letter.",
        "request_id": request_id,
    }


def test_edit_waits_for_confirmed_stop_before_candidate(backend, tmp_path):
    owner, _reopen, _runner, _page = backend
    pipeline, flow, worker = (
        owner.application_pipeline_service,
        owner.application_flow_service,
        owner.worker_service,
    )
    identifier = _claimed_codex(owner)
    task = flow.task_snapshot(pipeline.snapshot()["active_task_id"])
    payload = json.dumps(_edit_payload(task)).encode()
    flow_bytes = flow.path.read_bytes()
    client, thread = _served(owner, tmp_path)
    try:
        status, _, raw = client.request(
            "POST", "/api/flow/edit-material", body=payload, headers=client.write_headers()
        )
        assert status == 409 and json.loads(raw)["error"] == "material_edit_stopping", raw
        assert flow.path.read_bytes() == flow_bytes
        stopping = worker.store.load()
        assistance = stopping["jobs"][0]["assistance"]
        assert stopping["control"] == "paused" and "material_edit" not in stopping["jobs"][0]
        assert assistance["status"] == "stopping"
        assert assistance["stop"]["reason"] == "user_paused"
        state = pipeline.snapshot()
        assert state["control"] == "paused" and "material_edit_gate" not in state
        # The original owner confirms Codex drained; only then may Flow see the edit.
        worker.record_assistance_stop(
            identifier,
            worker.assistance_context(identifier)["assistance_ref"],
            {
                "tools_revoked": True,
                "local_tools_drained": True,
                "process_stopped": True,
                "native_turn_id": None,
                "native_turn_status": "idle",
                "stop_status": "stopped",
            },
            request_id=assistance["stop"]["request_id"],
        )
        status, _, raw = client.request(
            "POST", "/api/flow/edit-material", body=payload, headers=client.write_headers()
        )
        gate = pipeline.snapshot()["material_edit_gate"]
    finally:
        owner.shutdown()
        thread.join(timeout=2)
    # The confirmed gate hands the edit to the unchanged material checks.
    assert json.loads(raw)["error"] != "material_edit_stopping", raw
    current = worker.store.load()
    assert gate == {
        "request_id": "e" * 32,
        "task_id": task["id"],
        "task_revision": task["revision"],
        "batch_id": current["batch_id"],
        "run_id": current["runtime"]["id"],
        "page_id": "original-page",
        "confirmed_at": gate["confirmed_at"],
    }
    assert current["jobs"][0]["assistance"]["active_writer"] == "codex"


def test_edit_gate_is_idempotent_and_preparation_edits_unchanged(backend, portal, tmp_path):
    from career_evidence_graph.career_portal_data import PortalDataError

    owner, _reopen, _runner, _page = backend
    pipeline, flow, worker = (
        owner.application_pipeline_service,
        owner.application_flow_service,
        owner.worker_service,
    )
    task = flow.task_snapshot(pipeline.snapshot()["active_task_id"])
    try:
        ready = pipeline.begin_material_edit(task["id"], task["revision"], request_id="gate-one")
        assert ready == {"edit_gate": "ready"}
        assert worker.store.load()["control"] == "paused"
        before = (
            pipeline.path.read_bytes(),
            worker.store.path.read_bytes(),
            flow.path.read_bytes(),
        )
        again = pipeline.begin_material_edit(task["id"], task["revision"], request_id="gate-one")
        assert again == ready
        after = (pipeline.path.read_bytes(), worker.store.path.read_bytes(), flow.path.read_bytes())
        assert after == before
        with pytest.raises(PortalDataError) as changed:
            pipeline.begin_material_edit(task["id"], "stale-revision", request_id="gate-two")
        assert changed.value.code == "current_job_changed"
        assert pipeline.path.read_bytes() == before[0]
    finally:
        owner.server_close()
    # Material-only preparation has no Worker batch: its edits keep their own checks.
    with _running_portal(
        portal.applications, portal.career, flow_root=tmp_path / "prep-flow", preparation_only=True
    ) as active:
        record = tmp_path / "prep-flow" / "pipeline.json"
        before = record.read_bytes() if record.exists() else None
        status, _, raw = active.request(
            "POST",
            "/api/flow/edit-material",
            body=json.dumps(_edit_payload({"id": "a" * 32, "revision": "r"})).encode(),
            headers=active.write_headers(),
        )
        assert status == 409 and json.loads(raw)["error"] == "flow_worker_unavailable", raw
        assert (record.read_bytes() if record.exists() else None) == before


RESUME_EDIT_ROUTES = {
    "begin-automatic-edit": {},
    "save-automatic-source": {
        "expected_source_revision": "f" * 64,
        "latex_source": "\\documentclass{article}\\begin{document}Edit\\end{document}",
    },
    "begin-prism-edit": {},
    "finish-prism-edit": {},
    "capture-prism-result": {},
}


@pytest.mark.parametrize("route", sorted(RESUME_EDIT_ROUTES))
def test_resume_edit_during_filling_waits_for_confirmed_stop(backend, tmp_path, route):
    owner, _reopen, _runner, _page = backend
    pipeline, flow, worker = (
        owner.application_pipeline_service,
        owner.application_flow_service,
        owner.worker_service,
    )
    identifier = _claimed_codex(owner)
    task = flow.task_snapshot(pipeline.snapshot()["active_task_id"])
    body = json.dumps(
        {"task_id": task["id"], "task_revision": task["revision"]} | RESUME_EDIT_ROUTES[route]
    ).encode()
    flow_bytes = flow.path.read_bytes()
    client, thread = _served(owner, tmp_path)
    try:
        status, _, raw = client.request(
            "POST", "/api/flow/" + route, body=body, headers=client.write_headers()
        )
        assert status == 409 and json.loads(raw)["error"] == "material_edit_stopping", raw
        assert flow.path.read_bytes() == flow_bytes
        assistance = worker.store.load()["jobs"][0]["assistance"]
        assert assistance["stop"]["reason"] == "user_paused"
        assert "material_edit_gate" not in pipeline.snapshot()
        worker.record_assistance_stop(
            identifier,
            worker.assistance_context(identifier)["assistance_ref"],
            {
                "tools_revoked": True,
                "local_tools_drained": True,
                "process_stopped": True,
                "native_turn_id": None,
                "native_turn_status": "idle",
                "stop_status": "stopped",
            },
            request_id=assistance["stop"]["request_id"],
        )
        status, _, raw = client.request(
            "POST", "/api/flow/" + route, body=body, headers=client.write_headers()
        )
        gate = pipeline.snapshot().get("material_edit_gate")
    finally:
        owner.shutdown()
        thread.join(timeout=2)
    # After the confirmed stop the route reaches its unchanged Flow checks.
    assert status != 409 or json.loads(raw)["error"] != "material_edit_stopping", raw
    assert gate["task_id"] == task["id"] and gate["page_id"] == "original-page"


def test_edit_gate_reports_a_pending_intent_while_stopping(backend):
    owner, _reopen, _runner, _page = backend
    pipeline, flow, worker = (
        owner.application_pipeline_service,
        owner.application_flow_service,
        owner.worker_service,
    )
    state = worker.store.load()
    state["jobs"][0]["intent"] = {"action": "fill", "attempt_id": "unknown-fill"}
    worker.store.save(state)
    task = flow.task_snapshot(pipeline.snapshot()["active_task_id"])
    try:
        gate = pipeline.begin_material_edit(task["id"], task["revision"], request_id="intent")
    finally:
        owner.server_close()
    assert gate == {"edit_gate": "stopping", "edit_gate_reason": "pending_intent"}
    assert "material_edit_gate" not in pipeline.snapshot()


def test_repeated_edit_gate_rechecks_that_the_worker_is_still_stopped(backend):
    owner, _reopen, _runner, _page = backend
    pipeline, flow, worker = (
        owner.application_pipeline_service,
        owner.application_flow_service,
        owner.worker_service,
    )
    task = flow.task_snapshot(pipeline.snapshot()["active_task_id"])
    try:
        assert pipeline.begin_material_edit(
            task["id"], task["revision"], request_id="gate-repeat"
        ) == {"edit_gate": "ready"}
        state = worker.store.load()
        state["control"] = "running"
        worker.store.save(state)
        again = pipeline.begin_material_edit(task["id"], task["revision"], request_id="gate-repeat")
    finally:
        owner.server_close()
    assert again == {"edit_gate": "stopping", "edit_gate_reason": "worker_running"}
    assert "material_edit_gate" not in pipeline.snapshot()
