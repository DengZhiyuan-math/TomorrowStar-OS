"""MC-15: the App and Codex callers keep their exact endpoints, fields and exit codes."""

import json
import re
import subprocess
import sys
import time
from pathlib import Path

import pytest
from test_career_portal_http import _running_portal
from test_pipeline_takeover_chain import _job, _turn, _until
from test_pipeline_takeover_chain import chain as chain
from test_runtime_assembly import roots as roots
from test_single_application_worker import single_worker as single_worker
from test_worker_assistance_return_service import COUNTRY_CLICK, make_report, select_country
from test_worker_assistance_return_service import returning as returning
from test_worker_codex_assistance import block
from test_worker_codex_assistance import retained_assistance_page as retained_assistance_page
from test_worker_native_takeover import native_page as native_page

from career_evidence_graph._vendor import job_apply_store as helper
from career_evidence_graph.application_pipeline import POLICY, PROTOCOL, ApplicationPipeline
from career_evidence_graph.career_portal import _STATIC
from career_evidence_graph.career_portal_data import ApplicationStore
from career_evidence_graph.validation.hashing import record_digest as digest

ROOT = Path(__file__).resolve().parents[1]
APP = (ROOT / "macos/App.swift").read_text()
# PipelineStatus.decode: statuses on which the App accepts a persistent notification.
APP_NOTIFICATION_STATUSES = {
    "ready_for_review",
    "needs_input",
    "needs_recheck",
    "blocked",
    "cancelled",
    "expired",
    "paused",
    "interrupted",
    "no_matches",
}
TAKEOVER_NOTICE = {
    "kind": "takeover",
    "title": "已交给 Codex 接续",
    "message": "已自动交给 Codex 接续原页",
}


def app_decodes(raw: bytes) -> bool:
    """Python mirror of App.swift PipelineStatus.decode; the Swift source stays unchanged."""
    value = json.loads(raw)
    if not (
        len(raw) <= 65536
        and value.get("protocol") == "application-pipeline/v1"
        and value.get("control") in {"running", "paused"}
        and isinstance(value.get("status"), str)
        and value["status"]
        and "notification" in value
    ):
        return False
    notice = value["notification"]
    return notice is None or (
        value["status"] in APP_NOTIFICATION_STATUSES
        and all(
            isinstance(notice.get(key), str) and 0 < len(notice[key]) <= limit
            for key, limit in (("id", 200), ("title", 200), ("message", 1000))
        )
    )


def test_app_swift_inventory_is_unchanged():
    assert set(re.findall(r'"(/api/[a-z0-9./-]+)"', APP)) == {
        "/api/pipeline/state",
        "/api/export.csv",
    }
    assert '"application-pipeline/v1"' in APP and PROTOCOL == "application-pipeline/v1"
    statuses = re.search(r'guard \[("ready_for_review".*?)\]\.contains\(status\)', APP, re.S)
    assert set(re.findall(r'"([a-z_]+)"', statuses.group(1))) == APP_NOTIFICATION_STATUSES
    allowed = re.search(r"let allowed = \[(.*?)\]", APP).group(1)
    server = (ROOT / "macos/server.py").read_text()
    emitted = set(re.findall(r'"code": "([a-z-]+)"', server))
    # Recorded gap: --codex-assist outside the single-job flow reaches the App as its
    # generic invalid_ready_response message; App.swift stays unchanged in MC-15.
    assert emitted - set(re.findall(r'"([a-z-]+)"', allowed)) == {"single-flow-required"}


def test_app_endpoints_serve_the_decoded_pipeline_and_export(tmp_path):
    applications = tmp_path / "applications"
    applications.mkdir()
    career = tmp_path / "career"
    career.mkdir()
    subprocess.run(["git", "init", "--quiet", str(career)], check=True)
    with _running_portal(
        applications, career, flow_root=tmp_path / "flow", worker_root=tmp_path / "worker"
    ) as active:
        status, _, raw = active.request("GET", "/api/pipeline/state")
        assert status == 200 and app_decodes(raw)
        value = json.loads(raw)
        assert value["notification"] is None and value["notice"] is None
        status, headers, _ = active.request("GET", "/api/export.csv")
        assert status == 200 and headers["Content-Type"].startswith("text/csv")


class _Flow:
    def __init__(self, root, applications):
        self.root, self.applications, self.callbacks = root, applications, {}

    def snapshot(self, task_id=None):
        return {"tasks": [], "active_task": None}


class _Intake:
    def snapshot(self):
        return {"recommendations": []}


def _pipeline_record(root, **fields):
    record = {
        "schemaVersion": 1,
        "protocol": PROTOCOL,
        "policy_version": POLICY,
        "control": "paused",
        "status": "idle",
        "id": None,
        "request_id": None,
        "intake_run_id": None,
        "items": [],
        "active_task_id": None,
        "notification": None,
        "authorization": None,
        "transmission_authorization": None,
    } | fields
    record["revision"] = digest(record)
    helper.atomic_write_json(root / "pipeline.json", record)


