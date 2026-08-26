---
phase: 03-artifact-aware-grill-me-and-attribution-workflow
verified: 2026-08-26T18:32:00Z
status: gaps_found
score: 22/24 must-haves verified
behavior_unverified: 0
overrides_applied: 0
re_verification:
  previous_status: passed
  previous_score: 24/24
  gaps_closed: []
  gaps_remaining:
    - "The locked public CLI imports a stale installed AuditStore and can write custody files through a redirected audit root."
    - "The source AuditStore can be redirected by a root symlink swap after validation and before lock creation."
  regressions:
    - "The prior public CLI containment proof exercised scripts/run_career_evidence.py, not the installed career-evidence entry point."
    - "The prior root-link regression covered only a pre-existing symlink, not a post-validation swap."
gaps:
  - truth: "The public locked CLI retains custody files inside the caller-selected workspace."
    status: failed
    reason: "The PEP 660 editable wheel embeds package modules as well as a src .pth path, so uv run --locked career-evidence imports the stale site-packages AuditStore rather than the reviewed checkout source."
    artifacts:
      - path: _career_evidence_build.py
        issue: "_wheel_contents(editable=True) starts with _package_files(), embedding stale modules in the editable wheel."
      - path: pyproject.toml
        issue: "The public career-evidence entry point resolves the installed distribution, not pytest's pythonpath override."
    missing:
      - "Produce a genuinely editable wheel that contains metadata, entry point, and the src .pth but not package modules, or adopt a standard editable backend."
      - "Add a subprocess regression that runs uv sync --locked then uv run --locked career-evidence audit start against workspace/audits -> external and proves the external tree is unchanged."
  - truth: "A validated audit root cannot be redirected outside the workspace before any lock or custody write."
    status: failed
    reason: "_audit_root() validates a pathname, but _locked() subsequently creates .locks by pathname; a local actor can replace the audited directory with a symlink between those operations."
    artifacts:
      - path: src/career_evidence_graph/audit/store.py
        issue: "_locked() calls locks.mkdir() on a previously validated path without retaining a directory handle or preventing symlink traversal."
    missing:
      - "Anchor root, lock, audit-directory, and publication operations to verified directory descriptors using O_DIRECTORY and O_NOFOLLOW with dir_fd APIs, or an equivalent handle-held containment design."
      - "Add a deterministic swap-after-validation regression proving no external lock or custody file is created."
---

# Phase 3: Artifact-Aware Grill-Me and Attribution Workflow Verification Report

**Phase Goal:** As a career-evidence user, I want to complete and resume an artifact-aware audit of a selected Contribution and review its capability and responsibility conclusion, so that I retain a truthful, inspectable record of what the evidence establishes.
**Verified:** 2026-08-26T18:32:00Z
**Status:** gaps_found
**Re-verification:** Yes — prior passing verdict overturned after independent code review and isolated reproduction.

## User Flow Coverage

