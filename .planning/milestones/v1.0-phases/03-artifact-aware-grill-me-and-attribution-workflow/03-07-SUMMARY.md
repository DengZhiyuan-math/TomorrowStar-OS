---
phase: 03-artifact-aware-grill-me-and-attribution-workflow
plan: "07"
subsystem: audit-validation
tags: [pytest, offline, cli, custody, regression, ruff]
requires: [03-04, 03-05, 03-06]
provides: [audit-cli-e2e-acceptance, exact-phase03-probe-inventory]
affects: [phase-03-verification, audit-workflow]
tech-stack:
  added: []
  patterns: [subprocess-cli-acceptance, pytest-collection-as-coverage-authority, exact-node-id-inventory]
key-files:
  created: [tests/test_audit_gap_e2e.py]
  modified:
    - tests/test_audit_storage_regressions.py
    - tests/test_validation_probe_matrix.py
    - .planning/phases/03-artifact-aware-grill-me-and-attribution-workflow/03-VALIDATION.md
key-decisions:
  - "Executable pytest collection, not Markdown, is the authority for the 28 original and nine gap probes."
  - "The final acceptance path uses real offline CLI subprocesses and persisted-workspace reopen checks."
actuals:
  tokens: 7696
  tasks: 2
  commits: 2
requirements-completed: [AUD-01, AUD-02, AUD-03, AUD-04, AUD-05]
coverage:
  - id: D1
    description: "Offline CLI journey verifies inspection, questioning, attribution, review custody, replay, stale writes, tampering, CAS, and recovery."
    requirement: AUD-01
    verification:
      - kind: e2e
        ref: tests/test_audit_gap_e2e.py#test_repaired_audit_cli_journey_preserves_custody_and_reopens
        status: pass
    human_judgment: false
  - id: D2
    description: "Exact original and gap behavioral inventory is collected from declared pytest files."
    requirement: AUD-05
    verification:
      - kind: integration
        ref: tests/test_validation_probe_matrix.py#test_all_28_original_and_nine_gap_probes_are_collected
        status: pass
    human_judgment: false
metrics:
  duration: "35 min"
  completed: "2026-08-26"
status: complete
---

# Phase 3 Plan 7: Final audit acceptance and executable inventory Summary

The repaired offline audit is now exercised through its public CLI, while pytest itself proves the exact 28 original and nine gap behavioral node IDs.

## Completed Tasks

1. Added a single temporary-workspace CLI journey that crosses inspection, pause/resume, bilingual attribution, review hashes, canonical conclusion lineage, replay, stale rejection, concurrency, tampering, and publication recovery.
2. Marked the four storage-side custody regressions and replaced Markdown-based probe checking with scoped collect-only exact node-ID gates; updated the human-readable validation map.

## Verification

- Public CLI E2E: `1 passed`.
- Focused journey, inventory, workflow, and storage regressions: `13 passed`.
- Exact collection: `28/38` original tests collected and `9/11` gap tests collected; the exact-ID gate passed.
- Locked full suite: `226 passed, 1 deselected`.
- `ruff check .`: passed.
- `ruff format --check .`: `49 files already formatted`.

## Task Commits

1. Task 1 — `a308b53` `test(03-07): prove repaired audit CLI journey`
2. Task 2 — `ff49ee0` `test(03-07): gate exact phase three probe inventory`

## Files Created/Modified

- `tests/test_audit_gap_e2e.py` — public offline subprocess acceptance journey.
- `tests/test_audit_storage_regressions.py` — directly marked CAS, event-chain, replay, and recovery tests.
- `tests/test_validation_probe_matrix.py` — scoped pytest collection and exact full node-ID gate.
- `03-VALIDATION.md` — non-authoritative human map of the executable inventory and final commands.

## Decisions Made

- Scoped pytest collection is the coverage authority, so Markdown can document but cannot manufacture a probe.
- One E2E test uses the public CLI for cross-layer behavior while focused tests retain direct storage and workflow assertions.

## Deviations from Plan

### Auto-fixed Issues

1. [Rule 1 - Test bug] Corrected the collection parser to match pytest node IDs rather than a double-escaped literal period.
- **Found during:** Task 2 red test execution.
- **Fix:** Changed the node-ID regular expression to match `tests/file.py::test_name` correctly.
- **Files modified:** `tests/test_validation_probe_matrix.py`
- **Verification:** Exact original 28 and gap nine collection checks pass.
- **Committed in:** `ff49ee0`

**Total deviations:** 1 auto-fixed (Rule 1).

## Known Stubs

None.

## Next Phase Readiness

Phase 3 now has a reproducible offline acceptance journey and exact executable probe inventory. No deferred phase behavior was introduced.

## Self-Check: PASSED

- Created test and all three modified validation artifacts exist.
- Commits `a308b53` and `ff49ee0` exist in Git history.
