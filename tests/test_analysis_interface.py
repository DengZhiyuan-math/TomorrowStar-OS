"""Analysis owns saved attempts without reads becoming execution effects."""

import threading
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy

import pytest
from test_application_information import answer, library_with
from test_application_match import match_inputs as match_inputs
from test_application_match import model_output, model_runner
from test_canonical_career_sources import canonical as canonical
from test_career_portal_http import portal as portal
from test_matching_stage_recovery import sent_schemas, terminal_model_failure
from test_normal_retrieval_pipeline import APPLICATION, RecordedPipeline, requirement, thin

from career_evidence_graph.application_match import Analysis, analyze_job
from career_evidence_graph.career_portal_data import PortalDataError
from career_evidence_graph.codex_cli import CodexCLIError
from career_evidence_graph.validation.hashing import record_digest as digest

pytestmark = pytest.mark.usefixtures("planner_path")


def test_missing_progress_and_reconcile_do_not_create_the_selected_root(tmp_path):
    root = tmp_path / "not-created"
    analysis = Analysis(root)
    expected = {
        "attempt_id": "a" * 32,
        "status": "missing",
        "phase": None,
        "result_ref": None,
        "error_code": None,
    }
    assert analysis.progress("a" * 32) == expected
    assert analysis.reconcile("a" * 32) == expected
    assert not root.exists()


def test_prepare_returns_progress_then_verified_delivery_and_repeated_reads_are_pure(
    match_inputs, tmp_path
):
    application, snapshot = match_inputs
    calls = []
    root = tmp_path / "analyses"
    analysis = Analysis(root, runner=model_runner(model_output(snapshot), calls))
    progress = analysis.prepare(application, snapshot, request_id="b" * 32)
    assert progress["status"] == "complete"
    assert progress["result_ref"]["id"] == "b" * 32
    result = analysis.read(progress["result_ref"])
    assert result["id"] == "b" * 32
    assert result["score"]["lower"] == 100
    before = {str(p.relative_to(root)): p.read_bytes() for p in root.rglob("*") if p.is_file()}
    call_count = len(calls)
    assert analysis.prepare(application, snapshot, request_id="b" * 32) == progress
    for _ in range(3):
        assert analysis.progress("b" * 32) == progress
        assert analysis.reconcile("b" * 32) == progress
        assert analysis.read(progress["result_ref"]) == result
    changed = deepcopy(application)
    changed["job_description"] = "A different role"
    with pytest.raises(PortalDataError, match="请求"):
        analysis.prepare(changed, snapshot, request_id="b" * 32)
    assert len(calls) == call_count
    assert before == {
        str(p.relative_to(root)): p.read_bytes() for p in root.rglob("*") if p.is_file()
    }


def test_a_new_request_resumes_past_an_unanswered_call_only_when_admitted(match_inputs, tmp_path):
    # The ended attempt's unanswered call is sent again (Model Call Record); here the
    # admission check refuses, so the new request stops before sending anything.
    application, snapshot = match_inputs
    calls = []

    def interrupted(*args, **kwargs):
        calls.append("dispatched")
        raise KeyboardInterrupt("synthetic interrupted model call")

    analysis = Analysis(tmp_path / "analyses", runner=interrupted)
    with pytest.raises(KeyboardInterrupt):
        analysis.prepare(application, snapshot, request_id="c" * 32)
    assert analysis.progress("c" * 32)["status"] == "needs_recheck"
    assert (
        analysis.prepare(application, snapshot, request_id="c" * 32, admit_call=lambda: False)[
            "status"
        ]
        == "needs_recheck"
    )
    with pytest.raises(PortalDataError) as error:
        analysis.prepare(application, snapshot, request_id="d" * 32, admit_call=lambda: False)
    assert error.value.code == "flow_preparation_stopped"
    assert calls == ["dispatched"]


def test_explicit_recovery_keeps_completed_brief_and_retrieval(canonical, tmp_path):
    library, _, _, base, *_ = canonical
    snapshot = thin(canonical)
    initial = RecordedPipeline([requirement("Interdisciplinary research")])

    def fail_evaluation(config, prompt, **kwargs):
        if config.output_schema.name == "match-schema.json":
            raise terminal_model_failure("synthetic failed evaluation")
        return initial(config, prompt, **kwargs)

    root = tmp_path / "analyses"
    analysis = Analysis(
        root,
        runner=fail_evaluation,
        source_loader=lambda ids: library.snapshot_for_analysis(base, ids),
        information_provider=lambda: {"status": "unconfigured"},
    )
    with pytest.raises(PortalDataError):
        analysis.prepare(APPLICATION, snapshot, request_id="e" * 32)
    assert analysis.progress("e" * 32)["phase"] == "evaluation"
    previous = {
        str(p.relative_to(root)): p.read_bytes()
        for p in (root / ("e" * 32)).rglob("*")
        if p.is_file()
    }
    retry = RecordedPipeline(initial.requirements)
    analysis = Analysis(
        root,
        runner=retry,
        source_loader=lambda ids: library.snapshot_for_analysis(base, ids),
        information_provider=lambda: {"status": "unconfigured"},
    )
    result = analysis.prepare(APPLICATION, snapshot, request_id="f" * 32, resume_from="e" * 32)
    assert result["status"] == "complete"
    assert retry.brief_calls == []
    assert retry.read_calls == []
    assert retry.phases == ["evaluate"]
    assert previous == {
        str(p.relative_to(root)): p.read_bytes()
        for p in (root / ("e" * 32)).rglob("*")
        if p.is_file()
    }


def test_same_jd_can_reuse_its_saved_brief_for_a_different_application(canonical, tmp_path):
    library, _, _, base, *_ = canonical
    snapshot = thin(canonical)
    first = RecordedPipeline([requirement("Interdisciplinary research")])
    root = tmp_path / "analyses"
    analysis = Analysis(
        root, runner=first, source_loader=lambda ids: library.snapshot_for_analysis(base, ids)
    )
    original = analysis.prepare(APPLICATION, snapshot, request_id="1" * 32)
    second = RecordedPipeline(first.requirements)
    analysis = Analysis(
        root, runner=second, source_loader=lambda ids: library.snapshot_for_analysis(base, ids)
    )
    application = APPLICATION | {"id": "a-different-synthetic-application"}
    later = analysis.prepare(application, snapshot, request_id="2" * 32)
    assert second.brief_calls == []
    assert (
        analysis.read(later["result_ref"])["job_brief"]["revision"]
        == analysis.read(original["result_ref"])["job_brief"]["revision"]
    )


