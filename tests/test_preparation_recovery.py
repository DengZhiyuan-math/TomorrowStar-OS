"""Preparation recovery preserves checkpoints and requires explicit continuation."""

import threading

import pytest
from test_application_flow import application as application
from test_application_flow import wait_for
from test_pdf_export_flow import reviewed_draft as reviewed_draft

from career_evidence_graph.application_flow import ApplicationFlowService
from career_evidence_graph.application_flow_store import assemble, read_flow_state
from career_evidence_graph.career_portal_data import PortalDataError


def test_interrupted_model_records_original_attempt_once_and_late_return_cannot_publish(
    application, tmp_path
):
    applications, job = application
    entered, release, exited = threading.Event(), threading.Event(), threading.Event()
    calls = []

    def analyze(task):
        calls.append(task["id"])
        entered.set()
        assert release.wait(3)
        exited.set()
        return {"id": "retired-result"}

    flow = ApplicationFlowService(
        applications, tmp_path / "flow", preparation_only=True, callbacks={"analysis": analyze}
    )
    task = flow.create(job["id"], job["revision"], inputs={"sources_revision": "source-v1"})
    started = flow.start(task["id"], task["revision"], "analysis")
    assert entered.wait(2)
    flow.close()
    observer = ApplicationFlowService(
        applications, tmp_path / "flow", preparation_only=True, callbacks={"analysis": analyze}
    )
    try:
        recovered = observer.snapshot(task["id"])["active_task"]
        history = recovered["recovery_history"]
        assert len(history) == 1
        assert history[0]["stage"] == "analysis"
        assert history[0]["previous_status"] == "running"
        assert history[0]["status"] == "failed"
        assert history[0]["reason"] == "flow_interrupted"
        assert history[0]["attempt_id"] == started["stages"]["analysis"]["attempt_id"]
        assert history[0]["input_epoch"] == 0
        assert len(history[0]["inputs_revision"]) == 64
        assert history[0]["job_binding"] == task["job_binding"]
        with pytest.raises(PortalDataError) as error:
            observer.start(task["id"], recovered["revision"], "analysis", retry=True)
        assert error.value.code == "flow_runtime_busy"
        assert observer.snapshot(task["id"])["active_task"] == recovered
        release.set()
        assert exited.wait(2)
        flow.close()
        assert observer.snapshot(task["id"])["active_task"] == recovered
        assert recovered["analysis_id"] is None and recovered["artifacts"] == []
        assert calls == [task["id"]]
    finally:
        release.set()
        flow.close()
        observer.close()
    reopened = ApplicationFlowService(applications, tmp_path / "flow", preparation_only=True)
    try:
        assert reopened.snapshot(task["id"])["active_task"] == recovered
    finally:
        reopened.close()


@pytest.mark.parametrize("checkpoint", ["draft", "reviewed_draft", "pdf", "materials"])
def test_completed_material_checkpoints_reopen_unchanged_without_any_callback(
    reviewed_draft, checkpoint
):
    flow, task, calls = reviewed_draft
    if checkpoint != "draft":
        task = flow.review_draft(
            task["id"], task["revision"], task["draft_id"], task["draft_sha256"]
        )
    if checkpoint in {"pdf", "materials"}:
        flow.export_pdf(task["id"], task["revision"], task["draft_id"], task["draft_sha256"])
        task = wait_for(flow, task["id"], lambda row: row["status"] == "materials_ready")
    if checkpoint == "materials":
        flow.confirm_materials(
            task["id"], task["revision"], task["resume_id"], task["resume_sha256"]
        )
    before = flow.snapshot(task["id"])["active_task"]
    expected_calls = list(calls)
    flow.close()

    def forbidden(*args):
        calls.append("unexpected-recovery-call")
        raise AssertionError("Reopening a saved checkpoint must not execute work")

    reopened = ApplicationFlowService(
        flow.applications,
        flow.root,
        preparation_only=True,
        callbacks={
            name: forbidden
            for name in (
                "analysis",
                "resume",
                "export",
                "reconcile_export",
                "verify_draft",
                "verify_materials",
            )
        },
    )
    try:
        assert reopened.snapshot(task["id"])["active_task"] == before
        assert reopened.snapshot(task["id"])["active_task"] == before
        assert calls == expected_calls
        assert before.get("recovery_history", []) == []
    finally:
        reopened.close()


