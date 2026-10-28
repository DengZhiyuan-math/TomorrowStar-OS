"""The portal may request only a current-host check through its own native WebView."""

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest


@pytest.fixture(scope="module")
def native_check_request(tmp_path_factory):
    compiler = shutil.which("swiftc")
    if sys.platform != "darwin" or compiler is None:
        pytest.skip("Native portal request validation requires macOS Swift")
    source = (Path(__file__).parents[1] / "macos/App.swift").read_text()
    start = source.find("struct NativeHostCheckRequest {")
    assert start >= 0, "The source-scoped native permission check bridge is missing"
    code = source[start : source.index("struct BackgroundCheckLaunch {")]
    directory = tmp_path_factory.mktemp("native-web-check")
    harness = directory / "check.swift"
    harness.write_text(
        "import Foundation\n"
        + code
        + """
let requestData = Data(CommandLine.arguments[1].utf8)
let request = try JSONSerialization.jsonObject(with: requestData) as! [String: Any]
let permitted = NativeHostCheckRequest.allows(
    body: request["body"] as Any, mainFrame: request["main_frame"] as! Bool,
    sameWebView: request["same_webview"] as! Bool,
    origin: URLComponents(string: request["origin"] as! String)!,
    currentURL: (request["current_url"] as? String).flatMap(URL.init(string:)),
    backendURL: (request["backend_url"] as? String).flatMap(URL.init(string:)))
print(permitted ? "allowed" : "refused")
"""
    )
    executable = directory / "check"
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

    def run(**changes):
        request = {
            "body": {"action": "check-current-host"},
            "main_frame": True,
            "same_webview": True,
            "origin": "http://127.0.0.1:41001",
            "current_url": "http://127.0.0.1:41001/#flow",
            "backend_url": "http://127.0.0.1:41001/#flow",
        }
        request.update(changes)
        result = subprocess.run(
            [str(executable), json.dumps(request)],
            capture_output=True,
            text=True,
            timeout=5,
            check=True,
        )
        return result.stdout.strip()

    return run


def test_current_portal_can_request_a_fixed_non_prompting_host_check(native_check_request):
    assert native_check_request() == "allowed"


@pytest.mark.parametrize(
    "changes",
    [
        {"main_frame": False},
        {"same_webview": False},
        {"body": {"action": "start-worker"}},
        {"body": {"action": "check-current-host", "script": "/private/arbitrary.py"}},
        {"body": "check-current-host"},
        {"body": None},
        {"body": {}},
        {"body": {"action": 1}},
        {"origin": "http://127.0.0.1:41002"},
        {"origin": "https://127.0.0.1:41001"},
        {"origin": "http://localhost:41001"},
        {"origin": "https://employer.invalid:41001"},
        {"current_url": "http://127.0.0.1:41002/#flow"},
        {"current_url": "https://employer.invalid/"},
        {"current_url": "http://user@127.0.0.1:41001/"},
        {"current_url": None},
        {"backend_url": "http://localhost:41001/#flow"},
        {"backend_url": "http://127.0.0.1/#flow"},
        {"backend_url": "http://127.0.0.1:0/#flow"},
        {"backend_url": None},
    ],
)
def test_other_documents_frames_views_and_actions_cannot_request_native_checks(
    native_check_request, changes
):
    assert native_check_request(**changes) == "refused"
