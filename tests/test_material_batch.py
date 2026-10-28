"""Bounded material batches preserve explicit pauses and single-job decisions."""

import pytest
from test_application_flow import application as application
from test_pdf_export_flow import reviewed_draft as reviewed_draft

from career_evidence_graph.application_flow import ApplicationFlowService
from career_evidence_graph.application_material_batch import MaterialBatch
from career_evidence_graph.career_portal_data import PortalDataError


def test_explicit_batch_selection_stays_paused_and_replay_does_not_duplicate(application, tmp_path):
    applications, job = application
    calls = []
    flow = ApplicationFlowService(
        applications,
        tmp_path / "flow",
        preparation_only=True,
        callbacks={"analysis": lambda task: calls.append(task)},
    )
    batch = MaterialBatch(flow)
    payload = {
        "request_id": "a" * 32,
        "items": [{"kind": "application", "id": job["id"], "revision": job["revision"]}],
    }
    try:
        saved = batch.request("batch-create", payload)
        assert saved["control"] == "paused"
        assert len(saved["items"]) == 1
        assert saved["items"][0]["status"] == "pending"
        assert batch.request("batch-create", payload)["id"] == saved["id"]
        assert flow.snapshot()["tasks"] == [] and calls == []
    finally:
        flow.close()


def test_pause_and_resume_require_current_revision_and_never_start_other_tasks(
    application, tmp_path
):
    applications, job = application
    flow = ApplicationFlowService(applications, tmp_path / "flow", preparation_only=True)
    batch = MaterialBatch(flow)
    try:
        saved = batch.request(
            "batch-create",
            {
                "request_id": "b" * 32,
                "items": [{"kind": "application", "id": job["id"], "revision": job["revision"]}],
            },
        )
        with applications.write_lock():
            running = batch.request(
                "batch-control",
                {
                    "batch_id": saved["id"],
                    "batch_revision": saved["revision"],
                    "operation": "resume",
                },
            )
            assert running["control"] == "running"
            with pytest.raises(PortalDataError) as error:
                batch.request(
                    "batch-control",
                    {
                        "batch_id": saved["id"],
                        "batch_revision": saved["revision"],
                        "operation": "pause",
                    },
                )
            assert error.value.code == "conflict"
            paused = batch.request(
                "batch-control",
                {
                    "batch_id": running["id"],
                    "batch_revision": running["revision"],
                    "operation": "pause",
                },
            )
            assert paused["control"] == "paused" and paused["epoch"] > running["epoch"]
        assert flow.snapshot()["tasks"] == []
    finally:
        flow.close()


def test_one_job_waits_for_draft_review_and_materials_do_not_unlock_next_job(application, tmp_path):
    from test_application_flow import wait_for
    from test_job_explanations import requirement

    applications, first = application
    second = applications.create_application(
        {"company": "Second Synthetic", "role_title": "Engineer", "job_description": "Python work."}
    )
    calls = []
    flow = ApplicationFlowService(
        applications,
        tmp_path / "flow",
        preparation_only=True,
        callbacks={
            "analysis": lambda task: {
                "id": "analysis-" + task["id"],
                "requirements": [requirement()],
            },
            "resume": lambda task: (
                calls.append(task["application_id"])
                or {"id": "draft-" + task["id"], "kind": "draft", "draft_sha256": "a" * 64}
            ),
            "verify_draft": lambda task: None,
            "verify_materials": lambda task: None,
            "export_configuration": lambda: "export-v1",
            "export": lambda task: {
                "id": task["stages"]["export"]["attempt_id"],
                "kind": "pdf",
                "pdf_sha256": "b" * 64,
                "draft_id": task["draft_id"],
                "draft_sha256": task["draft_sha256"],
                "export_configuration_revision": "export-v1",
            },
        },
    )
    batch = MaterialBatch(flow)
    try:
        saved = batch.request(
            "batch-create",
            {
                "request_id": "c" * 32,
                "items": [
                    {"kind": "application", "id": job["id"], "revision": job["revision"]}
                    for job in (first, second)
                ],
            },
        )
        batch.request(
            "batch-control",
            {"batch_id": saved["id"], "batch_revision": saved["revision"], "operation": "resume"},
        )
        import time

        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            state = flow.snapshot()
            if state["tasks"] and state["tasks"][0]["status"] == "draft_ready":
                break
            time.sleep(0.01)
        assert state["tasks"] and len(state["tasks"]) == 1
        task = state["tasks"][0]
        assert task["status"] == "draft_ready" and calls == [first["id"]]
        task = flow.review_draft(
            task["id"], task["revision"], task["draft_id"], task["draft_sha256"]
        )
        task = wait_for(flow, task["id"], lambda task: task["status"] == "materials_ready")
        flow.confirm_materials(
            task["id"], task["revision"], task["resume_id"], task["resume_sha256"]
        )
        state = flow.snapshot()
        saved = state["preparation_batch"]
        assert saved["items"][0]["status"] == "waiting_application_record"
        assert saved["items"][1]["status"] == "pending"
        assert len(state["tasks"]) == 1 and calls == [first["id"]]
        with pytest.raises(PortalDataError) as error:
            batch.request(
                "batch-control",
                {
                    "batch_id": saved["id"],
                    "batch_revision": saved["revision"],
                    "operation": "resume",
                },
            )
        assert error.value.code == "flow_batch_application_record_required"
    finally:
        flow.close()


