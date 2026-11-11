"""Fixed JSON rendering uses synthetic applicant facts only."""

from copy import deepcopy

import pytest

from career_evidence_graph.application_resume_content import ResumeContent, content_revision
from career_evidence_graph.application_resume_render import render_resume


def revised(content):
    payload = ResumeContent.model_validate(content).model_dump(mode="json")
    payload["revision"] = content_revision(payload)
    return payload


def resume_content():
    return revised(
        {
            "schema_version": "resume-content/v1",
            "revision": "content-demo-1",
            "application_id": "application-demo-1",
            "profile": {"name": "Synthetic Person", "contacts": []},
            "education": [
                {
                    "id": "education-demo-1",
                    "institution": "Synthetic University",
                    "qualification": "MSc in Mathematics",
                    "start": "2025",
                    "end": "Present",
                    "status": "in_progress",
                    "details": ["Synthetic scholarship"],
                }
            ],
            "summary": [],
            "skills": [],
            "experiences": [
                {
                    "id": "experience-demo-1",
                    "candidate_id": "experience-demo-1",
                    "title": "Software Engineer",
                    "organization": "Synthetic Team",
                    "start": "2026",
                    "end": None,
                    "location": "Zurich",
                    "items": [
                        {
                            "id": "item-demo-1",
                            "text": "Implemented a validation workflow with the project team.",
                            "fact_refs": ["fact-demo-1"],
                            "inference_refs": [],
                            "origin": "ai",
                            "protected": False,
                            "links": [],
                        }
                    ],
                }
            ],
        }
    )


def test_one_experience_renders_a_complete_document_with_fixed_education():
    result = render_resume(resume_content())
    assert result.tex.startswith(r"\documentclass[10pt,a4paper]{article}")
    assert result.tex.endswith("\\end{document}\n")
    assert result.tex.count(r"\subsection*{") == 1
    assert r"\subsection*{Software Engineer}" in result.tex
    assert "Synthetic Person" in result.tex
    assert "Synthetic University" in result.tex
    assert "MSc in Mathematics" in result.tex
    assert "in progress" in result.tex
    assert "Synthetic scholarship" in result.tex
    assert "Implemented a validation workflow with the project team." in result.tex
    assert result.content_revision == resume_content()["revision"]
    assert result.template_revision == "resume-fixed/v1"
    assert result.renderer_revision == "resume-renderer/v1"


def test_all_content_text_is_literal_including_commands_unicode_and_newlines():
    content = resume_content()
    content["profile"]["name"] = "Élodie & 李"
    content["education"][0]["institution"] = "Institute_1"
    content["experiences"][0]["title"] = "R&D #1"
    content["experiences"][0]["organization"] = "Returns 20%"
    content["experiences"][0]["items"][0]["text"] = (
        "Budget $5 {small} ~ ^ \\input{secret.tex}\r\n第二行"
    )
    tex = render_resume(revised(content)).tex
    assert "Élodie \\& 李" in tex
    assert "Institute\\_1" in tex
    assert r"\subsection*{R\&D \#1}" in tex
    assert "Returns 20\\%" in tex
    assert (
        r"\item Budget \$5 \{small\} \textasciitilde{} \textasciicircum{} "
        r"\textbackslash{}input\{secret.tex\}\mbox{}\newline{}第二行" + "\n"
    ) in tex
    assert r"\input{secret.tex}" not in tex


def test_ranges_select_whole_blocks_and_items_in_content_order():
    content = resume_content()
    second = deepcopy(content["experiences"][0])
    second.update(id="experience-second", candidate_id="experience-second", title="Earlier role")
    second["items"][0].update(id="item-second", text="第二段经历")
    content["experiences"].insert(0, second)
    result = render_resume(revised(content))
    start, end = result.ranges["item-demo-1"]
    assert result.tex[start:end] == (
        "\\item Implemented a validation workflow with the project team.\n"
    )
    start, end = result.ranges["experience-demo-1"]
    assert result.tex[start:end] == (
        "\\subsection*{Software Engineer}\n"
        "Synthetic Team\\hfill 2026\\par\n"
        "Zurich\\par\n"
        "\\begin{itemize}\n"
        "\\item Implemented a validation workflow with the project team.\n"
        "\\end{itemize}\n"
    )
    assert result.ranges["experience-second"][0] < start
    start, end = result.ranges["item-second"]
    assert result.tex[start:end] == "\\item 第二段经历\n"
    assert result.tex.count(r"\subsection*{") == 2
    assert "experience-demo-1" not in result.tex
    assert "fact-demo-1" not in result.tex


def test_contacts_and_item_links_are_fixed_hyperlinks_with_literal_labels():
    content = resume_content()
    content["profile"]["contacts"] = [
        {"label": "Email", "url": "mailto:synthetic@example.test"},
        {"label": "Zurich & Remote"},
    ]
    content["experiences"][0]["items"][0]["links"] = [
        {"label": "Code_1", "url": "https://example.test/a?q=one&x=2#section"},
        {"label": "Literal", "url": "https://example.test/{brace}\\input{file}"},
    ]
    tex = render_resume(revised(content)).tex
    assert r"\href{mailto:synthetic@example.test}{Email}" in tex
    assert "Zurich \\& Remote" in tex
    assert (r"\href{https://example.test/a?q=one\&x=2\#section}{Code\_1}") in tex
    assert (r"\href{https://example.test/\%7Bbrace\%7D\%5Cinput\%7Bfile\%7D}{Literal}") in tex


