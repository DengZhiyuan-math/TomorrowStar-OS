"""JSON content versions reach the existing Worker with exact saved PDF identity.

Provider and Prism results are recorded boundaries. These checks do not invoke a
compiler, model, installed App, or an employer website.
"""

import hashlib
import time
from copy import deepcopy
from pathlib import Path

import pytest
from test_application_flow import wait_for
from test_canonical_career_sources import canonical as canonical
from test_j08_flow_combination import (
    finish_json_writing,
    start_json_writing,
)
from test_j08_flow_combination import (
    json_flow as json_flow,
)
from test_p08_combination import SavedPrism, action

from career_evidence_graph.career_portal_data import PortalDataError


class RecordedPrism(SavedPrism):
    def __init__(self):
        self.reads = 0
        self.failure = None

    def read_compiled(self, binding):
        self.reads += 1
        if self.failure:
            raise PortalDataError(self.failure, "Recorded build unavailable", 409)
        result = super().read_compiled(binding)
        marker = result["binding"]["files"][binding["main"]]
        result["pdf"] += b"\n% source-fixture:" + marker.encode() + b"\n"
        result["build"]["pdf_sha256"] = hashlib.sha256(result["pdf"]).hexdigest()
        return result


@pytest.fixture(autouse=True)
def recorded_pipeline_clock(monkeypatch):
    from career_evidence_graph.application_pipeline import ApplicationPipeline

    monkeypatch.setattr(ApplicationPipeline, "_run", lambda self, _: self._closed.wait())


@pytest.fixture
def json_material(json_flow):
    case = json_flow
    case.store.prism_client = RecordedPrism()
    return case


def adopt_content(case):
    task, _ = finish_json_writing(case, start_json_writing(case))
    return task


def prepared_pdf(case, edit):
    task = adopt_content(case)
    if edit:
        task = action(case, task, "begin-prism-edit")
        source = Path(task["prism_edit"]["project_root"]) / task["prism_edit"]["main"]
        human = source.read_text().replace("Planned cross-domain", "Human edited cross-domain")
        if edit == "unmerged":
            human = human.replace("\\section*{Experience}", "\\section*{Selected Experience}")
        source.write_text(human)
        task = action(case, task, "finish-prism-edit")
        draft = case.store.draft(task["draft_id"])
        assert draft["content_reconciliation"]["status"] == edit
        assert draft["latex_source"] == human
        task = action(case, task, "capture-prism-result")
    else:
        case.flow.start(task["id"], task["revision"], "export")
        task = wait_for(
            case.flow,
            task["id"],
            lambda row: row["status"] in {"materials_ready", "failed", "resume_ready"},
        )
    assert task["status"] == "materials_ready", task
    return task


@pytest.mark.parametrize("edit", [None, "mapped", "unmerged"])
def test_content_or_human_version_reaches_worker_with_exact_saved_pdf(json_material, edit):
    case = json_material
    task = prepared_pdf(case, edit)
    pdf = case.store.pdf(task["resume_id"])
    draft = case.store.draft(task["draft_id"])
    assert "Fixed Template Person" in draft["latex_source"]
    assert "fixed@example.test" in draft["latex_source"]
    assert "Fixed University; documented degree in progress." in draft["latex_source"]
    if edit != "unmerged":
        assert (
            "profile" not in draft["resume_content"] and "education" not in draft["resume_content"]
        )
    before = deepcopy(task)
    bound = case.flow.prepare_worker(task["id"], task["revision"], "CHE", True)
    worker = case.server.worker_service
    checkpoint = worker.store.load()
    job = checkpoint["jobs"][0]
    assert bound["worker_ref"]["job_id"] == task["application_id"]
    assert job["single_binding"]["resume_id"] == task["resume_id"]
    assert case.store.read_export(task["resume_id"])["draft_id"] == task["draft_id"]
    assert Path(job["file_path"]).read_bytes() == pdf
    worker.store.check_single(job, checkpoint)
    assert job["file_sha256"] == task["resume_sha256"]
    assert not job.get("attachment_state"), "binding a PDF does not establish a website upload"
    assert case.flow.snapshot(task["id"])["active_task"]["resume_id"] == before["resume_id"]


def test_contact_refresh_never_rewrites_fixed_template_through_the_legacy_generator(json_material):
    from career_evidence_graph._vendor import job_apply_store as helper
    from career_evidence_graph.application_information import put_information_answer

    case = json_material
    task = prepared_pdf(case, "mapped")
    task = case.flow.prepare_worker(task["id"], task["revision"], "CHE", True)
    pdf = case.store.pdf(task["resume_id"])
    source = case.store.draft(task["draft_id"])["latex_source"]
    versions = {path.name for path in case.store.root.iterdir()}
    calls = len(case.runner.calls)
    put_information_answer(
        helper.Store(case.information),
        {
            "question": "Email",
            "value": "corrected@example.test",
            "state": "confirmed",
            "scope": {"application_id": task["application_id"]},
        },
    )
    application = case.applications.get_application(task["application_id"])
    pending = case.flow.update_inputs(task["id"], task["revision"], application["revision"])
    assert pending["material_update"]["inputs"] != task["inputs"]
    with pytest.raises(PortalDataError) as raised:
        case.flow.begin_automatic_edit(pending["id"], pending["revision"])
    assert raised.value.code == "resume_template_update_required"
    assert case.store.draft(task["draft_id"])["latex_source"] == source
    assert case.store.pdf(task["resume_id"]) == pdf
    assert {path.name for path in case.store.root.iterdir()} == versions
    assert len(case.runner.calls) == calls
    assert case.flow.snapshot(task["id"])["active_task"]["resume_id"] == task["resume_id"]


