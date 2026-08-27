---
phase: 04-contribution-skill-assessment-and-aggregation-calibration
verified: 2026-08-27T20:43:02Z
status: gaps_found
score: 2/5 must-haves verified
behavior_unverified: 0
overrides_applied: 0
gaps:
  - truth: "Calibration history is content-tamper-evident before it can support an active policy."
    status: failed
    reason: "Persisted PolicyRunResult and PolicyComparison hashes are accepted as identifiers but never recomputed from retained contents."
    artifacts:
      - path: "src/career_evidence_graph/domain/models.py"
        issue: "PolicyRunResult only checks case-ID uniqueness and PolicyComparison has no content-integrity validator."
      - path: "src/career_evidence_graph/assessment.py"
        issue: "_validate_policy_history validates activation ancestry but not policy, result, or comparison payload hashes."
    missing:
      - "Recompute and compare policy_hash, result_hash, and comparison_hash on every history read."
      - "Add negative tests that mutate a retained case result, delta, or regression label while retaining the stored hash."
  - truth: "Policy calibration runs only over revalidated completed/confirmed audit custody."
    status: failed
    reason: "run_calibration_policy verifies fixture and manifest bytes but accepts declared audit/conclusion hashes directly from corpus JSON."
    artifacts:
      - path: "src/career_evidence_graph/assessment.py"
        issue: "_calibration_input_hashes stringifies corpus audit hashes; run_calibration_policy does not call _materialize_audit."
    missing:
      - "Materialize and verify the completed audit/conclusion inside calibration and derive all custody hashes from verified objects."
      - "Add tamper tests for snapshot, conclusion-lineage, and effective-conclusion hashes."
  - truth: "An insufficient-basis human review remains outside mastery after the normal assessment command is re-run."
    status: failed
    reason: "The deterministic run ID collision path overwrites the whole AssessmentStore record with a newly admitted record."
    artifacts:
      - path: "src/career_evidence_graph/assessment.py"
        issue: "run_assessment catches an existing record then calls store.replace(run_id, record)."
    missing:
      - "Make an existing run idempotently return the validated record or reject it."
      - "Require an explicit append-only reassessment operation for a new assessment and add a CLI regression test."
  - truth: "Every reviewer correction is preserved as a hash-linked immutable assessment version."
    status: failed
    reason: "review_assessment rebuilds the current version with the same ID and replaces the final tuple element, so earlier effective content is lost."
    artifacts:
      - path: "src/career_evidence_graph/assessment.py"
        issue: "The version uses latest.version_id/latest.previous_version_hash and returns (*record.versions[:-1], version)."
    missing:
      - "Append a new version with a new sequential ID and previous_version_hash equal to the current version hash."
      - "Test two edits and assert every intermediate effective assessment remains retrievable."
  - truth: "A reviewed-user-truth Skill can be promoted only with reviewed-user-truth, audit-verified support."
    status: failed
    reason: "Promotion accepts source envelopes with resolved fields regardless of authority/origin/review state, then labels the result from the baseline only."
    artifacts:
      - path: "src/career_evidence_graph/assessment.py"
        issue: "validate_anchor_promotion omits authority_label/origin_status/substantive_review_complete checks; aggregate_user_skills uses baseline.source_envelope authority for the combined result."
    missing:
      - "Partition promotion inputs by authority and require completed substantive review and audit-verified reviewed-user-truth for every user-truth promotion input."
      - "Add a mixed reviewed-user-truth/derived-counterfactual promotion test that fails closed."
---

# Phase 04: Contribution–Skill Assessment and Aggregation Calibration Verification Report

**Phase Goal:** Reviewers can turn confirmed Contribution audits into traceable Skill assessments and calibrate stable user-level mastery without collapsing distinct signals or rewarding evidence volume.
**Verified:** 2026-08-27T20:43:02Z
**Status:** gaps_found
**Re-verification:** No — initial verification

## Verification Scope Gate

