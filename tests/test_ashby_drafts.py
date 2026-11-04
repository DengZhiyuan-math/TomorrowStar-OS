"""Reviewed native draft requests. Fixtures contain no personal data."""

import base64
import gc
import hashlib
import json
import time
import weakref
from copy import deepcopy
from types import SimpleNamespace

import pytest

from career_evidence_graph.application_worker import WorkerService
from career_evidence_graph.application_worker_browser import ApplicationRunner
from career_evidence_graph.career_portal_data import ApplicationStore, PortalDataError

URL = "https://jobs.ashbyhq.com/synthetic/00000000-0000-0000-0000-000000000001/application"
UPLOAD = "https://uploaded-files.example.test/"
PDF = b"%PDF-1.4 Approved synthetic file"
QUERIES = {
    "ApiJobPosting": (
        "query ApiJobPosting($organizationHostedJobsPageName: String!, $jobPostingId: String!) { "
        "jobPosting(organizationHostedJobsPageName: $organizationHostedJobsPageName, "
        "jobPostingId: $jobPostingId) { applicationForm { id } } }"
    ),
    "ApiSetFormValue": (
        "mutation ApiSetFormValue($organizationHostedJobsPageName: String!, "
        "$formRenderIdentifier: String!, $formDefinitionIdentifier: String!, "
        "$path: String!, $value: JSON!) { "
        "setFormValue(organizationHostedJobsPageName: $organizationHostedJobsPageName, "
        "formRenderIdentifier: $formRenderIdentifier, "
        "formDefinitionIdentifier: $formDefinitionIdentifier, path: $path, value: $value) { id } }"
    ),
    "ApiAutocompleteGeoLocation": (
        "query ApiAutocompleteGeoLocation($text: String!, $locationTypes: [String!]!) { "
        "result: autocompleteGeoLocation(text: $text, locationTypes: $locationTypes) "
        "{ suggestions } }"
    ),
    "ApiCreateFileUploadHandle": (
        "mutation ApiCreateFileUploadHandle($organizationHostedJobsPageName: String!, "
        "$fileUploadContext: String!, $filename: String!, $contentType: String!, "
        "$contentLength: Int!) { fileUploadHandle: createFileUploadHandle("
        "organizationHostedJobsPageName: $organizationHostedJobsPageName, "
        "fileUploadContext: $fileUploadContext, filename: $filename, "
        "contentType: $contentType, contentLength: $contentLength) { url } }"
    ),
    "ApiSetFormValueToFile": (
        "mutation ApiSetFormValueToFile($organizationHostedJobsPageName: String!, "
        "$formRenderIdentifier: String!, $formDefinitionIdentifier: String!, "
        "$path: String!, $fileHandle: String!) { "
        "setFormValueToFile(organizationHostedJobsPageName: $organizationHostedJobsPageName, "
        "formRenderIdentifier: $formRenderIdentifier, "
        "formDefinitionIdentifier: $formDefinitionIdentifier, "
        "path: $path, fileHandle: $fileHandle) { id } }"
    ),
}


def setup_service(tmp_path, monkeypatch):
    apps = tmp_path / "applications"
    apps.mkdir()
    service = WorkerService(ApplicationStore(apps), tmp_path / "worker", live=True, generic=True)
    monkeypatch.setattr(service, "spawn", lambda: None)
    app = service.store.applications.create_application(
        {
            "company": "Synthetic",
            "role_title": "Engineer",
            "url": URL,
            "status": "drafting",
            "application_strategy": "batch",
        }
    )
    service.request(
        "prepare",
        {
            "jobs": [
                {
                    "application_id": app["id"],
                    "revision": app["revision"],
                    "country": "CHE",
                    "filename": "resume.pdf",
                    "file_base64": base64.b64encode(PDF).decode(),
                }
            ]
        },
    )
    for q, v in [("Name", "Synthetic Person"), ("Email", "synthetic@example.invalid")]:
        service.store.answers.put_answer(
            {"question": q, "value": v, "scope": {}, "state": "confirmed"}
        )
    service.store.answers.put_answer(
        {
            "question": "Source",
            "value": "Job board",
            "scope": {"company": "Synthetic"},
            "state": "confirmed",
        }
    )
    service.request("resume", {"controller": "synthetic-controller"})
    body = json.dumps(
        {
            "operationName": "ApiJobPosting",
            "query": QUERIES["ApiJobPosting"],
            "variables": {
                "organizationHostedJobsPageName": "synthetic",
                "jobPostingId": URL.split("/")[4],
            },
        }
    )
    return service, body


def endpoint(op):
    return "https://jobs.ashbyhq.com/api/non-user-graphql?op=" + op


def bounded_route(request):
    """Model fetch/fulfill without network and require the redirect/retry boundary."""
    route = SimpleNamespace(request=request, outcome="", fetch_calls=[])
    response = SimpleNamespace(status=200, disposed=0)

    def dispose():
        assert response.disposed == 0
        response.disposed += 1

    response.dispose = dispose

    def fetch(**options):
        assert options == {"max_redirects": 0, "max_retries": 0, "timeout": 10000}
        route.fetch_calls.append(options)
        return response

    def fulfill(*, response):
        assert response is route.response
        assert response.disposed == 0
        route.outcome = "allowed"

    route.response, route.fetch, route.fulfill = response, fetch, fulfill
    # A page request passes untouched; only a final operation is aborted.
    route.continue_ = lambda: setattr(route, "outcome", "allowed")
    route.abort = lambda _: setattr(route, "outcome", "blocked")
    return route


