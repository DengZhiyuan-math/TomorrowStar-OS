"""2026-11-20: a LinkedIn job is read once in the App's Chrome, never by script."""

from career_evidence_graph import job_listing_links
from career_evidence_graph.indeed_job_source import fetch_job_source_or_browser
from career_evidence_graph.linkedin_job_source import read_linkedin_job, saved_posting

URL = "https://www.linkedin.com/jobs/view/4486769780"
DESCRIPTION = "About the job\n\n" + "Build retrieval services in Python for customers. " * 8


def page(top=None, apply=None):
    return {
        "top": top or ["Synthetic AG", "ML Engineer", "Zurich, Switzerland · 40 applicants"],
        "description": DESCRIPTION + "\n… more",
        "apply": apply or [],
    }


def test_one_read_names_the_jd_fields_and_the_company_site_route():
    offsite = (
        "https://www.linkedin.com/safety/go/?url=https%3A%2F%2Fjobs.synthetic.example"
        "%2F42&urlhash=x"
    )
    apply = [{"text": "Apply", "label": "Apply on company website", "href": offsite}]
    capture = read_linkedin_job(URL, read=lambda _url: page(apply=apply))
    assert capture["reader"] == "app_browser"
    assert capture["jd_completeness"] == "full" and capture["source_format"] == "job_posting"
    assert capture["body_text"].startswith("Build retrieval services")
    assert "… more" not in capture["body_text"] and "About the job" not in capture["body_text"]
    fields = capture["job_fields"]
    assert (fields["company"], fields["title"], fields["location"]) == (
        "Synthetic AG",
        "ML Engineer",
        "Zurich, Switzerland",
    )
    assert saved_posting(fields) == ("open", "https://jobs.synthetic.example/42")


def test_easy_apply_closed_and_unreadable_pages_keep_their_meaning():
    easy = read_linkedin_job(URL, read=lambda _url: page(apply=[{"text": "Easy Apply"}]))
    assert saved_posting(easy["job_fields"]) == ("easy_apply", None)
    closed = page(top=["Synthetic AG", "ML Engineer", "No longer accepting applications"])
    assert read_linkedin_job(URL, read=lambda _url: closed)["acquisition_status"] == "expired"
    blank = read_linkedin_job(URL, read=lambda _url: {"top": [], "description": ""})
    assert blank["jd_completeness"] == "unknown" and blank["acquisition_status"] == "unavailable"

    def broken(_url):
        raise OSError("Chrome closed")

    failed = read_linkedin_job(URL, read=broken)
    assert failed["error_code"] == "browser_error" and "Chrome closed" in failed["browser_error"]
    # No apply control shown: the route is recorded as read, so matching does not reread.
    unknown = read_linkedin_job(URL, read=lambda _url: page())
    assert unknown["job_fields"]["linkedin_posting"] == "unknown"
    assert saved_posting(unknown["job_fields"]) == (None, None)


def test_the_app_reads_linkedin_only_in_its_browser(monkeypatch, tmp_path):
    from career_evidence_graph import application_job_source, indeed_job_source

    def script_read(_url):
        raise AssertionError("LinkedIn must not be read by script")

    monkeypatch.setattr(indeed_job_source, "fetch_job_source", script_read)
    monkeypatch.setattr(application_job_source, "fetch_job_source", script_read)
    monkeypatch.setattr(
        "career_evidence_graph.linkedin_job_source._read_in_browser", lambda _url: page()
    )
    monkeypatch.setattr(job_listing_links, "LOGIN_ROOT", tmp_path)
    assert fetch_job_source_or_browser(URL)["reader"] == "app_browser"
