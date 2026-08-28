---
phase: 02-domain-contracts-stoa-fixture-and-deterministic-invariants
plan: 06
subsystem: fixture-regression-validation
tags: [python, pydantic, cli, deterministic-fixtures, immutable-evidence]
requires:
  - phase: 02-05
    provides: Human-reviewed sealed STOA known-good fixture and verified FormalRunStore bundle
provides:
  - Closed, deep-copy-only one-fault mutation contracts and sixteen checked-in known-bad cases
  - Offline CLI suite proving the sealed base and every declared sole rejection in stable JSON order
  - Green Phase 02 Nyquist validation record backed by focused and full offline gates
affects: [phase-03-grill-me, phase-04-calibration, phase-05-evaluation, fixture-regression]
tech-stack:
  added: []
  patterns:
    - Closed typed mutation vocabulary instead of generic JSON patching
    - Sealed-base before/after validation with formal-run byte preservation assertions
    - Fail-closed deterministic CLI inventory validation
key-files:
  created:
    - tests/test_fixture_mutations.py
    - validation/fixtures/stoa/v1/known-bad/
  modified:
    - src/career_evidence_graph/domain/fixtures.py
    - src/career_evidence_graph/domain/__init__.py
    - src/career_evidence_graph/cli.py
    - .planning/phases/02-domain-contracts-stoa-fixture-and-deterministic-invariants/02-VALIDATION.md
key-decisions:
  - "Known-bad variants are a closed operation over an in-memory deep copy of sealed truth; no generic patch or fixture write capability is exposed."
  - "The reviewed user/Codex-assisted attribution remains intact in the sealed base; the obscured-assistance case proves a reviewed assertion cannot hide it."
  - "The suite reports fixture-contract rejections only and makes no calibration, aggregation, JD, or effectiveness claim."
patterns-established:
  - "Single-fault suite: a case ID is its one typed operation, must bind the sealed confirmed-result hash, and is green only for exactly one matching code."
  - "Offline suite gate: validate sealed known-good first, require the exact checked-in inventory, then emit case-ID-sorted JSON."
requirements-completed: [FIX-02, MOD-02, MOD-04, MOD-05, MOD-07]
coverage:
  - id: D1
    description: Sixteen sealed-base known-bad fixtures each yield one stable declared rejection without changing known-good or FormalRunStore bytes.
    requirement: FIX-02
    verification:
      - kind: unit
        ref: tests/test_fixture_mutations.py
        status: pass
    human_judgment: false
  - id: D2
    description: Offline fixture validate-suite CLI verifies the sealed base, exact known-bad inventory, sole errors, and fail-closed invalid inputs.
    requirement: FIX-02
    verification:
      - kind: integration
        ref: python -m career_evidence_graph.cli fixture validate-suite --known-good validation/fixtures/stoa/v1/known-good.json --known-bad-dir validation/fixtures/stoa/v1/known-bad
        status: pass
    human_judgment: false
  - id: D3
    description: Phase 02 validation matrix is synchronized only after focused checks, full offline pytest, lint, and format gates passed.
    requirement: FIX-02
    verification:
      - kind: other
        ref: .planning/phases/02-domain-contracts-stoa-fixture-and-deterministic-invariants/02-VALIDATION.md
        status: pass
    human_judgment: false
metrics:
  duration: 11min
  completed: 2026-07-30
status: complete
---

# Phase 02 Plan 06: Deterministic Known-Bad Fixture Suite Summary

**Sixteen sealed-STOA one-fault variants now prove deterministic, sole invariant rejections through an offline CLI while leaving known-good and its formal-run evidence byte-identical.**

## Performance

- **Duration:** 11 min
- **Started:** 2026-07-30T15:45:56Z
- **Completed:** 2026-07-30T15:56:49Z
- **Tasks:** 2/2
- **Files modified:** 21

## Accomplishments

- Added closed mutation records, deep-copy application, sole-code evaluation, and deterministic suite ordering; generic JSON paths and patch values are rejected.
- Added exactly 16 declarative cases covering the required direct-source, attribution, assistance, duplicate-Evidence, lineage, basis, dimension, range, context, duration, and ontology faults.
- Added `fixture validate-suite`, which verifies sealed known-good first, requires the exact 16-file inventory, emits stable JSON, and exits 2 for invalid, missing, extra, tampered, base-mismatched, or non-sole results.
- Marked Phase 02 validation green only after all task commands, the batch CLI, full pytest, Ruff lint, and Ruff format checks passed.

## Task Commits