def batch_until(flow, predicate):
    import time

    deadline = time.monotonic() + 3
    while time.monotonic() < deadline:
        current = flow.snapshot()["preparation_batch"]
        if predicate(current):
            return current
        time.sleep(0.01)
    pytest.fail("Material batch did not reach expected disposition")


def test_known_failure_and_missing_qualification_continue_but_only_manual_retry_recovers(
    application, tmp_path
):
    from test_job_explanations import requirement

    applications, first = application
    second = applications.create_application(
        {
            "company": "Unknown Permit Synthetic",
            "role_title": "Engineer",
            "job_description": "Python work.",
        }
    )
    calls = []

    def generate(task):
        calls.append(task["application_id"])
        if len(calls) == 1:
            raise PortalDataError("resume_failed", "Synthetic known generation failure.", 503)
        return {"id": "recovered", "kind": "draft", "draft_sha256": "a" * 64}

    flow = ApplicationFlowService(
        applications,
        tmp_path / "flow",
        preparation_only=True,
        callbacks={
            "analysis": lambda task: {
                "id": "analysis-" + task["id"],
                "requirements": [
                    requirement()
                    if task["application_id"] == first["id"]
                    else requirement("Work permit", judgment="unknown", hard=True)
                ],
            },
            "resume": generate,
        },
    )
    try:
        saved = flow.request(
            "batch-create",
            {
                "request_id": "d" * 32,
                "items": [
                    {"kind": "application", "id": job["id"], "revision": job["revision"]}
                    for job in (first, second)
                ],
            },
        )
        flow.request(
            "batch-control",
            {"batch_id": saved["id"], "batch_revision": saved["revision"], "operation": "resume"},
        )
        saved = batch_until(flow, lambda row: row["reason"] == "no_processable_items")
        assert [row["status"] for row in saved["items"]] == ["deferred", "needs_input"]
        assert calls == [first["id"]]
        retried = flow.request(
            "batch-retry",
            {
                "batch_id": saved["id"],
                "batch_revision": saved["revision"],
                "item_id": saved["items"][0]["item_id"],
            },
        )
        assert retried["control"] == "paused" and calls == [first["id"]]
        flow.request(
            "batch-control",
            {
                "batch_id": retried["id"],
                "batch_revision": retried["revision"],
                "operation": "resume",
            },
        )
        saved = batch_until(flow, lambda row: row["items"][0]["status"] == "waiting_draft_review")
        assert calls == [first["id"], first["id"]]
        assert saved["items"][1]["status"] == "needs_input"
    finally:
        flow.close()


