"""Each owner adopts only its exact side of the existing material journal."""

from copy import deepcopy

import pytest
from test_application_resume import task_resume as task_resume
from test_bound_material_commit_recovery import interrupted_commit as interrupted_commit
from test_bound_material_update import bound_pipeline as bound_pipeline
from test_full_latex_generation import full_latex as full_latex

from career_evidence_graph import application_bound_materials as materials
from career_evidence_graph._vendor import job_apply_store as helper
from career_evidence_graph.career_portal_data import PortalDataError
from career_evidence_graph.validation.hashing import record_digest as digest


def restore_old_flow(flow, journal):
    local = flow._load()
    original = deepcopy(journal["new"]["material_update"]["old"])
    original["artifacts"] = deepcopy(
        next(row for row in local["tasks"] if row["id"] == journal["task_id"])["artifacts"]
    )
    original["material_update"] = deepcopy(journal["new"]["material_update"])
    original["material_update"].update(status="awaiting_page", candidate=deepcopy(journal["new"]))
    local["tasks"] = [
        original if row["id"] == journal["task_id"] else row for row in local["tasks"]
    ]
    flow._save(local)
    return original


def test_flow_material_commit_is_idempotent_at_the_new_side(interrupted_commit):
    server, _, _, candidate, path = interrupted_commit
    flow, worker, pipeline = (
        server.application_flow_service,
        server.worker_service,
        server.application_pipeline_service,
    )
    task = flow.snapshot()["active_task"]
    before = (
        flow.path.read_bytes(),
        worker.store.path.read_bytes(),
        pipeline.path.read_bytes(),
        path.read_bytes(),
    )
    result = flow.commit_material_candidate(task["id"], path.stem)
    assert result["resume_id"] == candidate["resume_id"]
    assert (
        flow.path.read_bytes(),
        worker.store.path.read_bytes(),
        pipeline.path.read_bytes(),
        path.read_bytes(),
    ) == before


def test_flow_bound_delivery_does_not_reopen_committing(interrupted_commit):
    server, _, _, _, path = interrupted_commit
    flow, worker, pipeline = (
        server.application_flow_service,
        server.worker_service,
        server.application_pipeline_service,
    )
    pipeline.pause()
    pipeline.continue_current(request_id="recover-before-late-flow-delivery")
    task = flow.task_snapshot(pipeline.snapshot()["active_task_id"])
    assert task["material_update"]["status"] == "bound"
    files = (flow.path, worker.store.path, pipeline.path, path)
    before = tuple(item.read_bytes() for item in files)
    result = flow.commit_material_candidate(task["id"], path.stem)
    assert result["material_update"]["status"] == "bound"
    assert tuple(item.read_bytes() for item in files) == before


def test_worker_material_commit_changes_only_its_exact_journal_side(interrupted_commit):
    import json

    server, _, _, candidate, path = interrupted_commit
    flow, worker, pipeline = (
        server.application_flow_service,
        server.worker_service,
        server.application_pipeline_service,
    )
    journal = json.loads(path.read_text())
    before = flow.path.read_bytes(), pipeline.path.read_bytes(), path.read_bytes()
    result = worker.commit_material_update(
        journal["application_id"], path.stem, expected_batch_id=journal["batch_id"]
    )
    assert result["status"] == "bound"
    current = worker.store.load()
    assert current["jobs"][0]["single_binding"]["resume_id"] == candidate["resume_id"]
    saved = worker.store.path.read_bytes()
    worker.commit_material_update(
        journal["application_id"], path.stem, expected_batch_id=journal["batch_id"]
    )
    assert worker.store.path.read_bytes() == saved
    assert (flow.path.read_bytes(), pipeline.path.read_bytes(), path.read_bytes()) == before


def test_pipeline_adopts_only_its_saved_transmission_authorization(interrupted_commit):
    import json

    server, _, _, candidate, path = interrupted_commit
    flow, worker, pipeline = (
        server.application_flow_service,
        server.worker_service,
        server.application_pipeline_service,
    )
    journal = json.loads(path.read_text())
    before = flow.path.read_bytes(), worker.store.path.read_bytes(), path.read_bytes()
    result = pipeline.commit_material_authorization(path.stem)
    assert result["transmission_authorization"]["resume_id"] == candidate["resume_id"]
    assert result["transmission_authorization"] == journal["new_receipt"]
    raw = pipeline.path.read_bytes()
    pipeline.commit_material_authorization(path.stem)
    assert pipeline.path.read_bytes() == raw
    assert (flow.path.read_bytes(), worker.store.path.read_bytes(), path.read_bytes()) == before


