"""Employer wording may name tools with digits but may not state unsupported quantities."""

import pytest

from career_evidence_graph.application_inference import _check_expression
from career_evidence_graph.career_portal_data import PortalDataError


def test_tool_names_with_digits_are_not_quantities():
    # Installed MC-11: "ROS2" from the JD made a correct matching answer invalid.
    _check_expression("ROS2, EC2 and 3D tooling are not established.", [], None)


@pytest.mark.parametrize("expression", ["5 years of control work", "Improved latency by 20%"])
def test_quantities_still_need_cited_support(expression):
    with pytest.raises(PortalDataError):
        _check_expression(expression, [{"quote": "Led control work."}], None)


@pytest.mark.parametrize(("judgment", "accepted"), [("partial", True), ("supported", False)])
def test_only_supported_wording_must_have_cited_numbers(judgment, accepted):
    from career_evidence_graph.application_inference import validate_inference

    text = "Work in the stated 100% Zurich-based arrangement."
    quote = "Zurich is the preferred location."
    row = {
        "judgment": judgment,
        "sources": [
            {
                "source_id": "s",
                "source_revision": "r",
                "quote_start": 0,
                "quote_end": len(quote),
                "quote": quote,
            }
        ],
        "inference": {
            "requirement_id": "r1",
            "type": "semantic",
            "relation": {"partial": "partial_support", "supported": "supports"}[judgment],
            "basis": "Recorded location preference.",
            # Installed MC-11: naming the JD's missing "100%" rejected a valid answer.
            "expression_scope": "Zurich preferred; 100% on-site commitment is not established.",
            "calculation": None,
        },
    }
    template = {"text": text, "scoring_framework": {"requirement_id": "r1"}}
    brief = {"groups": [{"requirements": [{"id": "r1", "text": text}]}]}
    if accepted:
        assert validate_inference(row, template, brief)["relation"] == "partial_support"
    else:
        with pytest.raises(PortalDataError):
            validate_inference(row, template, brief)
