"""MC-15: the default page shows the backend's activity projection and pipeline notice."""

import json
from contextlib import contextmanager

import pytest
from test_career_portal_http import _running_portal
from test_career_portal_http import portal as portal
from test_portal_workflow_browser import browser_page as browser_page

from career_evidence_graph.career_portal_data import ApplicationStore

pytestmark = pytest.mark.worker_browser

RUNNING = "当前阶段仍有执行记录"
IDLE = "任务已保存，尚未开始分析"
TAKEOVER = "已自动交给 Codex 接续原页"


@contextmanager
def _flow_portal(portal, tmp_path, *, preparation=False):
    job = ApplicationStore(portal.applications).create_application(
        {"company": "Synthetic", "role_title": "Engineer", "job_description": "Build Python."}
    )
    mode = {"preparation_only": True} if preparation else {"worker_root": tmp_path / "worker"}
    with _running_portal(
        portal.applications, portal.career, flow_root=tmp_path / "flow", **mode
    ) as active:
        active.server.application_flow_service.create(job["id"], job["revision"])
        yield active


@pytest.mark.parametrize(
    ("saved_stage", "projected", "shown", "hidden"),
    [
        # A locally running stage record does not override the backend's idle projection.
        ("running", "idle", IDLE, RUNNING),
        # The backend's running projection is shown even when the stage looks pending.
        ("pending", "running", RUNNING, IDLE),
    ],
)
def test_next_step_follows_the_projected_activity(
    portal, browser_page, tmp_path, saved_stage, projected, shown, hidden
):
    from playwright.sync_api import expect

    with _flow_portal(portal, tmp_path, preparation=True) as active:

        def project(route):
            state = json.loads(route.fetch().body())
            assert state["preparation_activity"]["status"] == "idle"
            state["active_task"]["stages"]["analysis"]["status"] = saved_stage
            state["preparation_activity"]["status"] = projected
            route.fulfill(json=state)

        browser_page.route("**/api/flow/state", project)
        browser_page.goto(active.origin + "/#flow")
        task = browser_page.locator("#flow-task")
        expect(task).to_contain_text(shown)
        expect(task).not_to_contain_text(hidden)


@pytest.mark.parametrize(
    ("notice", "takeover_title"),
    [
        ({"kind": "takeover", "title": "已交给 Codex 接续", "message": TAKEOVER}, True),
        (None, True),
    ],
)
def test_pipeline_notice_shows_a_live_takeover_only(
    portal, browser_page, tmp_path, notice, takeover_title
):
    from playwright.sync_api import expect

    with _flow_portal(portal, tmp_path) as active:

        def read(route):
            state = json.loads(route.fetch().body())
            assert state["notice"] is None and state["notification"] is None
            state.update(
                id="synthetic-pipeline",
                control="running",
                status="filling",
                notice=notice,
                takeover_request={"title": "已交给 Codex 接续", "message": TAKEOVER}
                if takeover_title
                else None,
            )
            route.fulfill(json=state)

        browser_page.route("**/api/pipeline/state", read)
        browser_page.goto(active.origin + "/#flow")
        automation = browser_page.locator("#flow-automation")
        expect(automation).to_contain_text("正在填写并上传申请材料")
        if notice:
            expect(automation).to_contain_text(TAKEOVER)
        else:
            expect(automation).not_to_contain_text(TAKEOVER)


def test_wait_notice_keeps_the_notification_text(portal, browser_page, tmp_path):
    from playwright.sync_api import expect

    with _flow_portal(portal, tmp_path) as active:
        message = "请补充电话号码后继续当前岗位。"

        def read(route):
            state = json.loads(route.fetch().body())
            notification = {"id": "n1", "title": "自动流程需要处理", "message": message}
            state.update(
                id="synthetic-pipeline",
                status="needs_input",
                notification=notification,
                notice={"kind": "wait", "title": notification["title"], "message": message},
            )
            route.fulfill(json=state)

        browser_page.route("**/api/pipeline/state", read)
        browser_page.goto(active.origin + "/#flow")
        expect(browser_page.locator("#flow-automation")).to_contain_text(message)
