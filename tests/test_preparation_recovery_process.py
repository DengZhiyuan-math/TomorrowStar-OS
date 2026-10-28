"""Real isolated backend exits retain synthetic preparation checkpoints."""

import json
import os
import select
import signal
import subprocess
import sys
from contextlib import contextmanager
from http.client import HTTPConnection
from pathlib import Path
from urllib.parse import urlsplit

import pytest
from test_application_flow import application as application
from test_career_portal_http import portal as portal

from career_evidence_graph.application_flow import ApplicationFlowService, digest
from career_evidence_graph.career_portal_data import ApplicationStore


def test_killed_analysis_process_reopens_paused_with_original_attempt_and_inputs(
    application, tmp_path
):
    applications, job = application
    root = tmp_path / "preparation"
    child = """
import json,sys,threading
from pathlib import Path
sys.path.insert(0,sys.argv[1])
from career_evidence_graph.application_flow import ApplicationFlowService
from career_evidence_graph.career_portal_data import ApplicationStore
def analyze(task):
    print(json.dumps(task),flush=True)
    threading.Event().wait()
store=ApplicationStore(Path(sys.argv[2]))
flow=ApplicationFlowService(store,Path(sys.argv[3]),preparation_only=True,
    callbacks={"analysis":analyze})
job=store.get_application(sys.argv[4])
batch=flow.request("batch-create",{"request_id":"1"*32,
    "items":[{"kind":"application","id":job["id"],"revision":job["revision"]}]})
flow.request("batch-control",{"batch_id":batch["id"],
    "batch_revision":batch["revision"],"operation":"resume"})
threading.Event().wait()
"""
    process = subprocess.Popen(
        [
            sys.executable,
            "-I",
            "-B",
            "-u",
            "-c",
            child,
            str(Path(__file__).parents[1] / "src"),
            str(applications.root),
            str(root),
            job["id"],
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        assert select.select([process.stdout], [], [], 10)[0], "analysis did not start"
        original = json.loads(process.stdout.readline())
        process.kill()
        assert process.wait(timeout=5) == -signal.SIGKILL
        assert process.stderr.read() == ""
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=5)
        process.stdout.close()
        process.stderr.close()

    calls = []
    reopened = ApplicationFlowService(
        applications,
        root,
        preparation_only=True,
        callbacks={"analysis": lambda task: calls.append(task)},
    )
    try:
        state = reopened.snapshot()
        task = state["active_task"]
        assert task["id"] == original["id"]
        assert task["inputs"] == original["inputs"]
        assert task["job_binding"] == original["job_binding"]
        assert task["status"] == "failed" and task["analysis_id"] is None
        assert state["preparation_batch"]["control"] == "paused"
        assert state["preparation_batch"]["items"][0]["status"] == "deferred"
        event = task["recovery_history"][-1]
        assert event["stage"] == "analysis" and event["previous_status"] == "running"
        assert event["attempt_id"] == original["stages"]["analysis"]["attempt_id"]
        assert event["inputs_revision"] == digest(original["inputs"])
        assert event["input_epoch"] == original["input_epoch"]
        assert reopened.snapshot()["active_task"] == task and calls == []
    finally:
        reopened.close()


@contextmanager
def native_backend(portal, root, tmp_path):
    code = """
import runpy,sys
module=runpy.run_path(sys.argv.pop(1))
module['main'].__globals__['find_codex_executable']=lambda configured:None
raise SystemExit(module['main']())
"""
    environment = os.environ | {"CODEX_HOME": str(tmp_path / "synthetic-codex")}
    for key in ("CODEX_API_KEY", "OPENAI_API_KEY", "TOMORROWSTAR_CODEX_EXECUTABLE"):
        environment.pop(key, None)
    process = subprocess.Popen(
        [
            sys.executable,
            "-I",
            "-B",
            "-u",
            "-c",
            code,
            str(Path(__file__).parents[1] / "macos/server.py"),
            "--applications",
            str(portal.applications),
            "--career-workspace",
            str(portal.career),
            "--flow-root",
            str(root),
            "--information-library-root",
            str(tmp_path / "synthetic-information"),
        ],
        env=environment,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        assert select.select([process.stdout], [], [], 10)[0], "backend did not start"
        ready = json.loads(process.stdout.readline())
        assert ready["status"] == "ready" and ready["capabilities"]["worker"] is False
        address = urlsplit(ready["url"])
        assert address.hostname == "127.0.0.1" and address.fragment == "flow"
        yield process, address
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=5)
        for pipe in (process.stdin, process.stdout, process.stderr):
            pipe.close()


def native_state(address):
    connection = HTTPConnection(address.hostname, address.port, timeout=5)
    try:
        connection.request("GET", "/api/flow/state")
        response = connection.getresponse()
        assert response.status == 200
        return json.loads(response.read())
    finally:
        connection.close()


@pytest.mark.parametrize("exit_kind", ["parent-eof", "sigterm", "sigkill"])
def test_native_backend_exit_and_reopen_retains_saved_results_without_work(
    portal, tmp_path, exit_kind
):
    applications = ApplicationStore(portal.applications)
    job = applications.create_application(
        {
            "company": "Synthetic Lifecycle",
            "role_title": "Python Engineer",
            "job_description": "Build reliable Python services.",
        }
    )
    root = tmp_path / "preparation"
    service = ApplicationFlowService(
        applications,
        root,
        preparation_only=True,
        callbacks={"analysis": lambda task: {"id": "retained-analysis", "requirements": []}},
    )
    from test_application_flow import wait_for

    try:
        task = service.create(job["id"], job["revision"])
        service.start(task["id"], task["revision"], "analysis")
        saved = wait_for(service, task["id"], lambda row: row["status"] == "analysis_ready")
    finally:
        service.close()
    history = {p: p.read_bytes() for p in (root / "snapshots").rglob("*.json")}
    note_before = {p: p.read_bytes() for p in portal.applications.rglob("*") if p.is_file()}
    with native_backend(portal, root, tmp_path) as (process, address):
        first = native_state(address)
        assert first["active_task"] == saved
        assert first["worker"] == {"enabled": False}
        if exit_kind == "parent-eof":
            process.stdin.close()
        elif exit_kind == "sigterm":
            process.terminate()
        else:
            process.kill()
        exit_code = process.wait(timeout=5)
        diagnostics = process.stderr.read()
        assert exit_code == (-signal.SIGKILL if exit_kind == "sigkill" else 0), diagnostics
        assert diagnostics == ""
    with native_backend(portal, root, tmp_path) as (process, address):
        restored = native_state(address)
        assert restored["active_task"] == saved
        assert restored["tasks"] == first["tasks"]
        assert restored["runtime"]["session_id"] != first["runtime"]["session_id"]
        assert restored["runtime"]["engine_revision"] == first["runtime"]["engine_revision"]
        assert restored["runtime"]["mode"] == "preparation"
        assert native_state(address)["active_task"] == saved
        process.stdin.close()
        assert process.wait(timeout=5) == 0
        assert process.stderr.read() == ""
    assert all(p.read_bytes() == value for p, value in history.items())
    assert {p: p.read_bytes() for p in portal.applications.rglob("*") if p.is_file()} == note_before
