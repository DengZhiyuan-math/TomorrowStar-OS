"""Normal analysis consumes scoped answers without requirement-specific grammar."""

from copy import deepcopy

import pytest
from test_application_information import answer, library_with

from career_evidence_graph.application_information import (
    information_context,
    information_fact,
    material_information_library,
    validate_information_references,
)
from career_evidence_graph.career_portal_data import PortalDataError

APPLICATION = {"id": "job-a", "company": "Example", "country": "CHE"}


def context(*records, keys=None):
    return information_context(APPLICATION, library_with(*records), fact_keys=keys)


def test_language_facts_are_available_without_a_requirement_sentence_or_hard_guard():
    rows = [
        answer(f"{name} proficiency CEFR", level)
        for name, level in (
            ("English", "C2"),
            ("French", "B2"),
            ("German", "B1"),
            ("Japanese", "B1"),
        )
    ]
    result = context(*rows)
    assert len(result["facts"]) == 4
    assert {f["value"] for f in result["facts"]} == {"C2", "B2", "B1"}
    assert all(f["status"] == "confirmed" for f in result["facts"])
    assert all(f["accepted_as_fact"] is True for f in result["facts"])
    assert all("credential_verified" not in f for f in result["facts"])
    assert all("fluency" not in f for f in result["facts"])


def test_original_self_report_provenance_and_professional_wording_are_retained():
    key, record = answer("English proficiency CEFR", "C2")
    record.update(source="user-self-assessment-no-exam", raw_statement="professional")
    result = context((key, record))
    cited = validate_information_references(result, result["facts"][0]["references"])
    assert cited[0]["source"] == "user-self-assessment-no-exam"
    assert cited[0]["raw_statement"] == "professional"
    assert cited[0]["state"] == "confirmed"
    assert result["facts"][0]["accepted_as_fact"] is True
    assert "credential_verified" not in result["facts"][0]


def test_unfamiliar_user_fact_remains_retrievable_without_alias_implementation():
    result = context(answer("Preferred weekly working days?", "Four"))
    fact = result["facts"][0]
    assert fact["fact"] == information_fact("Preferred weekly working days?")
    assert fact["fact"].startswith("question:")
    assert fact["value"] == "Four"
    assert "question" not in result


def test_narrow_exception_and_withdrawal_never_fall_back_to_global_answer():
    generic = answer("French level", "B2")
    narrow = answer("French proficiency CEFR", "B1", scope={"application_id": "job-a"})
    result = context(generic, narrow)
    assert result["facts"][0]["value"] == "B1"
    assert len(result["facts"][0]["references"]) == 1
    withdrawn = answer(
        "French proficiency CEFR", None, scope={"application_id": "job-a"}, state="missing"
    )
    current = context(generic, withdrawn)
    assert current["facts"][0]["status"] == "missing"
    with pytest.raises(PortalDataError):
        validate_information_references(current, result["facts"][0]["references"])


def test_scope_and_incomparable_conflicts_are_not_resolved_by_order():
    country = answer("French level", "B2", scope={"country": "CHE"})
    employer = answer("French proficiency CEFR", "B1", scope={"company": "Example"})
    excluded = answer("German level", "C2", scope={"country": "DEU"})
    result = context(country, employer, excluded)
    by_fact = {f["fact"]: f for f in result["facts"]}
    assert by_fact["language_french_cefr"]["status"] == "conflict"
    assert by_fact["language_german_cefr"]["status"] == "missing"
    assert context(employer, country, excluded) == result
    with pytest.raises(PortalDataError):
        validate_information_references(result, by_fact["language_french_cefr"]["references"])


@pytest.mark.parametrize("state", ["inferred", "sensitive", "missing"])
def test_unconfirmed_records_cannot_be_used_as_confirmed_evidence(state):
    result = context(answer("French level", None if state == "missing" else "B2", state=state))
    assert result["facts"][0]["status"] != "confirmed"
    with pytest.raises(PortalDataError):
        validate_information_references(result, result["facts"][0]["references"])


