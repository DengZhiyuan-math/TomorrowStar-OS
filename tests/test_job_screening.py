"""Conservative, read-only screening of synthetic job records."""

from copy import deepcopy
from datetime import date

import pytest

from career_evidence_graph.application_automation import deadline_passed
from career_evidence_graph.job_screening import screen_applications

LEVER = "https://jobs.lever.co/example/12345678-1234-1234-1234-123456789abc"
TODAY = date(2026, 10, 10)


def record(**changes):
    return {
        "id": "synthetic",
        "company": "Example",
        "role_title": "AI Engineer",
        "status": "drafting",
        "url": LEVER,
        **changes,
    }


def screen(**changes):
    return screen_applications([record(**changes)], today=TODAY)[0]["screening"]


def test_unknown_conditions_remain_pending_without_changing_original_record():
    original = [record()]
    before = deepcopy(original)
    result = screen_applications(original, today=TODAY)
    assert original == before
    hint = result[0]["screening"]
    assert hint["worker_preparable"]
    assert hint["category"] == "review"
    assert any("资格" in reason for reason in hint["review_reasons"])
    assert any("JD" in reason for reason in hint["review_reasons"])
    assert result[0]["status"] == "drafting"


@pytest.mark.parametrize(
    "title",
    ["AI Engineer", "ML Scientist", "Quantitative Researcher", "量化开发", "NLP Researcher"],
)
def test_target_titles(title):
    assert screen(role_title=title)["target_relevant"]


def test_title_words_and_explicit_track_do_not_infer_fit_from_company_or_jd():
    assert not screen(role_title="Chair Designer", company="AI Labs", job_description="We use ML")[
        "target_relevant"
    ]
    assert screen(role_title="Research Engineer", track="Quant")["target_relevant"]
    assert screen(role_title="Research Engineer - Inference")["target_relevant"]
    assert screen(role_title="Research Engineer", track="AI")["target_relevant"]


@pytest.mark.parametrize(
    "url", [LEVER + "/apply?source=test#form", LEVER.replace("jobs.lever.co", "jobs.eu.lever.co")]
)
def test_lever_duplicate_identity_ignores_tracking_and_region_alias(url):
    results = screen_applications([record(), record(id="duplicate", url=url)])
    assert all(row["screening"]["duplicate"] for row in results)
    assert all(not row["screening"]["worker_preparable"] for row in results)


def test_greenhouse_alias_duplicate_but_distinct_enterprise_query_ids_remain_distinct():
    rows = [
        record(url="https://boards.greenhouse.io/example/jobs/123"),
        record(id="second", url="https://job-boards.greenhouse.io/example/jobs/123/?source=x"),
    ]
    assert all(row["screening"]["duplicate"] for row in screen_applications(rows))
    rows = [
        record(url="https://careers.example/jobs?id=1"),
        record(id="second", url="https://careers.example/jobs?id=2"),
    ]
    assert all(not row["screening"]["duplicate"] for row in screen_applications(rows))
    rows = [record(), record(id="second", url=LEVER.replace("9abc", "9abd"))]
    assert all(not row["screening"]["duplicate"] for row in screen_applications(rows))


@pytest.mark.parametrize(
    "host,platform",
    [
        ("jobs.ashbyhq.com", "ashby"),
        ("jobs.smartrecruiters.com", "smartrecruiters"),
        ("example.myworkdayjobs.com", "workday"),
        ("career.successfactors.eu", "successfactors"),
        ("careers-example.icims.com", "icims"),
        ("example.taleo.net", "taleo"),
        ("www.linkedin.com", "linkedin"),
        ("jobs.lever.co.attacker.example", "other"),
    ],
)
def test_platform_detection_never_enables_an_unsupported_site(host, platform):
    hint = screen(url=f"https://{host}/job/123")
    assert hint["platform"] == platform
    assert hint["category"] == "manual"
    assert not hint["worker_supported"]
    assert not hint["worker_preparable"]


@pytest.mark.parametrize(
    "value,expired",
    [
        ("2026-10-09", True),
        ("2026-10-10", False),
        ("2026-10-11", False),
        ("2026-02-30", False),
        ("待定", False),
        ("", False),
        (None, False),
    ],
)
def test_only_valid_saved_past_deadlines_exclude(value, expired):
    assert deadline_passed(value, TODAY) is expired
    assert screen(deadline=value)["expired"] is expired
    assert screen(deadline=value)["worker_preparable"] is not expired


def test_existing_application_status_is_preserved_and_cannot_enter_batch():
    row = screen_applications([record(status="applied")])[0]
    assert row["status"] == "applied"
    assert row["screening"]["category"] == "recorded"
    assert not row["screening"]["worker_preparable"]


def test_linkless_history_is_shown_and_same_role_is_excluded():
    rows = [
        record(),
        record(id="prior", company="EXAMPLE", role_title="AI engineer", status="applied", url=""),
        record(id="different", role_title="Quant Internship", url=LEVER.replace("9abc", "9abd")),
    ]
    result = screen_applications(rows)
    assert result[0]["screening"]["duplicate"]
    assert not result[0]["screening"]["worker_preparable"]
    assert result[0]["screening"]["history_matches"] == [
        {"id": "prior", "status": "applied", "basis": "company_role"}
    ]
    hint = result[2]["screening"]
    assert not hint["duplicate"]
    assert hint["worker_preparable"]
    assert hint["company_history"] == [
        {"id": "prior", "role_title": "AI engineer", "status": "applied", "url": ""}
    ]
    assert any("同公司已有投递进度" in reason for reason in hint["review_reasons"])
    assert rows[1]["status"] == "applied"


