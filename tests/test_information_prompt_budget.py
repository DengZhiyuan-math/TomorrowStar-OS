"""Prompt budgeting must preserve complete confirmed facts ahead of career prose."""

import json
from copy import deepcopy

import pytest
from test_application_information import answer, library_with
from test_application_match import model_runner
from test_canonical_career_sources import canonical as canonical
from test_normal_retrieval_pipeline import APPLICATION, RecordedPipeline, requirement, thin

from career_evidence_graph.application_information import information_source_snapshot
from career_evidence_graph.application_match import MAX_PROMPT_BYTES, analyze_job
from career_evidence_graph.application_worker import digest
from career_evidence_graph.career_portal_data import PortalDataError


class _BudgetReadingPipeline(RecordedPipeline):
    """Read every range; the explicitly unrelated fixture prose supplies no evidence."""

    def __init__(self, *args, unrelated_source_id, **kwargs):
        super().__init__(*args, **kwargs)
        self.unrelated_source_id = unrelated_source_id

    def __call__(self, config, prompt, **kwargs):
        schema = json.loads(config.output_schema.read_text())
        if set(schema["properties"]) != {"selections"}:
            return super().__call__(config, prompt, **kwargs)
        data = json.loads(prompt.split("CONTEXT_JSON\n", 1)[1])
        self.read_calls.append(data)
        selections = []
        for supplied in data.get("source_ranges", [data]):
            if supplied["source"]["source_id"] == self.unrelated_source_id:
                continue
            if "spans" in supplied:
                if not supplied["spans"]:
                    continue
                selection = {"span_id": supplied["spans"][0]["span_id"]}
            else:
                if not supplied["text"].strip():
                    continue
                selection = {"source_id": supplied["source"]["source_id"]}
            selections.append(
                selection | {"requirement_indexes": list(range(len(self.requirements)))}
            )
        return model_runner({"selections": selections}, self.calls)(config, prompt, **kwargs)


def _assert_unrelated_source_fully_read(report, source_id):
    reading = report["material_packet"]["source_reads"][source_id]
    assert reading["status"] == "complete"
    ranges = reading["ranges"]
    assert len(ranges) > 1
    assert ranges[0]["start"] == 0
    assert ranges[-1]["end"] == reading["original_chars"]
    assert all(
        following["start"] <= previous["end"] < following["end"]
        for previous, following in zip(ranges, ranges[1:], strict=False)
    )
    assert all(not row["excerpts"] for row in ranges)
    assert source_id not in report["material_packet"]["sources"]


def test_normal_analysis_keeps_complete_fact_beside_150kb_career_body(canonical, tmp_path):
    library, _, _, base, *_ = canonical
    text = "Career context. " * 10_000  # 160 KB; intentionally beyond the single-call budget.
    assert len(text.encode()) >= 150_000
    source_revision = digest(text)
    base["documents"].append(
        {
            "id": "large-career",
            "source_name": "career.md",
            "available": True,
            "revision": source_revision,
            "content": text,
        }
    )
    base["items"].append(
        {
            "title": "Long research record",
            "text": text,
            "source_id": "large-career:Scope",
            "evidence_id": "large-career",
            "source_name": "career.md",
            "source_revision": source_revision,
            "locator": "Scope",
            "resume_eligible": True,
            "attribution": "User",
            "rewrite_allowed": True,
        }
    )
    snapshot = thin(canonical)
    answers = library_with(answer("English fluency", "professional"))
    fact = next(
        item
        for item in information_source_snapshot(APPLICATION, answers, snapshot)["items"]
        if item.get("source_kind") == "confirmed_information"
    )
    runner = _BudgetReadingPipeline(
        [requirement("Communicate fluently in English", hard=True)],
        select=False,
        unrelated_source_id="large-career:Scope",
    )
    original = deepcopy((snapshot, answers))
    result = analyze_job(
        APPLICATION,
        snapshot,
        tmp_path / "fact-with-long-career",
        runner=runner,
        source_loader=lambda ids: library.snapshot_for_analysis(base, ids),
        information_library=answers,
    )
    assert runner.phases == ["plan", "evaluate"]
    supplied = next(
        source
        for source in runner.contexts[1]["sources"]
        if source.get("source_kind") == "confirmed_information"
    )
    assert supplied["text"] == fact["text"]
    assert supplied["confirmed_information"] == {"fact": fact["confirmed_information"]["fact"]}
    cited_fact = next(
        source
        for source in result["requirements"][0]["sources"]
        if source.get("source_kind") == "confirmed_information"
    )
    assert cited_fact["confirmed_information"] == fact["confirmed_information"]
    assert supplied["context_range"] == {"start": 0, "end": len(fact["text"])}
    assert result["requirements"][0]["judgment"] == "supported"
    assert result["requirements"][0]["information_support"]["status"] == "supported"
    assert not result["coverage"]["truncated"]
    assert runner.read_calls
    assert result["material_packet"]["status"] == "complete"
    _assert_unrelated_source_fully_read(result, "large-career:Scope")
    assert result["coverage"]["context_bytes"] <= MAX_PROMPT_BYTES
    assert result["selected_source_ids"] == []
    assert (snapshot, answers) == original


