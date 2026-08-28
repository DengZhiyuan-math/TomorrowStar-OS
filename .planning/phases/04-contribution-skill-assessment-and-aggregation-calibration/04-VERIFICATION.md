---
phase: 04-contribution-skill-assessment-and-aggregation-calibration
verified: 2026-08-28T12:46:00Z
status: gaps_found
score: 7/8 must-haves verified
behavior_unverified: 0
overrides_applied: 0
re_verification:
  previous_status: gaps_found
  previous_score: 3/5
  gaps_closed:
    - "Reassessment no longer accepts a fabricated or detached source-audit as an authority to mutate the caller workspace."
    - "Rejected missing, corrupt, incomplete, unconfirmed, custody-invalid, stale, and sampled forged reassessments preserve both persistence roots."
  gaps_remaining:
    - "The committed whole-proposal regression matrix does not cover every structural group required by 04-10."
  regressions: []
gaps:
  - truth: "The committed reassessment regression matrix proves that every valid caller mismatch across full lineage, source-envelope custody, context/duration, attribution, assistance, anchor bases, and all judgment bases is rejected with zero writes."
    status: failed
    reason: "Plan 04-10 explicitly requires a valid Pydantic mutation across every named structural group. The committed CLI matrix omits duration, attribution_status, assistance_status, lineage.source_kind, most source-envelope custody fields/ID collections, next_anchor_not_established, and centrality/confidence judgment bases."
    artifacts:
      - path: tests/test_assessment_cli.py
        issue: "The parameterization at lines 383-403 samples 17 leaves but leaves multiple required structural groups unexercised."
      - path: tests/test_assessment_admission.py
        issue: "The service matrix at lines 480-541 covers invalid audit states, not the omitted valid proposal mutations."
    missing:
      - "Add one Pydantic-valid mutation for each omitted structural group through the service or CLI, asserting exit/rejection plus byte-identical assessment sidecar and complete audits-tree snapshot."
      - "Keep the committed matrix as the durable regression proof; an ad-hoc verifier probe is not a substitute for repository coverage."
---

# Phase 4: Contribution-Skill Assessment and Aggregation Calibration Verification Report

**Phase Goal:** Reviewers can turn confirmed Contribution audits into traceable Skill assessments and calibrate stable user-level mastery without collapsing distinct signals or rewarding evidence volume.
**Verified:** 2026-08-28T12:46:00Z
**Status:** gaps_found
**Re-verification:** Yes — after 04-10 reassessment custody remediation.

## User Flow Coverage

Phase 4 is marked `mode: mvp`, but `user-story.validate` returns `valid: false`: its roadmap goal is not in the required `As a [role], I want to [capability], so that [outcome].` form. A canonical MVP user-flow UAT therefore cannot be generated. This report is the requested technical goal-backward verification; the metadata discrepancy must be corrected before claiming MVP UAT completion.

