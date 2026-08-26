---
phase: 03-artifact-aware-grill-me-and-attribution-workflow
verified: 2026-08-26T19:54:02Z
status: gaps_found
score: 22/24 must-haves verified
behavior_unverified: 0
overrides_applied: 0
re_verification:
  previous_status: gaps_found
  previous_score: 22/24
  gaps_closed:
    - "The installed editable entry point no longer embeds a stale AuditStore; the fresh-environment public command resolves the checkout cli.py."
    - "A replacement of the audits child after its descriptor is opened is rejected before an external custody write."
  gaps_remaining:
    - "The public CLI follows a symlink in an ancestor of the caller-supplied workspace and writes the full audit custody tree outside that workspace."
    - "Replacing .locks after its descriptor is opened creates separate per-audit locks; concurrent same-head transactions can race into an unreadable accepted-result/event state."
  regressions:
    - "The installed containment test covers workspace/audits as a pre-existing link but not an ancestor of --workspace."
    - "The descriptor test binds audit root and audit directory but never re-binds root_fd/.locks to locks_fd before use or before publication."
gaps:
  - truth: "The public locked CLI retains every audit custody file inside the caller-selected workspace."
    status: failed
    reason: "_root_session() uses Path.mkdir(parents=True) and os.open(self.workspace, O_NOFOLLOW); O_NOFOLLOW protects only the final component. A symlink in an existing parent is followed before the final workspace directory is opened."
    artifacts:
      - path: src/career_evidence_graph/audit/store.py
        issue: "Lines 105-106 traverse all pre-final workspace path components by pathname."
      - path: tests/test_audit_installation_regressions.py
        issue: "The installed-CLI test covers a linked audits child but no linked ancestor of --workspace."
    missing:
      - "Resolve the user-supplied workspace from a trusted directory descriptor one component at a time, rejecting dot components and every symlinked component with O_DIRECTORY|O_NOFOLLOW."
      - "Add a literal installed-CLI regression with entry/link -> external and prove an exact external-tree snapshot remains unchanged."
  - truth: "Each per-audit transaction has one stable mutex and preserves a readable, hash-linked event/result chain under concurrent same-head actions."
    status: failed
    reason: "_locked() holds locks_fd but never verifies that root_fd/.locks still names that inode. Renaming .locks and creating a replacement lets concurrent sessions flock different files for the same audit."
    artifacts:
      - path: src/career_evidence_graph/audit/store.py
        issue: "Lines 143-179 bind the lock file inside locks_fd but do not bind root_fd/.locks to locks_fd after acquisition, before reads, or before publication."
      - path: tests/test_audit_storage_regressions.py
        issue: "Existing root/audit swap and hard-link probes do not replace .locks after one transaction has acquired its descriptor."
    missing:
      - "Carry locks_fd as a bound authority and compare root_fd/.locks with locks_fd before transaction reads and before/after publication; fail closed if replaced."
      - "Add a deterministic two-writer replacement regression proving exactly one same-head action can commit, the other gets stale-head rejection, and read() remains valid."
---

# Phase 3: Artifact-Aware Grill-Me and Attribution Workflow Verification Report

**Phase Goal:** As a career-evidence user, I want to complete and resume an artifact-aware audit of a selected Contribution and review its capability and responsibility conclusion, so that I retain a truthful, inspectable record of what the evidence establishes.
**Verified:** 2026-08-26T19:54:02Z
**Status:** gaps_found
**Re-verification:** Yes — the two prior gaps closed, but independent final review found two distinct filesystem-authority gaps.

## User Flow Coverage

