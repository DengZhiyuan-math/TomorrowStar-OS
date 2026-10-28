"""Human supplemental versions are conditionally adopted by their Worker owner."""

from copy import deepcopy

import pytest
from test_application_worker import service as service
from test_cover_letter_delivery import modern as modern
from test_cover_letter_edit import editable as editable
from test_cover_letter_legacy_renderer import old_editable as old_editable
from test_cover_letter_legacy_renderer import original_v1 as original_v1
from test_supplemental_material_module import prepared as prepared

from career_evidence_graph import application_material_edit as editing
from career_evidence_graph.career_portal_data import PortalDataError


def test_worker_owned_successor_adoption_reuses_the_exact_saved_edit(editable):
    flow, worker, old, payload, flow_state = editable
    result = editing.edit_material(flow, worker, None, payload)
    current = worker.store.load()["jobs"][0]
    material = deepcopy(current["materials"][0])
    edit = deepcopy(current["material_edit"])
    edit["status"] = "preparing"
    before = worker.store.path.read_bytes()
    flow_before = deepcopy(flow_state)

    retry = worker.commit_material_successor(
        old["source_binding"]["application"]["id"],
        target=edit["target"],
        edit=edit,
        material=material,
    )

    assert retry == result
    assert worker.store.path.read_bytes() == before
    assert flow_state == flow_before
    assert current["material_history"] == [old]
    assert material["text"] == payload["text"]


@pytest.mark.parametrize("fault", ["unknown", "target", "edit_id", "old_material", "candidate"])
def test_owner_rejects_changed_scope_without_overwriting_either_participant(
    editable, monkeypatch, fault
):
    flow, worker, old, payload, flow_state = editable
    save = worker.store.save

    def interrupt(value):
        if value["jobs"][0].get("material_edit", {}).get("status") == "complete":
            raise OSError("interrupt Worker adoption")
        save(value)

    with monkeypatch.context() as stopped:
        stopped.setattr(worker.store, "save", interrupt)
        with pytest.raises(OSError, match="interrupt Worker"):
            editing.edit_material(flow, worker, None, payload)
    state = worker.store.load()
    job = state["jobs"][0]
    edit = deepcopy(job["material_edit"])
    import json

    material = json.loads(
        (worker.store.root / "materials" / payload["request_id"] / "material.json").read_text()
    )
    target = deepcopy(edit["target"])
    if fault == "unknown":
        job["intent"] = {"action": "upload", "attempt_id": "unknown-before-human-adoption"}
        worker.store.save(state)
    elif fault == "target":
        target["run_id"] = "another-execution"
    elif fault == "edit_id":
        edit["request_id"] = "a" * 32
    elif fault == "old_material":
        job["materials"][0]["text"] = "Later human text"
        worker.store.save(state)
    else:
        material["text"] = "Another candidate"
    before = worker.store.path.read_bytes()
    flow_before = deepcopy(flow_state)

    with pytest.raises(PortalDataError):
        worker.commit_material_successor(
            old["source_binding"]["application"]["id"],
            target=target,
            edit=edit,
            material=material,
        )

    assert worker.store.path.read_bytes() == before
    assert flow_state == flow_before


