"""Observed same-form steps on isolated synthetic pages; no external network."""

from contextlib import contextmanager

import pytest

from career_evidence_graph import hosted_ats
from career_evidence_graph.career_portal_data import PortalDataError

pytestmark = pytest.mark.worker_browser
URL = "https://careers.example.test/jobs/42"
JOB = {"platform": "generic", "job_url": URL, "company": "Synthetic", "role_title": "Engineer"}


@contextmanager
def form_page(monkeypatch, html):
    from playwright.sync_api import sync_playwright

    monkeypatch.setenv("PLAYWRIGHT_BROWSERS_PATH", "0")
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True, channel="chromium")
        try:
            context = browser.new_context(offline=True)
            page = context.new_page()
            page.set_default_timeout(5000)
            page.route(
                "**/*",
                lambda route: route.fulfill(
                    body="<title>Synthetic Careers</title><h1>Engineer</h1>" + html,
                    content_type="text/html",
                ),
            )
            page.goto(URL)
            yield page
        finally:
            browser.close()


def test_observe_explicit_step_ignores_future_required_fields(monkeypatch):
    html = """<form>
    <section role="tabpanel" id="person"><label>Full name *<input required></label>
    <button id="advance" type="button" aria-controls="documents">Next</button></section>
    <section role="tabpanel" id="documents" hidden>
    <label>Email *<input type="email" required></label>
    <label>Resume *<input type="file" name="resume" required></label></section>
    </form>"""
    with form_page(monkeypatch, html) as page:
        observed = hosted_ats.observe(page, JOB)
        assert observed["stage"] == "person"
        assert [(field["question"], field["type"]) for field in observed["fields"]] == [
            ("Full name", "text")
        ]
        navigation = observed["navigation"]
        assert navigation["from_step"] == "person"
        assert navigation["to_step"] == "documents"
        assert (
            page.locator(f'[data-ts-worker-navigation="{navigation["control_id"]}"]').get_attribute(
                "id"
            )
            == "advance"
        )


def test_reordered_options_keep_their_original_control_identity(monkeypatch):
    html = """<form><label>Email<input type="email"></label>
    <label>Resume<input type="file" name="resume"></label>
    <fieldset><legend>Work location *</legend>
    <label id="onsite-label">Onsite<input id="onsite" type="radio" name="location" required></label>
    <label id="remote-label">Remote<input id="remote" type="radio" name="location" required></label>
    </fieldset></form>"""
    with form_page(monkeypatch, html) as page:
        before = hosted_ats.observe(page, JOB)
        question = next(field for field in before["fields"] if field["type"] == "radio")
        original_control = page.locator("#remote").get_attribute("data-ts-worker-field")
        page.evaluate(
            "document.querySelector('#onsite-label').before(document.querySelector('#remote-label'))"
        )
        after = hosted_ats.observe(page, JOB)
        current = next(field for field in after["fields"] if field["type"] == "radio")
        assert current["id"] == question["id"]
        assert page.locator("#remote").get_attribute("data-ts-worker-field") == original_control
        hosted_ats.fill(page, current, "Remote")
        assert page.locator("#remote").is_checked()
        assert not page.locator("#onsite").is_checked()


@pytest.mark.parametrize(
    "challenge",
    [
        '<input type="password">',
        '<input autocomplete="one-time-code">',
        '<iframe title="CAPTCHA verification"></iframe>',
    ],
)
def test_authentication_on_owned_url_precedes_missing_application_identity(monkeypatch, challenge):
    with form_page(monkeypatch, challenge) as page:
        page.evaluate("document.title='Sign in'; document.querySelector('h1').remove()")
        with pytest.raises(PortalDataError) as error:
            hosted_ats.observe(page, JOB)
        assert error.value.code == "user_authentication"


def test_rescan_preserves_existing_ids_and_replacement_gets_a_new_id(monkeypatch):
    html = """<form><label>Email<input id="email" type="email"></label>
    <label>Resume<input type="file" name="resume"></label></form>"""
    with form_page(monkeypatch, html) as page:
        original = next(
            field for field in hosted_ats.observe(page, JOB)["fields"] if field["type"] == "email"
        )
        page.evaluate("""() => {
          const label=document.createElement('label'); label.textContent='Phone';
          label.append(document.createElement('input'));
          document.querySelector('form').prepend(label);
        }""")
        current = next(
            field for field in hosted_ats.observe(page, JOB)["fields"] if field["type"] == "email"
        )
        assert current["id"] == original["id"]
        page.evaluate("""() => {
          const next=document.createElement('input'); next.type='email'; next.id='email';
          document.querySelector('#email').replaceWith(next);
        }""")
        replaced = next(
            field for field in hosted_ats.observe(page, JOB)["fields"] if field["type"] == "email"
        )
        assert replaced["id"] != original["id"]
        assert hosted_ats.control(page, original).count() == 0


