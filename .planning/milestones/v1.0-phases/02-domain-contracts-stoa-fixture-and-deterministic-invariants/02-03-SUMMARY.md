---
phase: 02-domain-contracts-stoa-fixture-and-deterministic-invariants
plan: "03"
subsystem: fixture-validation
tags: [python, pydantic, git, sha256, cli, pytest, stoa]
requires:
  - phase: 02-domain-contracts-stoa-fixture-and-deterministic-invariants
    provides: strict contribution-grounded models and offline CLI conventions
provides:
  - Pinned Git-object-only verification for the four STOA repositories and ten permitted documents
  - An unsealed one-Experience candidate ledger with durable-outcome grouping and source coverage
  - Field-separated human review status that prevents premature known-good sealing
affects: [02-04-stoa-human-review, 02-05-known-good-fixture, phase-03-grill-me]
tech-stack:
  added: []
  patterns:
    - Fixed source inventories are verified by allowlisted argv-only pinned Git-object reads.
    - Documentary candidates remain non-personal and unsealed until each decision family is reviewed.
key-files:
  created:
    - src/career_evidence_graph/domain/fixtures.py
    - validation/fixtures/stoa/v1/source-manifest.json
    - validation/fixtures/stoa/v1/candidates.json
    - validation/fixtures/stoa/v1/review.json
    - tests/test_stoa_fixture.py
  modified:
    - src/career_evidence_graph/domain/__init__.py
    - src/career_evidence_graph/cli.py
key-decisions:
  - "The sole STOA candidate Experience is grouped by durable outcome, never by repository, commit, ticket, or development phase."
  - "Only five non-plan document sources create candidate Evidence links; all plan-only sources remain background-only."
  - "Every candidate claim remains document-derived and non-personal with six independent pending review decisions."
patterns-established:
  - "Verify source bytes with `git -C REPOSITORY show PIN:TRACKED_PATH`, never with working-tree reads."
  - "Bind review records to the canonical candidate-ledger hash and report pending IDs deterministically."
requirements-completed: [FIX-01]
coverage:
  - id: D1
    description: "Pinned-document source manifest accepts only four fixed repositories and ten hashed tracked documents."
    requirement: FIX-01
    verification:
      - kind: integration
        ref: tests/test_stoa_fixture.py#test_source_manifest_verifies_exact_pinned_document_inventory
        status: pass
    human_judgment: false
  - id: D2
    description: "The document-derived STOA candidate/review packet remains unsealed pending separate truth decisions."
    requirement: FIX-01
    verification:
      - kind: integration
        ref: tests/test_stoa_fixture.py#test_review_status_has_six_pending_decision_groups_and_cannot_seal
        status: pass
    human_judgment: true
    rationale: "Pinned documents cannot establish personal responsibility, capability, accepted limitations, or fixture test values."
duration: 10 min
completed: 2026-07-30
status: complete
---

# Phase 02 Plan 03: Pinned STOA candidate and review packet Summary

**A Git-object-pinned, document-only STOA packet proposes four durable outcomes inside one Experience while retaining limitations, conflicts, and 24 pending human decisions.**

## Performance

- **Duration:** 10 min
- **Started:** 2026-07-30T14:46:33Z
- **Completed:** 2026-07-30T14:56:10Z
- **Tasks:** 2/2
- **Files modified:** 8 primary implementation and fixture files

## Accomplishments

- Added strict source-manifest verification for exactly four local repositories, four pinned commits, and ten named documentation Git objects; it has no working-tree fallback or network boundary.
- Created one `exp-stoa` candidate ledger with four durable-outcome Contributions, five non-plan Evidence sources, all ten document dispositions, explicit conflicts/limitations, and five planned-only background sources.
- Added an unsealed review packet with four claim items and six independently pending decision groups each; `fixture review-status` deterministically reports `sealable: false` with 24 pending decisions.

## Task Commits

1. **Task 1: Enforce the pinned document-only STOA source boundary** — `75e8e15` (TDD RED), `62aed7f` (TDD GREEN)
2. **Task 2: Produce the one-Experience durable-outcome candidate and review packet** — `0562afb` (TDD RED), `aca389a` (TDD GREEN)

## Files Created/Modified

- `src/career_evidence_graph/domain/fixtures.py` — strict source-boundary and unsealed packet contracts, verification, and review status.
- `src/career_evidence_graph/domain/__init__.py` — public fixture verification exports.
- `src/career_evidence_graph/cli.py` — offline `fixture source verify` and `fixture review-status` commands.
- `validation/fixtures/stoa/v1/source-manifest.json` — exact pin/path/proof-limit/hash inventory.
- `validation/fixtures/stoa/v1/candidates.json` — non-personal candidate proposal with source coverage and background-only plans.
- `validation/fixtures/stoa/v1/review.json` — four field-separated, entirely pending review items.
- `tests/test_stoa_fixture.py` — source-scope, candidate, conflict, planned-lineage, and sealing-blocker regressions.

## Decisions Made

- The candidate ledger keeps one STOA Experience and consolidates work by durable outcome, preserving audit conflicts and partial states instead of resolving them in the favorable direction.
- Documents labelled as plans—including backlog, system plan, ADR, deployment guide, and infrastructure README—are background-only and cannot form Evidence or assessment lineage.
- The review record is hash-bound to the proposal and exposes fact, attribution/assistance, Evidence-link, completion, limitation/conflict, and fixture-score/range decisions separately.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Rebuilt the local locked package before executing the green tests.**
- **Found during:** Task 1 TDD GREEN verification
- **Issue:** The installed local wheel lacked the newly added `career_evidence_graph.domain.fixtures` module.
- **Fix:** Ran `uv sync --locked --reinstall-package career-evidence-graph`; no dependency or lockfile changed.
- **Files modified:** None
- **Verification:** The focused suite, both offline CLI commands, and Ruff checks passed afterward.
- **Committed in:** Not applicable (local environment repair only)

---

**Total deviations:** 1 auto-fixed (1 Rule 3 blocking environment repair).
**Impact on plan:** No scope or dependency change; verification exercised the current locked source package.

## Issues Encountered

- The repository-wide suite was run once and stopped at the pre-existing `tests/test_cli_tracer.py::test_domain_fixture_rejects_missing_assessment_contribution` assertion. The Phase 02 invariant code now returns two additional violations for that malformed input; 02-03 did not modify the assertion or invariant module. It is recorded in `deferred-items.md`; focused 02-03 verification is green. The full suite was not retried.

## User Setup Required

None — all verification uses local pinned Git objects and the locked offline environment.

## Next Phase Readiness

- Plan 02-04 must perform the mandatory human review. Every candidate fact, attribution/assistance state, Evidence link, completion state, limitation/conflict, and fixture score/range remains pending.
- No `known-good.json` exists. This plan makes no calibrated mastery, aggregation, product, application, interview, or hiring-effectiveness conclusion.

## Self-Check

PASSED — all seven implementation/fixture paths and the 02-03 summary exist; TDD commits `75e8e15`, `62aed7f`, `0562afb`, and `aca389a` are present in Git history.

---
*Phase: 02-domain-contracts-stoa-fixture-and-deterministic-invariants*
*Completed: 2026-07-30*
