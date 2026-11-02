"""Input binding Module: (stage, saved, current) decides reusable, stale or rebind."""

import pytest

from career_evidence_graph.application_input_binding import (
    configuration_revision,
    reusable,
    same_configuration,
    task_binding,
)
from career_evidence_graph.validation.hashing import record_digest as digest

BUSINESS = {
    "policy_version": "documentary-match/v1",
    "prompt_version": "documentary-match-prompt/v6",
    "output_schema_sha256": "a" * 64,
    "requested_model": "synthetic-model",
    "reasoning_effort": "medium",
}
PROVENANCE = {
    "engine_sha256": "1" * 64,
    "retrieval_engine_sha256": "2" * 64,
    "retrieval_component_sha256": {"application_retrieval": "3" * 64},
    "executable": "codex",
    "resolved_executable": "/synthetic/bin/codex",
    "executable_status": "available",
    "executable_metadata_revision": digest({"mtime_ns": 1, "inode": 7}),
    "immutable_snapshot": None,
}
RESUME = {
    "engine_sha256": "4" * 64,
    "draft_engine_sha256": "5" * 64,
    "requested_profile": {"requested_model": "synthetic-model"},
    "cli_identity": {"resolved_executable": "/synthetic/bin/codex"},
    "tailorer": "codex",
}


def inputs(**overrides):
    base = {
        "jd_revision": "j" * 64,
        "sources_revision": "s" * 64,
        "information_library_revision": "i" * 64,
        "historical_benchmark_revision": "b" * 64,
        "analysis_configuration_revision": configuration_revision(BUSINESS),
        "resume_configuration_revision": configuration_revision(RESUME),
    }
    return base | overrides


@pytest.mark.parametrize(
    "provenance",
    [
        {"engine_sha256": "9" * 64},
        {"retrieval_component_sha256": {"application_retrieval": "8" * 64}},
        {"executable_metadata_revision": digest({"mtime_ns": 2, "inode": 7})},
        {"resolved_executable": "/synthetic/other/codex"},
    ],
)
def test_engine_bytes_or_codex_executable_change_keeps_revision(provenance):
    before = BUSINESS | PROVENANCE
    after = before | provenance
    assert configuration_revision(before) == configuration_revision(after)
    assert same_configuration(before, after)
    saved = inputs(analysis_configuration_revision=configuration_revision(before))
    current = inputs(analysis_configuration_revision=configuration_revision(after))
    for stage in ("analysis", "resume", "export", "readiness"):
        assert reusable(stage, saved, current).reusable


def test_resume_engine_and_cli_identity_are_provenance():
    changed = RESUME | {
        "draft_engine_sha256": "6" * 64,
        "cli_identity": {"resolved_executable": "x"},
    }
    assert configuration_revision(changed) == configuration_revision(RESUME)
    assert configuration_revision(RESUME | {"tailorer": "other"}) != configuration_revision(RESUME)


@pytest.mark.parametrize(
    "business",
    [{"prompt_version": "documentary-match-prompt/v7"}, {"output_schema_sha256": "b" * 64}],
)
def test_prompt_or_schema_change_is_stale(business):
    saved = inputs()
    current = inputs(analysis_configuration_revision=configuration_revision(BUSINESS | business))
    result = reusable("analysis", saved, current)
    assert result.stale
    assert result.changed == ("analysis_configuration_revision",)


def test_legacy_revision_asks_for_rebind_not_stale():
    legacy = digest(BUSINESS | PROVENANCE)
    result = reusable("analysis", inputs(analysis_configuration_revision=legacy), inputs())
    assert not result.stale
    assert result.status == "rebind"
    assert result.rebind == ("analysis_configuration_revision",)


def test_legacy_revision_with_a_real_change_is_stale_and_names_both():
    saved = inputs(analysis_configuration_revision=digest(BUSINESS), jd_revision="0" * 64)
    result = reusable("analysis", saved, inputs())
    assert result.stale
    assert result.changed == ("jd_revision",)
    assert result.rebind == ("analysis_configuration_revision",)


def test_analysis_ignores_material_only_inputs():
    current = inputs(resume_configuration_revision=configuration_revision({"tailorer": "x"}))
    assert reusable("analysis", inputs(), current).reusable
    assert reusable("resume", inputs(), current).stale


def test_imported_latex_owns_its_generator_setting():
    current = inputs(resume_configuration_revision=configuration_revision({"tailorer": "x"}))
    assert reusable("export", inputs(), current, origin="existing_latex").reusable


def _task(saved, *, origin=None, completed=()):
    return {
        "inputs": saved,
        "origin": origin,
        "stages": {name: {"status": "complete"} for name in completed},
    }


def test_retained_task_keeps_legacy_revision_for_saved_receipts():
    legacy = digest(RESUME | {"cli_identity": {"resolved_executable": "old"}})
    task = _task(inputs(resume_configuration_revision=legacy), completed=("analysis",))
    binding = task_binding(task, inputs(), stage="materials")
    assert binding.reusable


@pytest.mark.parametrize("preparation_only", [False, True])
def test_readiness_and_flow_ask_the_same_question(preparation_only):
    """Readiness used to miss the imported-LaTeX rule that Flow applied."""
    current = inputs(resume_configuration_revision=configuration_revision({"tailorer": "x"}))
    task = _task(inputs(), origin="existing_latex", completed=("analysis",))
    flow = task_binding(task, current, stage="materials", preparation_only=preparation_only)
    readiness = task_binding(task, current, stage="readiness", preparation_only=preparation_only)
    assert flow == readiness
    assert flow.stale is not preparation_only


def test_unknown_stage_is_rejected():
    with pytest.raises(ValueError):
        reusable("worker", inputs(), inputs())
