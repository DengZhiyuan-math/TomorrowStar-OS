"""Controlled native facts are cited by identity and anchored by the program."""

import json
from copy import deepcopy
from pathlib import Path

import pytest
from test_application_job_brief import runner_for
from test_application_match import model_runner
from test_application_material_packet import snapshot
from test_compact_structured_fact_delivery import career_facts

from career_evidence_graph.application_job_brief import brief_requirements, create_job_brief
from career_evidence_graph.application_match import analyze_job
from career_evidence_graph.application_material_packet import prepare_material_packet
from career_evidence_graph.application_worker import digest

pytestmark = pytest.mark.usefixtures("reading_limits")


def allowed_ids(schema, field):
    if "$ref" in field:
        return allowed_ids(schema, schema["$defs"][field["$ref"].split("/")[-1]])
    if "anyOf" in field:
        return set().union(*(allowed_ids(schema, branch) for branch in field["anyOf"]))
    return set(field["enum"])


def _real_ids(directory):
    aliases = json.loads((directory / "context-coverage.json").read_text())["source_aliases"]
    return {alias: source_id for source_id, alias in aliases.items()}


def saved_schema(directory):
    """The saved schema with call-local source handles mapped back to source IDs."""
    real = _real_ids(directory)

    def mapped(node):
        if isinstance(node, list):
            return [mapped(item) for item in node]
        if not isinstance(node, dict):
            return node
        return {
            key: sorted(real.get(item, item) for item in value) if key == "enum" else mapped(value)
            for key, value in node.items()
        }

    return mapped(json.loads((directory / "match-schema.json").read_text()))


def saved_context(directory):
    """The saved prompt context with call-local source handles mapped back."""
    real = _real_ids(directory)
    prompt = json.loads((directory / "context-input.json").read_text())["prompt"]
    context = json.loads(prompt.rsplit("\n", 1)[1])
    # Grouped experiences list their facts and background under one header.
    for experience in context.pop("experiences", []):
        for entry in experience.get("facts", []) + experience.get("context", []):
            context.setdefault("sources", []).append(entry)
    for source in context.get("sources", []):
        source["source_id"] = real.get(source["source_id"], source["source_id"])
    return context


@pytest.fixture
def native_case(tmp_path):
    return build_native_case(tmp_path)


def build_native_case(tmp_path, *, education=False, texts=("Validate risk",)):
    application = {
        "id": "synthetic-native",
        "revision": "r1",
        "company": "Example",
        "role_title": "Researcher",
        "location": "Zurich",
        "job_description": "Validate risk.",
    }
    brief = create_job_brief(
        application,
        tmp_path / "brief",
        runner=runner_for(
            {
                "business_object": "Risk decisions",
                "role_understanding": {
                    "business_objective": "Validate risk",
                    "work_outputs": ["Risk analysis"],
                    "methods_role": "Analysis supports risk decisions",
                },
                "groups": [
                    {
                        "label": "Risk",
                        "jd_quote": "Validate risk.",
                        "operator": "all",
                        "importance": "required",
                        "hard_condition": False,
                        "weight": 100,
                        "weight_reason": "The stated output",
                        "requirements": [
                            {"text": text, "jd_quote": "Validate risk"} for text in texts
                        ],
                    }
                ],
            }
        ),
        environment={},
    )
    original = career_facts(1)
    original["items"][0]["text"] = (
        "I validated risk. The team reviewed it. No production deployment."
    )
    confirmed = snapshot('{"English fluency":"professional"}')["items"][0]
    confirmed.update(
        source_id="confirmed-language",
        evidence_id="confirmed-doc",
        source_kind="confirmed_information",
        resume_eligible=False,
        confirmed_information={"fact": "English fluency", "value": "professional"},
    )
    original["documents"].append({"id": "confirmed-doc", "revision": "r-0", "available": True})
    original["items"].append(confirmed)
    if education:
        degree = snapshot("M2 in Mathematics, Example University, 2021-09 to 2022-06 (awarded).")
        degree = degree["items"][0] | {
            "source_id": "education-m2",
            "evidence_id": "education-doc",
            "source_kind": "education",
            "resume_eligible": False,
        }
        original["documents"].append({"id": "education-doc", "revision": "r-0", "available": True})
        original["items"].append(degree)
    original["schemaVersion"] = 1
    original["application_library_policy"] = "trusted-library/v1"
    original["job_brief"] = brief
    original["match_requirements"] = brief_requirements(brief)
    original["revision"] = digest({k: v for k, v in original.items() if k != "revision"})
    prepared, _ = prepare_material_packet(
        application,
        original,
        tmp_path / "packet",
        requirements=original["match_requirements"],
        job_brief=brief,
    )
    prepared["revision"] = digest({k: v for k, v in prepared.items() if k != "revision"})
    row = prepared["match_requirements"][0]
    output = {
        "role_understanding": brief["role_understanding"],
        "requirements": [
            {
                "text": row["text"],
                "importance": row["importance"],
                "hard_condition": row["hard_condition"],
                "judgment": "supported",
                "explanation": "Recorded experimental work supports the requirement.",
                "source_ids": ["source-0", "confirmed-language"],
                "citations": [{"source_id": "source-0"}, {"source_id": "confirmed-language"}],
                "claim_scope": "documentary",
                "inference": {
                    "requirement_id": row["scoring_framework"]["requirement_id"],
                    "type": "semantic",
                    "relation": "supports",
                    "basis": "The cited work supports the requirement.",
                    "expression_scope": "Validated risk within the recorded team responsibility.",
                    "calculation": None,
                },
            }
        ],
        "selected_source_ids": ["source-0"],
        "selection_rationale": [
            {
                "source_id": "source-0",
                "business_relevance": "Experimental risk validation",
                "evidence_role": "direct_domain",
            }
        ],
        "extracted_fields": {
            "company": None,
            "role_title": None,
            "location": None,
            "uncertain_fields": ["company", "role_title", "location"],
        },
        "limitations": [],
    }
    return application, prepared, output


