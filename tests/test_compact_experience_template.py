"""An explicit template header joins metadata without changing legacy renders."""

from copy import deepcopy

import pytest
from test_json_resume_content import fragment
from test_json_resume_template_content import TEMPLATE, plan

from career_evidence_graph.application_content_reconcile import reconcile_content
from career_evidence_graph.application_resume_content import assemble_content, content_revision
from career_evidence_graph.application_resume_render import render_resume
from career_evidence_graph.application_worker import digest


def compact_content():
    template = TEMPLATE.replace(
        r"\begin{document}",
        "\\newcommand{\\TomorrowStarExperienceMeta}[4]{#2 #1 #3 #4}\n"
        r"\begin{document}",
    )
    planned = plan()
    planned["template_revision"] = digest(template)
    content = assemble_content(planned, [fragment()])
    content["experiences"][0].update(
        organization="R&D Lab",
        role="Research Intern",
        location="Remote",
        start="2026",
        end="Present",
    )
    content["revision"] = content_revision(content)
    return content, template


def test_template_controls_a_single_metadata_header_with_all_literal_fields():
    content, template = compact_content()
    rendered = render_resume(content, template=template)
    assert rendered.tex.count(r"\subsection*{Validation workflow}") == 1
    assert (
        r"\TomorrowStarExperienceMeta{R\&D Lab}{Research Intern}{Remote}{2026 -- Present}"
        in rendered.tex
    )
    assert "Remote\\par\n" not in rendered.tex
    assert rendered.renderer_revision == "resume-template-renderer/v2"


def test_compact_header_keeps_human_wording_round_trip_and_ranges():
    content, template = compact_content()
    before = deepcopy(content)
    rendered = render_resume(content, template=template)
    edited = rendered.tex.replace(
        "Participated in planning a validation workflow.", "Human validation wording."
    )
    result = reconcile_content(content, template, edited, "prism:human-wording")
    assert result["status"] == "mapped"
    item = result["content"]["experiences"][0]["items"][0]
    assert item["text"] == "Human validation wording."
    assert item["origin"] == "human" and item["protected"]
    assert render_resume(result["content"], template=template).tex == edited
    start, end = rendered.ranges["experience-demo-1"]
    assert rendered.tex[start:end].startswith(r"\subsection*{Validation workflow}")
    assert r"\TomorrowStarExperienceMeta" in rendered.tex[start:end]
    assert content == before
    changed_header = rendered.tex.replace("{Remote}", "{Elsewhere}")
    assert reconcile_content(content, template, changed_header, "header-edit")["status"] == (
        "unmerged"
    )


@pytest.mark.parametrize(
    ("organization", "role", "location", "start", "end", "expected"),
    [
        (None, None, "Remote", None, None, r"\TomorrowStarExperienceMeta{}{}{Remote}{}"),
        # 2026-11-16: an entry with only dates carries them on its title line.
        (
            None,
            None,
            None,
            "2026",
            None,
            r"\subsection*{Validation workflow\hfill\mbox{\normalfont\small 2026}}",
        ),
        (
            "Lab_1",
            "R&D {lead}",
            None,
            None,
            None,
            r"\TomorrowStarExperienceMeta{Lab\_1}{R\&D \{lead\}}{}{}",
        ),
        (None, None, None, None, None, None),
    ],
)
def test_optional_fields_preserve_escaped_values_without_empty_metadata_rows(
    organization, role, location, start, end, expected
):
    content, template = compact_content()
    content["experiences"][0].update(
        organization=organization, role=role, location=location, start=start, end=end
    )
    content["revision"] = content_revision(content)
    rendered = render_resume(content, template=template)
    block = rendered.tex[slice(*rendered.ranges["experience-demo-1"])]
    if expected is None:
        assert "TomorrowStarExperienceMeta" not in block
    else:
        assert expected in block


def test_an_entry_with_only_dates_carries_them_on_its_title_line():
    # 2026-11-16 (Volatility Wins): an empty header line showed only "2026 -- 2026".
    content, template = compact_content()
    content["experiences"][0].update(
        organization=None, role=None, location=None, start="2026", end="2026"
    )
    content["revision"] = content_revision(content)
    rendered = render_resume(content, template=template)
    assert r"\subsection*{Validation workflow\hfill\mbox{\normalfont\small 2026}}" in rendered.tex
    assert r"\TomorrowStarExperienceMeta" not in rendered.tex.split(r"\begin{document}")[1]
    assert rendered.renderer_revision.endswith("+dated-title/v1")
    saved = render_resume(content, template=template, layout=False)
    assert r"\TomorrowStarExperienceMeta{}{}{}{2026 -- 2026}" in saved.tex
    assert "dated-title" not in saved.renderer_revision


def test_an_entry_with_a_role_keeps_its_layout_and_version():
    content, template = compact_content()
    assert render_resume(content, template=template) == render_resume(
        content, template=template, layout=False
    )
