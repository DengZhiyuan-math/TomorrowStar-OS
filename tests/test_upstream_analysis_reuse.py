"""Completed upstream stages survive implementation changes before P04 dispatch."""

from copy import deepcopy

import pytest
from test_canonical_career_sources import canonical as canonical
from test_normal_retrieval_pipeline import APPLICATION, RecordedPipeline, requirement, thin

from career_evidence_graph import application_match
from career_evidence_graph.application_job_brief import create_job_brief
from career_evidence_graph.career_portal_data import PortalDataError


@pytest.mark.parametrize("implementation_changed", [False, True])
def test_saved_explicit_brief_and_plan_resume_without_reading_them_again(
    canonical, tmp_path, monkeypatch, implementation_changed
):
    library, _, _, base, *_ = canonical
    snapshot = thin(canonical)
    initial = RecordedPipeline([requirement("Scientific collaboration")])
    brief = create_job_brief(APPLICATION, tmp_path / "saved-brief", runner=initial)
    old = tmp_path / "selected"

    def unavailable(ids):
        raise PortalDataError("retrieval_execution_incomplete", "Known body read failure", 409)

    with pytest.raises(PortalDataError):
        application_match.analyze_job(
            APPLICATION,
            snapshot,
            old,
            runner=initial,
            source_loader=unavailable,
            information_library={"status": "unconfigured"},
            job_brief=brief,
        )
    before = {p.relative_to(old): p.read_bytes() for p in old.rglob("*") if p.is_file()}
    if implementation_changed:
        original = application_match.match_configuration

        def changed(environment=None):
            configuration = deepcopy(original(environment))
            configuration["retrieval_engine_sha256"] = "new-reading-implementation"
            configuration["retrieval_component_sha256"]["application_material_packet"] = "new"
            return configuration

        monkeypatch.setattr(application_match, "match_configuration", changed)
    retry = RecordedPipeline(initial.requirements)
    result = application_match.analyze_job(
        APPLICATION,
        snapshot,
        tmp_path / "continued",
        runner=retry,
        source_loader=lambda ids: library.snapshot_for_analysis(base, ids),
        information_library={"status": "unconfigured"},
        resume_from=old,
    )
    assert retry.brief_calls == []
    assert retry.phases == ["evaluate"]
    assert result["job_brief"] == brief
    assert before == {p.relative_to(old): p.read_bytes() for p in old.rglob("*") if p.is_file()}


def test_model_change_cannot_claim_same_upstream_configuration(canonical, tmp_path, monkeypatch):
    library, _, _, base, *_ = canonical
    snapshot = thin(canonical)
    initial = RecordedPipeline([requirement("Scientific collaboration")])
    old = tmp_path / "selected"

    def unavailable(ids):
        raise PortalDataError("retrieval_execution_incomplete", "Known body read failure", 409)

    with pytest.raises(PortalDataError):
        application_match.analyze_job(
            APPLICATION,
            snapshot,
            old,
            runner=initial,
            source_loader=unavailable,
            information_library={"status": "unconfigured"},
        )
    original = application_match.match_configuration

    def changed(environment=None):
        return original(environment) | {"requested_model": "another-model"}

    monkeypatch.setattr(application_match, "match_configuration", changed)
    retry = RecordedPipeline(initial.requirements)
    with pytest.raises(PortalDataError) as caught:
        application_match.analyze_job(
            APPLICATION,
            snapshot,
            tmp_path / "rejected",
            runner=retry,
            source_loader=lambda ids: library.snapshot_for_analysis(base, ids),
            information_library={"status": "unconfigured"},
            resume_from=old,
        )
    assert caught.value.code == "match_resume_invalid"
    assert retry.calls == []


@pytest.mark.parametrize(
    ("fault", "error_code"),
    [("source", "retrieval_execution_incomplete"), ("inference", "match_inference_invalid")],
)
def test_known_invalid_evaluator_keeps_ready_packet_after_implementation_repair(
    canonical, tmp_path, monkeypatch, fault, error_code
):
    from test_application_match import model_runner

    library, _, _, base, *_ = canonical
    snapshot = thin(canonical)
    initial = RecordedPipeline([requirement("Scientific collaboration")])

    def invalid_reference(config, prompt, **kwargs):
        result = initial(config, prompt, **kwargs)
        if config.output_schema.name == "match-schema.json":
            output = deepcopy(result.structured_result)
            if fault == "source":
                output["requirements"][0]["source_ids"] = ["not-delivered"]
                output["requirements"][0]["citations"] = [
                    {"source_id": "not-delivered", "quote": "Not supplied"}
                ]
            else:
                output["requirements"][0]["inference"].update(
                    type="deterministic", calculation=None
                )
            return model_runner(output, [])(config, prompt, **kwargs)
        return result

    old = tmp_path / "known-invalid-evaluator"
    with pytest.raises(PortalDataError) as caught:
        application_match.analyze_job(
            APPLICATION,
            snapshot,
            old,
            runner=invalid_reference,
            source_loader=lambda ids: library.snapshot_for_analysis(base, ids),
            information_library={"status": "unconfigured"},
        )
    assert caught.value.code == error_code
    original = application_match.match_configuration

    def repaired(environment=None):
        return original(environment) | {"engine_sha256": "repaired-native-citations"}

    monkeypatch.setattr(application_match, "match_configuration", repaired)
    retry = RecordedPipeline(initial.requirements)
    result = application_match.analyze_job(
        APPLICATION,
        snapshot,
        tmp_path / "repaired-evaluator",
        runner=retry,
        source_loader=lambda ids: library.snapshot_for_analysis(base, ids),
        information_library={"status": "unconfigured"},
        resume_from=old,
    )
    assert retry.brief_calls == []
    assert retry.read_calls == []
    assert retry.phases == ["evaluate"]
    assert result["material_packet"]["status"] == "complete"
