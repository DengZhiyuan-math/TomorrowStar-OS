"""Original real local DOM, one Continue, exact updated PDF, zero final Submit."""

import fcntl
import json
import os
import time
from copy import deepcopy
from types import SimpleNamespace

import pytest
from test_application_resume import task_resume as task_resume
from test_bound_material_update import bound_pipeline as bound_pipeline
from test_full_latex_generation import full_latex as full_latex
from test_resume_export import PDF_SAMPLE

from career_evidence_graph.application_form_state import SAMPLE_INTERVAL
from career_evidence_graph.application_information import put_information_answer
from career_evidence_graph.application_worker import start_run
from career_evidence_graph.application_worker_browser import ApplicationRunner
from career_evidence_graph.career_portal_data import PortalDataError

pytestmark = pytest.mark.worker_browser


def choose_email_and_continue(server, runner, page, *, current_value, proposed_value, request_id):
    """Choose the one reported Email difference, then resume the original page."""
    flow, worker, pipeline = (
        server.application_flow_service,
        server.worker_service,
        server.application_pipeline_service,
    )
    assert pipeline.snapshot()["status"] == "needs_input", json.dumps(
        {
            "pipeline": pipeline.snapshot()["status"],
            "notification": pipeline.snapshot().get("notification"),
            "job": worker.store.load()["jobs"][0].get("reason"),
            "update": {
                key: flow.snapshot()["active_task"].get("material_update", {}).get(key)
                for key in ("status", "error_code", "error_message")
            },
        },
        ensure_ascii=False,
    )
    job = worker.store.load()["jobs"][0]
    assert job["status"] == "needs_input" and job["reason"] == "form_differences", job
    form = job["form_state"]
    assert len(form["differences"]) == 1, form["differences"]
    difference = form["differences"][0]
    assert difference["question"] == "Email"
    assert difference["current_value"] == current_value
    assert difference["proposed_value"] == proposed_value

    def assert_preserved():
        assert page.locator("#email").input_value() == current_value
        assert page.locator("#notes").input_value() == "Retain this human text."
        assert (
            page.locator("#certificate").evaluate("e => e.files[0].name") == "human-certificate.pdf"
        )

    assert_preserved()
    task = flow.task_snapshot(pipeline.snapshot()["active_task_id"])
    flow.worker_action(
        task["id"],
        task["revision"],
        "resolve-form-differences",
        {
            "application_id": job["application_id"],
            "binding": form["binding"],
            "revision": form["revision"],
            "choices": [{"difference_id": difference["id"], "action": "use"}],
        },
    )
    # Saving the choice does not write the page or resume the queue.
    assert_preserved()
    assert pipeline.snapshot()["status"] == "needs_input"
    pipeline.continue_current(request_id=request_id)
    deadline = time.monotonic() + 15
    while True:
        pipeline._tick()
        runner.tick()
        state = pipeline.snapshot()
        if state["status"] in {"ready_for_review", "needs_recheck", "needs_input"}:
            break
        assert time.monotonic() < deadline, state
        time.sleep(SAMPLE_INTERVAL)
    assert state["status"] == "ready_for_review", state.get("notification")
    assert page.locator("#email").input_value() == proposed_value
    assert page.locator("#notes").input_value() == "Retain this human text."
    assert page.locator("#certificate").evaluate("e => e.files[0].name") == "human-certificate.pdf"
    return state


