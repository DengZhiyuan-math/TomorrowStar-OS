"""Completed upstream stages survive implementation changes before P04 dispatch."""

from copy import deepcopy

import pytest
import test_normal_retrieval_pipeline as recorded
from test_application_match import model_runner
from test_canonical_career_sources import canonical as canonical
from test_normal_retrieval_pipeline import APPLICATION, RecordedPipeline, requirement, thin

from career_evidence_graph import application_match
from career_evidence_graph.application_job_brief import create_job_brief
from career_evidence_graph.career_portal_data import PortalDataError

pytestmark = pytest.mark.usefixtures("planner_path")


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


def test_a_model_change_analyses_the_job_from_the_start(canonical, tmp_path, monkeypatch):
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
    before = {p.relative_to(old): p.read_bytes() for p in old.rglob("*") if p.is_file()}
    # The changed model cannot reuse the earlier phases; nothing earlier needs guarding,
    # so the job is analysed again instead of stopping (Model Call Record, 2026-11-09).
    result = application_match.analyze_job(
        APPLICATION,
        snapshot,
        tmp_path / "fresh",
        runner=retry,
        source_loader=lambda ids: library.snapshot_for_analysis(base, ids),
        information_library={"status": "unconfigured"},
        resume_from=old,
    )
    assert result["requirements"]
    assert len(retry.brief_calls) == 1
    assert before == {p.relative_to(old): p.read_bytes() for p in old.rglob("*") if p.is_file()}


# An unusable citation now only withholds that requirement (test_native_fact_citations).
@pytest.mark.parametrize(("fault", "error_code"), [("inference", "match_inference_invalid")])
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


@pytest.mark.parametrize("changed", ["engine_sha256", "executable_metadata_revision"])
def test_rejected_job_brief_is_read_again_after_an_app_or_codex_update(
    canonical, tmp_path, monkeypatch, changed
):
    library, _, _, base, *_ = canonical
    snapshot = thin(canonical)
    loader = lambda ids: library.snapshot_for_analysis(base, ids)  # noqa: E731
    initial = RecordedPipeline([requirement("Scientific collaboration")])
    old = tmp_path / "rejected"

    def unquoted(output, calls):
        if "groups" in output:
            output = deepcopy(output)
            output["groups"][0]["jd_quote"] = "Unrecorded duty"
        return model_runner(output, calls)

    with monkeypatch.context() as patch, pytest.raises(PortalDataError) as rejected:
        patch.setattr(recorded, "model_runner", unquoted)
        application_match.analyze_job(
            APPLICATION,
            snapshot,
            old,
            runner=initial,
            source_loader=loader,
            information_library={"status": "unconfigured"},
        )
    assert rejected.value.code == "job_brief_invalid"
    # Installed MC-11: an App or Codex CLI update between the rejection and Continue
    # changed the configuration; the rejected reading reuses nothing, so it reads again.
    original = application_match.match_configuration
    monkeypatch.setattr(
        application_match,
        "match_configuration",
        lambda environment=None: original(environment) | {changed: "updated"},
    )
    retry = RecordedPipeline(initial.requirements)
    result = application_match.analyze_job(
        APPLICATION,
        snapshot,
        tmp_path / "retry",
        runner=retry,
        source_loader=loader,
        information_library={"status": "unconfigured"},
        resume_from=old,
    )
    assert len(retry.brief_calls) == 1
    assert result["job_brief"]["groups"][0]["jd_quote"] != "Unrecorded duty"


def test_retry_after_a_configuration_change_reads_the_rejected_job_brief_again(
    canonical, tmp_path, monkeypatch
):

    library, _, _, base, *_ = canonical
    snapshot = thin(canonical)
    root = tmp_path / "analyses"
    options = {"source_loader": lambda ids: library.snapshot_for_analysis(base, ids)}
    initial = RecordedPipeline([requirement("Scientific collaboration")])

    def unquoted(output, calls):
        if "groups" in output:
            output = deepcopy(output)
            output["groups"][0]["jd_quote"] = "Unrecorded duty"
        return model_runner(output, calls)

    with monkeypatch.context() as patch, pytest.raises(PortalDataError) as rejected:
        patch.setattr(recorded, "model_runner", unquoted)
        application_match.Analysis(root, runner=initial, **options).prepare(
            APPLICATION, snapshot, request_id="1" * 32
        )
    assert rejected.value.code == "job_brief_invalid"
    original = application_match.match_configuration
    monkeypatch.setattr(
        application_match,
        "match_configuration",
        lambda environment=None: original(environment) | {"engine_sha256": "updated"},
    )
    retry = RecordedPipeline(initial.requirements)
    progress = application_match.Analysis(root, runner=retry, **options).prepare(
        APPLICATION, snapshot, request_id="3" * 32, recovery_candidates=["1" * 32]
    )
    assert progress["status"] == "complete"
    assert len(retry.brief_calls) == 1


