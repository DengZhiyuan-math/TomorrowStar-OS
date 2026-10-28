"""Shared policy for employer-facing resumes; source provenance stays private."""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

from .career_portal_data import PortalDataError

ENGINE_SHA256 = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()

PRESENTATION_POLICY_VERSION = "resume-presentation/v1"
PRESENTATION_INSTRUCTIONS = (
    "Keep confirmed education fixed: reuse its institutions, degrees, dates and details "
    "without JD-driven rewriting or repeated factual confirmation. Select and order supported "
    "skills and work experiences, and tailor their wording to the current job description. "
    "Never invent facts, skills, mastery, dates, results or personal responsibility. Preserve "
    "real team and collaboration scope, planned versus completed work and factual limits. "
    "AI assistance and tool-use provenance are internal evidence metadata, not employer-facing "
    "resume disclosures: do not add AI-assisted, Codex-assisted, coding-agent attribution or "
    "editor/tool-use explanations. Keep that provenance in internal records. Relevant technical "
    "skills and project technologies such as PyTorch, OpenAI API and AI product development "
    "remain allowed when supported by evidence."
)

# Names alone are valid technologies; only explicit assistance/ownership syntax fails.
_TOOL = r"(?:Codex|ChatGPT|(?:GitHub\s+)?Copilot|coding\s+agents?|VS\s*Code|PyCharm)"
_ASSISTANT = rf"(?:{_TOOL}|(?:AI|artificial\s+intelligence)(?:\s+tools?)?)"
_TOOL_ASSISTANCE = re.compile(
    rf"\b{_TOOL}[\s-]+(?:assisted|generated|authored|implemented|implementation|coding|wrote)\b"
    rf"|\b(?:assisted|generated|written|implemented)\s+by\s+{_ASSISTANT}\b"
    rf"|\bwith\s+(?:help\s+from\s+{_ASSISTANT}|{_ASSISTANT}\s+assistance)\b"
    rf"|\b(?:using|used)\s+(?:{_TOOL}|AI\s+tools?)\b(?!\s+(?:API|SDK|integration|models?)\b)"
    rf"|\b(?:implementation|coding|code)\s*[:|]\s*{_TOOL}\b"
    rf"|{_ASSISTANT}\s*(?:辅助|协助|代写|生成|实现)"
    rf"|(?:使用|借助|通过)\s*(?:{_ASSISTANT}|人工智能工具)\s*(?:完成|辅助|编写|实现)"
    r"|\bwith\s+(?:an?\s+)?(?:AI|artificial\s+intelligence)\s+(?:coding|programming)\s+assistant\b"
    r"|\bAI[\s-]+assisted(?:\s+(?:software\s+)?(?:research|programming|coding|implementation|work|"
    r"engineering|development|design|evaluation|project)\b|(?=\s*(?:[.;,:]|$)))"
    r"|人工智能\s*(?:辅助|协助|代写)",
    re.IGNORECASE,
)


def validate_resume_presentation(text: str) -> None:
    """Reject explicit assistance disclosures, without changing claims or echoing private text."""
    visible = re.sub(r"\\(?:textbf|textit|texttt|emph)\*?\s*", "", text)
    visible = visible.translate(
        str.maketrans(
            {
                "{": "",
                "}": "",
                "~": " ",
                "\u00a0": " ",
                "\u00ad": "",
                **dict.fromkeys("‐‑‒–—―", "-"),
            }
        )
    )
    if _TOOL_ASSISTANCE.search(visible):
        raise PortalDataError(
            "resume_tool_attribution_disclosure",
            "简历正文含内部 AI 或工具辅助归属说明；请修订正文，内部来源记录继续保留。",
            409,
        )
