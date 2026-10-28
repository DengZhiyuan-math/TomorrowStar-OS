"""Normal material entry continues a fixed writing handoff without live rescans."""

import subprocess
from copy import deepcopy

import pytest
from test_application_flow import application as application
from test_application_flow import wait_for
from test_application_resume import task_resume as task_resume
from test_experience_handoff_flow import begin, handoff
from test_full_latex_flow import candidate
from test_full_latex_flow import latex_flow as latex_flow
from test_full_latex_generation import full_latex as full_latex
from test_p05_generation import complete
from test_p05_generation import fixed as fixed

from career_evidence_graph import application_experience_latex as generation
from career_evidence_graph.career_portal import create_server


def test_fixed_handoff_rejoins_resume_stage_despite_live_input_and_template_drift(latex_flow):
    service, _, project = latex_flow
    progress = {}
    calls = []

    def generate(task):
        calls.append(task["id"])
        if len(calls) == 1:
            progress.update(
                handoff(task),
                generation_contract="fixed-writing/v1",
                fixed_inputs_revision="fixed-inputs",
            )
            return deepcopy(progress)
        return candidate(task)

    service.callbacks["resume"] = generate
    service.callbacks["experience_generation"] = lambda _: deepcopy(progress)
    task = begin(latex_flow)
    progress["status"] = "adopted"
    service.input_provider = lambda _: {
        "application_revision": service.applications.get_application(task["application_id"])[
            "revision"
        ],
        "inputs": {**task["inputs"], "sources_revision": "changed-live-library"},
    }
    (project / "main.tex").write_text("Changed external template")
    service.request(
        "resume-experience-generation",
        {"task_id": task["id"], "task_revision": task["revision"], "generation_id": progress["id"]},
    )
    result = wait_for(
        service, task["id"], lambda row: row["status"] in {"draft_ready", "failed", "stale"}
    )
    assert result["status"] == "draft_ready", result
    assert result["analysis_id"] == task["analysis_id"]
    assert len(calls) == 2


def test_normal_portal_resume_callback_uses_existing_fixed_handoff_request(
    fixed, tmp_path, monkeypatch
):
    data, state, *_ = fixed
    store, job, _, analysis, _, _, _, inputs = data
    candidate = complete(fixed)
    generation.review_generation(
        store,
        state["id"],
        candidate_sha256=candidate["candidate_sha256"],
        reviewer_id="reviewer",
        passed=True,
        issues=[],
    )
    draft = generation.adopt_generation(store, state["id"])
    subprocess.run(["git", "init", "--quiet", "--template=", str(store.catalog.root)], check=True)
    server = create_server(
        store.applications.root,
        store.catalog.root,
        port=0,
        flow_root=tmp_path / "portal-flow",
        preparation_only=True,
        write_admission_policy="development",
        flow_resume_factory=lambda *_: store,
    )
    try:
        import career_evidence_graph.career_portal as portal

        monkeypatch.setattr(
            portal,
            "career_source_snapshot",
            lambda *a, **k: pytest.fail("Fixed handoff cannot rescan live career sources"),
        )
        monkeypatch.setattr(
            store,
            "_task_current",
            lambda *a, **k: pytest.fail("Fixed handoff cannot recheck live matching inputs"),
        )
        monkeypatch.setattr(
            store,
            "configuration",
            lambda: pytest.fail("Fixed handoff cannot read current model settings"),
        )
        task = {
            "id": "flow-task",
            "application_id": job["id"],
            "analysis_id": analysis["id"],
            "inputs": inputs,
            "experience_handoff": generation.generation_state(store, state["id"]),
            "stages": {"resume": {"status": "pending"}},
            "latex_base": data[5],
            "artifacts": [{"stage": "analysis", "adopted": True, "result": analysis}],
        }
        result = server.application_flow_service.callbacks["resume"](task)
        assert result["id"] == draft["id"]
        assert result["draft_sha256"] == draft["draft_sha256"]
    finally:
        server.server_close()


