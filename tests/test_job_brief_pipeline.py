"""The fixed JD framework survives ordinary retrieval, qualification and refresh."""

from copy import deepcopy

import pytest
from test_application_job_brief import runner_for
from test_application_match import model_runner
from test_canonical_career_sources import canonical as canonical
from test_normal_retrieval_pipeline import APPLICATION, RecordedPipeline, requirement, thin

from career_evidence_graph.application_explanations import qualification_for
from career_evidence_graph.application_flow import analysis_input_binding, task_eligibility
from career_evidence_graph.application_job_brief import brief_requirements, create_job_brief
from career_evidence_graph.application_match import analyze_job
from career_evidence_graph.application_match_refresh import _requirements
from career_evidence_graph.application_worker import digest
from career_evidence_graph.career_portal_data import PortalDataError

pytestmark = pytest.mark.usefixtures("planner_path")


def test_brief_is_published_before_source_reads_and_reused_for_every_followup(canonical, tmp_path):
    library, _, _, base, *_ = canonical
    runner = RecordedPipeline(
        [requirement("Interdisciplinary research")], select=False, followup_select=True
    )
    directory = tmp_path / "analysis"

    def load(ids):
        assert len(runner.brief_calls) == 1
        assert (directory / "job-brief/job-brief.json").is_file()
        return library.snapshot_for_analysis(base, ids)

    report = analyze_job(
        APPLICATION,
        thin(canonical),
        directory,
        runner=runner,
        source_loader=load,
        information_library={"status": "unconfigured"},
    )
    assert len(runner.brief_calls) == 1
    assert set(runner.brief_calls[0]) == {"company", "role_title", "location", "job_description"}
    # Matching reads the brief without the JD copy and revisions the program keeps.
    shared = {"business_object", "role_understanding", "groups"}
    assert all(
        {key: context["job_brief"][key] for key in shared}
        == {key: report["job_brief"][key] for key in shared}
        for context in runner.contexts
    )
    assert _requirements(report) == brief_requirements(report["job_brief"])

    refreshed = RecordedPipeline(runner.requirements)
    result = analyze_job(
        APPLICATION,
        thin(canonical),
        tmp_path / "refresh",
        runner=refreshed,
        source_loader=lambda ids: library.snapshot_for_analysis(base, ids),
        information_library={"status": "unconfigured"},
        requirements=_requirements(report),
        job_brief=report["job_brief"],
        matching_only=True,
    )
    assert refreshed.brief_calls == []
    assert result["job_brief"] == report["job_brief"]


@pytest.mark.parametrize("change", ["goal", "requirement", "weight"])
def test_evaluator_cannot_reinterpret_fixed_inputs(canonical, tmp_path, change):
    library, _, _, base, *_ = canonical
    original = RecordedPipeline([requirement("Interdisciplinary research")])

    def runner(config, prompt, **kwargs):
        result = original(config, prompt, **kwargs)
        if original.phases and original.phases[-1] == "evaluate":
            output = deepcopy(result.structured_result)
            if change == "goal":
                output["role_understanding"]["business_objective"] = "Invented profitability target"
            elif change == "requirement":
                output["requirements"][0]["text"] = "Unstated live trading requirement"
            else:
                output["requirements"][0]["scoring_framework"] = {"weight": 100}
            return model_runner(output, [])(config, prompt, **kwargs)
        return result

    with pytest.raises(PortalDataError) as error:
        analyze_job(
            APPLICATION,
            thin(canonical),
            tmp_path / change,
            runner=runner,
            source_loader=lambda ids: library.snapshot_for_analysis(base, ids),
            information_library={"status": "unconfigured"},
        )
    assert error.value.code == "match_model_invalid"


def hard_task(tmp_path, *, operator="any", alternatives=None, judgments=None):
    job = {"job_description": "Python or C++ required. SQL also required."}
    names = ["Python", "C++"] if alternatives is None else ["Python", "C++", "SQL"]
    output = {
        "business_object": "Implementation work",
        "role_understanding": {
            "business_objective": "Deliver implementation work",
            "work_outputs": ["Working code"],
            "methods_role": "Programming",
        },
        "groups": [
            {
                "label": "Programming alternatives",
                "jd_quote": job["job_description"],
                "operator": operator,
                "alternatives": alternatives,
                "importance": "required",
                "hard_condition": True,
                "weight": 100,
                "weight_reason": "Only stated qualification group",
                "requirements": [{"text": name, "jd_quote": name} for name in names],
            }
        ],
    }
    brief = create_job_brief(job, tmp_path / "brief", runner=runner_for(output))
    rows = [
        row | {"judgment": status, "explanation": "Saved synthetic fact"}
        for row, status in zip(
            brief_requirements(brief), judgments or ["supported", "gap"], strict=True
        )
    ]
    report = {
        "id": "analysis",
        "job_brief": brief,
        "requirements": rows,
        "application_library_policy": "trusted-library/v1",
        "retrieval": {"status": "read"},
    }
    task = {
        "analysis_id": "analysis",
        "inputs": {},
        "artifacts": [{"stage": "analysis", "adopted": True, "result": report}],
        "hard_condition_resolutions": [],
    }
    return task, job, report


@pytest.mark.parametrize("operator,expected", [("any", "supported"), ("all", "conflict")])
def test_flow_and_explanation_preserve_any_vs_all_qualification(tmp_path, operator, expected):
    task, job, _ = hard_task(tmp_path, operator=operator)
    assert task_eligibility(task)["status"] == expected
    result = qualification_for(task, job)
    assert result["status"] == expected
    assert [condition["status"] for condition in result["conditions"]] == ["supported", "conflict"]
    if operator == "any":
        assert "暂停" not in result["conditions"][1]["explanation"]


def test_nested_qualification_requires_sql_in_either_language_branch(tmp_path):
    task, job, _ = hard_task(
        tmp_path, alternatives=[[0, 2], [1, 2]], judgments=["supported", "gap", "unknown"]
    )
    assert task_eligibility(task)["status"] == "needs_input"
    assert qualification_for(task, job)["status"] == "needs_input"
    task["hard_condition_resolutions"] = [
        {
            "analysis_id": "analysis",
            "requirement_index": 2,
            "confirmed": True,
            "verified_by": "user",
            "eligible": True,
            "source": "Explicit saved fact",
            "analysis_input_revision": digest(analysis_input_binding(task["inputs"])),
        }
    ]
    assert task_eligibility(task, bind_inputs=True)["status"] == "supported"
    assert qualification_for(task, job)["status"] == "supported"


def test_effective_explanation_uses_current_child_facts_without_mutating_history(tmp_path):
    task, job, original = hard_task(tmp_path)
    current = deepcopy(original)
    current["requirements"][0]["judgment"] = "unknown"
    assert qualification_for(task, job, analysis=current)["status"] == "needs_input"
    assert task_eligibility(task)["status"] == "supported"
