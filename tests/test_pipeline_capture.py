"""New mail can be captured while the current job waits, without executing another job."""

from copy import deepcopy

import pytest
from test_application_intake import message, ready
from test_application_pipeline import advance, language_wait
from test_application_pipeline import environment as environment

from career_evidence_graph.application_intake import ApplicationIntakeService
from career_evidence_graph.application_pipeline import ApplicationPipeline
from career_evidence_graph.career_portal_data import PortalDataError


def test_capture_during_language_wait_preserves_current_job_and_deduplicates_candidates(
    environment,
):
    pipeline, flow, original_intake, worker, jobs, waiting = language_wait(environment)
    reads = []

    def reader(_directory, **options):
        reads.append(options.get("page_token"))
        return {
            "status": "readable",
            "emails": [message("capture-one"), message("capture-two")],
            "provenance": {},
        }

    def forbidden(*_args, **_kwargs):
        raise AssertionError("Capture must not acquire a JD or start work on another job")

    intake = ApplicationIntakeService(
        flow.applications,
        original_intake.root,
        reader=reader,
        fetcher=forbidden,
        extractor=forbidden,
    )
    pipeline.intake = intake
    try:
        before_tasks = deepcopy(flow.tasks)
        before_calls = deepcopy(flow.calls)
        before_worker = worker.snapshot()
        before_applications = {
            path: path.read_bytes()
            for path in flow.applications.root.rglob("*")
            if path.suffix in {".md", ".json"}
        }
        assert before_applications
        pipeline.capture_mail(request_id="capture-during-wait")
        captured = ready(intake)
        assert len(captured["recommendations"]) == 1
        assert len(captured["recommendations"][0]["source_messages"]) == 2
        shown = pipeline.snapshot()
        for key in (
            "id",
            "status",
            "control",
            "items",
            "active_task_id",
            "notification",
            "intake_run_id",
        ):
            assert shown[key] == waiting[key]
        assert flow.tasks == before_tasks and flow.calls == before_calls
        assert worker.snapshot() == before_worker
        assert {
            path: path.read_bytes()
            for path in flow.applications.root.rglob("*")
            if path.suffix in {".md", ".json"}
        } == before_applications
        assert [row["id"] for row in shown["pending_recommendations"]] == [
            captured["recommendations"][0]["id"]
        ]
        assert shown["can_resume_matching"] is True
        pipeline.capture_mail(request_id="capture-during-wait")
        assert reads == [None]

        worker.store.answers.put_answer(
            {
                "question": "German level",
                "value": "B2",
                "scope": {"application_id": jobs[0]["id"]},
                "state": "confirmed",
            }
        )
        resumed = pipeline.start(request_id="continue-original-job")
        assert resumed["id"] == waiting["id"]
        assert resumed["intake_run_id"] == waiting["intake_run_id"]
        pipeline._tick()
        assert [call for call in flow.calls if call[0] == "analysis"] == [
            ("analysis", jobs[0]["id"])
        ]
        assert pipeline.snapshot()["items"][1]["status"] == "pending"
        assert reads == [None]
    finally:
        intake.close()


