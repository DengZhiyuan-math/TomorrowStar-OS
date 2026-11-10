"""Flow owns preparation progression independently of queue and execution state."""

from copy import deepcopy

import pytest
from test_application_flow import application as application
from test_application_flow import wait_for
from test_application_resume import task_resume as task_resume
from test_bound_material_update import bound_pipeline as bound_pipeline
from test_bound_preparation_owner import queued_bound_preparation as queued_bound_preparation
from test_canonical_career_sources import canonical as canonical
from test_full_latex_generation import full_latex as full_latex
from test_j08_flow_combination import finish_json_writing, prepare_materials, start_json_writing
from test_j08_flow_combination import json_flow as json_flow

from career_evidence_graph.application_flow import ApplicationFlowService
from career_evidence_graph.career_portal_data import PortalDataError


def test_progress_reads_preparation_without_dispatch_or_execution_projection(application, tmp_path):
    applications, job = application
    calls = []
    flow = ApplicationFlowService(
        applications,
        tmp_path / "flow",
        callbacks={
            "analysis": lambda task: calls.append("analysis"),
            "worker": lambda task: calls.append("worker"),
        },
    )
    try:
        task = flow.create(job["id"], job["revision"])
        before = {p: p.read_bytes() for p in flow.root.rglob("*") if p.is_file()}
        progress = flow.progress(task["id"])
        assert progress["status"] == "not_started"
        assert progress["phase"] == "analysis"
        assert progress["task_id"] == task["id"]
        assert progress["task_revision"] == task["revision"]
        assert progress["analysis"]["status"] == "pending"
        assert progress["resume"]["status"] == "pending"
        assert progress["letter"]["status"] == "not_started"
        assert progress["material_consistency"]["status"] == "not_started"
        assert progress["can_prepare_execution"] is False
        assert calls == []
        assert {p: p.read_bytes() for p in flow.root.rglob("*") if p.is_file()} == before
    finally:
        flow.close()


def test_prepare_keeps_analysis_as_a_route_boundary(application, tmp_path):
    from test_job_explanations import requirement

    applications, job = application
    calls = []
    flow = ApplicationFlowService(
        applications,
        tmp_path / "flow",
        callbacks={
            "analysis": lambda task: (
                calls.append("analysis") or {"id": "analysis", "requirements": [requirement()]}
            ),
            "resume": lambda task: calls.append("resume"),
        },
    )
    try:
        task = flow.create(job["id"], job["revision"])
        flow.prepare(task["id"], task["revision"], request_id="initial-preparation")
        ready = wait_for(flow, task["id"], lambda row: row["status"] == "analysis_ready")
        assert calls == ["analysis"]
        progress = flow.progress(task["id"])
        assert progress["phase"] == "materials" and progress["status"] == "not_started"
        assert progress["analysis"]["status"] == "ready"
        assert progress["task_revision"] == ready["revision"]
        # Route selection is still required before the caller advances materials.
        assert flow.prepare(task["id"], ready["revision"], analysis_only=True) == progress
        assert calls == ["analysis"]
    finally:
        flow.close()


