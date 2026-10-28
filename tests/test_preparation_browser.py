"""Synthetic loopback journeys for the material preparation workspace."""

import sys

import pytest
from test_application_intake import message
from test_application_intake import page as captured_page
from test_application_resume import task_resume as task_resume
from test_automatic_material_editor_browser import serving
from test_automatic_material_reuse_edit import complete_portal as complete_portal
from test_career_portal_http import _running_portal
from test_career_portal_http import portal as portal
from test_full_latex_generation import full_latex as full_latex
from test_job_explanation_browser import open_internal_management, reveal_control, select_saved_job
from test_portal_workflow_browser import browser_page as browser_page

from career_evidence_graph.application_intake import ApplicationIntakeService
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


def open_system_details(page):
    open_internal_management(page)
    details = page.locator("#flow-system-details")
    if details.get_attribute("open") is None:
        details.locator(":scope > summary").click()


def test_preparation_readiness_is_visible_without_a_task(portal, tmp_path, browser_page):
    from playwright.sync_api import expect

    page = browser_page

    def preparation_state(route):
        response = route.fetch()
        state = response.json()
        state["mode"] = "preparation"
        state["capabilities"]["codex_cli"] = "unavailable"
        state["preparation"] = {
            "checks": {
                "gmail": {"status": "unavailable", "message": "Synthetic Gmail is disconnected."},
                "model": {"status": "unavailable", "message": "Synthetic model is disconnected."},
                "sources": {"status": "unavailable", "message": "Synthetic sources are missing."},
                "pdf": {"status": "unavailable", "message": "Synthetic PDF exporter is missing."},
                "policy": {"status": "needs_input", "message": "Synthetic policy needs review."},
                "draft": {"status": "not_ready", "message": "Synthetic draft is not ready."},
            }
        }
        route.fulfill(response=response, json=state)

    page.route("**/api/flow/state", preparation_state)
    with _running_portal(
        portal.applications,
        portal.career,
        flow_root=tmp_path / "preparation",
        preparation_only=True,
    ) as instance:
        page.goto(instance.origin + "/#flow")
        expect(page.get_by_role("heading", name="投递工作台", exact=True)).to_be_visible()
        expect(page.locator('[data-view="flow"]')).to_contain_text("材料准备")
        open_internal_management(page)
        page.locator("#flow-preparation-diagnostics > summary").click()
        expect(page.locator("#flow-readiness")).to_be_visible()
        for message in (
            "Synthetic Gmail is disconnected.",
            "Synthetic model is disconnected.",
            "Synthetic sources are missing.",
            "Synthetic PDF exporter is missing.",
            "Synthetic policy needs review.",
            "Synthetic draft is not ready.",
        ):
            expect(page.locator("#flow-readiness")).to_contain_text(message)
        expect(page.locator("#flow-worker")).to_have_count(0)
        expect(page.locator("#flow-task-list button")).to_have_count(0)
        expect(page.locator("#flow-refresh-mail")).to_be_disabled()


@pytest.mark.parametrize("damaged_draft", [False, True])
@pytest.mark.parametrize(
    "complete_portal", [{"preparation_only": True, "stop_before_export": True}], indirect=True
)
def test_retained_full_latex_draft_reopens_without_filling_controls(
    complete_portal, browser_page, damaged_draft
):
    from playwright.sync_api import expect

    server, store, task, calls = complete_portal
    flow = server.application_flow_service
    before = flow.path.read_bytes()
    call_count = len(calls)
    page = browser_page
    with serving(server) as origin:
        page.goto(origin + "/#flow")
        expect(page.locator("#flow-saved-jobs")).to_contain_text("Synthetic · Service Engineer")
        expect(page.locator("#flow-draft")).not_to_be_visible()
        reveal_control(page, "#flow-draft")
        expect(page.locator("#flow-draft")).to_contain_text("当前岗位简历")
        assert store.draft(task["draft_id"])["latex_source"]
        for selector in ("#flow-review-draft", "#flow-confirm-materials", "#flow-worker"):
            expect(page.locator(selector)).to_have_count(0)
        expect(page.locator("#flow-pdf-link")).to_have_count(0)
        if damaged_draft:
            (store.root / task["draft_id"] / "draft.json").write_text("{}")
        page.reload()
        page.locator("#flow-observe").click()
        state = page.request.get(origin + "/api/flow/state").json()
        assert state["active_task"]["draft_id"] == task["draft_id"]
        assert state["draft_integrity"]["status"] == ("invalid" if damaged_draft else "valid")
        expect(page.locator("#flow-draft")).not_to_be_visible()
        assert flow.path.read_bytes() == before
        assert len(calls) == call_count and store.prism_client.calls == []


