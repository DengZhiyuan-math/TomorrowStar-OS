"""Readiness reads existing state without advancing workflow or worker state."""

import json

import pytest
from test_career_portal_http import _running_portal
from test_career_portal_http import portal as portal
from test_flow_retained_review import retained_flow as retained_flow

from career_evidence_graph.career_portal_data import ApplicationStore


def tree_bytes(root):
    return {
        str(path.relative_to(root)): path.read_bytes() for path in root.rglob("*") if path.is_file()
    }


def test_readiness_get_is_independent_of_business_snapshots_and_writes(
    portal, tmp_path, monkeypatch
):
    app = ApplicationStore(portal.applications).create_application(
        {"company": "Synthetic", "role_title": "Engineer", "job_description": "Build Python."}
    )
    with _running_portal(
        portal.applications, portal.career, flow_root=tmp_path / "flow"
    ) as instance:
        flow = instance.server.application_flow_service
        task = flow.create(app["id"], app["revision"])
        monkeypatch.setattr(flow, "snapshot", lambda *_args: pytest.fail("No business snapshot"))
        before = tree_bytes(tmp_path)
        status, _, raw = instance.request("GET", "/api/flow/readiness/" + task["id"])
        assert status == 200, raw
        shown = json.loads(raw)
        assert shown["protocol"] == "installed-readiness/v1"
        assert shown["controller"]["loaded_engine_revision"].startswith(
            "python-loaded-code/v1:controller:"
        )
        assert shown["native_host"]["state"] == "unknown"
        assert shown["worker"]["loaded_engine_revision"] is None
        assert shown["decision"]["can_fill"] is False
        assert shown["decision"]["user_control"] == "paused"
        assert tree_bytes(tmp_path) == before


def test_application_mode_serves_frozen_ui_and_reports_disk_drift(portal, tmp_path, monkeypatch):
    import shutil

    from career_evidence_graph import career_portal

    static = tmp_path / "static-copy"
    shutil.copytree(career_portal._STATIC, static)
    monkeypatch.setattr(career_portal, "_STATIC", static)
    with _running_portal(
        portal.applications, portal.career, flow_root=tmp_path / "flow"
    ) as instance:
        initial = instance.server.application_readiness()
        status, _, original = instance.request("GET", "/static/application_flow.js")
        assert status == 200
        (static / "application_flow.js").write_bytes(
            b"// Different disk UI, never served by this controller"
        )
        shown = instance.server.application_readiness()
        assert (
            shown["controller"]["loaded_engine_revision"]
            == initial["controller"]["loaded_engine_revision"]
        )
        assert shown["controller"]["ui_revision"] == initial["controller"]["ui_revision"]
        assert shown["controller"]["ui_matches_disk"] is False
        assert instance.request("GET", "/static/application_flow.js")[2] == original


def test_readiness_does_not_relabel_or_resume_retained_worker(retained_flow, monkeypatch):
    from copy import deepcopy
    from types import SimpleNamespace

    owner, _, task = retained_flow
    worker = owner.worker_service
    raw = worker.store.load()
    runtime = raw["runtime"]
    assert runtime.get("loaded_engine_revision") is None
    monkeypatch.setattr(worker, "snapshot", lambda: pytest.fail("No worker snapshot"))
    monkeypatch.setattr(
        owner.application_flow_service, "snapshot", lambda *_args: pytest.fail("No flow snapshot")
    )
    monkeypatch.setattr(worker, "process", SimpleNamespace(pid=runtime["pid"], poll=lambda: 2))
    monkeypatch.setattr(worker, "process_run_id", runtime["id"])
    monkeypatch.setattr(worker, "process_started_at", runtime["started_at"])
    raw["worker_error"] = "PortalDataError"
    worker.store.save(raw)
    before = deepcopy(worker.store.load())
    flow_bytes = owner.application_flow_service.path.read_bytes()
    all_bytes = tree_bytes(worker.store.root.parent)
    shown = owner.application_readiness(task["id"])
    assert shown["worker"]["state"] == "exited"
    assert shown["worker"]["last_error"] == "PortalDataError"
    assert shown["worker"]["loaded_engine_revision"] is None
    assert shown["decision"]["can_fill"] is False
    assert shown["decision"]["can_observe_page"] is False
    assert shown["worker"]["startup_source_revision"] == runtime["source"]["sha256"]
    assert worker.store.load() == before
    assert owner.application_flow_service.path.read_bytes() == flow_bytes
    assert tree_bytes(worker.store.root.parent) == all_bytes


