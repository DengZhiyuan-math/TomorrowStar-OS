"""Experience bodies, incremental discovery and source roles use synthetic facts only."""

import hashlib
import json
from copy import deepcopy

import pytest
from test_canonical_career_sources import canonical as canonical
from test_canonical_career_sources import inventory_binding

from career_evidence_graph.application_career_library import CareerLibrary
from career_evidence_graph.career_experiences import ExperienceStore
from career_evidence_graph.career_portal_data import PortalDataError


def material(identifier, text, *, role="supplement", **extra):
    return {"id": identifier, "source_name": identifier, "text": text, "role": role, **extra}


@pytest.fixture
def library(tmp_path):
    root = tmp_path / "career"
    root.mkdir()
    manifest = tmp_path / "manifest.json"

    def write(name, value):
        raw = json.dumps(value).encode()
        (root / name).write_bytes(raw)
        return {"path": name, "sha256": hashlib.sha256(raw).hexdigest()}

    rows = [
        {
            "candidate_id": identifier,
            "title": title,
            "record_class": "current-confirmed-identity",
            "confirmed_identity_facts": {"status": "in progress", "role": "team member"},
        }
        for identifier, title in (("alpha", "Network research"), ("beta", "Teaching"))
    ]
    descriptor = {
        "schema_version": 1,
        "root": str(root),
        "catalog": write("catalog.json", {"records": rows}),
        "evidence": [
            {
                **write("work.json", {"work": "Python models of neural connectivity"}),
                "candidate_id": "alpha",
                "pointer": "/work",
            },
        ],
    }
    manifest.write_text(json.dumps(descriptor))
    return CareerLibrary(manifest), root, descriptor, rows, write


def test_body_and_detailed_materials_independently_supply_directory_terms(tmp_path):
    store = ExperienceStore(tmp_path)
    body = "# Network research\n\nModelled neural connectivity with biology collaborators."
    saved = store.save(
        "fixed-id",
        title="Network research",
        body=body,
        metadata={"aliases": ["Earlier name"], "status": "planned"},
        materials=[
            material("repository", "Detailed implementation used Python and sparse matrices")
        ],
    )
    row = store.directory()["fixed-id"]
    assert {"neural", "biology", "python", "sparse"} <= set(row["retrieval_terms"])
    assert "Python" not in row["title"] and "Python" not in row["summary"]
    assert row["aliases"] == ["Earlier name"]
    assert row["index_status"] == "ready" and row["status"] == "planned"
    assert "body" not in row and "text" not in json.dumps(row)
    assert store.get("fixed-id") == saved


def test_duplicates_keep_source_relationships_and_unique_pdf_annotations(tmp_path):
    store = ExperienceStore(tmp_path)
    store.save(
        "fixed-id",
        title="Work",
        body="# Work\n\nBuilt a model.",
        materials=[
            material("source.tex", "Reproduced a sparse solver."),
            material(
                "export.pdf",
                "Reproduced  a sparse solver.\n",
                role="artifact",
                derived_from="source.tex",
            ),
            material("copy.txt", "Reproduced a sparse solver."),
            material(
                "annotated.pdf", "Additional observation: convergence diagnosis.", role="artifact"
            ),
            material("resume.pdf", "Generated fantasy keyword", role="generated"),
        ],
    )
    row = store.directory()["fixed-id"]
    assert len(row["material_groups"]) == 2
    assert row["material_groups"][0]["source_ids"] == ["source.tex", "export.pdf", "copy.txt"]
    assert row["material_groups"][0]["sources"][1]["derived_from"] == "source.tex"
    assert "convergence" in row["retrieval_terms"]
    assert "fantasy" not in row["retrieval_terms"]
    assert len(store.get("fixed-id")["materials"]) == 5


def test_corrections_rename_and_relocation_keep_identity_and_history(tmp_path):
    store = ExperienceStore(tmp_path)
    first = store.save("id/never-a-path", title="Before", body="Exact previous facts.")
    previous_path = tmp_path / store.directory()["id/never-a-path"]["detail_entry"]
    second = store.save(
        "id/never-a-path",
        title="After",
        body="Explicit correction; team operated the system.",
        metadata={"links": ["repositories/moved"]},
        expected_revision=first["revision"],
    )
    assert second["previous_revision"] == first["revision"]
    assert json.loads(previous_path.read_bytes()) == first
    assert list(store.directory()) == ["id/never-a-path"]
    with pytest.raises(PortalDataError, match="刷新"):
        store.save(
            "id/never-a-path", title="Late", body="Stale", expected_revision=first["revision"]
        )
    assert store.get("id/never-a-path") == second


