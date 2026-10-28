"""Worker owns fixed execution references and reuses unpublished preparation."""

import json
from copy import deepcopy
from pathlib import Path

import pytest
from test_application_single_binding import make_bound_single
from test_single_application_worker import single_worker as single_worker

from career_evidence_graph.application_worker import WorkerService, digest
from career_evidence_graph.career_portal_data import PortalDataError


def test_execution_reference_reads_fixed_scope_without_creating_work(single_worker):
    service, item, _checks, launches = single_worker
    service.request("prepare", {"workflow": "single", "send_confirmed": True, "jobs": [item]})
    state = service.store.load()
    roots = [service.store.root, service.store.applications.root]
    before = {
        str(path): path.read_bytes() for root in roots for path in root.rglob("*") if path.is_file()
    }

    result = service.execution_reference(item["application_id"], "synthetic-task")

    assert result == {
        "reference": {
            "application_id": item["application_id"],
            "task_id": "synthetic-task",
            "batch_id": state["batch_id"],
            "run_id": None,
        },
        "view": {
            "status": "queued",
            "reason": "",
            "handed_off": False,
            "page_open": False,
            "control": "paused",
            "current": True,
        },
    }
    assert all(Path(path).read_bytes() == raw for path, raw in before.items())
    assert launches == []


@pytest.fixture
def unpublished_execution(tmp_path):
    applications, flow, career, frozen, _batch = make_bound_single(tmp_path)
    path = flow / "flow.json"
    state = json.loads(path.read_text())
    task = state["tasks"][0]
    task.update(worker_ref=None, status="materials_ready")
    task["revision"] = digest({k: v for k, v in task.items() if k != "revision"})
    path.write_text(json.dumps(state))
    service = WorkerService(
        applications,
        tmp_path / "worker",
        fixture_origin="http://127.0.0.1:9999",
        single_flow_root=flow,
        single_career_root=career,
    )
    app = applications.get_application(frozen["application_id"])
    calls = []

    def pdf_reader(resume_id):
        calls.append(resume_id)
        return (flow / "resumes" / resume_id / "resume.pdf").read_bytes()

    return service, app, frozen["single_binding"], pdf_reader, calls


def test_prepare_execution_reads_pdf_only_for_new_unopened_preparation(unpublished_execution):
    service, app, binding, reader, calls = unpublished_execution
    result = service.prepare_execution(app["id"], app["revision"], binding, pdf_reader=reader)
    assert result == service.execution_reference(app["id"], binding["task_id"])
    assert calls == [binding["resume_id"]]
    before = service.store.load()
    pdf = Path(before["jobs"][0]["file_path"]).read_bytes()

    def forbidden(_resume_id):
        pytest.fail("unpublished preparation must reuse its retained PDF")

    retry = service.prepare_execution(app["id"], app["revision"], binding, pdf_reader=forbidden)
    assert retry == result
    assert service.store.load() == before
    assert Path(before["jobs"][0]["file_path"]).read_bytes() == pdf


def test_control_execution_uses_fixed_scope_and_original_control_rules(single_worker):
    service, item, _checks, launches = single_worker
    service.request("prepare", {"workflow": "single", "send_confirmed": True, "jobs": [item]})
    reference = service.execution_reference(item["application_id"], "synthetic-task")["reference"]
    payload = {"controller": "synthetic-controller"}
    result = service.control_execution(reference, "resume", payload)
    assert result["view"]["control"] == "running"
    assert launches == [True]
    assert payload == {"controller": "synthetic-controller"}
    service.control_execution(reference, "pause", payload)
    assert service.store.load()["control"] == "paused"


@pytest.mark.parametrize("field", ["batch_id", "task_id", "run_id", "application_id"])
def test_stale_control_reference_does_not_change_execution(single_worker, field):
    service, item, _checks, launches = single_worker
    service.request("prepare", {"workflow": "single", "send_confirmed": True, "jobs": [item]})
    reference = service.execution_reference(item["application_id"], "synthetic-task")["reference"]
    reference[field] = "stale-reference"
    before = service.store.load()
    with pytest.raises(PortalDataError):
        service.control_execution(reference, "resume", {"controller": "synthetic-controller"})
    assert service.store.load() == before
    assert launches == []


