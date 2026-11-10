"""The letter is a Flow stage after the résumé, on the same queue, with its own adopted row."""

import hashlib
import threading
import time
from copy import deepcopy
from pathlib import Path

import pytest

from career_evidence_graph.application_cover_letter import adopted_letter
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
    pytest.fail("letter stage did not reach its expected state")


def material(task):
    branch = task["stages"]["letter"]
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


def service(tmp_path, letter, resume=None):
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
            "job_brief": {
                "requirements": [],
                "job": {"company": "Synthetic Employer", "role_title": "Engineer"},
            },
            "material_packet": {"sources": {}},
            "inference_result": {},
        },
        "resume": resume
        or (lambda task: {"id": "resume-draft", "kind": "draft", "draft_sha256": "a" * 64}),
        "letter": letter,
    }
    flow = ApplicationFlowService(
        applications, tmp_path / "flow", preparation_only=True, callbacks=callbacks
    )
    task = flow.create(application["id"], application["revision"])
    flow.start(task["id"], task["revision"], "analysis")
    task = wait_for(flow, task["id"], lambda row: row["status"] == "analysis_ready")
    return flow, task


def change_saved_task(flow, task_id, change):
    """Change one saved task directly, as a record written outside this stage."""
    with flow.applications.write_lock():
        state = flow._load()
        change(flow._task(state, task_id))
        flow._save(state)


def resume_then_letter(flow, task):
    """Write the résumé, then start the letter stage as ``prepare`` does."""
    flow.start(task["id"], task["revision"], "resume")
    drafted = wait_for(flow, task["id"], lambda row: row["status"] == "draft_ready")
    return flow.start(task["id"], drafted["revision"], "letter")


def test_prepare_runs_letter_after_resume_on_the_flow_queue(tmp_path):
    entered, release = threading.Event(), threading.Event()
    requests = {}

    def letter(task):
        requests["letter"] = task
        entered.set()
        assert release.wait(5)
        return material(task)

    def resume(task):
        requests["resume"] = task
        return {"id": "resume-draft", "kind": "draft", "draft_sha256": "a" * 64}

    flow, task = service(tmp_path, letter, resume)
    try:
        flow.start(task["id"], task["revision"], "resume")
        drafted = wait_for(flow, task["id"], lambda row: row["status"] == "draft_ready")
        # The résumé ran alone; the letter starts only after it.
        assert "letter" not in requests and "letter" not in drafted["stages"]
        flow.prepare(task["id"], drafted["revision"])
        assert entered.wait(5)
        # The callback is held outside the store lock, and the résumé status stays.
        running = flow.task_snapshot(task["id"])
        assert running["stages"]["letter"]["status"] == "running"
        assert running["status"] == "draft_ready"
        assert flow.progress(task["id"])["status"] == "running"
        assert requests["letter"]["analysis_id"] == requests["resume"]["analysis_id"]
        release.set()
        done = wait_for(
            flow, task["id"], lambda row: row["stages"]["letter"]["status"] == "complete"
        )
        assert done["status"] == "draft_ready"
        assert done["draft_id"] == "resume-draft"
        assert done["letter_id"] == requests["letter"]["stages"]["letter"]["attempt_id"]
        assert adopted_letter(done) == material(requests["letter"])
        assert "cover_letter" not in done
        assert {row["stage"] for row in done["artifacts"] if row["adopted"]} == {
            "analysis",
            "resume",
            "letter",
        }
    finally:
        release.set()
        flow.close()


