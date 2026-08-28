---
status: resolved
trigger: "深入分析并修复这个问题"
created: 2026-08-28T17:45:21Z
updated: 2026-08-28T18:50:11Z
---

## Current Focus

hypothesis: Confirmed — the missing resolved-Contribution guard caused the derivative violation, 987cc7c fixed it, and this session corrected the stale planning records that still called it unfixed.
test: Human confirmation that the original source-selecting CLI/test workflow now reports only assessment.contribution_missing and that the planning records accurately show the issue resolved.
expecting: The user confirms the original issue is resolved in their workflow; otherwise return to investigation with the reported discrepancy.
next_action: Archive this resolved session, commit only its scoped planning/debug records, and update the local debug knowledge base.
bug_class: bohrbug
reasoning_checkpoint:
  hypothesis: "validate_claim_attribution emitted assessment.basis_claim_mismatch after contribution lookup had already failed because it lacked a guard on resolved Contribution lineage; 987cc7c added that guard, but the deferred ledger was not reconciled."
  confirming_evidence:
    - "The exact test fails at f210fa6 with basis_claim_mismatch plus contribution_missing and passes at 987cc7c/current HEAD."
    - "The Phase 02 plan explicitly specifies contribution_missing as the sole code, and 33 current boundary-neighbor tests pass."
  falsification_test: "The hypothesis would be false if f210fa6 did not reproduce the cascade, if removing the guard did not restore it, or if valid-reference basis/attribution tests were suppressed by the guard."
  fix_rationale: "The existing guard stops only checks that require the absent Contribution; the remaining change reconciles stale planning metadata rather than duplicating an already-landed code fix."
  blind_spots: "The ledger's third attribution_not_delivery code is not recoverable from committed history; the full current suite and lint gate have not yet been rerun in this session."
  candidate_causes:
    - "code: validate_claim_attribution lacked a resolved-Contribution guard before comparing basis-claim lineage."
    - "data: the deliberate dangling assessment reference plus a basis claim exposed the invalid comparison, but this malformed fixture is the specified validation input rather than a defect to repair."
    - "environment/process: the deferred ledger was archived without rerunning the now-fixed target after 987cc7c landed."
  and_gate: "no for the historical cascade: the missing guard fully accounts for the derivative code under the specified malformed-input trigger; the stale ledger is a separate bookkeeping defect, not a simultaneous condition required for the cascade."
tdd_checkpoint: null

## Symptoms

expected: Removing an assessment's referenced Contribution should yield the single primary violation assessment.contribution_missing.
actual: The malformed fixture also yields assessment.basis_claim_mismatch and assessment.attribution_not_delivery.
errors: tests/test_cli_tracer.py::test_domain_fixture_rejects_missing_assessment_contribution fails because the returned violation list contains three codes instead of one.
reproduction: Run the named pytest test against the current checkout, then inspect collect_invariant_violations for the missing-Contribution assessment.
started: Recorded during Phase 2 on 2026-07-30 and acknowledged, but not fixed, at the v1.0 partial closeout on 2026-08-28.

## Eliminated

- hypothesis: The sole-code test oracle is wrong and all reported violations are independently valid.
  evidence: Plan 02-01 explicitly specifies contribution_missing as the sole violation, and basis-claim lineage cannot be compared to a Contribution that does not exist.
  timestamp: 2026-08-28T17:51:41Z

- hypothesis: The cascading-violation source defect is still present in current HEAD.
  evidence: Current source contains the resolved-Contribution guard from 987cc7c; the exact test and direct neighbors pass against checkout source.
  timestamp: 2026-08-28T17:51:41Z

- hypothesis: This session's planning reconciliation introduced the sealed-fixture CLI failure.
  evidence: An isolated unmodified HEAD archive fails the same representative test with the identical missing archived-summary input.
  timestamp: 2026-08-28T17:54:30Z

## Evidence

- timestamp: 2026-08-28T17:45:21Z
  checked: Archived Phase 2 deferred item and current source/test references.
  found: The test expects only contribution_missing while current invariant branches also emit basis_claim_mismatch and attribution_not_delivery.
  implication: The defect is reproducible and bounded to the validation error contract; root-cause analysis must decide whether dependent checks should be gated or the oracle updated.

- timestamp: 2026-08-28T17:47:25Z
  checked: Phase-0 semantic recall and local debug knowledge base.
  found: No MemPalace recall tool is available and .planning/debug/knowledge-base.md does not exist; the project memory contains no matching prior resolution for these violation codes.
  implication: There is no known-pattern candidate to privilege; proceed from the current source and deterministic test evidence.

