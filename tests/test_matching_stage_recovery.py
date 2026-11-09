"""Explicit analysis retries keep successful JD and material-reading work."""

from pathlib import Path

import pytest
from test_canonical_career_sources import canonical as canonical
from test_normal_retrieval_pipeline import APPLICATION, RecordedPipeline, requirement, thin

from career_evidence_graph._vendor import job_apply_store as helper
from career_evidence_graph.application_match import analyze_job
from career_evidence_graph.career_portal_data import PortalDataError
from career_evidence_graph.codex_cli import CodexCLIError

pytestmark = pytest.mark.usefixtures("planner_path")


def terminal_model_failure(message):
    import json

    return CodexCLIError(
        message,
        raw_stdout_jsonl="\n".join(
            json.dumps(event)
            for event in (
                {"type": "thread.started", "thread_id": "synthetic-known-failed-turn"},
                {"type": "turn.started"},
                {"type": "error", "message": message},
                {"type": "turn.failed", "error": {"message": message}},
            )
        )
        + "\n",
    )


def test_failed_evaluation_retries_without_repeating_brief_selection_or_reading(
    canonical, tmp_path
):
    library, _, _, base, *_ = canonical
    snapshot = thin(canonical)
    initial = RecordedPipeline([requirement("Interdisciplinary research")])

    def fail_evaluation(config, prompt, **kwargs):
        if config.output_schema.name == "match-schema.json":
            raise terminal_model_failure("Recorded unavailable evaluator")
        return initial(config, prompt, **kwargs)

    failed = tmp_path / "failed"
    with pytest.raises(PortalDataError) as error:
        analyze_job(
            APPLICATION,
            snapshot,
            failed,
            runner=fail_evaluation,
            source_loader=lambda ids: library.snapshot_for_analysis(base, ids),
            information_library={"status": "unconfigured"},
        )
    assert error.value.code == "match_model_unavailable"
    before = {p.relative_to(failed): p.read_bytes() for p in failed.rglob("*") if p.is_file()}
    retry = RecordedPipeline(initial.requirements)
    result = analyze_job(
        APPLICATION,
        snapshot,
        tmp_path / "retry",
        runner=retry,
        source_loader=lambda ids: library.snapshot_for_analysis(base, ids),
        information_library={"status": "unconfigured"},
        resume_from=failed,
    )
    assert retry.brief_calls == []
    assert retry.read_calls == []
    assert retry.phases == ["evaluate"]
    assert result["job_brief"]["groups"][0]["label"] == "Interdisciplinary research"
    assert result["retrieval"]["status"] == "retrieved"
    assert before == {
        p.relative_to(failed): p.read_bytes() for p in failed.rglob("*") if p.is_file()
    }


def sent_schemas(runner):
    """Wrap a runner to list the schema file of every call it actually sends."""
    names = []

    def run(config, prompt, **kwargs):
        names.append(config.output_schema.name)
        return runner(config, prompt, **kwargs)

    run.names = names
    return run


def test_an_unknown_evaluation_is_sent_again_on_retry(canonical, tmp_path):
    # An unknown model result has no outside effect; the retry sends only that call
    # again and replays the earlier stages (Model Call Record, decided 2026-11-09).
    library, _, _, base, *_ = canonical
    snapshot = thin(canonical)
    initial = RecordedPipeline([requirement("Interdisciplinary research")])

    def interrupted(config, prompt, **kwargs):
        if config.output_schema.name == "match-schema.json":
            raise KeyboardInterrupt("Simulated backend interruption during evaluation")
        return initial(config, prompt, **kwargs)

    previous = tmp_path / "interrupted"
    with pytest.raises(KeyboardInterrupt):
        analyze_job(
            APPLICATION,
            snapshot,
            previous,
            runner=interrupted,
            source_loader=lambda ids: library.snapshot_for_analysis(base, ids),
            information_library={"status": "unconfigured"},
        )
    retry = sent_schemas(RecordedPipeline(initial.requirements))
    report = analyze_job(
        APPLICATION,
        snapshot,
        tmp_path / "retry",
        runner=retry,
        source_loader=lambda ids: library.snapshot_for_analysis(base, ids),
        information_library={"status": "unconfigured"},
        resume_from=previous,
    )
    assert report["requirements"]
    assert retry.names == ["match-schema.json"]


