"""Passive read-only tool requests use the Worker caller and fixed reference."""

import json
import threading
import time
from contextlib import suppress

import pytest
from test_application_codex_assist import config, server

from career_evidence_graph.application_codex_assist import CodexAdapter

PNG = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAIAAACQd1PeAAAADElEQVR4nGP4//8/AAX+Av4N70a4AAAAAElFTkSuQmCC"


def reference():
    return {
        "id": "assist-synthetic",
        "generation": 1,
        "binding": {"page_id": "original-page", "document_token": "original-document"},
        "page_writes_enabled": False,
    }


def observation(ref):
    return {
        "data": {"url": "https://example.invalid/application", "fields": []},
        "document": {"loader_id": "original-loader"},
        "binding": ref["binding"],
        "at": 1.0,
        "screenshot": {"mime_type": "image/png", "base64": PNG},
    }


def tool_server(tmp_path, requests):
    executable = server(tmp_path)
    insertion = ""
    for request in requests:
        insertion += f"        send({request!r})\n"
    reply = "        send({'id':msg['id'],'result':{'thread':{'id':'thread-synthetic'}}})\n"
    source = executable.read_text().replace(reply, reply + insertion)
    executable.write_text(source)
    return executable


def request(identifier="read-1", **changes):
    return {
        "id": identifier,
        "method": "item/tool/call",
        "params": {
            "threadId": "thread-synthetic",
            "turnId": "passive-synthetic-turn",
            "callId": identifier,
            "tool": "observe_owned_page",
            "arguments": {},
            **changes,
        },
    }


def rows(executable):
    result = []
    for line in executable.with_suffix(".jsonl").read_text().splitlines():
        # The fixture may still be appending a large image response.
        with suppress(json.JSONDecodeError):
            result.append(json.loads(line))
    return result


def wait_response(adapter, executable, identifier):
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline:
        adapter.service_readonly()
        found = next((r for r in rows(executable) if r.get("id") == identifier), None)
        if found is not None:
            return found
        time.sleep(0.005)
    raise AssertionError("controlled server did not receive tool response")


def test_readonly_tool_returns_an_image_on_the_worker_caller_thread(tmp_path):
    executable = tool_server(tmp_path, [request()])
    adapter = CodexAdapter(config(tmp_path, executable))
    calls = []

    def observe(ref):
        calls.append((threading.get_ident(), ref))
        return observation(ref)

    try:
        run = adapter.start(reference(), request_id="start", readonly_handler=observe)
        response = wait_response(adapter, executable, "read-1")
        assert calls == [(threading.get_ident(), reference())]
        assert response["result"]["success"] is True
        content = response["result"]["contentItems"]
        assert content[1] == {"type": "inputImage", "imageUrl": "data:image/png;base64," + PNG}
        assert json.loads(content[0]["text"])["binding"] == reference()["binding"]
        recorded = rows(executable)
        start = next(r for r in recorded if r.get("method") == "thread/start")
        assert [tool["name"] for tool in start["params"]["dynamicTools"]] == ["observe_owned_page"]
        assert not any(r.get("method") == "turn/start" for r in recorded)
        assert run.page_write_allowed is False and run.model_turn_allowed is False
    finally:
        adapter.close()


def test_startup_wait_yields_to_control_and_browser_pump(tmp_path):
    executable = server(tmp_path)
    executable.write_text(
        executable.read_text().replace(
            "    if msg.get('method')=='initialize':\n",
            "    if msg.get('method')=='initialize':\n        time.sleep(.15)\n",
        )
    )
    adapter = CodexAdapter(config(tmp_path, executable))
    pumped = []
    try:
        run = adapter.start(
            reference(), request_id="start", pump=lambda: pumped.append(threading.get_ident())
        )
        assert run.status == "ready"
        assert pumped and set(pumped) == {threading.get_ident()}
    finally:
        adapter.close()


@pytest.mark.parametrize("setting", [{"readonly_handler": True}, {"pump": True}])
def test_invalid_callback_configuration_is_rejected_before_start(tmp_path, setting):
    executable = server(tmp_path)
    adapter = CodexAdapter(config(tmp_path, executable))
    try:
        with pytest.raises(ValueError, match="callback"):
            adapter.start(reference(), request_id="start", **setting)
    finally:
        adapter.close()
    assert not executable.with_suffix(".jsonl").exists()


@pytest.mark.parametrize(
    "change",
    [
        {"threadId": "foreign-thread"},
        {"tool": "write_page"},
        {"arguments": {"url": "https://foreign.example.invalid"}},
        {"arguments": None},
        {"namespace": "shell"},
        {"url": "https://foreign.example.invalid"},
        {"turnId": ""},
        {"callId": ""},
        {"callId": "x" * 129},
    ],
)
def test_only_the_empty_argument_original_page_tool_is_callable(tmp_path, change):
    executable = tool_server(tmp_path, [request(**change)])
    adapter = CodexAdapter(config(tmp_path, executable))
    observed, pumped = [], []
    try:
        adapter.start(
            reference(),
            request_id="start",
            readonly_handler=lambda ref: observed.append(ref) or observation(ref),
            pump=lambda: pumped.append(True),
        )
        pumped.clear()
        result = wait_response(adapter, executable, "read-1")
        assert "error" in result
        assert observed == []
        assert pumped
    finally:
        adapter.close()