@pytest.mark.parametrize(
    "button",
    [
        '<button aria-controls="documents">Next</button>',
        '<button type="submit" aria-controls="documents">Next</button>',
        '<button type="button" formaction="/send" aria-controls="documents">Next</button>',
        '<button type="button">Next</button>',
        '<button type="button" aria-controls="missing">Next</button>',
        '<button type="button" aria-controls="documents">Next</button>'
        '<button type="button" aria-controls="documents">Continue</button>',
    ],
)
def test_unverified_navigation_stops_instead_of_marking_ready(monkeypatch, button):
    html = f"""<form><section role="tabpanel" id="person">
    <label>Email<input type="email"></label>{button}</section>
    <section role="tabpanel" id="documents" hidden>
    <label>Resume<input type="file" name="resume"></label></section></form>"""
    with form_page(monkeypatch, html) as page:
        with pytest.raises(PortalDataError) as error:
            hosted_ats.observe(page, JOB)
        assert error.value.code == "unsupported_structure"


def test_final_explicit_stage_can_be_empty_while_retaining_form_resume_count(monkeypatch):
    html = """<form><section role="tabpanel" id="documents" hidden>
    <label>Email<input type="email"></label>
    <label>Resume<input type="file" name="resume"></label></section>
    <section role="tabpanel" id="review"><p>Review your application</p>
    <button type="submit">Submit</button></section></form>"""
    with form_page(monkeypatch, html) as page:
        current = hosted_ats.observe(page, JOB)
        assert current["stage"] == "review"
        assert current["fields"] == []
        assert current["navigation"] is None
        assert current["resume_count"] == 1


def test_distinct_job_url_still_refused_even_when_it_contains_a_login(monkeypatch):
    with form_page(monkeypatch, '<input type="password">') as page:
        page.goto(URL.replace("42", "43"))
        with pytest.raises(PortalDataError) as error:
            hosted_ats.observe(page, JOB)
        assert error.value.code == "page_changed"


def test_listbox_opener_is_not_misclassified_as_step_navigation(monkeypatch):
    html = """<form><label>Email<input type="email"></label>
    <label>Resume<input type="file" name="resume"></label>
    <button type="button" role="combobox" aria-controls="choices"
      aria-label="Location" aria-valuetext="">Location</button>
    <div role="listbox" id="choices" hidden></div></form>"""
    with form_page(monkeypatch, html) as page:
        observed = hosted_ats.observe(page, JOB)
        assert observed["navigation"] is None
        assert not observed["unknown_navigation"]


def test_previous_step_control_does_not_advance_or_block_final_stage(monkeypatch):
    html = """<form><section role="tabpanel" id="documents" hidden>
    <label>Email<input type="email"></label>
    <label>Resume<input type="file" name="resume"></label></section>
    <section role="tabpanel" id="review">
    <button type="button" aria-controls="documents">Back</button>
    <button type="submit">Submit</button></section></form>"""
    with form_page(monkeypatch, html) as page:
        observed = hosted_ats.observe(page, JOB)
        assert observed["stage"] == "review"
        assert observed["navigation"] is None


def test_explicit_form_stages_can_create_and_remove_fields_dynamically(monkeypatch):
    html = """<form><section role="tabpanel" id="person">
    <label>Full name<input></label>
    <button type="button" aria-controls="documents">Next</button></section>
    <section role="tabpanel" id="documents" hidden></section></form>"""
    with form_page(monkeypatch, html) as page:
        before = hosted_ats.observe(page, JOB)
        assert before["stage"] == "person"
        assert before["resume_count"] == 0
        assert before["navigation"]["to_step"] == "documents"
        page.evaluate("""() => {
          document.querySelector('#person').hidden=true;
          document.querySelector('#person').replaceChildren();
          document.querySelector('#documents').hidden=false;
        }""")
        current = hosted_ats.observe(page, JOB)
        assert current["stage"] == "documents"
        assert current["fields"] == []
        assert current["resume_count"] == 0


