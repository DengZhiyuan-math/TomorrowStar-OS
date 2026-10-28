"""Fixed generic controls extend the isolated browser fixture, never real ATS uploads."""

import json
from html.parser import HTMLParser
from types import SimpleNamespace

import pytest
from test_synthetic_browser_mode import create_browser, synthetic_runner
from worker_preview_support import advance_until

from career_evidence_graph.application_worker_fixtures import (
    BROWSER_FIXTURE_URL,
    browser_fixture_configuration,
    browser_fixture_markup,
    install_browser_fixture,
)


class Inputs(HTMLParser):
    def __init__(self, markup):
        super().__init__()
        self.inputs = {}
        self.feed(markup)

    def handle_starttag(self, tag, attrs):
        if tag == "input":
            attributes = dict(attrs)
            self.inputs.setdefault(attributes.get("name"), []).append(attributes)


def test_fixed_integration_generator_preserves_isolated_runtime_contract(tmp_path):
    root = tmp_path / "integration"
    created = create_browser(root, "integration")
    assert created.returncode == 0, created.stderr
    config = browser_fixture_configuration(root)
    assert config["scenario"] == "integration"
    assert config["applications"] == str(root / "applications")
    assert list((root / "runtime/single-job-worker").iterdir()) == []
    assert list((root / "runtime/single-job-flow").iterdir()) == []
    inputs = Inputs(browser_fixture_markup(config["scenario"])).inputs
    assert inputs["email"][0]["value"] == "wrong-address"
    assert inputs["start_date"][0]["type"] == "date"
    assert "required" in inputs["start_date"][0]
    assert [row["value"] for row in inputs["onsite"]] == ["yes", "no"]
    assert ["checked" in row for row in inputs["onsite"]] == [False, True]
    assert inputs["policy"][0]["type"] == "checkbox"
    assert "required" in inputs["policy"][0] and "checked" not in inputs["policy"][0]
    assert "checked" in inputs["keep_preference"][0]
    assert inputs["untouched"][0]["value"] == "Preserve this value"
    assert "value" not in inputs["checkpoint"][0]


def test_upload_scenario_seeds_only_the_fixed_workable_job(tmp_path):
    from career_evidence_graph.career_portal_data import ApplicationStore

    root = tmp_path / "integration-upload"
    created = create_browser(root, "integration-upload")
    assert created.returncode == 0, created.stderr
    config = browser_fixture_configuration(root)
    assert config["scenario"] == "integration-upload"
    assert ApplicationStore(root / "applications").list_applications()[0]["url"] == (
        "https://apply.workable.com/synthetic-employer/j/SYNTHETIC1/apply/"
    )
    assert list((root / "runtime/single-job-worker").iterdir()) == []
    markup = browser_fixture_markup(config["scenario"])
    assert 'data-ui="resume"' in markup and "form/upload/resume" in markup
    assert Inputs(markup).inputs["checkpoint"][0].get("value") is None


