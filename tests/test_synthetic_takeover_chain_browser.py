"""MC-09 slice C: the takeover chain on one real loopback Lever-shaped page.

Real mail intake, Pipeline (background thread), WorkerService, ApplicationRunner
ticks and headless Chromium. The native client and the Codex turn are scripted:
the scripted turn applies its effect to the original page the way native
``browser_type`` insert_text does (focus and insert, no pointer), then emits the
structured report. Zero model calls; final Submit stays manual.
"""

import base64
import hashlib
import json
import os
import threading
import time
from copy import deepcopy
from dataclasses import replace
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import SimpleNamespace

import pytest
from synthetic_ats_material_context import supply_synthetic_material_context
from test_application_intake import message
from test_application_intake import page as captured_page
from test_application_pipeline import Flow

from career_evidence_graph import cua_driver, hosted_ats
from career_evidence_graph.application_codex_assist import AssistRunProgress
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
from career_evidence_graph.cua_driver import NATIVE_HANDOFF_PROTOCOL, NATIVE_HANDOFF_TOOLS
from career_evidence_graph.worker_process_identity import process_identity

pytestmark = pytest.mark.worker_browser

MAIL_URL = "https://www.linkedin.com/jobs/view/10001"
JOB_URL = "https://jobs.lever.co/synthetic-1/00000000-0000-0000-0000-000000000001"
DOCUMENT_URL = JOB_URL + "/apply"
FACTS = {
    "Email": "synthetic@example.invalid",
    "Country": "Switzerland",
    "Phone": "+41 44 000 00 00",
    "Region": "Zurich",
}


def covered_combobox(name, options):
    """An editable Lever-style text combobox partly under a transparent pointer-blocking strip.

    Like a sticky banner overlapping part of the input, the strip covers the input's
    centre (Playwright's click point) but not its full bounds, so the box itself is
    still visible to a native page snapshot.
    """
    key = name.lower()
    items = "".join(f'<li role="option">{option}</li>' for option in options)
    return f"""<div class="select">
<label id="{key}-label">{name}</label>
<span style="position:relative;display:inline-block">
<input id="{key}" name="{key}" type="text" role="combobox" autocomplete="off"
  aria-labelledby="{key}-label" aria-autocomplete="list" aria-controls="{key}-options"
  aria-expanded="false" aria-required="true" style="width:240px">
<div class="cover" style="position:absolute;top:0;bottom:0;left:30%;width:40%;z-index:9"></div>
</span>
<span class="select__single-value"></span>
<ul id="{key}-options" role="listbox" hidden>{items}</ul></div>"""


HTML = (
    """<!doctype html><title>Synthetic - Engineer</title><link rel="icon" href="data:,">
<h1>Engineer</h1>
<form id="application-form" method="post" action="/submit">
<label>Resume/CV *<input id="resume" name="resume" type="file" required></label>
<label>Email <input id="email" name="email" type="email"></label>
"""
    + covered_combobox("Country", ["Switzerland", "Germany"])
    + """
<label>Phone <input id="phone" name="phone" type="tel"></label>
"""
    + covered_combobox("Region", ["Zurich", "Geneva"])
    + """
<button type="submit">Submit</button></form>
<script>
window.__tomorrowstarMaterialDocument=crypto.randomUUID();
window.inputs={}; window.selections={}; window.submits=0; window.files=0;
document.querySelector('form').addEventListener('submit',e=>{window.submits++;e.preventDefault();});
document.querySelector('#resume').addEventListener('change',()=>window.files++);
for (const box of document.querySelectorAll('input')) {
  box.addEventListener('input',()=>{window.inputs[box.id]=(window.inputs[box.id]||0)+1;});
}
// Commit only an exact option match typed into the empty box.
for (const box of document.querySelectorAll('[role=combobox]')) {
  const root=box.closest('.select'), list=root.querySelector('[role=listbox]');
  box.addEventListener('input',()=>{
    const match=[...list.querySelectorAll('[role=option]')].find(o=>o.textContent===box.value);
    if(!match){list.hidden=!box.value;return;}
    window.selections[box.id]=(window.selections[box.id]||0)+1;
    root.querySelector('.select__single-value').textContent=match.textContent;
    list.hidden=true;
  });
}
</script>"""
).encode()


