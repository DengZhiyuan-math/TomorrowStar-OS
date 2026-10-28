"""Only the current native parent pipe can supply host samples or request probes."""

import importlib.util
import json
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import pytest


@pytest.fixture
def host(tmp_path, monkeypatch):
    monkeypatch.setattr(sys, "path", sys.path.copy())
    source = Path(__file__).parents[1] / "macos/server.py"
    spec = importlib.util.spec_from_file_location("current_native_server", source)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    identity = {
        "native_pid": 9001,
        "python_pid": 9002,
        "python_responsible_pid": 9001,
        "bundle_id": "dev.synthetic.current-host",
        "executable": "/fixed/Synthetic.app/Contents/MacOS/Synthetic",
    }
    calls = []

    def verify(resources, native):
        assert native["pid"] == 9001
        assert native["executable"] == identity["executable"]
        return identity

    def probe(resources, directory, native, **kwargs):
        calls.append(native)
        return {
            **identity,
            "daemon_pid": 9003,
            "daemon_responsible_pid": 9001,
            "proxy_pid": 9004,
            "proxy_responsible_pid": 9001,
            "native_and_embedded_permissions_match": True,
            "daemon_closed": True,
            "permission_checked_at": time.time(),
            "accessibility": native["accessibility"],
            "screen_recording": native["screen_recording"],
        }

    tools = SimpleNamespace(
        host_identity=lambda resources, pid: identity,
        verify_native_identity=verify,
        probe_host_permissions=probe,
    )
    monkeypatch.setattr(module, "native_permission_tools", lambda resources: tools, raising=False)
    bridge = module.NativeHostBridge(
        tmp_path, tmp_path / "diagnostics", "a" * 32, native_pid=9001, backend_pid=9002
    )
    return module, bridge, calls, tools


def receipt(bridge, *, kind="sample", sequence=1, **changes):
    frame = {
        "protocol": "current-native-host/v1",
        "scope": "current_instance",
        "kind": kind,
        **bridge.binding,
        "sequence": sequence,
        "captured_at": time.time(),
        "native_responsible_pid": 9001,
        "accessibility": True,
        "screen_recording": True,
        "active": True,
        "windows": 1,
        **changes,
    }
    return json.dumps(frame).encode() + b"\n"


def test_startup_sample_verifies_current_python_parent_but_never_starts_a_daemon(host, tmp_path):
    _, bridge, calls, _ = host
    assert bridge.snapshot()["state"] == "unknown"

    bridge.receive(receipt(bridge))
    first = bridge.snapshot()
    assert first["state"] == "unknown"
    assert first["reason"] == "permission_check_required"
    assert first["responsibility_chain"] == "python_verified"
    assert first["native_pid"] == 9001 and first["backend_pid"] == 9002
    assert first["session_open"] is True
    assert first["instance_binding"] == bridge.binding
    assert all(first[key] == value for key, value in first["instance_binding"].items())
    assert first["accessibility"] is True and first["screen_recording"] is True
    assert first["daemon"] is None
    for _ in range(2):
        assert bridge.snapshot() == first
    assert calls == [] and not (tmp_path / "diagnostics").exists()


def test_only_explicit_current_native_check_can_publish_verified_daemon_chain(host):
    _, bridge, calls, _ = host

    bridge.receive(receipt(bridge, kind="check"))
    until = time.monotonic() + 1
    while time.monotonic() < until and bridge.snapshot()["state"] == "unknown":
        time.sleep(0.01)

    result = bridge.snapshot()
    assert result["state"] == "verified"
    assert result["kind"] == "check" and result["responsibility_chain"] == "verified"
    assert result["daemon"]["pid"] == 9003
    assert result["daemon"]["responsible_pid"] == 9001
    assert result["daemon"]["proxy_pid"] == 9004
    assert result["daemon"]["proxy_responsible_pid"] == 9001
    assert result["daemon"]["prompt"] is False and result["daemon"]["closed"] is True
    assert len(calls) == 1


