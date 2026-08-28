# Phase 2: Domain Contracts, STOA Fixture, and Deterministic Invariants - Pattern Map

**Mapped:** 2026-07-30  
**Files analyzed:** 14 file paths/groups  
**Analogs found:** 9 / 14

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|---|---|---|---|---|
| `src/career_evidence_graph/domain/__init__.py` | package surface | transform | `src/career_evidence_graph/validation/__init__.py` | exact |
| `src/career_evidence_graph/domain/models.py` | model | transform | `src/career_evidence_graph/validation/models.py` | exact |
| `src/career_evidence_graph/domain/invariants.py` | utility / validator | transform | `src/career_evidence_graph/validation/acceptance.py` | role-match |
| `src/career_evidence_graph/domain/fixtures.py` | service / fixture loader | file-I/O | `src/career_evidence_graph/validation/store.py` | role-match |
| `validation/fixtures/stoa/v1/source-manifest.json` | config / fixture | file-I/O | `validation/provenance/registry.json` | partial |
| `validation/fixtures/stoa/v1/candidates.json` | fixture | transform | `validation/charter/v1.json` | partial |
| `validation/fixtures/stoa/v1/review.json` | fixture | event-driven / transform | formal-run `corrections.json` payload from `FormalRunStore` | role-match |
| `validation/fixtures/stoa/v1/known-good.json` | fixture | file-I/O / transform | formal-run `confirmed_result.json` payload from `FormalRunStore` | role-match |
| `validation/fixtures/stoa/v1/known-bad/*.json` | fixture | transform | `tests/test_security_boundaries.py` negative inputs | role-match |
| `tests/test_domain_models.py` | test | transform | `tests/test_charter.py` | exact |
| `tests/test_domain_invariants.py` | test | transform | `tests/test_security_boundaries.py` | exact |
| `tests/test_stoa_fixture.py` | test | file-I/O | `tests/test_provenance.py` | role-match |
| `tests/test_fixture_mutations.py` | test | transform | `tests/test_security_boundaries.py` | role-match |
| `src/career_evidence_graph/cli.py` (only if a fixture command is necessary) | CLI / controller | request-response | `src/career_evidence_graph/cli.py` | self-extension |

## Pattern Assignments

### `src/career_evidence_graph/domain/models.py` (model, transform)

**Analog:** `src/career_evidence_graph/validation/models.py`

**Strict imports/base model** (lines 3-16):

```python
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictModel(BaseModel):
    """Base model that rejects silent schema drift."""

    model_config = ConfigDict(extra="forbid", frozen=True)
```

Import `StrictModel` rather than redefining it. Each Phase 2 record should have a literal schema version, use `Field` for ranges/IDs, and use an `after` validator only for invariants local to one model.

**Schema version, bounded fields, and local invariant** (lines 32-44, 80-127):

```python
class CriticalNegativeCase(StrictModel):
    schema_version: Literal["critical-negative-case/v1"]
    case_id: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{0,127}$")
    blocker_class: Literal[...]
    triggered: bool
    evidence: list[str]

@model_validator(mode="after")
def validate_frozen_decisions(self) -> ValidationCharter:
    if len(set(self.critical_blocking_failures)) != 5:
        raise ValueError("critical blocking failure classes must be unique")
    return self
```

Use this for `Experience`, `Contribution`, claim, Evidence, Skill, assessment, user-Skill view, source manifest, review, and mutation declarations. Put cross-record resolution, duplicate Evidence, and no-direct-mastery rules in `invariants.py`, not a single record validator.

### `src/career_evidence_graph/domain/invariants.py` (utility / validator, transform)

**Analog:** `src/career_evidence_graph/validation/acceptance.py`

**Pure aggregate evaluation** (lines 1-22):

```python
from collections.abc import Iterable

from .models import CriticalNegativeCase, FunctionalAcceptanceEvaluation


def evaluate_functional_acceptance(
    cases: Iterable[CriticalNegativeCase], *, strengths_observed: Iterable[str] = ()
) -> FunctionalAcceptanceEvaluation:
    blocking_classes = sorted({case.blocker_class for case in cases if case.triggered})
    return FunctionalAcceptanceEvaluation(
        schema_version="functional-acceptance-evaluation/v1",
        decision="block" if blocking_classes else "pass",
        blocking_classes=blocking_classes,
        strengths_observed=list(strengths_observed),
    )
```

Follow this side-effect-free shape: accept validated fixture records, resolve IDs and uniqueness in local indexes, and return or raise a deterministic domain error. Never calculate a score, repair conflicts, or invoke a provider while validating. Apply it to contribution-only lineage, claim-level reviewed user-owned basis, duplicate `(evidence_id, claim_id)` detection, unresolved/partial mastery blocking, separated user-Skill fields, and ontology non-propagation.

