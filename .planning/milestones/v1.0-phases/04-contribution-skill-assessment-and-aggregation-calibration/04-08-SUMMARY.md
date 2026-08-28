---
phase: 04-contribution-skill-assessment-and-aggregation-calibration
plan: "08"
subsystem: assessment-aggregation-authority
tags: [python, pydantic, aggregation, authority-partition, calibration, offline]
requires:
  - phase: 04-contribution-skill-assessment-and-aggregation-calibration
    provides: immutable assessment review lineage and tamper-evident calibration custody
provides:
  - authority-partitioned same-Skill aggregation and promotion
  - calibration-only CLI disposition for excluded derived records
  - executable five-gap regression matrix on the final revision
affects: [independent-verification, security-review, phase-05-jd-usefulness]
completion_authority: independent_verification
actuals:
  tokens: 7878
  tasks: 2
  commits: 5
tech-stack:
  added: []
  patterns:
    - aggregate exact Skills separately for each validated source authority
    - require immutable substantive-review lineage only for reviewed-user-truth promotion, never for routine D-05 baselines
key-files:
  created: []
  modified:
    - src/career_evidence_graph/assessment.py
    - src/career_evidence_graph/cli.py
    - tests/test_anchor_promotion.py
    - tests/test_skill_aggregation.py
    - tests/test_assessment_cli.py
    - .planning/phases/04-contribution-skill-assessment-and-aggregation-calibration/04-VALIDATION.md
key-decisions:
  - "A promotion decision is constrained to one exact Skill and one source-authority partition; mixed authority fails closed."
  - "Routine audit-verified D-05 baselines remain eligible without substantive review, while every reviewed-user-truth promotion support must be reviewed and retained in immutable lineage."
patterns-established:
  - "Derived-counterfactual records remain separately inspectable calibration evidence and never lend their authority to user-facing mastery."
requirements-addressed: [AGG-03]
requirements-completed: []
coverage:
  - id: D1
    description: "Mixed derived and reviewed support cannot promote a reviewed-user-truth Skill result."
    requirement: AGG-03
    verification:
      - kind: integration
        ref: tests/test_anchor_promotion.py::test_mixed_authority_promotion_cannot_elevate_reviewed_user_truth
        status: pass
    human_judgment: false
  - id: D2
    description: "One Evidence reference supports distinct Skills independently while repeated same-Skill support remains neutral."
    requirement: AGG-03
    verification:
      - kind: integration
        ref: tests/test_skill_aggregation.py::test_same_evidence_keeps_two_reviewed_user_truth_skills_independent
        status: pass
    human_judgment: false
  - id: D3
    description: "The final matrix maps every Phase 4 gap to a passing deterministic regression without claiming external effectiveness."
    requirement: AGG-03
    verification:
      - kind: other
        ref: .planning/phases/04-contribution-skill-assessment-and-aggregation-calibration/04-VALIDATION.md
        status: pass
    human_judgment: true
    rationale: "Fresh independent verification and the required security authority remain the completion authority for this gap closure."
duration: 12min
completed: 2026-08-28
status: complete
---

# Phase 04 Plan 08: Authority-Partitioned Aggregation Summary

**Same-Skill aggregation now partitions reviewed user truth from derived calibration evidence, preventing synthetic support from elevating or relabeling user mastery.**

## Performance

- **Duration:** 12 min
- **Started:** 2026-08-28T08:38:45Z
- **Completed:** 2026-08-28T08:50:36Z
- **Tasks:** 2/2
- **Files modified:** 6

## Accomplishments

- Rejected mixed-authority promotion decisions before any user-truth result is emitted, while retaining pure derived calibration promotion as explicitly derived.
- Required audit-verified, substantively reviewed, immutable AssessmentRun lineage for every cited reviewed-user-truth promotion support without overconstraining routine D-05 baselines.
- Preserved independent cross-Skill Evidence reuse, made excluded derived records visible as calibration-only, and recorded measured CR-01 through CR-05 regressions.

## Task Commits

1. **Task 1 RED: Fail closed on one mixed-authority next-anchor promotion** — `ef8e67a` (test)
2. **Task 1 control coverage: Preserve D-05 and derived-only boundaries** — `149f6bb` (test)
3. **Task 1 GREEN: Partition aggregation authority** — `d810087` (feat)
4. **Task 2 regression: Preserve cross-Skill Evidence semantics** — `b4a7622` (test)
5. **Task 2 verification: Measure final aggregation gaps** — `78b6286` (test)

## Files Created/Modified

- `src/career_evidence_graph/assessment.py` — partitions aggregates and validates authority-bound promotion lineage.
- `src/career_evidence_graph/cli.py` — labels excluded derived records as calibration-only evidence.
- `tests/test_anchor_promotion.py` — covers mixed, reviewed-only, routine-baseline, and derived-only promotion outcomes.
- `tests/test_skill_aggregation.py` — proves one Evidence reference can independently support separate reviewed-user-truth Skills.
- `tests/test_assessment_cli.py` — checks the explicit aggregate calibration-only disposition.
- `04-VALIDATION.md` — replaces insufficient prior mappings with the measured five-gap matrix and limits.

## Decisions Made

- Aggregation partitions on the exact `(skill_id, authority_label)` pair; any promotion support that crosses those partitions fails closed.
- Only a reviewed-user-truth promotion requires substantive review and immutable lineage; ordinary unflagged audit-verified inputs retain the D-05 baseline path.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Verification defect] Corrected newly introduced Ruff line-length violations**
- **Found during:** Task 1 GREEN verification
- **Issue:** Two aggregation lines exceeded the repository's 100-character limit.
- **Fix:** Wrapped the comprehension and workflow error without changing behavior.
- **Files modified:** `src/career_evidence_graph/assessment.py`
- **Verification:** Focused promotion regressions and scoped Ruff checks passed.
- **Committed in:** `d810087`

**2. [Rule 3 - Blocking quality gate] Formatted the related aggregate CLI test file**
- **Found during:** Task 2 full Ruff format check
- **Issue:** Existing formatting in `tests/test_assessment_cli.py` blocked the plan-required repository-wide format gate.
- **Fix:** Applied Ruff's mechanical formatter and added the planned calibration-only CLI disposition regression in the same focused file.
- **Files modified:** `tests/test_assessment_cli.py`
- **Verification:** Focused aggregate CLI test, five-file matrix, full offline suite, Ruff check, and Ruff format check passed.
- **Committed in:** `78b6286`

**Total deviations:** 2 auto-fixed (Rule 1 and Rule 3)

## Verification

- Five-file blocker matrix: **59 passed in 15.07s**.
- Full offline suite: exited 0.
- `ruff check .` and `ruff format --check .`: both exited 0.
- Active calibration history remains unchanged and still names `policy-04-conservative-70`.

## Known Stubs

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

The remediation plan is complete, but it does **not** complete AGG-03, Phase 04, or the milestone. Hand this unchanged revision to fresh independent verification and the required security authority before any shared planning status is promoted.

## Self-Check: PASSED

- All six modified implementation, test, validation artifacts and this SUMMARY exist.
- Task commits `ef8e67a`, `149f6bb`, `d810087`, `b4a7622`, and `78b6286` exist in repository history.
