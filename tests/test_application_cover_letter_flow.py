"""Independent authors share fixed inputs and retain separately adopted results."""

import hashlib
import threading
import time

import pytest

from career_evidence_graph.application_flow import ApplicationFlowService
from career_evidence_graph.career_portal_data import ApplicationStore, PortalDataError
from career_evidence_graph.validation.hashing import record_digest as digest


def wait_for(flow, task_id, predicate):
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        task = flow.task_snapshot(task_id)
        if predicate(task):
            return task
        time.sleep(0.01)
    pytest.fail("cover-letter branch did not reach its expected state")


def material(task):
    branch = task["cover_letter"]
    content = {
        "schema_version": "cover-letter-content/v1",
        "application_id": task["application_id"],
        "job_revision": "a" * 64,
        "inputs_revision": branch["fixed_inputs_revision"],
        "language": "English",
        "paragraphs": [
            {
                "id": "paragraph-1",
                "kind": "motivation",
                "text": "Synthetic body.",
                "source_ids": [],
                "source_quotes": [],
                "origin": "ai",
                "protected": False,
            }
        ],
    }
    content["revision"] = digest(content)
    return {
        "id": branch["attempt_id"],
        "attempt_id": branch["attempt_id"],
        "kind": "cover_letter",
        "status": "ready",
        "content_revision": content["revision"],
        "content": content,
        "text": "Synthetic body.",
        "text_sha256": hashlib.sha256(b"Synthetic body.").hexdigest(),
    }


def service(tmp_path, letter, resume=None, *, reader=None):
    (tmp_path / "applications").mkdir()
    applications = ApplicationStore(tmp_path / "applications")
    application = applications.create_application(
        {
            "company": "Synthetic Employer",
            "role_title": "Engineer",
            "job_description": "Build reliable Python systems.",
        }
    )
    callbacks = {
        "analysis": lambda task: {
            "id": "fixed-analysis",
            "application_id": application["id"],
            "job_brief": {"requirements": []},
            "material_packet": {"sources": {}},
            "inference_result": {},
        },
        "resume": resume
        or (lambda task: {"id": "resume-draft", "kind": "draft", "draft_sha256": "a" * 64}),
        "cover_letter": letter,
    }
    if reader:
        callbacks["cover_letter_result"] = reader
    flow = ApplicationFlowService(
        applications, tmp_path / "flow", preparation_only=True, callbacks=callbacks
    )
    task = flow.create(application["id"], application["revision"])
    flow.start(task["id"], task["revision"], "analysis")
    task = wait_for(flow, task["id"], lambda row: row["status"] == "analysis_ready")
    return flow, task


def test_two_authors_really_overlap_outside_store_lock(tmp_path):
    entered = threading.Barrier(3)
    release = threading.Event()
    requests = {}

    def letter(task):
        requests["letter"] = task
        entered.wait(timeout=5)
        assert release.wait(5)
        return material(task)

    def resume(task):
        requests["resume"] = task
        entered.wait(timeout=5)
        assert release.wait(5)
        return {"id": "resume-draft", "kind": "draft", "draft_sha256": "a" * 64}

    flow, task = service(tmp_path, letter, resume)
    try:
        flow.start(task["id"], task["revision"], "resume")
        entered.wait(timeout=5)
        # Both callbacks are held; the snapshot lock is still available.
        running = flow.task_snapshot(task["id"])
        assert running["cover_letter"]["status"] == "running"
        assert requests["letter"]["analysis_id"] == requests["resume"]["analysis_id"]
        assert (
            requests["letter"]["cover_letter"]["fixed_inputs_revision"]
            == requests["resume"]["cover_letter"]["fixed_inputs_revision"]
        )
        release.set()
        done = wait_for(
            flow,
            task["id"],
            lambda row: row["status"] == "draft_ready" and row["cover_letter"]["status"] == "ready",
        )
        assert done["draft_id"] == "resume-draft"
        assert {row["stage"] for row in done["artifacts"] if row["adopted"]} == {
            "analysis",
            "resume",
            "cover_letter",
        }
    finally:
        release.set()
        flow.close()