@pytest.fixture
def original_material_page(bound_pipeline, monkeypatch):
    from playwright.sync_api import sync_playwright

    server, store, calls = bound_pipeline
    monkeypatch.setenv("PLAYWRIGHT_BROWSERS_PATH", "0")
    worker, pipeline = server.worker_service, server.application_pipeline_service

    start_run(worker.store)
    descriptor = os.open(worker.store.root / ".worker.lock", os.O_CREAT | os.O_RDWR, 0o600)
    fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
    worker.store.worker_lock_descriptor = descriptor
    html = (
        "<title>Service Engineer — Synthetic</title><h1>Service Engineer</h1><form>"
        '<label>Email *<input id="email" type="email" required></label>'
        '<label>Resume *<input id="resume" type="file" required></label>'
        '<label>Certificate<input id="certificate" type="file"></label>'
        '<label>Additional comments<textarea id="notes"></textarea></label>'
        '<button type="submit">Submit</button></form>'
    )
    posts = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True, channel="chromium")
        try:
            context = browser.new_context(offline=True)
            runner = ApplicationRunner(worker.store, context)

            def intercept(route):
                def fetch(**_options):
                    if route.request.method != "GET":
                        posts.append(route.request.url)
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
            deadline = time.monotonic() + 15
            while True:
                runner.tick()
                current = worker.store.load()["jobs"][0]
                if current["status"] == "ready_for_review":
                    break
                assert current["status"] in {"queued", "filling"}, {
                    key: current.get(key) for key in ("status", "reason", "error", "last_error")
                }
                assert time.monotonic() < deadline, current
                time.sleep(SAMPLE_INTERVAL)
            # Pause directly before the automatic handoff: the original Runner
            # and original Page are actual owned Chromium objects throughout.
            pipeline.pause()
            page = runner.pages[current["application_id"]]
            page.locator("#notes").fill("Retain this human text.")
            page.locator("#certificate").set_input_files(
                {
                    "name": "human-certificate.pdf",
                    "mimeType": "application/pdf",
                    "buffer": PDF_SAMPLE.read_bytes(),
                }
            )
            yield server, store, calls, runner, page, posts
        finally:
            browser.close()
            os.close(descriptor)


