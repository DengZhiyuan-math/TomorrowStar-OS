"""Public worker behavior on unbranded synthetic forms. No external network."""

import base64
import hashlib
import json
from contextlib import contextmanager
from types import SimpleNamespace

import pytest
from test_hosted_ats import PDF, prepare
from worker_preview_support import advance_until

from career_evidence_graph.application_worker import WorkerService, start_run
from career_evidence_graph.application_worker_browser import ApplicationRunner
from career_evidence_graph.career_portal_data import ApplicationStore, PortalDataError
from career_evidence_graph.job_screening import screen_applications

URL = "https://careers.example.test/openings/engineer?job_id=42"
FIELDS = """<label>Full name *<input name='person' required></label>
<label>Email *<input name='contact' type='email' required></label>
<label>Resume/CV *<input name='attachment' type='file' required></label>"""


def test_generic_sync_retry_preserves_external_edits_without_browser_actions(tmp_path, monkeypatch):
    apps = tmp_path / "applications"
    apps.mkdir()
    service = WorkerService(ApplicationStore(apps), tmp_path / "worker", live=True, generic=True)
    monkeypatch.setattr(service, "spawn", lambda: None)
    job = prepare(service, URL)
    state = service.store.load()
    current = state["jobs"][0]
    changed = service.store.applications.update_application(
        job["application_id"], {"notes": "Keep this external edit"}, job["revision"]
    )
    service.store.sync(current, "Review the existing page")
    service.store.save(state)
    assert current["sync_error"] == "revision-conflict"
    result = service.request(
        "retry-sync",
        {
            "application_id": job["application_id"],
            "revision": changed["revision"],
            "acknowledge": True,
        },
    )
    app = service.store.applications.get_application(job["application_id"])
    assert app["notes"] == "Keep this external edit"
    assert app["next_action"] == "Review the existing page"
    assert app["status"] == "drafting"
    assert result["jobs"][0]["sync_error"] == ""
    assert result["jobs"][0]["intent"] is None
    assert result["commands"] == []
    assert result["control"] == "paused"


def test_generic_selection_is_explicit_and_preserves_distinct_query_jobs(tmp_path, monkeypatch):
    apps = tmp_path / "applications"
    apps.mkdir()
    store = ApplicationStore(apps)
    strict = WorkerService(store, tmp_path / "strict", live=True)
    generic = WorkerService(store, tmp_path / "generic", live=True, generic=True)
    monkeypatch.setattr(generic, "spawn", lambda: None)
    records = [
        store.create_application(
            {
                "company": "Synthetic",
                "role_title": "AI Engineer",
                "status": "drafting",
                "url": url,
                "application_strategy": "batch",
            }
        )
        for url in (URL, URL.replace("42", "43"))
    ]
    payload = {
        "jobs": [
            {
                "application_id": r["id"],
                "revision": r["revision"],
                "country": "CHE",
                "filename": "resume.pdf",
                "file_base64": base64.b64encode(PDF).decode(),
            }
            for r in records
        ]
    }
    with pytest.raises(PortalDataError) as error:
        strict.request("prepare", payload)
    assert error.value.code == "unsupported_platform"
    generic.request("prepare", payload)
    assert [j["job_url"] for j in generic.snapshot()["jobs"]] == [URL, URL.replace("42", "43")]
    assert not screen_applications(records)[0]["screening"]["worker_preparable"]
    hints = screen_applications(records, allow_generic=True)
    assert all(r["screening"]["worker_preparable"] for r in hints)
    assert all(r["screening"]["generic_preflight"] for r in hints)


