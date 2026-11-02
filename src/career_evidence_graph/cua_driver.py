"""Bounded CuaDriver MCP execution. The application worker owns authorization."""

from __future__ import annotations

import base64
import hashlib
import json
import math
import os
import queue
import re
import selectors
import socket as local_socket
import stat
import struct
import subprocess
import sys
import tempfile
import threading
import time
from contextlib import ExitStack, contextmanager, suppress
from copy import deepcopy
from pathlib import Path
from urllib.parse import urlsplit
from uuid import uuid4

from ._vendor import job_apply_store as helper
from .application_takeover_budget import DEFAULT_BUDGET
from .career_portal_data import PortalDataError
from .owned_browser_cdp import OwnedCDP
from .worker_measurement import current_measurements
from .worker_process_identity import (
    process_identity,
    process_parent_identity,
    valid_process_identity,
)

# Reviewed release build of the restricted-metadata native successor, signed with the
# pinned private identity. A version string alone cannot admit it.
_NATIVE_HANDOFF_DRIVER_SHA256 = "ba1541e7862df48c8eff5101276223e543093a66bc17b6c1033dce3a1d9f3256"
# The App bundles one cua-driver, so the script route admits the same reviewed bytes.
_OWNED_DRIVER_SHA256 = _NATIVE_HANDOFF_DRIVER_SHA256
NATIVE_HANDOFF_PROTOCOL = "cua-trusted-handoff/v1"
NATIVE_HANDOFF_TOOLS = (
    "get_browser_state",
    "browser_click",
    "browser_type",
    "browser_deliver_material",
)