@pytest.mark.parametrize(
    "corruption", ["worker_fields", "authorization_fields", "worker_scalar_type"]
)
def test_all_owner_preflights_reject_before_any_participant_write(interrupted_commit, corruption):
    import json

    server, _, _, _, path = interrupted_commit
    flow, worker, pipeline = (
        server.application_flow_service,
        server.worker_service,
        server.application_pipeline_service,
    )
    journal = json.loads(path.read_text())
    restore_old_flow(flow, journal)
    assert flow.validate_material_candidate(journal["task_id"], journal["id"])["status"] == "ready"
    assert flow.task_snapshot(journal["task_id"])["resume_id"] != journal["new"]["resume_id"]
    if corruption == "worker_fields":
        journal["old_job"]["questions"] = deepcopy(worker.store.load()["jobs"][0]["questions"])
        journal["new_job"]["questions"] = deepcopy(journal["old_job"]["questions"])
    elif corruption == "authorization_fields":
        journal["new_receipt"]["final_submit"] = "automatic"
        journal["new"]["send_approval"]["authorization"] = deepcopy(journal["new_receipt"])
    else:
        current = worker.store.load()
        current["jobs"][0]["material_update"]["verified"] = True
        worker.store.save(current)
        journal["old_job"]["material_update"]["verified"] = True
        journal["new_job"]["material_update"]["verified"] = 1
    journal["revision"] = digest(
        {key: value for key, value in journal.items() if key != "revision"}
    )
    helper.atomic_write_json(path, journal)
    before = (
        flow.path.read_bytes(),
        worker.store.path.read_bytes(),
        pipeline.path.read_bytes(),
        path.read_bytes(),
    )
    with pytest.raises(PortalDataError) as error:
        materials.recover_commit(pipeline, pipeline._load(), path)
    assert error.value.code == "bound_material_journal_conflict"
    assert (
        flow.path.read_bytes(),
        worker.store.path.read_bytes(),
        pipeline.path.read_bytes(),
        path.read_bytes(),
    ) == before


def test_material_candidate_cannot_erase_a_later_human_letter(interrupted_commit):
    import json

    server, _, _, _, path = interrupted_commit
    flow = server.application_flow_service
    journal = json.loads(path.read_text())
    restore_old_flow(flow, journal)
    local = flow._load()
    task = flow._task(local, journal["task_id"])
    letter = {
        "status": "ready",
        "attempt_id": "late-human-letter",
        "human_edit_id": "f" * 32,
        "result": {"actor": "user", "text": "Retain the user's newer letter body."},
        "content_history": [{"actor": "system", "text": "Older letter body."}],
    }
    task["cover_letter"] = deepcopy(letter)
    task["cover_letter_history"] = [{"status": "superseded", "result": {"actor": "user"}}]
    flow._save(local)
    result = flow.commit_material_candidate(journal["task_id"], journal["id"])
    assert result["cover_letter"] == letter
    assert result["cover_letter_history"] == task["cover_letter_history"]
    assert result["resume_id"] == journal["new"]["resume_id"]


def test_material_candidate_rejects_a_third_letter_when_both_sides_changed(interrupted_commit):
    import json

    server, _, _, _, path = interrupted_commit
    flow = server.application_flow_service
    journal = json.loads(path.read_text())
    restore_old_flow(flow, journal)
    candidate_letter = {"status": "ready", "result": {"text": "Candidate letter."}}
    journal["new"]["cover_letter"] = deepcopy(candidate_letter)
    journal["revision"] = digest({key: row for key, row in journal.items() if key != "revision"})
    helper.atomic_write_json(path, journal)
    local = flow._load()
    task = flow._task(local, journal["task_id"])
    task["material_update"]["candidate"]["cover_letter"] = deepcopy(candidate_letter)
    task["cover_letter"] = {
        "status": "ready",
        "result": {"actor": "user", "text": "Third human letter."},
    }
    flow._save(local)
    before = flow.path.read_bytes(), path.read_bytes()
    with pytest.raises(PortalDataError) as error:
        flow.commit_material_candidate(journal["task_id"], journal["id"])
    assert error.value.code == "bound_material_journal_conflict"
    assert (flow.path.read_bytes(), path.read_bytes()) == before


def test_late_preparation_cancel_rejects_a_saved_material_candidate(interrupted_commit):
    server, _, _, _, path = interrupted_commit
    flow, worker, pipeline = (
        server.application_flow_service,
        server.worker_service,
        server.application_pipeline_service,
    )
    task = flow.task_snapshot(pipeline.snapshot()["active_task_id"])
    flow.cancel_preparation(task["id"], task["revision"])
    before = (
        flow.path.read_bytes(),
        worker.store.path.read_bytes(),
        pipeline.path.read_bytes(),
        path.read_bytes(),
    )
    with pytest.raises(PortalDataError):
        flow.commit_material_candidate(task["id"], path.stem)
    assert (
        flow.path.read_bytes(),
        worker.store.path.read_bytes(),
        pipeline.path.read_bytes(),
        path.read_bytes(),
    ) == before