| Step | Expected | Evidence | Status |
| --- | --- | --- | --- |
| Inspect | Inspect supplied artifacts, established facts, limitations, and question rationale. | Fixture/manifest inspection and lifecycle probes pass. | ✓ VERIFIED |
| Start and resume | Receive one focused question; pause and resume the retained audit. | Policy, CLI, and normal persistence journeys pass; concurrent lock-directory replacement can still make the retained record unreadable. | ✗ FAILED |
| Attribute | Keep ambiguous English/Chinese ownership or assistance unresolved. | Bilingual unresolved-attribution regression passes. | ✓ VERIFIED |
| Review | Edit/confirm entries and the whole conclusion, then reopen it. | Review lineage tests pass in normal operation; its persisted custody can be redirected or corrupted by the failed storage boundaries. | ✗ FAILED |
| Outcome | Retain a truthful inspectable record inside the chosen workspace. | Literal installed CLI wrote its complete custody tree beneath an external target through an ancestor symlink. | ✗ FAILED |

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
| --- | --- | --- | --- |
| 1 | Artifacts, established facts, limitations, and remaining-question rationale are inspectable before questioning. | ✓ VERIFIED | Fixture inspection and malformed/missing/duplicate/unverified-manifest probes pass. |
| 2 | One focused question is active; pause/resume preserves audit state without invalid transitions. | ✗ FAILED | Normal lifecycle tests pass, but an attacker replacing `.locks` can split the lock and leave `read()` with `accepted result index is incomplete`, so a retained audit is not reliably resumable. |
| 3 | Question progression is hard-to-simple, avoids groundless prompts, and preserves Unicode exactly. | ✓ VERIFIED | Exact original probe inventory covers ordering, descent, blank/exhausted guards, and Unicode round trips. |
| 4 | Responsibility and assistance are separate; ownership, team, other, coding-agent-assisted, third-party, and unresolved claims remain truthful. | ✓ VERIFIED | Separate round/order tests and bilingual unresolved-conclusion regression pass. |
| 5 | The conclusion exposes capability boundaries, basis, attribution, unresolved points, and editable/confirmable/rejectable reviews. | ✗ FAILED | The normal review contract passes, but its custody files share the redirectable/corruptible storage authority. |
| 6 | Event, snapshot, accepted-result, and review lineage are hash-linked, replay-safe, recoverable, and stale writers/reviewers cannot overwrite state. | ✗ FAILED | Two sessions with the same event head acquired different lock files after `.locks` replacement; the isolated probe then produced `accepted result index is incomplete` rather than the required stale-head outcome. |
| 7 | The public CLI and source implementation keep audit custody inside the selected workspace, including against redirected roots. | ✗ FAILED | Literal `uv run --locked career-evidence audit start --workspace entry/link/nested-workspace` returned 0 and created lock, snapshot, events, and accepted-result files under `external/nested-workspace`. |
| 8 | The MVP Phase 3 goal is a valid user story without weakening its outcome. | ✓ VERIFIED | Central `user-story.validate` remains valid with all slots extracted. |

**Score:** 22/24 must-haves verified (0 present-but-behavior-unverified).

### Required Artifacts

| Artifact | Expected | Status | Details |
| --- | --- | --- | --- |
| `src/career_evidence_graph/audit/store.py` | Descriptor-held, contained, single-lock audit storage | ✗ FAILED | Child `audits` and audit descriptors are bound, but workspace ancestors and the `.locks` directory are not kept as bound authority. |
| `_career_evidence_build.py` | Public editable installation executes reviewed source | ✓ VERIFIED | Fresh-environment installed-entrypoint regression passes and resolves checkout `src/career_evidence_graph/cli.py`. |
| `tests/test_audit_installation_regressions.py` | Public installed containment proof | ⚠️ PARTIAL | It proves a linked `workspace/audits` child is rejected, but misses a symlink in a workspace ancestor and makes its default path network-dependent. |
| `tests/test_audit_storage_regressions.py` | Storage-race and external-target protection | ⚠️ PARTIAL | Root/audit swap and hard-link cases pass; no test replaces `.locks` after its descriptor has been acquired. |
| `tests/test_validation_probe_matrix.py` | Exact Phase 3 acceptance inventory | ⚠️ PARTIAL | Its 28 original + 20 gap nodes omit both final-review blockers. |
| `src/career_evidence_graph/audit/workflow.py` | Fixture-bounded inspection, lifecycle, attribution, and conclusion transitions | ✓ VERIFIED | `start_audit()` persists through `AuditStore.save()` and mutations reach `AuditStore.transact()`. |
| `src/career_evidence_graph/cli.py` | User-facing audit entry point | ✓ WIRED, UNSAFE BOUNDARY | The literal installed command reaches the current source, but source storage accepts an unsafe ancestor path. |

### Key Link Verification

| From | To | Via | Status | Details |
| --- | --- | --- | --- | --- |
| CLI `--workspace` | workspace directory authority | `_root_session()` → mkdir/open | ✗ NOT WIRED SAFELY | Parent pathname components are followed before the final `O_NOFOLLOW` open. |
| audit root | `.locks` mutex authority | `_mkdir_open(root_fd, ".locks")` → `flock` | ✗ NOT WIRED SAFELY | `locks_fd` is held but never re-bound to the root directory entry. |
| `AuditStore` | audit snapshot/event/result data | directory descriptors plus `dir_fd` publication | ⚠️ PARTIAL | Safe for tested root/audit swaps, unsafe after mutex split. |
| CLI | workflow/store | parsed action → `transition_audit` in `AuditStore.transact()` | ✓ WIRED | Public normal journey and affected tests pass. |
| workflow | sealed STOA fixture | manifest/link validation → inspection facts | ✓ WIRED | Fixture-backed inspection tests pass. |

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
| --- | --- | --- | --- | --- |
| `workflow.py` | inspected artifacts, facts, limitations, question reasons | sealed STOA fixture, manifest, Contribution links | Yes | ✓ FLOWING |
| `workflow.py` | answers, coverage, attribution, conclusion | validated public `AuditAction` records | Yes | ✓ FLOWING |
| `store.py` | snapshots, events, accepted results, reviews | directory-descriptor custody files | Yes, but integrity is breakable | ✗ CORRUPTIBLE |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
| --- | --- | --- | --- |
| Affected automated regressions | `uv run --locked pytest -q tests/test_audit_storage_regressions.py tests/test_audit_installation_regressions.py tests/test_validation_probe_matrix.py` | 13 passed | ✓ PASS, insufficient coverage |
| Lint | `uv run --locked ruff check .` | All checks passed | ✓ PASS |
| Formatting | `uv run --locked ruff format --check .` | 50 files already formatted | ✓ PASS |
| Parent-directory symlink containment | Literal installed `uv run --locked career-evidence audit start` with `entry/link -> external` | Exit 0; created `.locks/audit-parent-link.lock`, snapshot, events, and accepted results beneath external target | ✗ FAIL |
| Post-open `.locks` replacement | Isolated two-thread same-head probe: first transaction acquires old lock, `.locks` is renamed/recreated, second transaction acquires replacement lock | Separate lock files existed; an accepted transaction raced with the other and later `read()` failed `accepted result index is incomplete` | ✗ FAIL |
| Fresh-cache offline installation | Empty `UV_CACHE_DIR` + `UV_PROJECT_ENVIRONMENT`, `UV_OFFLINE=1 uv sync --locked --project .` | Exit 1: `ruff==0.16.0` absent from cache; ordinary fresh-install test omits `--offline`, so it depends on network availability | ⚠️ WARNING |

