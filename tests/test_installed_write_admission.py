"""Business safeguards are independent of installed maintenance diagnostics."""

import json
import subprocess

import pytest
from test_application_single_binding import make_bound_single

from career_evidence_graph.application_worker import digest
from career_evidence_graph.career_portal import create_server
from career_evidence_graph.career_portal_data import PortalDataError


def prepared_inputs(tmp_path, *, job_description="Build Python services."):
    applications, root, career, _, _ = make_bound_single(tmp_path, job_description=job_description)
    subprocess.run(["git", "init", "--quiet", str(career)], check=True)
    path = root / "flow.json"
    state = json.loads(path.read_text())
    task = state["tasks"][0]
    task.update(
        status="materials_ready",
        worker_ref=None,
        stages={"analysis": {"status": "complete"}, "resume": {"status": "complete"}},
    )
    task["revision"] = digest({k: v for k, v in task.items() if k != "revision"})
    path.write_text(json.dumps(state))
    return applications, root, career, task


def bytes_under(root):
    return {str(p.relative_to(root)): p.read_bytes() for p in root.rglob("*") if p.is_file()}


@pytest.mark.parametrize("policy", ["strict", "development"])
def test_installed_prepare_uses_current_materials_without_package_evidence(tmp_path, policy):
    applications, root, career, task = prepared_inputs(tmp_path)
    with create_server(
        applications.root,
        career,
        flow_root=root,
        worker_root=tmp_path / "worker",
        worker_live=True,
        package_resources=tmp_path / "missing-installed-package",
        write_admission_policy=policy,
    ) as server:
        prepared = server.application_flow_service.prepare_worker(
            task["id"], task["revision"], "CHE", True
        )
        state = server.worker_service.store.load()
        assert prepared["status"] == "queued"
        assert state["control"] == "paused" and state.get("runtime") is None
        assert state["jobs"][0]["application_id"] == task["application_id"]
        assert state["jobs"][0]["file_sha256"] == task["resume_sha256"]
        assert server.worker_service.process is None


def test_direct_resume_storage_stop_keeps_pause_error_stop_marker_and_claims(tmp_path, monkeypatch):
    applications, root, career, task = prepared_inputs(tmp_path)
    worker_root = tmp_path / "worker"
    with create_server(
        applications.root,
        career,
        flow_root=root,
        worker_root=worker_root,
        worker_live=True,
        write_admission_policy="development",
    ) as development:
        development.application_flow_service.prepare_worker(
            task["id"], task["revision"], "CHE", True
        )
    with create_server(
        applications.root,
        career,
        flow_root=root,
        worker_root=worker_root,
        worker_live=True,
        package_resources=tmp_path / "missing-installed-package",
    ) as server:
        worker = server.worker_service
        state = worker.store.load()
        state["worker_error"] = "PortalDataError"
        worker.store.save(state)
        worker.store.stop_path.write_text('{"reason":"checkpoint_unavailable"}')
        before = worker.store.path.read_bytes()
        stop = worker.store.stop_path.read_bytes()
        claims = bytes_under(applications.root)
        starts = []
        monkeypatch.setattr(worker, "spawn", lambda: starts.append(True))
        from career_evidence_graph._vendor import job_apply_store as helper

        original = helper.atomic_write_json

        def still_unavailable(path, value):
            if path == worker.store.path:
                raise OSError("synthetic checkpoint still unavailable")
            return original(path, value)

        # Continue lifts the stop only after the unchanged checkpoint is durable again.
        monkeypatch.setattr(helper, "atomic_write_json", still_unavailable)
        with pytest.raises(PortalDataError) as stopped:
            worker.request(
                "resume",
                {"controller": "synthetic-controller", "write_admission_policy": "development"},
            )
        assert stopped.value.code == "checkpoint_unavailable"
        assert worker.store.path.read_bytes() == before
        assert worker.store.stop_path.read_bytes() == stop
        assert worker.store.stop_reason() == "checkpoint_unavailable"
        assert bytes_under(applications.root) == claims
        assert starts == []


def synthetic_package_inspection(_resources):
    import hashlib

    from career_evidence_graph import career_portal
    from career_evidence_graph.loaded_code import loaded_runtime_revision

    return {
        "status": "verified",
        "matches_manifest": True,
        "manifest_revision": "disk-manifest-sha256:" + "a" * 64,
        "loaded_code": {
            "controller": loaded_runtime_revision("controller"),
            "worker": "python-loaded-code/v1:worker:" + "b" * 64,
            "ui_revision": digest(
                {
                    p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                    for p in career_portal._STATIC.iterdir()
                    if p.is_file()
                }
            ),
        },
    }


def installed_evidence(monkeypatch, tmp_path):
    """Synthetic measured-build and native receipts; no package/App/process is created."""
    import time
    from copy import deepcopy

    from test_application_readiness import native_fixture

    from career_evidence_graph import application_readiness

    binding, native = native_fixture()
    native["captured_at"] = native["daemon"]["checked_at"] = time.time()
    native.update(session_open=True, instance_binding=dict(binding), invalidation_epoch=0)
    resources = tmp_path / "synthetic-resources"
    resources.mkdir()

    monkeypatch.setattr(application_readiness, "inspect_disk_package", synthetic_package_inspection)

    def snapshot():
        if snapshot.before_read is not None:
            snapshot.before_read()
        return deepcopy(native)

    snapshot.before_read = None
    snapshot.receipt = native
    return {
        "package_resources": resources,
        "native_host_binding": binding,
        "native_host_identity": snapshot,
    }


