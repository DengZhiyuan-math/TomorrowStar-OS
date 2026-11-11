"""MC-07 return to script and filling completion through the real native proxy.

Controlled app-server peer, zero model calls. The peer performs real native
actions on a synthetic Lever-shaped page with a custom combobox that the form
runner does not recognise, then emits the model's final structured message
before turn/completed. Worker stop, drain, reclaim, read-only page check and
adoption are production code. Final Submit stays manual.
"""

import os
import re
import time
import traceback
from copy import deepcopy
from dataclasses import asdict
from pathlib import Path
from types import SimpleNamespace

import pytest
from synthetic_ats_material_context import supply_synthetic_material_context
from test_single_application_worker import single_worker as single_worker
from test_worker_codex_assistance import retained_assistance_page as retained_assistance_page
from test_worker_native_handoff_browser import drive_until, page_identity, read_peer
from test_worker_native_handoff_browser import native_handoff as native_handoff

from career_evidence_graph import application_form_runner
from career_evidence_graph.application_form_state import SAMPLE_INTERVAL

pytestmark = [
    pytest.mark.worker_browser,
    pytest.mark.skipif(
        os.environ.get("TS_CUA_NATIVE_TEST") != "1", reason="Explicit native Cua opt-in"
    ),
]

PEER = Path(__file__).with_name("native_return_peer.py")
# single_worker's synthetic Lever job; the document is supplied from loopback.
JOB_URL = "https://jobs.lever.co/synthetic/00000000-0000-0000-0000-000000000001"
EMAIL = "synthetic@example.invalid"
PHONE = "+41 44 000 00 00"
COUNTRY = "Switzerland"
MUTATIONS = {"browser_click", "browser_type", "browser_deliver_material"}
WAITING = {"needs_recheck", "needs_input"}
CONTROLLER = {"controller": "synthetic-controller"}


def return_html(effect):
    slow_phone = (
        """
document.querySelector('#phone').addEventListener('input',()=>{
  console.log('native-input-handler-start:'+Date.now());
  const until=Date.now()+8000;while(Date.now()<until){}
  console.log('native-input-handler-end:'+Date.now());
});"""
        if effect == "pending_call"
        else ""
    )
    # The complex control is an autocomplete text combobox outside
    # form#application-form: the Lever form reader enumerates only that form,
    # so the script never identifies or fills it (an in-form text combobox is
    # enumerated, routed to Playwright fill and read back as empty, so the
    # script would refill it after a return). The native policy admits typing
    # the confirmed Country fact into it; the page commits an exact option
    # match into the form's hidden value. Generic page reads see it document-wide.
    return (
        """<!doctype html><title>Synthetic - Engineer</title>
<link rel="icon" href="data:,"><h1>Engineer</h1>
<form id="application-form" method="post" action="/submit">
<label>Resume/CV <input id="resume" name="resume" type="file" accept=".pdf"></label>
<label>Email <input id="email" name="email" type="email"></label>
<input id="country-value" name="country" type="hidden">
<label>Phone <input id="phone" name="phone" type="tel"></label>
<button type="submit">Submit</button></form>
<div class="country-widget">
<span id="country-label">Country</span>
<input id="country" type="text" role="combobox" autocomplete="off"
  aria-labelledby="country-label" aria-autocomplete="list" aria-controls="country-options"
  aria-expanded="false" aria-required="true">
<ul id="country-options" role="listbox" aria-labelledby="country-label" hidden>
<li id="country-ch" role="option" aria-selected="false">Switzerland</li>
<li id="country-de" role="option" aria-selected="false">Germany</li></ul></div>
<script>
window.__tomorrowstarMaterialDocument=crypto.randomUUID();
window.nativeInputEvents=0; window.nativeSubmitEvents=0;
window.comboboxOpens=0; window.comboboxSelections=0; window.fileChangeEvents=0;
for (const id of ['email','phone'])
  document.getElementById(id).addEventListener('input',()=>window.nativeInputEvents++);
document.querySelector('form').addEventListener('submit',()=>window.nativeSubmitEvents++);
document.querySelector('#resume').addEventListener('change',()=>window.fileChangeEvents++);
const box=document.querySelector('#country'), list=document.querySelector('#country-options');
const show=open=>{
  if(open && list.hidden) window.comboboxOpens++;
  list.hidden=!open; box.setAttribute('aria-expanded',String(open));
};
// Commit only an exact option match typed into the empty box.
box.addEventListener('input',()=>{
  const match=[...list.querySelectorAll('[role=option]')].find(o=>o.textContent===box.value);
  if(!match) { show(Boolean(box.value)); return; }
  window.comboboxSelections++;
  document.querySelector('#country-value').value=match.textContent;
  match.setAttribute('aria-selected','true');
  show(false);
});
"""
        + slow_phone
        + "\n</script>"
    ).encode()


