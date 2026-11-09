"""Retained human acceptance can be recorded and reused without execution."""

import json
from pathlib import Path

import pytest
from test_application_flow import application as application
from test_existing_latex import existing_latex as existing_latex
from test_flow_review_snapshot_adoption import recoverable as recoverable

from career_evidence_graph.application_flow import ApplicationFlowService
from career_evidence_graph.application_flow_store import read_flow_state
from career_evidence_graph.application_worker import digest
from career_evidence_graph.career_portal_data import PortalDataError


@pytest.fixture
def accepted_candidate(recoverable):
    flow, store, client, _previous, adoption, _project = recoverable
    task = flow.request("adopt-review-snapshot", adoption)

    def verify_materials(task):
        saved = store.read_export(task["resume_id"])
        assert saved["pdf_sha256"] == task["resume_sha256"]
        assert saved["draft_sha256"] == task["draft_sha256"]

    flow.callbacks["verify_materials"] = verify_materials
    payload = {
        "task_id": task["id"],
        "task_revision": task["revision"],
        "resume_id": task["resume_id"],
        "resume_sha256": task["resume_sha256"],
        "source_sha256": task["prism"]["files"][task["prism"]["main"]],
        "approval_record": {
            "sha256": "c" * 64,
            "accepted_at": "2026-10-19T12:30:00Z",
            "statement": (
                "这份 PDF 的内容和排版可以，按这版保存并绑定到 App/Prism；真实申请继续暂停。"
            ),
        },
    }
    return flow, store, client, task, payload


def test_record_existing_human_decision_binds_exact_material_without_claiming_a_new_review(
    accepted_candidate,
):
    flow, _store, client, previous, payload = accepted_candidate
    task = flow.request("record-retained-material-acceptance", payload)
    acceptance = task["material_acceptance"]
    assert acceptance["approval_record"] == payload["approval_record"]
    assert acceptance["operator_record"]["actor"] == "codex"
    assert acceptance["pdf_sha256"] == payload["resume_sha256"]
    assert acceptance["source_sha256"] == payload["source_sha256"]
    assert task["status"] == "materials_ready" and task["materials_confirmed"] is True
    assert task["origin"] == "existing_latex" and task["factual_review"] == "pending"
    assert task["export_recoveries"] == previous["export_recoveries"]
    assert task["worker_ref"] is None
    assert client.calls == ["compile", "unknown_compile"]
    before = flow.path.read_bytes()
    assert flow.request("record-retained-material-acceptance", payload) == task
    assert flow.path.read_bytes() == before
    assert (
        flow.request(
            "record-retained-material-acceptance", payload | {"task_revision": task["revision"]}
        )
        == task
    )
    assert flow.path.read_bytes() == before


def test_accepted_material_batch_reuses_exact_task_and_decision_without_queueing(
    accepted_candidate,
):
    flow, _store, client, _previous, payload = accepted_candidate
    task = flow.request("record-retained-material-acceptance", payload)
    request = {"request_id": "d" * 32, "task_id": task["id"], "task_revision": task["revision"]}
    batch = flow.request("batch-adopt-accepted-material", request)
    assert batch["control"] == "paused"
    assert batch["active_task_id"] == task["id"]
    assert len(batch["items"]) == 1
    assert batch["items"][0]["status"] == "waiting_application_record"
    assert (
        batch["retained_material"]["material_acceptance_revision"]
        == task["material_acceptance"]["revision"]
    )
    assert len(flow.snapshot()["tasks"]) == 1
    assert flow._queue.empty()
    before = flow.path.read_bytes()
    assert flow.request("batch-adopt-accepted-material", request) == batch
    assert flow.path.read_bytes() == before
    another = flow.request("batch-adopt-accepted-material", request | {"request_id": "e" * 32})
    assert another["id"] == batch["id"]
    before = flow.path.read_bytes()
    assert (
        flow.request("batch-adopt-accepted-material", request | {"request_id": "e" * 32}) == another
    )
    assert flow.path.read_bytes() == before
    assert len(flow.snapshot()["tasks"]) == 1
    assert client.calls == ["compile", "unknown_compile"]


