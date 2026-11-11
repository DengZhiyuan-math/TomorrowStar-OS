"""Retained education stays bound to its original credential and source lines."""

import json

import pytest
from test_application_resume import task_resume as task_resume
from test_application_source_reuse import write_retained_material
from test_full_latex_generation import full_latex as full_latex
from test_full_latex_generation import generate
from test_standalone_prism_review import FakePrism

from career_evidence_graph.application_resume import career_source_snapshot
from career_evidence_graph.application_worker import digest
from career_evidence_graph.career_portal_data import PortalDataError


def _retained_base(full_latex, source, profile, groups):
    store, _, _, analysis, _, project, _, inputs = full_latex
    write_retained_material(store.catalog.root, source, profile, groups)
    (store.catalog.root / "sources/profile.json").write_text(json.dumps(profile))
    sources = career_source_snapshot(store.catalog)
    # These cases exercise legacy generation's exact historical TeX templates.
    # The current analysis facts intentionally exclude those templates.
    retained = sources["retained_materials"]
    (project / "main.tex").write_text(source)
    data = list(full_latex)
    data[2] = sources
    analysis["source_snapshot_revision"] = inputs["sources_revision"] = sources["revision"]
    return data, retained


def test_identical_work_entry_cannot_reuse_the_education_group_review_exemption(full_latex):
    store, _, _, _, _, _, output, _ = full_latex
    credential = "\\entry{Example University}{2024--2028}{PhD in progress}{Expected July 2028}\n"
    source = (
        "\\documentclass[a4paper]{article}\n\\begin{document}\n"
        "\\section{Education}\n"
        + credential
        + "\\section{Experience}\n"
        + credential
        + "\\end{document}\n"
    )
    entry = {
        "degree": "PhD in progress",
        "institution": "Example University",
        "period": "2024--2028",
        "detail": "Expected July 2028",
    }
    profile = {"name": "Synthetic Person", "education": [entry]}
    groups = [
        {
            "title": "Education credential",
            "start_line": 4,
            "end_line": 4,
            "source_kind": "education",
            "context_source_ids": [],
            "education_profile_locator": "profile.education[0]",
            "education_profile_sha256": digest(entry),
        },
        {
            "title": "Experience",
            "start_line": 5,
            "end_line": 6,
            "source_kind": "accepted_resume",
            "context_source_ids": [],
            "education_profile_locator": None,
            "education_profile_sha256": None,
        },
    ]
    data, retained = _retained_base(full_latex, source, profile, groups)
    output["groups"] = [
        {
            "title": title,
            "start_line": line,
            "end_line": line,
            "source_ids": identifiers,
            "latex": text,
            "disposition": "include",
            "reason": "Existing text",
        }
        for line, title, text, identifiers in [
            (1, "Education heading", "\\section{Education}\n", []),
            (2, "Original credential", credential, [retained[0]["source_id"]]),
            (3, "Work heading", "\\section{Experience}\n", [retained[1]["source_id"]]),
            (4, "Duplicated work entry", credential, [retained[0]["source_id"]]),
        ]
    ]
    result = generate(data)

    fixed = [
        group for group in result["review_groups"] if group["content_policy"] == "fixed_education"
    ]
    assert [group["start_line"] for group in fixed] == [2]
    duplicate = next(group for group in result["verification_queue"] if group["start_line"] == 4)
    assert duplicate["content_policy"] == "education_verification_required"
    assert result["factual_review"] == "pending"
    assert not list(store.root.rglob("*.pdf"))


