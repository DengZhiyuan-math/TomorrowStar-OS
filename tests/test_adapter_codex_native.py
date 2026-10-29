"""Native MCP takeover lifecycle against a controlled app-server peer, never a model."""

import hashlib
import json
import os
import sys
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

import pytest

from career_evidence_graph import cua_driver
from career_evidence_graph.application_codex_assist import CodexAdapter, CodexAssistConfig
from career_evidence_graph.application_worker import valid_assistance_report
from career_evidence_graph.validation.hashing import record_digest as digest


def native_case(tmp_path, monkeypatch):
    driver = tmp_path / "native-driver"
    driver.write_text("#!/bin/sh\nexit 0\n")
    driver.chmod(0o700)
    driver_hash = hashlib.sha256(driver.read_bytes()).hexdigest()
    monkeypatch.setattr(cua_driver, "_NATIVE_HANDOFF_DRIVER_SHA256", driver_hash)
    policy = {
        "protocol": "cua-trusted-handoff/v1",
        "driver_sha256": driver_hash,
        "tools": ["get_browser_state", "browser_click", "browser_type", "browser_deliver_material"],
        "type_mode": "insert_text",
    }
    ref = {
        "id": "a" * 32,
        "generation": 1,
        "protocol": "codex-assistance/native/v1",
        "native_policy_digest": digest(policy),
        "page_writes_enabled": True,
        "binding": {
            "application_id": "synthetic-app",
            "page_id": "original-page",
            "document_token": "original-document",
            "step": "https://example.invalid/app",
        },
    }
    document = {
        "frame_id": "original-frame",
        "loader_id": "original-loader",
        "url": ref["binding"]["step"],
    }
    scope = {"target_id": "native-target", "tab_id": "native-tab", "expected_document": document}
    packet = {
        "schema_version": 1,
        "assistance_ref": ref,
        "progress": {"completed": [], "remaining": []},
        "blocker": {"code": "unsupported_control"},
        "pending_actions": [],
        "page_context": {
            "status": "captured",
            "binding": ref["binding"],
            "document": document,
            "data": {"fields": []},
            "native_scope": {
                "target_id": "native-target",
                "tab_id": "native-tab",
                "application_ref_digest": digest(ref),
            },
        },
        "materials": [],
        "next_step": {"kind": "inspect_control_and_continue"},
    }
    peer = tmp_path / "codex-peer"
    peer.write_text(
        f"#!{Path(sys.executable).resolve()}\n"
        + r"""
import json, os, sys, time, tomllib
from pathlib import Path
log=Path(__file__).with_suffix('.jsonl')
settings_path=Path(__file__).with_suffix('.settings')
settings=json.loads(settings_path.read_text()) if settings_path.exists() else {}
def record(value):
    with log.open('a') as out: out.write(json.dumps(value)+'\n')
def send(value):
    print(json.dumps(value),flush=True)
def await_native_grant(native):
    ready=Path(native['args'][-1])
    initial=json.loads(ready.read_text())
    initial.update(status='pending',connection_id='native-connection',peer_pid=os.getpid(),
                   proxy_pid=os.getpid())
    if settings.get('ready_mode')=='world_readable': ready.chmod(0o644)
    elif settings.get('ready_mode') in ('symlink','hardlink'):
        replacement=ready.with_suffix('.replacement')
        ready.rename(replacement)
        if settings['ready_mode']=='symlink': ready.symlink_to(replacement)
        else: os.link(replacement,ready)
    ready.write_text(json.dumps(initial))
    until=time.monotonic()+3
    while not ready.with_suffix('.granted').exists() and time.monotonic()<until:
        time.sleep(.005)
if sys.argv[1:]==['--version']:
    print('codex-cli 0.165.0-alpha.1.2');sys.exit(0)
record({'argv':sys.argv[1:]})
config={}
for n,part in enumerate(sys.argv[:-1]):
    if part=='--config':
        fragment=tomllib.loads(sys.argv[n+1])
        if 'web_search' in fragment: config['web_search']=fragment['web_search']
        if 'mcp_servers' in fragment:
            config.setdefault('mcp_servers',{})
            for name, value in fragment['mcp_servers'].items():
                config.setdefault('mcp_servers',{}).setdefault(name,{}).update(value)
for line in sys.stdin:
    msg=json.loads(line);record(msg)
    method=msg.get('method')
    if method=='initialize':
        send({'id':msg['id'],'result':{'userAgent':'synthetic','codexHome':'synthetic',
              'platformFamily':'unix','platformOs':'macos'}})
    elif method=='config/read':
        if settings.get('force_web_search'): config['web_search']=settings['force_web_search']
        if 'force_mcp_servers' in settings: config['mcp_servers']=settings['force_mcp_servers']
        send({'id':msg['id'],'result':{'config':config,'origins':{}}})
    elif method=='thread/start':
        native=msg['params']['config']['mcp_servers']['cua_takeover']
        if not settings.get('lazy_catalog') and not settings.get('no_native_recipient'):
            await_native_grant(native)
        send({'id':msg['id'],'result':{'thread':{'id':'thread-native'}}})
    elif method=='mcpServerStatus/list':
        if settings.get('lazy_catalog') and not settings.get('no_native_recipient'):
            await_native_grant(native)
        catalog={'data':[{'name':'cua_takeover','runtimeStatus':'connected',
             'authStatus':'unsupported','pluginId':None,'httpOrigin':None,'resources':[],
             'resourceTemplates':[],'tools':{name:{'name':name,'inputSchema':{'type':'object'}}
             for name in (['get_browser_state','browser_click','browser_type',
                           'browser_deliver_material']
                          + settings.get('extra_tools',[]))}}], 'nextCursor':None}
        catalog['data'][0].update(settings.get('catalog_extra',{}))
        if (settings.get('require_thread_catalog')
                and msg['params'].get('serverName')!='cua_takeover'):
            catalog['data'][0].update(
                tools={},toolsError='MCP startup failed: initialize response: connection closed')
        send({'id':msg['id'],'result':catalog})
    elif method=='turn/start':
        if settings.get('lose_turn_ack'): time.sleep(10)
        if settings.get('terminal_before_ack'):
            send({'method':'turn/started','params':{'threadId':'thread-native','turn':{'id':'native-turn','status':'inProgress'}}})
            send({'method':'turn/completed','params':{'threadId':'thread-native','turn':{'id':'native-turn','status':'completed'}}})
        send({'id':msg['id'],'result':{'turn':{'id':'native-turn','status':'inProgress','items':[]}}})
        for value in settings.get('after_ack',[]): send(value)
        if 'after_ack' in settings: record({'sent':'after_ack'})
        if settings.get('terminal_backlog'):
            for _ in range(settings['terminal_backlog']):
                send({'method':'synthetic/notification','params':{}})
            if not settings.get('backlog_only'):
                send({'method':'turn/completed','params':{'threadId':'thread-native',
                      'turn':{'id':'native-turn','status':'completed'}}})
    elif method=='turn/interrupt':
        send({'id':msg['id'],'result':{}})
        send({'method':'turn/completed','params':{'threadId':'thread-native',
             'turn':{'id':'native-turn','status':'interrupted'}}})
"""
    )
    peer.chmod(0o700)
    home, runtime = tmp_path / "home", tmp_path / "runtime"
    home.mkdir()
    runtime.mkdir()
    events = []

    class Native:
        native_session = True
        driver_sha256 = driver_hash
        socket_path = str(tmp_path / "native.sock")
        process = SimpleNamespace(pid=os.getpid(), poll=lambda: None)
        active = 0
        granted = False
        receiver_yielded = True
        revoked = False
        calls = None

        def yield_to(self, ready, **kwargs):
            assert kwargs["scope"] == scope
            assert kwargs["application_ref_digest"] == digest(ref)
            assert kwargs["request_id"] == ready["request_id"]
            assert kwargs["appserver_identity"]["pid"] == ready["proxy_pid"]
            events.append("yield")
            self.granted = self.receiver_yielded
            ready_path = next((runtime / "native-handoffs").rglob("*.json"))
            ready_path.with_suffix(".granted").write_text("granted")
            return {
                "handoff_id": "native-handoff",
                "generation": 1,
                "local_tools_drained": True,
                "yielded": self.receiver_yielded,
            }

        def handoff_status(self, **kwargs):
            return {
                "handoff_id": "native-handoff",
                "generation": 1,
                "phase": "active",
                "revoked": self.revoked,
                "active_calls": self.active,
                "local_tools_drained": self.active == 0,
                "return_ready": self.revoked and self.active == 0,
                "calls": self.calls or [],
            }

        def admit_call(self, call_id, arguments_digest, decision, **kwargs):
            events.append(("admit", call_id, decision))
            for call in self.calls or []:
                if call["call_id"] == call_id:
                    call["status"] = "in_flight" if decision == "allow" else "not_sent"
            return self.handoff_status()

        def revoke_handoff(self, **kwargs):
            events.append("revoke")
            self.revoked = True
            return self.handoff_status()

    native = Native()
    native.driver_executable = str(driver.resolve())
    config = CodexAssistConfig(
        executable=peer, runtime=runtime, home=home, native_assistance_policy=policy
    )
    return config, ref, scope, packet, driver, native, events


