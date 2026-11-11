"""Automatic full materials share immutable generation/export without human receipts."""

import json
import subprocess

import pytest
from test_application_resume import task_resume as task_resume
from test_full_latex_generation import full_latex as full_latex
from test_full_latex_generation import generate

from career_evidence_graph.application_flow_store import read_flow_state
from career_evidence_graph.application_input_binding import configuration_revision
from career_evidence_graph.career_portal_data import PortalDataError


class SyntheticCompiler:
    def __init__(self):
        self.calls = []

    def configuration(self):
        return {"compiler": "synthetic"}

    def compile(self, binding):
        self.calls.append(binding)
        return {
            "build": {"main": binding["main"], "exit": 0, "pdf_updated": True},
            "pdf": b"%PDF-1.4\n1 0 obj<</Type /Page>>endobj\n%%EOF\n",
        }


def test_automatic_full_export_keeps_tex_build_without_fabricating_user_review(full_latex):
    store, _, _, _, calls, _, _, inputs = full_latex
    draft = generate(full_latex)
    compiler = SyntheticCompiler()
    store.prism_client = compiler
    store.pdf_inspector = lambda raw: 1
    result = store.export_for_draft(
        draft["id"],
        draft["draft_sha256"],
        task_inputs=inputs,
        export_id="1" * 32,
        prism=draft["source_checkpoint"],
        automatic_materials=True,
    )
    assert result["kind"] == "pdf"
    assert result["automatic_materials"] is True
    assert result["factual_review"] == "pending"
    assert "group_review" not in result
    assert len(compiler.calls) == len(calls) == 1
    assert "Project 6" in result["latex_source"]
    assert store.read_export(result["id"])["pdf_sha256"] == result["pdf_sha256"]
    manifest = json.loads((store.root / result["id"] / "export.json").read_text())
    assert "verified_by" not in json.dumps(manifest)
    assert len(compiler.calls) == 1


def test_unknown_automatic_compile_keeps_attempt_and_never_replays(full_latex):
    store, _, _, _, _, _, _, inputs = full_latex
    draft = generate(full_latex)
    compiler = SyntheticCompiler()
    store.prism_client = compiler

    def unknown(binding):
        compiler.calls.append(binding)
        raise TimeoutError("Synthetic compile response lost")

    compiler.compile = unknown
    with pytest.raises(PortalDataError) as failure:
        store.export_for_draft(
            draft["id"],
            draft["draft_sha256"],
            task_inputs=inputs,
            export_id="2" * 32,
            prism=draft["source_checkpoint"],
            automatic_materials=True,
        )
    assert failure.value.code == "resume_export_needs_recheck"
    for _ in range(2):
        with pytest.raises(PortalDataError) as pending:
            store.reconcile_export(
                "2" * 32,
                draft_id=draft["id"],
                draft_sha256=draft["draft_sha256"],
                task_inputs=inputs,
            )
        assert pending.value.code == "resume_export_needs_recheck"
    with pytest.raises(PortalDataError):
        store.export_for_draft(
            draft["id"],
            draft["draft_sha256"],
            task_inputs=inputs,
            export_id="2" * 32,
            prism=draft["source_checkpoint"],
            automatic_materials=True,
        )
    assert len(compiler.calls) == 1
    assert (store.root / ("2" * 32) / "export-intent.json").exists()
    assert not (store.root / ("2" * 32) / "export.json").exists()


def test_historical_full_export_still_requires_real_group_receipts(full_latex):
    store, _, _, _, _, _, _, inputs = full_latex
    draft = generate(full_latex)
    compiler = SyntheticCompiler()
    store.prism_client = compiler
    with pytest.raises(PortalDataError):
        store.export_for_draft(
            draft["id"],
            draft["draft_sha256"],
            task_inputs=inputs,
            export_id="3" * 32,
            prism=draft["source_checkpoint"],
        )
    assert not compiler.calls