def test_input_change_and_mid_scan_task_change_are_not_silently_accepted(
    portal, tmp_path, monkeypatch
):
    from career_evidence_graph import application_runtime

    app = ApplicationStore(portal.applications).create_application(
        {"company": "Synthetic", "role_title": "Engineer", "job_description": "Python."}
    )
    with _running_portal(
        portal.applications, portal.career, flow_root=tmp_path / "flow"
    ) as instance:
        flow = instance.server.application_flow_service
        task = flow.create(app["id"], app["revision"])
        assert instance.server.application_readiness(task["id"])["inputs"]["state"] == "current"
        ApplicationStore(portal.applications).update_application(
            app["id"], {"job_description": "Rust."}, app["revision"]
        )
        assert instance.server.application_readiness(task["id"])["inputs"]["state"] == "stale"
        original = application_runtime.career_source_snapshot

        def concurrent_change(catalog):
            result = original(catalog)
            with flow.applications.write_lock():
                state = flow._load()
                state["tasks"][0]["reason"] = "synthetic_concurrent_change"
                flow._save(state)
            return result

        monkeypatch.setattr(application_runtime, "career_source_snapshot", concurrent_change)
        shown = instance.server.application_readiness(task["id"])
        assert shown["inputs"]["state"] == "state_changed"
        assert shown["status"] == "blocked"
        assert "state_changed_during_read" in shown["reasons"]


def native_fixture():
    binding = {
        "launch_nonce": "synthetic-launch",
        "native_pid": 100,
        "backend_pid": 200,
        "bundle_id": "synthetic.app",
        "executable": "/synthetic/App",
    }
    return binding, {
        **binding,
        "protocol": "current-native-host/v1",
        "scope": "current_instance",
        "kind": "check",
        "state": "verified",
        "captured_at": 1000,
        "accessibility": True,
        "screen_recording": True,
        "responsibility_chain": "verified",
        "daemon": {
            "pid": 300,
            "responsible_pid": 100,
            "proxy_pid": 400,
            "proxy_responsible_pid": 100,
            "prompt": False,
            "closed": True,
            "checked_at": 1000,
        },
    }


@pytest.mark.parametrize(
    ("mutation", "expected"),
    [
        ("none", "verified"),
        ("sample", "unknown"),
        ("nonce", "blocked"),
        ("pid", "blocked"),
        ("executable", "blocked"),
        ("background", "unknown"),
        ("stale", "unknown"),
        ("missing_permission", "blocked"),
        ("daemon", "unknown"),
    ],
)
def test_native_permission_evidence_requires_exact_current_instance(mutation, expected):
    from career_evidence_graph.application_readiness import project_native_host

    binding, receipt = native_fixture()
    if mutation == "sample":
        receipt["kind"] = "sample"
    if mutation == "nonce":
        receipt["launch_nonce"] = "different-launch"
    if mutation == "pid":
        receipt["backend_pid"] = 201
    if mutation == "executable":
        receipt["executable"] = "/other/App"
    if mutation == "background":
        receipt["scope"] = "same_bundle_background_probe"
    if mutation == "stale":
        receipt["captured_at"] = 900
    if mutation == "missing_permission":
        receipt["screen_recording"] = False
    if mutation == "daemon":
        receipt["daemon"]["proxy_responsible_pid"] = 999
    assert project_native_host(receipt, binding, 1001)["state"] == expected


def test_disk_manifest_check_remains_separate_from_loaded_identity(tmp_path):
    import hashlib

    from career_evidence_graph.application_readiness import inspect_disk_package

    resources = tmp_path / "Resources"
    source = resources / "system/src/synthetic.py"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"# Synthetic package source\n")
    manifest = {
        "format": "tomorrowstar-macos-build/v1",
        "engine_files": {
            "src/synthetic.py": hashlib.sha256(source.read_bytes()).hexdigest(),
        },
    }
    (resources / "build-manifest.json").write_text(json.dumps(manifest))
    result = inspect_disk_package(resources)
    assert result["matches_manifest"] is True
    assert result["loaded_mapping"] == "unknown" and result["signature"] == "not_checked"
    source.write_bytes(b"# Different unloaded disk source\n")
    assert inspect_disk_package(resources)["status"] == "mismatch"
    manifest["engine_files"] = {"../../escape": "0" * 64}
    (resources / "build-manifest.json").write_text(json.dumps(manifest))
    assert inspect_disk_package(resources)["status"] == "unavailable"


