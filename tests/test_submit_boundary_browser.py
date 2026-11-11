"""Focused exit-contract proofs against the existing loopback ATS receiver.

The normal worker drives filling/upload. Test-originated page scripts below are
adversarial inputs, not a production Next driver or automatic Submit API.
"""

from __future__ import annotations

import base64
import json
import re
from contextlib import contextmanager
from copy import deepcopy
from types import SimpleNamespace
from urllib.parse import urlencode

import pytest
from playwright.sync_api import sync_playwright
from test_ashby_drafts import QUERIES, endpoint
from test_ashby_drafts import form as ashby_form
from test_ashby_drafts import setup_service as ashby_service
from test_hosted_ats import LEVER, PDF, live_service, prepare
from test_worker_recovery_regressions import UPLOAD_HTML
from worker_preview_support import advance_until

from career_evidence_graph import hosted_ats
from career_evidence_graph.application_worker import WorkerService, start_run
from career_evidence_graph.application_worker_browser import ApplicationRunner
from career_evidence_graph.application_worker_fixtures import create_fixture_server
from career_evidence_graph.ashby_drafts import DraftSession
from career_evidence_graph.ats_forms import FORMS
from career_evidence_graph.career_portal_data import ApplicationStore, PortalDataError

pytestmark = pytest.mark.worker_browser

COUNTERS = """(() => {
  window.finalChannels = {button:0, enter:0, requestSubmit:0, formSubmit:0};
  document.addEventListener('click', event => {
    if(event.target.closest('button,input')?.type === 'submit') finalChannels.button++;
  }, true);
  document.addEventListener('keydown', event => {
    if(event.key === 'Enter' && event.target.closest('form')) finalChannels.enter++;
  }, true);
  const requestSubmit = HTMLFormElement.prototype.requestSubmit;
  HTMLFormElement.prototype.requestSubmit = function(...args) {
    finalChannels.requestSubmit++; return requestSubmit.apply(this,args);
  };
  const submit = HTMLFormElement.prototype.submit;
  HTMLFormElement.prototype.submit = function(...args) {
    finalChannels.formSubmit++; return submit.apply(this,args);
  };
  document.addEventListener('DOMContentLoaded', () => {
    const next = document.createElement('button');
    next.type='button';next.id='boundary-next';next.textContent='Next';
    next.onclick=async()=>{
      const response=await fetch(location.href,{headers:{'X-Synthetic-Next':'1'}});
      next.dataset.complete=String(response.ok);
    };
    document.querySelector('form')?.append(next);
  });
})();"""


