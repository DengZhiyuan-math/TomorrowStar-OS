"""Single-job preparation reuses worker safety without routing or automatic launch."""

import base64
import json
import time
from copy import deepcopy
from uuid import uuid4

import pytest

from career_evidence_graph.application_worker import WorkerService, digest
from career_evidence_graph.career_portal_data import ApplicationStore, PortalDataError


@pytest.fixture
def single_worker(tmp_path, monkeypatch):
    (tmp_path / "applications").mkdir()
    applications = ApplicationStore(tmp_path / "applications")
    app = applications.create_application(
        {
            "company": "Synthetic",
            "role_title": "Engineer",
            "status": "drafting",
            "url": "https://jobs.lever.co/synthetic/00000000-0000-0000-0000-000000000001",
            "job_description": "Build Python services.",
        }
    )
    checks, launches = [], []
    service = WorkerService(
        applications,
        tmp_path / "worker",
        live=True,
        single_flow_root=tmp_path / "flow",
        single_career_root=tmp_path / "career",
        single_validator=lambda *args, **kwargs: checks.append((args, kwargs)),
    )
    monkeypatch.setattr(service, "spawn", lambda: launches.append(True))
    item = {
        "application_id": app["id"],
        "revision": app["revision"],
        "country": "CHE",
        "filename": "synthetic.pdf",
        "file_base64": base64.b64encode(b"%PDF-1.4 synthetic").decode(),
        "single_binding": {"task_id": "synthetic-task"},
    }
    return service, item, checks, launches


def test_single_prepare_without_routing_stays_paused_until_explicit_resume(single_worker):
    service, item, checks, launches = single_worker
    prepared = service.request(
        "prepare", {"workflow": "single", "send_confirmed": True, "jobs": [item]}
    )
    assert prepared["control"] == "paused"
    assert prepared["jobs"][0]["workflow"] == "single"
    assert launches == []
    assert checks
    resumed = service.request("resume", {"controller": "synthetic-controller"})
    assert resumed["control"] == "running"
    assert launches == [True]
    assert len(checks) >= 2


def test_invalid_single_binding_on_resume_keeps_control_paused_and_never_launches(single_worker):
    service, item, _, launches = single_worker
    service.request("prepare", {"workflow": "single", "send_confirmed": True, "jobs": [item]})

    def stale(*args, **kwargs):
        raise PortalDataError("single_binding_invalid", "Synthetic stale materials.", 409)

    service.store.single_validator = stale
    result = service.request("resume", {"controller": "synthetic-controller"})
    assert result["control"] == "paused"
    assert result["jobs"][0]["status"] == "needs_recheck"
    assert launches == []


def test_spawn_passes_the_persisted_single_flow_root_to_the_child(single_worker, monkeypatch):
    from types import SimpleNamespace

    from career_evidence_graph import application_worker

    service, item, _, _ = single_worker
    service.request("prepare", {"workflow": "single", "send_confirmed": True, "jobs": [item]})
    calls = []

    def process(args, **kwargs):
        calls.append(args)
        return SimpleNamespace(pid=987654321, poll=lambda: None)

    monkeypatch.setattr(application_worker.subprocess, "Popen", process)
    WorkerService.spawn(service)
    assert len(calls) == 1
    argv = calls[0]
    assert argv[argv.index("--single-flow-root") + 1] == str(service.store.single_flow_root)
    assert "--cover-letter-template" not in argv
    assert "--pdf-inspect" not in argv


def test_spawn_passes_the_backends_cover_letter_template_to_the_child(
    single_worker, monkeypatch, tmp_path
):
    """2026-11-03: the backend had its template, the child Worker none, so every letter
    the child prepared failed as letter_template_required."""
    from types import SimpleNamespace

    from career_evidence_graph import application_worker

    service, item, _, _ = single_worker
    service.request("prepare", {"workflow": "single", "send_confirmed": True, "jobs": [item]})
    service.store.cover_letter_template = tmp_path / "letter.tex"
    calls = []
    monkeypatch.setattr(
        application_worker.subprocess,
        "Popen",
        lambda args, **kwargs: calls.append(args) or SimpleNamespace(pid=987654321, poll=None),
    )
    WorkerService.spawn(service)
    argv = calls[0]
    assert argv[argv.index("--cover-letter-template") + 1] == str(tmp_path / "letter.tex")

    # The child's own store takes it before any browser starts.
    from career_evidence_graph import application_worker_browser

    stores = []

    class Store(application_worker_browser.WorkerStore):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            stores.append(self)

    def stop_before_browser():
        raise OSError("Synthetic stop before browser startup")

    monkeypatch.setattr(application_worker_browser, "WorkerStore", Store)
    monkeypatch.setattr(application_worker_browser, "sync_playwright", stop_before_browser)
    application_worker_browser.main(argv[argv.index("--applications") :])
    assert stores[0].cover_letter_template == tmp_path / "letter.tex"


