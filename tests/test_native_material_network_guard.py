"""Native material networking keeps real draft and durable one-use guards."""

import base64
import json
from copy import deepcopy
from types import SimpleNamespace
from uuid import uuid4

import pytest
import test_single_application_worker
import test_worker_bound_material_delivery
import test_worker_native_material_journal
from test_ashby_drafts import UPLOAD, URL, bounded_route
from test_native_material_draft_proof import Request, make_request, respond
from test_worker_assistance_delivery import page_context
from test_worker_codex_assistance import retained_assistance_page as retained_assistance_page
from test_worker_native_material_journal import sealed_receipt

from career_evidence_graph.application_worker_browser import ApplicationRunner
from career_evidence_graph.ashby_drafts import DraftSession

original_single_worker = test_single_application_worker.single_worker
original_material_page = test_worker_bound_material_delivery.bound_material_page
material_journal = test_worker_native_material_journal.material_call


@pytest.fixture
def single_worker(original_single_worker):
    service, item, checks, launches = original_single_worker
    app = service.store.applications.update_application(
        item["application_id"], {"url": URL}, item["revision"]
    )
    item["revision"] = app["revision"]
    service.generic = True
    state = service.store.load()
    state["generic_enabled"] = True
    service.store.save(state)
    return service, item, checks, launches


@pytest.fixture
def bound_material_page(original_material_page):
    service, fixed, issue = original_material_page
    # The reused native-service fixture defaults to generic=False. Configure this
    # synthetic Ashby case before issue prepares any material or claims a writer.
    service.generic = True
    state = service.store.load()
    state["generic_enabled"] = True
    service.store.save(state)
    return service, fixed, issue


class Page:
    def __init__(self, url):
        self.url = url
        self.context = SimpleNamespace(browser=SimpleNamespace(is_connected=lambda: True))
        self.main_frame = SimpleNamespace(page=self)

    def is_closed(self):
        return False


def form(question, value=None):
    return {
        "id": "render-one",
        "sourceFormDefinitionId": "definition-one",
        "errorMessages": [],
        "formErrors": [],
        "sections": [
            {
                "fieldEntries": [
                    {
                        "field": {"path": question["draft_path"], "title": question["question"]},
                        "fieldValue": value,
                        "isRequired": True,
                        "isHidden": False,
                    }
                ]
            }
        ],
    }


@pytest.fixture
def native_draft(material_journal, request):
    service, reference, scope, current_receipt, _ = material_journal
    runner = ApplicationRunner(service.store, None)
    state = service.store.load()
    job = state["jobs"][0]
    page = Page(job["job_url"])
    runner.context = page.context
    runner.pages[job["application_id"]] = page
    runner.page_ids[page] = reference["binding"]["page_id"]
    runner.document_urls[page] = page.url
    draft = DraftSession(job)
    runner.drafts[page] = draft
    question = job["form_state"]["snapshot"]["fields"][0]
    initial = make_request(
        "ApiJobPosting",
        {
            "organizationHostedJobsPageName": draft.org,
            "jobPostingId": draft.posting,
        },
    )
    assert draft.track_public(initial)
    respond(
        draft,
        initial,
        {
            "data": {
                "jobPosting": {
                    "id": draft.posting,
                    "title": job["role_title"],
                    "applicationForm": form(question),
                }
            }
        },
    )
    call = current_receipt["calls"][0]
    context = page_context(service, reference)
    context["data"]["fields"] = [
        {"value": "", "material_target": deepcopy(call["target_descriptor"])}
    ]
    # The production preparation must arm this already registered DraftSession.
    # Calling draft.begin here would hide wrong material metadata at that boundary.
    payload = runner._prepare_native_material_call(
        reference, call, context, request_id="journal-run", scope=scope, receipt=current_receipt
    )
    intent = service.store.load()["jobs"][0]["intent"]
    journal = service, reference, scope, current_receipt, intent
    if getattr(request, "param", "sealed") != "unsealed":
        service.store.record_native_handoff(
            reference,
            request_id="journal-run",
            phase="granted",
            scope=scope,
            receipt=sealed_receipt(journal),
        )
    state = service.store.load()
    job = state["jobs"][0]
    saved_material = next(row for row in job["materials"] if row["id"] == intent["material_id"])
    material = {
        "id": saved_material["id"],
        "sha256": saved_material["text_sha256"]
        if payload["kind"] == "text"
        else saved_material["sha256"],
    }
    if payload["kind"] == "file":
        material["filename"] = saved_material["filename"]
    assert material["sha256"] == intent["sha256"] == payload["sha256"]
    assert service.store.native_material_intent(state, job, reference) == intent
    assert job["assistance"]["active_writer"] == "codex"
    assert not runner.permitted(state, page)
    checked_page, check = runner._assistance_page_checker(reference)
    assert checked_page is page
    check()
    return SimpleNamespace(
        runner=runner,
        service=service,
        reference=reference,
        page=page,
        draft=draft,
        intent=intent,
        payload=payload,
        question=question,
        material=material,
        scope=scope,
        journal=journal,
    )


