"""The preparation candidate seals public source bytes without running them."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def module():
    path = ROOT / "scripts/freeze_preparation_candidate.py"
    spec = importlib.util.spec_from_file_location("freeze_preparation_candidate", path)
    loaded = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(loaded)
    return loaded


def source(root: Path) -> Path:
    files = {
        ".python-version": "3.13.14\n",
        "pyproject.toml": '[project]\nrequires-python = ">=3.13,<3.14"\ndependencies = []\n',
        "uv.lock": "version = 1\n",
        "_career_evidence_build.py": "# synthetic backend\n",
        "src/career_evidence_graph/__init__.py": "# synthetic public source\n",
        "scripts/run_pytest.py": "# synthetic verification launcher\n",
        "macos/App.swift": "// synthetic native shell\n",
        "macos/icons/AppIcon.icns": "synthetic icon",
        "docs/question-scoring-pipeline.md": "Synthetic public protocol\n",
        "references/README.md": "Synthetic provenance\n",
        "references/cua-driver-LICENSE.md": "Synthetic license\n",
        "references/cua-driver-synthetic-keychain.patch": "Synthetic reviewed patch\n",
        "references/upstream/example/LICENSE": "Synthetic upstream license\n",
        "tests/test_synthetic.py": "# synthetic test\n",
        "tests/fixtures/synthetic.json": '{"synthetic": true}\n',
        ".scratch/private.json": "private excluded",
        "validation/application-automation/private.json": "private excluded",
        "references/upstream/example/source.py": "upstream excluded",
    }
    for relative, text in files.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
    return root


def test_candidate_copies_working_source_and_is_read_only_verifiable(tmp_path):
    freezer = module()
    root = source(tmp_path / "checkout")
    candidate = tmp_path / "candidate"
    result = freezer.create(root, candidate)
    assert result == freezer.verify(candidate, root)
    manifest = json.loads((candidate / "manifest.json").read_text())
    paths = {item["path"] for item in manifest["files"]}
    assert "src/career_evidence_graph/__init__.py" in paths
    assert "tests/fixtures/synthetic.json" in paths
    assert "references/upstream/example/LICENSE" in paths
    assert all("private" not in item and not item.endswith("source.py") for item in paths)
    before = {
        str(path): (path.stat().st_mtime_ns, path.read_bytes())
        for path in candidate.rglob("*")
        if path.is_file()
    }
    assert freezer.verify(candidate) == result
    assert before == {
        str(path): (path.stat().st_mtime_ns, path.read_bytes())
        for path in candidate.rglob("*")
        if path.is_file()
    }


def test_candidate_id_ignores_location_and_excluded_private_changes(tmp_path):
    freezer = module()
    first = source(tmp_path / "first")
    second = source(tmp_path / "second")
    (second / ".scratch/private.json").write_text("different excluded private content")
    cache = second / "src/career_evidence_graph/__pycache__/module.pyc"
    cache.parent.mkdir()
    cache.write_bytes(b"ignored cache")
    a = freezer.create(first, tmp_path / "a")
    b = freezer.create(second, tmp_path / "b")
    assert a == b
    assert a["scope"]["standalone_full_test_checkout"] is False
    assert a["scope"]["app_built_or_installed"] is False
    assert str(tmp_path) not in json.dumps(a)


def test_source_verification_detects_new_working_source_without_refreshing_candidate(tmp_path):
    freezer = module()
    root = source(tmp_path / "checkout")
    candidate = tmp_path / "candidate"
    frozen = freezer.create(root, candidate)
    before = (candidate / "manifest.json").read_bytes()
    (root / "src/career_evidence_graph/untracked.py").write_text("# new working source\n")
    with pytest.raises(ValueError, match="Current source differs"):
        freezer.verify(candidate, root)
    assert freezer.verify(candidate) == frozen
    assert (candidate / "manifest.json").read_bytes() == before


def test_existing_destination_is_preserved_and_symlink_destination_rejected(tmp_path):
    freezer = module()
    root = source(tmp_path / "checkout")
    existing = tmp_path / "existing"
    existing.mkdir()
    original = existing / "keep.json"
    original.write_text("keep")
    with pytest.raises(ValueError, match="existing paths"):
        freezer.create(root, existing)
    assert original.read_text() == "keep"
    alias = tmp_path / "alias"
    alias.symlink_to(existing, target_is_directory=True)
    with pytest.raises(ValueError, match="Symlinks"):
        freezer.create(root, alias)
    assert original.read_text() == "keep"


def test_candidate_refuses_source_symlink_and_unsafe_destination(tmp_path):
    freezer = module()
    root = source(tmp_path / "checkout")
    (root / "src/career_evidence_graph/linked.py").symlink_to(root / "uv.lock")
    with pytest.raises(ValueError, match="Symlinks"):
        freezer.create(root, tmp_path / "candidate")
    assert not (tmp_path / "candidate").exists()
    with pytest.raises(ValueError, match="outside source input"):
        freezer.create(root, root / "tests/candidate")


def test_source_change_during_copy_does_not_publish_a_partial_candidate(tmp_path, monkeypatch):
    freezer = module()
    root = source(tmp_path / "checkout")
    original = freezer._manifest
    calls = 0

    def change_after_first_snapshot(path):
        nonlocal calls
        result = original(path)
        calls += 1
        if calls == 1:
            (root / "src/career_evidence_graph/__init__.py").write_text("# changed during copy\n")
        return result

    monkeypatch.setattr(freezer, "_manifest", change_after_first_snapshot)
    with pytest.raises(ValueError, match="Source changed"):
        freezer.create(root, tmp_path / "candidate")
    assert not (tmp_path / "candidate").exists()


def test_verify_rejects_changed_bytes_and_unlisted_paths(tmp_path):
    freezer = module()
    root = source(tmp_path / "checkout")
    for damage in ("source", "config", "snapshot", "extra", "empty_directory", "symlink"):
        candidate = tmp_path / damage
        freezer.create(root, candidate)
        if damage == "source":
            (candidate / "payload/src/career_evidence_graph/__init__.py").write_text("changed")
        elif damage == "config":
            (candidate / "payload/uv.lock").write_text("changed")
        elif damage == "snapshot":
            (candidate / "manifest.json").write_text('{"broken": true}')
        elif damage == "extra":
            (candidate / "payload/private.json").write_text("unexpected")
        elif damage == "empty_directory":
            (candidate / "payload/unlisted").mkdir()
        else:
            target = candidate / "payload/src/career_evidence_graph/__init__.py"
            target.unlink()
            target.symlink_to(root / "src/career_evidence_graph/__init__.py")
        with pytest.raises((ValueError, OSError)):
            freezer.verify(candidate)


def test_verify_rejects_manifest_path_escape_duplicate_and_metadata_tamper(tmp_path):
    freezer = module()
    root = source(tmp_path / "checkout")
    for damage in ("escape", "duplicate", "candidate_id", "configuration", "policy", "typed_scope"):
        candidate = tmp_path / damage
        freezer.create(root, candidate)
        manifest_path = candidate / "manifest.json"
        manifest = json.loads(manifest_path.read_text())
        if damage == "escape":
            manifest["files"][0]["path"] = "../outside"
        elif damage == "duplicate":
            manifest["files"].append(manifest["files"][0])
        elif damage == "candidate_id":
            manifest["candidate_id"] = "preparation-candidate-" + "0" * 64
        elif damage == "configuration":
            manifest["configuration"]["python_version"] = "different"
        elif damage == "typed_scope":
            manifest["scope"]["real_applications_authorized"] = 0
        else:
            manifest["policy_version"] = "unconfirmed-policy"
        manifest_path.write_text(json.dumps(manifest))
        with pytest.raises(ValueError):
            freezer.verify(candidate)


def test_top_level_parent_traversal_is_rejected_before_creation_or_verification(tmp_path):
    freezer = module()
    root = source(tmp_path / "checkout")
    candidate = tmp_path / "candidate"
    freezer.create(root, candidate)
    paths = [root / "src/../tests/unwanted", tmp_path / "candidate/../other"]
    for output in paths:
        with pytest.raises(ValueError, match="Parent traversal"):
            freezer.create(root, output)
        assert not output.exists()
    with pytest.raises(ValueError, match="Parent traversal"):
        freezer.create(root / "tests/..", tmp_path / "new")
    with pytest.raises(ValueError, match="Parent traversal"):
        freezer.verify(candidate / "payload/..")
    with pytest.raises(ValueError, match="Parent traversal"):
        freezer.verify(candidate, root / "tests/..")
    assert not (tmp_path / "new").exists()


def test_cli_create_verify_and_failure_preserve_candidate_and_source(tmp_path):
    root = source(tmp_path / "checkout")
    candidate = tmp_path / "candidate"
    command = [sys.executable, str(ROOT / "scripts/freeze_preparation_candidate.py")]
    created = subprocess.run(
        [*command, "create", "--output", str(candidate), "--source-root", str(root)],
        check=True,
        capture_output=True,
        text=True,
    )
    snapshot = (candidate / "manifest.json").read_bytes()
    verified = subprocess.run(
        [*command, "verify", "--candidate", str(candidate), "--source-root", str(root)],
        check=True,
        capture_output=True,
        text=True,
    )
    assert json.loads(created.stdout) == json.loads(verified.stdout)
    assert (candidate / "manifest.json").read_bytes() == snapshot
    original = (root / "src/career_evidence_graph/__init__.py").read_bytes()
    failed = subprocess.run(
        [*command, "create", "--output", str(candidate), "--source-root", str(root)],
        check=False,
        capture_output=True,
        text=True,
    )
    assert failed.returncode == 1
    assert "existing paths" in failed.stderr
    assert (candidate / "manifest.json").read_bytes() == snapshot
    assert (root / "src/career_evidence_graph/__init__.py").read_bytes() == original


def test_duplicate_json_keys_and_non_regular_source_entries_are_rejected(tmp_path):
    freezer = module()
    root = source(tmp_path / "checkout")
    candidate = tmp_path / "candidate"
    freezer.create(root, candidate)
    path = candidate / "manifest.json"
    content = path.read_text().replace('"format":', '"format": "duplicate", "format":', 1)
    path.write_text(content)
    with pytest.raises(ValueError, match="duplicate keys"):
        freezer.verify(candidate)
    unsafe = root / "src/career_evidence_graph/directory.py"
    unsafe.mkdir()
    # A directory within package source is valid. A top-level launcher masquerading
    # as a Python file is not a source file and must not be copied.
    (root / "scripts/directory.py").mkdir()
    with pytest.raises(ValueError, match="regular file"):
        freezer.create(root, tmp_path / "unsafe")
    assert unsafe.is_dir()