def test_oversized_confirmed_fact_fails_before_evidence_model_instead_of_partial_fact(tmp_path):
    key, record = answer("English fluency", "professional")
    record["raw_statement"] = "Original self-report. " * 10_000
    answers = library_with((key, record))
    base = {"schemaVersion": 1, "documents": [], "items": [], "coverage": {}}
    base["revision"] = digest(base)
    runner = RecordedPipeline([requirement("English fluency")])

    def jd_only_runner(config, prompt, **kwargs):
        schema = json.loads(config.output_schema.read_text())
        if set(schema["properties"]) != {"business_object", "role_understanding", "groups"}:
            pytest.fail("An oversized fact must fail before applicant evidence model execution.")
        assert record["raw_statement"] not in prompt
        return runner(config, prompt, **kwargs)

    with pytest.raises(PortalDataError) as error:
        analyze_job(
            APPLICATION,
            base,
            tmp_path / "oversized-fact",
            runner=jd_only_runner,
            information_library=answers,
        )
    assert error.value.code == "match_information_too_large"
    assert len(runner.brief_calls) == 1
    assert runner.phases == []


def test_selected_canonical_capture_precedes_large_unselected_career_text(canonical, tmp_path):
    library, _, _, base, *_ = canonical
    text = "Unselected older career prose. " * 6000
    assert len(text.encode()) > 160_000
    revision = digest(text)
    base["documents"].append(
        {
            "id": "legacy-prose",
            "source_name": "legacy.md",
            "available": True,
            "revision": revision,
            "content": text,
        }
    )
    base["items"].append(
        {
            "title": "Legacy career prose",
            "text": text,
            "source_id": "legacy-prose:Scope",
            "evidence_id": "legacy-prose",
            "source_revision": revision,
            "source_name": "legacy.md",
            "locator": "Scope",
            "resume_eligible": True,
            "attribution": "User",
        }
    )
    snapshot = thin(canonical)
    expected = library.snapshot_for_analysis(base, ["unseen-identity"])
    selected_items = [item for item in expected["items"] if item.get("candidate_id")]
    runner = _BudgetReadingPipeline(
        [requirement("Experience across scientific disciplines")],
        judgments=["partial"],
        unrelated_source_id="legacy-prose:Scope",
    )
    report = analyze_job(
        APPLICATION,
        snapshot,
        tmp_path / "prioritize-selected-capture",
        runner=runner,
        source_loader=lambda ids: library.snapshot_for_analysis(base, ids),
        information_library=library_with(),
    )
    real = {alias: source_id for source_id, alias in report["coverage"]["source_aliases"].items()}
    supplied = {real[source["source_id"]]: source for source in runner.contexts[1]["sources"]}
    for item in selected_items:
        assert supplied[item["source_id"]]["text"] == item["text"]
        assert supplied[item["source_id"]]["context_range"] == {
            "start": 0,
            "end": len(item["text"]),
        }
    assert any("Physics and biology" in source["text"] for source in supplied.values())
    assert report["retrieval"]["source_reads"][0]["status"] == "read"
    assert not report["coverage"]["truncated"]
    assert runner.read_calls
    assert report["material_packet"]["status"] == "complete"
    _assert_unrelated_source_fully_read(report, "legacy-prose:Scope")
    assert not any(
        item["source_id"] in report["coverage"]["omitted_source_ids"] for item in selected_items
    )