@pytest.mark.parametrize(
    "query",
    [
        QUERIES["ApiJobPosting"],
        "# schema formatting changed\n"
        + QUERIES["ApiJobPosting"].replace("{ applicationForm", "{ id applicationForm"),
        "\ufeff" + QUERIES["ApiJobPosting"].replace("jobPosting(", "posting: jobPosting("),
    ],
)
def test_observed_ashby_posting_read_needs_no_request_grant(tmp_path, monkeypatch, query):
    service, initial = setup_service(tmp_path, monkeypatch)
    payload = json.loads(initial)
    payload["query"] = query
    initial = json.dumps(payload)
    runner = ApplicationRunner(service.store, None)
    job = service.store.load()["jobs"][0]
    from career_evidence_graph.ashby_drafts import DraftSession

    page = object()
    runner.pages[job["application_id"]] = page
    runner.drafts[page] = DraftSession(job)

    class Request(SimpleNamespace):
        __hash__ = object.__hash__

    request = Request(
        method="POST",
        url=endpoint("ApiJobPosting"),
        resource_type="fetch",
        frame=SimpleNamespace(page=page),
        headers={"content-type": "application/json"},
        post_data_buffer=initial.encode(),
        is_navigation_request=lambda: False,
    )
    route = bounded_route(request)

    runner._live_guard(route)

    assert route.outcome == "allowed"
    assert runner.drafts[page].pending[request] == (
        "initial",
        "posting" if "posting: jobPosting" in query else "jobPosting",
    )
    assert page not in runner.blocked_pages


def form(values):
    return {
        "id": "render-one",
        "sourceFormDefinitionId": "definition-one",
        "errorMessages": [],
        "formErrors": [],
        "sections": [
            {
                "fieldEntries": [
                    {
                        "field": {
                            "path": path,
                            "title": title,
                            **(
                                {
                                    "selectableValues": [
                                        {"label": "Job board ", "value": "Job board "}
                                    ]
                                }
                                if path == "source"
                                else {}
                            ),
                        },
                        "fieldValue": values.get(path),
                        "isRequired": True,
                        "isHidden": False,
                    }
                    for path, title in [
                        ("name", "Name"),
                        ("email", "Email"),
                        ("source", "Source"),
                        ("resume", "Resume"),
                    ]
                ]
            }
        ],
    }


@pytest.mark.parametrize("hidden,confirmed", [(False, False), (True, False), (False, True)])
def test_server_required_field_without_dom_required_respects_server_visibility(
    tmp_path, monkeypatch, hidden, confirmed
):
    from career_evidence_graph.application_form_state import (
        MIN_SAMPLES,
        QUIET_WINDOW,
        SAMPLE_INTERVAL,
    )
    from career_evidence_graph.ashby_drafts import DraftSession

    service, _ = setup_service(tmp_path, monkeypatch)
    state = service.store.load()
    job = state["jobs"][0]
    runner = ApplicationRunner(service.store, None)
    page = object()
    runner.pages[job["application_id"]] = page
    runner.page_ids[page] = "synthetic-page"
    draft = DraftSession(job)
    path = "name" if confirmed else "required-custom"
    title = "Name" if confirmed else "Unknown server requirement"
    value = "Synthetic Person" if confirmed else ""
    server_form = form({"resume": {"id": "verified-file", "filename": job["filename"]}})
    entries = server_form["sections"][0]["fieldEntries"]
    server_form["sections"][0]["fieldEntries"] = [
        entries[-1],
        {
            "field": {"path": path, "title": title},
            "fieldValue": {"value": value} if confirmed else None,
            "isRequired": True,
            "isHidden": hidden,
        },
    ]
    draft._form(server_form)
    draft.uploaded = draft.linked = True
    draft.files["resume"] = {
        "id": "resume",
        "filename": job["filename"],
        "sha256": job["file_sha256"],
        "attachment_id": next(
            row["fieldValue"]["id"]
            for row in server_form["sections"][0]["fieldEntries"]
            if row["field"]["path"] == "resume"
        ),
    }
    runner.drafts[page] = draft
    fields = [
        {
            "id": "hosted-0",
            "type": "text",
            "question": title,
            "options": [],
            "value": value,
            "valid": True,
            "required": False,
            "multiple": False,
            "draft_path": path,
        },
        {
            "id": "hosted-1",
            "type": "file",
            "question": "Resume",
            "options": [],
            "value": "",
            "valid": True,
            "required": True,
            "multiple": False,
            "draft_path": "resume",
            "resume": True,
            "filename": job["filename"],
            "file_sha256": job["file_sha256"],
        },
    ]
    monkeypatch.setattr(
        "career_evidence_graph.application_worker_browser.hosted_ats.observe",
        lambda *args: {"fields": deepcopy(fields)},
    )

    assert runner.observe(page, job)["fields"][0]["required"] is not hidden
    assert runner.observe(page, job)["fields"][0]["required"] is not hidden
    assert fields[0]["required"] is False

    # Server-required semantics remain independent of the parser quiet window.
    # Observe the real defaults before asserting the final server-readback gate.
    deadline = time.monotonic() + QUIET_WINDOW + MIN_SAMPLES * SAMPLE_INTERVAL + 2
    while True:
        runner.process(job, state["batch_id"])
        saved = service.store.load()["jobs"][0]
        if saved["form_state"]["parser"]["status"] == "stable":
            break
        assert time.monotonic() < deadline, saved["reason"]
        time.sleep(SAMPLE_INTERVAL)

    if hidden or confirmed:
        assert saved["status"] == "ready_for_review"
        assert saved["questions"] == []
        assert any(o.get("server_readback") for o in saved["observations"])
    else:
        assert saved["status"] == "needs_input"
        assert saved["questions"][0]["draft_path"] == "required-custom"
        assert saved["questions"][0]["required"] is True
        assert not any(o.get("server_readback") for o in saved["observations"])