def test_known_pdf_failure_reopens_without_repeating_render_or_generation(reviewed_draft):
    flow, task, calls = reviewed_draft
    task = flow.review_draft(task["id"], task["revision"], task["draft_id"], task["draft_sha256"])
    original = flow.callbacks["export"]

    def known_failure(task):
        calls.append("known-export-failure")
        raise PortalDataError("resume_export_failed", "Synthetic renderer failed.", 503)

    flow.callbacks["export"] = known_failure
    flow.export_pdf(task["id"], task["revision"], task["draft_id"], task["draft_sha256"])
    task = wait_for(flow, task["id"], lambda row: row["status"] == "export_failed")
    review = task["draft_review"]
    flow.close()
    reopened = ApplicationFlowService(
        flow.applications,
        flow.root,
        preparation_only=True,
        callbacks=flow.callbacks | {"export": original},
    )
    try:
        saved = reopened.snapshot(task["id"])["active_task"]
        assert saved == task and saved.get("recovery_history", []) == []
        assert calls == ["generate", "known-export-failure"]
        with pytest.raises(PortalDataError) as error:
            reopened.export_pdf(
                saved["id"], saved["revision"], saved["draft_id"], saved["draft_sha256"]
            )
        assert error.value.code == "flow_retry_required"
        reopened.export_pdf(
            saved["id"], saved["revision"], saved["draft_id"], saved["draft_sha256"], retry=True
        )
        exported = wait_for(reopened, task["id"], lambda row: row["status"] == "materials_ready")
        assert exported["draft_review"] == review and calls == [
            "generate",
            "known-export-failure",
            "export",
        ]
    finally:
        reopened.close()


@pytest.mark.parametrize("previous_status", ["queued", "running"])
def test_interrupted_pdf_reopens_as_not_started_or_requires_read_only_receipt_reconciliation(
    reviewed_draft, previous_status
):
    flow, task, calls = reviewed_draft
    task = flow.review_draft(task["id"], task["revision"], task["draft_id"], task["draft_sha256"])
    original = flow.callbacks["export"]
    entered, release, exited = threading.Event(), threading.Event(), threading.Event()
    receipts, reads = {}, []

    def render(task):
        result = original(task)
        receipts["result"] = result
        entered.set()
        assert release.wait(3)
        exited.set()
        return result

    flow.callbacks["export"] = render
    if previous_status == "queued":
        with flow.applications.write_lock():
            flow.export_pdf(task["id"], task["revision"], task["draft_id"], task["draft_sha256"])
            flow.close()
    else:
        flow.export_pdf(task["id"], task["revision"], task["draft_id"], task["draft_sha256"])
        assert entered.wait(2)
        flow.close()
        release.set()
        assert exited.wait(2)
        flow.close()
    interrupted = flow.snapshot(task["id"])["active_task"]
    record = interrupted["recovery_history"][-1]
    assert record["previous_status"] == previous_status and record["stage"] == "export"
    assert record["status"] == ("failed" if previous_status == "queued" else "needs_recheck")
    assert record["reason"] == (
        "flow_export_not_started" if previous_status == "queued" else "flow_interrupted"
    )
    assert interrupted["draft_review"] == task["draft_review"]
    assert interrupted["draft_sha256"] == task["draft_sha256"]
    assert calls == (["generate"] if previous_status == "queued" else ["generate", "export"])

    def reconcile(task):
        reads.append(task["stages"]["export"]["attempt_id"])
        return receipts["result"]

    reopened = ApplicationFlowService(
        flow.applications,
        flow.root,
        preparation_only=True,
        callbacks=flow.callbacks | {"export": original, "reconcile_export": reconcile},
    )
    try:
        saved = reopened.snapshot(task["id"])["active_task"]
        assert saved == interrupted and reads == []
        if previous_status == "queued":
            with pytest.raises(PortalDataError):
                reopened.recheck_export(saved["id"], saved["revision"])
            reopened.export_pdf(
                saved["id"], saved["revision"], saved["draft_id"], saved["draft_sha256"], retry=True
            )
            exported = wait_for(
                reopened, task["id"], lambda row: row["status"] == "materials_ready"
            )
            assert reads == []
        else:
            with pytest.raises(PortalDataError) as error:
                reopened.export_pdf(
                    saved["id"],
                    saved["revision"],
                    saved["draft_id"],
                    saved["draft_sha256"],
                    retry=True,
                )
            assert error.value.code == "flow_export_recheck_required"
            exported = reopened.recheck_export(saved["id"], saved["revision"])
            assert reads == [record["attempt_id"]]
        assert exported["status"] == "materials_ready"
        assert exported["recovery_history"] == interrupted["recovery_history"]
        assert calls == ["generate", "export"]
    finally:
        release.set()
        reopened.close()


