"""Real native fixed-material delivery on the original synthetic Page.

The adopted archive and completed PDF builds are explicit offline fixtures.
Worker admission, native delivery, local byte readback and cleanup are real.
"""

import base64
import hashlib
import json
import os
import socket
import threading
import time
from copy import deepcopy
from dataclasses import asdict
from email.parser import BytesParser
from email.policy import default
from functools import partial
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace

import pytest
import test_j08_flow_combination as recorded_flow
from test_application_flow import wait_for
from test_ashby_drafts import QUERIES, UPLOAD, endpoint
from test_ashby_drafts import URL as ASHBY_URL
from test_canonical_career_sources import canonical as canonical
from test_cover_letter_content import Compiler
from test_cover_letter_delivery import TEMPLATE
from test_j08_flow_combination import json_flow as json_flow
from test_j08_material_binding import json_material as json_material
from test_j08_material_binding import recorded_pipeline_clock as recorded_pipeline_clock
from test_j08_worker_information import bound_worker
from test_native_material_draft_proof import form as ashby_form
from test_p08_combination import SavedPrism
from test_worker_native_handoff_browser import (
    drive_until,
    native_denial,
    original_page_intact,
    read_peer,
    stopped_native,
)
from test_worker_native_handoff_browser import (
    native_handoff as native_handoff,
)

from career_evidence_graph import application_form_runner, hosted_ats
from career_evidence_graph.application_materials import SupplementalMaterials, material_kind
from career_evidence_graph.application_single_binding import read_delivered_material_inputs
from career_evidence_graph.application_worker import start_run
from career_evidence_graph.ashby_drafts import DraftSession
from career_evidence_graph.career_portal_data import PortalDataError

pytestmark = [
    pytest.mark.worker_browser,
    pytest.mark.skipif(
        os.environ.get("TS_CUA_NATIVE_TEST") != "1", reason="Explicit native Cua opt-in"
    ),
]

PDF = Path(__file__).parent / "fixtures/pdf-export/current-template.pdf"
PDF_SHA = "024c16287b8b9b105b4dbab31a0bb94fcca0d3ed4b47ecd8cf0b8745ae3b62be"
PEER = Path(__file__).with_name("native_material_peer.py")


@pytest.fixture(autouse=True)
def configure_material_portal(request, monkeypatch):
    if request.node.callspec.params["native_handoff"]["effect"] == "material_upload_lost":
        # Preserve the actual Portal factory and supply its existing configuration
        # parameter before it creates the original private WorkerService.
        monkeypatch.setattr(
            recorded_flow,
            "create_server",
            partial(recorded_flow.create_server, worker_generic=True),
        )


@pytest.fixture
def retained_assistance_page(json_material, monkeypatch, request, tmp_path):
    """Reuse an actual saved P04 delivery; never substitute its material resolver."""
    case = json_material
    remote = request.node.callspec.params["native_handoff"]["effect"] == "material_upload_lost"
    if remote:
        case.job = case.applications.update_application(
            case.job["id"], {"url": ASHBY_URL}, case.job["revision"]
        )
        assert case.server.worker_service.generic is True
        assert case.server.worker_service.store.load()["generic_enabled"] is True
    # The existing archive fixture records builds. Its permissive page-count
    # adapter is unnecessary here: the production PDF byte validator is used.
    case.store.pdf_inspector = None
    case.store.prism_client = SavedPrism()
    worker, job = bound_worker(case)
    task = wait_for(
        case.flow,
        job["single_binding"]["task_id"],
        lambda row: (
            row.get("cover_letter", {}).get("status") == "ready"
            and row.get("material_consistency", {}).get("status") == "passed"
        ),
    )
    assert task["cover_letter"]["result"]["content_revision"]
    assert worker.store.single_validator is None
    # The Portal installs the production delivered-material reader; nothing is substituted.
    provider = worker.store.single_material_source_provider
    assert provider.func is read_delivered_material_inputs and not provider.args
    assert provider.keywords == {"delivery_reader": case.flow.fixed_writing_inputs}
    worker.store.check_single(job, worker.store.load(), material_required=True)

    def repeated_author(*args, **kwargs):
        pytest.fail("Native delivery must not restart author/JD/consistency work")

    monkeypatch.setattr(case.store, "model_runner", repeated_author)
    monkeypatch.setattr(type(case.runner), "__call__", repeated_author)
    worker.request("resume", {"controller": "synthetic-controller"})
    run_id = start_run(worker.store)
    state = worker.store.load()
    state["jobs"][0].update(status="filling", page_open=True)
    state["jobs"][0]["page_observation"] = {
        "run_id": run_id,
        "page_id": "retained-page",
        "event": "observed",
        "at": time.time(),
    }
    state["jobs"][0]["form_state"] = {
        "binding": {
            "run_id": run_id,
            "page_id": "retained-page",
            "document_token": "original-document",
            "step": job["job_url"],
        }
    }
    worker.store.save(state)
    receiver = start_receiver(worker, tmp_path / "upload-receiver") if remote else None
    worker.native_material_receiver = receiver
    try:
        yield worker, job["application_id"]
    finally:
        if receiver is not None:
            receiver.server.shutdown()
            receiver.server.server_close()
            receiver.thread.join(timeout=3)
            cleanup = {
                "automatic": True,
                "server_socket_fileno": receiver.server.socket.fileno(),
                "serve_thread_alive": receiver.thread.is_alive(),
                "completed_at": time.time(),
            }
            (receiver.root / "cleanup.json").write_text(json.dumps(cleanup, indent=2))
            assert cleanup["server_socket_fileno"] == -1
            assert cleanup["serve_thread_alive"] is False


