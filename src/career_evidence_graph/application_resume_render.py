"""Render variable content into fixed TeX, preserving literal template contents.

Historical complete-content rendering remains supported. Neither path writes
files, invokes models or starts a compiler.
"""

from __future__ import annotations

import re
import unicodedata
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, replace
from typing import Any
from urllib.parse import quote, urlsplit

from .application_resume_content import ResumeContent, TemplateResumeContent, validate_content
from .validation.hashing import record_digest as digest

TEMPLATE_REVISION = "resume-fixed/v1"
RENDERER_REVISION = "resume-renderer/v1"
TEMPLATE_RENDERER_REVISION = "resume-template-renderer/v1"
METADATA_RENDERER_REVISION = "resume-template-renderer/v2"
HEADLINE_RENDERER_REVISION = "resume-template-renderer/v3"
HEADLINE_SLOT = "%% TOMORROWSTAR_HEADLINE %%"
TEMPLATE_SLOTS = {
    "summary": "%% TOMORROWSTAR_SUMMARY %%",
    "skills": "%% TOMORROWSTAR_SKILLS %%",
    "experiences": "%% TOMORROWSTAR_EXPERIENCES %%",
}


def template_slots(template: str) -> dict[str, str]:
    """Opt into the career headline without changing historical required slots."""
    return {**TEMPLATE_SLOTS, **({"headline": HEADLINE_SLOT} if HEADLINE_SLOT in template else {})}


_PREAMBLE = r"""\documentclass[10pt,a4paper]{article}
\usepackage[margin=18mm]{geometry}
\usepackage[hidelinks]{hyperref}
\pagestyle{empty}
\setlength{\parindent}{0pt}
\setlength{\parskip}{3pt}
\begin{document}
"""

_ESCAPES = {
    "%": r"\%",
    "&": r"\&",
    "_": r"\_",
    "#": r"\#",
    "$": r"\$",
    "{": r"\{",
    "}": r"\}",
    "~": r"\textasciitilde{}",
    "^": r"\textasciicircum{}",
    "\\": r"\textbackslash{}",
    "\n": r"\mbox{}\newline{}",
}
# Templates use 8-bit fonts; these characters have no glyph there and vanish. Renders
# that write one carry SYMBOLS_SUFFIX, so earlier saved renders still verify.
SYMBOLS_SUFFIX = "+symbols/v1"
SYMBOLS = {
    "\u2014": "---",
    "\u2013": "--",
    "\u2018": "`",
    "\u2019": "'",
    "\u201c": "``",
    "\u201d": "''",
    "\u2026": r"\ldots{}",
    "\u2022": r"\textbullet{}",
    "\u2192": r"\ensuremath{\rightarrow}",
    "\u00d7": r"\ensuremath{\times}",
    "\u00b1": r"\ensuremath{\pm}",
    "\u2248": r"\ensuremath{\approx}",
    "\u2264": r"\ensuremath{\leq}",
    "\u2265": r"\ensuremath{\geq}",
    **{chr(0x2080 + digit): rf"\textsubscript{{{digit}}}" for digit in range(10)},
    **{
        char: rf"\textsuperscript{{{digit}}}"
        for digit, char in enumerate("\u2070\u00b9\u00b2\u00b3\u2074\u2075\u2076\u2077\u2078\u2079")
    },
    **{
        unicodedata.lookup(f"GREEK {case} LETTER {name.upper()}"): rf"\ensuremath{{\{command}}}"
        for case, names in (
            (
                "SMALL",
                "alpha beta gamma delta epsilon zeta eta theta iota kappa lamda mu nu "
                "xi pi rho sigma tau upsilon phi chi psi omega",
            ),
            ("CAPITAL", "Gamma Delta Theta Lamda Xi Pi Sigma Upsilon Phi Psi Omega"),
        )
        for name in names.split()
        for command in [name.replace("amda", "ambda")]
    },
}


_symbols = ContextVar("resume_symbols", default=None)


@contextmanager
def symbol_escapes(enabled: bool = True):
    """Within this block, text escapes also map SYMBOLS; yields the characters mapped."""
    used: list[str] = []
    token = _symbols.set(used if enabled else None)
    try:
        yield used
    finally:
        _symbols.reset(token)


def symbols_for(renderer_revision: str | None) -> bool:
    """Whether a saved render used the symbol escapes."""
    return bool(renderer_revision and renderer_revision.endswith(SYMBOLS_SUFFIX))


