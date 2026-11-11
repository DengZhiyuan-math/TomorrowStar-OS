"""Worker reads project state; committed transitions own intervention records."""

from test_application_worker import job
from test_application_worker import service as service

from career_evidence_graph.application_worker import WorkerStore
from career_evidence_graph.validation.hashing import record_digest


def file_bytes(root):
    return {
        str(path.relative_to(root)): path.read_bytes() for path in root.rglob("*") if path.is_file()
    }


def test_worker_snapshot_does_not_write_missing_answer_measurements(service):
    service.request("prepare", {"jobs": [job(service)]})
    state = service.store.load()
    state["jobs"][0].update(
        status="needs_input",
        questions=[{"id": "email", "question": "Email", "options": []}],
    )
    service.store.save(state)
    before = file_bytes(service.store.root)
    first = service.snapshot()
    second = service.snapshot()
    assert len(first["input_items"]) == len(second["input_items"]) == 1
    assert file_bytes(service.store.root) == before


def test_committed_missing_answers_record_one_shared_request_without_a_snapshot(service):
    service.request("prepare", {"jobs": [job(service, 1), job(service, 2)]})
    state = service.store.load()
    for index, current in enumerate(state["jobs"]):
        current.update(
            status="needs_input" if index == 0 else "queued",
            questions=[{"id": f"email-{index}", "question": "Email", "options": []}],
        )
    service.store.save(state)
    requests = [
        row for row in service.store.measurements.read() if row["kind"] == "intervention_request"
    ]
    assert len(requests) == 1
    # Retained public question-group identity for Email with global scope and no options.
    original_group_id = "6fba1b110c5e6c7774afea1e6f03a57203d2e888a966a7bb549dab46802c6c4e"
    assert requests[0]["request_group"] == record_digest([state["batch_id"], original_group_id])
    assert requests[0]["affected_jobs"] == [row["application_id"] for row in state["jobs"]]
    assert requests[0]["reason"] == "missing_answers"
    service.store.save(state)
    reopened = WorkerStore(service.store.applications, service.store.root)
    reopened.save(state)
    assert [
        row for row in reopened.measurements.read() if row["kind"] == "intervention_request"
    ] == requests
    assert service.snapshot()["input_items"][0]["id"] == original_group_id


def test_measurement_failure_does_not_undo_committed_waiting_state(service, monkeypatch):
    service.request("prepare", {"jobs": [job(service)]})
    state = service.store.load()
    state["jobs"][0].update(
        status="needs_input",
        questions=[{"id": "email", "question": "Email", "options": []}],
    )

    def unavailable(*args, **kwargs):
        raise OSError("Observation unavailable")

    monkeypatch.setattr(service.store.measurements, "request_group", unavailable)
    service.store.save(state)
    assert service.store.load() == state
    assert service.snapshot()["input_items"][0]["question"] == "Email"
