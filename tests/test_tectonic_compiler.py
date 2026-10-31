"""Automatic materials compile with tectonic directly, without a Prism page."""

import shutil

import pytest

from career_evidence_graph.application_resume_versions import (
    TectonicCompiler,
    _binding,
    _successful_build,
)

pytestmark = pytest.mark.skipif(shutil.which("tectonic") is None, reason="tectonic not installed")

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
