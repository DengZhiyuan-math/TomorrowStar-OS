---
phase: 03-artifact-aware-grill-me-and-attribution-workflow
plan: "13"
subsystem: testing
tags: [uv, editable-install, cli, pytest, audit-containment]
requires:
  - phase: 03-11
    provides: package-scoped editable source authority
  - phase: 03-12
    provides: descriptor-anchored audit containment
provides:
  - Fresh-environment installed CLI containment regression
  - Measured, complete Phase 3 probe inventory
affects: [phase-verification, audit-storage]
actuals:
  tokens: 6330
  tasks: 2
  commits: 4
tech-stack:
  added: []
  patterns: [fresh UV_PROJECT_ENVIRONMENT public-CLI proof, exact pytest node inventory]
key-files:
  created: [tests/test_audit_installation_regressions.py]
  modified: [tests/test_validation_probe_matrix.py, 03-13-PLAN.md]
key-decisions:
  - "Installed-CLI containment is proved in a fresh UV environment without source launchers or PYTHONPATH."
  - "The acceptance matrix records all 20 measured gap probes instead of suppressing the pre-existing package-proxy probe."
requirements-addressed: [AUD-01, AUD-02, AUD-04, AUD-05]
requirements-completed: []
coverage:
  - id: D1
    description: Fresh installed public CLI resolves checkout source, permits normal custody, and rejects redirected audit roots without external mutation.
    requirement: AUD-01
    verification:
      - kind: integration
        ref: tests/test_audit_installation_regressions.py#test_fresh_locked_installed_cli_preserves_audit_root_containment
        status: pass
    human_judgment: false
  - id: D2
    description: Exact Phase 3 probe inventory preserves every original and closure marker.
    requirement: AUD-05
    verification:
      - kind: integration
        ref: tests/test_validation_probe_matrix.py#test_all_28_original_and_twenty_gap_probes_are_collected
        status: pass
    human_judgment: false
duration: 22min
completed: 2026-08-26
status: complete
---

# Phase 03 Plan 13: Installed Containment and Probe Gate Summary

**A fresh locked editable installation now proves the real public CLI uses checkout source and cannot write through a linked audit root, while the acceptance matrix preserves all 20 measured gap probes.**

## Accomplishments

- Added a fresh `UV_PROJECT_ENVIRONMENT` regression that uses only `uv run --locked career-evidence`, validates its implementation path, exercises a normal audit, and preserves an external redirected-root tree byte-for-byte.
- Replaced the source-wrapper collection helper with literal locked `uv run pytest` collection and recorded the complete ordered 20-node gap inventory alongside the 28 original probes.
- Passed the synchronized full suite and Ruff gates.

## Task Commits

1. **Task 1: Run the installed audit start in a fresh locked environment** - `4f34fca` (test), `d23c5e7` (style)
2. **Task 2: Register all closure probes and run the complete synchronized gate** - `4bc05a2` (test)
3. **Approved planning correction** - `51f1a18` (docs)

## Verification

- `uv sync --locked --reinstall-package career-evidence-graph && uv run --locked pytest -q tests/test_audit_installation_regressions.py` — 1 passed.
- Exact `phase03_gap_probe` collection — 20 collected, 26 deselected.
- `uv sync --locked && uv run --locked pytest -q` — 239 passed, 1 deselected.
- `uv sync --locked && uv run --locked ruff check .` — passed.
- `uv sync --locked && uv run --locked ruff format --check .` — 50 files already formatted.

## Deviations from Plan

### Approved plan correction

The plan initially expected 19 gap probes. Actual collection proved 20: the retained 15-node baseline plus two 03-11 CLI probes, two 03-12 storage probes, and this plan's installed-CLI probe. With user approval, the plan and matrix were corrected to retain every existing marker; none was de-marked or excluded.

## Known Stubs

None.

## Next Phase Readiness

The remediation plan is complete. Phase requirements remain pending fresh independent verification.

## Self-Check: PASSED

- `tests/test_audit_installation_regressions.py` and `tests/test_validation_probe_matrix.py` exist.
- Commits `4f34fca`, `d23c5e7`, `51f1a18`, and `4bc05a2` exist.