def test_native_source_ids_produce_full_literal_citations_and_keep_raw_response(
    native_case, tmp_path
):
    application, prepared, output = native_case
    before = deepcopy(prepared)
    directory = tmp_path / "native"
    result = analyze_job(application, prepared, directory, runner=model_runner(output, []))
    row = result["requirements"][0]
    assert row["citations"] == [
        {
            "source_id": "source-0",
            "quote": "I validated risk. The team reviewed it. No production deployment.",
        },
        {"source_id": "confirmed-language", "quote": '{"English fluency":"professional"}'},
    ]
    assert row["sources"][0]["record_context"]["responsibility"] == "team"
    assert (
        row["sources"][0]["record_context"]["scope"]
        == "Experimental risk validation; no production deployment."
    )
    assert row["sources"][0]["quote_start"] == 0
    assert row["sources"][0]["quote_end"] == len(row["sources"][0]["text"])
    assert row["sources"][1]["confirmed_information"]["value"] == "professional"
    assert [fact["quote"] for fact in row["inference"]["facts"]] == [
        source["quote"] for source in row["sources"]
    ]
    assert result["score"]["lower"] == 100
    assert prepared == before
    assert json.loads((directory / "model-result.json").read_text())["structured_result"] == output


def compact(output, prepared):
    """The answer without the fixed rows' echoed text, flags and role understanding."""
    rows = [
        {
            key: value
            for key, value in row.items()
            if key not in {"text", "importance", "hard_condition", "source_ids"}
        }
        | {"requirement_id": template["scoring_framework"]["requirement_id"]}
        # A fixture may answer fewer rows than the brief holds.
        for row, template in zip(
            output["requirements"], prepared["match_requirements"], strict=False
        )
    ]
    return {key: value for key, value in output.items() if key != "role_understanding"} | {
        "requirements": rows
    }


def test_compact_answer_is_bound_to_the_fixed_requirements(native_case, tmp_path):
    from career_evidence_graph.career_portal_data import PortalDataError

    application, prepared, output = native_case
    full = analyze_job(application, prepared, tmp_path / "full", runner=model_runner(output, []))
    directory = tmp_path / "compact"
    result = analyze_job(
        application, prepared, directory, runner=model_runner(compact(output, prepared), [])
    )
    assert result["requirements"] == full["requirements"]
    assert result["role_understanding"] == full["role_understanding"]
    assert result["score"] == full["score"]
    schema = json.loads((directory / "match-schema.json").read_text())
    assert "role_understanding" not in schema["properties"]
    row = schema["$defs"]["_CompactRequirement"]["properties"]
    assert not {"text", "importance", "hard_condition", "source_ids"} & row.keys()
    assert row["requirement_id"]["enum"] == [
        template["scoring_framework"]["requirement_id"]
        for template in prepared["match_requirements"]
    ]
    prompt = json.loads((directory / "context-input.json").read_text())["prompt"]
    assert "do not repeat its text, importance or hard_condition" in prompt
    assert "keep its exact text" not in prompt

    shifted = compact(output, prepared)
    shifted["requirements"][0]["requirement_id"] = "req-other"
    with pytest.raises(PortalDataError) as caught:
        analyze_job(application, prepared, tmp_path / "shifted", runner=model_runner(shifted, []))
    assert caught.value.code == "match_model_invalid"


