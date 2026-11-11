"""Paused control does not prove that a retained Codex tool has drained."""

from types import SimpleNamespace

import pytest
from test_single_application_worker import single_worker as single_worker
from test_worker_codex_assistance import retained_assistance_page as retained_assistance_page
from test_worker_codex_observation import owned_codex_page as owned_codex_page

from career_evidence_graph.application_bound_materials import paused_job
from career_evidence_graph.application_material_edit import edit_material
from career_evidence_graph.career_portal_data import PortalDataError


@pytest.mark.parametrize("stop_status", ["stopping", "unknown"])
def test_paused_bound_materials_wait_for_codex_drain(owned_codex_page, stop_status):
    worker, _, _, reference, _ = owned_codex_page
    worker.request("pause", {"controller": "synthetic-controller"})
    if stop_status == "unknown":
        stop = worker.store.load()["jobs"][0]["assistance"]["stop"]
        worker.record_assistance_stop(
            reference["binding"]["application_id"],
            reference,
            {
                "tools_revoked": True,
                "local_tools_drained": False,
                "process_stopped": False,
                "native_turn_id": None,
                "native_turn_status": "unknown",
                "stop_status": "unknown",
            },
            request_id=stop["request_id"],
        )
    current = worker.store.load()
    task = {
        "application_id": reference["binding"]["application_id"],
        "worker_ref": {"batch_id": current["batch_id"]},
    }
    flow = SimpleNamespace(
        check_available=lambda: None,
        callbacks={"bound_worker_state": worker.store.load},
    )
    before = worker.store.path.read_bytes()
    with pytest.raises(PortalDataError) as error:
        paused_job(flow, task)
    assert error.value.code == "bound_material_pause_required"
    assert worker.store.path.read_bytes() == before


def test_unavailable_flow_keeps_the_bound_material_pause_failure():
    def closed():
        raise PortalDataError("flow_runtime_busy", "Synthetic closed Flow", 409)

    flow = SimpleNamespace(
        check_available=closed,
        callbacks={"bound_worker_state": lambda: pytest.fail("Worker state is not read")},
    )
    with pytest.raises(PortalDataError) as error:
        paused_job(flow, {"application_id": "synthetic", "worker_ref": {}})
    assert error.value.code == "bound_material_pause_required"
    assert error.value.status == 409


def test_bound_materials_allow_confirmed_stop_without_releasing_the_writer(owned_codex_page):
    worker, _, _, reference, _ = owned_codex_page
    worker.request("pause", {"controller": "synthetic-controller"})
    stop = worker.store.load()["jobs"][0]["assistance"]["stop"]
    worker.record_assistance_stop(
        reference["binding"]["application_id"],
        reference,
        {
            "tools_revoked": True,
            "local_tools_drained": True,
            "process_stopped": True,
            "native_turn_id": None,
            "native_turn_status": "idle",
            "stop_status": "stopped",
        },
        request_id=stop["request_id"],
    )
    current = worker.store.load()
    flow = SimpleNamespace(
        check_available=lambda: None, callbacks={"bound_worker_state": worker.store.load}
    )
    before = worker.store.path.read_bytes()
    _, job = paused_job(
        flow,
        {
            "application_id": reference["binding"]["application_id"],
            "worker_ref": {"batch_id": current["batch_id"]},
        },
    )
    assert job["assistance"]["active_writer"] == "codex"
    assert worker.store.path.read_bytes() == before


def test_precise_material_editor_waits_for_codex_drain(owned_codex_page):
    worker, _, _, reference, _ = owned_codex_page
    worker.request("pause", {"controller": "synthetic-controller"})
    state = worker.store.load()
    task_id = "b" * 32
    task = {
        "id": task_id,
        "application_id": reference["binding"]["application_id"],
        "status": "materials_ready",
    }
    state["jobs"][0].update(
        status="needs_input",
        precision_preparation={
            "status": "ready",
            "task_id": task_id,
            "run_id": reference["binding"]["run_id"],
            "page_id": reference["binding"]["page_id"],
            "document_token": reference["binding"]["document_token"],
        },
    )
    worker.store.save(state)
    flow = SimpleNamespace(
        preparation_only=False,
        applications=worker.store.applications,
        writable_task=lambda *_: task,
    )
    payload = {
        "task_id": task_id,
        "task_revision": "current",
        "material_id": "c" * 32,
        "expected_text_sha256": "d" * 64,
        "request_id": "e" * 32,
        "text": "Synthetic edited letter.",
    }
    before = worker.store.path.read_bytes()
    with pytest.raises(PortalDataError) as error:
        edit_material(flow, worker, lambda *_: None, payload)
    assert error.value.code == "material_edit_pause_required"
    assert worker.store.path.read_bytes() == before
