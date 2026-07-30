---
phase: 01-validation-charter-provenance-and-technical-decision-gate
verified: 2026-07-30T09:51:27Z
status: passed
score: 6/6 must-haves verified
behavior_unverified: 0
overrides_applied: 0
gaps: []
human_verification: []
requirements_verified: [VAL-01, VAL-02, OSS-01]
live_model_smoke: not_run_optional
---

# Phase 1: Validation Charter, Provenance, and Technical Decision Gate Verification

**Phase Goal:** As a validation evaluator, I want to start a falsifiable and
reproducible validation study with fixed success rules, trust boundaries, and
upstream reuse decisions, so that future results can be evaluated without
tuning those rules after seeing them.

**Verified:** 2026-07-30T09:51:27Z  
**Status:** passed  
**Re-verification:** No — initial verification

## User Flow Coverage

| Step | Expected | Evidence | Status |
|------|----------|----------|--------|
| Load the study contract | The evaluator can load one versioned, strict, functional-only charter before any real result exists | `validation/charter/v1.json`; `ValidationCharter`; `tests/test_charter.py`; live CLI check returned `{"valid": true}` | ✓ VERIFIED |
| Record and replay a run | The evaluator can create an immutable run, verify all bytes and lineage, and replay recorded output without a live provider | `FormalRunStore`, `replay_recorded_response`, `tests/test_run_store.py`, `tests/test_replay.py`, `tests/test_cli_tracer.py` | ✓ VERIFIED |
| Check trust boundaries | Critical blockers, hostile paths, Codex subprocess controls, and alias drift fail closed | `tests/test_security_boundaries.py`, `tests/test_codex_cli.py`, `01-SECURITY.md` | ✓ VERIFIED |
| Trace upstream reuse | Every declared adaptation can be checked against pinned revision, license, source, divergence, and a covering test | `validation/provenance/registry.json`; `verify_provenance_registry`; live CLI check returned four valid records | ✓ VERIFIED |
| Outcome | Future functional results can be evaluated under rules fixed before those results are seen | Charter version, formal hashes, immutable reruns, exact replay, and machine provenance are wired into the CLI | ✓ VERIFIED |

The optional real Luna invocation is not part of this user flow's acceptance
evidence. It remains a separately marked technical smoke and was not run.

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | A versioned charter fixes the functional claim boundary, expected-result policy, case eligibility, blockers, and decision vocabulary before results exist | ✓ VERIFIED | Strict charter validation plus `tests/test_charter.py`; no STOA case or holdout was invented |
| 2 | A recorded run is reproducible from complete input hashes without overwriting the original | ✓ VERIFIED | Formal manifests require all seven lineage inputs; reruns link to and revalidate immutable ancestry; 52-test offline suite passed |
| 3 | Reused or adapted seams are traceable to pinned upstream revision, path, license, classification, attribution, divergence, and tests | ✓ VERIFIED | Four strict provenance records pass both unit tests and `career-evidence provenance verify` |
| 4 | Every critical failure class blocks independently and cannot be offset by unrelated strengths | ✓ VERIFIED | Six parameterized blocker cases in `tests/test_security_boundaries.py` |
| 5 | The Codex runtime seam is fixed to Luna medium, structured JSON, and read-only execution without a shell | ✓ VERIFIED | Argument and runner contract tests pass; local Codex help accepts the locked reasoning syntax |
| 6 | Live-boundary metadata and model identity fail closed on malformed output, secrets, path escape, raw-response mismatch, or untrusted snapshot claims | ✓ VERIFIED | Recorded subprocess and hostile-input tests pass; security register closes T-01-04 through T-01-07 |

**Score:** 6/6 truths verified; 0 behavior-unverified.

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `validation/charter/v1.json` | Frozen functional validation contract | ✓ VERIFIED | Strictly loaded by CLI and tests; case count remains zero |
| `src/career_evidence_graph/validation/store.py` | Immutable formal bundles and lineage | ✓ VERIFIED | Substantive create/verify/rerun implementation; invoked by CLI and replay |
| `src/career_evidence_graph/validation/replay.py` | Exact provider-free replay | ✓ VERIFIED | Reads only verified stored payloads; no runner parameter exists |
| `src/career_evidence_graph/codex_cli.py` | Shell-free Luna-medium technical gate | ✓ VERIFIED | Fixed argv, allowlisted environment, raw JSONL capture, snapshot/drift policy |
| `validation/provenance/registry.json` | Machine-readable upstream traceability | ✓ VERIFIED | Four records validated against README and covering tests |
| `docs/validation-runs.md` | Operator contract and claim boundary | ✓ VERIFIED | Separates offline commands, optional live smoke, and prohibited effectiveness claims |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `cli.py` | `store.py` | `run create`, `run verify`, and `live-run codex` | ✓ WIRED | CLI constructs and verifies formal bundles |
| `cli.py` | `replay.py` | `replay` subcommand | ✓ WIRED | Returns non-zero on mismatch and never calls a provider |
| `codex_cli.py` | `store.py` | Validated `CodexCLIResult` becomes immutable live metadata | ✓ WIRED | Raw JSONL and structured result must match before publication |
| `provenance.py` | registry, README, tests | CLI `provenance verify` | ✓ WIRED | Machine and human records plus covering-test paths are checked together |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| Full deterministic behavior | `uv run --locked pytest -q` | 52 passed, 1 live smoke deselected | ✓ PASS |
| Charter loading | `career-evidence validate-charter validation/charter/v1.json` | Charter `1.0.0`, valid | ✓ PASS |
| Provenance traceability | `career-evidence provenance verify` | 4 records, valid | ✓ PASS |
| Live gate remains opt-in | `pytest --collect-only -q -m live_model` | Exactly one marked live smoke collected | ✓ PASS |
| Static quality | `ruff check .` and `ruff format --check .` | Passed | ✓ PASS |

### Probe Execution

No separate probe scripts were declared. CLI spot-checks above cover the
runnable Phase 1 entry points.

### Requirements Coverage

| Requirement | Source Plans | Status | Evidence |
|-------------|--------------|--------|----------|
| VAL-01 | 01-01, 01-02 | ✓ SATISFIED | Versioned charter plus executable independent blocker cases |
| VAL-02 | 01-01, 01-02 | ✓ SATISFIED | Full input hashes, immutable bundles, ancestry validation, corrections, exact replay, and bounded live metadata |
| OSS-01 | 01-01, 01-02 | ✓ SATISFIED | Strict provenance registry, synchronized human matrix, pinned revisions, licenses, divergence, and covering tests |

No Phase 1 requirement is orphaned.

### Anti-Patterns Found

No unresolved `TBD`, `FIXME`, or `XXX` markers were found in local Phase 1
source, tests, validation data, or operator documentation. Code review found
and resolved three trust gaps in commit `98372f8`; the final review status is
clean.

## Human Verification Required

None for the Phase 1 functional infrastructure goal. A real Codex Luna smoke is
optional external-runtime evidence, not a prerequisite for the deterministic
phase goal and not evidence of STOA or job-search effectiveness.

## Gaps Summary

No blocking gaps. Phase 1 establishes that the planned validation functions and
trust boundaries run as designed. It does not establish that the broader
product is effective; the first real STOA fixture belongs to Phase 2.

---

_Verified: 2026-07-30T09:51:27Z_  
_Verifier: Codex inline gsd-verifier execution_
