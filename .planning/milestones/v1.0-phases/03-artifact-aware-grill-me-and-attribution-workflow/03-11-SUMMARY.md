---
phase: 03-artifact-aware-grill-me-and-attribution-workflow
plan: "11"
subsystem: packaging
tags: [pep-660, editable-wheel, uv, cli, regression]
requires:
  - phase: 03-10
    provides: audit-root containment source implementation
provides:
  - Package-scoped editable import proxy that resolves current checkout source
  - Locked public CLI regression proving source authority
affects: [03-12, 03-13, phase-verification]
actuals:
  tokens: 1700
  tasks: 2
  commits: 4
tech-stack:
  added: []
  patterns: ["PEP 660 editable wheel contains a package-scoped source proxy only"]
key-files:
  created: []
  modified: [_career_evidence_build.py, tests/test_cli_tracer.py]
key-decisions:
  - "Editable wheels use a generated package initializer rather than a .pth or global startup hook."
  - "Ordinary wheels retain the full package inventory and no checkout-local path."
patterns-established:
  - "Installed-CLI proofs invoke uv run --locked career-evidence separately from pytest source-path tests."
requirements-addressed: [AUD-01, AUD-05]
requirements-completed: []
coverage:
  - id: D1
    description: Editable distribution delegates the package and all children to checkout source without copied business modules.
    requirement: AUD-01
    verification:
      - kind: integration
        ref: tests/test_cli_tracer.py#test_editable_wheel_uses_package_scoped_source_proxy_without_embedded_modules
        status: pass
    human_judgment: false
  - id: D2
    description: Locked public career-evidence command resolves checkout CLI and package initializer.
    requirement: AUD-05
    verification:
      - kind: integration
        ref: tests/test_cli_tracer.py#test_locked_editable_entrypoint_imports_checkout_source
        status: pass
    human_judgment: false
duration: 2min
completed: 2026-08-26
status: complete
---

# Phase 03 Plan 11: Installed CLI Source Authority Summary

**PEP 660 editable installs now load the checkout package through a package-scoped proxy, while ordinary wheels remain self-contained.**

## Performance

- **Duration:** 2 min
- **Started:** 2026-08-26T19:21:42Z
- **Completed:** 2026-08-26T19:23:56Z
- **Tasks:** 2
- **Files modified:** 2

## Accomplishments

- Replaced the editable wheel's copied package modules and ignored `.pth` file with a generated `career_evidence_graph` initializer that delegates package and child imports to `src`.
- Kept the ordinary wheel's complete package inventory, metadata, RECORD integrity, entry point, and checkout independence unchanged.
- Added archive-level and installed-public-CLI regressions that prove the checkout `__init__.py` and `cli.py` are imported after a locked reinstall.

## Task Commits

1. **Task 1: Make one editable import resolve through the checkout source** - `c66fd9e` (test), `ce2a1c7` (fix)
2. **Task 2: Prove the locked installed entry point imports current source** - `15ccef0` (test)
3. **Lint cleanup** - `2c48535` (style)

## Files Created/Modified

- `_career_evidence_build.py` - Produces an editable-only package initializer proxy and retains self-contained normal-wheel contents.
- `tests/test_cli_tracer.py` - Checks editable archive structure and locked installed entry-point source authority.

## Decisions Made

- The editable proxy is package-scoped: it sets the package search locations and executes the checkout initializer, avoiding global import hooks and `.pth` reliance.
- `implementation-path` is verified through the installed console entry point; a second installed-interpreter check confirms the root package was not spoofed.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Lint] Corrected generated-proxy encoding and test formatting.**
- **Found during:** Task 2
- **Issue:** Ruff rejected an unnecessary encoding argument and test assertion layout.
- **Fix:** Used default string encoding and applied Ruff-compatible assertion formatting.
- **Files modified:** `_career_evidence_build.py`, `tests/test_cli_tracer.py`
- **Verification:** Locked Ruff check and format check passed.
- **Committed in:** `2c48535`

**Total deviations:** 1 auto-fixed (Rule 1)

## Verification

- `uv sync --locked --reinstall-package career-evidence-graph && uv run --locked pytest -q tests/test_cli_tracer.py -k 'editable_wheel_uses_package_scoped_source_proxy_without_embedded_modules or built_wheel_is_self_contained_outside_the_checkout'` — 2 passed, 8 deselected.
- `uv sync --locked --reinstall-package career-evidence-graph && uv run --locked pytest -q tests/test_cli_tracer.py -k 'locked_editable_entrypoint_imports_checkout_source'` — 1 passed, 10 deselected.
- `uv sync --locked && uv run --locked pytest -q tests/test_cli_tracer.py` — 11 passed.
- `uv run --locked career-evidence implementation-path` — resolved `src/career_evidence_graph/cli.py`.
- `uv sync --locked && uv run --locked ruff check _career_evidence_build.py tests/test_cli_tracer.py` — passed.
- `uv sync --locked && uv run --locked ruff format --check _career_evidence_build.py tests/test_cli_tracer.py` — passed.

## Known Stubs

None.

## Next Phase Readiness

03-12 can now harden audit-root filesystem containment against post-validation path replacement. A fresh independent Phase 3 verification remains required before AUD-01 or AUD-05 may be marked complete.

## Self-Check: PASSED

- `_career_evidence_build.py` and `tests/test_cli_tracer.py` exist.
- Task commits `c66fd9e`, `ce2a1c7`, `15ccef0`, and `2c48535` exist.
