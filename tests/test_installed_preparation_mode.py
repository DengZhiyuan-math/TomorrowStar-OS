"""The installed synthetic preparation entry never enables an application worker."""

import hashlib
import json
import os
import re
import select
import shutil
import subprocess
import sys
import tempfile
import time
from datetime import UTC, datetime
from http.client import HTTPConnection
from pathlib import Path
from urllib.parse import urlsplit

import pytest

CHECKOUT = Path(__file__).resolve().parents[1]


def assert_backend_diagnostics(root, expected):
    """Admit only complete, content-free exit records for these exact child PIDs."""
    directory = root / "runtime/diagnostics"
    assert not directory.is_symlink() and directory.is_dir()
    assert directory.stat().st_mode & 0o777 == 0o700
    records = {}
    observed = set()
    base = {"utc", "pid", "ppid", "event"}
    for path in directory.iterdir():
        match = re.fullmatch(r"backend-exit-([1-9][0-9]*)-[a-f0-9]{32}\.jsonl", path.name)
        assert match is not None, path.name
        pid = int(match[1])
        assert pid in expected and pid not in observed
        observed.add(pid)
        assert path.is_file() and not path.is_symlink()
        assert path.stat().st_mode & 0o777 == 0o600
        raw = path.read_bytes()
        rows = [json.loads(line) for line in raw.splitlines()]
        reason = expected[pid]
        event_names = ["backend_started"]
        event_names += ["signal_received"] if reason == "signal" else ["parent_pipe_eof"]
        event_names += ["backend_shutdown_requested", "backend_shutdown_complete"]
        assert [row["event"] for row in rows] == event_names
        timestamps = []
        for row in rows:
            event = row["event"]
            extra = {"signal"} if event == "signal_received" else set()
            if event in {"backend_shutdown_requested", "backend_shutdown_complete"}:
                extra = {"reason"}
                assert row["reason"] == reason
            if event == "signal_received":
                assert type(row["signal"]) is int and row["signal"] == 15
            assert set(row) == base | extra
            assert type(row["pid"]) is int and row["pid"] == pid
            assert type(row["ppid"]) is int and row["ppid"] == os.getpid()
            instant = datetime.fromisoformat(row["utc"])
            assert instant.utcoffset() == UTC.utcoffset(instant)
            timestamps.append(instant)
        assert timestamps == sorted(timestamps)
        records[str(path.relative_to(root))] = (raw, path.stat().st_mtime_ns)
    assert observed == set(expected)
    return records


def preparation_root(tmp_path):
    root = tmp_path / "synthetic preparation"
    root.mkdir(mode=0o700)
    for name in ("applications", "career", "home", "tmp", "runtime", "information-library"):
        (root / name).mkdir(mode=0o700)
    subprocess.run(["git", "init", "--quiet", "--template=", str(root / "career")], check=True)
    executable = root / "codex-fixture"
    executable.write_text("#!/bin/sh\nexit 91\n")
    executable.chmod(0o700)
    (root / "synthetic-flow.json").write_text(
        json.dumps(
            {
                "schemaVersion": 1,
                "purpose": "preparation-synthetic",
                "codex_sha256": hashlib.sha256(executable.read_bytes()).hexdigest(),
            }
        )
    )
    (root / "portal.json").write_text(
        json.dumps(
            {
                "applications": str(root / "applications"),
                "career_workspace": str(root / "career"),
            }
        )
    )
    return root


@pytest.fixture(scope="module")
def preparation_launch_executable():
    compiler = shutil.which("swiftc")
    if sys.platform != "darwin" or compiler is None:
        pytest.skip("native launch regression requires macOS Swift")
    source = (CHECKOUT / "macos/App.swift").read_text()
    code = source[
        source.index("struct Workspace: Codable") : source.index("final class AppDelegate:")
    ]
    with tempfile.TemporaryDirectory(prefix="preparation-launch-", dir="/private/tmp") as folder:
        root = Path(folder)
        harness = root / "launch.swift"
        harness.write_text(
            "import Foundation\n"
            + code
            + """
if CommandLine.arguments.count == 2 && CommandLine.arguments[1] == "--startup-failure" {
    let input = FileHandle.standardInput.readDataToEndOfFile()
    let result = (try? JSONSerialization.jsonObject(with: input)) as? [String: Any]
    print(BackendStartupFailure.reason(from: result))
    exit(0)
}
do {
    let launch = try NativeLaunch(arguments: CommandLine.arguments,
        home: URL(fileURLWithPath: "/ordinary/home"))
    let workspace = try launch.loadWorkspace()
    let result: [String: Any] = ["config": launch.configURL.path,
        "arguments": launch.backendArguments(workspace), "canSave": launch.canChangeWorkspace,
        "flowTitle": launch.flowTitle,
        "windowTitle": launch.windowTitle,
        "external": launch.canOpenExternal(URL(string: "https://example.com")!),
        "loopback": launch.canOpenExternal(URL(string: "http://127.0.0.1:1234")!)]
    let data = try JSONSerialization.data(withJSONObject: result, options: [.sortedKeys])
    print(String(decoding: data, as: UTF8.self))
} catch { exit(2) }
"""
        )
        executable = root / "launch"
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