@pytest.mark.parametrize("change", ["epoch", "attempt"])
def test_material_candidate_rejects_a_changed_preparation_scope(interrupted_commit, change):
    import json

    server, _, _, _, path = interrupted_commit
    flow = server.application_flow_service
    journal = json.loads(path.read_text())
    restore_old_flow(flow, journal)
    local = flow._load()
    task = flow._task(local, journal["task_id"])
    if change == "epoch":
        task["input_epoch"] = task.get("input_epoch", 0) + 1
    else:
        task["stages"]["resume"]["attempt_id"] = "another-resume-attempt"
    flow._save(local)
    before = flow.path.read_bytes()
    with pytest.raises(PortalDataError) as error:
        flow.commit_material_candidate(journal["task_id"], journal["id"])
    assert error.value.code == "bound_material_journal_conflict"
    assert flow.path.read_bytes() == before


@pytest.mark.parametrize("change", ["claim", "controller", "resume_serial"])
def test_worker_rejects_a_journal_for_another_execution_scope(interrupted_commit, change):
    import json

    server, _, _, _, path = interrupted_commit
    worker = server.worker_service
    journal = json.loads(path.read_text())
    if change == "claim":
        journal["execution_claim"] = {"id": "another-claim"}
    elif change == "controller":
        current = worker.store.load()
        journal["worker_controller"] = current["controller"]
        current["controller"] = "another-controller"
        worker.store.save(current)
    else:
        current = worker.store.load()
        journal["worker_resume_serial"] = current.get("resume_serial", 0)
        current["resume_serial"] = current.get("resume_serial", 0) + 1
        worker.store.save(current)
    journal["revision"] = digest({key: row for key, row in journal.items() if key != "revision"})
    helper.atomic_write_json(path, journal)
    before = worker.store.path.read_bytes()
    with pytest.raises(PortalDataError) as error:
        worker.commit_material_update(
            journal["application_id"], journal["id"], expected_batch_id=journal["batch_id"]
        )
    assert error.value.code == "bound_material_journal_conflict"
    assert worker.store.path.read_bytes() == before


def test_public_continue_keeps_recovery_projection_unsaved_until_all_preflights(
    interrupted_commit, monkeypatch
):
    import json

    server, _, _, _, path = interrupted_commit
    flow, worker, pipeline = (
        server.application_flow_service,
        server.worker_service,
        server.application_pipeline_service,
    )
    pipeline.pause()
    before = flow.path.read_bytes(), worker.store.path.read_bytes(), path.read_bytes()
    checked = []

    def reject(*_a, **_k):
        persisted = json.loads(pipeline.path.read_text())
        assert persisted["control"] == "paused"
        assert persisted["current_requests"][-1]["status"] == "dispatching"
        assert (flow.path.read_bytes(), worker.store.path.read_bytes(), path.read_bytes()) == before
        checked.append(True)
        raise PortalDataError(
            "bound_material_journal_conflict", "Synthetic participant conflict", 409
        )

    monkeypatch.setattr(worker, "validate_material_update", reject)
    with pytest.raises(PortalDataError):
        pipeline.continue_current(request_id="preflight-must-not-resume")
    assert checked == [True]
    assert (flow.path.read_bytes(), worker.store.path.read_bytes(), path.read_bytes()) == before
    persisted = json.loads(pipeline.path.read_text())
    assert persisted["control"] == "paused"
    assert persisted["current_requests"][-1]["status"] == "needs_recheck"


def test_completed_original_page_update_uses_each_participants_own_interface(interrupted_commit):
    import json

    server, _, _, _, path = interrupted_commit
    flow, worker, pipeline = (
        server.application_flow_service,
        server.worker_service,
        server.application_pipeline_service,
    )
    pipeline.pause()
    pipeline.continue_current(request_id="recover-before-page-complete")
    journal = json.loads(path.read_text())
    state = worker.store.load()
    state["jobs"][0]["material_update"]["status"] = "complete"
    worker.store.save(state)
    before = (
        flow.path.read_bytes(),
        worker.store.path.read_bytes(),
        pipeline.path.read_bytes(),
        path.read_bytes(),
    )
    progress = worker.material_update_progress(
        journal["application_id"], journal["id"], expected_batch_id=journal["batch_id"]
    )
    assert progress["status"] == "complete"
    assert (
        flow.path.read_bytes(),
        worker.store.path.read_bytes(),
        pipeline.path.read_bytes(),
        path.read_bytes(),
    ) == before
    flow.complete_material_update(journal["task_id"], journal["id"], execution=progress)
    assert flow.material_update_progress(journal["task_id"], journal["id"])["status"] == "complete"
    assert (worker.store.path.read_bytes(), pipeline.path.read_bytes(), path.read_bytes()) == (
        before[1],
        before[2],
        before[3],
    )
    completed = pipeline.complete_material_update(journal["id"])
    assert "material_update_id" not in completed
    assert flow.task_snapshot(journal["task_id"])["status"] == "ready_for_review"
