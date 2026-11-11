"""A match cites the exact visible content, never an entire career document."""

import json
from copy import deepcopy

import pytest
from test_application_match import match_inputs as match_inputs
from test_application_match import model_output, model_runner

from career_evidence_graph.application_match import _sources, analyze_job
from career_evidence_graph.application_resume import career_source_snapshot
from career_evidence_graph.career_portal_data import CareerCatalog


def quoted_output(snapshot, quote="Implemented a Python service."):
    output = model_output(snapshot)
    output["requirements"][0]["citations"] = [
        {"source_id": snapshot["items"][0]["source_id"], "quote": quote}
    ]
    return output


def test_exact_quote_is_retained_with_its_source_and_character_range(match_inputs, tmp_path):
    application, snapshot = match_inputs
    output = quoted_output(snapshot)
    result = analyze_job(
        application, snapshot, tmp_path / "quoted", runner=model_runner(output, [])
    )
    source = result["requirements"][0]["sources"][0]
    assert source["quote"] == "Implemented a Python service."
    assert source["quote_start"] == 0
    assert source["quote_end"] == len(source["quote"])
    assert source["source_revision"] == snapshot["items"][0]["source_revision"]
    assert source["locator"] == "Scope"
    assert result["score"]["lower"] == 100
    assert all(source["locator"] != "document" for source in _sources(snapshot).values())


@pytest.mark.parametrize("bad", ["invented", "missing", "wrong-source", "mixed-whole-document"])
def test_invalid_quote_marks_one_requirement_unknown_and_saves_the_analysis(
    match_inputs, tmp_path, bad
):
    application, snapshot = match_inputs
    output = quoted_output(snapshot)
    requirement = output["requirements"][0]
    if bad == "invented":
        requirement["citations"][0]["quote"] = "Published twenty technical articles."
    elif bad == "missing":
        requirement["citations"] = []
    elif bad == "wrong-source":
        requirement["citations"][0]["source_id"] = "another-source:Scope"
    else:
        whole = snapshot["documents"][0]["id"] + ":document"
        requirement["source_ids"].append(whole)
        requirement["citations"].append({"source_id": whole, "quote": "Python service"})
    output["requirements"].append(
        deepcopy(quoted_output(snapshot)["requirements"][0]) | {"text": "Maintain a Python service"}
    )
    result = analyze_job(application, snapshot, tmp_path / bad, runner=model_runner(output, []))
    assert result["requirements"][0]["citation_warning"] == "match_source_invalid"
    assert result["requirements"][0]["judgment"] == "unknown"
    assert result["requirements"][1]["judgment"] == "supported"
    assert (tmp_path / bad / "analysis.json").exists()
    assert (tmp_path / bad / "model-result.json").exists()


def profile_snapshot(tmp_path):
    root = tmp_path / "facts"
    profile = {
        "name": "Synthetic Person",
        "location": "Zurich, Switzerland",
        "sideProjects": [
            {
                "title": "Data viewer",
                "description": "Implemented a Python data viewer.",
                "status": "Published",
            },
            {
                "title": "Future viewer",
                "description": "Plan to implement a Python data viewer.",
                "status": "Planned",
            },
        ],
    }
    path = root / "sources/profile.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(profile))
    return career_source_snapshot(CareerCatalog(root))


def test_profile_facts_are_specific_and_keep_unrelated_record_boundaries(tmp_path):
    snapshot = profile_snapshot(tmp_path)
    sources = _sources(snapshot)
    origin = snapshot["profile_source"]["id"]
    assert origin + ":document" not in sources
    location = sources[origin + ":profile.location"]
    assert location["text"] == "Zurich, Switzerland"
    assert location["document_locator"] == "$.location"
    assert location["documentary_only"] is True
    completed = sources[origin + ":profile.side_projects[0]"]
    planned = sources[origin + ":profile.side_projects[1]"]
    assert completed["document_locator"] == "$.sideProjects[0].description"
    assert completed["match_eligible"] is True
    assert completed["resume_eligible"] is False
    assert planned["match_eligible"] is False
    assert planned["record_context"]["status"] == "Planned"


