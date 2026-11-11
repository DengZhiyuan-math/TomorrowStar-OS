"""Main App maintenance preserves ownership, identity and recoverable bytes."""

import importlib.util
import json
import plistlib
import shutil
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

_spec = importlib.util.spec_from_file_location(
    "main_app_operator", Path(__file__).parents[1] / "macos/main_app.py"
)
operator = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(operator)


@pytest.fixture
def setup(tmp_path, monkeypatch):
    home = tmp_path / "home"
    monkeypatch.setattr(Path, "home", lambda: home)
    app = home / "Applications/TomorrowStar.app"
    (app / "Contents").mkdir(parents=True)
    (app / "Contents/Info.plist").write_bytes(
        plistlib.dumps(
            {"CFBundleIdentifier": "dev.tomorrowstar.desktop", "CFBundleExecutable": "TomorrowStar"}
        )
    )
    (app / "Contents/payload").write_bytes(b"original")
    policy = operator.signing.SigningPolicy(
        "A" * 40,
        'identifier "dev.tomorrowstar.desktop" and certificate leaf = H"' + "A" * 40 + '"',
        app,
    )
    root = tmp_path / "private-evidence"
    root.mkdir()
    calls = []
    monkeypatch.setattr(
        operator.signing, "validate_identity", lambda policy: calls.append("identity")
    )
    monkeypatch.setattr(
        operator.signing, "verify_app", lambda app, policy: calls.append(("verify", app))
    )
    monkeypatch.setattr(
        operator.signing,
        "sign_code",
        lambda path, policy, **kwargs: calls.append(("sign", path, kwargs)),
    )
    monkeypatch.setattr(operator, "matching_processes", lambda app: [])
    monkeypatch.setattr(
        operator, "copy_bundle", lambda src, dst: shutil.copytree(src, dst, symlinks=True)
    )
    monkeypatch.setattr(
        operator, "run", lambda argv: subprocess.CompletedProcess(argv, 0, "", "Signature=adhoc\n")
    )
    return SimpleNamespace(app=app, policy=policy, root=root, calls=calls, tmp=tmp_path)


def candidate(setup):
    path = setup.tmp / "private/TomorrowStar.bundle-candidate"
    path.parent.mkdir()
    shutil.copytree(setup.app, path)
    (path / "Contents/payload").write_bytes(b"new")
    return path


def test_check_only_verifies_main_without_copy_sign_or_process_interference(setup):
    before = operator.inventory(setup.app)
    result = operator.maintain("check", setup.policy, setup.root)
    assert result["app_changed"] is False
    assert operator.inventory(setup.app) == before
    assert not (setup.root / "rollback-main.bundle-backup").exists()
    assert setup.calls == ["identity", ("verify", setup.app)]


def test_migration_preserves_original_before_signing_only_outer_app(setup, monkeypatch):
    before = operator.inventory(setup.app)

    def sign(path, policy, **kwargs):
        assert kwargs == {"app": True}
        assert operator.inventory(setup.root / "rollback-main.bundle-backup") == before
        assert json.loads((setup.root / "processes-before.json").read_text()) == []
        (path / "Contents/signature").write_text("pinned")

    monkeypatch.setattr(operator.signing, "sign_code", sign)
    result = operator.maintain("migrate-signature", setup.policy, setup.root)
    assert result["signature_migrated"]
    assert (setup.app / "Contents/payload").read_bytes() == b"original"
    assert operator.inventory(setup.root / "rollback-main.bundle-backup") == before


def test_migration_rejects_another_existing_signed_identity(setup, monkeypatch):
    monkeypatch.setattr(
        operator,
        "run",
        lambda argv: subprocess.CompletedProcess(argv, 0, "", "Authority=Other signer\n"),
    )
    with pytest.raises(ValueError, match="ad-hoc"):
        operator.maintain("migrate-signature", setup.policy, setup.root)
    assert not (setup.root / "rollback-main.bundle-backup").exists()
    assert not any(isinstance(call, tuple) and call[0] == "sign" for call in setup.calls)


@pytest.mark.parametrize("busy_check", [1, 2])
def test_migration_stops_if_main_process_is_active_at_either_boundary(
    setup, monkeypatch, busy_check
):
    before = operator.inventory(setup.app)
    checks = iter([[]] * (busy_check - 1) + [[{"pid": 123}]])
    monkeypatch.setattr(operator, "matching_processes", lambda app: next(checks))
    with pytest.raises(ValueError, match="active"):
        operator.maintain("migrate-signature", setup.policy, setup.root)
    assert operator.inventory(setup.app) == before
    signed = [call for call in setup.calls if isinstance(call, tuple) and call[0] == "sign"]
    assert all(call[1] != setup.app for call in signed)
    assert len(signed) == busy_check - 1


def test_failed_sign_retains_verified_original_and_failure_does_not_launch(setup, monkeypatch):
    before = operator.inventory(setup.app)

    def fail(*args, **kwargs):
        raise subprocess.CalledProcessError(1, "codesign", stderr="key access denied")

    monkeypatch.setattr(operator.signing, "sign_code", fail)
    with pytest.raises(subprocess.CalledProcessError):
        operator.maintain("migrate-signature", setup.policy, setup.root)
    assert operator.inventory(setup.root / "rollback-main.bundle-backup") == before
    assert operator.inventory(setup.app) == before


