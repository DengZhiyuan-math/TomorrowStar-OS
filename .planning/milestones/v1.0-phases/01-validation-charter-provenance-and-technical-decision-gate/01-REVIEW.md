---
phase: 01
status: clean
depth: standard
files_reviewed: 17
findings:
  critical: 0
  warning: 0
  info: 0
  total: 0
resolved_findings: 3
reviewed_at: 2026-07-30
---

# Phase 1 Code Review

## Verdict

Phase 1 source changes pass standard-depth review after three formal-evidence
trust gaps were corrected and covered by regression tests.

## Scope

The review covered the local Python package, CLI boundary, validation store,
acceptance and replay logic, provenance verifier, and their Phase 1 tests.
Planning artifacts, pinned upstream repositories, and lock files were excluded.

## Resolved Findings

### CR-01: Untrusted subprocess output could claim an immutable model snapshot

- **Severity:** Critical
- **Resolution:** Only an operator-configured snapshot can populate
  `resolved_snapshot`; model fields in JSONL remain untrusted output.
- **Regression:** `test_untrusted_event_cannot_claim_an_immutable_model_snapshot`
- **Commit:** `98372f8`

### WR-01: Undeclared files did not invalidate a formal bundle

- **Severity:** Warning
- **Resolution:** Verification now requires the run directory to contain exactly
  `manifest.json` plus the declared payload set.
- **Regression:** `test_undeclared_file_invalidates_the_complete_formal_bundle`
- **Commit:** `98372f8`

### WR-02: Child verification did not revalidate parent lineage

- **Severity:** Warning
- **Resolution:** Linked-run verification now recursively validates ancestry and
  rejects cycles, so later parent tampering invalidates the child.
- **Regression:** `test_child_verification_fails_when_parent_is_later_tampered`
- **Commit:** `98372f8`

## Verification

- Full offline suite: 52 passed, 1 explicitly deselected live-model smoke.
- Targeted security/Codex suite: 33 passed, 1 explicitly deselected live-model smoke.
- Ruff lint: passed.
- Ruff formatting check: passed.

## Remaining Notes

- The filesystem manifest detects mutations relative to the stored manifest; it
  is not an external signature against an operator who can rewrite the entire
  workspace.
- The optional live Luna smoke remains unrun and therefore supplies no live-model
  evidence.
