---
phase: 02-domain-contracts-stoa-fixture-and-deterministic-invariants
verified: 2026-07-30T17:15:52Z
status: passed
score: 47/47 capability must-haves verified
requirements_verified: 9/9
behavior_unverified: 0
overrides_applied: 0
re_verification:
  previous_status: gaps_found
  previous_score: 47/47 capability must-haves verified
  gaps_closed:
    - "The MVP phase goal is a valid user story."
  gaps_remaining: []
  regressions: []
human_verification: []
---

# Phase 2: Domain Contracts, STOA Fixture, and Deterministic Invariants Verification Report

**Phase Goal:** As a user or evaluator, I want to record representative career evidence in a strict Contribution-grounded model, so that invalid or unsupported assessment states are rejected.

**Verified:** 2026-07-30T17:15:52Z  
**Status:** passed  
**Re-verification:** Yes — after the sole metadata-gap closure.

## Re-verification Result

The prior report established that the 47 executable capability must-haves and all
nine Phase 2 requirements were satisfied, but correctly blocked this MVP phase
because the ROADMAP goal was not a canonical User Story. Commit `a736866`
changed only `.planning/ROADMAP.md`; `git diff --name-status 47c46a5..HEAD`
contains that one file and no source, fixture, test, or formal-run change.

The current ROADMAP goal passes the centralized contract:

```json
{"valid":true,"slots":{"role":"user or evaluator","capability":"record representative career evidence in a strict Contribution-grounded model","outcome":"invalid or unsupported assessment states are rejected"}}
```

This closes the previous blocker without widening the capability boundary.

## User Flow Coverage

| Step | Expected | Current codebase evidence | Status |
| --- | --- | --- | --- |
| Record a strict fixture | JSON enters `CareerEvidenceFixture.model_validate`, then collection-level invariant validation | `cli.py` routes `fixture validate` to `load_and_validate_fixture`; full locked suite exercises the contracts and CLI tracer | ✓ VERIFIED |
| Represent traceable evidence | An Experience has Contributions, claims, and separately stored Evidence links | Strict models plus `collect_invariant_violations`; sealed fixture validates as 1 Experience, 4 Contributions | ✓ VERIFIED |
| Reject unsupported assessment state | Invalid lineage, direct sources, score/context/duration/basis, attribution/assistance, Evidence, and ontology changes fail with stable codes | `fixture validate-suite` executed all 16 declared one-fault cases; every case produced exactly its declared sole code | ✓ VERIFIED |
| Review fixture boundary | Completed review has a named reviewer and separate decisions for all candidates/groups before sealing | Current review status is `sealable: true`; sealed fixture verifies the review and checkpoint hashes | ✓ VERIFIED |
| MVP outcome contract | ROADMAP supplies a valid user story matching the exercised capability | `user-story.validate` returned `valid: true` with role, capability, and outcome slots | ✓ VERIFIED |

## Goal Achievement

### Roadmap Success Criteria

| # | Truth | Status | Evidence |
| --- | --- | --- | --- |
| 1 | Typed Experiences contain distinguishable Contributions and Contribution-supported Evidence | ✓ VERIFIED | Frozen strict models, cross-record containment/link checks, and the sealed 1-Experience/4-Contribution fixture. |
| 2 | Direct mastery sources reject and responsibility/assistance remains distinguishable | ✓ VERIFIED | `DIRECT_MASTERY_SOURCES`, attribution invariant checks, and the direct-source/responsibility/Codex-assistance known-bad cases. |
| 3 | Assessments enforce independent 0–100 dimensions plus context, duration, and basis | ✓ VERIFIED | `ContributionSkillAssessment` has independent bounded fields; dedicated model/invariant/mutation tests exercise invalid values. |
| 4 | One Skill view keeps mastery separate from confidence, duration, recency, context, and JD match; ontology cannot create mastery | ✓ VERIFIED | `UserSkillView`, `mastery_snapshot_bytes`, metadata-only normalizer, and ontology regressions; sealed STOA fixture intentionally has no assessments or user-skill views. |
| 5 | A reviewed STOA fixture and good/bad variants cover score, attribution, assistance, context, duration, and evidence-quality boundaries | ✓ VERIFIED | Source verifier returned 4 repositories/10 documents; `zhdeng` review is hash-bound; known-good plus 16 one-fault cases executed. |