def test_captured_source_changed_after_flow_adoption_retains_its_precise_error(
    editable, monkeypatch
):
    import hashlib
    import json

    flow, worker, old, payload, flow_state = editable
    source = worker.store.root / "materials" / "captured-human.tex"
    source.parent.mkdir(exist_ok=True)
    source.write_text("original human source")
    capture = {"path": str(source), "sha256": hashlib.sha256(source.read_bytes()).hexdigest()}
    save = worker.store.save

    def interrupt(value):
        if value["jobs"][0].get("material_edit", {}).get("status") == "complete":
            raise OSError("interrupt Worker adoption")
        save(value)

    with monkeypatch.context() as stopped:
        stopped.setattr(worker.store, "save", interrupt)
        with pytest.raises(OSError, match="interrupt Worker"):
            editing.edit_material(flow, worker, None, payload, captured_source=capture)
    source.write_text("later human source")
    edit = worker.store.load()["jobs"][0]["material_edit"]
    material = json.loads(
        (worker.store.root / "materials" / payload["request_id"] / "material.json").read_text()
    )
    before = worker.store.path.read_bytes()
    flow_before = deepcopy(flow_state)

    with pytest.raises(PortalDataError) as caught:
        worker.commit_material_successor(
            old["source_binding"]["application"]["id"],
            target=edit["target"],
            edit=edit,
            material=material,
        )

    assert caught.value.code == "cover_letter_tex_changed"
    assert worker.store.path.read_bytes() == before
    assert flow_state == flow_before
    assert source.read_text() == "later human source"
    with pytest.raises(PortalDataError) as recovered:
        editing.reconcile_material_edit(
            flow,
            worker,
            None,
            {key: payload[key] for key in ("task_id", "task_revision", "request_id")},
        )
    assert recovered.value.code == "cover_letter_tex_changed"
    assert worker.store.path.read_bytes() == before
    assert flow_state == flow_before


def test_saved_worker_successor_with_lost_response_is_not_published_twice(editable, monkeypatch):
    flow, worker, old, payload, flow_state = editable
    save = worker.store.save
    failed = False

    def saved_then_lost(value):
        nonlocal failed
        save(value)
        if value["jobs"][0].get("material_edit", {}).get("status") == "complete" and not failed:
            failed = True
            raise OSError("lost response after durable adoption")

    monkeypatch.setattr(worker.store, "save", saved_then_lost)
    with pytest.raises(OSError, match="durable adoption"):
        editing.edit_material(flow, worker, None, payload)
    before = worker.store.path.read_bytes()
    flow_before = deepcopy(flow_state)

    result = editing.edit_material(flow, worker, None, payload)

    assert result["status"] == "complete"
    assert worker.store.path.read_bytes() == before
    assert flow_state == flow_before
    assert worker.store.load()["jobs"][0]["material_history"] == [old]


def test_successor_preflight_reads_existing_records_without_creating_or_adopting(editable):
    flow, worker, old, payload, flow_state = editable
    editing.edit_material(flow, worker, None, payload)
    current = worker.store.load()["jobs"][0]
    material = deepcopy(current["materials"][0])
    edit = dict(current["material_edit"], status="preparing")
    before_files = {str(p): p.read_bytes() for p in worker.store.root.rglob("*") if p.is_file()}
    before_dirs = {str(p) for p in worker.store.root.rglob("*") if p.is_dir()}
    flow_before = deepcopy(flow_state)

    progress = worker.validate_material_successor(
        old["source_binding"]["application"]["id"],
        target=edit["target"],
        edit=edit,
        material=material,
    )

    assert progress["edit"]["status"] == "complete"
    assert progress["old_material"] == old
    assert {
        str(p): p.read_bytes() for p in worker.store.root.rglob("*") if p.is_file()
    } == before_files
    assert {str(p) for p in worker.store.root.rglob("*") if p.is_dir()} == before_dirs
    assert flow_state == flow_before


def test_owner_preserves_a_sibling_saved_after_the_original_edit_was_reserved(
    editable, monkeypatch
):
    import json

    flow, worker, old, payload, flow_state = editable
    save = worker.store.save

    def interrupt(value):
        if value["jobs"][0].get("material_edit", {}).get("status") == "complete":
            raise OSError("interrupt Worker adoption")
        save(value)

    with monkeypatch.context() as stopped:
        stopped.setattr(worker.store, "save", interrupt)
        with pytest.raises(OSError, match="interrupt Worker"):
            editing.edit_material(flow, worker, None, payload)
    current = worker.store.load()
    sibling = {"id": "a" * 32, "actor": "user", "kind": "certificate", "status": "manual"}
    current["jobs"][0]["materials"].append(sibling)
    worker.store.save(current)
    edit = deepcopy(current["jobs"][0]["material_edit"])
    material = json.loads(
        (worker.store.root / "materials" / payload["request_id"] / "material.json").read_text()
    )
    flow_before = deepcopy(flow_state)

    result = worker.commit_material_successor(
        old["source_binding"]["application"]["id"],
        target=edit["target"],
        edit=edit,
        material=material,
    )

    saved = worker.store.load()["jobs"][0]
    assert result["status"] == "complete"
    assert saved["materials"] == [material, sibling]
    assert saved["precision_preparation"]["materials"] == [material, sibling]
    assert saved["material_history"] == [old]
    assert flow_state == flow_before


