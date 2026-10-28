"""MC-09 slice D: the takeover chain through the real native proxy on one loopback page.

Real mail intake, Pipeline (background thread), WorkerService, ApplicationRunner
ticks, the reviewed native candidate's owned browser and the real CodexAdapter.
Only the app-server is a controlled peer (``native_return_peer.py``, zero model
calls); every page effect of a takeover comes from the native tools. The page is
the slice C Lever-shaped document with two covered text comboboxes. Final Submit
stays manual.
"""

import base64
import hashlib
import json
import os
import subprocess
import sys
import threading
import time
import traceback
from copy import deepcopy
from dataclasses import asdict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace

import pytest
from synthetic_ats_material_context import supply_synthetic_material_context
from test_application_intake import message
from test_application_intake import page as captured_page
from test_application_pipeline import Flow
from test_synthetic_takeover_chain_browser import (
    DOCUMENT_URL,
    FACTS,
    HTML,
    JOB_URL,
    MAIL_URL,
    _until,
    assistance,
    counters,
    drive,
    fills,
    job,
    values,
)

from career_evidence_graph import hosted_ats
from career_evidence_graph.application_codex_assist import CodexAdapter, CodexAssistConfig
from career_evidence_graph.application_form_state import SAMPLE_INTERVAL
from career_evidence_graph.application_intake import ApplicationIntakeService
from career_evidence_graph.application_pipeline import ApplicationPipeline
from career_evidence_graph.application_worker import (
    WorkerService,
    digest,
    script_writes_allowed,
    start_run,
)
from career_evidence_graph.application_worker_browser import ApplicationRunner
from career_evidence_graph.career_portal_data import ApplicationStore
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

PEER = Path(__file__).with_name("native_return_peer.py")
LOOPBACK = {"127.0.0.1", "[::1]", "::1", "localhost"}
# The first takeover's Country typing lands, then the page stays busy so the
# native call is still in flight when the peer claims the segment resolved.
SLOW_COUNTRY = HTML.replace(
    b"</script>",
    b"""document.querySelector('#country').addEventListener('input',()=>{
  console.log('native-input-handler-start:'+Date.now());
  const until=Date.now()+8000;while(Date.now()<until){}
  console.log('native-input-handler-end:'+Date.now());
});
</script>""",
)


def read_peer(root):
    path = root / "native-peer.jsonl"
    if not path.exists():
        return []
    return [
        json.loads(line)
        for line in path.read_text().splitlines(keepends=True)
        if line.endswith("\n")
    ]


def chrome_sockets(pid):
    """Diagnostic network check: every connected socket of the owned browser tree."""
    pids, frontier = {pid}, [pid]
    while frontier:
        found = subprocess.run(
            ["pgrep", "-P", str(frontier.pop())], capture_output=True, text=True, check=False
        ).stdout.split()
        for child in map(int, found):
            if child not in pids:
                pids.add(child)
                frontier.append(child)
    lines = subprocess.run(
        ["lsof", "-nP", "-a", "-i", "-p", ",".join(map(str, sorted(pids)))],
        capture_output=True,
        text=True,
        check=False,
    ).stdout.splitlines()[1:]
    remote = []
    for line in lines:
        name = line.split()[8] if len(line.split()) > 8 else ""
        if "->" in name:
            host = name.split("->", 1)[1].rsplit(":", 1)[0]
            if host not in LOOPBACK:
                remote.append(line)
    return {"at": time.time(), "pids": sorted(pids), "lsof": lines, "non_loopback": remote}