def check_job_url(ns):
    assert ns.service.store.load()["jobs"][0]["job_url"] == JOB_URL


def prepare_page(ns):
    """Supply the Phone/Country facts and the job's resume before the immutable binding."""
    # This ATS-only job has no Flow delivery; the script's later fill reads it.
    # The service is per-test, so a plain setattr stands in for monkeypatch.
    supply_synthetic_material_context(ns.service, SimpleNamespace(setattr=setattr))
    for question, value in (("Phone", PHONE), ("Country", COUNTRY)):
        ns.service.store.answers.put_answer(
            {"question": question, "value": value, "scope": {}, "state": "confirmed"}
        )
    # The script's first pass on this page uploads the job's own resume through
    # its verified upload transaction and returns before any field fill.
    state = ns.service.store.load()
    ns.runner.process(state["jobs"][0], state["batch_id"])
    uploaded = ns.service.store.load()["jobs"][0]
    assert ns.runner.recovered_upload(uploaded), uploaded.get("reason")
    assert uploaded["status"] == "filling" and uploaded.get("intent") is None
    assert ns.page.locator("#email").input_value() == ""
    assert ns.page.locator("#phone").input_value() == ""
    # It then reaches the complex control: establish its real stable read-only
    # form snapshot (no fill), as a script tick would have.
    deadline = time.monotonic() + 5
    while True:
        state = ns.service.store.load()
        current = state["jobs"][0]
        observed = ns.runner.observe(ns.page, current)
        form_state = application_form_runner.capture(
            ns.runner, ns.page, current, state["batch_id"], observed
        )
        if form_state["parser"]["status"] == "stable":
            break
        assert time.monotonic() < deadline, form_state["parser"]
        ns.page.wait_for_timeout(SAMPLE_INTERVAL * 1000)
    assert "country" not in {field.get("question", "").casefold() for field in observed["fields"]}
    ns.extra_evidence["script_snapshot"] = deepcopy(observed["fields"])
    ns.extra_evidence["prepared_counters"] = counters_of(ns.page)


def case(effect):
    return pytest.param(
        {
            "effect": effect,
            "html": return_html(effect),
            "peer_source": PEER,
            "document_url": JOB_URL,
            "before_navigation": check_job_url,
            "before_request": prepare_page,
        },
        id=effect,
    )


def counters_of(page):
    return page.evaluate(
        "({input:window.nativeInputEvents,submit:window.nativeSubmitEvents,"
        "opens:window.comboboxOpens,selections:window.comboboxSelections,"
        "files:window.fileChangeEvents})"
    )


def job(h):
    return h.service.store.load()["jobs"][0]


def assistance(h):
    return job(h).get("assistance") or {}


def peer_failures(h):
    return [row for row in read_peer(h.runtime) if row["kind"] == "failure"]


def native_sent(h):
    return [
        row
        for row in read_peer(h.runtime)
        if row["kind"] == "native_sent" and row["request"].get("method") == "tools/call"
    ]


