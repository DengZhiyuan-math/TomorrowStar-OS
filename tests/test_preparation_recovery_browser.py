"""Saved LaTeX checkpoints reopen without generation, compilation or application work."""

import pytest
from latex_browser_support import review_all_groups
from test_application_flow import wait_for
from test_application_resume import task_resume as task_resume
from test_automatic_material_editor_browser import serving
from test_automatic_material_reuse_edit import complete_portal as complete_portal
from test_career_portal_http import Portal, _running_portal
from test_career_portal_http import portal as portal
from test_full_latex_generation import full_latex as full_latex
from test_job_explanation_browser import reveal_control
from test_material_batch_http import wait_batch
from test_pdf_export_browser import assert_automatic_binding
from test_portal_workflow_browser import browser_page as browser_page
from test_preparation_entry import post, snapshot

from career_evidence_graph.career_portal_data import PortalDataError

pytestmark = pytest.mark.worker_browser


@pytest.mark.parametrize("complete_portal", [{"preparation_only": True}], indirect=True)
def test_retained_automatically_bound_latex_pdf_reopens_with_exact_identity_without_work(
    complete_portal, browser_page
):
    from playwright.sync_api import expect

    server, store, original, calls = complete_portal
    flow = server.application_flow_service
    page = browser_page
    with serving(server):
        active = Portal(server, store.applications.root, store.catalog.root)
        before = snapshot(active)
        assert_automatic_binding(before["active_task"])
        page.goto(active.origin + "/#flow")
        expect(page.locator("#flow-pdf-link")).to_be_visible()
        expect(page.locator("#flow-worker")).to_have_count(0)
    call_count = len(calls)
    flow.close()
    with _running_portal(
        store.applications.root,
        store.catalog.root,
        flow_root=flow.path.parent,
        preparation_only=True,
        flow_resume_factory=lambda *_: store,
    ) as reopened:
        page.goto(reopened.origin + "/#flow")
        reveal_control(page, "#flow-runtime")
        expect(page.locator("#flow-runtime")).to_contain_text(
            snapshot(reopened)["runtime"]["session_id"]
        )
        binding = page.locator("#flow-task-binding")
        reveal_control(page, binding.locator(":scope > summary"))
        for value in (
            original["id"],
            *[
                original["inputs"][key]
                for key in ("jd_revision", "sources_revision", "resume_configuration_revision")
            ],
        ):
            expect(binding).to_contain_text(value)
        expect(page.locator("#flow-recovery")).to_contain_text("真实申请继续暂停")
        expect(page.locator("#flow-pdf-link")).to_have_attribute(
            "href", f"/api/flow/resumes/{original['resume_id']}/pdf"
        )
        for selector in ("#flow-confirm-materials", "#flow-reviewed-pdf", "#flow-worker"):
            expect(page.locator(selector)).to_have_count(0)
        page.reload()
        page.locator("#flow-observe").click()
        after = snapshot(reopened)
        assert after["runtime"]["session_id"] != before["runtime"]["session_id"]
        assert after["active_task"] == original
        assert after["draft_integrity"]["status"] == after["pdf_integrity"]["status"] == "valid"
        assert len(calls) == call_count and len(store.prism_client.calls) == 1
        assert reopened.server.worker_service is None
        assert (
            post(
                reopened,
                "cancel",
                {"task_id": original["id"], "task_revision": original["revision"]},
            )[0]
            == 200
        )
        page.locator("#flow-observe").click()
        expect(page.locator("#flow-task > .flow-badges")).to_have_text("任务已取消")
        assert snapshot(reopened)["active_task"]["status"] == "cancelled"
        reveal_control(page, "#flow-draft")
        expect(page.locator("#flow-draft")).to_contain_text("当前岗位简历")
        expect(page.locator("#flow-edit-automatic-source")).to_be_disabled()
        assert store.draft(original["draft_id"])["latex_source"]
        assert len(calls) == call_count and len(store.prism_client.calls) == 1


