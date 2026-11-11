"""A user Continue retries only a known failed source on the current job."""

from test_application_intake import page
from test_pipeline_recommendation_queue import drive
from test_pipeline_recommendation_queue import queue_environment as queue_environment


def test_continue_retries_failed_current_source_once_and_keeps_next_job_pending(queue_environment):
    pipeline, flow, intake, _worker, _reads, fetches, _messages = queue_environment
    original = intake.fetcher

    def fail_first(url):
        if not fetches:
            fetches.append(url)
            return page(url, status="unavailable", completeness="unknown")
        return original(url)

    intake.fetcher = fail_first
    pipeline.start(request_id="failed-source")
    waiting = drive(pipeline, "needs_input")
    current_id = waiting["current_recommendation_id"]
    for _ in range(3):
        pipeline._tick()
    assert len(fetches) == 1 and flow.tasks == {}

    pipeline.continue_current(request_id="retry-current")
    resumed = drive(pipeline, "filling")
    assert resumed["current_recommendation_id"] == current_id
    assert fetches == ["https://www.linkedin.com/jobs/view/10000"] * 2
    assert len(flow.tasks) == 1 and len(resumed["pending_recommendations"]) == 15
    pipeline.continue_current(request_id="retry-current")
    for _ in range(3):
        pipeline._tick()
    assert len(fetches) == 2 and len(flow.tasks) == 1


def test_failed_retry_waits_for_a_new_continue_request_and_does_not_retry_on_ticks(
    queue_environment,
):
    pipeline, flow, intake, _worker, _reads, fetches, _messages = queue_environment

    def fail(url):
        fetches.append(url)
        return page(url, status="unavailable", completeness="unknown")

    intake.fetcher = fail
    pipeline.start(request_id="failed-source")
    waiting = drive(pipeline, "needs_input")
    pipeline.continue_current(request_id="retry-once")
    drive(pipeline, "needs_input")
    assert len(fetches) == 2
    pipeline.continue_current(request_id="retry-once")
    pipeline.pause()
    for _ in range(3):
        pipeline._tick()
    assert len(fetches) == 2 and flow.tasks == {}
    pipeline.continue_current(request_id="retry-again")
    resumed = drive(pipeline, "needs_input")
    assert len(fetches) == 3 and len(set(fetches)) == 1
    assert resumed["current_recommendation_id"] == waiting["current_recommendation_id"]


def test_continue_never_replays_an_unknown_source_checkpoint(queue_environment):
    from test_application_intake import ready

    pipeline, flow, intake, worker, _reads, fetches, _messages = queue_environment
    intake.refresh(capture_only=True)
    record = ready(intake)["recommendations"][0]
    assert intake.store.begin_acquisition(record["id"], record["revision"])["status"] == "fetch"
    pipeline.start(request_id="unknown-source")
    drive(pipeline, "needs_recheck")
    pipeline.continue_current(request_id="continue-unknown")
    waiting = drive(pipeline, "needs_recheck")
    assert waiting["current_recommendation_id"] == record["id"]
    assert fetches == [] and flow.tasks == {} and worker.state["jobs"] == []


def test_running_source_retry_ignores_duplicate_and_additional_continue(queue_environment):
    import threading

    pipeline, flow, intake, _worker, _reads, fetches, _messages = queue_environment
    original = intake.fetcher
    entered, release = threading.Event(), threading.Event()

    def fetch(url):
        if not fetches:
            fetches.append(url)
            return page(url, status="unavailable", completeness="unknown")
        entered.set()
        assert release.wait(3)
        return original(url)

    intake.fetcher = fetch
    try:
        pipeline.start(request_id="failed-source")
        drive(pipeline, "needs_input")
        pipeline.continue_current(request_id="retry-running")
        pipeline._tick()
        assert entered.wait(2)
        pipeline.continue_current(request_id="retry-running")
        pipeline.continue_current(request_id="extra-while-running")
        for _ in range(3):
            pipeline._tick()
        assert len(fetches) == 1 and flow.tasks == {}
        release.set()
        drive(pipeline, "filling")
        assert len(fetches) == 2 and len(flow.tasks) == 1
    finally:
        release.set()


def test_continue_retains_failed_source_retry_while_mail_capture_is_running(queue_environment):
    import threading

    from test_application_intake import ready

    pipeline, flow, intake, _worker, _reads, fetches, _messages = queue_environment
    original = intake.fetcher
    entered, release = threading.Event(), threading.Event()

    def fetch(url):
        if not fetches:
            fetches.append(url)
            return page(url, status="unavailable", completeness="unknown")
        return original(url)

    def reader(*_args, **_options):
        entered.set()
        assert release.wait(3)
        return {"status": "readable", "emails": [], "provenance": {}}

    intake.fetcher = fetch
    try:
        pipeline.start(request_id="failed-source")
        waiting = drive(pipeline, "needs_input")
        intake.reader = reader
        pipeline.capture_mail(request_id="capture-while-paused")
        assert entered.wait(2)
        pipeline.continue_current(request_id="retry-after-capture")
        for _ in range(3):
            pipeline._tick()
        assert len(fetches) == 1 and flow.tasks == {}
        release.set()
        ready(intake)
        resumed = drive(pipeline, "filling")
        assert resumed["current_recommendation_id"] == waiting["current_recommendation_id"]
        assert len(fetches) == 2 and len(flow.tasks) == 1
    finally:
        release.set()


def test_unknown_retry_dispatch_is_not_downgraded_or_replayed_by_continue(
    queue_environment, monkeypatch
):
    from test_application_intake import ready

    pipeline, flow, intake, _worker, _reads, fetches, _messages = queue_environment

    def fetch(url):
        fetches.append(url)
        return page(url, status="unavailable", completeness="unknown")

    intake.fetcher = fetch
    pipeline.start(request_id="failed-source")
    waiting = drive(pipeline, "needs_input")
    original = intake.acquire

    def lost_response(*args, **options):
        original(*args, **options)
        raise OSError("Synthetic retry dispatch response lost")

    monkeypatch.setattr(intake, "acquire", lost_response)
    pipeline.continue_current(request_id="retry-lost-response")
    drive(pipeline, "needs_recheck")
    ready(intake)
    assert len(fetches) == 2
    pipeline.continue_current(request_id="check-unknown")
    pipeline._tick()
    assert pipeline.snapshot()["status"] == "needs_recheck"
    pipeline.continue_current(request_id="still-unknown")
    pipeline._tick()
    assert pipeline.snapshot()["status"] == "needs_recheck"
    assert pipeline.snapshot()["current_recommendation_id"] == waiting["current_recommendation_id"]
    assert len(fetches) == 2 and flow.tasks == {}