def test_duplicate_rpc_or_call_id_never_recaptures_or_replays_a_screenshot(tmp_path):
    executable = tool_server(
        tmp_path,
        [
            request("rpc-1", callId="call-1"),
            request("rpc-1", callId="call-2"),
            request("rpc-3", callId="call-1"),
        ],
    )
    adapter = CodexAdapter(config(tmp_path, executable))
    observed = []
    try:
        adapter.start(
            reference(),
            request_id="start",
            readonly_handler=lambda ref: observed.append(ref) or observation(ref),
        )
        result = wait_response(adapter, executable, "rpc-3")
        assert "error" in result
        assert len(observed) == 1
        replies = [r for r in rows(executable) if r.get("id") == "rpc-1"]
        assert len(replies) == 2 and "result" in replies[0] and "error" in replies[1]
    finally:
        adapter.close()


def test_each_service_turn_leaves_the_next_observation_for_a_later_worker_tick(tmp_path):
    executable = tool_server(tmp_path, [request("read-1"), request("read-2")])
    executable.write_text(
        executable.read_text().replace(
            "        send({'id': 'read-2',",
            "        Path(__file__).with_suffix('.ready').touch()\n        send({'id': 'read-2',",
        )
    )
    adapter = CodexAdapter(config(tmp_path, executable))
    observed = []
    try:
        adapter.start(
            reference(),
            request_id="start",
            readonly_handler=lambda ref: observed.append(ref) or observation(ref),
        )
        deadline = time.monotonic() + 2
        while not executable.with_suffix(".ready").exists() and time.monotonic() < deadline:
            time.sleep(0.005)
        assert executable.with_suffix(".ready").exists()
        time.sleep(0.02)
        assert observed == []  # The pipe reader cannot invoke the Page callback.
        adapter.service_readonly()
        assert len(observed) == 1
        adapter.service_readonly()
        assert len(observed) == 2
    finally:
        adapter.close()


def test_nonowner_thread_cannot_consume_page_requests(tmp_path):
    executable = tool_server(tmp_path, [request()])
    adapter = CodexAdapter(config(tmp_path, executable))
    observed, failures = [], []
    try:
        adapter.start(
            reference(),
            request_id="start",
            readonly_handler=lambda ref: observed.append(ref) or observation(ref),
        )

        def poll():
            try:
                adapter.service_readonly()
            except ValueError as error:
                failures.append(str(error))

        other = threading.Thread(target=poll)
        other.start()
        other.join(timeout=1)
        assert failures and observed == []
        assert wait_response(adapter, executable, "read-1")["result"]["success"] is True
        assert len(observed) == 1
    finally:
        adapter.close()


def test_revoked_scope_after_capture_does_not_send_the_image(tmp_path):
    executable = tool_server(tmp_path, [request()])
    adapter = CodexAdapter(config(tmp_path, executable))
    current = True
    observed = []

    def observe(ref):
        nonlocal current
        observed.append(ref)
        current = False
        return observation(ref)

    try:
        adapter.start(
            reference(), request_id="start", readonly_handler=observe, pump=lambda: current
        )
        deadline = time.monotonic() + 2
        result = None
        while not observed and time.monotonic() < deadline:
            result = adapter.service_readonly()
            time.sleep(0.005)
        assert result.status == "unknown" and result.error_code == "read_scope_changed"
        assert not any(r.get("id") == "read-1" for r in rows(executable))
    finally:
        adapter.close()


def test_handler_failure_is_a_read_error_without_private_exception_text(tmp_path):
    executable = tool_server(tmp_path, [request()])
    adapter = CodexAdapter(config(tmp_path, executable))

    def failed(ref):
        raise ValueError("private observation sentinel")

    try:
        adapter.start(reference(), request_id="start", readonly_handler=failed)
        response = wait_response(adapter, executable, "read-1")
        assert "error" in response
        assert "private observation sentinel" not in json.dumps(rows(executable))
    finally:
        adapter.close()


