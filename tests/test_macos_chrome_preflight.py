"""A denied macOS registration service stops verification before Chrome starts."""

import ctypes
import importlib.util
import sys
from pathlib import Path
from unittest.mock import Mock

import pytest


@pytest.fixture
def verifier():
    path = Path(__file__).parents[1] / "macos/verify.py"
    spec = importlib.util.spec_from_file_location("macos_chrome_preflight", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def native_api(monkeypatch, codes, *, release_code=0, returned_port=47):
    calls = []

    def lookup(bootstrap, service, port):
        calls.append(service)
        code = codes.get(service, 0)
        if code == 0:
            port._obj.value = returned_port
        return code

    library = Mock()
    library.bootstrap_look_up = Mock(side_effect=lookup)
    library.mach_port_deallocate = Mock(return_value=release_code)
    monkeypatch.setattr(ctypes, "CDLL", lambda path: library)

    class Port(ctypes.c_uint):
        @classmethod
        def in_dll(cls, library, name):
            return cls({"bootstrap_port": 3, "mach_task_self_": 7}[name])

    monkeypatch.setattr(ctypes, "c_uint", Port)
    return library, calls


def test_denied_registration_stops_before_verification_subprocess(verifier, monkeypatch, tmp_path):
    service = b"com.apple.coreservices.launchservicesd"
    monkeypatch.setattr(sys, "platform", "darwin")
    library, calls = native_api(monkeypatch, {service: 1100})
    run = Mock(side_effect=AssertionError("No verification subprocess may start"))
    monkeypatch.setattr(verifier.subprocess, "run", run)
    with pytest.raises(RuntimeError, match="macos_chrome_registration_denied"):
        verifier.verify(tmp_path)
    assert service in calls
    run.assert_not_called()
    assert library.mach_port_deallocate.call_count == len(calls) - 1


def test_available_services_release_every_port(verifier, monkeypatch):
    monkeypatch.setattr(sys, "platform", "darwin")
    library, calls = native_api(monkeypatch, {})
    verifier.check_chrome_launch_environment()
    assert calls == [b"com.apple.coreservices.launchservicesd"]
    assert library.mach_port_deallocate.call_count == 1
    library.mach_port_deallocate.assert_called_with(7, 47)


def test_windowserver_denial_does_not_block_preflight(verifier, monkeypatch):
    monkeypatch.setattr(sys, "platform", "darwin")
    library, calls = native_api(monkeypatch, {b"com.apple.windowserver.active": 1100})
    verifier.check_chrome_launch_environment()
    assert calls == [b"com.apple.coreservices.launchservicesd"]
    library.mach_port_deallocate.assert_called_once_with(7, 47)


@pytest.mark.parametrize("code", [1102, 5])
def test_other_lookup_errors_remain_unknown(verifier, monkeypatch, code):
    monkeypatch.setattr(sys, "platform", "darwin")
    library, _ = native_api(monkeypatch, {b"com.apple.coreservices.launchservicesd": code})
    with pytest.raises(RuntimeError, match="macos_chrome_registration_unknown"):
        verifier.check_chrome_launch_environment()
    library.mach_port_deallocate.assert_not_called()


def test_native_api_failure_is_unknown(verifier, monkeypatch):
    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setattr(ctypes, "CDLL", Mock(side_effect=OSError("unavailable")))
    with pytest.raises(RuntimeError, match="macos_chrome_registration_unknown"):
        verifier.check_chrome_launch_environment()


def test_missing_native_symbol_is_unknown(verifier, monkeypatch):
    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setattr(ctypes, "CDLL", lambda path: object())
    with pytest.raises(RuntimeError, match="macos_chrome_registration_unknown"):
        verifier.check_chrome_launch_environment()


def test_success_without_a_port_is_unknown(verifier, monkeypatch):
    monkeypatch.setattr(sys, "platform", "darwin")
    library, _ = native_api(monkeypatch, {}, returned_port=0)
    with pytest.raises(RuntimeError, match="macos_chrome_registration_unknown"):
        verifier.check_chrome_launch_environment()
    library.mach_port_deallocate.assert_not_called()


def test_port_release_failure_stops_as_unknown(verifier, monkeypatch):
    monkeypatch.setattr(sys, "platform", "darwin")
    library, calls = native_api(monkeypatch, {}, release_code=5)
    with pytest.raises(
        RuntimeError, match="macos_chrome_registration_unknown.*port release failed"
    ):
        verifier.check_chrome_launch_environment()
    assert len(calls) == 1
    library.mach_port_deallocate.assert_called_once_with(7, 47)


def test_other_platform_does_not_call_native_api(verifier, monkeypatch):
    monkeypatch.setattr(sys, "platform", "linux")
    loader = Mock(side_effect=AssertionError("macOS API must not be called"))
    monkeypatch.setattr(ctypes, "CDLL", loader)
    verifier.check_chrome_launch_environment()
    loader.assert_not_called()


@pytest.mark.parametrize("packaged", [False, True])
def test_verifier_loads_registration_guard_from_its_own_source_tree(
    verifier, tmp_path, monkeypatch, packaged
):
    resources = tmp_path / ("Resources" if packaged else "macos")
    resources.mkdir()
    core = (
        resources / "system/src/career_evidence_graph/chrome_registration.py"
        if packaged
        else resources.parent / "src/career_evidence_graph/chrome_registration.py"
    )
    core.parent.mkdir(parents=True)
    core.write_text(
        "def check_chrome_launch_environment():\n"
        "    raise RuntimeError('same-tree synthetic guard')\n"
    )
    monkeypatch.setattr(verifier, "__file__", str(resources / "verify.py"))
    with pytest.raises(RuntimeError, match="same-tree synthetic guard"):
        verifier.check_chrome_launch_environment()


def test_verifier_does_not_fall_back_to_editable_checkout(verifier, tmp_path, monkeypatch):
    resources = tmp_path / "Resources"
    resources.mkdir()
    monkeypatch.setattr(verifier, "__file__", str(resources / "verify.py"))
    with pytest.raises(RuntimeError, match="macos_chrome_registration_unknown"):
        verifier.check_chrome_launch_environment()