def test_unstarted_control_reference_cannot_control_a_new_run(single_worker):
    from career_evidence_graph.application_worker import start_run

    service, item, _checks, _launches = single_worker
    service.request("prepare", {"workflow": "single", "send_confirmed": True, "jobs": [item]})
    reference = service.execution_reference(item["application_id"], "synthetic-task")["reference"]
    start_run(service.store)
    before = service.store.load()
    with pytest.raises(PortalDataError, match="执行任务或原运行已改变"):
        service.control_execution(reference, "resume", {"controller": "synthetic-controller"})
    assert service.store.load() == before


@pytest.mark.parametrize(
    "operation",
    ["prepare", "cancel", "library", "skip-current", "select-current", "claim-assistance"],
)
def test_execution_control_cannot_change_batch_selection_or_authority(single_worker, operation):
    service, item, _checks, _launches = single_worker
    service.request("prepare", {"workflow": "single", "send_confirmed": True, "jobs": [item]})
    reference = service.execution_reference(item["application_id"], "synthetic-task")["reference"]
    before = service.store.load()
    with pytest.raises(PortalDataError) as error:
        service.control_execution(reference, operation, {})
    assert error.value.code == "worker_control_invalid"
    assert service.store.load() == before


def test_execution_control_rejects_payload_application_override(single_worker):
    service, item, _checks, _launches = single_worker
    service.request("prepare", {"workflow": "single", "send_confirmed": True, "jobs": [item]})
    reference = service.execution_reference(item["application_id"], "synthetic-task")["reference"]
    before = service.store.load()
    with pytest.raises(PortalDataError):
        service.control_execution(reference, "pause", {"application_id": item["application_id"]})
    assert service.store.load() == before


@pytest.mark.parametrize("operation", ["resume", "pause", "heartbeat"])
def test_retained_reference_cannot_control_another_current_job(single_worker, operation):
    from test_application_worker import job

    service, item, _checks, _launches = single_worker
    service.request("prepare", {"workflow": "single", "send_confirmed": True, "jobs": [item]})
    reference = service.execution_reference(item["application_id"], "synthetic-task")["reference"]
    service.request(
        "skip-current", {"application_id": item["application_id"], "request_id": "skip-one"}
    )
    second = job(service, 2)
    second["single_binding"] = {"task_id": "second-task"}
    service.request("prepare", {"workflow": "single", "send_confirmed": True, "jobs": [second]})
    before = service.store.load()
    assert not service.execution_reference(item["application_id"], "synthetic-task")["view"][
        "current"
    ]
    with pytest.raises(PortalDataError):
        service.control_execution(reference, operation, {"controller": "synthetic-controller"})
    assert service.store.load() == before


@pytest.mark.parametrize("mutation", ["page", "intent", "running", "status"])
def test_prepare_execution_refuses_replay_of_started_or_uncertain_work(
    unpublished_execution, mutation
):
    service, app, binding, reader, calls = unpublished_execution
    service.prepare_execution(app["id"], app["revision"], binding, pdf_reader=reader)
    state = service.store.load()
    if mutation == "page":
        state["jobs"][0]["page_open"] = True
    elif mutation == "intent":
        state["jobs"][0]["intent"] = {"action": "fill", "attempt_id": "unresolved"}
    elif mutation == "running":
        state["control"] = "running"
    else:
        state["jobs"][0]["status"] = "needs_recheck"
    service.store.save(state)
    before = service.store.load()
    with pytest.raises(PortalDataError):
        service.prepare_execution(app["id"], app["revision"], binding, pdf_reader=reader)
    assert calls == [binding["resume_id"]]
    assert service.store.load() == before


def test_prepare_execution_reuses_publication_after_lost_response(
    unpublished_execution, monkeypatch
):
    service, app, binding, reader, calls = unpublished_execution
    original = service.snapshot

    def lost_response():
        raise OSError("synthetic response lost after publication")

    monkeypatch.setattr(service, "snapshot", lost_response)
    with pytest.raises(OSError, match="response lost"):
        service.prepare_execution(app["id"], app["revision"], binding, pdf_reader=reader)
    before = service.store.load()
    monkeypatch.setattr(service, "snapshot", original)
    result = service.prepare_execution(app["id"], app["revision"], binding, pdf_reader=reader)
    assert result["reference"]["batch_id"] == before["batch_id"]
    assert calls == [binding["resume_id"]]
    assert service.store.load() == before


