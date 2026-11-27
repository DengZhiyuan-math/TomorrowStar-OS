"""Find a model's quote in its source text, ignoring typography only (2026-11-24).

Quote checks exist so a model cannot cite words the source does not contain. Typed
apostrophes, dashes, full-width letters, ellipsis glyphs, case, line breaks and a
captured ``{{:}}`` colon are typography, and each such slip had rejected a whole
analysis or résumé. Matching here folds those away and still returns the source's
own characters; a changed word, number or truncated token still fails.
"""

from __future__ import annotations

import re
import unicodedata

_SINGLE = "‘’‚‛′´`"
_DOUBLE = "“”„‟″«»"
_DASH = "‐‑‒–—―−﹘﹣－"
# A match may not start or end inside a word, number or operator (``C++``, ``1.5``).
_JOINED = re.compile(r"[\w+#*/<>=&|%^~-]")


def _fold_char(char):
    if char in _SINGLE:
        return "'"
    if char in _DOUBLE:
        return '"'
    if char in _DASH:
        return "-"
    return unicodedata.normalize("NFKC", char).casefold()


def fold(text):
    """Folded text and, for each folded character, its source index."""
    out, origin = [], []
    text = str(text)
    index = 0
    while index < len(text):
        if text.startswith("{{:}}", index):
            out.append(":")
            origin.append(index)
            index += 5
            continue
        char = text[index]
        if char.isspace():
            if out and out[-1] != " ":
                out.append(" ")
                origin.append(index)
            index += 1
            continue
        for piece in _fold_char(char):
            out.append(piece)
            origin.append(index)
        index += 1
    return "".join(out), origin


def _bounded(text, start, end):
    before = text[start - 1] if start else ""
    after = text[end] if end < len(text) else ""
    if before and (
        _JOINED.match(before)
        or before == "."
        and start > 1
        and text[start - 2].isalnum()
        or before == ","
        and start > 1
        and text[start - 2].isdigit()
    ):
        return False
    return not (
        after
        and (
            _JOINED.match(after)
            or after == "."
            and end + 1 < len(text)
            and text[end + 1].isalnum()
            or after == ","
            and end + 1 < len(text)
            and text[end + 1].isdigit()
        )
    )


def quote_span(text, quote, start=0):
    """(start, end) of ``quote`` in ``text`` from ``start``, or None.

    Exact text wins; otherwise the first typography-folded match on token boundaries.
    """
    text, quote = str(text), str(quote)
    if not quote.strip():
        return None
    exact = text.find(quote, start)
    if exact >= 0:
        return exact, exact + len(quote)
    folded, origin = fold(text)
    wanted = fold(quote)[0].strip()
    if not wanted:
        return None
    position = next((i for i, source in enumerate(origin) if source >= start), len(folded))
    while (found := folded.find(wanted, position)) >= 0:
        end = found + len(wanted)
        if _bounded(folded, found, end):
            last = origin[end - 1]
            stop = last + (5 if text.startswith("{{:}}", last) else 1)
            return origin[found], stop
        position = found + 1
    return None
