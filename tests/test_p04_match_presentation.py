"""Saved business explanations keep background, reading and writing coverage separate."""

from copy import deepcopy

import pytest
from test_application_job_brief import application as application
from test_application_job_brief import output as output
from test_application_job_brief import runner_for
from test_job_explanations import job_and_task, requirement

from career_evidence_graph.application_explanations import job_explanation
from career_evidence_graph.application_job_brief import brief_requirements, create_job_brief


def saved_case(tmp_path, application, output, *, unknown=False):
    brief = create_job_brief(
        application, tmp_path / "brief", runner=runner_for(output), environment={}
    )
    rows = brief_requirements(brief)
    for index, row in enumerate(rows):
        row.update(
            judgment="unknown" if unknown and index == 1 else "supported",
            explanation=f"Recorded business basis {index}.",
            sources=[{"source_id": "source:a" if index % 2 == 0 else "source:b"}],
        )
    app, task = job_and_task(rows)
    analysis = task["artifacts"][0]["result"]
    analysis.update(
        job_brief=brief,
        selected_source_ids=["source:a", "source:b"],
        material_packet={
            "status": "complete",
            "sources": {"source:a": {}, "source:b": {}},
            "source_reads": {
                sid: {
                    "status": "complete",
                    "original_chars": 6,
                    "ranges": [
                        {"start": 0, "end": 4, "method": "excerpt_read"},
                        {"start": 3, "end": 6, "method": "excerpt_read"},
                    ],
                }
                for sid in ("source:a", "source:b")
            },
        },
    )
    return app, task


def explain(app, task):
    return job_explanation(app, task, current_inputs=task["inputs"])


@pytest.mark.parametrize("unknown", [False, True])
def test_fixed_profile_has_one_score_presentation_and_business_bases(
    tmp_path, application, output, unknown
):
    app, task = saved_case(tmp_path, application, output, unknown=unknown)
    before = deepcopy(task)
    result = explain(app, task)
    score = result["match_score"]
    assert score["kind"] == ("interval" if unknown else "single")
    assert score["display"] == ("60–100/100" if unknown else "100/100")
    assert result["score_coverage_label"] == "分数确定度"
    business = result["business_summary"]
    assert business["business_objective"] == output["role_understanding"]["business_objective"]
    assert business["work_outputs"] == output["role_understanding"]["work_outputs"]
    assert business["groups"][0]["label"] == "Business"
    assert "Recorded business basis 0." in business["groups"][0]["supported"]
    if unknown:
        assert business["groups"][0]["concerns"] == [
            {"judgment": "unknown", "basis": "Recorded business basis 1."}
        ]
    assert result["resume_coverage"]["status"] == "not_generated"
    assert task == before
    assert explain(app, task) == result


@pytest.mark.parametrize("change", ["packet", "source", "range_gap", "range_type", "missing"])
def test_read_coverage_tracks_packet_and_ranges_without_changing_background_score(
    tmp_path, application, output, change
):
    app, task = saved_case(tmp_path, application, output)
    before = explain(app, task)
    assert before["material_read_coverage"] == {
        "status": "complete",
        "complete": True,
        "sources_total": 2,
        "sources_complete": 2,
        "ranges_total": 4,
        "ranges_complete": 4,
    }
    packet = task["artifacts"][0]["result"]["material_packet"]
    if change == "packet":
        packet["status"] = "reading"
    elif change == "source":
        packet["source_reads"]["source:a"]["status"] = "reading"
    elif change == "missing":
        del packet["source_reads"]["source:a"]
    else:
        packet["source_reads"]["source:a"]["ranges"][1][
            "start" if change == "range_gap" else "method"
        ] = 5 if change == "range_gap" else "unknown_method"
    result = explain(app, task)
    assert not result["material_read_coverage"]["complete"]
    assert result["score"] == before["score"]
    assert result["match_score"] == before["match_score"]


def test_resume_coverage_uses_actual_current_material_and_ignores_selection_order(
    tmp_path, application, output
):
    app, task = saved_case(tmp_path, application, output)
    score = explain(app, task)["score"]
    task["draft_id"] = "draft-current"
    task["artifacts"].extend(
        [
            {
                "stage": "resume",
                "adopted": True,
                "result": {"id": "old-draft", "used_source_ids": ["source:a", "source:b"]},
            },
            {
                "stage": "resume",
                "adopted": True,
                "result": {"id": "draft-current", "selected_source_ids": ["source:b"]},
            },
        ]
    )
    assert explain(app, task)["resume_coverage"]["status"] == "unavailable"
    task["artifacts"][-1]["result"]["used_source_ids"] = ["source:a"]
    result = explain(app, task)
    assert result["resume_coverage"] == {
        "status": "generated",
        "requirements_total": 4,
        "requirements_used": 2,
        "percent": 50,
        "used_source_ids": ["source:a"],
    }
    assert result["score"] == score
    task["artifacts"][0]["result"]["selected_source_ids"] = ["source:b", "source:a"]
    assert explain(app, task)["resume_coverage"] == result["resume_coverage"]
    task["artifacts"][-1]["result"]["used_source_ids"] = []
    result = explain(app, task)
    assert result["resume_coverage"]["percent"] == 0
    assert result["score"] == score


def test_legacy_explanation_does_not_invent_new_inference_or_coverage():
    app, task = job_and_task([requirement()])
    result = explain(app, task)
    assert "business_summary" not in result
    assert "material_read_coverage" not in result
    assert "resume_coverage" not in result
    assert "inference" not in result["reasons"][0]


def test_inference_details_and_short_basis_are_preserved_without_new_evaluation(
    tmp_path, application, output
):
    app, task = saved_case(tmp_path, application, output)
    inference = {
        "requirement_id": "synthetic-requirement",
        "type": "semantic",
        "relation": "supports",
        "basis": "Implemented a pricing research workflow with a collaborator.",
        "expression_scope": "Research collaboration; no live-trading responsibility.",
        "calculation": None,
        "facts": [{"source_id": "source:a", "locator": "contributions", "revision": "v1"}],
    }
    task["artifacts"][0]["result"]["requirements"][0]["inference"] = inference
    before = deepcopy(task)
    result = explain(app, task)
    assert result["reasons"][0]["inference"] == inference
    assert inference["basis"] in result["business_summary"]["groups"][0]["supported"]
    result["reasons"][0]["inference"]["facts"][0]["revision"] = "changed-client-copy"
    assert task == before


def test_satisfied_or_group_has_certain_score_with_an_unresolved_alternative(
    tmp_path, application, output
):
    app, task = saved_case(tmp_path, application, output)
    requirements = task["artifacts"][0]["result"]["requirements"]
    assert requirements[2]["scoring_framework"]["group"]["operator"] == "any"
    assert requirements[2]["judgment"] == "supported"
    requirements[3]["judgment"] = "unknown"
    result = explain(app, task)
    assert result["score"]["coverage"] == 100
    assert result["match_score"] == {
        "kind": "single",
        "lower": 100,
        "upper": 100,
        "display": "100/100",
    }
    assert result["score_coverage_label"] == "分数确定度"
    assert result["reasons"][3]["judgment"] == "unknown"
    assert result["business_summary"]["groups"][1]["concerns"][0]["judgment"] == "unknown"
