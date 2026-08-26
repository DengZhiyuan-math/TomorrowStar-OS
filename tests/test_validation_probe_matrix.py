from __future__ import annotations

import re
from pathlib import Path

MATRIX = (
    Path(__file__).parents[1]
    / ".planning/phases/03-artifact-aware-grill-me-and-attribution-workflow/03-VALIDATION.md"
)

EXPECTED = {
    "test_inspection_preserves_duplicate_source_locators",
    "test_inspection_rejects_missing_contribution",
    "test_inspection_rejects_empty_linked_evidence",
    "test_inspection_rejects_unverified_manifest",
    "test_inspection_order_is_stable",
    "test_start_does_not_overwrite_existing_audit",
    "test_audit_creation_is_atomic_under_competition",
    "test_transition_has_exactly_one_active_question",
    "test_blank_answer_fails_closed",
    "test_duplicate_action_is_idempotent",
    "test_stale_expected_hash_rejects_lost_update",
    "test_resume_returns_next_unanswered_question",
    "test_only_one_same_level_followup",
    "test_second_incomplete_answer_descends",
    "test_dont_know_descends_without_penalty",
    "test_exhausted_or_irrelevant_area_emits_no_question",
    "test_unicode_answer_and_reason_round_trip_exactly",
    "test_fixture_ladder_is_hard_to_simple_and_stable",
    "test_ownership_precedes_assistance",
    "test_assistance_never_fills_ownership",
    "test_attribution_values_round_trip_distinctly",
    "test_conflict_preserves_documentary_and_user_claims",
    "test_legacy_codex_assisted_reads_and_new_write_is_canonical",
    "test_incomplete_coverage_blocks_conclusion",
    "test_conclusion_order_and_unicode_are_stable",
    "test_duplicate_terminal_review_is_idempotent",
    "test_stale_or_tampered_review_fails_closed",
    "test_review_preserves_original_and_emits_no_verified_numeric_score",
}


def test_all_28_edge_probes_are_collected() -> None:
    text = MATRIX.read_text(encoding="utf-8")
    collected = set(re.findall(r"`(test_[a-z0-9_]+)`", text))
    assert len(collected) == 28
    assert collected == EXPECTED