def start_receiver(worker, root):
    """Receive real approved multipart bytes, then lose only their HTTP reply."""
    root.mkdir(mode=0o700)
    state = SimpleNamespace(root=root, events=[], mappings=[], peer_root=None)

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            raw = self.rfile.read(int(self.headers.get("Content-Length", "0")))
            event = {
                "path": self.path,
                "body_sha256": hashlib.sha256(raw).hexdigest(),
                "size_bytes": len(raw),
                "at": time.time(),
            }
            state.events.append(event)
            if self.path == "/upload":
                message = BytesParser(policy=default).parsebytes(
                    b"Content-Type: " + self.headers["Content-Type"].encode() + b"\r\n\r\n" + raw
                )
                files = [
                    part
                    for part in message.iter_parts()
                    if part.get_param("name", header="content-disposition") == "file"
                ]
                assert len(files) == 1
                actual = files[0].get_payload(decode=True)
                event.update(
                    file_sha256=hashlib.sha256(actual).hexdigest(),
                    file_size=len(actual),
                    filename=files[0].get_filename(),
                    intent=deepcopy(worker.store.load()["jobs"][0]["intent"]),
                )
                (root / "received.pdf").write_bytes(actual)
                (root / "received.pdf").chmod(0o600)
                (root / "upload-received.json").write_text(json.dumps(event, indent=2))
                # Native core and the peer continue independently of the host's
                # bounded route.fetch. Lose the reply only after the real local
                # native result is confirmed, not while its outcome is unknown.
                deadline = time.monotonic() + 8
                while time.monotonic() < deadline:
                    rows = read_peer(state.peer_root)
                    confirmed = [
                        row
                        for row in rows
                        if row["kind"] == "material_local_result"
                        and row["result"].get("structuredContent", {}).get("effect") == "confirmed"
                    ]
                    if confirmed:
                        event["native_local_result_before_disconnect"] = confirmed[0]
                        break
                    time.sleep(0.01)
                event["disconnected_at"] = time.time()
                (root / "upload-disconnected.json").write_text(json.dumps(event, indent=2))
                self.close_connection = True
                self.connection.shutdown(socket.SHUT_RDWR)
                return
            body = json.loads(raw)
            operation = body["operationName"]
            form = ashby_form()
            form["sections"][0]["fieldEntries"][0]["field"]["title"] = "Cover letter PDF"
            if operation == "ApiJobPosting":
                result = {
                    "jobPosting": {
                        "id": ASHBY_URL.split("/")[4],
                        "title": "Research Engineer",
                        "applicationForm": form,
                    }
                }
            elif operation == "ApiCreateFileUploadHandle":
                result = {
                    "fileUploadHandle": {
                        "handle": "native-original-upload",
                        "url": UPLOAD,
                        "fields": {"key": "synthetic", "policy": "fixed"},
                    }
                }
            else:
                event["unexpected_operation"] = operation
                self.send_error(409)
                return
            output = json.dumps({"data": result}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(output)))
            self.end_headers()
            self.wfile.write(output)

        def log_message(self, *args):
            pass

    state.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    state.thread = threading.Thread(target=state.server.serve_forever, daemon=True)
    state.thread.start()
    return state


