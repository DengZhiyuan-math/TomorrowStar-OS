"""MC-14: Runtime assembly, failure cleanup, shutdown and Portal transport mapping."""

import fcntl
import json
import socket
import subprocess
import threading
from contextlib import suppress
from pathlib import Path

import pytest
from test_career_portal_http import _running_portal

from career_evidence_graph.career_portal import create_server
from career_evidence_graph.career_portal_data import ApplicationStore

FLOCKS = (".flow.lock", "pipeline.lock", "intake/.intake.lock")
OWNED_THREADS = {"application-flow", "application-pipeline"}


@pytest.fixture
def roots(tmp_path):
    applications = tmp_path / "synthetic-applications"
    applications.mkdir()
    career = tmp_path / "synthetic-career"
    career.mkdir()
    subprocess.run(["git", "init", "--quiet", str(career)], check=True)
    (career / ".gitignore").write_text(".career-evidence/raw/\n", encoding="utf-8")
    return applications, career, tmp_path / "flow", tmp_path / "worker"


def assert_released(flow_root: Path, before: set) -> None:
    for name in FLOCKS:
        path = flow_root / name
        if not path.exists():
            continue
        with path.open("a") as handle:
            # A leaked owner keeps this exclusive lock; a released runtime does not.
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            fcntl.flock(handle, fcntl.LOCK_UN)
    leaked = [
        thread
        for thread in threading.enumerate()
        if thread not in before and thread.name in OWNED_THREADS and thread.is_alive()
    ]
    for thread in leaked:
        thread.join(timeout=2)
    assert not [thread.name for thread in leaked if thread.is_alive()]


def test_occupied_port_releases_runtime_resources(roots):
    applications, career, flow_root, worker_root = roots
    before = set(threading.enumerate())
    with socket.socket() as occupied:
        occupied.bind(("127.0.0.1", 0))
        occupied.listen()
        with pytest.raises(OSError):
            create_server(
                applications,
                career,
                port=occupied.getsockname()[1],
                flow_root=flow_root,
                worker_root=worker_root,
                write_admission_policy="development",
            )
    assert_released(flow_root, before)
    # The same roots open again as the single owner.
    server = create_server(
        applications,
        career,
        flow_root=flow_root,
        worker_root=worker_root,
        write_admission_policy="development",
    )
    try:
        assert server.application_pipeline_service is not None
    finally:
        server.server_close()


def test_unexpected_intake_factory_failure_releases_started_flow(roots):
    applications, career, flow_root, worker_root = roots
    before = set(threading.enumerate())

    def failing_intake(*_args, **_kwargs):
        raise RuntimeError("synthetic intake construction failure")

    with pytest.raises(RuntimeError, match="synthetic intake"):
        create_server(
            applications,
            career,
            flow_root=flow_root,
            worker_root=worker_root,
            flow_intake_factory=failing_intake,
            write_admission_policy="development",
        )
    assert_released(flow_root, before)


def test_shutdown_and_server_close_are_idempotent(roots):
    applications, career, flow_root, worker_root = roots
    before = set(threading.enumerate())
    server = create_server(
        applications,
        career,
        flow_root=flow_root,
        worker_root=worker_root,
        write_admission_policy="development",
    )
    serving = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.01})
    serving.start()
    pipeline_record = (flow_root / "pipeline.json").read_bytes()
    server.shutdown()
    server.shutdown()
    serving.join(timeout=5)
    assert not serving.is_alive()
    server.server_close()
    server.server_close()
    assert (flow_root / "pipeline.json").read_bytes() == pipeline_record
    assert_released(flow_root, before)


def test_preparation_permit_is_registered_before_pipeline_thread_starts(roots, monkeypatch):
    applications, career, flow_root, worker_root = roots
    observed = []
    original = threading.Thread.start

    def recording_start(thread):
        target = getattr(thread, "_target", None)
        if thread.name == "application-pipeline":
            pipeline = target.__self__
            observed.append(
                pipeline.flow.callbacks.get("preparation_allowed") == pipeline.preparation_allowed
            )
        return original(thread)

    monkeypatch.setattr(threading.Thread, "start", recording_start)
    server = create_server(
        applications,
        career,
        flow_root=flow_root,
        worker_root=worker_root,
        write_admission_policy="development",
    )
    try:
        assert observed == [True]
    finally:
        server.server_close()


