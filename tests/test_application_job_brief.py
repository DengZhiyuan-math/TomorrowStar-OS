"""JD-only interpretation fixes reusable business weights before candidate retrieval."""

import json
import subprocess
from copy import deepcopy
from types import SimpleNamespace

import pytest

from career_evidence_graph.application_job_brief import (
    brief_requirements,
    calculate_framework_score,
    create_job_brief,
    route_for_score,
    validate_job_brief,
)
from career_evidence_graph.application_worker import digest
from career_evidence_graph.career_portal_data import PortalDataError
from career_evidence_graph.codex_cli import CodexCLIError


@pytest.fixture
def application():
    return {
        "id": "app-1",
        "revision": "old",
        "company": "Example Quant",
        "role_title": "Quant",
        "location": "Zurich",
        "job_description": (
            "Research pricing models and validate risk. Use Python or C++. "
            "Communicate results. Work permit required."
        ),
    }


@pytest.fixture
def output():
    return {
        "business_object": "Pricing and risk decisions",
        "role_understanding": {
            "business_objective": "Improve pricing and risk decisions",
            "work_outputs": ["Validated pricing models"],
            "methods_role": "Python or C++ implements the models",
        },
        "groups": [
            {
                "label": "Business",
                "jd_quote": "Research pricing models and validate risk.",
                "operator": "all",
                "importance": "required",
                "hard_condition": False,
                "weight": 80,
                "weight_reason": "Primary business output",
                "requirements": [
                    {"text": "Research pricing models", "jd_quote": "Research pricing models"},
                    {"text": "Validate risk", "jd_quote": "validate risk"},
                ],
            },
            {
                "label": "Methods",
                "jd_quote": "Use Python or C++.",
                "operator": "any",
                "importance": "preferred",
                "hard_condition": False,
                "weight": 20,
                "weight_reason": "Tools serving business output",
                "requirements": [
                    {"text": "Python", "jd_quote": "Python"},
                    {"text": "C++", "jd_quote": "C++"},
                ],
            },
        ],
    }


def runner_for(output, calls=None):
    def runner(config, prompt, **kwargs):
        if calls is not None:
            calls.append((config, prompt, kwargs))
        return SimpleNamespace(
            structured_result=deepcopy(output),
            model_dump=lambda **_: {
                "status": "completed",
                "structured_result": deepcopy(output),
            },
        )

    return runner


def brief(tmp_path, application, output):
    return create_job_brief(
        application, tmp_path / "brief", runner=runner_for(output), environment={}
    )


def judged_rows(value, judgments):
    return [
        row | {"judgment": judgments.get(row["text"], "unknown")}
        for row in brief_requirements(value)
    ]


def test_quant_business_output_outweighs_keyword_only_match(tmp_path, application, output):
    value = brief(tmp_path, application, output)
    rows = judged_rows(
        value,
        {
            "Research pricing models": "gap",
            "Validate risk": "gap",
            "Python": "supported",
            "C++": "gap",
        },
    )
    assert calculate_framework_score(rows) == {
        "lower": 20,
        "upper": 20,
        "coverage": 100,
        "eligibility": "not_specified",
    }
    assert route_for_score(calculate_framework_score(rows)) == {
        "route": "matched",
        "auto_skip": False,
    }
    # Group conservation: splitting the business output never creates new weight.
    weights = {row["text"]: row["scoring_framework"] for row in rows}
    assert (
        weights["Research pricing models"]["weight_numerator"]
        / weights["Research pricing models"]["weight_denominator"]
        == 40
    )
    assert weights["Python"]["weight_numerator"] / weights["Python"]["weight_denominator"] == 10


def test_call_is_jd_only_and_durable_reuse_ignores_candidate_changes(tmp_path, application, output):
    calls = []
    application["candidate_secret"] = "PRIVATE_APPLICANT_SENTINEL"
    value = create_job_brief(
        application, tmp_path / "brief", runner=runner_for(output, calls), environment={}
    )
    changed = application | {"id": "app-2", "revision": "new", "candidate_secret": "other"}
    assert create_job_brief(changed, tmp_path / "brief", runner=runner_for(output, calls)) == value
    assert len(calls) == 1
    assert "PRIVATE_APPLICANT_SENTINEL" not in calls[0][1]
    assert "candidate_secret" not in json.dumps(
        json.loads((tmp_path / "brief/job-brief-input.json").read_text())
    )
    assert set(path.name for path in (tmp_path / "brief").iterdir()) == {
        "attempt.json",
        "job-brief.json",
        "job-brief-schema.json",
        "job-brief-input.json",
        "job-brief-prompt.json",
        "job-brief-result.json",
    }
    with pytest.raises(PortalDataError):
        validate_job_brief(value, application | {"job_description": "Changed JD"})