def _text(value: str) -> str:
    # A single pass prevents generated escape sequences from being re-escaped.
    if any((ord(char) < 32 and char not in "\r\n\t") or ord(char) == 127 for char in value):
        raise ValueError("resume text contains unsupported control characters")
    used = _symbols.get()
    pieces = []
    for char in value.replace("\r\n", "\n").replace("\r", "\n"):
        if used is not None and char in SYMBOLS:
            used.append(char)
            pieces.append(SYMBOLS[char])
        else:
            pieces.append(_ESCAPES.get(char, char))
    return "".join(pieces)


def _link(label: str, url: str | None) -> str:
    if not url:
        return _text(label)
    parsed = urlsplit(url)
    if (
        any(char.isspace() or ord(char) < 32 or ord(char) == 127 for char in url)
        or parsed.scheme not in {"http", "https", "mailto"}
        or (parsed.scheme in {"http", "https"} and not parsed.hostname)
        or (parsed.scheme == "mailto" and not parsed.path)
    ):
        raise ValueError("unsafe or incomplete resume URL")
    # quote() always preserves ~; its text escape is unsuitable for a URI.
    encoded = quote(url, safe=":/?#[]@!$&'()*+,;=%_").replace("~", "%7E")
    return "\\href{" + _text(encoded) + "}{" + _text(label) + "}"


def _item(item: dict[str, Any]) -> str:
    links = item["links"]
    used = _symbols.get()
    if used is not None and len(links) == 1 and links[0]["label"].strip() == item["text"].strip():
        # A link labelled with the item's own text is the item (same versioned render).
        used.append("link")
        return "\\item " + _link(item["text"], links[0]["url"]) + "\n"
    rendered = " ".join(_link(link["label"], link["url"]) for link in links)
    return "\\item " + _text(item["text"]) + (" " + rendered if rendered else "") + "\n"


@dataclass(frozen=True)
class RenderedResume:
    tex: str
    content_revision: str
    template_revision: str
    renderer_revision: str
    ranges: dict[str, tuple[int, int]]


def validate_template(template: str, expected_revision: str | None = None) -> str:
    """Require every explicit slot exactly once and bind all literal template bytes."""
    if not isinstance(template, str) or any(
        template.count(slot) != 1 for slot in TEMPLATE_SLOTS.values()
    ):
        raise ValueError("resume template must contain each content slot exactly once")
    boundaries = [
        list(re.finditer(r"(?m)^[ \t]*\\" + command + r"\{document\}[ \t]*\r?$", template))
        for command in ("begin", "end")
    ]
    if any(len(matches) != 1 for matches in boundaries):
        raise ValueError("resume template requires one explicit document body")
    beginning, ending = boundaries[0][0].end(), boundaries[1][0].start()
    for marker in template_slots(template).values():
        if template.count(marker) != 1:
            raise ValueError("resume template must contain each content slot exactly once")
        line = re.search(r"(?m)^[ \t]*" + re.escape(marker) + r"[ \t]*\r?$", template)
        if line is None or not beginning < line.start() < line.end() < ending:
            raise ValueError("resume template slots must occupy separate lines inside the document")
    revision = digest(template)
    if expected_revision is not None and revision != expected_revision:
        raise ValueError("resume template revision does not match its fixed contents")
    return revision


def _append_items(pieces, ranges, items):
    if not items:
        return
    pieces.append("\\begin{itemize}\n")
    for item in items:
        start = sum(map(len, pieces))
        rendered = _item(item)
        pieces.append(rendered)
        ranges[item["id"]] = (start, start + len(rendered))
    pieces.append("\\end{itemize}\n")


def _append_experiences(pieces, ranges, experiences, *, metadata_macro=False):
    for row in experiences:
        start = sum(map(len, pieces))
        pieces.append("\\subsection*{" + _text(row["title"]) + "}\n")
        dates = " -- ".join(filter(None, [row.get("start"), row.get("end")]))
        if metadata_macro:
            fields = [row.get("organization"), row.get("role"), row.get("location"), dates]
            if any(fields):
                pieces.append(
                    "\\TomorrowStarExperienceMeta"
                    + "".join("{" + _text(field or "") + "}" for field in fields)
                    + "\n"
                )
        elif row.get("organization"):
            pieces.append(_text(row["organization"]) + "\\hfill " + _text(dates) + "\\par\n")
        elif dates:
            pieces.append(_text(dates) + "\\par\n")
        if not metadata_macro and row.get("role"):
            pieces.append(_text(row["role"]) + "\\par\n")
        if not metadata_macro and row.get("location"):
            pieces.append(_text(row["location"]) + "\\par\n")
        _append_items(pieces, ranges, row["items"])
        ranges[row["id"]] = (start, sum(map(len, pieces)))