@pytest.mark.parametrize(
    "error_code", ["resume_author_failed", "resume_author_needs_recheck", "resume_author_paused"]
)
def test_preparation_recovery_distinguishes_known_failure_unknown_result_and_pause(
    application, tmp_path, error_code
):
    from test_job_explanations import requirement

    applications, job = application
    calls = []

    def rejected(request):
        calls.append(request["stages"]["resume"]["attempt_id"])
        raise PortalDataError(error_code, "Synthetic retained author result", 409)

    flow = ApplicationFlowService(
        applications,
        tmp_path / "flow",
        callbacks={
            "analysis": lambda task: {"id": "analysis", "requirements": [requirement()]},
            "resume": rejected,
        },
    )
    try:
        task = flow.create(job["id"], job["revision"])
        flow.prepare(task["id"], task["revision"])
        task = wait_for(flow, task["id"], lambda row: row["status"] == "analysis_ready")
        flow.start(task["id"], task["revision"], "resume")
        task = wait_for(flow, task["id"], lambda row: row["status"] in {"failed", "needs_recheck"})
        original_attempt = calls[0]
        if error_code == "resume_author_paused":
            # Ordinary automatic preparation still resumes a known pause without a request ID.
            for _ in range(2):
                flow.prepare(task["id"], task["revision"])
                task = wait_for(flow, task["id"], lambda row: row["status"] == "failed")
            assert len(calls) == 3
            assert not task.get("preparation_attempts")
            # Supplying an explicit identity consumes it even when the author pauses again.
            flow.prepare(task["id"], task["revision"], request_id="prepare-paused-author")
            task = wait_for(flow, task["id"], lambda row: row["status"] == "failed")
            retained = flow.progress(task["id"])
            assert (
                flow.prepare(task["id"], task["revision"], request_id="prepare-paused-author")
                == retained
            )
            assert len(calls) == 4
            return
        before = deepcopy(flow.progress(task["id"]))
        for _ in range(2):
            assert flow.prepare(task["id"], task["revision"]) == before
        assert calls == [original_attempt]
        if error_code == "resume_author_needs_recheck":
            assert before["status"] == "needs_recheck"
            assert before["continuation"] is None
            assert (
                flow.continue_preparation(
                    task["id"], task["revision"], request_id="cannot-replay-unknown"
                )
                == before
            )
            assert (
                flow.reconcile_preparation(
                    task["id"], task["revision"], request_id="no-original-receipt"
                )
                == before
            )
            assert calls == [original_attempt]
        else:
            assert before["status"] == "waiting"
            assert before["continuation"] == {"task_id": task["id"], "attempt_id": original_attempt}
            flow.continue_preparation(
                task["id"],
                task["revision"],
                request_id="one-retry",
                expected_attempt_id=original_attempt,
            )
            task = wait_for(flow, task["id"], lambda row: row["status"] == "failed")
            assert len(calls) == 2 and calls[1] != original_attempt
            retained = flow.progress(task["id"])
            assert (
                flow.continue_preparation(
                    task["id"],
                    task["revision"],
                    request_id="stale-original-retry",
                    expected_attempt_id=original_attempt,
                )
                == retained
            )
            assert len(calls) == 2
    finally:
        flow.close()


def test_cancelled_preparation_cannot_be_restarted(application, tmp_path):
    applications, job = application
    flow = ApplicationFlowService(applications, tmp_path / "flow")
    try:
        task = flow.create(job["id"], job["revision"])
        cancelled = flow.cancel_preparation(task["id"], task["revision"])
        progress = flow.progress(task["id"])
        assert progress["status"] == "cancelled"
        with pytest.raises(PortalDataError) as rejected:
            flow.continue_preparation(
                task["id"], cancelled["revision"], request_id="must-not-resurrect"
            )
        assert rejected.value.code == "flow_cancelled"
        assert flow.progress(task["id"]) == progress
    finally:
        flow.close()


@pytest.mark.parametrize("letter_running", [False, True])
def test_preparation_ready_is_not_replaced_by_execution_status(
    application, tmp_path, letter_running
):
    from test_job_explanations import requirement

    applications, job = application
    flow = ApplicationFlowService(
        applications,
        tmp_path / "flow",
        callbacks={
            "analysis": lambda task: {"id": "analysis", "requirements": [requirement()]},
            "resume": lambda task: {"id": "pdf", "pdf_sha256": "b" * 64},
            "worker_reference": lambda task: pytest.fail("Progress must not inspect execution"),
        },
    )
    try:
        task = flow.create(job["id"], job["revision"])
        flow.prepare(task["id"], task["revision"])
        task = wait_for(flow, task["id"], lambda row: row["status"] == "analysis_ready")
        flow.start(task["id"], task["revision"], "resume")
        task = wait_for(flow, task["id"], lambda row: row["status"] == "resume_ready")
        # Replay an existing queued execution binding; preparation is already complete.
        with applications.write_lock():
            state = flow._load()
            current = flow._task(state, task["id"])
            current.update(status="queued", worker_ref={"batch_id": "saved", "job_id": job["id"]})
            if letter_running:
                current["automatic_materials"] = True
                current["stages"]["letter"] = {"status": "running", "attempt_id": "d" * 32}
            flow._save(state)
        before = {p: p.read_bytes() for p in flow.root.rglob("*") if p.is_file()}
        progress = flow.progress(task["id"])
        assert progress["status"] == ("running" if letter_running else "ready")
        # Materials are ready only once the letter is adopted too.
        assert progress["can_prepare_execution"] is not letter_running
        assert progress["task"]["status"] == "queued"
        assert progress["execution_ref"] == {"batch_id": "saved", "job_id": job["id"]}
        assert {p: p.read_bytes() for p in flow.root.rglob("*") if p.is_file()} == before
    finally:
        flow.close()


