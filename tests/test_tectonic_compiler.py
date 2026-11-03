"""Automatic materials compile with tectonic directly, without a Prism page."""

import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from test_cover_letter_content import TEMPLATE, ready

from career_evidence_graph import application_prism
from career_evidence_graph.application_cover_letter import (
    cover_letter_pdf_inspector,
    edit_cover_letter,
    export_cover_letter_pdf,
    read_cover_letter_pdf,
)
from career_evidence_graph.application_pdf import NativePDFInspector
from career_evidence_graph.application_prism import source_snapshot
from career_evidence_graph.application_resume_versions import (
    TectonicCompiler,
    _binding,
    _successful_build,
    tectonic_executable,
)

pytestmark = pytest.mark.skipif(tectonic_executable() is None, reason="tectonic not installed")

PREAMBLE = "\\documentclass{article}\n\\usepackage[T1]{fontenc}\n\\usepackage{mathptmx}\n"


def compiled(tmp_path, body):
    root = tmp_path.resolve() / "project"
    root.mkdir()
    (root / "main.tex").write_text(PREAMBLE + "\\begin{document}\n" + body + "\n\\end{document}\n")
    binding = _binding({"project_root": str(root), "main": "main.tex"})
    return binding, TectonicCompiler().read_compiled(binding), root


def test_a_clean_source_compiles_without_writing_into_the_project(tmp_path):
    binding, result, root = compiled(tmp_path, "Plain text.")
    # Installed MC-11: the Prism project closed with its last page, so the
    # automatic flow could not read a compiled PDF.
    assert result["pdf"].startswith(b"%PDF")
    assert _successful_build(result["build"], result["binding"], result["pdf"])
    assert result["binding"] == binding
    assert [path.name for path in root.iterdir()] == ["main.tex"]


def test_a_glyph_the_font_lacks_refuses_the_build(tmp_path):
    _, result, _ = compiled(tmp_path, "\u03c0 model")
    assert not _successful_build(result["build"], result["binding"], result["pdf"])


def test_compile_matches_the_prism_compile_contract(tmp_path):
    root = tmp_path.resolve() / "project"
    root.mkdir()
    (root / "main.tex").write_text(PREAMBLE + "\\begin{document}\nPlain.\n\\end{document}\n")
    binding = source_snapshot(root, "main.tex", source_policy="generated-latex-project/v1")
    built = TectonicCompiler().compile(binding)
    assert set(built) == {"pdf", "source_revision", "builder", "pdf_sha256", "build"}
    assert built["pdf"].startswith(b"%PDF")
    assert built["source_revision"] == binding["source_revision"]
    assert built["builder"] == "tectonic"
    assert built["pdf_sha256"] == hashlib.sha256(built["pdf"]).hexdigest()
    assert built["build"] | {"diagnostics": []} == {
        "main": "main.tex",
        "exit": 0,
        "engine": "xetex",
        "builder": "tectonic",
        "pdf_updated": True,
        "diagnostics": [],
    }
    assert [path.name for path in root.iterdir()] == ["main.tex"]


def test_a_cover_letter_compiles_with_tectonic_by_default(tmp_path, monkeypatch):
    """2026-11-03: the letter LaTeX rendered, but its build reached for Prism on 8790."""
    monkeypatch.setattr(
        application_prism, "PrismClient", lambda *a, **kw: pytest.fail("No Prism by default")
    )
    content = ready(tmp_path)["content"]
    directory = tmp_path / "pdf"
    exported = export_cover_letter_pdf(directory, content, TEMPLATE, pdf_inspector=lambda _: 1)
    raw = Path(exported["file_path"]).read_bytes()
    assert raw.startswith(b"%PDF") and exported["sha256"] == hashlib.sha256(raw).hexdigest()
    assert read_cover_letter_pdf(directory, content, TEMPLATE, pdf_inspector=lambda _: 1) == (
        exported
    )


def test_a_cover_letter_with_symbols_compiles_under_8bit_fonts(tmp_path):
    content = ready(tmp_path)["content"]
    content = edit_cover_letter(
        content, "Trained π₀ models; CO₂ — x² → done.", expected_revision=content["revision"]
    )
    template = TEMPLATE.replace(
        "\\begin{document}", "\\usepackage[T1]{fontenc}\n\\begin{document}", 1
    )
    directory = tmp_path / "pdf"
    exported = export_cover_letter_pdf(directory, content, template, pdf_inspector=lambda _: 1)
    assert Path(exported["file_path"]).read_bytes().startswith(b"%PDF")
    build = json.loads((directory / "build.json").read_text())["build"]
    assert not [row for row in build["diagnostics"] if "glyph" in row["message"]]
    assert read_cover_letter_pdf(directory, content, template, pdf_inspector=lambda _: 1) == (
        exported
    )


@pytest.fixture(scope="module")
def native_pdf_inspector(tmp_path_factory):
    compiler = shutil.which("swiftc")
    if sys.platform != "darwin" or not compiler:
        pytest.skip("requires macOS Swift")
    binary = tmp_path_factory.mktemp("pdf-inspect") / "pdf-inspect"
    source = Path(__file__).parents[1] / "macos/pdf_inspect.swift"
    subprocess.run([compiler, "-O", str(source), "-o", str(binary)], check=True)
    return NativePDFInspector(binary)


def test_a_tectonic_pdf_1_5_letter_reads_back_with_the_resume_inspector(
    tmp_path, native_pdf_inspector
):
    """2026-11-03: a compressed-xref PDF 1.5 letter failed the regex as resume_pdf_invalid."""
    content = ready(tmp_path)["content"]
    directory = tmp_path / "pdf"
    store = SimpleNamespace(pdf_inspector=native_pdf_inspector)
    inspector = cover_letter_pdf_inspector(store)
    exported = export_cover_letter_pdf(directory, content, TEMPLATE, pdf_inspector=inspector)
    raw = Path(exported["file_path"]).read_bytes()
    assert raw.startswith(b"%PDF-1.5") and b"/Type/XRef" in raw
    assert native_pdf_inspector(raw) == 1
    assert read_cover_letter_pdf(directory, content, TEMPLATE, pdf_inspector=inspector) == exported