@contextmanager
def native_form(tmp_path, monkeypatch, html, resources=None, read_grants=None, platform="generic"):
    from playwright.sync_api import sync_playwright

    monkeypatch.setenv("PLAYWRIGHT_BROWSERS_PATH", "0")
    apps = tmp_path / "applications"
    apps.mkdir()
    service = WorkerService(
        ApplicationStore(apps), tmp_path / "worker", live=True, generic=platform == "generic"
    )
    monkeypatch.setattr(service, "spawn", lambda: None)
    target = {
        "generic": URL,
        "lever": "https://jobs.lever.co/synthetic/00000000-0000-0000-0000-000000000001",
        "greenhouse": "https://job-boards.greenhouse.io/synthetic/jobs/123",
    }[platform]
    job = prepare(service, target)
    assert job["platform"] == platform
    assert job["job_url"] == target
    for question, value in (
        ("Full name", "Synthetic Person"),
        ("Email", "synthetic@example.invalid"),
    ):
        service.store.answers.put_answer(
            {"question": question, "value": value, "scope": {}, "state": "confirmed"}
        )
    title = {
        "generic": "Engineer — Synthetic Careers",
        "lever": "Synthetic - Engineer",
        "greenhouse": "Job Application for Engineer at Synthetic",
    }[platform]
    html = f"<title>{title}</title><h1>Engineer</h1>" + html
    service.request("resume", {"controller": "synthetic-controller"})
    if read_grants is not None:
        (service.store.root / "public-read-grants.json").write_text(
            json.dumps({"schemaVersion": 1, "grants": read_grants})
        )
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True, channel="chromium")
        try:
            context = browser.new_context(offline=True)
            start_run(service.store)
            runner = ApplicationRunner(service.store, context)
            posts = []

            def intercept(route):
                class Route:
                    request = route.request

                    def fetch(self, **options):
                        assert options == {"max_redirects": 0, "max_retries": 0, "timeout": 10000}
                        return SimpleNamespace(status=200, dispose=lambda: None)

                    def fulfill(self, *, response):
                        assert response.status == 200
                        if self.request.method != "GET":
                            posts.append(self.request.method)
                        body = (resources or {}).get(self.request.url, html)
                        route.fulfill(
                            status=200,
                            body=body,
                            content_type="text/javascript"
                            if self.request.resource_type == "script"
                            else "text/html",
                        )

                    def abort(self, reason):
                        route.abort(reason)

                runner._live_guard(Route())

            context.route("**/*", intercept)
            yield service, runner, job, posts
        finally:
            browser.close()


def test_retired_public_grants_do_not_dispatch_unknown_posts(tmp_path, monkeypatch):
    apps = tmp_path / "applications"
    apps.mkdir()
    service = WorkerService(ApplicationStore(apps), tmp_path / "worker", live=True, generic=True)
    monkeypatch.setattr(service, "spawn", lambda: None)
    job = prepare(service, URL)
    endpoint = "https://careers.example.test/public-form"
    body = b'{"query":"query Job { job { form } }","variables":{"job":"42"}}'
    grant = {"job_url": URL, "url": endpoint, "body_sha256": hashlib.sha256(body).hexdigest()}
    path = service.store.root / "public-read-grants.json"
    path.write_text(json.dumps({"schemaVersion": 1, "grants": [grant]}))
    runner = ApplicationRunner(service.store, None)
    page = object()
    runner.pages[job["application_id"]] = page

    def outcome(payload=body, url=endpoint, current=page, method="POST", resource="fetch"):
        request = SimpleNamespace(
            method=method,
            url=url,
            post_data_buffer=payload,
            headers={"content-type": "application/json"},
            resource_type=resource,
            frame=SimpleNamespace(page=current),
            is_navigation_request=lambda: resource == "document",
        )
        route = SimpleNamespace(request=request, outcome="")
        route.continue_ = lambda: setattr(route, "outcome", "allowed")
        route.abort = lambda _: setattr(route, "outcome", "blocked")
        runner._live_guard(route)
        return route.outcome

    assert outcome() == "blocked"
    assert runner.blocked_pages[page] == "unverified_send_path"
    runner.editing_pages.add(page)
    assert outcome() == "blocked"
    assert outcome(body.replace(b'"42"', b'"private answer"')) == "blocked"
    assert outcome(body + b" ") == "blocked"
    assert outcome(url=endpoint + "?private=value") == "blocked"
    assert outcome(current=object()) == "blocked"
    assert outcome(method="PUT") == "blocked"
    assert outcome(resource="document") == "blocked"
    path.write_text(json.dumps({"schemaVersion": 1, "grants": [{**grant, "extra": True}]}))
    assert ApplicationRunner(service.store, None).store is service.store