@pytest.mark.parametrize(
    "server_value", [None, {}, {"value": None}, {"value": ""}, {"value": " "}, {"value": []}]
)
def test_required_server_values_must_be_verified_even_without_resolved_answers(
    tmp_path, monkeypatch, server_value
):
    from career_evidence_graph.ashby_drafts import DraftSession

    service, _ = setup_service(tmp_path, monkeypatch)
    job = service.store.load()["jobs"][0]
    draft = DraftSession(job)
    server_form = form(
        {"name": server_value, "resume": {"id": "verified-file", "filename": job["filename"]}}
    )
    server_form["sections"][0]["fieldEntries"] = [
        e
        for e in server_form["sections"][0]["fieldEntries"]
        if e["field"]["path"] in {"name", "resume"}
    ]
    draft._form(server_form)
    draft.uploaded = draft.linked = True
    draft.files["resume"] = {
        "id": "resume",
        "filename": job["filename"],
        "sha256": job["file_sha256"],
        "attachment_id": next(
            row["fieldValue"]["id"]
            for row in server_form["sections"][0]["fieldEntries"]
            if row["field"]["path"] == "resume"
        ),
    }
    observed = {
        "fields": [
            {"draft_path": "name", "type": "text", "value": "Synthetic Person", "valid": True},
            {"draft_path": "resume", "type": "file"},
        ]
    }

    with pytest.raises(PortalDataError, match="服务端必填项"):
        draft.verify(observed, [], lambda q, value: value)


@pytest.mark.parametrize(
    "value,valid",
    [("Synthetic Person", True), ("", False), (" \n", False), (False, True), (0, True)],
)
def test_required_readback_distinguishes_empty_values_from_explicit_no_or_zero(
    tmp_path, monkeypatch, value, valid
):
    from career_evidence_graph.ashby_drafts import DraftSession

    service, _ = setup_service(tmp_path, monkeypatch)
    job = service.store.load()["jobs"][0]
    draft = DraftSession(job)
    server_form = form(
        {"name": {"value": value}, "resume": {"id": "verified-file", "filename": job["filename"]}}
    )
    server_form["sections"][0]["fieldEntries"] = [
        e
        for e in server_form["sections"][0]["fieldEntries"]
        if e["field"]["path"] in {"name", "resume"}
    ]
    draft._form(server_form)
    draft.uploaded = draft.linked = True
    draft.files["resume"] = {
        "id": "resume",
        "filename": job["filename"],
        "sha256": job["file_sha256"],
        "attachment_id": next(
            row["fieldValue"]["id"]
            for row in server_form["sections"][0]["fieldEntries"]
            if row["field"]["path"] == "resume"
        ),
    }
    observed = {
        "fields": [
            {"draft_path": "name", "type": "text", "value": value, "valid": True},
            {"draft_path": "resume", "type": "file"},
        ]
    }
    if valid:
        assert draft.verify(observed, [], lambda q, value: value)["server_readback"] is True
    else:
        with pytest.raises(PortalDataError, match="服务端必填项"):
            draft.verify(observed, [], lambda q, value: value)


@pytest.mark.parametrize(
    ("action", "conclusion", "uploaded"),
    [
        ("upload", "not_applied", False),
        ("upload", "manual_stop", False),
        ("fill", "not_applied", True),
    ],
)
def test_refresh_uses_latest_upload_resolution(tmp_path, monkeypatch, action, conclusion, uploaded):
    from career_evidence_graph.ashby_drafts import DraftSession

    service, initial = setup_service(tmp_path, monkeypatch)
    job = service.store.load()["jobs"][0]
    draft = DraftSession(job)
    draft.public_request = {"url": endpoint("ApiJobPosting"), "body": initial}
    draft.uploaded = draft.linked = True
    intent = {
        "action": action,
        "attempt_id": "upload-one",
        "sha256": job["file_sha256"],
        "draft_path": "resume",
    }
    resolutions = [
        {"intent_ref": "upload-one", "intent": intent, "conclusion": result}
        for result in ("current_matches", conclusion)
    ]
    history = deepcopy(resolutions)
    page = SimpleNamespace(
        evaluate=lambda *args: {
            "data": {
                "jobPosting": {
                    "id": draft.posting,
                    "title": job["role_title"],
                    "applicationForm": form(
                        {"resume": {"id": "file-one", "filename": job["filename"]}}
                        if uploaded
                        else {}
                    ),
                }
            }
        }
    )

    draft.refresh(
        page, ApplicationRunner.effective_action_results({**job, "action_resolutions": resolutions})
    )

    assert draft.uploaded is uploaded and draft.linked is uploaded
    assert resolutions == history


@pytest.mark.parametrize(
    ("conclusion", "later_completion", "attachment"),
    [
        ("not_applied", True, "matching"),
        ("manual_stop", True, "matching"),
        ("not_applied", False, "matching"),
        ("manual_stop", False, "matching"),
        ("not_applied", True, "missing"),
        ("not_applied", True, "different"),
    ],
)
def test_refresh_recognizes_completion_after_negative_resolution(
    tmp_path, monkeypatch, conclusion, later_completion, attachment
):
    from career_evidence_graph.ashby_drafts import DraftSession

    service, initial = setup_service(tmp_path, monkeypatch)
    job = service.store.load()["jobs"][0]
    intent = {
        "action": "upload",
        "attempt_id": "upload-one",
        "sha256": job["file_sha256"],
        "draft_path": "resume",
    }
    job["action_resolutions"] = [
        {
            "intent_ref": "upload-one",
            "intent": deepcopy(intent),
            "conclusion": conclusion,
            "observation_count": len(job["observations"]) + (not later_completion),
            "at": 20,
        }
    ]
    job["observations"].append(
        {"action": "action_result", "result": "verified", "intent": intent, "at": 10}
    )
    before = deepcopy(job)
    draft = DraftSession(job)
    draft.public_request = {"url": endpoint("ApiJobPosting"), "body": initial}
    page = SimpleNamespace(
        evaluate=lambda *args: {
            "data": {
                "jobPosting": {
                    "id": draft.posting,
                    "title": job["role_title"],
                    "applicationForm": form(
                        {
                            "resume": {
                                "id": "file-one",
                                "filename": job["filename"]
                                if attachment == "matching"
                                else "other.pdf",
                            }
                        }
                        if attachment != "missing"
                        else {}
                    ),
                }
            }
        }
    )

    assert ApplicationRunner.recovered_upload(job) is later_completion
    if later_completion and attachment != "matching":
        with pytest.raises(PortalDataError) as error:
            draft.refresh(page, ApplicationRunner.effective_action_results(job))
        assert error.value.code == "draft_result_unknown"
    else:
        draft.refresh(page, ApplicationRunner.effective_action_results(job))
        assert draft.uploaded is later_completion and draft.linked is later_completion
    assert job == before


