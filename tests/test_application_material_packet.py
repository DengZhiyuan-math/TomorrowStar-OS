"""Complete UTF-8 source reading and immutable literal evidence packet regressions."""

import json
from copy import deepcopy
from types import SimpleNamespace

import pytest

from career_evidence_graph import application_material_packet as material
from career_evidence_graph.application_worker import digest
from career_evidence_graph.career_portal_data import PortalDataError

pytestmark = pytest.mark.usefixtures("reading_limits")


@pytest.fixture
def application():
    return {"company": "Example", "role_title": "Researcher", "job_description": "Validate risk."}


@pytest.fixture
def requirements():
    return [{"text": "Validate risk", "importance": "required", "hard_condition": False}]


def snapshot(*texts):
    return {
        "revision": "snapshot-r1",
        "coverage": {"truncated": False},
        "documents": [
            {"id": f"doc-{number}", "revision": f"r-{number}", "available": True}
            for number, _ in enumerate(texts)
        ],
        "items": [
            {
                "source_id": f"source-{number}",
                "source_revision": f"r-{number}",
                "source_name": f"source-{number}.md",
                "evidence_id": f"doc-{number}",
                "locator": f"lines-{number}",
                "document_locator": f"lines-{number}",
                "resume_eligible": True,
                "attribution": "User implemented; team reviewed",
                "boundaries": ["No production trading"],
                "text": text,
            }
            for number, text in enumerate(texts)
        ],
    }


def reader(calls, select="validated risk", mutate=None):
    def run(config, prompt, **kwargs):
        context = json.loads(prompt.split("CONTEXT_JSON\n", 1)[1])
        calls.append(context)
        rows = [
            {"span_id": span["span_id"], "requirement_indexes": [0]}
            for span in context["spans"]
            if select in span["text"]
        ]
        output = {"selections": rows}
        if mutate:
            mutate(output, context)
        return SimpleNamespace(
            structured_result=output,
            model_dump=lambda **_: {"status": "completed", "structured_result": output},
        )

    return run


def test_small_sources_are_delivered_in_full_without_another_call(
    tmp_path, application, requirements
):
    original = snapshot("I validated risk. Team reviewed it.", "I teach numerical methods.")
    calls = []
    prepared, packet = material.prepare_material_packet(
        application, original, tmp_path / "packet", runner=reader(calls), requirements=requirements
    )
    assert calls == []
    assert packet["status"] == "complete"
    assert packet["revision"] == digest(
        {key: value for key, value in packet.items() if key != "revision"}
    )
    assert packet["sources"]["source-0"]["text"] == original["items"][0]["text"]
    assert packet["source_reads"]["source-0"]["ranges"][0]["method"] == "complete_source"
    assert prepared["material_packet_sources"] == packet["sources"]
    assert "material_packet" not in original
    assert json.loads((tmp_path / "packet/material-packet.json").read_text()) == packet


def long_text():
    return (
        ("Unrelated context. " * 20 + "\n\n") * 100
        + "I have not validated risk in production.\n\n"
        + ("旧资料。" * 20 + "\n\n") * 100
    )


def test_long_source_all_ranges_read_and_relevant_sentence_preserves_limits(
    tmp_path, application, requirements
):
    original = snapshot(long_text())
    calls = []
    prepared, packet = material.prepare_material_packet(
        application,
        original,
        tmp_path / "packet",
        runner=reader(calls),
        requirements=requirements,
        job_brief={"revision": "fixed-brief", "business_object": "Risk decisions"},
    )
    source = packet["sources"]["source-0"]
    assert source["text"].strip() == "I have not validated risk in production."
    assert source["attribution"] == original["items"][0]["attribution"]
    assert source["source_revision"] == "r-0"
    assert len(calls) > 1
    assert all(
        sum(len(span["text"].encode()) for span in call["spans"]) <= material.MAX_CHUNK_BYTES
        for call in calls
    )
    assert all(call["job_brief"]["revision"] == "fixed-brief" for call in calls)
    ranges = packet["source_reads"]["source-0"]["ranges"]
    assert ranges[0]["start"] == 0
    assert ranges[-1]["end"] == len(original["items"][0]["text"])
    assert all(
        right["start"] < left["end"] for left, right in zip(ranges, ranges[1:], strict=False)
    )
    part = source["quote_segments"][0]
    assert original["items"][0]["text"][part["source_start"] : part["source_end"]] == part["text"]
    assert prepared["material_packet"] == packet


