---
phase: 07-career-source-custody-and-private-workspace
plan: 08
subsystem: private-workspace-custody
tags: [python, git, security, symlink, unicode, raw-cleanup, synthetic-tests]
requires:
  - phase: 07-07
    provides: explicit-commit custody verification and single-process mutation boundary
provides:
  - component-safe semantic custody routing for private workspace paths
  - recursive rejection of bidi embedding, override, and isolate controls
  - explicit-baseline raw cleanup that preserves committed and working references
affects: [phase-07-verification, private-workspace-custody, career-source-cli]
actuals:
  tokens: 8411.75
  tasks: 3
  commits: 5
tech-stack:
  added: []
  patterns:
    - one PrivateWorkspace component-safe resolver remains the semantic path authority
    - cleanup combines exact committed and current working semantic reference inventories before unlinking
key-files:
  created: []
  modified:
    - src/career_evidence_graph/career_sources.py
    - src/career_evidence_graph/domain/models.py
    - src/career_evidence_graph/cli.py
    - tests/test_career_source_security.py
    - tests/test_career_source_custody.py
key-decisions:
  - "Capture and transform CLI mutations require a caller-supplied full baseline OID; they do not derive authority from HEAD, refs, or mutable pointers."
  - "Only an attempt-created raw object absent from both exact committed and validated working inventories may be unlinked."
patterns-established:
  - "Reject hostile bidi controls recursively at the career-source model boundary and before raw-byte hashing."
  - "Keep all public security assertions synthetic and content-free."
requirements-completed: [INV-06, INV-07]
coverage:
  - id: D1
    description: Semantic namespace symlinks fail safely without creating synthetic files outside the selected workspace.
    requirement: INV-07
    verification:
      - kind: integration
        ref: "tests/test_career_source_security.py#test_semantic_namespace_symlink_rejects_capture_without_outside_write"
        status: pass
    human_judgment: false
  - id: D2
    description: All nine bidi controls are rejected from raw bytes and nested custody contracts before publication.
    requirement: INV-07
    verification:
      - kind: unit
        ref: "tests/test_career_source_security.py#test_bidi_controls_are_rejected_before_raw_or_structured_custody"
        status: pass
    human_judgment: false
  - id: D3
    description: Failed explicit-baseline publication removes only a newly created unreferenced raw object.
    requirement: INV-06
    verification:
      - kind: integration
        ref: "tests/test_career_source_custody.py#test_raw_cleanup_removes_only_new_unreferenced_attempt_object"
        status: pass
    human_judgment: false
duration: 27m
completed: 2026-08-30
status: complete
---

# Phase 07 Plan 08: Private Workspace Boundary Closure Summary

**Career-source custody now confines semantic paths, rejects ambiguous bidi controls, and uses an explicit committed baseline plus current working references before removing failed-attempt raw bytes.**

## Performance

- **Duration:** 27m
- **Completed:** 2026-08-30T22:44:12Z
- **Tasks:** 3/3
- **Files modified:** 5

## Accomplishments

- Routed semantic capture, transform, raw, and root paths through the existing component-safe `PrivateWorkspace` seam, returning redacted safe failures for namespace symlinks.
- Added one recursive domain guard for U+202A–U+202E and U+2066–U+2069, and applied it before raw hashing and structured record serialization.
- Required CLI capture/transform mutation baselines, and cleaned only exact attempt-created raw objects after the union of committed and working references proves absence.

## Task Commits

1. **Task 1: Enforce component-safe semantic operations** — `0c7e691` (RED), `eaa8b5b` (feature)
2. **Task 2: Reject bidi controls before publication** — `3fe5e02` (RED), `863a59e` (feature)
3. **Task 3: Guard failed raw cleanup with exact references** — `acb11f9` (feature and synthetic regression)

## Verification

- `uv run --locked python scripts/run_pytest.py tests/test_career_source_security.py tests/test_career_source_custody.py tests/test_domain_models.py tests/test_cli_tracer.py -x` — **165 passed**
- `uv run --locked ruff check src/career_evidence_graph/workspace.py src/career_evidence_graph/domain/models.py src/career_evidence_graph/career_sources.py src/career_evidence_graph/cli.py tests/test_career_source_security.py tests/test_career_source_custody.py` — **passed**

The repository's source-selecting pytest runner was used because direct `uv run --locked pytest` imports a stale installed package in this checkout.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Verification integrity] Preserved the source-aware synthetic CLI flow under mandatory mutation baselines**
- **Found during:** Task 3
- **Issue:** Existing CLI harness paths did not create and pass the full baseline commits newly required before capture and transform mutation.
- **Fix:** Updated only temporary synthetic Git fixture setup to commit declaration/capture baselines and pass their exact OIDs.
- **Files modified:** `tests/test_career_source_security.py`, `tests/test_career_source_custody.py`
- **Verification:** Complete 165-test source-aware suite passed.
- **Committed in:** `acb11f9`

**Total deviations:** 1 auto-fixed verification-integrity adjustment. No real career data, private repository, or external workspace was accessed.

## Self-Check: PASSED

- Confirmed all five implementation/test files and this summary exist.
- Confirmed commits `0c7e691`, `eaa8b5b`, `3fe5e02`, `863a59e`, and `acb11f9` exist in Git history.