def test_radio_value_comes_from_unique_server_option_not_html_default(tmp_path, monkeypatch):
    from career_evidence_graph.ashby_drafts import DraftSession

    service, _ = setup_service(tmp_path, monkeypatch)
    draft = DraftSession(service.store.load()["jobs"][0])
    definition = form({})
    definition["sections"][0]["fieldEntries"][0]["field"]["selectableValues"] = [
        {"label": "Job board ", "value": "Job board "}
    ]
    draft._form(definition)
    q = {"draft_path": "name", "type": "radio"}
    assert draft.option_value(q, "Job board") == "Job board "
    definition["sections"][0]["fieldEntries"][0]["field"]["selectableValues"].append(
        {"label": "Job board", "value": "different"}
    )
    with pytest.raises(PortalDataError, match="选项"):
        draft.option_value(q, "Job board")


def test_handle_response_is_applied_once_when_body_read_yields(tmp_path, monkeypatch):
    from career_evidence_graph.ashby_drafts import DraftSession

    service, _ = setup_service(tmp_path, monkeypatch)
    draft = DraftSession(service.store.load()["jobs"][0])
    reads = []

    class Request:
        def response(self):
            return response

    def body():
        reads.append(True)
        if len(reads) == 1:
            draft._settle("handle")
            assert draft.handle is not None
        return {
            "data": {
                "fileUploadHandle": {"handle": "one", "url": UPLOAD, "fields": {"key": "synthetic"}}
            }
        }

    request = Request()
    response = SimpleNamespace(request=request, status=200, json=body)
    draft.pending[request] = ("handle", None)
    draft.response(response)
    assert len(reads) == 2
    assert draft.counts == {"handle": 1}
    assert draft.pending == {}


