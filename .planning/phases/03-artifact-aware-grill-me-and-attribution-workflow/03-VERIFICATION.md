---
phase: 03-artifact-aware-grill-me-and-attribution-workflow
verified: 2026-08-26T00:00:00Z
status: gaps_found
score: 14/21 must-haves verified
behavior_unverified: 0
overrides_applied: 0
gaps:
  - truth: "AUD-02 empty: pause and terminal lifecycle transitions reject invalid answers and resumes"
    status: failed
    reason: "transition_audit accepts answer/skip while paused and pause from any status; resume does not validate unanswered/terminal state."
    artifacts:
      - path: "src/career_evidence_graph/audit/workflow.py"
        issue: "No active-state guard for answer/skip and no valid-state guard for pause."
    missing:
      - "Enforce active/paused/completed/rejected transition guards and explicit terminal handling."
  - truth: "AUD-02 concurrency: optimistic checks prevent lost updates for normal audit actions"
    status: failed
    reason: "AuditStore.update makes expected_event_hash optional and the CLI passes none for answer, skip, pause, and resume, so concurrent writers are last-write-wins."
    artifacts:
      - path: "src/career_evidence_graph/audit/store.py"
        issue: "update() permits unversioned replacement."
      - path: "src/career_evidence_graph/cli.py"
        issue: "Normal audit commands do not pass an expected snapshot/event hash."
    missing:
      - "Require compare-and-swap or a caller-supplied version on every mutating update."
  - truth: "AUD-01 event custody: the complete event history is tamper-detecting and verified"
    status: failed
    reason: "read() validates only required keys and the last record's snapshot hash; earlier events can be deleted or rewritten while reads still succeed."
    artifacts:
      - path: "src/career_evidence_graph/audit/store.py"
        issue: "No chained prev_event_hash, event schema validation, or full-chain verification. latest_event_hash hashes the JSONL line rather than returning a verified chain head."
    missing:
      - "Hash-link and verify every event from created through the current snapshot."
  - truth: "AUD-05 review actions affect canonical conclusion state"
    status: failed
    reason: "Entry/whole review appends a review record but leaves ConclusionEntry.review and AuditConclusion.whole_review pending; edits do not update the canonical conclusion."
    artifacts:
      - path: "src/career_evidence_graph/audit/workflow.py"
        issue: "Review branch only updates conclusion_reviews and accepted_action_ids."
    missing:
      - "Expose a derived reviewed conclusion or update canonical review state and corrections consistently."
  - truth: "AUD-04 attribution is language-independent for supported English and Chinese answers"
    status: failed
    reason: "English answers such as 'I owned the decisions and acceptance.' and 'No outside assistance' are classified unresolved by Chinese-only detectors."
    artifacts:
      - path: "src/career_evidence_graph/audit/workflow.py"
        issue: "Ownership checks 我/团队/不是我; assistance checks 没有/无 plus Chinese third-party only."
    missing:
      - "Add explicit structured choices or conservative tested English and Chinese vocabularies."
  - truth: "AUD-05 review idempotency remains stable after later event appends"
    status: partial
    reason: "Duplicate review checks stale expected_event_hash before accepted_action_ids, so replay after another append is rejected as stale rather than idempotent."
    artifacts:
      - path: "src/career_evidence_graph/audit/workflow.py"
        issue: "Lines 258-263 check the event hash before the duplicate action."
    missing:
      - "Resolve immutable accepted action identity before stale-version rejection, or document and test the stricter contract."
  - truth: "AUD-05 review lineage is transactionally durable"
    status: partial
    reason: "Snapshot replacement occurs before an unsynced event append; a crash can leave snapshot and event log mismatched or a partial JSONL line."
    artifacts:
      - path: "src/career_evidence_graph/audit/store.py"
        issue: "update() replaces snapshot then appends without fsync/transactional directory publication."
    missing:
      - "Use a journal/lock recovery protocol or atomically publish a complete snapshot-plus-event directory."
  - truth: "Artifact inspection fails closed on malformed claim/evidence references"
    status: partial
    reason: "inspect_contribution indexes claims and evidence dictionaries without checking link references; malformed sealed payloads can raise uncontrolled KeyError/traceback instead of the documented storage error."
    artifacts:
      - path: "src/career_evidence_graph/audit/workflow.py"
        issue: "Missing referential-integrity checks around claims[link.claim_id] and evidence[link.evidence_id]."
    missing:
      - "Validate every selected link and convert missing references to controlled fail-closed errors."
  - truth: "Conclusion basis distinguishes artifact context from area-specific answer evidence"
    status: partial
    reason: "_build_conclusion assigns all artifact references to every area and labels any answered area artifact-and-answer, including skipped or unresolved areas."
    artifacts:
      - path: "src/career_evidence_graph/audit/workflow.py"
        issue: "basis and source_type combine contribution-level facts with area answers indiscriminately."
    missing:
      - "Keep documentary artifact context separate from capability basis for skipped/unresolved areas."
