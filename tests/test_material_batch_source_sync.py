"""Synced preparation inputs resume the same reviewed-base task explicitly."""

import json

import pytest
from test_application_flow import application as application
from test_application_flow import wait_for
from test_full_latex_flow import bind, candidate
from test_job_explanations import requirement
from test_material_batch import batch_until

from career_evidence_graph.application_flow import ApplicationFlowService
from career_evidence_graph.application_prism import digest, source_snapshot
from career_evidence_graph.career_portal_data import PortalDataError


def control(flow, operation):
    batch = flow.snapshot()["preparation_batch"]
    return flow.request(
        "batch-control",
        {"batch_id": batch["id"], "batch_revision": batch["revision"], "operation": operation},
    )


def retry(flow):
    batch = flow.snapshot()["preparation_batch"]
    return flow.request(
        "batch-retry",
        {
            "batch_id": batch["id"],
            "batch_revision": batch["revision"],
            "item_id": batch["items"][0]["item_id"],
        },
    )


@pytest.fixture
def synced_job(application, tmp_path):
    applications, job = application
    identity = {"application_revision": job["revision"], "inputs": {"sources_revision": "A"}}
    calls = []

    def analyze(task):
        calls.append(("analysis", task["inputs"]["sources_revision"]))
        return {"id": f"analysis-{len(calls)}", "requirements": [requirement()]}

    def generate(task):
        calls.append(("resume", task["inputs"]["sources_revision"]))
        if task["inputs"]["sources_revision"] == "A":
            raise PortalDataError("resume_material_insufficient", "Synthetic known failure.")
        return candidate(task)

    options = {
        "preparation_only": True,
        "input_provider": lambda _: identity,
        "callbacks": {
            "analysis": analyze,
            "resume": generate,
            "prism_source": source_snapshot,
            "export": lambda _: pytest.fail("Group review must precede export"),
        },
    }
    root = tmp_path / "flow"
    flow = ApplicationFlowService(applications, root, **options)
    project = tmp_path / "base"
    project.mkdir()
    (project / "main.tex").write_text(r"\documentclass{article}\begin{document}Fact\end{document}")
    try:
        task = flow.create(job["id"], job["revision"])
        flow.start(task["id"], task["revision"], "analysis")
        task = wait_for(flow, task["id"], lambda row: row["status"] == "analysis_ready")
        task = bind(flow, task, project)
        flow.request(
            "batch-create",
            {
                "request_id": "a" * 32,
                "items": [{"kind": "application", "id": job["id"], "revision": job["revision"]}],
            },
        )
        control(flow, "resume")
        batch_until(flow, lambda row: row["control"] == "paused")
        failed = flow.snapshot()["active_task"]
        assert failed["status"] == "failed"
        assert calls == [("analysis", "A"), ("resume", "A")]
        yield flow, job, identity, calls, options, failed
    finally:
        flow.close()


def test_source_sync_retries_same_task_and_base_then_waits_for_group_review(synced_job):
    flow, job, identity, calls, _, failed = synced_job
    identity["inputs"] = {"sources_revision": "B"}
    synced = flow.update_inputs(failed["id"], failed["revision"], job["revision"])
    assert synced["analysis_id"] is None
    assert synced["stages"]["analysis"]["status"] == "pending"
    assert synced["artifacts"] == failed["artifacts"]
    assert calls == [("analysis", "A"), ("resume", "A")]
    retry(flow)
    assert calls == [("analysis", "A"), ("resume", "A")]
    control(flow, "resume")
    batch = batch_until(
        flow,
        lambda row: (
            row["items"][0]["status"] == "waiting_draft_review" or row["control"] == "paused"
        ),
    )
    assert batch["items"][0]["status"] == "waiting_draft_review"
    task = flow.snapshot()["active_task"]
    assert task["id"] == failed["id"]
    assert task["latex_base"] == failed["latex_base"]
    assert task["input_epoch"] == failed["input_epoch"] + 1
    assert task["artifacts"][: len(failed["artifacts"])] == failed["artifacts"]
    assert len(flow.snapshot()["tasks"]) == 1
    assert calls == [("analysis", "A"), ("resume", "A"), ("analysis", "B"), ("resume", "B")]
    assert task["origin"] == "generated_latex" and task["factual_review"] == "pending"
    assert task["stages"]["export"]["status"] == "pending"
    assert task["materials_confirmed"] is False and task["worker_ref"] is None


