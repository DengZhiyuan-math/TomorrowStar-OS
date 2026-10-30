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
