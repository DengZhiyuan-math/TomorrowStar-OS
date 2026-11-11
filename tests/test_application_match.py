"""Documentary job comparison preserves uncertainty and source responsibility."""

import json
import os
import subprocess
from copy import deepcopy
from functools import partial
from pathlib import Path

import pytest

from career_evidence_graph.application_match import calculate_match_score
from career_evidence_graph.application_resume import career_source_snapshot
from career_evidence_graph.application_worker import digest
from career_evidence_graph.career_portal_data import CareerCatalog, PortalDataError
from career_evidence_graph.codex_cli import CodexCLIError, run_codex_exec

pytestmark = pytest.mark.usefixtures("reading_limits")


def policy_case(identifier):
    document = json.loads(
        (Path(__file__).parent / "fixtures/application-match-v1.json").read_text()
    )
    case = next(item for item in document["cases"] if item["id"] == identifier)
    requirements = [
        dict(zip(("text", "importance", "judgment", "hard_condition"), row, strict=True))
        for row in case["requirements"]
    ]
    return requirements, case["expected"]


def test_fully_supported_requirements_match_the_confirmed_policy_vector():
    requirements, expected = policy_case("fully-supported")
    assert calculate_match_score(requirements) == expected


@pytest.mark.parametrize(
    "identifier",
    [
        "partial-support",
        "missing-evidence",
        "known-gap",
        "all-unknown",
        "same-career-python-jd",
        "same-career-rust-jd",
        "no-requirements",
    ],
)
def test_lower_upper_and_coverage_preserve_unknown_evidence(identifier):
    requirements, expected = policy_case(identifier)
    assert calculate_match_score(requirements) == expected


@pytest.mark.parametrize(
    "identifier",
    ["hard-unknown", "hard-conflict", "hard-partial", "hard-supported", "duplicate-requirement"],
)
def test_hard_conditions_are_independent_from_the_numeric_score(identifier):
    requirements, expected = policy_case(identifier)
    assert calculate_match_score(requirements) == expected


def test_partial_hard_condition_requires_input():
    requirements = [
        {
            "text": "Work permit",
            "importance": "required",
            "judgment": "partial",
            "hard_condition": True,
        }
    ]
    assert calculate_match_score(requirements) == {
        "lower": 50,
        "upper": 50,
        "coverage": 100,
        "eligibility": "needs_input",
    }


def test_duplicate_requirements_and_sources_do_not_raise_the_score():
    python = {
        "text": "Python",
        "importance": "required",
        "judgment": "supported",
        "hard_condition": False,
        "source_ids": ["source-a", "source-a"],
    }
    gap = {"text": "Rust", "importance": "preferred", "judgment": "gap", "hard_condition": False}
    assert calculate_match_score([python, python | {"text": "  PYTHON. "}, gap]) == {
        "lower": 75,
        "upper": 75,
        "coverage": 100,
        "eligibility": "not_specified",
    }


def test_conflicting_duplicate_judgments_and_invalid_categories_fail_closed():
    requirement = {
        "text": "Python",
        "importance": "required",
        "judgment": "supported",
        "hard_condition": False,
    }
    with pytest.raises(PortalDataError) as error:
        calculate_match_score([requirement, requirement | {"judgment": "unknown"}])
    assert error.value.code == "match_requirement_conflict"
    with pytest.raises(PortalDataError) as error:
        calculate_match_score([requirement | {"importance": "invented"}])
    assert error.value.code == "match_model_invalid"


@pytest.fixture
def match_inputs(tmp_path):
    career = tmp_path / "career"
    contributions = career / "contributions"
    contributions.mkdir(parents=True)
    (contributions / "python.md").write_text(
        "# Contribution candidate: Python service\n\n## Scope\nImplemented a Python service.\n\n"
        "## Responsibility attribution\n| Work | Owner |\n| --- | --- |\n"
        "| Implementation | User |\n"
        "\n## Boundaries\nNo GPU training claim.\n"
    )
    snapshot = career_source_snapshot(CareerCatalog(career))
    application = {
        "id": "synthetic-application",
        "revision": "application-v1",
        "company": "Synthetic",
        "role_title": "ML Engineer",
        "job_description": "Build reliable Python systems.",
        "notes": "Private local note sentinel; never send this to the model.",
    }
    return application, snapshot