@pytest.mark.parametrize("code", ["letter_generation_failed", "letter_generation_no_answer"])
def test_letter_failure_continues_like_resume_author_and_keeps_resume(tmp_path, code):
    calls = []

    def letter(task):
        calls.append(("letter", task["stages"]["letter"]))
        if len([row for row in calls if row[0] == "letter"]) == 1:
            raise PortalDataError(code, "Synthetic rejection", 409)
        return material(task)

    def resume(task):
        calls.append(("resume", None))
        return {"id": "resume-draft", "kind": "draft", "draft_sha256": "a" * 64}

    flow, task = service(tmp_path, letter, resume)
    try:
        resume_then_letter(flow, task)
        failed = wait_for(
            flow, task["id"], lambda row: row["stages"]["letter"]["status"] == "failed"
        )
        assert failed["status"] == "draft_ready"
        prior_resume = [row for row in failed["artifacts"] if row["stage"] == "resume"]
        progress = flow.progress(task["id"])
        assert progress["status"] == "waiting"
        assert progress["wait_reason"] == "resume_author_input_required"
        first = failed["stages"]["letter"]["attempt_id"]
        assert progress["continuation"] == {
            "task_id": task["id"],
            "attempt_id": first,
            "stage": "letter",
        }
        flow.continue_preparation(
            task["id"], failed["revision"], request_id="continue-1", expected_attempt_id=first
        )
        done = wait_for(
            flow, task["id"], lambda row: row["stages"]["letter"]["status"] == "complete"
        )
        assert [name for name, _ in calls] == ["resume", "letter", "letter"]
        # The retry names the earlier attempt, whose answered calls are reused.
        assert calls[-1][1]["retry_from_attempt_id"] == first
        assert [row for row in done["artifacts"] if row["stage"] == "resume"] == prior_resume
        before = list(calls)
        flow.start(task["id"], done["revision"], "letter", retry=True)
        assert calls == before
    finally:
        flow.close()


def test_unknown_letter_waits_and_only_an_explicit_retry_runs_it_again(tmp_path):
    calls = []

    def letter(task):
        calls.append(task["stages"]["letter"]["attempt_id"])
        if len(calls) == 1:
            raise PortalDataError("letter_generation_needs_recheck", "response lost", 409)
        return material(task)

    flow, task = service(tmp_path, letter)
    try:
        resume_then_letter(flow, task)
        unknown = wait_for(
            flow, task["id"], lambda row: row["stages"]["letter"]["status"] == "needs_recheck"
        )
        assert unknown["status"] == "draft_ready"
        progress = flow.progress(task["id"])
        assert (progress["status"], progress["wait_reason"]) == (
            "needs_recheck",
            "material_result_unknown",
        )
        with pytest.raises(PortalDataError, match="未知"):
            flow.start(task["id"], unknown["revision"], "letter")
        # Approved 2026-10-31: writing only drafts text, so the user's retry may re-run it.
        flow.start(task["id"], unknown["revision"], "letter", retry=True)
        done = wait_for(
            flow, task["id"], lambda row: row["stages"]["letter"]["status"] == "complete"
        )
        assert len(calls) == 2
        assert done["stages"]["letter"]["retry_from_attempt_id"] == calls[0]
    finally:
        flow.close()


def test_cancel_retains_late_letter_without_adopting_it(tmp_path):
    entered, release = threading.Event(), threading.Event()

    def letter(task):
        entered.set()
        assert release.wait(5)
        return material(task)

    flow, task = service(tmp_path, letter)
    try:
        started = resume_then_letter(flow, task)
        assert entered.wait(5)
        flow.cancel_preparation(task["id"], flow.task_snapshot(task["id"])["revision"])
        release.set()
        done = wait_for(
            flow,
            task["id"],
            lambda row: any(artifact["stage"] == "letter" for artifact in row["artifacts"]),
        )
        assert done["stages"]["letter"]["status"] == "cancelled"
        letters = [row for row in done["artifacts"] if row["stage"] == "letter"]
        assert [row["attempt_id"] for row in letters] == [started["stages"]["letter"]["attempt_id"]]
        assert letters[0]["adopted"] is False
        assert adopted_letter(done) is None
    finally:
        release.set()
        flow.close()