- timestamp: 2026-08-28T17:48:16Z
  checked: Exact reproduction command uv run --locked pytest tests/test_cli_tracer.py::test_domain_fixture_rejects_missing_assessment_contribution -q.
  found: The first sandboxed attempt could not access the uv cache; the authorized retry executed the test and passed (1 passed in 0.21s).
  implication: The historical symptom is not presently reproduced in this checkout; inspect source, oracle, and revision state before accepting or rejecting the original hypothesis.

- timestamp: 2026-08-28T17:49:26Z
  checked: Current implementation and scoped Git history for the focused test and validate_claim_attribution.
  found: Current source short-circuits claim-attribution checks when assessment.contribution_id is unresolved. Commit 987cc7c added that five-line guard and changed the domain invariant regression expectation to the sole contribution_missing code. The deferred item was committed at 16:58:54, while 987cc7c followed at 17:02:38; the item was merely marked acknowledged during the 2026-08-28 milestone archive.
  implication: The historical failure report preceded its source fix by four minutes. A historical differential run can establish causality; the still-open status is a stale-ledger defect, not an unfixed current validator defect.

- timestamp: 2026-08-28T17:49:26Z
  checked: SBFL eligibility for the current failure.
  found: SBFL skipped because there is no current failing test and the installed project dependencies do not provide an existing per-test coverage spectrum for the historical revision.
  implication: Route the deterministic Bohrbug through historical differential reproduction and commit bisection evidence instead of manufacturing a coverage framework.

- timestamp: 2026-08-28T17:50:39Z
  checked: Historical differential reproduction at f210fa6 (pre-fix), 987cc7c (fix), and current HEAD using the exact named pytest test.
  found: f210fa6 deterministically fails with assessment.basis_claim_mismatch plus assessment.contribution_missing; 987cc7c and current HEAD both pass. The archived ledger's third attribution_not_delivery code is not present in the committed f210fa6 reproduction and does not exist in reachable source history.
  implication: The five-line guard in 987cc7c is causal for the reproducible cascade. The third archived code appears to describe transient/uncommitted state and should not be repeated as current behavior.

- timestamp: 2026-08-28T17:51:41Z
  checked: Phase 02 specified oracle and current boundary-neighbor regression set.
  found: Plan 02-01 acceptance explicitly requires exactly assessment.contribution_missing as the sole code. The focused CLI test, all domain invariant tests, and the sealed one-fault inventory check passed (33 tests total), including independent valid-reference attribution and evidence-basis violations.
  implication: The oracle is specified rather than inferred, and the existing guard is narrow: it suppresses only lineage-dependent noise without hiding independently evaluable faults.

- timestamp: 2026-08-28T17:53:58Z
  checked: Expanded adjacent test run and Ruff boundary check.
  found: Ruff passed. The target plus domain and fixture suites produced 48 passes and one failure in test_fixture_validate_suite_cli_emits_the_stable_complete_json_report because canonical known-good review inputs are invalid.
  implication: The target and direct neighbors remain green, but the broader fixture CLI failure must be classified against clean HEAD before the guardrail can accept it as unrelated baseline debt.

- timestamp: 2026-08-28T17:54:30Z
  checked: Isolated clean-HEAD reproduction of the sealed-fixture CLI failure.
  found: The unmodified HEAD archive fails the same test with the same canonical known-good review inputs are invalid error.
  implication: This is a pre-existing baseline failure, not a regression from the two Markdown changes; retain it as an explicit verification limitation and do not broaden the cascading-violation fix.

- timestamp: 2026-08-28T17:54:59Z
  checked: Repository-wide command uv run --locked pytest -q.
  found: Collection stopped with 15 import errors because Python resolved career_evidence_graph from .venv/site-packages, which lacks current assessment, audit, and JD modules.
  implication: This command is not the repository's source-selecting verification entry point and is invalid as a current-checkout regression signal; rerun through scripts/run_pytest.py as specified by project plans and tracer tests.

- timestamp: 2026-08-28T17:56:22Z
  checked: Authoritative repository-wide offline suite via uv run --locked python scripts/run_pytest.py -q.
  found: 231 tests passed, 151 failed, and 1 was deselected. The failures consistently trace to the already-archived .planning/phases/.../02-04-SUMMARY.md path still referenced by sealed fixture inputs; an isolated clean-HEAD representative test fails identically.
  implication: The full-suite baseline is not green after the milestone archive, but these are not newly introduced by the two planning-document edits or by 987cc7c. Verify the cascading-violation contract with the direct checkout-source suite and report the broader baseline limitation separately.

