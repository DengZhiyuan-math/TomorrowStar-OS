"""Real synthetic MCP pipes exercise client shutdown without launching Cua."""

import json
import os
import subprocess
import sys
import threading

import pytest

from career_evidence_graph.career_portal_data import PortalDataError
from career_evidence_graph.cua_driver import CuaMcpClient


@pytest.mark.parametrize("hold_output", [False, True])
def test_close_after_backend_exit_with_output_pipe_still_open(tmp_path, monkeypatch, hold_output):
    backend = tmp_path / "synthetic_mcp.py"
    backend.write_text(
        """import json, sys
for line in sys.stdin:
    message = json.loads(line)
    if message['method'] == 'initialize':
        result = {}
    elif message['method'] == 'tools/list':
        result = {'tools': [{'name': name} for name in (
            'browser_prepare', 'get_browser_state', 'browser_click', 'list_windows',
            'end_session', 'check_permissions')]}
    else:
        continue
    print(json.dumps({'jsonrpc': '2.0', 'id': message['id'], 'result': result}), flush=True)
    if message['method'] == 'tools/list':
        break
"""
    )
    original_popen = subprocess.Popen
    read_fd, held_write_fd = os.pipe()

    def launch(command, **kwargs):
        assert command == [sys.executable, "-B", str(backend)]
        # Model a second writer holding the same OS pipe. The backend is real;
        # the test owns and releases every descriptor instead of orphaning a child.
        process = original_popen(command, **{**kwargs, "stdout": held_write_fd})
        process.stdout = os.fdopen(read_fd, "r", encoding="utf-8")
        return process

    monkeypatch.setattr(subprocess, "Popen", launch)
    client, closer = None, None
    closed = threading.Event()
    log = (tmp_path / "driver.log").open("w")
    try:
        client = CuaMcpClient([sys.executable, "-B", str(backend)], log, timeout=2)
        assert client.process.wait(timeout=2) == 0
        if not hold_output:
            os.close(held_write_fd)
            held_write_fd = None

        def close():
            client.close()
            closed.set()

        closer = threading.Thread(target=close)
        closer.start()
        assert closed.wait(2), "close blocked after backend exit while stdout writer remained open"
        closer.join(timeout=1)
        assert not closer.is_alive()
        assert client.process.stdout.closed and client.process.stdin.closed
        client.close()
    finally:
        if held_write_fd is not None:
            os.close(held_write_fd)
        if closer is not None:
            closer.join(timeout=3)
            assert not closer.is_alive()
        if client is not None:
            client.close()
            client.process.stdin.close()
        else:
            os.close(read_fd)
        log.close()


@pytest.fixture
def framed_backend(tmp_path):
    backend = tmp_path / "framed_mcp.py"
    calls = tmp_path / "calls.jsonl"
    backend.write_text(
        """import json, os, sys, time
mode, calls = sys.argv[1:]
for line in sys.stdin:
    message = json.loads(line)
    if 'id' not in message:
        continue
    if message['method'] == 'initialize':
        result = {}
    elif message['method'] == 'tools/list':
        names = ('browser_prepare', 'get_browser_state', 'browser_click',
                 'list_windows', 'end_session', 'check_permissions')
        result = {'tools': [] if mode == 'missing_tools' else [{'name': n} for n in names]}
    else:
        with open(calls, 'a') as handle:
            handle.write(json.dumps(message['params']) + '\\n')
        result = {'structuredContent': {'windows': [{'title': '合成窗口 🌱'}]}}
        if mode in ('partial_eof', 'invalid_utf8', 'empty_eof'):
            data = {'partial_eof': b'{"jsonrpc":"2.0","id":',
                    'invalid_utf8': b'\\xff\\n', 'empty_eof': b''}[mode]
            os.write(1, data)
            break
    data = json.dumps({'jsonrpc': '2.0', 'id': message['id'], 'result': result},
                      ensure_ascii=False).encode('utf-8')
    if message['method'] == 'tools/call':
        if mode == 'pump':
            time.sleep(0.1)
        if mode == 'final_frame':
            os.write(1, data)
            break
        # Split inside a multibyte code point and terminate with CRLF.
        split = data.index('合'.encode('utf-8')) + 1
        os.write(1, data[:split])
        time.sleep(0.03)
        os.write(1, data[split:] + b'\\r\\n')
    else:
        os.write(1, data + b'\\n')
"""
    )
    return backend, calls


