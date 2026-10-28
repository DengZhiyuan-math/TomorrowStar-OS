"""Complete discovery and demand reads retain source truth using synthetic data."""

import hashlib
import json

import pytest

from career_evidence_graph.application_career_library import CareerLibrary
from career_evidence_graph.career_experiences import ExperienceStore
from career_evidence_graph.career_portal_data import PortalDataError


def library(tmp_path, rows, evidence=()):
    root = tmp_path / "career"
    root.mkdir()

    def write(name, value):
        raw = json.dumps(value).encode()
        (root / name).write_bytes(raw)
        return {"path": name, "sha256": hashlib.sha256(raw).hexdigest()}

    descriptor = {
        "schema_version": 1,
        "root": str(root),
        "catalog": write("catalog.json", {"records": rows}),
        "evidence": [
            {**write(f"source-{number}.json", text), "candidate_id": identifier}
            for number, (identifier, text) in enumerate(evidence)
        ],
    }
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps(descriptor))
    return CareerLibrary(manifest), root


def row(identifier, **fields):
    return {
        "candidate_id": identifier,
        "title": identifier,
        "record_class": "current-confirmed-identity",
        **fields,
    }


@pytest.mark.parametrize(
    ("fields", "required"),
    [
        ({}, True),
        ({"confirmed_identity_facts": {}}, True),
        ({"confirmed_identity_facts": {"role": "", "nested": []}}, True),
        ({"confirmed_identity_facts": {"role": "team researcher"}}, True),
        ({"accepted_reading_summary": "Worked on cell imaging"}, False),
        ({"candidate": {"description": "Planned research placement"}}, False),
        ({"summary": "Cell imaging contributions"}, False),
        ({"description": "Education and project record"}, False),
        ({"accepted_reading_summary": None}, True),
        ({"summary": {"claim": "dict is not narrative"}}, True),
        ({"summary": "entry", "description": "# entry"}, True),
    ],
)
def test_legacy_discovery_is_not_all_pending(tmp_path, fields, required):
    adapter, _ = library(tmp_path, [row("entry", **fields)])
    record = adapter.index()["records"][0]
    assert record["requires_body_discovery"] is required
    assert record["index_status"] == ("pending" if required else "legacy_context")
    assert record["read_status"] == "indexed_not_read"


def test_directory_and_manifest_only_are_read_during_discovery(tmp_path, monkeypatch):
    adapter, root = library(tmp_path, [row("entry")], [("entry", "body")])
    import career_evidence_graph.application_career_library as module

    original = module._bound

    def bound(root, binding, *args):
        assert not binding["path"].startswith("source-")
        return original(root, binding, *args)

    monkeypatch.setattr(module, "_bound", bound)
    (root / "source-0.json").unlink()
    assert adapter.index()["status"] == "available"


def test_complete_selection_has_no_candidate_count_cap_or_total_evidence_cap(tmp_path):
    identifiers = [f"entry-{number}" for number in range(105)]
    adapter, _ = library(
        tmp_path,
        [row(identifier) for identifier in identifiers],
        [(identifiers[0], "A" * 300_000), (identifiers[-1], "B" * 300_000)],
    )
    snapshot = adapter.snapshot_for_analysis({"documents": [], "items": []}, identifiers)
    assert snapshot["career_library"]["selected_candidate_ids"] == sorted(identifiers)
    assert snapshot["career_library"]["unavailable_sources"] == []
    assert sum(len(item["text"]) for item in snapshot["items"]) > 600_000


def test_single_oversized_source_is_explicit_and_never_truncated(tmp_path):
    adapter, _ = library(tmp_path, [row("entry")], [("entry", "A" * 2_000_001)])
    snapshot = adapter.snapshot_for_analysis({"documents": [], "items": []}, ["entry"])
    assert len(snapshot["items"]) == 1
    assert snapshot["career_library"]["unavailable_sources"] == [
        {"candidate_id": "entry", "path": "source-0.json", "status": "unavailable"}
    ]
    assert snapshot["career_library"]["source_reads"][0]["status"] == "unavailable"