@pytest.mark.parametrize("late_bound", [True, False])
def test_contact_update_one_continue_replaces_only_original_resume(
    original_material_page, late_bound
):
    server, store, calls, runner, page, posts = original_material_page
    flow, worker, pipeline = (
        server.application_flow_service,
        server.worker_service,
        server.application_pipeline_service,
    )
    old = deepcopy(worker.store.load())
    original = flow.snapshot()["active_task"]
    pdf = store.pdf(original["resume_id"])
    page_id = runner.page_ids[page]
    put_information_answer(
        worker.store.answers,
        {
            "question": "Email",
            "value": "updated@example.invalid",
            "state": "confirmed",
            "scope": {},
        },
    )
    pipeline.continue_current(request_id="replace-original-resume-once")
    for _ in range(250):
        pipeline._tick()
        runner.tick()
        state = pipeline.snapshot()
        if state["status"] in {"ready_for_review", "needs_recheck", "needs_input"}:
            break
        time.sleep(0.01)
    state = choose_email_and_continue(
        server,
        runner,
        page,
        current_value="job@example.invalid",
        proposed_value="updated@example.invalid",
        request_id="adopt-updated-email-once",
    )
    task = flow.snapshot(original["id"])["active_task"]
    current = worker.store.load()["jobs"][0]
    assert state["status"] == "ready_for_review", {
        "pipeline": state["status"],
        "notification": state.get("notification"),
        "job": current.get("reason"),
        "continuation": current.get("continuation"),
        "update": {
            key: task.get("material_update", {}).get(key)
            for key in ("status", "error_code", "error_message")
        },
        "mirror": current.get("material_update"),
    }
    assert current["material_update"]["status"] == "complete"
    assert current["file_sha256"] != old["jobs"][0]["file_sha256"]
    assert task["analysis_id"] == original["analysis_id"]
    assert task["worker_ref"]["batch_id"] == original["worker_ref"]["batch_id"]
    assert runner.pages[current["application_id"]] is page
    assert runner.page_ids[page] == page_id and len(page.context.pages) == 1
    assert page.locator("#email").input_value() == "updated@example.invalid"
    assert page.locator("#notes").input_value() == "Retain this human text."
    assert page.locator("#certificate").evaluate("e => e.files[0].name") == "human-certificate.pdf"
    assert store.pdf(original["resume_id"]) == pdf
    assert len(calls) == 1 and len(store.prism_client.calls) == 2
    attempts = [
        row["intent"]
        for row in current["observations"]
        if row.get("action") == "action_result"
        and row.get("intent", {}).get("action") == "upload"
        and not row["intent"].get("material_id")
    ]
    assert len(attempts) == 2 and len({row["attempt_id"] for row in attempts}) == 2
    assert posts == []
    worker.store.check_single(current, worker.store.load())
    assert (
        pipeline.continue_current(request_id="replace-original-resume-once")["status"]
        == "ready_for_review"
    )
    # A retried participant delivery must not reopen an already completed update.
    update_id = task["material_update"]["id"]
    journal_path = flow.root / "material-updates" / f"{update_id}.json"
    files = (flow.path, worker.store.path, pipeline.path, journal_path)
    completed = tuple(path.read_bytes() for path in files)
    result = flow.commit_material_candidate(task["id"], update_id, bound=late_bound)
    assert result["material_update"]["status"] == "complete"
    assert tuple(path.read_bytes() for path in files) == completed
    assert pipeline.snapshot().get("material_update_id") is None
    result = worker.commit_material_update(
        current["application_id"], update_id, expected_batch_id=old["batch_id"]
    )
    assert result["status"] == "complete"
    assert tuple(path.read_bytes() for path in files) == completed
    # A cleared Pipeline pointer cannot become an authorization recovery context.
    with pytest.raises(PortalDataError) as rejected:
        pipeline.commit_material_authorization(update_id)
    assert rejected.value.code == "bound_material_journal_conflict"
    assert tuple(path.read_bytes() for path in files) == completed
    for corruption in (
        "controller",
        "attempt",
        "attachment",
        "late_failure",
        "not_applied",
        "active_intent",
    ):
        altered = worker.store.load()
        job = altered["jobs"][0]
        if corruption == "controller":
            altered["controller"] = "another-controller"
        else:
            mirror = job["material_update"]
            if corruption == "attempt":
                mirror["upload_attempt_id"] = "another-attempt"
            elif corruption == "attachment":
                mirror["new_attachment"]["sha256"] = "f" * 64
            else:
                intent = next(
                    row["intent"]
                    for row in job["observations"]
                    if row.get("action") == "action_result"
                    and row.get("intent", {}).get("attempt_id") == mirror["upload_attempt_id"]
                )
                if corruption == "late_failure":
                    job["observations"].append(
                        {
                            "stage": "requestfailed",
                            "intent": deepcopy(intent),
                            "application_id": job["application_id"],
                            "batch_id": altered["batch_id"],
                            "run_id": altered["runtime"]["id"],
                        }
                    )
                elif corruption == "not_applied":
                    job.setdefault("action_resolutions", []).append(
                        {
                            "intent_ref": mirror["upload_attempt_id"],
                            "intent": deepcopy(intent),
                            "conclusion": "not_applied",
                            "source": "Synthetic later readback",
                            "verified_by": "user",
                            "at": time.time(),
                            "observation_count": len(job["observations"]),
                            "run_id": altered["runtime"]["id"],
                        }
                    )
                else:
                    job["intent"] = deepcopy(intent)
        worker.store.save(altered)
        corrupted = tuple(path.read_bytes() for path in files)
        with pytest.raises(PortalDataError) as rejected:
            worker.commit_material_update(
                current["application_id"], update_id, expected_batch_id=old["batch_id"]
            )
        assert rejected.value.code == "bound_material_journal_conflict"
        assert tuple(path.read_bytes() for path in files) == corrupted
        if corruption == "not_applied":
            job["observations"].append(
                {
                    "action": "action_result",
                    "result": "verified",
                    "intent": deepcopy(intent),
                    "run_id": altered["runtime"]["id"],
                    "at": time.time(),
                }
            )
            worker.store.save(altered)
            verified = tuple(path.read_bytes() for path in files)
            result = worker.commit_material_update(
                current["application_id"], update_id, expected_batch_id=old["batch_id"]
            )
            assert result["status"] == "complete"
            assert tuple(path.read_bytes() for path in files) == verified
        worker.store.path.write_bytes(completed[1])
    later = worker.store.load()
    later_job = later["jobs"][0]
    later_job["intent"] = deepcopy(intent) | {"action": "fill", "attempt_id": "later-field"}
    later_job["observations"].append(
        {
            "stage": "requestfailed",
            "intent": deepcopy(later_job["intent"]),
            "application_id": later_job["application_id"],
            "batch_id": later["batch_id"],
            "run_id": later["runtime"]["id"],
        }
    )
    worker.store.save(later)
    unrelated = tuple(path.read_bytes() for path in files)
    result = worker.commit_material_update(
        current["application_id"], update_id, expected_batch_id=old["batch_id"]
    )
    assert result["status"] == "complete"
    assert tuple(path.read_bytes() for path in files) == unrelated
    worker.store.path.write_bytes(completed[1])


