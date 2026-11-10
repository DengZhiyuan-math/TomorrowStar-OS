"""Cancelled pair checks retain uncertain effects; another job's open letter blocks recovery."""

import threading

import pytest
from test_application_cover_letter_flow import material, resume_then_letter, service, wait_for

from career_evidence_graph.career_portal_data import PortalDataError


def another_analysis(flow):
    application = flow.applications.create_application(
        {
            "company": "Another Synthetic Employer",
            "role_title": "Engineer",
            "job_description": "Build reliable Python systems.",
        }
    )
    flow.callbacks["analysis"] = lambda request: {
        "id": "second-analysis",
        "application_id": request["application_id"],
        "job_brief": {"requirements": []},
        "material_packet": {"sources": {}},
        "inference_result": {},
    }
    task = flow.create(application["id"], application["revision"])
    flow.start(task["id"], task["revision"], "analysis")
    return wait_for(flow, task["id"], lambda row: row["status"] == "analysis_ready")


def resume(request):
    return {
        "id": "resume-draft",
        "kind": "draft",
        "draft_sha256": "a" * 64,
        "content_revision": "c" * 64,
        "resume_content": {"revision": "c" * 64},
    }


def test_unadmitted_pair_of_an_earlier_job_does_not_block_the_next_letter(tmp_path):
    flow, task = service(tmp_path, material)
    try:
        with flow.applications.write_lock():
            state = flow._load()
            current = flow._task(state, task["id"])
            current["material_consistency"] = {"status": "cancelled", "attempt_id": "c" * 32}
            flow._save(state)
        other = another_analysis(flow)
        resume_then_letter(flow, other)
        wait_for(flow, other["id"], lambda row: row["stages"]["letter"]["status"] == "complete")
    finally:
        flow.close()


@pytest.mark.parametrize("unknown", [False, True])
def test_cancelled_running_pair_retains_late_known_result_or_unknown_stop(tmp_path, unknown):
    entered, release = threading.Event(), threading.Event()

    def check(request):
        entered.set()
        assert release.wait(5)
        if unknown:
            raise TimeoutError("synthetic lost pair response")
        return {
            "status": "passed",
            **{
                key: request["material_consistency"][key]
                for key in ("resume_content_revision", "letter_content_revision")
            },
        }

    flow, task = service(tmp_path, material, resume)
    flow.callbacks["material_consistency"] = check
    try:
        resume_then_letter(flow, task)
        assert entered.wait(5)
        flow.cancel_preparation(task["id"], flow.task_snapshot(task["id"])["revision"])
        assert flow.task_snapshot(task["id"])["material_consistency"]["status"] == "running"
        release.set()
        done = wait_for(
            flow,
            task["id"],
            lambda row: (
                row["material_consistency"]["status"]
                == ("needs_recheck" if unknown else "cancelled")
            ),
        )
        assert "result" not in done["material_consistency"]
        if not unknown:
            assert done["material_consistency_history"][-1]["adopted"] is False
        else:
            other = another_analysis(flow)
            flow.start(other["id"], other["revision"], "resume")
            drafted = wait_for(flow, other["id"], lambda row: row["status"] == "draft_ready")
            with pytest.raises(PortalDataError) as blocked:
                flow.start(other["id"], drafted["revision"], "letter")
            assert blocked.value.code == "letter_other_job_pending"
    finally:
        release.set()
        flow.close()