deferred: []
---

# Phase 3: Artifact-Aware Grill-Me and Attribution Workflow Verification Report

**Phase Goal:** A user can complete a resumable, artifact-aware audit of a selected Contribution and explicitly confirm what capability and responsibility the evidence establishes.
**Verified:** 2026-08-26T00:00:00Z
**Status:** gaps_found
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|---|---|---|
| 1 | Before questioning, supplied artifacts, established facts, and question rationale are inspectable. | ✓ VERIFIED | `inspect_contribution()` validates the manifest, loads the sealed fixture, returns sorted `ArtifactFact` records and limitations, and `_question()` carries an inspection reference and reason. |
| 2 | Duplicate/overlapping artifact facts retain source locators and do not become ownership claims. | ✓ VERIFIED | Facts retain `evidence_id` and `section_locator`; duplicate link identities are rejected; no inspection code asserts ownership/capability. |
| 3 | Missing Contribution, empty evidence, null/invalid input, and unverified manifest fail closed. | ⚠️ PRESENT WITH GAP | Normal missing/empty/manifest paths reject, but malformed claim/evidence references escape as `KeyError`; see WR-02. |
| 4 | Inspection and creation are deterministic, idempotent, and creation interruption/concurrency bounded. | ✓ VERIFIED | Sorted facts/limitations and deterministic question IDs; `AuditStore.save()` rejects existing IDs and publishes through a temporary directory with fsynced snapshot. |
| 5 | Start emits one reason-prefaced question; pause emits none; invalid lifecycle resume/answer is rejected. | ✗ FAILED | Start behavior passes, but a direct run showed `paused_answer ... len=1`; `transition_audit()` lacks active-state guards. |
| 6 | The offline path crosses inspection, pause/resume, attribution, and review without a live provider. | ✗ FAILED | Offline path exists and full tests pass, but English attribution is unresolved and review does not alter canonical conclusion state. |
| 7 | Competing actions cannot merge answers or lose updates. | ✗ FAILED | Normal CLI updates call `store.update(updated)` without an expected version; last writer can replace the other answer. |
| 8 | Question/event ordering is stable, one focused action is accepted per transition, and replays are stable. | ✓ VERIFIED | Deterministic area ladder and action IDs are covered by policy tests; duplicate accepted action IDs return the snapshot. |
| 9 | One same-level follow-up is allowed, then incomplete answers descend hard→intermediate→simple. | ✓ VERIFIED | `follow_up_count` and ladder logic are covered by `test_questions_descend_after_one_incomplete_followup`. |
| 10 | Blank answers/exhausted areas cannot create ungrounded questions or conclusions. | ✓ VERIFIED | Strict `AuditAction` rejects blank answer payloads; no unanswered question raises; conclusion requires all five terminal coverage states. |
| 11 | Unicode answers/reasons preserve exact round-trip identity. | ✓ VERIFIED | Pydantic UTF-8 JSON persistence and Unicode conclusion tests pass. |
| 12 | Relevant areas, difficulty progression, answered-question uniqueness, and competing coverage updates are deterministic. | ✗ FAILED | Deterministic ladder is present, but competing normal updates are unversioned (CR-02). |
| 13 | Ownership precedes assistance and assistance cannot fill ownership. | ✓ VERIFIED | Workflow creates separate responsibility and assistance rounds in sequence and keeps separate attribution fields. |
| 14 | Absent, Unicode, and unresolved attribution values remain distinguishable. | ✓ VERIFIED | Literal unions and separate nullable rounds preserve these states; migration tests pass. |
| 15 | Competing attribution answers preserve conflicts and cannot overwrite proposals. | ✗ FAILED | No optimistic check is supplied for normal attribution actions; concurrent attribution writes can lose one claim. |
| 16 | Entry and whole reviews remain separate ordered records. | ✓ VERIFIED | `ConclusionReview` records target separately and append to `conclusion_reviews`; whole review does not erase entry records. |
| 17 | No proposal exists before all areas are terminal and each entry has capability boundaries/basis/attribution fields. | ✓ VERIFIED | `_build_conclusion()` gates on all five coverage areas and constructs the required fields. |
| 18 | Proposal/correction/rejection/reviewer Unicode data is exact and stable. | ✓ VERIFIED | Strict models and UTF-8 JSON tests pass; original proposal is retained in review records. |
| 19 | Review history follows event order and repeated terminal outcomes cannot conflict. | ✗ FAILED | Terminal conflict prevention exists, but replay after any later append fails stale before idempotency (WR-03); event history itself is not fully chained. |
| 20 | Review actions require expected hashes and competing edits cannot overwrite originals. | ✓ VERIFIED | Review CLI requires expected event hash; stale review tests reject and original proposal/hash are retained. This does not cure general event-chain tampering. |
| 21 | Verified conclusions contain prose only; skipped numeric self-ratings remain unverified text. | ✓ VERIFIED | Conclusion models have no numeric assessment fields; skip preserves opaque `self_rating`, and the no-score test passes. |

