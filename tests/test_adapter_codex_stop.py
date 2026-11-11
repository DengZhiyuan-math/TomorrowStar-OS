"""Stopping revokes queued tools before draining the original execution."""

import os
import time

import pytest
from test_adapter_codex_readonly import observation, reference, request, rows, tool_server
from test_application_codex_assist import config, server

from career_evidence_graph.application_codex_assist import CodexAdapter, CodexAssistConfig


@pytest.mark.parametrize("handler_fails", [False, True])
def test_stop_inside_tool_does_not_claim_the_tool_has_drained(tmp_path, handler_fails):
    executable = tool_server(tmp_path, [request(), request("queued-second")])
    adapter = CodexAdapter(config(tmp_path, executable))
    during = []

    def observe(ref):
        during.append(adapter.stop(run.run_id, request_id="stop-original"))
        if handler_fails:
            raise ValueError("private outcome cannot be adopted after revocation")
        return observation(ref)

    try:
        run = adapter.start(reference(), request_id="start", readonly_handler=observe)
        deadline = time.monotonic() + 3
        while not during and time.monotonic() < deadline:
            adapter.service_readonly(run.run_id)
            time.sleep(0.005)
        assert during
        assert during[0].status == "stopping"
        assert during[0].tools_revoked is True
        assert during[0].local_tools_drained is False
        assert during[0].process_stopped is False
        stopped = adapter.progress(run.run_id)
        assert stopped.status == "stopped"
        assert stopped.stop_status == "stopped"
        assert stopped.local_tools_drained is True
        assert stopped.process_stopped is True
        assert not any(row.get("id") == "read-1" for row in rows(executable))
        assert len(during) == 1
    finally:
        adapter.close()


def native_server(tmp_path, *, completed=True):
    executable = server(tmp_path)
    source = executable.read_text()
    reply = "        send({'id':msg['id'],'result':{'thread':{'id':'thread-synthetic'}}})\n"
    source = source.replace(
        reply,
        reply + "        send({'method':'turn/started','params':{'threadId':'thread-synthetic',"
        "'turn':{'id':'original-turn','status':'inProgress'}}})\n",
    )
    interrupt = (
        "    elif msg.get('method')=='turn/interrupt':\n"
        "        send({'id':msg['id'],'result':{}})\n"
    )
    if completed:
        interrupt += (
            "        time.sleep(.03)\n"
            + f"        send({request('late-request')!r})\n"
            + "        time.sleep(.03)\n"
            "        send({'method':'turn/completed','params':{'threadId':'thread-synthetic',"
            "'turn':{'id':'original-turn','status':'interrupted'}}})\n"
        )
    source = source.replace("if SCENARIO=='stubborn':\n", interrupt + "if SCENARIO=='stubborn':\n")
    executable.write_text(source)
    return executable


def test_interrupt_ack_waits_for_native_terminal_and_refuses_late_tools(tmp_path):
    executable = native_server(tmp_path)
    value = config(tmp_path, executable).to_dict()
    value.update(stop_timeout=0.2)
    adapter = CodexAdapter(CodexAssistConfig.from_dict(value))
    observed = []
    try:
        run = adapter.start(
            reference(), request_id="start", readonly_handler=lambda ref: observed.append(ref)
        )
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline:
            before = adapter.progress(run.run_id)
            if before.native_turn_status == "running":
                break
            time.sleep(0.005)
        assert before.native_turn_id == "original-turn"
        assert before.native_turn_status == "running"
        stopped = adapter.stop(run.run_id, request_id="stop")
        assert stopped.stop_status == "stopped"
        assert stopped.native_turn_status == "interrupted"
        assert stopped.local_tools_drained and stopped.tools_revoked and stopped.process_stopped
        assert observed == []
        assert [
            row["params"] for row in rows(executable) if row.get("method") == "turn/interrupt"
        ] == [{"threadId": "thread-synthetic", "turnId": "original-turn"}]
    finally:
        adapter.close()


