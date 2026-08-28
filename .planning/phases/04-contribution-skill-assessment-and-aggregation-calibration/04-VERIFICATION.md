---
phase: 04-contribution-skill-assessment-and-aggregation-calibration
verified: 2026-08-28T09:12:21Z
status: gaps_found
score: 3/5 must-haves verified
behavior_unverified: 0
overrides_applied: 0
re_verification:
  previous_status: gaps_found
  previous_score: 2/5
  gaps_closed:
    - "Calibration derives audit custody and rehashes retained policy, result, and comparison contents."
    - "Normal reruns retain insufficient-basis decisions and reviewer decisions append immutable versions."
    - "Mixed derived/reviewed authority promotion is partitioned and rejected."
  gaps_remaining:
    - "Reassessment accepts a caller-controlled source-audit ID and complete proposal envelope, allowing fabricated audit provenance and reviewed-user-truth admission."
  regressions:
    - "New CR-01: post-remediation reassessment bypasses the audited-source and authority boundary."
gaps:
  - truth: "Specific Skill assessments and user-level mastery are derived only from confirmed audited Contributions with traceable Evidence, answers, attribution, and assessment basis."
    status: failed
    reason: "The reassess CLI accepts caller JSON and an arbitrary syntactically valid source audit ID; the service only checks that the ID differs from the prior version. It neither materializes that audit nor compares it to the proposal envelope, contribution, evidence, conclusion, or authority."
    artifacts:
      - path: "src/career_evidence_graph/assessment.py"
        issue: "reassess_from_new_evidence() at lines 1077-1117 validates only the source-audit string shape, current-version hash, assessment ID, and Skill ID before issuing a new admission/result."
      - path: "src/career_evidence_graph/cli.py"
        issue: "The reassess handler at lines 614-631 parses an arbitrary ContributionSkillAssessment JSON file and persists the returned record without authoritative audit derivation."
      - path: "tests/test_assessment_cli.py"
        issue: "The current reassessment regression tests only a stale version hash; it does not submit a fabricated audit ID or relabelled source envelope."
    missing:
      - "Derive reassessment custody from a materialized completed, confirmed later audit, or reject reassessment until such an authoritative locator exists."
      - "Require the version source-audit ID, proposal envelope audit/contribution/evidence/conclusion identities, origin, and authority to match values derived from that audit."
      - "Add a black-box exploit regression for audit-fabricated plus a relabelled envelope; it must exit 2 and leave sidecar bytes unchanged."
---

# Phase 4: Contribution–Skill Assessment and Aggregation Calibration Verification Report

**Phase Goal:** Reviewers can turn confirmed Contribution audits into traceable Skill assessments and calibrate stable user-level mastery without collapsing distinct signals or rewarding evidence volume.
**Verified:** 2026-08-28T09:12:21Z
**Status:** gaps_found
**Re-verification:** Yes — after remediation Plans 04-06 through 04-08

## User Flow Coverage

Phase 4 is marked `mode: mvp`, but its ROADMAP goal fails the canonical User Story validator: it is not in `As a [role], I want to [capability], so that [outcome].` form. A mandatory MVP user-flow UAT cannot be generated from this goal. This report records the requested technical, goal-backward verification and must not be treated as a completed MVP UAT.

