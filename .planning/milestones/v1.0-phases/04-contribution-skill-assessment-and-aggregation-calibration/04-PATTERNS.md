# Phase 4: Contribution–Skill Assessment and Aggregation Calibration - Pattern Map

**Mapped:** 2026-08-27
**Files analyzed:** 17 proposed new/modified files
**Analogs found:** 16 / 17

## Scope Extraction

The file set below is the smallest concrete interpretation of `04-CONTEXT.md` and
`04-RESEARCH.md`. The `assessment/` package and calibration paths are research
recommendations, not locked names; the planner may rename them while preserving the
same authority boundaries. Do not add a second Skill normalizer, a second
`ContributionSkillAssessment`, or a second user-Skill authority.

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|---|---|---|---|---|
| `src/career_evidence_graph/assessment/__init__.py` | config | transform | `src/career_evidence_graph/audit/__init__.py` | exact |
| `src/career_evidence_graph/assessment/models.py` | model | transform | `src/career_evidence_graph/audit/models.py` | exact |
| `src/career_evidence_graph/assessment/service.py` | service | transform / batch | `src/career_evidence_graph/audit/workflow.py` | role-match |
| `src/career_evidence_graph/assessment/store.py` | service | file-I/O | `src/career_evidence_graph/validation/store.py` | exact |
| `src/career_evidence_graph/domain/models.py` | model | transform | same file, lines 161-246 | exact |
| `src/career_evidence_graph/domain/invariants.py` | utility | transform | same file, lines 55-334 | exact |
| `src/career_evidence_graph/cli.py` | controller | request-response | same file, lines 158-200 and 356-435 | exact |
| `validation/calibration/phase-04/corpus.json` | config | batch | none: no checked-in completed audit corpus exists | none |
| `validation/calibration/phase-04/policies.json` | config | batch | `validation/charter/v1.json` | role-match |
| `tests/test_assessment_models.py` | test | transform | `tests/test_audit_conclusion.py` | exact |
| `tests/test_assessment_proposal.py` | test | transform | `tests/test_audit_gap_e2e.py` | role-match |
| `tests/test_assessment_admission.py` | test | event-driven | `tests/test_audit_gap_e2e.py` | exact |
| `tests/test_mastery_anchors.py` | test | transform | `tests/test_domain_models.py` | role-match |
| `tests/test_skill_aggregation.py` | test | batch | `tests/test_domain_invariants.py` | role-match |
| `tests/test_anchor_promotion.py` | test | batch | `tests/test_domain_invariants.py` | role-match |
| `tests/test_policy_calibration.py` | test | batch / file-I/O | `tests/test_run_store.py` | role-match |
| `tests/test_assessment_cli.py` | test | request-response | `tests/test_audit_gap_e2e.py` | exact |

## Pattern Assignments

### `src/career_evidence_graph/assessment/__init__.py` (config, transform)

**Analog:** `src/career_evidence_graph/audit/__init__.py`

**Public package surface** (lines 1-14):

```python
"""Bounded, offline Contribution audit workflow."""

from .models import AuditAction, AuditSnapshot
from .store import AuditStore
from .workflow import inspect_contribution, start_audit, transition_audit

__all__ = [
    "AuditAction",
    "AuditSnapshot",
    "AuditStore",
    "inspect_contribution",
    "start_audit",
    "transition_audit",
]
```

Copy the explicit imports and `__all__` convention. Export only the narrow Phase 4
application surface. Do not re-export duplicate domain models.

---

### `src/career_evidence_graph/assessment/models.py` (model, transform)

**Analogs:** `src/career_evidence_graph/domain/models.py` and
`src/career_evidence_graph/audit/models.py`

Use this file only for Phase 4 proposal, review, admission, policy, comparison,
promotion, and activation envelopes. Evolve the existing assessment and user-Skill
entities in `domain/models.py` rather than redefining them here.

**Strict model/import pattern** (`domain/models.py`, lines 7-19):

```python
from __future__ import annotations

from typing import Annotated, Literal

from pydantic import Field, model_validator

from ..validation.models import StrictModel

ID_PATTERN = r"^[a-z][a-z0-9]*(?:[._-][a-z0-9]+)*$"
Identifier = Annotated[str, Field(pattern=ID_PATTERN)]
```

