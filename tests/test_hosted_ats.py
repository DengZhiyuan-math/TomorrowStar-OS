"""Offline guards and browser DOM probes. These never contact a real ATS."""

from __future__ import annotations

import base64
import hashlib
import json
from types import SimpleNamespace

import pytest

from career_evidence_graph import hosted_ats
from career_evidence_graph.application_worker import WorkerService, WorkerStore
from career_evidence_graph.application_worker_browser import ApplicationRunner
from career_evidence_graph.career_portal_data import ApplicationStore, PortalDataError

LEVER = "https://jobs.lever.co/synthetic/00000000-0000-0000-0000-000000000001"
GREENHOUSE = "https://job-boards.greenhouse.io/synthetic/jobs/123"
PDF = b"%PDF-1.4 Selected synthetic file"


def forwarding_route(request, *, allowed="allowed", blocked="blocked", initial=""):
    """Model bounded dispatch and response fulfillment without network access."""
    route = SimpleNamespace(request=request, outcome=initial, fetches=[])
    response = SimpleNamespace(status=200, dispose=lambda: None)

    def fetch(**options):
        assert options == {"max_redirects": 0, "max_retries": 0, "timeout": 10000}
        route.fetches.append(options)
        return response

    def fulfill(*, response: object):
        assert response is route.response
        route.outcome = allowed

    route.response = response
    route.fetch = fetch
    route.fulfill = fulfill
    route.continue_ = lambda: setattr(route, "outcome", allowed)
    route.abort = lambda _reason: setattr(route, "outcome", blocked)
    return route


@pytest.mark.parametrize(
    "payload",
    [
        {
            "operationName": "ApiSubmitSingleApplicationFormAction",
            "query": "mutation Final { submit }",
        },
        {
            "operationName": "ApiSetFormValue",
            "query": "mutation Save { setFormValue { id } hidden: submitApplication { id } }",
        },
        [
            {"query": "query Read { jobPosting { id } }"},
            {"query": "mutation Final { submitSingleApplicationFormAction { id } }"},
        ],
    ],
)
def test_final_request_is_blocked_even_with_a_legacy_public_grant(tmp_path, monkeypatch, payload):
    apps = tmp_path / "applications"
    apps.mkdir()
    service = WorkerService(ApplicationStore(apps), tmp_path / "worker", live=True, generic=True)
    monkeypatch.setattr(service, "spawn", lambda: None)
    job = prepare(service, "https://careers.example.test/jobs/42")
    body = json.dumps(payload).encode()
    url = "https://careers.example.test/graphql"
    (service.store.root / "public-read-grants.json").write_text(
        json.dumps(
            {
                "schemaVersion": 1,
                "grants": [
                    {
                        "job_url": job["job_url"],
                        "url": url,
                        "body_sha256": hashlib.sha256(body).hexdigest(),
                    }
                ],
            }
        )
    )
    runner = ApplicationRunner(service.store, None)
    page = object()
    runner.pages[job["application_id"]] = page
    request = SimpleNamespace(
        method="POST",
        url=url,
        resource_type="fetch",
        frame=SimpleNamespace(page=page),
        headers={"content-type": "application/json"},
        post_data_buffer=body,
        is_navigation_request=lambda: False,
    )
    route = forwarding_route(request)

    runner._live_guard(route)

    assert route.outcome == "blocked"
    assert runner.blocked_pages[page] == "manual_submit_required"
    assert not runner.sent_requests
    assert service.store.load()["jobs"][0]["intent"] is None
    runner.handed_off_pages.add(page)
    runner._live_guard(route)
    assert route.outcome == "allowed"


def live_service(tmp_path, monkeypatch, *, lever_uploads=False):
    monkeypatch.setenv("PLAYWRIGHT_BROWSERS_PATH", "0")
    root = tmp_path / "applications"
    root.mkdir()
    service = WorkerService(ApplicationStore(root), tmp_path / "worker", live=True)
    monkeypatch.setattr(service, "spawn", lambda: None)
    if lever_uploads:
        (service.store.root / "lever-upload-grants.json").write_text(
            json.dumps(
                {"schemaVersion": 1, "grants": [{"job_url": LEVER, "accountId": "public-account"}]}
            )
        )
    return service


def prepare(service, url=LEVER):
    record = service.store.applications.create_application(
        {
            "company": "Synthetic",
            "role_title": "Engineer",
            "status": "drafting",
            "url": url,
            "application_strategy": "batch",
        }
    )
    service.request(
        "prepare",
        {
            "jobs": [
                {
                    "application_id": record["id"],
                    "revision": record["revision"],
                    "country": "CHE",
                    "filename": "resume.pdf",
                    "file_base64": base64.b64encode(PDF).decode(),
                }
            ]
        },
    )
    return service.store.load()["jobs"][0]


@pytest.mark.parametrize("action", ["submit", "click", "press", "requestSubmit", "evaluate"])
def test_dispatcher_has_no_automatic_final_or_arbitrary_script_action(
    tmp_path, monkeypatch, action
):
    service = live_service(tmp_path, monkeypatch)
    job = prepare(service)
    service.request("resume", {"controller": "synthetic-controller"})
    runner = ApplicationRunner(service.store, None)
    before = service.store.load()

    with pytest.raises(PortalDataError) as error:
        runner.authorize(job, before["batch_id"], {"action": action})

    assert error.value.code == "unsupported_action"
    assert service.store.load() == before
    assert not runner.sent_requests


@pytest.mark.parametrize("url", [LEVER, GREENHOUSE])
def test_known_final_endpoint_keeps_intent_and_allows_human_original_page(
    tmp_path, monkeypatch, url
):
    service = live_service(tmp_path, monkeypatch)
    job = prepare(service, url)
    service.request("resume", {"controller": "synthetic-controller"})
    runner = ApplicationRunner(service.store, None)
    # Page objects must be hashable, like Playwright's Page.
    page = type("Page", (), {"is_closed": lambda self: False})()
    runner.pages[job["application_id"]] = page
    assert runner.authorize(job, service.store.load()["batch_id"], {"action": "fill"})
    intent = service.store.load()["jobs"][0]["intent"]
    request = SimpleNamespace(
        method="POST",
        url=hosted_ats.page_url(job),
        resource_type="document",
        frame=SimpleNamespace(page=page),
        headers={},
        post_data_buffer=b"application=synthetic",
        is_navigation_request=lambda: True,
    )
    route = forwarding_route(request)

    runner._live_guard(route)

    assert route.outcome == "blocked"
    assert runner.blocked_pages[page] == "manual_submit_required"
    assert not runner.sent_requests
    assert service.store.load()["jobs"][0]["intent"] == intent
    runner.handed_off_pages.add(page)
    runner._live_guard(route)
    assert route.outcome == "allowed"


@pytest.mark.parametrize(
    "payload",
    [
        {
            "operationName": "ApiSetFormValue",
            "extensions": {"persistedQuery": {"sha256Hash": "0" * 64}},
        },
        {"query": "mutation OtherBusinessAction { changeSomething { id } }"},
    ],
)
def test_unknown_request_waits_without_calling_it_final(tmp_path, monkeypatch, payload):
    service = live_service(tmp_path, monkeypatch)
    job = prepare(service)
    runner = ApplicationRunner(service.store, None)
    page = object()
    runner.pages[job["application_id"]] = page
    request = SimpleNamespace(
        method="POST",
        url="https://jobs.lever.co/graphql",
        resource_type="fetch",
        frame=SimpleNamespace(page=page),
        headers={"content-type": "application/json"},
        post_data_buffer=json.dumps(payload).encode(),
        is_navigation_request=lambda: False,
    )
    route = forwarding_route(request)

    runner._live_guard(route)

    assert route.outcome == "blocked"
    assert runner.blocked_pages[page] == "unverified_send_path"
    assert not runner.sent_requests


