---
phase: 07-career-source-custody-and-private-workspace
plan: "06"
subsystem: private-workspace-custody
tags: [python, pydantic, git, migration, provenance, private-workspace, synthetic-tests]
requires:
  - phase: 07-05
    provides: Declaration-bound capture/transformation contracts, retained derived-output bytes, and explicit committed-snapshot verification
provides:
  - Complete explicit-baseline migration requests that authenticate all legacy captures, declaration bindings, transformations, and retained output bytes before writes
  - Deterministic candidate-only successor staging for every legacy chain, with exhaustive receipts and byte-identical retry handling
affects: [07-07, 07-08, phase-08-inventory-reconciliation]
actuals:
  tokens: 11543
  tasks: 2
  commits: 3
tech-stack:
  added: []
  patterns: [explicit-baseline migration preflight, retained-output authentication, exhaustive successor maps, retry-safe non-authoritative staging]
key-files:
  created: []
  modified: [src/career_evidence_graph/domain/models.py, src/career_evidence_graph/career_sources.py, tests/test_career_source_custody.py]
key-decisions:
  - "A migration request must enumerate the complete committed legacy inventory; current working state cannot select a subset."
  - "A retry may reuse only canonical request-derived staged files, and staging cannot move pointers or create Git authority."
patterns-established:
  - "Migration preflight authenticates explicit baseline records and ignored raw output bytes before any successor materialization."
  - "Successor receipts repeat exhaustive maps so Plan 07-07 can finalize one workspace-wide stage rather than per-source results."
requirements-completed: [INV-06]
coverage:
  - id: D1
    description: Complete migration requests authenticate committed legacy chains and non-identity retained output bytes before staging.
    requirement: INV-06
    verification:
      - kind: integration
        ref: tests/test_career_source_custody.py#test_workspace_migration_request_authenticates_two_capture_non_identity_outputs_before_write
        status: pass
      - kind: integration
        ref: uv run --locked python scripts/run_pytest.py tests/test_career_source_custody.py tests/test_career_source_security.py -x
        status: pass
    human_judgment: false
  - id: D2
    description: One candidate-only stage creates exhaustive multi-source successor maps and accepts only byte-identical retry state.
    requirement: INV-06
    verification:
      - kind: integration
        ref: tests/test_career_source_custody.py#test_two_source_multi_chain_stage_has_exhaustive_non_authoritative_receipt
        status: pass
      - kind: integration
        ref: tests/test_career_source_custody.py#test_migration_staging_retry_accepts_only_byte_identical_request_derived_files
        status: pass
    human_judgment: false
duration: 5min
completed: 2026-08-30
status: complete
---

# Phase 07 Plan 06: Workspace-Complete Migration Staging Summary

**Explicit-baseline migration now authenticates every retained transformation output before staging one exhaustive, candidate-only successor graph for all private source chains.**

## Performance

- **Duration:** 5 min
- **Tasks:** 2/2
- **Files modified:** 3
- **Verification:** 74 source-aware synthetic custody/security tests passed; scoped Ruff check passed.

## Accomplishments

- Added strict Pydantic request, chain, capture, transformation, and receipt contracts that reject incomplete, duplicate, unsafe, or cross-chain mappings.
- Preflight now loads only the caller-supplied full baseline commit, validates immutable declaration bindings, and hashes every regular raw-vault retained output before writes.
- Staging creates deterministic successor captures, transformations, output manifests, and a complete receipt for all discovered chains without changing current pointers, refs, HEAD, or legacy/raw bytes.
- Partial stages can resume only if every existing staged semantic file is canonical and byte-identical to the same request; conflicts fail closed.

## Task Commits

1. **Task 1 RED: migration preflight regressions** — `d00b5a2`
2. **Task 1 GREEN: authenticate complete migration requests** — `bdd3b1a`
3. **Task 2: stage exhaustive migration successors** — `49bc638`

## Files Created/Modified

- `src/career_evidence_graph/domain/models.py` — strict workspace migration request, map, chain, and receipt contracts.
- `src/career_evidence_graph/career_sources.py` — committed-baseline discovery, raw-output authentication, exhaustive preflight, deterministic staging, and retry overlay validation.
- `tests/test_career_source_custody.py` — synthetic two-capture, non-identity output, two-source, exhaustive receipt, and retry-conflict regressions.

## Decisions Made

- Migration chain coverage is bidirectional: all committed legacy records must be requested, and every requested successor must derive from one committed predecessor.
- Raw-vault artifacts are addressed only through their output hash under the existing private boundary; no secondary parser, store, validator, transaction layer, or authority was introduced.
- Staging remains non-authoritative until Plan 07-07 constructs, verifies, and retains a dedicated Git snapshot.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Verification integrity] Used the checkout-source pytest runner**

- **Found during:** Tasks 1 and 2
- **Issue:** Direct `uv run --locked pytest` can import an installed package rather than this checkout's `src/` implementation.
- **Fix:** Used `uv run --locked python scripts/run_pytest.py` for every reported test result.
- **Files modified:** None
- **Verification:** 74 synthetic custody/security tests passed against checkout source.

---

**Total deviations:** 1 auto-fixed (Rule 2 verification integrity).

## TDD Gate Compliance

- Task 1 has separate RED (`d00b5a2`) and GREEN (`bdd3b1a`) commits.
- Task 2's RED regression was executed before implementation, but its test and GREEN changes are co-located in `49bc638`; do not treat this as a separate RED commit.

## Known Stubs

None.

## Next Phase Readiness

- Plan 07-07 can consume the staged receipt to create a deterministic temporary-index commit and retain it through the sole dedicated-ref CAS.
- The public harness contains only synthetic temporary Git workspace tests; no real private career repository, path, source material, or private-derived value was accessed or recorded.

## Self-Check: PASSED

- Confirmed the three scoped implementation/test files and this summary exist.
- Confirmed commits `d00b5a2`, `bdd3b1a`, and `49bc638` exist in Git history.
