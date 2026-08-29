---
phase: 07-career-source-custody-and-private-workspace
plan: "00"
subsystem: testing
tags: [pytest, custody, lineage, privacy, synthetic-fixtures]
requires: []
provides:
  - "Collected synthetic custody contracts for Phase 7 declaration, capture, lineage, transformation, and duplicate behavior."
  - "Collected synthetic disclosure and private-workspace containment contracts for later CLI work."
affects: [07-01, 07-02, 07-03, career-source-custody]
actuals:
  tokens: 2879
  tasks: 2
  commits: 2
tech-stack:
  added: []
  patterns: ["Explicit module-availability guard for Wave 0 contract collection", "Synthetic-only sentinel builders"]
key-files:
  created: [tests/test_career_source_custody.py, tests/test_career_source_security.py]
  modified: []
key-decisions:
  - "Wave 0 contracts use invented sentinels only and never derive assertions from a private workspace."
  - "Missing production symbols skip explicitly during collection and become active contract assertions once Plan 07-01 adds the custody seam."
patterns-established:
  - "Custody tests name selectors by tracer, declaration, capture, lineage, transform, and duplicate."
  - "Security tests name selectors by cli, output, inspect, and format."
requirements-completed: [INV-01, INV-06, INV-07]
coverage:
  - id: D1
    description: "Synthetic custody selectors and builders collect before production implementation."
    requirement: INV-01
    verification:
      - kind: unit
        ref: "uv run --locked python scripts/run_pytest.py --collect-only -q tests/test_career_source_custody.py"
        status: pass
    human_judgment: false
  - id: D2
    description: "Synthetic security selectors and disclosure sentinels collect before production implementation."
    requirement: INV-07
    verification:
      - kind: unit
        ref: "uv run --locked python scripts/run_pytest.py --collect-only -q tests/test_career_source_security.py"
        status: pass
    human_judgment: false
duration: 13min
completed: 2026-08-29
status: complete
---

# Phase 07 Plan 00: Career Source Custody Wave 0 Summary

**Synthetic-only custody and disclosure contracts now provide all Phase 7 test selectors without reading, retaining, or deriving personal career data.**

## Performance

- **Duration:** 13 min
- **Started:** 2026-08-29T12:58:00Z
- **Completed:** 2026-08-29T13:11:20Z
- **Tasks:** 2/2
- **Files modified:** 2

## Accomplishments

- Added declaration, capture, recapture, locator, transformation, tampering, and duplicate-content builders for the custody expansion plans.
- Added synthetic raw-body, label, path, digest, hostile-input, public-tree, and staged-diff sentinels for the security expansion plans.
- Ensured all selectors collect while the production custody seam is absent, without importing missing symbols at collection time.

## Task Commits

1. **Task 07-00-01: Scaffold custody contracts and synthetic lineage builders** - `ffbdcce` (test)
2. **Task 07-00-02: Scaffold security contracts and disclosure sentinels** - `34e9c16` (test)

## Files Created/Modified

- `tests/test_career_source_custody.py` - Synthetic declaration and immutable-lineage contract surface.
- `tests/test_career_source_security.py` - Synthetic CLI, no-echo, containment, and public-boundary contract surface.

## Decisions Made

- Wave 0 fixture builders carry `candidate-only` expectations and explicit zero authority effects so provenance cannot imply facts, Skills, mastery, confidence, or assessments.
- The absent production module is guarded only at runtime in each test, preserving collection now while allowing Plan 07-01 to turn the cases into executable/red contracts.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Bounded the oversized hostile-input pytest identifier**
- **Found during:** Task 07-00-02
- **Issue:** Default parametrization rendered the complete oversized synthetic sentinel in the collected node identifier, producing excessive diagnostic output.
- **Fix:** Added fixed synthetic parameter IDs while retaining the same oversized-byte test input.
- **Files modified:** `tests/test_career_source_security.py`
- **Verification:** Combined collection reports the short `oversized` selector.
- **Committed in:** `34e9c16`

**Total deviations:** 1 auto-fixed (Rule 1)

## Known Stubs

| File | Lines | Intentional stub | Resolution |
|------|-------|------------------|------------|
| `tests/test_career_source_custody.py` | 21-25 | Explicit skip while `career_evidence_graph.career_sources` is unavailable. | Plan 07-01 supplies the custody module and makes these assertions runnable. |
| `tests/test_career_source_security.py` | 29-32 | Explicit skip while `career_evidence_graph.career_sources` is unavailable. | Plan 07-01 supplies the custody module and makes these assertions runnable. |

## Issues Encountered

- The sandbox could not access the existing `uv` cache; the locked offline commands succeeded after approved access to that existing cache.

## User Setup Required

None - no private workspace, credentials, or personal source material was requested or used.

## Next Phase Readiness

Plans 07-01 through 07-03 can use the collected selectors as their test-first custody and security contract surface. The intentional availability guards must be removed by providing the planned production module, not by suppressing the tests.

## Self-Check: PASSED

- Both declared test modules exist.
- Task commits `ffbdcce` and `34e9c16` exist in Git history.
