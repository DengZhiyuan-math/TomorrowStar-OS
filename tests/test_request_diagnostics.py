"""Request guards retain exact synthetic action context without dispatching I/O."""

from copy import deepcopy
from types import SimpleNamespace

import pytest
from owned_cdp_fake import OwnedCDPFake
from test_workable_bootstrap_diagnostic import FORM, TELEMETRY, SyntheticPage, decide
from test_workable_bootstrap_diagnostic import bootstrap as bootstrap
from test_workable_uploads import local_transport as local_transport
from test_workable_uploads import setup_service
from test_worker_stability import retained_live_page as retained_live_page

from career_evidence_graph.application_worker import WorkerStore, start_run
from career_evidence_graph.application_worker_browser import ApplicationRunner
from career_evidence_graph.career_portal_data import PortalDataError


def test_rejected_request_survives_reopen_with_original_field_attempt(tmp_path, monkeypatch):
    service = setup_service(tmp_path, monkeypatch)
    run_id = start_run(service.store)
    page = SyntheticPage()
    runner = ApplicationRunner(service.store, None)
    job = service.store.load()["jobs"][0]
    runner.pages[job["application_id"]] = page
    runner.page_ids[page] = "synthetic-request-page"
    intent = {"action": "fill", "field_id": "email", "fact": "email"}
    assert runner.authorize(job, service.store.load()["batch_id"], intent)
    before = deepcopy(service.store.load())
    request = SimpleNamespace(
        method="POST",
        url="https://apply.workable.com/synthetic-unknown-save?origin=synthetic",
        resource_type="fetch",
        frame=page.main_frame,
        headers={"content-type": "application/json"},
        post_data_buffer=b'{"answer":"synthetic body is not a diagnostic field"}',
        redirected_from=None,
    )
    outcomes = []
    route = SimpleNamespace(
        request=request,
        abort=lambda reason: outcomes.append(reason),
        continue_=lambda: outcomes.append("unexpected-dispatch"),
    )

    runner._live_guard(route)
    runner.persist(service.store.load())

    reopened = WorkerStore(service.store.applications, service.store.root, live=True)
    after = reopened.load()
    current = after["jobs"][0]
    rows = [row for row in current["observations"] if row.get("action") == "request_diagnostic"]
    assert len(rows) == 1, "The denied request disappeared from the durable worker checkpoint"
    record = rows[0]
    assert record["stage"] == "request_blocked"
    assert record["method"] == "POST" and record["url"] == request.url
    assert record["resource_type"] == "fetch"
    assert record["dispatch"] == "not_sent" and record["purpose"] == "unknown"
    assert record["reason"] == "unverified_send_path"
    assert record["application_id"] == job["application_id"]
    assert record["batch_id"] == before["batch_id"]
    assert record["run_id"] == run_id and record["page_id"] == "synthetic-request-page"
    assert record["attempt_id"] == intent["attempt_id"] and record["field_id"] == "email"
    assert record["intent"] == intent
    assert outcomes == ["blockedbyclient"] and runner.blocked_pages[page] == "unverified_send_path"
    assert "synthetic body is not a diagnostic field" not in service.store.path.read_text()
    current["observations"] = before["jobs"][0]["observations"]
    assert after == before


def test_routine_repeat_of_a_recorded_request_decision_is_not_retained_again(tmp_path, monkeypatch):
    # A job board repeated the same polling and tracking requests thousands of times.
    service = setup_service(tmp_path, monkeypatch)
    start_run(service.store)
    page = SyntheticPage()
    runner = ApplicationRunner(service.store, None)
    state = service.store.load()
    job = state["jobs"][0]
    runner.pages[job["application_id"]] = page
    runner.page_ids[page] = "synthetic-request-page"

    def request(url):
        return SimpleNamespace(method="POST", url=url, resource_type="fetch")

    polled = request("https://apply.workable.com/synthetic-poll")
    for sequence, (sent, stage, stop) in enumerate(
        [
            (polled, "request_blocked", False),
            (polled, "request_blocked", False),
            (polled, "request_permitted", False),
            (polled, "request_permitted", False),
            (polled, "request_blocked", True),
            (polled, "request_blocked", True),
            (request("https://apply.workable.com/synthetic-other"), "request_blocked", False),
        ]
    ):
        runner.request_diagnostic(
            sent,
            page,
            job,
            state,
            stage,
            "unverified_send_path",
            sequence=sequence,
            caused_stop=stop,
        )
    runner.persist(service.store.load())

    rows = [
        (row["url"].rsplit("-", 1)[-1], row["stage"], row["caused_stop"], row["sequence"])
        for row in service.store.load()["jobs"][0]["observations"]
        if row.get("action") == "request_diagnostic"
    ]
    assert rows == [
        ("poll", "request_blocked", False, 0),
        ("poll", "request_permitted", False, 2),
        ("poll", "request_blocked", True, 4),
        ("poll", "request_blocked", True, 5),
        ("other", "request_blocked", False, 6),
    ]


