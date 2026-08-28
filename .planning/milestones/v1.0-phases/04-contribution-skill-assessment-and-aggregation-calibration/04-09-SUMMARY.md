---
phase: 04-contribution-skill-assessment-and-aggregation-calibration
plan: "09"
subsystem: assessment-audit-custody
tags: [python, pydantic, reassessment, audit-custody, authority-partition, offline]
requires:
  - phase: 04-contribution-skill-assessment-and-aggregation-calibration
    provides: immutable assessment versions, completed-audit materialization, and authority-partitioned aggregation
provides:
  - reassessment derived only from a completed and confirmed later audit
  - canonical source-envelope comparison before append-only sidecar replacement
  - black-box regressions for fabricated audit provenance and caller identity mutations
affects: [independent-verification, security-review, phase-05-jd-usefulness]
completion_authority: independent_verification
actuals:
  tokens: 6227
  tasks: 2
  commits: 7
tech-stack:
  added: []
  patterns:
    - reuse _materialize_audit as the sole audit custody authority for initial assessment and reassessment
    - treat reassessment caller fields as expected identities and compare them to a canonical later-audit proposal before persistence
key-files:
  created:
    - .planning/phases/04-contribution-skill-assessment-and-aggregation-calibration/04-09-SUMMARY.md
  modified:
    - src/career_evidence_graph/assessment.py
    - src/career_evidence_graph/cli.py
    - tests/test_assessment_admission.py
    - tests/test_assessment_cli.py
    - .planning/phases/04-contribution-skill-assessment-and-aggregation-calibration/04-VALIDATION.md
key-decisions:
  - "Reassessment derives the persisted audit ID and source envelope from a materialized later audit; CLI audit IDs are expected identities only."
  - "Later evidence retains the current source-authority partition and canonical proposal identity, then resets substantive review on the newly appended version."
patterns-established:
  - "Audit-backed mutation paths validate all custody and identity inputs before their sole persistence boundary."
requirements-addressed: [ASS-01, AGG-01, AGG-03]
requirements-completed: []
coverage:
  - id: D1
    description: "Caller-fabricated audit provenance, authority, and identity mutations cannot append reassessment versions."
    requirement: ASS-01
    verification:
      - kind: integration
        ref: tests/test_assessment_cli.py::test_reassess_cli_rejects_fabricated_audit_and_authority_without_mutation
        status: pass
      - kind: integration
        ref: tests/test_assessment_cli.py::test_reassess_cli_rejects_each_caller_identity_permutation_without_mutation
        status: pass
    human_judgment: false
  - id: D2
    description: "A completed confirmed later audit appends one hash-linked version while preserving authority and immutable history."
    requirement: AGG-01
    verification:
      - kind: integration
        ref: tests/test_assessment_admission.py::test_insufficient_review_and_later_evidence_preserve_immutable_versions
        status: pass
      - kind: e2e
        ref: tests/test_assessment_cli.py::test_reassess_cli_appends_a_materialized_later_audit_version
        status: pass
    human_judgment: false
  - id: D3
    description: "Stale reassessment hashes reject before later-corpus loading and preserve sidecar bytes."
    requirement: AGG-03
    verification:
      - kind: integration
        ref: tests/test_assessment_admission.py::test_reassessment_rejects_stale_hash_before_later_corpus_loading
        status: pass
      - kind: e2e
        ref: tests/test_assessment_cli.py::test_explicit_reassess_rejects_stale_hash_without_mutating_sidecar
        status: pass
    human_judgment: false
duration: 32min
completed: 2026-08-28
status: complete
---

# Phase 04 Plan 09: Reassessment Audit Custody Summary

**Reassessment now materializes a completed, confirmed later audit and rejects caller-forged custody or authority before immutable assessment history can change.**

## Performance

- **Duration:** 32 min
- **Tasks:** 2/2
- **Files modified:** 5
- **Implementation revision:** `e009b082d4e0bc5d852268457d1629113c76078f`
- **Final regression revision:** `fb74ced`

## Accomplishments

- Extracted one canonical assessment source-envelope builder and retained `_materialize_audit` as the sole completed-and-confirmed audit authority.
- Required `assessment reassess --later-corpus` and derived every persisted custody identity from that corpus's materialized audit.
- Added service and black-box controls for fabricated IDs, source envelopes, authority/origin/status, assessment/Skill/Contribution/lineage identities, stale-hash ordering, immutable history, and valid append-only reassessment.
- Recorded measured local offline evidence without changing `.planning/STATE.md`, `.planning/ROADMAP.md`, or `.planning/REQUIREMENTS.md`.

## Task Commits

1. **Task 1 RED: Cover canonical reassessment custody** — `3aad515` (test)
2. **Task 1 GREEN: Materialize reassessment audit custody** — `50e6103` (fix)
3. **Task 2 RED: Prove reassessment CLI custody boundary** — `7b6c8eb` (test)
4. **Task 2 GREEN: Require corpus-backed reassessment** — `e009b08` (feat)
5. **Task 2 expanded controls: Cover reassessment identity permutations** — `fb74ced` (test)
6. **Measured gates: Record reassessment custody gates** — `1735f73` (docs)

## Decisions Made

- A caller may name an expected later audit ID, but the persisted audit ID, snapshot/conclusion hashes, fixture/manifest hashes, content identities, and authority come only from the materialized later audit.
- Derived calibration remains `derived-counterfactual`; reassessment cannot relabel it as reviewed user truth or use it to cross the established authority partition.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Test fixture] Completed the copied sealed-fixture custody bundle for the later-audit regression.**
- **Found during:** Task 1 RED
- **Issue:** The first temporary later-corpus helper copied only the fixture and manifest, while the existing sealed-fixture loader correctly also requires its hash-bound review and checkpoint summary.
- **Fix:** Reused the complete existing fixture directory and the required checkpoint summary in the temporary repository-shaped test layout.
- **Files modified:** `tests/test_assessment_admission.py`
- **Verification:** Real completed/confirmed later-audit service and CLI controls pass.
- **Committed in:** `3aad515`

**2. [Rule 1 - Quality gate] Corrected newly introduced Ruff formatting and line-length findings.**
- **Found during:** Task 1 and Task 2 verification
- **Fix:** Wrapped two workflow-error/model-validation lines and normalized test imports/formatting.
- **Files modified:** `src/career_evidence_graph/assessment.py`, `tests/test_assessment_cli.py`
- **Verification:** `ruff check .` and `ruff format --check .` pass.
- **Committed in:** `50e6103`, `e009b08`

**Total deviations:** 2 auto-fixed Rule 1 corrections; no scope expansion or dependency changes.

## Verification

- Focused reassessment gates: **13 passed, 27 deselected in 7.80s**.
- Full deterministic offline suite: exited 0.
- `ruff check .` and `ruff format --check .`: both exited 0.
- The decisive black-box `audit-fabricated` plus `reviewed-user-truth` attempt exits 2 and preserves sidecar bytes exactly.

## Known Stubs

None.

## Next Phase Readiness

This independent gap-closure execution addresses `ASS-01`, `AGG-01`, and `AGG-03` but completes none of them. It does not promote Phase 04, the milestone, or any shared planning status. Fresh independent code review, security review, and goal verification must run against the unchanged implementation revision before any promotion.

## Self-Check: PASSED

- All five modified artifacts and this SUMMARY exist.
- Task commits `3aad515`, `50e6103`, `7b6c8eb`, `e009b08`, `fb74ced`, and `1735f73` exist in repository history.
