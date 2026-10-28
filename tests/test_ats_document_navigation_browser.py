"""Bounded document steps use the original browser Page and request guard."""

import time

import pytest
from test_ats_navigation_browser import tick
from test_generic_worker import FIELDS, URL, native_form

pytestmark = pytest.mark.worker_browser

NEXT_URL = URL + "&step=documents"
FIRST = """<form>
<label>Full name *<input name='person' required></label>
<label>Email *<input name='contact' type='email' required></label>
<a id='next' rel='next' href='?job_id=42&step=documents'>Continue</a>
</form>"""
LAST = (
    "<title>Engineer — Synthetic Careers</title><h1>Engineer</h1><form>"
    + FIELDS
    + "<button type='submit'>Submit application</button></form>"
    + "<script>window.finalActions=0;document.querySelector('form').onsubmit="
    + "e=>{e.preventDefault();window.finalActions++}</script>"
)


def wait_for_review(service, runner):
    """Observe parser windows until the semantic result, without an action-count assumption."""
    deadline = time.monotonic() + 12
    while True:
        current = tick(service, runner)
        if current["status"] in {"ready_for_review", "needs_recheck"}:
            return current
        assert time.monotonic() < deadline, current["reason"]


def test_document_continue_keeps_original_page_and_job_identity(tmp_path, monkeypatch):
    with native_form(tmp_path, monkeypatch, FIRST, {NEXT_URL: LAST}) as (
        service,
        runner,
        job,
        posts,
    ):
        tick(service, runner)
        page = runner.pages[job["application_id"]]
        page_id = runner.page_ids[page]
        current = wait_for_review(service, runner)
        assert current["status"] == "ready_for_review", current["reason"]
        assert page.url == NEXT_URL
        assert runner.pages[job["application_id"]] is page
        assert runner.page_ids[page] == page_id
        assert current["job_url"] == URL
        assert page.locator("[name=person]").input_value() == "Synthetic Person"
        assert page.locator("[name=attachment]").evaluate("(e)=>e.files[0].name") == job["filename"]
        advances = [
            event["intent"]
            for event in current["observations"]
            if event.get("action") == "action_result"
            and event.get("result") == "verified"
            and (event.get("intent") or {}).get("action") == "advance"
        ]
        assert len(advances) == 1
        assert advances[0]["navigation"]["from_step"] == URL
        assert advances[0]["navigation"]["to_step"] == NEXT_URL
        assert advances[0]["page_id"] == page_id
        assert page.evaluate("window.finalActions") == 0
        assert posts == []


@pytest.mark.parametrize(
    "change,reason",
    [
        ("different_job", "navigation_changed"),
        ("different_origin", "navigation_changed"),
        ("different_path", "navigation_changed"),
        ("final_label", "unsupported_structure"),
        ("final_apply_label", "unsupported_structure"),
        ("target_blank", "unsupported_structure"),
        ("unlabelled_button", "unsupported_structure"),
    ],
)
def test_document_next_refuses_unbound_or_final_targets(tmp_path, monkeypatch, change, reason):
    html = FIRST
    if change == "different_job":
        html = html.replace("job_id=42&", "job_id=43&")
    elif change == "different_origin":
        html = html.replace(
            "?job_id=42&step=documents", "https://other.test/?job_id=42&step=documents"
        )
    elif change == "different_path":
        html = html.replace("?job_id=42&step=documents", "/other?job_id=42&step=documents")
    elif change in {"final_label", "final_apply_label"}:
        label = "Apply" if change == "final_apply_label" else "Submit application"
        html = html.replace(">Continue</a>", ">" + label + "</a>")
    elif change == "target_blank":
        html = html.replace("rel='next'", "rel='next' target='_blank'")
    else:
        html = html.replace(
            "<a id='next' rel='next' href='?job_id=42&step=documents'>Continue</a>",
            "<button type='button'>Continue</button>",
        )
    with native_form(tmp_path, monkeypatch, html) as (service, runner, job, posts):
        current = tick(service, runner, 4)
        page = runner.pages[job["application_id"]]
        assert current["status"] == "needs_recheck"
        assert current["reason"] == reason
        assert page.url == URL
        assert len(page.context.pages) == 1
        assert current["intent"] is None
        assert posts == []


