---
phase: 04-contribution-skill-assessment-and-aggregation-calibration
reviewed: 2026-08-28T12:31:44Z
depth: standard
files_reviewed: 3
files_reviewed_list:
  - src/career_evidence_graph/assessment.py
  - tests/test_assessment_admission.py
  - tests/test_assessment_cli.py
findings:
  critical: 0
  warning: 1
  info: 0
  total: 1
status: issues_found
---

# Phase 04: Code Review Report

**Reviewed:** 2026-08-28T12:31:44Z
**Depth:** standard
**Files Reviewed:** 3
**Status:** issues_found

## Summary

The no-replay reassessment path correctly requires a pre-existing audit, delegates persisted-snapshot validation to `AuditStore.read`, preserves stale-hash-before-corpus behavior in the service, and compares the submitted proposal with the complete canonical Pydantic model. The focused reassessment suite passed (56 tests); Ruff lint and format checks for the three scoped files also passed.

The remaining gap is regression adequacy. The tests claim whole-proposal coverage but exercise only a subset of independently meaningful fields, so they do not protect the stated complete-canonical-equality contract against a future return to a partial comparison.

## Warnings

### WR-01: Whole-proposal equality regression omits several independently valid custody fields

**Classification:** WARNING

**File:** `tests/test_assessment_cli.py:383-448`

**Issue:** The parameterized black-box mismatch matrix mutates selected top-level values, one source-envelope hash, one anchor basis, and one judgment basis, but it does not exercise valid mismatches in `duration`, `attribution_status`, `assistance_status`, `lineage.source_kind`, most source-envelope custody fields (`fixture_hash`, `source_manifest_hash`, conclusion hashes, evidence/question IDs, and `attribution_hash`), the remaining anchor bases, or the centrality/confidence judgment bases. The companion service test in `tests/test_assessment_admission.py:480-541` covers invalid audit states rather than these omitted proposal leaves. This falls short of the plan's required matrix for full lineage, source-envelope custody, context/duration, attribution, assistance, and all judgment bases. The current `proposal != canonical` implementation is sound, but this test set would allow a later sampled-field comparison to reintroduce a caller-controlled custody bypass without a failing regression.

**Fix:** Extend the service or CLI parameterization with one Pydantic-valid forged value for every independently mutable leaf/group. Build the payload from the canonical proposal, validate it with `ContributionSkillAssessment.model_validate`, invoke reassessment, and assert exit/rejection plus byte-identical assessment sidecar and complete audit-tree snapshots for each case. Include valid mutations for duration, all source-envelope hashes/ID collections, attribution/assistance state, lineage source kind, every anchor basis, and all three judgment bases.

---

_Reviewed: 2026-08-28T12:31:44Z_
_Reviewer: the agent (gsd-code-reviewer)_
_Depth: standard_
