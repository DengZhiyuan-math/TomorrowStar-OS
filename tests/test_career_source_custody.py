"""Synthetic-only contracts for Phase 7 career-source custody.

These tests deliberately describe the public harness boundary before the custody
implementation exists.  They contain sentinel data only: no real career source,
private-workspace value, or value derived from one may be added here.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from career_evidence_graph.domain.models import CareerSourceUniverse
from career_evidence_graph.validation.hashing import sha256_digest

_CAREER_SOURCE_MODULE = "career_evidence_graph.career_sources"
ROOT = Path(__file__).parents[1]
LAUNCHER = ROOT / "scripts/run_career_evidence.py"


def _run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(LAUNCHER), *args],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )


def _git(workspace: Path, *args: str) -> str:
    """Run Git only inside a synthetic temporary workspace."""
    completed = subprocess.run(
        ["git", *args],
        cwd=workspace,
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


def _require_career_sources() -> Any:
    """Keep Wave 0 collectable until the Phase 7 custody seam exists."""
    if importlib.util.find_spec(_CAREER_SOURCE_MODULE) is None:
        pytest.skip("career-source custody implementation is introduced in Plan 07-01")
    return __import__(_CAREER_SOURCE_MODULE, fromlist=["CareerSourceStore"])


def synthetic_source_universe(*, revision_id: str = "revision-synthetic-a") -> dict[str, Any]:
    """Return a source-universe declaration with no capability authority."""
    return {
        "schema_version": "career-source-universe/v1",
        "revision_id": revision_id,
        "career_fact_cutoff": "2001-02-03",
        "categories": (
            {"category_id": "category-projects", "kind": "projects"},
            {"category_id": "category-education", "kind": "education"},
        ),
        "sources": (
            {
                "source_id": "source-synthetic-a",
                "category_id": "category-projects",
                "source_type": "self-reported",
                "availability": "available",
            },
            unavailable_source(),
        ),
        "authority": "candidate-only",
    }


def unavailable_source() -> dict[str, str]:
    return {
        "source_id": "source-synthetic-unavailable",
        "category_id": "category-education",
        "source_type": "document",
        "availability": "location-unknown",
        "explanation": "synthetic-unavailable-sentinel",
    }


def synthetic_capture(*, capture_id: str = "capture-synthetic-a") -> dict[str, Any]:
    source = b"synthetic-raw-body-sentinel"
    return {
        "schema_version": "career-source-capture/v2",
        "capture_id": capture_id,
        "source_id": "source-synthetic-a",
        "content_hash": sha256_digest(source),
        "acquired_at": datetime(2001, 2, 3, tzinfo=UTC).isoformat(),
        "method": "synthetic-text",
        "predecessor_capture_id": None,
        "authority": "candidate-only",
    }


def synthetic_recapture() -> dict[str, Any]:
    capture = synthetic_capture(capture_id="capture-synthetic-b")
    capture.update(
        {
            "content_hash": sha256_digest(b"synthetic-raw-body-sentinel-v2"),
            "predecessor_capture_id": "capture-synthetic-a",
        }
    )
    return capture


def synthetic_locator() -> dict[str, Any]:
    return {"kind": "whole-source", "declared_fallback": True}


def synthetic_transformation() -> dict[str, Any]:
    input_hash = sha256_digest(b"synthetic-raw-body-sentinel")
    return {
        "schema_version": "career-source-transformation/v2",
        "transformation_id": "transform-synthetic-a",
        "input_capture_id": "capture-synthetic-a",
        "input_hash": input_hash,
        "transformer": {
            "identity": "synthetic-transformer",
            "version": "v1",
            "configuration": {"mode": "synthetic"},
        },
        "output_hash": input_hash,
        "locator": synthetic_locator(),
        "authority": "candidate-only",
    }


def duplicate_content_sources() -> tuple[dict[str, Any], dict[str, Any]]:
    first = synthetic_capture(capture_id="capture-synthetic-duplicate-a")
    second = synthetic_capture(capture_id="capture-synthetic-duplicate-b")
    second["source_id"] = "source-synthetic-unavailable"
    content_hash = sha256_digest(b"synthetic-duplicate-body")
    first["content_hash"] = content_hash
    second["content_hash"] = content_hash
    return first, second


def tampered(value: dict[str, Any], field: str, replacement: Any) -> dict[str, Any]:
    target = deepcopy(value)
    target[field] = replacement
    return target


def committed_synthetic_snapshot(tmp_path: Path) -> tuple[Any, str]:
    """Create a committed semantic snapshot with ignored synthetic raw bytes."""
    module = _require_career_sources()
    store = module.CareerSourceStore(tmp_path)
    store.declare(synthetic_source_universe())
    store.capture(synthetic_capture(), b"synthetic-raw-body-sentinel")
    store.transform(synthetic_transformation())
    (tmp_path / ".gitignore").write_text(".career-evidence/raw/\n", encoding="utf-8")
    _git(tmp_path, "init", "--quiet")
    _git(tmp_path, "config", "user.email", "synthetic@example.invalid")
    _git(tmp_path, "config", "user.name", "Synthetic Test")
    _git(tmp_path, "add", ".gitignore", ".career-evidence/sources")
    _git(tmp_path, "commit", "--quiet", "-m", "synthetic custody snapshot")
    return store, _git(tmp_path, "rev-parse", "HEAD")


def test_tracer_synthetic_path_is_candidate_only_and_has_no_assessment_authority(tmp_path) -> None:
    module = _require_career_sources()
    store = module.CareerSourceStore(tmp_path)
    result = store.run_synthetic_tracer(
        declaration=synthetic_source_universe(),
        source_bytes=b"synthetic-raw-body-sentinel",
        transformation=synthetic_transformation(),
    )
    assert result["authority"] == "candidate-only"
    assert result["created_assessment_count"] == 0
    assert result["created_mastery_count"] == 0


def test_declaration_requires_complete_unique_two_level_synthetic_registry(tmp_path) -> None:
    module = _require_career_sources()
    store = module.CareerSourceStore(tmp_path)
    declaration = synthetic_source_universe()
    duplicate = deepcopy(declaration)
    duplicate["sources"] = (*duplicate["sources"], duplicate["sources"][0])
    with pytest.raises(module.CareerSourceError):
        store.declare(duplicate)


def test_declaration_keeps_unavailable_source_visible_without_capability_effect(tmp_path) -> None:
    module = _require_career_sources()
    status = module.CareerSourceStore(tmp_path).declare(synthetic_source_universe())
    assert status["unavailable_source_count"] == 1
    assert status["created_skill_count"] == 0


@pytest.mark.parametrize(
    "mutate",
    (
        lambda declaration: declaration.update({"categories": ()}),
        lambda declaration: declaration.update({"sources": ()}),
        lambda declaration: declaration["sources"][0].update({"category_id": "category-missing"}),
        lambda declaration: declaration.update({"career_fact_cutoff": "not-a-date"}),
        lambda declaration: declaration["sources"][1].update({"availability": "available"}),
    ),
)
def test_declaration_rejects_incomplete_or_invalid_source_universe(mutate) -> None:
    declaration = synthetic_source_universe()
    mutate(declaration)

    with pytest.raises(ValidationError):
        CareerSourceUniverse.model_validate(declaration)


def test_declaration_round_trip_is_canonical_and_new_pre_cutoff_revision_preserves_original(
    tmp_path,
) -> None:
    module = _require_career_sources()
    store = module.CareerSourceStore(tmp_path)
    original = synthetic_source_universe()
    store.declare(original)
    revised = synthetic_source_universe(revision_id="revision-synthetic-b")
    revised["predecessor_revision_id"] = original["revision_id"]
    revised["sources"] = (
        *revised["sources"],
        {
            "source_id": "source-synthetic-later-discovery",
            "category_id": "category-projects",
            "source_type": "document",
            "availability": "available",
        },
    )
    store.declare(revised)

    declarations = tmp_path / ".career-evidence/sources/declarations"
    original_bytes = (declarations / original["revision_id"] / "manifest.json").read_bytes()
    revised_bytes = (declarations / revised["revision_id"] / "manifest.json").read_bytes()
    assert original_bytes == CareerSourceUniverse.model_validate(original).canonical_bytes()
    assert revised_bytes == CareerSourceUniverse.model_validate(revised).canonical_bytes()
    assert original_bytes != revised_bytes
    assert json.loads((declarations / "current.json").read_text()) == json.loads(revised_bytes)


def test_capture_recapture_creates_immutable_predecessor_link(tmp_path) -> None:
    module = _require_career_sources()
    store = module.CareerSourceStore(tmp_path)
    store.declare(synthetic_source_universe())
    first = store.capture(synthetic_capture(), b"synthetic-raw-body-sentinel")
    second = store.capture(synthetic_recapture(), b"synthetic-raw-body-sentinel-v2")
    assert second["predecessor_capture_id"] == first["capture_id"]


@pytest.mark.parametrize(
    "field", ("content_hash", "predecessor_capture_id", "acquired_at", "method")
)
def test_lineage_rejects_tampered_capture_bound_fields(tmp_path, field: str) -> None:
    module = _require_career_sources()
    store = module.CareerSourceStore(tmp_path)
    store.declare(synthetic_source_universe())
    capture = store.capture(synthetic_capture(), b"synthetic-raw-body-sentinel")
    with pytest.raises(module.CareerSourceError):
        store.verify_capture(tampered(capture, field, "tampered-sentinel"))


@pytest.mark.parametrize("field", ("input_hash", "output_hash", "locator", "transformer"))
def test_transform_rejects_tampered_bound_lineage(tmp_path, field: str) -> None:
    module = _require_career_sources()
    store = module.CareerSourceStore(tmp_path)
    store.declare(synthetic_source_universe())
    store.capture(synthetic_capture(), b"synthetic-raw-body-sentinel")
    transform = store.transform(synthetic_transformation())
    with pytest.raises(module.CareerSourceError):
        store.verify_transformation(tampered(transform, field, "tampered-sentinel"))


def test_duplicate_content_retains_logical_source_provenance_without_authority_inflation(
    tmp_path,
) -> None:
    module = _require_career_sources()
    store = module.CareerSourceStore(tmp_path)
    store.declare(synthetic_source_universe())
    first, second = duplicate_content_sources()
    outcome = store.capture_duplicates(first, second, b"synthetic-duplicate-body")
    assert outcome["logical_source_count"] == 2
    assert outcome["created_fact_count"] == 0
    assert outcome["created_confidence_count"] == 0


@pytest.mark.parametrize(
    "field",
    ("capture_id", "source_id", "content_hash", "predecessor_capture_id", "acquired_at", "method"),
)
def test_capture_verification_fails_closed_for_manifest_mutations_and_undeclared_payload(
    tmp_path, field: str
) -> None:
    module = _require_career_sources()
    store = module.CareerSourceStore(tmp_path)
    store.declare(synthetic_source_universe())
    capture = store.capture(synthetic_capture(), b"synthetic-raw-body-sentinel")
    capture_path = tmp_path / ".career-evidence/sources/captures" / capture["capture_id"]
    control = deepcopy(capture)
    replacement = "capture-tampered" if field != "content_hash" else sha256_digest(b"tampered")
    mutated = tampered(capture, field, replacement)
    (capture_path / "manifest.json").write_text(json.dumps(mutated), encoding="utf-8")

    with pytest.raises(module.CareerSourceError):
        store.verify_capture(mutated)

    assert control["capture_id"] == "capture-synthetic-a"


def test_capture_verification_rejects_substituted_raw_bytes_and_preserves_prior_capture(
    tmp_path,
) -> None:
    module = _require_career_sources()
    store = module.CareerSourceStore(tmp_path)
    store.declare(synthetic_source_universe())
    first = store.capture(synthetic_capture(), b"synthetic-raw-body-sentinel")
    second = store.capture(synthetic_recapture(), b"synthetic-raw-body-sentinel-v2")
    raw = tmp_path / ".career-evidence/raw" / first["content_hash"].removeprefix("sha256:")
    raw.write_bytes(b"substituted")

    with pytest.raises(module.CareerSourceError):
        store.verify_capture(first)

    raw = tmp_path / ".career-evidence/raw" / second["content_hash"].removeprefix("sha256:")
    assert raw.read_bytes() == b"synthetic-raw-body-sentinel-v2"


def test_capture_verification_rejects_undeclared_bundle_payload(tmp_path) -> None:
    module = _require_career_sources()
    store = module.CareerSourceStore(tmp_path)
    store.declare(synthetic_source_universe())
    capture = store.capture(synthetic_capture(), b"synthetic-raw-body-sentinel")
    bundle = tmp_path / ".career-evidence/sources/captures" / capture["capture_id"]
    (bundle / "undeclared.json").write_text("{}", encoding="utf-8")

    with pytest.raises(module.CareerSourceError):
        store.verify_capture(capture)


def test_transformation_binds_capture_hash_transformer_and_precise_locator(tmp_path) -> None:
    module = _require_career_sources()
    store = module.CareerSourceStore(tmp_path)
    store.declare(synthetic_source_universe())
    capture = store.capture(synthetic_capture(), b"synthetic-raw-body-sentinel")
    transformation = store.transform(synthetic_transformation())

    for field, replacement in (
        ("input_capture_id", "capture-missing"),
        ("input_hash", sha256_digest(b"substituted")),
        ("transformer", {"identity": "other", "version": "v2", "configuration": {}}),
        ("output_hash", sha256_digest(b"substituted-output")),
        ("locator", {"kind": "page", "page": 0}),
    ):
        with pytest.raises(module.CareerSourceError):
            store.verify_transformation(tampered(transformation, field, replacement))

    store.verify_capture(capture)


def test_duplicate_bytes_share_one_raw_object_without_merging_logical_source_relations(
    tmp_path,
) -> None:
    module = _require_career_sources()
    store = module.CareerSourceStore(tmp_path)
    store.declare(synthetic_source_universe())
    first, second = duplicate_content_sources()
    body = b"synthetic-duplicate-body"
    first["content_hash"] = sha256_digest(body)
    second["content_hash"] = sha256_digest(body)
    outcome = store.capture_duplicates(first, second, body)

    raw_root = tmp_path / ".career-evidence/raw"
    assert [path.name for path in raw_root.iterdir()] == [
        sha256_digest(body).removeprefix("sha256:")
    ]
    assert outcome == {
        "logical_source_count": 2,
        "created_fact_count": 0,
        "created_confidence_count": 0,
    }


def test_tracer_declares_captures_transforms_and_inspects_without_authority(tmp_path: Path) -> None:
    source = b'{"synthetic": "career source"}'
    workspace = str(tmp_path)

    declared = _run(
        "career-source",
        "declare",
        "--workspace",
        workspace,
        "--cutoff",
        "2026-08-01",
        "--category",
        "project",
        "--source-id",
        "source-probe",
        "--availability",
        "available",
    )
    assert declared.returncode == 0, declared.stderr
    assert json.loads(declared.stdout) == {"declared": True, "candidate_only": True}

    captured = _run(
        "career-source",
        "capture",
        "--workspace",
        workspace,
        "--source-id",
        "source-probe",
        "--paste",
        source.decode("utf-8"),
    )
    assert captured.returncode == 0, captured.stderr
    assert json.loads(captured.stdout) == {"captured": True, "candidate_only": True}

    transformed = _run(
        "career-source",
        "transform",
        "--workspace",
        workspace,
        "--source-id",
        "source-probe",
        "--transformation-id",
        "transform-source-probe",
        "--transformer",
        "deterministic-whole-source",
        "--version",
        "v1",
        "--configuration-json",
        "{}",
    )
    assert transformed.returncode == 0, transformed.stderr
    assert json.loads(transformed.stdout) == {"transformed": True, "candidate_only": True}

    inspected = _run("career-source", "inspect", "--workspace", workspace)
    assert inspected.returncode == 0, inspected.stderr
    assert json.loads(inspected.stdout) == {
        "backup_state": "not-configured",
        "candidate_only": True,
        "capture_count": 1,
        "declaration_present": True,
        "source_revision_count": 1,
        "transformation_count": 1,
    }
    assert source.decode("utf-8") not in inspected.stdout

    root = tmp_path / ".career-evidence" / "sources"
    declaration = json.loads((root / "declarations" / "current.json").read_text())
    assert declaration["schema_version"] == "career-source-universe/v1"
    capture = next((root / "captures").iterdir())
    manifest = json.loads((capture / "manifest.json").read_text())
    assert manifest["source_id"] == "source-probe"
    assert manifest["content_hash"] == sha256_digest(source)
    assert (
        tmp_path / ".career-evidence" / "raw" / manifest["content_hash"].removeprefix("sha256:")
    ).read_bytes() == source
    transformation = next((root / "transformations").iterdir())
    transformed_manifest = json.loads((transformation / "manifest.json").read_text())
    assert transformed_manifest["predecessor_capture_id"] == manifest["capture_id"]
    assert transformed_manifest["candidate_only"] is True
    assert not list(tmp_path.glob("**/*assessment*"))


def test_explicit_commit_verifies_committed_snapshot_and_ignored_raw_authentication(
    tmp_path: Path,
) -> None:
    store, commit = committed_synthetic_snapshot(tmp_path)

    result = store.verify(expected_workspace_commit=commit)

    assert result == {
        "candidate_only": True,
        "raw_byte_count": len(b"synthetic-raw-body-sentinel"),
        "semantic_entry_count": 6,
    }
    assert _git(tmp_path, "ls-files", ".career-evidence/raw") == ""


@pytest.mark.parametrize("anchor", ("", "HEAD", "main", "deadbeef", "not-a-commit"))
def test_snapshot_anchor_requires_an_explicit_complete_commit_oid(
    tmp_path: Path, anchor: str
) -> None:
    store, commit = committed_synthetic_snapshot(tmp_path)
    assert len(commit) == 40

    with pytest.raises(_require_career_sources().CareerSourceError) as error:
        store.verify(expected_workspace_commit=anchor)

    assert error.value.code == "career-source-snapshot-anchor-invalid"


def test_snapshot_anchor_rejects_the_full_oid_of_an_annotated_tag(tmp_path: Path) -> None:
    store, _ = committed_synthetic_snapshot(tmp_path)
    _git(tmp_path, "tag", "-a", "synthetic-snapshot", "-m", "synthetic tag")
    tag_oid = _git(tmp_path, "rev-parse", "refs/tags/synthetic-snapshot^{tag}")

    with pytest.raises(_require_career_sources().CareerSourceError) as error:
        store.verify(expected_workspace_commit=tag_oid)

    assert error.value.code == "career-source-snapshot-anchor-invalid"


def test_raw_authentication_rejects_changed_ignored_bytes_without_disclosing_workspace(
    tmp_path: Path,
) -> None:
    store, commit = committed_synthetic_snapshot(tmp_path)
    raw = (
        tmp_path
        / ".career-evidence/raw"
        / synthetic_capture()["content_hash"].removeprefix("sha256:")
    )
    raw.write_bytes(b"synthetic-tampered-raw")

    with pytest.raises(_require_career_sources().CareerSourceError) as error:
        store.verify(expected_workspace_commit=commit)

    assert error.value.code == "career-source-snapshot-invalid"
    assert str(tmp_path) not in str(error.value)


def test_snapshot_inventory_rejects_missing_extra_and_coordinated_semantic_changes(
    tmp_path: Path,
) -> None:
    store, commit = committed_synthetic_snapshot(tmp_path)
    transform = (
        tmp_path
        / ".career-evidence/sources/transformations/transform-synthetic-a/manifest.json"
    )
    transform.unlink()
    with pytest.raises(_require_career_sources().CareerSourceError):
        store.verify(expected_workspace_commit=commit)

    extra_workspace = tmp_path / "extra"
    extra_workspace.mkdir()
    store, commit = committed_synthetic_snapshot(extra_workspace)
    extra = extra_workspace / ".career-evidence/sources/derived-outputs/unexpected.json"
    extra.parent.mkdir(parents=True, exist_ok=True)
    extra.write_text("{}", encoding="utf-8")
    with pytest.raises(_require_career_sources().CareerSourceError):
        store.verify(expected_workspace_commit=commit)


def test_empty_workspace_requires_a_complete_commit_and_proves_every_namespace_empty(
    tmp_path: Path,
) -> None:
    module = _require_career_sources()
    (tmp_path / ".gitignore").write_text(".career-evidence/raw/\n", encoding="utf-8")
    _git(tmp_path, "init", "--quiet")
    _git(tmp_path, "config", "user.email", "synthetic@example.invalid")
    _git(tmp_path, "config", "user.name", "Synthetic Test")
    _git(tmp_path, "add", ".gitignore")
    _git(tmp_path, "commit", "--quiet", "-m", "empty synthetic snapshot")
    commit = _git(tmp_path, "rev-parse", "HEAD")

    assert module.CareerSourceStore(tmp_path).verify(expected_workspace_commit=commit) == {
        "candidate_only": True,
        "raw_byte_count": 0,
        "semantic_entry_count": 0,
    }
    with pytest.raises(module.CareerSourceError):
        module.CareerSourceStore(tmp_path).verify(expected_workspace_commit="HEAD")


def test_expected_zero_transformation_namespace_still_requires_snapshot_anchor(
    tmp_path: Path,
) -> None:
    module = _require_career_sources()
    store = module.CareerSourceStore(tmp_path)
    store.declare(synthetic_source_universe())
    store.capture(synthetic_capture(), b"synthetic-raw-body-sentinel")
    (tmp_path / ".gitignore").write_text(".career-evidence/raw/\n", encoding="utf-8")
    _git(tmp_path, "init", "--quiet")
    _git(tmp_path, "config", "user.email", "synthetic@example.invalid")
    _git(tmp_path, "config", "user.name", "Synthetic Test")
    _git(tmp_path, "add", ".gitignore", ".career-evidence/sources")
    _git(tmp_path, "commit", "--quiet", "-m", "expected zero transformations")
    commit = _git(tmp_path, "rev-parse", "HEAD")

    assert store.verify(expected_workspace_commit=commit)["semantic_entry_count"] == 4
    with pytest.raises(module.CareerSourceError):
        store.verify(expected_workspace_commit=commit[:12])


@pytest.mark.parametrize(
    "pointer", ({"capture_id": "capture-missing"}, {"capture_id": "capture-synthetic-a"})
)
def test_current_capture_pointer_must_match_its_source_and_existing_capture(
    tmp_path: Path, pointer: dict[str, str]
) -> None:
    store, commit = committed_synthetic_snapshot(tmp_path)
    current = tmp_path / ".career-evidence/sources/current-captures/source-synthetic-a.json"
    if pointer["capture_id"] == "capture-synthetic-a":
        current.rename(
            tmp_path / ".career-evidence/sources/current-captures/source-synthetic-unavailable.json"
        )
    else:
        current.write_text(json.dumps(pointer), encoding="utf-8")

    with pytest.raises(_require_career_sources().CareerSourceError):
        store.verify(expected_workspace_commit=commit)


def test_committed_malformed_path_and_pointer_fail_even_when_working_tree_matches(
    tmp_path: Path,
) -> None:
    store, _ = committed_synthetic_snapshot(tmp_path)
    current = tmp_path / ".career-evidence/sources/current-captures/source-synthetic-a.json"
    current.write_text('{"capture_id":"capture-missing"}', encoding="utf-8")
    malformed = tmp_path / ".career-evidence/sources/captures/capture--invalid/manifest.json"
    malformed.parent.mkdir()
    malformed.write_text("{}", encoding="utf-8")
    _git(tmp_path, "add", ".career-evidence/sources")
    _git(tmp_path, "commit", "--quiet", "-m", "malformed synthetic snapshot")

    with pytest.raises(_require_career_sources().CareerSourceError):
        store.verify(expected_workspace_commit=_git(tmp_path, "rev-parse", "HEAD"))


def test_exact_source_id_transform_uses_only_its_current_capture_pointer(tmp_path: Path) -> None:
    """The CLI must never choose a capture by directory ordering."""
    module = _require_career_sources()
    store = module.CareerSourceStore(tmp_path)
    declaration = synthetic_source_universe()
    declaration["sources"] = (
        {
            "source_id": "source-alpha",
            "category_id": "category-projects",
            "source_type": "self-reported",
            "availability": "available",
        },
        {
            "source_id": "source-beta",
            "category_id": "category-projects",
            "source_type": "self-reported",
            "availability": "available",
        },
    )
    store.declare(declaration)
    alpha = synthetic_capture(capture_id="capture-alpha")
    alpha.update(
        {
            "source_id": "source-alpha",
            "content_hash": sha256_digest(b"synthetic-alpha"),
        }
    )
    beta = synthetic_capture(capture_id="capture-beta")
    beta.update(
        {
            "source_id": "source-beta",
            "content_hash": sha256_digest(b"synthetic-beta"),
        }
    )
    store.capture(alpha, b"synthetic-alpha")
    store.capture(beta, b"synthetic-beta")

    transformed = _run(
        "career-source",
        "transform",
        "--workspace",
        str(tmp_path),
        "--source-id",
        "source-alpha",
        "--transformation-id",
        "transform-alpha",
        "--transformer",
        "synthetic-transformer",
        "--version",
        "v1",
        "--configuration-json",
        '{"z": 1, "a": 2}',
    )

    assert transformed.returncode == 0, transformed.stderr
    manifest = json.loads(
        (
            tmp_path
            / ".career-evidence/sources/transformations/transform-alpha/manifest.json"
        ).read_text(encoding="utf-8")
    )
    assert manifest["source_id"] == "source-alpha"
    assert manifest["input_capture_id"] == "capture-alpha"
    assert manifest["input_hash"] == sha256_digest(b"synthetic-alpha")


def test_new_capture_and_transform_keep_immutable_declaration_binding(tmp_path: Path) -> None:
    module = _require_career_sources()
    store = module.CareerSourceStore(tmp_path)
    initial = synthetic_source_universe(revision_id="revision-synthetic-a")
    store.declare(initial)
    capture = store.capture(synthetic_capture(), b"synthetic-raw-body-sentinel")
    revised = synthetic_source_universe(revision_id="revision-synthetic-b")
    revised["predecessor_revision_id"] = "revision-synthetic-a"
    revised["sources"] = (
        {
            "source_id": "source-synthetic-unavailable",
            "category_id": "category-education",
            "source_type": "document",
            "availability": "location-unknown",
            "explanation": "synthetic-unavailable-sentinel",
        },
    )
    store.declare(revised)
    stored = store.current_capture("source-synthetic-a")

    assert capture["declaration_revision_id"] == "revision-synthetic-a"
    assert stored.declaration_revision_id == "revision-synthetic-a"
    store.verify_capture(capture)


def test_legacy_capture_requires_explicit_migration(tmp_path: Path) -> None:
    module = _require_career_sources()
    store = module.CareerSourceStore(tmp_path)
    store.declare(synthetic_source_universe())
    legacy = synthetic_capture()
    legacy["schema_version"] = "career-source-capture/v1"
    bundle = tmp_path / ".career-evidence/sources/captures/capture-synthetic-a"
    bundle.mkdir(parents=True)
    (tmp_path / ".career-evidence/raw").mkdir(parents=True, exist_ok=True)
    raw_path = tmp_path / ".career-evidence/raw" / legacy["content_hash"].removeprefix("sha256:")
    raw_path.write_bytes(b"synthetic-raw-body-sentinel")
    (bundle / "manifest.json").write_text(json.dumps(legacy), encoding="utf-8")

    with pytest.raises(module.CareerSourceError) as error:
        store.verify_capture(legacy)

    assert error.value.code == "career-source-capture-migration-required"