### Requirements Coverage

| Requirement | Source Plans | Status | Evidence |
| --- | --- | --- | --- |
| AUD-01 | 03-01, 03-04–03-07, 03-10–03-13 | ✗ BLOCKED | The user-selected workspace can be redirected through a parent symlink before audit storage opens. |
| AUD-02 | 03-01–03-13 | ✗ BLOCKED | Split locks permit same-head writers to race into an unreadable retained audit, breaking reliable resume. |
| AUD-03 | 03-01, 03-02, 03-06, 03-07 | ✓ SATISFIED | Question policy probes remain intact. |
| AUD-04 | 03-01, 03-02, 03-04, 03-06, 03-07, 03-09 | ✓ SATISFIED | Attribution semantics and bilingual ambiguity regression remain intact. |
| AUD-05 | 03-01, 03-03–03-13 | ✗ BLOCKED | Review/accepted-result lineage is stored through the same redirectable and mutex-splittable custody path. |

### Anti-Patterns Found

| File | Pattern | Severity | Impact |
| --- | --- | --- | --- |
| `src/career_evidence_graph/audit/store.py` | Final-component-only `O_NOFOLLOW` after `parents=True` traversal | 🛑 BLOCKER | Public CLI writes outside caller-selected workspace through ancestor symlink. |
| `src/career_evidence_graph/audit/store.py` | Held `.locks` descriptor not re-bound to root entry | 🛑 BLOCKER | Same audit can use separate mutexes and corrupt persisted custody. |
| `tests/test_audit_installation_regressions.py` | Empty UV cache with ordinary online `uv sync` inside default pytest | ⚠️ WARNING | Default regression suite is not offline-deterministic on an uncached machine. |

### Test Quality Audit

| Test File | Linked Req | Active | Skipped | Circular | Assertion Level | Verdict |
| --- | --- | --- | --- | --- | --- | --- |
| `tests/test_audit_storage_regressions.py` | AUD-01, AUD-02, AUD-05 | Yes | 0 | No | Behavioral | Insufficient: no `.locks` rebind/split case |
| `tests/test_audit_installation_regressions.py` | AUD-01, AUD-05 | Yes | 0 | No | Behavioral | Insufficient: no ancestor-component link case; fresh setup depends on network |
| `tests/test_validation_probe_matrix.py` | Phase acceptance inventory | Yes | 0 | No | Value | Insufficient: inventory omits both new blockers |

**Disabled tests on requirements:** 0
**Circular patterns detected:** 0
**Insufficient assertions/coverage:** 3 warnings; the two missing security behaviors are blockers because direct isolated reproductions failed.

### Decision Coverage

All 16 trackable Phase 3 CONTEXT decisions are represented in shipped artifacts. This is advisory only and does not override the filesystem-authority blockers.

## Gaps Summary

The installed editable CLI now points at the checkout source, and child-root replacement is blocked. Phase 3 still fails its outcome because the remaining filesystem authority is incomplete:

1. A symlink in any ancestor of the user-supplied workspace is followed before `O_NOFOLLOW` sees the final component, so real CLI custody files leave the selected workspace.
2. The lock directory is treated as a checked path rather than a persistent authority. Replacing it after one session opens it splits the mutex; the isolated same-head probe produced an unreadable accepted-result index rather than a stale-writer rejection.
3. The fresh-install regression's `UV_CACHE_DIR` is deliberately empty and calls online `uv sync`; its behavior is a network integration check, not a deterministic default pytest proof. This warning does not replace either blocker.

These are not deferred to later phases. Further gap planning is required before Phase 3 can pass: one plan must close ancestor-component descriptor traversal and one must bind/revalidate `.locks` across the transaction. The installed-CLI regression should be retained as a separately declared network-capable integration check or rebuilt from local artifacts; the normal default suite must remain offline-deterministic.

---

_Verified: 2026-08-26T19:54:02Z_
_Verifier: the agent (gsd-verifier)_
