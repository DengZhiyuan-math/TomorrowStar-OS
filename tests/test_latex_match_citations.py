"""Presentation-only quote mapping retains exact, attributable source spans."""

import hashlib
from copy import deepcopy

import pytest

from career_evidence_graph.application_match import _quoted_source
from career_evidence_graph.career_portal_data import PortalDataError


def source(text, **overrides):
    return {
        "source_kind": "accepted_resume",
        "text": text,
        "retained_receipt_revision": "receipt-v1",
        "retained_source_sha256": "source-v1",
        "retained_text_sha256": hashlib.sha256(text.encode()).hexdigest(),
        "attribution": "Previously human-accepted resume wording",
        "rewrite_allowed": False,
        "match_eligible": True,
        **overrides,
    }


def test_formatting_only_quote_maps_to_exact_raw_span_and_keeps_proposal():
    raw = r"\item \textbf{Scientific computing:} Python, NumPy and SciPy."
    proposal = "Scientific computing: Python, NumPy and SciPy."
    original = source(raw)
    before = deepcopy(original)
    result = _quoted_source(original, proposal)
    assert result["quote"] == r"\textbf{Scientific computing:} Python, NumPy and SciPy."
    assert result["quote"] == raw[result["quote_start"] : result["quote_end"]]
    assert result["proposed_quote"] == proposal
    assert result["quote_match_policy"] == "latex-presentation-literal/v1"
    assert result["attribution"] == original["attribution"]
    assert result["rewrite_allowed"] is False
    assert original == before


def test_literal_quote_path_is_unchanged():
    result = _quoted_source(source("Python, NumPy and SciPy."), "Python, NumPy")
    assert result["quote"] == "Python, NumPy"
    assert result["quote_start"] == 0
    assert "proposed_quote" not in result


@pytest.mark.parametrize(
    "overrides",
    [
        {"source_kind": "contribution"},
        {"retained_receipt_revision": None},
        {"retained_text_sha256": "tampered"},
    ],
)
def test_formatting_fallback_requires_retained_accepted_source(overrides):
    with pytest.raises(PortalDataError, match="引用片段"):
        _quoted_source(source(r"\textbf{Python:} NumPy.", **overrides), "Python: NumPy.")


@pytest.mark.parametrize(
    ("raw", "proposal"),
    [
        (r"\unknown{Python:} NumPy.", "Python: NumPy."),
        (r"\textbf{Python:} $x$ NumPy.", "Python: NumPy."),
        (r"\textbf{Python:} not implemented NumPy.", "Python: implemented NumPy."),
        (r"\textbf{Python:}  NumPy.", "Python: NumPy."),
        (r"\textbf{Python:} NumPy.", "Python: SciPy."),
        (r"\textbf{Python:} NumPy. \textit{Python:} NumPy.", "Python: NumPy."),
    ],
)
def test_no_macro_math_negation_whitespace_or_ambiguous_repair(raw, proposal):
    with pytest.raises(PortalDataError):
        _quoted_source(source(raw), proposal)


def test_formatting_quote_cannot_cross_source_fields():
    raw = r"\textbf{Python:} NumPy."
    original = source(
        raw,
        quote_segments=[
            {"start": 0, "end": 16, "text": raw[:16], "document_locator": "field.a"},
            {"start": 16, "end": len(raw), "text": raw[16:], "document_locator": "field.b"},
        ],
    )
    with pytest.raises(PortalDataError, match="跨字段"):
        _quoted_source(original, "Python: NumPy.")


def test_negation_context_still_marks_unimplemented_work():
    raw = r"Not implemented: \textbf{Scientific computing:} Python and NumPy."
    result = _quoted_source(source(raw), "Scientific computing: Python and NumPy.")
    assert result["planned_only"] is True
    assert "Not implemented" in result["quote_context"]


def test_formatting_cannot_hide_negation_in_sentence_context():
    raw = r"Not \textbf{implemented}: \textbf{Scientific computing:} Python and NumPy."
    result = _quoted_source(source(raw), "Scientific computing: Python and NumPy.")
    assert result["planned_only"] is True
    assert result["quote_context"] == raw


def test_literal_quote_cannot_hide_formatted_negation_in_sentence_context():
    raw = r"Not \textbf{implemented}: \textbf{Python service}."
    result = _quoted_source(source(raw), "Python service")
    assert result["planned_only"] is True
    assert result["quote_context"] == raw
    assert "proposed_quote" not in result
