---
phase: 07-career-source-custody-and-private-workspace
plan: 01
subsystem: private-workspace-custody
tags: [python, pydantic, cli, provenance, privacy, filesystem]
requires:
  - phase: 07-00
    provides: Synthetic custody and security contract scaffolds
provides:
  - Explicit private-workspace career-source CLI tracer
  - Candidate-only immutable declaration, capture, and transformation manifests
  - Content-free adversarial containment checks
affects: [phase-08-inventory-reconciliation, phase-09-career-audit]
actuals:
  tokens: 6624
  tasks: 3
  commits: 3
tech-stack:
  added: []
  patterns: [explicit workspace authority, create-only source custody, content-free errors]
key-files:
  created: [src/career_evidence_graph/workspace.py, src/career_evidence_graph/career_sources.py]
  modified: [src/career_evidence_graph/domain/models.py, src/career_evidence_graph/cli.py, tests/test_career_source_custody.py, tests/test_career_source_security.py]
key-decisions:
  - "The confirmed public/private split remains runtime-only through required --workspace selection."
  - "Career-source records remain candidate-only and cannot create assessment, mastery, fact, or resume authority."
patterns-established:
  - "Semantic .career-evidence/sources manifests use create-only bundles; exact bytes stay under the ignored raw vault."
requirements-completed: [INV-01, INV-06, INV-07]
coverage:
  - id: D1
    description: Synthetic declaration, capture, transformation, and safe inspection are candidate-only end to end.
    requirement: INV-01
    verification:
      - kind: integration
        ref: tests/test_career_source_custody.py
        status: pass
    human_judgment: false
  - id: D2
    description: Unsafe workspace/source inputs and disclosure probes fail closed without routine output echoes.
    requirement: INV-07
    verification:
      - kind: integration
        ref: tests/test_career_source_security.py
        status: pass
    human_judgment: false
duration: 15min
completed: 2026-08-29
status: complete
---

# Phase 07 Plan 01: Career Source Custody Tracer Summary

**An explicit private-workspace CLI now records a synthetic career-source declaration, immutable raw capture, candidate-only transformation lineage, and content-free status without creating career-graph authority.**

## Performance

- **Duration:** 15 min
- **Started:** 2026-08-29T13:12:21Z
- **Completed:** 2026-08-29T13:27:38Z
- **Tasks:** 3/3
- **Files modified:** 6

## Accomplishments

- Honored the user's `confirm` decision for the one-way public/private custody boundary without recording any private workspace value.
- Added the offline `career-source` declaration, capture, transformation, and inspection tracer, with raw bytes confined to the selected workspace's ignored vault.
- Added strict candidate-only contracts and adversarial no-echo, inert-input, read-only, symlink, and synthetic public-leak checks.

## Task Commits

1. **Task 07-01-01: Confirm the one-way public/private custody door** — no code commit; user replied `confirm`.
2. **Task 07-01-02: Wire one synthetic declaration-capture-transform-inspect path** — `838da89` (test), `7224928` (feat)
3. **Task 07-01-03: Close tracer privacy and containment failures** — `3f1a911` (feat)

## Files Created/Modified

- `src/career_evidence_graph/workspace.py` — explicit safe private-workspace resolver.
- `src/career_evidence_graph/career_sources.py` — candidate-only custody store and safe status boundary.
- `src/career_evidence_graph/domain/models.py` — source-universe, capture, locator, and transformation contracts.
- `src/career_evidence_graph/cli.py` — required `career-source --workspace` commands.
- `tests/test_career_source_custody.py` — synthetic end-to-end and lineage coverage.
- `tests/test_career_source_security.py` — adversarial containment and disclosure coverage.

## Decisions Made

- The only personal-data entry point is an explicit runtime `--workspace`; no public pointer, URL, path, or identity is persisted.
- Routine status is content-free and source transformations are candidate-only, not accepted facts or assessment inputs.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Reconciled contradictory instruction-like input test expectations**
- **Found during:** Task 07-01-03
- **Issue:** One parametrized rejection test included inert instruction-like bytes, while the adjacent test required those same bytes to be accepted as inert data.
- **Fix:** Limited the rejection case to malformed/control/oversized bytes and preserved the dedicated inert-input assertion.
- **Files modified:** `tests/test_career_source_security.py`
- **Verification:** Scoped custody/security suite passed.
- **Committed in:** `3f1a911`

**Total deviations:** 1 auto-fixed (Rule 1)

## Issues Encountered

The sandboxed `uv` invocation could not access its existing cache; the same locked offline checks ran successfully with the required approval.

## User Setup Required

None - no private workspace identity, content, or configuration was collected or persisted.

## Next Phase Readiness

Phase 8 can consume only the candidate-only source-universe and capture lineage. No inventory acceptance, Skill creation, mastery, assessment confidence, market proof, JD authority, or resume authority was added.

## Self-Check: PASSED

- Confirmed source files and both test modules exist.
- Confirmed commits `838da89`, `7224928`, and `3f1a911` exist.
- Re-ran `uv run --locked python scripts/run_pytest.py -q tests/test_career_source_custody.py tests/test_career_source_security.py` (26 passed) and Ruff on all changed Python files.