### Plan Must-Haves

The six plan frontmatters declare 42 additional truths (8 + 11 + 6 + 5 + 6 + 6).
They remain present, substantive, wired, and tested; together with the five
roadmap criteria this yields **47/47** verified capability must-haves.

| Plan truths | Status | Current evidence |
| --- | --- | --- |
| 02-01 (8): strict model, Evidence, attribution, score, context/duration/basis, CLI tracer | ✓ VERIFIED | Models/invariants are imported by the CLI; the locked suite and the real fixture command exercise the JSON-to-domain path. |
| 02-02 (11): Contribution-only lineage, Skill-view separation, deterministic/no-op ontology metadata | ✓ VERIFIED | Source checks show direct-source rejection, sorted invariant output, exact-Skill view checks, and metadata-only mastery snapshot; invariant tests passed. |
| 02-03 (6): pinned document-only STOA candidate boundary | ✓ VERIFIED | `verify_source_manifest` reads only declared `git show COMMIT:PATH` objects; current command verified the fixed 4-pin/10-document inventory. |
| 02-04 (5): itemized human review authority | ✓ VERIFIED | The existing `zhdeng` checkpoint records four candidate IDs × six decision groups; its SHA-256 is `4878bca9…09e81` and is cross-bound by sealed-fixture validation. |
| 02-05 (6): materialized immutable known-good fixture | ✓ VERIFIED | Sealed envelope cross-binds source/review/checkpoint/v2 formal result; both formal runs verify and replay to `sha256:f393c103…78242`. |
| 02-06 (6): closed, deterministic one-fault known-bad suite | ✓ VERIFIED | Exact 16-file inventory; deep-copy mutations preserve accepted bytes and each returned only the declared failure code. |

**Score:** 47/47 capability must-haves verified; 0 present-but-behavior-unverified.

## Required Artifacts and Key Links

| Artifact / link | Status | Evidence |
| --- | --- | --- |
| `domain/models.py` → `domain/invariants.py` | ✓ WIRED | Strict Pydantic contracts are loaded before aggregate validation; collection validators enforce containment, basis, attribution, Evidence links, and views. |
| `cli.py fixture validate` → `load_and_validate_fixture` | ✓ WIRED | Production CLI route was invoked against the sealed fixture and returned valid JSON. |
| Assessment → Contribution → claim → Evidence → declared Skill | ✓ WIRED | Lineage/basis/reverse-containment validators are in the executable path; model and mutation coverage passed. |
| `source-manifest.json` → pinned Git objects | ✓ WIRED | Current source command verified all declared hashes from the fixed Git object inventory. |
| candidates → review → checkpoint → formal run → `known-good.json` | ✓ WIRED | `review-status` is sealable; known-good validation recomputed the bound hashes; v1 and v2 formal manifests/replay are valid. |
| `known-good.json` → 16 known-bad files | ✓ WIRED | The suite requires the sealed-base hash, exact case inventory, one operation, and one matching sole result. |
| `_career_evidence_build.py` → installed regular wheel | ✓ WIRED | The focused CLI-tracer test included in the 173-pass locked suite builds offline from a fresh cache, installs outside checkout, and rejects `.pth`/source hooks in the regular wheel. |

## Current Behavioral Spot-Checks

