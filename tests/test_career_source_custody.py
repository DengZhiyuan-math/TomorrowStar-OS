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
    record_captured_source_successor,
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
        ("temporarily-unavailable", None, True),
        ("permanently-lost", None, True),
        ("access-restricted", None, True),
        ("never-created", None, True),
        ("location-unknown", None, True),
        ("user-declined", None, True),
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


@pytest.mark.parametrize("availability", ["available", "location-unknown"])
@pytest.mark.parametrize("reason", [None, "", 1])
def test_explicit_invalid_unavailability_reason_fails_before_publication(
    tmp_path: Path, availability: str, reason: object
) -> None:
    workspace = _private_workspace(tmp_path)
    declaration = _declaration()
    source = declaration["sources"][0]
    assert isinstance(source, dict)
    source.update(availability=availability, unavailability_reason=reason)

    with pytest.raises(WorkspaceError, match="registry-invalid"):
        declare_sources(workspace, declaration)

    assert not (workspace / ".career-evidence/registry.json").exists()


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


def test_document_successors_preserve_parent_bytes_and_source_type(tmp_path: Path) -> None:
    workspace = _private_workspace(tmp_path)
    declare_sources(workspace, _declaration())
    original = (workspace / ".career-evidence/registry.json").read_bytes()
    parent = load_source_universe_snapshot(workspace)
    first = record_captured_source_successor(
        workspace,
        parent_registry_hash=parent["registry_hash"],
        source_id="document-synthetic-one",
        category="documents",
        source_type="document",
        payload=b"synthetic-first-document",
        captured_at="2001-02-03T04:05:06+00:00",
    )
    first_path = (
        workspace
        / ".career-evidence/source-universe-revisions"
        / (first["registry_hash"].removeprefix("sha256:") + ".json")
    )
    first_bytes = first_path.read_bytes()
    second = record_captured_source_successor(
        workspace,
        parent_registry_hash=first["registry_hash"],
        source_id="document-synthetic-two",
        category="documents",
        source_type="audit-record",
        payload=b"synthetic-second-document",
        captured_at="2001-02-03T04:05:07+00:00",
    )
    loaded = load_source_universe_snapshot(workspace, registry_hash=second["registry_hash"])
    assert loaded["registry"]["sources"][-1]["source_type"] == "audit-record"
    assert loaded["captures"]["document-synthetic-two"] == b"synthetic-second-document"
    assert (
        loaded["registry"]["sources"][:-1]
        == load_source_universe_snapshot(workspace, registry_hash=first["registry_hash"])[
            "registry"
        ]["sources"]
    )
    assert (workspace / ".career-evidence/registry.json").read_bytes() == original
    assert first_path.read_bytes() == first_bytes


@pytest.mark.parametrize(
    ("category", "source_type"),
    [("../outside", "document"), ("documents", "invented-type")],
)
def test_invalid_successor_metadata_fails_before_writing_raw(
    tmp_path: Path, category: str, source_type: str
) -> None:
    workspace = _private_workspace(tmp_path)
    declare_sources(workspace, _declaration())
    parent = load_source_universe_snapshot(workspace)
    before = sorted(path.relative_to(workspace) for path in workspace.rglob("*"))
    with pytest.raises(WorkspaceError, match="registry-invalid"):
        record_captured_source_successor(
            workspace,
            parent_registry_hash=parent["registry_hash"],
            source_id="document-synthetic",
            category=category,
            source_type=source_type,
            payload=b"synthetic-invalid-metadata",
            captured_at="2001-02-03T04:05:06+00:00",
        )
    assert sorted(path.relative_to(workspace) for path in workspace.rglob("*")) == before


def test_successor_rejects_corrupt_parent_capture_before_writing(tmp_path: Path) -> None:
    workspace = _private_workspace(tmp_path)
    declare_sources(workspace, _declaration())
    payload = b"synthetic-original-parent"
    capture_source(
        workspace, "source-synthetic-a", payload, captured_at="2001-02-03T04:05:06+00:00"
    )
    parent = load_source_universe_snapshot(workspace)
    raw = workspace / ".career-evidence/raw" / sha256_digest(payload).removeprefix("sha256:")
    raw.write_bytes(b"synthetic-corrupted-parent")
    before = sorted(path.relative_to(workspace) for path in workspace.rglob("*"))
    with pytest.raises(WorkspaceError, match="capture-integrity-invalid"):
        record_captured_source_successor(
            workspace,
            parent_registry_hash=parent["registry_hash"],
            source_id="document-synthetic",
            category="documents",
            source_type="document",
            payload=b"synthetic-new-document",
            captured_at="2001-02-03T04:05:07+00:00",
        )
    assert sorted(path.relative_to(workspace) for path in workspace.rglob("*")) == before


@pytest.mark.parametrize("operation", ("capture", "derived-mapping"))
def test_published_successor_freezes_root_registry_before_any_side_effect(
    tmp_path: Path, operation: str
) -> None:
    workspace = _private_workspace(tmp_path)
    declaration = _declaration()
    declaration["sources"].append(
        {
            "source_id": "source-synthetic-b",
            "category": "projects",
            "source_type": "self-reported",
            "availability": "available",
        }
    )
    declare_sources(workspace, declaration)
    body = b"synthetic-original-capture"
    capture_source(workspace, "source-synthetic-a", body, captured_at="2001-02-03T04:05:06+00:00")
    parent = load_source_universe_snapshot(workspace)
    successor = record_self_report_source_successor(
        workspace,
        parent_registry_hash=parent["registry_hash"],
        source_id="synthetic-new-report",
        statement=b"synthetic-successor-statement",
        captured_at="2001-02-03T04:05:07+00:00",
    )
    successor_before = load_source_universe_snapshot(
        workspace, registry_hash=successor["registry_hash"]
    )
    evidence = workspace / ".career-evidence"
    before = {
        path.relative_to(evidence): path.read_bytes()
        for path in evidence.rglob("*")
        if path.is_file()
    }

    with pytest.raises(WorkspaceError) as rejected:
        if operation == "capture":
            capture_source(
                workspace,
                "source-synthetic-b",
                b"synthetic-later-capture",
                captured_at="2001-02-03T04:05:08+00:00",
            )
        else:
            record_derived_mapping(
                workspace,
                "source-synthetic-a",
                input_hash=sha256_digest(body),
                output_hash=sha256_digest(b"synthetic-derived"),
                transformer_identity="synthetic-transformer",
                transformer_version="v1",
            )

    assert rejected.value.code == "registry-frozen"
    assert load_source_universe_snapshot(workspace) == parent
    assert (
        load_source_universe_snapshot(workspace, registry_hash=successor["registry_hash"])
        == successor_before
    )
    after = {
        path.relative_to(evidence): path.read_bytes()
        for path in evidence.rglob("*")
        if path.is_file()
    }
    assert after == before
