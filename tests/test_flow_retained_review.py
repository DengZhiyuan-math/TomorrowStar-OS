"""A second control server can hand off an existing synthetic page without flow ownership."""

import json
import subprocess
import time
from copy import deepcopy

import pytest
from test_application_single_binding import bound_single

from career_evidence_graph.application_worker import digest, start_run
from career_evidence_graph.career_portal import create_server


@pytest.fixture
def retained_flow(tmp_path, monkeypatch):
    applications, root, career, _, _ = bound_single.__wrapped__(tmp_path)
    subprocess.run(["git", "init", "--quiet", str(career)], check=True)
    path = root / "flow.json"
    state = json.loads(path.read_text())
    task = state["tasks"][0]
    task.update(
        status="materials_ready",
        worker_ref=None,
        stages={"analysis": {"status": "complete"}, "resume": {"status": "complete"}},
    )
    task["revision"] = digest({k: v for k, v in task.items() if k != "revision"})
    path.write_text(json.dumps(state))
    servers = []
    try:
        owner = create_server(
            applications.root,
            career,
            write_admission_policy="development",
            flow_root=root,
            worker_root=tmp_path / "worker",
            worker_live=True,
        )
        servers.append(owner)
        task = owner.application_flow_service.prepare_worker(
            task["id"], task["revision"], "CHE", True
        )
        worker = owner.worker_service
        run_id = start_run(worker.store)
        current = worker.store.load()
        job = current["jobs"][0]
        job.update(
            status="needs_recheck",
            reason="action_result_unknown",
            page_open=False,
            intent={"action": "open", "attempt_id": "synthetic-open", "run_id": run_id},
            page_observation={
                "run_id": run_id,
                "page_id": "synthetic-retained-page",
                "event": "observed",
                "at": time.time(),
            },
        )
        worker.store.save(current)
        observer = create_server(
            applications.root,
            career,
            write_admission_policy="development",
            flow_root=root,
            worker_root=tmp_path / "worker",
            worker_live=True,
        )
        servers.append(observer)
        for server in servers:
            monkeypatch.setattr(
                server.worker_service,
                "spawn",
                lambda: pytest.fail("Review must not start a worker"),
            )
        yield owner, observer, task
    finally:
        for server in reversed(servers):
            server.server_close()


def assert_current_review(result, prepared, worker):
    """Page fields come from Worker; material identity and revision stay retained."""
    assert {key: value for key, value in result.items() if key not in {"status", "worker_ref"}} == {
        key: value for key, value in prepared.items() if key not in {"status", "worker_ref"}
    }
    current = worker.store.load()
    job = current["jobs"][0]
    assert result["status"] == "needs_recheck"
    assert result["worker_ref"] == {
        "batch_id": current["batch_id"],
        "job_id": job["application_id"],
        "status": "needs_recheck",
        "reason": "action_result_unknown",
        "handed_off": True,
        "page_open": bool(job["page_open"]),
    }


def test_second_flow_service_reviews_existing_page_without_writing_flow(retained_flow):
    owner, observer, task = retained_flow
    flow = observer.application_flow_service
    assert owner.application_flow_service._owner and not flow._owner
    before = flow.path.read_bytes()
    pending = deepcopy(observer.worker_service.store.load()["jobs"][0]["intent"])

    result = flow.request(
        "worker-action",
        {
            "task_id": task["id"],
            "task_revision": task["revision"],
            "operation": "review",
            "payload": {"application_id": task["application_id"], "acknowledge": True},
        },
    )

    assert_current_review(result, task, observer.worker_service)
    assert flow.path.read_bytes() == before
    assert flow._thread is None and flow._queue.empty()
    worker = observer.worker_service.store.load()
    assert worker["control"] == "paused"
    assert worker["commands"] == [{"action": "review", "id": task["application_id"]}]
    assert worker["jobs"][0]["intent"] == pending
    assert worker["jobs"][0]["handed_off"] is True
    assert worker["jobs"][0]["handoff"]["run_id"] == worker["runtime"]["id"]


