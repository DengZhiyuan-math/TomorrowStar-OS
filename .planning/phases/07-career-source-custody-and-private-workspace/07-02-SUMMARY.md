---
phase: 07-career-source-custody-and-private-workspace
plan: 02
subsystem: private-workspace-custody
tags: [python, pydantic, provenance, immutable-storage, sha256, privacy]
requires:
  - phase: 07-01
    provides: Candidate-only private-workspace custody tracer
provides:
  - Strict, versioned source-universe declarations with immutable revisions
  - Content-addressed recaptures and verified transformation lineage
  - Candidate-only duplicate content storage that retains logical source links
affects: [phase-08-inventory-reconciliation, phase-09-career-audit]
actuals:
  tokens: 7843
  tasks: 3
  commits: 4
tech-stack:
  added: []
  patterns: [canonical declaration manifests, content-addressed raw vault, fail-closed lineage verification]
key-files:
  created: []
  modified: [src/career_evidence_graph/domain/models.py, src/career_evidence_graph/career_sources.py, tests/test_career_source_custody.py]
key-decisions:
  - "The confirmed D-18/D-19 seam uses strict schema-versioned Pydantic manifests with centralized writer and reader validation."
  - "Equal source bytes share one hash-addressed raw object while every immutable capture retains its own logical source ID."
patterns-established:
  - "Declaration revisions and recaptures are create-only; current selectors never rewrite historical manifests."
requirements-completed: [INV-01, INV-06]
coverage:
  - id: D1
    description: Complete candidate-only source-universe declarations preserve cutoffs, unavailable dispositions, and predecessor-linked revisions.
    requirement: INV-01
    verification:
      - kind: integration
        ref: tests/test_career_source_custody.py -k declaration
        status: pass
    human_judgment: false
  - id: D2
    description: Immutable recapture, transformation, locator, and duplicate-content lineage fails closed under mutation.
    requirement: INV-06
    verification:
      - kind: integration
        ref: tests/test_career_source_custody.py -k 'capture or lineage or transform or duplicate'
        status: pass
    human_judgment: false
duration: 38min
completed: 2026-08-29
status: complete
---

# Phase 07 Plan 02: Career Source Custody Contract Summary

**Versioned source declarations now preserve explicit career coverage, while immutable hash-addressed captures and candidate-only transformations retain tamper-evident D-18/D-19 lineage.**

## Performance

- **Duration:** 38 min
- **Tasks:** 3/3
- **Files modified:** 3

## Accomplishments

- Recorded the user-confirmed versioned manifest seam without collecting or persisting private workspace data.
- Enforced canonical source-universe declarations with date cutoffs, typed availability dispositions, strict categories, and predecessor-linked immutable revisions.
- Enforced content-addressed raw storage, recapture ancestry, exact capture/hash transformation binding, precise locators, and zero fact/confidence side effects for duplicate content.

## Task Commits

1. **Task 07-02-00: Confirm the versioned D-18/D-19 lineage contract seam** — completed by the supplied `confirm-versioned-seam` response; no repository commit.
2. **Task 07-02-01: Complete source-universe revision declaration** — `89e6c43` (test), `4dfd397` (feat).
3. **Task 07-02-02: Enforce recapture, transformation, locator, and duplicate lineage** — `55bffe3` (test), `9198ace` (feat).

## Files Created/Modified

- `src/career_evidence_graph/domain/models.py` — strict source-universe, capture, transformer, and locator contracts.
- `src/career_evidence_graph/career_sources.py` — canonical declarations, content-addressed capture storage, and fail-closed lineage verification.
- `tests/test_career_source_custody.py` — synthetic golden, mutation, undeclared-payload, recapture, locator, and duplicate-storage coverage.

## Decisions Made

- Stable logical source IDs remain distinct from immutable capture IDs; only explicit selectors name the current capture.
- Transformation output remains candidate-only and cannot create facts, confidence, assessments, or mastery.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Preserved the existing tracer category spelling**

- **Found during:** Task 07-02-02
- **Issue:** The existing CLI tracer emits `project`, while the expanded registry uses `projects`; narrowing the strict category contract broke the previously proven tracer.
- **Fix:** Retained `project` as a legacy supported category spelling while preserving the complete registry and non-authoritative semantics.
- **Files modified:** `src/career_evidence_graph/domain/models.py`
- **Verification:** `tests/test_career_source_custody.py tests/test_career_source_security.py` — 42 passed.
- **Committed in:** `9198ace`

**Total deviations:** 1 auto-fixed (Rule 1)

## Issues Encountered

The sandbox could not read the existing uv cache. The same locked, offline verification commands passed after approved cache access.

## User Setup Required

None — no private source identity, path, raw content, hash, count, or configuration was collected or persisted.

## Next Phase Readiness

Phase 8 can consume a declared candidate-only source universe and immutable capture lineage. Inventory acceptance, completeness sealing, graph facts, assessment confidence, mastery, JD authority, and résumé authority remain absent.

## Self-Check: PASSED

- Confirmed all three modified source/test files exist.
- Confirmed commits `89e6c43`, `4dfd397`, `55bffe3`, and `9198ace` exist.
- Re-ran the Phase 7 custody/security suite: 42 passed; Ruff passed on all custody files.
