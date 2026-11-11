"""P07 on retained, isolated synthetic ATS pages. No real applications or model calls.

The legacy fixture only supplies a valid prepared PDF and guarded browser. Its
single-job document binding is bypassed here to isolate the ATS boundary. An
explicit trusted synthetic delivery supplies its material context; the normal
flow's material binding is covered by separate flow/UI regressions.
"""

import hashlib
import time
from copy import deepcopy

import pytest
from synthetic_ats_material_context import supply_synthetic_material_context
from test_generic_worker import FIELDS, native_form

from career_evidence_graph import hosted_ats
from career_evidence_graph.ats_forms import FORMS

pytestmark = pytest.mark.worker_browser

INSTRUMENT = """<script>
window.finalActions={click:0,enter:0,submit:0,post:0};
document.addEventListener('click',e=>{
 if(e.target.closest('button[type=submit],input[type=submit]')) finalActions.click++;
});
document.addEventListener('keydown',e=>{if(e.key==='Enter')finalActions.enter++});
document.addEventListener('submit',e=>{finalActions.submit++;e.preventDefault()});
HTMLFormElement.prototype.submit=function(){finalActions.submit++};
const originalFetch=window.fetch;
window.fetch=(url,options={})=>{
 if((options.method||'GET').toUpperCase()==='POST')finalActions.post++;
 return originalFetch(url,options);
};
</script>"""
FINAL = '<button type="submit">Submit application</button>'


def current(service):
    return service.store.load()["jobs"][0]


def single_ats_fixture(service, monkeypatch):
    state = service.store.load()
    state["current_job_id"] = state["jobs"][0]["application_id"]
    state["jobs"][0]["workflow"] = "single"
    service.store.save(state)
    monkeypatch.setattr(service.store, "check_single", lambda *args, **kwargs: None)
    supply_synthetic_material_context(service, monkeypatch)


def reach(service, runner, predicate, *, timeout=8):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        runner.tick()
        state = current(service)
        if predicate(state):
            return state
        if state["status"] == "needs_recheck":
            pytest.fail(
                f"unexpected retained-page stop: {state['reason']}; form={state.get('form_state')}"
            )
        page = runner.pages.get(state["application_id"])
        assert page is not None
        page.wait_for_timeout(250)
    pytest.fail(f"ATS did not reach expected state: {current(service)}")


def assert_no_final_actions(page, posts):
    assert page.evaluate("window.finalActions") == {"click": 0, "enter": 0, "submit": 0, "post": 0}
    assert posts == []


def record_fills(monkeypatch):
    actual = hosted_ats.fill
    writes = []

    def fill(page, question, value):
        writes.append((question["question"], value))
        return actual(page, question, value)

    monkeypatch.setattr(hosted_ats, "fill", fill)
    return writes


