"""Present fixed P04 output without retrieving or reassessing its evidence."""

from copy import deepcopy

import pytest
from test_application_flow import application as application
from test_application_flow import wait_for
from test_job_explanations import job_and_task, requirement

from career_evidence_graph.application_explanations import job_explanation
from career_evidence_graph.application_flow import ApplicationFlowService, task_eligibility
from career_evidence_graph.application_match import calculate_match_score


def test_fixed_explanation_consumes_delivered_judgments_without_live_source_reads():
    application, task = job_and_task([requirement("Fluent English", hard=True)])
    analysis = task["artifacts"][0]["result"]
    analysis.update(
        application_id=application["id"],
        application_library_policy="trusted-library/v1",
        retrieval={"selected_candidate_ids": []},
        job_brief={},
        material_packet={},
        inference_result={},
    )
    analysis["score"] = calculate_match_score(analysis["requirements"])
    before = deepcopy(task)

    def unavailable_sources(*args):
        raise AssertionError("A view must consume the fixed delivery, not read career facts")

    view = job_explanation(
        application,
        task,
        current_inputs=task["inputs"],
        library={"status": "unavailable"},
        source_provider=unavailable_sources,
        fixed_delivery=True,
    )
    assert view["reasons"] == analysis["requirements"]
    assert view["qualification"]["status"] == "supported"
    assert view["score"] == analysis["score"]
    assert view["match_recheck_stale"] is False
    assert view["factual_rechecks"] == []
    assert task == before


def test_fixed_explanation_rescores_saved_verdicts_with_the_current_rule():
    application, task = job_and_task(
        [requirement("Python"), requirement("Embedded Linux", judgment="partial")]
    )
    analysis = task["artifacts"][0]["result"]
    analysis.update(
        retrieval={"selected_candidate_ids": []}, application_library_policy="trusted-library/v1"
    )
    # Installed MC-11: a score saved under the old partial rule kept showing 14-94.
    analysis["score"] = {"lower": 50, "upper": 100, "coverage": 50, "eligibility": "not_specified"}
    view = job_explanation(application, task, current_inputs=task["inputs"], fixed_delivery=True)
    assert view["score"] == calculate_match_score(analysis["requirements"])
    assert (view["score"]["lower"], view["score"]["upper"]) == (75, 75)


@pytest.mark.parametrize(
    ("judgment", "expected"), [("unknown", "needs_input"), ("gap", "conflict")]
)
def test_fixed_projection_does_not_turn_unknown_or_conflicting_qualification_into_support(
    judgment, expected
):
    application, task = job_and_task([requirement("Work permit", hard=True, judgment=judgment)])
    report = task["artifacts"][0]["result"]
    report.update(
        retrieval={"selected_candidate_ids": []}, application_library_policy="trusted-library/v1"
    )
    view = job_explanation(application, task, current_inputs=task["inputs"], fixed_delivery=True)
    assert view["qualification"]["status"] == expected
    assert view["reasons"][0]["judgment"] == judgment


def test_flow_snapshot_presents_the_same_fixed_qualification_as_execution(application, tmp_path):
    applications, job = application

    def analyze(task):
        rows = [requirement("Fluent English", hard=True)]
        return {
            "id": "fixed-analysis",
            "application_id": task["application_id"],
            "application_library_policy": "trusted-library/v1",
            "requirements": rows,
            "score": calculate_match_score(rows),
            "retrieval": {"selected_candidate_ids": []},
            "job_brief": {},
            "material_packet": {},
            "inference_result": {},
        }

    flow = ApplicationFlowService(
        applications, tmp_path / "flow", callbacks={"analysis": analyze}, preparation_only=True
    )
    try:
        task = flow.create(job["id"], job["revision"])
        flow.start(task["id"], task["revision"], "analysis")
        task = wait_for(flow, task["id"], lambda row: row["status"] == "analysis_ready")
        view = flow.snapshot(task["id"])
        assert task_eligibility(task, bind_inputs=True)["status"] == "supported"
        assert view["eligibility"]["status"] == "supported"
        assert view["active_explanation"]["reasons"][0]["judgment"] == "supported"
    finally:
        flow.close()


def test_the_card_shows_each_in_band_fit_and_none_for_a_withheld_citation():
    application, task = job_and_task(
        [
            requirement("Python") | {"fit_score": 120},
            requirement("Linux", judgment="partial") | {"fit_score": 62},
            requirement("ROS2", judgment="unknown")
            | {"citation_warning": "match_source_invalid", "fit_score": 5},
        ]
    )
    view = job_explanation(application, task, current_inputs=task["inputs"], fixed_delivery=True)
    assert [reason.get("fit") for reason in view["reasons"]] == [100, 60, None]


def test_fixed_card_shows_the_latest_recheck_but_keeps_its_qualification():
    application, task = job_and_task([requirement("Work permit", judgment="unknown", hard=True)])
    analysis = task["artifacts"][0]["result"]
    analysis.update(
        retrieval={"selected_candidate_ids": []}, application_library_policy="trusted-library/v1"
    )
    recheck = deepcopy(analysis)
    recheck["requirements"] = [requirement("Work permit", hard=True) | {"fit_score": 90}]
    task["job_binding"] = task.get("job_binding")
    task["match_rechecks"] = [
        {
            "id": "r1",
            "method": "normal_analysis",
            "base_analysis_id": task["analysis_id"],
            "job_binding": task["job_binding"],
            "library_revision": "lib",
            "source_snapshot_revision": "src",
            "reviewed_at": "2026-10-31T12:00:00+00:00",
            "result": recheck,
        }
    ]
    # Decided 2026-10-31: the card shows the latest recheck of a fixed job.
    view = job_explanation(application, task, current_inputs=task["inputs"], fixed_delivery=True)
    assert view["score"] == calculate_match_score(recheck["requirements"])
    assert view["match_recheck"]["id"] == "r1"
    assert view["qualification"]["status"] == "needs_input"
