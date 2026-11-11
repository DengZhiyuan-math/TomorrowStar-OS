"""Structural assembly is not a second factual or keyword review."""

from copy import deepcopy

import pytest

from career_evidence_graph.application_writing import assemble_fixed_plan
from career_evidence_graph.career_portal_data import PortalDataError


def case():
    original = (
        "\\documentclass[letterpaper]{article}\n% Human template settings\n"
        "\\begin{document}\nFixed Person\n\\section*{Research}\nRecorded work.\n"
        "\\end{document}\n"
    )
    payload = {
        "base": original,
        "sources": [{"source_id": "fact-source", "text": "Recorded work."}],
        "writing_plan": {
            "blocks": [
                {"block_id": "fixed", "group_index": 0, "owner": "fixed"},
                {"block_id": "research", "group_index": 1, "owner": "writer"},
            ],
            "block_order": ["fixed", "research"],
        },
    }
    output = {
        "groups": [
            {
                "title": "Identity",
                "start_line": 1,
                "end_line": 1,
                "source_ids": [],
                "latex": "Fixed Person\n",
                "disposition": "include",
                "reason": "Preserve",
            },
            {
                "title": "Research",
                "start_line": 2,
                "end_line": 3,
                "source_ids": ["fact-source"],
                "latex": "\\section*{Research}\nRecorded work.\n",
                "disposition": "include",
                "reason": "Fixed plan",
            },
        ],
        "limitations": [],
    }
    return payload, output


def test_assembler_preserves_template_and_defers_new_numbers_to_single_final_review():
    payload, output = case()
    output["groups"][1]["latex"] = "\\section*{Research}\nComputed 24 months; used AI tooling.\n"
    before = deepcopy(payload)
    result = assemble_fixed_plan(payload, output)
    assert "Computed 24 months" in result["latex_source"]
    assert result["verification_queue"] == []
    assert result["latex_source"].startswith("\\documentclass[letterpaper]{article}\n% Human")
    assert payload == before
    assert result["block_mapping"][1]["block_id"] == "research"


@pytest.mark.parametrize("change", ["missing", "overlap", "source", "unsafe", "unclosed"])
def test_assembler_rejects_structural_or_reference_failure(change):
    payload, output = case()
    if change == "missing":
        output["groups"].pop()
    elif change == "overlap":
        output["groups"][1]["start_line"] = 1
    elif change == "source":
        output["groups"][1]["source_ids"] = ["foreign"]
    elif change == "unsafe":
        output["groups"][1]["latex"] = "\\input{private}\n"
    else:
        output["groups"][1]["latex"] = "\\section*{Research\n"
    with pytest.raises(PortalDataError):
        assemble_fixed_plan(payload, output)


@pytest.mark.parametrize("heading", ["Qualifications", "学历背景"])
def test_documented_education_cannot_be_relabelled_as_work_under_a_custom_heading(heading):
    import json

    payload, output = case()
    text = f"\\section*{{{heading}}}\nBSc, Synthetic University, 2020--2023.\n"
    payload["base"] = payload["base"].replace("\\section*{Research}\nRecorded work.\n", text)
    payload["sources"].append(
        {
            "source_id": "education",
            "source_kind": "education",
            "text": json.dumps(
                {
                    "degree": "BSc",
                    "institution": "Synthetic University",
                    "period": "2020--2023",
                    "detail": "",
                }
            ),
        }
    )
    output["groups"][1]["latex"] = text.replace("BSc", "PhD")
    # Its submitted references deliberately cite only the work source.
    with pytest.raises(PortalDataError, match="学历"):
        assemble_fixed_plan(payload, output)


def test_documented_education_final_line_without_newline_stays_protected():
    import json

    from career_evidence_graph.application_writing import fixed_education_lines

    body = "\\section*{Qualifications}\nBSc, Synthetic University, 2020--2023."
    source = {
        "source_kind": "education",
        "text": json.dumps(
            {
                "degree": "BSc",
                "institution": "Synthetic University",
                "period": "2020--2023",
                "detail": "",
            }
        ),
    }
    assert fixed_education_lines(body, [source]) == {1, 2}


def test_group_array_order_cannot_move_fixed_header():
    payload, output = case()
    output["groups"].reverse()
    with pytest.raises(PortalDataError, match="底稿位置"):
        assemble_fixed_plan(payload, output)


def test_multiple_documented_degrees_in_custom_section_remain_protected():
    import json

    from career_evidence_graph.application_writing import fixed_education_lines

    body = (
        "\\section*{Qualifications}\nBSc, First University, 2018--2021.\n"
        "MSc, Second University, 2021--2023.\n"
    )
    sources = [
        {
            "source_kind": "education",
            "text": json.dumps(
                {"degree": degree, "institution": institution, "period": period, "detail": ""}
            ),
        }
        for degree, institution, period in [
            ("BSc", "First University", "2018--2021"),
            ("MSc", "Second University", "2021--2023"),
        ]
    ]
    assert fixed_education_lines(body, sources) == {1, 2, 3}
