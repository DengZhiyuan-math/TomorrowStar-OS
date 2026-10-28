"""Capability-local native startup checks against disposable workspaces only."""

import json
import os
import select
import shutil
import subprocess
import sys
import tempfile
import time
from http.client import HTTPConnection
from pathlib import Path
from urllib.parse import urlsplit

import pytest
import test_macos_portal as native_tests
from test_macos_portal import synthetic_native_root

native_launch_executable = native_tests.native_launch_executable


@pytest.fixture(scope="module")
def native_backend_environment(tmp_path_factory):
    compiler = shutil.which("swiftc")
    if sys.platform != "darwin" or compiler is None:
        pytest.skip("native environment regression requires macOS Swift")
    source = (Path(__file__).parents[1] / "macos/App.swift").read_text()
    start = source.index(
        '        process.environment = ["PATH":',
        source.index("    private func start(_ workspace: Workspace)"),
    )
    end = source.index("        process.standardInput = input", start)
    root = tmp_path_factory.mktemp("native-backend-environment")
    harness = root / "environment.swift"
    harness.write_text(
        "import Foundation\n"
        "struct Launch { let syntheticRoot: URL? }\n"
        'let launch = Launch(syntheticRoot: CommandLine.arguments[1] == "synthetic" '
        '? URL(fileURLWithPath: "/synthetic") : nil)\n'
        'let nonce = "synthetic-launch-nonce"\n'
        "let process = Process()\n"
        + source[start:end]
        + "let data = try JSONSerialization.data(withJSONObject: process.environment!)\n"
        + "print(String(decoding: data, as: UTF8.self))\n"
    )
    executable = root / "environment"
    subprocess.run(
        [compiler, "-module-cache-path", str(root / "cache"), str(harness), "-o", str(executable)],
        check=True,
        capture_output=True,
        text=True,
        timeout=60,
    )
    return executable


@pytest.mark.parametrize("mode", ["ordinary", "synthetic"])
def test_native_backend_forwards_only_supported_context_limits(native_backend_environment, mode):
    overrides = {
        "TOMORROWSTAR_MATCH_CONTEXT_BYTES": "1048576",
        "TOMORROWSTAR_MATERIAL_CONTEXT_BYTES": "800000",
        "TOMORROWSTAR_CODEX_EXECUTABLE": "/synthetic/model-cli",
        "TOMORROWSTAR_UNRELATED_OVERRIDE": "must-not-propagate",
        "OPENAI_API_KEY": "synthetic-secret-must-not-propagate",
    }
    result = subprocess.run(
        [str(native_backend_environment), mode],
        env=os.environ | overrides,
        capture_output=True,
        text=True,
        check=True,
        timeout=5,
    )
    environment = json.loads(result.stdout)
    for name in (
        "TOMORROWSTAR_MATCH_CONTEXT_BYTES",
        "TOMORROWSTAR_MATERIAL_CONTEXT_BYTES",
        "TOMORROWSTAR_CODEX_EXECUTABLE",
    ):
        if mode == "ordinary":
            assert environment.get(name) == overrides[name]
        else:
            assert name not in environment
    assert "TOMORROWSTAR_UNRELATED_OVERRIDE" not in environment
    assert "OPENAI_API_KEY" not in environment


