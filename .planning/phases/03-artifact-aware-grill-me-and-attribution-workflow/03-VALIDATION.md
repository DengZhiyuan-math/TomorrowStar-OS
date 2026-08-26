---
phase: 3
slug: artifact-aware-grill-me-and-attribution-workflow
# status lifecycle: draft (seeded by plan-phase) → validated (set by validate-phase §6)
# audit-milestone §5.5 distinguishes NOT-VALIDATED (draft) from PARTIAL (validated + nyquist_compliant: false)
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-08-26
---

# Phase 3 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 9.1.1 |
| **Config file** | `pyproject.toml` |
| **Quick run command** | `UV_CACHE_DIR=/tmp/career-evidence-uv-cache uv run --locked python scripts/run_pytest.py -q tests/test_audit_policy.py tests/test_audit_store.py` |
| **Full suite command** | `UV_CACHE_DIR=/tmp/career-evidence-uv-cache uv run --locked python scripts/run_pytest.py -q` |
| **Estimated runtime** | Target under 30 seconds for quick sampling; measure during Wave 0 |

> Environment prerequisite: restore the locked Python 3.13.14 interpreter before execution. The current `.venv/bin/python` target is absent and the host `python3` is 3.14.5; do not change the project's `>=3.13,<3.14` range to bypass this gate.

---

## Sampling Rate

- **After every task commit:** Run the task's targeted audit test file plus `UV_CACHE_DIR=/tmp/career-evidence-uv-cache uv run --locked ruff check src tests`
- **After every plan wave:** Run `UV_CACHE_DIR=/tmp/career-evidence-uv-cache uv run --locked python scripts/run_pytest.py -q` and `UV_CACHE_DIR=/tmp/career-evidence-uv-cache uv run --locked ruff format --check src tests`
- **Before `$gsd-verify-work`:** Full offline suite and Ruff checks must be green
- **Max feedback latency:** 30 seconds for the targeted quick command

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 03-W0-01 | TBD | 0 | AUD-01 | T-03-01 | Inspection is bounded to pinned fixture sources; project documents never establish personal capability | unit + integration | `UV_CACHE_DIR=/tmp/career-evidence-uv-cache uv run --locked python scripts/run_pytest.py -q tests/test_audit_inspection.py` | ❌ W0 | ⬜ pending |
| 03-W0-02 | TBD | 0 | AUD-02, AUD-03 | Invalid, repeated, multi-part, leading, and artifact-answerable transitions fail closed | unit + persistence | `UV_CACHE_DIR=/tmp/career-evidence-uv-cache uv run --locked python scripts/run_pytest.py -q tests/test_audit_policy.py tests/test_audit_store.py` | ❌ W0 | ⬜ pending |
| 03-W0-03 | TBD | 0 | AUD-04 | Ownership and assistance stay separate; legacy assistance remains provenance-compatible | unit + migration | `UV_CACHE_DIR=/tmp/career-evidence-uv-cache uv run --locked python scripts/run_pytest.py -q tests/test_audit_attribution.py tests/test_assistance_migration.py` | ❌ W0 | ⬜ pending |
| 03-W0-04 | TBD | 0 | AUD-05 | Review never overwrites the original proposal and rejects numeric score promotion | integration + CLI | `UV_CACHE_DIR=/tmp/career-evidence-uv-cache uv run --locked python scripts/run_pytest.py -q tests/test_audit_conclusion.py tests/test_audit_cli.py` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] Restore or install the locked Python 3.13.14 interpreter and verify `uv run --locked python --version` reports Python 3.13.14.
- [ ] `tests/test_audit_models.py` — strict audit-contract rejection matrix.
- [ ] `tests/test_audit_inspection.py` — sealed source-manifest/fixture boundary and reason traceability for AUD-01.
- [ ] `tests/test_audit_policy.py` — one-question, relevance, hard-to-simple, same-level follow-up, anti-leading, and resume transition matrix for AUD-02/AUD-03.
- [ ] `tests/test_audit_store.py` — atomic snapshots, invalid identifiers, corruption rejection, and history immutability for AUD-02.
- [ ] `tests/test_audit_attribution.py` — separate responsibility/assistance rounds and conflict/unresolved flows for AUD-04.
- [ ] `tests/test_assistance_migration.py` — legacy `codex_assisted` read compatibility without rewriting sealed fixture bytes.
- [ ] `tests/test_audit_conclusion.py` — capability boundary plus immutable edit/confirm/reject lineage for AUD-05.
- [ ] `tests/test_audit_cli.py` — complete offline start/answer/skip/pause/resume/inspect/review flow.

---

## Manual-Only Verifications

All phase behaviors are designed for automated offline verification. A later `$gsd-verify-work` session may additionally inspect question wording, but no Phase 3 requirement depends solely on manual verification.

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verification or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verification
- [ ] Wave 0 covers all missing test references
- [ ] No watch-mode flags
- [ ] Targeted feedback latency is under 30 seconds
- [ ] Full offline suite and Ruff checks pass under Python 3.13.14
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