def test_sync_of_active_old_epoch_requires_retry_and_preserves_binding_history(synced_job):
    flow, job, identity, calls, _, failed = synced_job
    identity["inputs"] = {"sources_revision": "B"}
    flow.update_inputs(failed["id"], failed["revision"], job["revision"])
    retry(flow)
    control(flow, "resume")
    old = batch_until(flow, lambda row: row["items"][0]["status"] == "waiting_draft_review")
    task = flow.snapshot()["active_task"]
    identity["inputs"] = {"sources_revision": "C"}
    task = flow.update_inputs(task["id"], task["revision"], job["revision"])
    saved = batch_until(flow, lambda row: row["control"] == "paused")
    assert saved["items"][0]["status"] == "stale"
    # A queued background freshness check can observe C before update_inputs runs.
    # Both paths must pause the old epoch; the binding/retry assertions below still apply.
    assert saved["items"][0]["reason"] in {"flow_inputs_changed", "flow_inputs_stale"}
    assert calls[-1] == ("resume", "B")
    retried = retry(flow)
    assert retried["items"][0]["binding_history"][:-1] == old["items"][0]["binding_history"]
    assert (
        retried["items"][0]["binding_history"][-1]["task_input_epoch"]
        == old["items"][0]["task_input_epoch"]
    )
    assert retried["items"][0]["force_new"] is False
    control(flow, "resume")
    ready = batch_until(flow, lambda row: row["items"][0]["status"] == "waiting_draft_review")
    assert ready["items"][0]["task_id"] == task["id"]
    assert ready["items"][0]["task_input_epoch"] == task["input_epoch"]
    assert flow.snapshot()["active_task"]["latex_base"] == failed["latex_base"]
    assert calls[-2:] == [("analysis", "C"), ("resume", "C")]


@pytest.mark.parametrize("invalid", ["other-job", "unknown-group-read"])
def test_recovery_rejects_wrong_binding_or_unknown_group_read_without_writes(synced_job, invalid):
    flow, job, identity, calls, options, failed = synced_job
    identity["inputs"] = {"sources_revision": "B"}
    flow.update_inputs(failed["id"], failed["revision"], job["revision"])
    flow.close()
    saved = json.loads(flow.path.read_text())
    task = saved["tasks"][-1]
    if invalid == "other-job":
        other = flow.applications.create_application(
            {"company": "Other Synthetic", "role_title": "Engineer", "job_description": "Python."}
        )
        task["application_id"] = other["id"]
    else:
        task["group_read"] = {"status": "needs_recheck"}
    task["revision"] = digest({key: value for key, value in task.items() if key != "revision"})
    flow.path.write_text(json.dumps(saved))
    reopened = ApplicationFlowService(flow.applications, flow.root, **options)
    try:
        preserved = flow.path.read_bytes()
        with pytest.raises(PortalDataError) as error:
            retry(reopened)
        assert error.value.code == (
            "flow_batch_task_mismatch" if invalid == "other-job" else "flow_group_recheck_required"
        )
        assert flow.path.read_bytes() == preserved
        assert calls == [("analysis", "A"), ("resume", "A")]
    finally:
        reopened.close()


