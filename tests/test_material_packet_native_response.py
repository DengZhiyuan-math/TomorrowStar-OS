"""Saved native reading results can finish their unpublished range receipts."""

import json
import subprocess
from copy import deepcopy

import pytest
from test_application_material_packet import many_small_sources, snapshot

from career_evidence_graph import application_material_packet as material
from career_evidence_graph.career_portal_data import PortalDataError
from career_evidence_graph.codex_cli import run_codex_exec

APPLICATION = {"company": "Example", "role_title": "Researcher", "job_description": "Risk."}
REQUIREMENTS = [{"text": "Validate risk", "importance": "required", "hard_condition": False}]


class InterruptedPublication(BaseException):
    pass


def native_reader(calls):
    """Exercise the actual CLI result constructor with an offline subprocess boundary."""

    def process(argv, **kwargs):
        if argv[-1] == "--version":
            return subprocess.CompletedProcess(argv, 0, "codex synthetic-offline", "")
        context = json.loads(kwargs["input"].split("CONTEXT_JSON\n", 1)[1])
        calls.append(context)
        selections = []
        for row in context.get("source_ranges", [context]):
            if "spans" in row:
                selections.extend(
                    {"span_id": span["span_id"], "requirement_indexes": [0]}
                    for span in row["spans"]
                    if "validated risk" in span["text"]
                )
            elif "validated risk" in row["text"]:
                selections.append(
                    {"source_id": row["source"]["source_id"], "requirement_indexes": [0]}
                )
        output = {"selections": selections}
        return subprocess.CompletedProcess(
            argv, 0, json.dumps({"type": "structured_result", "result": output}) + "\n", ""
        )

    def read(config, prompt, **kwargs):
        return run_codex_exec(config, prompt, runner=process, **kwargs)

    return read


def test_many_complete_sources_bound_selection_output_and_keep_complete_coverage(
    tmp_path, monkeypatch
):
    original = snapshot(
        "An unrelated source.", *(f"I validated risk. Source {i}." for i in range(64))
    )
    source_bytes = material._size(material._sources(original))
    monkeypatch.setenv("TOMORROWSTAR_MATERIAL_CONTEXT_BYTES", str(source_bytes - 1))
    calls = []
    _, packet = material.prepare_material_packet(
        APPLICATION,
        original,
        tmp_path / "bounded-output",
        runner=native_reader(calls),
        requirements=REQUIREMENTS,
    )
    batches = [context.get("source_ranges", [context]) for context in calls]
    assert [len(batch) for batch in batches] == [32, 32, 1]
    assert {row["source"]["source_id"] for batch in batches for row in batch} == {
        row["source_id"] for row in original["items"]
    }
    assert len(packet["source_reads"]) == 65
    assert all(row["status"] == "complete" for row in packet["source_reads"].values())
    assert len(packet["sources"]) == 64
    for source in original["items"][1:]:
        assert packet["sources"][source["source_id"]]["text"] == source["text"]


def stopped_attempt(tmp_path, monkeypatch):
    original = many_small_sources()
    first = tmp_path / "first"
    write = material.helper.atomic_write_json
    calls = []

    def interrupt(path, value):
        write(path, value)
        if path.name == "result.json":
            raise InterruptedPublication

    with monkeypatch.context() as patch:
        patch.setattr(material.helper, "atomic_write_json", interrupt)
        with pytest.raises(InterruptedPublication):
            material.prepare_material_packet(
                APPLICATION, original, first, runner=native_reader(calls), requirements=REQUIREMENTS
            )
    assert len(calls) == 1
    return original, first


def test_native_result_saved_before_publication_resumes_without_another_call(tmp_path, monkeypatch):
    original, first = stopped_attempt(tmp_path, monkeypatch)
    preserved = {path: path.read_bytes() for path in first.rglob("*") if path.is_file()}
    calls = []
    _, packet = material.prepare_material_packet(
        APPLICATION,
        original,
        tmp_path / "resumed",
        runner=native_reader(calls),
        requirements=REQUIREMENTS,
        resume_from=first,
    )
    assert calls == []
    assert packet["status"] == "complete"
    assert "pending_call" not in packet
    assert all(row["status"] == "complete" for row in packet["source_reads"].values())
    selected = original["items"][-1]
    assert packet["sources"][selected["source_id"]]["text"] == selected["text"]
    assert all(path.read_bytes() == value for path, value in preserved.items())


