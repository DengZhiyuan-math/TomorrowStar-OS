"""A LinkedIn job resolves to the employer page it names; anything else keeps LinkedIn."""

import json

from career_evidence_graph import job_listing_links as links

PAGE = (
    '{\\"payload\\":{\\"jobId\\":\\"4477077634\\",\\"companyName\\":\\"Example\\",'
    '\\"isOnsiteApply\\":false,'
    '\\"offsiteApplyUrl\\":\\"https://example.onlyfy.jobs/job/abc\\"}}'
)
EASY_APPLY = '{\\"jobId\\":\\"4477077634\\",\\"isOnsiteApply\\":true}'
JOB = "https://www.linkedin.com/jobs/view/4477077634/"


def signed_in(tmp_path):
    cookie = {"name": "li_at", "value": "synthetic", "domain": ".www.linkedin.com"}
    (tmp_path / "browser-login-state.json").write_text(json.dumps({"cookies": [cookie]}))
    links.configure(tmp_path)


def test_offsite_url_is_read_for_its_job_only():
    assert links.offsite_apply_url(PAGE, "4477077634") == "https://example.onlyfy.jobs/job/abc"
    assert links.offsite_apply_url(PAGE, "1") is None
    assert links.offsite_apply_url(EASY_APPLY, "4477077634") is None


def test_resolves_to_the_final_employer_page(tmp_path):
    signed_in(tmp_path)
    final = "https://example.onlyfy.jobs/en/job/abc"
    resolved = links.resolve_apply_url(
        JOB, read=lambda url, cookies: PAGE, fetch=lambda url: {"final_url": final}
    )
    assert resolved == final


def test_keeps_linkedin_without_login_or_for_easy_apply(tmp_path):
    links.configure(tmp_path)
    assert links.resolve_apply_url(JOB, read=lambda *_: PAGE) is None
    signed_in(tmp_path)
    assert links.resolve_apply_url(JOB, read=lambda *_: EASY_APPLY) is None
    assert links.resolve_apply_url("https://jobs.lever.co/x/1", read=lambda *_: PAGE) is None
    links.configure(None)


def test_escaped_url_and_a_refused_direct_read(tmp_path):
    signed_in(tmp_path)
    page = PAGE.replace("job/abc", "job/abc?a=1\\u0026src=LinkedIn")
    assert links.offsite_apply_url(page, "4477077634").endswith("abc?a=1&src=LinkedIn")
    resolved = links.resolve_apply_url(
        JOB, read=lambda *_: page, fetch=lambda url: {"error_code": "network_error"}
    )
    assert resolved == "https://example.onlyfy.jobs/job/abc?a=1&src=LinkedIn"
    links.configure(None)


PHENOM = (
    "https://careers.bcg.com/global/en/job/BCG1US794EXTERNALENGLOBAL/AI-Tech-Consultant"
    "?utm_source=linkedin&utm_medium=phenom-feeds"
)
AVATURE = "https://platinion.avature.net/CareersDeEn/ApplicationMethods?jobId=794"


def test_a_phenom_job_applying_elsewhere_opens_on_that_site():
    # 2026-11-05: BCG Platinion's Phenom page renders no Apply button; its data names
    # Avature, and the native takeover refused a page that had moved to Avature itself.
    page = (
        '<script>phApp.ddo = {"jobDetail":{"data":{"job":{"isExternalApply":true,'
        f'"applyUrl":"{AVATURE}"}}}}}};</script>'
    )
    reads = []

    def read(url):
        reads.append(url)
        return page

    fetch = lambda url: {"final_url": url}  # noqa: E731
    assert links.employer_url(PHENOM, fetch=fetch, read_page=read) == AVATURE
    # A Phenom job applying on its own site, or a page naming none, keeps the page.
    internal = page.replace('"isExternalApply":true', '"isExternalApply":false')
    assert links.employer_url(PHENOM, fetch=fetch, read_page=lambda url: internal) == PHENOM
    same_site = page.replace(AVATURE, "https://careers.bcg.com/apply/794")
    assert links.employer_url(PHENOM, fetch=fetch, read_page=lambda url: same_site) == PHENOM

    def unreadable(url):
        raise OSError("refused")

    assert links.employer_url(PHENOM, fetch=fetch, read_page=unreadable) == PHENOM
    # Only LinkedIn's Phenom feed links are read a second time.
    onlyfy = "https://example.onlyfy.jobs/job/abc"
    assert links.employer_url(onlyfy, fetch=fetch, read_page=read) == onlyfy
    assert reads == [PHENOM]


def test_only_a_page_that_says_so_counts_as_gone():
    # 2026-11-11: read before matching; an unclear read never removes a job.
    def fetch(receipt):
        return lambda url: receipt

    assert links.posting_gone(JOB, fetch=fetch({"acquisition_status": "expired"}))
    assert not links.posting_gone(JOB, fetch=fetch({"acquisition_status": "login_required"}))
    assert not links.posting_gone(JOB, fetch=fetch({"error_code": "timeout"}))
    assert not links.posting_gone(JOB, fetch=fetch({"acquisition_status": "available"}))

    def offline(url):
        raise OSError

    assert not links.posting_gone(JOB, fetch=offline)