def test_redone_job_interprets_its_jd_anew_instead_of_reusing_the_saved_brief(canonical, tmp_path):
    # 2026-11-04: an explicit redo after a prompt fix reused the old, incomplete brief.
    library, _, _, base, *_ = canonical
    snapshot = thin(canonical)
    first = RecordedPipeline([requirement("Interdisciplinary research")])
    root = tmp_path / "analyses"
    analysis = Analysis(
        root, runner=first, source_loader=lambda ids: library.snapshot_for_analysis(base, ids)
    )
    analysis.prepare(APPLICATION, snapshot, request_id="1" * 32)
    second = RecordedPipeline(first.requirements)
    analysis = Analysis(
        root, runner=second, source_loader=lambda ids: library.snapshot_for_analysis(base, ids)
    )
    analysis.prepare(APPLICATION, snapshot, request_id="2" * 32, fresh_job_brief=True)
    assert len(second.brief_calls) == 1


def test_explicit_injected_adapter_is_part_of_the_request_identity(match_inputs, tmp_path):
    application, snapshot = match_inputs
    calls = []

    def injected(application, snapshot, directory):
        calls.append("injected")
        return analyze_job(
            application, snapshot, directory, runner=model_runner(model_output(snapshot), [])
        )

    def forbidden(*args, **kwargs):
        raise AssertionError("The injected adapter must own its evaluation")

    root = tmp_path / "analyses"
    analysis = Analysis(root, runner=forbidden, analyzer=injected, adapter_revision="fixture-v1")
    progress = analysis.prepare(application, snapshot, request_id="3" * 32)
    assert analysis.read(progress["result_ref"])["application_id"] == application["id"]
    assert calls == ["injected"]
    changed = Analysis(root, runner=forbidden, analyzer=injected, adapter_revision="fixture-v2")
    with pytest.raises(PortalDataError):
        changed.prepare(application, snapshot, request_id="3" * 32)
    assert calls == ["injected"]


def test_reuse_owns_paths_and_keeps_model_free_source_rebinding(match_inputs, tmp_path):
    application, snapshot = match_inputs
    calls = []
    analysis = Analysis(tmp_path / "analyses", runner=model_runner(model_output(snapshot), calls))
    original = analysis.prepare(application, snapshot, request_id="4" * 32)
    current = deepcopy(snapshot)
    current["display_metadata"] = "Unrelated directory presentation"
    current["revision"] = digest({k: v for k, v in current.items() if k != "revision"})
    count = len(calls)
    reused = analysis.reuse(application, current, original["result_ref"], request_id="5" * 32)
    assert reused["status"] == "complete"
    report = analysis.read(reused["result_ref"])
    assert report["source_snapshot_revision"] == current["revision"]
    assert report["reused_from"]["model_called"] is False
    assert len(calls) == count

    assert (
        analysis.reuse(application, current, original["result_ref"], request_id="5" * 32) == reused
    )
    changed = application | {"job_description": "A different job description"}
    assert analysis.reuse(changed, current, original["result_ref"], request_id="6" * 32) is None
    assert analysis.progress("6" * 32)["status"] == "not_reusable"
    assert len(calls) == count


def test_reconcile_validates_saved_response_without_replaying_or_writing(
    canonical, tmp_path, monkeypatch
):
    from career_evidence_graph._vendor import job_apply_store as helper

    library, _, _, base, *_ = canonical
    runner = RecordedPipeline([requirement("Interdisciplinary research")])
    root = tmp_path / "analyses"
    analysis = Analysis(
        root, runner=runner, source_loader=lambda ids: library.snapshot_for_analysis(base, ids)
    )
    write = helper.atomic_write_json

    def interrupt_after_response(path, value):
        write(path, value)
        if path.name == "model-result.json":
            raise KeyboardInterrupt("synthetic interruption after durable response")

    with monkeypatch.context() as patch:
        patch.setattr(helper, "atomic_write_json", interrupt_after_response)
        with pytest.raises(KeyboardInterrupt):
            analysis.prepare(APPLICATION, thin(canonical), request_id="7" * 32)
    before = {str(p.relative_to(root)): p.read_bytes() for p in root.rglob("*") if p.is_file()}
    count = len(runner.calls)
    assert analysis.progress("7" * 32)["status"] == "needs_recheck"
    reconciled = analysis.reconcile("7" * 32)
    assert reconciled["status"] == "recoverable"
    assert reconciled["result_ref"] is None
    assert len(runner.calls) == count
    assert before == {
        str(p.relative_to(root)): p.read_bytes() for p in root.rglob("*") if p.is_file()
    }


@pytest.mark.parametrize("published", [False, True])
def test_request_save_failure_never_dispatches_or_replays_an_unknown_intent(
    match_inputs, tmp_path, monkeypatch, published
):
    from career_evidence_graph._vendor import job_apply_store as helper

    application, snapshot = match_inputs
    calls = []
    analysis = Analysis(tmp_path / "analyses", runner=model_runner(model_output(snapshot), calls))
    write = helper.atomic_write_json

    def fail_request(path, value):
        if "requests" in path.parts:
            if published:
                write(path, value)
            raise OSError("synthetic request publication failure")
        write(path, value)

    with monkeypatch.context() as patch:
        patch.setattr(helper, "atomic_write_json", fail_request)
        with pytest.raises(OSError):
            analysis.prepare(application, snapshot, request_id="8" * 32)
    assert calls == []
    result = analysis.prepare(application, snapshot, request_id="8" * 32)
    if published:
        # The published intent itself is never replayed; a new request may follow
        # because the ended attempt wrote nothing and therefore called no model.
        assert result["status"] == "needs_recheck"
        assert calls == []
        assert analysis.prepare(application, snapshot, request_id="9" * 32)["status"] == (
            "complete"
        )
        assert len(calls) == 2
    else:
        assert result["status"] == "complete"
        assert len(calls) == 2  # Existing boundary's version check and evaluation.