def test_update_verifies_same_policy_and_keeps_original_outside_applications(setup):
    new = candidate(setup)
    before = operator.inventory(setup.app)
    expected = operator.inventory(new)
    result = operator.maintain("update", setup.policy, setup.root, new)
    assert result["main_app_updated"] and not result["permissions_changed"]
    assert operator.inventory(setup.app) == expected
    assert operator.inventory(setup.root / "rollback-main.bundle-backup") == before
    assert operator.inventory(setup.root / "replaced-main-original.bundle-backup") == before
    assert [p.name for p in setup.app.parent.iterdir()] == ["TomorrowStar.app"]
    assert ("verify", setup.app) in setup.calls and ("verify", new) in setup.calls


def test_update_rejects_candidate_requirement_before_any_copy(setup, monkeypatch):
    new = candidate(setup)

    def verify(app, policy):
        if app == new:
            raise ValueError("requirement mismatch")

    monkeypatch.setattr(operator.signing, "verify_app", verify)
    before = operator.inventory(setup.app)
    with pytest.raises(ValueError, match="mismatch"):
        operator.maintain("update", setup.policy, setup.root, new)
    assert operator.inventory(setup.app) == before
    assert not (setup.root / "rollback-main.bundle-backup").exists()


def test_second_rename_failure_restores_untouched_main(setup, monkeypatch):
    new = candidate(setup)
    before = operator.inventory(setup.app)
    rename = operator.os.rename

    def interrupted(source, target):
        if source.suffix == ".bundle-staging":
            raise OSError("swap interrupted")
        return rename(source, target)

    monkeypatch.setattr(operator.os, "rename", interrupted)
    with pytest.raises(OSError, match="interrupted"):
        operator.maintain("update", setup.policy, setup.root, new)
    assert operator.inventory(setup.app) == before
    assert operator.inventory(setup.root / "rollback-main.bundle-backup") == before


def test_inventory_records_modes_and_links_without_following_them(setup):
    (setup.app / "Contents/payload").chmod(0o640)
    (setup.app / "Contents/link").symlink_to("payload")
    rows = {row["path"]: row for row in operator.inventory(setup.app)}
    assert rows["Contents/payload"]["mode"] == 0o640
    assert rows["Contents/link"]["link"] == "payload"
    assert "sha256" not in rows["Contents/link"]


def test_private_root_rejects_applications_and_existing_directories(setup):
    with pytest.raises(ValueError, match="outside"):
        operator.evidence_root(setup.app.parent / "private", setup.app)
    with pytest.raises(ValueError, match="fresh"):
        operator.evidence_root(setup.root, setup.app)


def test_partial_signature_timeout_changes_only_private_stage(setup, monkeypatch):
    before = operator.inventory(setup.app)

    def partial(path, policy, **kwargs):
        (path / "Contents/payload").write_bytes(b"partially signed")
        raise subprocess.TimeoutExpired("codesign", 60)

    monkeypatch.setattr(operator.signing, "sign_code", partial)
    with pytest.raises(subprocess.TimeoutExpired):
        operator.maintain("migrate-signature", setup.policy, setup.root)
    assert operator.inventory(setup.app) == before
    assert (
        setup.root / "signed-main.bundle-staging/Contents/payload"
    ).read_bytes() == b"partially signed"
    assert operator.inventory(setup.root / "rollback-main.bundle-backup") == before


def test_failed_migration_verification_leaves_installed_bytes_untouched(setup, monkeypatch):
    before = operator.inventory(setup.app)

    def reject(path, policy):
        raise ValueError("stage invalid")

    monkeypatch.setattr(operator.signing, "verify_app", reject)
    with pytest.raises(ValueError, match="stage invalid"):
        operator.maintain("migrate-signature", setup.policy, setup.root)
    assert operator.inventory(setup.app) == before
    assert (setup.root / "signed-main.bundle-staging").is_dir()


@pytest.mark.parametrize("embedded", [False, True])
def test_process_scan_blocks_embedded_ancestor_but_ignores_external_argv_ancestor(
    setup, monkeypatch, embedded
):
    original_scan = operator.matching_processes
    # Restore the real scanner hidden by the fixture's idle stub.
    spec = importlib.util.spec_from_file_location(
        "process_scan_operator", Path(__file__).parents[1] / "macos/main_app.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(
        module,
        "run",
        lambda argv: subprocess.CompletedProcess(
            argv, 0, f"100 90 python {setup.app}/Contents/payload\n90 0 shell\n", ""
        ),
    )
    monkeypatch.setattr(module.os, "getpid", lambda: 100)

    class ProcPath:
        def __call__(self, pid, buffer, size):
            buffer.value = (
                str(setup.app / "Contents/MacOS/TomorrowStar")
                if embedded and pid == 90
                else "/usr/bin/python3"
            ).encode()
            return len(buffer.value)

    monkeypatch.setattr(
        module.ctypes, "CDLL", lambda path: SimpleNamespace(proc_pidpath=ProcPath())
    )
    found = module.matching_processes(setup.app)
    assert [row["pid"] for row in found] == ([90] if embedded else [])
    assert operator.matching_processes == original_scan