def test_citations_bind_exact_current_value_key_and_digest():
    result = context(answer("Japanese level", "B1"))
    ref = {**result["facts"][0]["references"][0], "value": "B1", "fact": "language_japanese_cefr"}
    assert len(validate_information_references(result, [ref, ref])) == 1
    for field, value in (
        ("key", "wrong"),
        ("revision", "wrong"),
        ("value", "fluent"),
        ("fact", "other"),
    ):
        with pytest.raises(PortalDataError):
            validate_information_references(result, [{**ref, field: value}])
    updated = context(answer("Japanese level", "B2"))
    with pytest.raises(PortalDataError):
        validate_information_references(updated, [ref])


def test_context_is_read_only_and_language_changes_do_not_invalidate_material_contacts():
    application = deepcopy(APPLICATION)
    lib = library_with(answer("French level", "B2"), answer("Phone", "+41000"))
    before = deepcopy((application, lib))
    result = information_context(application, lib, fact_keys=["language_french_cefr", "unknown"])
    assert result["facts"][1]["status"] == "missing"
    result["facts"][0]["records"][0]["scope"]["country"] = "DEU"
    assert (application, lib) == before
    changed = library_with(answer("French level", "B1"), answer("Phone", "+41000"))
    assert (
        material_information_library(application, lib)["revision"]
        == material_information_library(application, changed)["revision"]
    )
    assert (
        information_context(application, lib)["revision"]
        != information_context(application, changed)["revision"]
    )


def test_match_only_sources_are_literal_read_only_and_bind_current_context():
    from career_evidence_graph.application_information import (
        information_source_snapshot,
        validate_information_source,
    )

    lib = library_with(answer("French level", "B2"), answer("German level", "B1", state="inferred"))
    base = {"revision": "old", "items": [], "documents": []}
    before = deepcopy((APPLICATION, lib, base))
    snapshot = information_source_snapshot(APPLICATION, lib, base)
    assert (APPLICATION, lib, base) == before
    assert len(snapshot["items"]) == 1
    item = snapshot["items"][0]
    assert item["source_kind"] == "confirmed_information"
    assert item["resume_eligible"] is False
    assert item["rewrite_allowed"] is False
    assert '"B2"' in item["text"]
    assert validate_information_source(APPLICATION, lib, item)[0]["value"] == "B2"
    changed = library_with(answer("French level", "B1"))
    with pytest.raises(PortalDataError):
        validate_information_source(APPLICATION, changed, item)
    with pytest.raises(PortalDataError):
        validate_information_source(
            {**APPLICATION, "company": "Other"},
            library_with(answer("French level", "B2", scope={"company": "Example"})),
            item,
        )
    malformed = {
        **item,
        "confirmed_information": {**item["confirmed_information"], "fact": "other"},
    }
    with pytest.raises(PortalDataError):
        validate_information_source(APPLICATION, lib, malformed)


@pytest.mark.parametrize("field", ["text", "source_revision", "source_id", "evidence_id"])
def test_information_source_cannot_preserve_binding_but_substitute_its_content(field):
    from career_evidence_graph.application_information import (
        information_source_snapshot,
        validate_information_source,
    )

    lib = library_with(answer("French level", "B2"))
    item = information_source_snapshot(APPLICATION, lib, {})["items"][0]
    with pytest.raises(PortalDataError):
        validate_information_source(APPLICATION, lib, {**item, field: "C2"})


def test_match_only_sources_leave_out_contact_facts_and_record_bookkeeping():
    from career_evidence_graph.application_information import (
        information_source_snapshot,
        validate_information_source,
    )

    level = answer("French level", "B2")
    level[1].update(source="user-self-assessment-no-exam", confirmedAt="2026-10-22T22:40:13Z")
    lib = library_with(
        level,
        answer("Phone number", "+41 00 000 00 00"),
        answer("What are your preferred pronouns", "they/them"),
    )
    items = information_source_snapshot(APPLICATION, lib, {})["items"]
    # Contact and identity facts never bear on a requirement; the matcher never sees them.
    assert [item["confirmed_information"]["fact"] for item in items] == ["language_french_cefr"]
    text = items[0]["text"]
    assert text.count('"B2"') == 1 and "user-self-assessment-no-exam" in text
    assert all(noise not in text for noise in ("confirmedAt", '"key"', '"state"', '"scope"'))
    assert validate_information_source(APPLICATION, lib, items[0])[0]["value"] == "B2"
    assert information_fact("What are your preferred pronouns") == "pronouns"
