"""Real LaTeX checkpoint exports retain failures, receipts and per-job versions."""

import pytest
from latex_browser_support import authorized_latex_portal
from test_career_portal_http import portal as portal
from test_job_explanation_browser import reveal_control
from test_portal_workflow_browser import browser_page as browser_page
from test_preparation_entry import snapshot

from career_evidence_graph.career_portal_data import PortalDataError

pytestmark = pytest.mark.worker_browser


def assert_automatic_binding(task):
    from career_evidence_graph.application_flow import digest

    binding = task["material_binding"]
    assert task["materials_confirmed"] and task["status"] == "materials_ready"
    assert binding["actor"] == "system" and binding["human_reviewed"] is False
    assert binding["scope"] == "current_pdf_materials"
    assert binding["resume_id"] == task["resume_id"]
    assert binding["pdf_sha256"] == task["resume_sha256"]
    assert binding["draft_id"] == task["draft_id"]
    assert binding["draft_sha256"] == task["draft_sha256"]
    assert binding["input_revision"] == digest(task["inputs"])
    assert not task.get("material_reviews") and not task["worker_ref"]


def test_export_failure_preserves_authorized_latex_and_only_explicitly_retries_pdf(
    portal, tmp_path, browser_page
):
    from playwright.sync_api import expect

    page = browser_page
    with authorized_latex_portal(portal, tmp_path) as (active, _jobs, tasks, work):
        store = active.server.application_resume_store
        compile_source = store.prism_client.compile
        attempts = []

        def fail_once(binding):
            attempts.append(binding)
            if len(attempts) == 1:
                raise PortalDataError("resume_export_failed", "Synthetic compiler failure", 503)
            return compile_source(binding)

        store.prism_client.compile = fail_once
        page.goto(active.origin + "/#flow")
        reveal_control(page, "#flow-export-pdf")
        page.locator("#flow-export-pdf").click()
        expect(page.locator("#flow-export-pdf")).to_have_text("仅重试 PDF 导出")
        expect(page.locator("#flow-export")).to_contain_text("PDF 导出未完成")
        page.reload()
        reveal_control(page, "#flow-export-pdf")
        assert len(attempts) == 1 and work["calls"] == []
        page.locator("#flow-export-pdf").click()
        expect(page.locator("#flow-pdf-link")).to_be_visible()
        saved = snapshot(active)["active_task"]
        assert saved["draft_id"] == tasks[0]["draft_id"]
        assert saved["draft_sha256"] == tasks[0]["draft_sha256"]
        assert saved["draft_review"] is None and saved["materials_confirmed"] is False
        assert saved["status"] == "resume_ready" and saved["worker_ref"] is None
        assert len(attempts) == 2 and len(work["exports"]) == 1 and work["calls"] == []
        expect(page.locator("#flow-reviewed-pdf")).to_have_count(0)
        expect(page.locator("#flow-worker")).to_have_count(0)


def test_unknown_export_requires_receipt_recheck_without_repeating_export_or_model(
    portal, tmp_path, browser_page
):
    from playwright.sync_api import expect

    page = browser_page
    with authorized_latex_portal(portal, tmp_path) as (active, _jobs, tasks, work):
        store = active.server.application_resume_store
        export = store.export_for_draft

        def save_then_unknown(*args, **kwargs):
            export(*args, **kwargs)
            raise PortalDataError("resume_export_needs_recheck", "Synthetic lost reply", 409)

        store.export_for_draft = save_then_unknown
        page.goto(active.origin + "/#flow")
        reveal_control(page, "#flow-export-pdf")
        page.locator("#flow-export-pdf").click()
        expect(page.locator("#flow-recheck-export")).to_be_enabled()
        expect(page.locator("#flow-export-pdf")).to_be_disabled()
        unknown = snapshot(active)["active_task"]
        assert unknown["stages"]["export"]["status"] == "needs_recheck"
        assert unknown["resume_id"] is None and len(work["exports"]) == 1
        page.reload()
        reveal_control(page, "#flow-recheck-export")
        assert snapshot(active)["active_task"] == unknown
        page.locator("#flow-recheck-export").click()
        expect(page.locator("#flow-pdf-link")).to_be_visible()
        saved = snapshot(active)["active_task"]
        assert saved["draft_id"] == tasks[0]["draft_id"]
        assert saved["resume_id"] == unknown["stages"]["export"]["attempt_id"]
        assert saved["status"] == "resume_ready" and not saved["materials_confirmed"]
        assert len(work["exports"]) == 1 and work["calls"] == []


