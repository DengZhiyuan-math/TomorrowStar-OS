"""Conservative language admission and mechanical source-review hints."""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

# Cache identity follows the helper code actually loaded for this process.
ENGINE_SHA256 = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()

_LANGUAGES = {
    "en": r"English|anglais|Englisch|英文|英语",
    "de": r"German|allemand|Deutsch|德文|德语",
    "fr": r"French|français|francais|Französisch|法文|法语",
    "it": r"Italian|italien|italiano|Italienisch",
    "es": r"Spanish|espagnol|español|Spanisch",
    "nl": r"Dutch|néerlandais|Niederländisch",
    "pt": r"Portuguese|portugais|português|Portugiesisch",
    "zh": r"Chinese|chinois|Chinesisch|中文|汉语",
    "ja": r"Japanese|japonais|Japanisch|日文|日语",
    "sv": r"Swedish|瑞典语|瑞典文",
}
_LANGUAGE = "(?:" + "|".join(_LANGUAGES.values()) + ")"
_RESUME = r"(?:\b(?:CVs?|resum[eé]s?|résumés?|curriculum vitae|Lebenslauf)\b|简历|履历|履歷)"
_DATES = re.compile(r"\b(?:19|20)\d{2}(?:[-/]\d{1,2}(?:[-/]\d{1,2})?)?\b")
_NUMBERS = re.compile(r"(?<!\w)\d+(?:[.,]\d+)*(?:%|x)?(?!\w)")
_TECHNICAL = re.compile(
    r"\b(?:Python|JavaScript|TypeScript|Java|Rust|Go|SQL|PostgreSQL|SQLite|"
    r"PyTorch|TensorFlow|Kubernetes|Docker|Linux|macOS|React|NumPy|pandas)\b"
    r"|\bC\+\+|\bC#|\b[A-Z][A-Z0-9]{1,}\b"
)


def review_findings(source: str, rewritten: str) -> dict:
    """Report literal token differences, without claiming factual or semantic acceptance."""

    def tokens(text):
        dates = set(_DATES.findall(text))
        return {
            "numbers": set(_NUMBERS.findall(_DATES.sub(" ", text))),
            "dates": dates,
            "technical_terms": set(_TECHNICAL.findall(text)),
        }

    before, after = tokens(source), tokens(rewritten)
    return {
        "method": "mechanical_not_semantic",
        "review_required": True,
        "checks": [
            {
                "category": category,
                "added": sorted(after[category] - before[category]),
                "omitted": sorted(before[category] - after[category]),
            }
            for category in ("numbers", "dates", "technical_terms")
        ],
        "message": "机械差异提示不能代替语义审核；请核对原文与改写。术语扫描范围有限。",
    }


def resume_language_policy(jd: str) -> dict:
    """Pause explicit non-English submission requirements; skill language is separate."""
    requirements, needs_input = [], False
    for sentence in re.findall(r"[^.!?\n]+(?:[.!?]|$)", jd or ""):
        text = sentence.strip()
        resume = re.search(_RESUME, text, re.I)
        if not resume:
            continue
        phrases = []
        prefix = re.search(
            rf"({_LANGUAGE}(?:\s*(?:,|and|or|ou|et|und|oder|as well as)\s*{_LANGUAGE})*)"
            rf"(?:[- ]language|版)?\s*{_RESUME}",
            text,
            re.I,
        )
        if prefix:
            phrases.append(prefix.group(1))
        post_resume = text[resume.end() :]
        scaffold = re.search(r"(?:\bin|\binto|\ben|\bauf)\s+([^.;:]+)", post_resume, re.I)
        capability_scope = scaffold and re.search(
            r"\b(?:proficiency|fluency|experience|knowledge|skills)\s*$",
            post_resume[: scaffold.start()],
            re.I,
        )
        suffix = re.search(
            rf"(?:\bin|\binto|\ben|\bauf)\s+(?:(?:both|either)\s+)?({_LANGUAGE}"
            rf"(?:\s*(?:,|and|or|ou|et|und|oder|as well as)\s*(?:(?:in|en|auf)\s+)?{_LANGUAGE})*)",
            post_resume,
            re.I,
        )
        if suffix and not capability_scope:
            phrases.append(suffix.group(1))
            if re.match(r"\s*(?:and|or|et|ou|und|oder)\b", post_resume[suffix.end() :], re.I):
                needs_input = True
                requirements.append({"text": text, "language": "unknown"})
        elif not capability_scope:
            # Unknown explicit document language fails closed. File formats and destinations
            # remain separate from language; this is intentionally a bounded grammar.
            language_shape = scaffold and (
                re.fullmatch(r"[A-ZÀ-ÖØ-Þ][\w-]+", scaffold.group(1).strip())
                or re.search(r"\blanguage\b", scaffold.group(1), re.I)
            )
            if language_shape and not re.match(
                r"(?:(?:one|a single)\s+)?"
                r"(?:PDF|DOCX?|ODT|RTF|TXT|HTML|LaTeX|plain text|file)\b"
                r"|(?:(?:our|the|this|your|an?)\s+)?(?:online\s+)?"
                r"(?:portal|system|website|application form)\b",
                scaffold.group(1),
                re.I,
            ):
                needs_input = True
                requirements.append({"text": text, "language": "unknown"})
        named_language = re.search(
            rf"^\s+(?:language\s+)?(?:must|should)\s+be\s+({_LANGUAGE})",
            post_resume,
            re.I,
        )
        if named_language:
            phrases.append(named_language.group(1))
        elif re.match(r"^\s+language\s+(?:must|should)\s+be\s+\S", post_resume, re.I) or re.match(
            r"^\s+(?i:(?:must|should)\s+be)\s+[A-Z][a-z]+\b", post_resume
        ):
            needs_input = True
            requirements.append({"text": text, "language": "unknown"})
        for phrase in phrases:
            languages = [
                code for code, pattern in _LANGUAGES.items() if re.search(pattern, phrase, re.I)
            ]
            optional_english = (
                "en" in languages
                and bool(re.search(r"\b(?:or|ou|oder)\b", phrase, re.I))
                and not re.search(r"\b(?:and|et|und|as well as)\b", phrase, re.I)
            )
            if any(code != "en" for code in languages) and not optional_english:
                needs_input = True
            requirements.extend({"text": text, "language": code} for code in languages)
    return {
        "status": "needs_input" if needs_input else "default_english",
        "language": None if needs_input else "en",
        "requirements": requirements,
        "message": "岗位明确要求其他简历语言，请先确认后单独处理。"
        if needs_input
        else "按 v1.0 使用英文简历。",
    }