def test_resumed_attempt_that_never_saved_progress_called_no_model(
    match_inputs, tmp_path, monkeypatch
):
    # 2026-11-04: a resumed attempt stopped inside its job brief before any model call
    # (no progress saved) blocked every later analysis as an unknown result.
    from career_evidence_graph._vendor import job_apply_store as helper

    application, snapshot = match_inputs
    calls = []
    root = tmp_path / "analyses"
    analysis = Analysis(root, runner=model_runner(model_output(snapshot), calls))
    write = helper.atomic_write_json

    def published_only(path, value):
        write(path, value)
        if "requests" in path.parts:
            raise OSError("synthetic stop after publication")

    with monkeypatch.context() as patch:
        patch.setattr(helper, "atomic_write_json", published_only)
        with pytest.raises(OSError):
            analysis.prepare(application, snapshot, request_id="8" * 32)
    started = root / ("8" * 32) / "job-brief"
    started.mkdir(parents=True)
    (started / "job-brief-schema.json").write_text("{}")
    assert analysis.prepare(application, snapshot, request_id="9" * 32)["status"] == "complete"


@pytest.mark.parametrize("attempt_id", ["../escape", "", True, "a" * 31, "g" * 32, {}])
def test_invalid_attempt_references_never_initialize_storage(tmp_path, attempt_id):
    root = tmp_path / "absent"
    analysis = Analysis(root)
    with pytest.raises(PortalDataError):
        analysis.progress(attempt_id)
    assert not root.exists()


def test_mutated_report_cannot_satisfy_its_original_delivery_reference(match_inputs, tmp_path):
    from career_evidence_graph._vendor import job_apply_store as helper

    application, snapshot = match_inputs
    calls = []
    root = tmp_path / "analyses"
    analysis = Analysis(root, runner=model_runner(model_output(snapshot), calls))
    progress = analysis.prepare(application, snapshot, request_id="a" * 32)
    report = analysis.read(progress["result_ref"])
    report["score"]["lower"] = 0
    helper.atomic_write_json(root / ("a" * 32) / "analysis.json", report)
    with pytest.raises(PortalDataError):
        analysis.read(progress["result_ref"])
    assert len(calls) == 2


@pytest.mark.parametrize("mutation", ["phase", "origin", "binding"])
def test_checkpoint_references_are_validated_without_effects(canonical, tmp_path, mutation):
    from career_evidence_graph._vendor import job_apply_store as helper

    library, _, _, base, *_ = canonical
    recorded = RecordedPipeline([requirement("Interdisciplinary research")])

    def fail(config, prompt, **kwargs):
        if config.output_schema.name == "match-schema.json":
            raise CodexCLIError("synthetic evaluation failure")
        return recorded(config, prompt, **kwargs)

    root = tmp_path / "analyses"
    analysis = Analysis(
        root, runner=fail, source_loader=lambda ids: library.snapshot_for_analysis(base, ids)
    )
    with pytest.raises(PortalDataError):
        analysis.prepare(APPLICATION, thin(canonical), request_id="b" * 32)
    path = root / ("b" * 32) / "analysis-progress.json"
    checkpoint = helper.read_json_object(path, "checkpoint")
    if mutation == "phase":
        checkpoint["phase"] = []
    elif mutation == "origin":
        checkpoint["evaluation_origin"] = False
    else:
        checkpoint["binding"]["application_id"] = "wrong-application"
    checkpoint["revision"] = digest({k: v for k, v in checkpoint.items() if k != "revision"})
    helper.atomic_write_json(path, checkpoint)
    before = path.read_bytes()
    with pytest.raises(PortalDataError):
        analysis.progress("b" * 32)
    assert path.read_bytes() == before


def test_concurrent_duplicate_and_new_identity_cannot_repeat_an_active_call(match_inputs, tmp_path):
    application, snapshot = match_inputs
    entered, release = threading.Event(), threading.Event()
    calls, dispatched = [], []
    fixture = model_runner(model_output(snapshot), calls)

    def waiting(config, prompt, **kwargs):
        dispatched.append("model")
        entered.set()
        assert release.wait(3)
        return fixture(config, prompt, **kwargs)

    analysis = Analysis(tmp_path / "analyses", runner=waiting)
    with ThreadPoolExecutor(max_workers=1) as executor:
        pending = executor.submit(analysis.prepare, application, snapshot, request_id="c" * 32)
        try:
            assert entered.wait(3)
            assert (
                analysis.prepare(application, snapshot, request_id="c" * 32)["status"]
                == "needs_recheck"
            )
            with pytest.raises(PortalDataError):
                analysis.prepare(application, snapshot, request_id="d" * 32)
            assert dispatched == ["model"]
        finally:
            release.set()
        assert pending.result(timeout=3)["status"] == "complete"


def test_active_scope_cannot_be_explicitly_recovered_while_an_independent_scope_runs(
    canonical, tmp_path
):
    library, _, _, base, *_ = canonical
    snapshot = thin(canonical)
    entered, release = threading.Event(), threading.Event()
    recorded = RecordedPipeline([requirement("Interdisciplinary research")])

    def sources(ids):
        if (
            threading.current_thread().name.startswith("ThreadPoolExecutor")
            and not entered.is_set()
        ):
            entered.set()
            assert release.wait(5)
        return library.snapshot_for_analysis(base, ids)

    module = Analysis(tmp_path / "analyses", runner=recorded, source_loader=sources)
    with ThreadPoolExecutor(max_workers=1) as pool:
        original = pool.submit(module.prepare, APPLICATION, snapshot, request_id="1" * 32)
        try:
            assert entered.wait(3)
            before = {
                str(path): path.read_bytes() for path in module.root.rglob("*") if path.is_file()
            }
            assert module.progress("1" * 32)["status"] == "needs_recheck"
            with pytest.raises(PortalDataError) as busy:
                module.prepare(APPLICATION, snapshot, request_id="2" * 32, resume_from="1" * 32)
            assert busy.value.code == "match_result_needs_recheck"
            assert before == {
                str(path): path.read_bytes() for path in module.root.rglob("*") if path.is_file()
            }
            independent = module.prepare(
                APPLICATION | {"id": "independent-job"}, snapshot, request_id="3" * 32
            )
            assert independent["status"] == "complete"
        finally:
            release.set()
        assert original.result(timeout=3)["status"] == "complete"
    assert recorded.phases.count("evaluate") == 2
    assert not (module.root / ("2" * 32)).exists()


