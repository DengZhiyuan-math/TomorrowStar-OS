# Deferred items

## 2026-07-30 — resolved Phase 02 full-suite regression

- **Status:** resolved
- **Acknowledged at:** v1.0 user-approved partial closeout on 2026-08-28
- **Resolved by:** `987cc7c fix: resolve post-merge conflicts from wave 2`
- **Revalidated at:** 2026-08-28
- `tests/test_cli_tracer.py::test_domain_fixture_rejects_missing_assessment_contribution`
  specifies `assessment.contribution_missing` as the sole violation. The
  pre-fix `f210fa6` revision also emitted the derivative
  `assessment.basis_claim_mismatch` because claim-attribution validation ran
  without a resolved Contribution.
- `987cc7c` added the missing guard before lineage-dependent claim checks. The
  exact CLI test passes at that revision and current HEAD, while the same test
  fails at `f210fa6`; current domain-invariant and sealed one-fault neighbor
  checks also pass.
- The earlier mention of `assessment.attribution_not_delivery` is not
  reproducible from committed `f210fa6` history and is not current behavior.