### `src/career_evidence_graph/domain/fixtures.py` (fixture loader/sealer, file-I/O)

**Analog:** `src/career_evidence_graph/validation/store.py`

**Validated JSON ingress** (lines 47-59):

```python
def _load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise FormalRunStorageError(f"cannot read valid JSON from {path.name}") from exc


def load_charter(path: Path) -> ValidationCharter:
    try:
        return ValidationCharter.model_validate(_load_json(path.resolve(strict=True)))
    except (OSError, ValidationError) as exc:
        raise FormalRunStorageError("invalid validation charter") from exc
```

Load every Phase 2 JSON file through its Pydantic contract; do not use `model_construct()`. Translate JSON, validation, and unsafe-path errors into a small fixture-specific error type.

**Canonical immutable write and identity** (lines 77-90):

```python
@staticmethod
def _write_json(path: Path, value: Any) -> None:
    data = canonical_json_bytes(value) + b"\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.")
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_name, path)
    except BaseException:
        Path(temporary_name).unlink(missing_ok=True)
        raise
```

Reuse Phase 1’s `canonical_json_bytes` and `sha256_digest` for the sealed known-good base hash. Reuse `FormalRunStore`/`CorrectionRecord` for review publication and history instead of inventing a second mutable store; Phase 2 fixture code should primarily validate/load and enforce sealing prerequisites.

### `src/career_evidence_graph/domain/__init__.py` (package surface, transform)

**Analog:** `src/career_evidence_graph/validation/__init__.py`

**Explicit public surface** (lines 1-12):

```python
"""Strict contracts and offline validation primitives."""

from .acceptance import evaluate_functional_acceptance
from .models import FormalRunManifest, ProvenanceRegistry, ReplayResult, ValidationCharter

__all__ = [
    "FormalRunManifest",
    "ProvenanceRegistry",
    "ReplayResult",
    "ValidationCharter",
    "evaluate_functional_acceptance",
]
```

Export only stable domain contracts, public validators, and fixture-loading entry points. Keep implementation helpers private.

### `validation/fixtures/stoa/v1/*.json` (fixtures, file-I/O/transform)

**Closest analogs:** `validation/charter/v1.json`, `validation/provenance/registry.json`, and formal-run payload files published by `FormalRunStore`.

**Canonical JSON serialization** (`src/career_evidence_graph/validation/store.py`, lines 77-87):

```python
data = canonical_json_bytes(value) + b"\n"
...
os.replace(temporary_name, path)
```

**Review correction preservation** (`tests/test_run_store.py`, lines 90-120):

```python
correction = CorrectionRecord(
    schema_version="correction-record/v1",
    correction_id="correction-1",
    original_proposal=proposal,
    original_proposal_hash=proposal_hash,
    correction={"capability": "reviewer-corrected"},
    reviewer_id="reviewer-1",
    reason="Responsibility belonged to the team.",
)
```

Use one schema-versioned object per file, UTF-8 canonical JSON, stable IDs, and no undocumented fields. `candidates.json` remains document-derived/non-personal; `review.json` retains each accept/edit/reject/unresolved decision and corrections; `known-good.json` must remain absent or unsealed until the human checkpoint; each known-bad JSON declares exactly one base hash, typed mutation, and expected invariant code.

### `tests/test_domain_models.py` (test, transform)

**Analog:** `tests/test_charter.py`

**Strict parsing and message-focused rejection** (lines 24-44):

```python
payload = json.loads(charter_path.read_text(encoding="utf-8"))
payload["unreviewed_rule"] = True

with pytest.raises(ValidationError):
    ValidationCharter.model_validate(payload)

with pytest.raises(ValidationError, match="cannot be acceptance-eligible"):
    ValidationCharter.model_validate(payload)
```

Test valid models plus unknown fields, invalid ranges, missing basis/locators, unsupported Experience types, and distinct per-claim attribution. Make each invalid payload isolate one model-level rule.

### `tests/test_domain_invariants.py` and `tests/test_fixture_mutations.py` (tests, transform)

**Analog:** `tests/test_security_boundaries.py`

**One negative case per parametrized fault** (lines 56-73):

```python
@pytest.mark.parametrize("blocker_class", CRITICAL_CLASSES)
def test_each_critical_class_blocks_independently(blocker_class):
    case = CriticalNegativeCase(..., blocker_class=blocker_class, triggered=True, ...)
    evaluation = evaluate_functional_acceptance([case])
    assert evaluation.decision == "block"
    assert evaluation.blocking_classes == [blocker_class]
```

