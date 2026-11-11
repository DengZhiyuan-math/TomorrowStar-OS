---
status: resolved
trigger: "修复 milestone 归档后全套测试仍引用旧 .planning/phases 路径的问题"
created: 2026-08-28T18:54:01Z
updated: 2026-08-28T19:45:00Z
---

## Current Focus

hypothesis: The hard-coded active-layout locator causes all path-dependent fixture failures because milestone archival changes the checkpoint's location without changing its content or hash-bound identity.
test: Replace only path discovery with one centralized active-or-archive resolver, then rerun the exact failing test and adjacent sealed-loader tests.
expecting: Exact reproduction turns green, active-layout scratch tests remain green, archived layout resolves, and simultaneous active/archive copies fail closed.
next_action: Ask the user to confirm the archived-milestone workflow now succeeds in their real invocation; archive only after confirmation.
bug_class: bohrbug
reasoning_checkpoint:
  hypothesis: "A hard-coded .planning/phases locator causes fixture loading to fail after GSD moves the same hash-bound Phase 2 checkpoint into .planning/milestones/v1.0-phases."
  confirming_evidence:
    - "The representative test fails directly at read_bytes on the missing active path."
    - "Exactly one archived checkpoint exists and its hash remains the checkpoint_summary_hash sealed in review.json and known-good.json."
    - "A centralized resolver makes the exact reproduction and adjacent sealed-loader tests pass."
  falsification_test: "If the exact reproduction still fails after resolving the sole archived checkpoint, or its bytes fail the sealed hash check, the hypothesis is false."
  fix_rationale: "Resolve the immutable evidence by its canonical phase/file identity across GSD's two supported lifecycle locations, while requiring exactly one candidate so custody remains fail-closed."
  blind_spots: "The full suite and CLI sealing path have not yet been exercised after the change; milestone naming is assumed to retain GSD's *-phases convention."
  candidate_causes:
    - "code: production and tests hard-code the mutable active-phase path."
    - "environment: filesystem layout changed through normal milestone archival."
    - "data: checkpoint bytes or recorded hash may have drifted, which was checked and not observed."
  and_gate: "no — the hard-coded locator alone explains the failure; archival is the valid lifecycle event that exposes it, not a defect requiring a second corrective cause."
tdd_checkpoint: null

## Symptoms

expected: Archiving a completed milestone should preserve historical evidence and leave the repository's authoritative offline test suite green.
actual: After phase directories moved to .planning/milestones/v1.0-phases, the authoritative suite reports 231 passed, 151 failed, and 1 deselected because code and tests still resolve .planning/phases/.../02-04-SUMMARY.md.
errors: Representative fixture validation reports canonical known-good review inputs are invalid or cannot find the old active Phase 2 summary path.
reproduction: Run uv run --locked python scripts/run_pytest.py -q or a representative STOA fixture validation test after the v1.0 milestone archive.
started: Began when v1.0 milestone closeout archived .planning/phases into .planning/milestones/v1.0-phases on 2026-08-28.

## Eliminated

## Evidence

- timestamp: 2026-08-28T18:54:01Z
  checked: Current source and test references to .planning/phases and 02-04-SUMMARY.md.
  found: Production fixture and CLI code plus multiple tests hard-code the pre-archive path; the archived file exists under .planning/milestones/v1.0-phases.
  implication: The failure is an application-level provenance locator defect, not merely stale test data.
- timestamp: 2026-08-28T19:09:00Z
  checked: Representative test tests/test_stoa_fixture.py::test_review_materialization_preserves_human_corrections_and_unresolved_values.
  found: It fails deterministically at Path.read_bytes() for the removed active .planning/phases/.../02-04-SUMMARY.md path.
  implication: The bug is a Bohrbug caused before fixture semantics execute; path discovery is the fault boundary.
- timestamp: 2026-08-28T19:09:30Z
  checked: Archived Phase 2 checkpoint and sealed fixture metadata.
  found: Exactly one archived 02-04-SUMMARY.md exists under .planning/milestones/v1.0-phases, while review.json and known-good.json retain its sha256 custody value.
  implication: Archive relocation did not invalidate evidence content; only the mutable filesystem locator became stale.
- timestamp: 2026-08-28T19:17:00Z
  checked: Central active-or-archive resolver against archived repository, active scratch layout, and simultaneous active/archive candidates.
  found: Archived and active layouts each resolve uniquely; simultaneous candidates raise SourceScopeError; exact failing and adjacent sealed-loader tests pass (3 passed).
  implication: The path-locator hypothesis is causally supported and the proposed fix preserves fail-closed provenance.
- timestamp: 2026-08-28T19:26:00Z
  checked: Revert-and-reconfirm using a path-scoped temporary stash.
  found: With only the six fix files reverted, the original representative test returned the same FileNotFoundError; after restoring the fix, target plus boundary tests passed (2 passed).
  implication: The change is causally necessary and sufficient for the recorded reproduction.
- timestamp: 2026-08-28T19:26:30Z
  checked: Ruff and complete offline pytest suite after the fix.
  found: Ruff passed and the complete suite exited successfully; an explicit final test count is being captured for the verification record.
  implication: No adjacent regression has been observed.
- timestamp: 2026-08-28T19:30:30Z
  checked: Complete authoritative offline suite with collection summary.
  found: Pytest collected 384 items, deselected 1, selected 383, and exited 0; Ruff also passed on every changed file.
  implication: The prior 151 path-derived failures are cleared without an observed adjacent regression.

## Resolution

root_cause: Production and test provenance loading hard-coded the mutable active .planning/phases location instead of resolving the sole canonical Phase 2 checkpoint across active and archived milestone layouts.
fix: Added one stdlib Path-based resolver that accepts exactly one active-or-archived canonical checkpoint, reused it in sealed loading, CLI sealing, and repository-backed tests, and added ambiguity regression coverage.
verification:
  target_test: {result: pass}
  mutation_check: {result: skipped, reason_if_skipped: "No Python mutation framework is configured; the agent-authored active/archive/ambiguity boundary test exercises the changed predicate."}
  no_op_deletion: {result: pass, deletion_justified_by_rca: false}
  adjacent_tests: {result: pass, suites_run: ["ruff changed files", "383-test authoritative offline pytest suite"]}
  revert_and_reconfirm: {result: pass, bug_returned_on_revert: true, fixed_on_reapply: true}
  guardrail_verdict: accepted
oracle_type: specified
files_changed:
  - src/career_evidence_graph/domain/fixtures.py
  - src/career_evidence_graph/domain/__init__.py
  - src/career_evidence_graph/cli.py
  - tests/test_stoa_fixture.py
  - tests/test_assessment_admission.py
  - tests/test_policy_calibration.py

## Prevention

- code branch: The evidence loader encoded one lifecycle location as the canonical identity; the resolver now centralizes identity lookup across active and archived layouts and fails closed unless exactly one candidate exists.
- environment branch: Normal milestone archival changes the filesystem location while preserving checkpoint bytes; repository-backed tests now exercise both supported lifecycle layouts instead of assuming the active layout persists.
- data branch: The sealed hash remained unchanged, confirming that evidence content was not the cause and must continue to be verified independently after location resolution.
- why_not_caught: No pre-archive gate exercised sealed fixture loading against the post-archive milestone layout.
- recurrence_guard: Regression test `tests/test_stoa_fixture.py::test_checkpoint_summary_resolves_active_or_archived_layout_and_rejects_ambiguity` covers active, archived, and ambiguous layouts; the full 383-test offline suite passed.
