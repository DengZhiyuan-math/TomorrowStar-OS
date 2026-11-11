"""Current-page ATS continuation. Synthetic forms, isolated browser, no external writes."""

import json
import time
from copy import deepcopy

import pytest
from synthetic_ats_material_context import supply_synthetic_material_context
from test_generic_worker import FIELDS, native_form

pytestmark = pytest.mark.worker_browser

STEP_FORM = """<form id='step-form'>
<section id='contact-step' role='tabpanel'>
<label>Full name *<input id='person' name='person' required></label>
<label>Optional note<input id='note' name='note'></label>
<button id='next' type='button' aria-controls='details-step'>Continue</button>
</section>
<section id='details-step' role='tabpanel' hidden>
<label>Email *<input id='contact' name='contact' type='email' required></label>
<label>Located in Switzerland? *<select id='location' required>
<option value=''>Choose</option><option value='yes'>Yes</option><option value='no'>No</option>
</select></label>
<label>Resume/CV *<input id='attachment' name='attachment' type='file' required></label>
<button id='submit' type='submit'>Submit application</button>
</section></form><script>
window.nextActions=0;window.finalActions=0;
document.querySelector('#next').onclick=()=>{
  nextActions++;document.querySelector('#contact-step').hidden=true;
  document.querySelector('#details-step').hidden=false;
};document.querySelector('form').onsubmit=e=>{e.preventDefault();finalActions++};
</script>"""


def tick(service, runner, count=1):
    # Keep the old action budget, while observing the real parser quiet windows.
    # An idle parser sample is not another completed browser operation.
    deadline = time.monotonic() + 12
    for _ in range(count):
        before = service.store.load()["jobs"][0]
        while True:
            service.request("heartbeat", {"controller": "synthetic-controller"})
            runner.tick()
            current = service.store.load()["jobs"][0]
            progressed = len(current["observations"]) != len(before["observations"])
            if current["status"] == "needs_recheck":
                return current
            if current["reason"] != "awaiting_parser" or progressed or runner.work_progressed:
                break
            assert time.monotonic() < deadline, current["reason"]
            runner.pages[current["application_id"]].wait_for_timeout(250)
    return current


def test_semantic_button_combobox_fills_and_reads_back_without_native_proxy(tmp_path, monkeypatch):
    html = (
        """<form>"""
        + FIELDS
        + """
<span id='degree-label'>Degree *</span>
<button id='degree' type='button' role='combobox' aria-controls='degrees'
 aria-valuetext='' aria-labelledby='degree-label' aria-required='true'>Choose</button>
<div id='degrees' role='listbox' hidden><div role='option'>Master</div></div>
<button type='submit'>Submit application</button></form><script>
window.finalActions=0;window.comboActions=[];
const degree=document.querySelector('#degree'),degrees=document.querySelector('#degrees');
degree.onclick=()=>{degrees.hidden=false;window.comboActions.push('open')};
degrees.firstElementChild.onclick=()=>{
 degree.setAttribute('aria-valuetext','Master');degrees.hidden=true;
 window.comboActions.push('choose');
};document.querySelector('form').onsubmit=e=>{e.preventDefault();window.finalActions++};
</script>"""
    )
    with native_form(tmp_path, monkeypatch, html) as (service, runner, job, posts):
        service.store.answers.put_answer(
            {"question": "Degree", "value": "Master", "scope": {}, "state": "confirmed"}
        )
        current = tick(service, runner, 6)
        page = runner.pages[job["application_id"]]
        assert current["status"] == "ready_for_review", (
            current["reason"],
            current.get("form_state"),
            current.get("intent"),
        )
        assert page.locator("#degree").get_attribute("aria-valuetext") == "Master"
        assert page.evaluate("window.comboActions") == ["open", "choose"]
        assert page.locator("input[type=file]").evaluate("(e)=>e.files[0].name") == job["filename"]
        assert page.evaluate("window.finalActions") == 0
        assert posts == []


