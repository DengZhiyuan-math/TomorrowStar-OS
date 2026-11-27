"""eFinancialCareers and Indeed match-mail recommendations (2026-11-27, user decision)."""

import base64
import gzip
import json

from career_evidence_graph.application_automation import recommendation_key
from career_evidence_graph.application_intake import _canonical
from career_evidence_graph.application_recommendations import normalize_message
from career_evidence_graph.efinancialcareers_job_source import read_efinancialcareers_job
from career_evidence_graph.indeed_job_source import employer_apply_url

JOB = "https://www.efinancialcareers.ch/en/jobs-Switzerland-Zurich-Synthetic_Engineer.id25030395"


def _state(*, external=True, expires="2050-01-01T23:45:00Z"):
    return {
        "https://job-branding-facade.efinancialcareers.com/job/25030395": {
            "body": {
                "data": {
                    "jobId": "SYNTH",
                    "title": "Synthetic Engineer",
                    "brand": {"name": "Synthetic AG"},
                    "description": "<p>Build synthetic services.</p>",
                    "location": {"city": "Zurich", "country": "Switzerland"},
                    "expiration_date": expires,
                }
            }
        },
        "https://job-application.efinancialcareers.com/v1/jobs/SYNTH/apply-information": {
            "body": {
                "data": {
                    "is_external_job_application": external,
                    "external_job_application_url": "https://careers.example.test/42",
                }
            }
        },
    }


def test_job_links_are_identified_by_their_posting_id():
    assert recommendation_key(JOB + "?stlt=token&utm_campaign=x") == (
        "efinancialcareers",
        "25030395",
    )
    assert recommendation_key("https://www.efinancialcareers.ch/en/myefc/matching-jobs") is None
    assert _canonical(JOB + "?stlt=token") == JOB


def test_page_names_the_job_and_the_employer_application_page():
    capture = read_efinancialcareers_job(JOB + "?stlt=token", read=lambda url: _state())
    assert capture["acquisition_status"] == "available"
    assert capture["jd_completeness"] == "full"
    assert capture["job_fields"]["company"] == "Synthetic AG"
    assert "Zurich, Switzerland" in capture["body_text"]
    record = {"documentary_fields": capture["job_fields"]}
    assert employer_apply_url(record) == "https://careers.example.test/42"


def test_internal_application_keeps_the_job_board_page_and_expired_job_is_marked():
    capture = read_efinancialcareers_job(JOB, read=lambda url: _state(external=False))
    assert employer_apply_url({"documentary_fields": capture["job_fields"]}) is None
    expired = read_efinancialcareers_job(
        JOB, read=lambda url: _state(expires="2020-01-01T00:00:00Z")
    )
    assert expired["acquisition_status"] == "expired"


def test_unreadable_page_stays_a_receipt():
    def refuse(url):
        raise RuntimeError("closed")

    for read in (lambda url: None, lambda url: {}, refuse):
        capture = read_efinancialcareers_job(JOB, read=read)
        assert capture["acquisition_status"] == "unavailable"
        assert capture["body_text"] == ""


def test_indeed_match_mail_redirect_names_its_job():
    target = "https://ch.indeed.com/rc/clk?jk=24d27d6ff34defb3&from=email"
    payload = base64.urlsafe_b64encode(gzip.compress(json.dumps({"u": target}).encode()))
    link = "https://cts.indeed.com/v3/" + payload.decode().rstrip("=") + "/signature"
    foreign = base64.urlsafe_b64encode(gzip.compress(b'{"u": "https://evil.test/?jk=1"}'))
    message = normalize_message(
        {
            "message_id": "m1",
            "body_text": f"View job: {link}",
            "links": ["https://cts.indeed.com/v3/" + foreign.decode()],
        }
    )
    jobs = {_canonical(value) for value in message["links"]} - {None}
    assert jobs == {"https://ch.indeed.com/viewjob?jk=24d27d6ff34defb3"}


def test_only_a_read_job_without_an_external_page_is_internal_apply():
    from career_evidence_graph.efinancialcareers_job_source import internal_apply

    read = {"title": "Synthetic Engineer", "company": "Synthetic AG"}
    assert internal_apply({"url": JOB, "documentary_fields": read})
    external = read | {"employer_apply_url": "https://careers.example.test/42"}
    assert not internal_apply({"url": JOB, "documentary_fields": external})
    assert not internal_apply({"url": JOB, "documentary_fields": {}})
    assert not internal_apply(
        {"url": "https://careers.example.test/42", "documentary_fields": read}
    )
