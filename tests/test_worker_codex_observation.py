"""Original-page observations are read-only and scoped to one Codex reservation."""

import base64
import threading
import time
from copy import deepcopy
from types import SimpleNamespace

import pytest
from owned_cdp_fake import OwnedCDPFake
from test_single_application_worker import single_worker as single_worker
from test_worker_codex_assistance import retained_assistance_page as retained_assistance_page

from career_evidence_graph.application_worker_browser import ApplicationRunner
from career_evidence_graph.career_portal_data import PortalDataError

SYNTHETIC_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAAC0lEQVR4nGP4DwQACfsD/fteaysAAAAASUVORK5CYII="
)


@pytest.fixture
def owned_codex_page(retained_assistance_page, request):
    service, identifier = retained_assistance_page
    service.request(
        "request-assistance",
        {
            "application_id": identifier,
            "binding": service.assistance_context(identifier)["binding"],
            "request_id": "request-readonly",
        },
    )
    reference = service.assistance_context(identifier)["assistance_ref"]
    service.request(
        "claim-assistance",
        {
            "application_id": identifier,
            "assistance_ref": reference,
            "request_id": "claim-readonly",
        },
    )
    calls = []
    context = SimpleNamespace(browser=SimpleNamespace(is_connected=lambda: True))

    class Page:
        url = reference["binding"]["step"]
        token = reference["binding"]["document_token"]
        loader = "original-loader"
        field_value = "synthetic@example.invalid"
        token_descriptor = None
        screenshot_hook = None

        def is_closed(self):
            return False

        def screenshot(self, **kwargs):
            calls.append(("screenshot", threading.get_ident()))
            if self.screenshot_hook:
                self.screenshot_hook()
            return SYNTHETIC_PNG

    page = Page()
    page.context = context

    class Session:
        def send(self, method, arguments=None):
            calls.append((method, threading.get_ident()))
            if method == "Page.getFrameTree":
                return {
                    "frameTree": {
                        "frame": {"id": "original-frame", "loaderId": page.loader, "url": page.url}
                    }
                }
            if method == "Page.createIsolatedWorld":
                return {"executionContextId": 10}
            if method == "Runtime.evaluate":
                if arguments.get("expression") == "this":
                    return {"result": {"type": "object", "objectId": "original-window"}}
                return {
                    "result": {
                        "value": {
                            "url": page.url,
                            "title": "Original page",
                            "fields": [{"id": "email", "value": page.field_value}],
                        }
                    }
                }
            if method == "Runtime.getProperties":
                return {
                    "result": [
                        page.token_descriptor
                        or {
                            "name": "__tomorrowstarMaterialDocument",
                            "value": {"type": "string", "value": page.token},
                        }
                    ]
                }
            if method == "Runtime.releaseObject":
                return {}
            raise AssertionError(method)

        def detach(self):
            calls.append(("detach", threading.get_ident()))

    context.new_cdp_session = lambda original: (
        Session() if original is page else pytest.fail("wrong page")
    )
    request.addfinalizer(OwnedCDPFake(page).close)
    runner = ApplicationRunner(service.store, None)
    runner.context = context
    runner.pages[identifier] = page
    runner.page_ids[page] = reference["binding"]["page_id"]
    return service, runner, page, reference, calls


def test_observe_retained_page_returns_image_without_checkpoint_or_page_writes(owned_codex_page):
    service, runner, page, reference, calls = owned_codex_page
    before = service.store.path.read_bytes()

    observation = runner.observe_assistance_page(reference)

    assert observation["binding"] == reference["binding"]
    assert observation["data"]["title"] == "Original page"
    assert observation["data"]["fields"][0]["value"] == "synthetic@example.invalid"
    assert observation["page_writes_enabled"] is False
    assert base64.b64decode(observation["image_url"].split(",", 1)[1]).startswith(b"\x89PNG")
    assert service.store.path.read_bytes() == before
    assert runner.pages[reference["binding"]["application_id"]] is page
    assert {ident for _, ident in calls} == {threading.get_ident()}


def test_capture_does_not_hold_business_lock_and_discards_a_concurrent_pause(owned_codex_page):
    service, runner, page, reference, _ = owned_codex_page
    acquired = threading.Event()

    def pause():
        service.request("pause", {"controller": "synthetic-controller"})
        acquired.set()

    def during_capture():
        thread = threading.Thread(target=pause)
        thread.start()
        assert acquired.wait(1), "Page IO must not hold the application write lock"
        thread.join(timeout=1)

    page.screenshot_hook = during_capture
    with pytest.raises(PortalDataError, match="接管范围"):
        runner.observe_assistance_page(reference)
    assert service.store.load()["control"] == "paused"
    assert "owned_page_inspection" not in service.store.load()["jobs"][0]


