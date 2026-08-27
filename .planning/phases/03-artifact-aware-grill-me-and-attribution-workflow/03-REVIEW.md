---
phase: 03-artifact-aware-grill-me-and-attribution-workflow
reviewed: 2026-08-27T09:01:00Z
depth: deep
files_reviewed: 19
files_reviewed_list:
  - src/career_evidence_graph/audit/models.py
  - src/career_evidence_graph/audit/store.py
  - src/career_evidence_graph/audit/workflow.py
  - src/career_evidence_graph/audit/decision.py
  - src/career_evidence_graph/cli.py
  - _career_evidence_build.py
  - pyproject.toml
  - validation/schemas/audit-probe-plan.schema.json
  - validation/schemas/audit-boundary-decision.schema.json
  - tests/test_audit_store.py
  - tests/test_audit_cli.py
  - tests/test_assistance_migration.py
  - tests/test_audit_inspection.py
  - tests/test_cli_tracer.py
  - tests/test_audit_decision.py
  - tests/test_audit_policy.py
  - tests/test_audit_attribution.py
  - tests/test_audit_conclusion.py
  - tests/test_audit_gap_e2e.py
findings:
  critical: 1
  warning: 3
  info: 0
  total: 4
status: issues_found
---

# Phase 03: Code Review Report

**Reviewed:** 2026-08-27T09:01:00Z  
**Depth:** deep  
**Files Reviewed:** 19  
**Status:** issues_found

## Summary

This review used the reduced Phase 3 contract: one trusted-local operator, one atomic snapshot, and no event/CAS/replay/lock/installation/count authority. The selected source and test files were read end-to-end and their audit call chain was traced from the CLI through `AuditStore` and `transition_audit` to conclusion construction. The selected regression files pass (`45 passed`), but they do not exercise the defects below.

The primary defect is not a removed-scope filesystem attack: the snapshot contract itself accepts altered proposal/history bytes whose stored hashes no longer describe their contents. That breaks the active D-15 promise that the system's original proposal remains immutable and review history remains auditable.

## Narrative Findings (AI reviewer)

### Critical Issues

### CR-01: Stored conclusions do not validate either proposal or effective-history hash

**Classification:** BLOCKER  
**File:** `src/career_evidence_graph/audit/models.py:162` and `src/career_evidence_graph/audit/store.py:121`  
**Issue:** `AuditConclusion` treats `original_proposal`, `original_proposal_hash`, and `effective_conclusion_hash` as three unrelated fields. `StrictModel(frozen=True)` is only shallow: callers can mutate the nested `dict`/lists in `original_proposal`, and a JSON snapshot can also be edited so that either proposal/history no longer matches its persisted hash. `AuditStore.read()` only performs Pydantic shape validation, and `replace()` repeats that shape validation; neither recomputes either hash. A snapshot can therefore be reopened or confirmed while claiming an unchanged original proposal/hash even though its recorded proposal or effective conclusion has changed. This directly defeats D-15 and the Phase 3 repudiation mitigation for immutable proposals and ordered reviews.

**Fix:** Add model- or store-level integrity validation before every create, read, and replace: canonicalize `original_proposal` and require its digest to equal `original_proposal_hash`; derive the effective digest from `entries` plus `whole_review` and require equality with `effective_conclusion_hash`. Store an immutable JSON value (for example canonical bytes/string or recursively immutable structures) for `original_proposal`, or at minimum deep-copy it and reject a replacement whose digest changed without the appropriate append-only review transition. Add a regression that mutates serialized proposal/effective fields while retaining the old hash and asserts `AuditStorageError`.

### WR-01: A purported capability question may be a non-question

**Classification:** WARNING  
**File:** `src/career_evidence_graph/audit/workflow.py:123`  
**Issue:** `_validate_new_question()` rejects prompts containing more than one `?`/`？`, but accepts prompts containing none. A recorded or optional live probe plan can therefore persist an imperative/declarative statement as an audit question (for example, an injected or leading instruction without the small list of blocked phrases). The workflow then presents it as the next focused question even though Phase 3 requires one question at a time.

**Fix:** Require exactly one question terminator after normalization, or use a stricter prompt contract that separately stores the question text and validates it is interrogative. Add negative tests for a zero-question prompt and an instruction that lacks a question mark.

### WR-02: Attribution conflicts are attached to the first snapshot fact, not the fact behind the affected capability area

**Classification:** WARNING  
**File:** `src/career_evidence_graph/audit/workflow.py:654`  
**Issue:** When the ownership answer is `other-person-owned`, the conflict records `snapshot.inspected_facts[0].statement` regardless of the capability area whose ownership is being clarified. A selected Contribution may have multiple claims/evidence links; the resulting conclusion can display a concrete but unrelated documentary claim as the conflict. This makes D-11's visible conflict misleading rather than evidence-bound.

**Fix:** Resolve the area from `question.capability_area_id`, use `_area_for()` and `_fact_for()` to record that exact fact's statement, and add a two-area/two-fact test proving the recorded conflict uses the active area's fact.

### WR-03: Whole-Contribution skip accepts a stale question target

**Classification:** WARNING  
**File:** `src/career_evidence_graph/audit/workflow.py:749`  
**Issue:** `answer` and area `skip` validate a supplied `question_id` against the sole active question at lines 797-803, but `skip-contribution` returns before that guard. The CLI accepts `--question-id` for this action, so a stale or mismatched target is silently accepted and skips the active audit. This violates the one-action/one-active-question contract and makes the recorded action target misleading.

**Fix:** In the `skip-contribution` branch, reject a non-null `action.question_id` that differs from `active.id`, then add a CLI and transition regression mirroring `test_question_target_must_match_the_one_active_question`.

---

_Reviewed: 2026-08-27T09:01:00Z_  
_Reviewer: gsd-code-reviewer_  
_Depth: deep_
