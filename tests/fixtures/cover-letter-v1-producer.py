"""Original v1 renderer and PDF producer retained only for compatibility tests.

The function bodies are copied verbatim from the original implementation. Shared
validation, literal escaping and source-storage primitives are unchanged helpers.
Do not modernize this producer when changing the current renderer.
"""

import hashlib
import re
from pathlib import Path

from career_evidence_graph._vendor import job_apply_store as helper
from career_evidence_graph.application_cover_letter import (
    BEGIN_BODY,
    _plain_literal,
    _read_letter_file,
    _template_parts,
    validate_letter,
)
from career_evidence_graph.application_resume_render import _text
from career_evidence_graph.career_portal_data import PortalDataError
from career_evidence_graph.validation.hashing import record_digest as digest

RENDERER_REVISION = "cover-letter-renderer/v1"


def _fixed_text(prefix, suffix):
    # The accepted article template places a literal greeting immediately before
    # the body and a literal closing after it. Reject unknown formatting explicitly.
    preceding = [
        line.strip()
        for line in prefix[: prefix.rfind(BEGIN_BODY)].splitlines()
        if line.strip() and not line.lstrip().startswith("%")
    ]
    if not preceding:
        raise ValueError("template greeting is missing")
    greeting = _plain_literal(preceding[-1])
    following = []
    for line in suffix.splitlines()[1:]:
        line = line.strip()
        if (
            not line
            or line.startswith("%")
            or re.fullmatch(
                r"\\vspace\*?\[[^]]+\]|\\vspace\*?\{[^}]+\}|"
                r"\\nopagebreak(?:\[[0-4]\])?|\\end\{document\}",
                line,
            )
        ):
            continue
        if line.endswith("\\\\"):
            line = line[:-2]
        following.append(_plain_literal(line))
    if not following:
        raise ValueError("template closing is missing")
    return greeting, "\n".join(following)


def render_cover_letter(content, template):
    """Fill only the body span and derive plain text from the same fixed template."""
    content = validate_letter(content)
    prefix, existing_body, suffix = _template_parts(template)
    if existing_body.strip():
        raise ValueError("letter template contains existing body content")
    greeting, closing = _fixed_text(prefix, suffix)
    pieces, ranges = [prefix], {}
    for row in content["paragraphs"]:
        pieces.append("% LETTER PARAGRAPH " + row["id"] + " BEGIN\n")
        first = sum(map(len, pieces))
        pieces.append(_text(row["text"]))
        ranges[row["id"]] = [first, sum(map(len, pieces))]
        pieces.append("\n% LETTER PARAGRAPH " + row["id"] + " END\n\n")
    pieces.append(suffix)
    body = "\n\n".join(row["text"] for row in content["paragraphs"])
    return {
        "tex": "".join(pieces),
        "text": greeting + "\n\n" + body + "\n\n" + closing,
        "text_prefix": greeting + "\n\n",
        "text_suffix": "\n\n" + closing,
        "content_revision": content["revision"],
        "template_revision": digest(template),
        "renderer_revision": RENDERER_REVISION,
        "ranges": ranges,
    }


def _pdf_delivery_result(directory, rendered, binding, raw, *, max_bytes, pdf_inspector):
    from .application_prism import refresh_source_snapshot
    from .application_resume import ApplicationResumeStore

    if not isinstance(raw, bytes) or refresh_source_snapshot(binding) != binding:
        raise ValueError("changed letter source or PDF type")
    source = directory / "project" / "main.tex"
    if source.read_bytes() != rendered["tex"].encode():
        raise ValueError("letter source does not render this content and template")
    ApplicationResumeStore._validate_export_pdf(raw, pdf_inspector)
    if not 1 <= len(raw) <= max_bytes:
        raise PortalDataError("letter_file_too_large", "求职信 PDF 超过页面限制，正文已保留。", 409)
    if pdf_inspector is not None:
        pages = pdf_inspector(raw)
    else:
        counts = [
            int(value) for value in re.findall(rb"/Type\s*/Pages\b[^>]*?/Count\s+(\d+)\b", raw)
        ]
        pages = max(counts) if counts else None
    if pages is None:
        raise PortalDataError(
            "letter_pdf_pages_unverified", "求职信 PDF 页数尚未核验，保留正文和文件。", 409
        )
    if pages != 1:
        raise PortalDataError(
            "letter_pdf_overflow", "求职信超过一页，请调整正文；不会裁切或缩小字号。", 409
        )
    return {
        **{
            key: rendered[key]
            for key in ("content_revision", "template_revision", "renderer_revision")
        },
        "file_path": str(directory / "letter.pdf"),
        "filename": "cover-letter.pdf",
        "sha256": hashlib.sha256(raw).hexdigest(),
        "tex_sha256": hashlib.sha256(rendered["tex"].encode()).hexdigest(),
        "tex_path": str(source),
        "page_count": pages,
        "prism_source_revision": binding["source_revision"],
    }


def _pdf_intent(directory, rendered):
    from .application_prism import source_snapshot

    if directory.is_symlink() or (directory / "project").is_symlink():
        raise ValueError("redirected letter project")
    intent = _read_letter_file(directory, "export-intent.json")
    expected = {
        key: rendered[key] for key in ("content_revision", "template_revision", "renderer_revision")
    }
    binding = source_snapshot(
        directory / "project", "main.tex", source_policy="generated-latex-project/v1"
    )
    if intent != expected | {"binding": binding}:
        raise ValueError("letter build intent differs from source or content")
    return binding