def test_failed_index_still_saves_body_and_discoverable_entry(tmp_path):
    def fail(_):
        raise ValueError("synthetic indexing failure")

    store = ExperienceStore(tmp_path, derive=fail)
    saved = store.save("id", title="Retained", body="Unchanged self-reported facts.")
    row = store.directory()["id"]
    assert row["index_status"] == "pending" and row["detail_entry"]
    assert store.get("id") == saved


def test_sync_is_complete_incremental_and_does_not_require_research_review(library, monkeypatch):
    adapter, root, descriptor, rows, write = library
    before = deepcopy(descriptor)
    first = adapter.sync_experiences()
    assert first["updated"] == ["alpha", "beta"]
    initial = ExperienceStore(root).directory()
    assert "python" in initial["alpha"]["retrieval_terms"]
    assert "in progress" in adapter.read_experience("alpha")["body"]
    assert adapter.sync_experiences()["unchanged"] == ["alpha", "beta"]

    original = adapter.snapshot_for_analysis
    reads = []

    def counted(base, ids=None, **kwargs):
        reads.extend(ids or [])
        return original(base, ids, **kwargs)

    monkeypatch.setattr(adapter, "snapshot_for_analysis", counted)
    rows[0]["title"] = "Renamed research"
    descriptor["catalog"] = write("catalog.json", {"records": rows})
    adapter.manifest.write_text(json.dumps(descriptor))
    result = adapter.sync_experiences()
    assert result["updated"] == ["alpha"] and result["unchanged"] == ["beta"]
    assert reads == ["alpha"]
    after = ExperienceStore(root).directory()
    assert initial["beta"] == after["beta"]
    assert after["alpha"]["title"] == "Renamed research"
    assert before["evidence"] == descriptor["evidence"]


def test_explicit_body_edits_survive_source_sync_and_application_snapshots(library):
    adapter, root, descriptor, rows, write = library
    adapter.sync_experiences()
    before = adapter.read_experience("alpha")
    adapter.save_experience(
        "alpha",
        title="Human title",
        body="My wording and planned team responsibility.",
        materials=[
            material("detail", "Python sparse reconstruction"),
            material("detail-copy", "Python sparse reconstruction"),
            material("resume.pdf", "Generated fantasy", role="generated"),
        ],
        expected_revision=before["revision"],
    )
    rows[0]["title"] = "Source changed later"
    descriptor["catalog"] = write("catalog.json", {"records": rows})
    adapter.manifest.write_text(json.dumps(descriptor))
    adapter.sync_experiences()
    saved = adapter.read_experience("alpha")
    assert (
        saved["title"] == "Human title"
        and saved["body"] == "My wording and planned team responsibility."
    )
    base = {"documents": [], "items": []}
    snapshot = adapter.snapshot_for_analysis(base, ["alpha"])
    assert base == {"documents": [], "items": []}
    assert len(snapshot["items"]) == 2
    assert "fantasy" not in json.dumps(snapshot)
    assert snapshot["career_library"]["records"] == adapter.index()["records"]
    assert snapshot["career_library"]["revision"] == adapter.index()["revision"]
    assert "My wording" in snapshot["items"][0]["text"]
    assert snapshot["items"][0]["title"] == "Human title"


def test_missing_material_keeps_entry_and_records_execution_failure(library):
    adapter, root, *_ = library
    (root / "work.json").unlink()
    result = adapter.sync_experiences()
    assert "alpha" in result["pending"]
    index = adapter.index()
    assert {row["candidate_id"] for row in index["records"]} == {"alpha", "beta"}
    snapshot = adapter.snapshot_for_analysis({"documents": [], "items": []}, ["alpha"])
    assert snapshot["career_library"]["unavailable_sources"] == [
        {"candidate_id": "alpha", "status": "import_pending"},
        {"candidate_id": "alpha", "source_id": "work.json", "status": "unavailable"},
    ]


