---
quick_id: 260908-dbj
phase: quick-260908-dbj
plan: "01"
status: complete
---

# Candidate Skill Harness Execution Summary

## Outcome

Deployed the synthetic Candidate Skill Link boundary into the audit and
proposal harness without modifying private data, calibration, or JD policy.

## Delivered

- Added the strict, versioned `CandidateSkillLink` contract: one Experience
  Candidate, source/capture identity, locator, candidate wording, and
  extraction version only.
- Candidate-aware audits use `audit-snapshot/v2` only when links are present;
  legacy v1 serialization remains byte-stable for sealed corpus hashes.
- A selected link supplies an explicitly unverified recall reminder outside the
  capability prompt and is retained as optional conclusion/proposal provenance.
- Candidate provenance is attached only when its candidate wording matches the
  proposed Skill's candidate text; an audit-discovered sibling Skill retains no
  fabricated candidate link.
- Loading a v2 audit snapshot rejects any probe, question, or conclusion
  reference to a missing Candidate Skill Link; candidate context is invalid in
  a legacy v1 snapshot.
- Candidate context is rejected when it belongs to another selected Experience
  Candidate. Candidate-free complete audits remain proposal-eligible.
- Added focused synthetic acceptance coverage without duplicating generic
  direct-source/lineage invariant cases.

## Verification

- `uv run --locked python scripts/run_pytest.py -q tests/test_candidate_skill_harness.py tests/test_audit_policy.py tests/test_assessment_proposal.py` — passed (13 tests).
- `uv run --locked ruff check <changed files>` — passed.
- `uv run --locked ruff format --check <changed files>` — passed.
- `git diff --check` — passed.
- `uv run --locked python scripts/run_pytest.py -q` — passed (full offline suite).

## Scope Limits

No private career-data was read or imported. No candidate-skill extractor,
mastery calibration, confidence admission, JD comparison, or résumé-generation
behavior was changed.
