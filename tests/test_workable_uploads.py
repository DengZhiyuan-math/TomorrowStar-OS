"""Synthetic Workable resume transport through the real browser guard."""

import base64
import hashlib
import json
from datetime import UTC, datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
from types import SimpleNamespace
from urllib.parse import urlencode

import pytest
from worker_preview_support import advance_until

from career_evidence_graph.application_worker import WorkerService
from career_evidence_graph.application_worker_browser import ApplicationRunner
from career_evidence_graph.career_portal_data import ApplicationStore

URL = "https://apply.workable.com/synthetic-employer/j/SYNTHETIC1/apply/"
ORIGIN = "https://workable-application-form.s3.us-east-1.amazonaws.com"
KEY = "tmp/ttl-1d/production/00000000-0000-0000-0000-000000000001"
DATE = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
CREDENTIAL = "SYNTHETIC/" + DATE[:8] + "/us-east-1/s3/aws4_request"
DOWNLOAD = (
    ORIGIN
    + "/"
    + KEY
    + "?"
    + urlencode(
        {
            "X-Amz-Algorithm": "AWS4-HMAC-SHA256",
            "X-Amz-Content-Sha256": "UNSIGNED-PAYLOAD",
            "X-Amz-Credential": CREDENTIAL,
            "X-Amz-Date": DATE,
            "X-Amz-Expires": "21600",
            "X-Amz-Signature": "b" * 64,
            "X-Amz-SignedHeaders": "host",
            "x-amz-checksum-mode": "ENABLED",
            "x-id": "GetObject",
        }
    )
)
PRESIGN = "https://apply.workable.com/api/v1/jobs/SYNTHETIC1/form/upload/resume?contentType=application%2Fpdf"
PDF = b"%PDF-1.4 Approved synthetic resume"


def setup_service(tmp_path, monkeypatch):
    apps = tmp_path / "applications"
    apps.mkdir()
    service = WorkerService(ApplicationStore(apps), tmp_path / "worker", live=True, generic=True)
    monkeypatch.setattr(service, "spawn", lambda: None)
    app = service.store.applications.create_application(
        {
            "company": "Synthetic Employer",
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
    service.request("resume", {"controller": "synthetic-controller"})
    return service


def descriptor():
    fields = {
        "utf8": "",
        "bucket": "workable-application-form",
        "key": KEY,
        "X-Amz-Algorithm": "AWS4-HMAC-SHA256",
        "X-Amz-Credential": CREDENTIAL,
        "X-Amz-Date": DATE,
        "X-Amz-Signature": "a" * 64,
    }
    policy = {
        "expiration": (datetime.now(UTC) + timedelta(minutes=10)).isoformat(),
        "conditions": [
            ["starts-with", "$utf8", ""],
            ["eq", "$key", KEY],
            ["content-length-range", 1, 12000000],
            ["starts-with", "$Content-Type", ""],
            *[{k: v} for k, v in fields.items() if k not in {"X-Amz-Signature"}],
        ],
    }
    fields["Policy"] = base64.b64encode(json.dumps(policy).encode()).decode()
    return {
        "uploadPostUrl": {"url": ORIGIN, "fields": fields, "path": KEY},
        "downloadUrl": DOWNLOAD,
    }


@pytest.fixture
def local_transport():
    responses, wire = {}, []

    class Handler(BaseHTTPRequestHandler):
        def handle_request(self):
            body = self.rfile.read(int(self.headers.get("Content-Length", "0")))
            wire.append((self.command, self.path, body))
            if self.path not in responses:
                self.send_error(409)
                return
            status, headers, content = responses[self.path]
            if status == 0:
                self.close_connection = True
                return
            self.send_response(status)
            for key, value in headers.items():
                self.send_header(key, value)
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)

        do_GET = do_POST = handle_request

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}", responses, wire
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


