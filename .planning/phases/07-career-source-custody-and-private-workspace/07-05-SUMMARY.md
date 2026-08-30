---
phase: 07-career-source-custody-and-private-workspace
plan: 05
subsystem: private-workspace-custody
tags: [python, git, custody, provenance, private-workspace, synthetic-tests]
requires:
  - phase: 07-04
    provides: Explicit commit snapshot authority and semantic namespace inventory
provides:
  - Exact source-ID transformation routing through declaration-bound current-capture pointers
  - Immutable declaration lineage on capture and transformation manifests
  - Content-addressed derived-output manifests with retained-byte authentication
  - Bidirectional transformation and derived-output closure in global verification
affects: [07-06, 07-07, 07-08, phase-08-inventory-reconciliation]
actuals:
  tokens: 10990
  tasks: 2
  commits: 4
tech-stack:
  added: []
  patterns: [declaration-bound lineage, strict source pointer, derived-output closure, explicit commit authentication]
key-files:
  created: []
  modified: [src/career_evidence_graph/domain/models.py, src/career_evidence_graph/career_sources.py, src/career_evidence_graph/cli.py, tests/test_career_source_custody.py]
key-decisions:
  - "Transforms resolve only the caller-named current-capture pointer; capture-directory order is never authority."
  - "Derived candidate bytes share the existing private raw vault while their tracked manifest is addressed by the unprefixed SHA-256 digest."
  - "A global verification snapshot requires bidirectional closure between transformations, output manifests, and recomputed retained bytes."
duration: 10min
completed: 2026-08-30
status: complete
---

# Phase 07 Plan 05: Declaration-Bound Transformation Custody Summary

**Source-selected transformations now retain immutable declaration and capture lineage, while global verification authenticates every derived-output manifest and ignored byte object against an explicit synthetic Git snapshot.**

## Performance

- **Duration:** 10 min
- **Tasks:** 2/2
- **Files modified:** 4
- **Verification:** 51 synthetic custody tests passed; scoped Ruff check passed.

## Accomplishments

- Replaced directory-based transform selection with an exact `--source-id` current-capture pointer lookup that confirms source, capture, content hash, and declaration identity.
- Added strict v2 declaration-bound capture, current-pointer, and transformation contracts, plus a v1 derived-output manifest contract.
- Bound each new capture to the exact immutable declaration revision and canonical declaration hash active at capture time; unbound v1 captures now fail with a migration-required code.
- Required CLI callers to supply a transformation ID and recorded source/input, declaration, transformer/version/configuration, candidate-only status, output digest, and byte count.
- Retained transformation output bytes in the existing ignored raw vault and published content-addressed output manifests at `derived-outputs/{digest}/manifest.json`.
- Extended explicit-commit verification to reject malformed, missing, stale, replaced, or unreferenced transformations and derived outputs, while allowing a complete newly committed transformation snapshot.

## Task Commits

1. **Task 1 RED: exact source and immutable-lineage regressions** — `0c03189`
2. **Task 1 GREEN: declaration-bound source transformations and retained output** — `ef444a2`
3. **Task 2 RED: transformation/output custody regressions** — `54c73f5`
4. **Task 2 GREEN: complete transformation/output verification** — `8f5a498`

## Files Modified

- `src/career_evidence_graph/domain/models.py` — declaration-bound capture, pointer, transformation, and derived-output contracts.
- `src/career_evidence_graph/career_sources.py` — strict current-source resolution, immutable capture lineage, output publication, and inventory closure verification.
- `src/career_evidence_graph/cli.py` — required transformation IDs and exact source routing.
- `tests/test_career_source_custody.py` — only temporary synthetic Git workspace regressions for routing, lineage, output mutation, and commit-anchor behavior.

## Decisions Made

- The mutable current-capture pointer is selector-only and repeats immutable target identity; it cannot redirect a requested source to another capture.
- Captures and transformations never use mutable `declarations/current.json` as historical authority after publication.
- Derived bytes remain ignored private objects, but their digest, byte count, candidate-only status, and reference closure are committed and verified.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Verification integrity] Used the checkout-source pytest runner**

- **Found during:** Tasks 1 and 2
- **Issue:** Direct `uv run --locked pytest` can import a stale installed package instead of this checkout's `src/` code.
- **Fix:** Ran the established `uv run --locked python scripts/run_pytest.py` wrapper for all cited test evidence.
- **Files modified:** None
- **Verification:** 51 synthetic custody tests passed against checkout source.

## Verification

- `uv run --locked python scripts/run_pytest.py tests/test_career_source_custody.py -x` — 51 passed.
- `uv run --locked ruff check src/career_evidence_graph/domain/models.py src/career_evidence_graph/career_sources.py src/career_evidence_graph/cli.py tests/test_career_source_custody.py` — passed.

## Known Stubs

None.

## Self-Check: PASSED

- Confirmed the four scoped implementation/test files exist.
- Confirmed commits `0c03189`, `ef444a2`, `54c73f5`, and `8f5a498` exist in Git history.
- Confirmed no real private career material or repository was accessed; all tests used temporary synthetic Git workspaces.