def recorded(config):
    return [
        json.loads(line)
        for line in config.executable.with_suffix(".jsonl").read_text().splitlines()
    ]


def test_native_takeover_hands_json_to_verified_native_tool_catalog(tmp_path, monkeypatch):
    config, ref, scope, packet, driver, native, events = native_case(tmp_path, monkeypatch)
    adapter = CodexAdapter(config)
    try:
        run = adapter.start_takeover(
            ref,
            request_id="native-start",
            delivery=packet,
            native_client=native,
            native_scope=scope,
            driver_executable=driver,
            before_yield=lambda intent: events.append("before"),
            after_yield=lambda receipt: events.append("after"),
            pump=lambda: True,
            before_native_call=lambda call: True,
        )
        assert run.status == "ready"
        assert run.page_write_allowed is True and run.model_turn_allowed is True
        assert run.native_turn_id == "native-turn"
        messages = recorded(config)
        argv = messages[0]["argv"]
        assert [
            argv[index + 1]
            for index, argument in enumerate(argv[:-1])
            if argument == "--config" and argv[index + 1].startswith("mcp_servers")
        ] == ["mcp_servers={}"]
        start = next(m for m in messages if m.get("method") == "thread/start")
        assert start["params"]["dynamicTools"] == []
        assert start["params"]["config"]["web_search"] == "disabled"
        ready_path = next((config.runtime / "native-handoffs").rglob("*.json"))
        assert start["params"]["config"]["mcp_servers"] == {
            "cua_takeover": {
                "command": str(driver),
                "args": [
                    "mcp",
                    "--embedded",
                    "--socket",
                    native.socket_path,
                    "--trusted-handoff",
                    str(ready_path),
                ],
                "enabled": True,
                "required": True,
                "startup_timeout_sec": 30,
                "tool_timeout_sec": 15,
                "enabled_tools": [
                    "get_browser_state",
                    "browser_click",
                    "browser_type",
                    "browser_deliver_material",
                ],
                # Without per-tool approve, approvalPolicy "never" refuses every
                # non-read-only call (actual C1 r2); only the four tools are approved.
                "tools": {
                    name: {"approval_mode": "approve"}
                    for name in (
                        "get_browser_state",
                        "browser_click",
                        "browser_type",
                        "browser_deliver_material",
                    )
                },
            }
        }
        turn = next(m for m in messages if m.get("method") == "turn/start")
        assert turn["params"]["input"] == [
            {"type": "text", "text": json.dumps(packet, ensure_ascii=False, allow_nan=False)}
        ]
        assert events[:3] == ["before", "yield", "after"]
        assert next(m for m in messages if m.get("method") == "mcpServerStatus/list")["params"] == {
            "threadId": "thread-native",
            "serverName": "cua_takeover",
            "detail": "full",
        }
        assert not any(m.get("method") == "item/tool/call" for m in messages)
    finally:
        adapter.close()


def test_native_takeover_reuses_the_named_thread_mcp_connection(tmp_path, monkeypatch):
    config, ref, scope, packet, driver, native, events = native_case(tmp_path, monkeypatch)
    # Fixed-CLI D1 observed a fresh connection for unscoped full discovery.
    config.executable.with_suffix(".settings").write_text(
        json.dumps({"require_thread_catalog": True})
    )
    adapter = CodexAdapter(config)
    try:
        run = adapter.start_takeover(
            ref,
            request_id="native-named-catalog",
            delivery=packet,
            native_client=native,
            native_scope=scope,
            driver_executable=driver,
            before_yield=lambda intent: None,
            after_yield=lambda receipt: None,
            before_native_call=lambda call: True,
            pump=lambda: True,
        )
        assert run.status == "ready"
        assert run.model_turn_allowed is True and run.native_turn_id == "native-turn"
    finally:
        adapter.close()


def test_native_model_input_omits_backend_process_identity(tmp_path, monkeypatch):
    config, ref, scope, packet, driver, native, events = native_case(tmp_path, monkeypatch)
    ref["backend_authority"] = {
        "instance_id": "b" * 32,
        "process": {
            "pid": 4242,
            "uid": 501,
            "started_seconds": 1,
            "started_microseconds": 0,
            "executable": "/Users/someone/.local/bin/python3.13",
        },
    }
    packet["page_context"]["native_scope"]["application_ref_digest"] = digest(ref)
    adapter, run = start_case(config, ref, scope, packet, driver, native)
    try:
        assert run.status == "ready"
        turn = next(m for m in recorded(config) if m.get("method") == "turn/start")
        text = turn["params"]["input"][0]["text"]
        model_ref = {key: value for key, value in ref.items() if key != "backend_authority"}
        assert "backend_authority" not in text and "/Users/" not in text
        assert json.loads(text) == packet | {"assistance_ref": model_ref}
    finally:
        adapter.close()


def test_lazy_native_recipient_is_granted_during_catalog_before_the_model_turn(
    tmp_path, monkeypatch
):
    config, ref, scope, packet, driver, native, events = native_case(tmp_path, monkeypatch)
    config.executable.with_suffix(".settings").write_text(json.dumps({"lazy_catalog": True}))
    granted_after = []
    adapter, run = start_case(
        config,
        ref,
        scope,
        packet,
        driver,
        native,
        after_yield=lambda _: granted_after.append(
            [m["method"] for m in recorded(config) if "method" in m]
        ),
    )
    try:
        assert run.status == "ready", run
        assert run.model_turn_allowed is True and run.page_write_allowed is True
        assert granted_after and all(
            methods
            == ["initialize", "initialized", "config/read", "thread/start", "mcpServerStatus/list"]
            for methods in granted_after
        )
        methods = [m["method"] for m in recorded(config) if "method" in m]
        assert methods[-1] == "turn/start"
        assert native.granted
        assert events.count("yield") == 1
    finally:
        adapter.close()


