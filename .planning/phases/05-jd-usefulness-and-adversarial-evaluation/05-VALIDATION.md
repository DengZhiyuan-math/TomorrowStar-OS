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

The planner must preserve this requirement coverage and replace anticipated task locations if the final plan decomposition differs.

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 05-01-01 | 01 | 1 | JD-01 | T05-01, T05-02 | Reject malformed, hidden, unsafe, or unaccepted JD input before scoring | unit | `uv run --offline --locked python scripts/run_pytest.py -q tests/test_jd_models.py -x` | ❌ W0 | ⬜ pending |
| 05-01-02 | 01 | 1 | JD-03, JD-04 | T05-03 | Revalidate reviewed-user-truth lineage and keep the Skill graph byte-identical | unit + metamorphic | `uv run --offline --locked python scripts/run_pytest.py -q tests/test_jd_security.py -x` | ❌ W0 | ⬜ pending |
| 05-02-01 | 02 | 2 | JD-02, JD-04 | T05-04 | Emit only evidence-bearing judgments and keep four gap meanings distinct | unit + golden | `uv run --offline --locked python scripts/run_pytest.py -q tests/test_jd_comparison.py -x` | ❌ W0 | ⬜ pending |
| 05-02-02 | 02 | 2 | JD-03 | T05-05 | A priority-company preference may change route/reason only, never score or capability truth | metamorphic | `uv run --offline --locked python scripts/run_pytest.py -q tests/test_jd_comparison.py -x` | ❌ W0 | ⬜ pending |
| 05-03-01 | 03 | 3 | JD-01 | T05-01 | Accept exactly three user-supplied JDs and the authoritative graph snapshot through immutable manifests | integration | `uv run --offline --locked python scripts/run_pytest.py -q tests/test_jd_evaluation.py -x` | ❌ W0 | ⬜ pending |
| 05-04-01 | 04 | 4 | EVAL-01, EVAL-02 | T05-01 through T05-06 | Run the deterministic golden, invariant, adversarial, and counterfactual matrix fail-closed | parameterized integration | `uv run --offline --locked python scripts/run_pytest.py -q tests/test_jd_evaluation.py tests/test_jd_security.py -x` | ❌ W0 | ⬜ pending |
| 05-04-02 | 04 | 4 | EVAL-03 | T05-06 | Retain three distinct attempts and block material variance rather than averaging it | integration | `uv run --offline --locked python scripts/run_pytest.py -q tests/test_jd_evaluation.py -x` | ❌ W0 | ⬜ pending |
| 05-05-01 | 05 | 5 | EVAL-04, EVAL-05 | T05-07 | Preserve blinded arm mapping, independent judgment, disagreement, and adjudication without fabrication | integration | `uv run --offline --locked python scripts/run_pytest.py -q tests/test_jd_evaluation.py -x` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_jd_models.py` — strict JD intake, exact source spans, policy/result/review models, and unaccepted-input rejection.
- [ ] `tests/test_jd_comparison.py` — requirement judgments, hard-requirement cap, routing, priority-company counterfactual, evidence explanations, and graph isolation.
- [ ] `tests/test_jd_evaluation.py` — deterministic matrix, three retained attempts, baseline packet, independent review, disagreement, and adjudication.
- [ ] `tests/test_jd_security.py` — hidden text, prompt injection, stale lineage, unsafe paths/links, and zero-publication-on-block tests.
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
