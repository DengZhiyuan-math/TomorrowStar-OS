"""Private guard diagnostics retain structural navigation facts, never credentials."""

import json
from types import SimpleNamespace

import pytest
from test_workable_bootstrap_diagnostic import FORM
from test_workable_bootstrap_diagnostic import bootstrap as bootstrap

from career_evidence_graph.application_worker import WorkerStore


def reopened_diagnostic(service, runner):
    runner.persist(service.store.load())
    state = WorkerStore(service.store.applications, service.store.root, live=True).load()
    return next(
        row
        for row in reversed(state["jobs"][0]["observations"])
        if row.get("action") == "request_diagnostic"
    )


def test_denied_navigation_keeps_initial_frame_page_and_waiting_state(bootstrap):
    service, runner, page = bootstrap
    page.url = (
        "https://login-user:login-password@apply.workable.com:8443/sign-in"
        "?token=secret-token&state=secret-state&token=again#secret-fragment"
    )
    state = service.store.load()
    state["jobs"][0].update(status="needs_recheck", reason="user_authentication")
    service.store.save(state)
    request = SimpleNamespace(
        method="POST",
        url="https://apply.workable.com/synthetic-sign-in",
        resource_type="document",
        frame=page.main_frame,
        headers={},
        post_data_buffer=b"do not retain this password",
        redirected_from=SimpleNamespace(
            url="https://redirect-user:redirect-password@identity.invalid/start?code=secret-code#secret-anchor"
        ),
        is_navigation_request=lambda: True,
    )
    outcomes = []

    def abort(reason):
        outcomes.append(reason)
        page.url = "https://later.invalid/already-changed"

    runner._live_guard(
        SimpleNamespace(
            request=request,
            abort=abort,
            continue_=lambda: pytest.fail("Unknown login must stay blocked"),
        )
    )
    record = reopened_diagnostic(service, runner)

    assert record["is_navigation_request"] is True
    assert record["is_main_frame"] is True
    assert record["page_location"] == {
        "scheme": "https",
        "hostname": "apply.workable.com",
        "port": 8443,
        "path": "/sign-in",
        "query_keys": ["state", "token"],
    }
    assert record["redirected_from_location"] == {
        "scheme": "https",
        "hostname": "identity.invalid",
        "port": None,
        "path": "/start",
        "query_keys": ["code"],
    }
    assert record["job_status"] == "needs_recheck"
    assert record["job_reason"] == "user_authentication"
    assert record["stage"] == "request_blocked" and record["dispatch"] == "not_sent"
    assert outcomes == ["blockedbyclient"]
    serialized = json.dumps(record)
    for secret in (
        "login-user",
        "login-password",
        "secret-token",
        "secret-state",
        "again",
        "secret-fragment",
        "redirect-user",
        "redirect-password",
        "secret-code",
        "secret-anchor",
        "do not retain this password",
    ):
        assert secret not in serialized


def test_rejected_redirect_retains_status_and_sanitized_location_from_response(bootstrap):
    service, runner, page = bootstrap
    initial_url = page.url
    request = SimpleNamespace(
        method="GET",
        url=FORM,
        resource_type="fetch",
        frame=page.main_frame,
        headers={"accept": "application/json"},
        post_data_buffer=None,
        redirected_from=None,
        is_navigation_request=lambda: False,
    )
    calls = []

    def fetch(**options):
        calls.append(options)
        page.url = "https://later.invalid/changed-during-fetch"
        return SimpleNamespace(
            status=302,
            url="https://response-user:response-password@identity.invalid:444/base/page?ignored=secret",
            headers={
                "location": "../authorize?code=secret-code&state=secret-state"
                "&code=again#secret-fragment"
            },
            dispose=lambda: calls.append("disposed"),
        )

    runner._live_guard(
        SimpleNamespace(
            request=request,
            fetch=fetch,
            abort=lambda reason: calls.append(reason),
            fulfill=lambda **_: pytest.fail("A rejected redirect must not reach the Page"),
        )
    )
    record = reopened_diagnostic(service, runner)

    assert record["http_status"] == 302
    assert record["response_redirect_location"] == {
        "scheme": "https",
        "hostname": "identity.invalid",
        "port": 444,
        "path": "/authorize",
        "query_keys": ["code", "state"],
    }
    assert record["redirect_followed"] is False
    assert record["is_navigation_request"] is False and record["is_main_frame"] is True
    assert record["page_location"]["hostname"] == "apply.workable.com"
    assert record["page_location"]["path"] in initial_url
    assert record["stage"] == "public_read_response_rejected"
    assert record["dispatch"] == "unknown" and record["purpose"] == "unknown"
    assert calls == [
        {"max_redirects": 0, "max_retries": 0, "timeout": 10000},
        "disposed",
        "blockedbyclient",
    ]
    serialized = json.dumps(record)
    for secret in (
        "response-user",
        "response-password",
        "secret-code",
        "secret-state",
        "again",
        "secret-fragment",
        "changed-during-fetch",
        "ignored",
    ):
        assert secret not in serialized


