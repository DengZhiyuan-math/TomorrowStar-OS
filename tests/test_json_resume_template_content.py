"""Variable JSON fills an explicit template; fixed text never enters model data."""

from copy import deepcopy

import pytest
from test_json_resume_content import assignment, fragment

from career_evidence_graph.application_resume_content import (
    apply_content_patch,
    assemble_content,
    validate_content,
    validate_plan,
)
from career_evidence_graph.application_resume_render import (
    TEMPLATE_SLOTS,
    render_resume,
    validate_template,
)
from career_evidence_graph.application_worker import digest

TEMPLATE = r"""\documentclass{article}
\usepackage[hidelinks]{hyperref}
\begin{document}
  \textbf{Fixed Applicant}  
\href{mailto:fixed@example.invalid}{fixed@example.invalid}
\href{https://example.invalid/fixed-profile}{LinkedIn}
\section*{Education}
Fixed University --- Recorded degree, in progress
%% TOMORROWSTAR_SUMMARY %%
%% TOMORROWSTAR_SKILLS %%
\section*{Experience}
%% TOMORROWSTAR_EXPERIENCES %%
\end{document}
"""


@pytest.mark.parametrize("placement", ["after_document", "inline", "commented"])
def test_template_rejects_slots_outside_supported_document_positions(placement):
    marker = TEMPLATE_SLOTS["experiences"]
    if placement == "after_document":
        invalid = TEMPLATE.replace(marker, "") + marker + "\n"
    elif placement == "inline":
        invalid = TEMPLATE.replace(marker, "Text " + marker)
    else:
        invalid = TEMPLATE.replace(marker, "% hidden " + marker)
    with pytest.raises(ValueError):
        validate_template(invalid)


def plan():
    return {
        "schema_version": "resume-template-plan/v1",
        "application_id": "application-demo",
        "template_revision": digest(TEMPLATE),
        "assignments": [assignment()],
    }


def test_job_specific_headline_is_rendered_as_escaped_variable_text():
    template = TEMPLATE.replace(
        "%% TOMORROWSTAR_SUMMARY %%", "%% TOMORROWSTAR_HEADLINE %%\n%% TOMORROWSTAR_SUMMARY %%"
    )
    planned = plan()
    planned.update(
        template_revision=digest(template),
        headline={
            "id": "career-headline",
            "text": "Quantitative Research & Data Science",
            "fact_refs": ["fact-demo-1"],
        },
    )
    content = assemble_content(planned, [fragment()])
    rendered = render_resume(content, template=template)
    first, last = rendered.ranges["career-headline"]
    assert rendered.tex[first:last] == "Quantitative Research \\& Data Science\\par\n"
    assert rendered.renderer_revision == "resume-template-renderer/v3"
    assert content["headline"]["text"] == "Quantitative Research & Data Science"
    assert "Fixed University --- Recorded degree, in progress" in rendered.tex


def test_variable_content_fills_template_without_transporting_fixed_text():
    planned, response = plan(), fragment()
    before = deepcopy((planned, response))
    content = assemble_content(planned, [response])
    assert content["schema_version"] == "resume-template-content/v1"
    assert "profile" not in content
    assert "education" not in content
    assert "headline" not in content
    assert "headline" not in validate_plan(planned).model_dump(mode="json")
    assert "Fixed Applicant" not in str(content)
    assert "Fixed University" not in str(content)
    assert validate_content(content).template_revision == digest(TEMPLATE)
    rendered = render_resume(content, template=TEMPLATE)
    expected_experience = (
        "\\subsection*{Validation workflow}\n"
        "Synthetic Lab\\hfill \\par\n"
        "\\begin{itemize}\n"
        "\\item Participated in planning a validation workflow.\n"
        "\\end{itemize}\n"
    )
    expected = (
        TEMPLATE.replace("%% TOMORROWSTAR_SUMMARY %%", "")
        .replace("%% TOMORROWSTAR_SKILLS %%", "")
        .replace("%% TOMORROWSTAR_EXPERIENCES %%", expected_experience)
    )
    assert rendered.tex == expected
    start, end = rendered.ranges["experience-demo-1"]
    assert rendered.tex[start:end] == expected_experience
    assert (planned, response) == before