def _two_credential_base(full_latex, *, gap=False):
    entries = [
        {
            "degree": "BSc Mathematics",
            "institution": "Alpha University",
            "period": "2017--2021",
            "detail": "Numerical methods",
        },
        {
            "degree": "MSc Statistics",
            "institution": "Beta University",
            "period": "2021--2022",
            "detail": "Applied statistics",
        },
    ]
    first = (
        "\\section{Education}\n"
        "\\entry{Alpha University}{2017--2021}{BSc Mathematics}{Numerical methods}\n"
    )
    second = "\\entry{Beta University}{2021--2022}{MSc Statistics}{Applied statistics}\n"
    education = first + ("\n" if gap else "") + second
    work = "\\section{Experience}\nBuilt a Python service with the engineering team.\n"
    source = (
        "\\documentclass[a4paper]{article}\n\\begin{document}\n"
        + education
        + work
        + "\\end{document}\n"
    )
    groups = [
        {
            "title": "First credential",
            "start_line": 3,
            "end_line": 4,
            "source_kind": "education",
            "context_source_ids": [],
            "education_profile_locator": "profile.education[0]",
            "education_profile_sha256": digest(entries[0]),
        },
        {
            "title": "Second credential",
            "start_line": 5 + int(gap),
            "end_line": 5 + int(gap),
            "source_kind": "education",
            "context_source_ids": [],
            "education_profile_locator": "profile.education[1]",
            "education_profile_sha256": digest(entries[1]),
        },
        {
            "title": "Service",
            "start_line": 6 + int(gap),
            "end_line": 7 + int(gap),
            "source_kind": "accepted_resume",
            "context_source_ids": [],
            "education_profile_locator": None,
            "education_profile_sha256": None,
        },
    ]
    data, retained = _retained_base(
        full_latex, source, {"name": "Synthetic Person", "education": entries}, groups
    )
    data[6]["groups"] = [
        {
            "title": "Both credentials",
            "start_line": 1,
            "end_line": 3 + int(gap),
            "source_ids": [retained[1]["source_id"], retained[0]["source_id"]],
            "latex": education,
            "disposition": "include",
            "reason": "Reuse both documentary credentials unchanged",
        },
        {
            "title": "Service",
            "start_line": 4 + int(gap),
            "end_line": 5 + int(gap),
            "source_ids": [retained[2]["source_id"]],
            "latex": work,
            "disposition": "include",
            "reason": "Preserve the actual engineering team scope",
        },
    ]
    return data, education


@pytest.mark.parametrize("gap", [False, True], ids=["continuous", "unmapped-gap"])
def test_merged_education_requires_continuous_retained_source_coverage(full_latex, gap):
    data, education = _two_credential_base(full_latex, gap=gap)

    result = generate(data)

    fixed = [
        group for group in result["review_groups"] if group["content_policy"] == "fixed_education"
    ]
    if gap:
        assert fixed == []
        assert education not in result["latex_source"]
        assert result["verification_queue"][0]["title"] == "Both credentials"
        assert (
            result["verification_queue"][0]["content_policy"] == "education_verification_required"
        )
    else:
        assert len(fixed) == 1
        assert fixed[0]["rewritten"] == education
        assert len(fixed[0]["sources"]) == 2
        assert result["verification_queue"] == []
    assert result["factual_review"] == "pending"
    assert not list(data[0].root.rglob("*.pdf"))


@pytest.mark.parametrize("before,after", [("MSc Statistics", "PhD Statistics"), ("2022", "2023")])
def test_retained_education_editor_rejects_changed_credential_before_compilation(
    full_latex, before, after
):
    data, _ = _two_credential_base(full_latex)
    store, *_, inputs = data
    generated = generate(data)
    store.group_prism_client = FakePrism()
    draft = store.prepare_group_review(
        generated["id"], generated["draft_sha256"], task_inputs=inputs
    )
    group = next(
        group for group in draft["review_groups"] if group["content_policy"] == "fixed_education"
    )
    saved = {path: path.read_bytes() for path in store.root.rglob("*") if path.is_file()}

    with pytest.raises(PortalDataError) as error:
        store.edit_group_review(
            draft["id"],
            draft["draft_sha256"],
            task_inputs=inputs,
            payload={
                "group_id": group["id"],
                "title": group["title"],
                "latex": group["rewritten"].replace(before, after),
                "source_ids": [source["source_id"] for source in group["sources"]],
                "disposition": "include",
            },
        )

    assert error.value.code == "resume_fixed_education_changed"
    assert saved == {path: path.read_bytes() for path in store.root.rglob("*") if path.is_file()}
    assert store.group_prism_client.calls == []
    assert draft["factual_review"] == "pending"
    assert "material_acceptance" not in draft
    assert not list(store.root.rglob("*.pdf"))