@pytest.mark.parametrize("fault", ["changed_target", "replaced_link", "pause", "old_intent"])
def test_document_next_rechecks_authority_and_control_before_click(tmp_path, monkeypatch, fault):
    with native_form(tmp_path, monkeypatch, FIRST, {NEXT_URL: LAST}) as (
        service,
        runner,
        job,
        posts,
    ):
        original_authorize = runner.authorize
        modified = []

        def change_after_authorization(current, batch_id, intent):
            allowed = original_authorize(current, batch_id, intent)
            if allowed and intent["action"] == "advance":
                modified.append(intent["attempt_id"])
                if len(modified) != 1:
                    return allowed
                page = runner.pages[job["application_id"]]
                if fault == "changed_target":
                    page.locator("#next").evaluate("e=>e.href='?job_id=43&step=documents'")
                elif fault == "replaced_link":
                    page.locator("#next").evaluate("e=>e.replaceWith(e.cloneNode(true))")
                elif fault == "pause":
                    service.request("pause", {"controller": "synthetic-controller"})
                else:
                    state = service.store.load()
                    state["jobs"][0]["intent"]["attempt_id"] = "another-attempt"
                    service.store.save(state)
            return allowed

        monkeypatch.setattr(runner, "authorize", change_after_authorization)
        current = tick(service, runner, 7)
        page = runner.pages[job["application_id"]]
        assert len(modified) == 1
        assert page.url == URL
        assert current["intent"]["action"] == "advance"
        assert current["intent"]["attempt_id"] == (
            "another-attempt" if fault == "old_intent" else modified[0]
        )
        pending = current["intent"]["attempt_id"]
        current = tick(service, runner, 3)
        if fault in {"replaced_link", "old_intent"}:
            # The old attempt never crossed dispatch_current. The retained
            # document proves not_applied, permitting a newly checked plan.
            resolution = next(
                row for row in current["action_resolutions"] if row["intent_ref"] == pending
            )
            assert resolution["conclusion"] == "not_applied"
            assert resolution["source"] == "retained_original_page"
            assert resolution["intent"]["dispatch_state"] == "prepared"
            assert len(modified) == 2 and len(set(modified)) == 2
            assert modified[-1] != pending
            completed = [
                event["intent"]
                for event in current["observations"]
                if event.get("action") == "action_result"
                and event.get("result") == "verified"
                and (event.get("intent") or {}).get("action") == "advance"
            ]
            assert len(completed) == 1
            assert completed[0]["attempt_id"] == modified[-1]
            assert completed[0]["navigation"]["from_step"] == URL
            assert completed[0]["navigation"]["to_step"] == NEXT_URL
            assert page.url == NEXT_URL
        else:
            assert len(modified) == 1
            assert current["intent"]["attempt_id"] == pending
            assert page.url == URL
            if fault == "pause":
                assert service.store.load()["control"] == "paused"
        assert posts == []


@pytest.mark.parametrize(
    "fault", ["unknown_write", "final_write", "unknown_read", "changed_identity"]
)
def test_document_result_failure_retains_attempt_without_repeat(tmp_path, monkeypatch, fault):
    html = LAST
    if fault == "changed_identity":
        html = html.replace("<h1>Engineer</h1>", "<h1>Another job</h1>")
    else:
        endpoint = (
            "/graphql?op=ApiSubmitSingleApplicationFormAction"
            if fault == "final_write"
            else "/unrecognized"
        )
        options = "" if fault == "unknown_read" else ",{method:'POST',body:'synthetic'}"
        html += f"<script>fetch('{endpoint}'{options}).catch(()=>{{}})</script>"
    with native_form(tmp_path, monkeypatch, FIRST, {NEXT_URL: html}) as (
        service,
        runner,
        job,
        posts,
    ):
        original_authorize = runner.authorize
        advances = []

        def record_authorization(current, batch_id, intent):
            allowed = original_authorize(current, batch_id, intent)
            if allowed and intent["action"] == "advance":
                advances.append(intent["attempt_id"])
            return allowed

        monkeypatch.setattr(runner, "authorize", record_authorization)
        current = tick(service, runner, 7)
        page = runner.pages[job["application_id"]]
        assert current["status"] == "needs_recheck"
        assert current["reason"] == {
            "final_write": "manual_submit_required",
            "changed_identity": "identity_changed",
        }.get(fault, "unverified_send_path")
        assert len(advances) == 1
        attempt = advances[0]
        if current["intent"]:
            assert current["intent"]["action"] == "advance"
            assert current["intent"]["attempt_id"] == attempt
        assert page.url == NEXT_URL
        current = tick(service, runner, 3)
        assert current["status"] == "needs_recheck"
        if current["intent"]:
            assert current["intent"]["attempt_id"] == attempt
        else:
            # Exact GET readback may settle the advance independently of the
            # new document's blocked request. The page remains unable to send.
            resolution = next(
                row for row in current["action_resolutions"] if row["intent_ref"] == attempt
            )
            assert resolution["conclusion"] == "current_matches"
            assert resolution["source"] == "retained_original_page"
        assert advances == [attempt]
        if fault != "changed_identity":
            assert runner.blocked_pages[page] == current["reason"]
            assert not runner.permitted(service.store.load(), page)
        assert page.url == NEXT_URL
        assert page.evaluate("window.finalActions") == 0
        assert posts == []