@pytest.mark.parametrize(
    ("stage", "stage_status", "task_status"),
    [
        ("resume", "running", "resume_generating"),
        ("resume", "failed", "failed"),
        ("export", "running", "exporting"),
        ("export", "failed", "export_failed"),
    ],
)
def test_retained_pdf_does_not_complete_new_preparation(
    application, tmp_path, stage, stage_status, task_status
):
    from test_job_explanations import requirement

    applications, job = application
    calls = []
    flow = ApplicationFlowService(
        applications,
        tmp_path / "flow",
        callbacks={
            "analysis": lambda task: {"id": "analysis", "requirements": [requirement()]},
            "resume": lambda task: {"id": "old-pdf", "pdf_sha256": "b" * 64},
            "export": lambda task: calls.append("export"),
        },
    )
    try:
        task = flow.create(job["id"], job["revision"])
        flow.prepare(task["id"], task["revision"])
        task = wait_for(flow, task["id"], lambda row: row["status"] == "analysis_ready")
        flow.start(task["id"], task["revision"], "resume")
        wait_for(flow, task["id"], lambda row: row["status"] == "resume_ready")
        # Replay a saved replacement attempt which deliberately retains the old PDF.
        with applications.write_lock():
            state = flow._load()
            current = flow._task(state, task["id"])
            current["status"] = task_status
            if stage == "export":
                current["automatic_materials"] = True
            current["stages"][stage] = {
                "status": stage_status,
                "attempt_id": "c" * 32,
                **({"error_code": "flow_stage_failed"} if stage_status == "failed" else {}),
            }
            flow._save(state)
        progress = flow.progress(task["id"])
        assert progress["task"]["resume_id"] == "old-pdf"
        assert progress["can_prepare_execution"] is False
        assert progress["status"] == ("running" if stage_status == "running" else "failed")
        assert flow.prepare(task["id"], progress["task_revision"]) == progress
        assert calls == []
    finally:
        flow.close()


def test_reconcile_preparation_reads_only_original_completed_pdf(json_flow):
    case = json_flow
    task, _ = finish_json_writing(case, start_json_writing(case))
    build = case.store.build_pdf
    results = []

    def lost_response(*args, **kwargs):
        results.append(build(*args, **kwargs))
        raise OSError("Synthetic lost response after archive completion")

    case.store.build_pdf = lost_response
    case.flow.export_pdf(task["id"], task["revision"], task["draft_id"], task["draft_sha256"])
    task = wait_for(case.flow, task["id"], lambda row: row["status"] == "needs_recheck")
    assert len(results) == 1
    original = case.store.pdf(results[0]["id"])

    def forbidden(*args, **kwargs):
        pytest.fail("Reconciliation cannot build or capture a new PDF")

    case.store.build_pdf = forbidden
    case.store.prism_client.read_compiled = forbidden
    case.store.prism_client.compile = forbidden
    progress = case.flow.reconcile_preparation(
        task["id"], task["revision"], request_id="read-original-pdf"
    )
    assert progress["status"] == "ready"
    assert progress["task"]["resume_id"] == results[0]["id"]
    assert case.store.pdf(progress["task"]["resume_id"]) == original
    assert len(results) == 1


@pytest.mark.parametrize(
    "retained_state", ["reset", "inflight", "failed_stale_attempt", "pending_attempt", "bound_pdf"]
)
def test_explicit_analysis_reset_preserves_material_history_and_starts_once(
    json_flow, retained_state
):
    case, attempts = json_flow, []
    flow = case.flow
    assert flow.preparation_only is False
    task, _ = finish_json_writing(case, start_json_writing(case))
    original = prepare_materials(flow, task)
    old_pdf = case.store.pdf(original["resume_id"])
    original_artifacts = deepcopy(original["artifacts"])
    analyze = flow.callbacks["analysis"]

    def analyze_again(request):
        attempts.append(request["stages"]["analysis"]["attempt_id"])
        return analyze(request)

    flow.callbacks["analysis"] = analyze_again
    job = case.applications.get_application(original["application_id"])
    updated_job = case.applications.update_application(
        job["id"], {"location": "Zurich, Switzerland"}, job["revision"]
    )
    task = flow.update_inputs(original["id"], original["revision"], updated_job["revision"])
    assert task["status"] == "stale"
    assert task["stages"]["analysis"] == {"status": "pending"}
    assert task["analysis_id"] is None and task["resume_id"] is None
    assert task["origin"] == original["origin"]
    assert task["source_checkpoint"] == original["source_checkpoint"]
    assert task["artifacts"] == original_artifacts
    assert task["input_epoch"] == original["input_epoch"] + 1
    if retained_state != "reset":
        with flow.applications.write_lock():
            state = flow._load()
            task = flow._task(state, task["id"])
            if retained_state == "bound_pdf":
                task.update(
                    resume_id=original["resume_id"], resume_sha256=original["resume_sha256"]
                )
            else:
                task["stages"]["analysis"] = {
                    "status": {
                        "inflight": "running",
                        "failed_stale_attempt": "failed",
                        "pending_attempt": "pending",
                    }[retained_state],
                    "attempt_id": original["stages"]["analysis"]["attempt_id"],
                }
                if retained_state == "failed_stale_attempt":
                    task["stages"]["analysis"]["error_code"] = "flow_inputs_stale"
            flow._save(state)
    before = flow.progress(task["id"])
    if retained_state != "reset":
        assert before["analysis"]["status"] == "unknown"
        assert flow.prepare(task["id"], before["task_revision"], analysis_only=True) == before
        assert attempts == []
    else:
        assert flow.analysis_outcome(task["id"])["status"] == "pending"
        assert before["status"] == "not_started" and before["phase"] == "analysis"
        with flow.applications.write_lock():
            started = flow.prepare(task["id"], before["task_revision"], analysis_only=True)
            repeated = flow.prepare(task["id"], started["task_revision"], analysis_only=True)
            assert repeated == started
        task = wait_for(flow, task["id"], lambda row: row["status"] == "analysis_ready")
        assert len(attempts) == 1
        assert attempts[0] != original["stages"]["analysis"]["attempt_id"]
        assert task["id"] == original["id"] and task["resume_id"] is None
        assert task["stages"]["resume"] == task["stages"]["export"] == {"status": "pending"}
        assert task["artifacts"][: len(original_artifacts)] == original_artifacts
    assert case.store.pdf(original["resume_id"]) == old_pdf