def test_replacement_cannot_inherit_a_previous_nodes_stamped_identity(monkeypatch):
    html = """<form><label>Email<input id="email" type="email"></label>
    <label>Resume<input type="file" name="resume"></label></form>"""
    with form_page(monkeypatch, html) as page:
        hosted_ats.observe(page, JOB)
        page.evaluate("""() => {
          const previous=document.querySelector('#email');
          previous.replaceWith(previous.cloneNode(true));
        }""")
        with pytest.raises(PortalDataError) as error:
            hosted_ats.observe(page, JOB)
        assert error.value.code == "unsupported_structure"


def test_nested_select_options_are_not_part_of_the_question(monkeypatch):
    html = """<form><label>Email<input type="email"></label>
    <label>Resume<input type="file" name="resume"></label>
    <label>Located in Switzerland? *<select required><option value="">Choose</option>
    <option value="yes">Yes</option><option value="no">No</option></select></label></form>"""
    with form_page(monkeypatch, html) as page:
        observed = hosted_ats.observe(page, JOB)
        question = next(field for field in observed["fields"] if field["type"] == "select")
        assert question["question"] == "Located in Switzerland?"
        assert question["options"] == ["Yes", "No"]


def test_semantic_button_combobox_uses_declared_listbox_and_value_readback(monkeypatch):
    html = """<form><label>Email<input type="email"></label>
    <label>Resume<input type="file" name="resume"></label>
    <span id="degree-label">Education *</span>
    <button type="button" role="combobox" aria-labelledby="degree-label" aria-required="true"
      aria-controls="degrees" aria-expanded="false" aria-valuetext="">Choose a degree</button>
    <div role="listbox" id="degrees" hidden><div role="option">Master</div></div></form>"""
    with form_page(monkeypatch, html) as page:
        before = hosted_ats.observe(page, JOB)
        question = next(field for field in before["fields"] if field["type"] == "combobox")
        assert question["question"] == "Education"
        assert question["required"]
        assert question["value"] == ""
        assert not question["valid"]
        assert question["options"] == []
        assert before["navigation"] is None
        page.get_by_role("combobox").evaluate("e=>e.setAttribute('aria-valuetext','Master')")
        current = next(
            field
            for field in hosted_ats.observe(page, JOB)["fields"]
            if field["type"] == "combobox"
        )
        assert current["id"] == question["id"]
        assert current["value"] == "Master"
        assert current["valid"]


@pytest.mark.parametrize(
    "attributes,listbox",
    [
        (
            'aria-controls="degrees" aria-valuetext=""',
            '<div id="degrees" role="listbox" hidden></div>',
        ),
        (
            'type="submit" aria-controls="degrees" aria-valuetext=""',
            '<div id="degrees" role="listbox" hidden></div>',
        ),
        (
            'type="button" formaction="/submit" aria-controls="degrees" aria-valuetext=""',
            '<div id="degrees" role="listbox" hidden></div>',
        ),
        ('type="button" aria-controls="degrees"', '<div id="degrees" role="listbox" hidden></div>'),
        (
            'type="button" aria-controls="missing" aria-valuetext=""',
            '<div id="degrees" role="listbox" hidden></div>',
        ),
        (
            'type="button" aria-controls="degrees other" aria-valuetext=""',
            '<div id="degrees" role="listbox" hidden></div>',
        ),
        (
            'type="button" aria-controls="degrees" aria-valuetext=""',
            '<div id="degrees" hidden></div>',
        ),
        (
            'type="button" aria-controls="degrees" aria-valuetext=""',
            '<div id="degrees" role="listbox" hidden></div>'
            '<div id="degrees" role="listbox" hidden></div>',
        ),
        (
            'type="button" aria-controls="degrees" aria-valuetext=""',
            '<div id="degrees" role="listbox" aria-multiselectable="true" hidden></div>',
        ),
    ],
)
def test_unsafe_button_combobox_relationships_stop_before_execution(
    monkeypatch, attributes, listbox
):
    html = f"""<form><label>Email<input type="email"></label>
    <label>Resume<input type="file" name="resume"></label>
    <button role="combobox" aria-label="Education" aria-required="true" {attributes}>
    Choose</button>{listbox}</form>"""
    with form_page(monkeypatch, html) as page:
        with pytest.raises(PortalDataError) as error:
            hosted_ats.observe(page, JOB)
        assert error.value.code == "unsupported_structure"


