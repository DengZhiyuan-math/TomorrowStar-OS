"""MC-15: the page's Flow projection is a Runtime-assembled read with additive fields only."""

import hashlib
import threading
from pathlib import Path

import pytest
from test_application_flow import wait_for
from test_career_portal_http import portal as portal
from test_job_explanation_browser import explanation_portal
from test_pdf_export_http import SyntheticLatexClient, create_authorized_latex, export_payload
from test_preparation_entry import post, snapshot
from test_runtime_assembly import roots as roots

from career_evidence_graph.career_portal import _STATIC
from career_evidence_graph.career_portal_data import ApplicationStore, PortalDataError

ADDITIVE = {"progress", "preparation_activity"}
# /api/flow/state key order recorded from the before-copy (`mc15-projection/before`) served
# on the same one-job, one-task fixture in each mode; the additive keys trail these.
APPLICATION_ORDER = [
    "applications_root",
    "schemaVersion",
    "tasks",
    "enabled",
    "active_task",
    "local_materials",
    "eligibility",
    "runtime_error",
    "mode",
    "capabilities",
    "worker",
]
PREPARATION_ORDER = [
    "applications_root",
    "mode",
    "schemaVersion",
    "tasks",
    "enabled",
    "active_task",
    "local_materials",
    "eligibility",
    "runtime_error",
    "resume_language",
    "preparation_batch",
    "policy_version",
    "explanations",
    "order_mode",
    "order_revision",
    "active_explanation",
    "capabilities",
    "runtime",
    "draft_integrity",
    "pdf_integrity",
    "review_snapshots",
    "prism",
    "preparation",
    "worker",
]
APPLICATION_KEYS = set(APPLICATION_ORDER)
PREPARATION_KEYS = set(PREPARATION_ORDER)


def _open(roots, **options):
    from career_evidence_graph.application_runtime import open_runtime

    applications, career, flow_root, worker_root = roots
    static = {path.name: path.read_bytes() for path in _STATIC.iterdir() if path.is_file()}
    return open_runtime(
        applications,
        career,
        static_root=_STATIC,
        static_files=static,
        flow_root=flow_root,
        **({"worker_root": worker_root} if not options.get("preparation_only") else {}),
        **options,
    )


def _task(runtime, company="Synthetic Employer"):
    job = runtime.applications.create_application(
        {"company": company, "role_title": "Engineer", "job_description": "Build Python services."}
    )
    return runtime.flow.create(job["id"], job["revision"])


def _tree(root: Path) -> dict:
    return {
        str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(root.rglob("*"))
        if path.is_file() and ".git" not in path.relative_to(root).parts
    }


def test_runtime_assembles_flow_view_with_old_keys_and_additive_progress(roots):
    from career_evidence_graph.application_flow_view import FlowView

    runtime = _open(roots)
    try:
        assert isinstance(runtime.flow_view, FlowView)
        task = _task(runtime)
        state = runtime.flow_view.state()
        assert list(state) == [*APPLICATION_ORDER, "progress", "preparation_activity"]
        # Values recorded from the before-copy on the same fixture; codex_cli depends on the host.
        assert {key: state[key] for key in APPLICATION_ORDER[3:9] if key != "active_task"} == {
            "enabled": True,
            "local_materials": False,
            "eligibility": {"status": "analysis_required", "conditions": []},
            "runtime_error": "",
            "mode": "application",
        }
        assert list(state["capabilities"]) == ["codex_cli", "analysis", "resume", "worker"]
        assert state["capabilities"]["worker"] is True
        assert state["worker"] == {"enabled": False}
        # Flow-owned keys equal a fresh snapshot, so the projection adds keys without
        # rewriting or reordering Flow's own values.
        original = runtime.flow.snapshot()
        assert list(original) == APPLICATION_ORDER[:8]
        assert {key: state[key] for key in original} == original
        assert state["active_task"]["id"] == task["id"] and state["tasks"] == [state["active_task"]]
        progress = runtime.flow.progress(task["id"])
        progress.pop("task")
        assert state["progress"] == progress
        assert state["preparation_activity"] == {
            "task_id": task["id"],
            "task_revision": task["revision"],
            "status": "idle",
        }
        assert runtime.flow_view.state(task["id"])["active_task"]["id"] == task["id"]
    finally:
        runtime.close()


def test_flow_view_without_task_or_flow_keeps_the_old_shape(roots, tmp_path):
    runtime = _open(roots)
    try:
        state = runtime.flow_view.state()
        assert state["active_task"] is None
        assert state["progress"] is None and state["preparation_activity"] is None
    finally:
        runtime.close()
    applications, career, _, _ = roots
    from career_evidence_graph.application_runtime import open_runtime

    bare = open_runtime(applications, career, static_root=_STATIC, static_files={})
    try:
        assert bare.flow_view.state() == {"enabled": False}
    finally:
        bare.close()


