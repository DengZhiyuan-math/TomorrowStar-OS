"""Real isolated backend lifetimes cannot outlive their saved tool authority."""

import subprocess
import sys
import time
from copy import deepcopy

import pytest
from test_adapter_codex_readonly import request, tool_server
from test_single_application_worker import single_worker as single_worker
from test_worker_codex_assistance import retained_assistance_page as retained_assistance_page
from test_worker_codex_observation import owned_codex_page as owned_codex_page

from career_evidence_graph.application_codex_assist import CodexAdapter, CodexAssistConfig
from career_evidence_graph.worker_process_identity import process_identity


@pytest.mark.skipif(sys.platform != "darwin", reason="kernel process birth is a macOS contract")
@pytest.mark.parametrize("termination", ["parent_eof", "term", "kill", "native_exit_window"])
def test_backend_death_stops_original_assistance_before_serving_queued_tools(
    owned_codex_page, tmp_path, termination
):
    service, runner, _, _, calls = owned_codex_page
    child = "import sys; sys.stdin.buffer.read()"
    if termination == "native_exit_window":
        child = (
            "import signal,sys,time; signal.signal(signal.SIGTERM,signal.SIG_IGN);"
            "sys.stdin.buffer.read();time.sleep(30)"
        )
    backend = subprocess.Popen(
        [sys.executable, "-c", child],
        stdin=subprocess.PIPE,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    adapter = None
    try:
        identity = process_identity(backend.pid)
        assert identity is not None
        # The fixture represents the separate backend that published this scope.
        state = service.store.load()
        state["backend_authority"]["process"] = identity
        state["jobs"][0]["assistance"]["backend_authority"]["process"] = deepcopy(identity)
        service.store.save(state)
        reference = service.assistance_context(state["jobs"][0]["application_id"])["assistance_ref"]
        executable = tool_server(tmp_path, [request()])
        home, runtime = tmp_path / "home", service.store.root / "codex-assist"
        home.mkdir()
        runtime.mkdir()
        adapter = CodexAdapter(
            CodexAssistConfig(executable=executable, runtime=runtime, home=home, stop_timeout=0.1)
        )
        runner.codex_assist = adapter
        runner.pump = lambda: None
        run = runner.start_readonly_assistance(reference, request_id="backend-death")
        assert run.status == "ready"
        if termination == "native_exit_window":
            # Exercise the existing App's 2s TERM / 4s KILL window with a child
            # deliberately stuck in cleanup; authority must be gone at t=0.
            service.begin_backend_close()
            backend.stdin.close()
            runner.tick()
            assert backend.poll() is None
            assert not runner.assistance_read_permitted(reference)
            time.sleep(2)
            backend.terminate()
            runner.tick()
            assert backend.poll() is None
            assert not runner.assistance_read_permitted(reference)
            time.sleep(2)
            backend.kill()
        elif termination == "parent_eof":
            backend.stdin.close()
        elif termination == "term":
            backend.terminate()
        else:
            backend.kill()
        backend.wait(timeout=2)
        started = time.monotonic()
        runner.tick()
        assert time.monotonic() - started < 2
        stopped_state = service.store.load()
        assistance = stopped_state["jobs"][0]["assistance"]
        assert stopped_state["backend_authority"]["status"] == "revoked"
        assert stopped_state["control"] == "paused"
        assert stopped_state["jobs"][0]["status"] == "needs_recheck"
        assert stopped_state["jobs"][0]["reason"] == "backend_authority_lost"
        assert assistance["status"] == "stopped"
        assert assistance["active_writer"] == "codex"
        assert assistance["stop"]["tools_revoked"] is True
        assert assistance["stop"]["local_tools_drained"] is True
        assert assistance["stop"]["process_stopped"] is True
        assert calls == []
    finally:
        if adapter is not None:
            adapter.close()
        if backend.poll() is None:
            backend.kill()
            backend.wait(timeout=2)
        if backend.stdin and not backend.stdin.closed:
            backend.stdin.close()