def test_two_jobs_keep_technical_latex_exports_and_previews_separate(
    portal, tmp_path, browser_page
):
    from playwright.sync_api import expect
    from test_application_flow import wait_for
    from test_pdf_export_http import export_payload
    from test_preparation_entry import post

    page = browser_page
    with authorized_latex_portal(portal, tmp_path, count=2) as (active, jobs, tasks, work):
        flow = active.server.application_flow_service
        saved = []
        for task in tasks:
            assert post(active, "export-pdf", export_payload(task))[0] == 200
            saved.append(wait_for(flow, task["id"], lambda row: row["status"] == "resume_ready"))
        assert saved[0]["draft_id"] != saved[1]["draft_id"]
        assert saved[0]["resume_id"] != saved[1]["resume_id"]
        page.goto(active.origin + "/#flow")
        for job, task in zip(jobs, saved, strict=True):
            reveal_control(page, page.locator("#flow-task-list button").first)
            page.locator("#flow-task-list button").filter(has_text=job["company"]).click()
            expect(page.locator("#flow-pdf-link")).to_have_attribute(
                "href", f"/api/flow/resumes/{task['resume_id']}/pdf"
            )
            assert flow.task_snapshot(task["id"])["draft_id"] == task["draft_id"]
        assert len(work["exports"]) == 2 and work["calls"] == []
        assert all(not task["materials_confirmed"] and task["worker_ref"] is None for task in saved)


def test_damaged_pdf_stops_binding_and_allows_only_explicit_pdf_reexport(
    portal, tmp_path, browser_page
):
    from playwright.sync_api import expect

    page = browser_page
    with authorized_latex_portal(portal, tmp_path) as (active, _jobs, tasks, work):
        page.goto(active.origin + "/#flow")
        reveal_control(page, "#flow-export-pdf")
        page.locator("#flow-export-pdf").click()
        expect(page.locator("#flow-pdf-link")).to_be_visible()
        saved = snapshot(active)["active_task"]
        store = active.server.application_resume_store
        old_path = store.root / saved["resume_id"] / "resume.pdf"
        old_path.write_bytes(b"Damaged saved PDF")
        page.locator("#flow-observe").click()
        expect(page.locator("#flow-final-pdf-preview")).to_have_count(0)
        reveal_control(page, "#flow-export-pdf")
        expect(page.locator("#flow-export-pdf")).to_have_text("仅重试 PDF 导出")
        assert len(work["exports"]) == 1
        page.locator("#flow-export-pdf").click()
        expect(page.locator("#flow-final-pdf-preview")).to_be_visible()
        latest = snapshot(active)["active_task"]
        assert latest["resume_id"] != saved["resume_id"]
        assert latest["draft_id"] == tasks[0]["draft_id"]
        assert old_path.read_bytes() == b"Damaged saved PDF"
        assert len(work["exports"]) == 2 and work["calls"] == []


@pytest.mark.parametrize(
    "error_code", ["resume_chrome_registration_denied", "resume_chrome_registration_unknown"]
)
def test_registration_failure_reaches_main_ui_without_start_or_automatic_retry(
    portal, tmp_path, browser_page, error_code
):
    from playwright.sync_api import expect

    page = browser_page
    with authorized_latex_portal(portal, tmp_path) as (active, _jobs, tasks, work):
        attempts = []

        def unavailable(binding):
            attempts.append(binding)
            raise PortalDataError(error_code, "Synthetic compiler registration unavailable", 503)

        active.server.application_resume_store.prism_client.compile = unavailable
        page.goto(active.origin + "/#flow")
        reveal_control(page, "#flow-export-pdf")
        page.locator("#flow-export-pdf").click()
        expect(page.locator("#flow-export-pdf")).to_have_text("仅重试 PDF 导出")
        saved = snapshot(active)["active_task"]
        assert saved["stages"]["export"]["error_code"] == error_code
        assert saved["draft_id"] == tasks[0]["draft_id"] and saved["resume_id"] is None
        page.reload()
        page.locator("#flow-observe").click()
        assert len(attempts) == 1 and work["calls"] == work["exports"] == []