@pytest.mark.worker_browser
@pytest.mark.parametrize(
    "failure",
    [
        "",
        "save_errors",
        "unsaved_prefill",
        "release",
        "page_closed",
        "save_lost",
        "save_http_error",
        "upload_lost",
        "upload_http_error",
        "link_lost",
        "link_http_error",
        "intent_write",
        "result_write",
        "recover_match",
        "recover_not_applied",
        "recover_unknown",
        "recover_upload_match",
        "recover_upload_corrected",
        "late_upload_not_applied",
        "late_upload_manual_stop",
    ],
)
def test_worker_saves_on_blur_and_uploads_only_selected_pdf_before_review(
    tmp_path, monkeypatch, failure
):
    from playwright.sync_api import Error, sync_playwright

    from career_evidence_graph.application_worker import start_run

    monkeypatch.setenv("PLAYWRIGHT_BROWSERS_PATH", "0")
    service, initial = setup_service(tmp_path, monkeypatch)
    original_save = service.store.save
    failed_writes = []

    def write_checkpoint(state):
        candidate = state["jobs"][0]
        previous = service.store.load()["jobs"][0]
        if not failed_writes and (
            failure == "intent_write"
            and (candidate.get("intent") or {}).get("action") == "fill"
            or failure == "result_write"
            and previous["intent"]
            and previous["intent"]["action"] == "fill"
            and candidate["intent"] is None
        ):
            before = service.store.path.read_bytes()
            failed_writes.append(before)
            assert service.store.path.read_bytes() == before
            raise OSError("Synthetic checkpoint failure")
        original_save(state)

    if failure in {"intent_write", "result_write"}:
        monkeypatch.setattr(service.store, "save", write_checkpoint)
    html = (
        """<title>Engineer @ Synthetic</title><h1>Engineer</h1><div id='root'></div><script>
    const queries=QUERIES, init=INITIAL;
    async function call(op,variables) {
      return (await fetch('/api/non-user-graphql?op='+op,{method:'POST',
        headers:{'Content-Type':'application/json'},
        body:JSON.stringify({operationName:op,query:queries[op],variables})})).json();
    }
    fetch('/api/non-user-graphql?op=ApiJobPosting',{method:'POST',headers:{'Content-Type':'application/json'},body:init})
    .then(r=>r.json()).then(()=>{
      document.querySelector('#root').innerHTML=`<form>
        <label>Name<input id='name' data-field-path='name' required></label>
        <label>Email<input id='email' data-field-path='email' type='email' required></label>
            <fieldset data-field-path='source'><legend>Source</legend>
              <label><input id='source' name='source' type='radio' required>Job board</label>
            </fieldset>
        <label>Resume<input id='resume' data-field-path='resume' type='file' required></label>
        <button type='submit'>Submit Application</button></form>`;
      const base={organizationHostedJobsPageName:'synthetic',formRenderIdentifier:'render-one',
        formDefinitionIdentifier:'definition-one'};
      if(PREFILL)document.getElementById('name').value='Synthetic Person';
      for (const id of ['name','email']) document.getElementById(id).onblur=()=>
        call('ApiSetFormValue',{...base,path:id,value:document.getElementById(id).value});
          document.getElementById('source').onchange=()=>
            call('ApiSetFormValue',{...base,path:'source',value:'Job board '});
      document.getElementById('resume').onchange=async()=>{
        const file=document.getElementById('resume').files[0];
        const r=await call('ApiCreateFileUploadHandle',{organizationHostedJobsPageName:'synthetic',
          fileUploadContext:'NonUserFormEngine',filename:file.name,
          contentType:file.type,contentLength:file.size});
        const h=r.data.fileUploadHandle, data=new FormData();
            data.append('Content-Type',file.type);
        for(const [k,v] of Object.entries(h.fields))data.append(k,v);data.append('file',file);
        await fetch(h.url,{method:'POST',body:data});
        await call('ApiSetFormValueToFile',{...base,path:'resume',fileHandle:h.handle});
      };
      window.finalActions=0;document.querySelector('form').onsubmit=e=>{e.preventDefault();window.finalActions++};
    });</script>""".replace("QUERIES", json.dumps(QUERIES))
        .replace("INITIAL", json.dumps(initial))
        .replace("PREFILL", json.dumps(failure == "unsaved_prefill"))
    )
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, channel="chromium")
        try:
            context = browser.new_context(offline=True)
            start_run(service.store)
            runner = ApplicationRunner(service.store, context)
            values, requests, attempted, page_errors, denied = {}, [], [], [], []
            fetched_responses = []
            failed_requests = []
            context.on(
                "requestfailed",
                lambda request: failed_requests.append(
                    {"url": request.url, "failure": request.failure}
                ),
            )
            context.on(
                "page", lambda page: page.on("pageerror", lambda e: page_errors.append(str(e)))
            )

            def intercept(route):
                def reply(**fields):
                    response = SimpleNamespace(
                        status=fields.get("status", 200), fields=fields, disposed=False
                    )

                    def dispose():
                        assert not response.disposed
                        response.disposed = True

                    response.dispose = dispose
                    fetched_responses.append(response)
                    return response

                def fetch(**options):
                    assert options == {"max_redirects": 0, "max_retries": 0, "timeout": 10000}
                    req = route.request
                    if req.method == "GET":
                        return reply(status=200, body=html, content_type="text/html")
                    op = req.url.split("?op=")[-1]
                    requests.append(op if req.url != UPLOAD else "upload")
                    if req.url == UPLOAD:
                        if failure == "upload_lost" or (
                            failure == "recover_upload_corrected" and requests.count("upload") == 1
                        ):
                            raise Error("Synthetic upload response lost")
                        else:
                            return reply(
                                status=503 if failure == "upload_http_error" else 204,
                                headers={"access-control-allow-origin": "*"},
                            )
                    v = req.post_data_json["variables"]
                    if op == "ApiJobPosting":
                        result = {
                            "jobPosting": {
                                "id": URL.split("/")[4],
                                "title": "Engineer",
                                "applicationForm": form(values),
                            }
                        }
                    elif op == "ApiSetFormValue":
                        if failure == "save_errors":
                            return reply(
                                status=200, json={"errors": [{"message": "Synthetic save failure"}]}
                            )
                        if (
                            failure != "recover_not_applied"
                            or requests.count("ApiSetFormValue") > 1
                        ):
                            values[v["path"]] = {"value": v["value"]}
                        if (
                            failure in {"recover_match", "recover_not_applied", "recover_unknown"}
                            and requests.count("ApiSetFormValue") == 1
                        ):
                            raise Error("Synthetic save response lost")
                        if failure == "save_lost":
                            raise Error("Synthetic save response lost")
                        result = {"setFormValue": form(values)}
                    elif op == "ApiCreateFileUploadHandle":
                        result = {
                            "fileUploadHandle": {
                                "handle": "upload-one",
                                "url": UPLOAD,
                                "fields": {"key": "synthetic", "policy": "fixed"},
                            }
                        }
                    else:
                        assert op == "ApiSetFormValueToFile"
                        if failure.startswith("late_upload_"):
                            current = service.store.load()["jobs"][0]
                            service.request(
                                "resolve-action",
                                {
                                    "application_id": current["application_id"],
                                    "intent_ref": current["intent"]["attempt_id"],
                                    "conclusion": failure.removeprefix("late_upload_"),
                                    "source": "Synthetic readback before pending link completes",
                                },
                            )
                        values["resume"] = {"id": "file-one", "filename": "resume.pdf"}
                        result = {"setFormValueToFile": form(values)}
                    if op == "ApiSetFormValueToFile" and failure in {
                        "link_lost",
                        "recover_upload_match",
                    }:
                        raise Error("Synthetic link response lost")
                    return reply(
                        status=503
                        if (
                            op == "ApiSetFormValue"
                            and failure == "save_http_error"
                            or op == "ApiSetFormValueToFile"
                            and failure == "link_http_error"
                        )
                        else 200,
                        json={"data": result},
                    )

                def fulfill(*, response):
                    assert not response.disposed
                    route.fulfill(**response.fields)

                def abort(reason):
                    from career_evidence_graph.hosted_ats import multipart_parts

                    state = service.store.load()
                    draft = runner.drafts.get(route.request.frame.page)
                    denied.append(
                        {
                            "method": route.request.method,
                            "url": route.request.url,
                            "lease_age": time.time() - state["heartbeat_at"],
                            "control": state["control"],
                            "active": draft.active if draft else None,
                            "parts": [
                                (
                                    p.get_param("name", header="content-disposition"),
                                    p.get_filename(),
                                    hashlib.sha256(p.get_payload(decode=True) or b"").hexdigest(),
                                )
                                for p in multipart_parts(route.request)
                            ],
                        }
                    )
                    route.abort(reason)

                proxy = SimpleNamespace(
                    request=route.request,
                    fetch=fetch,
                    fulfill=fulfill,
                    continue_=lambda: pytest.fail("Automated drafts must use bounded fetch"),
                    abort=abort,
                )
                attempted.append((route.request.method, route.request.url))
                runner._live_guard(proxy)

            context.route("**/*", intercept)

            def settle():
                from career_evidence_graph.application_form_state import (
                    MIN_SAMPLES,
                    QUIET_WINDOW,
                    SAMPLE_INTERVAL,
                )

                # APP-08 uploads before filling; each changed observation must
                # pass the real parser window before the next field is written.
                deadline = time.monotonic() + 5 * (QUIET_WINDOW + MIN_SAMPLES * SAMPLE_INTERVAL) + 5
                while True:
                    service.request("heartbeat", {"controller": "synthetic-controller"})
                    runner.tick()
                    saved = service.store.load()["jobs"][0]
                    if saved["status"] in {
                        "ready_for_review",
                        "needs_recheck",
                        "needs_input",
                        "cancelled",
                    }:
                        return saved
                    assert time.monotonic() < deadline, saved["reason"]
                    time.sleep(SAMPLE_INTERVAL)

            upload_requests = [
                "ApiJobPosting",
                "ApiCreateFileUploadHandle",
                "upload",
                "ApiSetFormValueToFile",
            ]
            job = settle()
            if failure.startswith("late_upload_"):
                assert job["status"] == "needs_recheck" and job["intent"] is None
                assert ApplicationRunner.recovered_upload(job)
                history = deepcopy(job["action_resolutions"])
                before = list(requests)
                service.request("pause", {"controller": "synthetic-controller"})
                service.request(
                    "recheck", {"application_id": job["application_id"], "acknowledge": True}
                )
                runner.tick()
                assert service.store.load()["control"] == "paused"
                draft = runner.drafts[runner.pages[job["application_id"]]]
                assert draft.uploaded and draft.linked
                assert requests == [*before, "ApiJobPosting"]
                service.request("resume", {"controller": "synthetic-controller"})
                result = settle()
                assert result["status"] == "ready_for_review", result["reason"]
                assert result["intent"] is None and result["action_resolutions"] == history
                assert requests == [*before, "ApiJobPosting", *(["ApiSetFormValue"] * 3)]
                assert requests.count("upload") == requests.count("ApiSetFormValueToFile") == 1
                assert runner.pages[job["application_id"]].evaluate("window.finalActions") == 0
                return
            if failure.startswith("recover_"):
                assert job["status"] == "needs_recheck" and job["intent"]
                conclusion = {
                    "recover_match": "current_matches",
                    "recover_not_applied": "not_applied",
                    "recover_unknown": "manual_stop",
                    "recover_upload_match": "current_matches",
                    "recover_upload_corrected": "current_matches",
                }[failure]
                service.request(
                    "resolve-action",
                    {
                        "application_id": job["application_id"],
                        "intent_ref": job["intent"]["attempt_id"],
                        "conclusion": conclusion,
                        "source": "Synthetic authoritative server value readback",
                    },
                )
                if failure == "recover_upload_corrected":
                    service.request(
                        "resolve-action",
                        {
                            "application_id": job["application_id"],
                            "intent_ref": job["intent"]["attempt_id"],
                            "conclusion": "not_applied",
                            "source": "Correction after synthetic server confirms no attachment",
                        },
                    )
                assert service.store.load()["jobs"][0]["intent"] == job["intent"]
                if failure == "recover_unknown":
                    with pytest.raises(PortalDataError) as error:
                        service.request(
                            "recheck",
                            {"application_id": job["application_id"], "acknowledge": True},
                        )
                    assert error.value.code == "action_unresolved"
                    for _ in range(3):
                        runner.tick()
                    assert requests.count("ApiSetFormValue") == requests.count("upload") == 1
                else:
                    service.request("pause", {"controller": "synthetic-controller"})
                    service.request(
                        "recheck", {"application_id": job["application_id"], "acknowledge": True}
                    )
                    runner.tick()  # Read-only verification is allowed while paused.
                    assert service.store.load()["control"] == "paused"
                    assert requests.count("ApiSetFormValue") == (
                        0 if failure.startswith("recover_upload_") else 1
                    )
                    service.request("resume", {"controller": "synthetic-controller"})
                    result = settle()
                    assert result["status"] == "ready_for_review", (
                        result["reason"],
                        requests,
                        denied,
                        page_errors,
                    )
                    assert requests.count("ApiSetFormValue") == (
                        4 if failure == "recover_not_applied" else 3
                    )
                    assert (
                        requests.count("upload")
                        == (2 if failure == "recover_upload_corrected" else 1)
                        and requests.count("ApiSetFormValueToFile") == 1
                    )
                    assert (
                        result["intent"] is None
                        and result["action_resolutions"][-1]["intent"] == job["intent"]
                    )
                assert runner.pages[job["application_id"]].evaluate("window.finalActions") == 0
                return
            if failure in {
                "save_lost",
                "save_http_error",
                "upload_lost",
                "upload_http_error",
                "link_lost",
                "link_http_error",
                "intent_write",
                "result_write",
            }:
                assert job["status"] == "needs_recheck"
                before = list(requests)
                for _ in range(3):
                    runner.tick()
                assert requests == before
                assert runner.pages[job["application_id"]].evaluate("window.finalActions") == 0
                if failure == "intent_write":
                    assert requests == upload_requests
                    assert set(values) == {"resume"}
                else:
                    assert job["intent"] and job["intent"].get("attempt_id")
                    kinds = {o.get("kind") for o in job["observations"]}
                    if failure.startswith(("save", "result")):
                        assert values["name"] == {"value": "Synthetic Person"}
                        assert requests == [*upload_requests, "ApiSetFormValue"]
                        assert "save" in kinds
                    else:
                        assert "name" not in values
                        assert requests.count("ApiSetFormValue") == 0
                    if failure.startswith("upload"):
                        assert requests.count("upload") == 1 and "upload" in kinds
                    if failure.startswith("link"):
                        assert (
                            requests.count("upload") == 1
                            and requests.count("ApiSetFormValueToFile") == 1
                        )
                        assert "upload" in kinds and "link" in kinds
                if failure.endswith("write"):
                    assert failed_writes and runner.storage_stopped
                    assert service.snapshot()["control"] == "paused"
                return
            if failure == "save_errors":
                assert job["status"] == "needs_recheck"
                assert job["reason"] == "draft_result_unverified"
                assert job["intent"] is not None
                assert requests == [*upload_requests, "ApiSetFormValue"]
                assert not runner.pages[job["application_id"]].is_closed()
                return
            if failure == "unsaved_prefill":
                # APP-08 protects an existing value even when it matches our
                # answer. Its absent server receipt must not become ready.
                assert job["status"] == "needs_recheck"
                assert job["reason"] == "draft_result_unverified"
                assert job["intent"] is None and "name" not in values
                assert requests == [*upload_requests, *(["ApiSetFormValue"] * 2)]
                page = runner.pages[job["application_id"]]
                assert page.locator("[data-field-path=name]").input_value() == "Synthetic Person"
                assert page.evaluate("window.finalActions") == 0
                before = list(requests)
                for _ in range(3):
                    runner.tick()
                assert requests == before
                return
            assert job["status"] == "ready_for_review", json.dumps(
                {
                    "reason": job["reason"],
                    "requests": requests,
                    "attempted": attempted,
                    "page_errors": page_errors,
                    "failed_requests": failed_requests,
                    "denied": denied,
                },
                indent=2,
            )
            assert any(
                o.get("action") == "draft_transport_verified" and o["server_readback"]
                for o in job["observations"]
            )
            assert values["name"] == {"value": "Synthetic Person"}
            assert values["email"] == {"value": "synthetic@example.invalid"}
            assert values["source"] == {"value": "Job board "}
            assert requests == [*upload_requests, *(["ApiSetFormValue"] * 3)]
            assert runner.pages[job["application_id"]].evaluate("window.finalActions") == 0
            assert (
                service.store.applications.get_application(job["application_id"])["status"]
                == "drafting"
            )
            if failure in {"release", "page_closed"}:
                page = runner.pages[job["application_id"]]
                session = weakref.ref(runner.drafts[page])
                service.request("pause", {"controller": "synthetic-controller"})
                if failure == "release":
                    service.request("review", {"application_id": job["application_id"]})
                    runner.tick()
                    service.request("release", {"application_id": job["application_id"]})
                else:
                    page.close()
                runner.tick()
                assert page.is_closed()
                assert not service.snapshot()["jobs"][0]["page_open"]
                gc.collect()
                assert session() is None, (
                    "Closed pages must not retain draft values or upload handles"
                )
                assert service.snapshot()["jobs"][0]["manual_submission"] is None
        finally:
            browser.close()
            assert all(response.disposed for response in fetched_responses)