@pytest.mark.parametrize("retained_unavailable", [None, ["explicit-missing-source"]])
def test_explicit_body_correction_supersedes_old_failed_source_status(
    library, retained_unavailable
):
    adapter, root, *_ = library
    (root / "work.json").unlink()
    assert adapter.sync_experiences(["alpha"])["pending"] == ["alpha"]
    before = adapter.read_experience("alpha")
    assert before["metadata"]["unavailable_sources"] == ["work.json"]
    metadata = {} if retained_unavailable is None else {"unavailable_sources": retained_unavailable}
    correction = "Explicit correction: validated team models; deployment remained planned."
    saved = adapter.save_experience(
        "alpha", body=correction, metadata=metadata, expected_revision=before["revision"]
    )
    assert saved["body"] == correction
    assert saved["previous_revision"] == before["revision"]
    assert saved["metadata"]["import_status"] == "complete"
    assert saved["metadata"]["unavailable_sources"] == (retained_unavailable or [])
    snapshot = adapter.snapshot_for_analysis({"documents": [], "items": []}, ["alpha"])
    assert snapshot["career_library"]["unavailable_sources"] == [
        {"candidate_id": "alpha", "source_id": source_id, "status": "unavailable"}
        for source_id in (retained_unavailable or [])
    ]
    assert snapshot["items"][0]["text"] == correction


def test_directory_reads_never_open_primary_bodies(library, monkeypatch):
    adapter, root, *_ = library
    adapter.sync_experiences()

    def forbidden(*args):
        raise AssertionError("directory attempted to read a primary body")

    monkeypatch.setattr(ExperienceStore, "get", forbidden)
    assert len(adapter.index()["records"]) == 2
    assert ExperienceStore(root).directory()["alpha"]["index_status"] == "ready"


def test_tampered_version_is_execution_failure_and_not_old_source_fallback(library):
    adapter, root, *_ = library
    adapter.sync_experiences()
    path = root / ExperienceStore(root).directory()["alpha"]["detail_entry"]
    value = json.loads(path.read_bytes())
    value["body"] = "Corrupt unrelated replacement"
    path.write_text(json.dumps(value))
    snapshot = adapter.snapshot_for_analysis({"documents": [], "items": []}, ["alpha"])
    assert snapshot["items"] == []
    assert snapshot["career_library"]["unavailable_sources"]
    assert any(row["candidate_id"] == "alpha" for row in adapter.index()["records"])


def test_user_body_keeps_corrections_while_new_linked_materials_refresh(library):
    adapter, _, descriptor, rows, write = library
    rows[0]["confirmed_identity_facts"]["role"] = "sole owner"
    rows[0]["candidate"] = {"description": "sole owner"}
    descriptor["catalog"] = write("catalog.json", {"records": rows})
    adapter.manifest.write_text(json.dumps(descriptor))
    adapter.sync_experiences()
    original = adapter.read_experience("alpha")
    corrected = adapter.save_experience(
        "alpha",
        body="The team operated the system. I reviewed it.",
        expected_revision=original["revision"],
        metadata={"status": "planned"},
    )
    descriptor["evidence"].append(
        {
            **write("new-repository.json", {"work": "Rust compiler experiments"}),
            "candidate_id": "alpha",
            "pointer": "/work",
        }
    )
    adapter.manifest.write_text(json.dumps(descriptor))
    adapter.sync_experiences()
    saved = adapter.read_experience("alpha")
    row = next(row for row in adapter.index()["records"] if row["candidate_id"] == "alpha")
    assert saved["body"] == corrected["body"]
    assert row["status"] == "planned" and "rust" in row["retrieval_terms"]
    assert "sole owner" not in json.dumps(row)
    snapshot = adapter.snapshot_for_analysis({"documents": [], "items": []}, ["alpha"])
    assert "Rust compiler" in json.dumps(snapshot["items"])
    assert "sole owner" not in json.dumps(snapshot)
    # Updating a linked supplement affects that source while preserving the body.
    descriptor["evidence"][-1] = {
        **write("new-repository.json", {"work": "Haskell compiler experiments"}),
        "candidate_id": "alpha",
        "pointer": "/work",
    }
    adapter.manifest.write_text(json.dumps(descriptor))
    adapter.sync_experiences()
    row = next(row for row in adapter.index()["records"] if row["candidate_id"] == "alpha")
    assert "haskell" in row["retrieval_terms"] and "rust" not in row["retrieval_terms"]


def test_missing_generated_export_cannot_degrade_saved_experience(library):
    adapter, _, descriptor, _, _ = library
    descriptor["evidence"].append(
        {
            "candidate_id": "alpha",
            "path": "missing-generated-resume.pdf",
            "sha256": "a" * 64,
            "role": "generated",
        }
    )
    adapter.manifest.write_text(json.dumps(descriptor))
    adapter.sync_experiences()
    assert adapter.index()["status"] == "available"
    assert adapter.index()["coverage"]["unavailable_sources"] == []


