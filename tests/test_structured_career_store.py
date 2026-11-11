"""Structured experience storage preserves facts, provenance and old revisions."""

import hashlib
import json
from copy import deepcopy

import pytest

from career_evidence_graph.career_experiences import ExperienceStore
from career_evidence_graph.career_portal_data import PortalDataError


def facts(**changes):
    value = {
        "schema_version": "experience-facts/v1",
        "revision": "caller-label-is-not-a-content-version",
        "experience_id": "experience-alpha",
        "candidate_id": "alpha",
        "title": "Network research",
        "role": "Research assistant",
        "organization": "Synthetic institute",
        "sources": [{"id": "source-1", "locator": "record:/source-1"}],
        "facts": [
            {
                "id": "fact-1",
                "text": "Modelled sparse connectivity.",
                "source_refs": ["source-1"],
                "responsibility": "team",
                "status": "planned",
                "scope": "Neural reconstruction",
            }
        ],
    }
    value.update(changes)
    return value


def test_structured_save_uses_only_validated_content_and_computed_revision(tmp_path):
    store = ExperienceStore(tmp_path)
    supplied = facts()
    saved = store.save("alpha", title=supplied["title"], content=supplied)
    assert supplied["revision"] == "caller-label-is-not-a-content-version"
    assert saved["schema_version"] == "experience-record/v2"
    assert "body" not in saved
    canonical = {key: value for key, value in saved["content"].items() if key != "revision"}
    raw = json.dumps(canonical, ensure_ascii=False, sort_keys=True, allow_nan=False).encode()
    assert saved["content"]["revision"] == hashlib.sha256(raw).hexdigest()
    assert store.get("alpha") == saved
    row = store.directory()["alpha"]
    assert row["content_schema"] == "experience-facts/v1"
    assert "facts" not in row and "body" not in row and "content" not in row
    assert {"research", "assistant", "institute", "sparse", "neural", "planned"} <= set(
        row["retrieval_terms"]
    )


@pytest.mark.parametrize(
    "changes",
    [
        {"candidate_id": "other"},
        {"title": "other"},
        {"extra": "not accepted"},
        {"facts": [{"id": "bad"}]},
    ],
)
def test_invalid_content_never_publishes_a_record(tmp_path, changes):
    store = ExperienceStore(tmp_path)
    with pytest.raises(PortalDataError):
        store.save("alpha", title="Network research", content=facts(**changes))
    assert store.directory() == {}


@pytest.mark.parametrize("arguments", [{}, {"body": "old", "content": facts()}])
def test_requires_exactly_one_fact_representation(tmp_path, arguments):
    with pytest.raises(PortalDataError):
        ExperienceStore(tmp_path).save("alpha", title="Network research", **arguments)


def test_structured_revisions_keep_history_and_reject_legacy_downgrade(tmp_path):
    store = ExperienceStore(tmp_path)
    legacy = store.save("alpha", title="Network research", body="Original wording.")
    legacy_path = tmp_path / store.directory()["alpha"]["detail_entry"]
    report = {"source_revision": legacy["revision"], "unrepresented": []}
    structured = store.save(
        "alpha",
        title="Network research",
        content=facts(),
        expected_revision=legacy["revision"],
        migration=report,
        metadata={"manual_fields": ["title"], "aliases": ["Old name"]},
    )
    assert json.loads(legacy_path.read_text()) == legacy
    assert structured["previous_revision"] == legacy["revision"]
    assert structured["migration"] == report
    assert store.directory()["alpha"]["manual_fields"] == ["title"]
    assert "migration" not in store.directory()["alpha"]
    with pytest.raises(PortalDataError):
        store.save(
            "alpha",
            title="Network research",
            body="Late legacy update.",
            expected_revision=structured["revision"],
        )
    assert store.get("alpha") == structured
    with pytest.raises(PortalDataError) as error:
        store.save(
            "alpha", title="Network research", content=facts(), expected_revision=legacy["revision"]
        )
    assert error.value.code == "revision-conflict"


def test_structured_index_preserves_sources_and_excludes_generated_materials(tmp_path):
    materials = [
        {
            "id": role,
            "source_name": role,
            "text": keyword,
            "role": role,
            "locator": "record:/original",
            "attribution": "team",
        }
        for role, keyword in [
            ("supplement", "Numerical diagnostics"),
            ("generated", "phantom"),
            ("history", "obsolete"),
        ]
    ]
    saved = ExperienceStore(tmp_path).save(
        "alpha",
        title="Network research",
        content=facts(),
        materials=materials,
        migration={"notes": "migrationonlykeyword"},
    )
    row = ExperienceStore(tmp_path).directory()["alpha"]
    assert saved["materials"] == materials
    assert "diagnostics" in row["retrieval_terms"]
    assert not {"phantom", "obsolete", "migrationonlykeyword"} & set(row["retrieval_terms"])


def test_failed_structured_index_is_visible_and_saved_content_can_be_read(tmp_path):
    def fail(_):
        raise ValueError("synthetic indexing failure")

    store = ExperienceStore(tmp_path, derive=fail)
    saved = store.save("alpha", title="Network research", content=facts())
    assert store.directory()["alpha"]["index_status"] == "pending"
    assert store.get("alpha") == saved


def test_read_rejects_invalid_internal_content_even_with_valid_outer_digest(tmp_path):
    store = ExperienceStore(tmp_path)
    saved = store.save("alpha", title="Network research", content=facts())
    row = store.directory()["alpha"]
    payload = deepcopy(saved)
    payload["content"]["facts"][0]["text"] = "Changed after publication."
    payload.pop("revision")
    payload["revision"] = hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, allow_nan=False).encode()
    ).hexdigest()
    path = tmp_path / row["detail_entry"]
    new_path = path.with_name(payload["revision"] + ".json")
    new_path.write_text(json.dumps(payload))
    row.update(revision=payload["revision"], detail_entry=str(new_path.relative_to(tmp_path)))
    (store.base / "directory.json").write_text(json.dumps({"alpha": row}))
    with pytest.raises(PortalDataError):
        store.get("alpha")


def test_fact_revision_tracks_content_and_not_caller_labels_or_record_metadata(tmp_path):
    store = ExperienceStore(tmp_path)
    first = store.save("alpha", title="Network research", content=facts())
    second = store.save(
        "alpha",
        title="Network research",
        content=facts(revision="another-caller-label"),
        metadata={"aliases": ["Different discovery metadata"]},
        expected_revision=first["revision"],
    )
    assert first["content"]["revision"] == second["content"]["revision"]
    changed = facts()
    changed["facts"][0]["status"] = "completed"
    third = store.save(
        "alpha", title="Network research", content=changed, expected_revision=second["revision"]
    )
    assert second["content"]["revision"] != third["content"]["revision"]


def test_structured_experience_identity_is_stable_but_title_can_be_corrected(tmp_path):
    store = ExperienceStore(tmp_path)
    first = store.save("alpha", title="Network research", content=facts())
    with pytest.raises(PortalDataError):
        store.save(
            "alpha",
            title="Network research",
            content=facts(experience_id="new-id"),
            expected_revision=first["revision"],
        )
    assert store.get("alpha") == first
    corrected = store.save(
        "alpha",
        title="Corrected title",
        content=facts(title="Corrected title"),
        expected_revision=first["revision"],
    )
    assert corrected["content"]["experience_id"] == first["content"]["experience_id"]