def test_optional_letter_failure_keeps_resume_and_retry_only_calls_letter(tmp_path):
    calls = []

    def letter(task):
        calls.append("letter")
        if calls.count("letter") == 1:
            raise PortalDataError("letter_generation_failed", "Synthetic rejection", 409)
        return material(task)

    def resume(task):
        calls.append("resume")
        return {"id": "resume-draft", "kind": "draft", "draft_sha256": "a" * 64}

    flow, task = service(tmp_path, letter, resume)
    try:
        flow.start(task["id"], task["revision"], "resume")
        failed = wait_for(
            flow,
            task["id"],
            lambda row: (
                row["status"] == "draft_ready" and row["cover_letter"]["status"] == "failed"
            ),
        )
        prior_resume = [row for row in failed["artifacts"] if row["stage"] == "resume"]
        flow.request(
            "start-cover-letter",
            {"task_id": task["id"], "task_revision": failed["revision"], "retry": True},
        )
        done = wait_for(flow, task["id"], lambda row: row["cover_letter"]["status"] == "ready")
        assert calls.count("resume") == 1
        assert calls.count("letter") == 2
        assert [row for row in done["artifacts"] if row["stage"] == "resume"] == prior_resume
        before = list(calls)
        flow.start_cover_letter(task["id"], done["revision"], retry=True)
        assert calls == before
    finally:
        flow.close()


def test_unknown_letter_requires_exact_local_reconciliation_without_replay(tmp_path):
    calls = []
    receipts = {}

    def letter(task):
        calls.append(task["cover_letter"]["attempt_id"])
        receipts.update(task=task)
        raise TimeoutError("response lost")

    flow, task = service(tmp_path, letter, reader=lambda task: material(receipts["task"]))
    try:
        flow.start(task["id"], task["revision"], "resume")
        unknown = wait_for(
            flow,
            task["id"],
            lambda row: (
                row["cover_letter"]["status"] == "needs_recheck" and row["status"] == "draft_ready"
            ),
        )
        reconciled = flow.recheck_cover_letter(task["id"], unknown["revision"])
        assert reconciled["cover_letter"]["status"] == "ready"
        assert len(calls) == 1
        assert reconciled["draft_id"] == "resume-draft"
    finally:
        flow.close()


def test_explicit_retry_runs_an_unknown_letter_again_and_keeps_its_history(tmp_path):
    calls = []

    def letter(task):
        calls.append(task["cover_letter"]["attempt_id"])
        if len(calls) == 1:
            raise TimeoutError("response lost")
        return material(task)

    flow, task = service(tmp_path, letter)
    try:
        flow.start(task["id"], task["revision"], "resume")
        unknown = wait_for(
            flow, task["id"], lambda row: row["cover_letter"]["status"] == "needs_recheck"
        )
        with pytest.raises(PortalDataError, match="未知"):
            flow.start_cover_letter(task["id"], unknown["revision"])
        # Approved 2026-10-31: writing only drafts text, so the user's retry may re-run it.
        flow.start_cover_letter(task["id"], unknown["revision"], retry=True)
        done = wait_for(flow, task["id"], lambda row: row["cover_letter"]["status"] == "ready")
        assert len(calls) == 2
        assert done["cover_letter_history"][-1]["status"] == "needs_recheck"
    finally:
        flow.close()


def test_skip_retains_late_letter_without_adopting_it(tmp_path):
    entered, release = threading.Event(), threading.Event()

    def letter(task):
        entered.set()
        assert release.wait(5)
        return material(task)

    flow, task = service(tmp_path, letter)
    try:
        flow.start(task["id"], task["revision"], "resume")
        assert entered.wait(5)
        flow.cancel_cover_letter(task["id"])
        release.set()
        done = wait_for(flow, task["id"], lambda row: row["cover_letter"]["status"] == "cancelled")
        letters = [row for row in done["artifacts"] if row["stage"] == "cover_letter"]
        assert len(letters) == 1
        assert letters[0]["adopted"] is False
        assert "result" not in done["cover_letter"]
    finally:
        release.set()
        flow.close()


def test_close_retains_running_letter_unknown_and_restart_does_not_replay(tmp_path):
    entered, release = threading.Event(), threading.Event()
    calls = []

    def letter(task):
        calls.append(task["id"])
        entered.set()
        assert release.wait(5)
        return material(task)

    flow, task = service(tmp_path, letter)
    flow.start(task["id"], task["revision"], "resume")
    assert entered.wait(5)
    flow.close()
    # The first executor retains its lock until its author actually exits.
    duplicate = ApplicationFlowService(flow.applications, tmp_path / "flow", preparation_only=True)
    try:
        assert duplicate._owner is False
        release.set()
        wait_for(
            flow,
            task["id"],
            lambda row: any(artifact["stage"] == "cover_letter" for artifact in row["artifacts"]),
        )
    finally:
        duplicate.close()
    for thread in flow._letter_threads.values():
        thread.join(timeout=5)
    reopened = ApplicationFlowService(
        flow.applications,
        tmp_path / "flow",
        preparation_only=True,
        callbacks={"cover_letter": letter},
    )
    try:
        assert reopened._owner
        assert reopened.cover_letter_outcome(task["id"])["status"] == "needs_recheck"
        assert calls == [task["id"]]
    finally:
        reopened.close()


