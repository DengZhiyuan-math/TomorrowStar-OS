"""Synthetic observed fields cross the material boundary without a browser process."""

from copy import deepcopy

import pytest
from test_application_worker import job as worker_job
from test_application_worker import service as service
from test_supplemental_materials import selection, source_data

from career_evidence_graph.career_portal_data import PortalDataError


@pytest.fixture
def prepared(service, monkeypatch):
    from career_evidence_graph import application_materials

    item = worker_job(service)
    app = service.store.applications.get_application(item["application_id"])
    app = service.store.applications.update_application(
        app["id"],
        {"job_description": "Build Python services for financial analysis."},
        app["revision"],
    )
    item["revision"] = app["revision"]
    service.request("prepare", {"jobs": [item]})
    state = service.store.load()
    state.update(control="running")
    state["jobs"][0]["status"] = "filling"
    service.store.save(state)
    service.store.material_sources = source_data
    monkeypatch.setattr(application_materials, "run_codex_exec", selection)
    return service, state["jobs"][0], state["batch_id"]


def materials(prepared, *, allowed=None):
    from career_evidence_graph.application_materials import SupplementalMaterials

    service, job, batch_id = prepared

    def update(job, batch, **changes):
        state = service.store.load()
        if state["batch_id"] != batch:
            return
        current = next(
            row for row in state["jobs"] if row["application_id"] == job["application_id"]
        )
        current.update(deepcopy(changes))
        service.store.save(state)

    return SupplementalMaterials(
        service.store,
        allowed=allowed or (lambda state, identifier: state["control"] == "running"),
        update=update,
        persist=service.store.save,
    )


def question(kind="motivation_text", *, value="", filename=""):
    return {
        "id": kind,
        "question": "Why this company?" if kind == "motivation_text" else "Certificate",
        "type": "textarea" if kind == "motivation_text" else "file",
        "required": True,
        "value": value,
        "valid": True,
        "filename": filename,
        "file_sha256": "retained-sha" if filename else None,
        "resume": False,
    }


def test_material_module_preserves_human_filled_text_without_model_call(prepared, monkeypatch):
    from career_evidence_graph import application_materials

    monkeypatch.setattr(
        application_materials, "run_codex_exec", lambda *a, **kw: pytest.fail("human text")
    )
    service, job, batch = prepared
    field = question(value="My human explanation.")
    assert materials(prepared).prepare(job, batch, {"fields": [field]})
    assert service.store.load()["jobs"][0]["manual_fields"][field["id"]]["value"] == field["value"]
    assert not job.get("materials")


def test_independent_material_result_is_consumed_without_browser_dependencies(prepared):
    service, job, batch = prepared
    boundary = materials(prepared)
    assert boundary.prepare(job, batch, {"fields": [question()]})
    result = service.store.load()["jobs"][0]["materials"][0]
    assert result["status"] == "ready" and result["actor"] == "system"
    assert result["field_id"] == question()["id"]
    assert service.store.verify_material(result, job)["text"] == result["text"]


def test_lost_generation_result_stays_needs_recheck_and_never_retries(prepared, monkeypatch):
    from career_evidence_graph import application_materials

    calls = []

    def unknown(*args, **kwargs):
        calls.append(1)
        raise RuntimeError("lost recorded result")

    monkeypatch.setattr(application_materials, "run_codex_exec", unknown)
    service, job, batch = prepared
    boundary = materials(prepared)
    with pytest.raises(PortalDataError) as first:
        boundary.prepare(job, batch, {"fields": [question()]})
    assert first.value.code == "material_generation_needs_recheck"
    saved = service.store.load()["jobs"][0]["materials"][0]
    assert saved["status"] == "needs_recheck"
    with pytest.raises(PortalDataError) as failure:
        boundary.prepare(job, batch, {"fields": [question()]})
    assert failure.value.code == "material_generation_needs_recheck"
    assert calls == [1]


def test_late_material_result_is_preserved_without_resuming_execution(prepared, monkeypatch):
    from career_evidence_graph import application_materials

    service, job, batch = prepared

    def pause(*args, **kwargs):
        state = service.store.load()
        state["control"] = "paused"
        service.store.save(state)
        return selection(*args, **kwargs)

    monkeypatch.setattr(application_materials, "run_codex_exec", pause)
    assert not materials(prepared).prepare(job, batch, {"fields": [question()]})
    state = service.store.load()
    assert state["control"] == "paused"
    assert state["jobs"][0]["materials"][0]["status"] == "ready"


def test_retained_manual_attachment_keeps_original_page_provenance(prepared):
    service, job, batch = prepared
    field = question("certificate", filename="human-certificate.pdf")
    assert materials(prepared).prepare(
        job, batch, {"fields": [field]}, page_binding={"run_id": "run", "page_id": "page"}
    )
    saved = service.store.load()["jobs"][0]["materials"][0]
    assert saved["status"] == "manual"
    assert saved["source_binding"]["run_id"] == "run"
    assert saved["source_binding"]["page_id"] == "page"


def precision_job(prepared, description):
    service, job, batch = prepared
    app = service.store.applications.get_application(job["application_id"])
    service.store.applications.update_application(
        app["id"], {"job_description": description}, app["revision"]
    )
    state = service.store.load()
    state["jobs"][0]["precision_preparation"] = {"status": "preparing"}
    service.store.save(state)
    job["precision_preparation"] = {"status": "preparing"}
    return service, job, batch


def test_precision_requirements_parse_saved_jd_once_and_map_one_independent_draft(
    prepared, monkeypatch
):
    from career_evidence_graph import application_materials

    service, job, batch = precision_job(
        prepared, "Build Python services for financial analysis. Please write motivation."
    )
    parsed = []
    original = application_materials.jd_material_requirements

    def record(application):
        parsed.append(application["job_description"])
        return original(application)

    monkeypatch.setattr(application_materials, "jd_material_requirements", record)
    assert materials(prepared).prepare(job, batch, {"fields": [question()]})
    assert len(parsed) == 1
    saved = service.store.load()["jobs"][0]
    assert len(saved["materials"]) == 1
    assert saved["materials"][0]["field_bindings"][0]["field_id"] == question()["id"]
    assert (
        saved["materials"][0]["requirement_id"]
        == saved["precision_preparation"]["requirements"][0]["id"]
    )


def test_distinct_jd_requirements_keep_separate_attempts_when_field_mapping_is_ambiguous(prepared):
    service, job, batch = precision_job(
        prepared,
        "Build Python services for financial analysis. Please write motivation. "
        "Please explain why this company.",
    )
    with pytest.raises(PortalDataError) as failure:
        materials(prepared).prepare(job, batch, {"fields": [question()]})
    assert failure.value.code == "material_field_mapping_required"
    rows = service.store.load()["jobs"][0]["materials"]
    assert len(rows) == 2
    assert len({row["requirement_id"] for row in rows}) == 2
    assert len({row["attempt_id"] for row in rows}) == 2
    assert all(row["status"] == "ready" for row in rows)


def test_missing_document_waits_for_user_without_generation(prepared, monkeypatch):
    from career_evidence_graph import application_materials

    monkeypatch.setattr(
        application_materials, "run_codex_exec", lambda *a, **kw: pytest.fail("document")
    )
    service, job, batch = prepared
    assert not materials(prepared).prepare(job, batch, {"fields": [question("certificate")]})
    saved = service.store.load()["jobs"][0]
    assert saved["status"] == "needs_input" and saved["reason"] == "missing_materials"
    assert saved["materials"][0]["status"] == "needs_input"
