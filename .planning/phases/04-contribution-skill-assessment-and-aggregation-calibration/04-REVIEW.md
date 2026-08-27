---
phase: 04-contribution-skill-assessment-and-aggregation-calibration
reviewed: 2026-08-27T20:37:02Z
depth: standard
files_reviewed: 14
files_reviewed_list:
  - src/career_evidence_graph/domain/models.py
  - src/career_evidence_graph/domain/invariants.py
  - src/career_evidence_graph/assessment.py
  - src/career_evidence_graph/cli.py
  - validation/calibration/phase-04/corpus.json
  - validation/calibration/phase-04/policies.json
  - tests/test_assessment_cli.py
  - tests/test_assessment_models.py
  - tests/test_assessment_proposal.py
  - tests/test_mastery_anchors.py
  - tests/test_assessment_admission.py
  - tests/test_skill_aggregation.py
  - tests/test_anchor_promotion.py
  - tests/test_policy_calibration.py
findings:
  critical: 5
  warning: 0
  info: 0
  total: 5
status: issues_found
---

# Phase 04: Code Review Report

**Reviewed:** 2026-08-27T20:37:02Z
**Depth:** standard
**Files Reviewed:** 14
**Status:** issues_found

## Summary

The Phase 4 assessment and calibration seams were reviewed against the Phase 4 plan decisions, including the explicit no-inflation, immutable-review, audit-custody, and policy-activation requirements. The focused suite passes (`64 passed`), but it does not exercise several authority-changing failure paths. Five blockers remain: hashes stored in policy history are never checked against their contents, calibration runs do not revalidate their audit/conclusion custody, a normal rerun erases review history and an insufficient-basis decision, review edits replace rather than preserve the current immutable version, and synthetic evidence can be used to promote a result labelled as reviewed user truth.

## Narrative Findings (AI reviewer)

The primary risk is not a malformed JSON input: strict Pydantic parsing succeeds while semantic authority is silently changed. This is contrary to the project's stated requirement that calibration ancestry, reviewed evidence, and score-promotion bases remain independently verifiable.

## Critical Issues

### CR-01: Policy history accepts tampered results and comparisons without recomputing their hashes

**Classification:** BLOCKER

**File:** `/Users/zhdeng/Documents/TomorrowStar OS/src/career_evidence_graph/domain/models.py:430`

**Related code:** `/Users/zhdeng/Documents/TomorrowStar OS/src/career_evidence_graph/assessment.py:1127`, `/Users/zhdeng/Documents/TomorrowStar OS/src/career_evidence_graph/assessment.py:1423`

**Issue:** `PolicyRunResult` validates only unique case IDs, `PolicyComparison` has no content-integrity validator, and `_validate_policy_history` checks only cross-references. It never recomputes `result_hash` from `case_results`, nor `comparison_hash` from the retained comparison. A reproduced temporary-workspace attack changed a persisted run's first `mastery` from 54 to 53 while retaining its original `result_hash`; `load_policy_history()` accepted it. An activation can therefore point to altered calibration evidence while appearing hash-bound and immutable.

**Fix:** Persist the canonical policy snapshot with each run, then recompute and compare `policy_hash`, `result_hash`, and `comparison_hash` on every history read before accepting any pointer or activation. Add a regression test that mutates a valid case result, delta, or regression label without changing its stored hash and requires `load_policy_history()` to fail.

### CR-02: Calibration policy runs trust declared audit and conclusion hashes instead of verifying the audited source

**Classification:** BLOCKER

**File:** `/Users/zhdeng/Documents/TomorrowStar OS/src/career_evidence_graph/assessment.py:1255`

**Related code:** `/Users/zhdeng/Documents/TomorrowStar OS/src/career_evidence_graph/assessment.py:1127`

