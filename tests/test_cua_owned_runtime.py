"""Candidate admission must precede executing the selected binary."""

import hashlib
import json
from contextlib import contextmanager
from types import SimpleNamespace

import pytest

from career_evidence_graph import cua_driver as module


def test_app_selects_its_verified_bundled_driver_without_environment(tmp_path, monkeypatch):
    resources = tmp_path / "TomorrowStar.app/Contents/Resources"
    binary = resources / "cua-driver/cua-driver"
    binary.parent.mkdir(parents=True)
    binary.write_bytes(b"Synthetic verified bundle helper")
    monkeypatch.delenv("TS_CUA_DRIVER_BINARY", raising=False)
    monkeypatch.setattr(module, "__file__", str(resources / "system/src/pkg/cua_driver.py"))
    monkeypatch.setattr(module.sys, "platform", "darwin")
    monkeypatch.setattr(
        module, "_OWNED_DRIVER_SHA256", hashlib.sha256(binary.read_bytes()).hexdigest()
    )

    def manifest(command, **kwargs):
        assert command == [str(binary), "manifest"]
        return '{"binary_version":"0.35.4"}'

    @contextmanager
    def owned(playwright, root, driver, env, record, origins):
        assert driver == binary and record["permission_mode"] == "bounded"
        yield "original-context", "original-cua"

    monkeypatch.setattr(module.subprocess, "check_output", manifest)
    monkeypatch.setattr(module, "managed_owned_cua_browser", owned)
    with module.managed_cua_browser(None, tmp_path) as result:
        assert result == ("original-context", "original-cua")
    assert "TS_CUA_DRIVER_BINARY" not in module.os.environ


@pytest.mark.parametrize("opt_in", [None, False, True, "1", 1])
def test_mock_keychain_requires_explicit_synthetic_opt_in(tmp_path, monkeypatch, opt_in):
    binary = tmp_path / "verified-helper"
    binary.write_bytes(b"Synthetic verified helper")
    monkeypatch.setenv("TS_CUA_DRIVER_BINARY", str(binary))
    monkeypatch.setenv("CUA_E2E_USE_MOCK_KEYCHAIN", "1")
    monkeypatch.setattr(module.sys, "platform", "darwin")
    monkeypatch.setattr(
        module, "_OWNED_DRIVER_SHA256", hashlib.sha256(binary.read_bytes()).hexdigest()
    )
    expected = "1" if opt_in is True else None

    def manifest(command, **kwargs):
        assert kwargs["env"].get("CUA_E2E_USE_MOCK_KEYCHAIN") == expected
        return '{"binary_version":"0.35.4"}'

    @contextmanager
    def owned(playwright, root, driver, env, record, origins):
        assert env.get("CUA_E2E_USE_MOCK_KEYCHAIN") == expected
        yield "original-context", "original-cua"

    monkeypatch.setattr(module.subprocess, "check_output", manifest)
    monkeypatch.setattr(module, "managed_owned_cua_browser", owned)
    options = {} if opt_in is None else {"synthetic_keychain": opt_in}
    with module.managed_cua_browser(None, tmp_path, **options) as result:
        assert result == ("original-context", "original-cua")
    assert module.os.environ["CUA_E2E_USE_MOCK_KEYCHAIN"] == "1"


@pytest.mark.parametrize("missing", [False, True])
def test_app_never_executes_or_falls_back_from_a_bad_bundled_driver(tmp_path, monkeypatch, missing):
    resources = tmp_path / "TomorrowStar.app/Contents/Resources"
    binary = resources / "cua-driver/cua-driver"
    binary.parent.mkdir(parents=True)
    if not missing:
        binary.write_bytes(b"Unreviewed helper; must not execute")
    monkeypatch.delenv("TS_CUA_DRIVER_BINARY", raising=False)
    monkeypatch.setattr(module, "__file__", str(resources / "system/src/pkg/cua_driver.py"))
    monkeypatch.setattr(module.sys, "platform", "darwin")

    def unexpected(*args, **kwargs):
        pytest.fail("Invalid App helper must not execute or fall back to the external driver")

    monkeypatch.setattr(module.subprocess, "check_output", unexpected)
    monkeypatch.setattr(module.subprocess, "Popen", unexpected)
    with pytest.raises(module.PortalDataError) as error, module.managed_cua_browser(None, tmp_path):
        pytest.fail("Invalid helper entered the runtime")
    assert error.value.code == ("cua_unavailable" if missing else "cua_candidate_unverified")


