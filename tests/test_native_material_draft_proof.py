"""Ashby success belongs to the active native material attempt, not old files."""

import hashlib
import json
from copy import deepcopy
from types import SimpleNamespace
from uuid import uuid4

import pytest
from test_ashby_drafts import PDF, QUERIES, UPLOAD, URL, endpoint

from career_evidence_graph.ashby_drafts import DraftSession
from career_evidence_graph.career_portal_data import PortalDataError


class Request(SimpleNamespace):
    __hash__ = object.__hash__


def make_request(operation, variables):
    return Request(
        method="POST",
        url=endpoint(operation),
        resource_type="fetch",
        headers={"content-type": "application/json"},
        post_data_buffer=json.dumps(
            {"operationName": operation, "query": QUERIES[operation], "variables": variables}
        ).encode(),
        redirected_from=None,
        response=lambda: None,
    )


def form(value=None):
    return {
        "id": "render-one",
        "sourceFormDefinitionId": "definition-one",
        "errorMessages": [],
        "formErrors": [],
        "sections": [
            {
                "fieldEntries": [
                    {
                        "field": {"path": "letter", "title": "Cover letter"},
                        "fieldValue": value,
                        "isRequired": True,
                        "isHidden": False,
                    }
                ]
            }
        ],
    }


def respond(draft, req, data, status=200):
    draft.response(SimpleNamespace(request=req, status=status, json=lambda: data))


@pytest.fixture
def active_draft(request):
    kind = getattr(request, "param", "text")
    text = "I built synthetic services and verified their results."
    raw = text.encode() if kind == "text" else PDF
    sha = hashlib.sha256(raw).hexdigest()
    material = {"id": "letter-id", "sha256": sha}
    if kind == "file":
        material["filename"] = "letter.pdf"
    question = {
        "id": "hosted-letter",
        "draft_path": "letter",
        "question": "Cover letter",
        "type": "textarea" if kind == "text" else "file",
    }
    manifest = {
        "protocol": "fixed-material/v1",
        "resolution_id": uuid4().hex,
        "material_ref": "a" * 64,
        "kind": kind,
        "sha256": sha,
        "size_bytes": len(raw),
    }
    if kind == "file":
        manifest.update(filename="letter.pdf", mime_type="application/pdf")
    intent = {
        "action": "fill" if kind == "text" else "upload",
        "attempt_id": uuid4().hex,
        "field_id": question["id"],
        "draft_path": "letter",
        "material_id": material["id"],
        "sha256": sha,
        "run_id": "original-run",
        "page_id": "original-page",
        "native_material": {
            "protocol": "fixed-material/v1",
            "request_id": "native-run",
            "handoff_id": "handoff",
            "call_id": "material-call",
            "generation": 1,
            "sequence": 1,
            "arguments_digest": "b" * 64,
            "assistance_ref_digest": "c" * 64,
            "resolution": manifest,
        },
    }
    intent.update({"expected_value": text} if kind == "text" else {"filename": "letter.pdf"})
    draft = DraftSession(
        {
            "job_url": URL,
            "platform": "generic",
            "role_title": "Engineer",
            "filename": "resume.pdf",
            "file_sha256": hashlib.sha256(PDF).hexdigest(),
        }
    )
    initial = make_request(
        "ApiJobPosting",
        {"organizationHostedJobsPageName": "synthetic", "jobPostingId": URL.split("/")[4]},
    )
    assert draft.track_public(initial)
    respond(
        draft,
        initial,
        {
            "data": {
                "jobPosting": {"id": draft.posting, "title": "Engineer", "applicationForm": form()}
            }
        },
    )
    expected = text if kind == "text" else len(raw)
    draft.begin(question, expected, intent, material=material)
    return draft, question, material, intent, expected


def save_request(draft, value, *, path="letter"):
    return make_request(
        "ApiSetFormValue",
        {
            "organizationHostedJobsPageName": draft.org,
            "formRenderIdentifier": "render-one",
            "formDefinitionIdentifier": "definition-one",
            "path": path,
            "value": value,
        },
    )


def test_text_save_proves_only_the_active_native_attempt(active_draft):
    draft, question, material, intent, expected = active_draft
    assert not draft.native_material_verified(intent, question, material)
    save = save_request(draft, expected)
    assert draft.allows(save)
    assert not draft.native_material_verified(intent, question, material)
    respond(draft, save, {"data": {"setFormValue": form({"value": expected})}})
    assert draft.native_material_verified(intent, question, material)
    other = deepcopy(intent)
    other["attempt_id"] = uuid4().hex
    assert not draft.native_material_verified(other, question, material)


