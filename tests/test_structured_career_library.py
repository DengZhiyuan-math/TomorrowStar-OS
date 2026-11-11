"""Structured career facts enter normal analysis without raw résumé leakage."""

import json
from copy import deepcopy

import pytest
from test_career_experiences import library as library

from career_evidence_graph.career_experiences import ExperienceStore
from career_evidence_graph.career_portal_data import PortalDataError


def content(candidate_id="alpha"):
    return {
        "schema_version": "experience-facts/v1",
        "revision": "input-revision",
        "experience_id": candidate_id,
        "candidate_id": candidate_id,
        "title": "Reviewed research",
        "role": "Researcher",
        "organization": "Synthetic Lab",
        "start": "2025",
        "end": "2026",
        "sources": [{"id": "note-1", "locator": "notes/project.txt"}],
        "facts": [
            {
                "id": "fact-1",
                "text": "Validated a team model.",
                "source_refs": ["note-1"],
                "responsibility": "user",
                "status": "completed",
                "scope": "validation only",
            }
        ],
    }


def save_content(root, **extra):
    return ExperienceStore(root).save(
        "alpha", title="Reviewed research", content=content(), **extra
    )


def test_metadata_edits_preserve_structured_facts_and_reject_body_overwrite(library):
    adapter, root, _, _, _ = library
    first = save_content(root, metadata={"import_status": "pending"})
    saved = adapter.save_experience(
        "alpha", metadata={"status": "completed"}, expected_revision=first["revision"]
    )
    assert saved["content"] == first["content"]
    assert saved["metadata"]["import_status"] == "pending"
    assert "body" not in saved
    with pytest.raises(PortalDataError):
        adapter.save_experience(
            "alpha", body="Unreviewed replacement", expected_revision=saved["revision"]
        )
    assert ExperienceStore(root).get("alpha") == saved


def test_structured_snapshot_supplies_each_fact_with_complete_version_binding(library):
    adapter, root, _, _, _ = library
    first = save_content(
        root,
        materials=[
            {
                "id": "generated",
                "source_name": "resume.tex",
                "text": "Untrusted résumé prose",
                "role": "generated",
            }
        ],
    )
    snapshot = adapter.snapshot_for_analysis({"documents": [], "items": []}, ["alpha"])
    assert [item["text"] for item in snapshot["items"]] == ["Validated a team model."]
    item = snapshot["items"][0]
    context = item["record_context"]
    assert context["fact_id"] == "fact-1"
    assert context["sources"] == [{"id": "note-1", "locator": "notes/project.txt"}]
    assert context["responsibility"] == "user"
    assert context["status"] == "completed"
    assert context["scope"] == "validation only"
    assert context["role"] == "Researcher"
    assert context["organization"] == "Synthetic Lab"
    assert context["start"] == "2025" and context["end"] == "2026"
    assert context["experience_revision"] == first["revision"]
    assert context["content_revision"] == first["content"]["revision"]
    assert context["experience_id"] == "alpha"
    assert snapshot["career_library"]["unavailable_sources"] == []
    changed = deepcopy(first["content"])
    changed["organization"] = "Corrected Lab"
    adapter.save_experience("alpha", content=changed, expected_revision=first["revision"])
    after = adapter.snapshot_for_analysis({"documents": [], "items": []}, ["alpha"])["items"][0]
    assert item["text"] == after["text"]
    assert item["source_revision"] != after["source_revision"]
    assert "Python models" not in json.dumps(snapshot)


def test_source_refresh_preserves_imported_json_and_reports_unconverted_materials(library):
    adapter, root, descriptor, rows, write = library
    first = save_content(
        root,
        origin="imported",
        metadata={"institution": "Saved institution", "manual_fields": ["institution"]},
    )
    rows[0]["title"] = "Renamed upstream"
    descriptor["catalog"] = write("catalog.json", {"records": rows})
    adapter.manifest.write_text(json.dumps(descriptor))
    result = adapter.sync_experiences(["alpha"])
    assert result["pending"] == ["alpha"]
    after = adapter.read_experience("alpha")
    assert after["content"] == first["content"]
    assert after["title"] == first["title"]
    assert after["metadata"]["institution"] == "Saved institution"
    assert after["materials"]
    assert all(material["role"] == "supplement" for material in after["materials"])
    snapshot = adapter.snapshot_for_analysis({"documents": [], "items": []}, ["alpha"])
    assert [item["text"] for item in snapshot["items"]] == ["Validated a team model."]
    assert any(
        item["status"] == "structured_import_pending"
        for item in snapshot["career_library"]["unavailable_sources"]
    )


