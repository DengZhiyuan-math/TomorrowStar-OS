"""Retained human decisions bind exact material without replaying real work."""

import hashlib

import pytest
from test_career_portal_http import portal as portal
from test_preparation_entry import post, snapshot
from test_review_snapshot_adoption_http import (
    adoption_payload,
    assert_no_replay,
)
from test_review_snapshot_adoption_http import (
    unknown_export_with_review as unknown_export_with_review,
)

from career_evidence_graph.career_portal_data import ApplicationStore


@pytest.fixture
def recovered_material(unknown_export_with_review):
    case = unknown_export_with_review
    status, task = post(case["active"], "adopt-review-snapshot", adoption_payload(case))
    assert status == 200, task
    case["task"] = task
    case["approval"] = {
        "sha256": hashlib.sha256(b"Synthetic retained human decision receipt").hexdigest(),
        "accepted_at": "2026-10-19T12:00:00Z",
        "statement": "Synthetic acceptance of exact PDF content and layout. Applications paused.",
    }
    return case


def acceptance_payload(case):
    task = case["task"]
    return {
        "task_id": task["id"],
        "task_revision": task["revision"],
        "resume_id": task["resume_id"],
        "resume_sha256": task["resume_sha256"],
        "source_sha256": case["version"]["source_sha256"],
        "approval_record": case["approval"],
    }


def test_retained_acceptance_and_batch_adoption_are_idempotent_metadata_only(recovered_material):
    case = recovered_material
    active = case["active"]
    task = case["task"]
    original_recoveries = task["export_recoveries"]
    exports = active.server.application_resume_store.root
    original_export_files = {
        str(path.relative_to(exports)): path.read_bytes()
        for path in exports.rglob("*")
        if path.is_file()
    }
    payload = acceptance_payload(case)
    status, task = post(active, "record-retained-material-acceptance", payload)
    assert status == 200, task
    assert task["materials_confirmed"] is True and task["status"] == "materials_ready"
    receipt = task["material_acceptance"]
    assert receipt["kind"] == "retained_human_material_acceptance"
    assert receipt["approval_record"] == case["approval"]
    assert receipt["source_sha256"] == case["version"]["source_sha256"]
    assert receipt["pdf_sha256"] == case["version"]["pdf_sha256"]
    assert receipt["human_actor"] == "user"
    assert receipt["operator_record"]["operation"] == "record_existing_human_decision"
    assert task["origin"] == "existing_latex" and task["factual_review"] == "pending"
    assert task["export_recoveries"] == original_recoveries
    assert task["worker_ref"] is None and not task.get("send_approval")
    status, repeated = post(active, "record-retained-material-acceptance", payload)
    assert status == 200 and repeated == task
    assert (
        post(
            active,
            "confirm-materials",
            {
                "task_id": task["id"],
                "task_revision": task["revision"],
                "resume_id": task["resume_id"],
                "resume_sha256": task["resume_sha256"],
            },
        )[0]
        == 409
    )
    batch_payload = {
        "request_id": "a" * 32,
        "task_id": task["id"],
        "task_revision": task["revision"],
    }
    status, batch = post(active, "batch-adopt-accepted-material", batch_payload)
    assert status == 200, batch
    assert batch["control"] == "paused"
    assert len(batch["items"]) == 1
    assert batch["items"][0]["task_id"] == task["id"]
    assert batch["items"][0]["status"] == "waiting_application_record"
    status, repeated = post(active, "batch-adopt-accepted-material", batch_payload)
    assert status == 200 and repeated == batch
    status, repeated = post(
        active, "batch-adopt-accepted-material", batch_payload | {"request_id": "b" * 32}
    )
    assert status == 200 and repeated["id"] == batch["id"]
    assert repeated["items"] == batch["items"] and repeated["control"] == "paused"
    batch = repeated
    state = snapshot(active)
    assert state["preparation_batch"] == batch
    assert len(state["tasks"]) == 1 and state["active_task"]["id"] == task["id"]
    assert state["active_task"]["material_acceptance"] == receipt
    assert state["pdf_integrity"]["status"] == "valid"
    assert state["capabilities"]["worker"] is False and active.server.worker_service is None
    status, _, pdf = active.request("GET", f"/api/flow/resumes/{task['resume_id']}/pdf")
    assert status == 200 and hashlib.sha256(pdf).hexdigest() == receipt["pdf_sha256"]
    status, response = post(
        active,
        "batch-control",
        {"batch_id": batch["id"], "batch_revision": batch["revision"], "operation": "resume"},
    )
    assert status == 409, response
    assert snapshot(active)["preparation_batch"] == batch
    assert {
        str(path.relative_to(exports)): path.read_bytes()
        for path in exports.rglob("*")
        if path.is_file()
    } == original_export_files
    assert_no_replay(case)


@pytest.mark.parametrize("damage", ["pdf-hash", "source-hash", "jd-change"])
def test_retained_acceptance_refuses_material_or_current_job_drift(recovered_material, damage):
    case = recovered_material
    payload = acceptance_payload(case)
    if damage == "pdf-hash":
        payload["resume_sha256"] = "0" * 64
    elif damage == "source-hash":
        payload["source_sha256"] = "0" * 64
    else:
        applications = ApplicationStore(case["active"].applications)
        current = applications.get_application(case["task"]["application_id"])
        applications.update_application(
            current["id"], {"job_description": "Changed synthetic JD"}, current["revision"]
        )
    status, response = post(case["active"], "record-retained-material-acceptance", payload)
    assert status == 409, response
    state = snapshot(case["active"])
    assert not state["active_task"].get("material_acceptance")
    assert state["active_task"]["materials_confirmed"] is False
    assert state["active_task"]["worker_ref"] is None
    assert state["active_task"]["export_recoveries"] == case["task"]["export_recoveries"]
    assert_no_replay(case)
