"""Versioned resume transports use current evidence and retain old upload history.

Ashby readback uses the existing synthetic posting helper. Workable exercises
real isolated Chromium requests and bounded loopback HTTP responses. Neither
fixture starts an application worker or proves canonical binding admission.
"""

import hashlib
from copy import deepcopy
from types import SimpleNamespace

import pytest
from test_ashby_drafts import endpoint, form
from test_workable_uploads import local_transport as local_transport

from career_evidence_graph.ashby_drafts import DraftSession
from career_evidence_graph.career_portal_data import PortalDataError

ASHBY_URL = "https://jobs.ashbyhq.com/synthetic/00000000-0000-0000-0000-000000000001/application"
OLD_PDF = b"%PDF-1.4 old synthetic resume"
NEW_PDF = b"%PDF-1.4 corrected synthetic resume"


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def ashby_readback_page(draft, attachments):
    posting_form = form(attachments)
    posting_form["sections"][0]["fieldEntries"].append(
        {
            "field": {"path": "certificate", "title": "Certificate"},
            "fieldValue": attachments["certificate"],
            "isRequired": False,
            "isHidden": False,
        }
    )
    return SimpleNamespace(
        evaluate=lambda *_args: {
            "data": {
                "jobPosting": {
                    "id": draft.posting,
                    "title": "Engineer",
                    "applicationForm": posting_form,
                }
            }
        }
    )


@pytest.mark.parametrize(
    ("current_attachment", "current_attempt"),
    [
        ("new-resume-attachment", "new-resume-attempt"),
        ("old-resume-attachment", "new-resume-attempt"),
        ("new-resume-attachment", "another-attempt"),
        ("new-resume-attachment", None),
    ],
    ids=["current", "old-same-name-id", "wrong-attempt", "missing-current-attempt"],
)
def test_ashby_replacement_refresh_retains_history_and_requires_new_attachment(
    current_attachment, current_attempt
):
    old_sha, new_sha = digest(OLD_PDF), digest(NEW_PDF)
    certificate = {
        "id": "user-certificate",
        "draft_path": "certificate",
        "field_id": "certificate-field",
        "filename": "certificate.pdf",
        "sha256": digest(b"%PDF-1.4 user certificate"),
    }
    update = {
        "id": "material-update-one",
        "old_sha256": old_sha,
        "status": "complete",
        "upload_attempt_id": "new-resume-attempt",
        "new_attachment": {
            "attachment_id": "new-resume-attachment",
            "attempt_id": "new-resume-attempt",
        },
        "page_receipt": {
            "attachments": {
                "resume": {
                    "id": "resume-field",
                    "draft_path": "resume",
                    "filename": "resume.pdf",
                    "file_sha256": old_sha,
                    "multiple": False,
                },
                "remote": {"attachment_id": "old-resume-attachment", "sha256": old_sha},
                "empty": False,
                "others": [],
            }
        },
    }
    job = {
        "job_url": ASHBY_URL,
        "role_title": "Engineer",
        "filename": "resume.pdf",
        "file_sha256": new_sha,
        "materials": [certificate],
        "material_update": update,
    }
    results = {
        "old-resume-attempt": {
            "intent": {
                "action": "upload",
                "attempt_id": "old-resume-attempt",
                "field_id": "resume-field",
                "draft_path": "resume",
                "sha256": old_sha,
            },
            "conclusion": "current_matches",
        },
        "user-certificate-attempt": {
            "intent": {
                "action": "upload",
                "attempt_id": "user-certificate-attempt",
                "material_id": certificate["id"],
                "field_id": "certificate-field",
                "draft_path": "certificate",
                "sha256": certificate["sha256"],
            },
            "conclusion": "current_matches",
        },
        "new-resume-attempt": {
            "intent": {
                "action": "upload",
                "attempt_id": current_attempt,
                "field_id": "resume-field",
                "draft_path": "resume",
                "sha256": new_sha,
                "material_update_id": update["id"],
                "replaces_sha256": old_sha,
            },
            "conclusion": "current_matches",
        },
    }
    if current_attempt is None:
        results.pop("new-resume-attempt")
    before = deepcopy((job, results))
    draft = DraftSession(job)
    draft.public_request = {"url": endpoint("ApiJobPosting"), "body": "synthetic query"}
    draft.uploaded = draft.linked = True
    draft.files["resume"] = {
        "id": "resume",
        "filename": "resume.pdf",
        "sha256": old_sha,
        "attachment_id": "old-resume-attachment",
    }
    page = ashby_readback_page(
        draft,
        {
            "resume": {"id": current_attachment, "filename": "resume.pdf"},
            "certificate": {"id": "certificate-attachment", "filename": "certificate.pdf"},
        },
    )
    current_resume = {"id": "resume", "filename": "resume.pdf", "sha256": new_sha}
    if current_attachment == "old-resume-attachment" or current_attempt == "another-attempt":
        with pytest.raises(PortalDataError):
            draft.refresh(page, results)
    else:
        draft.refresh(page, results)
        assert draft.file_verified({"draft_path": "resume"}, current_resume) is bool(
            current_attempt
        )
        assert draft.uploaded is bool(current_attempt) and draft.linked is bool(current_attempt)
        if current_attempt:
            assert draft.files["resume"]["attachment_id"] == "new-resume-attachment"
        assert draft.file_verified({"draft_path": "certificate"}, certificate)
        assert draft.files["certificate"]["attachment_id"] == "certificate-attachment"
        assert not draft.file_verified(
            {"draft_path": "resume"}, {**current_resume, "sha256": old_sha}
        )
        assert not draft.file_verified({"draft_path": "certificate"}, current_resume)
    assert (job, results) == before