def test_native_preparation_has_its_own_strict_entry_and_material_title(
    tmp_path, preparation_launch_executable
):
    root = preparation_root(tmp_path)
    result = subprocess.run(
        [str(preparation_launch_executable), "--synthetic-preparation", str(root)],
        capture_output=True,
        text=True,
        timeout=5,
    )
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == {
        "config": str(root / "portal.json"),
        "arguments": ["--synthetic-preparation", str(root)],
        "flowTitle": "材料准备",
        "windowTitle": "TomorrowStar · 合成材料准备",
        "canSave": False,
        "external": False,
        "loopback": True,
    }


@pytest.mark.parametrize(
    "status,code,expected",
    [
        ("error", "codex-unavailable", "codex-unavailable"),
        ("error", "workspace-unavailable", "workspace-unavailable"),
        ("error", "worker-mode-required", "worker-mode-required"),
        ("error", "PRIVATE UNKNOWN CODE", "invalid_ready_response"),
        ("ready", "codex-unavailable", "invalid_ready_response"),
    ],
)
def test_native_readiness_failure_keeps_only_allowlisted_code(
    preparation_launch_executable, status, code, expected
):
    result = subprocess.run(
        [str(preparation_launch_executable), "--startup-failure"],
        input=json.dumps(
            {"status": status, "code": code, "body": "PRIVATE body /private/material.pdf"}
        ),
        text=True,
        capture_output=True,
        timeout=5,
        check=True,
    )
    assert result.stdout.strip() == expected
    assert result.stderr == ""


def request(address, method, path, *, payload=None, token=None):
    connection = HTTPConnection(address.hostname, address.port, timeout=5)
    headers = {}
    if payload is not None:
        headers = {
            "Origin": f"http://{address.netloc}",
            "Content-Type": "application/json",
            "X-CSRF-Token": token,
        }
    connection.request(
        method,
        path,
        body=json.dumps(payload).encode() if payload is not None else None,
        headers=headers,
    )
    response = connection.getresponse()
    result = response.status, json.loads(response.read())
    connection.close()
    return result


def start_backend(root, unrelated):
    process = subprocess.Popen(
        [
            sys.executable,
            "-I",
            "-B",
            "-u",
            str(CHECKOUT / "macos/server.py"),
            "--synthetic-preparation",
            str(root),
        ],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=os.environ
        | {
            "HOME": str(unrelated),
            "CODEX_HOME": str(unrelated / "codex"),
            "OPENAI_API_KEY": "synthetic-must-be-cleared",
            "TOMORROWSTAR_CODEX_EXECUTABLE": "/invalid/formal-cli",
        },
    )
    assert select.select([process.stdout], [], [], 10)[0], "backend never became ready"
    line = process.stdout.readline()
    ready = json.loads(line)
    if ready.get("status") != "ready":
        process.wait(timeout=5)
        pytest.fail(f"Synthetic preparation did not start: {ready}; {process.stderr.read()}")
    return process, ready, urlsplit(ready["url"])


def stop_backend(process):
    if process.poll() is None:
        process.stdin.close()
        try:
            assert process.wait(timeout=5) == 0
        finally:
            if process.poll() is None:
                process.kill()
                process.wait()


