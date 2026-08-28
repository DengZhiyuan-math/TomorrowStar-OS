---
phase: 03-artifact-aware-grill-me-and-attribution-workflow
plan: "08"
subsystem: audit-storage
tags: [python, pytest, audit-store, optimistic-concurrency, custody]
requires:
  - phase: 03-07
    provides: locked audit event authority and gap-probe inventory baseline
provides:
  - Mandatory caller-held event-head CAS at the public audit writer
  - Transaction-backed direct test helper publication
  - Tenth phase03_gap_probe stale direct-update regression
affects: [03-09, audit workflow, review publication]
actuals:
  tokens: 1819
  tasks: 2
  commits: 3
tech-stack:
  added: []
  patterns: [caller-held CAS, locked-current transaction transition]
key-files:
  created: []
  modified:
    - src/career_evidence_graph/audit/store.py
    - tests/test_audit_storage_regressions.py
    - tests/test_audit_store.py
    - tests/test_audit_workflow_regressions.py
    - tests/test_audit_conclusion.py
key-decisions:
  - "AuditStore.update rejects a missing caller-held event hash rather than deriving one from live storage."
  - "Test fixtures publish state only through AuditStore.transact callbacks derived from locked current state."
patterns-established:
  - "Every persistent audit action supplies a unique action ID and the latest event head before entering transact."
requirements-completed: [AUD-02, AUD-05]
coverage:
  - id: D1
    description: "Public audit writes reject omitted and stale event heads without changing custody bytes."
    requirement: AUD-02
    verification:
      - kind: unit
        ref: "tests/test_audit_storage_regressions.py#test_direct_update_requires_caller_held_head_and_rejects_stale_snapshot"
        status: pass
    human_judgment: false
  - id: D2
    description: "Workflow, review, and conclusion fixtures publish through caller-held transactions."
    requirement: AUD-05
    verification:
      - kind: unit
        ref: "tests/test_audit_workflow_regressions.py and tests/test_audit_conclusion.py"
        status: pass
    human_judgment: false
duration: 5min
completed: 2026-08-26
status: complete
---

# Phase 03 Plan 08: Audit Writer CAS Summary

**The public audit writer now requires a caller-held event head, while all direct fixture publication uses the locked transaction authority.**

## Performance

- **Duration:** 5min
- **Started:** 2026-08-26T16:00:00Z
- **Completed:** 2026-08-26T16:04:47Z
- **Tasks:** 2
- **Files modified:** 5

## Accomplishments

- Added the distinct tenth `phase03_gap_probe` proving omitted and stale direct updates cannot publish or alter snapshot, event, or accepted-result bytes.
- Removed the public writer's implicit live-head compatibility fallback; it now fails closed without an explicit event hash and delegates publication to `transact`.
- Migrated store, workflow, terminal-review, and conclusion helpers to caller-held action IDs, event heads, and locked-current transitions.

## Task Commits

1. **Task 1 RED: stale direct update regression** - `2c92b3a` (test)
2. **Task 1: Enforce caller-held CAS on the public audit writer** - `7618af5` (feat)
3. **Task 2: Migrate workflow regression helpers to explicit transactions** - `cbf1496` (test)

## Files Created/Modified

- `src/career_evidence_graph/audit/store.py` - requires an explicit event-head precondition for direct updates.
- `tests/test_audit_storage_regressions.py` - covers omitted-head and stale-snapshot direct-update rejection with byte preservation.
- `tests/test_audit_store.py` - uses transactions for fixture setup and review publication.
- `tests/test_audit_workflow_regressions.py` - uses transactions for completion and terminal-review publication.
- `tests/test_audit_conclusion.py` - uses transactions for conclusion setup.

## Decisions Made

- `AuditStore.update` has no live-head fallback: a caller must present the event head it observed.
- Direct test setup is subject to the same custody authority as normal audit actions.

## Verification

- `UV_CACHE_DIR=/tmp/career-evidence-uv-cache uv run --locked python scripts/run_pytest.py -q tests/test_audit_storage_regressions.py tests/test_audit_store.py` — passed (10 tests).
- `UV_CACHE_DIR=/tmp/career-evidence-uv-cache uv run --locked python scripts/run_pytest.py -q tests/test_audit_workflow_regressions.py tests/test_audit_conclusion.py` — passed (11 tests).
- Combined focused suite — passed (21 tests).

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

Phase 03-09 can extend the exact probe inventory and validate the public semantic boundary on top of the strict writer contract.

## Self-Check: PASSED

- Confirmed all five changed source/test files exist.
- Confirmed task commits `2c92b3a`, `7618af5`, and `cbf1496` exist in Git history.

---
*Phase: 03-artifact-aware-grill-me-and-attribution-workflow*
*Completed: 2026-08-26*