@contextmanager
def receiver_flow(
    tmp_path, monkeypatch, *, upload_redirect=0, get_redirect=0, upload_case="", draft_redirect=0
):
    monkeypatch.setenv("PLAYWRIGHT_BROWSERS_PATH", "0")
    apps, runtime = tmp_path / "applications", tmp_path / "worker"
    apps.mkdir()
    runtime.mkdir()
    applications = ApplicationStore(apps)
    app = applications.create_application(
        {
            "company": "Synthetic",
            "role_title": "Engineer",
            "status": "drafting",
            "url": LEVER,
        }
    )
    server = create_fixture_server([app], runtime)
    origin = f"http://127.0.0.1:{server.server_port}"
    identifier, form = app["id"], FORMS["lever"]
    receiver = SimpleNamespace(next_reads=0, initial_reads=0, drafts=[])
    original_handler = server.RequestHandlerClass

    class Handler(original_handler):
        def end_headers(self):
            self.send_header("Access-Control-Allow-Origin", "*")
            super().end_headers()

        def do_GET(self):
            if self.path == form.page_path(identifier):
                receiver.initial_reads += 1
                if get_redirect:
                    self.send_response(get_redirect)
                    self.send_header(
                        "Location",
                        form.submit_path(identifier) + "?op=ApiSubmitSingleApplicationFormAction",
                    )
                    self.send_header("Content-Length", "0")
                    self.end_headers()
                    return
            if self.path.startswith(form.submit_path(identifier) + "?"):
                server.fixture_events["submissions"].append({"id": identifier, "method": "GET"})
                (runtime / "fixture-events.json").write_text(json.dumps(server.fixture_events))
                self.send(200, b"Synthetic final GET received", "text/plain")
                return
            if self.headers.get("X-Synthetic-Next") == "1":
                receiver.next_reads += 1
            super().do_GET()

        def do_POST(self):
            if self.path != "/draft/" + identifier:
                super().do_POST()
                return
            payload = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            if any(
                name in payload["query"]
                for name in (
                    "submitApplication",
                    "submitSingleApplicationFormAction",
                )
            ):
                server.fixture_events["submissions"].append({"id": identifier, "method": "GraphQL"})
                (runtime / "fixture-events.json").write_text(json.dumps(server.fixture_events))
            # This receiver's fixed direct-argument schema resolves literal values
            # independently of variables, so a checked-but-unused variable cannot
            # hide a different actual write from the assertions.
            call = re.search(r"\bsetFormValue\s*\(([^)]*)\)", payload["query"])
            assert call
            arguments = dict(re.findall(r'(\w+)\s*:\s*(\$\w+|"(?:\\.|[^"\\])*")', call[1]))
            effective = {
                key: payload["variables"][value[1:]] if value.startswith("$") else json.loads(value)
                for key, value in arguments.items()
            }
            receiver.drafts.append(effective)
            if draft_redirect:
                self.send_response(draft_redirect)
                self.send_header("Location", origin + form.submit_path(identifier))
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            result = {
                "data": {
                    "setFormValue": ashby_form(
                        {
                            effective["path"]: {"value": effective["value"]},
                        }
                    )
                }
            }
            self.send(200, json.dumps(result).encode(), "application/json")

        def send(self, status, raw, mime):
            if self.path == form.upload_path(identifier) and upload_case:
                receiver.upload_intent = deepcopy(service.store.load()["jobs"][0]["intent"])
                if upload_case == "lost":
                    self.close_connection = True
                    return
                assert upload_case == "late_after_recheck"
                service.request(
                    "resolve-action",
                    {
                        "application_id": identifier,
                        "intent_ref": receiver.upload_intent["attempt_id"],
                        "conclusion": "not_applied",
                        "source": "Synthetic decision before the withheld receiver response",
                    },
                )
                service.request("recheck", {"application_id": identifier, "acknowledge": True})
            if upload_redirect and self.path == form.upload_path(identifier):
                self.send_response(upload_redirect)
                self.send_header("Location", form.submit_path(identifier))
                self.send_header("Content-Length", "0")
                self.end_headers()
            else:
                super().send(status, raw, mime)

    server.RequestHandlerClass = Handler
    service = WorkerService(applications, runtime, fixture_origin=origin)
    monkeypatch.setattr(service, "spawn", lambda: None)
    service.request(
        "prepare",
        {
            "jobs": [
                {
                    "application_id": identifier,
                    "revision": app["revision"],
                    "country": "CHE",
                    "filename": "resume.pdf",
                    "file_base64": base64.b64encode(PDF).decode(),
                }
            ]
        },
    )
    for question, value, scope in (
        ("Full name", "Synthetic Person", {}),
        ("Email address", "synthetic@example.invalid", {}),
        ("Will you now or in the future require visa sponsorship?", "No", {"country": "CHE"}),
    ):
        service.store.answers.put_answer(
            {
                "question": question,
                "value": value,
                "scope": scope,
                "state": "confirmed",
            }
        )
    service.request("resume", {"controller": "synthetic-boundary-controller"})
    start_run(service.store)
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True, channel="chromium")
            try:
                context = browser.new_context()
                # All browser traffic is restricted to this disposable loopback receiver.
                context.route(
                    "**/*",
                    lambda route: (
                        route.continue_()
                        if route.request.url.startswith(origin + "/")
                        else route.abort("blockedbyclient")
                    ),
                )
                context.add_init_script(COUNTERS)
                runner = ApplicationRunner(service.store, context, origin)
                receiver.service, receiver.runner = service, runner
                receiver.browser = browser
                receiver.server, receiver.origin = server, origin
                receiver.identifier, receiver.form = identifier, form
                receiver.events = lambda: json.loads((runtime / "fixture-events.json").read_text())
                yield receiver
            finally:
                browser.close()
    finally:
        server.shutdown()
        server.server_close()