@pytest.mark.parametrize("qualification", ["not_specified", "needs_input", "conflict"])
def test_installed_first_prepare_and_explicit_bootstrap_do_not_require_a_future_page(
    tmp_path, monkeypatch, qualification
):
    applications, root, career, task = prepared_inputs(tmp_path)
    if qualification != "not_specified":
        state = json.loads((root / "flow.json").read_text())
        task = state["tasks"][0]
        analysis = task["artifacts"][0]["result"]
        analysis["requirements"] = [
            {
                "text": "Required work permit",
                "hard_condition": True,
                "judgment": "unknown" if qualification == "needs_input" else "gap",
            }
        ]
        (root / "analyses" / analysis["id"] / "analysis.json").write_text(json.dumps(analysis))
        task["revision"] = digest({key: value for key, value in task.items() if key != "revision"})
        (root / "flow.json").write_text(json.dumps(state))
    options = installed_evidence(monkeypatch, tmp_path)
    with create_server(
        applications.root,
        career,
        flow_root=root,
        worker_root=tmp_path / "worker",
        worker_live=True,
        **options,
    ) as server:
        worker = server.worker_service
        starts = []
        monkeypatch.setattr(worker, "spawn", lambda: starts.append(True))
        readiness = server.application_readiness(task["id"])
        assert readiness["inputs"]["qualification"] == qualification
        if qualification == "conflict":
            assert "qualification_unverified" in readiness["reasons"]
            before = (root / "flow.json").read_bytes()
            with pytest.raises(PortalDataError) as stopped:
                server.application_flow_service.prepare_worker(
                    task["id"], task["revision"], "CHE", True
                )
            assert stopped.value.code == "flow_eligibility_required"
            assert (root / "flow.json").read_bytes() == before
            assert not starts
            return
        assert "qualification_unverified" not in readiness["reasons"]
        prepared = server.application_flow_service.prepare_worker(
            task["id"], task["revision"], "CHE", True
        )
        assert prepared["status"] == "queued"
        assert worker.store.load().get("runtime") is None
        assert worker.store.load()["control"] == "paused" and starts == []
        server.application_flow_service.worker_action(
            prepared["id"],
            prepared["revision"],
            "resume",
            {"controller": "synthetic-controller"},
        )
        state = worker.store.load()
        assert state["control"] == "running" and starts == [True]
        assert state.get("runtime") is None and not state["jobs"][0].get("page_observation")
        from career_evidence_graph.application_flow import task_eligibility

        saved = server.application_flow_service.snapshot(task["id"])["active_task"]
        assert task_eligibility(saved)["status"] == qualification
        assert not saved.get("hard_condition_resolutions")


def test_worker_entry_reaches_browser_boundary_despite_replaced_package(tmp_path, monkeypatch):
    from career_evidence_graph import application_readiness, application_worker_browser
    from career_evidence_graph.application_worker import WorkerService
    from career_evidence_graph.career_portal_data import ApplicationStore

    apps = tmp_path / "applications"
    apps.mkdir()
    service = WorkerService(ApplicationStore(apps), tmp_path / "worker")
    monkeypatch.setattr(
        application_worker_browser,
        "sync_playwright",
        synthetic_stop_before_browser,
    )
    monkeypatch.setattr(application_readiness, "inspect_disk_package", synthetic_package_inspection)
    assert (
        application_worker_browser.main(
            [
                "--applications",
                str(apps),
                "--runtime",
                str(service.store.root),
                "--fixture-origin",
                "http://127.0.0.1:65432",
                "--headless",
                "--package-resources",
                str(tmp_path / "synthetic-resources"),
                "--expected-package-manifest",
                "disk-manifest-sha256:" + "c" * 64,
                "--expected-worker-revision",
                "python-loaded-code/v1:worker:" + "b" * 64,
            ]
        )
        == 2
    )
    state = service.store.load()
    assert state["control"] == "paused" and state["worker_error"] == "OSError"
    assert state["jobs"] == [] and state["commands"] == []


@pytest.mark.parametrize("drift", ["configuration", "source", "native"])
def test_prepare_rechecks_actual_sources_but_ignores_unrelated_diagnostics(
    tmp_path, monkeypatch, drift
):
    applications, root, career, task = prepared_inputs(tmp_path)
    options = installed_evidence(monkeypatch, tmp_path)
    with create_server(
        applications.root,
        career,
        flow_root=root,
        worker_root=tmp_path / "worker",
        worker_live=True,
        **options,
    ) as server:
        flow = server.application_flow_service
        original = flow._checked
        import os

        previous_executable = os.environ.get("TOMORROWSTAR_CODEX_EXECUTABLE")
        before_flow = flow.path.read_bytes()
        before_worker = bytes_under(server.worker_service.store.root)
        before_applications = bytes_under(applications.root)

        def change_after_slow_scan(*args):
            result = original(*args)
            if drift == "configuration":
                monkeypatch.setenv("TOMORROWSTAR_CODEX_EXECUTABLE", "/synthetic/changed-codex")
            elif drift == "source":
                (career / "sources").mkdir(exist_ok=True)
                (career / "sources/new-synthetic-source.md").write_text(
                    "Synthetic source added after scan"
                )
            else:
                # Same bound instance; permission evidence changes after capture.
                options["native_host_identity"].receipt["accessibility"] = False
            return result

        monkeypatch.setattr(flow, "_checked", change_after_slow_scan)
        if drift != "source":
            prepared = flow.prepare_worker(task["id"], task["revision"], "CHE", True)
            assert prepared["status"] == "queued"
            assert server.worker_service.store.load()["control"] == "paused"
            assert server.worker_service.process is None
            return
        with pytest.raises(PortalDataError) as stopped:
            flow.prepare_worker(task["id"], task["revision"], "CHE", True)
        assert stopped.value.code == "flow_inputs_stale"
        assert flow.path.read_bytes() == before_flow
        assert bytes_under(server.worker_service.store.root) == before_worker
        assert bytes_under(applications.root) == before_applications
        # A rejected operation resets its target; corrected source is rechecked.
        monkeypatch.setattr(flow, "_checked", original)
        if drift == "configuration":
            if previous_executable is None:
                monkeypatch.delenv("TOMORROWSTAR_CODEX_EXECUTABLE")
            else:
                monkeypatch.setenv("TOMORROWSTAR_CODEX_EXECUTABLE", previous_executable)
        elif drift == "source":
            (career / "sources/new-synthetic-source.md").unlink()
        else:
            options["native_host_identity"].receipt["accessibility"] = True
        prepared = flow.prepare_worker(task["id"], task["revision"], "CHE", True)
        assert prepared["status"] == "queued"
        assert server.worker_service.store.load()["control"] == "paused"


