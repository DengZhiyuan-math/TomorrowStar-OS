"""Public Ashby bootstrap through the existing Runner; no external requests."""

import json
from types import SimpleNamespace

import pytest
from test_ashby_drafts import URL, bounded_route, form, setup_service

from career_evidence_graph.application_worker_browser import ApplicationRunner

ORG = "ApiOrganizationFromHostedJobsPageName"
QUERIES = {
    "ApiJobPosting": (
        "query ApiJobPosting($organizationHostedJobsPageName: String!, $jobPostingId: String!) {"
        " jobPosting(organizationHostedJobsPageName: $organizationHostedJobsPageName,"
        " jobPostingId: $jobPostingId) { ...PostingParts } }"
        " fragment PostingParts on JobPosting { id title applicationForm { id } }"
    ),
    ORG: (
        "query ApiOrganizationFromHostedJobsPageName($organizationHostedJobsPageName: String!,"
        " $searchContext: OrganizationSearchContext) { organization:"
        " organizationFromHostedJobsPageName(organizationHostedJobsPageName:"
        " $organizationHostedJobsPageName, searchContext: $searchContext)"
        " { ...OrganizationParts } }"
        " fragment OrganizationParts on Organization { organizationId name hostedJobsPageSlug }"
    ),
}


def public_request(page, operation, *, variables=None, query=None):
    class Request(SimpleNamespace):
        __hash__ = object.__hash__

    return Request(
        method="POST",
        url="https://jobs.ashbyhq.com/api/non-user-graphql?op=" + operation,
        resource_type="fetch",
        frame=SimpleNamespace(page=page),
        headers={"content-type": "application/json"},
        post_data_buffer=json.dumps(
            {
                "operationName": operation,
                "query": query or QUERIES[operation],
                "variables": variables
                or {
                    "organizationHostedJobsPageName": "synthetic",
                    **({"jobPostingId": URL.split("/")[4]} if operation == "ApiJobPosting" else {}),
                },
            }
        ).encode(),
        is_navigation_request=lambda: False,
    )


@pytest.mark.parametrize("operation", ["ApiJobPosting", ORG])
def test_public_bootstrap_fragments_use_existing_runner_guard(tmp_path, monkeypatch, operation):
    from career_evidence_graph.ashby_drafts import DraftSession

    service, _ = setup_service(tmp_path, monkeypatch)
    runner = ApplicationRunner(service.store, None)
    job = service.store.load()["jobs"][0]
    page = object()
    runner.pages[job["application_id"]] = page
    runner.drafts[page] = DraftSession(job)
    route = bounded_route(public_request(page, operation))

    runner._live_guard(route)

    assert route.outcome == "allowed"
    assert len(route.fetch_calls) == 1
    assert not runner.blocked_pages


@pytest.mark.parametrize("context", ["omitted", None, "JobPosting"])
@pytest.mark.parametrize("renamed", [False, True])
def test_public_organization_names_and_optional_context_need_no_grant(
    tmp_path, monkeypatch, context, renamed
):
    from career_evidence_graph.ashby_drafts import DraftSession

    service, _ = setup_service(tmp_path, monkeypatch)
    runner = ApplicationRunner(service.store, None)
    job = service.store.load()["jobs"][0]
    page = object()
    runner.pages[job["application_id"]] = page
    runner.drafts[page] = DraftSession(job)
    variables = {"organizationHostedJobsPageName": "synthetic"}
    if context != "omitted":
        variables["searchContext"] = context
    operation = "PublicOrganizationV2" if renamed else ORG
    query = (
        QUERIES[ORG]
        .replace(ORG, operation)
        .replace("organizationId name", "organizationId # new response fields\n publicWebsite name")
    )
    route = bounded_route(public_request(page, operation, variables=variables, query=query))
    before = service.store.load()

    runner._live_guard(route)

    assert route.outcome == "allowed"
    assert service.store.load() == before
    assert runner.drafts[page].public_request is None  # Org reads cannot become form readbacks.


