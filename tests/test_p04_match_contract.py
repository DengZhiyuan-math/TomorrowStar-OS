"""Recorded P04 contract cases verify bindings, not model semantic quality."""

import json
import subprocess
import sys
from copy import deepcopy

import pytest
import test_normal_retrieval_pipeline as recorded
from test_application_information import answer, library_with, tree_bytes
from test_application_match import model_runner
from test_canonical_career_sources import canonical as canonical
from test_normal_retrieval_pipeline import APPLICATION, RecordedPipeline, requirement, thin

from career_evidence_graph.application_match import analyze_job
from career_evidence_graph.application_worker import digest
from career_evidence_graph.career_portal_data import PortalDataError


def test_loaded_controller_identity_includes_inference_helpers(monkeypatch):
    from career_evidence_graph import application_inference, loaded_code

    loaded_code.load_controller_modules()
    before = loaded_code.loaded_runtime_revision("controller")
    assert before is not None
    helper = application_inference._check_expression
    monkeypatch.setattr(
        helper,
        "__code__",
        helper.__code__.replace(co_consts=(*helper.__code__.co_consts, "Synthetic policy change")),
    )
    assert loaded_code.loaded_runtime_revision("controller") != before


def inference_fixture(output, context, *, inference_type="semantic"):
    """A pre-recorded grounded conclusion; this function does not assess ability."""
    for row, template in zip(output["requirements"], context["match_requirements"], strict=True):
        row["inference"] = {
            "requirement_id": template["scoring_framework"]["requirement_id"],
            "type": inference_type,
            "relation": {
                "supported": "supports",
                "partial": "partial_support",
                "gap": "contradicts",
                "unknown": "unresolved",
            }[row["judgment"]],
            "basis": "The cited recorded work supports the stated capability across labels.",
            "expression_scope": ""
            if row["judgment"] == "unknown"
            else "Describe the cited work within its recorded responsibility.",
            "calculation": None,
        }


def transform_evaluation(monkeypatch, transform):
    def runner(output, calls):
        def execute(config, prompt, **kwargs):
            schema = json.loads(config.output_schema.read_text())
            changed = deepcopy(output)
            if schema.get("title") == "_ControlledOutput":
                context = json.loads(prompt.rsplit("\n", 1)[1])
                inference_fixture(changed, context)
                transform(changed, context)
            return model_runner(changed, calls)(config, prompt, **kwargs)

        return execute

    monkeypatch.setattr(recorded, "model_runner", runner)


def run_case(canonical, tmp_path, name, requirements, *, information=None, **kwargs):
    library, _, _, base, *_ = canonical
    runner = RecordedPipeline(requirements, **kwargs)
    result = analyze_job(
        APPLICATION,
        thin(canonical),
        tmp_path / name,
        runner=runner,
        source_loader=lambda ids: library.snapshot_for_analysis(base, ids),
        information_library=information if information is not None else library_with(),
    )
    return result, runner


def test_inference_receipt_is_bound_to_fixed_inputs_and_program_owned_literal_facts(
    canonical, tmp_path, monkeypatch
):
    transform_evaluation(monkeypatch, lambda output, context: None)
    result, runner = run_case(
        canonical,
        tmp_path,
        "semantic",
        [requirement("Experience spanning different scientific fields")],
    )
    receipt = result["inference_result"]
    row = result["requirements"][0]
    inference = row["inference"]
    assert inference["type"] == "semantic"
    assert inference["requirement_id"] == row["scoring_framework"]["requirement_id"]
    assert inference["relation"] == "supports"
    assert inference["facts"]
    for fact, source in zip(inference["facts"], row["sources"], strict=True):
        assert fact["id"] == "fact-" + digest({k: v for k, v in fact.items() if k != "id"})
        assert all(
            fact[key] == source[key]
            for key in ("source_id", "source_revision", "quote", "quote_start", "quote_end")
        )
    assert receipt["job_brief_revision"] == result["job_brief"]["revision"]
    assert receipt["material_packet_revision"] == result["material_packet"]["revision"]
    assert receipt["revision"] == digest({k: v for k, v in receipt.items() if k != "revision"})
    assert runner.phases == ["plan", "evaluate"]
    assert len(runner.brief_calls) == 1
    assert len(result["retrieval"]["evaluations"]) == 1


