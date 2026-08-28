---
phase: 04-contribution-skill-assessment-and-aggregation-calibration
plan: "05"
subsystem: assessment-calibration
tags: [python, pydantic, calibration, policy-history, cli, offline]
requires:
  - phase: 04-contribution-skill-assessment-and-aggregation-calibration
    provides: explicit contribution-skill admission, no-inflation aggregation, and next-anchor promotion controls
provides:
  - hash-bound same-input policy comparison and immutable activation lineage
  - conservative-70 human-approved confidence-admission pointer
  - offline compare, activate, and history CLI operations with stale-safe replacement
affects: [phase-05-jd-usefulness, assessment-calibration, validation]
actuals:
  tokens: 20731
  tasks: 3
  commits: 2
tech-stack:
  added: []
  patterns:
    - immutable policy run/comparison/activation history with a convenience pointer
    - exact bootstrap and stale-safe replacement preconditions for trusted-local calibration authority
key-files:
  created:
    - validation/calibration/phase-04/policy-calibration/history.json
  modified:
    - src/career_evidence_graph/assessment.py
    - src/career_evidence_graph/domain/models.py
    - src/career_evidence_graph/cli.py
    - tests/test_policy_calibration.py
    - tests/test_assessment_cli.py
    - .planning/phases/04-contribution-skill-assessment-and-aggregation-calibration/04-VALIDATION.md
key-decisions:
  - "zhdeng activated policy-04-conservative-70 using the verified policy, result, and comparison hashes."
  - "Confidence-boundary cases below 70 remain pending human confirmation; re-evaluate after more real audited samples."
  - "policy-04-baseline-60 remains immutable comparison evidence, not active authority."
patterns-established:
  - "Calibration activation verifies retained policy/result/comparison ancestry before publishing the pointer."
  - "A first activation is only null/null/absent; replacement must name the exact prior policy, result, and pointer hash."
requirements-completed: [AGG-04, ASS-01, ASS-02, ASS-03, ASS-04, AGG-01, AGG-02, AGG-03]
coverage:
  - id: D1
    description: Hash-bound same-input calibration policies retain deltas, regressions, disagreement, and variance without activation side effects.
    requirement: AGG-04
    verification:
      - kind: integration
        ref: tests/test_policy_calibration.py#test_candidates_use_identical_input_and_compare_without_activation
        status: pass
    human_judgment: false
  - id: D2
    description: The owner-approved conservative-70 activation is immutable, hash-bound, and inspectable through offline history.
    requirement: AGG-04
    verification:
      - kind: integration
        ref: tests/test_policy_calibration.py#test_first_activation_records_exact_bootstrap_selection_and_pointer
        status: pass
      - kind: other
        ref: validation/calibration/phase-04/policy-calibration/history.json
        status: pass
    human_judgment: false
  - id: D3
    description: Competing bootstrap, stale pointer, forged reviewer, malformed history, and symlink aliases fail without changing authority.
    requirement: AGG-04
    verification:
      - kind: integration
        ref: tests/test_policy_calibration.py#test_stale_pointer_and_subsequent_replacement_require_exact_current_ancestry
        status: pass
      - kind: integration
        ref: tests/test_policy_calibration.py#test_calibration_history_rejects_symlink_aliases_and_malformed_payloads
        status: pass
    human_judgment: false
duration: 21min
completed: 2026-08-27
status: complete
---

# Phase 04 Plan 05: Policy Comparison and Human Activation Summary

**Hash-bound baseline/conservative comparison with a human-approved conservative-70 confidence gate, immutable activation lineage, and offline inspection CLI.**

## Performance

- **Duration:** 21 min
- **Started:** 2026-08-27T20:06:05Z
- **Completed:** 2026-08-27T20:27:01Z
- **Tasks:** 3/3
- **Files modified:** 9

## Accomplishments

- Extended the sealed audit-bound calibration corpus into a complete labeled counterfactual matrix and compared baseline-60 with conservative-70 over identical input hashes.
- Added immutable `PolicyActivation` records, recursive history verification, and exact bootstrap/replacement authority guards.
- Recorded `zhdeng`'s conservative-70 activation with the approved reason, limitation, policy hash, result hash, and comparison hash; baseline-60 remains comparison-only.
- Added stable offline `assessment compare`, `assessment activate`, and `assessment history` CLI commands and completed the Phase 4 executable validation matrix.

## Task Commits

1. **Task 1: Build the hash-bound corpus and compare current/candidate policies** — `307365f` (feat)
2. **Task 2: Human calibration authority selects or rejects the compared policy candidates** — approved `activate-conservative-70`; recorded in Task 3's immutable activation history.
3. **Task 3: Record the human selection, inspect history, and close the offline matrix** — `55cbdc5` (feat)

## Files Created/Modified

- `validation/calibration/phase-04/policy-calibration/history.json` — canonical policy runs, comparison, selected activation, and active pointer.
- `src/career_evidence_graph/domain/models.py` — strict activation and history contracts.
- `src/career_evidence_graph/assessment.py` — ancestry verification, fail-closed activation, and history persistence.
- `src/career_evidence_graph/cli.py` — offline comparison, activation, and history commands.
- `tests/test_policy_calibration.py` and `tests/test_assessment_cli.py` — bootstrap, stale replacement, tamper, symlink, redaction, and CLI coverage.
- `04-VALIDATION.md` — measured requirements, decision, edge, and threat matrix.

## Decisions Made

- Activated only `policy-04-conservative-70` with policy hash `sha256:603cfbadcf8bb6ab2163dd0206e844a4b8b3956fe15974da85c028fe75fb6f6b`, result hash `sha256:0992b26cfa0ab76eba631851bf4fc22b1a8213cc30c18492d08d45a7832e0719`, and comparison hash `sha256:ac2630db1076b3a824e28e1e29c9c1cc64cc972a500d2deae5c492ab35d11ea7`.
- Reviewer `zhdeng` selected the conservative gate so boundary cases with insufficient evidence confidence remain pending human confirmation rather than being counted immediately.
- This is an initial calibration policy and must be re-evaluated after additional real audited samples accumulate.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

- The sandbox initially prevented uv from opening its existing user-level cache. Scoped read access was approved; all checks remained `--offline --locked`, and no dependency was installed or changed.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

Phase 5 can consume the immutable calibration lineage and inspectable conservative admission policy. The synthetic/counterfactual corpus remains a calibration fixture, not evidence of general JD or employment effectiveness.

## Self-Check: PASSED

- All nine Plan 04-05 implementation, fixture, validation, and summary artifacts exist.
- Task commits `307365f` and `55cbdc5` exist in repository history.

---
*Phase: 04-contribution-skill-assessment-and-aggregation-calibration*
*Completed: 2026-08-27*
