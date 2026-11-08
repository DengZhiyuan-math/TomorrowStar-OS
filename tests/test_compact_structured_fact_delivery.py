"""Canonical career facts fit the material budget without repeated source history."""

import json
from copy import deepcopy

import pytest
from test_application_material_packet import snapshot

from career_evidence_graph import application_material_packet as material

pytestmark = pytest.mark.usefixtures("reading_limits")

APPLICATION = {"company": "Example", "role_title": "Researcher", "job_description": "Risk."}
REQUIREMENTS = [{"text": "Validate risk", "importance": "required", "hard_condition": False}]


def career_facts(count=85):
    original = snapshot(*(f"I validated risk scenario {number}." for number in range(count)))
    definitions = [
        {"id": f"history-{number}", "locator": f"archive/{number}/" + "old-record/" * 100}
        for number in range(12)
    ]
    for number, row in enumerate(original["items"]):
        row["record_context"] = {
            "experience_id": "experience-risk",
            "candidate_id": "career-experience:risk",
            "experience_revision": "experience-r1",
            "content_revision": "content-r1",
            "fact_id": f"fact-{number}",
            "title": "Risk research",
            "role": "Researcher",
            "organization": "Example",
            "start": "2024-01",
            "end": "2025-01",
            "location": None,
            "sources": deepcopy(definitions),
            "source_refs": ["history-0"],
            "responsibility": "team",
            "status": "completed",
            "scope": "Experimental risk validation; no production deployment.",
        }
    return original


def test_complete_canonical_facts_do_not_repeat_historical_sources_in_model_budget(tmp_path):
    original = career_facts()
    before = deepcopy(original)

    def unexpected_reader(*args, **kwargs):
        raise AssertionError("These complete structured facts fit without another model read")

    prepared, packet = material.prepare_material_packet(
        APPLICATION,
        original,
        tmp_path / "packet",
        runner=unexpected_reader,
        requirements=REQUIREMENTS,
    )

    assert packet["status"] == "complete"
    assert len(packet["sources"]) == 85
    for number, source in enumerate(packet["sources"].values()):
        assert source["text"] == f"I validated risk scenario {number}."
        assert source["record_context"] == original["items"][number]["record_context"]
    assert prepared["material_packet_sources"] == packet["sources"]
    assert original == before


def test_overfull_selected_evidence_stops_before_reading_later_batches(tmp_path, monkeypatch):
    from test_application_material_packet import batch_reader

    from career_evidence_graph.career_portal_data import PortalDataError

    original = career_facts(40)
    for row in original["items"]:
        row["text"] += " I validated risk without a production deployment." * 100
    monkeypatch.setattr(material, "MAX_READING_PROMPT_BYTES", 100_000)
    calls = []
    with pytest.raises(PortalDataError) as caught:
        material.prepare_material_packet(
            APPLICATION,
            original,
            tmp_path / "packet",
            runner=batch_reader(calls),
            requirements=REQUIREMENTS,
        )
    assert caught.value.code == "retrieval_execution_incomplete"
    assert len(calls) == 1
    packet = json.loads((tmp_path / "packet/material-packet.json").read_text())
    assert packet["status"] == "failed"
    assert 0 < len(packet["sources"]) < 40
    assert not packet.get("pending_call")
    assert all(
        row["text"] == original["items"][int(source_id.split("-")[1])]["text"]
        for source_id, row in packet["sources"].items()
    )