def test_retained_acceptance_does_not_allow_internal_worker_binding(accepted_candidate):
    flow, _store, client, _previous, payload = accepted_candidate
    task = flow.request("record-retained-material-acceptance", payload)
    before = flow.path.read_bytes()
    with pytest.raises(PortalDataError):
        flow.bind_worker(
            task["id"],
            task["revision"],
            {"batch_id": "synthetic", "job_id": task["application_id"], "status": "queued"},
        )
    assert flow.path.read_bytes() == before
    assert client.calls == ["compile", "unknown_compile"]


@pytest.mark.parametrize(
    "damage",
    [
        "pdf",
        "source",
        "resume_id",
        "task_revision",
        "approval_sha",
        "approval_time",
        "approval_statement",
        "approval_extra",
        "current_source",
        "current_inputs",
        "compiler",
        "verifier",
    ],
)
def test_recording_rejects_unbound_or_changed_materials_without_writes(accepted_candidate, damage):
    flow, _store, client, _previous, payload = accepted_candidate
    if damage in {"pdf", "source", "resume_id", "task_revision"}:
        field = {"pdf": "resume_sha256", "source": "source_sha256"}.get(damage, damage)
        payload[field] = "0" * (32 if field == "resume_id" else 64)
    elif damage.startswith("approval_"):
        key = damage.removeprefix("approval_")
        payload["approval_record"] = payload["approval_record"] | {
            {"sha": "sha256", "time": "accepted_at"}.get(key, key): {
                "sha": "not-sha",
                "time": "2026-10-19T12:30:00",
                "statement": "",
                "extra": True,
            }[key]
        }
    elif damage == "current_source":
        task = flow.snapshot()["active_task"]
        (Path(task["prism"]["project_root"]) / "main.tex").write_text("Changed")
    elif damage == "current_inputs":
        provider = flow.input_provider
        flow.input_provider = lambda identifier: provider(identifier) | {"inputs": {"v": "changed"}}
    elif damage == "compiler":
        flow.callbacks["prism_export_configuration"] = lambda: "changed"
    else:
        flow.callbacks.pop("verify_materials")
    before = flow.path.read_bytes()
    with pytest.raises(PortalDataError):
        flow.request("record-retained-material-acceptance", payload)
    assert flow.path.read_bytes() == before
    assert client.calls == ["compile", "unknown_compile"]


def test_post_verification_input_change_rejects_retained_decision(accepted_candidate):
    flow, _store, _client, _previous, payload = accepted_candidate
    verify = flow.callbacks["verify_materials"]
    provider = flow.input_provider

    def change(task):
        verify(task)
        flow.input_provider = lambda identifier: provider(identifier) | {"inputs": {"v": "changed"}}

    flow.callbacks["verify_materials"] = change
    before = flow.path.read_bytes()
    with pytest.raises(PortalDataError):
        flow.request("record-retained-material-acceptance", payload)
    assert flow.path.read_bytes() == before


def test_conflicting_human_decision_cannot_replace_retained_acceptance(accepted_candidate):
    flow, _store, _client, _previous, payload = accepted_candidate
    task = flow.request("record-retained-material-acceptance", payload)
    before = flow.path.read_bytes()
    with pytest.raises(PortalDataError):
        flow.request(
            "record-retained-material-acceptance",
            payload
            | {
                "task_revision": task["revision"],
                "approval_record": payload["approval_record"] | {"statement": "Different decision"},
            },
        )
    assert flow.path.read_bytes() == before


