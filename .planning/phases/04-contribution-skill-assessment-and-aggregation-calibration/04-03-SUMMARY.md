---
phase: 04-contribution-skill-assessment-and-aggregation-calibration
plan: "03"
subsystem: assessment
tags: [python, pydantic, admission, review-lineage, cli, calibration]
requires:
  - phase: 04-contribution-skill-assessment-and-aggregation-calibration
    provides: normalized, anchor-grounded assessment proposals with policy-bearing aggregation
provides:
  - fail-closed confidence admission independent from mastery, centrality, and confidence values
  - D-10-complete reviewer confirmations and corrections with hash-linked effective values
  - immutable assessment versions for later evidence and safe pending-review CLI inspection
affects: [phase-04-calibration, phase-05-jd-usefulness]
actuals:
  tokens: 10561
  tasks: 2
  commits: 4
tech-stack:
  added: []
  patterns:
    - policy admission is a separate immutable decision and non-admitted records never produce an aggregate
    - assessment reviews replace a complete validated judgment while preserving original proposals and version history
key-files:
  created:
    - tests/test_assessment_admission.py
  modified:
    - src/career_evidence_graph/domain/models.py
    - src/career_evidence_graph/assessment.py
    - src/career_evidence_graph/cli.py
    - tests/test_assessment_cli.py
key-decisions:
  - "Only D-10-complete reviews may admit low-confidence, disputed, unresolved, or self-assessed proposals; their original source status remains inspectable."
  - "Assessment correction and reassessment are hash-linked immutable lineages, while admission remains a separate policy decision."
patterns-established:
  - "Validate a full Pydantic replacement before treating reviewer input as authoritative; never use model_copy(update=...) for authority-changing records."
  - "Pending CLI output exposes safe provenance and required checks, never raw interview answers."
requirements-completed: [ASS-04]
coverage:
  - id: D1
    description: "Integer-exact candidate-policy admission keeps flagged proposals visible but outside aggregation without changing any of the three judgments."
    requirement: "ASS-04"
    verification:
      - kind: unit
        ref: "tests/test_assessment_admission.py#test_admission_boundaries_are_integer_exact_and_never_mutate_judgments"
        status: pass
    human_judgment: false
  - id: D2
    description: "Substantive review, correction, insufficiency, reassessment, and CLI inspection preserve source provenance and immutable hash-linked lineage."
    requirement: "ASS-04"
    verification:
      - kind: integration
        ref: "uv run --offline --locked python scripts/run_pytest.py -q tests/test_assessment_admission.py tests/test_assessment_cli.py tests/test_audit_conclusion.py"
        status: pass
    human_judgment: false
duration: 10min
completed: 2026-08-27
status: complete
---

# Phase 04 Plan 03: Confidence Admission and Immutable Review Summary

**Fail-closed confidence admission keeps uncertain capability proposals intact while substantive reviewer decisions and later evidence create hash-linked, immutable assessment lineage.**

## Performance

- **Duration:** 10 min
- **Started:** 2026-08-27T21:08:13+02:00
- **Completed:** 2026-08-27T21:17:54+02:00
- **Tasks:** 2
- **Files modified:** 5

## Accomplishments

- Added policy-reasoned, integer-exact admission that leaves demonstrated mastery, Skill centrality, and evidence confidence untouched; pending and unverified candidates cannot enter aggregates.
- Preserved `self-assessed-unverified` origin plus disputed or unresolved attribution/assistance states until a D-10-complete review records every required acknowledgment.
- Added full replacement validation, reviewer/reason provenance, contiguous before/after hashes, immutable later-evidence versions, and pending/review CLI commands with redacted error behavior.

## Task Commits

1. **Task 1: Separate scoring from fail-closed confidence admission** — `2e7cb5d` (test), `21a1733` (feat)
2. **Task 2: Preserve substantive corrections, confirmations, and later versions** — `9acfc4c` (test), `ff10045` (feat)

## Files Created/Modified

- `src/career_evidence_graph/domain/models.py` — admission status, review, and immutable version contracts.
- `src/career_evidence_graph/assessment.py` — strict admission, review, lineage, reassessment, and pending-record workflow.
- `src/career_evidence_graph/cli.py` — safe assessment pending and review commands.
- `tests/test_assessment_admission.py` and `tests/test_assessment_cli.py` — boundary, review, lineage, reassessment, and black-box CLI coverage.

## Decisions Made

- D-10 confirmation is meaningful only when it acknowledges attribution, anchor fit, all three judgments and bases, reviewer/reason, and the expected effective hash; a click-only action fails closed.
- A reviewer finding insufficient basis creates `unverified-candidate`; it does not lower, delete, or silently admit the proposed mastery.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking issue] Imported the Pydantic field helper used by the new strict version collection.**
- **Found during:** Task 2
- **Issue:** The newly added `AssessmentRun.versions` contract could not load because `Field` was not imported.
- **Fix:** Added the existing Pydantic `Field` import and reran the planned test suite.
- **Files modified:** `src/career_evidence_graph/assessment.py`
- **Verification:** `30 passed` in the planned assessment/audit regression suite.
- **Committed in:** `ff10045`

**Total deviations:** 1 auto-fixed (Rule 3).
**Impact on plan:** The correction was required for the planned strict contract to import; it added no scope or dependency.

## Issues Encountered

The sandbox initially denied read access to the existing uv cache and Git index. After scoped approval, all checks ran locked and offline; no dependency or configuration changes were made.

## User Setup Required

None - no external service configuration required.

## Known Stubs

None.

## Self-Check: PASSED

- Confirmed all five planned source/test paths and this summary exist.
- Confirmed task commits `2e7cb5d`, `21a1733`, `9acfc4c`, and `ff10045` exist in Git history.

## Next Phase Readiness

Phase 4 can now calibrate and inspect confidence admission without treating uncertainty as zero or erasing its provenance. Candidate policy thresholds remain explicit calibration inputs, not active product policy.

---
*Phase: 04-contribution-skill-assessment-and-aggregation-calibration*
*Completed: 2026-08-27*
