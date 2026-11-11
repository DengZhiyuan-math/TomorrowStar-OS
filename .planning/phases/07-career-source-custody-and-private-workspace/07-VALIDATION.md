---
phase: 07
slug: career-source-custody-and-private-workspace
status: validated
nyquist_compliant: true
wave_0_complete: true
created: 2026-08-29
updated: 2026-08-31
---

# Phase 07 — Validation Strategy

> Planning-time selector contract for Plans 07-00 through 07-09. `nyquist_compliant: true` means every final task has a runnable automated check and its test module exists; it is not evidence that unexecuted Plans 07-04 through 07-09 pass.

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 9.1.1 with the existing locked Python project |
| **Config file** | `pyproject.toml` |
| **Quick run command** | `uv run --locked python scripts/run_pytest.py -q tests/test_career_source_custody.py tests/test_career_source_security.py` |
| **Full suite command** | `uv run --locked python scripts/run_pytest.py -q && uv run --locked ruff check . && uv run --locked ruff format --check .` |
| **Evidence boundary** | Synthetic private Git repositories and invented sentinels only; no personal workspace, source, path, hash, count, or remote is used. |

## Wave and Dependency Map

| Wave | Plan | Depends on | Validation focus |
|------|------|------------|------------------|
| 0 | 07-00 | none | Test modules, synthetic builders, and collection surface |
| 1 | 07-01 | 07-00 | End-to-end explicit-workspace custody tracer |
| 2 | 07-02 | 07-00, 07-01 | Declaration, capture, transformation, and duplicate lineage |
| 3 | 07-03 | 07-00, 07-02 | CLI/no-echo/public-boundary completion |
| 4 | 07-04 | 07-03 | Mandatory full-OID snapshot and complete inventory verification |
| 5 | 07-05 | 07-04 | Exact source, declaration-bound captures, and retained outputs |
| 6 | 07-06 | 07-05 | Workspace-complete legacy input, output authentication, and successor staging |
| 7 | 07-07 | 07-06 | Single-process deterministic commit, Git-ref-only CAS, and temporal descendant verification |
| 8 | 07-08 | 07-07 | All-namespace symlinks, nine bidi controls, and synchronous same-failure-path raw cleanup |
| 9 | 07-09 | 07-08 | Source-aware closure gates and fresh current-HEAD evidence |

## Sampling Rate

- **After every task commit:** Run the task's focused selector plus Ruff on changed Python files.
- **After every plan wave:** Run both Phase 07 test modules.
- **Before `$gsd-verify-work`:** Run the full offline suite, public/private boundary scan, full-OID mutation matrix, and every declared lineage/ref/cleanup mutation.
- **Default gate:** No watch mode, network, provider call, dependency installation, or personal source.

## Per-Task Verification Map

`✅ existing` means the task was already executed and its selector/module is recorded in 07-00 through 07-03 summaries; no command was rerun during this planning revision. `⬜ planned` means selector coverage is specified for execution, not that it currently passes.