def model_output(snapshot):
    source_id = snapshot["items"][0]["source_id"]
    return {
        "role_understanding": {
            "business_objective": "Build reliable Python systems.",
            "work_outputs": ["Reliable Python systems"],
            "methods_role": "Python is a means to deliver reliable systems.",
        },
        "requirements": [
            {
                "text": "Python",
                "importance": "required",
                "judgment": "supported",
                "hard_condition": False,
                "explanation": "Documentary implementation evidence.",
                "source_ids": [source_id],
                "citations": [
                    {"source_id": source_id, "quote": snapshot["items"][0]["text"][:4000]}
                ],
                "claim_scope": "personal_completed",
            }
        ],
        "selected_source_ids": [source_id],
        "selection_rationale": [
            {
                "source_id": source_id,
                "business_relevance": "Python service implementation supports system delivery.",
                "evidence_role": "direct_domain",
            }
        ],
        "extracted_fields": {
            "company": None,
            "role_title": "ML Engineer",
            "location": None,
            "uncertain_fields": ["company", "location"],
        },
        "limitations": ["Documentary evidence needs human review."],
    }


def persist_analysis_inputs(directory, application, sources):
    """Make native analyzer doubles retain the same bound inputs as analyze_job."""
    from career_evidence_graph._vendor import job_apply_store as helper
    from career_evidence_graph.application_match import match_configuration

    helper.atomic_write_json(
        directory / "input.json",
        {
            "application_id": application["id"],
            "application_revision": application["revision"],
            "job": {
                key: application.get(key, "")
                for key in ("company", "role_title", "location", "job_description")
            },
            "source_snapshot_revision": sources["revision"],
            "configuration": match_configuration(),
        },
    )
    helper.atomic_write_json(directory / "source-snapshot.json", sources)


def test_new_analysis_rejects_missing_business_interpretation(match_inputs, tmp_path):
    from career_evidence_graph.application_match import analyze_job

    application, snapshot = match_inputs
    output = model_output(snapshot)
    output.pop("role_understanding", None)
    with pytest.raises(PortalDataError) as error:
        analyze_job(
            application, snapshot, tmp_path / "missing-goal", runner=model_runner(output, [])
        )
    assert error.value.code == "match_model_invalid"


def test_analysis_preserves_business_interpretation_and_ordered_selection(match_inputs, tmp_path):
    from career_evidence_graph.application_match import analyze_job

    application, snapshot = match_inputs
    output = model_output(snapshot)
    result = analyze_job(
        application, snapshot, tmp_path / "business-goal", runner=model_runner(output, [])
    )
    assert result["role_understanding"] == {
        "business_objective": "Build reliable Python systems.",
        "work_outputs": ["Reliable Python systems"],
        "methods_role": "Python is a means to deliver reliable systems.",
    }
    assert result["selection_rationale"] == output["selection_rationale"]
    saved = json.loads((tmp_path / "business-goal" / "analysis.json").read_text())
    assert saved["role_understanding"] == result["role_understanding"]
    assert saved["selection_rationale"] == result["selection_rationale"]


@pytest.mark.parametrize(
    "mutation", ["blank-goal", "no-outputs", "blank-output", "missing-rationale", "wrong-source"]
)
def test_analysis_rejects_incomplete_business_selection(match_inputs, tmp_path, mutation):
    from career_evidence_graph.application_match import analyze_job

    application, snapshot = match_inputs
    output = model_output(snapshot)
    if mutation == "blank-goal":
        output["role_understanding"]["business_objective"] = "  "
    elif mutation == "no-outputs":
        output["role_understanding"]["work_outputs"] = []
    elif mutation == "blank-output":
        output["role_understanding"]["work_outputs"] = ["  "]
    elif mutation == "missing-rationale":
        output["selection_rationale"] = []
    else:
        output["selection_rationale"][0]["source_id"] = "another-source"
    with pytest.raises(PortalDataError) as error:
        analyze_job(application, snapshot, tmp_path / mutation, runner=model_runner(output, []))
    assert error.value.code == "match_model_invalid"


