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

> Environment gate: Plan 03-01 Task 1 first performs read-only detection. If Python 3.13.14 is absent, execution stops at a blocking human-action checkpoint; `uv python install 3.13.14` may run only after explicit approval. All later commands require the exact-version check to pass.

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
| 03-01-01 | 03-01 | 0 | environment | — | Detect exact interpreter; conditionally stop for explicit install authority | preflight | `PY313_PATH="$(uv python find 3.13.14)" && test "$($PY313_PATH --version)" = "Python 3.13.14"` | n/a | ⬜ pending |
| 03-01-02 | 03-01 | 0 | AUD-01..05 | T-03-01..04 | Offline tracer and strict contracts fail closed | integration | `UV_CACHE_DIR=/tmp/career-evidence-uv-cache uv run --locked python scripts/run_pytest.py -q tests/test_audit_cli.py tests/test_audit_models.py` | 03-01 / Wave 0 | ⬜ pending |
| 03-01-03 | 03-01 | 0 | AUD-01 | T-03-01..04 | Inspection remains pinned and non-personal | unit + integration | `UV_CACHE_DIR=/tmp/career-evidence-uv-cache uv run --locked python scripts/run_pytest.py -q tests/test_audit_inspection.py tests/test_audit_cli.py` | 03-01 / Wave 0 | ⬜ pending |
| 03-02-01 | 03-02 | 1 | AUD-02, AUD-03 | T-03-05 | Question transitions fail closed | unit | `UV_CACHE_DIR=/tmp/career-evidence-uv-cache uv run --locked python scripts/run_pytest.py -q tests/test_audit_policy.py` | 03-02 / Wave 1 | ⬜ pending |
| 03-02-02 | 03-02 | 1 | AUD-04 | T-03-06..07 | Attribution axes and migration remain distinct | unit + migration | `UV_CACHE_DIR=/tmp/career-evidence-uv-cache uv run --locked python scripts/run_pytest.py -q tests/test_audit_attribution.py tests/test_assistance_migration.py` | 03-02 / Wave 1 | ⬜ pending |
| 03-03-01 | 03-03 | 2 | AUD-05 | T-03-10 | Complete prose conclusion only | unit | `UV_CACHE_DIR=/tmp/career-evidence-uv-cache uv run --locked python scripts/run_pytest.py -q tests/test_audit_conclusion.py` | 03-03 / Wave 2 | ⬜ pending |
| 03-03-02 | 03-03 | 2 | AUD-05 | T-03-08..09 | Immutable review lineage | persistence | `UV_CACHE_DIR=/tmp/career-evidence-uv-cache uv run --locked python scripts/run_pytest.py -q tests/test_audit_conclusion.py tests/test_audit_store.py` | 03-03 / Wave 2 | ⬜ pending |
| 03-03-03 | 03-03 | 2 | AUD-05 | T-03-08..10 | CLI review and full phase gate | integration | `UV_CACHE_DIR=/tmp/career-evidence-uv-cache uv run --locked python scripts/run_pytest.py -q` | 03-03 / Wave 2 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] Detect Python 3.13.14; if absent, pause for explicit approval before installing exactly that version; verify the resolved interpreter reports Python 3.13.14.
- [ ] `tests/test_audit_models.py` — strict audit-contract rejection matrix.
- [ ] `tests/test_audit_inspection.py` — sealed source-manifest/fixture boundary and reason traceability for AUD-01.
- [ ] `tests/test_audit_cli.py` — complete offline start/answer/skip/pause/resume/inspect/review flow.

Later-wave tests (`test_audit_policy.py`, `test_audit_attribution.py`, `test_assistance_migration.py`, `test_audit_store.py`, and `test_audit_conclusion.py`) are created by their owning Plan 03-02/03-03 tasks and are not Wave 0 prerequisites.

## 28-Item Edge-Probe Matrix

