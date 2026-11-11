"""Real candidate handoff on one loopback Page; controlled peer, zero model calls."""

import hashlib
import json
import os
import sys
import threading
import time
from copy import deepcopy
from dataclasses import asdict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import urlsplit

import pytest
from playwright.sync_api import sync_playwright
from test_single_application_worker import single_worker as single_worker
from test_worker_codex_assistance import retained_assistance_page as retained_assistance_page

from career_evidence_graph.application_codex_assist import CodexAdapter, CodexAssistConfig
from career_evidence_graph.application_worker import WorkerService
from career_evidence_graph.application_worker_browser import ApplicationRunner
from career_evidence_graph.career_portal_data import PortalDataError
from career_evidence_graph.cua_driver import (
    NATIVE_HANDOFF_PROTOCOL,
    NATIVE_HANDOFF_TOOLS,
    managed_cua_browser,
    validate_native_assistance_policy,
)

pytestmark = [
    pytest.mark.worker_browser,
    pytest.mark.skipif(
        os.environ.get("TS_CUA_NATIVE_TEST") != "1", reason="Explicit native Cua opt-in"
    ),
]

HTML = b"""<!doctype html><title>Native handoff synthetic</title>
<link rel="icon" href="data:,">
<form method="post" action="/submit">
<label>Email <input id="email" name="email" type="email"></label>
<button type="submit">Submit</button></form>
<script>
window.__tomorrowstarMaterialDocument=crypto.randomUUID();
window.nativeInputEvents=0;
window.nativeSubmitEvents=0;
document.querySelector('#email').addEventListener('input',()=>window.nativeInputEvents++);
document.querySelector('form').addEventListener('submit',()=>window.nativeSubmitEvents++);
</script>"""


def scenario_html(effect):
    if effect == "rewrite_after_input":
        return HTML.replace(
            b"()=>window.nativeInputEvents++",
            b"event=>{window.nativeInputEvents++;event.target.value='';}",
        )
    if effect in {"click_boundaries", "click_network"}:
        html = HTML.replace(
            b'<button type="submit">',
            b'<label>Human note <input id="human" value="human original"></label>'
            b'<button id="reset" type="reset">Reset</button><button type="submit">',
        ).replace(
            b"<script>",
            b'<details id="safe"><summary id="safe-summary">Local details</summary>'
            b"<p>Local detail text</p></details>"
            b'<details id="forward"><summary id="forward-summary">'
            b'<label for="reset" style="display:block;padding:20px">Reset forwarding</label>'
            b"</summary><p>Forwarding detail</p></details><script>",
        )
        script = b"""
window.nativeResetEvents=0;
document.querySelector('#human').value='human edited';
document.querySelector('form').addEventListener('reset',()=>window.nativeResetEvents++);
window.nativeClickEvents=[];
document.addEventListener('click',event=>window.nativeClickEvents.push(event.target.id));
"""
        if effect == "click_network":
            script += b"""
window.networkAttempts=[];
document.querySelector('#safe-summary').addEventListener('click',()=>{
  window.networkAttempts.push('POST');
  fetch('/graphql',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({operationName:'SubmitApplication',
      query:'mutation SubmitApplication { submitApplication { id } }'})}).catch(()=>{});
  window.networkAttempts.push('WebSocket');
  window.syntheticSocket=new WebSocket(location.origin.replace('http:','ws:')+'/submit-socket');
});
"""
        return html.replace(b"</script>", script + b"</script>")
    if effect == "focus_after_scroll":
        return HTML.replace(
            b'<form method="post"',
            b'<label>Human note <input id="human" value="human edited"></label>'
            b'<div style="height:2000px"></div><form method="post"',
        ).replace(
            b"</script>",
            b"""
window.focusEvents=[];window.humanInputEvents=0;
const human=document.querySelector('#human');
human.addEventListener('input',()=>window.humanInputEvents++);
document.querySelector('#email').focus({preventScroll:true});
window.addEventListener('scroll',()=>{
  window.focusEvents.push({scrollY,active:document.activeElement.id});
  human.focus({preventScroll:true});human.select();
},{once:true});
</script>""",
        )
    if effect == "inflight_stop":
        return HTML.replace(
            b"()=>window.nativeInputEvents++",
            b"""()=>{window.nativeInputEvents++;
console.log('native-input-handler-start:'+Date.now());
const until=Date.now()+8000;while(Date.now()<until){}
console.log('native-input-handler-end:'+Date.now());}""",
        )
    return HTML


def read_peer(root):
    path = root / "native-peer.jsonl"
    if not path.exists():
        return []
    # Only complete lines are evidence while the controlled peer is still writing.
    # JSONL lines end only at "\n"; frames may carry U+2028, which splitlines() breaks on.
    return [json.loads(line) for line in path.read_text().split("\n")[:-1]]