@pytest.mark.parametrize(
    "query",
    [
        "op=ApiSubmitSingleApplicationFormAction",
        "op=ApiJobPosting&op=ApiSubmitSingleApplicationFormAction",
        "op=ApiSubmitSingleApplicationFormAction&op=ApiJobPosting",
    ],
)
def test_known_final_operation_in_url_is_blocked_during_generic_open(tmp_path, monkeypatch, query):
    apps = tmp_path / "applications"
    apps.mkdir()
    service = WorkerService(ApplicationStore(apps), tmp_path / "worker", live=True, generic=True)
    monkeypatch.setattr(service, "spawn", lambda: None)
    job = prepare(service, "https://careers.example.test/jobs/42")
    service.request("resume", {"controller": "synthetic-controller"})
    runner = ApplicationRunner(service.store, None)
    page = type("Page", (), {"is_closed": lambda self: False})()
    runner.pages[job["application_id"]] = page
    assert runner.authorize(job, service.store.load()["batch_id"], {"action": "open"})
    request = SimpleNamespace(
        method="GET",
        url="https://careers.example.test/api/non-user-graphql?" + query,
        resource_type="fetch",
        frame=SimpleNamespace(page=page),
        headers={},
        post_data_buffer=None,
        is_navigation_request=lambda: False,
    )
    route = forwarding_route(request)

    runner._live_guard(route)

    assert route.outcome == "blocked"
    assert runner.blocked_pages[page] == "manual_submit_required"
    assert not runner.sent_requests


def test_live_store_cannot_import_synthetic_answers(tmp_path, monkeypatch):
    service = live_service(tmp_path, monkeypatch)
    assert service.snapshot()["live_enabled"]
    assert service.snapshot()["mode"] == "live"
    with pytest.raises(ValueError, match="separate"):
        WorkerStore(service.store.applications, service.store.root)
    with pytest.raises(ValueError, match="visible"):
        WorkerService(service.store.applications, tmp_path / "headless", live=True, headless=True)
    with pytest.raises(ValueError, match="visible"):
        WorkerService(
            service.store.applications,
            tmp_path / "mixed",
            live=True,
            fixture_origin="http://127.0.0.1:1",
        )


def test_live_pilot_is_explicit_and_small(tmp_path, monkeypatch):
    service = live_service(tmp_path, monkeypatch)
    with pytest.raises(PortalDataError) as error:
        service.request("prepare", {"jobs": [{}] * 4})
    assert error.value.code == "pilot_limit"
    job = prepare(service)
    assert job["status"] == "queued"
    assert service.store.load()["control"] == "paused"
    assert service.store.library() == []


@pytest.mark.parametrize("platform", ["lever", "greenhouse", "generic"])
def test_live_pages_block_websocket_before_first_navigation(tmp_path, monkeypatch, platform):
    apps = tmp_path / "applications"
    apps.mkdir()
    service = WorkerService(
        ApplicationStore(apps), tmp_path / "worker", live=True, generic=platform == "generic"
    )
    monkeypatch.setattr(service, "spawn", lambda: None)
    job = prepare(
        service,
        {
            "lever": LEVER,
            "greenhouse": GREENHOUSE,
            "generic": "https://careers.example.test/jobs/42",
        }[platform],
    )
    service.request("resume", {"controller": "synthetic-controller"})

    class Socket:
        connected = False

        def connect_to_server(self):
            self.connected = True

        def on_message(self, callback):
            self.message_handler = callback

    socket = Socket()

    class Page:
        websocket_handler = None
        first = property(lambda self: self)

        def is_closed(self):
            return False

        def on(self, *_):
            pass

        def route_web_socket(self, pattern, callback):
            self.websocket_handler = callback

        def goto(self, url, **_):
            self.url = url
            if self.websocket_handler:
                self.websocket_handler(socket)
            else:
                socket.connect_to_server()

        def locator(self, *_):
            return self

        def wait_for(self, **_):
            pass

        def evaluate(self, *_):
            return {
                "title": "Synthetic - Engineer"
                if platform == "lever"
                else "Job Application for Engineer at Synthetic",
                "role": "Engineer",
                "challenge": False,
                "fields": [
                    {
                        "id": "email",
                        "type": "email",
                        "question": "Email",
                        "required": True,
                        "multiple": False,
                        "value": "",
                    },
                    {
                        "id": "resume",
                        "type": "file",
                        "question": "Resume",
                        "required": True,
                        "multiple": False,
                        "resume": True,
                        "remote_upload": False,
                    },
                ],
            }

    page = Page()
    opened = []
    context = SimpleNamespace(
        browser=None,
        on=lambda *_: None,
        route=lambda *_: None,
        route_web_socket=lambda *_: None,
        new_page=lambda: opened.append(page) or page,
    )
    runner = ApplicationRunner(service.store, context)

    runner.tick()
    runner.tick()

    current = service.store.load()["jobs"][0]
    assert not socket.connected
    assert current["status"] == "needs_recheck"
    assert current["reason"] == "unverified_send_path"
    assert runner.pages[job["application_id"]] is page
    assert opened == [page]
    assert not page.is_closed()
    # Manual ownership retains the site's native communication path.
    runner.handed_off_pages.add(page)
    page.websocket_handler(socket)
    assert socket.connected


def test_unowned_popup_websocket_is_blocked_before_page_discovery(tmp_path, monkeypatch):
    service = live_service(tmp_path, monkeypatch)
    prepare(service)
    routes = []
    context = SimpleNamespace(
        browser=None,
        on=lambda *_: None,
        route=lambda *_: None,
        route_web_socket=lambda pattern, callback: routes.append(callback),
    )
    runner = ApplicationRunner(service.store, context)
    socket = SimpleNamespace(connected=False, message_handler=None)
    socket.connect_to_server = lambda: setattr(socket, "connected", True)
    socket.on_message = lambda callback: setattr(socket, "message_handler", callback)

    # A popup's initial script can run before its page is associated with a job.
    if routes:
        routes[0](socket)
    else:
        socket.connect_to_server()

    assert not socket.connected
    assert socket.message_handler is not None
    assert runner.pages == {}


@pytest.mark.parametrize("multiple", [True, False])
def test_multiselect_checkbox_fill_preserves_all_selected_options(multiple):
    checked = [True, True]

    def locator(selector):
        index = 0 if selector.endswith('-0"]') else 1
        return SimpleNamespace(
            check=lambda: checked.__setitem__(index, True),
            uncheck=lambda: checked.__setitem__(index, False),
        )

    with pytest.raises(PortalDataError) as failure:
        hosted_ats.fill(
            SimpleNamespace(locator=locator),
            {
                "id": "languages",
                "type": "checkbox",
                "multiple": multiple,
                "options": ["English", "French"],
            },
            "English",
        )

    assert failure.value.code == "unsupported_structure"
    assert checked == [True, True]


