"""One canonical manual-route job prepares materials before its first precision wait."""

import fcntl
import json
import os
import time
from pathlib import Path
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
from career_evidence_graph.validation.hashing import record_digest as digest

pytestmark = pytest.mark.worker_browser


def advance_precision(prepared, predicate, *, pipeline=None, timeout=15):
    pipeline = pipeline or prepared.pipeline
    deadline = time.monotonic() + timeout
    while True:
        pipeline._tick()
        prepared.engine.tick()
        state = pipeline.snapshot()
        if predicate(state):
            return state
        assert time.monotonic() < deadline, state
        prepared.page.wait_for_timeout(SAMPLE_INTERVAL * 1000)


@pytest.fixture
def precision_page(bound_pipeline, monkeypatch, request):
    from playwright.sync_api import sync_playwright

    from career_evidence_graph import application_materials, application_resume

    server, store, calls = bound_pipeline
    pipeline, worker, flow = (
        server.application_pipeline_service,
        server.worker_service,
        server.application_flow_service,
    )
    material_calls = []

    def delivered_inputs(_applications, flow_root, job):
        # This legacy orchestration fixture supplies its actual saved analysis
        # inputs through the existing source Adapter. J08 separately verifies
        # production P04 delivery reading, including incomplete-delivery stops.
        analysis_id = job["single_binding"]["analysis_id"]
        directory = Path(flow_root) / "analyses" / analysis_id
        saved = json.loads((directory / "synthetic-material-inputs.json").read_text())
        analysis = json.loads((directory / "analysis.json").read_text())
        assert saved["schema_version"] == "synthetic-material-inputs/v1"
        assert saved["analysis_id"] == analysis["id"] == analysis_id
        assert saved["application"]["id"] == analysis["application_id"] == job["application_id"]
        assert saved["application"]["revision"] == analysis["application_revision"]
        sources = saved["sources"]
        assert sources["revision"] == analysis["source_snapshot_revision"]
        assert sources["revision"] == digest(
            {key: value for key, value in sources.items() if key != "revision"}
        )
        return {"application": saved["application"], "sources": sources}

    worker.store.single_material_source_provider = delivered_inputs

    def material_model(config, prompt, **kwargs):
        material_calls.append(config.output_schema.name)
        if getattr(request, "param", {}).get("unknown_material"):
            raise TimeoutError("Synthetic material response was lost after dispatch")
        data = json.loads(prompt[prompt.index("{") :])
        if config.output_schema.name == "validation-schema.json":
            result = {"supported": True, "reason": "Retained exact synthetic source"}
        else:
            source = next(
                item
                for item in data["sources"]
                if item.get("attribution") == "User"
                and item.get("rewrite_allowed")
                and item.get("text")
            )
            result = {
                "language": "en",
                "paragraphs": [
                    {
                        "kind": "fact",
                        "text": source["text"],
                        "source_ids": [source["source_id"]],
                        "source_quotes": [source["text"]],
                    }
                ],
            }
        return SimpleNamespace(
            structured_result=result, model_dump=lambda **kw: {"synthetic": True}
        )

    monkeypatch.setenv("PLAYWRIGHT_BROWSERS_PATH", "0")
    monkeypatch.setattr(application_materials, "run_codex_exec", material_model)
    monkeypatch.setattr(
        application_resume, "export_pdf", lambda html, pdf: pdf.write_bytes(PDF_SAMPLE.read_bytes())
    )
    state = worker.store.load()
    assert len(state["jobs"]) == 1, (
        "First precision wait must follow original-Page material discovery"
    )
    start_run(worker.store)
    descriptor = os.open(worker.store.root / ".worker.lock", os.O_CREAT | os.O_RDWR, 0o600)
    fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
    worker.store.worker_lock_descriptor = descriptor
    html = """<title>Service Engineer — Synthetic</title><h1>Service Engineer</h1><form>
      <label>Email *<input id=email type=email required></label>
      <label>Resume *<input id=resume type=file required></label>
      <label>Cover letter *<input id=cover type=file required></label>
      <label>Why this company? *<textarea id=why required></textarea></label>
      <button type=submit>Submit</button></form><script>
      window.finalActions=0;document.querySelector('form').onsubmit=e=>{e.preventDefault();window.finalActions++};
      </script>"""
    if getattr(request, "param", {}).get("certificate"):
        html = html.replace(
            "<button type=submit>",
            "<label>Certificate *<input id=certificate type=file required></label>"
            "<button type=submit>",
        )
    if getattr(request, "param", {}).get("no_cover"):
        html = html.replace("<label>Cover letter *<input id=cover type=file required></label>", "")
    if getattr(request, "param", {}).get("remote_workable"):
        html = html.replace(
            "<label>Resume *<input id=resume type=file required></label>",
            '<div data-ui="resume"><label>Resume *<input id=resume type=file required></label>'
            '<span data-id="filename">resume.pdf</span><a data-action="view" '
            'href="https://remote.example.test/old-resume">View</a></div>',
        )
    sent = []
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True, channel="chromium")
            try:
                context = browser.new_context(offline=True)
                engine = ApplicationRunner(worker.store, context)

                def intercept(route):
                    def fetch(**options):
                        sent.append((route.request.method, route.request.url))
                        return SimpleNamespace(status=200, dispose=lambda: None)

                    engine._live_guard(
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
                for _ in range(100):
                    pipeline._tick()
                    engine.tick()
                    current = pipeline.snapshot()
                    if current.get("wait_reason") == "precision_adjustment":
                        break
                    if worker.store.load()["jobs"][0].get("reason") == "missing_materials":
                        pipeline._tick()
                        break
                    if worker.store.load()["jobs"][0].get("status") == "needs_recheck":
                        pipeline._tick()
                        break
                    time.sleep(0.01)
                yield SimpleNamespace(
                    server=server,
                    store=store,
                    calls=calls,
                    pipeline=pipeline,
                    worker=worker,
                    flow=flow,
                    engine=engine,
                    context=context,
                    browser=browser,
                    page=engine.pages[worker.store.load()["jobs"][0]["application_id"]],
                    material_calls=material_calls,
                    sent=sent,
                )
            finally:
                browser.close()
    finally:
        os.close(descriptor)


@pytest.mark.parametrize(
    "bound_pipeline",
    [{"application_strategy": "manual", "stop_at": "needs_input"}],
    indirect=True,
)
@pytest.mark.parametrize("continue_once", [False, True])
def test_first_precision_wait_has_all_required_drafts_and_an_empty_original_page(
    precision_page, continue_once
):
    calls = precision_page.calls
    pipeline, worker, flow = precision_page.pipeline, precision_page.worker, precision_page.flow
    engine, context = precision_page.engine, precision_page.context
    material_calls, sent = precision_page.material_calls, precision_page.sent
    current = pipeline.snapshot()
    assert (
        current["status"] == "needs_input" and current["wait_reason"] == "precision_adjustment"
    ), current
    state = worker.store.load()
    job = state["jobs"][0]
    task = flow.snapshot(current["active_task_id"])["active_task"]
    assert state["control"] == "paused"
    assert task["resume_id"] and task["resume_sha256"]
    assert len(state["jobs"]) == 1 and len(context.pages) == 1
    page = engine.pages[job["application_id"]]
    assert page.locator("#email").input_value() == ""
    assert page.locator("#why").input_value() == ""
    assert page.locator("input[type=file]").evaluate_all(
        "nodes=>nodes.every(e=>e.files.length===0)"
    )
    assert {row["kind"] for row in job["materials"]} == {
        "cover_letter",
        "motivation_text",
    }
    assert all(
        row["status"] == "ready" and row["attempt_id"] and row["source_binding"]["sources"]
        for row in job["materials"]
    )
    assert len(material_calls) == 4 and len(calls) == 1
    assert not any(
        row.get("intent", {}).get("action") in {"fill", "upload", "advance"}
        for row in job["observations"]
    )
    assert all(method == "GET" for method, url in sent)
    assert page.evaluate("window.finalActions") == 0
    worker.store.check_single(job, state)
    for _ in range(3):
        engine.tick()
        pipeline._tick()
    assert len(material_calls) == 4 and worker.store.load()["control"] == "paused"
    assert page.locator("#why").input_value() == ""
    if continue_once:
        original_job_id = job["application_id"]
        original_page_id = engine.page_ids[page]
        original_grant = current["authorization"]["id"]
        pipeline.continue_current(request_id="precision-once")
        result = advance_precision(
            precision_page, lambda state: state["status"] in {"ready_for_review", "needs_recheck"}
        )
        assert result["status"] == "ready_for_review", result
        finished = worker.store.load()["jobs"][0]
        assert finished["application_id"] == original_job_id
        assert engine.pages[original_job_id] is page
        assert engine.page_ids[page] == original_page_id and len(context.pages) == 1
        assert result["authorization"]["id"] == original_grant
        assert len(material_calls) == 4 and len(calls) == 1
        assert page.locator("#email").input_value() == "job@example.invalid"
        assert page.locator("#why").input_value()
        assert page.locator("input[type=file]").evaluate_all(
            "nodes=>nodes.every(e=>e.files.length===1)"
        )
        assert page.evaluate("window.finalActions") == 0
        assert pipeline.continue_current(request_id="precision-once") == result


@pytest.mark.parametrize(
    "bound_pipeline", [{"application_strategy": "manual", "stop_at": "needs_input"}], indirect=True
)
@pytest.mark.parametrize("edit_kind", ["contact", "source", "samebytes_source"])
def test_contact_edit_after_precision_wait_sends_only_the_first_new_resume(
    precision_page, edit_kind, monkeypatch
):
    p = precision_page
    old = p.worker.store.load()["jobs"][0]
    original = p.flow.snapshot()["active_task"]
    old_pdf = p.store.pdf(original["resume_id"])
    if edit_kind == "samebytes_source":
        compile_source = p.store.prism_client.compile
        monkeypatch.setattr(
            p.store.prism_client,
            "compile",
            lambda binding: compile_source(binding) | {"pdf": old_pdf},
        )
    assert p.page.locator("#resume").evaluate("e=>e.files.length") == 0
    if edit_kind == "contact":
        put_information_answer(
            p.worker.store.answers,
            {
                "question": "Email",
                "value": "precision@example.invalid",
                "state": "confirmed",
                "scope": {},
            },
        )
    else:
        editing = p.flow.begin_automatic_edit(original["id"], original["revision"])
        draft = editing["material_update"]["editable_draft"]
        changed = draft["latex_source"].replace(
            "Analyzed strategy; built 6 Python services.",
            "Built 6 Python services; analyzed strategy.",
        )
        assert changed != draft["latex_source"]
        p.flow.save_automatic_source(
            editing["id"],
            editing["revision"],
            draft["source_checkpoint"]["source_revision"],
            changed,
        )
    p.pipeline.continue_current(request_id="precision-contact-once")
    result = advance_precision(
        p, lambda state: state["status"] in {"ready_for_review", "needs_recheck"}
    )
    assert result["status"] == "ready_for_review", result
    job = p.worker.store.load()["jobs"][0]
    task = p.flow.snapshot()["active_task"]
    uploads = [
        row["intent"]
        for row in job["observations"]
        if row.get("action") == "action_result" and row.get("intent", {}).get("kind") == "resume"
    ]
    assert len(uploads) == 1 and uploads[0]["sha256"] == job["file_sha256"]
    assert "replaces_sha256" not in uploads[0], "No old remote resume existed to replace"
    assert (job["file_sha256"] == old["file_sha256"]) is (edit_kind == "samebytes_source")
    assert p.store.pdf(original["resume_id"]) == old_pdf
    if edit_kind == "contact":
        assert "precision@example.invalid" in p.store.read_export(task["resume_id"])["latex_source"]
        assert p.page.locator("#email").input_value() == "precision@example.invalid"
    else:
        assert (
            "Built 6 Python services; analyzed strategy."
            in p.store.read_export(task["resume_id"])["latex_source"]
        )
    assert p.page.evaluate("window.finalActions") == 0 and len(p.context.pages) == 1
    assert len(p.material_calls) == 4


@pytest.mark.parametrize(
    "bound_pipeline", [{"application_strategy": "manual", "stop_at": "needs_input"}], indirect=True
)
@pytest.mark.parametrize("precision_page", [{"certificate": True}], indirect=True)
def test_missing_certificate_waits_before_precision_then_reuses_the_original_drafts(precision_page):
    p = precision_page
    state = p.worker.store.load()
    job = state["jobs"][0]
    assert job["reason"] == "missing_materials"
    assert p.pipeline.snapshot().get("wait_reason") != "precision_adjustment"
    assert state["control"] == "paused"
    assert len(p.material_calls) == 4
    assert p.page.locator("#resume").evaluate("e=>e.files.length") == 0
    p.page.locator("#certificate").set_input_files(
        {
            "name": "certificate.pdf",
            "mimeType": "application/pdf",
            "buffer": PDF_SAMPLE.read_bytes(),
        }
    )
    p.pipeline.continue_current(request_id="certificate-provided")
    for _ in range(50):
        p.pipeline._tick()
        p.engine.tick()
        result = p.pipeline.snapshot()
        if result.get("wait_reason") == "precision_adjustment":
            break
    assert result.get("wait_reason") == "precision_adjustment", result
    assert p.worker.store.load()["control"] == "paused" and len(p.material_calls) == 4
    assert p.page.locator("#resume").evaluate("e=>e.files.length") == 0
    assert p.page.locator("#certificate").evaluate("e=>e.files[0].name") == "certificate.pdf"
    assert p.page.evaluate("window.finalActions") == 0


@pytest.mark.parametrize(
    "bound_pipeline", [{"application_strategy": "manual", "stop_at": "needs_input"}], indirect=True
)
@pytest.mark.parametrize("stop_action", ["pause", "cancel-job", "skip"])
def test_a_later_stop_wins_over_a_queued_precision_continue(precision_page, stop_action):
    p = precision_page
    job = p.worker.store.load()["jobs"][0]
    p.pipeline.continue_current(request_id="queued-before-stop")
    if stop_action == "pause":
        p.pipeline.pause()
    elif stop_action == "skip":
        p.pipeline.skip_current(request_id="skip-before-consume")
    else:
        p.worker.request("cancel-job", {"application_id": job["application_id"]})
    p.engine.tick()
    state = p.worker.store.load()
    stopped = state["jobs"][0]
    assert state["control"] != "running"
    assert stopped["precision_preparation"]["status"] == "ready"
    assert stopped["status"] == ("cancelled" if stop_action == "cancel-job" else "needs_input")
    assert stopped["continuation"]["status"] == "cancelled"
    assert "queued-before-stop" in stopped["continuation_requests"]
    assert p.page.locator("#email").input_value() == ""
    assert p.page.locator("#resume").evaluate("e=>e.files.length") == 0
    assert len(p.material_calls) == 4 and p.page.evaluate("window.finalActions") == 0


@pytest.mark.parametrize(
    "bound_pipeline",
    [
        {
            "application_strategy": "manual",
            "stop_at": "needs_input",
            "job_description": "Please submit a cover letter. Operate service systems.",
        }
    ],
    indirect=True,
)
@pytest.mark.parametrize("precision_page", [{"no_cover": True}], indirect=True)
@pytest.mark.parametrize("expose_later", [False, True])
def test_jd_only_required_cover_is_ready_before_the_first_precision_wait(
    precision_page, expose_later
):
    p = precision_page
    job = p.worker.store.load()["jobs"][0]
    covers = [row for row in job.get("materials", []) if row.get("kind") == "cover_letter"]
    assert len(covers) == 1, "A required attachment explicitly in the JD is already known"
    cover = covers[0]
    assert cover["origin"] == "jd" and cover["requirement_id"]
    assert "field_id" not in cover and "draft_path" not in cover
    assert cover["status"] == "ready" and cover["sha256"] and cover["source_binding"]["sources"]
    assert cover["jd_source"]["jd_quote"] == "Please submit a cover letter."
    assert p.pipeline.snapshot()["wait_reason"] == "precision_adjustment"
    assert p.worker.store.load()["control"] == "paused" and len(p.material_calls) == 4
    assert p.page.locator("#resume").evaluate("e=>e.files.length") == 0
    assert (
        p.page.locator("#why").input_value() == "" and p.page.evaluate("window.finalActions") == 0
    )
    if expose_later:
        original_material_id, original_attempt = cover["id"], cover["attempt_id"]
        p.page.evaluate(
            "document.querySelector('form').insertAdjacentHTML('beforeend',"
            "'<label>Cover letter *<input id=late-cover type=file required></label>')"
        )
        p.pipeline.continue_current(request_id="late-cover-once")
        result = advance_precision(
            p, lambda state: state["status"] in {"ready_for_review", "needs_recheck"}
        )
        assert result["status"] == "ready_for_review", result
        covers = [
            row
            for row in p.worker.store.load()["jobs"][0]["materials"]
            if row["kind"] == "cover_letter"
        ]
        assert len(covers) == 1 and covers[0]["id"] == original_material_id
        assert covers[0]["attempt_id"] == original_attempt and len(p.material_calls) == 4
        assert (
            covers[0]["field_id"]
            == next(
                field["id"]
                for field in p.engine.observe(p.page, p.worker.store.load()["jobs"][0])["fields"]
                if field["question"].strip().rstrip(" *") == "Cover letter"
            )
            and covers[0]["requirement_id"] == cover["requirement_id"]
        )
        assert p.page.locator("#late-cover").evaluate("e=>e.files[0].name") == "cover-letter.pdf"
        assert p.page.evaluate("window.finalActions") == 0


@pytest.mark.parametrize(
    "bound_pipeline",
    [
        {
            "application_strategy": "manual",
            "stop_at": "needs_input",
            "url": "https://jobs.ashbyhq.com/synthetic/00000000-0000-0000-0000-000000000001/application",
        }
    ],
    indirect=True,
)
@pytest.mark.parametrize("operation", ["ApiSetFormValue", "ApiCreateFileUploadHandle"])
def test_precision_wait_allows_actual_schema_post_but_never_a_mutation(precision_page, operation):
    from test_ashby_drafts import QUERIES, endpoint, form

    p = precision_page
    sent, denied = [], []
    draft = p.engine.drafts[p.page]

    def intercept(route):
        def fetch(**kwargs):
            sent.append(route.request.url)
            return SimpleNamespace(status=200, dispose=lambda: None)

        def abort(reason):
            denied.append(route.request.url)
            route.abort(reason)

        p.engine._live_guard(
            SimpleNamespace(
                request=route.request,
                fetch=fetch,
                abort=abort,
                fulfill=lambda *, response: route.fulfill(
                    status=200,
                    content_type="application/json",
                    body=json.dumps(
                        {
                            "data": {
                                "jobPosting": {
                                    "id": draft.posting,
                                    "title": "Service Engineer",
                                    "applicationForm": form({}),
                                }
                            }
                        }
                    ),
                ),
            )
        )

    p.context.route("**/api/non-user-graphql*", intercept)

    def request(op, variables):
        return p.page.evaluate(
            "async ({url,body})=>fetch(url,{method:'POST',"
            "headers:{'Content-Type':'application/json'},body})"
            ".then(r=>r.json()).catch(()=>null)",
            {
                "url": endpoint(op),
                "body": json.dumps(
                    {"operationName": op, "variables": variables, "query": QUERIES[op]}
                ),
            },
        )

    assert request(
        "ApiJobPosting",
        {"organizationHostedJobsPageName": "synthetic", "jobPostingId": draft.posting},
    )
    variables = {"organizationHostedJobsPageName": "synthetic"}
    variables.update(
        {
            "formRenderIdentifier": "render-one",
            "formDefinitionIdentifier": "definition-one",
            "path": "email",
            "value": "should-not-send@example.invalid",
        }
        if operation == "ApiSetFormValue"
        else {
            "fileUploadContext": "NonUserFormEngine",
            "filename": "cover-letter.pdf",
            "contentType": "application/pdf",
            "contentLength": 100,
        }
    )
    assert request(operation, variables) is None
    assert sent == [endpoint("ApiJobPosting")] and denied == [endpoint(operation)]
    assert p.worker.store.load()["control"] == "paused"
    assert p.page.locator("#email").input_value() == ""
    assert p.page.locator("#resume").evaluate("e=>e.files.length") == 0
    assert p.page.evaluate("window.finalActions") == 0


@pytest.mark.parametrize(
    "bound_pipeline", [{"application_strategy": "manual", "stop_at": "needs_input"}], indirect=True
)
@pytest.mark.parametrize("retain", ["reopen", "skip-return"])
def test_explicit_precision_wait_retains_its_page_drafts_and_grant(precision_page, retain):
    from career_evidence_graph.application_pipeline import ApplicationPipeline

    p = precision_page
    original = p.pipeline.snapshot()
    original_job = p.worker.store.load()["jobs"][0]
    pipeline = p.pipeline
    if retain == "reopen":
        pipeline.close()
        pipeline = ApplicationPipeline(
            p.flow, p.server.application_intake_service, p.worker, interval=100
        )
    try:
        if retain == "skip-return":
            pipeline.skip_current(request_id="retain-skip")
            assert p.worker.store.load()["current_job_id"] is None
            pipeline.return_to(original_job["application_id"], request_id="retain-return")
        for _ in range(3):
            pipeline._tick()
            p.engine.tick()
        state = pipeline.snapshot()
        assert state["control"] == "paused" and state["wait_reason"] == "precision_adjustment"
        assert p.engine.pages[original_job["application_id"]] is p.page
        assert p.worker.store.load()["jobs"][0]["materials"] == original_job["materials"]
        assert state["authorization"]["id"] == original["authorization"]["id"]
        assert len(p.material_calls) == 4 and p.page.locator("#why").input_value() == ""
        pipeline.continue_current(request_id="retained-precision-once")
        state = advance_precision(
            p,
            lambda state: state["status"] in {"ready_for_review", "needs_recheck"},
            pipeline=pipeline,
        )
        assert state["status"] == "ready_for_review", state
        assert len(p.material_calls) == 4 and len(p.context.pages) == 1
        assert p.page.evaluate("window.finalActions") == 0
    finally:
        if pipeline is not p.pipeline:
            pipeline.close()


@pytest.mark.parametrize(
    "bound_pipeline",
    [
        {
            "application_strategy": "manual",
            "stop_at": "needs_input",
            "job_description": "Please submit a cover letter. Operate service systems.",
        }
    ],
    indirect=True,
)
@pytest.mark.parametrize("precision_page", [{"no_cover": True, "certificate": True}], indirect=True)
def test_real_certificate_can_be_provided_beside_a_jd_only_cover(precision_page):
    import base64

    p = precision_page
    job = p.worker.store.load()["jobs"][0]
    assert any(row.get("origin") == "jd" and "field_id" not in row for row in job["materials"])
    missing = next(row for row in job["materials"] if row["kind"] == "certificate")
    assert missing["status"] == "needs_input" and p.worker.store.load()["control"] == "paused"
    p.worker.request(
        "provide-material",
        {
            "application_id": job["application_id"],
            "field_id": missing["field_id"],
            "draft_path": missing["draft_path"],
            "kind": "certificate",
            "request_id": "actual-certificate",
            "filename": "certificate.pdf",
            "file_base64": base64.b64encode(PDF_SAMPLE.read_bytes()).decode(),
        },
    )
    p.pipeline.continue_current(request_id="certificate-ready")
    for _ in range(40):
        p.pipeline._tick()
        p.engine.tick()
        result = p.pipeline.snapshot()
        if result.get("wait_reason") == "precision_adjustment":
            break
    assert result.get("wait_reason") == "precision_adjustment", result
    job = p.worker.store.load()["jobs"][0]
    supplied = next(row for row in job["materials"] if row["kind"] == "certificate")
    assert supplied["actor"] == "user" and supplied["status"] == "ready"
    assert supplied["source_binding"]["provided_file"] is True
    assert (
        len(p.material_calls) == 4
        and p.page.locator("#certificate").evaluate("e=>e.files.length") == 0
    )
    assert p.page.locator("#resume").evaluate("e=>e.files.length") == 0


@pytest.mark.parametrize(
    "bound_pipeline",
    [
        {
            "application_strategy": "manual",
            "stop_at": "needs_input",
            "job_description": "Please submit a safety certificate and a training certificate. "
            "Operate service systems.",
        }
    ],
    indirect=True,
)
def test_jd_certificates_are_provided_by_their_exact_local_requirement(precision_page):
    import base64

    from career_evidence_graph.career_portal_data import PortalDataError

    p = precision_page
    job = p.worker.store.load()["jobs"][0]
    requirements = [
        row
        for row in job["materials"]
        if row.get("origin") == "jd" and row["kind"] == "certificate"
    ]
    assert len(requirements) == 2 and all("field_id" not in row for row in requirements)

    def provide(requirement_id, request_id):
        return p.worker.request(
            "provide-material",
            {
                "application_id": job["application_id"],
                "requirement_id": requirement_id,
                "kind": "certificate",
                "request_id": request_id,
                "filename": "certificate.pdf",
                "file_base64": base64.b64encode(PDF_SAMPLE.read_bytes()).decode(),
            },
        )

    with pytest.raises(PortalDataError):
        provide("different-requirement", "wrong-requirement")
    provide(requirements[0]["requirement_id"], "certificate-one")
    rows = [
        row for row in p.worker.store.load()["jobs"][0]["materials"] if row.get("origin") == "jd"
    ]
    assert [row["status"] for row in rows] == ["ready", "needs_input"]
    provide(requirements[1]["requirement_id"], "certificate-two")
    p.pipeline.continue_current(request_id="both-certificates-provided")
    for _ in range(40):
        p.pipeline._tick()
        p.engine.tick()
        result = p.pipeline.snapshot()
        if result.get("wait_reason") == "precision_adjustment":
            break
    assert result.get("wait_reason") == "precision_adjustment", result
    rows = [
        row for row in p.worker.store.load()["jobs"][0]["materials"] if row.get("origin") == "jd"
    ]
    assert all(
        row["status"] == "ready" and row["actor"] == "user" and "field_id" not in row
        for row in rows
    )
    assert all(
        row["source_binding"]["provided_file"] and row["jd_source"]["jd_sha256"] for row in rows
    )
    assert (
        p.worker.store.load()["control"] == "paused"
        and p.page.locator("#resume").evaluate("e=>e.files.length") == 0
    )
    assert p.page.evaluate("window.finalActions") == 0


@pytest.mark.parametrize(
    "bound_pipeline",
    [
        {
            "application_strategy": "manual",
            "stop_at": "needs_input",
            "job_description": "Please submit a cover letter. Operate service systems.",
        }
    ],
    indirect=True,
)
@pytest.mark.parametrize("precision_page", [{"no_cover": True}], indirect=True)
def test_an_unmapped_required_jd_file_cannot_be_reported_as_sent(precision_page):
    p = precision_page
    assert p.pipeline.snapshot()["wait_reason"] == "precision_adjustment"
    p.pipeline.continue_current(request_id="unknown-cover-destination")
    result = advance_precision(
        p, lambda state: state["status"] in {"ready_for_review", "needs_input", "needs_recheck"}
    )
    assert result["status"] == "needs_input", result
    job = p.worker.store.load()["jobs"][0]
    assert job["reason"] == "material_field_mapping_required"
    assert len(p.material_calls) == 4
    assert len([row for row in job["materials"] if row.get("kind") == "cover_letter"]) == 1
    assert p.page.evaluate("window.finalActions") == 0


@pytest.mark.parametrize(
    "bound_pipeline",
    [
        {
            "application_strategy": "manual",
            "stop_at": "needs_input",
            "url": "https://apply.workable.com/synthetic-employer/j/SYNTHETIC1/apply/",
        }
    ],
    indirect=True,
)
@pytest.mark.parametrize("precision_page", [{"remote_workable": True}], indirect=True)
@pytest.mark.parametrize("change_contact", [False, True])
def test_an_unverified_remote_resume_is_never_mistaken_for_an_empty_first_upload(
    precision_page, change_contact
):
    p = precision_page
    original = p.flow.snapshot()["active_task"]
    assert p.page.locator("#resume").evaluate("e=>e.files.length") == 0
    if change_contact:
        put_information_answer(
            p.worker.store.answers,
            {
                "question": "Email",
                "value": "new@example.invalid",
                "state": "confirmed",
                "scope": {},
            },
        )
    p.pipeline.continue_current(request_id="remote-is-not-empty")
    for _ in range(100):
        p.pipeline._tick()
        p.engine.tick()
        result = p.pipeline.snapshot()
        if result["status"] == "needs_recheck":
            break
        time.sleep(0.01)
    job = p.worker.store.load()["jobs"][0]
    assert result["status"] == "needs_recheck", result
    assert p.flow.snapshot()["active_task"]["resume_id"] == original["resume_id"]
    assert p.page.locator("#email").input_value() == ""
    assert p.page.locator("#resume").evaluate("e=>e.files.length") == 0
    assert not any(
        row.get("intent", {}).get("action") in {"fill", "upload"} for row in job["observations"]
    )
    assert (
        p.page.locator('[data-action="view"]').get_attribute("href")
        == "https://remote.example.test/old-resume"
    )
    assert p.page.evaluate("window.finalActions") == 0


@pytest.mark.parametrize(
    "bound_pipeline", [{"application_strategy": "manual", "stop_at": "needs_input"}], indirect=True
)
@pytest.mark.parametrize("precision_page", [{"unknown_material": True}], indirect=True)
def test_unknown_material_attempt_keeps_the_original_precision_job_waiting(precision_page):
    p = precision_page
    job = p.worker.store.load()["jobs"][0]
    failed = next(row for row in job["materials"] if row["status"] == "needs_recheck")
    attempt = failed["attempt_id"]
    assert len(p.material_calls) == 1 and p.worker.store.load()["control"] == "paused"
    assert p.pipeline.snapshot().get("wait_reason") != "precision_adjustment"
    for _ in range(3):
        p.pipeline._tick()
        p.engine.tick()
    p.pipeline.continue_current(request_id="unknown-material-once")
    for _ in range(20):
        p.pipeline._tick()
        p.engine.tick()
        result = p.pipeline.snapshot()
        if result["status"] == "needs_recheck":
            break
    assert result["status"] == "needs_recheck", result
    current = p.worker.store.load()["jobs"][0]
    assert (
        next(row for row in current["materials"] if row["attempt_id"] == attempt)["status"]
        == "needs_recheck"
    )
    assert len(p.material_calls) == 1 and current["precision_preparation"]["status"] == "preparing"
    assert p.page.locator("#resume").evaluate("e=>e.files.length") == 0
    assert (
        p.page.locator("#why").input_value() == "" and p.page.evaluate("window.finalActions") == 0
    )


@pytest.mark.parametrize(
    "bound_pipeline",
    [
        {
            "application_strategy": "manual",
            "stop_at": "needs_input",
            "job_description": "Please submit an English cover letter. "
            "Please submit a French cover letter. Operate service systems.",
        }
    ],
    indirect=True,
)
@pytest.mark.parametrize("precision_page", [{"no_cover": False}, {"no_cover": True}], indirect=True)
def test_two_distinct_jd_files_cannot_share_one_plain_destination(precision_page):
    p = precision_page
    requirements = p.worker.store.load()["jobs"][0]["precision_preparation"]["requirements"]
    assert len(requirements) == 2 and len({row["id"] for row in requirements}) == 2
    # A later field cannot claim both already prepared documents either.
    if not p.page.locator("#cover").count():
        original_covers = [
            row
            for row in p.worker.store.load()["jobs"][0]["materials"]
            if row["kind"] == "cover_letter"
        ]
        assert len(original_covers) == 2
        p.page.evaluate(
            "document.querySelector('form').insertAdjacentHTML('beforeend',"
            "'<label>Cover letter *<input id=one-cover type=file required></label>')"
        )
        p.pipeline.continue_current(request_id="one-field-is-not-two")
        for _ in range(30):
            p.pipeline._tick()
            p.engine.tick()
            if p.pipeline.snapshot()["status"] == "needs_recheck":
                break
    job = p.worker.store.load()["jobs"][0]
    assert job["reason"] == "material_field_mapping_required"
    assert p.pipeline.snapshot().get("wait_reason") != "precision_adjustment"
    covers = [row for row in job.get("materials", []) if row["kind"] == "cover_letter"]
    assert len(covers) == 2 and len({row["requirement_id"] for row in covers}) == 2
    assert all("field_id" not in row and row["jd_source"]["jd_quote"] for row in covers)
    assert p.page.locator("input[type=file]").evaluate_all(
        "nodes=>nodes.every(e=>e.files.length===0)"
    )
    assert p.page.evaluate("window.finalActions") == 0


@pytest.mark.parametrize(
    "bound_pipeline",
    [{"application_strategy": "manual", "stop_at": "needs_input"}],
    indirect=True,
)
def test_a_fresh_continue_resumes_the_same_bound_transaction_after_explicit_pause(precision_page):
    p = precision_page
    original = p.flow.snapshot()["active_task"]
    old_pdf = p.store.pdf(original["resume_id"])
    put_information_answer(
        p.worker.store.answers,
        {
            "question": "Email",
            "value": "resume-after-pause@example.invalid",
            "state": "confirmed",
            "scope": {},
        },
    )
    p.pipeline.continue_current(request_id="bound-before-user-pause")
    for _ in range(300):
        p.pipeline._tick()
        job = p.worker.store.load()["jobs"][0]
        if (
            job.get("material_update", {}).get("status") == "bound"
            and job.get("continuation", {}).get("status") == "pending"
        ):
            break
        p.engine.tick()
        time.sleep(0.01)
    assert job["material_update"]["status"] == "bound"
    assert job["continuation"]["status"] == "pending"
    transaction_id = job["material_update"]["id"]
    new_sha256 = job["file_sha256"]
    p.pipeline.pause()
    p.engine.tick()
    stopped = p.worker.store.load()["jobs"][0]
    assert p.worker.store.load()["control"] == "paused"
    assert stopped["continuation"]["status"] == "cancelled"
    assert p.page.locator("#resume").evaluate("e=>e.files.length") == 0
    p.pipeline.continue_current(request_id="fresh-bound-continue")
    result = advance_precision(
        p, lambda state: state["status"] in {"ready_for_review", "needs_recheck"}
    )
    assert result["status"] == "ready_for_review", result
    job = p.worker.store.load()["jobs"][0]
    assert job["material_update"]["id"] == transaction_id
    assert job["file_sha256"] == new_sha256
    assert len(p.calls) == 1 and len(p.store.prism_client.calls) == 2
    assert len(p.material_calls) == 4
    assert p.store.pdf(original["resume_id"]) == old_pdf
    uploads = [
        row["intent"]
        for row in job["observations"]
        if row.get("action") == "action_result" and row.get("intent", {}).get("kind") == "resume"
    ]
    assert len(uploads) == 1 and "replaces_sha256" not in uploads[0]
    assert "bound-before-user-pause" in job["continuation_requests"]
    assert "fresh-bound-continue" in job["continuation_requests"]
    assert p.page.evaluate("window.finalActions") == 0 and len(p.context.pages) == 1