@pytest.mark.parametrize("runtime_kind", ["unknown", "stale", "exited"])
def test_resume_preserves_existing_runtime_despite_diagnostic_process_state(
    tmp_path, monkeypatch, runtime_kind
):
    import time
    from types import SimpleNamespace

    from career_evidence_graph.application_worker import start_run

    applications, root, career, task = prepared_inputs(tmp_path)
    options = installed_evidence(monkeypatch, tmp_path)
    with create_server(
        applications.root,
        career,
        flow_root=root,
        worker_root=tmp_path / "worker",
        worker_live=True,
        **options,
    ) as server:
        flow, worker = server.application_flow_service, server.worker_service
        prepared = flow.prepare_worker(task["id"], task["revision"], "CHE", True)
        start_run(worker.store)
        state = worker.store.load()
        runtime = state["runtime"]
        if runtime_kind == "stale":
            runtime["observed_at"] = time.time() - 60
            runtime["loaded_engine_revision"] = "python-loaded-code/v1:worker:" + "b" * 64
        if runtime_kind == "exited":
            worker.process = SimpleNamespace(pid=runtime["pid"], poll=lambda: 2)
            worker.process_started_at = runtime["started_at"]
            worker.process_run_id = runtime["id"]
        worker.store.save(state)
        before = worker.store.load()
        starts = []
        monkeypatch.setattr(worker, "spawn", lambda: starts.append(True))
        flow.worker_action(
            prepared["id"],
            prepared["revision"],
            "resume",
            {"controller": "synthetic-controller"},
        )
        resumed = worker.store.load()
        assert resumed["runtime"] == before["runtime"]
        assert resumed["batch_id"] == before["batch_id"]
        assert resumed["jobs"] == before["jobs"]
        assert resumed["control"] == "running" and starts == [True]
        if runtime_kind == "exited":
            worker.process = None  # server_close must not signal this synthetic process object


def test_default_server_prepares_current_materials_without_installation_evidence(tmp_path):
    applications, root, career, task = prepared_inputs(tmp_path)
    with create_server(
        applications.root,
        career,
        flow_root=root,
        worker_root=tmp_path / "worker",
        worker_live=True,
    ) as server:
        prepared = server.application_flow_service.prepare_worker(
            task["id"], task["revision"], "CHE", True
        )
        assert prepared["status"] == "queued"
        state = server.worker_service.store.load()
        assert state["control"] == "paused" and state.get("runtime") is None
        assert state["jobs"][0]["file_sha256"] == task["resume_sha256"]


@pytest.mark.parametrize(
    "actual, expected_manifest, expected_worker, accepted",
    [
        (
            "python-loaded-code/v1:worker:" + "b" * 64,
            "disk-manifest-sha256:" + "a" * 64,
            "python-loaded-code/v1:worker:" + "b" * 64,
            True,
        ),
        (
            None,
            "disk-manifest-sha256:" + "a" * 64,
            "python-loaded-code/v1:worker:" + "b" * 64,
            False,
        ),
        (
            "python-loaded-code/v1:worker:" + "c" * 64,
            "disk-manifest-sha256:" + "a" * 64,
            "python-loaded-code/v1:worker:" + "b" * 64,
            False,
        ),
        (
            "python-loaded-code/v1:worker:" + "b" * 64,
            None,
            "python-loaded-code/v1:worker:" + "b" * 64,
            False,
        ),
    ],
)
def test_package_identity_diagnostic_compares_the_frozen_same_role(
    tmp_path,
    monkeypatch,
    actual,
    expected_manifest,
    expected_worker,
    accepted,
):
    from career_evidence_graph import application_readiness

    monkeypatch.setattr(application_readiness, "inspect_disk_package", synthetic_package_inspection)
    if accepted:
        application_readiness.require_packaged_worker_identity(
            tmp_path, expected_manifest, expected_worker, actual
        )
    else:
        with pytest.raises(PortalDataError) as stopped:
            application_readiness.require_packaged_worker_identity(
                tmp_path, expected_manifest, expected_worker, actual
            )
        assert stopped.value.code == "installed_worker_identity_unverified"