def test_denied_telemetry_and_permitted_public_read_keep_order_without_releasing_stop(bootstrap):
    service, runner, page = bootstrap
    before = deepcopy(service.store.load())

    denied = decide(bootstrap, TELEMETRY, "POST", b'{"data":"synthetic"}')
    read = decide(bootstrap, FORM)
    runner.persist(service.store.load())

    current = service.store.load()["jobs"][0]
    rows = [row for row in current["observations"] if row.get("action") == "request_diagnostic"]
    assert [row["stage"] for row in rows] == ["request_blocked", "request_permitted"]
    assert [row["method"] for row in rows] == ["POST", "GET"]
    assert [row["url"] for row in rows] == [TELEMETRY, FORM]
    assert [row["dispatch"] for row in rows] == ["not_sent", "unknown"]
    assert rows[1]["purpose"] == "public_read"
    assert len({row["request_id"] for row in rows}) == 2
    assert all(row["intent"] == before["jobs"][0]["intent"] for row in rows)
    assert all(row["field_id"] is None for row in rows)
    assert denied.outcome == "blockedbyclient" and read.outcome == "continued_without_network"
    assert runner.blocked_pages[page] == "unverified_send_path"
    assert current["intent"] == before["jobs"][0]["intent"]
    assert ApplicationRunner.verified_intents(current) == []


def test_field_readback_stop_links_to_denied_request_without_claiming_a_result(bootstrap):
    service, runner, page = bootstrap
    before = deepcopy(service.store.load())
    decide(bootstrap, TELEMETRY, "POST", b'{"data":"synthetic"}')

    with pytest.raises(PortalDataError) as stopped:
        runner.observe(page, before["jobs"][0])
    assert stopped.value.code == "unverified_send_path"
    runner.persist(service.store.load())

    current = service.store.load()["jobs"][0]
    request = next(
        row for row in current["observations"] if row.get("action") == "request_diagnostic"
    )
    readbacks = [
        row for row in current["observations"] if row.get("action") == "readback_diagnostic"
    ]
    assert len(readbacks) == 1, "The checkpoint cannot explain which readback stage stopped"
    record = readbacks[0]
    assert record["stage"] == "before_dom_read"
    assert record["reason"] == "unverified_send_path"
    assert record["request_id"] == request["request_id"]
    assert record["intent"] == before["jobs"][0]["intent"]
    assert record["attempt_id"] == request["attempt_id"]
    assert record["page_id"] == "synthetic-bootstrap-page"
    assert "verified" not in record and "result" not in record
    assert current["intent"] == before["jobs"][0]["intent"]
    assert ApplicationRunner.verified_intents(current) == []


def test_later_denial_does_not_replace_the_request_that_first_stopped_readback(bootstrap):
    service, runner, page = bootstrap
    decide(bootstrap, TELEMETRY, "POST", b"{}")
    decide(bootstrap, TELEMETRY + "later", "POST", b"{}")
    runner.persist(service.store.load())
    with pytest.raises(PortalDataError):
        runner.observe(page, service.store.load()["jobs"][0])
    runner.persist(service.store.load())

    rows = service.store.load()["jobs"][0]["observations"]
    requests = [row for row in rows if row.get("action") == "request_diagnostic"]
    readback = next(row for row in rows if row.get("action") == "readback_diagnostic")
    assert readback["request_id"] == requests[0]["request_id"]
    assert [row["caused_stop"] for row in requests] == [True, False]