def test_output_backpressure_keeps_pumping_before_the_bounded_failure(tmp_path):
    executable = tool_server(tmp_path, [request()])
    needle = "if SCENARIO=='stubborn':\n"
    executable.write_text(
        executable.read_text().replace(
            needle,
            "        Path(__file__).with_suffix('.waiting').touch()\n"
            "        time.sleep(30)\n" + needle,
        )
    )
    value = config(tmp_path, executable).to_dict()
    value["stop_timeout"] = 0.1
    from career_evidence_graph.application_codex_assist import CodexAssistConfig

    adapter = CodexAdapter(CodexAssistConfig.from_dict(value))
    pumped = []

    def observe(ref):
        captured = observation(ref)
        captured["data"]["fields"] = [{"value": "x" * 4000}] * 128
        return captured

    try:
        adapter.start(
            reference(),
            request_id="start",
            readonly_handler=observe,
            pump=lambda: pumped.append(True),
        )
        deadline = time.monotonic() + 2
        while not executable.with_suffix(".waiting").exists() and time.monotonic() < deadline:
            time.sleep(0.005)
        assert executable.with_suffix(".waiting").exists()
        before = len(pumped)
        started = time.monotonic()
        result = adapter.service_readonly()
        assert result.status == "unknown" and result.error_code == "transport_write_unknown"
        assert len(pumped) >= before + 2
        assert time.monotonic() - started < 4
    finally:
        adapter.close()


def test_progress_only_retains_tool_work_for_explicit_service(tmp_path):
    executable = tool_server(
        tmp_path,
        [
            request(),
            {"id": "approval-1", "method": "item/permissions/requestApproval", "params": {}},
        ],
    )
    adapter = CodexAdapter(config(tmp_path, executable))
    observed, pumped = [], []
    try:
        adapter.start(
            reference(),
            request_id="start",
            readonly_handler=lambda ref: observed.append(ref) or observation(ref),
            pump=lambda: pumped.append(True),
        )
        pumped.clear()
        for _ in range(5):
            adapter.progress()
            time.sleep(0.01)
        assert observed == [] and pumped == []
        assert not any(row.get("id") in {"read-1", "approval-1"} for row in rows(executable))
        deadline = time.monotonic() + 2
        while not observed and time.monotonic() < deadline:
            adapter.service_readonly()
            time.sleep(0.005)
        assert len(observed) == 1
        assert wait_response(adapter, executable, "read-1")["result"]["success"] is True
        assert "error" in wait_response(adapter, executable, "approval-1")
        assert pumped
    finally:
        adapter.close()


@pytest.mark.parametrize("fault", ["malformed", "eof", "overflow"])
def test_known_reader_failure_prevents_queued_observation_and_image(tmp_path, fault):
    executable = tool_server(tmp_path, [request()])
    extra = {
        "malformed": "        os.write(1,b'bad-json\\n')\n",
        "eof": "        os.close(1)\n",
        "overflow": "        os.write(1,b'x'*1048577)\n",
    }[fault]
    source = executable.read_text().replace(
        "        send({'id': 'read-1',",
        "        while not Path(__file__).with_suffix('.release').exists(): time.sleep(.005)\n"
        "        send({'id': 'read-1',",
    )
    executable.write_text(
        source.replace(
            "if SCENARIO=='stubborn':\n",
            extra + "        Path(__file__).with_suffix('.fault').touch()\n"
            "        time.sleep(30)\nif SCENARIO=='stubborn':\n",
        )
    )
    adapter = CodexAdapter(config(tmp_path, executable))
    observed = []
    try:
        run = adapter.start(
            reference(),
            request_id="start",
            readonly_handler=lambda ref: observed.append(ref) or observation(ref),
        )
        assert run.status == "ready"
        executable.with_suffix(".release").touch()
        deadline = time.monotonic() + 2
        while not executable.with_suffix(".fault").exists() and time.monotonic() < deadline:
            time.sleep(0.005)
        assert executable.with_suffix(".fault").exists()
        time.sleep(0.05)
        result = adapter.service_readonly(run.run_id)
        assert result.status == "unknown"
        assert observed == []
        assert not any(row.get("id") == "read-1" for row in rows(executable))
    finally:
        adapter.close()


def test_reader_failure_during_capture_prevents_the_success_response(tmp_path):
    executable = tool_server(tmp_path, [request()])
    executable.write_text(
        executable.read_text().replace(
            "if SCENARIO=='stubborn':\n",
            "        while not Path(__file__).with_suffix('.trigger').exists(): time.sleep(.005)\n"
            "        os.write(1,b'bad-json\\n')\n"
            "        Path(__file__).with_suffix('.fault').touch()\n"
            "        time.sleep(30)\nif SCENARIO=='stubborn':\n",
        )
    )
    adapter = CodexAdapter(config(tmp_path, executable))
    observed = []

    def observe(ref):
        observed.append(ref)
        executable.with_suffix(".trigger").touch()
        deadline = time.monotonic() + 2
        while not executable.with_suffix(".fault").exists() and time.monotonic() < deadline:
            time.sleep(0.005)
        assert executable.with_suffix(".fault").exists()
        time.sleep(0.05)
        return observation(ref)

    try:
        run = adapter.start(reference(), request_id="start", readonly_handler=observe)
        deadline = time.monotonic() + 2
        result = run
        while result.status == "ready" and time.monotonic() < deadline:
            result = adapter.service_readonly(run.run_id)
            time.sleep(0.005)
        assert result.status == "unknown" and len(observed) == 1
        assert not any(row.get("id") == "read-1" for row in rows(executable))
    finally:
        adapter.close()
