"""Opt-in real Chromium DOM/handoff/result journey with every request fulfilled offline."""

import time
from types import SimpleNamespace

import pytest
from test_pipeline_current_job import current_pipeline as current_pipeline
from test_pipeline_recommendation_queue import drive

from career_evidence_graph import application_form_runner
from career_evidence_graph.application_form_state import SAMPLE_INTERVAL
from career_evidence_graph.application_worker import start_run
from career_evidence_graph.application_worker_browser import ApplicationRunner

pytestmark = pytest.mark.worker_browser


def test_original_page_submit_is_manual_and_success_advances_after_readback(
    current_pipeline, monkeypatch
):
    from playwright.sync_api import sync_playwright

    monkeypatch.setenv("PLAYWRIGHT_BROWSERS_PATH", "0")
    pipeline, flow, _intake, worker = current_pipeline
    pipeline.start(request_id="browser-original-submit")
    first = drive(pipeline, "filling")
    start_run(worker.store)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True, channel="chromium")
        try:
            context = browser.new_context(offline=True)
            runner = ApplicationRunner(worker.store, context)
            current = worker.store.load()["jobs"][0]
            posts = []
            form = (
                "<title>Synthetic - Engineer</title><h1>Engineer</h1>"
                '<form id="application-form" method="post">'
                '<label>Resume/CV *<input id="resume" name="resume" type="file" required></label>'
                '<button type="submit">Submit</button></form>'
            )
            success = "<h1>Your application has been submitted.</h1>"

            def offline_route(route):
                if route.request.method == "POST":
                    posts.append(route.request.url)
                    runner._live_guard_request(
                        SimpleNamespace(
                            request=route.request,
                            continue_=lambda: route.fulfill(
                                status=200, body=success, content_type="text/html"
                            ),
                            abort=route.abort,
                        )
                    )
                else:
                    route.fulfill(status=200, body=form, content_type="text/html")

            context.route("**/*", offline_route)
            page = context.new_page()
            runner.pages[current["application_id"]] = page
            runner.page_ids[page] = "original-chromium-page"
            runner.guards[current["application_id"]] = runner._live_guard
            page.goto(current["job_url"] + "/apply")
            page.locator("input[type=file]").set_input_files(current["file_path"])
            # This journey starts on the completed submit-only page. Establish
            # its real stable form snapshot before asking the pipeline to hand off.
            deadline = time.monotonic() + 5
            while True:
                observed = runner.observe(page, current)
                form_state = application_form_runner.capture(
                    runner, page, current, worker.store.load()["batch_id"], observed
                )
                if form_state["parser"]["status"] == "stable":
                    break
                assert time.monotonic() < deadline, form_state["parser"]
                page.wait_for_timeout(SAMPLE_INTERVAL * 1000)
            application_form_runner.check_ready(current, observed)
            assert observed["fields"][0]["file_sha256"] == current["file_sha256"]
            state = worker.store.load()
            state["runtime"]["observed_at"] = time.time()
            state["jobs"][0].update(
                status="ready_for_review",
                page_open=True,
                page_observation={
                    "event": "observed",
                    "run_id": runner.run_id,
                    "page_id": "original-chromium-page",
                    "at": time.time(),
                },
            )
            worker.store.save(state)
            pipeline._tick()
            runner._tick()
            assert page in runner.handed_off_pages and posts == []
            assert worker.store.load()["jobs"][0]["handoff"]["source"] == "automatic_submit_wait"
            # This test action represents the human's only final click, outside product automation.
            page.get_by_role("button", name="Submit", exact=True).click()
            page.get_by_role("heading", name="Your application has been submitted.").wait_for()
            runner._tick()
            assert posts == [current["job_url"] + "/apply"]
            assert pipeline.snapshot()["active_task_id"] == first["active_task_id"]
            pipeline.observe_result(request_id="browser-result")
            runner._tick()
            assert (
                worker.store.load()["jobs"][0]["submission_observation"]["conclusion"] == "success"
            )
            pipeline._tick()
            second = drive(pipeline, "filling")
            assert second["active_task_id"] != first["active_task_id"] and len(flow.tasks) == 2
            assert len(posts) == 1 and not page.is_closed()
        finally:
            browser.close()
