"""Bound workers reuse the local task's declared information store."""

import json
from copy import deepcopy

import pytest
from test_j08_flow_combination import canonical as canonical
from test_j08_flow_combination import json_flow as json_flow
from test_j08_material_binding import (
    json_material as json_material,
)
from test_j08_material_binding import (
    prepared_pdf,
)
from test_j08_material_binding import (
    recorded_pipeline_clock as recorded_pipeline_clock,
)

from career_evidence_graph._vendor import job_apply_store as helper
from career_evidence_graph.application_information import (
    put_information_answer,
    read_information_history,
)
from career_evidence_graph.application_worker import WorkerStore, digest
from career_evidence_graph.career_portal_data import PortalDataError


def bound_worker(case):
    task = prepared_pdf(case, None)
    case.flow.prepare_worker(task["id"], task["revision"], "CHE", True)
    worker = case.server.worker_service
    return worker, worker.store.load()["jobs"][0]


def test_bound_worker_resolves_email_from_declared_information_store(json_material):
    case = json_material
    worker, job = bound_worker(case)
    result = worker.store.resolve({"id": "email", "question": "Email"}, job)
    assert result is not None
    assert result[0] == "library@example.test"
    assert worker.store.answers._load_answers_document()["answers"] == {}


def test_bound_answer_and_correction_update_declared_store_and_preserve_history(json_material):
    case = json_material
    worker, job = bound_worker(case)
    default_bytes = worker.store.answers.answers_path.read_bytes()
    state = worker.store.load()
    job = state["jobs"][0]
    job.update(
        status="needs_input",
        questions=[
            {
                "id": "language",
                "question": "French proficiency (CEFR)",
                "options": [],
            }
        ],
    )
    worker.store.save(state)
    worker.request(
        "answer",
        {
            "application_id": job["application_id"],
            "question_id": "language",
            "value": "B2",
        },
    )
    assert worker.store.language_levels(case.job)["French"] == "B2"
    assert (
        helper.Store(case.information).get_answer(
            helper.answer_key("French proficiency (CEFR)", {})
        )["value"]
        == "B2"
    )
    record = next(row for row in worker.snapshot()["library"] if row["question"] == "Email")
    worker.request(
        "library",
        {
            "key": record["key"],
            "revision": digest(
                {key: value for key, value in record.items() if key != "content_revision"}
            ),
            "value": "corrected@example.test",
        },
    )
    assert (
        worker.store.resolve({"id": "email", "question": "Email"}, job)[0]
        == "corrected@example.test"
    )
    assert (
        read_information_history(case.information, key=record["key"])[0]["source"]
        == "answer-correction"
    )
    assert worker.store.answers.answers_path.read_bytes() == default_bytes
    reopened = WorkerStore(
        case.applications,
        worker.store.root,
        live=True,
        single_flow_root=worker.store.single_flow_root,
        single_career_root=worker.store.single_career_root,
    )
    assert (
        reopened.resolve({"id": "email", "question": "Email"}, job)[0] == "corrected@example.test"
    )
    # APP-04: the correction fills from the current library and keeps the adopted PDF.
    reopened.check_single(reopened.load()["jobs"][0])


@pytest.mark.parametrize("mutation", ["payload-root", "local-task", "symlink-root"])
def test_unverified_information_pointer_is_rejected(json_material, mutation, tmp_path):
    case = json_material
    worker, job = bound_worker(case)
    job = deepcopy(job)
    if mutation == "payload-root":
        job["single_binding"]["inputs"]["information_library_root"] = str(tmp_path / "arbitrary")
    elif mutation == "local-task":
        path = worker.store.single_flow_root / "flow.json"
        document = json.loads(path.read_text())
        document["tasks"][0]["inputs"]["information_library_root"] = str(tmp_path / "arbitrary")
        path.write_text(json.dumps(document))
    else:
        moved = case.information.with_name("retained-information")
        case.information.rename(moved)
        case.information.symlink_to(moved, target_is_directory=True)
    with pytest.raises(PortalDataError) as error:
        worker.store.resolve({"id": "email", "question": "Email"}, job)
    assert error.value.code == "single_information_invalid"
    assert not (tmp_path / "arbitrary").exists()


def test_legacy_job_keeps_original_worker_answers(json_material):
    case = json_material
    worker, job = bound_worker(case)
    put_information_answer(
        worker.store.answers,
        {
            "question": "Email",
            "value": "historical@example.test",
            "scope": {},
            "state": "confirmed",
        },
    )
    legacy = deepcopy(job)
    legacy["single_binding"]["inputs"].pop("information_library_root")
    assert (
        worker.store.resolve({"id": "email", "question": "Email"}, legacy)[0]
        == "historical@example.test"
    )
    assert (
        helper.Store(case.information).get_answer(helper.answer_key("Email", {}))["value"]
        == "library@example.test"
    )