def test_irrelevant_range_remains_covered_and_is_not_a_capability_judgment(
    tmp_path, application, requirements
):
    calls = []
    _, packet = material.prepare_material_packet(
        application,
        snapshot("Unrelated.\n" * 8_000),
        tmp_path / "packet",
        runner=reader(calls),
        requirements=requirements,
    )
    assert packet["sources"] == {}
    assert packet["source_reads"]["source-0"]["status"] == "complete"
    assert all(page["excerpts"] == [] for page in packet["source_reads"]["source-0"]["ranges"])
    assert "judgment" not in json.dumps(packet)


@pytest.mark.parametrize("mutation", ["source", "quote", "range", "requirement", "schema"])
def test_invalid_excerpt_fails_with_retained_result_no_retry(
    tmp_path, application, requirements, mutation
):
    def mutate(output, context):
        output["selections"] = [
            {"span_id": context["spans"][0]["span_id"], "requirement_indexes": [0]}
        ]
        row = output["selections"][0]
        if mutation == "source":
            row["span_id"] = "unprovided"
        elif mutation == "quote":
            row["quote"] = "invented quote"
        elif mutation == "range":
            row["end"] = len(long_text()) + 1
        elif mutation == "requirement":
            row["requirement_indexes"] = [True]
        else:
            output["score"] = 100

    calls = []
    directory = tmp_path / "packet"
    with pytest.raises(PortalDataError) as caught:
        material.prepare_material_packet(
            application,
            snapshot(long_text()),
            directory,
            runner=reader(calls, mutate=mutate),
            requirements=requirements,
        )
    assert caught.value.code == "retrieval_execution_incomplete"
    assert len(calls) == 1
    assert json.loads((directory / "material-packet.json").read_text())["status"] == "failed"
    assert (
        json.loads(next(directory.glob("source-*/result.json")).read_text())["status"]
        == "completed"
    )
    with pytest.raises(PortalDataError):
        material.prepare_material_packet(
            application,
            snapshot(long_text()),
            directory,
            runner=reader(calls),
            requirements=requirements,
        )
    assert len(calls) == 1


def test_runner_failure_preserves_successful_ranges_without_retry(
    tmp_path, application, requirements
):
    calls = []
    good = reader(calls)

    def fail_second(*args, **kwargs):
        if calls:
            raise OSError("synthetic unavailable")
        return good(*args, **kwargs)

    directory = tmp_path / "packet"
    with pytest.raises(PortalDataError) as caught:
        material.prepare_material_packet(
            application,
            snapshot(long_text()),
            directory,
            runner=fail_second,
            requirements=requirements,
        )
    assert caught.value.code == "retrieval_execution_incomplete"
    packet = json.loads((directory / "material-packet.json").read_text())
    assert packet["status"] == "failed"
    assert len(packet["source_reads"]["source-0"]["ranges"]) == 1
    assert len(list(directory.glob("source-*/result.json"))) == 2


def test_previous_identical_source_read_is_reused_but_new_content_is_not(
    tmp_path, application, requirements
):
    calls = []
    original = snapshot(long_text())
    _, first = material.prepare_material_packet(
        application, original, tmp_path / "first", runner=reader(calls), requirements=requirements
    )
    count = len(calls)
    _, second = material.prepare_material_packet(
        application,
        original,
        tmp_path / "second",
        runner=reader(calls),
        requirements=requirements,
        previous=first,
    )
    assert len(calls) == count
    assert second["source_reads"]["source-0"]["reused"] is True
    changed = deepcopy(original)
    changed["items"][0]["text"] += "Changed context."
    material.prepare_material_packet(
        application,
        changed,
        tmp_path / "third",
        runner=reader(calls),
        requirements=requirements,
        previous=first,
    )
    assert len(calls) > count


def test_changed_requirement_cannot_reuse_a_prior_reading(tmp_path, application, requirements):
    calls = []
    original = snapshot(long_text())
    _, first = material.prepare_material_packet(
        application, original, tmp_path / "first", runner=reader(calls), requirements=requirements
    )
    count = len(calls)
    changed = requirements + [{"text": "Teach", "importance": "preferred", "hard_condition": False}]
    material.prepare_material_packet(
        application,
        original,
        tmp_path / "second",
        runner=reader(calls),
        requirements=changed,
        previous=first,
    )
    assert len(calls) > count