@pytest.mark.parametrize("configured_by", ["argument", "environment"])
@pytest.mark.parametrize("mode", ["preparation", "application"])
@pytest.mark.parametrize("path_damage", ["missing", "long", "unknown-home"])
def test_invalid_model_path_preserves_native_data_read_and_correction(
    tmp_path, configured_by, mode, path_damage
):
    root = synthetic_native_root(tmp_path)
    document = root / "career/sources/service.md"
    document.parent.mkdir()
    original = "# Synthetic service\n\n## Scope\nImplemented Python.\n"
    document.write_text(original)
    fallback = tmp_path / "bin"
    fallback.mkdir()
    canary = tmp_path / "unexpected-model-call"
    executable = fallback / "codex"
    executable.write_text(f"#!/bin/sh\ntouch '{canary}'\nexit 91\n")
    executable.chmod(0o700)
    environment = os.environ | {
        "HOME": str(tmp_path),
        "CODEX_HOME": str(tmp_path / "private-codex-home"),
        "PATH": str(fallback) + ":/usr/bin:/bin:/usr/sbin:/sbin",
    }
    for key in ("OPENAI_API_KEY", "CODEX_API_KEY", "TOMORROWSTAR_NATIVE_LAUNCH_NONCE"):
        environment.pop(key, None)
    missing = root / ("x" * 300 if path_damage == "long" else "missing-cli")
    if path_damage == "unknown-home":
        missing = Path("~tomorrowstar-definitely-absent-user/codex")
    arguments = [
        sys.executable,
        str(Path(__file__).parents[1] / "macos/server.py"),
        "--applications",
        str(root / "applications"),
        "--career-workspace",
        str(root / "career"),
    ]
    if mode == "application":
        arguments.append("--single-job-flow")
    if configured_by == "argument":
        environment.pop("TOMORROWSTAR_CODEX_EXECUTABLE", None)
        arguments.extend(["--codex-executable", str(missing)])
    else:
        environment["TOMORROWSTAR_CODEX_EXECUTABLE"] = str(missing)
    process = subprocess.Popen(
        arguments,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=environment,
    )
    try:
        assert select.select([process.stdout], [], [], 10)[0]
        ready = json.loads(process.stdout.readline())
        assert ready["status"] == "ready", ready
        assert ready["capabilities"]["codex"] is False
        address = urlsplit(ready["url"])
        connection = HTTPConnection(address.hostname, address.port, timeout=5)

        def request(method, path, payload=None, token=None):
            connection.request(
                method,
                path,
                body=json.dumps(payload).encode() if payload is not None else None,
                headers={
                    "Origin": f"http://{address.netloc}",
                    "Content-Type": "application/json",
                    **({"X-CSRF-Token": token} if token else {}),
                },
            )
            response = connection.getresponse()
            body = json.loads(response.read())
            assert response.status in {200, 201}, body
            return body

        state = request("GET", "/api/state")
        token = state["csrf_token"]
        evidence = state["evidence"][0]
        shown = request("GET", f"/api/evidence/{evidence['id']}")
        assert shown["content"] == original
        corrected = original.replace("Python", "Python and SQLite")
        saved = request(
            "PATCH",
            f"/api/evidence/{evidence['id']}",
            {"revision": shown["revision"], "content": corrected},
            token,
        )
        assert saved["content"] == corrected
        assert saved["history"][0]["status"] == "applied"
        flow = request("GET", "/api/flow/state")
        assert flow["capabilities"]["codex_cli"] == "unavailable"
        application = request(
            "POST",
            "/api/applications",
            {"company": "Synthetic", "role_title": "Engineer", "job_description": "Python"},
            token,
        )["application"]
        task = request(
            "POST",
            "/api/flow/create",
            {"application_id": application["id"], "application_revision": application["revision"]},
            token,
        )
        request(
            "POST",
            "/api/flow/start",
            {"task_id": task["id"], "task_revision": task["revision"], "stage": "analysis"},
            token,
        )
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            task = request("GET", "/api/flow/state")["active_task"]
            if task["stages"]["analysis"]["status"] == "failed":
                break
            time.sleep(0.01)
        assert task["stages"]["analysis"]["error_code"] == "match_cli_missing"
        assert request("GET", f"/api/evidence/{evidence['id']}")["content"] == corrected
        assert document.read_text() == corrected
        assert not canary.exists()
        connection.close()
        process.stdin.close()
        assert process.wait(timeout=5) == 0
    finally:
        if process.poll() is None:
            process.kill()
            process.wait()