| Step | Expected | Evidence | Status |
| --- | --- | --- | --- |
| Inspect | Inspect supplied artifacts, established facts, limitations, and question rationale. | Fixture/manifest inspection tests and the public CLI journey pass. | ✓ VERIFIED |
| Start and resume | Receive one focused question; pause and resume the retained audit. | Public CLI E2E exercises start, answer, pause, resume; policy probes cover one active question and stable resume. | ✓ VERIFIED |
| Attribute | Keep ambiguous English/Chinese ownership or assistance unresolved. | Direct bilingual probe and public E2E assert unresolved responsibility and assistance conclusion entries. | ✓ VERIFIED |
| Review | Edit/confirm entries and the whole conclusion, then reopen it. | Public E2E validates effective/original hash lineage, stale-review rejection, replay, completion, and reopen. | ✓ VERIFIED |
| Outcome | Retain a truthful inspectable record inside the chosen workspace. | The public locked CLI uses stale installed code, and source-level pathname validation has a reproducible swap race. | ✗ FAILED |

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
| --- | --- | --- | --- |
| 1 | Artifacts, established facts, limitations, and remaining-question rationale are inspectable before questioning. | ✓ VERIFIED | Fixture inspection plus controlled missing/empty/duplicate/malformed/unverified-manifest rejection probes pass. |
| 2 | One focused question is active; pause/resume preserves audit state without invalid transitions. | ✓ VERIFIED | Policy, lifecycle, CLI, and public journey probes pass under locked persistence. |
| 3 | Question progression is hard-to-simple, avoids groundless prompts, and preserves Unicode exactly. | ✓ VERIFIED | Original exact probe inventory covers stable order, follow-up/descent, blank/exhausted guards, and Unicode round trips. |
| 4 | Responsibility and assistance are separate; ownership, team, other, coding-agent-assisted, third-party, and unresolved claims remain truthful. | ✓ VERIFIED | Separate round/order tests and bilingual unresolved-conclusion regression pass. |
| 5 | The conclusion exposes capability boundaries, basis, attribution, unresolved points, and editable/confirmable/rejectable reviews. | ✓ VERIFIED | Terminal conclusion/review contract tests and public E2E pass. |
| 6 | Event, snapshot, accepted-result, and review lineage are hash-linked, replay-safe, recoverable, and stale writers/reviewers cannot overwrite state. | ✓ VERIFIED | CAS, effective-hash freshness, chain-tamper, recovery, and replay regressions pass. |
| 7 | The public CLI and source implementation keep audit custody inside the selected workspace, including against redirected roots. | ✗ FAILED | `uv run --locked career-evidence` imported `.venv/.../site-packages/career_evidence_graph/cli.py` and wrote an external `.locks` and audit files through `workspace/audits -> external`; a source-imported deterministic post-validation symlink swap also created `external/.locks/audit-race.lock`. |
| 8 | The MVP Phase 3 goal is a valid user story without weakening its outcome. | ✓ VERIFIED | Central `user-story.validate` returns `valid: true` with role, capability, and outcome slots. |

**Score:** 22/24 must-haves verified (0 present-but-behavior-unverified).

### Required Artifacts

| Artifact | Expected | Status | Details |
| --- | --- | --- | --- |
| `src/career_evidence_graph/audit/store.py` | Verified audit-root containment and locked custody authority | ✗ FAILED | It rejects a pre-existing root link but does not retain a verified root descriptor; a check-to-lock symlink replacement redirected lock creation outside the workspace. |
| `_career_evidence_build.py` | Public editable installation executes reviewed source | ✗ FAILED | Editable wheels include package modules before adding the .pth file; the public CLI currently resolves the stale installed module. |
| `src/career_evidence_graph/audit/workflow.py` | Fixture-bounded inspection, lifecycle, attribution, and conclusion transitions | ✓ VERIFIED | `start_audit()` persists via `AuditStore.save()`; mutations are called through `AuditStore.transact()` by CLI. |
| `src/career_evidence_graph/cli.py` | Offline user entry point | ✓ VERIFIED | Public subprocess E2E parses real actions and reaches workflow/store transaction paths. |
| `tests/test_audit_storage_regressions.py` | External-target-preserving containment regressions | ⚠️ PARTIAL | Covers a pre-existing link via source import only; it does not execute the installed CLI nor force a post-validation link swap. |
| `tests/test_audit_gap_e2e.py` | End-to-end inspect/start/pause/resume/attribution/review/reopen flow | ✓ VERIFIED | Real subprocess CLI, not stubbed transitions. |
| `tests/test_validation_probe_matrix.py` | Exact phase acceptance inventory | ✓ VERIFIED | Collects exactly 28 original plus 15 gap probes. |
| `.planning/ROADMAP.md` | Canonical MVP goal | ✓ VERIFIED | Keeps `Mode: mvp` and passes centralized user-story validation. |

### Key Link Verification