def test_default_flow_runs_full_generation_export_and_system_binding(full_latex, tmp_path):
    from test_application_flow import wait_for

    from career_evidence_graph.application_flow import ApplicationFlowService
    from career_evidence_graph.application_prism import source_snapshot

    store, job, sources, analysis, calls, project, _, inputs = full_latex
    store.prism_client = SyntheticCompiler()
    store.pdf_inspector = lambda raw: 1

    def generate_task(task):
        return store.generate_for_task(
            job["id"],
            job["revision"],
            source_snapshot=sources,
            analysis=analysis,
            draft_only=True,
            task_inputs=task["inputs"],
            latex_base=task["latex_base"],
        )

    def export_task(task):
        return store.export_for_draft(
            task["draft_id"],
            task["draft_sha256"],
            task_inputs=task["inputs"],
            export_id=task["stages"]["export"]["attempt_id"],
            prism=task["prism"],
            automatic_materials=task.get("automatic_materials", False),
        )

    service = ApplicationFlowService(
        store.applications,
        tmp_path / "flow",
        callbacks={
            "analysis": lambda _: analysis,
            "resume": generate_task,
            "export": export_task,
            "prism_source": source_snapshot,
            "prism_export_configuration": lambda: configuration_revision(
                store.prism_client.configuration()
            ),
            "verify_draft": lambda task: store.draft(task["draft_id"]),
            "verify_materials": lambda task: store.read_export(task["resume_id"]),
        },
    )
    try:
        task = service.create(job["id"], job["revision"], inputs=inputs)
        service.start(task["id"], task["revision"], "analysis")
        task = wait_for(service, task["id"], lambda t: t["status"] == "analysis_ready")
        task = service.prepare_automatic_materials(
            task["id"],
            task["revision"],
            str(project),
            "main.tex",
        )
        service.start(task["id"], task["revision"], "resume")
        task = wait_for(service, task["id"], lambda t: t["status"] in {"draft_ready", "failed"})
        assert task["status"] == "draft_ready", task
        assert task["factual_review"] == "pending"
        service.start(task["id"], task["revision"], "export")
        task = wait_for(
            service,
            task["id"],
            lambda t: t["status"] in {"materials_ready", "failed", "needs_recheck"},
        )
        assert task["status"] == "materials_ready", task
        assert task["material_binding"]["actor"] == "system"
        assert task["material_binding"]["human_reviewed"] is False
        assert not task.get("material_reviews") and not task.get("group_reviews")
        assert len(store.prism_client.calls) == len(calls) == 1
    finally:
        service.close()
    reopened = ApplicationFlowService(
        store.applications,
        tmp_path / "flow",
        callbacks=service.callbacks,
    )
    try:
        retained = reopened.snapshot(task["id"])["active_task"]
        assert retained["status"] == "materials_ready"
        assert retained["resume_sha256"] == task["resume_sha256"]
        assert retained["material_binding"]["human_reviewed"] is False
        assert len(store.prism_client.calls) == len(calls) == 1
    finally:
        reopened.close()


def test_default_portal_uses_shared_full_material_callbacks_and_reuses_retained_base(
    full_latex, tmp_path
):
    from test_application_flow import wait_for
    from test_career_portal_http import _running_portal

    from career_evidence_graph.application_flow import job_input_revision

    store, job, _, analysis, calls, project, _, _ = full_latex
    store.prism_client = SyntheticCompiler()
    store.pdf_inspector = lambda raw: 1
    subprocess.run(["git", "init", "--quiet", str(store.catalog.root)], check=True)
    with _running_portal(
        store.applications.root,
        store.catalog.root,
        flow_root=tmp_path / "portal-flow",
        flow_analyzer=lambda application, _sources, directory: (
            analysis
            | {
                "id": directory.name,
                "application_id": application["id"],
                "application_revision": application["revision"],
                "jd_revision": job_input_revision(application),
            }
        ),
        flow_resume_factory=lambda *args: store,
    ) as active:
        service = active.server.application_flow_service
        task = service.create(job["id"], job["revision"])
        # This fake pre-P02 analysis replays a persisted historical task.
        with service.applications.write_lock():
            state = service._load()
            service._task(state, task["id"]).pop("material_contract", None)
            service._save(state)
        task = service.snapshot(task["id"])["active_task"]
        service.start(task["id"], task["revision"], "analysis")
        task = wait_for(service, task["id"], lambda t: t["status"] == "analysis_ready")
        task = service.prepare_automatic_materials(
            task["id"], task["revision"], str(project), "main.tex"
        )
        service.start(task["id"], task["revision"], "resume")
        task = wait_for(service, task["id"], lambda t: t["status"] in {"draft_ready", "failed"})
        assert task["status"] == "draft_ready", task
        service.start(task["id"], task["revision"], "export")
        task = wait_for(
            service,
            task["id"],
            lambda t: t["status"] in {"materials_ready", "export_failed", "needs_recheck"},
        )
        assert task["status"] == "materials_ready", task
        assert len(store.prism_client.calls) == len(calls) == 1
        assert active.request("GET", f"/api/flow/resumes/{task['resume_id']}/pdf")[0] == 200
        other = store.applications.create_application(
            {
                "company": "Second synthetic employer",
                "role_title": "Engineer",
                "job_description": "Operate service systems.",
            }
        )
        analysis["application_id"] = other["id"]
        other_task = service.create(other["id"], other["revision"])
        with service.applications.write_lock():
            state = service._load()
            service._task(state, other_task["id"]).pop("material_contract", None)
            service._save(state)
        other_task = service.snapshot(other_task["id"])["active_task"]
        service.start(other_task["id"], other_task["revision"], "analysis")
        other_task = wait_for(service, other_task["id"], lambda t: t["status"] == "analysis_ready")
        other_task = service.prepare_automatic_materials(other_task["id"], other_task["revision"])
        assert other_task["latex_base"]["project_root"] == task["source_checkpoint"]["project_root"]
        assert len(store.prism_client.calls) == len(calls) == 1