def reach_review(flow):
    current = advance_until(
        flow.service,
        flow.runner,
        lambda job: job["status"] == "ready_for_review",
        application_id=flow.identifier,
    )
    return current, flow.runner.pages[flow.identifier]


def test_supported_worker_and_original_page_manual_submit_have_separate_receiver_counts(
    tmp_path, monkeypatch
):
    with receiver_flow(tmp_path, monkeypatch) as flow:
        current, page = reach_review(flow)
        original_document = page.locator("form").element_handle()
        before = flow.service.store.path.read_bytes()
        for intent in (
            {"action": "click", "selector": "button[type=submit]"},
            {"action": "press", "key": "Enter"},
            {"action": "requestSubmit"},
            {"action": "form.submit"},
            {"action": "http"},
            {"action": "graphql"},
        ):
            with pytest.raises(PortalDataError) as error:
                flow.runner.authorize(current, flow.service.store.load()["batch_id"], intent)
            assert error.value.code == "unsupported_action"
        assert flow.service.store.path.read_bytes() == before
        assert page.evaluate("window.finalChannels") == {
            "button": 0,
            "enter": 0,
            "requestSubmit": 0,
            "formSubmit": 0,
        }
        assert len(flow.events()["uploads"]) == 1
        assert flow.events()["uploads"][0]["sha256"] == current["file_sha256"]
        assert flow.events()["submissions"] == []

        # Exit contract only: a synthetic client Next may perform a non-final GET.
        page.locator("#boundary-next").click()
        page.wait_for_function("document.querySelector('#boundary-next').dataset.complete==='true'")
        assert flow.next_reads == 1
        assert flow.events()["submissions"] == []
        flow.service.request("review", {"application_id": flow.identifier})
        flow.runner.tick()
        handed_off = flow.service.store.load()["jobs"][0]
        assert handed_off["handed_off"] and handed_off["handoff"]["status"] == "complete"
        assert flow.runner.pages[flow.identifier] is page
        assert page.locator("form").evaluate("(form, original)=>form===original", original_document)
        # Human editing starts after the explicit handoff of the original page.
        page.locator("#name").fill("Synthetic manual edit")
        assert page.locator("#name").input_value() == "Synthetic manual edit"
        assert page.locator("#resume").evaluate("e=>e.files[0].name") == "resume.pdf"
        page.get_by_role("button", name="Submit application", exact=True).click()
        page.wait_for_function(
            "document.body.textContent.includes('Synthetic human submission received')"
        )
        assert len(flow.events()["submissions"]) == 1
        assert len(flow.events()["uploads"]) == 1


@pytest.mark.parametrize("status", [307, 308])
def test_upload_redirect_cannot_reach_final_receiver(tmp_path, monkeypatch, status):
    with receiver_flow(tmp_path, monkeypatch, upload_redirect=status) as flow:
        for _ in range(4):
            flow.service.request("heartbeat", {"controller": "synthetic-boundary-controller"})
            flow.runner.tick()
        current = flow.service.store.load()["jobs"][0]
        assert len(flow.events()["uploads"]) == 1
        assert flow.events()["submissions"] == []
        assert current["status"] == "needs_recheck"
        assert current["intent"]["action"] == "upload"