@pytest.mark.parametrize("missing", ["historical_request", "same_page_binding"])
def test_readback_cannot_invent_a_request_binding_from_an_old_or_missing_record(bootstrap, missing):
    service, runner, page = bootstrap
    before = deepcopy(service.store.load())
    if missing == "historical_request":
        runner.blocked_pages[page] = "unverified_send_path"
    else:
        decide(bootstrap, TELEMETRY, "POST", b"{}")
        runner.page_ids[page] = "different-synthetic-page"
    with pytest.raises(PortalDataError):
        runner.observe(page, before["jobs"][0])
    runner.persist(service.store.load())

    current = service.store.load()["jobs"][0]
    record = next(
        row for row in current["observations"] if row.get("action") == "readback_diagnostic"
    )
    assert record["request_id"] is None
    assert current["intent"] == before["jobs"][0]["intent"]
    assert ApplicationRunner.verified_intents(current) == []


@pytest.mark.parametrize("ownership", ["unowned", "handed_off"])
def test_guard_cannot_attach_foreign_or_handed_off_requests_to_the_job(bootstrap, ownership):
    service, runner, page = bootstrap
    before = deepcopy(service.store.load())
    if ownership == "unowned":
        runner.pages.clear()
    else:
        runner.handed_off_pages.add(page)

    result = decide(bootstrap, TELEMETRY, "POST", b"{}")
    runner.persist(service.store.load())

    assert service.store.load() == before
    assert result.outcome == (
        "blockedbyclient" if ownership == "unowned" else "continued_without_network"
    )


def test_reentrant_route_callback_preserves_request_arrival_order(bootstrap):
    service, runner, page = bootstrap
    request = SimpleNamespace(
        method="POST",
        url=TELEMETRY,
        resource_type="fetch",
        frame=page.main_frame,
        headers={},
        redirected_from=None,
    )
    route = SimpleNamespace(
        request=request,
        abort=lambda _reason: decide(bootstrap, FORM),
        continue_=lambda: pytest.fail("Unknown POST must remain blocked"),
    )

    runner._live_guard(route)
    runner.persist(service.store.load())

    rows = service.store.load()["jobs"][0]["observations"]
    requests = [row for row in rows if row.get("action") == "request_diagnostic"]
    ordered = sorted(requests, key=lambda row: row["sequence"])
    assert [row["method"] for row in ordered] == ["POST", "GET"]
    assert ordered[0]["caused_stop"] is True
    assert ordered[1]["caused_stop"] is False


@pytest.mark.parametrize(
    "url,resource,redirected",
    [
        ("https://apply.workable.com/api/v1/jobs/OTHERJOB/form", "fetch", False),
        ("https://apply.workable.com/api/v2/accounts/other/jobs/SYNTHETIC1", "xhr", False),
        ("https://other.example.invalid/public-bootstrap", "fetch", False),
        (FORM, "fetch", True),
        ("https://apply.workable.com/api/v1/jobs/OTHERJOB/form", "script", False),
        ("https://other.example.invalid/public-bootstrap", "image", False),
        (FORM, "script", False),
        (FORM, "stylesheet", False),
        (FORM, "image", False),
        (FORM, "document", False),
    ],
)
def test_public_read_recovery_cannot_discover_foreign_or_redirected_workable_reads(
    bootstrap, url, resource, redirected
):
    service, runner, page = bootstrap
    assert decide(bootstrap, TELEMETRY, "POST", b"{}").outcome == "blockedbyclient"
    assert decide(bootstrap, FORM).outcome == "continued_without_network"
    before = deepcopy(service.store.load())
    known = set(runner.public_reads[page])
    request = SimpleNamespace(
        method="GET",
        url=url,
        resource_type=resource,
        frame=page.main_frame,
        headers={"accept": "application/json", "accept-language": "en"},
        post_data_buffer=None,
        redirected_from=object() if redirected else None,
        is_navigation_request=lambda: resource == "document",
    )
    outcomes = []
    route = SimpleNamespace(
        request=request,
        abort=lambda reason: outcomes.append(reason),
        continue_=lambda: outcomes.append("unexpected-dispatch"),
    )

    runner._live_guard(route)
    runner.persist(service.store.load())

    assert outcomes == ["blockedbyclient"]
    after = service.store.load()
    assert after["jobs"][0]["intent"] == before["jobs"][0]["intent"]
    assert ApplicationRunner.verified_intents(after["jobs"][0]) == []
    assert runner.blocked_pages[page] == "unverified_send_path"
    assert runner.public_reads[page] == known
    records = after["jobs"][0]["observations"]
    diagnostic = [row for row in records if row.get("action") == "request_diagnostic"][-1]
    assert diagnostic["stage"] == "request_blocked" and diagnostic["dispatch"] == "not_sent"