def test_all_relevant_text_too_large_is_explicit_failure(tmp_path, application, requirements):
    calls = []

    def entire(output, context):
        output["selections"] = [
            {"span_id": span["span_id"], "requirement_indexes": [0]} for span in context["spans"]
        ]

    directory = tmp_path / "packet"
    with pytest.raises(PortalDataError) as caught:
        material.prepare_material_packet(
            application,
            snapshot(long_text()),
            directory,
            runner=reader(calls, mutate=entire),
            requirements=requirements,
        )
    assert caught.value.code == "retrieval_execution_incomplete"
    packet = json.loads((directory / "material-packet.json").read_text())
    assert packet["source_reads"]["source-0"]["status"] == "complete"
    assert packet["status"] == "failed"


def test_confirmed_information_never_truncated_or_sent_to_excerpt_reader(
    tmp_path, application, requirements
):
    original = snapshot("Fact." * 20_000)
    original["items"][0]["source_kind"] = "confirmed_information"
    original["items"][0]["confirmed_information"] = {"fact": "language"}
    calls = []
    with pytest.raises(PortalDataError) as caught:
        material.prepare_material_packet(
            application,
            original,
            tmp_path / "packet",
            runner=reader(calls),
            requirements=requirements,
        )
    assert caught.value.code == "match_information_too_large"
    assert calls == []


def test_noncontiguous_fragments_cannot_be_quoted_as_one_field(tmp_path, application, requirements):
    from career_evidence_graph.application_match import _quoted_source

    text = (
        "I validated risk.\n\n" + ("Unrelated. " * 20 + "\n\n") * 400 + "I validated risk again.\n"
    )
    _, packet = material.prepare_material_packet(
        application,
        snapshot(text),
        tmp_path / "packet",
        runner=reader([]),
        requirements=requirements,
    )
    source = packet["sources"]["source-0"]
    assert len(source["quote_segments"]) == 2
    with pytest.raises(PortalDataError) as caught:
        _quoted_source(source, source["text"])
    assert caught.value.code == "match_source_invalid"


def test_symlink_directory_does_not_write_or_call(tmp_path, application, requirements):
    real = tmp_path / "real"
    real.mkdir()
    linked = tmp_path / "linked"
    linked.symlink_to(real, target_is_directory=True)
    calls = []
    with pytest.raises(PortalDataError):
        material.prepare_material_packet(
            application,
            snapshot("Text"),
            linked / "packet",
            runner=reader(calls),
            requirements=requirements,
        )
    assert calls == []
    assert list(real.iterdir()) == []


def test_business_only_tail_is_preserved_and_reusable(tmp_path, application, requirements):
    text = ("Unrelated. " * 20 + "\n\n") * 400 + "I improved portfolio decisions for the team.\n"
    original = snapshot(text)
    calls = []

    def business_only(output, context):
        for row in output["selections"]:
            row.update(requirement_indexes=[], business_relevance=True)

    run = reader(calls, select="improved portfolio decisions", mutate=business_only)
    brief = {
        "revision": "business-brief",
        "business_object": "Investment portfolios",
        "role_understanding": {
            "business_objective": "Improve portfolio decisions",
            "work_outputs": ["Portfolio recommendations"],
        },
    }
    _, packet = material.prepare_material_packet(
        application,
        original,
        tmp_path / "first",
        runner=run,
        requirements=requirements,
        job_brief=brief,
    )
    assert packet["sources"]["source-0"]["text"].strip() == (
        "I improved portfolio decisions for the team."
    )
    excerpts = [
        row for page in packet["source_reads"]["source-0"]["ranges"] for row in page["excerpts"]
    ]
    assert all(row["requirement_indexes"] == [] and row["business_relevance"] for row in excerpts)
    count = len(calls)
    _, second = material.prepare_material_packet(
        application,
        original,
        tmp_path / "second",
        runner=run,
        requirements=requirements,
        job_brief=brief,
        previous=packet,
    )
    assert len(calls) == count
    assert second["source_reads"]["source-0"]["reused"] is True


@pytest.mark.parametrize(
    "business_flag,objective", [(False, "Risk decisions"), (True, ""), (True, None)]
)
def test_empty_requirement_indexes_need_explicit_business_scope(
    tmp_path, application, requirements, business_flag, objective
):
    def unrelated(output, context):
        output["selections"] = [
            {
                "span_id": context["spans"][0]["span_id"],
                "requirement_indexes": [],
                "business_relevance": business_flag,
            }
        ]

    with pytest.raises(PortalDataError) as caught:
        material.prepare_material_packet(
            application,
            snapshot(long_text()),
            tmp_path / "packet",
            runner=reader([], mutate=unrelated),
            requirements=requirements,
            job_brief={
                "revision": "fixed",
                "role_understanding": {"business_objective": objective},
            },
        )
    assert caught.value.code == "retrieval_execution_incomplete"


