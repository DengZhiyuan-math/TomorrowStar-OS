---
phase: 03-artifact-aware-grill-me-and-attribution-workflow
reviewed: 2026-08-26T16:17:37Z
depth: standard
files_reviewed: 12
files_reviewed_list:
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
findings:
  critical: 1
  warning: 0
  info: 0
  total: 1
status: issues_found
---

# Phase 03: Code Review Report

**Reviewed:** 2026-08-26T16:17:37Z
**Depth:** standard
**Files Reviewed:** 12
**Status:** issues_found

## Summary

The cumulative 03-08/03-09 gap-closure scope was reviewed against its custody, replay, truthfulness, zero-write, and Phase-3-only claims. The former stale-update, omitted-effective-hash, ambiguous-attribution, question-target, and malformed-action defects are fixed on their reviewed public paths. The focused supplied suite passed (36 tests), and the exact Phase 3 gap inventory collected all 14 declared probes. However, the storage authority still permits a symlinked `audits` child to redirect writes outside the caller-provided workspace.

## Narrative Findings (AI reviewer)

## Critical Issues

### CR-01: A symlinked `audits` directory escapes the selected workspace

**Classification:** BLOCKER

**File:** `src/career_evidence_graph/audit/store.py:25-29, 39-50, 156-163`

**Issue:** `AuditStore.__init__()` rejects a workspace path that is itself a symlink, but it never rejects or contains `workspace/audits` when that child is a symlink. `_locked()` creates `.locks` below `self.root`, and `save()` creates the audit directory below it. Both operations follow a pre-existing `audits` symlink. A caller can therefore pass a normal workspace whose `audits` entry points elsewhere and cause `audit start` to create lock and custody files outside the requested workspace. A direct isolated probe confirmed that `start_audit()` writes `outside/audit-root-escape/snapshot.json` in this setup. This breaks the file-custody and zero-write boundary and is a filesystem symlink-escape vulnerability.

**Fix:** Establish and verify a non-symlinked audit root before every filesystem operation. For example, create `workspace/audits` only under a verified real workspace, reject it when `is_symlink()`, and require `root.resolve().parent == workspace.resolve()` before creating locks or audit directories. Keep the existing per-audit containment check, and add a regression that makes `workspace/audits` point to an external temporary directory and asserts `AuditStorageError` with no files created outside the workspace.

```python
def _audit_root(self) -> Path:
    workspace = self.workspace
    if workspace.is_symlink() or not workspace.is_dir():
        raise AuditStorageError("workspace path is unsafe")
    root = workspace / "audits"
    if root.is_symlink():
        raise AuditStorageError("audit root is unsafe")
    root.mkdir(mode=0o700, exist_ok=True)
    if root.resolve().parent != workspace.resolve():
        raise AuditStorageError("audit root escapes workspace")
    return root
```

---

_Reviewed: 2026-08-26T16:17:37Z_
_Reviewer: the agent (gsd-code-reviewer)_
_Depth: standard_
