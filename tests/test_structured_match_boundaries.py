"""Application trust preserves the actual source's responsibility restrictions."""

import json

import pytest
from test_application_information import library_with
from test_application_match import match_inputs as match_inputs
from test_application_match import model_output, model_runner
from test_canonical_career_sources import canonical as canonical
from test_normal_retrieval_pipeline import APPLICATION, RecordedPipeline, requirement, thin

from career_evidence_graph.application_match import analyze_job
from career_evidence_graph.application_worker import digest
from career_evidence_graph.career_portal_data import PortalDataError


def test_normal_matching_retains_original_source_boundaries(canonical, tmp_path):
    library, _, _, base, *_ = canonical
    expected = {
        item["source_id"]: item["boundaries"]
        for item in library.snapshot_for_analysis(base, ["unseen-identity"])["items"]
    }
    runner = RecordedPipeline([requirement("Work across scientific domains")])
    analyze_job(
        APPLICATION,
        thin(canonical),
        tmp_path / "matching",
        runner=runner,
        source_loader=lambda ids: library.snapshot_for_analysis(base, ids),
        information_library=library_with(),
    )
    context = next(row for row in runner.contexts if "match_requirements" in row)
    supplied = [row for row in context["sources"] if row["source_id"] in expected]
    assert supplied
    assert all(row["boundaries"] == expected[row["source_id"]] for row in supplied)


def test_trusted_fact_cannot_become_a_personal_ownership_claim(match_inputs, tmp_path):
    application, snapshot = match_inputs
    snapshot["items"][0].update(
        attribution="Third party",
        resume_eligible=False,
        rewrite_allowed=False,
    )
    snapshot["application_library_policy"] = "trusted-library/v1"
    snapshot["revision"] = digest(
        {key: value for key, value in snapshot.items() if key != "revision"}
    )
    output = model_output(snapshot)
    output["selected_source_ids"] = []
    output["selection_rationale"] = []
    original_runner = model_runner(output, [])

    def runner(config, prompt, **kwargs):
        schema = json.loads(config.output_schema.read_text())
        scopes = [
            definition["properties"]["claim_scope"]["enum"]
            for definition in schema["$defs"].values()
            if "claim_scope" in definition.get("properties", {})
        ]
        assert scopes and all(values == ["documentary", "unknown"] for values in scopes)
        return original_runner(config, prompt, **kwargs)

    with pytest.raises(PortalDataError) as error:
        analyze_job(application, snapshot, tmp_path / "ownership", runner=runner)
    assert error.value.code == "match_model_invalid"
    assert not (tmp_path / "ownership/analysis.json").exists()
