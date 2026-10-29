"""Controlled app-server peer for real native handoff tests; never calls a model.

The test copies this source behind a Python shebang into its private workspace.
Only the app-server protocol is synthetic. The direct child is the exact native
MCP command supplied by the production Adapter, with its real lease and tools.
"""

import json
import os
import subprocess
import sys
import threading
import tomllib
import traceback
from pathlib import Path


def main():
    if sys.argv[1:] == ["--version"]:
        print("codex-cli 0.165.0-alpha.1.2")
        return

    root = Path.cwd()
    lock = threading.Lock()
    proxy = None
    operation = None
    sequence = 0
    catalog = None
    settings_path = root / "peer-settings.json"
    settings = json.loads(settings_path.read_text()) if settings_path.exists() else {}

    def record(value):
        with lock, (root / "native-peer.jsonl").open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(value, ensure_ascii=False) + "\n")

    def send(value):
        with lock:
            print(json.dumps(value), flush=True)

    def exchange(messages):
        proxy.stdin.write("".join(json.dumps(message) + "\n" for message in messages))
        proxy.stdin.flush()
        for message in messages:
            record({"kind": "native_sent", "request": message})
        results = []
        for message in messages:
            line = proxy.stdout.readline()
            if not line:
                raise RuntimeError(f"Native proxy closed during {message['method']}")
            response = json.loads(line)
            record({"kind": "native_rpc", "request": message, "response": response})
            if response.get("id") != message["id"] or "error" in response:
                raise RuntimeError(f"Native RPC refused: {response}")
            results.append(response["result"])
        return results

    def rpc(method, params):
        nonlocal sequence
        sequence += 1
        return exchange([{"jsonrpc": "2.0", "id": sequence, "method": method, "params": params}])[0]

    def tool(name, arguments):
        result = rpc("tools/call", {"name": name, "arguments": arguments})
        data = result.get("structuredContent")
        if (
            result.get("isError")
            or not isinstance(data, dict)
            or data.get("refusal")
            or data.get("effect") == "refused"
            or data.get("error")
            or data.get("status") in {"refused", "error"}
        ):
            raise RuntimeError(f"Native tool failed: {result}")
        return data

    def native_type(packet):
        nonlocal sequence
        try:
            context = packet["page_context"]
            scope = {key: context["native_scope"][key] for key in ("target_id", "tab_id")}
            observation = {
                **scope,
                "snapshot_format": "semantic_v2",
                "include_screenshot": False,
            }
            before = tool("get_browser_state", observation)
            if settings.get("effect") in {"click_boundaries", "click_network"}:
                targets = (
                    [
                        ("Local details", "disclosuretriangle"),
                        ("Reset forwarding", "button"),
                        ("Submit", "button"),
                        ("Reset forwarding", "disclosuretriangle"),
                    ]
                    if settings["effect"] == "click_boundaries"
                    else [("Local details", "disclosuretriangle")]
                )
                actions = []
                current = before
                for name, role in targets:
                    candidates = [
                        row
                        for row in current["refs"]
                        if row.get("name") == name
                        and row.get("role") == role
                        and "click" in row.get("actions", [])
                    ]
                    if len(candidates) != 1:
                        raise RuntimeError(f"Expected one native click ref for {name}: {current}")
                    result = rpc(
                        "tools/call",
                        {
                            "name": "browser_click",
                            "arguments": {**scope, "ref": candidates[0]["ref"]},
                        },
                    )
                    actions.append({"name": name, "before": candidates[0], "result": result})
                    if settings["effect"] == "click_boundaries":
                        current = tool("get_browser_state", observation)
                record(
                    {"kind": "completed", "before": before, "actions": actions, "after": current}
                )
                send(
                    {
                        "method": "turn/completed",
                        "params": {
                            "threadId": "controlled-native-thread",
                            "turn": {"id": "controlled-native-turn", "status": "completed"},
                        },
                    }
                )
                return
            fields = [
                row
                for row in before["refs"]
                if row.get("name") == "Email" and "type" in row.get("actions", [])
            ]
            if len(fields) != 1 or fields[0].get("value") not in (None, ""):
                raise RuntimeError("Expected one empty native Email field")
            facts = [
                row
                for row in packet["answers"]["facts"]
                if row.get("fact") == "email" and row.get("status") == "confirmed"
            ]
            if len(facts) != 1:
                raise RuntimeError("Expected one confirmed Email answer in Worker JSON")
            arguments = {
                **scope,
                "ref": fields[0]["ref"],
                "text": facts[0]["value"],
                "mode": "insert_text",
                "replace": False,
                "expected_value": "",
            }
            if settings.get("effect") == "rewrite_after_input":
                sequence += 1
                first_id = sequence
                sequence += 1
                # The proxy derives native call ids. Reuse the original MCP id,
                # then refresh real refs before attempting a new mutation id.
                results = exchange(
                    [
                        {
                            "jsonrpc": "2.0",
                            "id": identifier,
                            "method": "tools/call",
                            "params": {"name": "browser_type", "arguments": arguments},
                        }
                        for identifier in (first_id, first_id)
                    ]
                    + [
                        {
                            "jsonrpc": "2.0",
                            "id": sequence,
                            "method": "tools/call",
                            "params": {"name": "get_browser_state", "arguments": observation},
                        }
                    ]
                )
                fresh_result = results.pop()
                fresh = fresh_result.get("structuredContent", {})
                field = next(
                    (
                        row
                        for row in fresh.get("refs", [])
                        if row.get("name") == "Email" and "type" in row.get("actions", [])
                    ),
                    None,
                )
                record({"kind": "retry_scope", "fresh_result": fresh_result, "fresh_ref": field})
                results.append(
                    rpc(
                        "tools/call",
                        {
                            "name": "browser_type",
                            "arguments": {
                                **arguments,
                                "ref": field["ref"] if field else arguments["ref"],
                            },
                        },
                    )
                )
                record(
                    {
                        "kind": "completed",
                        "before": before,
                        "fresh": fresh,
                        "unknown_results": results,
                    }
                )
            else:
                typed = tool("browser_type", arguments)
                after = tool("get_browser_state", observation)
                record({"kind": "completed", "before": before, "typed": typed, "after": after})
            send(
                {
                    "method": "turn/completed",
                    "params": {
                        "threadId": "controlled-native-thread",
                        "turn": {"id": "controlled-native-turn", "status": "completed"},
                    },
                }
            )
        except Exception:
            record({"kind": "failure", "traceback": traceback.format_exc()})
            send(
                {
                    "method": "turn/completed",
                    "params": {
                        "threadId": "controlled-native-thread",
                        "turn": {"id": "controlled-native-turn", "status": "failed"},
                    },
                }
            )

    config = {}
    for index, argument in enumerate(sys.argv[:-1]):
        if argument == "--config":
            fragment = tomllib.loads(sys.argv[index + 1])
            if "web_search" in fragment:
                config["web_search"] = fragment["web_search"]
            if "mcp_servers" in fragment:
                config.setdefault("mcp_servers", {})
            for name, value in fragment.get("mcp_servers", {}).items():
                config.setdefault("mcp_servers", {}).setdefault(name, {}).update(value)

    try:
        for line in sys.stdin:
            message = json.loads(line)
            method = message.get("method")
            if method == "initialize":
                result = {
                    "userAgent": "controlled-native-acceptance-peer",
                    "codexHome": "isolated-synthetic",
                    "platformFamily": "unix",
                    "platformOs": "macos",
                }
            elif method == "config/read":
                result = {"config": config, "origins": {}}
            elif method == "thread/start":
                native = message["params"]["config"]["mcp_servers"]["cua_takeover"]
                command = [native["command"], *native["args"]]
                with (root / "native-proxy.log").open("w", encoding="utf-8") as log:
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
                        "clientInfo": {"name": "controlled-native-peer", "version": "1"},
                    },
                )
                proxy.stdin.write(
                    json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}) + "\n"
                )
                proxy.stdin.flush()
                catalog = rpc("tools/list", {})["tools"]
                # Report the real driver metadata, as the app-server does.
                resources = rpc("resources/list", {})["resources"]
                templates = rpc("resources/templates/list", {})["resourceTemplates"]
                result = {"thread": {"id": "controlled-native-thread"}}
            elif method == "mcpServerStatus/list":
                result = {
                    "data": [
                        {
                            "name": "cua_takeover",
                            "runtimeStatus": "connected",
                            "authStatus": "unsupported",
                            "pluginId": None,
                            "httpOrigin": None,
                            "resources": resources,
                            "resourceTemplates": templates,
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
                record({"kind": "delivery", "packet": packet})
                send(
                    {
                        "id": message["id"],
                        "result": {
                            "turn": {
                                "id": "controlled-native-turn",
                                "status": "inProgress",
                                "items": [],
                            }
                        },
                    }
                )
                operation = threading.Thread(target=native_type, args=(packet,), daemon=True)
                operation.start()
                continue
            elif method == "turn/interrupt":
                send({"id": message["id"], "result": {}})
                send(
                    {
                        "method": "turn/completed",
                        "params": {
                            "threadId": "controlled-native-thread",
                            "turn": {"id": "controlled-native-turn", "status": "interrupted"},
                        },
                    }
                )
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
