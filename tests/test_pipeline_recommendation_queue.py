"""The real intake store drives one current job and continues capture while waiting."""

import time
from copy import deepcopy

import pytest
from test_application_intake import message, page, ready
from test_application_pipeline import Flow, Worker

from career_evidence_graph.application_intake import ApplicationIntakeService
from career_evidence_graph.application_pipeline import ApplicationPipeline
from career_evidence_graph.career_portal_data import ApplicationStore


@pytest.fixture
def queue_environment(tmp_path):
    (tmp_path / "applications").mkdir()
    apps = ApplicationStore(tmp_path / "applications")
    reads, fetches = [], []
    messages = [
        message(f"mail-{index}", [f"https://www.linkedin.com/jobs/view/{10000 + index}"])
        for index in range(16)
    ]

    def reader(_directory, **options):
        token = options.get("page_token")
        offset = int(token or 0)
        reads.append(token)
        return {
            "status": "readable",
            "emails": messages[offset : offset + 3],
            "provenance": {
                "next_page_token": str(offset + 3) if offset + 3 < len(messages) else None
            },
        }

    def fetcher(url):
        fetches.append(url)
        return page(url) | {
            "job_fields": {
                "title": "Systems Engineer",
                "company": "Synthetic Labs",
                "location": "Zurich, Switzerland",
            }
        }

    intake = ApplicationIntakeService(apps, tmp_path / "intake", reader=reader, fetcher=fetcher)
    worker = Worker()
    flow = Flow(tmp_path / "flow", apps, worker)
    original_start = flow.start

    def start(identifier, revision, stage):
        if stage == "analysis":
            return original_start(identifier, revision, stage)
        task = flow.tasks[identifier]
        assert task["automatic_materials"] is True
        flow.calls.append((stage, identifier))
        if stage == "resume":
            task.update(status="draft_ready", draft_id="full-draft", draft_sha256="a" * 64)
        elif stage == "export":
            task.update(status="materials_ready", resume_id="pdf", resume_sha256="b" * 64)
        else:
            pytest.fail(f"Unexpected material stage: {stage}")
        return deepcopy(task)

    flow.start = start
    pipeline = ApplicationPipeline(flow, intake, worker, interval=100)
    try:
        yield pipeline, flow, intake, worker, reads, fetches, messages
    finally:
        pipeline.close()
        intake.close()


def poll_due(pipeline):
    """Make the background mail poll due on the next tick."""
    state = pipeline._load()
    state["mail_poll_at"] = 0
    pipeline._save(state)


def drive(pipeline, status):
    for _ in range(100):
        pipeline._tick()
        if pipeline.snapshot()["status"] == status:
            return pipeline.snapshot()
        time.sleep(0.005)
    pytest.fail(str(pipeline.snapshot()))


def test_completed_capture_selects_a_job_before_any_new_background_capture(queue_environment):
    # Installed MC-11: a real capture outlasts the 60 s poll, so the poll restarted it
    # in the very tick selection ran, and selection waited on it again and again.
    import threading

    pipeline, _flow, intake, _worker, reads, _fetches, _messages = queue_environment
    pipeline.start(request_id="select-after-capture")
    drive(pipeline, "selecting_job")
    gate, original = threading.Event(), intake.reader

    def held(directory, **options):
        gate.wait(5)
        return original(directory, **options)

    intake.reader = held
    try:
        poll_due(pipeline)
        before = len(reads)
        current = drive(pipeline, "acquiring_source")
        assert current["current_recommendation_id"]
        assert intake.snapshot()["status"] != "running" and len(reads) == before
    finally:
        gate.set()


def test_paused_selection_starts_no_background_capture_that_continue_would_wait_on(
    queue_environment,
):
    # Installed MC-11: the App opened paused at selection, the poll began a full
    # capture within seconds, and Continue then waited minutes behind it.
    pipeline, _flow, intake, _worker, reads, _fetches, _messages = queue_environment
    pipeline.start(request_id="paused-selection")
    drive(pipeline, "selecting_job")
    pipeline.pause()
    poll_due(pipeline)
    before = len(reads)
    drive(pipeline, "paused")
    assert intake.snapshot()["status"] != "running" and len(reads) == before
    pipeline.continue_current(request_id="continue-paused-selection")
    assert drive(pipeline, "acquiring_source")["current_recommendation_id"]
    assert len(reads) == before