**Immutable original/effective review pattern** (`audit/models.py`, lines 181-232):

```python
class AuditConclusion(StrictModel):
    schema_version: Literal["audit-conclusion/v1"] = "audit-conclusion/v1"
    entries: tuple[ConclusionEntry, ...] = Field(min_length=1)
    whole_review: Literal["pending", "confirmed", "rejected"] = "pending"
    original_proposal: dict[str, object]
    original_proposal_hash: str = Field(pattern=r"^sha256:[a-f0-9]{64}$")
    effective_conclusion_hash: str = Field(pattern=r"^sha256:[a-f0-9]{64}$")

    @model_validator(mode="after")
    def hashes_match_conclusion_content(self) -> AuditConclusion:
        if self.original_proposal_hash != original_proposal_digest(self.original_proposal):
            raise ValueError("original proposal hash does not match its content")
        if self.effective_conclusion_hash != effective_conclusion_digest(
            self.entries, self.whole_review
        ):
            raise ValueError("effective conclusion hash does not match its content")
        return self

class ConclusionReview(StrictModel):
    review_id: str = Field(pattern=r"^review-[a-z0-9-]+$")
    reviewer_id: str = Field(min_length=1)
    reason: str = Field(min_length=1)
    sequence: int = Field(ge=1)
    before_effective_hash: str = Field(pattern=r"^sha256:[a-f0-9]{64}$")
    after_effective_hash: str = Field(pattern=r"^sha256:[a-f0-9]{64}$")
```

Apply this to original system proposals, complete corrected judgments, substantive
confirmation fields, ordered review history, and content hashes. Every policy and
result contract gets a literal schema version.

---

### `src/career_evidence_graph/domain/models.py` (model, transform)

**Analog:** existing Phase 2 contracts in the same file.

**Assessment separation pattern** (lines 190-217):

```python
class AssessmentLineage(StrictModel):
    schema_version: Literal["assessment-lineage/v1"] = "assessment-lineage/v1"
    source_kind: AssessmentSourceKind
    contribution_id: Identifier = Field(pattern=ID_PATTERN)

class ContributionSkillAssessment(StrictModel):
    schema_version: Literal["contribution-skill-assessment/v1"] = "contribution-skill-assessment/v1"
    id: Identifier = Field(pattern=ID_PATTERN)
    skill_id: Identifier = Field(pattern=ID_PATTERN)
    contribution_id: Identifier = Field(pattern=ID_PATTERN)
    lineage: AssessmentLineage
    demonstrated_mastery: int = Field(ge=0, le=100)
    skill_centrality: int = Field(ge=0, le=100)
    evidence_confidence: int = Field(ge=0, le=100)
    context: str = Field(min_length=1)
    duration: DurationEvidence
    basis_claim_ids: tuple[Identifier, ...] = Field(min_length=1)
    assessment_status: Literal["partial", "unresolved", "reviewed"]
```

Evolve this contract with anchor identity/range/text, observable anchor-fit basis,
exact-score basis, next-anchor-not-established, audit/conclusion lineage, version,
and effective admission state. Keep the three scores as independent fields.

**Compatibility seam** (lines 220-246): retain loading of `UserSkillView/v1` and
the sealed fixture's empty collections. Add a policy-bearing calibrated result
contract without mutating `validation/fixtures/stoa/v1/known-good.json`.

---

### `src/career_evidence_graph/assessment/service.py` (service, transform / batch)

**Analog:** `src/career_evidence_graph/audit/workflow.py`

**Imports and explicit dependency seam** (lines 3-34):

```python
from __future__ import annotations

import re
from pathlib import Path
from uuid import uuid4

from ..domain.fixtures import SealedFixtureRecord, load_sealed_fixture, verify_source_manifest
from .decision import AuditDecisionPort, FakeDecisionPort, validate_boundary_decision
from .models import AuditAction, AuditSnapshot
from .store import AuditStore
```