@pytest.mark.parametrize("receipt_name", ["model-result.json", "analysis.json"])
def test_saved_evaluator_response_is_adopted_after_backend_interrupt(
    canonical, tmp_path, monkeypatch, receipt_name
):
    library, _, _, base, *_ = canonical
    snapshot = thin(canonical)
    initial = RecordedPipeline([requirement("Interdisciplinary research")])
    failed = tmp_path / "interrupted-after-response"
    write = helper.atomic_write_json

    def interrupt_after_result(path, value):
        write(path, value)
        if path == failed / "evaluation-1" / receipt_name:
            raise KeyboardInterrupt("Backend stopped after durable model receipt")

    with monkeypatch.context() as patch:
        patch.setattr(helper, "atomic_write_json", interrupt_after_result)
        with pytest.raises(KeyboardInterrupt):
            analyze_job(
                APPLICATION,
                snapshot,
                failed,
                runner=initial,
                source_loader=lambda ids: library.snapshot_for_analysis(base, ids),
                information_library={"status": "unconfigured"},
            )
    retry = RecordedPipeline(initial.requirements)
    result = analyze_job(
        APPLICATION,
        snapshot,
        tmp_path / "adopt-response",
        runner=retry,
        source_loader=lambda ids: library.snapshot_for_analysis(base, ids),
        information_library={"status": "unconfigured"},
        resume_from=failed,
    )
    assert retry.calls == []
    assert result["retrieval"]["status"] == "retrieved"


def test_a_retry_interrupted_during_its_evaluation_sends_it_again(canonical, tmp_path):
    library, _, _, base, *_ = canonical
    snapshot = thin(canonical)
    first = RecordedPipeline([requirement("Interdisciplinary research")])

    def failed(config, prompt, **kwargs):
        if config.output_schema.name == "match-schema.json":
            raise terminal_model_failure("Known initial failure")
        return first(config, prompt, **kwargs)

    original = tmp_path / "first-known-failure"
    with pytest.raises(PortalDataError):
        analyze_job(
            APPLICATION,
            snapshot,
            original,
            runner=failed,
            source_loader=lambda ids: library.snapshot_for_analysis(base, ids),
            information_library={"status": "unconfigured"},
        )

    def interrupted(*args, **kwargs):
        raise KeyboardInterrupt("The retry has an unacknowledged model call")

    unknown = tmp_path / "interrupted-retry"
    with pytest.raises(KeyboardInterrupt):
        analyze_job(
            APPLICATION,
            snapshot,
            unknown,
            runner=interrupted,
            source_loader=lambda ids: library.snapshot_for_analysis(base, ids),
            information_library={"status": "unconfigured"},
            resume_from=original,
        )
    final = sent_schemas(RecordedPipeline(first.requirements))
    report = analyze_job(
        APPLICATION,
        snapshot,
        tmp_path / "second-retry",
        runner=final,
        source_loader=lambda ids: library.snapshot_for_analysis(base, ids),
        information_library={"status": "unconfigured"},
        resume_from=unknown,
    )
    # The interrupted retry's evaluation is sent again; nothing earlier is repeated.
    assert report["requirements"]
    assert final.names == ["match-schema.json"]


def test_known_jd_failure_can_retry_only_the_unfinished_stage(canonical, tmp_path):
    library, _, _, base, *_ = canonical
    snapshot = thin(canonical)

    def failed(*args, **kwargs):
        raise terminal_model_failure("JD service unavailable")

    first = tmp_path / "failed-jd"
    with pytest.raises(PortalDataError):
        analyze_job(
            APPLICATION,
            snapshot,
            first,
            runner=failed,
            source_loader=lambda ids: library.snapshot_for_analysis(base, ids),
            information_library={"status": "unconfigured"},
        )
    retry = RecordedPipeline([requirement("Interdisciplinary research")])
    result = analyze_job(
        APPLICATION,
        snapshot,
        tmp_path / "retried-jd",
        runner=retry,
        source_loader=lambda ids: library.snapshot_for_analysis(base, ids),
        information_library={"status": "unconfigured"},
        resume_from=first,
    )
    assert len(retry.brief_calls) == 1
    assert retry.phases == ["plan", "evaluate"]
    assert result["retrieval"]["status"] == "retrieved"