def spawned_child_store(service, monkeypatch):
    """Spawn the child argv, then run the child's main until just before its browser."""
    from types import SimpleNamespace

    from career_evidence_graph import application_worker, application_worker_browser

    calls = []
    monkeypatch.setattr(
        application_worker.subprocess,
        "Popen",
        lambda args, **kwargs: calls.append(args) or SimpleNamespace(pid=987654321, poll=None),
    )
    WorkerService.spawn(service)
    stores = []

    class Store(application_worker_browser.WorkerStore):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            stores.append(self)

    def stop_before_browser():
        raise OSError("Synthetic stop before browser startup")

    monkeypatch.setattr(application_worker_browser, "WorkerStore", Store)
    monkeypatch.setattr(application_worker_browser, "sync_playwright", stop_before_browser)
    argv = calls[0]
    application_worker_browser.main(argv[argv.index("--applications") :])
    return argv, stores[0]


@pytest.mark.parametrize("usable", [True, False])
def test_spawn_hands_the_backends_native_pdf_inspector_to_the_child(
    single_worker, monkeypatch, tmp_path, capsys, usable
):
    """2026-11-03: only the backend held the PDFKit inspector; the child rechecked a
    PDF 1.5 letter with the regex fallback and failed it as resume_pdf_invalid."""
    from career_evidence_graph.application_pdf import NativePDFInspector

    service, item, _, _ = single_worker
    service.request("prepare", {"workflow": "single", "send_confirmed": True, "jobs": [item]})
    executable = tmp_path / "pdf-inspect"
    executable.write_text("#!/bin/sh\nexit 1\n")
    executable.chmod(0o700 if usable else 0o600)
    service.store.pdf_inspector = NativePDFInspector(executable)
    argv, store = spawned_child_store(service, monkeypatch)
    assert argv[argv.index("--pdf-inspect") + 1] == str(executable)
    if usable:
        assert isinstance(store.pdf_inspector, NativePDFInspector)
        assert store.pdf_inspector.executable == executable
    else:
        assert getattr(store, "pdf_inspector", None) is None
        assert "pdf_inspect_ignored" in capsys.readouterr().err


def test_child_requires_explicit_matching_flow_root_and_restores_only_persisted_context(
    single_worker,
):
    from career_evidence_graph.application_worker import WorkerStore

    service, item, _, _ = single_worker
    service.request("prepare", {"workflow": "single", "send_confirmed": True, "jobs": [item]})
    child = WorkerStore(service.store.applications, service.store.root, live=True)
    with pytest.raises(PortalDataError):
        child.restore_single_context(None)
    with pytest.raises(PortalDataError):
        child.restore_single_context(service.store.root / "wrong-flow")
    child.restore_single_context(service.store.single_flow_root)
    assert child.single_context() == service.store.single_context()
    assert child.single_validator is None


def test_manual_review_handoff_rechecks_the_single_material_binding(single_worker):
    service, item, _, _ = single_worker
    service.request("prepare", {"workflow": "single", "send_confirmed": True, "jobs": [item]})
    state = service.store.load()
    state["jobs"][0]["status"] = "ready_for_review"
    service.store.save(state)

    def stale(*args, **kwargs):
        raise PortalDataError("single_binding_invalid", "Synthetic changed materials.", 409)

    service.store.single_validator = stale
    with pytest.raises(PortalDataError) as error:
        service.request("review", {"application_id": item["application_id"]})
    assert error.value.code == "single_binding_invalid"
    assert service.store.load()["jobs"][0]["handed_off"] is False