def test_observer_http_snapshot_shows_current_worker_without_saving_flow(retained_flow):
    from threading import Thread

    from test_career_portal_http import Portal

    owner, observer, task = retained_flow
    thread = Thread(target=observer.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True)
    thread.start()
    try:
        active = Portal(
            observer,
            owner.worker_service.store.applications.root,
            observer.worker_service.store.single_career_root,
        )
        before = observer.application_flow_service.path.read_bytes()
        status, _, raw = active.request("GET", "/api/flow/state")
        shown = json.loads(raw)
        assert status == 200
        assert shown["worker"]["enabled"] is True, shown["worker"]
        assert shown["worker"]["jobs"][0]["status"] == "needs_recheck"
        assert shown["worker"]["jobs"][0]["page_current"] is True
        assert shown["active_task"]["revision"] == task["revision"]
        assert observer.application_flow_service.path.read_bytes() == before
        request = {
            "task_id": task["id"],
            "task_revision": task["revision"],
            "operation": "review",
            "payload": {"acknowledge": True},
        }
        status, _, raw = active.request(
            "POST",
            "/api/flow/worker-action",
            body=json.dumps(request).encode(),
            headers=active.write_headers(),
        )
        assert status == 200
        assert_current_review(json.loads(raw), task, observer.worker_service)
        assert observer.worker_service.store.load()["commands"] == [
            {"action": "review", "id": task["application_id"]}
        ]
        request["operation"] = "recheck"
        status, _, raw = active.request(
            "POST",
            "/api/flow/worker-action",
            body=json.dumps(request).encode(),
            headers=active.write_headers(),
        )
        assert status == 409 and json.loads(raw)["error"] == "flow_runtime_busy"
        observed = observer.worker_service.store.load()
        observed["jobs"][0]["handoff"]["status"] = "complete"
        observer.worker_service.store.save(observed)
        status, _, raw = active.request("GET", "/api/flow/state")
        shown = json.loads(raw)
        assert status == 200 and shown["worker"]["jobs"][0]["handoff"]["status"] == "complete"
        assert shown["active_task"]["revision"] == task["revision"]
        assert observer.application_flow_service.path.read_bytes() == before
    finally:
        observer.shutdown()
        thread.join(timeout=3)


@pytest.mark.parametrize(
    "operation",
    [
        "resume",
        "pause",
        "heartbeat",
        "answer",
        "recheck",
        "release",
        "retry-sync",
        "resolve-action",
        "cancel-job",
        "settle-cancelled",
    ],
)
def test_observer_rejects_every_other_worker_operation(retained_flow, operation):
    from career_evidence_graph.career_portal_data import PortalDataError

    _, observer, task = retained_flow
    flow, worker = observer.application_flow_service, observer.worker_service
    before = flow.path.read_bytes(), worker.store.path.read_bytes()
    with pytest.raises(PortalDataError) as error:
        flow.request(
            "worker-action",
            {
                "task_id": task["id"],
                "task_revision": task["revision"],
                "operation": operation,
                "payload": {"application_id": task["application_id"]},
            },
        )
    assert error.value.code == "flow_runtime_busy"
    assert (flow.path.read_bytes(), worker.store.path.read_bytes()) == before
    assert flow._queue.empty()


@pytest.mark.parametrize(
    "action,extra",
    [
        ("start", {"stage": "analysis"}),
        ("cancel", {}),
        ("update-inputs", {"application_revision": "synthetic"}),
        ("confirm-materials", {"resume_id": "synthetic", "resume_sha256": "a" * 64}),
        (
            "clarify-condition",
            {"requirement_index": 0, "eligible": True, "source": "Synthetic fact"},
        ),
        ("prepare-worker", {"country": "CHE", "send_confirmed": True}),
    ],
)
def test_observer_cannot_mutate_or_start_flow_work(retained_flow, action, extra):
    from career_evidence_graph.career_portal_data import PortalDataError

    _, observer, task = retained_flow
    flow = observer.application_flow_service
    before = flow.path.read_bytes(), observer.worker_service.store.path.read_bytes()
    with pytest.raises(PortalDataError) as error:
        flow.request(action, {"task_id": task["id"], "task_revision": task["revision"], **extra})
    assert error.value.code == "flow_runtime_busy"
    assert (flow.path.read_bytes(), observer.worker_service.store.path.read_bytes()) == before
    assert flow._queue.empty()