@pytest.mark.parametrize(
    "field_type,options", [("checkbox", ["Agree"]), ("radio", ["English", "French"])]
)
def test_single_checkbox_and_radio_answers_remain_fillable(field_type, options):
    checked = []
    page = SimpleNamespace(
        locator=lambda selector: SimpleNamespace(check=lambda: checked.append(selector))
    )

    hosted_ats.fill(
        page,
        {"id": "choice", "type": field_type, "multiple": False, "options": options},
        options[0],
    )

    assert checked == ['[data-ts-worker-field="choice-0"]']


@pytest.mark.parametrize(
    "actual,expected",
    [
        (LEVER + "/apply", True),
        (LEVER + "0/apply", False),
        (LEVER.replace("jobs.lever.co", "jobs.eu.lever.co"), False),
        ("https://job-boards.greenhouse.io/synthetic/jobs/123", True),
        ("https://boards.greenhouse.io/synthetic/jobs/123", True),
        ("https://job-boards.greenhouse.io/other/jobs/123", False),
    ],
)
def test_hosted_redirect_is_bound_to_job(actual, expected):
    job = {
        "platform": "greenhouse" if "greenhouse" in actual else "lever",
        "job_url": GREENHOUSE if "greenhouse" in actual else LEVER,
    }
    assert hosted_ats.matches_page(actual, job) is expected


def multipart(file=PDF, extra=False, account=b"public-account"):
    body = (
        b'--bound\r\nContent-Disposition: form-data; name="accountId"\r\n\r\n' + account + b"\r\n"
        b'--bound\r\nContent-Disposition: form-data; name="resume"; filename="resume.pdf"\r\n'
        b"Content-Type: application/pdf\r\n\r\n" + file + b"\r\n"
    )
    if extra:
        body += b'--bound\r\nContent-Disposition: form-data; name="email"\r\n\r\nprivate-value\r\n'
    return body + b"--bound--\r\n"


@pytest.mark.parametrize(
    "account,grant_url,expected",
    [
        (b"public-account", LEVER, "allowed"),
        (b"private answer", LEVER, "blocked"),
        (b"other-public-account", LEVER, "allowed"),
        (b"", LEVER, "blocked"),
        (b"public-account\nprivate-answer", LEVER, "blocked"),
        (b"public-account", None, "allowed"),
        (b"public-account", LEVER[:-1] + "2", "allowed"),
    ],
)
def test_lever_parser_uses_current_pdf_without_account_grant(
    tmp_path, monkeypatch, account, grant_url, expected
):
    service = live_service(tmp_path, monkeypatch)
    job = prepare(service)
    if grant_url:
        (service.store.root / "lever-upload-grants.json").write_text(
            json.dumps(
                {
                    "schemaVersion": 1,
                    "grants": [{"job_url": grant_url, "accountId": "public-account"}],
                }
            )
        )
    runner = ApplicationRunner(service.store, None)

    class Page:
        def is_closed(self):
            return False

    page = Page()
    runner.pages[job["application_id"]] = page
    service.request("resume", {"controller": "synthetic-controller"})
    assert runner.authorize(
        job, service.store.load()["batch_id"], {"action": "upload", "sha256": job["file_sha256"]}
    )
    runner.upload_job = job
    intent = service.store.load()["jobs"][0]["intent"]

    class Request(SimpleNamespace):
        __hash__ = object.__hash__

    request = Request(
        url="https://jobs.lever.co/parseResume",
        method="POST",
        headers={"content-type": "multipart/form-data; boundary=bound"},
        post_data_buffer=multipart(account=account),
        resource_type="fetch",
        frame=SimpleNamespace(page=page),
        is_navigation_request=lambda: False,
    )
    route = forwarding_route(request)

    runner._live_guard(route)

    assert route.outcome == expected
    if expected == "blocked":
        assert runner.blocked_pages[page] == "unverified_send_path"
        assert runner.sent_requests == set()
        runner.tick()
        current = service.store.load()["jobs"][0]
        assert current["status"] == "needs_recheck"
        assert current["reason"] == "unverified_send_path"
        assert current["intent"] == intent
        assert runner.pages[job["application_id"]] is page
    else:
        assert page not in runner.blocked_pages
        assert len(runner.sent_requests) == 1


@pytest.mark.parametrize(
    "method,path,body,expected",
    [
        ("POST", "/parseResume", multipart(), True),
        ("POST", "/parseResume", multipart(b"other file"), False),
        ("POST", "/parseResume", multipart(extra=True), False),
        ("POST", "/parseResume?redirect=apply", multipart(), False),
        ("POST", "/apply", multipart(), False),
        ("PUT", "/parseResume", multipart(), False),
    ],
)
def test_only_selected_pdf_can_enter_lever_parser(method, path, body, expected):
    request = SimpleNamespace(
        url="https://jobs.lever.co" + path,
        method=method,
        headers={"content-type": "multipart/form-data; boundary=bound"},
        post_data_buffer=body,
    )
    job = {"platform": "lever", "job_url": LEVER, "file_sha256": hashlib.sha256(PDF).hexdigest()}
    assert hosted_ats.is_resume_parse(request, job) is expected
    assert not hosted_ats.is_resume_parse(request, {**job, "platform": "greenhouse"})


@pytest.mark.parametrize(
    "metadata",
    [
        b'; filename="answer.txt"',
        b'; private="answer"',
        b"\r\nContent-Type: text/plain",
        b"\r\nContent-Type: multipart/mixed; boundary=nested",
        b"\r\nContent-Transfer-Encoding: base64",
        b"\r\nX-Answer: private answer",
        b'\r\nContent-Disposition: form-data; name="private answer"',
    ],
)
def test_lever_account_is_an_unambiguous_scalar(metadata):
    body = multipart().replace(b'name="accountId"\r\n', b'name="accountId"' + metadata + b"\r\n", 1)
    request = SimpleNamespace(
        url="https://jobs.lever.co/parseResume",
        method="POST",
        headers={"content-type": "multipart/form-data; boundary=bound"},
        post_data_buffer=body,
    )
    job = {"platform": "lever", "job_url": LEVER, "file_sha256": hashlib.sha256(PDF).hexdigest()}

    assert not hosted_ats.is_resume_parse(request, job)


def test_lever_parser_rejects_duplicate_account_parts():
    body = multipart().replace(
        b"--bound--\r\n",
        b'--bound\r\nContent-Disposition: form-data; name="accountId"\r\n\r\n'
        b"private answer\r\n--bound--\r\n",
    )
    request = SimpleNamespace(
        url="https://jobs.lever.co/parseResume",
        method="POST",
        headers={"content-type": "multipart/form-data; boundary=bound"},
        post_data_buffer=body,
    )
    job = {"platform": "lever", "job_url": LEVER, "file_sha256": hashlib.sha256(PDF).hexdigest()}

    assert not hosted_ats.is_resume_parse(request, job)


