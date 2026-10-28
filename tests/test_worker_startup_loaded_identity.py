"""A fresh worker records its complete loaded role before opening a browser."""

import json
import subprocess
import sys
from pathlib import Path


def test_fresh_worker_main_records_complete_loaded_identity_before_browser(tmp_path):
    source = Path(__file__).resolve().parents[1] / "src"
    probe = """
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, sys.argv[1])
from career_evidence_graph import application_worker_browser as browser
from career_evidence_graph.loaded_code import loaded_runtime_revision

def deny_external_actions(event, arguments):
    if event in {"socket.connect", "socket.bind", "subprocess.Popen", "os.system"}:
        raise AssertionError("Worker startup must stop before external actions")

def stop_before_browser():
    raise browser.Error("bounded_startup_probe")

sys.addaudithook(deny_external_actions)
root = Path(sys.argv[2])
applications = root / "applications"
applications.mkdir()
runtime = root / "runtime"
browser.sync_playwright = stop_before_browser
result = browser.main([
    "--applications", str(applications),
    "--runtime", str(runtime),
    "--fixture-origin", "http://127.0.0.1:9999",
])
state = browser.WorkerStore(browser.ApplicationStore(applications), runtime).load()
print(json.dumps({
    "exit_code": result,
    "pid": os.getpid(),
    "state": state,
    "loaded_identity": loaded_runtime_revision("worker"),
    "readiness_loaded": "career_evidence_graph.application_readiness" in sys.modules,
    "single_binding_loaded": "career_evidence_graph.application_single_binding" in sys.modules,
    "fixed_source_loaded": "career_evidence_graph.application_experience_latex" in sys.modules,
    "controller_loaded": "career_evidence_graph.career_portal" in sys.modules,
    "preparation_loaded": "career_evidence_graph.application_preparation" in sys.modules,
}))
"""
    result = subprocess.run(
        [sys.executable, "-I", "-B", "-c", probe, str(source), str(tmp_path)],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
    measured = json.loads(result.stdout.splitlines()[-1])
    state = measured["state"]
    runtime = state["runtime"]
    assert measured["exit_code"] == 2
    assert state["worker_error"] == "Error" and state["control"] == "paused"
    assert state["jobs"] == [] and state["commands"] == []
    assert runtime["id"] and runtime["pid"] == state["worker_pid"] == measured["pid"]
    assert runtime["applications_root"] == str(tmp_path / "applications")
    assert runtime["loaded_engine_revision"] is not None
    assert runtime["loaded_engine_revision"].startswith("python-loaded-code/v1:worker:")
    assert runtime["loaded_engine_revision"] == measured["loaded_identity"]
    assert measured["readiness_loaded"] and measured["single_binding_loaded"]
    assert measured["fixed_source_loaded"]
    assert not measured["controller_loaded"]
    # MC-20: the worker role covers its full static import closure, so preparation code
    # is loaded (measured, not run) before the identity is recorded.
    assert measured["preparation_loaded"]
    assert "current_build" not in runtime
    assert not (tmp_path / "runtime/browser-profile").exists()


def test_recorded_worker_identity_matches_the_packaged_build_measurement(tmp_path):
    # MC-20: the installed App compares the running worker's recorded identity with the build
    # measurement (macos/build.py), so the two separate processes must agree. Stop at
    # Playwright's own context manager: rebinding a worker module name would change the identity.
    source = Path(__file__).resolve().parents[1] / "src"
    worker = """
import sys
from pathlib import Path

sys.path.insert(0, sys.argv[1])
from playwright.sync_api._context_manager import PlaywrightContextManager
from career_evidence_graph import application_worker_browser as browser

def stop_before_browser(self):
    raise browser.Error("bounded_startup_probe")

PlaywrightContextManager.__enter__ = stop_before_browser
applications = Path(sys.argv[2]) / "applications"
applications.mkdir()
runtime = Path(sys.argv[2]) / "runtime"
browser.main(["--applications", str(applications), "--runtime", str(runtime),
              "--fixture-origin", "http://127.0.0.1:9999"])
state = browser.WorkerStore(browser.ApplicationStore(applications), runtime).load()
print(state["runtime"]["loaded_engine_revision"])
"""
    build = (
        "import sys; sys.path.insert(0, sys.argv[1]); "
        "from career_evidence_graph.loaded_code import measure_packaged_roles; "
        "print(measure_packaged_roles(worker_first=sys.argv[2] == 'worker-first')['worker'])"
    )

    def run(*arguments):
        return subprocess.run(
            [sys.executable, "-I", "-B", "-c", *arguments],
            cwd=tmp_path,
            capture_output=True,
            text=True,
            timeout=60,
            check=True,
        ).stdout.splitlines()[-1]

    recorded = run(worker, str(source), str(tmp_path))
    assert recorded.startswith("python-loaded-code/v1:worker:")
    assert recorded == run(build, str(source), "worker-first") == run(build, str(source), "")
