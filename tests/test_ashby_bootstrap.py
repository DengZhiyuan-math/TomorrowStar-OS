"""Public Ashby bootstrap through the existing Runner; no external requests."""

import json
from types import SimpleNamespace

import pytest
from test_ashby_drafts import URL, form, setup_service

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
