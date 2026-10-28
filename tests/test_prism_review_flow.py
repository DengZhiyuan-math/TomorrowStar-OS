"""A real LaTeX source revision is reviewed separately from its generated PDF."""

import pytest
from test_application_flow import application as application
from test_application_flow import wait_for
from test_pdf_export_flow import review
from test_pdf_export_flow import reviewed_draft as reviewed_draft

from career_evidence_graph.application_prism import source_snapshot
from career_evidence_graph.career_portal_data import PortalDataError


def test_binding_and_refresh_require_review_of_the_exact_changed_latex_source(
    reviewed_draft, tmp_path
):
    service, task, _ = reviewed_draft
    project = tmp_path / "dedicated latex"
    project.mkdir()
    main = project / "main.tex"
    main.write_text("Synthetic source v1")
    service.callbacks["prism_source"] = source_snapshot
    task = review(service, task)
    original_review = task["draft_review"]
    task = service.request(
        "bind-prism",
        {
            "task_id": task["id"],
            "task_revision": task["revision"],
            "project_root": str(project),
            "main": "main.tex",
        },
    )
    assert (
        task["prism"]["source_revision"] == source_snapshot(project, "main.tex")["source_revision"]
    )
    assert task["draft_review"] is None and original_review in task["draft_reviews"]
    task = review(service, task)
    assert task["draft_review"]["prism_source_revision"] == task["prism"]["source_revision"]
    main.write_text("Synthetic source v2")
    with pytest.raises(PortalDataError) as error:
        service.export_pdf(task["id"], task["revision"], task["draft_id"], task["draft_sha256"])
    assert error.value.code == "prism_source_changed"
    previous = task["draft_review"]
    task = service.request(
        "refresh-prism", {"task_id": task["id"], "task_revision": task["revision"]}
    )
    assert task["draft_review"] is None and previous in task["draft_reviews"]
    assert task["resume_id"] is None and task["materials_confirmed"] is False
    assert task["prism_history"]


def test_unchanged_refresh_keeps_review_and_source_edits_cannot_retire_unknown_compile(
    reviewed_draft, tmp_path
):
    service, task, _ = reviewed_draft
    project = tmp_path / "latex"
    project.mkdir()
    main = project / "main.tex"
    main.write_text("Synthetic reviewed source")
    service.callbacks["prism_source"] = source_snapshot
    task = service.bind_prism(task["id"], task["revision"], str(project), "main.tex")
    task = review(service, task)
    unchanged = service.refresh_prism(task["id"], task["revision"])
    assert unchanged["draft_review"] == task["draft_review"]
    assert unchanged["revision"] == task["revision"]

    def uncertain(_):
        raise PortalDataError("resume_export_needs_recheck", "Synthetic uncertain compile", 409)

    service.callbacks["export"] = uncertain
    service.callbacks["prism_export_configuration"] = lambda: "synthetic-prism-config"
    service.export_pdf(task["id"], task["revision"], task["draft_id"], task["draft_sha256"])
    task = wait_for(service, task["id"], lambda row: row["status"] == "needs_recheck")
    attempt = task["stages"]["export"]["attempt_id"]
    main.write_text("Synthetic newer source")
    with pytest.raises(PortalDataError) as pending:
        service.recheck_export(task["id"], task["revision"])
    assert pending.value.code == "prism_source_changed"
    current = service.snapshot(task["id"])["active_task"]
    assert current["status"] == "needs_recheck"
    assert current["stages"]["export"]["status"] == "needs_recheck"
    assert current["stages"]["export"]["attempt_id"] == attempt
    with pytest.raises(PortalDataError) as blocked:
        service.refresh_prism(current["id"], current["revision"])
    assert blocked.value.code == "prism_review_blocked"


def test_missing_prism_receipt_does_not_allow_another_export_or_callback_replay(
    reviewed_draft, tmp_path
):
    service, task, _ = reviewed_draft
    project = tmp_path / "latex"
    project.mkdir()
    (project / "main.tex").write_text("Synthetic reviewed source")
    service.callbacks["prism_source"] = source_snapshot
    task = service.bind_prism(task["id"], task["revision"], str(project), "main.tex")
    task = review(service, task)
    calls = []

    def uncertain(_):
        calls.append("compile")
        raise PortalDataError("resume_export_needs_recheck", "Synthetic disconnected build", 409)

    service.callbacks["export"] = uncertain
    service.callbacks["prism_export_configuration"] = lambda: "synthetic-prism-config"
    service.callbacks["reconcile_export"] = lambda task: {
        "status": "not_complete",
        "id": task["stages"]["export"]["attempt_id"],
    }
    service.export_pdf(task["id"], task["revision"], task["draft_id"], task["draft_sha256"])
    task = wait_for(service, task["id"], lambda row: row["status"] == "needs_recheck")
    with pytest.raises(PortalDataError) as pending:
        service.recheck_export(task["id"], task["revision"])
    assert pending.value.code == "resume_export_needs_recheck"
    current = service.snapshot(task["id"])["active_task"]
    assert current["status"] == "needs_recheck"
    with pytest.raises(PortalDataError):
        service.export_pdf(
            current["id"],
            current["revision"],
            current["draft_id"],
            current["draft_sha256"],
            retry=True,
        )
    assert calls == ["compile"]
