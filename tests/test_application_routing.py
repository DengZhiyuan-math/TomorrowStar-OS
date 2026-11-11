"""Live-entry contracts with synthetic records and no browser or network calls."""

import base64
import json

import pytest

from career_evidence_graph.application_worker import WorkerService
from career_evidence_graph.career_portal_data import ApplicationStore, PortalDataError


@pytest.fixture
def service(tmp_path, monkeypatch):
    apps = tmp_path / "applications"
    apps.mkdir()
    service = WorkerService(ApplicationStore(apps), tmp_path / "worker", live=True)
    monkeypatch.setattr(service, "spawn", lambda: None)
    return service


def item(service, index=1, **decisions):
    app = service.store.applications.create_application(
        {
            "company": f"Synthetic {index}",
            "role_title": "AI Engineer",
            "url": f"https://jobs.lever.co/synthetic/00000000-0000-0000-0000-{index:012d}",
            **decisions,
        }
    )
    return {
        "application_id": app["id"],
        "revision": app["revision"],
        "country": "CHE",
        "filename": "synthetic.pdf",
        "file_base64": base64.b64encode(b"%PDF-1.4 Synthetic").decode(),
    }


@pytest.mark.parametrize(
    "decisions", [{}, {"target_company": "target"}, {"application_strategy": "hold"}]
)
def test_unclassified_high_value_or_held_jobs_cannot_enter_batch(service, decisions):
    target = item(service, **decisions)
    with pytest.raises(PortalDataError) as error:
        service.request("prepare", {"jobs": [target]})
    assert error.value.code == "application_route_required"
    assert service.store.load()["jobs"] == []
    assert not list(service.store.root.rglob("*.pdf"))
    assert (
        service.store.applications.get_application(target["application_id"])["status"] == "drafting"
    )


def test_mixed_batch_rejects_all_jobs_before_attachment_write(service):
    targets = [
        item(service, application_strategy="batch"),
        item(service, 2, target_company="target"),
    ]
    with pytest.raises(PortalDataError, match="高价值"):
        service.request("prepare", {"jobs": targets})
    assert not list(service.store.root.rglob("*.pdf"))
    assert service.store.load()["jobs"] == []


def test_saved_batch_choice_enters_paused_queue_without_status_change(service):
    target = item(service, application_strategy="batch")
    result = service.request("prepare", {"jobs": [target]})
    assert result["control"] == "paused"
    assert result["jobs"][0]["workflow"] == "batch"
    assert (
        service.store.applications.get_application(target["application_id"])["status"] == "drafting"
    )


def test_precision_requires_one_job_and_explicit_review(service):
    target = item(service, compensation_priority="exceptional")
    for jobs, reviewed in (([target], False), ([target], "true"), ([target, target], True)):
        with pytest.raises(PortalDataError) as error:
            service.request(
                "prepare", {"jobs": jobs, "workflow": "precision", "precision_reviewed": reviewed}
            )
        assert error.value.code == "precision_review_required"
    assert not list(service.store.root.rglob("*.pdf"))
    result = service.request(
        "prepare", {"jobs": [target], "workflow": "precision", "precision_reviewed": True}
    )
    assert result["jobs"][0]["workflow"] == "precision"
    assert result["control"] == "paused"


def test_precision_flag_does_not_bypass_routing_or_duplicates(service):
    target = item(service)
    with pytest.raises(PortalDataError) as error:
        service.request(
            "prepare", {"jobs": [target], "workflow": "precision", "precision_reviewed": True}
        )
    assert error.value.code == "application_route_required"
    app = service.store.applications.get_application(target["application_id"])
    updated = service.store.applications.update_application(
        app["id"], {"application_strategy": "manual"}, app["revision"]
    )
    target["revision"] = updated["revision"]
    service.store.applications.create_application(
        {
            "company": app["company"],
            "role_title": app["role_title"],
            "url": app["url"],
            "status": "applied",
        }
    )
    with pytest.raises(PortalDataError) as error:
        service.request(
            "prepare", {"jobs": [target], "workflow": "precision", "precision_reviewed": True}
        )
    assert error.value.code == "duplicate_application"
    assert not list(service.store.root.rglob("*.pdf"))


