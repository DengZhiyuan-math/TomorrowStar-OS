"""Deterministic provenance checks do not replace semantic model evaluation."""

from copy import deepcopy

import pytest
from pydantic import ValidationError

from career_evidence_graph.application_inference import Inference, validate_inference
from career_evidence_graph.career_portal_data import PortalDataError


def source(quote="Worked with physicists to explain the analysis.", **updates):
    return {
        "source_id": "experience-1",
        "source_revision": "revision-1",
        "quote_start": 5,
        "quote_end": 5 + len(quote),
        "quote": quote,
        "attribution": "User",
        "match_eligible": True,
        "rewrite_allowed": True,
        **updates,
    }


def case(
    judgment="supported",
    inference_type="semantic",
    quote=None,
    jd_quote="Communicate across disciplines",
):
    evidence = source() if quote is None else source(quote)
    inference = {
        "requirement_id": "requirement-1",
        "type": inference_type,
        "relation": {
            "supported": "supports",
            "partial": "partial_support",
            "gap": "contradicts",
            "unknown": "unresolved",
        }[judgment],
        "basis": "The recorded work involves explaining analysis to another discipline.",
        "expression_scope": "Explained analysis to collaborators from physics.",
        "calculation": None,
    }
    row = {
        "judgment": judgment,
        "claim_scope": "documentary",
        "sources": [evidence],
        "source_ids": [evidence["source_id"]],
        "citations": [{"source_id": evidence["source_id"], "quote": evidence["quote"]}],
        "inference": inference,
    }
    atom = {"id": "requirement-1", "text": "Communicate across disciplines", "jd_quote": jd_quote}
    template = {"text": atom["text"], "scoring_framework": {"requirement_id": atom["id"]}}
    return row, template, {"groups": [{"requirements": [atom]}]}


def invalid(values):
    with pytest.raises(PortalDataError) as caught:
        validate_inference(*values)
    assert caught.value.code == "match_inference_invalid"


@pytest.mark.parametrize("kind", ["direct", "semantic"])
def test_valid_reasoning_binds_fact_without_reweighting_or_mutating(kind):
    values = case(inference_type=kind)
    before = deepcopy(values)
    result = validate_inference(*values)
    assert values == before
    assert result["type"] == kind
    assert result["relation"] == "supports"
    assert result["calculation"] is None
    assert result["facts"][0] == {
        "id": result["facts"][0]["id"],
        "source_id": "experience-1",
        "source_revision": "revision-1",
        "quote_start": 5,
        "quote_end": 5 + len(values[0]["sources"][0]["quote"]),
        "quote": values[0]["sources"][0]["quote"],
    }
    assert "weight" not in result
    assert result["facts"][0]["id"] == validate_inference(*values)["facts"][0]["id"]


def test_fact_revision_and_quote_location_change_fact_id():
    values = case()
    original = validate_inference(*values)["facts"][0]["id"]
    values[0]["sources"][0]["source_revision"] = "revision-2"
    assert validate_inference(*values)["facts"][0]["id"] != original
    values[0]["sources"][0]["source_revision"] = "revision-1"
    values[0]["sources"][0]["quote_start"] += 1
    values[0]["sources"][0]["quote_end"] += 1
    assert validate_inference(*values)["facts"][0]["id"] != original


def test_partial_and_unknown_remain_distinct():
    partial = validate_inference(*case(judgment="partial"))
    assert partial["relation"] == "partial_support"
    values = case(judgment="unknown")
    values[0]["sources"] = []
    values[0]["inference"]["expression_scope"] = ""
    unknown = validate_inference(*values)
    assert unknown["relation"] == "unresolved"
    assert unknown["facts"] == []


@pytest.mark.parametrize("kind", ["direct", "semantic"])
def test_missing_exam_is_not_a_barrier_to_recorded_language_use(kind):
    values = case(
        inference_type=kind, quote="I use English to teach and work; I have no exam certificate."
    )
    values[0]["inference"]["expression_scope"] = "Uses English for teaching and work."
    assert validate_inference(*values)["relation"] == "supports"


@pytest.mark.parametrize(
    "change",
    [
        {"requirement_id": "invented"},
        {"relation": "contradicts"},
        {"basis": " "},
        {"facts": []},
        {"weight": 2},
        {"type": "other"},
    ],
)
def test_invalid_model_inference_is_an_explicit_error(change):
    values = case()
    values[0]["inference"].update(change)
    invalid(values)


@pytest.mark.parametrize(
    "change",
    [
        {"source_revision": None},
        {"quote_start": True},
        {"quote_end": 999},
        {"quote": ""},
        {"source_id": ""},
    ],
)
def test_invalid_program_fact_shape_is_not_unknown(change):
    values = case()
    values[0]["sources"][0].update(change)
    invalid(values)


def test_model_cannot_supply_calculated_result():
    values = elapsed()
    values[0]["inference"]["calculation"]["result"] = {"satisfied": True}
    invalid(values)
    with pytest.raises(ValidationError):
        Inference.model_validate({**case()[0]["inference"], "facts": []})


