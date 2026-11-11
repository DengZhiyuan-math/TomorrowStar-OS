"""Default job selection admits work without independently creating a flow."""

import pytest
from test_career_portal_http import portal as portal
from test_handoff_http import create_application, handoff_portal, post, prepare_payload
from test_job_explanation_browser import reveal_control
from test_pipeline_controls_browser import pipeline_state
from test_portal_workflow_browser import browser_page as browser_page

pytestmark = pytest.mark.worker_browser


def test_recommendation_enters_pipeline_without_starting_another_flow(portal, browser_page):
    from playwright.sync_api import expect

    page = browser_page
    state = pipeline_state(
        id="pipeline-one",
        current_recommendation_id="current",
        control="running",
        status="needs_input",
    )
    page.route("**/api/pipeline/state", lambda route: route.fulfill(json=state))
    page.route(
        "**/api/flow/state",
        lambda route: route.fulfill(
            json={"enabled": True, "mode": "application", "tasks": [], "active_task": None}
        ),
    )
    page.route(
        "**/api/recommendations/state",
        lambda route: route.fulfill(
            json={
                "enabled": True,
                "status": "complete",
                "recommendations": [
                    {
                        "id": "rec-other",
                        "revision": "rev-one",
                        "company": "Other",
                        "role_title": "Engineer",
                        "jd_completeness": "excerpt",
                        "acquisition_status": "available",
                    }
                ],
            }
        ),
    )
    writes = []

    def admit(route):
        writes.append(route.request.post_data_json)
        route.fulfill(json=state)

    page.route("**/api/pipeline/admit", admit)
    page.goto(portal.origin + "/#flow")
    reveal_control(page, "#flow-candidates")
    expect(page.get_by_role("button", name="加入申请队列", exact=True)).to_be_enabled()
    page.get_by_role("button", name="加入申请队列", exact=True).click()
    expect(page.locator("#flow-notice")).to_contain_text("已加入申请队列")
    assert writes[0]["recommendation_id"] == "rec-other"
    assert writes[0]["recommendation_revision"] == "rev-one"
    assert state["current_recommendation_id"] == "current"
    expect(page.get_by_role("button", name="取得完整 JD", exact=True)).to_have_count(0)


def test_manual_job_open_uses_admission_and_keeps_viewing_current_job(portal, browser_page):
    from playwright.sync_api import expect

    page = browser_page
    state = pipeline_state(
        id="pipeline-one", current_recommendation_id="current", status="needs_input"
    )
    page.route("**/api/pipeline/state", lambda route: route.fulfill(json=state))
    readable = False

    def flow_read(route):
        if not readable:
            route.abort()
        else:
            route.fulfill(
                json={"enabled": True, "mode": "application", "tasks": [], "active_task": None}
            )

    page.route("**/api/flow/state", flow_read)
    page.route(
        "**/api/recommendations/state",
        lambda route: route.fulfill(
            json={"enabled": True, "status": "complete", "recommendations": []}
        ),
    )
    page.route(
        "**/api/applications/manual",
        lambda route: route.fulfill(
            json={"application": {"id": "manual", "revision": "manual-v1"}}
        ),
    )
    writes = []

    def admit(route):
        writes.append(route.request.post_data_json)
        route.fulfill(json=state)

    page.route("**/api/pipeline/admit", admit)
    page.goto(portal.origin + "/#flow")
    expect(page.locator("#flow-notice")).to_be_visible()
    readable = True
    page.evaluate(
        "window.dispatchEvent(new CustomEvent('flow-open', "
        "{ detail: { applicationId: 'manual' } }))"
    )
    expect(page.locator("#flow-notice")).to_contain_text("已加入申请队列")
    assert writes[0]["application_id"] == "manual"
    assert writes[0]["application_revision"] == "manual-v1"
    assert state["current_recommendation_id"] == "current"


@pytest.mark.parametrize("fragment", ["", "#overview"], ids=["bare", "overview"])
def test_default_overview_uses_automatic_pipeline_guidance(portal, browser_page, fragment):
    from playwright.sync_api import expect

    page = browser_page
    state = pipeline_state(
        id="pipeline-one",
        current_recommendation_id="current",
        control="running",
        status="generating_resume",
        items=[{"recommendation_id": "current", "company": "Current", "role_title": "Engineer"}],
    )
    page.route("**/api/pipeline/state", lambda route: route.fulfill(json=state))
    page.route(
        "**/api/flow/state",
        lambda route: route.fulfill(
            json={"enabled": True, "mode": "application", "tasks": [], "active_task": None}
        ),
    )
    page.goto(portal.origin + "/" + fragment)
    expect(page.locator("#workflow-state")).to_have_text("正在生成并检查完整岗位材料")
    expect(page.locator("#workflow-title")).to_have_text("Current · Engineer")
    expect(page.locator("#workflow-primary")).to_have_attribute("href", "#flow")
    expect(page.locator('[aria-label="申请主流程"]')).not_to_contain_text("Codex 领取")
    expect(page.locator('[aria-label="申请主流程"]')).to_contain_text("自动生成简历")
    expect(page.locator('[data-view="flow"]')).to_contain_text("自动申请")
    expect(page.locator('[data-view="handoff"]')).to_be_hidden()
    page.locator("#workflow-primary").click()
    expect(page.locator("#view-flow")).to_be_visible()
    expect(page.locator("#flow-automation")).to_contain_text("正在生成并检查完整岗位材料")


def test_explicit_handoff_keeps_its_existing_overview_guidance(tmp_path, browser_page):
    from playwright.sync_api import expect

    page = browser_page
    with handoff_portal(tmp_path) as instance:
        application = create_application(instance)
        status, state = post(instance, "prepare", prepare_payload(application))
        assert status == 200, state
        page.goto(instance.origin + "/#overview")
        expect(page.locator("#workflow-state")).to_have_text("等待 Codex 领取")
        expect(page.locator("#workflow-primary")).to_have_attribute("href", "#handoff")
        expect(page.locator('[aria-label="申请主流程"]')).to_contain_text("Codex 领取")
        expect(page.locator('[data-view="handoff"]')).to_be_visible()
        expect(page.locator('[data-view="flow"]')).to_contain_text("单岗位工作台")
        page.locator("#workflow-primary").click()
        expect(page.locator("#view-handoff")).to_be_visible()
        expect(
            page.locator("#handoff-root").get_by_role("heading", name="待 Codex 领取", exact=True)
        ).to_be_visible()


def test_material_preparation_keeps_its_navigation_label(portal, browser_page):
    from playwright.sync_api import expect

    page = browser_page
    page.route(
        "**/api/flow/state",
        lambda route: route.fulfill(
            json={"enabled": True, "mode": "preparation", "tasks": [], "active_task": None}
        ),
    )
    page.goto(portal.origin + "/#flow")
    expect(page.locator("#flow-title")).to_have_text("投递工作台")
    expect(page.locator('[data-view="flow"]')).to_contain_text("材料准备")
    page.locator("#flow-observe").click()
    expect(page.locator('[data-view="flow"]')).to_contain_text("材料准备")