def test_unknown_export_stops_every_job_until_explicit_read_only_reconciliation(
    application, tmp_path
):
    from test_job_explanations import requirement

    applications, first = application
    second = applications.create_application(
        {"company": "Second Synthetic", "role_title": "Engineer", "job_description": "Python work."}
    )
    calls = []

    def exported(task):
        return {
            "id": task["stages"]["export"]["attempt_id"],
            "kind": "pdf",
            "pdf_sha256": "b" * 64,
            "draft_id": task["draft_id"],
            "draft_sha256": task["draft_sha256"],
            "export_configuration_revision": "export-v1",
        }

    def unknown(task):
        calls.append("export")
        raise PortalDataError("resume_export_needs_recheck", "Synthetic unknown publish.", 409)

    flow = ApplicationFlowService(
        applications,
        tmp_path / "flow",
        preparation_only=True,
        callbacks={
            "analysis": lambda task: {"id": "a-" + task["id"], "requirements": [requirement()]},
            "resume": lambda task: {
                "id": "d-" + task["id"],
                "kind": "draft",
                "draft_sha256": "a" * 64,
            },
            "verify_draft": lambda task: None,
            "verify_materials": lambda task: None,
            "export_configuration": lambda: "export-v1",
            "export": unknown,
            "reconcile_export": exported,
        },
    )
    try:
        saved = flow.request(
            "batch-create",
            {
                "request_id": "e" * 32,
                "items": [
                    {"kind": "application", "id": job["id"], "revision": job["revision"]}
                    for job in (first, second)
                ],
            },
        )
        flow.request(
            "batch-control",
            {"batch_id": saved["id"], "batch_revision": saved["revision"], "operation": "resume"},
        )
        saved = batch_until(flow, lambda row: row["items"][0]["status"] == "waiting_draft_review")
        task = flow.snapshot()["active_task"]
        flow.review_draft(task["id"], task["revision"], task["draft_id"], task["draft_sha256"])
        saved = batch_until(flow, lambda row: row["control"] == "needs_recheck")
        for operation in ("resume", "cancel"):
            with pytest.raises(PortalDataError) as error:
                flow.request(
                    "batch-control",
                    {
                        "batch_id": saved["id"],
                        "batch_revision": saved["revision"],
                        "operation": operation,
                    },
                )
            assert error.value.code == "flow_batch_recheck_required"
        with pytest.raises(PortalDataError):
            flow.request(
                "batch-retry",
                {
                    "batch_id": saved["id"],
                    "batch_revision": saved["revision"],
                    "item_id": saved["items"][0]["item_id"],
                },
            )
        # A changed status is not evidence that the interrupted export was reconciled.
        with applications.write_lock():
            persisted = flow._load()
            changed = persisted["tasks"][0]
            changed["status"] = "export_failed"
            changed["stages"]["export"]["status"] = "failed"
            flow._save(persisted)
        with pytest.raises(PortalDataError) as error:
            flow.request(
                "batch-control",
                {
                    "batch_id": saved["id"],
                    "batch_revision": saved["revision"],
                    "operation": "resume",
                },
            )
        assert error.value.code == "flow_batch_recheck_required"
        with applications.write_lock():
            persisted = flow._load()
            changed = persisted["tasks"][0]
            changed["status"] = "needs_recheck"
            changed["stages"]["export"]["status"] = "needs_recheck"
            flow._save(persisted)
        task = flow.snapshot()["active_task"]
        flow.recheck_export(task["id"], task["revision"])
        saved = flow.snapshot()["preparation_batch"]
        assert saved["control"] == "paused"
        assert saved["items"][0]["status"] == "waiting_application_record"
        assert saved["items"][1]["status"] == "pending" and len(flow.snapshot()["tasks"]) == 1
        assert calls == ["export"]
    finally:
        flow.close()


def test_batch_cannot_capture_an_existing_single_job_call_or_unknown_result(application, tmp_path):
    import threading

    applications, job = application
    entered, release = threading.Event(), threading.Event()

    def analyze(task):
        entered.set()
        assert release.wait(3)
        return {"id": "late"}

    flow = ApplicationFlowService(
        applications, tmp_path / "flow", preparation_only=True, callbacks={"analysis": analyze}
    )
    try:
        task = flow.create(job["id"], job["revision"])
        flow.start(task["id"], task["revision"], "analysis")
        assert entered.wait(2)
        with pytest.raises(PortalDataError) as error:
            flow.request(
                "batch-create",
                {
                    "request_id": "f" * 32,
                    "items": [
                        {"kind": "application", "id": job["id"], "revision": job["revision"]}
                    ],
                },
            )
        assert error.value.code == "flow_batch_existing_work"
        assert flow.snapshot()["preparation_batch"] is None
    finally:
        release.set()
        flow.close()


