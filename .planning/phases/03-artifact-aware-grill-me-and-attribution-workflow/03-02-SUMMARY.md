---
phase: 03-artifact-aware-grill-me-and-attribution-workflow
plan: "02"
subsystem: audit
tags: [python, pydantic, offline, attribution, concurrency]
requires: [03-01]
provides: [deterministic-question-coverage, attribution-rounds, assistance-migration]
affects: [phase-03, phase-04-calibration]
tech-stack:
  added: []
  patterns: [hard-to-simple ladders, optimistic snapshot hashes, provider-neutral assistance]
key-files:
  created: [tests/test_audit_policy.py, tests/test_audit_attribution.py, tests/test_assistance_migration.py]
  modified: [src/career_evidence_graph/audit/models.py, src/career_evidence_graph/audit/workflow.py, src/career_evidence_graph/domain/models.py]
key-decisions:
  - "Question coverage is deterministic and Contribution-bounded: one same-level follow-up then downward difficulty descent."
  - "Responsibility and assistance remain separate rounds; conflicts retain artifact and user claims as unresolved."
  - "Legacy codex_assisted is read-compatible while new audit values use coding-agent-assisted."
metrics:
  duration: "~18 min"
  completed: 2026-08-26
status: complete
actuals:
  tokens: 18200
  tasks: 2
  commits: 4
---

# Phase 3 Plan 2: Deterministic questioning and truth-preserving attribution

The audit now resumes through deterministic relevant-area coverage, hard-to-simple capability probes, voluntary self-assessment skips, optimistic concurrency checks, and separate ownership/assistance attribution with legacy provenance compatibility.

## Accomplishments

- Added stable question metadata (`area_id`, difficulty, inspection reference, follow-up count) and coverage envelopes preserving skipped self-ratings verbatim.
- Implemented one same-level incomplete-answer follow-up, downward descent for another miss or `不知道`, and deterministic progression through debugging, operation, responsibility, and assistance.
- Added action IDs and expected snapshot hashes for idempotency and optimistic stale-write rejection.
- Added ownership and assistance rounds, immutable unresolved attribution conflicts, coding-agent role probes, and canonical assistance migration helpers.
- Preserved sealed STOA fixture bytes and accepted legacy `codex_assisted` domain records without rewriting them.

## Verification

- `UV_CACHE_DIR=/tmp/career-evidence-uv-cache uv run --locked python scripts/run_pytest.py -q` — 182 passed, 1 deselected.
- `UV_CACHE_DIR=/tmp/career-evidence-uv-cache uv run --locked ruff check src tests` — passed.

## Task Commits

1. `08372e2` — test(03-02): add focused audit policy coverage
2. `7b08135` — feat(03-02): enforce deterministic audit coverage policy
3. `3cf7ba4` — feat(03-02): preserve attribution and assistance provenance
4. `2d495a9` — test(03-02): cover separated attribution rounds

## Deviations from Plan

None — implementation stayed within the Phase 3 offline, provider-neutral, non-numeric boundary.

## Self-Check: PASSED

- Summary file exists at the planned path.
- All four task commits are present in Git history.
- Focused and full offline verification plus Ruff checks pass.