def test_directory_keeps_full_provenance_in_details_only(tmp_path):
    store = ExperienceStore(tmp_path)
    original = material("source", "Python sparse work", boundaries="Long provenance " * 6000)
    store.save("id", title="Research", body="Worked with a team.", materials=[original])
    row = store.directory()["id"]
    assert len(json.dumps(row)) < 2000
    assert store.get("id")["materials"][0] == original


def test_missing_superseded_capture_does_not_downgrade_explicit_correction(library):
    adapter, root, descriptor, rows, write = library
    adapter.sync_experiences()
    before = adapter.read_experience("alpha")
    adapter.save_experience(
        "alpha",
        body="User correction: the work was planned, and the team owned operations.",
        expected_revision=before["revision"],
    )
    (root / "work.json").unlink()
    rows[0]["title"] = "Updated source title"
    descriptor["catalog"] = write("catalog.json", {"records": rows})
    adapter.manifest.write_text(json.dumps(descriptor))
    assert adapter.sync_experiences(["alpha"])["pending"] == []
    assert ExperienceStore(root).directory()["alpha"]["index_status"] == "ready"
    snapshot = adapter.snapshot_for_analysis({"documents": [], "items": []}, ["alpha"])
    assert not snapshot["career_library"]["unavailable_sources"]


@pytest.mark.parametrize("fragment", ["L1", "unknown_symbol"])
def test_history_identity_uses_original_registry_locator(canonical, tmp_path, fragment):
    adapter, root, _, _, write, manifest, descriptor = canonical
    inventory_binding(
        canonical,
        tmp_path / "archived-project",
        b"const callback = () => 1;\n",
        retained=True,
        fragment=fragment,
    )
    adapter.sync_experiences()
    before = adapter.read_experience("unseen-identity")
    adapter.save_experience(
        "unseen-identity",
        body="Explicit user correction with current facts.",
        expected_revision=before["revision"],
    )
    catalog = json.loads((root / "catalog.json").read_bytes())
    catalog["records"][0]["title"] = "Later title"
    descriptor["catalog"] = write("catalog.json", catalog)
    manifest.write_text(json.dumps(descriptor))
    for path in (root / ".career-evidence/raw").iterdir():
        path.unlink()
    assert adapter.sync_experiences()["pending"] == []


@pytest.mark.parametrize("trusted", [False, True])
def test_identical_work_text_retains_distinct_responsibility_context(library, trusted):
    adapter, root, descriptor, _, _ = library
    if trusted:
        descriptor["application_policy"] = "trusted-library/v1"
        adapter.manifest.write_text(json.dumps(descriptor))
    adapter.save_experience(
        "alpha",
        title="Multiple work streams",
        body="Worked on two distinct subprojects.",
        materials=[
            material(
                "team",
                "Implemented solver.",
                attribution="Team only",
                boundaries="User did not implement this.",
                dates="Earlier period",
            ),
            material(
                "personal",
                "Implemented solver.",
                attribution="User only",
                boundaries="User implemented this in another subproject.",
                dates="Later period",
            ),
        ],
    )
    assert len(ExperienceStore(root).directory()["alpha"]["material_groups"]) == 2
    snapshot = adapter.snapshot_for_analysis({"documents": [], "items": []}, ["alpha"])
    assert len(snapshot["items"]) == 3
    team, personal = snapshot["items"][1:]
    assert team["attribution"] == "Team only"
    assert personal["attribution"] == "User only"
    assert team["text"] == personal["text"] == "Implemented solver."
    assert team["record_context"]["material"]["boundaries"] == "User did not implement this."
    assert personal["record_context"]["material"]["boundaries"] == (
        "User implemented this in another subproject."
    )
    assert team["record_context"]["material"]["dates"] == "Earlier period"
    assert personal["record_context"]["material"]["dates"] == "Later period"


@pytest.mark.parametrize(
    "target", [".tomorrowstar-experiences", ".tomorrowstar-experiences/directory.json"]
)
def test_store_rejects_symlinks(tmp_path, target):
    store = ExperienceStore(tmp_path)
    saved = store.save("id", title="Work", body="Private facts")
    path = tmp_path / target
    moved = tmp_path / "moved"
    path.rename(moved)
    path.symlink_to(moved, target_is_directory=moved.is_dir())
    with pytest.raises(PortalDataError):
        store.save("id", title="Work", body="Update", expected_revision=saved["revision"])