def test_unknown_source_is_only_unlocked_by_a_persisted_reconciliation(application, tmp_path):
    from test_job_explanations import requirement

    applications, job = application
    candidate = {
        "id": "1" * 32,
        "revision": "2" * 64,
        "company": "Synthetic Employer",
        "role_title": "ML Engineer",
        "acquisition_checkpoint": "needs_recheck",
        "selection_status": "unselected",
    }
    selections = []

    def select(item):
        selections.append(item["revision"])
        if candidate["acquisition_checkpoint"] == "needs_recheck":
            raise PortalDataError("recommendation_needs_recheck", "Synthetic unknown source.", 409)
        return job

    flow = ApplicationFlowService(
        applications,
        tmp_path / "flow",
        preparation_only=True,
        callbacks={
            "batch_candidates": lambda: {"applications": [job], "recommendations": [candidate]},
            "batch_select": select,
            "analysis": lambda task: {"id": "analysis", "requirements": [requirement()]},
            "resume": lambda task: {"id": "draft", "kind": "draft", "draft_sha256": "a" * 64},
        },
    )
    try:
        saved = flow.request(
            "batch-create",
            {
                "request_id": "1" * 32,
                "items": [
                    {
                        "kind": "recommendation",
                        "id": candidate["id"],
                        "revision": candidate["revision"],
                    }
                ],
            },
        )
        flow.request(
            "batch-control",
            {"batch_id": saved["id"], "batch_revision": saved["revision"], "operation": "resume"},
        )
        saved = batch_until(flow, lambda b: b["control"] == "needs_recheck")
        with pytest.raises(PortalDataError):
            flow.request(
                "batch-control",
                {
                    "batch_id": saved["id"],
                    "batch_revision": saved["revision"],
                    "operation": "resume",
                },
            )
        assert selections == ["2" * 64] and flow.snapshot()["tasks"] == []
        candidate.update(
            acquisition_checkpoint="complete", revision="3" * 64, jd_completeness="full"
        )
        flow.request(
            "batch-control",
            {"batch_id": saved["id"], "batch_revision": saved["revision"], "operation": "resume"},
        )
        saved = batch_until(flow, lambda b: b["items"][0]["status"] == "waiting_draft_review")
        assert selections == ["2" * 64, "3" * 64]
        assert saved["items"][0]["revision"] == "3" * 64
    finally:
        flow.close()


def test_saved_batch_rejects_invalid_dispositions_even_with_a_matching_digest(
    application, tmp_path
):
    import json

    from career_evidence_graph.application_worker import digest

    applications, job = application
    flow = ApplicationFlowService(applications, tmp_path / "flow", preparation_only=True)
    try:
        flow.request(
            "batch-create",
            {
                "request_id": "2" * 32,
                "items": [{"kind": "application", "id": job["id"], "revision": job["revision"]}],
            },
        )
        original = flow.path.read_bytes()
        state = json.loads(original)
        state["preparation_batch"]["items"][0]["status"] = "application_completed"
        batch = state["preparation_batch"]
        batch["revision"] = digest({k: v for k, v in batch.items() if k != "revision"})
        flow.path.write_text(json.dumps(state))
        with pytest.raises(PortalDataError) as error:
            flow.snapshot()
        assert error.value.code == "flow_batch_invalid"
    finally:
        flow.path.write_bytes(original)
        flow.close()


def test_existing_match_order_and_manual_pending_order_share_the_batch(application, tmp_path):
    from test_application_flow import wait_for
    from test_job_explanations import requirement

    applications, first = application
    second = applications.create_application(
        {
            "company": "Strong Synthetic",
            "role_title": "Engineer",
            "job_description": "Python engineering.",
        }
    )
    flow = ApplicationFlowService(
        applications,
        tmp_path / "flow",
        preparation_only=True,
        callbacks={
            "analysis": lambda task: {
                "id": "a-" + task["id"],
                "requirements": [
                    requirement(
                        judgment="partial" if task["application_id"] == first["id"] else "supported"
                    )
                ],
            }
        },
    )
    try:
        for job in (first, second):
            task = flow.create(job["id"], job["revision"])
            flow.start(task["id"], task["revision"], "analysis")
            wait_for(flow, task["id"], lambda t: t["status"] == "analysis_ready")
        saved = flow.request(
            "batch-create",
            {
                "request_id": "3" * 32,
                "items": [
                    {"kind": "application", "id": job["id"], "revision": job["revision"]}
                    for job in (first, second)
                ],
            },
        )
        assert [row["application_id"] for row in saved["items"]] == [second["id"], first["id"]]
        reordered = flow.request(
            "batch-reorder",
            {
                "batch_id": saved["id"],
                "batch_revision": saved["revision"],
                "item_id": saved["items"][1]["item_id"],
                "direction": "up",
            },
        )
        assert [row["application_id"] for row in reordered["items"]] == [first["id"], second["id"]]
        assert reordered["control"] == "paused" and len(flow.snapshot()["tasks"]) == 2
    finally:
        flow.close()