| Step | Expected | Evidence | Status |
| --- | --- | --- | --- |
| Metadata guard | MVP phase goal is a valid user story. | The centralized validator rejected the current Phase 4 goal. | ⚠️ INVALID MVP METADATA |
| Assessment outcome | Confirmed audit data yields traceable specific-Skill results without false authority promotion. | Technical paths below are exercised; no user-facing UI exists. | ✓ TECHNICAL PATH VERIFIED |

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
| --- | --- | --- | --- |
| 1 | Specific-Skill assessments originate in confirmed audited Contributions and retain Evidence, answers, attribution, and assessment-basis lineage. | ✓ VERIFIED | `assessment.py:480-540` materializes/validates the audit; proposal and source-envelope tests are active, and reassessment derives the canonical proposal from the read snapshot at `1141-1164`. |
| 2 | Mastery, centrality, and confidence remain independently assignable and inspectable. | ✓ VERIFIED | Separate Pydantic fields/bases in `domain/models.py:544-568`; active independence and admission-boundary tests were collected and the full suite passed. |
| 3 | Mastery names an observable anchor; unsupported higher bands fail and high-mastery/low-confidence remains provisional. | ✓ VERIFIED | `MasteryAnchorFit` validates literal anchor identity/range/bases at `277-305`; anchor and provisional-admission tests are active and passed. |
| 4 | One traceable aggregate per exact Skill does not mechanically reward duplicate Evidence, duplicate Contributions, or incidental use. | ✓ VERIFIED | Aggregate/invariant wiring plus `test_skill_aggregation.py` and `test_anchor_promotion.py` active behavioral tests passed in the full offline suite. |
| 5 | Calibration compares replaceable policies while retaining variance, disagreement, decisions, regressions, and immutable history. | ✓ VERIFIED | Active policy-calibration custody/history regressions passed; retained policy history is revalidated before use rather than treated as static output. |
| 6 | 04-10 reassessment consumes only a pre-existing completed/confirmed audit; every rejected audit/proposal request is zero-write, valid reassessment appends one version, and stale rejection is first. | ✓ VERIFIED | `reassess_from_new_evidence()` checks stale hash before corpus read (`1131-1139`), invokes `_materialize_audit(... allow_replay=False)` (`1141-1147`), compares canonical proposal before version creation (`1161-1172`), and the 26 focused reassessment tests passed. |
| 7 | The committed whole-proposal regression matrix covers every required structural group, so a future sampled comparison cannot silently return. | ✗ FAILED | WR-01 is confirmed: the checked-in matrix omits valid mutations for several groups expressly required by 04-10; see Gaps Summary. Current `proposal != canonical` is sound, but the required durable test evidence is incomplete. |
| 8 | 04-10 neither expands scope nor falsely promotes Phase 4/requirements. | ✓ VERIFIED | The only post-summary commits are fresh `04-REVIEW.md` and `04-SECURITY.md` audits (`80514ef`, `cf0c37c`); no source, shared tracking, policy history, or promotion change followed `edae898`. |

**Score:** 7/8 must-haves verified (0 present, behavior-unverified).

### Required Artifacts

| Artifact | Expected | Status | Details |
| --- | --- | --- | --- |
| `src/career_evidence_graph/assessment.py` | Audit-derived assessment, admission, aggregation, calibration, and no-replay reassessment. | ✓ VERIFIED | 1,742 substantive lines; no debt markers/stubs. Reassessment's no-replay and equality branches execute before `_make_version`. |
| `src/career_evidence_graph/domain/models.py` | Strict separate assessment, lineage, anchor, envelope, version, and policy contracts. | ✓ VERIFIED | 746 substantive lines; frozen strict models retain distinct signals and source custody. |
| `src/career_evidence_graph/domain/invariants.py` | Exact-Skill/no-inflation/promotion invariants. | ✓ VERIFIED | 482 substantive lines and active aggregation/promotion callers/tests. |
| `src/career_evidence_graph/cli.py` | `assessment run`, `review`, `reassess`, aggregate, comparison, activation, and inspection wiring. | ✓ VERIFIED | The reassess handler parses a strict model, calls the service, and calls `AssessmentStore.replace` only after success (`615-635`). |
| `tests/test_assessment_admission.py` | Invalid-audit, stale-first, custody, append-only, and service-boundary regression evidence. | ⚠️ PARTIAL | Invalid audit states and service zero-write controls are substantive, but it does not cover the omitted valid proposal mutations. |
| `tests/test_assessment_cli.py` | Black-box dual-store regression evidence for every caller mismatch. | ✗ INCOMPLETE | The 17-case parameterization is active and behavioral, but fails 04-10's all-structural-group coverage contract. |
| `validation/calibration/phase-04/corpus.json` and `policies.json` | Hash-bound calibration inputs and replaceable policy versions. | ✓ VERIFIED | Referenced by actual run/calibration flows; policy history remains unchanged after 04-10. |
| `04-VALIDATION.md` | Measured local gates without a promotion claim. | ✓ VERIFIED | Records 04-10 commands/results and explicitly withholds Phase/requirement completion. |

### Key Link Verification