| Behavior | Command | Result | Status |
| --- | --- | --- | --- |
| Full locked deterministic suite | `uv run --locked python scripts/run_pytest.py -p no:cacheprovider -q` | `173 passed, 1 deselected` | ✓ PASS |
| Lint and format | `uv run --locked ruff check .` / `uv run --locked ruff format --check .` | `All checks passed!`; `32 files already formatted` | ✓ PASS |
| Pinned source scope | `... fixture source verify --manifest validation/fixtures/stoa/v1/source-manifest.json` | valid; 4 repositories, 10 documents; manifest `sha256:79a56725…2f066` | ✓ PASS |
| Review/checkpoint binding | `... fixture review-status --candidates .../candidates.json --review .../review.json` | `sealable: true`; all six pending-ID lists empty | ✓ PASS |
| Sealed known-good | `... fixture validate validation/fixtures/stoa/v1/known-good.json` | valid; 1 Experience, 4 Contributions, 0 assessments, 0 user-Skill views; fixture `sha256:f393c103…78242` | ✓ PASS |
| Known-bad matrix | `... fixture validate-suite --known-good .../known-good.json --known-bad-dir .../known-bad` | valid; 16/16 cases, each with exactly its expected sole code | ✓ PASS |
| Formal run v1 | `... run verify --workspace validation/fixtures/stoa/v1 --run-id stoa-known-good`; then `... replay ...` | manifest valid; replay matched `sha256:f393c103…78242` | ✓ PASS |
| Formal run v2 | `... run verify --workspace validation/fixtures/stoa/v1 --run-id stoa-known-good-v2`; then `... replay ...` | manifest valid; replay matched `sha256:f393c103…78242` | ✓ PASS |

`...` above is `uv run --locked python scripts/run_career_evidence.py`.

## Requirements Coverage

| Requirement | Status | Evidence |
| --- | --- | --- |
| MOD-01 | ✓ SATISFIED | Closed Experience vocabulary, parent/child containment, and strict model tests. |
| MOD-02 | ✓ SATISFIED | Contribution-only lineage and direct-source/basis/invariant/mutation rejection. |
| MOD-03 | ✓ SATISFIED | Typed, pinned, proof-limited Evidence and unique claim-link validation. |
| MOD-04 | ✓ SATISFIED | Independently bounded assessment dimensions with context/duration/basis failures. |
| MOD-05 | ✓ SATISFIED | Per-claim user/team/other/non-responsibility and Codex/third-party assistance semantics. |
| MOD-06 | ✓ SATISFIED | Exact-Skill view separation and no synthetic user-mastery behavior. |
| MOD-07 | ✓ SATISFIED | Deterministic alias metadata and ontology non-propagation tests. |
| FIX-01 | ✓ SATISFIED | Pinned document boundary, four partial STOA Contributions, itemized named review, and immutable formal evidence. |
| FIX-02 | ✓ SATISFIED | Exact 16 one-fault variants and deterministic batch validation. |

No Phase 2 requirement is orphaned: all nine occur in plan frontmatter and in
the current executable evidence path.

## Review Closure and Anti-Patterns

The final code review is clean. Its sole in-scope issue, the fresh-cache
offline regular-wheel build, was fixed in `4470947` by the in-tree stdlib PEP
517/660 backend; the current full suite includes the external-install probe.
The prior review-fix closure also retained the sealed source/review/checkpoint
cross-binding and confirmed-reviewer enforcement.

No `TBD`, `FIXME`, `XXX`, placeholder, hard-coded empty rendering path, generic
JSON patch facility, live network/provider fixture extraction, database, or
unwired Phase 2 artifact was found. The automatic artifact/link helper cannot
parse a few declarative component and directory endpoints, so those were
checked manually through the concrete source paths and current executable
commands above.

## Human Verification Required

None. The sole Phase 2 human gate was the completed, named `zhdeng` review.
It is now evidence input with a hash bound into `known-good.json` and the v2
formal run; reopening it would be a new authority decision, not verification.

## Scope and Limitations

This phase verifies a strict, deterministic, Contribution-grounded fixture
contract. It does **not** establish calibrated mastery, confidence-admission
or aggregation policy, JD usefulness, résumé generation, product usefulness,
application outcomes, interview outcomes, hiring outcomes, or hiring
effectiveness. The sealed fixture deliberately contains no assessment or
user-level mastery value and states those exclusions explicitly.

---

_Verified: 2026-07-30T17:15:52Z_  
_Verifier: the agent (gsd-verifier)_