def install_ashby_transport(h):
    receiver = h.original.native_material_receiver
    receiver.peer_root = h.runtime
    h.runner.native_material_receiver = receiver
    job = h.service.store.load()["jobs"][0]
    assert job["job_url"] == ASHBY_URL and job["platform"] == "generic"
    assert h.service.store.load()["generic_enabled"] is True
    h.runner.drafts[h.page] = DraftSession(job)
    mapping = {
        endpoint(name): "/graphql?op=" + name
        for name in (
            "ApiJobPosting",
            "ApiCreateFileUploadHandle",
            "ApiSetFormValueToFile",
        )
    }
    mapping[UPLOAD] = "/upload"

    def intercept(route):
        if route.request.url not in mapping:
            route.fallback()
            return

        def fetch(**options):
            assert options == {"max_redirects": 0, "max_retries": 0, "timeout": 10000}
            physical = (
                f"http://127.0.0.1:{receiver.server.server_port}" + mapping[route.request.url]
            )
            record = {
                "logical_url": route.request.url,
                "receiver_url": physical,
                "method": route.request.method,
                "options": options,
            }
            receiver.mappings.append(record)
            try:
                response = route.fetch(url=physical, **options)
            except Exception as error:
                record["exception"] = {"type": type(error).__name__, "message": str(error)}
                raise
            record.update(actual_response_url=response.url, status=response.status)
            return response

        # Preserve the original Browser Request and actual APIResponse. The
        # production guard checks the logical request; no response URL is forged.
        h.runner._live_guard(
            SimpleNamespace(
                request=route.request,
                fetch=fetch,
                fulfill=route.fulfill,
                abort=route.abort,
                continue_=lambda: pytest.fail("Draft transport must use bounded fetch"),
            )
        )

    h.context.route("**/*", intercept)


def material_html(effect):
    control = (
        '<label>Cover letter<textarea id="letter" name="cover_letter"></textarea></label>'
        '<label>Cover letter PDF<input id="alternative" type="file" accept=".pdf"></label>'
        if effect == "material_text"
        else '<label>Cover letter PDF<input id="letter" name="cover_letter" type="file" '
        'accept=".pdf" required></label>'
    )
    fault = {
        "material_unknown": "event.target.value='';",
        "material_pending": "event.target.setCustomValidity('synthetic pending validation');",
        "material_stop": """
          const start=Date.now(); console.log('material-handler-start:'+start);
          while(Date.now()-start<8000) {}
          console.log('material-handler-end:'+Date.now());
        """,
    }.get(effect, "")
    html = (
        """<!doctype html><title>Synthetic Employer - Research Engineer</title>
<link rel="icon" href="data:,"><h1>Research Engineer</h1>
<form id="application-form" method="post" action="/submit">
<label>Email<input id="email" type="email"></label>"""
        + control
        + """
<label>Human note<input id="human" value="Keep this human note"></label>
<label>Certificate<input id="certificate" type="file" accept=".pdf"></label>
<label>Resume/CV<input id="wrong" name="resume" type="file"></label>
<button type="submit">Submit</button></form><script>
window.__tomorrowstarMaterialDocument=crypto.randomUUID();
window.nativeInputEvents=0; window.nativeSubmitEvents=0;
window.materialInputEvents=0; window.materialChangeEvents=0;
document.querySelector('#email').addEventListener('input',()=>window.nativeInputEvents++);
document.querySelector('form').addEventListener('submit',()=>window.nativeSubmitEvents++);
document.querySelector('#letter').addEventListener('input',event=>{
  window.materialInputEvents++;
  if(event.target.files?.length && !window.originalMaterialFile)
    window.originalMaterialFile=event.target.files[0];
  """
        + fault
        + """
});
document.querySelector('#letter').addEventListener('change',()=>window.materialChangeEvents++);
</script>"""
    )
    if effect == "material_upload_lost":
        html = html.replace('id="letter"', 'id="letter" data-field-path="letter"')
        script = """
const queries=QUERIES;
async function call(op,variables) {
  const response=await fetch('/api/non-user-graphql?op='+op,{method:'POST',
    headers:{'Content-Type':'application/json'},
    body:JSON.stringify({operationName:op,query:queries[op],variables})});
  return response.json();
}
window.materialUploadState='not-started';
call('ApiJobPosting',{organizationHostedJobsPageName:'synthetic',jobPostingId:POSTING})
  .then(()=>window.materialBootstrapReady=true);
document.querySelector('#letter').addEventListener('change',async()=>{
  try {
    window.materialUploadState='handle';
    const file=document.querySelector('#letter').files[0];
    const result=await call('ApiCreateFileUploadHandle',{
      organizationHostedJobsPageName:'synthetic',fileUploadContext:'NonUserFormEngine',
      filename:file.name,contentType:file.type,contentLength:file.size});
    const handle=result.data.fileUploadHandle, data=new FormData();
    data.append('Content-Type',file.type);
    for(const [key,value] of Object.entries(handle.fields)) data.append(key,value);
    data.append('file',file);
    window.materialUploadState='upload';
    await fetch(handle.url,{method:'POST',body:data});
    window.materialUploadState='link';
    await call('ApiSetFormValueToFile',{organizationHostedJobsPageName:'synthetic',
      formRenderIdentifier:'render-one',formDefinitionIdentifier:'definition-one',
      path:'letter',fileHandle:handle.handle});
    window.materialUploadState='completed';
  } catch(error) { window.materialUploadState='reply-lost'; }
});
""".replace("QUERIES", json.dumps(QUERIES)).replace("POSTING", json.dumps(ASHBY_URL.split("/")[4]))
        html = html.replace("</script>", script + "</script>")
    return html.encode()