def test_same_email_cycle_appends_candidates_and_preserves_waiting_page(environment):
    pipeline, flow, original_intake, worker, _jobs = environment
    pipeline.start(request_id="original-job")
    advance(pipeline, "filling")
    pdf = flow.root / "synthetic-current.pdf"
    pdf.write_bytes(b"%PDF-1.4 synthetic manually retained")
    worker.state["jobs"][0].update(
        status="needs_input",
        page_open=True,
        page_observation={"page_id": "synthetic-current-page"},
        intent={"action": "fill", "field_id": "synthetic-unresolved"},
        file_path=str(pdf),
    )
    pipeline._tick()
    waiting = pipeline.snapshot()
    before_worker, before_tasks, before_calls = (
        worker.snapshot(),
        deepcopy(flow.tasks),
        deepcopy(flow.calls),
    )
    intake = ApplicationIntakeService(
        flow.applications,
        original_intake.root,
        reader=lambda *_a, **_k: {"status": "readable", "emails": [message()], "provenance": {}},
        fetcher=lambda *_: pytest.fail("must not acquire another JD"),
        extractor=lambda *_: pytest.fail("must not analyze another candidate"),
    )
    pipeline.intake = intake
    try:
        pipeline.capture_mail(request_id="capture-with-page")
        assert ready(intake)["status"] == "complete"
        after = pipeline.snapshot()
        for key in (
            "id",
            "status",
            "control",
            "items",
            "active_task_id",
            "notification",
            "worker_batch_id",
        ):
            assert after[key] == waiting[key]
        assert worker.snapshot() == before_worker
        assert flow.tasks == before_tasks and flow.calls == before_calls
        assert pdf.read_bytes() == b"%PDF-1.4 synthetic manually retained"
        assert len(after["pending_recommendations"]) == 1
    finally:
        intake.close()


def test_capture_unknown_dispatch_result_is_retained_and_not_replayed(environment, monkeypatch):
    pipeline, flow, original_intake, _worker, _jobs, waiting = language_wait(environment)
    reads = []
    intake = ApplicationIntakeService(
        flow.applications,
        original_intake.root,
        reader=lambda *_a, **_k: (
            reads.append(True) or {"status": "readable", "emails": [message()], "provenance": {}}
        ),
    )
    original_refresh = intake.refresh

    def response_lost(**options):
        original_refresh(**options)
        raise OSError("Synthetic capture dispatch response lost")

    monkeypatch.setattr(intake, "refresh", response_lost)
    pipeline.intake = intake
    try:
        with pytest.raises(OSError, match="response lost"):
            pipeline.capture_mail(request_id="unknown-capture")
        assert ready(intake)["status"] == "complete"
        shown = pipeline.capture_mail(request_id="unknown-capture")
        assert reads == [True]
        assert shown["mail_capture_requests"][-1]["status"] == "needs_recheck"
        assert shown["status"] == waiting["status"] and shown["items"] == waiting["items"]
    finally:
        intake.close()


def test_capture_does_not_replace_an_existing_jd_read(environment):
    pipeline, flow, intake, worker, _jobs, _waiting = language_wait(environment)
    intake.state.update(status="running", capture_only=False)
    before, before_worker = pipeline.path.read_bytes(), worker.snapshot()
    calls = deepcopy(flow.calls)
    with pytest.raises(PortalDataError) as error:
        pipeline.capture_mail(request_id="must-not-replace-read")
    assert error.value.code == "mail_capture_busy"
    assert pipeline.path.read_bytes() == before and worker.snapshot() == before_worker
    assert flow.calls == calls and len(intake.calls) == 1


@pytest.mark.parametrize("paused", [False, True])
def test_capture_preserves_completed_mail_results_until_pipeline_adopts_them(environment, paused):
    pipeline, flow, intake, worker, jobs = environment
    pipeline.start(request_id="original-mail-read")
    pipeline._tick()
    assert intake.snapshot()["status"] == "complete"
    assert pipeline.snapshot()["status"] == "reading_email"
    if paused:
        pipeline.pause()
    before = pipeline.path.read_bytes()
    original_run = intake.snapshot()["run_id"]
    original_chain = (intake.root / "runs" / original_run / "source-chain.json").read_bytes()
    with pytest.raises(PortalDataError) as error:
        pipeline.capture_mail(request_id="capture-before-adoption")
    assert error.value.code == "mail_capture_busy"
    assert pipeline.path.read_bytes() == before
    assert intake.snapshot()["run_id"] == original_run and len(intake.calls) == 1
    assert (
        intake.root / "runs" / original_run / "source-chain.json"
    ).read_bytes() == original_chain
    assert flow.calls == [] and worker.snapshot()["jobs"] == []
    if paused:
        pipeline.start(request_id="continue-original-read")
    pipeline._tick()
    adopted = pipeline.snapshot()
    assert adopted["status"] == "matching"
    assert [item["application_id"] for item in adopted["items"]] == [job["id"] for job in jobs]
    pipeline.capture_mail(request_id="capture-before-adoption")
    assert intake.calls[-1] == {"capture_only": True}
    assert pipeline.snapshot()["items"] == adopted["items"]