@pytest.mark.parametrize(
    "url",
    [
        "javascript:alert(1)",
        "data:text/html,hi",
        "file:///tmp/private",
        "run:command",
        "https:///missing-host",
        "https://example.test/line\nbreak",
        "mailto:",
        "//example.test/no-scheme",
    ],
)
def test_unsafe_or_ambiguous_link_targets_are_rejected(url):
    content = resume_content()
    content["profile"]["contacts"] = [{"label": "Unsafe", "url": url}]
    with pytest.raises(ValueError, match="URL"):
        render_resume(revised(content))


def test_optional_summary_and_skills_render_before_experience_and_have_ranges():
    content = resume_content()
    content["summary"] = [
        {"id": "summary-1", "text": "Team validation experience", "fact_refs": ["fact-demo-1"]}
    ]
    content["skills"] = [{"id": "skill-1", "text": "Python & JSON", "fact_refs": ["fact-demo-1"]}]
    result = render_resume(revised(content))
    assert result.tex.index(r"\section*{Summary}") < result.tex.index(r"\section*{Skills}")
    assert result.tex.index(r"\section*{Skills}") < result.tex.index(r"\section*{Experience}")
    start, end = result.ranges["summary-1"]
    assert result.tex[start:end] == "\\item Team validation experience\n"
    start, end = result.ranges["skill-1"]
    assert result.tex[start:end] == "\\item Python \\& JSON\n"
    start, end = result.ranges["education-demo-1"]
    assert result.tex[start:end].startswith(r"\textbf{Synthetic University}")


def test_long_text_empty_options_and_validated_input_are_deterministic_and_unchanged():
    content = resume_content()
    content["education"] = []
    experience = content["experiences"][0]
    experience.update(start=None, end=None, location=None)
    experience["items"][0]["text"] = "  Preserved human wording. " + "Long sentence. " * 300
    experience["items"][0].update(
        origin="human", fact_refs=[], edit_source="synthetic-edit-1", protected=True
    )
    content = revised(content)
    original = deepcopy(content)
    first = render_resume(content)
    assert content == original
    assert first == render_resume(content)
    assert first == render_resume(ResumeContent.model_validate(content))
    assert "Preserved human wording." in first.tex
    assert first.tex.count("Long sentence.") == 300
    assert r"\section*{Education}" not in first.tex
    assert r"\section*{Summary}" not in first.tex
    assert r"\section*{Skills}" not in first.tex
    assert "None" not in first.tex
    assert "synthetic-edit-1" not in first.tex


def test_unknown_template_revision_is_rejected():
    with pytest.raises(ValueError, match="template revision"):
        render_resume(resume_content(), template_revision=r"\input{template}")


@pytest.mark.parametrize("control", ["\0", "\x08", "\x1b", "\x7f"])
def test_text_with_nonprinting_controls_fails_before_returning_tex(control):
    content = resume_content()
    content["experiences"][0]["items"][0]["text"] = "Literal" + control + "text"
    with pytest.raises(ValueError, match="control"):
        render_resume(revised(content))


def test_stale_content_revision_is_rejected_instead_of_misattributing_build():
    content = resume_content()
    content["experiences"][0]["items"][0]["text"] = "Changed after revision was issued."
    with pytest.raises(ValueError, match="revision"):
        render_resume(content)


def test_mutated_model_cannot_bypass_content_validation():
    model = ResumeContent.model_validate(resume_content())
    model.experiences[0].items[0].text = "Changed without revising content identity."
    with pytest.raises(ValueError, match="revision"):
        render_resume(model)
    model.experiences[0].items[0].origin = "unrecognized"
    with pytest.raises(ValueError):
        render_resume(model)


def test_project_title_and_optional_role_are_both_rendered_as_literal_text():
    content = resume_content()
    experience = content["experiences"][0]
    experience["title"] = "Synthetic validation project"
    experience["role"] = "Research & Development Lead"
    result = render_resume(revised(content))
    start, end = result.ranges["experience-demo-1"]
    assert result.tex[start:end].startswith(
        "\\subsection*{Synthetic validation project}\n"
        "Synthetic Team\\hfill 2026\\par\n"
        "Research \\& Development Lead\\par\n"
        "Zurich\\par\n"
    )


def test_leading_and_repeated_newlines_start_an_empty_box_before_each_break():
    content = resume_content()
    content["profile"]["name"] = "\n\nSynthetic Person"
    result = render_resume(revised(content))
    assert r"\mbox{}\newline{}\mbox{}\newline{}Synthetic Person" in result.tex


def test_english_template_uses_default_article_fonts_without_custom_font_setup():
    tex = render_resume(resume_content()).tex
    assert tex.startswith(r"\documentclass[10pt,a4paper]{article}")
    assert "fontspec" not in tex
    assert "xeCJK" not in tex
    assert r"\setmainfont" not in tex
    assert r"\setCJKmainfont" not in tex


def test_personal_project_without_organization_keeps_dates_role_and_content():
    content = resume_content()
    content["experiences"][0].update(organization=None, role="Project contributor")
    result = render_resume(revised(content))
    start, end = result.ranges["experience-demo-1"]
    block = result.tex[start:end]
    assert block.startswith(
        "\\subsection*{Software Engineer}\n2026\\par\nProject contributor\\par\n"
    )
    assert "Implemented a validation workflow with the project team." in block
    assert "None" not in block


def test_url_tilde_is_percent_encoded_to_preserve_the_hyperlink_target():
    content = resume_content()
    content["profile"]["contacts"] = [
        {"label": "Profile", "url": "https://example.invalid/a_b/~user?q=one&x=two%20words#section"}
    ]
    tex = render_resume(revised(content)).tex
    assert (
        r"\href{https://example.invalid/a\_b/\%7Euser?q=one\&x=two\%20words\#section}{Profile}"
    ) in tex
