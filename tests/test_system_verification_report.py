"""Public acceptance evidence contains conclusions, never private measurements."""

import json
from pathlib import Path

import pytest

REPORT = (
    Path(__file__).parents[1] / ".scratch/artifact-query-installed-2026-10-18/verification.json"
)

# Keep this reviewed contract independent of the report being checked.
ROOT_FIELDS = {
    "http_private_store_traversal_removed",
    "adopted_stage_kind_identity_filters_retained",
    "persistent_snapshot_validation_retained",
    "draft_receipt_pdf_validation_retained",
    "queries_skip_current_source_projection",
    "existing_history_retained",
    "real_applications_paused",
    "previous_installation_verified",
    "no_real_application_actions",
    "no_real_model_calls",
    "no_real_compiles",
}
GROUP_FIELDS = {
    "verification": {
        "offline_passed",
        "affected_passed",
        "packaged_passed",
        "browser_passed",
        "independent_boundary_checks_passed",
        "ruff_check_passed",
        "ruff_format_passed",
        "default_preparation_and_explicit_single_job_modes",
        "compressed_object_pdfkit",
    },
    "installed": {
        "signature_verified",
        "exact_candidate_tree_after_readback",
        "engine_matches_loaded_code",
        "complete_previous_app_retained",
        "native_config_values_and_original_bytes_retained",
        "existing_pdf_verified",
        "review_history_retained",
        "protected_static_files_unchanged",
        "application_notes_unchanged",
        "paused_processes_preserved",
    },
    "validation_script_corrections": {
        "existing_hidden_lockfiles_included_in_inventory",
        "signed_app_bytes_restored_and_verified",
        "bytecode_writes_disabled_for_final_readback",
        "generated_bytecode_quarantined_outside_app",
    },
    "report_data_boundary": {
        "original_report_preserved_privately",
        "original_report_bytes_verified",
        "private_counts_retained_outside_system",
        "source_fingerprints_retained_privately",
        "system_report_boolean_conclusions_only",
    },
}


def assert_public_report(report):
    assert type(report) is dict
    assert set(report) == ROOT_FIELDS | GROUP_FIELDS.keys(), "Unreviewed or missing report fields"
    assert all(type(report[key]) is bool for key in ROOT_FIELDS)
    for group, fields in GROUP_FIELDS.items():
        values = report[group]
        assert type(values) is dict, "Expected a verification group"
        assert set(values) == fields, "Unreviewed or missing verification fields"
        assert all(type(value) is bool for value in values.values())


def test_system_acceptance_report_contains_only_boolean_conclusions():
    assert_public_report(json.loads(REPORT.read_text()))


@pytest.mark.parametrize(
    "group",
    [None, "verification", "installed", "validation_script_corrections", "report_data_boundary"],
)
@pytest.mark.parametrize(
    "key",
    [
        "synthetic_private_count_4242",
        "synthetic_source_sha256_" + "a" * 64,
        "synthetic_personal_source_label",
        "unexpected_conclusion",
    ],
)
def test_system_acceptance_report_rejects_unreviewed_field_names(group, key):
    report = json.loads(REPORT.read_text())
    target = report if group is None else report[group]
    target[key] = True
    with pytest.raises(AssertionError):
        assert_public_report(report)


@pytest.mark.parametrize("value", [0, 1, 1.0, None, "synthetic", [], {}])
@pytest.mark.parametrize(
    "group, key", [(None, "no_real_model_calls"), ("verification", "offline_passed")]
)
def test_system_acceptance_report_rejects_non_boolean_values(group, key, value):
    report = json.loads(REPORT.read_text())
    target = report if group is None else report[group]
    target[key] = value
    with pytest.raises(AssertionError):
        assert_public_report(report)


@pytest.mark.parametrize("group", GROUP_FIELDS)
def test_system_acceptance_report_rejects_replaced_or_missing_groups(group):
    report = json.loads(REPORT.read_text())
    report[group] = True
    with pytest.raises(AssertionError):
        assert_public_report(report)
    del report[group]
    with pytest.raises(AssertionError):
        assert_public_report(report)


def test_system_acceptance_report_requires_fields_in_their_reviewed_groups():
    report = json.loads(REPORT.read_text())
    report["installed"]["offline_passed"] = report["verification"].pop("offline_passed")
    with pytest.raises(AssertionError):
        assert_public_report(report)


def test_system_acceptance_report_allows_boolean_failure_conclusions():
    report = {key: False for key in ROOT_FIELDS}
    report.update({group: dict.fromkeys(fields, False) for group, fields in GROUP_FIELDS.items()})
    assert_public_report(report)


def test_system_acceptance_report_retains_history_validation_and_pause_conclusions():
    report = json.loads(REPORT.read_text())
    for key in (
        "adopted_stage_kind_identity_filters_retained",
        "persistent_snapshot_validation_retained",
        "draft_receipt_pdf_validation_retained",
        "queries_skip_current_source_projection",
        "existing_history_retained",
        "real_applications_paused",
    ):
        assert report[key] is True
    for key in (
        "complete_previous_app_retained",
        "existing_pdf_verified",
        "review_history_retained",
        "protected_static_files_unchanged",
        "application_notes_unchanged",
        "paused_processes_preserved",
    ):
        assert report["installed"][key] is True
    for key in (
        "original_report_preserved_privately",
        "original_report_bytes_verified",
        "private_counts_retained_outside_system",
    ):
        assert report["report_data_boundary"][key] is True