@pytest.mark.parametrize(
    "grants",
    [
        [{"job_url": LEVER, "accountId": ""}],
        [{"job_url": LEVER, "accountId": "public\nanswer"}],
        [{"job_url": LEVER, "accountId": ["public-account"]}],
        [{"job_url": LEVER, "accountId": "public-account", "answer": "private"}],
        [{"job_url": GREENHOUSE, "accountId": "public-account"}],
        [{"job_url": LEVER + "/apply", "accountId": "public-account"}],
        [{"job_url": LEVER, "accountId": "public-account"}] * 2,
        [None],
    ],
)
def test_retired_lever_account_grants_do_not_block_a_runner(tmp_path, monkeypatch, grants):
    service = live_service(tmp_path, monkeypatch)
    (service.store.root / "lever-upload-grants.json").write_text(
        json.dumps({"schemaVersion": 1, "grants": grants})
    )

    runner = ApplicationRunner(service.store, None)
    assert runner.store is service.store


@pytest.mark.parametrize(
    ("request_url", "resource", "expected"),
    [
        ("https://careers.example.test/jobs/42?role=ai", "document", True),
        ("https://careers.example.test/jobs/43?role=ai", "document", False),
        ("https://careers.example.test/jobs/42?role=other", "document", False),
        ("https://other.example.test/jobs/42?role=ai", "document", False),
        ("https://careers.example.test/jobs/42?role=ai", "fetch", False),
    ],
)
def test_fragment_job_navigation_uses_network_url_without_weakening_page_identity(
    tmp_path, monkeypatch, request_url, resource, expected
):
    apps = tmp_path / "applications"
    apps.mkdir()
    service = WorkerService(ApplicationStore(apps), tmp_path / "worker", live=True, generic=True)
    monkeypatch.setattr(service, "spawn", lambda: None)
    current = prepare(service, "https://careers.example.test/jobs/42?role=ai#application")
    runner = ApplicationRunner(service.store, None)
    page = object()
    runner.pages[current["application_id"]] = page
    request = SimpleNamespace(
        method="GET",
        url=request_url,
        resource_type=resource,
        headers={},
        frame=SimpleNamespace(page=page),
        is_navigation_request=lambda: resource == "document",
    )
    route = forwarding_route(request, allowed=True, blocked=False, initial=None)

    runner._live_guard(route)

    assert route.outcome is expected
    assert hosted_ats.matches_page(current["job_url"], current)
    assert not hosted_ats.matches_page("https://careers.example.test/jobs/42?role=ai", current)
    assert not hosted_ats.matches_page(
        "https://careers.example.test/jobs/42?role=ai#other", current
    )


def test_context_guard_keeps_popups_and_final_requests_blocked(tmp_path, monkeypatch):
    service = live_service(tmp_path, monkeypatch, lever_uploads=True)
    job = prepare(service)
    runner = ApplicationRunner(service.store, None)
    page = object()
    runner.pages[job["application_id"]] = page

    class Request(SimpleNamespace):
        __hash__ = object.__hash__

    def route(method, url, current=page, body=None, resource="document"):
        request = Request(
            method=method,
            url=url,
            frame=SimpleNamespace(page=current),
            resource_type=resource,
            is_navigation_request=lambda: resource == "document",
            headers={"content-type": "multipart/form-data; boundary=bound"},
            post_data_buffer=body,
        )
        result = forwarding_route(request)
        runner._live_guard(result)
        return result.outcome

    assert route("GET", LEVER + "/apply") == "allowed"
    assert route("GET", LEVER + "/apply?email=private") == "blocked"
    assert route("POST", LEVER + "/apply", body=multipart()) == "blocked"
    assert route("POST", LEVER + "/apply", current=object()) == "blocked"
    assert route("POST", "https://jobs.lever.co/parseResume", body=multipart()) == "blocked"
    # A refused send stops that page. Use a fresh runner for the positive upload case.
    assert page in runner.blocked_pages
    runner = ApplicationRunner(service.store, None)
    runner.pages[job["application_id"]] = page
    service.request("resume", {"controller": "synthetic-live-controller"})
    assert runner.authorize(
        job, service.store.load()["batch_id"], {"action": "upload", "sha256": job["file_sha256"]}
    )
    runner.upload_job = job
    assert route("POST", "https://jobs.lever.co/parseResume", body=multipart()) == "allowed"
    assert (
        route("POST", "https://jobs.lever.co/parseResume", current=object(), body=multipart())
        == "blocked"
    )
    assert (
        route("GET", "https://tracker.example/pixel?email=private", resource="image") == "blocked"
    )
    runner.upload_job = None
    runner.handed_off_pages.add(page)
    assert route("POST", LEVER + "/apply", body=multipart()) == "allowed"
    runner.handed_off_pages.remove(page)
    assert route("POST", LEVER + "/apply", body=multipart()) == "blocked"


@pytest.mark.parametrize("resource", ["fetch", "image", "script"])
@pytest.mark.parametrize("platform", ["lever", "greenhouse", "generic"])
def test_unbound_get_cannot_send_answers_from_a_paused_batch(
    tmp_path, monkeypatch, platform, resource
):
    apps = tmp_path / "applications"
    apps.mkdir()
    service = WorkerService(
        ApplicationStore(apps), tmp_path / "worker", live=True, generic=platform == "generic"
    )
    monkeypatch.setattr(service, "spawn", lambda: None)
    url = {
        "lever": LEVER,
        "greenhouse": GREENHOUSE,
        "generic": "https://careers.example.test/jobs/42",
    }[platform]
    job = prepare(service, url)
    runner = ApplicationRunner(service.store, None)
    page = object()
    runner.pages[job["application_id"]] = page
    request = SimpleNamespace(
        method="GET",
        url=hosted_ats.page_url(job) + "?answer=private-value",
        frame=SimpleNamespace(page=page),
        resource_type=resource,
        headers={},
        is_navigation_request=lambda: False,
    )
    route = forwarding_route(request)
    checkpoint = service.store.load()

    runner._live_guard(route)

    assert route.outcome == "blocked"
    assert not runner.public_reads.get(page)
    assert service.store.load() == checkpoint


def test_only_exact_public_gets_from_the_owned_open_intent_can_be_reused(tmp_path, monkeypatch):
    service = live_service(tmp_path, monkeypatch)
    job = prepare(service)
    runner = ApplicationRunner(service.store, None)
    page = object()
    runner.pages[job["application_id"]] = page
    service.request("resume", {"controller": "synthetic-controller"})
    assert runner.authorize(job, service.store.load()["batch_id"], {"action": "open"})

    def outcome(url="https://boards.cdn.greenhouse.io/app.js", headers=None, owner=page):
        request = SimpleNamespace(
            method="GET",
            url=url,
            headers=headers or {"accept": "*/*"},
            resource_type="script",
            frame=SimpleNamespace(page=owner),
            is_navigation_request=lambda: False,
        )
        route = forwarding_route(request)
        runner._live_guard(route)
        return route.outcome

    assert outcome() == "allowed"
    runner.editing_pages.add(page)
    service.request("pause", {"controller": "synthetic-controller"})
    assert outcome() == "allowed"
    assert outcome(owner=object()) == "blocked"
    assert outcome(headers={"accept": "*/*", "x-answer": "private"}) == "blocked"
    assert outcome(url="https://boards.cdn.greenhouse.io/app.js?answer=private") == "blocked"