def test_all_mail_pages_captured_but_only_first_job_acquired_and_processed(queue_environment):
    pipeline, flow, intake, worker, reads, fetches, _messages = queue_environment
    pipeline.start(request_id="persistent-queue")
    current = drive(pipeline, "filling")
    records = intake.snapshot()["recommendations"]
    assert len(records) == 16 and reads == [None, "3", "6", "9", "12", "15"]
    assert fetches == ["https://www.linkedin.com/jobs/view/10000"]
    assert current["current_recommendation_id"] == records[0]["id"]
    assert len(current["items"]) == len(flow.tasks) == 1
    assert [name for name, _ in flow.calls if name in {"analysis", "resume", "export"}] == [
        "analysis",
        "resume",
        "export",
    ]
    worker.state["jobs"][0].update(status="ready_for_review", page_open=True)
    waiting = drive(pipeline, "ready_for_review")
    before = deepcopy(flow.calls), deepcopy(worker.state)
    pipeline._tick()
    assert pipeline.snapshot()["items"] == waiting["items"]
    assert (flow.calls, worker.state) == before
    assert len(fetches) == 1


def test_new_mail_captured_automatically_during_submit_wait_without_changing_page(
    queue_environment,
):
    pipeline, flow, intake, worker, _reads, fetches, messages = queue_environment
    pipeline.start(request_id="capture-while-waiting")
    drive(pipeline, "filling")
    worker.state["jobs"][0].update(
        status="ready_for_review",
        page_open=True,
        page_observation={"page_id": "kept"},
        file_path="synthetic-existing.pdf",
        intent=None,
    )
    waiting = drive(pipeline, "ready_for_review")
    before = deepcopy(worker.state), deepcopy(flow.tasks), deepcopy(flow.calls)
    messages.append(message("new-mail", ["https://www.linkedin.com/jobs/view/99999"]))
    poll_due(pipeline)
    polled = time.time()
    pipeline._tick()
    assert len(ready(intake)["recommendations"]) == 17
    # 2026-11-08: the next waiting read is 30 minutes away, not 60 s.
    assert pipeline._load()["mail_poll_at"] >= polled + 1800
    after = pipeline.snapshot()
    for key in ("items", "active_task_id", "notification", "status", "control", "worker_batch_id"):
        assert after[key] == waiting[key]
    assert (worker.state, flow.tasks, flow.calls) == before
    assert len(fetches) == 1
    # Duplicate mail changes neither queue length nor execution.
    poll_due(pipeline)
    pipeline._tick()
    assert len(ready(intake)["recommendations"]) == 17 and len(fetches) == 1


def test_previously_saved_pending_note_remains_eligible(queue_environment):
    pipeline, flow, intake, _worker, _reads, fetches, _messages = queue_environment
    intake.refresh(capture_only=True)
    record = ready(intake)["recommendations"][0]
    intake.acquire(record["id"], record["revision"])
    record = ready(intake)["recommendations"][0]
    existing_id = record["existing_application"]["id"]
    assert flow.tasks == {}
    pipeline.start(request_id="adopt-existing-note")
    current = drive(pipeline, "filling")
    assert current["active_task_id"] == existing_id
    assert len(fetches) == 1 and len(flow.applications.list_applications()) == 1


def test_failed_source_holds_current_and_never_retries(queue_environment):
    pipeline, flow, intake, worker, _reads, fetches, _messages = queue_environment

    def failed(url):
        fetches.append(url)
        return page(url, status="unavailable", completeness="unknown")

    intake.fetcher = failed
    pipeline.start(request_id="failed-source")
    waiting = drive(pipeline, "needs_input")
    for _ in range(5):
        pipeline._tick()
    assert len(fetches) == 1 and flow.tasks == {} and worker.state["jobs"] == []
    assert pipeline.snapshot()["current_recommendation_id"] == waiting["current_recommendation_id"]


def test_empty_queue_waits_for_mail_without_expiring(queue_environment, monkeypatch):
    pipeline, flow, intake, _worker, _reads, fetches, messages = queue_environment
    messages.clear()
    pipeline.start(request_id="empty-queue")
    waiting = drive(pipeline, "waiting_for_mail")
    assert waiting["control"] == "running" and fetches == [] and flow.tasks == {}
    monkeypatch.setattr(
        "career_evidence_graph.application_pipeline.time.time", lambda: waiting["started_at"] + 3600
    )
    messages.append(message("arrived", ["https://www.linkedin.com/jobs/view/98765"]))
    drive(pipeline, "filling")
    assert fetches == ["https://www.linkedin.com/jobs/view/98765"]


