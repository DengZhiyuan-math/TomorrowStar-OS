---
phase: 02-domain-contracts-stoa-fixture-and-deterministic-invariants
plan: "02"
subsystem: domain-validation
tags: [python, pydantic, pytest, invariants, ontology-normalization]
requires:
  - phase: 02-domain-contracts-stoa-fixture-and-deterministic-invariants
    provides: Contribution-grounded domain contracts and canonical fixture hashing
provides:
  - Deterministic Contribution-only lineage, evidence, attribution, and user-Skill view invariants
  - Metadata-only Unicode alias and ontology normalization with pinned provenance
  - Canonical mastery snapshots that prove ontology metadata cannot change mastery
affects: [phase-02-fixtures, phase-03-grill-me, phase-04-assessment, phase-05-jd-comparison]
tech-stack:
  added: []
  patterns:
    - Pure validators return unique code/path-sorted violations and never repair fixtures
    - Skill alias and ontology records are descriptive metadata, isolated from mastery-bearing snapshots
key-files:
  created:
    - tests/test_domain_invariants.py
  modified:
    - src/career_evidence_graph/domain/models.py
    - src/career_evidence_graph/domain/invariants.py
    - src/career_evidence_graph/domain/__init__.py
key-decisions:
  - "The six prohibited direct sources are represented explicitly so each is rejected with assessment.direct-source-forbidden."
  - "UserSkillView retains only its specific Skill, mastery, admitted assessments, and fixture-expectation markers; supporting dimensions and JD data remain outside it."
  - "Ontology aliases and adjacency produce reviewable metadata only; mastery snapshots deliberately exclude that metadata."
patterns-established:
  - "Use stable `(code, path)` identities for invariant output, deduplicated and lexicographically sorted before publication."
  - "Use `mastery_snapshot_bytes` for tests that must prove metadata-only transforms cannot write capability state."
requirements-completed: [MOD-02, MOD-06, MOD-07]
coverage:
  - id: D1
    description: "Direct Experience, credential, title, repository, resume-list, and ontology paths cannot establish a user-Skill assessment."
    requirement: MOD-02
    verification:
      - kind: unit
        ref: tests/test_domain_invariants.py#test_direct_mastery_sources_are_rejected_with_the_same_sole_code
        status: pass
    human_judgment: false
  - id: D2
    description: "A fixture enforces one separated UserSkillView per assessed exact Skill and reports deterministic lineage, evidence, and attribution failures."
    requirement: MOD-06
    verification:
      - kind: unit
        ref: tests/test_domain_invariants.py
        status: pass
    human_judgment: false
  - id: D3
    description: "Unicode aliases and ontology relations are reviewable metadata that cannot change canonical mastery bytes."
    requirement: MOD-07
    verification:
      - kind: regression
        ref: tests/test_domain_invariants.py#test_ontology_relations_are_descriptive_metadata_and_cannot_change_mastery
        status: pass
    human_judgment: false
duration: 14 min
completed: 2026-07-30
status: complete
---

# Phase 02 Plan 02: Deterministic invariants and non-propagating normalization Summary

**Contribution-only assessment validation now rejects direct mastery shortcuts and exposes Unicode alias/ontology metadata without allowing it to create or alter user mastery.**

## Performance

- **Duration:** 14 min
- **Started:** 2026-07-30T14:28:00Z
- **Completed:** 2026-07-30T14:42:00Z
- **Tasks:** 2/2
- **Files modified:** 4

## Accomplishments

- Added pure lineage, Evidence-link, attribution, and user-Skill validators with unique, lexicographically sorted `(code, path)` violations.
- Rejected all six prohibited direct assessment sources and preserved exactly one separate mastery view per exact assessed Skill.
- Added deterministic NFKC/casefold/whitespace alias normalization, pinned ontology provenance, ambiguous-review states, and mastery-byte isolation tests.

## Task Commits

