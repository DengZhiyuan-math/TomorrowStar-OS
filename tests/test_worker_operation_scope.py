"""Ordinary browser actions retain task guards without replaying material adoption."""

import base64
import json

import pytest
from test_application_resume import task_resume as task_resume
from test_application_single_binding import bound_single as bound_single
from test_automatic_material_reuse_edit import complete_portal as complete_portal
from test_full_latex_generation import full_latex as full_latex

from career_evidence_graph.application_worker import WorkerService, digest, start_run
from career_evidence_graph.application_worker_browser import ApplicationRunner
from career_evidence_graph.career_portal_data import PortalDataError


@pytest.fixture
def bound_runner(bound_single, tmp_path, monkeypatch):
    applications, flow, career, frozen, _ = bound_single
    path = flow / "flow.json"
    state = json.loads(path.read_text())
    task = state["tasks"][0]
    task.update(worker_ref=None, status="materials_ready")
    task["revision"] = digest({key: value for key, value in task.items() if key != "revision"})
    path.write_text(json.dumps(state))
    service = WorkerService(
        applications,
        tmp_path / "worker",
        fixture_origin="http://127.0.0.1:9999",
        single_flow_root=flow,
        single_career_root=career,
    )
    monkeypatch.setattr(service, "spawn", lambda: None)
    app = applications.get_application(frozen["application_id"])
    raw = (flow / "resumes" / task["resume_id"] / "resume.pdf").read_bytes()
    prepared = service.request(
        "prepare",
        {
            "workflow": "single",
            "send_confirmed": True,
            "jobs": [
                {
                    "application_id": app["id"],
                    "revision": app["revision"],
                    "country": "CHE",
                    "filename": "synthetic.pdf",
                    "file_base64": base64.b64encode(raw).decode(),
                    "single_binding": frozen["single_binding"],
                }
            ],
        },
    )
    task.update(
        worker_ref={"batch_id": prepared["batch_id"], "job_id": app["id"], "status": "queued"},
        status="queued",
    )
    task["revision"] = digest({key: value for key, value in task.items() if key != "revision"})
    path.write_text(json.dumps(state))
    start_run(service.store)
    service.request("resume", {"controller": "synthetic-controller"})
    return service, ApplicationRunner(service.store, None), flow, career


@pytest.mark.parametrize("action", ["open", "fill"])
def test_ordinary_actions_ignore_unrelated_career_and_research_changes(
    bound_runner, monkeypatch, action
):
    service, runner, flow, career = bound_runner
    before = {str(path): path.read_bytes() for path in flow.rglob("*") if path.is_file()}
    (career / "contributions").mkdir()
    (career / "contributions/unrelated.md").write_text(
        "# New unrelated work\n\n## Scope\nOther work."
    )
    history = career / ".tomorrowstar-match-history"
    history.mkdir()
    (history / "current.json").write_text("corrupt independent research benchmark")
    reads = []
    from career_evidence_graph import application_resume

    original = application_resume.career_source_snapshot

    def snapshot(catalog):
        reads.append(True)
        return original(catalog)

    monkeypatch.setattr(application_resume, "career_source_snapshot", snapshot)
    state = service.store.load()
    current = state["jobs"][0]
    assert runner.authorize(current, state["batch_id"], {"action": action, "field_id": "name"})
    assert reads == []
    assert service.store.load()["jobs"][0]["intent"]["action"] == action
    assert {str(path): path.read_bytes() for path in flow.rglob("*") if path.is_file()} == before


def test_single_resume_uses_bound_task_without_rescanning_unrelated_sources(
    bound_runner, monkeypatch
):
    service, _, _, career = bound_runner
    service.request("pause", {"controller": "synthetic-controller"})
    (career / "contributions").mkdir()
    (career / "contributions/unrelated.md").write_text("# New work\n\n## Scope\nOther work.")
    reads = []
    from career_evidence_graph import application_resume

    original = application_resume.career_source_snapshot

    def snapshot(catalog):
        reads.append(True)
        return original(catalog)

    monkeypatch.setattr(application_resume, "career_source_snapshot", snapshot)
    resumed = service.request("resume", {"controller": "synthetic-controller"})
    assert resumed["control"] == "running"
    assert resumed["jobs"][0]["status"] == "queued"
    assert reads == []


