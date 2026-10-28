"""Actual local DOM checks for JSON material versions; no employer network or Submit.

Upstream model and compiler responses are recorded here. Real authors and native
Prism compilation are verified separately against the same production interfaces.
"""

import fcntl
import os
import time
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

import pytest
from test_canonical_career_sources import canonical as canonical
from test_j08_flow_combination import json_flow as json_flow
from test_j08_material_binding import (
    json_material as json_material,
)
from test_j08_material_binding import (
    pipeline_bound,
)
from test_j08_material_binding import (
    recorded_pipeline_clock as recorded_pipeline_clock,
)
from test_p07_runner_browser import INSTRUMENT, assert_no_final_actions, reach
from test_p08_combination import action
from test_resume_export import PDF_SAMPLE

from career_evidence_graph.application_worker import start_run
from career_evidence_graph.application_worker_browser import ApplicationRunner

pytestmark = pytest.mark.worker_browser


@pytest.mark.parametrize("edit", ["mapped", "unmerged"])
def test_json_prism_one_continue_preserves_original_page_and_uploads_exact_candidate(
    json_material, monkeypatch, edit
):
    from playwright.sync_api import sync_playwright

    case = json_material
    task = pipeline_bound(case)
    flow, worker, pipeline = (
        case.flow,
        case.server.worker_service,
        case.server.application_pipeline_service,
    )
    monkeypatch.setenv("PLAYWRIGHT_BROWSERS_PATH", "0")
    start_run(worker.store)
    descriptor = os.open(worker.store.root / ".worker.lock", os.O_CREAT | os.O_RDWR, 0o600)
    fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
    worker.store.worker_lock_descriptor = descriptor
    html = (
        f"<title>{case.job['company']} - {case.job['role_title']}</title>"
        f"<h1>{case.job['role_title']}</h1>"
        + INSTRUMENT
        + '<form id="application-form" data-parser-state="complete">'
        '<label>Full name *<input name="name" value="Human Name" required></label>'
        '<label>Email *<input id="email" type="email" required></label>'
        '<label>Resume *<input id="resume" type="file" required></label>'
        '<label>Certificate<input id="certificate" type="file"></label>'
        '<label>Additional comments<textarea id="notes"></textarea></label>'
        '<button type="submit">Submit application</button></form>'
    )
    posts = []
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True, channel="chromium")
            try:
                context = browser.new_context(offline=True)
                runner = ApplicationRunner(worker.store, context)

                def intercept(route):
                    def fetch(**_options):
                        if route.request.method != "GET":
                            posts.append(route.request.method)
                        return SimpleNamespace(status=200, dispose=lambda: None)

                    runner._live_guard(
                        SimpleNamespace(
                            request=route.request,
                            fetch=fetch,
                            fulfill=lambda *, response: route.fulfill(
                                status=200, body=html, content_type="text/html"
                            ),
                            abort=lambda reason: route.abort(reason),
                        )
                    )

                context.route("**/*", intercept)
                worker.request("resume", {"controller": pipeline.snapshot()["controller"]})
                ready = reach(worker, runner, lambda row: row["status"] == "ready_for_review")
                assert ready["single_binding"]["resume_id"] == task["resume_id"]
                page = runner.pages[task["application_id"]]
                assert page.locator("#email").input_value() == "library@example.test"
                assert page.locator("[name=name]").input_value() == "Human Name"
                pipeline.pause()
                page.locator("#notes").fill("Preserve human notes.")
                page.locator("#certificate").set_input_files(
                    {
                        "name": "human-certificate.pdf",
                        "mimeType": "application/pdf",
                        "buffer": PDF_SAMPLE.read_bytes(),
                    }
                )
                page_id = runner.page_ids[page]
                old = deepcopy(worker.store.load()["jobs"][0])
                task = flow.snapshot(task["id"])["active_task"]
                editing = action(case, task, "begin-prism-edit")
                source = Path(editing["prism_edit"]["project_root"]) / editing["prism_edit"]["main"]
                text = source.read_text().replace(
                    "Planned cross-domain", "Human edited cross-domain"
                )
                if edit == "unmerged":
                    text = text.replace("\\section*{Experience}", "\\section*{Selected Experience}")
                source.write_text(text)
                finished = action(case, editing, "finish-prism-edit")
                captured = action(case, finished, "capture-prism-result")
                candidate = captured["material_update"]["candidate"]
                assert worker.store.load()["jobs"][0]["file_sha256"] == old["file_sha256"]
                assert captured["resume_id"] == task["resume_id"]
                reads = case.store.prism_client.reads
                pipeline.continue_current(request_id="j08-browser-one-continue")
                deadline = time.monotonic() + 10
                while time.monotonic() < deadline:
                    pipeline._tick()
                    runner.tick()
                    state = pipeline.snapshot()
                    job = worker.store.load()["jobs"][0]
                    if job.get("material_update", {}).get("status") == "complete":
                        break
                    time.sleep(0.01)
                assert job.get("material_update", {}).get("status") == "complete", {
                    "pipeline": state,
                    "job": job,
                }
                assert case.store.prism_client.reads == reads
                assert runner.pages[task["application_id"]] is page
                assert runner.page_ids[page] == page_id
                assert page.locator("#notes").input_value() == "Preserve human notes."
                assert (
                    page.locator("#certificate").evaluate("e=>e.files[0].name")
                    == "human-certificate.pdf"
                )
                assert page.locator("[name=name]").input_value() == "Human Name"
                uploaded = page.locator("#resume").evaluate(
                    "async e=>Array.from(new Uint8Array(await e.files[0].arrayBuffer()))"
                )
                assert bytes(uploaded) == case.store.pdf(candidate["resume_id"])
                assert job["single_binding"]["resume_id"] == candidate["resume_id"]
                worker.store.check_single(job, worker.store.load())
                assert_no_final_actions(page, posts)
                assert source.read_text() == text
            finally:
                browser.close()
    finally:
        os.close(descriptor)
        worker.store.worker_lock_descriptor = None