@pytest.mark.parametrize("placement", ["duplicate", "outside", "inline"])
def test_optional_headline_slot_requires_one_separate_line_inside_document(placement):
    marker = "%% TOMORROWSTAR_HEADLINE %%"
    if placement == "outside":
        template = TEMPLATE + marker + "\n"
    else:
        replacement = marker + "\n" + marker if placement == "duplicate" else "text " + marker
        template = TEMPLATE.replace(
            "%% TOMORROWSTAR_SUMMARY %%", replacement + "\n%% TOMORROWSTAR_SUMMARY %%"
        )
    with pytest.raises(ValueError):
        validate_template(template)


def test_headline_cannot_be_silently_dropped_by_old_template_or_carry_out_of_scope_refs():
    planned = plan()
    planned["headline"] = {"id": "headline", "text": "Data Science", "fact_refs": ["fact-demo-1"]}
    content = assemble_content(planned, [fragment()])
    with pytest.raises(ValueError, match="headline.*slot"):
        render_resume(content, template=TEMPLATE)
    planned["headline"]["fact_refs"] = ["unread-fact"]
    with pytest.raises(ValueError, match="reference"):
        assemble_content(planned, [fragment()])


def test_content_patch_changes_variable_words_and_keeps_template_binding():
    content = assemble_content(plan(), [fragment()])
    patched = apply_content_patch(
        content,
        {
            "schema_version": "resume-content-patch/v1",
            "base_revision": content["revision"],
            "changes": [
                {
                    "item_id": "item-demo-1",
                    "field": "text",
                    "expected": "Participated in planning a validation workflow.",
                    "value": "Contributed to planning a validation workflow.",
                }
            ],
        },
        allowed_targets=[{"item_id": "item-demo-1", "fields": ["text"]}],
    )
    assert patched["schema_version"] == "resume-template-content/v1"
    assert patched["template_revision"] == digest(TEMPLATE)
    assert patched["revision"] != content["revision"]
    assert (
        "Contributed to planning a validation workflow."
        in render_resume(patched, template=TEMPLATE).tex
    )
    assert (
        "Fixed University --- Recorded degree, in progress"
        in render_resume(patched, template=TEMPLATE).tex
    )


@pytest.mark.parametrize(
    "field,value",
    [
        ("profile", {"name": "Model-selected name"}),
        ("education", []),
        ("template", "Model-written document"),
    ],
)
def test_template_model_contracts_cannot_carry_fixed_contents(field, value):
    planned = plan()
    planned[field] = value
    with pytest.raises(ValueError):
        validate_plan(planned)
    content = assemble_content(plan(), [fragment()])
    content[field] = value
    with pytest.raises(ValueError):
        validate_content(content)


@pytest.mark.parametrize("slot", list(TEMPLATE_SLOTS))
@pytest.mark.parametrize("count", [0, 2])
def test_template_requires_each_slot_exactly_once(slot, count):
    marker = TEMPLATE_SLOTS[slot]
    template = TEMPLATE.replace(marker, marker * count)
    with pytest.raises(ValueError, match="each content slot exactly once"):
        validate_template(template)


def test_any_fixed_template_change_requires_explicit_new_binding():
    content = assemble_content(plan(), [fragment()])
    with pytest.raises(ValueError, match="revision"):
        render_resume(content, template=TEMPLATE.replace("Fixed Applicant", "Changed Applicant"))
    with pytest.raises(ValueError, match="revision"):
        render_resume(content, template=TEMPLATE + " ")
    with pytest.raises(ValueError):
        render_resume(content)


def test_slots_follow_literal_template_order_and_ranges_match_rendered_items():
    planned = plan()
    planned["summary"] = [
        {
            "id": "summary-one",
            "text": "Uses 50% of a synthetic budget.",
            "fact_refs": ["fact-demo-1"],
        }
    ]
    planned["skills"] = [
        {"id": "skills-one", "text": "Validation & planning", "fact_refs": ["fact-demo-1"]}
    ]
    template = (
        "\\begin{document}\r\nfixed-prefix\r\n"
        + TEMPLATE_SLOTS["skills"]
        + "\r\nfixed-middle  \r\n"
        + TEMPLATE_SLOTS["experiences"]
        + "\r\nfixed-tail\r\n"
        + TEMPLATE_SLOTS["summary"]
        + "\r\n\\end{document}\r\n"
    )
    planned["template_revision"] = digest(template)
    rendered = render_resume(assemble_content(planned, [fragment()]), template=template)
    assert rendered.tex.startswith("\\begin{document}\r\nfixed-prefix\r\n\\begin{itemize}\n")
    assert "fixed-middle  \r\n" in rendered.tex
    assert "fixed-tail\r\n" in rendered.tex
    first, last = rendered.ranges["summary-one"]
    assert rendered.tex[first:last] == "\\item Uses 50\\% of a synthetic budget.\n"
    first, last = rendered.ranges["skills-one"]
    assert rendered.tex[first:last] == "\\item Validation \\& planning\n"
    assert (
        rendered.ranges["skills-one"][0]
        < rendered.ranges["experience-demo-1"][0]
        < rendered.ranges["summary-one"][0]
    )


