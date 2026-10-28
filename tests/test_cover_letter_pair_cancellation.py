"""Skipped pair checks retain uncertain effects without blocking on unstarted work."""

import threading

import pytest
from test_application_cover_letter_flow import material, service, wait_for

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


def test_skipping_unadmitted_pair_releases_next_job_without_running_old_check(tmp_path):
    flow, task = service(tmp_path, material)
    try:
        with flow.applications.write_lock():
            state = flow._load()
            current = flow._task(state, task["id"])
            current["material_consistency"] = {"status": "queued", "attempt_id": "c" * 32}
            flow._save(state)
        flow.cancel_cover_letter(task["id"])
        old = flow.task_snapshot(task["id"])
        assert old["material_consistency"]["status"] == "cancelled"
        assert old["material_consistency_history"][-1]["status"] == "queued"
        other = another_analysis(flow)
        flow.start(other["id"], other["revision"], "resume")
        wait_for(flow, other["id"], lambda row: row["cover_letter"]["status"] == "ready")
    finally:
        flow.close()


@pytest.mark.parametrize("unknown", [False, True])
def test_skipped_running_pair_retains_late_known_result_or_unknown_stop(tmp_path, unknown):
    entered, release = threading.Event(), threading.Event()

    def resume(task):
        return {
            "id": "resume-draft",
            "kind": "draft",
            "draft_sha256": "a" * 64,
            "content_revision": "c" * 64,
            "resume_content": {"revision": "c" * 64},
        }

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
        flow.start(task["id"], task["revision"], "resume")
        assert entered.wait(5)
        flow.cancel_cover_letter(task["id"])
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
            with pytest.raises(PortalDataError) as blocked:
                flow.start(other["id"], other["revision"], "resume")
            assert blocked.value.code == "letter_other_job_pending"
    finally:
        release.set()
        flow.close()


@pytest.mark.parametrize("entry", ["retained_letter", "retry_consistency"])
@pytest.mark.parametrize("branch", ["cover_letter", "material_consistency"])
@pytest.mark.parametrize("pending", ["queued", "running", "needs_recheck"])
def test_old_job_recovery_refuses_other_job_pending_before_any_mutation(
    tmp_path, entry, branch, pending
):
    from test_application_information import tree_bytes

    entered, release = threading.Event(), threading.Event()
    calls = []

    def letter(request):
        calls.append(request["id"])
        entered.set()
        assert release.wait(5)
        return material(request)

    flow, task = service(tmp_path, letter)
    try:
        flow.start(task["id"], task["revision"], "resume")
        assert entered.wait(5)
        flow.cancel_cover_letter(task["id"])
        release.set()
        wait_for(
            flow,
            task["id"],
            lambda row: (
                row["cover_letter"]["status"] == "cancelled" and row["status"] == "draft_ready"
            ),
        )
        other = another_analysis(flow)
        with flow.applications.write_lock():
            state = flow._load()
            old = flow._task(state, task["id"])
            old["manual_edits"] = {"letter": "Preserved human text"}
            if entry == "retry_consistency":
                retained = next(
                    row["result"] for row in old["artifacts"] if row.get("stage") == "cover_letter"
                )
                old["cover_letter"].update(status="ready", result=retained)
                old["material_consistency"] = {
                    "status": "cancelled",
                    "cancel_requested": True,
                    "pair_revision": "old-pair",
                    "attempt_id": "c" * 32,
                }
            flow._task(state, other["id"])[branch] = {"status": pending}
            flow._save(state)
        old = flow.task_snapshot(task["id"])
        before = tree_bytes(flow.root)
        before_calls = list(calls)
        with pytest.raises(PortalDataError) as rejected:
            if entry == "retained_letter":
                flow.start_cover_letter(task["id"], old["revision"], retry=True)
            else:
                flow.retry_material_consistency(task["id"], old["revision"])
        assert rejected.value.code == "letter_other_job_pending"
        assert tree_bytes(flow.root) == before
        assert calls == before_calls
        assert flow.task_snapshot(task["id"]) == old
    finally:
        release.set()
        flow.close()


@pytest.mark.parametrize("entry", ["retained_letter", "retry_consistency"])
def test_old_job_recovery_preserves_receipts_while_new_author_really_runs(tmp_path, entry):
    from test_application_information import tree_bytes

    entered, release = threading.Event(), threading.Event()
    calls, checks = [], []

    def letter(request):
        calls.append(request["id"])
        entered.set()
        assert release.wait(5)
        return material(request)

    def resume(request):
        return {
            "id": "resume-draft",
            "kind": "draft",
            "draft_sha256": "a" * 64,
            "content_revision": "c" * 64,
            "resume_content": {"revision": "c" * 64},
        }

    def check(request):
        checks.append(request["id"])
        return {
            "status": "passed",
            **{
                key: request["material_consistency"][key]
                for key in ("resume_content_revision", "letter_content_revision")
            },
        }

    flow, task = service(tmp_path, letter, resume)
    flow.callbacks["material_consistency"] = check
    try:
        flow.start(task["id"], task["revision"], "resume")
        assert entered.wait(5)
        flow.cancel_cover_letter(task["id"])
        release.set()
        wait_for(
            flow,
            task["id"],
            lambda row: (
                row["cover_letter"]["status"] == "cancelled" and row["status"] == "draft_ready"
            ),
        )
        other = another_analysis(flow)
        if entry == "retry_consistency":
            with flow.applications.write_lock():
                state = flow._load()
                old = flow._task(state, task["id"])
                retained = next(
                    row["result"] for row in old["artifacts"] if row.get("stage") == "cover_letter"
                )
                old["cover_letter"].update(status="ready", result=retained)
                old["material_consistency"] = {
                    "status": "failed",
                    "error_code": "material_consistency_not_started",
                    "pair_revision": "stale",
                }
                flow._save(state)
        entered.clear()
        release.clear()
        flow.start(other["id"], other["revision"], "resume")
        assert entered.wait(5)
        wait_for(
            flow,
            other["id"],
            lambda row: (
                row["cover_letter"]["status"] == "running" and row["status"] == "draft_ready"
            ),
        )
        old = flow.task_snapshot(task["id"])
        before = tree_bytes(flow.root)
        with pytest.raises(PortalDataError) as rejected:
            if entry == "retained_letter":
                flow.start_cover_letter(task["id"], old["revision"], retry=True)
            else:
                flow.retry_material_consistency(task["id"], old["revision"])
        assert rejected.value.code == "letter_other_job_pending"
        assert tree_bytes(flow.root) == before
        assert calls == [task["id"], other["id"]]
        assert checks == []
        flow.cancel_cover_letter(other["id"])
        release.set()
        wait_for(flow, other["id"], lambda row: row["cover_letter"]["status"] == "cancelled")
        if entry == "retained_letter":
            flow.start_cover_letter(task["id"], old["revision"], retry=True)
        else:
            flow.retry_material_consistency(task["id"], old["revision"])
        wait_for(flow, task["id"], lambda row: row["material_consistency"]["status"] == "passed")
        assert calls == [task["id"], other["id"]]
        assert checks == [task["id"]]
    finally:
        release.set()
        flow.close()