def old_job(tmp_path, entry, letter_calls, **callbacks):
    """An earlier job whose letter failed, or whose pair check needs a retry."""

    def letter(request):
        letter_calls.append(request["id"])
        if entry == "letter_retry" and len(letter_calls) == 1:
            raise PortalDataError("letter_generation_failed", "Synthetic rejection", 409)
        hold = callbacks.get("hold")
        if hold and len(letter_calls) == 2:
            hold()
        return material(request)

    flow, task = service(tmp_path, letter, resume)
    if "check" in callbacks:
        flow.callbacks["material_consistency"] = callbacks["check"]
    resume_then_letter(flow, task)
    wait_for(
        flow,
        task["id"],
        lambda row: (
            row["stages"]["letter"]["status"] in {"failed", "complete"}
            and row.get("material_consistency", {}).get("status") not in {"queued", "running"}
        ),
    )
    if entry == "retry_consistency":
        with flow.applications.write_lock():
            state = flow._load()
            flow._task(state, task["id"])["material_consistency"] = {
                "status": "failed",
                "error_code": "material_consistency_not_started",
                "pair_revision": "stale",
                "attempt_id": "c" * 32,
            }
            flow._save(state)
    return flow, task


def recover(flow, task, entry, revision):
    if entry == "letter_retry":
        return flow.start(task["id"], revision, "letter", retry=True)
    return flow.retry_material_consistency(task["id"], revision)


@pytest.mark.parametrize("entry", ["letter_retry", "retry_consistency"])
@pytest.mark.parametrize("branch", ["letter", "material_consistency"])
@pytest.mark.parametrize("pending", ["queued", "running", "needs_recheck"])
def test_old_job_recovery_refuses_other_job_pending_before_any_mutation(
    tmp_path, entry, branch, pending
):
    from test_application_information import tree_bytes

    calls = []
    flow, task = old_job(tmp_path, entry, calls)
    try:
        other = another_analysis(flow)
        with flow.applications.write_lock():
            state = flow._load()
            old = flow._task(state, task["id"])
            old["manual_edits"] = {"letter": "Preserved human text"}
            row = flow._task(state, other["id"])
            if branch == "letter":
                row["stages"]["letter"] = {"status": pending}
            else:
                row["material_consistency"] = {"status": pending}
            flow._save(state)
        old = flow.task_snapshot(task["id"])
        before = tree_bytes(flow.root)
        before_calls = list(calls)
        with pytest.raises(PortalDataError) as rejected:
            recover(flow, task, entry, old["revision"])
        assert rejected.value.code == "letter_other_job_pending"
        assert tree_bytes(flow.root) == before
        assert calls == before_calls
        assert flow.task_snapshot(task["id"]) == old
    finally:
        flow.close()


@pytest.mark.parametrize("entry", ["letter_retry", "retry_consistency"])
def test_old_job_recovery_preserves_receipts_while_new_author_really_runs(tmp_path, entry):
    from test_application_information import tree_bytes

    entered, release = threading.Event(), threading.Event()
    calls, checks = [], []

    def hold():
        entered.set()
        assert release.wait(5)

    def check(request):
        checks.append(request["id"])
        return {
            "status": "passed",
            **{
                key: request["material_consistency"][key]
                for key in ("resume_content_revision", "letter_content_revision")
            },
        }

    flow, task = old_job(tmp_path, entry, calls, hold=hold, check=check)
    try:
        checks.clear()
        other = another_analysis(flow)
        resume_then_letter(flow, other)
        assert entered.wait(5)
        old = flow.task_snapshot(task["id"])
        before = tree_bytes(flow.root)
        with pytest.raises(PortalDataError) as rejected:
            recover(flow, task, entry, old["revision"])
        assert rejected.value.code == "letter_other_job_pending"
        assert tree_bytes(flow.root) == before
        assert calls == [task["id"], other["id"]]
        assert checks == []
        release.set()
        wait_for(
            flow,
            other["id"],
            lambda row: row.get("material_consistency", {}).get("status") == "passed",
        )
        recover(flow, task, entry, flow.task_snapshot(task["id"])["revision"])
        wait_for(
            flow,
            task["id"],
            lambda row: row.get("material_consistency", {}).get("status") == "passed",
        )
        if entry == "letter_retry":
            assert calls == [task["id"], other["id"], task["id"]]
        else:
            assert calls == [task["id"], other["id"]]
        assert checks == [other["id"], task["id"]]
    finally:
        release.set()
        flow.close()
