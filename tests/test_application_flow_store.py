"""flow.json indexes one file per task revision (2026-11-09: a 206 MB record)."""

import json

import pytest
from test_application_flow import application as application

from career_evidence_graph._vendor import job_apply_store as helper
from career_evidence_graph.application_flow import ApplicationFlowService
from career_evidence_graph.application_flow_store import STORAGE, read_flow_state
from career_evidence_graph.career_portal_data import PortalDataError


def service(applications, root):
    return ApplicationFlowService(
        applications, root, callbacks={"analysis": lambda task: {"id": "result"}}
    )


def test_the_record_is_an_index_of_task_files(application, tmp_path):
    applications, job = application
    flow = service(applications, tmp_path / "flow")
    try:
        task = flow.create(job["id"], job["revision"])
        index = json.loads(flow.path.read_text())
        assert index["storage"] == STORAGE and "tasks" not in index
        assert index["task_refs"] == [{"id": task["id"], "revision": task["revision"]}]
        assert (flow.root / "snapshots" / task["id"] / f"{task['revision']}.json").is_file()
        # Readers see the same whole record as before.
        assert read_flow_state(flow.root)["tasks"][0]["id"] == task["id"]
        assert flow.snapshot()["tasks"][0]["id"] == task["id"]
    finally:
        flow.close()


def test_a_save_writes_only_the_task_that_changed(application, tmp_path, monkeypatch):
    applications, job = application
    flow = service(applications, tmp_path / "flow")
    try:
        first = flow.create(job["id"], job["revision"])
        with applications.write_lock():
            state = flow._load()
            state["tasks"].append(
                dict(state["tasks"][0], id="b" * 32, application_id="other-application")
            )
            flow._save(state)
        writes, reads = [], []
        write, read = helper.atomic_write_json, helper.read_json_object
        monkeypatch.setattr(
            helper,
            "atomic_write_json",
            lambda path, payload: writes.append(path) or write(path, payload),
        )
        monkeypatch.setattr(
            helper, "read_json_object", lambda path, label: reads.append(path) or read(path, label)
        )
        with applications.write_lock():
            state = flow._load()
            reads.clear()
            state["tasks"][0]["job_description"] = "Changed job description."
            flow._save(state)
        task_writes = [path for path in writes if path != flow.path]
        assert [path.parent.name for path in task_writes] == [first["id"]]
        assert flow.path in writes
        # Unchanged task files this process verified are not read back.
        assert reads == []
    finally:
        flow.close()


def test_an_inline_record_loads_and_the_first_save_converts_it(application, tmp_path):
    applications, job = application
    flow = service(applications, tmp_path / "flow")
    task = flow.create(job["id"], job["revision"])
    inline = read_flow_state(flow.root)
    flow.close()
    flow.path.write_text(json.dumps(inline))
    flow = service(applications, tmp_path / "flow")
    try:
        assert flow.snapshot()["tasks"][0]["id"] == task["id"]
        with applications.write_lock():
            flow._save(flow._load())
        assert json.loads(flow.path.read_text())["storage"] == STORAGE
        backup = json.loads((flow.root / "flow-v1-backup.json").read_text())
        assert backup["tasks"][0]["id"] == task["id"]
    finally:
        flow.close()


def test_a_changed_task_file_is_rejected(application, tmp_path):
    applications, job = application
    flow = service(applications, tmp_path / "flow")
    task = flow.create(job["id"], job["revision"])
    flow.close()
    path = flow.root / "snapshots" / task["id"] / f"{task['revision']}.json"
    saved = json.loads(path.read_text())
    saved["job_description"] = "Edited outside the App."
    path.write_text(json.dumps(saved))
    with pytest.raises(PortalDataError) as error:
        service(applications, tmp_path / "flow")
    assert error.value.code == "flow_invalid"