@pytest.mark.parametrize("name", ["cua_takeover", "unrelated_server"])
def test_nonempty_global_mcp_table_stops_before_thread_creation(tmp_path, monkeypatch, name):
    config, ref, scope, packet, driver, native, events = native_case(tmp_path, monkeypatch)
    config.executable.with_suffix(".settings").write_text(
        json.dumps({"force_mcp_servers": {name: {"command": str(driver)}}})
    )
    adapter, run = start_case(config, ref, scope, packet, driver, native)
    try:
        assert run.status == "failed" and run.error_code == "tool_policy_unverified"
        methods = [m["method"] for m in recorded(config) if "method" in m]
        assert methods == ["initialize", "initialized", "config/read"]
        assert not native.granted and events == []
    finally:
        adapter.close()


def test_verified_catalog_without_a_native_grant_never_starts_a_model_turn(tmp_path, monkeypatch):
    config, ref, scope, packet, driver, native, events = native_case(tmp_path, monkeypatch)
    config.executable.with_suffix(".settings").write_text(json.dumps({"no_native_recipient": True}))
    adapter, run = start_case(config, ref, scope, packet, driver, native)
    try:
        assert run.status == "unknown" and run.error_code == "native_handoff_unavailable"
        methods = [m["method"] for m in recorded(config) if "method" in m]
        assert methods[-1] == "mcpServerStatus/list" and "turn/start" not in methods
        assert not native.granted and events == []
        assert not run.page_write_allowed and not run.model_turn_allowed
    finally:
        adapter.close()


@pytest.mark.parametrize(
    "unverified",
    [
        {"extra_tools": ["browser_navigate"]},
        # Driver skill documents are model-readable context outside the four tools.
        {"catalog_extra": {"resources": [{"uri": "skill://cua-driver/SKILL.md", "name": "SKILL"}]}},
        {"catalog_extra": {"resourceTemplates": [{"uriTemplate": "skill://cua-driver/{name}"}]}},
    ],
    ids=["extra_tool", "resource", "resource_template"],
)
def test_unverified_lazy_catalog_revokes_the_grant_without_starting_a_model_turn(
    tmp_path, monkeypatch, unverified
):
    config, ref, scope, packet, driver, native, events = native_case(tmp_path, monkeypatch)
    config.executable.with_suffix(".settings").write_text(
        json.dumps({"lazy_catalog": True} | unverified)
    )
    adapter, run = start_case(config, ref, scope, packet, driver, native)
    try:
        assert run.status == "unknown" and run.error_code == "native_tool_policy_unverified"
        assert native.granted and native.revoked
        assert "yield" in events and "revoke" in events
        assert not any(m.get("method") == "turn/start" for m in recorded(config))
        assert not run.page_write_allowed and not run.model_turn_allowed
    finally:
        adapter.close()


def start_case(
    config,
    ref,
    scope,
    packet,
    driver,
    native,
    *,
    before_native_call=lambda call: True,
    after_yield=lambda receipt: None,
    before_yield=lambda intent: None,
    pump=lambda: True,
):
    adapter = CodexAdapter(config)
    run = adapter.start_takeover(
        ref,
        request_id="native-start",
        delivery=packet,
        native_client=native,
        native_scope=scope,
        driver_executable=driver,
        before_yield=before_yield,
        after_yield=after_yield,
        pump=pump,
        before_native_call=before_native_call,
    )
    return adapter, run


def test_native_call_waits_for_persisted_metadata_before_native_admission(tmp_path, monkeypatch):
    config, ref, scope, packet, driver, native, events = native_case(tmp_path, monkeypatch)
    call = {
        "call_id": "native-call",
        "tool": "browser_type",
        "arguments_digest": "a" * 64,
        "status": "awaiting_host",
        "generation": 1,
        "sequence": 1,
        "mutation": True,
        "semantic_verified": False,
        "scope": scope,
        "native_ref": "field-1",
        "field_hint": {"role": "textbox", "name": "Applicant full name"},
        "text_sha256": "b" * 64,
    }
    native.calls = [call]
    observed = []

    def persist(receipt):
        observed.append(receipt)
        if receipt.get("calls"):
            events.append(("persist", receipt["calls"][0]["status"]))

    def decide(metadata):
        assert observed[-1]["calls"][0] == metadata
        assert metadata["native_ref"] == "field-1"
        assert metadata["field_hint"] == {"role": "textbox", "name": "Applicant full name"}
        events.append("decision")
        return True

    adapter, run = start_case(
        config, ref, scope, packet, driver, native, before_native_call=decide, after_yield=persist
    )
    try:
        assert run.status == "ready"
        assert events.index(("persist", "awaiting_host")) < events.index("decision")
        assert events.index("decision") < events.index(("admit", "native-call", "allow"))
        for _ in range(2):
            adapter.progress(run.run_id)
        assert events.count("decision") == 1
        assert events.count(("admit", "native-call", "allow")) == 1
        assert all(
            "text" not in row and "arguments" not in row
            for receipt in observed
            for row in receipt.get("calls", [])
        )
    finally:
        adapter.close()


def test_stop_waits_for_native_effect_drain_after_appserver_has_exited(tmp_path, monkeypatch):
    config, ref, scope, packet, driver, native, events = native_case(tmp_path, monkeypatch)
    adapter, run = start_case(config, ref, scope, packet, driver, native)
    try:
        native.active = 1
        stopped = adapter.stop(run.run_id, request_id="stop-with-active-native-call")
        assert stopped.process_stopped is True
        assert stopped.status == "unknown" and stopped.stop_status == "unknown"
        assert stopped.local_tools_drained is False
        native.active = 0
        completed = adapter.progress(run.run_id)
        assert completed.status == "stopped" and completed.stop_status == "stopped"
        assert completed.local_tools_drained is True
        assert completed.native_handoff["return_ready"] is True
    finally:
        adapter.close()


@pytest.mark.parametrize("decision", [False, "raise"])
def test_denied_or_unpersisted_native_intent_never_allows_a_write(tmp_path, monkeypatch, decision):
    config, ref, scope, packet, driver, native, events = native_case(tmp_path, monkeypatch)
    native.calls = [
        {
            "call_id": "native-call",
            "tool": "browser_click",
            "arguments_digest": "a" * 64,
            "status": "awaiting_host",
            "generation": 1,
            "sequence": 1,
            "mutation": True,
            "semantic_verified": False,
            "scope": scope,
            "native_ref": "control-1",
            "field_hint": {"role": "button", "name": "Expand details"},
        }
    ]

    def decide(call):
        if decision == "raise":
            raise OSError("synthetic persistence failure")
        return False

    adapter, run = start_case(config, ref, scope, packet, driver, native, before_native_call=decide)
    try:
        assert run.status == "unknown" and native.revoked
        if decision == "raise":
            assert run.error_code == "native_receipt_persistence_failed"
            assert ("admit", "native-call", "deny") not in events
        else:
            assert ("admit", "native-call", "deny") in events
        assert ("admit", "native-call", "allow") not in events
        assert not any(m.get("method") == "turn/start" for m in recorded(config))
    finally:
        adapter.close()