1. **Task 1 RED: fixture mutation regressions** — `4427356` (test)
2. **Task 1 GREEN: sealed one-fault variants** — `d841442` (feat)
3. **Task 2 RED: fixture suite CLI coverage** — `0f9cc7f` (test)
4. **Task 2 GREEN: offline fixture validation suite** — `8577091` (feat)

## Verification Evidence

- Batch suite: `valid: true`, sealed base `sha256:f393c1034a6d604ae915a18dac3bd206ce146e9c050b4e938048eb10a6378242`, `case_count: 16`; repeated JSON reports were byte-identical.
- Phase 2 modules: **105 passed**.
- Full offline suite: **160 passed, 1 deselected**.
- Ruff: `check .` and `format --check .` passed.
- Immutable evidence hashes remained unchanged: known-good `38329222f8275fb22924717c7b4b2e0bb25d8e82189177d9039cd891f2a1e883`; confirmed-result `c434d3c6e84f5a67db1059eda58658ba3168b10c477f7f340b7dbd5f1f923dc4`.

## Exact Case Results

| Case | Sole code |
| --- | --- |
| dimension-confusion | `assessment.dimension_confusion` |
| direct-mastery-experience | `assessment.direct-source-forbidden` |
| direct-mastery-ontology | `assessment.direct-source-forbidden` |
| direct-mastery-repository | `assessment.direct-source-forbidden` |
| direct-mastery-resume-skill-list | `assessment.direct-source-forbidden` |
| direct-mastery-title | `assessment.direct-source-forbidden` |
| duplicate-evidence-link | `claim_evidence_link.duplicate` |
| missing-assessment-basis | `assessment.basis_claim_missing` |
| missing-context | `assessment.context_missing` |
| missing-contribution-lineage | `assessment.contribution_missing` |
| missing-duration | `assessment.duration_missing` |
| obscured-codex-assistance | `assessment.definite_claim_assisted` |
| ontology-mastery-change | `assessment.ontology_mastery_change` |
| score-above-hundred | `assessment.score_out_of_range` |
| score-below-zero | `assessment.score_out_of_range` |
| wrong-responsibility | `assessment.definite_claim_not_user` |

## Decisions Made

- Retained sealed claim semantics (`responsibility=user`, `assistance=codex_assisted`) as reviewed evidence; negative cases can test assertion failures without changing accepted evidence.
- Kept schema-originating structural mutation rejections in the fixture-suite code namespace so each invalid case still returns one stable, explicit diagnostic.
- Did not add a scoring, calibration, aggregation, JD, résumé, or product-effectiveness policy.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Test ordering] Corrected the regression assertion to sort deliberately shuffled discovery results before comparison.**
- **Found during:** Task 1
- **Issue:** The test intentionally loaded files in reverse order but compared the raw result list to case-ID order.
- **Fix:** Sorted the observed `(case_id, actual_codes)` pairs; the production suite still owns deterministic ordering.
- **Files modified:** `tests/test_fixture_mutations.py`
- **Verification:** Focused mutation tests, repeated suite JSON comparison, and full offline suite passed.
- **Committed in:** `d841442`

**2. [Rule 3 - Blocking environment] Reused the locked source-path environment for offline verification.**
- **Found during:** Both tasks
- **Issue:** Rebuilding the installed package would require unavailable build-isolation cache content.
- **Fix:** Ran every verification command with `PYTHONPATH=src` and the existing locked uv cache; no dependency, lockfile, or configuration changed.
- **Files modified:** None
- **Verification:** 105 focused Phase 2 tests and 160 full-suite tests passed; lint and format passed.
- **Committed in:** `8577091`

---

**Total deviations:** 2 auto-fixed (1 Rule 1, 1 Rule 3). **Impact:** No fixture bytes, dependencies, scope boundaries, or assessment semantics changed.

## Issues Encountered

None beyond the already-recorded offline package-rebuild limitation.

## Known Stubs

None.

## User Setup Required

None - the complete fixture gate is local, deterministic, and provider-free.

## Next Phase Readiness

- Phase 03 can consume a sealed immutable STOA fixture with explicit attribution and known-bad regression evidence.
- This plan supplies no mastery calibration, confidence-admission, aggregation, JD comparison, résumé generation, or effectiveness conclusion.

## Self-Check: PASSED

- All 16 declared known-bad JSON files, mutation domain contracts, CLI route, test module, and validation-status record exist.
- All four task commits (`4427356`, `d841442`, `0f9cc7f`, `8577091`) exist in Git.
- The repeated suite output was byte-identical and known-good/formal-run file hashes remained unchanged.

---
*Phase: 02-domain-contracts-stoa-fixture-and-deterministic-invariants*
*Completed: 2026-07-30*
