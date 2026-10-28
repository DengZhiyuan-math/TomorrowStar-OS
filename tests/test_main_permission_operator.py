"""The fixed-host diagnostic rejects identity drift and reports missing grants."""

import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest


def load():
    path = Path(__file__).parents[1] / "macos/check_main_permissions.py"
    spec = importlib.util.spec_from_file_location("permission_operator", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("accessibility,screen", [(True, True), (False, True), (True, False)])
def test_fixed_host_probe_reports_grants_without_prompt_or_browser(
    tmp_path, monkeypatch, accessibility, screen
):
    module = load()
    home = tmp_path / "home"
    app = home / "Applications/TomorrowStar.app"
    root = tmp_path / "evidence"
    monkeypatch.setattr(Path, "home", lambda: home)
    monkeypatch.setattr(sys, "argv", ["probe", "--private-root", str(root)])
    monkeypatch.setattr(
        module.operator.signing, "load_policy", lambda: SimpleNamespace(installed_app=app)
    )
    monkeypatch.setattr(module.operator.signing, "validate_identity", lambda policy: None)
    monkeypatch.setattr(module.operator.signing, "verify_app", lambda path, policy: None)
    monkeypatch.setattr(module.operator, "validate_bundle", lambda path: None)
    monkeypatch.setattr(module, "inventory", lambda path: [])
    calls = []

    def run(argv, **kwargs):
        calls.append(argv)
        if argv[0] == "/usr/bin/open":
            assert argv[1:7] == ["-W", "-n", "-g", "-a", str(app), "--args"]
            assert argv[7] == "--permission-check"
            diagnostic = home / "Library/Application Support/TomorrowStar/diagnostics" / argv[8]
            diagnostic.mkdir(parents=True)
            native = {"windows": 0, "active": False}
            receipt = dict(
                mode="permission-only",
                browser_prepare_sent=False,
                permission_prompts=0,
                daemon_closed=True,
                native_and_embedded_permissions_match=True,
                bundle_id="dev.tomorrowstar.desktop",
                native_pid=123,
                python_pid=124,
                daemon_pid=125,
                proxy_pid=126,
                python_responsible_pid=123,
                daemon_responsible_pid=123,
                proxy_responsible_pid=123,
                accessibility=accessibility,
                screen_recording=screen,
            )
            (diagnostic / "native-tcc.json").write_text(json.dumps(native))
            (diagnostic / "background-result.json").write_text(json.dumps(receipt))
            (diagnostic / "background.log").write_text("Synthetic; no browser or real host used.\n")
        return subprocess.CompletedProcess(argv, 1 if argv[0] == "/bin/ps" else 0, b"", b"")

    monkeypatch.setattr(module.subprocess, "run", run)
    assert module.main() == (0 if accessibility and screen else 2)
    summary = json.loads((root / "summary.json").read_text())
    assert summary["accessibility"] is accessibility
    assert summary["screen_recording"] is screen
    assert summary["real_applications_resumed"] is False
    assert len([call for call in calls if call[0] == "/usr/bin/open"]) == 1


def test_identity_failure_prevents_native_launch_and_evidence_creation(tmp_path, monkeypatch):
    module = load()
    root = tmp_path / "must-not-exist"
    monkeypatch.setattr(sys, "argv", ["probe", "--private-root", str(root)])
    monkeypatch.setattr(
        module.operator.signing,
        "load_policy",
        lambda: SimpleNamespace(installed_app=tmp_path / "main"),
    )
    monkeypatch.setattr(module.operator, "validate_bundle", lambda path: None)
    monkeypatch.setattr(module.operator.signing, "validate_identity", lambda policy: None)

    def reject(*args):
        raise ValueError("Pinned requirement mismatch")

    monkeypatch.setattr(module.operator.signing, "verify_app", reject)
    monkeypatch.setattr(
        module.subprocess, "run", lambda *args, **kwargs: pytest.fail("Native launch forbidden")
    )
    with pytest.raises(ValueError, match="Pinned requirement mismatch"):
        module.main()
    assert not root.exists()