def test_compatible_analysis_refresh_keeps_completed_letter_version(tmp_path):
    calls = []

    def letter(task):
        calls.append(task["id"])
        return material(task)

    flow, task = service(tmp_path, letter)
    try:
        flow.start(task["id"], task["revision"], "resume")
        done = wait_for(
            flow,
            task["id"],
            lambda row: row["cover_letter"]["status"] == "ready" and row["status"] == "draft_ready",
        )
        saved = done["cover_letter"]
        with flow.applications.write_lock():
            state = flow._load()
            current = flow._task(state, task["id"])
            original = next(row for row in current["artifacts"] if row["stage"] == "analysis")
            from copy import deepcopy

            refreshed = deepcopy(original)
            refreshed["result"]["id"] = "same-selected-facts-new-diagnostic-revision"
            current["artifacts"].append(refreshed)
            current["analysis_id"] = refreshed["result"]["id"]
            flow._save(state)
        flow.start_cover_letter(task["id"], retry=True)
        assert flow.cover_letter_outcome(task["id"]) == saved
        assert calls == [task["id"]]
    finally:
        flow.close()


@pytest.mark.parametrize("corruption", ["application", "body"])
def test_misbound_letter_cannot_be_adopted(tmp_path, corruption):
    def letter(task):
        result = material(task)
        if corruption == "application":
            result["content"]["application_id"] = "another-application"
        else:
            result["text"] = "Changed body with an unchanged receipt."
        return result

    flow, task = service(tmp_path, letter)
    try:
        flow.start(task["id"], task["revision"], "resume")
        stopped = wait_for(
            flow, task["id"], lambda row: row["cover_letter"]["status"] == "needs_recheck"
        )
        assert "result" not in stopped["cover_letter"]
        assert all(
            not row["adopted"] for row in stopped["artifacts"] if row["stage"] == "cover_letter"
        )
    finally:
        flow.close()


def test_second_ready_material_reserves_exact_pair_before_exposure(tmp_path):
    entered, release = threading.Event(), threading.Event()
    calls = []

    def resume(task):
        return {
            "id": "resume-draft",
            "kind": "draft",
            "draft_sha256": "a" * 64,
            "content_revision": "c" * 64,
            "resume_content": {"revision": "c" * 64},
        }

    def consistency(task):
        calls.append(task["material_consistency"]["pair_revision"])
        entered.set()
        assert release.wait(5)
        return {
            "status": "passed",
            **{
                key: task["material_consistency"][key]
                for key in ("resume_content_revision", "letter_content_revision")
            },
        }

    flow, task = service(tmp_path, material, resume)
    flow.callbacks["material_consistency"] = consistency
    try:
        flow.start(task["id"], task["revision"], "resume")
        assert entered.wait(5)
        ready = flow.task_snapshot(task["id"])
        assert ready["cover_letter"]["status"] == "ready"
        assert ready["status"] == "draft_ready"
        assert ready["material_consistency"]["status"] == "running"
        release.set()
        wait_for(flow, task["id"], lambda row: row["material_consistency"]["status"] == "passed")
        flow._run_material_consistency(task["id"])
        assert len(calls) == 1
    finally:
        release.set()
        flow.close()


