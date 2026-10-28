"""Human material versions retain exact source archives through fixed parent links."""

import hashlib
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
from test_p08_combination import SavedPrism, prepare_human_material
from test_p08_combination import combination as combination

from career_evidence_graph.application_experience_latex import _fixed_inputs_revision
from career_evidence_graph.application_prism import source_snapshot
from career_evidence_graph.application_single_binding import _adopted_source_archive
from career_evidence_graph.application_worker import digest, start_run
from career_evidence_graph.application_worker_browser import ApplicationRunner
from career_evidence_graph.career_portal_data import PortalDataError


@pytest.mark.parametrize(
    "problem",
    [
        "missing",
        "rehashed",
        "parent-bytes",
        "parent-sha",
        "cycle",
        "parent-origin",
        "parent-origin-missing",
        "child-shadow",
    ],
)
def test_human_successor_cannot_skip_changed_original_source_archive(json_material, problem):
    case = json_material
    task = prepared_pdf(case, "mapped")
    task = case.flow.prepare_worker(task["id"], task["revision"], "CHE", True)
    worker = case.server.worker_service
    start_run(worker.store)
    worker.request("resume", {"controller": "synthetic-controller"})
    assert not (case.store.root / task["draft_id"] / "source-snapshot.json").exists()
    saved = case.flow._load()
    current = case.flow._task(saved, task["id"])
    artifact = next(
        row
        for row in reversed(current["artifacts"])
        if row["stage"] == "resume" and row["result"]["id"] == task["draft_id"]
    )
    manual = artifact["result"]["manual_source"]
    parent = case.store.root / manual["parent_draft_id"]
    archive = parent / "source-snapshot.json"
    if problem == "child-shadow":
        selected = case.flow.root / "analyses" / task["analysis_id"] / "source-snapshot.json"
        (case.store.root / task["draft_id"] / "source-snapshot.json").write_bytes(
            selected.read_bytes()
        )
        archive.unlink()
    elif problem == "missing":
        archive.unlink()
    elif problem == "rehashed":
        source = json.loads(archive.read_text())
        source["profile"]["name"] = "Rehashed changed parent profile"
        source["revision"] = digest(
            {key: value for key, value in source.items() if key != "revision"}
        )
        archive.write_text(json.dumps(source))
    elif problem == "parent-bytes":
        path = parent / "draft.json"
        path.write_bytes(path.read_bytes() + b"\n")
    elif problem in {"parent-origin", "parent-origin-missing"}:
        path = parent / "draft.json"
        record = json.loads(path.read_text())
        if problem == "parent-origin":
            record["origin"] = "existing_latex"
        else:
            record.pop("origin")
        raw = json.dumps(record).encode()
        path.write_bytes(raw)
        manual["parent_draft_sha256"] = hashlib.sha256(raw).hexdigest()
        archive.unlink()
        case.flow._save(saved)
    else:
        if problem == "parent-sha":
            manual["parent_draft_sha256"] = "0" * 64
        else:
            manual.update(
                parent_draft_id=task["draft_id"], parent_draft_sha256=task["draft_sha256"]
            )
        case.flow._save(saved)
    state = worker.store.load()
    before = worker.store.path.read_bytes()
    runner = ApplicationRunner(worker.store, None)
    with pytest.raises(PortalDataError) as error:
        runner.authorize(
            state["jobs"][0], state["batch_id"], {"action": "fill", "field_id": "name"}
        )
    assert error.value.code == "single_binding_invalid"
    assert worker.store.path.read_bytes() == before


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
    task = {"application_id": application["id"], "inputs": child["task_inputs"]}
    assert _adopted_source_archive(store.root.parent, task, child, child["id"]) is None


@pytest.mark.parametrize(
    "problem", ["alternate-archive", "request-source", "self-consistent-request"]
)
def test_fixed_writer_keeps_its_actual_snapshot_choice_and_external_receipt(combination, problem):
    case = combination
    task, _pdf, _source, _manual, parent = prepare_human_material(case)
    root = case.store.root / parent["id"]
    archive = root / "source-snapshot.json"
    original = json.loads(archive.read_text())
    alternate = json.loads(
        (case.flow.root / "analyses" / task["analysis_id"] / "source-snapshot.json").read_text()
    )
    assert alternate["revision"] == parent["analysis_binding"]["source_snapshot_revision"]
    assert alternate["revision"] != original["revision"]
    if problem == "alternate-archive":
        archive.write_text(json.dumps(alternate))
    else:
        path = root / "experience-generation.json"
        state = json.loads(path.read_text())
        state["request"]["source_snapshot"] = alternate
        if problem == "self-consistent-request":
            state["fixed_inputs_revision"] = _fixed_inputs_revision(state)
            state["request_revision"] = digest(
                {
                    "application_id": task["application_id"],
                    "request": state["request"],
                    "generation_contract": "fixed-writing/v1",
                }
            )
            archive.write_text(json.dumps(alternate))
        path.write_text(json.dumps(state))
    worker = case.server.worker_service
    before = worker.store.load()
    with pytest.raises(PortalDataError) as error:
        case.flow.prepare_worker(task["id"], task["revision"], "CHE", True)
    assert error.value.code == "single_binding_invalid"
    assert worker.store.load() == before