def test_two_contact_updates_keep_the_same_task_worker_and_page(original_material_page):
    test_contact_update_one_continue_replaces_only_original_resume(
        original_material_page, late_bound=False
    )
    server, store, calls, runner, page, posts = original_material_page
    worker, pipeline, flow = (
        server.worker_service,
        server.application_pipeline_service,
        server.application_flow_service,
    )
    runner.tick()  # Finish the original automatic manual-Submit handoff.
    first = flow.snapshot()["active_task"]
    assert first["material_update"]["status"] == "complete"
    put_information_answer(
        worker.store.answers,
        {"question": "Email", "value": "second@example.invalid", "state": "confirmed", "scope": {}},
    )
    pipeline.continue_current(request_id="second-bound-material-update")
    for _ in range(250):
        pipeline._tick()
        runner.tick()
        state = pipeline.snapshot()
        if state["status"] in {"ready_for_review", "needs_recheck", "needs_input"}:
            break
        time.sleep(0.01)
    state = choose_email_and_continue(
        server,
        runner,
        page,
        current_value="updated@example.invalid",
        proposed_value="second@example.invalid",
        request_id="adopt-second-updated-email",
    )
    final = flow.snapshot()["active_task"]
    assert state["status"] == "ready_for_review", state.get("notification")
    assert final["id"] == first["id"] and final["material_update"]["status"] == "complete"
    assert final["material_update_history"][0]["id"] == first["material_update"]["id"]
    assert final["resume_sha256"] != first["resume_sha256"]
    assert page.locator("#email").input_value() == "second@example.invalid"
    assert page.locator("#notes").input_value() == "Retain this human text."
    assert len(store.prism_client.calls) == 3 and len(calls) == 1 and posts == []


@pytest.mark.parametrize(
    "fault", ["manual_resume", "manual_email", "duplicate_resume", "lost_owner", "unknown_intent"]
)
def test_original_page_conflicts_preserve_manual_work_and_do_not_replace(
    original_material_page, fault
):
    server, store, _calls, runner, page, posts = original_material_page
    worker, pipeline = (
        server.worker_service,
        server.application_pipeline_service,
    )
    before = deepcopy(worker.store.load())
    if fault == "manual_resume":
        page.locator("#resume").set_input_files(
            {"name": "resume.pdf", "mimeType": "application/pdf", "buffer": PDF_SAMPLE.read_bytes()}
        )
    elif fault == "manual_email":
        page.locator("#email").fill("human-specific@example.invalid")
    elif fault == "duplicate_resume":
        page.evaluate(
            """() => {
              const label=document.createElement('label'); label.textContent='Resume';
              const f=document.createElement('input'); f.type='file'; f.name='resume';
              label.append(f); document.querySelector('form').append(label);
            }"""
        )
    elif fault == "lost_owner":
        fcntl.flock(worker.store.worker_lock_descriptor, fcntl.LOCK_UN)
    else:
        state = worker.store.load()
        state["jobs"][0]["intent"] = {
            "action": "upload",
            "attempt_id": "unknown-retained-attempt",
            "sha256": before["jobs"][0]["file_sha256"],
        }
        worker.store.save(state)
    put_information_answer(
        worker.store.answers,
        {
            "question": "Email",
            "value": "updated@example.invalid",
            "state": "confirmed",
            "scope": {},
        },
    )
    if fault == "unknown_intent":
        from career_evidence_graph.career_portal_data import PortalDataError

        with pytest.raises(PortalDataError):
            pipeline.continue_current(request_id="reject-original-" + fault)
        assert worker.store.load()["jobs"][0]["intent"]["attempt_id"] == "unknown-retained-attempt"
    else:
        pipeline.continue_current(request_id="reject-original-" + fault)
        for _ in range(250):
            pipeline._tick()
            runner.tick()
            if pipeline.snapshot()["status"] in {"needs_recheck", "needs_input"}:
                break
            time.sleep(0.01)
        assert pipeline.snapshot()["status"] in {"needs_recheck", "needs_input"}
    current = worker.store.load()["jobs"][0]
    successful = [
        row
        for row in current["observations"]
        if row.get("action") == "action_result"
        and row.get("intent", {}).get("action") == "upload"
        and not row["intent"].get("material_id")
    ]
    assert len(successful) == 1
    assert page.locator("#notes").input_value() == "Retain this human text."
    assert page.locator("#certificate").evaluate("e=>e.files[0].name") == "human-certificate.pdf"
    if fault == "manual_email":
        assert page.locator("#email").input_value() == "human-specific@example.invalid"
    assert posts == [] and len(page.context.pages) == 1