def observe_materials(h):
    observed = h.page.evaluate(hosted_ats.INSPECT_HOSTED, True)
    for question in observed["fields"]:
        if material_kind(question) == "cover_letter":
            # Same actual-control augmentation as ApplicationRunner.observe;
            # the loopback document does not pass an external ATS URL check.
            question.update(
                hosted_ats.control(h.page, question).evaluate(
                    "e=>({accept:e.getAttribute('accept')||'',"
                    "max_length:e.maxLength>=0?e.maxLength:null})"
                )
            )
    return observed


def prepare_materials(h):
    """Prepare current actual fields before request creates an immutable binding."""
    assert hashlib.sha256(PDF.read_bytes()).hexdigest() == PDF_SHA
    assert h.service.store.load()["jobs"][0].get("assistance") is None
    assert h.service.store.single_validator is None
    assert h.service.store.single_material_source_provider is None
    if receiver := getattr(h.runner, "native_material_receiver", None):
        h.page.wait_for_function("window.materialBootstrapReady===true", timeout=8000)
        assert h.runner.drafts[h.page].form["id"] == "render-one"
        h.extra_evidence["material_receiver"] = {
            "events": receiver.events,
            "mappings": receiver.mappings,
            "logical_document_url": h.page.url,
            "root": str(receiver.root),
            "scope": "synthetic transport mapping; no real ATS connection",
        }
    template = h.runtime / "synthetic-letter-template.tex"
    template.write_text(TEMPLATE)
    template.chmod(0o600)
    h.service.store.cover_letter_template = template
    h.service.store.cover_letter_client = Compiler()
    # This is initial synthetic human content, never the target material write.
    h.page.evaluate(
        """encoded=>{
      const data=Uint8Array.from(atob(encoded),c=>c.charCodeAt(0));
      const file=new File([data], 'cover-letter.pdf', {type:'application/pdf'});
      const transfer=new DataTransfer(); transfer.items.add(file);
      document.querySelector('#certificate').files=transfer.files;
      window.originalHumanFile=document.querySelector('#certificate').files[0];
    }""",
        base64.b64encode(PDF.read_bytes() + b"\n% human attachment\n").decode(),
    )
    state = h.service.store.load()
    job = state["jobs"][0]
    fixed = h.service.store.material_inputs(job)
    archive = (
        h.service.store.single_flow_root
        / "analyses"
        / job["single_binding"]["analysis_id"]
        / "source-snapshot.json"
    )
    assert json.loads(archive.read_text()) == fixed["sources"]
    # Parse actual DOM with the production generic observer; the sole loopback
    # Page and its document are already bound by the real native fixture.
    observed = observe_materials(h)
    boundary = SupplementalMaterials(
        h.service.store,
        allowed=lambda state, identifier: h.runner.permitted(state, h.runner.pages.get(identifier)),
        update=h.runner.update,
        persist=h.runner.persist,
    )
    assert boundary.prepare(
        job,
        state["batch_id"],
        observed,
        temporary=h.runner.temporary,
        page_binding={"run_id": h.runner.run_id, "page_id": h.runner.page_ids[h.page]},
    )
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        state = h.service.store.load()
        job = state["jobs"][0]
        observed = observe_materials(h)
        captured = application_form_runner.capture(
            h.runner,
            h.page,
            job,
            state["batch_id"],
            observed,
        )
        if captured["parser"]["status"] == "stable":
            break
        h.page.wait_for_timeout(260)
    else:
        pytest.fail("Actual material form did not become stable before first request")
    current = h.service.store.load()["jobs"][0]
    letter = [row for row in current["materials"] if row["kind"] == "cover_letter"]
    assert len(letter) == 1 and letter[0]["status"] == "ready"
    h.service.store.verify_material_source(letter[0])
    h.service.store.verify_material(letter[0], current)
    h.extra_evidence["material_preparation"] = {
        "source_fixture": "saved synthetic P04 archive; recorded author/build, no actual model",
        "fixed_inputs": fixed,
        "archive_sha256": hashlib.sha256(archive.read_bytes()).hexdigest(),
        "material": deepcopy(letter[0]),
        "observed": observed,
        "compile_calls": h.service.store.cover_letter_client.calls,
    }