@pytest.fixture
def native_chain(tmp_path, monkeypatch, request):
    options = request.param
    effect, html = options["effect"], options.get("html", HTML)
    os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", "0")
    from playwright.sync_api import sync_playwright

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
    (tmp_path / "applications").mkdir()
    apps = ApplicationStore(tmp_path / "applications")
    intake = ApplicationIntakeService(
        apps,
        tmp_path / "intake",
        reader=lambda *_a, **_k: {
            "status": "readable",
            "emails": [message(links=[MAIL_URL])],
            "provenance": {},
        },
        fetcher=lambda url: (
            captured_page(url)
            | {
                "final_url": JOB_URL,
                "redirects": [{"url": url, "status": 302, "location": JOB_URL}],
                "job_fields": {
                    "title": "Engineer",
                    "company": "Synthetic",
                    "location": "Zurich, Switzerland",
                },
            }
        ),
    )
    worker = WorkerService(
        apps,
        tmp_path / "worker",
        live=True,
        cua=True,
        single_flow_root=tmp_path / "flow",
        single_career_root=tmp_path / "career",
        single_validator=lambda *_a, **_k: None,
        native_assistance_policy=policy,
    )
    monkeypatch.setattr(worker, "spawn", lambda: None)

    class RealWorkerFlow(Flow):
        def prepare_worker(self, identifier, revision, country, send_confirmed, **options):
            task = self.tasks[identifier]
            app = apps.get_application(identifier)
            worker.request(
                "prepare",
                {
                    "workflow": "single",
                    "send_confirmed": True,
                    "jobs": [
                        {
                            "application_id": identifier,
                            "revision": app["revision"],
                            "country": country,
                            "filename": "synthetic.pdf",
                            "file_base64": base64.b64encode(b"%PDF-1.4 synthetic").decode(),
                            "single_binding": {"task_id": identifier},
                        }
                    ],
                },
            )
            task.update(
                status="queued",
                worker_ref={
                    "batch_id": worker.snapshot()["batch_id"],
                    "job_id": identifier,
                    "status": "queued",
                },
            )
            return deepcopy(task)

        def worker_action(self, identifier, revision, operation, payload):
            self.actions.append(operation)
            worker.request(operation, payload | {"application_id": identifier})
            status = next(
                row["status"]
                for row in worker.snapshot()["jobs"]
                if row["application_id"] == identifier
            )
            self.tasks[identifier]["worker_ref"]["status"] = status
            return deepcopy(self.tasks[identifier])

    flow = RealWorkerFlow(tmp_path / "flow", apps, worker)
    flow.actions = []
    requests = []
    original_request = worker.request_takeover

    def counted(*args, **kwargs):
        requests.append(kwargs["request_id"])
        return original_request(*args, **kwargs)

    monkeypatch.setattr(worker, "request_takeover", counted)
    pipeline = ApplicationPipeline(flow, intake, worker, interval=0.05)

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
            self.send_response(204)
            self.end_headers()

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    origin = f"http://127.0.0.1:{server.server_port}"
    runtime, home, native_root = (tmp_path / part for part in ("peer", "home", "native"))
    for directory in (runtime, home, native_root):
        directory.mkdir(mode=0o700)
    (runtime / "peer-settings.json").write_text(json.dumps({"effect": effect}))
    peer = runtime / "controlled-app-server"
    peer.write_text(f"#!{Path(sys.executable).resolve()}\n" + PEER.read_text())
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
    blocked, fetched, escaped, seen, console = [], [], [], [], []
    evidence = {"effect": effect, "model_runtime": "controlled app-server peer; no actual model"}
    try:
        pipeline.start(request_id="native-chain-start")
        _until(lambda: pipeline.snapshot()["status"] == "filling")
        assert worker.store.load()["jobs"][0]["job_url"] == JOB_URL
        for question, value in FACTS.items():
            worker.store.answers.put_answer(
                {"question": question, "value": value, "scope": {}, "state": "confirmed"}
            )
        supply_synthetic_material_context(worker, monkeypatch)
        start_run(worker.store)
        with (
            sync_playwright() as playwright,
            managed_cua_browser(
                playwright,
                native_root,
                click_route="dom_event",
                origins=[JOB_URL],
                native_handoff=True,
            ) as (context, cua),
        ):
            native_request = cua.client._request

            def record_native_request(message, **options):
                row = {"request": deepcopy(message)}
                try:
                    result = native_request(message, **options)
                    row["response"] = result
                    return result
                except Exception as error:
                    row["exception"] = {"type": type(error).__name__, "message": str(error)}
                    raise
                finally:
                    with (native_root / "native-control.jsonl").open("a") as stream:
                        stream.write(json.dumps(row) + "\n")

            monkeypatch.setattr(cua.client, "_request", record_native_request)
            native_control = cua.client._control_request

            def record_native_control(message, **options):
                row = {"control": deepcopy(message)}
                try:
                    result = native_control(message, **options)
                    row["response"] = result
                    return result
                except Exception as error:
                    row["exception"] = {"type": type(error).__name__, "message": str(error)}
                    raise
                finally:
                    with (native_root / "native-control.jsonl").open("a") as stream:
                        stream.write(json.dumps(row, default=str) + "\n")

            # Diagnostics only: observe the handoff control channel without replacing it.
            monkeypatch.setattr(cua.client, "_control_request", record_native_control)
            # Production's worker context default (application_worker_browser main).
            context.set_default_timeout(4000)
            initial_pages = [(page, page.url) for page in context.pages]
            sockets = [chrome_sockets(cua.pid) | {"stage": "browser_started"}]
            context.on("request", lambda r: seen.append((r.method, r.url)))
            context.on(
                "requestfinished",
                lambda r: (
                    sockets.append(chrome_sockets(cua.pid) | {"stage": "document_read"})
                    if r.url == DOCUMENT_URL
                    else None
                ),
            )
            context.on(
                "console", lambda m: console.append({"text": m.text, "at": time.monotonic()})
            )
            runner = ApplicationRunner(
                worker.store, context, cua=cua, native_assistance_policy=policy
            )
            assert runner.live is True
            runner.codex_assist = adapter

            def isolated(route):
                """Production's live guard decides; its fetch is served by the loopback."""

                class Loopback:
                    request = route.request

                    def fetch(self, **options):
                        assert options == {"max_redirects": 0, "max_retries": 0, "timeout": 10000}
                        path = "/application" if self.request.url == DOCUMENT_URL else "/none"
                        fetched.append((self.request.method, self.request.url))
                        return route.fetch(
                            url=origin + path, method="GET", post_data=None, **options
                        )

                    def fulfill(self, *, response):
                        route.fulfill(response=response)

                    def abort(self, reason="failed"):
                        blocked.append((self.request.method, self.request.url))
                        route.abort(reason)

                    def continue_(self, **_options):
                        # A handed-off page's own request would leave the host: isolate it.
                        escaped.append((self.request.method, self.request.url))
                        route.abort("blockedbyclient")

                    fallback = continue_

                runner._live_guard(Loopback())

            # Registered after the runner: this wrapper of its own guard runs first,
            # so no request reaches anything but the loopback receiver.
            context.route("**/*", isolated)
            ns = SimpleNamespace(
                effect=effect,
                pipeline=pipeline,
                flow=flow,
                worker=worker,
                runner=runner,
                adapter=adapter,
                context=context,
                cua=cua,
                client=cua.client,
                runtime=runtime,
                requests=requests,
                received=received,
                blocked=blocked,
                fetched=fetched,
                escaped=escaped,
                seen=seen,
                console=console,
                initial_pages=initial_pages,
                writes=[],
                trace=[],
                at_start=[],
                sockets=sockets,
                page=None,
            )
            hosted_fill = hosted_ats.fill

            def script_fill(page, question, value):
                state = worker.store.load()
                ns.writes.append(
                    {
                        "writer": "script",
                        "field": question.get("question"),
                        "script": script_writes_allowed(state),
                        "handoff_active": cua.client.handoff_active,
                        "at": time.time(),
                    }
                )
                return hosted_fill(page, question, value)

            monkeypatch.setattr(hosted_ats, "fill", script_fill)
            start_takeover = adapter.start_takeover

            def observed_start(reference, **kwargs):
                """Observation only: snapshot the dispatch and log each native admission."""
                ns.at_start.append(
                    {
                        "request_id": kwargs["request_id"],
                        "job": deepcopy(worker.store.load()["jobs"][0]),
                        "pipeline": pipeline.snapshot(),
                        "page": counters(ns),
                        "values": values(ns),
                        "delivery": deepcopy(kwargs["delivery"]),
                    }
                )
                ns.sockets.append(chrome_sockets(cua.pid))
                admit = kwargs["before_native_call"]

                def recorded_admit(call):
                    allowed = admit(call)
                    ns.writes.append(
                        {
                            "writer": "codex",
                            "tool": call.get("tool"),
                            "field": (call.get("field_hint") or {}).get("name"),
                            "admitted": allowed,
                            "script": script_writes_allowed(worker.store.load()),
                            "at": time.time(),
                        }
                    )
                    return allowed

                try:
                    result = start_takeover(
                        reference, **{**kwargs, "before_native_call": recorded_admit}
                    )
                    ns.at_start[-1]["result"] = asdict(result)
                    return result
                except Exception:
                    # Diagnostics only: the Worker maps this refusal to a capability code.
                    ns.at_start[-1]["error"] = traceback.format_exc()
                    raise

            adapter.start_takeover = observed_start
            start_native = runner.start_native_assistance
            ns.start_errors = []

            def recorded_native_start(reference, **kwargs):
                # Diagnostics only: keep the refusal the Worker maps to a capability code.
                try:
                    return start_native(reference, **kwargs)
                except Exception:
                    ns.start_errors.append(traceback.format_exc())
                    raise

            runner.start_native_assistance = recorded_native_start
            try:
                yield ns
            finally:
                try:
                    adapter.close()
                finally:
                    evidence.update(
                        candidate_sha256=policy["driver_sha256"],
                        worker_source=runner._page_source,
                        received=received,
                        fetched=fetched,
                        blocked=blocked,
                        escaped=escaped,
                        seen=seen,
                        console=console,
                        trace=ns.trace,
                        writes=ns.writes,
                        takeover_requests=requests,
                        starts=[row["request_id"] for row in ns.at_start],
                        deliveries=[row["delivery"].get("next_step") for row in ns.at_start],
                        sockets=ns.sockets,
                        at_start=ns.at_start,
                        start_errors=ns.start_errors,
                    )
                    try:
                        evidence.update(
                            final_values=values(ns),
                            final_counters=counters(ns),
                            page_count=len(context.pages),
                            pages=[page.url for page in context.pages],
                        )
                    except Exception as error:
                        evidence["readback_error"] = str(error)
                    (runtime / "effect.json").write_text(
                        json.dumps(evidence, indent=2, default=str) + "\n"
                    )
        record = json.loads((native_root / "cua-runtime.json").read_text())
        assert record["binary_sha256"] == policy["driver_sha256"]
        assert record["closed"] is True
    finally:
        adapter.close()
        pipeline.close()
        intake.close()
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def peer_failures(ns):
    return [row for row in read_peer(ns.runtime) if row["kind"] == "failure"]


