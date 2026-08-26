from __future__ import annotations

import json
import os
import stat
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "validation/fixtures/stoa/v1/known-good.json"
MANIFEST = FIXTURE.with_name("source-manifest.json")


def _tree_snapshot(root: Path) -> dict[Path, tuple[str, int, bytes | str]]:
    """Capture every external entry without following any link."""
    captured: dict[Path, tuple[str, int, bytes | str]] = {}
    for directory, names, files in os.walk(root, followlinks=False):
        parent = Path(directory)
        for name in sorted([*names, *files]):
            path = parent / name
            relative = path.relative_to(root)
            info = path.lstat()
            mode = stat.S_IMODE(info.st_mode)
            if stat.S_ISLNK(info.st_mode):
                captured[relative] = ("link", mode, os.readlink(path))
            elif stat.S_ISDIR(info.st_mode):
                captured[relative] = ("dir", mode, "")
            elif stat.S_ISREG(info.st_mode):
                captured[relative] = ("file", mode, path.read_bytes())
            else:
                captured[relative] = ("other", mode, "")
    return captured


def _public_command(
    environment: dict[str, str], *arguments: str
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["uv", "run", "--locked", "--project", str(ROOT), "career-evidence", *arguments],
        cwd=ROOT,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )


@pytest.mark.phase03_gap_probe
def test_fresh_locked_installed_cli_preserves_audit_root_containment(tmp_path: Path) -> None:
    environment = os.environ.copy()
    environment.pop("PYTHONPATH", None)
    environment["UV_PROJECT_ENVIRONMENT"] = str(tmp_path / "fresh-environment")
    environment["UV_CACHE_DIR"] = str(tmp_path / "uv-cache")

    synchronized = subprocess.run(
        ["uv", "sync", "--locked", "--project", str(ROOT)],
        cwd=ROOT,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )
    assert synchronized.returncode == 0, synchronized.stderr

    implementation = _public_command(environment, "implementation-path")
    assert implementation.returncode == 0, implementation.stderr
    assert (
        Path(json.loads(implementation.stdout)["package_path"]).resolve()
        == (ROOT / "src/career_evidence_graph/cli.py").resolve()
    )

    workspace = tmp_path / "normal-workspace"
    normal = _public_command(
        environment,
        "audit",
        "start",
        "--workspace",
        str(workspace),
        "--fixture",
        str(FIXTURE),
        "--manifest",
        str(MANIFEST),
        "--contribution-id",
        "contrib-stoa-authorization-boundary",
        "--audit-id",
        "audit-installed-normal",
        "--action-id",
        "start-installed-normal",
    )
    assert normal.returncode == 0, normal.stderr
    assert {path.name for path in (workspace / "audits" / "audit-installed-normal").iterdir()} == {
        "accepted-results.json",
        "events.jsonl",
        "snapshot.json",
    }
    assert (workspace / "audits" / ".locks" / "audit-installed-normal.lock").is_file()

    redirected_workspace = tmp_path / "redirected-workspace"
    redirected_workspace.mkdir()
    external = tmp_path / "external"
    external.mkdir()
    (external / "sentinel.txt").write_bytes(b"external bytes must not change")
    nested = external / "nested"
    nested.mkdir()
    (nested / "nested-sentinel.txt").write_bytes(b"nested bytes must not change")
    (redirected_workspace / "audits").symlink_to(external, target_is_directory=True)
    before = _tree_snapshot(external)

    redirected = _public_command(
        environment,
        "audit",
        "start",
        "--workspace",
        str(redirected_workspace),
        "--fixture",
        str(FIXTURE),
        "--manifest",
        str(MANIFEST),
        "--contribution-id",
        "contrib-stoa-authorization-boundary",
        "--audit-id",
        "audit-installed-redirected",
        "--action-id",
        "start-installed-redirected",
    )
    assert redirected.returncode == 2
    assert "audit root is unsafe" in redirected.stderr
    assert _tree_snapshot(external) == before
    assert not (external / ".locks").exists()
    assert not (external / "audit-installed-redirected").exists()