def test_prepare_execution_rechecks_saved_materials_before_reuse(unpublished_execution):
    service, app, binding, reader, calls = unpublished_execution
    service.prepare_execution(app["id"], app["revision"], binding, pdf_reader=reader)
    path = service.store.single_career_root / "contributions"
    path.mkdir()
    (path / "changed.md").write_text("# Changed synthetic source\n\n## Scope\nNew evidence.")
    before = service.store.load()
    with pytest.raises(PortalDataError) as error:
        service.prepare_execution(app["id"], app["revision"], binding, pdf_reader=reader)
    assert error.value.code == "single_binding_invalid"
    assert service.store.load() == before
    assert calls == [binding["resume_id"]]


def test_execution_reference_missing_job_is_read_only(single_worker):
    service, item, _checks, _launches = single_worker
    root = service.store.applications.root.parent
    before = {str(path): path.read_bytes() for path in root.rglob("*") if path.is_file()}
    directories = {str(path) for path in root.rglob("*") if path.is_dir()}
    with pytest.raises(PortalDataError):
        service.execution_reference(item["application_id"], "synthetic-task")
    assert {str(path): path.read_bytes() for path in root.rglob("*") if path.is_file()} == before
    assert {str(path) for path in root.rglob("*") if path.is_dir()} == directories


def test_execution_reference_rejects_legacy_unbound_job_without_migrating(single_worker):
    service, item, _checks, _launches = single_worker
    service.request("prepare", {"workflow": "single", "send_confirmed": True, "jobs": [item]})
    state = service.store.load()
    state["jobs"][0].pop("single_binding")
    state["jobs"][0].pop("workflow")
    state.pop("single_context")
    state.pop("current_job_id")
    service.store.save(state)
    before = service.store.load()
    with pytest.raises(PortalDataError):
        service.execution_reference(item["application_id"], "synthetic-task")
    assert service.store.load() == before


def test_older_single_task_without_selection_metadata_retains_control(single_worker):
    service, item, _checks, launches = single_worker
    service.request("prepare", {"workflow": "single", "send_confirmed": True, "jobs": [item]})
    state = service.store.load()
    state.pop("current_job_id")
    service.store.save(state)
    result = service.execution_reference(item["application_id"], "synthetic-task")
    assert result["view"]["current"]
    resumed = service.control_execution(
        result["reference"], "resume", {"controller": "synthetic-controller"}
    )
    assert resumed["view"]["control"] == "running"
    assert launches == [True]


def test_selection_interface_preserves_original_skip_and_return(single_worker):
    service, item, _checks, _launches = single_worker
    service.request("prepare", {"workflow": "single", "send_confirmed": True, "jobs": [item]})
    reference = service.execution_reference(item["application_id"], "synthetic-task")["reference"]
    skipped = service.select_execution(reference, "skip-current", {"request_id": "skip-one"})
    assert not skipped["view"]["current"]
    returned = service.select_execution(reference, "select-current", {"request_id": "return-one"})
    assert returned["view"]["current"]
    assert returned["view"]["control"] == "paused"
    before = service.store.load()
    with pytest.raises(PortalDataError):
        service.select_execution(reference, "cancel", {})
    reference["run_id"] = "stale-run"
    with pytest.raises(PortalDataError):
        service.select_execution(reference, "skip-current", {"request_id": "stale-skip"})
    assert service.store.load() == before


def test_execution_view_is_detached_and_pause_does_not_require_fresh_materials(single_worker):
    service, item, _checks, _launches = single_worker
    service.request("prepare", {"workflow": "single", "send_confirmed": True, "jobs": [item]})
    service.request("resume", {"controller": "synthetic-controller"})
    result = service.execution_reference(item["application_id"], "synthetic-task")
    reference = deepcopy(result["reference"])
    result["reference"]["task_id"] = "caller-mutated"
    result["view"]["status"] = "caller-mutated"

    def stale(*_args, **_kwargs):
        raise PortalDataError("single_binding_invalid", "Synthetic materials changed.", 409)

    service.store.single_validator = stale
    paused = service.control_execution(reference, "pause", {"controller": "synthetic-controller"})
    assert paused["view"]["status"] == "queued"
    assert paused["view"]["control"] == "paused"
    assert paused["reference"]["task_id"] == "synthetic-task"


def test_prepare_execution_rejects_stale_revision_before_reading_pdf(unpublished_execution):
    service, app, binding, reader, calls = unpublished_execution
    before = service.store.load()
    with pytest.raises(PortalDataError):
        service.prepare_execution(app["id"], "0" * 64, binding, pdf_reader=reader)
    assert service.store.load() == before
    assert calls == []