def test_partial_handoff_requires_user_action_and_stops_processing(tmp_path, monkeypatch):
    from career_evidence_graph.application_worker import start_run

    service = live_service(tmp_path, monkeypatch)
    job = prepare(service)
    run_id = start_run(service.store)
    state = service.store.load()
    state["jobs"][0].update(
        status="needs_input",
        page_open=True,
        page_observation={
            "run_id": run_id,
            "page_id": "synthetic-partial-handoff-page",
            "event": "observed",
            "at": state["runtime"]["observed_at"],
        },
    )
    service.store.save(state)
    with pytest.raises(PortalDataError):
        service.request("review", {"application_id": job["application_id"]})
    service.request("review", {"application_id": job["application_id"], "acknowledge": True})
    runner = ApplicationRunner(service.store, None)

    class Page:
        def is_closed(self):
            return False

        def unroute(self, *_):
            pass

        def route(self, *_):
            pass

        def bring_to_front(self):
            pass

    page = Page()
    runner.pages[job["application_id"]] = page
    runner.page_ids[page] = "synthetic-partial-handoff-page"
    runner.guards[job["application_id"]] = None
    processed = []
    monkeypatch.setattr(runner, "process", lambda *_: processed.append(True))
    service.request("resume", {"controller": "synthetic-live-controller"})
    runner.tick()
    assert service.store.load()["jobs"][0]["handed_off"]
    assert processed == []
    service.request(
        "recheck",
        {
            "application_id": job["application_id"],
            "acknowledge": True,
            "reclaim": True,
            "handoff_source": "Synthetic current handoff and history verified",
        },
    )
    runner.tick()
    assert not service.store.load()["jobs"][0]["handed_off"]
    assert processed == [True]


@pytest.mark.parametrize("binding", ["current", "old_run", "old_page", "legacy"])
def test_replaced_file_control_requires_current_page_verification(tmp_path, monkeypatch, binding):
    from career_evidence_graph.application_worker import start_run

    service = live_service(tmp_path, monkeypatch)
    job = prepare(service)
    run_id = start_run(service.store)
    service.request("resume", {"controller": "synthetic-live-controller"})
    runner = ApplicationRunner(service.store, None)
    import time

    from career_evidence_graph.application_form_state import sample

    # A retained page is a hashable browser handle.
    page = type("RetainedPage", (), {"url": job["job_url"]})()
    runner.pages[job["application_id"]] = page
    runner.page_ids[page] = "current-page"
    state = service.store.load()
    job = state["jobs"][0]
    job["observations"].append(
        {
            "action": "select_file",
            "local_sha256": job["file_sha256"],
            **({"run_id": run_id, "page_id": "current-page"} if binding != "legacy" else {}),
        }
    )
    if binding == "old_run":
        job["observations"][-1]["run_id"] = "historical-run"
    elif binding == "old_page":
        job["observations"][-1]["page_id"] = "historical-page"
    service.store.save(state)
    monkeypatch.setattr(
        runner,
        "observe",
        lambda *_: {
            "fields": [
                {
                    "id": "resume",
                    "value": "resume.pdf",
                    "valid": True,
                    "type": "file",
                    "multiple": False,
                    "required": True,
                    "resume": True,
                    "filename": "resume.pdf",
                }
            ]
        },
    )
    # This attachment-identity regression starts after ordinary parser stability.
    observation = runner.observe(page, job)
    form_binding = {
        "run_id": run_id,
        "page_id": "current-page",
        "step": page.url,
        "document_token": None,
    }
    form_state = None
    for offset in (2, 1.5, 1):
        form_state = sample(form_state, observation, binding=form_binding, now=time.time() - offset)
    state = service.store.load()
    state["jobs"][0]["form_state"] = form_state
    job = state["jobs"][0]
    service.store.save(state)
    if binding == "current":
        runner.process(job, state["batch_id"])
        assert service.store.load()["jobs"][0]["status"] == "ready_for_review"
    else:
        with pytest.raises(PortalDataError) as error:
            runner.process(job, state["batch_id"])
        assert error.value.code == "upload_result_unknown"


@pytest.mark.worker_browser
@pytest.mark.parametrize("required_marker", [" *", ""])
def test_generic_required_combobox_proxy_is_one_labeled_field(monkeypatch, required_marker):
    from playwright.sync_api import sync_playwright

    monkeypatch.setenv("PLAYWRIGHT_BROWSERS_PATH", "0")
    job = {
        "platform": "generic",
        "job_url": "https://careers.example.test/jobs/42",
        "company": "Synthetic",
        "role_title": "Engineer",
    }
    html = f"""<title>Synthetic careers</title><h1>Engineer</h1><form>
    <label for="email">Email *</label><input id="email" type="email" required>
    <div data-ui="education"><label id="education-label">Education{required_marker}</label>
    <div><div><input id="input_education_input" role="combobox" readonly
      aria-labelledby="education-label" aria-expanded="false"></div></div>
    <input name="education" required aria-hidden="true" style="display:none"></div>
    <label for="resume">Resume *</label><input id="resume" type="file" required>
    </form>"""
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True, channel="chromium")
        try:
            context = browser.new_context(offline=True)
            context.route(
                "**/*", lambda route: route.fulfill(status=200, body=html, content_type="text/html")
            )
            page = context.new_page()
            page.goto(job["job_url"])
            observed = hosted_ats.observe(page, job)
            assert [(field["question"], field["required"]) for field in observed["fields"]] == [
                ("Email", True),
                ("Education", True),
                ("Resume", True),
            ]
            assert not observed["fields"][1]["valid"]
        finally:
            browser.close()


@pytest.mark.worker_browser
@pytest.mark.parametrize("native_required", [True, False])
def test_generic_labeled_radio_group_uses_hidden_native_inputs(
    tmp_path, monkeypatch, native_required
):
    from test_ats_navigation_browser import tick
    from test_cua_worker import SyntheticControls
    from test_generic_worker import FIELDS, native_form

    html = (
        """<form>"""
        + FIELDS
        + """
    <div data-ui="education"><label id="education-label">Education *</label>
      <div><div><input id="input_education_input" role="combobox" readonly
        aria-labelledby="education-label" aria-expanded="false"
        aria-controls="education-options"></div></div>
      <input name="education" required aria-hidden="true" style="display:none">
      <div id="education-options" role="listbox" hidden><div role="option">Master</div></div>
    </div>
    <div role="radiogroup" aria-labelledby="language-label" aria-required="true">
      <label id="language-label">Language fluent? *</label>
      <label><input type="radio" name="language" value="yes" required
        aria-hidden="true">Yes</label>
      <label><input type="radio" name="language" value="no" required
        aria-hidden="true">No</label>
    </div><button type="submit">Submit</button></form><script>
    const education=document.querySelector('[role=combobox]');
    education.onclick=()=>{education.ariaExpanded='true';
      document.querySelector('[role=listbox]').hidden=false};
    document.querySelector('[role=option]').onclick=()=>{
      education.value='Master';education.ariaExpanded='false';
      document.querySelector('[name=education]').value='master';
      document.querySelector('[role=listbox]').hidden=true};
    </script>"""
    )
    if not native_required:
        html = html.replace('name="language" value="yes" required', 'name="language" value="yes"')
        html = html.replace('name="language" value="no" required', 'name="language" value="no"')
        html = html.replace("Language fluent? *", "Language fluent?")
    with native_form(tmp_path, monkeypatch, html) as (service, runner, job, posts):
        controls = SyntheticControls()
        runner.cua = controls
        for question, value in (("Language fluent?", "Yes"), ("Education", "Master")):
            service.store.answers.put_answer(
                {"question": question, "value": value, "scope": {}, "state": "confirmed"}
            )
        for _ in range(8):
            tick(service, runner)
            if service.store.load()["jobs"][0]["status"] == "ready_for_review":
                break
        current = service.store.load()["jobs"][0]
        assert current["status"] == "ready_for_review", current["reason"]
        page = runner.pages[job["application_id"]]
        language = next(
            field
            for field in hosted_ats.observe(page, job)["fields"]
            if field["question"] == "Language fluent?"
        )
        assert language["required"] and language["valid"]
        assert language["options"] == ["Yes", "No"]
        assert language["value"] == "Yes"
        education = next(
            field
            for field in hosted_ats.observe(page, job)["fields"]
            if field["question"] == "Education"
        )
        assert education["value"] == "Master"
        assert education["valid"]
        assert posts == []


