"""JSON Page context reuses original-page checks without producing screenshots."""

import json
import threading

import pytest
from test_single_application_worker import single_worker as single_worker
from test_worker_codex_assistance import retained_assistance_page as retained_assistance_page
from test_worker_codex_observation import owned_codex_page as owned_codex_page

from career_evidence_graph.career_portal_data import PortalDataError


def test_json_context_retains_current_page_and_user_value_without_screenshot(owned_codex_page):
    service, runner, page, reference, calls = owned_codex_page
    page.field_value = "human-edited@example.invalid"
    before = service.store.path.read_bytes()

    result = runner.observe_assistance_context(reference)

    assert result["binding"] == reference["binding"]
    assert result["document"] == {
        "frame_id": "original-frame",
        "loader_id": "original-loader",
        "url": page.url,
    }
    assert result["observed_at"] == result["at"]
    assert result["data"]["fields"][0]["value"] == "human-edited@example.invalid"
    assert result["data"]["fields"][0]["locator_hint"]["id"] == "email"
    assert result["data"]["validation_errors"] == []
    assert result["page_writes_enabled"] is False
    assert "screenshot" not in result and "image_url" not in result
    assert "screenshot" not in [name for name, _ in calls]
    assert json.loads(json.dumps(result)) == result
    assert service.store.path.read_bytes() == before
    assert page.field_value == "human-edited@example.invalid"
    assert {ident for _, ident in calls} == {threading.get_ident()}


def test_json_context_still_works_when_screenshot_capture_is_unavailable(owned_codex_page):
    _, runner, page, reference, _ = owned_codex_page

    def unavailable(**kwargs):
        raise AssertionError("JSON handoff must not request a screenshot")

    page.screenshot = unavailable
    assert runner.observe_assistance_context(reference)["data"]["title"] == "Original page"
    with pytest.raises(AssertionError, match="screenshot"):
        runner.observe_assistance_page(reference)


def test_json_read_releases_business_lock_and_discards_a_pause(owned_codex_page):
    service, runner, _, reference, _ = owned_codex_page
    original = runner.context.new_cdp_session
    paused = threading.Event()

    def session_for(page):
        session = original(page)
        send = session.send
        called = False

        def checked_send(method, arguments=None):
            nonlocal called
            if (
                method == "Runtime.evaluate"
                and arguments.get("expression") != "this"
                and not called
            ):
                called = True
                worker = threading.Thread(
                    target=lambda: (
                        service.request("pause", {"controller": "synthetic-controller"}),
                        paused.set(),
                    )
                )
                worker.start()
                assert paused.wait(1), "DOM reads must release the business lock"
                worker.join(timeout=1)
            return send(method, arguments)

        session.send = checked_send
        return session

    runner.context.new_cdp_session = session_for
    with pytest.raises(PortalDataError, match="接管范围"):
        runner.observe_assistance_context(reference)
    assert service.store.load()["control"] == "paused"
    assert "owned_page_inspection" not in service.store.load()["jobs"][0]


@pytest.mark.parametrize("changed", ["document", "field", "frame"])
def test_json_context_discards_mid_read_page_changes(owned_codex_page, changed):
    service, runner, page, reference, _ = owned_codex_page
    original = runner.context.new_cdp_session

    def session_for(original_page):
        session = original(original_page)
        send = session.send
        reads = 0

        def checked_send(method, arguments=None):
            nonlocal reads
            if method == "Runtime.evaluate" and arguments.get("expression") != "this":
                reads += 1
                if reads == 2:
                    if changed == "document":
                        page.token = "new-token"
                    elif changed == "field":
                        page.field_value = "new-human-edit@example.invalid"
                    else:
                        page.loader = "new-loader"
            return send(method, arguments)

        session.send = checked_send
        return session

    runner.context.new_cdp_session = session_for
    before = service.store.path.read_bytes()
    with pytest.raises(PortalDataError):
        runner.observe_assistance_context(reference)
    assert service.store.path.read_bytes() == before


