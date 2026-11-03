"""A host-admitted native file delivery may send its own upload once (onlyfy, 2026-11-03).

onlyfy posts the file to the page's own URL as a Next.js server action. The same
endpoint was blocked at page load, so the guard's fast path silently aborted the
upload during the takeover and the widget showed "That didn't work".
"""

import base64
import hashlib
import json
from types import SimpleNamespace

import pytest
from test_workable_bootstrap_diagnostic import SyntheticPage
from test_workable_uploads import URL, setup_service

from career_evidence_graph import application_worker_browser as browser
from career_evidence_graph.application_worker_browser import ApplicationRunner

RAW = b"%PDF-1.4 synthetic resume bytes"


class Request(SimpleNamespace):
    """A Playwright request is hashable; the guard keys tracked requests by it."""

    __hash__ = object.__hash__


@pytest.fixture
def guarded(tmp_path, monkeypatch):
    service = setup_service(tmp_path, monkeypatch)
    page = SyntheticPage()
    runner = ApplicationRunner(service.store, None)
    job = service.store.load()["jobs"][0]
    runner.pages[job["application_id"]] = page
    runner.page_ids[page] = "native-page"
    # The page stays native for the whole test, as during a borrowed takeover.
    runner._assistance_run = ({"binding": {"application_id": job["application_id"]}}, "run")
    return service, runner, page, job


def send(runner, page, url=URL, *, method="POST", body=b"{}"):
    request = Request(
        method=method,
        url=url,
        resource_type="fetch",
        headers={"content-type": "multipart/form-data; boundary=x"},
        post_data_buffer=body,
        frame=page.main_frame,
        redirected_from=None,
        is_navigation_request=lambda: False,
    )
    route = SimpleNamespace(request=request, outcome="unset")
    route.continue_ = lambda: setattr(route, "outcome", "continued")
    route.fetch = lambda **_: pytest.fail("a native upload is continued, never refetched")
    route.abort = lambda reason: setattr(route, "outcome", reason)
    runner._live_guard(route)
    return route.outcome


def authorize(runner, job):
    payload = {
        "kind": "file",
        "material_ref": "e" * 64,
        "sha256": hashlib.sha256(RAW).hexdigest(),
        "size_bytes": len(RAW),
        "filename": "resume.pdf",
        "bytes_base64": base64.b64encode(RAW).decode(),
    }
    runner._authorize_native_upload(
        {"binding": {"application_id": job["application_id"]}},
        payload,
        {"material_id": "resume"},
        {"call_id": "native-cv"},
    )


def diagnostics(runner):
    return [row for row in runner.transports if row.get("action") == "request_diagnostic"]


def multipart(raw=RAW):
    return b"--x\r\nContent-Type: application/pdf\r\n\r\n" + raw + b"\r\n--x--"


def test_admitted_delivery_sends_its_upload_once_after_a_page_load_block(guarded):
    service, runner, page, job = guarded
    # Page load: the same endpoint's action POST is blocked and remembered.
    assert send(runner, page) == "blockedbyclient"
    authorize(runner, job)
    authorized = [r for r in runner.transports if r.get("action") == "native_upload_authorized"]
    assert len(authorized) == 1 and authorized[0]["sha256"] == hashlib.sha256(RAW).hexdigest()
    assert "raw" not in authorized[0] and RAW.decode() not in json.dumps(runner.transports)

    assert send(runner, page, body=multipart()) == "continued"
    permitted = diagnostics(runner)[-1]
    assert permitted["stage"] == "request_permitted"
    assert permitted["reason"] == "native_material_upload"
    # The response status is kept with the upload record, like a script upload.
    request = next(iter(runner.requests))
    runner.transport(request, "response", 200)
    assert runner.transports[-1]["kind"] == "native_material_upload"
    assert runner.transports[-1]["http_status"] == 200

    # Single use: the same upload again is blocked and recorded, not silently aborted.
    before = len(diagnostics(runner))
    assert send(runner, page, body=multipart()) == "blockedbyclient"
    assert len(diagnostics(runner)) == before + 1
    assert diagnostics(runner)[-1]["stage"] == "request_blocked"
    assert diagnostics(runner)[-1]["native_takeover"] is True


@pytest.mark.parametrize(
    "case", ["none", "expired", "no_file", "cross_site", "base64", "subdomain"]
)
def test_only_a_valid_authorization_carrying_the_file_to_the_ats_site_is_sent(guarded, case):
    service, runner, page, job = guarded
    assert send(runner, page) == "blockedbyclient"
    if case != "none":
        authorize(runner, job)
    if case == "expired":
        runner.native_uploads[page]["expires_at"] = 0
    url = {
        "cross_site": "https://uploads.example.invalid/apply",
        "subdomain": "https://files.workable.com/upload",
    }.get(case, URL)
    body = {
        "no_file": multipart(b"other bytes"),
        "base64": b'{"file":"' + base64.b64encode(RAW) + b'"}',
    }.get(case, multipart())
    outcome = send(runner, page, url, body=body)
    if case in {"base64", "subdomain"}:
        assert outcome == "continued"
        return
    assert outcome == "blockedbyclient"
    # Every block during the takeover is recorded.
    assert diagnostics(runner)[-1]["stage"] == "request_blocked"
    assert diagnostics(runner)[-1]["native_takeover"] is True
    if case != "none":
        assert runner.native_uploads[page]["used"] is False


