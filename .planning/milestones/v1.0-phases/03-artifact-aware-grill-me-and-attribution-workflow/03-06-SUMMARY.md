---
phase: 03-artifact-aware-grill-me-and-attribution-workflow
plan: "06"
subsystem: audit-validation
tags: [pytest, offline, behavioral-probes, audit-workflow]
requires: [03-04, 03-05]
provides: [phase03-original-probe-marker, workflow-gap-probe-marker]
affects: [phase-03-final-acceptance, audit-regressions]
tech-stack:
  added: []
  patterns: [direct-behavior-probes, marker-owned-acceptance-inventory]
key-files:
  created: []
  modified:
    - pyproject.toml
    - tests/test_audit_cli.py
    - tests/test_audit_inspection.py
    - tests/test_audit_policy.py
    - tests/test_audit_attribution.py
    - tests/test_assistance_migration.py
    - tests/test_audit_conclusion.py
    - tests/test_audit_store.py
    - tests/test_audit_workflow_regressions.py
key-decisions:
  - "Phase 3 acceptance probes are uniquely named direct pytest tests, not wrapper or planning-text checks."
  - "Original acceptance probes and workflow-review gaps use separate registered pytest markers."
actuals:
  tokens: 5412
  tasks: 3
  commits: 3
metrics:
  duration: "24 min"
  completed: "2026-08-26"
status: complete
---

# Phase 3 Plan 6: Materialize audit acceptance probes Summary

All 28 original Phase 3 acceptance behaviors and the five workflow-side review gaps are direct, marker-owned offline pytest regressions.

## Completed Tasks

1. Registered the `phase03_original_probe` and `phase03_gap_probe` markers, and materialized original probes 1–18 across CLI, inspection, and question-policy tests.
2. Materialized original probes 19–28 across attribution, assistance migration, conclusion, and custody tests.
3. Marked the five workflow-side review/verification regressions and removed wrapper-only duplicate tests.

## Verification

- Seven original probe files plus both gap regression files: 47 passed.
- `phase03_original_probe` collection: 28/38 tests collected, 10 deselected.
- `phase03_gap_probe` workflow collection: 5 tests collected.
- Focused Ruff check and format check: passed.

## Task Commits

1. `ca5405d` — `test(03-06): materialize original workflow probes`
2. `215e9f7` — `test(03-06): materialize remaining original probes`
3. `df4c34c` — `test(03-06): mark workflow gap regressions`

## Deviations from Plan

### Auto-fixed Issues

1. [Rule 1 - Test isolation] Corrected the empty-linked-evidence probe fixture so it reaches the intended empty-link guard instead of the earlier missing-claim guard.
- **Found during:** Task 1 verification
- **Fix:** Retained valid contribution claims while removing their evidence links in the isolated fixture copy.
- **Files modified:** `tests/test_audit_inspection.py`
- **Commit:** `ca5405d`

## Known Stubs

None.

## Self-Check: PASSED

- All nine modified implementation/test artifacts and this summary exist.
- Commits `ca5405d`, `215e9f7`, and `df4c34c` exist in Git history.