| Task ID | Plan | Wave | Requirement | Secure behavior | Automated command | Test file | Status |
|---------|------|------|-------------|-----------------|-------------------|-----------|--------|
| 07-00-01 | 00 | 0 | INV-01, INV-06 | Custody selectors and synthetic lineage builders collect before implementation | `uv run --locked python scripts/run_pytest.py --collect-only -q tests/test_career_source_custody.py` | existing | ✅ existing |
| 07-00-02 | 00 | 0 | INV-07 | Security selectors and synthetic disclosure sentinels collect | `uv run --locked python scripts/run_pytest.py --collect-only -q tests/test_career_source_security.py` | existing | ✅ existing |
| 07-01-01 | 01 | 1 | INV-07 | One-way public/private decision records no private value | `git diff --check` | N/A | ✅ existing |
| 07-01-02 | 01 | 1 | INV-01, INV-06, INV-07 | Synthetic declaration-capture-transform-inspect path is candidate-only | `uv run --locked python scripts/run_pytest.py -q tests/test_career_source_custody.py -k tracer` | existing | ✅ existing |
| 07-01-03 | 01 | 1 | INV-07 | Initial traversal, symlink, disclosure, and collision cases fail safely | `uv run --locked python scripts/run_pytest.py -q tests/test_career_source_security.py` | existing | ✅ existing |
| 07-02-00 | 02 | 2 | INV-06 | Versioned D-18/D-19 seam is confirmed without private values | `git diff --check` | N/A | ✅ existing |
| 07-02-01 | 02 | 2 | INV-01 | Strict declaration revisions and unavailable dispositions round-trip | `uv run --locked python scripts/run_pytest.py -q tests/test_career_source_custody.py -k declaration` | existing | ✅ existing |
| 07-02-02 | 02 | 2 | INV-06 | Capture/predecessor/transform/locator/duplicate mutations reject | `uv run --locked python scripts/run_pytest.py -q tests/test_career_source_custody.py -k 'capture or lineage or transform or duplicate'` | existing | ✅ existing |
| 07-03-01 | 03 | 3 | INV-07 | Explicit-workspace CLI and content-free diagnostics are enforced | `uv run --locked python scripts/run_pytest.py -q tests/test_career_source_security.py -k 'cli or output or inspect or format'` | existing | ✅ existing |
| 07-03-02 | 03 | 3 | INV-01, INV-07 | Private boundary checkpoint is paired with the synthetic quick gate | `uv run --locked python scripts/run_pytest.py -q tests/test_career_source_custody.py tests/test_career_source_security.py` | existing | ✅ existing |
| 07-03-03 | 03 | 3 | INV-01, INV-06, INV-07 | Full offline public-boundary and zero-authority regression gate | `uv run --locked python scripts/run_pytest.py -q && uv run --locked ruff check . && uv run --locked ruff format --check .` | existing | ✅ existing |
| 07-04-01 | 04 | 4 | INV-06 | Exact full OID authenticates one complete commit/raw snapshot | `uv run --locked python scripts/run_pytest.py tests/test_career_source_custody.py -k 'explicit_commit or snapshot_anchor or raw_authentication' -x` | existing, expanded by task | ⬜ planned |
| 07-04-02 | 04 | 4 | INV-06 | Committed/working inventories match bidirectionally, expected-zero included | `uv run --locked python scripts/run_pytest.py tests/test_career_source_custody.py tests/test_career_source_security.py -k 'inventory or expected_zero or empty_workspace or coordinated_edit or current_capture' -x` | existing, expanded by task | ⬜ planned |
| 07-05-01 | 05 | 5 | INV-06 | Exact source selection, declaration binding, and retained output authenticate | `uv run --locked python scripts/run_pytest.py tests/test_career_source_custody.py -k 'exact_source_id or declaration_bound or retained_output or migration_required' -x` | existing, expanded by task | ⬜ planned |
| 07-05-02 | 05 | 5 | INV-06 | Every transformation/output participates in explicit-commit verification | `uv run --locked python scripts/run_pytest.py tests/test_career_source_custody.py -k 'transformation_inventory or transformation_tamper or derived_output or stale_commit' -x` | existing, expanded by task | ⬜ planned |
| 07-06-01 | 06 | 6 | INV-06 | Complete request authenticates each retained non-identity output before writes | `uv run --locked python scripts/run_pytest.py tests/test_career_source_custody.py -k 'workspace_migration_request or retained_output_artifact or non_identity_output' -x` | existing, expanded by task | ⬜ planned |
| 07-06-02 | 06 | 6 | INV-06 | Two-source/multi-chain staging and receipt coverage are exhaustive | `uv run --locked python scripts/run_pytest.py tests/test_career_source_custody.py -k 'two_source_multi_chain or exhaustive_migration_coverage or migration_staging_retry' -x` | existing, expanded by task | ⬜ planned |
| 07-07-01 | 07 | 7 | INV-06 | One operator process finalizes synchronously; Git expected-old CAS alone protects the dedicated ref, and detected external workspace drift fails closed | `uv run --locked python scripts/run_pytest.py tests/test_career_source_custody.py -k 'retention_ref or ref_cas or finalization_interrupt or adjudicate_complete_workspace' -x` | existing, expanded by task | ⬜ planned |
| 07-07-02 | 07 | 7 | INV-06 | Migration head equality becomes verified same-source descendant semantics later | `uv run --locked python scripts/run_pytest.py tests/test_career_source_custody.py -k 'migration_head_temporal or post_migration_recapture or descendant_chain' -x` | existing, expanded by task | ⬜ planned |
| 07-08-01 | 08 | 8 | INV-07 | Every semantic namespace rejects directory/nested/dangling/leaf symlinks | `uv run --locked python scripts/run_pytest.py tests/test_career_source_security.py -k 'symlink and semantic_namespace' -x` | existing, expanded by task | ⬜ planned |
| 07-08-02 | 08 | 8 | INV-07 | All nine bidi controls reject recursively before side effects | `uv run --locked python scripts/run_pytest.py tests/test_career_source_security.py -k 'bidi or unicode_control' -x` | existing, expanded by task | ⬜ planned |
| 07-08-03 | 08 | 8 | INV-06, INV-07 | Cleanup completes synchronously in the failed call, unions exact committed and validated working references, and retains on drift or uncertainty | `uv run --locked python scripts/run_pytest.py tests/test_career_source_custody.py tests/test_career_source_security.py -k 'committed_raw_reference or deleted_working_manifest or raw_cleanup or shared_raw or manifest_collision' -x` | existing, expanded by task | ⬜ planned |
| 07-09-01 | 09 | 9 | INV-01, INV-06, INV-07 | Current-checkout selectors and recursive quality scope exclude only tool-managed nested worktrees | `uv run --locked ruff format --check . && uv run --locked python -c "from pathlib import Path; p=Path('.planning/phases/07-career-source-custody-and-private-workspace/07-VALIDATION.md'); rows=[line for line in p.read_text(encoding='utf-8').splitlines() if any(line.startswith(f'| 07-{plan}-') for plan in ('04','05','06','07','08'))]; assert len(rows) == 11 and all('scripts/run_pytest.py' in line for line in rows)"` | config and validation contract | ⬜ planned |
| 07-09-03 | 09 | 9 | INV-01, INV-06, INV-07 | Current HEAD is exercised through source-aware tests, quality gates, review ancestry, and content-free boundary checks | `uv run --locked python scripts/run_pytest.py -q tests/test_career_source_custody.py tests/test_career_source_security.py && uv run --locked python scripts/run_pytest.py -q && uv run --locked ruff check . && uv run --locked ruff format --check . && git diff --check` | synthetic custody and security modules | ⬜ planned |