def test_field_inserted_during_fill_preserves_existing_control_identity(tmp_path, monkeypatch):
    html = (
        "<form>"
        + FIELDS
        + """<button type='submit'>Submit application</button></form>
<script>window.finalActions=0;
document.querySelector('[name=person]').oninput=e=>{
 if(document.querySelector('#inserted'))return;
 e.target.closest('label').insertAdjacentHTML('beforebegin',
 '<label>Optional note<input id="inserted" value="Keep inserted manual value"></label>');
};document.querySelector('form').onsubmit=e=>{e.preventDefault();window.finalActions++};
</script>"""
    )
    with native_form(tmp_path, monkeypatch, html) as (service, runner, job, posts):
        current = tick(service, runner, 6)
        page = runner.pages[job["application_id"]]
        assert current["status"] == "ready_for_review", current["reason"]
        assert page.locator("[name=person]").input_value() == "Synthetic Person"
        assert page.locator("[name=contact]").input_value() == "synthetic@example.invalid"
        assert page.locator("#inserted").input_value() == "Keep inserted manual value"
        assert page.locator("input[type=file]").evaluate("(e)=>e.files[0].name") == job["filename"]
        assert page.evaluate("window.finalActions") == 0
        assert posts == []


@pytest.mark.parametrize("dynamic", [False, True])
def test_two_step_dynamic_question_retains_manual_edit_and_selected_pdf(
    tmp_path, monkeypatch, dynamic
):
    html = STEP_FORM
    if dynamic:
        start = html.index("<label>Email")
        end = html.index("</section>", start)
        details = html[start:end]
        html = html[:start] + html[end:]
        html = html.replace(
            "nextActions++;",
            "nextActions++;document.querySelector('#details-step').innerHTML="
            + json.dumps(details)
            + ";",
        )
    with native_form(tmp_path, monkeypatch, html) as (service, runner, job, posts):
        # Isolate ATS continuation from the full flow's separate document binding.
        state = service.store.load()
        state["current_job_id"] = job["application_id"]
        state["jobs"][0]["workflow"] = "single"
        service.store.save(state)
        monkeypatch.setattr(service.store, "check_single", lambda *args, **kwargs: None)
        supply_synthetic_material_context(service, monkeypatch)
        library = deepcopy(service.store.library())
        tick(service, runner)
        page = runner.pages[job["application_id"]]
        page.locator("#note").fill("Keep this manual edit")
        interrupted = tick(service, runner)
        assert interrupted["status"] == "needs_recheck"
        assert interrupted["reason"] == "form_changed"
        assert page.evaluate("window.nextActions") == 0
        service.request(
            "continue-current",
            {
                "application_id": job["application_id"],
                "request_id": "continue-after-manual-note",
                "controller": "synthetic-controller",
            },
        )
        current = tick(service, runner, 5)
        assert current["continuation"]["status"] == "verified"
        assert current["continuation_requests"] == ["continue-after-manual-note"]
        assert service.store.library() == library
        assert current["status"] == "needs_input", current["reason"]
        assert [q["question"] for q in current["questions"]] == ["Located in Switzerland?"]
        assert page.evaluate("window.nextActions") == 1
        assert page.locator("#contact").input_value() == "synthetic@example.invalid"
        service.request(
            "answer",
            {
                "application_id": job["application_id"],
                "question_id": current["questions"][0]["id"],
                "value": "Yes",
            },
        )
        current = tick(service, runner, 5)
        assert current["status"] == "ready_for_review", current["reason"]
        assert page.locator("#note").input_value() == "Keep this manual edit"
        assert page.locator("#location").input_value() == "yes"
        assert page.locator("#attachment").evaluate("(e)=>e.files[0].name") == job["filename"]
        assert page.evaluate("window.nextActions") == 1
        assert page.evaluate("window.finalActions") == 0
        assert posts == []