@pytest.mark.parametrize(
    "change",
    [
        "",
        "answer",
        "path",
        "organization",
        "render",
        "definition",
        "query",
        "submit",
        "paused",
        "revoked",
        "applied",
        "extra",
    ],
)
def test_draft_permission_requires_current_answer_intent_and_exact_request(
    tmp_path, monkeypatch, change
):
    from career_evidence_graph.ashby_drafts import DraftSession

    service, initial = setup_service(tmp_path, monkeypatch)
    runner = ApplicationRunner(service.store, None)
    job = service.store.load()["jobs"][0]
    page = object()
    runner.pages[job["application_id"]] = page
    draft = DraftSession(job)
    runner.drafts[page] = draft
    q = {"id": "hosted-0", "draft_path": "name", "type": "text", "question": "Name", "options": []}
    value, ref = service.store.resolve(q, job)
    intent = {"action": "fill", "field_id": q["id"], "answer_ref": ref}
    state = service.store.load()
    state["jobs"][0].update(status="filling", intent=intent)
    service.store.save(state)
    draft._form(form({}))
    draft.begin(q, value, intent)
    v = {
        "organizationHostedJobsPageName": "synthetic",
        "formRenderIdentifier": "render-one",
        "path": "name",
        "value": "Synthetic Person",
        "formDefinitionIdentifier": "definition-one",
    }
    for name, key in [
        ("answer", "value"),
        ("path", "path"),
        ("organization", "organizationHostedJobsPageName"),
        ("render", "formRenderIdentifier"),
        ("definition", "formDefinitionIdentifier"),
    ]:
        if change == name:
            v[key] = "unapproved"
    if change == "extra":
        v["submit"] = True
    op = "ApiSubmitSingleApplicationFormAction" if change == "submit" else "ApiSetFormValue"
    query = QUERIES["ApiSetFormValue"] + (
        " mutation HiddenSubmit { submit }" if change == "query" else ""
    )
    if change == "paused":
        service.request("pause", {"controller": "synthetic-controller"})
    if change == "revoked":
        service.store.answers.put_answer(
            {"question": "Name", "value": None, "scope": {}, "state": "missing"}
        )
    if change == "applied":
        app = service.store.applications.get_application(job["application_id"])
        service.store.applications.update_application(
            app["id"], {"status": "applied"}, app["revision"]
        )
    req = SimpleNamespace(
        method="POST",
        url=endpoint(op),
        resource_type="fetch",
        frame=SimpleNamespace(page=page),
        headers={"content-type": "application/json"},
        post_data_buffer=json.dumps({"operationName": op, "variables": v, "query": query}).encode(),
        is_navigation_request=lambda: False,
    )
    route = bounded_route(req)
    # Real requests are hashable; SimpleNamespace stands in for their protocol here.
    draft.pending = {}
    if not change:

        class Request:
            pass

        actual = Request()
        actual.__dict__.update(req.__dict__)
        route.request = actual
    runner._live_guard(route)
    # A page request passes unless it is a final operation; only the exact
    # pending write is tracked.
    assert route.outcome == ("blocked" if change in {"query", "submit"} else "allowed")
    assert bool(runner.sent_requests) == (not change)


