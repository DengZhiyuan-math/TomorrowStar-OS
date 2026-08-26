---
phase: 03-artifact-aware-grill-me-and-attribution-workflow
reviewed: 2026-08-26T15:13:32Z
depth: standard
files_reviewed: 17
files_reviewed_list:
  - pyproject.toml
  - src/career_evidence_graph/audit/models.py
  - src/career_evidence_graph/audit/store.py
  - src/career_evidence_graph/audit/workflow.py
  - src/career_evidence_graph/cli.py
  - tests/test_assistance_migration.py
  - tests/test_audit_attribution.py
  - tests/test_audit_cli.py
  - tests/test_audit_conclusion.py
  - tests/test_audit_event_models.py
  - tests/test_audit_gap_e2e.py
  - tests/test_audit_inspection.py
  - tests/test_audit_policy.py
  - tests/test_audit_storage_regressions.py
  - tests/test_audit_store.py
  - tests/test_audit_workflow_regressions.py
  - tests/test_validation_probe_matrix.py
findings:
  critical: 3
  warning: 2
  info: 0
  total: 5
status: issues_found
---

# Phase 03: Code Review Report

**Reviewed:** 2026-08-26T15:13:32Z
**Depth:** standard
**Files Reviewed:** 17
**Status:** issues_found

## Summary

The Phase 03 gap-closure source, regression tests, and the 03-04 through 03-07 plans/summaries were reviewed. The focused suite (51 tests) and Ruff gates pass, but passing tests do not cover core write and attribution paths that violate the stated CAS and truthfulness contracts.

## Critical Issues

### CR-01: `update()` can overwrite a newer audit state without caller-held CAS

**Classification:** BLOCKER

**File:** `src/career_evidence_graph/audit/store.py:249`

**Issue:** `update()` makes the event-head precondition optional. When omitted, it reads the *current* event head immediately before calling `transact()`, then publishes the caller-supplied `snapshot` through `lambda _current: snapshot`. A stale caller can therefore overwrite another writer's accepted transition: construct a snapshot from head A, let another action commit head B, then call `update(stale_snapshot)`. The method uses head B itself, so CAS succeeds and state is rolled back/lost. This contradicts the Phase 03 requirement that every mutation require caller-supplied CAS and enables audit-history/custody loss for any programmatic consumer of this public method.

**Fix:** Remove the compatibility write API, or require `expected_event_hash` with no default and derive the replacement strictly from the locked `current` snapshot. Do not accept a prebuilt snapshot after fetching a newer head. Add a regression that commits writer B between creation of the stale snapshot and `update()`, then asserts rejection and byte-identical files.

### CR-02: Core review transitions accept no effective-conclusion precondition

**Classification:** BLOCKER

**File:** `src/career_evidence_graph/audit/models.py:118`

**Issue:** `expected_effective_conclusion_hash` is optional, and `_review_conclusion()` only compares it when supplied (`workflow.py:345`). Although the CLI requires the option, Python callers can invoke a review action without it and mutate the canonical conclusion based only on the event-head check. This bypasses the independent effective-projection guard promised for every entry/whole review and allows a stale review intent to be applied after a projection-changing edit whenever a caller has acquired the latest event head.

**Fix:** Require `expected_effective_conclusion_hash` in `AuditAction.valid_payload()` for both review actions, and unconditionally compare it in `_review_conclusion()`. Add direct-workflow tests for omitted and stale hashes, rather than testing only the CLI parser.

### CR-03: Ambiguous ownership or assistance is recorded as a verified area

**Classification:** BLOCKER

**File:** `src/career_evidence_graph/audit/workflow.py:527`

**Issue:** Any non-empty responsibility/assistance answer marks coverage `verified` before the conservative classifier runs. For example, an answer such as “maybe the team and I did it” yields `ownership="unresolved"`, yet the resulting conclusion says the user established hard-level responsibility capability and uses `verification="audit-verified"` (`workflow.py:211-219`). The same happens for ambiguous assistance. This directly launders unresolved attribution into a verified conclusion, contrary to the Phase 03 requirement that ambiguous/conflicting text remain unresolved and that responsibility-affecting truthfulness be preserved.

**Fix:** For responsibility and assistance, set coverage to `unresolved` whenever the relevant classifier returns `unresolved` (and preserve the answer as an unresolved record). Make `_build_conclusion()` derive its verification/wording from attribution status for these two areas. Add a regression for mixed English/Chinese ownership and assistance text asserting no `audit-verified` conclusion entry.

## Warnings

### WR-01: Invalid audit action payloads do not use the structured audit-error boundary

**Classification:** WARNING

**File:** `src/career_evidence_graph/cli.py:382`

**Issue:** `AuditAction.model_validate(payload)` can raise Pydantic `ValidationError`, which is caught only by the generic branch at lines 401-413 and emitted as `error: ...` text. Thus malformed review/action input has a different, non-JSON error contract from rejected audit actions, despite this phase's structured CLI diagnostics goal.

**Fix:** Catch `ValidationError` while building an audit action and emit the same structured audit error envelope (or a documented structured `invalid_audit_action` envelope). Add CLI tests for an invalid edit/action payload and assert exit 2, JSON stderr, no traceback, and no writes.

### WR-02: Supplied question IDs are silently ignored

**Classification:** WARNING

**File:** `src/career_evidence_graph/audit/workflow.py:479`

**Issue:** `AuditAction` exposes `question_id`, but answer/skip always applies to the first unanswered question and never checks it. This makes a caller's target assertion meaningless and hides client/workflow desynchronization instead of failing closed, contrary to the lifecycle-table guard that the target match the single active question.

**Fix:** If `question_id` is present, require it to equal `q.id`; alternatively require it for answer/skip actions and expose it in the CLI. Add a regression proving that a stale/wrong question ID raises `AuditWorkflowError` without changing the audit files.

---

_Reviewed: 2026-08-26T15:13:32Z_
_Reviewer: the agent (gsd-code-reviewer)_
_Depth: standard_
