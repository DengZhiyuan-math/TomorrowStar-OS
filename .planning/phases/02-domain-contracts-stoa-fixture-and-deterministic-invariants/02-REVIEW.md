---
phase: 02-domain-contracts-stoa-fixture-and-deterministic-invariants
reviewed: 2026-07-30T16:05:37Z
depth: standard
files_reviewed: 16
files_reviewed_list:
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
  - validation/fixtures/stoa/v1/formal-runs/stoa-known-good/manifest.json
  - validation/fixtures/stoa/v1/known-good.json
  - validation/fixtures/stoa/v1/review.json
  - validation/fixtures/stoa/v1/source-manifest.json
findings:
  critical: 4
  warning: 1
  info: 0
  total: 5
status: issues_found
---

# Phase 02: Code Review Report

**Reviewed:** 2026-07-30T16:05:37Z
**Depth:** standard
**Files Reviewed:** 16
**Status:** issues_found

## Summary

The submitted source has strong deterministic fixtures and the source-tree-focused Phase 2 tests pass (111 passed). However, the required locked verification command does not test this source tree: it imports a stale installed package, fails collection, and exposes no `fixture validate-suite` command. Independent probes also show that sealing can materialize rejected claims as confirmed user work, and that assessment grounding is incomplete for both Skills and Evidence.

## Narrative Findings (AI reviewer)

## Critical Issues

### CR-01: Required locked verification runs a stale package, not this implementation

**Classification:** BLOCKER

**File:** `tests/test_fixture_mutations.py:16` and `tests/test_stoa_fixture.py:12`

**Issue:** These tests import `career_evidence_graph` directly. Running the declared gate, `uv run --locked pytest -q ...`, imports `/Users/zhdeng/Documents/TomorrowStar OS/.venv/lib/python3.13/site-packages/career_evidence_graph`, which predates Phase 2. Collection then fails because it lacks `FixtureMutationCase` and `load_sealed_fixture`; the same environment's CLI rejects `fixture validate-suite` as an unknown command. The green source run required manually adding `PYTHONPATH=src`, so the recorded Phase 2 gate is neither reproducible nor evidence that the submitted code was tested.

**Fix:** Make the locked project command resolve `src/` deterministically (for example, configure pytest's `pythonpath = ["src"]` and use the same package entry point for the CLI), or ensure the editable package is rebuilt/synced before every locked gate. Add a regression that asserts `career_evidence_graph.__file__` is under the repository's `src/` directory when the documented command runs.

### CR-02: A rejected review can still be sealed as confirmed user/Codex-assisted work

**Classification:** BLOCKER

**File:** `src/career_evidence_graph/domain/fixtures.py:491-518, 577-627`

**Issue:** `evaluate_review_status` considers every state other than `pending` sealable, including `rejected`, and only checks that correction IDs exist. `_reviewed_fixture` then ignores the supplied review decisions and correction contents, hard-coding every candidate as `responsibility="user"`, `assistance="codex_assisted"`, and `confirmation_status="confirmed"`. In a direct probe, changing every recorded `fact` decision to `rejected` still yielded `sealable=True`, and `materialize_review_decisions` returned four user claims. This violates the human-review gate and permits responsibility fabrication during immutable publication.

**Fix:** Materialize claims only from a validated, hash-bound review decision and its concrete corrections. A rejected fact must be omitted from the confirmed fixture; unresolved decisions must remain unresolved and cannot become confirmed claims. Validate each correction's candidate ID, reviewer, original hash, and edited attribution against the output rather than only checking its ID.

### CR-03: A reviewed assessment may rely on a claim with no Evidence link

**Classification:** BLOCKER

**File:** `src/career_evidence_graph/domain/invariants.py:86-106, 109-157`

**Issue:** `validate_evidence_links` validates only links that happen to be present. `validate_claim_attribution` validates the basis claim's attribution but never requires any Evidence link for it. A valid fixture can therefore add a claim to a Contribution, point a reviewed assessment's `basis_claim_ids` at that claim, and provide no link to any Evidence; `collect_invariant_violations` returns no errors. This allows a contribution-to-Skill conclusion without the provenance-bearing Evidence required by MOD-03.

**Fix:** Build a claim-to-Evidence index and reject every assessment basis claim that has no linked, resolved Evidence record (for example `assessment.basis_claim_evidence_missing`). Add a mutation and a direct invariant test for an otherwise reviewed/delivered claim with no Evidence link.

### CR-04: Assessments and user-Skill views may name Skills that do not exist

**Classification:** BLOCKER

**File:** `src/career_evidence_graph/domain/invariants.py:160-191`

**Issue:** The validator derives `assessed_skill_ids` from assessments but never compares those IDs with `fixture.skills`. If an assessment and its view are both changed from `skill.validation` to an undeclared ID, all current checks pass and a user-level mastery view is accepted for no defined Skill. This breaks the strict “one specific Skill” contract rather than merely reporting a malformed reference.

**Fix:** Index `fixture.skills` and reject unknown `assessment.skill_id` and `UserSkillView.skill_id` values before evaluating view uniqueness (for example `assessment.skill_missing` and `user-skill.skill_missing`). Cover the paired unknown-assessment/unknown-view case with an expected deterministic result.

## Warnings

### WR-01: Reverse Experience/Contribution containment is not validated

**Classification:** WARNING

**File:** `src/career_evidence_graph/domain/invariants.py:330-359`

**Issue:** The code verifies each ID listed on an Experience, but never verifies that every Contribution whose `experience_id` names that Experience is included in its `contribution_ids`. An extra Contribution (and its claim) can therefore be accepted while absent from the Experience's declared auditable contents. This duplicated relationship can drift and permits assessments to refer to a Contribution the Experience does not actually enumerate.

**Fix:** After indexing records, compare each Experience's declared contribution IDs with the set of Contributions whose `experience_id` equals its ID. Emit a stable violation for both unlisted Contributions and any mismatched reverse relationship; add a mutation test for an orphan Contribution used by an assessment.

---

_Reviewed: 2026-07-30T16:05:37Z_
_Reviewer: the agent (gsd-code-reviewer)_
_Depth: standard_