def mutation_calls(ns):
    calls = {}
    for run in job(ns).get("native_handoff_runs") or []:
        for event in run["events"]:
            for call in (event.get("receipt") or {}).get("calls", []):
                if call.get("mutation"):
                    calls[(run["request_id"], call["call_id"])] = call
    return calls


def native_sent(ns):
    return [
        row
        for row in read_peer(ns.runtime)
        if row["kind"] == "native_sent" and row["request"].get("method") == "tools/call"
    ]


def stalled(ns):
    """The Pipeline itself waits; a job's needs_recheck during a real takeover is not a stop.

    The native turn's stop, drain, reclaim and readback span several ticks, during which
    the job keeps its dispatch reason while the Pipeline is still filling.
    """
    return ns.pipeline.snapshot()["status"] in {"needs_recheck", "needs_input"}


def started(ns, count):
    return lambda: len(ns.at_start) >= count or bool(peer_failures(ns))


def isolated_network(ns):
    """Page level: every request was served from loopback or aborted; none left the host."""
    assert ns.received == [("GET", "/application")]
    assert ns.fetched == [("GET", DOCUMENT_URL)]
    assert ns.escaped == []
    assert set(ns.seen) <= set(ns.fetched) | set(ns.blocked), ns.seen
    assert ("GET", DOCUMENT_URL) in ns.seen
    # Recorded evidence only (user decision): the owned Chrome's own background
    # connections and DNS/TCP preconnect to the synthetic job host carry no request.
    ns.sockets.append(chrome_sockets(ns.cua.pid) | {"stage": "case_end"})