@pytest.mark.worker_browser
@pytest.mark.parametrize("confirmed_consent", [False, True])
def test_generic_semantic_privacy_checkbox_needs_an_explicit_answer(
    tmp_path, monkeypatch, confirmed_consent
):
    from test_ats_navigation_browser import tick
    from test_generic_worker import FIELDS, native_form

    html = (
        "<form>"
        + FIELDS
        + """
    <label><label data-ui="privacy" data-checked="false">
      <div role="checkbox" aria-labelledby="privacy-label" aria-checked="false">
        <input type="checkbox" name="privacy" aria-hidden="true" tabindex="-1">
      </div><span id="privacy-label">Privacy policy acceptance</span>
    </label></label><button type="submit">Submit</button></form>"""
    )
    with native_form(tmp_path, monkeypatch, html) as (service, runner, job, posts):
        if confirmed_consent:
            service.store.answers.put_answer(
                {
                    "question": "Privacy policy acceptance",
                    "value": "Privacy policy acceptance",
                    "scope": {},
                    "state": "confirmed",
                }
            )
        runner.tick()
        page = runner.pages[job["application_id"]]
        consent = next(
            field
            for field in hosted_ats.observe(page, job)["fields"]
            if field["question"] == "Privacy policy acceptance"
        )
        assert consent["required"] is False
        assert not page.locator('[name="privacy"]').is_checked()
        for _ in range(8):
            tick(service, runner)
            if service.store.load()["jobs"][0]["status"] == "ready_for_review":
                break
        current = service.store.load()["jobs"][0]
        assert current["status"] == "ready_for_review", current["reason"]
        assert page.locator('[name="privacy"]').is_checked() is confirmed_consent
        assert posts == []


@pytest.mark.worker_browser
def test_generic_css_required_checkbox_waits_for_explicit_consent(tmp_path, monkeypatch):
    from test_ats_navigation_browser import tick
    from test_generic_worker import FIELDS, native_form

    html = (
        '<style>[role="checkbox"]::after { content: "*"; }</style><form>'
        + FIELDS
        + """<label><div role="checkbox" aria-labelledby="policy-label">
        <input type="checkbox" name="policy" aria-hidden="true"></div>
        <span id="policy-label">Policy acknowledgement</span></label>
        <button type="submit">Submit</button></form>"""
    )
    with native_form(tmp_path, monkeypatch, html) as (service, runner, job, posts):
        runner.tick()
        page = runner.pages[job["application_id"]]
        checkbox = page.locator('[name="policy"]')
        assert checkbox.get_attribute("required") is None
        assert page.get_by_role("checkbox").get_attribute("aria-required") is None
        assert (
            page.get_by_role("checkbox").evaluate("e=>getComputedStyle(e,'::after').content")
            == '"*"'
        )
        assert "*" not in page.locator("#policy-label").text_content()
        field = next(
            item
            for item in hosted_ats.observe(page, job)["fields"]
            if item["question"] == "Policy acknowledgement"
        )
        assert field["required"] is True
        assert not field["valid"]
        for _ in range(8):
            tick(service, runner)
            if service.store.load()["jobs"][0]["status"] == "needs_input":
                break
        current = service.store.load()["jobs"][0]
        assert current["status"] == "needs_input", current["reason"]
        assert [question["question"] for question in current["questions"]] == [
            "Policy acknowledgement"
        ]
        assert not checkbox.is_checked()
        # APP-08 uploads the selected resume before parser stability and filling.
        # This does not grant consent to the separate required policy checkbox.
        attachment = page.locator('input[type="file"]')
        assert attachment.evaluate("e=>e.files.length") == 1
        assert attachment.evaluate("e=>e.files[0].name") == job["filename"]
        service.request(
            "answer",
            {
                "application_id": job["application_id"],
                "question_id": current["questions"][0]["id"],
                "value": "Policy acknowledgement",
                "only_this": True,
            },
        )
        for _ in range(8):
            tick(service, runner)
            if service.store.load()["jobs"][0]["status"] == "ready_for_review":
                break
        current = service.store.load()["jobs"][0]
        assert current["status"] == "ready_for_review", current["reason"]
        assert checkbox.is_checked()
        assert posts == []


@pytest.mark.worker_browser
def test_generic_aria_file_labels_bind_only_the_resume_and_read_labeled_text(tmp_path, monkeypatch):
    from test_ats_navigation_browser import tick
    from test_generic_worker import native_form

    html = """<form>
    <label for="person">Full name *</label><input id="person" required>
    <label for="contact">Email *</label><input id="contact" type="email" required>
    <label id="document-label">Resume</label><span id="document-description">Choose file</span>
    <input id="document" data-ui="resume" type="file" required
      aria-labelledby="document-label document-description">
    <label id="photo-label">Photo</label><span id="photo-description">Choose file</span>
    <input id="picture" data-ui="avatar" type="file"
      aria-labelledby="photo-label photo-description">
    <input name="city" aria-hidden="true"><input name="postcode" aria-hidden="true">
    <label id="phone-label">Phone *</label><input type="tel" required aria-labelledby="phone-label">
    <label for="start">Available date *</label><input id="start" name="start" required>
    <label for="salary">Annual salary (EUR) *</label><input id="salary" name="salary" required>
    <button type="submit">Submit</button></form>"""
    with native_form(tmp_path, monkeypatch, html) as (service, runner, job, posts):
        for question, value in (
            ("Phone", "+00 123456789"),
            ("Available date", "2030-04-01"),
            ("Annual salary (EUR)", "123456"),
        ):
            service.store.answers.put_answer(
                {"question": question, "value": value, "scope": {}, "state": "confirmed"}
            )
        for _ in range(8):
            tick(service, runner)
            if service.store.load()["jobs"][0]["status"] == "ready_for_review":
                break
        current = service.store.load()["jobs"][0]
        assert current["status"] == "ready_for_review", current["reason"]
        page = runner.pages[job["application_id"]]
        fields = hosted_ats.observe(page, job)["fields"]
        files = [field for field in fields if field["type"] == "file"]
        assert [(field["question"], field["resume"]) for field in files] == [
            ("Resume Choose file", True),
            ("Photo Choose file", False),
        ]
        assert files[0]["filename"] == "resume.pdf"
        assert files[0]["file_sha256"] == job["file_sha256"]
        assert page.locator("#picture").evaluate("e=>e.files.length") == 0
        assert page.locator('[name="city"]').input_value() == ""
        assert page.locator('[name="postcode"]').input_value() == ""
        assert {
            field["question"]: field["value"] for field in fields if field["type"] != "file"
        } == {
            "Full name": "Synthetic Person",
            "Email": "synthetic@example.invalid",
            "Phone": "+00 123456789",
            "Available date": "2030-04-01",
            "Annual salary (EUR)": "123456",
        }
        assert posts == []


