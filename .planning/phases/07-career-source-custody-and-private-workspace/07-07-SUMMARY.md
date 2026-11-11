---
phase: 07-career-source-custody-and-private-workspace
plan: 07
subsystem: custody
tags: [git, private-workspace, cas, migration, synthetic-tests]
requires:
  - phase: 07-06
    provides: exhaustive request-authenticated migration staging without Git authority
provides:
  - deterministic temporary-index migration commits retained only by refs/career-evidence/custody
  - explicit expected-old Git ref CAS with interruption-safe retry semantics
  - temporal receipt verification for authenticated same-source post-migration recaptures
affects: [phase-07-verification, private-workspace-custody, migration-receipts]
actuals:
  tokens: 9782.75
  tasks: 2
  commits: 4
tech-stack:
  added: []
  patterns:
    - temporary Git index plus commit-tree produces an unreachable deterministic commit without moving HEAD
    - dedicated ref retention uses Git expected-old update-ref CAS only
    - migration receipts authenticate temporal same-source descendant chains
key-files:
  created: []
  modified:
    - src/career_evidence_graph/career_sources.py
    - src/career_evidence_graph/cli.py
    - tests/test_career_source_custody.py
key-decisions:
  - "refs/career-evidence/custody is the sole non-configurable migration retention ref."
  - "Standalone verification remains anchored solely to a caller-supplied full commit OID."
  - "A post-CAS retry accepts only the exact deterministic commit proven by parent, paths, metadata, receipt, pointer, and explicit verification checks."
patterns-established:
  - "Complete workspace mutations are synchronous, single-process operations; detected drift fails closed without a phase-local lock."
  - "Later current heads must reach the receipt successor through a fully authenticated same-source predecessor chain."
requirements-completed: [INV-06]
coverage:
  - id: D1
    description: Dedicated retention-ref CAS finalizes verified complete migration snapshots without ambient Git authority.
    requirement: INV-06
    verification:
      - kind: integration
        ref: "uv run --locked python scripts/run_pytest.py tests/test_career_source_custody.py -k 'retention_ref or ref_cas or finalization_interrupt or adjudicate_complete_workspace' -x"
        status: pass
    human_judgment: false
  - id: D2
    description: Migration receipts accept only authenticated same-source descendant heads and reject unrelated or skipped chains.
    requirement: INV-06
    verification:
      - kind: integration
        ref: "uv run --locked python scripts/run_pytest.py tests/test_career_source_custody.py -k 'migration_head_temporal or post_migration_recapture or descendant_chain' -x"
        status: pass
    human_judgment: false
duration: 10m
completed: 2026-08-30
status: complete
---

# Phase 07 Plan 07: Retention CAS and Temporal Receipt Summary

**A deterministic, verified private migration snapshot is retained only through the dedicated Git CAS ref, while later same-source recaptures remain independently verifiable through immutable receipt ancestry.**

## Performance

- **Duration:** 10m
- **Started:** 2026-08-30T22:23:35Z
- **Completed:** 2026-08-30T22:33:56Z
- **Tasks:** 2/2
- **Files modified:** 3

## Accomplishments

- Added `career-source adjudicate`, requiring an explicit workspace baseline and expected retention-ref OID, and constructing a deterministic child commit through a temporary Git index without touching HEAD.
- Retained successful migrations only by `refs/career-evidence/custody` with expected-old `git update-ref` CAS; stale refs and pre-CAS failures expose no candidate OID and restore attempt-owned pointers safely.
- Added idempotent post-CAS retry recognition and temporal migration receipt checks that allow authenticated same-source children/grandchildren but reject unrelated and skipped chains.

## Task Commits

1. **Task 1: Finalize, verify, and retain the complete migration with a dedicated ref CAS** - `14dbd76` (test RED), `195ecc4` (feature)
2. **Task 2: Verify migration heads temporally across real later recaptures** - `857d789` (feature)
3. **Rule 1 correction: post-CAS emission interruption retry** - `f736e74` (fix)

## Files Created/Modified

- `src/career_evidence_graph/career_sources.py` - deterministic temporary-index finalization, dedicated-ref CAS, strict retry identity validation, and temporal receipt ancestry verification.
- `src/career_evidence_graph/cli.py` - explicit `career-source adjudicate` route.
- `tests/test_career_source_custody.py` - synthetic-only CAS, interruption, CLI, and temporal recapture regressions.

## Decisions Made

- Kept `refs/career-evidence/custody` constant and non-configurable; no branch, tag, HEAD, or alternate ref is accepted as authority.
- Used the existing explicit commit verifier after all mutation/ref steps; the ref is retention metadata only, never a standalone verification anchor.
- Treated cross-process changes as unsupported workspace drift and restored only pointers that still held this attempt's exact successor bytes.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Added post-CAS interruption retry recognition**
- **Found during:** Task 1
- **Issue:** The initial finalizer covered interruption before ref update but did not model interruption after a successful CAS and before result emission.
- **Fix:** Added a deterministic retry proof that checks commit parent, allowed changed paths, fixed metadata, receipt bytes, successor pointers, and explicit full-OID verification before returning the retained OID.
- **Files modified:** `src/career_evidence_graph/career_sources.py`, `tests/test_career_source_custody.py`
- **Verification:** Source-aware post-CAS interruption regression and full custody suite passed.
- **Committed in:** `f736e74`

### Verification adjustment

The literal plan command `uv run --locked pytest` imports a stale installed package in this checkout. Following the established Phase 07 source-selection convention, all reported pytest evidence used `uv run --locked python scripts/run_pytest.py` to execute the checkout's `src/` code.

**Total deviations:** 1 auto-fixed bug; one source-selection verification adjustment.

## Issues Encountered

- Direct pytest imported an installed package lacking the current custody models; the existing source-aware wrapper resolved it without changing product behavior.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- The dedicated retention ref and receipt ancestry checks are ready for fresh independent Phase 07 verification.
- No real career source, private workspace identifier, path, hash, or content was accessed or recorded; all tests used temporary synthetic Git repositories.

## Self-Check: PASSED

- Confirmed all three declared source/test files and this summary exist.
- Confirmed task commits `14dbd76`, `195ecc4`, `857d789`, and `f736e74` exist in Git history.

---
*Phase: 07-career-source-custody-and-private-workspace*
*Completed: 2026-08-30*
