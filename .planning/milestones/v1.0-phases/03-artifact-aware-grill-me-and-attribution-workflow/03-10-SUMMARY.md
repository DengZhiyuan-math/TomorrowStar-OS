---
phase: 03-artifact-aware-grill-me-and-attribution-workflow
plan: "10"
subsystem: audit-storage
tags: [python, pytest, filesystem, symlink-containment, mvp]
requires:
  - phase: 03-09
    provides: locked audit transactions, replay, conclusion review, and gap-probe inventory
provides:
  - Fail-closed custody-root validation for every audit storage path
  - External-target-preserving regression for a redirected audits directory
  - Canonical MVP user-story metadata for Phase 3
affects: [phase-03-verification, audit-storage, mvp-validation]
tech-stack:
  added: []
  patterns: [verified audit-root boundary, external-target byte-preservation regression]
key-files:
  created:
    - .planning/phases/03-artifact-aware-grill-me-and-attribution-workflow/03-10-SUMMARY.md
  modified:
    - src/career_evidence_graph/audit/store.py
    - tests/test_audit_storage_regressions.py
    - tests/test_validation_probe_matrix.py
    - .planning/ROADMAP.md
decisions:
  - "Every audit filesystem entry point derives its root from a real caller workspace and rejects a symlinked audits child before locks or records are created."
  - "Missing normal workspaces are created before validation so the containment fix preserves the public CLI start contract."
metrics:
  duration: 26min
  completed: 2026-08-26
status: complete
actuals:
  tokens: 10305
  tasks: 2
  commits: 3
requirements-completed: [AUD-01, AUD-02, AUD-04, AUD-05]
coverage:
  - id: D1
    description: "Audit custody root rejects an external symbolic-link target without modifying it."
    requirement: AUD-01
    verification:
      - kind: integration
        ref: tests/test_audit_storage_regressions.py#test_symlinked_audit_root_rejects_before_external_writes
        status: pass
    human_judgment: false
  - id: D2
    description: "Phase 3 uses a valid MVP user story and retains its exact gap-probe inventory."
    requirement: AUD-05
    verification:
      - kind: unit
        ref: tests/test_validation_probe_matrix.py#test_all_28_original_and_fifteen_gap_probes_are_collected
        status: pass
      - kind: other
        ref: user-story.validate Phase 3 goal
        status: pass
    human_judgment: false
---

# Phase 03 Plan 10: Audit-Root Containment Summary

**Audit storage now rejects a redirected `audits` root before custody writes, while Phase 3's resumable Contribution audit is represented as a valid MVP user story.**

## Accomplishments

- Established one verified audit-root boundary used by path derivation, locks, audit reads, transactions, recovery, and publication.
- Added a marked regression that points `workspace/audits` to an external directory and proves the directory's bytes remain unchanged after public `start_audit` fails.
- Preserved new-workspace CLI starts, existing recovery behavior, and per-audit containment while registering the fifteenth exact Phase 3 gap probe.
- Replaced only the Phase 3 roadmap goal with the canonical user story and validated it through the GSD user-story gate.

## Task Commits

1. **Task 1: Reject a redirected audit custody root before the first audit write** - `82ab32c` (fix)
2. **Task 1 deviation: preserve safe creation of a new workspace** - `6d9881f` (fix)
3. **Task 2: Restore canonical MVP goal metadata and exact probe inventory** - `0dd4115` (docs)

## Verification

- Focused storage and inspection suite: **19 passed**.
- User-story validation: **true**.
- Exact Phase 3 gap inventory: **15/31 collected, 16 deselected**.
- Full locked suite: **233 passed, 1 deselected**.
- `ruff check .`: passed.
- `ruff format --check .`: **49 files already formatted**.
- `git diff --check`: passed.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Restored creation of a missing normal workspace**
- **Found during:** Task 2 full locked quality gate
- **Issue:** The new containment guard rejected a normal CLI workspace before its first audit because that directory did not yet exist.
- **Fix:** Create the caller workspace first, then apply the existing non-symlink, directory, and resolved-root containment checks.
- **Files modified:** `src/career_evidence_graph/audit/store.py`
- **Verification:** Full locked suite passed with all CLI and end-to-end audit paths.
- **Committed in:** `6d9881f`

**Total deviations:** 1 auto-fixed (Rule 1 bug).

## Known Stubs

None.

## Self-Check: PASSED

- Confirmed all four modified implementation, test, and roadmap files exist.
- Confirmed commits `82ab32c`, `6d9881f`, and `0dd4115` exist in Git history.

## Next Phase Readiness

The planned containment closure and all locked gates are complete. Fresh independent Phase 3 verification can now evaluate the repaired custody boundary and the complete user story.