def test_interrupt_ack_without_terminal_retains_native_unknown_after_process_exit(tmp_path):
    executable = native_server(tmp_path, completed=False)
    value = config(tmp_path, executable).to_dict()
    value.update(stop_timeout=0.08)
    adapter = CodexAdapter(CodexAssistConfig.from_dict(value))
    try:
        run = adapter.start(reference(), request_id="start")
        deadline = time.monotonic() + 2
        while adapter.progress(run.run_id).native_turn_status != "running":
            assert time.monotonic() < deadline
            time.sleep(0.005)
        started = time.monotonic()
        stopped = adapter.stop(run.run_id, request_id="stop")
        assert time.monotonic() - started >= 0.07
        assert stopped.stop_status == "stopped" and stopped.process_stopped
        assert stopped.native_turn_status == "unknown"
        assert stopped.error_code == "native_stop_unknown"
        again = adapter.stop(run.run_id, request_id="stop")
        assert again == stopped
        assert len([row for row in rows(executable) if row.get("method") == "turn/interrupt"]) == 1
    finally:
        adapter.close()


@pytest.mark.parametrize("completed", [True, False])
def test_stopping_pump_continues_controls_even_after_scope_is_revoked(tmp_path, completed):
    executable = native_server(tmp_path, completed=completed)
    value = config(tmp_path, executable).to_dict()
    value.update(stop_timeout=0.15)
    adapter = CodexAdapter(CodexAssistConfig.from_dict(value))
    pumped = []
    stopping = False

    def pump():
        pumped.append(stopping)
        return not stopping

    try:
        run = adapter.start(reference(), request_id="start", pump=pump)
        deadline = time.monotonic() + 2
        while adapter.progress(run.run_id).native_turn_status != "running":
            assert time.monotonic() < deadline
            time.sleep(0.005)
        stopping = True
        stopped = adapter.stop(run.run_id, request_id="stop")
        assert True in pumped
        assert stopped.stop_status == "stopped"
        assert stopped.native_turn_status == ("interrupted" if completed else "unknown")
        assert stopped.error_code != "read_scope_changed"
    finally:
        adapter.close()


def test_stop_consumes_queued_native_start_before_interrupting(tmp_path):
    executable = native_server(tmp_path)
    value = config(tmp_path, executable).to_dict()
    value.update(stop_timeout=0.2)
    adapter = CodexAdapter(CodexAssistConfig.from_dict(value))
    try:
        run = adapter.start(reference(), request_id="start")
        time.sleep(0.03)
        stopped = adapter.stop(run.run_id, request_id="stop")
        assert stopped.native_turn_id == "original-turn"
        assert stopped.native_turn_status == "interrupted"
        assert len([row for row in rows(executable) if row.get("method") == "turn/interrupt"]) == 1
    finally:
        adapter.close()


def test_failed_process_termination_is_unknown_and_can_be_rechecked(tmp_path, monkeypatch):
    executable = server(tmp_path, "stubborn")
    value = config(tmp_path, executable).to_dict()
    value.update(stop_timeout=0.03)
    adapter = CodexAdapter(CodexAssistConfig.from_dict(value))
    original_killpg = os.killpg

    def denied(*args):
        raise PermissionError("synthetic host termination denial")

    try:
        run = adapter.start(reference(), request_id="start")
        monkeypatch.setattr(os, "killpg", denied)
        stopped = adapter.stop(run.run_id, request_id="stop")
        assert stopped.stop_status == "unknown" and stopped.status == "unknown"
        assert stopped.tools_revoked and stopped.local_tools_drained
        assert stopped.process_stopped is False
        assert stopped.error_code == "stop_unknown"
        monkeypatch.setattr(os, "killpg", original_killpg)
        assert adapter.stop(run.run_id, request_id="stop").stop_status == "stopped"
    finally:
        monkeypatch.setattr(os, "killpg", original_killpg)
        adapter.close()


