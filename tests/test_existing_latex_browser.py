"""Existing LaTeX technical exports retain factual review and historical versions."""

import pytest
from test_application_prism import compiling_editor
from test_career_portal_http import portal as portal
from test_job_explanation_browser import explanation_portal, reveal_control
from test_portal_workflow_browser import browser_page as browser_page

from career_evidence_graph.career_portal_data import ApplicationStore

pytestmark = pytest.mark.worker_browser


def test_existing_latex_import_export_receipt_and_changed_source_keep_history(
    portal, tmp_path, browser_page, monkeypatch
):
    from playwright.sync_api import expect

    project = tmp_path / "existing-latex"
    project.mkdir()
    source = project / "main.tex"
    source.write_text(r"\documentclass{article}\begin{document}Synthetic CV\end{document}")
    job = ApplicationStore(portal.applications).create_application(
        {
            "company": "Synthetic Existing",
            "role_title": "Engineer",
            "job_description": "Build Python services.",
        }
    )
    page = browser_page
    with (
        compiling_editor(project, monkeypatch) as requests,
        explanation_portal(portal, tmp_path) as (instance, work),
    ):
        page.goto(instance.origin + "/#flow")

        def import_source():
            form = page.locator(f"#flow-import-latex-{job['id']}")
            reveal_control(page, form)
            if form.get_attribute("open") is None:
                form.locator("summary").click()
            form.get_by_label("已有简历 LaTeX 项目目录").fill(str(project))
            form.get_by_label("已有简历 LaTeX 主文件").fill("main.tex")
            form.get_by_role("button", name="接入此 LaTeX 新版本").click()
            reveal_control(page, "#flow-draft")
            expect(page.locator("#flow-draft")).to_contain_text("事实审核待完成")

        import_source()
        for selector in (
            "#flow-start-analysis",
            "#flow-start-resume",
            "#flow-review-draft",
            "#flow-regenerate-resume",
            "#flow-bind-prism",
            "#flow-refresh-prism",
            "#flow-confirm-materials",
            "#flow-reviewed-pdf",
            "#flow-worker",
        ):
            expect(page.locator(selector)).to_have_count(0)
        expect(page.locator("#flow-export-pdf")).to_be_disabled()
        page.locator("#flow-authorize-latex-export").click()
        expect(page.locator("#flow-export-pdf")).to_be_enabled()
        page.locator("#flow-export-pdf").click()
        expect(page.locator("#flow-pdf-link")).to_be_visible()
        page.locator("#flow-read-export-receipt").click()
        expect(page.locator("#flow-export-receipt")).to_contain_text("导出回执已核验")
        first = instance.server.application_flow_service.snapshot()["active_task"]
        receipt = page.locator("#flow-export-receipt")
        expect(receipt).to_contain_text(first["resume_id"])
        expect(receipt).to_contain_text(first["prism"]["source_revision"])
        expect(receipt).to_contain_text(first["resume_sha256"])
        expect(page.locator("#flow-confirm-materials")).to_have_count(0)
        expect(page.locator("#flow-reviewed-pdf")).to_have_count(0)
        assert first["draft_review"] is None and not first["materials_confirmed"]
        assert len([request for request in requests if request[0] == "POST"]) == 1

        source.write_text(source.read_text() + "\n% Synthetic saved successor\n")
        page.locator("#flow-observe").click()
        expect(page.locator("#flow-prism")).to_contain_text("接入新版本")
        expect(page.locator("#flow-export-pdf")).to_be_disabled()
        import_source()
        expect(page.locator("#flow-task-list button")).to_have_count(2)
        latest = instance.server.application_flow_service.snapshot()["active_task"]
        assert latest["id"] != first["id"] and latest["draft_id"] != first["draft_id"]
        assert latest["prism"]["source_revision"] != first["prism"]["source_revision"]
        historical = instance.server.application_flow_service.snapshot()["tasks"][0]
        assert historical == first
        reveal_control(page, page.locator("#flow-task-list button").first)
        page.locator("#flow-task-list button").last.click()
        expect(page.locator("#flow-pdf-link")).to_have_attribute(
            "href", f"/api/flow/resumes/{first['resume_id']}/pdf"
        )
        assert not work["calls"] and not work["exports"]
        assert len([request for request in requests if request[0] == "POST"]) == 1
