"""Conservatively reconcile program-rendered variable TeX with human wording.

Only the fixed renderer's literal item language is accepted. Exact re-rendering
is the adoption gate; unsupported TeX remains available to the caller unchanged.
This module performs no I/O and never changes the parent or fixed template.
"""

from __future__ import annotations

import re
from copy import deepcopy
from difflib import unified_diff
from hashlib import sha256

from .application_resume_content import content_revision, validate_content
from .application_resume_render import _ESCAPES, render_resume, template_slots
from .validation.hashing import record_digest as digest


class _Unmerged(ValueError):
    pass


def _decode(text):
    pieces, offset = [], 0
    tokens = sorted(((value, key) for key, value in _ESCAPES.items()), reverse=True)
    while offset < len(text):
        if text[offset] != "\\":
            pieces.append(text[offset])
            offset += 1
            continue
        for encoded, plain in tokens:
            if text.startswith(encoded, offset):
                pieces.append(plain)
                offset += len(encoded)
                break
        else:
            raise _Unmerged("unsupported TeX command in variable text")
    return "".join(pieces)


def _group(text, offset):
    start = offset
    while offset < len(text):
        if text[offset] == "\\":
            for token in sorted(_ESCAPES.values(), key=len, reverse=True):
                if text.startswith(token, offset):
                    offset += len(token)
                    break
            else:
                raise _Unmerged("unsupported TeX command in link")
        elif text[offset] == "}":
            return _decode(text[start:offset]), offset + 1
        elif text[offset] == "{":
            raise _Unmerged("unsupported nested TeX group")
        else:
            offset += 1
    raise _Unmerged("incomplete TeX link")


def _wording(rendered):
    if not rendered.startswith("\\item ") or not rendered.endswith("\n"):
        raise _Unmerged("unsupported item structure")
    body = rendered[len("\\item ") : -1]
    first_link = body.find(" \\href{")
    if first_link < 0:
        return _decode(body), []
    text, links, offset = _decode(body[:first_link]), [], first_link
    while offset < len(body):
        if not body.startswith(" \\href{", offset):
            raise _Unmerged("unsupported text after link")
        url, offset = _group(body, offset + len(" \\href{"))
        if not body.startswith("{", offset):
            raise _Unmerged("missing TeX link label")
        label, offset = _group(body, offset + 1)
        links.append({"label": label, "url": url})
    return text, links


def _items(items, block, baseline, source, scope):
    if not block:
        return []
    beginning, ending = "\\begin{itemize}\n", "\\end{itemize}\n"
    if not block.startswith(beginning) or not block.endswith(ending):
        raise _Unmerged("unsupported item-list layout")
    body = block[len(beginning) : -len(ending)]
    starts = [match.start() for match in re.finditer(r"(?m)^\\item ", body)]
    if not starts or starts[0] != 0:
        raise _Unmerged("unsupported item-list contents")
    snippets = [
        body[first:last] for first, last in zip(starts, starts[1:] + [len(body)], strict=True)
    ]
    old = [baseline.tex[slice(*baseline.ranges[item["id"]])] for item in items]
    if snippets == old:
        return deepcopy(items)
    if len(old) != len(set(old)) or len(snippets) != len(set(snippets)):
        raise _Unmerged("ambiguous duplicate item identity")
    old_by_tex = dict(zip(old, items, strict=True))
    unmatched = [item for text, item in zip(old, items, strict=True) if text not in snippets]
    changed = [text for text in snippets if text not in old_by_tex]
    if unmatched and changed and len(unmatched) != len(changed):
        raise _Unmerged("ambiguous simultaneous item deletion and replacement")
    if len(unmatched) > 1 and changed:
        raise _Unmerged("multiple replacements have no unique item identity")
    replacements = dict(zip(changed, unmatched, strict=False))
    result = []
    for index, snippet in enumerate(snippets):
        if snippet in old_by_tex:
            result.append(deepcopy(old_by_tex[snippet]))
            continue
        text, links = _wording(snippet)
        item = deepcopy(replacements.get(snippet)) or {
            "id": "human-" + digest([scope, source, index, snippet]),
            "fact_refs": [],
            "inference_refs": [],
        }
        item.update(text=text, links=links, origin="human", protected=True, edit_source=source)
        result.append(item)
    return result


def _experiences(rows, block, baseline, source):
    if not block:
        return []
    headers = {}
    for row in rows:
        start, _ = baseline.ranges[row["id"]]
        first, _ = baseline.ranges[row["items"][0]["id"]]
        header = baseline.tex[start:first]
        # The item-list wrapper belongs to the list parser rather than the header.
        header = header.removesuffix("\\begin{itemize}\n")
        if header in headers:
            raise _Unmerged("ambiguous experience identity")
        headers[header] = row
    result, offset, seen = [], 0, set()
    while offset < len(block):
        matches = [
            (header, row) for header, row in headers.items() if block.startswith(header, offset)
        ]
        if len(matches) != 1:
            raise _Unmerged("unsupported experience heading or layout")
        header, row = matches[0]
        if row["id"] in seen:
            raise _Unmerged("duplicate experience identity")
        seen.add(row["id"])
        end = block.find("\\end{itemize}\n", offset + len(header))
        if end < 0:
            raise _Unmerged("incomplete experience item list")
        end += len("\\end{itemize}\n")
        child = deepcopy(row)
        child["items"] = _items(
            row["items"], block[offset + len(header) : end], baseline, source, row["id"]
        )
        result.append(child)
        offset = end
    return result


