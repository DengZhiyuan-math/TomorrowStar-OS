from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parents[1]
PYTEST_RUNNER = ROOT / "scripts" / "run_pytest.py"
ORIGINAL_FILES = (
    "tests/test_audit_cli.py",
    "tests/test_audit_inspection.py",
    "tests/test_audit_policy.py",
    "tests/test_audit_attribution.py",
    "tests/test_assistance_migration.py",
    "tests/test_audit_conclusion.py",
    "tests/test_audit_store.py",
)
GAP_FILES = (
    "tests/test_audit_workflow_regressions.py",
    "tests/test_audit_storage_regressions.py",
    "tests/test_audit_conclusion.py",
    "tests/test_audit_cli.py",
    "tests/test_audit_attribution.py",
)
ORIGINAL_NODE_IDS = (
    "tests/test_audit_cli.py::test_start_does_not_overwrite_existing_audit",
    "tests/test_audit_cli.py::test_audit_creation_is_atomic_under_competition",
    "tests/test_audit_inspection.py::test_inspection_order_is_stable",
    "tests/test_audit_inspection.py::test_inspection_preserves_duplicate_source_locators",
    "tests/test_audit_inspection.py::test_inspection_rejects_missing_contribution",
    "tests/test_audit_inspection.py::test_inspection_rejects_empty_linked_evidence",
    "tests/test_audit_inspection.py::test_inspection_rejects_unverified_manifest",
    "tests/test_audit_policy.py::test_transition_has_exactly_one_active_question",
    "tests/test_audit_policy.py::test_only_one_same_level_followup",
    "tests/test_audit_policy.py::test_second_incomplete_answer_descends",
    "tests/test_audit_policy.py::test_dont_know_descends_without_penalty",
    "tests/test_audit_policy.py::test_blank_answer_fails_closed",
    "tests/test_audit_policy.py::test_duplicate_action_is_idempotent",
    "tests/test_audit_policy.py::test_stale_expected_hash_rejects_lost_update",
    "tests/test_audit_policy.py::test_resume_returns_next_unanswered_question",
    "tests/test_audit_policy.py::test_exhausted_or_irrelevant_area_emits_no_question",
    "tests/test_audit_policy.py::test_unicode_answer_and_reason_round_trip_exactly",
    "tests/test_audit_policy.py::test_fixture_ladder_is_hard_to_simple_and_stable",
    "tests/test_audit_attribution.py::test_ownership_precedes_assistance",
    "tests/test_audit_attribution.py::test_assistance_never_fills_ownership",
    "tests/test_audit_attribution.py::test_attribution_values_round_trip_distinctly",
    "tests/test_audit_attribution.py::test_conflict_preserves_documentary_and_user_claims",
    "tests/test_assistance_migration.py::test_legacy_codex_assisted_reads_and_new_write_is_canonical",
    "tests/test_audit_conclusion.py::test_incomplete_coverage_blocks_conclusion",
    "tests/test_audit_conclusion.py::test_conclusion_order_and_unicode_are_stable",
    "tests/test_audit_conclusion.py::test_review_preserves_original_and_emits_no_verified_numeric_score",
    "tests/test_audit_conclusion.py::test_duplicate_terminal_review_is_idempotent",
    "tests/test_audit_store.py::test_stale_or_tampered_review_fails_closed",
)
GAP_NODE_IDS = (
    "tests/test_audit_workflow_regressions.py::test_paused_and_terminal_lifecycle_actions_fail_closed",
    "tests/test_audit_workflow_regressions.py::test_supported_english_and_chinese_attribution_are_equivalent",
    "tests/test_audit_workflow_regressions.py::test_conclusion_basis_separates_documentary_context",
    "tests/test_audit_workflow_regressions.py::test_missing_claim_or_evidence_reference_fails_closed",
    "tests/test_audit_workflow_regressions.py::test_review_actions_update_canonical_conclusion_state",
    "tests/test_audit_workflow_regressions.py::test_wrong_question_target_rejects_before_audit_workspace_write",
    "tests/test_audit_storage_regressions.py::test_complete_event_chain_rejects_historical_tampering",
    "tests/test_audit_storage_regressions.py::test_symlinked_audit_root_rejects_before_external_writes",
    "tests/test_audit_storage_regressions.py::test_snapshot_event_publication_recovers_after_interruption",
    "tests/test_audit_storage_regressions.py::test_all_mutations_require_cas_and_competing_writer_loses",
    "tests/test_audit_storage_regressions.py::test_direct_update_requires_caller_held_head_and_rejects_stale_snapshot",
    "tests/test_audit_storage_regressions.py::test_review_replay_resolves_identity_before_stale_head",
    "tests/test_audit_conclusion.py::test_direct_reviews_require_current_effective_conclusion_hash",
    "tests/test_audit_cli.py::test_malformed_audit_action_has_json_diagnostic_and_no_workspace_writes",
    "tests/test_audit_attribution.py::test_bilingual_ambiguous_attribution_persists_as_unresolved_conclusion",
)
NODE_ID = re.compile(r"^tests/[a-z0-9_]+\.py::test_[a-z0-9_]+$")


def _collect(marker: str, files: tuple[str, ...]) -> tuple[str, ...]:
    completed = subprocess.run(
        [sys.executable, str(PYTEST_RUNNER), "--collect-only", "-q", "-m", marker, *files],
        cwd=ROOT,
        env=os.environ | {"UV_CACHE_DIR": "/tmp/career-evidence-uv-cache"},
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr
    node_ids = tuple(line for line in completed.stdout.splitlines() if NODE_ID.fullmatch(line))
    assert node_ids, completed.stdout
    assert len(node_ids) == len(set(node_ids)), node_ids
    assert all("[" not in node_id for node_id in node_ids)
    return node_ids


def test_all_28_original_and_fifteen_gap_probes_are_collected() -> None:
    assert _collect("phase03_original_probe", ORIGINAL_FILES) == ORIGINAL_NODE_IDS
    assert _collect("phase03_gap_probe", GAP_FILES) == GAP_NODE_IDS
