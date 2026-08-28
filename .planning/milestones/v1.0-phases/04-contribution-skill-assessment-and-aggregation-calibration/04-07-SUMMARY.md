---
phase: 04-contribution-skill-assessment-and-aggregation-calibration
plan: "07"
subsystem: assessment-custody
tags: [python, cli, assessment, immutable-history, sha256, offline]
requires:
  - phase: 04-contribution-skill-assessment-and-aggregation-calibration
    provides: completed-audit proposals, hash-bound review lineage, and conservative-70 admission policy
provides:
  - idempotent normal assessment reruns that preserve reviewed current state
  - explicit stale-safe reassessment command for later audit evidence
  - append-only reviewer versions with retained predecessor content
affects: [assessment-custody, phase-05-jd-usefulness, independent-verification, security-review]
completion_authority: independent_verification
actuals:
  tokens: 2932.5
  tasks: 2
  commits: 4
tech-stack:
  added: []
  patterns:
    - deterministic reruns validate and return existing authority rather than replacing it
    - human review changes append a canonical version linked to the prior current hash
key-files:
  created: []
  modified:
    - src/career_evidence_graph/assessment.py
    - src/career_evidence_graph/cli.py
    - tests/test_assessment_admission.py
    - tests/test_assessment_cli.py
key-decisions:
  - "Normal assessment execution is retry-only; later evidence must use explicit reassessment with the expected current version hash."
  - "Each substantive reviewer outcome appends a full AssessmentVersion so original and intermediate assessments remain auditable."
patterns-established:
  - "Current assessment projections are rebuilt solely from the final retained version."
requirements-addressed: [ASS-04]
requirements-completed: []
coverage:
  - id: D1
    description: "A normal CLI rerun preserves an insufficient-basis decision, canonical sidecar bytes, version history, and lack of an aggregate result."
    requirement: ASS-04
    verification:
      - kind: integration
        ref: tests/test_assessment_cli.py#test_rerun_after_insufficient_review_is_byte_idempotent
        status: pass
    human_judgment: false
  - id: D2
    description: "Explicit reassessment rejects stale expected-version hashes without mutating the sidecar."
    requirement: ASS-04
    verification:
      - kind: integration
        ref: tests/test_assessment_cli.py#test_explicit_reassess_rejects_stale_hash_without_mutating_sidecar
        status: pass
    human_judgment: false
  - id: D3
    description: "Two reviewer edits retain the initial and both intermediate effective assessments as sequential hash-linked versions after canonical reopen."
    requirement: ASS-04
    verification:
      - kind: integration
        ref: tests/test_assessment_admission.py#test_two_edits_retain_immutable_versions_and_reopen
        status: pass
    human_judgment: false
duration: 5min
completed: 2026-08-28
status: complete
---

# Phase 04 Plan 07: Assessment Rerun and Review-Lineage Summary

**Normal assessment retries now preserve reviewed authority, while explicit reassessments and every reviewer decision produce hash-linked immutable history.**

## Performance

- **Duration:** 5 min
- **Started:** 2026-08-28T08:30:59Z
- **Completed:** 2026-08-28T08:36:01Z
- **Tasks:** 2/2
- **Files modified:** 4

## Accomplishments

- Replaced collision overwrite on the documented assessment command with full validation of the stored deterministic record and identity matching against the requested audit and policy.
- Added the explicit `assessment reassess` path, requiring a later audit identity, complete proposal, and expected current version hash before atomically replacing the current projection.
- Made confirm, edit, and insufficient-basis reviewer outcomes append sequential versions, retaining every predecessor, review lineage, and effective assessment.

## Task Commits

1. **Task 1 RED: Preserve an insufficient-basis decision across normal rerun** — `5a8e2bd` (test)
2. **Task 1 GREEN: Preserve an insufficient-basis decision across normal rerun** — `a5d26dc` (feat)
3. **Task 2 RED: Append every reviewer decision as a retained immutable version** — `1398708` (test)
4. **Task 2 GREEN: Append every reviewer decision as a retained immutable version** — `c902fe3` (feat)

## Files Created/Modified

- `src/career_evidence_graph/assessment.py` — validates normal reruns, guards explicit reassessments, and appends review versions instead of replacing them.
- `src/career_evidence_graph/cli.py` — exposes the stale-safe `assessment reassess` command.
- `tests/test_assessment_cli.py` — covers byte-idempotent rerun after insufficient basis and stale reassessment non-mutation.
- `tests/test_assessment_admission.py` — proves two reviewer edits retain all three effective versions after reopening.

## Decisions Made

- A normal rerun is never new assessment intent: it returns only the fully validated existing record whose initial proposal and policy identity match the requested deterministic run.
- Reviewer decisions preserve a complete retained lineage; explicit reassessment remains the separate, hash-guarded path for later evidence.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Verification bug] Repaired scoped Ruff violations in resumed reassessment and rerun error paths**
- **Found during:** Task 2 verification
- **Issue:** The resumed Task 1 implementation had an overlong error line and omitted exception chaining when rejecting a mismatched existing record.
- **Fix:** Wrapped the audit-identity error and chained the workflow error from the storage collision exception.
- **Files modified:** `src/career_evidence_graph/assessment.py`
- **Verification:** Both focused RED-to-GREEN groups, the full focused 35-test suite, and scoped Ruff checks passed.
- **Committed in:** `c902fe3` (part of Task 2 GREEN)

**Total deviations:** 1 auto-fixed (Rule 1)

## Issues Encountered

- The workspace sandbox could not open the pre-existing uv cache; the locked offline verification commands then ran with the approved existing cache and performed no dependency installation or network access.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

This remediation addresses ASS-04 but does not complete ASS-04, Phase 04, or the milestone. Hand the unchanged revision to fresh independent verification and the required security authority before any shared planning status is promoted.

## Self-Check: PASSED

- All four modified plan artifacts and this SUMMARY exist.
- TDD commits `5a8e2bd`, `a5d26dc`, `1398708`, and `c902fe3` exist in repository history.