@pytest.mark.parametrize("status", [307, 308])
def test_live_resume_parse_redirect_cannot_reach_final_receiver(tmp_path, monkeypatch, status):
    with receiver_flow(tmp_path, monkeypatch, upload_redirect=status) as flow:
        live_root = tmp_path / "live"
        live_root.mkdir()
        service = live_service(live_root, monkeypatch)
        job = prepare(service)
        service.request("resume", {"controller": "synthetic-controller"})
        start_run(service.store)
        context = flow.browser.new_context()
        context.add_init_script("window.retryUploads=true")
        runner = ApplicationRunner(service.store, context)

        def intercept(route):
            request = route.request

            def fulfill(*, response):
                headers = dict(response.headers)
                if "location" in headers:
                    headers["location"] = flow.origin + flow.form.submit_path(flow.identifier)
                body = UPLOAD_HTML if request.method == "GET" else response.body()
                route.fulfill(status=response.status, body=body, headers=headers)

            def proceed():
                if request.method == "GET" and request.url == LEVER + "/apply":
                    route.fulfill(status=200, body=UPLOAD_HTML, content_type="text/html")
                elif request.url == "https://jobs.lever.co/parseResume":
                    fulfill(response=fetch(max_redirects=0, max_retries=0))
                elif request.url.startswith(flow.origin + "/"):
                    route.continue_()
                else:
                    route.abort("blockedbyclient")

            def fetch(**options):
                if request.method == "GET" and request.url == LEVER + "/apply":
                    path = flow.form.page_path(flow.identifier)
                else:
                    assert request.url == "https://jobs.lever.co/parseResume"
                    path = flow.form.upload_path(flow.identifier)
                return context.request.fetch(
                    flow.origin + path,
                    method=request.method,
                    headers=request.headers,
                    data=request.post_data_buffer,
                    **options,
                )

            runner._live_guard(
                SimpleNamespace(
                    request=request,
                    continue_=proceed,
                    abort=route.abort,
                    fetch=fetch,
                    fulfill=fulfill,
                )
            )

        context.route("**/*", intercept)
        for _ in range(4):
            service.request("heartbeat", {"controller": "synthetic-controller"})
            runner.tick()
        current = service.store.load()["jobs"][0]
        assert len(flow.events()["uploads"]) == 1
        assert flow.events()["submissions"] == []
        assert current["status"] == "needs_recheck"
        assert current["intent"]["action"] == "upload"
        assert current["intent"]["sha256"] == job["file_sha256"]
        assert not any(
            intent.get("attempt_id") == current["intent"]["attempt_id"]
            for intent in runner.verified_intents(current)
        )
        for _ in range(2):
            runner.tick()
        assert len(flow.events()["uploads"]) == 1
        assert flow.events()["submissions"] == []
        context.close()


@pytest.mark.parametrize("status", [307, 308])
def test_read_redirect_cannot_reach_final_get_receiver(tmp_path, monkeypatch, status):
    with receiver_flow(tmp_path, monkeypatch, get_redirect=status) as flow:
        for _ in range(3):
            flow.runner.tick()
        current = flow.service.store.load()["jobs"][0]
        assert flow.initial_reads == 1
        assert flow.events()["submissions"] == []
        assert flow.events()["uploads"] == []
        assert current["status"] == "needs_recheck"
        assert current["intent"]["action"] == "open"


