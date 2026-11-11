"""Synthetic owner-health reads never change the browser or named session."""

import json
import sys
from types import SimpleNamespace

import pytest

from career_evidence_graph.career_portal_data import PortalDataError
from career_evidence_graph.cua_driver import CuaDriver, CuaMcpClient


@pytest.mark.parametrize("owned", [True, False])
def test_owner_read_uses_one_existing_transport_without_scope_or_tab_selection(monkeypatch, owned):
    calls = []

    def pump():
        pass

    client = SimpleNamespace(
        failed=False,
        process=SimpleNamespace(poll=lambda: None),
        session="synthetic-existing-session",
    )

    def call(name, arguments, **kwargs):
        calls.append((name, arguments, kwargs))
        return {
            "status": "ok",
            "binding_quality": "exact",
            "endpoint_access_class": "driver_owned" if owned else "existing_profile_approved",
            "target_id": "synthetic-owner-target",
            "mutation_allowed": False,
            "tabs": [{"url": "https://never-select.invalid", "tab_id": "not-a-page-grant"}],
        }

    client.call = call
    driver = CuaDriver(
        client,
        42,
        window_id=7,
        driver_owned=owned,
        ensure_scope=lambda *_: (_ for _ in ()).throw(AssertionError("No scope refresh")),
        keep_owner=lambda **_: (_ for _ in ()).throw(AssertionError("One fresh read only")),
    )
    monkeypatch.setattr("career_evidence_graph.cua_driver.time.time", lambda: 123.0)

    result = driver.observe_owner(pump=pump)

    assert result == {
        "status": "accepted",
        "pid": 42,
        "window_id": 7,
        "observed_at": 123.0,
        "driver_version": None,
    }
    assert calls == [
        ("get_browser_state", {"pid": 42, "window_id": 7}, {"pump": pump, "owner": True})
    ]
    assert client.session == "synthetic-existing-session"
    assert driver.client is client


@pytest.mark.parametrize(
    "change",
    [
        {"status": "expired"},
        {"status": "refused"},
        {"binding_quality": "heuristic"},
        {"endpoint_access_class": "external"},
        {"endpoint_access_class": "existing_profile_approved"},
        {"target_id": ""},
        {"target_id": " "},
        {"target_id": 42},
        {"refusal": {"code": "expired"}},
    ],
)
def test_unproven_owner_receipt_is_refused_without_fallback(change):
    calls = []
    reply = {
        "status": "ok",
        "binding_quality": "exact",
        "endpoint_access_class": "driver_owned",
        "target_id": "synthetic-owner-target",
    } | change

    def call(name, arguments, **kwargs):
        calls.append((name, arguments, kwargs))
        return reply

    client = SimpleNamespace(failed=False, process=SimpleNamespace(poll=lambda: None), call=call)
    driver = CuaDriver(client, 42, window_id=7, driver_owned=True)

    with pytest.raises(PortalDataError) as error:
        driver.observe_owner(pump=None)

    assert error.value.code == "cua_owner_unknown"
    assert len(calls) == 1
    assert calls[0] == (
        "get_browser_state",
        {"pid": 42, "window_id": 7},
        {"pump": None, "owner": True},
    )


@pytest.mark.parametrize("fault", ["failed", "exited"])
def test_transport_becoming_unknown_during_the_read_cannot_publish_health(fault):
    calls = []
    client = SimpleNamespace(failed=False, process=SimpleNamespace(poll=lambda: None))

    def call(name, arguments, **kwargs):
        calls.append((name, arguments, kwargs))
        if fault == "failed":
            client.failed = True
        else:
            client.process.poll = lambda: 0
        return {
            "status": "ok",
            "binding_quality": "exact",
            "endpoint_access_class": "driver_owned",
            "target_id": "synthetic-owner-target",
        }

    client.call = call
    driver = CuaDriver(client, 42, window_id=7, driver_owned=True)
    with pytest.raises(PortalDataError) as error:
        driver.observe_owner(pump=None)

    assert error.value.code == "cua_owner_unknown"
    assert len(calls) == 1


# A typed cua_refused is read again (test_a_refused_owner_read_is_read_again).
@pytest.mark.parametrize("code", ["cua_scope_expired", "cua_result_unknown"])
def test_rpc_refusal_or_unknown_result_does_not_retry_or_refresh(code):
    calls = []
    client = SimpleNamespace(failed=False, process=SimpleNamespace(poll=lambda: None))

    def call(name, arguments, **kwargs):
        calls.append(name)
        raise PortalDataError(code, "Synthetic owner refusal", 409)

    client.call = call
    with pytest.raises(PortalDataError) as error:
        CuaDriver(client, 42, window_id=7, driver_owned=True).observe_owner(pump=None)

    assert error.value.code == code
    assert calls == ["get_browser_state"]


