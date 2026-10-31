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
