"""Public resume wording excludes internal tool attribution, not technical skills."""

import pytest

from career_evidence_graph.career_portal_data import PortalDataError


def test_explicit_ai_tool_assistance_is_rejected_without_echoing_resume_text():
    from career_evidence_graph.resume_presentation import validate_resume_presentation

    with pytest.raises(PortalDataError) as failure:
        validate_resume_presentation(
            "Designed the synthetic-private protocol with Codex assistance."
        )
    assert failure.value.code == "resume_tool_attribution_disclosure"
    assert failure.value.status == 409
    assert "synthetic-private" not in failure.value.message


@pytest.mark.parametrize(
    "text",
    [
        "Codex-assisted implementation.",
        "AI-assisted research engineering.",
        "Implemented the service with help from ChatGPT.",
        "The implementation was assisted by GitHub Copilot.",
        "Used Codex to write the service.",
        "Built the prototype using AI tools.",
        "Implementation | Codex",
        "Codex implemented the service.",
        "Used VSCode to implement the service.",
        "由 Codex 辅助实现。",
        "使用 ChatGPT 完成代码。",
        "AI 辅助编程。",
        "借助人工智能工具完成项目。",
    ],
)
def test_assistance_disclosure_phrases_are_rejected(text):
    from career_evidence_graph.resume_presentation import validate_resume_presentation

    with pytest.raises(PortalDataError, match="内部"):
        validate_resume_presentation(text)


@pytest.mark.parametrize(
    "text",
    [
        "Built AI education systems with PyTorch and OpenAI API.",
        "Developed a Codex integration for a research product.",
        "Evaluated GitHub Copilot model performance on reproducible benchmarks.",
        "Skills: Python, PyTorch, OpenAI API, AI evaluation.",
        "Designed a collaborative evaluation protocol with a research team.",
        "设计并部署人工智能教育产品，使用 OpenAI API。",
        "Built an AI assistant for education.",
        "Built a product using AI for tutoring.",
        "Evaluated AI-generated model outputs.",
        "Developed an AI-assisted education system.",
    ],
)
def test_technical_skills_ai_products_and_collaboration_remain_allowed(text):
    from career_evidence_graph.resume_presentation import validate_resume_presentation

    validate_resume_presentation(text)


@pytest.mark.parametrize(
    "text",
    [
        r"\textbf{Codex}-assisted implementation.",
        r"AI~assisted research engineering.",
        "AI‑assisted research engineering.",
    ],
)
def test_visible_assistance_cannot_be_hidden_by_resume_formatting(text):
    from career_evidence_graph.resume_presentation import validate_resume_presentation

    with pytest.raises(PortalDataError):
        validate_resume_presentation(text)


@pytest.mark.parametrize(
    "text",
    [
        "AI-assisted software development.",
        "Implemented with artificial intelligence assistance.",
        "Developed the service with an AI coding assistant.",
    ],
)
def test_explicit_generic_ai_work_assistance_is_rejected(text):
    from career_evidence_graph.resume_presentation import validate_resume_presentation

    with pytest.raises(PortalDataError) as failure:
        validate_resume_presentation(text)
    assert failure.value.code == "resume_tool_attribution_disclosure"