def test_legacy_tex_is_retained_for_explicit_import_without_raw_model_input(library):
    adapter, root, _, _, _ = library
    ExperienceStore(root).save(
        "alpha",
        title="Research",
        body=r"\subsection{Research}\item Validated a model.",
        materials=[
            {
                "id": "plain.tex",
                "source_name": "plain.tex",
                "text": "Literal source facts remain valid despite file name.",
                "role": "supplement",
            },
            {
                "id": "markup",
                "source_name": "notes",
                "text": r"\textbf{Other raw prose}",
                "role": "supplement",
            },
        ],
    )
    snapshot = adapter.snapshot_for_analysis({"documents": [], "items": []}, ["alpha"])
    assert [item["text"] for item in snapshot["items"]] == [
        "Literal source facts remain valid despite file name."
    ]
    retained = snapshot["retained_materials"]
    assert any("Validated a model" in item["text"] for item in retained)
    assert any("Other raw prose" in item["text"] for item in retained)
    assert any(
        item["status"] == "legacy_tex_import_pending"
        for item in snapshot["career_library"]["unavailable_sources"]
    )


def test_explicit_import_preview_and_commit_keep_original_revision_and_materials(library):
    adapter, root, _, _, _ = library
    text = "Validated a team model."
    first = ExperienceStore(root).save("alpha", title="Original research", body=text)
    request = {
        "schema_version": "experience-import/v1",
        "expected_revision": first["revision"],
        "content": content(),
        "parts": [
            {
                "id": "part-1",
                "source_pointer": "/body",
                "start": 0,
                "end": len(text),
                "quote": text,
                "disposition": "fact",
                "fact_ids": ["fact-1"],
                "source_ref": "note-1",
                "reason": "Explicit literal source mapping.",
            }
        ],
    }
    preview = adapter.preview_experience_import("alpha", request)
    assert preview["ready"]
    assert adapter.read_experience("alpha") == first
    saved = adapter.import_experience("alpha", request)
    assert saved["content"]["facts"][0]["text"] == text
    assert saved["previous_revision"] == first["revision"]
    assert saved["migration"]["from_revision"] == first["revision"]
    assert "body" not in saved
    snapshot = adapter.snapshot_for_analysis({"documents": [], "items": []}, ["alpha"])
    assert snapshot["career_library"]["unavailable_sources"] == []
    assert [item["text"] for item in snapshot["items"]] == [text]


def test_trusted_library_does_not_promote_retained_resume_or_inherited_sources(library):
    adapter, root, descriptor, _, _ = library
    descriptor["application_policy"] = "trusted-library/v1"
    adapter.manifest.write_text(json.dumps(descriptor))
    save_content(root)
    base = {
        "documents": [],
        "items": [
            {
                "source_kind": "accepted_resume",
                "source_id": "old-resume",
                "text": r"\item Old human wording",
            },
            {"source_kind": "source", "source_id": "ordinary", "text": "Inherited input"},
        ],
    }
    before = deepcopy(base)
    snapshot = adapter.snapshot_for_analysis(base, ["alpha"])
    assert base == before
    assert "old-resume" not in {item["source_id"] for item in snapshot["items"]}
    assert snapshot["retained_materials"][0]["text"] == r"\item Old human wording"
    inherited = next(item for item in snapshot["items"] if item["source_id"] == "ordinary")
    assert "application_trusted" not in inherited
    assert snapshot["items"][-1]["application_trusted"]
    assert snapshot["items"][-1]["boundaries"] == "Status: completed; scope: validation only"


def test_imported_source_coverage_is_bound_to_literal_material_and_context(library):
    adapter, root, _, _, _ = library
    text = "Validated a team model."
    first = ExperienceStore(root).save(
        "alpha",
        title="Research",
        body=text,
        materials=[{"id": "notes", "source_name": "notes", "text": text, "role": "supplement"}],
    )
    request = {
        "schema_version": "experience-import/v1",
        "expected_revision": first["revision"],
        "content": content(),
        "parts": [
            {
                "id": "body",
                "source_pointer": "/body",
                "start": 0,
                "end": len(text),
                "quote": text,
                "disposition": "fact",
                "fact_ids": ["fact-1"],
                "source_ref": "note-1",
                "reason": "Literal evidence.",
            },
            {
                "id": "duplicate",
                "source_pointer": "/materials/0/text",
                "start": 0,
                "end": len(text),
                "quote": text,
                "disposition": "fact",
                "fact_ids": ["fact-1"],
                "source_ref": "note-1",
                "reason": "Explicit source mapping; preserve its distinct context.",
            },
        ],
    }
    saved = adapter.import_experience("alpha", request)
    snapshot = adapter.snapshot_for_analysis({"documents": [], "items": []}, ["alpha"])
    assert snapshot["career_library"]["unavailable_sources"] == []
    changed = [
        {**saved["materials"][0], "attribution": "Team responsibility; recheck attribution."}
    ]
    adapter.save_experience("alpha", materials=changed, expected_revision=saved["revision"])
    snapshot = adapter.snapshot_for_analysis({"documents": [], "items": []}, ["alpha"])
    assert any(
        item["status"] == "structured_import_pending"
        for item in snapshot["career_library"]["unavailable_sources"]
    )
    assert [item["text"] for item in snapshot["items"]] == [text]