@pytest.mark.parametrize(
    "index,scope,code",
    [
        (0, "documentary", None),
        (0, "personal_completed", "match_attribution_invalid"),
        (1, "documentary", "match_attribution_invalid"),
    ],
)
def test_actual_profile_record_controls_support_not_the_entire_document(
    match_inputs, tmp_path, index, scope, code
):
    application, _ = match_inputs
    snapshot = profile_snapshot(tmp_path)
    identifier = snapshot["profile_source"]["id"] + f":profile.side_projects[{index}]"
    quote = (
        "Implemented a Python data viewer."
        if index == 0
        else "Plan to implement a Python data viewer."
    )
    output = {
        "role_understanding": {
            "business_objective": "Deliver the systems described in the JD.",
            "work_outputs": ["Reliable systems"],
            "methods_role": "Technical methods support reliable system delivery.",
        },
        "requirements": [
            {
                "text": "Python project experience",
                "importance": "required",
                "judgment": "supported",
                "hard_condition": False,
                "explanation": "A specific self-reported project, not assessed mastery.",
                "source_ids": [identifier],
                "claim_scope": scope,
                "citations": [{"source_id": identifier, "quote": quote}],
            }
        ],
        "selected_source_ids": [],
        "selection_rationale": [],
        "extracted_fields": {
            "company": None,
            "role_title": None,
            "location": None,
            "uncertain_fields": ["company", "role_title", "location"],
        },
        "limitations": ["Documentary comparison only."],
    }
    result = analyze_job(
        application, snapshot, tmp_path / "project", runner=model_runner(output, [])
    )
    if code:
        assert result["requirements"][0]["citation_warning"] == code
        assert result["requirements"][0]["judgment"] == "unknown"
    else:
        assert result["requirements"][0]["sources"][0]["quote"] == quote
        assert result["requirements"][0]["sources"][0]["documentary_only"] is True


def test_quote_must_be_inside_the_part_actually_sent_to_the_model(
    match_inputs, tmp_path, monkeypatch
):
    application, _ = match_inputs
    path = tmp_path / "career/contributions/python.md"
    path.write_text(
        path.read_text().replace(
            "Implemented a Python service.",
            "Implemented a Python service. " + "context " * 9000 + "UNSEEN LAST SENTENCE.",
        )
    )
    snapshot = career_source_snapshot(CareerCatalog(tmp_path / "career"))
    monkeypatch.setenv("TOMORROWSTAR_MATCH_CONTEXT_BYTES", "11000")
    output = quoted_output(snapshot, "UNSEEN LAST SENTENCE.")
    result = analyze_job(
        application, snapshot, tmp_path / "unseen", runner=model_runner(output, [])
    )
    assert result["requirements"][0]["citation_warning"] == "match_source_invalid"
    assert result["requirements"][0]["judgment"] == "unknown"
    coverage = json.loads((tmp_path / "unseen/context-coverage.json").read_text())
    assert coverage["truncated_sources"][0]["included_chars"] < len(snapshot["items"][0]["text"])


def test_merged_duplicate_requirements_retain_both_literal_citations(match_inputs, tmp_path):
    application, _ = match_inputs
    path = tmp_path / "career/contributions/python.md"
    path.write_text(
        path.read_text().replace(
            "Implemented a Python service.", "Implemented a Python service. Maintained its tests."
        )
    )
    snapshot = career_source_snapshot(CareerCatalog(tmp_path / "career"))
    output = quoted_output(snapshot)
    second = deepcopy(output["requirements"][0])
    second["citations"][0]["quote"] = "Maintained its tests."
    output["requirements"].append(second)
    result = analyze_job(
        application, snapshot, tmp_path / "duplicate", runner=model_runner(output, [])
    )
    assert len(result["requirements"]) == 1
    assert [source["quote"] for source in result["requirements"][0]["sources"]] == [
        "Implemented a Python service.",
        "Maintained its tests.",
    ]


@pytest.mark.parametrize(
    "quote,code",
    [
        ("Implemented a Python service.", None),
        ("Plan to add Rust later.", "match_attribution_invalid"),
        ("Rust", "match_attribution_invalid"),
    ],
)
def test_actual_quoted_sentence_controls_planned_work_boundary(match_inputs, tmp_path, quote, code):
    application, _ = match_inputs
    path = tmp_path / "career/contributions/python.md"
    path.write_text(
        path.read_text().replace(
            "Implemented a Python service.", "Implemented a Python service. Plan to add Rust later."
        )
    )
    snapshot = career_source_snapshot(CareerCatalog(tmp_path / "career"))
    output = quoted_output(snapshot, quote)
    result = analyze_job(
        application, snapshot, tmp_path / "mixed-plan", runner=model_runner(output, [])
    )
    if code:
        assert result["requirements"][0]["citation_warning"] == code
        assert result["requirements"][0]["judgment"] == "unknown"
    else:
        assert result["score"]["lower"] == 100