@pytest.mark.worker_browser
def test_opaque_public_post_waits_without_using_retired_grant(tmp_path, monkeypatch):
    endpoint = "https://careers.example.test/public-form"
    body = '{"query":"query Job { job { form } }","variables":{"job":"42"}}'
    grant = {
        "job_url": URL,
        "url": endpoint,
        "body_sha256": hashlib.sha256(body.encode()).hexdigest(),
    }
    html = """<script>fetch('/public-form',{method:'POST',
    headers:{'Content-Type':'application/json'},body:PUBLIC_BODY})
    .then(r=>r.text()).then(text=>{document.body.insertAdjacentHTML('beforeend',text);
    document.querySelector('input').oninput=()=>fetch('/public-form',{method:'POST',
    headers:{'Content-Type':'application/json'},body:JSON.stringify({query:'mutation Save',
    variables:{answer:document.querySelector('input').value}})}).catch(()=>{})})</script>""".replace(
        "PUBLIC_BODY", json.dumps(body)
    )
    with native_form(
        tmp_path, monkeypatch, html, {endpoint: "<form>" + FIELDS + "</form>"}, [grant]
    ) as (service, runner, job, posts):
        for _ in range(6):
            runner.tick()
        current = service.store.load()["jobs"][0]
        assert current["status"] == "needs_recheck", current["reason"]
        assert current["reason"] == "unverified_send_path"
        assert current["intent"]["action"] == "open"
        assert any(
            event.get("stage") == "request_blocked"
            and event.get("reason") == "unverified_send_path"
            and event.get("dispatch") == "not_sent"
            for event in current["observations"]
        )
        page = runner.pages[job["application_id"]]
        assert page.locator("input[name=person]").count() == 0
        assert posts == []
        assert not page.is_closed()


@pytest.mark.worker_browser
def test_unverified_websocket_write_pauses_only_the_owned_job(tmp_path, monkeypatch):
    html = (
        "<form>"
        + FIELDS
        + "</form><script>document.querySelector('input').oninput=()=>{new WebSocket('wss://careers.example.test/save')};</script>"
    )
    with native_form(tmp_path, monkeypatch, html) as (service, runner, job, posts):
        current = advance_until(service, runner, lambda row: row["status"] == "needs_recheck")
        assert current["status"] == "needs_recheck"
        assert current["reason"] == "unverified_send_path"
        assert not runner.pages[job["application_id"]].is_closed()
        assert posts == []


@pytest.mark.worker_browser
def test_native_form_without_ats_classes_reaches_review_without_submit(tmp_path, monkeypatch):
    html = (
        "<form>"
        + FIELDS
        + """<button type='submit'>Submit application</button></form>
    <script>window.finalActions=0;document.querySelector('form').onsubmit=e=>{
      e.preventDefault();window.finalActions++};</script>"""
    )
    with native_form(tmp_path, monkeypatch, html) as (service, runner, job, posts):
        current = advance_until(service, runner, lambda row: row["status"] == "ready_for_review")
        assert current["status"] == "ready_for_review", current["reason"]
        page = runner.pages[job["application_id"]]
        assert page.get_by_label("Full name", exact=False).input_value() == "Synthetic Person"
        assert page.get_by_label("Email", exact=False).input_value() == "synthetic@example.invalid"
        assert page.get_by_label("Resume/CV", exact=False).evaluate("e=>e.files[0].size") == len(
            PDF
        )
        assert page.evaluate("window.finalActions") == 0
        assert posts == []
        assert (
            service.store.applications.get_application(job["application_id"])["status"]
            == "drafting"
        )


