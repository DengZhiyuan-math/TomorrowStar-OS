"""Analysis reuse follows the actual consumed input, not omitted source revisions."""

import json
import subprocess
from functools import partial
from types import SimpleNamespace

import pytest
from test_application_flow import wait_for
from test_application_match import model_output, model_runner

from career_evidence_graph._vendor import job_apply_store as helper
from career_evidence_graph.application_flow import task_eligibility
from career_evidence_graph.application_information import (
    put_information_answer,
    read_information_library,
)
from career_evidence_graph.application_match import analyze_job
from career_evidence_graph.application_resume import career_source_snapshot
from career_evidence_graph.career_portal import create_server
from career_evidence_graph.career_portal_data import ApplicationStore, CareerCatalog

pytestmark = pytest.mark.usefixtures("planner_path")


@pytest.fixture
def analyzed_omitted_source(tmp_path, request):
    clarify = getattr(request, "param", False)
    career = tmp_path / "career"
    contributions = career / "contributions"
    contributions.mkdir(parents=True)
    template = (
        "# Contribution candidate: Synthetic service\n\n## Scope\n{scope}\n\n"
        "## Responsibility attribution\n| Work | Owner |\n| --- | --- |\n"
        "| Implementation | User |\n\n## Boundaries\nNo GPU training claim.\n"
    )
    # Explicit lexical order exhausts the real context budget on this first record.
    (contributions / "00-consumed.md").write_text(
        template.format(scope="Implemented a Python service. " + "source-text " * 20000)
    )
    sources = career / "sources"
    sources.mkdir()
    (sources / "profile.json").write_text(
        json.dumps({"name": "Synthetic Person", "location": "Ruby"})
    )
    subprocess.run(["git", "init", "--quiet", str(career)], check=True)
    catalog = CareerCatalog(career)
    before_sources = career_source_snapshot(catalog)
    assert before_sources["items"][0]["source_name"] == "contributions/00-consumed.md"
    omitted_id = before_sources["profile_source"]["id"] + ":profile.location"
    calls = []
    output = model_output(before_sources)
    if clarify:
        output["requirements"].append(
            {
                "text": "Residence in Ruby required"
                if clarify == "residence"
                else "German B2 required",
                "importance": "required",
                "judgment": "unknown",
                "hard_condition": True,
                "explanation": "Applicant fact requires clarification.",
                "source_ids": [],
                "citations": [],
                "claim_scope": "unknown",
            }
        )
    analyzer = partial(analyze_job, runner=model_runner(output, calls))
    applications = tmp_path / "applications"
    applications.mkdir()
    job = ApplicationStore(applications).create_application(
        {
            "company": "Synthetic Employer",
            "role_title": "Python Engineer",
            "job_description": "Build reliable Python systems.",
        }
    )
    with create_server(
        applications, career, flow_root=tmp_path / "flow", flow_analyzer=analyzer
    ) as server:
        flow = server.application_flow_service
        task = flow.create(job["id"], job["revision"])
        flow.start(task["id"], task["revision"], "analysis")
        task = wait_for(flow, task["id"], lambda row: row["status"] == "analysis_ready")
        if clarify:
            task = flow.clarify_condition(
                task["id"],
                task["revision"],
                1,
                True,
                "Current career profile location is Ruby"
                if clarify == "residence"
                else "Existing fact",
            )
            assert task_eligibility(task, bind_inputs=True)["status"] == "supported"
        yield SimpleNamespace(
            flow=flow,
            task=task,
            job=job,
            catalog=catalog,
            before_sources=before_sources,
            omitted_id=omitted_id,
            calls=calls,
            analyzer=analyzer,
            clarify=clarify,
            root=tmp_path,
        )