def test_same_handle_cannot_observe_a_different_current_page_location(owned_codex_page):
    service, runner, page, reference, calls = owned_codex_page
    page.url = "https://synthetic.invalid/other-application"
    before = service.store.path.read_bytes()
    with pytest.raises(PortalDataError):
        runner.observe_assistance_page(reference)
    assert calls == []
    assert service.store.path.read_bytes() == before


def test_response_scope_rejects_navigation_after_capture_without_saved_state_change(
    owned_codex_page,
):
    service, runner, page, reference, _ = owned_codex_page
    captured = runner.observe_assistance_page(reference)
    before = service.store.path.read_bytes()
    assert runner.assistance_read_permitted(reference, document=captured["document"])
    page.loader = "new-document-at-same-url"
    assert not runner.assistance_read_permitted(reference, document=captured["document"])
    assert service.store.path.read_bytes() == before


def test_boolean_generation_is_not_the_integer_generation(owned_codex_page):
    service, runner, _, reference, calls = owned_codex_page
    malformed = deepcopy(reference)
    malformed["generation"] = True
    before = service.store.path.read_bytes()
    with pytest.raises(PortalDataError):
        runner.observe_assistance_page(malformed)
    assert calls == []
    assert service.store.path.read_bytes() == before


@pytest.mark.parametrize(
    "change",
    [
        "document",
        "material",
        "answers",
        "controller",
        "run",
        "source",
        "stale_runtime",
        "stale_page",
        "pause",
        "cancel",
        "unclaimed",
        "removed",
    ],
)
def test_changed_saved_scope_never_collects_or_overwrites_page_content(owned_codex_page, change):
    service, runner, _, reference, calls = owned_codex_page
    state = service.store.load()
    job = state["jobs"][0]
    if change == "document":
        job["form_state"]["binding"]["document_token"] = "new-saved-document"
    elif change == "material":
        job["file_sha256"] = "a" * 64
    elif change == "answers":
        job["answer_refs"] = [{"key": "new-answer", "revision": "new"}]
    elif change == "controller":
        state["controller"] = "different-controller"
    elif change == "run":
        state["runtime"]["id"] = "different-run"
    elif change == "source":
        state["runtime"]["source"]["sha256"] = "a" * 64
    elif change == "stale_runtime":
        state["runtime"]["observed_at"] -= 10
    elif change == "stale_page":
        job["page_observation"]["at"] -= 10
    elif change == "pause":
        state["control"] = "paused"
    elif change == "cancel":
        job["status"] = "cancelled"
    elif change == "unclaimed":
        job["assistance"].update(status="requested", active_writer="none", claim_request_id=None)
    else:
        job.pop("assistance")
    service.store.save(state)
    before = service.store.path.read_bytes()

    assert runner.assistance_read_permitted(reference) is False
    with pytest.raises(PortalDataError):
        runner.observe_assistance_page(reference)
    assert calls == []
    assert service.store.path.read_bytes() == before


def test_same_url_new_live_document_is_rejected_without_token_initialization(owned_codex_page):
    service, runner, page, reference, calls = owned_codex_page
    page.token = None
    before = service.store.path.read_bytes()
    with pytest.raises(PortalDataError, match="文档"):
        runner.observe_assistance_page(reference)
    assert page.token is None
    assert "screenshot" not in [name for name, _ in calls]
    assert service.store.path.read_bytes() == before


def test_foreign_thread_is_rejected_before_any_page_io(owned_codex_page):
    from concurrent.futures import ThreadPoolExecutor

    service, runner, _, reference, calls = owned_codex_page
    before = service.store.path.read_bytes()
    with ThreadPoolExecutor(max_workers=1) as pool:
        result = pool.submit(runner.observe_assistance_page, reference)
        with pytest.raises(PortalDataError, match="线程"):
            result.result(timeout=2)
        assert pool.submit(runner.assistance_read_permitted, reference).result(timeout=2) is False
    assert calls == []
    assert service.store.path.read_bytes() == before


@pytest.mark.parametrize("fault", ["page", "context", "connection", "cua", "guard"])
def test_changed_live_owner_is_rejected_before_capture(owned_codex_page, fault):
    from copy import copy

    service, runner, page, reference, calls = owned_codex_page
    if fault == "page":
        runner.pages[reference["binding"]["application_id"]] = copy(page)
    elif fault == "context":
        page.context = SimpleNamespace(browser=runner.context.browser)
    elif fault == "connection":
        runner.context.browser.is_connected = lambda: False
    elif fault == "cua":
        runner.cua = SimpleNamespace(client=SimpleNamespace(failed=True))
    else:
        runner.handed_off_pages.add(page)
    before = service.store.path.read_bytes()
    with pytest.raises(PortalDataError):
        runner.observe_assistance_page(reference)
    assert calls == []
    assert service.store.path.read_bytes() == before


