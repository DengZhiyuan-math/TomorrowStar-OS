---
phase: 03-artifact-aware-grill-me-and-attribution-workflow
plan: "05"
subsystem: audit-workflow
tags: [python, pydantic, offline, event-chain, locking, compare-and-swap, recovery]
requires: [03-04]
provides: [strict-event-custody, per-audit-locking, replay-first-cas, publication-recovery]
affects: [audit-cli, audit-store, phase-03-verification]
tech-stack:
  added: []
  patterns: [canonical-event-hashes, immutable-action-receipts, lock-scoped-read-versioned, journal-recovery]
key-files:
  created: [tests/test_audit_event_models.py, tests/test_audit_storage_regressions.py]
  modified:
    - src/career_evidence_graph/audit/models.py
    - src/career_evidence_graph/audit/store.py
    - src/career_evidence_graph/audit/workflow.py
    - src/career_evidence_graph/cli.py
    - tests/test_audit_cli.py
    - tests/test_audit_store.py
key-decisions:
  - "An accepted action result is the only replay authority and is anchored to a strict event hash."
  - "Identity and semantic digest resolve before compare-and-swap checks, so exact replay is safe after later writes."
  - "A stable 0600 advisory lock and recovery journal protect every audit custody read and write."
actuals:
  tokens: 9048
  tasks: 3
  commits: 5
requirements-completed: [AUD-01, AUD-02, AUD-05]
coverage:
  - id: D1
    description: Strict complete audit event and accepted-result custody contracts.
    requirement: AUD-01
    verification:
      - kind: unit
        ref: tests/test_audit_event_models.py
        status: pass
    human_judgment: false
  - id: D2
    description: Locked chain validation and journal-backed publication recovery.
    requirement: AUD-02
    verification:
      - kind: integration
        ref: tests/test_audit_storage_regressions.py
        status: pass
    human_judgment: false
  - id: D3
    description: Replay-first CLI compare-and-swap mutations with deterministic output.
    requirement: AUD-05
    verification:
      - kind: e2e
        ref: tests/test_audit_cli.py#test_exact_action_replay_is_byte_identical_and_stale_new_action_fails
        status: pass
    human_judgment: false
metrics:
  duration: "31 min"
  completed: "2026-08-26"
status: complete
---

# Phase 3 Plan 5: Audit custody and replay transaction Summary

The audit workflow now persists strict hash-linked event history, immutable replay receipts, per-audit locked compare-and-swap mutations, and journal-backed recovery without new dependencies.

## Completed Tasks

1. Added red-first event custody contracts, strict event/genesis/hash validation, and the atomic start/answer CLI tracer.
2. Verified complete history and accepted-result linkage fail closed when records are deleted or detached.
3. Routed CLI mutations through replay-first transactions and added durable recovery for interrupted snapshot/event/receipt publication.

## Verification

- Targeted replay/CAS coverage: 1 passed.
- Audit storage, CLI, and conclusion coverage: 13 passed.
- Full locked offline suite: 208 passed, 1 deselected.
- `ruff check .` and `ruff format --check .`: passed.

## Task Commits

1. Task 1 red evidence: `7fdaa9e` — `test(03-05): add failing audit event custody contract`
2. Task 1 implementation: `1c9b4ba` — `feat(03-05): add atomic audit event custody tracer`
3. Task 2: `bb656b3` — `test(03-05): cover full audit custody validation`
4. Task 3 replay/CAS: `fcc67a7` — `test(03-05): verify replay-first audit compare-and-swap`
5. Task 3 recovery: `79aa5c2` — `fix(03-05): recover interrupted audit publication`

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Durability] Added write-ahead recovery after the tracer exposed a split-publication window.**
- **Found during:** Task 3
- **Issue:** Sequential atomic replacements alone could leave snapshot, event history, and accepted results out of sync after interruption.
- **Fix:** Added a fsynced publication journal that completes the declared replacement set before any locked read validates custody.
- **Files modified:** `src/career_evidence_graph/audit/store.py`, `tests/test_audit_storage_regressions.py`
- **Commit:** `79aa5c2`

## Self-Check: PASSED

- All eight declared source/test artifacts exist.
- Commits `7fdaa9e`, `1c9b4ba`, `bb656b3`, `fcc67a7`, and `79aa5c2` exist in Git history.