@pytest.mark.worker_browser
@pytest.mark.parametrize(
    "unknown_controls",
    [
        """<div data-ui="education"><label id="education-label">Education *</label>
        <input id="input_education_input" role="combobox" readonly
          aria-labelledby="education-label" aria-expanded="false">
        <input name="education" required aria-hidden="true" style="display:none">
        <input name="education" required aria-hidden="true" style="display:none"></div>""",
        """<div data-ui="education"><label id="education-label">Education *</label>
        <input id="input_education_input" role="combobox" readonly
          aria-labelledby="education-label" aria-expanded="false">
        <input name="education" aria-hidden="true" style="display:none">
        <input name="education" aria-hidden="true" style="display:none"></div>""",
        """<div data-ui="education"><label id="education-label">Education *</label>
        <input id="input_education_input" role="combobox" readonly
          aria-labelledby="education-label" aria-expanded="false">
        <input id="input_education_input" role="combobox" readonly
          aria-labelledby="education-label" aria-expanded="false">
        <input name="education" required aria-hidden="true" style="display:none"></div>""",
        '<input name="unmapped" required aria-hidden="true" style="display:none">',
        """<div role="checkbox" aria-required="true"><span>Consent choice</span>
        <input type="checkbox" name="consent" aria-hidden="true"></div>""",
        """<style>[role="checkbox"]::after { content: "*"; }</style>
        <div role="checkbox"><span>Unmapped choice</span>
        <input type="checkbox" name="choice" aria-hidden="true"></div>""",
        """<div role="radiogroup" aria-required="true"
          aria-labelledby="choice-label choice-note">
        <span id="choice-label">Required choice</span><span id="choice-note">Choose one</span>
        <label><input type="radio" name="choice" value="yes" aria-hidden="true">Yes</label>
        <label><input type="radio" name="choice" value="no" aria-hidden="true">No</label></div>""",
        """<style>[role="radiogroup"]::after { content: "*"; }</style>
        <div role="radiogroup" aria-labelledby="choice-label choice-note">
        <span id="choice-label">Required choice</span><span id="choice-note">Choose one</span>
        <label><input type="radio" name="choice" value="yes" aria-hidden="true">Yes</label>
        <label><input type="radio" name="choice" value="no" aria-hidden="true">No</label></div>""",
        """<div role="radiogroup" aria-labelledby="language-label">
        <label id="language-label">Language fluent?</label>
        <label><input type="radio" name="shared" value="yes" required aria-hidden="true">Yes</label>
        <label><input type="radio" name="shared" value="no" required aria-hidden="true">No</label>
        </div><div role="radiogroup" aria-labelledby="different-label">
        <label id="different-label">Different question</label>
        <label><input type="radio" name="shared" value="yes" required aria-hidden="true">Yes</label>
        <label><input type="radio" name="shared" value="no" required aria-hidden="true">No</label>
        </div>""",
        """<fieldset><legend>Language fluent?</legend>
        <label><input type="radio" name="shared" value="yes" required>Yes</label>
        <label><input type="radio" name="shared" value="no" required>No</label></fieldset>
        <div role="radiogroup" aria-labelledby="different-label">
        <span id="different-label">Different question</span>
        <label><input type="radio" name="shared" value="yes" aria-hidden="true">Yes</label>
        <label><input type="radio" name="shared" value="no" aria-hidden="true">No</label></div>""",
    ],
    ids=[
        "ambiguous-proxy",
        "ambiguous-optional-proxy",
        "reused-proxy",
        "unmapped-required",
        "unlabeled-required-semantic-checkbox",
        "unlabeled-css-required-semantic-checkbox",
        "multi-label-required-semantic-radio",
        "multi-label-css-required-semantic-radio",
        "ambiguous-radio-group",
        "fieldset-then-semantic-radio-group",
    ],
)
def test_generic_ambiguous_or_unknown_required_controls_stop(
    tmp_path, monkeypatch, unknown_controls
):
    from test_generic_worker import FIELDS, native_form

    with native_form(tmp_path, monkeypatch, "<form>" + FIELDS + unknown_controls + "</form>") as (
        service,
        runner,
        job,
        posts,
    ):
        service.store.answers.put_answer(
            {"question": "Language fluent?", "value": "Yes", "scope": {}, "state": "confirmed"}
        )
        runner.tick()
        runner.tick()
        current = service.store.load()["jobs"][0]
        assert current["status"] == "needs_recheck"
        assert current["reason"] == "unsupported_structure"
        page = runner.pages[job["application_id"]]
        assert page.locator('input[type="email"]').input_value() == ""
        assert page.locator('input[type="file"]').evaluate("e=>e.files.length") == 0
        assert posts == []


@pytest.mark.worker_browser
@pytest.mark.parametrize("platform", ["lever", "greenhouse"])
def test_real_selector_dom_reads_and_native_controls_without_network(
    tmp_path, monkeypatch, platform
):
    from playwright.sync_api import sync_playwright

    service = live_service(tmp_path, monkeypatch)
    job = prepare(service, GREENHOUSE if platform == "greenhouse" else LEVER)
    title = (
        "Synthetic - Engineer"
        if platform == "lever"
        else "Job Application for Engineer at Synthetic"
    )
    role = (
        "<h2 class='posting-headline'>Engineer</h2>" if platform == "lever" else "<h1>Engineer</h1>"
    )
    if platform == "lever":
        role = "<div class='posting-headline'><h2>Engineer</h2></div>"
    html = f"""<title>{title}</title>{role}<form id="application-form">
    <div class="application-question">
    <label class="application-label" for="name">Full name *</label>
    <input id="name" name="name" required></div>
    <div class="select"><label for="degree">Degree *</label>
    <input id="degree" role="combobox" aria-required="true">
    <span class="select__single-value"></span></div>
    <input aria-hidden="true" required tabindex="-1">
    <div class="application-question">
    <label class="application-label" for="resume">Resume/CV *</label>
    <input id="resume" name="resume" type="file"></div>
    <button type="submit">Submit application</button></form><script>
    const degree=document.querySelector('#degree');degree.addEventListener('input',()=>{{
      document.querySelector('[role=option]')?.remove();const option=document.createElement('div');
      option.setAttribute('role','option');option.textContent='Master';option.onclick=()=>{{
        document.querySelector('.select__single-value').textContent='Master';option.remove();}};document.body.append(option);
    }});</script>"""
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True, channel="chromium")
        try:
            context = browser.new_context(offline=True)
            # Exact source-owned document only. No request reaches the internet.
            context.route(
                "**/*", lambda route: route.fulfill(status=200, body=html, content_type="text/html")
            )
            page = context.new_page()
            page.goto(hosted_ats.page_url(job))
            observed = hosted_ats.observe(page, job)
            assert len(observed["fields"]) == 3
            name, degree, resume = observed["fields"]
            assert all(q["required"] for q in observed["fields"])
            hosted_ats.fill(page, name, "Reviewed Name")
            hosted_ats.fill(page, degree, "Master")
            hosted_ats.control(page, resume).set_input_files(
                {"name": "resume.pdf", "mimeType": "application/pdf", "buffer": PDF}
            )
            observed = hosted_ats.observe(page, job)
            assert observed["fields"][0]["value"] == "Reviewed Name"
            assert observed["fields"][1]["value"] == "Master"
            assert observed["fields"][1]["valid"]
            assert observed["fields"][2]["filename"] == "resume.pdf"
            page.locator("title").evaluate("e=>e.textContent='Other company - Engineer'")
            with pytest.raises(PortalDataError) as error:
                hosted_ats.observe(page, job)
            assert error.value.code == "identity_changed"
        finally:
            browser.close()