@pytest.mark.parametrize("mismatch", ["turn", "thread"])
def test_unrelated_terminal_notification_does_not_complete_original_turn(tmp_path, mismatch):
    executable = native_server(tmp_path)
    source = executable.read_text()
    terminal = (
        "send({'method':'turn/completed','params':{'threadId':'thread-synthetic',"
        "'turn':{'id':'original-turn','status':'interrupted'}}})"
    )
    wrong = terminal.replace(
        "original-turn" if mismatch == "turn" else "thread-synthetic", "unrelated-identity"
    )
    executable.write_text(source.replace(terminal, wrong))
    value = config(tmp_path, executable).to_dict()
    value.update(stop_timeout=0.12)
    adapter = CodexAdapter(CodexAssistConfig.from_dict(value))
    try:
        run = adapter.start(reference(), request_id="start")
        time.sleep(0.03)
        stopped = adapter.stop(run.run_id, request_id="stop")
        assert stopped.native_turn_id == "original-turn"
        assert stopped.native_turn_status == "unknown"
        assert stopped.process_stopped and stopped.local_tools_drained
    finally:
        adapter.close()


def test_transport_failure_revokes_tools_without_claiming_requested_stop(tmp_path):
    executable = server(tmp_path, "malformed")
    adapter = CodexAdapter(config(tmp_path, executable))
    try:
        result = adapter.start(reference(), request_id="start")
        assert result.status == "unknown"
        assert result.tools_revoked is True
        assert result.local_tools_drained and result.process_stopped
        assert result.stop_status == "not_requested"
    finally:
        adapter.close()


def test_invalid_native_identity_fails_closed_without_retaining_its_content(tmp_path):
    executable = native_server(tmp_path)
    source = executable.read_text().replace("'original-turn'", repr("x" * 129))
    executable.write_text(source)
    adapter = CodexAdapter(config(tmp_path, executable))
    try:
        run = adapter.start(reference(), request_id="start")
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline:
            result = adapter.progress(run.run_id)
            if result.status == "unknown":
                break
            time.sleep(0.005)
        assert result.status == "unknown" and result.error_code == "turn_event_invalid"
        assert result.native_turn_id is None
        assert result.tools_revoked and result.process_stopped
    finally:
        adapter.close()


def test_revocation_during_partial_tool_response_does_not_finish_the_old_image(tmp_path):
    executable = tool_server(tmp_path, [request()])
    executable.write_text(
        executable.read_text().replace(
            "if SCENARIO=='stubborn':\n",
            "        pending=bytearray(os.read(0,4096))\n"
            "        Path(__file__).with_suffix('.prefix').write_bytes(pending)\n"
            "        time.sleep(.15)\n"
            "        while b'\\n' not in pending:\n"
            "            chunk=os.read(0,65536)\n"
            "            if not chunk: break\n"
            "            pending.extend(chunk)\n"
            "        record({'response_complete':b'\\n' in pending,'bytes':len(pending)})\n"
            "        if b'\\n' in pending: record(json.loads(pending))\n"
            "if SCENARIO=='stubborn':\n",
        )
    )
    value = config(tmp_path, executable).to_dict()
    value.update(stop_timeout=0.2)
    adapter = CodexAdapter(CodexAssistConfig.from_dict(value))
    stops = []

    def observe(ref):
        result = observation(ref)
        result["data"]["fields"] = [{"value": "x" * 4000}] * 128
        return result

    def pump():
        if executable.with_suffix(".prefix").exists() and not stops:
            stops.append(adapter.stop(run.run_id, request_id="stop-partial-image"))
            return False
        return True

    try:
        run = adapter.start(reference(), request_id="start", readonly_handler=observe, pump=pump)
        deadline = time.monotonic() + 3
        while not stops and time.monotonic() < deadline:
            result = adapter.service_readonly(run.run_id)
            time.sleep(0.005)
        assert stops
        assert stops[0].stop_status == "stopping"
        assert result.tools_revoked and result.process_stopped and result.local_tools_drained
        assert (
            next(row for row in rows(executable) if "response_complete" in row)["response_complete"]
            is False
        )
        assert not any(row.get("id") == "read-1" for row in rows(executable))
    finally:
        adapter.close()


