"""Fixed P04 checks only its cited facts in the task's authoritative information library."""

from copy import deepcopy

import pytest
from test_application_information import answer, write_library
from test_application_job_brief import output, runner_for
from test_job_explanations import job_and_task

from career_evidence_graph.application_information import information_source_snapshot
from career_evidence_graph.application_job_brief import brief_requirements, create_job_brief
from career_evidence_graph.application_match_scoring import calculate_match_score
from career_evidence_graph.application_single_binding import check_single_qualification
from career_evidence_graph.career_portal_data import PortalDataError


def fixed_german_case(root):
    app, task = job_and_task([])
    app.update(job_description="German B2 required.", country="CHE", company="Synthetic")
    body = output.__wrapped__()
    body["groups"] = [
        {
            "label": "Language",
            "jd_quote": "German B2 required.",
            "operator": "all",
            "importance": "required",
            "hard_condition": True,
            "weight": 100,
            "weight_reason": "Explicit eligibility",
            "requirements": [{"text": "German B2 required.", "jd_quote": "German B2 required."}],
        }
    ]
    brief = create_job_brief(app, root / "brief", runner=runner_for(body), environment={})
    original = answer("German level", "B2", scope={"country": "CHE"})[1]
    other = answer("German proficiency CEFR", "C1", scope={"company": "Synthetic"})[1]
    old = {"status": "available", "records": [original]}
    new = {"status": "available", "records": [original, other]}
    delivered = information_source_snapshot(app, old, {})
    source = delivered["items"][0]
    fact = delivered["information_context"]["facts"][0]
    req = brief_requirements(brief)[0] | {
        "judgment": "supported",
        "explanation": "Saved confirmed German B2 supports this hard condition.",
        "sources": [source],
        "information_support": {
            "fact": fact["fact"],
            "references": fact["references"],
            "status": "supported",
            "explanation": "confirmed",
        },
    }
    report = task["artifacts"][0]["result"]
    report.update(
        requirements=[req],
        score=calculate_match_score([req]),
        application_library_policy="trusted-library/v1",
        retrieval={"selected_candidate_ids": []},
        job_brief=brief,
        material_packet={},
        inference_result={},
    )
    return app, task, old, new


@pytest.mark.parametrize("change", ["conflict", "correction", "withdrawal"])
def test_fixed_cited_language_fact_changes_stop_without_rewriting_p04(tmp_path, change):
    app, task, old, current = fixed_german_case(tmp_path)
    if change != "conflict":
        row = deepcopy(old["records"][0])
        if change == "correction":
            row["value"] = "A1"
        else:
            row["state"] = "missing"
        current = {"status": "available", "records": [row]}
    root = tmp_path / "information"
    write_library(root, answers={row["key"]: row for row in current["records"]})
    retained = deepcopy(task)
    with pytest.raises(PortalDataError) as failure:
        check_single_qualification(task, app, root, "CHE")
    assert failure.value.code == "single_eligibility_required"
    assert task == retained


def test_fixed_unrelated_language_conflicts_do_not_invalidate_cited_german(tmp_path):
    app, task, old, _ = fixed_german_case(tmp_path)
    rows = old["records"] + [
        answer("French level", "B2")[1],
        answer("French proficiency CEFR", "C1")[1],
    ]
    root = tmp_path / "information"
    write_library(root, answers={row["key"]: row for row in rows})
    assert check_single_qualification(task, app, root, "CHE") is True


def test_fixed_declared_information_root_is_authoritative_and_never_merges_default(tmp_path):
    app, task, old, current = fixed_german_case(tmp_path)
    selected, fallback = tmp_path / "selected", tmp_path / "worker-answers"
    write_library(selected, answers={row["key"]: row for row in old["records"]})
    write_library(fallback, answers={row["key"]: row for row in current["records"]})
    task["inputs"] = {"information_library_root": str(selected)}
    assert check_single_qualification(task, app, fallback, "CHE") is True
    (selected / "answers.json").write_bytes((fallback / "answers.json").read_bytes())
    with pytest.raises(PortalDataError):
        check_single_qualification(task, app, fallback, "CHE")


@pytest.mark.parametrize("part", ["job_brief", "material_packet", "inference_result"])
def test_incomplete_fixed_delivery_cannot_fall_back_to_legacy(tmp_path, part):
    app, task, old, _ = fixed_german_case(tmp_path)
    root = tmp_path / "information"
    write_library(root, answers={row["key"]: row for row in old["records"]})
    del task["artifacts"][0]["result"][part]
    with pytest.raises(PortalDataError) as failure:
        check_single_qualification(task, app, root, "CHE")
    assert failure.value.code == "single_binding_invalid"


@pytest.mark.parametrize(
    "extra",
    [
        ("German level", "A1", {}),
        ("German proficiency CEFR", "B2", {"company": "Synthetic"}),
        ("German proficiency CEFR", "C1", {"company": "Unrelated"}),
        ("German proficiency CEFR", "C1", {"country": "USA"}),
    ],
)
def test_fixed_refs_retain_scope_precedence_and_ignore_unrelated_answers(tmp_path, extra):
    app, task, old, _ = fixed_german_case(tmp_path)
    question, value, scope = extra
    rows = old["records"] + [answer(question, value, scope=scope)[1]]
    root = tmp_path / "information"
    write_library(root, answers={row["key"]: row for row in rows})
    assert check_single_qualification(task, app, root, "CHE") is True


def test_missing_declared_library_cannot_fall_back_to_worker_answers(tmp_path):
    app, task, old, _ = fixed_german_case(tmp_path)
    fallback = tmp_path / "worker-answers"
    write_library(fallback, answers={row["key"]: row for row in old["records"]})
    task["inputs"] = {"information_library_root": str(tmp_path / "missing-declared-library")}
    with pytest.raises(PortalDataError) as failure:
        check_single_qualification(task, app, fallback, "CHE")
    assert failure.value.code == "single_eligibility_required"


def test_corrupt_fixed_brief_cannot_fall_back_to_legacy(tmp_path):
    app, task, old, _ = fixed_german_case(tmp_path)
    root = tmp_path / "information"
    write_library(root, answers={row["key"]: row for row in old["records"]})
    task["artifacts"][0]["result"]["job_brief"]["revision"] = "corrupt"
    with pytest.raises(PortalDataError) as failure:
        check_single_qualification(task, app, root, "CHE")
    assert failure.value.code == "job_brief_invalid"