Use parametrization for prohibited direct sources, attribution laundering, duplicated Evidence, missing lineage/basis, score confusion/range, and ontology propagation. For fixture mutations assert the base fixture validates first, mutation metadata has one operation, and the resulting failure equals the declared code—without adding a second intentional fault.

### `tests/test_stoa_fixture.py` (test, file-I/O)

**Analog:** `tests/test_provenance.py`

**Repository fixture integration and fail-closed drift check** (lines 17-38, 75-84):

```python
registry = verify_provenance_registry(
    registry_path="validation/provenance/registry.json",
    readme_path="references/README.md",
    project_root=".",
)
assert len(registry.records) == 4

with pytest.raises(ProvenanceValidationError, match="invalid provenance registry"):
    load_provenance_registry(path)
```

Assert only the four exact pinned repositories and permitted tracked document locators are accepted; assert the candidate/review distinction; assert incomplete review cannot seal known-good; and assert planned-only items cannot enter contribution/assessment lineage. Do not inspect STOA implementation code in this test or fixture loader.

### `src/career_evidence_graph/cli.py` (only if needed; CLI, request-response)

**Analog:** existing command dispatch in `src/career_evidence_graph/cli.py`.

**Parser + typed boundary + uniform error exit** (lines 30-63, 80-109, 165-174):

```python
parser = argparse.ArgumentParser(prog="career-evidence")
commands = parser.add_subparsers(dest="command", required=True)
...
try:
    ...
    _emit({"valid": True, "record_count": len(registry.records)})
except (..., ValidationError, OSError, json.JSONDecodeError) as exc:
    print(f"error: {exc}", file=sys.stderr)
    return 2
```

Only add a deterministic `fixture validate`/`fixture seal` command if tests or operator workflow actually need it. Preserve JSON stdout, `2` for invalid input, and no live provider path.

## Shared Patterns

### Strict contracts and validation

**Source:** `src/career_evidence_graph/validation/models.py` lines 12-16, 80-127.  
**Apply to:** all Phase 2 domain records and fixture envelopes.

```python
class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
```

### Immutable, content-addressed fixture identity

**Source:** `src/career_evidence_graph/validation/store.py` lines 77-90; `tests/test_run_store.py` lines 41-50.  
**Apply to:** known-good sealing, review corrections, and base hashes for known-bad mutations.

```python
data = canonical_json_bytes(value) + b"\n"
...
os.replace(temporary_name, path)
```

### Fail closed on invalid/trust-breaking input

**Source:** `src/career_evidence_graph/validation/store.py` lines 47-59; `tests/test_security_boundaries.py` lines 90-97 and 147-156.  
**Apply to:** source pins, locators, schema violations, missing references, duplicate Evidence, missing review, and multi-operation mutations.

```python
with pytest.raises(FormalRunStorageError, match="unsafe path"):
    store.verify(unsafe_run_id)

assert not (tmp_path / "formal-runs").exists()
```

### Offline deterministic tests

**Source:** `pyproject.toml` lines 24-38 and `tests/test_replay.py` lines 27-43.  
**Apply to:** every Phase 2 test module.

```python
def fail_live_call(*args, **kwargs):
    raise AssertionError("exact replay must not invoke a live subprocess")

monkeypatch.setattr(subprocess, "run", fail_live_call)
```

## No Analog Found

| File | Role | Data Flow | Reason |
|---|---|---|---|
| `validation/fixtures/stoa/v1/source-manifest.json` | config / fixture | file-I/O | Phase 1 provenance records external-code reuse, not a document-only human-review source manifest. |
| `validation/fixtures/stoa/v1/candidates.json` | fixture | transform | No existing candidate-fact/review split exists; use Phase 1 correction-history semantics without treating documents as personal proof. |
| `validation/fixtures/stoa/v1/review.json` | fixture | event-driven / transform | No standalone review schema exists; adapt `CorrectionRecord` history and define Phase 2 review state explicitly. |
| `validation/fixtures/stoa/v1/known-bad/*.json` | fixture | transform | Existing negative cases are in Python tests, not declarative one-fault JSON mutation files. |
| `src/career_evidence_graph/domain/invariants.py` | utility / validator | transform | No prior collection-level domain invariant engine exists; adapt pure Phase 1 acceptance evaluation and keep the new logic explicit. |

## Metadata

**Analog search scope:** `src/career_evidence_graph/validation/`, `src/career_evidence_graph/cli.py`, `tests/`, `validation/`, `pyproject.toml`  
**Files scanned:** 16  
**Pattern extraction date:** 2026-07-30
