---
phase: 03-artifact-aware-grill-me-and-attribution-workflow
plan: "09"
subsystem: audit-workflow
tags: [python, pytest, audit, optimistic-concurrency, attribution, cli]
requires:
  - phase: 03-08
    provides: caller-held event-head CAS and locked audit transactions
provides:
  - Mandatory effective-conclusion CAS for every direct review
  - Fail-closed question target and malformed CLI action boundaries
  - Persisted unresolved bilingual attribution conclusions
affects: [phase-03-verification, audit-cli, audit-conclusions]
tech-stack:
  added: []
  patterns: [projection CAS, classifier-first attribution, structured CLI diagnostics]
key-files:
  created: []
  modified:
    - src/career_evidence_graph/audit/models.py
    - src/career_evidence_graph/audit/workflow.py
    - src/career_evidence_graph/cli.py
    - tests/test_audit_attribution.py
    - tests/test_audit_cli.py
    - tests/test_audit_conclusion.py
    - tests/test_audit_gap_e2e.py
    - tests/test_audit_store.py
    - tests/test_audit_workflow_regressions.py
    - tests/test_validation_probe_matrix.py
decisions:
  - "Every review action must carry both its observed event head and effective-conclusion hash."
  - "Ambiguous ownership or assistance is terminal unresolved coverage, never audit-verified capability."
  - "Malformed audit actions use the same structured zero-write public boundary as workflow rejections."
metrics:
  duration: 30min
  completed: 2026-08-26
status: complete
actuals:
  tokens: 5457
  tasks: 3
  commits: 6
---

# Phase 03 Plan 09: Direct Review and Attribution Closure Summary

**Audit reviews now require fresh event and effective-conclusion projections, while ambiguous bilingual attribution remains explicitly unresolved through the offline CLI journey.**

## Accomplishments

- Required `expected_effective_conclusion_hash` in the strict review action contract and compare it unconditionally before any review mutation.
- Rejected mismatched optional question targets before a transaction can publish, and returned malformed action validation as a JSON `invalid_audit_action` diagnostic with exit code 2.
- Classified responsibility and assistance before terminal coverage; unresolved classification persists into prose-only unresolved conclusion entries.
- Expanded the executable marker inventory to exactly fourteen Phase 3 gap probes and exercised the real offline CLI journey.

## Task Commits

1. **Task 1 RED: direct review freshness regressions** - `a8b2e3c` (test)
2. **Task 1: enforce effective-conclusion review CAS** - `139f054` (feat)
3. **Task 2 RED: public action boundary regressions** - `160830a` (test)
4. **Task 2: fail closed at public action boundaries** - `8ff5d3a` (fix)
5. **Task 3 RED: unresolved attribution acceptance** - `f16b597` (test)
6. **Task 3: persist unresolved attribution conclusions** - `b41fb5b` (fix)

## Verification

- Focused Phase 03 closure suite: **29 passed**.
- Exact gap inventory: **14/30 collected, 16 deselected**; the fourteen IDs include the ten post-storage-CAS probes plus review-CAS, stale question target, malformed CLI action, and bilingual-attribution regressions.
- Locked full suite: **232 passed, 1 deselected**.
- `ruff check .`: passed.
- `ruff format --check .`: **49 files already formatted**.
- `git diff --check`: passed.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Restored direct terminal-review idempotence through action identity**
- **Found during:** Task 1
- **Issue:** Enforcing the projection CAS before replay recognition made a manually repeated terminal review look stale.
- **Fix:** The direct regression now carries its action ID, so the existing action-identity replay guard resolves it before attempting another review.
- **Files modified:** `tests/test_audit_conclusion.py`
- **Commit:** `139f054`

**2. [Rule 1 - Bug] Normalized touched tests with the locked Ruff formatter**
- **Found during:** Task 3 verification
- **Issue:** Ruff format validation found two test files changed by the plan no longer matched the repository formatter output.
- **Fix:** Applied the locked formatter and reran all focused, collection, full-suite, and Ruff gates.
- **Files modified:** `tests/test_audit_store.py`, `tests/test_audit_workflow_regressions.py`
- **Commit:** `b41fb5b`

## Known Stubs

None.

## Self-Check: PASSED

- Confirmed all ten modified source and test files exist.
- Confirmed commits `a8b2e3c`, `139f054`, `160830a`, `8ff5d3a`, `f16b597`, and `b41fb5b` exist in Git history.