@pytest.mark.worker_browser
@pytest.mark.parametrize("new_remote_bytes", [NEW_PDF, OLD_PDF], ids=["new-digest", "old-digest"])
def test_workable_original_page_second_attempt_requires_its_own_remote_bytes(
    tmp_path, monkeypatch, local_transport, new_remote_bytes
):
    """Real browser wire; adapter recreation follows the verified Runner contract.

    This intentionally tests transport admission rather than faking a canonical
    workflow grant. The original-Page transaction itself has separate coverage.
    """
    import base64
    import json

    from playwright.sync_api import sync_playwright
    from test_workable_uploads import KEY, ORIGIN, PRESIGN, URL, descriptor

    from career_evidence_graph.workable_uploads import ResumeUpload

    monkeypatch.setenv("PLAYWRIGHT_BROWSERS_PATH", "0")
    origin, responses, wire = local_transport
    old_path, new_path = tmp_path / "old.pdf", tmp_path / "new.pdf"
    old_path.write_bytes(OLD_PDF)
    new_path.write_bytes(NEW_PDF)
    old_job = {
        "job_url": URL,
        "filename": "resume.pdf",
        "file_sha256": digest(OLD_PDF),
        "file_path": str(old_path),
    }
    new_job = {**old_job, "file_sha256": digest(NEW_PDF), "file_path": str(new_path)}
    old_adapter = ResumeUpload(old_job)
    current = [old_adapter]
    question = {"id": "resume", "control_ids": ["resume-field"]}
    old_intent = {"action": "upload", "attempt_id": "old-attempt", "sha256": digest(OLD_PDF)}
    new_intent = {"action": "upload", "attempt_id": "new-attempt", "sha256": digest(NEW_PDF)}
    attempts, denied = [], []
    html = """<title>Synthetic Workable</title><form>
      <div data-ui="resume"><label>Resume
        <input id="resume" data-ts-worker-field="resume-field" type="file"></label>
        <span data-id="filename"></span><a data-action="view" hidden>View</a></div>
      <input id="notes"><button type="submit">Submit Application</button></form><script>
      window.finalActions=0;document.querySelector('form').onsubmit=e=>{
        e.preventDefault();window.finalActions++};
      document.querySelector('#resume').onchange=async()=>{
        window.uploadDone=false;
        const file=document.querySelector('#resume').files[0];
        const handle=await (await fetch(PRESIGN)).json(), data=new FormData();
        data.append('Content-Type',file.type);
        for(const [key,value] of Object.entries(handle.uploadPostUrl.fields))data.append(key,value);
        data.append('file',file);
        const result=await fetch(handle.uploadPostUrl.url,{method:'POST',body:data});
        if(!result.ok)throw Error('upload failed');await result.text();
        document.querySelector('[data-id=filename]').textContent=file.name;
        const view=document.querySelector('[data-action=view]');
        view.href=handle.downloadUrl;view.hidden=false;window.uploadDone=true;
      };</script>""".replace("PRESIGN", json.dumps(PRESIGN))
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True, channel="chromium")
        try:
            context = browser.new_context(offline=True)
            page = context.new_page()
            context.on("response", lambda response: current[0].response(response))

            def intercept(route):
                request = route.request
                if request.url == URL and request.method == "GET":
                    route.fulfill(status=200, content_type="text/html", body=html)
                    return
                if not current[0].allows(request):
                    denied.append((request.method, request.url))
                    route.abort("blockedbyclient")
                    return
                attempts.append((current[0].active["attempt_id"], request.method, request.url))
                headers, status, content = {}, 200, b""
                if request.url == PRESIGN:
                    number = 1 if current[0] is old_adapter else 2
                    new_key = KEY[:-1] + str(number)
                    value = json.loads(json.dumps(descriptor()).replace(KEY, new_key))
                    policy = value["uploadPostUrl"]["fields"]["Policy"]
                    value["uploadPostUrl"]["fields"]["Policy"] = base64.b64encode(
                        base64.b64decode(policy).replace(KEY.encode(), new_key.encode())
                    ).decode()
                    headers["Content-Type"] = "application/json"
                    content = json.dumps(value).encode()
                elif request.url == ORIGIN + "/":
                    status = 204
                    headers["Access-Control-Allow-Origin"] = "https://apply.workable.com"
                else:
                    assert request.url == current[0].handle["downloadUrl"]
                    content = OLD_PDF if current[0] is old_adapter else new_remote_bytes
                    headers = {
                        "Content-Type": "application/pdf",
                        "Access-Control-Allow-Origin": "https://apply.workable.com",
                    }
                path = "/replacement-" + str(len(responses))
                responses[path] = status, headers, content
                response = route.fetch(
                    url=origin + path, max_redirects=0, max_retries=0, timeout=10000
                )
                try:
                    route.fulfill(response=response)
                finally:
                    response.dispose()

            context.route("**/*", intercept)
            page.goto(URL)
            page.locator("#notes").fill("Retain user text on the original page.")
            old_adapter.begin(question, old_intent, page)
            # Pending ownership cannot be erased by asking the same adapter to
            # begin another version, before any presign request has completed.
            with pytest.raises(ValueError, match="already attempted"):
                old_adapter.begin(question, new_intent, page)
            assert old_adapter.active == old_intent and attempts == []
            page.locator("#resume").set_input_files(
                {"name": "resume.pdf", "mimeType": "application/pdf", "buffer": OLD_PDF}
            )
            page.wait_for_function("window.uploadDone === true")
            old_adapter.wait(page)
            assert old_adapter.readback(page)["remote_sha256"] == digest(OLD_PDF)
            old_state = (
                deepcopy(old_adapter.active),
                deepcopy(old_adapter.handle),
                old_adapter.uploaded,
                old_adapter.remote_sha256,
                set(old_adapter.sent),
            )
            with pytest.raises(ValueError, match="already attempted"):
                old_adapter.begin(question, new_intent, page)
            assert (
                old_adapter.active,
                old_adapter.handle,
                old_adapter.uploaded,
                old_adapter.remote_sha256,
                old_adapter.sent,
            ) == old_state
            # The production Runner replaces the transport only after its
            # original-page transaction has verified the archived old version.
            replacement = current[0] = ResumeUpload(new_job)
            assert replacement.handle is None and replacement.remote_sha256 == ""
            replacement.begin(question, new_intent, page)
            page.locator("#resume").set_input_files(
                {"name": "resume.pdf", "mimeType": "application/pdf", "buffer": NEW_PDF}
            )
            page.wait_for_function("window.uploadDone === true")
            replacement.wait(page)
            if new_remote_bytes == OLD_PDF:
                with pytest.raises((ValueError, PortalDataError)):
                    replacement.readback(page)
                assert replacement.remote_sha256 == ""
            else:
                assert replacement.readback(page)["remote_sha256"] == digest(NEW_PDF)
            assert replacement.handle != old_adapter.handle
            assert old_adapter.active == old_intent and replacement.active == new_intent
            assert old_adapter.remote_sha256 == digest(OLD_PDF)
            assert page.locator("#notes").input_value() == "Retain user text on the original page."
            assert len(context.pages) == 1 and page.url == URL
            assert page.evaluate("window.finalActions") == 0 and denied == []
            uploads = [body for method, _path, body in wire if method == "POST"]
            assert len(uploads) == 2
            assert uploads[0].count(OLD_PDF) == 1 and NEW_PDF not in uploads[0]
            assert uploads[1].count(NEW_PDF) == 1 and OLD_PDF not in uploads[1]
            assert [attempt for attempt, method, _url in attempts if method == "POST"] == [
                "old-attempt",
                "new-attempt",
            ]
        finally:
            browser.close()


