"""Controlled app-server peer for MC-07 return/completion tests; never calls a model.

The test copies this source behind a Python shebang into its private workspace.
Only the app-server protocol and the model's final message are synthetic. The
direct child is the exact native MCP command supplied by the production Adapter,
with its real lease and tools; page effects come only from those native tools.

The final structured message shape lives in ``emit_final_message`` only, so it
can follow the event shape confirmed against the installed app-server schema.
"""

import json
import os
import subprocess
import sys
import threading
import time
import tomllib
import traceback
from pathlib import Path

THREAD = "controlled-native-thread"
TURN = "controlled-native-turn"
REPORT_ITEM = "controlled-native-final-message"


def main():
    if sys.argv[1:] == ["--version"]:
        print("codex-cli 0.165.0-alpha.1.2")
        return
    root = Path.cwd()
    settings = json.loads((root / "peer-settings.json").read_text())
    effect = settings["effect"]
    lock = threading.Lock()
    proxy = operation = None
    sequence = 0
    catalog = []
    terminal = []

    def record(value):
        with lock, (root / "native-peer.jsonl").open("a", encoding="utf-8") as stream:
            stream.write(json.dumps({**value, "at": time.time()}, ensure_ascii=False) + "\n")

    def send(value):
        with lock:
            print(json.dumps(value), flush=True)

    def complete(status):
        # One terminal per turn: an interrupt answered first wins over a later completion.
        with lock:
            if terminal:
                return
            terminal.append(status)
            print(
                json.dumps(
                    {
                        "method": "turn/completed",
                        "params": {"threadId": THREAD, "turn": {"id": TURN, "status": status}},
                    }
                ),
                flush=True,
            )
        record({"kind": "turn_terminal", "status": status})

    def emit_final_message(text):
        """The model's final message for the active turn, before turn/completed.

        Installed app-server schema: item/completed params {threadId, turnId,
        completedAtMs, item}; item {type: agentMessage, id, text}.
        """
        send(
            {
                "method": "item/completed",
                "params": {
                    "threadId": THREAD,
                    "turnId": TURN,
                    "completedAtMs": int(time.time() * 1000),
                    "item": {"type": "agentMessage", "id": REPORT_ITEM, "text": text},
                },
            }
        )
        record({"kind": "report_sent", "text": text})

    def claimed(status, summary, field_ids, **extra):
        # Only outputSchema keys; additionalProperties is false at every level.
        return json.dumps(
            {
                "status": status,
                "summary": summary,
                "unresolved_action_ids": [],
                "fields": [{"field_id": field, "state": "filled"} for field in field_ids],
                **extra,
                **settings.get("claimed_extra", {}),
            },
            ensure_ascii=False,
        )

    def wait_for(name, seconds):
        deadline = time.monotonic() + seconds
        while not (root / name).exists():
            if time.monotonic() >= deadline:
                raise TimeoutError(f"Fixture did not write {name}")
            time.sleep(0.01)

    def write_requests(messages):
        proxy.stdin.write("".join(json.dumps(message) + "\n" for message in messages))
        proxy.stdin.flush()
        for message in messages:
            record({"kind": "native_sent", "request": message})

    def read_response(message):
        line = proxy.stdout.readline()
        if not line:
            raise RuntimeError(f"Native proxy closed during {message['method']}")
        response = json.loads(line)
        record({"kind": "native_rpc", "request": message, "response": response})
        if response.get("id") != message["id"] or "error" in response:
            raise RuntimeError(f"Native RPC refused: {response}")
        return response["result"]

    def request(method, params):
        nonlocal sequence
        sequence += 1
        return {"jsonrpc": "2.0", "id": sequence, "method": method, "params": params}

    def rpc(method, params):
        message = request(method, params)
        write_requests([message])
        return read_response(message)

    def tool(name, arguments):
        result = rpc("tools/call", {"name": name, "arguments": arguments})
        data = result.get("structuredContent")
        if (
            result.get("isError")
            or not isinstance(data, dict)
            or data.get("refusal")
            or data.get("effect") in {"refused", "unverifiable"}
            or data.get("error")
            or data.get("status") in {"refused", "error"}
        ):
            raise RuntimeError(f"Native tool failed: {result}")
        return data

    def one_ref(snapshot, name, action, roles=()):
        rows = [
            row
            for row in snapshot.get("refs", [])
            if row.get("name") == name and action in row.get("actions", [])
        ]
        preferred = [row for row in rows if row.get("role") in roles]
        rows = preferred if len(preferred) == 1 else rows
        if len(rows) != 1:
            raise RuntimeError(f"Expected one native {action} ref for {name}: {snapshot}")
        return rows[0]

    def type_arguments(scope, snapshot, packet, label, fact):
        field = one_ref(snapshot, label, "type")
        if field.get("value") not in (None, ""):
            raise RuntimeError(f"Expected empty native {label} field: {field}")
        facts = [
            row
            for row in packet["answers"]["facts"]
            if row.get("fact") == fact and row.get("status") == "confirmed"
        ]
        if len(facts) != 1:
            raise RuntimeError(f"Expected one confirmed {fact} answer in Worker JSON")
        return {
            **scope,
            "ref": field["ref"],
            "text": facts[0]["value"],
            "mode": "insert_text",
            "replace": False,
            "expected_value": "",
        }

    def chain_turn(packet, scope, observation):
        """MC-09 chain: one covered combobox per takeover, chosen by the Worker's next step.

        Turn 1 (reconcile the script's pending Country fill) types Country and returns
        to the script at Phone; turn 2 (complete_remaining_fields, after a return)
        types Region and reports the form ready. ``chain_tool_unknown`` leaves the
        first turn's native call unresolved while claiming the segment resolved.
        """
        second = packet["next_step"]["kind"] == "complete_remaining_fields"
        label, fact = ("Region", "question:region") if second else ("Country", "question:country")
        before = tool("get_browser_state", observation)
        arguments = type_arguments(scope, before, packet, label, fact)
        if effect == "chain_tool_unknown" and not second:
            pending = request("tools/call", {"name": "browser_type", "arguments": arguments})
            write_requests([pending])
            record({"kind": "pending_sent", "request": pending})
            wait_for("release-report", 20)
            emit_final_message(
                claimed(
                    "blocked_segment_resolved",
                    "Selected Switzerland in Country",
                    ["country"],
                    next_step={"kind": "return_to_script", "field_id": "phone"},
                )
            )
            complete("completed")
            record({"kind": "completed", "turn": 1})
            try:
                record({"kind": "pending_result", "result": read_response(pending)})
            except Exception:
                record({"kind": "pending_lost", "traceback": traceback.format_exc()})
            return
        selected = tool("browser_type", arguments)
        current = tool("get_browser_state", observation)
        record(
            {
                "kind": "complex_control",
                "turn": 2 if second else 1,
                "before": before,
                "selected": selected,
                "after": current,
            }
        )
        if second:
            text = claimed("ready_for_review", "Selected Zurich in Region", ["region"])
        else:
            text = claimed(
                "blocked_segment_resolved",
                "Selected Switzerland in Country",
                ["country"],
                next_step={"kind": "return_to_script", "field_id": "phone"},
            )
        emit_final_message(text)
        record({"kind": "completed", "turn": 2 if second else 1, "after": current})
        complete("completed")

    def operate(packet):
        try:
            scope = {
                key: packet["page_context"]["native_scope"][key] for key in ("target_id", "tab_id")
            }
            observation = {**scope, "snapshot_format": "semantic_v2", "include_screenshot": False}
            if effect in {"chain", "chain_tool_unknown"}:
                chain_turn(packet, scope, observation)
                return
            before = tool("get_browser_state", observation)
            # The complex control: type the confirmed Country fact into the empty
            # autocomplete box; the page commits the exact option match. One call
            # per field keeps the change attributable (a click to open it first
            # would be a second observed call touching the same field).
            label, fact = settings.get("combobox", ["Country", "question:country"])
            selected = tool("browser_type", type_arguments(scope, before, packet, label, fact))
            current = tool("get_browser_state", observation)
            record(
                {
                    "kind": "complex_control",
                    "before": before,
                    "selected": selected,
                    "after": current,
                }
            )
            if effect in {"filling_complete", "lost_outcome_save", "prose_only"}:
                typed = []
                for label, fact in settings.get(
                    "type_fields", [["Email", "email"], ["Phone", "phone"]]
                ):
                    typed.append(
                        tool("browser_type", type_arguments(scope, current, packet, label, fact))
                    )
                    current = tool("get_browser_state", observation)
                record({"kind": "typed", "results": typed, "after": current})
            if effect == "return_to_script":
                # The next field is named by its handoff page_context DOM id.
                emit_final_message(
                    claimed(
                        "blocked_segment_resolved",
                        "Selected Switzerland in Country",
                        ["country"],
                        next_step={"kind": "return_to_script", "field_id": "phone"},
                    )
                )
                record({"kind": "completed", "after": current})
                complete("completed")
            elif effect in {"filling_complete", "lost_outcome_save"}:
                emit_final_message(
                    claimed("ready_for_review", "Filled every field", ["country", "email", "phone"])
                )
                record({"kind": "completed", "after": current})
                complete("completed")
            elif effect == "prose_only":
                emit_final_message("Done!")
                record({"kind": "completed", "after": current})
                complete("completed")
            elif effect == "pending_call":
                arguments = type_arguments(scope, current, packet, "Phone", "phone")
                pending = request("tools/call", {"name": "browser_type", "arguments": arguments})
                # Leave the actual native call unresolved while claiming completion.
                write_requests([pending])
                record({"kind": "pending_sent", "request": pending})
                wait_for("release-report", 20)
                emit_final_message(
                    claimed("ready_for_review", "Filled every field", ["country", "email", "phone"])
                )
                complete("completed")
                record({"kind": "completed"})
                try:
                    record({"kind": "pending_result", "result": read_response(pending)})
                except Exception:
                    record({"kind": "pending_lost", "traceback": traceback.format_exc()})
            elif effect == "pause_during_report":
                emit_final_message(
                    claimed(
                        "blocked_segment_resolved", "Selected Switzerland in Country", ["country"]
                    )
                )
                wait_for("release-turn", 20)
                record({"kind": "completed", "after": current})
                complete("completed")
            else:
                raise RuntimeError(f"Unknown peer effect: {effect}")
        except Exception:
            record({"kind": "failure", "traceback": traceback.format_exc()})
            complete("failed")

    config = {}
    for index, argument in enumerate(sys.argv[:-1]):
        if argument == "--config":
            fragment = tomllib.loads(sys.argv[index + 1])
            if "web_search" in fragment:
                config["web_search"] = fragment["web_search"]
            for name, value in fragment.get("mcp_servers", {}).items():
                config.setdefault("mcp_servers", {}).setdefault(name, {}).update(value)
    try:
        for line in sys.stdin:
            message = json.loads(line)
            method = message.get("method")
            if method == "initialize":
                result = {
                    "userAgent": "controlled-native-return-peer",
                    "codexHome": "isolated-synthetic",
                    "platformFamily": "unix",
                    "platformOs": "macos",
                }
            elif method == "config/read":
                result = {"config": config, "origins": {}}
            elif method == "thread/start":
                native = config["mcp_servers"]["cua_takeover"]
                command = [native["command"], *native["args"]]
                with (root / "native-proxy.log").open("a", encoding="utf-8") as log:
                    proxy = subprocess.Popen(
                        command,
                        stdin=subprocess.PIPE,
                        stdout=subprocess.PIPE,
                        stderr=log,
                        text=True,
                        encoding="utf-8",
                        env={
                            **os.environ,
                            "CUA_DRIVER_RS_UPDATE_CHECK": "false",
                            "CUA_DRIVER_RS_TELEMETRY_ENABLED": "0",
                        },
                    )
                record({"kind": "proxy_started", "pid": proxy.pid, "command": command})
                rpc(
                    "initialize",
                    {
                        "protocolVersion": "2025-06-18",
                        "capabilities": {},
                        "clientInfo": {"name": "native-return-peer", "version": "1"},
                    },
                )
                proxy.stdin.write(
                    json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}) + "\n"
                )
                proxy.stdin.flush()
                catalog = rpc("tools/list", {})["tools"]
                result = {"thread": {"id": THREAD}}
            elif method == "mcpServerStatus/list":
                result = {
                    "data": [
                        {
                            "name": "cua_takeover",
                            "runtimeStatus": "connected",
                            "authStatus": "unsupported",
                            "pluginId": None,
                            "httpOrigin": None,
                            "resources": [],
                            "resourceTemplates": [],
                            "tools": {row["name"]: row for row in catalog},
                        }
                    ],
                    "nextCursor": None,
                }
            elif method == "turn/start":
                inputs = message["params"]["input"]
                if len(inputs) != 1 or inputs[0]["type"] != "text":
                    raise RuntimeError("Worker handoff must be one JSON text item")
                packet = json.loads(inputs[0]["text"])
                record(
                    {
                        "kind": "delivery",
                        "packet": packet,
                        "output_schema": message["params"].get("outputSchema"),
                    }
                )
                send(
                    {
                        "id": message["id"],
                        "result": {"turn": {"id": TURN, "status": "inProgress", "items": []}},
                    }
                )
                operation = threading.Thread(target=operate, args=(packet,), daemon=True)
                operation.start()
                continue
            elif method == "turn/interrupt":
                send({"id": message["id"], "result": {}})
                record({"kind": "interrupt_received"})
                complete("interrupted")
                continue
            elif "id" not in message:
                continue
            else:
                raise RuntimeError(f"Unexpected app-server method: {method}")
            send({"id": message["id"], "result": result})
    except Exception:
        record({"kind": "failure", "traceback": traceback.format_exc()})
        raise
    finally:
        if proxy is not None:
            proxy.stdin.close()
            try:
                proxy.wait(timeout=3)
            except subprocess.TimeoutExpired:
                proxy.terminate()
                try:
                    proxy.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    proxy.kill()
                    proxy.wait(timeout=3)
            proxy.stdout.close()
        if operation is not None:
            operation.join(timeout=1)


if __name__ == "__main__":
    main()
