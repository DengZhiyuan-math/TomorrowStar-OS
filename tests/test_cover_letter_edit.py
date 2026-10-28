"""Human successors retain the application body across interrupted page saves."""

from copy import deepcopy
from types import MethodType, SimpleNamespace

import pytest
from test_application_worker import service as service
from test_cover_letter_delivery import field
from test_cover_letter_delivery import modern as modern
from test_supplemental_material_module import materials
from test_supplemental_material_module import prepared as prepared

from career_evidence_graph import application_material_edit as editing
from career_evidence_graph.application_flow import ApplicationFlowService
from career_evidence_graph.career_portal_data import PortalDataError


@pytest.fixture
def editable(modern, monkeypatch, request):
    prepared, fixed = modern
    worker, job, batch = prepared
    if getattr(request, "param", {}).get("role_slot"):
        from career_evidence_graph.application_cover_letter import ROLE_TITLE_SLOT

        template = worker.store.cover_letter_template
        template.write_text(
            template.read_text().replace(
                "Dear Hiring Team,\n\n",
                "% BEGIN LETTER OPENING\nDear Hiring Team,\n\nI am writing to apply for "
                + ROLE_TITLE_SLOT
                + ".\n% END LETTER OPENING\n\n",
            )
        )
    assert materials(prepared).prepare(job, batch, {"fields": [field()]})
    from career_evidence_graph.application_worker import start_run

    task_id = "e" * 32
    run_id = start_run(worker.store)
    state = worker.store.load()
    state.update(control="paused", current_job_id=job["application_id"])
    state["jobs"][0].update(
        status="needs_input",
        page_observation={"run_id": run_id, "page_id": "letter-edit-page", "at": 1.0},
        precision_preparation={
            "status": "ready",
            "task_id": task_id,
            "run_id": run_id,
            "page_id": "letter-edit-page",
            "document_token": "letter-edit-document",
        },
    )
    worker.store.save(state)
    old = deepcopy(state["jobs"][0]["materials"][0])
    fixed["cover_letter"]["attempt_id"] = old["letter_attempt_id"]
    flow_state = {
        "tasks": [
            {
                "id": task_id,
                "application_id": job["application_id"],
                "cover_letter": deepcopy(fixed["cover_letter"]),
            }
        ]
    }

    def save_flow(value):
        flow_state.update(deepcopy(value))
        fixed["cover_letter"] = deepcopy(value["tasks"][0]["cover_letter"])

    flow = SimpleNamespace(
        applications=worker.store.applications,
        _load=lambda: deepcopy(flow_state),
        _task=lambda value, identifier: next(
            row for row in value["tasks"] if row["id"] == identifier
        ),
        _save=save_flow,
        _writable=lambda: None,
        _reserve_material_consistency=lambda task: task.update(
            material_consistency={"status": "queued"}
        ),
    )
    flow.adopt_cover_letter_successor = MethodType(
        ApplicationFlowService.adopt_cover_letter_successor, flow
    )

    def target(*args):
        current = worker.store.load()
        return (
            current,
            current["jobs"][0],
            {
                "batch_id": current["batch_id"],
                "task_id": task_id,
                "application_id": job["application_id"],
                "run_id": current["runtime"]["id"],
                "page_id": current["jobs"][0]["page_observation"]["page_id"],
                "document_token": current["jobs"][0]["precision_preparation"]["document_token"],
            },
        )

    monkeypatch.setattr(editing, "_edit_target", target)
    payload = {
        "task_id": task_id,
        "task_revision": "revision",
        "material_id": old["id"],
        "expected_text_sha256": old["text_sha256"],
        "request_id": "f" * 32,
        "text": old["text"].replace("Built Python services", "Helped build Python services"),
    }
    return flow, worker, old, payload, flow_state


def test_human_edit_updates_canonical_body_without_pdf_or_author(editable):
    flow, worker, old, payload, state = editable
    result = editing.edit_material(flow, worker, None, payload)
    current = worker.store.load()["jobs"][0]
    saved = current["materials"][0]
    assert result["status"] == "complete"
    assert saved["text"] == payload["text"] and saved["actor"] == "user"
    assert "file_path" not in saved
    assert current["material_history"][-1] == old
    branch = state["tasks"][0]["cover_letter"]
    assert branch["result"]["content_revision"] == saved["content_revision"]
    assert branch["result"]["content"]["paragraphs"][0]["protected"] is True
    assert branch["content_history"][-1]["content_revision"] == old["content_revision"]