def test_unreadable_request_metadata_does_not_change_the_denial(bootstrap):
    service, runner, original_page = bootstrap

    class PageWithUnavailableMetadata:
        @property
        def url(self):
            raise RuntimeError("private page exception must not be retained")

        @property
        def main_frame(self):
            raise RuntimeError("private frame exception must not be retained")

    page = PageWithUnavailableMetadata()
    job = service.store.load()["jobs"][0]
    runner.pages[job["application_id"]] = page
    runner.page_ids[page] = runner.page_ids[original_page]

    class RequestWithUnavailableMetadata:
        method = "POST"
        url = "https://apply.workable.com/synthetic-sign-in"
        resource_type = "document"
        post_data_buffer = None
        frame = SimpleNamespace(page=page)

        def is_navigation_request(self):
            raise RuntimeError("private navigation exception must not be retained")

        @property
        def redirected_from(self):
            raise RuntimeError("private redirect exception must not be retained")

    outcomes = []
    runner._live_guard(
        SimpleNamespace(
            request=RequestWithUnavailableMetadata(),
            abort=lambda reason: outcomes.append(reason),
            continue_=lambda: pytest.fail("Missing diagnostics cannot permit a request"),
        )
    )
    record = reopened_diagnostic(service, runner)

    for key in (
        "is_navigation_request",
        "is_main_frame",
        "page_location",
        "redirected_from_location",
    ):
        assert record[key] is None
    assert record["stage"] == "request_blocked" and record["dispatch"] == "not_sent"
    assert record["http_status"] is None
    assert outcomes == ["blockedbyclient"] and not runner.storage_stopped
    assert "exception must not be retained" not in json.dumps(record)


@pytest.mark.parametrize("fault", ["headers", "response_url", "non_http_target"])
def test_unreadable_redirect_metadata_cannot_change_refusal_or_release(bootstrap, fault):
    service, runner, page = bootstrap
    request = SimpleNamespace(
        method="GET",
        url=FORM,
        resource_type="fetch",
        frame=page.main_frame,
        headers={"accept": "application/json"},
        post_data_buffer=None,
        redirected_from=None,
        is_navigation_request=lambda: False,
    )
    outcomes = []

    class ResponseWithUnavailableMetadata:
        status = 302

        @property
        def headers(self):
            if fault == "headers":
                raise RuntimeError("private header exception must not be retained")
            return {
                "location": "javascript:private-non-http-target"
                if fault == "non_http_target"
                else "/authorize?code=secret-code"
            }

        @property
        def url(self):
            if fault == "response_url":
                raise RuntimeError("private URL exception must not be retained")
            return FORM

        def dispose(self):
            outcomes.append("disposed")

    runner._live_guard(
        SimpleNamespace(
            request=request,
            fetch=lambda **_: ResponseWithUnavailableMetadata(),
            abort=lambda reason: outcomes.append(reason),
            fulfill=lambda **_: pytest.fail("Missing metadata cannot release a redirect"),
        )
    )
    record = reopened_diagnostic(service, runner)

    assert record["http_status"] == 302
    assert record["response_redirect_location"] is None
    assert record["redirect_followed"] is False
    assert record["stage"] == "public_read_response_rejected" and record["dispatch"] == "unknown"
    assert outcomes == ["disposed", "blockedbyclient"] and not runner.storage_stopped
    assert "private" not in json.dumps(record)
    assert "secret-code" not in json.dumps(record)


