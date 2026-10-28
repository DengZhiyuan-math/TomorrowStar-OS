"""Read-only T03 checks on isolated loopback pages, never a real ATS."""

import base64
import fcntl
import os
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest
from playwright.sync_api import sync_playwright
from test_single_application_worker import single_worker as single_worker
from test_worker_codex_assistance import retained_assistance_page as retained_assistance_page

from career_evidence_graph.application_worker_browser import ApplicationRunner
from career_evidence_graph.career_portal_data import PortalDataError

pytestmark = pytest.mark.worker_browser

HTML = b"""<!doctype html><title>T03 owned fixture</title>
<form><label>Email <input id="email" value="synthetic@example.invalid"></label>
<input id="password" type="password" value="fixture-password"><button>Submit</button></form>
<script>window.__tomorrowstarMaterialDocument=crypto.randomUUID();</script>"""


@pytest.mark.parametrize(
    "change", [None, "same_url_reload", "document_getter", "fragment_recovery"]
)
def test_real_cdp_observes_original_handle_without_page_mutation(retained_assistance_page, change):
    service, identifier = retained_assistance_page
    requests = []

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            requests.append(("GET", self.path))
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.send_header("Content-Length", str(len(HTML)))
            self.end_headers()
            self.wfile.write(HTML)

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    url = f"http://127.0.0.1:{server.server_port}/owned"
    if change == "fragment_recovery":
        url += "#application"
    try:
        with sync_playwright() as playwright:
            options = (
                {} if Path(playwright.chromium.executable_path).is_file() else {"channel": "chrome"}
            )
            browser = playwright.chromium.launch(headless=True, **options)
            try:
                context = browser.new_context()
                context.route(
                    "**/*",
                    lambda route: (
                        route.continue_()
                        if route.request.url.startswith(f"http://127.0.0.1:{server.server_port}/")
                        and route.request.method == "GET"
                        else route.abort()
                    ),
                )
                page = context.new_page()
                page.goto(url)
                token = page.evaluate("() => window.__tomorrowstarMaterialDocument")
                state = service.store.load()
                state["jobs"][0]["form_state"]["binding"].update(step=url, document_token=token)
                state["runtime"]["observed_at"] = time.time()
                state["jobs"][0]["page_observation"]["at"] = time.time()
                service.store.save(state)
                service.request(
                    "request-assistance",
                    {
                        "application_id": identifier,
                        "binding": service.assistance_context(identifier)["binding"],
                        "request_id": "browser-read",
                    },
                )
                reference = service.assistance_context(identifier)["assistance_ref"]
                service.request(
                    "claim-assistance",
                    {
                        "application_id": identifier,
                        "assistance_ref": reference,
                        "request_id": "browser-claim",
                    },
                )
                runner = ApplicationRunner(service.store, None)
                runner.context = context
                runner.pages[identifier] = page
                runner.page_ids[page] = reference["binding"]["page_id"]
                if change == "same_url_reload":
                    page.reload()
                page.evaluate("""() => {
                  window.readEvents=[];window.readMutations=[];
                  for(const event of ['input','change','focus','submit'])
                    document.addEventListener(event,()=>window.readEvents.push(event),true);
                  new MutationObserver(rows=>window.readMutations.push(...rows.map(x=>x.type)))
                    .observe(document,{subtree:true,childList:true,attributes:true,characterData:true});
                  const native=Object.getOwnPropertyDescriptor(
                    HTMLInputElement.prototype,'value').get;
                  Object.defineProperty(document.querySelector('#email'),'value',{get(){
                    window.readEvents.push('page_value_getter');
                    document.querySelector('form').setAttribute('data-read-side-effect','yes');
                    return native.call(this);
                  }});
                }""")
                if change == "document_getter":
                    page.evaluate("""() => {
                      const value=window.__tomorrowstarMaterialDocument;
                      Object.defineProperty(window,'__tomorrowstarMaterialDocument',{get(){
                        window.readEvents.push('document_getter');return value;
                      }});
                    }""")
                before = service.store.path.read_bytes()
                if change in {None, "fragment_recovery"}:
                    result = runner.observe_assistance_page(reference)
                    assert result["data"]["title"] == "T03 owned fixture"
                    fields = {row["id"]: row for row in result["data"]["fields"]}
                    assert fields["email"]["value"] == "synthetic@example.invalid"
                    assert fields["password"]["value"] == ""
                    assert "fixture-password" not in str(result["data"])
                    assert base64.b64decode(result["screenshot"]["base64"]).startswith(
                        b"\x89PNG\r\n\x1a\n"
                    )
                else:
                    with pytest.raises(PortalDataError):
                        runner.observe_assistance_page(reference)
                assert service.store.path.read_bytes() == before
                assert page.evaluate("() => [window.readEvents,window.readMutations]") == [[], []]
                assert runner.pages[identifier] is page and context.pages == [page]
                assert all(method == "GET" for method, _ in requests)
                if change == "fragment_recovery":
                    descriptor = os.open(
                        service.store.root / ".worker.lock", os.O_CREAT | os.O_RDWR, 0o600
                    )
                    try:
                        fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
                        service.store.worker_lock_descriptor = descriptor
                        runner.tick(control_only=True)
                        state = service.store.load()
                        recovery = service.suspend_backend(
                            pipeline_id="fragment-recovery",
                            controller=state["controller"],
                            batch_id=state["batch_id"],
                            application_id=identifier,
                        )
                        stop = service.store.load()["jobs"][0]["assistance"]["stop"]
                        service.record_assistance_stop(
                            identifier,
                            reference,
                            {
                                "tools_revoked": True,
                                "local_tools_drained": True,
                                "process_stopped": True,
                                "native_turn_id": None,
                                "native_turn_status": "idle",
                                "stop_status": "stopped",
                            },
                            request_id=stop["request_id"],
                        )
                        service.recover_backend(recovery["request_id"], "fragment-recovery")
                        state = service.store.load()
                        runner.commands(state)
                        runner.persist(state)
                        runner.service_backend_recovery()
                        after = service.store.load()
                        proof = after["backend_recovery"]["page_verification"]
                        assert after["backend_recovery"]["page_verified"] is True
                        assert proof["document"]["url"] == url.split("#", 1)[0]
                        assert proof["data"]["url"] == url
                        assert after["control"] == "paused"
                        assert after["jobs"][0]["assistance"]["active_writer"] == "codex"
                        assert context.pages == [page]
                        assert page.evaluate("() => [window.readEvents,window.readMutations]") == [
                            [],
                            [],
                        ]
                    finally:
                        os.close(descriptor)
            finally:
                browser.close()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