def test_delayed_parse_preserves_baselines_then_batch_choices_continue_once(tmp_path, monkeypatch):
    html = (
        INSTRUMENT
        + """<form>
        <label>Full name *<input name="person" value="Human Person" required></label>
        <label>Email *<input name="contact" type="email"
          value="human@example.invalid" required></label>
        <label>Phone *<input name="phone" type="tel" value="+41 79 111 22 33" required></label>
        <label>Resume/CV *<input name="attachment" type="file" required></label>"""
        + FINAL
        + """</form><script>
        document.querySelector('[type=file]').addEventListener('change',()=>{
          const form=document.querySelector('form');form.dataset.parserState='active';
          window.releaseParser=()=>setTimeout(()=>{
            document.querySelector('[name=person]').value='Website Person';
            document.querySelector('[name=contact]').value='website@example.invalid';
            document.querySelector('[name=phone]').value='+41 79 444 55 66';
            form.dataset.parserState='complete';
          },350);
        });</script>"""
    )
    fills = record_fills(monkeypatch)
    with native_form(tmp_path, monkeypatch, html) as (service, runner, job, posts):
        single_ats_fixture(service, monkeypatch)
        service.store.answers.put_answer(
            {"question": "Phone", "value": "+41799998877", "scope": {}, "state": "confirmed"}
        )
        library = deepcopy(service.store.library())
        runner.tick()
        page = runner.pages[job["application_id"]]
        assert page.locator("form").get_attribute("data-parser-state") == "active"
        assert fills == []
        for _ in range(2):
            runner.tick()
            assert current(service)["reason"] == "awaiting_parser"
            assert fills == []
        page.evaluate("window.releaseParser()")
        page.wait_for_function("document.querySelector('form').dataset.parserState==='complete'")
        runner.tick()
        assert current(service)["form_state"]["parser"]["status"] == "waiting"
        assert fills == []
        pending = reach(service, runner, lambda row: row["reason"] == "form_differences")
        form = pending["form_state"]
        assert len(form["differences"]) == 3
        baseline = {
            row["question"]: row["value"]
            for row in form["baseline"].values()
            if row["type"] != "file"
        }
        assert baseline == {
            "Full name": "Human Person",
            "Email": "human@example.invalid",
            "Phone": "+41 79 111 22 33",
        }
        assert {row["reason"] for row in form["differences"]} == {"protected_value_changed"}
        choices = []
        for row in form["differences"]:
            action = {"Full name": "keep", "Email": "use", "Phone": "edit"}[row["question"]]
            choices.append(
                {"difference_id": row["id"], "action": action}
                | ({"value": "+41790001122"} if action == "edit" else {})
            )
        before_values = page.locator("input:not([type=file])").evaluate_all(
            "es=>es.map(e=>e.value)"
        )
        service.request(
            "resolve-form-differences",
            {
                "application_id": job["application_id"],
                "binding": form["binding"],
                "revision": form["revision"],
                "choices": choices,
            },
        )
        assert (
            page.locator("input:not([type=file])").evaluate_all("es=>es.map(e=>e.value)")
            == before_values
        )
        assert fills == []
        continued = service.request(
            "continue-current",
            {
                "application_id": job["application_id"],
                "request_id": "one-human-continue",
                "controller": "synthetic-controller",
            },
        )
        assert len(continued["commands"]) == 1
        ready = reach(service, runner, lambda row: row["status"] == "ready_for_review")
        assert ready["continuation"]["status"] == "verified"
        assert ready["continuation_requests"] == ["one-human-continue"]
        assert ready["form_state"]["differences"] == []
        assert page.locator("[name=person]").input_value() == "Website Person"
        assert page.locator("[name=contact]").input_value() == "synthetic@example.invalid"
        assert page.locator("[name=phone]").input_value() == "+41790001122"
        assert sorted(fills) == [("Email", "synthetic@example.invalid"), ("Phone", "+41790001122")]
        assert service.store.library() == library
        assert_no_final_actions(page, posts)


@pytest.mark.parametrize("filename", ["resume.pdf", "user-selected.pdf"])
def test_attachment_changed_after_authorize_stays_prepared_without_our_selection(
    tmp_path, monkeypatch, filename
):
    html = INSTRUMENT + "<form>" + FIELDS + FINAL + "</form>"
    with native_form(tmp_path, monkeypatch, html) as (service, runner, job, posts):
        single_ats_fixture(service, monkeypatch)
        original_authorize = runner.authorize
        own_selections = []
        inserted = []
        user_bytes = b"%PDF-1.7\nUser selected distinct synthetic bytes\n%%EOF\n"

        def authorize(current_job, batch_id, intent):
            allowed = original_authorize(current_job, batch_id, intent)
            if allowed and intent["action"] == "upload":
                page = runner.pages[job["application_id"]]
                page.locator("[type=file]").set_input_files(
                    {"name": filename, "mimeType": "application/pdf", "buffer": user_bytes}
                )
                inserted.append(deepcopy(intent))
            return allowed

        original_control = hosted_ats.control

        def control(page, question, index=0):
            locator = original_control(page, question, index)
            original_set = locator.set_input_files

            def set_input_files(*args, **kwargs):
                own_selections.append(True)
                return original_set(*args, **kwargs)

            locator.set_input_files = set_input_files
            return locator

        monkeypatch.setattr(runner, "authorize", authorize)
        monkeypatch.setattr(hosted_ats, "control", control)
        runner.tick()
        saved = current(service)
        assert saved["status"] == "needs_recheck"
        assert saved["reason"] == "form_changed"
        assert own_selections == []
        assert len(inserted) == 1
        assert saved["intent"] == inserted[0]
        assert saved["intent"]["dispatch_state"] == "prepared"
        page = runner.pages[job["application_id"]]
        actual = hosted_ats.observe(page, saved)["fields"]
        attachment = next(row for row in actual if row["type"] == "file")
        assert attachment["filename"] == filename
        assert attachment["file_sha256"] == hashlib.sha256(user_bytes).hexdigest()
        assert_no_final_actions(page, posts)