def test_process_exit_releases_scope_ownership_and_preserves_checkpoint_recovery(
    canonical, tmp_path
):
    import multiprocessing

    library, _, _, base, *_ = canonical
    snapshot = thin(canonical)
    process_context = multiprocessing.get_context("fork")
    entered, release = process_context.Event(), process_context.Event()
    root = tmp_path / "analyses"

    def source(ids):
        entered.set()
        assert release.wait(10)
        return library.snapshot_for_analysis(base, ids)

    def prepare_in_child():
        Analysis(
            root,
            runner=RecordedPipeline([requirement("Interdisciplinary research")]),
            source_loader=source,
        ).prepare(APPLICATION, snapshot, request_id="1" * 32)

    process = process_context.Process(target=prepare_in_child)
    process.start()
    try:
        assert entered.wait(3)
        assert Analysis(root).progress("1" * 32)["status"] == "needs_recheck"
    finally:
        process.terminate()
        process.join(timeout=3)
    assert not process.is_alive()
    before = {
        str(path): path.read_bytes() for path in (root / ("1" * 32)).rglob("*") if path.is_file()
    }
    retry = RecordedPipeline([requirement("Interdisciplinary research")])
    recovered = Analysis(
        root, runner=retry, source_loader=lambda ids: library.snapshot_for_analysis(base, ids)
    ).prepare(APPLICATION, snapshot, request_id="2" * 32, resume_from="1" * 32)
    assert recovered["status"] == "complete"
    assert retry.brief_calls == []
    assert retry.phases == ["evaluate"]
    assert before == {
        str(path): path.read_bytes() for path in (root / ("1" * 32)).rglob("*") if path.is_file()
    }


def test_information_changed_during_analysis_is_not_delivered_as_current(canonical, tmp_path):
    library, _, _, base, *_ = canonical
    current = [library_with(answer("Are you fluent in English?", "yes"))]
    recorded = RecordedPipeline(
        [requirement("Professional communication in English", hard=True)], select=False
    )

    def changed(config, prompt, **kwargs):
        result = recorded(config, prompt, **kwargs)
        if config.output_schema.name == "match-schema.json":
            current[0] = library_with(answer("Are you fluent in English?", "no"))
        return result

    analysis = Analysis(
        tmp_path / "analyses",
        runner=changed,
        source_loader=lambda ids: library.snapshot_for_analysis(base, ids),
        information_provider=lambda: current[0],
    )
    with pytest.raises(PortalDataError) as error:
        analysis.prepare(APPLICATION, thin(canonical), request_id="e" * 32)
    assert error.value.code == "match_information_changed"


def test_a_newer_unknown_attempt_is_resumed_and_its_evaluation_sent_again(canonical, tmp_path):
    library, _, _, base, *_ = canonical
    root = tmp_path / "analyses"
    snapshot = thin(canonical)
    recorded = RecordedPipeline([requirement("Interdisciplinary research")])

    def failed(config, prompt, **kwargs):
        if config.output_schema.name == "match-schema.json":
            raise terminal_model_failure("synthetic known evaluation failure")
        return recorded(config, prompt, **kwargs)

    options = {"source_loader": lambda ids: library.snapshot_for_analysis(base, ids)}
    with pytest.raises(PortalDataError):
        Analysis(root, runner=failed, **options).prepare(APPLICATION, snapshot, request_id="1" * 32)

    def interrupted(*args, **kwargs):
        raise KeyboardInterrupt("synthetic unknown newer evaluation")

    with pytest.raises(KeyboardInterrupt):
        Analysis(root, runner=interrupted, **options).prepare(
            APPLICATION, snapshot, request_id="2" * 32, resume_from="1" * 32
        )
    retry = sent_schemas(RecordedPipeline(recorded.requirements))
    progress = Analysis(root, runner=retry, **options).prepare(
        APPLICATION, snapshot, request_id="3" * 32, recovery_candidates=["1" * 32, "2" * 32]
    )
    assert progress["status"] == "complete"
    assert retry.names == ["match-schema.json"]


def test_sources_delivery_distinguishes_bound_directory_and_selected_facts(canonical, tmp_path):
    from career_evidence_graph._vendor import job_apply_store as helper

    library, _, _, base, *_ = canonical
    runner = RecordedPipeline([requirement("Interdisciplinary research")])
    root = tmp_path / "analyses"
    analysis = Analysis(
        root, runner=runner, source_loader=lambda ids: library.snapshot_for_analysis(base, ids)
    )
    progress = analysis.prepare(APPLICATION, thin(canonical), request_id="a" * 32)
    report = analysis.read(progress["result_ref"])
    before = {str(p.relative_to(root)): p.read_bytes() for p in root.rglob("*") if p.is_file()}
    delivery = analysis.read_sources(progress["result_ref"])
    assert delivery["binding"]["revision"] == report["input_source_snapshot_revision"]
    assert delivery["selected"]["revision"] == report["source_snapshot_revision"]
    assert delivery["binding"]["items"] == []
    assert delivery["selected"]["items"]
    delivery["selected"]["items"].clear()
    assert analysis.read_sources(report)["selected"]["items"]
    assert before == {
        str(p.relative_to(root)): p.read_bytes() for p in root.rglob("*") if p.is_file()
    }
    selected_path = root / ("a" * 32) / "source-snapshot.json"
    selected = helper.read_json_object(selected_path, "selected")
    selected["items"].clear()
    helper.atomic_write_json(selected_path, selected)
    with pytest.raises(PortalDataError):
        analysis.read_sources(progress["result_ref"])


