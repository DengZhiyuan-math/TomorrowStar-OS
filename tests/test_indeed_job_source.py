"""An Indeed job refused by the direct read is read once in the App's Chrome."""

from career_evidence_graph import indeed_job_source
from career_evidence_graph.indeed_job_source import (
    apply_route,
    fetch_job_source_or_browser,
    indeed_capture,
)

URL = "https://ch.indeed.com/viewjob?jk=0c63a5b950793bd1"


def model(**changes):
    """The shape of window._initialData.viewJobClientSideModel seen on 2026-11-05."""
    value = {
        "jobKey": "0c63a5b950793bd1",
        "indeedApplyButtonContainer": {
            "indeedApplyAttributes": "data-indeed-apply-jobCountry='CH'"
        },
        "viewJobButtonLinkContainerModel": None,
        "jobInfoWrapperModel": {
            "jobInfoModel": {
                "jobInfoHeaderModel": {
                    "jobTitle": "LNG Structurer",
                    "companyName": "MET Group",
                    "formattedLocation": "Baar, ZG",
                },
                "sanitizedJobDescription": "<div><b>Company Description</b><p>MET builds"
                " supply structures.</p><ul><li>Model LNG cargoes</li></ul></div>",
                "showExpiredHeader": False,
                "expiredJobMetadataModel": None,
            }
        },
    }
    value.update(changes)
    return value


def refused(url=URL):
    return {
        "capture_id": "c" * 32,
        "url": url,
        "final_url": url,
        "redirects": [],
        "body_text": "",
        "acquisition_status": "login_required",
        "jd_completeness": "unknown",
        "source_format": "page",
        "job_fields": {},
        "http_status": 401,
    }


def test_the_view_job_model_becomes_a_full_job_posting():
    capture = indeed_capture(refused(), model(), "0c63a5b950793bd1")
    assert capture["acquisition_status"] == "available"
    assert capture["jd_completeness"] == "full" and capture["source_format"] == "job_posting"
    assert capture["job_fields"] == {
        "title": "LNG Structurer",
        "company": "MET Group",
        "location": "Baar, ZG",
        "indeed_apply_route": "indeed_apply",
    }
    assert "Model LNG cargoes" in capture["body_text"] and "<" not in capture["body_text"]
    assert capture["body_text"].endswith("Job location\nBaar, ZG")
    assert capture["url"] == URL and capture["capture_id"] == "c" * 32
    assert "http_status" not in capture and capture["reader"] == "app_browser"
    assert apply_route({"documentary_fields": capture["job_fields"]}) == "indeed_apply"


def test_a_company_site_route_and_an_expired_or_other_job():
    link = {
        "viewJobButtonLinkModel": {"href": "https://ch.indeed.com/applystart?jk=0c63a5b950793bd1"}
    }
    company = indeed_capture(
        refused(),
        model(indeedApplyButtonContainer=None, viewJobButtonLinkContainerModel=link),
        "0c63a5b950793bd1",
    )
    assert company["job_fields"]["indeed_apply_route"] == "company_site"
    expired = model()
    expired["jobInfoWrapperModel"]["jobInfoModel"]["showExpiredHeader"] = True
    assert indeed_capture(refused(), expired, "0c63a5b950793bd1")["acquisition_status"] == (
        "expired"
    )
    # Another job's page, or one without a description, keeps the refused receipt.
    assert indeed_capture(refused(), model(jobKey="ffffffffffffffff"), "0c63a5b950793bd1") == (
        refused()
    )
    empty = model()
    empty["jobInfoWrapperModel"]["jobInfoModel"]["sanitizedJobDescription"] = ""
    assert indeed_capture(refused(), empty, "0c63a5b950793bd1") == refused()
    assert apply_route({"documentary_fields": {"indeed_apply_route": "other"}}) == ""


def test_only_a_refused_indeed_read_opens_the_browser(monkeypatch):
    reads = []

    def read(url):
        reads.append(url)
        return model()

    monkeypatch.setattr(indeed_job_source, "fetch_job_source", lambda url: refused(url))
    capture = fetch_job_source_or_browser(URL, read=read)
    assert reads == [URL] and capture["jd_completeness"] == "full"
    # LinkedIn, a full direct read and an unreadable page never open it again.
    linkedin = "https://www.linkedin.com/jobs/view/1000"
    assert fetch_job_source_or_browser(linkedin, read=read) == refused(linkedin)
    monkeypatch.setattr(
        indeed_job_source,
        "fetch_job_source",
        lambda url: refused(url) | {"acquisition_status": "available", "jd_completeness": "full"},
    )
    fetch_job_source_or_browser(URL, read=read)
    monkeypatch.setattr(indeed_job_source, "fetch_job_source", lambda url: refused(url))
    assert fetch_job_source_or_browser(URL, read=lambda url: None) == refused()

    def broken(url):
        raise RuntimeError("Chrome did not start")

    failed = fetch_job_source_or_browser(URL, read=broken)
    assert failed["acquisition_status"] == "login_required"
    assert failed["browser_error"] == "RuntimeError: Chrome did not start"
    assert "error_code" not in failed

    def verification(url):
        raise indeed_job_source.VerificationRequired(url)

    held = fetch_job_source_or_browser(URL, read=verification)
    assert held["acquisition_status"] == "login_required"
    assert held["error_code"] == "verification_required"
    assert reads == [URL]


def test_without_a_saved_login_root_the_refused_receipt_stays(monkeypatch):
    from career_evidence_graph import job_listing_links

    monkeypatch.setattr(job_listing_links, "LOGIN_ROOT", None)
    monkeypatch.setattr(indeed_job_source, "fetch_job_source", lambda url: refused(url))
    assert fetch_job_source_or_browser(URL) == refused()
