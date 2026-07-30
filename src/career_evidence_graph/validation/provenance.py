"""Fail-closed validation for upstream provenance declarations."""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import ValidationError

from .models import ProvenanceRegistry


class ProvenanceValidationError(RuntimeError):
    """Raised when machine or human provenance records are incomplete."""


def load_provenance_registry(path: Path) -> ProvenanceRegistry:
    """Load a strict machine-readable provenance registry."""
    try:
        payload = json.loads(Path(path).resolve(strict=True).read_text(encoding="utf-8"))
        return ProvenanceRegistry.model_validate(payload)
    except (OSError, json.JSONDecodeError, ValidationError) as exc:
        raise ProvenanceValidationError("invalid provenance registry") from exc


def verify_provenance_registry(
    registry_path: Path,
    readme_path: Path,
    project_root: Path,
) -> ProvenanceRegistry:
    """Verify registry contracts, covering tests, and README synchronization."""
    registry = load_provenance_registry(Path(registry_path))
    try:
        readme = Path(readme_path).resolve(strict=True).read_text(encoding="utf-8")
    except OSError as exc:
        raise ProvenanceValidationError("cannot read human provenance matrix") from exc

    root = Path(project_root).resolve()
    tests_root = (root / "tests").resolve()
    for record in registry.records:
        required_human_tokens = (
            record.record_id,
            record.classification,
            record.pinned_commit,
            record.local_subsystem or record.local_destination or "documentation-only",
        )
        if any(token not in readme for token in required_human_tokens):
            raise ProvenanceValidationError(
                f"README is not synchronized for provenance record {record.record_id}"
            )
        if record.covering_test:
            test_path = (root / record.covering_test).resolve()
            if not test_path.is_relative_to(tests_root) or not test_path.is_file():
                raise ProvenanceValidationError(
                    f"covering test is missing or outside tests/: {record.covering_test}"
                )
    return registry
