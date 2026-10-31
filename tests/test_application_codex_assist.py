from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

from career_evidence_graph.application_codex_assist import CodexAdapter, CodexAssistConfig


def server(tmp_path, scenario="normal"):
    executable = tmp_path / "codex-fixture"
    executable.write_text(
        f"#!{Path(sys.executable).resolve()}\n"
        + "import json, os, sys, time\nfrom pathlib import Path\n"
        + f"SCENARIO = {scenario!r}\n"
        + "log = Path(__file__).with_suffix('.jsonl')\n"
        + "def record(value):\n"
        + "    with log.open('a') as out: out.write(json.dumps(value)+'\\n')\n"
        + "def send(value):\n"
        + "    data=(json.dumps(value,ensure_ascii=False)+'\\n').encode()\n"
        + "    if SCENARIO=='chunks':\n"
        + "        for byte in data: os.write(1,bytes([byte]));time.sleep(.0001)\n"
        + "    else: os.write(1,data)\n"
        + "record({'argv':sys.argv[1:],'env_keys':sorted(os.environ)})\n"
        + "if sys.argv[1:]==['--version']:\n"
        + "    if SCENARIO=='wrong_version': print('codex-cli 0.1');sys.exit(0)\n"
        + "    if SCENARIO=='vanish': Path(__file__).unlink()\n"
        + "    print('codex-cli 0.166.0-alpha.5.1');sys.exit(0)\n"
        + "for line in sys.stdin:\n"
        + "    msg=json.loads(line);record(msg)\n"
        + "    if msg.get('method')=='initialize':\n"
        + "        if SCENARIO=='timeout': time.sleep(30)\n"
        + "        if SCENARIO=='rejected':\n"
        + "            send({'id':msg['id'],'error':{'code':-32000,'message':'secret sentinel'}})\n"
        + "            continue\n"
        + "        if SCENARIO=='missing_init':\n"
        + "            send({'id':msg['id'],'result':{}});continue\n"
        + "        if SCENARIO=='malformed': os.write(1,b'bad-json\\n');continue\n"
        + "        if SCENARIO=='early_eof': sys.exit(0)\n"
        + "        if SCENARIO=='partial_eof': os.write(1,b'{\\\"id\\\":1');sys.exit(0)\n"
        + "        if SCENARIO=='early_response':\n"
        + "            send({'id':3,'result':{'thread':{'id':'wrong-thread'}}})\n"
        + "        send({'id':msg['id'],'result':{\n"
        + "            'userAgent':'合成','codexHome':'synthetic',\n"
        + "            'platformFamily':'unix','platformOs':'macos'}})\n"
        + "    elif msg.get('method')=='config/read':\n"
        + "        if SCENARIO=='policy_rejected':\n"
        + "            send({'id':msg['id'],'error':{'code':-32601,'message':'unsupported'}})\n"
        + "            continue\n"
        + "        if SCENARIO=='policy_timeout': time.sleep(30)\n"
        + "        if SCENARIO=='policy_shape_unknown':\n"
        + "            send({'id':msg['id'],'result':{'config':{},'origins':{}}});continue\n"
        + "        servers={}\n"
        + "        if SCENARIO=='inherited_mcp': servers={'inherited':{'command':'must-not-run'}}\n"
        + "        send({'id':msg['id'],'result':{\n"
        + "            'config':{'mcp_servers':servers},'origins':{}}})\n"
        + "    elif msg.get('method')=='thread/start':\n"
        + "        if SCENARIO=='missing_thread':\n"
        + "            send({'id':msg['id'],'result':{'thread':None}});continue\n"
        + "        if SCENARIO=='tool_request':\n"
        + "            send({'id':'tool-1','method':'item/tool/call',\n"
        + "                'params':{'tool':'write_page'}})\n"
        + "        send({'id':msg['id'],'result':{'thread':{'id':'thread-synthetic'}}})\n"
        + "if SCENARIO=='stubborn':\n"
        + "    import signal\n"
        + "    signal.signal(signal.SIGTERM,signal.SIG_IGN)\n"
        + "    time.sleep(30)\n",
        encoding="utf-8",
    )
    executable.chmod(0o700)
    return executable