def save_request(case):
    request = make_request(
        "ApiSetFormValue",
        {
            "organizationHostedJobsPageName": case.draft.org,
            "formRenderIdentifier": "render-one",
            "formDefinitionIdentifier": "definition-one",
            "path": case.intent["draft_path"],
            "value": case.payload["text"],
        },
    )
    request.frame = case.page.main_frame
    request.is_navigation_request = lambda: False
    return request


def dispatch(case, request):
    route = bounded_route(request)
    case.runner._live_guard_request(route)
    return route


def framed(case, request):
    request.frame = case.page.main_frame
    request.is_navigation_request = lambda: False
    request.redirected_from = None
    return request


def test_exact_native_text_uses_real_draft_and_one_use_request_guards(native_draft):
    case = native_draft
    request = save_request(case)
    route = dispatch(case, request)
    assert route.outcome == "allowed"
    assert len(route.fetch_calls) == 1
    assert case.draft.pending[request][0] == "save"
    assert case.runner.requests[request]["intent"] == case.intent
    assert not case.runner.permitted(case.service.store.load(), case.page)


def test_actual_native_text_preparation_and_save_prove_the_original_material(native_draft):
    case = native_draft
    assert not case.draft.native_material_verified(case.intent, case.question, case.material)
    request = save_request(case)
    assert dispatch(case, request).outcome == "allowed"
    respond(
        case.draft,
        request,
        {"data": {"setFormValue": form(case.question, {"value": case.payload["text"]})}},
    )
    assert case.draft.native_material_verified(case.intent, case.question, case.material), {
        "prepared_proof_material": case.draft.active["native_proof"]["material"],
        "expected_material": {key: case.material.get(key) for key in ("id", "sha256", "filename")},
    }
    assert case.runner.requests[request]["intent"] == case.intent
    assert case.service.store.load()["jobs"][0]["intent"] == case.intent
    assert not case.runner.permitted(case.service.store.load(), case.page)


@pytest.mark.parametrize(
    "change",
    [
        "body",
        "field",
        "submit_extra",
        "foreign_frame",
        "redirect",
        "old_attempt",
    ],
)
def test_native_text_mismatch_never_reaches_fetch(native_draft, change):
    case = native_draft
    request = save_request(case)
    body = json.loads(request.post_data_buffer)
    if change == "body":
        body["variables"]["value"] += " invented detail"
    elif change == "field":
        body["variables"]["path"] = "salary"
    elif change == "submit_extra":
        body["query"] = body["query"].rsplit("}", 1)[0] + " submitApplication { id } }"
    elif change == "foreign_frame":
        request.frame = SimpleNamespace(page=case.page)
    elif change == "redirect":
        request.redirected_from = object()
    elif change == "old_attempt":
        case.draft.active["intent"]["attempt_id"] = uuid4().hex
    request.post_data_buffer = json.dumps(body).encode()
    route = dispatch(case, request)
    assert route.outcome == "blocked"
    assert route.fetch_calls == []
    assert case.runner.requests == {}
    assert not case.runner.permitted(case.service.store.load(), case.page)


@pytest.mark.parametrize("reset_draft", [False, True])
def test_native_text_duplicate_post_cannot_replay_even_after_draft_reset(native_draft, reset_draft):
    case = native_draft
    first = dispatch(case, save_request(case))
    assert first.outcome == "allowed"
    if reset_draft:
        case.draft.begin(
            case.question,
            case.payload["text"],
            deepcopy(case.intent),
            material=case.material,
        )
    duplicate = dispatch(case, save_request(case))
    assert duplicate.outcome == "blocked"
    assert duplicate.fetch_calls == []
    assert len(case.runner.requests) == 1
    assert len(case.runner.sent_requests) == 1