def test_each_followup_rescores_only_the_requirements_still_unknown(tmp_path, monkeypatch):
    from career_evidence_graph import application_match
    from career_evidence_graph.application_match import settled_assessment
    from career_evidence_graph.career_portal_data import PortalDataError

    application, prepared, output = build_native_case(
        tmp_path, texts=("Validate risk", "Report risk", "Price risk")
    )
    known = compact(output, prepared)["requirements"][0]
    ids = [row["scoring_framework"]["requirement_id"] for row in prepared["match_requirements"]]

    def open_row(identifier):
        return known | {
            "requirement_id": identifier,
            "judgment": "unknown",
            "explanation": "No recorded fact covers this yet.",
            "citations": [],
            "fit_score": 10,
            "inference": known["inference"]
            | {"type": "direct", "basis": "Not established.", "expression_scope": ""},
        }

    partial = open_row(ids[1]) | {
        "judgment": "partial",
        "explanation": "The recorded validation partly covers reporting.",
        "citations": [{"source_id": "source-0"}],
        "fit_score": 50,
        "inference": known["inference"] | {"type": "semantic", "basis": "Validation work."},
    }
    calls = []

    def scorer(prompt, schema, directory):
        # Each second-opinion row names the call that answered it.
        calls.append(directory.name)
        enum = schema["$defs"]["_CompactRequirement"]["properties"]["requirement_id"]["enum"]
        rows = [
            {"judgment": "partial", "fit_score": 50, "explanation": directory.name} for _ in enum
        ]
        return {"model": "claude-opus-5-5", "status": "complete", "output": {"requirements": rows}}

    monkeypatch.setattr(application_match, "SECOND_OPINION", scorer)
    answers = compact(output, prepared)

    def evaluate(name, snapshot, rows):
        return analyze_job(
            application,
            snapshot,
            tmp_path / name,
            runner=model_runner(answers | {"requirements": rows}, []),
        )

    def followup(name, report):
        settled = settled_assessment(tmp_path / name, digest(report))
        snapshot = deepcopy(prepared) | {"settled_assessment": settled}
        snapshot.pop("revision")
        snapshot["revision"] = digest(snapshot)
        return settled, snapshot

    one = evaluate("round-1", prepared, [known, open_row(ids[1]), open_row(ids[2])])
    assert [row["judgment"] for row in one["requirements"]] == ["supported", "unknown", "unknown"]
    assert settled_assessment(tmp_path / "round-1", "other-revision") is None

    settled, later = followup("round-1", one)
    assert [row["requirement_id"] for row in settled["rows"]] == [ids[0]]
    two = evaluate("round-2", later, [partial, open_row(ids[2])])
    assert two["requirements"][0] == one["requirements"][0]
    assert [row["judgment"] for row in two["requirements"]] == ["supported", "partial", "unknown"]
    schema = json.loads((tmp_path / "round-2/match-schema.json").read_text())
    enum = schema["$defs"]["_CompactRequirement"]["properties"]["requirement_id"]["enum"]
    assert enum == ids[1:]
    prompt = json.loads((tmp_path / "round-2/context-input.json").read_text())["prompt"]
    shown = json.loads(prompt.rsplit("\n", 1)[1])["settled_assessments"]
    assert [row["requirement_id"] for row in shown] == [ids[0]]

    # The second follow-up keeps both earlier verdicts, though round 2 answered one of them.
    settled, last = followup("round-2", two)
    assert [row["requirement_id"] for row in settled["rows"]] == ids[:2]
    three = evaluate("round-3", last, [open_row(ids[2])])
    assert three["requirements"][:2] == two["requirements"][:2]
    assert [row["explanation"] for row in three["second_opinion"]["requirements"]] == [
        "round-1",
        "round-2",
        "round-3",
    ]

    with pytest.raises(PortalDataError) as caught:
        evaluate("rewritten", last, [known, partial, open_row(ids[2])])
    assert caught.value.code == "match_model_invalid"


