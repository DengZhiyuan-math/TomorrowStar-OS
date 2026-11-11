"""Saved pre-JSON task resumes through HTTP, strict binding and a child worker.

Current JSON-only creation is covered by the J08 combinations.
"""

from __future__ import annotations

import hashlib
import json
import os
import signal
import subprocess
import sys
import time
from contextlib import suppress
from pathlib import Path
from threading import Thread
from types import SimpleNamespace

import pytest
from legacy_full_latex_support import LegacyFullLatexFixtureStore
from test_career_portal_http import Portal

from career_evidence_graph.career_portal import create_server

pytestmark = pytest.mark.worker_browser
CHECKOUT = Path(__file__).resolve().parents[1]
PDF = (CHECKOUT / "tests/fixtures/pdf-export/current-template.pdf").read_bytes()


class LegacySingleJourney:
    def __init__(self, root):
        self.root = root
        self.controller = "single-flow-integration-controller"
        self.children = []
        self.server = None
        self.last_heartbeat = 0
        self.exports = []
        self.open()

    def open(self):
        def resume_factory(applications, catalog, directory):
            def compile_pdf(binding):
                self.exports.append(binding)
                return {
                    "build": {"main": binding["main"], "exit": 0, "pdf_updated": True},
                    "pdf": PDF,
                }

            # Default CLI generation; only the compiler returns a static real PDF.
            return LegacyFullLatexFixtureStore(
                applications,
                catalog,
                directory,
                prism_client=SimpleNamespace(
                    configuration=lambda: {"synthetic": "latex-compiler-boundary"},
                    compile=compile_pdf,
                ),
            )

        self.server = create_server(
            self.root / "applications",
            self.root / "career",
            write_admission_policy="development",
            flow_root=self.root / "runtime/single-job-flow",
            worker_root=self.root / "runtime/single-job-worker",
            flow_resume_factory=resume_factory,
            worker_fixtures=True,
            worker_headless=True,
        )
        self.thread = Thread(
            target=self.server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True
        )
        self.thread.start()
        self.portal = Portal(self.server, self.root / "applications", self.root / "career")

    def request(self, method, path, payload=None):
        status, _, raw = self.portal.request(
            method,
            path,
            body=json.dumps(payload).encode() if payload is not None else None,
            headers=self.portal.write_headers() if payload is not None else None,
        )
        assert status in {200, 201}, raw
        return json.loads(raw)

    def state(self):
        return self.request("GET", "/api/flow/state")

    def action(self, action, **payload):
        task = self.state()["active_task"]
        return self.request(
            "POST",
            "/api/flow/" + action,
            {"task_id": task["id"], "task_revision": task["revision"], **payload},
        )

    def worker(self, operation, **payload):
        if operation in {"resume", "pause", "heartbeat"}:
            payload["controller"] = self.controller
        result = self.action("worker-action", operation=operation, payload=payload)
        if operation in {"resume", "heartbeat"}:
            self.last_heartbeat = time.monotonic()
        process = self.server.worker_service.process
        if process is not None and process not in self.children:
            self.children.append(process)
        return result

    def wait(self, condition, timeout=30):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            state = self.state()
            task = state["active_task"]
            failures = [row for row in task["stages"].values() if row["status"] == "failed"]
            assert not failures, failures
            worker = state["worker"]
            assert not worker.get("worker_error"), worker.get("worker_error")
            if condition(state):
                return state
            if worker.get("control") == "running" and time.monotonic() - self.last_heartbeat >= 1:
                self.worker("heartbeat")
            time.sleep(0.05)
        pytest.fail("Single-flow deadline: " + json.dumps(state, ensure_ascii=False))

    def events(self):
        return json.loads((self.root / "runtime/single-job-worker/fixture-events.json").read_text())

    def close_backend(self):
        if self.server is None:
            return
        server, self.server = self.server, None
        process = server.worker_service.process
        if process is not None and process not in self.children:
            self.children.append(process)
        server.shutdown()
        self.thread.join(timeout=5)
        server.server_close()
        assert not self.thread.is_alive()

    def close(self):
        try:
            self.close_backend()
        finally:
            for process in self.children:
                if process.poll() is None:
                    with suppress(ProcessLookupError):
                        os.killpg(process.pid, signal.SIGTERM)
                    try:
                        process.wait(timeout=10)
                    except subprocess.TimeoutExpired:
                        with suppress(ProcessLookupError):
                            os.killpg(process.pid, signal.SIGKILL)
                        process.wait(timeout=5)
                assert process.poll() is not None
        report_path = self.root / "integration-result.json"
        if report_path.is_file():
            report = json.loads(report_path.read_text())
            report.update(
                result="passed",
                cleanup={
                    "owned_worker_children_reaped": True,
                    "exit_codes": [process.returncode for process in self.children],
                    "backend_thread_joined": not self.thread.is_alive(),
                },
            )
            report_path.write_text(json.dumps(report, indent=2) + "\n")


