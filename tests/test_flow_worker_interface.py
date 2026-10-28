"""Default Portal consumers cross Flow and Worker through their owned interfaces."""

import pytest
from test_portal_qualification_consumption import qualification_case
from test_worker_backend_recovery import backend as backend

from career_evidence_graph.career_portal import create_server
from career_evidence_graph.career_portal_data import PortalDataError


def test_default_portal_prepares_through_worker_execution_interface(tmp_path, monkeypatch):
    apps, root, career, task = qualification_case(tmp_path, "not_specified")
    with create_server(
        apps.root, career, flow_root=root, worker_root=tmp_path / "worker", worker_live=True
    ) as server:
        worker = server.worker_service
        original = worker.prepare_execution
        deliveries = []

        def prepare(application_id, revision, binding, *, pdf_reader):
            deliveries.append((application_id, revision, binding))
            return original(application_id, revision, binding, pdf_reader=pdf_reader)

        monkeypatch.setattr(worker, "prepare_execution", prepare)
        prepared = server.application_flow_service.prepare_worker(
            task["id"], task["revision"], "CHE", True
        )
        assert len(deliveries) == 1
        assert deliveries[0][0] == task["application_id"]
        assert deliveries[0][2]["task_id"] == task["id"]
        assert set(prepared["worker_ref"]) == {
            "batch_id",
            "job_id",
            "status",
            "reason",
            "handed_off",
            "page_open",
        }
        saved = server.application_flow_service.witness(task["id"])[1]
        assert set(saved["worker_ref"]) == {"batch_id", "job_id"}


def test_pipeline_skip_return_uses_default_selection_interface_and_retains_original_page(
    backend, monkeypatch
):
    owner, _reopen, runner, page = backend
    pipeline, worker = owner.application_pipeline_service, owner.worker_service
    policy = pipeline._load()
    task = owner.application_flow_service.task_snapshot(policy["active_task_id"])
    policy["items"] = [
        {
            "recommendation_id": policy["current_recommendation_id"],
            "application_id": task["application_id"],
            "task_id": task["id"],
            "status": "filling",
            "score": None,
        }
    ]
    pipeline._save(policy)
    before = worker.store.load()
    original = before["jobs"][0]
    original["intent"] = {"action": "upload", "attempt_id": "unknown-before-selection"}
    worker.store.save(before)
    select = worker.select_execution
    calls = []

    def selected(reference, operation, payload):
        calls.append(operation)
        return select(reference, operation, payload)

    monkeypatch.setattr(worker, "select_execution", selected)
    pipeline.skip_current(request_id="skip-default-interface")
    assert worker.store.load()["current_job_id"] is None
    returned = pipeline.return_to(task["application_id"], request_id="return-default-interface")
    after = worker.store.load()
    assert calls == ["skip-current", "select-current"]
    assert after["current_job_id"] == task["application_id"]
    assert after["jobs"][0] == original
    assert after["runtime"]["id"] == before["runtime"]["id"]
    assert runner.pages[task["application_id"]] is page
    assert returned["control"] == "paused"


def test_default_flow_reads_and_controls_through_worker_interfaces(backend, monkeypatch):
    owner, _reopen, _runner, _page = backend
    flow, worker = owner.application_flow_service, owner.worker_service
    task_id = owner.application_pipeline_service.snapshot()["active_task_id"]
    read, control = worker.execution_reference, worker.control_execution
    reads, commands = [], []

    def reference(application_id, task_id, **options):
        reads.append((application_id, task_id, options))
        return read(application_id, task_id, **options)

    def controlled(reference, operation, payload):
        commands.append((reference, operation, payload))
        return control(reference, operation, payload)

    monkeypatch.setattr(worker, "execution_reference", reference)
    monkeypatch.setattr(worker, "control_execution", controlled)
    before = flow.path.read_bytes()
    task = flow.task_snapshot(task_id)
    assert reads and reads[0][1] == task_id
    paused = flow.worker_action(
        task_id,
        task["revision"],
        "pause",
        {"application_id": task["application_id"], "controller": "pipeline-controller"},
    )
    assert len(commands) == 1
    assert commands[0][0]["task_id"] == task_id
    assert commands[0][0]["run_id"] == worker.store.load()["runtime"]["id"]
    assert commands[0][1:] == ("pause", {"controller": "pipeline-controller"})
    assert paused["worker_ref"]["batch_id"] == task["worker_ref"]["batch_id"]
    assert flow.path.read_bytes() == before


def test_default_flow_preserves_legacy_mismatch_error_for_stale_worker_scope(backend):
    owner, _reopen, _runner, _page = backend
    flow = owner.application_flow_service
    task = flow.witness(flow.snapshot()["active_task"]["id"])[1]
    task["worker_ref"]["batch_id"] = "different-batch"
    before = owner.worker_service.store.load()
    with pytest.raises(PortalDataError) as error:
        flow.callbacks["worker_reference"](task)
    assert error.value.code == "flow_worker_mismatch"
    assert owner.worker_service.store.load() == before
