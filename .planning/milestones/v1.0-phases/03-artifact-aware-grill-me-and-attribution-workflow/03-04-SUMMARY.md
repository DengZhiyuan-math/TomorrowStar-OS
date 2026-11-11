---
phase: 03-artifact-aware-grill-me-and-attribution-workflow
plan: "04"
subsystem: audit-workflow
tags: [python, pydantic, offline, lifecycle, attribution, conclusion-review]
requires: [03-03]
provides: [fail-closed-lifecycle, bilingual-attribution, effective-conclusion-custody]
affects: [audit-cli, audit-store]
tech-stack:
  added: []
  patterns: [pure-transition-guards, canonical-json-hashes, conservative-bilingual-allowlists]
key-files:
  created: [tests/test_audit_workflow_regressions.py]
  modified:
    - src/career_evidence_graph/audit/models.py
    - src/career_evidence_graph/audit/workflow.py
    - src/career_evidence_graph/cli.py
    - tests/test_audit_cli.py
    - tests/test_audit_conclusion.py
decisions:
  - "Reviewing is an explicit audit lifecycle state; only reviewing accepts conclusion actions."
  - "Artifact references remain documentary context while area capability basis contains only that area's answers."
  - "Original proposal custody is immutable; effective conclusion hashes advance with reviewed canonical state."
metrics:
  duration: "8m 10s"
  completed: "2026-08-26"
status: complete
actuals:
  tokens: 8738
  tasks: 2
  commits: 3
---

# Phase 3 Plan 4: Workflow lifecycle and conclusion custody Summary

The offline audit workflow now rejects malformed references and invalid lifecycle actions predictably, treats supported English and Chinese attribution answers equivalently, and keeps immutable proposal custody separate from the reviewed effective conclusion.

## Completed Tasks

1. Enforced active/paused/reviewing/terminal transition boundaries, controlled fixture-reference failures, documentary-only context, and structured CLI audit errors.
2. Added original/effective conclusion hash custody, edit before/after lineage, stale effective-hash rejection, and canonical review-state regression coverage.

## Verification

- Targeted lifecycle/reference/attribution/basis regression selection: 4 passed.
- Audit workflow, conclusion, CLI, policy, attribution, and inspection tests: 16 passed.
- Full locked offline suite: 201 passed, 1 deselected.
- `ruff check .` and `ruff format --check .`: passed.

## Commits

1. `06e9ea0` — `feat(03-04): enforce audit lifecycle boundaries`
2. `5142e87` — `test(03-04): cover effective conclusion custody`
3. `87b2a92` — `test(03-04): verify structured audit failures`

## Deviations from Plan

None - plan behavior was implemented within its declared workflow, model, CLI, and test scope. The effective-conclusion implementation landed with Task 1's shared workflow/model changes because those files also own the lifecycle contract; Task 2 added focused custody and stale-hash regressions.

## Self-Check: PASSED

- All declared source and regression-test files exist.
- Commits `06e9ea0`, `5142e87`, and `87b2a92` exist in Git history.