def test_actual_python_responsibility_mismatch_blocks_before_probe(host):
    _, bridge, calls, tools = host

    def mismatch(resources, native):
        raise AssertionError("Synthetic current Python responsibility mismatch")

    tools.verify_native_identity = mismatch
    bridge.receive(receipt(bridge, kind="check"))

    assert bridge.snapshot()["state"] == "blocked"
    assert calls == []


def wait_for_check(bridge):
    until = time.monotonic() + 2
    while time.monotonic() < until and bridge._checking:
        time.sleep(0.005)
    assert not bridge._checking
    return bridge.snapshot()


@pytest.mark.parametrize(
    "field", ["launch_nonce", "native_pid", "backend_pid", "bundle_id", "executable"]
)
def test_other_instance_binding_blocks_without_probing(host, field):
    _, bridge, calls, _ = host
    value = 9999 if field.endswith("pid") else "other"
    bridge.receive(receipt(bridge, kind="check", **{field: value}))
    assert bridge.snapshot()["state"] == "blocked"
    assert bridge.snapshot()["reason"] == "native_instance_mismatch"
    assert calls == []


@pytest.mark.parametrize(
    "changes",
    [
        {"scope": "background_instance"},
        {"kind": "arbitrary"},
        {"captured_at": time.time() - 60},
        {"captured_at": time.time() + 60},
        {"captured_at": float("nan")},
        {"sequence": True},
        {"accessibility": 1},
        {"body": "PRIVATE SYNTHETIC TEXT"},
    ],
)
def test_unusable_frames_cannot_promote_or_probe(host, changes):
    _, bridge, calls, _ = host
    bridge.receive(receipt(bridge, **{"kind": "check", **changes}))
    assert bridge.snapshot()["state"] == "unknown"
    assert calls == []
    assert "PRIVATE SYNTHETIC" not in json.dumps(bridge.snapshot())


def test_replay_and_oversized_frame_invalidate_previous_positive(host):
    _, bridge, calls, _ = host
    frame = receipt(bridge, kind="check")
    bridge.receive(frame)
    assert wait_for_check(bridge)["state"] == "verified"
    bridge.receive(frame)
    assert bridge.snapshot()["state"] == "unknown"
    bridge.receive(b"x" * 4097)
    assert bridge.snapshot()["state"] == "unknown"
    assert len(calls) == 1


@pytest.mark.parametrize(
    "field,value",
    [
        ("daemon_responsible_pid", 9999),
        ("proxy_responsible_pid", 9999),
        ("daemon_closed", False),
        ("accessibility", 1),
    ],
)
def test_daemon_mismatch_or_unclosed_probe_never_verifies(host, field, value):
    _, bridge, _, tools = host
    original = tools.probe_host_permissions

    def mismatched(*args, **kwargs):
        return {**original(*args, **kwargs), field: value}

    tools.probe_host_permissions = mismatched
    bridge.receive(receipt(bridge, kind="check"))
    assert wait_for_check(bridge)["state"] == "blocked"


def test_false_native_permission_is_blocked_after_explicit_read_only_check(host):
    _, bridge, calls, _ = host
    bridge.receive(receipt(bridge, kind="check", accessibility=False))
    assert wait_for_check(bridge)["state"] == "blocked"
    assert bridge.snapshot()["reason"] == "permissions_required"
    assert len(calls) == 1