def test_incomplete_import_and_stale_preview_never_replace_legacy_body(library):
    adapter, root, _, _, _ = library
    fact = "Validated a team model."
    first = ExperienceStore(root).save(
        "alpha", title="Original", body=fact + "\nOther source text must be retained."
    )
    request = {
        "schema_version": "experience-import/v1",
        "expected_revision": first["revision"],
        "content": content(),
        "parts": [
            {
                "id": "part",
                "source_pointer": "/body",
                "start": 0,
                "end": len(fact),
                "quote": fact,
                "disposition": "fact",
                "fact_ids": ["fact-1"],
                "source_ref": "note-1",
                "reason": "Partial source mapping only.",
            }
        ],
    }
    preview = adapter.preview_experience_import("alpha", request)
    assert not preview["ready"] and preview["unresolved"]
    with pytest.raises(PortalDataError) as failed:
        adapter.import_experience("alpha", request)
    assert failed.value.code == "experience-import-incomplete"
    assert adapter.read_experience("alpha") == first
    current = adapter.save_experience(
        "alpha", body="A later explicit human correction.", expected_revision=first["revision"]
    )
    with pytest.raises(PortalDataError) as failed:
        adapter.import_experience("alpha", request)
    assert failed.value.code == "revision-conflict"
    assert adapter.read_experience("alpha") == current


def test_normal_save_cannot_bypass_explicit_legacy_import_coverage(library):
    adapter, root, _, _, _ = library
    first = ExperienceStore(root).save("alpha", title="Original", body="Unmapped historical facts.")
    with pytest.raises(PortalDataError) as failed:
        adapter.save_experience("alpha", content=content(), expected_revision=first["revision"])
    assert failed.value.code == "experience-import-required"
    assert adapter.read_experience("alpha") == first


@pytest.mark.parametrize(
    "change",
    [
        {"metadata": {"status": "in_progress"}},
        {"metadata": {"import_status": "complete"}},
        {"materials": []},
    ],
)
def test_incidental_legacy_edits_keep_failed_source_import_pending(library, change):
    adapter, root, _, _, _ = library
    (root / "work.json").unlink()
    assert "alpha" in adapter.sync_experiences(["alpha"])["pending"]
    first = adapter.read_experience("alpha")
    saved = adapter.save_experience("alpha", expected_revision=first["revision"], **change)
    assert saved["metadata"]["import_status"] == "pending"
    snapshot = adapter.snapshot_for_analysis({"documents": [], "items": []}, ["alpha"])
    assert {"candidate_id": "alpha", "status": "import_pending"} in snapshot["career_library"][
        "unavailable_sources"
    ]


@pytest.mark.parametrize(
    "text",
    [
        r"\entry{Research}{2024--2026}{Validated team models}{No deployment}",
        r"\cvContribution{Validated team models}",
        r"\subsection{Research}",
    ],
)
def test_structural_legacy_tex_requires_explicit_import(library, text):
    adapter, root, _, _, _ = library
    ExperienceStore(root).save("alpha", title="Research", body=text)
    snapshot = adapter.snapshot_for_analysis({"documents": [], "items": []}, ["alpha"])
    assert snapshot["items"] == []
    assert snapshot["retained_materials"][0]["text"] == text
    assert any(
        item["status"] == "legacy_tex_import_pending"
        for item in snapshot["career_library"]["unavailable_sources"]
    )


@pytest.mark.parametrize(
    "text",
    [
        r"Read plain source.tex under C:\Users\Research\notes and preserve literal \n escapes.",
        r"Explained $\frac{x}{y}$, \(\mathbf{v}\), and unwrapped \sqrt{x} in a model.",
        r"Derived \begin{equation}x = \frac{a}{b}\end{equation} as a mathematical explanation.",
    ],
)
def test_plain_paths_escape_sequences_and_math_remain_legacy_facts(library, text):
    adapter, root, _, _, _ = library
    ExperienceStore(root).save("alpha", title="Research", body=text)
    snapshot = adapter.snapshot_for_analysis({"documents": [], "items": []}, ["alpha"])
    assert [item["text"] for item in snapshot["items"]] == [text]
    assert snapshot["career_library"]["unavailable_sources"] == []
