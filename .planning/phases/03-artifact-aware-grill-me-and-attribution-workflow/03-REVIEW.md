---
phase: 03-artifact-aware-grill-me-and-attribution-workflow
reviewed: 2026-08-26T20:30:00Z
depth: deep
files_reviewed: 7
files_reviewed_list:
  - _career_evidence_build.py
  - pyproject.toml
  - src/career_evidence_graph/audit/store.py
  - tests/test_audit_installation_regressions.py
  - tests/test_audit_storage_regressions.py
  - tests/test_cli_tracer.py
  - tests/test_validation_probe_matrix.py
findings:
  critical: 2
  warning: 1
  info: 0
  total: 3
status: issues_found
---

# Phase 03: Code Review Report

**Reviewed:** 2026-08-26T20:30:00Z
**Depth:** deep
**Files Reviewed:** 7
**Status:** issues_found

## Summary

Plans 03-11 through 03-13 close the prior stale-editable-wheel and direct `workspace/audits` pathname findings: the ordinary wheel remains self-contained, the installed editable command resolves the checkout package, and normal descriptor-relative storage works. They do not close containment or integrity for all filesystem entries used by the public store. A parent-directory link can still redirect the public CLI outside the selected workspace, and replacing `.locks` after it is opened splits the per-audit mutex and corrupts the event chain. The fresh-install regression also makes the ordinary test suite depend on a network-populated empty cache.

## Narrative Findings (AI reviewer)

## Critical Issues

### CR-01: A symlink in a workspace ancestor still redirects the public CLI outside its selected workspace

**Classification:** BLOCKER

**File:** `src/career_evidence_graph/audit/store.py:105-107`

**Issue:** `_root_session()` creates `self.workspace` with `parents=True` and opens only the final component with `O_NOFOLLOW`. `O_NOFOLLOW` does not protect intermediate pathname components. Consequently, an attacker can make a parent of the user-supplied `--workspace` path a symlink to an external directory; `mkdir()` follows that parent and the final `os.open()` accepts the newly-created external child directory. The public locked CLI then writes the lock, snapshot, events, and accepted-result files there. The installed command was reproduced in a temporary audit workspace with `entry/link -> external`: it returned success and created `external/nested-workspace/audits/.locks/audit-parent-link.lock` plus all three custody files.

**Fix:** Resolve the workspace from a trusted directory descriptor one component at a time, rejecting `.`/`..` and opening every existing or newly-created component with `O_DIRECTORY | O_NOFOLLOW`; retain the final workspace descriptor for the session. A final-component `O_NOFOLLOW` check is insufficient. Add a public-CLI regression where an ancestor of `--workspace` is a symlink and assert the complete external-tree snapshot is unchanged.

### CR-02: Replacing `.locks` after its one-time check splits the mutex and corrupts the audit event chain

**Classification:** BLOCKER

**File:** `src/career_evidence_graph/audit/store.py:143-180`

**Issue:** `_locked()` checks the `.locks` directory only while `_mkdir_open()` returns it (line 143), then never verifies that `root_fd/.locks` still names that held descriptor. An actor able to modify the audit root can rename `.locks` and create a replacement between two operations. The first operation locks a file in the unlinked original directory, while the second opens the replacement directory and acquires a different file lock for the same audit. Both then pass the same event head and publish concurrently. A deterministic two-thread probe performed this replacement after the first descriptor opened: both `split-a` and `split-b` transactions returned success, and a subsequent `read()` failed with `AuditStorageError('audit event chain is corrupt')`; `events.jsonl` had zero lines.

**Fix:** Treat `.locks` as a bound authority as well: carry `locks_fd` with its root binding and verify `root_fd/.locks` still has the same inode immediately before entering the transaction and before publication/return. If mutation of the root is an in-scope adversary capability, also ensure competing sessions cannot proceed on different lock directories (for example, bind and reject a replaced `.locks` entry before all critical reads/writes). Add the two-writer split-lock regression and require that exactly one action wins while the other receives the normal stale-head error; the persisted event chain must remain readable.

## Warnings

### WR-01: The default gap probe requires network access despite the project's offline deterministic-suite contract

**File:** `tests/test_audit_installation_regressions.py:52-65`

**Issue:** The test deliberately points `UV_CACHE_DIR` at a new empty directory, then runs `uv sync --locked` without `--offline`. A clean machine therefore downloads Pydantic and its dependencies during ordinary `pytest`; if network access is unavailable, the default suite fails before exercising the asserted CLI boundary. This was reproduced during review with a fresh cache, where `uv sync` failed resolving `pydantic-core` and `annotated-types` due to blocked DNS.

**Fix:** Keep the ordinary default suite offline and deterministic. Either run the truly fresh-cache installation probe only under an explicit integration marker/CI job with declared network authority, or redesign it to use prebuilt/local dependency artifacts while remaining offline. Retain a deterministic installed-entrypoint containment test in the default suite.

---

_Reviewed: 2026-08-26T20:30:00Z_
_Reviewer: the agent (gsd-code-reviewer)_
_Depth: deep_