@pytest.mark.parametrize("interrupt", ["close", "invalid", "mismatch"])
def test_late_probe_cannot_overwrite_invalidated_receipt_or_backend_close(host, interrupt):
    import threading

    _, bridge, calls, tools = host
    entered, release = threading.Event(), threading.Event()
    own = SimpleNamespace(killed=False)
    own.poll = lambda: 0 if own.killed else None

    def kill():
        own.killed = True

    own.kill = kill
    original = tools.probe_host_permissions

    def delayed(*args, **kwargs):
        kwargs["register_process"](own)
        entered.set()
        assert release.wait(2)
        return original(*args, **kwargs)

    tools.probe_host_permissions = delayed
    try:
        bridge.receive(receipt(bridge, kind="check"))
        assert entered.wait(1)
        # A second valid menu click must neither queue nor replace the in-flight check.
        bridge.receive(receipt(bridge, kind="check", sequence=2))
        if interrupt == "close":
            bridge.close()
            assert own.killed and bridge._cancelled.is_set()
        elif interrupt == "invalid":
            bridge.receive(b"not-json")
        else:
            bridge.receive(receipt(bridge, sequence=3, launch_nonce="b" * 32))
        expected = bridge.snapshot()
    finally:
        release.set()
    result = wait_for_check(bridge)
    assert result == expected
    assert result["state"] != "verified"
    assert len(calls) == 1


def test_snapshot_is_an_immutable_memory_copy_and_stale_result_is_unknown(host, monkeypatch):
    module, bridge, calls, _ = host
    bridge.receive(receipt(bridge))
    original = bridge.snapshot()
    copied = bridge.snapshot()
    copied["state"] = "verified"
    assert bridge.snapshot() == original
    monkeypatch.setattr(module.time, "time", lambda: original["captured_at"] + 31)
    assert bridge.snapshot()["state"] == "unknown"
    assert bridge.snapshot()["reason"] == "permission_check_required"
    assert bridge.snapshot()["session_open"] is True
    assert bridge.snapshot()["instance_binding"] == bridge.binding
    assert calls == []


@pytest.fixture(scope="module")
def native_receipt_encoder(tmp_path_factory):
    import shutil
    import subprocess

    compiler = shutil.which("swiftc")
    if sys.platform != "darwin" or compiler is None:
        pytest.skip("Native frame encoding requires macOS Swift")
    source = (Path(__file__).parents[1] / "macos/App.swift").read_text()
    code = source[
        source.index("struct NativeHostReceipt {") : source.index("struct BackgroundCheckLaunch {")
    ]
    directory = tmp_path_factory.mktemp("native-current-host-encoder")
    harness = directory / "encoder.swift"
    harness.write_text(
        "import Foundation\n"
        + code
        + """
let mode = CommandLine.arguments[1]
var snapshot: [String: Any] = ["pid": 9001, "responsible_pid": 9001,
    "bundle_id": "dev.synthetic.current-host",
    "executable": "/fixed/Synthetic.app/Contents/MacOS/Synthetic",
    "accessibility": true, "screen_recording": true, "active": true, "windows": 1,
    "private_body": "PRIVATE SYNTHETIC BODY"]
if mode == "oversized" { snapshot["executable"] = String(repeating: "x", count: 4097) }
do {
    let frame = try NativeHostReceipt.frame(snapshot: snapshot,
        nonce: mode == "nonce" ? "invalid" : String(repeating: "a", count: 32),
        backendPID: mode == "pid" ? 0 : 9002, sequence: 1,
        kind: ["check", "sample"].contains(mode) ? mode : (mode == "kind" ? "arbitrary" : "sample"))
    FileHandle.standardOutput.write(frame)
} catch { exit(2) }
"""
    )
    executable = directory / "encoder"
    subprocess.run(
        [
            compiler,
            "-module-cache-path",
            str(directory / "cache"),
            str(harness),
            "-o",
            str(executable),
        ],
        check=True,
        capture_output=True,
        timeout=60,
    )
    return executable