def test_native_request_schema_only_allows_supplied_source_ids_and_no_quote(native_case, tmp_path):
    application, prepared, output = native_case
    directory = tmp_path / "schema"
    analyze_job(application, prepared, directory, runner=model_runner(output, []))
    schema = saved_schema(directory)
    definitions = schema["$defs"]
    requirement = next(
        value for value in definitions.values() if "citations" in value.get("properties", {})
    )
    citation_ref = requirement["properties"]["citations"]["items"]["$ref"].split("/")[-1]
    citation = definitions[citation_ref]
    assert set(citation["properties"]) == {"source_id"}
    assert citation["required"] == ["source_id"]
    assert citation["additionalProperties"] is False
    assert allowed_ids(schema, citation["properties"]["source_id"]) == {
        "source-0",
        "confirmed-language",
    }
    # Compact rows cite only through citations; the program derives source_ids.
    assert "source_ids" not in requirement["properties"]
    prompt = json.loads((directory / "context-input.json").read_text())["prompt"]
    instructions = prompt.rsplit("\n", 1)[0]
    assert "only source_id" in instructions
    assert "literal quotes" not in instructions
    assert "Each citation contains source_id and a literal quote" not in instructions
    assert "short literal quotes" not in instructions


@pytest.mark.parametrize("quote", ["Validate risk.", "English is suitable for this role.", ""])
def test_recorded_native_quotes_are_replaced_without_changing_judgment(
    native_case, tmp_path, quote
):
    application, prepared, output = native_case
    for citation in output["requirements"][0]["citations"]:
        citation["quote"] = quote
    result = analyze_job(
        application, prepared, tmp_path / "recorded", runner=model_runner(output, [])
    )
    row = result["requirements"][0]
    assert row["judgment"] == output["requirements"][0]["judgment"]
    assert row["claim_scope"] == "documentary"
    assert row["inference"]["type"] == "semantic"
    assert (
        row["citations"][0]["quote"]
        == "I validated risk. The team reviewed it. No production deployment."
    )
    assert row["citations"][1]["quote"] == '{"English fluency":"professional"}'
    saved = json.loads((tmp_path / "recorded/model-result.json").read_text())
    assert saved["structured_result"] == output


@pytest.mark.parametrize("mutation", ["wrong-id", "missing-id", "missing-references"])
def test_invalid_native_id_bindings_publish_no_score(native_case, tmp_path, mutation):
    from career_evidence_graph.career_portal_data import PortalDataError

    application, prepared, output = native_case
    row = output["requirements"][0]
    if mutation == "wrong-id":
        row["source_ids"][0] = "unread-source"
        row["citations"][0]["source_id"] = "unread-source"
    elif mutation == "missing-id":
        row["citations"][0] = {}
    else:
        row["source_ids"] = []
        row["citations"] = []
    directory = tmp_path / "invalid-id"
    if mutation != "missing-id":
        result = analyze_job(application, prepared, directory, runner=model_runner(output, []))
        assert_citation_withheld(result)
        return
    with pytest.raises(PortalDataError) as caught:
        analyze_job(application, prepared, directory, runner=model_runner(output, []))
    assert caught.value.code == "match_model_invalid"
    assert not (directory / "analysis.json").exists()
    assert (directory / "model-result.json").exists()


@pytest.mark.parametrize("cited", [[], [{"source_id": "confirmed-language"}]])
def test_native_citations_follow_the_source_ids(native_case, tmp_path, cited):
    # Installed MC-11: an education judgment named the right record in source_ids but
    # cited an unrelated one; native citations only repeat source_ids.
    application, prepared, output = native_case
    row = output["requirements"][0]
    row.update(source_ids=["source-0"], citations=cited)
    result = analyze_job(application, prepared, tmp_path / "cited", runner=model_runner(output, []))
    row = result["requirements"][0]
    assert row["judgment"] == "supported" and "citation_warning" not in row
    assert [citation["source_id"] for citation in row["citations"]] == ["source-0"]


