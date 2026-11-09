"""Follow-up choices must address unresolved requirements and retain completed pages."""

import json
from copy import deepcopy
from pathlib import Path

import pytest
from test_canonical_career_sources import canonical as canonical
from test_normal_retrieval_pipeline import APPLICATION, RecordedPipeline, requirement, thin
from test_requirement_retrieval import REQUIREMENTS, model_runner
from test_requirement_retrieval import inputs as inputs

from career_evidence_graph import application_match
from career_evidence_graph import application_retrieval as retrieval
from career_evidence_graph.career_portal_data import PortalDataError

pytestmark = pytest.mark.usefixtures("planner_path")


def test_followup_schema_requires_a_requested_requirement_or_no_selection(inputs, tmp_path):
    app, snapshot = inputs
    schemas = []
    plan = retrieval.plan_retrieval(
        app,
        snapshot,
        tmp_path / "followup",
        runner=model_runner(
            lambda _: {"requirements": REQUIREMENTS, "selections": []}, [], schemas
        ),
        requirements=REQUIREMENTS,
        unknown_requirements=[0],
    )
    assert plan["selected_candidate_ids"] == []
    indexes = schemas[0]["$defs"]["_Selection"]["properties"]["requirement_indexes"]
    assert indexes["minItems"] == 1


def test_pages_answered_under_the_legacy_followup_schema_are_asked_again(
    inputs, tmp_path, monkeypatch
):
    app, snapshot = inputs
    monkeypatch.setattr(retrieval, "MAX_PAGE_BYTES", 180)
    current_schema = retrieval._page_schema

    def legacy_schema(*args):
        schema = current_schema(*args)
        schema["$defs"]["_Selection"]["properties"]["requirement_indexes"].pop("minItems", None)
        return schema

    def invalid(context):
        return {
            "requirements": REQUIREMENTS,
            "selections": []
            if context["page"] == 1
            else [
                {
                    "candidate_id": "unfamiliar",
                    "requirement_indexes": [],
                    "business_relevance": False,
                    "rationale": "Not relevant to this follow-up.",
                }
            ],
        }

    old = tmp_path / "old" / ("a" * 32)
    with monkeypatch.context() as patch:
        patch.setattr(retrieval, "_page_schema", legacy_schema)
        with pytest.raises(PortalDataError):
            retrieval.plan_retrieval(
                app,
                snapshot,
                old.parent,
                runner=model_runner(invalid, []),
                requirements=REQUIREMENTS,
                unknown_requirements=[0],
                invocation_id=old.name,
            )
    before = {p.relative_to(old): p.read_bytes() for p in old.rglob("*.json")}
    calls = []
    plan = retrieval.plan_retrieval(
        app,
        snapshot,
        tmp_path / "new",
        runner=model_runner(lambda _: {"requirements": REQUIREMENTS, "selections": []}, calls),
        requirements=REQUIREMENTS,
        unknown_requirements=[0],
        resume_from=old,
    )
    # Only an identical question is replayed (Model Call Record): the legacy schema
    # lacked minItems, so its completed page 1 is asked again with page 2.
    assert sorted(call["page"] for call in calls) == [1, 2]
    assert plan["selected_candidate_ids"] == []
    assert before == {p.relative_to(old): p.read_bytes() for p in old.rglob("*.json")}
    replay_calls = []
    retrieval.plan_retrieval(
        app,
        snapshot,
        tmp_path / "replay",
        runner=model_runner(lambda _: pytest.fail("Completed pages must be reused"), replay_calls),
        requirements=REQUIREMENTS,
        unknown_requirements=[0],
        resume_from=Path(plan["directory"]),
    )
    assert replay_calls == []


