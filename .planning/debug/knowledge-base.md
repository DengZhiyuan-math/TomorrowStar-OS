# GSD Debug Knowledge Base

Resolved debug sessions. Used by `gsd-debugger` to surface known-pattern hypotheses at the start of new investigations.

---

## phase2-cascading-violations — Dangling Contribution emitted derivative assessment violations
- **Date:** 2026-08-28
- **Error patterns:** assessment.contribution_missing, assessment.basis_claim_mismatch, assessment.attribution_not_delivery, test_domain_fixture_rejects_missing_assessment_contribution, cascading violations
- **Root cause(s):** Claim-attribution validation continued after an assessment's Contribution reference failed to resolve, so it compared a valid basis claim against a dangling Contribution ID and emitted a derivative mismatch. Commit `987cc7c` fixed the control flow, but the earlier Phase 2 deferred ledger was archived without revalidation and therefore still described the defect as unfixed.
- **Fix:** Reused the existing `987cc7c` resolved-Contribution guard and reconciled `.planning/STATE.md` plus the archived Phase 2 deferred item with historical/current test evidence; no duplicate source change was added.
- **Files changed:** `.planning/STATE.md`, `.planning/milestones/v1.0-phases/02-domain-contracts-stoa-fixture-and-deterministic-invariants/deferred-items.md`
- **Why not caught:** The named regression test caught and gated the source defect, but the milestone closeout verification step did not rerun acknowledged deferred tests against final HEAD, so the obsolete ledger status survived the fixing commit.
- **Recurrence guard:** Regression test `tests/test_cli_tracer.py::test_domain_fixture_rejects_missing_assessment_contribution` requires exactly `assessment.contribution_missing`; it fails at pre-fix `f210fa6` and passes at `987cc7c` and current HEAD. This knowledge-base entry also surfaces the stale-ledger pattern during future Phase-0 recall.
---

## archive-phase-path-regression — Archived milestone broke sealed fixture path resolution
- **Date:** 2026-08-28
- **Error patterns:** .planning/phases, .planning/milestones/v1.0-phases, 02-04-SUMMARY.md, FileNotFoundError, 151 failed, canonical known-good review inputs invalid
- **Root cause(s):** Production and test provenance loading hard-coded the mutable active `.planning/phases` location instead of resolving the sole canonical Phase 2 checkpoint across active and archived milestone layouts.
- **Fix:** Added one stdlib `Path`-based resolver that accepts exactly one active-or-archived canonical checkpoint, reused it in sealed loading, CLI sealing, and repository-backed tests, and added ambiguity regression coverage.
- **Files changed:** `src/career_evidence_graph/domain/fixtures.py`, `src/career_evidence_graph/domain/__init__.py`, `src/career_evidence_graph/cli.py`, `tests/test_stoa_fixture.py`, `tests/test_assessment_admission.py`, `tests/test_policy_calibration.py`
- **Why not caught:** No pre-archive gate exercised sealed fixture loading against the post-archive milestone layout.
- **Recurrence guard:** Regression test `tests/test_stoa_fixture.py::test_checkpoint_summary_resolves_active_or_archived_layout_and_rejects_ambiguity` covers active, archived, and ambiguous layouts; the authoritative 383-test offline suite passed.
---
