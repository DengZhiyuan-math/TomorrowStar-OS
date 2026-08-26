---
phase: 03-artifact-aware-grill-me-and-attribution-workflow
reviewed: 2026-08-26T00:00:00Z
depth: standard
files_reviewed: 15
files_reviewed_list:
  - src/career_evidence_graph/audit/__init__.py
  - src/career_evidence_graph/audit/models.py
  - src/career_evidence_graph/audit/workflow.py
  - src/career_evidence_graph/audit/store.py
  - src/career_evidence_graph/cli.py
  - src/career_evidence_graph/domain/models.py
  - tests/test_audit_cli.py
  - tests/test_audit_inspection.py
  - tests/test_audit_models.py
  - tests/test_audit_policy.py
  - tests/test_audit_attribution.py
  - tests/test_assistance_migration.py
  - tests/test_audit_conclusion.py
  - tests/test_audit_store.py
  - tests/test_validation_probe_matrix.py
findings:
  critical: 5
  warning: 4
  info: 0
  total: 9
status: issues_found
---

# Phase 03: Code Review Report

**Reviewed:** 2026-08-26T00:00:00Z  
**Depth:** standard  
**Files Reviewed:** 15  
**Status:** issues_found

## Summary

The review found correctness and integrity defects in the audit state machine, append-only storage boundary, conclusion review flow, and attribution parsing. The implementation is offline/provider-neutral, but several paths can accept state transitions that should be rejected or produce conclusions that do not faithfully represent the user's answer. Tests cover the happy path and several stale/tampered cases, but omit these failure modes.

## Critical Issues

### CR-01: Paused and terminal audits can still accept answers

**File:** `src/career_evidence_graph/audit/workflow.py:317-324`  
**Issue:** `pause` is accepted without checking the current status, and `answer`/`skip` has no `status == "active"` guard. Consequently a caller can answer while an audit is paused (and can pause an already rejected/completed snapshot); the declared `AuditStatus` lifecycle is not enforced. This allows an operator or concurrent caller to append evidence after the audit was intentionally paused or closed.
**Fix:** Reject all mutating actions except `resume` when status is `paused`, reject answer/skip/review when status is not active, and only allow pause from active. Add explicit terminal-state handling when all areas reach a terminal state.

### CR-02: Normal CLI updates are last-write-wins and can lose audit answers

**File:** `src/career_evidence_graph/audit/store.py:99-118`; `src/career_evidence_graph/cli.py:349-374`  
**Issue:** `AuditStore.update` makes the optimistic check optional, while the CLI never supplies either `expected_snapshot_hash` or an event hash for answer, skip, pause, or resume. Two processes can read the same snapshot, each transition it, and each replace `snapshot.json`; the later write silently discards the earlier answer. This is a correctness/data-loss defect in a resumable audit workflow.
**Fix:** Require a caller-supplied version/hash for every update (or perform a locked read/compare-and-swap inside `update`), pass the hash of the read snapshot from the CLI, and fail closed on mismatch.

### CR-03: Event history is neither chained nor fully verified, so tampering is accepted

**File:** `src/career_evidence_graph/audit/store.py:68-78,83-97`  
**Issue:** `read` checks only that the last record's `hash` equals the current snapshot hash; it does not validate event names, record count, or any prior event. `latest_event_hash` returns a hash of the JSONL line rather than the record's declared snapshot hash and also examines only the last line. An attacker can delete or rewrite earlier history (or replace the initial `created` record) while preserving the current snapshot and last record, and `read` still succeeds. This contradicts the intended immutable audit lineage.
**Fix:** Store an explicit `prev_event_hash` and event payload in every record, hash the canonical record, and verify the complete chain from `created` through the current snapshot. Make `latest_event_hash` return the verified chain head and reject malformed/unknown records.

### CR-04: Conclusion reviews never change conclusion review state or apply corrections