def config(tmp_path, executable):
    home, runtime = tmp_path / "home", tmp_path / "runtime"
    home.mkdir(exist_ok=True)
    runtime.mkdir(exist_ok=True)
    return CodexAssistConfig(executable=executable, runtime=runtime, home=home)


def test_start_is_metadata_only_and_stop_reaps_its_dedicated_process(tmp_path):
    executable = server(tmp_path)
    adapter = CodexAdapter(config(tmp_path, executable))

    run = adapter.start({"assistance_id": "assist-1", "generation": 1}, request_id="start-1")
    assert run.status == "ready"
    assert run.thread_id == "thread-synthetic"
    assert run.page_write_allowed is False
    assert run.model_turn_allowed is False
    assert adapter.progress(run.run_id).status == "ready"
    assert adapter.stop(run.run_id, request_id="stop-1").status == "stopped"
    assert adapter.stop(run.run_id, request_id="stop-1").status == "stopped"
    messages = [
        json.loads(line) for line in executable.with_suffix(".jsonl").read_text().splitlines()
    ]
    assert [m["method"] for m in messages if "method" in m] == [
        "initialize",
        "initialized",
        "config/read",
        "thread/start",
    ]


def test_missing_thread_is_unknown_and_cannot_be_restarted_with_new_request(tmp_path):
    executable = server(tmp_path, "missing_thread")
    adapter = CodexAdapter(config(tmp_path, executable))
    reference = {"assistance_id": "assist-1", "generation": 1}

    run = adapter.start(reference, request_id="start-1")
    assert run.status == "unknown"
    assert run.error_code == "thread_shape_invalid"
    assert adapter.start(reference, request_id="start-2").run_id == run.run_id
    with pytest.raises(ValueError, match="unresolved"):
        adapter.start({"assistance_id": "assist-2"}, request_id="start-3")
    messages = [
        json.loads(line) for line in executable.with_suffix(".jsonl").read_text().splitlines()
    ]
    assert len([m for m in messages if m.get("method") == "thread/start"]) == 1


def test_out_of_order_response_cannot_supply_a_future_thread_binding(tmp_path):
    adapter = CodexAdapter(config(tmp_path, server(tmp_path, "early_response")))
    run = adapter.start({"assistance_id": "assist-1"}, request_id="start-1")
    try:
        assert run.status == "ready"
        assert run.thread_id == "thread-synthetic"
    finally:
        adapter.close()


def test_serialized_config_rejects_non_path_values_as_validation_errors(tmp_path):
    value = config(tmp_path, server(tmp_path)).to_dict()
    value["home"] = ["not", "a", "path"]
    with pytest.raises(ValueError, match="configuration"):
        CodexAssistConfig.from_dict(value)


def test_split_utf8_frames_preserve_handshake_and_do_not_inherit_secrets(tmp_path, monkeypatch):
    executable = server(tmp_path, "chunks")
    adapter = CodexAdapter(config(tmp_path, executable))
    monkeypatch.setenv("OPENAI_API_KEY", "must-not-inherit")
    monkeypatch.setenv("CODEX_HOME", "/must-not-inherit")
    run = adapter.start({"assistance_id": "assist-1"}, request_id="start-1")
    assert run.status == "ready"
    adapter.close()
    rows = [json.loads(line) for line in executable.with_suffix(".jsonl").read_text().splitlines()]
    launches = [row for row in rows if "argv" in row]
    assert len(launches) == 2
    assert all("OPENAI_API_KEY" not in row["env_keys"] for row in launches)
    assert all("CODEX_HOME" not in row["env_keys"] for row in launches)
    argv = launches[1]["argv"]
    assert "mcp_servers={}" in argv
    assert "computer_use" in argv and "shell_tool" in argv and "plugins" in argv
    assert "must-not-inherit" not in json.dumps(rows)
    request = next(row for row in rows if row.get("method") == "thread/start")
    assert request["params"]["dynamicTools"] == []
    assert request["params"]["ephemeral"] is True
    assert request["params"]["sandbox"] == "read-only"


