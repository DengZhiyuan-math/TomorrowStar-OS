---
phase: 07
fixed_at: 2026-08-31T00:00:00Z
review_path: .planning/phases/07-career-source-custody-and-private-workspace/07-REVIEW.md
iteration: 1
findings_in_scope: 5
fixed: 5
skipped: 0
status: all_fixed
verification_environment: isolated review worktree
---

# Phase 07: Code Review Fix Report

**Fixed at:** 2026-08-31T00:00:00Z
**Source review:** `.planning/phases/07-career-source-custody-and-private-workspace/07-REVIEW.md`
**Iteration:** 1

**Summary:**

- Findings in scope: 5
- Fixed: 5
- Skipped: 0
- Targeted verification: `66 passed` in `tests/test_career_source_security.py`; scoped Ruff and Python AST parsing passed in the isolated review worktree.

## Fixed Issues

### CR-01: Store mutations can bypass the mandatory explicit Git snapshot

**Files modified:** `src/career_evidence_graph/career_sources.py`, `tests/test_career_source_security.py`
**Commit:** ef48f93
**Applied fix:** Made capture, transform, duplicate capture, and synthetic tracer mutation paths require a full explicit workspace commit and authenticate it before mutation.

### CR-02: Declaration manifests can be read through an unchecked symlink

**Files modified:** `src/career_evidence_graph/career_sources.py`, `tests/test_career_source_security.py`
**Commit:** ca1531f
**Applied fix:** Routed predecessor and declaration manifest reads through the strict semantic path seam and added bundle/leaf symlink regressions.

### CR-03: Transformed output bytes bypass the bidi/control gate before raw publication

**Files modified:** `src/career_evidence_graph/career_sources.py`, `tests/test_career_source_security.py`
**Commit:** baf3af7
**Applied fix:** Applied the shared raw-content validation to transformed output before hashing or writing and covered all nine bidi controls.

### CR-04: Routine status follows semantic namespace symlinks and leaks external counts

**Files modified:** `src/career_evidence_graph/career_sources.py`, `tests/test_career_source_security.py`
**Commit:** eecbdf7
**Applied fix:** Made safe status reject each semantic namespace symlink, including raw, before any count or presence result is derived.

### CR-05: Check-then-use path handling permits operation-time symlink swaps

**Files modified:** `src/career_evidence_graph/workspace.py`, `src/career_evidence_graph/career_sources.py`, `tests/test_career_source_security.py`
**Commit:** f4dd682
**Applied fix:** Added descriptor-bound `O_NOFOLLOW` raw and core semantic publication operations, with directory identity revalidation before create, replace, and unlink; added deterministic raw, manifest, and pointer parent-swap regressions.

## Verification Note

The full legacy `tests/test_career_source_custody.py` suite currently has 55 expected API-migration failures because those historical synthetic tests omit the newly required `expected_workspace_commit` argument. This report does not treat that as a reason to reintroduce an unanchored mutation API. Those test call sites need a follow-up mechanical migration to create and pass an explicit synthetic full-OID baseline.

---

_Fixed: 2026-08-31T00:00:00Z_
_Fixer: the agent (gsd-code-fixer)_
_Iteration: 1_
