---
phase: 04-contribution-skill-assessment-and-aggregation-calibration
reviewed: 2026-08-28T13:35:13Z
depth: standard
files_reviewed: 1
files_reviewed_list:
  - tests/test_assessment_cli.py
findings:
  critical: 0
  warning: 2
  info: 0
  total: 2
status: issues_found
---

# Phase 04: Code Review Report

**Reviewed:** 2026-08-28T13:35:13Z
**Depth:** standard
**Files Reviewed:** 1
**Status:** issues_found

## Summary

The 37 collected cases preserve the required fresh canonical payload, local Pydantic validation, real reassessment invocation, exit-2 workflow-error check, sidecar-byte comparison, and audit-tree comparison. The complete matrix also retains the planned 17 groups and adds the specified 20 valid groups. The focused node passed: 37 passed.

Two regression-quality gaps remain: failed matrix entries are anonymous, and the asserted audit-tree identity does not recognize a same-content symlink replacement.

## Narrative Findings (AI reviewer)

## Warnings

### WR-01: Anonymous parameter cases make the required mutation inventory non-auditable

**Classification:** WARNING

**File:** `tests/test_assessment_cli.py:383-465`

**Issue:** The matrix passes only `patches` to pytest, so collection and failures are reported as `patches0` through `patches36`. A 37-case result therefore proves only a count; it cannot identify which custody field failed or demonstrate that the retained-17 plus specified-20 inventory is still present. A duplicate or a substituted mutation can leave the same 37 passing cases while silently dropping a required structural group, and a future failure requires manual positional counting to diagnose.

**Fix:** Carry a stable semantic case ID with each ordered patch list and use it as the pytest parameter ID, while retaining the same one-loop patch application. For example: `pytest.param(patches, id="source-envelope-attribution-hash")` for each entry.

### WR-02: The audit-tree assertion cannot detect same-content symlink mutations

**Classification:** WARNING

**File:** `tests/test_assessment_cli.py:485-508`

**Issue:** The asserted `_audit_tree_snapshot` helper records only a relative path, a derived `directory`/`file` label, and `read_bytes()` content. Both `Path.is_dir()` and `Path.read_bytes()` follow symlinks. Consequently, a regression that replaces an audit JSON file with a symlink to identical bytes can change the audit tree while preserving the snapshot tuple, so this matrix would falsely pass its claimed complete audit-tree-identity check. This matters at an identity/custody boundary, where a symlink replacement is materially different from no write.

**Fix:** Make the snapshot used by this test preserve filesystem entry type and symlink target without dereferencing it (for example, use `path.is_symlink()` and `os.readlink(path)` before `is_dir()`/`read_bytes()`, or `lstat()` metadata). Keep byte checks for regular files and compare the enriched snapshot before and after each rejection.

---

_Reviewed: 2026-08-28T13:35:13Z_
_Reviewer: the agent (gsd-code-reviewer)_
_Depth: standard_