def test_server_tool_requests_are_denied_without_executing_a_callback(tmp_path):
    executable = server(tmp_path, "tool_request")
    adapter = CodexAdapter(config(tmp_path, executable))
    run = adapter.start({"assistance_id": "assist-1"}, request_id="start-1")
    assert run.status == "ready"
    adapter.close()
    rows = [json.loads(line) for line in executable.with_suffix(".jsonl").read_text().splitlines()]
    rejection = next(row for row in rows if row.get("id") == "tool-1")
    assert rejection["error"]["code"] == -32000
    assert all(row.get("method") != "turn/start" for row in rows)


@pytest.mark.parametrize(
    ("scenario", "status", "error"),
    [
        ("wrong_version", "failed", "version_unsupported"),
        ("vanish", "failed", "process_start_failed"),
        ("rejected", "failed", "request_rejected"),
        ("missing_init", "unknown", "initialize_shape_invalid"),
        ("malformed", "unknown", "protocol_frame_invalid"),
        ("early_eof", "unknown", "transport_eof"),
        ("partial_eof", "unknown", "partial_frame"),
        ("timeout", "unknown", "response_unknown"),
    ],
)
def test_startup_faults_are_bounded_and_never_grant_execution(tmp_path, scenario, status, error):
    executable = server(tmp_path, scenario)
    value = config(tmp_path, executable).to_dict()
    value.update(request_timeout=1.0, stop_timeout=0.1)
    adapter = CodexAdapter(CodexAssistConfig.from_dict(value))
    run = adapter.start({"assistance_id": "assist-1"}, request_id="start-1")
    assert (run.status, run.error_code) == (status, error)
    assert run.page_write_allowed is False and run.model_turn_allowed is False
    assert "secret sentinel" not in repr(run)
    assert adapter.start({"assistance_id": "assist-1"}, request_id="start-2").run_id == run.run_id
    assert adapter.stop(run.run_id, request_id="stop-1").status == "stopped"


def test_repeated_start_is_idempotent_and_conflicting_input_is_rejected(tmp_path):
    executable = server(tmp_path)
    adapter = CodexAdapter(config(tmp_path, executable))
    run = adapter.start({"assistance_id": "assist-1"}, request_id="start-1")
    assert adapter.start({"assistance_id": "assist-1"}, request_id="start-1") == run
    assert adapter.start({"assistance_id": "assist-1"}, request_id="start-2") == run
    with pytest.raises(ValueError, match="conflicts"):
        adapter.start({"assistance_id": "assist-2"}, request_id="start-1")
    adapter.close()
    rows = [json.loads(line) for line in executable.with_suffix(".jsonl").read_text().splitlines()]
    assert len([r for r in rows if "argv" in r]) == 2


def test_unread_stdin_cannot_block_progress_or_stop_forever(tmp_path):
    executable = server(tmp_path)
    source = executable.read_text()
    source = source.replace(
        "if SCENARIO=='stubborn':\n",
        (
            "        Path(__file__).with_suffix('.pid').write_text(str(os.getpid()))\n"
            "        for i in range(500):\n"
            "            send({'id':str(i)+'x'*10000,'method':'item/tool/call','params':{}})\n"
            "        time.sleep(30)\n"
        )
        + "if SCENARIO=='stubborn':\n",
    )
    executable.write_text(source)
    value = config(tmp_path, executable).to_dict()
    value.update(request_timeout=1.0, stop_timeout=0.1)
    adapter = CodexAdapter(CodexAssistConfig.from_dict(value))
    run = adapter.start({"assistance_id": "assist-1"}, request_id="start-1")
    deadline = time.monotonic() + 2
    while not executable.with_suffix(".pid").exists() and time.monotonic() < deadline:
        time.sleep(0.005)
    time.sleep(0.05)
    results = []
    thread = threading.Thread(target=lambda: results.append(adapter.service_readonly(run.run_id)))
    thread.start()
    thread.join(timeout=3)
    blocked = thread.is_alive()
    if blocked:
        # Terminate only the deliberately stuck fixture to keep a RED run bounded.
        os.kill(int(executable.with_suffix(".pid").read_text()), signal.SIGTERM)
        thread.join(timeout=3)
    adapter.close()
    assert not blocked
    assert results[0].status == "unknown"


