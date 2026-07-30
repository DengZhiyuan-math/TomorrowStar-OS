---
phase: 02-domain-contracts-stoa-fixture-and-deterministic-invariants
reviewed: 2026-07-30T16:47:46Z
depth: standard
files_reviewed: 44
files_reviewed_list:
  - _build_backend.py (deleted; reviewed through d7edfb6)
  - pyproject.toml
  - scripts/run_career_evidence.py
  - scripts/run_pytest.py
  - src/career_evidence_graph/cli.py
  - src/career_evidence_graph/domain/__init__.py
  - src/career_evidence_graph/domain/fixtures.py
  - src/career_evidence_graph/domain/invariants.py
  - src/career_evidence_graph/domain/models.py
  - tests/fixtures/domain_fixture.json
  - tests/test_cli_tracer.py
  - tests/test_domain_invariants.py
  - tests/test_domain_models.py
  - tests/test_fixture_mutations.py
  - tests/test_stoa_fixture.py
  - validation/fixtures/stoa/v1/candidates.json
  - validation/fixtures/stoa/v1/review.json
  - validation/fixtures/stoa/v1/source-manifest.json
  - validation/fixtures/stoa/v1/known-good.json
  - validation/fixtures/stoa/v1/formal-runs/stoa-known-good/manifest.json
  - validation/fixtures/stoa/v1/formal-runs/stoa-known-good/raw_response.json
  - validation/fixtures/stoa/v1/formal-runs/stoa-known-good/original_proposal.json
  - validation/fixtures/stoa/v1/formal-runs/stoa-known-good/confirmed_result.json
  - validation/fixtures/stoa/v1/formal-runs/stoa-known-good/corrections.json
  - validation/fixtures/stoa/v1/formal-runs/stoa-known-good-v2/manifest.json
  - validation/fixtures/stoa/v1/formal-runs/stoa-known-good-v2/raw_response.json
  - validation/fixtures/stoa/v1/formal-runs/stoa-known-good-v2/original_proposal.json
  - validation/fixtures/stoa/v1/formal-runs/stoa-known-good-v2/confirmed_result.json
  - validation/fixtures/stoa/v1/formal-runs/stoa-known-good-v2/corrections.json
  - validation/fixtures/stoa/v1/known-bad/dimension-confusion.json
  - validation/fixtures/stoa/v1/known-bad/direct-mastery-experience.json
  - validation/fixtures/stoa/v1/known-bad/direct-mastery-ontology.json
  - validation/fixtures/stoa/v1/known-bad/direct-mastery-repository.json
  - validation/fixtures/stoa/v1/known-bad/direct-mastery-resume-skill-list.json
  - validation/fixtures/stoa/v1/known-bad/direct-mastery-title.json
  - validation/fixtures/stoa/v1/known-bad/duplicate-evidence-link.json
  - validation/fixtures/stoa/v1/known-bad/missing-assessment-basis.json
  - validation/fixtures/stoa/v1/known-bad/missing-context.json
  - validation/fixtures/stoa/v1/known-bad/missing-contribution-lineage.json
  - validation/fixtures/stoa/v1/known-bad/missing-duration.json
  - validation/fixtures/stoa/v1/known-bad/obscured-codex-assistance.json
  - validation/fixtures/stoa/v1/known-bad/ontology-mastery-change.json
  - validation/fixtures/stoa/v1/known-bad/score-above-hundred.json
  - validation/fixtures/stoa/v1/known-bad/score-below-zero.json
  - validation/fixtures/stoa/v1/known-bad/wrong-responsibility.json
findings:
  critical: 0
  warning: 0
  info: 0
  total: 0
status: clean
---

# Phase 02: Code Review Report

**Reviewed:** 2026-07-30T16:47:46Z
**Depth:** standard
**Files Reviewed:** 44
**Status:** clean

## Summary

Final adversarial re-review found no actionable correctness, security, or robustness defects in the reviewed Phase 2 scope. The standard Flit wheel no longer embeds a global `sitecustomize` or a build-machine source path; the project-local launchers select checkout code only for their own invoked process. The current locked commands work without `PYTHONPATH`, while the isolated-wheel regression imports the installed artifact from outside the checkout.

The sealed fixture now recomputes and cross-binds source-manifest, canonical review, and checkpoint-summary hashes against the v2 formal-run lineage. The confirmed reviewer is required both when validating corrections and when materializing review decisions; coordinated reviewer tampering fails closed. The v1 formal bundle remains retained historical evidence, `known-good.json` points to `stoa-known-good-v2`, and both bundles independently verify and replay to the same confirmed fixture hash. All 16 closed known-bad cases bind that hash and return exactly their one declared error.

Verification performed without `PYTHONPATH`:

- `uv run --locked python scripts/run_pytest.py -q` — `173 passed, 1 deselected`.
- `uv run --locked ruff check .` and `uv run --locked ruff format --check .` — passed.
- `uv run --locked python scripts/run_career_evidence.py fixture validate ...known-good.json` — valid.
- `fixture validate-suite` — valid with `case_count: 16` and one matching sole error per case.
- `run verify` and `replay` — passed for both `stoa-known-good` and `stoa-known-good-v2`.

## Narrative Findings (AI reviewer)

No Critical Issues, Warnings, or Info findings.

### Prior-finding closure

| Prior finding | Re-review result |
| --- | --- |
| CR-01 global wheel import hook | Closed: the custom backend is deleted, standard Flit packaging is used, and the isolated-wheel regression passed. |
| CR-02 missing sealed source/review/checkpoint binding | Closed: loader recomputes canonical input hashes and compares envelope plus v2 `artifacts`/`reviewer` lineage hashes. |
| WR-01 non-confirmed reviewer materialization | Closed: exact `zhdeng` review and checkpoint identities are required before materialization. |
| Earlier CR-02 rejected claim sealing | Remains closed: rejected facts are omitted and unresolved review decisions are unsealable. |
| Earlier CR-03 Evidence basis gap | Remains closed: an assessment basis claim requires a resolved Evidence link. |
| Earlier CR-04 undeclared Skill reference | Remains closed: assessment and user-view Skill references are checked. |
| Earlier reverse containment warning | Remains closed: Contributions absent from their Experience are rejected. |

---

_Reviewed: 2026-07-30T16:47:46Z_
_Reviewer: the agent (gsd-code-reviewer)_
_Depth: standard_