@pytest.mark.parametrize("stage", ["intent", "receipt", "observed"])
def test_failed_handover_persistence_blocks_the_turn_and_revokes_any_grant(
    tmp_path, monkeypatch, stage
):
    config, ref, scope, packet, driver, native, events = native_case(tmp_path, monkeypatch)

    def before(intent):
        if stage == "intent":
            raise OSError("synthetic intent persistence failure")

    def after(receipt):
        if stage == "receipt" or stage == "observed" and "phase" in receipt:
            raise OSError("synthetic receipt persistence failure")

    adapter, run = start_case(
        config, ref, scope, packet, driver, native, before_yield=before, after_yield=after
    )
    try:
        assert run.status == "unknown"
        assert native.granted is (stage != "intent")
        assert native.revoked is (stage != "intent")
        assert not any(m.get("method") == "turn/start" for m in recorded(config))
    finally:
        adapter.close()


def test_observed_receipt_save_failure_during_completed_revoke_stays_unknown(tmp_path, monkeypatch):
    config, ref, scope, packet, driver, native, events = native_case(tmp_path, monkeypatch)
    durable, failures = [], []

    def persist(receipt):
        if any(
            call["mutation"] and call["status"] == "observed" for call in receipt.get("calls", [])
        ):
            failures.append(deepcopy(receipt))
            raise OSError("synthetic observed receipt save failure")
        durable.append(deepcopy(receipt))

    adapter, run = start_case(config, ref, scope, packet, driver, native, after_yield=persist)
    try:
        native.calls = [
            {
                "call_id": "native-write",
                "tool": "browser_type",
                "arguments_digest": "a" * 64,
                "status": "awaiting_host",
                "generation": 1,
                "sequence": 1,
                "mutation": True,
                "semantic_verified": False,
                "scope": scope,
                "native_ref": "field-1",
                "field_hint": {"role": "textbox", "name": "Email"},
                "text_sha256": "b" * 64,
            }
        ]
        adapter.progress(run.run_id)
        assert events.count(("admit", "native-write", "allow")) == 1
        saved = deepcopy(durable)
        revoke = native.revoke_handoff

        def completed_receipt(**kwargs):
            native.calls[0]["status"] = "observed"
            return revoke(**kwargs)

        monkeypatch.setattr(native, "revoke_handoff", completed_receipt)
        # The final native receipt is first read while processing the real
        # protocol terminal, exactly as in the retained native save-after run.
        adapter._runs[run.run_id].events.put_nowait(
            {
                "method": "turn/completed",
                "params": {
                    "threadId": "thread-native",
                    "turn": {"id": "native-turn", "status": "completed"},
                },
            }
        )
        current = adapter.progress(run.run_id)
        assert failures and failures[0]["calls"][0]["status"] == "observed"
        assert current.error_code == "native_receipt_persistence_failed"
        assert current.status == "unknown" and current.native_turn_status == "completed"
        assert (
            current.tools_revoked
            and not current.page_write_allowed
            and not current.model_turn_allowed
        )
        for current in (
            adapter.stop(run.run_id, request_id="stop-after-save-failure"),
            adapter.progress(run.run_id),
            adapter.stop(run.run_id, request_id="repeat-stop-after-save-failure"),
        ):
            assert current.status == "unknown" and current.native_turn_status == "completed"
            assert current.error_code == "native_receipt_persistence_failed"
            assert current.stop_status == "stopped" and current.process_stopped
            assert current.local_tools_drained
            assert current.native_handoff["calls"][0]["status"] == "observed"
        assert durable == saved and len(failures) == 1
        assert events.count(("admit", "native-write", "allow")) == 1

        status = native.handoff_status

        def transport_failed(**kwargs):
            raise OSError("synthetic later control transport failure")

        monkeypatch.setattr(native, "handoff_status", transport_failed)
        uncertain = adapter.stop(run.run_id, request_id="later-control-failure")
        assert uncertain.error_code == "native_receipt_persistence_failed"
        assert uncertain.status == "unknown" and uncertain.native_handoff is None
        assert not uncertain.local_tools_drained
        monkeypatch.setattr(native, "handoff_status", status)

        # A new native ref/call and a new request id cannot reopen this run.
        native.calls.append(
            {
                **native.calls[0],
                "call_id": "fresh-call",
                "native_ref": "field-2",
                "sequence": 2,
                "status": "awaiting_host",
            }
        )
        assert adapter.progress(run.run_id).error_code == "native_receipt_persistence_failed"
        assert ("admit", "fresh-call", "allow") not in events
        same = adapter.start_takeover(
            ref,
            request_id="fresh-request",
            delivery=packet,
            native_client=native,
            native_scope=scope,
            driver_executable=driver,
            before_yield=lambda _: None,
            after_yield=persist,
            pump=lambda: True,
            before_native_call=lambda _: True,
        )
        assert same.run_id == run.run_id and same.status == "unknown"
        changed_ref, changed_packet = deepcopy(ref), deepcopy(packet)
        changed_ref["generation"] += 1
        changed_packet["assistance_ref"] = changed_ref
        changed_packet["page_context"]["native_scope"]["application_ref_digest"] = digest(
            changed_ref
        )
        with pytest.raises(ValueError, match="already has an unresolved run"):
            adapter.start_takeover(
                changed_ref,
                request_id="fresh-reference",
                delivery=changed_packet,
                native_client=native,
                native_scope=scope,
                driver_executable=driver,
                before_yield=lambda _: None,
                after_yield=persist,
                pump=lambda: True,
                before_native_call=lambda _: True,
            )
        assert len([m for m in recorded(config) if m.get("method") == "turn/start"]) == 1
        assert adapter._runs[run.run_id].native["failed_receipt"] == failures[0]
        assert durable == saved and len(failures) == 1
    finally:
        adapter.close()


def test_extra_native_tool_stops_before_any_model_turn(tmp_path, monkeypatch):
    config, ref, scope, packet, driver, native, events = native_case(tmp_path, monkeypatch)
    config.executable.with_suffix(".settings").write_text(
        json.dumps({"extra_tools": ["browser_navigate"]})
    )
    adapter, run = start_case(config, ref, scope, packet, driver, native)
    try:
        assert run.status == "unknown" and run.error_code == "native_tool_policy_unverified"
        assert native.revoked
        assert not any(m.get("method") == "turn/start" for m in recorded(config))
    finally:
        adapter.close()


def test_native_terminal_before_start_ack_revokes_without_regressing_turn_status(
    tmp_path, monkeypatch
):
    config, ref, scope, packet, driver, native, events = native_case(tmp_path, monkeypatch)
    config.executable.with_suffix(".settings").write_text(json.dumps({"terminal_before_ack": True}))
    adapter, run = start_case(config, ref, scope, packet, driver, native)
    try:
        assert run.native_turn_status == "completed"
        assert run.tools_revoked and native.revoked
        assert not run.page_write_allowed and not run.model_turn_allowed
        assert run.status == "ready"  # Model completion is not application completion.
    finally:
        adapter.close()