def test_backend_refreshes_and_saves_fixed_recommendation_without_task_or_worker(tmp_path):
    root = preparation_root(tmp_path)
    unrelated = tmp_path / "unrelated home"
    unrelated.mkdir()
    process, ready, address = start_backend(root, unrelated)
    try:
        assert ready["capabilities"] == {
            "codex": True,
            "flow": True,
            "worker": False,
            "synthetic": True,
        }
        assert address.scheme == "http" and address.hostname == "127.0.0.1"
        assert address.fragment == "flow"
        status, initial = request(address, "GET", "/api/state")
        assert status == 200
        token = initial["csrf_token"]
        status, flow = request(address, "GET", "/api/flow/state")
        assert status == 200 and flow["mode"] == "preparation"
        assert flow["capabilities"]["worker"] is False and flow["tasks"] == []
        assert (
            request(address, "POST", "/api/recommendations/refresh", payload={}, token=token)[0]
            == 200
        )
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            status, intake = request(address, "GET", "/api/recommendations/state")
            if intake.get("status") != "running":
                break
            time.sleep(0.01)
        assert status == 200 and intake["status"] == "complete", intake
        assert len(intake["recommendations"]) == 1
        row = intake["recommendations"][0]
        assert row["company"] == "Synthetic Employer"
        assert row["url"] == "https://www.linkedin.com/jobs/view/424242"
        assert row["job_description"] == "Python\nunit tests"
        assert len(list((root / "applications").glob("*.json"))) == 1
        assert not list((root / "applications").glob("*.md"))
        assert row["selection_status"] == "saved"
        saved_id = row["existing_application"]["id"]
        status, saved = request(address, "GET", f"/api/applications/{saved_id}")
        assert status == 200
        assert saved["application"]["job_description"] == row["job_description"]
        assert saved["application"]["url"] == row["url"]
        primary = root / "applications" / saved["application"]["source_name"]
        saved_bytes = primary.read_bytes()
        assert json.loads(saved_bytes)["schema_version"] == "application-record/v1"
        status, selected = request(
            address,
            "POST",
            "/api/recommendations/select",
            payload={"id": row["id"], "revision": row["revision"]},
            token=token,
        )
        assert status == 200 and selected["created"] is False
        assert selected["application"]["id"] == saved_id
        assert primary.read_bytes() == saved_bytes
        assert len(list((root / "applications").glob("*.json"))) == 1
        assert not list((root / "applications").glob("*.md"))
        status, flow = request(address, "GET", "/api/flow/state")
        assert status == 200 and flow["tasks"] == []
        assert flow["capabilities"]["worker"] is False
        assert not list((root / "runtime").rglob("model-result.json"))
        assert {entry.name for entry in (root / "runtime").iterdir()} == {
            "material-preparation",
            "diagnostics",
        }
        assert list(unrelated.iterdir()) == []
        assert not (root / "home/Library").exists()
    finally:
        stop_backend(process)
    assert process.returncode == 0 and process.stderr.read() == ""
    assert_backend_diagnostics(root, {process.pid: "parent_pipe_eof"})


@pytest.mark.parametrize(
    "damage",
    [
        "missing",
        "relative",
        "config-override",
        "legacy-mode",
        "root-link",
        "config-link",
        "bad-paths",
        "equals-spelling",
    ],
)
def test_native_preparation_never_falls_back_to_ordinary_configuration(
    tmp_path, preparation_launch_executable, damage
):
    root = preparation_root(tmp_path)
    arguments = ["--synthetic-preparation", str(root)]
    if damage == "missing":
        arguments.pop()
    elif damage == "relative":
        arguments[1] = root.name
    elif damage == "config-override":
        arguments += ["--config", str(root / "portal.json")]
    elif damage == "legacy-mode":
        arguments += ["--synthetic-flow", str(root)]
    elif damage == "root-link":
        linked = tmp_path / "linked"
        linked.symlink_to(root, target_is_directory=True)
        arguments[1] = str(linked)
    elif damage == "config-link":
        (root / "portal.json").rename(root / "other.json")
        (root / "portal.json").symlink_to(root / "other.json")
    elif damage == "bad-paths":
        (root / "portal.json").write_text(
            '{"applications":"/outside","career_workspace":"/outside"}'
        )
    else:
        arguments = ["--synthetic-preparation=" + str(root)]
    result = subprocess.run(
        [str(preparation_launch_executable), *arguments],
        capture_output=True,
        text=True,
        timeout=5,
    )
    assert result.returncode == 2 and not result.stdout
    assert list((root / "runtime").iterdir()) == []