def read_cover_letter_pdf(directory, content, template, *, max_bytes=700000, pdf_inspector=None):
    """Reconstruct an exact completed local export without writes, builds or network."""
    directory = Path(directory)
    try:
        rendered = render_cover_letter(content, template)
        binding = _pdf_intent(directory, rendered)
        path = directory / "letter.pdf"
        if path.is_symlink() or path.stat().st_size > 700_000:
            raise ValueError("unsafe letter PDF")
        raw = path.read_bytes()
        built = _read_letter_file(directory, "build.json")
        if (
            built.get("source_revision") != binding["source_revision"]
            or built.get("pdf_sha256") != hashlib.sha256(raw).hexdigest()
            or built.get("build", {}).get("exit") != 0
        ):
            raise ValueError("letter local build does not bind this source and PDF")
        result = _pdf_delivery_result(
            directory, rendered, binding, raw, max_bytes=max_bytes, pdf_inspector=pdf_inspector
        )
        if (directory / "export.json").exists() and _read_letter_file(
            directory, "export.json"
        ) != result:
            raise ValueError("letter export receipt differs from build evidence")
        return result
    except (OSError, ValueError, KeyError, TypeError) as error:
        raise PortalDataError(
            "letter_export_needs_recheck", "求职信本地构建回执尚不能核验，保留原尝试。", 409
        ) from error


def reconcile_cover_letter_pdf(
    directory, content, template, *, client=None, max_bytes=700000, pdf_inspector=None
):
    """Recover only proven completed output; never request a compilation or model."""
    from .application_prism import PrismClient

    directory = Path(directory)
    try:
        result = read_cover_letter_pdf(
            directory, content, template, max_bytes=max_bytes, pdf_inspector=pdf_inspector
        )
    except PortalDataError as error:
        if error.code != "letter_export_needs_recheck":
            raise
        try:
            rendered = render_cover_letter(content, template)
            binding = _pdf_intent(directory, rendered)
            completed = (client or PrismClient()).read_compiled(binding)
            actual = completed["binding"]
            build = completed["build"]
            raw = completed["pdf"]
            if (
                actual.get("project_root") != binding["project_root"]
                or actual.get("main") != binding["main"]
                or actual.get("files") != binding["files"]
                or build.get("source_revision") != actual.get("source_revision")
                or build.get("pdf_sha256") != hashlib.sha256(raw).hexdigest()
                or build.get("status") != "complete"
                or build.get("exit") != 0
            ):
                raise ValueError("Prism readback differs from frozen letter build")
            result = _pdf_delivery_result(
                directory, rendered, binding, raw, max_bytes=max_bytes, pdf_inspector=pdf_inspector
            )
            (directory / "letter.pdf").write_bytes(raw)
            helper.atomic_write_json(
                directory / "build.json",
                {
                    "source_revision": binding["source_revision"],
                    "pdf_sha256": hashlib.sha256(raw).hexdigest(),
                    "build": build,
                },
            )
        except (OSError, ValueError, KeyError, TypeError) as failure:
            raise PortalDataError(
                "letter_export_needs_recheck", "求职信原构建结果仍未完整核验，不会重新编译。", 409
            ) from failure
    helper.atomic_write_json(directory / "export.json", result)
    return result


def export_cover_letter_pdf(
    directory, content, template, *, client=None, max_bytes=700000, pdf_inspector=None
):
    """Build only for a file destination, retaining separate source/build receipts."""
    from .application_prism import PrismClient, refresh_source_snapshot, source_snapshot

    rendered = render_cover_letter(content, template)
    directory = Path(directory)
    expected = {
        key: rendered[key] for key in ("content_revision", "template_revision", "renderer_revision")
    }
    if (directory / "export-intent.json").exists():
        return read_cover_letter_pdf(
            directory, content, template, max_bytes=max_bytes, pdf_inspector=pdf_inspector
        )
    directory.mkdir(parents=True, exist_ok=True)
    project = directory / "project"
    if project.exists():
        raise PortalDataError(
            "letter_export_needs_recheck", "求职信构建目录已有源文件，不能覆盖。", 409
        )
    project.mkdir()
    (project / "main.tex").write_bytes(rendered["tex"].encode())
    binding = source_snapshot(project, "main.tex", source_policy="generated-latex-project/v1")
    helper.atomic_write_json(directory / "export-intent.json", expected | {"binding": binding})
    stage = "compile"
    try:
        built = (client or PrismClient()).compile(binding)
        raw = built["pdf"]
        if (
            not isinstance(raw, bytes)
            or built.get("source_revision") != binding["source_revision"]
            or refresh_source_snapshot(binding) != binding
        ):
            raise ValueError("changed letter compile source")
        (directory / "letter.pdf").write_bytes(raw)
        helper.atomic_write_json(
            directory / "build.json",
            {
                **{key: value for key, value in built.items() if key != "pdf"},
                "pdf_sha256": hashlib.sha256(raw).hexdigest(),
            },
        )
        stage = "validation"
        result = _pdf_delivery_result(
            directory, rendered, binding, raw, max_bytes=max_bytes, pdf_inspector=pdf_inspector
        )
        stage = "publication"
        helper.atomic_write_json(directory / "export.json", result)
        return result
    except Exception as error:
        known = (
            stage == "validation"
            or isinstance(error, PortalDataError)
            and error.code
            in {
                "resume_export_failed",
                "prism_not_running",
                "prism_unavailable",
                "prism_identity_changed",
                "prism_sync_active",
                "prism_source_invalid",
                "prism_source_changed",
            }
        )
        helper.atomic_write_json(
            directory / "export-failure.json",
            expected
            | {
                "status": "failed" if known else "needs_recheck",
                "error_type": type(error).__name__,
                "code": getattr(error, "code", "letter_export_needs_recheck"),
            },
        )
        if isinstance(error, PortalDataError):
            raise
        raise PortalDataError(
            "letter_export_needs_recheck", "求职信构建结果尚未核验，正文已保留。", 409
        ) from error
