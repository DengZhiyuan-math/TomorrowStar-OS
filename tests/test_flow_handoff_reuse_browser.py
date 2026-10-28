"""A fresh form attempt reuses the current job's real saved material archive."""

import base64
import hashlib

import pytest
from test_application_handoff import act
from test_application_resume import task_resume as task_resume
from test_automatic_material_editor_browser import serving
from test_automatic_material_reuse_edit import complete_portal as complete_portal
from test_full_latex_generation import full_latex as base_full_latex  # noqa: F401
from test_portal_workflow_browser import browser_page as browser_page

from career_evidence_graph.application_handoff import CodexHandoffService

pytestmark = pytest.mark.worker_browser


@pytest.fixture
def full_latex(base_full_latex):  # noqa: F811
    store, application, *remaining = base_full_latex
    application = store.applications.update_application(
        application["id"], {"application_strategy": "manual"}, application["revision"]
    )
    return store, application, *remaining


@pytest.fixture
def retained_handoff(complete_portal, tmp_path):
    server, store, task, generations = complete_portal
    flow = server.application_flow_service
    # The test's injected ResumeStore must share the native factory's lock instance.
    assert store.applications.root == flow.applications.root
    store.applications = flow.applications
    application = flow.applications.get_application(task["application_id"])
    raw = store.pdf(task["resume_id"])
    service = CodexHandoffService(flow.applications, tmp_path / "retained-handoff")
    old = service.request(
        "prepare",
        {
            "application_id": application["id"],
            "revision": application["revision"],
            "country": "CHE",
            "filename": "saved.pdf",
            "file_base64": base64.b64encode(raw).decode(),
            "acknowledge": True,
        },
    )["active_task"]
    reply = act(service, old, "claim", owner="previous-synthetic-executor")
    old = act(
        service,
        reply["active_task"],
        "readback",
        claim_token=reply["claim_token"],
        result="ready",
        page_url=application["url"],
        source="Previous synthetic original-page observation",
        fields=[
            {"question": "Full name", "value": "Synthetic Person"},
            {"question": "Motivation", "value": "Keep my manual wording."},
        ],
        attachment={"filename": "saved.pdf", "sha256": hashlib.sha256(raw).hexdigest()},
        missing=[],
    )["active_task"]
    flow.attach_existing_handoff(
        task["id"], task["revision"], str(service.root), old["id"], old["revision"]
    )
    return server, store, task, service, old, generations


@pytest.mark.parametrize(
    "complete_portal", [{"preparation_only": True, "information_library": True}], indirect=True
)
def test_new_page_action_keeps_flow_pdf_and_manual_values_without_material_replay(
    retained_handoff, browser_page
):
    from playwright.sync_api import expect

    server, store, task, service, old, generations = retained_handoff
    before_calls = len(generations)
    before_compiles = len(store.prism_client.calls)
    before_pdf = store.pdf(task["resume_id"])
    page = browser_page
    writes = []
    page.on(
        "request",
        lambda request: (
            writes.append(request.url) if request.method not in {"GET", "HEAD", "OPTIONS"} else None
        ),
    )
    with serving(server) as origin:
        page.goto(origin + "/#flow")
        page.get_by_role("button", name="重新识别并使用现有材料", exact=True).click()
        panel = page.locator("#flow-current-handoff")
        expect(panel).to_contain_text("本次新页尚未完成填写")
        expect(panel.get_by_role("button", name="复制本次填写任务", exact=True)).to_be_visible()
        expect(page.locator("#flow-pdf-link")).to_have_attribute(
            "href", f"/api/flow/resumes/{task['resume_id']}/pdf"
        )
        current = server.application_flow_service.snapshot()["active_task"]
        successor = service.snapshot()["active_task"]
        assert current["id"] == task["id"] and current["resume_id"] == task["resume_id"]
        assert successor["id"] != old["id"]
        assert successor["status"] == "prepared" and successor["readbacks"] == []
        assert successor["claim"] is None
        assert "Keep my manual wording." in successor["prompt"]
        assert service.snapshot()["tasks"][0]["readbacks"] == old["readbacks"]
        page.reload()
        expect(panel).to_contain_text("本次新页尚未完成填写")
        assert service.snapshot()["active_task"]["id"] == successor["id"]
    assert len(writes) == 1 and writes[0].endswith("/api/flow/restart-existing-handoff")
    assert len(generations) == before_calls and len(store.prism_client.calls) == before_compiles
    assert store.pdf(task["resume_id"]) == before_pdf


