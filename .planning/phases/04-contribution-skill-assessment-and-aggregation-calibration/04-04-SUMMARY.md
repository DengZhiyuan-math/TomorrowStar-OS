---
phase: 04-contribution-skill-assessment-and-aggregation-calibration
plan: "04"
subsystem: assessment
tags: [python, pydantic, aggregation, mastery-anchors, cli, calibration]
requires:
  - phase: 04-contribution-skill-assessment-and-aggregation-calibration
    provides: admitted current assessment versions with immutable review and policy lineage
provides:
  - deterministic one-result-per-exact-Skill aggregation from admitted assessments
  - duplicate-neutral support lineage and canonical mastery snapshots
  - hash-bound, immediate-next-anchor promotion decisions with explicit behavior/context proof
affects: [phase-04-calibration, phase-05-jd-usefulness]
actuals:
  tokens: 8801
  tasks: 2
  commits: 4
tech-stack:
  added: []
  patterns:
    - aggregation selects the strongest admitted mastery exactly and records all same-Skill lineage without weighting it
    - promotion is a separate policy/input-hash-bound authority that can prove only the immediate next observable anchor
key-files:
  created:
    - tests/test_skill_aggregation.py
    - tests/test_anchor_promotion.py
  modified:
    - src/career_evidence_graph/domain/models.py
    - src/career_evidence_graph/domain/invariants.py
    - src/career_evidence_graph/assessment.py
    - src/career_evidence_graph/cli.py
    - tests/test_assessment_cli.py
key-decisions:
  - "Canonical user mastery equals the maximum admitted demonstrated mastery; confidence, centrality, duplicate evidence, duplicate contributions, and incidental volume cannot change it."
  - "A cross-Contribution promotion is defaulted to the immediate target anchor's lower bound and requires hash-bound, distinct same-Skill Contribution/context/behavior proof."
patterns-established:
  - "Inspect aggregate results instead of deriving user-level capability from counts or metadata."
  - "Bind every promotion behavior to an admitted assessment's demonstrated-mastery audit basis."
requirements-completed: [AGG-01, AGG-02, AGG-03]
coverage:
  - id: D1
    description: Deterministic aggregate output supplies exactly one traceable mastery result per exact Skill and policy.
    requirement: AGG-01
    verification:
      - kind: integration
        ref: tests/test_skill_aggregation.py#test_traceable_aggregate_keeps_one_sorted_result_and_strongest_admitted_baseline
        status: pass
      - kind: integration
        ref: tests/test_assessment_cli.py#test_aggregate_cli_emits_one_sorted_traceable_result_per_skill
        status: pass
    human_judgment: false
  - id: D2
    description: Duplicated assessment/support relationships and incidental uses preserve canonical mastery bytes and anchor band.
    requirement: AGG-02
    verification:
      - kind: unit
        ref: tests/test_skill_aggregation.py#test_no_inflation_from_duplicate_assessment_contribution_or_incidental_uses
        status: pass
      - kind: unit
        ref: tests/test_skill_aggregation.py#test_same_evidence_can_support_two_skills_without_same_skill_weighting
        status: pass
    human_judgment: false
  - id: D3
    description: Cross-Contribution promotion passes only with immediate-next-anchor, distinct behavior, context, and admitted-basis proof.
    requirement: AGG-03
    verification:
      - kind: unit
        ref: tests/test_anchor_promotion.py#test_next_anchor_promotion_requires_named_distinct_credible_support
        status: pass
      - kind: unit
        ref: tests/test_anchor_promotion.py#test_denied_promotions_leave_the_strongest_baseline_unchanged
        status: pass
    human_judgment: false
duration: 13min
completed: 2026-08-27
status: complete
---

# Phase 04 Plan 04: Deterministic Skill Aggregation and Next-Anchor Promotion Summary

**Stable per-Skill mastery now remains exactly at the strongest admitted assessment unless an explicit, hash-bound proof establishes the immediately next observable capability anchor.**

## Performance

- **Duration:** 13 min
- **Started:** 2026-08-27T21:24:07+02:00
- **Completed:** 2026-08-27T21:36:27Z
- **Tasks:** 2
- **Files modified:** 7

## Accomplishments