def test_generated_quotes_reuse_original_jd_case_and_whitespace(tmp_path, application, output):
    application["job_description"] = "We’re\u00a0researching\n pricing models. Use Python or C++."
    output["groups"][0].update(
        jd_quote="we’re researching pricing models.",
        requirements=[
            {"text": "Research pricing models", "jd_quote": "researching pricing MODELS"}
        ],
    )
    value = brief(tmp_path, application, output)
    assert value["job"]["job_description"] == (
        "We’re\u00a0researching\n pricing models. Use Python or C++."
    )
    assert value["groups"][0]["jd_quote"] == "We’re\u00a0researching\n pricing models."
    assert value["groups"][0]["requirements"][0]["jd_quote"] == "researching\n pricing models"
    assert validate_job_brief(value, application) == value
    raw = json.loads((tmp_path / "brief/job-brief-result.json").read_text())
    assert raw["structured_result"]["groups"][0]["jd_quote"] == "we’re researching pricing models."


def test_group_quote_may_join_separate_literal_jd_passages(tmp_path, application, output):
    # Installed MC-11: a real group summarized non-adjacent JD bullets, one per line.
    output["groups"][0]["jd_quote"] = (
        "Research pricing models and validate risk.\ncommunicate results."
    )
    value = brief(tmp_path, application, output)
    assert value["groups"][0]["jd_quote"] == (
        "Research pricing models and validate risk.\nCommunicate results."
    )
    assert validate_job_brief(value, application) == value


def test_joined_group_quote_still_rejects_a_passage_not_in_the_jd(tmp_path, application, output):
    output["groups"][0]["jd_quote"] = "Research pricing models and validate risk.\nEarn profits."
    with pytest.raises(PortalDataError) as error:
        brief(tmp_path, application, output)
    assert error.value.code == "job_brief_invalid"


@pytest.mark.parametrize(
    "jd,quote",
    [
        ("Use C++.", "c+"),
        ("Use C++.", "c"),
        ("At least 1.5 Years.", "5 years"),
        ("At least 1.5 Years.", "15 years"),
        ("At least 1,5 Years.", "5 years"),
        ("Salary 15,000 USD.", "000 usd"),
        ("Level 1,5 required.", "level 1"),
        ("At least 1–5 Years.", "5 years"),
        ("At least 1—5 Years.", "5 years"),
        ("At least 1−5 Years.", "5 years"),
        ("Years 1–5.", "years 1"),
        ("Pythonic research.", "python"),
        ("Research pricing models.", "re search pricing models"),
        ("Research pricing models.", "research pricingmodels"),
        ("We’re researching models.", "we're researching models."),
        ("Research pricing models.", "research pricing models!"),
        ("Use Python or C++.", "use python and c++."),
        ("Use Python.", "use Ｐｙｔｈｏｎ."),
        ("Research pricing models.", " \t\n"),
    ],
)
def test_quote_alignment_does_not_repair_changed_content(tmp_path, application, output, jd, quote):
    application["job_description"] = jd
    output["groups"] = [output["groups"][0]]
    output["groups"][0].update(
        jd_quote=jd, requirements=[{"text": "Synthetic requirement", "jd_quote": quote}]
    )
    with pytest.raises(PortalDataError) as error:
        brief(tmp_path, application, output)
    assert error.value.code == "job_brief_invalid"
    assert not (tmp_path / "brief/job-brief.json").exists()
    assert (tmp_path / "brief/job-brief-result.json").exists()


@pytest.mark.parametrize(
    "jd,quote",
    [("At least 1,5 Years.", "5 Years"), ("At least 1–5 Years.", "5 Years"), ("Use C++.", "C")],
)
def test_exact_legacy_quotes_remain_unchanged(tmp_path, application, output, jd, quote):
    application["job_description"] = jd
    output["groups"] = [output["groups"][0]]
    output["groups"][0].update(
        jd_quote=jd, requirements=[{"text": "Synthetic requirement", "jd_quote": quote}]
    )
    value = brief(tmp_path, application, output)
    assert value["groups"][0]["requirements"][0]["jd_quote"] == quote
    assert validate_job_brief(value, application) == value


