---
phase: 07
slug: career-source-custody-and-private-workspace
# status lifecycle: draft (seeded by plan-phase) → validated (set by validate-phase §6)
# audit-milestone §5.5 distinguishes NOT-VALIDATED (draft) from PARTIAL (validated + nyquist_compliant: false) (#2117)
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-08-29
---

# Phase 07 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 9.1.1 with the existing locked Python project |
| **Config file** | `pyproject.toml` |
| **Quick run command** | `uv run --locked python scripts/run_pytest.py -q tests/test_career_source_custody.py tests/test_career_source_security.py` |
| **Full suite command** | `uv run --locked python scripts/run_pytest.py -q && uv run --locked ruff check . && uv run --locked ruff format --check .` |
| **Estimated runtime** | Target: less than 30 seconds offline; measure and record during execution |

---

## Sampling Rate

- **After every task commit:** Run the smallest relevant custody/security test selection plus Ruff on changed Python files.
- **After every plan wave:** Run the full suite command.
- **Before `$gsd-verify-work`:** The full offline suite, public/private boundary scan, and every declared lineage mutation must be green.
- **Max feedback latency:** 30 seconds for offline automated checks.

---

## Per-Task Verification Map

The task IDs are provisional seeds for the planner and must be synchronized with the final PLAN.md files before execution.

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 07-01-01 | 01 | 1 | INV-01 | T-07-05 | Invalid, duplicate, or incomplete source-universe declarations fail closed while a valid revision round-trips byte-for-byte | unit + golden | `uv run --locked python scripts/run_pytest.py -q tests/test_career_source_custody.py -k declaration` | ❌ W0 | ⬜ pending |
| 07-02-01 | 02 | 2 | INV-06 | T-07-03 | Source/capture identity, acquisition metadata, predecessor links, hashes, transformation inputs/outputs, and locators remain traceable; substitution or tampering rejects | unit + lineage mutation | `uv run --locked python scripts/run_pytest.py -q tests/test_career_source_custody.py -k 'capture or lineage or transform'` | ❌ W0 | ⬜ pending |
| 07-03-01 | 03 | 2 | INV-07 | T-07-01, T-07-02, T-07-04 | Raw body, private labels/paths, and private-derived values never enter routine output or the public tree; unsafe paths, links, IDs, controls, and instruction-like input fail safely | adversarial CLI + filesystem | `uv run --locked python scripts/run_pytest.py -q tests/test_career_source_security.py` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_career_source_custody.py` — declaration, capture, recapture, duplicate-source/content, and transformation-lineage coverage for INV-01 and INV-06.
- [ ] `tests/test_career_source_security.py` — public/private boundary, traversal and symlink rejection, content-free stdout/stderr/errors, raw-vault containment, read-only inspection, and operator failure modes for INV-07.
- [ ] Synthetic fixture builders — include raw-body, private-label/path, private-derived hash, hostile Unicode/control, oversized input, and instruction-like sentinels without using any real resume, Skill graph, count, hash, path, report, or career source.
- [ ] Public-tree and simulated staged-diff scan helpers — reject private-workspace artifacts and private-derived sentinel values without inspecting or serializing real private content.

No dependency installation or lockfile change is required.

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Select and bootstrap the separate private career repository without recording its path or contents in the public checkout | INV-07 | Repository ownership, location, and privacy setting are user-controlled external state | At the gated checkpoint, select/create the private repository, verify it is private, verify `.career-evidence/raw/` is ignored there, and confirm no pointer, submodule, path, identifier, count, or derived value was written to the public repository. |
| Declare the first source universe and confirm the raw-vault boundary | INV-01, INV-07 | Completeness and source availability are user claims; automated tests can validate structure but cannot decide the user's full-career boundary | Review every source category, available/unavailable disposition, career-fact cutoff, capture timestamp, and raw-vault destination; confirm omissions explicitly and retain the private declaration only in the private workspace. |

Real-source execution is not a prerequisite for the public harness tests and must not be simulated with personal material. Phase completion may claim the generic workflow and gated private bootstrap; it may claim a completed personal source declaration only after the user performs and confirms the manual step.

---

## Threat References

| Ref | Threat | Required verification |
|-----|--------|-----------------------|
| T-07-01 | Path traversal or symlink escape from the explicit private workspace/raw vault | Reject absolute, parent, nested-separator, out-of-root, and symlinked roots/files with stable content-free codes. |
| T-07-02 | Raw or private-derived data disclosure through stdout, stderr, exceptions, fixtures, reports, cache, or Git | Adversarial sentinel and public-tree/staged-diff scans remain clean; routine envelopes contain only contractually safe fields. |
| T-07-03 | Capture, predecessor, locator, or transformation substitution/laundering | Mutating any bound byte/hash/config/locator/path makes end-to-end lineage verification fail closed. |
| T-07-04 | Instruction-like or hostile source text changes workflow behavior | Treat permitted source text as inert data; no provider, command, path, or transition is selected from source content. |
| T-07-05 | Duplicate content, duplicate logical sources, or availability metadata becomes false corroboration or capability evidence | Preserve declared source identities, deduplicate content without multiplying facts, and create no inventory acceptance, Skill, mastery, or assessment side effect. |

---

## Validation Sign-Off

- [ ] Final PLAN.md task IDs and waves are synchronized with this map.
- [ ] All tasks have `<automated>` verification or an explicit Wave 0 dependency.
- [ ] Sampling continuity: no three consecutive tasks lack automated verification.
- [ ] Wave 0 covers every missing test and synthetic fixture reference.
- [ ] No watch-mode flag, live model/provider call, network dependency, or personal source is part of the default gate.
- [ ] Every INV-01, INV-06, and INV-07 failure path returns a stable content-free diagnostic.
- [ ] Public-tree scans cover fixtures, routine outputs, generated artifacts, and simulated staged changes without deriving expectations from personal content.
- [ ] Feedback latency remains below 30 seconds or the slow checks are explicitly separated while preserving a per-task quick gate.
- [ ] `nyquist_compliant: true` and `wave_0_complete: true` are set only after final task IDs match, referenced files exist, and the full suite is green.

**Approval:** pending
