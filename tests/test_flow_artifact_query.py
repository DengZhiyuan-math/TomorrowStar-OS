"""Historical artifact queries retain adopted results without current projections."""

import hashlib
import json

import pytest
from test_application_flow import application as application
from test_application_flow import wait_for
from test_career_portal_http import portal as portal
from test_draft_http import import_latex_draft
from test_job_explanation_browser import explanation_portal
from test_pdf_export_http import SyntheticLatexClient, create_authorized_latex, export_payload
from test_preparation_entry import post

from career_evidence_graph.application_flow import ApplicationFlowService
from career_evidence_graph.application_flow_store import assemble
from career_evidence_graph.career_portal_data import ApplicationStore, PortalDataError


@pytest.fixture(autouse=True)
def isolated_connection(tmp_path, monkeypatch):
    monkeypatch.setenv("CODEX_HOME", str(tmp_path / "synthetic-codex"))
    monkeypatch.delenv("CODEX_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)


def test_service_reads_adopted_draft_without_current_source_projection(portal, tmp_path):
    job = ApplicationStore(portal.applications).create_application(
        {"company": "Synthetic", "role_title": "Engineer", "job_description": "Build Python."}
    )
    with explanation_portal(portal, tmp_path) as (active, _work):
        task = create_authorized_latex(active, job)
        service = active.server.application_flow_service
        before = service.path.read_bytes()

        def unavailable_inputs(_application_id):
            raise AssertionError("Historical queries must not read current source inputs")

        service.input_provider = unavailable_inputs
        result = service.adopted_artifact("resume", task["draft_id"], kind="draft")

        assert result["id"] == task["draft_id"]
        assert result["kind"] == "draft"
        assert result["draft_sha256"] == task["draft_sha256"]
        assert service.path.read_bytes() == before


def test_cancelled_task_keeps_draft_and_export_queryable_without_changing_history(portal, tmp_path):
    job = ApplicationStore(portal.applications).create_application(
        {"company": "Synthetic", "role_title": "Engineer", "job_description": "Build Python."}
    )
    with explanation_portal(portal, tmp_path) as (active, _work):
        active.server.application_resume_store.prism_client = SyntheticLatexClient()
        service = active.server.application_flow_service
        task = create_authorized_latex(active, job)
        assert post(active, "export-pdf", export_payload(task))[0] == 200
        task = wait_for(service, task["id"], lambda row: row["status"] == "resume_ready")
        service.cancel(task["id"], task["revision"])
        history = {
            path: path.read_bytes()
            for path in service.root.rglob("*")
            if path.is_file() and not path.name.startswith(".")
        }

        draft = service.adopted_artifact("resume", task["draft_id"], kind="draft")
        exported = service.adopted_artifact("export", task["resume_id"])
        assert draft["draft_sha256"] == task["draft_sha256"]
        assert exported["pdf_sha256"] == task["resume_sha256"]
        assert service.adopted_artifact("export", task["draft_id"]) is None
        assert service.adopted_artifact("resume", task["draft_id"], kind="pdf") is None
        assert service.adopted_artifact("export", "0" * 32) is None
        draft["analysis_binding"]["analysis_id"] = "Changed caller copy"
        assert (
            service.adopted_artifact("resume", task["draft_id"], kind="draft")["analysis_binding"]
            == {}
        )
        assert active.request("GET", "/api/flow/drafts/" + task["draft_id"])[0] == 200
        assert active.request("GET", "/api/flow/exports/" + task["resume_id"])[0] == 200
        assert all(path.read_bytes() == raw for path, raw in history.items())


@pytest.mark.parametrize("damage", ["task_revision", "root", "mode", "json"])
def test_artifact_query_keeps_persisted_state_validation(application, tmp_path, damage):
    applications, job = application
    service = ApplicationFlowService(applications, tmp_path / "flow", preparation_only=True)
    try:
        service.create(job["id"], job["revision"])
        original = service.path.read_bytes()
        state = assemble(service.path.parent, json.loads(original))
        if damage == "task_revision":
            state["tasks"][0]["revision"] = "0" * 64
        elif damage == "root":
            state["applications_root"] = str(tmp_path / "different-applications")
        elif damage == "mode":
            state["mode"] = "application"
        service.path.write_text("{" if damage == "json" else json.dumps(state))
        damaged = service.path.read_bytes()
        with pytest.raises(PortalDataError) as error:
            service.adopted_artifact("export", "0" * 32)
        assert error.value.code == ("flow_mode_mismatch" if damage == "mode" else "flow_invalid")
        assert service.path.read_bytes() == damaged
        service.path.write_bytes(original)
    finally:
        service.close()


def _job(portal, company="Synthetic"):
    return ApplicationStore(portal.applications).create_application(
        {"company": company, "role_title": "Engineer", "job_description": "Build Python services."}
    )


def _draft_payload(task, draft=None):
    draft = draft or task
    return {
        "task_id": task["id"],
        "task_revision": task["revision"],
        "draft_id": draft["draft_id"],
        "draft_sha256": draft["draft_sha256"],
    }


def _code(call, *args):
    with pytest.raises(PortalDataError) as error:
        call(*args)
    return error.value.code


def test_draft_query_returns_persisted_review_inputs_and_authorizes_only_export(portal, tmp_path):
    with explanation_portal(portal, tmp_path) as (active, work):
        task = import_latex_draft(active, _job(portal), tmp_path)
        service = active.server.application_flow_service
        assert task["status"] == "draft_ready" and work["exports"] == []
        draft = service.read_draft(task["draft_id"])
        assert draft["draft_sha256"] == task["draft_sha256"]
        assert draft["language"] == "und" and draft["review_status"] == "review_required"
        assert draft["task_inputs"] == task["inputs"]
        service.verify_draft(task)
        calls = list(work["calls"])
        payload = _draft_payload(task)
        stale = payload | {"draft_sha256": "f" * 64}
        assert _code(service.review_draft, *stale.values()) == "flow_factual_review_required"
        assert _code(service.review_draft, *payload.values()) == "flow_factual_review_required"
        authorized = service.authorize_latex_export(*payload.values())
        assert authorized["export_authorization"]["scope"] == "technical_export"
        assert authorized["factual_review"] == "pending"
        assert authorized["draft_review"] is None
        assert authorized["materials_confirmed"] is False and authorized["resume_id"] is None
        assert work["calls"] == calls and work["exports"] == []


@pytest.mark.parametrize("damage", ["bytes", "self_consistent_integrity"])
def test_corrupted_draft_cannot_be_queried_reviewed_or_authorized(portal, tmp_path, damage):
    with explanation_portal(portal, tmp_path) as (active, work):
        task = import_latex_draft(active, _job(portal), tmp_path)
        service = active.server.application_flow_service
        directory = active.server.application_resume_store.root / task["draft_id"]
        path = directory / "draft.json"
        if damage == "bytes":
            path.write_bytes(b'{"unverified":"changed"}')
        else:
            content = json.loads(path.read_bytes())
            content["limitations"].append("A changed claim absent from the adopted artifact.")
            path.write_text(json.dumps(content))
            (directory / "draft-integrity.json").write_text(
                json.dumps(
                    {
                        "schemaVersion": 1,
                        "id": task["draft_id"],
                        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                    }
                )
            )
        code = _code(service.read_draft, task["draft_id"])
        if damage == "self_consistent_integrity":
            assert code == "flow_draft_changed"
        assert _code(service.verify_draft, task) == code
        payload = _draft_payload(task).values()
        _code(service.review_draft, *payload)
        _code(service.authorize_latex_export, *payload)
        assert not service.task_snapshot(task["id"]).get("draft_review")
        assert work["exports"] == []


def test_another_jobs_draft_cannot_be_reviewed_or_authorized(portal, tmp_path):
    with explanation_portal(portal, tmp_path) as (active, work):
        service = active.server.application_flow_service
        first, second = (
            import_latex_draft(active, _job(portal, name), tmp_path) for name in ("First", "Second")
        )
        payload = _draft_payload(first, second).values()
        assert _code(service.review_draft, *payload) == "flow_factual_review_required"
        assert _code(service.authorize_latex_export, *payload) == "flow_draft_mismatch"
        assert not service.task_snapshot(first["id"]).get("draft_review")
        assert work["exports"] == []


@pytest.mark.parametrize("damage", ["pdf_bytes", "manifest_bytes"])
def test_export_query_reads_only_adopted_bytes(portal, tmp_path, damage):
    with explanation_portal(portal, tmp_path) as (active, work):
        active.server.application_resume_store.prism_client = SyntheticLatexClient()
        service = active.server.application_flow_service
        task = create_authorized_latex(active, _job(portal))
        calls = list(work["calls"])
        service.export_pdf(*_draft_payload(task).values())
        task = wait_for(service, task["id"], lambda row: row["status"] == "resume_ready")
        identifier = task["resume_id"]
        assert service.read_export(identifier)["pdf_sha256"] == task["resume_sha256"]
        assert _code(service.read_export, task["draft_id"]) == "flow_export_not_found"
        service.verify_materials(task)
        path = active.server.application_resume_store.root / identifier / "resume.pdf"
        if damage == "pdf_bytes":
            path.write_bytes(path.read_bytes() + b"corrupted")
        else:
            manifest = path.parent / "export.json"
            manifest.write_text(json.dumps(json.loads(manifest.read_text()), indent=3))
        code = _code(service.read_export, identifier)
        assert _code(service.verify_materials, task) == code
        service.verify_draft(task)
        _code(
            service.confirm_materials,
            task["id"],
            task["revision"],
            identifier,
            task["resume_sha256"],
        )
        assert not service.task_snapshot(task["id"])["materials_confirmed"]
        assert work["calls"] == calls


def test_orphan_export_and_other_jobs_draft_are_not_adopted(portal, tmp_path):
    with explanation_portal(portal, tmp_path) as (active, _):
        store = active.server.application_resume_store
        store.prism_client = SyntheticLatexClient()
        service = active.server.application_flow_service
        first = create_authorized_latex(active, _job(portal, "Synthetic A"))
        second = create_authorized_latex(active, _job(portal, "Synthetic B"))
        _code(service.export_pdf, *_draft_payload(second, first).values())
        orphan = store.export_for_draft(
            first["draft_id"],
            first["draft_sha256"],
            task_inputs=first["inputs"],
            export_id="e" * 32,
            prism=first["prism"],
        )
        assert _code(service.read_export, orphan["id"]) == "flow_export_not_found"
        _code(
            service.confirm_materials,
            second["id"],
            second["revision"],
            orphan["id"],
            orphan["pdf_sha256"],
        )
        assert not service.task_snapshot(second["id"]).get("resume_id")
