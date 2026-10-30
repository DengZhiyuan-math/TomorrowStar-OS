"""Structured facts remain whole during the existing material-packet read path."""

import json
from copy import deepcopy

import pytest
from test_application_material_packet import batch_reader, snapshot

from career_evidence_graph import application_material_packet as material

pytestmark = pytest.mark.usefixtures("reading_limits")

APPLICATION = {"company": "Example", "role_title": "Researcher", "job_description": "Risk."}
REQUIREMENTS = [{"text": "Validate risk", "importance": "required", "hard_condition": False}]


def structured_snapshot():
    original = snapshot(
        "I validated risk. " + "The team reviewed the experimental result. " * 800,
        "Unrelated historical material.\n\n" * 2500,
    )
    original["items"][0]["record_context"] = {
        "experience_id": "experience-risk",
        "candidate_id": "career-experience:risk",
        "experience_revision": "experience-r1",
        "content_revision": "content-r1",
        "fact_id": "fact-risk",
        "source_refs": ["source-notes"],
        "responsibility": "team",
        "status": "completed",
        "scope": "An experimental result; no production deployment.",
    }
    return original


def test_long_structured_fact_is_selected_by_source_id_and_delivered_whole(tmp_path):
    original = structured_snapshot()
    calls = []
    _, packet = material.prepare_material_packet(
        APPLICATION,
        original,
        tmp_path / "packet",
        runner=batch_reader(calls),
        requirements=REQUIREMENTS,
    )
    supplied = next(
        source
        for context, _ in calls
        for source in context.get("source_ranges", [context])
        if source["source"]["source_id"] == "source-0"
    )
    assert "spans" not in supplied
    assert supplied["text"] == original["items"][0]["text"]
    assert supplied["source"]["record_context"] == original["items"][0]["record_context"]
    delivered = packet["sources"]["source-0"]
    assert delivered["text"] == original["items"][0]["text"]
    assert delivered["record_context"]["source_refs"] == ["source-notes"]
    assert "original_text_chars" not in delivered
    response = next(
        result
        for path in (tmp_path / "packet").glob("source-*/result.json")
        if (result := json.loads(path.read_text()))["structured_result"]["selections"]
    )
    assert response["structured_result"] == {
        "selections": [{"source_id": "source-0", "requirement_indexes": [0]}]
    }


def test_changed_fact_context_cannot_reuse_a_completed_text_read(tmp_path):
    original = structured_snapshot()
    calls = []
    _, first = material.prepare_material_packet(
        APPLICATION,
        original,
        tmp_path / "first",
        runner=batch_reader(calls),
        requirements=REQUIREMENTS,
    )
    unchanged_calls = []
    _, unchanged = material.prepare_material_packet(
        APPLICATION,
        original,
        tmp_path / "unchanged",
        runner=batch_reader(unchanged_calls),
        requirements=REQUIREMENTS,
        previous=first,
    )
    assert unchanged_calls == []
    assert unchanged["source_reads"]["source-0"]["reused"] is True
    changed = deepcopy(original)
    changed["items"][0]["record_context"].update(
        responsibility="third_party", source_refs=["corrected-source"]
    )
    retry_calls = []
    _, second = material.prepare_material_packet(
        APPLICATION,
        changed,
        tmp_path / "changed",
        runner=batch_reader(retry_calls),
        requirements=REQUIREMENTS,
        previous=first,
    )
    read_ids = [
        source["source"]["source_id"]
        for context, _ in retry_calls
        for source in context.get("source_ranges", [context])
    ]
    assert read_ids == ["source-0"]
    assert second["sources"]["source-0"]["record_context"]["responsibility"] == "third_party"
    assert second["source_reads"]["source-1"]["reused"] is True