@pytest.mark.worker_browser
def test_native_multipart_and_react_file_replacement_are_observed(tmp_path, monkeypatch):
    from playwright.sync_api import sync_playwright

    service = live_service(tmp_path, monkeypatch, lever_uploads=True)
    job = prepare(service)
    html = """<title>Synthetic - Engineer</title>
    <div class='posting-headline'><h2>Engineer</h2></div><form id='application-form'>
    <div class='file-upload' aria-labelledby='upload-label-resume' aria-required='true'>
    <div id='upload-label-resume'>Resume/CV *</div><input id='resume' name='resume' type='file'>
    </div></form><script>
    const file=document.querySelector('#resume');file.onchange=async()=>{
      const data=new FormData();data.append('accountId','public-account');
      data.append('resume',file.files[0]);
      const response=await fetch('/parseResume',{method:'POST',body:data});
      if(response.ok){const name=file.files[0].name;file.remove();
        const selected=document.createElement('div');selected.className='file-upload__filename';
        selected.textContent=name;document.querySelector('.file-upload').append(selected);}
    };</script>"""
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True, channel="chromium")
        try:
            context = browser.new_context(offline=True)
            runner = ApplicationRunner(service.store, context)
            results = []

            def intercept(route):
                # Fetch returns a synthetic response; fulfillment stays local.
                class Route:
                    request = route.request

                    def fetch(self, **options):
                        assert options == {"max_redirects": 0, "max_retries": 0, "timeout": 10000}
                        return SimpleNamespace(status=200, dispose=lambda: None)

                    def fulfill(self, *, response):
                        results.append((self.request.method, "allowed"))
                        route.fulfill(
                            status=response.status,
                            body=html if self.request.method == "GET" else "{}",
                            content_type="text/html"
                            if self.request.method == "GET"
                            else "application/json",
                        )

                    def abort(self, reason):
                        results.append((self.request.method, "blocked"))
                        route.abort(reason)

                runner._live_guard(Route())

            context.route("**/*", intercept)
            page = context.new_page()
            runner.pages[job["application_id"]] = page
            page.goto(hosted_ats.page_url(job))
            resume = hosted_ats.observe(page, job)["fields"][0]
            service.request("resume", {"controller": "synthetic-live-controller"})
            assert runner.authorize(
                job,
                service.store.load()["batch_id"],
                {"action": "upload", "sha256": job["file_sha256"]},
            )
            runner.upload_job = job
            hosted_ats.control(page, resume).set_input_files(
                {"name": "resume.pdf", "mimeType": "application/pdf", "buffer": PDF}
            )
            page.locator(".file-upload__filename").wait_for(timeout=3000)
            runner.upload_job = None
            result = hosted_ats.observe(page, job)["fields"][0]
            assert result["resume"] and result["filename"] == "resume.pdf"
            assert ("POST", "allowed") in results
        finally:
            browser.close()


@pytest.mark.worker_browser
@pytest.mark.parametrize("platform", ["lever", "greenhouse"])
def test_live_worker_reaches_review_and_preserves_manual_edit(tmp_path, monkeypatch, platform):
    import time

    from playwright.sync_api import sync_playwright

    service = live_service(tmp_path, monkeypatch, lever_uploads=True)
    job = prepare(service, LEVER if platform == "lever" else GREENHOUSE)
    title = (
        "Synthetic - Engineer"
        if platform == "lever"
        else "Job Application for Engineer at Synthetic"
    )
    html = f"""<title>{title}</title><form id='application-form'>
    <label for='email'>Email*</label><input id='email' required type='email'>
    <div class='file-upload' aria-labelledby='upload-label-resume' aria-required='true'>
    <div id='upload-label-resume'>Resume/CV*</div><input id='resume' name='resume' type='file'>
    </div><span class='resume-upload-working' style='display:none'></span>
    <span class='resume-upload-failure' style='display:none'></span>
    <button type='submit'>Submit application</button></form><script>
    const field=document.querySelector('#resume');field.onchange=async()=>{{
      if('{platform}'==='lever'){{const data=new FormData();
        data.append('accountId','public-account');data.append('resume',field.files[0]);
        document.querySelector('.resume-upload-working').style.display='block';
        await fetch('/parseResume',{{method:'POST',body:data}});
        document.querySelector('.resume-upload-working').style.display='none';
      }}else{{const name=field.files[0].name;field.remove();
        const label=document.createElement('div');
        label.className='file-upload__filename';label.textContent=name;
        document.querySelector('.file-upload').append(label);}}
    }};</script>"""
    service.store.answers.put_answer(
        {
            "question": "Email",
            "value": "reviewed@example.invalid",
            "state": "confirmed",
            "scope": {},
        }
    )
    service.request("resume", {"controller": "synthetic-live-controller"})
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True, channel="chromium")
        try:
            context = browser.new_context(offline=True)
            runner = ApplicationRunner(service.store, context)
            posts = []

            def intercept(route):
                class Route:
                    request = route.request

                    def fetch(self, **options):
                        assert options == {"max_redirects": 0, "max_retries": 0, "timeout": 10000}
                        if self.request.method == "POST":
                            posts.append(self.request.url)
                        return SimpleNamespace(status=200, dispose=lambda: None)

                    def fulfill(self, *, response):
                        route.fulfill(
                            status=response.status,
                            body=html if self.request.method == "GET" else "{}",
                            content_type="text/html"
                            if self.request.method == "GET"
                            else "application/json",
                        )

                    def abort(self, reason):
                        route.abort(reason)

                runner._live_guard(Route())

            context.route("**/*", intercept)
            deadline = time.monotonic() + 12
            while True:
                runner.tick()
                current = service.store.load()["jobs"][0]
                if current["status"] in {"ready_for_review", "needs_input", "needs_recheck"}:
                    break
                assert time.monotonic() < deadline, current["reason"]
                runner.pages[job["application_id"]].wait_for_timeout(250)
            state = service.store.load()
            assert state["jobs"][0]["status"] == "ready_for_review", state["jobs"][0]["reason"]
            assert len(posts) == (1 if platform == "lever" else 0)
            assert all(url.endswith("/parseResume") for url in posts)
            assert (
                service.store.applications.get_application(job["application_id"])["status"]
                == "drafting"
            )
            service.request("review", {"application_id": job["application_id"]})
            runner.tick()
            page = runner.pages[job["application_id"]]
            page.locator("#email").fill("human-edit@example.invalid")
            runner.tick()
            assert page.locator("#email").input_value() == "human-edit@example.invalid"
            assert service.store.load()["jobs"][0]["handed_off"]
        finally:
            browser.close()