def test_pause_finishes_current_call_without_generating_and_reopen_stays_paused(
    application, tmp_path
):
    import threading

    from test_application_flow import wait_for
    from test_job_explanations import requirement

    applications, job = application
    entered, release = threading.Event(), threading.Event()
    calls = []

    def analyze(task):
        calls.append("analysis")
        entered.set()
        assert release.wait(3)
        return {"id": "a", "requirements": [requirement()]}

    callbacks = {
        "analysis": analyze,
        "resume": lambda task: (
            calls.append("resume") or {"id": "d", "kind": "draft", "draft_sha256": "a" * 64}
        ),
    }
    flow = ApplicationFlowService(
        applications, tmp_path / "flow", preparation_only=True, callbacks=callbacks
    )
    try:
        saved = flow.request(
            "batch-create",
            {
                "request_id": "4" * 32,
                "items": [{"kind": "application", "id": job["id"], "revision": job["revision"]}],
            },
        )
        flow.request(
            "batch-control",
            {"batch_id": saved["id"], "batch_revision": saved["revision"], "operation": "resume"},
        )
        assert entered.wait(2)
        saved = flow.snapshot()["preparation_batch"]
        flow.request(
            "batch-control",
            {"batch_id": saved["id"], "batch_revision": saved["revision"], "operation": "pause"},
        )
        release.set()
        task = flow.snapshot()["active_task"]
        wait_for(flow, task["id"], lambda t: t["status"] == "analysis_ready")
        saved = flow.snapshot()["preparation_batch"]
        assert saved["control"] == "paused" and calls == ["analysis"]
        assert flow.snapshot()["preparation_batch"] == saved
    finally:
        release.set()
        flow.close()
    reopened = ApplicationFlowService(
        applications, tmp_path / "flow", preparation_only=True, callbacks=callbacks
    )
    try:
        saved = reopened.snapshot()["preparation_batch"]
        assert saved["control"] == "paused" and calls == ["analysis"]
        reopened.request(
            "batch-control",
            {"batch_id": saved["id"], "batch_revision": saved["revision"], "operation": "resume"},
        )
        batch_until(reopened, lambda b: b["items"][0]["status"] == "waiting_draft_review")
        assert calls == ["analysis", "resume"]
    finally:
        reopened.close()


@pytest.mark.parametrize("selection", ["empty", "too_many", "bad_kind", "conflicting_duplicate"])
def test_batch_selection_rejects_unbounded_or_conflicting_requests(
    application, tmp_path, selection
):
    applications, job = application
    selected = {"kind": "application", "id": job["id"], "revision": job["revision"]}
    items = {
        "empty": [],
        "too_many": [selected] * 101,
        "bad_kind": [selected | {"kind": []}],
        "conflicting_duplicate": [selected, selected | {"revision": "wrong-version"}],
    }[selection]
    flow = ApplicationFlowService(applications, tmp_path / "flow", preparation_only=True)
    try:
        with pytest.raises(PortalDataError):
            flow.request("batch-create", {"request_id": "5" * 32, "items": items})
        assert flow.snapshot()["preparation_batch"] is None
        assert flow.snapshot()["tasks"] == []
    finally:
        flow.close()


