"""A lost admission response does not block the unrelated current job."""

from copy import deepcopy

import pytest
from test_application_intake import message
from test_application_resume import task_resume as task_resume
from test_automatic_material_editor_browser import serving
from test_bound_material_update import bound_pipeline as bound_pipeline
from test_full_latex_generation import full_latex as full_latex
from test_job_explanation_browser import reveal_control
from test_portal_workflow_browser import browser_page as browser_page

pytestmark = pytest.mark.worker_browser


def test_saved_admission_is_read_back_without_replay_or_current_job_lock(
    bound_pipeline, browser_page
):
    from playwright.sync_api import expect

    server, _store, _calls = bound_pipeline
    pipeline = server.application_pipeline_service
    pipeline.pause()
    before = pipeline.snapshot()
    flow = server.application_flow_service
    tasks_before = deepcopy(flow.snapshot()["tasks"])
    worker_before = deepcopy(server.worker_service.store.load())
    server.application_intake_service.store.import_messages(
        [message("new-recommendation", ["https://www.linkedin.com/jobs/view/987654"])],
        [
            {
                "message_id": "new-recommendation",
                "url": "https://www.linkedin.com/jobs/view/987654",
            }
        ],
    )
    writes = []
    held_readbacks = []
    readbacks_released = False

    def lose_response(route):
        writes.append(route.request.post_data_json)
        response = route.fetch()
        assert response.status == 200, response.text()
        route.abort()

    def hold_readback(route):
        # Keep initial reads live; release post-admission GETs after the unknown-state checks.
        if writes and not readbacks_released:
            held_readbacks.append(route)
        else:
            route.continue_()

    def release_readbacks():
        nonlocal readbacks_released
        readbacks_released = True
        while held_readbacks:
            held_readbacks.pop(0).continue_()

    browser_page.route("**/api/pipeline/admit", lose_response)
    browser_page.route("**/api/pipeline/state", hold_readback)
    with serving(server) as origin:
        try:
            browser_page.goto(origin + "/#flow")
            resume = browser_page.locator("#flow-pipeline-start")
            expect(resume).to_be_enabled()
            expect(resume).to_have_text("继续当前岗位")
            reveal_control(browser_page, "#flow-candidates")
            with browser_page.expect_request(
                lambda request: (
                    bool(writes)
                    and request.method == "GET"
                    and request.url.endswith("/api/pipeline/state")
                )
            ) as readback:
                browser_page.get_by_role("button", name="加入申请队列", exact=True).click(
                    timeout=3000
                )
            expect(browser_page.locator("#flow-notice")).to_contain_text("操作结果尚未核验")
            assert readback.value.method == "GET"
            assert held_readbacks
            expect(resume).to_be_enabled()
            release_readbacks()
            browser_page.locator("#flow-observe").click()
            expect(
                browser_page.get_by_role("button", name="已加入申请队列", exact=True)
            ).to_be_disabled()
            expect(resume).to_be_enabled()
            after = pipeline.snapshot()
            assert after["active_task_id"] == before["active_task_id"]
            assert after["current_recommendation_id"] == before["current_recommendation_id"]
            assert after["control"] == "paused"
            assert len(writes) == 1
            assert after["admission_requests"] == writes
            assert len(after["items"]) == len(before["items"]) + 1
            assert flow.snapshot()["tasks"] == tasks_before
            assert server.worker_service.store.load() == worker_before
        finally:
            release_readbacks()