1. **Task 1: Reject direct mastery paths and enforce one separated user-Skill view** - `05f54b6` (TDD RED), `acd370a` (TDD GREEN)
2. **Task 2: Normalize Skill metadata without mastery propagation** - `21d5951` (TDD RED), `f210fa6` (TDD GREEN)
3. **Plan verification repair: serialize invariant results deterministically** - `e004657` (test)

## Files Created/Modified

- `src/career_evidence_graph/domain/models.py` - Closed assessment source vocabulary, separated UserSkillView fields, and metadata-only Skill normalization contracts.
- `src/career_evidence_graph/domain/invariants.py` - Deterministic pure invariant collection, normalization records, and canonical mastery snapshot generation.
- `src/career_evidence_graph/domain/__init__.py` - Public exports for the invariant and normalization APIs.
- `tests/test_domain_invariants.py` - MOD-02, MOD-06, and MOD-07 regressions for direct sources, ordering, attribution, views, Unicode aliases, and ontology isolation.

## Decisions Made

- Direct-source and user-Skill invariant codes may use hyphenated domain namespaces required by the plan (`assessment.direct-source-forbidden`, `user-skill.*`).
- Phase 2 UserSkillView values remain fixture-test expectations; this plan adds no aggregation, confidence-admission rule, or calibrated capability claim.
- Ontology relationships are represented as descriptive, pinned metadata only and never as an assessment or user view input/output.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing Critical] Allowed the plan's stable hyphenated invariant namespaces.**
- **Found during:** Task 1
- **Issue:** The inherited invariant-code pattern rejected the required `assessment.direct-source-forbidden` and `user-skill.*` codes before callers could observe a stable violation.
- **Fix:** Expanded the code grammar to permit hyphens within a namespace segment while retaining the structured dotted-code constraint.
- **Files modified:** `src/career_evidence_graph/domain/models.py`
- **Verification:** All direct-source and user-Skill invariant regressions pass.
- **Committed in:** `acd370a`

**2. [Rule 3 - Blocking] Rebuilt the already-locked local package before GREEN verification.**
- **Found during:** Task 1
- **Issue:** `uv run --locked` initially imported the prior local wheel, which lacked the new invariant exports.
- **Fix:** Ran `uv sync --locked --reinstall-package career-evidence-graph`; no dependency or lockfile changed.
- **Files modified:** None
- **Verification:** The current source package ran the complete invariant suite twice successfully.
- **Committed in:** Not applicable (local environment repair only)

**3. [Rule 1 - Bug] Made the ordering regression serialize Pydantic violations as JSON-ready records.**
- **Found during:** Plan-level verification
- **Issue:** `canonical_json_bytes` accepts a top-level Pydantic model, not a tuple of models, so the assertion itself raised `TypeError`.
- **Fix:** Serialized each invariant violation with `model_dump(mode="json")` before canonical byte comparison.
- **Files modified:** `tests/test_domain_invariants.py`
- **Verification:** `uv run --locked pytest -q tests/test_domain_invariants.py` passes twice.
- **Committed in:** `e004657`

---

**Total deviations:** 3 auto-fixed (1 Rule 1 bug, 1 Rule 2 critical contract, 1 Rule 3 local environment repair).
**Impact on plan:** All changes were required to expose the plan's stable contracts and execute the locked test environment; no aggregation, scoring, provider, network, or STOA scope was added.

## Issues Encountered

The local editable package retained a pre-plan wheel until rebuilt from the locked project. This was resolved without changing dependencies or lockfiles.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Phase 02 fixture plans can consume strict deterministic invariant codes and use `mastery_snapshot_bytes` to detect unauthorized metadata-to-mastery propagation.
- STOA evidence review remains a later human checkpoint; this plan neither inspected STOA implementation code nor inferred personal capability.

## Self-Check

PASSED - all four planned source/test files exist; commits `05f54b6`, `acd370a`, `21d5951`, `f210fa6`, and `e004657` are present; the complete invariant suite passed twice with repository lint and formatting checks green.

---
*Phase: 02-domain-contracts-stoa-fixture-and-deterministic-invariants*
*Completed: 2026-07-30*