def projection_fixture():
    return {
        "controller": {
            "loaded_engine_revision": "synthetic-controller",
            "source_matches_disk": True,
            "ui_matches_disk": True,
        },
        "package": {"status": "verified", "loaded_mapping": "verified"},
        "state": {
            "control": "paused",
            "cua_enabled": True,
            "runtime": {
                "id": "synthetic-run",
                "pid": 100,
                "observed_at": 1000,
                "loaded_engine_revision": "synthetic-worker",
                "source": {"sha256": "synthetic-source"},
                "capabilities": ["owned-page-observation/v1"],
            },
        },
        "task": {
            "materials_confirmed": True,
            "inputs": {},
            "analysis_id": "analysis",
            "resume_id": "resume",
            "resume_sha256": "synthetic-pdf",
            "artifacts": [
                {
                    "stage": "analysis",
                    "adopted": True,
                    "result": {"id": "analysis", "requirements": []},
                }
            ],
            "send_approval": {
                "confirmed": True,
                "verified_by": "user",
                "analysis_id": "analysis",
                "resume_id": "resume",
                "resume_sha256": "synthetic-pdf",
                "inputs": {},
            },
        },
        "job": {
            "intent": None,
            "owned_page_inspection": {
                "status": "captured",
                "at": 1000,
                "binding": {"run_id": "synthetic-run"},
                "worker_source": "synthetic-source",
                "owner": {
                    "status": "accepted",
                    "pid": 300,
                    "window_id": 400,
                    "observed_at": 1000,
                    "driver_version": "synthetic-v1",
                },
            },
        },
        "inputs": {"state": "current"},
        "native_host": {"state": "verified", "reason": "verified"},
        "page_target": {"run_id": "synthetic-run"},
        "process": "managed",
        "storage_error": "",
        "changed": False,
        "now": 1001,
    }


def test_exact_synthetic_compatibility_evidence_never_grants_resume(monkeypatch):
    from career_evidence_graph import application_readiness as module

    args = projection_fixture()
    original = module.project_readiness(**args)
    assert original["compatibility"]["state"] == "unknown"
    key = (module.CONTROLLER_PROTOCOL, "synthetic-worker", "synthetic-source")
    monkeypatch.setitem(
        module.VERIFIED_WORKERS,
        key,
        {
            "commands": ["observe-page"],
            "basis": ["Synthetic exact protocol/schema handoff fixture"],
        },
    )
    result = module.project_readiness(**args)
    assert result["status"] == "verified_paused"
    assert result["page"]["owner"]["status"] == "accepted"
    assert result["decision"] == {
        "can_fill": False,
        "can_observe_page": True,
        "user_control": "paused",
    }
    assert args["state"]["control"] == "paused" and args["job"]["intent"] is None


def test_read_only_observation_survives_unknown_execution_identity_and_unresolved_intent():
    from copy import deepcopy

    from career_evidence_graph.application_readiness import project_readiness

    args = projection_fixture()
    args["process"] = "unknown"
    args["job"].update(
        status="needs_recheck", intent={"action": "fill", "attempt_id": "synthetic-pending"}
    )
    # The old image is historical; the retained handle can still capture a new one.
    args["job"]["owned_page_inspection"]["at"] = 900
    before = deepcopy(args)
    shown = project_readiness(**args)
    assert shown["page"]["state"] == "historical"
    assert shown["worker"]["process"] == "unknown"
    assert shown["compatibility"]["state"] == "unknown"
    assert shown["compatibility"]["commands"]["resume"] == "unknown"
    assert shown["decision"] == {
        "can_fill": False,
        "can_observe_page": True,
        "user_control": "paused",
    }
    assert "unresolved_action_retained" in shown["reasons"]
    assert args == before


@pytest.mark.parametrize(
    "failure",
    [
        "missing_capability",
        "old_capability",
        "missing_target",
        "stale_runtime",
        "exited",
        "running",
        "state_changed",
        "storage_stopped",
        "worker_error",
    ],
)
def test_read_only_observation_still_requires_current_supported_retained_handle(
    monkeypatch, failure
):
    from career_evidence_graph import application_readiness as module

    args = projection_fixture()
    args["process"] = "unknown"
    monkeypatch.setitem(
        module.VERIFIED_WORKERS,
        (module.CONTROLLER_PROTOCOL, "synthetic-worker", "synthetic-source"),
        {"commands": ["observe-page"], "basis": ["Synthetic exact legacy command evidence"]},
    )
    if failure == "missing_capability":
        args["state"]["runtime"].pop("capabilities")
    elif failure == "old_capability":
        args["state"]["runtime"]["capabilities"] = ["synthetic-old-observation/v0"]
    elif failure == "missing_target":
        args["page_target"] = None
    elif failure == "stale_runtime":
        args["state"]["runtime"]["observed_at"] = 900
    elif failure == "exited":
        args["process"] = "exited"
    elif failure == "running":
        args["state"]["control"] = "running"
    elif failure == "state_changed":
        args["changed"] = True
    elif failure == "storage_stopped":
        args["storage_error"] = "checkpoint_unavailable"
    else:
        args["state"]["worker_error"] = "cua_owner_unknown"
    shown = module.project_readiness(**args)
    assert shown["decision"]["can_observe_page"] is False
    assert shown["decision"]["can_fill"] is False