def test_unknown_company_placeholder_is_not_a_company_identity():
    rows = [
        record(company="Unknown Company"),
        record(id="prior", company="Unknown Company", status="applied", url=""),
    ]
    hint = screen_applications(rows)[0]["screening"]
    assert not hint["duplicate"]
    assert hint["company_history"] == []
    assert hint["worker_preparable"]


@pytest.mark.parametrize(
    "jd,mismatch",
    [
        ("French B2 required.", True),
        ("Minimum German level C1.", True),
        ("Fluency in French is mandatory.", True),
        ("French fluency preferred.", False),
        ("Fluent German is not required.", False),
        ("French or English fluency required.", False),
        ("English B2 and German A2 required.", False),
        ("French A2 or higher required.", False),
        ("We process French B2 datasets.", False),
        ("English fluency is mandatory, basic German is sufficient.", False),
    ],
)
def test_only_explicit_unmet_language_requirements_exclude(jd, mismatch):
    hint = screen_applications(
        [record(job_description=jd)], language_levels={"French": "A2", "German": "A2"}
    )[0]["screening"]
    assert hint["language_mismatch"] is mismatch
    assert hint["worker_preparable"] is not mismatch


def test_unknown_language_and_uncertain_fluency_threshold_remain_pending():
    row = record(job_description="French fluency is mandatory.")
    for levels in (None, {"French": "B1"}, {"French": "invalid"}):
        hint = screen_applications([row], language_levels=levels)[0]["screening"]
        assert not hint["language_mismatch"]
        assert hint["review_reasons"]


def test_internship_dates_experience_and_authorization_stay_distinct_review_items():
    hint = screen(
        role_title="Senior Quant Internship",
        job_description="At least 5 years experience. Work authorization required.",
    )
    reasons = " ".join(hint["review_reasons"])
    assert all(term in reasons for term in ("职级", "工作年限", "毕业时间", "签证"))
    assert hint["worker_preparable"]


REVIEWED = {
    "job_description": "Build and evaluate ML systems.",
    "jd_match": "possible",
    "evidence_match": "transferable",
    "personal_priority": "normal",
    "target_company": "normal",
    "compensation_priority": "normal",
}


def test_saved_jd_and_linked_documents_do_not_infer_match_or_value():
    hint = screen(job_description="ML systems", linked_evidence=["a" * 24])
    assert hint["application_route"] == "review"
    assert not hint["batch_preparable"]
    assert hint["worker_preparable"]


@pytest.mark.parametrize(
    "changes,route,reason",
    [
        ({}, "batch", "已核对"),
        ({"target_company": "target"}, "manual", "目标公司"),
        ({"compensation_priority": "exceptional"}, "manual", "超高薪资"),
        ({"personal_priority": "high"}, "manual", "优先意愿高"),
        ({"jd_match": "strong", "evidence_match": "direct"}, "manual", "高匹配"),
        ({"jd_match": "weak"}, "hold", "匹配较低"),
        ({"evidence_match": "missing"}, "hold", "证据不足"),
        ({"personal_priority": "low"}, "hold", "优先意愿低"),
        ({"compensation_priority": ""}, "review", "薪资吸引力"),
        ({"target_company": ""}, "review", "目标公司"),
        ({"jd_match": ""}, "review", "JD 匹配"),
        ({"application_strategy": "unknown"}, "review", "未知值"),
        ({"target_company": "target", "application_strategy": "batch"}, "batch", "人工分流"),
        ({"application_strategy": "manual"}, "manual", "人工分流"),
    ],
)
def test_comprehensive_routing_explains_saved_judgments(changes, route, reason):
    hint = screen(**(REVIEWED | changes))
    assert hint["application_route"] == route
    assert reason in " ".join(hint["route_reasons"])
    assert hint["batch_preparable"] is (route == "batch")
    assert hint["precision_preparable"] is (route == "manual")


def test_high_value_with_unknown_fit_requires_human_attention():
    hint = screen(target_company="target", compensation_priority="exceptional")
    assert hint["application_route"] == "manual"
    assert not hint["batch_preparable"]
    assert len(hint["route_reasons"]) == 2


@pytest.mark.parametrize(
    "changes,route",
    [({"deadline": "2026-10-09"}, "excluded"), ({"status": "applied"}, "recorded")],
)
def test_manual_routing_override_cannot_bypass_existing_gates(changes, route):
    hint = screen(application_strategy="batch", **changes)
    assert hint["application_route"] == route
    assert not hint["batch_preparable"]


@pytest.mark.parametrize("application_id", ["synthetic", "duplicate", "prior", "missing"])
def test_targeted_screening_matches_bulk_and_preserves_all_history(application_id):
    rows = [
        record(job_description="German B2 required."),
        record(id="duplicate", url=LEVER + "/apply?source=synthetic"),
        record(id="prior", role_title="Research Engineer", status="applied", url=""),
    ]
    original = deepcopy(rows)
    expected = [
        row
        for row in screen_applications(rows, today=TODAY, language_levels={"German": "B2"})
        if row["id"] == application_id
    ]
    calls = []

    def levels(context):
        calls.append(context["id"])
        return {"German": "B2"}

    targeted = screen_applications(
        rows, application_id=application_id, today=TODAY, language_levels=levels
    )

    assert targeted == expected
    assert calls == ([] if application_id == "missing" else [application_id])
    assert rows == original
    if application_id == "synthetic":
        hint = targeted[0]["screening"]
        assert hint["duplicate"]
        assert hint["history_matches"] == [
            {"id": "duplicate", "status": "drafting", "basis": "job_url"}
        ]
        assert hint["company_history"] == [
            {field: rows[2][field] for field in ("id", "role_title", "status", "url")}
        ]
