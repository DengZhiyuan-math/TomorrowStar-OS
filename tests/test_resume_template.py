"""Synthetic layout fixtures preserve facts and the original source project."""

import json
from pathlib import Path

import pytest

from career_evidence_graph.application_prism import source_snapshot
from career_evidence_graph.career_portal_data import PortalDataError
from career_evidence_graph.resume_template import (
    compact_education_latex,
    materialize_resume_template,
)

PREFIX = r"""\documentclass[10pt]{article}
\newcommand{\entry}[2]{\textbf{#1}\hfill #2\par}
\begin{document}
Synthetic Person
"""
EDUCATION = r"""\section*{Education}
\entry{Synthetic University}{2025--Present}
\textit{MSc in Finance (in progress)}\par\nopagebreak[4]
\begin{itemize}
\item Scholarship: Synthetic Award; Supervisor: Prof. Example; thesis on risk \& returns.
\end{itemize}
\entry{Example Institute}{2021--2025}
\textit{BSc in Mathematics}\par\nopagebreak[4]
"""
SUFFIX = r"""\section*{Experience}
\entry{Synthetic Research}{2025}
\begin{itemize}\item Preserved body detail.\end{itemize}
\end{document}
"""


def test_only_education_layout_changes_and_all_fields_remain():
    source = PREFIX + EDUCATION + SUFFIX
    compact = compact_education_latex(source)
    assert compact.startswith(PREFIX)
    assert compact.endswith(SUFFIX)
    education = compact[len(PREFIX) : -len(SUFFIX)]
    for text in (
        "Synthetic University",
        "2025--Present",
        "MSc in Finance (in progress)",
        "Example Institute",
        "2021--2025",
        "BSc in Mathematics",
        r"Scholarship: Synthetic Award; Supervisor: Prof. Example; thesis on risk \& returns.",
    ):
        assert text in education
    assert r"\fontsize{10}{12}\selectfont" in education
    assert r"\vspace" not in education
    assert r"\item" not in education
    assert r"\entry{Synthetic University}{2025--Present}" in education
    assert r"\entry{Example Institute}{2021--2025}" in education
    assert compact_education_latex(compact) == compact


@pytest.mark.parametrize("heading", [r"\section{Academic Background}", r"\cvsection{Education}"])
def test_supported_section_headings(heading):
    source = PREFIX + EDUCATION.replace(r"\section*{Education}", heading) + SUFFIX
    assert compact_education_latex(source) != source


@pytest.mark.parametrize(
    "education",
    [
        EDUCATION.replace(r"\item Scholarship", r"\item Other\item Scholarship"),
        EDUCATION.replace("Scholarship:", r"\begin{quote}Scholarship:\end{quote}"),
        EDUCATION.replace("Scholarship:", "% comment\nScholarship:"),
        EDUCATION + "Unrecognized free-form information.\n",
        EDUCATION.replace(r"\textit{BSc in Mathematics}", r"\textbf{BSc in Mathematics}"),
        EDUCATION.replace(r"\begin{itemize}", r"\begin{itemize}[leftmargin=*]"),
        EDUCATION.replace(r"\item Scholarship", r"\item[Label] Scholarship"),
        EDUCATION.replace(r"\entry{Example Institute}", r"\entry{Example {Institute}"),
    ],
)
def test_ambiguous_sections_stay_byte_for_byte_unchanged(education):
    source = PREFIX + education + SUFFIX
    assert compact_education_latex(source) == source


def test_final_education_section_preserves_document_terminator():
    source = PREFIX + EDUCATION + "\\end{document}\n"
    compact = compact_education_latex(source)
    assert compact != source
    assert compact.endswith("\\end{document}\n")


def project(tmp_path, *, policy=None):
    root = tmp_path / "source"
    root.mkdir()
    (root / "main.tex").write_text(PREFIX + EDUCATION + SUFFIX)
    (root / "styles").mkdir()
    (root / "styles" / "resume.sty").write_bytes(b"% synthetic support\n")
    (root / "notes.txt").write_bytes(b"Synthetic supporting notes\n")
    return source_snapshot(root, "main.tex", source_policy=policy)


