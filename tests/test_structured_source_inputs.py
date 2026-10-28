"""Current facts do not recycle accepted TeX, and historical bytes stay available."""

import json
from copy import deepcopy

import pytest
from test_application_match import model_output, model_runner
from test_application_source_reuse import retained_capture as retained_capture

from career_evidence_graph.application_match import analyze_job
from career_evidence_graph.application_resume import career_source_snapshot
from career_evidence_graph.application_worker import digest


@pytest.fixture
def structured_retained_case(retained_capture):
    case = retained_capture
    root = case["catalog"].root
    profile = {"name": "Synthetic Person", **case["profile"]}
    (root / "sources/profile.json").write_text(json.dumps(profile))
    contribution = root / "contributions/service.md"
    contribution.parent.mkdir()
    contribution.write_text(
        "# Service\n\n## Scope\n\nBuilt a Python service.\n\n"
        "## Responsibility attribution\n\n| Area | Attribution |\n| --- | --- |\n"
        "| Service | User |\n\n## Boundaries\n\nNo team leadership was established.\n"
    )
    record = case["catalog"]._record(contribution, "contribution", detail=True)
    context_id = record["id"] + ":Scope"
    case["manifest"]["groups"][1]["context_source_ids"] = [context_id]
    (root / "sources/retained-resume-sources.json").write_text(json.dumps(case["manifest"]))
    return case | {"context_id": context_id}


def test_default_snapshot_archives_retained_words_and_preserves_original_context(
    structured_retained_case,
):
    case = structured_retained_case
    root = case["catalog"].root
    before = {path: path.read_bytes() for path in root.rglob("*") if path.is_file()}
    snapshot = career_source_snapshot(case["catalog"])
    assert not any(item.get("source_kind") == "accepted_resume" for item in snapshot["items"])
    context = next(item for item in snapshot["items"] if item["source_id"] == case["context_id"])
    assert context["text"] == "Built a Python service."
    assert context["boundaries"] == "No team leadership was established."
    archived = next(
        item for item in snapshot["retained_materials"] if item["source_kind"] == "accepted_resume"
    )
    assert archived["text"] == (
        "\\section{Experience}\nBuilt a Python service with the engineering team.\n"
    )
    assert archived["import_status"] == "import_pending"
    assert archived["context_source_ids"] == [context["source_id"]]
    assert archived["supporting_sources"] == [context]
    assert before == {path: path.read_bytes() for path in root.rglob("*") if path.is_file()}


def test_education_fact_contains_json_profile_record_and_keeps_in_progress_status(
    structured_retained_case,
):
    case = structured_retained_case
    snapshot = career_source_snapshot(case["catalog"])
    education = next(item for item in snapshot["items"] if item.get("source_kind") == "education")
    assert json.loads(education["text"]) == {"profile_record": case["profile"]["education"][0]}
    assert "accepted_latex" not in education
    assert education["rewrite_allowed"] is False
    archived = next(
        item for item in snapshot["retained_materials"] if item["source_kind"] == "education"
    )
    assert "\\section{Education}" in json.loads(archived["text"])["accepted_latex"]
    assert archived["import_status"] == "projected"


def test_applied_education_correction_is_projected_without_old_accepted_words(
    structured_retained_case,
):
    case = structured_retained_case
    catalog = case["catalog"]
    profile_path = catalog.root / "sources/profile.json"
    before = catalog._record(profile_path, "source", detail=True)
    profile = json.loads(before["content"])
    profile["education"][0]["detail"] = "Expected August 2028; not awarded"
    catalog.update_evidence(before["id"], before["revision"], json.dumps(profile))
    snapshot = career_source_snapshot(catalog)
    education = next(item for item in snapshot["items"] if item.get("source_kind") == "education")
    assert json.loads(education["text"]) == {"profile_record": profile["education"][0]}
    assert education["education_profile_sha256"] == digest(profile["education"][0])
    assert "July 2028" not in education["text"]
    archived = next(
        item for item in snapshot["retained_materials"] if item["source_kind"] == "education"
    )
    assert "Expected July 2028" in json.loads(archived["text"])["accepted_latex"]


def test_analysis_model_receives_facts_without_retained_tex(structured_retained_case, tmp_path):
    application = {
        "id": "synthetic",
        "revision": "job-source-revision",
        "company": "Synthetic Co",
        "role_title": "Service Engineer",
        "job_description": "Build Python services.",
    }
    snapshot = career_source_snapshot(structured_retained_case["catalog"])
    calls = []
    analyze_job(
        application,
        snapshot,
        tmp_path / "analysis",
        runner=model_runner(model_output(snapshot), calls),
    )
    prompt = calls[-1][-1]
    assert "accepted_latex" not in prompt
    assert "\\\\section{Experience}" not in prompt
    assert "with the engineering team" not in prompt
    assert "Built a Python service." in prompt
    assert "PhD in progress" in prompt


def test_legacy_generation_reads_the_archive_without_repolluting_analysis_facts(
    structured_retained_case,
):
    from career_evidence_graph.application_full_latex import _sources as legacy_sources
    from career_evidence_graph.application_match import _sources as match_sources

    snapshot = career_source_snapshot(structured_retained_case["catalog"])
    before = deepcopy(snapshot)
    generated = legacy_sources(snapshot, {}, {})
    by_id = {source["source_id"]: source for source in generated}
    for archived in snapshot["retained_materials"]:
        assert by_id[archived["source_id"]]["text"] == archived["text"]
    assert snapshot == before
    analyzed = match_sources(snapshot)
    assert not any(source.get("source_kind") == "accepted_resume" for source in analyzed.values())
    assert all("accepted_latex" not in source["text"] for source in analyzed.values())


@pytest.mark.parametrize("source_kind", ["accepted_resume", "legacy_tex"])
def test_fact_projection_is_pure_and_idempotent_and_never_strips_unknown_original_text(source_kind):
    from career_evidence_graph.application_source_reuse import fact_source_projection

    archive = {
        "source_id": "legacy:1",
        "source_kind": source_kind,
        "text": "\\subsection{Historical}\nA unique unconverted statement.\n",
        "context_source_ids": [],
    }
    unconverted = {
        "source_id": "old-body:1",
        "source_name": "sources/kept.md",
        "text": "Original prose with \\LaTeX{} notation; attribution is not established.",
    }
    original = {"items": [archive, unconverted], "documents": [], "revision": "old"}
    before = deepcopy(original)
    result = fact_source_projection(original)
    assert original == before
    assert result["items"] == [unconverted]
    assert result["retained_materials"] == [archive | {"import_status": "import_pending"}]
    assert fact_source_projection(result) == result
    assert result["revision"] == digest(
        {key: value for key, value in result.items() if key != "revision"}
    )