@pytest.mark.parametrize(
    "declared",
    [
        {"truncated": True},
        {"omitted_source_ids": ["unprovided-source"]},
        {"truncated_sources": [{"source_id": "source-0", "omitted_range": {"start": 4, "end": 8}}]},
        {"unread_ranges": [{"start": 4, "end": 8}]},
        {"unread_source_ranges": [{"source_id": "source-0", "start": 4, "end": 8}]},
        {"unread_sources": ["source-0"]},
    ],
)
def test_incomplete_input_coverage_cannot_be_relabelled_complete(
    tmp_path, application, requirements, declared
):
    original = snapshot("Only the visible prefix.")
    original["coverage"].update(declared)
    directory = tmp_path / "packet"
    calls = []
    with pytest.raises(PortalDataError) as caught:
        material.prepare_material_packet(
            application, original, directory, runner=reader(calls), requirements=requirements
        )
    assert caught.value.code == "retrieval_execution_incomplete"
    assert calls == []
    packet = json.loads((directory / "material-packet.json").read_text())
    assert packet["status"] == "failed"
    assert packet["input_coverage"] == original["coverage"]
    assert packet["sources"] == {}


@pytest.mark.parametrize(
    "metadata",
    [
        {"original_text_chars": 100},
        {"context_range": {"start": 5, "end": 29}},
    ],
)
def test_declared_partial_source_cannot_be_scanned_as_complete(
    tmp_path, application, requirements, metadata
):
    original = snapshot("Only the visible prefix.")
    original["items"][0].update(metadata)
    calls = []
    with pytest.raises(PortalDataError) as caught:
        material.prepare_material_packet(
            application,
            original,
            tmp_path / "packet",
            runner=reader(calls),
            requirements=requirements,
        )
    assert caught.value.code == "retrieval_execution_incomplete"
    assert calls == []


def batch_reader(calls, mutate=None):
    def run(config, prompt, **kwargs):
        context = json.loads(prompt.split("CONTEXT_JSON\n", 1)[1])
        calls.append((context, len(prompt.encode())))
        rows = []
        for supplied in context.get("source_ranges", [context]):
            if "spans" in supplied:
                rows.extend(
                    {"span_id": span["span_id"], "requirement_indexes": [0]}
                    for span in supplied["spans"]
                    if "validated risk" in span["text"]
                )
            elif "validated risk" in supplied["text"]:
                rows.append(
                    {"source_id": supplied["source"]["source_id"], "requirement_indexes": [0]}
                )
        output = {"selections": rows}
        if mutate:
            mutate(output, context)
        return SimpleNamespace(
            structured_result=output,
            model_dump=lambda **_: {"status": "completed", "structured_result": output},
        )

    return run


def many_small_sources():
    return snapshot(
        *(f"Source {number}. " + "Irrelevant detail. " * 220 for number in range(20)),
        "I validated risk. Team reviewed it.",
    )


def test_small_source_excerpts_batch_with_fixed_scope_and_complete_attribution(
    tmp_path, application, requirements, monkeypatch
):
    monkeypatch.setattr(material, "MAX_READING_PROMPT_BYTES", 18_000)
    original = many_small_sources()
    calls = []
    _, packet = material.prepare_material_packet(
        application,
        original,
        tmp_path / "packet",
        runner=batch_reader(calls),
        requirements=requirements,
        job_brief={"revision": "fixed-brief"},
    )
    assert 1 < len(calls) < len(original["items"]) // 2
    assert all(size <= material.MAX_READING_PROMPT_BYTES for _, size in calls)
    supplied = [
        source for context, _ in calls for source in context.get("source_ranges", [context])
    ]
    assert [row["source"]["source_id"] for row in supplied] == [
        row["source_id"] for row in original["items"]
    ]
    assert all(context["job_brief"] == {"revision": "fixed-brief"} for context, _ in calls)
    assert all(context["requirements"] == requirements for context, _ in calls)
    for row, item in zip(supplied, original["items"], strict=True):
        assert row["text"] == item["text"]
        assert row["range"]["start"] == 0
        assert row["range"]["end"] == len(item["text"])
        assert row["source"]["attribution"] == item["attribution"]
        assert row["source"]["boundaries"] == item["boundaries"]
    assert list(packet["sources"]) == ["source-20"]
    assert packet["sources"]["source-20"]["text"] == original["items"][20]["text"]
    assert all(row["status"] == "complete" for row in packet["source_reads"].values())