def test_document_login_then_one_continue_reuses_page_without_reopening(tmp_path, monkeypatch):
    login = (
        "<title>Engineer — Synthetic Careers</title><h1>Engineer</h1>"
        "<form><label>Sign in<input id='password' type='password'></label></form>"
    )
    with native_form(tmp_path, monkeypatch, FIRST, {NEXT_URL: login}) as (
        service,
        runner,
        job,
        posts,
    ):
        current = tick(service, runner, 5)
        page = runner.pages[job["application_id"]]
        page_id = runner.page_ids[page]
        assert current["status"] == "needs_recheck"
        assert current["reason"] == "user_authentication"
        assert current["intent"] is None
        page.context.add_cookies(
            [{"name": "synthetic_session", "value": "retained", "url": page.url}]
        )
        page.evaluate("html => document.body.innerHTML = html", LAST)
        service.request("resume", {"controller": "synthetic-controller"})
        current = wait_for_review(service, runner)
        assert current["status"] == "ready_for_review", current["reason"]
        assert runner.pages[job["application_id"]] is page
        assert runner.page_ids[page] == page_id
        assert page.url == NEXT_URL
        assert any(cookie["name"] == "synthetic_session" for cookie in page.context.cookies())
        assert page.locator("[name=attachment]").evaluate("(e)=>e.files[0].name") == job["filename"]
        assert posts == []


@pytest.mark.parametrize("status", [302, 307])
def test_document_next_redirect_is_not_followed_or_retried(tmp_path, monkeypatch, status):
    from types import SimpleNamespace

    with native_form(tmp_path, monkeypatch, FIRST) as (service, runner, job, posts):
        tick(service, runner)
        page = runner.pages[job["application_id"]]
        requests = []

        def redirect(route):
            class Route:
                request = route.request

                def fetch(self, **options):
                    assert options == {"max_redirects": 0, "max_retries": 0, "timeout": 10000}
                    requests.append(self.request.url)
                    return SimpleNamespace(
                        status=status,
                        url=self.request.url,
                        headers={"location": "https://other.test/final"},
                        dispose=lambda: None,
                    )

                def fulfill(self, **options):
                    pytest.fail("The browser must not consume an unverified redirect response")

                def abort(self, reason):
                    route.abort(reason)

            runner._live_guard(Route())

        page.route(NEXT_URL, redirect)
        current = tick(service, runner, 6)
        assert current["status"] == "needs_recheck"
        assert current["reason"] == "public_read_result_unknown"
        attempt = current["intent"]["attempt_id"]
        current = tick(service, runner, 3)
        assert current["intent"]["attempt_id"] == attempt
        assert requests == [NEXT_URL]
        # Chromium may replace the aborted document with its own error page.
        # The retained Page and pending attempt remain the recovery target.
        assert runner.pages[job["application_id"]] is page
        assert page.url != "https://other.test/final"
        diagnostics = [
            event
            for event in current["observations"]
            if event.get("action") == "request_diagnostic"
            and event.get("reason") == "public_read_result_unknown"
        ]
        assert diagnostics[-1]["http_status"] == status
        assert diagnostics[-1]["redirect_followed"] is False
        assert posts == []


@pytest.mark.parametrize("query", ["job_id=42&action=submit", "job_id=42&step=submitApplication"])
def test_document_next_does_not_infer_final_get_from_next_label(tmp_path, monkeypatch, query):
    target = URL.split("?", 1)[0] + "?" + query
    html = FIRST.replace("?job_id=42&step=documents", "?" + query)
    with native_form(tmp_path, monkeypatch, html, {target: LAST}) as (service, runner, job, posts):
        current = tick(service, runner, 6)
        assert current["status"] == "needs_recheck"
        assert current["reason"] == "navigation_changed"
        assert runner.pages[job["application_id"]].url == URL
        assert current["intent"] is None
        assert posts == []