@pytest.mark.parametrize("initial_error", ["resume_author_failed", "resume_author_paused"])
def test_continue_request_is_bound_to_original_failed_attempt(application, tmp_path, initial_error):
    from test_job_explanations import requirement

    applications, job = application
    calls = []

    def rejected(task):
        calls.append(task["stages"]["resume"]["attempt_id"])
        code = initial_error if len(calls) == 1 else "resume_author_failed"
        raise PortalDataError(code, "Synthetic known author result", 409)

    flow = ApplicationFlowService(
        applications,
        tmp_path / "flow",
        callbacks={
            "analysis": lambda task: {"id": "analysis", "requirements": [requirement()]},
            "resume": rejected,
        },
    )
    try:
        task = flow.create(job["id"], job["revision"])
        flow.prepare(task["id"], task["revision"])
        task = wait_for(flow, task["id"], lambda row: row["status"] == "analysis_ready")
        flow.start(task["id"], task["revision"], "resume")
        task = wait_for(flow, task["id"], lambda row: row["status"] == "failed")
        original = calls[0]
        original_revision = task["revision"]
        flow.continue_preparation(task["id"], task["revision"], request_id="same-continue")
        task = wait_for(flow, task["id"], lambda row: row["status"] == "failed")
        assert len(calls) == 2
        callbacks = flow.callbacks
        flow.close()
        flow = ApplicationFlowService(applications, tmp_path / "flow", callbacks=callbacks)
        retained = flow.progress(task["id"])
        assert (
            flow.continue_preparation(task["id"], task["revision"], request_id="same-continue")
            == retained
        )
        assert len(calls) == 2
        assert (
            flow.continue_preparation(task["id"], original_revision, request_id="same-continue")
            == retained
        )
        with pytest.raises(PortalDataError) as conflict:
            flow.continue_preparation(
                task["id"],
                task["revision"],
                request_id="same-continue",
                expected_attempt_id=calls[1],
            )
        assert conflict.value.code == "flow_preparation_request_conflict"
        assert flow.progress(task["id"]) == retained
        # A different explicit Continue may retry; the first request remains consumed.
        flow.continue_preparation(task["id"], task["revision"], request_id="next-continue")
        task = wait_for(flow, task["id"], lambda row: row["status"] == "failed")
        assert len(calls) == 3
        retained = flow.progress(task["id"])
        assert (
            flow.continue_preparation(
                task["id"],
                task["revision"],
                request_id="same-continue",
                expected_attempt_id=original,
            )
            == retained
        )
        assert len(calls) == 3
        # An explicit input update cannot rebind an already used Continue identity.
        updated = flow.update_inputs(
            task["id"], task["revision"], job["revision"], inputs={"changed": "fixed-input"}
        )
        with pytest.raises(PortalDataError) as conflict:
            flow.continue_preparation(task["id"], updated["revision"], request_id="same-continue")
        assert conflict.value.code == "flow_preparation_request_conflict"
        assert len(calls) == 3
    finally:
        flow.close()