def test_normal_fixed_analysis_starts_writing_from_saved_snapshot_and_continues(
    fixed, tmp_path, monkeypatch
):
    import json

    from test_application_match import persist_analysis_inputs
    from test_full_latex_flow import bind

    data, _, experiences, plan = fixed
    store, job, sources, original_analysis, _, project, _, _ = data
    subprocess.run(["git", "init", "--quiet", "--template=", str(store.catalog.root)], check=True)
    server = create_server(
        store.applications.root,
        store.catalog.root,
        port=0,
        flow_root=tmp_path / "portal-flow",
        preparation_only=True,
        write_admission_policy="development",
        flow_resume_factory=lambda *_: store,
    )
    service = server.application_flow_service
    analysis = deepcopy(original_analysis) | {"id": "a" * 32}
    try:
        service.callbacks["analysis"] = lambda _: analysis
        task = service.create(job["id"], job["revision"])
        # Restore this fixture under its retained pre-JSON writing contract.
        with service.applications.write_lock():
            saved = service._load()
            service._task(saved, task["id"]).pop("material_contract", None)
            service._save(saved)
        task = service.snapshot(task["id"])["active_task"]
        service.start(task["id"], task["revision"], "analysis")
        task = wait_for(service, task["id"], lambda row: row["status"] == "analysis_ready")
        task = bind(service, task, project)
        directory = service.root / "analyses" / analysis["id"]
        directory.mkdir(parents=True)
        persist_analysis_inputs(directory, job, sources)
        (directory / "analysis.json").write_text(json.dumps(analysis))
        (directory / "binding-source-snapshot.json").write_text(json.dumps(sources))
        service.information_provider = lambda: {}
        service.input_provider = lambda _: pytest.fail(
            "Fixed adopted analysis cannot rescan inputs"
        )
        import career_evidence_graph.career_portal as portal

        monkeypatch.setattr(
            portal,
            "career_source_snapshot",
            lambda *a, **k: pytest.fail("Fixed analysis cannot rescan the career library"),
        )
        monkeypatch.setattr(
            store, "_task_current", lambda *a, **k: pytest.fail("No live JD/source matching check")
        )
        service.start(task["id"], task["revision"], "resume")
        task = wait_for(
            service, task["id"], lambda row: row["status"] in {"needs_input", "failed", "stale"}
        )
        assert task["status"] == "needs_input", task
        handoff = task["experience_handoff"]
        assert handoff["generation_contract"] == "fixed-writing/v1"
        assert handoff["analysis_binding"]["analysis_id"] == analysis["id"]
        assert handoff["fixed_inputs_revision"]
        configured = generation.configure_generation(
            store,
            handoff["id"],
            groups=data[6]["groups"],
            experiences=experiences,
            organization_plan=plan,
        )
        assembled = complete((data, configured, experiences, plan))
        generation.review_generation(
            store,
            handoff["id"],
            candidate_sha256=assembled["candidate_sha256"],
            reviewer_id="reviewer",
            passed=True,
            issues=[],
        )
        adopted = generation.adopt_generation(store, handoff["id"])
        service.request(
            "resume-experience-generation",
            {
                "task_id": task["id"],
                "task_revision": task["revision"],
                "generation_id": handoff["id"],
            },
        )
        # Poll persistence directly: completed PDF freshness projection is P06.
        from time import monotonic, sleep

        deadline = monotonic() + 3
        while monotonic() < deadline:
            with service.applications.write_lock():
                result = deepcopy(service._task(service._load(), task["id"]))
            if result["status"] in {"draft_ready", "failed", "stale"}:
                break
            sleep(0.01)
        assert result["status"] == "draft_ready", result
        assert result["draft_id"] == adopted["id"]
        assert result["draft_sha256"] == adopted["draft_sha256"]
        assert "experience_handoff" not in result
    finally:
        server.server_close()