def test_reuse_receipt_cannot_resolve_an_unknown_prepare(match_inputs, tmp_path):
    from career_evidence_graph._vendor import job_apply_store as helper

    application, snapshot = match_inputs

    def interrupted(*args, **kwargs):
        raise KeyboardInterrupt("synthetic unknown prepare")

    root = tmp_path / "analyses"
    analysis = Analysis(root, runner=interrupted)
    with pytest.raises(KeyboardInterrupt):
        analysis.prepare(application, snapshot, request_id="f" * 32)
    request_path = next((root / "requests").glob("*/" + "f" * 32 + ".json"))
    request = helper.read_json_object(request_path, "request")
    wrong_kind = {
        "schema_version": "analysis-reuse-result/v1",
        "attempt_id": "f" * 32,
        "request_revision": request["revision"],
        "status": "not_reusable",
        "model_called": False,
    }
    wrong_kind["revision"] = digest(wrong_kind)
    helper.atomic_write_json(root / ("f" * 32) / "reuse-result.json", wrong_kind)
    with pytest.raises(PortalDataError):
        analysis.progress("f" * 32)


def test_default_portal_analysis_uses_the_owned_module_interface(
    canonical, portal, tmp_path, monkeypatch
):
    from career_evidence_graph.career_portal import create_server
    from career_evidence_graph.career_portal_data import ApplicationStore

    _, _, _, _, _, manifest, _ = canonical
    job = ApplicationStore(portal.applications).create_application(
        {
            "company": APPLICATION["company"],
            "role_title": APPLICATION["role_title"],
            "job_description": APPLICATION["job_description"],
        }
    )
    calls = []
    prepare = Analysis.prepare

    def observed(module, *args, **kwargs):
        calls.append(kwargs["request_id"])
        return prepare(module, *args, **kwargs)

    monkeypatch.setattr(Analysis, "prepare", observed)
    with create_server(
        portal.applications,
        portal.career,
        flow_root=tmp_path / "flow-owned-analysis",
        career_library_manifest=manifest,
        flow_match_runner=RecordedPipeline([requirement("Interdisciplinary research")]),
        write_admission_policy="development",
    ) as server:
        flow = server.application_flow_service
        task = flow.create(job["id"], job["revision"])
        result = flow.callbacks["analysis"](task)
        assert calls == [result["id"]]
        assert result["application_id"] == task["application_id"]


def test_known_failed_call_does_not_block_a_fresh_request_after_input_change(canonical, tmp_path):
    library, _, _, base, *_ = canonical
    snapshot = thin(canonical)
    recorded = RecordedPipeline([requirement("Interdisciplinary research")])

    def failed(config, prompt, **kwargs):
        if config.output_schema.name == "match-schema.json":
            raise terminal_model_failure("synthetic known terminal failure")
        return recorded(config, prompt, **kwargs)

    root = tmp_path / "analyses"
    options = {"source_loader": lambda ids: library.snapshot_for_analysis(base, ids)}
    with pytest.raises(PortalDataError):
        Analysis(root, runner=failed, **options).prepare(APPLICATION, snapshot, request_id="1" * 32)
    changed = snapshot | {"display_metadata": "a new confirmed directory version"}
    changed["revision"] = digest({k: v for k, v in changed.items() if k != "revision"})
    retry = RecordedPipeline(recorded.requirements)
    progress = Analysis(root, runner=retry, **options).prepare(
        APPLICATION, changed, request_id="2" * 32
    )
    assert progress["status"] == "complete"
    assert retry.brief_calls == []


def test_invalid_snapshot_is_rejected_before_reserving_an_execution(match_inputs, tmp_path):
    application, snapshot = match_inputs
    root = tmp_path / "not-reserved"
    analysis = Analysis(root)
    invalid = snapshot | {"revision": "not-a-verified-snapshot"}
    with pytest.raises(PortalDataError) as error:
        analysis.prepare(application, invalid, request_id="1" * 32)
    assert error.value.code == "match_snapshot_invalid"
    assert not root.exists()


PARTIAL = '{"type":"turn.started"}\n{"type":"item.completed","item":{"type":"agent_message"}}\n'


@pytest.mark.parametrize(
    "message,raw",
    [
        ("Codex CLI timed out", PARTIAL),
        ("Codex exec failed with exit code 1: ", PARTIAL),
        ("Codex returned malformed events", "incomplete JSONL"),
    ],
)
def test_unknown_failed_evaluation_is_sent_again_only_by_an_explicit_retry(
    canonical, tmp_path, message, raw
):
    library, _, _, base, *_ = canonical
    snapshot = thin(canonical)
    recorded = RecordedPipeline([requirement("Interdisciplinary research")])
    calls = []

    def failed(config, prompt, **kwargs):
        if config.output_schema.name == "match-schema.json":
            calls.append("evaluation dispatched")
            raise CodexCLIError(message, raw_stdout_jsonl=raw)
        return recorded(config, prompt, **kwargs)

    root = tmp_path / "analyses"
    options = {"source_loader": lambda ids: library.snapshot_for_analysis(base, ids)}
    module = Analysis(root, runner=failed, **options)
    with pytest.raises(PortalDataError):
        module.prepare(APPLICATION, snapshot, request_id="1" * 32)
    before = {
        str(path): path.read_bytes() for path in (root / ("1" * 32)).rglob("*") if path.is_file()
    }
    assert module.progress("1" * 32)["status"] == "needs_recheck"
    assert module.reconcile("1" * 32)["status"] == "needs_recheck"
    # The attempt has ended on a call without an answer, so a retry may send it again
    # (Model Call Record, decided 2026-11-09); the attempt itself never reruns.
    assert module.ended_without_answer("1" * 32) is True
    retry = sent_schemas(RecordedPipeline(recorded.requirements))
    reopened = Analysis(root, runner=retry, **options)
    assert reopened.prepare(APPLICATION, snapshot, request_id="1" * 32)["status"] == "needs_recheck"
    assert retry.names == []
    resumed = reopened.prepare(APPLICATION, snapshot, request_id="3" * 32, resume_from="1" * 32)
    assert resumed["status"] == "complete"
    assert retry.names == ["match-schema.json"]
    assert calls == ["evaluation dispatched"]
    assert before == {
        str(path): path.read_bytes() for path in (root / ("1" * 32)).rglob("*") if path.is_file()
    }