def test_batched_source_selection_cannot_name_an_unsupplied_source(
    tmp_path, application, requirements
):
    def corrupt(output, context):
        assert "source_ranges" in context
        output["selections"][0]["source_id"] = "not-supplied"

    with pytest.raises(PortalDataError) as caught:
        material.prepare_material_packet(
            application,
            many_small_sources(),
            tmp_path / "packet",
            runner=batch_reader([], mutate=corrupt),
            requirements=requirements,
        )
    assert caught.value.code == "retrieval_execution_incomplete"
    assert json.loads((tmp_path / "packet/material-packet.json").read_text())["status"] == "failed"


def test_unavailable_nonempty_source_stops_before_batch_calls(tmp_path, application, requirements):
    original = many_small_sources()
    original["documents"][-1]["available"] = False
    calls = []
    with pytest.raises(PortalDataError) as caught:
        material.prepare_material_packet(
            application,
            original,
            tmp_path / "packet",
            runner=batch_reader(calls),
            requirements=requirements,
        )
    assert caught.value.code == "retrieval_execution_incomplete"
    assert calls == []


def test_completed_batches_are_reused_after_later_batch_failure(
    tmp_path, application, requirements, monkeypatch
):
    monkeypatch.setattr(material, "MAX_READING_PROMPT_BYTES", 18_000)
    original = many_small_sources()
    calls = []
    good = batch_reader(calls)

    def fail_second(*args, **kwargs):
        if calls:
            raise OSError("synthetic batch failure")
        return good(*args, **kwargs)

    with pytest.raises(PortalDataError):
        material.prepare_material_packet(
            application,
            original,
            tmp_path / "first",
            runner=fail_second,
            requirements=requirements,
        )
    first = json.loads((tmp_path / "first/material-packet.json").read_text())
    complete = {key for key, row in first["source_reads"].items() if row["status"] == "complete"}
    assert len(complete) > 1
    retry_calls = []
    _, second = material.prepare_material_packet(
        application,
        original,
        tmp_path / "next",
        runner=batch_reader(retry_calls),
        requirements=requirements,
        previous=first,
    )
    reread = {
        row["source"]["source_id"]
        for context, _ in retry_calls
        for row in context.get("source_ranges", [context])
    }
    assert reread == set(first["source_reads"]) - complete
    assert all(second["source_reads"][key]["reused"] for key in complete)


def test_fixed_scope_over_reading_budget_stops_without_truncation_or_calls(
    tmp_path, application, requirements, monkeypatch
):
    monkeypatch.setattr(material, "MAX_READING_PROMPT_BYTES", 2_000)
    original = many_small_sources()
    calls = []
    with pytest.raises(PortalDataError) as caught:
        material.prepare_material_packet(
            application,
            original,
            tmp_path / "packet",
            runner=batch_reader(calls),
            requirements=requirements,
            job_brief={"revision": "fixed-brief", "business_object": "Complete scope. " * 300},
        )
    assert caught.value.code == "retrieval_execution_incomplete"
    assert calls == []
    packet = json.loads((tmp_path / "packet/material-packet.json").read_text())
    assert packet["status"] == "failed"
    assert packet["sources"] == {}
    assert all(row["status"] == "reading" for row in packet["source_reads"].values())


@pytest.mark.parametrize(
    "indexes,business,valid", [([0], False, True), ([], True, True), ([], False, False)]
)
def test_provider_schema_requires_explicit_contextual_relevance(
    tmp_path, application, requirements, indexes, business, valid
):
    def contextual_limit(output, context):
        for row in output["selections"]:
            row.update(requirement_indexes=indexes, business_relevance=business)

    read = reader([], mutate=contextual_limit)

    def schema_bound(config, prompt, **kwargs):
        schema = json.loads(config.output_schema.read_text())
        assert schema["$defs"]["_SpanSelection"].get("anyOf") == [
            {
                "properties": {"requirement_indexes": {"minItems": 1}},
                "required": ["requirement_indexes"],
            },
            {
                "properties": {"business_relevance": {"const": True}},
                "required": ["business_relevance"],
            },
        ]
        assert "Contextual limits must use the requirement_indexes" in prompt
        assert "Never return empty requirement_indexes with business_relevance=false" in prompt
        return read(config, prompt, **kwargs)

    arguments = {
        "runner": schema_bound,
        "requirements": requirements,
        "job_brief": {
            "revision": "fixed",
            "role_understanding": {"business_objective": "Risk decisions"},
        },
    }
    if valid:
        _, packet = material.prepare_material_packet(
            application, snapshot(long_text()), tmp_path / "packet", **arguments
        )
        assert packet["status"] == "complete"
    else:
        with pytest.raises(PortalDataError) as caught:
            material.prepare_material_packet(
                application, snapshot(long_text()), tmp_path / "packet", **arguments
            )
        assert caught.value.code == "retrieval_execution_incomplete"