@pytest.mark.worker_browser
@pytest.mark.parametrize(
    "failure",
    [
        "",
        "duplicate_policy_key",
        "bad_filename",
        "encoded_multipart",
        "trailing_multipart",
        "duplicate_boundary",
        "extra_multipart",
        "changed_pdf",
        "wrong_job",
        "forged_grant_apply",
        "autofill",
        "unknown_fallback",
        "duplicate_presign",
        "pause",
        "input_drift",
        "remote_mismatch",
        "readback_without_cors",
        "wrong_object",
        "presign_redirect",
        "download_redirect",
        "upload_redirect",
        "iframe",
    ],
)
def test_workable_approved_pdf_reaches_review_only_after_remote_digest(
    tmp_path, monkeypatch, failure, local_transport
):
    from playwright.sync_api import sync_playwright

    monkeypatch.setenv("PLAYWRIGHT_BROWSERS_PATH", "0")
    service = setup_service(tmp_path, monkeypatch)
    if failure == "forged_grant_apply":
        (service.store.root / "public-read-grants.json").write_text(
            json.dumps(
                {
                    "schemaVersion": 1,
                    "grants": [
                        {
                            "job_url": URL,
                            "url": "https://apply.workable.com/api/v1/jobs/SYNTHETIC1/apply",
                            "body_sha256": hashlib.sha256(b'{"candidate":{}}').hexdigest(),
                        }
                    ],
                }
            )
        )
    html = """<title>Engineer @ Synthetic Employer</title><h1>Engineer</h1><form>
    <div data-ui="resume"><label for="resume">Resume</label>
    <input id="resume" name="resume" type="file" required>
    <span id="name" data-id="filename"></span></div>
    <button type="submit">Submit Application</button></form><script>
    document.querySelector('form').onsubmit=e=>e.preventDefault();
    document.querySelector('#resume').onchange=async()=>{
      const failure=FAILURE, f=document.querySelector('#resume').files[0];
      if(['forged_grant_apply','autofill'].includes(failure))
        await fetch('/api/v1/jobs/SYNTHETIC1/'+(failure==='autofill'?'autofill':'apply'),
          {method:'POST',headers:{'Content-Type':'application/json'},body:'{"candidate":{}}'});
      const presign=failure==='wrong_job'?PRESIGN.replace('SYNTHETIC1','OTHERJOB'):PRESIGN;
      if(failure==='iframe'){
        const i=document.createElement('iframe');document.body.append(i);
        await i.contentWindow.fetch(presign);return;
      }
      const h=await (await fetch(presign)).json(), data=new FormData();
      if(failure==='duplicate_presign')await fetch(presign);
      data.append('Content-Type',f.type);
      for(const [k,v] of Object.entries(h.uploadPostUrl.fields))data.append(k,v);
      data.append('file',failure==='changed_pdf'?
        new File(['%PDF-1.4 different'],f.name,{type:f.type}):f);
      if(failure==='extra_multipart')data.append('candidate','forbidden');
      let options={method:'POST',body:data};
      if(failure==='encoded_multipart'){
        const req=new Request(h.uploadPostUrl.url,options), raw=await req.text();
        options={method:'POST',headers:{'Content-Type':req.headers.get('Content-Type')},
          body:raw.replace('Content-Type: application/pdf\\r\\n\\r\\n',
            'Content-Type: application/pdf\\r\\nContent-Transfer-Encoding: base64\\r\\n\\r\\n')
            .replace(await f.text(),btoa(await f.text()))};
      }
      if(['trailing_multipart','duplicate_boundary'].includes(failure)){
        const req=new Request(h.uploadPostUrl.url,options), raw=await req.text();
        options={method:'POST',headers:{'Content-Type':req.headers.get('Content-Type')+
          (failure==='duplicate_boundary'?'; boundary=forged':'')},
          body:raw+(failure==='trailing_multipart'?'UNAPPROVED TRAILING DATA':'')};
      }
      let r;
      try {r=await fetch(h.uploadPostUrl.url,options);}
      catch(e){if(failure==='unknown_fallback')await fetch(h.uploadPostUrl.url,options);throw e;}
      if(!r.ok)throw Error('upload failed');await r.text();
      document.querySelector('#name').textContent=failure==='bad_filename'?'old-'+f.name:f.name;
      const a=document.createElement('a');a.dataset.action='view';a.href=h.downloadUrl;
      a.textContent='View';document.querySelector('[data-ui=resume]').append(a);
    };</script>""".replace("PRESIGN", json.dumps(PRESIGN)).replace("FAILURE", json.dumps(failure))
    sent, denied = [], []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, channel="chromium")
        try:
            context = browser.new_context(offline=True)
            runner = ApplicationRunner(service.store, context)

            def intercept(route):
                def send():
                    assert route.request.url == URL
                    sent.append(("GET", URL))
                    route.fulfill(status=200, content_type="text/html", body=html)

                def fetch(**options):
                    assert options == {"max_redirects": 0, "max_retries": 0, "timeout": 10000}
                    req = route.request
                    sent.append((req.method, req.url))
                    origin, responses, _ = local_transport
                    status, headers, content = 200, {}, b""
                    if req.url == URL:
                        headers["Content-Type"] = "text/html"
                        content = html.encode()
                    elif req.url == PRESIGN:
                        value = descriptor()
                        if failure == "duplicate_policy_key":
                            fields = value["uploadPostUrl"]["fields"]
                            raw = (
                                base64.b64decode(fields["Policy"])
                                .decode()
                                .replace(
                                    '"bucket": "workable-application-form"',
                                    '"bucket": "wrong", "bucket": "workable-application-form"',
                                )
                            )
                            fields["Policy"] = base64.b64encode(raw.encode()).decode()
                        if failure == "wrong_object":
                            value["downloadUrl"] = DOWNLOAD.replace(KEY, KEY[:-1] + "2")
                        if failure == "pause":
                            service.request("pause", {"controller": "synthetic-controller"})
                        elif failure == "input_drift":
                            from pathlib import Path

                            Path(service.store.load()["jobs"][0]["file_path"]).write_bytes(
                                b"%PDF-1.4 changed"
                            )
                        headers["Content-Type"] = "application/json"
                        content = json.dumps(value).encode()
                        if failure == "presign_redirect":
                            status, headers = 302, {"Location": origin + "/forbidden"}
                    elif req.url == ORIGIN + "/":
                        status = 0 if failure == "unknown_fallback" else 204
                        headers["Access-Control-Allow-Origin"] = "https://apply.workable.com"
                        if failure == "upload_redirect":
                            status, headers = 307, {"Location": origin + "/forbidden"}
                    elif req.url == DOWNLOAD:
                        headers = {
                            "Content-Type": "application/pdf",
                            "Access-Control-Allow-Origin": "https://apply.workable.com",
                        }
                        content = (
                            PDF if failure != "remote_mismatch" else b"%PDF-1.4 remote mismatch"
                        )
                        if failure == "readback_without_cors":
                            headers.pop("Access-Control-Allow-Origin")
                        if failure == "download_redirect":
                            status, headers = 302, {"Location": origin + "/forbidden"}
                    else:
                        raise AssertionError("Unexpected dispatched request: " + req.url)
                    path = "/response-" + str(len(responses))
                    responses[path] = status, headers, content
                    return route.fetch(url=origin + path, **options)

                def abort(reason):
                    denied.append((route.request.method, route.request.url))
                    route.abort(reason)

                runner._live_guard(
                    SimpleNamespace(
                        request=route.request,
                        continue_=send,
                        abort=abort,
                        fetch=fetch,
                        fulfill=route.fulfill,
                    )
                )

            context.route("**/*", intercept)
            expected = (
                "needs_recheck"
                if failure and failure != "readback_without_cors"
                else "ready_for_review"
            )
            job = advance_until(service, runner, lambda row: row["status"] == expected)
            wire = local_transport[2]
            assert not any(path == "/forbidden" for _, path, _ in wire)
            if failure and failure != "readback_without_cors":
                assert job["status"] == "needs_recheck", (job["reason"], sent, denied)
                assert sent.count(("POST", ORIGIN + "/")) == (
                    1
                    if failure
                    in {
                        "bad_filename",
                        "unknown_fallback",
                        "remote_mismatch",
                        "download_redirect",
                        "upload_redirect",
                    }
                    else 0
                )
                assert job["intent"]["action"] == "upload"
                page = runner.pages[job["application_id"]]
                before = list(sent)
                runner.tick()
                # Restarted workers retain the unresolved intent and never open/re-upload.
                replacement = ApplicationRunner(service.store, context)
                replacement.process(
                    service.store.load()["jobs"][0], service.store.load()["batch_id"]
                )
                assert sent == before and not page.is_closed()
                assert not any(
                    "/apply" in url and method != "GET" or "/autofill" in url
                    for method, url in sent
                )
                return
            assert job["status"] == "ready_for_review", (job["reason"], sent, denied)
            uploads = [body for method, _, body in wire if method == "POST"]
            assert len(uploads) == 1 and uploads[0].count(PDF) == 1
            assert b'name="file"; filename="resume.pdf"' in uploads[0]
            assert sent == [
                ("GET", URL),
                ("GET", PRESIGN),
                ("POST", ORIGIN + "/"),
                ("GET", DOWNLOAD),
            ]
            verified = next(
                o for o in job["observations"] if o.get("action") == "workable_upload_verified"
            )
            assert verified["remote_sha256"] == hashlib.sha256(PDF).hexdigest()
            assert job["intent"] is None
            assert not denied
        finally:
            browser.close()