def sha(value):
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def report(status, field_id, next_field=None, summary="Selected"):
    claimed = {
        "status": status,
        "summary": summary,
        "unresolved_action_ids": [],
        "fields": [{"field_id": field_id, "state": "filled"}],
    }
    if next_field is not None:
        claimed["next_step"] = {"kind": "return_to_script", "field_id": next_field}
    return {
        "protocol": "assistance-report/v1",
        "request_id": "report-native-run",
        "native_turn_id": "native-turn",
        "received_at": time.time(),
        "claimed": claimed,
        "claimed_sha256": sha(claimed),
    }


class NativeClient:
    """Fake native session (shape of test_worker_native_takeover.py native_page)."""

    native_session = True
    failed = False
    process = SimpleNamespace(poll=lambda: None)

    def __init__(self, executable, driver_sha256):
        self.driver_executable, self.driver_sha256 = executable, driver_sha256
        self.handoff_active = False
        self.reclaimed = []

    def resume_after_handoff(self, *, pump):
        self.reclaimed.append(time.time())
        self.handoff_active = False


class Cua:
    """Owner surface the runner uses: page creation, owner reads, native scope, review."""

    def __init__(self, client):
        self.client = client
        self.reviewed = []

    def new_page(self, context, *, keep_visible):
        return context.new_page()

    def observe_owner(self, *, pump):
        return {"status": "accepted"}

    def native_page_scope(self, original, *, pump):
        process = process_identity(os.getpid())
        return {
            "target_id": "native-target",
            "tab_id": "native-tab",
            "cdp_target_id": "cdp-target",
            "binding_generation": 0,
            "tab_generation": 0,
            "process_fingerprint": {
                "pid": process["pid"],
                "start_time": 42,
                "executable": process["executable"],
            },
            "process_identity": process,
            "application_ref_digest": "",
        }

    def review(self, page, *, pump):
        self.reviewed.append(page)


class ScriptedCodex:
    """Scripted Adapter: one planned turn per start; effects land on the original page."""

    def __init__(self, chain, turns):
        self.chain, self.turns = chain, list(turns)
        self.starts, self.stops, self.deliveries, self.at_start = [], [], [], []
        self.current = None

    def start_takeover(self, original, **kwargs):
        turn = self.turns.pop(0)
        self.starts.append(kwargs["request_id"])
        self.at_start.append(
            {
                "job": deepcopy(self.chain.worker.store.load()["jobs"][0]),
                "pipeline": self.chain.pipeline.snapshot(),
                "page": counters(self.chain),
                "values": values(self.chain),
            }
        )
        self.deliveries.append(deepcopy(kwargs["delivery"]))
        kwargs["before_yield"](
            {
                "application_ref_digest": digest(original),
                "scope": kwargs["native_scope"],
                "request_id": kwargs["request_id"],
            }
        )
        kwargs["after_yield"](
            {"handoff_id": "native-run", "generation": 1, "local_tools_drained": True}
        )
        client = self.chain.client
        client.handoff_active = True
        records = []
        for sequence, (name, value) in enumerate(turn["types"], 1):
            call = {
                "call_id": f"native-type-{name.lower()}",
                "tool": "browser_type",
                "arguments_digest": "c" * 64,
                "status": "awaiting_host",
                "generation": 1,
                "sequence": sequence,
                "mutation": True,
                "semantic_verified": False,
                "scope": kwargs["native_scope"],
                "native_ref": f"native-ref-{name.lower()}",
                "field_hint": {"role": "combobox", "name": name},
                "text_sha256": hashlib.sha256(value.encode()).hexdigest(),
            }
            assert kwargs["before_native_call"](call)
            # Native browser_type insert_text: CDP focus and insert, no hit test.
            state = self.chain.worker.store.load()
            self.chain.writes.append(
                {"writer": "codex", "field": name, "script": script_writes_allowed(state)}
            )
            if turn.get("lands", True):
                self.chain.page.locator(f"#{name.lower()}").focus()
                self.chain.page.keyboard.insert_text(value)
            status = turn.get("final_status", {}).get(call["call_id"], "observed")
            records.append({**call, "status": status})
        unknown = any(row["status"] == "unknown" for row in records)
        kwargs["after_yield"](
            {
                "handoff_id": "native-run",
                "generation": 1,
                "revoked": True,
                "return_ready": not unknown,
                "local_tools_drained": True,
                "active_calls": 0,
                "calls": records,
            }
        )
        self.current = turn["report"]()
        return SimpleNamespace(run_id=f"adapter-native-run-{len(self.starts)}")

    def progress(self, run_id):
        return AssistRunProgress(
            run_id=run_id,
            status="ready",
            tools_revoked=True,
            native_turn_id="native-turn",
            native_turn_status="completed",
            report=deepcopy(self.current),
        )

    def stop(self, run_id, *, request_id):
        self.stops.append(request_id)
        return AssistRunProgress(
            run_id=run_id,
            status="stopped",
            tools_revoked=True,
            local_tools_drained=True,
            process_stopped=True,
            native_turn_id="native-turn",
            native_turn_status="completed",
            stop_status="stopped",
            report=deepcopy(self.current),
        )

    def service_readonly(self):
        return None