def test_upload_fixture_receiver_binds_one_pdf_and_retains_remote_bytes(tmp_path):
    import hashlib
    from http.client import HTTPConnection

    from career_evidence_graph.application_worker_fixtures import create_browser_upload_receiver
    from career_evidence_graph.workable_uploads import ResumeUpload

    root = tmp_path / "integration-upload"
    assert create_browser(root, "integration-upload").returncode == 0
    pdf = b"%PDF-1.4 synthetic fixture upload only"
    server, token = create_browser_upload_receiver(root)

    def request(method, path, body=None, **headers):
        connection = HTTPConnection("127.0.0.1", server.server_port, timeout=2)
        try:
            connection.request(method, path, body=body, headers=headers)
            response = connection.getresponse()
            return response.status, response.read()
        finally:
            connection.close()

    try:
        assert request("GET", "/presign")[0] == 403
        headers = {"X-Synthetic-Receiver": token}
        status, raw = request("GET", "/presign", **headers)
        assert status == 200 and json.loads(raw)["uploadPostUrl"]["fields"]["bucket"] == (
            "workable-application-form"
        )
        approved = root / "approved.pdf"
        approved.write_bytes(pdf)
        protocol = ResumeUpload(
            {
                "job_url": "https://apply.workable.com/synthetic-employer/j/SYNTHETIC1/apply/",
                "file_path": str(approved),
            }
        )
        assert (
            protocol.validate(json.loads(raw))["downloadUrl"]
            == (server.synthetic_descriptor["downloadUrl"])
        )
        body = (
            b'--synthetic\r\nContent-Disposition: form-data; name="file"; '
            b'filename="synthetic.pdf"\r\nContent-Type: application/pdf\r\n\r\n'
            + pdf
            + b"\r\n--synthetic--\r\n"
        )
        assert (
            request(
                "POST",
                "/upload",
                body,
                **headers,
                **{"Content-Type": "multipart/form-data; boundary=synthetic"},
            )[0]
            == 204
        )
        assert request("GET", "/object", **headers) == (200, pdf)
        assert (
            request(
                "POST",
                "/upload",
                body,
                **headers,
                **{"Content-Type": "multipart/form-data; boundary=synthetic"},
            )[0]
            == 409
        )
        assert request("POST", "/apply", b"{}", **headers)[0] == 404
        evidence = json.loads((root / "runtime/browser-upload-receiver/events.json").read_text())
        assert evidence["uploads"] == [
            {"sha256": hashlib.sha256(pdf).hexdigest(), "size": len(pdf)}
        ]
        assert evidence["readbacks"] == 1 and evidence["submissions"] == 0
    finally:
        server.shutdown()
        server.server_close()


@pytest.mark.parametrize(
    "fixture",
    [
        {"schemaVersion": 1, "scenario": "integration", "html": "<form>"},
        {"schemaVersion": 1, "scenario": "integration", "url": "https://employer.invalid"},
        {"schemaVersion": 1, "scenario": "integration-unreviewed"},
    ],
)
def test_integration_does_not_admit_caller_content_or_scenario_variants(tmp_path, fixture):
    root = tmp_path / "integration"
    assert create_browser(root, "integration").returncode == 0
    (root / "browser-fixture.json").write_text(json.dumps(fixture))
    with pytest.raises(ValueError, match="synthetic-browser-scenario"):
        browser_fixture_configuration(root)


def test_integration_fulfills_only_one_guarded_get_and_never_continues_transport(tmp_path):
    root = tmp_path / "integration"
    assert create_browser(root, "integration").returncode == 0
    routes, guarded = [], []
    context = SimpleNamespace(
        route=lambda _pattern, callback: routes.append(callback),
        route_web_socket=lambda *_args: None,
    )

    def live_guard(route):
        guarded.append((route.request.method, route.request.url))
        route.continue_()

    install_browser_fixture(context, SimpleNamespace(_live_guard=live_guard), root)
    for method, url in (
        ("GET", BROWSER_FIXTURE_URL),
        ("POST", BROWSER_FIXTURE_URL),
        ("PUT", BROWSER_FIXTURE_URL),
        ("GET", BROWSER_FIXTURE_URL + "?other=1"),
        ("GET", "https://employer.invalid/upload"),
    ):
        outcomes = []
        route = SimpleNamespace(
            request=SimpleNamespace(method=method, url=url),
            fulfill=lambda outcomes=outcomes, **_payload: outcomes.append("fulfilled"),
            abort=lambda _reason, outcomes=outcomes: outcomes.append("blocked"),
            continue_=lambda: pytest.fail("Fixture continued a real network request"),
        )
        routes[-1](route)
        assert outcomes == [
            "fulfilled" if method == "GET" and url == BROWSER_FIXTURE_URL else "blocked"
        ]
    assert len(guarded) == 5