def test_human_change_waits_for_old_pair_result_then_checks_only_new_pair(tmp_path):
    from career_evidence_graph.application_cover_letter import edit_cover_letter

    entered, release = threading.Event(), threading.Event()
    calls = []

    def resume(task):
        return {
            "id": "resume-draft",
            "kind": "draft",
            "draft_sha256": "a" * 64,
            "content_revision": "c" * 64,
            "resume_content": {"revision": "c" * 64},
        }

    def consistency(task):
        calls.append(task["material_consistency"]["pair_revision"])
        if len(calls) == 1:
            entered.set()
            assert release.wait(5)
        return {
            "status": "passed",
            **{
                key: task["material_consistency"][key]
                for key in ("resume_content_revision", "letter_content_revision")
            },
        }

    flow, task = service(tmp_path, material, resume)
    flow.callbacks["material_consistency"] = consistency
    try:
        flow.start(task["id"], task["revision"], "resume")
        assert entered.wait(5)
        with flow.applications.write_lock():
            state = flow._load()
            current = flow._task(state, task["id"])
            letter = current["cover_letter"]["result"]
            edited = edit_cover_letter(
                letter["content"],
                "Preserved human body.",
                expected_revision=letter["content_revision"],
                edit_id="human-edit",
            )
            letter.update(
                content=edited, content_revision=edited["revision"], text="Preserved human body."
            )
            letter["text_sha256"] = hashlib.sha256(letter["text"].encode()).hexdigest()
            previous_attempt = current["material_consistency"]["attempt_id"]
            flow._reserve_material_consistency(current)
            assert current["material_consistency"]["attempt_id"] == previous_attempt
            flow._save(state)
        release.set()
        done = wait_for(
            flow,
            task["id"],
            lambda row: len(calls) == 2 and row["material_consistency"]["status"] == "passed",
        )
        assert len(set(calls)) == 2
        assert done["cover_letter"]["result"]["text"] == "Preserved human body."
        assert any(row.get("adopted") is False for row in done["material_consistency_history"])
    finally:
        release.set()
        flow.close()


def test_human_change_replaces_unadmitted_pair_without_stalling_current_check(
    tmp_path, monkeypatch
):
    flow, task = service(tmp_path, material)
    queued = []
    flow.callbacks["material_consistency"] = lambda request: {
        "status": "passed",
        **{
            key: request["material_consistency"][key]
            for key in ("resume_content_revision", "letter_content_revision")
        },
    }
    original_put = flow._queue.put
    monkeypatch.setattr(flow._queue, "put", queued.append)
    try:
        with flow.applications.write_lock():
            state = flow._load()
            current = flow._task(state, task["id"])
            current["draft_id"] = "resume-draft"
            current["artifacts"].append(
                {
                    "stage": "resume",
                    "adopted": True,
                    "result": {"id": "resume-draft", "content_revision": "c" * 64},
                }
            )
            current["cover_letter"] = {"status": "ready", "result": {"content_revision": "d" * 64}}
            flow._reserve_material_consistency(current)
            original_attempt = current["material_consistency"]["attempt_id"]
            current["cover_letter"]["result"]["content_revision"] = "e" * 64
            flow._reserve_material_consistency(current)
            assert current["material_consistency"]["attempt_id"] != original_attempt
            assert current["material_consistency"]["letter_content_revision"] == "e" * 64
            retired = current["material_consistency_history"][-1]
            assert retired["attempt_id"] == original_attempt
            assert retired["status"] == "superseded" and retired["adopted"] is False
            flow._save(state)
        flow._run_material_consistency(task["id"])
        done = flow.task_snapshot(task["id"])
        assert done["material_consistency"]["status"] == "passed"
        assert done["material_consistency"]["letter_content_revision"] == "e" * 64
        assert len(queued) == 2
    finally:
        monkeypatch.setattr(flow._queue, "put", original_put)
        flow.close()


def test_explicit_retry_after_skip_reuses_exact_known_success_without_author_calls(tmp_path):
    entered, release = threading.Event(), threading.Event()
    calls = []

    def letter(request):
        calls.append(request["cover_letter"]["attempt_id"])
        entered.set()
        assert release.wait(5)
        return material(request)

    flow, task = service(tmp_path, letter)
    try:
        flow.start(task["id"], task["revision"], "resume")
        assert entered.wait(5)
        flow.cancel_cover_letter(task["id"])
        release.set()
        cancelled = wait_for(
            flow, task["id"], lambda row: row["cover_letter"]["status"] == "cancelled"
        )
        retained = next(
            row["result"] for row in cancelled["artifacts"] if row.get("stage") == "cover_letter"
        )
        resumed = flow.start_cover_letter(task["id"], cancelled["revision"], retry=True)
        assert resumed["cover_letter"]["status"] == "ready"
        assert resumed["cover_letter"]["result"] == retained
        assert resumed["cover_letter"]["attempt_id"] == calls[0]
        assert calls == [calls[0]]
        assert resumed["artifacts"][-1]["reused_after_cancel"] is True
        assert resumed["artifacts"][-1]["adopted"] is True
        assert "cancel_requested" not in resumed["cover_letter"]
    finally:
        release.set()
        flow.close()