| From | To | Via | Status | Details |
| --- | --- | --- | --- | --- |
| `AuditStore` workspace boundary | `workspace/audits` custody root | `_audit_root()` before paths, locks, reads, publication, transactions, and updates | ✗ NOT WIRED SAFELY | The public CLI has a different stale implementation, and source path validation is not preserved across the subsequent lock/write operations. |
| CLI | workflow/store | parsed action → `transition_audit` in `AuditStore.transact()` | ✓ WIRED | Public E2E passes. |
| workflow | sealed STOA fixture | manifest/link validation → inspection facts | ✓ WIRED | Real fixture-backed inspection tests pass. |
| MVP mode | Phase 3 goal | centralized user-story validator | ✓ WIRED | `valid: true`; all required slots extracted. |

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
| --- | --- | --- | --- | --- |
| `workflow.py` | inspected artifacts, facts, limitations, question reasons | sealed STOA fixture, manifest, Contribution links | Yes | ✓ FLOWING |
| `workflow.py` | answers, coverage, attribution, conclusion | validated public `AuditAction` records | Yes | ✓ FLOWING |
| `store.py` | snapshots, events, accepted results, reviews | verified per-audit custody files | Yes | ✓ FLOWING |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
| --- | --- | --- | --- |
| Canonical MVP story | `node ... gsd-tools.cjs query user-story.validate --story "$PHASE_GOAL" --raw` | `valid: true`; all slots present | ✓ PASS |
| Exact closure inventory | `uv sync --locked && uv run --locked pytest --collect-only -q -m phase03_gap_probe ...` | `15/31 tests collected (16 deselected)` | ✓ PASS |
| Full executable audit behavior | `uv sync --locked && uv run --locked pytest -q` | `233 passed, 1 deselected` | ✓ PASS |
| Lint | `uv sync --locked && uv run --locked ruff check .` | `All checks passed!` | ✓ PASS |
| Formatting | `uv sync --locked && uv run --locked ruff format --check .` | `49 files already formatted` | ✓ PASS |
| Locked public CLI containment | `uv run --locked career-evidence implementation-path; ... audit start` with `workspace/audits -> external` in a fresh `/private/tmp` fixture | Entry point resolved `.venv/.../site-packages/.../cli.py`; external `.locks/audit-cli-stale.lock`, snapshot, events, and accepted-results files were created | ✗ FAIL |
| Post-validation root swap | Source-imported `AuditStore` subclass swaps `workspace/audits` after `_audit_root()` returns and before `_locked()` creates the lock | `external/.locks/audit-race.lock` was created | ✗ FAIL |

### Requirements Coverage

| Requirement | Source Plans | Status | Evidence |
| --- | --- | --- | --- |
| AUD-01 | 03-01, 03-04–03-07, 03-10 | ✗ BLOCKED | The claimed contained audit custody is bypassable through the locked CLI and a source-level root-swap race. |
| AUD-02 | 03-01–03-10 | ✓ SATISFIED | One-active-question lifecycle, pause/resume, CAS, recovery, and public CLI journey. |
| AUD-03 | 03-01, 03-02, 03-06, 03-07 | ✓ SATISFIED | Hard-to-simple policy, blank/exhausted guards, no repeated active question, exact original probes. |
| AUD-04 | 03-01, 03-02, 03-04, 03-06, 03-07, 03-09, 03-10 | ✓ SATISFIED | Separate attribution and bilingual ambiguity regression prevent capability laundering. |
| AUD-05 | 03-01, 03-03–03-10 | ✗ BLOCKED | Review lineage files can be redirected outside the selected workspace through the same custody-boundary defects. |

### Anti-Patterns Found

| File | Pattern | Severity | Impact |
| --- | --- | --- | --- |
| `_career_evidence_build.py` | Editable wheel embeds package sources | 🛑 BLOCKER | Installed public CLI bypasses reviewed containment code. |
| `src/career_evidence_graph/audit/store.py` | Path check followed by path-based lock/write | 🛑 BLOCKER | A local symlink swap redirects custody files outside the chosen workspace. |

### Disconfirmation Checks

- Previously failing public stale-update and omitted-review-freshness cases now reject through direct regressions.
- The containment test calls public `start_audit()` and compares external bytes, proving behavior rather than symbol presence.
- Malformed CLI actions and wrong question targets assert controlled errors with zero workspace writes.

## Gaps Summary

The prior completed status must be reversed. Both blockers violate the Phase 3 outcome that the user retains a truthful, inspectable record in the chosen workspace:

1. The locked, user-facing `career-evidence` CLI is not executing the reviewed checkout source. In an isolated temporary workspace, it wrote lock, snapshot, event, and accepted-result files under an external directory targeted by `workspace/audits`.
2. The reviewed source rejects a link only at check time. In a deterministic isolated probe, replacing the root immediately after `_audit_root()` returned caused `_locked()` to create an external lock.

The existing pre-existing-link test and source-path pytest configuration cannot establish the public CLI or race-safe containment guarantees. Plan and implement the two specific missing protections above, then re-run containment tests through the installed locked CLI and a deterministic swap regression before restoring a passing verdict.

---

_Verified: 2026-08-26T18:32:00Z_
_Verifier: the agent (gsd-verifier)_