def test_an_education_record_is_cited_by_identity(tmp_path):
    # Installed MC-11: education needed a literal quote, so the model's ID-only citation
    # named an unrelated record and both degree requirements stayed unresolved.
    application, prepared, output = build_native_case(tmp_path, education=True)
    row = output["requirements"][0]
    row.update(source_ids=["education-m2"], citations=[{"source_id": "education-m2"}])
    result = analyze_job(
        application, prepared, tmp_path / "degree", runner=model_runner(output, [])
    )
    row = result["requirements"][0]
    assert row["judgment"] == "supported" and "citation_warning" not in row
    assert row["citations"][0]["quote"].startswith("M2 in Mathematics")


def test_packet_matching_counts_an_in_progress_degree_as_held(native_case, tmp_path):
    # Installed MC-11: the rule reached only the legacy prompt, so packet matching still
    # judged the in-progress PhD a gap for "Hold a PhD".
    application, prepared, output = native_case
    directory = tmp_path / "degree-rule"
    calls = []
    analyze_job(application, prepared, directory, runner=model_runner(output, calls))
    # Decided 2026-10-31: the final matching call uses gpt-6.1-sol.
    assert any(
        call[call.index("--model") + 1] == "gpt-6.1-sol" for call in calls if "--model" in call
    )
    prompt = json.loads((directory / "context-input.json").read_text())["prompt"]
    assert "a degree in progress with an expected completion date supports" in prompt
    assert "return fit_score, an integer 0-100" in prompt
    # Decided 2026-10-31: team and AI-assisted work count only the user's own share.
    assert "count the user's design, direction and review" in prompt
    # A five-job comparison: a different setting is partial, never supported.
    assert "Supported needs the stated setting" in prompt
    from career_evidence_graph.codex_cli import strict_output_schema

    sent = strict_output_schema(json.loads((directory / "match-schema.json").read_text()))
    definitions = sent["$defs"]
    requirement = next(v for v in definitions.values() if "fit_score" in v.get("properties", {}))
    assert "fit_score" in requirement["required"]


@pytest.mark.parametrize("opinion", ["agree", "differ", "failed"])
def test_a_second_model_scores_the_same_prompt_beside_the_first(
    native_case, tmp_path, monkeypatch, opinion
):
    from career_evidence_graph import application_match
    from career_evidence_graph.application_match_scoring import combined_score

    application, prepared, output = native_case
    output["requirements"][0]["fit_score"] = 90
    seen = []

    def scorer(prompt, schema, directory):
        seen.append(prompt)
        if opinion == "failed":
            return {
                "model": "claude-opus-5-5",
                "status": "failed",
                "error_code": "claude_not_signed_in",
            }
        row = {
            "judgment": "supported" if opinion == "agree" else "partial",
            "fit_score": 85 if opinion == "agree" else 40,
            "explanation": "Second reading.",
        }
        return {"model": "claude-opus-5-5", "status": "complete", "output": {"requirements": [row]}}

    # Decided 2026-10-31: Opus scores the same prompt beside sol.
    monkeypatch.setattr(application_match, "SECOND_OPINION", scorer)
    result = analyze_job(application, prepared, tmp_path / opinion, runner=model_runner(output, []))
    prompt = json.loads((tmp_path / opinion / "context-input.json").read_text())["prompt"]
    assert seen == [prompt]
    score, models = combined_score(result["score"], result, result["requirements"])
    if opinion == "failed":
        assert result["second_opinion"]["status"] == "failed" and models is None
        assert score == result["score"]
        return
    assert models["needs_review"] is (opinion == "differ")
    assert models["differing_requirements"] == ([] if opinion == "agree" else [0])
    # Decided 2026-11-04: sol 0.45, Opus 0.55.
    assert score["lower"] == pytest.approx(0.45 * 90 + 0.55 * (85 if opinion == "agree" else 40))


def assert_citation_withheld(result):
    """A complete answer keeps its score, but the unusable citation counts for nothing."""
    # Installed MC-11: one bad citation used to fail the whole analysis as unknown.
    row = result["requirements"][0]
    assert row["judgment"] == "unknown" and row["citation_warning"] in {
        "match_source_invalid",
        "match_attribution_invalid",
    }
    assert row["inference"]["relation"] == "unresolved"
    assert row["inference"]["expression_scope"] == "" and row["inference"]["facts"] == []
    assert result["score"]["lower"] == 0


def reseal(prepared):
    packet = prepared["material_packet"]
    packet["sources"] = deepcopy(prepared["material_packet_sources"])
    packet["revision"] = digest({k: v for k, v in packet.items() if k != "revision"})
    prepared["revision"] = digest({k: v for k, v in prepared.items() if k != "revision"})