| From | To | Via | Status | Details |
| --- | --- | --- | --- | --- |
| `reassess_from_new_evidence` | `_materialize_audit` | stale guard, then `allow_replay=False` | ✓ WIRED | Direct call at `assessment.py:1141-1147`. The generic key-link query reports a parser limitation for `path::symbol`, not an absent link. |
| `_materialize_audit` | `AuditStore` | `path_for().lstat()` existence probe then `AuditStore.read()` | ✓ WIRED | No-replay branch at `491-499` has no route to `start_audit`, `transition_audit`, `create`, or `replace`. |
| Reassessment service | `ContributionSkillAssessment` | full canonical-model equality | ✓ WIRED | `proposal != canonical` at `1161-1164`; 14 additional valid mutations independently rejected with dual-store identity. |
| CLI reassessment | service / `AssessmentStore.replace` | strict input, service return, then persistence | ✓ WIRED | `cli.py:617-635`; rejected service calls never reach line 634. |
| Aggregation/promotion | invariants and authority partition | validation plus exact-Skill support | ✓ WIRED | Active aggregation/promotion tests passed; mixed derived/reviewed support remains rejected. |
| Calibration runner | audit custody and retained history | materialized audit identities plus semantic rehash | ✓ WIRED | Custody and retained-history regressions are active and passed. |

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
| --- | --- | --- | --- | --- |
| Reassessment | `AuditSnapshot` then canonical `ContributionSkillAssessment` | Existing `AuditStore` bytes, validated through `_materialize_audit` | Yes | ✓ FLOWING |
| Aggregate result | admitted versions / exact-Skill support | Persisted assessment versions and active policy | Yes | ✓ FLOWING |
| Calibration comparison | policy, run, and comparison histories | Hash-revalidated persisted calibration records | Yes | ✓ FLOWING |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
| --- | --- | --- | --- |
| No-replay, invalid-audit, stale-first, CLI zero-write, append-only, and sampled mismatch controls | `uv run --offline --locked python scripts/run_pytest.py -q` with six named reassessment tests | 26 passed | ✓ PASS |
| Full Phase/workspace regression | `uv run --offline --locked python scripts/run_pytest.py -q` | Exit 0 | ✓ PASS |
| Static quality | `uv run --offline --locked ruff check .` and `ruff format --check .` | Both exit 0 | ✓ PASS |
| Omitted WR-01 field groups on current implementation | Disposable-workspace probe of duration, attribution, assistance, lineage source kind, remaining envelope custody, remaining anchor basis, and remaining judgment bases | 14 valid mutations rejected; assessment sidecar and complete audit tree remained identical | ✓ PASS — current behavior only |

### Probe Execution

Step 7c: **SKIPPED** — no declared or conventional `scripts/**/tests/probe-*.sh` probe exists for Phase 04.

### Requirements Coverage

| Requirement | Source Plan(s) | Description | Status | Evidence |
| --- | --- | --- | --- | --- |
| ASS-01 | 04-01, 04-02, 04-05, 04-09, 04-10 | Specific Skills are grounded in audited Contributions with traceable support. | ✓ SATISFIED | Audit materialization, source envelope, strict models, active proposal tests, and no-replay reassessment wiring. |
| ASS-02 | 04-01, 04-02, 04-05 | Three judgments remain independent. | ✓ SATISFIED | Separate fields/bases and active independence cases. |
| ASS-03 | 04-01, 04-02, 04-05 | Anchored mastery rejects unsupported higher-band claims. | ✓ SATISFIED | Literal anchor validators and active boundary/higher-band cases. |
| ASS-04 | 04-01, 04-03, 04-05, 04-07 | High mastery with inadequate confidence remains provisional. | ✓ SATISFIED | Active admission and immutable review-state regressions. |
| AGG-01 | 04-01, 04-04, 04-05, 04-09, 04-10 | One traceable aggregate per exact Skill. | ✓ SATISFIED | Aggregate traceability and valid reassessment append behavior. |
| AGG-02 | 04-01, 04-04, 04-05 | Evidence/contribution/incidental volume cannot inflate mastery. | ✓ SATISFIED | Active metamorphic no-inflation tests. |
| AGG-03 | 04-01, 04-04, 04-05, 04-08, 04-09, 04-10 | Cross-contribution promotion requires credible behavior and correct authority. | ✓ SATISFIED | Active promotion and authority-partition tests. |
| AGG-04 | 04-01, 04-05, 04-06 | Policy comparisons preserve variance, disagreement, decisions, and regressions. | ✓ SATISFIED | Active audit-custody and semantic-history regressions. |

