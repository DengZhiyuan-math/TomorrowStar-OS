---
phase: 02
slug: domain-contracts-stoa-fixture-and-deterministic-invariants
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-07-30
---

# Phase 02 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 9.1.1 with strict Pydantic 2.13.4 contracts |
| **Config file** | `pyproject.toml` |
| **Quick run command** | `uv run --locked pytest -q tests/test_domain_models.py tests/test_domain_invariants.py tests/test_stoa_fixture.py tests/test_fixture_mutations.py` |
| **Full suite command** | `uv run --locked pytest -q && uv run --locked ruff check . && uv run --locked ruff format --check .` |
| **Estimated runtime** | Existing 52-test baseline completes in 1.21 seconds; keep Phase 2 offline feedback below 20 seconds |

---

## Sampling Rate

- **After every task commit:** Run the smallest listed Phase 2 test module
  covering the changed contract or fixture, plus Ruff on changed Python files.
- **After every plan wave:** Run the full suite command.
- **Before `$gsd-verify-work`:** Full suite, source-manifest pin verification,
  and every declared known-bad rejection must be green.
- **Max feedback latency:** 20 seconds for offline tests.

---

## Per-Task Verification Map

Task IDs are provisional Wave 0 mappings and must be synchronized with the
final PLAN.md task IDs during execution.

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 02-01-01 | 01 | 1 | MOD-01, MOD-03 | T-02-01 | Unknown fields, invalid parent IDs, unpinned Evidence, and unsupported Experience types fail closed | unit | `uv run --locked pytest -q tests/test_domain_models.py -k "experience or evidence"` | ❌ W0 | ⬜ pending |
| 02-01-02 | 01 | 1 | MOD-04, MOD-05 | T-02-02 | Assessment scores are independently bounded and each concrete claim retains its own attribution and assistance state | unit | `uv run --locked pytest -q tests/test_domain_models.py -k "assessment or attribution"` | ❌ W0 | ⬜ pending |
| 02-01-03 | 01 | 1 | MOD-02 | T-02-03 | Experience, credential, title, repository, résumé, and ontology sources cannot directly create mastery | negative unit | `uv run --locked pytest -q tests/test_domain_invariants.py -k direct_mastery` | ❌ W0 | ⬜ pending |
| 02-02-01 | 02 | 2 | MOD-06 | T-02-04 | Confidence, duration, recency, context, and JD data remain separate from the one specific user-Skill mastery value | invariant | `uv run --locked pytest -q tests/test_domain_invariants.py -k user_skill` | ❌ W0 | ⬜ pending |
| 02-02-02 | 02 | 2 | MOD-07 | T-02-05 | Alias and ontology metadata cannot create or change assessment or mastery records | regression | `uv run --locked pytest -q tests/test_domain_invariants.py -k ontology` | ❌ W0 | ⬜ pending |
| 02-03-01 | 03 | 3 | FIX-01 | T-02-01, T-02-02, T-02-06 | Only named tracked documents at four pinned commits enter the candidate set; document claims never become personal facts without recorded human review | integration | `uv run --locked pytest -q tests/test_stoa_fixture.py` | ❌ W0 | ⬜ pending |
| 02-03-02 | 03 | 3 | FIX-01 | T-02-06 | A known-good fixture cannot seal until facts, attribution, Evidence links, completion status, limitations, and test values are accepted, edited, rejected, or explicitly unresolved | integration + human checkpoint | `uv run --locked pytest -q tests/test_stoa_fixture.py -k seal` | ❌ W0 | ⬜ pending |
| 02-04-01 | 04 | 4 | FIX-02 | T-02-03, T-02-04, T-02-05, T-02-07 | Every known-bad variant references the sealed base hash, declares exactly one mutation, and yields exactly its expected invariant error | regression | `uv run --locked pytest -q tests/test_fixture_mutations.py` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `src/career_evidence_graph/domain/__init__.py` — public Phase 2 domain
  contract surface.
- [ ] `src/career_evidence_graph/domain/models.py` — strict Experience,
  Contribution, claim, Evidence, Skill, assessment, and user-Skill records.
- [ ] `src/career_evidence_graph/domain/invariants.py` — collection-level
  lineage, attribution, duplicate-Evidence, score-separation, and
  ontology-non-propagation validators.
- [ ] `src/career_evidence_graph/domain/fixtures.py` — validated fixture
  loading, sealing prerequisites, base hashes, and closed one-fault mutations.
- [ ] `validation/fixtures/stoa/v1/source-manifest.json` — four pinned
  repositories, permitted tracked document paths, proof limits, section
  locators, and content hashes.
- [ ] `validation/fixtures/stoa/v1/candidates.json` — document-derived
  candidates that are explicitly not yet personal facts.
- [ ] `validation/fixtures/stoa/v1/review.json` — accept/edit/reject/unresolved
  decisions and preserved corrections.
- [ ] `validation/fixtures/stoa/v1/known-good.json` — created only after the
  human verification checkpoint.
- [ ] `validation/fixtures/stoa/v1/known-bad/*.json` — one declared mutation
  and one expected invariant error per case.
- [ ] `tests/test_domain_models.py` — MOD-01, MOD-03, MOD-04, and MOD-05.
- [ ] `tests/test_domain_invariants.py` — MOD-02, MOD-06, and MOD-07.
- [ ] `tests/test_stoa_fixture.py` — FIX-01 and sealing prerequisites.
- [ ] `tests/test_fixture_mutations.py` — FIX-02 single-fault coverage.

No dependency installation or lockfile change is required.

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Confirm the STOA known-good fixture | FIX-01 | Pinned documents can propose project facts but cannot establish the user's personal responsibility, capability, limitations acceptance, or test score expectations | Review every candidate fact, attribution, Evidence link, completion status, limitation, and test value/range; accept, edit, reject, or explicitly leave it unresolved. Confirm that planned-only outcomes remain background and that no known-good seal exists before this review is recorded. |

The manual checkpoint decides fixture truth only. It does not calibrate real
mastery, select an aggregation formula, or evaluate product/job-search
effectiveness.

---

## Validation Sign-Off

- [ ] All final PLAN.md tasks have an automated command or an explicit Wave 0
  dependency.
- [ ] Sampling continuity: no three consecutive tasks lack automated
  verification.
- [ ] Wave 0 creates every missing Phase 2 test and fixture path.
- [ ] No live provider, model call, network dependency, or watch-mode flag is
  part of the default gate.
- [ ] Every known-bad fixture has one base hash, one mutation, one expected
  invariant code, and no second intentional fault.
- [ ] The known-good fixture is not sealed before the manual review record is
  complete.
- [ ] Full-suite feedback latency remains below 20 seconds.
- [ ] `nyquist_compliant: true` and `wave_0_complete: true` are set only after
  final task IDs match, all referenced files exist, and the full suite is
  green.

**Approval:** Pending plan-task synchronization, implementation, and the
human STOA fixture review checkpoint.