def actual_entry_package_inspection(resources):
    from career_evidence_graph.loaded_code import loaded_runtime_revision

    package = synthetic_package_inspection(resources)
    package["loaded_code"]["worker"] = loaded_runtime_revision("worker")
    return package


def synthetic_stop_before_browser():
    raise OSError("Synthetic worker reached browser boundary")


def test_worker_entry_accepts_frozen_actual_role_then_stops_before_browser(tmp_path, monkeypatch):
    from career_evidence_graph import application_readiness, application_worker_browser
    from career_evidence_graph.application_worker import WorkerService
    from career_evidence_graph.career_portal_data import ApplicationStore
    from career_evidence_graph.loaded_code import loaded_runtime_revision, measure_packaged_roles

    apps = tmp_path / "applications"
    apps.mkdir()
    service = WorkerService(ApplicationStore(apps), tmp_path / "worker")
    monkeypatch.setattr(
        application_worker_browser, "sync_playwright", synthetic_stop_before_browser
    )
    monkeypatch.setattr(
        application_readiness, "inspect_disk_package", actual_entry_package_inspection
    )
    measure_packaged_roles()
    expected = loaded_runtime_revision("worker")
    assert expected is not None
    assert (
        application_worker_browser.main(
            [
                "--applications",
                str(apps),
                "--runtime",
                str(service.store.root),
                "--fixture-origin",
                "http://127.0.0.1:65432",
                "--headless",
                "--package-resources",
                str(tmp_path / "synthetic-resources"),
                "--expected-package-manifest",
                "disk-manifest-sha256:" + "a" * 64,
                "--expected-worker-revision",
                expected,
            ]
        )
        == 2
    )
    state = service.store.load()
    assert state["runtime"]["loaded_engine_revision"] == expected
    assert state["control"] == "paused" and state["worker_error"] == "OSError"
    assert state["jobs"] == [] and state["commands"] == []


@pytest.mark.parametrize("signal", ["native", "installed_layout"])
def test_native_diagnostic_or_installed_layout_does_not_gate_local_preparation(
    tmp_path, monkeypatch, signal
):
    from career_evidence_graph import career_portal

    applications, root, career, task = prepared_inputs(tmp_path)
    options = {}
    if signal == "native":
        options["native_host_identity"] = lambda: None
    else:
        monkeypatch.setattr(
            career_portal,
            "__file__",
            str(
                tmp_path
                / "Synthetic.app/Contents/Resources/system/src"
                / "career_evidence_graph/career_portal.py"
            ),
        )
    with create_server(
        applications.root,
        career,
        flow_root=root,
        worker_root=tmp_path / "worker",
        worker_live=True,
        write_admission_policy="development",
        **options,
    ) as server:
        prepared = server.application_flow_service.prepare_worker(
            task["id"], task["revision"], "CHE", True
        )
        assert prepared["status"] == "queued"
        state = server.worker_service.store.load()
        assert state["control"] == "paused" and state.get("runtime") is None
        assert state["jobs"][0]["file_sha256"] == task["resume_sha256"]


def synthetic_owned_worker(server, *, page=False):
    import time
    from types import SimpleNamespace

    from career_evidence_graph.application_readiness import CONTROLLER_PROTOCOL
    from career_evidence_graph.application_worker import start_run

    worker = server.worker_service
    worker.process_started_at = time.time()
    start_run(worker.store)
    state = worker.store.load()
    runtime = state["runtime"]
    runtime["loaded_engine_revision"] = "python-loaded-code/v1:worker:" + "b" * 64
    runtime["current_build"] = {
        "protocol": "installed-worker-start/v1",
        "controller_protocol": CONTROLLER_PROTOCOL,
        "manifest_revision": "disk-manifest-sha256:" + "a" * 64,
        "loaded_engine_revision": runtime["loaded_engine_revision"],
        "run_id": runtime["id"],
        "pid": runtime["pid"],
        "batch_id": state["batch_id"],
        "source_revision": runtime["source"]["sha256"],
    }
    worker.process = SimpleNamespace(pid=runtime["pid"], poll=lambda: None)
    worker.process_run_id = runtime["id"]
    if page:
        job = state["jobs"][0]
        job["page_open"] = True
        job["page_observation"] = {
            "run_id": runtime["id"],
            "page_id": "synthetic-owned-page",
            "event": "observed",
            "at": time.time(),
        }
    worker.store.save(state)
    return worker


def record_synthetic_retained_read(server):
    import time

    worker = server.worker_service
    state = worker.store.load()
    job = state["jobs"][0]
    job["owned_page_inspection"] = {
        "status": "captured",
        "at": time.time(),
        "binding": worker._page_inspection_target(state, job),
        "worker_source": state["runtime"]["source"]["sha256"],
        "owner": {"status": "not_used", "transport": "retained-playwright"},
    }
    worker.store.save(state)


def test_current_package_can_pause_observe_and_explicitly_resume_without_legacy_admission(
    tmp_path, monkeypatch
):
    applications, root, career, task = prepared_inputs(tmp_path)
    options = installed_evidence(monkeypatch, tmp_path)
    with create_server(
        applications.root,
        career,
        flow_root=root,
        worker_root=tmp_path / "worker",
        worker_live=True,
        **options,
    ) as server:
        worker = server.worker_service
        monkeypatch.setattr(worker, "spawn", lambda: None)
        flow = server.application_flow_service
        prepared = flow.prepare_worker(task["id"], task["revision"], "CHE", True)
        flow.worker_action(
            prepared["id"], prepared["revision"], "resume", {"controller": "synthetic-controller"}
        )
        synthetic_owned_worker(server, page=True)
        try:
            worker.request("pause", {"controller": "synthetic-controller"})
            record_synthetic_retained_read(server)
            shown = server.application_readiness(task["id"])
            assert shown["compatibility"]["kind"] == "current_package"
            assert shown["compatibility"]["commands"]["resume"] == "supported"
            assert shown["page"]["state"] == "current"
            worker.request("resume", {"controller": "synthetic-controller"})
            assert worker.store.load()["control"] == "running"
            worker.request("heartbeat", {"controller": "synthetic-controller"})
        finally:
            worker.process = None