@pytest.mark.parametrize(
    "message,raw",
    [
        ("Codex CLI timed out", '{"type":"turn.started","turn_id":"synthetic-unknown"}\n'),
        ("Codex CLI timed out", ""),
        ("Codex exec failed with exit code 1: ", ""),
    ],
)
def test_evaluation_that_ended_without_output_is_retried_only_by_a_new_request(
    canonical, tmp_path, message, raw
):
    library, _, _, base, *_ = canonical
    snapshot = thin(canonical)
    recorded = RecordedPipeline([requirement("Interdisciplinary research")])

    def failed(config, prompt, **kwargs):
        if config.output_schema.name == "match-schema.json":
            raise CodexCLIError(message, raw_stdout_jsonl=raw)
        return recorded(config, prompt, **kwargs)

    root = tmp_path / "analyses"
    options = {"source_loader": lambda ids: library.snapshot_for_analysis(base, ids)}
    with pytest.raises(PortalDataError):
        Analysis(root, runner=failed, **options).prepare(APPLICATION, snapshot, request_id="1" * 32)
    # Installed MC-11 (approved 2026-10-31): a read-only call that ended with no output
    # has nothing to adopt, so the user's Continue may run it again; it never replays itself.
    retry = RecordedPipeline(recorded.requirements)
    module = Analysis(root, runner=retry, **options)
    assert module.progress("1" * 32)["status"] == "failed"
    assert module.prepare(APPLICATION, snapshot, request_id="1" * 32)["status"] == "failed"
    assert retry.calls == []
    assert module.prepare(APPLICATION, snapshot, request_id="2" * 32)["status"] == "complete"


@pytest.mark.parametrize("phase", ["brief", "planning", "reading"])
@pytest.mark.parametrize("outcome", ["partial_output", "no_output", "terminal"])
def test_upstream_failure_requires_a_terminal_turn_or_stays_unknown(
    canonical, tmp_path, monkeypatch, phase, outcome
):
    import json

    from test_structured_career_store import facts

    from career_evidence_graph.career_experiences import ExperienceStore

    library, career_root, _, base, *_ = canonical
    if phase == "reading":
        content = facts(candidate_id="unseen-identity")
        content["facts"][0]["text"] = "Studied cross-domain models with biology collaborators."
        content["facts"].append(
            deepcopy(content["facts"][0])
            | {"id": "fact-2", "text": "Unrelated recorded detail. " * 2800}
        )
        ExperienceStore(career_root).save(
            "unseen-identity", title=content["title"], content=content
        )
    snapshot = thin(canonical)
    recorded = RecordedPipeline([requirement("Interdisciplinary research")])
    failures = []

    def runner(config, prompt, **kwargs):
        schema = json.loads(config.output_schema.read_text())
        current = (
            "brief"
            if config.output_schema.name == "job-brief-schema.json"
            else "planning"
            if schema.get("title") == "_PageResult"
            else "reading"
            if set(schema.get("properties", {})) == {"selections"}
            else "evaluation"
        )
        if current == phase:
            failures.append(current)
            if outcome == "terminal":
                raise terminal_model_failure("Synthetic fully terminated stage")
            # A call that ended without output has nothing to adopt (approved 2026-10-31).
            raise CodexCLIError(
                "Codex CLI timed out",
                raw_stdout_jsonl=PARTIAL
                if outcome == "partial_output"
                else '{"type":"turn.started"}\n',
            )
        return recorded(config, prompt, **kwargs)

    options = {"source_loader": lambda ids: library.snapshot_for_analysis(base, ids)}
    root = tmp_path / "analyses"
    with pytest.raises(PortalDataError):
        Analysis(root, runner=runner, **options).prepare(APPLICATION, snapshot, request_id="1" * 32)
    assert failures == [phase]
    retry = RecordedPipeline(recorded.requirements)

    def retry_stage(config, prompt, **kwargs):
        schema = json.loads(config.output_schema.read_text())
        if phase == "reading" and set(schema.get("properties", {})) == {"selections"}:
            data = json.loads(prompt.split("CONTEXT_JSON\n", 1)[1])
            selections = []
            for supplied in data.get("source_ranges", [data]):
                if "Studied cross-domain" in supplied.get("text", ""):
                    selections.append(
                        {"source_id": supplied["source"]["source_id"], "requirement_indexes": [0]}
                    )
                for span in supplied.get("spans", []):
                    if "Studied cross-domain" in span.get("text", ""):
                        selections.append({"span_id": span["span_id"], "requirement_indexes": [0]})
            return model_runner({"selections": selections}, retry.calls)(config, prompt, **kwargs)
        return retry(config, prompt, **kwargs)

    module = Analysis(root, runner=retry_stage, **options)
    if outcome != "partial_output":
        assert (
            module.prepare(APPLICATION, snapshot, request_id="2" * 32, resume_from="1" * 32)[
                "status"
            ]
            == "complete"
        )
    else:
        # An unknown brief, planner or reading call is sent again by an explicit retry.
        assert module.ended_without_answer("1" * 32) is True
        assert (
            module.prepare(APPLICATION, snapshot, request_id="3" * 32, resume_from="1" * 32)[
                "status"
            ]
            == "complete"
        )


