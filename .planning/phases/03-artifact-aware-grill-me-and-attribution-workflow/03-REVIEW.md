---
phase: 03-artifact-aware-grill-me-and-attribution-workflow
reviewed: 2026-08-26T18:14:17Z
depth: deep
files_reviewed: 15
files_reviewed_list:
  - _career_evidence_build.py
  - pyproject.toml
  - src/career_evidence_graph/audit/models.py
  - src/career_evidence_graph/audit/store.py
  - src/career_evidence_graph/audit/workflow.py
  - src/career_evidence_graph/cli.py
  - tests/test_audit_attribution.py
  - tests/test_audit_cli.py
  - tests/test_audit_conclusion.py
  - tests/test_audit_gap_e2e.py
  - tests/test_audit_storage_regressions.py
  - tests/test_audit_store.py
  - tests/test_audit_workflow_regressions.py
  - tests/test_validation_probe_matrix.py
  - tests/test_audit_inspection.py
findings:
  critical: 2
  warning: 0
  info: 0
  total: 2
status: issues_found
---

# Phase 03: Code Review Report

**Reviewed:** 2026-08-26T18:14:17Z
**Depth:** deep
**Files Reviewed:** 15
**Status:** issues_found

## Summary

The source-level containment regression, normal-workspace behavior, CAS, recovery, and focused/full pytest suites pass when pytest prepends `src/`. However, the user-facing locked CLI still imports the stale installed package rather than the reviewed source, so it retains the original audit-root symlink escape. Independently, the new source-level check is a time-of-check/time-of-use boundary: a local filesystem actor can replace the validated root with a symlink between validation and the first lock/write operation. Both defects permit custody files outside the caller-selected workspace.

## Narrative Findings (AI reviewer)

## Critical Issues

### CR-01: The locked CLI runs the stale, vulnerable installed `AuditStore`

**Classification:** BLOCKER

**File:** `pyproject.toml:24-27`, `_career_evidence_build.py:78-87`

**Issue:** `pythonpath = ["src"]` changes pytest's import resolution only. The editable wheel still packages every source file before adding the `.pth` entry, so `uv run --locked career-evidence` resolves `career_evidence_graph` from `.venv/site-packages`, where `AuditStore.__init__()` still uses the pre-03-10 `self.root = workspace.resolve() / "audits"` implementation. The Phase 3 public CLI is therefore not executing the reviewed containment fix. A clean temporary probe with `workspace/audits -> external` and `uv run --locked career-evidence audit start ...` created `external/.locks/audit-cli-stale.lock`, `external/audit-cli-stale/snapshot.json`, `events.jsonl`, and `accepted-results.json`.

**Fix:** Make the editable build genuinely editable: do not include package modules in the editable wheel, leaving only metadata, entry points, and the `src` `.pth` file (or use a standard editable backend). Then add a subprocess regression that runs `uv sync --locked` followed by `uv run --locked career-evidence audit start` against the redirected-root fixture and asserts the external directory stays unchanged. Do not rely on pytest's `pythonpath` setting as proof of the installed CLI.

### CR-02: Audit-root validation can be bypassed by a symlink swap after the check

**Classification:** BLOCKER

**File:** `src/career_evidence_graph/audit/store.py:38-46, 58-67, 178-184`

**Issue:** `_audit_root()` validates `workspace/audits` and returns a pathname. `_locked()` then creates `.locks` through that pathname without holding a directory descriptor or revalidating immediately before the write. An actor able to modify the selected workspace can rename the checked directory and replace `workspace/audits` with a symlink after line 44 succeeds but before line 61 executes. The next `locks.mkdir()` follows the replacement into the external target. An isolated source-import probe reproduced this exact ordering and observed `external/.locks/audit-race.lock` after entering `_locked()`.

**Fix:** Anchor storage operations to opened directory file descriptors with `O_DIRECTORY | O_NOFOLLOW` (and use `dir_fd` variants for lock/audit creation and publication), or otherwise keep a verified root directory handle across the lock and all file operations. Add a deterministic regression that swaps the root between validation and lock creation and asserts no external file appears. Rechecking only after a path-based write is not sufficient.

---

_Reviewed: 2026-08-26T18:14:17Z_
_Reviewer: the agent (gsd-code-reviewer)_
_Depth: deep_
