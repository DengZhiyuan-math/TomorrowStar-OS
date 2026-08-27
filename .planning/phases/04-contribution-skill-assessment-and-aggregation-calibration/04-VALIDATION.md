---
phase: 04
slug: contribution-skill-assessment-and-aggregation-calibration
# status lifecycle: draft (seeded by plan-phase) → validated (set by validate-phase §6)
# audit-milestone §5.5 distinguishes NOT-VALIDATED (draft) from PARTIAL (validated + nyquist_compliant: false)
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-08-27
---

# Phase 04 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 9.1.1 |
| **Config file** | `pyproject.toml` |
| **Quick run command** | `uv run --offline --locked python scripts/run_pytest.py -q tests/test_assessment_models.py tests/test_assessment_admission.py tests/test_skill_aggregation.py` |
| **Full suite command** | `uv run --offline --locked python scripts/run_pytest.py -q` |
| **Estimated runtime** | Measure and record during Wave 0; max feedback latency 60 seconds |

---

## Sampling Rate

- **After every task commit:** Run the focused test file(s) named by that task plus affected Phase 2/3 regression tests.
- **After every plan wave:** Run `uv run --offline --locked python scripts/run_pytest.py -q`.
- **Before `$gsd-verify-work`:** Run the full offline suite, Ruff, deterministic calibration-corpus replay, and exact same-input current/candidate policy comparison.
- **Max feedback latency:** 60 seconds for focused task feedback.

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 04-W0-ASS01 | 04-01 | 0 | ASS-01 | T-04-01 / T-04-05 | Strict source envelope; only completed audited Contributions propose a specific Skill | integration | `uv run --offline --locked python scripts/run_pytest.py -q tests/test_assessment_proposal.py` | ❌ W0 | ⬜ pending |
| 04-W0-ASS02 | 04-01 | 0 | ASS-02 | T-04-01 | Mastery, centrality, and confidence remain independent and strictly validated | unit/golden | `uv run --offline --locked python scripts/run_pytest.py -q tests/test_assessment_models.py -k independent` | ❌ W0 | ⬜ pending |
| 04-W0-ASS03 | 04-01 | 0 | ASS-03 | T-04-02 | Exact score cannot escape its stored observable anchor | invariant/golden | `uv run --offline --locked python scripts/run_pytest.py -q tests/test_mastery_anchors.py` | ❌ W0 | ⬜ pending |
| 04-W0-ASS04 | 04-01 | 0 | ASS-04 | Low-confidence high-mastery proposals fail closed as pending until substantive review | workflow | `uv run --offline --locked python scripts/run_pytest.py -q tests/test_assessment_admission.py` | ❌ W0 | ⬜ pending |
| 04-W0-AGG01 | 04-01 | 0 | AGG-01 | One policy-bearing, traceable result exists per exact Skill | invariant/integration | `uv run --offline --locked python scripts/run_pytest.py -q tests/test_skill_aggregation.py -k traceable` | ❌ W0 | ⬜ pending |
| 04-W0-AGG02 | 04-01 | 0 | AGG-02 | Duplicate Evidence, Contributions, assessments, and incidental volume are mastery-neutral | metamorphic | `uv run --offline --locked python scripts/run_pytest.py -q tests/test_skill_aggregation.py -k no_inflation` | ❌ W0 | ⬜ pending |
| 04-W0-AGG03 | 04-01 | 0 | AGG-03 | Promotion requires explicit proof that combined behavior satisfies the next anchor | golden | `uv run --offline --locked python scripts/run_pytest.py -q tests/test_anchor_promotion.py` | ❌ W0 | ⬜ pending |
| 04-W0-AGG04 | 04-01 | 0 | AGG-04 | Policy history, reviewer disagreement, variance, and regressions remain inspectable; first activation requires null/null/absent plus selected hashes, and replacement requires exact prior identities/current pointer | integration/golden | `uv run --offline --locked python scripts/run_pytest.py -q tests/test_policy_calibration.py` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] Checked-in Phase 4 calibration corpus bound to sealed fixture and completed Phase 3 audit hashes.
- [ ] `tests/test_assessment_models.py` — strict schemas, score separation, anchor containment, and version lineage.
- [ ] `tests/test_assessment_proposal.py` — completed-audit gate, specific Skill, normalization, and complete source envelope.
- [ ] `tests/test_assessment_admission.py` — provisional, self-rated, and substantive-review workflow.
- [ ] `tests/test_mastery_anchors.py` — every anchor boundary and unsupported higher-band rejection.
- [ ] `tests/test_skill_aggregation.py` — one result per Skill, strongest-admitted baseline, duplicate neutrality, and evidence-volume neutrality.
- [ ] `tests/test_anchor_promotion.py` — allowed and denied cross-Contribution promotion.
- [ ] `tests/test_policy_calibration.py` — same-input comparison, disagreement, variance, regression, positive null/null/absent first activation, competing/non-absent bootstrap rejection, stale-pointer rejection, and exact subsequent replacement.
- [ ] CLI black-box coverage for propose, inspect pending, review, aggregate, compare, and activate behavior.

No framework installation is required.

---

## Manual-Only Verifications

All Phase 4 behaviors have automated verification. Human confirmation is exercised through deterministic review fixtures and CLI black-box tests; it does not require an unrecorded manual-only acceptance step.

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verification or Wave 0 dependencies.
- [ ] Sampling continuity: no three consecutive tasks without automated verification.
- [ ] Wave 0 covers all missing references.
- [ ] No watch-mode flags.
- [ ] Focused feedback latency is below 60 seconds.
- [ ] `nyquist_compliant: true` set in frontmatter.

**Approval:** pending