@pytest.mark.parametrize(
    "analyzed_omitted_source", [False, True], indirect=True, ids=["plain", "clarified"]
)
def test_omitted_source_correction_preserves_identical_analysis_input(analyzed_omitted_source):
    case = analyzed_omitted_source
    flow, task, job, catalog = case.flow, case.task, case.job, case.catalog
    before_sources, omitted_id = case.before_sources, case.omitted_id
    calls, analyzer, clarify, tmp_path = case.calls, case.analyzer, case.clarify, case.root
    original_artifacts = json.loads(json.dumps(task["artifacts"]))
    original_analysis_id = task["analysis_id"]
    directory = flow.root / "analyses" / original_analysis_id
    original_files = {path.name: path.read_bytes() for path in directory.iterdir()}
    assert omitted_id in task["artifacts"][0]["result"]["coverage"]["omitted_source_ids"]
    before_prompt = calls[-1][-1]
    before_document = catalog.get_evidence(before_sources["profile_source"]["id"])
    corrected = before_document["content"].replace("Ruby", "Rust")
    assert len(corrected.encode()) == len(before_document["content"].encode())
    catalog.update_evidence(
        before_document["id"],
        before_document["revision"],
        corrected,
        actor="user",
        source="synthetic omitted-source correction",
    )
    after_sources = career_source_snapshot(catalog)
    assert before_sources["revision"] != after_sources["revision"]
    assert before_sources["items"][0] == after_sources["items"][0]
    # A separate bounded analyzer probe records the true post-correction prompt.
    # It is not a Flow stage, and no model/provider or browser is used.
    probe = analyzer(job, after_sources, tmp_path / "after-context-probe")
    assert omitted_id in probe["coverage"]["omitted_source_ids"]
    after_prompt = calls[-1][-1]
    assert before_prompt.encode() == after_prompt.encode()
    evidence = tmp_path / "consumed-input-evidence"
    evidence.mkdir()
    for label, prompt, snapshot in (
        ("before", before_prompt, before_sources),
        ("after", after_prompt, after_sources),
    ):
        (evidence / f"{label}-prompt.txt").write_text(prompt)
        (evidence / f"{label}-sources.json").write_text(json.dumps(snapshot, indent=2))
    print(f"analysis_evidence_root={evidence}")
    call_count = len(calls)
    refreshed = flow.update_inputs(task["id"], task["revision"], job["revision"])
    assert len(calls) == call_count
    assert {path.name: path.read_bytes() for path in directory.iterdir()} == original_files
    assert refreshed["artifacts"][:-1] == original_artifacts
    adopted = refreshed["artifacts"][-1]["result"]
    original_result = original_artifacts[-1]["result"]
    assert adopted["reused_from"]["analysis_id"] == original_analysis_id
    assert adopted["reused_from"]["model_called"] is False
    assert refreshed["analysis_id"] == adopted["id"]
    assert adopted["source_snapshot_revision"] == after_sources["revision"]
    for key in ("score", "requirements", "selected_source_ids", "model"):
        assert adopted[key] == original_result[key]
    # Analysis equivalence does not declare material or PDF equivalence.
    assert refreshed["resume_id"] is None
    assert refreshed["stages"]["resume"]["status"] == "pending"
    assert refreshed["stages"]["analysis"]["status"] == "complete"
    if clarify:
        assert task_eligibility(refreshed, bind_inputs=True)["status"] == "supported"
        assert refreshed["hard_condition_resolutions"][0] == task["hard_condition_resolutions"][0]
        original_resolution = task["hard_condition_resolutions"][-1]
        assert original_resolution["qualification_basis"]
        inherited = refreshed["hard_condition_resolutions"][-1]
        assert inherited["analysis_id"] == adopted["id"]
        assert inherited["qualification_basis"] == original_resolution["qualification_basis"]
        assert inherited["inherited_from"]["analysis_id"] == original_analysis_id