@pytest.mark.parametrize(
    "quote,expected", [("python.", "PYTHON."), ("Python.", "Python."), (" \tpython.\n", "PYTHON.")]
)
def test_quote_alignment_prefers_exact_then_first_source_span(
    tmp_path, application, output, quote, expected
):
    application["job_description"] = "PYTHON. Python. PYTHON."
    output["groups"] = [output["groups"][0]]
    output["groups"][0].update(jd_quote=quote, requirements=[{"text": "Python", "jd_quote": quote}])
    value = brief(tmp_path, application, output)
    assert value["groups"][0]["jd_quote"] == expected
    assert value["groups"][0]["requirements"][0]["jd_quote"] == expected
    saved = (tmp_path / "brief/job-brief.json").read_bytes()
    calls = []
    assert (
        create_job_brief(application, tmp_path / "brief", runner=runner_for(output, calls)) == value
    )
    assert calls == []
    assert (tmp_path / "brief/job-brief.json").read_bytes() == saved


def test_saved_quotes_must_remain_literal_even_with_recomputed_hashes(
    tmp_path, application, output
):
    value = brief(tmp_path, application, output)
    value["groups"][0]["jd_quote"] = "research pricing models and validate risk."
    value["framework_revision"] = digest(
        {"protocol": "business-group-framework/v1", "groups": value["groups"]}
    )
    value["revision"] = digest({key: item for key, item in value.items() if key != "revision"})
    path = tmp_path / "brief/job-brief.json"
    path.write_text(json.dumps(value), encoding="utf-8")
    saved = path.read_bytes()
    calls = []
    with pytest.raises(PortalDataError) as error:
        create_job_brief(application, path.parent, runner=runner_for(output, calls))
    assert error.value.code == "job_brief_invalid"
    assert calls == []
    assert path.read_bytes() == saved


def test_normalized_exact_duplicates_do_not_inflate_group_weight(tmp_path, application, output):
    output["groups"][0]["requirements"].append(
        {"text": "  ＲＥＳＥＡＲＣＨ pricing models. ", "jd_quote": "Research pricing models"}
    )
    output["groups"].append(deepcopy(output["groups"][0]))
    value = brief(tmp_path, application, output)
    assert len(value["groups"]) == 2
    assert len(brief_requirements(value)) == 4
    assert sum(group["weight"] for group in value["groups"]) == 100


@pytest.mark.parametrize(
    "mutation", ["duplicate-weight", "overlap", "quote", "empty-output", "schema"]
)
def test_invalid_interpretation_is_retained_without_retry(tmp_path, application, output, mutation):
    if mutation == "duplicate-weight":
        duplicate = deepcopy(output["groups"][0])
        duplicate["weight"] = 70
        output["groups"].append(duplicate)
    elif mutation == "overlap":
        output["groups"][1]["requirements"].append(deepcopy(output["groups"][0]["requirements"][0]))
    elif mutation == "quote":
        output["groups"][0]["requirements"][0]["jd_quote"] = "Earn trading profits"
    elif mutation == "empty-output":
        output["role_understanding"]["work_outputs"] = [" "]
    else:
        output["applicant_verdict"] = "good"
    calls = []
    with pytest.raises(PortalDataError):
        create_job_brief(application, tmp_path / "brief", runner=runner_for(output, calls))
    with pytest.raises(PortalDataError) as error:
        create_job_brief(application, tmp_path / "brief", runner=runner_for(output, calls))
    assert error.value.code == "job_brief_attempt_exists"
    assert len(calls) == 1
    assert (tmp_path / "brief/job-brief-result.json").exists()
    assert not (tmp_path / "brief/job-brief.json").exists()


@pytest.mark.parametrize(
    "failure,code",
    [
        (CodexCLIError("service failed"), "job_brief_unavailable"),
        (CodexCLIError("configured Codex CLI executable is unavailable"), "match_cli_missing"),
        (FileNotFoundError("missing executable"), "match_cli_missing"),
        (subprocess.TimeoutExpired("synthetic-model", 180), "match_model_timeout"),
        (
            CodexCLIError("service failed", redacted_stderr="Login required"),
            "match_cli_auth_required",
        ),
    ],
)
def test_failed_call_never_retries_same_directory(tmp_path, application, failure, code):
    calls = []

    def fail(*args, **kwargs):
        calls.append(1)
        failure.raw_stdout_jsonl = "retained"
        raise failure

    with pytest.raises(PortalDataError) as error:
        create_job_brief(application, tmp_path / "brief", runner=fail)
    assert error.value.code == code
    with pytest.raises(PortalDataError):
        create_job_brief(application, tmp_path / "brief", runner=fail)
    assert calls == [1]
    assert (
        json.loads((tmp_path / "brief/job-brief-result.json").read_text())["raw_stdout_jsonl"]
        == "retained"
    )