@pytest.fixture
def single_journey(tmp_path, monkeypatch):
    root = tmp_path / "single-flow"
    result = subprocess.run(
        [sys.executable, str(CHECKOUT / "scripts/create_synthetic_flow.py"), str(root)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    monkeypatch.setenv("TOMORROWSTAR_CODEX_EXECUTABLE", str(root / "codex-fixture"))
    monkeypatch.setenv("PLAYWRIGHT_BROWSERS_PATH", "0")
    monkeypatch.setenv("HOME", str(root / "home"))
    monkeypatch.setenv("TMPDIR", str(root / "tmp"))
    journey = LegacySingleJourney(root)
    try:
        yield journey
    finally:
        journey.close()


def test_retained_legacy_single_flow_reaches_real_fixture_review_without_submit(single_journey):
    journey = single_journey
    # Contact facts must already be part of the PDF's material binding.
    for question, value in (
        ("Full name", "Synthetic Person"),
        ("Email address", "synthetic@example.invalid"),
    ):
        journey.server.worker_service.store.answers.put_answer(
            {"question": question, "value": value, "scope": {}, "state": "confirmed"}
        )
    application = journey.portal.state()["applications"][0]
    application = journey.request(
        "PATCH",
        "/api/applications/" + application["id"],
        {"revision": application["revision"], "job_description": "Python\nunit tests"},
    )["application"]
    task = journey.request(
        "POST",
        "/api/flow/create",
        {"application_id": application["id"], "application_revision": application["revision"]},
    )
    flow = journey.server.application_flow_service
    # Replay an explicitly saved pre-JSON task, without changing new-task creation.
    with flow.applications.write_lock():
        saved = flow._load()
        flow._task(saved, task["id"]).pop("material_contract", None)
        flow._save(saved)
    for stage, status in (
        ("analysis", "analysis_ready"),
        ("resume", "draft_ready"),
        ("export", "materials_ready"),
    ):
        if stage == "resume":
            current = journey.state()["active_task"]
            flow.prepare_automatic_materials(
                current["id"], current["revision"], str(journey.root / "latex-base"), "main.tex"
            )
        journey.action("start", stage=stage)
        completed = journey.wait(
            lambda state, expected=status: state["active_task"]["status"] == expected
        )
        task = completed["active_task"]
    assert task["materials_confirmed"] is True
    journey.action("prepare-worker", country="CHE", send_confirmed=True)
    prepared = journey.state()
    assert prepared["worker"]["control"] == "paused"
    assert journey.server.worker_service.process is None
    assert journey.events()["uploads"] == []
    assert prepared["active_task"]["resume_sha256"] == hashlib.sha256(PDF).hexdigest()

    journey.worker("resume")
    waiting = journey.wait(lambda state: state["active_task"]["status"] == "needs_input")
    assert journey.children and journey.children[0].poll() is None
    assert waiting["worker"]["runtime_status"]["source_matches_disk"] is True
    assert waiting["worker"]["cua_enabled"] is False
    assert waiting["worker"]["live_enabled"] is False
    assert {row["question"] for row in waiting["worker"]["input_items"]} == {
        "Will you now or in the future require visa sponsorship?",
    }
    fills_before_pause = [
        row for row in waiting["worker"]["jobs"][0]["observations"] if row["action"] == "fill"
    ]
    uploaded_before_pause = journey.events()["uploads"]
    assert uploaded_before_pause == [
        {"id": application["id"], "sha256": hashlib.sha256(PDF).hexdigest(), "size": len(PDF)}
    ]
    journey.worker("pause")
    values = {
        "name": "Synthetic Person",
        "email": "synthetic@example.invalid",
        "sponsorship": "Yes",
    }
    for item in waiting["worker"]["input_items"]:
        question = item["jobs"][0]["question_id"]
        journey.worker("answer", question_id=question, value=values[question], scope=item["scope"])
    assert journey.state()["worker"]["control"] == "paused"
    heartbeat = journey.state()["worker"]["worker_heartbeat"]
    paused = journey.wait(lambda state: state["worker"]["worker_heartbeat"] > heartbeat)
    assert [
        row for row in paused["worker"]["jobs"][0]["observations"] if row["action"] == "fill"
    ] == fills_before_pause
    assert journey.events()["uploads"] == uploaded_before_pause
    journey.worker("resume")
    ready = journey.wait(lambda state: state["active_task"]["status"] == "ready_for_review")
    job = ready["worker"]["jobs"][0]
    assert job["file_sha256"] == hashlib.sha256(PDF).hexdigest()
    assert job["page_current"] is True
    fills = [row for row in job["observations"] if row["action"] == "fill" and row["verified"]]
    library = {row["key"]: row for row in ready["worker"]["library"]}
    readback = {}
    for row in fills:
        reference = row["intent"]["answer_ref"]
        answer = library[reference["key"]]
        assert answer["state"] == "confirmed"
        assert answer["content_revision"] == reference["revision"]
        readback[row["field_id"]] = answer["value"]
    assert readback == {
        "name": "Synthetic Person",
        "email": "synthetic@example.invalid",
        "sponsorship": "Yes",
    }
    assert journey.events()["uploads"] == [
        {"id": application["id"], "sha256": hashlib.sha256(PDF).hexdigest(), "size": len(PDF)}
    ]
    assert journey.events()["submissions"] == []
    assert len(journey.exports) == 1

    # Reopening observes the retained child and page; it never starts another run.
    journey.worker("pause")
    before = journey.state()
    previous_task = before["active_task"]
    previous_worker = before["worker"]
    previous_job = previous_worker["jobs"][0]
    previous_events = journey.events()
    flow_root = journey.root / "runtime/single-job-flow"
    model_files = sorted(flow_root.rglob("model-result.json"))
    assert len(model_files) == 2
    model_bytes = {path: path.read_bytes() for path in model_files}
    for path in model_files:
        trace = json.loads(path.read_text())["raw_stdout_jsonl"]
        events = [json.loads(line) for line in trace.splitlines()]
        assert events[0] == {"type": "synthetic_fixture", "synthetic": True, "new_model_calls": 0}
    status, _, raw_pdf = journey.portal.request(
        "GET", f"/api/flow/resumes/{previous_task['resume_id']}/pdf"
    )
    assert status == 200 and raw_pdf == PDF
    journey.close_backend()
    assert journey.children[0].poll() is None
    journey.open()
    reopened = journey.wait(lambda state: state["worker"]["jobs"][0]["page_current"])
    for key in ("id", "analysis_id", "resume_id", "resume_sha256", "inputs", "artifacts"):
        assert reopened["active_task"][key] == previous_task[key]
    assert reopened["active_task"]["materials_confirmed"] is True
    assert reopened["worker"]["batch_id"] == previous_worker["batch_id"]
    assert reopened["worker"]["runtime"]["id"] == previous_worker["runtime"]["id"]
    assert reopened["worker"]["worker_pid"] == journey.children[0].pid
    assert reopened["worker"]["control"] == "paused"
    assert journey.server.worker_service.process is None
    assert (
        reopened["worker"]["jobs"][0]["page_observation"]["page_id"]
        == previous_job["page_observation"]["page_id"]
    )
    assert reopened["worker"]["jobs"][0]["observations"] == previous_job["observations"]
    assert journey.events() == previous_events
    assert len(journey.exports) == 1
    assert sorted(flow_root.rglob("model-result.json")) == model_files
    assert all(path.read_bytes() == raw for path, raw in model_bytes.items())
    status, _, reopened_pdf = journey.portal.request(
        "GET", f"/api/flow/resumes/{previous_task['resume_id']}/pdf"
    )
    assert status == 200 and reopened_pdf == PDF
    journey.worker("resume")
    deadline = time.monotonic() + 1.2
    while time.monotonic() < deadline:
        journey.worker("heartbeat")
        retained = journey.state()
        assert retained["active_task"]["status"] == "ready_for_review"
        assert retained["worker"]["jobs"][0]["page_current"] is True
        assert retained["worker"]["runtime"]["id"] == previous_worker["runtime"]["id"]
        assert retained["worker"]["worker_pid"] == journey.children[0].pid
        assert journey.events() == previous_events
        time.sleep(0.1)
    assert journey.server.worker_service.process is None
    assert len(journey.children) == 1
    assert len(journey.exports) == 1
    (journey.root / "integration-result.json").write_text(
        json.dumps(
            {
                "result": "assertions_passed; cleanup pending",
                "transport": "real-loopback-http",
                "model_transport": "default run_codex_exec subprocess; synthetic CLI fixture",
                "pdf_exporter": "fixed-byte double; no system Chrome",
                "worker": "default spawned child; bundled headless Chromium; no Cua",
                "single_binding_validator": "production default in independent child",
                "verified_fields": readback,
                "pause_and_reopen": (
                    "same task, analysis, PDF, batch, run, PID and page; no reupload"
                ),
                "worker_pid": journey.children[0].pid,
                "worker_run_id": previous_worker["runtime"]["id"],
                "worker_source": previous_worker["runtime"]["source"],
                "pdf_sha256": previous_task["resume_sha256"],
                "uploads": len(previous_events["uploads"]),
                "automatic_final_submissions": len(previous_events["submissions"]),
                "real_model_calls": 0,
                "real_ats_calls": 0,
                "personal_data_used": False,
            },
            indent=2,
        )
        + "\n"
    )