@pytest.mark.parametrize(
    "change",
    [
        "failed",
        "exited",
        "missing_client",
        "missing_process",
        "missing_pid",
        "bool_pid",
        "missing_window",
        "bool_window",
    ],
)
def test_unavailable_original_transport_or_window_stops_before_any_rpc(change):
    def call(*_args, **_kwargs):
        pytest.fail("An unavailable original owner must not dispatch or reconnect")

    client = SimpleNamespace(failed=False, process=SimpleNamespace(poll=lambda: None), call=call)
    driver = CuaDriver(client, 42, window_id=7, driver_owned=True)
    if change == "failed":
        client.failed = True
    elif change == "exited":
        client.process.poll = lambda: -9
    elif change == "missing_client":
        driver.client = None
    elif change == "missing_process":
        client.process = None
    elif change == "missing_pid":
        driver.pid = None
    elif change == "bool_pid":
        driver.pid = True
    elif change == "missing_window":
        driver.window_id = None
    else:
        driver.window_id = True

    with pytest.raises(PortalDataError) as error:
        driver.observe_owner(pump=None)

    assert error.value.code == "cua_owner_unknown"


@pytest.mark.parametrize(
    "server_info,expected",
    [({"version": "0.synthetic-owner"}, "0.synthetic-owner"), ({"version": 42}, None), ({}, None)],
)
def test_owner_version_comes_from_the_same_transport_initialize_reply(
    tmp_path, server_info, expected
):
    backend = tmp_path / "synthetic-mcp.py"
    calls = tmp_path / "calls.jsonl"
    backend.write_text("""import json, sys
server_info, calls = json.loads(sys.argv[1]), sys.argv[2]
for line in sys.stdin:
    message = json.loads(line)
    if "id" not in message:
        continue
    if message["method"] == "initialize":
        result = {"serverInfo": server_info}
    elif message["method"] == "tools/list":
        result = {"tools": [{"name": name} for name in (
            "browser_prepare", "get_browser_state", "browser_click", "list_windows",
            "end_session", "check_permissions")]}
    else:
        with open(calls, "a") as handle:
            handle.write(json.dumps(message["params"]) + "\\n")
        result = {"structuredContent": {"status": "ok", "binding_quality": "exact",
            "endpoint_access_class": "driver_owned", "target_id": "synthetic-owner"}}
    print(json.dumps({"jsonrpc": "2.0", "id": message["id"], "result": result}), flush=True)
""")
    with (tmp_path / "driver.log").open("w") as log:
        client = CuaMcpClient(
            [sys.executable, "-B", str(backend), json.dumps(server_info), str(calls)],
            log,
            timeout=2,
        )
        try:
            session = client.session
            result = CuaDriver(client, 42, window_id=7, driver_owned=True).observe_owner(pump=None)

            assert client.driver_version == expected
            assert result["driver_version"] == expected
            assert client.session == session
            assert [json.loads(line) for line in calls.read_text().splitlines()] == [
                {"name": "get_browser_state", "arguments": {"pid": 42, "window_id": 7}}
            ]
        finally:
            client.close()


def test_a_refused_owner_read_is_read_again(monkeypatch):
    # 2026-11-07, Harmattan: the driver's host check raced the App's process lookup and
    # one refused read at takeover start revoked the takeover.
    calls = []

    def call(name, arguments, **kwargs):
        calls.append(name)
        if len(calls) == 1:
            raise PortalDataError("cua_refused", "Cua 拒绝该操作。", 409)
        return {
            "status": "ok",
            "binding_quality": "exact",
            "endpoint_access_class": "driver_owned",
            "target_id": "synthetic-owner-target",
        }

    client = SimpleNamespace(failed=False, process=SimpleNamespace(poll=lambda: None), call=call)
    driver = CuaDriver(client, 42, window_id=7, driver_owned=True)
    monkeypatch.setattr("career_evidence_graph.cua_driver.time.sleep", lambda _: None)

    assert driver.observe_owner(pump=None)["status"] == "accepted"
    assert calls == ["get_browser_state", "get_browser_state"]


def test_an_owner_read_refused_every_time_still_fails(monkeypatch):
    calls = []

    def call(name, arguments, **kwargs):
        calls.append(name)
        raise PortalDataError("cua_refused", "Cua 拒绝该操作。", 409)

    client = SimpleNamespace(failed=False, process=SimpleNamespace(poll=lambda: None), call=call)
    driver = CuaDriver(client, 42, window_id=7, driver_owned=True)
    monkeypatch.setattr("career_evidence_graph.cua_driver.time.sleep", lambda _: None)

    with pytest.raises(PortalDataError) as error:
        driver.observe_owner(pump=None)
    assert error.value.code == "cua_refused" and len(calls) == 3