def field_source(separator="\n \t"):
    original = many_small_sources()
    first, second = "Original raw detail. " * 500 + "I validated risk.", "No production trading."
    item = original["items"][-1]
    item["text"] = first + separator + second
    item["quote_segments"] = [
        {"start": 0, "end": len(first), "document_locator": "$.first"},
        {
            "start": len(first + separator),
            "end": len(item["text"]),
            "document_locator": "$.second",
        },
    ]
    return original


def whole_field_reader(original, calls, mutate=None):
    item = original["items"][-1]

    def whole(output, context):
        if "spans" in context and context["source"]["source_id"] == item["source_id"]:
            output["selections"] = [
                {
                    "span_id": span["span_id"],
                    "requirement_indexes": [0],
                    "business_relevance": False,
                }
                for span in context["spans"]
            ]
            if mutate:
                mutate(output["selections"][0])

    return batch_reader(calls, mutate=whole)


def test_native_field_receipts_preserve_raw_selection_and_original_offsets(
    tmp_path, application, requirements
):
    original = field_source()
    item = original["items"][-1]
    _, packet = material.prepare_material_packet(
        application,
        original,
        tmp_path / "packet",
        runner=whole_field_reader(original, []),
        requirements=requirements,
    )
    excerpts = packet["source_reads"][item["source_id"]]["ranges"][0]["excerpts"]
    assert len(excerpts) == 2
    for excerpt, field in zip(excerpts, item["quote_segments"], strict=True):
        assert excerpt == {
            "source_id": item["source_id"],
            "quote": item["text"][field["start"] : field["end"]],
            "start": field["start"],
            "end": field["end"],
            "requirement_indexes": [0],
            "business_relevance": False,
        }
    assert packet["sources"][item["source_id"]]["text"] == "\n".join(
        item["text"][field["start"] : field["end"]] for field in item["quote_segments"]
    )
    raw = next(
        data
        for path in (tmp_path / "packet").glob("source-*/result.json")
        if (data := json.loads(path.read_text()))["structured_result"].get("selections")
    )
    assert len(raw["structured_result"]["selections"]) == 2
    assert all(
        "quote" not in row and "start" not in row and "end" not in row
        for row in raw["structured_result"]["selections"]
    )


@pytest.mark.parametrize("invalid", ["source", "quote", "offset", "gap", "overlap"])
def test_field_split_does_not_repair_invalid_fresh_evidence(
    tmp_path, application, requirements, invalid
):
    original = field_source(separator="MISSING" if invalid == "gap" else "\n \t")
    if invalid == "overlap":
        fields = original["items"][-1]["quote_segments"]
        fields[0]["end"] = fields[1]["start"] + 1

    def corrupt(row):
        if invalid == "source":
            row["span_id"] = "not-supplied"
        elif invalid == "quote":
            row["quote"] += "Fabricated."
        elif invalid == "offset":
            row.update(start=1, end=2)

    with pytest.raises(PortalDataError) as caught:
        material.prepare_material_packet(
            application,
            original,
            tmp_path / "packet",
            runner=whole_field_reader(original, [], mutate=corrupt),
            requirements=requirements,
        )
    assert caught.value.code == "retrieval_execution_incomplete"
    assert json.loads((tmp_path / "packet/material-packet.json").read_text())["status"] == "failed"


@pytest.mark.parametrize("forgery", ["cross_field", "offset"])
def test_persisted_forgery_cannot_use_fresh_model_native_binding(
    tmp_path, application, requirements, forgery
):
    original = field_source()
    item = original["items"][-1]
    _, first = material.prepare_material_packet(
        application,
        original,
        tmp_path / "first",
        runner=whole_field_reader(original, []),
        requirements=requirements,
    )
    if forgery == "offset":
        first["source_reads"][item["source_id"]]["ranges"][0]["excerpts"][0]["end"] -= 1
    else:
        first["source_reads"][item["source_id"]]["ranges"][0]["excerpts"] = [
            {
                "source_id": item["source_id"],
                "quote": item["text"],
                "start": 0,
                "end": len(item["text"]),
                "requirement_indexes": [0],
                "business_relevance": False,
            }
        ]
    first["revision"] = digest({key: value for key, value in first.items() if key != "revision"})
    calls = []
    _, second = material.prepare_material_packet(
        application,
        original,
        tmp_path / "second",
        runner=whole_field_reader(original, calls),
        requirements=requirements,
        previous=first,
    )
    assert len(calls) == 1
    assert "reused" not in second["source_reads"][item["source_id"]]
    assert len(second["source_reads"][item["source_id"]]["ranges"][0]["excerpts"]) == 2


