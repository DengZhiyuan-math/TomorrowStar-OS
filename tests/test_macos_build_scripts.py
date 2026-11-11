"""Package entrypoint contract, without compiling, signing or installing an App."""

import hashlib
import importlib.util
from pathlib import Path


def test_bundled_system_contains_execution_and_experience_launchers(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location(
        "macos_build_scripts", Path(__file__).parents[1] / "macos/build.py"
    )
    builder = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(builder)
    source = tmp_path / "checkout"
    scripts = source / "scripts"
    scripts.mkdir(parents=True)
    (scripts / "run_application_worker.py").write_bytes(b"# Synthetic worker launcher\n")
    (scripts / "run_codex_handoff.py").write_bytes(b"# Synthetic Codex handoff launcher\n")
    (scripts / "run_experience_generation.py").write_bytes(b"# Synthetic experience launcher\n")
    monkeypatch.setattr(builder, "ROOT", source)
    system = tmp_path / "bundle-system-fixture"
    builder.copy_engine_scripts(system)
    assert (
        system / "scripts/run_application_worker.py"
    ).read_bytes() == b"# Synthetic worker launcher\n"
    assert (
        system / "scripts/run_codex_handoff.py"
    ).read_bytes() == b"# Synthetic Codex handoff launcher\n"
    assert (
        system / "scripts/run_experience_generation.py"
    ).read_bytes() == b"# Synthetic experience launcher\n"
    assert sorted(path.name for path in (system / "scripts").iterdir()) == [
        "run_application_worker.py",
        "run_codex_handoff.py",
        "run_experience_generation.py",
    ]


def test_native_resource_inventory_copies_and_hashes_the_fixed_review_helper(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location(
        "macos_native_resources", Path(__file__).parents[1] / "macos/build.py"
    )
    builder = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(builder)
    checkout = tmp_path / "checkout"
    macos = checkout / "macos"
    macos.mkdir(parents=True)
    helpers = {
        "server.py",
        "background_check.py",
        "resume_review.py",
        "verify.py",
        "pdf_export_check.py",
    }
    for name in helpers:
        (macos / name).write_text("# Synthetic " + name + "\n")
    (macos / "not-a-bundled-helper.py").write_text("Must not be copied")
    resources = tmp_path / "Resources"
    resources.mkdir()
    monkeypatch.setattr(builder, "ROOT", checkout)
    inventory = builder.copy_native_helpers(resources)
    assert set(inventory) == helpers
    assert sorted(path.name for path in resources.iterdir()) == sorted(inventory)
    for name, sha256 in inventory.items():
        assert (resources / name).read_bytes() == (macos / name).read_bytes()
        assert hashlib.sha256((resources / name).read_bytes()).hexdigest() == sha256