@pytest.mark.parametrize("entry", ["update-inputs", "batch-retry"])
def test_legacy_synced_stale_survives_reopen_until_explicit_recovery(synced_job, entry):
    flow, job, identity, calls, options, failed = synced_job
    identity["inputs"] = {"sources_revision": "B"}
    synced = flow.update_inputs(failed["id"], failed["revision"], job["revision"])
    flow.close()
    # Replay the previous installed format; this is a synthetic migration fixture.
    saved = json.loads(flow.path.read_text())
    task = saved["tasks"][-1]
    task["status"] = "stale"
    task["revision"] = digest({key: value for key, value in task.items() if key != "revision"})
    flow.path.write_text(json.dumps(saved))
    preserved = flow.path.read_bytes()
    reopened = ApplicationFlowService(flow.applications, flow.root, **options)
    try:
        current = reopened.snapshot()["active_task"]
        assert current["status"] == "stale" and calls == [("analysis", "A"), ("resume", "A")]
        assert flow.path.read_bytes() == preserved
        if entry == "update-inputs":
            current = reopened.update_inputs(current["id"], current["revision"], job["revision"])
            assert current["status"] == "draft"
        retry(reopened)
        current = reopened.snapshot()["active_task"]
        assert current["status"] == "draft"
        assert current["id"] == synced["id"] and current["input_epoch"] == synced["input_epoch"]
        assert current["latex_base"] == failed["latex_base"]
        assert current["artifacts"] == failed["artifacts"]
        assert reopened.snapshot()["preparation_batch"]["control"] == "paused"
        assert calls == [("analysis", "A"), ("resume", "A")]
        unchanged = reopened.update_inputs(current["id"], current["revision"], job["revision"])
        assert unchanged == current
        control(reopened, "resume")
        batch = batch_until(
            reopened, lambda row: row["items"][0]["status"] == "waiting_draft_review"
        )
        assert batch["items"][0]["task_id"] == current["id"]
        assert len(reopened.snapshot()["tasks"]) == 1
        assert calls[-2:] == [("analysis", "B"), ("resume", "B")]
    finally:
        reopened.close()


@pytest.mark.parametrize("drift", ["sources", "newer-task"])
def test_retry_does_not_rearm_inputs_that_are_no_longer_current(synced_job, drift):
    flow, job, identity, calls, _, failed = synced_job
    identity["inputs"] = {"sources_revision": "B"}
    synced = flow.update_inputs(failed["id"], failed["revision"], job["revision"])
    if drift == "sources":
        identity["inputs"] = {"sources_revision": "C"}
    else:
        flow.create(job["id"], job["revision"], force_new=True)
    preserved = flow.path.read_bytes()
    with pytest.raises(PortalDataError) as error:
        retry(flow)
    assert error.value.code == "flow_inputs_stale"
    assert flow.path.read_bytes() == preserved
    assert flow.snapshot(synced["id"])["active_task"] == synced
    assert calls == [("analysis", "A"), ("resume", "A")]


@pytest.mark.parametrize("stage", ["analysis", "resume"])
def test_resumed_stage_failure_stays_explicit_and_does_not_repeat(synced_job, stage):
    flow, job, identity, calls, _, failed = synced_job
    identity["inputs"] = {"sources_revision": "B"}
    flow.update_inputs(failed["id"], failed["revision"], job["revision"])

    def fail(task):
        calls.append((stage, task["inputs"]["sources_revision"]))
        raise PortalDataError("synthetic_known_failure", "Stop without a retry.")

    flow.callbacks[stage] = fail
    retry(flow)
    control(flow, "resume")
    batch = batch_until(flow, lambda row: row["control"] == "paused")
    assert batch["items"][0]["status"] == "deferred"
    assert batch["items"][0]["reason"] == "synthetic_known_failure"
    task = flow.snapshot()["active_task"]
    assert task["id"] == failed["id"] and task["latex_base"] == failed["latex_base"]
    assert calls[2:] == (
        [("analysis", "B")] if stage == "analysis" else [("analysis", "B"), ("resume", "B")]
    )
    assert task["stages"][stage]["status"] == "failed"
    assert task["stages"]["export"]["status"] == "pending"
