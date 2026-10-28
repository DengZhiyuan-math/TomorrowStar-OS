"""Maintenance setting changes preserve current business and worker bindings."""

import pytest
from test_installed_write_admission import (
    record_synthetic_retained_read,
    synthetic_owned_worker,
)
from test_installed_write_admission_http import (
    business_bytes,
    installed_portal,
    post,
    prepare_payload,
)


@pytest.mark.parametrize(
    "field", ["cdp_port", "fixture_origin", "synthetic_browser_root", "packaged_startup_identity"]
)
def test_resume_post_uses_business_binding_despite_unrelated_launch_setting_changes(
    tmp_path, monkeypatch, field
):
    with installed_portal(tmp_path, monkeypatch) as (portal, task, _, starts):
        status, prepared = post(portal, "prepare-worker", prepare_payload(task))
        assert status == 200
        flow = portal.server.application_flow_service
        worker = portal.server.worker_service
        original = flow._checked
        reached = []

        def change_after_scan(*arguments):
            result = original(*arguments)
            reached.append(True)
            if field == "packaged_startup_identity":
                worker.packaged_startup_identity = {"resources": "/synthetic/other-package"}
            elif field == "synthetic_browser_root":
                worker.synthetic_browser_root = tmp_path / "different-synthetic-context"
            elif field == "cdp_port":
                worker.cdp_port = 9222
            else:
                worker.fixture_origin = "http://127.0.0.1:65534"
            return result

        monkeypatch.setattr(flow, "_checked", change_after_scan)
        before = worker.store.load()
        retained_files = business_bytes(portal)
        status, shown = post(
            portal,
            "worker-action",
            {
                "task_id": task["id"],
                "task_revision": prepared["revision"],
                "operation": "resume",
                "payload": {"controller": "synthetic-controller"},
            },
        )
        assert reached == [True]
        assert status == 200, shown
        after = worker.store.load()
        assert after["control"] == "running" and starts == [True]
        assert after["jobs"] == before["jobs"]
        assert after["batch_id"] == before["batch_id"]
        assert business_bytes(portal)["applications"] == retained_files["applications"]


@pytest.mark.parametrize("changed", [False, True])
def test_changed_package_diagnostic_keeps_original_worker_page_and_materials(
    tmp_path, monkeypatch, changed
):
    with installed_portal(tmp_path, monkeypatch) as (portal, task, _, starts):
        status, _ = post(portal, "prepare-worker", prepare_payload(task))
        assert status == 200
        worker = portal.server.worker_service
        worker.request("resume", {"controller": "synthetic-controller"})
        synthetic_owned_worker(portal.server, page=True)
        try:
            worker.request("pause", {"controller": "synthetic-controller"})
            record_synthetic_retained_read(portal.server)
            worker.request("resume", {"controller": "synthetic-controller"})
            worker.request("heartbeat", {"controller": "synthetic-controller"})
            process = worker.process
            starts.clear()
            if changed:
                worker.packaged_startup_identity = {"worker": "synthetic-changed-loaded-worker"}
            before = worker.store.load()
            retained_files = business_bytes(portal)
            worker.request("heartbeat", {"controller": "synthetic-controller"})
            state = worker.store.load()
            assert state["control"] == "running"
            assert state["runtime"] == before["runtime"] and state["jobs"] == before["jobs"]
            assert business_bytes(portal)["applications"] == retained_files["applications"]
            assert worker.process is process and starts == []
        finally:
            worker.process = None