@pytest.mark.parametrize(
    "change",
    [
        "organization",
        "posting",
        "extra",
        "context",
        "mutation",
        "mixed",
        "second_query",
        "literal",
        "endpoint",
        "redirect",
        "undefined_fragment",
        "required_context",
        "missing_unknown_optional",
    ],
)
def test_bootstrap_rejects_out_of_scope_or_write_semantics(tmp_path, monkeypatch, change):
    from career_evidence_graph.ashby_drafts import DraftSession

    service, _ = setup_service(tmp_path, monkeypatch)
    runner = ApplicationRunner(service.store, None)
    job = service.store.load()["jobs"][0]
    page = object()
    runner.pages[job["application_id"]] = page
    runner.drafts[page] = DraftSession(job)
    variables = {"organizationHostedJobsPageName": "synthetic"}
    query = QUERIES[ORG]
    if change == "organization":
        variables["organizationHostedJobsPageName"] = "foreign"
    elif change == "posting":
        query = QUERIES["ApiJobPosting"].replace("ApiJobPosting", ORG)
        variables["jobPostingId"] = "00000000-0000-0000-0000-000000000002"
    elif change == "extra":
        variables["email"] = "synthetic@example.invalid"
    elif change == "context":
        variables["searchContext"] = "JobBoard"
    elif change == "mutation":
        query = query.replace("query ", "mutation ", 1)
    elif change == "mixed":
        query = query.replace("{ ...OrganizationParts } }", "{ id } submitApplication { id } }")
    elif change == "second_query":
        query += " query Another { jobPosting { id } }"
    elif change == "literal":
        query = query.replace(
            "organizationHostedJobsPageName: $organizationHostedJobsPageName",
            'organizationHostedJobsPageName: "foreign"',
        )
    elif change == "undefined_fragment":
        query = query.split(" fragment ")[0]
    elif change == "required_context":
        query = query.replace("OrganizationSearchContext)", "OrganizationSearchContext!)")
    elif change == "missing_unknown_optional":
        query = query.replace(
            "$searchContext: OrganizationSearchContext)",
            "$unrelated: String)",
        ).replace("searchContext: $searchContext", "unrelated: $unrelated")
    request = public_request(page, ORG, variables=variables, query=query)
    if change == "endpoint":
        request.url += "&unreviewed=true"
    elif change == "redirect":
        request.redirected_from = object()
    route = bounded_route(request)

    runner._live_guard(route)

    assert route.outcome == "blocked"
    assert not route.fetch_calls
    assert not runner.drafts[page].pending


@pytest.mark.parametrize("slug", ["synthetic", "foreign"])
def test_organization_response_checks_returned_identity(tmp_path, monkeypatch, slug):
    from career_evidence_graph.ashby_drafts import DraftSession

    service, _ = setup_service(tmp_path, monkeypatch)
    runner = ApplicationRunner(service.store, None)
    job = service.store.load()["jobs"][0]
    page = object()
    runner.pages[job["application_id"]] = page
    draft = runner.drafts[page] = DraftSession(job)
    request = public_request(page, ORG)
    route = bounded_route(request)
    runner._live_guard(route)

    runner._draft_response(
        SimpleNamespace(
            request=request,
            status=200,
            json=lambda: {
                "data": {
                    "organization": {
                        "organizationId": "synthetic-org",
                        "hostedJobsPageSlug": slug,
                    }
                }
            },
        )
    )

    assert draft.failed is (slug != "synthetic")
    assert (page in runner.blocked_pages) is (slug != "synthetic")
    assert draft.form is None