def test_related_ids_expand_cycle_once_and_missing_relation_is_visible(tmp_path):
    adapter, root = library(tmp_path, [row("a"), row("b"), row("c")])
    store = ExperienceStore(root)
    store.save("a", title="A", body="Research responsibility.", metadata={"related_ids": ["b"]})
    store.save(
        "b", title="B", body="Team implementation.", metadata={"related_ids": ["a", "absent"]}
    )
    snapshot = adapter.snapshot_for_analysis({"documents": [], "items": []}, ["a"])
    reads = snapshot["career_library"]
    assert reads["requested_candidate_ids"] == ["a"]
    assert reads["selected_candidate_ids"] == ["a", "b"]
    assert len(snapshot["items"]) == 2
    assert reads["unavailable_sources"] == [
        {"candidate_id": "absent", "related_from": "b", "status": "related_identity_unavailable"}
    ]
    assert {"candidate_id": "c", "status": "indexed_not_read"} in reads["source_reads"]
    assert reads["unavailable_sources"][0] in reads["source_reads"]


def test_pending_derived_index_does_not_fail_successful_body_read(tmp_path, monkeypatch):
    adapter, root = library(tmp_path, [row("entry")])
    store = ExperienceStore(root)

    def fail(*args):
        raise ValueError("Synthetic indexing failure")

    monkeypatch.setattr(store, "_derive", fail)
    store.save("entry", title="Research", body="Preserved responsibility and result.")
    assert adapter.index()["records"][0]["requires_body_discovery"]
    snapshot = adapter.snapshot_for_analysis({"documents": [], "items": []}, ["entry"])
    assert snapshot["career_library"]["unavailable_sources"] == []
    assert snapshot["career_library"]["source_reads"] == [
        {"candidate_id": "entry", "status": "read"}
    ]
    assert "Preserved responsibility" in snapshot["items"][0]["text"]


def test_import_pending_and_missing_material_remain_explicit_after_body_read(tmp_path):
    adapter, root = library(tmp_path, [row("entry")])
    ExperienceStore(root).save(
        "entry",
        title="Research",
        body="Preserved partial body.",
        metadata={"import_status": "pending", "unavailable_sources": ["missing-document"]},
    )
    snapshot = adapter.snapshot_for_analysis({"documents": [], "items": []}, ["entry"])
    failed = snapshot["career_library"]["unavailable_sources"]
    assert {"candidate_id": "entry", "status": "import_pending"} in failed
    assert {
        "candidate_id": "entry",
        "source_id": "missing-document",
        "status": "unavailable",
    } in failed
    assert all(outcome in snapshot["career_library"]["source_reads"] for outcome in failed)
    assert snapshot["items"]


def test_corrupt_experience_directory_is_not_silently_available(tmp_path):
    adapter, root = library(tmp_path, [row("entry")])
    store = ExperienceStore(root)
    store.save("entry", title="Research", body="Saved facts.")
    (store.base / "directory.json").write_text("{bad-json")
    index = adapter.index()
    assert index["status"] == "unavailable"
    assert index["experience_directory_status"] == "unavailable"
    assert index["records"][0]["candidate_id"] == "entry"
    with pytest.raises(PortalDataError):
        adapter.snapshot_for_analysis({"documents": [], "items": []}, ["entry"])


def test_managed_library_without_registry_starts_with_thin_directory(tmp_path, monkeypatch):
    adapter, root = library(tmp_path, [row("entry")], [("entry", "Original source")])
    ExperienceStore(root).save("entry", title="Research", body="Canonical body.")

    def forbidden(*args):
        raise AssertionError("Discovery opened a body")

    monkeypatch.setattr(ExperienceStore, "get", forbidden)
    snapshot = adapter.snapshot_for_analysis({"documents": [], "items": []})
    assert snapshot["items"] == []
    assert snapshot["career_library"]["canonical_sources"]
    assert snapshot["career_library"]["requested_candidate_ids"] == []
    assert snapshot["career_library"]["source_reads"] == [
        {"candidate_id": "entry", "status": "indexed_not_read"}
    ]