def test_materialize_copies_archive_and_never_changes_source(tmp_path):
    binding = project(tmp_path)
    root = Path(binding["project_root"])
    original = {name: (root / name).read_bytes() for name in binding["files"]}
    result = materialize_resume_template(binding, tmp_path / "templates")
    target = Path(result["project_root"])
    assert target != root
    assert {name: (root / name).read_bytes() for name in binding["files"]} == original
    assert (target / "main.tex").read_text() == compact_education_latex(
        original["main.tex"].decode()
    )
    for name in ("styles/resume.sty", "notes.txt"):
        assert (target / name).read_bytes() == original[name]
    assert materialize_resume_template(binding, tmp_path / "templates") == result


def test_materialize_preserves_explicit_source_policy(tmp_path):
    binding = project(tmp_path, policy="generated-latex-project/v1")
    (tmp_path / ".git").mkdir()
    result = materialize_resume_template(binding, tmp_path / "templates")
    assert result["source_policy"] == binding["source_policy"]


def test_unknown_layout_returns_original_binding_without_creating_directories(tmp_path):
    binding = project(tmp_path)
    root = Path(binding["project_root"])
    (root / "main.tex").write_text(PREFIX + SUFFIX)
    binding = source_snapshot(root, "main.tex")
    destination = tmp_path / "templates"
    assert materialize_resume_template(binding, destination) is binding
    assert not destination.exists()


def test_changed_source_creates_separate_copy(tmp_path):
    binding = project(tmp_path)
    first = materialize_resume_template(binding, tmp_path / "templates")
    root = Path(binding["project_root"])
    (root / "notes.txt").write_text("Updated supporting note")
    new_binding = source_snapshot(root, "main.tex")
    second = materialize_resume_template(new_binding, tmp_path / "templates")
    assert first["project_root"] != second["project_root"]
    assert (
        Path(first["project_root"]) / "notes.txt"
    ).read_bytes() == b"Synthetic supporting notes\n"


def test_modified_existing_copy_is_rejected_without_overwrite(tmp_path):
    binding = project(tmp_path)
    first = materialize_resume_template(binding, tmp_path / "templates")
    main = Path(first["project_root"]) / "main.tex"
    main.write_text("User accepted edits")
    with pytest.raises(PortalDataError, match="已有模板副本已修改"):
        materialize_resume_template(binding, tmp_path / "templates")
    assert main.read_text() == "User accepted edits"


def test_stale_source_binding_is_rejected(tmp_path):
    binding = project(tmp_path)
    (Path(binding["project_root"]) / "notes.txt").write_text("Source changed")
    with pytest.raises(PortalDataError):
        materialize_resume_template(binding, tmp_path / "templates")


def test_destination_inside_original_source_is_rejected(tmp_path):
    binding = project(tmp_path)
    with pytest.raises(PortalDataError):
        materialize_resume_template(binding, Path(binding["project_root"]) / "templates")


def test_preamble_and_post_document_education_examples_stay_untouched():
    source = EDUCATION + PREFIX + EDUCATION + SUFFIX + EDUCATION
    compact = compact_education_latex(source)
    assert compact.startswith(EDUCATION + PREFIX)
    assert compact.endswith(SUFFIX + EDUCATION)


def test_incomplete_document_is_unchanged():
    source = PREFIX + EDUCATION
    assert compact_education_latex(source) == source


def test_destination_alias_inside_original_source_is_rejected(tmp_path):
    binding = project(tmp_path)
    destination = tmp_path / "unused" / ".." / "source" / "templates"
    with pytest.raises(PortalDataError):
        materialize_resume_template(binding, destination)
    assert not (Path(binding["project_root"]) / "templates").exists()


def test_compact_entries_pass_existing_multi_credential_validation():
    from career_evidence_graph.application_full_latex import _education_matches

    sources = [
        {"source_kind": "education", "text": json.dumps(record)}
        for record in (
            {
                "institution": "Synthetic University",
                "period": "2025--Present",
                "degree": "MSc in Finance (in progress)",
                "detail": (
                    "Scholarship: Synthetic Award; Supervisor: Prof. Example; "
                    "thesis on risk & returns."
                ),
            },
            {
                "institution": "Example Institute",
                "period": "2021--2025",
                "degree": "BSc in Mathematics",
                "detail": "",
            },
        )
    ]
    source = PREFIX + EDUCATION + SUFFIX
    compact = compact_education_latex(source)
    education = compact[len(PREFIX) : -len(SUFFIX)]
    assert _education_matches(education, sources)
    swapped = education.replace("BSc in Mathematics", "MSc in Finance (in progress)")
    assert not _education_matches(swapped, sources)