def page_identity(page):
    session = page.context.new_cdp_session(page)
    try:
        frame = session.send("Page.getFrameTree")["frameTree"]["frame"]
        return {
            "cdp_target_id": session.send("Target.getTargetInfo")["targetInfo"]["targetId"],
            "frame_id": frame["id"],
            "loader_id": frame["loaderId"],
            "url": frame["url"],
        }
    finally:
        session.detach()


def drive_until(h, run_id, predicate, *, timeout=30):
    """Service the ordinary host pump; never suppress native revocation."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        progress = h.adapter.progress(run_id)
        h.extra_evidence["last_progress"] = asdict(progress)
        h.page.wait_for_timeout(25)
    pytest.fail(f"Native case did not reach its observation: {read_peer(h.runtime)}")


def stopped_native(h, run_id):
    stopped = h.adapter.stop(run_id, request_id="real-native-stop")
    deadline = time.monotonic() + 12
    while stopped.stop_status != "stopped" and time.monotonic() < deadline:
        h.page.wait_for_timeout(25)
        stopped = h.adapter.progress(run_id)
    h.extra_evidence["stopped_progress"] = asdict(stopped)
    assert stopped.stop_status == "stopped", stopped
    assert stopped.tools_revoked and stopped.local_tools_drained
    assert stopped.native_handoff["return_ready"] is True
    return stopped


def original_page_intact(h, *, inputs):
    assert h.runner.pages[h.identifier] is h.page and h.context.pages == [h.page]
    assert page_identity(h.page) == h.original_page
    assert h.page.evaluate("[window.nativeInputEvents,window.nativeSubmitEvents]") == [inputs, 0]
    assert h.received == [("GET", "/application")]


def native_denial(result):
    """Accept exact daemon denial codes, never an arbitrary failure or stale ref."""
    data = result.get("structuredContent", {})
    if data.get("effect") == "refused":
        return data.get("error", {}).get("code")
    if result.get("isError") is True and data.get("code") == "tool_invocation_failed":
        text = [row.get("text") for row in result.get("content", [])]
        if data.get("exit_code") == 77 and text in (
            ["handoff_revoked"],
            ["handoff_native_effect_unresolved"],
        ):
            return text[0]
    return None


@pytest.fixture
def native_handoff(retained_assistance_page, tmp_path, monkeypatch, request):
    options = request.param if isinstance(request.param, dict) else {}
    effect = options.get("effect", request.param)
    monkeypatch.setenv("CUA_DRIVER_RS_UPDATE_CHECK", "false")
    candidate = os.environ.get("TS_CUA_DRIVER_BINARY")
    assert candidate, "Set TS_CUA_DRIVER_BINARY to the reviewed native candidate explicitly"
    binary = Path(candidate)
    assert binary.is_absolute() and binary.is_file() and not binary.is_symlink()
    policy = validate_native_assistance_policy(
        {
            "protocol": NATIVE_HANDOFF_PROTOCOL,
            "driver_sha256": hashlib.sha256(binary.read_bytes()).hexdigest(),
            "tools": list(NATIVE_HANDOFF_TOOLS),
            "type_mode": "insert_text",
        }
    )
    original, identifier = retained_assistance_page
    service = WorkerService(
        original.store.applications,
        original.store.root,
        live=True,
        cua=True,
        generic=options.get("generic", False),
        single_flow_root=original.store.single_flow_root,
        single_career_root=original.store.single_career_root,
        single_validator=original.store.single_validator,
        native_assistance_policy=policy,
    )
    value = "synthetic@example.invalid"
    changed_value = ""
    html = options["html"] if "html" in options else scenario_html(effect)
    service.store.answers.put_answer(
        {"question": "Email", "value": value, "scope": {}, "state": "confirmed"}
    )
    received = []

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            received.append(("GET", self.path))
            self.send_response(200 if self.path == "/application" else 404)
            self.send_header("Content-Type", "text/html")
            self.send_header("Content-Length", str(len(html)))
            self.end_headers()
            self.wfile.write(html)

        def do_POST(self):
            received.append(("POST", self.path))
            self.rfile.read(int(self.headers.get("Content-Length", "0")))
            self.send_response(204)
            self.end_headers()

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()
    origin = f"http://127.0.0.1:{server.server_port}"
    document_url = options.get("document_url", origin + "/application")
    parsed_document = urlsplit(document_url)
    document_origin = f"{parsed_document.scheme}://{parsed_document.netloc}"
    runtime, home, native_root = (tmp_path / part for part in ("peer", "home", "native"))
    for directory in (runtime, home, native_root):
        directory.mkdir(mode=0o700)
    (runtime / "peer-settings.json").write_text(
        json.dumps({"effect": effect, **options.get("peer_settings", {})})
    )
    peer = runtime / "controlled-app-server"
    peer.write_text(
        f"#!{Path(sys.executable).resolve()}\n"
        + Path(
            options.get("peer_source", Path(__file__).with_name("native_handoff_peer.py"))
        ).read_text()
    )
    peer.chmod(0o700)
    adapter = CodexAdapter(
        CodexAssistConfig(
            executable=peer,
            runtime=runtime,
            home=home,
            request_timeout=15,
            stop_timeout=2,
            native_assistance_policy=policy,
        )
    )
    try:
        with (
            sync_playwright() as playwright,
            managed_cua_browser(
                playwright,
                native_root,
                click_route="dom_event",
                origins=[document_origin],
                native_handoff=True,
            ) as (context, cua),
        ):
            native_request = cua.client._request

            def record_native_request(message, **options):
                record = {"request": deepcopy(message)}
                try:
                    result = native_request(message, **options)
                    record["response"] = result
                    return result
                except Exception as error:
                    record["exception"] = {"type": type(error).__name__, "message": str(error)}
                    raise
                finally:
                    with (native_root / "native-control.jsonl").open("a") as stream:
                        stream.write(json.dumps(record) + "\n")

            # Observe the real native control boundary without replacing its
            # return value, invoking it twice, or changing the production pump.
            monkeypatch.setattr(cua.client, "_request", record_native_request)

            def loopback_only(route):
                # Isolation cannot approve a request past the production request guard.
                if route.request.url.startswith(origin + "/"):
                    route.fallback()
                else:
                    route.abort()

            page = context.pages[0]
            assert service.store.load()["mode"] == "live"
            runner = ApplicationRunner(
                service.store, context, cua=cua, native_assistance_policy=policy
            )
            assert runner.live is True
            runner.pages[identifier] = page
            runner.page_ids[page] = service.store.load()["jobs"][0]["form_state"]["binding"][
                "page_id"
            ]
            page.on("close", lambda *_: runner.event("page_closed", page, identifier))
            page.on("crash", lambda *_: runner.event("page_crashed", page, identifier))
            page.route_web_socket("**/*", lambda ws: runner._websocket_guard(page, ws))
            context.route("**/*", loopback_only)
            if before_navigation := options.get("before_navigation"):
                before_navigation(
                    SimpleNamespace(
                        original=original,
                        service=service,
                        identifier=identifier,
                        runner=runner,
                        page=page,
                        context=context,
                        runtime=runtime,
                        document_url=document_url,
                    )
                )
            document_supplies = []

            def initial_document(route):
                request = route.request
                if (
                    not document_supplies
                    and request.url == document_url
                    and request.method == "GET"
                    and request.is_navigation_request()
                    and request.frame == page.main_frame
                ):
                    document_supplies.append({"url": request.url, "method": "GET"})
                    if document_url == origin + "/application":
                        route.continue_()
                    else:
                        # Canonical synthetic documents still come from this
                        # actual owned receiver, without an external connection.
                        document_supplies[-1]["receiver_url"] = origin + "/application"
                        response = route.fetch(
                            url=origin + "/application",
                            max_redirects=0,
                            max_retries=0,
                            timeout=10000,
                        )
                        try:
                            route.fulfill(response=response)
                        finally:
                            response.dispose()
                else:
                    route.fallback()

            # Supply only the first synthetic document from the actual loopback
            # server. Every subsequent request falls through to production guards.
            context.route(document_url, initial_document)
            console_events = []
            page.on(
                "console",
                lambda message: console_events.append(
                    {"text": message.text, "at": time.monotonic()}
                ),
            )
            page.goto(document_url)
            context.unroute(document_url, initial_document)
            original_page = page_identity(page)
            token = page.evaluate("window.__tomorrowstarMaterialDocument")
            state = service.store.load()
            state["jobs"][0]["form_state"]["binding"].update(step=page.url, document_token=token)
            state["runtime"]["observed_at"] = time.time()
            state["jobs"][0]["page_observation"]["at"] = time.time()
            service.store.save(state)
            extra_evidence = {"fixture_document_supplies": document_supplies}
            if prepare := options.get("before_request"):
                # Material preparation must precede the first immutable assistance
                # binding. This hook supplies fixture data through real owner APIs.
                prepare(
                    SimpleNamespace(
                        service=service,
                        identifier=identifier,
                        runner=runner,
                        page=page,
                        context=context,
                        runtime=runtime,
                        original_page=original_page,
                        extra_evidence=extra_evidence,
                    )
                )
            service.request(
                "request-assistance",
                {
                    "application_id": identifier,
                    "binding": service.assistance_context(identifier)["binding"],
                    "request_id": "real-native-request",
                },
            )
            reference = service.assistance_context(identifier)["assistance_ref"]
            service.request(
                "claim-assistance",
                {
                    "application_id": identifier,
                    "assistance_ref": reference,
                    "request_id": "real-native-claim",
                },
            )
            assert runner.page_ids[page] == reference["binding"]["page_id"]
            runner.codex_assist = adapter
            try:
                yield SimpleNamespace(
                    effect=effect,
                    service=service,
                    identifier=identifier,
                    runner=runner,
                    adapter=adapter,
                    page=page,
                    context=context,
                    reference=reference,
                    original_page=original_page,
                    received=received,
                    runtime=runtime,
                    value=value,
                    changed_value=changed_value,
                    extra_evidence=extra_evidence,
                    console_events=console_events,
                )
            finally:
                try:
                    adapter.close()
                finally:
                    adapter = None
                    evidence = {
                        "candidate_sha256": policy["driver_sha256"],
                        "worker_source": runner._page_source,
                        "effect": effect,
                        "original_page": original_page,
                        "requests": received,
                        "model_runtime": "controlled app-server peer; no actual model",
                        "console_events": console_events,
                        **extra_evidence,
                    }
                    try:
                        evidence.update(
                            final_page=page_identity(page),
                            same_page=runner.pages[identifier] is page,
                            page_count=len(context.pages),
                            value=page.get_by_label("Email", exact=True).input_value(),
                            events=page.evaluate(
                                "[window.nativeInputEvents,window.nativeSubmitEvents]"
                            ),
                            fixture_state=page.evaluate(
                                """() => ({
                                    human:document.querySelector('#human')?.value,
                                    safeOpen:document.querySelector('#safe')?.open,
                                    forwardOpen:document.querySelector('#forward')?.open,
                                    clicks:window.nativeClickEvents,
                                    resets:window.nativeResetEvents,
                                    focus:window.focusEvents,
                                    humanInputs:window.humanInputEvents,
                                    networkAttempts:window.networkAttempts
                                })"""
                            ),
                        )
                    except Exception as error:
                        evidence["readback_error"] = str(error)
                    (runtime / "effect.json").write_text(json.dumps(evidence, indent=2) + "\n")
        record = json.loads((native_root / "cua-runtime.json").read_text())
        assert record["binary_sha256"] == policy["driver_sha256"]
        assert record["closed"] is True
        assert not Path(record["socket"]).exists()
    finally:
        if adapter is not None:
            adapter.close()
        server.shutdown()
        server.server_close()
        server_thread.join(timeout=2)


@pytest.mark.parametrize("native_handoff", ["normal", "rewrite_after_input"], indirect=True)
def test_real_native_handoff_types_confirmed_empty_field_on_original_page(native_handoff):
    h = native_handoff
    effect, service, identifier = h.effect, h.service, h.identifier
    runner, adapter, page, context = h.runner, h.adapter, h.page, h.context
    reference, original_page = h.reference, h.original_page
    received, runtime = h.received, h.runtime
    value, changed_value = h.value, h.changed_value
    started = runner.start_native_assistance(reference, request_id="real-native-start")
    progress = started
    until = time.monotonic() + 30
    while time.monotonic() < until:
        rows = read_peer(runtime)
        failures = [row for row in rows if row["kind"] == "failure"]
        if effect == "normal":
            assert not failures, failures
        if any(row["kind"] == "completed" for row in rows):
            break
        progress = adapter.progress(started.run_id)
        if progress.status in {"failed", "unknown", "stopped"}:
            latest = read_peer(runtime)
            if effect == "normal":
                assert any(row["kind"] == "completed" for row in latest), (progress, latest)
            elif not any(row["kind"] == "completed" for row in latest):
                assert progress.error_code == "native_call_result_unknown", (progress, latest)
            break
        page.wait_for_timeout(25)
    else:
        pytest.fail(f"Real native input did not complete: {read_peer(runtime)}")

    rows = read_peer(runtime)
    packet = next(row["packet"] for row in rows if row["kind"] == "delivery")
    assert packet["assistance_ref"] == {
        key: value for key, value in reference.items() if key != "backend_authority"
    }
    assert "screenshot" not in packet["page_context"]
    assert "image_url" not in packet["page_context"]
    calls = [
        row["request"]["params"]
        for row in rows
        if row["kind"] == "native_rpc" and row["request"]["method"] == "tools/call"
    ]
    if effect == "normal":
        assert [call["name"] for call in calls] == [
            "get_browser_state",
            "browser_type",
            "get_browser_state",
        ]
        typed = next(row for row in rows if row["kind"] == "completed")["typed"]
        assert typed["effect"] == "confirmed"
        assert any(item["kind"] == "value_readback" for item in typed["evidence"])
    else:
        requests = [
            row["request"]
            for row in rows
            if row["kind"] == "native_sent"
            and row["request"].get("params", {}).get("name") == "browser_type"
        ]
        assert len(requests) in (2, 3)
        assert requests[0] == requests[1]
        responses = [
            row
            for row in rows
            if row["kind"] == "native_rpc"
            and row["request"].get("params", {}).get("name") == "browser_type"
        ]
        results = [row["response"]["result"] for row in responses]
        assert results, "The first actual unknown wire response must be retained"
        unknown = results[0]["structuredContent"]
        assert unknown["effect"] == "unverifiable"
        assert unknown["delivery"]["mode"] == "unknown"
        assert "error" not in unknown
        message = "Input was acknowledged but the final native value could not be verified"
        assert unknown["summary"] == message
        assert any(item.get("text") == message for item in results[0]["content"])
        if len(results) >= 2:
            assert results[1] == results[0] or native_denial(results[1]) == "handoff_revoked"
        retry_scope = next((row for row in rows if row["kind"] == "retry_scope"), None)
        if retry_scope and not retry_scope["fresh_ref"]:
            assert native_denial(retry_scope["fresh_result"]) == "handoff_revoked"
        if len(requests) == 3:
            assert requests[2]["id"] != requests[0]["id"]
            if retry_scope and retry_scope["fresh_ref"]:
                assert requests[2]["params"]["arguments"]["ref"] == retry_scope["fresh_ref"]["ref"]
        if len(results) == 3:
            assert native_denial(results[2]) in {
                "handoff_native_effect_unresolved",
                "handoff_revoked",
            }
        elif len(results) < 2 or len(requests) < 3 or len(results) < 3:
            # The ordinary host pump may revoke and close the peer first. This
            # proves revocation with one effect; absent retry stages remain unverified.
            assert progress.error_code == "native_call_result_unknown"
        fresh_responses = [
            row["response"]
            for row in rows
            if row["kind"] == "native_rpc"
            and row["request"]["id"] > requests[0]["id"]
            and row["request"].get("params", {}).get("name") == "get_browser_state"
        ]
        fresh_refs = (
            fresh_responses[0].get("result", {}).get("structuredContent", {}).get("refs", [])
            if fresh_responses
            else []
        )
        fresh_field = next((row for row in fresh_refs if row.get("name") == "Email"), None)
        used_fresh_ref = bool(
            len(requests) == 3
            and fresh_field
            and requests[2]["params"]["arguments"]["ref"] == fresh_field["ref"]
        )
        h.extra_evidence["unknown_retry_coverage"] = {
            "same_id_sent": True,
            "same_id_response": len(results) >= 2,
            "same_id_cached_result": len(results) >= 2 and results[1] == results[0],
            "fresh_snapshot_sent": any(
                row["kind"] == "native_sent"
                and row["request"]["id"] > requests[0]["id"]
                and row["request"].get("params", {}).get("name") == "get_browser_state"
                for row in rows
            ),
            "fresh_snapshot_response": bool(fresh_responses),
            "fresh_ref_obtained": fresh_field is not None,
            "new_id_sent": len(requests) == 3,
            "new_id_response": len(results) == 3,
            "new_id_used_fresh_ref": used_fresh_ref,
            "new_id_denial": native_denial(results[2]) if len(results) == 3 else None,
            "unverified_stages_must_not_be_claimed": len(results) < 3
            or not used_fresh_ref
            or results[1] != results[0],
        }
    expected_value = value if effect == "normal" else changed_value
    assert page.get_by_label("Email", exact=True).input_value() == expected_value
    assert page.evaluate("[window.nativeInputEvents,window.nativeSubmitEvents]") == [
        1,
        0,
    ]
    assert runner.pages[identifier] is page and context.pages == [page]
    assert page_identity(page) == original_page
    assert received == [("GET", "/application")]

    stopped = adapter.stop(started.run_id, request_id="real-native-stop")
    until = time.monotonic() + 5
    while stopped.stop_status != "stopped" and time.monotonic() < until:
        page.wait_for_timeout(25)
        stopped = adapter.progress(started.run_id)
    assert stopped.stop_status == "stopped", stopped
    assert stopped.tools_revoked and stopped.local_tools_drained
    assert stopped.native_handoff["return_ready"] is True
    ledger = stopped.native_handoff["calls"]
    writes = [row for row in ledger if row["mutation"]]
    assert len(writes) == 1 and writes[0]["tool"] == "browser_type"
    assert writes[0]["status"] == ("observed" if effect == "normal" else "unknown")
    assert writes[0]["text_sha256"] == hashlib.sha256(value.encode()).hexdigest()
    assert page_identity(page) == original_page
    assert page.get_by_label("Email", exact=True).input_value() == expected_value
    assert received == [("GET", "/application")]
    journal = service.store.load()["jobs"][0]["native_handoff_runs"][-1]
    assert journal["events"][0]["phase"] == "prepared"
    assert journal["semantic_unknown"] is (effect == "rewrite_after_input")
    assert any(
        call["call_id"] == writes[0]["call_id"] and call["status"] == "awaiting_host"
        for event in journal["events"]
        for call in (event.get("receipt") or {}).get("calls", [])
    )
    if effect == "rewrite_after_input":
        previous = deepcopy(journal)
        with pytest.raises(PortalDataError):
            runner.start_native_assistance(reference, request_id="unknown-cannot-start-again")
        assert service.store.load()["jobs"][0]["native_handoff_runs"][-1] == previous
        assert page.evaluate("window.nativeInputEvents") == 1


@pytest.mark.parametrize("native_handoff", ["click_boundaries"], indirect=True)
def test_real_native_click_reads_disclosure_and_refuses_reset_submit_label(native_handoff):
    h = native_handoff
    assert h.page.locator("#safe").evaluate("node=>node.open") is False
    started = h.runner.start_native_assistance(h.reference, request_id="real-native-click")
    drive_until(
        h,
        started.run_id,
        lambda: any(row["kind"] in {"completed", "failure"} for row in read_peer(h.runtime)),
    )
    rows = read_peer(h.runtime)
    assert not [row for row in rows if row["kind"] == "failure"], rows
    completed = next(row for row in rows if row["kind"] == "completed")
    local, reset, submit, label = completed["actions"]
    assert local["before"]["states"]["expanded"] in (False, "false")
    result = local["result"]["structuredContent"]
    assert result["effect"] == "confirmed"
    assert any(row["kind"] == "value_readback" for row in result["evidence"])
    after = next(row for row in completed["after"]["refs"] if row.get("name") == "Local details")
    assert after["states"]["expanded"] in (True, "true")
    assert h.page.locator("#safe").evaluate("node=>node.open") is True
    assert "handoff_control_not_permitted" in json.dumps(reset["result"])
    assert "handoff_control_not_permitted" in json.dumps(submit["result"])
    assert label["result"]["structuredContent"]["effect"] == "refused"
    assert label["result"]["structuredContent"]["error"]["code"] == "browser_action_unavailable"
    assert h.page.get_by_label("Human note").input_value() == "human edited"
    assert h.page.locator("#forward").evaluate("node=>node.open") is False
    assert h.page.evaluate("window.nativeResetEvents") == 0
    assert h.page.evaluate("window.nativeClickEvents") == ["safe-summary"]
    stopped = stopped_native(h, started.run_id)
    label_calls = [
        row
        for row in stopped.native_handoff["calls"]
        if row.get("native_ref") == label["before"]["ref"]
    ]
    assert len(label_calls) == 1 and label_calls[0]["status"] == "not_sent"
    original_page_intact(h, inputs=0)


@pytest.mark.parametrize("native_handoff", ["click_network"], indirect=True)
def test_real_native_disclosure_click_still_hits_http_and_websocket_guards(
    native_handoff, monkeypatch
):
    h = native_handoff
    sockets = []
    guard = h.runner._websocket_guard

    def observe_websocket(page, websocket):
        sockets.append({"url": websocket.url, "at": time.monotonic()})
        return guard(page, websocket)

    monkeypatch.setattr(h.runner, "_websocket_guard", observe_websocket)
    h.extra_evidence["websocket_guard_calls"] = sockets

    def request_diagnostics():
        # The ordinary pump may already have moved these events into the store.
        rows = h.runner.transports + h.service.store.load()["jobs"][0].get("observations", [])
        return [row for row in rows if row.get("action") == "request_diagnostic"]

    started = h.runner.start_native_assistance(h.reference, request_id="real-native-network")
    drive_until(
        h,
        started.run_id,
        lambda: (
            bool(sockets)
            and any(row.get("reason") == "manual_submit_required" for row in request_diagnostics())
        ),
    )
    diagnostics = request_diagnostics()
    h.extra_evidence["request_diagnostics"] = deepcopy(diagnostics)
    assert any(
        row["stage"] == "request_blocked"
        and row["reason"] == "manual_submit_required"
        and row["method"] == "POST"
        and row["dispatch"] == "not_sent"
        for row in diagnostics
    )
    assert len(sockets) == 1 and sockets[0]["url"].endswith("/submit-socket")
    assert h.page.evaluate("window.networkAttempts") == ["POST", "WebSocket"]
    assert h.page.locator("#safe").evaluate("node=>node.open") is True
    stopped_native(h, started.run_id)
    original_page_intact(h, inputs=0)


@pytest.mark.parametrize("native_handoff", ["focus_after_scroll"], indirect=True)
def test_real_native_scroll_focus_drift_preserves_human_value(native_handoff):
    h = native_handoff
    assert h.page.evaluate("({y:scrollY,active:document.activeElement.id})") == {
        "y": 0,
        "active": "email",
    }
    started = h.runner.start_native_assistance(h.reference, request_id="real-native-focus")
    drive_until(
        h,
        started.run_id,
        lambda: any(row["kind"] in {"completed", "failure"} for row in read_peer(h.runtime)),
    )
    results = [
        row["response"]["result"]
        for row in read_peer(h.runtime)
        if row["kind"] == "native_rpc"
        and row["request"].get("params", {}).get("name") == "browser_type"
    ]
    assert len(results) == 1
    assert results[0]["structuredContent"]["effect"] == "refused"
    assert results[0]["structuredContent"]["error"]["code"] == "browser_action_unavailable"
    focus_events = h.page.evaluate("window.focusEvents")
    assert len(focus_events) == 1
    assert focus_events[0]["scrollY"] > 0 and focus_events[0]["active"] == "email"
    assert h.page.evaluate("document.activeElement.id") == "human"
    assert h.page.get_by_label("Human note").input_value() == "human edited"
    assert h.page.evaluate("window.humanInputEvents") == 0
    assert h.page.get_by_label("Email", exact=True).input_value() == ""
    stopped = stopped_native(h, started.run_id)
    requested_ref = next(
        row["request"]["params"]["arguments"]["ref"]
        for row in read_peer(h.runtime)
        if row["kind"] == "native_rpc"
        and row["request"].get("params", {}).get("name") == "browser_type"
    )
    writes = [row for row in stopped.native_handoff["calls"] if row["mutation"]]
    assert len(writes) == 1
    assert writes[0]["tool"] == "browser_type" and writes[0]["native_ref"] == requested_ref
    assert writes[0]["status"] == "not_sent"
    h.extra_evidence["focus_stage"] = (
        "Actual scroll and focus drift plus not_sent; the public refusal does not identify "
        "an exact internal guard stage"
    )
    original_page_intact(h, inputs=0)


@pytest.mark.parametrize(
    "native_handoff", ["save_before_admit", "save_after_receipt"], indirect=True
)
def test_real_native_storage_failure_retains_original_intent(native_handoff, monkeypatch):
    h = native_handoff
    save = h.service.store.save
    failure = []
    save_error = OSError("synthetic native checkpoint write failure")

    def fail_at_native_save(state):
        runs = state["jobs"][0].get("native_handoff_runs", [])
        receipt = runs[-1]["events"][-1].get("receipt") if runs else None
        calls = (receipt or {}).get("calls", [])
        statuses = {"awaiting_host"} if h.effect == "save_before_admit" else {"observed", "unknown"}
        if failure or any(row["mutation"] and row["status"] in statuses for row in calls):
            if not failure:
                failure.append({"attempted": deepcopy(runs[-1]), "durable": h.service.store.load()})
            raise save_error
        return save(state)

    monkeypatch.setattr(h.service.store, "save", fail_at_native_save)
    h.extra_evidence["save_failure"] = failure
    try:
        started = h.runner.start_native_assistance(
            h.reference, request_id="real-native-save-failure"
        )
        run_id = started.run_id
    except OSError as error:
        if error is not save_error:
            raise
        assert failure and h.runner._assistance_run is not None
        reference, run_id = h.runner._assistance_run
        assert reference == h.reference and run_id
        h.extra_evidence["start_save_exception"] = {
            "same_injected_error": True,
            "message": str(error),
            "registered_run_id": run_id,
        }
    drive_until(h, run_id, lambda: bool(failure))
    progress = h.adapter.progress(run_id)
    h.extra_evidence["memory_after_save_failure"] = asdict(progress)
    assert progress.tools_revoked
    assert progress.error_code == "native_receipt_persistence_failed"
    if h.effect == "save_after_receipt":
        assert progress.status == "unknown"
        assert progress.native_turn_status == "completed"
    else:
        assert progress.native_turn_status == "unknown"
        assert progress.status == "unknown" or (
            progress.status == "stopped" and progress.stop_status == "stopped"
        )
        if progress.status == "stopped":
            assert progress.local_tools_drained and progress.process_stopped
        writes = [row for row in progress.native_handoff["calls"] if row["mutation"]]
        assert len(writes) == 1
        assert writes[0]["tool"] == "browser_type" and writes[0]["status"] == "not_sent"
    durable_state = h.service.store.load()
    durable = durable_state["jobs"][0]
    before = failure[0]["durable"]["jobs"][0]
    assert durable["native_handoff_runs"] == before["native_handoff_runs"]
    assert durable["intent"] == before["intent"]
    assert durable["assistance"] == before["assistance"]
    assert durable_state["current_job_id"] == h.identifier
    assert durable["assistance"]["status"] == "claimed"
    assert durable["assistance"]["active_writer"] == "codex"
    journal = durable["native_handoff_runs"][-1]
    assert journal["phase"] != "stopped"
    assert journal["assistance_ref"] == h.reference
    assert journal["events"][0]["phase"] == "prepared"
    if h.effect == "save_after_receipt":
        assert any(
            call["mutation"] and call["status"] == "awaiting_host"
            for event in journal["events"]
            for call in (event.get("receipt") or {}).get("calls", [])
        )
    inputs = 0 if h.effect == "save_before_admit" else 1
    assert h.page.get_by_label("Email", exact=True).input_value() == (h.value if inputs else "")
    stopped = stopped_native(h, run_id)
    assert stopped.status != "completed"
    if h.effect == "save_after_receipt":
        assert stopped.status == "unknown"
        assert stopped.error_code == "native_receipt_persistence_failed"
        assert stopped.native_turn_status == "completed"
    assert h.service.store.load()["jobs"][0]["native_handoff_runs"] == before["native_handoff_runs"]
    # Recover only the injected disk failure. Preserve any real stop sentinel,
    # scope change, original claim and unresolved journal when retrying prepare.
    monkeypatch.setattr(h.service.store, "save", save)
    before_retry = h.service.store.path.read_bytes()
    with pytest.raises(PortalDataError) as rejected:
        h.service.store.record_native_handoff(
            h.reference,
            request_id="save-failure-cannot-prepare-again",
            phase="prepared",
            scope=journal["scope"],
            expected_worker_source=journal["worker_source"],
        )
    h.extra_evidence["durable_retry_denial"] = rejected.value.code
    assert rejected.value.code in {"native_handoff_unresolved", "native_handoff_scope_changed"}
    assert h.service.store.path.read_bytes() == before_retry
    original_page_intact(h, inputs=inputs)


@pytest.mark.parametrize("native_handoff", ["inflight_stop"], indirect=True)
def test_real_native_stop_begins_during_input_handler_and_drains(native_handoff):
    h = native_handoff
    start_prefix, end_prefix = "native-input-handler-start:", "native-input-handler-end:"
    started = h.runner.start_native_assistance(h.reference, request_id="real-native-inflight")
    drive_until(
        h,
        started.run_id,
        lambda: any(row["text"].startswith(start_prefix) for row in h.console_events),
    )
    assert not any(row["text"].startswith(end_prefix) for row in h.console_events)
    stop_started = time.monotonic()
    stop_wall = time.time()
    h.extra_evidence["stop_started"] = stop_started
    h.extra_evidence["stop_wall_seconds"] = stop_wall
    stopped = stopped_native(h, started.run_id)
    stop_completed_wall = time.time()
    h.extra_evidence["stop_completed_wall_seconds"] = stop_completed_wall
    drive_until(
        h,
        started.run_id,
        lambda: any(row["text"].startswith(end_prefix) for row in h.console_events),
        timeout=15,
    )
    start = next(row for row in h.console_events if row["text"].startswith(start_prefix))
    end = next(row for row in h.console_events if row["text"].startswith(end_prefix))
    assert start["at"] <= stop_started < end["at"]
    browser_start = int(start["text"][len(start_prefix) :])
    browser_end = int(end["text"][len(end_prefix) :])
    assert browser_start <= stop_wall * 1000 < browser_end
    assert browser_end <= stop_completed_wall * 1000
    writes = [row for row in stopped.native_handoff["calls"] if row["mutation"]]
    assert len(writes) == 1 and writes[0]["status"] == "unknown"
    journal = h.service.store.load()["jobs"][0]["native_handoff_runs"][-1]
    assert journal["semantic_unknown"] is True
    revoked_inflight = [
        event["receipt"]
        for event in journal["events"]
        if (event.get("receipt") or {}).get("revoked") is True
        and event["receipt"]["active_calls"] > 0
    ]
    h.extra_evidence["revoked_inflight_receipts"] = deepcopy(revoked_inflight)
    assert revoked_inflight
    assert any(
        call["call_id"] == writes[0]["call_id"] and call["status"] == "in_flight"
        for receipt in revoked_inflight
        for call in receipt["calls"]
    )
    assert stopped.native_handoff["active_calls"] == 0
    assert h.page.get_by_label("Email", exact=True).input_value() == h.value
    original_page_intact(h, inputs=1)