DEFAULT_KEYS = {
    "analysis",
    "automatic_edit_prepare",
    "automatic_latex_base",
    "automatic_source_save",
    "bound_candidate_source",
    "bound_edit_prepare",
    "bound_material_candidate",
    "bound_resume_draft",
    "cover_letter",
    "cover_letter_result",
    "existing_experience_materials",
    "experience_generation",
    "export",
    "export_configuration",
    "material_consistency",
    "material_consistency_result",
    "observe_confirmation",
    "observe_group_confirmation",
    "observe_pdf_ready",
    "observe_preparation_started",
    "prism_edit_begin",
    "prism_edit_finish",
    "prism_edit_state",
    "prism_export_configuration",
    "prism_result_capture",
    "prism_source",
    "reconcile_export",
    "refresh_match",
    "resume",
    "resume_author_result",
    "retained_draft",
    "reuse_analysis",
    "validate_write_preflight",
    "verify_draft",
    "verify_materials",
    "verify_pdf_reuse",
    "verify_prepared_resume",
    "write_preflight",
}
WORKER_KEYS = {
    "bound_material_preparation",
    "bound_worker_state",
    "control_worker",
    "preparation_allowed",
    "prepare_worker",
    "verify_automation_authorization",
    "worker_reference",
}
PREPARATION_KEYS = {
    "batch_candidates",
    "batch_select",
    "group_capture",
    "group_edit",
    "group_prepare",
    "group_state",
    "import_latex",
    "observe_group_requests",
    "observe_material_requests",
    "prism_open",
}


@pytest.mark.parametrize(
    "mode,expected",
    [
        ("flow", DEFAULT_KEYS),
        ("worker", DEFAULT_KEYS | WORKER_KEYS),
        ("preparation", DEFAULT_KEYS | PREPARATION_KEYS),
    ],
)
def test_assembled_flow_keeps_the_same_callback_keys(roots, mode, expected):
    applications, career, flow_root, worker_root = roots
    options = {"flow_root": flow_root}
    if mode == "worker":
        options["worker_root"] = worker_root
    if mode == "preparation":
        options["preparation_only"] = True
    server = create_server(applications, career, write_admission_policy="development", **options)
    try:
        assert set(server.application_flow_service.callbacks) == expected
        worker = server.worker_service
        assert (worker.validate_write_preflight is not None) if worker else mode != "worker"
    finally:
        server.server_close()


START = "请使用自动流程开始、暂停或收录邮件。"
CURRENT = "请使用当前岗位操作。"
CANCEL = "请使用当前岗位取消操作。"
INVALID_REQUESTS = [
    ("unknown-operation", {}, 400, START),
    ("pause", {"unexpected": True}, 400, START),
    ("start", {}, 400, START),
    ("capture", {"request_id": "synthetic", "extra": 1}, 400, START),
    ("continue", {}, 409, CURRENT),
    ("skip", {"request_id": "synthetic", "extra": 1}, 409, CURRENT),
    ("return", {"request_id": "synthetic"}, 409, CURRENT),
    ("observe-result", {}, 409, CURRENT),
    ("cancel-current", {}, 409, CANCEL),
    ("cancel-current", {"request_id": "synthetic", "task_id": "x"}, 409, CANCEL),
]


def post(active, path, payload):
    status, _, raw = active.request(
        "POST", path, body=json.dumps(payload).encode(), headers=active.write_headers()
    )
    return status, json.loads(raw)


@pytest.mark.parametrize("closed", [False, True], ids=["open", "closed"])
def test_invalid_pipeline_requests_keep_code_status_and_message(roots, closed):
    applications, career, flow_root, worker_root = roots
    with _running_portal(
        applications, career, flow_root=flow_root, worker_root=worker_root
    ) as active:
        pipeline = active.server.application_pipeline_service
        if closed:
            # MC-14 accepted change: the transport refuses a malformed shape before
            # a closed Pipeline is consulted (was pipeline_unavailable/409).
            pipeline.close()
        record = pipeline.path.read_bytes()
        for action, payload, status, message in INVALID_REQUESTS:
            shown = post(active, f"/api/pipeline/{action}", payload)
            assert shown == (
                status,
                {"error": "pipeline_request_invalid", "message": message},
            ), action
            assert pipeline.path.read_bytes() == record
        valid = post(active, "/api/pipeline/continue", {"request_id": "synthetic"})
        if closed:
            assert valid[0] == 409 and valid[1]["error"] == "pipeline_unavailable"
        else:
            assert valid == (409, {"error": "pipeline_request_invalid", "message": CURRENT})
        assert pipeline.path.read_bytes() == record