@pytest.mark.parametrize("business_only", [False, True])
def test_small_tex_sources_select_ids_and_preserve_complete_original_fields(
    tmp_path, application, requirements, business_only
):
    original = many_small_sources()
    item = original["items"][-1]
    first = r"\item \textbf{Scientific computing:} I validated risk."
    second = r"\item No production trading; further work is planned."
    item["text"] = first + "\n" + second
    item["quote_segments"] = [
        {"start": 0, "end": len(first), "document_locator": "$.first"},
        {"start": len(first) + 1, "end": len(item["text"]), "document_locator": "$.second"},
    ]
    selection = {
        "source_id": item["source_id"],
        "requirement_indexes": [] if business_only else [0],
        "business_relevance": business_only,
    }

    def select(config, prompt, **kwargs):
        schema = json.loads(config.output_schema.read_text())
        assert set(schema["properties"]) == {"selections"}
        fields = schema["$defs"]["_SourceSelection"]["properties"]
        assert set(fields) == {"source_id", "requirement_indexes", "business_relevance"}
        assert fields["source_id"]["enum"] == [row["source_id"] for row in original["items"]]
        assert fields["requirement_indexes"]["items"]["enum"] == [0]
        assert "Do not copy text or calculate character positions" in prompt
        output = {"selections": [selection]}
        return SimpleNamespace(
            structured_result=output,
            model_dump=lambda **_: {"status": "completed", "structured_result": output},
        )

    _, packet = material.prepare_material_packet(
        application,
        original,
        tmp_path / "packet",
        runner=select,
        requirements=requirements,
        job_brief={"role_understanding": {"business_objective": "Risk decisions"}},
    )
    assert packet["sources"][item["source_id"]]["text"] == item["text"]
    assert packet["sources"][item["source_id"]]["quote_segments"] == item["quote_segments"]
    rows = packet["source_reads"][item["source_id"]]["ranges"][0]["excerpts"]
    assert [row["quote"] for row in rows] == [first, second]
    assert all(row["requirement_indexes"] == selection["requirement_indexes"] for row in rows)
    assert all(row["business_relevance"] == business_only for row in rows)
    assert all(row["status"] == "complete" for row in packet["source_reads"].values())
    assert all(
        row["ranges"][0]["excerpts"] == []
        for source_id, row in packet["source_reads"].items()
        if source_id != item["source_id"]
    )
    raw = json.loads(next((tmp_path / "packet").glob("source-*/result.json")).read_text())
    assert raw["structured_result"] == {"selections": [selection]}


@pytest.mark.parametrize("invalid", ["source", "unbound", "quote", "requirement"])
def test_small_source_selection_rejects_unknown_or_unbound_output(
    tmp_path, application, requirements, invalid
):
    def select(config, prompt, **kwargs):
        row = {"source_id": "source-20", "requirement_indexes": [0], "business_relevance": False}
        if invalid == "source":
            row["source_id"] = "unknown-source"
        elif invalid == "unbound":
            row["requirement_indexes"] = []
        elif invalid == "requirement":
            row["requirement_indexes"] = [1]
        else:
            row["quote"] = "Rendered text is unnecessary."
        output = {"selections": [row]}
        return SimpleNamespace(
            structured_result=output,
            model_dump=lambda **_: {"status": "completed", "structured_result": output},
        )

    with pytest.raises(PortalDataError) as caught:
        material.prepare_material_packet(
            application,
            many_small_sources(),
            tmp_path / "packet",
            runner=select,
            requirements=requirements,
        )
    assert caught.value.code == "retrieval_execution_incomplete"


def span_reader(calls, choose=None):
    def run(config, prompt, **kwargs):
        context = json.loads(prompt.split("CONTEXT_JSON\n", 1)[1])
        calls.append(context)
        schema = json.loads(config.output_schema.read_text())
        fields = schema["$defs"]["_SpanSelection"]["properties"]
        assert set(fields) == {"span_id", "requirement_indexes", "business_relevance"}
        assert fields["span_id"]["enum"] == [row["span_id"] for row in context["spans"]]
        assert fields["requirement_indexes"]["items"]["enum"] == [0]
        assert "text" not in context
        rows = choose(context) if choose else []
        output = {"selections": rows}
        return SimpleNamespace(
            structured_result=output,
            model_dump=lambda **_: {"status": "completed", "structured_result": output},
        )

    return run


