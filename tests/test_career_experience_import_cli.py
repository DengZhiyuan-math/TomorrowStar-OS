"""The existing career operator previews and publishes through the real store."""

import json
import subprocess
import sys
from copy import deepcopy
from pathlib import Path

import pytest
from test_career_experience_import import legacy_case
from test_career_experiences import library as library

from career_evidence_graph.career_experiences import ExperienceStore
from career_evidence_graph.career_portal_data import PortalDataError

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/run_career_experiences.py"


def run_import(adapter, path, action):
    return subprocess.run(
        [
            sys.executable,
            "-B",
            str(SCRIPT),
            "--manifest",
            str(adapter.manifest),
            action,
            "--candidate-id",
            "alpha",
            "--request",
            str(path),
        ],
        capture_output=True,
        text=True,
        check=False,
    )


def test_existing_operator_previews_without_write_then_publishes_version(library, tmp_path):
    adapter, root, *_ = library
    previous, request = legacy_case()
    store = ExperienceStore(root)
    saved = store.save("alpha", title="Validation", body=previous["body"])
    request["expected_revision"] = saved["revision"]
    request["content"].update(candidate_id="alpha", experience_id="alpha")
    path = tmp_path / "import-request.json"
    path.write_text(json.dumps(request))
    preview = run_import(adapter, path, "preview-import")
    assert preview.returncode == 0, preview.stderr
    assert json.loads(preview.stdout)["ready"] is True
    assert store.get("alpha") == saved
    committed = run_import(adapter, path, "import")
    assert committed.returncode == 0, committed.stderr
    current = store.get("alpha")
    assert "body" not in current
    assert current["previous_revision"] == saved["revision"]
    assert current["content"]["facts"][0]["text"] == previous["body"]


def test_incomplete_import_reports_gap_and_never_changes_current_record(library, tmp_path):
    adapter, root, *_ = library
    previous, request = legacy_case()
    store = ExperienceStore(root)
    saved = store.save("alpha", title="Validation", body=previous["body"] + " Unique detail.")
    request["expected_revision"] = saved["revision"]
    request["content"].update(candidate_id="alpha", experience_id="alpha")
    path = tmp_path / "incomplete-import.json"
    path.write_text(json.dumps(request))
    preview = run_import(adapter, path, "preview-import")
    assert preview.returncode == 0, preview.stderr
    assert json.loads(preview.stdout)["ready"] is False
    committed = run_import(adapter, path, "import")
    assert committed.returncode == 1
    assert json.loads(committed.stderr) == {"error": "experience-import-incomplete"}
    assert store.get("alpha") == saved


def test_structured_experience_imports_new_material_without_rewriting_saved_facts(
    library, tmp_path
):
    adapter, root, *_ = library
    previous, request = legacy_case()
    store = ExperienceStore(root)
    saved = store.save("alpha", title="Validation", body=previous["body"])
    request["expected_revision"] = saved["revision"]
    request["content"].update(candidate_id="alpha", experience_id="alpha")
    imported = adapter.import_experience("alpha", request)
    text = "No deployment occurred; validation remained a team plan."
    pending = adapter.save_experience(
        "alpha",
        materials=[
            {"id": "update", "source_name": "update.txt", "role": "supplement", "text": text}
        ],
        expected_revision=imported["revision"],
    )
    assert pending["metadata"]["import_status"] == "pending"
    incoming = deepcopy(imported["content"])
    incoming["sources"].append({"id": "update", "locator": "/materials/0/text"})
    incoming["facts"].append(
        {**incoming["facts"][0], "id": "fact-2", "text": text, "source_refs": ["update"]}
    )
    request.update(
        expected_revision=pending["revision"],
        content=incoming,
        parts=[
            {
                **request["parts"][0],
                "id": "update",
                "source_pointer": "/materials/0/text",
                "end": len(text),
                "quote": text,
                "fact_ids": ["fact-2"],
                "source_ref": "update",
            }
        ],
    )
    path = tmp_path / "incremental-import.json"
    path.write_text(json.dumps(request))
    preview = run_import(adapter, path, "preview-import")
    assert preview.returncode == 0, preview.stderr
    assert json.loads(preview.stdout)["ready"] is True
    assert store.get("alpha") == pending
    published = run_import(adapter, path, "import")
    assert published.returncode == 0, published.stderr
    current = store.get("alpha")
    assert current["previous_revision"] == pending["revision"]
    assert current["content"]["facts"][0] == imported["content"]["facts"][0]
    assert current["content"]["sources"][0] == imported["content"]["sources"][0]
    assert current["metadata"]["import_status"] == "complete"
    snapshot = adapter.snapshot_for_analysis({"documents": [], "items": []}, ["alpha"])
    assert [item["text"] for item in snapshot["items"]] == [previous["body"], text]
    assert snapshot["career_library"]["unavailable_sources"] == []


def test_normal_save_cannot_supply_import_coverage(library):
    adapter, root, *_ = library
    previous, request = legacy_case()
    saved = ExperienceStore(root).save("alpha", title="Validation", body=previous["body"])
    request["expected_revision"] = saved["revision"]
    request["content"].update(candidate_id="alpha", experience_id="alpha")
    imported = adapter.import_experience("alpha", request)
    with pytest.raises(PortalDataError) as error:
        adapter.save_experience(
            "alpha",
            expected_revision=imported["revision"],
            content=imported["content"],
            migration={"source_snapshots": {}, "parts": []},
        )
    assert error.value.code == "experience-import-required"
    assert adapter.read_experience("alpha") == imported


@pytest.mark.parametrize("failed_sources", [[], ["unread-source"]])
def test_empty_incremental_import_cannot_clear_unread_or_unknown_pending(library, failed_sources):
    adapter, root, *_ = library
    previous, request = legacy_case()
    saved = ExperienceStore(root).save("alpha", title="Validation", body=previous["body"])
    request["expected_revision"] = saved["revision"]
    request["content"].update(candidate_id="alpha", experience_id="alpha")
    imported = adapter.import_experience("alpha", request)
    pending = ExperienceStore(root).save(
        "alpha",
        title=imported["title"],
        content=imported["content"],
        materials=imported["materials"],
        migration=imported["migration"],
        metadata={"import_status": "pending", "unavailable_sources": failed_sources},
        expected_revision=imported["revision"],
    )
    request.update(expected_revision=pending["revision"], content=pending["content"], parts=[])
    published = adapter.import_experience("alpha", request)
    assert published["metadata"]["import_status"] == "pending"
    assert published["metadata"]["unavailable_sources"] == failed_sources
    unchanged = deepcopy(published["content"])
    unchanged["revision"] = "caller-controlled-revision"
    saved_again = adapter.save_experience(
        "alpha",
        content=unchanged,
        metadata={"import_status": "complete", "unavailable_sources": []},
        expected_revision=published["revision"],
    )
    assert saved_again["metadata"]["import_status"] == "pending"
    assert saved_again["metadata"]["unavailable_sources"] == failed_sources
    corrected = deepcopy(saved_again["content"])
    corrected["facts"][0]["text"] += " The user confirmed this correction."
    corrected_record = adapter.save_experience(
        "alpha", content=corrected, expected_revision=saved_again["revision"]
    )
    assert corrected_record["metadata"]["import_status"] == "complete"
    assert corrected_record["metadata"]["unavailable_sources"] == []
    assert "unavailable_sources" not in corrected_record["metadata"]["manual_fields"]