@pytest.mark.parametrize("field", ["application_id", "analysis_binding", "fixed_inputs_revision"])
def test_fixed_handoff_cannot_bypass_task_or_delivery_identity(latex_flow, field):
    from career_evidence_graph.career_portal_data import PortalDataError

    service, _, _ = latex_flow
    progress = {}

    def generate(task):
        progress.update(
            handoff(task),
            generation_contract="fixed-writing/v1",
            fixed_inputs_revision="fixed-inputs",
        )
        return deepcopy(progress)

    service.callbacks["resume"] = generate
    service.callbacks["experience_generation"] = lambda _: deepcopy(progress)
    task = begin(latex_flow)
    progress["status"] = "adopted"
    progress[field] = (
        {"analysis_id": "another-analysis"} if field == "analysis_binding" else "another-delivery"
    )
    with pytest.raises(PortalDataError, match="固定经历交付"):
        service.request(
            "resume-experience-generation",
            {
                "task_id": task["id"],
                "task_revision": task["revision"],
                "generation_id": progress["id"],
            },
        )


def test_newer_preparation_task_still_blocks_old_fixed_handoff_continuation(latex_flow):
    from career_evidence_graph.career_portal_data import PortalDataError

    service, _, _ = latex_flow
    progress = {}

    def generate(task):
        progress.update(
            handoff(task),
            generation_contract="fixed-writing/v1",
            fixed_inputs_revision="fixed-inputs",
        )
        return deepcopy(progress)

    service.callbacks["resume"] = generate
    service.callbacks["experience_generation"] = lambda _: deepcopy(progress)
    task = begin(latex_flow)
    progress["status"] = "adopted"
    application = service.applications.get_application(task["application_id"])
    service.create(application["id"], application["revision"], force_new=True)
    with pytest.raises(PortalDataError) as error:
        service.request(
            "resume-experience-generation",
            {
                "task_id": task["id"],
                "task_revision": task["revision"],
                "generation_id": progress["id"],
            },
        )
    assert error.value.code == "flow_inputs_stale"


@pytest.mark.parametrize("judgment", ["unknown", "gap"])
def test_fixed_writing_preserves_saved_hard_qualification_block(latex_flow, judgment):
    from career_evidence_graph.career_portal_data import PortalDataError

    service, task, _ = latex_flow
    service.callbacks["resume"] = lambda _: pytest.fail("Blocked fixed writing cannot dispatch")
    with service.applications.write_lock():
        state = service._load()
        current = service._task(state, task["id"])
        analysis = current["artifacts"][0]["result"]
        analysis.update(
            application_id=task["application_id"],
            job_brief={},
            material_packet={},
            inference_result={},
        )
        analysis["requirements"][0].update(hard_condition=True, judgment=judgment)
        service._save(state)
    task = service.snapshot(task["id"])["active_task"]
    with pytest.raises(PortalDataError) as error:
        service.start(task["id"], task["revision"], "resume")
    assert error.value.code == "flow_qualification_required"


def test_fixed_writing_uses_original_delivered_resume_language_requirement(latex_flow):
    from career_evidence_graph.career_portal_data import PortalDataError

    service, task, _ = latex_flow
    service.callbacks["resume"] = lambda _: pytest.fail("Blocked fixed writing cannot dispatch")
    with service.applications.write_lock():
        state = service._load()
        current = service._task(state, task["id"])
        analysis = current["artifacts"][0]["result"]
        analysis.update(
            application_id=task["application_id"],
            job_brief={"job": {"job_description": "Please submit your CV in German."}},
            material_packet={},
            inference_result={},
        )
        service._save(state)
    task = service.snapshot(task["id"])["active_task"]
    with pytest.raises(PortalDataError) as error:
        service.start(task["id"], task["revision"], "resume")
    assert error.value.code == "flow_resume_language_required"
