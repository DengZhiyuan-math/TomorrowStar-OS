---
phase: 03-artifact-aware-grill-me-and-attribution-workflow
plan: "17"
subsystem: audit-workflow
tags: [capability-boundary, attribution, pydantic, offline-tests]
requires:
  - phase: 03-16
    provides: Simplified trusted-local AuditSnapshot boundary
provides:
  - Fact-bound capability probe plans and answer-bound decisions
  - Relevant hard-to-simple questioning with explicit skip paths
  - Separate ownership and coding-agent/third-party assistance turns
affects: [03-18, independent-verification]
actuals:
  tokens: 21314
  tasks: 2
  commits: 2
tech-stack:
  added: []
  patterns: [recorded decision port, fact-grounded question reason, per-capability attribution]
key-files:
  created:
    - src/career_evidence_graph/audit/decision.py
    - validation/schemas/audit-probe-plan.schema.json
    - validation/schemas/audit-boundary-decision.schema.json
    - tests/test_audit_decision.py
  modified:
    - src/career_evidence_graph/audit/models.py
    - src/career_evidence_graph/audit/workflow.py
    - src/career_evidence_graph/cli.py
    - tests/test_audit_policy.py
    - tests/test_audit_attribution.py
key-decisions:
  - "Only an exact question-and-answer-bound established decision may state a capability boundary."
  - "Ownership and assistance are separate per-capability turns, not capability areas."
  - "coding-agent-assisted remains provider-neutral; existing Codex configuration is opt-in only."
completion_authority: independent_verification
requirements-addressed: [AUD-01, AUD-02, AUD-03, AUD-04]
requirements-completed: []
duration: 51m
completed: 2026-08-27
status: complete
---

# Phase 03 Plan 17: Capability Boundary and Attribution Summary

**A fact-grounded interview now finds a capability boundary through strict decisions, then records ownership and assistance separately before coverage becomes verified.**

## Accomplishments

- Added strict, data-only probe-plan and boundary-decision contracts. Recorded and fake paths are deterministic; the optional Codex adapter reuses existing configuration and exposes no model or reasoning selector.
- Replaced non-empty-answer promotion with a decision-controlled hard-to-simple ladder, one same-level follow-up, fact-specific reasons, relevant capability areas, and safe area/Contribution skip handling.
- Required separate ownership then assistance turns after every ordinarily established boundary, while early attribution signals follow the same sequence without proving or erasing capability.

## Task Commits

1. **Task 1: Turn one inspected fact and answer into a validated boundary decision** — `663591d`
2. **Task 2: Enforce relevant ladders and ownership-then-assistance on every verified path** — `dd44082`

## Verification

- `uv run --offline --locked python scripts/run_pytest.py -q tests/test_audit_decision.py tests/test_audit_policy.py tests/test_audit_attribution.py tests/test_audit_inspection.py tests/test_assistance_migration.py tests/test_codex_cli.py` — 39 passed, 1 deselected.
- `uv run --offline --locked ruff check src/career_evidence_graph/audit/decision.py src/career_evidence_graph/audit/models.py src/career_evidence_graph/audit/workflow.py src/career_evidence_graph/cli.py tests/test_audit_decision.py tests/test_audit_policy.py tests/test_audit_attribution.py` — passed.
- `rg -n 'phase03_(original|gap)_probe' tests/test_audit_policy.py tests/test_audit_attribution.py` returned no matches; `git diff --check` passed.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Correctness] Persisted the validated probe plan, decisions, and per-capability attribution state in the existing snapshot model.**
- **Found during:** Task 2.
- **Issue:** The existing snapshot had only global attribution fields, so pause/resume could not truthfully retain separate ownership and assistance evidence for more than one selected capability area.
- **Fix:** Added minimal snapshot fields and `AttributionRecord`; no new persistence mechanism, dependency, scoring, or model configuration was introduced.
- **Files modified:** `src/career_evidence_graph/audit/models.py`.
- **Committed in:** `dd44082`.

**Total deviations:** 1 auto-fixed (Rule 2 correctness).

## Known Stubs

None.

## Next Phase Readiness

Plan 03-18 can build reviewable Contribution conclusions from terminal coverage and run the independent acceptance journeys. This plan addresses requirements only; it does not claim Phase 3, AUD requirements, or milestone completion.

## Self-Check: PASSED

Both task commits exist in Git, all nine planned implementation/schema/test paths exist, and no unrelated scheduler configuration or `.gsd/` content was staged.
