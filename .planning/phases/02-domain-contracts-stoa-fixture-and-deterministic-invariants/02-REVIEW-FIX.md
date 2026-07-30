---
phase: 02
fixed_at: 2026-07-30T16:42:21Z
review_path: .planning/phases/02-domain-contracts-stoa-fixture-and-deterministic-invariants/02-REVIEW.md
iteration: 2
findings_in_scope: 3
fixed: 3
skipped: 0
status: all_fixed
---

# Phase 02: Code Review Fix Report

**Fixed at:** 2026-07-30T16:42:21Z
**Source review:** `.planning/phases/02-domain-contracts-stoa-fixture-and-deterministic-invariants/02-REVIEW.md`
**Iteration:** 2

**Summary:**

- Findings in scope: 3
- Fixed: 3
- Skipped: 0

## Fixed Issues

### CR-01: The wheel globally executes source outside the installed artifact

**Files modified:** `pyproject.toml`, `scripts/run_career_evidence.py`, `scripts/run_pytest.py`, `tests/test_cli_tracer.py`, Phase 02 gates
**Commits:** `d7edfb6`, `ac2bb7d`
**Applied fix:** Replaced the custom wheel hook with the standard Flit PEP 517/660 backend. Explicit project-local launchers select checkout code only for invoked commands; an offline isolated-wheel regression verifies no `sitecustomize.py`, RECORD coverage for package modules, and an installed-wheel import from another directory.

### CR-02: Sealed-fixture validation ignores its source, review, and checkpoint bindings

**Files modified:** `src/career_evidence_graph/domain/fixtures.py`, `src/career_evidence_graph/cli.py`, `tests/test_stoa_fixture.py`, `validation/fixtures/stoa/v1/known-good.json`, `formal-runs/stoa-known-good-v2/`
**Commit:** `af7ca21`
**Applied fix:** Loading now recomputes each canonical on-disk input hash and requires matching envelope and FormalRun lineage hashes. Added separate source-manifest, review, and checkpoint envelope-tamper regressions. The official reissue path preserved the confirmed fixture hash and retained the old bundle while moving the sealed envelope to verified `stoa-known-good-v2` lineage.

### WR-01: Review materialization accepts a reviewer other than the confirmed human

**Files modified:** `src/career_evidence_graph/domain/fixtures.py`, `tests/test_stoa_fixture.py`
**Commit:** `19a48ac`
**Applied fix:** Correction validation now requires the exact confirmed reviewer, and materialization parses exactly one `review-confirmed` and `reviewer_id` checkpoint record before accepting it. The coordinated review-and-correction reviewer tampering regression now fails closed.

---

_Fixed: 2026-07-30T16:42:21Z_
_Fixer: the agent (gsd-code-fixer)_
_Iteration: 2_