def test_second_round_failure_preserves_first_round_evidence_location(canonical, tmp_path):
    library, _, _, base, *_ = canonical
    snapshot = thin(canonical)
    first = RecordedPipeline(
        [requirement("Interdisciplinary research")], select=False, followup_select=True
    )
    evaluations = 0

    def failed_second(config, prompt, **kwargs):
        nonlocal evaluations
        if config.output_schema.name == "match-schema.json":
            evaluations += 1
            if evaluations == 2:
                raise terminal_model_failure("Second evaluator failed")
        return first(config, prompt, **kwargs)

    failed = tmp_path / "second-round-failure"
    with pytest.raises(PortalDataError):
        analyze_job(
            APPLICATION,
            snapshot,
            failed,
            runner=failed_second,
            source_loader=lambda ids: library.snapshot_for_analysis(base, ids),
            information_library={"status": "unconfigured"},
        )
    retry = RecordedPipeline(first.requirements)
    result = analyze_job(
        APPLICATION,
        snapshot,
        tmp_path / "retry-second-round",
        runner=retry,
        source_loader=lambda ids: library.snapshot_for_analysis(base, ids),
        information_library={"status": "unconfigured"},
        resume_from=failed,
    )
    assert retry.brief_calls == []
    assert retry.read_calls == []
    assert retry.phases == ["evaluate"]
    assert len(result["retrieval"]["evaluations"]) == 2
    for receipt in result["retrieval"]["evaluations"]:
        assert (
            Path(receipt["analysis_directory"]) / receipt["directory"] / "analysis.json"
        ).is_file()


@pytest.mark.parametrize("followup", [False, True])
def test_an_unknown_planner_call_is_sent_again(canonical, tmp_path, followup):
    import json

    library, _, _, base, *_ = canonical
    snapshot = thin(canonical)
    first = RecordedPipeline([requirement("Interdisciplinary research")], select=False)

    def interrupted(config, prompt, **kwargs):
        if config.output_schema.name == "schema.json":
            context = json.loads(prompt.split("CONTEXT_JSON\n", 1)[1])
            if (context["unknown_requirement_indexes"] is not None) == followup:
                raise KeyboardInterrupt("Planner result is unknown")
        return first(config, prompt, **kwargs)

    origin = tmp_path / "unknown-plan"
    with pytest.raises(KeyboardInterrupt):
        analyze_job(
            APPLICATION,
            snapshot,
            origin,
            runner=interrupted,
            source_loader=lambda ids: library.snapshot_for_analysis(base, ids),
            information_library={"status": "unconfigured"},
        )
    retry = sent_schemas(RecordedPipeline(first.requirements))
    report = analyze_job(
        APPLICATION,
        snapshot,
        tmp_path / "plan-retry",
        runner=retry,
        source_loader=lambda ids: library.snapshot_for_analysis(base, ids),
        information_library={"status": "unconfigured"},
        resume_from=origin,
    )
    # The unknown planner page is sent again; the job brief is replayed.
    assert report["requirements"]
    assert "job-brief-schema.json" not in retry.names
    assert "schema.json" in retry.names


