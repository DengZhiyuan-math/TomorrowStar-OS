---
phase: 02
fixed_at: 2026-07-30T16:56:49Z
review_path: .planning/phases/02-domain-contracts-stoa-fixture-and-deterministic-invariants/02-REVIEW.md
iteration: 3
findings_in_scope: 1
fixed: 1
skipped: 0
status: all_fixed
---

# Phase 02: Code Review Fix Report

**Fixed at:** 2026-07-30T16:56:49Z
**Source review:** `.planning/phases/02-domain-contracts-stoa-fixture-and-deterministic-invariants/02-REVIEW.md`
**Iteration:** 3

**Summary:**

- Findings in scope: 1
- Fixed: 1
- Skipped: 0

## Fixed Issues

### CR-01 regression: fresh-cache offline wheel build requires an uncached Flit backend

**Files modified:** `pyproject.toml`, `_career_evidence_build.py`, `tests/test_cli_tracer.py`
**Commit:** `4470947`
**Applied fix:** Replaced the third-party Flit build requirement with a project-local, standard-library PEP 517/660 backend. Regular wheels now contain only deterministic package/metadata members, a valid hashed `RECORD`, and the console entry-point metadata; they contain no checkout path, `.pth`, or `sitecustomize`. The PEP 660 editable path is deliberately separate and uses an environment-local `.pth` only for checkout development. The isolated regression now creates a fresh `UV_CACHE_DIR`, builds offline, installs outside the checkout, validates installed package/CLI metadata paths, rejects source-path hooks, and verifies every wheel `RECORD` hash and size.

## Prior Fixes Retained

- `d7edfb6` / `ac2bb7d` — closed the original wheel-import hook issue and aligned checkout launchers with the verification gates.
- `af7ca21` — sealed fixture validation recomputes and cross-binds the source-manifest, review, checkpoint, and v2 FormalRun lineage.
- `19a48ac` — review materialization requires the confirmed human reviewer identity.

## Verification

- Fresh `UV_CACHE_DIR` + `UV_OFFLINE=1`: `uv build --wheel --offline` passed.
- `uv sync --locked --offline` passed; locked launcher test path works without `PYTHONPATH`.
- Phase 1 regression files: `58 passed, 1 deselected`.
- Full locked suite: `173 passed, 1 deselected`.
- `ruff check .` and `ruff format --check .` passed.
- Sealed fixture validation passed; the known-bad batch reported `case_count: 16`, with each case returning its declared sole error.
- Both `stoa-known-good` and `stoa-known-good-v2` FormalRuns verified and replayed to `sha256:f393c1034a6d604ae915a18dac3bd206ce146e9c050b4e938048eb10a6378242`.
- Artifact hash checks passed for the sealed fixture, source manifest, review ledger, and both FormalRun manifests.

---

_Fixed: 2026-07-30T16:56:49Z_
_Fixer: the agent (gsd-code-fixer)_
_Iteration: 3_
