"""Explicit import maps old source ranges instead of guessing facts from TeX."""

from copy import deepcopy

import pytest

from career_evidence_graph.career_experience_import import prepare_experience_import


def legacy_case():
    text = "Planned a Python validation workflow with the team."
    previous = {
        "candidate_id": "fixed-id",
        "title": "Validation",
        "revision": "stored-version-1",
        "body": text,
        "metadata": {},
        "materials": [],
    }
    request = {
        "schema_version": "experience-import/v1",
        "expected_revision": "stored-version-1",
        "content": {
            "schema_version": "experience-facts/v1",
            "revision": "program-will-replace-this",
            "candidate_id": "fixed-id",
            "experience_id": "fixed-id",
            "title": "Validation",
            "sources": [{"id": "original-note", "locator": "/body"}],
            "facts": [
                {
                    "id": "fact-1",
                    "text": text,
                    "source_refs": ["original-note"],
                    "responsibility": "team",
                    "status": "planned",
                    "scope": "validation-project",
                }
            ],
        },
        "parts": [
            {
                "id": "part-1",
                "source_pointer": "/body",
                "start": 0,
                "end": len(text),
                "quote": text,
                "disposition": "fact",
                "fact_ids": ["fact-1"],
                "source_ref": "original-note",
                "reason": "Preserve the recorded plan and team responsibility.",
            }
        ],
    }
    return previous, request


def test_explicit_mapping_preserves_fact_and_original_input():
    previous, request = legacy_case()
    before = deepcopy((previous, request))
    result = prepare_experience_import(previous, request)
    assert result["ready"] is True
    assert result["unresolved"] == []
    assert result["content"]["facts"][0]["text"] == previous["body"]
    assert result["migration"]["from_revision"] == "stored-version-1"
    assert (previous, request) == before


def test_unmapped_unique_text_stays_unresolved_and_blocks_publication():
    previous, request = legacy_case()
    previous["body"] += " No deployment or measured outcome exists."
    result = prepare_experience_import(previous, request)
    assert result["ready"] is False
    assert result["unresolved"][0]["source_pointer"] == "/body"
    assert result["unresolved"][0]["quote"] == " No deployment or measured outcome exists."


@pytest.mark.parametrize(
    "changes",
    [
        {"source_ref": "another-source"},
        {"fact_ids": ["invented-fact"]},
        {"fact_ids": []},
        {"fact_ids": ["fact-1", "fact-1"]},
    ],
)
def test_mapping_cannot_claim_coverage_with_unbound_fact_or_source(changes):
    previous, request = legacy_case()
    request["parts"][0].update(changes)
    with pytest.raises(ValueError):
        prepare_experience_import(previous, request)


def test_new_fact_without_source_mapping_is_not_ready():
    previous, request = legacy_case()
    request["content"]["facts"].append(
        {**request["content"]["facts"][0], "id": "unmapped-fact", "text": "Separate assertion."}
    )
    result = prepare_experience_import(previous, request)
    assert result["ready"] is False
    assert result["unresolved"] == [{"fact_id": "unmapped-fact", "reason": "unmapped_fact"}]


def test_unique_supplement_cannot_be_discarded_as_a_duplicate():
    previous, request = legacy_case()
    text = "A unique observation on convergence."
    previous["materials"] = [{"id": "note", "role": "supplement", "text": text}]
    request["content"]["sources"].append({"id": "note", "locator": "/materials/0/text"})
    request["content"]["facts"][0]["source_refs"].append("note")
    request["parts"].append(
        {
            **request["parts"][0],
            "id": "part-2",
            "source_pointer": "/materials/0/text",
            "end": len(text),
            "quote": text,
            "disposition": "duplicate",
            "source_ref": "note",
            "duplicate_of": "part-1",
        }
    )
    with pytest.raises(ValueError, match="duplicate"):
        prepare_experience_import(previous, request)


def test_identical_text_with_different_responsibility_is_not_a_duplicate():
    previous, request = legacy_case()
    text = previous["body"]
    previous["materials"] = [
        {"id": "other-work", "role": "supplement", "text": text, "attribution": "Other person"}
    ]
    request["content"]["sources"].append({"id": "other", "locator": "/materials/0/text"})
    request["content"]["facts"][0]["source_refs"].append("other")
    request["parts"].append(
        {
            **request["parts"][0],
            "id": "part-2",
            "source_pointer": "/materials/0/text",
            "disposition": "duplicate",
            "source_ref": "other",
            "duplicate_of": "part-1",
        }
    )
    with pytest.raises(ValueError, match="duplicate"):
        prepare_experience_import(previous, request)


