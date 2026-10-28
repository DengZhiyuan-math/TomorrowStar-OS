"""Stable main-App signing policy; these tests never create or sign an App."""

import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest


def signing_module():
    spec = importlib.util.spec_from_file_location(
        "macos_code_signing", Path(__file__).parents[1] / "macos/code_signing.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_missing_signing_config_fails_closed_without_creating_it(tmp_path):
    signing = signing_module()
    config = tmp_path / "absent/signing.json"
    with pytest.raises(ValueError, match="stable signing configuration"):
        signing.load_policy(config)
    assert not config.parent.exists()


def policy_config(tmp_path, signing):
    import json

    config = tmp_path / "signing.json"
    config.write_text(
        json.dumps(
            {
                "identity_sha1": "A" * 40,
                "designated_requirement": (
                    'identifier "dev.tomorrowstar.desktop" and '
                    'certificate leaf = H"' + "A" * 40 + '"'
                ),
                "installed_app": str(Path.home() / "Applications/TomorrowStar.app"),
            }
        )
    )
    return config


@pytest.mark.parametrize(
    "field,value",
    [
        ("identity_sha1", "TomorrowStar"),
        ("designated_requirement", 'identifier "dev.tomorrowstar.desktop"'),
        ("installed_app", "/Applications/Other.app"),
    ],
)
def test_policy_rejects_identity_or_requirement_drift(tmp_path, field, value):
    import json

    signing = signing_module()
    config = policy_config(tmp_path, signing)
    record = json.loads(config.read_text())
    record[field] = value
    config.write_text(json.dumps(record))
    with pytest.raises(ValueError):
        signing.load_policy(config)


def test_identity_override_cannot_silently_migrate_certificate(tmp_path):
    signing = signing_module()
    config = policy_config(tmp_path, signing)
    assert signing.load_policy(config, "a" * 40).identity_sha1 == "A" * 40
    with pytest.raises(ValueError, match="differs"):
        signing.load_policy(config, "B" * 40)


def test_unavailable_pinned_identity_is_not_replaced_with_ad_hoc(tmp_path, monkeypatch):
    import subprocess

    signing = signing_module()
    policy = signing.load_policy(policy_config(tmp_path, signing))
    calls = []

    def run(command, **kwargs):
        calls.append(command)
        return subprocess.CompletedProcess(
            command, 0, stdout="  1) " + "B" * 40 + ' "Other"\n', stderr=""
        )

    monkeypatch.setattr(signing.subprocess, "run", run)
    with pytest.raises(ValueError, match="unavailable"):
        signing.validate_identity(policy)
    assert all(command[0] != "/usr/bin/codesign" for command in calls)


@pytest.mark.parametrize(
    "actual",
    [
        'identifier "dev.tomorrowstar.desktop"',
        'identifier "dev.tomorrowstar.desktop" and certificate leaf = H"' + "B" * 40 + '"',
        'identifier "DEV.tomorrowstar.desktop" and certificate leaf = H"' + "A" * 40 + '"',
        'identifier "dev.tomorrowstar.desktop" and certificate leaf = H"' + "A" * 40 + '" or true',
    ],
)
def test_valid_signature_with_changed_designated_requirement_is_rejected(
    tmp_path, monkeypatch, actual
):
    import subprocess

    signing = signing_module()
    policy = signing.load_policy(policy_config(tmp_path, signing))

    def run(command, **kwargs):
        return subprocess.CompletedProcess(
            command, 0, stdout="", stderr="designated => " + actual + "\n"
        )

    monkeypatch.setattr(signing.subprocess, "run", run)
    with pytest.raises(ValueError, match="designated requirement differs"):
        signing.verify_app(tmp_path / "synthetic-bundle", policy)


def test_build_rejects_missing_config_before_creating_output(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location(
        "macos_signing_builder", Path(__file__).parents[1] / "macos/build.py"
    )
    builder = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(builder)
    monkeypatch.setattr(builder, "sys", SimpleNamespace(platform="darwin", version_info=(3, 13)))
    monkeypatch.setattr(builder, "platform", SimpleNamespace(machine=lambda: "arm64"))
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    output = tmp_path / "new-parent/TomorrowStar.bundle-candidate"
    with pytest.raises(ValueError, match="stable signing configuration"):
        builder.build(output, tmp_path / "unused-driver")
    assert not output.parent.exists()


def test_main_app_signing_and_verification_bind_pinned_certificate(tmp_path, monkeypatch):
    import subprocess

    signing = signing_module()
    policy = signing.load_policy(policy_config(tmp_path, signing))
    calls = []

    def run(command, **kwargs):
        calls.append(command)
        if "-r-" in command:
            return subprocess.CompletedProcess(
                command,
                0,
                stdout="",
                stderr="designated => " + policy.designated_requirement + "\n",
            )
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    monkeypatch.setattr(signing.subprocess, "run", run)
    app = tmp_path / "synthetic-bundle"
    signing.sign_code(app, policy, app=True)
    signing.verify_app(app, policy)
    assert calls[0] == [
        "/usr/bin/codesign",
        "--force",
        "--sign",
        "A" * 40,
        "--requirements",
        '=designated => identifier "dev.tomorrowstar.desktop" and certificate leaf = H"'
        + "A" * 40
        + '"',
        str(app),
    ]
    assert any(
        "-R" in command and command[command.index("-R") + 1] == "=" + policy.designated_requirement
        for command in calls
    )
    assert all("-" not in command for command in calls)


def test_synthetic_ad_hoc_requires_explicit_opt_in_and_cannot_replace_main(tmp_path, monkeypatch):
    signing = signing_module()
    assert (
        signing.load_policy(tmp_path / "missing", allow_ad_hoc_synthetic=True).identity_sha1 == "-"
    )
    with pytest.raises(ValueError):
        signing.load_policy(tmp_path / "missing", "A" * 40, True)
    spec = importlib.util.spec_from_file_location(
        "macos_synthetic_builder", Path(__file__).parents[1] / "macos/build.py"
    )
    builder = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(builder)
    monkeypatch.setattr(builder, "sys", SimpleNamespace(platform="darwin", version_info=(3, 13)))
    monkeypatch.setattr(builder, "platform", SimpleNamespace(machine=lambda: "arm64"))
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    main = tmp_path / "Applications/TomorrowStar.app"
    with pytest.raises(ValueError, match="outside Applications"):
        builder.build(main, tmp_path / "unused", allow_ad_hoc_synthetic=True)
    assert not main.parent.exists()


@pytest.mark.skipif(not Path("/usr/bin/csreq").exists(), reason="macOS requirement compiler")
def test_native_requirement_text_roundtrip_preserves_certificate_pin(tmp_path, monkeypatch):
    import subprocess

    signing = signing_module()
    policy = signing.load_policy(policy_config(tmp_path, signing))
    # Compile/pretty-print text only. No App, private key, signature or permission is touched.
    rendered = subprocess.run(
        ["/usr/bin/csreq", "-r", "=" + policy.designated_requirement, "-t"],
        check=True,
        capture_output=True,
        text=True,
        timeout=10,
    ).stdout.strip()

    def run(command, **kwargs):
        return subprocess.CompletedProcess(
            command, 0, stdout="", stderr="designated => " + rendered + "\n"
        )

    monkeypatch.setattr(signing.subprocess, "run", run)
    signing.verify_app(tmp_path / "synthetic-bundle", policy)


def test_signing_config_rejects_a_symlink_in_its_parent_path(tmp_path):
    signing = signing_module()
    target = tmp_path / "real"
    target.mkdir()
    policy_config(target, signing)
    alias = tmp_path / "alias"
    alias.symlink_to(target, target_is_directory=True)
    with pytest.raises(ValueError, match="symlink"):
        signing.load_policy(alias / "signing.json")


def test_build_rejects_aliased_output_parent_before_external_commands(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location(
        "macos_aliased_builder", Path(__file__).parents[1] / "macos/build.py"
    )
    builder = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(builder)
    monkeypatch.setattr(builder, "sys", SimpleNamespace(platform="darwin", version_info=(3, 13)))
    monkeypatch.setattr(builder, "platform", SimpleNamespace(machine=lambda: "arm64"))
    target = tmp_path / "real"
    target.mkdir()
    alias = tmp_path / "alias"
    alias.symlink_to(target, target_is_directory=True)

    def unexpected(*args, **kwargs):
        pytest.fail("An aliased output must be rejected before signing or building")

    monkeypatch.setattr(builder.signing, "validate_identity", unexpected)
    with pytest.raises(ValueError, match="symlink"):
        builder.build(
            alias / "new.bundle-candidate", tmp_path / "unused", allow_ad_hoc_synthetic=True
        )
    assert list(target.iterdir()) == []
