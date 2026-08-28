---
phase: 04-contribution-skill-assessment-and-aggregation-calibration
plan: "02"
subsystem: assessment
tags: [python, pydantic, skill-normalization, mastery-anchors, calibration]
requires:
  - phase: 04-contribution-skill-assessment-and-aggregation-calibration
    provides: confirmed-audit assessment tracer and strict persisted proposal lineage
provides:
  - independently traceable, specific-Skill proposals from confirmed audit conclusions
  - accepted 0--100 anchor registry with exact capability text and fail-closed validation
  - separate observable bases for mastery, centrality, and evidence confidence
affects: [phase-04-calibration, phase-05-jd-usefulness]
actuals:
  tokens: 6068
  tasks: 2
  commits: 4
tech-stack:
  added: []
  patterns:
    - one existing deterministic normalizer remains the only automatic Skill-resolution authority
    - anchor-first assessment stores exact anchor text, observable fit, score basis, and unmet next behavior
key-files:
  created:
    - tests/test_assessment_proposal.py
    - tests/test_mastery_anchors.py
  modified:
    - src/career_evidence_graph/domain/models.py
    - src/career_evidence_graph/domain/invariants.py
    - src/career_evidence_graph/assessment.py
    - validation/calibration/phase-04/corpus.json
key-decisions:
  - "Only one unambiguous result from the existing normalization metadata becomes score-eligible automatically; ambiguity and unmatched candidates remain outside proposals."
  - "The eight accepted anchors are exact schema-versioned data, while mastery, centrality, and confidence require separate observable bases."
patterns-established:
  - "Proposal records retain fixture, audit, conclusion, evidence, answer-question, attribution-area, and normalization-record custody without raw answer text."
  - "Exact mastery scores are valid only inside one accepted inclusive anchor with an observable fit, exact-score rationale, and explicitly unmet next behavior."
requirements-completed: [ASS-01, ASS-02, ASS-03]
coverage:
  - id: D1
    description: Specific-Skill proposal resolution preserves completed-audit source custody and withholds ambiguous or unmatched candidates.
    requirement: ASS-01
    verification:
      - kind: integration
        ref: tests/test_assessment_proposal.py
        status: pass
    human_judgment: false
  - id: D2
    description: Independent mastery, centrality, and confidence bases are retained alongside all exact mastery-anchor boundaries.
    requirement: ASS-02
    verification:
      - kind: unit
        ref: tests/test_assessment_models.py and tests/test_mastery_anchors.py
        status: pass
    human_judgment: false
  - id: D3
    description: Every exact score maps to one accepted anchor and rejects missing or mismatched anchor information.
    requirement: ASS-03
    verification:
      - kind: unit
        ref: tests/test_mastery_anchors.py
        status: pass
    human_judgment: false
duration: 8min
completed: 2026-08-27
status: complete
---

# Phase 04 Plan 02: Specific-Skill Proposal and Anchor-First Judgment Summary

**Confirmed audit conclusions now emit independently traceable specific-Skill proposals, while every effective mastery value carries one exact observable anchor and three separate assessment bases.**

## Performance

- **Duration:** 8 min
- **Started:** 2026-08-27T18:54:43Z
- **Completed:** 2026-08-27T19:02:37Z
- **Tasks:** 2
- **Files modified:** 7

## Accomplishments

- Reused `SkillNormalizationRecord` and `normalize_skill_metadata` as the sole automatic resolution path; only one deterministic alias result can become a proposal.
- Added source-custody proposals for every matched concrete Skill from a confirmed conclusion, retaining fixture, audit, lineage, evidence, answer-question, attribution, and normalization references.
- Encoded all eight accepted inclusive mastery ranges with verbatim capability text, explicit next-anchor absence, exact-score rationale, and independent mastery/centrality/confidence bases.
- Updated the synthetic calibration input so its existing effective assessment has the newly required explicit bases; the sealed STOA `known-good.json` remains unchanged.

## Task Commits

1. **Task 1: Propose every directly supported specific Skill with full source custody** - `c67fe3c` (test RED), `b0aee3c` (feat GREEN)
2. **Task 2: Enforce independent judgments and anchor-first exact mastery** - `1c1c49d` (test RED), `491a0be` (feat GREEN)

## Files Created/Modified

- `src/career_evidence_graph/domain/models.py` - Specific-Skill proposal, accepted-anchor, and independent judgment-basis contracts.
- `src/career_evidence_graph/domain/invariants.py` - Exact inclusive-anchor validator.
- `src/career_evidence_graph/assessment.py` - Existing-normalizer candidate resolution and confirmed-audit proposal assembly.
- `validation/calibration/phase-04/corpus.json` - Explicit synthetic basis records for the existing assessment tracer.
- `tests/test_assessment_proposal.py` - Deterministic normalization and audit-custody coverage.
- `tests/test_mastery_anchors.py` - All boundary pairs and malformed anchor-fit coverage.
- `tests/test_assessment_models.py` - Independent judgment-basis persistence coverage.

## Decisions Made

- A proposal becomes score-eligible only through a single unambiguous result from the existing normalizer; broad, descriptive, ambiguous, and unmatched wording remains review-required or unmatched.
- The project anchor wording is stored verbatim and cannot be substituted by a range-compatible but semantically different label.
- Separate judgment bases prevent centrality or confidence from silently becoming mastery evidence.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing Critical Functionality] Made the existing synthetic calibration proposal carry mandatory independent bases.**
- **Found during:** Task 2
- **Issue:** The prior calibration corpus supplied an effective mastery number without the newly required anchor text, next-anchor exclusion, and independent three-judgment bases.
- **Fix:** Added explicit synthetic basis data to the calibration corpus and validated it through the existing tracer.
- **Files modified:** `validation/calibration/phase-04/corpus.json`
- **Verification:** Focused assessment tests and the full offline suite pass.
- **Committed in:** `491a0be`

**Total deviations:** 1 auto-fixed (Rule 2)

## Issues Encountered

- The first custody assertion omitted one audited evidence reference and answer-attribution turns. The test was corrected to require the complete source envelope rather than discard valid provenance.

## Known Stubs

None.

## Next Phase Readiness

- Phase 04-03 can add substantive human review and confidence admission atop specific, anchor-valid proposals.
- The configured synthetic calibration remains visibly `derived-counterfactual`; it is not reviewed user truth.

## Verification

- `uv run --offline --locked python scripts/run_pytest.py -q tests/test_assessment_models.py tests/test_assessment_proposal.py tests/test_mastery_anchors.py tests/test_domain_invariants.py` — 54 passed.
- `uv run --offline --locked ruff check ...` and `ruff format --check ...` — passed.
- `uv run --offline --locked python scripts/run_pytest.py -q` — 248 passed, 1 deselected.

## Self-Check: PASSED

- All seven implementation/test/calibration files and the summary exist.
- TDD RED/GREEN commits `c67fe3c`, `b0aee3c`, `1c1c49d`, and `491a0be` exist in Git history.

---
*Phase: 04-contribution-skill-assessment-and-aggregation-calibration*
*Completed: 2026-08-27*