@pytest.mark.parametrize("native_draft", ["unsealed"], indirect=True)
def test_prepared_intent_without_native_seal_cannot_send(native_draft):
    case = native_draft
    state = case.service.store.load()
    assert (
        case.service.store.native_material_intent(
            state,
            state["jobs"][0],
            case.reference,
        )
        == case.intent
    )
    route = dispatch(case, save_request(case))
    assert route.outcome == "blocked"
    assert route.fetch_calls == []
    assert case.runner.requests == {}


@pytest.mark.parametrize("change", ["revoked", "unknown", "other_unknown"])
def test_native_call_state_cannot_lend_a_material_network_permit(native_draft, change):
    case = native_draft
    receipt = sealed_receipt(case.journal)
    if change == "revoked":
        receipt["revoked"] = True
    elif change == "unknown":
        receipt["calls"][0]["status"] = "unknown"
    else:
        other = deepcopy(receipt["calls"][0])
        other.update(call_id="another-call", tool="browser_click", sequence=2, status="unknown")
        for key in ("material_ref", "material_resolution", "target_descriptor"):
            other.pop(key)
        receipt["calls"].append(other)
    case.service.store.record_native_handoff(
        case.reference,
        request_id="journal-run",
        phase="stopping" if change == "revoked" else "unknown",
        scope=case.scope,
        receipt=receipt,
    )
    route = dispatch(case, save_request(case))
    assert route.outcome == "blocked"
    assert route.fetch_calls == []
    assert case.runner.requests == {}


@pytest.mark.parametrize(
    "change",
    ["storage_stopped", "stop_file", "shared_fault", "page_fault", "blocked_page", "other_run"],
)
def test_native_material_permit_keeps_the_runner_stop_and_fault_gates(native_draft, change):
    case = native_draft
    if change == "storage_stopped":
        case.runner.storage_stopped = True
    elif change == "stop_file":
        case.service.store.block_storage()
    elif change == "shared_fault":
        case.runner.shared_fault = "cua_owner_unknown"
    elif change == "page_fault":
        case.runner.page_faults[case.page] = "page_error"
    elif change == "blocked_page":
        case.runner.blocked_pages[case.page] = "manual_submit_required"
    else:
        case.runner.run_id = uuid4().hex
    state = case.service.store.load()
    assert not case.runner._native_material_network_permitted(state, state["jobs"][0], case.page)
    route = dispatch(case, save_request(case))
    assert route.outcome == "blocked"
    assert route.fetch_calls == []
    assert case.runner.requests == {}


def file_request(case, stage):
    if stage == "handle":
        return framed(
            case,
            make_request(
                "ApiCreateFileUploadHandle",
                {
                    "organizationHostedJobsPageName": case.draft.org,
                    "fileUploadContext": "NonUserFormEngine",
                    "filename": case.payload["filename"],
                    "contentType": "application/pdf",
                    "contentLength": case.payload["size_bytes"],
                },
            ),
        )
    if stage == "link":
        return framed(
            case,
            make_request(
                "ApiSetFormValueToFile",
                {
                    "organizationHostedJobsPageName": case.draft.org,
                    "formRenderIdentifier": "render-one",
                    "formDefinitionIdentifier": "definition-one",
                    "path": case.intent["draft_path"],
                    "fileHandle": "current-handle",
                },
            ),
        )
    raw = base64.b64decode(case.payload["bytes_base64"])
    body = b'--b\r\nContent-Disposition: form-data; name="key"\r\n\r\nfixed-key\r\n'
    body += b'--b\r\nContent-Disposition: form-data; name="Content-Type"\r\n\r\napplication/pdf\r\n'
    body += (
        (
            '--b\r\nContent-Disposition: form-data; name="file"; filename="'
            + case.payload["filename"]
            + '"\r\nContent-Type: application/pdf\r\n\r\n'
        ).encode()
        + raw
        + b"\r\n--b--\r\n"
    )
    return framed(
        case,
        Request(
            method="POST",
            url=UPLOAD,
            resource_type="fetch",
            headers={"content-type": "multipart/form-data; boundary=b"},
            post_data_buffer=body,
            response=lambda: None,
        ),
    )