Keep Phase 4 orchestration explicit: load a sealed source, accept a completed and
confirmed `AuditSnapshot`, normalize a specific Skill, create three judgments,
decide admission, aggregate admitted assessments, compare policies, then record a
separate activation decision.

**Fail-closed transition pattern** (lines 727-744):

```python
allowed = {
    "active": {"answer", "skip", "skip-contribution", "pause"},
    "paused": {"resume"},
    "reviewing": {"review-entry", "review-conclusion"},
    "completed": set(),
    "rejected": set(),
}
if action.action not in allowed[snapshot.status]:
    raise AuditWorkflowError(
        f"action {action.action} is not allowed while audit is {snapshot.status}"
    )
```

Use the same allow-list structure for assessment review/admission and policy
activation. Routine proposal input must have `snapshot.status == "completed"` and
`snapshot.conclusion.whole_review == "confirmed"`.

**Do not copy:** authority-changing `model_copy(update=...)` calls such as lines
474-486. At Phase 4 human review and activation boundaries, dump JSON, merge the
change, and run the concrete model's `model_validate` so cross-field validators run.

---

### `src/career_evidence_graph/domain/invariants.py` (utility, transform)

**Analog:** existing invariant functions in the same file.

**Contribution-only authority** (lines 55-83):

```python
def validate_contribution_lineage(fixture: CareerEvidenceFixture) -> tuple[InvariantViolation, ...]:
    contribution_ids = {item.id for item in fixture.contributions}
    violations: list[InvariantViolation] = []
    for assessment in fixture.assessments:
        path = f"assessments.{assessment.id}"
        if assessment.lineage.source_kind in DIRECT_MASTERY_SOURCES:
            violations.append(
                InvariantViolation(
                    code="assessment.direct-source-forbidden",
                    path=f"{path}.lineage.source_kind",
                )
            )
```

**One exact Skill result** (lines 171-213): retain same-Skill assessment tracing
and one-view-per-Skill enforcement, extended to policy-bearing Phase 4 results.

**Deterministic normalization** (lines 216-306): reuse `_normalized_text`, sorted
alias groups, `matched` / `review-required` / `unmatched`, and `descriptive-only`.
Never infer mastery from ontology relations.

**Required deliberate evolution:** replace lines 164-167's blanket
`assistance != "none"` rejection. Preserve assistance provenance, but base admission
on confirmed user ownership, explained capability, anchor fit, and unresolved
conflicts. Assistance alone neither proves nor disqualifies mastery.

---

### `src/career_evidence_graph/assessment/store.py` (service, file-I/O)

**Analogs:** `src/career_evidence_graph/audit/store.py` for atomic replacement and
`src/career_evidence_graph/validation/store.py` for immutable bundles.

**Validate again at storage boundary** (`audit/store.py`, lines 73-82):

```python
@staticmethod
def _validate(snapshot: AuditSnapshot) -> AuditSnapshot:
    try:
        return AuditSnapshot.model_validate(snapshot.model_dump(mode="json"))
    except ValidationError as exc:
        raise AuditStorageError("audit snapshot is invalid") from exc

@staticmethod
def _snapshot_bytes(snapshot: AuditSnapshot) -> bytes:
    return canonical_json_bytes(snapshot.model_dump(mode="json")) + b"\n"
```

**Atomic write** (`audit/store.py`, lines 85-109): use `tempfile.mkstemp`, flush,
`os.fsync`, `os.replace`, directory fsync, and cleanup.

**Immutable bundle verification** (`validation/store.py`, lines 252-306): reject
unsafe directories/symlinks, require the exact declared payload set, verify every
content hash, validate correction history, and recursively verify ancestry.

Use separate immutable payloads for proposal, reviews, effective assessments,
policy, aggregate results, comparison, and activation. A current-policy pointer is
not the policy/result authority itself.

---

### `src/career_evidence_graph/cli.py` (controller, request-response)

**Analog:** existing `audit` command family.

**Parser pattern** (lines 158-200):

```python
audit = commands.add_parser("audit")
audit_commands = audit.add_subparsers(dest="audit_command", required=True)
start = audit_commands.add_parser("start")
start.add_argument("--workspace", required=True)
# ... one parser per explicit action ...
inspect = audit_commands.add_parser("inspect")
inspect.add_argument("--workspace")
inspect.add_argument("--audit-id")
```

