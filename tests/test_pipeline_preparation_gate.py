"""Preparation calls observe Pipeline control without changing its queue."""

import pytest
from test_application_resume import task_resume as task_resume
from test_bound_material_update import bound_pipeline as bound_pipeline
from test_full_latex_generation import full_latex as full_latex
from test_pipeline_current_job import current_pipeline as current_pipeline
from test_pipeline_recommendation_queue import drive

from career_evidence_graph.career_portal import pipeline_control
from career_evidence_graph.career_portal_data import PortalDataError


def test_preparation_gate_reuses_current_control_without_writes(current_pipeline):
    pipeline, _, _, worker = current_pipeline
    before = pipeline.path.read_bytes(), worker.store.path.read_bytes()
    assert pipeline.preparation_allowed("manual-task") is True
    assert (pipeline.path.read_bytes(), worker.store.path.read_bytes()) == before
    pipeline.start(request_id="preparation-gate-cycle")
    assert pipeline.preparation_allowed("manual-task") is False
    current = drive(pipeline, "filling")
    task_id = current["active_task_id"]
    before = pipeline.path.read_bytes(), worker.store.path.read_bytes()
    assert pipeline.preparation_allowed(task_id) is True
    assert pipeline.preparation_allowed("another-task") is False
    assert (pipeline.path.read_bytes(), worker.store.path.read_bytes()) == before
    pipeline.pause()
    before = pipeline.path.read_bytes(), worker.store.path.read_bytes()
    assert pipeline.preparation_allowed(task_id) is False
    assert (pipeline.path.read_bytes(), worker.store.path.read_bytes()) == before


def test_closed_pipeline_cannot_authorize_preparation(current_pipeline):
    pipeline, _, _, _ = current_pipeline
    pipeline.close()
    assert pipeline.preparation_allowed("manual-task") is False


def test_current_matching_task_can_prepare_before_active_task_publication(current_pipeline):
    pipeline, _, _, worker = current_pipeline
    pipeline.start(request_id="matching-preparation-scope")
    drive(pipeline, "matching")
    pipeline._tick()
    current = pipeline.snapshot()
    assert current["active_task_id"] is None
    assert current["status"] == "matching" and current["control"] == "running"
    item = next(row for row in current["items"] if row["status"] == "matching")
    before = pipeline.path.read_bytes(), worker.store.path.read_bytes()
    assert pipeline.preparation_allowed(item["task_id"]) is True
    assert pipeline.preparation_allowed("another-queued-task") is False
    assert pipeline.preparation_allowed(item["task_id"], refresh=("a" * 32, "opaque")) is False
    assert (pipeline.path.read_bytes(), worker.store.path.read_bytes()) == before
    pipeline.pause()
    assert pipeline.preparation_allowed(item["task_id"]) is False


def test_paused_refresh_permission_is_scoped_to_entry_and_control_generation(bound_pipeline):
    server, _, _ = bound_pipeline
    pipeline = server.application_pipeline_service
    current = pipeline.snapshot()
    pipeline.pause()
    task = pipeline.flow.task_snapshot(current["active_task_id"])
    request_id = "a" * 32
    payload = {
        "task_id": task["id"],
        "task_revision": task["revision"],
        "request_id": request_id,
    }
    ref = request_id, "opaque-verified-flow-intent"
    before = pipeline.path.read_bytes(), pipeline.flow.path.read_bytes()
    assert pipeline.preparation_allowed(task["id"], refresh=ref) is False
    with pipeline.manual_entry("flow:refresh-match", payload):
        assert pipeline.preparation_allowed(task["id"], refresh=ref) is True
        assert pipeline.preparation_allowed(task["id"]) is False
        assert pipeline.preparation_allowed("another-task", refresh=ref) is False
        assert pipeline.preparation_allowed(task["id"], refresh=("b" * 32, ref[1])) is False
        assert pipeline.preparation_allowed(task["id"], refresh=(request_id, "changed")) is False
        assert (pipeline.path.read_bytes(), pipeline.flow.path.read_bytes()) == before
        for action, invalid in (
            ("unknown-operation", {}),
            ("pause", {"unexpected": True}),
            ("continue", {}),
            ("cancel-current", {}),
        ):
            with pytest.raises(PortalDataError):
                pipeline_control(pipeline, action, invalid)
            assert pipeline.preparation_allowed(task["id"], refresh=ref) is True
        pipeline.capture_mail(request_id="refresh-mail-only")
        assert pipeline.preparation_allowed(task["id"], refresh=ref) is True
    assert pipeline.preparation_allowed(task["id"], refresh=ref) is False
    with pipeline.manual_entry("flow:refresh-match", payload):
        assert pipeline.preparation_allowed(task["id"], refresh=ref) is True
        pipeline.pause()
        assert pipeline.preparation_allowed(task["id"], refresh=ref) is False