def test_automatic_compile_cannot_adopt_a_source_changed_during_build(full_latex):
    from pathlib import Path

    store, _, _, _, _, _, _, inputs = full_latex
    draft = generate(full_latex)
    compiler = SyntheticCompiler()
    compile_source = compiler.compile

    def edit_during_build(binding):
        result = compile_source(binding)
        path = Path(binding["project_root"]) / binding["main"]
        path.write_text(path.read_text() + "% User edit during compilation\n")
        return result

    compiler.compile = edit_during_build
    store.prism_client = compiler
    store.pdf_inspector = lambda raw: 1
    with pytest.raises(PortalDataError) as failure:
        store.export_for_draft(
            draft["id"],
            draft["draft_sha256"],
            task_inputs=inputs,
            export_id="4" * 32,
            prism=draft["source_checkpoint"],
            automatic_materials=True,
        )
    assert failure.value.code == "resume_export_needs_recheck"
    assert len(compiler.calls) == 1
    assert not (store.root / ("4" * 32) / "export.json").exists()


def test_automatic_materials_missing_base_stops_without_short_summary_fallback(
    full_latex, tmp_path
):
    from test_application_flow import wait_for

    from career_evidence_graph.application_flow import ApplicationFlowService

    store, job, _, analysis, calls, _, _, inputs = full_latex
    service = ApplicationFlowService(
        store.applications,
        tmp_path / "missing-base-flow",
        callbacks={"analysis": lambda _: analysis},
    )
    try:
        task = service.create(job["id"], job["revision"], inputs=inputs)
        service.start(task["id"], task["revision"], "analysis")
        task = wait_for(service, task["id"], lambda row: row["status"] == "analysis_ready")
        with pytest.raises(PortalDataError) as missing:
            service.prepare_automatic_materials(task["id"], task["revision"])
        assert missing.value.code == "flow_latex_base_required"
        current = service.snapshot(task["id"])["active_task"]
        assert current["stages"]["resume"]["status"] == "pending"
        assert current["revision"] == task["revision"]
        assert not current.get("automatic_materials")
        assert not calls
    finally:
        service.close()


def test_automatic_full_export_trusts_successful_tex_build_without_pdf_review(full_latex):
    store, _, _, _, _, _, _, inputs = full_latex
    draft = generate(full_latex)
    compiler = SyntheticCompiler()
    store.prism_client = compiler

    def unnecessary_pdf_review(_raw):
        pytest.fail("A successful TeX build must not require a separate PDF review")

    store.pdf_inspector = unnecessary_pdf_review
    result = store.export_for_draft(
        draft["id"],
        draft["draft_sha256"],
        task_inputs=inputs,
        export_id="5" * 32,
        prism=draft["source_checkpoint"],
        automatic_materials=True,
    )
    assert result["kind"] == "pdf" and result["automatic_materials"] is True
    assert result["factual_review"] == "pending"
    assert store.read_export(result["id"])["pdf_sha256"] == result["pdf_sha256"]
    assert len(compiler.calls) == 1
    manifest = json.loads((store.root / result["id"] / "export.json").read_text())
    assert "verified_by" not in manifest and "group_review" not in manifest