def test_business_evidence_without_title_keywords_reaches_analyzer(match_inputs, tmp_path):
    from career_evidence_graph.application_match import analyze_job

    application, _ = match_inputs
    application.update(
        role_title="Quantitative Research Intern",
        job_description="Research trading strategies, assess investment returns and risk.",
    )
    base = tmp_path / "career/contributions/python.md"
    base.write_text(base.read_text().replace("Python service", "AI quantitative model"))
    finance = base.parent / "options.md"
    finance.write_text(
        base.read_text().replace(
            "Implemented a AI quantitative model.",
            "Compared option premium income with transaction costs and drawdowns.",
        )
    )
    snapshot = career_source_snapshot(CareerCatalog(tmp_path / "career"))
    source = next(item for item in snapshot["items"] if item["source_name"].endswith("options.md"))
    output = model_output(snapshot)
    output["role_understanding"] = {
        "business_objective": "Assess trading strategy investment returns and risk.",
        "work_outputs": ["Trading strategy research"],
        "methods_role": "Quantitative methods support investment decisions.",
    }
    output["requirements"][0].update(
        text="Assess investment returns and risk",
        source_ids=[source["source_id"]],
        citations=[{"source_id": source["source_id"], "quote": source["text"]}],
    )
    output["selected_source_ids"] = [source["source_id"]]
    output["selection_rationale"] = [
        {
            "source_id": source["source_id"],
            "business_relevance": "Option income, costs and drawdowns inform investment decisions.",
            "evidence_role": "direct_domain",
        }
    ]
    calls = []
    result = analyze_job(
        application, snapshot, tmp_path / "business-evidence", runner=model_runner(output, calls)
    )
    assert "quantitative" not in source["text"].casefold()
    assert source["text"] in calls[-1][-1]
    assert "AI quantitative model" in calls[-1][-1]
    assert result["selected_source_ids"] == [source["source_id"]]
    assert result["selection_rationale"][0]["evidence_role"] == "direct_domain"


def model_runner(output, calls):
    def process(argv, **kwargs):
        calls.append([*argv[:-1], kwargs["input"]] if "input" in kwargs else argv)
        if argv[-1] == "--version":
            return subprocess.CompletedProcess(argv, 0, "codex-cli synthetic\n", "")
        fixture_output = deepcopy(output)
        schema = json.loads(Path(argv[argv.index("--output-schema") + 1]).read_text())
        if schema.get("title") == "_ControlledOutput" and isinstance(fixture_output, dict):
            context = json.loads(kwargs["input"].rsplit("\n", 1)[1])
            templates = context["match_requirements"]
            rows = fixture_output.get("requirements", [])
            if isinstance(rows, list) and len(rows) == len(templates):
                for row, template in zip(rows, templates, strict=True):
                    if not isinstance(row, dict) or "inference" in row:
                        continue
                    row["inference"] = {
                        "requirement_id": template["scoring_framework"]["requirement_id"],
                        "type": "direct",
                        "relation": {
                            "supported": "supports",
                            "partial": "partial_support",
                            "gap": "contradicts",
                            "unknown": "unresolved",
                        }.get(row.get("judgment"), "unresolved"),
                        "basis": "Recorded fixture judgment from cited source work.",
                        "expression_scope": ""
                        if row.get("judgment") == "unknown"
                        else "Use only the cited recorded work and responsibility.",
                        "calculation": None,
                    }
        event = {"type": "structured_result", "result": fixture_output}
        return subprocess.CompletedProcess(argv, 0, json.dumps(event) + "\n", "")

    return partial(run_codex_exec, runner=process)


def test_analyzer_runs_codex_boundary_with_no_url_or_profile(match_inputs, tmp_path):
    from career_evidence_graph.application_match import analyze_job

    application, snapshot = match_inputs
    calls = []
    directory = tmp_path / "analysis-v1"
    result = analyze_job(
        application, snapshot, directory, runner=model_runner(model_output(snapshot), calls)
    )
    assert result["id"] == "analysis-v1"
    assert result["score"] == {
        "lower": 100,
        "upper": 100,
        "coverage": 100,
        "eligibility": "not_specified",
    }
    assert result["selected_source_ids"] == [snapshot["items"][0]["source_id"]]
    assert result["source_snapshot_revision"] == snapshot["revision"]
    assert result["policy_version"] == "documentary-match/v1"
    assert result["requirements"][0]["sources"][0]["review_status"] == "documentary"
    assert application["notes"] not in calls[-1][-1]
    assert application["job_description"] in calls[-1][-1]
    assert json.loads((directory / "model-result.json").read_text())["raw_stdout_jsonl"]