def test_native_paragraph_spans_cover_every_supplied_unicode_character_once(
    tmp_path, application, requirements
):
    first = "原始 α line\ncontinued.\n\n" * 4_000
    final = "尾部 final partial paragraph"
    text = first + "\n\t\n" + final
    original = snapshot(text)
    original["items"][0]["quote_segments"] = [
        {"start": 0, "end": len(first), "document_locator": "$.first"},
        {"start": len(first) + 3, "end": len(text), "document_locator": "$.final"},
    ]
    calls = []
    _, packet = material.prepare_material_packet(
        application,
        original,
        tmp_path / "packet",
        runner=span_reader(calls),
        requirements=requirements,
    )
    assert len(calls) > 1
    assert packet["status"] == "complete"
    assert packet["sources"] == {}
    for context in calls:
        assert len(material._reading_prompt(context).encode()) <= material.MAX_READING_PROMPT_BYTES
        counts = {}
        for span in context["spans"]:
            assert span["text"] == text[span["start"] : span["end"]]
            assert span["document_locator"] in {"$.first", "$.final"}
            for index in range(span["start"], span["end"]):
                if not text[index].isspace():
                    counts[index] = counts.get(index, 0) + 1
        expected = {
            index
            for index in range(context["range"]["start"], context["range"]["end"])
            if not text[index].isspace()
        }
        assert set(counts) == expected
        assert set(counts.values()) == {1}
    assert calls[-1]["spans"][-1]["text"] == final


def test_native_span_ids_distinguish_repeated_original_paragraphs(
    tmp_path, application, requirements
):
    repeated = r"\item \textbf{Evidence:} I validated risk; no production trading."
    text = ("Unrelated context. " * 20 + "\n\n") * 200 + repeated + "\n\n" + repeated
    calls = []

    def choose(context):
        matches = [span for span in context["spans"] if span["text"] == repeated]
        return (
            [
                {
                    "span_id": matches[-1]["span_id"],
                    "requirement_indexes": [0],
                    "business_relevance": False,
                }
            ]
            if matches
            else []
        )

    _, packet = material.prepare_material_packet(
        application,
        snapshot(text),
        tmp_path / "packet",
        runner=span_reader(calls, choose),
        requirements=requirements,
    )
    receipts = [
        row for page in packet["source_reads"]["source-0"]["ranges"] for row in page["excerpts"]
    ]
    assert receipts[-1]["start"] == text.rindex(repeated)
    assert receipts[-1]["quote"] == repeated
    raw = [
        json.loads(path.read_text())["structured_result"]
        for path in (tmp_path / "packet").glob("source-*/result.json")
    ]
    assert all(
        "quote" not in row and "start" not in row and "end" not in row
        for output in raw
        for row in output["selections"]
    )


@pytest.mark.parametrize("invalid", ["unknown", "quote", "positions", "relevance"])
def test_native_span_selection_rejects_unbound_or_rewritten_provider_output(
    tmp_path, application, requirements, invalid
):
    def choose(context):
        row = {
            "span_id": context["spans"][0]["span_id"],
            "requirement_indexes": [0],
            "business_relevance": False,
        }
        if invalid == "unknown":
            row["span_id"] = "unknown-span"
        elif invalid == "quote":
            row["quote"] = "Rendered replacement."
        elif invalid == "positions":
            row.update(start=0, end=1)
        else:
            row["requirement_indexes"] = [1]
        return [row]

    with pytest.raises(PortalDataError) as caught:
        material.prepare_material_packet(
            application,
            snapshot(long_text()),
            tmp_path / "packet",
            runner=span_reader([], choose),
            requirements=requirements,
        )
    assert caught.value.code == "retrieval_execution_incomplete"


def test_whitespace_only_long_ranges_complete_natively_without_model_calls(
    tmp_path, application, requirements
):
    calls = []
    text = " " * 70_000
    _, packet = material.prepare_material_packet(
        application,
        snapshot(text),
        tmp_path / "packet",
        runner=span_reader(calls),
        requirements=requirements,
    )
    assert calls == []
    assert packet["status"] == "complete"
    assert packet["sources"] == {}
    reading = packet["source_reads"]["source-0"]
    assert reading["status"] == "complete"
    assert reading["ranges"][0]["start"] == 0
    assert reading["ranges"][-1]["end"] == len(text)
    assert all(row["excerpts"] == [] for row in reading["ranges"])