@pytest.mark.parametrize("first_stage", ["analysis", "resume", "export", "letter"])
def test_continue_first_dispatch_cannot_be_reused_for_a_later_author_failure(
    json_flow, first_stage
):
    case, calls = json_flow, []
    flow = case.flow
    request_id = "first-dispatch-" + first_stage

    def rejected(task):
        calls.append(task["stages"]["resume"]["attempt_id"])
        raise PortalDataError("resume_author_failed", "Synthetic known author failure", 409)

    if first_stage in {"analysis", "resume"}:
        task = flow.create(case.job["id"], case.job["revision"])
        if first_stage == "analysis":
            flow.continue_preparation(task["id"], task["revision"], request_id=request_id)
        else:
            flow.start(task["id"], task["revision"], "analysis")
        task = wait_for(flow, task["id"], lambda row: row["status"] == "analysis_ready")
        task = flow.prepare_automatic_materials(
            task["id"], task["revision"], project_root=str(case.project), main="main.tex"
        )
        flow.callbacks["resume"] = rejected
        if first_stage == "resume":
            flow.continue_preparation(task["id"], task["revision"], request_id=request_id)
        else:
            flow.start(task["id"], task["revision"], "resume")
    else:
        task, _ = finish_json_writing(case, start_json_writing(case))

        def settled(row):
            return all(
                part.get("status") not in {"queued", "running"}
                for part in (*row["stages"].values(), row.get("material_consistency", {}))
            )

        if first_stage == "export":
            # The letter and its PDF come first; the Continue then dispatches the export.
            for _ in range(2):
                flow.prepare(task["id"], task["revision"])
                task = wait_for(flow, task["id"], settled)
        flow.continue_preparation(task["id"], task["revision"], request_id=request_id)
        task = wait_for(flow, task["id"], settled)
        while task["status"] == "draft_ready":
            flow.prepare(task["id"], task["revision"])
            task = wait_for(flow, task["id"], settled)
        task = wait_for(
            flow,
            task["id"],
            lambda row: row["status"] in {"resume_ready", "materials_ready"} and settled(row),
        )
        flow.callbacks["resume"] = rejected
        flow.start(task["id"], task["revision"], "resume", retry=True)
    task = wait_for(flow, task["id"], lambda row: row["status"] == "failed")
    assert len(calls) == 1
    try:
        flow.continue_preparation(task["id"], task["revision"], request_id=request_id)
    except PortalDataError as conflict:
        assert conflict.code == "flow_preparation_request_conflict"
    wait_for(flow, task["id"], lambda row: row["status"] == "failed")
    assert len(calls) == 1


@pytest.mark.parametrize(
    ("update_status", "preparation_status", "ready"),
    [
        ("staged", "waiting", False),
        ("preparing", "running", False),
        ("needs_recheck", "needs_recheck", False),
        ("awaiting_page", "waiting", False),
        ("committing", "running", False),
        ("bound", "waiting", False),
        ("complete", "ready", True),
        ("unrecognized", "needs_recheck", False),
    ],
)
def test_bound_update_progress_keeps_old_materials_without_claiming_preparation_ready(
    queued_bound_preparation, update_status, preparation_status, ready
):
    flow, worker, store, calls, original, _queued = queued_bound_preparation
    # Replay each retained lifecycle point; a read cannot dispatch or finish its update.
    with flow.applications.write_lock():
        state = flow._load()
        task = flow._task(state, original["id"])
        execution_ref = deepcopy(task["worker_ref"])
        update = task["material_update"]
        update["status"] = update_status
        update["candidate"] = {
            "resume_id": "independent-candidate",
            "resume_sha256": "c" * 64,
            "stages": {"resume": {"status": "complete"}, "export": {"status": "complete"}},
        }
        if update_status == "needs_recheck":
            update["error_code"] = "resume_export_needs_recheck"
        flow._save(state)
    before = flow.path.read_bytes(), worker.store.path.read_bytes()
    before_calls = len(calls), len(store.prism_client.calls)
    progress = flow.progress(original["id"])
    assert progress["status"] == preparation_status
    assert progress["can_prepare_execution"] is ready
    assert progress["material_update"]["status"] == update_status
    assert progress["material_update"]["candidate"]["resume_id"] == "independent-candidate"
    assert progress["task"]["resume_id"] == original["resume_id"]
    assert progress["task"]["resume_sha256"] == original["resume_sha256"]
    assert progress["execution_ref"] == execution_ref
    assert (flow.path.read_bytes(), worker.store.path.read_bytes()) == before
    assert (len(calls), len(store.prism_client.calls)) == before_calls
