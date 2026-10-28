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
    assert matching.MAX_PROMPT_BYTES == limits.MAX_MATCH_CONTEXT_BYTES == 128_000
    assert reading.MAX_MATERIAL_BYTES == limits.MAX_MATERIAL_CONTEXT_BYTES == 60_000
    assert limits.context_limits({}) == {
        "match_context_bytes": 128_000,
        "material_context_bytes": 60_000,
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


def test_historical_source_imports_are_direct_aliases_of_the_shared_interface():
    from career_evidence_graph import application_match as matching
    from career_evidence_graph import application_material_packet as reading
    from career_evidence_graph import application_material_sources as sources

    assert matching._sources is reading._sources is sources.source_records
    assert matching._model_source is reading._model_source is sources.model_source
    assert matching._model_sources is reading._model_sources is sources.model_sources
    assert matching._quoted_source is reading._quoted_source is sources.quoted_source
    assert reading._structured_fact is sources.structured_fact


def test_source_and_budget_consumers_do_not_load_reader_or_matcher():
    source = Path(__file__).resolve().parents[1] / "src"
    code = """
import sys
sys.path.insert(0, sys.argv[1])
from career_evidence_graph.application_input_limits import context_limits
from career_evidence_graph.application_material_sources import model_source
assert context_limits({})["match_context_bytes"] == 128000
assert model_source({"source_id": "one", "text": "Known fact."}) == {
    "source_id": "one", "text": "Known fact."
}
assert "career_evidence_graph.application_match" not in sys.modules
assert "career_evidence_graph.application_material_packet" not in sys.modules
"""
    subprocess.run([sys.executable, "-I", "-B", "-c", code, str(source)], check=True)