def test_literal_copy_with_same_responsibility_keeps_both_source_relationships():
    previous, request = legacy_case()
    previous["materials"] = [
        {"id": "copy", "source_name": "copy.txt", "role": "artifact", "text": previous["body"]}
    ]
    request["content"]["sources"].append({"id": "copy", "locator": "/materials/0/text"})
    request["content"]["facts"][0]["source_refs"].append("copy")
    request["parts"].append(
        {
            **request["parts"][0],
            "id": "part-2",
            "source_pointer": "/materials/0/text",
            "disposition": "duplicate",
            "source_ref": "copy",
            "duplicate_of": "part-1",
        }
    )
    result = prepare_experience_import(previous, request)
    assert result["ready"] is True
    assert result["content"]["facts"][0]["source_refs"] == ["original-note", "copy"]


def test_every_claimed_fact_source_needs_a_bound_old_source_range():
    previous, request = legacy_case()
    request["content"]["sources"].append({"id": "unmapped", "locator": "invented:/missing"})
    request["content"]["facts"][0]["source_refs"].append("unmapped")
    result = prepare_experience_import(previous, request)
    assert result["ready"] is False
    assert result["unresolved"] == [
        {"fact_id": "fact-1", "source_ref": "unmapped", "reason": "unmapped_fact_source"}
    ]


@pytest.mark.parametrize(
    "change",
    [
        {"quote": "Rewritten source quote"},
        {"start": -1},
        {"end": 10000},
        {"source_pointer": "/outside/the/record"},
    ],
)
def test_bad_source_ranges_are_rejected_without_touching_inputs(change):
    previous, request = legacy_case()
    request["parts"][0].update(change)
    before = deepcopy((previous, request))
    with pytest.raises(ValueError):
        prepare_experience_import(previous, request)
    assert (previous, request) == before


def test_presentation_ranges_preserve_raw_tex_without_entering_facts():
    previous, request = legacy_case()
    prefix = "\\section*{Validation}\n"
    previous["body"] = prefix + previous["body"]
    request["parts"][0]["start"] += len(prefix)
    request["parts"][0]["end"] += len(prefix)
    request["parts"].insert(
        0,
        {
            "id": "heading",
            "source_pointer": "/body",
            "start": 0,
            "end": len(prefix),
            "quote": prefix,
            "disposition": "presentation",
            "reason": "Heading retained as provenance.",
        },
    )
    result = prepare_experience_import(previous, request)
    assert result["ready"] is True
    assert r"\section*{" not in result["content"]["facts"][0]["text"]
    assert result["migration"]["parts"][0]["quote"] == prefix
    assert previous["body"].startswith(prefix)


@pytest.mark.parametrize("field", ["text", "responsibility", "status", "scope", "source_refs"])
def test_incremental_import_cannot_replace_saved_fact_fields(field):
    previous, request = legacy_case()
    plan = prepare_experience_import(previous, request)
    previous.pop("body")
    previous.update(content=plan["content"], migration=plan["migration"])
    request.update(content=deepcopy(plan["content"]), parts=[])
    request["content"]["facts"][0][field] = {
        "text": "Led a deployed production system.",
        "responsibility": "user",
        "status": "completed",
        "scope": "production ownership",
        "source_refs": [],
    }[field]
    with pytest.raises(ValueError):
        prepare_experience_import(previous, request)


def test_incremental_import_keeps_saved_sources_and_requires_new_reference_coverage():
    previous, request = legacy_case()
    plan = prepare_experience_import(previous, request)
    previous.pop("body")
    previous.update(content=plan["content"], migration=plan["migration"])
    request.update(content=deepcopy(plan["content"]), parts=[])
    request["content"]["sources"][0]["locator"] = "changed-location"
    with pytest.raises(ValueError, match="saved sources"):
        prepare_experience_import(previous, request)
    request["content"] = deepcopy(plan["content"])
    request["content"]["sources"].append({"id": "new", "locator": "not-delivered"})
    request["content"]["facts"][0]["source_refs"].append("new")
    result = prepare_experience_import(previous, request)
    assert result["ready"] is False
    assert result["unresolved"] == [
        {"fact_id": "fact-1", "source_ref": "new", "reason": "unmapped_fact_source"}
    ]
