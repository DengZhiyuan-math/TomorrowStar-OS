---
phase: 01-validation-charter-provenance-and-technical-decision-gate
plan: 01
subsystem: validation
tags: [pydantic, json, sha256, replay, provenance, uv]

requires: []
provides:
  - Versioned functional-only validation charter with no fictional STOA case
  - Immutable formal-run bundles, linked reruns, correction history, and exact replay
  - Machine-validated upstream provenance synchronized with the human reuse matrix
affects: [phase-02-fixtures, phase-03-audit, phase-04-assessment, phase-05-evaluation]

tech-stack:
  added: [CPython 3.13.14, Pydantic 2.13.4, pytest 9.1.1, Ruff 0.16.0, uv 0.12.0]
  patterns:
    - Strict schema-versioned Pydantic contracts with extra fields forbidden
    - Canonical JSON and SHA-256 content manifests
    - Atomic immutable directory publication with linked reruns
    - Exact recorded-response replay without a live provider

key-files:
  created:
    - validation/charter/v1.json
    - validation/provenance/registry.json
    - src/career_evidence_graph/validation/store.py
    - src/career_evidence_graph/validation/replay.py
    - src/career_evidence_graph/validation/provenance.py
  modified:
    - references/README.md
    - pyproject.toml

key-decisions:
  - "Phase 1 charter remains functional-chain-only with case_count zero and no product-effectiveness authority."
  - "Formal corrections coexist with the immutable original proposal; reruns create linked bundles rather than overwriting history."
  - "Recognizable subsystem adaptations use central provenance records; no line-level copied-code claim is made."

patterns-established:
  - "Formal artifact pattern: canonical bytes, declared hashes, atomic publication, and fail-closed verification."
  - "Replay boundary: exact replay reads only retained raw output and never invokes a live runner."
  - "Provenance gate: reuse requires exact paths while adapt/inspired-by use tested subsystem records."

requirements-completed: [VAL-01, VAL-02, OSS-01]

coverage:
  - id: D1
    description: "The functional charter fixes scope, blockers, comparison policy, and future case eligibility without inventing STOA evidence."
    requirement: VAL-01
    verification:
      - kind: unit
        ref: "tests/test_charter.py"
        status: pass
      - kind: integration
        ref: "career-evidence validate-charter validation/charter/v1.json"
        status: pass
    human_judgment: false
  - id: D2
    description: "Formal runs preserve complete input hashes, immutable lineage, corrections, and exact offline replay."
    requirement: VAL-02
    verification:
      - kind: integration
        ref: "tests/test_run_store.py"
        status: pass
      - kind: integration
        ref: "tests/test_replay.py"
        status: pass
      - kind: e2e
        ref: "tests/test_cli_tracer.py"
        status: pass
    human_judgment: false
  - id: D3
    description: "Implemented upstream adaptations are machine validated and synchronized with references/README.md."
    requirement: OSS-01
    verification:
      - kind: unit
        ref: "tests/test_provenance.py"
        status: pass
      - kind: integration
        ref: "career-evidence provenance verify"
        status: pass
    human_judgment: false

duration: 28min
completed: 2026-07-30
status: complete
---

# Phase 1 Plan 1: Offline Validation and Provenance Foundation Summary

**A functional-only charter now drives immutable formal bundles, linked correction history, exact offline replay, and fail-closed upstream provenance checks.**

## Performance

- **Duration:** 28 min
- **Started:** 2026-07-30T09:03:37Z
- **Completed:** 2026-07-30T09:31:40Z
- **Tasks:** 3
- **Files modified:** 22

## Accomplishments

- Locked D-01 through D-09 into a strict charter with zero cases, no holdout eligibility, five blocking failure classes, and an explicit product-effectiveness prohibition.
- Built immutable formal-run storage with complete lineage hashes, linked reruns, preserved reviewer corrections, tamper detection, and exact replay from recorded output.
- Added a strict provenance registry for the three upstream subsystem patterns actually introduced and synchronized it with the human reuse matrix.

## Task Commits

Each task was committed atomically:

1. **Task 1: Build the offline charter-to-replay vertical tracer** - `b3e2395`
2. **Task 2: Complete immutable formal-run lineage and correction history** - `040d860`
3. **Task 3: Enforce exact and subsystem-level open-source provenance** - `d86fc0d`

## Files Created/Modified

- `validation/charter/v1.json` - Machine-readable functional validation boundary and eligibility rules.
- `src/career_evidence_graph/validation/models.py` - Strict charter, run, correction, replay, and provenance contracts.
- `src/career_evidence_graph/validation/store.py` - Atomic immutable run publication, verification, and linked reruns.
- `src/career_evidence_graph/validation/replay.py` - Provider-free exact replay.
- `validation/provenance/registry.json` - Actual Phase 1 subsystem adaptation records.
- `references/README.md` - Human-readable registry synchronization table.
- `tests/` - Charter, CLI, storage, replay, tamper, path, and provenance coverage.

## Decisions Made

- Kept the tracer synthetic and limited to plumbing; it is not a user case or acceptance result.
- Required all seven reproducibility input categories on every formal manifest.
- Stored corrections inside the new immutable bundle and required each correction to retain the complete original proposal and its hash.
- Used subsystem-level `adapt` and `inspired-by` records because no upstream code or data was copied verbatim.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Replaced hidden editable-path dependency**
- **Found during:** Task 1
- **Issue:** Repeated `uv run` on this macOS workspace marked editable `.pth` files hidden; CPython 3.13.14 then skipped them.
- **Fix:** Added a narrow PEP 517 shim that uses Flit's full wheel for the editable hook, preserving repeatable imports without weakening Python path safety.
- **Files modified:** `_build_backend.py`, `pyproject.toml`
- **Verification:** The locked target suite passed repeatedly in fresh subprocesses.
- **Committed in:** `b3e2395`

**2. [Rule 3 - Blocking] Scoped Ruff away from pinned upstream submodules**
- **Found during:** Task 3
- **Issue:** `ruff check .` inspected six read-only upstream repositories and reported their unrelated historical lint findings.
- **Fix:** Excluded `.planning/` and `references/upstream/` while retaining checks over every local Python source and test.
- **Files modified:** `pyproject.toml`
- **Verification:** `uv run --locked ruff check .` and `ruff format --check .` pass.
- **Committed in:** `d86fc0d`

---

**Total deviations:** 2 auto-fixed blocking environment/tooling issues.
**Impact on plan:** Both changes make the specified repeatable verification commands work without changing the validation scope.

## Issues Encountered

All encountered issues were resolved. No implementation blocker remains.

## User Setup Required

None - default verification is offline and requires no external service configuration.

## Next Phase Readiness

Plan 01-02 can now add adversarial negative cases and the opt-in Codex CLI `gpt-5.6-luna` medium technical gate on top of stable run, replay, and provenance boundaries.

## Self-Check: PASSED

- All declared key files exist.
- Three `01-01` task commits exist.
- `uv run --locked pytest -q` passes with 19 tests.
- `uv run --locked ruff check .` and `ruff format --check .` pass.
- `career-evidence validate-charter` and `career-evidence provenance verify` pass.

---
*Phase: 01-validation-charter-provenance-and-technical-decision-gate*
*Completed: 2026-07-30*
