---
phase: 04
slug: contribution-skill-assessment-and-aggregation-calibration
status: validated
nyquist_compliant: true
wave_0_complete: true
created: 2026-08-27
validated: 2026-08-27
---

# Phase 04 — Measured Validation Matrix

Phase 4 validates an offline, contribution-grounded assessment seam. The
synthetic/counterfactual calibration corpus is not reviewed user truth and does
not establish JD, employment, resume, or gap-work effectiveness.

## Executed Gates

| Gate | Evidence | Result |
|---|---|---|
| Focused activation/replacement | `tests/test_policy_calibration.py -k "first_activation or competing_bootstrap or stale_pointer or subsequent_replacement"` | 3 passed in 0.29s |
| Calibration + CLI regression | `tests/test_policy_calibration.py tests/test_assessment_cli.py` | 15 passed in 14.64s |
| Full offline suite | `uv run --offline --locked python scripts/run_pytest.py -q` | exited 0 |
| Static gates | `ruff check .` and `ruff format --check .` | passed |
| Sealed input protection | `git diff --exit-code -- validation/fixtures/stoa/v1/known-good.json validation/fixtures/stoa/v1/source-manifest.json` | passed |
| Same-input comparison and selected activation | `assessment compare`, `assessment activate`, `assessment history` against `validation/calibration/phase-04` | passed; conservative-70 is the sole active pointer |

Focused feedback stayed below the 60-second ceiling (0.29s and 14.64s). No
watch mode, network call, dependency change, provider/model change, or sealed
fixture mutation was used.

## Requirement and Decision Coverage

| Authority | Executable evidence | Checked behavior |
|---|---|---|
| ASS-01 / D-01 | `tests/test_assessment_proposal.py`, `tests/test_assessment_cli.py -k tracer` | Specific Skills originate only from the completed audited Contribution and retain source custody. |
| ASS-02 / D-02 / D-07 | `tests/test_assessment_models.py -k independent`, `tests/test_assessment_proposal.py` | Mastery, centrality, and confidence are separate strict judgments with separate bases. |
| ASS-03 / D-03 / D-05 / D-06 | `tests/test_mastery_anchors.py`, `tests/test_assessment_proposal.py` | A specific normalization decision and observable anchor fit are required before an exact score. |
| ASS-04 / D-04 / D-08 / D-09 / D-10 / D-11 / D-12 | `tests/test_assessment_admission.py`, `tests/test_assessment_cli.py -k review` | Low-confidence, self-assessed, disputed, unresolved, corrected, and reassessed records remain visible and require complete substantive review before admission. |
| AGG-01 / D-13 | `tests/test_skill_aggregation.py -k traceable`, `tests/test_assessment_cli.py -k aggregate` | One traceable result per exact Skill uses an explicit policy-bearing strongest admitted baseline. |
| AGG-02 / D-15 | `tests/test_skill_aggregation.py -k no_inflation`, `tests/test_policy_calibration.py -k regression` | Duplicate relationships, reused Evidence, centrality, confidence, and incidental volume cannot inflate mastery. |
| AGG-03 / D-14 | `tests/test_anchor_promotion.py` | Cross-Contribution promotion requires distinct same-Skill Contributions, contexts, and immediate-next-anchor behavior proof. |
| AGG-04 / D-16 | `tests/test_policy_calibration.py`, `tests/test_assessment_cli.py -k calibration_cli` | Byte-identical candidate inputs, exact deltas, disagreement, zero variance, regressions, human activation, pointer history, bootstrap rejection, stale replacement, and redacted offline CLI history. |

## Edge and Threat Coverage

| Item | Executable evidence | Result |
|---|---|---|
| AGG-04 threshold equality | `tests/test_policy_calibration.py -k threshold` | Exact integer equality is retained; the 60-to-69 confidence boundary flip is explicit. |
| AGG-04 numeric precision | `tests/test_policy_calibration.py -k compare` | Integer values are compared exactly; no average, tolerance, coercion, truncation, or rounding path exists. |
| T-04-21 corpus tampering | `tests/test_policy_calibration.py -k corpus` | Fixture and manifest hashes plus labeled derived/synthetic cases are revalidated. |
| T-04-22 comparison tampering | `tests/test_policy_calibration.py -k compare` | Same-input hashes, retained per-case deltas, disagreements, variance, and regressions are verified. |
| T-04-23 activation elevation | `tests/test_policy_calibration.py -k "first_activation or competing_bootstrap or stale_pointer or subsequent_replacement or activation_requires"` | Only `zhdeng`, exact selected hashes, null/null/absent bootstrap, and stale-safe replacement are accepted. |
| T-04-24 history tampering/disclosure | `tests/test_policy_calibration.py -k symlink_aliases`, `tests/test_assessment_cli.py -k calibration_cli` | Symlink and malformed history payloads fail closed; history emits IDs, hashes, codes, and the recorded human decision without raw answers. |
| T-04-25 reviewer provenance | `tests/test_policy_calibration.py -k activation_requires` | `zhdeng` is asserted trusted-local provenance only; no authentication claim is made. |

## Activation Record

The owner-approved selection is `policy-04-conservative-70`. Its immutable
record is at `validation/calibration/phase-04/policy-calibration/history.json`:

- Policy hash: `sha256:603cfbadcf8bb6ab2163dd0206e844a4b8b3956fe15974da85c028fe75fb6f6b`
- Result hash: `sha256:0992b26cfa0ab76eba631851bf4fc22b1a8213cc30c18492d08d45a7832e0719`
- Comparison hash: `sha256:ac2630db1076b3a824e28e1e29c9c1cc64cc972a500d2deae5c492ab35d11ea7`
- Activation hash: `sha256:bcd7c7446c7d7438986ce930debf7cf2e3c5af6e7d3539d8b5175d568b8b856f`

Reviewer `zhdeng` chose the conservative initial calibration because boundary
cases with insufficient evidence confidence remain pending human confirmation
rather than being counted immediately. Limitation: this policy must be
re-evaluated after additional real audited samples accumulate. The non-selected
baseline-60 run remains comparison-only evidence and is never active authority.

## Flagged Assumptions and Prohibition

- `AGG-04-threshold-boundary` and `AGG-04-numeric-precision` are deliberately
  visible in the comparison output and must be independently reviewed as the
  real audited corpus grows.
- The bespoke prohibition remains descriptor-less and flagged-unverified:
  passing deterministic replay does not prove JD or employment effectiveness,
  and it must not hide regressions, average reviewer disagreement away, or
  silently overwrite a prior result.
