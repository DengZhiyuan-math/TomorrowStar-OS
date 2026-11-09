"""An application behind an account is recognized beside the match (2026-11-09)."""

import pytest

from career_evidence_graph.application_account_check import (
    check_account,
    classify_url,
    learn_host,
    learned_hosts,
    page_rules,
)


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("https://jobs.ashbyhq.com/keyrock/1", "direct"),
        ("https://saeki.jobs.personio.com/job/2860436", "direct"),
        ("https://boards.greenhouse.io/qube/jobs/1", "direct"),
        ("https://roche.wd3.myworkdayjobs.com/en-US/roche/job/1", "account"),
        ("https://career5.successfactors.eu/career?company=x", "account"),
        ("https://bcg.avature.net/careers/apply", "account"),
        ("https://careers.hero-group.ch/job/Lenzburg-AI-Engineer/1444348733/", None),
        ("https://evil-ashbyhq.com/x", None),
    ],
)
def test_known_application_systems_are_decided_by_address(url, expected):
    assert classify_url(url) == expected


def test_a_learned_site_needs_an_account(tmp_path):
    path = tmp_path / "account-hosts.json"
    learn_host(path, "https://careers.hero-group.ch/job/x/1/")
    learn_host(path, "https://jobs.ashbyhq.com/a/1")  # never learned: known form site
    assert learned_hosts(path) == {"careers.hero-group.ch"}
    assert classify_url("https://careers.hero-group.ch/job/y/2/", learned_hosts(path)) == "account"


@pytest.mark.parametrize(
    ("observation", "expected"),
    [
        ({"url": "https://x.example/apply", "applied": True, "password_field": True}, "account"),
        ({"url": "https://login.microsoftonline.com/x", "text": ""}, "account"),
        # 2026-11-09: Hitachi Energy's Apply link pointed at Workday.
        (
            {"url": "https://x.example/a", "apply_url": "https://h.wd1.myworkdayjobs.com/j"},
            "account",
        ),
        # Apple's job link itself redirected to a sign-in page.
        ({"url": "https://idmsa.apple.com/IDMSWebAuth/signin?x=1"}, "account"),
        ({"url": "https://x.example/auth/sign-in"}, "account"),
        (
            {"url": "https://x.example/a", "applied": True, "text": "Sign in\nCreate an account"},
            "account",
        ),
        (
            {"url": "https://x.example/a", "applied": True, "text": "First name\nLast name\nEmail"},
            "direct",
        ),
        (
            {
                "url": "https://x.example/a",
                "applied": True,
                "text": "Vorname\nNachname\nLebenslauf",
            },
            "direct",
        ),
        (
            {
                "url": "https://x.example/a",
                "applied": True,
                "text": "Sign in or as guest: First name, Email",
            },
            None,
        ),
        # A job posting's own menu "Login" link counts only once Apply was reached.
        ({"url": "https://x.example/job", "applied": False, "text": "Login | Search | Jobs"}, None),
        ({"url": "https://x.example/job", "applied": False, "password_field": True}, None),
    ],
)
def test_page_rules_decide_clear_pages(observation, expected):
    assert page_rules(observation) == expected


def test_only_an_unclear_page_goes_to_the_screenshot_model(tmp_path):
    browsed, judged = [], []

    def browser(url, directory):
        browsed.append(url)
        return {
            "url": url,
            "applied": True,
            "text": "Our culture",
            "screenshot": str(directory / "a.png"),
        }

    def model(observation, directory):
        judged.append(observation["url"])
        return "account"

    # A known site needs no browser at all.
    assert check_account(
        "https://jobs.ashbyhq.com/a/1", tmp_path, browser=browser, model=model
    ) == {"status": "direct", "by": "address", "url": "https://jobs.ashbyhq.com/a/1"}
    assert browsed == [] and judged == []
    result = check_account("https://careers.example/job/1", tmp_path, browser=browser, model=model)
    assert result["status"] == "account" and result["by"] == "screenshot"
    assert judged == ["https://careers.example/job/1"]


def test_a_failed_page_is_unclear_and_leaves_the_fill_to_find_out(tmp_path):
    def browser(url, directory):
        raise TimeoutError("blocked")

    result = check_account("https://careers.example/job/1", tmp_path, browser=browser)
    assert result == {"status": "unclear", "by": "browser_failed", "error": "TimeoutError"}


def test_a_page_without_an_apply_control_skips_the_model(tmp_path):
    judged = []
    result = check_account(
        "https://careers.example/job/1",
        tmp_path,
        browser=lambda url, directory: {"url": url, "applied": False, "text": "Our culture"},
        model=lambda observation, directory: judged.append(1) or "account",
    )
    assert result["status"] == "unclear" and result["by"] == "no_apply_found" and judged == []
