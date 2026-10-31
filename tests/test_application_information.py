"""Synthetic, read-only access to the existing answer library."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from career_evidence_graph._vendor import job_apply_store as helper
from career_evidence_graph.application_information import (
    condition_from_library,
    read_information_library,
)


def write_library(root: Path, *, answers=None, profile=None):
    root.mkdir()
    (root / "answers.json").write_text(
        json.dumps({"schemaVersion": 1, "answers": answers or {}, "metadata": {}}),
        encoding="utf-8",
    )
    if profile is not None:
        (root / "profile.json").write_text(
            json.dumps({"schemaVersion": 1, "profile": profile, "metadata": {}}),
            encoding="utf-8",
        )


def tree_bytes(root: Path):
    return {
        str(path.relative_to(root)): path.read_bytes() if path.is_file() else None
        for path in root.rglob("*")
    }


def answer(question, value, *, scope=None, state="confirmed"):
    key = helper.answer_key(question, scope)
    return key, {
        "key": key,
        "question": question,
        "value": value,
        "scope": scope or {},
        "state": state,
    }


def test_reader_is_unconfigured_without_an_explicit_root(tmp_path):
    before = tree_bytes(tmp_path)
    result = read_information_library(None)
    assert result["status"] == "unconfigured"
    assert result["records"] == []
    assert result["preferences"] == {}
    assert tree_bytes(tmp_path) == before


def test_reader_validates_existing_library_without_creating_or_changing_paths(tmp_path):
    root = tmp_path / "library"
    write_library(root, profile={"preferences": {"location": "remote"}})
    before = tree_bytes(tmp_path)
    result = read_information_library(root)
    assert result["status"] == "available"
    assert result["records"] == []
    assert result["preferences"] == {"location": "remote"}
    assert len(result["revision"]) == 64
    assert tree_bytes(tmp_path) == before


def test_reader_does_not_initialize_missing_library(tmp_path):
    root = tmp_path / "missing"
    result = read_information_library(root)
    assert result["status"] == "unavailable"
    assert not root.exists()


def test_reader_accepts_missing_profile_but_not_invalid_present_profile(tmp_path):
    root = tmp_path / "library"
    write_library(root)
    assert read_information_library(root)["status"] == "available"
    (root / "profile.json").write_text("[]", encoding="utf-8")
    before = tree_bytes(tmp_path)
    result = read_information_library(root)
    assert result["status"] == "unavailable"
    assert result["records"] == []
    assert result["preferences"] == {}
    assert tree_bytes(tmp_path) == before


@pytest.mark.parametrize("link_kind", ["answers", "profile", "root", "ancestor"])
def test_reader_refuses_symlink_components(tmp_path, link_kind):
    root = tmp_path / "library"
    write_library(root, profile={})
    if link_kind in {"answers", "profile"}:
        path = root / f"{link_kind}.json"
        target = tmp_path / f"real-{link_kind}.json"
        path.rename(target)
        path.symlink_to(target)
    else:
        linked = tmp_path / "linked"
        linked.symlink_to(root if link_kind == "root" else tmp_path, target_is_directory=True)
        root = linked if link_kind == "root" else linked / "library"
    assert read_information_library(root)["status"] == "unavailable"


@pytest.mark.parametrize(
    "document",
    [
        "{invalid",
        "[]",
        json.dumps({"schemaVersion": 2, "answers": {}, "metadata": {}}),
        json.dumps({"schemaVersion": 1, "answers": {"x": {}}, "metadata": {}}),
        " " * (2 * 1024 * 1024 + 1),
    ],
)
def test_reader_invalid_or_oversized_answers_fail_without_content(tmp_path, document):
    root = tmp_path / "library"
    write_library(root)
    (root / "answers.json").write_text(document, encoding="utf-8")
    before = tree_bytes(tmp_path)
    result = read_information_library(root)
    assert result["status"] == "unavailable"
    assert set(result) == {"status", "revision", "records", "preferences"}
    assert str(root) not in json.dumps(result)
    assert tree_bytes(tmp_path) == before


def test_reader_keeps_validated_records_and_versions_relevant_contents(tmp_path):
    root = tmp_path / "library"
    key, record = answer("French proficiency CEFR", "B2")
    write_library(root, answers={key: record}, profile={"name": "Example Person"})
    first = read_information_library(root)
    assert first["records"] == [record]
    profile = json.loads((root / "profile.json").read_text())
    profile["profile"]["name"] = "Different Name"
    (root / "profile.json").write_text(json.dumps(profile))
    assert read_information_library(root)["revision"] == first["revision"]
    profile["profile"]["preferences"] = {"salary_minimum": 100}
    (root / "profile.json").write_text(json.dumps(profile))
    second = read_information_library(root)
    assert second["revision"] != first["revision"]
    document = json.loads((root / "answers.json").read_text())
    document["answers"][key]["value"] = "C1"
    (root / "answers.json").write_text(json.dumps(document))
    assert read_information_library(root)["revision"] != second["revision"]


def test_reader_read_error_is_content_free(tmp_path, monkeypatch):
    root = tmp_path / "library"
    write_library(root)

    def fail(*args, **kwargs):
        raise PermissionError("private content must not escape")

    monkeypatch.setattr("career_evidence_graph.application_information.os.open", fail)
    result = read_information_library(root)
    assert result["status"] == "unavailable"
    assert "private" not in json.dumps(result)


def library_with(*records):
    return {"status": "available", "records": [record for _key, record in records]}


APPLICATION = {"id": "example-job", "company": "Example Company", "country": "CHE"}


@pytest.mark.parametrize(
    ("language", "value", "minimum", "expected"),
    [
        ("French", "B2", "B2", "supported"),
        ("German", "C1", "B2", "supported"),
        ("French", "A2", "B2", "conflict"),
    ],
)
def test_exact_confirmed_cefr_is_compared_to_explicit_minimum(language, value, minimum, expected):
    record = answer(f"{language} proficiency CEFR", value)
    result = condition_from_library(
        {"text": f"{language} {minimum} required", "hard_condition": True},
        APPLICATION,
        library_with(record),
    )
    assert result["status"] == expected
    assert result["fact"] == f"language_{language.lower()}_cefr"
    assert result["explanation"]
    assert result["references"][0]["key"] == record[0]
    assert len(result["references"][0]["revision"]) == 64
    assert "value" not in result


@pytest.mark.parametrize("state", ["inferred", "sensitive", "missing"])
def test_unconfirmed_language_record_does_not_resolve_qualification(state):
    record = answer("French proficiency CEFR", "C2" if state != "missing" else None, state=state)
    result = condition_from_library("French B2 required", APPLICATION, library_with(record))
    assert result["status"] == "needs_input"
    assert result["references"] == []


@pytest.mark.parametrize(
    "records",
    [
        [answer("French level", "B1"), answer("French proficiency CEFR", "C1")],
        [answer("French level", "fluent")],
        [answer("French level", ["C1"])],
    ],
)
def test_conflicting_or_non_cefr_answers_need_input_instead_of_known_mismatch(records):
    result = condition_from_library("French B2 required", APPLICATION, library_with(*records))
    assert result["status"] == "needs_input"
    assert result["references"]


@pytest.mark.parametrize(
    ("scope", "expected"),
    [
        ({}, "supported"),
        ({"country": "CHE"}, "supported"),
        ({"company": "Example Company"}, "supported"),
        ({"application_id": "example-job"}, "supported"),
        ({"country": "FRA"}, "needs_input"),
        ({"company": "Another Company"}, "needs_input"),
        ({"application_id": "another-job"}, "needs_input"),
        ({"unknown": "anything"}, "needs_input"),
    ],
)
def test_only_applicable_scopes_can_supply_language(scope, expected):
    record = answer("German level", "C1", scope=scope)
    result = condition_from_library("German B2 required", APPLICATION, library_with(record))
    assert result["status"] == expected


def test_library_lookup_does_not_infer_country_from_location():
    record = answer("German level", "C1", scope={"country": "CHE"})
    result = condition_from_library(
        "German B2 required",
        {"id": "example-job", "company": "Example Company", "location": "Zurich, Switzerland"},
        library_with(record),
    )
    assert result["status"] == "needs_input"


@pytest.mark.parametrize("status", ["unconfigured", "unavailable"])
def test_unavailable_library_never_resolves_a_recognized_requirement(status):
    result = condition_from_library("French B2 required", APPLICATION, {"status": status})
    assert result["status"] == "needs_input"
    assert result["references"] == []


@pytest.mark.parametrize(
    "text",
    [
        "French B2 preferred",
        "French B2 not required",
        "French B2 or German B2 required",
        "Python required",
        "Work permit required",
    ],
)
def test_unknown_optional_and_alternative_requirement_semantics_remain_unresolved(text):
    assert condition_from_library(text, APPLICATION, library_with()) is None


def test_a_soft_requirement_cannot_be_promoted_by_information_library():
    assert (
        condition_from_library(
            {"text": "French B2 required", "hard_condition": False},
            APPLICATION,
            library_with(answer("French level", "C1")),
        )
        is None
    )


def test_fluent_without_exact_cefr_threshold_needs_input():
    result = condition_from_library(
        "Fluent French required", APPLICATION, library_with(answer("French level", "B2"))
    )
    assert result["status"] == "needs_input"


@pytest.mark.parametrize(
    "text",
    [
        "German B2 speaking and C1 writing are required",
        "German B2 required, but C1 is the actual minimum",
        "At most German B2 is required",
        "German B2 maximum required",
        "Below German B2 is required",
        "German B2 is not sufficient; stronger language skills required",
        "German B2 and a Swiss work permit are required",
        "German B2 is required together with two years of experience",
        "德语B2要求，但必须低于这个等级",
        "德语B2要求，至多达到该等级",
    ],
)
def test_composite_or_non_minimum_cefr_grammar_stays_unresolved(text):
    result = condition_from_library(
        {"text": text, "hard_condition": True},
        APPLICATION,
        library_with(answer("German level", "B2")),
    )
    assert result["status"] == "needs_input"
    assert result["fact"] == "language_german_cefr"


@pytest.mark.parametrize(
    "text",
    [
        "German B2 required",
        "German CEFR B2 is required.",
        "German at least B2 required",
        "Minimum German B2 required",
        "B2 in German mandatory",
    ],
)
def test_simple_single_cefr_minimum_remains_supported_after_composite_guard(text):
    result = condition_from_library(
        text,
        APPLICATION,
        library_with(answer("German level", "B2")),
    )
    assert result["status"] == "supported"


@pytest.mark.parametrize("field", ["company", "application_id"])
def test_empty_scope_identity_cannot_match_missing_application_identity(field):
    result = condition_from_library(
        "French B2 required",
        {},
        library_with(answer("French level", "C1", scope={field: ""})),
    )
    assert result["status"] == "needs_input"


def test_invalid_deep_json_is_unavailable_without_changes(tmp_path):
    root = tmp_path / "library"
    write_library(root)
    (root / "answers.json").write_text("[" * 2000 + "0" + "]" * 2000, encoding="utf-8")
    before = tree_bytes(tmp_path)
    assert read_information_library(root)["status"] == "unavailable"
    assert tree_bytes(tmp_path) == before


def test_job_exception_overrides_reusable_language_without_changing_other_jobs():
    global_answer = answer("German level", "C1")
    exception = answer("German proficiency CEFR", "A2", scope={"application_id": "example-job"})
    library = library_with(global_answer, exception)
    current = condition_from_library("German B2 required", APPLICATION, library)
    assert current["status"] == "conflict"
    assert [row["key"] for row in current["references"]] == [exception[0]]
    other = condition_from_library(
        "German B2 required", APPLICATION | {"id": "another-job"}, library
    )
    assert other["status"] == "supported"
    assert [row["key"] for row in other["references"]] == [global_answer[0]]


def test_answer_correction_and_withdrawal_preserve_original_records(tmp_path):
    from career_evidence_graph.application_information import (
        put_information_answer,
        read_information_history,
    )
    from career_evidence_graph.application_worker import digest

    store = helper.Store(tmp_path / "library")
    first = put_information_answer(
        store,
        {
            "question": "Email",
            "scope": {},
            "state": "confirmed",
            "value": "old@example.invalid",
        },
        actor="user",
        source="user supplied contact",
    )
    original_bytes = store.answers_path.read_bytes()
    corrected = put_information_answer(
        store,
        {
            **first,
            "value": "correct@example.invalid",
        },
        expected_revision=digest(first),
        source="explicit contact correction",
    )
    withdrawn = put_information_answer(
        store,
        {
            **corrected,
            "value": None,
            "state": "missing",
        },
        expected_revision=digest(corrected),
        source="explicit withdrawal",
    )
    assert store.get_answer(first["key"])["state"] == "missing"
    assert withdrawn["value"] is None
    events = read_information_history(store.root, key=first["key"])
    assert len(events) == 3
    correction = events[1]
    assert correction["before_revision"] == digest(first)
    assert correction["after_revision"] == digest(corrected)
    assert correction["source"] == "explicit contact correction"
    assert (store.root / correction["backup"]).read_bytes() == original_bytes
    assert events[2]["before_revision"] == digest(corrected)
    before = tree_bytes(store.root)
    with pytest.raises(Exception) as error:
        put_information_answer(
            store, {**first, "value": "stale@example.invalid"}, expected_revision=digest(first)
        )
    assert error.value.code == "answer_conflict"
    assert tree_bytes(store.root) == before


def test_answer_atomic_failure_retains_old_library_and_failed_attempt_history(
    tmp_path, monkeypatch
):
    from career_evidence_graph.application_information import (
        put_information_answer,
        read_information_history,
    )
    from career_evidence_graph.application_worker import digest

    store = helper.Store(tmp_path / "library")
    first = put_information_answer(
        store,
        {
            "question": "Email",
            "scope": {},
            "state": "confirmed",
            "value": "old@example.invalid",
        },
    )
    before = store.answers_path.read_bytes()
    real_replace = helper.os.replace

    def fail_answers(source, destination):
        if destination == store.answers_path:
            raise OSError("synthetic atomic answers failure")
        return real_replace(source, destination)

    monkeypatch.setattr(helper.os, "replace", fail_answers)
    with pytest.raises(OSError):
        put_information_answer(
            store, {**first, "value": "new@example.invalid"}, expected_revision=digest(first)
        )
    assert store.answers_path.read_bytes() == before
    history = read_information_history(store.root, key=first["key"])
    assert [event["status"] for event in history] == ["applied", "needs_recheck"]
    assert (store.root / history[-1]["backup"]).read_bytes() == before


def test_material_information_revision_tracks_only_applicable_contact_facts():
    from career_evidence_graph.application_information import material_information_library

    application = {"id": "job-one", "company": "Synthetic", "country": "CHE"}
    records = [
        {
            "key": "email-general",
            "question": "Email",
            "value": "general@example.invalid",
            "state": "confirmed",
            "scope": {},
        },
        {
            "key": "email-job",
            "question": "Email",
            "value": "job@example.invalid",
            "state": "confirmed",
            "scope": {"application_id": "job-one"},
        },
        {
            "key": "sponsorship",
            "question": "Will you now or in the future require sponsorship?",
            "value": "No",
            "state": "confirmed",
            "scope": {"country": "CHE"},
        },
        {
            "key": "french",
            "question": "French proficiency CEFR",
            "value": "B1",
            "state": "confirmed",
            "scope": {},
        },
    ]
    original = {
        "status": "available",
        "revision": "original-global",
        "records": records,
        "preferences": {},
    }
    before = material_information_library(application, original)
    unrelated = json.loads(json.dumps(original))
    unrelated["revision"] = "new-global"
    unrelated["records"][0]["value"] = "new-general@example.invalid"
    unrelated["records"][2]["value"] = "Yes"
    after = material_information_library(application, unrelated)
    assert before["revision"] == after["revision"]
    assert after["library_revision"] == "new-global"
    assert after["records"] == unrelated["records"]
    relevant = json.loads(json.dumps(unrelated))
    relevant["records"][1]["value"] = "correct-job@example.invalid"
    assert material_information_library(application, relevant)["revision"] != before["revision"]
    language = json.loads(json.dumps(unrelated))
    language["records"][3]["value"] = "B2"
    changed = material_information_library(application, language)
    assert changed["revision"] == before["revision"]
    assert changed["qualification_revision"] != before["qualification_revision"]


def test_material_projection_treats_no_configured_answers_as_empty_but_not_unreadable():
    from career_evidence_graph.application_information import material_information_library

    application = {"id": "job-one"}
    empty = material_information_library(application, {"status": "available", "records": []})
    unconfigured = material_information_library(
        application, {"status": "unconfigured", "records": []}
    )
    unreadable = material_information_library(application, {"status": "unavailable", "records": []})
    assert empty["revision"] == unconfigured["revision"]
    assert empty["revision"] != unreadable["revision"]


def test_material_contacts_use_explicit_unique_country_in_application_location():
    from career_evidence_graph.application_information import material_information_library

    key, record = answer("Email", "swiss@example.invalid", scope={"country": "CHE"})
    library = {"status": "available", "revision": "source", "records": [record]}
    swiss = material_information_library({"id": "job", "location": "Zurich, Switzerland"}, library)
    explicit = material_information_library({"id": "job", "country": "CHE"}, library)
    unknown = material_information_library({"id": "job", "location": "Zurich"}, library)
    assert swiss["revision"] == explicit["revision"]
    assert swiss["revision"] != unknown["revision"]


def test_form_labels_for_contact_and_address_map_to_saved_facts():
    from career_evidence_graph.application_information import information_fact

    expected = {
        "E-mail address": "email",
        "Street and house number": "street_address",
        "ZIP Code": "postal_code",
        "Home city": "city",
        "Country of residence": "country_of_residence",
        "Salutation": "salutation",
    }
    assert {label: information_fact(label) for label in expected} == expected