@pytest.mark.parametrize("visible", ["old@example.invalid", "new@example.invalid"])
def test_denied_field_request_still_allows_local_capture_without_settling_original_input(
    retained_live_page, visible, request
):
    service, identifier = retained_live_page
    state = service.store.load()
    job = state["jobs"][0]
    job["intent"].update(
        action="fill",
        field_id="email",
        fact="email",
        page_id=job["page_observation"]["page_id"],
        answer_ref={"key": "original-answer", "revision": "a" * 64, "fact": "email"},
    )
    service.store.save(state)
    data = {
        "url": job["job_url"],
        "title": "Synthetic original field",
        "fields": [{"id": "email", "value": visible, "valid": True}],
        "attachments": [],
        "remote_save_verified": False,
    }

    def send(method, _arguments=None):
        if method == "Page.getFrameTree":
            return {"frameTree": {"frame": {"id": "original-frame", "loaderId": "original-doc"}}}
        if method == "Page.createIsolatedWorld":
            return {"executionContextId": 7}
        assert method == "Runtime.evaluate"
        return {"result": {"value": deepcopy(data)}}

    context = SimpleNamespace(
        browser=SimpleNamespace(is_connected=lambda: True),
        new_cdp_session=lambda _: SimpleNamespace(send=send, detach=lambda: None),
    )
    page = SyntheticPage()
    page.url = job["job_url"]
    page.context = context
    page.is_closed = lambda: False
    page.screenshot = lambda **_: b"synthetic-cdp-test-png"
    request.addfinalizer(OwnedCDPFake(page).close)
    runner = ApplicationRunner(service.store, None)
    runner.context = context
    runner.pages[identifier] = page
    runner.page_ids[page] = job["page_observation"]["page_id"]
    assert decide((service, runner, page), TELEMETRY, "POST", b"{}").outcome == "blockedbyclient"
    runner.persist(service.store.load())
    before = deepcopy(service.store.load())
    target = service.snapshot()["jobs"][0]["page_inspection_target"]
    service.request("observe-page", {"application_id": identifier, "binding": target})
    state = service.store.load()

    runner.commands(state)
    runner.persist(state)

    reopened = WorkerStore(service.store.applications, service.store.root, live=True).load()
    current = reopened["jobs"][0]
    receipt = current.pop("owned_page_inspection")
    assert receipt["status"] == "captured" and receipt["data"] == data
    assert current == before["jobs"][0]
    assert reopened["control"] == "paused" and reopened["commands"] == []
    assert ApplicationRunner.verified_intents(current) == []
    assert runner.blocked_pages[page] == "unverified_send_path"


def test_rejected_public_redirect_retains_unknown_dispatch_and_exact_readback_stop(bootstrap):
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
        return SimpleNamespace(status=302, dispose=lambda: None)

    runner._live_guard(
        SimpleNamespace(
            request=request,
            fetch=fetch,
            fulfill=lambda **_: pytest.fail("A redirect must not reach the Page"),
            abort=lambda reason: calls.append(reason),
        )
    )
    with pytest.raises(PortalDataError) as stopped:
        runner.observe(page, service.store.load()["jobs"][0])
    assert stopped.value.code == "public_read_result_unknown"
    runner.persist(service.store.load())
    rows = service.store.load()["jobs"][0]["observations"]
    diagnostic = next(row for row in rows if row.get("action") == "request_diagnostic")
    readback = next(row for row in rows if row.get("action") == "readback_diagnostic")
    assert calls == [
        {"max_redirects": 0, "max_retries": 0, "timeout": 10000},
        "blockedbyclient",
    ]
    assert diagnostic["dispatch"] == "unknown" and diagnostic["caused_stop"] is True
    assert readback["request_id"] == diagnostic["request_id"]
    assert ApplicationRunner.verified_intents(service.store.load()["jobs"][0]) == []