@pytest.mark.parametrize(
    "current_present,current_attachment",
    [
        (True, "current-a-attachment"),
        (False, "current-a-attachment"),
        (True, "old-a-attachment"),
    ],
)
def test_ashby_return_to_a_uses_current_attempt_not_historical_same_hash(
    current_present, current_attachment
):
    a_sha, b_sha = digest(OLD_PDF), digest(NEW_PDF)
    certificate = {
        "id": "certificate",
        "draft_path": "certificate",
        "field_id": "certificate-field",
        "filename": "certificate.pdf",
        "sha256": digest(b"certificate"),
    }
    update = {
        "id": "b-to-a",
        "status": "complete",
        "old_sha256": b_sha,
        "upload_attempt_id": "a-current",
        "new_attachment": {"attachment_id": "current-a-attachment", "attempt_id": "a-current"},
        "page_receipt": {
            "attachments": {"remote": {"attachment_id": "b-attachment", "sha256": b_sha}}
        },
    }
    job = {
        "job_url": ASHBY_URL,
        "role_title": "Engineer",
        "filename": "resume.pdf",
        "file_sha256": a_sha,
        "materials": [certificate],
        "material_update": update,
        "material_update_history": [{"id": "a-to-b", "status": "complete", "old_sha256": a_sha}],
    }

    def resume(identifier, sha, transaction=None):
        return {
            "intent": {
                "action": "upload",
                "attempt_id": identifier,
                "field_id": "resume-field",
                "draft_path": "resume",
                "sha256": sha,
                **({"material_update_id": transaction} if transaction else {}),
            },
            "conclusion": "current_matches",
        }

    results = {
        "a-original": resume("a-original", a_sha),
        "b": resume("b", b_sha, "a-to-b"),
        "certificate": {
            "intent": {
                "action": "upload",
                "attempt_id": "certificate",
                "material_id": certificate["id"],
                "draft_path": "certificate",
                "sha256": certificate["sha256"],
            },
            "conclusion": "current_matches",
        },
    }
    if current_present:
        results["a-current"] = resume("a-current", a_sha, "b-to-a")
    before = deepcopy((job, results))
    draft = DraftSession(job)
    draft.public_request = {"url": endpoint("ApiJobPosting"), "body": "synthetic query"}
    page = ashby_readback_page(
        draft,
        {
            "resume": {"id": current_attachment, "filename": "resume.pdf"},
            "certificate": {"id": "certificate-attachment", "filename": "certificate.pdf"},
        },
    )
    if current_attachment == "old-a-attachment":
        with pytest.raises(PortalDataError):
            draft.refresh(page, results)
    else:
        draft.refresh(page, results)
        assert (
            draft.file_verified(
                {"draft_path": "resume"},
                {"id": "resume", "filename": "resume.pdf", "sha256": a_sha},
            )
            is current_present
        )
        assert draft.uploaded is current_present and draft.linked is current_present
        assert draft.file_verified({"draft_path": "certificate"}, certificate)
    assert (job, results) == before