def test_preparation_failed_mail_read_can_be_explicitly_retried(
    portal, tmp_path, browser_page, monkeypatch
):
    from playwright.sync_api import expect

    monkeypatch.setenv("TOMORROWSTAR_CODEX_EXECUTABLE", sys.executable)
    reads = []

    def reader(directory, **kwargs):
        reads.append(kwargs)
        directory.mkdir()
        if len(reads) == 1:
            raise ValueError("Synthetic temporary connector failure")
        return {"status": "readable", "emails": [message()], "provenance": {}}

    def intake_factory(applications, root):
        return ApplicationIntakeService(applications, root, reader=reader, fetcher=captured_page)

    page = browser_page
    with _running_portal(
        portal.applications,
        portal.career,
        preparation_only=True,
        flow_root=tmp_path / "preparation",
        flow_intake_factory=intake_factory,
    ) as instance:
        page.goto(instance.origin + "/#flow")
        open_internal_management(page)
        page.locator("#flow-intake-settings > summary").click()
        refresh = page.locator("#flow-refresh-mail")
        refresh.click()
        expect(page.locator("#flow-mail-status")).to_contain_text("读取失败，可明确重试")
        expect(refresh).to_be_enabled()
        assert len(reads) == 1
        refresh.click()
        expect(page.locator("#flow-candidates .flow-recommendation")).to_have_count(1)
        expect(page.locator("#flow-mail-status")).to_contain_text("推荐岗位已载入")
        assert len(reads) == 2
        assert instance.server.application_flow_service.snapshot()["tasks"] == []


def test_preparation_changed_jd_requires_explicit_sync_before_analysis(
    portal, tmp_path, browser_page
):
    from playwright.sync_api import expect

    applications = ApplicationStore(portal.applications)
    job = applications.create_application(
        {
            "company": "Synthetic",
            "role_title": "Engineer",
            "job_description": "Build Python services.",
        }
    )
    page = browser_page
    with _running_portal(
        portal.applications,
        portal.career,
        preparation_only=True,
        flow_root=tmp_path / "preparation",
        flow_analyzer=lambda *_args, **_kwargs: pytest.fail("Unexpected analysis execution"),
    ) as instance:
        page.goto(instance.origin + "/#flow")
        open_internal_management(page)
        select_saved_job(
            page, page.locator("#flow-saved-jobs").get_by_role("button", name="选择已有岗位")
        )
        expect(page.locator("#flow-start-analysis")).to_be_enabled()
        applications.update_application(
            job["id"], {"job_description": "Build Rust services."}, job["revision"]
        )
        page.locator("#flow-observe").click()
        expect(page.locator("#flow-readiness")).to_contain_text("输入已变化")
        expect(page.locator("#flow-start-analysis")).to_be_disabled()
        expect(page.locator("#flow-task")).to_contain_text("同步最新岗位与资料")
        reveal_control(page, "#flow-sync-inputs")
        page.locator("#flow-sync-inputs").click()
        page.locator("#confirmation-continue").click()
        expect(page.locator("#flow-start-analysis")).to_be_enabled()
        expect(page.locator("#flow-system-details")).to_contain_text("Build Rust services.")
        expect(page.locator("#flow-task-list button")).to_have_count(1)