def test_state_and_readiness_reads_make_no_model_or_spawn_call(roots, monkeypatch):
    applications, career, flow_root, worker_root = roots
    calls = []

    def forbidden(name):
        def record(*_args, **_kwargs):
            calls.append(name)
            raise AssertionError(f"read path called {name}")

        return record

    store = ApplicationStore(applications)
    job = store.create_application(
        {
            "company": "Synthetic Employer",
            "role_title": "Service Engineer",
            "url": "https://example.invalid/jobs/1",
            "job_description": "Build reliable Python services.",
        }
    )
    monkeypatch.setattr("career_evidence_graph.codex_cli.run_codex_exec", forbidden("codex"))
    server = create_server(
        applications,
        career,
        flow_root=flow_root,
        worker_root=worker_root,
        flow_match_runner=forbidden("match_runner"),
        write_admission_policy="development",
    )
    serving = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.01})
    serving.start()
    try:
        flow = server.application_flow_service
        server.application_resume_store.model_runner = forbidden("resume_runner")
        monkeypatch.setattr(server.worker_service, "spawn", forbidden("spawn"))
        task = flow.create(job["id"], job["revision"])
        records = {path: path.read_bytes() for path in flow_root.rglob("*.json")}
        from test_career_portal_http import Portal

        active = Portal(server, applications, career)
        for path in (
            "/api/state",
            "/api/flow/state",
            f"/api/flow/{task['id']}",
            "/api/flow/readiness",
            f"/api/flow/readiness/{task['id']}",
            "/api/pipeline/state",
            "/api/intake/state",
            "/api/worker/state",
        ):
            status, _, _ = active.request("GET", path)
            assert status == 200, path
        assert calls == []
        assert {path: path.read_bytes() for path in flow_root.rglob("*.json")} == records
    finally:
        with suppress(Exception):
            server.shutdown()
        serving.join(timeout=5)
        server.server_close()


def test_flow_owns_material_reads_lineage_and_witness(roots):
    from career_evidence_graph.application_flow import material_task_view
    from career_evidence_graph.career_portal_data import PortalDataError

    applications, career, flow_root, _ = roots
    job = ApplicationStore(applications).create_application(
        {
            "company": "Synthetic Employer",
            "role_title": "Service Engineer",
            "job_description": "Build reliable Python services.",
        }
    )
    server = create_server(
        applications, career, flow_root=flow_root, write_admission_policy="development"
    )
    try:
        flow = server.application_flow_service
        for read, code in (
            (flow.read_draft, "flow_draft_not_found"),
            (flow.read_export, "flow_export_not_found"),
        ):
            with pytest.raises(PortalDataError) as missing:
                read("a" * 32)
            assert (missing.value.code, missing.value.status) == (code, 404)
        task = flow.create(job["id"], job["revision"])
        state, copy = flow.witness(task["id"])
        assert copy == state["tasks"][0] and copy is not state["tasks"][0]
        assert flow.witness() == (state, None)
        assert flow.material_tasks() == [material_task_view(row) for row in state["tasks"]]
        assert flow.ready_cover_letter_content(job["id"], task.get("analysis_id")) is None
        assert flow.adopted_resume_content(task["id"]) is None
        assert flow.cover_letter_call_allowed(task["id"], "synthetic-attempt") is False
        assert flow.reuses_base_sources(job["id"], "synthetic-revision") is False
        assert flow.callbacks["verify_materials"] == flow.verify_materials
        assert flow.callbacks["verify_draft"] == flow.verify_draft
        assert server.application_resume_store.cover_letter_provider == (
            flow.ready_cover_letter_content
        )
    finally:
        server.server_close()


def test_readiness_and_write_preflight_are_owned_entries(roots):
    from career_evidence_graph.application_readiness import ReadinessProbe
    from career_evidence_graph.career_portal_data import PortalDataError

    applications, career, flow_root, worker_root = roots
    server = create_server(
        applications,
        career,
        flow_root=flow_root,
        worker_root=worker_root,
        write_admission_policy="development",
    )
    try:
        flow, worker = server.application_flow_service, server.worker_service
        assert isinstance(server.application_readiness, ReadinessProbe)
        from career_evidence_graph import application_single_binding as binding

        preflight = flow.callbacks["write_preflight"]
        validate = flow.callbacks["validate_write_preflight"]
        # The single-binding admission owns the preflight; Flow is reached only publicly.
        assert preflight.func is binding.write_preflight and preflight.args == (flow,)
        assert validate.func is binding.validate_write_preflight and validate.args == (flow,)
        assert not hasattr(flow, "write_preflight") and not hasattr(flow, "_preparation_target")
        assert worker.validate_write_preflight is validate
        assert validate("prepare") is False
        with preflight("observe"):
            pass
        facts = worker.readiness_facts(worker.store.load(), None)
        assert {key: facts[key] for key in facts if key not in {"root", "paths"}} == {
            "pending_prepare": False,
            "owned_process_alive": False,
            "process": "unknown",
            "page_target": None,
        }
        assert worker.store.stop_path in facts["paths"]
        flow.check_available()
        flow.close()
        with pytest.raises(PortalDataError) as busy:
            flow.check_available()
        assert busy.value.code == "flow_runtime_busy"
    finally:
        server.server_close()