def test_fixed_text_edit_retains_original_body(editable):
    flow, worker, old, payload, state = editable
    payload["text"] = payload["text"].replace("Dear Hiring Team", "Dear Different Team")
    with pytest.raises(PortalDataError) as caught:
        editing.edit_material(flow, worker, None, payload)
    assert caught.value.code == "letter_fixed_text_changed"
    assert worker.store.load()["jobs"][0]["materials"][0] == old
    assert not worker.store.load()["jobs"][0].get("material_edit")
    assert (
        state["tasks"][0]["cover_letter"]["result"]["content_revision"] == old["content_revision"]
    )


@pytest.mark.parametrize("editable", [{"role_slot": True}], indirect=True)
def test_body_edit_preserves_program_filled_role_and_rejects_role_rewrite(editable):
    flow, worker, old, payload, _ = editable
    title = old["source_binding"]["application"]["role_title"]
    phrase = "I am writing to apply for " + title + "."
    assert phrase in old["text"]
    with pytest.raises(PortalDataError) as error:
        editing.edit_material(
            flow,
            worker,
            None,
            {
                **payload,
                "text": payload["text"].replace(phrase, "I am writing to apply for Other role."),
            },
        )
    assert error.value.code == "letter_fixed_text_changed"
    assert editing.edit_material(flow, worker, None, payload)["status"] == "complete"
    saved = worker.store.load()["jobs"][0]["materials"][0]
    assert phrase in saved["text"] and "Helped build Python services" in saved["text"]
    assert phrase not in saved["letter_content"]["paragraphs"][0]["text"]


def test_interrupted_page_save_reconciles_canonical_successor_without_new_edit(
    editable, monkeypatch
):
    flow, worker, old, payload, state = editable
    save = worker.store.save
    failed = False

    def interrupt(value):
        nonlocal failed
        if value["jobs"][0].get("material_edit", {}).get("status") == "complete" and not failed:
            failed = True
            raise OSError("synthetic interrupted page save")
        return save(value)

    monkeypatch.setattr(worker.store, "save", interrupt)
    with pytest.raises(OSError):
        editing.edit_material(flow, worker, None, payload)
    revision = state["tasks"][0]["cover_letter"]["result"]["content_revision"]
    assert worker.store.load()["jobs"][0]["materials"][0] == old
    receipt = editing.reconcile_material_edit(
        flow,
        worker,
        None,
        {key: payload[key] for key in ("task_id", "task_revision", "request_id")},
    )
    assert receipt["status"] == "complete"
    assert worker.store.load()["jobs"][0]["materials"][0]["content_revision"] == revision
    assert len(state["tasks"][0]["cover_letter"]["content_history"]) == 1


@pytest.mark.parametrize("fixed_edit", [False, True])
def test_tex_capture_maps_only_body_and_preserves_original_source_and_pdf(editable, fixed_edit):
    import hashlib

    from test_cover_letter_delivery import TEMPLATE

    from career_evidence_graph.application_cover_letter import render_cover_letter

    flow, worker, old, payload, _ = editable
    directory = worker.store.root / "materials" / old["id"]
    directory.mkdir(parents=True)
    rendered = render_cover_letter(old["letter_content"], TEMPLATE)
    source = directory / "main.tex"
    changed = rendered["tex"].replace(
        "Dear Hiring Team" if fixed_edit else "Built Python services",
        "Dear Changed Team" if fixed_edit else "Helped build Python services",
    )
    source.write_text(changed)
    pdf = directory / "letter.pdf"
    pdf.write_bytes(b"immutable synthetic PDF fixture")
    old.update(
        tex_path=str(source),
        tex_sha256=hashlib.sha256(rendered["tex"].encode()).hexdigest(),
        file_path=str(pdf),
        sha256=hashlib.sha256(pdf.read_bytes()).hexdigest(),
    )
    state = worker.store.load()
    state["jobs"][0]["materials"][0] = deepcopy(old)
    worker.store.save(state)
    request = {
        key: payload[key] for key in ("task_id", "task_revision", "material_id", "request_id")
    }
    request["expected_content_revision"] = old["content_revision"]
    if fixed_edit:
        with pytest.raises(PortalDataError) as caught:
            editing.capture_material_tex(flow, worker, None, request)
        assert caught.value.code == "letter_tex_mapping_required"
        assert worker.store.load()["jobs"][0]["materials"][0] == old
    else:
        result = editing.capture_material_tex(flow, worker, None, request)
        assert result["status"] == "complete"
        saved = worker.store.load()["jobs"][0]["materials"][0]
        assert "Helped build Python services" in saved["text"]
        assert saved["actor"] == "user" and "file_path" not in saved
    assert source.read_text() == changed
    assert pdf.read_bytes() == b"immutable synthetic PDF fixture"
    retained = worker.store.root / "material-source-edits" / request["request_id"]
    assert (retained / "edited-main.tex").read_text() == changed
    assert (retained / "source.diff").read_text()
