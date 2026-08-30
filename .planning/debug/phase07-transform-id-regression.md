---
status: awaiting_human_verify
trigger: "Phase 07 Wave 5 source-aware custody/security integration test fails because the existing complete CLI flow does not supply the newly required --transformation-id argument."
created: 2026-08-31T00:00:00Z
updated: 2026-08-31T09:31:00Z
---

# Phase 07 Transform ID Regression

## Symptoms

- Expected behavior: the complete synthetic CLI flow remains valid after transform gains strict transformation identity.
- Actual behavior: `tests/test_career_source_security.py::test_complete_synthetic_cli_flow_has_no_later_phase_authority_side_effects` exits 2 before transformation.
- Error: `career-source transform: error: the following arguments are required: --transformation-id`.
- Reproduction: `uv run --locked python scripts/run_pytest.py -q tests/test_career_source_custody.py tests/test_career_source_security.py -x`.

## Current Focus

- hypothesis: The Phase 07 security flow fixture invokes the strict public transform CLI using the pre-contract argument set, so argparse rejects it before transformation.
- test: Completed exact target and supplied focused suite after the minimal fixture repair.
- expecting: Met: target passed and all 68 custody/security tests passed with production CLI unchanged.
- next_action: Commit the test and debug record by explicit paths, then hand the checkpoint to the parent orchestrator for human verification.
- bug_class: bohrbug
- reasoning_checkpoint:
    hypothesis: "The stale synthetic security invocation causes argparse exit 2 because it omits the now-required --transformation-id argument."
    confirming_evidence:
      - "The focused command deterministically fails after 64 passes at this invocation with argparse naming only --transformation-id as missing."
      - "src/career_evidence_graph/cli.py declares --transformation-id required, and both comparable custody transform fixtures already pass deterministic synthetic IDs."
    falsification_test: "If adding only the missing synthetic ID does not make the original focused command pass, the stale invocation is not a sufficient root cause."
    fix_rationale: "Updating the fixture to satisfy the strict contract exercises the intended production path without weakening identity, custody, or private-data boundaries."
    blind_spots: "The focused suite does not prove every repository test passes; adjacent custody and security tests are included, while the supplied command is the scoped acceptance gate."
    candidate_causes:
      - "code: one test invocation retained the pre-transformation-identity argument list"
      - "config: uv cache access was sandbox-restricted, but the escalated locked run reproduced the same deterministic argparse failure"
      - "data: the synthetic source payload is accepted by declare/capture and is not involved in argparse rejection"
    and_gate: "no — the stale call alone supplies all conditions needed for the deterministic parser failure; environment and data candidates are ruled out by direct reproduction."

## Evidence

- timestamp: 2026-08-31T00:00:00Z
  observation: Wave 5 integration gate reproduced the failure after 64 passing tests.
- timestamp: 2026-08-31T09:18:00Z
  checked: Focused locked custody/security suite.
  found: The suite reproduced one failure after 64 passes; argparse exited 2 because the security transform invocation omitted --transformation-id.
  implication: The bug is a deterministic Bohrbug localized to the synthetic invocation rather than transformation runtime behavior.
- timestamp: 2026-08-31T09:20:00Z
  checked: Transform parser and comparable custody test invocations.
  found: The public parser intentionally requires --transformation-id, while both custody fixtures already provide deterministic synthetic IDs.
  implication: The compatible repair is to update the stale security fixture, not relax the public CLI contract.
- timestamp: 2026-08-31T09:28:00Z
  checked: Exact failing test after the fixture repair.
  found: tests/test_career_source_security.py::test_complete_synthetic_cli_flow_has_no_later_phase_authority_side_effects passed (1 passed).
  implication: The synthetic flow now satisfies strict transformation identity and completes its authority-boundary assertions.
- timestamp: 2026-08-31T09:29:00Z
  checked: Supplied focused custody/security command after the fixture repair.
  found: All 68 tests passed.
  implication: Adjacent custody behavior and the security boundary remain intact.

## Eliminated

- hypothesis: Runtime, source payload, or private workspace data causes the failure.
  evidence: argparse rejects the argument vector before transformation reads source or workspace state, and the locked run reproduces identically.
  timestamp: 2026-08-31T09:20:00Z

## Resolution

root_cause: The Phase 07 security integration fixture was not updated when transformation identity became a required public CLI argument.
fix: Added deterministic public synthetic transformation ID transform-synthetic-authority to the one stale security CLI invocation.
verification:
  target_test: {result: pass, detail: "1 passed"}
  mutation_check: {result: skipped, reason_if_skipped: "Stryker is a JavaScript mutation tool and is not configured for this Python repository", mutant_killed: null}
  no_op_deletion: {result: pass, deletion_justified_by_rca: false, detail: "diff adds only the required synthetic fixture argument and deletes no behavior"}
  adjacent_tests: {result: pass, suites_run: ["tests/test_career_source_custody.py", "tests/test_career_source_security.py"], detail: "68 passed"}
  revert_and_reconfirm: {result: pass, bug_returned_on_revert: true, fixed_on_reapply: true, detail: "pre-fix exact focused command failed at the missing argument after 64 passes; reapplied two-line fixture addition yielded 68 passes"}
  guardrail_verdict: accepted
files_changed: [tests/test_career_source_security.py]