def one_page(ns):
    page = ns.page
    identifier = job(ns)["application_id"]
    assert ns.runner.pages == {identifier: page}
    others = [p for p in ns.context.pages if p is not page]
    assert [(p, p.url) for p in others] == ns.initial_pages, ns.initial_pages
    assert all(url == "about:blank" for _p, url in ns.initial_pages)


def single_writer(ns):
    assert all(not (row["script"] and row["codex"]) for row in ns.trace)
    for row in ns.writes:
        if row["writer"] == "script":
            assert row["script"] is True and row["handoff_active"] is False, row
        else:
            assert row["script"] is False, row


def codex_types(ns):
    return [row for row in ns.writes if row["writer"] == "codex" and row["tool"] == "browser_type"]


def first_stop(ns):
    """Real script stop on the covered Country box, then one automatic native takeover."""
    drive(ns, lambda: started(ns, 1)() or stalled(ns))
    assert not peer_failures(ns), peer_failures(ns)
    assert ns.at_start, ns.trace
    at = ns.at_start[0]
    stopped, dispatched = at["job"], at["job"]["assistance"]
    intent = stopped["intent"]
    assert (stopped["status"], stopped["reason"]) == ("needs_recheck", "browser_result_unknown")
    assert intent["action"] == "fill" and intent["expected_value"] == FACTS["Country"]
    assert intent["dispatch_state"] == "sent" and intent["executor"] == "playwright"
    assert intent["route_reason"] == "supported_dom_field"
    assert at["values"]["country"] == "" and at["page"]["selections"] == {}
    assert at["values"]["email"] == FACTS["Email"]
    assert dispatched["generation"] == 1 and dispatched["status"] == "claimed"
    assert dispatched["active_writer"] == "codex"
    assert dispatched["dispatch"]["blocker"]["code"] == "browser_result_unknown"
    assert dispatched["dispatch"]["blocker"]["field_id"] == intent["field_id"]
    assert dispatched["dispatch"]["pending_intent_ref"] == digest(intent)
    assert at["pipeline"]["takeover_request"]["request_id"] == dispatched["claim_request_id"]
    assert [row["request_id"] for row in ns.at_start] == [dispatched["claim_request_id"]]
    assert ns.requests == [dispatched["claim_request_id"]]
    assert at["delivery"]["next_step"]["kind"] == "reconcile_pending_actions"
    return intent