def test_changed_decision_invalidates_prepared_input(service):
    target = item(service, application_strategy="batch")
    service.store.applications.update_application(
        target["application_id"], {"application_strategy": "manual"}, target["revision"]
    )
    with pytest.raises(PortalDataError) as error:
        service.request("prepare", {"jobs": [target]})
    assert error.value.code == "conflict"


@pytest.mark.parametrize("workflow", ["other", [], None])
def test_invalid_workflow_is_rejected_before_writes(service, workflow):
    with pytest.raises(PortalDataError) as error:
        service.request("prepare", {"jobs": [item(service)], "workflow": workflow})
    assert error.value.code == "invalid_workflow"
    assert not list(service.store.root.rglob("*.pdf"))


def test_language_change_after_upload_authorization_still_blocks_send(service):
    from pathlib import Path
    from types import SimpleNamespace

    from test_hosted_ats import multipart

    from career_evidence_graph.application_worker_browser import ApplicationRunner

    service.store.answers.put_answer(
        {"question": "French level", "value": "B2", "scope": {}, "state": "confirmed"}
    )
    target = item(service, application_strategy="batch", job_description="French B2 is required.")
    service.request("prepare", {"jobs": [target]})
    service.request("resume", {"controller": "synthetic-controller"})
    job = service.store.load()["jobs"][0]
    (service.store.root / "lever-upload-grants.json").write_text(
        json.dumps(
            {
                "schemaVersion": 1,
                "grants": [{"job_url": job["job_url"], "accountId": "public-account"}],
            }
        )
    )
    runner = ApplicationRunner(service.store, None)
    page = object()
    runner.pages[job["application_id"]] = page
    assert runner.authorize(
        job, service.store.load()["batch_id"], {"action": "upload", "sha256": job["file_sha256"]}
    )
    runner.upload_job = job
    service.store.answers.put_answer(
        {"question": "French level", "value": "A1", "scope": {}, "state": "confirmed"}
    )

    class Request(SimpleNamespace):
        __hash__ = object.__hash__

    request = Request(
        method="POST",
        url="https://jobs.lever.co/parseResume",
        resource_type="fetch",
        frame=SimpleNamespace(page=page),
        is_navigation_request=lambda: False,
        headers={"content-type": "multipart/form-data; boundary=bound"},
        post_data_buffer=multipart(Path(job["file_path"]).read_bytes()),
    )
    route = SimpleNamespace(request=request, outcome="")
    route.continue_ = lambda: setattr(route, "outcome", "allowed")
    route.abort = lambda _: setattr(route, "outcome", "blocked")

    runner._live_guard(route)

    assert route.outcome == "blocked"
    assert runner.blocked_pages[page] == "job_requirement_mismatch"
    assert service.store.stop_reason() == ""


@pytest.mark.parametrize("boundary", ["resume", "action", "review"])
def test_changed_language_level_blocks_existing_batch_at_each_boundary(service, boundary):
    from career_evidence_graph.application_worker_browser import ApplicationRunner

    service.store.answers.put_answer(
        {"question": "French level", "value": "B2", "scope": {}, "state": "confirmed"}
    )
    first = item(service, application_strategy="batch", job_description="French B2 is required.")
    second = item(service, 2, application_strategy="batch")
    service.request("prepare", {"jobs": [first, second]})
    checkpoint = service.store.load()
    job = checkpoint["jobs"][0]
    service.store.answers.put_answer(
        {"question": "French level", "value": "A1", "scope": {}, "state": "confirmed"}
    )

    if boundary == "resume":
        result = service.request("resume", {"controller": "synthetic-controller"})
        assert result["jobs"][0]["status"] == "needs_recheck"
        assert result["jobs"][0]["reason"] == "job_requirement_mismatch"
        assert result["jobs"][1]["status"] == "queued"
    else:
        with pytest.raises(PortalDataError) as failure:
            if boundary == "action":
                ApplicationRunner(service.store, None).check_inputs(job)
            else:
                service._check_review(job)
        assert failure.value.code == "job_requirement_mismatch"
        assert service.store.load() == checkpoint
    assert (
        service.store.applications.get_application(first["application_id"])["status"] == "drafting"
    )