def test_flow_cancel_after_first_model_call_blocks_all_later_model_dispatches(
    canonical, portal, tmp_path
):
    from career_evidence_graph.career_portal import create_server
    from career_evidence_graph.career_portal_data import ApplicationStore

    _, _, _, _, _, manifest, _ = canonical
    job = ApplicationStore(portal.applications).create_application(
        {
            "company": APPLICATION["company"],
            "role_title": APPLICATION["role_title"],
            "job_description": APPLICATION["job_description"],
        }
    )
    recorded = RecordedPipeline([requirement("Interdisciplinary research")])
    calls, attempts = [], []
    finished = threading.Event()

    def runner(config, prompt, **kwargs):
        calls.append(config.output_schema.name)
        result = recorded(config, prompt, **kwargs)
        if len(calls) == 1:
            current = flow.task_snapshot(task["id"])
            flow.cancel_preparation(task["id"], current["revision"])
        return result

    with create_server(
        portal.applications,
        portal.career,
        flow_root=tmp_path / "flow-cancel-analysis",
        career_library_manifest=manifest,
        flow_match_runner=runner,
        write_admission_policy="development",
    ) as server:
        flow = server.application_flow_service
        task = flow.create(job["id"], job["revision"])
        prepare = flow.callbacks["analysis"]

        def observe(request):
            attempts.append(request["stages"]["analysis"]["attempt_id"])
            try:
                return prepare(request)
            finally:
                finished.set()

        flow.callbacks["analysis"] = observe
        flow.start(task["id"], task["revision"], "analysis")
        assert finished.wait(3)
        assert calls == ["job-brief-schema.json"]
        assert flow.task_snapshot(task["id"])["status"] == "cancelled"
        assert flow.analysis.progress(attempts[0])["status"] == "stopped"
        before = {
            str(path): path.read_bytes() for path in flow.analysis.root.rglob("*") if path.is_file()
        }
        for _ in range(3):
            assert flow.analysis.reconcile(attempts[0])["status"] == "stopped"
        assert before == {
            str(path): path.read_bytes() for path in flow.analysis.root.rglob("*") if path.is_file()
        }


def test_flow_pause_between_calls_can_continue_without_repeating_completed_brief(
    canonical, portal, tmp_path
):
    from test_application_flow import wait_for

    from career_evidence_graph.career_portal import create_server
    from career_evidence_graph.career_portal_data import ApplicationStore

    _, _, _, _, _, manifest, _ = canonical
    job = ApplicationStore(portal.applications).create_application(
        {
            "company": APPLICATION["company"],
            "role_title": APPLICATION["role_title"],
            "job_description": APPLICATION["job_description"],
        }
    )
    recorded = RecordedPipeline([requirement("Interdisciplinary research")])
    calls, paused = [], threading.Event()

    def runner(config, prompt, **kwargs):
        calls.append(config.output_schema.name)
        result = recorded(config, prompt, **kwargs)
        if len(calls) == 1:
            paused.set()
        return result

    with create_server(
        portal.applications,
        portal.career,
        flow_root=tmp_path / "flow-pause-analysis",
        career_library_manifest=manifest,
        flow_match_runner=runner,
        write_admission_policy="development",
    ) as server:
        flow = server.application_flow_service
        flow.callbacks["preparation_allowed"] = lambda task_id, **kwargs: not paused.is_set()
        task = flow.create(job["id"], job["revision"])
        flow.start(task["id"], task["revision"], "analysis")
        pending = wait_for(
            flow,
            task["id"],
            lambda row: row["stages"]["analysis"]["status"] not in {"queued", "running"},
        )
        assert pending["stages"]["analysis"]["status"] == "pending"
        assert calls == ["job-brief-schema.json"]
        original = pending["analysis_attempts"][-1]["stage"]["attempt_id"]
        assert flow.analysis.progress(original)["status"] == "stopped"
        paused.clear()
        flow.start(task["id"], pending["revision"], "analysis")
        complete = wait_for(flow, task["id"], lambda row: row["status"] == "analysis_ready")
        assert complete["analysis_id"] != original
        assert calls.count("job-brief-schema.json") == 1
        assert complete["analysis_attempts"][-1]["stage"]["attempt_id"] == original


@pytest.mark.parametrize("lose_prior_receipt", [False, True])
def test_refresh_pause_proves_only_the_refused_call_and_resumes_completed_retrieval(
    canonical, portal, tmp_path, lose_prior_receipt
):
    from test_application_flow import wait_for

    from career_evidence_graph.career_portal import create_server
    from career_evidence_graph.career_portal_data import ApplicationStore

    _, _, _, _, _, manifest, _ = canonical
    job = ApplicationStore(portal.applications).create_application(
        {
            "company": APPLICATION["company"],
            "role_title": APPLICATION["role_title"],
            "job_description": APPLICATION["job_description"],
        }
    )
    recorded = RecordedPipeline([requirement("Interdisciplinary research")])
    calls, paused = [], threading.Event()
    refresh_calls = []

    def runner(config, prompt, **kwargs):
        calls.append(config.output_schema.name)
        result = recorded(config, prompt, **kwargs)
        if "match-refreshes" in config.output_schema.parts:
            refresh_calls.append(config.output_schema.name)
            if len(refresh_calls) == 1:
                paused.set()
        return result

    with create_server(
        portal.applications,
        portal.career,
        flow_root=tmp_path / "flow-refresh-pause",
        career_library_manifest=manifest,
        flow_match_runner=runner,
        write_admission_policy="development",
    ) as server:
        flow = server.application_flow_service

        def allowed(task_id, **kwargs):
            if paused.is_set() and lose_prior_receipt:
                for path in (flow.root / "match-refreshes").glob(
                    "*/analysis/retrieval/*/page-*/result.json"
                ):
                    path.unlink()
            return not paused.is_set()

        flow.callbacks["preparation_allowed"] = allowed
        task = flow.create(job["id"], job["revision"])
        flow.start(task["id"], task["revision"], "analysis")
        ready = wait_for(flow, task["id"], lambda row: row["status"] == "analysis_ready")
        with pytest.raises(PortalDataError) as stopped:
            flow.refresh_match(task["id"], ready["revision"], "a" * 32)
        assert stopped.value.code == "flow_preparation_stopped"
        assert len(refresh_calls) == 1
        paused.clear()
        if lose_prior_receipt:
            with pytest.raises(PortalDataError):
                flow.refresh_match(
                    task["id"], ready["revision"], "b" * 32, resume_request_id="a" * 32
                )
            assert len(refresh_calls) == 1
            assert not (flow.root / "match-refreshes" / ("a" * 32) / "failure.json").exists()
            return
        refreshed = flow.refresh_match(
            task["id"], ready["revision"], "b" * 32, resume_request_id="a" * 32
        )
        assert len(refreshed["match_rechecks"]) == 1
        assert refreshed["match_rechecks"][0]["id"] == "b" * 32
        assert len(refresh_calls) == 2