def test_lost_native_turn_ack_stays_unknown_without_starting_a_second_run(tmp_path, monkeypatch):
    from dataclasses import replace

    config, ref, scope, packet, driver, native, events = native_case(tmp_path, monkeypatch)
    config = replace(config, request_timeout=0.25)
    config.executable.with_suffix(".settings").write_text(json.dumps({"lose_turn_ack": True}))
    adapter, run = start_case(config, ref, scope, packet, driver, native)
    try:
        assert run.status == "unknown" and run.tools_revoked and native.revoked
        same = adapter.start_takeover(
            ref,
            request_id="different-retry-id",
            delivery=packet,
            native_client=native,
            native_scope=scope,
            driver_executable=driver,
            before_yield=lambda intent: None,
            after_yield=lambda receipt: None,
            pump=lambda: True,
            before_native_call=lambda call: True,
        )
        assert same.run_id == run.run_id and same.status == "unknown"
        assert sum(m.get("method") == "turn/start" for m in recorded(config)) == 1
    finally:
        adapter.close()


def test_repeated_native_metadata_poll_does_not_repeat_journal_writes(tmp_path, monkeypatch):
    config, ref, scope, packet, driver, native, events = native_case(tmp_path, monkeypatch)
    receipts = []
    adapter, run = start_case(
        config, ref, scope, packet, driver, native, after_yield=receipts.append
    )
    try:
        first = len(receipts)
        for _ in range(4):
            adapter.progress(run.run_id)
        assert len(receipts) == first
        assert receipts[-1]["phase"] == "active"
    finally:
        adapter.close()


def test_source_changes_before_dispatch_deny_native_admission(tmp_path, monkeypatch):
    config, ref, scope, packet, driver, native, events = native_case(tmp_path, monkeypatch)
    source_valid = [True]
    adapter, run = start_case(
        config, ref, scope, packet, driver, native, pump=lambda: source_valid[0]
    )
    try:
        native.calls = [
            {
                "call_id": "changed-source",
                "tool": "browser_click",
                "arguments_digest": "a" * 64,
                "status": "awaiting_host",
                "generation": 1,
                "sequence": 1,
                "mutation": True,
                "semantic_verified": False,
                "scope": scope,
                "native_ref": "control-1",
                "field_hint": {"role": "button", "name": "Expand details"},
            }
        ]
        # A failed caller preflight must not leave the already granted session writable.
        source_valid[0] = False
        result = adapter.progress(run.run_id)
        assert result.status == "unknown" and result.tools_revoked and native.revoked
        assert not any(isinstance(event, tuple) and event[-1] == "allow" for event in events)
    finally:
        adapter.close()


@pytest.mark.parametrize("mode", ["symlink", "hardlink", "world_readable"])
def test_private_rendezvous_replacement_is_refused_before_yield(tmp_path, monkeypatch, mode):
    config, ref, scope, packet, driver, native, events = native_case(tmp_path, monkeypatch)
    config.executable.with_suffix(".settings").write_text(json.dumps({"ready_mode": mode}))
    adapter, run = start_case(config, ref, scope, packet, driver, native)
    try:
        assert run.status == "unknown" and native.granted is False
        assert "yield" not in events
        assert not any(m.get("method") == "turn/start" for m in recorded(config))
    finally:
        adapter.close()


def test_unknown_native_effect_revokes_before_admitting_any_later_call(tmp_path, monkeypatch):
    config, ref, scope, packet, driver, native, events = native_case(tmp_path, monkeypatch)
    adapter, run = start_case(config, ref, scope, packet, driver, native)
    try:
        native.calls = [
            {
                "call_id": "unknown-effect",
                "tool": "browser_click",
                "arguments_digest": "c" * 64,
                "status": "unknown",
                "generation": 1,
                "sequence": 1,
                "mutation": True,
                "semantic_verified": False,
                "scope": scope,
                "native_ref": "control-1",
                "field_hint": {"role": "button", "name": "Expand details"},
            },
            {
                "call_id": "later-call",
                "tool": "browser_click",
                "arguments_digest": "d" * 64,
                "status": "awaiting_host",
                "generation": 1,
                "sequence": 2,
                "mutation": True,
                "semantic_verified": False,
                "scope": scope,
                "native_ref": "control-2",
                "field_hint": {"role": "button", "name": "Expand section"},
            },
        ]
        result = adapter.progress(run.run_id)
        assert result.status == "unknown" and native.revoked
        assert ("admit", "later-call", "allow") not in events
    finally:
        adapter.close()


@pytest.mark.parametrize("change", ["old_protocol", "policy_digest", "scope", "host_driver"])
def test_native_takeover_refuses_an_unbound_or_legacy_reference_before_launch(
    tmp_path, monkeypatch, change
):
    config, ref, scope, packet, driver, native, events = native_case(tmp_path, monkeypatch)
    if change == "old_protocol":
        ref["protocol"] = "codex-assistance/v1"
    elif change == "policy_digest":
        ref["native_policy_digest"] = "0" * 64
    elif change == "scope":
        scope["tab_id"] = "different-tab"
    else:
        native.driver_executable = None
    adapter = CodexAdapter(config)
    with pytest.raises(ValueError):
        adapter.start_takeover(
            ref,
            request_id="refused",
            delivery=packet,
            native_client=native,
            native_scope=scope,
            driver_executable=driver,
            before_yield=lambda intent: None,
            after_yield=lambda receipt: None,
            pump=lambda: True,
            before_native_call=lambda call: True,
        )
    assert not config.executable.with_suffix(".jsonl").exists()
    assert events == []


def test_native_policy_configuration_roundtrips_without_sharing_mutable_tools(
    tmp_path, monkeypatch
):
    config, ref, scope, packet, driver, native, events = native_case(tmp_path, monkeypatch)
    encoded = config.to_dict()
    assert CodexAssistConfig.from_dict(encoded) == config
    encoded["native_assistance_policy"]["tools"].append("browser_navigate")
    assert config.native_assistance_policy["tools"] == [
        "get_browser_state",
        "browser_click",
        "browser_type",
        "browser_deliver_material",
    ]


def test_native_web_search_policy_is_verified_before_thread_creation(tmp_path, monkeypatch):
    config, ref, scope, packet, driver, native, events = native_case(tmp_path, monkeypatch)
    config.executable.with_suffix(".settings").write_text(json.dumps({"force_web_search": "live"}))
    adapter, run = start_case(config, ref, scope, packet, driver, native)
    try:
        assert run.error_code == "tool_policy_unverified"
        assert not any(message.get("method") == "thread/start" for message in recorded(config))
        assert not native.granted
    finally:
        adapter.close()


@pytest.mark.parametrize("flag", ["handoff_transition_inflight", "control_inflight"])
def test_inflight_native_control_skips_reentrant_status_and_reports_undrained(
    tmp_path, monkeypatch, flag
):
    config, ref, scope, packet, driver, native, events = native_case(tmp_path, monkeypatch)
    adapter, run = start_case(config, ref, scope, packet, driver, native)
    original_status = native.handoff_status

    def unexpected_status(**kwargs):
        pytest.fail("reentrant native control query")

    try:
        setattr(native, flag, True)
        native.handoff_status = unexpected_status
        current = adapter.progress(run.run_id)
        assert current.status == "ready"
        assert current.local_tools_drained is False
        assert current.page_write_allowed is False and current.native_handoff is None
        setattr(native, flag, False)
        native.handoff_status = original_status
        recovered = adapter.progress(run.run_id)
        assert recovered.page_write_allowed and recovered.local_tools_drained
    finally:
        setattr(native, flag, False)
        native.handoff_status = original_status
        adapter.close()