@pytest.mark.parametrize(
    "complete_portal",
    [
        {
            "preparation_only": True,
            "grouped_review": True,
            "stop_before_export": True,
        }
    ],
    indirect=True,
)
def test_unknown_grouped_latex_batch_reopens_for_receipt_recheck_without_next_job(
    complete_portal, browser_page
):
    from playwright.sync_api import expect

    server, store, initial, calls = complete_portal
    service = server.application_flow_service
    first_job = store.applications.get_application(initial["application_id"])
    next_job = store.applications.create_application(
        {
            "company": "Synthetic Next",
            "role_title": "Engineer",
            "job_description": "Build Python services.",
        }
    )
    page, exports = browser_page, []
    original_export = store.export_for_draft

    def save_then_unknown(*args, **kwargs):
        exports.append(kwargs["export_id"])
        original_export(*args, **kwargs)
        raise PortalDataError("resume_export_needs_recheck", "Synthetic lost response.", 503)

    store.export_for_draft = save_then_unknown
    with serving(server):
        active = Portal(server, store.applications.root, store.catalog.root)
        page.goto(active.origin + "/#flow")
        review_all_groups(page)
        reviewed = snapshot(active)["active_task"]
        assert reviewed["factual_review"] == "groups_reviewed"
        assert store.group_prism_client.calls == ["compile"] and exports == []
        assert store.prism_client.calls == []
        _, batch = post(
            active,
            "batch-create",
            {
                "request_id": "b" * 32,
                "items": [
                    {"kind": "application", "id": job["id"], "revision": job["revision"]}
                    for job in [first_job, next_job]
                ],
            },
        )
        assert (
            post(
                active,
                "batch-control",
                {
                    "batch_id": batch["id"],
                    "batch_revision": batch["revision"],
                    "operation": "resume",
                },
            )[0]
            == 200
        )
        task = wait_for(service, initial["id"], lambda row: row["status"] == "needs_recheck")
        before = wait_batch(
            active, lambda state: state["preparation_batch"]["control"] == "needs_recheck"
        )
        assert exports == [task["stages"]["export"]["attempt_id"]]
        assert len(before["tasks"]) == 1
        assert sum(bool(item["task_id"]) for item in before["preparation_batch"]["items"]) == 1
        call_count = len(calls)
    with _running_portal(
        store.applications.root,
        store.catalog.root,
        flow_root=service.path.parent,
        preparation_only=True,
        flow_resume_factory=lambda *_: store,
    ) as reopened:
        page.goto(reopened.origin + "/#flow")
        reveal_control(page, "#flow-recheck-export")
        expect(page.locator("#flow-recovery")).to_contain_text(task["draft_id"])
        expect(page.locator("#flow-recovery")).to_contain_text(
            task["stages"]["export"]["attempt_id"]
        )
        expect(page.locator("#flow-recheck-export")).to_be_enabled()
        expect(page.locator("#flow-export-pdf")).to_be_disabled()
        page.reload()
        page.locator("#flow-observe").click()
        assert snapshot(reopened)["active_task"] == task
        assert len(exports) == 1 and store.group_prism_client.calls == ["compile"]
        assert store.prism_client.calls == [] and len(calls) == call_count
        reveal_control(page, "#flow-recheck-export")
        page.locator("#flow-recheck-export").click()
        expect(page.locator("#flow-pdf-link")).to_be_visible()
        expect(page.locator("#flow-recheck-export")).to_have_count(0)
        recovered = snapshot(reopened)["active_task"]
        assert recovered["stages"]["export"]["attempt_id"] == task["stages"]["export"]["attempt_id"]
        assert recovered["export_recheck"]["status"] == "complete"
        assert_automatic_binding(recovered)
        reveal_control(page, "#flow-batch-resume")
        expect(page.locator("#flow-batch-resume")).to_be_disabled()
        expect(page.locator("#flow-material-batch")).to_contain_text("等待投递结果记录")
        after = snapshot(reopened)
        assert after["preparation_batch"]["control"] == "paused"
        assert len(after["tasks"]) == 1
        assert sum(bool(item["task_id"]) for item in after["preparation_batch"]["items"]) == 1
        assert len(exports) == 1 and store.group_prism_client.calls == ["compile"]
        assert store.prism_client.calls == [] and len(calls) == call_count
        assert reopened.server.worker_service is None