def test_same_site_keeps_the_job_origin_and_its_registrable_site():
    job = "https://hexagon-robotics.onlyfy.jobs/application/en/apply/1"
    assert browser._same_site("https://hexagon-robotics.onlyfy.jobs/x", job)
    assert browser._same_site("https://upload.onlyfy.jobs/x", job)
    assert not browser._same_site("http://hexagon-robotics.onlyfy.jobs/x", job)
    assert not browser._same_site("https://onlyfy.jobs.evil.invalid/x", job)
    assert not browser._same_site("https://example.co.uk/x", "https://jobs.acme.co.uk/1")
    assert browser._same_site("https://cdn.acme.co.uk/x", "https://jobs.acme.co.uk/1")
    assert not browser._same_site("http://127.0.0.2/x", "http://127.0.0.1/1")


MULTIPART = {"content-type": "multipart/form-data; boundary=----x", "next-action": "abc"}


def blob_send(runner, page, url=URL, *, headers=MULTIPART):
    """A FormData File is a Blob: CDP gives Playwright no request body for it."""
    request = Request(
        method="POST",
        url=url,
        resource_type="fetch",
        headers=dict(headers),
        post_data_buffer=None,
        frame=page.main_frame,
        redirected_from=None,
        is_navigation_request=lambda: False,
    )
    route = SimpleNamespace(request=request, outcome="unset")
    route.continue_ = lambda: setattr(route, "outcome", "continued")
    route.abort = lambda reason: setattr(route, "outcome", reason)
    runner._live_guard(route)
    return route.outcome, request


def test_blob_upload_is_sent_by_its_shape_and_its_block_is_described(guarded):
    service, runner, page, job = guarded
    # Before the delivery the same send is blocked; its row names the body's shape.
    assert blob_send(runner, page)[0] == "blockedbyclient"
    blocked = diagnostics(runner)[-1]
    assert blocked["native_takeover"] is True
    assert blocked["body"] == {
        "readable": False,
        "length": None,
        "content_type": "multipart/form-data",
        "content_length": None,
        "next_action": True,
    }
    authorize(runner, job)
    outcome, request = blob_send(runner, page)
    assert outcome == "continued"
    permitted = diagnostics(runner)[-1]
    assert (permitted["reason"], permitted["match"], permitted["send"]) == (
        "native_material_upload",
        "shape",
        1,
    )
    # A 2xx answer uses the authorization up; the next send is blocked again.
    runner.transport(request, "response", 200)
    assert runner.native_uploads[page]["used"] is True
    assert blob_send(runner, page)[0] == "blockedbyclient"


@pytest.mark.parametrize(
    ("case", "url", "headers"),
    [
        ("not_multipart", URL, {"content-type": "application/json"}),
        ("cross_site", "https://uploads.example.invalid/apply", MULTIPART),
        ("too_short", URL, {**MULTIPART, "content-length": str(len(RAW) - 1)}),
        ("expired", URL, MULTIPART),
    ],
)
def test_a_blob_send_of_another_shape_or_place_stays_blocked(guarded, case, url, headers):
    service, runner, page, job = guarded
    authorize(runner, job)
    if case == "expired":
        runner.native_uploads[page]["expires_at"] = 0
    assert blob_send(runner, page, url, headers=headers)[0] == "blockedbyclient"
    assert diagnostics(runner)[-1]["stage"] == "request_blocked"
    assert runner.native_uploads[page]["sends"] == []


def test_a_retry_follows_only_a_failed_or_unanswered_send_up_to_three(guarded, monkeypatch):
    service, runner, page, job = guarded
    authorize(runner, job)
    outcome, first = blob_send(runner, page, headers={**MULTIPART, "content-length": "999"})
    assert outcome == "continued"
    # Still waiting for its answer: a second send is not a retry yet.
    assert blob_send(runner, page)[0] == "blockedbyclient"
    runner.transport(first, "response", 500)
    outcome, second = blob_send(runner, page)
    assert outcome == "continued"
    # Unanswered for more than 10 s, it may be retried once more.
    clock = browser.time.time() + 11
    monkeypatch.setattr(browser.time, "time", lambda: clock)
    runner.native_uploads[page]["expires_at"] = clock + 60
    outcome, third = blob_send(runner, page)
    assert outcome == "continued"
    runner.transport(third, "requestfailed")
    # Three sends are the limit for one authorization.
    assert blob_send(runner, page)[0] == "blockedbyclient"
    assert [row["send"] for row in diagnostics(runner) if row.get("match")] == [1, 2, 3]