def case(effect):
    return pytest.param(
        {
            "effect": effect,
            "html": material_html(effect),
            "peer_source": PEER,
            "before_request": prepare_materials,
            "peer_settings": {
                "target_label": "Resume/CV"
                if effect == "material_wrong_field"
                else "Cover letter"
                if effect == "material_text"
                else "Cover letter PDF",
                "target_action": "type" if effect == "material_text" else "upload",
            },
            **(
                {
                    "generic": True,
                    "document_url": ASHBY_URL,
                    "before_navigation": install_ashby_transport,
                }
                if effect == "material_upload_lost"
                else {}
            ),
        },
        id=effect,
    )


def file_bytes(page, selector):
    return bytes(
        page.locator(selector).evaluate(
            "async e=>e.files.length ? "
            "Array.from(new Uint8Array(await e.files[0].arrayBuffer())) : []"
        )
    )


def evidence(h):
    raw = file_bytes(h.page, "#letter") if h.effect != "material_text" else b""
    return {
        "input_events": h.page.evaluate("window.materialInputEvents"),
        "change_events": h.page.evaluate("window.materialChangeEvents"),
        "file_count": h.page.locator("#letter").evaluate("e=>e.files?.length??0"),
        "file_sha256": hashlib.sha256(raw).hexdigest() if raw else None,
        "file_size": len(raw),
        "original_file_retained": h.page.evaluate(
            "window.originalMaterialFile ? "
            "document.querySelector('#letter').files?.[0]===window.originalMaterialFile : null"
        ),
        "text": h.page.locator("#letter").input_value() if h.effect == "material_text" else None,
        "human_file_retained": h.page.evaluate(
            "document.querySelector('#certificate').files[0]===window.originalHumanFile"
        ),
        "human_sha256": hashlib.sha256(file_bytes(h.page, "#certificate")).hexdigest(),
        "job": h.service.store.load()["jobs"][0],
    }


@pytest.fixture
def material_handoff(native_handoff):
    h = native_handoff
    try:
        yield h
    finally:
        try:
            h.extra_evidence["material_final"] = evidence(h)
        except Exception as error:
            h.extra_evidence["material_final_read_error"] = {
                "type": type(error).__name__,
                "message": str(error),
            }


def material_denial(result):
    """Read the material tool's exact not-sent refusal; other shapes use the MC05 reader."""
    data = result.get("structuredContent", {})
    refusal = data.get("refusal") or {}
    if (
        result.get("isError") is True
        and data.get("status") == "refused"
        and (refusal.get("detail") or {}).get("delivery") == "not_sent"
    ):
        return refusal.get("code")
    return native_denial(result)


def start_material(h):
    started = h.runner.start_native_assistance(h.reference, request_id="real-native-material")
    drive_until(
        h,
        started.run_id,
        lambda: any(row["kind"] == "material_ready" for row in read_peer(h.runtime)),
    )
    packet = next(row["packet"] for row in read_peer(h.runtime) if row["kind"] == "delivery")
    assert packet["assistance_ref"] == {
        key: value for key, value in h.reference.items() if key != "backend_authority"
    }
    assert "file_path" not in json.dumps(packet)
    assert h.service.store.load()["jobs"][0]["intent"] is None
    return started


def release_material(h):
    (h.runtime / "release-material").write_text("one original material request\n")


def finished(h, run_id):
    drive_until(
        h,
        run_id,
        lambda: any(row["kind"] in {"completed", "failure"} for row in read_peer(h.runtime)),
    )
    rows = read_peer(h.runtime)
    assert not [row for row in rows if row["kind"] == "failure"], rows
    return next(row for row in rows if row["kind"] == "completed")