ROADMAP marks this phase `mode: mvp`, but `user-story.validate` returned `false` for the phase goal. It is not in the required `As a …, I want to …, so that …` form, so a formal MVP User Flow Coverage report cannot be emitted. Under the direct verification request, this report evaluates the five ROADMAP success criteria and the eight requirement contracts; the invalid MVP metadata remains a workflow configuration discrepancy requiring correction before an MVP-formal verification can pass.

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
| --- | --- | --- | --- |
| 1 | A reviewer receives specific Skill proposals only from audited Contributions and can trace each proposal through Evidence, answers, attribution, and assessment basis. | ✓ VERIFIED | `run_assessment()` materializes a completed, confirmed `AuditSnapshot` before proposal creation; the custody proposal test passed in the focused run. |
| 2 | Reviewers can independently assign and inspect mastery, centrality, and confidence, including the contrasting cases. | ✓ VERIFIED | Separate fields/bases are modelled and the focused suite exercises the independent admission/contrast matrix. |
| 3 | Every mastery judgment identifies its anchor; unsupported higher-band claims are rejected and high-mastery/low-confidence claims stay provisional until durable human confirmation. | ✗ FAILED | Anchor and provisional admission paths exist, but ordinary rerun can restore admission and reviewer edits overwrite rather than retain immutable versions. This breaks the required durable confirmation/correction state. |
| 4 | A user can inspect one aggregated result per Skill with admitted assessments and policy; duplicate/incidental evidence cannot mechanically promote it. | ✗ FAILED | Normal duplicate-neutral aggregation is tested, but a derived-counterfactual assessment can supply promotion support while the result inherits the reviewed-user-truth baseline label. The displayed user result can therefore be elevated by non-user evidence. |
| 5 | Evaluators can compare replaceable policies while preserving variance, disagreement, calibration decisions, and regressions. | ✗ FAILED | Comparison fields exist, but history reads neither recompute result/comparison hashes nor revalidate the declared audit/conclusion custody. Retained calibration evidence is mutable in substance. |

**Score:** 2/5 truths verified (0 present, behavior-unverified)

### Required Artifacts

| Artifact | Expected | Status | Details |
| --- | --- | --- | --- |
| `src/career_evidence_graph/assessment.py` | Assessment, admission, aggregation, calibration, persistence | ⚠️ HOLLOW FOR GOAL | Substantive and CLI-wired, but contains all five failed authority/integrity paths. |
| `src/career_evidence_graph/domain/models.py` | Strict assessment, review, policy, and result contracts | ⚠️ PARTIAL | Strict parsing exists; policy run/comparison models do not prove stored hashes match their content. |
| `src/career_evidence_graph/domain/invariants.py` | Exact-Skill, anchor, and lineage invariants | ✓ VERIFIED | Wired from aggregation via `validate_user_skill`; focused aggregation behavior passes. |
| `src/career_evidence_graph/cli.py` | Run, inspect, pending, review, aggregate, compare, activate, history | ✓ WIRED | Handlers call the application services at lines 506–635; review persists returned record at lines 568–591. |
| `validation/calibration/phase-04/corpus.json` / `policies.json` | Versioned corpus and candidate policies | ⚠️ PARTIAL | 12 cases and two candidate policies are present; calibration trusts the corpus's audit/conclusion declarations rather than deriving them from a revalidated audit. |
| Phase 04 tests | Contract and regression evidence | ⚠️ INSUFFICIENT | 29 active non-CLI contract tests, plus CLI coverage, exist and pass; none covers the five failure paths described below. |

### Key Link Verification

| From | To | Via | Status | Details |
| --- | --- | --- | --- | --- |
| CLI | assessment service | `run`, `review`, `aggregate`, `compare`, `activate`, `history` handlers | ✓ WIRED | Direct calls in `cli.py` lines 506–635. |
| Assessment run | Phase 3 audit | `_materialize_audit` completed/confirmed checks | ✓ WIRED | Direct run path validates actual audit snapshot and conclusion hashes. |
| Assessment aggregate | domain invariants | `validate_user_skill` | ✓ WIRED | Aggregate result is validated before return. |
| Calibration run | audit custody | corpus audit/conclusion hash binding | ✗ NOT WIRED | Calibration path performs fixture/manifest byte checks only, then copies three audit values from corpus JSON. |
| Policy history | content hashes | run/comparison/policy recomputation | ✗ NOT WIRED | History validation checks activation hashes and cross-references only. |
| Promotion | user-truth authority | all supporting assessments checked as audited/reviewed truth | ✗ NOT WIRED | Only resolved envelope/attribution/assistance/basis are checked; output authority is copied from baseline. |

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
| --- | --- | --- | --- | --- |
| `assessment.py` direct run | `AuditSnapshot` | `AuditStore` / replayed confirmed audit | Yes | ✓ FLOWING |
| `assessment.py` policy calibration | `input_hashes` | Raw `corpus.json` audit/conclusion strings | No independent source verification | ⚠️ STATIC CUSTODY |
| `assessment.py` aggregate | `authority_label` | Baseline assessment only | No validation of all promotion inputs | ✗ HOLLOW AUTHORITY FLOW |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
| --- | --- | --- | --- |
| Full offline test suite | `uv run --offline --locked python scripts/run_pytest.py -q` | Exit 0 | ✓ PASS |
| Specific audited Skill custody | focused named proposal test | Included in focused run | ✓ PASS |
| Separate provisional admission | focused named admission test | Included in focused run | ✓ PASS |
| Duplicate/incidental no-inflation | focused named aggregation test | Included in focused run | ✓ PASS |
| Same-input comparison without activation | focused named policy test | `8 passed in 2.04s` | ✓ PASS |