def test_calculation_union_retains_strict_kinds_without_discriminator_metadata():
    schema = Inference.model_json_schema()["properties"]["calculation"]
    assert "discriminator" not in schema
    assert len(schema["anyOf"]) == 3
    values = elapsed()
    values[0]["inference"]["calculation"]["kind"] = "arbitrary_calculation"
    invalid(values)


def test_missing_or_changed_requirement_binding_is_rejected():
    values = case()
    values[1]["text"] = "Changed requirement"
    invalid(values)
    values = case()
    values[2]["groups"][0]["requirements"] *= 2
    invalid(values)


@pytest.mark.parametrize("judgment", ["supported", "partial", "gap"])
def test_nonunknown_conclusion_requires_fact(judgment):
    values = case(judgment=judgment)
    values[0]["sources"] = []
    invalid(values)


def test_unknown_cannot_have_employer_assertion():
    invalid(case(judgment="unknown"))


@pytest.mark.parametrize(
    "expression",
    [
        "Delivered 42% improvement.",
        "Has 3 years of experience.",
        "Speaks English at C1.",
        "Speaks English at CEFR B2.",
        "Completed on 2024-03-02.",
    ],
)
def test_precise_numbers_and_levels_require_cited_fact(expression):
    values = case(quote="Used English at work from 2024-03-01; no examination.")
    values[0]["inference"]["expression_scope"] = expression
    invalid(values)


@pytest.mark.parametrize(
    "quote,expression",
    [
        ("I self-report English at C1.", "English CEFR C1 (self-reported)."),
        ("Reduced runtime by 42%.", "Reduced runtime by 42%."),
        ("Completed on 2024-03-01.", "Completed on 2024-03-01."),
        ("Used Python 3 and C++17.", "Python 3 and C++17."),
    ],
)
def test_explicit_numbers_and_self_reported_level_are_reusable(quote, expression):
    values = case(inference_type="direct", quote=quote)
    values[0]["inference"]["expression_scope"] = expression
    assert validate_inference(*values)["relation"] == "supports"


@pytest.mark.parametrize(
    "flags",
    [
        {"planned_only": True},
        {"attribution": "Team"},
        {"attribution": "Other"},
        {"design_only": True},
        {"documentary_only": True},
        {"match_eligible": False},
        {"rewrite_allowed": False},
    ],
)
def test_responsibility_flags_cannot_upgrade_to_personal_completion(flags):
    values = case()
    values[0]["sources"][0].update(flags)
    values[0]["claim_scope"] = "personal_completed"
    invalid(values)


def test_documentary_team_record_keeps_its_scope():
    values = case(quote="Our team explained results to partner researchers.")
    values[0]["sources"][0]["attribution"] = "Team"
    values[0]["inference"]["expression_scope"] = "Team collaboration with partner researchers."
    assert validate_inference(*values)["relation"] == "supports"


def elapsed(start="2022-01-15", end="2024-01-15", threshold="2 years", judgment="supported"):
    values = case(
        judgment=judgment,
        inference_type="deterministic",
        quote=f"Worked from {start} to {end}.",
        jd_quote=f"Requires at least {threshold} experience.",
    )
    values[0]["inference"].update(
        calculation={
            "kind": "elapsed_months_at_least",
            "start_date": start,
            "end_date": end,
            "threshold_quote": threshold,
        },
        expression_scope="Meets the recorded duration." if judgment == "supported" else "",
    )
    return values


@pytest.mark.parametrize(
    "start,end,threshold,months,judgment",
    [
        ("2022-01-15", "2024-01-15", "2 years", 24, "supported"),
        ("2022-01-15", "2024-01-14", "24 months", 23, "gap"),
        ("2024-01-31", "2024-02-29", "1 month", 0, "gap"),
        ("2024-02-29", "2025-02-28", "1 year", 11, "gap"),
        ("2024-02-29", "2025-03-01", "1年", 12, "supported"),
        ("2024-01-01", "2024-03-01", "2个月", 2, "supported"),
    ],
)
def test_complete_month_calculation_uses_explicit_boundary(start, end, threshold, months, judgment):
    result = validate_inference(*elapsed(start, end, threshold, judgment))
    assert result["calculation"]["result"] == {
        "elapsed_months": months,
        "threshold_months": int(threshold.split()[0])
        if threshold == "24 months"
        else {"2 years": 24, "1 month": 1, "1 year": 12, "1年": 12, "2个月": 2}[threshold],
        "satisfied": judgment == "supported",
    }


def test_program_calculated_duration_is_available_for_expression():
    values = elapsed()
    values[0]["inference"]["expression_scope"] = "Completed 24 months; meets 2 years."
    assert validate_inference(*values)["calculation"]["result"]["elapsed_months"] == 24


@pytest.mark.parametrize(
    "change",
    [
        {"start_date": "2022-01"},
        {"end_date": "today"},
        {"start_date": "2022-02-30"},
        {"end_date": "2021-01-15"},
        {"threshold_quote": "1 year"},
    ],
)
def test_invalid_or_unquoted_date_and_threshold_are_rejected(change):
    values = elapsed()
    values[0]["inference"]["calculation"].update(change)
    invalid(values)