def test_stop_drops_late_request_flood_without_sending_each_denial(tmp_path):
    executable = native_server(tmp_path)
    source = executable.read_text()
    start = (
        "        send({'method':'turn/started','params':{'threadId':'thread-synthetic',"
        "'turn':{'id':'original-turn','status':'inProgress'}}})\n"
    )
    source = source.replace(
        start,
        start + "".join(f"        send({request(f'flood-{i}')!r})\n" for i in range(100)),
    )
    executable.write_text(source)
    value = config(tmp_path, executable).to_dict()
    value.update(stop_timeout=0.2)
    adapter = CodexAdapter(CodexAssistConfig.from_dict(value))
    try:
        run = adapter.start(reference(), request_id="start")
        time.sleep(0.03)
        adapter.progress(run.run_id)
        started = time.monotonic()
        stopped = adapter.stop(run.run_id, request_id="stop")
        assert time.monotonic() - started < 0.6
        assert stopped.native_turn_status == "interrupted"
        assert stopped.stop_status == "stopped"
        assert not any(str(row.get("id", "")).startswith("flood-") for row in rows(executable))
    finally:
        adapter.close()


@pytest.mark.parametrize("phase", ["progress", "stop"])
@pytest.mark.parametrize("shape", ["method_list", "method_dict", "status_list", "status_dict"])
def test_malformed_native_notification_fails_closed_during_progress_or_stop(tmp_path, phase, shape):
    executable = native_server(tmp_path)
    value = [] if shape.endswith("list") else {}
    bad = {"method": value}
    if shape.startswith("status"):
        bad = {
            "method": "turn/completed",
            "params": {
                "threadId": "thread-synthetic",
                "turn": {"id": "original-turn", "status": value},
            },
        }
    start = (
        "        send({'method':'turn/started','params':{'threadId':'thread-synthetic',"
        "'turn':{'id':'original-turn','status':'inProgress'}}})\n"
    )
    executable.write_text(executable.read_text().replace(start, start + f"        send({bad!r})\n"))
    adapter = CodexAdapter(config(tmp_path, executable))
    try:
        run = adapter.start(reference(), request_id="start")
        time.sleep(0.03)
        result = (
            adapter.progress(run.run_id)
            if phase == "progress"
            else adapter.stop(run.run_id, request_id="stop")
        )
        assert result.error_code == (
            "protocol_method_invalid" if shape.startswith("method") else "turn_event_invalid"
        )
        assert result.tools_revoked and result.process_stopped
        assert result.native_turn_status == "unknown"
    finally:
        adapter.close()


def native_notice(method, status):
    return {
        "method": method,
        "params": {
            "threadId": "thread-synthetic",
            "turn": {"id": "original-turn", "status": status},
        },
    }


@pytest.mark.parametrize(
    "after", ["started", "same_terminal", "conflicting_terminal", "queued_tool"]
)
def test_native_terminal_is_monotonic_and_revokes_late_tool_permission(tmp_path, after):
    started = native_notice("turn/started", "inProgress")
    completed = native_notice("turn/completed", "completed")
    extra = {
        "started": started,
        "same_terminal": completed,
        "conflicting_terminal": native_notice("turn/completed", "interrupted"),
        "queued_tool": request("after-terminal", turnId="original-turn"),
    }[after]
    executable = tool_server(tmp_path, [started, completed, extra])
    adapter = CodexAdapter(config(tmp_path, executable))
    calls = []

    def observe(ref):
        calls.append(ref)
        return observation(ref)

    try:
        run = adapter.start(reference(), request_id="start", readonly_handler=observe)
        time.sleep(0.03)
        result = adapter.progress(run.run_id)
        assert result.native_turn_status == "completed"
        assert result.tools_revoked
        if after == "conflicting_terminal":
            assert result.status == "unknown" and result.error_code == "conflicting_turn_terminal"
        adapter.service_readonly(run.run_id)
        assert calls == []
        stopped = adapter.stop(run.run_id, request_id="stop")
        assert stopped.native_turn_status == "completed"
        assert not any(row.get("method") == "turn/interrupt" for row in rows(executable))
    finally:
        adapter.close()


