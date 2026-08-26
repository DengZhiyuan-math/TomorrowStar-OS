---
phase: 03-artifact-aware-grill-me-and-attribution-workflow
verified: 2026-08-26T15:17:51Z
status: gaps_found
score: 17/21 must-haves verified
behavior_unverified: 0
overrides_applied: 0
re_verification:
  previous_status: gaps_found
  previous_score: 14/21
  gaps_closed:
    - "Malformed selected claim/evidence references now fail closed."
    - "Invalid lifecycle actions now reject without persistence."
    - "Event history is fully hash-linked and tamper-detecting."
    - "Supported English and Chinese attribution parse equivalently."
    - "Review actions update canonical conclusion state."
    - "Replay is resolved before stale-head rejection."
    - "Interrupted publication is recoverable."
    - "Conclusion basis separates documentary context from answer evidence."
  gaps_remaining:
    - "Programmatic AuditStore.update() permits a stale snapshot to overwrite newer state."
  regressions:
    - "Review actions accept an omitted effective-conclusion precondition."
    - "Ambiguous ownership or assistance is labelled audit-verified in a conclusion."
gaps:
  - truth: "Competing actions cannot merge answers, lose updates, or overwrite attribution/conflicts."
    status: failed
    reason: "AuditStore.update() obtains the current head when expected_event_hash is omitted and publishes its caller-supplied snapshot."
    artifacts:
      - path: "src/career_evidence_graph/audit/store.py"
        issue: "update(snapshot, expected_event_hash=None) is an unprotected replacement API."
    missing:
      - "Remove update() or require caller-held event hash and derive every replacement from locked current state."
  - truth: "Ambiguous responsibility or assistance remains unresolved instead of establishing verified capability."
    status: failed
    reason: "transition_audit() marks a nonempty responsibility/assistance answer verified before conservative classification."
    artifacts:
      - path: "src/career_evidence_graph/audit/workflow.py"
        issue: "Unresolved attribution emits verified coverage and audit-verified conclusion prose."
    missing:
      - "Set responsibility/assistance coverage unresolved for unresolved attribution and prevent verified conclusions."
  - truth: "Review actions are guarded by the current effective conclusion as well as the event head."
    status: failed
    reason: "expected_effective_conclusion_hash is optional and the workflow compares it only when supplied."
    artifacts:
      - path: "src/career_evidence_graph/audit/models.py"
        issue: "Review validation does not require an effective conclusion hash."
      - path: "src/career_evidence_graph/audit/workflow.py"
        issue: "Effective-hash comparison is conditional."
    missing:
      - "Require and unconditionally compare expected_effective_conclusion_hash for all review actions."
deferred: []
---

# Phase 3: Artifact-Aware Grill-Me and Attribution Workflow Verification Report

**Phase Goal:** A user can complete a resumable, artifact-aware audit of a selected Contribution and explicitly confirm what capability and responsibility the evidence establishes.
**Verified:** 2026-08-26T15:17:51Z
**Status:** gaps_found
**Re-verification:** Yes — after gap-only execution

## Goal Achievement

The earlier lifecycle, fixture-reference, bilingual-attribution, canonical-review, full-chain, replay, durability, and basis gaps are closed. The goal remains unmet because public Python write/review seams bypass custody or truthfulness guarantees, and ambiguous responsibility is turned into a verified capability conclusion.

### Observable Truths