def test_pipeline_real_full_materials_reaches_fake_worker_manual_submit_boundary(
    full_latex, tmp_path
):
    """Only intake and browser transport are doubles; shared material stages run normally."""
    import time

    from test_application_pipeline import Intake, Worker

    from career_evidence_graph.application_flow import ApplicationFlowService, job_input_revision
    from career_evidence_graph.application_pipeline import ApplicationPipeline
    from career_evidence_graph.application_prism import source_snapshot

    store, original, sources, analysis, calls, project, _, inputs = full_latex
    job = store.applications.update_application(
        original["id"],
        {"url": "https://example.com/synthetic/job", "location": "Zurich, Switzerland"},
        original["revision"],
    )
    analysis.update(application_revision=job["revision"], jd_revision=job_input_revision(job))
    analysis["requirements"][0].update(
        text="Operate Python services",
        importance="required",
        judgment="supported",
        hard_condition=False,
    )
    worker = Worker()
    compiler = SyntheticCompiler()
    store.prism_client = compiler
    store.pdf_inspector = lambda raw: 1
    prepared = []

    def generate_task(task):
        return store.generate_for_task(
            job["id"],
            job["revision"],
            source_snapshot=sources,
            analysis=analysis,
            draft_only=True,
            task_inputs=task["inputs"],
            latex_base=task["latex_base"],
        )

    def export_task(task):
        return store.export_for_draft(
            task["draft_id"],
            task["draft_sha256"],
            task_inputs=task["inputs"],
            export_id=task["stages"]["export"]["attempt_id"],
            prism=task["prism"],
            automatic_materials=task["automatic_materials"],
        )

    def prepare_transport(task, country):
        assert country == "CHE"
        prepared.append(task)
        worker.state.update(
            batch_id="synthetic-batch",
            jobs=[
                {
                    "application_id": job["id"],
                    "status": "queued",
                    "page_open": False,
                    "intent": None,
                    "handed_off": False,
                }
            ],
        )
        return {"batch_id": "synthetic-batch", "job_id": job["id"], "status": "queued"}

    def control_transport(task, operation, payload):
        assert operation in {"resume", "heartbeat", "pause"}
        worker.state.update(controller=payload["controller"])
        if operation == "resume":
            worker.state["control"] = "running"
            worker.state["jobs"][0]["status"] = "filling"
        elif operation == "pause":
            worker.state["control"] = "paused"
        return {
            "batch_id": worker.state["batch_id"],
            "job_id": job["id"],
            "status": worker.state["jobs"][0]["status"],
        }

    service = ApplicationFlowService(
        store.applications,
        tmp_path / "pipeline-flow",
        input_provider=lambda identifier: {
            "application_revision": store.applications.get_application(identifier)["revision"],
            "inputs": inputs,
        },
        callbacks={
            "analysis": lambda _: analysis,
            "resume": generate_task,
            "export": export_task,
            "automatic_latex_base": lambda _: source_snapshot(project, "main.tex"),
            "prism_source": source_snapshot,
            "prism_export_configuration": lambda: configuration_revision(compiler.configuration()),
            "verify_draft": lambda task: store.draft(task["draft_id"]),
            "verify_materials": lambda task: store.read_export(task["resume_id"]),
            "prepare_worker": prepare_transport,
            "control_worker": control_transport,
        },
    )
    intake = Intake(tmp_path / "pipeline-intake", [job])
    pipeline = ApplicationPipeline(service, intake, worker, interval=100)
    try:
        pipeline.start(request_id="synthetic-full-automatic")
        for _ in range(200):
            pipeline._tick()
            state = pipeline.snapshot()
            if state["status"] in {"filling", "needs_input", "needs_recheck", "blocked"}:
                break
            time.sleep(0.01)
        assert state["status"] == "filling", state
        task = service.snapshot(state["active_task_id"])["active_task"]
        assert task["automatic_materials"] is True
        assert task["material_binding"]["actor"] == "system"
        assert task["material_binding"]["human_reviewed"] is False
        assert task["send_approval"]["verified_by"] == "workflow_policy"
        assert len(prepared) == len(calls) == len(compiler.calls) == len(intake.calls) == 1
        assert "Project 6" in store.read_export(task["resume_id"])["latex_source"]
        worker.state["jobs"][0].update(status="ready_for_review", page_open=True)
        pipeline._tick()
        state = pipeline.snapshot()
        assert state["status"] == "ready_for_review"
        assert state["control"] == worker.state["control"] == "paused"
        assert worker.state["jobs"][0]["page_open"] is True
        assert len(calls) == len(compiler.calls) == 1
    finally:
        pipeline.close()
        service.close()