@pytest.mark.parametrize("change", ["", "pdf", "filename", "extra", "url", "intent", "mime"])
def test_upload_permission_binds_pdf_bytes_and_server_handle_fields(tmp_path, monkeypatch, change):
    from career_evidence_graph.ashby_drafts import DraftSession

    service, _ = setup_service(tmp_path, monkeypatch)
    runner = ApplicationRunner(service.store, None)
    job = service.store.load()["jobs"][0]
    page = object()
    runner.pages[job["application_id"]] = page
    draft = DraftSession(job)
    runner.drafts[page] = draft
    intent = {"action": "upload", "sha256": job["file_sha256"]}
    state = service.store.load()
    state["jobs"][0].update(status="filling", intent=intent)
    service.store.save(state)
    draft._form(form({}))
    draft.begin({"draft_path": "resume", "type": "file", "question": "Resume"}, len(PDF), intent)
    draft.handle = {
        "url": UPLOAD,
        "fields": {"key": "synthetic", "policy": "fixed"},
        "handle": "one",
    }
    if change == "intent":
        state["jobs"][0]["intent"] = {"action": "fill"}
        service.store.save(state)
    raw = PDF if change != "pdf" else b"%PDF-1.4 Unapproved replacement"
    filename = "resume.pdf" if change != "filename" else "other.pdf"
    body = b'--b\r\nContent-Disposition: form-data; name="key"\r\n\r\nsynthetic\r\n'
    body += b'--b\r\nContent-Disposition: form-data; name="policy"\r\n\r\nfixed\r\n'
    mime = b"application/pdf" if change != "mime" else b"text/plain"
    body += b'--b\r\nContent-Disposition: form-data; name="Content-Type"\r\n\r\n' + mime + b"\r\n"
    body += (
        (
            f'--b\r\nContent-Disposition: form-data; name="file"; filename="{filename}"\r\n'
            "Content-Type: application/pdf\r\n\r\n"
        ).encode()
        + raw
        + b"\r\n"
    )
    if change == "extra":
        body += b'--b\r\nContent-Disposition: form-data; name="email"\r\n\r\nunapproved\r\n'
    body += b"--b--\r\n"

    class Request:
        method = "POST"
        url = UPLOAD if change != "url" else "https://other.example.test/"
        resource_type = "fetch"
        frame = SimpleNamespace(page=page)
        headers = {"content-type": "multipart/form-data; boundary=b"}
        post_data_buffer = body

        def is_navigation_request(self):
            return False

    route = bounded_route(Request())
    runner._live_guard(route)
    # The page's request always passes; only the exact pending write is tracked.
    assert route.outcome == "allowed"
    assert bool(runner.sent_requests) == (not change)


