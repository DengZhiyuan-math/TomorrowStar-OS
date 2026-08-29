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
        "schema_version": "career-source-capture/v1",
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
        "schema_version": "career-source-transformation/v1",
        "transformation_id": "transform-synthetic-a",
        "input_capture_id": "capture-synthetic-a",
        "input_hash": input_hash,
        "transformer": {
            "identity": "synthetic-transformer",
            "version": "v1",
            "configuration": {"mode": "synthetic"},
        },
        "output_hash": sha256_digest(b"synthetic-derived-output-sentinel"),
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