def validate_fixed_material_resolution(value, *, material_ref=None):
    """Validate the sealed private payload; never include its contents in an error."""
    if not isinstance(value, dict) or value.get("kind") not in ("text", "file"):
        raise ValueError("Invalid fixed material resolution")
    kind = value["kind"]
    if (
        set(value)
        != (
            {"protocol", "resolution_id", "material_ref", "kind", "sha256", "size_bytes"}
            | ({"text"} if kind == "text" else {"bytes_base64", "filename", "mime_type"})
        )
        or value.get("protocol") != "fixed-material/v1"
        or any(
            not isinstance(value.get(key), str) or re.fullmatch(pattern, value[key]) is None
            for key, pattern in (
                ("resolution_id", r"[a-f0-9]{32}"),
                ("material_ref", r"[a-f0-9]{64}"),
                ("sha256", r"[a-f0-9]{64}"),
            )
        )
        or material_ref is not None
        and value["material_ref"] != material_ref
        or type(value.get("size_bytes")) is not int
        or not 1 <= value["size_bytes"] <= (20000 if kind == "text" else 700000)
    ):
        raise ValueError("Invalid fixed material resolution")
    if kind == "text":
        if not isinstance(value["text"], str) or not 1 <= len(value["text"]) <= 20000:
            raise ValueError("Invalid fixed material resolution")
        try:
            raw = value["text"].encode("utf-8")
        except UnicodeError:
            raise ValueError("Invalid fixed material resolution") from None
    else:
        filename = value["filename"]
        if (
            not isinstance(filename, str)
            or not 1 <= len(filename) <= 255
            or any(ord(char) < 32 or 0x7F <= ord(char) <= 0x9F for char in filename)
            or "/" in filename
            or "\\" in filename
            or Path(filename).suffix.casefold() != ".pdf"
            or value["mime_type"] != "application/pdf"
            or not isinstance(value["bytes_base64"], str)
            or not 1 <= len(value["bytes_base64"]) <= ((700000 + 2) // 3) * 4
        ):
            raise ValueError("Invalid fixed material resolution")
        try:
            raw = base64.b64decode(value["bytes_base64"], validate=True)
        except ValueError:
            raise ValueError("Invalid fixed material resolution") from None
        if base64.b64encode(raw).decode("ascii") != value["bytes_base64"]:
            raise ValueError("Invalid fixed material resolution")
    if value["size_bytes"] != len(raw) or value["sha256"] != hashlib.sha256(raw).hexdigest():
        raise ValueError("Invalid fixed material resolution")
    return deepcopy(value)


def validate_native_material_target(value):
    """Validate bounded target identity, leaving field eligibility to its owner."""
    strings = {
        "tag": 100,
        "type": 100,
        "id": 200,
        "name": 200,
        "worker_field": 200,
        "label": 1000,
        "accept": 1000,
        "draft_path": 1000,
    }
    booleans = {"required", "disabled", "readonly", "value_empty", "multiple"}
    if (
        not isinstance(value, dict)
        or set(value) != set(strings) | booleans | {"frame", "max_length", "file_count"}
        or any(
            not isinstance(value[key], str) or len(value[key]) > limit
            for key, limit in strings.items()
        )
        or value["frame"] != "main"
        or any(type(value[key]) is not bool for key in booleans)
        or (
            value["max_length"] is not None
            and (type(value["max_length"]) is not int or value["max_length"] < 0)
        )
        or type(value["file_count"]) is not int
        or not 0 <= value["file_count"] <= 20
    ):
        raise ValueError("Invalid native material target")
    return deepcopy(value)


def validate_native_material_metadata(row):
    """Validate only payload-free native material metadata, without filtering it."""
    fields = {
        "call_id",
        "tool",
        "arguments_digest",
        "status",
        "generation",
        "sequence",
        "mutation",
        "semantic_verified",
        "scope",
        "native_ref",
        "field_hint",
        "material_ref",
        "target_descriptor",
    }
    if (
        not isinstance(row, dict)
        or not fields <= set(row) <= fields | {"material_resolution", "material_readback"}
        or row["tool"] != "browser_deliver_material"
        or any(
            not isinstance(row[key], str)
            or not 1 <= len(row[key]) <= limit
            or not row[key].isprintable()
            for key, limit in (("call_id", 128), ("native_ref", 256))
        )
        or any(
            not isinstance(row[key], str) or re.fullmatch(r"[a-f0-9]{64}", row[key]) is None
            for key in ("arguments_digest", "material_ref")
        )
        or row["status"] not in ("awaiting_host", "in_flight", "observed", "not_sent", "unknown")
        or any(type(row[key]) is not int or row[key] <= 0 for key in ("generation", "sequence"))
        or row["mutation"] is not True
        or row["semantic_verified"] is not False
        or not valid_page_scope(row["scope"])
        or not isinstance(row["field_hint"], dict)
        or set(row["field_hint"]) != {"role", "name"}
        or any(
            not isinstance(value, str) or len(value) > 1000 for value in row["field_hint"].values()
        )
        or row["status"] in ("in_flight", "observed")
        and "material_resolution" not in row
        or ("material_readback" in row) != (row["status"] == "observed")
    ):
        raise ValueError("Invalid native material metadata")
    validate_native_material_target(row["target_descriptor"])
    if "material_resolution" in row:
        value = row["material_resolution"]
        if not isinstance(value, dict) or value.get("kind") not in ("text", "file"):
            raise ValueError("Invalid native material metadata")
        kind = value["kind"]
        if (
            set(value)
            != (
                {"protocol", "resolution_id", "material_ref", "kind", "sha256", "size_bytes"}
                | ({"filename", "mime_type"} if kind == "file" else set())
            )
            or value.get("protocol") != "fixed-material/v1"
            or value.get("material_ref") != row["material_ref"]
            or any(
                not isinstance(value.get(key), str) or re.fullmatch(pattern, value[key]) is None
                for key, pattern in (
                    ("resolution_id", r"[a-f0-9]{32}"),
                    ("sha256", r"[a-f0-9]{64}"),
                )
            )
            or type(value.get("size_bytes")) is not int
            or not 1 <= value["size_bytes"] <= (20000 if kind == "text" else 700000)
        ):
            raise ValueError("Invalid native material metadata")
        if kind == "file" and (
            not isinstance(value["filename"], str)
            or not 1 <= len(value["filename"]) <= 255
            or any(ord(char) < 32 or 0x7F <= ord(char) <= 0x9F for char in value["filename"])
            or "/" in value["filename"]
            or "\\" in value["filename"]
            or Path(value["filename"]).suffix.casefold() != ".pdf"
            or value["mime_type"] != "application/pdf"
        ):
            raise ValueError("Invalid native material metadata")
        if "material_readback" in row:
            readback = row["material_readback"]
            if (
                not isinstance(readback, dict)
                or set(readback)
                != {"kind", "sha256", "size_bytes"}
                | ({"filename", "file_count"} if kind == "file" else set())
                or readback["kind"] != ("file_list" if kind == "file" else "value")
                or readback["sha256"] != value["sha256"]
                or type(readback["size_bytes"]) is not int
                or readback["size_bytes"] != value["size_bytes"]
                or kind == "file"
                and (
                    readback["filename"] != value["filename"]
                    or type(readback["file_count"]) is not int
                    or readback["file_count"] != 1
                )
            ):
                raise ValueError("Invalid native material metadata")
    return deepcopy(row)


def valid_page_scope(value):
    """The one shape of a borrowed original-page scope: target, tab and exact document."""
    return bool(
        isinstance(value, dict)
        and set(value) == {"target_id", "tab_id", "expected_document"}
        and all(
            isinstance(value[k], str) and 1 <= len(value[k]) <= 512 for k in ("target_id", "tab_id")
        )
        and isinstance(value["expected_document"], dict)
        and set(value["expected_document"]) == {"frame_id", "loader_id", "url"}
        and all(
            isinstance(v, str) and 1 <= len(v) <= 20_000
            for v in value["expected_document"].values()
        )
    )


_CALL_STATUSES = frozenset({"awaiting_host", "in_flight", "observed", "not_sent", "unknown"})
_CALL_FIELDS = frozenset(
    {
        "call_id",
        "tool",
        "arguments_digest",
        "status",
        "generation",
        "sequence",
        "mutation",
        "semantic_verified",
        "scope",
    }
)
HANDOFF_RECEIPT_FIELDS = frozenset(
    {
        "handoff_id",
        "generation",
        "phase",
        "revoked",
        "active_calls",
        "local_tools_drained",
        "return_ready",
        "calls",
    }
)
HANDOFF_GRANT_FIELDS = frozenset({"handoff_id", "generation", "local_tools_drained"})
_HEX64 = re.compile(r"[a-f0-9]{64}")


def _printable(value, limit):
    return isinstance(value, str) and 1 <= len(value) <= limit and value.isprintable()


def _counter(value):
    return type(value) is int and 0 < value < 2**64


def _valid_handoff_call(row):
    tool = row.get("tool") if isinstance(row, dict) else None
    # Every native tool except the read-only page state may change the page.
    mutation = tool != "get_browser_state"
    return bool(
        isinstance(row, dict)
        and tool in {"get_browser_state", "browser_click", "browser_type"}
        and set(row)
        == _CALL_FIELDS
        | ({"text_sha256"} if tool == "browser_type" else set())
        | ({"native_ref", "field_hint"} if mutation else set())
        and _printable(row["call_id"], 128)
        and isinstance(row["arguments_digest"], str)
        and _HEX64.fullmatch(row["arguments_digest"])
        and row["status"] in _CALL_STATUSES
        and _counter(row["generation"])
        and _counter(row["sequence"])
        and row["mutation"] is mutation
        and row["semantic_verified"] is False
        and valid_page_scope(row["scope"])
        and (
            not mutation
            or _printable(row["native_ref"], 256)
            and isinstance(row["field_hint"], dict)
            and set(row["field_hint"]) == {"role", "name"}
            and all(isinstance(v, str) and len(v) <= 1000 for v in row["field_hint"].values())
        )
        and (
            tool != "browser_type"
            or isinstance(row["text_sha256"], str)
            and _HEX64.fullmatch(row["text_sha256"])
        )
    )


def validate_handoff_receipt(value, *, grant=False):
    """The one check of a native handoff receipt; every reader trusts what it returns.

    ``grant`` is the receipt of the yield itself: identity and drain state, with the
    driver's ``yielded`` answer when it comes straight from the driver. Otherwise it is
    a full status: phase, revocation, drain, return readiness and payload-free calls.
    A receipt that fails raises ``ValueError``; the driver Seam reports it as unknown.
    """
    if not isinstance(value, dict):
        raise ValueError("Invalid native handoff receipt")
    keys = set(value)
    if grant:
        valid = HANDOFF_GRANT_FIELDS <= keys <= HANDOFF_GRANT_FIELDS | {"yielded"} and (
            "yielded" not in value or type(value["yielded"]) is bool
        )
    else:
        valid = (
            keys == HANDOFF_RECEIPT_FIELDS
            and isinstance(value["phase"], str)
            and len(value["phase"]) <= 100
            and value["phase"].isidentifier()
            and type(value["revoked"]) is bool
            and type(value["return_ready"]) is bool
            and type(value["active_calls"]) is int
            and 0 <= value["active_calls"] <= 1000
            and value["local_tools_drained"] is (value["active_calls"] == 0)
            and (not value["return_ready"] or value["local_tools_drained"])
            and isinstance(value["calls"], list)
            and len(value["calls"]) <= 1000
        )
    if not (
        valid
        and _printable(value["handoff_id"], 200)
        and type(value["generation"]) is int
        and 0 <= value["generation"] < 2**64
        and type(value["local_tools_drained"]) is bool
    ):
        raise ValueError("Invalid native handoff receipt")
    result = deepcopy(value)
    if not grant:
        calls = []
        for row in value["calls"]:
            if isinstance(row, dict) and row.get("tool") == "browser_deliver_material":
                calls.append(validate_native_material_metadata(row))
            elif _valid_handoff_call(row):
                calls.append(deepcopy(row))
            else:
                raise ValueError("Invalid native handoff call")
        if len({call["call_id"] for call in calls}) != len(calls):
            raise ValueError("Duplicate native handoff call")
        result["calls"] = calls
    if len(json.dumps(result, allow_nan=False).encode()) > 256_000:
        raise ValueError("Native handoff receipt exceeds its limit")
    return result


def validate_native_assistance_policy(value):
    """Admit only the reviewed native candidate and the fixed borrowed tool ceiling."""
    if value is None:
        return None
    if (
        not isinstance(value, dict)
        or set(value) != {"protocol", "driver_sha256", "tools", "type_mode"}
        or value.get("protocol") != NATIVE_HANDOFF_PROTOCOL
        or not isinstance(_NATIVE_HANDOFF_DRIVER_SHA256, str)
        or re.fullmatch(r"[a-f0-9]{64}", _NATIVE_HANDOFF_DRIVER_SHA256) is None
        or value.get("driver_sha256") != _NATIVE_HANDOFF_DRIVER_SHA256
        or value.get("tools") != list(NATIVE_HANDOFF_TOOLS)
        or value.get("type_mode") != "insert_text"
    ):
        raise ValueError("Native assistance requires its reviewed driver and fixed native tools")
    return {**value, "tools": list(value["tools"])}


def reviewed_native_assistance_policy():
    """The one native policy the product may pass: the reviewed driver and fixed tools."""
    return validate_native_assistance_policy(
        {
            "protocol": NATIVE_HANDOFF_PROTOCOL,
            "driver_sha256": _NATIVE_HANDOFF_DRIVER_SHA256,
            "tools": list(NATIVE_HANDOFF_TOOLS),
            "type_mode": "insert_text",
        }
    )


def _name(value: str) -> str:
    return " ".join(re.sub(r"[✱*]", "", value).split())


class CuaMcpClient:
    """One stdio transport. Pump Playwright on the owner thread during native calls."""

    def __init__(self, command: list[str], log, *, env=None, timeout: float = 15):
        self.process = subprocess.Popen(
            command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=log,
            text=True,
            encoding="utf-8",
            env=env,
        )
        self.timeout, self.sequence, self.failed = timeout, 0, False
        self.reply_sequence = 0
        self.measurements = current_measurements()
        self.session = "tomorrowstar-" + uuid4().hex
        self.replies = queue.Queue()
        self._reader_stopped = threading.Event()

        def read():
            try:
                pending = bytearray()
                with selectors.DefaultSelector() as selector:
                    selector.register(self.process.stdout, selectors.EVENT_READ)
                    while not self._reader_stopped.is_set():
                        if not selector.select(0.1):
                            continue
                        chunk = os.read(self.process.stdout.fileno(), 65536)
                        if not chunk:
                            if pending:
                                self.replies.put(pending.decode("utf-8"))
                            break
                        pending.extend(chunk)
                        while (newline := pending.find(b"\n")) >= 0:
                            frame = bytes(pending[: newline + 1])
                            del pending[: newline + 1]
                            self.replies.put(frame.decode("utf-8"))
            except (OSError, UnicodeError):
                pass
            finally:
                self.replies.put(None)

        self._reader = threading.Thread(target=read)
        self._reader.start()
        try:
            initialized = self._rpc(
                "initialize",
                {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {"name": "tomorrowstar-worker", "version": "1"},
                },
            )
            info = initialized.get("serverInfo")
            version = info.get("version") if isinstance(info, dict) else None
            self.driver_version = version if isinstance(version, str) else None
            self._send({"jsonrpc": "2.0", "method": "notifications/initialized"})
            listed = self._rpc("tools/list", {})
            self.tools = {t["name"] for t in listed["tools"]}
            if (
                not {
                    "browser_prepare",
                    "get_browser_state",
                    "browser_click",
                    "list_windows",
                    "end_session",
                    "check_permissions",
                }
                <= self.tools
            ):
                raise PortalDataError("cua_unavailable", "Cua 工具能力不完整。", 409)
        except BaseException:
            self.failed = True
            self.close()
            raise

    def _send(self, message: dict):
        self.process.stdin.write(json.dumps(message) + "\n")
        self.process.stdin.flush()

    def _rpc(self, method: str, params: dict, pump=None) -> dict:
        if self.failed:
            raise PortalDataError("cua_result_unknown", "Cua 结果未知；不会重复操作。", 409)
        self.sequence += 1
        try:
            self._send({"jsonrpc": "2.0", "id": self.sequence, "method": method, "params": params})
            until = time.monotonic() + self.timeout
            while time.monotonic() < until:
                try:
                    line = self.replies.get(timeout=0.025)
                except queue.Empty:
                    if pump is not None:
                        pump()
                    continue
                if line is None:
                    raise ValueError("MCP disconnected")
                reply = json.loads(line)
                if reply.get("id") == self.sequence:
                    self.reply_sequence = self.sequence
                    if "error" in reply or not isinstance(reply.get("result"), dict):
                        raise ValueError("MCP error")
                    return reply["result"]
            raise TimeoutError("MCP response deadline")
        except (Exception, KeyboardInterrupt) as error:
            self.failed = True
            if isinstance(error, KeyboardInterrupt):
                raise
            raise PortalDataError(
                "cua_result_unknown", "Cua 结果未知；不会重复操作。", 409
            ) from error

    def call(self, name: str, arguments: dict, *, pump=None, owner=False) -> dict:
        measurements = current_measurements() or self.measurements
        if measurements is None:
            return self._call(name, arguments, pump=pump, owner=owner)
        before = self.sequence
        with measurements.stage("cua", tool=name) as measured:
            try:
                return self._call(name, arguments, pump=pump, owner=owner)
            finally:
                measured["dispatch"] = (
                    "acknowledged"
                    if self.reply_sequence > before
                    else "unknown"
                    if self.sequence > before
                    else "not_sent"
                )

    def _call(self, name: str, arguments: dict, *, pump=None, owner=False) -> dict:
        args = dict(arguments)
        if name != "list_windows" and not owner:
            args["session"] = self.session
        result = self._rpc("tools/call", {"name": name, "arguments": args}, pump)
        data = result.get("structuredContent", {})
        if not isinstance(data, dict):
            self.failed = True
            raise PortalDataError("cua_result_unknown", "Cua 回执不能核验；不会重复操作。", 409)
        if (
            result.get("isError")
            or data.get("refusal")
            or data.get("status") in {"refused", "error"}
        ):
            raise PortalDataError(
                "cua_refused", data.get("refusal", {}).get("message", "Cua 拒绝该操作。"), 409
            )
        return data

    def close(self):
        try:
            if self.process.poll() is None:
                if not self.failed:
                    with suppress(PortalDataError, OSError):
                        self.call("end_session", {})
                with suppress(OSError):
                    self.process.stdin.close()
                try:
                    self.process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    self.process.terminate()
                    try:
                        self.process.wait(timeout=3)
                    except subprocess.TimeoutExpired:
                        self.process.kill()
                        self.process.wait(timeout=3)
        finally:
            self._reader_stopped.set()
            self._reader.join()
            self.process.stdout.close()
            with suppress(OSError):
                self.process.stdin.close()


def verify_native_handoff_recipient(
    ready,
    *,
    expected_request_id,
    expected_socket,
    application_ref_digest,
    appserver_identity,
    driver_executable,
):
    """Verify a daemon connection's process; the ready JSON itself grants nothing."""
    fields = {
        "protocol",
        "request_id",
        "socket_path",
        "application_ref_digest",
        "status",
        "connection_id",
        "peer_pid",
        "proxy_pid",
    }
    if (
        not isinstance(ready, dict)
        or set(ready) != fields
        or ready.get("protocol") != NATIVE_HANDOFF_PROTOCOL
        or ready.get("status") != "pending"
        or ready.get("request_id") != expected_request_id
        or ready.get("socket_path") != str(expected_socket)
        or ready.get("application_ref_digest") != application_ref_digest
        or not isinstance(application_ref_digest, str)
        or re.fullmatch(r"[a-f0-9]{64}", application_ref_digest) is None
        or not isinstance(ready.get("connection_id"), str)
        or not 1 <= len(ready["connection_id"]) <= 200
        or not ready["connection_id"].isprintable()
        or type(ready.get("peer_pid")) is not int
        or not 0 < ready["peer_pid"] <= 0xFFFFFFFF
        or type(ready.get("proxy_pid")) is not int
        or ready["proxy_pid"] != ready["peer_pid"]
        or not valid_process_identity(appserver_identity)
        or not Path(driver_executable).is_absolute()
    ):
        raise PortalDataError("cua_recipient_unverified", "原生接管进程尚不能核验。", 409)
    pid = ready["peer_pid"]
    before = process_identity(pid)
    parent = process_parent_identity(pid)
    after = process_identity(pid)
    current_appserver = process_identity(appserver_identity["pid"])
    if (
        not valid_process_identity(before)
        or before != after
        or before["uid"] != appserver_identity["uid"]
        or before["executable"] != str(Path(driver_executable).resolve())
        or parent != appserver_identity
        or current_appserver != appserver_identity
    ):
        raise PortalDataError("cua_recipient_unverified", "原生接管进程身份或所属会话已改变。", 409)
    return before


class NativeCuaSessionClient:
    """Original embedded host's native service connection, without an MCP proxy.

    The daemon retains the browser and executes its existing native tools. A
    lost response never causes this client to repeat an action or start a session.
    """

    native_session = True
    _MAX_FRAME = 2_000_000

    def __init__(
        self, socket_path, process, options, *, driver_sha256, driver_executable=None, timeout=15
    ):
        if (
            type(timeout) not in (int, float)
            or not math.isfinite(timeout)
            or not 0 < timeout <= 120
            or not isinstance(_NATIVE_HANDOFF_DRIVER_SHA256, str)
            or re.fullmatch(r"[a-f0-9]{64}", _NATIVE_HANDOFF_DRIVER_SHA256) is None
            or driver_sha256 != _NATIVE_HANDOFF_DRIVER_SHA256
        ):
            raise PortalDataError(
                "cua_native_candidate_unverified", "原生接管驱动尚未通过本轮核验。", 409
            )
        if (
            not isinstance(options, dict)
            or set(options)
            != {
                "public_session",
                "mode",
                "ttl_seconds",
                "idle_ttl_seconds",
                "capability_manifest_path",
                "bounded_manifest_path",
            }
            or options.get("mode") != "bounded"
            or not isinstance(options.get("public_session"), str)
            or not 1 <= len(options["public_session"]) <= 200
            or any(
                type(options[k]) is not int or not 0 < options[k] <= 86400
                for k in ("ttl_seconds", "idle_ttl_seconds")
            )
            or not isinstance(options.get("capability_manifest_path"), str)
            or not Path(options["capability_manifest_path"]).is_absolute()
            or options.get("bounded_manifest_path") is not None
            or type(getattr(process, "pid", None)) is not int
            or process.pid <= 0
            or not callable(getattr(process, "poll", None))
        ):
            raise ValueError("Choose an explicit bounded native host session")
        self.socket_path = str(socket_path)
        self.process, self.timeout = process, timeout
        self.driver_sha256 = driver_sha256
        self.driver_executable = None
        if driver_executable is not None:
            binary = Path(driver_executable)
            if (
                not binary.is_absolute()
                or binary.is_symlink()
                or not binary.is_file()
                or hashlib.sha256(binary.read_bytes()).hexdigest() != driver_sha256
            ):
                raise PortalDataError(
                    "cua_native_candidate_unverified", "原生驱动身份已改变。", 409
                )
            self.driver_executable = str(binary.resolve())
        self.session = options["public_session"]
        self.failed = False
        self.sequence = self.reply_sequence = 0
        self.measurements = current_measurements()
        self._socket = None
        self._closed = False
        self._lock = threading.Lock()
        self._resume_credential = None
        self._yield_attempt = None
        self._handoff = None
        self._handoff_transition_inflight = False
        self._control_depth = 0
        self._control_pumping = False
        try:
            self._socket = self._connect()
            metadata = self._request({"method": "metadata"})
            if (
                not isinstance(metadata, dict)
                or metadata.get("pid") != process.pid
                or type(metadata.get("pid")) is not int
                or metadata.get("embedded") is not True
                or metadata.get("trusted_session_handoff_protocol") != NATIVE_HANDOFF_PROTOCOL
                or metadata.get("trusted_session_handoff_supported") is not True
                or any(
                    type(metadata.get(k)) is not int or metadata[k] <= 0
                    for k in ("max_session_ttl_seconds", "max_idle_ttl_seconds")
                )
                or options["ttl_seconds"] > metadata["max_session_ttl_seconds"]
                or options["idle_ttl_seconds"] > metadata["max_idle_ttl_seconds"]
                or any(
                    metadata.get(key) != value
                    for key, value in {
                        "driver_version": "0.35.4",
                        "contract_version": "0.8.0",
                        "tools_list_schema_version": "1",
                        "capability_version": "1",
                        "mcp_protocol_version": "2025-06-18",
                    }.items()
                )
            ):
                raise ValueError("Native daemon identity or handoff contract changed")
            self.driver_version = metadata["driver_version"]
            catalog = self._request({"method": "list"})
            tools = catalog.get("tools") if isinstance(catalog, dict) else None
            if not isinstance(tools, list) or any(
                not isinstance(tool, dict) or not isinstance(tool.get("name"), str)
                for tool in tools
            ):
                raise ValueError("Invalid native tool catalog")
            self.tools = {tool["name"] for tool in tools}
            if (
                not {
                    "browser_prepare",
                    "get_browser_state",
                    "browser_click",
                    "browser_type",
                    "browser_set_input_files",
                    "end_session",
                    "check_permissions",
                }
                <= self.tools
            ):
                raise ValueError("Native host tool surface is incomplete")
            bound = self._request(
                {"method": "trusted_session_begin", "args": options, "client_kind": "python_sdk"}
            )
            self._adopt_bound(bound)
        except BaseException as error:
            self.failed = True
            self._close_socket()
            if isinstance(error, (KeyboardInterrupt, PortalDataError)):
                raise
            raise PortalDataError(
                "cua_native_session_unavailable", "原生会话身份或能力尚不能核验。", 409
            ) from error

    def _connect(self, *, timeout=None):
        timeout = self._control_timeout(timeout)
        if sys.platform not in {"darwin", "linux"}:
            raise PortalDataError("cua_native_session_unsupported", "本机尚无原生接管连接。", 409)
        path = Path(self.socket_path)
        before = path.lstat()
        parent = path.parent.stat()
        if (
            not path.is_absolute()
            or path.is_symlink()
            or path.parent.is_symlink()
            or not stat.S_ISSOCK(before.st_mode)
            or before.st_uid != os.getuid()
            or parent.st_uid != os.getuid()
            or stat.S_IMODE(parent.st_mode) & 0o077
            or self.process.poll() is not None
        ):
            raise ValueError("Native daemon socket is not privately owned")
        stream = local_socket.socket(local_socket.AF_UNIX, local_socket.SOCK_STREAM)
        try:
            stream.settimeout(timeout)
            stream.connect(self.socket_path)
            if sys.platform == "darwin":
                peer_pid = struct.unpack("i", stream.getsockopt(0, 2, struct.calcsize("i")))[0]
                import ctypes

                uid, gid = ctypes.c_uint32(), ctypes.c_uint32()
                libc = ctypes.CDLL(None, use_errno=True)
                libc.getpeereid.argtypes = [ctypes.c_int, ctypes.c_void_p, ctypes.c_void_p]
                libc.getpeereid.restype = ctypes.c_int
                if libc.getpeereid(stream.fileno(), ctypes.byref(uid), ctypes.byref(gid)) != 0:
                    raise OSError("Native daemon peer UID unavailable")
                peer_uid = uid.value
            else:
                peer_pid, peer_uid, _ = struct.unpack(
                    "3i", stream.getsockopt(local_socket.SOL_SOCKET, local_socket.SO_PEERCRED, 12)
                )
            after = path.lstat()
            if (
                peer_pid != self.process.pid
                or peer_uid != os.getuid()
                or (before.st_dev, before.st_ino) != (after.st_dev, after.st_ino)
            ):
                raise ValueError("Native daemon peer identity changed")
            stream.setblocking(False)
            return stream
        except BaseException:
            stream.close()
            raise

    def _adopt_bound(self, value):
        if (
            not isinstance(value, dict)
            or value.get("bound") is not True
            or value.get("connection_bound") is not True
            or not isinstance(value.get("resume_credential"), str)
            or not 1 <= len(value["resume_credential"]) <= 256
        ):
            raise ValueError("Native session bind omitted its original-host continuation")
        self._resume_credential = value["resume_credential"]

    def _exchange(self, stream, message, *, pump=None, timeout=None):
        data = (json.dumps(message, ensure_ascii=False, allow_nan=False) + "\n").encode("utf-8")
        if len(data) > self._MAX_FRAME:
            raise ValueError("Native request exceeds limit")
        self.sequence += 1
        deadline = time.monotonic() + self._control_timeout(timeout)
        sent = 0
        pending = bytearray()
        with selectors.DefaultSelector() as selector:
            selector.register(stream, selectors.EVENT_WRITE)
            while sent < len(data):
                if time.monotonic() >= deadline:
                    raise TimeoutError("native service request deadline")
                if pump is not None and pump() is False:
                    raise PortalDataError("cua_stopped", "原生调用已停止。", 409)
                if not selector.select(min(0.025, max(0, deadline - time.monotonic()))):
                    continue
                if time.monotonic() >= deadline:
                    raise TimeoutError("native service request deadline")
                try:
                    written = stream.send(data[sent:])
                    if written == 0:
                        raise EOFError("native service connection closed")
                    sent += written
                except BlockingIOError:
                    continue
            selector.modify(stream, selectors.EVENT_READ)
            while time.monotonic() < deadline:
                # The owner pump fills only idle waits: it took 1.3-3.1 s per call
                # while the driver answered within its own 0.25 s idle wait (2026-11-02).
                if not selector.select(min(0.25, max(0, deadline - time.monotonic()))):
                    if pump is not None and pump() is False:
                        raise PortalDataError("cua_stopped", "原生调用已停止。", 409)
                    if not selector.select(min(0.025, max(0, deadline - time.monotonic()))):
                        continue
                if time.monotonic() >= deadline:
                    raise TimeoutError("native service response deadline")
                try:
                    chunk = stream.recv(65536)
                except BlockingIOError:
                    continue
                if not chunk:
                    raise EOFError("native service connection closed")
                pending.extend(chunk)
                if len(pending) > self._MAX_FRAME:
                    raise ValueError("Native response exceeds limit")
                if b"\n" not in pending:
                    continue
                line, remainder = pending.split(b"\n", 1)
                if remainder:
                    raise ValueError("Unexpected native service frame")
                value = json.loads(line)
                if not isinstance(value, dict) or type(value.get("ok")) is not bool:
                    raise ValueError("Invalid native service response")
                self.reply_sequence = self.sequence
                if not value["ok"]:
                    # The driver's refusal code stays as the private cause only.
                    raise PortalDataError("cua_refused", "原生驱动拒绝本次操作。", 409) from (
                        ValueError(str(value.get("error"))[:200])
                    )
                return value.get("result")
        raise TimeoutError("native service response deadline")

    def _request(self, message, *, pump=None):
        if self.failed or self._closed or self._socket is None or self.process.poll() is not None:
            raise PortalDataError("cua_result_unknown", "Cua 结果未知；不会重复操作。", 409)
        if not self._lock.acquire(blocking=False):
            raise PortalDataError("cua_request_in_flight", "原生调用尚未结束。", 409)
        try:
            return self._exchange(self._socket, message, pump=pump)
        except (Exception, KeyboardInterrupt) as error:
            self.failed = True
            self._close_socket()
            if isinstance(error, KeyboardInterrupt):
                raise
            raise PortalDataError(
                "cua_result_unknown", "Cua 结果未知；不会重复操作。", 409
            ) from error
        finally:
            self._lock.release()

    def call(self, name, arguments, *, pump=None, owner=False):
        # Reuse the existing measurement wrapper; _call keeps the native wire path.
        return CuaMcpClient.call(self, name, arguments, pump=pump, owner=owner)

    def _call(self, name, arguments, *, pump=None, owner=False):
        if self._yield_attempt is not None:
            raise PortalDataError("cua_session_yielded", "原生页面权限已交出，脚本不能操作。", 409)
        if not isinstance(name, str) or name not in self.tools or not isinstance(arguments, dict):
            raise ValueError("Choose an existing native tool with JSON arguments")
        args = dict(arguments)
        if name != "list_windows" and not owner:
            args["session"] = self.session
        result = self._request(
            {"method": "trusted_session_call", "name": name, "args": args}, pump=pump
        )
        if not isinstance(result, dict) or not isinstance(
            result.get("structuredContent", {}), dict
        ):
            self.failed = True
            raise PortalDataError("cua_result_unknown", "Cua 回执不能核验；不会重复操作。", 409)
        data = result.get("structuredContent", {})
        if (
            result.get("isError")
            or data.get("refusal")
            or data.get("status") in {"refused", "error"}
        ):
            raise PortalDataError("cua_refused", "Cua 拒绝该操作。", 409)
        return data

    @property
    def handoff_active(self):
        return self._yield_attempt is not None

    @property
    def handoff_transition_inflight(self):
        return self._handoff_transition_inflight

    @property
    def control_inflight(self):
        return self._control_depth > 0

    def _control_timeout(self, timeout):
        value = self.timeout if timeout is None else timeout
        if (
            type(value) not in (int, float)
            or not math.isfinite(value)
            or not 0 < value <= self.timeout
        ):
            raise ValueError("Native control timeout must be positive and within the action bound")
        return value

    def _control_request(self, message, *, pump=None, timeout=None):
        """The original host can revoke while the borrowed action stream is busy."""
        if self._closed or self.process.poll() is not None:
            raise PortalDataError("cua_handoff_unknown", "原生接管控制连接已失效。", 409)
        timeout = self._control_timeout(timeout)
        deadline = time.monotonic() + timeout
        stream = None
        self._control_depth += 1

        def control_pump():
            if pump is None or self._control_pumping:
                return
            self._control_pumping = True
            try:
                return pump()
            finally:
                self._control_pumping = False

        try:
            stream = self._connect(timeout=timeout)
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError("native control connection deadline")
            return self._exchange(stream, message, pump=control_pump, timeout=remaining)
        except (Exception, KeyboardInterrupt) as error:
            self.failed = True
            if isinstance(error, KeyboardInterrupt):
                raise
            raise PortalDataError("cua_handoff_unknown", "原生接管控制结果未知。", 409) from error
        finally:
            self._control_depth -= 1
            if stream is not None:
                stream.close()

    def _adopt_handoff(self, value):
        receipt = None
        expected = {*HANDOFF_GRANT_FIELDS, "yielded", "host_return_credential"}
        if isinstance(value, dict) and set(value) == expected:
            try:
                receipt = validate_handoff_receipt(
                    {k: v for k, v in value.items() if k != "host_return_credential"}, grant=True
                )
            except ValueError:
                receipt = None
        if (
            receipt is None
            or receipt["local_tools_drained"] is not True
            or not isinstance(value.get("host_return_credential"), str)
            or not 1 <= len(value["host_return_credential"]) <= 256
        ):
            self.failed = True
            raise PortalDataError("cua_handoff_unknown", "原生交接回执尚不能核验。", 409)
        self._return_credential = value["host_return_credential"]
        self._handoff = receipt
        return dict(self._handoff)

    _valid_borrow_scope = staticmethod(valid_page_scope)

    def yield_to(
        self,
        ready,
        *,
        request_id,
        scope,
        application_ref_digest,
        appserver_identity,
        driver_executable,
        pump=None,
    ):
        recipient = verify_native_handoff_recipient(
            ready,
            expected_request_id=request_id,
            expected_socket=self.socket_path,
            application_ref_digest=application_ref_digest,
            appserver_identity=appserver_identity,
            driver_executable=driver_executable,
        )
        if (
            not isinstance(request_id, str)
            or not 1 <= len(request_id) <= 128
            or not request_id.isprintable()
            or not self._valid_borrow_scope(scope)
        ):
            raise ValueError("Choose an exact original-page native handoff")
        args = {
            "connection_id": ready["connection_id"],
            "expected_peer_pid": recipient["pid"],
            "request_id": request_id,
            "scope": deepcopy(scope),
            "application_ref_digest": application_ref_digest,
        }
        if self._yield_attempt is not None:
            if self._yield_attempt != args:
                raise PortalDataError("cua_handoff_conflict", "原交接请求不能更换范围。", 409)
            if self._handoff is not None:
                return dict(self._handoff)
            raise PortalDataError("cua_handoff_unknown", "原交接结果未知，请先核对。", 409)
        self._yield_attempt = args
        self._handoff_transition_inflight = True
        try:
            result = self._request({"method": "trusted_session_yield", "args": args}, pump=pump)
            handoff = self._adopt_handoff(result)
            self._close_socket()
            return handoff
        finally:
            self._handoff_transition_inflight = False

    def reconcile_handoff(self, *, pump=None, timeout=None):
        """Query the exact original host request; daemon idempotency never regrants it."""
        if self._yield_attempt is None:
            raise PortalDataError("cua_handoff_missing", "没有待核对的原生交接。", 409)
        result = self._control_request(
            {"method": "trusted_session_yield", "args": dict(self._yield_attempt)},
            pump=pump,
            timeout=timeout,
        )
        handoff = self._adopt_handoff(result)
        self._close_socket()
        self.failed = False
        return handoff

    def _handoff_status(self, value):
        try:
            value = validate_handoff_receipt(value)
        except ValueError:
            value = None
        if value is None or (
            self._handoff is not None
            and any(value[k] != self._handoff[k] for k in ("handoff_id", "generation"))
        ):
            raise PortalDataError("cua_handoff_unknown", "原生接管排空状态不能核验。", 409)
        return value

    def handoff_status(self, *, pump=None, timeout=None):
        if self._yield_attempt is None:
            raise PortalDataError("cua_handoff_missing", "没有原生交接记录。", 409)
        args = (
            {"handoff_id": self._handoff["handoff_id"]}
            if self._handoff
            else {"request_id": self._yield_attempt["request_id"]}
        )
        return self._handoff_status(
            self._control_request(
                {"method": "trusted_session_handoff_status", "args": args},
                pump=pump,
                timeout=timeout,
            )
        )

    def revoke_handoff(self, *, pump=None, timeout=None):
        budget = self._control_timeout(timeout)
        started = time.monotonic()
        handoff = self._handoff or self.handoff_status(pump=pump, timeout=budget)
        remaining = budget - (time.monotonic() - started)
        if remaining <= 0:
            raise PortalDataError("cua_handoff_unknown", "原生撤权尚未在期限内确认。", 409)
        return self._handoff_status(
            self._control_request(
                {
                    "method": "trusted_session_handoff_revoke",
                    "args": {"handoff_id": handoff["handoff_id"]},
                },
                pump=pump,
                timeout=remaining,
            )
        )

    def admit_call(
        self,
        call_id,
        arguments_digest,
        decision,
        *,
        material_resolution=None,
        pump=None,
        timeout=None,
    ):
        """Acknowledge the native intent only; the native daemon performs the operation."""
        if (
            self._handoff is None
            or self._handoff.get("yielded") is not True
            or not isinstance(call_id, str)
            or not 1 <= len(call_id) <= 128
            or not isinstance(arguments_digest, str)
            or re.fullmatch(r"[a-f0-9]{64}", arguments_digest) is None
            or not isinstance(decision, str)
            or decision not in {"allow", "deny"}
        ):
            raise PortalDataError("cua_handoff_invalid", "原生动作授权记录无效。", 409)
        material = {}
        if material_resolution is not None:
            try:
                if decision != "allow":
                    raise ValueError("Material payload requires admission")
                material["material_resolution"] = validate_fixed_material_resolution(
                    material_resolution
                )
            except ValueError:
                raise PortalDataError(
                    "cua_handoff_invalid", "原生材料授权记录无效。", 409
                ) from None
        return self._handoff_status(
            self._control_request(
                {
                    "method": "trusted_session_handoff_admit",
                    "args": {
                        "handoff_id": self._handoff["handoff_id"],
                        "call_id": call_id,
                        "arguments_digest": arguments_digest,
                        "decision": decision,
                        **material,
                    },
                },
                pump=pump,
                timeout=timeout,
            )
        )

    def resume_after_handoff(self, *, pump=None):
        if self.failed or self._handoff is None:
            raise PortalDataError("cua_handoff_unknown", "原生交接结果仍需核对。", 409)
        status = self.handoff_status(pump=pump)
        if not status["return_ready"] or not status["local_tools_drained"]:
            raise PortalDataError("cua_handoff_pending", "原生调用尚未排空或未交回。", 409)
        self._close_socket()
        self._socket = self._connect()
        bound = self._request(
            {
                "method": "trusted_session_resume",
                "args": {"resume_credential": self._return_credential},
            },
            pump=pump,
        )
        self._adopt_bound(bound)
        self._handoff = self._yield_attempt = None
        self._return_credential = None

    def _close_socket(self):
        if self._socket is not None:
            self._socket.close()
            self._socket = None

    def close(self):
        if self._closed:
            return
        try:
            if self._yield_attempt is not None:
                self.revoke_handoff(timeout=min(DEFAULT_BUDGET.stop, self.timeout))
            elif not self.failed:
                result = self._request({"method": "trusted_session_end"})
                if not isinstance(result, dict) or result.get("closed") is not True:
                    raise PortalDataError("cua_cleanup_unknown", "原生会话尚未确认关闭。", 409)
        finally:
            self._closed = True
            self._close_socket()


class NativeHandoffPort:
    """The narrow Interface the Codex Adapter holds for one native handoff.

    It yields the original page, admits or denies one call, reads and revokes the
    handoff, and says whether a control request is in flight. Every receipt it returns
    passed `validate_handoff_receipt`; nothing else of the session is reachable.
    """

    def __init__(self, client):
        if getattr(client, "native_session", False) is not True:
            raise ValueError("A native handoff needs the original native session")
        self._client = client

    @property
    def driver_sha256(self):
        return self._client.driver_sha256

    @property
    def driver_executable(self):
        return self._client.driver_executable

    @property
    def socket_path(self):
        return self._client.socket_path

    @property
    def action_timeout(self):
        """The session's own action bound; no control deadline may exceed it."""
        return self._client.timeout

    @property
    def control_busy(self):
        """A yield or control request is in flight; a reentrant query must wait."""
        return bool(self._client.handoff_transition_inflight or self._client.control_inflight)

    @staticmethod
    def _checked(value, *, grant=False):
        try:
            receipt = validate_handoff_receipt(value, grant=grant)
        except ValueError:
            raise PortalDataError("cua_handoff_unknown", "原生交接回执不能核验。", 409) from None
        if grant and "yielded" not in receipt:
            raise PortalDataError("cua_handoff_unknown", "原生交接回执不能核验。", 409)
        return receipt

    def yield_to(self, ready, **options):
        return self._checked(self._client.yield_to(ready, **options), grant=True)

    def handoff_status(self, *, pump=None, timeout=None):
        return self._checked(self._client.handoff_status(pump=pump, timeout=timeout))

    def revoke_handoff(self, *, pump=None, timeout=None):
        return self._checked(self._client.revoke_handoff(pump=pump, timeout=timeout))

    def admit_call(self, call_id, arguments_digest, decision, **options):
        return self._checked(
            self._client.admit_call(call_id, arguments_digest, decision, **options)
        )


def native_handoff_port(client):
    """The handoff Interface of an original native session, or None for any other client."""
    return NativeHandoffPort(client) if getattr(client, "native_session", False) is True else None


def mac_chrome_state(
    pid: int, *, launch_date=None, action="read", windows=False, timeout=3
) -> dict:
    """Control one launch generation through AppKit. Never target a bundle-wide instance."""
    script = """ObjC.import('AppKit');
function run(args) {
 const pid=Number(args[0]), expected=Number(args[1]), action=args[2];
 const app=$.NSRunningApplication.runningApplicationWithProcessIdentifier(pid);
 if (Number(app.processIdentifier)!==pid || ObjC.unwrap(app.bundleIdentifier)!=='com.google.Chrome')
   throw Error('Owned Chrome unavailable');
 const date=Number(app.launchDate.timeIntervalSince1970);
 if (!date || (expected && expected!==date)) throw Error('Chrome launch identity changed');
 if(action==='hide' && !app.hidden) app.hide;
 if(action==='show' && app.hidden) app.unhide;
 const until=Date.now()+1500;
 while(action!=='read' && Boolean(app.hidden)!==(action==='hide') && Date.now()<until)
   $.NSRunLoop.currentRunLoop.runUntilDate($.NSDate.dateWithTimeIntervalSinceNow(0.025));
 if(action!=='read' && Boolean(app.hidden)!==(action==='hide')) throw Error('Visibility unknown');
 const result={pid,launch_date:date,hidden:Boolean(app.hidden),active:Boolean(app.active)};
 if(args[3]==='windows') {
   ObjC.import('CoreGraphics');
   const rows=ObjC.deepUnwrap(ObjC.castRefToObject($.CGWindowListCopyWindowInfo(0,0)));
   result.windows=rows.filter(w=>Number(w.kCGWindowOwnerPID)===pid && Number(w.kCGWindowLayer)===0)
     .map(w=>({pid,window_id:Number(w.kCGWindowNumber),title:w.kCGWindowName||'',
               is_on_screen:Boolean(w.kCGWindowIsOnscreen)}));
 }
 return JSON.stringify(result);
}"""
    try:
        return json.loads(
            subprocess.check_output(
                [
                    "/usr/bin/osascript",
                    "-l",
                    "JavaScript",
                    "-e",
                    script,
                    str(pid),
                    str(launch_date or 0),
                    action,
                    "windows" if windows else "",
                ],
                text=True,
                stderr=subprocess.PIPE,
                timeout=timeout,
            )
        )
    except (subprocess.SubprocessError, ValueError) as error:
        raise PortalDataError(
            "cua_visibility_unknown", "受管浏览器身份或显示状态不能核验。", 409
        ) from error


@contextmanager
def managed_cua_client(
    driver, socket, manifest, log, env, *, embedded=False, trusted_session=False
):
    """One private bounded daemon. An exact generated scope contains no global profile grant."""
    if type(trusted_session) is not bool or trusted_session and not embedded:
        raise ValueError("A native trusted session requires the original embedded host")
    native_digest = None
    if trusted_session:
        binary = Path(driver)
        if (
            not _NATIVE_HANDOFF_DRIVER_SHA256
            or binary.is_symlink()
            or not binary.is_file()
            or hashlib.sha256(binary.read_bytes()).hexdigest() != _NATIVE_HANDOFF_DRIVER_SHA256
        ):
            raise PortalDataError(
                "cua_native_candidate_unverified", "原生接管驱动尚未通过本轮核验。", 409
            )
        native_digest = _NATIVE_HANDOFF_DRIVER_SHA256
    path = Path(socket).with_suffix(".json")
    manifest.setdefault("expires_after", "24h")
    manifest.setdefault("idle_timeout", "1h" if trusted_session else "24h")
    native_durations = {}
    if trusted_session:
        for key in ("expires_after", "idle_timeout"):
            value = manifest[key]
            match = (
                re.fullmatch(r"([0-9]+)([smh])", value.strip()) if isinstance(value, str) else None
            )
            if not match:
                raise ValueError("Native capability durations require integer s/m/h units")
            native_durations[key] = int(match[1]) * {"s": 1, "m": 60, "h": 3600}[match[2]]
        if not 0 < native_durations["idle_timeout"] <= native_durations["expires_after"] <= 86400:
            raise ValueError("Native capability lifetime is invalid")
    helper.atomic_write_json(path, manifest)
    client, launched, backend = None, False, None
    try:
        serve_args = [
            "serve",
            "--socket",
            socket,
            "--permission-mode",
            "bounded",
            "--capability-manifest",
            str(path),
            "--approve-capability-manifest",
            "--no-overlay",
            "--no-permissions-gate",
        ]
        if embedded:
            backend = subprocess.Popen(
                [
                    str(driver),
                    *serve_args,
                    "--embedded",
                    "--pid-file",
                    str(Path(socket).with_suffix(".pid")),
                ],
                env=env,
                stdout=log,
                stderr=log,
            )
        else:
            subprocess.run(
                [
                    "open",
                    "-n",
                    "-g",
                    "-j",
                    "-a",
                    "/Applications/CuaDriver.app",
                    "--args",
                    *serve_args,
                ],
                env=env,
                stdout=log,
                stderr=log,
                check=True,
                timeout=10,
            )
        launched = True
        until = time.monotonic() + 10
        while not Path(socket).exists() and time.monotonic() < until:
            if backend is not None and backend.poll() is not None:
                break
            time.sleep(0.05)
        if not Path(socket).exists():
            raise PortalDataError("cua_unavailable", "Cua 独立服务未启动。", 409)
        if trusted_session:
            client = NativeCuaSessionClient(
                socket,
                backend,
                {
                    "public_session": "tomorrowstar-" + uuid4().hex,
                    "mode": "bounded",
                    "ttl_seconds": native_durations["expires_after"],
                    "idle_ttl_seconds": min(native_durations["idle_timeout"], 3600),
                    "capability_manifest_path": str(path),
                    "bounded_manifest_path": None,
                },
                driver_sha256=native_digest,
                driver_executable=str(Path(driver).resolve()),
            )
        else:
            client = CuaMcpClient(
                [str(driver), "mcp", *(["--embedded"] if embedded else []), "--socket", socket],
                log,
                env=env,
            )
        permissions = client.call("check_permissions", {})
        if not permissions.get("accessibility") or not permissions.get("screen_recording"):
            raise PortalDataError(
                "cua_permissions_required", "CuaDriver 缺少辅助功能或录屏权限。", 409
            )
        if backend is not None and permissions.get("source", {}).get("pid") != backend.pid:
            raise PortalDataError("cua_binding_ambiguous", "Cua 服务身份不能核验。", 409)
        yield client, permissions
    finally:
        try:
            if client is not None:
                client.close()
        finally:
            try:
                if launched:
                    stopped = subprocess.run(
                        [str(driver), "stop", "--socket", socket],
                        env=env,
                        stdout=log,
                        stderr=log,
                        timeout=10,
                    )
                    if stopped.returncode and Path(socket).exists():
                        raise PortalDataError(
                            "cua_cleanup_unknown", "本次 Cua 服务未确认停止。", 409
                        )
            finally:
                if backend is not None:
                    try:
                        backend.wait(timeout=3)
                    except subprocess.TimeoutExpired:
                        backend.terminate()
                        try:
                            backend.wait(timeout=3)
                        except subprocess.TimeoutExpired:
                            backend.kill()
                            backend.wait(timeout=3)


@contextmanager
def managed_hidden_chrome(playwright, temporary, driver, log, env):
    """LaunchServices hides a fresh windowless Chrome before any target can be created."""
    profile = Path(temporary) / "chrome-profile"
    pid, identity = None, None
    started = time.monotonic_ns()

    def trace(stage, **facts):
        now = time.monotonic_ns()
        log.write(
            json.dumps(
                {
                    "event": "cua_startup",
                    "stage": stage,
                    "utc_ns": time.time_ns(),
                    "monotonic_ns": now,
                    "elapsed_ns": now - started,
                    "pid": pid,
                    **facts,
                }
            )
            + "\n"
        )
        log.flush()

    port_seen = False
    try:
        trace("launch_requested")
        subprocess.run(
            [
                "open",
                "-n",
                "-g",
                "-j",
                "-a",
                "/Applications/Google Chrome.app",
                "--args",
                f"--user-data-dir={profile}",
                "--remote-debugging-port=0",
                "--no-startup-window",
                "--no-first-run",
                "--no-default-browser-check",
                "--disable-background-networking",
                "--disable-component-update",
                "--disable-extensions",
            ],
            env=env,
            stdout=log,
            stderr=log,
            check=True,
            timeout=10,
        )
        trace("launch_returned")
        until = time.monotonic() + 10
        while time.monotonic() < until:
            if pid is None and (profile / "SingletonLock").is_symlink():
                pid = int((profile / "SingletonLock").readlink().name.rsplit("-", 1)[1])
                trace("singleton_lock")
            if pid is not None and identity is None:
                # LaunchServices may register the process after Chrome writes its lock.
                trace("hide_requested")
                try:
                    identity = mac_chrome_state(pid, action="hide")
                except PortalDataError as error:
                    trace("hide_unconfirmed", code=error.code)
                else:
                    trace("hide_confirmed", application=identity)
            if not port_seen and (profile / "DevToolsActivePort").exists():
                port_seen = True
                trace("devtools_port_ready")
            if identity is not None and port_seen:
                break
            time.sleep(0.05)
        if identity is None or not (profile / "DevToolsActivePort").exists():
            raise PortalDataError("cua_unavailable", "受管浏览器未确认启动。", 409)
        port = int((profile / "DevToolsActivePort").read_text().splitlines()[0])
        listeners = subprocess.check_output(
            ["lsof", "-nP", "-a", "-p", str(pid), "-iTCP", "-sTCP:LISTEN", "-Fn"],
            text=True,
            timeout=5,
        )
        if set(re.findall(r"^n127\.0\.0\.1:([0-9]+)$", listeners, re.MULTILINE)) != {str(port)}:
            raise PortalDataError("cua_binding_ambiguous", "受管端点与新 profile 不符。", 409)
        trace("endpoint_confirmed", port=port)
        read_manifest = {
            "version": 3,
            "allow": {"tools": ["check_permissions", "list_windows", "end_session"]},
            "resources": {"desktop": {"applications": [pid]}},
        }
        trace("discovery_requested")
        with managed_cua_client(
            driver, str(Path(temporary) / "discovery.sock"), read_manifest, log, env
        ) as (client, permissions):
            daemon_pid = permissions["source"]["pid"]
            trace("discovery_ready", discovery_daemon_pid=daemon_pid)
            trace("windowless_read_requested")
            before = client.call("list_windows", {"pid": pid})["windows"]
            trace("windowless_read_complete", windowless_before=before, application=identity)
            if any(w["is_on_screen"] for w in before):
                trace("windowless_rejected", discovery_daemon_pid=daemon_pid)
                # These reads preserve the rejection. Never hide again or retry startup.
                # A failed diagnostic read must not replace the original guard error.
                for stage, key, read in (
                    (
                        "failure_appkit",
                        "application",
                        lambda: mac_chrome_state(pid, launch_date=identity["launch_date"]),
                    ),
                    (
                        "failure_windows",
                        "windows",
                        lambda: client.call("list_windows", {"pid": pid})["windows"],
                    ),
                ):
                    trace(stage + "_requested")
                    try:
                        value = read()
                    except Exception as error:
                        trace(
                            stage + "_failed",
                            error_type=type(error).__name__,
                            code=getattr(error, "code", None),
                        )
                    else:
                        trace(stage + "_complete", **{key: value})
                raise PortalDataError("cua_visibility_unknown", "无窗口启动出现了意外窗口。", 409)
            trace("windowless_accepted")
            browser = playwright.chromium.connect_over_cdp(
                f"http://127.0.0.1:{port}", timeout=10000
            )
            startup_targets = sum(len(c.pages) for c in browser.contexts)
            if startup_targets:
                raise PortalDataError("cua_visibility_unknown", "无窗口启动出现了意外页面。", 409)
            context = browser.new_context(service_workers="block", accept_downloads=False)
            anchor = CuaDriver(None, pid).new_page(context)
            anchor_title = "TS-" + uuid4().hex[:12]
            anchor.set_content("<title>" + anchor_title + "</title>")
            until = time.monotonic() + 2
            while True:
                raw_windows = client.call("list_windows", {"pid": pid})["windows"]
                log.write(
                    json.dumps(
                        {
                            "hidden_window_discovery": raw_windows,
                            "application": mac_chrome_state(pid),
                        }
                    )
                    + "\n"
                )
                log.flush()
                windows = [w for w in raw_windows if w["title"] == anchor_title]
                if windows or time.monotonic() >= until:
                    break
                anchor.wait_for_timeout(50)
            if len(windows) != 1 or windows[0]["is_on_screen"]:
                raise PortalDataError("cua_binding_ambiguous", "隐藏工作窗口不能唯一绑定。", 409)
            identity.update(
                window_id=windows[0]["window_id"],
                startup_windows=before,
                startup_target_count=startup_targets,
                profile=str(profile),
                discovery_daemon_pid=permissions["source"]["pid"],
            )
        mac_chrome_state(pid, launch_date=identity["launch_date"], action="hide")
        yield context, identity
    except BaseException as error:
        trace("startup_failed", error_type=type(error).__name__, code=getattr(error, "code", None))
        raise
    finally:
        if pid is not None and identity is not None:
            trace("cleanup_requested", launch_date=identity["launch_date"])
            try:
                os.kill(pid, 0)
            except ProcessLookupError:
                pass
            else:
                mac_chrome_state(pid, launch_date=identity["launch_date"])
                os.kill(pid, 15)
                until = time.monotonic() + 3
                while time.monotonic() < until:
                    try:
                        os.kill(pid, 0)
                    except ProcessLookupError:
                        break
                    time.sleep(0.05)
                else:
                    mac_chrome_state(pid, launch_date=identity["launch_date"])
                    os.kill(pid, 9)
                    until = time.monotonic() + 3
                    while time.monotonic() < until:
                        try:
                            os.kill(pid, 0)
                        except ProcessLookupError:
                            break
                        time.sleep(0.05)
                    else:
                        raise PortalDataError("cua_cleanup_unknown", "受管浏览器未确认停止。", 409)
            trace("cleanup_complete", launch_date=identity["launch_date"])


# Logins the user made in the worker's browser (decided 2026-10-31). Each run still
# opens a fresh context; it starts from these cookies. Only cookies are kept:
# reading site storage makes Playwright open and navigate pages to every origin.
LOGIN_STATE = "browser-login-state.json"


def load_login_state(root) -> dict | None:
    try:
        value = json.loads((Path(root) / LOGIN_STATE).read_text())
    except (OSError, ValueError):
        return None
    if not isinstance(value, dict) or not isinstance(value.get("cookies"), list):
        return None
    return {"cookies": value["cookies"], "origins": []}


def save_login_state(root, context) -> None:
    helper.atomic_write_json(
        Path(root) / LOGIN_STATE, {"cookies": context.cookies(), "origins": []}
    )


def sync_login_state(root, context, seen):
    """Adopt a login the sign-in window saved since ``seen``, then save this context."""
    path = Path(root) / LOGIN_STATE
    with suppress(OSError):
        if seen is not None and path.stat().st_mtime_ns != seen:
            saved = load_login_state(root)
            if saved:
                context.add_cookies(saved["cookies"])
    save_login_state(root, context)
    return path.stat().st_mtime_ns


@contextmanager
def managed_owned_cua_browser(
    playwright, root, driver, env, record, origins, *, trusted_session=False
):
    """Keep the implicit owner and its immutable ceiling alive across named scopes."""
    profiles = root / "cua-profiles"
    if profiles.is_symlink():
        raise PortalDataError("cua_binding_ambiguous", "Cua profile 目录不能核验。", 409)
    profiles.mkdir(mode=0o700, exist_ok=True)
    if any(profiles.iterdir()):
        raise PortalDataError("cua_binding_ambiguous", "已有 Cua profile 必须先人工核验。", 409)
    env = {
        **env,
        "CUA_DRIVER_BROWSER_PROFILE_ROOT": str(profiles),
        "CUA_DRIVER_RS_HOME": str(root / "cua-home"),
    }
    allowed = sorted(
        {
            "about:blank",
            *(
                f"{u.scheme}://{u.netloc}"
                for value in origins
                if (u := urlsplit(value)).scheme in {"http", "https"} and u.netloc
            ),
        }
    )
    scope = {
        "version": 3,
        "allow": {
            "tools": [
                "check_permissions",
                "browser_prepare",
                "get_browser_state",
                "browser_click",
                "browser_type",
                *(["browser_set_input_files"] if trusted_session else []),
                "end_session",
            ]
        },
        "resources": {
            "browser": {
                "profiles": [{"kind": "isolated_new"}],
                "origins": allowed,
                **({"fixed_material_uploads": True} if trusted_session else {}),
            }
        },
    }
    cleaned = False
    with tempfile.TemporaryDirectory(prefix="ts-cua-owned-", dir="/private/tmp") as temporary:
        socket = str(Path(temporary) / "driver.sock")
        record.update(
            socket=socket,
            profile_owner="driver",
            capability_manifest=scope,
            window_policy="hidden_until_review",
            session_refreshes=0,
        )
        descriptor = os.open(
            root / "cua.log", os.O_CREAT | os.O_APPEND | os.O_WRONLY | os.O_NOFOLLOW, 0o600
        )
        client = None
        try:
            with (
                os.fdopen(descriptor, "w") as log,
                managed_cua_client(
                    driver,
                    socket,
                    scope,
                    log,
                    env,
                    embedded=True,
                    **({"trusted_session": True} if trusted_session else {}),
                ) as (
                    client,
                    permissions,
                ),
            ):
                prepared = client.call(
                    "browser_prepare",
                    {"allow_launch": True, "profile": {"mode": "isolated_new", "windowless": True}},
                    owner=True,
                )
                pid = prepared.get("prepared_pid")
                if (
                    prepared.get("action") != "launched_isolated_browser"
                    or not isinstance(pid, int)
                    or any(
                        v
                        for k, v in prepared.get("side_effects", {}).items()
                        if k not in {"launched_browser", "created_profile"}
                    )
                ):
                    raise PortalDataError(
                        "cua_binding_ambiguous", "Cua 后台启动回执不能核验。", 409
                    )
                identity = mac_chrome_state(pid, windows=True)
                startup_windows = identity.pop("windows")
                record.update(identity, startup_windows=startup_windows)
                if (
                    not identity["hidden"]
                    or identity["active"]
                    or any(w["is_on_screen"] for w in startup_windows)
                ):
                    raise PortalDataError("cua_visibility_unknown", "Cua 后台状态不能核验。", 409)
                owned = [
                    p
                    for p in profiles.glob("isolated-*")
                    if p.is_dir()
                    and not p.is_symlink()
                    and (p / "SingletonLock").is_symlink()
                    and (p / "SingletonLock").readlink().name.rsplit("-", 1)[-1] == str(pid)
                ]
                if len(owned) != 1:
                    raise PortalDataError(
                        "cua_binding_ambiguous", "Cua profile 与 PID 不能唯一绑定。", 409
                    )
                profile = owned[0]
                port = int((profile / "DevToolsActivePort").read_text().splitlines()[0])
                listeners = subprocess.check_output(
                    ["lsof", "-nP", "-a", "-p", str(pid), "-iTCP", "-sTCP:LISTEN", "-Fn"],
                    text=True,
                    timeout=5,
                )
                if set(re.findall(r"^n127\.0\.0\.1:([0-9]+)$", listeners, re.MULTILINE)) != {
                    str(port)
                }:
                    raise PortalDataError(
                        "cua_binding_ambiguous", "Cua loopback 监听者不能核验。", 409
                    )
                browser = playwright.chromium.connect_over_cdp(
                    f"http://127.0.0.1:{port}", timeout=10000
                )
                if any(c.pages for c in browser.contexts):
                    raise PortalDataError(
                        "cua_visibility_unknown", "无窗口启动出现了意外页面。", 409
                    )
                context = browser.new_context(
                    service_workers="block",
                    accept_downloads=False,
                    **({"storage_state": saved} if (saved := load_login_state(root)) else {}),
                )
                anchor = CuaDriver(
                    None, pid, launch_date=identity["launch_date"], driver_owned=True
                ).new_page(context)
                title = "TS-" + uuid4().hex[:12]
                anchor.set_content("<title>" + title + "</title>")
                record.update(identity, profile=str(profile))
                until = time.monotonic() + 2
                while True:
                    remaining = until - time.monotonic()
                    if remaining <= 0:
                        raise PortalDataError(
                            "cua_binding_ambiguous", "Cua 隐藏窗口不能唯一绑定。", 409
                        )
                    windows = mac_chrome_state(
                        pid, launch_date=identity["launch_date"], windows=True, timeout=remaining
                    )["windows"]
                    log.write(
                        json.dumps(
                            {
                                "event": "cua_startup",
                                "stage": "owned_window_discovery",
                                "pid": pid,
                                "windows": windows,
                            }
                        )
                        + "\n"
                    )
                    log.flush()
                    matches = [w for w in windows if w["title"] == title]
                    if any(w["is_on_screen"] for w in windows) or len(matches) > 1:
                        raise PortalDataError(
                            "cua_visibility_unknown", "Cua 隐藏窗口状态不能核验。", 409
                        )
                    if time.monotonic() >= until:
                        raise PortalDataError(
                            "cua_binding_ambiguous", "Cua 隐藏窗口不能唯一绑定。", 409
                        )
                    if len(matches) == 1:
                        break
                    anchor.wait_for_timeout(min(50, max(0, (until - time.monotonic()) * 1000)))
                window_id = matches[0]["window_id"]
                idle = prepared.get("lifecycle", {}).get("idle_expires_in_seconds", 0)
                if type(idle) not in (int, float) or not 0 < idle <= (
                    3600 if trusted_session else 300
                ):
                    raise PortalDataError("cua_unavailable", "Cua owner 期限不能核验。", 409)
                record.update(
                    identity,
                    window_id=window_id,
                    profile=str(profile),
                    startup_target_count=0,
                    startup_windows=startup_windows,
                    daemon_pid=permissions["source"]["pid"],
                    owner_idle_seconds=idle,
                )
                last_owner = time.monotonic()
                started = last_owner

                def maintain_owner(*, pump=None):
                    nonlocal last_owner
                    if trusted_session and (
                        client.handoff_transition_inflight or client.control_inflight
                    ):
                        return
                    if trusted_session and client.handoff_active:
                        client.handoff_status(pump=pump)
                        return
                    if client.failed:
                        return
                    now = time.monotonic()
                    if 0 <= now - last_owner < min(60, idle / 3):
                        return
                    if now < last_owner:
                        raise PortalDataError(
                            "cua_scope_expired", "Cua 时钟发生回退；请核验运行。", 409
                        )
                    client.call(
                        "get_browser_state",
                        {"pid": pid, "window_id": window_id},
                        owner=True,
                        pump=pump or (lambda: anchor.wait_for_timeout(0)),
                    )
                    last_owner = time.monotonic()

                def ensure_scope(url, *, force=False):
                    nonlocal started
                    if client.failed:
                        raise PortalDataError(
                            "cua_result_unknown", "Cua 结果未知；不会重建重试。", 409
                        )
                    parts = urlsplit(url or "about:blank")
                    origin = (
                        "about:blank"
                        if not url or url == "about:blank"
                        else f"{parts.scheme}://{parts.netloc}"
                    )
                    if origin not in allowed:
                        raise PortalDataError(
                            "cua_scope_unapproved", "页面来源未在本次 Cua 上限中批准。", 409
                        )
                    maintain_owner()
                    age = time.monotonic() - started
                    if age < 0:
                        raise PortalDataError(
                            "cua_scope_expired", "Cua 时钟发生回退；请核验运行。", 409
                        )
                    if trusted_session:
                        if force or age >= 23 * 3600:
                            raise PortalDataError(
                                "cua_scope_expired", "原生授权不能自动续期。", 409
                            )
                        return
                    if force or age >= min(23 * 3600, idle * 2 / 3):
                        client.call("end_session", {}, pump=lambda: anchor.wait_for_timeout(0))
                        client.session = "tomorrowstar-" + uuid4().hex
                        record["session_refreshes"] += 1
                        record["session"] = client.session
                        started = time.monotonic()
                        helper.atomic_write_json(root / "cua-runtime.json", record)

                record.update(session=client.session, admission="reviewed_driver_owned")
                helper.atomic_write_json(root / "cua-runtime.json", record)
                cua = CuaDriver(
                    client,
                    pid,
                    click_route=record["click_route"],
                    window_id=window_id,
                    launch_date=identity["launch_date"],
                    driver_owned=True,
                    ensure_scope=ensure_scope,
                    keep_owner=maintain_owner,
                )
                yield context, cua
            cleaned = not profile.exists() and not Path(socket).exists()
            if not cleaned:
                raise PortalDataError("cua_cleanup_unknown", "Cua 自有资源未确认清理。", 409)
        finally:
            record.update(closed=cleaned, transport_failed=bool(client and client.failed))
            helper.atomic_write_json(root / "cua-runtime.json", record)


@contextmanager
def managed_cua_browser(
    playwright,
    root: Path,
    *,
    click_route: str = "trusted",
    origins=(),
    synthetic_keychain: bool = False,
    native_handoff: bool = False,
):
    """Own a hidden worker profile and a bounded exact-window Cua attachment."""
    if type(native_handoff) is not bool:
        raise ValueError("Choose an explicit native handover mode")
    candidate = os.environ.get("TS_CUA_DRIVER_BINARY")
    resources = Path(__file__).resolve().parents[3]
    if (
        not candidate
        and resources.name == "Resources"
        and resources.parent.name == "Contents"
        and resources.parent.parent.suffix == ".app"
    ):
        candidate = str(resources / "cua-driver/cua-driver")
    driver = Path(candidate or "/Applications/CuaDriver.app/Contents/MacOS/cua-driver")
    if sys.platform != "darwin" or not driver.is_file():
        raise PortalDataError("cua_unavailable", "本机 CuaDriver.app 未安装。", 409)
    if click_route not in {"trusted", "dom_event"}:
        raise ValueError("Choose an explicit supported Cua click route.")
    binary_sha256 = hashlib.sha256(driver.read_bytes()).hexdigest()
    expected_digest = _NATIVE_HANDOFF_DRIVER_SHA256 if native_handoff else _OWNED_DRIVER_SHA256
    if native_handoff and (not candidate or not expected_digest):
        raise PortalDataError(
            "cua_native_candidate_unverified", "原生接管驱动尚未通过本轮核验。", 409
        )
    if candidate and (driver.is_symlink() or binary_sha256 != expected_digest):
        helper.atomic_write_json(
            root / "cua-runtime.json",
            {
                "binary_sha256": binary_sha256,
                "admission": "candidate_unverified",
                "closed": True,
            },
        )
        raise PortalDataError("cua_candidate_unverified", "Cua 候选不是已复验的修复构建。", 409)
    env = {
        k: v
        for k, v in os.environ.items()
        if not any(word in k.upper() for word in ("TOKEN", "SECRET", "PASSWORD", "KEY"))
    }
    # The diagnostic opt-in must never be inherited by an ordinary worker.
    env.pop("CUA_E2E_USE_MOCK_KEYCHAIN", None)
    if synthetic_keychain is True:
        env["CUA_E2E_USE_MOCK_KEYCHAIN"] = "1"
    env["CUA_DRIVER_RS_TELEMETRY_ENABLED"] = "0"
    manifest = json.loads(subprocess.check_output([str(driver), "manifest"], env=env, timeout=10))
    record = {
        "version": manifest["binary_version"],
        "binary_sha256": binary_sha256,
        "permission_mode": "bounded",
        "existing_profile_grant": False,
        "click_route": click_route,
        "service_workers": "block",
        "closed": False,
        "profile_owner": "worker",
    }
    if candidate:
        with managed_owned_cua_browser(
            playwright,
            root,
            driver,
            env,
            record,
            origins,
            **({"trusted_session": True} if native_handoff else {}),
        ) as owned:
            yield owned
        return
    # Audited 0.35.2 / 0.35.4 check foreground risk before endpoint discovery. A worker-owned
    # Chrome is still an existing profile to Cua; an open CDP port is no grant.
    # Keep the driver's refusal and stop before creating any browser resources.
    if record["version"] in {"0.35.2", "0.35.4"}:
        record.update(admission="background_unavailable", closed=True)
        helper.atomic_write_json(root / "cua-runtime.json", record)
        raise PortalDataError(
            "cua_background_unavailable",
            f"CuaDriver {record['version']} 不支持当前后台附着条件；已在浏览器启动前停止。",
            409,
        )
    with tempfile.TemporaryDirectory(prefix="ts-cua-", dir="/private/tmp") as temporary:
        socket = str(Path(temporary) / "driver.sock")
        record["socket"] = socket
        log_fd = os.open(
            root / "cua.log", os.O_CREAT | os.O_APPEND | os.O_WRONLY | os.O_NOFOLLOW, 0o600
        )
        cleaned = False
        try:
            with (
                os.fdopen(log_fd, "w") as log,
                managed_hidden_chrome(playwright, temporary, driver, log, env) as (
                    context,
                    identity,
                ),
                ExitStack() as sessions,
            ):
                pid, window_id = identity["pid"], identity["window_id"]
                allowed_origins = sorted(
                    {
                        "about:blank",
                        *(
                            f"{u.scheme}://{u.netloc}"
                            for value in origins
                            if (u := urlsplit(value)).scheme in {"http", "https"} and u.netloc
                        ),
                    }
                )
                scope = {
                    "version": 3,
                    "allow": {
                        "tools": [
                            "check_permissions",
                            "list_windows",
                            "browser_prepare",
                            "get_browser_state",
                            "browser_click",
                            "end_session",
                        ]
                    },
                    "resources": {
                        "browser": {
                            "existing_profiles": [{"pid": pid, "window_id": window_id}],
                            "origins": allowed_origins,
                        }
                    },
                }
                record.update(
                    identity,
                    capability_manifest=scope,
                    window_policy="hidden_until_review",
                    session_refreshes=0,
                )
                started = None

                def ensure_scope(url):
                    nonlocal started
                    if getattr(cua.client, "failed", False):
                        raise PortalDataError(
                            "cua_result_unknown", "Cua 结果未知；不会重建重试。", 409
                        )
                    origin = "about:blank"
                    if url and url != origin:
                        parts = urlsplit(url)
                        if parts.scheme not in {"http", "https"} or not parts.netloc:
                            raise PortalDataError("cua_refused", "Cua 不支持该页面来源。", 409)
                        origin = f"{parts.scheme}://{parts.netloc}"
                    if (
                        started is not None
                        and origin in allowed_origins
                        and time.monotonic() - started < 23 * 3600
                    ):
                        return
                    if origin not in allowed_origins:
                        allowed_origins.append(origin)
                        allowed_origins.sort()
                    sessions.close()
                    client, permissions = sessions.enter_context(
                        managed_cua_client(driver, socket, scope, log, env)
                    )
                    prepared = client.call(
                        "browser_prepare",
                        {
                            "pid": pid,
                            "window_id": window_id,
                            "strategy": {"kind": "existing_profile"},
                        },
                    )
                    if (
                        prepared.get("prepared_pid") != pid
                        or prepared.get("action") != "attached_existing_profile"
                        or any(prepared.get("side_effects", {}).values())
                    ):
                        raise PortalDataError(
                            "cua_binding_ambiguous", "Cua 未无副作用地绑定受管浏览器。", 409
                        )
                    cua.client = client
                    record.update(session=client.session, daemon_pid=permissions["source"]["pid"])
                    record["session_refreshes"] += int(started is not None)
                    started = time.monotonic()
                    helper.atomic_write_json(root / "cua-runtime.json", record)

                cua = CuaDriver(
                    None,
                    pid,
                    click_route=click_route,
                    window_id=window_id,
                    launch_date=identity["launch_date"],
                    ensure_scope=ensure_scope,
                )
                ensure_scope(None)
                yield context, cua
            cleaned = True
        finally:
            record["closed"] = cleaned and not Path(socket).exists()
            helper.atomic_write_json(root / "cua-runtime.json", record)


# Consecutive failed owner reads before a live driver's owner counts as lost.
OWNER_READ_RETRIES = 3


class CuaDriver:
    """Select one confirmed option. No arbitrary clicks, scripts or submit surface."""

    def __init__(
        self,
        client,
        pid: int,
        *,
        click_route: str = "trusted",
        window_id=None,
        launch_date=None,
        ensure_scope=None,
        driver_owned=False,
        keep_owner=None,
    ):
        if click_route not in {"trusted", "dom_event"}:
            raise ValueError("Choose an explicit supported Cua click route.")
        self.client, self.pid, self.click_route = client, pid, click_route
        self.window_id, self.launch_date = window_id, launch_date
        self.ensure_scope = ensure_scope
        self.driver_owned, self.keep_owner = driver_owned, keep_owner
        self._maintaining = False
        # Why the owner is gone for good (driver exited or client failed), or None.
        self.owner_lost = None
        self._owner_failures = 0

    def _owner_terminal(self):
        """The terminal cause, or None: an exited driver or failed client never recovers."""
        process = getattr(self.client, "process", None)
        if getattr(self.client, "failed", False):
            return "cua_client_failed"
        if process is not None and process.poll() is not None:
            return "cua_driver_exited"
        return None

    def _lose_owner(self, cause):
        # Logged once; maintenance stops and the page's reopen path takes over.
        self.owner_lost = cause
        print(f"cua_owner_lost: {cause}", flush=True)

    def maintain(self, *, pump):
        """Keep the owner alive; a terminal loss stops here, a transient one retries.

        A failed read is retried on later ticks up to ``OWNER_READ_RETRIES`` times in a
        row before it too counts as terminal (2026-11-02: 574 identical owner errors,
        two log lines per tick, after the driver had already exited).
        """
        if self._maintaining or self.owner_lost is not None:
            return
        self._maintaining = True
        try:
            cause = self._owner_terminal()
            if cause is not None:
                self._lose_owner(cause)
                return
            if getattr(self.client, "handoff_transition_inflight", False) or getattr(
                self.client, "control_inflight", False
            ):
                pump()
            elif self.keep_owner is not None:
                try:
                    self.keep_owner(pump=pump)
                except PortalDataError as error:
                    self._owner_failures += 1
                    cause = self._owner_terminal()
                    if cause is None and self._owner_failures >= OWNER_READ_RETRIES:
                        cause = error.code
                    if cause is not None:
                        self._lose_owner(cause)
                        return
                    raise
                self._owner_failures = 0
        finally:
            self._maintaining = False

    def _owner_state(self, *, pump) -> dict:
        """Read the existing owner; the worker binds its retained CDP Page separately."""
        process = getattr(self.client, "process", None)
        if (
            type(self.pid) is not int
            or self.pid <= 0
            or type(self.window_id) is not int
            or self.window_id <= 0
            or getattr(self.client, "failed", True) is not False
            or process is None
            or process.poll() is not None
        ):
            raise PortalDataError("cua_owner_unknown", "Cua 原所属窗口不能核验。", 409)
        bound = self.client.call(
            "get_browser_state",
            {"pid": self.pid, "window_id": self.window_id},
            pump=pump,
            owner=True,
        )
        if (
            self.client.failed
            or process.poll() is not None
            or not isinstance(bound, dict)
            or bound.get("status") != "ok"
            or bound.get("refusal")
            or bound.get("binding_quality") != "exact"
            or bound.get("endpoint_access_class")
            != ("driver_owned" if self.driver_owned else "existing_profile_approved")
            or not isinstance(bound.get("target_id"), str)
            or not bound["target_id"].strip()
        ):
            raise PortalDataError("cua_owner_unknown", "Cua 原所属窗口不能核验。", 409)
        return bound

    def observe_owner(self, *, pump) -> dict:
        """Read the existing owner without selecting a browser tab."""
        self._owner_state(pump=pump)
        return {
            "status": "accepted",
            "pid": self.pid,
            "window_id": self.window_id,
            "observed_at": time.time(),
            "driver_version": getattr(self.client, "driver_version", None),
        }

    def native_page_scope(self, page, *, pump):
        """Attest the retained CDP Page against one existing native target and tab."""
        session = None
        try:
            before = process_identity(self.pid)
            if not valid_process_identity(before) or page.is_closed():
                raise ValueError("Original browser identity unavailable")
            session = OwnedCDP(page).__enter__()
            target = session.send("Target.getTargetInfo").get("targetInfo", {}).get("targetId")
            if not isinstance(target, str) or not target:
                raise ValueError("Retained Page has no exact CDP target")
            bound = self._owner_state(pump=pump)
            fingerprint = bound.get("process_fingerprint")
            generation = bound.get("binding_generation")
            tabs = bound.get("tabs")
            if (
                type(generation) is not int
                or generation < 0
                or not isinstance(fingerprint, dict)
                or set(fingerprint) != {"pid", "start_time", "executable"}
                or type(fingerprint["pid"]) is not int
                or fingerprint["pid"] != self.pid
                or type(fingerprint["start_time"]) is not int
                or fingerprint["start_time"] < 0
                or not isinstance(fingerprint["executable"], str)
                or str(Path(fingerprint["executable"]).resolve()) != before["executable"]
                or not isinstance(tabs, list)
                or len(tabs) > 500
            ):
                raise ValueError("Native original-page attestation unavailable")
            matches = [
                tab for tab in tabs if isinstance(tab, dict) and tab.get("cdp_target_id") == target
            ]
            if len(matches) != 1:
                raise ValueError("Retained CDP Page is not one unique native tab")
            tab = matches[0]
            if (
                not isinstance(tab.get("tab_id"), str)
                or not tab["tab_id"]
                or type(tab.get("tab_generation")) is not int
                or tab["tab_generation"] < 0
                or process_identity(self.pid) != before
                or page.is_closed()
                or session.send("Target.getTargetInfo").get("targetInfo", {}).get("targetId")
                != target
            ):
                raise ValueError("Native Page or browser generation changed")
            return {
                "target_id": bound["target_id"],
                "tab_id": tab["tab_id"],
                "cdp_target_id": target,
                "binding_generation": generation,
                "tab_generation": tab["tab_generation"],
                "process_fingerprint": fingerprint,
                "process_identity": before,
            }
        except Exception as error:
            raise PortalDataError(
                "cua_page_unverified", "原页与原生浏览器标签不能精确对应。", 409
            ) from error
        finally:
            if session is not None:
                try:
                    session.detach()
                except Exception as error:
                    raise PortalDataError(
                        "cua_page_unverified", "原页观察连接已失效。", 409
                    ) from error

    def review(self, page, *, pump):
        self._bind(page.url, pump)
        self.window_state(page, state="normal")
        if self.launch_date is not None:
            mac_chrome_state(self.pid, launch_date=self.launch_date, action="show")

    def _check_background(self):
        state = mac_chrome_state(self.pid, launch_date=self.launch_date, windows=True)
        if (
            not state["hidden"]
            or state["active"]
            or any(w["is_on_screen"] for w in state["windows"])
        ):
            raise PortalDataError("cua_visibility_unknown", "Cua 后台状态不能核验。", 409)

    def new_page(self, context, *, keep_visible=False):
        """Open a background tab. Preserve an existing human review window."""
        if not keep_visible and self.launch_date is not None:
            if self.driver_owned:
                self._check_background()
            else:
                mac_chrome_state(self.pid, launch_date=self.launch_date, action="hide")
        session = context.browser.new_browser_cdp_session()
        try:
            identifiers = session.send("Target.getBrowserContexts")["browserContextIds"]
            if len(identifiers) != 1:
                raise PortalDataError("cua_binding_ambiguous", "工作 context 不能唯一绑定。", 409)
            new_window = not context.pages
            with context.expect_page(timeout=5000) as created:
                # Creation-time minimization can animate despite AppKit hidden=true.
                session.send(
                    "Target.createTarget",
                    {
                        "url": "about:blank",
                        "browserContextId": identifiers[0],
                        "background": True,
                        "focus": False,
                        "newWindow": new_window,
                    },
                )
            page = created.value
            if not keep_visible:
                if self.driver_owned:
                    # A new Chrome tab restores a minimized window and animates
                    # even while the app is hidden. Keep this owned window hidden
                    # without a minimize/restore cycle; retain the visibility guard.
                    self._check_background()
                else:
                    self.window_state(page, state="minimized")
            return page
        finally:
            session.detach()

    @staticmethod
    def window_state(page, *, state=None) -> dict:
        session = page.context.new_cdp_session(page)
        try:
            window = session.send("Browser.getWindowForTarget")
            if state is not None:
                session.send(
                    "Browser.setWindowBounds",
                    {
                        "windowId": window["windowId"],
                        "bounds": {"windowState": state},
                    },
                )
            expected = state
            until = time.monotonic() + 1.5
            while True:
                bounds = session.send("Browser.getWindowBounds", {"windowId": window["windowId"]})[
                    "bounds"
                ]
                if expected is None or bounds["windowState"] == expected:
                    return bounds
                if time.monotonic() >= until:
                    raise PortalDataError("cua_visibility_unknown", "浏览器显示状态不能核验。", 409)
                page.wait_for_timeout(25)
        finally:
            session.detach()

    def _bind(self, url: str, pump) -> dict:
        if self.ensure_scope is not None:
            self.ensure_scope(url)
        matches = []
        windows = (
            [{"pid": self.pid, "window_id": self.window_id}]
            if self.driver_owned
            else self.client.call("list_windows", {"pid": self.pid}, pump=pump)["windows"]
        )
        if len(windows) > 50:
            raise PortalDataError("cua_binding_ambiguous", "浏览器窗口不能唯一绑定。", 409)
        for window in windows:
            if (
                window["pid"] != self.pid
                or self.window_id is not None
                and window["window_id"] != self.window_id
            ):
                continue
            try:
                bound = self.client.call(
                    "get_browser_state",
                    {"pid": self.pid, "window_id": window["window_id"]},
                    pump=pump,
                )
            except PortalDataError as error:
                if error.code == "cua_refused":
                    continue
                raise
            if (
                bound.get("binding_quality") != "exact"
                or bound.get("endpoint_access_class")
                != (
                    "existing_profile_approved"
                    if self.window_id is not None and not self.driver_owned
                    else "driver_owned"
                )
                or bound.get("mutation_allowed") is not True
            ):
                continue
            for tab in bound.get("tabs", []):
                if tab["url"] == url:
                    matches.append({"target_id": bound["target_id"], "tab_id": tab["tab_id"]})
        if len(matches) != 1:
            raise PortalDataError("cua_binding_ambiguous", "当前页面不能唯一绑定。", 409)
        return matches[0]

    def fill(self, page, question: dict, value: str, *, check, pump) -> dict:
        url = page.url
        binding = self._bind(url, pump)
        for role, label in [("combobox", question["question"]), ("option", value)]:
            state = self.client.call(
                "get_browser_state",
                {**binding, "snapshot_format": "semantic_v2"},
                pump=pump,
            )
            if (
                state.get("page", {}).get("url") != url
                or page.url != url
                or state.get("target_id") != binding["target_id"]
                or state.get("tab_id") != binding["tab_id"]
                or state.get("snapshot", {}).get("complete") is not True
            ):
                raise PortalDataError("cua_snapshot_changed", "当前页面状态不能核验。", 409)
            refs = [
                ref
                for ref in state.get("refs", [])
                if ref.get("role") == role
                and _name(ref.get("name") or "") == _name(label)
                and ref.get("frame") == "main"
                and "click" in ref.get("actions", [])
            ]
            if len(refs) != 1:
                raise PortalDataError("cua_control_ambiguous", "当前控件或选项不唯一。", 409)
            check()
            self.client.call(
                "browser_click",
                {**binding, "ref": refs[0]["ref"], "input_route": self.click_route},
                pump=pump,
            )
        # The runner independently verifies the resulting field and remote contract.
        # Native completion can precede the worker's queued request-guard events.
        pump()
        return {"executor": "cua_driver", "input_route": self.click_route}
