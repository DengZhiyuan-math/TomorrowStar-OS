"""A contact change that the fixed template already shows needs no template update."""

from career_evidence_graph._vendor import job_apply_store as helper
from career_evidence_graph.application_information import (
    material_information_library,
    put_information_answer,
    read_information_library,
)
from career_evidence_graph.application_resume import ApplicationResumeStore

LATEX = r"""\documentclass{article}
\usepackage{titlesec}
\titleformat{\section}{}{}{0pt}{}
\begin{document}
{\bfseries Ada Example}\\
\href{mailto:ada@example.org}{ada@example.org} | \href{https://github.com/ada-example}{GitHub}
\section{Projects}
Pull request https://github.com/other/repo/pull/12345678 and arXiv:2601.21954.
\end{document}
"""


def check(tmp_path, latex, changed=("information_library_revision",)):
    store = helper.Store(tmp_path / "library")
    for question, value in (
        ("Full name", "Ada Example"),
        ("Email address", "ada@example.org"),
        ("Phone number", "+41 79 000 00 00"),
        ("GitHub profile URL", "https://github.com/ada-example"),
    ):
        put_information_answer(
            store,
            {"question": question, "scope": {}, "value": value, "state": "confirmed"},
            source="test",
        )
    application = {"id": "a" * 24, "company": "Example", "location": "Zurich, Switzerland"}
    library = material_information_library(application, read_information_library(store.root))
    old = {"jd_revision": "same"} | {key: "old" for key in changed}
    new = {"jd_revision": "same"} | {key: "new" for key in changed}
    return ApplicationResumeStore._template_shows_contacts(
        {"latex_source": latex}, old, new, application, library
    )


def test_matching_header_needs_no_update_and_ignores_body_links(tmp_path):
    # The header shows no phone; body numbers and links are not contacts.
    assert check(tmp_path, LATEX)


def test_a_different_header_value_or_other_input_still_requires_update(tmp_path):
    assert not check(tmp_path / "a", LATEX.replace("ada@example.org", "eve@example.org"))
    assert not check(tmp_path / "b", LATEX, changed=("information_library_revision", "jd_revision"))
