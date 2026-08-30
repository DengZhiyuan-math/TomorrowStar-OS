---
phase: 07-career-source-custody-and-private-workspace
plan: 04
subsystem: private-workspace-custody
tags: [python, git, custody, provenance, privacy, synthetic-tests]
requires:
  - phase: 07-03
    provides: Explicit private-workspace CLI and content-free custody diagnostics
provides:
  - Caller-supplied complete Git commit authentication for global source custody verification
  - One complete semantic namespace registry with bidirectional snapshot comparison
  - Ignored raw-byte authentication and exhaustive empty-workspace proof
affects: [07-05, 07-06, 07-07, 07-08, phase-08-inventory-reconciliation]
actuals:
  tokens: 6939
  tasks: 2
  commits: 5
tech-stack:
  added: []
  patterns: [explicit commit authority, NUL-safe Git tree inventory, component-safe semantic paths]
key-files:
  created: []
  modified: [src/career_evidence_graph/workspace.py, src/career_evidence_graph/career_sources.py, src/career_evidence_graph/cli.py, tests/test_career_source_custody.py, tests/test_career_source_security.py]
key-decisions:
  - "Global verification accepts only a repository-format full OID that names a commit in the selected workspace."
  - "The committed Git tree, rather than mutable same-namespace files, authorizes every registered semantic record."
patterns-established:
  - "Use CareerSourceStore._semantic_path over PrivateWorkspace.child for custody inventory reads."
  - "Run source verification through scripts/run_pytest.py so tests import this checkout rather than an installed package."
requirements-completed: [INV-06]
coverage:
  - id: D1
    description: Explicit full commit OIDs authenticate semantic manifests and ignored raw bytes without exposing private material.
    requirement: INV-06
    verification:
      - kind: integration
        ref: "tests/test_career_source_custody.py#test_explicit_commit_verifies_committed_snapshot_and_ignored_raw_authentication"
        status: pass
    human_judgment: false
  - id: D2
    description: Every registered semantic namespace is compared in both directions, including expected-zero and empty snapshots.
    requirement: INV-06
    verification:
      - kind: integration
        ref: "tests/test_career_source_custody.py#test_empty_workspace_requires_a_complete_commit_and_proves_every_namespace_empty"
        status: pass
    human_judgment: false
duration: 43min
completed: 2026-08-30
status: complete
---

# Phase 07 Plan 04: Explicit Commit Snapshot Custody Summary

**Career-source verification now authenticates every semantic manifest and ignored raw object against a caller-supplied full private-Git commit, including expected-zero and empty snapshots.**

## Performance

- **Duration:** 43 min
- **Started:** 2026-08-30T21:12:00Z
- **Completed:** 2026-08-30T21:55:10Z
- **Tasks:** 2/2
- **Files modified:** 5

## Accomplishments

- Made `--expected-workspace-commit` mandatory for `career-source verify`; only a complete repository-format OID that names a commit in the selected workspace is accepted.
- Compared NUL-safe committed Git-tree blobs with safely scanned working semantic files in both directions before canonical lineage validation.
- Registered declarations, current declaration pointers, captures, current-captures, transformations, migration receipts, and derived outputs in one immutable semantic namespace registry.
- Authenticated ignored raw objects by committed capture digest and byte count while rejecting committed raw paths, malformed IDs, symlinks, orphan pointers, tag objects, and mutable inventory changes.

## Task Commits

1. **Task 1: Authenticate one custody snapshot end to end with a mandatory full commit OID** - `a425fef` (test), `4f8c793` (feat)
2. **Task 2: Compare complete semantic inventories and prove empty state exhaustively** - `4dedba0` (test), `b5ff069` (feat), `da16043` (fix)

## Files Created/Modified

- `src/career_evidence_graph/workspace.py` - verifies component-safe private-workspace child paths without following symlinks.
- `src/career_evidence_graph/career_sources.py` - owns explicit commit resolution, semantic namespace inventory, raw authentication, and empty-state proof.
- `src/career_evidence_graph/cli.py` - requires the explicit commit anchor for every source verification invocation.
- `tests/test_career_source_custody.py` - uses only temporary synthetic Git repositories for anchor, inventory, raw, tag, and malformed-path regressions.
- `tests/test_career_source_security.py` - updates the synthetic CLI flow to commit its semantic manifests before authoritative verification.

## Decisions Made

- Verification resolves the selected workspace's Git object format and accepts only a complete lowercase hexadecimal commit OID; refs, abbreviations, tags, and non-commit objects fail closed.
- Empty status is an authenticated Git snapshot with zero registered semantic entries and zero raw objects, never an inference from absent directories.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Regression] Preserved the existing synthetic CLI flow under the mandatory anchor contract**
- **Found during:** Task 2
- **Issue:** Existing verify regressions omitted the newly required explicit anchor and therefore exercised argparse failure instead of custody verification.
- **Fix:** Materialized and committed only synthetic test manifests, then passed their complete temporary-repository OID to the CLI.
- **Files modified:** `tests/test_career_source_security.py`
- **Verification:** `61 passed` in the complete synthetic custody/security suite.

**2. [Rule 2 - Verification integrity] Used the checkout-source pytest runner**
- **Found during:** Task 1
- **Issue:** Direct `uv run --locked pytest` imported a stale installed package rather than this checkout's `src/` code.
- **Fix:** Used the project-established `uv run --locked python scripts/run_pytest.py` source-selecting runner for all pytest evidence.
- **Files modified:** None
- **Verification:** All cited tests executed against the current checkout source.

**Total deviations:** 2 auto-fixed (1 Rule 1, 1 Rule 2).
**Impact on plan:** Both changes preserve the required explicit-authority and current-source validation boundaries; no product scope expanded.

## Issues Encountered

- The local virtual environment initially imported a stale installed package. `uv sync --locked` confirmed the locked environment, while the repository runner remained necessary to select checkout source.

## User Setup Required

None - all verification used temporary synthetic Git repositories and no external services.

## Next Phase Readiness

- Plans 07-05 through 07-08 can build on the single explicit-commit and semantic-path authority without creating a parallel store, parser, validator, or Git abstraction.
- This remediation authenticates source custody only; it does not establish source review, inventory acceptance, graph, mastery, JD, gap, résumé, or personal-material authority.

## Self-Check: PASSED

- Confirmed all five implementation/test files and this summary exist.
- Confirmed task commits `a425fef`, `4f8c793`, `4dedba0`, `b5ff069`, and `da16043` exist in Git history.

---
*Phase: 07-career-source-custody-and-private-workspace*
*Completed: 2026-08-30*