@pytest.mark.parametrize(
    "mutation,code",
    [
        ("task_revision", "conflict"),
        ("worker_batch", "flow_worker_mismatch"),
        ("worker_task", "flow_worker_mismatch"),
        ("approved_pdf", "flow_materials_changed"),
        ("worker_pdf", "file_changed"),
        ("inputs", "single_binding_invalid"),
        ("closed", "flow_runtime_busy"),
        ("runtime_error", "synthetic_runtime_error"),
        ("page_closed", "not_ready"),
    ],
)
def test_observer_review_keeps_all_existing_guards(retained_flow, mutation, code):
    from pathlib import Path

    from career_evidence_graph.career_portal_data import PortalDataError

    _, observer, task = retained_flow
    flow, worker = observer.application_flow_service, observer.worker_service
    revision = task["revision"]
    if mutation == "task_revision":
        revision = "0" * 64
    elif mutation in {"worker_batch", "worker_task", "page_closed"}:
        state = worker.store.load()
        if mutation == "worker_batch":
            state["batch_id"] = "f" * 32
        elif mutation == "worker_task":
            state["jobs"][0]["single_binding"]["task_id"] = "e" * 32
        else:
            state["jobs"][0]["page_observation"]["event"] = "page_closed"
        worker.store.save(state)
    elif mutation == "approved_pdf":
        (flow.root / "resumes" / task["resume_id"] / "resume.pdf").write_bytes(b"%PDF-1.4 changed")
    elif mutation == "worker_pdf":
        Path(worker.store.load()["jobs"][0]["file_path"]).write_bytes(b"%PDF-1.4 changed")
    elif mutation == "inputs":
        application = worker.store.applications.get_application(task["application_id"])
        worker.store.applications.update_application(
            application["id"], {"job_description": "Changed synthetic JD."}, application["revision"]
        )
    elif mutation == "closed":
        flow.close()
    elif mutation == "runtime_error":
        flow._runtime_error = "synthetic_runtime_error"
    before = flow.path.read_bytes()
    with pytest.raises(PortalDataError) as error:
        flow.worker_action(task["id"], revision, "review", {"acknowledge": True})
    assert error.value.code == code
    assert flow.path.read_bytes() == before
    current = worker.store.load()
    assert current["commands"] == []
    assert current["jobs"][0]["handed_off"] is False
    assert current["jobs"][0]["intent"]["attempt_id"] == "synthetic-open"


def test_observer_cannot_create_another_flow_task(retained_flow):
    from career_evidence_graph.career_portal_data import PortalDataError

    _, observer, task = retained_flow
    flow = observer.application_flow_service
    app = observer.worker_service.store.applications.get_application(task["application_id"])
    before = flow.path.read_bytes()
    with pytest.raises(PortalDataError) as error:
        flow.request(
            "create", {"application_id": app["id"], "application_revision": app["revision"]}
        )
    assert error.value.code == "flow_runtime_busy"
    assert flow.path.read_bytes() == before and flow._queue.empty()


@pytest.mark.parametrize(
    "mutation,code",
    [
        ("worker_batch", "flow_worker_mismatch"),
        ("worker_task", "flow_worker_mismatch"),
        ("closed", "flow_runtime_busy"),
        ("runtime_error", "synthetic_runtime_error"),
    ],
)
def test_observer_snapshot_does_not_hide_real_errors(retained_flow, mutation, code):
    from threading import Thread

    from test_career_portal_http import Portal

    owner, observer, _ = retained_flow
    flow, worker = observer.application_flow_service, observer.worker_service
    if mutation in {"worker_batch", "worker_task"}:
        state = worker.store.load()
        if mutation == "worker_batch":
            state["batch_id"] = "f" * 32
        else:
            state["jobs"][0]["single_binding"]["task_id"] = "e" * 32
        worker.store.save(state)
    elif mutation == "closed":
        flow.close()
    else:
        flow._runtime_error = "synthetic_runtime_error"
    before = flow.path.read_bytes()
    thread = Thread(target=observer.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True)
    thread.start()
    try:
        active = Portal(
            observer, owner.worker_service.store.applications.root, worker.store.single_career_root
        )
        status, _, raw = active.request("GET", "/api/flow/state")
        shown = json.loads(raw)
        assert status == 200 and shown["worker"]["enabled"] is False
        assert shown["worker"]["error"] == code
        assert flow.path.read_bytes() == before
    finally:
        observer.shutdown()
        thread.join(timeout=3)


def test_retained_review_does_not_age_page_while_repeating_flow_input_scan(
    retained_flow, monkeypatch
):
    from threading import Event, Thread

    owner, observer, task = retained_flow
    flow, worker = observer.application_flow_service, observer.worker_service
    before_flow = flow.path.read_bytes()
    before = worker.store.load()
    pending = deepcopy(before["jobs"][0]["intent"])
    clock = [before["runtime"]["observed_at"]]
    monkeypatch.setattr("career_evidence_graph.application_worker.time.time", lambda: clock[0])
    original_inputs = flow.input_provider
    waiting, refreshed = Event(), Event()
    heartbeat = []

    def refresh_retained_page():
        waiting.set()
        with owner.worker_service.store.applications.write_lock():
            state = owner.worker_service.store.load()
            state["runtime"]["observed_at"] = clock[0]
            state["jobs"][0]["page_observation"]["at"] = clock[0]
            owner.worker_service.store.save(state)
            refreshed.set()

    def expensive_inputs(application_id):
        thread = Thread(target=refresh_retained_page, daemon=True)
        heartbeat.append(thread)
        thread.start()
        assert waiting.wait(1)
        # The separate worker cannot refresh its observation under the flow lock.
        assert not refreshed.wait(0.02)
        clock[0] += 9.5
        return original_inputs(application_id)

    flow.input_provider = expensive_inputs
    try:
        result = flow.request(
            "worker-action",
            {
                "task_id": task["id"],
                "task_revision": task["revision"],
                "operation": "review",
                "payload": {"acknowledge": True},
            },
        )
        assert_current_review(result, task, observer.worker_service)
        current = worker.store.load()
        assert current["commands"] == [{"action": "review", "id": task["application_id"]}]
        assert current["jobs"][0]["handed_off"] is True
        assert current["jobs"][0]["intent"] == pending
        assert flow.path.read_bytes() == before_flow
    finally:
        for thread in heartbeat:
            thread.join(timeout=2)
            assert not thread.is_alive()