@pytest.mark.parametrize("point", ["journal", "flow", "worker", "pipeline", "bound_journal"])
def test_local_journal_recovers_through_public_continue_without_reexport_or_duplicate_upload(
    original_material_page, monkeypatch, point
):
    from career_evidence_graph._vendor import job_apply_store as helper
    from career_evidence_graph.career_portal_data import PortalDataError

    server, store, calls, runner, page, posts = original_material_page
    worker, pipeline, flow = (
        server.worker_service,
        server.application_pipeline_service,
        server.application_flow_service,
    )
    old = deepcopy(worker.store.load()["jobs"][0])
    put_information_answer(
        worker.store.answers,
        {
            "question": "Email",
            "value": "updated@example.invalid",
            "state": "confirmed",
            "scope": {},
        },
    )
    pipeline.continue_current(request_id="crash-original-" + point)
    task = flow.snapshot()["active_task"]
    for _ in range(200):
        task = flow.snapshot()["active_task"]
        if task.get("material_update", {}).get("status") != "preparing":
            break
        time.sleep(0.01)
    assert task["material_update"]["status"] == "awaiting_page"
    pipeline._tick()  # Queue the exact old Page inspection.
    runner.tick()
    assert worker.store.load()["jobs"][0]["material_update"]["status"] == "page_verified"
    candidate_id = flow.snapshot()["active_task"]["material_update"]["candidate"]["resume_id"]
    triggered = []
    if point in {"journal", "bound_journal"}:
        original_write = helper.atomic_write_json

        def write_then_crash(path, value, *args, **kwargs):
            original_write(path, value, *args, **kwargs)
            if (
                path.parent.name == "material-updates"
                and value.get("status") == ("bound" if point == "bound_journal" else "committing")
                and not triggered
            ):
                triggered.append(True)
                raise OSError("synthetic interrupted local material commit")

        monkeypatch.setattr(helper, "atomic_write_json", write_then_crash)
    else:
        target = {"flow": flow, "worker": worker.store, "pipeline": pipeline}[point]
        method = "save" if point == "worker" else "_save"
        original_save = getattr(target, method)

        def save_then_crash(state):
            original_save(state)
            hit = (
                point == "flow"
                and any(
                    row.get("material_update", {}).get("status") == "committing"
                    for row in state.get("tasks", [])
                )
                or point == "worker"
                and state["jobs"][0]["file_sha256"] != old["file_sha256"]
                or point == "pipeline"
                and state.get("transmission_authorization", {}).get("resume_id") == candidate_id
            )
            if hit and not triggered:
                triggered.append(True)
                raise OSError("synthetic interrupted local material commit")

        monkeypatch.setattr(target, method, save_then_crash)
    with pytest.raises(OSError):
        pipeline._tick()
    assert triggered
    partial = worker.store.load()
    with pytest.raises(PortalDataError):
        worker.store.check_single(partial["jobs"][0], partial)
    # A fresh public Continue resumes only the existing local journal. It does
    # not issue another draft/export or create a second remote upload attempt.
    pipeline.pause()
    pipeline.continue_current(request_id="recover-existing-" + point)
    for _ in range(200):
        pipeline._tick()
        runner.tick()
        if pipeline.snapshot()["status"] in {"ready_for_review", "needs_recheck", "needs_input"}:
            break
        time.sleep(0.01)
    choose_email_and_continue(
        server,
        runner,
        page,
        current_value="job@example.invalid",
        proposed_value="updated@example.invalid",
        request_id="adopt-recovered-email-" + point,
    )
    assert pipeline.snapshot()["status"] == "ready_for_review", pipeline.snapshot().get(
        "notification"
    )
    final = flow.snapshot()["active_task"]
    assert final["resume_id"] == candidate_id and final["material_update"]["status"] == "complete"
    assert len(store.prism_client.calls) == 2 and len(calls) == 1
    final_job = worker.store.load()["jobs"][0]
    uploads = [
        row
        for row in final_job["observations"]
        if row.get("action") == "action_result"
        and row.get("intent", {}).get("action") == "upload"
        and not row["intent"].get("material_id")
    ]
    assert len(uploads) == 2 and posts == [] and len(page.context.pages) == 1