@pytest.mark.parametrize("scenario", ["dom", "manual", "unknown", "integration"])
def test_fixed_document_satisfies_bounded_fetch_without_any_network(tmp_path, scenario):
    root = tmp_path / "bounded-document"
    assert create_browser(root, scenario).returncode == 0
    routes, responses = [], []
    context = SimpleNamespace(
        route=lambda _pattern, callback: routes.append(callback),
        route_web_socket=lambda *_args: None,
    )

    def live_guard(route):
        response = route.fetch(max_redirects=0, max_retries=0, timeout=10000)
        assert response.status == 200
        route.fulfill(response=response)
        response.dispose()

    install_browser_fixture(context, SimpleNamespace(_live_guard=live_guard), root)
    routes[-1](
        SimpleNamespace(
            request=SimpleNamespace(method="GET", url=BROWSER_FIXTURE_URL),
            fetch=lambda **_: pytest.fail("Fixed document must not use real HTTP transport"),
            fulfill=lambda **payload: responses.append(payload),
            abort=lambda *_: pytest.fail("Fixed document was rejected"),
        )
    )
    assert len(responses) == 1 and responses[0]["status"] == 200
    assert "Synthetic" in responses[0]["body"]
    for method, url, options in (
        ("POST", BROWSER_FIXTURE_URL, {}),
        ("GET", BROWSER_FIXTURE_URL + "?other=1", {}),
        ("GET", BROWSER_FIXTURE_URL, {"max_redirects": 1}),
    ):

        def reject_guard(route, options=options):
            with pytest.raises(ValueError):
                route.fetch(**({"max_redirects": 0, "max_retries": 0, "timeout": 10000} | options))

        # The same wrapper must fail before delegating to a real transport.
        install_browser_fixture(context, SimpleNamespace(_live_guard=reject_guard), root)
        routes[-1](
            SimpleNamespace(
                request=SimpleNamespace(method=method, url=url),
                fetch=lambda **_: pytest.fail("Rejected request reached real HTTP transport"),
            )
        )


@pytest.mark.worker_browser
def test_legacy_integration_keeps_values_until_manual_correction_on_the_original_page(
    tmp_path, monkeypatch
):
    """Legacy batch recheck acknowledges manual corrections without a single-job choice."""
    with synthetic_runner(tmp_path, monkeypatch, "integration") as (service, runner, _context):
        for question, value in (
            ("Available for synthetic onsite work?", "Yes"),
            ("Synthetic policy acknowledgement", "Synthetic policy acknowledgement"),
            ("Synthetic start date", "2026-11-01"),
        ):
            service.store.answers.put_answer(
                {"question": question, "value": value, "scope": {}, "state": "confirmed"}
            )
        job = advance_until(service, runner, lambda row: row["status"] == "needs_input")
        assert job["status"] == "needs_input", job["reason"]
        assert [question["question"] for question in job["questions"]] == [
            "Manual acceptance checkpoint"
        ]
        page = runner.pages[job["application_id"]]
        assert page.locator("input[name=email]").input_value() == "wrong-address"
        assert page.locator("input[name=onsite][value=no]").is_checked()
        assert {row["question"] for row in job["form_state"]["differences"]} == {
            "Email",
            "Available for synthetic onsite work?",
        }
        page.locator("input[name=email]").fill("synthetic@example.invalid")
        page.locator("input[name=onsite][value=yes]").check()
        service.request("recheck", {"application_id": job["application_id"], "acknowledge": True})
        runner.tick()
        job = advance_until(service, runner, lambda row: row["status"] == "needs_input")
        assert [question["question"] for question in job["questions"]] == [
            "Manual acceptance checkpoint"
        ]
        assert runner.pages[job["application_id"]] is page
        assert page.locator("input[name=email]").input_value() == "synthetic@example.invalid"
        assert page.locator("[role=combobox]").input_value() == "Switzerland"
        assert page.locator("input[name=onsite][value=yes]").is_checked()
        assert not page.locator("input[name=onsite][value=no]").is_checked()
        assert page.locator("input[name=policy]").is_checked()
        assert page.locator("input[name=start_date]").input_value() == "2026-11-01"
        assert page.locator("input[name=keep_preference]").is_checked()
        assert page.locator("input[name=untouched]").input_value() == "Preserve this value"
        assert page.locator("input[name=checkpoint]").input_value() == ""
        assert page.locator("input[type=file]").evaluate("e=>e.files[0].name") == "synthetic.pdf"
        assert page.evaluate("window.syntheticSubmitAttempts") == 0
        verified = [
            row
            for row in job["observations"]
            if row.get("action") == "fill" and row.get("verified")
        ]
        assert len(verified) == 4
        uploads = [
            row
            for row in job["observations"]
            if row.get("action") == "action_result"
            and row.get("result") == "verified"
            and row.get("intent", {}).get("action") == "upload"
        ]
        assert len(uploads) == 1
        assert job["intent"] is None
        before = list(job["observations"])
        runner.tick()
        runner.pump()
        assert service.store.load()["jobs"][0]["observations"] == before