def case(effect, html=HTML):
    return pytest.param({"effect": effect, "html": html}, id=effect)


@pytest.mark.parametrize("native_chain", [case("chain")], indirect=True)
def test_native_chain_two_auto_takeovers_return_script_fill_and_manual_submit_wait(native_chain):
    ns = native_chain
    country_intent = first_stop(ns)
    drive(ns, lambda: assistance(ns).get("status") == "released" or bool(peer_failures(ns)))
    assert not peer_failures(ns), peer_failures(ns)
    returned = job(ns)
    first = returned["assistance"]
    outcome = deepcopy(first["outcome"])
    assert first["active_writer"] == "script"
    assert first["stop"]["reason"] == "native_turn_completed"
    assert first["stop"]["stop_status"] == "stopped"
    assert first["report"]["native_turn_id"] == "controlled-native-turn"
    assert first["report"]["claimed"]["next_step"] == {
        "kind": "return_to_script",
        "field_id": "phone",
    }
    assert (
        first["stop"]["observed_at"]
        <= outcome["session_reclaimed_at"]
        <= outcome["page_verification"]["at"]
        <= outcome["adopted_at"]
    )
    assert outcome["kind"] == "script_checkpoint" and outcome["return_count"] == 1
    assert returned["assistance_return_count"] == 1
    observed = {
        call["call_id"]
        for (request_id, _), call in mutation_calls(ns).items()
        if request_id == first["claim_request_id"] and call["status"] == "observed"
    }
    assert [row["field_id"] for row in outcome["attributed_fields"]] == ["country"]
    assert {row["call_id"] for row in outcome["attributed_fields"]} <= observed
    # The real native browser_type typed the confirmed fact; the pending script
    # intent was settled by read-only readback, never replayed.
    assert returned["intent"] is None
    resolution = returned["action_resolutions"][-1]
    assert resolution["intent_ref"] == country_intent["attempt_id"]
    assert resolution["conclusion"] == "current_matches"
    assert resolution["source"] == "retained_original_page"
    assert values(ns)["country"] == FACTS["Country"] and values(ns)["phone"] == ""
    sent_at_return = len(native_sent(ns))

    # The script itself continues on the same page and fills Phone.
    phone = outcome["checkpoint_field_id"]
    assert phone != "phone"
    drive(ns, lambda: any(row.get("field_id") == phone for row in fills(ns)) or stalled(ns))
    phone_fill = next(row for row in fills(ns) if row.get("field_id") == phone)
    assert phone_fill["executor"] == "playwright" and phone_fill["adopted"] is True
    assert phone_fill["at"] > outcome["adopted_at"]
    assert values(ns)["phone"] == FACTS["Phone"]
    assert len(native_sent(ns)) == sent_at_return

    # The covered Region box is a second real unknown stop: generation 2.
    drive(ns, lambda: started(ns, 2)() or stalled(ns))
    assert len(ns.at_start) == 2 and not peer_failures(ns), ns.trace
    second_at = ns.at_start[1]["job"]
    second = second_at["assistance"]
    assert (second_at["status"], second_at["reason"]) == ("needs_recheck", "browser_result_unknown")
    assert second_at["intent"]["expected_value"] == FACTS["Region"]
    assert second["generation"] == 2 and second["status"] == "claimed"
    assert second["dispatch"]["pending_intent_ref"] == digest(second_at["intent"])
    assert second["claim_request_id"] != first["claim_request_id"]
    assert ns.requests == [first["claim_request_id"], second["claim_request_id"]]
    assert ns.at_start[1]["delivery"]["next_step"]["kind"] == "complete_remaining_fields"

    # The second native turn finishes the form: filling_complete.
    drive(
        ns,
        lambda: bool(assistance(ns).get("outcome")) or stalled(ns) or bool(peer_failures(ns)),
    )
    assert not peer_failures(ns), peer_failures(ns)
    completed = job(ns)
    final = completed["assistance"]
    assert final["generation"] == 2 and final["status"] == "released"
    assert final["outcome"]["kind"] == "filling_complete"
    assert [row["field_id"] for row in final["outcome"]["attributed_fields"]] == ["region"]
    assert completed["status"] == "ready_for_review" and completed["intent"] is None
    assert [row["generation"] for row in completed["assistance_history"]] == [1]
    assert values(ns) == {
        "email": FACTS["Email"],
        "country": FACTS["Country"],
        "phone": FACTS["Phone"],
        "region": FACTS["Region"],
    }

    # The Pipeline hands the original page over for the manual Submit wait.
    drive(ns, lambda: ns.pipeline.snapshot()["status"] == "ready_for_review")
    drive(ns, lambda: bool(job(ns).get("handed_off")) or stalled(ns))
    for _ in range(10):
        ns.runner.tick()
        ns.page.wait_for_timeout(25)
    state, final_job = ns.pipeline.snapshot(), job(ns)
    assert state["control"] == "paused" and state["notification"]["status"] == "ready_for_review"
    assert ns.flow.actions.count("review") == 1
    handoff = final_job["handoff"]
    assert final_job["handed_off"] is True and handoff["status"] == "complete"
    assert handoff["source"] == "automatic_submit_wait" and handoff["actor"] == "system"
    assert handoff["human_reviewed"] is False
    assert final_job["status"] == "ready_for_review" and not final_job.get("manual_submission")
    assert final_job["assistance"]["outcome"] == final["outcome"]
    assert state["items"][0]["status"] != "completed"

    page_counters = counters(ns)
    assert page_counters["submits"] == 0 and page_counters["files"] == 1
    assert page_counters["selections"] == {"country": 1, "region": 1}
    one_page(ns)
    isolated_network(ns)
    assert len(ns.requests) == 2 == len(ns.at_start)
    single_writer(ns)
    writers = [
        (row["writer"], row["field"])
        for row in ns.writes
        if row["writer"] == "script" or row["tool"] == "browser_type"
    ]
    assert writers == [
        ("script", "Email"),
        ("script", "Country"),
        ("codex", "Country"),
        ("script", "Phone"),
        ("script", "Region"),
        ("codex", "Region"),
    ]
    assert all(row["admitted"] for row in codex_types(ns))