@pytest.mark.parametrize("changed", ["adopted-pdf", "worker-pdf", "lineage"])
def test_upload_keeps_exact_current_material_guards(bound_runner, changed):
    service, runner, flow, _career = bound_runner
    state = service.store.load()
    job = state["jobs"][0]
    resume_id = job["single_binding"]["resume_id"]
    if changed == "adopted-pdf":
        (flow / "resumes" / resume_id / "resume.pdf").write_bytes(
            b"%PDF-1.4 different adopted bytes"
        )
    elif changed == "worker-pdf":
        from pathlib import Path

        Path(job["file_path"]).write_bytes(b"%PDF-1.4 different worker bytes")
    else:
        path = flow / "resumes" / resume_id / "sources.json"
        draft = json.loads(path.read_text())
        draft["analysis_binding"]["source_snapshot_revision"] = "changed-source-binding"
        path.write_text(json.dumps(draft))
    before = service.store.path.read_bytes()
    with pytest.raises(PortalDataError) as error:
        runner.authorize(job, state["batch_id"], {"action": "upload", "field_id": "resume"})
    assert error.value.code == (
        "file_changed" if changed == "worker-pdf" else "single_binding_invalid"
    )
    assert service.store.path.read_bytes() == before


def test_upload_uses_adopted_settings_without_reading_new_model_or_benchmark(
    bound_runner, monkeypatch
):
    service, runner, _, career = bound_runner
    history = career / ".tomorrowstar-match-history"
    history.mkdir()
    (history / "current.json").write_text("corrupt independent research benchmark")

    def unrelated_read(*_args, **_kwargs):
        pytest.fail(
            "Completed PDF uses recorded configuration, not current research or model settings"
        )

    monkeypatch.setattr(
        "career_evidence_graph.application_benchmark.load_benchmark", unrelated_read
    )
    monkeypatch.setattr(
        "career_evidence_graph.application_match.match_configuration_revision", unrelated_read
    )
    monkeypatch.setattr(
        "career_evidence_graph.application_resume.resume_configuration_revision", unrelated_read
    )
    state = service.store.load()
    job = state["jobs"][0]
    assert runner.authorize(job, state["batch_id"], {"action": "upload", "field_id": "resume"})


@pytest.mark.parametrize(
    "change", ["target", "jd", "worker-reference", "material-update", "eligibility"]
)
def test_light_actions_still_reject_known_current_input_changes(bound_runner, change):
    service, runner, flow, _ = bound_runner
    state = service.store.load()
    job = state["jobs"][0]
    if change in {"target", "jd"}:
        app = service.store.applications.get_application(job["application_id"])
        updates = (
            {"url": app["url"].replace("000001", "000002")}
            if change == "target"
            else {"job_description": "Changed current job"}
        )
        service.store.applications.update_application(app["id"], updates, app["revision"])
    else:
        path = flow / "flow.json"
        saved = json.loads(path.read_text())
        task = saved["tasks"][0]
        if change == "worker-reference":
            task["worker_ref"]["batch_id"] = "e" * 32
        elif change == "material-update":
            task["material_update"] = {"id": "e" * 32, "status": "needs_recheck"}
        else:
            task["artifacts"][0]["result"]["requirements"] = [
                {
                    "text": "A known required qualification",
                    "judgment": "gap",
                    "hard_condition": True,
                }
            ]
        task["revision"] = digest({key: value for key, value in task.items() if key != "revision"})
        path.write_text(json.dumps(saved))
    before = service.store.path.read_bytes()
    with pytest.raises(PortalDataError):
        runner.authorize(job, state["batch_id"], {"action": "fill", "field_id": "name"})
    assert service.store.path.read_bytes() == before