def test_threshold_cannot_be_a_substring_of_larger_number():
    values = elapsed(threshold="12 years", judgment="gap")
    values[0]["inference"]["calculation"]["threshold_quote"] = "2 years"
    invalid(values)


@pytest.mark.parametrize(
    "duration,threshold",
    [
        ("2.2 years", "2 years"),
        ("2,2 years", "2 years"),
        ("2 . 2 years", "2 years"),
        ("-2 years", "2 years"),
        ("- 2 years", "2 years"),
        ("−2 years", "2 years"),
        ("+2 years", "2 years"),
        ("1-2 years", "2 years"),
        ("1 - 2 years", "2 years"),
        ("1–2 years", "2 years"),
        ("1 to 2 years", "2 years"),
        ("1至2年", "2年"),
        ("1 years to 2 years", "1 years"),
        ("1 years to 2 years", "2 years"),
        ("2.24 months", "24 months"),
    ],
)
def test_noninteger_or_range_duration_cannot_be_truncated_to_integer(duration, threshold):
    values = elapsed()
    values[2]["groups"][0]["requirements"][0]["jd_quote"] = (
        f"Requires at least {duration} experience."
    )
    values[0]["inference"]["calculation"]["threshold_quote"] = threshold
    invalid(values)


@pytest.mark.parametrize(
    "jd_quote,threshold",
    [
        ("Requires 2 years of experience.", "2 years"),
        ("Required. 24 months of experience.", "24 months"),
        ("至少2年经历。", "2年"),
    ],
)
def test_explicit_integer_duration_remains_supported(jd_quote, threshold):
    values = elapsed()
    values[2]["groups"][0]["requirements"][0]["jd_quote"] = jd_quote
    values[0]["inference"]["calculation"]["threshold_quote"] = threshold
    assert validate_inference(*values)["calculation"]["result"]["satisfied"] is True


@pytest.mark.parametrize(
    "duration",
    [
        "2 years and 6 months",
        "2 years 6 months",
        "2 years or 6 months",
        "2年6个月",
        "2 years (24 months)",
        "2 years and -6 months",
        "2 years or 2.5 months",
    ],
)
def test_multiple_durations_cannot_be_truncated_to_one_threshold(duration):
    values = elapsed()
    values[2]["groups"][0]["requirements"][0]["jd_quote"] = (
        f"Requires at least {duration} experience."
    )
    values[0]["inference"]["calculation"]["threshold_quote"] = (
        "2年" if duration == "2年6个月" else "2 years"
    )
    invalid(values)


def test_single_explicit_thirty_months_can_be_computed():
    values = elapsed(end="2024-07-15", threshold="30 months")
    assert validate_inference(*values)["calculation"]["result"] == {
        "elapsed_months": 30,
        "threshold_months": 30,
        "satisfied": True,
    }


def test_inconsistent_computed_judgment_is_error_not_unknown():
    invalid(elapsed(judgment="gap"))


@pytest.mark.parametrize(
    "kind,calculation",
    [
        (
            "direct",
            {
                "kind": "elapsed_months_at_least",
                "start_date": "2022-01-15",
                "end_date": "2024-01-15",
                "threshold_quote": "2 years",
            },
        ),
        ("deterministic", None),
    ],
)
def test_only_deterministic_reasoning_uses_calculation(kind, calculation):
    values = case(inference_type=kind)
    values[0]["inference"]["calculation"] = calculation
    invalid(values)


@pytest.mark.parametrize("subject,judgment", [("2026-06-30", "supported"), ("2026-07-01", "gap")])
def test_date_comparison_includes_cutoff(subject, judgment):
    values = case(
        judgment=judgment,
        inference_type="deterministic",
        quote=f"The certificate was awarded on {subject}.",
        jd_quote="Certificate awarded by 2026-06-30.",
    )
    values[0]["inference"].update(
        calculation={
            "kind": "date_on_or_before",
            "subject_date": subject,
            "cutoff_date": "2026-06-30",
        },
        expression_scope="",
    )
    assert validate_inference(*values)["calculation"]["result"]["satisfied"] == (
        judgment == "supported"
    )
    values[0]["inference"]["calculation"]["cutoff_date"] = "2027-06-30"
    invalid(values)


@pytest.mark.parametrize(
    "expression",
    ["Graduated on 2026-06-30.", "Degree was awarded on 2026-06-30.", "已毕业，日期 2026-06-30。"],
)
def test_expected_date_can_meet_date_requirement_without_awarding_degree(expression):
    values = case(
        inference_type="deterministic",
        quote="Expected graduation: 2026-06-30.",
        jd_quote="Expected graduation on or before 2026-06-30.",
    )
    values[0]["inference"].update(
        calculation={
            "kind": "date_on_or_before",
            "subject_date": "2026-06-30",
            "cutoff_date": "2026-06-30",
        },
        expression_scope="Expected graduation: 2026-06-30.",
    )
    assert validate_inference(*values)["calculation"]["result"]["satisfied"] is True
    values[0]["inference"]["expression_scope"] = expression
    invalid(values)