@pytest.mark.parametrize(
    "location,stops",
    [("/en/api/v1/jobs/SYNTHETIC1/form", False), ("https://synthetic.example/form", True)],
)
def test_same_origin_redirect_of_a_page_read_is_a_read_result_not_a_stop(
    bootstrap, location, stops
):
    # A Next.js page prefetched its own route and got a same-origin 307 (2026-11-03).
    service, runner, page = bootstrap
    request = SimpleNamespace(
        method="GET",
        url=FORM,
        resource_type="fetch",
        frame=page.main_frame,
        headers={"accept": "*/*"},
        post_data_buffer=None,
        redirected_from=None,
        is_navigation_request=lambda: False,
    )
    calls = []
    runner._live_guard(
        SimpleNamespace(
            request=request,
            fetch=lambda **_: SimpleNamespace(
                status=307, url=FORM, headers={"location": location}, dispose=lambda: None
            ),
            fulfill=lambda **_: pytest.fail("A redirect hop must not reach the Page"),
            abort=lambda reason: calls.append(reason),
        )
    )
    runner.persist(service.store.load())
    diagnostic = [
        row
        for row in service.store.load()["jobs"][0]["observations"]
        if row.get("action") == "request_diagnostic"
    ][-1]
    assert calls == ["blockedbyclient"]
    assert diagnostic["redirect_followed"] is False and diagnostic["http_status"] == 307
    assert (page in runner.blocked_pages) is stops
    assert diagnostic["caused_stop"] is stops
    assert diagnostic["stage"] == (
        "public_read_response_rejected" if stops else "request_redirect_not_followed"
    )


@pytest.mark.worker_browser
@pytest.mark.parametrize(
    "resource,status",
    [
        ("fetch", 200),
        ("fetch", 302),
        ("fetch", 307),
        ("script", 200),
        ("script", 302),
        ("document", 200),
        ("document", 302),
        ("script-alias", 302),
    ],
)
def test_workable_public_read_uses_one_loopback_receiver_and_never_follows_redirect(
    tmp_path, monkeypatch, local_transport, resource, status
):
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    from threading import Thread

    from playwright.sync_api import Error, sync_playwright
    from test_workable_uploads import URL

    from career_evidence_graph.workable_uploads import ResumeUpload

    forbidden = []

    class Receiver(BaseHTTPRequestHandler):
        def do_GET(self):
            forbidden.append(self.path)
            self.send_response(200)
            self.end_headers()

        def log_message(self, *_):
            pass

    second = ThreadingHTTPServer(("127.0.0.1", 0), Receiver)
    thread = Thread(target=second.serve_forever, daemon=True)
    thread.start()
    origin, responses, wire = local_transport
    responses["/bootstrap"] = (
        status,
        {
            "Location": (
                f"http://synthetic-user:synthetic-password@127.0.0.1:{second.server_port}"
                "/forbidden?code=synthetic-auth-code&state=synthetic-state#synthetic-fragment"
            ),
            "Content-Type": "application/javascript" if resource == "script" else "text/html",
        },
        b"window.syntheticLoaded = true;" if resource == "script" else b'{"synthetic":true}',
    )
    service = setup_service(tmp_path, monkeypatch)
    monkeypatch.setenv("PLAYWRIGHT_BROWSERS_PATH", "0")
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True, channel="chromium")
            try:
                context = browser.new_context(offline=True)
                page = context.new_page()
                context.route(URL, lambda route: route.fulfill(body="<title>Synthetic</title>"))
                page.goto(URL)
                context.unroute(URL)
                runner = ApplicationRunner(service.store, context)
                job = service.store.load()["jobs"][0]
                runner.pages[job["application_id"]] = page
                runner.page_ids[page] = "synthetic-request-page"
                runner.workable[page] = ResumeUpload(job)
                assert runner.authorize(job, service.store.load()["batch_id"], {"action": "open"})

                def intercept(route):
                    def fetch(**options):
                        assert options == {"max_redirects": 0, "max_retries": 0, "timeout": 10000}
                        return route.fetch(url=origin + "/bootstrap", **options)

                    runner._live_guard(
                        SimpleNamespace(
                            request=route.request,
                            fetch=fetch,
                            fulfill=route.fulfill,
                            abort=route.abort,
                            continue_=lambda: pytest.fail("Scoped GET must use bounded fetch"),
                        )
                    )

                context.route("**/*", intercept)
                if resource == "document":
                    try:
                        result = page.goto(URL).status
                    except Error:
                        result = 0
                elif resource in {"script", "script-alias"}:
                    script_url = (
                        FORM
                        if resource == "script-alias"
                        else "https://dcvxs6ggqztsa.cloudfront.net/candidate/releases/"
                        "careers.6901cd820c44d775.js"
                    )
                    result = page.evaluate(
                        """url => new Promise(resolve => {
                        const script=document.createElement('script');script.src=url;
                        script.onload=()=>resolve(200);script.onerror=()=>resolve(0);
                        document.head.append(script);
                    })""",
                        script_url,
                    )
                else:
                    result = page.evaluate("url => fetch(url).then(r=>r.status).catch(()=>0)", FORM)
                # The page can consume fulfillment before response disposal and
                # the guard's diagnostic append finish. Drain those handlers.
                context.unroute_all(behavior="wait")
                runner.persist(service.store.load())
                assert result == (200 if status == 200 else 0)
                assert [(row[0], row[1]) for row in wire] == (
                    [] if resource == "script-alias" else [("GET", "/bootstrap")]
                )
                assert forbidden == []
                current = service.store.load()["jobs"][0]
                diagnostic = [
                    row
                    for row in current["observations"]
                    if row.get("action") == "request_diagnostic"
                ][-1]
                assert diagnostic["dispatch"] == (
                    "not_sent" if resource == "script-alias" else "unknown"
                )
                assert diagnostic["stage"] == (
                    "request_blocked"
                    if resource == "script-alias"
                    else "request_permitted"
                    if status == 200
                    else "public_read_response_rejected"
                )
                assert diagnostic["is_navigation_request"] is (resource == "document")
                assert diagnostic["is_main_frame"] is True
                assert diagnostic["page_location"]["hostname"] == "apply.workable.com"
                assert diagnostic["http_status"] == (None if resource == "script-alias" else status)
                if status in {302, 307} and resource != "script-alias":
                    assert diagnostic["response_redirect_location"] == {
                        "scheme": "http",
                        "hostname": "127.0.0.1",
                        "port": second.server_port,
                        "path": "/forbidden",
                        "query_keys": ["code", "state"],
                    }
                    assert diagnostic["redirect_followed"] is False
                else:
                    assert diagnostic["response_redirect_location"] is None
                    assert diagnostic["redirect_followed"] is None
                context_text = str(
                    {
                        key: diagnostic[key]
                        for key in (
                            "page_location",
                            "response_redirect_location",
                        )
                    }
                )
                for secret in (
                    "synthetic-user",
                    "synthetic-password",
                    "synthetic-auth-code",
                    "synthetic-state",
                    "synthetic-fragment",
                ):
                    assert secret not in context_text
                assert ApplicationRunner.verified_intents(current) == []
            finally:
                browser.close()
    finally:
        second.shutdown()
        second.server_close()
        thread.join(timeout=2)


