"""Supplemental writing reuses the adopted P04 archive without rereading career facts."""

import json
from copy import deepcopy

import pytest
from test_canonical_career_sources import canonical as canonical
from test_j08_flow_combination import json_flow as json_flow
from test_j08_material_binding import json_material as json_material
from test_j08_material_binding import recorded_pipeline_clock as recorded_pipeline_clock
from test_j08_worker_information import bound_worker

from career_evidence_graph.application_worker import WorkerStore
from career_evidence_graph.career_portal_data import CareerCatalog, PortalDataError


def test_single_supplement_sources_reuse_delivered_archive_in_backend_and_reopened_worker(
    json_material, monkeypatch
):
    worker, job = bound_worker(json_material)
    archive = (
        worker.store.single_flow_root
        / "analyses"
        / job["single_binding"]["analysis_id"]
        / "source-snapshot.json"
    )
    expected = json.loads(archive.read_text())

    def no_catalog(*args, **kwargs):
        pytest.fail("A bound single material must not scan the current career catalog")

    monkeypatch.setattr(CareerCatalog, "_paths", no_catalog)
    assert worker.store.material_sources(job) == expected
    reopened = WorkerStore(
        json_material.applications,
        worker.store.root,
        live=True,
        single_flow_root=worker.store.single_flow_root,
        single_career_root=worker.store.single_career_root,
    )
    assert reopened.material_sources(job) == expected


@pytest.mark.parametrize("change", ["missing", "corrupt", "revision", "analysis", "task"])
def test_missing_or_changed_delivery_stops_without_catalog_fallback(
    json_material, monkeypatch, change
):
    worker, job = bound_worker(json_material)
    directory = worker.store.single_flow_root / "analyses" / job["single_binding"]["analysis_id"]
    snapshot = directory / "source-snapshot.json"
    if change == "missing":
        snapshot.unlink()
    elif change == "corrupt":
        snapshot.write_text("{")
    elif change == "revision":
        data = json.loads(snapshot.read_text())
        data["revision"] = "changed"
        snapshot.write_text(json.dumps(data))
    elif change == "analysis":
        data = json.loads((directory / "analysis.json").read_text())
        data["application_id"] = "0" * 32
        (directory / "analysis.json").write_text(json.dumps(data))
    else:
        job = deepcopy(job)
        job["single_binding"]["analysis_id"] = "0" * 32
    with pytest.raises(PortalDataError) as failure:
        worker.store.material_sources(job)
    assert failure.value.code in {"single_binding_invalid", "single_material_sources_invalid"}


def test_canonical_letter_consumes_same_full_facts_and_reuses_body_on_new_fields(
    json_material, tmp_path
):
    from test_application_flow import wait_for
    from test_cover_letter_delivery import TEMPLATE, field
    from test_supplemental_material_module import materials

    from career_evidence_graph.application_cover_letter import adopted_letter

    worker, job = bound_worker(json_material)
    task_id = job["single_binding"]["task_id"]
    task = wait_for(
        json_material.flow,
        task_id,
        lambda row: (
            row["stages"].get("letter", {}).get("status") == "complete"
            and row.get("material_consistency", {}).get("status") == "passed"
        ),
    )
    state = worker.store.load()
    state["control"] = "running"
    state["jobs"][0]["status"] = "filling"
    worker.store.save(state)
    job = state["jobs"][0]
    template = tmp_path / "private-letter.tex"
    template.write_text(TEMPLATE)
    worker.store.cover_letter_template = template
    boundary = materials((worker, job, state["batch_id"]))
    assert boundary.prepare(job, state["batch_id"], {"fields": [field()]})
    material = worker.store.load()["jobs"][0]["materials"][0]
    assert material["content_revision"] == adopted_letter(task)["content_revision"]
    assert worker.store.verify_material(material, job)["letter_content"]
    assert boundary.prepare(job, state["batch_id"], {"fields": [field("new-field")]})
    current = worker.store.load()["jobs"][0]
    versions = {row["content_revision"] for row in current["materials"]}
    assert versions == {material["content_revision"]}