**Issue:** `run_calibration_policy()` verifies only the fixture and source-manifest bytes (lines 1265-1271). Its `input_hashes` then accepts the corpus's declared audit snapshot, conclusion-lineage, and effective-conclusion hashes as strings (lines 1127-1146). It never opens/materializes the audit or checks those three values against it. Thus a modified corpus can describe a different or invented audited conclusion while retaining valid fixture/manifest hashes, and the policy run records it as immutable provenance.

**Fix:** Reuse the completed-audit verification performed by `_materialize_audit()` (or extract a shared verifier) inside `run_calibration_policy()`, require the declared values to be valid SHA-256 values, and derive all five custody hashes from the verified fixture/audit objects rather than from corpus strings. Add tamper tests for each audit/conclusion hash.

### CR-03: Re-running the standard CLI path deletes substantive review history and restores admission

**Classification:** BLOCKER

**File:** `/Users/zhdeng/Documents/TomorrowStar OS/src/career_evidence_graph/assessment.py:1060`

**Issue:** The run ID is deterministic for an audit/policy pair (line 1070). When that record already exists, `run_assessment()` catches the collision and replaces the whole sidecar with a newly constructed one (lines 1073-1077). This bypasses the immutable version chain: a completed `insufficient-basis` review becomes a fresh admitted proposal with no reviews. Reproduction: after such a review, the record was `unverified-candidate` with one review; running the documented assessment command again returned `admitted` with zero reviews.

**Fix:** Make an existing run idempotently return only an identical validated record, or reject it. If a new assessment is intentional, require an explicit reassessment operation that appends a new version with an expected-current hash; it must never overwrite prior reviews or admission decisions. Add an end-to-end CLI regression test for rerun-after-review.

### CR-04: Reviewer edits overwrite the latest immutable version instead of appending a versioned correction

**Classification:** BLOCKER

**File:** `/Users/zhdeng/Documents/TomorrowStar OS/src/career_evidence_graph/assessment.py:991`

**Issue:** `review_assessment()` uses the current version's ID and `previous_version_hash` (lines 991-996), then constructs `(*record.versions[:-1], version)` (line 1006). Every correction replaces the latest `AssessmentVersion`; only a before/after hash remains, not the prior effective assessment content needed to verify that hash. After multiple edits, intervening assessed values are irretrievable, contradicting the Phase 4 decision that corrections are immutable, hash-linked assessment versions.

**Fix:** Create a new `AssessmentVersion` for every review (`...-{len(record.versions)+1}`), set its `previous_version_hash` to the current version hash, and append it to `record.versions`. Preserve the prior version and add a test with two edits that verifies every historical effective assessment remains present and each predecessor hash resolves to its retained bytes.

### CR-05: Derived counterfactual evidence can promote a reviewed-user-truth Skill score

**Classification:** BLOCKER

**File:** `/Users/zhdeng/Documents/TomorrowStar OS/src/career_evidence_graph/assessment.py:779`

**Related code:** `/Users/zhdeng/Documents/TomorrowStar OS/src/career_evidence_graph/assessment.py:864`

**Issue:** Promotion validation only requires a non-null source envelope plus resolved attribution/assistance and a judgment basis (lines 784-794). It does not require `reviewed-user-truth`, a reviewed status, or audit-verified origin. `aggregate_user_skills()` can therefore combine a reviewed-user-truth baseline with a derived-counterfactual assessment that supplies the second Contribution/context and required behaviors; it then takes the baseline envelope's label (lines 891-906) and emits an elevated score labelled `reviewed-user-truth`. This is a direct hidden score-inflation and authority-transfer path.

**Fix:** Partition aggregation and promotion inputs by authority label, and require every assessment used for a user-truth promotion to be reviewed user truth with completed substantive review and verified audit provenance. Keep synthetic calibration promotions in a separate derived output that can never merge into a user-facing result. Add a mixed-authority promotion test that must fail closed.

---

_Reviewed: 2026-08-27T20:37:02Z_
_Reviewer: the agent (gsd-code-reviewer)_
_Depth: standard_