@pytest.mark.worker_browser
def test_login_wait_request_keeps_unknown_purpose_without_saving_credentials(tmp_path, monkeypatch):
    from test_generic_worker import native_form

    html = "<form><label>Sign in<input id='password' type='password'></label></form>"
    with native_form(tmp_path, monkeypatch, html) as (service, runner, job, posts):
        runner.tick()
        page = runner.pages[job["application_id"]]
        before = service.store.load()["jobs"][0]
        assert before["reason"] == "user_authentication"
        assert page not in runner.handed_off_pages
        assert (
            page.evaluate("""() => fetch('/session',{
          method:'POST',headers:{'Content-Type':'application/json'},
          body:JSON.stringify({password:'synthetic-private-login-answer'})
        }).then(r=>r.status).catch(()=>0)""")
            == 0
        )
        # Wait for abort diagnostics before reading the durable checkpoint.
        page.context.unroute_all(behavior="wait")
        runner.persist(service.store.load())
        reopened = WorkerStore(service.store.applications, service.store.root, live=True)
        current = reopened.load()["jobs"][0]
        diagnostic = next(
            row
            for row in current["observations"]
            if row.get("action") == "request_diagnostic" and row["method"] == "POST"
        )
        assert diagnostic["job_status"] == "needs_recheck"
        assert diagnostic["job_reason"] == "user_authentication"
        assert diagnostic["is_navigation_request"] is False
        assert diagnostic["is_main_frame"] is True
        assert diagnostic["purpose"] == "unknown"
        assert diagnostic["dispatch"] == "not_sent"
        assert diagnostic["http_status"] is None
        assert diagnostic["response_redirect_location"] is None
        assert current["intent"] == before["intent"] is None
        assert current["reason"] == "user_authentication"
        assert ApplicationRunner.verified_intents(current) == ApplicationRunner.verified_intents(
            before
        )
        assert "synthetic-private-login-answer" not in service.store.path.read_text()
        assert page not in runner.handed_off_pages
        assert posts == []
