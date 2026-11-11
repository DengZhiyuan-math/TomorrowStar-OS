"""Source-owned form observers on isolated synthetic DOM fixtures only."""

import pytest
from test_ats_step_observation import JOB, form_page

from career_evidence_graph import hosted_ats
from career_evidence_graph.ats_forms import FORMS

pytestmark = pytest.mark.worker_browser


@pytest.mark.parametrize("script", [hosted_ats.INSPECT_HOSTED, FORMS["lever"].inspect_script()])
def test_parser_and_visible_associated_errors_are_observed(monkeypatch, script):
    html = """<form class="application-form" id="application-form" aria-busy="true">
    <label>Email<input id="email" type="email" aria-invalid="true"
      aria-errormessage="email-error"></label>
    <span id="email-error">Use a valid email</span>
    <label>Resume<input name="resume" type="file"></label>
    <div role="alert">An unrelated announcement</div>
    <label>Other<input id="other" aria-invalid="true" aria-describedby="hidden-error"></label>
    <span id="hidden-error" hidden>Hidden old error</span>
    <label>Helper<input id="helper" aria-invalid="true" aria-describedby="helper-text"></label>
    <span id="helper-text">Unrelated input guidance</span>
    <span class="resume-upload-failure" hidden></span>
    <span class="resume-upload-working" hidden></span>
    </form>"""
    with form_page(monkeypatch, html) as page:
        result = page.evaluate(script, True)
        assert result["parser"] == {"status": "active", "signal": "form-aria-busy"}
        assert len(result["validation_errors"]) == 1
        assert result["validation_errors"][0]["message"] == "Use a valid email"
        page.locator("form").evaluate(
            "e=>{e.removeAttribute('aria-busy');e.dataset.parserState='complete'}"
        )
        assert page.evaluate(script, True)["parser"]["status"] == "complete"
        page.locator(".resume-upload-working").evaluate("e=>e.hidden=false")
        assert page.evaluate(script, True)["parser"]["status"] == "active"
        page.locator(".resume-upload-failure").evaluate("e=>e.hidden=false")
        assert page.evaluate(script, True)["parser"]["status"] == "failed"


def test_hosted_observe_preserves_unknown_no_signal_and_ignores_hidden_step_errors(monkeypatch):
    html = """<form><section role="tabpanel" id="now">
    <label>Email<input type="email"></label>
    <label>Resume<input type="file" name="resume"></label></section>
    <section role="tabpanel" id="later" hidden>
    <label>Later<input id="later-input" aria-invalid="true" aria-errormessage="later-error"></label>
    <span id="later-error">This is for later</span></section></form>"""
    with form_page(monkeypatch, html) as page:
        result = hosted_ats.observe(page, JOB)
        assert result["parser"]["status"] == "unknown"
        assert not result["validation_errors"]