def test_retained_material_batch_stays_paused_across_reopen_and_all_execution_requests(
    accepted_candidate,
):
    flow, _store, client, _previous, payload = accepted_candidate
    task = flow.request("record-retained-material-acceptance", payload)
    batch = flow.request(
        "batch-adopt-accepted-material",
        {"request_id": "f" * 32, "task_id": task["id"], "task_revision": task["revision"]},
    )
    before = flow.path.read_bytes()
    for operation in ("resume", "cancel"):
        with pytest.raises(PortalDataError):
            flow.request(
                "batch-control",
                {
                    "batch_id": batch["id"],
                    "batch_revision": batch["revision"],
                    "operation": operation,
                },
            )
    with pytest.raises(PortalDataError):
        flow.request(
            "batch-create",
            {
                "request_id": "a" * 32,
                "items": [
                    {
                        "kind": "application",
                        "id": task["application_id"],
                        "revision": task["application_revision"],
                    }
                ],
            },
        )
    flow.material_batch.advance(batch["id"], batch["epoch"])
    assert flow.path.read_bytes() == before
    flow.close()
    reopened = ApplicationFlowService(
        flow.applications,
        flow.root,
        preparation_only=True,
        callbacks=flow.callbacks,
        input_provider=flow.input_provider,
    )
    try:
        assert (
            reopened.snapshot()["active_task"]["material_acceptance"] == task["material_acceptance"]
        )
        assert reopened.snapshot()["preparation_batch"] == batch
        assert reopened.path.read_bytes() == before
        assert reopened._queue.empty()
        assert client.calls == ["compile", "unknown_compile"]
    finally:
        reopened.close()


def test_retained_receipt_tampering_fails_even_when_outer_task_revision_is_resealed(
    accepted_candidate,
):
    flow, _store, _client, _previous, payload = accepted_candidate
    flow.request("record-retained-material-acceptance", payload)
    original = flow.path.read_bytes()
    state = read_flow_state(flow.path.parent)
    task = state["tasks"][0]
    task["material_acceptance"]["approval_record"]["statement"] = "Altered decision"
    task["revision"] = digest({key: value for key, value in task.items() if key != "revision"})
    try:
        flow.path.write_text(json.dumps(state))
        with pytest.raises(PortalDataError):
            flow.snapshot()
    finally:
        flow.path.write_bytes(original)


@pytest.mark.parametrize("damage", ["source", "compiler"])
def test_verifier_cannot_change_material_binding_during_acceptance(accepted_candidate, damage):
    flow, _store, _client, _previous, payload = accepted_candidate
    verify = flow.callbacks["verify_materials"]

    def change(task):
        verify(task)
        if damage == "source":
            (Path(task["prism"]["project_root"]) / "main.tex").write_text(
                "Changed during verification"
            )
        else:
            flow.callbacks["prism_export_configuration"] = lambda: "changed"

    flow.callbacks["verify_materials"] = change
    before = flow.path.read_bytes()
    with pytest.raises(PortalDataError):
        flow.request("record-retained-material-acceptance", payload)
    assert flow.path.read_bytes() == before


def test_batch_adoption_requires_separate_retained_human_decision(accepted_candidate):
    flow, _store, client, task, _payload = accepted_candidate
    before = flow.path.read_bytes()
    with pytest.raises(PortalDataError) as error:
        flow.request(
            "batch-adopt-accepted-material",
            {"request_id": "a" * 32, "task_id": task["id"], "task_revision": task["revision"]},
        )
    assert error.value.code == "flow_batch_material_acceptance_required"
    assert flow.path.read_bytes() == before
    assert client.calls == ["compile", "unknown_compile"]


def test_ordinary_batch_creation_remains_blocked_by_the_original_unknown_request(
    accepted_candidate,
):
    flow, _store, _client, _previous, payload = accepted_candidate
    task = flow.request("record-retained-material-acceptance", payload)
    before = flow.path.read_bytes()
    with pytest.raises(PortalDataError) as error:
        flow.request(
            "batch-create",
            {
                "request_id": "a" * 32,
                "items": [
                    {
                        "kind": "application",
                        "id": task["application_id"],
                        "revision": task["application_revision"],
                    }
                ],
            },
        )
    assert error.value.code == "flow_batch_existing_work"
    assert flow.path.read_bytes() == before


def test_normal_confirmation_still_cannot_treat_imported_latex_as_group_reviewed(
    accepted_candidate,
):
    flow, _store, _client, task, _payload = accepted_candidate
    with pytest.raises(PortalDataError) as error:
        flow.confirm_materials(
            task["id"], task["revision"], task["resume_id"], task["resume_sha256"]
        )
    assert error.value.code == "flow_factual_review_required"
