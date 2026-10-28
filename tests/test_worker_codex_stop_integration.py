"""The original Worker revokes and records a dedicated assistance stop."""

import time

from test_adapter_codex_readonly import request, rows, tool_server
from test_single_application_worker import single_worker as single_worker
from test_worker_codex_assistance import retained_assistance_page as retained_assistance_page
from test_worker_codex_backend_recovery import stopped_original_owner as stopped_original_owner
from test_worker_codex_observation import owned_codex_page as owned_codex_page

from career_evidence_graph.application_codex_assist import CodexAdapter, CodexAssistConfig
from career_evidence_graph.application_worker_browser import ApplicationRunner


def test_pause_drains_assistance_without_serving_queued_page_requests(owned_codex_page, tmp_path):
    service, runner, _, reference, calls = owned_codex_page
    executable = tool_server(tmp_path, [request()])
    home, runtime = tmp_path / "home", service.store.root / "codex-assist"
    home.mkdir()
    runtime.mkdir()
    adapter = CodexAdapter(CodexAssistConfig(executable=executable, runtime=runtime, home=home))
    runner.codex_assist = adapter
    runner.pump = lambda: None
    try:
        run = runner.start_readonly_assistance(reference, request_id="pause-before-read")
        service.request("pause", {"controller": "synthetic-controller"})
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            runner.tick()
            assistance = service.store.load()["jobs"][0]["assistance"]
            if assistance.get("stop", {}).get("stop_status") == "stopped":
                break
        assert assistance["status"] == "stopped"
        assert assistance["active_writer"] == "codex"
        assert assistance["stop"]["tools_revoked"] is True
        assert assistance["stop"]["local_tools_drained"] is True
        assert assistance["stop"]["process_stopped"] is True
        assert adapter.progress(run.run_id).page_write_allowed is False
        assert calls == []
        assert not any(row.get("result", {}).get("contentItems") for row in rows(executable))
    finally:
        adapter.close()


def test_checkpoint_failure_still_revokes_the_live_assistance_process(
    owned_codex_page, tmp_path, monkeypatch
):
    service, runner, _, reference, calls = owned_codex_page
    executable = tool_server(tmp_path, [request()])
    home, runtime = tmp_path / "home", service.store.root / "codex-assist"
    home.mkdir()
    runtime.mkdir()
    adapter = CodexAdapter(CodexAssistConfig(executable=executable, runtime=runtime, home=home))
    runner.codex_assist = adapter
    runner.pump = lambda: None
    try:
        run = runner.start_readonly_assistance(reference, request_id="storage-failure-stop")
        service.request("pause", {"controller": "synthetic-controller"})

        def fail(_state):
            raise OSError("synthetic checkpoint unavailable")

        monkeypatch.setattr(runner, "persist", fail)
        runner.tick()
        stopped = adapter.progress(run.run_id)
        assert stopped.tools_revoked is True
        assert stopped.local_tools_drained is True
        assert stopped.process_stopped is True
        assert runner.storage_stopped is True
        assert service.store.stop_reason()
        assert calls == []
        assert service.store.load()["jobs"][0]["assistance"]["status"] == "stopping"
    finally:
        adapter.close()


def test_pause_inside_capture_reports_draining_until_the_callback_returns(
    owned_codex_page, tmp_path
):
    service, runner, page, reference, _ = owned_codex_page
    executable = tool_server(tmp_path, [request()])
    home, runtime = tmp_path / "home", service.store.root / "codex-assist"
    home.mkdir()
    runtime.mkdir()
    adapter = CodexAdapter(CodexAssistConfig(executable=executable, runtime=runtime, home=home))
    runner.codex_assist = adapter
    runner.pump = lambda: None
    draining = []

    def pause_during_capture():
        service.request("pause", {"controller": "synthetic-controller"})
        assert runner.pump_codex_events(reference) is False
        stop = service.store.load()["jobs"][0]["assistance"]["stop"]
        draining.append((stop["stop_status"], stop["local_tools_drained"], stop["process_stopped"]))

    page.screenshot_hook = pause_during_capture
    try:
        runner.start_readonly_assistance(reference, request_id="pause-in-capture")
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            runner.tick()
            assistance = service.store.load()["jobs"][0]["assistance"]
            if assistance.get("stop", {}).get("stop_status") == "stopped":
                break
        assert draining == [("stopping", False, False)]
        assert assistance["stop"]["stop_status"] == "stopped"
        assert assistance["stop"]["local_tools_drained"] is True
        assert not any(row.get("result", {}).get("contentItems") for row in rows(executable))
    finally:
        adapter.close()


def test_original_owner_confirms_no_start_when_cancelled_before_claim(retained_assistance_page):
    service, identifier = retained_assistance_page
    service.request(
        "request-assistance",
        {
            "application_id": identifier,
            "binding": service.assistance_context(identifier)["binding"],
            "request_id": "cancel-before-claim",
        },
    )
    service.request("pause", {"controller": "synthetic-controller"})
    runner = ApplicationRunner(service.store, None)
    runner.tick(control_only=True)
    assistance = service.store.load()["jobs"][0]["assistance"]
    assert assistance["status"] == "stopped"
    assert assistance["claim_request_id"] is None
    assert assistance["active_writer"] == "none"
    assert assistance["stop"]["local_tools_drained"] is True
    assert assistance["stop"]["process_stopped"] is True
    assert assistance["stop"]["native_turn_status"] == "idle"


def test_native_completion_stops_the_scope_without_executing_queued_tools(
    owned_codex_page, tmp_path
):
    service, runner, _, reference, calls = owned_codex_page
    events = [
        {
            "method": method,
            "params": {
                "threadId": "thread-synthetic",
                "turn": {"id": "passive-synthetic-turn", "status": status},
            },
        }
        for method, status in [("turn/started", "inProgress"), ("turn/completed", "completed")]
    ]
    executable = tool_server(tmp_path, [*events, request()])
    home, runtime = tmp_path / "home", service.store.root / "codex-assist"
    home.mkdir()
    runtime.mkdir()
    adapter = CodexAdapter(CodexAssistConfig(executable=executable, runtime=runtime, home=home))
    runner.codex_assist = adapter
    runner.pump = lambda: None
    try:
        runner.start_readonly_assistance(reference, request_id="native-completed")
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            runner.tick()
            assistance = service.store.load()["jobs"][0]["assistance"]
            if assistance.get("stop", {}).get("stop_status") == "stopped":
                break
        assert assistance["status"] == "stopped"
        assert assistance["stop"]["native_turn_status"] == "completed"
        assert assistance["active_writer"] == "codex"
        assert calls == []
    finally:
        adapter.close()


def test_recovery_rejects_a_new_resume_serial_even_with_the_same_controller(stopped_original_owner):
    service, runner, _, reference, calls = stopped_original_owner
    service.request("resume", {"controller": "synthetic-controller"})
    current = service.store.load()
    assert current["resume_serial"] > reference["binding"]["resume_serial"]
    receipt = service.suspend_backend(
        pipeline_id="synthetic-pipeline",
        controller=current["controller"],
        batch_id=current["batch_id"],
        application_id=reference["binding"]["application_id"],
    )
    service.recover_backend(receipt["request_id"], "synthetic-pipeline")
    current = service.store.load()
    runner.commands(current)
    runner.persist(current)
    runner.service_backend_recovery()
    after = service.store.load()
    assert not after["backend_recovery"].get("page_verified")
    assert after["backend_recovery"]["status"] == "needs_recheck"
    assert after["control"] == "paused"
    assert calls == []