def test_equal_pdf_bytes_reuses_verified_original_attachment_without_new_upload(
    original_material_page, monkeypatch
):
    server, store, calls, runner, page, posts = original_material_page
    worker, pipeline, flow = (
        server.worker_service,
        server.application_pipeline_service,
        server.application_flow_service,
    )
    original = flow.snapshot()["active_task"]
    old_pdf = store.pdf(original["resume_id"])
    compile_source = store.prism_client.compile
    monkeypatch.setattr(
        store.prism_client, "compile", lambda binding: compile_source(binding) | {"pdf": old_pdf}
    )
    put_information_answer(
        worker.store.answers,
        {
            "question": "Email",
            "value": "updated@example.invalid",
            "state": "confirmed",
            "scope": {},
        },
    )
    pipeline.continue_current(request_id="same-pdf-bytes")
    for _ in range(200):
        pipeline._tick()
        runner.tick()
        if pipeline.snapshot()["status"] in {"ready_for_review", "needs_recheck", "needs_input"}:
            break
        time.sleep(0.01)
    choose_email_and_continue(
        server,
        runner,
        page,
        current_value="job@example.invalid",
        proposed_value="updated@example.invalid",
        request_id="adopt-email-with-same-pdf",
    )
    assert pipeline.snapshot()["status"] == "ready_for_review", pipeline.snapshot().get(
        "notification"
    )
    current = worker.store.load()["jobs"][0]
    task = flow.snapshot()["active_task"]
    assert (
        task["resume_id"] != original["resume_id"]
        and task["resume_sha256"] == original["resume_sha256"]
    )
    uploads = [
        row
        for row in current["observations"]
        if row.get("action") == "action_result"
        and row.get("intent", {}).get("action") == "upload"
        and not row["intent"].get("material_id")
    ]
    assert len(uploads) == 1 and current["material_update"]["status"] == "complete"
    assert page.locator("#email").input_value() == "updated@example.invalid"
    assert len(store.prism_client.calls) == 2 and len(calls) == 1 and posts == []


