"""Permission readiness stops before browser work; all OS responses are synthetic."""

import builtins
import hashlib
import importlib.util
import json
import plistlib
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from career_evidence_graph import cua_driver


@pytest.fixture
def probe(tmp_path, monkeypatch):
    monkeypatch.setattr(sys, "path", sys.path.copy())
    source = Path(__file__).parents[1] / "macos/background_check.py"
    spec = importlib.util.spec_from_file_location("permission_readiness", source)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    resources = tmp_path / "Synthetic.app/Contents/Resources"
    executable = resources.parent / "MacOS/TomorrowStar"
    executable.parent.mkdir(parents=True)
    executable.write_bytes(b"Synthetic native executable; never run")
    (resources.parent / "Info.plist").write_bytes(
        plistlib.dumps(
            {"CFBundleIdentifier": "dev.tomorrowstar.desktop", "CFBundleExecutable": "TomorrowStar"}
        )
    )
    helper = resources / "cua-driver/cua-driver"
    helper.parent.mkdir(parents=True)
    helper.write_bytes(b"Synthetic reviewed driver; never execute")
    monkeypatch.setattr(module, "__file__", str(resources / "background_check.py"))
    monkeypatch.setattr(
        cua_driver, "_OWNED_DRIVER_SHA256", hashlib.sha256(helper.read_bytes()).hexdigest()
    )
    monkeypatch.delenv("TS_CUA_DRIVER_BINARY", raising=False)
    root = tmp_path / "diagnostic"
    root.mkdir(mode=0o700)
    native = {
        "pid": 9001,
        "responsible_pid": 9001,
        "bundle_id": "dev.tomorrowstar.desktop",
        "executable": str(executable),
        "windows": 0,
        "active": False,
        "accessibility": True,
        "screen_recording": True,
    }
    (root / "native-tcc.json").write_text(json.dumps(native))
    permissions = {
        "source": {"pid": 2001, "attribution": "host"},
        "direct_capture_status": "not_checked",
        "accessibility": True,
        "screen_recording": True,
    }
    calls = []
    monkeypatch.setattr(module, "responsible", lambda pid: 9001)
    monkeypatch.setattr(module.os, "getppid", lambda: 9001)
    monkeypatch.setattr(module, "process_executable", lambda pid: str(executable), raising=False)

    def launch(command, **kwargs):
        assert command[1] == "serve"
        manifest = json.loads(Path(command[command.index("--capability-manifest") + 1]).read_text())
        assert manifest["allow"]["tools"] == ["check_permissions", "end_session"]
        Path(command[command.index("--socket") + 1]).touch()
        calls.append("daemon")
        return SimpleNamespace(pid=2001, poll=lambda: None, wait=lambda timeout: 0)

    monkeypatch.setattr(module.subprocess, "Popen", launch)

    def stop(command, **kwargs):
        assert command[1] == "stop"
        calls.append("stop")

    monkeypatch.setattr(module.subprocess, "run", stop)

    class Client:
        process = SimpleNamespace(pid=2002, poll=lambda: 0)

        def __init__(self, command, log, **kwargs):
            assert command[1] == "mcp"

        def call(self, name, arguments, **kwargs):
            assert name == "check_permissions" and arguments == {"prompt": False}
            calls.append("check_permissions")
            return permissions

        def close(self):
            calls.append("close")

    monkeypatch.setattr(cua_driver, "CuaMcpClient", Client)
    original_import = builtins.__import__

    def no_browser_import(name, *args, **kwargs):
        if name == "playwright.sync_api":
            pytest.fail("Permission-only readiness must not import the browser probe")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", no_browser_import)
    return module, root, permissions, native, calls


def test_permission_only_reports_grants_without_browser_or_attachment(probe):
    module, root, _, _, calls = probe

    assert module.run(root, permission_only=True) == 0

    result = json.loads((root / "background-result.json").read_text())
    assert result["status"] == "passed"
    assert result["mode"] == "permission-only"
    assert result["native_and_embedded_permissions_match"] is True
    assert result["browser_prepare_sent"] is False
    assert calls == ["daemon", "check_permissions", "close", "stop"]
    assert not (root / "synthetic-worker").exists()
    assert not (root / "synthetic.txt").exists()