| # | Probe | Mapping |
|---:|---|---|
| 1 | AUD-01 duplicate/overlapping locators stay distinct | `test_inspection_preserves_duplicate_source_locators` |
| 2 | AUD-01 missing Contribution | `test_inspection_rejects_missing_contribution` |
| 3 | AUD-01 empty evidence links | `test_inspection_rejects_empty_linked_evidence` |
| 4 | AUD-01 null/unverified manifest | `test_inspection_rejects_unverified_manifest` |
| 5 | AUD-01 deterministic ordering | `test_inspection_order_is_stable` |
| 6 | AUD-01 repeat start idempotency | `test_start_does_not_overwrite_existing_audit` |
| 7 | AUD-01 interrupted/competing creation | `test_audit_creation_is_atomic_under_competition` |
| 8 | AUD-02 one active question/order | `test_transition_has_exactly_one_active_question` |
| 9 | AUD-02 blank/null answer | `test_blank_answer_fails_closed` |
| 10 | AUD-02 duplicate action | `test_duplicate_action_is_idempotent` |
| 11 | AUD-02 stale concurrent action | `test_stale_expected_hash_rejects_lost_update` |
| 12 | AUD-02 pause/resume no repeat | `test_resume_returns_next_unanswered_question` |
| 13 | AUD-03 one same-level follow-up | `test_only_one_same_level_followup` |
| 14 | AUD-03 second incomplete descends | `test_second_incomplete_answer_descends` |
| 15 | AUD-03 unknown descends | `test_dont_know_descends_without_penalty` |
| 16 | AUD-03 exhausted/irrelevant area | `test_exhausted_or_irrelevant_area_emits_no_question` |
| 17 | AUD-03 Unicode round trip | `test_unicode_answer_and_reason_round_trip_exactly` |
| 18 | AUD-03 deterministic ladder order | `test_fixture_ladder_is_hard_to_simple_and_stable` |
| 19 | AUD-04 ownership before assistance | `test_ownership_precedes_assistance` |
| 20 | AUD-04 assistance cannot fill ownership | `test_assistance_never_fills_ownership` |
| 21 | AUD-04 absent/Unicode/unresolved attribution | `test_attribution_values_round_trip_distinctly` |
| 22 | AUD-04 conflicting attribution preserved | `test_conflict_preserves_documentary_and_user_claims` |
| 23 | AUD-04 legacy read/canonical write | `test_legacy_codex_assisted_reads_and_new_write_is_canonical` |
| 24 | AUD-05 incomplete coverage blocks proposal | `test_incomplete_coverage_blocks_conclusion` |
| 25 | AUD-05 stable entry order/UTF-8 | `test_conclusion_order_and_unicode_are_stable` |
| 26 | AUD-05 duplicate terminal review | `test_duplicate_terminal_review_is_idempotent` |
| 27 | AUD-05 competing/tampered review | `test_stale_or_tampered_review_fails_closed` |
| 28 | AUD-05 original proposal and no-score boundary | `test_review_preserves_original_and_emits_no_verified_numeric_score` |

No-silent-drop gate: `test_validation_probe_matrix.py::test_all_28_edge_probes_are_collected` must assert exact set equality between these 28 names and collected probe IDs; additions or omissions fail.

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

---

## Final executable inventory (03-04 through 03-07)

This section is human-readable only. Runtime authority is
`tests/test_validation_probe_matrix.py`, which asks pytest to collect the scoped
files and compares its full node IDs against hard-coded constants; this Markdown
file is never parsed to establish coverage.

| Marker | Owning files | Requirement / finding mapping | Plan references |
|---|---|---|---|
| `phase03_original_probe` | The seven files listed below | Original AUD-01 through AUD-05 28-item acceptance matrix | 03-01, 03-02, 03-03; materialized in 03-06 and collected in 03-07 |
| `phase03_gap_probe` | `tests/test_audit_workflow_regressions.py`, `tests/test_audit_storage_regressions.py` | Lifecycle/English attribution/basis/reference/review gaps plus CAS, full-chain, replay, and recovery gaps | Repaired in 03-04 and 03-05; marked in 03-06 and collected in 03-07 |
| end-to-end acceptance | `tests/test_audit_gap_e2e.py` | AUD-01..05 and T-03G-17/T-03G-18 public-CLI custody journey | 03-07 |

### Exact original 28 node IDs