@pytest.mark.parametrize("kind", ["body", "supplement"])
def test_managed_markdown_packet_preserves_literal_lines_offsets_and_context(tmp_path, kind):
    from test_application_match import model_runner

    from career_evidence_graph.application_match import _model_source, _quoted_source
    from career_evidence_graph.application_material_packet import prepare_material_packet

    adapter, root = library(tmp_path, [row("entry")])
    text = ("Unrelated context " * 20 + "\n\n") * 400 + "I validated risk\n"
    material = {
        "id": "supplement",
        "role": "supplement",
        "source_name": "Research notes",
        "text": text,
        "attribution": "User validated; collaborators wrote the original model.",
        "boundaries": "Planned deployment; completed validation only.",
    }
    ExperienceStore(root).save(
        "entry",
        title="Research",
        body=text if kind == "body" else "Validation research context.",
        metadata={"status": "planned"},
        materials=[] if kind == "body" else [material],
    )
    snapshot = adapter.snapshot_for_analysis({"documents": [], "items": []}, ["entry"])
    item = next(item for item in snapshot["items"] if item["locator"] == kind)
    assert item["text"] == text
    assert item["record_context"]["metadata"]["status"] == "planned"
    if kind == "supplement":
        assert item["record_context"]["material"]["attribution"] == material["attribution"]
        assert item["record_context"]["material"]["boundaries"] == material["boundaries"]
    calls = []

    def runner(config, prompt, **kwargs):
        data = json.loads(prompt.split("CONTEXT_JSON\n", 1)[1])
        selections = []
        for supplied in data.get("source_ranges", [data]):
            if "spans" in supplied:
                selections.extend(
                    {"span_id": span["span_id"], "requirement_indexes": [0]}
                    for span in supplied["spans"]
                    if "I validated risk" in span["text"]
                )
            elif "I validated risk" in supplied["text"]:
                selections.append(
                    {"source_id": supplied["source"]["source_id"], "requirement_indexes": [0]}
                )
        return model_runner({"selections": selections}, calls)(config, prompt, **kwargs)

    _, packet = prepare_material_packet(
        {"job_description": "Risk validation"},
        snapshot,
        tmp_path / "packet",
        runner=runner,
        requirements=[
            {"text": "Risk validation", "importance": "required", "hard_condition": False}
        ],
    )
    assert packet["status"] == "complete"
    prepared = packet["sources"][item["source_id"]]
    assert prepared["text"].strip() == "I validated risk"
    part = prepared["quote_segments"][0]
    assert text[part["source_start"] : part["source_end"]] == prepared["text"]
    assert prepared["record_context"] == item["record_context"]
    assert _model_source(prepared)["record_context"] == item["record_context"]
    citation = _quoted_source(prepared, "I validated risk")
    assert citation["quote_start"] == text.index("I validated risk")
    assert text[citation["quote_start"] : citation["quote_end"]] == "I validated risk"
    assert prepared["original_text_chars"] == len(text)
    assert packet["source_reads"][item["source_id"]]["status"] == "complete"
    assert len(packet["source_reads"][item["source_id"]]["ranges"]) > 1


def test_managed_source_revision_binds_context_even_when_literal_text_unchanged(tmp_path):
    adapter, root = library(tmp_path, [row("entry")])
    store = ExperienceStore(root)
    first = store.save(
        "entry", title="Research", body="Literal research.", metadata={"status": "planned"}
    )
    before = adapter.snapshot_for_analysis({"documents": [], "items": []}, ["entry"])["items"][0]
    store.save(
        "entry",
        title="Research",
        body=first["body"],
        metadata={"status": "completed"},
        expected_revision=first["revision"],
    )
    after = adapter.snapshot_for_analysis({"documents": [], "items": []}, ["entry"])["items"][0]
    assert before["text"] == after["text"]
    assert before["record_context"] != after["record_context"]
    assert before["source_revision"] != after["source_revision"]
    assert before["source_id"] != after["source_id"]
