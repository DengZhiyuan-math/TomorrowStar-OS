"""A job-board job moves to the employer's page only when that page is the same job."""

from types import SimpleNamespace

from career_evidence_graph import employer_page_search, indeed_job_source, job_listing_links
from career_evidence_graph.employer_page_search import (
    _codex_candidates,
    employer_host,
    find_employer_page,
    job_reference,
    same_job,
)

FIELDS = {
    "title": "Infrastructure Research & Strategy Lead, Unified Global Alternatives",
    "company": "UBS",
    "location": "Zürich, ZH",
}
JD = (
    "Job Reference # 345073BR City Zürich Job Type Full Time. Your role: publish in-depth "
    "infrastructure research and support investment strategy across private markets."
)
EMPLOYER = (
    "https://jobs.ubs.com/TGnewUI/Search/home/HomeWithPreLoad?PageType=JobDetails&jobId=352646"
)
PAGE = (
    "Infrastructure Research &amp; Strategy Lead, Unified Global Alternatives\n"
    "Job Reference # 345073BR\nApply now"
)


class Browser:
    def __init__(self, cards=(), pages=None):
        self.cards, self.pages, self.visited = list(cards), pages or {}, []

    def __enter__(self):
        return self

    def __exit__(self, *_error):
        return False

    def linkedin_cards(self, keywords, fields):
        self.visited.append(("linkedin", keywords))
        return self.cards

    def page_text(self, url):
        self.visited.append(("page", url))
        return url, self.pages.get(url, "")


def test_employer_hosts_and_the_jds_reference():
    assert employer_host(EMPLOYER, "UBS")
    assert employer_host("https://careers.metgroup.com/job/1", "MET Group")
    assert employer_host("https://boards.greenhouse.io/acme/jobs/1", "Other")
    for board in (
        "https://www.jobup.ch/en/jobs/detail/1",
        "https://ch.linkedin.com/jobs/view/1",
        "https://ch.indeed.com/viewjob?jk=1",
        "https://example.com/ubs-jobs",
    ):
        assert not employer_host(board, "UBS")
    assert job_reference(JD) == "345073BR"
    assert job_reference("Reference number: pending") == ""


def test_the_same_job_needs_the_title_and_its_reference_or_most_of_the_jd():
    assert same_job(FIELDS, JD, EMPLOYER, PAGE)
    assert not same_job(FIELDS, JD, EMPLOYER, PAGE.replace("345073BR", "999999BR"))
    assert not same_job(FIELDS, JD, EMPLOYER, PAGE + "\nThis job has expired.")
    assert not same_job(FIELDS, JD, "https://www.jobup.ch/en/jobs/detail/1", PAGE)
    assert not same_job(FIELDS | {"title": "Investor Relations Real Assets"}, JD, EMPLOYER, PAGE)
    # Without a reference number, most of the JD's text must be on the page.
    unreferenced = JD.replace("Job Reference # 345073BR ", "")
    assert same_job(FIELDS, unreferenced, EMPLOYER, FIELDS["title"] + "\n" + unreferenced)
    assert not same_job(FIELDS, unreferenced, EMPLOYER, FIELDS["title"] + "\nApply now")


def test_linkedin_names_the_employer_page_first(monkeypatch):
    cards = [
        {"title": FIELDS["title"], "company": "UBS Card Center", "id": "111"},
        {"title": FIELDS["title"], "company": "UBS", "id": "4478472236"},
    ]
    read = []
    monkeypatch.setattr(
        job_listing_links,
        "posting_status",
        lambda url: read.append(url) or ("open", EMPLOYER + "&codes=ILINKEDIN"),
    )
    monkeypatch.setattr(job_listing_links, "employer_url", lambda target: target)
    browser = Browser(cards, {EMPLOYER + "&codes=ILINKEDIN": PAGE})
    codex = []
    found = find_employer_page(FIELDS, JD, browser=browser, codex=lambda *a: codex.append(a))
    assert found == {"url": EMPLOYER + "&codes=ILINKEDIN", "found_by": "linkedin"}
    assert read == ["https://www.linkedin.com/jobs/view/4478472236/"] and codex == []


def test_codex_search_is_the_fallback_and_an_unverified_page_is_not_used(monkeypatch):
    monkeypatch.setattr(job_listing_links, "posting_status", lambda url: ("easy_apply", None))
    board = "https://www.jobup.ch/en/jobs/detail/1"
    browser = Browser(
        [{"title": FIELDS["title"], "company": "UBS", "id": "4478472236"}],
        {board: PAGE, EMPLOYER: PAGE},
    )
    found = find_employer_page(FIELDS, JD, browser=browser, codex=lambda *a: [board, EMPLOYER])
    assert found == {"url": EMPLOYER, "found_by": "codex"}
    assert ("page", board) in browser.visited
    assert find_employer_page(FIELDS, JD, browser=Browser(), codex=lambda *a: [board]) == {}

    class Broken(Browser):
        def linkedin_cards(self, keywords, fields):
            raise RuntimeError("Chrome did not start")

    assert find_employer_page(FIELDS, JD, browser=Broken(), codex=lambda *a: [EMPLOYER]) == {}


def test_codex_is_asked_with_live_web_search_and_returns_https_urls(monkeypatch):
    calls = []

    def runner(config, prompt, *, runner, timeout_seconds, allow_non_repository):
        calls.append(prompt)
        argv = []
        runner_result = SimpleNamespace(
            structured_result={"urls": [EMPLOYER, "http://insecure.example/job"]}
        )
        monkeypatch.setattr(
            employer_page_search.subprocess, "run", lambda value, **options: argv.extend(value)
        )
        runner(["codex", "exec", "--json", "-"])
        assert 'web_search="live"' in argv and "features.shell_tool=false" in argv
        return runner_result

    assert _codex_candidates(FIELDS, JD, runner=runner) == [EMPLOYER]
    assert '"employer_reference": "345073BR"' in calls[0]


def test_a_company_site_indeed_job_keeps_its_verified_employer_page(monkeypatch):
    from test_indeed_job_source import URL, model, refused

    link = {
        "viewJobButtonLinkModel": {"href": "https://ch.indeed.com/applystart?jk=0c63a5b950793bd1"}
    }
    company_site = model(indeedApplyButtonContainer=None, viewJobButtonLinkContainerModel=link)
    monkeypatch.setattr(indeed_job_source, "fetch_job_source", lambda url: refused(url))
    capture = indeed_job_source.fetch_job_source_or_browser(
        URL,
        read=lambda url: company_site,
        find=lambda fields, description: {"url": EMPLOYER, "found_by": "linkedin"},
    )
    assert capture["job_fields"]["employer_apply_url"] == EMPLOYER
    record = {"documentary_fields": capture["job_fields"]}
    assert indeed_job_source.employer_apply_url(record) == EMPLOYER
    # Nothing found keeps the Indeed page; an Indeed Apply job never looks.
    none = indeed_job_source.fetch_job_source_or_browser(
        URL, read=lambda url: company_site, find=lambda fields, description: {}
    )
    assert "employer_apply_url" not in none["job_fields"]
    looked = []
    indeed_job_source.fetch_job_source_or_browser(
        URL, read=lambda url: model(), find=lambda *a: looked.append(a) or {}
    )
    assert looked == []
    assert indeed_job_source.employer_apply_url({"documentary_fields": {}}) is None