def test_close_marks_running_letter_interrupted_and_restart_does_not_replay(tmp_path):
    entered, release = threading.Event(), threading.Event()
    calls = []

    def letter(task):
        calls.append(task["id"])
        entered.set()
        assert release.wait(5)
        return material(task)

    flow, task = service(tmp_path, letter)
    resume_then_letter(flow, task)
    assert entered.wait(5)
    flow.close()
    # The first executor retains its lock until its author actually exits.
    duplicate = ApplicationFlowService(flow.applications, tmp_path / "flow", preparation_only=True)
    try:
        assert duplicate._owner is False
    finally:
        duplicate.close()
    release.set()
    flow._thread.join(timeout=5)
    reopened = ApplicationFlowService(
        flow.applications,
        tmp_path / "flow",
        preparation_only=True,
        callbacks={"letter": letter},
    )
    try:
        assert reopened._owner
        saved = reopened.task_snapshot(task["id"])
        assert saved["stages"]["letter"]["status"] == "failed"
        assert saved["stages"]["letter"]["error_code"] == "flow_interrupted"
        # The letter stage never changes the résumé's task status.
        assert saved["status"] == "draft_ready"
        assert reopened.material_outcomes([task["id"]])[task["id"]]["letter"] == "failed"
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
        resume_then_letter(flow, task)
        done = wait_for(
            flow, task["id"], lambda row: row["stages"]["letter"]["status"] == "complete"
        )
        saved = adopted_letter(done)

        def refresh(current):
            original = next(row for row in current["artifacts"] if row["stage"] == "analysis")
            refreshed = deepcopy(original)
            refreshed["result"]["id"] = "same-selected-facts-new-diagnostic-revision"
            current["artifacts"].append(refreshed)
            current["analysis_id"] = refreshed["result"]["id"]

        change_saved_task(flow, task["id"], refresh)
        refreshed_task = flow.task_snapshot(task["id"])
        flow.start(task["id"], refreshed_task["revision"], "letter", retry=True)
        assert adopted_letter(flow.task_snapshot(task["id"])) == saved
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
        resume_then_letter(flow, task)
        stopped = wait_for(
            flow, task["id"], lambda row: row["stages"]["letter"]["status"] == "needs_recheck"
        )
        assert stopped["stages"]["letter"]["error_code"] == "letter_result_invalid"
        assert "letter_id" not in stopped
        assert all(not row["adopted"] for row in stopped["artifacts"] if row["stage"] == "letter")
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
        resume_then_letter(flow, task)
        assert entered.wait(5)
        ready = flow.task_snapshot(task["id"])
        assert ready["stages"]["letter"]["status"] == "complete"
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
        resume_then_letter(flow, task)
        assert entered.wait(5)
        with flow.applications.write_lock():
            state = flow._load()
            current = flow._task(state, task["id"])
            # A human edit appends a newer adopted letter row.
            letter = deepcopy(adopted_letter(current))
            current["artifacts"].append({"stage": "letter", "adopted": True, "result": letter})
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
        assert adopted_letter(done)["text"] == "Preserved human body."
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
            current["stages"]["letter"] = {"status": "complete"}
            current["letter_id"] = "letter"
            row = {"stage": "letter", "adopted": True, "result": {"id": "letter"}}
            row["result"]["content_revision"] = "d" * 64
            current["artifacts"].append(row)
            flow._reserve_material_consistency(current)
            original_attempt = current["material_consistency"]["attempt_id"]
            row["result"]["content_revision"] = "e" * 64
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


def letter_pdf_store(tmp_path, client):
    """The Worker store pieces Flow's letter_export uses: template, compiler, inspector."""
    from types import SimpleNamespace

    from test_cover_letter_delivery import TEMPLATE

    template = tmp_path / "private-letter.tex"
    template.write_text(TEMPLATE)
    return SimpleNamespace(
        cover_letter_template=template,
        cover_letter_client=client,
        cover_letter_pdf_inspector=lambda raw: 1,
    )


def letter_ready(tmp_path, client):
    flow, task = service(tmp_path, material)
    store = letter_pdf_store(tmp_path, client)
    flow.callbacks["letter_export"] = lambda request: flow.export_letter(store, request)
    resume_then_letter(flow, task)
    done = wait_for(flow, task["id"], lambda row: row["stages"]["letter"]["status"] == "complete")
    return flow, done