def mutation_calls(h):
    runs = job(h).get("native_handoff_runs") or []
    if not runs:
        return []
    calls = {}
    for event in runs[-1]["events"]:
        for call in (event.get("receipt") or {}).get("calls", []):
            if call.get("mutation"):
                calls[call["call_id"]] = call
    return list(calls.values())


def hosted_id(page, selector):
    marker = page.locator(selector).get_attribute("data-ts-worker-field")
    return re.sub(r"-\d+$", "", marker) if marker else None


def field_ids(page, selector, name):
    """A generic page read may use the DOM id; the script uses its hosted id."""
    return {name, hosted_id(page, selector)} - {None}


def drive_worker(h, predicate, *, timeout=45):
    """Run ordinary Worker ticks; record every writer transition for the single-writer check."""
    trace = h.extra_evidence.setdefault("writer_trace", [])
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        current = assistance(h)
        row = {
            "at": time.time(),
            "status": current.get("status"),
            "writer": current.get("active_writer"),
            "stop_status": (current.get("stop") or {}).get("stop_status"),
            "job_status": job(h)["status"],
        }
        if not trace or {k: v for k, v in trace[-1].items() if k != "at"} != {
            k: v for k, v in row.items() if k != "at"
        }:
            trace.append(row)
        if predicate():
            return
        h.runner.tick()
        h.page.wait_for_timeout(25)
    pytest.fail(
        f"Native return case did not reach its observation: {assistance(h)} {read_peer(h.runtime)}"
    )


def assert_single_writer(h):
    for row in h.extra_evidence.get("writer_trace", []):
        if row["writer"] == "script":
            assert row["status"] == "released" and row["stop_status"] == "stopped", row


def assert_no_native_after(h, at):
    late = [row for row in native_sent(h) if row["at"] > at]
    assert not late, late


def assert_adopted(h, kind):
    current = assistance(h)
    assert current["status"] == "released" and current["active_writer"] == "script"
    stop, report, outcome = current["stop"], current["report"], current["outcome"]
    assert stop["stop_status"] == "stopped" and stop["reason"] == "native_turn_completed"
    assert report["protocol"] == "assistance-report/v1"
    assert report["native_turn_id"] == "controlled-native-turn" == stop["native_turn_id"]
    assert outcome["protocol"] == "assistance-outcome/v1" and outcome["kind"] == kind
    assert re.fullmatch(r"[0-9a-f]{64}", outcome["report_sha256"])
    assert outcome["stop_request_id"] == stop["request_id"]
    assert (
        stop["observed_at"]
        <= outcome["session_reclaimed_at"]
        <= outcome["page_verification"]["at"]
        <= outcome["adopted_at"]
    )
    assert report["received_at"] <= outcome["adopted_at"]
    observed = {call["call_id"] for call in mutation_calls(h) if call["status"] == "observed"}
    assert outcome["attributed_fields"]
    assert {row["call_id"] for row in outcome["attributed_fields"]} <= observed
    assert_no_native_after(h, outcome["session_reclaimed_at"])
    assert_single_writer(h)
    return current


def attributed(outcome):
    return {row["field_id"] for row in outcome["attributed_fields"]}


def original_document(h):
    assert h.runner.pages[h.identifier] is h.page and h.context.pages == [h.page]
    assert page_identity(h.page) == h.original_page
    assert h.page.evaluate("window.nativeSubmitEvents") == 0
    assert h.received == [("GET", "/application")]


