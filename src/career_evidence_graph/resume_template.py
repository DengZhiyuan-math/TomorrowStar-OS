"""Conservative, source-preserving layout adjustments for reusable resume templates."""

import base64
import hashlib
import json
import os
import re
import shutil
import tempfile
from pathlib import Path

from .application_prism import archive_sources, source_snapshot, validate_archive
from .career_portal_data import PortalDataError

ENGINE_SHA256 = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
_SECTION = re.compile(r"(?m)^[ \t]*\\(?:section|cvsection)\*?\{([^{}\n]+)\}[ \t]*(?:\n|$)")


def _argument(text: str, offset: int) -> tuple[str, int] | None:
    if offset >= len(text) or text[offset] != "{":
        return None
    start, depth, cursor = offset + 1, 1, offset + 1
    while cursor < len(text):
        if text[cursor] == "\\":
            cursor += 2
            continue
        if text[cursor] == "{":
            depth += 1
        elif text[cursor] == "}":
            depth -= 1
            if depth == 0:
                value = text[start:cursor]
                return (value, cursor + 1) if value.strip() else None
        cursor += 1
    return None


def _compact_body(body: str) -> str | None:
    # Comments and nested environments are deliberately outside this narrow grammar.
    if "%" in body:
        return None
    entries, cursor = [], 0
    while cursor < len(body):
        whitespace = re.match(r"\s*", body[cursor:])
        cursor += whitespace.end()
        if cursor == len(body):
            break
        if not body.startswith(r"\entry", cursor):
            return None
        cursor += len(r"\entry")
        fields = []
        for _ in range(2):
            argument = _argument(body, cursor)
            if argument is None:
                return None
            value, cursor = argument
            fields.append(value)
        separator = re.match(r"\s*\\textit", body[cursor:])
        if not separator:
            return None
        cursor += separator.end()
        argument = _argument(body, cursor)
        if argument is None:
            return None
        degree, cursor = argument
        suffix = re.match(r"\\par\s*\\nopagebreak\[4\]", body[cursor:])
        if not suffix:
            return None
        cursor += suffix.end()
        gap = re.match(r"\s*", body[cursor:])
        cursor += gap.end()
        detail = ""
        if body.startswith(r"\begin{itemize}", cursor):
            cursor += len(r"\begin{itemize}")
            end = body.find(r"\end{itemize}", cursor)
            if end < 0:
                return None
            raw = body[cursor:end].strip()
            if not raw.startswith(r"\item ") and not raw.startswith("\\item\n"):
                return None
            detail = raw[len(r"\item") :].strip()
            if not detail or re.search(r"\\(?:item|begin|end)\b", detail):
                return None
            cursor = end + len(r"\end{itemize}")
        if any(re.search(r"\\(?:begin|end|item|entry)\b", value) for value in (*fields, degree)):
            return None
        # Keep all documentary fields verbatim; only surrounding layout changes.
        paragraph = rf"\noindent\textit{{{degree}}}" + (r"\space " + detail if detail else "")
        entries.append(rf"\entry{{{fields[0]}}}{{{fields[1]}}}" + "\n" + paragraph + r"\par")
    if not entries:
        return None
    return (
        "\n\\begingroup\\fontsize{10}{12}\\selectfont\n" + "\n".join(entries) + "\n\\endgroup\n\n"
    )


def compact_education_latex(source: str) -> str:
    """Compact only wholly recognized education sections; leave other text untouched."""
    document = re.search(r"\\begin\{document\}", source)
    if document is None:
        return source
    document_end = source.find(r"\end{document}", document.end())
    if document_end < 0:
        return source
    sections = [
        section
        for section in _SECTION.finditer(source)
        if document.end() <= section.start() < document_end
    ]
    replacements = []
    for index, section in enumerate(sections):
        if section.group(1).strip().casefold() not in {"education", "academic background"}:
            continue
        end = sections[index + 1].start() if index + 1 < len(sections) else document_end
        compact = _compact_body(source[section.end() : end])
        if compact is not None:
            replacements.append((section.end(), end, compact))
    for start, end, replacement in reversed(replacements):
        source = source[:start] + replacement + source[end:]
    return source


def materialize_resume_template(binding: dict, destination_root: Path) -> dict:
    """Create an immutable derived template from validated bytes, never the live source."""
    archive = archive_sources(binding)
    original = validate_archive(archive, binding)
    compact = compact_education_latex(original.decode("utf-8")).encode("utf-8")
    if compact == original:
        return binding
    root = Path(destination_root)
    if not root.is_absolute() or any(path.is_symlink() for path in (root, *root.parents)):
        raise PortalDataError("resume_template_invalid", "模板副本目录不能重定向。", 409)
    root = root.resolve()
    if root.is_relative_to(Path(binding["project_root"])):
        raise PortalDataError("resume_template_invalid", "模板副本不能写入原项目。", 409)
    key = hashlib.sha256((binding["source_revision"] + ENGINE_SHA256).encode()).hexdigest()
    target = root / key
    files = {
        name: base64.b64decode(value, validate=True) for name, value in json.loads(archive).items()
    }
    files[binding["main"]] = compact
    expected = {name: hashlib.sha256(raw).hexdigest() for name, raw in files.items()}
    policy = binding.get("source_policy")

    def checked_snapshot():
        result = source_snapshot(target, binding["main"], source_policy=policy)
        if result["files"] != expected:
            raise PortalDataError("resume_template_changed", "已有模板副本已修改，不能覆盖。", 409)
        return result

    if os.path.lexists(target):
        return checked_snapshot()
    root.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=".resume-template-", dir=root))
    try:
        for name, raw in files.items():
            path = temporary / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(raw)
        source_snapshot(temporary, binding["main"], source_policy=policy)
        try:
            temporary.rename(target)
        except OSError:
            if not os.path.lexists(target):
                raise
        return checked_snapshot()
    finally:
        if temporary.exists():
            shutil.rmtree(temporary)