def test_saved_empty_followup_is_not_repeated_after_publication_interrupt(
    canonical, tmp_path, monkeypatch
):
    library, _, _, base, *_ = canonical
    snapshot = thin(canonical)
    first = RecordedPipeline([requirement("Interdisciplinary research")], select=False)
    failed = tmp_path / "finished-empty-plan"
    write = helper.atomic_write_json

    def interrupt_publication(path, value):
        write(path, value)
        if path == failed / "analysis.json":
            raise KeyboardInterrupt("Backend stopped after final publication")

    with monkeypatch.context() as patch:
        patch.setattr(helper, "atomic_write_json", interrupt_publication)
        with pytest.raises(KeyboardInterrupt):
            analyze_job(
                APPLICATION,
                snapshot,
                failed,
                runner=first,
                source_loader=lambda ids: library.snapshot_for_analysis(base, ids),
                information_library={"status": "unconfigured"},
            )
    assert first.phases == ["plan", "evaluate", "followup"]
    retry = RecordedPipeline(first.requirements)
    result = analyze_job(
        APPLICATION,
        snapshot,
        tmp_path / "adopt-empty-plan",
        runner=retry,
        source_loader=lambda ids: library.snapshot_for_analysis(base, ids),
        information_library={"status": "unconfigured"},
        resume_from=failed,
    )
    assert retry.calls == []
    assert result["requirements"][0]["judgment"] == "unknown"
    assert len(result["retrieval"]["plans"]) == 2


def test_reading_retry_then_durable_evaluation_interrupt_adopts_without_more_provider_calls(
    canonical, tmp_path, monkeypatch
):
    import json
    from copy import deepcopy

    from test_application_match import model_runner
    from test_structured_career_store import facts

    from career_evidence_graph.career_experiences import ExperienceStore

    library, career_root, _, base, *_ = canonical
    content = facts(candidate_id="unseen-identity")
    content["facts"][0]["text"] = "Studied cross-domain models with biology collaborators."
    content["facts"].append(
        deepcopy(content["facts"][0])
        | {"id": "fact-2", "text": "Unrelated recorded detail. " * 2800}
    )
    ExperienceStore(career_root).save("unseen-identity", title=content["title"], content=content)
    snapshot = thin(canonical)

    class FailFirstReading(RecordedPipeline):
        reading_attempts = 0

        def __call__(self, config, prompt, **kwargs):
            schema = json.loads(config.output_schema.read_text())
            if set(schema.get("properties", {})) == {"selections"}:
                self.reading_attempts += 1
                if self.reading_attempts == 1:
                    raise terminal_model_failure("Recorded first material-reading failure")
                data = json.loads(prompt.split("CONTEXT_JSON\n", 1)[1])
                self.read_calls.append(data)
                supplied = data.get("source_ranges", [data])[0]
                return model_runner(
                    {
                        "selections": [
                            {
                                "source_id": supplied["source"]["source_id"],
                                "requirement_indexes": [0],
                            }
                        ]
                    },
                    self.calls,
                )(config, prompt, **kwargs)
            return super().__call__(config, prompt, **kwargs)

    runner = FailFirstReading([requirement("Interdisciplinary research")])
    first = tmp_path / "failed-reading"
    with pytest.raises(PortalDataError):
        analyze_job(
            APPLICATION,
            snapshot,
            first,
            runner=runner,
            source_loader=lambda ids: library.snapshot_for_analysis(base, ids),
            information_library={"status": "unconfigured"},
        )
    assert runner.reading_attempts == 1
    assert runner.phases == ["plan"]
    first_files = {
        path.relative_to(first): path.read_bytes() for path in first.rglob("*") if path.is_file()
    }
    second = tmp_path / "interrupted-evaluation-after-reading-retry"
    write = helper.atomic_write_json

    def interrupt_after_evaluator_receipt(path, value):
        write(path, value)
        if path == second / "evaluation-1/model-result.json":
            raise KeyboardInterrupt("Backend stopped after the fresh durable P04 receipt")

    with monkeypatch.context() as patch:
        patch.setattr(helper, "atomic_write_json", interrupt_after_evaluator_receipt)
        with pytest.raises(KeyboardInterrupt):
            analyze_job(
                APPLICATION,
                snapshot,
                second,
                runner=runner,
                source_loader=lambda ids: library.snapshot_for_analysis(base, ids),
                information_library={"status": "unconfigured"},
                resume_from=first,
            )
    assert runner.reading_attempts > 1
    assert runner.read_calls
    assert len(runner.brief_calls) == 1
    assert runner.phases == ["plan", "evaluate"]
    assert (second / "evaluation-1/model-result.json").is_file()
    second_files = {
        path.relative_to(second): path.read_bytes() for path in second.rglob("*") if path.is_file()
    }
    final_runner = RecordedPipeline(runner.requirements)
    result = analyze_job(
        APPLICATION,
        snapshot,
        tmp_path / "adopt-fresh-evaluation",
        runner=final_runner,
        source_loader=lambda ids: library.snapshot_for_analysis(base, ids),
        information_library={"status": "unconfigured"},
        resume_from=second,
    )
    assert final_runner.calls == []
    assert result["retrieval"]["status"] == "retrieved"
    assert first_files == {
        path.relative_to(first): path.read_bytes() for path in first.rglob("*") if path.is_file()
    }
    assert second_files == {
        path.relative_to(second): path.read_bytes() for path in second.rglob("*") if path.is_file()
    }