@pytest.mark.parametrize(
    "operator,judgments,expected",
    [
        ("all", ["supported", "gap"], (50, 50, "conflict")),
        ("any", ["supported", "gap"], (100, 100, "supported")),
        ("all", ["supported", "partial"], (75, 75, "needs_input")),
        ("any", ["gap", "unknown"], (0, 100, "needs_input")),
        ("any", ["gap", "gap"], (0, 0, "conflict")),
    ],
)
def test_all_any_eligibility_and_uncertainty(
    tmp_path, application, output, operator, judgments, expected
):
    output["groups"] = [output["groups"][0]]
    output["groups"][0].update(operator=operator, hard_condition=True)
    value = brief(tmp_path, application, output)
    rows = judged_rows(
        value, dict(zip(["Research pricing models", "Validate risk"], judgments, strict=True))
    )
    score = calculate_framework_score(rows)
    assert (score["lower"], score["upper"], score["eligibility"]) == expected
    assert score["coverage"] == 100 - (expected[1] - expected[0])
    assert not route_for_score(score)["auto_skip"]
    assert route_for_score(score)["route"] == (
        "hold"
        if expected[2] == "conflict"
        else "needs_input"
        if expected[2] == "needs_input"
        else "matched"
    )


@pytest.mark.parametrize(
    "marks,expected",
    [
        # The model's fit is kept inside its judgment's band, in steps of 5.
        ({"judgment": "partial", "fit_score": 62}, (80, 80)),
        ({"judgment": "partial", "fit_score": 95}, (87.5, 87.5)),
        ({"judgment": "unknown", "fit_score": 40}, (57.5, 57.5)),
        ({"judgment": "gap", "fit_score": 30}, (50, 50)),
        # An unread source or a withheld citation is not evidence of absence.
        (
            {"judgment": "unknown", "fit_score": 5, "evidence_state": "context_not_fully_read"},
            (50, 100),
        ),
        (
            {
                "judgment": "unknown",
                "citation_warning": "match_source_invalid",
                "proposed_judgment": "partial",
                "proposed_fit_score": 60,
            },
            (50, 80),
        ),
    ],
)
def test_model_fit_scores_give_one_score_inside_their_bands(
    tmp_path, application, output, marks, expected
):
    # Decided 2026-10-31: wide intervals from many unknown or partial items gave the
    # user no usable score; the model now scores each requirement inside its band.
    output["groups"] = [output["groups"][0]]
    output["groups"][0].update(operator="all", hard_condition=False)
    rows = judged_rows(
        brief(tmp_path, application, output),
        {"Research pricing models": "supported", "Validate risk": marks["judgment"]},
    )
    rows[0]["fit_score"] = 100
    rows[1].update(marks)
    score = calculate_framework_score(rows)
    assert (score["lower"], score["upper"]) == expected


def test_hard_conflict_cannot_be_offset_by_business_advantages(tmp_path, application, output):
    output["groups"][1]["hard_condition"] = True
    rows = judged_rows(
        brief(tmp_path, application, output),
        {
            "Research pricing models": "supported",
            "Validate risk": "supported",
            "Python": "gap",
            "C++": "gap",
        },
    )
    score = calculate_framework_score(rows)
    assert score["lower"] == 80
    assert score["eligibility"] == "conflict"
    assert route_for_score(score) == {"route": "hold", "auto_skip": False}


def test_required_preferred_do_not_override_proposed_business_weights(
    tmp_path, application, output
):
    output["groups"][0]["weight"] = 1
    output["groups"][1]["weight"] = 9
    rows = judged_rows(
        brief(tmp_path, application, output),
        {
            "Research pricing models": "supported",
            "Validate risk": "supported",
            "Python": "gap",
            "C++": "gap",
        },
    )
    assert calculate_framework_score(rows)["lower"] == 10