| # | Truth | Status | Evidence |
| --- | --- | --- | --- |
| 1 | Artifacts, established facts, and question rationale are inspectable before questioning. | ✓ VERIFIED | `inspect_contribution()` validates manifest/link references, returns sorted facts/limitations, and `start_audit()` creates a reason-prefaced first question. |
| 2 | Overlapping facts retain locators and do not become ownership claims. | ✓ VERIFIED | Link identity is evidence ID plus locator; facts are documentary-only and duplicate links reject. |
| 3 | Invalid selection, empty evidence, malformed references, or an unverified manifest fail closed. | ✓ VERIFIED | Controlled `AuditWorkflowError` guards cover missing Contribution, link references, empty links, duplicates, and manifest validation. |
| 4 | Inspection/creation are deterministic and bounded under creation competition. | ✓ VERIFIED | Stable sorting/question IDs; locked save rejects existing IDs; marked tests pass. |
| 5 | One focused question is active and invalid lifecycle transitions are rejected. | ✓ VERIFIED | Explicit active/paused/reviewing/terminal table; public E2E proves paused answer exits 2 without writes. |
| 6 | Offline CLI crosses inspection, pause/resume, attribution, review, reopen, tamper rejection, and recovery. | ✓ VERIFIED | `test_repaired_audit_cli_journey_preserves_custody_and_reopens` invokes real subcommands and passed. |
| 7 | Competing actions cannot merge answers or lose updates. | ✗ FAILED | Winner write followed by `AuditStore.update(stale_snapshot)` succeeded; final answer was `stale writer`. |
| 8 | Question/event ordering, one active action, and exact replay are stable. | ✓ VERIFIED | Hash-linked sequence validation and action-ID-first replay receipts are implemented and tested. |
| 9 | One same-level follow-up precedes hard-to-simple descent. | ✓ VERIFIED | `follow_up_count`/descent policy are covered by marked policy tests. |
| 10 | Blank/exhausted areas cannot create ungrounded questions or conclusions. | ✓ VERIFIED | Strict action validation and terminal coverage gating pass policy/conclusion tests. |
| 11 | Unicode answers and reasons round-trip exactly. | ✓ VERIFIED | Strict UTF-8 models/persistence and marked Unicode coverage pass. |
| 12 | Relevant-area progression and normal CLI coverage updates are deterministic. | ✓ VERIFIED | CLI uses `transact()` with required event head and fixed area order. |
| 13 | Ownership precedes assistance and ambiguous responsibility/assistance is separated or unresolved. | ✗ FAILED | `maybe the team and I did it` produces ownership `unresolved` but responsibility coverage `verified` and conclusion `audit-verified`. |
| 14 | Absent, Unicode, and explicit unresolved attribution remain distinct. | ✓ VERIFIED | Literal contracts preserve states; English/Chinese equivalence regression passes. |
| 15 | Competing attribution answers cannot overwrite a conflict or proposal. | ✗ FAILED | The unprotected `update()` seam can replace later attribution/conflict state with a stale snapshot. |
| 16 | Entry and whole-conclusion reviews remain separate ordered records. | ✓ VERIFIED | Separate targets and immutable review records persist in canonical conclusion state. |
| 17 | A proposal requires terminal coverage and records boundaries, basis, attribution, and provisional fields. | ✓ VERIFIED | `_build_conclusion()` gates all five areas and builds these fields. |
| 18 | Review data remains exact and original proposal custody immutable. | ✓ VERIFIED | Original/effective hashes and immutable original proposal are asserted by workflow/E2E tests. |
| 19 | Review history follows event order; exact replays are stable; lineage is durable. | ✓ VERIFIED | Full chain, result anchoring, and journal recovery are implemented/tested. |
| 20 | Review actions require current event and effective-conclusion hashes. | ✗ FAILED | Event head is required by `transact()`, but Python callers can omit the effective hash. |
| 21 | Verified conclusions contain prose only; skipped numeric ratings are unverified text. | ✓ VERIFIED | No numeric conclusion fields; marked no-score regression passes. |

**Score:** 17/21 truths verified (0 present-but-behavior-unverified).

### Required Artifacts

| Artifact | Expected | Status | Details |
| --- | --- | --- | --- |
| `audit/models.py` | Strict action/event/conclusion contracts | ⚠️ PARTIAL | Wired/substantive, but review effective hash is optional. |
| `audit/workflow.py` | Inspection, lifecycle, attribution, conclusion transitions | ⚠️ PARTIAL | Earlier lifecycle/reference/review fixes hold; unresolved attribution is overclaimed. |
| `audit/store.py` | Locked, hash-linked, recoverable custody | ⚠️ PARTIAL | `transact()` is CAS-guarded; compatibility `update()` is not. |
| `cli.py` | Offline audit command group | ✓ VERIFIED | Commands require event heads and review hashes; dispatches via `transact()`. |
| `tests/test_audit_gap_e2e.py` | Real public-CLI journey | ✓ VERIFIED | Subprocess E2E is substantive and passed. |
| `tests/test_validation_probe_matrix.py` | Executable acceptance inventory | ✓ VERIFIED | Collect-only proof requires exactly 28 original plus nine gap nodes. |

### Key Link Verification

| From | To | Via | Status | Details |
| --- | --- | --- | --- | --- |
| `cli.py` | `workflow.py` | parsed action → transition | ✓ WIRED | CLI invokes `transition_audit` inside `AuditStore.transact`. |
| `workflow.py` | sealed STOA fixture | manifest + Contribution links | ✓ WIRED | Facts originate in verified sealed fixture data. |
| `workflow.py` | `models.py` | strict snapshots/actions/conclusions | ✓ WIRED | Pydantic validation is at domain boundaries. |
| `cli.py` | `store.py` | replay-first CAS transaction | ✓ WIRED | CLI mutation requires `--expected-event-hash`. |
| `store.py` | event/result files | lock + recovery publication | ✓ WIRED | Read validates chain, snapshot hash, and receipt anchoring. |
| `AuditStore.update()` | `store.transact()` | compatibility replacement | ✗ UNSAFE | It synthesizes the latest head rather than requiring caller’s stale version. |

### Data-Flow Trace (Level 4)

