"""The native review opener only accepts a verified loopback editor response."""

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest


@pytest.fixture(scope="module")
def response_reader(tmp_path_factory):
    compiler = shutil.which("swiftc")
    if sys.platform != "darwin" or not compiler:
        pytest.skip("requires macOS Swift")
    root = tmp_path_factory.mktemp("native-prism-response")
    source = (Path(__file__).parents[1] / "macos/App.swift").read_text()
    declarations = source[
        source.index("struct Workspace: Codable") : source.index("final class AppDelegate:")
    ]
    harness = root / "reader.swift"
    harness.write_text(
        "import Foundation\n"
        + declarations
        + "\nlet data = FileHandle.standardInput.readDataToEndOfFile()\n"
        + "if let url = ResumeReviewResponse.editorURL(from: data) {\n"
        + "    print(url.absoluteString)\n} else { exit(2) }\n"
    )
    binary = root / "reader"
    subprocess.run(
        [compiler, "-module-cache-path", str(root / "cache"), str(harness), "-o", str(binary)],
        capture_output=True,
        check=True,
        text=True,
        timeout=60,
    )
    return binary


def test_native_review_opens_only_the_ready_local_editor(response_reader):
    result = subprocess.run(
        [str(response_reader)],
        input=json.dumps({"status": "ready", "url": "http://127.0.0.1:52000/"}),
        capture_output=True,
        text=True,
        timeout=5,
    )
    assert result.returncode == 0
    assert result.stdout.strip() == "http://127.0.0.1:52000/"


@pytest.mark.parametrize(
    "response",
    [
        {"status": "error", "url": "http://127.0.0.1:52000/"},
        {"status": "ready", "url": "https://example.com/"},
        {"status": "ready", "url": "http://example.com:52000/"},
        {"status": "ready", "url": "http://127.0.0.1/"},
        {"status": "ready", "url": "http://user@127.0.0.1:52000/"},
        {"status": "ready", "url": "http://127.0.0.1:52000/other"},
        {"status": "ready", "url": "http://127.0.0.1:52000/?secret=wrong"},
        {"status": "ready", "url": "file:///private/tmp/main.tex"},
        {"status": "ready", "url": "javascript:alert(1)"},
        {"status": "ready", "url": "http://127.0.0.1:52000/", "padding": "x" * 9000},
    ],
)
def test_native_review_refuses_nonlocal_or_unverified_navigation(response_reader, response):
    result = subprocess.run(
        [str(response_reader)],
        input=json.dumps(response),
        capture_output=True,
        text=True,
        timeout=5,
    )
    assert result.returncode == 2 and result.stdout == ""