Passing these tests does not overturn the failures: their assertions do not invoke tampered retained histories, calibration audit-hash tampering, rerun-after-review, multi-edit version retention, or mixed-authority promotion.

### Requirements Coverage

| Requirement | Source Plan | Status | Evidence |
| --- | --- | --- | --- |
| ASS-01 | 04-01, 04-02 | ✓ SATISFIED | Direct proposal path materializes completed/confirmed audit and focused custody test passes. |
| ASS-02 | 04-01, 04-02 | ✓ SATISFIED | Separate values and bases are modelled and test-covered. |
| ASS-03 | 04-01, 04-02 | ✓ SATISFIED | Inclusive anchor validation and higher-band rejection tests exist. |
| ASS-04 | 04-01, 04-03 | ✗ BLOCKED | CR-03 permits re-run to erase an insufficient review; CR-04 overwrites correction versions. |
| AGG-01 | 04-01, 04-04 | ✓ SATISFIED | Normal aggregate retains exact Skill, baseline, admitted IDs, and policy version. |
| AGG-02 | 04-01, 04-04 | ✓ SATISFIED | Metamorphic duplicate/incidental test passes; no direct duplication failure was found. |
| AGG-03 | 04-01, 04-04 | ✗ BLOCKED | CR-05 allows non-credible derived support to promote a result labelled reviewed user truth. |
| AGG-04 | 04-01, 04-05 | ✗ BLOCKED | CR-01 and CR-02 leave retained policy evidence and audit custody semantically mutable. |

All eight Phase 04 requirement IDs are declared by at least one PLAN; no orphaned Phase 04 requirement was found.

### Test Quality Audit

| Test File | Linked Req | Active | Skipped | Circular | Assertion Level | Verdict |
| --- | --- | ---: | ---: | --- | --- | --- |
| `test_assessment_proposal.py` | ASS-01 | 2 | 0 | No | Behavioral/custody | PASS |
| `test_mastery_anchors.py` | ASS-03 | 3 | 0 | No | Value/invariant | PASS |
| `test_assessment_admission.py` | ASS-04 | 7 | 0 | No | Behavioral | INSUFFICIENT — no rerun-after-review or two-edit version test |
| `test_skill_aggregation.py` | AGG-01/02 | 3 | 0 | No | Metamorphic | PASS for duplicate/volume cases |
| `test_anchor_promotion.py` | AGG-03 | 2 | 0 | No | Behavioral | INSUFFICIENT — fixtures do not test mixed reviewed/derived authority |
| `test_policy_calibration.py` | AGG-04 | 9 | 0 | No | Behavioral | INSUFFICIENT — no semantic hash/audit-custody tamper test |

Disabled requirement tests: **0**. Circular expected-value patterns: **0**. The shortfall is assertion coverage of the authority-changing counterexamples, not test execution.

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
| --- | --- | --- | --- | --- |
| `assessment.py` | 1073–1077 | Existing assessment record replaced on normal rerun | 🛑 Blocker | Erases review/admission conclusion. |
| `assessment.py` | 991–1006 | Latest assessment version replaced rather than appended | 🛑 Blocker | Loses immutable correction history. |
| `assessment.py` | 1127–1146, 1255–1284 | Audit custody taken from corpus strings | 🛑 Blocker | Allows false audit provenance in calibration. |
| `assessment.py` | 1423–1466 | History validates references but not run/comparison content hashes | 🛑 Blocker | Allows semantic calibration-history tampering. |
| `assessment.py` | 788–795, 905–906 | Promotion does not constrain support authority; result takes baseline label | 🛑 Blocker | Allows synthetic support to inflate a user-truth result. |

No `TBD`, `FIXME`, `XXX`, disabled-test, placeholder, or empty-render/implementation marker was found in Phase 04 implementation and test files.

### Decision Coverage

The non-blocking decision-coverage check reports **16/16** trackable D-01…D-16 decisions as represented in shipped artifacts. This syntactic coverage does not supersede the five failed semantic authority paths above.

### Prohibition Flags

The five PLAN-level prohibitions are judgment-tier and remain explicitly `unresolved` / `flagged-unverified`. They cannot be silently green-lit by code presence or the passing deterministic suite. They require human review after the blocking code gaps are closed; the overall status is already `gaps_found` on observable failures.

## Gaps Summary

The ordinary feature paths and their routine tests exist, but Phase 04 does not yet deliver stable, traceable, immutable user-level mastery. The five independent failures break the exact safeguards the phase promised: semantic integrity of policy history, audited source custody, durable insufficient-review conclusions, immutable version history, and separation of synthetic calibration evidence from reviewed user truth. No later roadmap phase explicitly owns these Phase 04 custody/authority repairs, so none are deferred.

---

_Verified: 2026-08-27T20:43:02Z_
_Verifier: the agent (gsd-verifier)_