@pytest.mark.parametrize("pause_again", [False, True])
def test_real_paused_pipeline_manual_refresh_has_only_a_bound_revocable_permission(
    canonical, portal, tmp_path, pause_again
):
    from uuid import uuid4

    from test_application_flow import wait_for

    from career_evidence_graph._vendor import job_apply_store as helper
    from career_evidence_graph.career_portal import create_server
    from career_evidence_graph.career_portal_data import ApplicationStore

    _, _, _, _, _, manifest, _ = canonical
    job = ApplicationStore(portal.applications).create_application(
        {
            "company": APPLICATION["company"],
            "role_title": APPLICATION["role_title"],
            "job_description": APPLICATION["job_description"],
        }
    )
    recorded = RecordedPipeline([requirement("Interdisciplinary research")])
    refresh_calls = []

    def runner(config, prompt, **kwargs):
        result = recorded(config, prompt, **kwargs)
        if "match-refreshes" in config.output_schema.parts:
            refresh_calls.append(config.output_schema.name)
            if pause_again and len(refresh_calls) == 1:
                pipeline.pause()
        return result

    with create_server(
        portal.applications,
        portal.career,
        flow_root=tmp_path / "flow-manual-refresh",
        worker_root=tmp_path / "worker-manual-refresh",
        career_library_manifest=manifest,
        flow_match_runner=runner,
        write_admission_policy="development",
    ) as server:
        flow, pipeline = server.application_flow_service, server.application_pipeline_service
        pipeline._poll_mail = lambda state: None
        task = flow.create(job["id"], job["revision"])
        flow.start(task["id"], task["revision"], "analysis")
        ready = wait_for(flow, task["id"], lambda row: row["status"] == "analysis_ready")
        with flow.applications.write_lock():
            state = pipeline._load()
            state.update(
                id=uuid4().hex,
                queue_mode=True,
                status="needs_input",
                control="paused",
                active_task_id=task["id"],
                current_recommendation_id="application:" + job["id"],
                items=[
                    {
                        "recommendation_id": "application:" + job["id"],
                        "application_id": job["id"],
                        "task_id": task["id"],
                        "status": "needs_input",
                    }
                ],
            )
            pipeline._save(state)
        assert pipeline.preparation_allowed(task["id"]) is False
        payload = {
            "task_id": task["id"],
            "task_revision": ready["revision"],
            "request_id": "a" * 32,
        }
        if pause_again:
            with (
                pytest.raises(PortalDataError) as stopped,
                pipeline.manual_entry("flow:refresh-match", payload),
            ):
                flow.refresh_match(**payload)
            assert stopped.value.code == "flow_preparation_stopped"
            assert len(refresh_calls) == 1
            payload.update(request_id="b" * 32, resume_request_id="a" * 32)
        with pipeline.manual_entry("flow:refresh-match", payload):
            complete = flow.refresh_match(**payload)
        assert complete["match_rechecks"][-1]["id"] == payload["request_id"]
        assert len(refresh_calls) == 2
        intent = helper.read_json_object(
            flow.root / "match-refreshes" / payload["request_id"] / "intent.json", "intent"
        )
        assert (
            pipeline.preparation_allowed(
                task["id"], refresh=(payload["request_id"], digest(intent))
            )
            is False
        )
        # Adoption changed only the task version; even a trusted provider cannot
        # keep an older refresh TaskRef alive after that version changed.
        flow.callbacks["preparation_allowed"] = lambda *args, **kwargs: True
        assert (
            flow.analysis_call_allowed(ready, refresh=(payload["request_id"], digest(intent)))
            is False
        )


@pytest.mark.parametrize(
    ("saved", "status"),
    [
        # 2026-11-08, UBS: a context-size refusal raised before the prompt was saved.
        ((), "failed"),
        # Once the prompt is saved, a call may have gone out: its result stays unknown.
        (("context-input.json",), "needs_recheck"),
        (("match-schema.json",), "needs_recheck"),
    ],
)
def test_an_evaluation_refused_before_its_prompt_is_a_known_failure(tmp_path, saved, status):
    root = tmp_path / "analyses"
    origin = root / ("a" * 32) / "evaluation-1"
    origin.mkdir(parents=True)
    for name in saved:
        (origin / name).write_text("{}")
    checked = Analysis(root)._saved_evaluation_progress(
        {"status": "needs_recheck"},
        {"evaluation_origin": str(origin), "evaluation_error": "retrieval_execution_incomplete"},
    )
    assert checked["status"] == status
    if status == "failed":
        assert checked["error_code"] == "retrieval_execution_incomplete"


def test_an_empty_refused_attempt_resumes_what_it_was_resuming(tmp_path, monkeypatch):
    """2026-11-08, Keyrock: a retry refused before writing anything left an empty
    attempt; the next retry resumed it and was refused again, forever."""
    root = tmp_path / "analyses"
    analysis = Analysis(root)
    first, empty, newer = "a" * 32, "b" * 32, "c" * 32
    (root / first).mkdir(parents=True)
    (root / first / "analysis-progress.json").write_text("{}")
    (root / empty).mkdir()
    requests = {empty: {"binding": {"resume_from": first}}, newer: {"binding": {}}}
    monkeypatch.setattr(analysis, "_request", lambda attempt_id: requests.get(attempt_id))
    monkeypatch.setattr(analysis, "_checkpoint", lambda attempt_id: None)
    assert analysis._recovery_directory(empty, []) == root / first
    # One refused before even its request was saved falls back to the candidates.
    missing = "d" * 32
    assert analysis._recovery_directory(missing, [missing, empty, first]) == root / first
    # An empty attempt that resumed nothing starts afresh.
    (root / newer).mkdir()
    assert analysis._recovery_directory(newer, []) is None
    # An attempt that wrote something without a checkpoint stays unverifiable.
    (root / empty / "partial.json").write_text("{}")
    with pytest.raises(PortalDataError):
        analysis._recovery_directory(empty, [])