def _slots(template, edited):
    positions = sorted(
        (template.index(marker), key, marker) for key, marker in template_slots(template).items()
    )
    pattern, keys, offset = [], [], 0
    for position, key, marker in positions:
        capture = (
            r"((?:\\begin\{itemize\}\n.*?\\end\{itemize\}\n)?)"
            if key in {"summary", "skills"}
            else "(.*?)"
        )
        pattern.extend((re.escape(template[offset:position]), capture))
        keys.append(key)
        offset = position + len(marker)
    pattern.append(re.escape(template[offset:]))
    matched = re.fullmatch("".join(pattern), edited, re.DOTALL)
    if matched is None:
        raise _Unmerged("fixed template or cross-block layout changed")
    return dict(zip(keys, matched.groups(), strict=True))


def reconcile_content(
    parent_content, template_tex, edited_tex, edit_source, *, render_manifest=None
):
    """Map supported human edits only when exact fixed-template rendering agrees.

    ``render_manifest`` can bind trusted stored render metadata to this parent.
    Unmerged results retain the exact edited TeX and diff for caller persistence;
    they contain no adopted JSON, and must not trigger automatic regeneration.
    """
    parent = validate_content(parent_content).model_dump(mode="json")
    if (
        not isinstance(edited_tex, str)
        or not isinstance(edit_source, str)
        or not edit_source.strip()
    ):
        raise ValueError("human TeX and nonempty edit provenance are required")
    is_template = parent["schema_version"] == "resume-template-content/v1"
    baseline = render_resume(parent, template=template_tex if is_template else None)
    result = {
        "schema_version": "resume-content-reconciliation/v1",
        "base_content_revision": parent["revision"],
        "template_revision": baseline.template_revision,
        "renderer_revision": baseline.renderer_revision,
        "baseline_ranges": {key: list(value) for key, value in baseline.ranges.items()},
        "edited_tex_revision": digest(edited_tex),
        "edited_tex": edited_tex,
        "edit_source": edit_source,
        "diff": "".join(
            unified_diff(
                baseline.tex.splitlines(True),
                edited_tex.splitlines(True),
                fromfile="parent.tex",
                tofile="human.tex",
            )
        ),
    }
    try:
        if not is_template:
            raise _Unmerged(
                "historical complete-content format requires explicit template migration"
            )
        if render_manifest is not None:
            if not isinstance(render_manifest, dict):
                raise _Unmerged("stored render metadata is invalid")
            expected = {
                "schema_version": "resume-render-manifest/v1",
                "content_revision": baseline.content_revision,
                "template_revision": baseline.template_revision,
                "renderer_revision": baseline.renderer_revision,
                "tex_sha256": sha256(baseline.tex.encode()).hexdigest(),
                "item_ranges": result["baseline_ranges"],
            }
            if any(render_manifest.get(key) != value for key, value in expected.items()):
                raise _Unmerged("stored render metadata does not match parent rendering")
        if edited_tex == baseline.tex:
            return {**result, "status": "unchanged", "content": parent}
        slots = _slots(template_tex, edited_tex)
        child = deepcopy(parent)
        if "headline" in slots:
            block = slots["headline"]
            previous = parent.get("headline")
            original = baseline.tex[slice(*baseline.ranges[previous["id"]])] if previous else ""
            if block != original:
                if not block:
                    child.pop("headline", None)
                else:
                    if not block.endswith("\\par\n"):
                        raise _Unmerged("unsupported career headline layout")
                    text, links = _wording("\\item " + block[: -len("\\par\n")] + "\n")
                    headline = (
                        deepcopy(previous)
                        if previous
                        else {
                            "id": "human-" + digest(["headline", edit_source, block]),
                            "fact_refs": [],
                            "inference_refs": [],
                        }
                    )
                    headline.update(
                        text=text,
                        links=links,
                        origin="human",
                        protected=True,
                        edit_source=edit_source,
                    )
                    child["headline"] = headline
        for key in ("summary", "skills"):
            child[key] = _items(parent[key], slots[key], baseline, edit_source, key)
        child["experiences"] = _experiences(
            parent["experiences"], slots["experiences"], baseline, edit_source
        )
        child["revision"] = content_revision(child)
        validate_content(child)
        if render_resume(child, template=template_tex).tex != edited_tex:
            raise _Unmerged("human TeX is outside the renderer's exact literal language")
        return {**result, "status": "mapped", "content": child}
    except ValueError as error:
        return {**result, "status": "unmerged", "reason": str(error)}