def no_other_effect(h):
    original_page_intact(h, inputs=0)
    assert h.page.locator("#human").input_value() == "Keep this human note"
    assert h.page.evaluate(
        "document.querySelector('#certificate').files[0]===window.originalHumanFile"
    )
    assert file_bytes(h.page, "#certificate") == PDF.read_bytes() + b"\n% human attachment\n"
    preparation = h.extra_evidence["material_preparation"]
    if h.effect != "material_text":
        assert (
            h.page.locator("#certificate").evaluate("e=>e.files[0].name")
            == (preparation["material"]["filename"])
        )
    assert h.service.store.cover_letter_client.calls == preparation["compile_calls"]
    assert (
        h.service.store.material_inputs(h.service.store.load()["jobs"][0])
        == preparation["fixed_inputs"]
    )


def original_call(h):
    journal = h.service.store.load()["jobs"][0]["native_handoff_runs"][-1]
    calls = [
        call
        for call in journal["events"][-1]["receipt"]["calls"]
        if call["tool"] == "browser_deliver_material"
    ]
    assert len(calls) == 1, journal
    return journal, calls[0]


@pytest.mark.parametrize(
    "native_handoff", [case("material_text"), case("material_file")], indirect=True
)
def test_native_bound_material_is_read_back_on_original_page(material_handoff):
    h = material_handoff
    started = start_material(h)
    release_material(h)
    result = finished(h, started.run_id)
    assert result["results"][0]["structuredContent"]["effect"] == "confirmed"
    drive_until(
        h,
        started.run_id,
        lambda: any(
            row.get("action") == "action_result"
            and row.get("result") == "verified"
            and row.get("intent", {}).get("native_material")
            for row in h.service.store.load()["jobs"][0]["observations"]
        ),
    )
    job = h.service.store.load()["jobs"][0]
    journal, call = original_call(h)
    completed = [
        row["intent"]
        for row in job["observations"]
        if row.get("action") == "action_result"
        and row.get("result") == "verified"
        and row.get("intent", {}).get("native_material")
    ]
    assert len(completed) == 1
    intent = completed[0]
    assert job["intent"] is None and call["status"] == "observed"
    assert intent["native_material"]["call_id"] == call["call_id"]
    assert intent["attempt_id"] == call["material_resolution"]["resolution_id"]
    prepared = h.extra_evidence["material_preparation"]["material"]
    assert intent["material_id"] == prepared["id"]
    assert call["material_readback"]["sha256"] == intent["sha256"]
    # One insertText dispatches an input event per text segment and line break.
    text = prepared.get("text") or ""
    one_delivery = len([part for part in text.split("\n") if part]) + text.count("\n")
    assert h.page.evaluate("window.materialInputEvents") == (
        one_delivery if h.effect == "material_text" else 1
    )
    if h.effect == "material_text":
        assert h.page.locator("#letter").input_value() == prepared["text"]
        assert h.page.locator("#alternative").evaluate("e=>e.files.length") == 0
        assert h.extra_evidence["material_preparation"]["compile_calls"] == 0
    else:
        raw = file_bytes(h.page, "#letter")
        assert raw == PDF.read_bytes()
        assert hashlib.sha256(raw).hexdigest() == prepared["sha256"] == PDF_SHA
        assert h.page.locator("#letter").evaluate("e=>e.files.length") == 1
        assert h.extra_evidence["material_preparation"]["compile_calls"] == 1
    h.extra_evidence["material_confirmed"] = {
        "journal": journal,
        "intent": intent,
        "effect": evidence(h),
    }
    stopped_native(h, started.run_id)
    no_other_effect(h)


@pytest.mark.parametrize(
    "native_handoff", [case("material_corrupt"), case("material_wrong_field")], indirect=True
)
def test_native_bound_material_refuses_changed_file_or_wrong_field(material_handoff):
    h = material_handoff
    started = start_material(h)
    if h.effect == "material_corrupt":
        path = Path(h.extra_evidence["material_preparation"]["material"]["file_path"])
        assert path.resolve().is_relative_to(h.service.store.root.resolve())
        assert not path.is_symlink()
        path.write_bytes(b"Corrupted synthetic PDF after token capture\n")
    release_material(h)
    result = finished(h, started.run_id)
    assert material_denial(result["results"][0]) == "handoff_host_did_not_authorize"
    stopped_native(h, started.run_id)
    _, call = original_call(h)
    assert call["status"] == "not_sent"
    assert h.page.evaluate("[window.materialInputEvents,window.materialChangeEvents]") == [0, 0]
    assert file_bytes(h.page, "#letter") == b""
    assert h.service.store.load()["jobs"][0]["intent"] is None
    no_other_effect(h)


