---
phase: 01-validation-charter-provenance-and-technical-decision-gate
plan: 02
subsystem: validation-security
tags: [codex-cli, luna, security, negative-cases, jsonl, provenance]

requires:
  - phase: 01-validation-charter-provenance-and-technical-decision-gate
    provides: Immutable offline tracer, exact replay, charter, and provenance registry
provides:
  - Independent blocking acceptance cases for all six critical failure classes
  - Shell-free, read-only Codex CLI adapter fixed to gpt-5.6-luna with medium reasoning
  - Opt-in live technical gate with retained JSONL, model-drift limits, and operator documentation
affects: [phase-02-fixtures, phase-03-audit, phase-04-assessment]

tech-stack:
  added: []
  patterns:
    - Fixed argv subprocess execution with shell disabled and an allowlisted environment
    - Default-off live-model tests separated from deterministic offline verification
    - Untrusted subprocess output retained raw but validated before formal publication

key-files:
  created:
    - src/career_evidence_graph/codex_cli.py
    - src/career_evidence_graph/validation/acceptance.py
    - tests/test_codex_cli.py
    - tests/test_security_boundaries.py
    - docs/validation-runs.md
  modified:
    - src/career_evidence_graph/cli.py
    - src/career_evidence_graph/validation/models.py
    - src/career_evidence_graph/validation/store.py
    - validation/provenance/registry.json

key-decisions:
  - "A live Codex invocation is an explicitly opted-in technical gate, not Phase 1 functional acceptance."
  - "The default suite never calls a model; it validates the runtime seam with injected recorded subprocess results."
  - "An alias-based model run requires retained raw output and an explicit drift limitation before formal storage."

patterns-established:
  - "Critical blockers are conjunctive: any one blocker rejects acceptance and cannot be averaged away."
  - "Live boundary: fixed read-only argv, shell disabled, allowlisted environment, redacted diagnostics, and fail-closed publication."
  - "Claims boundary: runtime viability is distinct from STOA case acceptance and job-search effectiveness."

requirements-completed: [VAL-01, VAL-02, OSS-01]

coverage:
  - id: D1
    description: "All six critical failure classes and hostile storage/replay inputs independently block acceptance without mutating accepted bytes."
    requirement: VAL-01
    verification:
      - kind: integration
        ref: "tests/test_security_boundaries.py"
        status: pass
      - kind: integration
        ref: "tests/test_run_store.py"
        status: pass
    human_judgment: false
  - id: D2
    description: "The Luna medium Codex CLI seam is shell-free, read-only, observable, drift-limited, and excluded from default live execution."
    requirement: VAL-02
    verification:
      - kind: integration
        ref: "tests/test_codex_cli.py"
        status: pass
      - kind: live-model
        ref: "tests/test_codex_cli.py::test_opt_in_live_luna_medium_smoke"
        status: not-run-optional
    human_judgment: false
  - id: D3
    description: "Operator commands, coverage exclusions, and recognizable provider-port provenance are synchronized and machine checked."
    requirement: OSS-01
    verification:
      - kind: unit
        ref: "tests/test_provenance.py"
        status: pass
      - kind: integration
        ref: "career-evidence provenance verify"
        status: pass
    human_judgment: false

duration: 9min
completed: 2026-07-30
status: complete
---

# Phase 1 Plan 2: Security Cases and Codex Luna Technical Gate Summary

**The offline tracer now rejects every critical failure independently and exposes a tested, explicit opt-in Codex CLI Luna-medium runtime seam without claiming a live model result.**

## Performance

- **Duration:** 9 min
- **Started:** 2026-07-30T09:35:09Z
- **Completed:** 2026-07-30T09:43:52Z
- **Tasks:** 3
- **Files modified:** 19

## Accomplishments

- Added deterministic blockers for fabrication, attribution errors, duplicate evidence, broken lineage, material instability, and non-reproducibility, plus hostile path, symlink, corruption, and replay-boundary cases.
- Integrated `codex exec` through a fixed argument vector using `gpt-5.6-luna`, `medium` reasoning, structured JSON output, a read-only sandbox, an allowlisted environment, and no shell.
- Added retained JSONL and invocation metadata, alias-drift limitations, secret-redacted diagnostics, operator instructions, test-backed coverage, and synchronized upstream provenance.

## Task Commits

Each task was committed atomically:

1. **Task 1: Add deterministic critical negative and security cases** - `bfa9a7e`
2. **Task 2: Integrate Codex CLI Luna medium behind an opt-in live gate** - `a53344e`
3. **Task 3: Close operator documentation, coverage, and provenance** - `510754c`

## Files Created/Modified

- `src/career_evidence_graph/validation/acceptance.py` - Independent critical-blocker evaluation.
- `src/career_evidence_graph/codex_cli.py` - Shell-free Codex invocation, JSONL parsing, metadata capture, and drift policy.
- `tests/test_security_boundaries.py` - Critical negative and filesystem/replay attack cases.
- `tests/test_codex_cli.py` - Recorded subprocess contracts and a separately marked live smoke.
- `docs/validation-runs.md` - Offline and opt-in live operator contract with claim limits.
- `validation/provenance/registry.json` - Provider-port provenance record.

## Decisions Made

- Kept the real model smoke explicitly opt-in and did not invoke it during ordinary phase execution.
- Treated a successful live invocation only as evidence that the selected runtime/configuration can cross the technical boundary.
- Required formal storage to fail closed on malformed streams, non-zero exits, missing metadata, path escapes, or unbounded model alias drift.

## Deviations from Plan

None. The planned negative cases, runtime adapter, documentation, coverage, and provenance were implemented within scope.

## Issues Encountered

All implementation issues were resolved. No functional implementation blocker remains.

## User Setup Required

None for offline validation. The optional live smoke requires an authenticated Codex CLI and `CAREER_EVIDENCE_ENABLE_LIVE_MODEL=1`.

## Next Phase Readiness

Phase 2 can introduce the first real, user-provided STOA fixture. Phase 1 has not evaluated a STOA case and does not establish product or job-search effectiveness.

## Self-Check: PASSED

- `uv run --locked pytest -q` passes with 49 tests and 1 explicitly deselected live-model smoke.
- `uv run --locked ruff check .` and `ruff format --check .` pass.
- `career-evidence validate-charter` and `career-evidence provenance verify` pass.
- The optional live test is collected under the `live_model` marker but was not run.

---
*Phase: 01-validation-charter-provenance-and-technical-decision-gate*
*Completed: 2026-07-30*
