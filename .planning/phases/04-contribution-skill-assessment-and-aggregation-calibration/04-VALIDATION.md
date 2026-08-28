---
phase: 04
slug: contribution-skill-assessment-and-aggregation-calibration
status: remediation-measured
nyquist_compliant: true
wave_0_complete: true
created: 2026-08-27
validated: 2026-08-28
---

# Phase 04 — Measured Validation Matrix

Phase 4 has deterministic, offline remediation evidence for five previously
identified custody and authority gaps. The synthetic/counterfactual calibration
corpus remains calibration-only evidence, never reviewed user truth. These
results do not establish JD usefulness, application, interview, hiring,
employment, resume, gap-work, real-user-case, or job-market effectiveness.

## Executed Gates on the Final Remediation Revision

| Gate | Evidence | Measured outcome |
|---|---|---|
| Five-gap regression matrix | `uv run --offline --locked python scripts/run_pytest.py -q tests/test_policy_calibration.py tests/test_assessment_admission.py tests/test_assessment_cli.py tests/test_anchor_promotion.py tests/test_skill_aggregation.py` | 59 passed in 15.07s |
| Full offline suite | `uv run --offline --locked python scripts/run_pytest.py -q` | exited 0 |
| Static gates | `uv run --offline --locked ruff check .` and `uv run --offline --locked ruff format --check .` | both exited 0 |
| Active calibration custody | `git diff --exit-code -- validation/calibration/phase-04/policy-calibration/history.json` | exited 0; retained `policy-04-conservative-70` history unchanged |

No watch mode, network call, dependency installation, provider/model change, or
sealed fixture mutation was used. The focused regression group stayed below the
60-second feedback ceiling.

## Five-Gap Executable Mapping

| Blocker | Exact regression | Verified contract |
|---|---|---|
| CR-01 retained semantic history hashes | `tests/test_policy_calibration.py::test_history_semantic_tamper_fails_closed_before_activation_lookup` | Mutating retained policy, result, or comparison semantics while retaining hashes fails closed before activation lookup. |
| CR-02 completed-audit custody | `tests/test_policy_calibration.py::test_run_rejects_declared_audit_custody_tampering_before_history_publish` | Calibration materializes and validates audit/conclusion custody instead of trusting corpus declarations. |
| CR-03 rerun durability | `tests/test_assessment_cli.py::test_rerun_after_insufficient_review_is_byte_idempotent` | A normal rerun retains an insufficient-basis decision and cannot recreate admitted mastery. |
| CR-04 append-only corrections | `tests/test_assessment_admission.py::test_two_edits_retain_immutable_versions_and_reopen` | Each substantive edit appends a hash-linked immutable version and retains every earlier effective assessment. |
| CR-05 authority-safe promotion | `tests/test_anchor_promotion.py::test_mixed_authority_promotion_cannot_elevate_reviewed_user_truth` | Derived support cannot promote or relabel a reviewed-user-truth result; unpromoted user truth remains at its strongest baseline. |

The CR-05 control regressions are
`test_routine_unflagged_baseline_does_not_require_substantive_review`,
`test_reviewed_user_truth_promotion_accepts_only_retained_review_lineage`, and
`test_derived_calibration_promotion_stays_in_its_own_authority_partition` in
`tests/test_anchor_promotion.py`. They preserve D-05 baseline admission,
require immutable reviewed lineage for a reviewed-user-truth promotion, and
retain a derived-only promotion as `derived-counterfactual` respectively.

## Evidence and Authority Boundaries

- `tests/test_skill_aggregation.py::test_same_evidence_can_support_two_skills_without_same_skill_weighting`
  and `::test_same_evidence_keeps_two_reviewed_user_truth_skills_independent`
  show that one Evidence reference may support distinct Skills independently.
  Repetition within one exact Skill remains weight-neutral and is recorded only
  as a suppressed relationship.
- The aggregate service partitions admitted assessments by exact Skill and
  authority. A reviewed-user-truth promotion requires audit-verified origin,
  reviewed status, completed substantive review, and retained immutable review
  lineage for every cited assessment. A mixed-authority decision fails closed.
- The active policy remains `policy-04-conservative-70`; baseline-60 remains
  comparison-only. The accepted activation pointer and its hashes are retained
  unchanged below.

## Requirement and Decision Coverage

| Authority | Executable evidence | Checked behavior |
|---|---|---|
| ASS-04 / D-10 | `tests/test_assessment_cli.py::test_rerun_after_insufficient_review_is_byte_idempotent`, `tests/test_assessment_admission.py::test_two_edits_retain_immutable_versions_and_reopen` | Reruns retain reviewer authority and corrections are append-only. |
| AGG-01 / D-13 | `tests/test_skill_aggregation.py::test_traceable_aggregate_keeps_one_sorted_result_and_strongest_admitted_baseline` | One traceable result per exact Skill and authority partition uses an explicit strongest admitted baseline. |
| AGG-02 / D-15 | `tests/test_skill_aggregation.py::test_no_inflation_from_duplicate_assessment_contribution_or_incidental_uses`, `tests/test_skill_aggregation.py::test_same_evidence_can_support_two_skills_without_same_skill_weighting` | Duplicate same-Skill support, centrality, confidence, incidental volume, and repeated Evidence cannot inflate mastery. |
| AGG-03 / D-14 | `tests/test_anchor_promotion.py::test_mixed_authority_promotion_cannot_elevate_reviewed_user_truth` | Cross-Contribution promotion is exact-Skill and authority-partitioned; synthetic support cannot elevate reviewed user truth. |
| AGG-04 / D-16 | `tests/test_policy_calibration.py::test_history_semantic_tamper_fails_closed_before_activation_lookup`, `tests/test_policy_calibration.py::test_run_rejects_declared_audit_custody_tampering_before_history_publish` | Retained policy semantics and completed-audit custody are revalidated before active-history use. |

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

## 04-09 CR-01 Reassessment Custody Closure

Measured on implementation revision `e009b082d4e0bc5d852268457d1629113c76078f`
with regression controls at `fb74ced`.
These are local deterministic implementation gates only; they do not complete
ASS-01, AGG-01, AGG-03, Phase 04, or independent verification.

| Gate | Command | Measured outcome |
| --- | --- | --- |
| Focused reassessment controls | `uv run --offline --locked python scripts/run_pytest.py -q tests/test_assessment_admission.py tests/test_assessment_cli.py -k "reassess or fabricated or later_audit or stale_hash or authority_partition or append" -x` | 13 passed, 27 deselected in 7.83s |
| Full offline suite | `uv run --offline --locked python scripts/run_pytest.py -q` | exited 0 |
| Static gates | `uv run --offline --locked ruff check .` and `uv run --offline --locked ruff format --check .` | both exited 0; 57 files already formatted |

The focused controls prove that `assessment reassess` rejects the exact
`audit-fabricated` plus `reviewed-user-truth` relabelling attempt with exit 2
and byte-identical sidecar output; stale expected-version hashes reject before
the later corpus is read; and a real completed, confirmed later audit appends
one hash-linked version while retaining the derived authority partition and
resetting substantive review. The command now derives custody through
`_materialize_audit`; caller-provided source audit IDs are expected identities
only. Fresh independent code, security, and goal verification must inspect this
unchanged revision before any shared status promotion.