@pytest.mark.parametrize(
    "mutation",
    [
        None,
        "export-source",
        "analysis-policy",
        "export-adoption",
        "draft-adoption",
        "unknown-export",
        "material-binding",
        "legacy-adoption",
        "legacy-adoption-pdf",
    ],
)
def test_full_automatic_materials_reach_real_worker_binding(
    full_latex, tmp_path, monkeypatch, mutation
):
    from test_application_flow import wait_for
    from test_resume_export import PDF_SAMPLE

    from career_evidence_graph import application_match
    from career_evidence_graph.application_flow import job_input_revision
    from career_evidence_graph.career_portal import create_server

    store, original, _, analysis, calls, project, _, _ = full_latex
    job = store.applications.update_application(
        original["id"],
        {
            "url": "https://jobs.lever.co/synthetic/12345678-1234-1234-1234-123456789012",
            "location": "Zurich, Switzerland",
        },
        original["revision"],
    )
    root = tmp_path / "actual-flow"
    store.root = root / "resumes"
    store.root.mkdir(parents=True)
    store.prism_client = SyntheticCompiler()
    original_compile = store.prism_client.compile
    store.prism_client.compile = lambda binding: (
        original_compile(binding) | {"pdf": PDF_SAMPLE.read_bytes()}
    )
    store.pdf_inspector = lambda raw: 1
    subprocess.run(["git", "init", "--quiet", str(store.catalog.root)], check=True)

    def fake_analysis(application, sources, directory, *, information_library=None, **kwargs):
        from career_evidence_graph.application_information import information_context

        directory.mkdir(parents=True)
        result = analysis | {
            "id": directory.name,
            "application_id": application["id"],
            "application_revision": application["revision"],
            "jd_revision": job_input_revision(application),
            "source_snapshot_revision": sources["revision"],
            "information_context_revision": information_context(
                application, information_library or {"status": "unconfigured", "records": []}
            )["revision"],
        }
        (directory / "analysis.json").write_text(json.dumps(result))
        from test_application_match import persist_analysis_inputs

        persist_analysis_inputs(directory, application, sources)
        return result

    monkeypatch.setattr(application_match, "analyze_job", fake_analysis)
    with create_server(
        store.applications.root,
        store.catalog.root,
        flow_root=root,
        worker_root=tmp_path / "worker",
        worker_live=True,
        flow_resume_factory=lambda *args: store,
    ) as server:
        flow, worker = server.application_flow_service, server.worker_service
        task = flow.create(job["id"], job["revision"])
        # This recorded pre-P02 material scenario represents a saved legacy task.
        with flow.applications.write_lock():
            state = flow._load()
            flow._task(state, task["id"]).pop("material_contract", None)
            flow._save(state)
        task = flow.snapshot(task["id"])["active_task"]
        flow.start(task["id"], task["revision"], "analysis")
        task = wait_for(flow, task["id"], lambda row: row["status"] in {"analysis_ready", "failed"})
        assert task["status"] == "analysis_ready", task
        task = flow.prepare_automatic_materials(
            task["id"], task["revision"], str(project), "main.tex"
        )
        flow.start(task["id"], task["revision"], "resume")
        task = wait_for(flow, task["id"], lambda row: row["status"] in {"draft_ready", "failed"})
        assert task["status"] == "draft_ready", task
        flow.start(task["id"], task["revision"], "export")
        task = wait_for(
            flow,
            task["id"],
            lambda row: row["status"] in {"materials_ready", "export_failed", "needs_recheck"},
        )
        assert task["status"] == "materials_ready", task
        prepared = flow.prepare_worker(task["id"], task["revision"], "CHE", True)
        assert prepared["status"] == "queued"
        current = worker.store.load()
        assert worker.process is None
        if mutation is not None and mutation.startswith("legacy-adoption"):
            # 2026-11-03: an older adoption recorded `used_source_ids` as [] and a
            # pre-cfg2 draft configuration revision; both are re-derived on read.
            saved_flow = read_flow_state(flow.path.parent)
            saved_task = saved_flow["tasks"][0]
            for row in saved_task["artifacts"]:
                if row["stage"] in {"resume", "export"} and row.get("adopted") is True:
                    row["result"]["used_source_ids"] = []
                    if row["stage"] == "resume":
                        row["result"]["resume_configuration_revision"] = "b" * 64
            from career_evidence_graph.application_worker import digest

            saved_task["revision"] = digest(
                {k: v for k, v in saved_task.items() if k != "revision"}
            )
            flow.path.write_text(json.dumps(saved_flow))
            if mutation == "legacy-adoption":
                mutation = None
            else:
                (root / "resumes" / task["resume_id"] / "resume.pdf").write_bytes(
                    PDF_SAMPLE.read_bytes() + b"\n% changed"
                )
        if mutation is not None:
            if mutation == "analysis-policy":
                path = root / "analyses" / task["analysis_id"] / "analysis.json"
                record = json.loads(path.read_text())
                record["policy_version"] = "changed"
                path.write_text(json.dumps(record))
            elif mutation == "export-source":
                (root / "resumes" / task["resume_id"] / "resume.tex").write_text("Changed source")
            elif mutation == "unknown-export":
                (root / "resumes" / task["resume_id"] / "export.json").unlink()
            else:
                saved_flow = read_flow_state(flow.path.parent)
                saved_task = saved_flow["tasks"][0]
                if mutation == "material-binding":
                    saved_task["material_binding"]["human_reviewed"] = True
                else:
                    stage = "export" if mutation == "export-adoption" else "resume"
                    next(row for row in saved_task["artifacts"] if row["stage"] == stage)[
                        "adopted"
                    ] = False
                from career_evidence_graph.application_worker import digest

                saved_task["revision"] = digest(
                    {k: v for k, v in saved_task.items() if k != "revision"}
                )
                flow.path.write_text(json.dumps(saved_flow))
            before = {str(p): p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}
            with pytest.raises(PortalDataError):
                worker.store.check_single(current["jobs"][0], current)
            assert {str(p): p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()} == before
            assert len(calls) == len(store.prism_client.calls) == 1
            return
        try:
            worker.store.check_single(current["jobs"][0], current)
        except PortalDataError as error:
            cause = error.__cause__
            raise AssertionError(
                {
                    "prepared": prepared["status"],
                    "child_check": error.code,
                    "cause": str(cause),
                    "draft_id": prepared["draft_id"],
                    "resume_id": prepared["resume_id"],
                    "artifacts": [
                        (row["stage"], row["result"].get("id"), row["result"].get("kind"))
                        for row in prepared["artifacts"]
                    ],
                }
            ) from None
        assert len(calls) == len(store.prism_client.calls) == 1