def test_progress_is_read_with_the_snapshot_under_one_lock(roots):
    runtime = _open(roots)
    try:
        task = _task(runtime)
        flow, original = runtime.flow, runtime.flow.snapshot
        writer = {}

        def snapshot_then_race(task_id=None, **options):
            observed = original(task_id, **options)
            # A concurrent writer between snapshot and progress must wait for the lock.
            writer["thread"] = threading.Thread(
                target=lambda: writer.setdefault("task", flow.cancel(task["id"], task["revision"]))
            )
            writer["thread"].start()
            writer["thread"].join(0.3)
            return observed

        flow.snapshot = snapshot_then_race
        try:
            state = runtime.flow_view.state()
        finally:
            del flow.snapshot
        writer["thread"].join(3)
        assert writer["task"]["status"] == "cancelled"
        assert state["active_task"]["revision"] == task["revision"]
        assert state["progress"]["task_revision"] == task["revision"]
        assert state["preparation_activity"]["task_revision"] == task["revision"]
    finally:
        runtime.close()


@pytest.mark.parametrize(
    ("stages", "status"),
    [
        ({"analysis": {"status": "complete"}, "resume": {"status": "queued"}}, "running"),
        ({"analysis": {"status": "running"}, "resume": {"status": "pending"}}, "running"),
        (
            {"analysis": {"status": "complete"}, "export": {"status": "needs_recheck"}},
            "needs_recheck",
        ),
        ({"analysis": {"status": "failed"}, "resume": {"status": "complete"}}, "idle"),
    ],
)
def test_preparation_activity_projects_saved_stage_records(stages, status):
    from career_evidence_graph.application_flow_view import preparation_activity

    task = {"id": "t", "revision": "r", "stages": stages}
    assert preparation_activity(task) == {"task_id": "t", "task_revision": "r", "status": status}
    assert preparation_activity(None) is None


def test_http_flow_routes_read_the_runtime_flow_view(portal, tmp_path, monkeypatch):
    from career_evidence_graph import application_flow_view

    calls = []
    original = application_flow_view.FlowView.state

    def spy(self, task_id=None):
        calls.append(task_id)
        return original(self, task_id)

    monkeypatch.setattr(application_flow_view.FlowView, "state", spy)
    job = ApplicationStore(portal.applications).create_application(
        {"company": "Synthetic", "role_title": "Engineer", "job_description": "Build Python."}
    )
    with explanation_portal(portal, tmp_path) as (active, _work):
        status, task = post(
            active,
            "create",
            {"application_id": job["id"], "application_revision": job["revision"]},
        )
        assert status == 200, task
        calls.clear()
        state = snapshot(active)
        assert set(state) - ADDITIVE == PREPARATION_KEYS
        status, _, _ = active.request("GET", "/api/flow/" + task["id"])
        assert status == 200
        assert calls == [None, task["id"]]


def test_status_reads_write_nothing_and_start_no_model_build_or_browser(portal, tmp_path):
    job = ApplicationStore(portal.applications).create_application(
        {"company": "Synthetic", "role_title": "Engineer", "job_description": "Build Python."}
    )
    with explanation_portal(portal, tmp_path) as (active, work):
        client = SyntheticLatexClient(on_compile=lambda: compiles.append(True))
        compiles = []
        active.server.application_resume_store.prism_client = client
        task = create_authorized_latex(active, job)
        assert post(active, "export-pdf", export_payload(task))[0] == 200
        flow = active.server.application_flow_service
        wait_for(flow, task["id"], lambda row: row["status"] == "resume_ready")
        roots = (portal.applications, portal.career, tmp_path / "preparation")
        before = {root: _tree(root) for root in roots}
        calls, exports, builds = list(work["calls"]), list(work["exports"]), list(compiles)
        state = snapshot(active)
        assert state["pdf_integrity"]["status"] == "valid"
        assert state["preparation_activity"]["status"] == "idle"
        assert state["progress"]["task_id"] == task["id"] and "task" not in state["progress"]
        assert active.request("GET", "/api/flow/" + task["id"])[0] == 200
        assert {root: _tree(root) for root in roots} == before
        assert (work["calls"], work["exports"], compiles) == (calls, exports, builds)


def test_application_status_read_does_not_start_the_worker(roots):
    runtime = _open(roots)
    try:
        _task(runtime)
        before = {root: _tree(root) for root in roots[2:]}
        runtime.flow_view.state()
        assert runtime.worker.process is None
        assert runtime.pipeline.snapshot()["control"] == "paused"
        assert {root: _tree(root) for root in roots[2:]} == before
    finally:
        runtime.close()


def test_preparation_projection_keeps_runtime_identity(roots):
    runtime = _open(roots, preparation_only=True)
    try:
        _task(runtime)
        state = runtime.flow_view.state()
        assert list(state) == [*PREPARATION_ORDER, "progress", "preparation_activity"]
        assert state["runtime"] == runtime.identity and state["runtime"] is not runtime.identity
        assert state["mode"] == "preparation"
        assert state["capabilities"]["worker"] is False
    finally:
        runtime.close()