def test_direct_and_semantic_inferences_keep_the_same_fixed_business_score(
    canonical, tmp_path, monkeypatch
):
    results = []
    for kind in ("direct", "semantic"):
        transform_evaluation(
            monkeypatch,
            lambda output, context, kind=kind: output["requirements"][0]["inference"].update(
                type=kind
            ),
        )
        result, _ = run_case(
            canonical, tmp_path, kind, [requirement("Work spanning scientific disciplines")]
        )
        results.append(result)
    assert results[0]["score"] == results[1]["score"]
    assert results[1]["score"]["lower"] == results[1]["score"]["upper"] == 100


@pytest.mark.parametrize(
    "text",
    [
        "Use English professionally with a research team",
        "Explain findings clearly in the working language",
        "Collaborate across language boundaries using English",
    ],
)
def test_unexamined_explicit_self_report_survives_requirement_paraphrases(
    canonical, tmp_path, monkeypatch, text
):
    transform_evaluation(monkeypatch, lambda output, context: None)
    information = library_with(answer("English fluency", "professional"))
    before = deepcopy(information)
    career_before = tree_bytes(canonical[1])
    result, runner = run_case(
        canonical,
        tmp_path,
        "self-report",
        [requirement(text, hard=True)],
        information=information,
        select=False,
    )
    assert result["score"]["lower"] == result["score"]["upper"] == 100
    assert result["score"]["eligibility"] == "supported"
    assert result["selected_source_ids"] == []
    assert all(
        source["source_kind"] == "confirmed_information"
        for source in result["requirements"][0]["sources"]
    )
    assert runner.phases == ["plan", "evaluate"]
    assert information == before
    assert tree_bytes(canonical[1]) == career_before


def test_missing_fact_keeps_interval_and_qualification_separate(canonical, tmp_path, monkeypatch):
    transform_evaluation(monkeypatch, lambda output, context: None)
    result, _ = run_case(
        canonical,
        tmp_path,
        "unknown",
        [
            requirement("Communicate professionally using English"),
            requirement("Use another language", hard=True),
        ],
        information=library_with(answer("English fluency", "professional")),
        select=False,
    )
    assert result["score"]["lower"] == 50
    assert result["score"]["upper"] == 100
    assert result["score"]["eligibility"] == "needs_input"
    assert result["material_packet"]["status"] == "complete"
    unknown = result["requirements"][1]
    assert unknown["judgment"] == "unknown"
    assert unknown["inference"]["relation"] == "unresolved"
    assert unknown["inference"]["expression_scope"] == ""
    assert unknown["inference"]["facts"] == []


@pytest.mark.parametrize(
    ("field", "value", "code"),
    [
        # Native requirement_id and relation are bound by the program; the native
        # citation tests cover those redundant recorded fields separately.
        ("expression_scope", "Use CEFR C2 with professional fluency.", "match_inference_invalid"),
        ("expression_scope", "Delivered 987654 successful projects.", "match_inference_invalid"),
        ("calculation", {"kind": "invented"}, "match_model_invalid"),
    ],
)
def test_invalid_inference_fails_without_publishing_a_score(
    canonical, tmp_path, monkeypatch, field, value, code
):
    transform_evaluation(
        monkeypatch,
        lambda output, context: output["requirements"][0]["inference"].update({field: value}),
    )
    with pytest.raises(PortalDataError) as error:
        run_case(
            canonical,
            tmp_path,
            "invalid",
            [requirement("English communication")],
            information=library_with(answer("English fluency", "professional")),
            select=False,
        )
    assert error.value.code == code
    assert not list((tmp_path / "invalid").rglob("analysis.json"))