**Score:** 14/21 truths verified (0 present-but-behavior-unverified; 7 failed/partial).

## Required Artifacts

| Artifact | Expected | Status | Details |
|---|---|---|---|
| `src/career_evidence_graph/audit/__init__.py` | Package marker | ✓ VERIFIED | Exists and imports successfully. |
| `src/career_evidence_graph/audit/models.py` | Strict audit/question/attribution/conclusion contracts | ✓ VERIFIED | Substantive Pydantic strict models; imported by workflow/CLI and exercised by tests. |
| `src/career_evidence_graph/audit/workflow.py` | Inspection and pure transitions | ⚠️ PARTIAL | Substantive and wired, but lifecycle, English attribution, basis, and review-state defects remain. |
| `src/career_evidence_graph/audit/store.py` | Contained snapshot/event persistence | ⚠️ PARTIAL | Atomic initial publication and path checks exist; update is unversioned by default and event history is not fully verified/durable. |
| `src/career_evidence_graph/cli.py` | Offline audit command group | ⚠️ PARTIAL | All commands are wired and tested, but ordinary mutations omit concurrency hashes and review output does not update canonical state. |

## Key Link Verification

| From | To | Via | Status | Details |
|---|---|---|---|---|
| `cli.py` | `audit/workflow.py` | audit subcommand dispatch | ✓ WIRED | CLI imports and invokes start, inspect, transition, and review paths. |
| `audit/workflow.py` | sealed STOA fixture | `load_sealed_fixture`/manifest verification | ✓ WIRED | Selected Contribution and declared links are used for inspection. |
| `audit/workflow.py` | `audit/models.py` | validated transition models | ✓ WIRED | All snapshots/actions/questions/conclusions are Pydantic contracts. |
| `workflow.py` | `store.py` | persisted transitions/reviews | ⚠️ PARTIAL | Persistence is called, but normal updates are not compare-and-swap and review state is only appended separately. |

## Data-Flow Trace (Level 4)

| Artifact | Data variable | Source | Produces real data | Status |
|---|---|---|---|---|
| `workflow.py` | `inspected_facts` | sealed STOA fixture + verified manifest + Contribution links | Yes | ✓ FLOWING |
| `workflow.py` | `answers`/`coverage` | user `AuditAction` transitions | Yes | ✓ FLOWING, subject to lost-update gap |
| `workflow.py` | conclusion basis | answers plus inspected facts | Yes but over-broad | ⚠️ STATIC/OVERBROAD BASIS |
| `store.py` | snapshot/events | canonical JSON snapshot and append log | Yes | ⚠️ FLOWING WITH LINEAGE GAPS |

## Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|---|---|---|---|
| Full locked offline suite | `UV_CACHE_DIR=/tmp/career-evidence-uv-cache uv run --locked python scripts/run_pytest.py -q` | `192 passed, 1 deselected` | ✓ PASS |
| Ruff lint | `UV_CACHE_DIR=/tmp/career-evidence-uv-cache uv run --locked ruff check .` | `All checks passed!` | ✓ PASS |
| Ruff formatting | `UV_CACHE_DIR=/tmp/career-evidence-uv-cache uv run --locked ruff format --check .` | `45 files already formatted` | ✓ PASS |
| Paused audit rejects answer | direct `transition_audit()` probe | `paused_answer paused 1` — answer accepted | ✗ FAIL |
| Deleted earlier event is rejected | direct store tamper probe | `history_delete_read paused` — read accepted | ✗ FAIL |
| English attribution is classified | direct five-answer probe | ownership=`unresolved`, assistance=`unresolved` | ✗ FAIL |
| Review updates canonical state | direct review probe | entry review remained `pending`, whole review `pending` | ✗ FAIL |
| Phase probe collection | `pytest --collect-only` for phase tests | 19 tests collected; exact 28-row matrix test present | ✓ PASS |