def file_response(case, request, stage):
    if stage == "handle":
        respond(
            case.draft,
            request,
            {
                "data": {
                    "fileUploadHandle": {
                        "handle": "current-handle",
                        "url": UPLOAD,
                        "fields": {"key": "fixed-key"},
                    }
                }
            },
        )
    elif stage == "upload":
        respond(case.draft, request, {}, 204)
    else:
        respond(
            case.draft,
            request,
            {
                "data": {
                    "setFormValueToFile": form(
                        case.question,
                        {
                            "filename": case.payload["filename"],
                            "id": "current-attachment",
                        },
                    )
                }
            },
        )


@pytest.mark.parametrize("material_journal", ["file"], indirect=True)
def test_native_file_chain_uses_exact_handle_bytes_and_link(native_draft):
    case = native_draft
    for stage in ("handle", "upload", "link"):
        request = file_request(case, stage)
        route = dispatch(case, request)
        assert route.outcome == "allowed", stage
        assert len(route.fetch_calls) == 1
        assert case.runner.requests[request]["kind"] == stage
        assert case.runner.requests[request]["intent"] == case.intent
        file_response(case, request, stage)
    assert case.draft.native_material_verified(case.intent, case.question, case.material)
    assert len(case.runner.sent_requests) == 3
    assert not case.runner.permitted(case.service.store.load(), case.page)


@pytest.mark.parametrize("material_journal", ["file"], indirect=True)
@pytest.mark.parametrize("stage", ["handle", "upload", "link"])
def test_native_file_stage_duplicate_never_dispatches_twice(native_draft, stage):
    case = native_draft
    for current in ("handle", "upload", "link"):
        request = file_request(case, current)
        assert dispatch(case, request).outcome == "allowed"
        if current == stage:
            duplicate = dispatch(case, file_request(case, current))
            assert duplicate.outcome == "blocked"
            assert duplicate.fetch_calls == []
            break
        file_response(case, request, current)


@pytest.mark.parametrize("material_journal", ["file"], indirect=True)
@pytest.mark.parametrize("change", ["file_bytes", "filename", "field", "handle"])
def test_native_file_mismatch_never_reaches_fetch(native_draft, change):
    case = native_draft
    handle = file_request(case, "handle")
    assert dispatch(case, handle).outcome == "allowed"
    file_response(case, handle, "handle")
    request = file_request(case, "upload")
    if change == "file_bytes":
        raw = base64.b64decode(case.payload["bytes_base64"])
        request.post_data_buffer = request.post_data_buffer.replace(raw, raw + b"changed")
    elif change == "filename":
        request.post_data_buffer = request.post_data_buffer.replace(
            case.payload["filename"].encode(),
            b"another.pdf",
        )
    else:
        assert dispatch(case, request).outcome == "allowed"
        file_response(case, request, "upload")
        request = file_request(case, "link")
        body = json.loads(request.post_data_buffer)
        body["variables"]["path" if change == "field" else "fileHandle"] = "another"
        request.post_data_buffer = json.dumps(body).encode()
    route = dispatch(case, request)
    assert route.outcome == "blocked"
    assert route.fetch_calls == []


@pytest.mark.parametrize("material_journal", ["file"], indirect=True)
@pytest.mark.parametrize("native", [True, False])
def test_upload_with_browser_hidden_file_bytes_fails_closed(native_draft, native):
    """Chrome omits disk-backed file bytes from intercepted bodies; never resend an empty file.

    Ashby/Workable early uploads after native delivery stay blocked until resolved (map fog).
    """
    case = native_draft
    handle = file_request(case, "handle")
    assert dispatch(case, handle).outcome == "allowed"
    file_response(case, handle, "handle")
    if not native:
        case.draft.active.pop("native_proof")
    request = file_request(case, "upload")
    raw = base64.b64decode(case.payload["bytes_base64"])
    request.post_data_buffer = request.post_data_buffer.replace(raw, b"")
    route = dispatch(case, request)
    assert route.outcome == "blocked"
    assert route.fetch_calls == []
