---
phase: 07-career-source-custody-and-private-workspace
plan: 12
subsystem: private-workspace
tags: [python, json, git-worktree, pytest, ruff]
requires:
  - phase: 07-10
    provides: historical current-HEAD gate evidence without requirement promotion
provides:
  - one direct private-workspace module and small JSON source registry
  - create-only ignored raw vault with optional caller-supplied derived mapping
  - synthetic direct-module custody and security coverage
affects: [phase-08-inventory, private-career-data, source-provenance]
actuals:
  tokens: 60284
  tasks: 2
  commits: 4
tech-stack:
  added: []
  patterns: [direct function API, standard-library registry validation, synthetic private-workspace tests]
key-files:
  created: []
  modified:
    - src/career_evidence_graph/workspace.py
    - src/career_evidence_graph/domain/models.py
    - src/career_evidence_graph/cli.py
    - tests/test_career_source_custody.py
    - tests/test_career_source_security.py
key-decisions:
  - "Keep private source custody as one direct workspace module instead of workspace/store/models/CLI layers."
  - "Use Git only to resolve and compare worktree roots; commits, refs, history, and migrations have no authority."
  - "Keep raw writes create-only and leave a failed-publication orphan for manual recovery rather than adding cleanup machinery."
patterns-established:
  - "Personal source data stays in the caller-selected private worktree; the public harness contains only generic code and synthetic fixtures."
  - "Source registry rows are candidate-only provenance metadata and cannot create facts, Skills, assessments, or mastery."
requirements-completed: []
coverage:
  - id: D1
    description: Direct private-workspace registry, raw capture, and caller-supplied derived-mapping boundary.
    verification:
      - kind: unit
        ref: tests/test_career_source_custody.py
        status: pass
    human_judgment: false
  - id: D2
    description: Separate-worktree, ignored-vault, safe-path, symlink, and redacted-output boundary.
    verification:
      - kind: unit
        ref: tests/test_career_source_security.py
        status: pass
    human_judgment: false
duration: 8min
completed: 2026-09-01
status: complete
---

# Phase 07 Plan 12: MVP Simplification Summary

**A single direct private-workspace registry replaces the Phase 7 store, source-model, and CLI custody engine.**

## Performance

- **Duration:** 8 min
- **Started:** 2026-09-01T10:27:16+02:00
- **Completed:** 2026-09-01T10:35:03+02:00
- **Tasks:** 2
- **Files modified:** 6

## Accomplishments

- Replaced the custody engine with `workspace.py`: explicit separate-worktree admission, one JSON registry, create-only ignored raw vault, and optional caller-supplied derived mapping.
- Removed the legacy `CareerSourceStore`, custody Pydantic hierarchy, `career-source` CLI branch, Git-history/ref/commit authority, migration, cleanup, and temporal machinery.
- Replaced legacy tests with 24 synthetic direct-module boundary tests; full offline tests and Ruff checks pass.

## Task Commits

1. **Task 1: Collapse Phase 7 to one direct private-workspace module** — `3e8011a` (RED test), `2e8f871` (implementation), `9e88860` (legacy-module deletion)
2. **Task 2: Prove the small workspace boundary without a CLI or custody engine** — `339bbcd` (direct boundary tests)

## Files Created/Modified

- `src/career_evidence_graph/workspace.py` — sole direct private-workspace and source-registry implementation.
- Legacy custody engine — removed; its deletion is recorded in `9e88860`.
- `src/career_evidence_graph/domain/models.py` — removed Phase 7 source-custody Pydantic contracts.
- `src/career_evidence_graph/cli.py` — removed `career-source` parser and error route.
- `tests/test_career_source_custody.py` — synthetic registry, capture, derived mapping, orphan, and redaction tests.
- `tests/test_career_source_security.py` — synthetic worktree, ignored vault, path, symlink, and output-boundary tests.

## Decisions Made

- One function-based module is sufficient for this personal MVP; a CLI and separate persistence/model layers add no validated value.
- Git worktree root comparison provides the required public/private separation; no Git historical data is read.
- An orphaned raw object after failed registry publication is explicit manual-recovery residue, not an invitation to add cleanup automation.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Execution bookkeeping] Legacy module deletion was not staged by the first scoped commit.**

- **Found during:** Task 2 final diff check.
- **Issue:** `career_sources.py` was correctly deleted in the worktree but absent from commit `2e8f871`.
- **Fix:** Added a one-file deletion commit immediately.
- **Files modified:** `src/career_evidence_graph/career_sources.py`
- **Verification:** Explicit absence check, focused tests, full suite, and Ruff passed.
- **Committed in:** `9e88860`

---

**Total deviations:** 1 auto-fixed (execution bookkeeping).
**Impact on plan:** No scope change; the intended legacy-module removal is now committed.

## Issues Encountered

- The sandbox could not open the shared uv cache. Re-running the same locked commands with approved access produced the actual test results.
- Ruff reported only unused-import and formatting issues; they were mechanically fixed before the final quality run.

## User Setup Required

None - the caller supplies the private Git worktree when using the module; no personal data was created or copied during this plan.

## Next Phase Readiness

- The minimal source-provenance boundary is ready for the Phase 8 inventory work.
- This plan does not complete INV-01, INV-06, INV-07, Phase 7, or the milestone. Independent verification remains required.

---
*Phase: 07-career-source-custody-and-private-workspace*
*Completed: 2026-09-01*