def test_saved_final_long_source_page_reuses_all_published_ranges(tmp_path, monkeypatch):
    text = "Unrelated details. " * 5_000 + "\n\nI validated risk.\n"
    original = snapshot(text)
    first = tmp_path / "first"
    write = material.helper.atomic_write_json
    calls = []

    def interrupt(path, value):
        write(path, value)
        if path.name == "result.json":
            context = json.loads(path.with_name("context.json").read_text())
            if context["range"]["end"] == len(text):
                raise InterruptedPublication

    with monkeypatch.context() as patch:
        patch.setattr(material.helper, "atomic_write_json", interrupt)
        with pytest.raises(InterruptedPublication):
            material.prepare_material_packet(
                APPLICATION, original, first, runner=native_reader(calls), requirements=REQUIREMENTS
            )
    assert len(calls) > 1
    saved = json.loads((first / "material-packet.json").read_text())
    completed_ranges = saved["source_reads"]["source-0"]["ranges"]
    assert completed_ranges
    resumed_calls = []
    _, packet = material.prepare_material_packet(
        APPLICATION,
        original,
        tmp_path / "resumed",
        runner=native_reader(resumed_calls),
        requirements=REQUIREMENTS,
        resume_from=first,
    )
    assert resumed_calls == []
    assert packet["status"] == "complete"
    assert packet["source_reads"]["source-0"]["ranges"][:-1] == completed_ranges
    assert packet["sources"]["source-0"]["text"].strip() == "I validated risk."


@pytest.mark.parametrize(
    "mutation",
    [
        "missing",
        "prompt",
        "schema",
        "source",
        "scope",
        "selection",
        "raw",
        "requirement",
        "business",
        "duplicate",
        "context",
        "source_metadata",
        "symlink",
    ],
)
def test_unverified_native_results_remain_stopped(tmp_path, monkeypatch, mutation):
    original, first = stopped_attempt(tmp_path, monkeypatch)
    result_path = next(first.glob("source-*/result.json"))
    if mutation == "missing":
        result_path.unlink()
    elif mutation == "symlink":
        target = tmp_path / "detached-result.json"
        result_path.rename(target)
        result_path.symlink_to(target)
    elif mutation in {"prompt", "schema"}:
        path = result_path.with_name(f"{mutation}.json")
        path.write_text(path.read_text() + " ")
        if mutation == "prompt":
            value = json.loads(path.read_text())
            value["prompt"] += "changed"
            path.write_text(json.dumps(value))
    elif mutation == "source":
        original = deepcopy(original)
        original["items"][0]["text"] += " Changed."
    elif mutation == "source_metadata":
        original = deepcopy(original)
        original["items"][0]["boundaries"].append("Changed responsibility.")
    elif mutation == "context":
        path = result_path.with_name("context.json")
        value = json.loads(path.read_text())
        value["job"]["role_title"] = "Different"
        path.write_text(json.dumps(value))
    elif mutation == "scope":
        original = deepcopy(original)
        original["match_requirements"] = REQUIREMENTS + [{"text": "Different"}]
    else:
        value = json.loads(result_path.read_text())
        selection = value["structured_result"]["selections"][0]
        if mutation == "raw":
            value["raw_stdout_jsonl"] = json.dumps(
                {"type": "structured_result", "result": {"selections": []}}
            )
        else:
            if mutation == "selection":
                selection["source_id"] = "unsupplied"
            elif mutation == "requirement":
                selection["requirement_indexes"] = [1]
            elif mutation == "business":
                selection.update(requirement_indexes=[], business_relevance=True)
            elif mutation == "duplicate":
                value["structured_result"]["selections"].append(deepcopy(selection))
            value["raw_stdout_jsonl"] = json.dumps(
                {"type": "structured_result", "result": value["structured_result"]}
            )
        result_path.write_text(json.dumps(value))
    calls = []
    with pytest.raises(PortalDataError) as caught:
        material.prepare_material_packet(
            APPLICATION,
            original,
            tmp_path / "resumed",
            runner=native_reader(calls),
            requirements=original.get("match_requirements", REQUIREMENTS),
            resume_from=first,
        )
    assert caught.value.code == "match_result_needs_recheck"
    assert calls == []