def test_duplicate_save_endpoint_never_counts_as_current_attempt_proof(active_draft):
    draft, question, material, intent, expected = active_draft
    original = save_request(draft, expected)
    assert draft.allows(original)
    assert not draft.allows(save_request(draft, expected))
    respond(draft, original, {"data": {"setFormValue": form({"value": expected})}})
    assert not draft.native_material_verified(intent, question, material)


def test_failed_save_response_cannot_be_replayed_into_success(active_draft):
    draft, question, material, intent, expected = active_draft
    save = save_request(draft, expected)
    assert draft.allows(save)
    with pytest.raises(ValueError):
        respond(draft, save, {"errors": [{"message": "failed"}]})
    # A late duplicate response is not a fresh successful request for this attempt.
    draft.fields["letter"]["fieldValue"] = {"value": expected}
    draft.done = True
    respond(draft, save, {"data": {"setFormValue": form({"value": expected})}})
    assert not draft.native_material_verified(intent, question, material)


def handle_request(draft, size):
    return make_request(
        "ApiCreateFileUploadHandle",
        {
            "organizationHostedJobsPageName": draft.org,
            "fileUploadContext": "NonUserFormEngine",
            "filename": "letter.pdf",
            "contentType": "application/pdf",
            "contentLength": size,
        },
    )


def handle_response(draft, req, status=200):
    respond(
        draft,
        req,
        {
            "data": {
                "fileUploadHandle": {
                    "handle": "current-handle",
                    "url": UPLOAD,
                    "fields": {"key": "fixed-key"},
                }
            }
        },
        status,
    )


def upload_request(raw=PDF):
    body = b'--b\r\nContent-Disposition: form-data; name="key"\r\n\r\nfixed-key\r\n'
    body += b'--b\r\nContent-Disposition: form-data; name="Content-Type"\r\n\r\napplication/pdf\r\n'
    body += (
        b'--b\r\nContent-Disposition: form-data; name="file"; filename="letter.pdf"\r\n'
        b"Content-Type: application/pdf\r\n\r\n" + raw + b"\r\n--b--\r\n"
    )
    return Request(
        method="POST",
        url=UPLOAD,
        resource_type="fetch",
        headers={"content-type": "multipart/form-data; boundary=b"},
        post_data_buffer=body,
        response=lambda: None,
    )


def link_request(draft, *, path="letter", handle="current-handle"):
    return make_request(
        "ApiSetFormValueToFile",
        {
            "organizationHostedJobsPageName": draft.org,
            "formRenderIdentifier": "render-one",
            "formDefinitionIdentifier": "definition-one",
            "path": path,
            "fileHandle": handle,
        },
    )


def link_response(draft, req, *, status=200, value=None):
    respond(
        draft,
        req,
        {
            "data": {
                "setFormValueToFile": form(
                    value or {"filename": "letter.pdf", "id": "current-attachment"}
                )
            }
        },
        status,
    )


@pytest.mark.parametrize("active_draft", ["file"], indirect=True)
def test_file_proof_requires_this_attempts_handle_bytes_and_link(active_draft):
    draft, question, material, intent, expected = active_draft
    handle = handle_request(draft, expected)
    assert draft.allows(handle)
    handle_response(draft, handle)
    assert not draft.native_material_verified(intent, question, material)
    upload = upload_request()
    assert draft.allows(upload)
    respond(draft, upload, {}, 204)
    assert not draft.native_material_verified(intent, question, material)
    link = link_request(draft)
    assert draft.allows(link)
    link_response(draft, link)
    assert draft.native_material_verified(intent, question, material)
    draft.begin(question, expected, intent, material=material)
    assert draft.file_verified(question, material)
    assert not draft.native_material_verified(intent, question, material)


@pytest.mark.parametrize("active_draft", ["file"], indirect=True)
@pytest.mark.parametrize("stage", ["handle", "upload", "link"])
@pytest.mark.parametrize("failure", ["missing", "failed", "duplicate"])
def test_incomplete_or_duplicate_file_chain_is_not_proof(active_draft, stage, failure):
    draft, question, material, intent, expected = active_draft
    chain = [
        (
            "handle",
            lambda: handle_request(draft, expected),
            lambda req, status=200: handle_response(draft, req, status),
        ),
        ("upload", upload_request, lambda req, status=204: respond(draft, req, {}, status)),
        (
            "link",
            lambda: link_request(draft),
            lambda req, status=200: link_response(draft, req, status=status),
        ),
    ]
    for name, make, answer in chain:
        req = make()
        assert draft.allows(req)
        if name == stage:
            if failure == "missing":
                break
            if failure == "failed":
                with pytest.raises(ValueError):
                    answer(req, 500)
                break
            assert not draft.allows(make())
        answer(req)
    assert not draft.native_material_verified(intent, question, material)