@pytest.mark.parametrize("occupied", ["runtime", "page", "intent", "old_batch", "pending"])
def test_prepare_cannot_write_approval_over_unsettled_worker_state(tmp_path, monkeypatch, occupied):
    from career_evidence_graph.application_worker import start_run

    applications, root, career, task = prepared_inputs(tmp_path)
    options = installed_evidence(monkeypatch, tmp_path)
    with create_server(
        applications.root,
        career,
        flow_root=root,
        worker_root=tmp_path / "worker",
        worker_live=True,
        **options,
    ) as server:
        flow, worker = server.application_flow_service, server.worker_service
        flow.prepare_worker(task["id"], task["revision"], "CHE", True)
        saved = flow._load()
        target = saved["tasks"][0]
        target.update(status="materials_ready", worker_ref=None)
        flow._save(saved)
        if occupied == "runtime":
            start_run(worker.store)
        else:
            state = worker.store.load()
            job = state["jobs"][0]
            if occupied == "page":
                job["page_open"] = True
            elif occupied == "intent":
                job["intent"] = {"action": "fill", "attempt_id": "synthetic-old"}
            elif occupied == "old_batch":
                job["country"] = "USA"
            else:
                (worker.store.root / "prepare-pending.json").write_text("{}")
            worker.store.save(state)
        before_flow, before_worker = flow.path.read_bytes(), bytes_under(worker.store.root)
        claims = bytes_under(applications.root)
        with pytest.raises(PortalDataError) as stopped:
            flow.prepare_worker(target["id"], target["revision"], "CHE", True)
        assert stopped.value.code == {
            "runtime": "single_legacy_active",
            "pending": "prepare_needs_recheck",
        }.get(occupied, "flow_worker_mismatch")
        assert flow.path.read_bytes() == before_flow
        assert bytes_under(worker.store.root) == before_worker
        assert bytes_under(applications.root) == claims


@pytest.mark.parametrize("revocation", ["epoch", "closed", "permission", "binding"])
def test_local_heartbeat_ignores_expired_or_changed_maintenance_receipts(
    tmp_path, monkeypatch, revocation
):
    import time

    from career_evidence_graph import application_readiness

    applications, root, career, task = prepared_inputs(tmp_path)
    options = installed_evidence(monkeypatch, tmp_path)
    with create_server(
        applications.root,
        career,
        flow_root=root,
        worker_root=tmp_path / "worker",
        worker_live=True,
        **options,
    ) as server:
        worker, flow = server.worker_service, server.application_flow_service
        monkeypatch.setattr(worker, "spawn", lambda: None)
        prepared = flow.prepare_worker(task["id"], task["revision"], "CHE", True)
        flow.worker_action(
            prepared["id"], prepared["revision"], "resume", {"controller": "synthetic-controller"}
        )
        synthetic_owned_worker(server, page=True)
        try:
            worker.request("heartbeat", {"controller": "synthetic-controller"})
            advanced = time.time() + 31
            monkeypatch.setattr(application_readiness.time, "time", lambda: advanced)
            state = worker.store.load()
            state["runtime"]["observed_at"] = state["worker_heartbeat"] = advanced
            state["jobs"][0]["page_observation"]["at"] = advanced
            worker.store.save(state)
            native = options["native_host_identity"].receipt
            native.update(state="unknown", reason="native_receipt_stale")
            result = worker.request("heartbeat", {"controller": "synthetic-controller"})
            assert result["control"] == "running"
            assert worker.store.load()["heartbeat_at"] == advanced
            # A later diagnostic result does not revoke a healthy business command.
            native.update(state="verified", reason="permissions_verified", captured_at=advanced)
            native["daemon"]["checked_at"] = advanced
            if revocation == "epoch":
                native["invalidation_epoch"] = 1
            elif revocation == "closed":
                native["session_open"] = False
            elif revocation == "permission":
                native["accessibility"] = False
            else:
                native["instance_binding"] = dict(
                    native["instance_binding"], launch_nonce="different-synthetic-session"
                )
            before = worker.store.load()
            worker.request("heartbeat", {"controller": "synthetic-controller"})
            after = worker.store.load()
            assert after["control"] == "running"
            assert after["heartbeat_at"] == advanced
            assert after["runtime"] == before["runtime"] and after["jobs"] == before["jobs"]
        finally:
            worker.process = None