@pytest.mark.parametrize("mutation", ["raw", "empty-fact-id", "excerpt"])
def test_raw_or_mixed_controlled_sources_keep_literal_quote_validation(
    native_case, tmp_path, mutation
):

    application, prepared, output = native_case
    source = prepared["material_packet_sources"]["source-0"]
    if mutation == "raw":
        source.pop("record_context")
    elif mutation == "empty-fact-id":
        source["record_context"]["fact_id"] = ""
    else:
        source["quote_segments"] = [
            {
                "start": 0,
                "end": len(source["text"]),
                "text": source["text"],
                "document_locator": "excerpt",
                "source_start": 20,
            }
        ]
    reseal(prepared)
    for citation in output["requirements"][0]["citations"]:
        citation["quote"] = "Invented content, not a literal source fact."
    directory = tmp_path / "raw"
    assert_citation_withheld(
        analyze_job(application, prepared, directory, runner=model_runner(output, []))
    )
    schema = saved_schema(directory)
    assert "quote" in schema["$defs"]["_Citation"]["required"]
    prompt = json.loads((directory / "context-input.json").read_text())["prompt"]
    assert "exact literal" in prompt


def test_native_full_fact_does_not_bypass_inference_precision_checks(native_case, tmp_path):
    from career_evidence_graph.career_portal_data import PortalDataError

    application, prepared, output = native_case
    output["requirements"][0]["inference"]["expression_scope"] = (
        "Delivered 987654 completed projects."
    )
    directory = tmp_path / "unsupported-inference"
    with pytest.raises(PortalDataError) as caught:
        analyze_job(application, prepared, directory, runner=model_runner(output, []))
    assert caught.value.code == "match_inference_invalid"
    assert not (directory / "analysis.json").exists()


def test_default_material_budget_adapts_but_explicit_invalid_pair_is_rejected():
    from career_evidence_graph import application_match as match
    from career_evidence_graph.career_portal_data import PortalDataError

    environment = {"TOMORROWSTAR_MATCH_CONTEXT_BYTES": "10000"}
    assert match.context_limits(environment) == {
        "match_context_bytes": 10_000,
        "material_context_bytes": 9_999,
    }
    with pytest.raises(PortalDataError) as caught:
        match.context_limits(environment | {"TOMORROWSTAR_MATERIAL_CONTEXT_BYTES": "60000"})
    assert caught.value.code == "match_context_limits_invalid"


@pytest.fixture
def mixed_case(native_case):
    application, prepared, output = native_case
    raw = snapshot("I worked with a research team.")["items"][0]
    raw.update(
        source_id="raw-profile",
        evidence_id="raw-doc",
        source_kind="profile",
        available=True,
        match_eligible=True,
        rewrite_allowed=False,
        documentary_only=True,
    )
    prepared["items"].append(deepcopy(raw))
    prepared["documents"].append({"id": "raw-doc", "revision": "r-0", "available": True})
    prepared["material_packet_sources"]["raw-profile"] = raw
    reseal(prepared)
    row = output["requirements"][0]
    row["source_ids"].append("raw-profile")
    row["citations"].append({"source_id": "raw-profile", "quote": "worked with a research team"})
    return application, prepared, output


def test_mixed_sources_use_native_ids_and_retain_precise_raw_quotes(mixed_case, tmp_path):
    application, prepared, output = mixed_case
    directory = tmp_path / "mixed"
    result = analyze_job(application, prepared, directory, runner=model_runner(output, []))
    row = result["requirements"][0]
    assert [citation["quote"] for citation in row["citations"]] == [
        "I validated risk. The team reviewed it. No production deployment.",
        '{"English fluency":"professional"}',
        "worked with a research team",
    ]
    assert row["sources"][2]["quote_start"] == 2
    context = saved_context(directory)
    assert {source["source_id"] for source in context["sources"]} == {
        "source-0",
        "confirmed-language",
        "raw-profile",
    }
    schema = saved_schema(directory)
    requirement = next(
        value for value in schema["$defs"].values() if "citations" in value.get("properties", {})
    )
    citation = schema["$defs"][
        requirement["properties"]["citations"]["items"]["$ref"].split("/")[-1]
    ]
    assert len(citation["anyOf"]) == 2
    native, raw = citation["anyOf"]
    assert allowed_ids(schema, native["properties"]["source_id"]) == {
        "confirmed-language",
        "source-0",
    }
    assert set(native["properties"]) == {"source_id"}
    assert raw["$ref"] == "#/$defs/_Citation"
    assert allowed_ids(schema, schema["$defs"]["_Citation"]["properties"]["source_id"]) == {
        "raw-profile"
    }


