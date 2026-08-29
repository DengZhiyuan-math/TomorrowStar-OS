"""Synthetic-only contracts for Phase 7 career-source custody.

These tests deliberately describe the public harness boundary before the custody
implementation exists.  They contain sentinel data only: no real career source,
private-workspace value, or value derived from one may be added here.
"""

from __future__ import annotations

import importlib.util
from copy import deepcopy
from datetime import UTC, datetime
from typing import Any

import pytest

_CAREER_SOURCE_MODULE = "career_evidence_graph.career_sources"


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
    return {
        "schema_version": "career-source-capture/v1",
        "capture_id": capture_id,
        "source_id": "source-synthetic-a",
        "content_hash": "a" * 64,
        "acquired_at": datetime(2001, 2, 3, tzinfo=UTC).isoformat(),
        "method": "synthetic-text",
        "predecessor_capture_id": None,
        "authority": "candidate-only",
    }


def synthetic_recapture() -> dict[str, Any]:
    capture = synthetic_capture(capture_id="capture-synthetic-b")
    capture.update({"content_hash": "b" * 64, "predecessor_capture_id": "capture-synthetic-a"})
    return capture


def synthetic_locator() -> dict[str, Any]:
    return {"kind": "whole-source", "declared_fallback": True}


def synthetic_transformation() -> dict[str, Any]:
    return {
        "schema_version": "career-source-transformation/v1",
        "transformation_id": "transform-synthetic-a",
        "input_capture_id": "capture-synthetic-a",
        "input_hash": "a" * 64,
        "transformer": {
            "identity": "synthetic-transformer",
            "version": "v1",
            "configuration": {"mode": "synthetic"},
        },
        "output_hash": "c" * 64,
        "locator": synthetic_locator(),
        "authority": "candidate-only",
    }


def duplicate_content_sources() -> tuple[dict[str, Any], dict[str, Any]]:
    first = synthetic_capture(capture_id="capture-synthetic-duplicate-a")
    second = synthetic_capture(capture_id="capture-synthetic-duplicate-b")
    second["source_id"] = "source-synthetic-unavailable"
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