@pytest.mark.parametrize(
    "quote,code", [('Built a "Python" service.', None), ("Synthetic Lab", "match_source_invalid")]
)
def test_profile_quotes_use_decoded_work_content_and_exact_field_path(
    match_inputs, tmp_path, quote, code
):
    application, _ = match_inputs
    snapshot = profile_snapshot(tmp_path)
    root = tmp_path / "facts"
    path = root / "sources/profile.json"
    profile = json.loads(path.read_text())
    profile["experience"] = [
        {
            "role": "Engineer",
            "organization": "Synthetic Lab",
            "period": "2020–2022",
            "detail": 'Built a "Python" service.\nMaintained it.',
            "points": [],
        }
    ]
    path.write_text(json.dumps(profile))
    snapshot = career_source_snapshot(CareerCatalog(root))
    identifier = snapshot["profile_source"]["id"] + ":profile.experience[0]"
    output = model_output(snapshot)
    output["requirements"][0].update(
        source_ids=[identifier],
        claim_scope="documentary",
        citations=[{"source_id": identifier, "quote": quote}],
    )
    output["selected_source_ids"] = [identifier]
    output["selection_rationale"][0]["source_id"] = identifier
    result = analyze_job(
        application, snapshot, tmp_path / "decoded", runner=model_runner(output, [])
    )
    if code:
        assert result["requirements"][0]["citation_warning"] == code
        assert result["requirements"][0]["judgment"] == "unknown"
    else:
        source = result["requirements"][0]["sources"][0]
        assert source["document_locator"] == "$.experience[0].detail"
        assert source["quote"] == quote
        assert result["selected_source_ids"] == [identifier]


@pytest.mark.parametrize(
    "candidate_degree,detail,requirement,judgment,eligibility",
    [
        ("PhD Candidate", "In progress.", "An awarded PhD", "unknown", "needs_input"),
        ("PhD Candidate", "In progress.", "Current PhD student", "supported", "supported"),
        ("PhD", "Degree not yet awarded.", "An awarded PhD", "partial", "needs_input"),
        ("PhD Candidate", "In progress.", "Documentary credential", "supported", "supported"),
    ],
)
def test_education_interpretation_preserves_context_and_model_uncertainty(
    match_inputs, tmp_path, requirement, judgment, eligibility, candidate_degree, detail
):
    application, _ = match_inputs
    profile_snapshot(tmp_path)
    path = tmp_path / "facts/sources/profile.json"
    profile = json.loads(path.read_text())
    profile["education"] = [
        {
            "degree": candidate_degree,
            "institution": "Synthetic University",
            "period": "2023–Present",
            "detail": detail,
        }
    ]
    path.write_text(json.dumps(profile))
    snapshot = career_source_snapshot(CareerCatalog(tmp_path / "facts"))
    identifier = snapshot["profile_source"]["id"] + ":profile.education[0]"
    output = {
        "role_understanding": {
            "business_objective": "Deliver the systems described in the JD.",
            "work_outputs": ["Reliable systems"],
            "methods_role": "Technical methods support reliable system delivery.",
        },
        "requirements": [
            {
                "text": requirement,
                "importance": "required",
                "judgment": judgment,
                "hard_condition": True,
                "explanation": "Documentary education.",
                "source_ids": [identifier],
                "claim_scope": "documentary",
                "citations": [{"source_id": identifier, "quote": "PhD"}],
            }
        ],
        "selected_source_ids": [],
        "selection_rationale": [],
        "extracted_fields": {
            "company": None,
            "role_title": None,
            "location": None,
            "uncertain_fields": ["company", "role_title", "location"],
        },
        "limitations": [],
    }
    calls = []
    result = analyze_job(
        application, snapshot, tmp_path / "degree", runner=model_runner(output, calls)
    )
    assert result["score"]["eligibility"] == eligibility
    assert result["requirements"][0]["judgment"] == judgment
    prompt = calls[-1][-1]
    assert detail in prompt
    assert "ongoing study can support an education-background requirement" in prompt
    # Decided 2026-10-31: the user applies for roles after the PhD, so it counts as held.
    assert "a degree in progress with an expected completion date supports" in prompt
    assert "return fit_score, an integer 0-100" in prompt


def test_quote_cannot_join_two_profile_fields_into_one_excerpt(match_inputs, tmp_path):
    application, _ = match_inputs
    profile_snapshot(tmp_path)
    path = tmp_path / "facts/sources/profile.json"
    profile = json.loads(path.read_text())
    profile["experience"] = [
        {
            "role": "Engineer",
            "organization": "Synthetic Lab",
            "period": "2020–2022",
            "detail": "Implemented Python.",
            "points": ["Maintained tests."],
        }
    ]
    path.write_text(json.dumps(profile))
    snapshot = career_source_snapshot(CareerCatalog(tmp_path / "facts"))
    output = model_output(snapshot)
    output["requirements"][0].update(
        claim_scope="documentary",
        citations=[
            {
                "source_id": snapshot["items"][0]["source_id"],
                "quote": "Implemented Python.\nMaintained tests.",
            }
        ],
    )
    result = analyze_job(
        application, snapshot, tmp_path / "cross-fields", runner=model_runner(output, [])
    )
    assert result["requirements"][0]["citation_warning"] == "match_source_invalid"
    assert result["requirements"][0]["judgment"] == "unknown"


