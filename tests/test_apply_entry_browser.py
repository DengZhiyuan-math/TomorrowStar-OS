"""Opening a job enters its application form from a description page's one entry."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from playwright.sync_api import sync_playwright

from career_evidence_graph import hosted_ats
from career_evidence_graph.application_worker_browser import ApplicationRunner

pytestmark = pytest.mark.worker_browser

FORM = '<form><label>Email <input type="email" name="email"></label></form>'
PAGES = {
    "/job/link": '<h1>Engineer</h1><a href="/apply/1">Apply now</a>',
    "/job/twice": '<a href="/apply/1">Apply</a><a href="/apply/1#top">Apply now ›</a>',
    "/job/two": '<a href="/apply/1">Apply</a><a href="/apply/2">Apply now</a>',
    "/job/button": "<button onclick=\"location.href='/apply/1'\">Jetzt bewerben</button>",
    "/job/tab": "<button onclick=\"window.open('/apply/1')\">Apply</button>",
    "/job/form": FORM + '<a href="/apply/1">Apply now</a>',
    # A form's own Apply button may be its submit; it is never an entry.
    "/job/in-form": '<form><input name="q"><button>Apply</button></form>',
    "/job/none": "<p>Closed</p>",
    "/apply/1": FORM,
    "/apply/2": FORM,
}


@pytest.fixture
def browser_page(monkeypatch):
    monkeypatch.setenv("PLAYWRIGHT_BROWSERS_PATH", "0")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, channel="chromium")
        context = browser.new_context()
        context.route(
            "http://jobs.test/**",
            lambda route: route.fulfill(
                body=PAGES.get(route.request.url.split("jobs.test", 1)[1].split("#")[0], ""),
                content_type="text/html",
            ),
        )
        yield context.new_page()
        browser.close()


@pytest.mark.parametrize(
    ("path", "entered"),
    [
        ("/job/link", "/apply/1"),
        ("/job/twice", "/apply/1"),
        ("/job/button", "/apply/1"),
        ("/job/tab", "/apply/1"),
        ("/job/two", None),
        ("/job/form", None),
        ("/job/in-form", None),
        ("/job/none", None),
    ],
)
def test_open_enters_the_one_apply_entry_of_a_description_page(browser_page, path, entered):
    page = browser_page
    page.goto("http://jobs.test" + path)
    url = ApplicationRunner._enter_application(SimpleNamespace(), page)
    assert url == (entered and "http://jobs.test" + entered)
    assert page.url == "http://jobs.test" + (entered or path)
    assert len(page.context.pages) == 1


def test_entered_application_page_keeps_the_job_identity():
    job = {"job_url": "https://careers.example.test/job/42", "platform": "generic"}
    entry = "https://apply.example.test/form?job=42"
    assert not hosted_ats.matches_page(entry, job, document_url=entry)
    job["entry_url"] = entry
    assert hosted_ats.matches_page(entry, job, document_url=entry)
    assert not hosted_ats.matches_page(entry + "&x=1", job, document_url=entry)


AVATURE = "https://platinion.avature.net/CareersDeEn"
SITES = {
    # BCG Platinion, 2026-11-05: Phenom renders no Apply button but names its
    # external applyUrl; Avature first asks how to apply.
    "http://jobs.test/job/phenom": "<h1>AI Tech Consultant</h1><script>window.phApp = {ddo: "
    "{jobDetail: {data: {job: {isExternalApply: true, applyUrl: "
    f"'{AVATURE}/ApplicationMethods?jobId=794'}}}}}}}}}};</script>",
    f"{AVATURE}/ApplicationMethods?jobId=794": "<h2>Select your resume</h2>"
    '<button>Parse CV</button><a href="/CareersDeEn/Register?jobId=794">Apply Manually</a>'
    '<a href="/CareersDeEn/Login?jobId=794">Login</a>',
    f"{AVATURE}/Register?jobId=794": FORM,
}


def test_an_external_phenom_job_enters_the_avature_manual_form(browser_page):
    page = browser_page
    page.context.route(
        "**/*",
        lambda route: (
            route.fulfill(
                body=SITES.get(route.request.url, PAGES.get(route.request.url[15:], "")),
                content_type="text/html",
            )
            if route.request.url in SITES
            else route.fallback()
        ),
    )
    page.goto("http://jobs.test/job/phenom")
    url = ApplicationRunner._enter_application(SimpleNamespace(), page)
    assert url == f"{AVATURE}/Register?jobId=794" == page.url
    # A Phenom job applying on its own site, and other pages, are unchanged.
    page.goto("http://jobs.test/job/link")
    assert (
        ApplicationRunner._enter_application(SimpleNamespace(), page) == "http://jobs.test/apply/1"
    )