@pytest.mark.parametrize("native_chain", [case("chain_tool_unknown", SLOW_COUNTRY)], indirect=True)
def test_native_chain_tool_unknown_waits_without_replay(native_chain):
    ns = native_chain
    country_intent = first_stop(ns)
    released = []

    def release():
        if not released and any(
            row["text"].startswith("native-input-handler-start:") for row in ns.console
        ):
            (ns.runtime / "release-report").write_text("report while the call is in flight\n")
            released.append(time.time())
        return False

    drive(
        ns,
        lambda: (
            release()
            or bool(peer_failures(ns))
            or (
                ns.pipeline.snapshot()["status"] == "needs_recheck"
                and (assistance(ns).get("stop") or {}).get("stop_status") == "stopped"
            )
        ),
    )
    assert released and not peer_failures(ns), peer_failures(ns)
    before = {
        "page": counters(ns),
        "values": values(ns),
        "fills": len(fills(ns)),
        "intent": deepcopy(job(ns)["intent"]),
        "assistance": deepcopy(assistance(ns)),
        "native_sent": len(native_sent(ns)),
    }
    for _ in range(15):
        ns.runner.tick()
        ns.page.wait_for_timeout(SAMPLE_INTERVAL * 1000)
    waited, held = job(ns), assistance(ns)
    country = [
        call
        for call in mutation_calls(ns).values()
        if call["tool"] == "browser_type" and call["field_hint"]["name"] == "Country"
    ]
    assert len(country) == 1 and country[0]["status"] == "unknown", country
    assert waited["native_handoff_runs"][-1]["semantic_unknown"] is True
    # The return is refused: Codex stays the stopped writer, nothing is adopted.
    assert waited["status"] == "needs_recheck"
    assert waited["reason"] == "assistance_return_unverified"
    assert held["status"] == "stopped" and held["active_writer"] == "codex"
    assert held["stop"]["stop_status"] == "stopped" and "outcome" not in held
    assert not script_writes_allowed(ns.worker.store.load())
    # The typing landed; readback settles only the script's own intent.
    assert waited["intent"] is None
    assert waited["action_resolutions"][-1]["intent_ref"] == country_intent["attempt_id"]
    state = ns.pipeline.snapshot()
    assert (state["status"], state["control"]) == ("needs_recheck", "paused")
    assert len(ns.requests) == 1 == len(ns.at_start)
    assert "review" not in ns.flow.actions
    after = {
        "page": counters(ns),
        "values": values(ns),
        "fills": len(fills(ns)),
        "intent": waited["intent"],
        "assistance": held,
        "native_sent": len(native_sent(ns)),
    }
    assert after == before
    assert before["values"]["country"] == FACTS["Country"]
    assert before["values"]["phone"] == "" and before["values"]["region"] == ""
    assert before["page"]["submits"] == 0
    # One native type, never replayed; no script refill of Country after the stop.
    assert len(codex_types(ns)) == 1
    assert [row["field"] for row in ns.writes if row["writer"] == "script"] == [
        "Email",
        "Country",
    ]
    one_page(ns)
    isolated_network(ns)
    single_writer(ns)


