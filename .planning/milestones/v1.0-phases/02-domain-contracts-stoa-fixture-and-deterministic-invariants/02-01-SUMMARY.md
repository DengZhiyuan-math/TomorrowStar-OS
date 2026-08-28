---
phase: 02-domain-contracts-stoa-fixture-and-deterministic-invariants
plan: "01"
subsystem: domain-validation
tags: [python, pydantic, cli, pytest, career-evidence]
requires:
  - phase: 01-validation-charter-provenance-and-technical-decision-gate
    provides: frozen strict-model, canonical hashing, and offline CLI patterns
provides:
  - Contribution-grounded career-evidence models and aggregate validation
  - Offline JSON fixture validation through the package CLI
  - Strict model tests for experience, evidence, attribution, and score boundaries
affects: [phase-02-fixtures, phase-03-grill-me, phase-04-assessment]
tech-stack:
  added: []
  patterns:
    - Frozen Pydantic records with schema-versioned recursive identifiers
    - Contribution-first fixture lineage and deterministic cross-record validation
key-files:
  created:
    - src/career_evidence_graph/domain/__init__.py
    - src/career_evidence_graph/domain/invariants.py
    - src/career_evidence_graph/domain/models.py
    - tests/fixtures/domain_fixture.json
    - tests/test_domain_models.py
  modified:
    - src/career_evidence_graph/cli.py
    - tests/test_cli_tracer.py
key-decisions:
  - "All nested collection references use the same stable identifier contract as top-level records."
  - "Whitespace-only assessment context is invalid; fixture scores remain explicitly non-calibrated."
patterns-established:
  - "Validate individual model syntax at Pydantic ingress, then resolve cross-record lineage in deterministic invariants."
requirements-completed: [MOD-01, MOD-03, MOD-04, MOD-05]
coverage:
  - id: D1
    description: "Supported Experience types retain distinct Contribution children and reject unsupported or malformed identifiers."
    requirement: MOD-01
    verification:
      - kind: unit
        ref: tests/test_domain_models.py#test_supported_experience_types_keep_distinguishable_contribution_ids
        status: pass
    human_judgment: false
  - id: D2
    description: "Evidence proof limits, claim attribution, duration, and independent assessment score boundaries fail closed."
    requirement: MOD-03
    verification:
      - kind: unit
        ref: tests/test_domain_models.py
        status: pass
    human_judgment: false
  - id: D3
    description: "A synthetic non-calibrated fixture crosses JSON, domain validation, and the real offline CLI while broken lineage rejects."
    requirement: MOD-04
    verification:
      - kind: e2e
        ref: tests/test_cli_tracer.py#test_domain_fixture_validate_tracer_is_offline_and_deterministic
        status: pass
    human_judgment: false
duration: 17 min
completed: 2026-07-30
status: complete
---

# Phase 02 Plan 01: Domain contracts and offline CLI tracer Summary

**Contribution-grounded Pydantic contracts validate offline fixture JSON, evidence limits, claim attribution, and independent 0–100 assessment dimensions without calibrating mastery.**

## Performance

- **Duration:** 17 min
- **Started:** 2026-07-30T14:09:20Z
- **Completed:** 2026-07-30T14:26:26Z
- **Tasks:** 2/2
- **Files modified:** 7

## Accomplishments

- Added the public `career_evidence_graph.domain` boundary, deterministic aggregate validation, and `career-evidence fixture validate PATH` for fully offline fixture traversal.
- Proved the tracer accepts the synthetic Contribution-grounded fixture and returns a stable rejection for missing Contribution lineage without reaching a network, subprocess, or live-model adapter.
- Added boundary coverage for the nine supported Experience types, five Evidence proof limits, independent responsibility and assistance, required duration/basis/context, and independently bounded score dimensions.

## Task Commits

1. **Task 1: Carry one Contribution-grounded record through the importable core and offline CLI** - `0a6d34c` (TDD RED), `71cbc9e` (TDD GREEN)
2. **Task 2: Expand strict record semantics across history types, Evidence proof limits, attribution, and score boundaries** - `643018a` (TDD RED), `4dd00cf` (TDD GREEN)

## Files Created/Modified

- `src/career_evidence_graph/domain/models.py` - Frozen schema-versioned career evidence contracts with strict nested identifiers and nonblank assessment context.
- `src/career_evidence_graph/domain/invariants.py` - Deterministic cross-record ID, lineage, evidence-link, and assessment validation.
- `src/career_evidence_graph/domain/__init__.py` - Explicit stable domain validation exports.
- `src/career_evidence_graph/cli.py` - Offline `fixture validate` command and stable invalid-fixture reporting.
- `tests/test_cli_tracer.py` - Real CLI subprocess and offline-side-effect tracer proof.
- `tests/test_domain_models.py` - Domain model positive, boundary, and fail-closed coverage.
- `tests/fixtures/domain_fixture.json` - Synthetic non-STOA, non-calibrated CLI fixture.

## Decisions Made

- Nested IDs use the same pattern contract as top-level IDs so malformed child references fail at model ingress.
- Context consisting only of whitespace is rejected; test fixture scores remain explicitly non-calibrated and no aggregation rule is introduced.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Rebuilt the local package after its pre-existing wheel omitted the new domain package.**
- **Found during:** Task 2 TDD RED verification
- **Issue:** `uv run --locked pytest` initially imported an older full-wheel installation and could not import `career_evidence_graph.domain`.
- **Fix:** Rebuilt only the already-locked local project package with `uv sync --locked --reinstall-package career-evidence-graph`; no dependency changed.
- **Files modified:** None
- **Verification:** The RED suite then collected and failed only on unmet constraints; the GREEN and plan-wide suites passed.
- **Committed in:** Not applicable (local environment repair only)

---

**Total deviations:** 1 auto-fixed (1 Rule 3 blocking environment repair).
**Impact on plan:** No production scope change or dependency change; the required verification now tested the current source package.

## Issues Encountered

None after rebuilding the local locked package.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Domain contracts and the deterministic CLI seam are ready for Phase 2 fixture/invariant plans.
- The checked-in tracer remains synthetic and non-calibrated; human-reviewed STOA material and any aggregation policy are intentionally deferred.

## Self-Check

PASSED - all seven shipped files exist and all four task commits (`0a6d34c`, `71cbc9e`, `643018a`, and `4dd00cf`) are present in Git history.

---
*Phase: 02-domain-contracts-stoa-fixture-and-deterministic-invariants*
*Completed: 2026-07-30*
