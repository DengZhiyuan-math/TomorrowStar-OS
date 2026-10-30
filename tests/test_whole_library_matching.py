"""A library that fits one matching call is matched whole, without directory selection."""

import json

import pytest
from test_canonical_career_sources import canonical as canonical
from test_normal_retrieval_pipeline import APPLICATION, RecordedPipeline, requirement, thin

from career_evidence_graph.application_match import analyze_job
from career_evidence_graph.application_material_sources import matching_view
from career_evidence_graph.career_portal_data import PortalDataError


def test_a_library_that_fits_is_matched_in_one_call_with_every_experience(canonical, tmp_path):
    library, _, _, base, *_ = canonical
    snapshot = thin(canonical)
    runner = RecordedPipeline([requirement("Scientific collaboration")])
    result = analyze_job(
        APPLICATION,
        snapshot,
        tmp_path / "whole",
        runner=runner,
        source_loader=lambda ids: library.snapshot_for_analysis(base, ids),
        information_library={"status": "unconfigured"},
    )
    # Installed MC-11: ten serial selection and reading calls took 141 seconds
    # before one evaluation; the whole library answered in one 31-second call.
    assert runner.phases == ["evaluate"] and runner.read_calls == []
    every = [row["candidate_id"] for row in snapshot["career_library"]["records"]]
    assert result["retrieval"]["selected_candidate_ids"] == every
    assert result["retrieval"]["plans"][0]["policy_version"] == "whole-library/v1"


def test_a_library_over_the_budget_still_selects_from_the_directory(
    canonical, tmp_path, monkeypatch
):
    library, _, _, base, *_ = canonical
    monkeypatch.setenv("TOMORROWSTAR_MATCH_CONTEXT_BYTES", "128000")
    monkeypatch.setenv("TOMORROWSTAR_MATERIAL_CONTEXT_BYTES", "200")
    runner = RecordedPipeline([requirement("Scientific collaboration")])
    with pytest.raises(PortalDataError) as refused:
        analyze_job(
            APPLICATION,
            thin(canonical),
            tmp_path / "planned",
            runner=runner,
            source_loader=lambda ids: library.snapshot_for_analysis(base, ids),
            information_library={"status": "unconfigured"},
        )
    # Directory selection ran first; this tiny budget then refuses the selected sources.
    assert runner.phases == ["plan"]
    assert refused.value.code == "retrieval_execution_incomplete"


def test_matching_view_states_each_experience_once_and_keeps_background_apart():
    rows = [
        {
            "source_id": f"S{index}",
            "text": text,
            "application_trusted": True,
            "record_context": {
                "experience_id": "e1",
                "candidate_id": "e1",
                "content_revision": "r",
                "experience_revision": "r",
                "fact_id": f"f{index}",
                "source_refs": ["s"],
                "sources": [{"id": "s", "locator": "notes"}],
                "title": "Platform",
                "role": "Co-founder",
                "organization": None,
                "responsibility": responsibility,
                "status": "completed",
                "scope": scope,
            },
        }
        for index, (text, responsibility, scope) in enumerate(
            [
                ("Led delivery.", "team", "Recorded experience fact."),
                ("Website describes FastAPI.", "third_party", "Website text only."),
            ],
            1,
        )
    ]
    view = matching_view(rows)
    assert view["sources"] == []
    assert view["experiences"] == [
        {
            "title": "Platform",
            "role": "Co-founder",
            "facts": [
                {
                    "source_id": "S1",
                    "responsibility": "team",
                    "status": "completed",
                    "text": "Led delivery.",
                }
            ],
            "context": [
                {
                    "source_id": "S2",
                    "status": "completed",
                    "text": "Website describes FastAPI.",
                    "note": 1,
                }
            ],
            "notes": ["Website text only."],
        }
    ]
    assert json.dumps(view).count("Co-founder") == 1


def test_source_handles_are_numbered_in_reading_order(canonical, tmp_path):
    import re

    library, _, _, base, *_ = canonical
    runner = RecordedPipeline([requirement("Scientific collaboration")])
    analyze_job(
        APPLICATION,
        thin(canonical),
        tmp_path / "ordered",
        runner=runner,
        source_loader=lambda ids: library.snapshot_for_analysis(base, ids),
        information_library={"status": "unconfigured"},
    )
    attempt = next((tmp_path / "ordered").glob("evaluation-*"))
    prompt = json.loads((attempt / "context-input.json").read_text())["prompt"]
    handles = [int(number) for number in re.findall(r'"source_id":"S([0-9]+)"', prompt)]
    # Installed MC-11: scattered handles led the model to cite one fact's text
    # under another fact's handle.
    assert handles == list(range(1, len(handles) + 1))