@pytest.mark.parametrize("failure", ["timeout", "exit", "replacement"])
def test_local_heartbeat_has_no_startup_lease_and_preserves_checkpoint(
    tmp_path, monkeypatch, failure
):
    import time
    from types import SimpleNamespace

    from career_evidence_graph import application_readiness

    applications, root, career, task = prepared_inputs(tmp_path)
    options = installed_evidence(monkeypatch, tmp_path)
    with create_server(
        applications.root,
        career,
        flow_root=root,
        worker_root=tmp_path / "worker",
        worker_live=True,
        **options,
    ) as server:
        worker, flow = server.worker_service, server.application_flow_service
        monkeypatch.setattr(worker, "spawn", lambda: None)
        prepared = flow.prepare_worker(task["id"], task["revision"], "CHE", True)
        flow.worker_action(
            prepared["id"], prepared["revision"], "resume", {"controller": "synthetic-controller"}
        )
        worker.process_started_at = time.time()
        worker.process = SimpleNamespace(pid=2147480001, poll=lambda: None)
        try:
            worker.request("heartbeat", {"controller": "synthetic-controller"})
            assert worker.store.load().get("runtime") is None
            assert worker.store.load()["control"] == "running"
            if failure == "timeout":
                later = time.monotonic() + 31
                monkeypatch.setattr(application_readiness.time, "monotonic", lambda: later)
            elif failure == "exit":
                worker.process.poll = lambda: 2
            else:
                worker.process = SimpleNamespace(pid=2147480002, poll=lambda: None)
                worker.process_started_at = time.time()
            before = worker.store.load()
            worker.request("heartbeat", {"controller": "synthetic-controller"})
            after = worker.store.load()
            assert after["control"] == "running" and after.get("runtime") is None
            assert after["jobs"] == before["jobs"]
            assert after["batch_id"] == before["batch_id"]
        finally:
            worker.process = None


def test_running_answer_admission_accepts_concurrent_progress_without_releasing_scope(
    tmp_path, monkeypatch
):
    import time
    from threading import Event, Thread

    applications, root, career, task = prepared_inputs(tmp_path)
    options = installed_evidence(monkeypatch, tmp_path)
    with create_server(
        applications.root,
        career,
        flow_root=root,
        worker_root=tmp_path / "worker",
        worker_live=True,
        **options,
    ) as server:
        worker, flow = server.worker_service, server.application_flow_service
        monkeypatch.setattr(worker, "spawn", lambda: None)
        prepared = flow.prepare_worker(task["id"], task["revision"], "CHE", True)
        flow.worker_action(
            prepared["id"], prepared["revision"], "resume", {"controller": "synthetic-controller"}
        )
        synthetic_owned_worker(server, page=True)
        state = worker.store.load()
        job = state["jobs"][0]
        job.update(
            status="needs_input",
            questions=[
                {"id": "synthetic-email-question", "question": "Email address", "options": []}
            ],
        )
        worker.store.save(state)
        advance, completed = Event(), Event()
        errors = []

        def progress():
            if not advance.wait(3):
                errors.append("concurrent progress was not requested")
                return
            try:
                with worker.store.applications.write_lock():
                    current = worker.store.load()
                    runtime = current["runtime"]
                    current["worker_heartbeat"] = runtime["observed_at"] = time.time()
                    active = current["jobs"][0]
                    active["status"] = "filling"
                    active["intent"] = {
                        "action": "fill",
                        "run_id": runtime["id"],
                        "page_id": active["page_observation"]["page_id"],
                        "input_refs": {
                            "revision": active["revision"],
                            "file_sha256": active["file_sha256"],
                        },
                    }
                    active["observations"].append(
                        {"action": "synthetic-progress", "run_id": runtime["id"], "at": time.time()}
                    )
                    worker.store.save(current)
            finally:
                completed.set()

        writer = Thread(target=progress)
        writer.start()
        options["native_host_identity"].before_read = lambda: pytest.fail(
            "Saving an answer must not scan native diagnostic receipts"
        )
        advance.set()
        assert completed.wait(3), "Concurrent progress must release the application write lock"
        try:
            flow.worker_action(
                prepared["id"],
                prepared["revision"],
                "answer",
                {
                    "question_id": "synthetic-email-question",
                    "value": "synthetic@example.invalid",
                    "only_this": True,
                },
            )
            current = worker.store.load()
            assert current["control"] == "running"
            assert current["commands"] == [{"action": "answers-changed"}]
            record = worker.store.library()[0]
            assert record["scope"] == {"application_id": task["application_id"]}
            assert record["value"] == "synthetic@example.invalid"
            assert current["jobs"][0]["intent"]["run_id"] == current["runtime"]["id"]
        finally:
            advance.set()
            writer.join(timeout=3)
            worker.process = None
        assert errors == [] and not writer.is_alive()


@pytest.mark.parametrize("operation", ["recheck", "answer", "library", "heartbeat"])
def test_existing_run_commands_keep_business_validation_without_diagnostic_gate(
    tmp_path, monkeypatch, operation
):
    from career_evidence_graph.application_worker import start_run

    applications, root, career, task = prepared_inputs(tmp_path)
    options = installed_evidence(monkeypatch, tmp_path)
    with create_server(
        applications.root,
        career,
        flow_root=root,
        worker_root=tmp_path / "worker",
        worker_live=True,
        **options,
    ) as server:
        flow, worker = server.application_flow_service, server.worker_service
        flow.prepare_worker(task["id"], task["revision"], "CHE", True)
        start_run(worker.store)
        state = worker.store.load()
        state["control"] = "paused" if operation == "recheck" else "running"
        state["controller"] = "synthetic-controller"
        if operation == "recheck":
            state["jobs"][0].update(
                status="needs_recheck",
                intent={"action": "fill", "attempt_id": "synthetic-unresolved"},
            )
        worker.store.save(state)
        before = bytes_under(worker.store.root)
        before_flow = flow.path.read_bytes()
        starts = []
        monkeypatch.setattr(worker, "spawn", lambda: starts.append(True))
        if operation == "heartbeat":
            worker.request(operation, {"controller": "synthetic-controller"})
            result = worker.store.load()
            assert result["runtime"] == state["runtime"]
            assert result["jobs"] == state["jobs"] and result["control"] == "running"
            assert flow.path.read_bytes() == before_flow and starts == []
            return
        with pytest.raises(PortalDataError) as stopped:
            worker.request(
                operation,
                {
                    "application_id": task["application_id"],
                    "controller": "synthetic-controller",
                    "acknowledge": True,
                },
            )
        assert (
            stopped.value.code
            == {
                "recheck": "action_unresolved",
                "answer": "question_changed",
                "library": "answer_conflict",
            }[operation]
        )
        after = bytes_under(worker.store.root)
        assert {key: value for key, value in after.items() if key != "measurements.jsonl"} == {
            key: value for key, value in before.items() if key != "measurements.jsonl"
        }
        assert after["measurements.jsonl"].startswith(before["measurements.jsonl"])
        assert flow.path.read_bytes() == before_flow and starts == []


