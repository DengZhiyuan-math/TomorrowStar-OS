"""Complete LaTeX generation preserves the base and stops before factual review."""

import threading

import pytest
from test_application_flow import application as application
from test_application_flow import wait_for
from test_job_explanations import requirement

from career_evidence_graph.application_flow import ApplicationFlowService
from career_evidence_graph.application_prism import source_snapshot
from career_evidence_graph.career_portal_data import PortalDataError


@pytest.fixture
def latex_flow(application, tmp_path):
    applications, job = application
    project = tmp_path / "base"
    project.mkdir()
    (project / "main.tex").write_text(r"\documentclass{article}\begin{document}Fact\end{document}")
    service = ApplicationFlowService(
        applications,
        tmp_path / "flow",
        preparation_only=True,
        callbacks={
            "analysis": lambda _: {"id": "analysis", "requirements": [requirement()]},
            "prism_source": source_snapshot,
            "export": lambda _: pytest.fail("No PDF export in generation slice"),
        },
    )
    task = service.create(job["id"], job["revision"])
    # Replay a saved task under the pre-JSON full-TeX writing contract.
    with service.applications.write_lock():
        saved = service._load()
        service._task(saved, task["id"]).pop("material_contract", None)
        service._save(saved)
    task = service.snapshot(task["id"])["active_task"]
    service.start(task["id"], task["revision"], "analysis")
    task = wait_for(service, task["id"], lambda row: row["status"] == "analysis_ready")
    try:
        yield service, task, project
    finally:
        service.close()


def bind(service, task, project):
    return service.request(
        "bind-latex-base",
        {
            "task_id": task["id"],
            "task_revision": task["revision"],
            "project_root": str(project),
            "main": "main.tex",
        },
    )


def candidate(task):
    return {
        "id": "d",
        "kind": "draft",
        "origin": "generated_latex",
        "factual_review": "pending",
        "draft_sha256": "a" * 64,
        "base_checkpoint": task["latex_base"],
        "source_checkpoint": {
            "project_root": "/synthetic/generated",
            "main": "main.tex",
            "files": {"main.tex": "b" * 64},
            "source_revision": "c" * 64,
            "archive_sha256": "d" * 64,
        },
        "review_groups": [],
        "omitted_groups": [],
        "verification_queue": [],
        "task_inputs": task["inputs"],
    }


def test_bind_preserves_analysis_rebind_invalidates_only_downstream(latex_flow):
    service, task, project = latex_flow
    analysis = task["analysis_id"]
    task = bind(service, task, project)
    assert task["latex_base"] == source_snapshot(project, "main.tex")
    assert task["analysis_id"] == analysis and task["status"] == "analysis_ready"
    assert task["input_epoch"] == 1 and not task["materials_confirmed"]
    unchanged = bind(service, task, project)
    assert unchanged["revision"] == task["revision"]
    old = task["latex_base"]
    (project / "main.tex").write_text("Updated full LaTeX")
    task = bind(service, task, project)
    assert task["latex_base_history"] == [old]
    assert task["input_epoch"] == 2 and task["analysis_id"] == analysis
    assert task["stages"]["resume"]["status"] == "pending"


def test_generated_latex_has_no_generic_fact_pdf_or_material_shortcut(latex_flow):
    service, task, project = latex_flow
    service.callbacks["resume"] = candidate
    task = bind(service, task, project)
    service.start(task["id"], task["revision"], "resume")
    task = wait_for(service, task["id"], lambda row: row["status"] in {"draft_ready", "failed"})
    assert task["status"] == "draft_ready" and task["origin"] == "generated_latex"
    assert task["factual_review"] == "pending" and task["source_checkpoint"]
    assert task["resume_id"] is None and task["materials_confirmed"] is False
    for action, extra in (
        ("review-draft", {"draft_id": "d", "draft_sha256": "a" * 64}),
        ("export-pdf", {"draft_id": "d", "draft_sha256": "a" * 64}),
        ("confirm-materials", {"resume_id": "d", "resume_sha256": "a" * 64}),
    ):
        with pytest.raises(PortalDataError) as error:
            service.request(
                action, {"task_id": task["id"], "task_revision": task["revision"], **extra}
            )
        assert error.value.code == "flow_factual_review_required"


def test_changed_base_blocks_generation_before_callback(latex_flow):
    service, task, project = latex_flow
    service.callbacks["resume"] = lambda _: pytest.fail("Changed base must fail before generation")
    task = bind(service, task, project)
    (project / "main.tex").write_text("Changed after binding")
    with pytest.raises(PortalDataError) as error:
        service.start(task["id"], task["revision"], "resume")
    assert error.value.code == "flow_latex_base_changed"


def test_late_generation_after_base_edit_is_retained_but_not_adopted(latex_flow):
    service, task, project = latex_flow
    entered, release = threading.Event(), threading.Event()

    def generate(request):
        entered.set()
        assert release.wait(2)
        return candidate(request)

    service.callbacks["resume"] = generate
    task = bind(service, task, project)
    service.start(task["id"], task["revision"], "resume")
    try:
        assert entered.wait(2)
        (project / "main.tex").write_text("Changed during generation")
        release.set()
        task = wait_for(service, task["id"], lambda row: row["status"] == "failed")
        assert task["stages"]["resume"]["error_code"] == "flow_latex_base_changed"
        assert task["artifacts"][-1]["adopted"] is False
        assert task.get("draft_id") is None
    finally:
        release.set()


@pytest.mark.parametrize("mutation", ["cancelled", "worker", "unknown", "busy", "existing_latex"])
def test_rebinding_cannot_erase_an_active_or_unknown_attempt(latex_flow, mutation):
    service, task, project = latex_flow
    with service.applications.write_lock():
        state, stored = service._checked(task["id"], task["revision"])
        if mutation == "cancelled":
            stored["status"] = "cancelled"
        elif mutation == "worker":
            stored["worker_ref"] = {"job_id": "bound", "status": "needs_input"}
        elif mutation == "existing_latex":
            stored["origin"] = "existing_latex"
        else:
            stored["stages"]["export"] = {
                "status": "needs_recheck" if mutation == "unknown" else "running"
            }
        service._save(state)
    task = service.snapshot(task["id"])["active_task"]
    with pytest.raises(PortalDataError):
        bind(service, task, project)
    assert "latex_base" not in service.snapshot(task["id"])["active_task"]
