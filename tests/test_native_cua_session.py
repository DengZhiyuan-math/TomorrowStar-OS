"""Synthetic native UDS peers exercise the original-host session transport."""

import json
import os
import socket
import socketserver
import tempfile
import threading
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace

import pytest

from career_evidence_graph.career_portal_data import PortalDataError
from career_evidence_graph.cua_driver import NativeCuaSessionClient


@pytest.fixture(autouse=True)
def synthetic_review_pin(monkeypatch):
    monkeypatch.setattr("career_evidence_graph.cua_driver._NATIVE_HANDOFF_DRIVER_SHA256", "1" * 64)


@contextmanager
def native_service(
    tmp_path,
    *,
    fail_call=False,
    delay_call=0,
    metadata_change=None,
    catalog_change=None,
    fail_yield_once=False,
    control_delay=0,
    yielded=True,
):
    requests = []
    state = {"return_ready": False, "active_calls": 1}
    options = {
        "public_session": "worker-test",
        "mode": "bounded",
        "ttl_seconds": 60,
        "idle_ttl_seconds": 30,
        "capability_manifest_path": str(tmp_path / "scope.json"),
        "bounded_manifest_path": None,
    }
    temporary = tempfile.TemporaryDirectory(prefix="ts-native-", dir="/private/tmp")
    path = Path(temporary.name) / "native.sock"
    stopped = threading.Event()

    class Handler(socketserver.StreamRequestHandler):
        def handle(self):
            for line in self.rfile:
                message = json.loads(line)
                requests.append(message)
                method = message["method"]
                if method == "metadata":
                    result = {
                        "driver_version": "0.35.4",
                        "contract_version": "0.8.0",
                        "tools_list_schema_version": "1",
                        "capability_version": "1",
                        "mcp_protocol_version": "2025-06-18",
                        "pid": os.getpid(),
                        "embedded": True,
                        "trusted_session_handoff_protocol": "cua-trusted-handoff/v1",
                        "trusted_session_handoff_supported": True,
                        "max_session_ttl_seconds": 86400,
                        "max_idle_ttl_seconds": 3600,
                    }
                    result.update(metadata_change or {})
                elif method == "list":
                    result = {
                        "tools": [
                            {"name": name}
                            for name in (
                                "browser_prepare",
                                "get_browser_state",
                                "browser_click",
                                "browser_type",
                                "browser_set_input_files",
                                "list_windows",
                                "end_session",
                                "check_permissions",
                            )
                        ],
                        "schema_version": "1",
                        "capability_version": "1",
                        "enforcement_adapters": [],
                        "tool_observation_owner": "daemon",
                    }
                    result.update(catalog_change or {})
                elif method in {"trusted_session_begin", "trusted_session_resume"}:
                    result = {
                        "bound": True,
                        "connection_bound": True,
                        "resume_credential": "private-resume-credential",
                    }
                elif method == "trusted_session_call":
                    if fail_call:
                        return
                    if delay_call:
                        stopped.wait(delay_call)
                    result = {"structuredContent": {"status": "ok", "value": "native-result"}}
                elif method == "trusted_session_end":
                    result = {"closed": True}
                elif method == "trusted_session_yield":
                    if (
                        fail_yield_once
                        and sum(r["method"] == "trusted_session_yield" for r in requests) == 1
                    ):
                        return
                    result = {
                        "handoff_id": "handoff-test",
                        "host_return_credential": "private-return",
                        "generation": 1,
                        "local_tools_drained": True,
                        "yielded": yielded,
                    }
                elif method in {
                    "trusted_session_handoff_status",
                    "trusted_session_handoff_revoke",
                    "trusted_session_handoff_admit",
                }:
                    if control_delay:
                        stopped.wait(control_delay)
                    result = {
                        "handoff_id": "handoff-test",
                        "generation": 1,
                        "phase": "borrowed",
                        "revoked": method.endswith("revoke"),
                        "active_calls": state["active_calls"],
                        "local_tools_drained": state["active_calls"] == 0,
                        "return_ready": state["return_ready"],
                        "calls": state.get("calls", []),
                    }
                else:
                    raise AssertionError(message)
                try:
                    self.wfile.write((json.dumps({"ok": True, "result": result}) + "\n").encode())
                    self.wfile.flush()
                except (BrokenPipeError, ConnectionResetError):
                    return

    class Server(socketserver.ThreadingUnixStreamServer):
        daemon_threads = True

    server = Server(str(path), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield (
            str(path),
            options,
            SimpleNamespace(pid=os.getpid(), poll=lambda: None),
            requests,
            state,
        )
    finally:
        stopped.set()
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
        temporary.cleanup()


def test_native_host_calls_existing_tool_without_second_mcp_proxy(tmp_path):
    with native_service(tmp_path) as (path, options, process, requests, _):
        client = NativeCuaSessionClient(path, process, options, driver_sha256="1" * 64, timeout=1)
        try:
            assert client.call(
                "get_browser_state", {"target_id": "original", "tab_id": "original-tab"}
            ) == {"status": "ok", "value": "native-result"}
            assert client.session == "worker-test"
            assert client.process is process
            calls = [r for r in requests if r["method"] == "trusted_session_call"]
            assert calls == [
                {
                    "method": "trusted_session_call",
                    "name": "get_browser_state",
                    "args": {
                        "target_id": "original",
                        "tab_id": "original-tab",
                        "session": "worker-test",
                    },
                }
            ]
            assert not any(
                r.get("method") in {"initialize", "tools/call", "session_begin"} for r in requests
            )
        finally:
            client.close()
        assert sum(r["method"] == "trusted_session_end" for r in requests) == 1


def test_lost_native_reply_is_unknown_and_never_replayed(tmp_path):
    with native_service(tmp_path, fail_call=True) as (path, options, process, requests, _):
        client = NativeCuaSessionClient(path, process, options, driver_sha256="1" * 64, timeout=0.2)
        try:
            with pytest.raises(PortalDataError, match="未知"):
                client.call(
                    "browser_click", {"target_id": "original", "tab_id": "tab", "ref": "button"}
                )
            with pytest.raises(PortalDataError, match="未知"):
                client.call(
                    "browser_click", {"target_id": "original", "tab_id": "tab", "ref": "button"}
                )
            assert client.failed is True
            assert sum(r["method"] == "trusted_session_call" for r in requests) == 1
        finally:
            client.close()
        assert not any(r["method"] == "trusted_session_resume" for r in requests)


def test_native_wait_pumps_original_owner_thread(tmp_path):
    with native_service(tmp_path, delay_call=0.12) as (path, options, process, _, _):
        client = NativeCuaSessionClient(path, process, options, driver_sha256="1" * 64, timeout=1)
        calls = []
        try:
            client.call(
                "get_browser_state",
                {"target_id": "original", "tab_id": "tab"},
                pump=lambda: calls.append(threading.get_ident()),
            )
            assert calls and set(calls) == {threading.get_ident()}
        finally:
            client.close()


def ready_record(path):
    return {
        "protocol": "cua-trusted-handoff/v1",
        "request_id": "borrow-one",
        "socket_path": path,
        "application_ref_digest": "a" * 64,
        "status": "pending",
        "connection_id": "connection-one",
        "peer_pid": 20,
        "proxy_pid": 20,
    }


def test_native_handoff_retains_host_credential_and_gates_resume_on_actual_drain(
    tmp_path, monkeypatch
):
    import career_evidence_graph.cua_driver as module

    monkeypatch.setattr(
        module, "verify_native_handoff_recipient", lambda *args, **kwargs: {"pid": 20}
    )
    with native_service(tmp_path) as (path, options, process, requests, state):
        client = NativeCuaSessionClient(path, process, options, driver_sha256="1" * 64, timeout=1)
        try:
            grant = client.yield_to(
                ready_record(path),
                request_id="borrow-one",
                scope={
                    "target_id": "original",
                    "tab_id": "tab",
                    "expected_document": {
                        "frame_id": "frame",
                        "loader_id": "loader",
                        "url": "https://example.invalid",
                    },
                },
                application_ref_digest="a" * 64,
                appserver_identity={},
                driver_executable="/native/driver",
            )
            assert "host_return_credential" not in grant
            assert "private-return" not in json.dumps(grant)
            assert client.handoff_active is True
            with pytest.raises(PortalDataError) as error:
                client.call("browser_click", {"target_id": "original", "tab_id": "tab"})
            assert error.value.code == "cua_session_yielded"
            yielded = next(r for r in requests if r["method"] == "trusted_session_yield")
            assert yielded["args"]["expected_peer_pid"] == 20
            assert yielded["args"]["application_ref_digest"] == "a" * 64
            status = client.handoff_status()
            assert status["active_calls"] == 1 and status["local_tools_drained"] is False
            with pytest.raises(PortalDataError) as error:
                client.resume_after_handoff()
            assert error.value.code == "cua_handoff_pending"
            assert not any(r["method"] == "trusted_session_resume" for r in requests)
            revoked = client.revoke_handoff()
            assert revoked["revoked"] is True and revoked["local_tools_drained"] is False
            state.update(active_calls=0, return_ready=True)
            client.resume_after_handoff()
            assert client.handoff_active is False
            assert (
                client.call("get_browser_state", {"target_id": "original", "tab_id": "tab"})[
                    "status"
                ]
                == "ok"
            )
            resumed = next(r for r in requests if r["method"] == "trusted_session_resume")
            assert resumed["args"] == {"resume_credential": "private-return"}
        finally:
            client.close()


def test_native_policy_uses_fixed_tools_and_the_distinct_reviewed_candidate(monkeypatch):
    import career_evidence_graph.cua_driver as module

    policy = {
        "protocol": module.NATIVE_HANDOFF_PROTOCOL,
        "driver_sha256": "1" * 64,
        "tools": list(module.NATIVE_HANDOFF_TOOLS),
        "type_mode": "insert_text",
    }
    validated = module.validate_native_assistance_policy(policy)
    assert validated == policy and validated is not policy
    validated["tools"].append("browser_prepare")
    assert "browser_prepare" not in policy["tools"]
    assert module.validate_native_assistance_policy(None) is None
    monkeypatch.setattr(module, "_NATIVE_HANDOFF_DRIVER_SHA256", None)
    with pytest.raises(ValueError):
        module.validate_native_assistance_policy(policy)


@pytest.mark.parametrize(
    "change",
    [
        {"trusted_session_handoff_supported": False},
        {"trusted_session_handoff_protocol": "legacy"},
        {"embedded": False},
        {"pid": -1},
        {"contract_version": "other"},
        {"max_session_ttl_seconds": 20},
    ],
)
def test_native_capability_probe_is_not_a_nominal_version_grant(tmp_path, change):
    with native_service(tmp_path, metadata_change=change) as (path, options, process, requests, _):
        with pytest.raises(PortalDataError):
            NativeCuaSessionClient(path, process, options, driver_sha256="1" * 64, timeout=1)
        assert not any(r["method"] == "trusted_session_begin" for r in requests)


def test_native_session_requires_the_actual_text_input_tool_before_binding(tmp_path):
    catalog = {
        "tools": [
            {"name": name}
            for name in (
                "browser_prepare",
                "get_browser_state",
                "browser_click",
                "end_session",
                "check_permissions",
            )
        ]
    }
    with native_service(tmp_path, catalog_change=catalog) as (path, options, process, requests, _):
        with pytest.raises(PortalDataError) as error:
            NativeCuaSessionClient(path, process, options, driver_sha256="1" * 64, timeout=1)
        assert error.value.code == "cua_native_session_unavailable"
        assert not any(r["method"] == "trusted_session_begin" for r in requests)


def test_lost_yield_reply_is_reconciled_only_by_the_exact_host_request(tmp_path, monkeypatch):
    import career_evidence_graph.cua_driver as module

    monkeypatch.setattr(
        module, "verify_native_handoff_recipient", lambda *args, **kwargs: {"pid": 20}
    )
    with native_service(tmp_path, fail_yield_once=True) as (path, options, process, requests, _):
        client = NativeCuaSessionClient(path, process, options, driver_sha256="1" * 64, timeout=1)
        try:
            with pytest.raises(PortalDataError):
                client.yield_to(
                    ready_record(path),
                    request_id="borrow-one",
                    scope={
                        "target_id": "original",
                        "tab_id": "tab",
                        "expected_document": {
                            "frame_id": "frame",
                            "loader_id": "loader",
                            "url": "https://example.invalid",
                        },
                    },
                    application_ref_digest="a" * 64,
                    appserver_identity={},
                    driver_executable="/native/driver",
                )
            assert client.failed and client.handoff_active
            assert not client.handoff_transition_inflight
            assert client.handoff_status()["local_tools_drained"] is False
            assert client.failed  # Metadata cannot restore permission or replay the action.
            assert sum(r["method"] == "trusted_session_yield" for r in requests) == 1
            recovered = client.reconcile_handoff()
            assert recovered["handoff_id"] == "handoff-test" and not client.failed
            attempts = [r for r in requests if r["method"] == "trusted_session_yield"]
            assert len(attempts) == 2 and attempts[0] == attempts[1]
            assert sum(r["method"] == "trusted_session_begin" for r in requests) == 1
        finally:
            client.close()


def test_host_admission_is_native_control_metadata_not_an_action_reimplementation(
    tmp_path, monkeypatch
):
    import career_evidence_graph.cua_driver as module

    monkeypatch.setattr(
        module, "verify_native_handoff_recipient", lambda *args, **kwargs: {"pid": 20}
    )
    with native_service(tmp_path) as (path, options, process, requests, _):
        client = NativeCuaSessionClient(path, process, options, driver_sha256="1" * 64, timeout=1)
        try:
            client.yield_to(
                ready_record(path),
                request_id="borrow-one",
                scope={
                    "target_id": "original",
                    "tab_id": "tab",
                    "expected_document": {
                        "frame_id": "frame",
                        "loader_id": "loader",
                        "url": "https://example.invalid",
                    },
                },
                application_ref_digest="a" * 64,
                appserver_identity={},
                driver_executable="/native/driver",
            )
            client.admit_call("native-call", "b" * 64, "allow", timeout=0.5)
            admitted = next(r for r in requests if r["method"] == "trusted_session_handoff_admit")
            assert admitted["args"] == {
                "handoff_id": "handoff-test",
                "call_id": "native-call",
                "arguments_digest": "b" * 64,
                "decision": "allow",
            }
            assert not any(r.get("name") == "browser_click" for r in requests)
        finally:
            client.close()


def test_native_revoke_uses_its_own_short_control_budget(tmp_path, monkeypatch):
    import time

    import career_evidence_graph.cua_driver as module

    monkeypatch.setattr(
        module, "verify_native_handoff_recipient", lambda *args, **kwargs: {"pid": 20}
    )
    with native_service(tmp_path, control_delay=0.3) as (path, options, process, requests, _):
        client = NativeCuaSessionClient(path, process, options, driver_sha256="1" * 64, timeout=1)
        try:
            client.yield_to(
                ready_record(path),
                request_id="borrow-one",
                scope={
                    "target_id": "original",
                    "tab_id": "tab",
                    "expected_document": {
                        "frame_id": "frame",
                        "loader_id": "loader",
                        "url": "https://example.invalid",
                    },
                },
                application_ref_digest="a" * 64,
                appserver_identity={},
                driver_executable="/native/driver",
            )
            started = time.monotonic()
            with pytest.raises(PortalDataError) as error:
                client.revoke_handoff(timeout=0.03)
            assert time.monotonic() - started < 0.2
            assert error.value.code == "cua_handoff_unknown"
            assert sum(r["method"] == "trusted_session_handoff_revoke" for r in requests) == 1
        finally:
            client.close()


def native_mutation_row():
    return {
        "call_id": "native-click",
        "tool": "browser_click",
        "arguments_digest": "b" * 64,
        "status": "awaiting_host",
        "generation": 1,
        "sequence": 1,
        "mutation": True,
        "semantic_verified": False,
        "scope": {
            "target_id": "original",
            "tab_id": "tab",
            "expected_document": {
                "frame_id": "frame",
                "loader_id": "loader",
                "url": "https://example.invalid",
            },
        },
        "native_ref": "ref-one",
        "field_hint": {"role": "combobox", "name": "Country"},
    }


def test_native_status_preserves_attested_field_identity_for_host_admission(tmp_path, monkeypatch):
    import career_evidence_graph.cua_driver as module

    monkeypatch.setattr(
        module, "verify_native_handoff_recipient", lambda *args, **kwargs: {"pid": 20}
    )
    with native_service(tmp_path) as (path, options, process, _, state):
        client = NativeCuaSessionClient(path, process, options, driver_sha256="1" * 64, timeout=1)
        try:
            client.yield_to(
                ready_record(path),
                request_id="borrow-one",
                scope={
                    "target_id": "original",
                    "tab_id": "tab",
                    "expected_document": {
                        "frame_id": "frame",
                        "loader_id": "loader",
                        "url": "https://example.invalid",
                    },
                },
                application_ref_digest="a" * 64,
                appserver_identity={},
                driver_executable="/native/driver",
            )
            state["calls"] = [native_mutation_row()]
            assert client.handoff_status()["calls"] == [native_mutation_row()]
        finally:
            client.close()


@pytest.mark.parametrize(
    "change",
    ["missing_ref", "control_ref", "long_ref", "hint_extra", "hint_type", "long_name", "raw_text"],
)
def test_native_status_rejects_unattested_or_unbounded_mutation_metadata(
    tmp_path, monkeypatch, change
):
    import career_evidence_graph.cua_driver as module

    monkeypatch.setattr(
        module, "verify_native_handoff_recipient", lambda *args, **kwargs: {"pid": 20}
    )
    with native_service(tmp_path) as (path, options, process, _, state):
        client = NativeCuaSessionClient(path, process, options, driver_sha256="1" * 64, timeout=1)
        try:
            client.yield_to(
                ready_record(path),
                request_id="borrow-one",
                scope={
                    "target_id": "original",
                    "tab_id": "tab",
                    "expected_document": {
                        "frame_id": "frame",
                        "loader_id": "loader",
                        "url": "https://example.invalid",
                    },
                },
                application_ref_digest="a" * 64,
                appserver_identity={},
                driver_executable="/native/driver",
            )
            row = native_mutation_row()
            if change == "missing_ref":
                row.pop("native_ref")
            elif change == "control_ref":
                row["native_ref"] = "bad\nref"
            elif change == "long_ref":
                row["native_ref"] = "x" * 257
            elif change == "hint_extra":
                row["field_hint"]["html"] = "<input>"
            elif change == "hint_type":
                row["field_hint"]["role"] = []
            elif change == "long_name":
                row["field_hint"]["name"] = "x" * 1001
            elif change == "raw_text":
                row["text"] = "private text"
            state["calls"] = [row]
            with pytest.raises(PortalDataError) as error:
                client.handoff_status()
            assert error.value.code == "cua_handoff_unknown"
        finally:
            state["calls"] = []
            client.close()


def test_yield_pump_keeps_browser_live_without_querying_unsent_handoff(tmp_path, monkeypatch):
    import career_evidence_graph.cua_driver as module

    monkeypatch.setattr(
        module, "verify_native_handoff_recipient", lambda *args, **kwargs: {"pid": 20}
    )
    with native_service(tmp_path) as (path, options, process, requests, _):
        client = NativeCuaSessionClient(path, process, options, driver_sha256="1" * 64, timeout=1)
        browser_ticks = []
        maintained = []

        def keep_owner(*, pump):
            # A real daemon cannot find a grant before it receives the yield request.
            assert any(r["method"] == "trusted_session_yield" for r in requests)
            maintained.append(client.handoff_status(pump=pump))

        cua = module.CuaDriver(client, 1, keep_owner=keep_owner)

        def tick():
            cua.maintain(pump=lambda: browser_ticks.append(1))

        try:
            client.yield_to(
                ready_record(path),
                request_id="borrow-one",
                scope={
                    "target_id": "original",
                    "tab_id": "tab",
                    "expected_document": {
                        "frame_id": "frame",
                        "loader_id": "loader",
                        "url": "https://example.invalid",
                    },
                },
                application_ref_digest="a" * 64,
                appserver_identity={},
                driver_executable="/native/driver",
                pump=tick,
            )
            assert browser_ticks and not maintained
            assert not any(r["method"] == "trusted_session_handoff_status" for r in requests)
            cua.maintain(pump=tick)
            assert len(maintained) == 1 and maintained[0]["active_calls"] == 1
            assert sum(r["method"] == "trusted_session_handoff_status" for r in requests) == 1
            assert not any(r["method"] == "trusted_session_call" for r in requests)
            assert not client.failed
        finally:
            client.close()


def test_control_pump_can_revoke_once_without_recursive_status_queries(tmp_path, monkeypatch):
    import career_evidence_graph.cua_driver as module

    monkeypatch.setattr(
        module, "verify_native_handoff_recipient", lambda *args, **kwargs: {"pid": 20}
    )
    with native_service(tmp_path) as (path, options, process, requests, _):
        client = NativeCuaSessionClient(path, process, options, driver_sha256="1" * 64, timeout=1)
        try:
            client.yield_to(
                ready_record(path),
                request_id="borrow-one",
                scope={
                    "target_id": "original",
                    "tab_id": "tab",
                    "expected_document": {
                        "frame_id": "frame",
                        "loader_id": "loader",
                        "url": "https://example.invalid",
                    },
                },
                application_ref_digest="a" * 64,
                appserver_identity={},
                driver_executable="/native/driver",
            )
            ticks = []
            pumping = False

            def tick():
                nonlocal pumping
                assert not pumping
                assert client.control_inflight
                if not ticks:
                    ticks.append(1)
                    pumping = True
                    try:
                        revoked = client.revoke_handoff(pump=tick)
                        assert revoked["revoked"] is True
                    finally:
                        pumping = False

            status = client.handoff_status(pump=tick)
            assert status["local_tools_drained"] is False
            assert ticks == [1] and not client.control_inflight
            assert sum(r["method"] == "trusted_session_handoff_revoke" for r in requests) == 1
        finally:
            client.close()


def test_ready_native_reply_is_read_before_another_owner_pump(tmp_path):
    # The owner pump took 1.3-3.1 s per call while the driver answered at once.
    with native_service(tmp_path) as (path, options, process, _, _):
        client = NativeCuaSessionClient(path, process, options, driver_sha256="1" * 64, timeout=1)
        ours, driver = socket.socketpair()
        try:
            ours.setblocking(False)
            driver.sendall(b'{"ok": true, "result": {"status": "ok"}}\n')
            pumps = []
            assert client._exchange(
                ours, {"method": "trusted_session_handoff_status"}, pump=lambda: pumps.append(1)
            ) == {"status": "ok"}
            assert pumps == [1]  # only the check before any request bytes
        finally:
            ours.close()
            driver.close()
            client.close()


@pytest.mark.parametrize("lost_reply", [False, True])
def test_failed_receiver_bind_retains_return_path_without_native_admission(
    tmp_path, monkeypatch, lost_reply
):
    import career_evidence_graph.cua_driver as module

    monkeypatch.setattr(
        module, "verify_native_handoff_recipient", lambda *args, **kwargs: {"pid": 20}
    )
    with native_service(tmp_path, yielded=False, fail_yield_once=lost_reply) as (
        path,
        options,
        process,
        requests,
        state,
    ):
        client = NativeCuaSessionClient(path, process, options, driver_sha256="1" * 64, timeout=1)
        try:

            def request_yield():
                return client.yield_to(
                    ready_record(path),
                    request_id="borrow-one",
                    scope={
                        "target_id": "original",
                        "tab_id": "tab",
                        "expected_document": {
                            "frame_id": "frame",
                            "loader_id": "loader",
                            "url": "https://example.invalid",
                        },
                    },
                    application_ref_digest="a" * 64,
                    appserver_identity={},
                    driver_executable="/native/driver",
                )

            if lost_reply:
                with pytest.raises(PortalDataError):
                    request_yield()
                assert client.failed
                receipt = client.reconcile_handoff()
                assert not client.failed
            else:
                receipt = request_yield()
            assert receipt["yielded"] is False and "private-return" not in json.dumps(receipt)
            assert client.handoff_active
            with pytest.raises(PortalDataError):
                client.admit_call("native-call", "b" * 64, "allow")
            assert not any(r["method"] == "trusted_session_handoff_admit" for r in requests)
            state.update(active_calls=0, return_ready=True)
            client.resume_after_handoff()
            assert not client.handoff_active
            assert next(r for r in requests if r["method"] == "trusted_session_resume")["args"] == {
                "resume_credential": "private-return"
            }
        finally:
            client.close()


@pytest.mark.parametrize("control", [False, True])
def test_false_pump_stops_before_any_native_request_bytes(tmp_path, control):
    with native_service(tmp_path) as (path, options, process, requests, _):
        client = NativeCuaSessionClient(path, process, options, driver_sha256="1" * 64, timeout=1)
        before = len(requests)
        try:
            with pytest.raises(PortalDataError):
                if control:
                    client._control_request(
                        {"method": "trusted_session_handoff_status", "args": {"handoff_id": "x"}},
                        pump=lambda: False,
                    )
                else:
                    client.call("get_browser_state", {}, pump=lambda: False)
            assert len(requests) == before
            assert client.failed
        finally:
            client.close()


@pytest.mark.parametrize("yielded", [None, 1, "true"])
def test_yield_receipt_requires_boolean_grant(tmp_path, monkeypatch, yielded):
    import career_evidence_graph.cua_driver as module

    monkeypatch.setattr(
        module, "verify_native_handoff_recipient", lambda *args, **kwargs: {"pid": 20}
    )
    with native_service(tmp_path, yielded=yielded) as (path, options, process, requests, _):
        client = NativeCuaSessionClient(path, process, options, driver_sha256="1" * 64, timeout=1)
        try:
            with pytest.raises(PortalDataError) as error:
                client.yield_to(
                    ready_record(path),
                    request_id="borrow-one",
                    scope={
                        "target_id": "original",
                        "tab_id": "tab",
                        "expected_document": {
                            "frame_id": "frame",
                            "loader_id": "loader",
                            "url": "https://example.invalid",
                        },
                    },
                    application_ref_digest="a" * 64,
                    appserver_identity={},
                    driver_executable="/native/driver",
                )
            assert error.value.code == "cua_handoff_unknown"
            assert client.failed and client.handoff_active
            with pytest.raises(PortalDataError):
                client.admit_call("native-call", "b" * 64, "allow")
            assert not any(r["method"] == "trusted_session_handoff_admit" for r in requests)
        finally:
            client.close()