def test_wait_notification_is_the_page_notice(tmp_path):
    applications = tmp_path / "applications"
    applications.mkdir()
    root = tmp_path / "flow"
    root.mkdir()
    notification = {
        "id": "n1",
        "status": "needs_input",
        "title": "自动流程需要处理",
        "message": "请补充电话号码。",
        "task_id": None,
        "at": time.time(),
    }
    _pipeline_record(root, status="needs_input", notification=notification)
    pipeline = ApplicationPipeline(
        _Flow(root, ApplicationStore(applications)), _Intake(), None, interval=3600
    )
    try:
        state = pipeline.snapshot()
        assert state["notice"] == {
            "kind": "wait",
            "title": notification["title"],
            "message": notification["message"],
        }
        assert state["notification"] == notification
        assert app_decodes(json.dumps(state).encode())
    finally:
        pipeline.close()


def test_running_takeover_is_a_page_notice_only_while_it_holds_the_job(chain):
    worker, pipeline = chain.service, chain.pipeline
    assert pipeline.snapshot()["notice"] is None
    with worker.store.applications.write_lock():
        block(worker, "unsupported_control", field="country")
    _until(lambda: (_job(chain).get("assistance") or {}).get("status") == "claimed")
    state = _until(lambda: (s := pipeline.snapshot())["notice"] and s)
    # The App's Dock notification stays empty; only the page shows the takeover.
    assert state["notice"] == TAKEOVER_NOTICE
    assert state["notification"] is None and app_decodes(json.dumps(state).encode())
    # Codex returns the segment to the script; the released takeover is no notice.
    _turn(chain, planned=COUNTRY_CLICK, effect=select_country, report=make_report())
    chain.runner.tick()
    assert _job(chain)["assistance"]["status"] == "released"
    after = pipeline.snapshot()
    assert after["takeover_request"]["title"] == TAKEOVER_NOTICE["title"]
    assert after["notice"] is None


HANDOFF = [sys.executable, str(ROOT / "scripts/run_codex_handoff.py")]


def _handoff(tmp_path, *arguments):
    applications = tmp_path / "applications"
    applications.mkdir(exist_ok=True)
    command = [*HANDOFF, "--applications", str(applications), "--root", str(tmp_path / "root")]
    return subprocess.run([*command, *arguments], capture_output=True, text=True, timeout=30)


def test_handoff_cli_keeps_exit_codes_and_error_shape(tmp_path):
    result = _handoff(tmp_path, "snapshot")
    assert result.returncode == 0, result.stderr
    snapshot = json.loads(result.stdout)
    assert snapshot["execution_lane"] == "codex" and snapshot["active_task"] is None
    assert {"schemaVersion", "tasks", "enabled", "library", "applications_root"} <= set(snapshot)
    request = tmp_path / "request.json"
    request.write_text("{}")
    refused = _handoff(tmp_path, "claim", "--request", str(request))
    assert refused.returncode == 1 and refused.stdout == ""
    error = json.loads(refused.stderr)
    assert set(error) == {"error", "message"} and error["error"] != "handoff_unavailable"
    missing = _handoff(tmp_path, "claim", "--request", str(tmp_path / "missing.json"))
    assert missing.returncode == 1
    assert json.loads(missing.stderr)["error"] == "handoff_unavailable"
    assert _handoff(tmp_path, "snapshot", "--request", str(request)).returncode == 2
    assert _handoff(tmp_path, "claim").returncode == 2


def test_synthetic_start_settings_apply_before_the_pipeline_starts(roots, monkeypatch):
    from career_evidence_graph import application_pipeline
    from career_evidence_graph.application_runtime import open_runtime

    applications, career, flow_root, worker_root = roots
    seen = {}
    original = application_pipeline.ApplicationPipeline.__init__

    def observe(self, flow, intake, worker, **options):
        seen.update(base=flow.callbacks.get("automatic_latex_base"))
        original(self, flow, intake, worker, **options)

    monkeypatch.setattr(application_pipeline.ApplicationPipeline, "__init__", observe)

    def base(_task):
        return None

    runtime = open_runtime(
        applications,
        career,
        static_root=_STATIC,
        static_files={},
        flow_root=flow_root,
        worker_root=worker_root,
        resume_model_mode="synthetic",
        flow_automatic_latex_base=base,
    )
    try:
        assert runtime.pipeline is not None and seen["base"] is base
        assert runtime.flow.callbacks["automatic_latex_base"] is base
        assert runtime.flow_resumes.model_mode == "synthetic"
    finally:
        runtime.close()


@pytest.mark.parametrize(
    "options",
    [
        {"resume_model_mode": "real"},
        {"flow_automatic_latex_base": "not-callable"},
        {"flow_automatic_latex_base": lambda _task: None, "flow_root": None},
    ],
)
def test_synthetic_start_settings_are_checked_before_construction(roots, options):
    from career_evidence_graph.application_runtime import open_runtime

    applications, career, flow_root, worker_root = roots
    arguments = {"flow_root": flow_root, "worker_root": worker_root} | options
    with pytest.raises(ValueError, match="synthetic"):
        open_runtime(applications, career, static_root=_STATIC, static_files={}, **arguments)
    assert not flow_root.exists() and not worker_root.exists()