@pytest.mark.parametrize(
    "complete_portal", [{"preparation_only": True, "information_library": True}], indirect=True
)
def test_only_the_fresh_readback_can_mark_the_current_attempt_ready(retained_handoff, browser_page):
    from playwright.sync_api import expect

    server, store, task, service, old, generations = retained_handoff
    page = browser_page
    with serving(server) as origin:
        page.goto(origin + "/#flow")
        page.get_by_role("button", name="重新识别并使用现有材料", exact=True).click()
        panel = page.locator("#flow-current-handoff")
        expect(panel).to_contain_text("本次新页尚未完成填写")
        assert page.locator("#flow-existing-handoff").count() == 0
        successor = service.snapshot()["active_task"]
        reply = act(service, successor, "claim", owner="current-synthetic-executor")
        current = act(
            service,
            reply["active_task"],
            "readback",
            claim_token=reply["claim_token"],
            result="ready",
            page_url=old["job_url"],
            source="Fresh synthetic page observation after its actual attachment readback",
            fields=[{"question": "Motivation", "value": "Keep my manual wording."}],
            attachment={"filename": "saved.pdf", "sha256": successor["file_sha256"]},
            missing=[],
        )["active_task"]
        parent_before = server.application_flow_service.path.read_bytes()
        child_before = service.path.read_bytes()
        page.get_by_role("button", name="读取最新状态", exact=True).click()
        expect(panel).to_contain_text("执行者已核验本次字段与附件")
        expect(panel).to_contain_text("最终 Submit 由你手动完成")
        page.reload()
        expect(panel).to_contain_text("执行者已核验本次字段与附件")
        assert service.path.read_bytes() == child_before
        assert server.application_flow_service.path.read_bytes() == parent_before
        projected = server.application_flow_service.snapshot()["active_task"]
        assert projected["id"] == task["id"] and projected["resume_id"] == task["resume_id"]
        assert projected["codex_handoff_ref"]["task_id"] == current["id"] != old["id"]
        assert len(generations) == 1 and len(store.prism_client.calls) == 1


@pytest.mark.parametrize(
    "complete_portal", [{"preparation_only": True, "information_library": True}], indirect=True
)
def test_unknown_fresh_attempt_does_not_offer_another_restart(retained_handoff, browser_page):
    from playwright.sync_api import expect

    server, _, _, service, old, _ = retained_handoff
    page = browser_page
    with serving(server) as origin:
        page.goto(origin + "/#flow")
        page.get_by_role("button", name="重新识别并使用现有材料", exact=True).click()
        panel = page.locator("#flow-current-handoff")
        expect(panel).to_contain_text("本次新页尚未完成填写")
        successor = service.snapshot()["active_task"]
        reply = act(service, successor, "claim", owner="current-synthetic-executor")
        act(
            service,
            reply["active_task"],
            "readback",
            claim_token=reply["claim_token"],
            result="unknown",
            page_url=old["job_url"],
            source="Synthetic attachment result could not be verified",
            fields=[{"question": "Full name", "value": "Synthetic Person"}],
            attachment=None,
            missing=["Resume attachment"],
        )
        page.get_by_role("button", name="读取最新状态", exact=True).click()
        expect(panel).to_contain_text("本次结果仍需核验")
        expect(panel).to_contain_text("不重复未知动作")
        expect(panel.get_by_role("button", name="重新识别并使用现有材料")).to_have_count(0)
        assert len(service.snapshot()["tasks"]) == 2


@pytest.mark.parametrize(
    "complete_portal", [{"preparation_only": True, "information_library": True}], indirect=True
)
def test_saved_new_attempt_is_recognized_after_a_lost_http_response(retained_handoff, browser_page):
    from playwright.sync_api import expect

    server, _, _, service, _, _ = retained_handoff
    page = browser_page
    requests = []

    def lose_reply(route):
        response = route.fetch()
        assert response.status == 200
        requests.append(route.request.post_data_json)
        route.fulfill(status=503, json={"message": "Synthetic lost response"})

    with serving(server) as origin:
        page.route("**/api/flow/restart-existing-handoff", lose_reply)
        page.goto(origin + "/#flow")
        page.get_by_role("button", name="重新识别并使用现有材料", exact=True).click()
        panel = page.locator("#flow-current-handoff")
        expect(panel).to_contain_text("本次新页尚未完成填写")
        identifier = service.snapshot()["active_task"]["id"]
        observe = page.get_by_role("button", name="读取最新状态", exact=True)
        observe.click()
        expect(page.locator("#flow-notice")).to_have_text(
            "已读取持久状态。操作是否完成，以当前岗位和任务记录为准。"
        )
        expect(observe).to_be_enabled()
        expect(page.locator("#flow-root")).to_have_attribute("aria-busy", "false")
        page.reload()
        expect(panel).to_contain_text("本次新页尚未完成填写")
        assert len(requests) == 1
        assert len(service.snapshot()["tasks"]) == 2
        assert service.snapshot()["active_task"]["id"] == identifier
