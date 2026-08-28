---
phase: 05
slug: jd-usefulness-and-adversarial-evaluation
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-08-28
---

# Phase 05 — Validation Strategy

> Per-phase validation contract for the private, single-JD comparison and routing workflow. This document defines the harness before any real JD is available; real-fixture acceptance remains blocked until the user supplies all three test JDs at the execution checkpoint.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest `9.1.1` |
| **Config file** | `pyproject.toml` |
| **Quick run command** | `uv run --offline --locked python scripts/run_pytest.py -q tests/test_jd_models.py tests/test_jd_comparison.py tests/test_jd_security.py -x` |
| **Full suite command** | `uv run --offline --locked python scripts/run_pytest.py -q` |
| **Static commands** | `uv run --offline --locked ruff check .` and `uv run --offline --locked ruff format --check .` |
| **Estimated quick runtime** | `< 30 seconds` target |

The default acceptance path is deterministic and offline. Optional live-model runs are additional evidence only and cannot replace the offline suite or relax route, core-judgment, evidence, and lineage stability.

---

## Sampling Rate

- **After every task commit:** Run the smallest named JD test file plus any touched assessment, store, or security regression file.
- **After every plan wave:** Run the full offline pytest suite and both Ruff gates.
- **Before `$gsd-verify-work`:** Full offline suite, three-attempt evaluation matrix, fixture-custody verification, and manual acceptance checkpoints must be complete.
- **Max feedback latency:** 60 seconds for the focused automated group; split the group if it exceeds this ceiling.

---

## Per-Task Verification Map