def test_batched_canonical_selection_shares_context_and_keeps_exact_fact_semantics(
    tmp_path, monkeypatch
):
    from test_application_material_packet import batch_reader

    original = career_facts(40)
    for row in original["items"]:
        row["text"] += " Experimental detail." * 90
    original["items"][1]["record_context"].update(
        responsibility="third_party", status="planned", scope="Not implemented by the user."
    )
    monkeypatch.setattr(material, "MAX_READING_PROMPT_BYTES", 18_000)
    calls = []

    def select_first(output, context):
        output["selections"] = [
            row for row in output["selections"] if row["source_id"] == "source-0"
        ]

    _, packet = material.prepare_material_packet(
        APPLICATION,
        original,
        tmp_path / "packet",
        runner=batch_reader(calls, mutate=select_first),
        requirements=REQUIREMENTS,
    )

    assert len(calls) > 1
    inspected = {}
    for context, prompt_bytes in calls:
        assert prompt_bytes <= 18_000
        for supplied in context.get("source_ranges", [context]):
            source = supplied["source"]
            number = int(source["source_id"].split("-")[1])
            expected = original["items"][number]
            fact = source["record_context"]
            shared = context["experience_contexts"][fact["experience_context_ref"]]
            assert supplied["text"] == expected["text"]
            assert fact["fact_id"] == expected["record_context"]["fact_id"]
            for key in ("responsibility", "status", "source_refs"):
                assert fact[key] == expected["record_context"][key]
            assert (
                context["scope_contexts"][fact["scope_ref"]] == expected["record_context"]["scope"]
            )
            assert shared["experience_id"] == "experience-risk"
            assert shared["sources"] == expected["record_context"]["sources"][:1]
            inspected[source["source_id"]] = supplied["text"]
    assert len(inspected) == 40
    assert calls[1][0]["already_selected"]["sources"][0]["source_id"] == "source-0"
    assert list(packet["sources"]) == ["source-0"]
    assert packet["sources"]["source-0"]["record_context"] == original["items"][0]["record_context"]


def test_context_limits_defaults_and_explicit_budget_bind_match_configuration():
    from career_evidence_graph.application_match import context_limits, match_configuration

    assert context_limits({}) == {"match_context_bytes": 384_000, "material_context_bytes": 200_000}
    environment = {
        "TOMORROWSTAR_MATCH_CONTEXT_BYTES": "384000",
        "TOMORROWSTAR_MATERIAL_CONTEXT_BYTES": "300000",
    }
    assert context_limits(environment) == {
        "match_context_bytes": 384_000,
        "material_context_bytes": 300_000,
    }
    assert match_configuration(environment)["context_limits"] == context_limits(environment)
    assert (
        match_configuration({})["context_limits"]
        != match_configuration(environment)["context_limits"]
    )