@pytest.mark.parametrize(
    "mutation,code",
    [
        ("missing-reference", "match_source_invalid"),
        ("unavailable-source", "match_source_invalid"),
        ("unmapped-selection", "match_source_invalid"),
        ("model-score", "match_model_invalid"),
        ("review-upgrade", "match_model_invalid"),
    ],
)
def test_model_cannot_forge_sources_selection_review_or_final_score(
    match_inputs, tmp_path, mutation, code
):
    from career_evidence_graph.application_match import analyze_job

    application, original = match_inputs
    snapshot = deepcopy(original)
    output = model_output(snapshot)
    if mutation == "missing-reference":
        output["requirements"][0]["source_ids"] = ["missing:Scope"]
    elif mutation == "unavailable-source":
        snapshot["documents"][0]["available"] = False
        snapshot["revision"] = digest(
            {key: value for key, value in snapshot.items() if key != "revision"}
        )
    elif mutation == "unmapped-selection":
        output["requirements"][0].update(judgment="unknown", source_ids=[], claim_scope="unknown")
    elif mutation == "model-score":
        output["score"] = 100
    else:
        output["requirements"][0]["review_status"] = "reviewed"
    directory = tmp_path / "rejected-analysis"
    if code == "match_model_invalid":
        with pytest.raises(PortalDataError) as error:
            analyze_job(application, snapshot, directory, runner=model_runner(output, []))
        assert error.value.code == code
        assert "Implemented" not in str(error.value)
        assert not (directory / "analysis.json").exists()
    else:
        result = analyze_job(application, snapshot, directory, runner=model_runner(output, []))
        requirement = result["requirements"][0]
        assert requirement["judgment"] == "unknown"
        assert requirement["claim_scope"] == "unknown"
        assert requirement["citation_warning"]
        assert requirement["model_explanation"] == output["requirements"][0]["explanation"]
        assert result["selected_source_ids"] == []
        assert result["limitations"]
        assert all(source["available"] for source in requirement["sources"])
        assert (directory / "analysis.json").exists()
    saved_model = json.loads((directory / "model-result.json").read_text())
    assert saved_model["structured_result"] == output


@pytest.mark.parametrize("kind", ["team", "design", "document-bypass", "team-documentary"])
def test_other_work_and_design_cannot_be_promoted_to_personal_implementation(
    match_inputs, tmp_path, kind
):
    from career_evidence_graph.application_match import analyze_job

    application, _ = match_inputs
    path = tmp_path / "career/contributions/python.md"
    if kind == "design":
        path.write_text(
            path.read_text().replace("Implemented a Python service.", "Designed a Python service.")
        )
    else:
        path.write_text(
            path.read_text().replace("| Implementation | User |", "| Implementation | Team |")
        )
    snapshot = career_source_snapshot(CareerCatalog(tmp_path / "career"))
    output = model_output(snapshot)
    if kind == "document-bypass":
        output["requirements"][0]["source_ids"] = [snapshot["documents"][0]["id"] + ":document"]
        output["selected_source_ids"] = []
        output["selection_rationale"] = []
    elif kind == "team-documentary":
        output["requirements"][0]["claim_scope"] = "documentary"
    directory = tmp_path / "bad-ownership"
    result = analyze_job(application, snapshot, directory, runner=model_runner(output, []))
    requirement = result["requirements"][0]
    assert requirement["judgment"] == "unknown"
    assert requirement["claim_scope"] == "unknown"
    assert requirement["citation_warning"]
    assert requirement["model_explanation"] == output["requirements"][0]["explanation"]
    assert result["selected_source_ids"] == []
    assert result["score"]["lower"] == 0
    assert result["score"]["upper"] == 100
    if kind == "document-bypass":
        assert requirement["sources"] == []
    else:
        assert requirement["sources"][0]["attribution"] == snapshot["items"][0]["attribution"]
    assert (directory / "model-result.json").exists()
    assert (directory / "analysis.json").exists()