def test_open_runtime_assembles_owners_without_http_and_closes_repeatedly(roots):
    from career_evidence_graph.application_runtime import open_runtime
    from career_evidence_graph.career_portal import _STATIC

    applications, career, flow_root, worker_root = roots
    before = set(threading.enumerate())
    static = {path.name: path.read_bytes() for path in _STATIC.iterdir() if path.is_file()}
    runtime = open_runtime(
        applications,
        career,
        static_root=_STATIC,
        static_files=static,
        flow_root=flow_root,
        worker_root=worker_root,
    )
    try:
        flow, pipeline = runtime.flow, runtime.pipeline
        assert pipeline is not None and pipeline.flow is flow and pipeline.worker is runtime.worker
        assert flow.callbacks["preparation_allowed"] == pipeline.preparation_allowed
        assert runtime.identity["mode"] == "application"
        # Opening never enables a paused Pipeline or starts the Worker.
        assert pipeline.snapshot()["control"] == "paused"
        assert runtime.worker.process is None
        assert runtime.readiness()["inputs"]["state"] == "unknown"
    finally:
        runtime.close()
        runtime.close()
    assert_released(flow_root, before)


def test_open_runtime_rejects_a_mixed_handoff_and_worker_before_construction(roots):
    from career_evidence_graph.application_runtime import open_runtime
    from career_evidence_graph.career_portal import _STATIC

    applications, career, flow_root, worker_root = roots
    with pytest.raises(ValueError, match="separate servers"):
        open_runtime(
            applications,
            career,
            static_root=_STATIC,
            static_files={},
            worker_root=worker_root,
            handoff_root=flow_root / "handoff",
        )
    # Neither the selected worker nor the handoff directory was created.
    assert not worker_root.exists()
    assert not (flow_root / "handoff").exists()


def test_pipeline_transport_uses_named_controls_only():
    from career_evidence_graph.application_pipeline import ApplicationPipeline
    from career_evidence_graph.career_portal import pipeline_control

    assert not hasattr(ApplicationPipeline, "request")
    assert callable(ApplicationPipeline.flow_control)

    class Named:
        def __init__(self):
            self.calls = []

        def __getattr__(self, name):
            return lambda *args, **kwargs: self.calls.append((name, args, kwargs)) or name

    pipeline = Named()
    assert pipeline_control(pipeline, "return", {"request_id": "r", "application_id": "a"}) == (
        "return_to"
    )
    assert pipeline_control(pipeline, "cancel-current", {"request_id": "r"}) == "cancel_current"
    assert pipeline_control(pipeline, "admit", {"anything": True}) == "admit"
    assert pipeline.calls == [
        ("return_to", (), {"request_id": "r", "application_id": "a"}),
        ("cancel_current", (), {"request_id": "r"}),
        ("admit", ({"anything": True},), {}),
    ]


def test_flow_offers_checked_task_reads_for_admission(roots):
    from career_evidence_graph.career_portal_data import PortalDataError

    applications, career, flow_root, _ = roots
    job = ApplicationStore(applications).create_application(
        {
            "company": "Synthetic Employer",
            "role_title": "Service Engineer",
            "job_description": "Build reliable Python services.",
        }
    )
    server = create_server(
        applications, career, flow_root=flow_root, write_admission_policy="development"
    )
    try:
        flow = server.application_flow_service
        task = flow.create(job["id"], job["revision"])
        assert flow.read_checked_task(task["id"], task["revision"]) == task
        assert flow.writable_task(task["id"], task["revision"]) == task
        for read in (flow.read_checked_task, flow.writable_task):
            with pytest.raises(PortalDataError) as changed:
                read(task["id"], "stale-revision")
            assert (changed.value.code, changed.value.status) == ("conflict", 409)
    finally:
        server.server_close()