def test_explicit_context_budget_delivers_all_canonical_facts_without_extra_calls(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("TOMORROWSTAR_MATCH_CONTEXT_BYTES", "384000")
    monkeypatch.setenv("TOMORROWSTAR_MATERIAL_CONTEXT_BYTES", "300000")
    original = career_facts(200)
    for row in original["items"]:
        row["text"] += " Complete experimental detail." * 20

    def unexpected_reader(*args, **kwargs):
        raise AssertionError("The explicitly configured budget fits all supplied facts")

    _, packet = material.prepare_material_packet(
        APPLICATION,
        original,
        tmp_path / "packet",
        runner=unexpected_reader,
        requirements=REQUIREMENTS,
    )
    assert len(packet["sources"]) == 200
    assert packet["context_limits"] == {
        "match_context_bytes": 384_000,
        "material_context_bytes": 300_000,
    }
    for number, row in enumerate(packet["sources"].values()):
        assert row["text"] == original["items"][number]["text"]
        assert row["record_context"] == original["items"][number]["record_context"]


@pytest.mark.parametrize(
    "match_limit, material_limit",
    [
        ("0", "1"),
        ("-1", "1"),
        ("1.5", "1"),
        (" 128000", "60000"),
        ("1048577", "60000"),
        ("128000", "128000"),
        ("128000", "0"),
        ("128000", "-2"),
        ("128000", "false"),
    ],
)
def test_invalid_context_limits_fail_before_any_source_or_model_read(
    tmp_path, monkeypatch, match_limit, material_limit
):
    from career_evidence_graph.career_portal_data import PortalDataError

    monkeypatch.setenv("TOMORROWSTAR_MATCH_CONTEXT_BYTES", match_limit)
    monkeypatch.setenv("TOMORROWSTAR_MATERIAL_CONTEXT_BYTES", material_limit)
    calls = []
    with pytest.raises(PortalDataError) as caught:
        material.prepare_material_packet(
            APPLICATION, career_facts(), tmp_path / "packet", runner=lambda *a, **k: calls.append(a)
        )
    assert caught.value.code == "match_context_limits_invalid"
    assert calls == []
    assert not (tmp_path / "packet").exists()


def test_explicit_small_context_budget_rejects_full_raw_range_without_truncation(
    tmp_path, monkeypatch
):
    from career_evidence_graph.career_portal_data import PortalDataError

    monkeypatch.setenv("TOMORROWSTAR_MATCH_CONTEXT_BYTES", "2000")
    monkeypatch.setenv("TOMORROWSTAR_MATERIAL_CONTEXT_BYTES", "1000")
    original = snapshot("I validated risk. " * 1000)
    before = deepcopy(original)
    calls = []
    with pytest.raises(PortalDataError) as caught:
        material.prepare_material_packet(
            APPLICATION,
            original,
            tmp_path / "packet",
            runner=lambda *a, **k: calls.append(a),
            requirements=REQUIREMENTS,
        )
    assert caught.value.code == "retrieval_execution_incomplete"
    assert calls == []
    saved = json.loads((tmp_path / "packet/input.json").read_text())
    assert saved["sources"]["source-0"]["text"] == before["items"][0]["text"]
    assert original == before


def test_explicit_large_context_reaches_matching_with_all_original_facts(tmp_path, monkeypatch):
    from test_application_match import model_output, model_runner

    from career_evidence_graph.application_match import analyze_job
    from career_evidence_graph.application_worker import digest

    monkeypatch.setenv("TOMORROWSTAR_MATCH_CONTEXT_BYTES", "384000")
    monkeypatch.setenv("TOMORROWSTAR_MATERIAL_CONTEXT_BYTES", "300000")
    original = career_facts(200)
    for row in original["items"]:
        row["text"] += " Complete experimental detail." * 20
    original["schemaVersion"] = 1
    original["revision"] = digest(
        {key: value for key, value in original.items() if key != "revision"}
    )
    prepared, _ = material.prepare_material_packet(
        APPLICATION,
        original,
        tmp_path / "packet",
        requirements=REQUIREMENTS,
        runner=lambda *a, **k: pytest.fail("The configured material budget fits all facts"),
    )
    output = model_output(prepared)
    output["requirements"][0]["claim_scope"] = "team"
    application = APPLICATION | {"id": "job-risk", "revision": "job-r1"}
    result = analyze_job(application, prepared, tmp_path / "match", runner=model_runner(output, []))
    coverage = json.loads((tmp_path / "match/context-coverage.json").read_text())
    assert coverage["context_limit_bytes"] == 384_000
    assert 128_000 < coverage["context_bytes"] <= 384_000
    assert coverage["truncated"] is False
    assert len(coverage["included_source_ids"]) == 200
    context = json.loads((tmp_path / "match/context-input.json").read_text())["prompt"].rsplit(
        "\n", 1
    )[1]
    grouped = json.loads(context)
    assert (
        len(grouped["sources"])
        + sum(
            len(row.get("facts", [])) + len(row.get("context", []))
            for row in grouped.get("experiences", [])
        )
        == 200
    )
    assert result["selected_source_ids"] == ["source-0"]


def test_explicit_reading_capacity_batches_all_supplied_fact_ids(tmp_path, monkeypatch):
    from test_application_material_packet import batch_reader

    monkeypatch.setenv("TOMORROWSTAR_MATCH_CONTEXT_BYTES", "384000")
    monkeypatch.setenv("TOMORROWSTAR_MATERIAL_CONTEXT_BYTES", "10000")
    original = career_facts(200)
    for row in original["items"]:
        row["text"] += " Complete experimental detail." * 20
    calls = []

    def empty_selection(output, context):
        output["selections"] = []

    _, packet = material.prepare_material_packet(
        APPLICATION,
        original,
        tmp_path / "packet",
        requirements=REQUIREMENTS,
        runner=batch_reader(calls, mutate=empty_selection),
    )
    assert len(calls) > 1
    assert all(0 < size <= 384_000 for _, size in calls)
    delivered = [
        row["source"]["source_id"] for context, _ in calls for row in context["source_ranges"]
    ]
    assert len(delivered) == len(set(delivered)) == 200
    assert set(delivered) == {row["source_id"] for row in original["items"]}
    assert len(packet["source_reads"]) == 200
    assert all(row["status"] == "complete" for row in packet["source_reads"].values())
    assert packet["sources"] == {}