def test_healthy_reopen_continues_current_job_without_replaying_analysis(queue_environment):
    pipeline, flow, intake, worker, _reads, fetches, _messages = queue_environment
    pipeline.start(request_id="healthy-reopen")
    current = drive(pipeline, "generating_resume")
    before = deepcopy(flow.calls)
    pipeline.close()
    reopened = ApplicationPipeline(flow, intake, worker, interval=100)
    try:
        assert reopened.snapshot()["control"] == "running"
        after = drive(reopened, "filling")
        assert after["current_recommendation_id"] == current["current_recommendation_id"]
        assert after["active_task_id"] == current["active_task_id"]
        assert [call for call in flow.calls if call[0] == "analysis"] == [
            call for call in before if call[0] == "analysis"
        ]
        assert len(fetches) == 1
    finally:
        reopened.close()


def test_paused_reopen_retains_current_and_does_not_process_next(queue_environment):
    pipeline, flow, intake, worker, _reads, fetches, _messages = queue_environment
    pipeline.start(request_id="paused-reopen")
    drive(pipeline, "generating_resume")
    waiting = pipeline.pause()
    pipeline.close()
    reopened = ApplicationPipeline(flow, intake, worker, interval=100)
    try:
        before = deepcopy(flow.calls)
        reopened._tick()
        assert reopened.snapshot()["items"] == waiting["items"]
        assert reopened.snapshot()["control"] == "paused" and flow.calls == before
        assert len(fetches) == 1
    finally:
        reopened.close()


def test_unknown_acquisition_dispatch_never_repeats_or_moves_to_next(
    queue_environment, monkeypatch
):
    pipeline, flow, intake, worker, _reads, fetches, _messages = queue_environment
    original = intake.acquire

    def lost_response(identifier, revision):
        original(identifier, revision)
        raise OSError("Synthetic dispatch result lost")

    monkeypatch.setattr(intake, "acquire", lost_response)
    pipeline.start(request_id="unknown-source-dispatch")
    waiting = drive(pipeline, "needs_recheck")
    ready(intake)
    for _ in range(3):
        pipeline._tick()
    assert len(fetches) == 1 and flow.tasks == {} and worker.state["jobs"] == []
    assert waiting["source_receipt"]["status"] == "needs_recheck"
    pipeline.close()
    reopened = ApplicationPipeline(flow, intake, worker, interval=100)
    try:
        reopened._tick()
        assert (
            reopened.snapshot()["current_recommendation_id"] == waiting["current_recommendation_id"]
        )
        assert reopened.snapshot()["control"] == "paused" and len(fetches) == 1
    finally:
        reopened.close()


def test_current_language_conflict_waits_and_one_continue_resumes_same_job(queue_environment):
    from career_evidence_graph.application_worker import WorkerStore

    pipeline, flow, intake, worker, _reads, fetches, _messages = queue_environment
    worker.store = WorkerStore(flow.applications, flow.root.parent / "language-worker")
    original = intake.fetcher
    intake.fetcher = lambda url: (
        original(url) | {"body_text": "German B2 required. Python engineering."}
    )
    for question, value in [("German level", "B2"), ("German proficiency CEFR", "C1")]:
        worker.store.answers.put_answer(
            {"question": question, "value": value, "scope": {}, "state": "confirmed"}
        )
    pipeline.start(request_id="current-language")
    waiting = drive(pipeline, "needs_input")
    assert waiting["can_resume_matching"] is True and flow.tasks == {} and len(fetches) == 1
    application_id = waiting["items"][0]["application_id"]
    worker.store.answers.put_answer(
        {
            "question": "German level",
            "value": "B2",
            "scope": {"application_id": application_id},
            "state": "confirmed",
        }
    )
    # Replaying admission is not Continue.
    assert pipeline.start(request_id="current-language")["control"] == "paused"
    pipeline.start(request_id="continue-current-language")
    current = drive(pipeline, "filling")
    assert current["current_recommendation_id"] == waiting["current_recommendation_id"]
    assert len(fetches) == len(flow.tasks) == 1


def test_retained_unknown_source_checkpoint_holds_without_another_fetch(queue_environment):
    pipeline, flow, intake, worker, _reads, fetches, _messages = queue_environment
    intake.refresh(capture_only=True)
    record = ready(intake)["recommendations"][0]
    # This durable admission represents an interrupted source operation with no response.
    assert intake.store.begin_acquisition(record["id"], record["revision"])["status"] == "fetch"
    pipeline.start(request_id="retained-unknown-source")
    waiting = drive(pipeline, "needs_recheck")
    assert waiting["current_recommendation_id"] == record["id"]
    assert fetches == [] and flow.tasks == {} and worker.state["jobs"] == []
    for _ in range(3):
        pipeline._tick()
    assert fetches == []