@pytest.mark.parametrize(
    "query",
    [
        "mutation ApiSetFormValue { setFormValue("
        'organizationHostedJobsPageName: "other-org", formRenderIdentifier: "other-render", '
        'formDefinitionIdentifier: "other-definition", path: "email", '
        'value: "different@example.invalid") { id } }',
        QUERIES["ApiSetFormValue"].replace("value: $value", 'value: "different@example.invalid"'),
        QUERIES["ApiSetFormValue"].replace("path: $path", "path: $value"),
        QUERIES["ApiSetFormValue"].replace("$value: JSON!", '$value: JSON! = "default"'),
        QUERIES["ApiSetFormValue"].replace("$value: JSON!", "$unused: String!, $value: JSON!"),
        QUERIES["ApiSetFormValue"].replace("path: $path", "path: $path, path: $path"),
        QUERIES["ApiSetFormValue"].replace("value: $value", "value: { nested: $value }"),
        "mutation ApiSetFormValue { setFormValue { id } }",
        "# only a comment",
        QUERIES["ApiSetFormValue"][:-2],
    ],
)
def test_draft_query_arguments_cannot_override_the_verified_answer(tmp_path, monkeypatch, query):
    from career_evidence_graph.ashby_drafts import DraftSession

    service, _ = setup_service(tmp_path, monkeypatch)
    job = service.store.load()["jobs"][0]
    runner = ApplicationRunner(service.store, None)
    page = object()
    runner.pages[job["application_id"]] = page
    assert runner.authorize(job, service.store.load()["batch_id"], {"action": "fill"})
    intent = deepcopy(service.store.load()["jobs"][0]["intent"])
    draft = DraftSession(job)
    draft._form(form({}))
    draft.begin(
        {"draft_path": "email", "question": "Email", "type": "email"},
        "synthetic@example.invalid",
        intent,
    )
    runner.drafts[page] = draft
    payload = {
        "operationName": "ApiSetFormValue",
        "query": query,
        "variables": {
            "organizationHostedJobsPageName": "synthetic",
            "formRenderIdentifier": "render-one",
            "formDefinitionIdentifier": "definition-one",
            "path": "email",
            "value": "synthetic@example.invalid",
        },
    }

    class Request(SimpleNamespace):
        __hash__ = object.__hash__

    request = Request(
        method="POST",
        url=endpoint("ApiSetFormValue"),
        resource_type="fetch",
        frame=SimpleNamespace(page=page),
        headers={"content-type": "application/json"},
        post_data_buffer=json.dumps(payload).encode(),
        is_navigation_request=lambda: False,
    )
    route = bounded_route(request)
    runner._live_guard(route)
    assert route.outcome == "allowed"
    assert page not in runner.blocked_pages
    assert not runner.sent_requests and not draft.pending
    assert service.store.load()["jobs"][0]["intent"] == intent


@pytest.mark.parametrize(
    "operation,variables",
    [
        (
            "ApiJobPosting",
            {
                "organizationHostedJobsPageName": "synthetic",
                "jobPostingId": "00000000-0000-0000-0000-000000000001",
            },
        ),
        (
            "ApiSetFormValue",
            {
                "organizationHostedJobsPageName": "synthetic",
                "formRenderIdentifier": "render-one",
                "formDefinitionIdentifier": "definition-one",
                "path": "email",
                "value": "synthetic@example.invalid",
            },
        ),
        ("ApiAutocompleteGeoLocation", {"text": "Switzerland", "locationTypes": ["Country"]}),
        (
            "ApiCreateFileUploadHandle",
            {
                "organizationHostedJobsPageName": "synthetic",
                "fileUploadContext": "NonUserFormEngine",
                "filename": "resume.pdf",
                "contentType": "application/pdf",
                "contentLength": 128,
            },
        ),
        (
            "ApiSetFormValueToFile",
            {
                "organizationHostedJobsPageName": "synthetic",
                "formRenderIdentifier": "render-one",
                "formDefinitionIdentifier": "definition-one",
                "path": "resume",
                "fileHandle": "synthetic-handle",
            },
        ),
    ],
)
def test_supported_draft_payload_binds_every_declared_root_argument(operation, variables):
    from career_evidence_graph.ashby_drafts import DraftSession

    draft = DraftSession({"job_url": URL, "platform": "generic"})
    request = SimpleNamespace(
        method="POST",
        url=endpoint(operation),
        resource_type="fetch",
        headers={"content-type": "application/json"},
        post_data_buffer=json.dumps(
            {"operationName": operation, "variables": variables, "query": QUERIES[operation]}
        ).encode(),
    )
    assert draft.payload(request) == (operation, variables)
