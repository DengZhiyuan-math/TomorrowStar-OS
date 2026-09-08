"""Synthetic contracts for the small private career-source workspace."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from career_evidence_graph.validation.hashing import sha256_digest
from career_evidence_graph.workspace import (
    WorkspaceError,
    capture_source,
    declare_sources,
    load_source_universe_snapshot,
    open_private_workspace,
    record_derived_mapping,
    record_self_report_source_successor,
    workspace_status,
)


def _git_workspace(path: Path) -> Path:
    path.mkdir()
    subprocess.run(["git", "init", "--quiet", str(path)], check=True)
    return path


def _private_workspace(tmp_path: Path) -> Path:
    public = _git_workspace(tmp_path / "public-harness")
    private = _git_workspace(tmp_path / "private-records")
    (private / ".gitignore").write_text(".career-evidence/raw/\n", encoding="utf-8")
    return open_private_workspace(private, public_root=public)


def _declaration() -> dict[str, object]:
    return {
        "cutoff": "2001-02-03",
        "categories": ["projects", "education"],
        "sources": [
            {
                "source_id": "source-synthetic-a",
                "category": "projects",
                "source_type": "self-reported",
                "availability": "available",
            },
            {
                "source_id": "source-synthetic-unavailable",
                "category": "education",
                "source_type": "document",
                "availability": "location-unknown",
                "unavailability_reason": "synthetic-unavailable-sentinel",
            },
        ],
    }


def test_declaration_is_one_small_candidate_only_registry(tmp_path: Path) -> None:
    workspace = _private_workspace(tmp_path)

    declared = declare_sources(workspace, _declaration())

    assert declared == {"authority": "candidate-only", "source_count": 2}
    registry = json.loads((workspace / ".career-evidence/registry.json").read_text())
    assert registry == _declaration()


def test_capture_is_create_only_and_records_hash_and_time_on_source(tmp_path: Path) -> None:
    workspace = _private_workspace(tmp_path)
    declare_sources(workspace, _declaration())
    body = b"synthetic-raw-body-sentinel"

    captured = capture_source(
        workspace,
        "source-synthetic-a",
        body,
        captured_at="2001-02-03T04:05:06+00:00",
    )

    digest = sha256_digest(body)
    assert captured == {"authority": "candidate-only", "captured": True}
    raw = workspace / ".career-evidence/raw" / digest.removeprefix("sha256:")
    assert raw.read_bytes() == body
    registry = json.loads((workspace / ".career-evidence/registry.json").read_text())
    source = registry["sources"][0]
    assert source["capture"] == {"content_hash": digest, "captured_at": "2001-02-03T04:05:06+00:00"}

    with pytest.raises(WorkspaceError) as duplicate:
        capture_source(
            workspace,
            "source-synthetic-a",
            body,
            captured_at="2001-02-03T04:05:07+00:00",
        )
    assert duplicate.value.code == "capture-already-recorded"


def test_derived_mapping_records_only_caller_supplied_lineage(tmp_path: Path) -> None:
    workspace = _private_workspace(tmp_path)
    declare_sources(workspace, _declaration())
    body = b"synthetic-raw-body-sentinel"
    capture_source(workspace, "source-synthetic-a", body, captured_at="2001-02-03T04:05:06+00:00")

    recorded = record_derived_mapping(
        workspace,
        "source-synthetic-a",
        input_hash=sha256_digest(body),
        output_hash=sha256_digest(b"synthetic-derived-output"),
        transformer_identity="synthetic-transformer",
        transformer_version="v1",
        locator="whole-source",
    )

    assert recorded == {"authority": "candidate-only", "derived_mapping_recorded": True}
    registry = json.loads((workspace / ".career-evidence/registry.json").read_text())
    assert registry["sources"][0]["derived"] == {
        "input_hash": sha256_digest(body),
        "locator": "whole-source",
        "output_hash": sha256_digest(b"synthetic-derived-output"),
        "transformer": {"identity": "synthetic-transformer", "version": "v1"},
    }


@pytest.mark.parametrize(
    ("availability", "reason", "valid"),
    [
        ("available", None, True),
        ("available", "synthetic-reason", False),
        ("temporarily-unavailable", "synthetic-reason", True),
        ("permanently-lost", "synthetic-reason", True),
        ("access-restricted", "synthetic-reason", True),
        ("never-created", "synthetic-reason", True),
        ("location-unknown", "synthetic-reason", True),
        ("user-declined", "synthetic-reason", True),
    ],
)
def test_availability_is_a_closed_vocabulary_with_coherent_reason(
    tmp_path: Path, availability: str, reason: str | None, valid: bool
) -> None:
    workspace = _private_workspace(tmp_path)
    declaration = _declaration()
    source = declaration["sources"][0]
    assert isinstance(source, dict)
    source["availability"] = availability
    if reason is not None:
        source["unavailability_reason"] = reason

    if valid:
        declare_sources(workspace, declaration)
    else:
        with pytest.raises(WorkspaceError) as invalid:
            declare_sources(workspace, declaration)
        assert invalid.value.code == "registry-invalid"


def test_raw_capture_may_remain_if_registry_publication_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace = _private_workspace(tmp_path)
    declare_sources(workspace, _declaration())
    body = b"synthetic-orphan-raw"

    def fail_publication(_: Path, __: dict[str, object]) -> None:
        raise WorkspaceError("registry-write-failed")

    monkeypatch.setattr("career_evidence_graph.workspace._write_registry", fail_publication)
    with pytest.raises(WorkspaceError, match="registry-write-failed"):
        capture_source(
            workspace,
            "source-synthetic-a",
            body,
            captured_at="2001-02-03T04:05:06+00:00",
        )

    raw = workspace / ".career-evidence/raw" / sha256_digest(body).removeprefix("sha256:")
    assert raw.exists()


def test_status_never_returns_private_source_labels_or_content(tmp_path: Path) -> None:
    workspace = _private_workspace(tmp_path)
    declare_sources(workspace, _declaration())

    assert workspace_status(workspace) == {
        "authority": "candidate-only",
        "source_count": 2,
        "unavailable_source_count": 1,
    }


def test_source_snapshot_reuses_registry_validation_and_verifies_capture_bytes(
    tmp_path: Path,
) -> None:
    workspace = _private_workspace(tmp_path)
    declare_sources(workspace, _declaration())
    body = b"synthetic-snapshot-body"
    capture_source(
        workspace,
        "source-synthetic-a",
        body,
        captured_at="2001-02-03T04:05:06+00:00",
    )

    snapshot = load_source_universe_snapshot(workspace)

    assert snapshot["authority"] == "candidate-only"
    assert snapshot["registry"]["cutoff"] == "2001-02-03"
    assert snapshot["captures"] == {"source-synthetic-a": body}
    assert snapshot["registry_hash"].startswith("sha256:")

    snapshot["registry"]["cutoff"] = "1999-01-01"
    persisted = json.loads((workspace / ".career-evidence/registry.json").read_text())
    assert persisted["cutoff"] == "2001-02-03"


def test_self_report_successor_preserves_parent_and_binds_its_own_capture(
    tmp_path: Path,
) -> None:
    workspace = _private_workspace(tmp_path)
    declare_sources(workspace, _declaration())
    parent = load_source_universe_snapshot(workspace)
    statement = b"Synthetic first-person statement; scope intentionally deferred."

    successor = record_self_report_source_successor(
        workspace,
        parent_registry_hash=parent["registry_hash"],
        source_id="self-report-synthetic",
        statement=statement,
        captured_at="2001-02-03T04:05:06+00:00",
    )

    assert successor == {
        "authority": "candidate-only",
        "parent_registry_hash": parent["registry_hash"],
        "registry_hash": successor["registry_hash"],
        "source_id": "self-report-synthetic",
    }
    assert successor["registry_hash"] != parent["registry_hash"]
    assert load_source_universe_snapshot(workspace)["registry_hash"] == parent["registry_hash"]
    loaded = load_source_universe_snapshot(workspace, registry_hash=successor["registry_hash"])
    source = loaded["registry"]["sources"][-1]
    assert source == {
        "source_id": "self-report-synthetic",
        "category": "self-reports",
        "source_type": "self-reported",
        "availability": "available",
        "capture": {
            "content_hash": sha256_digest(statement),
            "captured_at": "2001-02-03T04:05:06+00:00",
        },
    }
    assert loaded["captures"]["self-report-synthetic"] == statement

    original = json.loads((workspace / ".career-evidence/registry.json").read_text())
    assert original == _declaration()