def _render_template(content, template):
    revision = validate_template(template, content["template_revision"])
    # Opt in through the fixed preamble. Historical templates keep exact v1 bytes.
    metadata_macro = (
        re.search(
            r"(?m)^[ \t]*\\newcommand\{\\TomorrowStarExperienceMeta\}\[4\]",
            template[: template.index(r"\begin{document}")],
        )
        is not None
    )
    pieces, ranges, offset = [], {}, 0
    selected_slots = template_slots(template)
    if content.get("headline") is not None and "headline" not in selected_slots:
        raise ValueError("career headline requires an explicit template slot")
    slots = sorted((template.index(marker), key, marker) for key, marker in selected_slots.items())
    for position, key, marker in slots:
        pieces.append(template[offset:position])
        body, body_ranges = [], {}
        if key == "headline":
            headline = content.get(key)
            if headline is not None:
                # Reuse the item text/link language without the list marker.
                rendered = _item(headline).removeprefix("\\item ").removesuffix("\n") + "\\par\n"
                body.append(rendered)
                body_ranges[headline["id"]] = (0, len(rendered))
        elif key == "experiences":
            _append_experiences(body, body_ranges, content[key], metadata_macro=metadata_macro)
        else:
            _append_items(body, body_ranges, content[key])
        start = sum(map(len, pieces))
        ranges.update(
            {
                identifier: (start + first, start + last)
                for identifier, (first, last) in body_ranges.items()
            }
        )
        pieces.extend(body)
        offset = position + len(marker)
    pieces.append(template[offset:])
    return RenderedResume(
        tex="".join(pieces),
        content_revision=content["revision"],
        template_revision=revision,
        renderer_revision=(
            HEADLINE_RENDERER_REVISION
            if "headline" in selected_slots
            else METADATA_RENDERER_REVISION
            if metadata_macro
            else TEMPLATE_RENDERER_REVISION
        ),
        ranges=ranges,
    )


def render_resume(
    content: ResumeContent | TemplateResumeContent | dict[str, Any],
    template_revision: str = TEMPLATE_REVISION,
    *,
    template: str | None = None,
    symbols: bool = True,
) -> RenderedResume:
    """Render one complete document; ranges use Python character offsets."""
    with symbol_escapes(symbols) as used:
        rendered = _render(content, template_revision, template)
    if not used:
        return rendered
    return replace(rendered, renderer_revision=rendered.renderer_revision + SYMBOLS_SUFFIX)


def _render(content, template_revision, template):
    content = validate_content(content).model_dump(mode="json")
    if content["schema_version"] == "resume-template-content/v1":
        if template_revision not in {TEMPLATE_REVISION, content["template_revision"]}:
            raise ValueError("unsupported resume template revision")
        return _render_template(content, template)
    if template is not None or template_revision != TEMPLATE_REVISION:
        raise ValueError("unsupported resume template revision")
    ranges = {}
    pieces = [_PREAMBLE, "{\\Large\\bfseries " + _text(content["profile"]["name"]) + "}\\par\n"]
    contacts = content["profile"]["contacts"]
    if contacts:
        pieces.append(
            " | ".join(_link(row["label"], row.get("url")) for row in contacts) + "\\par\n"
        )
    if content["education"]:
        pieces.append("\\section*{Education}\n")
        for row in content["education"]:
            start = sum(map(len, pieces))
            dates = " -- ".join(filter(None, [row.get("start"), row.get("end")]))
            pieces.append(
                "\\textbf{" + _text(row["institution"]) + "}\\hfill " + _text(dates) + "\\par\n"
            )
            pieces.append("\\textit{" + _text(row["qualification"]) + "}\\par\n")
            if row.get("status"):
                pieces.append(_text(row["status"].replace("_", " ")) + "\\par\n")
            for detail in row.get("details", []):
                pieces.append(_text(detail) + "\\par\n")
            ranges[row["id"]] = (start, sum(map(len, pieces)))
    for key, title in (("summary", "Summary"), ("skills", "Skills")):
        if content[key]:
            pieces.append("\\section*{" + title + "}\n")
            _append_items(pieces, ranges, content[key])
    if content["experiences"]:
        pieces.append("\\section*{Experience}\n")
        _append_experiences(pieces, ranges, content["experiences"])
    pieces.append("\\end{document}\n")
    return RenderedResume(
        tex="".join(pieces),
        content_revision=content["revision"],
        template_revision=template_revision,
        renderer_revision=RENDERER_REVISION,
        ranges=ranges,
    )