@pytest.mark.parametrize("native_handoff", [case("material_unknown")], indirect=True)
def test_native_file_readback_unknown_never_replays_original_attempt(material_handoff):
    h = material_handoff
    started = start_material(h)
    release_material(h)
    result = finished(h, started.run_id)
    first, cached, retry = result["results"]
    assert first == cached
    assert first["structuredContent"]["effect"] == "unverifiable"
    # File input uses the DOM route; the uncertain outcome is the effect, not a typing mode.
    assert first["structuredContent"]["delivery"]["mode"] == "not_applicable"
    assert material_denial(retry) == "handoff_native_effect_unresolved"
    requests = [
        row["request"]
        for row in read_peer(h.runtime)
        if row["kind"] == "native_sent"
        and row["request"].get("params", {}).get("name") == "browser_deliver_material"
    ]
    assert len(requests) == 3 and requests[0] == requests[1]
    assert requests[2]["id"] != requests[0]["id"]
    assert requests[2]["params"]["arguments"]["ref"] == result["fresh_ref"]
    journal, call = original_call(h)
    assert call["status"] == "unknown" and journal["semantic_unknown"] is True
    intent = deepcopy(h.service.store.load()["jobs"][0]["intent"])
    assert intent["native_material"]["call_id"] == call["call_id"]
    assert intent["attempt_id"] == call["material_resolution"]["resolution_id"]
    assert h.page.evaluate("window.materialInputEvents") == 1
    assert file_bytes(h.page, "#letter") == b""
    assert (
        bytes(
            h.page.evaluate(
                "async()=>Array.from(new Uint8Array("
                "await window.originalMaterialFile.arrayBuffer()))"
            )
        )
        == PDF.read_bytes()
    )
    stopped_native(h, started.run_id)
    assert h.service.store.load()["jobs"][0]["intent"] == intent
    before = h.service.store.path.read_bytes()
    with pytest.raises(PortalDataError):
        h.runner.start_native_assistance(h.reference, request_id="forbidden-material-replay")
    assert h.service.store.path.read_bytes() == before
    no_other_effect(h)


@pytest.mark.parametrize("native_handoff", [case("material_pending")], indirect=True)
def test_native_invalid_material_destination_stays_unknown_and_blocks_next_type(material_handoff):
    """Native readback requires destination validity, so an invalid field is never confirmed."""
    h = material_handoff
    started = start_material(h)
    release_material(h)
    result = finished(h, started.run_id)
    assert result["results"][0]["structuredContent"]["effect"] == "unverifiable"
    assert material_denial(result["results"][1]) == "handoff_native_effect_unresolved"
    job = h.service.store.load()["jobs"][0]
    journal, call = original_call(h)
    assert call["status"] == "unknown" and "material_readback" not in call
    intent = deepcopy(job["intent"])
    assert intent["native_material"]["call_id"] == call["call_id"]
    assert intent["attempt_id"] == call["material_resolution"]["resolution_id"]
    receipt_calls = journal["events"][-1]["receipt"]["calls"]
    assert not [row for row in receipt_calls if row["tool"] == "browser_type"]
    assert h.page.evaluate("window.nativeInputEvents") == 0
    assert h.page.locator("#letter").evaluate("e=>e.validity.valid") is False
    assert file_bytes(h.page, "#letter") == PDF.read_bytes()
    assert h.page.evaluate("window.materialInputEvents") == 1
    stopped_native(h, started.run_id)
    assert h.service.store.load()["jobs"][0]["intent"] == intent
    no_other_effect(h)


@pytest.mark.parametrize("native_handoff", [case("material_stop")], indirect=True)
def test_native_material_stop_revokes_during_original_file_handler(material_handoff):
    h = material_handoff
    started = start_material(h)
    release_material(h)
    prefix, end_prefix = "material-handler-start:", "material-handler-end:"
    drive_until(
        h, started.run_id, lambda: any(row["text"].startswith(prefix) for row in h.console_events)
    )
    stop_wall = time.time()
    h.extra_evidence["material_stop_started_wall"] = stop_wall
    stopped = stopped_native(h, started.run_id)
    completed_wall = time.time()
    h.extra_evidence["material_stop_completed_wall"] = completed_wall
    drive_until(
        h,
        started.run_id,
        lambda: any(row["text"].startswith(end_prefix) for row in h.console_events),
        timeout=15,
    )
    start = next(
        int(row["text"][len(prefix) :])
        for row in h.console_events
        if row["text"].startswith(prefix)
    )
    end = next(
        int(row["text"][len(end_prefix) :])
        for row in h.console_events
        if row["text"].startswith(end_prefix)
    )
    assert start <= stop_wall * 1000 < end <= completed_wall * 1000
    journal, call = original_call(h)
    receipts = [
        event["receipt"]
        for event in journal["events"]
        if (event.get("receipt") or {}).get("revoked") is True
        and event["receipt"]["active_calls"] > 0
    ]
    assert any(
        row["call_id"] == call["call_id"] and row["status"] == "in_flight"
        for receipt in receipts
        for row in receipt["calls"]
    )
    assert stopped.native_handoff["active_calls"] == 0
    assert call["status"] == "unknown" and journal["semantic_unknown"] is True
    assert h.page.evaluate("window.materialInputEvents") == 1
    assert file_bytes(h.page, "#letter") == PDF.read_bytes()
    intent = h.service.store.load()["jobs"][0]["intent"]
    assert intent["native_material"]["call_id"] == call["call_id"]
    h.extra_evidence["material_stop_receipts"] = receipts
    h.extra_evidence["material_stop_progress"] = asdict(stopped)
    no_other_effect(h)


