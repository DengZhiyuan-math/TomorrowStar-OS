"""Human and automatic material versions prepare from their adopted sources.

Source-archive comparisons served the removed contact check (APP-04, 2026-11-01).
"""

import json
from types import SimpleNamespace

import pytest
from test_application_flow import application as application
from test_application_flow import wait_for
from test_application_resume import task_resume as task_resume
from test_application_resume_author import author_output, response
from test_canonical_career_sources import canonical as canonical
from test_imported_content_mapping import mapped_import as mapped_import
from test_j08_flow_combination import json_flow as json_flow
from test_j08_material_binding import json_material as json_material
from test_j08_material_binding import prepared_pdf
from test_j08_material_binding import recorded_pipeline_clock as recorded_pipeline_clock
from test_p08_combination import SavedPrism
from test_p08_combination import combination as combination

from career_evidence_graph.application_prism import source_snapshot

pytestmark = pytest.mark.usefixtures("planner_path")


def test_real_imported_root_keeps_its_local_human_successor_without_career_archive(mapped_import):
    store, application, project, _mapping = mapped_import
    parent = store.import_latex_for_task(
        application["id"],
        application["revision"],
        task_inputs={"synthetic": "current"},
        prism=source_snapshot(project, "main.tex"),
    )
    assert parent["origin"] == "existing_latex" and parent["analysis_binding"] == {}
    store.prism_client = SavedPrism()
    store.model_runner = lambda *_args, **_kwargs: SimpleNamespace(
        structured_result={"patches": [], "notices": []}
    )
    session = store.begin_prism_edit(
        parent["id"], parent["draft_sha256"], task_inputs=parent["task_inputs"]
    )
    child = store.finish_prism_edit(session["id"])
    assert child["origin"] == "generated_latex"
    assert child["material_version_contract"] == "local-material/v1"
    assert child["analysis_binding"] == {}
    assert store.draft(child["id"]) == {
        key: value for key, value in child.items() if key != "prism_edit"
    }


def test_content_writer_preserves_the_public_full_snapshot_choice(json_material, monkeypatch):
    case = json_material
    generate = case.store.generate_for_task

    def full_snapshot(identifier, revision, **request):
        analysis = request["analysis"]
        path = case.flow.root / "analyses" / analysis["id"] / "binding-source-snapshot.json"
        full = json.loads(path.read_text())
        assert full["revision"] == analysis["input_source_snapshot_revision"]
        assert full["revision"] != analysis["source_snapshot_revision"]
        return generate(identifier, revision, **(request | {"source_snapshot": full}))

    monkeypatch.setattr(case.store, "generate_for_task", full_snapshot)
    task = prepared_pdf(case, None)
    parent = case.store.draft(task["draft_id"])
    assert parent["generation_contract"] == "content-writing/v1"
    root = case.store.root / parent["id"]
    archive = root / "source-snapshot.json"
    original = json.loads(archive.read_text())
    assert original["revision"] == task["inputs"]["sources_revision"]
    assert original["revision"] != parent["analysis_binding"]["source_snapshot_revision"]
    worker = case.server.worker_service
    prepared = case.flow.prepare_worker(task["id"], task["revision"], "CHE", True)
    assert prepared["worker_ref"]["job_id"] == task["application_id"]
    worker.store.check_single(worker.store.load()["jobs"][0], worker.store.load())


@pytest.mark.parametrize("json_flow", [{"automatic_resume_author": True}], indirect=True)
def test_default_automatic_author_exports_and_prepares_without_manual_handoff(
    json_material, monkeypatch
):
    case = json_material
    previous = case.store.model_runner

    def runner(config, prompt, **options):
        if "automatic-authors" in config.workspace.parts:
            return response(author_output(json.loads(prompt.split("\n", 1)[1])))
        return previous(config, prompt, **options)

    monkeypatch.setattr(case.store, "model_runner", runner)
    task = case.flow.create(case.job["id"], case.job["revision"])
    case.flow.start(task["id"], task["revision"], "analysis")
    task = wait_for(
        case.flow, task["id"], lambda row: row["status"] in {"analysis_ready", "failed"}
    )
    assert task["status"] == "analysis_ready"
    task = case.flow.prepare_automatic_materials(
        task["id"], task["revision"], project_root=str(case.project), main="main.tex"
    )
    case.flow.start(task["id"], task["revision"], "resume")
    task = wait_for(case.flow, task["id"], lambda row: row["status"] in {"draft_ready", "failed"})
    assert task["status"] == "draft_ready", task
    task = wait_for(
        case.flow,
        task["id"],
        lambda row: (
            row.get("cover_letter", {}).get("status") not in {"queued", "running"}
            and row.get("material_consistency", {}).get("status") not in {"queued", "running"}
        ),
    )
    assert not any(row["result"].get("kind") == "experience_handoff" for row in task["artifacts"])
    case.flow.start(task["id"], task["revision"], "export")
    task = wait_for(
        case.flow, task["id"], lambda row: row["status"] in {"materials_ready", "failed"}
    )
    assert task["status"] == "materials_ready", task
    task = wait_for(
        case.flow,
        task["id"],
        lambda row: row.get("material_consistency", {}).get("status") not in {"queued", "running"},
    )
    worker = case.server.worker_service
    prepared = case.flow.prepare_worker(task["id"], task["revision"], "CHE", True)
    assert prepared["worker_ref"]["job_id"] == task["application_id"]
    state = worker.store.load()
    worker.store.check_single(state["jobs"][0], state)