@pytest.mark.parametrize("matching_only", [False, True])
def test_match_refresh_discards_resume_rationale_but_normal_generation_remains_strict(
    canonical, tmp_path, matching_only
):
    library, _, _, base, *_ = canonical
    snapshot = thin(canonical)

    class GarbledSelectionPipeline(RecordedPipeline):
        def __call__(self, *args, **kwargs):
            result = super().__call__(*args, **kwargs)
            if self.phases and self.phases[-1] == "evaluate":
                output = result.structured_result
                output["selected_source_ids"] = output["requirements"][0]["source_ids"]
                output["selection_rationale"] = [
                    {
                        "source_id": "valid-schema-but-garbled-source-id",
                        "business_relevance": "Irrelevant generation-only selection rationale.",
                        "evidence_role": "transferable",
                    }
                ]
            return result

    runner = GarbledSelectionPipeline(
        [requirement("Experience across scientific disciplines")], judgments=["supported"]
    )

    def run():
        return analyze_job(
            APPLICATION,
            snapshot,
            tmp_path / f"selection-{matching_only}",
            runner=runner,
            source_loader=lambda ids: library.snapshot_for_analysis(base, ids),
            information_library=library_with(),
            matching_only=matching_only,
        )

    if matching_only:
        report = run()
        assert report["requirements"][0]["judgment"] == "supported"
        assert report["requirements"][0]["sources"]
        assert report["selected_source_ids"] == []
        assert report["selection_rationale"] == []
        assert report["matching_only"] is True
    else:
        with pytest.raises(PortalDataError) as error:
            run()
        assert error.value.code == "match_model_invalid"


def test_many_selected_bodies_fit_when_internal_receipts_stay_outside_prompt():
    import json

    from career_evidence_graph.application_match import _prompt_context

    sources = {}
    for index in range(80):
        identifier = f"selected-source-{index}"
        sources[identifier] = {
            "source_id": identifier,
            "candidate_id": f"new-candidate-{index}",
            "source_name": f"selected-{index}.json",
            "text": f"Confirmed research record {index}: " + "bounded documentary fact. " * 12,
            "source_revision": digest({"index": index}),
            "evidence_id": f"internal-document-{index}",
            "locator": "/confirmed_facts",
            "attribution": "User-confirmed documentary statement",
            "boundaries": "No inference of mastery or sole responsibility.",
            "review_status": "documentary",
            "available": True,
            "match_eligible": True,
            "resume_eligible": True,
            "rewrite_allowed": False,
            "documentary_only": True,
            "internal_receipt": {
                "references": [digest({"reference": item}) for item in range(80)],
                "context_revision": digest({"context": index}),
            },
        }
    before = deepcopy(sources)
    prompt, included, coverage = _prompt_context(
        {"job_description": "Evaluate scientific research experience."}, sources, {"coverage": {}}
    )
    rows = json.loads(prompt.rsplit("\n", 1)[1])["sources"]
    assert len(rows) == len(sources) == len(included) == 80
    assert coverage["omitted_source_ids"] == []
    assert coverage["truncated_sources"] == []
    assert coverage["context_bytes"] <= MAX_PROMPT_BYTES
    real = {alias: source_id for source_id, alias in coverage["source_aliases"].items()}
    for row in rows:
        original = sources[real[row["source_id"]]]
        assert row["text"] == original["text"]
        assert row["boundaries"] == original["boundaries"]
        assert row["rewrite_allowed"] is False
        assert "source_revision" not in row
        assert "evidence_id" not in row
        assert "internal_receipt" not in row
        receipt = included[real[row["source_id"]]]
        assert receipt["source_revision"] == original["source_revision"]
        assert receipt["internal_receipt"] == original["internal_receipt"]
    assert sources == before


def test_fixed_education_is_read_before_large_selected_project_bodies():
    from career_evidence_graph.application_match import _prompt_context

    sources = {
        "large-project": {
            "source_id": "large-project",
            "candidate_id": "project",
            "text": "Project detail. " * 20000,
            "available": True,
        },
        "degree": {
            "source_id": "degree",
            "locator": "profile.education[0]",
            "text": "Mathematics PhD, in progress, graduation July 2028",
            "available": True,
        },
    }
    prompt, _, coverage = _prompt_context(
        APPLICATION, sources, {"application_library_policy": "trusted-library/v1", "coverage": {}}
    )
    context = json.loads(prompt.rsplit("\n", 1)[1])
    assert context["sources"][0]["source_id"] == coverage["source_aliases"]["degree"]
    assert context["sources"][0]["text"] == sources["degree"]["text"]