@pytest.mark.worker_browser
def test_upload_integration_uses_production_guard_and_reads_one_remote_pdf(tmp_path, monkeypatch):
    import hashlib

    with synthetic_runner(tmp_path, monkeypatch, "integration-upload") as (
        service,
        runner,
        _context,
    ):
        for question, value in (
            ("Available for synthetic onsite work?", "Yes"),
            ("Synthetic policy acknowledgement", "Synthetic policy acknowledgement"),
            ("Synthetic start date", "2026-11-01"),
            ("Manual acceptance checkpoint", "Approved synthetic checkpoint"),
        ):
            service.store.answers.put_answer(
                {"question": question, "value": value, "scope": {}, "state": "confirmed"}
            )
        # This case isolates the ordinary upload protocol. The preceding case
        # exercises protected conflicting values; here the initial values agree.
        runner.context.add_init_script("""document.addEventListener('DOMContentLoaded',()=>{
          document.querySelector('[name=email]').value='synthetic@example.invalid';
          document.querySelector('[name=onsite][value=no]').checked=false;
          document.querySelector('[name=onsite][value=yes]').checked=true;
        });""")
        job = advance_until(service, runner, lambda row: row["status"] == "ready_for_review")
        assert job["status"] == "ready_for_review", job["reason"]
        baseline = {
            field["question"]: field["value"] for field in job["form_state"]["baseline"].values()
        }
        assert baseline["Email"] == "synthetic@example.invalid"
        assert baseline["Available for synthetic onsite work?"] == "Yes"
        assert not job["form_state"].get("choices")
        evidence_path = service.store.root.parent / "browser-upload-receiver/events.json"
        evidence = json.loads(evidence_path.read_text())
        assert evidence == {
            "presigns": 1,
            "uploads": [
                {
                    "sha256": hashlib.sha256(b"%PDF-1.4 synthetic only").hexdigest(),
                    "size": len(b"%PDF-1.4 synthetic only"),
                }
            ],
            "readbacks": 1,
            "submissions": 0,
        }
        verified = [
            row for row in job["observations"] if row.get("action") == "workable_upload_verified"
        ]
        assert len(verified) == 1 and verified[0]["remote_sha256"] == job["file_sha256"]
        page = runner.pages[job["application_id"]]
        assert page.locator("input[name=email]").input_value() == "synthetic@example.invalid"
        assert page.locator("input[name=keep_preference]").is_checked()
        assert page.locator("input[name=untouched]").input_value() == "Preserve this value"
        assert page.evaluate("window.syntheticSubmitAttempts") == 0
        assert page.locator("input[type=file]").evaluate("e=>e.files[0].name") == "synthetic.pdf"
        before = evidence_path.read_bytes()
        runner.tick()
        runner.pump()
        assert evidence_path.read_bytes() == before