def test_existing_worker_validates_slow_materials_after_fresh_page_gate(retained_flow, monkeypatch):
    from threading import Thread

    from test_career_portal_http import Portal

    from career_evidence_graph.application_single_binding import check_single_binding

    _, observer, task = retained_flow
    flow, worker = observer.application_flow_service, observer.worker_service
    before = worker.store.load()
    clock = [before["runtime"]["observed_at"]]
    monkeypatch.setattr("career_evidence_graph.application_worker.time.time", lambda: clock[0])
    checked = []

    def slow_full_check(*args, **kwargs):
        check_single_binding(*args, **kwargs)
        checked.append(True)
        clock[0] += 9.5

    worker.store.single_validator = slow_full_check
    before_flow = flow.path.read_bytes()
    thread = Thread(target=observer.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True)
    thread.start()
    try:
        active = Portal(observer, worker.store.applications.root, worker.store.single_career_root)
        status, _, raw = active.request(
            "POST",
            "/api/flow/worker-action",
            body=json.dumps(
                {
                    "task_id": task["id"],
                    "task_revision": task["revision"],
                    "operation": "review",
                    "payload": {"acknowledge": True},
                }
            ).encode(),
            headers=active.write_headers(),
        )
        assert status == 200, raw
        result = json.loads(raw)
    finally:
        observer.shutdown()
        thread.join(timeout=3)
    current = worker.store.load()
    assert checked == [True]
    assert_current_review(result, task, worker)
    assert current["jobs"][0]["handoff"]["at"] - before["runtime"]["observed_at"] == 9.5
    assert current["commands"] == [{"action": "review", "id": task["application_id"]}]
    assert current["jobs"][0]["intent"] == before["jobs"][0]["intent"]
    assert flow.path.read_bytes() == before_flow


@pytest.mark.parametrize("mutation", ["sources", "configuration", "stale_page"])
def test_review_still_checks_real_bound_inputs_and_current_page(
    retained_flow, monkeypatch, mutation
):
    from career_evidence_graph.career_portal_data import PortalDataError

    _, observer, task = retained_flow
    flow, worker = observer.application_flow_service, observer.worker_service
    if mutation == "sources":
        sources = worker.store.single_career_root / "sources"
        sources.mkdir(exist_ok=True)
        (sources / "profile.md").write_text("Synthetic changed career source.")
    elif mutation == "configuration":
        monkeypatch.setenv("TOMORROWSTAR_CODEX_EXECUTABLE", "/synthetic-missing/codex")
    else:
        state = worker.store.load()
        state["runtime"]["observed_at"] -= 9.5
        worker.store.save(state)
    before = flow.path.read_bytes()
    pdf_path = flow.root / "resumes" / task["resume_id"] / "resume.pdf"
    original_pdf = pdf_path.read_bytes()
    if mutation in {"configuration", "sources"}:
        # Review reuses already completed bytes and their original model binding;
        # a career source revision never invalidates them (APP-04).
        result = flow.worker_action(task["id"], task["revision"], "review", {"acknowledge": True})
        assert_current_review(result, task, observer.worker_service)
    else:
        with pytest.raises(PortalDataError) as error:
            flow.worker_action(task["id"], task["revision"], "review", {"acknowledge": True})
        assert error.value.code == (
            "not_ready" if mutation == "stale_page" else "single_binding_invalid"
        )
    current = worker.store.load()
    if mutation in {"configuration", "sources"}:
        assert current["commands"] == [{"action": "review", "id": task["application_id"]}]
        assert current["jobs"][0]["handed_off"] is True
    else:
        assert current["commands"] == [] and current["jobs"][0]["handed_off"] is False
    assert current["jobs"][0]["intent"]["attempt_id"] == "synthetic-open"
    assert pdf_path.read_bytes() == original_pdf
    assert flow.path.read_bytes() == before
