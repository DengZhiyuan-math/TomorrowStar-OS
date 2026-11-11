"""Retained worker continuity through the real loopback POST boundary."""

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

from career_evidence_graph import application_readiness
from career_evidence_graph.application_worker import WorkerService


@pytest.mark.parametrize(
    "policy", ["exact", "configuration", "missing", "command", "basis", "same_label_source"]
)
def test_historical_worker_resume_post_preserves_original_run_without_diagnostic_approval(
    tmp_path, monkeypatch, policy
):
    monkeypatch.setitem(
        application_readiness.VERIFIED_WORKERS,
        (application_readiness.CONTROLLER_PROTOCOL, "synthetic-old-worker", "c" * 64),
        {
            "commands": ["observe-page", "resume"],
            "basis": ["Synthetic exact retained-worker protocol contract"],
        },
    )
    with installed_portal(tmp_path, monkeypatch) as (portal, task, _, starts):
        status, prepared = post(portal, "prepare-worker", prepare_payload(task))
        assert status == 200
        worker = portal.server.worker_service
        worker.request("resume", {"controller": "synthetic-controller"})
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
            monkeypatch.setattr(worker, "spawn", WorkerService.spawn.__get__(worker))
            starts.clear()
            process = worker.process
            if policy == "configuration":
                monkeypatch.setenv("TOMORROWSTAR_CODEX_EXECUTABLE", "/synthetic/changed-codex")
            elif policy == "missing":
                monkeypatch.delitem(
                    application_readiness.VERIFIED_WORKERS,
                    (application_readiness.CONTROLLER_PROTOCOL, "synthetic-old-worker", "c" * 64),
                )
            elif policy in {"command", "basis"}:
                evidence = application_readiness.VERIFIED_WORKERS[
                    (application_readiness.CONTROLLER_PROTOCOL, "synthetic-old-worker", "c" * 64)
                ]
                if policy == "command":
                    evidence["commands"] = ["observe-page"]
                else:
                    evidence["basis"] = []
            elif policy == "same_label_source":
                state = worker.store.load()
                state["runtime"]["source"] = {
                    "sha256": "e" * 64,
                    "files": {"src/synthetic_other.py": "f" * 64},
                }
                worker.store.save(state)
                record_synthetic_retained_read(portal.server)
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
            assert status == 200, shown
            after = worker.store.load()
            assert after["control"] == "running" and worker.process is process
            assert after["runtime"] == before["runtime"]
            assert after["jobs"] == before["jobs"]
            assert after["commands"] == [] and starts == []
            saved_files = business_bytes(portal)
            assert saved_files["applications"] == retained_files["applications"]
            assert {
                name: content
                for name, content in saved_files["worker"].items()
                if name.startswith("attachments/")
            } == {
                name: content
                for name, content in retained_files["worker"].items()
                if name.startswith("attachments/")
            }
        finally:
            worker.process = None