@pytest.mark.parametrize("cancel", ["flow", "worker"])
def test_local_journal_never_overwrites_explicit_cancellation(
    original_material_page, monkeypatch, cancel
):
    from threading import Thread

    from test_career_portal_http import Portal

    from career_evidence_graph._vendor import job_apply_store as helper
    from career_evidence_graph.career_portal_data import PortalDataError

    server, _store, _calls, runner, _page, posts = original_material_page
    worker, pipeline, flow = (
        server.worker_service,
        server.application_pipeline_service,
        server.application_flow_service,
    )
    put_information_answer(
        worker.store.answers,
        {
            "question": "Email",
            "value": "updated@example.invalid",
            "state": "confirmed",
            "scope": {},
        },
    )
    pipeline.continue_current(request_id="cancel-journal-original")
    for _ in range(200):
        task = flow.snapshot()["active_task"]
        if task.get("material_update", {}).get("status") != "preparing":
            break
        time.sleep(0.01)
    pipeline._tick()
    runner.tick()
    original_write = helper.atomic_write_json
    failed = []

    def journal_only(path, value, *args, **kwargs):
        original_write(path, value, *args, **kwargs)
        if path.parent.name == "material-updates" and not failed:
            failed.append(True)
            raise OSError("synthetic interruption before first binding adoption")

    monkeypatch.setattr(helper, "atomic_write_json", journal_only)
    with pytest.raises(OSError):
        pipeline._tick()
    task = flow.snapshot()["active_task"]
    journals = {path: path.read_bytes() for path in (flow.root / "material-updates").glob("*.json")}
    assert journals
    thread = None
    try:
        if cancel == "flow":
            # The App's legacy Flow HTTP entry delegates whole-job cancellation to Pipeline.
            client = Portal(server, worker.store.applications.root, worker.store.single_career_root)
            thread = Thread(
                target=server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True
            )
            thread.start()
            status, _, raw = client.request(
                "POST",
                "/api/flow/cancel",
                body=json.dumps(
                    {"task_id": task["id"], "task_revision": task["revision"]}
                ).encode(),
                headers=client.write_headers(),
            )
            assert status == 200, raw
            response = json.loads(raw)
            assert response["status"] == "cancelled"
            assert response["cancellation"]["status"] == "complete"
            assert flow.task_snapshot(task["id"])["status"] == "cancelled"
            assert pipeline.snapshot()["active_task_id"] == task["id"]
        else:
            worker.request("cancel-job", {"application_id": task["application_id"]})
        cancelled = deepcopy(worker.store.load()["jobs"][0])
        assert cancelled["status"] == "cancelled"
        assert pipeline.snapshot()["enabled"] is True
        with pytest.raises(PortalDataError) as rejected:
            pipeline.continue_current(request_id="must-not-restore-cancelled")
        assert rejected.value.code != "pipeline_unavailable"
        if cancel == "flow":
            assert rejected.value.code == "pipeline_current_cancelled"
            assert flow.task_snapshot(task["id"])["status"] == "cancelled"
        assert worker.store.load()["jobs"][0] == cancelled
        assert {path: path.read_bytes() for path in journals} == journals
        assert runner.pages[task["application_id"]] is _page
        assert not _page.is_closed()
        assert posts == []
    finally:
        if thread is not None:
            server.shutdown()
            thread.join(timeout=2)
            assert not thread.is_alive()


def test_opening_editor_without_saving_keeps_current_pdf_and_one_continue(original_material_page):
    server, store, calls, runner, page, posts = original_material_page
    worker, pipeline, flow = (
        server.worker_service,
        server.application_pipeline_service,
        server.application_flow_service,
    )
    original = flow.snapshot()["active_task"]
    opened = flow.request(
        "begin-automatic-edit", {"task_id": original["id"], "task_revision": original["revision"]}
    )
    assert opened["material_update"]["status"] == "staged"
    pipeline.continue_current(request_id="unchanged-bound-editor")
    for _ in range(30):
        pipeline._tick()
        runner.tick()
        if pipeline.snapshot()["status"] in {"ready_for_review", "needs_input", "needs_recheck"}:
            break
    assert pipeline.snapshot()["status"] == "ready_for_review", pipeline.snapshot().get(
        "notification"
    )
    task = flow.snapshot()["active_task"]
    assert task["resume_id"] == original["resume_id"] and "material_update" not in task
    assert task["material_update_history"][-1]["status"] == "unchanged"
    assert len(store.prism_client.calls) == 1 and len(calls) == 1 and posts == []
    assert page.locator("#notes").input_value() == "Retain this human text."
    assert worker.store.load()["jobs"][0]["file_sha256"] == original["resume_sha256"]


