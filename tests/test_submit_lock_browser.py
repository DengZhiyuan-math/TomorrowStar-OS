"""APP-11 action layer: a locked page's forms cannot submit by any page channel."""

from __future__ import annotations

import pytest
from playwright.sync_api import sync_playwright

from career_evidence_graph.application_worker_browser import SUBMIT_LOCK_INSTALL, ApplicationRunner

pytestmark = pytest.mark.worker_browser

FORM = """<form method="post" action="/final">
  <input id="email" name="email"><button id="send" type="submit">Submit</button>
</form>
<form id="spa"><input id="q" name="q"></form>
<script>
  // An SPA submit handler that sends by fetch: stopping the event stops the send.
  document.getElementById('spa').addEventListener('submit', event => {
    event.preventDefault(); fetch('/final', {method: 'POST', body: 'spa'});
  });
</script>
<iframe srcdoc='<form method="post" action="http://form.test/final"></form>'></iframe>"""

CHANNELS = {
    "button": lambda page: page.click("#send"),
    "enter": lambda page: page.press("#email", "Enter"),
    "requestSubmit": lambda page: page.evaluate("document.forms[0].requestSubmit()"),
    "form.submit": lambda page: page.evaluate("document.forms[0].submit()"),
    "spa_handler": lambda page: page.press("#q", "Enter"),
    "frame": lambda page: page.frames[1].evaluate("document.forms[0].submit()"),
}


@pytest.fixture
def form_page(monkeypatch):
    monkeypatch.setenv("PLAYWRIGHT_BROWSERS_PATH", "0")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, channel="chromium")
        context = browser.new_context()
        context.add_init_script(SUBMIT_LOCK_INSTALL)
        finals = []

        def serve(route):
            if route.request.url.endswith("/final"):
                finals.append(route.request.method)
                route.fulfill(body="received")
            else:
                route.fulfill(body=FORM, content_type="text/html")

        context.route("http://form.test/**", serve)
        page = context.new_page()
        page.goto("http://form.test/apply")
        page.frames[1].wait_for_load_state()
        yield page, finals
        browser.close()


@pytest.mark.parametrize("channel", CHANNELS)
def test_locked_page_cannot_submit_by_any_page_channel(form_page, channel):
    page, finals = form_page
    ApplicationRunner._submit_lock(page, True)
    CHANNELS[channel](page)
    page.wait_for_timeout(200)
    assert finals == []


@pytest.mark.parametrize("channel", ["button", "requestSubmit", "spa_handler", "frame"])
def test_unlocked_page_submits_natively(form_page, channel):
    page, finals = form_page
    ApplicationRunner._submit_lock(page, True)
    ApplicationRunner._submit_lock(page, False)
    CHANNELS[channel](page)
    page.wait_for_timeout(200)
    assert finals == ["POST"]
