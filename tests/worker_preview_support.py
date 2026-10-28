"""Shared synthetic HTTP and process harness for the two ATS browser suites."""

from __future__ import annotations

import base64
import json
import os
import signal
import subprocess
import time
from contextlib import contextmanager, suppress
from http.client import HTTPConnection
from pathlib import Path
from threading import Thread

import pytest

from career_evidence_graph.career_portal import create_server
from career_evidence_graph.career_portal_data import ApplicationStore


class Preview:
    def __init__(self, server, root: Path):
        self.server, self.root = server, root
        self.origin = f"http://127.0.0.1:{server.server_port}"
        self.worker = server.worker_service
        self.store = self.worker.store
        self.token = self.get("/api/state")["csrf_token"]
        self.controller = "synthetic-test-controller"

    def get(self, path: str) -> dict:
        connection = HTTPConnection("127.0.0.1", self.server.server_port, timeout=10)
        try:
            connection.request("GET", path)
            response = connection.getresponse()
            assert response.status == 200
            return json.loads(response.read())
        finally:
            connection.close()

    def post(self, action: str, **payload) -> dict:
        connection = HTTPConnection("127.0.0.1", self.server.server_port, timeout=10)
        try:
            connection.request(
                "POST",
                "/api/worker/" + action,
                json.dumps(payload).encode(),
                {
                    "Origin": self.origin,
                    "Content-Type": "application/json",
                    "X-CSRF-Token": self.token,
                },
            )
            response = connection.getresponse()
            raw = response.read()
            assert response.status == 200, raw
            return json.loads(raw)
        finally:
            connection.close()

    def wait(self, condition, timeout: float = 20) -> dict:
        until = time.monotonic() + timeout
        while time.monotonic() < until:
            state = self.get("/api/worker/state")
            if state["worker_error"] and state["worker_error"] != "control_connection_lost":
                pytest.fail(self.store.root.joinpath("worker.log").read_text())
            if condition(state):
                return state
            time.sleep(0.1)
        pytest.fail("Worker did not reach expected state: " + json.dumps(state))

    def seed(self, question: str, value: str, scope: dict | None = None) -> None:
        with self.store.applications.write_lock():
            self.store.answers.put_answer(
                {
                    "question": question,
                    "value": value,
                    "scope": scope or {},
                    "state": "confirmed",
                    "source": "synthetic",
                }
            )

    def prepare(self, countries: list[str]) -> list[dict]:
        records = self.store.applications.list_applications()
        items = []
        for record, country in zip(records, countries, strict=True):
            raw = f"%PDF-1.4 Synthetic attachment for {record['id']}".encode()
            items.append(
                {
                    "application_id": record["id"],
                    "revision": record["revision"],
                    "country": country,
                    "filename": "resume.pdf",
                    "file_base64": base64.b64encode(raw).decode(),
                }
            )
        self.post("prepare", jobs=items)
        self.wait(lambda s: s["worker_heartbeat"] > 0)
        return items

    def events(self) -> dict:
        return json.loads((self.store.root / "fixture-events.json").read_text())

    def report(self, name: str, state: dict, checks: list[str]) -> None:
        output = os.environ.get("TS_WORKER_REPORT_DIR")
        if not output:
            return
        destination = Path(output)
        destination.mkdir(parents=True, exist_ok=True)
        report = {
            "mode": "synthetic_independent_worker",
            "round": name,
            "checks": checks,
            "result": "passed",
            "worker_pid": state["worker_pid"],
            "jobs": [
                {
                    key: j[key]
                    for key in (
                        "company",
                        "platform",
                        "status",
                        "reason",
                        "file_sha256",
                        "sync_error",
                    )
                }
                for j in state["jobs"]
            ],
            "uploaded_files": len(self.events()["uploads"]),
            "automatic_final_submissions": len(self.events()["submissions"]),
            "model_calls": 0,
            "real_ats_calls": 0,
        }
        (destination / f"{name}.json").write_text(json.dumps(report, indent=2) + "\n")


def stop_worker(preview: Preview) -> None:
    process = preview.worker.process
    if process:
        with suppress(ProcessLookupError):
            os.killpg(process.pid, signal.SIGTERM)
        process.wait(timeout=10)


def advance_until(service, runner, condition, *, application_id=None, timeout=15):
    """Observe a prepared job until a read-only condition holds on its saved state.

    Keep the real parser clock and sampling interval. Never change control,
    heartbeat, answers or unknown outcomes to make a test progress. Tests for
    no replay and individual dispatcher turns continue to call ``tick`` directly.
    """
    from career_evidence_graph.application_form_state import SAMPLE_INTERVAL

    state = service.store.load()
    identifier = application_id or state["jobs"][0]["application_id"]
    deadline = time.monotonic() + timeout
    while True:
        state = service.store.load()
        job = next(item for item in state["jobs"] if item["application_id"] == identifier)
        if condition(job):
            return job
        if job["status"] in {"needs_input", "needs_recheck", "ready_for_review", "cancelled"}:
            pytest.fail(f"Worker reached a different stop: {job['status']} / {job['reason']}")
        if time.monotonic() >= deadline:
            pytest.fail(f"Worker did not reach expected state: {job['status']} / {job['reason']}")
        runner.tick()
        page = runner.pages.get(identifier)
        if page is not None and not page.is_closed():
            page.wait_for_timeout(SAMPLE_INTERVAL * 1000)
        else:
            runner.pump()


@contextmanager
def running_preview(
    tmp_path: Path,
    count: int,
    platforms: tuple[str, ...] | None = None,
    *,
    cdp_port: int = 0,
    cua: bool = False,
):
    apps, career, runtime = (tmp_path / n for n in ("apps", "career", "worker"))
    apps.mkdir()
    career.mkdir()
    runtime.mkdir()
    subprocess.run(["git", "init", "--quiet", str(career)], check=True)
    (career / ".gitignore").write_text(".career-evidence/raw/\n")
    applications = ApplicationStore(apps)
    platforms = platforms or ("lever",) * count
    assert len(platforms) == count
    for index in range(count):
        url = (
            f"https://jobs.lever.co/synthetic-{index}/00000000-0000-0000-0000-{index:012d}"
            if platforms[index] == "lever"
            else f"https://job-boards.greenhouse.io/synthetic-{index}/jobs/{1000 + index}"
        )
        applications.create_application(
            {
                "company": f"Synthetic {index}",
                "role_title": "Engineer",
                "status": "drafting",
                "url": url,
            }
        )
    server = create_server(
        apps,
        career,
        write_admission_policy="development",
        port=0,
        worker_root=runtime,
        worker_fixtures=True,
        worker_headless=not cua,
        worker_cdp_port=cdp_port,
        worker_cua=cua,
    )
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    preview = Preview(server, tmp_path)
    preview.seed("Full name", "Synthetic Person")
    preview.seed("First Name", "Synthetic")
    preview.seed("Last Name", "Person")
    preview.seed("Email address", "synthetic@example.invalid")
    try:
        yield preview
    finally:
        stop_worker(preview)
        server.shutdown()
        thread.join(10)
        server.server_close()
        server.worker_fixtures.shutdown()
        server.worker_fixtures.server_close()