@pytest.mark.parametrize("mode", ["sample", "check", "nonce", "pid", "kind", "oversized"])
def test_real_native_encoder_uses_only_fixed_current_instance_frames(native_receipt_encoder, mode):
    import subprocess

    result = subprocess.run([str(native_receipt_encoder), mode], capture_output=True, timeout=5)
    if mode not in {"sample", "check"}:
        assert result.returncode == 2 and result.stdout == b""
        return
    assert result.returncode == 0 and result.stdout.endswith(b"\n")
    assert b"PRIVATE SYNTHETIC" not in result.stdout and len(result.stdout) <= 4096
    row = json.loads(result.stdout)
    assert set(row) == {
        "protocol",
        "scope",
        "kind",
        "launch_nonce",
        "native_pid",
        "backend_pid",
        "bundle_id",
        "executable",
        "captured_at",
        "sequence",
        "native_responsible_pid",
        "accessibility",
        "screen_recording",
        "active",
        "windows",
    }
    assert row["kind"] == mode and row["scope"] == "current_instance"
    assert row["native_pid"] == row["native_responsible_pid"] == 9001
    assert row["backend_pid"] == 9002 and row["sequence"] == 1
    assert row["accessibility"] is True and row["screen_recording"] is True


def test_real_parent_pipe_bounds_frames_resumes_after_oversize_and_closes_on_eof(tmp_path):
    import select
    import subprocess

    source = Path(__file__).parents[1] / "macos/server.py"
    script = tmp_path / "parent-pipe.py"
    script.write_text(
        "import importlib.util, json, threading\n"
        f"spec=importlib.util.spec_from_file_location('pipe_server', {str(source)!r})\n"
        "module=importlib.util.module_from_spec(spec); spec.loader.exec_module(module)\n"
        "class Bridge:\n"
        " closed=False\n"
        " def receive(self,raw): print(json.dumps({'frame_bytes':len(raw)}),flush=True)\n"
        " def close(self):\n"
        "  if not self.closed: self.closed=True; print(json.dumps({'closed':True}),flush=True)\n"
        "class Server:\n"
        " def __init__(self): self.stopped=threading.Event()\n"
        " def __enter__(self): return self\n"
        " def __exit__(self,*args): pass\n"
        " def shutdown(self): self.stopped.set()\n"
        " def serve_forever(self,poll_interval): self.stopped.wait(10)\n"
        f"module.serve_with_parent_pipe(Server(), {str(tmp_path / 'diagnostics')!r}, "
        "{'ready':True}, native_bridge=Bridge())\n"
    )
    process = subprocess.Popen(
        [sys.executable, "-I", "-B", "-u", str(script)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    try:
        assert select.select([process.stdout], [], [], 5)[0]
        assert json.loads(process.stdout.readline()) == {"ready": True}
        process.stdin.write(b"x" * 5000 + b"\n{}\n" + b"y" * 4096 + b"\n")
        process.stdin.flush()
        started = time.monotonic()
        process.stdin.close()
        assert process.wait(timeout=2) == 0 and time.monotonic() - started < 2
        rows = [json.loads(line) for line in process.stdout.read().splitlines()]
        assert rows == [
            {"frame_bytes": 0},
            {"frame_bytes": 2},
            {"frame_bytes": 4096},
            {"closed": True},
        ]
        for path in (tmp_path / "diagnostics").iterdir():
            assert "xxxxx" not in path.read_text() and "yyyyy" not in path.read_text()
    finally:
        if process.poll() is None:
            process.kill()
            process.wait()


def test_missing_permission_sample_during_probe_blocks_without_queuing_or_late_green(host):
    import threading

    _, bridge, calls, tools = host
    entered, release = threading.Event(), threading.Event()
    original = tools.probe_host_permissions

    def delayed(*args, **kwargs):
        entered.set()
        assert release.wait(2)
        return original(*args, **kwargs)

    tools.probe_host_permissions = delayed
    try:
        bridge.receive(receipt(bridge, kind="check"))
        assert entered.wait(1)
        bridge.receive(receipt(bridge, kind="check", sequence=2, accessibility=False))
        assert bridge.snapshot()["state"] == "blocked"
        assert bridge.snapshot()["accessibility"] is False
    finally:
        release.set()
        wait_for_check(bridge)
    assert bridge.snapshot()["state"] == "blocked" and len(calls) == 1


def test_session_facts_are_memory_only_immutable_and_closed_after_late_probe(host, tmp_path):
    import threading

    _, bridge, calls, tools = host
    entered, release = threading.Event(), threading.Event()
    original_probe = tools.probe_host_permissions

    def delayed(*args, **kwargs):
        entered.set()
        assert release.wait(2)
        return original_probe(*args, **kwargs)

    tools.probe_host_permissions = delayed
    initial = bridge.snapshot()
    assert initial["session_open"] is True
    assert initial["instance_binding"] == bridge.binding
    initial["instance_binding"]["launch_nonce"] = "external mutation"
    initial["invalidation_epoch"] = 999
    assert bridge.snapshot()["invalidation_epoch"] == 0
    assert bridge.snapshot()["instance_binding"] == bridge.binding
    assert calls == [] and not (tmp_path / "diagnostics").exists()
    try:
        bridge.receive(receipt(bridge, kind="check"))
        assert entered.wait(1)
        bridge.close()
        closed = bridge.snapshot()
        assert closed["session_open"] is False and closed["reason"] == "backend_closed"
        assert closed["instance_binding"] == bridge.binding
    finally:
        release.set()
    assert wait_for_check(bridge) == closed
    assert len(calls) == 1


def test_only_verified_receipt_can_be_downgraded_to_stale(host, monkeypatch):
    module, bridge, _, _ = host
    bridge.receive(receipt(bridge, kind="check"))
    verified = wait_for_check(bridge)
    assert verified["state"] == "verified"
    monkeypatch.setattr(module.time, "time", lambda: verified["captured_at"] + 31)
    stale = bridge.snapshot()
    assert stale["state"] == "unknown" and stale["reason"] == "native_receipt_stale"
    assert stale["session_open"] is True and stale["instance_binding"] == bridge.binding
    assert stale["invalidation_epoch"] == verified["invalidation_epoch"]
    assert bridge.snapshot() == stale
    assert stale["accessibility"] is True and stale["screen_recording"] is True
    # Reading a stale projection must not rewrite its underlying verified receipt.
    assert bridge._value["state"] == "verified"
    bridge.close()
    closed = bridge.snapshot()
    assert closed["state"] == "unknown" and closed["reason"] == "backend_closed"
    assert closed["session_open"] is False


def test_expired_blocked_receipt_keeps_its_explicit_reason(host, monkeypatch):
    module, bridge, calls, _ = host
    bridge.receive(receipt(bridge, accessibility=False))
    blocked = bridge.snapshot()
    assert blocked["state"] == "blocked" and blocked["reason"] == "permissions_required"
    monkeypatch.setattr(module.time, "time", lambda: blocked["captured_at"] + 31)
    assert bridge.snapshot() == blocked
    assert calls == []


@pytest.mark.parametrize("blocked_first", [False, True])
def test_expired_incoming_frame_cannot_masquerade_as_naturally_aged_positive(host, blocked_first):
    _, bridge, _, _ = host
    bridge.receive(receipt(bridge, kind="check"))
    assert wait_for_check(bridge)["state"] == "verified"
    if blocked_first:
        bridge.receive(receipt(bridge, sequence=2, launch_nonce="b" * 32))
        blocked = bridge.snapshot()
        assert blocked["reason"] == "native_instance_mismatch"
    bridge.receive(receipt(bridge, sequence=3, captured_at=time.time() - 31))
    result = bridge.snapshot()
    if blocked_first:
        assert result == blocked | {"invalidation_epoch": result["invalidation_epoch"]}
        assert result["invalidation_epoch"] > blocked["invalidation_epoch"]
    else:
        assert result["state"] == "unknown" and result["reason"] == "native_receipt_invalid"
    assert result["reason"] != "native_receipt_stale"


def test_invalidation_epoch_never_reuses_an_old_positive_after_a_new_check_or_fault(host):
    _, bridge, _, _ = host
    assert bridge.snapshot()["invalidation_epoch"] == 0
    bridge.receive(receipt(bridge, kind="check"))
    first = wait_for_check(bridge)
    original_epoch = first["invalidation_epoch"]
    assert first["state"] == "verified" and original_epoch > 0
    for _ in range(2):
        assert bridge.snapshot()["invalidation_epoch"] == original_epoch
    bridge.receive(receipt(bridge, sequence=2, launch_nonce="b" * 32))
    fault = bridge.snapshot()
    assert fault["state"] == "blocked" and fault["invalidation_epoch"] > original_epoch
    bridge.receive(receipt(bridge, sequence=3, captured_at=time.time() - 31))
    expired_incoming = bridge.snapshot()
    assert expired_incoming["state"] == "blocked"
    assert expired_incoming["reason"] == "native_instance_mismatch"
    assert expired_incoming["invalidation_epoch"] > fault["invalidation_epoch"]
    bridge.receive(receipt(bridge, kind="check", sequence=4))
    restored = wait_for_check(bridge)
    assert restored["state"] == "verified"
    assert restored["invalidation_epoch"] > expired_incoming["invalidation_epoch"] > original_epoch
    bridge.close()
    closed = bridge.snapshot()
    assert closed["invalidation_epoch"] > restored["invalidation_epoch"]
    bridge.close()
    assert bridge.snapshot() == closed


@pytest.mark.parametrize("failure", [TimeoutError, AssertionError, OSError])
def test_probe_failure_changes_epoch_and_later_positive_does_not_restore_it(host, failure):
    _, bridge, _, tools = host
    bridge.receive(receipt(bridge, kind="check"))
    prior = wait_for_check(bridge)
    original = tools.probe_host_permissions

    def fail(*args, **kwargs):
        raise failure("fixed synthetic probe failure")

    tools.probe_host_permissions = fail
    bridge.receive(receipt(bridge, kind="check", sequence=2))
    rejected = wait_for_check(bridge)
    assert rejected["invalidation_epoch"] > prior["invalidation_epoch"]
    assert rejected["state"] != "verified"
    tools.probe_host_permissions = original
    bridge.receive(receipt(bridge, kind="check", sequence=3))
    restored = wait_for_check(bridge)
    assert restored["state"] == "verified"
    assert restored["invalidation_epoch"] > rejected["invalidation_epoch"]


@pytest.mark.parametrize("replacement_kind", ["sample", "check"])
def test_new_current_sample_or_check_replaces_the_old_grant_epoch(host, replacement_kind):
    _, bridge, _, _ = host
    bridge.receive(receipt(bridge, kind="check"))
    positive = wait_for_check(bridge)
    bridge.receive(receipt(bridge, kind=replacement_kind, sequence=2))
    replacement = wait_for_check(bridge)
    assert replacement["invalidation_epoch"] > positive["invalidation_epoch"]
    if replacement_kind == "sample":
        assert (
            replacement["state"] == "unknown"
            and replacement["reason"] == "permission_check_required"
        )
    else:
        assert replacement["state"] == "verified"


@pytest.mark.parametrize("negative", ["invalid", "replay", "false", "binding"])
def test_negative_receipt_changes_epoch_before_any_later_fresh_success(host, negative):
    _, bridge, _, _ = host
    first = receipt(bridge, kind="check")
    bridge.receive(first)
    positive = wait_for_check(bridge)
    bad = {
        "invalid": b"not-json",
        "replay": first,
        "false": receipt(bridge, sequence=2, accessibility=False),
        "binding": receipt(bridge, sequence=2, backend_pid=9999),
    }[negative]
    bridge.receive(bad)
    rejected = bridge.snapshot()
    assert rejected["state"] != "verified"
    assert rejected["invalidation_epoch"] > positive["invalidation_epoch"]
    bridge.receive(receipt(bridge, kind="check", sequence=3))
    restored = wait_for_check(bridge)
    assert restored["state"] == "verified"
    assert restored["invalidation_epoch"] > rejected["invalidation_epoch"]