@pytest.mark.worker_browser
def test_formless_required_radio_waits_and_resumes_after_saved_answer(tmp_path, monkeypatch):
    html = (
        FIELDS
        + """<style>.required::after{content:'*'}</style>
    <fieldset><label for='virtual-id' class='required'>Located in Switzerland?</label>
    <label for='yes'>Yes</label><input id='yes' name='location' type='radio' value='yes'>
    <label for='no'>No</label><input id='no' name='location' type='radio' value='no'></fieldset>
    <button onclick='window.finalActions++'>Submit application</button>
    <script>window.finalActions=0</script>"""
    )
    with native_form(tmp_path, monkeypatch, html) as (service, runner, job, posts):
        current = advance_until(service, runner, lambda row: row["status"] == "needs_input")
        assert current["status"] == "needs_input", current["reason"]
        assert [q["question"] for q in current["questions"]] == ["Located in Switzerland?"]
        assert current["questions"][0]["options"] == ["Yes", "No"]
        page = runner.pages[job["application_id"]]
        assert page.locator("input[name=person]").input_value() == "Synthetic Person"
        assert not page.locator("#yes").is_checked()
        service.request(
            "answer",
            {
                "application_id": job["application_id"],
                "question_id": current["questions"][0]["id"],
                "value": "Yes",
            },
        )
        runner.tick()
        current = advance_until(service, runner, lambda row: row["status"] == "ready_for_review")
        assert current["status"] == "ready_for_review", current["reason"]
        assert page.locator("#yes").is_checked()
        assert page.evaluate("window.finalActions") == 0
        assert posts == []
        assert any(r["question"] == "Located in Switzerland?" for r in service.store.library())


@pytest.mark.worker_browser
def test_unknown_autosave_is_blocked_and_keeps_page_for_manual_review(tmp_path, monkeypatch):
    html = (
        "<form>"
        + FIELDS
        + """<button>Submit application</button></form>
    <script>document.querySelector('input[name=person]').oninput=()=>{
      setTimeout(()=>fetch('/save-draft',{method:'POST',body:'private-draft'}).catch(()=>{}),20)
    }</script>"""
    )
    with native_form(tmp_path, monkeypatch, html) as (service, runner, job, posts):
        current = advance_until(service, runner, lambda row: row["status"] == "needs_recheck")
        assert current["status"] == "needs_recheck", current["reason"]
        assert current["reason"] == "unverified_send_path"
        assert current["page_open"]
        assert posts == []
        page = runner.pages[job["application_id"]]
        assert not page.is_closed()
        assert not current["handed_off"]
        page.evaluate("window.faultPoint = {marker: 'original-page'}")
        original_url = page.url
        for _ in range(4):
            runner.tick()
        assert page.evaluate("window.faultPoint.marker") == "original-page"
        assert page.locator("input[name=person]").input_value() == "Synthetic Person"
        assert service.store.load()["jobs"][0]["status"] == "needs_recheck"
        assert posts == []
        service.request("review", {"application_id": job["application_id"], "acknowledge": True})
        runner.tick()
        current = service.store.load()["jobs"][0]
        assert current["handed_off"] and current["handoff"]["status"] == "complete"
        assert current["status"] == "needs_recheck"
        assert runner.pages[job["application_id"]] is page
        assert page.url == original_url
        assert page.evaluate("window.faultPoint.marker") == "original-page"
        assert page.locator("input[name=person]").input_value() == "Synthetic Person"
        assert posts == []