def test_a_packet_refused_for_size_after_every_read_is_a_known_failure(
    canonical, tmp_path, monkeypatch
):

    library, _, _, base, *_ = canonical
    snapshot = thin(canonical)
    root = tmp_path / "analyses"
    options = {"source_loader": lambda ids: library.snapshot_for_analysis(base, ids)}
    monkeypatch.setenv("TOMORROWSTAR_MATERIAL_CONTEXT_BYTES", "300")
    first = RecordedPipeline([requirement("Scientific collaboration")])
    with pytest.raises(PortalDataError) as caught:
        application_match.Analysis(root, runner=first, **options).prepare(
            APPLICATION, snapshot, request_id="1" * 32
        )
    assert caught.value.code == "retrieval_execution_incomplete"
    analysis = application_match.Analysis(root, runner=first, **options)
    # Installed MC-11: every reading call was receipted before the size refusal,
    # so the attempt hides no model result and a new request may run.
    assert analysis.progress("1" * 32)["status"] == "failed"
    retry = RecordedPipeline(first.requirements)
    with pytest.raises(PortalDataError) as again:
        application_match.Analysis(root, runner=retry, **options).prepare(
            APPLICATION, snapshot, request_id="2" * 32
        )
    assert again.value.code == "retrieval_execution_incomplete"
    # The resumed attempt points at the recovered reading but proves its own packet.
    assert analysis.progress("2" * 32)["status"] == "failed"
    monkeypatch.delenv("TOMORROWSTAR_MATERIAL_CONTEXT_BYTES")
    # Installed MC-11: the trimmed source view changed the information revision,
    # so the refused reading could not be resumed; it is read again from the start.
    # A changed job field stands in for that changed binding.
    fresh = RecordedPipeline(first.requirements)
    moved = APPLICATION | {"location": "Basel"}
    progress = application_match.Analysis(root, runner=fresh, **options).prepare(
        moved, snapshot, request_id="3" * 32, recovery_candidates=["2" * 32, "1" * 32]
    )
    assert progress["status"] == "complete"
    assert len(fresh.brief_calls) == 1
    packet = root / ("1" * 32) / "material-packet-1" / "material-packet.json"
    packet.write_text(packet.read_text().replace('"failed"', '"needs_recheck"', 1))
    assert analysis.progress("1" * 32)["status"] == "needs_recheck"


def test_a_rejected_evaluation_with_changed_inputs_is_analysed_again_from_the_start(
    canonical, tmp_path, monkeypatch
):
    from test_application_match import model_runner

    library, _, _, base, *_ = canonical
    snapshot = thin(canonical)
    initial = RecordedPipeline([requirement("Scientific collaboration")])

    def invalid(config, prompt, **kwargs):
        result = initial(config, prompt, **kwargs)
        if config.output_schema.name == "match-schema.json":
            output = deepcopy(result.structured_result)
            output["requirements"][0]["inference"].update(type="deterministic", calculation=None)
            return model_runner(output, [])(config, prompt, **kwargs)
        return result

    old = tmp_path / "rejected-evaluation"
    options = {
        "source_loader": lambda ids: library.snapshot_for_analysis(base, ids),
        "information_library": {"status": "unconfigured"},
    }
    with pytest.raises(PortalDataError) as caught:
        application_match.analyze_job(APPLICATION, snapshot, old, runner=invalid, **options)
    assert caught.value.code == "match_inference_invalid"
    # Installed MC-11: the Education Record changed the information binding, so the
    # rejected attempt could not be resumed and every retry was refused. A changed
    # job field stands in for that changed binding.
    retry = RecordedPipeline(initial.requirements)
    result = application_match.analyze_job(
        APPLICATION | {"location": "Basel"},
        snapshot,
        tmp_path / "fresh",
        runner=retry,
        resume_from=old,
        **options,
    )
    assert len(retry.brief_calls) == 1
    assert result["material_packet"]["status"] == "complete"