| Artifact | Data variable | Source | Produces Real Data | Status |
| --- | --- | --- | --- | --- |
| `workflow.py` | inspected facts/limitations | sealed fixture, manifest, links | Yes | ✓ FLOWING |
| `workflow.py` | answers, coverage, attribution | user `AuditAction` | Yes | ⚠️ FLOWING WITH ATTRIBUTION GAP |
| `workflow.py` | conclusion basis | terminal coverage and answer references | Yes | ✓ FLOWING |
| `store.py` | snapshot, event chain, receipts | per-audit custody files | Yes | ⚠️ FLOWING WITH UNSAFE WRITE |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
| --- | --- | --- | --- |
| Locked full suite | `UV_CACHE_DIR=/tmp/career-evidence-uv-cache uv run --locked python scripts/run_pytest.py -q` | `226 passed, 1 deselected` | ✓ PASS |
| Lint/format | locked Ruff check/format | clean; `49 files already formatted` | ✓ PASS |
| Stale replacement resistance | isolated `AuditStore.update()` two-writer probe | Final answer `stale writer`; 3 events | ✗ FAIL |
| Ambiguous attribution truthfulness | isolated five-answer workflow probe | unresolved ownership became verified coverage/conclusion | ✗ FAIL |
| Effective review precondition | direct `AuditAction` construction | review validates with effective hash omitted | ✗ FAIL |
| Acceptance inventory | marker collection gate in full suite | exact 28+9 nodes | ✓ PASS |

### Probe Execution

No declared `scripts/*/tests/probe-*.sh` files exist. The relevant executable probes are pytest functions; their full suite and marker-inventory gate passed.

### Requirements Coverage

| Requirement | Source Plans | Description | Status | Evidence |
| --- | --- | --- | --- | --- |
| AUD-01 | 03-01, 03-04, 03-05 | Inspect supplied artifacts and record facts/rationales. | SATISFIED | Verified manifest/link inspection and controlled malformed-reference errors; reads reject tampering. |
| AUD-02 | 03-01, 03-02, 03-04, 03-05 | One focused question and lossless resumability. | BLOCKED | CLI is protected, but public `update()` permits lost updates. |
| AUD-03 | 03-01, 03-02, 03-06 | Reject weak prompts and probe capability. | SATISFIED | Fixed one-question hard-to-simple policy and marked tests pass. |
| AUD-04 | 03-01, 03-02, 03-04 | Separate responsibility/assistance or leave unresolved. | BLOCKED | Unresolved text is promoted to verified conclusion coverage. |
| AUD-05 | 03-01, 03-03, 03-04, 03-05 | Review/edit/confirm/reject traceable conclusions. | BLOCKED | Canonical review state exists, but Python review can omit effective-hash precondition. |

### Decision Coverage

`check.decision-coverage-verify` reported **16/16** trackable `03-CONTEXT.md` decisions honored. This advisory result does not override the gaps.

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
| --- | ---: | --- | --- | --- |
| `audit/store.py` | 249-257 | Compatibility write defaults expected head to latest head. | BLOCKER | Stale snapshot can roll back newer mutation. |
| `audit/models.py` | 118, 121-132 | Review effective hash optional. | BLOCKER | Direct caller bypasses projection stale check. |
| `audit/workflow.py` | 520-558 | Coverage set verified before attribution classification. | BLOCKER | Ambiguous attribution becomes verified capability. |
| `cli.py` | 382 | Invalid action validation reaches generic error envelope. | WARNING | Invalid payload has less-specific diagnostics. |
| `audit/workflow.py` | 479-488 | Supplied `question_id` ignored. | WARNING | Caller target assertion is silently discarded. |

No `TBD`, `FIXME`, or `XXX` markers were found in Phase 03 artifacts. The `return None` in `_build_conclusion()` is a terminal-coverage guard, not a stub.

### Human Verification Required

Judgment-tier prohibitions remain non-authoritative human checks even though blockers already determine status:

1. **Neutral skip/uncertainty handling** — exercise prompts for skip and unresolved responsibility. Expected: no coercion, shame, or penalty for uncertainty. Human review is required because tone is judgment-tier.
2. **Assistance separation** — review coding-agent and third-party responses. Expected: assistance neither establishes mastery nor automatically disqualifies responsibility. Human review is required because this is semantic/truthfulness judgment.

### Gaps Summary

Three blockers remain. The full suite and exact marker inventory demonstrate an executable repaired happy path, but do not cover the public compatibility writer, omitted effective review hashes, or mixed ambiguous attribution. These contradict AUD-02, AUD-04, and AUD-05 and are not deferred: later phases concern assessment/JD calibration, not audit integrity.

---

_Verified: 2026-08-26T15:17:51Z_
_Verifier: the agent (gsd-verifier)_