@pytest.mark.parametrize("recorded_binding", [False, True])
def test_native_inference_binding_and_unknown_expression_are_program_owned(
    mixed_case, tmp_path, recorded_binding
):
    application, prepared, output = mixed_case
    row = output["requirements"][0]
    row["judgment"] = "unknown"
    row["inference"]["expression_scope"] = "The applicant has no risk capability."
    row["inference"].pop("requirement_id")
    row["inference"].pop("relation")
    if recorded_binding:
        row["inference"].update(requirement_id="a-wrong-recorded-id", relation="supports")
    directory = tmp_path / "bound-unknown"
    result = analyze_job(application, prepared, directory, runner=model_runner(output, []))
    bound = result["requirements"][0]
    assert bound["judgment"] == "unknown"
    assert (
        bound["inference"]["requirement_id"]
        == prepared["match_requirements"][0]["scoring_framework"]["requirement_id"]
    )
    assert bound["inference"]["relation"] == "unresolved"
    assert bound["inference"]["expression_scope"] == ""
    assert bound["inference"]["basis"] == row["inference"]["basis"]
    assert result["score"]["lower"] == 0
    assert result["score"]["upper"] == 100
    assert json.loads((directory / "model-result.json").read_text())["structured_result"] == output
    schema = saved_schema(directory)
    inference = next(
        value
        for value in schema["$defs"].values()
        if "expression_scope" in value.get("properties", {})
    )
    assert "relation" not in inference["properties"]
    assert "requirement_id" not in inference["properties"]


def test_mixed_resume_selection_uses_canonical_facts_but_keeps_raw_matching(mixed_case, tmp_path):
    application, prepared, output = mixed_case
    output["selected_source_ids"].append("raw-profile")
    output["selection_rationale"].append(
        {
            "source_id": "raw-profile",
            "business_relevance": "Team context",
            "evidence_role": "transferable",
        }
    )
    directory = tmp_path / "canonical-resume"
    result = analyze_job(application, prepared, directory, runner=model_runner(output, []))
    assert result["selected_source_ids"] == ["source-0"]
    assert result["requirements"][0]["source_ids"] == [
        "source-0",
        "confirmed-language",
        "raw-profile",
    ]
    schema = saved_schema(directory)
    assert allowed_ids(schema, schema["properties"]["selected_source_ids"]["items"]) == {"source-0"}
    assert allowed_ids(
        schema, schema["$defs"]["_SelectionRationale"]["properties"]["source_id"]
    ) == {"source-0"}
    context = saved_context(directory)
    assert "resume_selection_source_ids" not in context


def test_complete_native_fact_with_original_segments_still_uses_native_identity(
    native_case, tmp_path
):
    application, prepared, output = native_case
    source = prepared["material_packet_sources"]["source-0"]
    source["original_text_chars"] = len(source["text"])
    source["context_range"] = {"start": 0, "end": len(source["text"])}
    source["quote_segments"] = [
        {
            "start": 0,
            "end": len(source["text"]),
            "text": source["text"],
            "document_locator": "native-fact",
            "source_start": 0,
            "source_end": len(source["text"]),
        }
    ]
    reseal(prepared)
    result = analyze_job(
        application, prepared, tmp_path / "full-segments", runner=model_runner(output, [])
    )
    quoted = result["requirements"][0]["sources"][0]
    assert quoted["quote"] == "I validated risk. The team reviewed it. No production deployment."
    assert quoted["quote_segments"] == source["quote_segments"]
    assert quoted["quote_start"] == 0
    assert quoted["quote_end"] == len(source["text"])


@pytest.mark.parametrize("quote", [None, "Invented unrelated quote"])
def test_mixed_raw_quotes_are_required_even_when_native_ids_are_valid(mixed_case, tmp_path, quote):

    application, prepared, output = mixed_case
    citation = output["requirements"][0]["citations"][-1]
    if quote is None:
        citation.pop("quote")
    else:
        citation["quote"] = quote
    directory = tmp_path / "invalid-raw"
    assert_citation_withheld(
        analyze_job(application, prepared, directory, runner=model_runner(output, []))
    )


