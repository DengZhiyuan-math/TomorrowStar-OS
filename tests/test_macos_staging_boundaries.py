"""Packaging and verification never materialize another discoverable .app."""

import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest


class StopBeforeCopy(Exception):
    pass


def load_script(name):
    spec = importlib.util.spec_from_file_location(
        "macos_staging_" + name, Path(__file__).parents[1] / "macos" / (name + ".py")
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_builder_stages_only_unregistered_non_app_bundle(tmp_path, monkeypatch):
    builder = load_script("build")
    monkeypatch.setattr(
        builder,
        "sys",
        SimpleNamespace(
            platform="darwin",
            version_info=(3, 13),
            base_prefix=tmp_path,
        ),
    )
    monkeypatch.setattr(builder, "platform", SimpleNamespace(machine=lambda: "arm64"))
    temporary_directory = builder.tempfile.TemporaryDirectory
    seen = []

    def temporary(*args, **kwargs):
        assert kwargs.get("suffix") == ".noindex"
        return temporary_directory(*args, **kwargs)

    monkeypatch.setattr(builder.tempfile, "TemporaryDirectory", temporary)
    original_mkdir = Path.mkdir

    def mkdir(path, *args, **kwargs):
        # Guard before creating anything, including during the RED test.
        assert not any(part.endswith(".app") for part in path.parts)
        return original_mkdir(path, *args, **kwargs)

    monkeypatch.setattr(Path, "mkdir", mkdir)

    def copy(source, destination, *args, **kwargs):
        seen.append(destination)
        assert not any(part.endswith(".app") for part in destination.parts)
        assert any(part.endswith(".noindex") for part in destination.parts)
        raise StopBeforeCopy

    monkeypatch.setattr(builder.shutil, "copy2", copy)
    with pytest.raises(StopBeforeCopy):
        builder.build(
            tmp_path / "private-output.bundle-candidate",
            tmp_path / "unused-driver",
            allow_ad_hoc_synthetic=True,
        )
    assert len(seen) == 1
    assert not list(tmp_path.rglob("*.app"))


def test_verifier_relocates_only_to_unregistered_non_app_bundle(tmp_path, monkeypatch):
    verifier = load_script("verify")
    monkeypatch.setattr(verifier, "check_chrome_launch_environment", lambda: None)
    monkeypatch.setattr(verifier.subprocess, "run", lambda *args, **kwargs: None)
    temporary_directory = verifier.tempfile.TemporaryDirectory
    seen = []

    def temporary(*args, **kwargs):
        assert kwargs.get("suffix") == ".noindex"
        return temporary_directory(*args, **kwargs)

    monkeypatch.setattr(verifier.tempfile, "TemporaryDirectory", temporary)

    def copy(source, destination, *args, **kwargs):
        seen.append(destination)
        assert not any(part.endswith(".app") for part in destination.parts)
        assert any(part.endswith(".noindex") for part in destination.parts)
        raise StopBeforeCopy

    monkeypatch.setattr(verifier.shutil, "copytree", copy)
    with pytest.raises(StopBeforeCopy):
        verifier.verify(tmp_path / "synthetic-source.bundle-candidate")
    assert len(seen) == 1
    assert not list(tmp_path.rglob("*.app"))


@pytest.mark.parametrize("relative", ["Another.app", "Another.app/private.bundle-candidate"])
def test_even_explicit_synthetic_build_cannot_output_another_app(tmp_path, monkeypatch, relative):
    builder = load_script("build")
    monkeypatch.setattr(builder, "sys", SimpleNamespace(platform="darwin", version_info=(3, 13)))
    monkeypatch.setattr(builder, "platform", SimpleNamespace(machine=lambda: "arm64"))

    def unexpected(*args, **kwargs):
        pytest.fail("A second .app output must be rejected before signing or building")

    monkeypatch.setattr(builder.signing, "validate_identity", unexpected)
    with pytest.raises(ValueError, match="bundle-candidate"):
        builder.build(tmp_path / relative, tmp_path / "unused", allow_ad_hoc_synthetic=True)
    assert not (tmp_path / "Another.app").exists()