def test_unavailable_mail_intake_does_not_hide_current_job(environment, monkeypatch):
    pipeline, _flow, intake, _worker, _jobs, waiting = language_wait(environment)

    def unavailable():
        raise PortalDataError("intake_invalid", "Synthetic damaged mail checkpoint", 409)

    monkeypatch.setattr(intake, "snapshot", unavailable)
    shown = pipeline.snapshot()
    assert shown["items"] == waiting["items"] and shown["status"] == waiting["status"]
    assert shown["mail_intake_error"] == "intake_unavailable"
    assert shown["pending_recommendations"] == []


def test_capture_receipt_save_failure_stops_before_dispatch(environment, monkeypatch):
    pipeline, flow, intake, worker, _jobs, _waiting = language_wait(environment)
    before, before_worker, calls = (
        pipeline.path.read_bytes(),
        worker.snapshot(),
        deepcopy(flow.calls),
    )

    def unavailable(_state):
        raise OSError("Synthetic receipt cannot be saved")

    monkeypatch.setattr(pipeline, "_save", unavailable)
    with pytest.raises(OSError, match="cannot be saved"):
        pipeline.capture_mail(request_id="not-dispatched")
    assert len(intake.calls) == 1
    assert pipeline.path.read_bytes() == before
    assert worker.snapshot() == before_worker and flow.calls == calls


def test_capture_dispatch_checkpoint_survives_receipt_failure_and_reopen(environment, monkeypatch):
    pipeline, flow, original_intake, worker, _jobs, _waiting = language_wait(environment)
    reads = []
    intake = ApplicationIntakeService(
        flow.applications,
        original_intake.root,
        reader=lambda *_a, **_k: (
            reads.append(True) or {"status": "readable", "emails": [message()], "provenance": {}}
        ),
    )
    pipeline.intake = intake
    original_save = pipeline._save

    def save(state):
        if state.get("mail_capture_requests", [{}])[-1].get("status") == "started":
            raise OSError("Synthetic final receipt save failed")
        original_save(state)

    monkeypatch.setattr(pipeline, "_save", save)
    reopened = None
    try:
        with pytest.raises(OSError, match="final receipt save failed"):
            pipeline.capture_mail(request_id="dispatched-before-save-failed")
        assert ready(intake)["status"] == "complete"
        pipeline.close()
        reopened = ApplicationPipeline(flow, intake, worker, interval=100)
        result = reopened.capture_mail(request_id="dispatched-before-save-failed")
        assert reads == [True]
        assert result["mail_capture_requests"][-1]["status"] == "dispatching"
        assert flow.calls == [] and worker.snapshot()["jobs"] == []
    finally:
        if reopened is not None:
            reopened.close()
        intake.close()


def test_capture_request_is_not_replayed_after_another_pipeline_cycle(environment):
    pipeline, flow, intake, worker, _jobs = environment
    intake.jobs = []
    captured = pipeline.capture_mail(request_id="captured-before-cycles")
    receipt = deepcopy(captured["mail_capture_requests"])
    pipeline.start(request_id="empty-cycle-one")
    first = advance(pipeline, "no_matches")
    pipeline.start(request_id="empty-cycle-two")
    second = advance(pipeline, "no_matches")
    assert second["id"] != first["id"]
    calls = deepcopy(intake.calls)
    repeated = pipeline.capture_mail(request_id="captured-before-cycles")
    assert repeated["mail_capture_requests"] == receipt
    assert repeated["id"] == second["id"] and intake.calls == calls
    assert len(calls) == 3
    assert flow.calls == [] and worker.snapshot()["jobs"] == []