@pytest.mark.parametrize(
    "mutation", ["analysis-policy", "analysis-binding", "resume-source", "resume-adoption", "pdf"]
)
def test_shared_material_lineage_rejects_changed_legacy_evidence_without_writing(
    tmp_path, mutation
):
    from test_installed_write_admission import bytes_under, prepared_inputs

    from career_evidence_graph.application_single_binding import verify_material_lineage

    applications, root, career, task = prepared_inputs(tmp_path)
    verify_material_lineage(applications, root, career, task)
    if mutation.startswith("analysis"):
        path = root / "analyses" / task["analysis_id"] / "analysis.json"
        record = json.loads(path.read_text())
        record["policy_version" if mutation == "analysis-policy" else "jd_revision"] = "changed"
        path.write_text(json.dumps(record))
    elif mutation == "resume-source":
        path = root / "resumes" / task["resume_id"] / "sources.json"
        record = json.loads(path.read_text())
        record["analysis_binding"]["policy_version"] = "changed"
        path.write_text(json.dumps(record))
    elif mutation == "resume-adoption":
        task["artifacts"][-1]["adopted"] = False
    else:
        (root / "resumes" / task["resume_id"] / "resume.pdf").write_bytes(b"%PDF changed")
    before = bytes_under(tmp_path)
    with pytest.raises(PortalDataError) as changed:
        verify_material_lineage(applications, root, career, task)
    assert changed.value.code == "single_binding_invalid"
    assert bytes_under(tmp_path) == before


def test_material_lineage_can_check_first_legacy_pdf_before_system_binding(tmp_path):
    from test_installed_write_admission import bytes_under, prepared_inputs

    from career_evidence_graph.application_single_binding import verify_material_lineage

    applications, root, career, task = prepared_inputs(tmp_path)
    task.update(status="resume_ready", materials_confirmed=False)
    before = bytes_under(tmp_path)
    saved = verify_material_lineage(applications, root, career, task)
    assert saved["pdf_sha256"] == task["resume_sha256"]
    assert task["materials_confirmed"] is False
    assert bytes_under(tmp_path) == before
