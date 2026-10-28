"""Explicit library linkage is documentary, bounded, and separate from material lineage."""

import hashlib
import json
from copy import deepcopy

import pytest
from test_career_portal_http import portal as portal
from test_macos_portal import native_launch_executable as native_launch_executable

from career_evidence_graph.application_career_library import CareerLibrary
from career_evidence_graph.application_match import _sources
from career_evidence_graph.career_portal_data import PortalDataError


@pytest.fixture
def library(tmp_path):
    root = tmp_path / "career"
    root.mkdir()

    def write(name, data):
        raw = json.dumps(data).encode()
        (root / name).write_bytes(raw)
        return {"path": name, "sha256": hashlib.sha256(raw).hexdigest()}

    catalog = write(
        "catalog.json",
        {
            "records": [
                {
                    "candidate_id": "python",
                    "title": "Python_study",
                    "formal_category": "related",
                    "record_class": "current-confirmed-identity",
                    "uncertainty_notes": ["No authorship inferred"],
                },
                {
                    "candidate_id": "teaching",
                    "title": "Teaching",
                    "formal_category": "teaching",
                    "record_class": "current-confirmed-identity",
                },
                {"candidate_id": "old", "title": "Old", "record_class": "historical-predecessor"},
            ]
        },
    )
    capture = write(
        "capture.json", {"python": "Python exercises and study notes", "large": "x" * 1000}
    )
    descriptor = {
        "schema_version": 1,
        "root": str(root),
        "catalog": catalog,
        "evidence": [{**capture, "candidate_id": "python", "pointer": "/python"}],
    }
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps(descriptor))
    base = {"documents": [], "items": [], "coverage": {}, "revision": "original"}
    return CareerLibrary(manifest), root, manifest, descriptor, base


def test_index_is_thin_and_includes_unbound_current_records(library):
    adapter, _, _, _, _ = library
    index = adapter.index()
    assert index["status"] == "available"
    assert [row["candidate_id"] for row in index["records"]] == ["python", "teaching"]
    assert index["coverage"]["unbound_candidates"] == 1
    assert "study notes" not in json.dumps(index)


def test_demand_load_preserves_material_snapshot_and_attribution(library):
    adapter, _, _, _, base = library
    before = deepcopy(base)
    snapshot = adapter.snapshot_for_analysis(base)
    assert base == before
    assert len(snapshot["items"]) == 2
    assert "large" not in snapshot["items"][-1]["text"]
    sources = _sources(snapshot)
    assert all(row["available"] and row["match_eligible"] for row in sources.values())
    assert all(row["documentary_only"] and not row["rewrite_allowed"] for row in sources.values())
    assert "No personal responsibility" in snapshot["items"][-1]["boundaries"]


def test_hash_drift_never_becomes_available_evidence(library):
    adapter, root, _, _, base = library
    (root / "capture.json").write_text('{"python":"changed"}')
    snapshot = adapter.snapshot_for_analysis(base)
    assert len(snapshot["items"]) == 1
    assert snapshot["career_library"]["unavailable_sources"]
    assert adapter.index()["status"] == "available"  # Thin discovery never opens evidence.
    assert "changed" not in json.dumps(snapshot)
    (root / "catalog.json").write_text('{"records":[]}')
    assert adapter.index()["status"] == "unavailable"
    with pytest.raises(PortalDataError):
        adapter.snapshot_for_analysis(base)


@pytest.mark.parametrize("unsafe", ["../outside.json", "/private/tmp/outside.json"])
def test_relative_path_guards(library, unsafe):
    adapter, _, manifest, descriptor, _ = library
    descriptor["catalog"]["path"] = unsafe
    manifest.write_text(json.dumps(descriptor))
    assert adapter.index()["status"] == "unavailable"


def test_symlinks_and_historical_selection_rejected(library):
    adapter, root, _, _, base = library
    with pytest.raises(PortalDataError):
        adapter.snapshot_for_analysis(base, ["old"])
    (root / "capture.json").rename(root / "original.json")
    (root / "capture.json").symlink_to(root / "original.json")
    snapshot = adapter.snapshot_for_analysis(base)
    assert snapshot["career_library"]["unavailable_sources"]


def test_unconfigured_library_is_explicit():
    adapter = CareerLibrary(None)
    assert adapter.index()["status"] == "unconfigured"
    with pytest.raises(PortalDataError):
        adapter.snapshot_for_analysis({"documents": [], "items": []})


def test_native_manifest_survives_folder_save_and_is_passed_to_backend(
    library, tmp_path, native_launch_executable
):
    import os
    import subprocess

    _, _, manifest, _, _ = library
    config = tmp_path / "portal.json"
    config.write_text(
        json.dumps(
            {
                "applications": str(tmp_path / "applications"),
                "career_workspace": str(tmp_path / "material-career"),
                "career_library_manifest": str(manifest),
                "preparation_root": str(tmp_path / "flow"),
            }
        )
    )
    result = subprocess.run(
        [str(native_launch_executable), "--prepare-materials", "--config", str(config)],
        env=os.environ | {"TOMORROWSTAR_TEST_SAVE_FOLDERS": "1"},
        capture_output=True,
        text=True,
        timeout=5,
    )
    assert result.returncode == 0, result.stderr
    arguments = json.loads(result.stdout)["arguments"]
    assert arguments[arguments.index("--career-library-manifest") + 1] == str(manifest)
    assert json.loads(config.read_text())["career_library_manifest"] == str(manifest)


def test_connecting_library_keeps_existing_preparation_material_source_binding(
    portal, library, tmp_path
):
    from test_job_explanation_browser import explanation_portal
    from test_match_recheck_preservation import saved_latex_material

    from career_evidence_graph.career_portal_data import ApplicationStore

    _, _, manifest, _, _ = library
    application = ApplicationStore(portal.applications).create_application(
        {"company": "Synthetic", "role_title": "Engineer", "job_description": "Python coding."}
    )
    flow_root = tmp_path / "preparation"
    with explanation_portal(portal, tmp_path) as (first, work):
        service = first.server.application_flow_service
        task = saved_latex_material(first, application, work)
        original_inputs = task["inputs"]
        original_flow = service.path.read_bytes()
    from career_evidence_graph.career_portal import create_server

    server = create_server(
        portal.applications,
        portal.career,
        port=0,
        flow_root=flow_root,
        preparation_only=True,
        career_library_manifest=manifest,
    )
    try:
        service = server.application_flow_service
        current_inputs = service.input_provider(application["id"])["inputs"]
        assert current_inputs["sources_revision"] == original_inputs["sources_revision"]
        assert service.path.read_bytes() == original_flow
        assert service.information_provider()["career_library"]["status"] == "available"
        assert (
            service.recheck_source_provider(application["id"])["career_library"]["loaded_sources"]
            > 0
        )
    finally:
        server.server_close()