@pytest.mark.parametrize("symlink", [False, True])
def test_unreviewed_candidate_cannot_execute_or_launch(tmp_path, monkeypatch, symlink):
    binary = tmp_path / "candidate"
    binary.write_bytes(b"Synthetic binary; must never execute")
    if symlink:
        monkeypatch.setattr(
            module, "_OWNED_DRIVER_SHA256", hashlib.sha256(binary.read_bytes()).hexdigest()
        )
        link = tmp_path / "candidate-link"
        link.symlink_to(binary)
        binary = link
    monkeypatch.setenv("TS_CUA_DRIVER_BINARY", str(binary))
    monkeypatch.setattr(module.sys, "platform", "darwin")

    def unexpected(*args, **kwargs):
        pytest.fail("Unreviewed candidate executed a command")

    monkeypatch.setattr(module.subprocess, "check_output", unexpected)
    monkeypatch.setattr(module.subprocess, "Popen", unexpected)
    with pytest.raises(module.PortalDataError) as error, module.managed_cua_browser(None, tmp_path):
        pytest.fail("Unreviewed candidate entered its runtime")
    assert error.value.code == "cua_candidate_unverified"
    record = json.loads((tmp_path / "cua-runtime.json").read_text())
    assert record["admission"] == "candidate_unverified" and record["closed"]
    assert not {"pid", "socket", "profile", "daemon_pid", "session"} & record.keys()


@pytest.mark.parametrize("delay", [2.0, 2.01])
def test_owned_window_ready_at_or_after_deadline_is_refused(tmp_path, monkeypatch, delay):
    """A matching title does not authorize accepting an expired observation."""
    state = {"now": 100.0, "title": "", "queries": []}
    profile = tmp_path / "cua-profiles" / "isolated-synthetic"

    class Client:
        session = "synthetic-owner"
        failed = False

        def call(self, name, arguments, **kwargs):
            assert name == "browser_prepare"
            profile.mkdir()
            (profile / "SingletonLock").symlink_to("synthetic-42")
            (profile / "DevToolsActivePort").write_text("9222\n/devtools/browser/synthetic\n")
            return {
                "action": "launched_isolated_browser",
                "prepared_pid": 42,
                "lifecycle": {"idle_expires_in_seconds": 300},
            }

    @contextmanager
    def client(*args, **kwargs):
        yield Client(), {"source": {"pid": 7}}

    class Anchor:
        def set_content(self, content):
            state["title"] = content.removeprefix("<title>").removesuffix("</title>")

    def app_state(pid, **kwargs):
        assert pid == 42 and kwargs["windows"]
        windows = []
        if state["title"]:
            state["queries"].append(kwargs)
            state["now"] += delay
            windows = [{"window_id": 7, "title": state["title"], "is_on_screen": False}]
        return {"pid": 42, "launch_date": 1, "hidden": True, "active": False, "windows": windows}

    def listeners(command, **kwargs):
        assert command[0] == "lsof"
        return "n127.0.0.1:9222\n"

    browser = SimpleNamespace(contexts=[], new_context=lambda **kwargs: SimpleNamespace())
    playwright = SimpleNamespace(
        chromium=SimpleNamespace(connect_over_cdp=lambda *args, **kwargs: browser)
    )
    monkeypatch.setattr(module, "time", SimpleNamespace(monotonic=lambda: state["now"]))
    monkeypatch.setattr(module, "managed_cua_client", client)
    monkeypatch.setattr(module, "mac_chrome_state", app_state)
    monkeypatch.setattr(module.subprocess, "check_output", listeners)
    monkeypatch.setattr(module.CuaDriver, "new_page", lambda *args: Anchor())
    with (
        pytest.raises(module.PortalDataError) as error,
        module.managed_owned_cua_browser(
            playwright, tmp_path, tmp_path / "unused-driver", {}, {"click_route": "dom_event"}, []
        ),
    ):
        pytest.fail("An expired matching window must not enter the runtime")
    assert error.value.code == "cua_binding_ambiguous"
    assert len(state["queries"]) == 1
    assert 0 < state["queries"][0]["timeout"] <= 2
