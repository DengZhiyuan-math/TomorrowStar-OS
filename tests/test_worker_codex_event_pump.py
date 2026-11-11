"""Worker control ticks and the passive original-page tool share one thread."""

import json
import threading
import time
from types import SimpleNamespace

import pytest
from test_adapter_codex_readonly import request, rows, tool_server
from test_application_codex_assist import server
from test_single_application_worker import single_worker as single_worker
from test_worker_codex_assistance import retained_assistance_page as retained_assistance_page
from test_worker_codex_observation import owned_codex_page as owned_codex_page

from career_evidence_graph.application_codex_assist import CodexAdapter, CodexAssistConfig


def test_tick_services_readonly_adapter_without_holding_the_business_lock(owned_codex_page):
    service, runner, _, _, calls = owned_codex_page
    polled = []

    def progress():
        finished = threading.Event()

        def pause():
            service.request("pause", {"controller": "synthetic-controller"})
            finished.set()

        thread = threading.Thread(target=pause)
        thread.start()
        try:
            assert finished.wait(1), "Adapter polling must not retain the application write lock"
        finally:
            thread.join(timeout=1)
        polled.append("polled")

    runner.codex_assist = SimpleNamespace(service_readonly=progress)
    runner.tick()
    assert polled == ["polled"]
    assert service.store.load()["control"] == "paused"
    assert calls == []


def test_readonly_wait_pump_preserves_commands_after_scope_is_revoked(
    owned_codex_page, monkeypatch
):
    service, runner, _, reference, _ = owned_codex_page
    state = service.store.load()
    state["jobs"][0].pop("assistance")
    state["control"] = "paused"
    command = {"action": "review", "id": reference["binding"]["application_id"]}
    state["commands"] = [command]
    service.store.save(state)
    browser_events, writes = [], []
    monkeypatch.setattr(runner, "pump", lambda: browser_events.append("browser-pumped"))
    monkeypatch.setattr(runner, "_command", lambda *args: writes.append("must-not-run"))

    assert runner.pump_codex_events(reference) is False
    assert service.store.load()["commands"] == [command]
    assert service.store.load()["control"] == "paused"
    assert browser_events == ["browser-pumped"]
    assert writes == []


@pytest.mark.parametrize("after_capture", [None, "same_url_navigation", "pause"])
def test_passive_peer_reads_the_retained_page_through_worker_ticks(
    owned_codex_page, tmp_path, monkeypatch, after_capture
):
    service, runner, page, reference, calls = owned_codex_page
    executable = tool_server(tmp_path, [request()])
    home, runtime = tmp_path / "home", service.store.root / "codex-assist"
    home.mkdir()
    runtime.mkdir()
    adapter = CodexAdapter(CodexAssistConfig(executable=executable, runtime=runtime, home=home))
    runner.codex_assist = adapter
    pumped = []

    def browser_pump():
        pumped.append("browser-pumped")
        if any(call[0] == "screenshot" for call in calls):
            if after_capture == "same_url_navigation":
                page.loader = "new-document-without-saved-state-change"
            elif after_capture == "pause":
                service.request("pause", {"controller": "synthetic-controller"})

    monkeypatch.setattr(runner, "pump", browser_pump)
    try:
        run = runner.start_readonly_assistance(reference, request_id="start-observer")
        assert run.page_write_allowed is False and run.model_turn_allowed is False
        deadline = time.monotonic() + 3
        response = None
        while time.monotonic() < deadline:
            runner.tick()
            response = next((r for r in rows(executable) if r.get("id") == "read-1"), None)
            if response or adapter.progress(run.run_id).stop_status == "stopped":
                break
            time.sleep(0.005)
        if after_capture is None:
            assert response and response["result"]["success"] is True
            content = response["result"]["contentItems"]
            text = json.loads(content[0]["text"])
            assert text["binding"]["page_id"] == "retained-page"
            assert content[1]["imageUrl"].startswith("data:image/png;base64,iVBOR")
        else:
            assert response is None
            stopped = adapter.progress(run.run_id)
            assert stopped.status == "stopped"
            assert stopped.tools_revoked and stopped.local_tools_drained and stopped.process_stopped
            assert stopped.error_code == "read_scope_changed"
        assert calls.count(("screenshot", threading.get_ident())) == 1
        assert pumped
        assert all(r.get("method") != "turn/start" for r in rows(executable))
        assert service.store.load()["jobs"][0]["assistance"]["page_writes_enabled"] is False
    finally:
        adapter.close()


def test_silent_startup_still_processes_user_pause(owned_codex_page, tmp_path, monkeypatch):
    service, runner, _, reference, calls = owned_codex_page
    executable = server(tmp_path, "timeout")
    home, runtime = tmp_path / "home", service.store.root / "codex-assist"
    home.mkdir()
    runtime.mkdir()
    adapter = CodexAdapter(
        CodexAssistConfig(
            executable=executable, runtime=runtime, home=home, request_timeout=1, stop_timeout=0.1
        )
    )
    runner.codex_assist = adapter
    pumped = []

    def browser_pump():
        pumped.append("browser-pumped")
        if any(row.get("method") == "initialize" for row in rows(executable)):
            service.request("pause", {"controller": "synthetic-controller"})

    monkeypatch.setattr(runner, "pump", browser_pump)
    try:
        run = runner.start_readonly_assistance(reference, request_id="silent-startup")
        assert run.status == "unknown"
        assert run.error_code == "read_scope_changed"
        assert service.store.load()["control"] == "paused"
        assert pumped
        assert not any(call[0] == "screenshot" for call in calls)
        assert not any(
            row.get("method") in {"thread/start", "turn/start"} for row in rows(executable)
        )
    finally:
        adapter.close()