def test_native_admission_waits_for_backlogged_terminal_before_persisting_intent(
    tmp_path, monkeypatch
):
    import time

    config, ref, scope, packet, driver, native, events = native_case(tmp_path, monkeypatch)
    config.executable.with_suffix(".settings").write_text(json.dumps({"terminal_backlog": 200}))
    adapter, run = start_case(
        config,
        ref,
        scope,
        packet,
        driver,
        native,
        before_native_call=lambda call: events.append("decision") or True,
    )
    try:
        # Let the controlled peer finish its batch before asking for admission.
        time.sleep(0.05)
        native.calls = [
            {
                "call_id": "backlogged-call",
                "tool": "browser_click",
                "arguments_digest": "a" * 64,
                "status": "awaiting_host",
                "generation": 1,
                "sequence": 1,
                "mutation": True,
                "semantic_verified": False,
                "scope": scope,
                "native_ref": "control-1",
                "field_hint": {"role": "button", "name": "Expand details"},
            }
        ]
        for _ in range(5):
            current = adapter.progress(run.run_id)
            assert "decision" not in events
            assert ("admit", "backlogged-call", "allow") not in events
            if current.native_turn_status == "completed":
                break
        assert current.native_turn_status == "completed" and current.tools_revoked
        assert native.revoked
    finally:
        adapter.close()


def test_native_admission_does_not_pump_a_fact_correction_after_final_validation(
    tmp_path, monkeypatch
):
    config, ref, scope, packet, driver, native, events = native_case(tmp_path, monkeypatch)
    saved_fact = ["confirmed answer"]
    final_validation = [False]

    def owner_pump():
        if final_validation[0]:
            saved_fact[0] = "corrected answer"
        return True

    def persist_and_validate(call):
        allowed = saved_fact[0] == "confirmed answer"
        final_validation[0] = True
        return allowed

    adapter, run = start_case(
        config,
        ref,
        scope,
        packet,
        driver,
        native,
        pump=owner_pump,
        before_native_call=persist_and_validate,
    )
    try:
        native.calls = [
            {
                "call_id": "send-race",
                "tool": "browser_click",
                "arguments_digest": "a" * 64,
                "status": "awaiting_host",
                "generation": 1,
                "sequence": 1,
                "mutation": True,
                "semantic_verified": False,
                "scope": scope,
                "native_ref": "control-1",
                "field_hint": {"role": "button", "name": "Expand details"},
            }
        ]
        adapter.progress(run.run_id)
        assert not (
            saved_fact[0] == "corrected answer" and ("admit", "send-race", "allow") in events
        )
    finally:
        adapter.close()


def test_native_admission_final_callback_denies_a_pump_time_saved_fact_correction(
    tmp_path, monkeypatch
):
    config, ref, scope, packet, driver, native, events = native_case(tmp_path, monkeypatch)
    saved_fact = ["confirmed answer"]
    pending = [False]

    def owner_pump():
        if pending[0]:
            saved_fact[0] = "corrected answer"
        return True

    def observe_status(receipt):
        pending[0] = any(row["status"] == "awaiting_host" for row in receipt.get("calls", []))

    adapter, run = start_case(
        config,
        ref,
        scope,
        packet,
        driver,
        native,
        pump=owner_pump,
        after_yield=observe_status,
        before_native_call=lambda call: saved_fact[0] == "confirmed answer",
    )
    try:
        native.calls = [
            {
                "call_id": "corrected-fact",
                "tool": "browser_click",
                "arguments_digest": "a" * 64,
                "status": "awaiting_host",
                "generation": 1,
                "sequence": 1,
                "mutation": True,
                "semantic_verified": False,
                "scope": scope,
                "native_ref": "control-1",
                "field_hint": {"role": "button", "name": "Expand details"},
            }
        ]
        current = adapter.progress(run.run_id)
        assert saved_fact[0] == "corrected answer"
        assert current.status == "unknown" and current.tools_revoked and native.revoked
        assert ("admit", "corrected-fact", "deny") in events
        assert ("admit", "corrected-fact", "allow") not in events
    finally:
        adapter.close()


def test_deferred_native_admission_can_continue_once_backlog_is_drained(tmp_path, monkeypatch):
    import time

    config, ref, scope, packet, driver, native, events = native_case(tmp_path, monkeypatch)
    config.executable.with_suffix(".settings").write_text(
        json.dumps({"terminal_backlog": 200, "backlog_only": True})
    )
    adapter, run = start_case(config, ref, scope, packet, driver, native)
    try:
        time.sleep(0.05)
        native.calls = [
            {
                "call_id": "deferred-call",
                "tool": "browser_click",
                "arguments_digest": "a" * 64,
                "status": "awaiting_host",
                "generation": 1,
                "sequence": 1,
                "mutation": True,
                "semantic_verified": False,
                "scope": scope,
                "native_ref": "control-1",
                "field_hint": {"role": "button", "name": "Expand details"},
            }
        ]
        adapter.progress(run.run_id)
        assert ("admit", "deferred-call", "allow") not in events
        for _ in range(5):
            current = adapter.progress(run.run_id)
            if ("admit", "deferred-call", "allow") in events:
                break
        assert current.status == "ready" and not current.tools_revoked
        assert events.count(("admit", "deferred-call", "allow")) == 1
    finally:
        adapter.close()


def test_terminal_queued_during_durable_callback_defers_native_admission(tmp_path, monkeypatch):
    config, ref, scope, packet, driver, native, events = native_case(tmp_path, monkeypatch)

    def persist_intent(call):
        events.append("persisted-intent")
        # Inject the reader frame at this exact scheduling boundary, without a timing race.
        adapter._runs[run.run_id].events.put_nowait(
            {
                "method": "turn/completed",
                "params": {
                    "threadId": "thread-native",
                    "turn": {"id": "native-turn", "status": "completed"},
                },
            }
        )
        return True

    adapter, run = start_case(
        config, ref, scope, packet, driver, native, before_native_call=persist_intent
    )
    try:
        native.calls = [
            {
                "call_id": "callback-race",
                "tool": "browser_click",
                "arguments_digest": "a" * 64,
                "status": "awaiting_host",
                "generation": 1,
                "sequence": 1,
                "mutation": True,
                "semantic_verified": False,
                "scope": scope,
                "native_ref": "control-1",
                "field_hint": {"role": "button", "name": "Expand details"},
            }
        ]
        current = adapter.progress(run.run_id)
        assert events.count("persisted-intent") == 1
        assert ("admit", "callback-race", "allow") not in events
        assert current.native_turn_status == "completed" and current.tools_revoked
        assert native.revoked
        assert native.calls[0]["status"] == "awaiting_host"
    finally:
        adapter.close()


def test_false_native_yield_never_grants_or_starts_a_model_turn(tmp_path, monkeypatch):
    config, ref, scope, packet, driver, native, events = native_case(tmp_path, monkeypatch)
    native.receiver_yielded = False
    receipts = []
    adapter, run = start_case(
        config, ref, scope, packet, driver, native, after_yield=receipts.append
    )
    try:
        assert run.status == "unknown"
        assert not run.page_write_allowed and not run.model_turn_allowed
        assert native.revoked
        assert not any(message.get("method") == "turn/start" for message in recorded(config))
        assert receipts and all("phase" in receipt for receipt in receipts)
        assert receipts[-1]["revoked"] is True
        assert "host_return_credential" not in json.dumps(receipts)
        assert run.native_handoff["return_ready"] is True
    finally:
        adapter.close()