## Probe Execution

No `scripts/*/tests/probe-*.sh` files were declared or found for this phase; no external probe was available to execute.

## Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|---|---|---|---|---|
| AUD-01 | 03-01 | Inspect artifacts before questioning and record established facts/rationales. | BLOCKED | Main inspection path is wired and deterministic, but malformed references do not fail closed and event lineage is tamper-incomplete. |
| AUD-02 | 03-01/03-02 | One focused question per turn with lossless pause/resume. | BLOCKED | One-question ladder works, but paused answers are accepted and normal concurrent updates can lose answers. |
| AUD-03 | 03-01/03-02 | Reject repeated/leading/artifact-answerable prompts and probe capability. | SATISFIED | Deterministic hard-to-simple ladder, skip semantics, strict answer contracts, and no numeric mastery behavior are implemented and tests pass. |
| AUD-04 | 03-01/03-02 | Separate ownership, team/other work, assistance, and unresolved attribution. | BLOCKED | Separate rounds and Chinese/unresolved states work, but English answers are systematically misclassified and concurrency is not fail-closed. |
| AUD-05 | 03-01/03-03 | Review/edit/confirm/reject traceable capability-boundary conclusions. | BLOCKED | Proposal and append-only review records exist, but canonical conclusion review state never changes and review/event idempotency/transactionality have gaps. |

## Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|---|---:|---|---|---|
| `src/career_evidence_graph/audit/workflow.py` | 317-324 | Missing lifecycle guards | BLOCKER | Allows answers after pause/terminal state. |
| `src/career_evidence_graph/audit/store.py` | 99-118 | Optional optimistic check / snapshot-first append | BLOCKER | Lost updates and crash ambiguity. |
| `src/career_evidence_graph/audit/store.py` | 68-97 | Last-record-only event verification | BLOCKER | Historical tampering can be accepted. |
| `src/career_evidence_graph/audit/workflow.py` | 290-307 | Review record does not affect canonical conclusion | BLOCKER | Confirm/reject/edit is not reflected to consumers. |
| `src/career_evidence_graph/audit/workflow.py` | 376-404 | Chinese-only attribution parsing despite English prompts | BLOCKER | Valid responsibility/assistance evidence is lost. |
| `src/career_evidence_graph/audit/workflow.py` | 55-70 | Unchecked referential dictionary indexing | WARNING | Malformed fixture can produce uncontrolled traceback. |
| `src/career_evidence_graph/audit/workflow.py` | 205-233 | Artifact refs attached to every area basis | WARNING | Skipped/unresolved areas may appear artifact-supported. |

The two judgment-tier prohibitions in the plans (neutral/no-pressure wording and no automatic disqualification from coding-agent/third-party assistance) were not mechanically adjudicated. Autonomous review records them as `unverified-prohibition — human review recommended`; the implementation does show neutral prompts and separate attribution fields, but this is not a formal human judgment.

## Human Verification Required

Status remains `gaps_found` because the blockers above take precedence. Human review is recommended for the two judgment-tier prohibitions: confirm that prompts do not pressure users into capability claims, and that assistance never automatically disqualifies responsibility or establishes capability.

## Gaps Summary

The phase delivers substantive offline audit models, bounded fixture inspection, deterministic questioning, attribution records, and review records, and the claimed 192-test/Ruff gates reproduce. It does not yet achieve the phase goal as a trustworthy resumable workflow. The five Critical findings from `03-REVIEW.md` remain confirmed in the current code, and all four Warnings are also substantiated: lifecycle bypass, lost-update concurrency, incomplete event-chain integrity, canonical review-state disconnect, English attribution failure, over-broad basis, uncontrolled missing-reference failure, review idempotency ordering, and non-transactional update durability. Phase 4 does not clearly address these audit-integrity gaps, so none are deferred.

---

_Verified: 2026-08-26T00:00:00Z_
_Verifier: the agent (gsd-verifier)_