def record_waits(h):
    """Diagnostics only: keep the exception behind each production return wait."""
    wait = h.runner._assistance_wait
    rows = h.extra_evidence.setdefault("assistance_waits", [])

    def recorded(job, reason):
        rows.append({"reason": reason, "error": traceback.format_exc(), "at": time.time()})
        return wait(job, reason)

    h.runner._assistance_wait = recorded
    update = h.runner.update
    updates = h.extra_evidence.setdefault("waiting_updates", [])

    def recorded_update(*args, **changes):
        if changes.get("status") in WAITING:
            updates.append(
                {
                    "changes": {k: changes[k] for k in ("status", "reason") if k in changes},
                    "error": traceback.format_exc(),
                    "stack": traceback.format_stack(limit=8),
                    "at": time.time(),
                }
            )
        return update(*args, **changes)

    h.runner.update = recorded_update
    block = h.service.store.block_storage
    blocks = h.extra_evidence.setdefault("storage_blocks", [])

    def recorded_block():
        if len(blocks) < 20:
            blocks.append({"error": traceback.format_exc(), "at": time.time()})
        return block()

    h.service.store.block_storage = recorded_block
    stop = h.adapter.stop
    stops = h.extra_evidence.setdefault("adapter_stops", [])

    def recorded_stop(run_id, *, request_id):
        result = stop(run_id, request_id=request_id)
        if len(stops) < 20:
            stops.append({"request_id": request_id, "progress": asdict(result), "at": time.time()})
        return result

    h.adapter.stop = recorded_stop


def start(h, request_id):
    record_waits(h)
    started = h.runner.start_native_assistance(h.reference, request_id=request_id)
    h.extra_evidence["start_progress"] = asdict(started)
    return started


def report_kept(h, claimed_status):
    current = assistance(h)
    report = current.get("report")
    if report is not None:
        assert report["protocol"] == "assistance-report/v1"
        assert report["claimed"]["status"] == claimed_status
        return report
    rows = [
        row
        for row in job(h)["observations"]
        if row.get("action") == "assistance_report_not_adopted"
    ]
    assert len(rows) == 1, current
    return rows[0]


@pytest.mark.parametrize("native_handoff", [case("return_to_script")], indirect=True)
def test_real_native_complex_control_returns_to_script_then_script_fills_next_field(
    native_handoff,
):
    h = native_handoff
    start(h, "real-native-return")
    drive_worker(
        h,
        lambda: (
            bool(peer_failures(h))
            or assistance(h).get("status") == "released"
            or job(h)["status"] in WAITING
        ),
    )
    assert not peer_failures(h)
    current = assert_adopted(h, "script_checkpoint")
    outcome = deepcopy(current["outcome"])
    assert outcome["return_count"] == 1
    assert attributed(outcome) & field_ids(h.page, "#country", "country")
    assert current["report"]["claimed"]["status"] == "blocked_segment_resolved"
    assert current["report"]["claimed"]["next_step"]["field_id"] == "phone"
    # The DOM id maps to the script's own Phone question.
    assert outcome["checkpoint_field_id"] == hosted_id(h.page, "#phone") != "phone"
    assert h.page.locator("#country").input_value() == COUNTRY
    assert h.page.locator("#country-value").input_value() == COUNTRY
    assert h.page.locator("#phone").input_value() == ""
    sent_at_release = len(native_sent(h))
    # The script continues the same document and fills the next plain text field.
    phone = field_ids(h.page, "#phone", "phone")

    def phone_verified():
        # The form-state/v1 fill records its own adopted, read-back verified write.
        return [
            row
            for row in job(h)["observations"]
            if row.get("action") == "fill"
            and row.get("adopted") is True
            and row.get("verified") is True
            and row.get("executor") == "playwright"
            and row.get("field_id") in phone
        ]

    drive_worker(h, lambda: bool(phone_verified()) or job(h)["status"] in WAITING, timeout=60)
    assert h.page.locator("#phone").input_value() == PHONE
    verified = phone_verified()
    assert verified and not any(row["intent"].get("native_material") for row in verified)
    assert assistance(h)["outcome"] == outcome
    assert len(native_sent(h)) == sent_at_release
    assert_no_native_after(h, outcome["session_reclaimed_at"])
    assert_single_writer(h)
    counters = counters_of(h.page)
    # One native selection; the script never re-identifies the complex control.
    assert counters["selections"] == 1 and counters["submit"] == 0
    original_document(h)


