"""The native PDF diagnostic uses only its verified bundle and synthetic input."""

import hashlib
import importlib.util
import json
import os
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest


@pytest.fixture
def diagnostic(tmp_path, monkeypatch):
    source = Path(__file__).parents[1] / "macos/pdf_export_check.py"
    spec = importlib.util.spec_from_file_location("native_pdf_diagnostic", source)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(sys, "path", sys.path.copy())
    resources = tmp_path / "Synthetic.app/Contents/Resources"
    resources.mkdir(parents=True)
    monkeypatch.setattr(module, "__file__", str(resources / "pdf_export_check.py"))
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(sys, "prefix", str(resources / "python"))
    monkeypatch.setattr(sys, "executable", str(resources / "python/bin/python3.13"))
    root = tmp_path / "Library/Application Support/TomorrowStar/diagnostics/gui-host-pdf-test-1234"
    root.mkdir(parents=True, mode=0o700)
    (root / "tmp").mkdir(mode=0o700)
    (root / "background.log").touch(mode=0o600)
    (root / "native-tcc.json").write_text(json.dumps({"pid": 9001}))
    manifest = {"engine_files": {}, "native_helpers": {}}
    for name in ("pdf_export_check.py", "background_check.py", "verify.py"):
        (resources / name).write_text("# synthetic verified helper\n")
        manifest["native_helpers"][name] = hashlib.sha256(
            (resources / name).read_bytes()
        ).hexdigest()
    (resources / "system/src").mkdir(parents=True)
    engine = resources / "system/src/synthetic.py"
    engine.write_text("# synthetic engine\n")
    manifest["engine_files"]["src/synthetic.py"] = hashlib.sha256(engine.read_bytes()).hexdigest()
    (resources / "build-manifest.json").write_text(json.dumps(manifest))
    calls = []

    def identity(package, native):
        assert package == resources and native == {"pid": 9001}
        calls.append("identity")
        return {"native_pid": 9001, "bundle_id": "dev.synthetic", "python_pid": os.getpid()}

    def preflight():
        calls.append("preflight")

    def export(html, pdf):
        calls.append("export")
        assert html.read_text() == module.SYNTHETIC_HTML
        assert sys.path[0] == str(resources / "system/src")
        pdf.write_bytes(b"%PDF-1.7\nSynthetic only\n")
        pdf.chmod(0o600)

    helpers = {
        "background_check.py": SimpleNamespace(verify_native_identity=identity),
        "verify.py": SimpleNamespace(check_chrome_launch_environment=preflight),
    }
    monkeypatch.setattr(module, "load_helper", lambda package, name: helpers[name])
    monkeypatch.setitem(
        sys.modules,
        "career_evidence_graph.application_resume",
        SimpleNamespace(export_pdf=export),
    )
    return module, root, resources, calls, helpers


def test_fixed_synthetic_pdf_and_identity_receipt(diagnostic):
    module, root, resources, calls, _ = diagnostic
    assert module.run(root) == 0
    receipt = json.loads((root / "pdf-export-result.json").read_text())
    assert calls == ["identity", "preflight", "export"]
    assert receipt["status"] == "passed" and receipt["chrome_launch_attempted"] is True
    assert receipt["engine_files_match"] and receipt["native_helpers_match"]
    assert receipt["runtime"] == str(resources / "python/bin/python3.13")
    assert (root / "pdf-export-result.json").stat().st_mode & 0o777 == 0o600


@pytest.mark.parametrize(
    "code", ["macos_chrome_registration_denied", "macos_chrome_registration_unknown"]
)
def test_registration_failure_does_not_start_or_retry_chrome(diagnostic, code):
    module, root, _, calls, helpers = diagnostic

    def deny():
        calls.append("preflight")
        raise RuntimeError(code + ": synthetic")

    helpers["verify.py"].check_chrome_launch_environment = deny
    assert module.run(root) == 1
    receipt = json.loads((root / "pdf-export-result.json").read_text())
    assert receipt["error_code"] == code and receipt["chrome_launch_attempted"] is False
    assert calls == ["identity", "preflight"]


def test_manifest_mismatch_stops_before_identity_or_export(diagnostic):
    module, root, resources, calls, _ = diagnostic
    (resources / "background_check.py").write_text("changed")
    assert module.run(root) == 1
    assert calls == []
    assert json.loads((root / "pdf-export-result.json").read_text())["stage"] == "package_identity"


def test_receipt_cannot_be_overwritten(diagnostic):
    module, root, _, calls, _ = diagnostic
    receipt = root / "pdf-export-result.json"
    receipt.write_text("original receipt")
    assert module.run(root) == 1
    assert receipt.read_text() == "original receipt" and calls == []


def test_symlink_root_is_refused(diagnostic):
    module, root, _, calls, _ = diagnostic
    alias = root.parent / "gui-host-alias-1234"
    alias.symlink_to(root, target_is_directory=True)
    assert module.run(alias) == 1
    assert not (root / "pdf-export-result.json").exists() and calls == []


def test_fixed_helper_is_loaded_from_resources_not_import_path(tmp_path):
    source = Path(__file__).parents[1] / "macos/pdf_export_check.py"
    spec = importlib.util.spec_from_file_location("native_pdf_loader", source)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    (tmp_path / "verify.py").write_text("origin = 'same bundle'\n")
    assert module.load_helper(tmp_path, "verify.py").origin == "same bundle"


def test_native_identity_failure_stops_before_preflight(diagnostic):
    module, root, _, calls, helpers = diagnostic

    def wrong_host(*args):
        calls.append("identity")
        raise AssertionError("synthetic responsibility mismatch")

    helpers["background_check.py"].verify_native_identity = wrong_host
    assert module.run(root) == 1
    assert calls == ["identity"]
    receipt = json.loads((root / "pdf-export-result.json").read_text())
    assert receipt["stage"] == "native_identity" and not receipt["chrome_launch_attempted"]


def test_export_failure_is_recorded_without_retry(diagnostic, monkeypatch):
    module, root, _, calls, _ = diagnostic

    def fail(*args):
        calls.append("export")
        raise RuntimeError("synthetic browser failure")

    monkeypatch.setattr(sys.modules["career_evidence_graph.application_resume"], "export_pdf", fail)
    assert module.run(root) == 1
    assert calls == ["identity", "preflight", "export"]
    receipt = json.loads((root / "pdf-export-result.json").read_text())
    assert receipt["export_attempts"] == 1 and receipt["chrome_launch_attempted"]
    assert receipt["stage"] == "pdf_export" and receipt["status"] == "failed"
