"""Reading and matching share literal source representation and input limits."""

import hashlib
import subprocess
import sys
from copy import deepcopy
from pathlib import Path

import pytest


def test_shared_source_interface_anchors_literal_unicode_without_mutating_input():
    from career_evidence_graph.application_material_sources import quoted_source

    original = {"source_id": "source-one", "text": "é proof. Planned extension."}
    before = deepcopy(original)
    quoted = quoted_source(original, "proof.")
    assert quoted["quote"] == "proof."
    assert (quoted["quote_start"], quoted["quote_end"]) == (2, 8)
    assert quoted["quote_context"] == "é proof."
    assert quoted["planned_only"] is False
    assert original == before


def test_shared_budget_is_used_by_match_reading_and_presentation_quotes(monkeypatch):
    from career_evidence_graph import application_input_limits as limits
    from career_evidence_graph import application_match as matching
    from career_evidence_graph import application_material_packet as reading
    from career_evidence_graph.application_material_sources import quoted_source
    from career_evidence_graph.career_portal_data import PortalDataError

    assert matching.context_limits is reading.context_limits is limits.context_limits
    assert matching.MAX_PROMPT_BYTES == limits.MAX_MATCH_CONTEXT_BYTES == 384_000
    assert reading.MAX_MATERIAL_BYTES == limits.MAX_MATERIAL_CONTEXT_BYTES == 200_000
    assert limits.context_limits({}) == {
        "match_context_bytes": 384_000,
        "material_context_bytes": 200_000,
    }
    text = r"\textbf{Confirmed} source body. " + "context " * 100
    source = {
        "source_id": "saved-resume",
        "source_kind": "accepted_resume",
        "text": text,
        "retained_receipt_revision": "saved-receipt",
        "retained_source_sha256": "saved-source",
        "retained_text_sha256": hashlib.sha256(text.encode()).hexdigest(),
    }
    assert quoted_source(source, "Confirmed source body.")["quote_match_policy"] == (
        "latex-presentation-literal/v1"
    )
    monkeypatch.setenv("TOMORROWSTAR_MATCH_CONTEXT_BYTES", "500")
    assert limits.context_limits()["material_context_bytes"] == 499
    with pytest.raises(PortalDataError) as caught:
        quoted_source(source, "Confirmed source body.")
    assert caught.value.code == "match_source_invalid"


def test_source_projection_keeps_order_and_omits_receipt_only_fields():
    from career_evidence_graph.application_material_sources import model_source, model_sources

    first = {"source_id": "first", "text": "Known first fact.", "source_revision": "receipt"}
    second = {"source_id": "second", "text": "Known second fact.", "available": True}
    before = deepcopy([first, second])
    assert model_source(first) == {"source_id": "first", "text": "Known first fact."}
    assert model_sources([first, second]) == {
        "sources": [
            {"source_id": "first", "text": "Known first fact."},
            {"source_id": "second", "text": "Known second fact."},
        ]
    }
    assert [first, second] == before


