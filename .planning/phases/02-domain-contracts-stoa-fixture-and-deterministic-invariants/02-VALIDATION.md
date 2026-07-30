---
phase: 02
slug: domain-contracts-stoa-fixture-and-deterministic-invariants
status: green
nyquist_compliant: true
wave_0_complete: true
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
| **Quick run command** | `uv run --locked python scripts/run_pytest.py -q tests/test_domain_models.py tests/test_domain_invariants.py tests/test_stoa_fixture.py tests/test_fixture_mutations.py` |
| **Full suite command** | `uv run --locked python scripts/run_pytest.py -q && uv run --locked ruff check . && uv run --locked ruff format --check .` |
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

Task IDs and statuses below are synchronized with the final six executed plans.

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 02-01-01 | 01 | 1 | MOD-01, MOD-03 | T-02-01, T-02-02, T-02-03 | A valid Contribution-grounded record crosses the real domain/CLI boundary; broken lineage rejects | e2e tracer | `uv run --locked python scripts/run_pytest.py -q tests/test_cli_tracer.py -k domain_fixture` | ✅ | ✅ green |
| 02-01-02 | 01 | 1 | MOD-01, MOD-03, MOD-04, MOD-05 | T-02-01, T-02-02 | History types, proof limits, attribution, required fields, and independent inclusive 0–100 scores fail closed | unit | `uv run --locked python scripts/run_pytest.py -q tests/test_domain_models.py` | ✅ | ✅ green |
| 02-02-01 | 02 | 2 | MOD-02, MOD-06 | T-02-05, T-02-06, T-02-07 | Direct sources, duplicate Evidence, attribution laundering, and invalid user-Skill views return stable errors | invariant | `uv run --locked python scripts/run_pytest.py -q tests/test_domain_invariants.py -k "direct_mastery or lineage or evidence or attribution or user_skill or idempotent or ordering"` | ✅ | ✅ green |
| 02-02-02 | 02 | 2 | MOD-07 | T-02-08 | Empty/Unicode/alias/ontology metadata is deterministic and cannot change mastery bytes | regression | `uv run --locked python scripts/run_pytest.py -q tests/test_domain_invariants.py -k ontology` | ✅ | ✅ green |
| 02-03-01 | 03 | 2 | FIX-01 | T-02-09, T-02-10, T-02-11 | Only the four pins and ten named tracked documents enter the candidate boundary | integration | `uv run --locked python scripts/run_pytest.py -q tests/test_stoa_fixture.py -k source_manifest` | ✅ | ✅ green |
| 02-03-02 | 03 | 2 | FIX-01 | T-02-11, T-02-12 | One-Experience durable-outcome candidates preserve proof limits, planned-only background, limitations, conflicts, and pending personal claims | integration | `uv run --locked python scripts/run_pytest.py -q tests/test_stoa_fixture.py` | ✅ | ✅ green |
| 02-04-01 | 04 | 3 | FIX-01 | T-02-13, T-02-14, T-02-15 | A named human separately reviews every fact, attribution, Evidence link, completion state, limitation, and fixture score/range | integration + completed human checkpoint | `uv run --locked python scripts/run_pytest.py -q tests/test_stoa_fixture.py -k "source_manifest or candidate or review or seal"` | ✅ | ✅ human-confirmed + green |
| 02-05-01 | 05 | 4 | FIX-01 | T-02-16, T-02-18 | Human decisions and corrections retain proposal bytes, reasons, reviewer identity, and unresolved states | integration | `uv run --locked python scripts/run_pytest.py -q tests/test_stoa_fixture.py -k "review and not seal"` | ✅ | ✅ green |
| 02-05-02 | 05 | 4 | FIX-01, MOD-02, MOD-03, MOD-04, MOD-05, MOD-06, MOD-07 | T-02-17, T-02-19, T-02-20 | Known-good publishes immutably only after review and validates/replays through the production core | integration | `uv run --locked python scripts/run_pytest.py -q tests/test_stoa_fixture.py` | ✅ | ✅ green |
| 02-06-01 | 06 | 5 | FIX-02 | T-02-21, T-02-22, T-02-23 | Every bad variant has one base hash, one operation, one expected code, and one actual sole error | regression | `uv run --locked python scripts/run_pytest.py -q tests/test_fixture_mutations.py` | ✅ | ✅ green |
| 02-06-02 | 06 | 5 | FIX-02 | T-02-24, T-02-25 | The batch CLI, all Phase 2 tests, full suite, lint, format, and validation-status synchronization pass offline | phase gate | `uv run --locked python scripts/run_career_evidence.py fixture validate-suite --known-good validation/fixtures/stoa/v1/known-good.json --known-bad-dir validation/fixtures/stoa/v1/known-bad` | ✅ | ✅ green |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [x] `src/career_evidence_graph/domain/__init__.py` — public Phase 2 domain
  contract surface.
- [x] `src/career_evidence_graph/domain/models.py` — strict Experience,
  Contribution, claim, Evidence, Skill, assessment, and user-Skill records.
- [x] `src/career_evidence_graph/domain/invariants.py` — collection-level
  lineage, attribution, duplicate-Evidence, score-separation, and
  ontology-non-propagation validators.
- [x] `src/career_evidence_graph/domain/fixtures.py` — validated fixture
  loading, sealing prerequisites, base hashes, and closed one-fault mutations.
- [x] `validation/fixtures/stoa/v1/source-manifest.json` — four pinned
  repositories, permitted tracked document paths, proof limits, section
  locators, and content hashes.
- [x] `validation/fixtures/stoa/v1/candidates.json` — document-derived
  candidates that are explicitly not yet personal facts.
- [x] `validation/fixtures/stoa/v1/review.json` — accept/edit/reject/unresolved
  decisions and preserved corrections.
- [x] `validation/fixtures/stoa/v1/known-good.json` — created only after the
  human verification checkpoint.
- [x] `validation/fixtures/stoa/v1/known-bad/*.json` — one declared mutation
  and one expected invariant error per case.
- [x] `tests/test_domain_models.py` — MOD-01, MOD-03, MOD-04, and MOD-05.
- [x] `tests/test_domain_invariants.py` — MOD-02, MOD-06, and MOD-07.
- [x] `tests/test_stoa_fixture.py` — FIX-01 and sealing prerequisites.
- [x] `tests/test_fixture_mutations.py` — FIX-02 single-fault coverage.

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

- [x] All final PLAN.md tasks have an automated command or an explicit Wave 0
  dependency.
- [x] Sampling continuity: no three consecutive tasks lack automated
  verification.
- [x] Wave 0 creates every missing Phase 2 test and fixture path.
- [x] No live provider, model call, network dependency, or watch-mode flag is
  part of the default gate.
- [x] Every known-bad fixture has one base hash, one mutation, one expected
  invariant code, and no second intentional fault.
- [x] The known-good fixture is not sealed before the manual review record is
  complete.
- [x] Full-suite feedback latency remains below 20 seconds.
- [x] `nyquist_compliant: true` and `wave_0_complete: true` are set only after
  final task IDs match, all referenced files exist, and the full suite is
  green.

**Approval:** The `zhdeng` human STOA review remains distinct evidence recorded
in `02-04-SUMMARY.md`; this green status reflects the completed automated gate
plus that recorded checkpoint, not an automated recreation of human judgment.
