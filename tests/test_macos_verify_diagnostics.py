"""Captured verifier failures retain diagnostics without retrying acceptance."""

import importlib.util
import json
import subprocess
from pathlib import Path

import pytest


@pytest.fixture
def verifier():
    path = Path(__file__).parents[1] / "macos/verify.py"
    spec = importlib.util.spec_from_file_location("macos_verify_diagnostics", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize(
    "error,expected",
    [
        (
            subprocess.CalledProcessError(
                1, ["synthetic-python"], output=b"launch pid=123\n", stderr=b"SIGABRT\xff\n"
            ),
            ["Captured stdout:\nlaunch pid=123\n", "Captured stderr:\nSIGABRT\ufffd\n"],
        ),
        (
            subprocess.CalledProcessError(1, ["synthetic-python"], stderr="registration failed"),
            ["Captured stderr:\nregistration failed"],
        ),
        (
            subprocess.TimeoutExpired(
                ["synthetic-python"], 30, output=b"launch started", stderr=b"pending"
            ),
            ["Captured stdout:\nlaunch started", "Captured stderr:\npending"],
        ),
        (subprocess.CalledProcessError(1, ["synthetic-python"]), []),
    ],
)
def test_failure_keeps_captured_streams_and_original_exception(
    verifier, tmp_path, monkeypatch, capsys, error, expected
):
    calls = []

    def fail(app):
        calls.append(app)
        raise error

    monkeypatch.setattr(verifier, "verify", fail)
    report = tmp_path / "acceptance.json"
    with pytest.raises(type(error)) as caught:
        verifier.main(["--app", str(tmp_path), "--report", str(report)])
    assert caught.value is error
    assert getattr(error, "__notes__", []) == expected
    assert calls == [tmp_path.resolve()]
    assert not report.exists()
    assert capsys.readouterr().out == ""


def test_success_keeps_report_and_stdout_contract(verifier, tmp_path, monkeypatch, capsys):
    result = {"personal_data_used": False, "signature": "verified"}
    monkeypatch.setattr(verifier, "verify", lambda app: result)
    report = tmp_path / "acceptance.json"
    verifier.main(["--app", str(tmp_path), "--report", str(report)])
    expected = json.dumps(result, indent=2) + "\n"
    assert report.read_text() == capsys.readouterr().out == expected