def test_trusted_projection_sends_evidence_and_boundaries_without_admission_flags():
    from career_evidence_graph.application_material_sources import (
        matching_view,
        model_source,
        model_sources,
    )

    flags = {
        "application_trusted": True,
        "match_eligible": True,
        "documentary_only": True,
        "design_only": False,
        "review_status": "documentary",
        "rewrite_allowed": False,
        "resume_eligible": True,
        "available": True,
    }
    profile = {
        "source_id": "profile",
        "source_name": "sources/profile.json",
        "locator": "profile.experience[0]",
        "document_locator": "$.experience[0].detail",
        "text": "Led delivery.",
        "record_context": {"organization": "Example", "role": "Lead"},
        "attribution": "Editorial statement",
        "boundaries": "",
        "planned_only": False,
        **flags,
    }
    # The program already admitted trusted sources and keeps every flag for its own
    # checks; the model reads only evidence, context and boundaries.
    assert model_source(profile) == {
        "source_id": "profile",
        "text": "Led delivery.",
        "record_context": {"organization": "Example", "role": "Lead"},
        "attribution": "Editorial statement",
        "resume_eligible": True,
    }
    assert model_source(profile | {"planned_only": True})["planned_only"] is True
    confirmed = {
        "source_id": "fact-answer",
        "source_kind": "confirmed_information",
        "text": '{"fact": "language_french_cefr", "value": "B2"}',
        "attribution": "Applicant-confirmed personal statement; retain original source.",
        "boundaries": "Accepted current applicant fact. Preserve its value and application scope.",
        "confirmed_information": {"fact": "language_french_cefr", "references": ["r1"]},
        **flags,
    }
    # The trusted prompt already states what every confirmed fact's boundary says.
    assert model_source(confirmed) == {
        "source_id": "fact-answer",
        "source_kind": "confirmed_information",
        "text": '{"fact": "language_french_cefr", "value": "B2"}',
        "resume_eligible": True,
        "confirmed_information": {"fact": "language_french_cefr"},
    }
    research = {key: value for key, value in profile.items() if key != "application_trusted"}
    assert model_source(research)["match_eligible"] is True
    fact = {
        "source_id": "fact",
        "text": "Built the parser.",
        "record_context": {
            "fact_id": "f1",
            "experience_id": "exp-1",
            "candidate_id": "exp-1",
            "content_revision": "r1",
            "source_refs": ["exp-1-body"],
            "sources": [{"id": "exp-1-body", "locator": "/body; original revision=r1"}],
            "organization": "Example",
            "responsibility": "user",
            "status": "completed",
            "scope": "Bounded self-report.",
        },
        **flags,
    }
    projected = model_sources([fact])
    assert projected["sources"] == [
        {
            "source_id": "fact",
            "text": "Built the parser.",
            "resume_eligible": True,
            # The user's own completed work is the default and carries no labels.
            "record_context": {
                "experience_context_ref": "experience-1",
                "scope_ref": "scope-1",
            },
        }
    ]
    assert projected["experience_contexts"] == {
        "experience-1": {"candidate_id": "exp-1", "organization": "Example"}
    }
    assert projected["scope_contexts"] == {"scope-1": "Bounded self-report."}
    team = deepcopy(fact)
    team["record_context"] |= {"responsibility": "team", "status": "planned"}
    assert model_sources([team])["sources"][0]["record_context"] == {
        "responsibility": "team",
        "status": "planned",
        "experience_context_ref": "experience-1",
        "scope_ref": "scope-1",
    }
    view = matching_view([fact, team | {"source_id": "team"}])
    assert [
        {key: value for key, value in entry.items() if key in {"responsibility", "status"}}
        for entry in view["experiences"][0]["facts"]
    ] == [{}, {"responsibility": "team", "status": "planned"}]


def test_historical_source_imports_are_direct_aliases_of_the_shared_interface():
    from career_evidence_graph import application_match as matching
    from career_evidence_graph import application_material_packet as reading
    from career_evidence_graph import application_material_sources as sources

    assert matching._sources is reading._sources is sources.source_records
    assert matching._model_source is reading._model_source is sources.model_source
    assert matching._matching_view is reading._matching_view is sources.matching_view
    assert reading._model_sources is sources.model_sources
    assert matching._quoted_source is reading._quoted_source is sources.quoted_source
    assert reading._structured_fact is sources.structured_fact


def test_source_and_budget_consumers_do_not_load_reader_or_matcher():
    source = Path(__file__).resolve().parents[1] / "src"
    code = """
import sys
sys.path.insert(0, sys.argv[1])
from career_evidence_graph.application_input_limits import context_limits
from career_evidence_graph.application_material_sources import model_source
assert context_limits({})["match_context_bytes"] == 384000
assert model_source({"source_id": "one", "text": "Known fact."}) == {
    "source_id": "one", "text": "Known fact."
}
assert "career_evidence_graph.application_match" not in sys.modules
assert "career_evidence_graph.application_material_packet" not in sys.modules
"""
    subprocess.run([sys.executable, "-I", "-B", "-c", code, str(source)], check=True)