```text
tests/test_audit_cli.py::test_start_does_not_overwrite_existing_audit
tests/test_audit_cli.py::test_audit_creation_is_atomic_under_competition
tests/test_audit_inspection.py::test_inspection_order_is_stable
tests/test_audit_inspection.py::test_inspection_preserves_duplicate_source_locators
tests/test_audit_inspection.py::test_inspection_rejects_missing_contribution
tests/test_audit_inspection.py::test_inspection_rejects_empty_linked_evidence
tests/test_audit_inspection.py::test_inspection_rejects_unverified_manifest
tests/test_audit_policy.py::test_transition_has_exactly_one_active_question
tests/test_audit_policy.py::test_only_one_same_level_followup
tests/test_audit_policy.py::test_second_incomplete_answer_descends
tests/test_audit_policy.py::test_dont_know_descends_without_penalty
tests/test_audit_policy.py::test_blank_answer_fails_closed
tests/test_audit_policy.py::test_duplicate_action_is_idempotent
tests/test_audit_policy.py::test_stale_expected_hash_rejects_lost_update
tests/test_audit_policy.py::test_resume_returns_next_unanswered_question
tests/test_audit_policy.py::test_exhausted_or_irrelevant_area_emits_no_question
tests/test_audit_policy.py::test_unicode_answer_and_reason_round_trip_exactly
tests/test_audit_policy.py::test_fixture_ladder_is_hard_to_simple_and_stable
tests/test_audit_attribution.py::test_ownership_precedes_assistance
tests/test_audit_attribution.py::test_assistance_never_fills_ownership
tests/test_audit_attribution.py::test_attribution_values_round_trip_distinctly
tests/test_audit_attribution.py::test_conflict_preserves_documentary_and_user_claims
tests/test_assistance_migration.py::test_legacy_codex_assisted_reads_and_new_write_is_canonical
tests/test_audit_conclusion.py::test_incomplete_coverage_blocks_conclusion
tests/test_audit_conclusion.py::test_conclusion_order_and_unicode_are_stable
tests/test_audit_conclusion.py::test_review_preserves_original_and_emits_no_verified_numeric_score
tests/test_audit_conclusion.py::test_duplicate_terminal_review_is_idempotent
tests/test_audit_store.py::test_stale_or_tampered_review_fails_closed
```

### Exact gap nine node IDs

```text
tests/test_audit_workflow_regressions.py::test_paused_and_terminal_lifecycle_actions_fail_closed
tests/test_audit_workflow_regressions.py::test_supported_english_and_chinese_attribution_are_equivalent
tests/test_audit_workflow_regressions.py::test_conclusion_basis_separates_documentary_context
tests/test_audit_workflow_regressions.py::test_missing_claim_or_evidence_reference_fails_closed
tests/test_audit_workflow_regressions.py::test_review_actions_update_canonical_conclusion_state
tests/test_audit_storage_regressions.py::test_complete_event_chain_rejects_historical_tampering
tests/test_audit_storage_regressions.py::test_snapshot_event_publication_recovers_after_interruption
tests/test_audit_storage_regressions.py::test_all_mutations_require_cas_and_competing_writer_loses
tests/test_audit_storage_regressions.py::test_review_replay_resolves_identity_before_stale_head
```

### Final commands

```bash
UV_CACHE_DIR=/tmp/career-evidence-uv-cache uv run --locked python scripts/run_pytest.py -q tests/test_audit_gap_e2e.py
UV_CACHE_DIR=/tmp/career-evidence-uv-cache uv run --locked python scripts/run_pytest.py -q tests/test_validation_probe_matrix.py tests/test_audit_workflow_regressions.py tests/test_audit_storage_regressions.py tests/test_audit_gap_e2e.py
UV_CACHE_DIR=/tmp/career-evidence-uv-cache uv run --locked python scripts/run_pytest.py --collect-only -q -m phase03_original_probe tests/test_audit_cli.py tests/test_audit_inspection.py tests/test_audit_policy.py tests/test_audit_attribution.py tests/test_assistance_migration.py tests/test_audit_conclusion.py tests/test_audit_store.py
UV_CACHE_DIR=/tmp/career-evidence-uv-cache uv run --locked python scripts/run_pytest.py --collect-only -q -m phase03_gap_probe tests/test_audit_workflow_regressions.py tests/test_audit_storage_regressions.py
UV_CACHE_DIR=/tmp/career-evidence-uv-cache uv run --locked python scripts/run_pytest.py -q
UV_CACHE_DIR=/tmp/career-evidence-uv-cache uv run --locked ruff check .
UV_CACHE_DIR=/tmp/career-evidence-uv-cache uv run --locked ruff format --check .
```