@pytest.mark.parametrize(
    "channel",
    [
        "button",
        "enter",
        "requestSubmit",
        "form.submit",
        "http",
        "mixed_graphql",
        "get_graphql",
    ],
)
def test_page_script_cannot_bypass_final_network_boundary(tmp_path, monkeypatch, channel):
    with receiver_flow(tmp_path, monkeypatch) as flow:
        _, page = reach_review(flow)
        final = flow.origin + flow.form.submit_path(flow.identifier)
        mixed = "mutation Save { setFormValue { id } hidden:submitApplication { id } }"
        try:
            if channel == "button":
                page.get_by_role("button", name="Submit application", exact=True).click()
            elif channel == "enter":
                page.locator("#email").press("Enter")
            elif channel == "requestSubmit":
                page.evaluate("document.querySelector('form').requestSubmit()")
            elif channel == "form.submit":
                page.evaluate("document.querySelector('form').submit()")
            else:
                url = (
                    final + "?" + urlencode({"query": mixed}) if channel == "get_graphql" else final
                )
                page.evaluate(
                    """async ({url, channel, mixed}) => {
                  try {await fetch(url, {method:channel==='get_graphql'?'GET':'POST',
                    ...(channel==='get_graphql'?{}:{body:channel==='mixed_graphql'?
                      JSON.stringify({operationName:'ApiSetFormValue',query:mixed,variables:{}}):
                      'synthetic final body',headers:{'Content-Type':'application/json'}})});
                  } catch (_) {}
                }""",
                    {"url": url, "channel": channel, "mixed": mixed},
                )
        except Exception as error:
            # Native form navigation can report ERR_BLOCKED_BY_CLIENT to Playwright.
            assert "ERR_BLOCKED_BY_CLIENT" in str(error) or "interrupted" in str(error)
        page.wait_for_timeout(50)
        assert flow.events()["submissions"] == []
        assert len(flow.events()["uploads"]) == 1


@pytest.mark.parametrize("case", ["lost", "late_after_recheck"])
def test_unknown_or_late_upload_result_does_not_replay_at_receiver(tmp_path, monkeypatch, case):
    with receiver_flow(tmp_path, monkeypatch, upload_case=case) as flow:
        current = advance_until(
            flow.service,
            flow.runner,
            lambda job: (
                job["status"] == ("needs_recheck" if case == "lost" else "ready_for_review")
            ),
            application_id=flow.identifier,
        )
        original = flow.upload_intent
        assert original["attempt_id"] and original["sha256"] == current["file_sha256"]
        assert len(flow.events()["uploads"]) == 1
        assert flow.events()["submissions"] == []
        if case == "lost":
            assert current["status"] == "needs_recheck"
            assert current["intent"] == original
            page = flow.runner.pages[flow.identifier]
            page.evaluate("document.querySelector('#resume').dispatchEvent(new Event('change'))")
            page.wait_for_timeout(50)
            flow.runner.tick()
            assert flow.service.store.load()["jobs"][0]["intent"] == original
            assert len(flow.events()["uploads"]) == 1
        else:
            assert current["status"] == "ready_for_review"
            assert current["intent"] is None
            assert current["action_resolutions"][-1]["intent"] == original
            completions = [
                event
                for event in current["observations"]
                if event.get("action") == "action_result"
                and event.get("intent", {}).get("attempt_id") == original["attempt_id"]
            ]
            assert len(completions) == 1 and completions[0]["result"] == "verified"