@pytest.mark.parametrize("active_draft", ["file"], indirect=True)
@pytest.mark.parametrize("change", ["bytes", "field", "handle"])
def test_wrong_file_transport_cannot_prove_fixed_material(active_draft, change):
    draft, question, material, intent, expected = active_draft
    handle = handle_request(draft, expected)
    assert draft.allows(handle)
    handle_response(draft, handle)
    upload = upload_request(b"other bytes" if change == "bytes" else PDF)
    if change == "bytes":
        assert not draft.allows(upload)
    else:
        assert draft.allows(upload)
        respond(draft, upload, {}, 204)
        link = link_request(
            draft,
            path="another-field" if change == "field" else "letter",
            handle="other-handle" if change == "handle" else "current-handle",
        )
        assert not draft.allows(link)
    assert not draft.native_material_verified(intent, question, material)


def test_old_pending_response_cannot_complete_a_new_attempt(active_draft):
    draft, question, material, intent, expected = active_draft
    old_request = save_request(draft, expected)
    assert draft.allows(old_request)
    successor = deepcopy(intent)
    successor["attempt_id"] = uuid4().hex
    successor["native_material"]["call_id"] = "successor-call"
    draft.begin(question, expected, successor, material=material)
    with pytest.raises(ValueError, match="another material attempt"):
        respond(draft, old_request, {"data": {"setFormValue": form({"value": expected})}})
    assert not draft.native_material_verified(successor, question, material)


@pytest.mark.parametrize(
    "change", ["attempt", "native_call", "field", "hash", "source_form", "restart"]
)
def test_completed_text_proof_stays_bound_to_its_original_identity(active_draft, change):
    draft, question, material, intent, expected = active_draft
    save = save_request(draft, expected)
    assert draft.allows(save)
    respond(draft, save, {"data": {"setFormValue": form({"value": expected})}})
    if change == "attempt":
        intent["attempt_id"] = uuid4().hex
    elif change == "native_call":
        intent["native_material"]["call_id"] = "changed-call"
    elif change == "field":
        question["id"] = "another-field"
    elif change == "hash":
        material["sha256"] = "0" * 64
    elif change == "source_form":
        draft.form["sourceFormDefinitionId"] = "another-definition"
    else:
        draft = DraftSession(draft.job)
    assert not draft.native_material_verified(intent, question, material)


@pytest.mark.parametrize("active_draft", ["text", "file"], indirect=True)
@pytest.mark.parametrize("change", ["title", "type"])
def test_successful_response_cannot_change_remote_material_field_identity(active_draft, change):
    draft, question, material, intent, expected = active_draft
    original_type = "File" if question["type"] == "file" else "LongText"
    draft.fields["letter"]["field"]["type"] = original_type
    draft.begin(question, expected, intent, material=material)
    remote = form(
        {"filename": "letter.pdf", "id": "current-attachment"}
        if question["type"] == "file"
        else {"value": expected}
    )
    definition = remote["sections"][0]["fieldEntries"][0]["field"]
    definition["type"] = original_type
    definition[change] = "Salary" if change == "title" else "SalaryAmount"
    if question["type"] == "file":
        handle = handle_request(draft, expected)
        assert draft.allows(handle)
        handle_response(draft, handle)
        upload = upload_request()
        assert draft.allows(upload)
        respond(draft, upload, {}, 204)
        req = link_request(draft)
        operation = "setFormValueToFile"
    else:
        req = save_request(draft, expected)
        operation = "setFormValue"
    assert draft.allows(req)
    respond(draft, req, {"data": {operation: remote}})
    assert draft.done is True
    assert (
        draft.file_verified(question, material)
        if question["type"] == "file"
        else draft.saved(question, expected)
    )
    assert not draft.native_material_verified(intent, question, material)


@pytest.mark.parametrize("active_draft", ["text", "file"], indirect=True)
def test_native_begin_refuses_initial_remote_title_conflict_before_requests(active_draft):
    draft, question, material, intent, expected = active_draft
    draft.active = None
    draft.fields["letter"]["field"]["title"] = "Salary"
    before_counts = dict(draft.counts)
    with pytest.raises(PortalDataError) as error:
        draft.begin(question, expected, intent, material=material)
    assert error.value.code == "draft_identity_changed"
    assert draft.active is None
    assert draft.pending == {} and draft.sent == set()
    assert draft.counts == before_counts


@pytest.mark.parametrize("active_draft", ["text", "file"], indirect=True)
def test_native_begin_normalizes_only_case_space_and_required_markers(active_draft):
    draft, question, material, intent, expected = active_draft
    draft.active = None
    title = "  COVER\n  letter * ✱ "
    draft.fields["letter"]["field"]["title"] = title
    draft.begin(question, expected, intent, material=material)
    assert draft.active["intent"] == intent
    assert draft.active["native_proof"]["remote_field"]["title"] == title
    assert draft.pending == {} and draft.sent == set()