def test_reusing_a_historical_pdf_hash_still_replaces_the_current_different_file(
    original_material_page,
):
    server, store, _calls, runner, page, posts = original_material_page
    original = server.application_flow_service.snapshot()["active_task"]
    test_two_contact_updates_keep_the_same_task_worker_and_page(original_material_page)
    runner.tick()
    worker, pipeline, flow = (
        server.worker_service,
        server.application_pipeline_service,
        server.application_flow_service,
    )
    put_information_answer(
        worker.store.answers,
        {"question": "Email", "value": "job@example.invalid", "state": "confirmed", "scope": {}},
    )
    pipeline.continue_current(request_id="return-to-historical-pdf-bytes")
    for _ in range(200):
        pipeline._tick()
        runner.tick()
        if pipeline.snapshot()["status"] in {"ready_for_review", "needs_recheck", "needs_input"}:
            break
        time.sleep(0.01)
    choose_email_and_continue(
        server,
        runner,
        page,
        current_value="second@example.invalid",
        proposed_value="job@example.invalid",
        request_id="adopt-historical-email-value",
    )
    assert pipeline.snapshot()["status"] == "ready_for_review", pipeline.snapshot().get(
        "notification"
    )
    current = worker.store.load()["jobs"][0]
    final = flow.snapshot()["active_task"]
    assert final["resume_sha256"] == original["resume_sha256"]
    assert final["material_update"]["status"] == "complete"
    uploads = [
        row
        for row in current["observations"]
        if row.get("action") == "action_result"
        and row.get("intent", {}).get("action") == "upload"
        and not row["intent"].get("material_id")
    ]
    assert len(uploads) == 4 and len({row["intent"]["attempt_id"] for row in uploads}) == 4
    assert page.locator("#email").input_value() == "job@example.invalid"
    assert page.locator("#notes").input_value() == "Retain this human text."
    assert len(store.prism_client.calls) == 4 and posts == []


def test_manual_source_then_contact_change_can_open_a_new_independent_editor(
    original_material_page,
):
    server, store, calls, runner, page, posts = original_material_page
    worker, pipeline, flow = (
        server.worker_service,
        server.application_pipeline_service,
        server.application_flow_service,
    )
    original = flow.snapshot()["active_task"]
    opened = flow.begin_automatic_edit(original["id"], original["revision"])
    draft = opened["material_update"]["editable_draft"]
    text = draft["latex_source"].replace(
        "Analyzed strategy; built 6 Python services.", "Built 6 Python services; analyzed strategy."
    )
    saved = flow.save_automatic_source(
        opened["id"], opened["revision"], draft["source_checkpoint"]["source_revision"], text
    )
    pipeline.continue_current(request_id="manual-before-contact")
    for _ in range(200):
        pipeline._tick()
        runner.tick()
        if pipeline.snapshot()["status"] in {"ready_for_review", "needs_recheck", "needs_input"}:
            break
        time.sleep(0.01)
    assert pipeline.snapshot()["status"] == "ready_for_review", pipeline.snapshot().get(
        "notification"
    )
    runner.tick()
    put_information_answer(
        worker.store.answers,
        {
            "question": "Email",
            "value": "updated@example.invalid",
            "state": "confirmed",
            "scope": {},
        },
    )
    pipeline.continue_current(request_id="contact-after-manual")
    for _ in range(200):
        pipeline._tick()
        runner.tick()
        if pipeline.snapshot()["status"] in {"ready_for_review", "needs_recheck", "needs_input"}:
            break
        time.sleep(0.01)
    choose_email_and_continue(
        server,
        runner,
        page,
        current_value="job@example.invalid",
        proposed_value="updated@example.invalid",
        request_id="adopt-email-after-manual-source",
    )
    assert pipeline.snapshot()["status"] == "ready_for_review", pipeline.snapshot().get(
        "notification"
    )
    runner.tick()
    latest = flow.snapshot()["active_task"]
    opened_again = flow.begin_automatic_edit(latest["id"], latest["revision"])
    next_draft = opened_again["material_update"]["editable_draft"]
    assert "Built 6 Python services; analyzed strategy." in next_draft["latex_source"]
    assert "updated@example.invalid" in next_draft["latex_source"]
    assert store.draft(saved["material_update"]["editable_draft"]["id"])["latex_source"] == text
    assert len(calls) == 1 and len(store.prism_client.calls) == 3 and posts == []
    assert page.locator("#notes").input_value() == "Retain this human text."
