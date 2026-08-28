# Deferred items

## 2026-07-30 — pre-existing Phase 02 full-suite regression

- **Status:** acknowledged
- **Acknowledged at:** v1.0 user-approved partial closeout on 2026-08-28
- `tests/test_cli_tracer.py::test_domain_fixture_rejects_missing_assessment_contribution`
  expects only `assessment.contribution_missing`, but the current Phase 02 invariant
  implementation also returns `assessment.basis_claim_mismatch` and
  `assessment.attribution_not_delivery` for the same malformed fixture.
- The latest relevant implementation change is `f210fa6 feat(02-02): add
  non-propagating skill normalization`; 02-03 did not modify
  `domain/invariants.py` or `tests/test_cli_tracer.py`.
- Task-specific source-boundary and candidate/review-packet tests pass. Resolve
  the assertion/validator ordering in the owning Phase 02 invariant work before
  treating the repository-wide suite as green.