def test_json_context_rejects_a_foreign_thread_before_page_io(owned_codex_page):
    from concurrent.futures import ThreadPoolExecutor

    _, runner, _, reference, calls = owned_codex_page
    with ThreadPoolExecutor(max_workers=1) as pool:
        result = pool.submit(runner.observe_assistance_context, reference)
        with pytest.raises(PortalDataError, match="线程"):
            result.result(timeout=2)
    assert calls == []


@pytest.mark.parametrize("changed", ["pause", "document", "material", "page"])
def test_json_context_rejects_changed_scope_before_dom_read(owned_codex_page, changed):
    service, runner, page, reference, calls = owned_codex_page
    state = service.store.load()
    if changed == "pause":
        state["control"] = "paused"
    elif changed == "document":
        state["jobs"][0]["form_state"]["binding"]["document_token"] = "other-token"
    elif changed == "material":
        state["jobs"][0]["file_sha256"] = "c" * 64
    else:
        page.url = "https://example.invalid/other-page"
    service.store.save(state)
    before = service.store.path.read_bytes()
    with pytest.raises(PortalDataError):
        runner.observe_assistance_context(reference)
    assert calls == []
    assert service.store.path.read_bytes() == before


def test_json_assistance_passes_saved_progress_and_dom_context_to_the_adapter(owned_codex_page):
    from types import SimpleNamespace

    service, runner, _, reference, calls = owned_codex_page
    delivered = []

    class Adapter:
        def start(self, ref, *, request_id, context_handler, pump):
            assert request_id == "json-assistance"
            assert ref == reference
            delivered.append(context_handler(ref))
            return SimpleNamespace(run_id="json-run")

        def progress(self, run_id):
            assert run_id == "json-run"
            return SimpleNamespace(status="ready", tools_revoked=False)

    runner.codex_assist = Adapter()
    before = service.store.path.read_bytes()
    result = runner.start_json_assistance(reference, request_id="json-assistance")
    assert result.run_id == "json-run"
    assert delivered[0]["schema_version"] == 1
    assert delivered[0]["assistance_ref"] == reference
    assert delivered[0]["page_context"]["data"]["fields"][0]["value"] == "synthetic@example.invalid"
    assert "screenshot" not in [name for name, _ in calls]
    assert runner._assistance_run == (reference, "json-run")
    assert service.store.path.read_bytes() == before


def test_json_context_reaches_native_transport_as_one_json_text_without_image(
    owned_codex_page, tmp_path
):
    import time

    from test_adapter_codex_readonly import request, rows, tool_server
    from test_application_codex_assist import config

    from career_evidence_graph.application_codex_assist import CodexAdapter

    _, runner, _, reference, calls = owned_codex_page
    executable = tool_server(tmp_path, [request(tool="read_application_context")])
    adapter = CodexAdapter(config(tmp_path, executable))
    runner.codex_assist = adapter
    runner.pump = lambda: None
    try:
        runner.start_json_assistance(reference, request_id="json-wire")
        deadline = time.monotonic() + 3
        reply = None
        while time.monotonic() < deadline:
            adapter.service_readonly()
            reply = next((row for row in rows(executable) if row.get("id") == "read-1"), None)
            if reply:
                break
            time.sleep(0.005)
        assert reply is not None
        assert reply["result"]["success"] is True
        content = reply["result"]["contentItems"]
        assert [part["type"] for part in content] == ["inputText"]
        delivery = json.loads(content[0]["text"])
        assert delivery["schema_version"] == 1
        assert delivery["assistance_ref"] == {
            key: value for key, value in reference.items() if key != "backend_authority"
        }
        assert delivery["page_context"]["data"]["fields"][0]["locator_hint"]["id"] == "email"
        assert "screenshot" not in [name for name, _ in calls]
        assert not any(row.get("method") == "turn/start" for row in rows(executable))
    finally:
        adapter.close()
