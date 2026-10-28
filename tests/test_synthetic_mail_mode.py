"""The fixed mail entry uses ordinary intake and isolated, persistent simulated IO."""

import json
import os
import select
import subprocess
import sys
import time
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import urlsplit

import pytest
from test_installed_preparation_mode import request, stop_backend

CHECKOUT = Path(__file__).resolve().parents[1]

_HISTORICAL_MAIL_CHILD = """import runpy
import sys
from pathlib import Path

server = Path(sys.argv[1])
sys.path.insert(0, str(server.parents[1] / "src"))
from career_evidence_graph.application_flow import ApplicationFlowService

current_task = ApplicationFlowService._new_task
def restored_historical_task(application, inputs):
    task = current_task(application, inputs)
    task.pop("material_contract", None)
    return task

ApplicationFlowService._new_task = staticmethod(restored_historical_task)
sys.argv = sys.argv[1:]
runpy.run_path(str(server), run_name="__main__")
"""


def create_mail_root(tmp_path):
    root = tmp_path / "synthetic mail"
    result = subprocess.run(
        [
            sys.executable,
            "-I",
            "-B",
            str(CHECKOUT / "scripts/create_synthetic_flow.py"),
            "--mail",
            str(root),
        ],
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert result.returncode == 0, result.stderr
    return root


def test_mail_generator_seeds_fixed_settings_and_two_known_jobs(tmp_path):
    from career_evidence_graph.career_portal_data import ApplicationStore

    root = create_mail_root(tmp_path)
    config = json.loads((root / "portal.json").read_text())
    assert config == {
        "applications": str(root / "applications"),
        "career_workspace": str(root / "career"),
        "preparation_root": str(root / "latex-base"),
    }
    assert json.loads((root / "synthetic-flow.json").read_text())["purpose"] == "mail-synthetic"
    assert len(ApplicationStore(root / "applications").list_applications()) == 2
    assert (root / "latex-base/main.tex").is_file()
    assert (root / "synthetic-preview.pdf").is_file()


def test_mail_receipts_survive_reopen_without_repeating_unknown_archive(tmp_path):
    from test_application_intake import ready

    from career_evidence_graph.application_preparation_fixtures import create_mail_intake
    from career_evidence_graph.career_portal_data import ApplicationStore

    root = create_mail_root(tmp_path)
    applications = ApplicationStore(root / "applications")
    intake_root = root / "runtime/single-job-flow/intake"
    options = {"processed_label": "  Synthetic Processed / 已处理  "}
    service = create_mail_intake(applications, intake_root, **options)
    try:
        service.refresh(capture_only=True)
        first = ready(service)
        assert first["progress"]["mail_needs_recheck"] == 1
        assert first["progress"]["mail_archived"] == 1
        assert len(first["recommendations"]) == 2
        assert all(
            row["acquisition_checkpoint"] == "not_started" for row in first["recommendations"]
        )
    finally:
        service.close()

    service = create_mail_intake(applications, intake_root, **options)
    try:
        service.continue_read()
        after = ready(service)
        assert after["progress"]["mail_archived"] == 2
        assert after["progress"]["mail_needs_recheck"] == 0
        receipts = json.loads((intake_root / "synthetic-mailbox.json").read_text())
        archives = [row for row in receipts["calls"] if row[1] == "archive"]
        assert archives == [["mail-synthetic-1", "archive"], ["mail-synthetic-2", "archive"]]
    finally:
        service.close()


@contextmanager
def mail_backend(root, *, extra=(), legacy_material_history=False):
    # Only explicit old-material cases replay tasks saved before JSON contracts.
    # Ordinary synthetic mail keeps the current production task contract.
    process = subprocess.Popen(
        [
            sys.executable,
            "-I",
            "-B",
            "-u",
            *(["-c", _HISTORICAL_MAIL_CHILD] if legacy_material_history else []),
            str(CHECKOUT / "macos/server.py"),
            "--synthetic-mail",
            str(root),
            *extra,
        ],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=os.environ | {"OPENAI_API_KEY": "synthetic-must-be-cleared"},
    )
    try:
        assert select.select([process.stdout], [], [], 10)[0], "backend never became ready"
        ready = json.loads(process.stdout.readline())
        assert ready["status"] == "ready", (ready, process.stderr.read())
        yield ready, urlsplit(ready["url"])
    finally:
        stop_backend(process)


def wait_capture(address):
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        status, result = request(address, "GET", "/api/recommendations/state")
        assert status == 200, result
        if result["status"] != "running":
            return result
        time.sleep(0.02)
    pytest.fail("Fixed mail capture did not finish")


@pytest.mark.parametrize(
    ("legacy_wait", "admit_during_wait"),
    [(False, False), (True, False), (True, True)],
    ids=["marked", "legacy", "legacy-admitted"],
)
def test_mail_bootstrap_continue_after_reopened_archive_recovery(
    tmp_path, legacy_wait, admit_during_wait
):
    from career_evidence_graph.application_worker import digest

    root = create_mail_root(tmp_path)
    config_path = root / "portal.json"
    config = json.loads(config_path.read_text())
    config["application_processed_label"] = "Synthetic Processed / 已处理"
    config_path.write_text(json.dumps(config))
    with mail_backend(root, legacy_material_history=True) as (_, address):
        _, initial = request(address, "GET", "/api/state")
        status, started = request(
            address,
            "POST",
            "/api/pipeline/start",
            payload={"request_id": "mail-bootstrap-reopen"},
            token=initial["csrf_token"],
        )
        assert status == 200, started
        deadline = time.monotonic() + 6
        while time.monotonic() < deadline:
            _, waiting = request(address, "GET", "/api/pipeline/state")
            if waiting["status"] == "needs_input":
                break
            time.sleep(0.02)
        assert waiting["status"] == "needs_input", waiting
        assert waiting["active_task_id"] is None
        assert waiting["current_recommendation_id"] is None
        assert waiting["resume_status"] == "reading_email"
        assert waiting["wait_reason"] == "mail_capture_incomplete"
        captured = wait_capture(address)
        assert captured["progress"]["mail_archived"] == 1
        assert captured["progress"]["mail_needs_recheck"] == 1
        if admit_during_wait:
            row = captured["recommendations"][1]
            status, admitted = request(
                address,
                "POST",
                "/api/pipeline/admit",
                payload={
                    "request_id": "admit-during-bootstrap-wait",
                    "recommendation_id": row["id"],
                    "recommendation_revision": row["revision"],
                },
                token=initial["csrf_token"],
            )
            assert status == 200, admitted
            assert len(admitted["items"]) == 2
            assert all(
                row["status"] == "admitted" and row["task_id"] is None for row in admitted["items"]
            )
            assert admitted["active_task_id"] is None
        _, flow = request(address, "GET", "/api/flow/state")
        assert flow["tasks"] == []

    # Reopen the old persisted wait after the next automatic capture becomes due.
    pipeline_path = root / "runtime/single-job-flow/pipeline.json"
    saved = json.loads(pipeline_path.read_text())
    if legacy_wait:
        saved.pop("wait_reason")
        saved.pop("resume_status")
    saved["mail_poll_at"] = 0
    saved["revision"] = digest({key: value for key, value in saved.items() if key != "revision"})
    pipeline_path.write_text(json.dumps(saved))
    mailbox_path = root / "runtime/single-job-flow/intake/synthetic-mailbox.json"
    before_calls = json.loads(mailbox_path.read_text())["calls"]
    with mail_backend(root, legacy_material_history=True) as (_, address):
        _, initial = request(address, "GET", "/api/state")
        deadline = time.monotonic() + 6
        while time.monotonic() < deadline:
            _, captured = request(address, "GET", "/api/recommendations/state")
            if (
                captured["status"] == "complete"
                and captured["progress"]["mail_archived"] == 2
                and captured["progress"]["mail_needs_recheck"] == 0
            ):
                break
            time.sleep(0.02)
        assert captured["status"] == "complete", captured
        assert captured["progress"]["mail_archived"] == 2
        assert captured["progress"]["mail_needs_recheck"] == 0
        calls = json.loads(mailbox_path.read_text())["calls"]
        assert [row for row in calls if row[1] == "archive"] == [
            ["mail-synthetic-1", "archive"],
            ["mail-synthetic-2", "archive"],
        ]
        assert len([row for row in calls if row[1] == "inspect"]) == (
            len([row for row in before_calls if row[1] == "inspect"]) + 1
        )
        _, reopened = request(address, "GET", "/api/pipeline/state")
        assert reopened["status"] == "needs_input" and reopened["active_task_id"] is None
        status, continued = request(
            address,
            "POST",
            "/api/pipeline/continue",
            payload={"request_id": "continue-recovered-bootstrap"},
            token=initial["csrf_token"],
        )
        assert status == 200, continued
        assert continued["id"] == started["id"]
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            _, continued = request(address, "GET", "/api/pipeline/state")
            if continued["control"] == "paused":
                break
            time.sleep(0.02)
        assert continued["status"] == "needs_input", continued
        assert continued["wait_reason"] == "application_country_required"
        assert continued["active_task_id"]
        if admit_during_wait:
            assert (
                continued["current_recommendation_id"] == admitted["items"][0]["recommendation_id"]
            )
            assert continued["items"][1]["status"] == "admitted"
        _, flow = request(address, "GET", "/api/flow/state")
        assert len(flow["tasks"]) == 1
        assert flow["active_task"]["id"] == continued["active_task_id"]
        assert flow["active_task"]["status"] == "materials_ready"
        assert json.loads(mailbox_path.read_text())["calls"] == calls


def test_mail_bootstrap_unresolved_continue_waits_without_repeating_archive(tmp_path):
    root = create_mail_root(tmp_path)
    config_path = root / "portal.json"
    config = json.loads(config_path.read_text())
    config["application_processed_label"] = "Synthetic Processed / 已处理"
    config_path.write_text(json.dumps(config))
    with mail_backend(root) as (_, address):
        _, initial = request(address, "GET", "/api/state")
        token = initial["csrf_token"]
        status, result = request(
            address,
            "POST",
            "/api/pipeline/start",
            payload={"request_id": "unresolved-mail-bootstrap"},
            token=token,
        )
        assert status == 200, result
        deadline = time.monotonic() + 6
        while time.monotonic() < deadline:
            _, waiting = request(address, "GET", "/api/pipeline/state")
            if waiting["status"] == "needs_input":
                break
            time.sleep(0.02)
        assert waiting["wait_reason"] == "mail_capture_incomplete", waiting
        mailbox_path = root / "runtime/single-job-flow/intake/synthetic-mailbox.json"
        calls = json.loads(mailbox_path.read_text())["calls"]
        status, continued = request(
            address,
            "POST",
            "/api/pipeline/continue",
            payload={"request_id": "continue-unresolved-bootstrap"},
            token=token,
        )
        assert status == 200, continued
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            _, continued = request(address, "GET", "/api/pipeline/state")
            if continued["control"] == "paused":
                break
            time.sleep(0.02)
        assert continued["status"] == "needs_input"
        assert continued["wait_reason"] == "mail_capture_incomplete"
        assert continued["intake_run_id"] == waiting["intake_run_id"]
        assert continued["current_recommendation_id"] is None
        assert continued["active_task_id"] is None
        _, flow = request(address, "GET", "/api/flow/state")
        assert flow["tasks"] == []
        assert json.loads(mailbox_path.read_text())["calls"] == calls


def test_mail_bootstrap_continue_rejects_other_missing_current_states(tmp_path):
    from career_evidence_graph.application_worker import digest

    root = create_mail_root(tmp_path)
    with mail_backend(root) as (_, address):
        _, initial = request(address, "GET", "/api/state")
        status, captured = request(
            address,
            "POST",
            "/api/pipeline/capture",
            payload={"request_id": "capture-without-start"},
            token=initial["csrf_token"],
        )
        assert status == 200, captured
        captured = wait_capture(address)
        status, rejected = request(
            address,
            "POST",
            "/api/pipeline/continue",
            payload={"request_id": "cannot-start-by-continue"},
            token=initial["csrf_token"],
        )
        assert status == 409 and rejected["error"] == "pipeline_request_invalid", rejected

    pipeline_path = root / "runtime/single-job-flow/pipeline.json"
    original = json.loads(pipeline_path.read_text())
    retained_item = {
        "recommendation_id": captured["recommendations"][0]["id"],
        "application_id": None,
        "task_id": None,
        "score": None,
    }
    # These retained shapes are deliberately not a captured-mail bootstrap wait.
    for changes in (
        {"id": None},
        {"source_receipt": {"status": "selected"}},
        {"active_task_id": "retained-task"},
        {"worker_batch_id": "retained-batch"},
        {"transmission_authorization": {"status": "unknown"}},
        {"wait_reason": "language_information_required"},
        {"resume_status": "matching"},
        {"status": "paused", "resume_status": "needs_input"},
        {"items": [retained_item | {"status": "pending"}]},
        {"items": [retained_item | {"status": "needs_recheck"}]},
        {"items": [retained_item | {"status": "admitted", "task_id": "retained-task"}]},
    ):
        saved = (
            original
            | {
                "id": "retained-pipeline",
                "queue_mode": True,
                "status": "needs_input",
                "control": "paused",
                "mail_poll_at": time.time() + 60,
                "intake_run_id": captured["run_id"],
                "resume_status": "reading_email",
                "wait_reason": "mail_capture_incomplete",
            }
            | changes
        )
        saved["revision"] = digest(
            {key: value for key, value in saved.items() if key != "revision"}
        )
        pipeline_path.write_text(json.dumps(saved))
        with mail_backend(root) as (_, address):
            _, initial = request(address, "GET", "/api/state")
            status, rejected = request(
                address,
                "POST",
                "/api/pipeline/continue",
                payload={"request_id": "reject-other-bootstrap-shape"},
                token=initial["csrf_token"],
            )
            assert status == 409 and rejected["error"] == "pipeline_current_missing", (
                changes,
                rejected,
            )


@pytest.mark.parametrize("label", [None, "  Synthetic Processed / 已处理  ", "INBOX"])
def test_backend_mail_entry_captures_with_local_label_and_reopens(tmp_path, label):
    root = create_mail_root(tmp_path)
    config = json.loads((root / "portal.json").read_text())
    if label is not None:
        config["application_processed_label"] = label
        (root / "portal.json").write_text(json.dumps(config))
    with mail_backend(root) as (ready, address):
        assert ready["capabilities"] == {
            "codex": True,
            "flow": True,
            "worker": True,
            "synthetic": True,
        }
        status, initial = request(address, "GET", "/api/state")
        assert status == 200
        status, result = request(
            address,
            "POST",
            "/api/pipeline/capture",
            payload={"request_id": "fixed-mail-capture"},
            token=initial["csrf_token"],
        )
        assert status == 200, result
        captured = wait_capture(address)
        assert captured["progress"]["pages"] == 2
        assert len(captured["recommendations"]) == 2
        assert captured["progress"]["mail_processing_error"] == (
            "gmail_processing_invalid" if label == "INBOX" else ""
        )
        assert captured["progress"]["mail_needs_recheck"] == int(
            label is not None and label != "INBOX"
        )
        status, pipeline = request(address, "GET", "/api/pipeline/state")
        assert status == 200 and pipeline["active_task_id"] is None
    with mail_backend(root) as (_, address):
        reopened = wait_capture(address)
        assert reopened["recommendations"] == captured["recommendations"]
        assert reopened["progress"]["mail_label_configured"] == (
            label is not None and label != "INBOX"
        )


def test_default_mail_task_keeps_json_contract_and_waits_for_structured_facts(tmp_path):
    root = create_mail_root(tmp_path)
    with mail_backend(root) as (_, address):
        _, initial = request(address, "GET", "/api/state")
        status, started = request(
            address,
            "POST",
            "/api/pipeline/start",
            payload={"request_id": "current-mail-content-contract"},
            token=initial["csrf_token"],
        )
        assert status == 200, started
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            _, pipeline = request(address, "GET", "/api/pipeline/state")
            if pipeline["control"] == "paused":
                break
            time.sleep(0.02)
        assert pipeline["status"] == "needs_recheck", pipeline
        _, flow = request(address, "GET", "/api/flow/state")
        task = flow["active_task"]
        assert task["id"] == pipeline["active_task_id"]
        assert task["material_contract"] == "content-writing/v1"
        assert task["stages"]["resume"]["error_code"] == "resume_content_material_required"
        assert not task.get("experience_handoff")
        assert task.get("draft_id") is None and task["resume_id"] is None


def test_mail_entry_runs_existing_queue_and_holds_next_job_at_missing_fact(tmp_path):
    root = create_mail_root(tmp_path)
    with mail_backend(root, legacy_material_history=True) as (_, address):
        _, initial = request(address, "GET", "/api/state")
        token = initial["csrf_token"]
        status, result = request(
            address,
            "POST",
            "/api/pipeline/start",
            payload={"request_id": "fixed-mail-pipeline"},
            token=token,
        )
        assert status == 200, result
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            status, pipeline = request(address, "GET", "/api/pipeline/state")
            assert status == 200, pipeline
            if pipeline["status"] in {"needs_input", "needs_recheck", "failed"}:
                break
            time.sleep(0.05)
        assert pipeline["status"] == "needs_input", pipeline
        assert pipeline["active_task_id"]
        _, flow = request(address, "GET", "/api/flow/state")
        assert len(flow["tasks"]) == 1
        _, recommendations = request(address, "GET", "/api/recommendations/state")
        assert len(recommendations["recommendations"]) == 2
        status, result = request(
            address,
            "POST",
            "/api/pipeline/capture",
            payload={"request_id": "capture-during-fixed-wait"},
            token=token,
        )
        assert status == 200, result
        wait_capture(address)
        _, after = request(address, "GET", "/api/pipeline/state")
        assert after["active_task_id"] == pipeline["active_task_id"]
        assert after["status"] == "needs_input"
        _, retained = request(address, "GET", "/api/flow/state")
        assert retained["tasks"] == flow["tasks"]

        status, continued = request(
            address,
            "POST",
            "/api/pipeline/continue",
            payload={"request_id": "continue-country-still-missing"},
            token=token,
        )
        assert status == 200, continued
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            _, after = request(address, "GET", "/api/pipeline/state")
            if after["control"] == "paused":
                break
            time.sleep(0.02)
        assert after["status"] == "needs_input", after
        assert after["active_task_id"] == pipeline["active_task_id"]
        assert after["wait_reason"] == "application_country_required"
        assert after["resume_status"] == "generating_resume"
        _, retained = request(address, "GET", "/api/flow/state")
        assert retained["tasks"] == flow["tasks"]


def test_mail_country_location_patch_continues_same_task_through_fresh_analysis(tmp_path):
    root = create_mail_root(tmp_path)
    with mail_backend(root, legacy_material_history=True) as (_, address):
        _, initial = request(address, "GET", "/api/state")
        token = initial["csrf_token"]
        status, result = request(
            address,
            "POST",
            "/api/pipeline/start",
            payload={"request_id": "mail-country-location-patch"},
            token=token,
        )
        assert status == 200, result
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            _, waiting = request(address, "GET", "/api/pipeline/state")
            if waiting["status"] == "needs_input":
                break
            time.sleep(0.05)
        assert waiting["wait_reason"] == "application_country_required", waiting
        _, before = request(address, "GET", "/api/flow/state")
        original = before["active_task"]
        assert len(before["tasks"]) == 1 and original["status"] == "materials_ready"
        assert original["resume_id"] and original["analysis_id"]
        pdfs = {path: path.read_bytes() for path in root.rglob("*.pdf")}
        application_path = "/api/applications/" + original["application_id"]
        _, shown = request(address, "GET", application_path)
        status, saved = request(
            address,
            "PATCH",
            application_path,
            payload={
                "revision": shown["application"]["revision"],
                "location": "Zurich, Switzerland",
            },
            token=token,
        )
        assert status == 200, saved
        status, continued = request(
            address,
            "POST",
            "/api/pipeline/continue",
            payload={"request_id": "continue-after-country-location-patch"},
            token=token,
        )
        assert status == 200, continued
        assert continued["status"] == "matching", continued
        assert continued["active_task_id"] == original["id"]
        assert continued["current_recommendation_id"] == waiting["current_recommendation_id"]
        assert continued.get("history", []) == waiting.get("history", [])
        _, after = request(address, "GET", "/api/flow/state")
        current = after["active_task"]
        assert len(after["tasks"]) == 1 and current["id"] == original["id"]
        assert current["input_epoch"] == original.get("input_epoch", 0) + 1
        assert current["job_binding"] != original["job_binding"]
        assert current["application_revision"] == saved["application"]["revision"]
        assert current["stages"]["analysis"]["status"] in {"queued", "running", "complete"}
        assert current["stages"]["analysis"] != original["stages"]["analysis"]
        assert current["stages"]["resume"] == {"status": "pending"}
        assert current["stages"]["export"] == {"status": "pending"}
        assert current["resume_id"] is None and current["resume_sha256"] is None
        assert current["materials_confirmed"] is False
        assert all(path.read_bytes() == content for path, content in pdfs.items())
        # Stop here, before the ordinary generation/filling ticks can run.


@pytest.mark.parametrize(
    ("resolve_location", "legacy_markers"),
    [
        (False, {}),
        (True, {}),
        (True, {"wait_reason": "qualification_conflict"}),
        (True, {"resume_status": "matching"}),
    ],
    ids=["missing-location", "patched-location", "other-wait-reason", "partial-marker"],
)
def test_legacy_country_wait_reopens_and_continues_same_task(
    tmp_path, resolve_location, legacy_markers
):
    from career_evidence_graph.application_worker import digest

    root = create_mail_root(tmp_path)
    with mail_backend(root, legacy_material_history=True) as (_, address):
        _, initial = request(address, "GET", "/api/state")
        status, result = request(
            address,
            "POST",
            "/api/pipeline/start",
            payload={"request_id": "legacy-country-wait"},
            token=initial["csrf_token"],
        )
        assert status == 200, result
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            _, waiting = request(address, "GET", "/api/pipeline/state")
            if waiting["status"] == "needs_input":
                break
            time.sleep(0.05)
        assert waiting["wait_reason"] == "application_country_required", waiting
        _, before = request(address, "GET", "/api/flow/state")
        original = before["active_task"]
        assert original["status"] == "materials_ready"
    # Recreate the persisted shape emitted before country recovery markers existed.
    pipeline_path = root / "runtime/single-job-flow/pipeline.json"
    legacy = json.loads(pipeline_path.read_text())
    legacy.pop("wait_reason")
    legacy.pop("resume_status")
    legacy.update(legacy_markers)
    legacy["notification"]["message"] = "Retained historical notice"
    legacy["revision"] = digest({key: value for key, value in legacy.items() if key != "revision"})
    pipeline_path.write_text(json.dumps(legacy))
    pdfs = {path: path.read_bytes() for path in root.rglob("*.pdf")}
    with mail_backend(root, legacy_material_history=True) as (_, address):
        _, initial = request(address, "GET", "/api/state")
        token = initial["csrf_token"]
        if resolve_location:
            application_path = "/api/applications/" + original["application_id"]
            _, shown = request(address, "GET", application_path)
            status, saved = request(
                address,
                "PATCH",
                application_path,
                payload={
                    "revision": shown["application"]["revision"],
                    "location": "Zurich, Switzerland",
                },
                token=token,
            )
            assert status == 200, saved
        status, continued = request(
            address,
            "POST",
            "/api/pipeline/continue",
            payload={"request_id": "continue-reopened-legacy-country"},
            token=token,
        )
        if legacy_markers:
            assert status == 409 and continued["error"] == "pipeline_exists", continued
            _, after = request(address, "GET", "/api/flow/state")
            assert after["tasks"] == before["tasks"]
            assert all(path.read_bytes() == content for path, content in pdfs.items())
            return
        assert status == 200, continued
        assert continued["active_task_id"] == original["id"]
        assert continued["current_recommendation_id"] == waiting["current_recommendation_id"]
        if resolve_location:
            assert continued["status"] == "matching", continued
        else:
            deadline = time.monotonic() + 3
            while time.monotonic() < deadline:
                _, continued = request(address, "GET", "/api/pipeline/state")
                if continued["control"] == "paused":
                    break
                time.sleep(0.02)
            assert continued["status"] == "needs_input", continued
            assert continued["wait_reason"] == "application_country_required"
            assert continued["resume_status"] == "generating_resume"
        _, after = request(address, "GET", "/api/flow/state")
        assert len(after["tasks"]) == 1
        current = after["active_task"]
        if resolve_location:
            assert current["input_epoch"] == original.get("input_epoch", 0) + 1
            assert current["job_binding"] != original["job_binding"]
            assert current["stages"]["analysis"]["status"] in {"queued", "running", "complete"}
            assert current["stages"]["resume"] == {"status": "pending"}
            assert current["stages"]["export"] == {"status": "pending"}
            assert current["resume_id"] is None and current["resume_sha256"] is None
            assert current["materials_confirmed"] is False
        else:
            assert after["tasks"] == before["tasks"]
        assert all(path.read_bytes() == content for path, content in pdfs.items())
        # The resolved case stops here, before later generation/filling ticks.