## Wave 0 Completion Evidence

- [x] `tests/test_career_source_custody.py` exists and 07-00-SUMMARY records its collection scaffold and named selector families.
- [x] `tests/test_career_source_security.py` exists and 07-00-SUMMARY records its collection scaffold and synthetic disclosure sentinels.
- [x] Builders use invented raw-body, label/path, digest, hostile Unicode/control, oversized, instruction-like, public-tree, and staged-diff values only.
- [x] Plans 07-04 through 07-08 extend the same modules under TDD; no missing test module or dependency installation is required.

This revision did not rerun tests. Wave 0 completion is based on existing files and the executed 07-00 summary, while the gap-plan rows remain planned until execution.

## Manual-Only Verifications

| Behavior | Requirement | Why manual | Instruction |
|----------|-------------|------------|-------------|
| Select and bootstrap the separate private career repository without recording its identity publicly | INV-07 | Repository ownership/location/privacy are user-controlled external state | Use the already approved runtime-only `--workspace` boundary; never paste the path, remote, personal IDs, hashes, counts, or contents into public artifacts. |
| Declare the first personal source universe and confirm the raw-vault boundary | INV-01, INV-07 | Completeness and availability are user claims | Review privately; return only the approved/safe outcome. This does not create Phase 8 inventory acceptance. |

## Security and Failure Coverage

| Area | Plans | Required proof |
|------|-------|----------------|
| Full-OID snapshot authority and expected-zero inventory | 07-04 | Omitted/short/symbolic/stale anchors, missing/extra paths, and coordinated edits fail. |
| Exact source/declaration/output lineage | 07-05 | Two-source selection, immutable declaration binding, retained bytes, and transform/output tampering fail. |
| Workspace-complete legacy migration | 07-06 | Every chain and output artifact is present, authenticated, and bidirectionally receipt-mapped; two-source coverage is mandatory. |
| Commit retention and temporal heads | 07-07 | Single-process finalization, absent/existing/stale Git-ref CAS, interruptions, detected workspace drift, deterministic retry, migration equality, and later same-source descendants are covered. |
| Filesystem, Unicode, and destructive cleanup | 07-08 | All semantic symlinks, nine bidi controls, synchronous same-failure-path cleanup, committed-reference/working-deletion, shared objects, detected drift, and uncertainty-retains cases are covered. |
| Public/private and later-authority fences | 07-00 through 07-09 | No personal fixture/output and no inventory seal, graph, mastery, JD, gap, or resume side effect. |

## Validation Sign-Off

- [x] Final task IDs, plan count, dependencies, and waves are synchronized through 07-09.
- [x] Every task has an `<automated>` command; checkpoint tasks retain structural/quick automated checks.
- [x] Sampling continuity has no three consecutive tasks without automated verification.
- [x] Wave 0 modules and synthetic builders exist; later tasks expand them test-first.
- [x] No default selector uses watch mode, network, provider calls, personal sources, or a new dependency.
- [x] Full explicit commit OIDs remain mandatory for authoritative verify and cleanup-baseline paths, including expected-zero cases.
- [x] Workspace mutations are planned as one synchronous operator-owned CLI process: no workspace-lock or cross-process guarantee is introduced, Git expected-old CAS remains the sole ref-race protection, and cleanup completes inline before failure returns.
- [x] Planned selectors cover all five checker blockers plus symlink, bidi, public/private, and no-later-authority regressions.
- [x] `nyquist_compliant: true` records complete planned selector coverage only; runtime pass evidence for Plans 07-04 through 07-09 remains pending execution.

**Approval:** Validation contract synchronized for execution; no implementation result is claimed for unexecuted gap plans.

## Validation Audit 2026-08-31

| Metric | Count |
|--------|-------|
| Gaps found | 0 |
| Resolved | 0 |
| Escalated | 0 |

This post-Task-1 audit evaluates coverage rather than Plan 07-09 completion. `07-09-01` is covered by the recursive Ruff-format gate and the static check that all eleven Plan 07-04 through 07-08 selectors invoke `scripts/run_pytest.py`. `07-09-03` is covered by the source-aware focused/full test and quality-gate chain specified in its verification row. `07-09-02` is the intentional blocking human-action checkpoint that obtains this validation authority and the separate security authority; it is not a substitute code behavior or a reason to infer a requirement pass.

`07-09-SUMMARY.md` is pending. This audit does not claim that Plan 07-09, INV-01, INV-06, INV-07, Phase 07, or the milestone is complete. All evaluated test and boundary contracts remain synthetic-only; no real private career workspace, repository, path, remote, identity, hash, count, or content was accessed.