Add one `assessment` command family with the smallest explicit actions needed for
propose, inspect pending, review/confirm, aggregate, compare, and activate. Keep
business rules in `assessment/service.py`.

**Handler and error pattern** (lines 395-435): construct a strict action model,
read the store, call the service, persist the validated result, emit sorted JSON,
and map workflow/storage errors to stable JSON plus exit code 2.

No authentication middleware applies: this remains a trusted-local single-operator
CLI, and `reviewer_id` is asserted provenance rather than authenticated identity.

---

### `validation/calibration/phase-04/corpus.json` (config, batch)

**Analog:** none. The repository has no checked-in completed and confirmed Phase 3
audit corpus; `tests/test_audit_gap_e2e.py` lines 116-242 creates one only under
`tmp_path`.

Create a strict, schema-versioned corpus that references (rather than edits) the
sealed STOA fixture hash and exact audit/conclusion lineage hashes. Include real
reviewed inputs plus clearly labeled synthetic negative/counterfactual cases. Do
not place calibrated results into `known-good.json`.

---

### `validation/calibration/phase-04/policies.json` (config, batch)

**Analog:** `validation/charter/v1.json`

**Versioned data pattern** (lines 1-22):

```json
{
  "schema_version": "validation-charter/v1",
  "charter_version": "1.0.0",
  "expected_result_policy": {
    "structurally_exact": true,
    "semantic_comparisons": "declared_sets_and_ranges_only",
    "approved_set_fields": [],
    "approved_range_fields": {}
  }
}
```

Store thresholds, anchor rubrics, admission rules, duplicate suppression, and
promotion requirements as data. Include at least a current and candidate policy;
activation is a separate review record and never an implicit consequence of a run.

---

### `tests/test_assessment_models.py` (test, transform)

**Analog:** `tests/test_audit_conclusion.py`; construct complete frozen models and
assert invalid hash, missing basis, extra field, incomplete review, and invalid
version combinations fail closed. Cover all three score dimensions independently.

### `tests/test_assessment_proposal.py` (test, transform)

**Analog:** `tests/test_audit_gap_e2e.py`, lines 116-160. Build a completed,
confirmed audit through the real workflow, then assert the proposal retains fixture,
Contribution, Evidence, answer, attribution, conclusion-entry, normalization, and
lineage references. Reject active/reviewing/rejected audits and broad audit areas.

### `tests/test_assessment_admission.py` (test, event-driven)

**Analog:** `tests/test_audit_gap_e2e.py`, lines 161-206. Preserve the original
proposal across edit/confirm actions and verify contiguous before/after hashes.
High-mastery/low-confidence and self-rated inputs stay excluded until a substantive
review acknowledges attribution, anchor fit, all three judgments, reviewer, and
reason.

### `tests/test_mastery_anchors.py` (test, transform)

**Analog:** `tests/test_domain_models.py`. Parameterize every accepted boundary
(`0/19`, `20/39`, `40/54`, `55/69`, `70/79`, `80/89`, `90/95`, `96/100`), and
reject a number outside its named anchor or any higher band without observable
higher-order behavior and exact-score basis.

### `tests/test_skill_aggregation.py` (test, batch)

**Analog:** `tests/test_domain_invariants.py` and
`domain/invariants.py` lines 309-334. Compare canonical mastery snapshots before
and after duplicated Evidence, duplicated assessments/Contributions, and incidental
low-centrality uses. The result remains the maximum admitted mastery unless an
explicit valid promotion exists.

### `tests/test_anchor_promotion.py` (test, batch)

**Analog:** `tests/test_domain_invariants.py`. Use paired allowed/denied goldens.
Promotion names the next anchor, distinct behaviors, contexts, and admitted
assessment IDs. Counts, averages, sums, centrality, and confidence cannot trigger it.

### `tests/test_policy_calibration.py` (test, batch / file-I/O)

**Analog:** `tests/test_run_store.py` plus `validation/store.py` lines 158-218 and
252-331. Run current and candidate policies on the same hashed inputs, retain
per-Skill deltas, band/admission changes, reviewer disagreement and regressions,
verify immutable ancestry, and prove that comparison alone does not activate a
candidate.

