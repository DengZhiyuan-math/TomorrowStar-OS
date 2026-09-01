"""Synthetic safety boundaries for the direct private workspace API."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

import career_evidence_graph.workspace as workspace_module
from career_evidence_graph.workspace import (
    WorkspaceError,
    capture_source,
    declare_sources,
    load_source_universe_snapshot,
    open_private_workspace,
)


def _git_workspace(path: Path) -> Path:
    path.mkdir()
    subprocess.run(["git", "init", "--quiet", str(path)], check=True)
    return path


def _declaration() -> dict[str, object]:
    return {
        "cutoff": "2001-02-03",
        "categories": ["projects"],
        "sources": [
            {
                "source_id": "source-synthetic-a",
                "category": "projects",
                "source_type": "self-reported",
                "availability": "available",
            }
        ],
    }


@pytest.mark.parametrize("target_kind", ("same", "child", "ancestor"))
def test_public_harness_and_its_ancestor_or_child_cannot_be_private_workspace(
    tmp_path: Path, target_kind: str
) -> None:
    ancestor = _git_workspace(tmp_path / "ancestor")
    public = _git_workspace(ancestor / "public-harness")
    if target_kind == "same":
        target = public
    elif target_kind == "child":
        target = public / "child"
        target.mkdir()
    else:
        target = ancestor

    with pytest.raises(WorkspaceError) as rejected:
        open_private_workspace(target, public_root=public)

    assert rejected.value.code == "private-workspace-not-separate"


def test_private_workspace_must_be_a_separate_git_worktree(tmp_path: Path) -> None:
    public = _git_workspace(tmp_path / "public-harness")
    nongit = tmp_path / "not-a-worktree"
    nongit.mkdir()

    with pytest.raises(WorkspaceError) as rejected:
        open_private_workspace(nongit, public_root=public)

    assert rejected.value.code == "private-workspace-not-git"


def test_only_git_worktree_identity_is_queried(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    public = _git_workspace(tmp_path / "public-harness")
    private = _git_workspace(tmp_path / "private-records")
    commands: list[list[str]] = []
    original = workspace_module.subprocess.run

    def record(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        commands.append(command)
        return original(command, **kwargs)

    monkeypatch.setattr(workspace_module.subprocess, "run", record)
    open_private_workspace(private, public_root=public)

    assert commands == [
        ["git", "-C", str(private), "rev-parse", "--show-toplevel"],
        ["git", "-C", str(public), "rev-parse", "--show-toplevel"],
    ]


def test_raw_capture_requires_an_ignored_vault_before_any_raw_write(tmp_path: Path) -> None:
    public = _git_workspace(tmp_path / "public-harness")
    private = _git_workspace(tmp_path / "private-records")
    workspace = open_private_workspace(private, public_root=public)
    declare_sources(workspace, _declaration())

    with pytest.raises(WorkspaceError) as rejected:
        capture_source(
            workspace,
            "source-synthetic-a",
            b"synthetic-raw-body-sentinel",
            captured_at="2001-02-03T04:05:06+00:00",
        )

    assert rejected.value.code == "raw-vault-not-ignored"
    assert not (workspace / ".career-evidence/raw").exists()


def test_symlinked_private_namespace_is_rejected_without_raw_write(tmp_path: Path) -> None:
    public = _git_workspace(tmp_path / "public-harness")
    private = _git_workspace(tmp_path / "private-records")
    workspace = open_private_workspace(private, public_root=public)
    (workspace / ".gitignore").write_text(".career-evidence/raw/\n", encoding="utf-8")
    outside = tmp_path / "outside"
    outside.mkdir()
    (workspace / ".career-evidence").symlink_to(outside, target_is_directory=True)

    with pytest.raises(WorkspaceError) as rejected:
        declare_sources(workspace, _declaration())

    assert rejected.value.code == "private-path-invalid"
    assert not (outside / "raw").exists()


@pytest.mark.parametrize("source_id", ("../synthetic-escape", "/synthetic-escape", "a/b"))
def test_unsafe_source_id_cannot_create_a_private_path(tmp_path: Path, source_id: str) -> None:
    public = _git_workspace(tmp_path / "public-harness")
    private = _git_workspace(tmp_path / "private-records")
    (private / ".gitignore").write_text(".career-evidence/raw/\n", encoding="utf-8")
    workspace = open_private_workspace(private, public_root=public)
    declaration = _declaration()
    source = declaration["sources"][0]
    assert isinstance(source, dict)
    source["source_id"] = source_id

    with pytest.raises(WorkspaceError) as rejected:
        declare_sources(workspace, declaration)

    assert rejected.value.code == "registry-invalid"
    assert not (workspace / ".career-evidence").exists()


def test_errors_are_content_free_for_invalid_raw_input(tmp_path: Path) -> None:
    public = _git_workspace(tmp_path / "public-harness")
    private = _git_workspace(tmp_path / "private-records")
    (private / ".gitignore").write_text(".career-evidence/raw/\n", encoding="utf-8")
    workspace = open_private_workspace(private, public_root=public)
    declare_sources(workspace, _declaration())
    sentinel = b"synthetic-private-content-must-not-appear"

    with pytest.raises(WorkspaceError) as rejected:
        capture_source(
            workspace,
            "source-synthetic-a",
            b"",
            captured_at="2001-02-03T04:05:06+00:00",
        )

    assert str(rejected.value) == "capture-invalid"
    assert sentinel.decode() not in str(rejected.value)


def test_source_snapshot_fails_closed_when_referenced_capture_bytes_drift(
    tmp_path: Path,
) -> None:
    public = _git_workspace(tmp_path / "public-harness")
    private = _git_workspace(tmp_path / "private-records")
    (private / ".gitignore").write_text(".career-evidence/raw/\n", encoding="utf-8")
    workspace = open_private_workspace(private, public_root=public)
    declare_sources(workspace, _declaration())
    capture_source(
        workspace,
        "source-synthetic-a",
        b"synthetic-original",
        captured_at="2001-02-03T04:05:06+00:00",
    )
    registry = workspace / ".career-evidence" / "registry.json"
    digest = json.loads(registry.read_text())["sources"][0]["capture"]["content_hash"]
    raw = workspace / ".career-evidence" / "raw" / digest.removeprefix("sha256:")
    raw.write_bytes(b"synthetic-tampered")

    with pytest.raises(WorkspaceError) as rejected:
        load_source_universe_snapshot(workspace, public_root=public)

    assert rejected.value.code == "capture-integrity-invalid"