def test_prepare_builds_the_letter_pdf_once_in_flow_before_the_export(tmp_path):
    from test_cover_letter_content import Compiler

    from career_evidence_graph.application_cover_letter import adopted_letter_pdf, letter_branch

    compiler = Compiler()
    flow, task = letter_ready(tmp_path, compiler)
    try:
        assert flow.letter_export_due(task)
        flow.prepare(task["id"], task["revision"])
        done = wait_for(
            flow, task["id"], lambda row: row["stages"]["letter_export"]["status"] == "complete"
        )
        # The PDF stage never changes the résumé's task status.
        assert done["status"] == "draft_ready"
        pdf = adopted_letter_pdf(done)
        assert pdf["id"] == done["letter_export_id"] and pdf["page_count"] == 1
        assert pdf["content_revision"] == adopted_letter(done)["content_revision"]
        assert Path(pdf["file_path"]).parent == flow.root / "letter-pdfs" / pdf["id"]
        assert letter_branch(done)["pdf"] == pdf
        assert not flow.letter_export_due(done)
        flow.start(task["id"], done["revision"], "letter_export", retry=True)
        assert compiler.calls == 1
    finally:
        flow.close()


def test_unknown_letter_pdf_waits_and_continue_builds_it_again(tmp_path):
    from test_cover_letter_content import Compiler

    from career_evidence_graph.application_cover_letter import adopted_letter_pdf

    compiler = Compiler(unknown=True)
    flow, task = letter_ready(tmp_path, compiler)
    try:
        flow.start(task["id"], task["revision"], "letter_export")
        unknown = wait_for(
            flow,
            task["id"],
            lambda row: row["stages"]["letter_export"]["status"] == "needs_recheck",
        )
        assert unknown["stages"]["letter_export"]["error_code"] == "letter_export_needs_recheck"
        assert unknown["status"] == "draft_ready" and adopted_letter_pdf(unknown) is None
        progress = flow.progress(task["id"])
        assert (progress["status"], progress["wait_reason"]) == (
            "needs_recheck",
            "material_result_unknown",
        )
        first = flow.root / "letter-pdfs" / unknown["stages"]["letter_export"]["attempt_id"]
        files = {path: path.read_bytes() for path in first.rglob("*") if path.is_file()}
        with pytest.raises(PortalDataError):
            flow.start(task["id"], unknown["revision"], "letter_export")
        compiler.unknown = False
        flow.start(task["id"], unknown["revision"], "letter_export", retry=True)
        done = wait_for(
            flow, task["id"], lambda row: row["stages"]["letter_export"]["status"] == "complete"
        )
        assert Path(adopted_letter_pdf(done)["file_path"]).parent != first
        assert {path: path.read_bytes() for path in first.rglob("*") if path.is_file()} == files
        assert compiler.calls == 2
    finally:
        flow.close()


def test_an_edited_letter_body_gets_its_own_pdf(tmp_path):
    from test_cover_letter_content import Compiler

    from career_evidence_graph.application_cover_letter import adopted_letter_pdf, edit_cover_letter

    compiler = Compiler()
    flow, task = letter_ready(tmp_path, compiler)
    try:
        flow.start(task["id"], task["revision"], "letter_export")
        built = wait_for(
            flow, task["id"], lambda row: row["stages"]["letter_export"]["status"] == "complete"
        )
        letter = deepcopy(adopted_letter(built))
        edited = edit_cover_letter(
            letter["content"],
            "Preserved human body.",
            expected_revision=letter["content_revision"],
            edit_id="human-edit",
        )
        letter.update(content=edited, content_revision=edited["revision"])
        # A human edit appends a newer adopted letter row.
        change_saved_task(
            flow,
            task["id"],
            lambda current: current["artifacts"].append(
                {"stage": "letter", "adopted": True, "result": letter}
            ),
        )
        edited_task = flow.task_snapshot(task["id"])
        assert adopted_letter_pdf(edited_task) is None and flow.letter_export_due(edited_task)
        flow.start(task["id"], edited_task["revision"], "letter_export")
        done = wait_for(
            flow,
            task["id"],
            lambda row: (
                row["letter_export_id"] != built["letter_export_id"]
                and row["stages"]["letter_export"]["status"] == "complete"
            ),
        )
        assert adopted_letter_pdf(done)["content_revision"] == edited["revision"]
        assert compiler.calls == 2
    finally:
        flow.close()