@pytest.mark.parametrize("native_handoff", [case("filling_complete")], indirect=True)
def test_real_native_section_reaches_filling_complete_and_manual_submit_wait(native_handoff):
    h = native_handoff
    start(h, "real-native-complete")
    drive_worker(
        h,
        lambda: (
            bool(peer_failures(h))
            or assistance(h).get("outcome")
            and job(h)["status"] == "ready_for_review"
            or job(h)["status"] in WAITING
        ),
    )
    assert not peer_failures(h)
    current = assert_adopted(h, "filling_complete")
    outcome = deepcopy(current["outcome"])
    for selector, name in (("#country", "country"), ("#email", "email"), ("#phone", "phone")):
        assert attributed(outcome) & field_ids(h.page, selector, name), name
    assert h.page.locator("#email").input_value() == EMAIL
    assert h.page.locator("#phone").input_value() == PHONE
    counters = counters_of(h.page)
    calls = deepcopy(mutation_calls(h))
    # Ordinary ready ticks must use the verified outcome, never refill or downgrade it.
    for _ in range(10):
        h.runner.tick()
        h.page.wait_for_timeout(25)
    final = job(h)
    assert final["status"] == "ready_for_review"
    assert not final.get("manual_submission")
    assert final["status"] != "submitted"
    assert (final.get("assistance") or {}).get("outcome") == outcome
    assert counters_of(h.page) == counters and mutation_calls(h) == calls
    assert counters["submit"] == 0
    original_document(h)


@pytest.mark.parametrize(
    "native_handoff", [case("prose_only"), case("pending_call")], indirect=True
)
def test_real_native_success_prose_or_pending_call_never_completes(native_handoff):
    h = native_handoff
    started = start(h, "real-native-unverified")
    if h.effect == "pending_call":
        drive_until(
            h,
            started.run_id,
            lambda: any(
                row["text"].startswith("native-input-handler-start:") for row in h.console_events
            ),
        )
        (h.runtime / "release-report").write_text("report while the call is in flight\n")
    drive_worker(
        h,
        lambda: (
            bool(peer_failures(h))
            or assistance(h).get("outcome")
            or (assistance(h).get("stop") or {}).get("stop_status") == "stopped"
            and job(h)["status"] in WAITING
        ),
        timeout=60,
    )
    assert not peer_failures(h)
    for _ in range(5):
        h.runner.tick()
        h.page.wait_for_timeout(25)
    current = assistance(h)
    assert "outcome" not in current
    assert current["status"] != "released" and current["active_writer"] != "script"
    assert job(h)["status"] in WAITING
    if h.effect == "prose_only":
        assert current.get("report") is None
        assert not any(
            row.get("action") == "assistance_report_not_adopted" for row in job(h)["observations"]
        )
    else:
        report_kept(h, "ready_for_review")
        phone = [
            call
            for call in mutation_calls(h)
            if call["tool"] == "browser_type" and call["field_hint"]["name"] == "Phone"
        ]
        assert len(phone) == 1 and phone[0]["status"] == "unknown"
        assert job(h)["native_handoff_runs"][-1]["semantic_unknown"] is True
    assert_single_writer(h)
    original_document(h)


