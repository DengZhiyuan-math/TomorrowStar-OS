"""Experience facts v2 keeps every v1 fact and separates third-party background."""

from copy import deepcopy

import pytest
from test_career_experience_import import legacy_case
from test_career_experiences import library as library
from test_structured_career_library import content

from career_evidence_graph.application_resume_content import (
    experience_facts_v1,
    upgrade_experience_facts,
)
from career_evidence_graph.career_experience_import import prepare_experience_import
from career_evidence_graph.career_experiences import ExperienceStore
from career_evidence_graph.career_portal_data import PortalDataError


def mixed():
    value = content()
    value["facts"].append(
        {
            "id": "fact-2",
            "text": "The project website describes a FastAPI backend.",
            "source_refs": ["note-1"],
            "responsibility": "third_party",
            "status": "completed",
            "scope": "Website context; not the user's work.",
        }
    )
    return value


def test_upgrade_keeps_only_shared_fields_and_moves_every_scope_to_archive_notes():
    original = mixed()
    upgraded, notes = upgrade_experience_facts(deepcopy(original))
    assert set(upgraded) == {
        "schema_version",
        "revision",
        "experience_id",
        "title",
        "role",
        "organization",
        "location",
        "start",
        "end",
        "sources",
        "facts",
        "context",
    }
    assert upgraded["facts"] == [
        {
            "id": "fact-1",
            "text": "Validated a team model.",
            "responsibility": "user",
            "status": "completed",
            "source_refs": ["note-1"],
        }
    ]
    assert upgraded["context"] == [
        {
            "id": "fact-2",
            "text": "The project website describes a FastAPI backend.",
            "source_refs": ["note-1"],
        }
    ]
    assert notes == [
        {"fact_id": "fact-1", "text": "validation only", "status": "pending"},
        {
            "fact_id": "fact-2",
            "text": "Website context; not the user's work.",
            "status": "pending",
            "context_status": "completed",
        },
    ]
    # Until review, the transitional reader restores every v1 field.
    assert experience_facts_v1(upgraded, notes) == original | {"location": None}


def test_reviewed_notes_leave_matching_and_only_defaults_remain():
    upgraded, notes = upgrade_experience_facts(mixed())
    resolved = [note | {"status": "resolved"} for note in notes]
    rows = experience_facts_v1(upgraded, resolved)["facts"]
    assert [row["scope"] for row in rows] == [
        "Recorded experience fact.",
        "Experience background; not the user's activity.",
    ]
    assert rows[1]["status"] == "completed"


def test_saved_v2_record_projects_the_same_library_items(library):
    adapter, root, _, _, _ = library
    first = ExperienceStore(root).save("alpha", title="Reviewed research", content=mixed())
    before = adapter.snapshot_for_analysis({"documents": [], "items": []}, ["alpha"])["items"]
    assert adapter.upgrade_experience_facts() == {"upgraded": ["alpha"]}
    saved = ExperienceStore(root).get("alpha")
    assert saved["content"]["schema_version"] == "experience-facts/v2"
    assert saved["previous_revision"] == first["revision"]
    assert adapter.upgrade_experience_facts() == {"upgraded": []}
    after = adapter.snapshot_for_analysis({"documents": [], "items": []}, ["alpha"])["items"]
    assert [(row["text"], row["attribution"], row["boundaries"]) for row in after] == [
        (row["text"], row["attribution"], row["boundaries"]) for row in before
    ]
    # Ordinary edits keep the archive notes.
    edited = adapter.save_experience(
        "alpha", metadata={"status": "completed"}, expected_revision=saved["revision"]
    )
    assert edited["notes"] == saved["notes"]


def test_upgrade_keeps_record_fields_and_unavailable_sources(library):
    adapter, root, _, _, _ = library
    first = ExperienceStore(root).save(
        "alpha",
        title="Reviewed research",
        content=mixed(),
        metadata={"import_status": "pending", "unavailable_sources": ["missing.pdf"]},
    )
    adapter.upgrade_experience_facts(["alpha"])
    saved = ExperienceStore(root).get("alpha")
    assert {key: saved[key] for key in ("metadata", "materials", "origin", "title")} == {
        key: first[key] for key in ("metadata", "materials", "origin", "title")
    }


def test_notes_must_belong_to_the_saved_facts(library):
    _, root, _, _, _ = library
    upgraded, notes = upgrade_experience_facts(mixed())
    with pytest.raises(PortalDataError):
        ExperienceStore(root).save(
            "alpha",
            title="Reviewed research",
            content=upgraded,
            notes=notes + [{"fact_id": "missing", "text": "x", "status": "pending"}],
        )


@pytest.mark.parametrize("field", ["responsibility", "status"])
def test_v2_rejects_values_outside_the_unified_vocabulary(field):
    upgraded, _ = upgrade_experience_facts(content())
    upgraded["facts"][0][field] = "third_party" if field == "responsibility" else "delivered"
    with pytest.raises(ValueError):
        experience_facts_v1(upgraded)


def test_incremental_import_onto_an_upgraded_record_keeps_its_notes():
    previous, request = legacy_case()
    plan = prepare_experience_import(previous, request)
    previous.pop("body")
    upgraded, notes = upgrade_experience_facts(plan["content"])
    notes = [note | {"status": "resolved"} for note in notes]
    previous.update(content=upgraded, notes=notes, migration=plan["migration"])
    request.update(content=deepcopy(plan["content"]), parts=[])
    request["content"]["facts"][0]["scope"] = "Recorded experience fact."
    result = prepare_experience_import(previous, request)
    assert result["content"]["schema_version"] == "experience-facts/v2"
    assert result["content"]["facts"] == upgraded["facts"]
    assert result["notes"] == notes


def test_curated_directory_summary_and_terms_survive_the_upgrade_and_later_edits(library):
    import json

    adapter, root, _, _, _ = library
    ExperienceStore(root).save("alpha", title="Reviewed research", content=mixed())
    path = root / ".tomorrowstar-experiences/directory.json"
    rows = json.loads(path.read_text())
    # Installed library: curation wrote these rows directly; a save rebuilt them.
    rows["alpha"].update(summary="Curated summary.", retrieval_terms=["Model validation"])
    path.write_text(json.dumps(rows))
    adapter.upgrade_experience_facts()
    saved = ExperienceStore(root).get("alpha")
    edited = adapter.save_experience(
        "alpha", metadata={"status": "completed"}, expected_revision=saved["revision"]
    )
    row = ExperienceStore(root).directory()["alpha"]
    assert edited["metadata"]["summary"] == row["summary"] == "Curated summary."
    assert row["retrieval_terms"] == ["Model validation"]


def test_strict_output_schema_requires_every_property_and_drops_defaults():
    from career_evidence_graph.application_resume_content import TemplateResumePlan
    from career_evidence_graph.codex_cli import strict_output_schema

    schema = strict_output_schema(TemplateResumePlan.model_json_schema())
    # Installed MC-11: the provider rejected every résumé author call for the
    # optional headline missing from required.
    assert set(schema["required"]) == set(schema["properties"])
    assert "default" not in str(schema)
