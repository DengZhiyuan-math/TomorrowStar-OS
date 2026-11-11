"""Canonical original-Page Workable replacement through the actual Runner guard."""

import base64
import fcntl
import hashlib
import json
import os
import time
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

import pytest
from test_application_resume import task_resume as task_resume
from test_bound_material_update import bound_pipeline as bound_pipeline
from test_full_latex_generation import full_latex as full_latex
from test_workable_uploads import KEY, ORIGIN, PRESIGN, URL, descriptor
from test_workable_uploads import local_transport as local_transport
from worker_preview_support import advance_until

from career_evidence_graph.application_form_state import SAMPLE_INTERVAL
from career_evidence_graph.application_information import put_information_answer
from career_evidence_graph.application_worker import start_run
from career_evidence_graph.application_worker_browser import ApplicationRunner

pytestmark = pytest.mark.worker_browser


@pytest.mark.parametrize("bound_pipeline", [{"url": URL}], indirect=True)
@pytest.mark.parametrize(
    "read_fault", [None, "changed_attempt", "pause", "manual_submit", "unknown_result", "post"]
)
def test_workable_public_continue_replaces_original_page_resume(
    bound_pipeline, monkeypatch, local_transport, read_fault
):
    """Real canonical binding, actual Runner dispatch, synthetic loopback ATS.

    The fixture already runs synthetic mail -> matching -> materials -> strict
    single-job Worker admission. Only analysis/model/compiler external boundaries
    are fixture substitutes; this test never replaces single_validator.
    """
    from playwright.sync_api import sync_playwright

    monkeypatch.setenv("PLAYWRIGHT_BROWSERS_PATH", "0")
    server, store, calls = bound_pipeline
    worker, pipeline, flow = (
        server.worker_service,
        server.application_pipeline_service,
        server.application_flow_service,
    )
    initial = worker.store.load()
    old_job = deepcopy(initial["jobs"][0])
    assert old_job["job_url"] == URL
    worker.store.check_single(old_job, initial)
    old_pdf = Path(old_job["file_path"]).read_bytes()
    original = flow.snapshot()["active_task"]
    old_export_pdf = store.pdf(original["resume_id"])
    start_run(worker.store)
    lock_descriptor = os.open(worker.store.root / ".worker.lock", os.O_CREAT | os.O_RDWR, 0o600)
    fcntl.flock(lock_descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
    worker.store.worker_lock_descriptor = lock_descriptor
    origin, responses, wire = local_transport
    sent, denied, descriptors, remote_bytes = [], [], [], {}
    html = r"""<title>Service Engineer — Synthetic</title><h1>Service Engineer</h1><form>
      <label>Email *<input id="email" type="email" required></label>
      <div data-ui="resume"><label for="resume">Resume *</label>
        <input id="resume" name="resume" type="file" required>
        <span data-id="filename"></span><a data-action="view" hidden>View</a></div>
      <label>Additional comments<textarea id="notes"></textarea></label>
      <button type="submit">Submit Application</button></form><script>
      window.finalActions=0;document.querySelector('form').onsubmit=e=>{
        e.preventDefault();window.finalActions++};
      document.querySelector('#resume').onchange=async()=>{
        const f=document.querySelector('#resume').files[0];
        const h=await(await fetch(PRESIGN)).json(), data=new FormData();
        data.append('Content-Type',f.type);
        for(const [k,v] of Object.entries(h.uploadPostUrl.fields))data.append(k,v);
        data.append('file',f);
        const r=await fetch(h.uploadPostUrl.url,{method:'POST',body:data});
        if(!r.ok)throw Error('synthetic upload failed');await r.text();
        document.querySelector('[data-id=filename]').textContent=f.name;
        const view=document.querySelector('[data-action=view]');
        view.href=h.downloadUrl;view.hidden=false;
      };</script>""".replace("PRESIGN", json.dumps(PRESIGN))
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True, channel="chromium")
            try:
                context = browser.new_context(offline=True)
                runner = ApplicationRunner(worker.store, context)

                def intercept(route):
                    def send():
                        assert route.request.method == "GET" and route.request.url == URL
                        sent.append(("GET", URL))
                        route.fulfill(status=200, content_type="text/html", body=html)

                    def fetch(**options):
                        assert options == {"max_redirects": 0, "max_retries": 0, "timeout": 10000}
                        request = route.request
                        sent.append((request.method, request.url))
                        status, headers, content = 200, {}, b""
                        if request.method == "GET" and request.url == URL:
                            headers["Content-Type"] = "text/html"
                            content = html.encode()
                        elif request.method == "GET" and request.url == PRESIGN:
                            current = worker.store.load()["jobs"][0]
                            pdf = Path(current["file_path"]).read_bytes()
                            assert hashlib.sha256(pdf).hexdigest() == current["file_sha256"]
                            # Each actual Runner upload gets a different remote
                            # object while keeping the protocol's exact bounds.
                            next_key = KEY[:-1] + str(len(descriptors) + 1)
                            value = json.loads(json.dumps(descriptor()).replace(KEY, next_key))
                            fields = value["uploadPostUrl"]["fields"]
                            fields["Policy"] = base64.b64encode(
                                base64.b64decode(fields["Policy"]).replace(
                                    KEY.encode(), next_key.encode()
                                )
                            ).decode()
                            descriptors.append(deepcopy(value))
                            remote_bytes[value["downloadUrl"]] = pdf
                            headers["Content-Type"] = "application/json"
                            content = json.dumps(value).encode()
                        elif request.method == "POST" and request.url == ORIGIN + "/":
                            status = 204
                            headers["Access-Control-Allow-Origin"] = "https://apply.workable.com"
                        elif request.method == "GET" and request.url in remote_bytes:
                            content = remote_bytes[request.url]
                            headers = {
                                "Content-Type": "application/pdf",
                                "Access-Control-Allow-Origin": "https://apply.workable.com",
                            }
                        else:
                            pytest.fail("Unexpected dispatched synthetic request: " + request.url)
                        path = "/runner-replacement-" + str(len(responses))
                        responses[path] = status, headers, content
                        return route.fetch(url=origin + path, **options)

                    def abort(reason):
                        denied.append((route.request.method, route.request.url))
                        route.abort(reason)

                    runner._live_guard(
                        SimpleNamespace(
                            request=route.request,
                            continue_=send,
                            fetch=fetch,
                            fulfill=route.fulfill,
                            abort=abort,
                        )
                    )

                context.route("**/*", intercept)
                current = advance_until(
                    worker, runner, lambda row: row["status"] == "ready_for_review"
                )
                assert current["status"] == "ready_for_review", {
                    "reason": current.get("reason"),
                    "sent": sent,
                    "denied": denied,
                }
                page = runner.pages[current["application_id"]]
                page_id = runner.page_ids[page]
                old_adapter = runner.workable[page]
                old_handle = deepcopy(old_adapter.handle)
                assert old_adapter.remote_sha256 == old_job["file_sha256"]
                assert len(descriptors) == 1
                readback = old_adapter.readback
                interrupted = []

                def guarded_readback(retained_page):
                    allowance = runner.bound_material_read or {}
                    if read_fault and allowance.get("intent") is not None:
                        assert not interrupted
                        pending = worker.store.load()
                        pending_job = pending["jobs"][0]
                        interrupted.append(deepcopy(pending_job["intent"]))
                        assert allowance["intent"] == pending_job["intent"]
                        assert allowance["intent"] is not pending_job["intent"]
                        if read_fault == "changed_attempt":
                            pending_job["intent"]["attempt_id"] = (
                                "different-attempt-same-transaction"
                            )
                        elif read_fault == "pause":
                            pending["control"] = "paused"
                        elif read_fault == "manual_submit":
                            pending_job["submission_observation"] = {"conclusion": "unknown"}
                        elif read_fault == "unknown_result":
                            runner.transports.append(
                                {
                                    "stage": "requestfailed",
                                    "application_id": pending_job["application_id"],
                                    "run_id": runner.run_id,
                                    "batch_id": pending["batch_id"],
                                    "intent": deepcopy(pending_job["intent"]),
                                }
                            )
                        worker.store.save(pending)
                        if read_fault == "post":
                            retained_page.evaluate(
                                "url => fetch(url,{method:'POST',body:'forbidden'})"
                                ".catch(()=>null)",
                                old_handle["downloadUrl"],
                            )
                    return readback(retained_page)

                monkeypatch.setattr(old_adapter, "readback", guarded_readback)
                pipeline.pause()
                page.locator("#notes").fill("Retain this human text on the original Page.")
                put_information_answer(
                    worker.store.answers,
                    {
                        "question": "Email",
                        "value": "updated@example.invalid",
                        "state": "confirmed",
                        "scope": {},
                    },
                )
                pipeline.continue_current(request_id="workable-original-resume-once")
                for _ in range(300):
                    pipeline._tick()
                    runner.tick()
                    state = pipeline.snapshot()
                    if state["status"] in {"ready_for_review", "needs_recheck", "needs_input"}:
                        break
                    time.sleep(0.01)
                current = worker.store.load()["jobs"][0]
                task = flow.snapshot(original["id"])["active_task"]
                if read_fault:
                    assert interrupted
                    assert state["status"] != "ready_for_review"
                    assert len(descriptors) == 1
                    assert [method for method, url in sent if url == ORIGIN + "/"] == ["POST"]
                    assert runner.workable[page] is old_adapter
                    assert old_adapter.handle == old_handle
                    assert current["intent"] is not None
                    assert (
                        current["intent"]["material_update_id"]
                        == interrupted[0]["material_update_id"]
                    )
                    assert current["material_update"]["status"] == "bound"
                    assert (
                        page.locator("#notes").input_value()
                        == "Retain this human text on the original Page."
                    )
                    assert page.evaluate("window.finalActions") == 0
                    assert store.pdf(original["resume_id"]) == old_export_pdf
                    assert len(context.pages) == 1
                    assert (
                        "POST" if read_fault == "post" else "GET",
                        old_handle["downloadUrl"],
                    ) in denied
                    return
                assert state["status"] == "needs_input"
                assert current["reason"] == "form_differences"
                form = current["form_state"]
                assert len(form["differences"]) == 1
                difference = form["differences"][0]
                assert difference["question"] == "Email"
                assert difference["current_value"] == "job@example.invalid"
                assert difference["proposed_value"] == "updated@example.invalid"
                assert page.locator("#email").input_value() == "job@example.invalid"
                assert page.locator("#notes").input_value() == (
                    "Retain this human text on the original Page."
                )
                before_choice = list(sent)
                flow.worker_action(
                    task["id"],
                    task["revision"],
                    "resolve-form-differences",
                    {
                        "application_id": current["application_id"],
                        "binding": form["binding"],
                        "revision": form["revision"],
                        "choices": [{"difference_id": difference["id"], "action": "use"}],
                    },
                )
                assert sent == before_choice
                assert page.locator("#email").input_value() == "job@example.invalid"
                pipeline.continue_current(request_id="workable-confirm-email-once")
                deadline = time.monotonic() + 15
                while True:
                    pipeline._tick()
                    runner.tick()
                    state = pipeline.snapshot()
                    if state["status"] in {"ready_for_review", "needs_recheck", "needs_input"}:
                        break
                    assert time.monotonic() < deadline, state
                    page.wait_for_timeout(SAMPLE_INTERVAL * 1000)
                current = worker.store.load()["jobs"][0]
                task = flow.snapshot(original["id"])["active_task"]
                assert state["status"] == "ready_for_review", {
                    "pipeline": state["status"],
                    "notification": state.get("notification"),
                    "job": current.get("reason"),
                    "continuation": current.get("continuation"),
                    "update": task.get("material_update"),
                    "sent": sent,
                    "denied": denied,
                }
                new_pdf = Path(current["file_path"]).read_bytes()
                assert new_pdf != old_pdf and current["file_sha256"] != old_job["file_sha256"]
                assert current["material_update"]["status"] == "complete"
                assert task["analysis_id"] == original["analysis_id"]
                assert task["worker_ref"]["batch_id"] == original["worker_ref"]["batch_id"]
                assert runner.pages[current["application_id"]] is page
                assert runner.page_ids[page] == page_id and len(context.pages) == 1
                assert page.locator("#email").input_value() == "updated@example.invalid"
                assert page.locator("#notes").input_value() == (
                    "Retain this human text on the original Page."
                )
                assert page.evaluate("window.finalActions") == 0
                assert store.pdf(original["resume_id"]) == old_export_pdf
                assert len(calls) == 1 and len(store.prism_client.calls) == 2
                new_adapter = runner.workable[page]
                assert new_adapter is not old_adapter and new_adapter.handle != old_handle
                assert new_adapter.remote_sha256 == current["file_sha256"]
                assert old_adapter.handle == old_handle
                assert old_adapter.remote_sha256 == old_job["file_sha256"]
                assert len(descriptors) == 2
                assert descriptors[0]["downloadUrl"] != descriptors[1]["downloadUrl"]
                assert [method for method, url in sent if url == PRESIGN] == ["GET", "GET"]
                assert [method for method, url in sent if url == ORIGIN + "/"] == ["POST", "POST"]
                # Inspect and final dispatch verification read the archived old
                # remote object. Old and new download bodies remain separate.
                assert sent.count(("GET", descriptors[0]["downloadUrl"])) >= 2
                assert sent.count(("GET", descriptors[1]["downloadUrl"])) >= 1
                uploads = [body for method, _path, body in wire if method == "POST"]
                assert len(uploads) == 2
                assert uploads[0].count(old_pdf) == 1 and new_pdf not in uploads[0]
                assert uploads[1].count(new_pdf) == 1 and old_pdf not in uploads[1]
                attempts = [
                    row["intent"]
                    for row in current["observations"]
                    if row.get("action") == "action_result"
                    and row.get("intent", {}).get("action") == "upload"
                    and not row["intent"].get("material_id")
                ]
                assert len(attempts) == 2 and len({row["attempt_id"] for row in attempts}) == 2
                assert {row["sha256"] for row in attempts} == {
                    old_job["file_sha256"],
                    current["file_sha256"],
                }
                assert denied == []
                assert not any(
                    method != "GET" and ("/apply" in url or "/autofill" in url)
                    for method, url in sent
                )
                worker.store.check_single(current, worker.store.load())
                sent_before_replay = list(sent)
                assert (
                    pipeline.continue_current(request_id="workable-original-resume-once")["status"]
                    == "ready_for_review"
                )
                assert sent == sent_before_replay
            finally:
                browser.close()
    finally:
        os.close(lock_descriptor)