| Step | Expected | Evidence | Status |
| --- | --- | --- | --- |
| Metadata guard | A valid user story defines role, capability, and outcome. | `user-story.validate` returned `valid: false` for the actual Phase 4 goal. | ⚠️ INVALID MVP METADATA |
| Confirmed-audit assessment | Only a completed, confirmed audit can produce a traceable assessment/user result. | The normal run materializes an audit; reassess does not. | ✗ FAILED |
| Outcome | Stable, evidence-grounded Skill outcomes are inspectable. | CR-01 can persist a caller-fabricated admitted `reviewed-user-truth` record. | ✗ FAILED |

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
| --- | --- | --- | --- |
| 1 | Specific Skill proposals come only from audited Contributions and retain Evidence, answers, attribution, and basis lineage. | ✗ FAILED | Reassess accepts a complete caller-controlled proposal and `audit-fabricated`; it does no audit materialization or envelope-to-audit comparison. |
| 2 | Mastery, centrality, and confidence stay independently assignable and inspectable. | ✓ VERIFIED | Separate fields/bases and focused boundary/independence tests exist; the full offline suite exited 0. |
| 3 | Every mastery value has an observable anchor; unsupported higher bands fail, and high-mastery/low-confidence remains provisional. | ✓ VERIFIED | Domain anchor validation and admission boundaries are covered by current tests. |
| 4 | A user can inspect one traceable aggregate per Skill without duplicate/incidental inflation. | ✗ FAILED | Ordinary aggregation works, but an admitted reviewed-user-truth aggregate can be constructed from fabricated, non-audited reassessment provenance. |
| 5 | Policies are comparable with retained variance, disagreement, decisions, and regressions. | ✓ VERIFIED | Calibration materializes audit custody and rehashes retained run/comparison content before activation lookup. |

**Score:** 3/5 truths verified (0 present, behavior-unverified)

### Required Artifacts

| Artifact | Expected | Status | Details |
| --- | --- | --- | --- |
| `src/career_evidence_graph/assessment.py` | Assessment, admission, versioning, aggregation, calibration | ⚠️ HOLLOW FOR GOAL | 1,673 substantive lines and wired callers, but reassessment creates authoritative versions from untrusted source custody. |
| `src/career_evidence_graph/domain/models.py` | Strict assessment, version, policy, and result contracts | ✓ VERIFIED | Strict Pydantic contracts reject malformed shapes, but structural validation cannot establish audit origin. |
| `src/career_evidence_graph/cli.py` | Offline assessment/run/review/reassess/aggregate/calibration commands | ⚠️ WIRED UNSAFELY | The reassess handler forwards parsed JSON plus caller audit ID directly to the mutation service. |
| `src/career_evidence_graph/domain/invariants.py` | Exact-Skill, anchor, and aggregate invariants | ✓ VERIFIED | Wired from aggregation; no stub or orphaned invariant found. |
| Calibration corpus, policies, and history | Hash-bound calibration inputs/history | ✓ VERIFIED | Calibration-specific custody/history regressions now independently validate these artifacts. |
| Phase 04 tests | Behavioral and exploit evidence | ⚠️ INSUFFICIENT FOR REASSESSMENT | The 304-test suite passes, but no test submits fabricated reassessment provenance. |

### Key Link Verification

| From | To | Via | Status | Details |
| --- | --- | --- | --- | --- |
| `cli.py` `assessment run` | `assessment.py` | materialized audit then proposal/admission | ✓ WIRED | `run_assessment()` calls `_materialize_audit()` before proposal construction. |
| `cli.py` `assessment reassess` | `assessment.py` | caller JSON plus `--source-audit-id` | ✗ NOT SAFE | CLI lines 614-631 forward untrusted payloads; service lines 1088-1117 never resolve the claimed audit. |
| Calibration runner | audit custody/history | derived inputs plus semantic hashes | ✓ WIRED | Current code derives snapshot/conclusion values and rehashes retained content. |
| Assessment admission | policy data | validated `AggregationPolicy` decision | ✓ WIRED | `load_policy()` supplies the policy; the generic 04-03 literal pattern probe is invalid, but manual tracing and boundary tests confirm the link. |
| Aggregate/promotion | invariants/authority partition | `validate_user_skill()` / `validate_anchor_promotion()` | ✓ WIRED | Mixed authority promotion is rejected; it does not repair reassessment source custody. |

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
| --- | --- | --- | --- | --- |
| Normal assessment run | `AuditSnapshot` / envelope | `AuditStore` or replayed journey via `_materialize_audit()` | Yes | ✓ FLOWING |
| Calibration run | fixture/manifest/audit/conclusion identities | authoritative bytes plus materialized audit | Yes | ✓ FLOWING |
| Reassessment | audit ID, envelope, origin, authority | caller CLI arguments/JSON | No audit lookup | ✗ DISCONNECTED |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
| --- | --- | --- | --- |
| Existing stale reassessment guard | `uv run --offline --locked python scripts/run_pytest.py -q tests/test_assessment_cli.py::test_explicit_reassess_rejects_stale_hash_without_mutating_sidecar` | `1 passed` | ✓ PASS — narrow only |
| Full offline suite | `uv run --offline --locked python scripts/run_pytest.py -q` | Exit 0 (304 tests) | ✓ PASS — does not exercise CR-01 |
| Ruff check/format | `uv run --offline --locked ruff check .` / `ruff format --check .` | Exit 0 | ✓ PASS |
| CR-01 focused reproduction | Run tracer; submit a relabelled proposal with `--source-audit-id audit-fabricated` and live version hash. | Exit 0; persisted `version_source_audit_id=audit-fabricated`, `envelope_audit_id=audit-e2e`, `authority=reviewed-user-truth`, `origin=audit-verified`, `admission=admitted`, `versions=2`. | ✗ FAIL |