def pipeline_bound(case):
    from career_evidence_graph.application_prism import source_snapshot

    pipeline = case.server.application_pipeline_service
    case.flow.callbacks["automatic_latex_base"] = lambda _: source_snapshot(
        case.project, "main.tex"
    )
    pipeline.intake.reader = lambda *a, **k: {"status": "readable", "emails": [], "provenance": {}}
    case.job = case.applications.update_application(
        case.job["id"], {"location": "Zurich, Switzerland"}, case.job["revision"]
    )
    pipeline.admit(
        {
            "request_id": "recorded-json-admission",
            "application_id": case.job["id"],
            "application_revision": case.job["revision"],
        }
    )
    pipeline.start(request_id="recorded-json-cycle")
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        pipeline._tick()
        task = case.flow.snapshot().get("active_task")
        if task and task.get("experience_handoff"):
            break
        time.sleep(0.01)
    assert task.get("experience_handoff"), (pipeline.snapshot(), task)
    task, _ = finish_json_writing(case, task)
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        pipeline._tick()
        if pipeline.snapshot()["status"] == "filling":
            break
        time.sleep(0.01)
    assert pipeline.snapshot()["status"] == "filling", pipeline.snapshot()
    pipeline.pause()
    task = case.flow.snapshot(task["id"])["active_task"]
    assert task["send_approval"]["verified_by"] == "workflow_policy"
    return task


@pytest.fixture
def original_bound_page(json_material):
    import fcntl
    import os

    from career_evidence_graph.application_worker import start_run

    case = json_material
    task = pipeline_bound(case)
    worker = case.server.worker_service
    run_id = start_run(worker.store)
    descriptor = os.open(worker.store.root / ".worker.lock", os.O_CREAT | os.O_RDWR, 0o600)
    fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
    worker.store.worker_lock_descriptor = descriptor
    current = worker.store.load()
    current["jobs"][0].update(
        page_open=True,
        status="ready_for_review",
        reason="final_submit_manual",
        manual_fields={"notes": "Keep human text."},
        manual_attachments=[{"name": "human-attachment.pdf", "sha256": "c" * 64}],
        page_observation={"run_id": run_id, "page_id": "original-page", "at": time.time()},
    )
    worker.store.save(current)
    try:
        yield case, task, run_id, descriptor
    finally:
        os.close(descriptor)
        worker.store.worker_lock_descriptor = None


def test_bound_prism_edit_keeps_original_worker_material_until_one_continue(original_bound_page):
    import os

    case, task, run_id, descriptor = original_bound_page
    old_pdf = case.store.pdf(task["resume_id"])
    worker = case.server.worker_service
    original = deepcopy(worker.store.load())
    editing = action(case, task, "begin-prism-edit")
    assert editing["material_update"]["old"]["resume_id"] == task["resume_id"]
    assert worker.store.load() == original
    assert Path(original["jobs"][0]["file_path"]).read_bytes() == old_pdf
    source = Path(editing["prism_edit"]["project_root"]) / editing["prism_edit"]["main"]
    human = source.read_text().replace("Planned cross-domain", "Human edited cross-domain")
    source.write_text(human)
    finished = action(case, editing, "finish-prism-edit")
    assert finished["draft_id"] == task["draft_id"]
    assert finished["resume_id"] == task["resume_id"]
    assert finished["material_update"]["editable_draft"]["latex_source"] == human
    assert worker.store.load() == original
    captured = action(case, finished, "capture-prism-result")
    candidate = captured["material_update"]["candidate"]
    assert captured["resume_id"] == task["resume_id"]
    assert candidate["resume_id"] != task["resume_id"]
    assert candidate["draft_id"] == finished["material_update"]["editable_draft"]["id"]
    assert case.store.pdf(candidate["resume_id"]) != old_pdf
    assert case.store.pdf(task["resume_id"]) == old_pdf
    assert worker.store.load() == original
    pipeline = case.server.application_pipeline_service
    reads = case.store.prism_client.reads
    pipeline.continue_current(request_id="one-prism-bound-continue")
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        current_task = case.flow.snapshot(task["id"])["active_task"]
        if current_task["material_update"]["status"] != "preparing":
            break
        time.sleep(0.01)
    assert current_task["material_update"]["status"] == "awaiting_page", current_task[
        "material_update"
    ]
    assert case.store.prism_client.reads == reads
    pipeline._tick()
    current = worker.store.load()
    job = current["jobs"][0]
    assert job["material_update"]["status"] == "inspect_pending"
    stat = os.fstat(descriptor)
    # Replace only the browser readback boundary. Authorization, ownership,
    # immutable PDFs, journal commit and ordinary single binding remain real.
    job["material_update"].update(
        status="page_verified",
        page_receipt={
            "run_id": run_id,
            "page_id": "original-page",
            "worker_lock": {"device": stat.st_dev, "inode": stat.st_ino},
        },
    )
    worker.store.save(current)
    pipeline._tick()
    current_task = case.flow.snapshot(task["id"])["active_task"]
    assert current_task["material_update"]["status"] == "bound", pipeline.snapshot()
    current = worker.store.load()
    job = current["jobs"][0]
    assert job["file_sha256"] == candidate["resume_sha256"]
    assert job["single_binding"]["resume_id"] == candidate["resume_id"]
    for key in ("manual_fields", "manual_attachments", "page_observation", "intent"):
        assert job[key] == original["jobs"][0][key]
    worker.store.check_single(job, current)
    assert job["material_update"]["status"] == "bound", "local adoption is not a website upload"
    assert case.store.pdf(task["resume_id"]) == old_pdf


