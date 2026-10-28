"""Explicit native permission checks use fixed launch arguments and actual host identity."""

import json
import plistlib
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from test_macos_permission_readiness import probe as probe


@pytest.fixture(scope="module")
def permission_launch(tmp_path_factory):
    compiler = shutil.which("swiftc")
    if sys.platform != "darwin" or compiler is None:
        pytest.skip("native launch parsing requires macOS Swift")
    source = (Path(__file__).parents[1] / "macos/App.swift").read_text()
    start = source.find("struct BackgroundCheckLaunch {")
    assert start >= 0, "The explicit native diagnostic launch parser is missing"
    code = source[start : source.index("final class BackgroundCheckDelegate:")]
    root = tmp_path_factory.mktemp("native-permission-parser")
    harness = root / "launch.swift"
    harness.write_text(
        "import Foundation\n"
        + code
        + """
guard BackgroundCheckLaunch.requested(in: CommandLine.arguments) else { exit(3) }
do {
    let launch = try BackgroundCheckLaunch(arguments: CommandLine.arguments)
    let resources = URL(fileURLWithPath: "/fixed/Resources")
    let output = URL(fileURLWithPath: "/private/synthetic-diagnostic")
    let result: [String: Any] = ["marker": launch.marker,
        "permission_only": launch.permissionOnly,
        "arguments": launch.backendArguments(resources: resources, root: output)]
    print(String(decoding: try JSONSerialization.data(withJSONObject: result), as: UTF8.self))
} catch { exit(2) }
"""
    )
    executable = root / "launch"
    subprocess.run(
        [compiler, "-module-cache-path", str(root / "cache"), str(harness), "-o", str(executable)],
        check=True,
        capture_output=True,
        timeout=60,
    )
    return executable


@pytest.mark.parametrize("mode", ["--permission-check", "--background-check", "--pdf-export-check"])
def test_native_diagnostic_modes_forward_only_the_fixed_script(permission_launch, mode):
    run = subprocess.run(
        [str(permission_launch), mode, "gui-host-synthetic-1234"],
        capture_output=True,
        text=True,
        timeout=5,
        check=True,
    )
    result = json.loads(run.stdout)
    assert result["permission_only"] is (mode == "--permission-check")
    assert result["marker"] == "gui-host-synthetic-1234"
    script = "pdf_export_check.py" if mode == "--pdf-export-check" else "background_check.py"
    expected = ["-I", "-B", "-u", "/fixed/Resources/" + script]
    if mode == "--permission-check":
        expected.append("--permission-only")
    assert result["arguments"] == expected + ["/private/synthetic-diagnostic"]


@pytest.mark.parametrize(
    "arguments",
    [
        ["--permission-check", "gui-host-synthetic-1234", "/arbitrary/script.py"],
        ["--permission-check", "gui-host-synthetic-1234", "--background-check"],
        ["--permission-check", "../gui-host-escape"],
        ["--permission-check", "gui-host-synthetic-1234\n"],
        ["--permission-check=/private/path"],
        ["--permission-only", "gui-host-synthetic-1234"],
        ["--background-check", "gui-host-synthetic-1234", "--permission-only"],
        ["--pdf-export-check", "gui-host-synthetic-1234", "/arbitrary/script.py"],
        ["--pdf-export-check=/private/path"],
        ["--pdf-export-check", "../gui-host-escape"],
    ],
)
def test_native_diagnostic_modes_reject_extra_scripts_flags_or_invalid_markers(
    permission_launch, arguments
):
    run = subprocess.run([str(permission_launch), *arguments], capture_output=True, timeout=5)
    assert run.returncode == 2 and run.stdout == b""


def test_independent_bundle_is_accepted_only_when_actual_host_and_snapshot_match(probe):
    module, root, _, native, calls = probe
    executable = Path(native["executable"])
    info = executable.parent.parent / "Info.plist"
    values = plistlib.loads(info.read_bytes())
    values["CFBundleIdentifier"] = native["bundle_id"] = "dev.tomorrowstar.permission-candidate"
    info.write_bytes(plistlib.dumps(values))
    (root / "native-tcc.json").write_text(json.dumps(native))

    assert module.run(root, permission_only=True) == 0

    assert json.loads((root / "background-result.json").read_text())["status"] == "passed"
    assert calls == ["daemon", "check_permissions", "close", "stop"]


@pytest.mark.parametrize("mismatch", ["path", "bundle", "executable", "unknown", "boolean"])
def test_permission_check_rejects_unproven_host_identity_before_daemon(
    probe, monkeypatch, mismatch
):
    module, root, _, native, calls = probe
    executable = Path(native["executable"])
    info = executable.parent.parent / "Info.plist"
    if mismatch == "path":
        native["executable"] = "/another/App.app/Contents/MacOS/TomorrowStar"
    elif mismatch in {"bundle", "executable"}:
        values = plistlib.loads(info.read_bytes())
        values["CFBundleIdentifier" if mismatch == "bundle" else "CFBundleExecutable"] = "other"
        info.write_bytes(plistlib.dumps(values))
    elif mismatch == "unknown":

        def unknown(pid):
            raise OSError("Synthetic unavailable process path")

        monkeypatch.setattr(module, "process_executable", unknown, raising=False)
    else:
        native["accessibility"] = 1
    (root / "native-tcc.json").write_text(json.dumps(native))

    assert module.run(root, permission_only=True) == 1

    assert json.loads((root / "background-result.json").read_text())["status"] == "failed"
    assert calls == []
    assert not (root / "synthetic-worker").exists()


def test_permission_check_does_not_accept_numeric_daemon_grants(probe):
    module, root, permissions, _, calls = probe
    permissions["accessibility"] = 1

    assert module.run(root, permission_only=True) == 1

    assert json.loads((root / "background-result.json").read_text())["status"] == "failed"
    assert calls == ["daemon", "check_permissions", "close", "stop"]