def test_final_stage_reads_current_bytes_from_retained_hidden_resume(monkeypatch):
    import hashlib

    pdf = b"%PDF-1.4\nSynthetic retained resume\n"
    html = """<form><section role="tabpanel" id="documents">
    <label>Email<input type="email"></label>
    <label>Resume<input id="resume" type="file" name="resume" required></label></section>
    <section role="tabpanel" id="review" hidden><button type="submit">Submit</button></section>
    </form>"""
    with form_page(monkeypatch, html) as page:
        page.locator("#resume").set_input_files(
            {"name": "selected.pdf", "mimeType": "application/pdf", "buffer": pdf}
        )
        page.evaluate("""() => {
          document.querySelector('#documents').hidden=true;
          document.querySelector('#review').hidden=false;
        }""")
        observed = hosted_ats.observe(page, JOB)
        assert observed["stage"] == "review"
        assert observed["fields"] == []
        assert observed["retained_resume"] == [
            {
                "filename": "selected.pdf",
                "file_sha256": hashlib.sha256(pdf).hexdigest(),
                "valid": True,
                "multiple": False,
            }
        ]


def test_existing_remote_file_row_uses_stable_collision_free_identity(monkeypatch):
    html = """<form><label>Email<input type="email"></label>
    <span id="upload-label-resume">Resume</span>
    <div class="file-upload" aria-labelledby="upload-label-resume">
    <span class="file-upload__filename">selected.pdf</span></div></form>"""
    with form_page(monkeypatch, html) as page:
        before = hosted_ats.observe(page, JOB)
        identifiers = [field["id"] for field in before["fields"]]
        assert len(set(identifiers)) == len(identifiers)
        resume = next(field for field in before["fields"] if field["type"] == "file")
        assert resume["filename"] == "selected.pdf"
        page.evaluate("""() => {
          const label=document.createElement('label'); label.textContent='Phone';
          label.append(document.createElement('input'));
          document.querySelector('form').prepend(label);
        }""")
        after = hosted_ats.observe(page, JOB)
        current = next(field for field in after["fields"] if field["type"] == "file")
        assert current["id"] == resume["id"]
        assert current["filename"] == "selected.pdf"
        assert len({field["id"] for field in after["fields"]}) == len(after["fields"])


@pytest.mark.parametrize("change", ["cleared", "removed", "wrong_bytes", "disabled", "multiple"])
def test_retained_resume_reports_current_destructive_changes(monkeypatch, change):
    import hashlib

    selected = b"%PDF-1.4\nPreviously selected synthetic resume\n"
    wrong = b"%PDF-1.4\nDifferent synthetic resume\n"
    html = """<form><section role="tabpanel" id="documents" hidden>
    <label>Email<input type="email"></label>
    <label>Resume<input id="resume" type="file" name="resume" required></label></section>
    <section role="tabpanel" id="review"><button type="submit">Submit</button></section></form>"""
    with form_page(monkeypatch, html) as page:
        original_file = {"name": "selected.pdf", "mimeType": "application/pdf", "buffer": selected}
        page.locator("#resume").set_input_files(original_file)
        if change == "cleared":
            page.locator("#resume").set_input_files([])
        elif change == "removed":
            page.locator("#resume").evaluate("e=>e.remove()")
        elif change == "wrong_bytes":
            page.locator("#resume").evaluate("e=>e.replaceWith(e.cloneNode(true))")
            page.locator("#resume").set_input_files({**original_file, "buffer": wrong})
        elif change == "disabled":
            page.locator("#resume").evaluate("e=>e.disabled=true")
        else:
            page.locator("#resume").evaluate("e=>e.multiple=true")
            page.locator("#resume").set_input_files(
                [
                    original_file,
                    {"name": "other.pdf", "mimeType": "application/pdf", "buffer": wrong},
                ]
            )
        observed = hosted_ats.observe(page, JOB)
        assert observed["fields"] == []
        if change == "removed":
            assert observed["resume_count"] == 0
            assert observed["retained_resume"] == []
        else:
            assert len(observed["retained_resume"]) == 1
            current = observed["retained_resume"][0]
            if change == "cleared":
                assert current["filename"] == ""
                assert current["file_sha256"] == ""
                assert not current["valid"]
            elif change == "wrong_bytes":
                assert current["filename"] == "selected.pdf"
                assert current["file_sha256"] == hashlib.sha256(wrong).hexdigest()
                assert current["file_sha256"] != hashlib.sha256(selected).hexdigest()
            elif change == "disabled":
                assert not current["valid"]
            else:
                assert current["multiple"]