def test_item_names_two_writers_chose_independently_are_scoped_by_experience():
    second, written = assignment(), fragment()
    for row in (second, second["experience"], written):
        row.update(experience_id="experience-demo-2", candidate_id="candidate-demo-2")
    second["assignment_revision"] = written["assignment_revision"] = "assignment-demo-2"
    second["experience"]["facts"][0]["id"] = "fact-demo-2"
    second["allowed_fact_refs"] = written["items"][0]["fact_refs"] = ["fact-demo-2"]
    planned = plan()
    planned["assignments"].append(second)
    # Installed MC-11: two Hexagon experience writers both named items
    # "item-1", and assembly refused the whole résumé.
    content = assemble_content(planned, [fragment(), written])
    assert [row["items"][0]["id"] for row in content["experiences"]] == [
        "experience-demo-1-item-demo-1",
        "experience-demo-2-item-demo-1",
    ]
    assert assemble_content(plan(), [fragment()])["experiences"][0]["items"][0]["id"] == (
        "item-demo-1"
    )


def test_characters_the_template_font_lacks_are_written_as_latex():
    from career_evidence_graph.application_resume_render import SYMBOLS_SUFFIX

    written = fragment()
    written["items"][0]["text"] = "π₀.₅ — x²"
    content = assemble_content(plan(), [written])
    rendered = render_resume(content, template=TEMPLATE)
    # Installed MC-11: the Hexagon PDF silently dropped "π₀.₅" and an em dash.
    assert (
        r"\ensuremath{\pi}\textsubscript{0}.\textsubscript{5} --- x\textsuperscript{2}"
        in rendered.tex
    )
    assert rendered.renderer_revision.endswith(SYMBOLS_SUFFIX)
    # Saved renders from before the escapes still reproduce their own bytes.
    legacy = render_resume(content, template=TEMPLATE, symbols=False)
    assert "π₀.₅ — x²" in legacy.tex and not legacy.renderer_revision.endswith(SYMBOLS_SUFFIX)
    assert not render_resume(
        assemble_content(plan(), [fragment()]), template=TEMPLATE
    ).renderer_revision.endswith(SYMBOLS_SUFFIX)
    written["items"][0]["links"] = [{"label": "π₀.₅ — x²", "url": "https://example.com/1"}]
    linked = render_resume(assemble_content(plan(), [written]), template=TEMPLATE).tex
    assert linked.count("x\\textsuperscript{2}") == 1


def test_latin_one_signs_a_t1_font_prints_wrongly_are_written_as_latex():
    """2026-11-12: a headline's "·" printed as "ů"; the compile warned of nothing."""
    from career_evidence_graph.application_resume_render import (
        LEGACY_SYMBOLS_SUFFIX,
        SYMBOLS_SUFFIX,
        symbols_for,
    )

    written = fragment()
    written["items"][0]["text"] = "Research · Modelling, 20 °C, Straße — x²"
    content = assemble_content(plan(), [written])
    rendered = render_resume(content, template=TEMPLATE)
    assert (
        r"Research \textperiodcentered{} Modelling, 20 \textdegree{}C, Stra\ss{}e --- "
        in rendered.tex
    )
    assert not set("·°ß") & set(rendered.tex)
    assert rendered.renderer_revision.endswith(SYMBOLS_SUFFIX)
    assert symbols_for(rendered.renderer_revision) is True
    # A render saved with the first table keeps its own bytes.
    legacy = render_resume(content, template=TEMPLATE, symbols="v1")
    assert "Research · Modelling" in legacy.tex and "---" in legacy.tex
    assert legacy.renderer_revision.endswith(LEGACY_SYMBOLS_SUFFIX)
    assert symbols_for(legacy.renderer_revision) == "v1"