@pytest.mark.worker_browser
def test_fault_keeps_original_document_and_file_until_human_review(tmp_path, monkeypatch):
    html = (
        "<form>"
        + FIELDS
        + """<button>Submit application</button></form>
        <script>window.finalActions=0;document.querySelector('form').onsubmit=e=>{
          e.preventDefault();window.finalActions++};</script>"""
    )
    with native_form(tmp_path, monkeypatch, html) as (service, runner, job, posts):
        current = advance_until(service, runner, lambda row: row["status"] == "ready_for_review")
        assert current["status"] == "ready_for_review", current["reason"]
        page = runner.pages[job["application_id"]]
        page.evaluate(
            "window.faultDocument=document;"
            "window.faultFile=document.querySelector('[type=file]').files[0];"
            "void fetch('/unknown-save',{method:'POST',body:'synthetic'}).catch(()=>{})"
        )
        page.wait_for_timeout(50)
        runner.tick()
        current = service.store.load()["jobs"][0]
        assert current["status"] == "needs_recheck"
        assert current["reason"] == "unverified_send_path"
        assert not current["handed_off"]
        for _ in range(4):
            runner.tick()
        assert runner.pages[job["application_id"]] is page
        assert page.evaluate("faultDocument===document")
        assert page.evaluate("faultFile===document.querySelector('[type=file]').files[0]")
        assert page.get_by_label("Full name", exact=False).input_value() == "Synthetic Person"
        assert page.get_by_label("Email", exact=False).input_value() == "synthetic@example.invalid"
        assert page.get_by_label("Resume/CV", exact=False).evaluate("e=>e.files[0].size") == len(
            PDF
        )
        assert page.evaluate("window.finalActions") == 0
        assert posts == []
        service.request("review", {"application_id": job["application_id"], "acknowledge": True})
        runner.tick()
        current = service.store.load()["jobs"][0]
        assert current["handoff"]["status"] == "complete"
        assert current["status"] == "needs_recheck"
        assert runner.pages[job["application_id"]] is page
        assert page.evaluate("faultDocument===document")
        assert page.evaluate("faultFile===document.querySelector('[type=file]').files[0]")
        assert page.evaluate("window.finalActions") == 0
        assert posts == []


@pytest.mark.worker_browser
@pytest.mark.parametrize("platform", ["generic", "lever", "greenhouse"])
def test_public_assets_load_but_new_reads_cannot_send_filled_values(
    tmp_path, monkeypatch, platform
):
    asset = "https://boards.cdn.greenhouse.io/app.js"
    fields = FIELDS.replace("name='attachment'", "name='resume'")
    html = (
        "<form id='application-form'>"
        + fields
        + f"<button>Submit</button></form><script src='{asset}'></script>"
    )
    script = """window.publicAsset=1;document.querySelector('input[name=person]').oninput=()=>{
      fetch('/draft?person='+encodeURIComponent(document.querySelector('input').value))
        .then(()=>window.sent=true).catch(()=>window.sent=false)
    }"""
    with native_form(tmp_path, monkeypatch, html, {asset: script}, platform=platform) as (
        service,
        runner,
        job,
        posts,
    ):
        advance_until(service, runner, lambda row: row["status"] == "needs_recheck")
        page = runner.pages[job["application_id"]]
        assert page.evaluate("window.publicAsset") == 1
        current = service.store.load()["jobs"][0]
        assert current["status"] == "needs_recheck", current["reason"]
        assert current["reason"] == "unverified_send_path"
        page.wait_for_function("window.sent !== undefined")
        assert page.evaluate("window.sent") is False
        assert posts == []