def test_all_raw_controlled_dataset_keeps_legacy_quotes_and_inference_bindings(
    native_case, tmp_path
):
    from career_evidence_graph.career_portal_data import PortalDataError

    application, prepared, output = native_case
    prepared["material_packet_sources"]["source-0"].pop("record_context")
    confirmed = prepared["material_packet_sources"]["confirmed-language"]
    confirmed.pop("source_kind")
    confirmed.pop("confirmed_information")
    reseal(prepared)
    row = output["requirements"][0]
    for citation in row["citations"]:
        citation["quote"] = prepared["material_packet_sources"][citation["source_id"]]["text"]
    row["inference"]["requirement_id"] = "wrong-legacy-binding"
    directory = tmp_path / "legacy-binding"
    with pytest.raises(PortalDataError) as caught:
        analyze_job(application, prepared, directory, runner=model_runner(output, []))
    assert caught.value.code == "match_inference_invalid"
    schema = saved_schema(directory)
    assert "quote" in schema["$defs"]["_Citation"]["required"]
    assert "requirement_id" in schema["$defs"]["Inference"]["required"]
    assert not (directory / "analysis.json").exists()


def test_mixed_schema_encodes_each_source_identity_once(mixed_case, tmp_path):
    application, prepared, output = mixed_case
    directory = tmp_path / "deduplicated-schema"
    analyze_job(application, prepared, directory, runner=model_runner(output, []))
    schema = saved_schema(directory)
    encoded = json.dumps(schema)
    assert encoded.count('"source-0"') == 1
    assert encoded.count('"confirmed-language"') == 1
    assert encoded.count('"raw-profile"') == 1
    assert schema["properties"]["selected_source_ids"]["items"] == {
        "$ref": "#/$defs/ResumeSourceID"
    }
    context = saved_context(directory)
    assert "native_citation_source_ids" not in context
    assert "resume_selection_source_ids" not in context


@pytest.mark.parametrize("mode", ["raw-resume", "no-resume"])
def test_shared_source_definitions_handle_empty_partitions(native_case, tmp_path, mode):
    application, prepared, output = native_case
    source = prepared["material_packet_sources"]["source-0"]
    if mode == "raw-resume":
        source.pop("record_context")
        output["requirements"][0]["citations"][0]["quote"] = "I validated risk."
    else:
        source["resume_eligible"] = False
        output["selected_source_ids"] = []
        output["selection_rationale"] = []
    reseal(prepared)
    directory = tmp_path / mode
    result = analyze_job(application, prepared, directory, runner=model_runner(output, []))
    schema = saved_schema(directory)
    encoded = json.dumps(schema)
    assert encoded.count('"source-0"') == 1
    assert encoded.count('"confirmed-language"') == 1
    assert all(definition.get("enum") != [] for definition in schema["$defs"].values())
    assert allowed_ids(schema, {"$ref": "#/$defs/KnownSourceID"}) == {
        "source-0",
        "confirmed-language",
    }
    if mode == "raw-resume":
        assert allowed_ids(schema, {"$ref": "#/$defs/NativeSourceID"}) == {"confirmed-language"}
        assert allowed_ids(schema, {"$ref": "#/$defs/RawSourceID"}) == {"source-0"}
        assert allowed_ids(schema, schema["properties"]["selected_source_ids"]["items"]) == {
            "source-0"
        }
        assert result["requirements"][0]["citations"][0]["quote"] == "I validated risk."
    else:
        assert "ResumeSourceID" not in schema["$defs"]
        assert "RawSourceID" not in schema["$defs"]
        assert schema["properties"]["selected_source_ids"]["maxItems"] == 0
        assert schema["properties"]["selection_rationale"]["maxItems"] == 0
        assert result["selected_source_ids"] == []


def test_the_claude_call_names_the_user_for_its_keychain_login(monkeypatch):
    from career_evidence_graph.application_second_opinion import _claude_environment

    # Installed MC-11: without USER and LOGNAME the CLI reported "Not logged in".
    for name in ("USER", "LOGNAME"):
        monkeypatch.delenv(name, raising=False)
    environment = _claude_environment(Path("/tmp/claude-config"))
    assert environment["USER"] and environment["LOGNAME"] == environment["USER"]
    assert environment["CLAUDE_CONFIG_DIR"] == "/tmp/claude-config"
