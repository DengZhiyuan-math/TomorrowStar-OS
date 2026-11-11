"""The daily surface exposes saved outcomes while internal controls stay read-only."""

import json
from pathlib import Path

import pytest
from test_application_resume import task_resume as task_resume
from test_automatic_material_editor_browser import serving
from test_automatic_material_reuse_edit import complete_portal as complete_portal
from test_final_pdf_surface_browser import browser_page as browser_page
from test_final_pdf_surface_browser import (
    isolated_model_context as isolated_model_context,
)
from test_final_pdf_surface_browser import read_only_browser
from test_full_latex_generation import full_latex as full_latex

pytestmark = pytest.mark.worker_browser


@pytest.mark.parametrize("unknown", [False, True])
@pytest.mark.parametrize("fixed_profile", [False, True])
@pytest.mark.parametrize("complete_portal", [{"preparation_only": True}], indirect=True)
def test_internal_management_is_closed_and_toggling_never_repeats_material_work(
    complete_portal, tmp_path, browser_page, unknown, fixed_profile
):
    from playwright.sync_api import expect

    page = browser_page
    page.set_viewport_size({"width": 1280, "height": 900})
    server, store, task, generation = complete_portal
    requirement_text = "Build and operate reliable Python services for quantitative research teams."
    with serving(server) as origin:
        service = server.application_flow_service
        before = service.path.read_bytes()
        calls, exports = len(generation), len(store.prism_client.calls)

        def retained_state(route):
            response = route.fetch()
            state = response.json()
            state["active_explanation"]["reasons"].append(
                {
                    "text": requirement_text,
                    "importance": "required",
                    "judgment": "unknown",
                    "hard_condition": False,
                    "explanation": "No applicable evidence is recorded.",
                    "sources": [],
                }
            )
            state["preparation_batch"] = {
                "control": "paused" if unknown else "cancelled",
                "reason": "user_cancel",
                "kind": "selected_jobs",
                "items": [
                    {
                        "item_id": "synthetic-item",
                        "status": "needs_recheck",
                        "reason": "flow_result_needs_recheck",
                        "company": "Synthetic Final PDF",
                        "role_title": "Python Engineer",
                        "task_id": task["id"],
                    }
                ]
                if unknown
                else [],
            }
            if unknown:
                state["active_task"]["codex_handoff_ref"] = {
                    "kind": "executor_report",
                    "status": "needs_recheck",
                    "filename": "Synthetic_Final_CV.pdf",
                    "job_url": "https://example.invalid/jobs/synthetic",
                }
                state["active_task"]["status"] = "needs_recheck"
            if fixed_profile:
                explanation = state["active_explanation"]
                explanation["score"] = {
                    "lower": 60 if unknown else 100,
                    "upper": 100,
                    "coverage": 50 if unknown else 100,
                }
                explanation["business_summary"] = {
                    "business_objective": "Improve pricing decisions",
                    "work_outputs": ["Validated risk models"],
                    "groups": [],
                }
                explanation["material_read_coverage"] = {"complete": True}
                explanation["resume_coverage"] = {"status": "generated", "percent": 50}
                for reason in explanation["reasons"]:
                    reason["scoring_framework"] = {"group": {"label": "Pricing research outcomes"}}
                    reason["inference"] = {
                        "type": "semantic",
                        "relation": "supports"
                        if reason["judgment"] == "supported"
                        else "unresolved",
                        "basis": reason["explanation"],
                        "expression_scope": "Research implementation only",
                        "facts": [
                            {
                                "source_id": "synthetic-saved-source",
                                "quote": "Synthetic saved fact quote.",
                            }
                        ],
                    }
            route.fulfill(response=response, body=json.dumps(state))

        page.route("**/api/flow/state", retained_state)
        writes = read_only_browser(page)
        page.goto(origin + "/#flow")
        internal = page.locator("#flow-internal-management")
        for iteration in range(2):
            expect(internal).not_to_have_attribute("open", "")
            expect(page.locator("#flow-saved-jobs")).not_to_be_visible()
            expect(page.locator("#flow-opportunities")).not_to_be_visible()
            expect(page.locator("#flow-final-pdf-preview")).to_be_visible()
            expect(page.locator("#flow-pdf-link")).to_have_attribute(
                "href", f"/api/flow/resumes/{task['resume_id']}/pdf"
            )
            for selector in (
                "#flow-batch-create",
                "#flow-batch-resume",
                "#flow-refresh-mail",
                "#flow-history",
                "#flow-readiness",
                "#flow-job-management",
                "#flow-draft",
            ):
                expect(page.locator(selector)).not_to_be_visible()
            expect(page.get_by_text("加入材料批次", exact=True)).not_to_be_visible()
            visible_text = page.locator("#view-flow").inner_text()
            assert "待处理岗位" not in visible_text
            assert "材料批次" not in visible_text
            assert str(tmp_path) not in visible_text
            assert requirement_text not in visible_text
            overview = page.locator("#flow-explanation")
            expect(overview).to_be_visible()
            expect(page.locator("#flow-fit-score")).to_be_visible()
            expect(page.locator("#flow-fit-score-legend")).not_to_be_visible()
            if fixed_profile:
                expect(page.locator("#flow-fit-score")).to_contain_text(
                    "60–100/100" if unknown else "100/100"
                )
                expect(page.locator("#flow-fit-score")).not_to_contain_text("当前匹配分")
                expect(page.locator("#flow-fit-score")).not_to_contain_text("可能范围")
                expect(page.locator("#flow-fit-score")).to_contain_text("读取完成")
                expect(page.locator("#flow-fit-score")).to_contain_text("简历覆盖")
                expect(page.locator("#flow-fit-score")).to_contain_text("Improve pricing decisions")
                expect(page.locator(".flow-fit-list").first).to_contain_text(
                    "Pricing research outcomes"
                )
                expect(page.locator(".flow-fit-basis").first).to_be_visible()
                expect(overview).to_contain_text("分数确定度")
                expect(overview).to_contain_text("不表示每个原子事实都齐全")
            overview_box = overview.bounding_box()
            pdf_box = page.locator("#flow-final-pdf").bounding_box()
            assert overview_box and pdf_box and overview_box["height"] <= 380
            assert overview_box["y"] + overview_box["height"] <= pdf_box["y"]
            assert page.evaluate(
                """() => !!(document.querySelector('#flow-explanation').compareDocumentPosition(
                    document.querySelector('#flow-final-pdf'))
                    & Node.DOCUMENT_POSITION_FOLLOWING)"""
            )
            details = page.locator("#flow-fit-details")
            expect(details).not_to_have_attribute("open", "")
            details.locator(":scope > summary").click()
            expect(page.locator("#flow-fit-score-legend")).to_be_visible()
            expect(page.locator("#flow-fit-score-legend")).to_contain_text(
                "固定业务组权重" if fixed_profile else "必需 ×3"
            )
            if fixed_profile:
                expect(details).to_contain_text("语义推断")
                expect(details).to_contain_text("Research implementation only")
                # A fact shows its quote; its ids stay internal (2026-11-04).
                expect(details).to_contain_text("Synthetic saved fact quote.")
                expect(details).not_to_contain_text("synthetic-saved-source")
            expect(
                page.locator("#flow-fit-details .flow-requirement").filter(
                    has_text=requirement_text
                )
            ).to_be_visible()
            details.locator(":scope > summary").click()
            if unknown:
                expect(page.locator("#flow-batch-warning")).to_be_visible()
                expect(page.locator("#flow-batch-warning")).to_contain_text("操作结果待核验")
                expect(page.locator("#flow-existing-handoff .flow-error")).to_be_visible()
                expect(page.locator("#flow-existing-handoff")).to_contain_text("不重新填表或上传")
            internal.locator(":scope > summary").click()
            expect(page.locator("#flow-saved-jobs")).to_be_visible()
            expect(page.locator("#flow-opportunities")).to_be_visible()
            expect(page.locator("#flow-history")).to_be_visible()
            expect(page.locator("#flow-task-list button")).to_have_count(1)
            expect(page.locator("#flow-batch-create")).to_be_visible()
            page.locator("#flow-job-management .flow-job-settings > summary").click()
            expect(page.get_by_text("加入材料批次", exact=True)).to_be_visible()
            page.locator("#flow-material-batch > summary").click()
            expect(page.locator("#flow-batch-resume")).to_be_visible()
            expect(page.locator("#flow-batch-cancel")).to_be_visible()
            page.locator("#flow-intake-settings > summary").click()
            expect(page.locator("#flow-refresh-mail")).to_be_visible()
            internal.locator(":scope > summary").click()
            expect(page.locator("#flow-batch-resume")).not_to_be_visible()
            if not iteration:
                page.wait_for_load_state("networkidle")
                if not unknown:
                    page.evaluate("scrollTo(0, 0)")
                    page.screenshot(path="/private/tmp/daily-ui-synthetic.png")
                page.reload()
        assert not writes
        assert service.path.read_bytes() == before
        assert len(generation) == calls and len(store.prism_client.calls) == exports
        result = {
            "unknown": unknown,
            "fixed_profile": fixed_profile,
            "overview_height_px": overview_box["height"],
            "overview_before_pdf": True,
            "writes": writes,
            "flow_unchanged": True,
            "model_calls_unchanged": True,
            "export_calls_unchanged": True,
        }
        Path(f"/private/tmp/daily-ui-browser-{unknown}-{fixed_profile}.json").write_text(
            json.dumps(result)
        )