def test_public_read_does_not_resolve_retained_unknown_open(tmp_path, monkeypatch):
    from career_evidence_graph.ashby_drafts import DraftSession

    service, _ = setup_service(tmp_path, monkeypatch)
    state = service.store.load()
    job = state["jobs"][0]
    runner = ApplicationRunner(service.store, None)
    assert runner.authorize(job, state["batch_id"], {"action": "open"})
    state = service.store.load()
    state["jobs"][0].update(status="needs_recheck", reason="action_result_unknown")
    service.store.save(state)
    page = object()
    runner.pages[job["application_id"]] = page
    runner.drafts[page] = DraftSession(job)
    route = bounded_route(public_request(page, ORG))
    before = service.store.load()

    runner._live_guard(route)

    assert route.outcome == "allowed"
    assert service.store.load() == before
    assert before["jobs"][0]["intent"]["action"] == "open"


@pytest.mark.worker_browser
def test_runner_tick_loads_both_public_reads_before_original_form(tmp_path, monkeypatch):
    from playwright.sync_api import sync_playwright

    monkeypatch.setenv("PLAYWRIGHT_BROWSERS_PATH", "0")
    service, _ = setup_service(tmp_path, monkeypatch)
    html = """<title>Engineer @ Synthetic</title><h1>Engineer</h1><main></main><script>
      const queries=QUERIES;
      async function read(op,variables) {
        return (await fetch('/api/non-user-graphql?op='+op,{method:'POST',
          headers:{'Content-Type':'application/json'},
          body:JSON.stringify({operationName:op,query:queries[op],variables})})).json();
      }
      Promise.all([
        read('ApiJobPosting',{organizationHostedJobsPageName:'synthetic',jobPostingId:POSTING}),
        read('ApiOrganizationFromHostedJobsPageName',{organizationHostedJobsPageName:'synthetic',
          searchContext:'JobPosting'})
      ]).then(()=>document.querySelector('main').innerHTML=`<form>
        <label>Unrecorded required answer<input name='unknown' required></label>
        <button type='submit'>Submit Application</button></form>`);
      window.finalActions=0;document.addEventListener('submit',e=>{
        e.preventDefault();window.finalActions++;
      });
    </script>""".replace("QUERIES", json.dumps(QUERIES)).replace(
        "POSTING", json.dumps(URL.split("/")[4])
    )
    sent = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, channel="chromium")
        try:
            context = browser.new_context(offline=True)
            runner = ApplicationRunner(service.store, context)

            def intercept(route):
                request = route.request

                def fetch(**options):
                    assert options == {"max_redirects": 0, "max_retries": 0, "timeout": 10000}
                    if request.method == "GET":
                        assert request.url == URL
                        fields = {"status": 200, "body": html, "content_type": "text/html"}
                    else:
                        payload = request.post_data_json
                        op = payload["operationName"]
                        sent.append(op)
                        assert op in QUERIES
                        data = (
                            {
                                "jobPosting": {
                                    "id": URL.split("/")[4],
                                    "title": "Engineer",
                                    "applicationForm": form({}),
                                }
                            }
                            if op == "ApiJobPosting"
                            else {
                                "organization": {
                                    "organizationId": "synthetic-org",
                                    "name": "Synthetic",
                                    "hostedJobsPageSlug": "synthetic",
                                }
                            }
                        )
                        fields = {"status": 200, "json": {"data": data}}
                    return SimpleNamespace(status=200, fields=fields, dispose=lambda: None)

                runner._live_guard(
                    SimpleNamespace(
                        request=request,
                        fetch=fetch,
                        fulfill=lambda *, response: route.fulfill(**response.fields),
                        abort=route.abort,
                        continue_=lambda: pytest.fail("No external transport is allowed"),
                    )
                )

            context.route("**/*", intercept)
            runner.tick()

            job = service.store.load()["jobs"][0]
            assert sorted(sent) == sorted(QUERIES)
            page = runner.pages[job["application_id"]]
            assert job["page_open"] and job["intent"] is None
            assert page.locator("form").count() == 1
            assert page.evaluate("window.finalActions") == 0
            assert not runner.blocked_pages
            assert runner.drafts[page].counts == {"initial": 1, "organization": 1}
        finally:
            browser.close()