@pytest.mark.parametrize(
    "mutation", ["missing", "duplicate", "text", "group", "weight", "reference", "revision"]
)
def test_partial_or_mutated_framework_rows_are_rejected(tmp_path, application, output, mutation):
    rows = judged_rows(brief(tmp_path, application, output), {})
    if mutation == "missing":
        rows.pop()
    elif mutation == "duplicate":
        rows.append(deepcopy(rows[0]))
    elif mutation == "text":
        rows[0]["text"] = "different"
    elif mutation == "group":
        rows[0]["scoring_framework"]["group"]["weight"] += 1
    elif mutation == "weight":
        rows[0]["scoring_framework"]["weight_denominator"] += 1
    elif mutation == "reference":
        rows[0]["scoring_framework"]["requirement_id"] = "missing"
    else:
        rows[0]["scoring_framework"]["revision"] = "different"
    with pytest.raises(PortalDataError):
        calculate_framework_score(rows)


def test_brief_hash_and_canonical_ids_are_both_checked(tmp_path, application, output):
    value = brief(tmp_path, application, output)
    value["groups"][0]["requirements"][0]["id"] = "tampered"
    value["revision"] = digest({key: item for key, item in value.items() if key != "revision"})
    with pytest.raises(PortalDataError):
        validate_job_brief(value)


def test_normalization_preserves_decimals_symbols_and_word_boundaries(
    tmp_path, application, output
):
    application["job_description"] += " 1.5 years. 15 years. C. Data science. Datascience."
    output["groups"][0]["requirements"] += [
        {"text": text, "jd_quote": text}
        for text in ["1.5 years", "15 years", "Data science", "Datascience", "C"]
    ]
    value = brief(tmp_path, application, output)
    rows = brief_requirements(value)
    assert len(rows) == 9
    assert len({row["scoring_framework"]["requirement_id"] for row in rows}) == 9
    assert [group["label"] for group in value["groups"]] == ["Business", "Methods"]
    assert [row["text"] for row in rows[:2]] == ["Research pricing models", "Validate risk"]


@pytest.mark.parametrize(
    "field", ["business_object", "business_objective", "methods_role", "label", "weight_reason"]
)
def test_required_interpretation_fields_cannot_be_whitespace(tmp_path, application, output, field):
    if field == "business_object":
        output[field] = " "
    elif field in {"business_objective", "methods_role"}:
        output["role_understanding"][field] = " "
    else:
        output["groups"][0][field] = " "
    with pytest.raises(PortalDataError):
        brief(tmp_path, application, output)


def test_cache_symlink_and_oversized_cache_are_rejected(tmp_path, application, output):
    brief(tmp_path, application, output)
    cache = tmp_path / "brief/job-brief.json"
    target = tmp_path / "outside.json"
    cache.rename(target)
    cache.symlink_to(target)
    with pytest.raises(PortalDataError):
        create_job_brief(application, cache.parent, runner=runner_for(output))
    cache.unlink()
    cache.write_bytes(b" " * (2 * 1024 * 1024 + 1))
    with pytest.raises(PortalDataError):
        create_job_brief(application, cache.parent, runner=runner_for(output))


def test_private_cache_parent_symlink_is_rejected(tmp_path, application, output):
    (tmp_path / "actual").mkdir()
    (tmp_path / "link").symlink_to(tmp_path / "actual", target_is_directory=True)
    with pytest.raises(PortalDataError) as error:
        create_job_brief(application, tmp_path / "link/child/brief", runner=runner_for(output))
    assert error.value.code == "job_brief_directory_invalid"
    assert list((tmp_path / "actual").iterdir()) == []


def test_oversized_jd_and_unconsumable_requirement_fail_without_publication(
    tmp_path, application, output
):
    with pytest.raises(PortalDataError):
        create_job_brief(
            application | {"job_description": "字" * 16001},
            tmp_path / "too-large",
            runner=runner_for(output),
        )
    assert not (tmp_path / "too-large").exists()
    output["groups"][0]["requirements"][0]["text"] = "a" * 2001
    with pytest.raises(PortalDataError):
        brief(tmp_path, application, output)
    assert not (tmp_path / "brief/job-brief.json").exists()


def test_role_text_has_same_canonical_whitespace_as_downstream_echo(tmp_path, application, output):
    output["role_understanding"] = {
        "business_objective": "  Pricing decisions \n",
        "work_outputs": ["  Validated models  "],
        "methods_role": "  Implementation tools \t",
    }
    value = brief(tmp_path, application, output)
    assert value["role_understanding"] == {
        "business_objective": "Pricing decisions",
        "work_outputs": ["Validated models"],
        "methods_role": "Implementation tools",
    }
    assert validate_job_brief(value) == value