def test_selection_order_and_duplicate_source_references_do_not_change_background_score(
    canonical, tmp_path, monkeypatch
):
    results = []
    for mode in ("none", "forward", "reverse", "duplicate"):

        def selection(output, context, mode=mode):
            row = output["requirements"][0]
            sources = context["sources"]
            citations = [
                {"source_id": source["source_id"], "quote": source["text"].splitlines()[0]}
                for source in sources
            ]
            row["source_ids"] = [source["source_id"] for source in sources]
            row["citations"] = citations
            if mode == "duplicate":
                row["source_ids"] *= 2
                row["citations"] *= 2
            selected = [] if mode == "none" else [source["source_id"] for source in sources]
            if mode == "reverse":
                selected.reverse()
            output["selected_source_ids"] = selected
            output["selection_rationale"] = [
                {
                    "source_id": source_id,
                    "business_relevance": "Recorded relevant context.",
                    "evidence_role": "transferable",
                }
                for source_id in selected
            ]

        transform_evaluation(monkeypatch, selection)
        result, _ = run_case(
            canonical, tmp_path, mode, [requirement("Work across scientific disciplines")]
        )
        results.append(result)
    assert results[0]["selected_source_ids"] == []
    assert results[1]["selected_source_ids"]
    assert results[2]["selected_source_ids"] == list(reversed(results[1]["selected_source_ids"]))
    assert all(result["score"] == results[0]["score"] for result in results)
    assert (
        results[3]["requirements"][0]["inference"]["facts"]
        == results[1]["requirements"][0]["inference"]["facts"]
    )


def test_synthetic_cli_emits_controlled_inferences_only_for_the_new_schema(tmp_path):
    from career_evidence_graph.application_worker_fixtures import _FIXTURE_PYTHON

    role = {
        "business_objective": "Recorded fixture objective",
        "work_outputs": ["Fixture"],
        "methods_role": "Literal source replay only",
    }
    context = {
        "job": {"job_description": "Python\nRust", "company": "Synthetic"},
        "job_brief": {"role_understanding": role},
        "match_requirements": [
            {
                "text": text,
                "importance": "required",
                "hard_condition": False,
                "scoring_framework": {"requirement_id": "req-" + text.lower()},
            }
            for text in ("Python", "Rust")
        ],
        "sources": [
            {
                "source_id": "fixture-source",
                "text": "Implemented Python service.",
                "available": True,
                "match_eligible": True,
                "resume_eligible": True,
                "rewrite_allowed": True,
                "attribution": "User",
            }
        ],
    }
    for title in ("_ModelOutput", "_ControlledOutput"):
        schema_path = tmp_path / (title + ".json")
        schema_path.write_text(
            json.dumps(
                {
                    "title": title,
                    "properties": {
                        key: {}
                        for key in (
                            "role_understanding",
                            "requirements",
                            "selected_source_ids",
                            "selection_rationale",
                            "extracted_fields",
                            "limitations",
                        )
                    },
                }
            )
        )
        process = subprocess.run(
            [
                sys.executable,
                "-I",
                "-B",
                "-c",
                _FIXTURE_PYTHON,
                "exec",
                "--json",
                "--output-schema",
                str(schema_path),
                json.dumps(context),
            ],
            capture_output=True,
            text=True,
            check=True,
        )
        events = [json.loads(line) for line in process.stdout.splitlines()]
        result = next(event["result"] for event in events if event["type"] == "structured_result")
        if title == "_ModelOutput":
            assert all("inference" not in row for row in result["requirements"])
        else:
            first, second = result["requirements"]
            assert first["inference"]["requirement_id"] == "req-python"
            assert first["inference"]["relation"] == "supports"
            assert second["inference"]["requirement_id"] == "req-rust"
            assert second["inference"]["relation"] == "unresolved"
            assert second["inference"]["expression_scope"] == ""
            assert first["inference"]["calculation"] is None