def test_team_context_can_remain_unknown_without_becoming_a_capability_gap(match_inputs, tmp_path):
    from career_evidence_graph.application_match import analyze_job

    application, _ = match_inputs
    path = tmp_path / "career/contributions/python.md"
    path.write_text(
        path.read_text().replace("| Implementation | User |", "| Implementation | Team |")
    )
    snapshot = career_source_snapshot(CareerCatalog(tmp_path / "career"))
    output = model_output(snapshot)
    output["requirements"][0].update(judgment="unknown", claim_scope="team")
    output["selected_source_ids"] = []
    output["selection_rationale"] = []
    result = analyze_job(
        application, snapshot, tmp_path / "unknown-team", runner=model_runner(output, [])
    )
    assert result["score"] == {
        "lower": 0,
        "upper": 100,
        "coverage": 0,
        "eligibility": "not_specified",
    }
    assert "Team" in result["requirements"][0]["sources"][0]["attribution"]


def test_model_gap_proposal_requires_fact_review_and_cannot_become_a_known_conflict(
    match_inputs, tmp_path
):
    from career_evidence_graph.application_match import analyze_job

    application, snapshot = match_inputs
    output = model_output(snapshot)
    output["requirements"][0].update(
        text="Release operations",
        judgment="gap",
        hard_condition=True,
        claim_scope="documentary",
        explanation="The cited contribution does not establish release-operation capability.",
    )
    result = analyze_job(
        application, snapshot, tmp_path / "gap-proposal", runner=model_runner(output, [])
    )
    requirement = result["requirements"][0]
    assert requirement["proposed_judgment"] == "gap"
    assert requirement["gap_review_required"] is True
    assert requirement["judgment"] == "unknown"
    assert result["score"] == {
        "lower": 0,
        "upper": 100,
        "coverage": 0,
        "eligibility": "needs_input",
    }


def test_whole_document_cannot_extend_personal_scope_to_team_context(match_inputs, tmp_path):
    from career_evidence_graph.application_match import analyze_job

    application, _ = match_inputs
    path = tmp_path / "career/contributions/python.md"
    path.write_text(
        path.read_text() + "\n## Team context\nThe team implemented a CUDA accelerator.\n"
    )
    snapshot = career_source_snapshot(CareerCatalog(tmp_path / "career"))
    output = model_output(snapshot)
    output["requirements"][0].update(
        text="CUDA implementation", source_ids=[snapshot["documents"][0]["id"] + ":document"]
    )
    output["selected_source_ids"] = []
    output["selection_rationale"] = []
    directory = tmp_path / "document-scope-escape"
    result = analyze_job(application, snapshot, directory, runner=model_runner(output, []))
    requirement = result["requirements"][0]
    assert requirement["judgment"] == "unknown"
    assert requirement["claim_scope"] == "unknown"
    assert requirement["sources"] == []
    assert requirement["citation_warning"]
    assert requirement["model_explanation"] == output["requirements"][0]["explanation"]
    assert result["selected_source_ids"] == []
    assert (directory / "model-result.json").exists()
    assert (directory / "analysis.json").exists()