def test_saved_selection_never_silently_changes_to_a_new_application_revision(
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
    try:
        saved = flow.request(
            "batch-create",
            {
                "request_id": "6" * 32,
                "items": [{"kind": "application", "id": job["id"], "revision": job["revision"]}],
            },
        )
        applications.update_application(
            job["id"], {"job_description": "Changed complete Python JD."}, job["revision"]
        )
        flow.request(
            "batch-control",
            {"batch_id": saved["id"], "batch_revision": saved["revision"], "operation": "resume"},
        )
        saved = batch_until(flow, lambda b: b["reason"] == "no_processable_items")
        assert saved["items"][0]["status"] == "deferred"
        assert saved["items"][0]["reason"] == "conflict"
        assert flow.snapshot()["tasks"] == [] and calls == []
    finally:
        flow.close()


def test_pause_before_stage_admission_keeps_one_attempt_and_resume_runs_it_once(
    application, tmp_path, monkeypatch
):
    import threading

    from test_job_explanations import requirement

    applications, job = application
    waiting, release = threading.Event(), threading.Event()
    calls = []
    flow = ApplicationFlowService(
        applications,
        tmp_path / "flow",
        preparation_only=True,
        callbacks={
            "analysis": lambda task: (
                calls.append("analysis") or {"id": "a", "requirements": [requirement()]}
            ),
            "resume": lambda task: (
                calls.append("resume") or {"id": "d", "kind": "draft", "draft_sha256": "a" * 64}
            ),
        },
    )
    original_get = flow._queue.get

    def controlled_get(*args, **kwargs):
        item = original_get(*args, **kwargs)
        if item and item[1] == "analysis" and not waiting.is_set():
            waiting.set()
            assert release.wait(3)
        return item

    monkeypatch.setattr(flow._queue, "get", controlled_get)
    try:
        saved = flow.request(
            "batch-create",
            {
                "request_id": "7" * 32,
                "items": [{"kind": "application", "id": job["id"], "revision": job["revision"]}],
            },
        )
        flow.request(
            "batch-control",
            {"batch_id": saved["id"], "batch_revision": saved["revision"], "operation": "resume"},
        )
        assert waiting.wait(2)
        current = flow.snapshot()
        attempt = current["active_task"]["stages"]["analysis"]["attempt_id"]
        saved = current["preparation_batch"]
        saved = flow.request(
            "batch-control",
            {"batch_id": saved["id"], "batch_revision": saved["revision"], "operation": "pause"},
        )
        release.set()
        assert calls == []
        assert flow.snapshot()["active_task"]["stages"]["analysis"]["status"] == "queued"
        with applications.write_lock():
            running = flow.request(
                "batch-control",
                {
                    "batch_id": saved["id"],
                    "batch_revision": saved["revision"],
                    "operation": "resume",
                },
            )
            flow.request(
                "batch-control",
                {
                    "batch_id": running["id"],
                    "batch_revision": running["revision"],
                    "operation": "resume",
                },
            )
        batch_until(flow, lambda b: b["items"][0]["status"] == "waiting_draft_review")
        assert calls == ["analysis", "resume"]
        assert flow.snapshot()["active_task"]["stages"]["analysis"]["attempt_id"] == attempt
    finally:
        release.set()
        flow.close()


def test_completed_unknown_export_keeps_exact_proof_and_blocks_reexport(reviewed_draft):
    flow, task, calls = reviewed_draft
    application = flow.applications.get_application(task["application_id"])
    original = flow.callbacks["export"]
    receipts, reads, attempts = {}, [], []

    def unknown(task):
        result = original(task)
        receipts[result["id"]] = result
        raise PortalDataError("resume_export_needs_recheck", "Synthetic unknown publication.", 409)

    def reconcile(task):
        attempt = task["stages"]["export"]["attempt_id"]
        reads.append(attempt)
        return receipts[attempt]

    flow.callbacks.update(export=unknown, reconcile_export=reconcile)
    batch = flow.request(
        "batch-create",
        {
            "request_id": "8" * 32,
            "items": [
                {
                    "kind": "application",
                    "id": application["id"],
                    "revision": application["revision"],
                }
            ],
        },
    )
    flow.request(
        "batch-control",
        {"batch_id": batch["id"], "batch_revision": batch["revision"], "operation": "resume"},
    )
    batch_until(flow, lambda b: b["items"][0]["status"] == "waiting_draft_review")
    task = flow.snapshot()["active_task"]
    flow.review_draft(task["id"], task["revision"], task["draft_id"], task["draft_sha256"])
    batch = batch_until(flow, lambda b: b["control"] == "needs_recheck")
    task = flow.snapshot()["active_task"]
    attempts.append(task["stages"]["export"]["attempt_id"])
    flow.recheck_export(task["id"], task["revision"])
    batch = flow.snapshot()["preparation_batch"]
    assert batch["control"] == "paused"
    assert batch["items"][0]["status"] == "waiting_application_record"
    assert calls == ["generate", "export"]
    with pytest.raises(PortalDataError) as stopped:
        flow.request(
            "batch-control",
            {
                "batch_id": batch["id"],
                "batch_revision": batch["revision"],
                "operation": "resume",
            },
        )
    assert stopped.value.code == "flow_batch_application_record_required"
    task = flow.snapshot()["active_task"]
    with pytest.raises(PortalDataError):
        flow.export_pdf(
            task["id"], task["revision"], task["draft_id"], task["draft_sha256"], retry=True
        )
    assert len(set(attempts)) == 1 and reads == attempts
    history = batch["items"][0]["export_recheck_history"]
    assert [row["binding"]["attempt_id"] for row in history] == attempts
    assert [row["proof"]["attempt_id"] for row in history] == attempts
    assert all(row["proof"]["status"] == "complete" for row in history)


@pytest.mark.parametrize("endpoint", ["confirmed", "needs_recheck"])
@pytest.mark.parametrize("control_drift", [False, True])
def test_batch_endpoint_is_unchanged_across_reads_close_and_cold_reopen(
    reviewed_draft, endpoint, control_drift
):
    from test_application_flow import wait_for

    flow, task, calls = reviewed_draft
    if endpoint == "needs_recheck":
        original_export = flow.callbacks["export"]

        def unknown(task):
            original_export(task)
            raise PortalDataError("resume_export_needs_recheck", "Synthetic unknown export.", 409)

        flow.callbacks["export"] = unknown
    application = flow.applications.get_application(task["application_id"])
    batch = flow.request(
        "batch-create",
        {
            "request_id": "9" * 32,
            "items": [
                {
                    "kind": "application",
                    "id": application["id"],
                    "revision": application["revision"],
                }
            ],
        },
    )
    flow.request(
        "batch-control",
        {"batch_id": batch["id"], "batch_revision": batch["revision"], "operation": "resume"},
    )
    batch_until(flow, lambda b: b["items"][0]["status"] == "waiting_draft_review")
    task = flow.snapshot()["active_task"]
    flow.review_draft(task["id"], task["revision"], task["draft_id"], task["draft_sha256"])
    task = wait_for(
        flow,
        task["id"],
        lambda row: (
            row["status"] == ("materials_ready" if endpoint == "confirmed" else "needs_recheck")
        ),
    )
    if endpoint == "confirmed":
        flow.confirm_materials(
            task["id"], task["revision"], task["resume_id"], task["resume_sha256"]
        )
    saved = flow.snapshot()
    batch, task = saved["preparation_batch"], saved["active_task"]
    if endpoint == "confirmed":
        assert batch["control"] == "paused" and batch["reason"] == "waiting_application_record"
        disposition, task_status = "waiting_application_record", "materials_ready"
    else:
        assert (
            batch["control"] == "needs_recheck" and batch["reason"] == "flow_result_needs_recheck"
        )
        disposition = task_status = "needs_recheck"
    assert [event["action"] for event in batch["events"]].count(disposition) == 1
    assert task["status"] == task_status and calls == ["generate", "export"]
    original = flow.path.read_bytes()
    for _ in range(2):
        assert flow.snapshot()["preparation_batch"] == batch
        assert flow.snapshot()["active_task"] == task
        assert flow.path.read_bytes() == original
    if control_drift:
        import json

        from career_evidence_graph.application_worker import digest

        saved = json.loads(original)
        changed = saved["preparation_batch"]
        changed.update(control="running", reason="synthetic_control_drift")
        changed["revision"] = digest(
            {key: value for key, value in changed.items() if key != "revision"}
        )
        flow.path.write_text(json.dumps(saved))
    flow.close()
    if control_drift:
        restored = flow.snapshot()["preparation_batch"]
        assert restored["items"] == batch["items"]
        assert (restored["control"], restored["reason"]) == (batch["control"], batch["reason"])
        assert restored["events"][:-1] == batch["events"]
        assert restored["events"][-1]["action"] == disposition
        assert restored["epoch"] == batch["epoch"] + 2
        batch, original = restored, flow.path.read_bytes()
    assert flow.path.read_bytes() == original
    for _ in range(2):
        reopened = ApplicationFlowService(
            flow.applications, flow.root, preparation_only=True, callbacks=flow.callbacks
        )
        try:
            assert reopened.snapshot()["preparation_batch"] == batch
            assert reopened.snapshot()["active_task"] == task
            assert reopened.path.read_bytes() == original
            assert calls == ["generate", "export"]
        finally:
            reopened.close()
        assert flow.path.read_bytes() == original
