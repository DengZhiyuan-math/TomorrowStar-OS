---
phase: 04-contribution-skill-assessment-and-aggregation-calibration
reviewed: 2026-08-28T09:05:29Z
depth: standard
files_reviewed: 8
files_reviewed_list:
  - src/career_evidence_graph/domain/models.py
  - src/career_evidence_graph/assessment.py
  - src/career_evidence_graph/cli.py
  - tests/test_policy_calibration.py
  - tests/test_assessment_admission.py
  - tests/test_assessment_cli.py
  - tests/test_anchor_promotion.py
  - tests/test_skill_aggregation.py
findings:
  critical: 1
  warning: 0
  info: 0
  total: 1
status: issues_found
---

# Phase 04: Code Review Report

**Reviewed:** 2026-08-28T09:05:29Z
**Depth:** standard
**Files Reviewed:** 8
**Status:** issues_found

## Summary

The remediation closes the five previously reported direct paths: retained policy hashes are recomputed, calibration materializes the audited snapshot, ordinary assessment reruns retain their record, reviewer versions append, and promotion is partitioned by authority. The focused blocker suite (`59 passed`) and complete offline suite passed, but the newly introduced reassessment path still permits an arbitrary caller payload to manufacture a later audit version and reviewed-user-truth aggregate. This bypasses the custody and authority controls that the remediation is intended to preserve.

## Narrative Findings (AI reviewer)

Passing tests establish the exercised paths only. The reassessment command is a second mutation boundary, so its source-audit and source-envelope values must be derived from a verified audit rather than accepted from CLI-supplied JSON.

## Critical Issues

### CR-01: Reassessment can forge a later audit and relabel derived calibration as reviewed user truth

**Classification:** BLOCKER

**File:** `/Users/zhdeng/Documents/TomorrowStar OS/src/career_evidence_graph/assessment.py:1085-1117`

**Related code:** `/Users/zhdeng/Documents/TomorrowStar OS/src/career_evidence_graph/cli.py:614-631`

**Issue:** `reassess_from_new_evidence()` checks only that `source_audit_id` has the correct string shape and differs from the preceding version (lines 1088-1093). It neither materializes that audit nor requires it to match `proposal.source_envelope.audit_id`, the proposal lineage, contribution, evidence identities, or authority. The only proposal identity guard is its assessment and Skill ID (line 1094). The CLI then accepts the complete arbitrary JSON proposal and persists it. A local reproduction started from the derived calibration tracer, changed the submitted envelope label to `reviewed-user-truth`, and used `audit-fabricated`; reassessment returned an admitted reviewed-user-truth result while the new version named `audit-fabricated` and its envelope still named `audit-e2e`.

**Fix:** Make reassessment derive, not accept, source custody. Pass the workspace and an authoritative later-audit locator into the service; load/materialize the completed, confirmed audit and construct or fully compare the proposal from that verified snapshot. Require all of `AssessmentVersion.source_audit_id`, `proposal.source_envelope.audit_id`, proposal lineage/contribution, and derived audit/evidence/conclusion hashes to agree. Reject authority, origin, and source-envelope changes supplied through reassessment unless they are the values derived from that verified audit. Add a CLI regression that submits `audit-fabricated` and a relabelled envelope, then asserts exit 2 and byte-identical sidecar contents.

---

_Reviewed: 2026-08-28T09:05:29Z_
_Reviewer: the agent (gsd-code-reviewer)_
_Depth: standard_
