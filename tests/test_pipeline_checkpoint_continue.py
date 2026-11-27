"""An App quit's Worker stop marker is lifted by the Continue that resumes materials."""

from contextlib import suppress

from test_pipeline_current_job import current_pipeline as current_pipeline
from test_pipeline_recommendation_queue import drive

from career_evidence_graph.career_portal_data import PortalDataError


def test_continue_into_materials_lifts_a_stop_an_app_quit_left(current_pipeline):
    # 2026-11-20 (Deloitte): the stop marker refused every fill start, and Continue
    # resumed materials without lifting it, so the job stopped again and again.
    pipeline, _flow, _intake, worker = current_pipeline
    pipeline.start(request_id="start")
    drive(pipeline, "filling")
    worker.store.block_storage()
    assert worker.store.stop_reason() == "checkpoint_unavailable"
    with pipeline._guard:
        state = pipeline._load()
        # As at Deloitte: materials stopped before any fill batch existed.
        state.update(
            control="paused",
            status="needs_recheck",
            resume_status="generating_resume",
            worker_batch_id=None,
        )
        pipeline._save(state)
    pipeline.continue_current(request_id="continue-after-quit")
    assert worker.store.stop_reason() == ""
    assert not worker.store.stop_path.exists()
    assert pipeline.snapshot()["status"] != "needs_recheck"


def test_continue_from_an_input_wait_lifts_a_stop_an_app_quit_left(current_pipeline):
    # 2026-11-22 (Allianz): the App was quit while the job waited for its country;
    # Continue from that wait reached the fill start with the marker still in place.
    pipeline, _flow, _intake, worker = current_pipeline
    pipeline.start(request_id="start")
    drive(pipeline, "filling")
    worker.store.block_storage()
    with pipeline._guard:
        state = pipeline._load()
        state.update(
            control="paused",
            status="needs_input",
            resume_status="generating_resume",
            wait_reason="application_country_required",
            worker_batch_id=None,
        )
        pipeline._save(state)
    # The synthetic fill batch may refuse the restart; the lift comes first.
    with suppress(PortalDataError):
        pipeline.continue_current(request_id="continue-after-quit")
    assert worker.store.stop_reason() == ""
    assert not worker.store.stop_path.exists()