**File:** `src/career_evidence_graph/audit/workflow.py:290-307`  
**Issue:** A review action only appends a `ConclusionReview`. It never updates `ConclusionEntry.review`, `AuditConclusion.whole_review`, or the conclusion text when an entry is edited. Thus `confirm`, `reject`, and `edit` are not reflected in the canonical snapshot; a consumer reading `snapshot.conclusion` still sees `pending` and the uncorrected proposal, while a rejected conclusion remains available as if it were current.
**Fix:** Apply the review outcome to the targeted entry/whole-conclusion (or expose a clearly separate immutable proposal plus derived reviewed conclusion), set the corresponding review state, and require a new proposal hash when edits produce a new conclusion.

### CR-05: English responsibility and assistance answers are systematically misclassified

**File:** `src/career_evidence_graph/audit/workflow.py:376-404`  
**Issue:** The prompts are English, but ownership detection recognizes only `不是我`, `团队`, and `我`; an answer such as the test fixture's `I owned the decisions and acceptance.` becomes `unresolved`. Similarly, an English answer such as `No outside assistance` is not recognized as `none` because the detector only checks `没有`/`无` (and assistance keywords for positive help). This loses valid attribution evidence and makes the resulting boundary/conclusion dependent on language rather than the answer.
**Fix:** Use an explicit structured attribution choice in the action/CLI, or implement a provider-neutral, tested vocabulary for supported languages with conservative conflict handling; include English and Chinese positive/negative/third-party cases.

## Warnings

### WR-01: Artifact facts are reused as the basis for every area, including skipped/unresolved areas

**File:** `src/career_evidence_graph/audit/workflow.py:184-205,219-233`  
**Issue:** `_build_conclusion` assigns all contribution artifact references to every area and labels an entry `artifact-and-answer` whenever that area has any answer, even when the area was skipped or unresolved. Documentary facts are contribution-level and non-personal; presenting them as the basis of every capability area can imply support that the interview did not establish.
**Fix:** Keep artifact references as documentary context, restrict capability basis to answers that actually addressed the area, and use an explicit source/basis state for skipped and unresolved entries.

### WR-02: Broken claim/evidence references escape as an uncontrolled exception

**File:** `src/career_evidence_graph/audit/workflow.py:55-70`  
**Issue:** Inspection builds dictionaries but indexes `claims[link.claim_id]` and `evidence[link.evidence_id]` without checking referential integrity. A malformed sealed payload produces `KeyError`, which is not converted to the documented validation/storage error and is not caught by the CLI's exception list, yielding a traceback instead of a controlled fail-closed response.
**Fix:** Validate every link and contribution claim ID before indexing and raise a domain/storage validation error with the offending identifier; add a missing-reference fixture test.

### WR-03: Review idempotency is checked after the stale-event check

**File:** `src/career_evidence_graph/audit/workflow.py:258-263`  
**Issue:** A replay of an already accepted review action still requires the current event hash to match before checking `action_id`. Replaying a valid action after another append therefore fails as stale rather than being idempotent, despite `accepted_action_ids` being intended to provide duplicate-action idempotency.
**Fix:** Resolve a known `action_id` against an immutable action record first, or define idempotency as requiring the original expected version and document/test that contract consistently.

### WR-04: Storage writes are not durable/atomic as a snapshot-plus-event transaction

**File:** `src/career_evidence_graph/audit/store.py:115-118`  
**Issue:** `snapshot.json` is replaced before the event line is appended, and the event file is not flushed/fsynced. A crash between those operations leaves a new snapshot paired with an old event head (or a missing event), and a crash during append can leave a partial line. The reader then reports corruption even though the update may have been accepted, making recovery ambiguous.
**Fix:** Write and fsync the complete new event log and snapshot in a temporary directory, fsync directory metadata, then atomically replace the audit directory (or use a lock/journal protocol with explicit recovery).

---

_Reviewed: 2026-08-26T00:00:00Z_  
_Reviewer: the agent (gsd-code-reviewer)_  
_Depth: standard_