The passing stale-hash test proves optimistic-concurrency handling only. It never attempts a fabricated audit or changed source authority and is not evidence against CR-01.

### Requirements Coverage

| Requirement | Source Plan(s) | Status | Evidence |
| --- | --- | --- | --- |
| ASS-01 | 04-01, 04-02 | ✗ BLOCKED | Reassessment permits a specific-Skill proposal/user result not derived from a completed confirmed audit. |
| ASS-02 | 04-01, 04-02 | ✓ SATISFIED | Independent values and bases remain separately modelled and tested. |
| ASS-03 | 04-01, 04-02 | ✓ SATISFIED | Inclusive anchors and higher-band semantic rejection are tested. |
| ASS-04 | 04-01, 04-03, 04-07 | ✓ SATISFIED | Threshold, substantive review, rerun durability, and append-only version tests pass; CR-01 is a separate source-custody bypass. |
| AGG-01 | 04-01, 04-04 | ✗ BLOCKED | An aggregate can expose an admitted reviewed-user-truth result with fabricated/contradictory source-audit lineage. |
| AGG-02 | 04-01, 04-04 | ✓ SATISFIED | Duplicate, incidental, and cross-Skill Evidence metamorphic tests pass. |
| AGG-03 | 04-01, 04-04, 04-08 | ✗ BLOCKED | Promotion gates inspect authority/origin fields, but reassessment lets callers forge those prerequisite fields before later review; source credibility is not authoritative. |
| AGG-04 | 04-01, 04-05, 04-06 | ✓ SATISFIED | Semantic-history and audit-custody tamper regressions pass. |

All eight requirement IDs are declared by Phase 04 plans. No Phase 5 or 6 contract explicitly owns reassessment source custody, so CR-01 is not deferred.

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
| --- | --- | --- | --- | --- |
| `src/career_evidence_graph/assessment.py` | 1085-1117 | Caller-controlled audit/proposal authority at mutation boundary | 🛑 BLOCKER | Fabricates admitted reviewed-user-truth from derived calibration evidence. |
| `src/career_evidence_graph/cli.py` | 614-631 | Reassess forwards arbitrary JSON/caller audit ID without source derivation | 🛑 BLOCKER | Persists the forged record after schema validation only. |

No `TBD`, `FIXME`, `XXX`, placeholder, empty implementation, or debt-marker blocker was found in Phase 04 source/test files.

### Human Verification Required

N/A for the technical phase contract: the decisive failure is reproducible programmatically. The MVP user-flow metadata remains invalid, so a canonical user-flow UAT cannot be issued from the current ROADMAP goal.

### Gaps Summary

The five prior remediation paths are implemented and tested, but Plan 04-07 introduced an unguarded authoritative mutation path. `assessment reassess` treats audit provenance and authority as caller assertions. The focused reproduction created an admitted reviewed-user-truth record using `audit-fabricated`, with no verified audit to support it. This blocks the Phase 4 goal and ASS-01, AGG-01, and AGG-03. Do not promote Phase 4 or proceed to Phase 5 on this revision.

---

_Verified: 2026-08-28T09:12:21Z_
_Verifier: the agent (gsd-verifier)_