@pytest.mark.parametrize(
    "mutation", ["old_capture", "owner_expired", "different_run", "worker_exited", "unknown_action"]
)
def test_fresh_worker_heartbeat_does_not_hide_owner_or_action_uncertainty(mutation):
    from career_evidence_graph.application_readiness import project_readiness

    args = projection_fixture()
    if mutation == "old_capture":
        args["job"]["owned_page_inspection"]["at"] = 900
    if mutation == "owner_expired":
        args["job"]["owned_page_inspection"]["owner"]["observed_at"] = 900
    if mutation == "different_run":
        args["page_target"] = {"run_id": "different-run"}
    if mutation == "worker_exited":
        args["process"] = "exited"
    if mutation == "unknown_action":
        args["job"]["intent"] = {"action": "fill", "attempt_id": "synthetic-unknown"}
    result = project_readiness(**args)
    assert result["status"] != "verified_paused" and result["decision"]["can_fill"] is False
    if mutation != "unknown_action":
        assert result["page"]["state"] != "current"
    else:
        assert "unresolved_action_retained" in result["reasons"]


def test_only_actual_worker_entry_reports_its_loaded_code_before_browser_start(
    tmp_path, monkeypatch
):
    from career_evidence_graph import (
        application_single_binding,  # noqa: F401
        application_worker_browser,
    )
    from career_evidence_graph.application_worker import WorkerService, start_run
    from career_evidence_graph.loaded_code import loaded_runtime_revision

    applications = tmp_path / "applications"
    applications.mkdir()
    service = WorkerService(ApplicationStore(applications), tmp_path / "worker")
    start_run(service.store)
    assert service.store.load()["runtime"].get("loaded_engine_revision") is None

    def stop_before_browser():
        raise OSError("Synthetic stop before browser startup")

    monkeypatch.setattr(application_worker_browser, "sync_playwright", stop_before_browser)
    assert (
        application_worker_browser.main(
            [
                "--applications",
                str(applications),
                "--runtime",
                str(service.store.root),
                "--fixture-origin",
                "http://127.0.0.1:65432",
                "--headless",
            ]
        )
        == 2
    )
    raw = service.store.load()
    assert raw["runtime"]["loaded_engine_revision"] == loaded_runtime_revision("worker")
    assert raw["control"] == "paused" and raw["worker_error"] == "OSError"
    assert raw["jobs"] == [] and raw["commands"] == []


def test_native_identity_display_distinguishes_bound_app_from_reported_mismatch():
    from career_evidence_graph.application_readiness import project_native_host

    binding, receipt = native_fixture()
    receipt["accessibility"] = False
    result = project_native_host(receipt, binding, 1001)
    assert result["bundle_id"] == "synthetic.app" and result["executable"] == "/synthetic/App"
    assert result["native_pid"] == 100 and result["backend_pid"] == 200
    assert result["identity_state"] == "binding_verified"
    assert result["accessibility"] is False and result["screen_recording"] is True
    assert result["state"] == "blocked"
    receipt["launch_nonce"] = "other-instance"
    mismatched = project_native_host(receipt, binding, 1001)
    assert mismatched["identity_state"] == "unverified"
    assert mismatched["state"] == "blocked" and mismatched["reason"] == "native_instance_mismatch"


@pytest.mark.parametrize("reason", ["responsibility_chain_mismatch", "permission_probe_rejected"])
def test_bound_explicit_native_failure_remains_blocked(reason):
    from career_evidence_graph.application_readiness import project_native_host

    binding, receipt = native_fixture()
    receipt.update(state="blocked", reason=reason, kind="sample", daemon=None)
    result = project_native_host(receipt, binding, 1001)
    assert result["state"] == "blocked" and result["reason"] == reason
    receipt["launch_nonce"] = "not-the-current-native-instance"
    assert project_native_host(receipt, binding, 1001)["reason"] == "native_instance_mismatch"