@pytest.mark.parametrize("native_handoff", [case("pause_during_report")], indirect=True)
def test_real_native_pause_during_report_keeps_history_only(native_handoff):
    h = native_handoff
    started = start(h, "real-native-pause-report")
    drive_until(
        h,
        started.run_id,
        lambda: any(row["kind"] in {"report_sent", "failure"} for row in read_peer(h.runtime)),
    )
    assert not peer_failures(h)
    for _ in range(3):
        # Let the Adapter receive the report for the still-active turn.
        h.extra_evidence.setdefault("report_progress", []).append(
            asdict(h.adapter.progress(started.run_id))
        )
        h.page.wait_for_timeout(25)
    h.service.request("pause", CONTROLLER)
    (h.runtime / "release-turn").write_text("pause already requested\n")
    drive_worker(
        h, lambda: (assistance(h).get("stop") or {}).get("stop_status") == "stopped", timeout=30
    )
    for _ in range(5):
        h.runner.tick()
        h.page.wait_for_timeout(25)
    state = h.service.store.load()
    current = state["jobs"][0]["assistance"]
    assert state["control"] == "paused"
    assert current["stop"]["reason"] == "user_paused"
    # The pause itself is the stop; superseded marks only a control that
    # follows an existing completion stop, so it is absent here.
    assert "superseded" not in current
    assert "outcome" not in current
    assert current["status"] != "released" and current["active_writer"] != "script"
    report_kept(h, "blocked_segment_resolved")
    assert h.page.locator("#email").input_value() == ""
    assert h.page.locator("#phone").input_value() == ""
    assert_single_writer(h)
    original_document(h)


@pytest.mark.parametrize("native_handoff", [case("lost_outcome_save")], indirect=True)
def test_real_native_lost_outcome_save_resaves_without_refill(native_handoff, monkeypatch):
    h = native_handoff
    save = h.service.store.save
    failure = []
    save_error = OSError("synthetic outcome checkpoint write failure")

    def lose_outcome_save(state):
        attempted = (state["jobs"][0].get("assistance") or {}).get("outcome")
        if attempted and not failure and not assistance(h).get("outcome"):
            failure.append({"attempted": deepcopy(attempted), "durable": h.service.store.load()})
            raise save_error
        return save(state)

    monkeypatch.setattr(h.service.store, "save", lose_outcome_save)
    h.extra_evidence["outcome_save_failure"] = failure
    start(h, "real-native-lost-outcome")
    drive_worker(h, lambda: bool(failure) or bool(peer_failures(h)))
    assert not peer_failures(h)
    for _ in range(5):
        h.runner.tick()
        h.page.wait_for_timeout(25)
    attempted = failure[0]["attempted"]
    assert attempted["kind"] == "filling_complete"
    lost = assistance(h)
    assert "outcome" not in lost and lost.get("report")
    assert job(h)["status"] != "ready_for_review"
    before = {
        "native_sent": len(native_sent(h)),
        "mutations": deepcopy(mutation_calls(h)),
        "page": counters_of(h.page),
        "intent": deepcopy(job(h)["intent"]),
        "action_results": len(
            [row for row in job(h)["observations"] if row.get("action") == "action_result"]
        ),
    }
    h.extra_evidence["before_continue"] = before
    monkeypatch.setattr(h.service.store, "save", save)
    h.service.request("resume", CONTROLLER)
    drive_worker(
        h,
        lambda: bool(assistance(h).get("outcome")) or job(h)["status"] in WAITING,
        timeout=30,
    )
    current = assert_adopted(h, "filling_complete")
    outcome = current["outcome"]
    assert outcome["report_sha256"] == attempted["report_sha256"]
    assert outcome["stop_request_id"] == attempted["stop_request_id"]
    assert outcome["attributed_fields"] == attempted["attributed_fields"]
    assert current["report"]["claimed_sha256"] == lost["report"]["claimed_sha256"]
    assert job(h)["status"] == "ready_for_review" and not job(h).get("manual_submission")
    after = {
        "native_sent": len(native_sent(h)),
        "mutations": mutation_calls(h),
        "page": counters_of(h.page),
        "intent": job(h)["intent"],
        "action_results": len(
            [row for row in job(h)["observations"] if row.get("action") == "action_result"]
        ),
    }
    assert after == before
    # The script uploaded the resume once before the binding; nothing re-uploads it.
    assert before["page"]["files"] == h.extra_evidence["prepared_counters"]["files"]
    original_document(h)