@pytest.mark.parametrize("mode", ["default", "single-job-flow", "automation-lab", "codex-handoff"])
@pytest.mark.parametrize("damage", ["relative", "null", "number", "link", "file"])
def test_unselected_preparation_root_cannot_block_native_launch(
    tmp_path, native_launch_executable, mode, damage
):
    root = synthetic_native_root(tmp_path)
    unused = tmp_path / "unused-preparation"
    value = "relative" if damage == "relative" else None if damage == "null" else 42
    before = None
    if damage == "link":
        target = tmp_path / "target"
        target.mkdir()
        unused.symlink_to(target, target_is_directory=True)
        value = str(unused)
    elif damage == "file":
        unused.write_bytes(b"preserved unrelated file")
        before = unused.read_bytes()
        value = str(unused)
    config = root / "portal.json"
    config.write_text(json.dumps(json.loads(config.read_text()) | {"preparation_root": value}))
    original = config.read_bytes()
    arguments = [str(native_launch_executable), "--config", str(config)]
    if mode != "default":
        arguments.append("--" + mode)
    result = subprocess.run(arguments, capture_output=True, text=True, timeout=5)
    assert result.returncode == 0, result.stderr
    shown = json.loads(result.stdout)
    assert "--flow-root" not in shown["arguments"]
    assert config.read_bytes() == original
    if damage == "link":
        assert unused.is_symlink()
        assert not list(target.iterdir())
    elif damage == "file":
        assert unused.read_bytes() == before


@pytest.fixture(scope="module")
def startup_failure_executable():
    compiler = shutil.which("swiftc")
    if sys.platform != "darwin" or compiler is None:
        pytest.skip("native startup message checks require macOS Swift")
    source = (Path(__file__).parents[1] / "macos/App.swift").read_text()
    code = source[
        source.index("struct BackendStartupFailure {") : source.index(
            "struct ResumeReviewResponse {"
        )
    ]
    with tempfile.TemporaryDirectory(
        prefix="tomorrowstar-startup-test-", dir="/private/tmp"
    ) as directory:
        root = Path(directory)
        harness = root / "startup.swift"
        harness.write_text(
            "import Foundation\n"
            + code
            + """
let reason = BackendStartupFailure.reason(from:
    ["status": "error", "code": CommandLine.arguments[1]])
let value: [String: Any] = ["message": BackendStartupFailure.message(for: reason),
    "chooseFolders": BackendStartupFailure.canChooseFolders(for: reason)]
let data = try JSONSerialization.data(withJSONObject: value)
print(String(decoding: data, as: UTF8.self))
"""
        )
        executable = root / "startup"
        subprocess.run(
            [
                compiler,
                "-module-cache-path",
                str(root / "cache"),
                str(harness),
                "-o",
                str(executable),
            ],
            check=True,
            capture_output=True,
            text=True,
            timeout=60,
        )
        yield executable


@pytest.mark.parametrize(
    "code",
    [
        "codex-unavailable",
        "worker-mode-required",
        "invalid_ready_response",
        "unknown-private-details",
    ],
)
def test_native_non_workspace_startup_failure_does_not_request_directory_repair(
    startup_failure_executable, code
):
    result = subprocess.run(
        [str(startup_failure_executable), code], capture_output=True, text=True, timeout=5
    )
    assert result.returncode == 0, result.stderr
    value = json.loads(result.stdout)
    assert value["chooseFolders"] is False
    assert "目录" not in value["message"]
    assert "unknown-private-details" not in value["message"]


def test_native_workspace_failure_retains_selected_directory_repair(startup_failure_executable):
    result = subprocess.run(
        [str(startup_failure_executable), "workspace-unavailable"],
        capture_output=True,
        text=True,
        timeout=5,
    )
    assert result.returncode == 0, result.stderr
    value = json.loads(result.stdout)
    assert value["chooseFolders"] is True
    assert "目录" in value["message"]