- Added deterministic exact-Skill grouping that retains all admitted IDs, selects a stable strongest baseline, reports suppressed same-Skill relationship duplicates, and keeps cross-Skill Evidence relevance independent.
- Added canonical mastery snapshots and metamorphic tests proving that duplicated Evidence, assessments, Contributions, or many low-centrality uses cannot raise mastery or change its anchor.
- Added a strict aggregate CLI view with sorted results and safe explanations for excluded non-admitted records.
- Added versioned candidate next-anchor rubric data and hash-bound promotion decisions that require distinct admitted Contributions, distinct real contexts, behavior-to-audit-basis bindings, and integer-exact target scores.

## Task Commits

1. **Task 1: Aggregate one exact Skill from its strongest admitted assessment** - `e40f3cb` (test RED), `7479d62` (feat GREEN)
2. **Task 2: Permit only explicit next-anchor cross-Contribution promotion** - `94edddd` (test RED), `4367153` (feat GREEN)

## Files Created/Modified

- `src/career_evidence_graph/domain/models.py` - Hash-bound promotion and expanded traceable aggregate-result contracts.
- `src/career_evidence_graph/domain/invariants.py` - Exact-Skill and strongest-baseline result validation.
- `src/career_evidence_graph/assessment.py` - Aggregation, duplicate reporting, candidate rubric, and promotion validation.
- `src/career_evidence_graph/cli.py` - `assessment aggregate` inspection command.
- `tests/test_skill_aggregation.py` - Traceability and no-inflation metamorphs.
- `tests/test_anchor_promotion.py` - Allowed and denied next-anchor promotion goldens.
- `tests/test_assessment_cli.py` - Sorted aggregate CLI output coverage.

## Decisions Made

- A result's baseline is chosen by maximum admitted demonstrated mastery with stable ID ordering; no mean, weight, count, confidence discount, centrality value, or breadth bonus participates in mastery.
- Same-Skill repeats retain lineage but are explicitly suppression-recorded, while one Evidence item may independently appear in distinct Skill results.
- Promotion is an exception authority, not an aggregation formula: it must hit only the next anchor, cover every exact behavior in the versioned candidate rubric, and otherwise leaves the baseline untouched.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing Critical Functionality] Extended the existing strict domain contracts for the planned policy-bearing aggregate and promotion authority.**
- **Found during:** Task 1 and Task 2
- **Issue:** The planned `AnchorPromotionDecision` and aggregate fields could not be safely serialized or cross-validated using only the prior one-assessment result contract.
- **Fix:** Added minimal Pydantic fields and exact-Skill/strongest-baseline validation to the existing domain contracts; no second aggregation engine or authority store was introduced.
- **Files modified:** `src/career_evidence_graph/domain/models.py`, `src/career_evidence_graph/domain/invariants.py`
- **Verification:** Focused aggregation/promotion tests, full offline suite, Ruff check, and format check pass.
- **Committed in:** `7479d62`, `4367153`

**Total deviations:** 1 auto-fixed (Rule 2).
**Impact on plan:** Required strict serialization and validation for the plan's declared output fields; no dependency or architecture expansion.

## Issues Encountered

- The workspace sandbox initially blocked reads of the existing uv cache. Scoped access was granted; all verification remained `--offline --locked`, and no dependency or configuration changed.

## Known Stubs

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Stable duplicate-neutral aggregation and next-anchor promotion are ready for the policy-comparison/activation work in Phase 04-05.
- Candidate rubric semantics remain calibration inputs; this plan does not activate a product policy or convert synthetic calibration into reviewed user truth.

## Verification

- `uv run --offline --locked python scripts/run_pytest.py -q tests/test_skill_aggregation.py tests/test_assessment_cli.py -k "traceable or no_inflation or duplicate or evidence or aggregate"` — 4 passed, 4 deselected.
- `uv run --offline --locked python scripts/run_pytest.py -q tests/test_anchor_promotion.py tests/test_skill_aggregation.py` — 8 passed.
- `uv run --offline --locked python scripts/run_pytest.py -q` — 276 passed, 1 deselected.
- `uv run --offline --locked ruff check ...` and `ruff format --check ...` — passed.

## Self-Check: PASSED

- Confirmed all seven implementation/test paths and this summary exist.
- Confirmed TDD RED/GREEN commits `e40f3cb`, `7479d62`, `94edddd`, and `4367153` exist in Git history.
