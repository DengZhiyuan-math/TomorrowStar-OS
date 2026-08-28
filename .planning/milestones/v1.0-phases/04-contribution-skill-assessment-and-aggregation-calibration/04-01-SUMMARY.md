---
phase: 04-contribution-skill-assessment-and-aggregation-calibration
plan: "01"
subsystem: assessment
tags: [python, pydantic, cli, calibration, trusted-local-storage]
requires:
  - phase: 03-artifact-aware-grill-me-and-attribution-workflow
    provides: completed confirmed AuditSnapshot records with contribution and conclusion lineage
provides:
  - hash-bound offline specific-Skill assessment tracer
  - strict policy-bearing admission and no-inflation aggregate
  - atomic assessment sidecar persistence with redacted inspection failures
affects: [phase-04-calibration, phase-05-jd-usefulness]
actuals:
  tokens: 10397
  tasks: 2
  commits: 4
tech-stack:
  added: []
  patterns:
    - one strict AssessmentStore sidecar reusing AuditStore atomic persistence
    - synthetic calibration authority remains separate from reviewed user truth
key-files:
  created:
    - validation/calibration/phase-04/corpus.json
    - validation/calibration/phase-04/policies.json
    - tests/test_assessment_models.py
  modified:
    - src/career_evidence_graph/assessment.py
    - src/career_evidence_graph/domain/models.py
    - src/career_evidence_graph/cli.py
    - tests/test_assessment_cli.py
key-decisions:
  - "Persisted Phase 4 sidecars contain exactly one admitted proposal/result lineage, so a foreign assessment cannot be silently admitted."
  - "The offline tracer retains derived-counterfactual authority and exposes it rather than presenting synthetic calibration as reviewed user truth."
patterns-established:
  - "Validate complete Pydantic records before write and after read; use canonical bytes, fsync, atomic replacement, safe IDs, and direct-link rejection."
  - "Expose assessment workflow and storage failures as stable structured JSON without raw interview answer text."
requirements-completed: [ASS-01, ASS-02, ASS-03, ASS-04, AGG-01, AGG-02, AGG-03, AGG-04]
coverage:
  - id: D1
    description: "Offline confirmed-audit to explicitly synthetic, policy-bearing specific-Skill tracer"
    requirement: "ASS-01"
    verification:
      - kind: e2e
        ref: "tests/test_assessment_cli.py#test_tracer_cli_persists_explicitly_synthetic_calibration_result"
        status: pass
    human_judgment: false
  - id: D2
    description: "Atomic assessment sidecar reopen and corrupt/cross-linked record rejection"
    requirement: "AGG-01"
    verification:
      - kind: integration
        ref: "uv run --offline --locked python scripts/run_pytest.py -q tests/test_assessment_cli.py tests/test_assessment_models.py tests/test_audit_store.py"
        status: pass
    human_judgment: false
duration: 3min
completed: 2026-08-27
status: complete
---

# Phase 04 Plan 01: Confirmed-Audit Assessment Tracer Summary

**Hash-bound offline assessment tracer turns one completed confirmed STOA audit into an explicitly synthetic, policy-bearing specific-Skill aggregate with strict local persistence.**

## Performance

- **Duration:** 3 min
- **Started:** 2026-08-27T18:45:18Z
- **Completed:** 2026-08-27T18:48:31Z
- **Tasks:** 2
- **Files modified:** 8

## Accomplishments

- Materialized a corpus bound to the sealed STOA fixture and the completed `audit-e2e` hashes; the broad fixture marker remains non-scoreable and the positive case stays `derived-counterfactual`.
- Added the policy-bearing, anchor-first proposal/admission/aggregation CLI seam, preserving mastery, centrality, confidence, and source lineage as separate fields.
- Persisted one strict assessment sidecar per run and reject corrupt, unsafe, linked, extra-field, or cross-linked records before they can be reopened; CLI failures remain structured and redacted.

## Task Commits

1. **Task 1: Run one confirmed audit through proposal, admission, and aggregation** — `d60b0c4` (test), `c86c316` (feat)
2. **Task 2: Persist and reopen the traceable result through strict local boundaries** — `a757dbc` (test), `a7d7b3f` (feat)

## Files Created/Modified

- `src/career_evidence_graph/assessment.py` — canonical offline workflow and trusted-local AssessmentStore.
- `src/career_evidence_graph/domain/models.py` — policy, admission, anchor, source-envelope, and calibrated-result contracts.
- `src/career_evidence_graph/cli.py` — assessment run and inspect commands with structured error handling.
- `validation/calibration/phase-04/corpus.json` and `policies.json` — hash-bound synthetic tracer and replaceable candidate policies.
- `tests/test_assessment_cli.py` and `tests/test_assessment_models.py` — black-box tracer, redaction, reopening, and strict boundary coverage.

## Decisions Made

- A persisted result must exactly match its sole admitted proposal for skill, mastery, policy, source envelope, and assessment ID. This prevents a sidecar from concealing another assessment or collapsed aggregation state.
- The tracer's authority remains visibly synthetic calibration. It does not upgrade the source audit into reviewed user Skill truth.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

The local uv cache is outside the workspace sandbox; locked offline verification completed after obtaining permission to read that existing cache. No dependencies were installed or changed.

## Known Stubs

None.

## Next Phase Readiness

The confirmed-audit assessment tracer and strict persistence boundary are ready for the Phase 4 expansion plans. The two candidate policies remain calibration inputs rather than active product policy.

## Self-Check: PASSED

- Confirmed all eight plan artifact paths exist.
- Confirmed task commits `d60b0c4`, `c86c316`, `a757dbc`, and `a7d7b3f` exist in Git history.

---

*Phase: 04-contribution-skill-assessment-and-aggregation-calibration*
*Completed: 2026-08-27*