- timestamp: 2026-08-28T17:56:57Z
  checked: Authoritative focused checkout-source suite, Ruff, and scoped diff hygiene.
  found: The exact target, all domain invariant tests, and the sealed one-fault inventory test pass (33/33); Ruff passes; git diff --check passes; only the two intended tracked planning files are modified, while pre-existing untracked .gsd, milestone lock, debug, and research cache paths remain untouched.
  implication: All applicable scoped guardrail signals accept the existing source fix and planning reconciliation; human verification is the remaining resolution gate.

- timestamp: 2026-08-28T18:50:11Z
  checked: Archive-time semantic knowledge-base indexing configuration.
  found: `config.mempalace.enabled` is false, so no cross-session semantic index write was attempted; `.planning/debug/knowledge-base.md` was created as the durable fallback.
  implication: Future sessions can use keyword fallback immediately, and semantic indexing remains disabled by the project's existing configuration.

## Resolution

root_cause: "The historical validator called claim-attribution comparison after an assessment's Contribution reference failed to resolve, so a valid basis claim was incorrectly compared against a dangling Contribution ID and produced a derivative mismatch. Commit 987cc7c fixed the control flow, but the Phase 2 deferred ledger—created four minutes earlier—was later archived as merely acknowledged without revalidation, leaving current project state falsely marked unfixed."
fix: "Existing code fix 987cc7c guards lineage-dependent claim-attribution checks on a resolved Contribution. Reconciled the stale Phase 2 deferred item and STATE row with the causal commit and current revalidation evidence; no duplicate source change was made."
verification:
  target_test:
    result: pass
    evidence: "Exact named test passes at 987cc7c and current HEAD; it fails at pre-fix f210fa6."
  mutation_check:
    result: pass
    reason: "No Python mutation framework is configured; the isolated f210fa6 archive is the exact guard-removal mutant."
    mutant_killed: true
  no_op_deletion:
    result: pass
    deletion_justified_by_rca: true
    evidence: "The early continue suppresses only claim-lineage comparisons that cannot be evaluated without a Contribution; independent valid-reference violations remain covered and green."
  adjacent_tests:
    result: pass
    suites_run:
      - "tests/test_domain_invariants.py"
      - "tests/test_fixture_mutations.py::test_every_case_is_one_declared_failure_and_preserves_all_accepted_bytes"
      - "tests/test_cli_tracer.py::test_domain_fixture_rejects_missing_assessment_contribution"
    evidence: "33/33 scoped checkout-source tests and Ruff pass. Full-suite baseline remains independently red after milestone archival (231 passed, 151 pre-existing path failures, 1 deselected)."
  revert_and_reconfirm:
    result: pass
    bug_returned_on_revert: true
    fixed_on_reapply: true
    evidence: "The same test fails from f210fa6 and passes from 987cc7c/current HEAD in isolated archives."
  guardrail_verdict: accepted
  human_verify:
    result: pass
    evidence: "User confirmed the fix on 2026-08-28."
oracle_type: specified
files_changed:
  - .planning/STATE.md
  - .planning/milestones/v1.0-phases/02-domain-contracts-stoa-fixture-and-deterministic-invariants/deferred-items.md

## Prevention

### Blameless causal branches

- **Code:** Claim-attribution validation assumed an assessment's Contribution was resolvable after the primary reference validator had already reported it missing. The validators accumulated results independently, so the lineage-dependent comparison still ran and emitted derivative noise. The resolved-Contribution guard makes that dependency explicit.
- **Data:** The deliberately malformed fixture combined a dangling Contribution reference with an otherwise valid basis claim. That is a required boundary case, not bad production data; it exposed that the validator did not distinguish primary failures from checks whose prerequisites were absent.
- **Process:** The regression was recorded before `987cc7c`, then the fixing commit landed four minutes later. The later milestone closeout preserved the earlier ledger status without rerunning the named test against final HEAD, so the code was fixed while the planning record stayed stale.
- **AND-gate:** The historical cascade required only the missing code guard under the specified malformed fixture. The stale ledger was a separate bookkeeping condition that made the resolved defect appear current; it did not contribute to runtime violation emission.

### Why this was not caught

The named regression test caught the source defect and the subsequent commit fixed it, but the milestone closeout verification step did not cross-check every acknowledged deferred test against final HEAD. That process gap allowed the obsolete “not fixed” status to survive.

### Recurrence guard

`tests/test_cli_tracer.py::test_domain_fixture_rejects_missing_assessment_contribution` is the specified regression guard: it requires the malformed fixture to emit exactly `assessment.contribution_missing`. The test fails at pre-fix `f210fa6` and passes at `987cc7c` and current HEAD; the resolved debug entry and knowledge-base record preserve the ledger-reconciliation pattern for future Phase-0 recall.