def test_default_diagnostic_still_enters_the_full_browser_probe(probe, monkeypatch):
    module, root, _, _, calls = probe
    original_import = builtins.__import__

    def full_probe():
        raise RuntimeError("Synthetic full-browser probe reached; never launch")

    def controlled_import(name, *args, **kwargs):
        if name == "playwright.sync_api":
            return SimpleNamespace(sync_playwright=full_probe)
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", controlled_import)

    assert module.run(root) == 1

    result = json.loads((root / "background-result.json").read_text())
    assert result["message"] == "Synthetic full-browser probe reached; never launch"
    assert "mode" not in result
    assert calls == ["daemon", "check_permissions", "close", "stop"]
    assert (root / "synthetic-worker").is_dir()


def test_permission_only_cli_still_requires_an_independent_private_directory(tmp_path):
    shared = tmp_path / "shared"
    shared.mkdir(mode=0o755)
    result = subprocess.run(
        [
            sys.executable,
            "-I",
            "-B",
            str(Path(__file__).parents[1] / "macos/background_check.py"),
            "--permission-only",
            str(shared),
        ],
        capture_output=True,
        text=True,
        timeout=5,
    )
    assert result.returncode == 2
    assert "private diagnostic directory required" in result.stderr
    assert list(shared.iterdir()) == []


@pytest.mark.parametrize("missing", ["accessibility", "screen_recording"])
def test_permission_only_reports_missing_host_grant_without_browser(probe, missing):
    module, root, permissions, native, calls = probe
    permissions[missing] = native[missing] = False
    (root / "native-tcc.json").write_text(json.dumps(native))

    assert module.run(root, permission_only=True) == 0

    result = json.loads((root / "background-result.json").read_text())
    assert result["status"] == "permissions_required"
    assert result[missing] is False
    assert result["permission_prompts"] == 0
    assert calls == ["daemon", "check_permissions", "close", "stop"]
    assert not (root / "synthetic-worker").exists()


@pytest.mark.parametrize("mismatch", ["responsibility", "host_grant"])
def test_permission_only_refuses_wrong_responsibility_or_disagreeing_grant(
    probe, monkeypatch, mismatch
):
    module, root, permissions, _, calls = probe
    if mismatch == "responsibility":
        monkeypatch.setattr(module, "responsible", lambda pid: 9002)
    else:
        permissions["screen_recording"] = False

    assert module.run(root, permission_only=True) == 1

    result = json.loads((root / "background-result.json").read_text())
    assert result["status"] == "failed"
    assert result["error"] == "AssertionError"
    assert "native_and_embedded_permissions_match" not in result
    assert calls == (
        [] if mismatch == "responsibility" else ["daemon", "check_permissions", "close", "stop"]
    )
    assert not (root / "synthetic-worker").exists()


def test_shared_permission_probe_accepts_current_window_but_background_mode_stays_windowless(probe):
    module, root, _, native, calls = probe
    native.update(windows=1, active=True)
    resources = Path(module.__file__).parent
    result = module.probe_host_permissions(resources, root, native)
    assert result["native_and_embedded_permissions_match"] is True
    assert result["daemon_closed"] is True
    assert calls == ["daemon", "check_permissions", "close", "stop"]
    calls.clear()
    (root / "native-tcc.json").write_text(json.dumps(native))
    assert module.run(root, permission_only=True) == 1
    assert calls == []


@pytest.mark.parametrize("cancel_when", ["before", "after_call", "deadline"])
def test_shared_probe_has_one_deadline_and_cleans_only_its_separate_daemon(
    probe, monkeypatch, cancel_when
):
    import threading

    module, root, _, native, calls = probe
    cancelled = threading.Event()
    if cancel_when == "before":
        cancelled.set()
    elif cancel_when == "after_call":
        original = cua_driver.CuaMcpClient.call

        def cancel_after_call(self, *args, **kwargs):
            result = original(self, *args, **kwargs)
            cancelled.set()
            return result

        monkeypatch.setattr(cua_driver.CuaMcpClient, "call", cancel_after_call)
    else:
        # The same clock crosses the original deadline after the RPC. No budget reset.
        moments = iter([0, 0, 0, 0, 11])
        monkeypatch.setattr(module.time, "monotonic", lambda: next(moments))
    with pytest.raises(TimeoutError):
        module.probe_host_permissions(
            Path(module.__file__).parent, root, native, cancelled=cancelled
        )
    assert calls == (
        [] if cancel_when == "before" else ["daemon", "check_permissions", "close", "stop"]
    )
    assert not (root / "synthetic-worker").exists()