@pytest.mark.parametrize("result", ["success", "fetch_failure"])
def test_non_redirect_or_missing_response_does_not_claim_a_redirect_result(bootstrap, result):
    service, runner, page = bootstrap
    request = SimpleNamespace(
        method="GET",
        url=FORM,
        resource_type="fetch",
        frame=page.main_frame,
        headers={"accept": "application/json"},
        post_data_buffer=None,
        redirected_from=None,
        is_navigation_request=lambda: False,
    )
    calls = []

    def fetch(**options):
        calls.append(options)
        if result == "fetch_failure":
            raise OSError("private fetch exception must not be retained")
        return SimpleNamespace(status=200, dispose=lambda: calls.append("disposed"))

    runner._live_guard(
        SimpleNamespace(
            request=request,
            fetch=fetch,
            abort=lambda reason: calls.append(reason),
            fulfill=lambda **_: calls.append("fulfilled"),
        )
    )
    record = reopened_diagnostic(service, runner)

    assert record["http_status"] == (200 if result == "success" else None)
    assert record["response_redirect_location"] is None and record["redirect_followed"] is None
    assert record["stage"] == (
        "request_permitted" if result == "success" else "public_read_response_rejected"
    )
    assert record["dispatch"] == "unknown"
    assert calls == [
        {"max_redirects": 0, "max_retries": 0, "timeout": 10000},
        *(["fulfilled", "disposed"] if result == "success" else ["blockedbyclient"]),
    ]
    assert "private fetch exception" not in json.dumps(record)


def test_iframe_document_request_is_distinct_from_main_frame_navigation(bootstrap):
    service, runner, page = bootstrap
    request = SimpleNamespace(
        method="POST",
        url="https://apply.workable.com/synthetic-frame-login",
        resource_type="document",
        frame=SimpleNamespace(page=page),
        headers={},
        post_data_buffer=None,
        redirected_from=None,
        is_navigation_request=lambda: True,
    )
    outcomes = []
    runner._live_guard(
        SimpleNamespace(
            request=request,
            abort=lambda reason: outcomes.append(reason),
            continue_=lambda: pytest.fail("Frame metadata does not authorize a request"),
        )
    )
    record = reopened_diagnostic(service, runner)
    assert record["is_navigation_request"] is True and record["is_main_frame"] is False
    assert record["resource_type"] == "document"
    assert record["dispatch"] == "not_sent" and outcomes == ["blockedbyclient"]


def test_relative_location_uses_request_url_when_response_url_is_unavailable(bootstrap):
    service, runner, page = bootstrap
    request = SimpleNamespace(
        method="GET",
        url=FORM,
        resource_type="fetch",
        frame=page.main_frame,
        headers={},
        post_data_buffer=None,
        redirected_from=None,
        is_navigation_request=lambda: False,
    )
    outcomes = []
    response = SimpleNamespace(
        status=307,
        headers={"location": "/authorize?code=secret-code&state=secret-state#fragment"},
        dispose=lambda: outcomes.append("disposed"),
    )
    runner._live_guard(
        SimpleNamespace(
            request=request,
            fetch=lambda **_: response,
            abort=lambda reason: outcomes.append(reason),
            fulfill=lambda **_: pytest.fail("A diagnostic fallback cannot release a redirect"),
        )
    )
    record = reopened_diagnostic(service, runner)
    assert record["http_status"] == 307 and record["redirect_followed"] is False
    assert record["response_redirect_location"] == {
        "scheme": "https",
        "hostname": "apply.workable.com",
        "port": None,
        "path": "/authorize",
        "query_keys": ["code", "state"],
    }
    assert outcomes == ["disposed", "blockedbyclient"]
    assert "secret-code" not in json.dumps(record)
    assert "secret-state" not in json.dumps(record)