@pytest.mark.parametrize(
    "scope,source_state,selected,warning_kind",
    [
        ("documentary", "available", False, None),
        ("personal_completed", "available", False, "attribution"),
        ("personal_design", "available", False, "attribution"),
        ("team", "available", False, "attribution"),
        ("other", "available", False, "attribution"),
        ("documentary", "unavailable", False, "source"),
        ("documentary", "revision_mismatch", False, "source"),
        ("documentary", "available", True, "selection"),
    ],
)
def test_education_has_an_exact_documentary_locator_without_personal_mastery(
    match_inputs, tmp_path, scope, source_state, selected, warning_kind
):
    from career_evidence_graph.application_match import analyze_job
    from career_evidence_graph.application_worker import digest

    application, _ = match_inputs
    (tmp_path / "career/contributions/python.md").unlink()
    profile = tmp_path / "career/sources/profile.json"
    profile.parent.mkdir(exist_ok=True)
    profile.write_text(
        json.dumps(
            {
                "name": "Synthetic Person",
                "education": [
                    {
                        "degree": "MSc Mathematics",
                        "institution": "Synthetic University",
                        "period": "2020–2022",
                        "detail": "Completed degree; self-reported.",
                    }
                ],
            }
        )
    )
    snapshot = career_source_snapshot(CareerCatalog(tmp_path / "career"))
    source_id = snapshot["profile_source"]["id"] + ":profile.education[0]"
    if source_state != "available":
        document = next(
            row for row in snapshot["documents"] if row["id"] == snapshot["profile_source"]["id"]
        )
        if source_state == "unavailable":
            document["available"] = False
        else:
            document["revision"] = "b" * 64
        snapshot["revision"] = digest({k: v for k, v in snapshot.items() if k != "revision"})
    output = {
        "role_understanding": {
            "business_objective": "Deliver the systems described in the JD.",
            "work_outputs": ["Reliable systems"],
            "methods_role": "Technical methods support reliable system delivery.",
        },
        "requirements": [
            {
                "text": "A mathematics degree",
                "importance": "required",
                "judgment": "supported",
                "hard_condition": True,
                "explanation": "The profile states a mathematics degree, pending verification.",
                "source_ids": [source_id],
                "citations": [{"source_id": source_id, "quote": "MSc Mathematics"}],
                "claim_scope": scope,
            }
        ],
        "selected_source_ids": [source_id] if selected else [],
        "selection_rationale": [
            {
                "source_id": source_id,
                "business_relevance": "Documentary background for the role.",
                "evidence_role": "transferable",
            }
        ]
        if selected
        else [],
        "extracted_fields": {
            "company": None,
            "role_title": None,
            "location": None,
            "uncertain_fields": ["company", "role_title", "location"],
        },
        "limitations": ["Education is documentary and not independently verified."],
    }
    calls = []
    directory = tmp_path / "education"
    result = analyze_job(application, snapshot, directory, runner=model_runner(output, calls))
    requirement = result["requirements"][0]
    assert result["selected_source_ids"] == []
    if source_state == "available":
        evidence = requirement["sources"][0]
        assert evidence["locator"] == "profile.education[0]"
        assert evidence["review_status"] == "documentary"
        assert evidence["rewrite_allowed"] is False
        assert evidence["attribution"] == "Editorial statement; review required"
        assert "MSc Mathematics" in calls[-1][-1]
    else:
        assert requirement["sources"] == []
    if warning_kind in {"source", "attribution"}:
        assert requirement["judgment"] == "unknown"
        assert requirement["claim_scope"] == "unknown"
        assert requirement["citation_warning"]
        assert requirement["model_explanation"] == output["requirements"][0]["explanation"]
        assert result["score"]["lower"] == 0
        assert result["score"]["upper"] == 100
    else:
        assert requirement["judgment"] == "supported"
        assert result["score"]["lower"] == 100
    if selected:
        assert result["limitations"]
    assert (directory / "model-result.json").exists()
    assert (directory / "analysis.json").exists()


@pytest.mark.parametrize(
    "failure,code",
    [
        (FileNotFoundError("Synthetic missing CLI"), "match_cli_missing"),
        (
            subprocess.TimeoutExpired("codex", 1, output="synthetic private raw"),
            "match_model_timeout",
        ),
        (
            CodexCLIError(
                "Synthetic authentication failure", redacted_stderr="not logged in; login required"
            ),
            "match_cli_auth_required",
        ),
        (
            CodexCLIError(
                "Other synthetic failure", raw_stdout_jsonl="synthetic partial private output"
            ),
            "match_model_unavailable",
        ),
    ],
)
def test_model_failures_keep_private_evidence_and_return_only_safe_errors(
    match_inputs, tmp_path, failure, code
):
    from career_evidence_graph.application_match import analyze_job

    application, snapshot = match_inputs

    def fail(config, prompt, **kwargs):
        raise failure

    directory = tmp_path / "failed-analysis"
    with pytest.raises(PortalDataError) as error:
        analyze_job(application, snapshot, directory, runner=fail)
    assert error.value.code == code
    assert "synthetic private" not in str(error.value)
    saved = json.loads((directory / "model-result.json").read_text())
    assert saved["status"] == "failed"
    assert saved["error_type"] == type(failure).__name__
    assert (directory / "source-snapshot.json").exists()
    assert not (directory / "analysis.json").exists()