def test_owner_rejects_a_saved_candidate_with_a_different_structured_human_body(
    editable, monkeypatch
):
    import json

    from career_evidence_graph.application_cover_letter import edit_cover_letter

    flow, worker, old, payload, flow_state = editable
    save = worker.store.save

    def interrupt(value):
        if value["jobs"][0].get("material_edit", {}).get("status") == "complete":
            raise OSError("stop before Worker save")
        save(value)

    with monkeypatch.context() as stopped:
        stopped.setattr(worker.store, "save", interrupt)
        with pytest.raises(OSError, match="before Worker save"):
            editing.edit_material(flow, worker, None, payload)
    edit = deepcopy(worker.store.load()["jobs"][0]["material_edit"])
    path = worker.store.root / "materials" / payload["request_id"] / "material.json"
    candidate = json.loads(path.read_text())
    other = edit_cover_letter(
        old["letter_content"],
        "This body was not the text in the reserved human edit.",
        expected_revision=old["content_revision"],
        edit_id=payload["request_id"],
    )
    candidate.update(letter_content=other, content_revision=other["revision"])
    path.write_text(json.dumps(candidate))
    before = worker.store.path.read_bytes()
    flow_before = deepcopy(flow_state)
    candidate_before = path.read_bytes()

    with pytest.raises(PortalDataError) as caught:
        worker.commit_material_successor(
            old["source_binding"]["application"]["id"],
            target=edit["target"],
            edit=edit,
            material=candidate,
        )

    assert caught.value.code == "material_changed"
    assert worker.store.path.read_bytes() == before
    assert flow_state == flow_before
    assert path.read_bytes() == candidate_before
    assert candidate["text"] == payload["text"]
    with pytest.raises(PortalDataError) as recovered:
        editing.reconcile_material_edit(
            flow,
            worker,
            None,
            {key: payload[key] for key in ("task_id", "task_revision", "request_id")},
        )
    assert recovered.value.code == "material_edit_needs_recheck"
    assert worker.store.path.read_bytes() == before
    assert flow_state == flow_before
    assert path.read_bytes() == candidate_before


def test_legacy_human_successor_recovers_without_rebuilding_or_repeating_history(
    old_editable, monkeypatch
):
    flow, worker, old, payload, flow_state = old_editable
    save = worker.store.save

    def interrupt(value):
        if value["jobs"][0].get("material_edit", {}).get("status") == "complete":
            raise OSError("stop before legacy Worker save")
        save(value)

    with monkeypatch.context() as stopped:
        stopped.setattr(worker.store, "save", interrupt)
        with pytest.raises(OSError, match="legacy Worker"):
            editing.edit_material(flow, worker, None, payload)
    flow_before = deepcopy(flow_state)
    request = {key: payload[key] for key in ("task_id", "task_revision", "request_id")}

    recovered = editing.reconcile_material_edit(flow, worker, None, request)

    current = worker.store.load()["jobs"][0]
    assert recovered["status"] == "complete"
    assert current["materials"][0]["text"] == payload["text"]
    assert current["materials"][0]["text_suffix"] == old["text_suffix"]
    assert current["material_history"] == [old]
    assert flow_state == flow_before
    before = worker.store.path.read_bytes()
    assert editing.reconcile_material_edit(flow, worker, None, request) == recovered
    assert worker.store.path.read_bytes() == before
    assert flow_state == flow_before