def test_no_parser_signal_uses_default_quiet_window_and_late_edits_stop_without_overwrite(
    tmp_path, monkeypatch
):
    html = INSTRUMENT + "<form>" + FIELDS + FINAL + "</form>"
    fills = record_fills(monkeypatch)
    with native_form(tmp_path, monkeypatch, html) as (service, runner, job, posts):
        single_ats_fixture(service, monkeypatch)
        started = time.monotonic()
        ready = reach(service, runner, lambda row: row["status"] == "ready_for_review")
        assert time.monotonic() - started >= 1.0
        assert ready["form_state"]["parser"]["observed_status"] == "unknown"
        assert ready["form_state"]["parser"]["samples"] >= 3
        assert ready["form_state"]["parser"]["status"] == "stable"
        page = runner.pages[job["application_id"]]
        old_writes = deepcopy(fills)
        page.locator("[name=person]").fill("Late human change")
        page.locator("[name=contact]").evaluate("e=>e.value='late-website@example.invalid'")
        runner.tick()
        saved = current(service)
        assert saved["status"] == "needs_recheck"
        assert saved["form_state"]["intervention_pending"] is True
        assert fills == old_writes
        assert page.locator("[name=person]").input_value() == "Late human change"
        assert page.locator("[name=contact]").input_value() == "late-website@example.invalid"
        assert_no_final_actions(page, posts)


def test_explicit_associated_error_blocks_ready_and_upload_receipt_is_not_parser_completion(
    tmp_path, monkeypatch
):
    html = (
        INSTRUMENT
        + """<form class="application-form" id="application-form">
        <label>Full name *<input name="person" value="Synthetic Person" required></label>
        <label>Email *<input name="contact" type="email" required
          value="synthetic@example.invalid" aria-errormessage="email-error"></label>
        <span id="email-error">The website requires account verification</span>
        <label>Resume/CV *<input name="attachment" type="file" required></label>
        <div id="upload-status" data-state="complete">Upload complete</div>"""
        + FINAL
        + "</form>"
    )
    with native_form(tmp_path, monkeypatch, html) as (service, runner, job, posts):
        single_ats_fixture(service, monkeypatch)
        for _ in range(8):
            runner.tick()
            saved = current(service)
            page = runner.pages[job["application_id"]]
            if saved["status"] == "needs_recheck":
                break
            assert saved["status"] != "ready_for_review"
            page.wait_for_timeout(250)
        assert saved["status"] == "needs_recheck"
        assert saved["reason"] == "form_validation_errors"
        assert saved["form_state"]["parser"]["observed_status"] == "unknown"
        assert (
            saved["form_state"]["snapshot"]["validation_errors"][0]["message"]
            == "The website requires account verification"
        )
        assert page.locator("[name=contact]").get_attribute("aria-invalid") is None
        preview = page.evaluate(FORMS["lever"].inspect_script())
        assert preview["parser"]["status"] == "unknown"
        assert preview["upload"]["state"] == "complete"
        assert preview["validation_errors"]
        assert_no_final_actions(page, posts)


def test_user_typing_during_active_parser_requires_continue_before_field_merge(
    tmp_path, monkeypatch
):
    html = (
        INSTRUMENT
        + "<form>"
        + FIELDS
        + FINAL
        + """</form><script>
        document.querySelector('[type=file]').addEventListener('change',()=>{
          document.querySelector('form').dataset.parserState='active';
          window.releaseParser=()=>setTimeout(()=>{
            document.querySelector('form').dataset.parserState='complete';
          },350);
        });</script>"""
    )
    fills = record_fills(monkeypatch)
    with native_form(tmp_path, monkeypatch, html) as (service, runner, job, posts):
        single_ats_fixture(service, monkeypatch)
        runner.tick()
        page = runner.pages[job["application_id"]]
        assert page.locator("form").get_attribute("data-parser-state") == "active"
        assert fills == []
        human_text = "unfinished human @"
        page.locator("[name=contact]").fill(human_text)
        runner.tick()
        interrupted = current(service)
        assert interrupted["status"] == "needs_recheck"
        assert interrupted["form_state"]["intervention_pending"] is True
        assert fills == []
        page.evaluate("window.releaseParser()")
        page.wait_for_function("document.querySelector('form').dataset.parserState==='complete'")
        page.wait_for_timeout(600)
        for _ in range(2):
            runner.tick()
            assert current(service)["status"] == "needs_recheck"
            assert fills == []
            assert page.locator("[name=contact]").input_value() == human_text
        service.request(
            "continue-current",
            {
                "application_id": job["application_id"],
                "request_id": "human-continued-parser-edit",
                "controller": "synthetic-controller",
            },
        )
        merged = reach(service, runner, lambda row: row["reason"] == "form_differences")
        assert merged["continuation"]["status"] == "verified"
        assert merged["continuation_requests"] == ["human-continued-parser-edit"]
        differences = merged["form_state"]["differences"]
        assert len(differences) == 1
        assert differences[0]["question"] == "Email"
        assert differences[0]["current_value"] == human_text
        assert page.locator("[name=contact]").input_value() == human_text
        assert not any(question == "Email" for question, _ in fills)
        assert_no_final_actions(page, posts)