@pytest.mark.parametrize("analyzed_omitted_source", [True], indirect=True)
def test_reused_analysis_does_not_reconfirm_a_changed_language_fact(analyzed_omitted_source):
    case = analyzed_omitted_source
    document = case.catalog.get_evidence(case.before_sources["profile_source"]["id"])
    case.catalog.update_evidence(
        document["id"], document["revision"], document["content"].replace("Ruby", "Rust")
    )
    root = case.root / "changed-information"
    put_information_answer(
        helper.Store(root, legacy_profile=case.root / "absent-legacy-profile.json"),
        {
            "question": "German proficiency CEFR",
            "value": "A1",
            "scope": {},
            "state": "confirmed",
        },
    )
    case.flow.information_provider = lambda: read_information_library(root)
    refreshed = case.flow.update_inputs(
        case.task["id"], case.task["revision"], case.job["revision"]
    )
    assert refreshed["artifacts"][-1]["result"]["reused_from"]["model_called"] is False
    assert refreshed["hard_condition_resolutions"] == case.task["hard_condition_resolutions"]
    assert task_eligibility(refreshed, bind_inputs=True)["status"] == "needs_input"


@pytest.mark.parametrize("analyzed_omitted_source", ["residence"], indirect=True)
def test_reused_analysis_does_not_reconfirm_an_unbound_residence_fact(analyzed_omitted_source):
    case = analyzed_omitted_source
    task = case.task
    original_resolutions = json.loads(json.dumps(task["hard_condition_resolutions"]))
    assert "qualification_basis" not in original_resolutions[-1]
    assert task_eligibility(task, bind_inputs=True)["status"] == "supported"
    directory = case.flow.root / "analyses" / task["analysis_id"]
    original_files = {path.name: path.read_bytes() for path in directory.iterdir()}
    assert case.omitted_id in task["artifacts"][-1]["result"]["coverage"]["omitted_source_ids"]
    document = case.catalog.get_evidence(case.before_sources["profile_source"]["id"])
    assert json.loads(document["content"])["location"] == "Ruby"
    case.catalog.update_evidence(
        document["id"], document["revision"], document["content"].replace("Ruby", "Rust")
    )
    current_document = case.catalog.get_evidence(document["id"])
    assert json.loads(current_document["content"])["location"] == "Rust"
    call_count = len(case.calls)
    refreshed = case.flow.update_inputs(task["id"], task["revision"], case.job["revision"])
    assert len(case.calls) == call_count
    assert {path.name: path.read_bytes() for path in directory.iterdir()} == original_files
    assert refreshed["artifacts"][:-1] == task["artifacts"]
    assert refreshed["stages"]["analysis"]["attempt_id"] == task["stages"]["analysis"]["attempt_id"]
    adopted = refreshed["artifacts"][-1]["result"]
    assert adopted["reused_from"]["model_called"] is False
    assert adopted["reused_from"]["analysis_id"] == task["analysis_id"]
    assert refreshed["analysis_id"] == adopted["id"] != task["analysis_id"]
    eligibility = task_eligibility(refreshed, bind_inputs=True)
    assert eligibility["status"] == "needs_input"
    assert eligibility["conditions"][0]["resolution"] is None
    assert refreshed["hard_condition_resolutions"] == original_resolutions


@pytest.mark.parametrize("analyzed_omitted_source", [True], indirect=True)
def test_reused_analysis_does_not_inherit_a_legacy_language_confirmation_without_basis(
    analyzed_omitted_source,
):
    case = analyzed_omitted_source
    information_provider = case.flow.information_provider
    # A clarification saved without a library has the historical missing-basis shape.
    case.flow.information_provider = None
    task = case.flow.clarify_condition(
        case.task["id"], case.task["revision"], 1, True, "Legacy confirmed German proficiency"
    )
    case.flow.information_provider = information_provider
    assert "qualification_basis" not in task["hard_condition_resolutions"][-1]
    assert task_eligibility(task, bind_inputs=True)["status"] == "supported"
    document = case.catalog.get_evidence(case.before_sources["profile_source"]["id"])
    case.catalog.update_evidence(
        document["id"], document["revision"], document["content"].replace("Ruby", "Rust")
    )
    refreshed = case.flow.update_inputs(task["id"], task["revision"], case.job["revision"])
    assert refreshed["artifacts"][-1]["result"]["reused_from"]["model_called"] is False
    assert task_eligibility(refreshed, bind_inputs=True)["status"] == "needs_input"
    assert refreshed["hard_condition_resolutions"] == task["hard_condition_resolutions"]