def nested_output(application, output, texts=None, alternatives=None):
    texts = texts or ["PhD", "2 years", "5 years"]
    application["job_description"] = " and ".join(texts) + "."
    group = output["groups"][0]
    group.update(
        jd_quote=application["job_description"],
        operator="any",
        weight=100,
        hard_condition=True,
        alternatives=alternatives or [[0, 1], [2]],
        requirements=[{"text": text, "jd_quote": text} for text in texts],
    )
    output["groups"] = [group]
    return output


@pytest.mark.parametrize(
    "judgments,expected",
    [
        (["supported", "gap", "supported"], (100, 100, "supported")),
        (["supported", "supported", "gap"], (100, 100, "supported")),
        (["gap", "supported", "gap"], (50, 50, "conflict")),
        (["supported", "unknown", "gap"], (50, 100, "needs_input")),
        (["gap", "gap", "partial"], (50, 50, "needs_input")),
    ],
)
def test_nested_phd_and_two_years_or_five_years(tmp_path, application, output, judgments, expected):
    nested_output(application, output)
    value = brief(tmp_path, application, output)
    rows = judged_rows(value, dict(zip(["PhD", "2 years", "5 years"], judgments, strict=True)))
    score = calculate_framework_score(rows)
    assert (score["lower"], score["upper"], score["eligibility"]) == expected
    assert (
        sum(
            row["scoring_framework"]["weight_numerator"]
            / row["scoring_framework"]["weight_denominator"]
            for row in rows
        )
        == 100
    )


@pytest.mark.parametrize(
    "judgments,expected",
    [
        (["supported", "gap", "supported"], (100, "supported")),
        (["supported", "gap", "gap"], (50, "conflict")),
        (["gap", "supported", "supported"], (100, "supported")),
    ],
)
def test_python_or_r_and_sql_preserves_original_parentheses(
    tmp_path, application, output, judgments, expected
):
    texts = ["Python", "R", "SQL"]
    nested_output(application, output, texts, [[0, 2], [1, 2]])
    score = calculate_framework_score(
        judged_rows(brief(tmp_path, application, output), dict(zip(texts, judgments, strict=True)))
    )
    assert (score["lower"], score["eligibility"]) == expected


def test_nested_duplicate_atoms_remap_and_equal_clauses_collapse(tmp_path, application, output):
    nested_output(application, output)
    output["groups"][0]["requirements"].append({"text": "ＰＨＤ.", "jd_quote": "PhD"})
    output["groups"][0]["alternatives"] = [[0, 1], [3, 1, 0], [2]]
    value = brief(tmp_path, application, output)
    assert value["groups"][0]["alternatives"] == [[0, 1], [2]]
    assert len(brief_requirements(value)) == 3
    score = calculate_framework_score(
        judged_rows(value, {"PhD": "supported", "2 years": "supported", "5 years": "gap"})
    )
    assert score["lower"] == 100


@pytest.mark.parametrize(
    "alternatives",
    [
        [],
        [[]],
        [[0, 3], [2]],
        [[-1, 1], [2]],
        [[True, 1], [2]],
        [[0, 1]],
        [[0], [0, 1], [2]],
    ],
)
def test_invalid_nested_references_and_absorbed_branches_reject(
    tmp_path, application, output, alternatives
):
    nested_output(application, output)
    output["groups"][0]["alternatives"] = alternatives
    with pytest.raises(PortalDataError):
        brief(tmp_path, application, output)


def test_nested_relation_changes_group_identity_and_mutation_is_rejected(
    tmp_path, application, output
):
    nested_output(application, output)
    first = create_job_brief(application, tmp_path / "one", runner=runner_for(output))
    output["groups"][0]["alternatives"] = [[0], [1, 2]]
    second = create_job_brief(application, tmp_path / "two", runner=runner_for(output))
    assert first["groups"][0]["id"] != second["groups"][0]["id"]
    rows = judged_rows(first, {})
    rows[0]["scoring_framework"]["group"]["alternatives"] = [[0], [1, 2]]
    with pytest.raises(PortalDataError):
        calculate_framework_score(rows)


def test_nested_alternatives_cannot_claim_all_operator(tmp_path, application, output):
    nested_output(application, output)
    output["groups"][0]["operator"] = "all"
    with pytest.raises(PortalDataError):
        brief(tmp_path, application, output)