def finish_bound_edit(case, task):
    editing = action(case, task, "begin-prism-edit")
    source = Path(editing["prism_edit"]["project_root"]) / editing["prism_edit"]["main"]
    source.write_text(source.read_text().replace("Planned cross-domain", "Manual cross-domain"))
    return action(case, editing, "finish-prism-edit"), source


def test_bound_compile_failure_retains_old_pdf_and_recovers_same_capture(original_bound_page):
    case, task, _, _ = original_bound_page
    worker = case.server.worker_service
    original = deepcopy(worker.store.load())
    old_pdf = case.store.pdf(task["resume_id"])
    finished, source = finish_bound_edit(case, task)
    human = source.read_bytes()
    case.store.prism_client.failure = "resume_export_failed"
    with pytest.raises(PortalDataError) as failed:
        action(case, finished, "capture-prism-result")
    assert failed.value.code == "resume_export_failed"
    waiting = case.flow.snapshot(task["id"])["active_task"]
    assert waiting["resume_id"] == task["resume_id"]
    assert waiting["draft_id"] == task["draft_id"]
    assert source.read_bytes() == human
    assert case.store.pdf(task["resume_id"]) == old_pdf
    assert worker.store.load() == original
    pending_id = waiting["prism_capture"]["id"]
    case.store.prism_client.failure = None
    recovered = action(case, waiting, "capture-prism-result")
    assert recovered["prism_capture"]["id"] == pending_id
    assert recovered["material_update"]["candidate"]["resume_id"] == pending_id
    assert recovered["resume_id"] == task["resume_id"]
    assert worker.store.load() == original


def test_late_bound_pdf_cannot_replace_a_new_prism_edit(original_bound_page):
    case, task, _, _ = original_bound_page
    finished, source = finish_bound_edit(case, task)
    old_pdf = case.store.pdf(task["resume_id"])
    capture = case.flow.callbacks["prism_result_capture"]
    late = []

    def newer_edit(request, export_id):
        result = capture(request, export_id)
        late.append(result)
        current = case.flow.snapshot(task["id"])["active_task"]
        action(case, current, "begin-prism-edit")
        return result

    case.flow.callbacks["prism_result_capture"] = newer_edit
    with pytest.raises(PortalDataError) as raised:
        action(case, finished, "capture-prism-result")
    assert raised.value.code == "prism_result_changed"
    current = case.flow.snapshot(task["id"])["active_task"]
    assert current["prism_edit"]["status"] == "editing"
    assert current["resume_id"] == task["resume_id"]
    assert case.store.pdf(task["resume_id"]) == old_pdf
    assert case.store.pdf(late[0]["id"])
    assert not current["artifacts"][-1]["adopted"]
    assert "Manual cross-domain" in source.read_text()


@pytest.mark.parametrize("opened", [False, True])
def test_bound_capture_without_finished_edit_cannot_replace_the_active_pdf(
    original_bound_page, opened
):
    case, task, _, _ = original_bound_page
    if opened:
        task = action(case, task, "begin-prism-edit")
    worker = case.server.worker_service
    before_worker = deepcopy(worker.store.load())
    before_task = case.flow.snapshot(task["id"])["active_task"]
    versions = {path.name for path in case.store.root.iterdir()}
    reads = case.store.prism_client.reads
    with pytest.raises(PortalDataError) as raised:
        action(case, before_task, "capture-prism-result")
    assert raised.value.code == ("prism_edit_active" if opened else "prism_bound_edit_required")
    assert case.flow.snapshot(task["id"])["active_task"] == before_task
    assert worker.store.load() == before_worker
    assert {path.name for path in case.store.root.iterdir()} == versions
    assert case.store.prism_client.reads == reads
    job = before_worker["jobs"][0]
    assert job["single_binding"]["resume_id"] == before_task["resume_id"]