def test_an_evaluation_refused_on_size_before_its_prompt_is_retried(
    canonical, tmp_path, monkeypatch
):
    """2026-11-08, UBS: the context-size check refused the evaluation before its
    prompt was saved; the retry must evaluate, not wait on an unknown call."""
    from career_evidence_graph import application_match

    library, _, _, base, *_ = canonical
    snapshot = thin(canonical)
    initial = RecordedPipeline([requirement("Interdisciplinary research")])

    def refuse(*_args, **_kwargs):
        raise PortalDataError("retrieval_execution_incomplete", "too large", 409)

    real = application_match._prompt_context
    monkeypatch.setattr(application_match, "_prompt_context", refuse)
    refused = tmp_path / "refused"
    with pytest.raises(PortalDataError) as error:
        analyze_job(
            APPLICATION,
            snapshot,
            refused,
            runner=initial,
            source_loader=lambda ids: library.snapshot_for_analysis(base, ids),
            information_library={"status": "unconfigured"},
        )
    assert error.value.code == "retrieval_execution_incomplete"
    monkeypatch.setattr(application_match, "_prompt_context", real)
    retry = RecordedPipeline(initial.requirements)
    result = analyze_job(
        APPLICATION,
        snapshot,
        tmp_path / "retry",
        runner=retry,
        source_loader=lambda ids: library.snapshot_for_analysis(base, ids),
        information_library={"status": "unconfigured"},
        resume_from=refused,
    )
    assert retry.brief_calls == [] and retry.read_calls == []
    assert retry.phases == ["evaluate"]
    assert result["job_brief"]["groups"][0]["label"] == "Interdisciplinary research"


@pytest.mark.parametrize(
    ("result", "resumable"),
    [
        ({"status": "failed", "error_type": "CodexCLIError"}, True),
        ({"status": "failed", "error_type": "TimeoutExpired"}, True),
        # No recorded end: the call may still have answered.
        (None, False),
        ({"status": "ok"}, False),
    ],
)
def test_a_recorded_failed_followup_resumes_after_an_app_rebuild(tmp_path, result, resumable):
    """2026-11-08, Keyrock: a follow-up page timed out; after a rebuild only engine
    provenance differed, and resumption still demanded a validation-failure marker."""
    import json

    from career_evidence_graph.application_matching_pipeline import _same_upstream_binding

    page = tmp_path / "retrieval" / "page-0001"
    page.mkdir(parents=True)
    if result is not None:
        (page / "result.json").write_text(json.dumps(result))
    configuration = {"evaluation_model": "m", "engine_sha256": "old"}
    saved = {
        "phase": "planning",
        "planner_kind": "followup",
        "planner_pending": True,
        "planner_origin": str(tmp_path / "retrieval"),
        "binding": {"application_id": "a", "configuration": configuration},
    }
    binding = {"application_id": "a", "configuration": configuration | {"engine_sha256": "new"}}
    assert _same_upstream_binding(saved, binding) is resumable