All eight Phase 04 requirements are declared by at least one plan; no orphaned Phase 04 requirement was found. The blocking gap is a stated 04-10 regression-artifact acceptance condition, not evidence that a separate requirement implementation is presently absent.

### Test Quality Audit

| Test File | Linked Requirement | Active | Skipped | Circular | Assertion Level | Verdict |
| --- | --- | --- | --- | --- | --- | --- |
| `tests/test_assessment_admission.py` | ASS-01, ASS-04, AGG-01, AGG-03 | Yes | 0 | No | Behavioral/byte identity | ✓ PASS, partial matrix |
| `tests/test_assessment_cli.py` | ASS-01, ASS-04, AGG-01, AGG-03 | Yes | 0 | No | Behavioral/CLI exit/byte identity | 🛑 BLOCKER — WR-01 coverage omission |
| `tests/test_skill_aggregation.py` | AGG-01, AGG-02 | Yes | 0 | No | Behavioral/metamorphic | ✓ PASS |
| `tests/test_anchor_promotion.py` | AGG-03 | Yes | 0 | No | Behavioral | ✓ PASS |
| `tests/test_policy_calibration.py` | AGG-04 | Yes | 0 | No | Behavioral/tamper fail-closed | ✓ PASS |

`107` relevant tests were collected. No disabled requirement-linked tests or circular expected-output generation was found. WR-01 is blocking under 04-10's own matrix: Task 2 requires valid Pydantic mutations across **every structural group** and the acceptance criteria require complete canonical equality rather than sampled fields. The present `proposal != canonical` implementation and the verifier's 14-case probe establish current behavior, but they do not satisfy the committed regression deliverable that prevents a future partial comparison from reintroducing the vulnerability.

### Decision Coverage

`check.decision-coverage-verify` reports **16/16** trackable `04-CONTEXT.md` decisions honored. This is advisory and does not override the missing regression evidence.

### Prohibition Review

| Prohibition | Verdict | Evidence |
| --- | --- | --- |
| Rejected reassessment must not create, replace, or repair audit/assessment artifacts. | ✓ VERIFIED | Direct service/CLI zero-write tests and focused 26-test run compare exact sidecar and full audit-tree state. |
| Do not create a second audit authority, staging flow, transaction, or rollback subsystem. | ✓ VERIFIED | The no-replay branch reuses `AuditStore.path_for`/`read`; no new store, staging, transaction, or rollback source exists. |
| Passing local 04-10 gates must not promote Phase 4 or requirements. | ✓ VERIFIED | Post-summary commits are independent review/security documents only; `04-10-SUMMARY.md` retains empty `requirements-completed`. |

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
| --- | --- | --- | --- | --- |
| `tests/test_assessment_cli.py` | 383-403 | Partial whole-proposal mismatch parameterization | 🛑 BLOCKER | Fails the explicit 04-10 regression acceptance matrix and leaves future partial-field regressions unguarded. |
| `ROADMAP.md` Phase 4 metadata | phase goal | MVP mode with a non-User-Story goal | ⚠️ Warning | Canonical MVP user-flow verification remains unavailable. |

No `TBD`, `FIXME`, `XXX`, placeholder, empty implementation, disabled test, or source-level stub was found in Phase 04 implementation/test artifacts.

### Human Verification Required

N/A for the code-level Phase 04 contract: this is an infrastructure/foundation phase with no user-facing surface, and the blocking gap is mechanically observable. The roadmap's invalid MVP user-story metadata must be repaired before a canonical MVP UAT can be created.

### Gaps Summary

04-10 closes the prior CR-01 implementation defect: reassessment is now no-replay, reads an existing audit only, preserves stale-first ordering, compares the complete Pydantic model before persistence, and does not promote authority. The decisive remaining defect is **WR-01**.

WR-01 is a **BLOCKER** under the plan's stated acceptance matrix, even though the current code passed direct testing: the plan did not merely require a correct equality expression; it required a committed valid-mutation regression across every named structural group. Several independent custody and judgment leaves remain untested in repository coverage. Add those durable matrix cases, then rerun independent verification. No later roadmap phase clearly owns this Phase 04 reassessment-test obligation, so it is not deferred.

---

_Verified: 2026-08-28T12:46:00Z_
_Verifier: the agent (gsd-verifier)_