def test_paused_local_answer_and_resolution_remain_available_without_execution_evidence(
    tmp_path, monkeypatch
):
    applications, root, career, task = prepared_inputs(tmp_path)
    worker_root = tmp_path / "worker"
    with create_server(
        applications.root,
        career,
        flow_root=root,
        worker_root=worker_root,
        worker_live=True,
        write_admission_policy="development",
    ) as development:
        development.application_flow_service.prepare_worker(
            task["id"], task["revision"], "CHE", True
        )
    with create_server(
        applications.root, career, flow_root=root, worker_root=worker_root, worker_live=True
    ) as server:
        worker = server.worker_service
        state = worker.store.load()
        job = state["jobs"][0]
        intent = {"action": "fill", "attempt_id": "synthetic-unresolved"}
        job.update(
            status="needs_input",
            intent=intent,
            questions=[{"id": "synthetic-email", "question": "Email address", "options": []}],
        )
        worker.store.save(state)
        monkeypatch.setattr(
            worker, "spawn", lambda: pytest.fail("Local saving must not start a worker")
        )
        worker.request(
            "answer",
            {
                "application_id": task["application_id"],
                "question_id": "synthetic-email",
                "value": "synthetic@example.invalid",
                "only_this": True,
            },
        )
        queued = worker.store.load()
        assert queued["control"] == "paused" and queued["jobs"][0]["intent"] == intent
        assert queued["commands"][0]["action"] == "answers-changed"
        assert worker.store.library()[0]["scope"] == {"application_id": task["application_id"]}
        worker.request(
            "resolve-action",
            {
                "application_id": task["application_id"],
                "intent_ref": intent["attempt_id"],
                "conclusion": "manual_stop",
                "source": "Synthetic local display only",
            },
        )
        saved = worker.store.load()
        assert saved["control"] == "paused" and saved["jobs"][0]["intent"] == intent
        assert saved["commands"] == queued["commands"]
        assert saved["jobs"][0]["action_resolutions"][-1]["conclusion"] == "manual_stop"
        monkeypatch.setattr(worker, "spawn", lambda: None)
        worker.request("resume", {"controller": "synthetic-controller"})
        resumed = worker.store.load()
        assert resumed["jobs"][0]["intent"] == intent
        assert resumed["jobs"][0]["action_resolutions"] == saved["jobs"][0]["action_resolutions"]
        assert resumed["commands"] == saved["commands"]
        from career_evidence_graph.application_worker_browser import ApplicationRunner

        runner = ApplicationRunner(worker.store, None)
        assert not runner.authorize(resumed["jobs"][0], resumed["batch_id"], {"action": "fill"})


def test_prepare_duplicate_scan_runs_outside_write_lock(tmp_path, monkeypatch):
    from threading import Event, Thread

    applications, root, career, task = prepared_inputs(tmp_path)
    options = installed_evidence(monkeypatch, tmp_path)
    with create_server(
        applications.root,
        career,
        flow_root=root,
        worker_root=tmp_path / "worker",
        worker_live=True,
        **options,
    ) as server:
        store = server.application_flow_service.applications
        original = store.list_applications
        scanning, acquired = Event(), Event()
        stopped = Event()

        def cooperating_reader():
            assert scanning.wait(3)
            with store.write_lock():
                acquired.set()
            stopped.set()

        def observe_scan():
            scanning.set()
            assert acquired.wait(3), "Duplicate scan must not run inside the write lock"
            return original()

        writer = Thread(target=cooperating_reader)
        writer.start()
        monkeypatch.setattr(store, "list_applications", observe_scan)
        try:
            prepared = server.application_flow_service.prepare_worker(
                task["id"], task["revision"], "CHE", True
            )
            assert prepared["status"] == "queued"
        finally:
            scanning.set()
            writer.join(timeout=3)
        assert stopped.is_set() and not writer.is_alive()


def test_same_task_unstarted_batch_reuse_keeps_attachments_and_claim(tmp_path, monkeypatch):
    applications, root, career, task = prepared_inputs(tmp_path)
    options = installed_evidence(monkeypatch, tmp_path)
    with create_server(
        applications.root,
        career,
        flow_root=root,
        worker_root=tmp_path / "worker",
        worker_live=True,
        **options,
    ) as server:
        flow, worker = server.application_flow_service, server.worker_service
        flow.prepare_worker(task["id"], task["revision"], "CHE", True)
        original = worker.store.load()
        saved = flow._load()
        current = saved["tasks"][0]
        current.update(worker_ref=None, status="materials_ready")
        flow._save(saved)
        attachments = bytes_under(worker.store.root / "attachments")
        claims = bytes_under(applications.root / ".execution")
        result = flow.prepare_worker(current["id"], current["revision"], "CHE", True)
        assert result["worker_ref"]["batch_id"] == original["batch_id"]
        assert worker.store.load() == original
        assert bytes_under(worker.store.root / "attachments") == attachments
        assert bytes_under(applications.root / ".execution") == claims