def _until(predicate, timeout=10.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        value = predicate()
        if value:
            return value
        time.sleep(0.01)
    pytest.fail("condition not reached")


@pytest.fixture
def chain(tmp_path, monkeypatch):
    """current_pipeline-style intake → prepare harness with a native policy and a real page."""
    from playwright.sync_api import sync_playwright

    monkeypatch.setenv("PLAYWRIGHT_BROWSERS_PATH", "0")
    executable = tmp_path / "native-driver"
    executable.write_bytes(b"synthetic reviewed native driver")
    driver_sha256 = hashlib.sha256(executable.read_bytes()).hexdigest()
    monkeypatch.setattr(cua_driver, "_NATIVE_HANDOFF_DRIVER_SHA256", driver_sha256)
    policy = {
        "protocol": NATIVE_HANDOFF_PROTOCOL,
        "driver_sha256": driver_sha256,
        "tools": list(NATIVE_HANDOFF_TOOLS),
        "type_mode": "insert_text",
    }
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
            self.send_header("Content-Length", str(len(HTML)))
            self.end_headers()
            self.wfile.write(HTML)

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
    blocked, fetched = [], []
    try:
        pipeline.start(request_id="chain-start")
        _until(lambda: pipeline.snapshot()["status"] == "filling")
        assert worker.store.load()["jobs"][0]["job_url"] == JOB_URL
        for question, value in FACTS.items():
            worker.store.answers.put_answer(
                {"question": question, "value": value, "scope": {}, "state": "confirmed"}
            )
        supply_synthetic_material_context(worker, monkeypatch)
        start_run(worker.store)
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True, channel="chromium")
            try:
                context = browser.new_context(offline=True)
                # Production's worker context default (application_worker_browser main).
                context.set_default_timeout(4000)

                client = NativeClient(executable, driver_sha256)
                cua = Cua(client)
                runner = ApplicationRunner(
                    worker.store, context, cua=cua, native_assistance_policy=policy
                )

                def isolated(route):
                    """Production's live guard decides; its fetch is served by the loopback."""

                    class Loopback:
                        request = route.request

                        def fetch(self, **options):
                            assert options == {
                                "max_redirects": 0,
                                "max_retries": 0,
                                "timeout": 10000,
                            }
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

                    runner._live_guard(Loopback())

                # Registered after the runner: this wrapper of its own guard runs first,
                # so no request leaves the loopback receiver.
                context.route("**/*", isolated)
                ns = SimpleNamespace(
                    pipeline=pipeline,
                    flow=flow,
                    worker=worker,
                    runner=runner,
                    context=context,
                    client=client,
                    cua=cua,
                    requests=requests,
                    received=received,
                    blocked=blocked,
                    fetched=fetched,
                    writes=[],
                    trace=[],
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
                            "handoff_active": client.handoff_active,
                        }
                    )
                    return hosted_fill(page, question, value)

                monkeypatch.setattr(hosted_ats, "fill", script_fill)
                yield ns
            finally:
                browser.close()
    finally:
        pipeline.close()
        intake.close()
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def job(ns):
    return ns.worker.store.load()["jobs"][0]