### `tests/test_assessment_cli.py` (test, request-response)

**Analog:** `tests/test_audit_gap_e2e.py`, lines 14-25 and 89-113:

```python
def _run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(LAUNCHER), *args],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )

def _json(result: subprocess.CompletedProcess[str]) -> dict[str, object]:
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)
```

Exercise propose, pending inspection, substantive review, aggregation, comparison,
activation, reopen/inspect, and stable error JSON entirely offline.

## Shared Patterns

### Strict Validation and Validated Replacement

**Source:** `src/career_evidence_graph/validation/models.py`, lines 12-15

```python
class StrictModel(BaseModel):
    """Base model that rejects silent schema drift."""

    model_config = ConfigDict(extra="forbid", frozen=True)
```

Apply to every Phase 4 model. At correction/confirmation/activation boundaries,
use `model_dump(mode="json")`, merge changes, then call `type(model).model_validate`.

### Canonical Identity

**Source:** `src/career_evidence_graph/validation/hashing.py`, lines 12-27

```python
def canonical_json_bytes(value: Any) -> bytes:
    if isinstance(value, BaseModel):
        value = value.model_dump(mode="json")
    return json.dumps(
        value, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")

def sha256_digest(value: bytes) -> str:
    return f"sha256:{hashlib.sha256(value).hexdigest()}"
```

Reuse this exact identity format for policies, proposals, source envelopes,
effective assessments, comparisons, activations, and result bundles.

### Review Lineage

**Source:** `src/career_evidence_graph/audit/models.py`, lines 220-232 and 293-318

Hash the immutable proposal, current effective content, and ordered review records.
Require contiguous sequences and before/after hashes, and require the final review
hash to reach the effective object.

### Error Handling

**Source:** `src/career_evidence_graph/cli.py`, lines 411-458

Validate action payloads before service calls; return stable structured errors for
workflow/storage failures; emit no raw interview answers in integrity or security
errors. Use identifiers, invariant codes, and hashes instead.

### Authentication / Authorization

No auth analog applies. The phase is a trusted-local single-operator CLI. Preserve
`reviewer_id` as provenance but do not represent it as authenticated identity or use
SHA-256 content hashes as signatures.

### Deterministic Ordering and No Inflation

**Source:** `src/career_evidence_graph/domain/invariants.py`, lines 221-306 and
309-334

Sort normalized candidates and mastery-bearing records by stable identifiers.
Deduplicate repeated Evidence relationships within one Skill for weighting while
retaining lineage. Select the strongest admitted assessment as baseline; promotion
requires a separate validated next-anchor decision.

## No Analog Found

| File | Role | Data Flow | Reason |
|---|---|---|---|
| `validation/calibration/phase-04/corpus.json` | config | batch | Existing sealed STOA data has empty assessment/result collections, while the only completed audit E2E is temporary; no canonical checked-in Phase 4 corpus exists. |

## Planner Guardrails

- Prefer evolving `domain/models.py`, `domain/invariants.py`, and the existing
  normalizer over adding parallel authorities.
- Keep the sealed STOA fixture and completed audit snapshots immutable; Phase 4
  writes hash-linked sidecars.
- Treat `pending-confirmation` and `unverified-candidate` as explicit non-admitted
  states, not reduced mastery scores.
- Keep thresholds and formulas in versioned policy data. Do not change provider,
  model, SDK, temperature, reasoning, or structured-output configuration.
- Do not add a database, web UI, agent framework, vector store, document parser, JD
  comparison, résumé generator, or gap planner.
- Preserve upstream provenance records for any copied/adapted code. Local patterns
  above require no new dependency or upstream import.

## Metadata

**Analog search scope:** `src/career_evidence_graph/{domain,audit,validation}`,
`src/career_evidence_graph/cli.py`, `tests/`, `validation/`

**Files scanned:** 79 repository files under `src`, `tests`, and `validation`; 10
primary analog files read, with five recurring pattern families selected.

**Pattern extraction date:** 2026-08-27
