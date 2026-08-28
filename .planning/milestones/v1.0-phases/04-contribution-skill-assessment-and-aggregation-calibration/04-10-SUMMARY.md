---
phase: 04-contribution-skill-assessment-and-aggregation-calibration
plan: "10"
subsystem: assessment-custody
tags: [python, pydantic, audit-store, reassessment, regression-tests]
requires:
  - phase: 04-09
    provides: reassessment lineage and assessment-version custody boundary
provides:
  - replay-disabled reassessment audit consumption
  - complete canonical caller-proposal equality
  - dual-store service and CLI mutation regressions
affects: [independent-verification, phase-04-promotion]
actuals:
  tokens: 3573
  tasks: 2
  commits: 4
tech-stack:
  added: []
  patterns:
    - Existing AuditStore read authority is preceded by a no-write lstat presence probe for reassessment only.
    - Rejected reassessment assertions compare assessment bytes and the entire audit-tree snapshot.
key-files:
  created:
    - .planning/phases/04-contribution-skill-assessment-and-aggregation-calibration/04-10-SUMMARY.md
  modified:
    - src/career_evidence_graph/assessment.py
    - tests/test_assessment_admission.py
    - tests/test_assessment_cli.py
    - .planning/phases/04-contribution-skill-assessment-and-aggregation-calibration/04-VALIDATION.md
key-decisions:
  - Reassessment consumes only an existing audit in the caller workspace; it cannot replay a detached or missing audit.
  - Complete validated Pydantic-model equality is the caller-proposal custody check.
completion_authority: independent_verification
requirements-addressed: [ASS-01, AGG-01, AGG-03]
requirements-completed: []
coverage:
  - id: D1
    description: Reassessment rejects detached, invalid, stale, and forged inputs without mutating either persistence root.
    requirement: ASS-01
    verification:
      - kind: integration
        ref: tests/test_assessment_admission.py and tests/test_assessment_cli.py reassessment matrix
        status: pass
    human_judgment: false
  - id: D2
    description: A valid pre-existing audit appends one immutable assessment version while leaving the audit tree unchanged.
    requirement: AGG-01
    verification:
      - kind: integration
        ref: tests/test_assessment_admission.py and tests/test_assessment_cli.py valid reassessment controls
        status: pass
    human_judgment: false
  - id: D3
    description: Phase 4 shared promotion remains withheld until fresh code, security, and goal verification after this summary.
    requirement: AGG-03
    verification: []
    human_judgment: true
    rationale: Independent verification authority is explicitly required by this gap-closure plan.
duration: 9min
completed: 2026-08-28
status: complete
---

# Phase 04 Plan 10: Reassessment Custody Remediation Summary

**Reassessment now reads only an existing completed, confirmed audit and leaves both audit and assessment stores unchanged on every rejected request.**

## Performance

- **Started:** 2026-08-28T12:16:50Z
- **Tasks:** 2/2
- **Files modified:** 4; one summary created
- **Measured implementation revision:** `cc2b67ab9358a16e73c722bcb40f96eeadb08974`

## Accomplishments

- Added a defaulted internal `allow_replay` switch: normal assessment/calibration retain replay, while reassessment probes and reads a pre-existing audit without creating any audit artifact.
- Replaced sampled caller-field checks with complete `ContributionSkillAssessment` equality against the canonical model derived from the persisted audit.
- Added service and CLI regression coverage for detached, missing, corrupt, incomplete, unconfirmed, custody-invalid, stale, and caller-mismatch requests, plus append-only valid controls.
- Recorded focused, full offline, lint, and format results in `04-VALIDATION.md` without changing phase-status artifacts.

## Task Commits

1. **Task 1 RED:** `8e15fe9` — detached-audit mutation regressions.
2. **Task 1 GREEN:** `4136f4c` — pre-existing reassessment audit requirement and whole-model equality.
3. **Task 2:** `cc2b67a` — dual-store invalid-state, stale-first, full caller-mismatch, and valid-control coverage.
4. **Task 2 evidence:** `7bee805` — measured validation record.

## Validation

- Focused reassessment matrix: **29 passed, 27 deselected**.
- Full offline pytest suite: **exited 0**.
- `ruff check .` and `ruff format --check .`: **both exited 0**; 57 files already formatted.

## Decisions Made

- Missing later-audit custody is fail-closed. Reassessment neither replays nor repairs it; no staging, transaction, rollback, new authority, parser, schema, model/provider, scoring, or CLI behavior was added.
- `AuditStore.read` remains the sole persisted-snapshot validator. The `lstat` call is only a read-only absence probe that prevents `read` from creating a root for a missing path.

## Deviations from Plan

None - the locked minimal remediation was implemented without scope expansion.

## Known Stubs

None.

## Promotion Boundary

This execution did not edit or promote `.planning/STATE.md`, `.planning/ROADMAP.md`, or `.planning/REQUIREMENTS.md`. It preserved all user-owned untracked files. The plan is complete as an independently verified gap-closure implementation, but Phase 4 and requirements ASS-01, AGG-01, and AGG-03 remain unpromoted. Fresh code review, security review, and goal verification must run on a commit strictly after this 04-10 SUMMARY before any shared status promotion.

## Self-Check: PASSED

- All five owned artifacts exist.
- Task commits `8e15fe9`, `4136f4c`, `cc2b67a`, and `7bee805` exist in Git history.