def test_site_content_json_uses_the_actual_nested_alias_path(tmp_path):
    root = tmp_path / "nested"
    path = root / "reports/public-site/site-content.json"
    path.parent.mkdir(parents=True)
    path.write_text(
        json.dumps(
            {
                "schema_version": "public-site-source/v1",
                "profile": {
                    "name": "Synthetic Person",
                    "openSourceContributions": [
                        {
                            "title": "Parser fix",
                            "description": 'Fixed "quoted" Unicode 文本 parsing.',
                            "status": "Merged",
                        }
                    ],
                },
            }
        )
    )
    snapshot = career_source_snapshot(CareerCatalog(root))
    sources = _sources(snapshot)
    identifier = snapshot["profile_source"]["id"] + ":profile.open_source[0]"
    assert sources[identifier]["text"] == 'Fixed "quoted" Unicode 文本 parsing.'
    assert (
        sources[identifier]["document_locator"]
        == "$.profile.openSourceContributions[0].description"
    )


def test_future_training_sentence_does_not_prove_completed_training(match_inputs, tmp_path):
    application, _ = match_inputs
    path = tmp_path / "career/contributions/python.md"
    path.write_text(
        path.read_text().replace("Implemented a Python service.", "I will train a Python model.")
    )
    snapshot = career_source_snapshot(CareerCatalog(tmp_path / "career"))
    output = quoted_output(snapshot, "I will train a Python model.")
    output["requirements"][0]["text"] = "Completed Python model training"
    result = analyze_job(
        application, snapshot, tmp_path / "future-training", runner=model_runner(output, [])
    )
    assert result["requirements"][0]["citation_warning"] == "match_attribution_invalid"
    assert result["requirements"][0]["judgment"] == "unknown"


@pytest.mark.parametrize(
    "scope,code",
    [
        ("personal_completed", "match_attribution_invalid"),
        ("personal_design", "match_attribution_invalid"),
        ("unknown", None),
    ],
)
def test_unknown_judgment_does_not_upgrade_future_work_attribution(
    match_inputs, tmp_path, scope, code
):
    application, _ = match_inputs
    path = tmp_path / "career/contributions/python.md"
    path.write_text(
        path.read_text().replace(
            "Implemented a Python service.", "Plan to implement a Python service."
        )
    )
    snapshot = career_source_snapshot(CareerCatalog(tmp_path / "career"))
    output = quoted_output(snapshot, "Plan to implement a Python service.")
    output["requirements"][0].update(judgment="unknown", claim_scope=scope)
    output["selected_source_ids"] = []
    output["selection_rationale"] = []
    result = analyze_job(
        application, snapshot, tmp_path / "planned-scope", runner=model_runner(output, [])
    )
    if code:
        assert result["requirements"][0]["citation_warning"] == code
    else:
        assert result["requirements"][0]["claim_scope"] == "unknown"


def test_a_quote_cited_under_another_handle_moves_to_the_one_source_holding_it(
    match_inputs, tmp_path
):
    # Installed MC-11: a literal robotics quote cited under an unrelated record's handle
    # withheld nine Hexagon judgments; a quote held by exactly one source moves there.
    application, _ = match_inputs
    (tmp_path / "career/contributions/rust.md").write_text(
        "# Contribution candidate: Rust parser\n\n## Scope\nBuilt a Rust parser.\n\n"
        "## Responsibility attribution\n| Work | Owner |\n| --- | --- |\n"
        "| Implementation | User |\n"
    )
    snapshot = career_source_snapshot(CareerCatalog(tmp_path / "career"))
    python, rust = (
        next(i["source_id"] for i in snapshot["items"] if name in i.get("title", "") + i["text"])
        for name in ("Python service", "Rust parser")
    )
    output = model_output(snapshot)
    output["requirements"][0].update(
        source_ids=[rust],
        citations=[{"source_id": rust, "quote": "Implemented a Python service."}],
    )
    row = analyze_job(application, snapshot, tmp_path / "moved", runner=model_runner(output, []))[
        "requirements"
    ][0]
    assert "citation_warning" not in row and row["judgment"] == "supported"
    assert row["source_ids"] == [python]
    assert row["sources"][0]["quote"] == "Implemented a Python service."