This table matches the final six-plan, fifteen-task decomposition. Checkpoint commands are read-only state assertions and must exit 2 when their named expectation is unmet.

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 05-01-01 | 01 | 1 | JD-02, JD-03, JD-04 | T-05-01, T-05-03, T-05-04 | Carry one accepted minimal requirement through reviewed-user-truth graph verification, comparison, routing, and redacted JSON without mutating mastery | tracer integration | `uv run --offline --locked python scripts/run_pytest.py -q tests/test_jd_comparison.py -x` | ❌ W0 | ⬜ pending |
| 05-01-02 | 01 | 1 | JD-02, JD-04 | T-05-02 | Enforce exact source/proposal binding, ordered Skill combinations, evidence-bearing judgments, empty-input rejection, and canonical order | unit | `uv run --offline --locked python scripts/run_pytest.py -q tests/test_jd_models.py -x` | ❌ W0 | ⬜ pending |
| 05-01-03 | 01 | 1 | JD-02, JD-03, JD-04 | T-05-03, T-05-05 | Apply integer score/core cap/route rules, require every Skill-combination member for the exception, and keep the complete graph byte-identical | unit + metamorphic | `uv run --offline --locked python scripts/run_pytest.py -q tests/test_jd_comparison.py tests/test_skill_aggregation.py tests/test_domain_invariants.py -x` | ❌ W0 | ⬜ pending |
| 05-02-01 | 02 | 2 | JD-04 | T-05-06, T-05-07, T-05-11 | Reject unsafe, oversized, injected, mismatched, or stale input before any score, route, or write | security + unit | `uv run --offline --locked python scripts/run_pytest.py -q tests/test_jd_security.py tests/test_security_boundaries.py -x` | ❌ W0 | ⬜ pending |
| 05-02-02 | 02 | 2 | JD-04 | T-05-06, T-05-09, T-05-10 | Keep prepare/accept separate and make every `jd inspect --expect` state assertion read-only and machine-failing | CLI integration | `uv run --offline --locked python scripts/run_pytest.py -q tests/test_jd_security.py tests/test_assessment_cli.py -x` | ❌ W0 | ⬜ pending |
| 05-02-03 | 02 | 2 | JD-04 | T-05-08, T-05-09, T-05-10 | Preregister route-only priority input and the blind baseline/evaluation charter without capability inflation or private fixture content | integration + custody | `uv run --offline --locked python scripts/run_pytest.py -q tests/test_jd_security.py tests/test_run_store.py tests/test_policy_calibration.py -x` | ❌ W0 | ⬜ pending |
| 05-03-01 | 03 | 3 | JD-01 | T-05-12, T-05-13, T-05-15 | Accept only three user-selected raw files plus content-bound proposals produced after delivery; publish no score or route | checkpoint + CLI assertion | `uv run --offline --locked python scripts/run_career_evidence.py jd inspect --workspace .career-evidence/phase-05 --expect prepared-exact-three` | ❌ W0 | ⬜ pending |
| 05-03-02 | 03 | 3 | JD-01 | T-05-13, T-05-14, T-05-16 | Bind explicit user acceptance to exact corpus and complete reviewed-user-truth graph manifests | checkpoint + CLI assertion | `uv run --offline --locked python scripts/run_career_evidence.py jd inspect --workspace .career-evidence/phase-05 --expect accepted-corpus-and-graph` | ❌ W0 | ⬜ pending |
| 05-04-01 | 04 | 4 | EVAL-01, EVAL-03 | T-05-17 | Calibrate and activate one transparent forward-only policy only after accepted fixtures, with deterministic boundary expectations | parameterized integration | `uv run --offline --locked python scripts/run_pytest.py -q tests/test_jd_evaluation.py tests/test_policy_calibration.py -x` | ❌ W0 | ⬜ pending |
| 05-04-02 | 04 | 4 | EVAL-02, EVAL-03 | T-05-18, T-05-19, T-05-20, T-05-21 | Close the exact nonempty adversarial inventory, require three distinct attempt identities, and block material variance without averaging or deduplication | security + repeated integration | `uv run --offline --locked python scripts/run_pytest.py -q tests/test_jd_evaluation.py tests/test_jd_security.py tests/test_run_store.py -x` | ❌ W0 | ⬜ pending |
| 05-04-03 | 04 | 4 | EVAL-01, EVAL-02, EVAL-03 | T-05-18, T-05-19, T-05-20, T-05-21 | Freeze the exact-output one-shot evaluator, dedicated review actions, and read-only inspect contracts without executing the accepted real evaluation | CLI contract + security | `uv run --offline --locked python scripts/run_pytest.py -q tests/test_jd_evaluation.py tests/test_jd_security.py tests/test_run_store.py -x` | ❌ W0 | ⬜ pending |
| 05-05-01 | 05 | 5 | EVAL-01, EVAL-02, EVAL-03 | T-05-22, T-05-23, T-05-24, T-05-25, T-05-26 | Reopen accepted authority, then execute exactly one atomic three-attempt evaluation producing only the eight declared artifacts | one-shot CLI integration | `uv run --offline --locked python scripts/run_career_evidence.py jd evaluate --workspace .career-evidence/phase-05 --charter validation/jd/evaluation-charter.json --policies validation/jd/policies.json --attempts 3` | ❌ W0 | ⬜ pending |
| 05-05-02 | 05 | 5 | EVAL-01, EVAL-02, EVAL-03 | T-05-23, T-05-24, T-05-25, T-05-26 | Reopen the exact frozen evaluation hash and verify all inventories, attempts, invariants, blockers, and declared outputs without rerunning or repairing | read-only CLI assertion | `uv run --offline --locked python scripts/run_career_evidence.py jd inspect --workspace .career-evidence/phase-05 --expect existing-evaluation --evaluation-hash <evaluation-hash-emitted-by-05-05-01>` | ❌ W0 | ⬜ pending |
| 05-06-01 | 06 | 6 | EVAL-04, EVAL-05 | T-05-27, T-05-28, T-05-30, T-05-31, T-05-32, T-05-33 | Freeze an opaque packet and preserve one genuinely independent blind judgment against Plan 05-05's exact frozen evaluation | checkpoint + CLI assertion | `uv run --offline --locked python scripts/run_career_evidence.py jd inspect --workspace .career-evidence/phase-05 --expect sealed-blind-review --evaluation-hash <05-05-evaluation-hash>` | ❌ W0 | ⬜ pending |
| 05-06-02 | 06 | 6 | EVAL-04, EVAL-05 | T-05-28, T-05-29, T-05-31, T-05-33 | Record adjudication separately, retain every disagreement and original byte, require zero critical fabrication for a pass, and never rerun evaluation | checkpoint + CLI assertion | `uv run --offline --locked python scripts/run_career_evidence.py jd inspect --workspace .career-evidence/phase-05 --expect finalized --evaluation-hash <05-05-evaluation-hash>` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_jd_models.py` — strict JD intake, exact source spans, policy/result/review models, and unaccepted-input rejection.
- [ ] `tests/test_jd_comparison.py` — requirement judgments, hard-requirement cap, routing, priority-company counterfactual, evidence explanations, and graph isolation.
- [ ] `tests/test_jd_evaluation.py` — deterministic matrix, three retained attempts, baseline packet, independent review, disagreement, and adjudication.
- [ ] `tests/test_jd_security.py` — hidden text, prompt injection, stale lineage, unsafe paths/links, and zero-publication-on-block tests.
- [ ] `validation/jd/proposal.schema.json` — provider-independent, source-hash/span-bound proposal contract containing no JD body.
- [ ] `jd inspect --expect` assertions — read-only failing checks for prepared-exact-three, accepted-corpus-and-graph, existing-evaluation, sealed-blind-review, and finalized states.
- [ ] Empty real-fixture intake location and manifest contract — no sourced, copied, selected, or synthesized JD body may be added before the user checkpoint.
- [ ] Explicit execution checkpoint — the user supplies and accepts the three real JDs; execution also resolves and verifies the authoritative reviewed-user-truth graph snapshot.
- [ ] No framework or dependency installation is needed.

Wave 0 may use minimal schema objects and single-fault unit inputs to exercise code contracts. Those are not substitutes for, and must not be presented as, the three real evaluation JDs.

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Supply and accept three real test JDs | JD-01 | The user explicitly retained fixture selection authority | At the execution checkpoint, place the three user-provided JD files in the declared intake location, review their hashes and source-span manifests, and approve acceptance before calibration or evaluation continues. |
| Confirm the authoritative personal Skill graph snapshot | JD-02, JD-03 | Repository calibration artifacts are synthetic/counterfactual rather than reviewed user truth | Resolve the runtime workspace, verify every admitted assessment/version and reviewed-user-truth lineage, present the manifest hash, and obtain explicit confirmation before scoring. |
| One-time independent blinded comparison and adjudication | EVAL-04, EVAL-05 | Decision usefulness requires a human judgment that cannot be automated without circularity | Freeze the opaque A/B packet and rubric, obtain one independent review, preserve disagreement verbatim, then record separate adjudication without overwriting either arm or judgment. |

These checkpoints are development acceptance gates, not recurring product workflow.

---

## Validation Sign-Off

- [ ] All tasks have an automated command or an explicit Wave 0 dependency.
- [ ] Sampling continuity: no three consecutive tasks lack automated verification.
- [ ] Wave 0 covers every missing test reference.
- [ ] No watch-mode flags or network dependency are used for deterministic acceptance.
- [ ] Focused feedback latency remains below 60 seconds.
- [ ] All three JD files came from the user at the execution checkpoint; none was sourced or synthesized by the system.
- [ ] The full graph and mastery snapshots are byte-identical before and after every comparison.
- [ ] Three distinct attempts are retained; any material instability blocks acceptance.
- [ ] Independent review, disagreement, adjudication, and zero-fabrication checks are preserved.
- [ ] `nyquist_compliant: true` is set only after the measured matrix is complete.

**Approval:** pending user fixtures and measured execution evidence
