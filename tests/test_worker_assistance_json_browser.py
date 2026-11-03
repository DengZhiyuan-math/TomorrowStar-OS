"""Screenshot-free handoff context from one isolated loopback application Page."""

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

HTML = b"""<!doctype html><title>JSON original page</title>
<link rel="icon" href="data:,">
<form><label>Email <input id="email" name="email" value="human@example.invalid"></label>
<input id="country" name="country" role="combobox" aria-label="Country"
  value="Human choice" readonly aria-invalid="true">
<button type="button" id="custom-country" name="custom-country" role="combobox"
  aria-label="Custom country" aria-valuetext="Saved custom choice">Choose country</button>
<button type="button" id="picked-team" role="combobox" aria-label="Team">
  <span>Engineering</span></button>
<button type="button" id="open-team" role="combobox" aria-label="Open team"
  aria-controls="team-list">Engineering</button>
<ul id="team-list" role="listbox"><li role="option" aria-selected="false">Engineering</li></ul>
<button type="button" id="unpicked-team" role="combobox" aria-label="Other team">
  <span class="select__placeholder">Bitte ausw&auml;hlen</span></button>
<div id="div-team" role="combobox" aria-label="Div team">Research</div>
<label>Required <input id="required" name="required" required></label>
<input id="password" type="password" value="synthetic-secret">
<div class="file-upload__filename">synthetic-resume.pdf</div><button>Submit</button></form>
<script>window.__tomorrowstarMaterialDocument=crypto.randomUUID();</script>"""


@pytest.fixture
def json_page(retained_assistance_page):
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
    origin = f"http://127.0.0.1:{server.server_port}"
    try:
        with sync_playwright() as playwright:
            options = (
                {} if Path(playwright.chromium.executable_path).is_file() else {"channel": "chrome"}
            )
            browser = playwright.chromium.launch(headless=True, **options)
            try:
                context = browser.new_context(service_workers="block")
                context.route(
                    "**/*",
                    lambda route: (
                        route.continue_()
                        if route.request.url.startswith(origin + "/")
                        and route.request.method == "GET"
                        else route.abort()
                    ),
                )
                page = context.new_page()
                page.goto(origin + "/application")
                token = page.evaluate("window.__tomorrowstarMaterialDocument")
                state = service.store.load()
                state["jobs"][0]["form_state"]["binding"].update(
                    step=page.url, document_token=token
                )
                state["runtime"]["observed_at"] = time.time()
                state["jobs"][0]["page_observation"]["at"] = time.time()
                service.store.save(state)
                service.request(
                    "request-assistance",
                    {
                        "application_id": identifier,
                        "binding": service.assistance_context(identifier)["binding"],
                        "request_id": "json-request",
                    },
                )
                reference = service.assistance_context(identifier)["assistance_ref"]
                service.request(
                    "claim-assistance",
                    {
                        "application_id": identifier,
                        "assistance_ref": reference,
                        "request_id": "json-claim",
                    },
                )
                runner = ApplicationRunner(service.store, None)
                runner.context = context
                runner.pages[identifier] = page
                runner.page_ids[page] = reference["binding"]["page_id"]
                yield service, runner, page, reference, requests
            finally:
                browser.close()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_json_context_reads_dom_roles_validation_and_human_values_without_image(
    json_page, monkeypatch
):
    service, runner, page, reference, requests = json_page
    page.evaluate("""() => {
        window.readEvents=[];window.readMutations=[];
        for(const event of ['input','change','focus','submit'])
            document.addEventListener(event,()=>window.readEvents.push(event),true);
        new MutationObserver(rows=>window.readMutations.push(...rows.map(x=>x.type)))
            .observe(document,{subtree:true,childList:true,attributes:true,characterData:true});
        const native=Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').get;
        Object.defineProperty(document.querySelector('#email'),'value',{get(){
            window.readEvents.push('page_getter');return native.call(this);
        }});
    }""")
    before = service.store.path.read_bytes()

    def no_screenshot(**kwargs):
        pytest.fail("JSON handoff requested a screenshot")

    monkeypatch.setattr(page, "screenshot", no_screenshot)
    monkeypatch.setattr(page._impl_obj, "screenshot", no_screenshot)
    result = runner.observe_assistance_context(reference)
    fields = {field["id"]: field for field in result["data"]["fields"]}
    assert fields["email"]["value"] == "human@example.invalid"
    assert fields["country"]["value"] == "Human choice"
    assert fields["custom-country"]["locator_hint"]["role"] == "combobox"
    assert fields["custom-country"]["locator_hint"]["label"] == "Custom country"
    assert fields["custom-country"]["value"] == "Saved custom choice"
    # A custom combobox's shown choice is its value; a placeholder or an
    # unselected listbox is empty.
    assert fields["picked-team"]["value"] == "Engineering"
    assert fields["open-team"]["value"] == ""
    assert fields["unpicked-team"]["value"] == ""
    assert fields["div-team"]["value"] == "Research"
    assert fields["country"]["locator_hint"] == {
        "id": "country",
        "name": "country",
        "role": "combobox",
        "label": "Country",
    }
    errors = {error["field_hint"]["id"] for error in result["data"]["validation_errors"]}
    assert errors == {"country", "required"}
    assert fields["password"]["value"] == ""
    assert "synthetic-secret" not in str(result)
    assert result["data"]["attachments"] == [
        {"name": "synthetic-resume.pdf", "source": "visible_filename"}
    ]
    assert result["binding"] == reference["binding"]
    assert result["document"]["loader_id"]
    assert result["data"]["url"] == page.url
    assert "screenshot" not in result and "image_url" not in result
    assert page.evaluate("[window.readEvents,window.readMutations]") == [[], []]
    assert service.store.path.read_bytes() == before
    assert runner.context.pages == [page]
    assert all(method == "GET" for method, _ in requests)


@pytest.mark.parametrize("changed", ["reload", "document_accessor"])
def test_json_context_rejects_replacement_document_without_screenshot(json_page, changed):
    service, runner, page, reference, _ = json_page
    if changed == "reload":
        page.reload()
    else:
        page.evaluate("""() => {
            window.documentGetterCalls=0;
            const token=window.__tomorrowstarMaterialDocument;
            Object.defineProperty(window,'__tomorrowstarMaterialDocument',{get(){
                window.documentGetterCalls++;return token;
            }});
        }""")
    before = service.store.path.read_bytes()
    with pytest.raises(PortalDataError, match="文档"):
        runner.observe_assistance_context(reference)
    if changed == "document_accessor":
        assert page.evaluate("window.documentGetterCalls") == 0
    assert service.store.path.read_bytes() == before
    assert runner.context.pages == [page]