def test_another_execution_claim_stops_prepare_before_approval(tmp_path, monkeypatch):
    from career_evidence_graph.application_execution import reserve_execution

    applications, root, career, task = prepared_inputs(tmp_path)
    reserve_execution(applications, task["application_id"], "synthetic-other-owner", "codex")
    options = installed_evidence(monkeypatch, tmp_path)
    with create_server(
        applications.root,
        career,
        flow_root=root,
        worker_root=tmp_path / "worker",
        worker_live=True,
        **options,
    ) as server:
        flow, worker = server.application_flow_service, server.worker_service
        before_flow, before_worker = flow.path.read_bytes(), bytes_under(worker.store.root)
        claims = bytes_under(applications.root / ".execution")
        with pytest.raises(PortalDataError) as stopped:
            flow.prepare_worker(task["id"], task["revision"], "CHE", True)
        assert stopped.value.code == "single_legacy_active"
        assert (
            flow.path.read_bytes() == before_flow
            and bytes_under(worker.store.root) == before_worker
        )
        assert bytes_under(applications.root / ".execution") == claims


def test_reopened_controller_can_observe_and_continue_retained_page_without_package_proof(
    tmp_path, monkeypatch
):
    applications, root, career, task = prepared_inputs(tmp_path)
    options = installed_evidence(monkeypatch, tmp_path)
    arguments = {
        "flow_root": root,
        "worker_root": tmp_path / "worker",
        "worker_live": True,
        **options,
    }
    with create_server(applications.root, career, **arguments) as original:
        worker, flow = original.worker_service, original.application_flow_service
        monkeypatch.setattr(worker, "spawn", lambda: None)
        prepared = flow.prepare_worker(task["id"], task["revision"], "CHE", True)
        flow.worker_action(
            task["id"], prepared["revision"], "resume", {"controller": "synthetic-controller"}
        )
        synthetic_owned_worker(original, page=True)
        worker.request("pause", {"controller": "synthetic-controller"})
        record_synthetic_retained_read(original)
        original_state = worker.store.load()
        assert original.application_readiness(task["id"])["compatibility"]["kind"] == (
            "current_package"
        )

    with create_server(applications.root, career, **arguments) as reopened:
        worker, flow = reopened.worker_service, reopened.application_flow_service
        starts = []
        monkeypatch.setattr(worker, "spawn", lambda: starts.append(True))
        assert worker.process is None
        before = bytes_under(root), bytes_under(worker.store.root), bytes_under(applications.root)
        shown = reopened.application_readiness(task["id"])
        assert shown["worker"]["state"] == "current"
        assert shown["worker"]["process"] == "unknown"
        assert shown["compatibility"]["state"] == "unknown"
        assert shown["page"]["state"] == "current"
        assert shown["decision"]["can_observe_page"] is True
        assert shown["decision"]["can_fill"] is False
        assert before == (
            bytes_under(root),
            bytes_under(worker.store.root),
            bytes_under(applications.root),
        )
        current = flow.task_snapshot(task["id"])
        flow.worker_action(
            task["id"], current["revision"], "observe-page", {"binding": shown["page"]["binding"]}
        )
        observed = worker.store.load()
        assert observed["runtime"] == original_state["runtime"]
        assert observed["control"] == "paused"
        assert observed["commands"][0]["action"] == "observe-page"
        assert observed["jobs"][0]["intent"] == original_state["jobs"][0]["intent"]
        assert worker.process is None and starts == []
        current = flow.task_snapshot(task["id"])
        flow.worker_action(
            task["id"], current["revision"], "resume", {"controller": "synthetic-controller"}
        )
        resumed = worker.store.load()
        assert resumed["runtime"] == original_state["runtime"]
        assert resumed["batch_id"] == original_state["batch_id"]
        assert resumed["jobs"] == observed["jobs"]
        assert resumed["control"] == "running" and starts == [True]


def test_continue_lifts_a_storage_stop_once_the_checkpoint_is_writable(tmp_path, monkeypatch):
    applications, root, career, task = prepared_inputs(tmp_path)
    worker_root = tmp_path / "worker"
    with create_server(
        applications.root,
        career,
        flow_root=root,
        worker_root=worker_root,
        worker_live=True,
        write_admission_policy="development",
    ) as development:
        development.application_flow_service.prepare_worker(
            task["id"], task["revision"], "CHE", True
        )
        worker = development.worker_service
        worker.store.stop_path.write_text('{"reason":"checkpoint_unavailable"}')
        before = json.loads(worker.store.path.read_text())
        monkeypatch.setattr(worker, "spawn", lambda: None)
        worker.request("resume", {"controller": "synthetic-controller"})
        assert worker.store.stop_reason() == ""
        assert not worker.store.stop_path.exists()
        state = worker.store.load()
        assert state["control"] == "running"
        assert state["resume_serial"] == before.get("resume_serial", 0) + 1
        assert state["jobs"] == before["jobs"] or [
            job["application_id"] for job in state["jobs"]
        ] == [job["application_id"] for job in before["jobs"]]
