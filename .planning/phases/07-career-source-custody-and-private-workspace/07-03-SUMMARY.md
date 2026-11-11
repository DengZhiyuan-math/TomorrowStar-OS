---
phase: 07-career-source-custody-and-private-workspace
plan: 03
subsystem: private-workspace-custody
tags: [python, cli, privacy, provenance, security, tdd]
requires:
  - phase: 07-02
    provides: Immutable candidate-only declaration, capture, and transformation lineage
provides:
  - Content-free career-source operator diagnostics and routine status
  - Public-only synthetic sentinel scanning independent of any private workspace
  - Full deterministic custody regression coverage with zero downstream authority side effects
affects: [phase-08-inventory-reconciliation, phase-09-career-audit]
actuals:
  tokens: 4051
  tasks: 3
  commits: 7
tech-stack:
  added: []
  patterns: [stable-redacted-status, public-only-synthetic-scanning, candidate-only-zero-side-effects]
key-files:
  created: []
  modified: [src/career_evidence_graph/career_sources.py, src/career_evidence_graph/cli.py, tests/test_career_source_custody.py, tests/test_career_source_security.py]
key-decisions:
  - "Public-tree checks accept only explicitly supplied public paths and synthetic sentinels; they never inspect a private workspace."
  - "Routine custody status retains one redacted contract before and after candidate-only materialization, and backup remains not-configured."
patterns-established:
  - "Career-source operations can record candidate-only lineage without creating inventory, graph, mastery, assessment, JD, gap, market-proof, or resume authority."
requirements-completed: [INV-01, INV-06, INV-07]
coverage:
  - id: D1
    description: "Career-source commands preserve an explicit private-workspace boundary, return content-free diagnostics, and keep unsupported formats fail-closed."
    requirement: INV-07
    verification:
      - kind: integration
        ref: "tests/test_career_source_security.py"
        status: pass
    human_judgment: false
  - id: D2
    description: "Synthetic public-tree and staged-input sentinel checks reject disclosure without reading any private workspace."
    requirement: INV-07
    verification:
      - kind: integration
        ref: "tests/test_career_source_security.py#test_public_tree_scan_rejects_raw_namespace_and_synthetic_derived_sentinel"
        status: pass
    human_judgment: false
  - id: D3
    description: "Declaration, capture, transformation, inspection, and verification remain candidate-only and create no later-phase authority."
    requirement: INV-01
    verification:
      - kind: integration
        ref: "tests/test_career_source_custody.py tests/test_career_source_security.py"
        status: pass
    human_judgment: false
duration: 37min
completed: 2026-08-30
status: complete
---

# Phase 07 Plan 03: Secure Career-Source Operator Surface Summary

**Candidate-only custody commands now enforce content-free diagnostics, public-tree independence, and zero downstream career-authority side effects.**

## Performance

- **Duration:** 37 min
- **Tasks:** completed
- **Files modified:** scoped source and regression-test files only

## Accomplishments

- Completed the explicit-workspace operator surface with deterministic text/JSON support and safe unsupported-format behavior for all other formats.
- Added public-only synthetic sentinel scanning and a consistent content-free status envelope, including an honest not-configured backup state.
- Proved the complete offline custody boundary: candidate-only operations cannot create acceptance, inventory, graph, mastery, assessment, market-proof, JD, gap, or resume authority.
- Recorded the external private-workspace prerequisite as approved without storing private workspace details or claiming a source-universe review or actual format inventory.

## Task Commits

1. **Task 07-03-01: Complete content-free operator commands and secure diagnostics** — `befaafc` (test), `cbaa1d6` (feat), `a138ac6` (fix).
2. **Task 07-03-02: Select the private repository and confirm actual source formats** — approved external prerequisite; no public repository commit and no private values recorded.
3. **Task 07-03-03: Prove complete phase security, non-authority, and public-tree independence** — `2e3289f` (test), `54ab4a7` (feat), `afac99d` (fix).

## Files Created/Modified

- `src/career_evidence_graph/career_sources.py` — public-only synthetic disclosure scan and stable safe-status contract.
- `src/career_evidence_graph/cli.py` — completed content-free career-source command routing from Task 1.
- `tests/test_career_source_security.py` — adversarial public-tree, status-contract, and zero-authority regressions.
- `tests/test_career_source_custody.py` — custody-flow status regression aligned with the redacted contract.

## Decisions Made

- Public disclosure scanning is explicit-path and synthetic-only; it cannot discover or derive expectations from a private workspace.
- The approved external boundary authorizes the generic workflow only. It does not establish any personal source review, source-universe completeness, actual-format inventory, or downstream authority.
- No adapter was added beyond deterministic text/JSON handling; other formats retain the stable unsupported-format outcome pending separately authorized work.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Kept the status envelope stable after candidate-only materialization**

- **Found during:** Task 07-03-03
- **Issue:** The empty and materialized workspace status paths emitted different safe-field sets, leaving a stale custody regression after the new stable-contract coverage.
- **Fix:** Preserved the same redacted status keys in both states and updated the synthetic custody expectation.
- **Files modified:** `src/career_evidence_graph/career_sources.py`, `tests/test_career_source_custody.py`
- **Verification:** Phase 7 custody/security suites, full offline suite, and Ruff gates.
- **Committed in:** `54ab4a7`, `afac99d`

**Total deviations:** 1 auto-fixed (Rule 1)

## Issues Encountered

The full offline suite exceeded the interactive command window, so its output was buffered to a temporary local log while it completed. The final full-suite result and all Ruff gates passed.

## User Setup Required

The external private-workspace prerequisite is approved. No private value, source material, source-universe review, or actual-format inventory was recorded in this public repository.

## Next Phase Readiness

Phase 8 may consume only a user-supplied candidate-only declaration and immutable lineage through the explicit private-workspace runtime boundary. Inventory acceptance and sealing, graph facts, mastery, assessments, JD authority, and resume authority remain absent.

## Self-Check: PASSED

- Confirmed the scoped source and test files exist.
- Confirmed all Task 1 and Task 3 commits listed above exist.
- Confirmed the full offline suite and repository-wide Ruff checks pass.