def test_each_explicit_interrupted_attempt_appends_history_without_replaying_or_erasing_it(
    application, tmp_path
):
    applications, job = application
    calls = []
    flow = ApplicationFlowService(
        applications,
        tmp_path / "flow",
        preparation_only=True,
        callbacks={"analysis": lambda task: calls.append(task)},
    )
    with applications.write_lock():
        task = flow.create(job["id"], job["revision"])
        first_attempt = flow.start(task["id"], task["revision"], "analysis")
        flow.close()
    first = flow.snapshot(task["id"])["active_task"]
    first_history = first["recovery_history"]
    assert len(first_history) == 1 and first_history[0]["previous_status"] == "queued"
    reopened = ApplicationFlowService(
        applications, flow.root, preparation_only=True, callbacks=flow.callbacks
    )
    with applications.write_lock():
        saved = reopened.snapshot(task["id"])["active_task"]
        assert saved == first and calls == []
        second_attempt = reopened.start(task["id"], saved["revision"], "analysis", retry=True)
        reopened.close()
    second = reopened.snapshot(task["id"])["active_task"]
    assert second["recovery_history"][:1] == first_history
    assert len(second["recovery_history"]) == 2
    assert [row["attempt_id"] for row in second["recovery_history"]] == [
        first_attempt["stages"]["analysis"]["attempt_id"],
        second_attempt["stages"]["analysis"]["attempt_id"],
    ]
    assert calls == []


def test_recovery_metadata_with_a_matching_task_digest_must_still_have_valid_bindings(
    application, tmp_path
):
    import json

    from career_evidence_graph.application_worker import digest

    applications, job = application
    flow = ApplicationFlowService(
        applications,
        tmp_path / "flow",
        preparation_only=True,
        callbacks={"analysis": lambda task: {"id": "never-admitted"}},
    )
    with applications.write_lock():
        task = flow.create(job["id"], job["revision"])
        flow.start(task["id"], task["revision"], "analysis")
        flow.close()
    original = flow.path.read_bytes()
    try:
        # flow.json is an index of task files (2026-11-09); an inline record still loads.
        state = read_flow_state(flow.root)
        task = state["tasks"][0]
        task["recovery_history"][0]["inputs_revision"] = "unverifiable-inputs"
        task["revision"] = digest({key: value for key, value in task.items() if key != "revision"})
        flow.path.write_text(json.dumps(state))
        with pytest.raises(PortalDataError) as error:
            flow.snapshot()
        assert error.value.code == "flow_invalid"
    finally:
        flow.path.write_bytes(original)
        flow.close()


def test_close_racing_with_an_adopted_checkpoint_preserves_the_complete_result(
    application, tmp_path, monkeypatch
):
    from career_evidence_graph._vendor import job_apply_store as helper

    applications, job = application
    entered, release, closing, closed = (threading.Event() for _ in range(4))
    calls = []
    flow = ApplicationFlowService(
        applications,
        tmp_path / "flow",
        preparation_only=True,
        callbacks={
            "analysis": lambda task: calls.append("analysis") or {"id": "saved-before-close"}
        },
    )
    write = helper.atomic_write_json

    def checkpoint(path, payload):
        if path == flow.path and assemble(flow.root, payload)["tasks"][0]["status"] == (
            "analysis_ready"
        ):
            entered.set()
            assert release.wait(3)
        return write(path, payload)

    def close():
        closing.set()
        flow.close()
        closed.set()

    monkeypatch.setattr(helper, "atomic_write_json", checkpoint)
    try:
        task = flow.create(job["id"], job["revision"])
        flow.start(task["id"], task["revision"], "analysis")
        assert entered.wait(2)
        closer = threading.Thread(target=close)
        closer.start()
        assert closing.wait(2)
        assert not closed.is_set()
        release.set()
        assert closed.wait(2)
        closer.join(2)
        result = flow.snapshot(task["id"])["active_task"]
        assert result["status"] == "analysis_ready"
        assert result["analysis_id"] == "saved-before-close"
        assert result["artifacts"][0]["adopted"] is True
        assert result.get("recovery_history", []) == [] and calls == ["analysis"]
    finally:
        release.set()
        flow.close()
