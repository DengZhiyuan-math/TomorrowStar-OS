"""Retained education remains documentary and cannot become work selection."""

import json

import pytest
from test_application_match import match_inputs as match_inputs
from test_application_match import model_output, model_runner
from test_application_source_reuse import retained_capture as retained_capture

from career_evidence_graph.application_match import analyze_job
from career_evidence_graph.application_resume import career_source_snapshot
from career_evidence_graph.career_portal_data import CareerCatalog, PortalDataError


@pytest.fixture
def retained_match_inputs(match_inputs, retained_capture):
    application, _ = match_inputs
    case = retained_capture
    root = case["catalog"].root
    (root / "sources/profile.json").write_text(
        json.dumps(
            {"name": "Synthetic Person", "location": "Zurich, Switzerland", **case["profile"]},
            indent=2,
        )
    )
    manifest = case["manifest"]
    manifest["groups"][1]["context_source_ids"] = []
    (root / "sources/retained-resume-sources.json").write_text(json.dumps(manifest))
    snapshot = career_source_snapshot(CareerCatalog(root))
    education = next(s for s in snapshot["items"] if s.get("source_kind") == "education")
    return application, snapshot, education, root


@pytest.mark.parametrize(
    "scope,selected,warning_kind",
    [
        ("documentary", False, None),
        ("documentary", True, "selection"),
        ("team", False, "attribution"),
        ("other", False, "attribution"),
    ],
)
def test_retained_education_is_not_work_material(
    retained_match_inputs, tmp_path, scope, selected, warning_kind
):
    application, snapshot, education, _root = retained_match_inputs
    output = model_output(snapshot)
    output["requirements"] = [
        output["requirements"][0]
        | {
            "text": "Documentary credential",
            "source_ids": [education["source_id"]],
            "citations": [{"source_id": education["source_id"], "quote": education["text"]}],
            "claim_scope": scope,
        }
    ]
    output["selected_source_ids"] = [education["source_id"]] if selected else []
    output["selection_rationale"] = (
        [
            {
                "source_id": education["source_id"],
                "business_relevance": "Documentary background for the role.",
                "evidence_role": "transferable",
            }
        ]
        if selected
        else []
    )
    calls = []
    directory = tmp_path / "match"
    result = analyze_job(application, snapshot, directory, runner=model_runner(output, calls))
    requirement = result["requirements"][0]
    assert result["selected_source_ids"] == []
    assert requirement["sources"][0]["attribution"] == education["attribution"]
    if warning_kind == "attribution":
        assert requirement["judgment"] == "unknown"
        assert requirement["claim_scope"] == "unknown"
        assert requirement["citation_warning"]
        assert requirement["model_explanation"] == output["requirements"][0]["explanation"]
        assert result["score"]["lower"] == 0
    else:
        assert requirement["claim_scope"] == "documentary"
        assert requirement["judgment"] == "supported"
    if selected:
        assert result["limitations"]
    saved_model = json.loads((directory / "model-result.json").read_text())
    assert saved_model["structured_result"] == output
    assert (directory / "analysis.json").exists()


@pytest.mark.parametrize("selected", [True, False])
def test_plain_resume_selection_cannot_use_education_as_a_work_item(
    retained_match_inputs, selected
):
    from career_evidence_graph.application_resume import draft_resume

    application, snapshot, education, root = retained_match_inputs
    if selected:
        with pytest.raises(PortalDataError) as error:
            draft_resume(
                application,
                CareerCatalog(root),
                source_snapshot=snapshot,
                selected_source_ids=[education["source_id"]],
            )
        assert error.value.code == "resume_source_invalid"
    else:
        application = application | {
            "job_description": "PhD in progress, Example University, Expected July 2028"
        }
        draft = draft_resume(application, CareerCatalog(root), source_snapshot=snapshot)
        assert all(item.get("source_kind") != "education" for item in draft["items"])
        assert draft["profile"]["education"] == snapshot["profile"]["education"]


def test_retained_analysis_keeps_fact_text_without_duplicate_capture_metadata(
    retained_match_inputs, tmp_path
):
    application, snapshot, education, _root = retained_match_inputs
    calls = []
    result = analyze_job(
        application,
        snapshot,
        tmp_path / "compact-match",
        runner=model_runner(model_output(snapshot), calls),
    )
    prompt = calls[-1][-1]
    payload = json.loads(prompt[prompt.index("{") :])
    source = next(s for s in payload["sources"] if s["source_id"] == education["source_id"])
    assert source["text"] == education["text"]
    assert source["documentary_only"] is True
    assert "origin_locators" not in source
    assert "supporting_sources" not in source
    assert all(
        s["source_name"] != "sources/retained-resume-sources.json" or s["locator"] != "document"
        for s in payload["sources"]
    )
    profile_education = next(
        s
        for s in payload["sources"]
        if s["source_name"] == "sources/profile.json" and s["locator"] == "profile.education[0]"
    )
    profile_entry = snapshot["profile"]["education"][0]
    assert profile_education["text"].splitlines() == [
        profile_entry[key] for key in ("degree", "institution", "period", "detail")
    ]
    profile_location = next(s for s in payload["sources"] if s["locator"] == "profile.location")
    assert profile_location["text"] == snapshot["profile"]["location"]
    assert profile_location["documentary_only"] is True
    assert all(s["locator"] != "document" for s in payload["sources"])
    assert result["coverage"]["truncated"] is False


def test_whole_profile_skill_inventory_is_not_an_ambiguous_match_source(
    retained_match_inputs, tmp_path
):
    application, _snapshot, _education, root = retained_match_inputs
    profile_path = root / "sources/profile.json"
    profile = json.loads(profile_path.read_text())
    profile["skills"] = [f"Documentary synthetic keyword {index:04d}" for index in range(3000)]
    profile_path.write_text(json.dumps(profile))
    snapshot = career_source_snapshot(CareerCatalog(root))
    calls = []
    result = analyze_job(
        application,
        snapshot,
        tmp_path / "full-context",
        runner=model_runner(model_output(snapshot), calls),
    )
    prompt = calls[-1][-1]
    payload = json.loads(prompt[prompt.index("{") :])
    assert all(s["locator"] != "document" for s in payload["sources"])
    assert "Documentary synthetic keyword 0000" not in prompt
    assert "Documentary synthetic keyword 2999" not in prompt
    assert any(s["locator"] == "profile.education[0]" for s in payload["sources"])
    assert result["coverage"]["truncated"] is False
    assert result["coverage"]["omitted_source_ids"] == []
    assert result["coverage"]["truncated_sources"] == []
