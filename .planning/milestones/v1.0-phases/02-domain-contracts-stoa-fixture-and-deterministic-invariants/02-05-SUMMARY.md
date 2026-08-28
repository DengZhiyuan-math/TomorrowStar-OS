---
phase: 02-domain-contracts-stoa-fixture-and-deterministic-invariants
plan: 05
subsystem: evidence-fixture-validation
tags: [python, pydantic, formal-run-store, immutable-fixture, replay]
requires:
  - phase: 02-02
    provides: CareerEvidenceFixture validation and mastery-isolated fixture semantics
  - phase: 02-04
    provides: zhdeng's exact four-candidate, six-group review authority
provides:
  - Hash-linked review corrections and immutable human decision materialization
  - Verified STOA FormalRunStore bundle and canonical known-good fixture
  - Provider-free exact replay and offline fixture seal/validate CLI path
affects: [phase-03-grill-me, phase-04-calibration, fixture-regression]
tech-stack:
  added: []
  patterns:
    - Complete human-review authority before immutable publication
    - Exclusive canonical known-good publication linked to verified formal evidence
key-files:
  created:
    - validation/fixtures/stoa/v1/formal-runs/stoa-known-good/manifest.json
    - validation/fixtures/stoa/v1/known-good.json
  modified:
    - src/career_evidence_graph/domain/fixtures.py
    - src/career_evidence_graph/cli.py
    - validation/fixtures/stoa/v1/review.json
    - tests/test_stoa_fixture.py
key-decisions:
  - "zhdeng's four exact review packets are materialized one-to-one; all score/range groups remain unresolved with no numeric mastery score."
  - "Known-good is immutable validation evidence only: it makes no calibration, aggregation, JD, resume, or effectiveness claim."
patterns-established:
  - "Immutable review: accepted values retain candidate equality, while attribution edits retain original proposal hashes, reviewer, and reason."
  - "Recovery: an absent known-good output may be recreated only from an already verified identical formal bundle."
requirements-completed: [FIX-01, MOD-02, MOD-03, MOD-04, MOD-05, MOD-06, MOD-07]
coverage:
  - id: D1
    description: Human-authorized review materialization with retained corrections and unresolved fixture-score expectations
    requirement: FIX-01
    verification:
      - kind: unit
        ref: tests/test_stoa_fixture.py
        status: pass
    human_judgment: false
  - id: D2
    description: Immutable STOA known-good FormalRunStore bundle, canonical hash linkage, and provider-free replay
    requirement: MOD-02
    verification:
      - kind: integration
        ref: "python -m career_evidence_graph.cli fixture validate validation/fixtures/stoa/v1/known-good.json"
        status: pass
      - kind: integration
        ref: "python -m career_evidence_graph.cli replay --workspace validation/fixtures/stoa/v1 --run-id stoa-known-good"
        status: pass
    human_judgment: false
metrics:
  duration: 8min
  completed: 2026-07-30
status: complete
---

# Phase 02 Plan 05: Immutable STOA Known-Good Fixture Summary

**Human-confirmed STOA review history sealed as a hash-linked FormalRunStore bundle with exact offline replay and no mastery-calibration claim.**

## Performance

- **Duration:** 8 min
- **Started:** 2026-07-30T15:32:15Z
- **Completed:** 2026-07-30T15:40:14Z
- **Tasks:** 2/2
- **Files modified:** 10

## Accomplishments

- Materialized the reviewer `zhdeng` decision packet for all four candidates and all six groups; every attribution edit now preserves its original candidate-ledger payload/hash, reviewer, and reason.
- Retained all `fixture_score_range` decisions as explicit unresolved fixture-test expectations. The sealed fixture has no numeric assessment or user-skill mastery score.
- Published and verified `stoa-known-good`: confirmed-result hash `sha256:f393c1034a6d604ae915a18dac3bd206ce146e9c050b4e938048eb10a6378242`, with replay matched and no provider call.
- Added fail-closed duplicate/divergent-output handling and verified-bundle-only recovery for a missing known-good output.

## Task Commits

1. **Task 1 RED: reviewed-fixture regression** — `a5f2e0e` (test)
2. **Task 1 GREEN: materialize STOA review authority** — `38836f0` (feat)
3. **Task 2 RED: immutable-seal regression** — `a904b1b` (test)
4. **Task 2 GREEN: seal immutable STOA known-good fixture** — `e26f34c` (feat)

## Files Created/Modified

- `src/career_evidence_graph/domain/fixtures.py` — review authority, correction history, sealing, loading, and atomic publication.
- `src/career_evidence_graph/cli.py` — offline `fixture seal` and sealed `fixture validate` routes.
- `validation/fixtures/stoa/v1/review.json` — canonical reviewer, checkpoint hash, exact decisions, and corrections.
- `validation/fixtures/stoa/v1/formal-runs/stoa-known-good/` — immutable manifest plus raw response, proposal, corrections, and confirmed result.
- `validation/fixtures/stoa/v1/known-good.json` — canonical sealed envelope tied to the formal run/result hash.
- `tests/test_stoa_fixture.py` — review, immutable output, recovery, and replay coverage.

## Decisions Made

- The four review corrections replace only `unconfirmed` responsibility/assistance with `user`/`codex_assisted`; they do not change partial completion, proof limits, conflicts, limitations, or planned-only isolation.
- Human ownership and Codex assistance are attribution facts, not mastery proof. Later Grill-Me must still assess explain/reproduce/maintain capability.
- The known-good fixture is a validation fixture, not evidence of product, job-search, application, interview, or hiring effectiveness.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking environment] Reused the locked environment with source-path import for verification**
- **Found during:** Tasks 1 and 2
- **Issue:** `uv sync --locked --reinstall-package career-evidence-graph` required an uncached build-isolation `flit-core` download, unavailable in the offline execution environment.
- **Fix:** Ran all targeted and full locked test, Ruff, CLI-validation, formal-verification, and replay gates with `PYTHONPATH=src`; no dependency, lockfile, or project configuration changed.
- **Verification:** 143 passed, 1 deselected; Ruff check/format passed; sealed CLI validation, FormalRunStore verification, and replay passed.
- **Committed in:** `e26f34c` (task implementation; no environment files changed)

---

**Total deviations:** 1 auto-fixed (Rule 3). **Impact:** None on fixture bytes or validation semantics; the offline package-rebuild limitation remains environmental.

## Issues Encountered

- `uv` could not access its default cache outside the workspace, so the locked cache was set to `/private/tmp/tomorrowstar-uv-cache`. This is the same offline-only environment limitation recorded in Plan 02-04 and did not change tracked inputs.

## Known Stubs

None.

## User Setup Required

None - sealing, verification, and replay are local and provider-free.

## Next Phase Readiness

- Phase 03 can consume the sealed Contribution-grounded fixture and its preserved partial/conflict limitations.
- No score calibration, aggregation, confidence-admission, JD, resume, product, or employment-effect claim is authorized by this fixture.

## Self-Check: PASSED

- All declared source, CLI, review, formal-run, known-good, and test files exist.
- All four Task commits (`a5f2e0e`, `38836f0`, `a904b1b`, `e26f34c`) exist in Git.
- The canonical known-good hash matches the verified formal confirmed result, and exact recorded-response replay matched.

---
*Phase: 02-domain-contracts-stoa-fixture-and-deterministic-invariants*
*Completed: 2026-07-30*