@pytest.mark.parametrize("mode", ["split_utf8", "final_frame"])
def test_mcp_keeps_framed_unicode_and_final_response(framed_backend, tmp_path, mode):
    backend, calls = framed_backend
    with (tmp_path / "driver.log").open("w") as log:
        client = CuaMcpClient(
            [sys.executable, "-B", str(backend), mode, str(calls)], log, timeout=2
        )
        try:
            assert client.call("list_windows", {}) == {"windows": [{"title": "合成窗口 🌱"}]}
        finally:
            client.close()
        assert client.process.poll() == 0
        assert client.process.stdout.closed and client.process.stdin.closed


def test_owner_observation_and_named_scope_use_the_same_transport(framed_backend, tmp_path):
    backend, calls = framed_backend
    with (tmp_path / "driver.log").open("w") as log:
        client = CuaMcpClient(
            [sys.executable, "-B", str(backend), "pump", str(calls)], log, timeout=2
        )
        try:
            client.call("get_browser_state", {"pid": 42, "window_id": 7}, owner=True)
            client.call("get_browser_state", {"pid": 42, "window_id": 7})
            frames = [json.loads(line) for line in calls.read_text().splitlines()]
            assert frames[0]["arguments"] == {"pid": 42, "window_id": 7}
            assert frames[1]["arguments"] == {"pid": 42, "window_id": 7, "session": client.session}
        finally:
            client.close()


@pytest.mark.parametrize("mode", ["partial_eof", "invalid_utf8", "empty_eof"])
def test_mcp_disconnect_does_not_repeat_unknown_action(framed_backend, tmp_path, mode):
    backend, calls = framed_backend
    with (tmp_path / "driver.log").open("w") as log:
        client = CuaMcpClient(
            [sys.executable, "-B", str(backend), mode, str(calls)], log, timeout=2
        )
        try:
            for _ in range(2):
                with pytest.raises(PortalDataError) as error:
                    client.call("browser_click", {"ref": "synthetic:0"})
                assert error.value.code == "cua_result_unknown"
            assert len(calls.read_text().splitlines()) == 1
        finally:
            client.close()
        assert client.process.poll() == 0


def test_mcp_initialization_failure_releases_reader(framed_backend, tmp_path, monkeypatch):
    backend, calls = framed_backend
    launched = []
    original_popen = subprocess.Popen

    def launch(*args, **kwargs):
        process = original_popen(*args, **kwargs)
        launched.append(process)
        return process

    monkeypatch.setattr(subprocess, "Popen", launch)
    with (tmp_path / "driver.log").open("w") as log:
        with pytest.raises(PortalDataError) as error:
            CuaMcpClient(
                [sys.executable, "-B", str(backend), "missing_tools", str(calls)], log, timeout=2
            )
        assert error.value.code == "cua_unavailable"
    assert len(launched) == 1
    assert launched[0].poll() == 0
    assert launched[0].stdin.closed and launched[0].stdout.closed


def test_mcp_wait_keeps_pumping_on_calling_thread(framed_backend, tmp_path):
    backend, calls = framed_backend
    owner = threading.get_ident()
    pumped = []

    def pump():
        assert threading.get_ident() == owner
        pumped.append(True)

    with (tmp_path / "driver.log").open("w") as log:
        client = CuaMcpClient(
            [sys.executable, "-B", str(backend), "pump", str(calls)], log, timeout=2
        )
        try:
            assert client.call("list_windows", {}, pump=pump) == {
                "windows": [{"title": "合成窗口 🌱"}]
            }
            assert pumped
        finally:
            client.close()