def native_call_rows(ns):
    return sorted((key, call["status"]) for key, call in mutation_calls(ns).items())


@pytest.mark.parametrize("native_chain", [case("chain")], indirect=True)
def test_native_chain_lost_outcome_save_resaves_same_report_after_continue(
    native_chain, monkeypatch
):
    ns = native_chain
    first_stop(ns)
    store = ns.worker.store
    save, failure = store.save, []

    def lose_outcome_save(state):
        attempted = (state["jobs"][0].get("assistance") or {}).get("outcome")
        if attempted and attempted["kind"] == "filling_complete" and not failure:
            failure.append(deepcopy(attempted))
            raise OSError("synthetic outcome checkpoint write failure")
        return save(state)

    monkeypatch.setattr(store, "save", lose_outcome_save)
    # The second native takeover completes, but its filling_complete save is lost.
    drive(ns, lambda: bool(failure) or stalled(ns) or bool(peer_failures(ns)), timeout=60)
    assert failure and failure[0]["kind"] == "filling_complete", peer_failures(ns)
    monkeypatch.setattr(store, "save", save)
    drive(ns, lambda: ns.pipeline.snapshot()["status"] != "filling")
    for _ in range(5):
        ns.runner.tick()
        ns.page.wait_for_timeout(25)
    lost = assistance(ns)
    assert lost["status"] == "stopped" and lost["generation"] == 2
    assert "outcome" not in lost and lost["report"]["claimed"]["status"] == "ready_for_review"
    assert job(ns)["status"] != "ready_for_review"
    assert ns.pipeline.snapshot()["control"] == "paused"
    before = {
        "page": counters(ns),
        "values": values(ns),
        "fills": len(fills(ns)),
        "native": native_call_rows(ns),
        "native_sent": len(native_sent(ns)),
        "starts": [row["request_id"] for row in ns.at_start],
        "requests": list(ns.requests),
    }
    assert before["values"]["region"] == FACTS["Region"]

    # One Continue through the named Pipeline control re-saves the same verified report.
    ns.pipeline.continue_current(request_id="continue-after-lost-save")
    drive(
        ns,
        lambda: bool(assistance(ns).get("outcome")) or job(ns)["status"] == "needs_input",
        timeout=30,
    )
    resaved = assistance(ns)
    outcome = resaved["outcome"]
    assert resaved["status"] == "released" and resaved["generation"] == 2
    assert outcome["kind"] == "filling_complete"
    assert outcome["report_sha256"] == failure[0]["report_sha256"]
    assert outcome["stop_request_id"] == failure[0]["stop_request_id"]
    assert outcome["attributed_fields"] == failure[0]["attributed_fields"]
    assert resaved["report"]["claimed_sha256"] == lost["report"]["claimed_sha256"]
    assert job(ns)["status"] == "ready_for_review" and not job(ns).get("manual_submission")
    drive(ns, lambda: bool(job(ns).get("handed_off")) or stalled(ns))
    assert job(ns)["handoff"]["source"] == "automatic_submit_wait"
    assert ns.pipeline.snapshot()["status"] == "ready_for_review"
    after = {
        "page": counters(ns),
        "values": values(ns),
        "fills": len(fills(ns)),
        "native": native_call_rows(ns),
        "native_sent": len(native_sent(ns)),
        "starts": [row["request_id"] for row in ns.at_start],
        "requests": ns.requests,
    }
    # No refill, re-upload, new native call or new takeover.
    assert after == before
    assert after["page"]["submits"] == 0 and after["page"]["files"] == 1
    one_page(ns)
    isolated_network(ns)
    single_writer(ns)
