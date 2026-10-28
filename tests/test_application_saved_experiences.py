"""Application facts remain usable without reopening a deferred research assessment."""

import json

import pytest
from test_canonical_career_sources import canonical as canonical

from career_evidence_graph.career_experiences import ExperienceStore


@pytest.mark.parametrize(
    ("record_class", "origin", "available"),
    [
        ("research-deferred", "user", True),
        ("research-deferred", "imported", False),
        (None, "user", True),
    ],
)
def test_explicit_saved_facts_are_available_without_changing_research_decision(
    canonical, record_class, origin, available
):
    library, root, _, base, write, manifest, descriptor = canonical
    deferred = {
        "candidate_id": "retained-research",
        "title": "Incomplete estimator study",
        "record_class": "research-deferred",
        "decision": {"outcome": "deferred", "reason": "Do not reopen mastery assessment."},
        "source_links": [],
    }
    catalog = json.loads((root / "catalog.json").read_text())
    if record_class is not None:
        deferred["record_class"] = record_class
        catalog["records"].append(deferred)
    descriptor["catalog"] = write("catalog.json", catalog)
    manifest.write_text(json.dumps(descriptor))
    original = (root / "catalog.json").read_bytes()
    assert "retained-research" not in {r["candidate_id"] for r in library.index()["records"]}
    ExperienceStore(root).save(
        "retained-research",
        title="Incomplete estimator study",
        content={
            "schema_version": "experience-facts/v1",
            "revision": "computed-by-store",
            "experience_id": "retained-research",
            "candidate_id": "retained-research",
            "title": "Incomplete estimator study",
            "sources": [{"id": "accepted-wording", "locator": "retained-resume:4"}],
            "facts": [
                {
                    "id": "negative-experiment",
                    "text": "The fixed estimator comparison retained a negative result.",
                    "source_refs": ["accepted-wording"],
                    "responsibility": "user",
                    "status": "completed",
                    "scope": "The project remains incomplete; no benchmark success claim.",
                }
            ],
        },
        origin=origin,
    )
    if not available:
        assert "retained-research" not in {r["candidate_id"] for r in library.index()["records"]}
        assert (root / "catalog.json").read_bytes() == original
        return
    assert "retained-research" in {r["candidate_id"] for r in library.index()["records"]}
    saved_row = next(
        r for r in library.index()["records"] if r["candidate_id"] == "retained-research"
    )
    assert saved_row["has_bound_evidence"] is True
    assert saved_row["record_class"] == (record_class or "application-saved-experience")
    loaded = library.snapshot_for_analysis(base, ["retained-research"])
    assert [r["text"] for r in loaded["items"]] == [
        "The fixed estimator comparison retained a negative result."
    ]
    assert (
        library.read_experience("retained-research")["content"]["candidate_id"]
        == "retained-research"
    )
    assert (root / "catalog.json").read_bytes() == original


def test_directory_origin_cannot_promote_deferred_import_to_application_fact(canonical):
    library, root, _, base, write, manifest, descriptor = canonical
    catalog = json.loads((root / "catalog.json").read_text())
    catalog["records"].append(
        {
            "candidate_id": "deferred-import",
            "title": "Deferred source",
            "record_class": "research-deferred",
            "source_links": [],
        }
    )
    descriptor["catalog"] = write("catalog.json", catalog)
    manifest.write_text(json.dumps(descriptor))
    ExperienceStore(root).save(
        "deferred-import",
        title="Deferred source",
        body="Only an imported source.",
        origin="imported",
    )
    assert "deferred-import" not in {r["candidate_id"] for r in library.index()["records"]}
    directory = root / ".tomorrowstar-experiences/directory.json"
    rows = json.loads(directory.read_text())
    rows["deferred-import"]["origin"] = "user"
    directory.write_text(json.dumps(rows))
    assert ExperienceStore(root).get("deferred-import")["origin"] == "imported"
    loaded = library.snapshot_for_analysis(base, ["deferred-import"])
    assert loaded["items"] == []
    assert loaded["career_library"]["unavailable_sources"]
    from career_evidence_graph.career_portal_data import PortalDataError

    with pytest.raises(PortalDataError):
        library.read_experience("deferred-import")
