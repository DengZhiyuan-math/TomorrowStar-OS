---
phase: 03-artifact-aware-grill-me-and-attribution-workflow
plan: "12"
subsystem: audit-storage
tags: [python, posix, dir-fd, symlink-containment, hard-link-containment]
requires:
  - phase: 03-11
    provides: installed CLI authority from the checkout source
provides:
  - Descriptor-held audit root, lock, audit directory, and custody-file operations
  - Fail-closed post-open root/audit rebind and hard-link alias regressions
affects: [03-13, phase-verification, audit-storage]
actuals:
  tokens: 8118
  tasks: 2
  commits: 2
tech-stack:
  added: []
  patterns: [O_DIRECTORY and O_NOFOLLOW directory sessions, dir_fd publication, single-link file admission]
key-files:
  created: [03-12-SUMMARY.md]
  modified: [src/career_evidence_graph/audit/store.py, tests/test_audit_storage_regressions.py]
decisions:
  - "Audit custody authority is a held directory descriptor, never a validated pathname reused for production I/O."
  - "Existing locks and custody files must be regular, current-user-owned, safe-mode, and single-link before reads or mutation."
requirements-addressed: [AUD-01, AUD-02, AUD-05]
requirements-completed: []
coverage:
  - id: D1
    description: "Post-open audit-root replacement cannot create external locks or custody files."
    requirement: AUD-01
    verification:
      - kind: integration
        ref: tests/test_audit_storage_regressions.py#test_audit_root_swap_after_descriptor_open_never_writes_external
        status: pass
    human_judgment: false
  - id: D2
    description: "Hard-linked lock and custody aliases fail before external inode mutation."
    requirement: AUD-05
    verification:
      - kind: integration
        ref: tests/test_audit_storage_regressions.py#test_external_hard_link_aliases_fail_closed_without_external_mutation
        status: pass
    human_judgment: false
  - id: D3
    description: "Normal storage, recovery, replay, review, and audit E2E flows retain their contracts under descriptor custody."
    requirement: AUD-02
    verification:
      - kind: integration
        ref: uv run --locked pytest -q tests/test_audit_storage_regressions.py tests/test_audit_store.py tests/test_audit_inspection.py tests/test_audit_gap_e2e.py
        status: pass
    human_judgment: false
duration: 32min
completed: 2026-08-26
status: complete
---

# Phase 03 Plan 12: Descriptor-Anchored Audit Storage Summary

**Audit custody now holds verified POSIX directory descriptors from lock acquisition through recovery, read, transaction, and atomic publication.**

## Accomplishments

- Replaced path-based audit-root, lock, per-audit, read, journal recovery, and publication authority with `O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC` descriptor sessions and `dir_fd` operations.
- Added deterministic post-open root and audit-directory replacement coverage, proving external trees are unchanged.
- Rejected hard-linked lock and custody aliases before file reads, metadata changes, or replacement, while retaining CAS, replay, recovery, and review behavior.

## Task Commits

1. **Task 1: Hold the verified root through the first audit lock** - `880899a` (test)
2. **Task 2: Keep reads, recovery, transactions, and publication on held directory descriptors** - `f8b3519` (fix)

## Verification

- Targeted root-swap, hard-link, and linked-root tests: **3 passed, 8 deselected**.
- Affected storage, inspection, review, recovery, and E2E suite: **23 passed**.
- Ruff check and format check for modified files: passed.
- Full suite: **237 passed, 1 failed, 1 deselected**. The only failure is the intentionally stale Phase 3 gap-probe inventory; Plan 03-13 owns measuring and updating it after all new probes exist.

## Deviations from Plan

None - plan executed as specified.

## Known Stubs

None.

## Next Phase Readiness

03-13 can now use the installed public CLI to cross-prove descriptor custody and update the exact gap-probe inventory. Fresh independent Phase 3 verification remains required before requirements are completed.

## Self-Check: PASSED

- `src/career_evidence_graph/audit/store.py` and `tests/test_audit_storage_regressions.py` exist.
- Task commits `880899a` and `f8b3519` exist.