@pytest.mark.worker_browser
def test_unique_aria_option_is_selected_and_read_back_before_review(tmp_path, monkeypatch):
    html = (
        "<form>"
        + FIELDS
        + """<label for='country'>Country *</label>
    <input id='country' role='combobox' aria-expanded='false' required>
    <div role='listbox' hidden><button type='button' role='option'>Switzerland</button></div>
    <button type='submit'>Submit application</button></form><script>
    const c=document.querySelector('#country'), list=document.querySelector('[role=listbox]');
    c.oninput=()=>{list.hidden=false;c.setAttribute('aria-expanded','true')};
    list.firstChild.onclick=()=>{c.value='Switzerland';list.hidden=true;
      c.setAttribute('aria-expanded','false')};</script>"""
    )
    with native_form(tmp_path, monkeypatch, html) as (service, runner, job, posts):
        service.store.answers.put_answer(
            {
                "question": "Country",
                "value": "Switzerland",
                "scope": {"application_id": job["application_id"]},
                "state": "confirmed",
            }
        )
        current = advance_until(service, runner, lambda row: row["status"] == "ready_for_review")
        assert current["status"] == "ready_for_review", current["reason"]
        page = runner.pages[job["application_id"]]
        assert page.locator("#country").input_value() == "Switzerland"
        assert page.locator("#country").get_attribute("aria-expanded") == "false"
        assert posts == []


@pytest.mark.worker_browser
def test_optional_autofill_file_is_never_bound_or_selected(tmp_path, monkeypatch):
    html = "<form><input type='file' id='autofill'>" + FIELDS + "<button>Submit</button></form>"
    with native_form(tmp_path, monkeypatch, html) as (service, runner, job, posts):
        current = advance_until(service, runner, lambda row: row["status"] == "ready_for_review")
        assert current["status"] == "ready_for_review", current["reason"]
        page = runner.pages[job["application_id"]]
        assert page.locator("#autofill").evaluate("e=>e.files.length") == 0
        assert page.get_by_label("Resume/CV", exact=False).evaluate("e=>e.files.length") == 1
        assert posts == []


@pytest.mark.worker_browser
def test_custom_required_buttons_pause_instead_of_reporting_complete(tmp_path, monkeypatch):
    html = (
        "<form>"
        + FIELDS
        + """<style>.required::after{content:'*'}</style>
    <fieldset><label class='required'>Work permit?</label>
    <button type='button'>Yes</button><button type='button'>No</button></fieldset>
    <button type='submit'>Submit</button></form>"""
    )
    with native_form(tmp_path, monkeypatch, html) as (service, runner, job, posts):
        current = advance_until(service, runner, lambda row: row["status"] == "needs_recheck")
        assert current["status"] == "needs_recheck", current["reason"]
        assert current["reason"] == "unsupported_structure"
        assert runner.pages[job["application_id"]].locator("input[name=person]").input_value() == ""
        assert posts == []


@pytest.mark.worker_browser
def test_checkbox_group_pauses_before_any_existing_selection_is_changed(tmp_path, monkeypatch):
    html = (
        "<form>"
        + FIELDS
        + """<fieldset><legend>Languages *</legend>
        <label><input type='checkbox' name='languages' value='en' checked>English</label>
        <label><input type='checkbox' name='languages' value='fr' checked>French</label>
        </fieldset><button type='submit'>Submit</button></form>"""
    )
    with native_form(tmp_path, monkeypatch, html) as (service, runner, job, posts):
        service.store.answers.put_answer(
            {
                "question": "Languages",
                "value": "English",
                "scope": {"application_id": job["application_id"]},
                "state": "confirmed",
            }
        )
        runner.tick()
        page = runner.pages[job["application_id"]]
        assert page.get_by_label("English", exact=True).is_checked()
        assert page.get_by_label("French", exact=True).is_checked()
        assert page.get_by_label("Full name", exact=False).input_value() == ""
        assert page.get_by_label("Resume/CV", exact=False).evaluate("e=>e.files.length") == 0
        observed = runner.observe(page, job)
        languages = next(field for field in observed["fields"] if field["question"] == "Languages")
        assert languages["multiple"] is True
        current = service.store.load()["jobs"][0]
        assert current["status"] == "needs_recheck"
        assert current["reason"] == "unsupported_attachments"
        assert posts == []