def agent_message(text, *, thread="thread-native", turn="native-turn", kind="agentMessage"):
    # Shape checked against `codex app-server generate-json-schema` (0.165.0-alpha.1.2):
    # ItemCompletedNotification {threadId, turnId, completedAtMs, item: AgentMessageThreadItem}.
    return {
        "method": "item/completed",
        "params": {
            "threadId": thread,
            "turnId": turn,
            "completedAtMs": 0,
            "item": {"type": kind, "id": "item-1", "text": text, "phase": "final_answer"},
        },
    }


def turn_completed(status="completed"):
    return {
        "method": "turn/completed",
        "params": {"threadId": "thread-native", "turn": {"id": "native-turn", "status": status}},
    }


def settle(adapter, run, config):
    import time

    deadline = time.monotonic() + 3
    while not any(m.get("sent") == "after_ack" for m in recorded(config)):
        assert time.monotonic() < deadline
        time.sleep(0.01)
    quiet_until = time.monotonic() + 0.3
    while time.monotonic() < quiet_until:
        current = adapter.progress(run.run_id)
        time.sleep(0.02)
    return current


def report_case(tmp_path, monkeypatch, after_ack):
    config, ref, scope, packet, driver, native, events = native_case(tmp_path, monkeypatch)
    config.executable.with_suffix(".settings").write_text(json.dumps({"after_ack": after_ack}))
    adapter, run = start_case(config, ref, scope, packet, driver, native)
    return config, adapter, run


CLAIMED = {
    "status": "blocked_segment_resolved",
    "summary": "已选择 Country 下拉框中的 Switzerland",
    "unresolved_action_ids": [],
    "fields": [{"field_id": "country", "state": "filled"}],
    "next_step": {"kind": "return_to_script", "field_id": "phone"},
}


# Strict structured outputs (provider "Supported schemas"): every object closes its
# properties and requires all of them; optional values are nullable; strings take
# only pattern/format. A real C1 turn failed with 400 invalid_json_schema otherwise.
STRICT_KEYWORDS = {
    "type",
    "properties",
    "required",
    "additionalProperties",
    "items",
    "enum",
    "minItems",
    "maxItems",
    "pattern",
    "format",
    "description",
    "anyOf",
}


def assert_strict_output_schema(schema, *, root=True):
    assert set(schema) <= STRICT_KEYWORDS, set(schema) - STRICT_KEYWORDS
    assert ("type" in schema) != ("anyOf" in schema), schema
    if root:
        assert schema["type"] == "object"
    for option in schema.get("anyOf", ()):
        assert_strict_output_schema(option, root=False)
    if "properties" in schema:
        # Only scalars use a type list; a nullable object is an anyOf with null.
        assert schema["type"] == "object"
        assert schema["additionalProperties"] is False
        assert set(schema["required"]) == set(schema["properties"])
        for value in schema["properties"].values():
            assert_strict_output_schema(value, root=False)
    if "items" in schema:
        assert_strict_output_schema(schema["items"], root=False)


def test_native_final_report_is_bound_to_the_active_turn(tmp_path, monkeypatch):
    other = dict(CLAIMED, summary="other")
    config, adapter, run = report_case(
        tmp_path,
        monkeypatch,
        [
            agent_message(json.dumps(other), thread="other-thread"),
            agent_message(json.dumps(other), turn="other-turn"),
            agent_message(json.dumps(other), kind="reasoning"),
            agent_message(json.dumps(CLAIMED)),
            turn_completed(),
        ],
    )
    try:
        assert run.report is None
        turn = next(m for m in recorded(config) if m.get("method") == "turn/start")
        schema = turn["params"]["outputSchema"]
        assert {"fields", "next_step"} <= set(schema["properties"])
        assert_strict_output_schema(schema)
        thread = next(m for m in recorded(config) if m.get("method") == "thread/start")
        instructions = thread["params"]["developerInstructions"]
        assert "next_step" in instructions and "null" in instructions
        assert "2000" in instructions and "128" in instructions
        current = settle(adapter, run, config)
        assert current.native_turn_status == "completed"
        report = current.report
        assert set(report) == {
            "protocol",
            "request_id",
            "native_turn_id",
            "received_at",
            "claimed",
            "claimed_sha256",
        }
        assert report["protocol"] == "assistance-report/v1"
        assert report["request_id"] == "report-" + run.run_id
        assert report["native_turn_id"] == "native-turn"
        assert isinstance(report["received_at"], float)
        assert report["claimed"] == CLAIMED
        canonical = json.dumps(CLAIMED, sort_keys=True, separators=(",", ":"))
        assert report["claimed_sha256"] == hashlib.sha256(canonical.encode()).hexdigest()
    finally:
        adapter.close()


def test_success_prose_or_schema_violation_is_not_a_report(tmp_path, monkeypatch):
    config, adapter, run = report_case(
        tmp_path,
        monkeypatch,
        [
            agent_message("Done: I selected Switzerland."),
            agent_message("{" + json.dumps(CLAIMED)),
            agent_message(json.dumps([CLAIMED])),
            agent_message(json.dumps(dict(CLAIMED, status="submitted"))),
            agent_message(json.dumps(dict(CLAIMED, extra=True))),
            agent_message(json.dumps({k: v for k, v in CLAIMED.items() if k != "summary"})),
            agent_message(json.dumps(dict(CLAIMED, summary="x" * 2001))),
            agent_message(json.dumps(dict(CLAIMED, fields=[{"field_id": "country"}]))),
            agent_message(
                json.dumps(dict(CLAIMED, next_step={"kind": "return_to_script", "x": 1}))
            ),
            agent_message(json.dumps(dict(CLAIMED, unresolved_action_ids=[1]))),
            agent_message(json.dumps({k: v for k, v in CLAIMED.items() if k != "next_step"})),
            agent_message(json.dumps({k: v for k, v in CLAIMED.items() if k != "fields"})),
        ],
    )
    try:
        current = settle(adapter, run, config)
        assert current.native_turn_status == "running" and current.report is None
        stopped = adapter.stop(run.run_id, request_id="stop-after-prose")
        assert stopped.status == "stopped" and stopped.stop_status == "stopped"
        assert stopped.local_tools_drained is True and stopped.process_stopped is True
        assert stopped.native_turn_status == "interrupted"
        assert stopped.report is None
    finally:
        adapter.close()


@pytest.mark.parametrize(
    "next_step", [None, {"kind": "complete_remaining_fields", "field_id": None}]
)
def test_strict_report_without_a_next_step_or_fields_is_a_report(tmp_path, monkeypatch, next_step):
    claimed = dict(CLAIMED, status="ready_for_review", fields=[], next_step=next_step)
    config, adapter, run = report_case(
        tmp_path, monkeypatch, [agent_message(json.dumps(claimed)), turn_completed()]
    )
    try:
        report = settle(adapter, run, config).report
        assert report["claimed"] == claimed
        assert valid_assistance_report(report)
    finally:
        adapter.close()


def test_report_after_terminal_does_not_replace_the_final_report(tmp_path, monkeypatch):
    final = dict(CLAIMED, status="ready_for_review", summary="final")
    config, adapter, run = report_case(
        tmp_path,
        monkeypatch,
        [
            agent_message(json.dumps(CLAIMED)),
            agent_message(json.dumps(final)),
            agent_message("trailing prose"),
            turn_completed(),
            agent_message(json.dumps(dict(CLAIMED, summary="late"))),
        ],
    )
    try:
        current = settle(adapter, run, config)
        assert current.native_turn_status == "completed"
        assert current.report["claimed"] == final
        stopped = adapter.stop(run.run_id, request_id="stop-after-terminal")
        assert stopped.status == "stopped" and stopped.report["claimed"] == final
    finally:
        adapter.close()


