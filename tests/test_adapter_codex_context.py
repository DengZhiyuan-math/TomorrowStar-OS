"""JSON handoff uses existing passive transport without a screenshot/action channel."""

import json
import threading

from test_adapter_codex_readonly import reference, request, rows, tool_server, wait_response
from test_application_codex_assist import config

from career_evidence_graph.application_codex_assist import CodexAdapter


def delivery(ref):
    return {
        "schema_version": 1,
        "assistance_ref": ref,
        "progress": {"completed": [], "remaining": []},
        "blocker": {"code": "unsupported_control"},
        "pending_actions": [],
        "page_context": {
            "status": "captured",
            "binding": ref["binding"],
            "document": {"loader_id": "original-loader"},
            "data": {"fields": [{"id": "country", "role": "combobox"}]},
            "at": 1.0,
        },
        "materials": [],
        "next_step": {"kind": "inspect_control_and_continue"},
    }


def test_context_tool_delivers_json_without_screenshot_or_actions(tmp_path):
    executable = tool_server(tmp_path, [request(tool="read_application_context")])
    adapter = CodexAdapter(config(tmp_path, executable))
    calls = []

    def read(ref):
        calls.append((threading.get_ident(), ref))
        return delivery(ref)

    try:
        run = adapter.start(reference(), request_id="context-start", context_handler=read)
        response = wait_response(adapter, executable, "read-1")
        assert response["result"]["success"] is True
        assert len(response["result"]["contentItems"]) == 1
        content = response["result"]["contentItems"][0]
        assert content["type"] == "inputText"
        assert json.loads(content["text"]) == delivery(reference())
        assert calls == [(threading.get_ident(), reference())]
        started = next(r for r in rows(executable) if r.get("method") == "thread/start")
        assert [t["name"] for t in started["params"]["dynamicTools"]] == [
            "read_application_context"
        ]
        assert run.page_write_allowed is False
        assert not any(r.get("method") == "turn/start" for r in rows(executable))
    finally:
        adapter.close()


def test_context_tool_cannot_accept_page_arguments_or_expose_image_tool(tmp_path):
    executable = tool_server(
        tmp_path,
        [
            request(
                "foreign",
                tool="read_application_context",
                arguments={"url": "https://example.invalid/another"},
            ),
            request("image", tool="observe_owned_page"),
            request("valid", tool="read_application_context"),
        ],
    )
    adapter = CodexAdapter(config(tmp_path, executable))
    calls = []
    try:
        adapter.start(
            reference(),
            request_id="context-deny",
            context_handler=lambda ref: calls.append(ref) or delivery(ref),
        )
        response = wait_response(adapter, executable, "valid")
        assert response["result"]["success"] is True
        recorded = rows(executable)
        assert next(r for r in recorded if r.get("id") == "foreign")["error"]["code"] == -32000
        assert next(r for r in recorded if r.get("id") == "image")["error"]["code"] == -32000
        assert calls == [reference()]
    finally:
        adapter.close()


def test_context_binding_changed_after_read_is_not_sent(tmp_path):
    executable = tool_server(tmp_path, [request(tool="read_application_context")])
    adapter = CodexAdapter(config(tmp_path, executable))

    def wrong_binding(ref):
        value = delivery(ref)
        value["page_context"]["binding"] = {"page_id": "other-page"}
        return value

    try:
        adapter.start(reference(), request_id="changed-context", context_handler=wrong_binding)
        response = wait_response(adapter, executable, "read-1")
        assert response["error"]["code"] == -32000
        assert "contentItems" not in response
    finally:
        adapter.close()


def test_revocation_during_json_read_does_not_publish_stale_context(tmp_path):
    import time

    executable = tool_server(tmp_path, [request(tool="read_application_context")])
    adapter = CodexAdapter(config(tmp_path, executable))
    active = []
    run = None

    def revoke(ref):
        stopped = adapter.stop(run.run_id, request_id="stop-inside-json")
        active.append(stopped.local_tools_drained)
        return delivery(ref)

    try:
        run = adapter.start(reference(), request_id="revoke-context", context_handler=revoke)
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline and not active:
            adapter.service_readonly()
            time.sleep(0.005)
        assert active == [False]
        assert adapter.progress(run.run_id).local_tools_drained is True
        assert not any("contentItems" in r.get("result", {}) for r in rows(executable))
    finally:
        adapter.close()