@pytest.mark.parametrize("guard", ["pause", "unknown-intent", "wrong-current", "owner"])
def test_light_actions_keep_existing_execution_guards(bound_runner, guard):
    service, runner, _, _ = bound_runner
    state = service.store.load()
    job = state["jobs"][0]
    if guard == "pause":
        service.request("pause", {"controller": "synthetic-controller"})
    elif guard == "unknown-intent":
        job["intent"] = {"action": "fill", "attempt_id": "unknown-original-attempt"}
        service.store.save(state)
    elif guard == "wrong-current":
        state["current_job_id"] = None
        service.store.save(state)
    else:
        from career_evidence_graph.application_execution import (
            automated_owner,
            release_execution,
            reserve_execution,
        )

        release_execution(
            service.store.applications,
            job["application_id"],
            automated_owner(service.store.root, state["batch_id"], job["application_id"]),
            "automated",
        )
        reserve_execution(
            service.store.applications, job["application_id"], "other-executor", "codex"
        )
    before = service.store.path.read_bytes()
    if guard == "owner":
        with pytest.raises(PortalDataError):
            runner.authorize(job, state["batch_id"], {"action": "fill", "field_id": "name"})
    else:
        assert not runner.authorize(job, state["batch_id"], {"action": "fill", "field_id": "name"})
    assert service.store.path.read_bytes() == before


@pytest.mark.parametrize("changed", ["name", "links", "historical-profile"])
def test_ordinary_fill_continues_after_a_career_profile_contact_change(
    complete_portal, monkeypatch, changed
):
    server, store, original, _ = complete_portal
    flow, worker = server.application_flow_service, server.worker_service
    monkeypatch.setattr(worker, "spawn", lambda: None)
    flow.prepare_worker(original["id"], original["revision"], "CHE", True)
    start_run(worker.store)
    worker.request("resume", {"controller": "synthetic-controller"})
    runner = ApplicationRunner(worker.store, None)
    profile = store.catalog.root / "sources/profile.json"
    record = json.loads(profile.read_text())
    if changed == "historical-profile":
        snapshot = flow.root / "resumes" / original["draft_id"] / "source-snapshot.json"
        saved = json.loads(snapshot.read_text())
        saved["profile"]["name"] = "Altered historical profile"
        snapshot.write_text(json.dumps(saved))
    else:
        if changed == "name":
            record["name"] = "Corrected Current Name"
        else:
            record["links"] = [{"label": "Email", "href": "mailto:current@example.invalid"}]
        profile.write_text(json.dumps(record))
    # APP-04: a profile correction does not stop filling with the adopted PDF;
    # filling reads current facts and regenerating materials is explicit.
    state = worker.store.load()
    assert runner.authorize(
        state["jobs"][0], state["batch_id"], {"action": "fill", "field_id": "name"}
    )


def test_ordinary_fill_keeps_existing_latex_without_a_generated_source_archive(bound_runner):
    service, runner, flow, _career = bound_runner
    saved = json.loads((flow / "flow.json").read_text())
    task = saved["tasks"][0]
    artifact = next(row for row in task["artifacts"] if row["stage"] == "resume")
    artifact["result"].update(origin="existing_latex", analysis_binding={})
    task["revision"] = digest({key: value for key, value in task.items() if key != "revision"})
    (flow / "flow.json").write_text(json.dumps(saved))
    state = service.store.load()
    assert runner.authorize(
        state["jobs"][0], state["batch_id"], {"action": "fill", "field_id": "name"}
    )


@pytest.mark.parametrize("changed", ["new-work", "invalid-unrelated-work"])
def test_ordinary_fill_does_not_scan_the_catalog_for_unrelated_profile_work(
    complete_portal, monkeypatch, changed
):
    server, store, original, _ = complete_portal
    flow, worker = server.application_flow_service, server.worker_service
    monkeypatch.setattr(worker, "spawn", lambda: None)
    flow.prepare_worker(original["id"], original["revision"], "CHE", True)
    start_run(worker.store)
    worker.request("resume", {"controller": "synthetic-controller"})
    runner = ApplicationRunner(worker.store, None)
    profile = store.catalog.root / "sources/profile.json"
    record = json.loads(profile.read_text())
    record.setdefault("research", []).append(
        {"name": "New unrelated work", "points": [], "links": []}
    )
    if changed == "invalid-unrelated-work":
        record["research"] = "An unrelated malformed career research field"
    profile.write_text(json.dumps(record))

    def unrelated_scan(*_args, **_kwargs):
        pytest.fail("Ordinary contact checks must not enumerate all career documents")

    monkeypatch.setattr(
        "career_evidence_graph.career_portal_data.CareerCatalog._paths", unrelated_scan
    )
    state = worker.store.load()
    assert runner.authorize(
        state["jobs"][0], state["batch_id"], {"action": "fill", "field_id": "name"}
    )
