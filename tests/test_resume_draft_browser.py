"""Current language/content gates and the read-only retired HTML presentation.

LaTeX source edits and version invalidation run in existing_latex_browser and
manual-material-editor tests. PDF retries and unknown receipts run in
pdf_export_browser; grouped factual review runs in group_review_browser.
"""

import json
import sys

import pytest
from test_application_match import model_output as base_model_output
from test_career_portal_http import portal as portal
from test_job_explanation_browser import explanation_portal, reveal_control, select_saved_job
from test_portal_workflow_browser import browser_page as browser_page

from career_evidence_graph.career_portal_data import ApplicationStore

pytestmark = pytest.mark.worker_browser


@pytest.fixture(autouse=True)
def isolated_model_context(tmp_path, monkeypatch):
    codex_home = tmp_path / "synthetic-codex-home"
    codex_home.mkdir()
    monkeypatch.setenv("CODEX_HOME", str(codex_home))
    monkeypatch.setenv("TOMORROWSTAR_CODEX_EXECUTABLE", sys.executable)
    monkeypatch.delenv("CODEX_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)


def test_retired_html_history_has_no_review_generation_or_export_controls(
    portal, tmp_path, browser_page
):
    from playwright.sync_api import expect

    job = ApplicationStore(portal.applications).create_application(
        {
            "company": "Synthetic historical",
            "role_title": "Engineer",
            "job_description": "Build Python services.",
        }
    )
    page, writes = browser_page, []
    with explanation_portal(portal, tmp_path) as (active, work):
        flow = active.server.application_flow_service
        task = flow.create(job["id"], job["revision"])
        saved = flow.path.read_bytes()

        def historical_read(route):
            response = route.fetch()
            state = response.json()
            # UI-only historical response, with no saved or purportedly verified
            # manifest and no invocation of the retired HTML producer.
            retained = state["active_task"]
            retained.update(status="draft_ready", draft_id="a" * 32, draft_sha256="b" * 64)
            retained["artifacts"].append(
                {
                    "stage": "resume",
                    "adopted": True,
                    "result": {
                        "kind": "draft",
                        "origin": "legacy_html",
                        "id": "a" * 32,
                        "draft_sha256": "b" * 64,
                    },
                }
            )
            state["tasks"] = [retained]
            state["draft_integrity"] = {"status": "invalid", "message": "Retired HTML history"}
            route.fulfill(response=response, json=state)

        page.route("**/api/flow/state", historical_read)
        page.on(
            "request",
            lambda request: writes.append(request.url) if request.method == "POST" else None,
        )
        page.goto(active.origin + "/#flow")
        for _ in range(2):
            reveal_control(page, "#flow-draft")
            expect(page.locator("#flow-draft")).to_contain_text("旧 HTML 简历已弃用")
            for selector in (
                "#flow-review-draft",
                "#flow-export-pdf",
                "#flow-regenerate-resume",
                "#flow-bind-prism",
                "#flow-confirm-materials",
                "#flow-worker",
            ):
                expect(page.locator(selector)).to_have_count(0)
            assert flow.snapshot()["active_task"] == task and flow.path.read_bytes() == saved
            assert writes == work["calls"] == work["exports"] == []
            page.reload()


def test_explicit_other_resume_language_is_shown_and_waits_for_separate_handling(
    portal, tmp_path, browser_page
):
    from playwright.sync_api import expect

    ApplicationStore(portal.applications).create_application(
        {
            "company": "Synthetic",
            "role_title": "Engineer",
            "job_description": "Build Python services. Please submit your CV in German.",
        }
    )
    page = browser_page
    with explanation_portal(portal, tmp_path) as (active, work):
        page.goto(active.origin + "/#flow")
        select_saved_job(
            page, page.locator("#flow-saved-jobs").get_by_role("button", name="选择已有岗位")
        )
        expect(page.locator("#flow-resume-language")).to_contain_text(
            "Please submit your CV in German."
        )
        expect(page.locator("#flow-resume-language")).to_contain_text("等待单独处理")
        reveal_control(page, "#flow-start-analysis")
        page.locator("#flow-start-analysis").click()
        expect(page.locator("#flow-explanation")).to_contain_text("已支持 100/100")
        expect(page.locator("#flow-start-resume")).to_be_disabled()
        expect(page.locator("#flow-draft")).to_have_count(0)
        state = active.server.application_flow_service.snapshot()
        assert state["resume_language"]["status"] == "needs_input"
        assert state["active_task"]["material_contract"] == "content-writing/v1"
        assert not state["active_task"].get("draft_id") and not work["exports"]


def test_empty_selected_sources_cannot_fall_back_to_retired_html_without_json_material(
    portal, tmp_path, browser_page, monkeypatch
):
    from playwright.sync_api import expect

    def no_selected_material(snapshot):
        return base_model_output(snapshot) | {"selected_source_ids": [], "selection_rationale": []}

    monkeypatch.setattr("test_job_explanation_browser.model_output", no_selected_material)
    ApplicationStore(portal.applications).create_application(
        {
            "company": "Synthetic",
            "role_title": "Engineer",
            "job_description": "Build Python services.",
        }
    )
    page = browser_page
    with explanation_portal(portal, tmp_path) as (active, work):
        page.goto(active.origin + "/#flow")
        select_saved_job(
            page, page.locator("#flow-saved-jobs").get_by_role("button", name="选择已有岗位")
        )
        reveal_control(page, "#flow-start-analysis")
        page.locator("#flow-start-analysis").click()
        expect(page.locator("#flow-start-resume")).to_be_enabled()
        page.locator("#flow-start-resume").click()
        expect(page.locator("#flow-task")).to_contain_text("resume_content_material_required")
        expect(page.locator("#flow-draft")).to_have_count(0)
        expect(page.locator("#flow-pdf-link")).to_have_count(0)
        task = active.server.application_flow_service.snapshot()["active_task"]
        assert task["material_contract"] == "content-writing/v1"
        assert task["stages"]["resume"]["error_code"] == "resume_content_material_required"
        assert not task.get("draft_id") and not work["exports"]
        assert len(work["calls"]) == 2
        assert sum(call[-1] == "--version" for call in work["calls"]) == 1
        executions = [call for call in work["calls"] if "exec" in call]
        assert len(executions) == 1
        assert json.loads(executions[0][-1].rsplit("\n", 1)[1])["job"]["company"] == "Synthetic"
