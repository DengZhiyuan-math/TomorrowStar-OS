"""Fixed Ashby bootstrap exercises the existing Runner without employer transport."""

import json
from types import SimpleNamespace

import pytest
from test_synthetic_browser_mode import assert_synthetic_resume, create_browser, synthetic_runner
from worker_preview_support import advance_until


def test_browser_scenario_selects_only_the_fixed_ashby_application():
    from career_evidence_graph.application_worker_fixtures import browser_fixture_job_url

    assert browser_fixture_job_url("ashby-bootstrap") == (
        "https://jobs.ashbyhq.com/synthetic/00000000-0000-0000-0000-000000000001/application"
    )
    assert browser_fixture_job_url("integration-upload") == (
        "https://apply.workable.com/synthetic-employer/j/SYNTHETIC1/apply/"
    )
    assert browser_fixture_job_url("dom") == "https://careers.example.test/jobs/browser-synthetic"


def test_fixed_ashby_transport_stays_behind_the_original_guard(tmp_path):
    from test_ashby_bootstrap import QUERIES

    from career_evidence_graph.application_worker_fixtures import (
        BROWSER_ASHBY_URL,
        install_browser_fixture,
    )

    root = tmp_path / "ashby"
    assert create_browser(root).returncode == 0
    (root / "browser-fixture.json").write_text(
        json.dumps({"schemaVersion": 1, "scenario": "ashby-bootstrap"})
    )
    routes, guarded = [], []
    permitted = True

    def guard(route):
        guarded.append(route.request.url)
        if not permitted:
            route.abort("blockedbyclient")
            return
        response = route.fetch(max_redirects=0, max_retries=0, timeout=10000)
        route.fulfill(response=response)

    install_browser_fixture(
        SimpleNamespace(
            route=lambda pattern, callback: routes.append(callback),
            route_web_socket=lambda *args: None,
        ),
        SimpleNamespace(_live_guard=guard),
        root,
    )

    def dispatch(method, url, payload=None):
        received = []
        request = SimpleNamespace(method=method, url=url, post_data_json=payload)
        routes[0](
            SimpleNamespace(
                request=request,
                fulfill=lambda **values: received.append(values),
                abort=lambda reason: received.append({"aborted": reason}),
                fetch=lambda **kwargs: (_ for _ in ()).throw(AssertionError("External fetch")),
            )
        )
        return received[0]

    assert "ApiJobPosting" in dispatch("GET", BROWSER_ASHBY_URL)["body"]
    for operation in QUERIES:
        payload = {
            "operationName": operation,
            "query": QUERIES[operation],
            "variables": {"organizationHostedJobsPageName": "synthetic"},
        }
        response = dispatch(
            "POST", "https://jobs.ashbyhq.com/api/non-user-graphql?op=" + operation, payload
        )
        assert response["status"] == 200
        if operation == "ApiJobPosting":
            assert response["json"]["data"]["jobPosting"]["applicationForm"]["id"]
        else:
            assert response["json"]["data"]["organization"]["hostedJobsPageSlug"] == "synthetic"
    assert len(guarded) == 3
    with pytest.raises(ValueError, match="synthetic-browser-upload-target"):
        dispatch("GET", "https://example.com/unrelated")
    permitted = False
    assert dispatch("GET", BROWSER_ASHBY_URL) == {"aborted": "blockedbyclient"}


@pytest.mark.worker_browser
def test_fixed_ashby_public_bootstrap_keeps_unsupported_upload_result_unknown(
    tmp_path, monkeypatch
):
    from playwright.sync_api import Locator

    selections = []
    set_input_files = Locator.set_input_files

    def record_selection(control, *args, **kwargs):
        selections.append(args)
        return set_input_files(control, *args, **kwargs)

    monkeypatch.setattr(Locator, "set_input_files", record_selection)
    # This fixture implements only bootstrap reads, with no file-link transport.
    with synthetic_runner(tmp_path, monkeypatch, "ashby-bootstrap") as (service, runner, context):
        job = advance_until(service, runner, lambda row: row["status"] == "needs_recheck")
        page = runner.pages[job["application_id"]]
        assert job["page_open"] and job["intent"]["action"] == "upload"
        assert job["reason"] == "draft_result_unknown"
        intent = dict(job["intent"])
        assert_synthetic_resume(page, job)
        assert page.locator("form").count() == 1
        assert runner.drafts[page].counts == {"initial": 1, "organization": 1}
        assert not runner.blocked_pages
        runner.tick()
        runner.pump()
        job = service.store.load()["jobs"][0]
        assert job["status"] == "needs_recheck", job["reason"]
        assert job["intent"] == intent
        assert len(selections) == 1
        assert not any(o.get("action") == "fill" for o in job["observations"])
        uploads = [o for o in job["observations"] if o.get("action") == "upload"]
        assert uploads == []
        assert page.locator("input[name=unknown]").input_value() == ""
        assert page.evaluate("window.finalActions") == 0
        assert runner.drafts[page].counts == {"initial": 1, "organization": 1}