def test_codex_observation_does_not_publish_non_png_screenshot(owned_codex_page):
    service, runner, page, reference, _ = owned_codex_page
    page.screenshot = lambda **kwargs: b"not an image"
    before = service.store.path.read_bytes()
    with pytest.raises(PortalDataError):
        runner.observe_assistance_page(reference)
    assert service.store.path.read_bytes() == before


@pytest.mark.parametrize("change", ["document", "frame", "field"])
def test_mid_capture_changes_discard_the_result(owned_codex_page, change):
    service, runner, page, reference, _ = owned_codex_page

    def change_page():
        if change == "document":
            page.token = "new-live-document"
        elif change == "frame":
            page.loader = "new-live-loader"
        else:
            page.field_value = "new-user-value@example.invalid"

    page.screenshot_hook = change_page
    before = service.store.path.read_bytes()
    with pytest.raises(PortalDataError):
        runner.observe_assistance_page(reference)
    assert service.store.path.read_bytes() == before


def test_document_accessor_is_rejected_without_invoking_it(owned_codex_page):
    service, runner, page, reference, calls = owned_codex_page
    page.token_descriptor = {"name": "__tomorrowstarMaterialDocument", "get": {"type": "function"}}
    before = service.store.path.read_bytes()
    with pytest.raises(PortalDataError, match="文档"):
        runner.observe_assistance_page(reference)
    assert "screenshot" not in [name for name, _ in calls]
    assert service.store.path.read_bytes() == before


def test_oversized_capture_is_not_published(owned_codex_page):
    service, runner, page, reference, _ = owned_codex_page
    page.screenshot = lambda **kwargs: b"\x89PNG\r\n\x1a\n" + b"x" * 2_000_000
    before = service.store.path.read_bytes()
    with pytest.raises(PortalDataError) as caught:
        runner.observe_assistance_page(reference)
    assert caught.value.code == "page_observation_limit"
    assert service.store.path.read_bytes() == before


def test_stalled_cdp_read_and_cleanup_have_independent_short_deadlines(
    owned_codex_page, monkeypatch
):
    from career_evidence_graph import application_worker_browser as browser

    service, runner, page, reference, _ = owned_codex_page
    deadline = browser.browser_deadline
    monkeypatch.setattr(browser, "browser_deadline", lambda seconds: deadline(min(seconds, 0.03)))
    page._cdp_test_wire.delays.update(
        {"Runtime.getProperties": 0.4, "Runtime.releaseObject": 0.4, "detach": 0.4}
    )
    before = service.store.path.read_bytes()
    started = time.monotonic()
    with pytest.raises(
        browser.Error, match="^(?:owned_browser_outer_timeout|native_operation_timeout)$"
    ):
        runner.observe_assistance_page(reference)
    assert time.monotonic() - started < 0.8
    assert service.store.path.read_bytes() == before


def test_document_freshness_probe_and_detach_are_bounded(owned_codex_page, monkeypatch):
    from career_evidence_graph import application_worker_browser as browser

    service, runner, page, reference, _ = owned_codex_page
    captured = runner.observe_assistance_page(reference)
    deadline = browser.browser_deadline
    monkeypatch.setattr(browser, "browser_deadline", lambda seconds: deadline(min(seconds, 0.03)))
    page._cdp_test_wire.delays.update({"Page.getFrameTree": 0.4, "detach": 0.4})
    before = service.store.path.read_bytes()
    started = time.monotonic()
    assert runner.assistance_read_permitted(reference, document=captured["document"]) is False
    assert time.monotonic() - started < 0.6
    assert service.store.path.read_bytes() == before


def test_pause_during_final_frame_read_prevents_publication(owned_codex_page):
    service, runner, _, reference, _ = owned_codex_page
    original_session = runner.context.new_cdp_session
    paused_state = []

    def pausing_session(original):
        session = original_session(original)
        original_send = session.send
        frame_reads = 0

        def send(method, arguments=None):
            nonlocal frame_reads
            if method == "Page.getFrameTree":
                frame_reads += 1
                if frame_reads == 2:
                    service.request("pause", {"controller": "synthetic-controller"})
                    paused_state.append(service.store.path.read_bytes())
            return original_send(method, arguments)

        session.send = send
        return session

    runner.context.new_cdp_session = pausing_session
    with pytest.raises(PortalDataError, match="接管范围"):
        runner.observe_assistance_page(reference)
    assert service.store.path.read_bytes() == paused_state[0]
