"""Explicit English facts reuse without changing materials or saved analysis."""

from copy import deepcopy

import pytest
from test_application_information import answer, library_with
from test_confirmed_qualification_reuse import example_case, explain

from career_evidence_graph.application_information import (
    condition_from_library,
    condition_information_binding,
    material_information_library,
)

ENGLISH = "Be fluent in English."


def resolve(*records, text=ENGLISH):
    application, _ = example_case(ENGLISH)
    return condition_from_library(
        {"text": text, "hard_condition": True}, application, library_with(*records)
    )


@pytest.mark.parametrize(
    "question", ["Are you fluent in English?", "Do you speak English fluently?", "English fluency"]
)
@pytest.mark.parametrize("value", ["Yes", "true", "Fluent", True])
def test_explicit_confirmed_english_fluency_reuses_aliases(question, value):
    result = resolve(answer(question, value))
    assert result["status"] == "supported"
    assert result["fact"] == "language_english_fluent"
    assert result["references"][0]["key"]
    assert len(result["references"][0]["revision"]) == 64


@pytest.mark.parametrize(
    "text", [" BE  FLUENT in English! ", "Be fluent in English", "be fluent in english."]
)
def test_only_case_spacing_and_terminal_punctuation_are_normalized(text):
    assert resolve(answer("English fluency", "yes"), text=text)["status"] == "supported"


@pytest.mark.parametrize(
    "text",
    ["English preferred.", "Be fluent in English and German.", "Be fluent in English or French."],
)
def test_broader_language_prose_is_not_inferred(text):
    assert resolve(answer("English fluency", "yes"), text=text) is None


@pytest.mark.parametrize(
    "scope",
    [
        {},
        {"country": "CHE"},
        {"company": "Example Quant Firm"},
        {"application_id": "synthetic-example-job"},
    ],
)
def test_english_scope_applies(scope):
    assert resolve(answer("English fluency", "yes", scope=scope))["status"] == "supported"


@pytest.mark.parametrize(
    "scope", [{"country": "GBR"}, {"company": "Other"}, {"application_id": "other"}]
)
def test_english_other_scope_does_not_apply(scope):
    assert resolve(answer("English fluency", "yes", scope=scope))["status"] == "needs_input"


@pytest.mark.parametrize("value", ["No", "false", "not fluent", False])
def test_explicit_negative_fluency_conflicts(value):
    assert resolve(answer("English fluency", value))["status"] == "conflict"


@pytest.mark.parametrize("state", ["inferred", "missing", "sensitive"])
def test_unconfirmed_or_withdrawn_alias_blocks_global_confirmed_value(state):
    assert (
        resolve(
            answer("English fluency", "yes"),
            answer(
                "Are you fluent in English?",
                "yes",
                scope={"application_id": "synthetic-example-job"},
                state=state,
            ),
        )["status"]
        == "needs_input"
    )


@pytest.mark.parametrize("value", ["good", "B2", "C1", "IELTS 8", "", None])
def test_vague_values_are_not_fluency(value):
    assert resolve(answer("English fluency", value))["status"] == "needs_input"


def test_conflicts_across_question_aliases_are_not_ignored():
    assert (
        resolve(answer("English fluency", "yes"), answer("Are you fluent in English?", "no"))[
            "status"
        ]
        == "needs_input"
    )


def test_narrowest_scoped_fluency_wins_without_losing_conflict_semantics():
    assert (
        resolve(
            answer("English fluency", "no"),
            answer(
                "Are you fluent in English?",
                "yes",
                scope={"application_id": "synthetic-example-job"},
            ),
        )["status"]
        == "supported"
    )


def test_no_explicit_evidence_stays_unknown():
    assert resolve()["status"] == "needs_input"


def test_english_updates_qualification_binding_but_preserves_contact_material_revision():
    application, _ = example_case(ENGLISH)
    before = library_with(answer("English fluency", "yes"))
    after = library_with(answer("English fluency", "yes", state="missing"))
    assert (
        material_information_library(application, before)["revision"]
        == material_information_library(application, after)["revision"]
    )
    assert (
        material_information_library(application, before)["qualification_revision"]
        != material_information_library(application, after)["qualification_revision"]
    )
    assert condition_information_binding(
        ENGLISH, application, before
    ) != condition_information_binding(ENGLISH, application, after)


def test_existing_analysis_materials_and_history_stay_unchanged_with_current_score():
    application, task = example_case(ENGLISH)
    library = library_with(answer("English fluency", "yes"))
    before = deepcopy((application, task, library))
    result = explain(application, task, library)
    assert result["qualification"]["status"] == "supported"
    assert result["score"]["lower"] == 100
    assert result["documentary_score"]["lower"] == 0
    assert result["fresh"] and result["materials_fresh"]
    assert (application, task, library) == before


def test_saved_hard_gap_cannot_be_bypassed_by_fluency_fact():
    application, task = example_case(ENGLISH)
    for artifact in task["artifacts"]:
        if artifact["stage"] == "analysis":
            artifact["result"]["requirements"][0]["judgment"] = "gap"
    result = explain(application, task, library_with(answer("English fluency", "yes")))
    assert result["qualification"]["status"] == "conflict"


@pytest.mark.parametrize(
    "value",
    [
        "professional",
        "professional working proficiency",
        "熟练，professional 的水平",
        "熟练，professional的水平",
    ],
)
def test_explicit_professional_level_reuses_exact_saved_value_without_cefr_inference(
    tmp_path, value
):
    from test_application_information import write_library

    from career_evidence_graph.application_information import read_information_library

    key, record = answer("English fluency", value)
    root = tmp_path / "library"
    write_library(root, answers={key: record})
    library = read_information_library(root)
    assert library["records"][0]["value"] == value
    application, task = example_case(ENGLISH)
    result = explain(application, task, library)
    assert result["qualification"]["status"] == "supported"
    assert result["score"]["lower"] == 100
    assert result["qualification"]["conditions"][0]["library"]["fact"] == "language_english_fluent"


def test_professional_confirmation_does_not_hide_conflicting_existing_answer():
    assert (
        resolve(
            answer("English fluency", "熟练，professional 的水平"),
            answer("Are you fluent in English?", "no"),
        )["status"]
        == "needs_input"
    )


def test_withdrawn_fact_invalidates_manual_resolution_bound_to_prior_english_answer():
    from career_evidence_graph.application_worker import digest

    application, task = example_case(ENGLISH)
    original = library_with(answer("English fluency", "yes"))
    task["hard_condition_resolutions"] = [
        {
            "analysis_id": task["analysis_id"],
            "requirement_index": 0,
            "confirmed": True,
            "eligible": True,
            "verified_by": "user",
            "source": "Explicit language answer",
            "input_revision": digest(task["inputs"]),
            "qualification_basis": condition_information_binding(ENGLISH, application, original),
        }
    ]
    withdrawn = library_with(answer("English fluency", None, state="missing"))
    before = deepcopy(task)
    result = explain(application, task, withdrawn)
    assert result["qualification"]["status"] == "needs_input"
    assert result["qualification"]["conditions"][0]["resolution"] is None
    assert task == before