@pytest.mark.skip(
    reason="Ashby early upload after native file delivery is map fog: Chrome hides disk-backed "
    "file bytes from the intercepted body, so the Worker guard blocks it (fail closed)."
)
@pytest.mark.parametrize("native_handoff", [case("material_upload_lost")], indirect=True)
def test_native_local_file_observed_does_not_replay_upload_after_receiver_loses_reply(
    material_handoff,
):
    h = material_handoff
    receiver = h.runner.native_material_receiver
    started = start_material(h)
    release_material(h)
    drive_until(h, started.run_id, lambda: (receiver.root / "upload-disconnected.json").exists())
    uploaded = json.loads((receiver.root / "upload-disconnected.json").read_text())
    assert (
        uploaded["native_local_result_before_disconnect"]["result"]["structuredContent"]["effect"]
        == "confirmed"
    )
    assert (receiver.root / "received.pdf").read_bytes() == PDF.read_bytes()
    assert uploaded["file_sha256"] == PDF_SHA
    assert uploaded["file_size"] == len(PDF.read_bytes())
    drive_until(
        h, started.run_id, lambda: h.runner.blocked_pages.get(h.page) == "draft_result_unknown"
    )
    progress = h.adapter.progress(started.run_id)
    h.extra_evidence["upload_loss_progress"] = asdict(progress)
    job = h.service.store.load()["jobs"][0]
    intent = deepcopy(job["intent"])
    assert intent == uploaded["intent"]
    journal, call = original_call(h)
    assert call["status"] == "observed"
    assert intent["native_material"]["call_id"] == call["call_id"]
    assert intent["attempt_id"] == call["material_resolution"]["resolution_id"]
    assert file_bytes(h.page, "#letter") == PDF.read_bytes()
    assert h.page.evaluate("window.materialInputEvents") == 1
    assert h.page.evaluate(
        "document.querySelector('#letter').files[0]===window.originalMaterialFile"
    )
    question = next(
        row for row in job["form_state"]["snapshot"]["fields"] if row["id"] == intent["field_id"]
    )
    material = {
        "id": intent["material_id"],
        "sha256": intent["sha256"],
        "filename": intent["filename"],
    }
    assert h.runner.drafts[h.page].native_material_verified(intent, question, material) is False
    assert not any(
        row.get("action") == "action_result" and row.get("intent") == intent
        for row in job["observations"]
    )
    assert any(
        event.get("intent") == intent
        and event.get("stage")
        in {
            "request_response_rejected",
            "requestfailed",
        }
        for event in [*job["observations"], *h.runner.transports]
    )
    for _ in range(3):
        h.adapter.progress(started.run_id)
        h.page.wait_for_timeout(25)
    stopped_native(h, started.run_id)
    assert h.service.store.load()["jobs"][0]["intent"] == intent
    before = h.service.store.path.read_bytes()
    with pytest.raises(PortalDataError) as refused:
        h.runner.start_native_assistance(h.reference, request_id="lost-upload-no-replay")
    h.extra_evidence["upload_loss_new_handoff_refusal"] = refused.value.code
    assert h.service.store.path.read_bytes() == before
    paths = [event["path"] for event in receiver.events]
    assert paths.count("/graphql?op=ApiJobPosting") == 1
    assert paths.count("/graphql?op=ApiCreateFileUploadHandle") == 1
    assert paths.count("/upload") == 1
    assert "/graphql?op=ApiSetFormValueToFile" not in paths
    assert not any(event.get("unexpected_operation") for event in receiver.events)
    assert h.page.evaluate("window.materialUploadState") == "reply-lost"
    no_other_effect(h)