def test_long_sources_disclose_exact_omission_and_truncation_but_keep_complete_jd(
    match_inputs, tmp_path
):
    from career_evidence_graph.application_match import MAX_PROMPT_BYTES, analyze_job

    application, _ = match_inputs
    application["job_description"] = "Python work. " * 300 + "COMPLETE JD TAIL"
    path = tmp_path / "career/contributions/python.md"
    path.write_text(
        path.read_text().replace(
            "Implemented a Python service.",
            "Implemented a Python service. " + "source-text " * 20000,
        )
    )
    (path.parent / "second-source.md").write_text(path.read_text())
    snapshot = career_source_snapshot(CareerCatalog(tmp_path / "career"))
    calls = []
    result = analyze_job(
        application,
        snapshot,
        tmp_path / "bounded-context",
        runner=model_runner(model_output(snapshot), calls),
    )
    prompt = calls[-1][-1]
    assert len(prompt.encode()) <= MAX_PROMPT_BYTES
    assert application["job_description"] in prompt
    assert result["coverage"]["truncated"] is True
    truncation = result["coverage"]["truncated_sources"][0]
    assert truncation["source_id"] == snapshot["items"][0]["source_id"]
    assert 0 < truncation["included_chars"] < truncation["original_chars"]
    assert result["coverage"]["omitted_source_ids"]


def test_overlong_jd_fails_explicitly_before_any_model_call(match_inputs, tmp_path):
    from career_evidence_graph.application_match import MAX_JD_BYTES, analyze_job

    application, snapshot = match_inputs
    application["job_description"] = "x" * (MAX_JD_BYTES + 1)
    calls = []
    with pytest.raises(PortalDataError) as error:
        analyze_job(
            application,
            snapshot,
            tmp_path / "overlong-jd",
            runner=model_runner(model_output(snapshot), calls),
        )
    assert error.value.code == "match_jd_too_large"
    assert calls == []
    assert (
        json.loads((tmp_path / "overlong-jd/input.json").read_text())["job"]["job_description"]
        == application["job_description"]
    )


def test_forty_second_contribution_can_be_selected_without_legacy_resume_limits(
    match_inputs, tmp_path
):
    from career_evidence_graph.application_match import analyze_job

    application, _ = match_inputs
    base = tmp_path / "career/contributions/python.md"
    for index in range(41):
        (base.parent / f"additional-{index:02d}.md").write_text(
            base.read_text().replace("Python service", f"Python service {index}")
        )
    snapshot = career_source_snapshot(CareerCatalog(tmp_path / "career"))
    target = snapshot["items"][-1]
    output = model_output(snapshot)
    output["requirements"][0]["source_ids"] = [target["source_id"]]
    output["requirements"][0]["citations"] = [
        {"source_id": target["source_id"], "quote": target["text"]}
    ]
    output["selected_source_ids"] = [target["source_id"]]
    output["selection_rationale"][0]["source_id"] = target["source_id"]
    calls = []
    result = analyze_job(
        application, snapshot, tmp_path / "all-contributions", runner=model_runner(output, calls)
    )
    assert len(snapshot["items"]) == 42
    assert all(
        item["source_id"] in result["coverage"]["included_source_ids"] for item in snapshot["items"]
    )
    # The model sees the call-local handle of the selected contribution.
    assert '"' + result["coverage"]["source_aliases"][target["source_id"]] + '"' in calls[-1][-1]
    assert result["selected_source_ids"] == [target["source_id"]]


def test_snapshot_tampering_is_rejected_before_the_model_runs(match_inputs, tmp_path):
    from career_evidence_graph.application_match import analyze_job

    application, snapshot = match_inputs
    snapshot["items"][0]["attribution"] = "Forged ownership"
    calls = []
    with pytest.raises(PortalDataError) as error:
        analyze_job(
            application,
            snapshot,
            tmp_path / "invalid-snapshot",
            runner=model_runner(model_output(snapshot), calls),
        )
    assert error.value.code == "match_snapshot_invalid"
    assert calls == []


