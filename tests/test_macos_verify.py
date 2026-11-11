"""Package verification distinguishes preparation from explicit filling admission."""

import importlib.util
import json
import select
import subprocess
import sys
from http.client import HTTPConnection
from pathlib import Path

import pytest


@pytest.mark.parametrize(
    "arguments,preparation,expected",
    [
        (
            [],
            True,
            {"mode": "material-preparation", "worker_enabled": False, "worker_autostart": False},
        ),
        (
            ["--single-job-flow"],
            False,
            {"mode": "single-job-flow", "worker_enabled": True, "worker_autostart": False},
        ),
    ],
)
def test_verifier_distinguishes_default_preparation_from_explicit_single_job(
    tmp_path, arguments, preparation, expected
):
    checkout = Path(__file__).parents[1]
    spec = importlib.util.spec_from_file_location("macos_verify", checkout / "macos/verify.py")
    verifier = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(verifier)
    applications, career = tmp_path / "applications", tmp_path / "career"
    applications.mkdir()
    career.mkdir()
    subprocess.run(["git", "init", "--quiet", "--template=", str(career)], check=True)
    process = subprocess.Popen(
        [
            sys.executable,
            "-B",
            "-u",
            str(checkout / "macos/server.py"),
            "--applications",
            str(applications),
            "--career-workspace",
            str(career),
            *arguments,
        ],
        cwd="/",
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env={
            "PATH": "/usr/bin:/bin:/usr/sbin:/sbin",
            "HOME": str(tmp_path),
            "TMPDIR": str(tmp_path),
            "LANG": "en_US.UTF-8",
        },
    )
    try:
        assert select.select([process.stdout], [], [], 15)[0], "No synthetic backend readiness"
        ready = json.loads(process.stdout.readline())
        assert ready["status"] == "ready", ready
        from urllib.parse import urlsplit

        address = urlsplit(ready["url"])
        connection = HTTPConnection(address.hostname, address.port, timeout=10)
        try:
            connection.request("GET", "/api/flow/state")
            response = connection.getresponse()
            assert response.status == 200
            flow = json.loads(response.read())
        finally:
            connection.close()
        support = tmp_path / "Library/Application Support/TomorrowStar"
        assert verifier.verify_flow_mode(flow, support, preparation=preparation) == expected
        with pytest.raises(AssertionError):
            verifier.verify_flow_mode(flow, support, preparation=not preparation)
        assert not list(applications.glob("*.md"))
        assert not list(applications.glob("*.json"))
    finally:
        process.stdin.close()
        try:
            assert process.wait(timeout=5) == 0
            assert process.stderr.read() == ""
        finally:
            if process.poll() is None:
                process.kill()
                process.wait(timeout=5)