@pytest.mark.parametrize(
    "scenario", ["inherited_mcp", "policy_shape_unknown", "policy_rejected", "policy_timeout"]
)
def test_unverified_policy_refuses_metadata_thread_before_any_server_can_start(tmp_path, scenario):
    executable = server(tmp_path, scenario)
    value = config(tmp_path, executable).to_dict()
    value.update(request_timeout=1.0, stop_timeout=0.1)
    adapter = CodexAdapter(CodexAssistConfig.from_dict(value))
    try:
        run = adapter.start({"assistance_id": "assist-1"}, request_id="start-1")
        assert run.status == "failed"
        assert run.error_code == "tool_policy_unverified"
    finally:
        adapter.close()
    rows = [json.loads(line) for line in executable.with_suffix(".jsonl").read_text().splitlines()]
    assert all(row.get("method") != "thread/start" for row in rows)


def test_stop_escalates_only_its_own_stubborn_process(tmp_path):
    executable = server(tmp_path, "stubborn")
    value = config(tmp_path, executable).to_dict()
    value.update(stop_timeout=0.1)
    adapter = CodexAdapter(CodexAssistConfig.from_dict(value))
    unrelated = subprocess.Popen([sys.executable, "-c", "import time;time.sleep(30)"])
    try:
        run = adapter.start({"assistance_id": "assist-1"}, request_id="start-1")
        started = time.monotonic()
        stopped = adapter.stop(run.run_id, request_id="stop-1")
        assert stopped.status == "stopped"
        assert time.monotonic() - started < 2
        assert unrelated.poll() is None
    finally:
        adapter.close()
        unrelated.terminate()
        unrelated.wait(timeout=2)


def test_config_unavailable_executable_is_a_value_error(tmp_path):
    value = config(tmp_path, server(tmp_path)).to_dict()
    value["executable"] = str(tmp_path / "missing")
    with pytest.raises(ValueError, match="configuration"):
        CodexAssistConfig.from_dict(value)


def test_progress_yields_after_a_bounded_batch_instead_of_draining_every_notification(tmp_path):
    executable = server(tmp_path)
    source = executable.read_text().replace(
        "if SCENARIO=='stubborn':\n",
        "        for i in range(500): send({'method':'synthetic/notification','params':{}})\n"
        "        send({'id':None,'result':{}})\n"
        "        Path(__file__).with_suffix('.ready').touch()\n"
        "if SCENARIO=='stubborn':\n",
    )
    executable.write_text(source)
    adapter = CodexAdapter(config(tmp_path, executable))
    try:
        run = adapter.start({"assistance_id": "assist-1"}, request_id="start-1")
        deadline = time.monotonic() + 2
        while not executable.with_suffix(".ready").exists() and time.monotonic() < deadline:
            time.sleep(0.005)
        assert executable.with_suffix(".ready").exists()
        time.sleep(0.1)
        # One read must leave work queued so the Worker can process control commands.
        assert adapter.progress(run.run_id).status == "ready"
        for _ in range(16):
            result = adapter.progress(run.run_id)
            if result.status == "unknown":
                break
        assert result.status == "unknown"
        assert result.error_code == "response_shape_invalid"
    finally:
        adapter.close()