@pytest.mark.parametrize("notification_count", [0, 200])
def test_native_completion_during_capture_prevents_its_late_image_response(
    tmp_path, notification_count
):
    executable = tool_server(
        tmp_path,
        [native_notice("turn/started", "inProgress"), request(turnId="original-turn")],
    )
    executable.write_text(
        executable.read_text().replace(
            "if SCENARIO=='stubborn':\n",
            "        while not Path(__file__).with_suffix('.capture').exists(): time.sleep(.005)\n"
            + "".join(
                "        send({'method':'synthetic/notification','params':{}})\n"
                for _ in range(notification_count)
            )
            + f"        send({native_notice('turn/completed', 'completed')!r})\n"
            + "        Path(__file__).with_suffix('.terminal').touch()\n"
            "if SCENARIO=='stubborn':\n",
        )
    )
    adapter = CodexAdapter(config(tmp_path, executable))

    def observe(ref):
        executable.with_suffix(".capture").touch()
        deadline = time.monotonic() + 2
        while not executable.with_suffix(".terminal").exists():
            assert time.monotonic() < deadline
            time.sleep(0.005)
        time.sleep(0.03)
        return observation(ref)

    try:
        run = adapter.start(reference(), request_id="start", readonly_handler=observe)
        deadline = time.monotonic() + 3
        while not executable.with_suffix(".capture").exists():
            assert time.monotonic() < deadline
            result = adapter.service_readonly(run.run_id)
            time.sleep(0.005)
        adapter.stop(run.run_id, request_id="stop")
        assert result.native_turn_status == ("completed" if notification_count == 0 else "unknown")
        if notification_count:
            assert result.error_code == "tool_protocol_pending"
        assert result.tools_revoked and result.process_stopped
        assert not any(row.get("id") == "read-1" for row in rows(executable))
    finally:
        adapter.close()


def test_protocol_backlog_defers_tool_until_queued_terminal_is_observed(tmp_path):
    notifications = [{"method": "synthetic/notification", "params": {}}] * 200
    executable = tool_server(
        tmp_path,
        [native_notice("turn/started", "inProgress"), request(turnId="original-turn")]
        + notifications
        + [native_notice("turn/completed", "completed")],
    )
    adapter = CodexAdapter(config(tmp_path, executable))
    calls = []

    def observe(ref):
        calls.append(ref)
        return observation(ref)

    try:
        run = adapter.start(reference(), request_id="start", readonly_handler=observe)
        time.sleep(0.05)
        for _ in range(5):
            result = adapter.service_readonly(run.run_id)
            assert calls == []
            if result.native_turn_status == "completed":
                break
        assert result.native_turn_status == "completed" and result.tools_revoked
        assert not any(row.get("id") == "read-1" for row in rows(executable))
    finally:
        adapter.close()


def test_late_native_start_cannot_retarget_the_turn_already_being_stopped(tmp_path):
    executable = native_server(tmp_path)
    ack = "        send({'id':msg['id'],'result':{}})\n"
    late = native_notice("turn/started", "inProgress")
    late["params"]["turn"]["id"] = "different-turn"
    executable.write_text(executable.read_text().replace(ack, ack + f"        send({late!r})\n"))
    value = config(tmp_path, executable).to_dict()
    value.update(stop_timeout=0.2)
    adapter = CodexAdapter(CodexAssistConfig.from_dict(value))
    try:
        run = adapter.start(reference(), request_id="start")
        time.sleep(0.03)
        result = adapter.stop(run.run_id, request_id="stop")
        assert result.native_turn_id == "original-turn"
        assert result.native_turn_status == "unknown"
        assert result.error_code == "unexpected_active_turn"
        assert result.process_stopped and result.tools_revoked
    finally:
        adapter.close()


def test_unbound_native_notice_before_thread_creation_cannot_claim_the_future_thread(tmp_path):
    executable = server(tmp_path)
    bad = native_notice("turn/started", "inProgress")
    bad["params"]["threadId"] = None
    needle = "    if msg.get('method')=='initialize':\n"
    executable.write_text(
        executable.read_text().replace(needle, needle + f"        send({bad!r})\n")
    )
    value = config(tmp_path, executable).to_dict()
    value.update(stop_timeout=0.05)
    adapter = CodexAdapter(CodexAssistConfig.from_dict(value))
    try:
        run = adapter.start(reference(), request_id="start")
        assert run.status == "ready" and run.thread_id == "thread-synthetic"
        assert run.native_turn_id is None and run.native_turn_status == "idle"
        adapter.stop(run.run_id, request_id="stop")
        assert not any(row.get("method") == "turn/interrupt" for row in rows(executable))
    finally:
        adapter.close()
