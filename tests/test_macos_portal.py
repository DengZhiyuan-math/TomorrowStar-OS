"""Installed local-App boundaries, with synthetic Git workspaces only."""

import hashlib
import io
import json
import os
import runpy
import select
import shutil
import stat
import subprocess
import sys
import tempfile
import threading
from contextlib import suppress
from http.client import HTTPConnection
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from types import SimpleNamespace

import pytest

from career_evidence_graph.workspace import WorkspaceError, open_private_workspace


@pytest.fixture(scope="module")
def pipeline_status_executable():
    compiler = shutil.which("swiftc")
    if sys.platform != "darwin" or compiler is None:
        pytest.skip("native pipeline signal checks require macOS Swift")
    source = (Path(__file__).parents[1] / "macos/App.swift").read_text()
    code = source[
        source.index("struct PipelineStatus {") : source.index("struct Workspace: Codable")
    ]
    with tempfile.TemporaryDirectory(
        prefix="tomorrowstar-pipeline-test-", dir="/private/tmp"
    ) as directory:
        root = Path(directory)
        harness = root / "pipeline.swift"
        harness.write_text(
            "import Foundation\n"
            + code
            + """
if CommandLine.arguments[1] == "endpoint" {
    guard let base = URL(string: CommandLine.arguments[2]),
          let target = PipelineStatus.endpoint(base) else { exit(2) }
    print(target.absoluteString)
} else if CommandLine.arguments[1] == "request" {
    var completed = false
    let request = PipelineStatusRequest(endpoint: URL(string: CommandLine.arguments[2])!) { value in
        print(value?.running == true ? "running" : "refused")
        completed = true
    }
    request.start()
    let deadline = Date().addingTimeInterval(8)
    while !completed && Date() < deadline {
        RunLoop.current.run(until: Date().addingTimeInterval(0.05))
    }
    if !completed { request.cancel(); exit(3) }
} else {
    let data = FileHandle.standardInput.readDataToEndOfFile()
    guard let value = PipelineStatus.decode(data) else { exit(2) }
    print(value.running ? "running" : "paused")
    print(value.notificationID ?? "none")
}
"""
        )
        executable = root / "pipeline"
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


