"""Grouped source review produces exact automatic PDF bindings without a checkbox."""

import pytest
from test_application_flow import wait_for
from test_career_portal_http import portal as portal
from test_full_latex_http import bind_generate, generated_portal
from test_job_explanation_browser import reveal_control
from test_pdf_export_browser import assert_automatic_binding
from test_portal_workflow_browser import browser_page as browser_page
from test_preparation_entry import post, snapshot
from test_reviewed_latex_pdf_http import install_export, prepare_reviewed

from career_evidence_graph.career_portal_data import PortalDataError

pytestmark = pytest.mark.worker_browser


def test_grouped_pdf_binds_automatically_and_preserves_application_pause(
    portal, tmp_path, monkeypatch, browser_page
):
    from playwright.sync_api import expect

    with generated_portal(portal, tmp_path, monkeypatch) as (active, task, base, calls, work):
        task = bind_generate(active, task, base)
        task, draft, project = prepare_reviewed(active, task, tmp_path, monkeypatch)
        requests = install_export(active, task, draft, monkeypatch)
        page = browser_page
        page.goto(active.origin + "/#flow")
        root = page.locator("#flow-root")
        reveal_control(page, "#flow-export-pdf")
        expect(root.get_by_role("button", name="绑定完整源与新 PDF", exact=True)).to_be_enabled()
        assert not snapshot(active)["active_task"]["materials_confirmed"]
        root.get_by_role("button", name="绑定完整源与新 PDF", exact=True).click()
        expect(root.locator("#flow-pdf-link")).to_be_visible()
        expect(root.locator("#flow-final-pdf-preview")).to_be_visible()
        expect(root.locator("#flow-final-pdf-preview")).to_have_attribute(
            "src", f"/api/flow/resumes/{snapshot(active)['active_task']['resume_id']}/pdf"
        )
        expect(root.locator("#flow-reviewed-pdf")).to_have_count(0)
        expect(root.locator("#flow-confirm-materials")).to_have_count(0)
        saved = snapshot(active)["active_task"]
        assert_automatic_binding(saved)
        assert not saved["worker_ref"] and len(requests) == 1 and len(calls) == 1
        expect(root.locator("#flow-worker")).to_have_count(0)
        assert not work["exports"]
        store = active.server.application_resume_store
        original_reader = store.read_export

        def damaged_copy(identifier):
            if identifier == saved["resume_id"]:
                raise PortalDataError("resume_export_needs_recheck", "Synthetic damaged copy", 409)
            return original_reader(identifier)

        monkeypatch.setattr(store, "read_export", damaged_copy)
        root.get_by_role("button", name="读取最新状态", exact=True).click()
        expect(
            root.get_by_role("button", name="重新绑定完整源与新 PDF", exact=True)
        ).to_be_enabled()
        root.get_by_role("button", name="重新绑定完整源与新 PDF", exact=True).click()
        expect(root.locator("#flow-pdf-link")).to_be_visible()
        expect(root.locator("#flow-reviewed-pdf")).to_have_count(0)
        expect(root.locator("#flow-confirm-materials")).to_have_count(0)
        rebound = wait_for(
            active.server.application_flow_service,
            saved["id"],
            lambda row: (
                row["resume_id"] != saved["resume_id"]
                and row["status"] in {"materials_ready", "needs_recheck"}
            ),
        )
        assert rebound["resume_id"] != saved["resume_id"]
        assert_automatic_binding(rebound)
        assert rebound["material_binding"]["resume_id"] != saved["material_binding"]["resume_id"]
        assert len(requests) == 2
        (project / "main.tex").write_text(draft["latex_source"] + " changed")
        root.get_by_role("button", name="读取最新状态", exact=True).click()
        expect(root).to_contain_text("检测到 Prism 已保存新改动")
        expect(root.locator("#flow-confirm-materials")).to_have_count(0)
        status, _ = post(
            active,
            "export-pdf",
            {
                "task_id": rebound["id"],
                "task_revision": rebound["revision"],
                "draft_id": rebound["draft_id"],
                "draft_sha256": rebound["draft_sha256"],
            },
        )
        assert status == 409
        assert snapshot(active)["active_task"]["material_binding"] == rebound["material_binding"]
        assert len(requests) == 2