def assistance(ns):
    return job(ns).get("assistance") or {}


def trace_row(ns):
    state = ns.worker.store.load()
    current = state["jobs"][0]
    held = current.get("assistance") or {}
    codex = ns.client.handoff_active or (
        held.get("active_writer") == "codex"
        and held.get("status") == "claimed"
        and "stop" not in held
    )
    return {
        "job": (current["status"], current.get("reason")),
        "assistance": (held.get("generation"), held.get("status"), held.get("active_writer")),
        "script": script_writes_allowed(state),
        "codex": codex,
        "pipeline": ns.pipeline.snapshot()["status"],
    }


def drive(ns, predicate, *, timeout=60):
    """Ordinary runner ticks on the real page; one single-writer trace row per tick."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        row = trace_row(ns)
        if not ns.trace or ns.trace[-1] != row:
            ns.trace.append(row)
        assert not (row["script"] and row["codex"]), row
        if predicate():
            return
        ns.runner.tick()
        if ns.page is None:
            ns.page = ns.runner.pages.get(job(ns)["application_id"])
        if ns.page is not None:
            ns.page.wait_for_timeout(SAMPLE_INTERVAL * 1000)
        else:
            time.sleep(SAMPLE_INTERVAL)
    pytest.fail(f"chain did not reach its observation: {trace_row(ns)} {ns.trace[-5:]}")


def counters(ns):
    return ns.page.evaluate(
        "({inputs:{...window.inputs},selections:{...window.selections},"
        "submits:window.submits,files:window.files})"
    )


def values(ns):
    return {
        key: ns.page.locator(f"#{key}").input_value()
        for key in ("email", "country", "phone", "region")
    }


def fills(ns):
    return [
        row
        for row in job(ns)["observations"]
        if row.get("action") == "fill" and row.get("verified") is True
    ]


FIRST_TURN = {
    "types": [("Country", FACTS["Country"])],
    "report": lambda: report("blocked_segment_resolved", "country", next_field="phone"),
}
SECOND_TURN = {
    "types": [("Region", FACTS["Region"])],
    "report": lambda: report("ready_for_review", "region", summary="Region selected"),
}


def started(codex, count):
    return lambda: len(codex.starts) >= count


def waiting(ns):
    return job(ns)["status"] in {"needs_recheck", "needs_input"} and (
        "stop" in assistance(ns) or not assistance(ns)
    )


def first_return(ns, codex):
    """S1/S2 steps 1-2: real script stop, auto dispatch, Codex resolves, return to script."""
    drive(ns, lambda: started(codex, 1)() or waiting(ns))
    assert codex.starts, ns.trace
    at = codex.at_start[0]
    stopped, dispatched = at["job"], at["job"]["assistance"]
    intent = stopped["intent"]
    # The script's own fill of the covered box could not land: unknown, intent kept.
    assert (stopped["status"], stopped["reason"]) == ("needs_recheck", "browser_result_unknown")
    assert intent["action"] == "fill" and intent["expected_value"] == FACTS["Country"]
    assert intent["dispatch_state"] == "sent" and intent["executor"] == "playwright"
    assert intent["route_reason"] == "supported_dom_field"
    assert at["values"]["country"] == "" and at["page"]["selections"] == {}
    assert at["values"]["email"] == FACTS["Email"]
    # The Pipeline auto-dispatched exactly one takeover; the runner started that claim.
    assert dispatched["generation"] == 1 and dispatched["status"] == "claimed"
    assert dispatched["active_writer"] == "codex"
    assert dispatched["dispatch"]["blocker"]["code"] == "browser_result_unknown"
    assert dispatched["dispatch"]["blocker"]["field_id"] == intent["field_id"]
    assert dispatched["dispatch"]["pending_intent_ref"] == digest(intent)
    assert at["pipeline"]["takeover_request"]["request_id"] == dispatched["claim_request_id"]
    assert codex.starts == [dispatched["claim_request_id"]] == ns.requests
    assert codex.deliveries[0]["next_step"]["kind"] == "reconcile_pending_actions"
    return intent


def test_chain_two_auto_takeovers_return_script_fill_and_manual_submit_wait(chain):
    ns = chain
    codex = ns.runner.codex_assist = ScriptedCodex(ns, [FIRST_TURN, SECOND_TURN])
    country_intent = first_return(ns, codex)
    returned = job(ns)
    first = returned["assistance"]
    outcome = first["outcome"]
    # Stop, drain and reclaim happened before the read-only readback and adoption.
    assert first["status"] == "released" and first["active_writer"] == "script"
    assert first["stop"]["reason"] == "native_turn_completed"
    assert first["stop"]["stop_status"] == "stopped"
    assert codex.stops == [first["stop"]["request_id"]]
    assert len(ns.client.reclaimed) == 1 and ns.client.handoff_active is False
    assert (
        first["stop"]["observed_at"]
        <= outcome["session_reclaimed_at"]
        <= outcome["page_verification"]["at"]
        <= outcome["adopted_at"]
    )
    assert outcome["kind"] == "script_checkpoint" and outcome["return_count"] == 1
    assert returned["assistance_return_count"] == 1
    assert outcome["report_sha256"] == sha(first["report"])
    assert outcome["attributed_fields"] == [
        {"field_id": "country", "call_id": "native-type-country"}
    ]
    # The pending script intent was settled by readback, never replayed.
    assert returned["intent"] is None
    resolution = returned["action_resolutions"][-1]
    assert resolution["intent_ref"] == country_intent["attempt_id"]
    assert resolution["conclusion"] == "current_matches"
    assert resolution["source"] == "retained_original_page"
    assert values(ns)["country"] == FACTS["Country"] and values(ns)["phone"] == ""

    # 3. The script itself continues on the same page and fills Phone.
    phone = outcome["checkpoint_field_id"]
    drive(
        ns,
        lambda: any(row.get("field_id") == phone for row in fills(ns)) or waiting(ns),
    )
    phone_fill = next(row for row in fills(ns) if row.get("field_id") == phone)
    assert phone_fill["executor"] == "playwright" and phone_fill["adopted"] is True
    assert phone_fill["at"] > outcome["adopted_at"]
    assert values(ns)["phone"] == FACTS["Phone"]

    # 4. The covered Region box after the return is a second real unknown stop:
    #    one more automatic takeover, generation 2.
    drive(ns, lambda: started(codex, 2)() or waiting(ns))
    assert len(codex.starts) == 2, ns.trace
    second_at = codex.at_start[1]["job"]
    second = second_at["assistance"]
    assert (second_at["status"], second_at["reason"]) == ("needs_recheck", "browser_result_unknown")
    assert second_at["intent"]["expected_value"] == FACTS["Region"]
    assert second["generation"] == 2 and second["status"] == "claimed"
    assert second["dispatch"]["pending_intent_ref"] == digest(second_at["intent"])
    assert second["claim_request_id"] != first["claim_request_id"]
    assert codex.starts == ns.requests == [first["claim_request_id"], second["claim_request_id"]]
    assert codex.deliveries[1]["next_step"]["kind"] == "complete_remaining_fields"

    # 5. Codex finishes the form; the verified outcome is filling_complete.
    drive(ns, lambda: bool(assistance(ns).get("outcome")) or waiting(ns))
    completed = job(ns)
    final = completed["assistance"]
    assert final["generation"] == 2 and final["status"] == "released"
    assert final["outcome"]["kind"] == "filling_complete"
    assert final["outcome"]["attributed_fields"] == [
        {"field_id": "region", "call_id": "native-type-region"}
    ]
    assert completed["status"] == "ready_for_review" and completed["intent"] is None
    assert [row["generation"] for row in completed["assistance_history"]] == [1]
    assert values(ns) == {
        "email": FACTS["Email"],
        "country": FACTS["Country"],
        "phone": FACTS["Phone"],
        "region": FACTS["Region"],
    }

    # 6. The Pipeline hands the original page over for the manual Submit wait.
    drive(ns, lambda: ns.pipeline.snapshot()["status"] == "ready_for_review")
    drive(ns, lambda: bool(job(ns).get("handed_off")) or waiting(ns))
    for _ in range(10):
        ns.runner.tick()
        ns.page.wait_for_timeout(25)
    state, final_job = ns.pipeline.snapshot(), job(ns)
    assert state["control"] == "paused" and state["notification"]["status"] == "ready_for_review"
    assert ns.flow.actions.count("review") == 1
    assert ns.cua.reviewed == [ns.page]
    handoff = final_job["handoff"]
    assert final_job["handed_off"] is True and handoff["status"] == "complete"
    assert handoff["source"] == "automatic_submit_wait" and handoff["actor"] == "system"
    assert handoff["human_reviewed"] is False
    assert final_job["status"] == "ready_for_review" and not final_job.get("manual_submission")
    assert final_job["assistance"]["outcome"] == final["outcome"]
    assert state["items"][0]["status"] != "completed"

    # Exactly one page, no Submit, no request beyond the loopback document read.
    page_counters = counters(ns)
    assert page_counters["submits"] == 0 and page_counters["files"] == 1
    assert page_counters["selections"] == {"country": 1, "region": 1}
    assert ns.context.pages == [ns.page]
    assert ns.runner.pages[final_job["application_id"]] is ns.page
    assert ns.received == [("GET", "/application")] and ns.blocked == []
    assert ns.fetched == [("GET", DOCUMENT_URL)]
    assert codex.starts == ns.requests and len(ns.requests) == 2

    # Single writer per tick and per write: never script and Codex at once.
    assert all(not (row["script"] and row["codex"]) for row in ns.trace)
    writers = [(row["writer"], row["field"]) for row in ns.writes]
    assert writers == [
        ("script", "Email"),
        ("script", "Country"),
        ("codex", "Country"),
        ("script", "Phone"),
        ("script", "Region"),
        ("codex", "Region"),
    ]
    for row in ns.writes:
        if row["writer"] == "script":
            assert row["script"] is True and row["handoff_active"] is False, row
        else:
            assert row["script"] is False, row


@pytest.mark.parametrize("lands", [True, False], ids=["effect_landed", "effect_lost"])
def test_chain_fault_unknown_tool_result_refuses_return_and_waits_without_replay(chain, lands):
    ns = chain
    unknown_turn = {
        **FIRST_TURN,
        "final_status": {"native-type-country": "unknown"},
        "lands": lands,
    }
    codex = ns.runner.codex_assist = ScriptedCodex(ns, [unknown_turn, SECOND_TURN])
    country_intent = first_return(ns, codex)
    drive(ns, lambda: ns.pipeline.snapshot()["status"] != "filling")
    before = {
        "page": counters(ns),
        "values": values(ns),
        "fills": len(fills(ns)),
        "intent": deepcopy(job(ns)["intent"]),
        "assistance": deepcopy(assistance(ns)),
    }
    for _ in range(15):
        ns.runner.tick()
        ns.page.wait_for_timeout(SAMPLE_INTERVAL * 1000)
    waited, held = job(ns), assistance(ns)
    # The return is refused: Codex stays the stopped writer, nothing is adopted.
    assert waited["status"] == "needs_recheck"
    assert waited["reason"] == (
        "assistance_return_unverified" if lands else "assistance_pending_intent"
    )
    assert held["status"] == "stopped" and held["active_writer"] == "codex"
    assert held["stop"]["stop_status"] == "stopped" and "outcome" not in held
    assert not script_writes_allowed(ns.worker.store.load())
    assert waited["native_handoff_runs"][-1]["semantic_unknown"] is True
    if lands:
        # Readback shows the expected value, so only the script's own intent settles.
        assert waited["intent"] is None
        assert waited["action_resolutions"][-1]["intent_ref"] == country_intent["attempt_id"]
    else:
        assert waited["intent"] == country_intent
    # The Pipeline waits; no second takeover, replay, refill or review.
    state = ns.pipeline.snapshot()
    assert (state["status"], state["control"]) == ("needs_recheck", "paused")
    assert ns.requests == codex.starts and len(codex.starts) == 1
    assert "review" not in ns.flow.actions
    after = {
        "page": counters(ns),
        "values": values(ns),
        "fills": len(fills(ns)),
        "intent": waited["intent"],
        "assistance": held,
    }
    assert after == before
    assert before["values"]["country"] == (FACTS["Country"] if lands else "")
    assert before["values"]["phone"] == "" and before["values"]["region"] == ""
    assert ns.context.pages == [ns.page] and before["page"]["submits"] == 0
    assert all(not (row["script"] and row["codex"]) for row in ns.trace)


def native_calls(ns):
    runs = job(ns).get("native_handoff_runs") or []
    return [
        (run["request_id"], call["call_id"], call["status"])
        for run in runs
        for call in ((run["events"][-1].get("receipt") or {}).get("calls") or [])
    ]


def test_chain_fault_lost_outcome_save_resaves_same_report_after_continue(chain, monkeypatch):
    ns = chain
    codex = ns.runner.codex_assist = ScriptedCodex(ns, [FIRST_TURN, SECOND_TURN])
    first_return(ns, codex)
    store = ns.worker.store
    save, failure = store.save, []

    def lose_outcome_save(state):
        attempted = (state["jobs"][0].get("assistance") or {}).get("outcome")
        if attempted and attempted["kind"] == "filling_complete" and not failure:
            failure.append(deepcopy(attempted))
            raise OSError("synthetic outcome checkpoint write failure")
        return save(state)

    monkeypatch.setattr(store, "save", lose_outcome_save)
    stop = codex.stop

    def stop_after_reclaim(run_id, *, request_id):
        result = stop(run_id, request_id=request_id)
        if len(ns.client.reclaimed) >= 2:
            # The real Adapter cannot re-read a handoff the Worker took back.
            return replace(result, local_tools_drained=False)
        return result

    codex.stop = stop_after_reclaim
    # The second takeover completes, but its filling_complete outcome save is lost.
    drive(ns, lambda: bool(failure) or waiting(ns))
    assert failure and failure[0]["kind"] == "filling_complete"
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
        "native": native_calls(ns),
        "starts": list(codex.starts),
        "requests": list(ns.requests),
    }
    assert before["values"]["region"] == FACTS["Region"]

    # One Continue through the named Pipeline control re-saves the same verified report.
    ns.pipeline.continue_current(request_id="continue-after-lost-save")
    drive(
        ns,
        lambda: bool(assistance(ns).get("outcome")) or job(ns)["status"] == "needs_input",
        timeout=20,
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
    drive(ns, lambda: bool(job(ns).get("handed_off")) or waiting(ns))
    assert job(ns)["handoff"]["source"] == "automatic_submit_wait"
    assert ns.pipeline.snapshot()["status"] == "ready_for_review"
    # No refill, re-upload, new native call or new takeover.
    after = {
        "page": counters(ns),
        "values": values(ns),
        "fills": len(fills(ns)),
        "native": native_calls(ns),
        "starts": codex.starts,
        "requests": ns.requests,
    }
    assert after == before
    assert after["page"]["submits"] == 0 and after["page"]["files"] == 1
    assert ns.context.pages == [ns.page]
    assert all(not (row["script"] and row["codex"]) for row in ns.trace)