def test_the_page_lists_other_tasks_briefly_and_the_active_one_whole(roots):
    # 2026-11-05: the 1.2 s poll returned every task whole, about 107 MB.
    runtime = _open(roots)
    try:
        older, newer = _task(runtime, "Older Employer"), _task(runtime, "Newer Employer")
        brief = {"id", "revision", "application_id", "status"}
        state = runtime.flow_view.state()
        rows = {row["id"]: row for row in state["tasks"]}
        assert state["active_task"]["id"] == newer["id"]
        assert set(rows[older["id"]]) == brief and rows[older["id"]]["status"] == older["status"]
        assert "job_description" in rows[newer["id"]]
        chosen = runtime.flow_view.state(older["id"])
        rows = {row["id"]: row for row in chosen["tasks"]}
        assert chosen["active_task"]["id"] == older["id"] and "inputs" in rows[older["id"]]
        assert set(rows[newer["id"]]) == brief
        # Other readers of the snapshot keep every task whole.
        assert all("inputs" in row for row in runtime.flow.snapshot()["tasks"])
    finally:
        runtime.close()


def test_the_display_explanation_is_built_after_the_lock_is_released(roots, monkeypatch):
    # 2026-11-06: it was 0.65 s of each poll's hold of the shared write lock.
    runtime = _open(roots)
    try:
        _task(runtime)
        flow, original = runtime.flow, runtime.flow.snapshot
        held = []

        def analysed(*args, **options):
            state = original(*args, **options)
            state["active_task"]["analysis_id"] = "synthetic-analysis"
            return state

        def explanation(task):
            held.append(flow.applications._write_descriptor is not None)
            return {"task_id": task["id"]}

        monkeypatch.setattr(flow, "snapshot", analysed)
        monkeypatch.setattr(flow, "_task_explanation", explanation)
        state = runtime.flow_view.state()
        assert held == [False]
        assert state["match_explanation"] == {"task_id": state["active_task"]["id"]}
    finally:
        runtime.close()


def test_preparation_mode_keeps_every_task_whole(roots):
    runtime = _open(roots, preparation_only=True)
    try:
        _task(runtime, "Older Employer"), _task(runtime, "Newer Employer")
        assert all("inputs" in row for row in runtime.flow_view.state()["tasks"])
    finally:
        runtime.close()


def test_reads_share_one_parse_until_the_record_is_replaced(roots, monkeypatch):
    # 2026-11-05: every read parsed the 125 MB record under the shared write lock.
    runtime = _open(roots)
    try:
        task = _task(runtime)
        flow = runtime.flow
        original, loads = flow._load, []

        def counted():
            loads.append(True)
            return original()

        monkeypatch.setattr(flow, "_load", counted)
        flow._shared = None
        first = flow.task_snapshot(task["id"])
        flow.task_snapshot(task["id"])
        flow.progress(task["id"])
        # 2026-11-05: a worker action (the pipeline's 4 s heartbeat) read it too.
        for operation in ("observe-page", "heartbeat"):
            with pytest.raises(PortalDataError) as error:
                flow.worker_action(task["id"], task["revision"], operation, {})
            assert error.value.code == "flow_worker_unavailable"
        assert len(loads) == 1
        # A caller's copy never changes the shared parse.
        first["status"] = "synthetic-change"
        assert flow.task_snapshot(task["id"])["status"] != "synthetic-change"
        listed = flow.snapshot()
        listed["tasks"][0]["status"] = listed["schemaVersion"] = "synthetic-change"
        assert flow.snapshot()["tasks"][0]["status"] != "synthetic-change"
        assert flow._load_shared()["schemaVersion"] == 1
        cancelled = flow.cancel(task["id"], task["revision"])
        assert flow.task_snapshot(task["id"])["revision"] == cancelled["revision"]
        assert len(loads) >= 2
    finally:
        runtime.close()


def test_a_long_hold_logs_its_named_steps(roots, tmp_path, monkeypatch):
    import json
    import time

    from career_evidence_graph import career_portal_data

    log = tmp_path / "locks.jsonl"
    monkeypatch.setenv("TOMORROWSTAR_LOCK_LOG", str(log))
    runtime = _open(roots)
    try:
        _task(runtime)
        clock = iter(range(0, 1000, 2))
        monkeypatch.setattr(career_portal_data.time, "monotonic", lambda: next(clock))
        runtime.flow_view.state()
        monkeypatch.setattr(career_portal_data.time, "monotonic", time.monotonic)
        rows = [json.loads(line) for line in log.read_text().splitlines()]
        steps = next(row["steps"] for row in rows if "snapshot" in row.get("steps", {}))
        assert {"snapshot", "tasks", "progress"} <= set(steps)
        # Outside a hold, a step records nothing.
        with career_portal_data.lock_step("outside"):
            pass
    finally:
        runtime.close()