@pytest.mark.parametrize(
    "case",
    [
        "known_draft",
        "literal_other_value",
        "mixed_final",
        "escaped_block_mixed_final",
        "save_redirect_307",
        "save_redirect_308",
    ],
)
def test_known_draft_reaches_receiver_but_changed_query_intent_does_not(
    tmp_path, monkeypatch, case
):
    redirect = int(case.rsplit("_", 1)[1]) if case.startswith("save_redirect_") else 0
    with receiver_flow(tmp_path, monkeypatch, draft_redirect=redirect) as flow:
        live_root = tmp_path / "draft"
        live_root.mkdir()
        service, _ = ashby_service(live_root, monkeypatch)
        start_run(service.store)
        job = service.store.load()["jobs"][0]
        context = flow.browser.new_context()
        runner = ApplicationRunner(service.store, context)
        page = context.new_page()
        runner.pages[job["application_id"]] = page
        runner.page_ids[page] = "synthetic-draft-receiver-page"
        draft = DraftSession(job)
        draft._form(ashby_form({}))
        runner.drafts[page] = draft
        query = QUERIES["ApiSetFormValue"]
        if case == "literal_other_value":
            query = query.replace("value: $value", 'value: "Different receiver value"')
            assert "Different receiver value" in query
        elif case == "mixed_final":
            query = query[:-1] + " hidden:submitApplication { id } }"
        elif case == "escaped_block_mixed_final":
            triple = '"' * 3
            query = (
                "mutation ApiSetFormValue { setFormValue(value: "
                + triple
                + "prefix "
                + chr(92)
                + triple
                + " suffix"
                + triple
                + ") { id } "
                + "submitSingleApplicationFormAction(value: "
                + triple
                + "end"
                + triple
                + ") { id } }"
            )
        payload = {
            "operationName": "ApiSetFormValue",
            "query": query,
            "variables": {
                "organizationHostedJobsPageName": "synthetic",
                "formRenderIdentifier": "render-one",
                "formDefinitionIdentifier": "definition-one",
                "path": "name",
                "value": "Synthetic Person",
            },
        }
        html = """<title>Synthetic careers</title><h1>Engineer</h1><form>
          <label>Name<input id='name' data-field-path='name' required></label>
          <label>Resume<input type='file' required></label></form><script>
          document.querySelector('#name').onblur=()=>fetch(ENDPOINT,{method:'POST',
            headers:{'Content-Type':'application/json'},body:JSON.stringify(PAYLOAD)})
            .then(async response=>{await response.json();window.draftResponse=response.status})
            .catch(()=>{window.draftResponse='failed'});
        </script>""".replace("ENDPOINT", json.dumps(endpoint("ApiSetFormValue"))).replace(
            "PAYLOAD", json.dumps(payload)
        )

        def intercept(route):
            request = route.request

            def fetch(**options):
                path = (
                    flow.form.page_path(flow.identifier)
                    if request.method == "GET"
                    else "/draft/" + flow.identifier
                )
                return context.request.fetch(
                    flow.origin + path,
                    method=request.method,
                    headers=request.headers,
                    data=request.post_data_buffer,
                    **options,
                )

            def fulfill(*, response):
                if request.method == "GET":
                    route.fulfill(status=200, body=html, content_type="text/html")
                else:
                    route.fulfill(response=response)

            runner._live_guard(
                SimpleNamespace(request=request, fetch=fetch, fulfill=fulfill, abort=route.abort)
            )

        context.route("**/*", intercept)
        batch = service.store.load()["batch_id"]
        opened = {"action": "open"}
        assert runner.authorize(job, batch, opened)
        page.goto(job["job_url"])
        runner.update(job, batch, page_open=True, intent=None, completed_intent=opened)
        question = hosted_ats.observe(page, job)["fields"][0]
        value, ref = service.store.resolve(question, job)
        intent = {"action": "fill", "field_id": question["id"], "answer_ref": ref}
        assert runner.authorize(job, batch, intent)
        draft.begin(question, value, intent)
        hosted_ats.fill(page, question, value)
        hosted_ats.control(page, question).blur()
        page.wait_for_function("window.draftResponse!==undefined", timeout=5000)
        if case == "known_draft":
            assert page.evaluate("window.draftResponse") == 200, runner.transports[-3:]
            assert flow.drafts == [payload["variables"]]
            draft.wait(page)
            assert flow.drafts == [payload["variables"]]
            assert draft.saved(question, value)
        elif redirect:
            runner.tick()
            current = service.store.load()["jobs"][0]
            assert flow.drafts == [payload["variables"]]
            assert current["status"] == "needs_recheck"
            assert current["intent"] == intent
            assert draft.failed
            page.evaluate("document.querySelector('#name').dispatchEvent(new Event('blur'))")
            page.wait_for_timeout(50)
            runner.tick()
            assert len(flow.drafts) == 1
        else:
            page.wait_for_timeout(50)
            assert flow.drafts == []
            assert runner.blocked_pages[page] == (
                "manual_submit_required" if case.endswith("mixed_final") else "unverified_send_path"
            )
            assert service.store.load()["jobs"][0]["intent"] == intent
        assert flow.events()["submissions"] == []
        context.close()
