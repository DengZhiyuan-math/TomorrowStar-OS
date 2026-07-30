from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from career_evidence_graph.validation.models import ProvenanceRecord
from career_evidence_graph.validation.provenance import (
    ProvenanceValidationError,
    load_provenance_registry,
    verify_provenance_registry,
)


def test_project_registry_is_strict_complete_and_readme_synchronized():
    registry = verify_provenance_registry(
        registry_path="validation/provenance/registry.json",
        readme_path="references/README.md",
        project_root=".",
    )

    assert len(registry.records) == 3
    assert {record.classification for record in registry.records} == {
        "adapt",
        "inspired-by",
    }


def test_registry_rejects_unknown_fields(tmp_path):
    payload = json.loads(Path("validation/provenance/registry.json").read_text(encoding="utf-8"))
    payload["unreviewed"] = True
    path = tmp_path / "registry.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ProvenanceValidationError, match="invalid provenance registry"):
        load_provenance_registry(path)


def test_reuse_requires_exact_source_destination_and_test():
    with pytest.raises(ValidationError, match="reuse requires exact source"):
        ProvenanceRecord(
            schema_version="provenance-record/v1",
            record_id="invalid-copy",
            classification="reuse",
            repository="https://example.com/upstream",
            pinned_commit="a" * 40,
            spdx_license="MIT",
            attribution="Example contributors",
            rationale="Copied helper.",
            divergence="Changed encoding.",
        )


def test_subsystem_adaptation_does_not_require_line_annotations():
    record = ProvenanceRecord(
        schema_version="provenance-record/v1",
        record_id="valid-adaptation",
        classification="adapt",
        repository="https://example.com/upstream",
        pinned_commit="a" * 40,
        spdx_license="MIT",
        attribution="Example contributors",
        local_subsystem="validation store",
        rationale="Adapt an architectural boundary.",
        divergence="Use immutable storage.",
        covering_test="tests/test_provenance.py",
    )

    assert record.upstream_source_path is None
    assert record.local_destination is None


def test_readme_drift_fails_closed(tmp_path):
    readme = tmp_path / "README.md"
    readme.write_text("out of sync", encoding="utf-8")

    with pytest.raises(ProvenanceValidationError, match="not synchronized"):
        verify_provenance_registry(
            "validation/provenance/registry.json",
            readme,
            ".",
        )