@pytest.mark.parametrize(
    "fault,reason",
    [
        ("replacement", "navigation_changed"),
        ("target_replacement", "navigation_changed"),
        ("unknown_write", "unverified_send_path"),
        ("final_write", "manual_submit_required"),
    ],
)
def test_next_unknown_or_changed_target_preserves_attempt_without_replay(
    tmp_path, monkeypatch, fault, reason
):
    html = STEP_FORM
    if fault not in {"replacement", "target_replacement"}:
        endpoint = (
            "/opaque-save"
            if fault == "unknown_write"
            else "/graphql?op=ApiSubmitSingleApplicationFormAction"
        )
        html = html.replace(
            "nextActions++;",
            "nextActions++;fetch("
            + json.dumps(endpoint)
            + ",{method:'POST',body:'synthetic'}).catch(()=>{});",
        )
    with native_form(tmp_path, monkeypatch, html) as (service, runner, job, posts):
        if fault in {"replacement", "target_replacement"}:
            authorize = runner.authorize

            def replace_after_authorization(current, batch_id, intent):
                allowed = authorize(current, batch_id, intent)
                if allowed and intent["action"] == "advance":
                    runner.pages[job["application_id"]].evaluate(
                        """target => {
                        const old=document.querySelector(target);
                        const copy=old.cloneNode(true);copy.onclick=()=>window.nextActions++;
                        old.replaceWith(copy);
                    }""",
                        "#next" if fault == "replacement" else "#details-step",
                    )
                return allowed

            monkeypatch.setattr(runner, "authorize", replace_after_authorization)
        current = tick(service, runner, 5)
        assert current["status"] == "needs_recheck"
        assert current["reason"] == reason
        assert current["intent"]["action"] == "advance"
        page = runner.pages[job["application_id"]]
        clicks = page.evaluate("window.nextActions")
        tick(service, runner, 3)
        assert (
            page.evaluate("window.nextActions")
            == clicks
            == (0 if fault in {"replacement", "target_replacement"} else 1)
        )
        assert page.evaluate("window.finalActions") == 0
        assert posts == []


@pytest.mark.parametrize("still_waiting", [False, True])
def test_one_continue_checks_retained_login_page_and_reuses_session(
    tmp_path, monkeypatch, still_waiting
):
    login = "<form><label>Sign in<input id='password' type='password'></label></form>"
    with native_form(tmp_path, monkeypatch, login) as (service, runner, job, posts):
        current = tick(service, runner)
        assert current["status"] == "needs_recheck"
        assert current["reason"] == "user_authentication"
        assert current["intent"] is None
        page = runner.pages[job["application_id"]]
        page_id = runner.page_ids[page]
        page.locator("#password").fill("synthetic-user-only")
        if not still_waiting:
            page.context.add_cookies(
                [{"name": "synthetic_session", "value": "existing", "url": page.url}]
            )
            page.evaluate(
                "html => document.body.innerHTML=html",
                "<form>" + "<label>Full name<input name='person' required></label>"
                "<label>Email<input name='contact' type='email' required></label>"
                "<label>Resume/CV<input name='attachment' type='file' required></label>"
                "<button type='submit'>Submit application</button></form><h1>Engineer</h1>",
            )
        service.request("resume", {"controller": "synthetic-controller"})
        current = tick(service, runner, 5)
        assert runner.pages[job["application_id"]] is page
        assert runner.page_ids[page] == page_id
        if still_waiting:
            assert current["status"] == "needs_recheck"
            assert current["reason"] == "user_authentication"
            assert page.locator("#password").input_value() == "synthetic-user-only"
        else:
            assert current["status"] == "ready_for_review", current["reason"]
            assert any(cookie["name"] == "synthetic_session" for cookie in page.context.cookies())
            assert (
                page.locator("input[type=file]").evaluate("(e)=>e.files[0].name") == job["filename"]
            )
        assert posts == []


@pytest.mark.parametrize("historical_upload", [False, True])
def test_empty_review_stage_cannot_reuse_another_page_attachment(
    tmp_path, monkeypatch, historical_upload
):
    html = (
        "<form><section role='tabpanel' id='review'>"
        "<button type='submit'>Submit application</button></section></form>"
    )
    with native_form(tmp_path, monkeypatch, html) as (service, runner, job, posts):
        if historical_upload:
            state = service.store.load()
            state["jobs"][0]["observations"].append(
                {
                    "action": "action_result",
                    "result": "verified",
                    "run_id": "previous-run",
                    "intent": {
                        "action": "upload",
                        "attempt_id": "previous-upload",
                        "run_id": "previous-run",
                        "page_id": "previous-page",
                        "sha256": job["file_sha256"],
                    },
                }
            )
            service.store.save(state)
        current = tick(service, runner, 3)
        assert current["status"] == "needs_recheck"
        assert current["reason"] == "resume_control_missing"
        assert current["page_open"]
        assert posts == []