@pytest.mark.parametrize(
    "problem", [None, "alternate-archive", "request-source", "self-consistent-request"]
)
def test_content_writer_preserves_the_public_full_snapshot_choice(
    json_material, monkeypatch, problem
):
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
    if problem is not None:
        path = case.flow.root / "analyses" / task["analysis_id"] / "source-snapshot.json"
        alternate = json.loads(path.read_text())
        if problem == "alternate-archive":
            archive.write_text(json.dumps(alternate))
        else:
            path = root / "experience-generation.json"
            state = json.loads(path.read_text())
            state["request"]["source_snapshot"] = alternate
            if problem == "self-consistent-request":
                state["fixed_inputs_revision"] = _fixed_inputs_revision(state)
                state["request_revision"] = digest(
                    {
                        "application_id": task["application_id"],
                        "request": state["request"],
                        "generation_contract": "fixed-writing/v1",
                    }
                )
                archive.write_text(json.dumps(alternate))
            path.write_text(json.dumps(state))
    worker = case.server.worker_service
    before = worker.store.load()
    if problem is None:
        prepared = case.flow.prepare_worker(task["id"], task["revision"], "CHE", True)
        assert prepared["worker_ref"]["job_id"] == task["application_id"]
        worker.store.check_single(worker.store.load()["jobs"][0], worker.store.load())
    else:
        with pytest.raises(PortalDataError) as error:
            case.flow.prepare_worker(task["id"], task["revision"], "CHE", True)
        assert error.value.code == "single_binding_invalid"
        assert worker.store.load() == before


@pytest.mark.parametrize("json_flow", [{"automatic_resume_author": True}], indirect=True)
@pytest.mark.parametrize(
    "problem", [None, "self-consistent-request", "missing-proof-hash", "conflicting-proof-contract"]
)
def test_default_automatic_author_exports_and_prepares_without_manual_handoff(
    json_material, monkeypatch, problem
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
    if problem in {"missing-proof-hash", "conflicting-proof-contract"}:
        saved = case.flow._load()
        current = case.flow._task(saved, task["id"])
        state = json.loads(
            (case.store.root / task["draft_id"] / "experience-generation.json").read_text()
        )
        proof = {
            "id": task["draft_id"],
            "kind": "experience_handoff",
            "generation_contract": "content-writing/v1",
            "application_id": task["application_id"],
        }
        if problem == "conflicting-proof-contract":
            proof.update(
                generation_contract="fixed-writing/v1",
                fixed_inputs_revision=state["fixed_inputs_revision"],
            )
        row = next(row for row in current["artifacts"] if row["stage"] == "resume")
        current["artifacts"].append(row | {"adopted": False, "result": proof})
        case.flow._save(saved)
        task = current
    elif problem is not None:
        root = case.store.root / task["draft_id"]
        path = root / "experience-generation.json"
        state = json.loads(path.read_text())
        alternate = json.loads(
            (
                case.flow.root / "analyses" / task["analysis_id"] / "binding-source-snapshot.json"
            ).read_text()
        )
        assert alternate["revision"] != state["request"]["source_snapshot"]["revision"]
        state["request"]["source_snapshot"] = alternate
        state["fixed_inputs_revision"] = _fixed_inputs_revision(state)
        state["request_revision"] = digest(
            {
                "application_id": task["application_id"],
                "request": state["request"],
                "generation_contract": "fixed-writing/v1",
            }
        )
        path.write_text(json.dumps(state))
        (root / "source-snapshot.json").write_text(json.dumps(alternate))
    worker = case.server.worker_service
    before = worker.store.load()
    if problem is None:
        prepared = case.flow.prepare_worker(task["id"], task["revision"], "CHE", True)
        assert prepared["worker_ref"]["job_id"] == task["application_id"]
        state = worker.store.load()
        worker.store.check_single(state["jobs"][0], state)
    else:
        with pytest.raises(PortalDataError) as error:
            case.flow.prepare_worker(task["id"], task["revision"], "CHE", True)
        assert error.value.code == "single_binding_invalid"
        assert worker.store.load() == before
