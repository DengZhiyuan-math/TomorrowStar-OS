---
phase: 04-contribution-skill-assessment-and-aggregation-calibration
plan: "06"
subsystem: assessment-calibration
tags: [python, pydantic, calibration, custody, sha256, offline]
requires:
  - phase: 04-contribution-skill-assessment-and-aggregation-calibration
    provides: hash-bound policy comparison and the human-selected conservative-70 activation
provides:
  - calibration input identities derived from verified fixture, manifest, and completed-audit content
  - self-verifying retained policy snapshots, run results, and comparisons before activation lookup
  - immutable enriched conservative-70 history with its accepted identity chain unchanged
affects: [assessment-calibration, phase-05-jd-usefulness, independent-verification]
completion_authority: independent_verification
actuals:
  tokens: 10725
  tasks: 2
  commits: 5
tech-stack:
  added: []
  patterns:
    - derive trusted calibration input hashes from materialized audit and authoritative bytes
    - rehash retained policy, run, and comparison content before resolving activation references
key-files:
  created: []
  modified:
    - src/career_evidence_graph/domain/models.py
    - src/career_evidence_graph/assessment.py
    - validation/calibration/phase-04/policy-calibration/history.json
    - tests/test_policy_calibration.py
key-decisions:
  - "Corpus audit declarations remain assertions to validate, never a source for policy-run custody identities."
  - "The existing conservative-70 activation remains the sole active policy and preserves its prior policy, result, comparison, activation, and pointer hashes."
patterns-established:
  - "Retained policy history is semantically verified before lookup maps or activation ancestry checks are constructed."
requirements-addressed: [AGG-04]
requirements-completed: []
coverage:
  - id: D1
    description: "Calibration runs reject altered audit snapshot, conclusion-lineage, and effective-conclusion declarations before publishing history."
    requirement: AGG-04
    verification:
      - kind: integration
        ref: tests/test_policy_calibration.py#test_run_rejects_declared_audit_custody_tampering_before_history_publish
        status: pass
    human_judgment: false
  - id: D2
    description: "Retained policy snapshots, results, and comparisons fail closed on semantic or digest tampering before activation lookup."
    requirement: AGG-04
    verification:
      - kind: integration
        ref: tests/test_policy_calibration.py#test_history_semantic_tamper_fails_closed_before_activation_lookup
        status: pass
    human_judgment: false
duration: 4min
completed: 2026-08-27
status: complete
---

# Phase 04 Plan 06: Calibration Custody Rehashing Summary

**Audit-derived calibration identities and semantic history rehashing preserve the accepted conservative-70 authority while rejecting altered ancestry and retained policy evidence.**

## Performance

- **Duration:** 4 min
- **Started:** 2026-08-27T23:31:37+02:00
- **Completed:** 2026-08-27T23:35:05+02:00
- **Tasks:** 2/2
- **Files modified:** 4

## Accomplishments

- Materialized the completed, confirmed audit before policy execution and derived fixture, manifest, snapshot, conclusion-lineage, and effective-conclusion identities from authoritative content.
- Added repository-shaped exploit regressions proving altered corpus custody declarations fail before a history sidecar can be published.
- Persisted exact candidate policy snapshots with retained runs and recomputed policy, result, and comparison identities before any comparison or activation reference is trusted.
- Enriched the checked-in history with the exact baseline-60 and conservative-70 policy payloads without changing the accepted conservative-70 result, comparison, activation, or pointer identities.

## Task Commits

1. **Task 1 RED: Revalidate completed-audit custody through a real calibration run** — `d374a7f` (test)
2. **Task 1 GREEN: Revalidate completed-audit custody through a real calibration run** — `79e4df9` (feat)
3. **Task 2 RED: Rehash retained policy, result, and comparison semantics on every history read** — `afaf36d` (test)
4. **Task 2 GREEN: Rehash retained policy, result, and comparison semantics on every history read** — `3f7680b` (feat)

## Files Created/Modified

- `src/career_evidence_graph/domain/models.py` — requires a full `AggregationPolicy` snapshot in every retained policy run.
- `src/career_evidence_graph/assessment.py` — derives audit custody and validates retained policy/run/comparison semantics before activation lookup.
- `validation/calibration/phase-04/policy-calibration/history.json` — retains exact baseline-60 and conservative-70 policy snapshots alongside unchanged accepted identities.
- `tests/test_policy_calibration.py` — covers declared audit custody and semantic retained-history tampering.

## Decisions Made

- Audit declarations in the corpus are checked against a materialized completed/confirmed audit rather than being trusted as policy input.
- SHA-256 remains a trusted-local content-identity mechanism only; this remediation makes no reviewer-authentication or signature claim.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

- The locked offline commands needed scoped access to the existing uv cache; no dependency, provider, policy threshold, scorer, normalizer, or storage authority changed.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

This remediation addresses AGG-04 but does not complete the requirement, Phase 4, or milestone. Hand this unchanged revision to fresh independent verification and the required security authority before any shared planning status is promoted.

## Self-Check: PASSED

- All four implementation and regression artifacts plus this SUMMARY exist.
- Task commits `d374a7f`, `79e4df9`, `afaf36d`, and `3f7680b` exist in repository history.