@pytest.mark.parametrize(
    "damage",
    [
        "hash",
        "purpose",
        "config",
        "root-link",
        "cli-link",
        "runtime-link",
        "library-link",
        "library-missing",
        "corrupt",
        "relative",
        "application-override",
        "information-override",
        "flow-override",
        "worker-override",
        "codex-override",
        "legacy-mode",
    ],
)
def test_backend_rejects_invalid_preparation_contract_before_creating_runtime(tmp_path, damage):
    root = preparation_root(tmp_path)
    outside = tmp_path / "preserved"
    outside.mkdir()
    sentinel = outside / "sentinel"
    sentinel.write_bytes(b"preserved")
    selected, extra = root, []
    if damage == "hash":
        (root / "codex-fixture").write_text("#!/bin/sh\nexit 92\n")
    elif damage == "purpose":
        marker = json.loads((root / "synthetic-flow.json").read_text())
        marker["purpose"] = "single-job-synthetic"
        (root / "synthetic-flow.json").write_text(json.dumps(marker))
    elif damage == "config":
        (root / "portal.json").write_text(
            json.dumps({"applications": str(outside), "career_workspace": str(root / "career")})
        )
    elif damage == "root-link":
        selected = tmp_path / "linked"
        selected.symlink_to(root, target_is_directory=True)
    elif damage == "cli-link":
        (root / "codex-fixture").rename(root / "actual-cli")
        (root / "codex-fixture").symlink_to(root / "actual-cli")
    elif damage == "runtime-link":
        (root / "runtime/material-preparation").symlink_to(outside, target_is_directory=True)
    elif damage in {"library-link", "library-missing"}:
        (root / "information-library").rmdir()
        if damage == "library-link":
            (root / "information-library").symlink_to(outside, target_is_directory=True)
    elif damage == "corrupt":
        (root / "synthetic-flow.json").write_bytes(b"{broken")
    elif damage == "relative":
        selected = Path(root.name)
    elif damage == "legacy-mode":
        extra = ["--synthetic-flow", str(root)]
    else:
        flag = {
            "application-override": "--applications",
            "information-override": "--information-library-root",
            "flow-override": "--flow-root",
            "worker-override": "--worker-root",
            "codex-override": "--codex-executable",
        }[damage]
        extra = [flag, str(outside)]
    ordinary = tmp_path / "ordinary-home"
    result = subprocess.run(
        [
            sys.executable,
            "-I",
            "-B",
            str(CHECKOUT / "macos/server.py"),
            "--synthetic-preparation",
            str(selected),
            *extra,
        ],
        input="",
        capture_output=True,
        text=True,
        timeout=5,
        cwd=tmp_path,
        env=os.environ | {"HOME": str(ordinary)},
    )
    assert result.returncode == 2
    if damage != "legacy-mode":
        assert json.loads(result.stdout) == {
            "status": "error",
            "code": "worker-mode-required"
            if damage == "worker-override"
            else "workspace-unavailable",
        }
    assert list((root / "runtime").iterdir()) == (
        [root / "runtime/material-preparation"] if damage == "runtime-link" else []
    )
    assert list(outside.iterdir()) == [sentinel] and sentinel.read_bytes() == b"preserved"
    assert not ordinary.exists()


@pytest.mark.parametrize("shutdown", ["eof", "sigterm"])
def test_backend_cold_reopen_restores_read_receipts_without_refresh_or_worker(tmp_path, shutdown):
    root = preparation_root(tmp_path)
    ordinary = tmp_path / "ordinary home"
    ordinary.mkdir()
    process, _, address = start_backend(root, ordinary)
    try:
        _, initial = request(address, "GET", "/api/state")
        assert (
            request(
                address,
                "POST",
                "/api/recommendations/refresh",
                payload={},
                token=initial["csrf_token"],
            )[0]
            == 200
        )
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            _, before = request(address, "GET", "/api/recommendations/state")
            if before.get("status") != "running":
                break
            time.sleep(0.01)
        assert before["status"] == "complete"
        if shutdown == "sigterm":
            process.terminate()
            assert process.wait(timeout=5) == 0
        else:
            stop_backend(process)
        assert process.stderr.read() == ""
    finally:
        stop_backend(process)
    runtime = root / "runtime/material-preparation"
    files_before = {
        path.relative_to(runtime): path.read_bytes()
        for path in runtime.rglob("*")
        if path.is_file()
    }
    reopened, _, address = start_backend(root, ordinary)
    try:
        _, restored = request(address, "GET", "/api/recommendations/state")
        assert restored == before
        _, flow = request(address, "GET", "/api/flow/state")
        assert flow["mode"] == "preparation" and flow["tasks"] == []
        assert flow["capabilities"]["worker"] is False
        assert {
            path.relative_to(runtime): path.read_bytes()
            for path in runtime.rglob("*")
            if path.is_file()
        } == files_before
        assert list(ordinary.iterdir()) == []
    finally:
        stop_backend(reopened)
    assert reopened.stderr.read() == ""
