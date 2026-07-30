---
phase: 01
slug: validation-charter-provenance-and-technical-decision-gate
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-07-30
---

# Phase 01 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 9.1.1 |
| **Config file** | `pyproject.toml` — created in Wave 0 |
| **Quick run command** | `uv run --locked pytest -q tests/test_charter.py tests/test_run_store.py tests/test_replay.py tests/test_provenance.py` |
| **Full suite command** | `uv run --locked pytest -q && uv run --locked ruff check . && uv run --locked ruff format --check .` |
| **Estimated runtime** | ~15 seconds offline |

---

## Sampling Rate

- **After every task commit:** Run the quick command or the smallest listed
  test module covering the task.
- **After every plan wave:** Run the full suite.
- **Before `$gsd-verify-work`:** Full suite must be green.
- **Max feedback latency:** 20 seconds for offline tests.

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 01-01-01 | 01 | 1 | VAL-01 | T-01-01 | Charter rejects prohibited product-effectiveness claims and invalid paths | unit + CLI | `uv run --locked pytest -q tests/test_charter.py tests/test_cli_tracer.py` | ❌ W0 | ⬜ pending |
| 01-01-02 | 01 | 1 | VAL-02 | Formal bundles cannot overwrite or escape the workspace | unit | `uv run --locked pytest -q tests/test_run_store.py tests/test_replay.py` | ❌ W0 | ⬜ pending |
| 01-01-03 | 01 | 1 | OSS-01 | T-01-03 | Provenance profiles fail closed when required source/license fields are absent | unit + CLI | `uv run --locked pytest -q tests/test_provenance.py tests/test_cli_tracer.py` | ❌ W0 | ⬜ pending |
| 01-02-01 | 02 | 2 | VAL-01, VAL-02 | T-01-01, T-01-02, T-01-06 | Critical negative cases are deterministic and cannot mutate accepted artifacts | regression | `uv run --locked pytest -q` | ❌ W0 | ⬜ pending |
| 01-02-02 | 02 | 2 | VAL-02 | T-01-04, T-01-05, T-01-07 | Live Codex execution is opt-in, read-only, version-recorded, and raw-output preserving | contract + opt-in smoke | `uv run --locked pytest -q -m "not live_model" tests/test_codex_cli.py tests/test_security_boundaries.py` | ❌ W0 | ⬜ pending |
| 01-02-03 | 02 | 2 | VAL-02, OSS-01 | T-01-05 | Operator claims stay bounded and all used patterns remain provenance-complete | docs + integration | `uv run --locked pytest -q && uv run --locked career-evidence provenance verify validation/provenance/registry.json` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `.python-version` — pin CPython `3.13.14`.
- [ ] `pyproject.toml` — package metadata, Pydantic, pytest, Ruff, and CLI
  entrypoint.
- [ ] `uv.lock` — locked runtime and development dependencies.
- [ ] `tests/conftest.py` — temporary validation-workspace fixtures.
- [ ] `tests/test_charter.py` — initial red charter contract tests.
- [ ] `tests/test_run_store.py` — initial red immutability tests.
- [ ] `tests/test_replay.py` — initial red exact-replay tests.
- [ ] `tests/test_provenance.py` — initial red provenance-profile tests.
- [ ] `tests/test_cli_tracer.py` — initial red end-to-end CLI tracer.
- [ ] `tests/test_codex_cli.py` — recorded Codex process-contract cases and
  opt-in live marker.
- [ ] `tests/test_security_boundaries.py` — hostile path, mutation, and
  command-boundary regression cases.

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Live Codex CLI accepts `gpt-5.6-luna` with `medium` reasoning and emits JSONL | VAL-02 | Requires local Codex authentication and may incur model usage | Run the opt-in live smoke command documented by Plan 02; inspect the stored CLI version, invocation metadata, raw JSONL, exit code, and drift limitation/snapshot field |
| Human-readable provenance matrix matches the machine registry | OSS-01 | License and divergence descriptions require maintainer review | Compare every machine registry record with `references/README.md`; confirm copied records identify exact upstream path and local divergence |

---

## Validation Sign-Off

- [ ] All tasks have automated verification or Wave 0 dependencies.
- [ ] Sampling continuity: no three consecutive tasks without automated
  verification.
- [ ] Wave 0 covers all missing test references.
- [ ] Default suite contains no live model calls and no watch-mode flags.
- [ ] Feedback latency is under 20 seconds.
- [ ] `nyquist_compliant: true` is set after the validation map matches final
  plan task IDs and all referenced test files exist.

**Approval:** pending