@pytest.mark.parametrize("response", ["valid", "redirect", "oversized-length", "oversized-stream"])
def test_native_pipeline_transport_is_bounded_and_does_not_follow_redirects(
    pipeline_status_executable, response
):
    requested = []

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            requested.append(self.path)
            if response == "redirect":
                self.send_response(302)
                self.send_header("Location", "/must-not-read")
                self.end_headers()
                return
            body = json.dumps(
                {
                    "protocol": "application-pipeline/v1",
                    "control": "running",
                    "status": "analysis",
                    "notification": None,
                    "padding": "x" * (65536 if response.startswith("oversized") else 0),
                }
            ).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            if response != "oversized-stream":
                self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            with suppress(BrokenPipeError, ConnectionResetError):
                self.wfile.write(body)

        def log_message(self, *_args):
            pass

    server = HTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        result = subprocess.run(
            [
                str(pipeline_status_executable),
                "request",
                f"http://127.0.0.1:{server.server_port}/api/pipeline/state",
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert result.returncode == 0, result.stderr
        assert result.stdout.strip() == ("running" if response == "valid" else "refused")
        assert requested == ["/api/pipeline/state"]
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


@pytest.mark.parametrize(
    "base",
    [
        "https://127.0.0.1:1234/",
        "http://localhost:1234/",
        "http://127.0.0.1/",
        "http://127.0.0.1:1234/api/",
        "http://user@127.0.0.1:1234/",
        "http://127.0.0.1:1234/?target=external",
        "http://127.0.0.1:1234/#external",
    ],
)
def test_native_pipeline_endpoint_refuses_unbound_addresses(pipeline_status_executable, base):
    result = subprocess.run(
        [str(pipeline_status_executable), "endpoint", base],
        capture_output=True,
        text=True,
        timeout=5,
    )
    assert result.returncode == 2


@pytest.mark.parametrize("fragment", ["", "#flow"])
def test_native_pipeline_endpoint_stays_on_exact_backend(pipeline_status_executable, fragment):
    result = subprocess.run(
        [str(pipeline_status_executable), "endpoint", "http://127.0.0.1:1234/" + fragment],
        capture_output=True,
        text=True,
        timeout=5,
    )
    assert result.returncode == 0
    assert result.stdout.strip() == "http://127.0.0.1:1234/api/pipeline/state"


@pytest.mark.parametrize(
    "control,status,notice,expected",
    [
        ("running", "analysis", None, "running\nnone\n"),
        (
            "paused",
            "ready_for_review",
            {"id": "ready-1", "title": "Ready", "message": "Review original page"},
            "paused\nready-1\n",
        ),
        (
            "paused",
            "needs_input",
            {"id": "input-1", "title": "Facts", "message": "Known source conflict"},
            "paused\ninput-1\n",
        ),
        (
            "paused",
            "blocked",
            {"id": "blocked-1", "title": "Stopped", "message": "Unknown open result"},
            "paused\nblocked-1\n",
        ),
    ],
)
def test_native_pipeline_decodes_only_terminal_notices(
    pipeline_status_executable, control, status, notice, expected
):
    payload = {
        "protocol": "application-pipeline/v1",
        "control": control,
        "status": status,
        "notification": notice,
    }
    result = subprocess.run(
        [str(pipeline_status_executable), "decode"],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        timeout=5,
    )
    assert result.returncode == 0
    assert result.stdout == expected


@pytest.mark.parametrize(
    "status",
    [
        "ready_for_review",
        "needs_input",
        "needs_recheck",
        "blocked",
        "cancelled",
        "expired",
        "paused",
        "interrupted",
        "no_matches",
    ],
)
def test_native_pipeline_decodes_actual_backend_persistent_notification(
    tmp_path, pipeline_status_executable, status
):
    from career_evidence_graph.application_pipeline import ApplicationPipeline
    from career_evidence_graph.career_portal_data import ApplicationStore

    applications = tmp_path / "applications"
    applications.mkdir()
    flow = SimpleNamespace(
        root=tmp_path / "flow", applications=ApplicationStore(applications), callbacks={}
    )
    worker = SimpleNamespace(snapshot=lambda: {"control": "paused"})
    intake = SimpleNamespace(snapshot=lambda: {"recommendations": []})
    pipeline = ApplicationPipeline(flow, intake, worker, interval=100)
    try:
        state = pipeline.snapshot()
        pipeline._stop(state, status, "Application result requires attention")
        saved = pipeline.snapshot()
        result = subprocess.run(
            [str(pipeline_status_executable), "decode"],
            input=json.dumps(saved),
            capture_output=True,
            text=True,
            timeout=5,
        )
        assert result.returncode == 0, result.stderr
        assert result.stdout == "paused\n" + saved["notification"]["id"] + "\n"
    finally:
        pipeline.close()


@pytest.mark.parametrize(
    "change",
    [
        "protocol",
        "control",
        "oversized",
        "notice-stage",
        "notice-id",
        "notice-title",
        "notice-message",
    ],
)
def test_native_pipeline_refuses_invalid_signal(pipeline_status_executable, change):
    payload = {
        "protocol": "application-pipeline/v1",
        "control": "running",
        "status": "ready_for_review",
        "notification": {"id": "n1", "title": "Ready", "message": "Review"},
    }
    if change in {"protocol", "control"}:
        payload[change] = "untrusted"
    elif change == "oversized":
        payload["padding"] = "x" * 65536
    elif change == "notice-stage":
        payload["status"] = "filling"
    else:
        payload["notification"][change.removeprefix("notice-")] = ""
    result = subprocess.run(
        [str(pipeline_status_executable), "decode"],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        timeout=5,
    )
    assert result.returncode == 2


@pytest.fixture(scope="module")
def diagnostic_directory_executable():
    compiler = shutil.which("swiftc")
    if sys.platform != "darwin" or compiler is None:
        pytest.skip("the native diagnostic directory regression requires macOS Swift")
    source = (Path(__file__).parents[1] / "macos/App.swift").read_text()
    directory_code = source[
        source.index("func createDiagnosticDirectory(") : source.index(
            "// A fixed diagnostic route"
        )
    ]
    with tempfile.TemporaryDirectory(
        prefix="tomorrowstar-diagnostic-test-", dir="/private/tmp"
    ) as directory:
        root = Path(directory)
        harness = root / "diagnostic-directory.swift"
        harness.write_text(
            "import Foundation\n"
            + directory_code
            + """
do {
    let parent = URL(fileURLWithPath: CommandLine.arguments[1], isDirectory: true)
    let root = try createDiagnosticDirectory(parent: parent, marker: CommandLine.arguments[2])
    print(root.path)
} catch {
    fputs("Diagnostic directory refused: \\(error)\\n", stderr)
    exit(1)
}
"""
        )
        executable = root / "diagnostic-directory"
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
        yield executable


def test_first_background_diagnostic_creates_private_parent_and_output(
    tmp_path, diagnostic_directory_executable
):
    parent = tmp_path / "TomorrowStar" / "diagnostics"
    marker = "gui-host-synthetic-1234"
    result = subprocess.run(
        [str(diagnostic_directory_executable), str(parent), marker],
        capture_output=True,
        text=True,
        timeout=5,
    )
    assert result.returncode == 0, result.stderr
    output = parent / marker
    assert result.stdout.strip() == str(output)
    assert output.is_dir()
    assert list(output.iterdir()) == []
    assert output.stat().st_mode & 0o777 == 0o700
    assert parent.stat().st_mode & 0o777 == 0o700
    assert parent.parent.stat().st_mode & 0o777 == 0o700


def test_background_diagnostic_preserves_previous_runs_in_existing_parent(
    tmp_path, diagnostic_directory_executable
):
    parent = tmp_path / "diagnostics"
    previous = parent / "gui-host-previous-1234"
    previous.mkdir(parents=True, mode=0o700)
    sentinel = previous / "sentinel"
    sentinel.write_text("preserved")
    output = parent / "gui-host-synthetic-1234"
    result = subprocess.run(
        [str(diagnostic_directory_executable), str(parent), output.name],
        capture_output=True,
        text=True,
        timeout=5,
    )
    assert result.returncode == 0, result.stderr
    assert output.is_dir()
    assert output.stat().st_mode & 0o777 == 0o700
    assert sentinel.read_text() == "preserved"
    assert list(output.iterdir()) == []


@pytest.mark.parametrize("existing", ["directory", "file", "symlink", "broken-symlink"])
def test_background_diagnostic_never_reuses_an_existing_marker(
    tmp_path, diagnostic_directory_executable, existing
):
    parent = tmp_path / "diagnostics"
    parent.mkdir(mode=0o700)
    output = parent / "gui-host-synthetic-1234"
    target = tmp_path / "existing-target"
    if existing == "directory":
        output.mkdir()
        (output / "sentinel").write_text("preserved")
    elif existing == "file":
        output.write_text("preserved")
    else:
        if existing == "symlink":
            target.mkdir()
            (target / "sentinel").write_text("preserved")
        output.symlink_to(target, target_is_directory=True)
    result = subprocess.run(
        [str(diagnostic_directory_executable), str(parent), output.name],
        capture_output=True,
        text=True,
        timeout=5,
    )
    assert result.returncode == 1
    assert "Diagnostic directory refused:" in result.stderr
    if existing == "file":
        assert output.read_text() == "preserved"
    elif existing == "broken-symlink":
        assert output.is_symlink()
        assert not target.exists()
    else:
        assert (output / "sentinel").read_text() == "preserved"
        assert [entry.name for entry in output.iterdir()] == ["sentinel"]


@pytest.mark.parametrize(
    "linked", ["parent", "ancestor", "missing-target", "missing-ancestor-target"]
)
def test_background_diagnostic_rejects_linked_parent_paths(
    tmp_path, diagnostic_directory_executable, linked
):
    target = tmp_path / "target"
    if linked not in {"missing-target", "missing-ancestor-target"}:
        target.mkdir()
    link = tmp_path / "linked"
    link.symlink_to(target, target_is_directory=True)
    parent = link / "diagnostics" if linked in {"ancestor", "missing-ancestor-target"} else link
    result = subprocess.run(
        [str(diagnostic_directory_executable), str(parent), "gui-host-synthetic-1234"],
        capture_output=True,
        text=True,
        timeout=5,
    )
    assert result.returncode == 1
    assert "Diagnostic directory refused:" in result.stderr
    assert link.is_symlink()
    if linked in {"missing-target", "missing-ancestor-target"}:
        assert not target.exists()
    else:
        assert list(target.iterdir()) == []


def test_native_backend_finds_bundled_codex_without_terminal_path(tmp_path, monkeypatch):
    import importlib.util

    from career_evidence_graph.codex_cli import CodexCLIError

    spec = importlib.util.spec_from_file_location(
        "macos_server", Path(__file__).parents[1] / "macos/server.py"
    )
    backend = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(backend)
    executable = (
        tmp_path
        / "Applications/ChatGPT.app/Contents/Resources/codex-cli/CodexCLI.app/Contents/MacOS/codex"
    )
    executable.parent.mkdir(parents=True)
    executable.write_text("#!/bin/sh\necho 'codex-cli synthetic'\n")
    executable.chmod(0o700)
    monkeypatch.setattr(backend.Path, "home", lambda: tmp_path)
    monkeypatch.setattr(backend.shutil, "which", lambda _: None)
    monkeypatch.delenv("TOMORROWSTAR_CODEX_EXECUTABLE", raising=False)

    assert backend.find_codex_executable() == str(executable)
    monkeypatch.setenv("TOMORROWSTAR_CODEX_EXECUTABLE", str(tmp_path / "missing"))
    with pytest.raises(CodexCLIError):
        backend.find_codex_executable()
    assert backend.find_codex_executable(executable) == str(executable)


def test_background_check_rejects_shared_or_linked_output_before_starting(tmp_path):
    import sys

    shared = tmp_path / "shared"
    shared.mkdir(mode=0o755)
    link = tmp_path / "linked"
    link.symlink_to(shared, target_is_directory=True)
    for destination in (shared, link):
        result = subprocess.run(
            [
                sys.executable,
                "-I",
                "-B",
                str(Path(__file__).parents[1] / "macos/background_check.py"),
                str(destination),
            ],
            capture_output=True,
            text=True,
            timeout=5,
        )
        assert result.returncode == 2
        assert "private diagnostic directory required" in result.stderr
        assert list(shared.iterdir()) == []


def test_bundle_rejects_unreviewed_helper_before_copying(tmp_path):
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "macos_build", Path(__file__).parents[1] / "macos/build.py"
    )
    builder = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(builder)
    driver = tmp_path / "unreviewed-driver"
    driver.write_bytes(b"Unreviewed synthetic executable")
    with pytest.raises(ValueError, match="reviewed CuaDriver"):
        builder.copy_cua_driver(tmp_path, driver)
    assert not (tmp_path / "cua-driver").exists()


def test_bundled_helper_records_the_native_successor_provenance(tmp_path, monkeypatch):
    import hashlib
    import importlib.util

    from career_evidence_graph import cua_driver

    spec = importlib.util.spec_from_file_location(
        "macos_build", Path(__file__).parents[1] / "macos/build.py"
    )
    builder = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(builder)
    driver = tmp_path / "reviewed-driver"
    driver.write_bytes(b"Synthetic reviewed executable")
    digest = hashlib.sha256(driver.read_bytes()).hexdigest()
    monkeypatch.setattr(cua_driver, "_OWNED_DRIVER_SHA256", digest)
    monkeypatch.setattr(builder.subprocess, "run", lambda *args, **kwargs: None)
    resources = tmp_path / "Resources"
    resources.mkdir()
    record = builder.copy_cua_driver(resources, driver)
    assert record["sha256"] == digest
    # One bundled driver serves the script and native takeover (MC-10 successor).
    assert record["source_manifest_sha256"] == (
        "2048257ac3d9079bbefd59712683da3b7a59668bd99c2bdd2167606d89e61d30"
    )
    assert record["source_divergence_patch_sha256"] == (
        "37737e187dbd1c2cb8e42e0024b98d7c0d881e6bfd8923043afef9ab2e483235"
    )
    assert "trusted native handoff" in record["local_divergence"]
    assert "DOM set_value with read-back" in record["local_divergence"]
    assert record["synthetic_keychain_patch_sha256"] == (
        "c9ac461bfbf6dcc106ebe7d4cba527a0ed06e6fb5260427b9b3c44ad60a0184a"
    )


def test_explicit_installed_system_root_accepts_only_a_separate_private_git_repo(tmp_path):
    installed = tmp_path / "TomorrowStar.app" / "Contents" / "Resources" / "system"
    installed.mkdir(parents=True)
    private = tmp_path / "private-career"
    private.mkdir()
    subprocess.run(["git", "init", "--quiet", str(private)], check=True)
    assert open_private_workspace(private, public_root=installed) == private.resolve()
    ordinary = tmp_path / "ordinary-folder"
    ordinary.mkdir()
    with pytest.raises(WorkspaceError, match="not-git"):
        open_private_workspace(ordinary, public_root=installed)
    (private / "installed-system").mkdir()
    with pytest.raises(WorkspaceError, match="not-separate"):
        open_private_workspace(private, public_root=private / "installed-system")


@pytest.mark.parametrize("mode", ["flow", "automation-lab", "codex-handoff"])
@pytest.mark.parametrize("packaged", [False, True])
def test_desktop_backend_announces_loopback_readiness_and_stops_on_parent_eof(
    tmp_path, mode, packaged
):
    import sys

    applications = tmp_path / "applications"
    applications.mkdir()
    career = tmp_path / "career"
    career.mkdir()
    subprocess.run(["git", "init", "--quiet", str(career)], check=True)
    backend = Path(__file__).parents[1] / "macos/server.py"
    if packaged:
        resources = tmp_path / "Folder With Spaces/TomorrowStar.app/Contents/Resources"
        resources.mkdir(parents=True)
        shutil.copy2(backend, resources / "server.py")
        shutil.copytree(
            Path(__file__).parents[1] / "src",
            resources / "system/src",
            ignore=shutil.ignore_patterns("__pycache__"),
        )
        backend = resources / "server.py"
    process = subprocess.Popen(
        [
            sys.executable,
            "-I",
            "-B",
            "-u",
            str(backend),
            "--applications",
            str(applications),
            "--career-workspace",
            str(career),
            "--handoff-root",
            str(tmp_path / "handoff"),
            "--worker-root",
            str(tmp_path / "worker"),
            "--flow-root",
            str(tmp_path / "flow"),
            "--single-job-flow" if mode == "flow" else "--" + mode,
        ],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=os.environ | {"HOME": str(tmp_path)},
    )
    try:
        assert select.select([process.stdout], [], [], 10)[0], "backend never became ready"
        ready = json.loads(process.stdout.readline())
        assert ready["status"] == "ready"
        from urllib.parse import urlsplit

        address = urlsplit(ready["url"])
        assert address.scheme == "http" and address.hostname == "127.0.0.1"
        assert (
            address.fragment
            == {"flow": "flow", "automation-lab": "overview", "codex-handoff": "handoff"}[mode]
        )
        connection = HTTPConnection(address.hostname, address.port, timeout=5)
        connection.request("GET", "/api/state")
        response = connection.getresponse()
        assert response.status == 200
        state = json.loads(response.read())
        assert state["applications"] == []
        connection.request("GET", "/api/state", headers={"Host": "attacker.invalid"})
        response = connection.getresponse()
        assert response.status == 403
        response.read()
        payload = json.dumps({"company": "Synthetic Native", "role_title": "Engineer"})
        connection.request("POST", "/api/applications", body=payload)
        response = connection.getresponse()
        assert response.status == 403
        response.read()
        from urllib.parse import urlunsplit

        connection.request(
            "POST",
            "/api/applications",
            body=payload,
            headers={
                "Content-Type": "application/json",
                "Origin": urlunsplit((address.scheme, address.netloc, "", "", "")),
                "X-CSRF-Token": state["csrf_token"],
            },
        )
        response = connection.getresponse()
        assert response.status == 201
        response.read()
        connection.request("GET", "/static/application_flow.js")
        response = connection.getresponse()
        assert response.status == 200
        response.read()
        connection.close()
        connection = HTTPConnection(address.hostname, address.port, timeout=5)
        connection.request("GET", "/api/worker/state")
        response = connection.getresponse()
        assert response.status == 200
        worker = json.loads(response.read())
        assert worker["enabled"] is (mode == "automation-lab")
        assert (tmp_path / "worker" / "run.json").is_file() is (mode != "codex-handoff")
        if mode == "automation-lab":
            assert worker["cua_enabled"] is True
            assert worker["cua_click_route"] == "dom_event"
            assert worker["live_enabled"] is True
            assert worker["generic_enabled"] is True
            assert worker["worker_pid"] is None
        connection.close()
        connection = HTTPConnection(address.hostname, address.port, timeout=5)
        connection.request("GET", "/api/handoff/state")
        response = connection.getresponse()
        assert response.status == 200
        assert json.loads(response.read())["enabled"] is (mode == "codex-handoff")
        connection.close()
        connection = HTTPConnection(address.hostname, address.port, timeout=5)
        connection.request("GET", "/api/flow/state")
        response = connection.getresponse()
        flow = json.loads(response.read())
        assert flow["enabled"] is (mode == "flow")
        if mode == "flow":
            assert flow["capabilities"]["worker"] is True
        connection.close()
        assert (tmp_path / "handoff").exists() is (mode == "codex-handoff")
        process.stdin.close()
        assert process.wait(timeout=5) == 0
        assert process.stderr.read() == ""
        with pytest.raises(OSError):
            HTTPConnection(address.hostname, address.port, timeout=1).connect()
    finally:
        if process.poll() is None:
            process.kill()
            process.wait()


def synthetic_native_root(tmp_path):
    root = tmp_path / "synthetic flow"
    root.mkdir(mode=0o700)
    for name in ("applications", "career", "home", "tmp", "runtime"):
        (root / name).mkdir(mode=0o700)
    subprocess.run(["git", "init", "--quiet", str(root / "career")], check=True)
    executable = root / "codex-fixture"
    executable.write_text("#!/bin/sh\nexit 91\n")
    executable.chmod(0o700)
    (root / "synthetic-flow.json").write_text(
        json.dumps(
            {
                "schemaVersion": 1,
                "purpose": "single-job-synthetic",
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


def test_synthetic_native_backend_is_isolated_and_cannot_refresh_gmail(tmp_path):
    root = synthetic_native_root(tmp_path)
    unrelated = tmp_path / "ordinary-home"
    unrelated.mkdir()
    process = subprocess.Popen(
        [
            sys.executable,
            str(Path(__file__).parents[1] / "macos/server.py"),
            "--synthetic-flow",
            str(root),
        ],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=os.environ
        | {"HOME": str(unrelated), "TOMORROWSTAR_CODEX_EXECUTABLE": "/invalid/formal-cli"},
    )
    try:
        assert select.select([process.stdout], [], [], 10)[0]
        ready = json.loads(process.stdout.readline())
        assert ready["status"] == "ready", ready
        assert ready["capabilities"]["synthetic"] is True
        from urllib.parse import urlsplit, urlunsplit

        address = urlsplit(ready["url"])
        assert address.fragment == "flow"
        connection = HTTPConnection(address.hostname, address.port, timeout=5)
        connection.request("GET", "/api/state")
        response = connection.getresponse()
        state = json.loads(response.read())
        connection.request(
            "POST",
            "/api/recommendations/refresh",
            body=b"{}",
            headers={
                "Origin": urlunsplit((address.scheme, address.netloc, "", "", "")),
                "Content-Type": "application/json",
                "X-CSRF-Token": state["csrf_token"],
            },
        )
        response = connection.getresponse()
        assert response.status == 503
        assert json.loads(response.read())["error"] == "synthetic_gmail_disabled"
        connection.close()
        assert (root / "runtime/single-job-worker/run.json").is_file()
        assert (root / "runtime/single-job-flow").is_dir()
        assert list(unrelated.iterdir()) == []
        assert not (root / "home/Library").exists()
        process.stdin.close()
        assert process.wait(timeout=5) == 0
        assert process.stderr.read() == ""
    finally:
        if process.poll() is None:
            process.kill()
            process.wait()


@pytest.mark.parametrize(
    "damage",
    [
        "hash",
        "config",
        "root-link",
        "cli-link",
        "runtime-link",
        "corrupt",
        "relative",
        "override",
        "information-override",
        "mail-setting-override",
        "old-mode",
    ],
)
def test_synthetic_native_rejects_invalid_contract_before_creating_runtime(tmp_path, damage):
    root = synthetic_native_root(tmp_path)
    outside = tmp_path / "preserved"
    outside.mkdir()
    (outside / "sentinel").write_text("preserved")
    selected = root
    extra = []
    if damage == "hash":
        (root / "codex-fixture").write_text("#!/bin/sh\nexit 92\n")
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
        (root / "runtime/single-job-worker").symlink_to(outside, target_is_directory=True)
    elif damage == "corrupt":
        (root / "synthetic-flow.json").write_bytes(b"{broken")
    elif damage == "relative":
        selected = Path(root.name)
    elif damage == "override":
        extra = ["--applications", str(outside)]
    elif damage == "information-override":
        extra = ["--information-library-root", str(outside)]
    elif damage == "mail-setting-override":
        extra = ["--application-processed-label="]
    else:
        extra = ["--codex-handoff"]
    before = {path.name: path.read_bytes() for path in outside.iterdir()}
    result = subprocess.run(
        [
            sys.executable,
            str(Path(__file__).parents[1] / "macos/server.py"),
            "--synthetic-flow",
            str(selected),
            *extra,
        ],
        input="",
        capture_output=True,
        text=True,
        timeout=5,
        cwd=tmp_path,
        env=os.environ | {"HOME": str(tmp_path / "ordinary-home")},
    )
    assert result.returncode == 2
    if damage != "old-mode":
        assert json.loads(result.stdout)["status"] == "error"
        assert str(root) not in result.stdout
    assert {path.name: path.read_bytes() for path in outside.iterdir()} == before
    assert not (root / "runtime/single-job-flow").exists()
    assert not (tmp_path / "ordinary-home").exists()


@pytest.fixture(scope="module")
def native_launch_executable():
    compiler = shutil.which("swiftc")
    if sys.platform != "darwin" or compiler is None:
        pytest.skip("native launch regression requires macOS Swift")
    source = (Path(__file__).parents[1] / "macos/App.swift").read_text()
    code = source[
        source.index("struct Workspace: Codable") : source.index("final class AppDelegate:")
    ]
    with tempfile.TemporaryDirectory(
        prefix="tomorrowstar-launch-test-", dir="/private/tmp"
    ) as directory:
        root = Path(directory)
        harness = root / "launch.swift"
        harness.write_text(
            "import Foundation\n"
            + code
            + """
do {
    let launch = try NativeLaunch(arguments: CommandLine.arguments,
        home: URL(fileURLWithPath: "/ordinary/home"))
    guard var workspace = try launch.loadWorkspaceIfPresent() else {
        guard launch.canChangeWorkspace else { exit(2) }
        print("choose-folders")
        exit(0)
    }
    if ProcessInfo.processInfo.environment["TOMORROWSTAR_TEST_CHANGE_FOLDERS"] == "1" {
        workspace = try JSONDecoder().decode(Workspace.self, from: JSONEncoder().encode(
            workspace.selectingFolders(applications: "/changed/applications",
                careerWorkspace: "/changed/career")))
    }
    if ProcessInfo.processInfo.environment["TOMORROWSTAR_TEST_SAVE_FOLDERS"] == "1" {
        try launch.saveWorkspace(workspace.selectingFolders(applications: "/changed/applications",
            careerWorkspace: "/changed/career"))
    }
    if let label = ProcessInfo.processInfo.environment["TOMORROWSTAR_TEST_MAIL_LABEL"] {
        try launch.saveMailProcessingLabel(label)
        workspace = try launch.loadWorkspace()
    }
    if let takeover = ProcessInfo.processInfo.environment["TOMORROWSTAR_TEST_TAKEOVER"] {
        try launch.saveAutomaticTakeover(takeover == "on")
        workspace = try launch.loadWorkspace()
    }
    let result: [String: Any] = ["config": launch.configURL.path,
        "arguments": launch.backendArguments(workspace), "canSave": launch.canChangeWorkspace,
        "flowTitle": launch.flowTitle, "canSaveMail": launch.canChangeMailProcessing,
        "pipeline": launch.backgroundPipelineEnabled,
        "nativeReceipts": launch.nativeHostReceiptsEnabled,
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


def test_native_synthetic_launch_uses_only_selected_config_and_blocks_external_links(
    tmp_path, native_launch_executable
):
    root = synthetic_native_root(tmp_path)
    result = subprocess.run(
        [str(native_launch_executable), "--synthetic-flow", str(root)],
        capture_output=True,
        text=True,
        timeout=5,
    )
    assert result.returncode == 0, result.stderr
    value = json.loads(result.stdout)
    assert value == {
        "config": str(root / "portal.json"),
        "arguments": ["--synthetic-flow", str(root)],
        "flowTitle": "单岗位申请",
        "canSave": False,
        "canSaveMail": False,
        "pipeline": False,
        "nativeReceipts": True,
        "external": False,
        "loopback": True,
    }


def test_native_synthetic_mail_saves_only_current_label_and_reopens(
    tmp_path, native_launch_executable
):
    root = synthetic_native_root(tmp_path)
    config = root / "portal.json"
    preparation = root / "latex-base"
    preparation.mkdir(parents=True)
    data = json.loads(config.read_text()) | {
        "preparation_root": str(preparation),
        "application_processed_label": "previous",
    }
    config.write_text(json.dumps(data))
    arguments = [str(native_launch_executable), "--synthetic-mail", str(root)]
    opened = subprocess.run(arguments, capture_output=True, text=True, timeout=5)
    assert opened.returncode == 0, opened.stderr
    value = json.loads(opened.stdout)
    assert value["config"] == str(config)
    assert value["arguments"] == ["--synthetic-mail", str(root)]
    assert value["canSave"] is False
    assert value["canSaveMail"] is True
    assert value["pipeline"] is True
    assert value["nativeReceipts"] is False
    assert value["flowTitle"] == "自动申请"
    # A stale in-memory folder selection cannot replace the saved fixed roots.
    saved = subprocess.run(
        arguments,
        env=os.environ
        | {
            "TOMORROWSTAR_TEST_CHANGE_FOLDERS": "1",
            "TOMORROWSTAR_TEST_MAIL_LABEL": "  exact raw label  ",
        },
        capture_output=True,
        text=True,
        timeout=5,
    )
    assert saved.returncode == 0, saved.stderr
    assert json.loads(config.read_text()) == data | {
        "application_processed_label": "  exact raw label  "
    }
    assert stat.S_IMODE(config.stat().st_mode) == 0o600
    reopened = subprocess.run(arguments, capture_output=True, text=True, timeout=5)
    assert reopened.returncode == 0, reopened.stderr
    assert json.loads(reopened.stdout) == json.loads(saved.stdout)
    before = config.read_bytes()
    refused = subprocess.run(
        arguments,
        env=os.environ | {"TOMORROWSTAR_TEST_SAVE_FOLDERS": "1"},
        capture_output=True,
        text=True,
        timeout=5,
    )
    assert refused.returncode == 2
    assert config.read_bytes() == before


@pytest.mark.parametrize(
    "mode", ["--synthetic-flow", "--synthetic-preparation", "--synthetic-browser"]
)
def test_native_old_synthetic_modes_reject_mail_setting_saves(
    tmp_path, native_launch_executable, mode
):
    root = synthetic_native_root(tmp_path)
    config = root / "portal.json"
    before = config.read_bytes()
    arguments = [str(native_launch_executable), mode, str(root)]
    opened = subprocess.run(arguments, capture_output=True, text=True, timeout=5)
    assert opened.returncode == 0
    value = json.loads(opened.stdout)
    assert value["canSave"] is False
    assert value["canSaveMail"] is False
    assert value["pipeline"] is False
    assert value["nativeReceipts"] is True
    saved = subprocess.run(
        arguments,
        env=os.environ | {"TOMORROWSTAR_TEST_MAIL_LABEL": "fixture label"},
        capture_output=True,
        text=True,
        timeout=5,
    )
    assert saved.returncode == 2
    assert config.read_bytes() == before


@pytest.mark.parametrize("field", ["applications", "career_workspace", "preparation_root"])
def test_native_synthetic_mail_rejects_changed_fixed_folders(
    tmp_path, native_launch_executable, field
):
    root = synthetic_native_root(tmp_path)
    config = root / "portal.json"
    data = json.loads(config.read_text()) | {"preparation_root": str(root / "latex-base")}
    data[field] = str(tmp_path / "outside")
    config.write_text(json.dumps(data))
    before = config.read_bytes()
    result = subprocess.run(
        [str(native_launch_executable), "--synthetic-mail", str(root)],
        env=os.environ | {"TOMORROWSTAR_TEST_MAIL_LABEL": "fixture label"},
        capture_output=True,
        text=True,
        timeout=5,
    )
    assert result.returncode == 2
    assert not result.stdout
    assert config.read_bytes() == before
    assert not (tmp_path / "outside").exists()


def test_native_without_codex_defaults_to_preparation_and_keeps_old_roots_untouched(tmp_path):
    root = synthetic_native_root(tmp_path)
    support = tmp_path / "Library/Application Support/TomorrowStar"
    for name in (
        "application-worker",
        "application-automation-lab",
        "codex-handoff",
        "single-job-flow",
        "single-job-worker",
    ):
        directory = support / name
        directory.mkdir(parents=True)
        (directory / "run.json").write_bytes(b"preserved legacy state")
    before = {str(path): path.read_bytes() for path in support.rglob("*") if path.is_file()}
    code = (
        "import runpy,sys\n"
        "module=runpy.run_path(sys.argv.pop(1))\n"
        "module['main'].__globals__['find_codex_executable']=lambda configured:None\n"
        "raise SystemExit(module['main']())\n"
    )
    environment = os.environ | {
        "HOME": str(tmp_path),
        "CODEX_HOME": str(tmp_path / "synthetic-codex-home"),
    }
    for key in ("CODEX_API_KEY", "OPENAI_API_KEY"):
        environment.pop(key, None)
    environment.pop("TOMORROWSTAR_CODEX_EXECUTABLE", None)
    process = subprocess.Popen(
        [
            sys.executable,
            "-c",
            code,
            str(Path(__file__).parents[1] / "macos/server.py"),
            "--applications",
            str(root / "applications"),
            "--career-workspace",
            str(root / "career"),
        ],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=environment,
    )
    try:
        assert select.select([process.stdout], [], [], 10)[0]
        ready = json.loads(process.stdout.readline())
        assert ready["status"] == "ready"
        assert ready["capabilities"]["codex"] is False
        assert ready["capabilities"]["flow"] is True
        assert ready["capabilities"]["worker"] is False
        assert (support / "material-preparation").is_dir()
        from urllib.parse import urlsplit

        address = urlsplit(ready["url"])
        assert address.fragment == "flow"
        connection = HTTPConnection(address.hostname, address.port, timeout=5)
        connection.request("GET", "/api/flow/state")
        response = connection.getresponse()
        assert response.status == 200
        flow = json.loads(response.read())
        assert flow["mode"] == "preparation"
        assert flow["capabilities"]["worker"] is False
        assert flow["worker"] == {"enabled": False}
        assert flow["tasks"] == []
        assert flow["preparation"]["checks"]
        connection.close()
        assert all(Path(path).read_bytes() == data for path, data in before.items())
        assert all(
            list((support / name).iterdir()) == [support / name / "run.json"]
            for name in (
                "application-worker",
                "application-automation-lab",
                "codex-handoff",
                "single-job-flow",
                "single-job-worker",
            )
        )
        process.stdin.close()
        assert process.wait(timeout=5) == 0
        assert process.stderr.read() == ""
    finally:
        if process.poll() is None:
            process.kill()
            process.wait()


def test_native_preparation_rejects_worker_root_before_creating_runtime(tmp_path):
    root = synthetic_native_root(tmp_path)
    worker = tmp_path / "unexpected-worker"
    support = tmp_path / "Library/Application Support/TomorrowStar"
    result = subprocess.run(
        [
            sys.executable,
            str(Path(__file__).parents[1] / "macos/server.py"),
            "--applications",
            str(root / "applications"),
            "--career-workspace",
            str(root / "career"),
            "--worker-root",
            str(worker),
        ],
        input="",
        capture_output=True,
        text=True,
        timeout=5,
        env=os.environ | {"HOME": str(tmp_path)},
    )
    assert result.returncode == 2
    assert json.loads(result.stdout) == {"status": "error", "code": "worker-mode-required"}
    assert not worker.exists()
    assert not support.exists()


@pytest.mark.parametrize("library_kind", ["default", "explicit", "missing"])
def test_native_preparation_reads_existing_information_without_starting_or_migrating_worker(
    tmp_path, monkeypatch, capsys, library_kind
):
    from career_evidence_graph._vendor import job_apply_store as helper
    from career_evidence_graph.application_information import condition_from_library

    root = synthetic_native_root(tmp_path)
    support = tmp_path / "Library/Application Support/TomorrowStar"
    worker = support / "single-job-worker"
    worker.mkdir(parents=True)
    (worker / "run.json").write_bytes(b"invalid legacy run; must never be read")
    (worker / "execution-owner.json").write_bytes(b"preserved legacy ownership")
    library_root = worker / "answer-library"
    if library_kind == "explicit":
        library_root = tmp_path / "explicit-information"
    if library_kind != "missing":
        library_root.mkdir()
        key = helper.answer_key("French proficiency CEFR", {})
        (library_root / "answers.json").write_text(
            json.dumps(
                {
                    "schemaVersion": 1,
                    "answers": {
                        key: {
                            "key": key,
                            "question": "French proficiency CEFR",
                            "value": "C1",
                            "scope": {},
                            "state": "confirmed",
                        }
                    },
                    "metadata": {},
                }
            )
        )
        (library_root / "profile.json").write_text(
            json.dumps(
                {
                    "schemaVersion": 1,
                    "profile": {"phone": "synthetic-private-phone", "preferences": {}},
                    "metadata": {},
                }
            )
        )
    before = {
        str(path): path.read_bytes()
        for directory in (worker, library_root)
        for path in directory.rglob("*")
        if path.is_file()
    }
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("CODEX_HOME", str(tmp_path / "synthetic-codex-home"))
    for name in ("OPENAI_API_KEY", "CODEX_API_KEY", "TOMORROWSTAR_CODEX_EXECUTABLE"):
        monkeypatch.delenv(name, raising=False)
    module = runpy.run_path(str(Path(__file__).parents[1] / "macos/server.py"))
    namespace = module["main"].__globals__
    actual_create_server = namespace["create_server"]
    observed = {}

    def inspect_server(*args, **kwargs):
        server = actual_create_server(*args, **kwargs)
        observed["worker_root"] = kwargs["worker_root"]
        observed["pdf_inspector"] = kwargs.get("resume_review_pdf_inspector")
        observed["resume_pdf_inspector"] = server.application_resume_store.pdf_inspector
        observed["library_root"] = kwargs.get("information_library_root")
        observed["worker"] = server.worker_service
        observed["library"] = server.application_flow_service.information_provider()
        server.serve_forever = lambda **_kwargs: None
        server.shutdown = lambda: None
        return server

    monkeypatch.setitem(namespace, "create_server", inspect_server)
    monkeypatch.setitem(namespace, "find_codex_executable", lambda _configured: None)
    monkeypatch.setattr("signal.signal", lambda *_args: None)
    monkeypatch.setattr(sys, "stdin", SimpleNamespace(buffer=io.BytesIO()))
    arguments = [
        "server.py",
        "--applications",
        str(root / "applications"),
        "--career-workspace",
        str(root / "career"),
    ]
    if library_kind == "explicit":
        arguments.extend(["--information-library-root", str(library_root)])
    monkeypatch.setattr(sys, "argv", arguments)
    assert module["main"]() == 0
    assert observed["worker_root"] is None
    assert observed["pdf_inspector"] is not None
    assert observed["resume_pdf_inspector"] is observed["pdf_inspector"]
    assert observed["worker"] is None
    assert observed["library_root"] == library_root
    library = observed["library"]
    if library_kind == "missing":
        assert library["status"] == "unavailable"
        assert not library_root.exists()
    else:
        assert library["status"] == "available"
        assert condition_from_library("French B2 required", {}, library)["status"] == "supported"
        assert not (library_root / "sessions").exists()
    assert all(Path(path).read_bytes() == value for path, value in before.items())
    assert set(worker.iterdir()) == {
        worker / "run.json",
        worker / "execution-owner.json",
        *([worker / "answer-library"] if library_kind == "default" else []),
    }
    assert "synthetic-private-phone" not in capsys.readouterr().out


@pytest.mark.parametrize(
    "mode", ["default", "prepare-materials", "single-job-flow", "automation-lab", "codex-handoff"]
)
def test_native_normal_launch_defaults_to_application_and_keeps_explicit_modes(
    tmp_path, native_launch_executable, mode
):
    root = synthetic_native_root(tmp_path)
    arguments = ["--config", str(root / "portal.json")]
    if mode != "default":
        arguments.append("--" + mode)
    result = subprocess.run(
        [str(native_launch_executable), *arguments], capture_output=True, text=True, timeout=5
    )
    assert result.returncode == 0
    value = json.loads(result.stdout)
    assert value["canSave"] is True and value["external"] is True
    expected_mode = "single-job-flow" if mode == "default" else mode
    assert value["flowTitle"] == (
        "材料准备"
        if mode == "prepare-materials"
        else "自动申请"
        if expected_mode == "single-job-flow"
        else "单岗位申请"
    )
    assert value["arguments"] == [
        "--applications",
        str(root / "applications"),
        "--career-workspace",
        str(root / "career"),
        *(["--" + expected_mode] if mode != "prepare-materials" else []),
        # MC-22: automatic takeover is on by default in the single-job flow.
        *(TAKEOVER_FLAGS if expected_mode == "single-job-flow" else []),
    ]


@pytest.mark.parametrize("equals_spelling", [False, True])
def test_native_implicit_application_launch_rejects_unrequested_worker_root(
    tmp_path, native_launch_executable, equals_spelling
):
    root = synthetic_native_root(tmp_path)
    worker = tmp_path / "unexpected-worker"
    override = (
        ["--worker-root=" + str(worker)] if equals_spelling else ["--worker-root", str(worker)]
    )
    result = subprocess.run(
        [
            str(native_launch_executable),
            "--config",
            str(root / "portal.json"),
            *override,
        ],
        capture_output=True,
        text=True,
        timeout=5,
    )
    assert result.returncode == 2
    assert not result.stdout
    assert not worker.exists()


def test_native_single_job_launch_forwards_explicit_worker_root(tmp_path, native_launch_executable):
    root = synthetic_native_root(tmp_path)
    worker = tmp_path / "next-worker"
    result = subprocess.run(
        [
            str(native_launch_executable),
            "--config",
            str(root / "portal.json"),
            "--single-job-flow",
            "--worker-root",
            str(worker),
        ],
        capture_output=True,
        text=True,
        timeout=5,
    )
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["arguments"] == [
        "--applications",
        str(root / "applications"),
        "--career-workspace",
        str(root / "career"),
        "--single-job-flow",
        "--worker-root",
        str(worker),
        *TAKEOVER_FLAGS,
    ]
    assert not worker.exists()


def test_native_single_job_launch_accepts_existing_unlinked_worker_root(
    tmp_path, native_launch_executable
):
    root = synthetic_native_root(tmp_path)
    with tempfile.TemporaryDirectory(
        prefix="tomorrowstar-existing-worker-", dir="/private/tmp"
    ) as directory:
        worker = Path(directory)
        result = subprocess.run(
            [
                str(native_launch_executable),
                "--config",
                str(root / "portal.json"),
                "--single-job-flow",
                "--worker-root",
                str(worker),
            ],
            capture_output=True,
            text=True,
            timeout=5,
        )
        assert result.returncode == 0, result.stderr
        assert json.loads(result.stdout)["arguments"][-4:] == [
            "--worker-root",
            str(worker),
            *TAKEOVER_FLAGS,
        ]
        assert worker.is_dir()
        assert list(worker.iterdir()) == []


@pytest.mark.parametrize(
    "damage",
    [
        "relative",
        "root",
        "parent",
        "dot",
        "file",
        "symlink",
        "ancestor-symlink",
        "duplicate",
        "missing",
        "equals",
        "empty",
        "double-slash",
        "trailing-slash",
    ],
)
def test_native_single_job_launch_rejects_invalid_worker_root(
    tmp_path, native_launch_executable, damage
):
    root = synthetic_native_root(tmp_path)
    worker = tmp_path / "worker"
    value = str(worker)
    if damage == "relative":
        value = "relative-worker"
    elif damage == "root":
        value = "/"
    elif damage == "parent":
        value = str(tmp_path) + "/../worker"
    elif damage == "dot":
        value = str(tmp_path) + "/./worker"
    elif damage == "double-slash":
        value = str(tmp_path) + "//worker"
    elif damage == "trailing-slash":
        value += "/"
    elif damage == "file":
        worker.write_text("preserved")
    elif damage in {"symlink", "ancestor-symlink"}:
        target = tmp_path / "target"
        target.mkdir()
        worker.symlink_to(target, target_is_directory=True)
        if damage == "ancestor-symlink":
            value += "/nested"
    elif damage == "empty":
        value = ""
    override = ["--worker-root", value]
    if damage == "duplicate":
        override *= 2
    elif damage == "missing":
        override = ["--worker-root"]
    elif damage == "equals":
        override = ["--worker-root=" + value]
    result = subprocess.run(
        [
            str(native_launch_executable),
            "--config",
            str(root / "portal.json"),
            "--single-job-flow",
            *override,
        ],
        capture_output=True,
        text=True,
        timeout=5,
    )
    assert result.returncode == 2
    assert not result.stdout
    if damage == "file":
        assert worker.read_text() == "preserved"
    elif damage not in {"symlink", "ancestor-symlink"}:
        assert not worker.exists()


@pytest.mark.parametrize(
    "mode",
    [
        "--prepare-materials",
        "--automation-lab",
        "--codex-handoff",
        "--synthetic-preparation",
        "--synthetic-flow",
        "--synthetic-browser",
        "--synthetic-mail",
    ],
)
def test_native_other_modes_reject_worker_root(tmp_path, native_launch_executable, mode):
    root = synthetic_native_root(tmp_path)
    worker = tmp_path / "worker"
    arguments = (
        [mode, str(root)]
        if mode.startswith("--synthetic-")
        else ["--config", str(root / "portal.json"), mode]
    )
    result = subprocess.run(
        [str(native_launch_executable), *arguments, "--worker-root", str(worker)],
        capture_output=True,
        text=True,
        timeout=5,
    )
    assert result.returncode == 2
    assert not result.stdout
    assert not worker.exists()


@pytest.mark.parametrize("worker_override", [False, True])
def test_native_single_job_worker_override_preserves_default_worker_as_legacy(
    tmp_path, monkeypatch, worker_override
):
    root = synthetic_native_root(tmp_path)
    support = tmp_path / "Library/Application Support/TomorrowStar"
    previous = support / "single-job-worker"
    previous.mkdir(parents=True)
    (previous / "run.json").write_bytes(b"preserved unknown old worker")
    monkeypatch.setenv("HOME", str(tmp_path))
    module = runpy.run_path(str(Path(__file__).parents[1] / "macos/server.py"))
    namespace = module["main"].__globals__
    observed = {}

    def inspect_server(*args, **kwargs):
        observed.update(kwargs)
        return SimpleNamespace(
            server_port=12345, application_flow_service=object(), worker_service=object()
        )

    monkeypatch.setitem(namespace, "create_server", inspect_server)
    monkeypatch.setitem(namespace, "find_codex_executable", lambda _configured: None)
    monkeypatch.setitem(namespace, "serve_with_parent_pipe", lambda *args, **kwargs: None)
    arguments = [
        "server.py",
        "--applications",
        str(root / "applications"),
        "--career-workspace",
        str(root / "career"),
        "--single-job-flow",
    ]
    selected = tmp_path / "next-worker" if worker_override else previous
    if worker_override:
        arguments += ["--worker-root", str(selected)]
    monkeypatch.setattr(sys, "argv", arguments)
    assert module["main"]() == 0
    assert observed["worker_root"] == selected
    assert observed["flow_root"] == support / "single-job-flow"
    assert observed["flow_legacy_roots"] == tuple(
        support / name
        for name in (
            "application-worker",
            "application-automation-lab",
            "codex-handoff",
            *(["single-job-worker"] if worker_override else []),
        )
    )
    assert (previous / "run.json").read_bytes() == b"preserved unknown old worker"
    assert not (previous / "answer-library").exists()


def test_native_preparation_launch_uses_explicit_private_root(tmp_path, native_launch_executable):
    root = synthetic_native_root(tmp_path)
    preparation = tmp_path / "separate-preparation"
    config = root / "portal.json"
    workspace = json.loads(config.read_text()) | {"preparation_root": str(preparation)}
    config.write_text(json.dumps(workspace))
    result = subprocess.run(
        [str(native_launch_executable), "--prepare-materials", "--config", str(config)],
        capture_output=True,
        text=True,
        timeout=5,
    )
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["arguments"] == [
        "--applications",
        str(root / "applications"),
        "--career-workspace",
        str(root / "career"),
        "--flow-root",
        str(preparation),
    ]
    assert not preparation.exists()


@pytest.mark.parametrize("value", ["relative", "", "/", "/private/../tmp/run", None, 42])
def test_native_preparation_rejects_malformed_private_root(
    tmp_path, native_launch_executable, value
):
    root = synthetic_native_root(tmp_path)
    config = root / "portal.json"
    config.write_text(json.dumps(json.loads(config.read_text()) | {"preparation_root": value}))
    result = subprocess.run(
        [str(native_launch_executable), "--prepare-materials", "--config", str(config)],
        capture_output=True,
        text=True,
        timeout=5,
    )
    assert result.returncode == 2
    assert not result.stdout


@pytest.mark.parametrize("damage", ["missing", "dangling-link", "unreadable", "unreadable-parent"])
def test_native_only_missing_configuration_allows_folder_selection(
    tmp_path, native_launch_executable, damage
):
    root = synthetic_native_root(tmp_path)
    config = root / "portal.json"
    if damage == "unreadable":
        config.chmod(0)
    elif damage == "unreadable-parent":
        root.chmod(0)
    else:
        config.unlink()
        if damage == "dangling-link":
            config.symlink_to(root / "missing.json")
    try:
        result = subprocess.run(
            [str(native_launch_executable), "--config", str(config)],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if damage == "missing":
            assert result.returncode == 0
            assert result.stdout.strip() == "choose-folders"
        else:
            assert result.returncode == 2
            assert not result.stdout
    finally:
        if damage == "unreadable":
            config.chmod(0o600)
        elif damage == "unreadable-parent":
            root.chmod(0o700)
    if damage == "dangling-link":
        assert config.is_symlink()
        assert not (root / "missing.json").exists()


def test_native_changing_folders_preserves_private_preparation_root(
    tmp_path, native_launch_executable
):
    root = synthetic_native_root(tmp_path)
    config = root / "portal.json"
    preparation = tmp_path / "separate-preparation"
    config.write_text(
        json.dumps(json.loads(config.read_text()) | {"preparation_root": str(preparation)})
    )
    result = subprocess.run(
        [str(native_launch_executable), "--prepare-materials", "--config", str(config)],
        capture_output=True,
        text=True,
        timeout=5,
        env=os.environ | {"TOMORROWSTAR_TEST_CHANGE_FOLDERS": "1"},
    )
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["arguments"] == [
        "--applications",
        "/changed/applications",
        "--career-workspace",
        "/changed/career",
        "--flow-root",
        str(preparation),
    ]


@pytest.mark.parametrize(
    "mode",
    [
        "--single-job-flow",
        "--automation-lab",
        "--codex-handoff",
        "--synthetic-flow",
        "--synthetic-preparation",
        "--synthetic-browser",
    ],
)
def test_native_private_preparation_root_does_not_change_other_modes(
    tmp_path, native_launch_executable, mode
):
    root = synthetic_native_root(tmp_path)
    config = root / "portal.json"
    preparation = tmp_path / "separate-preparation"
    config.write_text(
        json.dumps(json.loads(config.read_text()) | {"preparation_root": str(preparation)})
    )
    arguments = (
        [mode, str(root)] if mode.startswith("--synthetic-") else ["--config", str(config), mode]
    )
    result = subprocess.run(
        [str(native_launch_executable), *arguments],
        capture_output=True,
        text=True,
        timeout=5,
    )
    assert result.returncode == 0, result.stderr
    forwarded = json.loads(result.stdout)["arguments"]
    assert "--flow-root" not in forwarded
    assert str(preparation) not in forwarded
    assert not preparation.exists()


@pytest.mark.parametrize("damage", ["root-link", "ancestor-link", "file"])
def test_native_preparation_rejects_linked_or_non_directory_root(
    tmp_path, native_launch_executable, damage
):
    root = synthetic_native_root(tmp_path)
    preparation = tmp_path / "preparation"
    if damage == "file":
        preparation.write_text("preserve")
    else:
        target = tmp_path / "target"
        target.mkdir()
        preparation.symlink_to(target, target_is_directory=True)
        if damage == "ancestor-link":
            preparation = preparation / "child"
    config = root / "portal.json"
    config.write_text(
        json.dumps(json.loads(config.read_text()) | {"preparation_root": str(preparation)})
    )
    result = subprocess.run(
        [str(native_launch_executable), "--prepare-materials", "--config", str(config)],
        capture_output=True,
        text=True,
        timeout=5,
    )
    assert result.returncode == 2
    assert not result.stdout
    if damage == "file":
        assert preparation.read_text() == "preserve"


@pytest.mark.parametrize(
    "damage",
    [
        "missing",
        "relative",
        "config-override",
        "old-mode",
        "root-link",
        "config-link",
        "bad-paths",
        "equals-spelling",
    ],
)
@pytest.mark.parametrize("mode", ["--synthetic-flow", "--synthetic-mail"])
def test_native_synthetic_launch_never_falls_back_to_normal_configuration(
    tmp_path, native_launch_executable, damage, mode
):
    root = synthetic_native_root(tmp_path)
    config = root / "portal.json"
    config.write_text(
        json.dumps(json.loads(config.read_text()) | {"preparation_root": str(root / "latex-base")})
    )
    arguments = [mode, str(root)]
    if damage == "missing":
        arguments.pop()
    elif damage == "relative":
        arguments[1] = root.name
    elif damage == "config-override":
        arguments.extend(["--config", str(root / "portal.json")])
    elif damage == "old-mode":
        arguments.append("--automation-lab")
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
        arguments = [mode + "=" + str(root), "--config", str(root / "portal.json")]
    result = subprocess.run(
        [str(native_launch_executable), *arguments], capture_output=True, text=True, timeout=5
    )
    assert result.returncode == 2
    assert not result.stdout


def test_native_explicit_invalid_cli_keeps_data_runtime_without_model_fallback(tmp_path):
    root = synthetic_native_root(tmp_path)
    result = subprocess.run(
        [
            sys.executable,
            str(Path(__file__).parents[1] / "macos/server.py"),
            "--applications",
            str(root / "applications"),
            "--career-workspace",
            str(root / "career"),
            "--codex-executable",
            str(root / "missing-cli"),
        ],
        input="",
        capture_output=True,
        text=True,
        timeout=5,
        env=os.environ | {"HOME": str(tmp_path)},
    )
    assert result.returncode == 0, result.stderr
    ready = json.loads(result.stdout)
    assert ready["status"] == "ready"
    assert ready["capabilities"] == {
        "codex": False,
        "flow": True,
        "worker": False,
        "synthetic": False,
    }
    assert result.stderr == ""
    support = tmp_path / "Library/Application Support/TomorrowStar"
    assert (support / "material-preparation").is_dir()
    assert not (support / "single-job-worker").exists()


@pytest.mark.parametrize(
    "label",
    [
        None,
        "Inbox/Processed",
        "  exact raw label  ",
        "--label",
        "",
        12,
        ["bad"],
        pytest.param("bad\0label", id="nul"),
        pytest.param("x" * 262_144, id="overlong"),
    ],
)
def test_native_mail_setting_remains_local_and_preserves_launch_value(
    tmp_path, native_launch_executable, label
):
    root = synthetic_native_root(tmp_path)
    config = root / "portal.json"
    data = json.loads(config.read_text())
    data["application_processed_label"] = label
    config.write_text(json.dumps(data))
    arguments = [str(native_launch_executable), "--config", str(config)]
    result = subprocess.run(arguments, capture_output=True, text=True, timeout=5)
    assert result.returncode == 0
    forwarded = [
        arg
        for arg in json.loads(result.stdout)["arguments"]
        if arg.startswith("--application-processed-label=")
    ]
    expected = label if isinstance(label, str) else ""
    if "\0" in expected or len(expected.encode()) > 65_536:
        expected = ""
    assert json.loads(config.read_text())["application_processed_label"] == label
    assert forwarded == ([] if label is None else ["--application-processed-label=" + expected])


@pytest.mark.parametrize("label", [" exact raw label ", ""])
def test_native_mail_settings_save_and_reopen_without_replacing_folders(
    tmp_path, native_launch_executable, label
):
    root = synthetic_native_root(tmp_path)
    config = root / "portal.json"
    data = json.loads(config.read_text())
    data["preparation_root"] = str(root / "preparation")
    data["cover_letter_template"] = str(root / "private-letter.tex")
    data["application_processed_label"] = "previous"
    config.write_text(json.dumps(data))
    arguments = [str(native_launch_executable), "--config", str(config)]
    saved = subprocess.run(
        arguments,
        env=os.environ
        | {
            "TOMORROWSTAR_TEST_MAIL_LABEL": label,
            "TOMORROWSTAR_TEST_CHANGE_FOLDERS": "1",
        },
        capture_output=True,
        text=True,
        timeout=5,
    )
    assert saved.returncode == 0
    value = json.loads(saved.stdout)
    template_index = value["arguments"].index("--cover-letter-template")
    assert value["arguments"][template_index + 1] == data["cover_letter_template"]
    assert value["canSaveMail"] is True
    assert value["pipeline"] is True
    assert value["nativeReceipts"] is True
    reopened = subprocess.run(arguments, capture_output=True, text=True, timeout=5)
    assert reopened.returncode == 0
    assert json.loads(saved.stdout)["arguments"] == json.loads(reopened.stdout)["arguments"]
    saved_data = json.loads(config.read_text())
    assert saved_data["applications"] == data["applications"]
    assert saved_data["career_workspace"] == data["career_workspace"]
    assert saved_data["preparation_root"] == data["preparation_root"]
    assert saved_data.get("application_processed_label") == (label or None)
    assert stat.S_IMODE(config.stat().st_mode) == 0o600


@pytest.mark.parametrize("label", [None, "  exact raw label  ", "", "--label"])
def test_native_server_forwards_optional_mail_setting(tmp_path, monkeypatch, label):
    root = synthetic_native_root(tmp_path)
    monkeypatch.setenv("HOME", str(tmp_path))
    module = runpy.run_path(str(Path(__file__).parents[1] / "macos/server.py"))
    namespace = module["main"].__globals__
    observed = {}

    def inspect_server(*args, **kwargs):
        observed.update(kwargs)
        return SimpleNamespace(
            server_port=12345, application_flow_service=object(), worker_service=object()
        )

    monkeypatch.setitem(namespace, "create_server", inspect_server)
    monkeypatch.setitem(namespace, "find_codex_executable", lambda _configured: None)
    monkeypatch.setitem(namespace, "serve_with_parent_pipe", lambda *args, **kwargs: None)
    arguments = [
        "server.py",
        "--applications",
        str(root / "applications"),
        "--career-workspace",
        str(root / "career"),
        "--single-job-flow",
    ]
    if label is not None:
        arguments.append("--application-processed-label=" + label)
    monkeypatch.setattr(sys, "argv", arguments)
    assert module["main"]() == 0
    assert observed["application_processed_label"] == label


def test_native_server_passes_synthetic_settings_and_mutates_nothing_after_create(
    tmp_path, monkeypatch
):
    import ast
    import types

    source = Path(__file__).parents[1] / "macos/server.py"
    main = next(
        node
        for node in ast.parse(source.read_text()).body
        if isinstance(node, ast.FunctionDef) and node.name == "main"
    )

    def base_name(node):
        while isinstance(node, (ast.Attribute, ast.Subscript)):
            node = node.value
        return node.id if isinstance(node, ast.Name) else None

    writes = [
        target
        for node in ast.walk(main)
        if isinstance(node, (ast.Assign, ast.AugAssign, ast.AnnAssign))
        for target in (node.targets if isinstance(node, ast.Assign) else [node.target])
        if isinstance(target, (ast.Attribute, ast.Subscript)) and base_name(target) == "server"
    ]
    assert writes == []

    class Frozen(SimpleNamespace):
        def __setattr__(self, name, value):
            raise AssertionError("server.py changed the server after create_server")

    root = synthetic_native_root(tmp_path)
    module = runpy.run_path(str(source))
    namespace = module["main"].__globals__
    observed = {}

    def inspect_server(*args, **kwargs):
        observed.update(kwargs)
        resumes = Frozen()
        flow = Frozen(callbacks=types.MappingProxyType({}))
        return Frozen(
            server_port=12345,
            application_flow_service=flow,
            application_resume_store=resumes,
            worker_service=object(),
        )

    monkeypatch.setitem(namespace, "create_server", inspect_server)
    monkeypatch.setitem(namespace, "serve_with_parent_pipe", lambda *args, **kwargs: None)
    monkeypatch.setattr(sys, "argv", ["server.py", "--synthetic-flow", str(root)])
    saved = dict(os.environ)
    try:
        assert module["main"]() == 0
    finally:
        os.environ.clear()
        os.environ.update(saved)
    assert observed["resume_model_mode"] == "synthetic"
    assert observed["flow_automatic_latex_base"] is None


TAKEOVER_FLAGS = ["--automatic-takeover", "--takeover-executor=codex"]


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        pytest.param("absent", TAKEOVER_FLAGS, id="default-on"),
        pytest.param(True, TAKEOVER_FLAGS, id="on"),
        pytest.param(False, [], id="off"),
        pytest.param("yes", [], id="unreadable-off"),
    ],
)
def test_native_automatic_takeover_setting_controls_backend_flags(
    tmp_path, native_launch_executable, value, expected
):
    # MC-22: on by default in the single-job flow; off or unreadable passes nothing.
    root = synthetic_native_root(tmp_path)
    config = root / "portal.json"
    data = json.loads(config.read_text())
    if value != "absent":
        data["automatic_takeover"] = value
    config.write_text(json.dumps(data))
    result = subprocess.run(
        [str(native_launch_executable), "--config", str(config)],
        capture_output=True,
        text=True,
        timeout=5,
    )
    assert result.returncode == 0, result.stderr
    arguments = json.loads(result.stdout)["arguments"]
    assert [arg for arg in arguments if arg.startswith("--") and "takeover" in arg] == expected


def test_native_automatic_takeover_saves_without_replacing_other_settings(
    tmp_path, native_launch_executable
):
    root = synthetic_native_root(tmp_path)
    config = root / "portal.json"
    data = json.loads(config.read_text())
    data["application_processed_label"] = "Processed"
    config.write_text(json.dumps(data))
    result = subprocess.run(
        [str(native_launch_executable), "--config", str(config)],
        env=os.environ | {"TOMORROWSTAR_TEST_TAKEOVER": "off"},
        capture_output=True,
        text=True,
        timeout=5,
    )
    assert result.returncode == 0, result.stderr
    saved = json.loads(config.read_text())
    assert saved["automatic_takeover"] is False and saved["takeover_executor"] == "codex"
    assert saved["application_processed_label"] == "Processed"
    assert saved["applications"] == data["applications"]
    assert not [
        a for a in json.loads(result.stdout)["arguments"] if a.startswith("--") and "takeover" in a
    ]


def test_synthetic_modes_never_pass_automatic_takeover(tmp_path, native_launch_executable):
    root = synthetic_native_root(tmp_path)
    result = subprocess.run(
        [str(native_launch_executable), "--synthetic-flow", str(root)],
        capture_output=True,
        text=True,
        timeout=5,
    )
    assert not [
        a for a in json.loads(result.stdout)["arguments"] if a.startswith("--") and "takeover" in a
    ]
