"""Scripted material requests through the real dedicated native MCP child.

Only the app-server peer is synthetic. No material body/path/bytes are sent as
tool arguments, and no native result or receipt is replaced by this peer.
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


def main():
    if sys.argv[1:] == ["--version"]:
        print("codex-cli 0.165.0-alpha.1.2")
        return
    root = Path.cwd()
    settings = json.loads((root / "peer-settings.json").read_text())
    lock = threading.Lock()
    proxy = operation = None
    sequence = 0
    catalog = []

    def record(value):
        with lock, (root / "native-peer.jsonl").open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(value, ensure_ascii=False) + "\n")

    def send(value):
        with lock:
            print(json.dumps(value), flush=True)

    def complete(status):
        send(
            {
                "method": "turn/completed",
                "params": {
                    "threadId": "controlled-native-thread",
                    "turn": {"id": "controlled-native-turn", "status": status},
                },
            }
        )

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

    def target(snapshot):
        matches = [
            row
            for row in snapshot.get("refs", [])
            if row.get("name") == settings["target_label"]
            and settings["target_action"] in row.get("actions", [])
        ]
        if len(matches) != 1:
            raise RuntimeError(f"Expected one actual material destination: {snapshot}")
        return matches[0]

    def deliver(packet):
        nonlocal sequence
        try:
            scope = {
                key: packet["page_context"]["native_scope"][key] for key in ("target_id", "tab_id")
            }
            observation = {**scope, "snapshot_format": "semantic_v2", "include_screenshot": False}
            before = rpc("tools/call", {"name": "get_browser_state", "arguments": observation})
            field = target(before.get("structuredContent", {}))
            materials = [
                row
                for row in packet["materials"]
                if row.get("kind") == "cover_letter"
                and row.get("status") == "ready"
                and row.get("material_ref")
            ]
            if len(materials) != 1:
                raise RuntimeError(f"Expected one prepared letter token: {packet['materials']}")
            arguments = {**scope, "ref": field["ref"], "material_ref": materials[0]["material_ref"]}
            record(
                {
                    "kind": "material_ready",
                    "before": before,
                    "material": materials[0],
                    "arguments": arguments,
                }
            )
            deadline = time.monotonic() + 12
            while not (root / "release-material").exists():
                if time.monotonic() >= deadline:
                    raise TimeoutError("Fixture did not release its one material request")
                time.sleep(0.01)
            sequence += 1
            first = {
                "jsonrpc": "2.0",
                "id": sequence,
                "method": "tools/call",
                "params": {"name": "browser_deliver_material", "arguments": arguments},
            }
            if settings["effect"] == "material_unknown":
                sequence += 1
                results = exchange(
                    [
                        first,
                        first,
                        {
                            "jsonrpc": "2.0",
                            "id": sequence,
                            "method": "tools/call",
                            "params": {"name": "get_browser_state", "arguments": observation},
                        },
                    ]
                )
                fresh_result = results.pop()
                record({"kind": "material_retry_snapshot", "result": fresh_result})
                fresh = target(fresh_result.get("structuredContent", {}))
                results.append(
                    rpc(
                        "tools/call",
                        {
                            "name": "browser_deliver_material",
                            "arguments": {**arguments, "ref": fresh["ref"]},
                        },
                    )
                )
                record(
                    {
                        "kind": "completed",
                        "results": results,
                        "fresh_ref": fresh["ref"],
                        "first_request": first,
                    }
                )
            else:
                result = exchange([first])[0]
                results = [result]
                record({"kind": "material_local_result", "result": result, "first_request": first})
                if settings["effect"] == "material_upload_lost":
                    deadline = time.monotonic() + 15
                    while not (root / "release-terminal").exists():
                        if time.monotonic() >= deadline:
                            raise TimeoutError("Fixture did not finish original upload observation")
                        time.sleep(0.01)
                if settings["effect"] == "material_pending":
                    fresh = rpc(
                        "tools/call", {"name": "get_browser_state", "arguments": observation}
                    )
                    fields = [
                        row
                        for row in fresh.get("structuredContent", {}).get("refs", [])
                        if row.get("name") == "Email" and "type" in row.get("actions", [])
                    ]
                    facts = [
                        row
                        for row in packet["answers"]["facts"]
                        if row.get("fact") == "email" and row.get("status") == "confirmed"
                    ]
                    if len(fields) != 1 or len(facts) != 1:
                        raise RuntimeError(
                            "Missing actual Email ref/confirmed fact for pending guard"
                        )
                    results.append(
                        rpc(
                            "tools/call",
                            {
                                "name": "browser_type",
                                "arguments": {
                                    **scope,
                                    "ref": fields[0]["ref"],
                                    "text": facts[0]["value"],
                                    "mode": "insert_text",
                                    "replace": False,
                                    "expected_value": "",
                                },
                            },
                        )
                    )
                    record({"kind": "pending_retry", "snapshot": fresh, "field": fields[0]})
                record({"kind": "completed", "results": results, "first_request": first})
            complete("completed")
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
                    "userAgent": "controlled-native-material-peer",
                    "codexHome": "isolated-synthetic",
                    "platformFamily": "unix",
                    "platformOs": "macos",
                }
            elif method == "config/read":
                result = {"config": config, "origins": {}}
            elif method == "thread/start":
                native = config["mcp_servers"]["cua_takeover"]
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
                        "clientInfo": {"name": "native-material-peer", "version": "1"},
                    },
                )
                proxy.stdin.write(
                    json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}) + "\n"
                )
                proxy.stdin.flush()
                catalog = rpc("tools/list", {})["tools"]
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
                operation = threading.Thread(target=deliver, args=(packet,), daemon=True)
                operation.start()
                continue
            elif method == "turn/interrupt":
                send({"id": message["id"], "result": {}})
                complete("interrupted")
                continue
            elif "id" not in message:
                continue
            else:
                raise RuntimeError(f"Unexpected app-server method: {method}")
            send({"id": message["id"], "result": result})
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
