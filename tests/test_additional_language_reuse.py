"""Bounded additional-language bonus reuses confirmed levels without claiming fluency."""

from copy import deepcopy

import pytest
from test_application_information import answer, library_with
from test_confirmed_qualification_reuse import example_case, explain

from career_evidence_graph._vendor import job_apply_store as helper
from career_evidence_graph.application_information import (
    condition_from_library,
    condition_information_binding,
    material_information_library,
    put_information_answer,
    read_information_library,
)

ADDITIONAL = "Have additional language skills."


def resolve(*records, text=ADDITIONAL):
    application, _ = example_case(ADDITIONAL)
    return condition_from_library(
        {"text": text, "hard_condition": False}, application, library_with(*records)
    )


def test_real_writer_roundtrip_three_levels_updates_bonus_preserving_existing_materials(tmp_path):
    store = helper.Store(tmp_path / "answers")
    for language, level in (("French", "B2"), ("German", "B1"), ("Japanese", "C1")):
        _, record = answer(f"{language} proficiency CEFR", level)
        put_information_answer(store, record, actor="user", source="explicit-user-confirmation")
    library = read_information_library(store.root)
    application, task = example_case(ADDITIONAL)
    task["artifacts"][0]["result"]["requirements"][0].update(
        hard_condition=False, importance="preferred"
    )
    before = deepcopy((application, task, library))
    result = explain(application, task, library)
    assert result["score"]["lower"] == 100
    assert result["documentary_score"]["lower"] == 0
    assert result["reasons"][0]["library"]["fact"] == "additional_language_skills"
    assert all(
        level in result["reasons"][0]["explanation"] for level in ("法语 B2", "德语 B1", "日语 C1")
    )
    assert "流利" not in result["reasons"][0]["explanation"]
    assert (application, task, library) == before


@pytest.mark.parametrize(
    "question",
    [
        "Japanese proficiency CEFR",
        "Japanese level",
        "Japanese proficiency",
        "Japanese language level",
    ],
)
def test_japanese_explicit_level_aliases(question):
    result = resolve(answer(question, "A2"))
    assert result["status"] == "supported"
    assert len(result["references"][0]["revision"]) == 64


@pytest.mark.parametrize("value", ["A1", "A2", "B1", "B2", "C1", "C2"])
def test_each_explicit_cefr_level_proves_additional_language(value):
    assert resolve(answer("French level", value))["status"] == "supported"


@pytest.mark.parametrize("state", ["inferred", "missing", "sensitive"])
def test_unconfirmed_language_cannot_prove_but_other_confirmed_language_can(state):
    uncertain = answer("French level", "B2", state=state)
    assert resolve(uncertain)["status"] == "needs_input"
    assert resolve(uncertain, answer("German level", "B1"))["status"] == "supported"


def test_conflicting_aliases_exclude_only_that_language():
    records = (answer("French level", "B2"), answer("French proficiency CEFR", "B1"))
    assert resolve(*records)["status"] == "needs_input"
    result = resolve(*records, answer("Japanese level", "B1"))
    assert result["status"] == "supported"
    assert "法语" not in result["explanation"]


@pytest.mark.parametrize("value", ["none", "fluent", "N2", "good", "A0", ""])
def test_non_cefr_and_absent_evidence_not_inferred(value):
    assert resolve(answer("Japanese level", value))["status"] == "needs_input"


def test_explicit_job_withdrawal_overrides_global_language_but_not_other_language():
    records = (
        answer("French level", "B2"),
        answer(
            "French proficiency CEFR",
            None,
            state="missing",
            scope={"application_id": "synthetic-example-job"},
        ),
    )
    assert resolve(*records)["status"] == "needs_input"
    assert resolve(*records, answer("German level", "B1"))["status"] == "supported"


def test_irrelevant_scope_is_ignored():
    assert (
        resolve(answer("Japanese level", "B1", scope={"company": "Other"}))["status"]
        == "needs_input"
    )


@pytest.mark.parametrize(
    "text",
    [
        "Have additional language skills and trading experience.",
        "Have fluent French.",
        "Language skills preferred.",
    ],
)
def test_other_requirement_prose_not_inferred(text):
    assert resolve(answer("French level", "B2"), text=text) is None


def test_bounded_punctuation_case_and_space_normalization():
    assert (
        resolve(answer("French level", "B2"), text=" HAVE additional  LANGUAGE skills! ")["status"]
        == "supported"
    )


def test_aggregate_condition_binding_tracks_underlying_facts_without_material_input_change():
    application, _ = example_case(ADDITIONAL)
    before = library_with(answer("Japanese level", "B1"))
    after = library_with(answer("Japanese level", None, state="missing"))
    assert condition_information_binding(
        ADDITIONAL, application, before
    ) != condition_information_binding(ADDITIONAL, application, after)
    assert (
        material_information_library(application, before)["qualification_revision"]
        != material_information_library(application, after)["qualification_revision"]
    )
    assert (
        material_information_library(application, before)["revision"]
        == material_information_library(application, after)["revision"]
    )