@pytest.mark.parametrize("fault", ["", "removed", "cleared", "changed_bytes"])
def test_final_review_panel_requires_current_attachment_from_same_owned_page(
    tmp_path, monkeypatch, fault
):
    html = STEP_FORM.replace(
        "<button id='submit' type='submit'>Submit application</button>",
        "<button id='review-next' type='button' aria-controls='review'>Review</button>",
    ).replace(
        "</form>",
        "<section role='tabpanel' id='review' hidden>"
        "<button type='submit'>Submit application</button></section></form>",
    )
    html += (
        "<script>document.querySelector('#review-next').onclick=()=>{"
        "document.querySelector('#details-step').hidden=true;"
        "document.querySelector('#review').hidden=false}</script>"
    )
    damage = {
        "": "",
        "removed": "document.querySelector('#attachment').remove();",
        "cleared": "document.querySelector('#attachment').value='';",
        "changed_bytes": (
            "const file=document.querySelector('#attachment'),data=new DataTransfer();"
            "data.items.add(new File(['%PDF-1.4 different'],file.files[0].name,"
            "{type:'application/pdf'}));file.files=data.files;"
        ),
    }[fault]
    html += (
        "<script>document.querySelector('#review-next').addEventListener('click',()=>{"
        + damage
        + "});</script>"
    )
    with native_form(tmp_path, monkeypatch, html) as (service, runner, job, posts):
        service.store.answers.put_answer(
            {
                "question": "Located in Switzerland?",
                "value": "Yes",
                "scope": {},
                "state": "confirmed",
            }
        )
        current = tick(service, runner, 12)
        page = runner.pages[job["application_id"]]
        assert current["status"] == ("needs_recheck" if fault else "ready_for_review"), current[
            "reason"
        ]
        assert page.locator("#review").is_visible()
        if not fault:
            assert page.locator("#attachment").evaluate("(e)=>e.files[0].name") == job["filename"]
        assert page.evaluate("window.finalActions") == 0
        assert posts == []


@pytest.mark.parametrize("change", ["clear", "insert", "manual_value"])
def test_next_rechecks_current_fields_after_authorization(tmp_path, monkeypatch, change):
    with native_form(tmp_path, monkeypatch, STEP_FORM) as (service, runner, job, posts):
        authorize = runner.authorize

        def changed_fields(current, batch_id, intent):
            allowed = authorize(current, batch_id, intent)
            if allowed and intent["action"] == "advance":
                script = {
                    "clear": "document.querySelector('#person').value=''",
                    "insert": (
                        "document.querySelector('#contact-step').insertAdjacentHTML("
                        "'afterbegin','<label>Additional fact<input required></label>')"
                    ),
                    "manual_value": (
                        "document.querySelector('#note').value="
                        "'Human changed this after authorization'"
                    ),
                }[change]
                runner.pages[job["application_id"]].evaluate(script)
            return allowed

        monkeypatch.setattr(runner, "authorize", changed_fields)
        current = tick(service, runner, 6)
        page = runner.pages[job["application_id"]]
        assert current["status"] == "needs_recheck", (
            current["reason"],
            current.get("form_state"),
            current.get("intent"),
        )
        assert current["reason"] in {"navigation_changed", "form_changed"}, (
            current.get("form_state"),
            current.get("intent"),
        )
        assert current["intent"]["action"] == "advance"
        assert page.evaluate("window.nextActions") == 0
        tick(service, runner, 3)
        assert page.evaluate("window.nextActions") == 0
        if change == "manual_value":
            assert page.locator("#note").input_value() == "Human changed this after authorization"
        assert posts == []


@pytest.mark.parametrize("lost", ["closed", "replaced"])
def test_login_continue_does_not_reopen_or_use_a_replacement_page(tmp_path, monkeypatch, lost):
    with native_form(tmp_path, monkeypatch, "<form><input type='password'></form>") as (
        service,
        runner,
        job,
        posts,
    ):
        current = tick(service, runner)
        assert current["reason"] == "user_authentication"
        original = runner.pages[job["application_id"]]
        if lost == "closed":
            original.close()
        else:
            replacement = original.context.new_page()
            replacement.set_content("<title>Synthetic Careers</title><h1>Engineer</h1>")
            runner.pages[job["application_id"]] = replacement
            runner.page_ids[replacement] = "different-synthetic-page"
        page_count = len(runner.context.pages)
        service.request("resume", {"controller": "synthetic-controller"})
        current = tick(service, runner, 3)
        assert current["status"] == "needs_recheck"
        assert current["reason"] in {"page_lost", "page_closed", "page_changed"}
        assert len(runner.context.pages) == page_count
        assert posts == []