def test_configuration_revision_binds_schema_and_settings_but_not_executable(monkeypatch):
    from career_evidence_graph.application_match import (
        match_configuration,
        match_configuration_revision,
    )

    initial = match_configuration_revision()
    assert initial.startswith("cfg2:")
    assert len(match_configuration()["engine_sha256"]) == 64
    assert len(match_configuration()["output_schema_sha256"]) == 64
    # The Codex path is provenance: recorded, never part of the revision (APP-15).
    monkeypatch.setenv("TOMORROWSTAR_CODEX_EXECUTABLE", "/synthetic/other-codex")
    assert match_configuration()["executable"] == "/synthetic/other-codex"
    assert match_configuration_revision() == initial
    monkeypatch.setattr("career_evidence_graph.application_match.PROMPT_VERSION", "synthetic/v0")
    assert match_configuration_revision() != initial
    assert match_configuration()["sandbox"] == "read-only"


def test_existing_analysis_directory_and_artifacts_are_never_overwritten(match_inputs, tmp_path):
    from career_evidence_graph.application_match import analyze_job

    application, snapshot = match_inputs
    calls = []
    directory = tmp_path / "immutable-analysis"
    analyze_job(
        application, snapshot, directory, runner=model_runner(model_output(snapshot), calls)
    )
    saved = (directory / "analysis.json").read_bytes()
    with pytest.raises(PortalDataError) as error:
        analyze_job(
            application, snapshot, directory, runner=model_runner(model_output(snapshot), calls)
        )
    assert error.value.code == "match_directory_exists"
    assert (directory / "analysis.json").read_bytes() == saved
    assert len(calls) == 2


def test_configuration_tracks_path_resolution_and_replacement_without_running_cli(tmp_path):
    from career_evidence_graph.application_match import match_configuration

    first_bin, second_bin = tmp_path / "first-bin", tmp_path / "second-bin"
    first_bin.mkdir()
    second_bin.mkdir()
    first, second = first_bin / "codex", second_bin / "codex"
    for executable in (first, second):
        executable.write_text("Synthetic binary; never execute this file.")
        executable.chmod(0o700)
    before = match_configuration({"PATH": str(first_bin)})
    switched = match_configuration({"PATH": str(second_bin)})
    assert before["resolved_executable"] == str(first.resolve())
    assert switched["resolved_executable"] == str(second.resolve())
    assert digest(before) != digest(switched)
    first.write_text("Changed synthetic binary; never execute this file.")
    assert digest(match_configuration({"PATH": str(first_bin)})) != digest(before)
    invalid = match_configuration(
        {"PATH": str(first_bin), "TOMORROWSTAR_CODEX_EXECUTABLE": str(tmp_path / "missing-codex")}
    )
    assert invalid["resolved_executable"] is None
    assert invalid["executable_status"] == "unavailable"


def test_model_uses_the_same_frozen_environment_as_its_configuration(
    match_inputs, tmp_path, monkeypatch
):
    from career_evidence_graph.application_input_binding import configuration_revision
    from career_evidence_graph.application_match import analyze_job, match_configuration

    application, snapshot = match_inputs
    original_path = os.environ.get("PATH", "")
    expected = configuration_revision(match_configuration(dict(os.environ)))
    wrapped = model_runner(model_output(snapshot), [])

    def run(config, prompt, **kwargs):
        monkeypatch.setenv("PATH", str(tmp_path / "changed-after-freeze"))
        assert kwargs["environment"]["PATH"] == original_path
        assert kwargs["environment"] is not os.environ
        return wrapped(config, prompt, **kwargs)

    result = analyze_job(application, snapshot, tmp_path / "frozen-environment", runner=run)
    assert result["configuration_revision"] == expected


def test_explicit_missing_cli_never_falls_back_to_path_codex(match_inputs, tmp_path, monkeypatch):
    from career_evidence_graph.application_match import analyze_job

    application, snapshot = match_inputs
    monkeypatch.setenv("TOMORROWSTAR_CODEX_EXECUTABLE", str(tmp_path / "does-not-exist"))
    calls = []
    with pytest.raises(PortalDataError) as error:
        analyze_job(
            application,
            snapshot,
            tmp_path / "invalid-explicit-cli",
            runner=model_runner(model_output(snapshot), calls),
        )
    assert error.value.code == "match_cli_missing"
    assert calls == []