def pipeline_job(service, item, *, policy=None):
    """Publish a synthetic, once-authorized email-cycle task and its receipt."""
    root = service.store.single_flow_root
    root.mkdir(exist_ok=True)
    flow_path = root / "flow.json"
    flow = json.loads(flow_path.read_text()) if flow_path.exists() else {"tasks": []}
    if policy is None:
        policy = {
            "schemaVersion": 1,
            "protocol": "application-pipeline/v1",
            "policy_version": "email-to-manual-submit/v1",
            "id": uuid4().hex,
            "intake_run_id": uuid4().hex,
            "control": "running",
            "started_at": time.time(),
            "expires_at": time.time() + 600,
            "authorization": {
                "id": uuid4().hex,
                "verified_by": "user",
                "scope": "this_email_cycle",
                "existing_facts": True,
                "generated_pdf": True,
                "final_submit": "manual",
            },
            "items": [],
        }
    task = {
        "id": uuid4().hex,
        "application_id": item["application_id"],
        "job_binding": "synthetic-job",
        "inputs": {},
        "analysis_id": "synthetic-analysis",
        "resume_id": "synthetic-resume",
        "resume_sha256": "synthetic-pdf",
    }
    receipt = {
        **deepcopy(task),
        "policy_version": policy["policy_version"],
        "pipeline_id": policy["id"],
        "intake_run_id": policy["intake_run_id"],
        "authorization_id": policy["authorization"]["id"],
        "task_id": task["id"],
        "country": "CHE",
        "job_url": service.store.applications.get_application(item["application_id"])["url"],
    }
    task["send_approval"] = {
        **{key: task[key] for key in ("inputs", "analysis_id", "resume_id", "resume_sha256")},
        "confirmed": True,
        "verified_by": "workflow_policy",
        "actor": "system",
        "human_reviewed": False,
        "authorization": receipt,
        "country": "CHE",
        "job_url": receipt["job_url"],
    }
    flow["tasks"].append(task)
    policy["active_task_id"] = task["id"]
    policy["transmission_authorization"] = receipt
    policy["items"].append(
        {
            "task_id": task["id"],
            "application_id": task["application_id"],
            "status": "matched",
            "transmission_authorization": receipt,
        }
    )
    policy["revision"] = digest({key: value for key, value in policy.items() if key != "revision"})
    flow_path.write_text(json.dumps(flow))
    (root / "pipeline.json").write_text(json.dumps(policy))
    return {**item, "single_binding": {"task_id": task["id"]}}, policy


def test_a_cancelled_current_job_lets_the_next_job_be_prepared(single_worker):
    service, item, _, _ = single_worker
    first, policy = pipeline_job(service, item)
    service.request("prepare", {"workflow": "single", "send_confirmed": True, "jobs": [first]})
    state = service.store.load()
    state["jobs"][0]["status"] = "cancelled"
    service.store.save(state)
    app = service.store.applications.create_application(
        {
            "company": "Synthetic second",
            "role_title": "Engineer",
            "status": "drafting",
            "url": "https://jobs.lever.co/synthetic/00000000-0000-0000-0000-000000000002",
        }
    )
    second, _ = pipeline_job(
        service, {**item, "application_id": app["id"], "revision": app["revision"]}, policy=policy
    )
    service.request("prepare", {"workflow": "single", "send_confirmed": True, "jobs": [second]})
    after = service.store.load()
    assert after["current_job_id"] == app["id"]
    assert [job["status"] for job in after["jobs"]][0] == "cancelled"
    # The same job cannot be prepared again into the batch that retains it.
    with pytest.raises(PortalDataError) as error:
        service.request("prepare", {"workflow": "single", "send_confirmed": True, "jobs": [first]})
    assert error.value.code in {"current_job_exists", "job_retained"}


def test_direct_prepare_cannot_replace_a_waiting_job(single_worker):
    service, item, _, _ = single_worker
    first, policy = pipeline_job(service, item)
    service.request("prepare", {"workflow": "single", "send_confirmed": True, "jobs": [first]})
    before = service.store.load()
    before["jobs"][0].update(status="needs_input", page_open=True, questions=[{"id": "missing"}])
    service.store.save(before)
    app = service.store.applications.create_application(
        {
            "company": "Synthetic second",
            "role_title": "Engineer",
            "status": "drafting",
            "url": "https://jobs.lever.co/synthetic/00000000-0000-0000-0000-000000000002",
        }
    )
    second, _ = pipeline_job(
        service, {**item, "application_id": app["id"], "revision": app["revision"]}, policy=policy
    )
    with pytest.raises(PortalDataError) as error:
        service.request("prepare", {"workflow": "single", "send_confirmed": True, "jobs": [second]})
    assert error.value.code == "current_job_exists"
    assert service.store.load() == before
