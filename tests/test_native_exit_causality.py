"""Content-free lifecycle records distinguish real pipe EOF and real signals."""

import json
import os
import select
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest


@pytest.mark.parametrize("cause", ["parent_pipe_eof", "signal"])
@pytest.mark.parametrize("log_mode", ["private", "linked"])
def test_backend_records_actual_eof_or_signal_without_service_or_input_text(
    tmp_path, cause, log_mode
):
    script = tmp_path / "synthetic-child.py"
    backend = Path(__file__).parents[1] / "macos/server.py"
    diagnostics = tmp_path / "diagnostics"
    if log_mode == "linked":
        target = tmp_path / "unselected"
        target.mkdir()
        diagnostics.symlink_to(target, target_is_directory=True)
    script.write_text(
        "import importlib.util, threading\n"
        f"spec=importlib.util.spec_from_file_location('native_server', {str(backend)!r})\n"
        "module=importlib.util.module_from_spec(spec); spec.loader.exec_module(module)\n"
        "class Server:\n"
        " def __init__(self): self.stopped=threading.Event()\n"
        " def __enter__(self): return self\n"
        " def __exit__(self,*args): pass\n"
        " def shutdown(self): self.stopped.set()\n"
        " def serve_forever(self,poll_interval): self.stopped.wait(10)\n"
        f"module.serve_with_parent_pipe(Server(), {str(diagnostics)!r}, {{'status':'ready'}})\n"
    )
    process = subprocess.Popen(
        [sys.executable, "-I", "-B", "-u", str(script)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        assert select.select([process.stdout], [], [], 5)[0]
        line = process.stdout.readline()
        assert line, process.stderr.read()
        assert json.loads(line)["status"] == "ready"
        process.stdin.write("PRIVATE SYNTHETIC INPUT MUST NEVER BE LOGGED\n")
        process.stdin.flush()
        started = time.monotonic()
        if cause == "parent_pipe_eof":
            process.stdin.close()
        else:
            process.send_signal(signal.SIGTERM)
        assert process.wait(timeout=2) == 0
        assert time.monotonic() - started < 2
        if log_mode == "linked":
            assert list(target.iterdir()) == []
            return
        files = list(diagnostics.glob("backend-exit-*.jsonl"))
        assert len(files) == 1
        raw = files[0].read_text()
        rows = [json.loads(line) for line in raw.splitlines()]
        assert "PRIVATE SYNTHETIC" not in raw
        assert str(tmp_path) not in raw
        assert all(row["pid"] == process.pid and row["ppid"] == os.getpid() for row in rows)
        requested = [row for row in rows if row["event"] == "backend_shutdown_requested"]
        assert len(requested) == 1 and requested[0]["reason"] == cause
        assert rows[-1]["event"] == "backend_shutdown_complete"
        assert all(row["utc"].endswith("+00:00") for row in rows)
        events = [row["event"] for row in rows]
        assert ("parent_pipe_eof" in events) is (cause == "parent_pipe_eof")
        assert ("signal_received" in events) is (cause == "signal")
        if cause == "signal":
            assert next(row for row in rows if row["event"] == "signal_received")["signal"] == 15
        assert diagnostics.stat().st_mode & 0o777 == 0o700
        assert files[0].stat().st_mode & 0o777 == 0o600
    finally:
        if process.poll() is None:
            process.kill()
            process.wait()


@pytest.fixture(scope="module")
def native_exit_logger(tmp_path_factory):
    compiler = shutil.which("swiftc")
    if sys.platform != "darwin" or compiler is None:
        pytest.skip("Swift logger compilation requires macOS Swift")
    root = tmp_path_factory.mktemp("native-exit-logger")
    source = (Path(__file__).parents[1] / "macos/App.swift").read_text()
    helpers = source[
        source.index("func createDiagnosticDirectory(") : source.index(
            "// A fixed diagnostic route"
        )
    ]
    harness = root / "logger.swift"
    harness.write_text(
        "import Foundation\n"
        + helpers
        + """
let logger = NativeExitLog(parent: URL(fileURLWithPath: CommandLine.arguments[1]))
let child = Process()
child.executableURL = URL(fileURLWithPath: "/bin/sh")
child.arguments = ["-c", CommandLine.arguments[2] == "signal" ? "kill -TERM $$" : "exit 7"]
try child.run()
child.waitUntilExit()
logger?.record("backend_exited", childPID: child.processIdentifier,
    exitCode: child.terminationReason == .exit ? child.terminationStatus : nil,
    signal: child.terminationReason == .uncaughtSignal ? child.terminationStatus : nil)
"""
    )
    executable = root / "logger"
    subprocess.run(
        [
            compiler,
            "-module-cache-path",
            str(root / "compiler-cache"),
            str(harness),
            "-o",
            str(executable),
        ],
        check=True,
        capture_output=True,
        text=True,
        timeout=60,
    )
    return executable


@pytest.mark.parametrize("cause", ["exit", "signal"])
def test_native_logger_preserves_actual_child_exit_and_history(tmp_path, native_exit_logger, cause):
    parent = tmp_path / "diagnostics"
    for _ in range(2):
        subprocess.run([str(native_exit_logger), str(parent), cause], check=True, timeout=5)
    records = list(parent.glob("native-exit-*/events.jsonl"))
    assert len(records) == 2
    for path in records:
        raw = path.read_text()
        row = json.loads(raw)
        assert row["event"] == "backend_exited"
        assert row["child_pid"] > 0
        assert row["utc"].endswith("Z")
        assert row["signal" if cause == "signal" else "exit_code"] == (
            15 if cause == "signal" else 7
        )
        assert ("exit_code" in row) is (cause == "exit")
        assert ("signal" in row) is (cause == "signal")
        assert str(tmp_path) not in raw
        assert path.parent.stat().st_mode & 0o777 == 0o700
        assert path.stat().st_mode & 0o777 == 0o600


def test_native_logger_failure_does_not_prevent_child_exit(tmp_path, native_exit_logger):
    blocked = tmp_path / "blocked"
    blocked.write_text("preserve existing file")
    subprocess.run([str(native_exit_logger), str(blocked), "exit"], check=True, timeout=5)
    assert blocked.read_text() == "preserve existing file"