@pytest.mark.parametrize(
    "alteration",
    [
        "retrieval",
        "engine",
        "model",
        "budget",
        "fact_reader",
        "unknown",
        "marker",
        "schema",
        "result",
        "native_content",
    ],
)
def test_followup_repair_reuses_accepted_evaluator_only_with_known_bound_planner_failure(
    canonical, tmp_path, monkeypatch, alteration
):
    library, _, _, base, *_ = canonical
    snapshot = thin(canonical)
    initial = RecordedPipeline([requirement("Scientific collaboration")], select=False)

    def invalid_followup(config, prompt, **kwargs):
        schema = json.loads(config.output_schema.read_text())
        if schema.get("title") == "_PageResult":
            context = json.loads(prompt.split("CONTEXT_JSON\n", 1)[1])
            if context["unknown_requirement_indexes"] is not None:
                output = {
                    "requirements": initial.requirements,
                    "selections": [
                        {
                            "candidate_id": context["records"][0]["candidate_id"],
                            "requirement_indexes": [],
                            "rationale": "Not relevant to unknown scope.",
                        }
                    ],
                }
                return model_runner(lambda _: output, [])(config, prompt, **kwargs)
        return initial(config, prompt, **kwargs)

    old = tmp_path / "failed-followup"
    with pytest.raises(PortalDataError) as caught:
        application_match.analyze_job(
            APPLICATION,
            snapshot,
            old,
            runner=invalid_followup,
            source_loader=lambda ids: library.snapshot_for_analysis(base, ids),
            information_library={"status": "unconfigured"},
        )
    assert caught.value.code == "retrieval_invalid"
    failed_page = next(old.glob("retrieval/*/page-*/validation-failure.json")).parent
    if alteration == "unknown":
        (failed_page / "validation-failure.json").unlink()
        (failed_page / "result.json").unlink()
    elif alteration in {"marker", "schema"}:
        name = "validation-failure.json" if alteration == "marker" else "schema.json"
        (failed_page / name).write_text("{}")
    elif alteration == "result":
        path = failed_page / "result.json"
        response = json.loads(path.read_text())
        response["prompt_hash"] = "sha256:" + "0" * 64
        path.write_text(json.dumps(response))
    elif alteration == "native_content":
        path = old / "evaluation-1/model-result.json"
        response = json.loads(path.read_text())
        response["structured_result"]["limitations"].append(
            "Changed structured text without native output"
        )
        path.write_text(json.dumps(response))
    before = {p.relative_to(old): p.read_bytes() for p in old.rglob("*") if p.is_file()}
    original = application_match.match_configuration

    def repaired(environment=None):
        config = deepcopy(original(environment))
        config["retrieval_engine_sha256"] = "repaired-followup-recovery"
        config["retrieval_component_sha256"]["application_retrieval"] = "repaired-followup-schema"
        if alteration == "engine":
            config["engine_sha256"] = "changed-evaluator"
        elif alteration == "model":
            config["requested_model"] = "changed-model"
        elif alteration == "budget":
            config["context_limits"]["match_context_bytes"] += 1
        elif alteration == "fact_reader":
            config["retrieval_component_sha256"]["application_material_packet"] = "changed-reader"
        return config

    monkeypatch.setattr(application_match, "match_configuration", repaired)
    retry = RecordedPipeline(initial.requirements, select=False)

    def resume():
        return application_match.analyze_job(
            APPLICATION,
            snapshot,
            tmp_path / "continued",
            runner=retry,
            source_loader=lambda ids: library.snapshot_for_analysis(base, ids),
            information_library={"status": "unconfigured"},
            resume_from=old,
        )

    # Engine and component hashes are provenance: like the retrieval repair itself,
    # an App rebuild alone must not discard the accepted evaluator (batch 1-A).
    if alteration not in {"retrieval", "engine", "fact_reader"}:
        with pytest.raises(PortalDataError):
            resume()
        assert retry.calls == []
        assert before == {p.relative_to(old): p.read_bytes() for p in old.rglob("*") if p.is_file()}
        return
    result = resume()
    assert retry.brief_calls == []
    assert retry.read_calls == []
    assert retry.phases == ["followup"]
    assert result["requirements"][0]["judgment"] == "unknown"
    assert before == {p.relative_to(old): p.read_bytes() for p in old.rglob("*") if p.is_file()}


def test_a_followup_page_that_never_answers_keeps_the_completed_evaluation(canonical, tmp_path):
    """2026-11-08: Keyrock's and Mistral's follow-up page never answered, even in
    360 s, and the whole analysis failed although an evaluation was complete."""
    from career_evidence_graph.codex_cli import CodexCLIError

    library, _, _, base, *_ = canonical
    snapshot = thin(canonical)
    initial = RecordedPipeline([requirement("Scientific collaboration")], select=False)

    def hanging_followup(config, prompt, **kwargs):
        schema = json.loads(config.output_schema.read_text())
        if schema.get("title") == "_PageResult":
            context = json.loads(prompt.split("CONTEXT_JSON\n", 1)[1])
            if context["unknown_requirement_indexes"] is not None:
                raise CodexCLIError("Recorded follow-up timeout")
        return initial(config, prompt, **kwargs)

    result = application_match.analyze_job(
        APPLICATION,
        snapshot,
        tmp_path / "analysis",
        runner=hanging_followup,
        source_loader=lambda ids: library.snapshot_for_analysis(base, ids),
        information_library={"status": "unconfigured"},
    )
    assert result["job_brief"]["groups"][0]["label"] == "Scientific collaboration"
    assert "evaluate" in initial.phases
