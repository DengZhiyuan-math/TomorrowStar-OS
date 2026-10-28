"""Maintenance diagnosis stays separate from local POST and heartbeat commands."""

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
    "revocation", [None, "not_declared", "removed", "commands", "basis", "runtime_identity"]
)
def test_retained_worker_heartbeat_does_not_depend_on_compatibility_diagnostic_policy(
    tmp_path, monkeypatch, revocation
):
    from career_evidence_graph import application_readiness

    monkeypatch.setitem(
        application_readiness.VERIFIED_WORKERS,
        (application_readiness.CONTROLLER_PROTOCOL, "synthetic-old-worker", "c" * 64),
        {
            "commands": ["observe-page", "resume"]
            + ([] if revocation == "not_declared" else ["heartbeat"]),
            "basis": ["Synthetic exact retained-worker protocol contract"],
        },
    )
    with installed_portal(tmp_path, monkeypatch) as (portal, task, _, starts):
        status, _ = post(portal, "prepare-worker", prepare_payload(task))
        assert status == 200
        portal.server.worker_service.request("resume", {"controller": "synthetic-controller"})
        starts.clear()
        worker = synthetic_owned_worker(portal.server, page=True)
        try:
            state = worker.store.load()
            runtime = state["runtime"]
            runtime.pop("current_build")
            runtime["loaded_engine_revision"] = "synthetic-old-worker"
            runtime["source"] = {"sha256": "c" * 64, "files": {"src/synthetic_old.py": "d" * 64}}
            worker.store.save(state)
            worker.request("pause", {"controller": "synthetic-controller"})
            record_synthetic_retained_read(portal.server)
            shown = portal.server.application_readiness(task["id"])
            assert shown["page"]["state"] == "current", shown
            assert shown["compatibility"]["state"] == "verified", shown
            from career_evidence_graph.application_worker import WorkerService

            monkeypatch.setattr(worker, "spawn", WorkerService.spawn.__get__(worker))
            retained_process = worker.process
            before = worker.store.load()
            worker.request("resume", {"controller": "synthetic-controller"})
            worker.request("heartbeat", {"controller": "synthetic-controller"})
            after = worker.store.load()
            assert after["control"] == "running" and worker.process is retained_process
            assert after["runtime"]["id"] == before["runtime"]["id"]
            assert after["jobs"][0]["page_observation"] == before["jobs"][0]["page_observation"]
            assert after["jobs"][0]["file_sha256"] == before["jobs"][0]["file_sha256"]
            assert after["commands"] == [] and starts == []
            if revocation is not None:
                key = (application_readiness.CONTROLLER_PROTOCOL, "synthetic-old-worker", "c" * 64)
                if revocation == "removed":
                    monkeypatch.delitem(application_readiness.VERIFIED_WORKERS, key)
                elif revocation == "commands":
                    application_readiness.VERIFIED_WORKERS[key]["commands"].remove("heartbeat")
                elif revocation == "basis":
                    application_readiness.VERIFIED_WORKERS[key]["basis"] = ["Changed evidence"]
                elif revocation == "runtime_identity":
                    after["runtime"]["loaded_engine_revision"] = "synthetic-other-worker"
                    worker.store.save(after)
                before_command = worker.store.load()
                retained_files = business_bytes(portal)
                worker.request("heartbeat", {"controller": "synthetic-controller"})
                current = worker.store.load()
                assert current["control"] == "running" and starts == []
                assert current["runtime"] == before_command["runtime"]
                assert current["jobs"] == before_command["jobs"]
                assert worker.process is retained_process
                assert business_bytes(portal)["applications"] == retained_files["applications"]
        finally:
            worker.process = None


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("native_pid", 999),
        ("backend_pid", 999),
        ("bundle_id", "synthetic.other.app"),
        ("executable", "/synthetic/OtherApp"),
        ("session_open", False),
        ("scope", "same_bundle_background_probe"),
        ("invalidation_epoch", -1),
    ],
)
def test_prepare_post_ignores_unrelated_host_or_bridge_diagnostic(
    tmp_path, monkeypatch, field, value
):
    with installed_portal(tmp_path, monkeypatch) as (portal, task, options, starts):
        options["native_host_identity"].receipt[field] = value
        status, shown = post(portal, "prepare-worker", prepare_payload(task))
        assert status == 200 and shown["status"] == "queued"
        state = portal.server.worker_service.store.load()
        assert state["control"] == "paused" and not state.get("runtime")
        assert state["jobs"][0]["application_id"] == task["application_id"]
        assert state["jobs"][0]["file_sha256"] == task["resume_sha256"]
        assert starts == []


def test_prepare_post_keeps_current_materials_when_diagnostic_age_expires_during_scan(
    tmp_path, monkeypatch
):
    import time

    from career_evidence_graph import application_readiness

    with installed_portal(tmp_path, monkeypatch) as (portal, task, _, starts):
        flow = portal.server.application_flow_service
        original = flow._checked
        reached = []
        expired = time.time() + 31

        def advance_clock_after_scan(*arguments):
            result = original(*arguments)
            reached.append(True)
            monkeypatch.setattr(application_readiness.time, "time", lambda: expired)
            return result

        monkeypatch.setattr(flow, "_checked", advance_clock_after_scan)
        status, shown = post(portal, "prepare-worker", prepare_payload(task))
        assert reached
        assert status == 200 and shown["status"] == "queued"
        state = portal.server.worker_service.store.load()
        assert state["control"] == "paused" and not state.get("runtime")
        assert state["jobs"][0]["file_sha256"] == task["resume_sha256"]
        assert starts == []