def pending_intent_row(action_id="script-attempt", **changes):
    """The Worker's delivery row for a saved script intent without a verified result."""
    return {
        "action_id": action_id,
        "kind": "fill",
        "field_id": "hosted-3",
        "scope": {"run_id": "run", "page_id": "original-page"},
        "source_ref": {"record": "intent"},
        "status": "unknown",
        "reason": "saved_intent_without_verified_result",
    } | changes


def test_native_takeover_carries_only_the_dispatched_pending_intent(tmp_path, monkeypatch):
    config, ref, scope, packet, driver, native, events = native_case(tmp_path, monkeypatch)
    packet["pending_actions"] = [pending_intent_row()]
    packet["next_step"] = {"kind": "reconcile_pending_actions", "field_id": "hosted-3"}
    adapter = CodexAdapter(config)
    try:
        run = adapter.start_takeover(
            ref,
            request_id="native-start",
            delivery=packet,
            native_client=native,
            native_scope=scope,
            driver_executable=driver,
            before_yield=lambda intent: events.append("before"),
            after_yield=lambda receipt: events.append("after"),
            pump=lambda: True,
            before_native_call=lambda call: True,
            pending_action_id="script-attempt",
        )
        assert run.status == "ready" and run.page_write_allowed is True
        turn = next(m for m in recorded(config) if m.get("method") == "turn/start")
        # The pending intent reaches Codex unchanged, for readback reconciliation.
        assert json.loads(turn["params"]["input"][0]["text"])["pending_actions"] == [
            pending_intent_row()
        ]
    finally:
        adapter.close()


@pytest.mark.parametrize(
    ("rows", "expected"),
    [
        ([pending_intent_row()], None),
        ([pending_intent_row()], "other-attempt"),
        ([pending_intent_row(), pending_intent_row("second-attempt")], "script-attempt"),
        ([pending_intent_row(source_ref={"record": "observations", "index": 3})], "script-attempt"),
        (
            [
                pending_intent_row(
                    "native:earlier-request",
                    kind="native_handoff",
                    source_ref={"record": "native_handoff_runs", "index": 0},
                )
            ],
            "native:earlier-request",
        ),
        ([pending_intent_row(status="verified")], "script-attempt"),
    ],
    ids=["no_dispatch_ref", "other_intent", "additional", "observation", "native", "not_unknown"],
)
def test_native_takeover_refuses_any_other_pending_action_before_launch(
    tmp_path, monkeypatch, rows, expected
):
    config, ref, scope, packet, driver, native, events = native_case(tmp_path, monkeypatch)
    packet["pending_actions"] = rows
    adapter = CodexAdapter(config)
    with pytest.raises(ValueError, match="Unresolved Worker actions"):
        adapter.start_takeover(
            ref,
            request_id="refused",
            delivery=packet,
            native_client=native,
            native_scope=scope,
            driver_executable=driver,
            before_yield=lambda intent: None,
            after_yield=lambda receipt: None,
            pump=lambda: True,
            before_native_call=lambda call: True,
            pending_action_id=expected,
        )
    assert not config.executable.with_suffix(".jsonl").exists()
    assert events == []


def native_row(call_id, status, generation, scope, sequence=1, tool="browser_type"):
    return {
        "call_id": call_id,
        "tool": tool,
        "arguments_digest": "e" * 64,
        "status": status,
        "generation": generation,
        "sequence": sequence,
        "mutation": tool != "get_browser_state",
        "semantic_verified": False,
        "scope": scope,
        **(
            {"native_ref": f"ref-{call_id}", "field_hint": {"role": "combobox", "name": "Country"}}
            if tool != "get_browser_state"
            else {}
        ),
        **({"text_sha256": "f" * 64} if tool == "browser_type" else {}),
    }


def second_handoff(native, history):
    """The pinned driver keeps one call ledger per session: a later handoff lists earlier rows."""
    yield_to, status = native.yield_to, native.handoff_status
    native.yield_to = lambda ready, **kwargs: {**yield_to(ready, **kwargs), "generation": 2}

    def handoff_status(**kwargs):
        value = status(**kwargs)
        return {**value, "generation": 2, "calls": [*history, *value["calls"]]}

    native.handoff_status = handoff_status


def test_second_handoff_filters_earlier_generation_terminal_rows(tmp_path, monkeypatch):
    config, ref, scope, packet, driver, native, events = native_case(tmp_path, monkeypatch)
    earlier = {**scope, "target_id": "earlier-target"}
    history = [
        native_row("gen1-read", "observed", 1, earlier, 1, "get_browser_state"),
        native_row("gen1-type", "observed", 1, earlier, 2),
        native_row("gen1-refused", "not_sent", 1, earlier, 3),
    ]
    second_handoff(native, history)
    current = native_row("gen2-type", "awaiting_host", 2, scope)
    native.calls = [current]
    receipts, decisions = [], []

    def decide(call):
        decisions.append(call["call_id"])
        return True

    adapter, run = start_case(
        config,
        ref,
        scope,
        packet,
        driver,
        native,
        before_native_call=decide,
        after_yield=lambda receipt: receipts.append(deepcopy(receipt)),
    )
    try:
        assert run.status == "ready" and run.error_code is None
        adapter.progress(run.run_id)
        # Earlier rows are history: never current calls, decisions or admissions.
        assert decisions == ["gen2-type"]
        admitted = [event[1] for event in events if isinstance(event, tuple)]
        assert admitted == ["gen2-type"]
        published = {row["call_id"] for receipt in receipts for row in receipt.get("calls", [])}
        assert published == {"gen2-type"}
        snapshot = adapter.progress(run.run_id).native_handoff
        assert [row["call_id"] for row in snapshot["calls"]] == ["gen2-type"]
    finally:
        adapter.close()


@pytest.mark.parametrize(
    "history",
    [
        [("gen1-unknown", "unknown", 1)],
        [("gen1-inflight", "in_flight", 1)],
        [("gen1-awaiting", "awaiting_host", 1)],
        [("gen3-future", "observed", 3)],
    ],
    ids=["earlier_unknown", "earlier_in_flight", "earlier_awaiting", "later_generation"],
)
def test_second_handoff_refuses_unresolved_or_future_rows(tmp_path, monkeypatch, history):
    config, ref, scope, packet, driver, native, events = native_case(tmp_path, monkeypatch)
    second_handoff(
        native, [native_row(call_id, status, gen, scope) for call_id, status, gen in history]
    )
    adapter, run = start_case(config, ref, scope, packet, driver, native)
    try:
        assert run.status == "unknown" and run.error_code == "native_handoff_status_unknown"
        assert native.revoked
        assert not [event for event in events if isinstance(event, tuple)]
    finally:
        adapter.close()


def test_current_generation_row_with_another_scope_is_still_refused(tmp_path, monkeypatch):
    config, ref, scope, packet, driver, native, events = native_case(tmp_path, monkeypatch)
    second_handoff(native, [])
    native.calls = [native_row("gen2-elsewhere", "observed", 2, {**scope, "tab_id": "other"})]
    adapter, run = start_case(config, ref, scope, packet, driver, native)
    try:
        assert run.status == "unknown" and run.error_code == "native_handoff_status_unknown"
    finally:
        adapter.close()