def test_paused_empty_queue_one_continue_restores_saved_mail_wait(queue_environment):
    pipeline, flow, _intake, _worker, reads, fetches, messages = queue_environment
    messages.clear()
    pipeline.start(request_id="empty-pause")
    waiting = drive(pipeline, "waiting_for_mail")
    pipeline.pause()
    resumed = pipeline.continue_current(request_id="continue-empty-mail-wait")
    assert resumed["status"] == "waiting_for_mail" and resumed["control"] == "running"
    assert resumed["id"] == waiting["id"] and resumed["current_recommendation_id"] is None
    assert pipeline.continue_current(request_id="continue-empty-mail-wait") == resumed
    assert reads == [None] and fetches == [] and flow.tasks == {}


def test_low_score_is_skipped_and_a_middle_score_waits_for_one_continue(
    queue_environment, monkeypatch
):
    from career_evidence_graph import application_pipeline

    # Decided 2026-10-31: below the skip line the job is set aside; in the approval band
    # it waits after analysis, before materials, until one Continue approves it.
    pipeline, flow, _intake, _worker, _reads, _fetches, _messages = queue_environment
    tiers = ["skip", "approve"]
    monkeypatch.setattr(
        application_pipeline,
        "score_tier",
        lambda score, needs_review=False: tiers.pop(0) if tiers else "auto",
    )
    pipeline.start(request_id="tiers")
    waiting = drive(pipeline, "needs_input")
    skipped = [row for row in waiting["items"] if row["status"] == "skipped"]
    assert [row["reason"] for row in skipped] == ["low_match_score"]
    assert skipped[0]["retained_status"] == "matched"
    assert waiting["wait_reason"] == "score_approval"
    assert not any(call[0] == "resume" for call in flow.calls)
    pipeline.continue_current(request_id="approve-score")
    drive(pipeline, "filling")
    assert [call[0] for call in flow.calls].count("resume") == 1


def test_a_closed_posting_leaves_unrecorded_and_easy_apply_with_its_reason(
    queue_environment, monkeypatch
):
    from career_evidence_graph import job_listing_links

    # Decided 2026-10-31: a LinkedIn job is read once before matching; an Easy Apply
    # one keeps LinkedIn and is set aside. 2026-11-05: a closed posting creates no
    # application record and is not listed; the queue still never picks it again.
    pipeline, flow, intake, _worker, _reads, _fetches, _messages = queue_environment
    statuses = {"10000": ("closed", None), "10001": ("easy_apply", None)}
    monkeypatch.setattr(
        job_listing_links,
        "posting_status",
        lambda url, read=None: statuses.get(url.rstrip("/").rsplit("/", 1)[-1], (None, None)),
    )
    before = {row["id"] for row in flow.applications.list_applications()}
    pipeline.start(request_id="postings")
    filling = drive(pipeline, "filling")
    closed = next(
        row["id"]
        for row in intake.snapshot()["recommendations"]
        if row["url"].rstrip("/").endswith("10000")
    )
    assert filling["closed_postings"] == [closed]
    assert closed not in {row["recommendation_id"] for row in filling["items"]}
    assert closed not in {row["id"] for row in filling["pending_recommendations"]}
    skipped = [row for row in filling["items"] if row["status"] == "skipped"]
    assert [row["reason"] for row in skipped] == ["easy_apply_only"]
    created = {row["id"] for row in flow.applications.list_applications()} - before
    assert skipped[0]["application_id"] in created
    assert all(
        not row["url"].rstrip("/").endswith("10000")
        for row in flow.applications.list_applications()
    )
    assert flow.applications.get_application(skipped[0]["application_id"])["status"] == "drafting"


def test_an_indeed_apply_job_leaves_the_queue_with_its_reason(queue_environment, monkeypatch):
    from career_evidence_graph import indeed_job_source, job_listing_links

    # 2026-11-05: Indeed names the apply route on the page read at intake; an
    # Indeed Apply job keeps Indeed and is set aside like an Easy Apply one.
    pipeline, flow, _intake, _worker, _reads, _fetches, _messages = queue_environment
    monkeypatch.setattr(job_listing_links, "posting_status", lambda url, read=None: (None, None))
    monkeypatch.setattr(
        indeed_job_source,
        "apply_route",
        lambda record: "indeed_apply" if record["url"].rstrip("/").endswith("10000") else "",
    )
    pipeline.start(request_id="indeed-apply")
    filling = drive(pipeline, "filling")
    skipped = [row for row in filling["items"] if row["status"] == "skipped"]
    assert [row["reason"] for row in skipped] == ["indeed_apply_only"]
    application = flow.applications.get_application(skipped[0]["application_id"])
    assert application["status"] == "drafting" and "Indeed Apply" in application["next_action"]
