"""Default loopback entry keeps mailbox checkpoints separate from job work."""

from threading import Thread

import pytest
from test_application_intake import message, ready
from test_career_portal_http import _running_portal
from test_career_portal_http import portal as portal
from test_portal_workflow_browser import browser_page as browser_page
from test_worker_backend_recovery import backend as backend

from career_evidence_graph.application_intake import ApplicationIntakeService

pytestmark = pytest.mark.worker_browser


def test_mail_progress_polling_preserves_current_unsaved_answer(backend, browser_page):
    from playwright.sync_api import expect

    owner, _, runner, _ = backend
    state = runner.store.load()
    state["control"] = "paused"
    state["jobs"][0].update(
        status="needs_input", questions=[{"id": "start", "question": "Start date", "options": []}]
    )
    runner.store.save(state)
    policy = owner.application_pipeline_service._load()
    policy.update(control="paused", status="needs_input")
    owner.application_pipeline_service._save(policy)
    intake = owner.application_intake_service.snapshot()
    intake["progress"].update(
        mail_captured=9,
        mail_labeled=7,
        mail_archived=4,
        mail_needs_recheck=2,
        mail_label_configured=True,
        source_complete=3,
        source_failed=5,
        source_needs_recheck=1,
    )
    page = browser_page
    writes = []
    page.on(
        "request", lambda request: writes.append(request.url) if request.method == "POST" else None
    )
    page.route("**/api/recommendations/state", lambda route: route.fulfill(json=intake))
    page.clock.install()
    thread = Thread(target=owner.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True)
    thread.start()
    try:
        page.goto(f"http://127.0.0.1:{owner.server_port}/#flow")
        expect(page.locator("#flow-title")).to_have_text("自动申请")
        progress = page.locator("#flow-mail-progress")
        expect(progress).to_contain_text("邮件处理：本地收录 9 · 已标记 7 · 已归档 4 · 待核对 2")
        expect(progress).to_contain_text("岗位来源：已完成 3 · 失败 5 · 待核验 1")
        answer = page.get_by_label("Start date · 补充信息")
        answer.fill("2026-11-01")
        intake["progress"].update(mail_captured=10, mail_needs_recheck=3)
        with page.expect_response("**/api/recommendations/state"):
            page.clock.fast_forward(1500)
        expect(progress).to_contain_text("邮件处理：本地收录 10 · 已标记 7 · 已归档 4 · 待核对 3")
        expect(answer).to_be_focused()
        expect(answer).to_have_value("2026-11-01")
        expect(page.locator("#flow-automation")).to_contain_text("需要补充信息")
        assert not writes
        assert not runner.store.library()
        assert runner.store.load()["control"] == "paused"
        assert (
            owner.application_pipeline_service.snapshot()["active_task_id"]
            == policy["active_task_id"]
        )
    finally:
        owner.shutdown()
        thread.join(3)


@pytest.mark.parametrize("processing_error", ["", "gmail_processing_invalid"])
def test_default_entry_explains_disabled_mail_processing_locally(
    portal, tmp_path, browser_page, processing_error
):
    from playwright.sync_api import expect

    page = browser_page
    writes = []
    page.on(
        "request", lambda request: writes.append(request.url) if request.method == "POST" else None
    )
    with _running_portal(
        portal.applications, portal.career, flow_root=tmp_path / "flow"
    ) as instance:
        intake = instance.server.application_intake_service.snapshot()
        intake["progress"]["mail_processing_error"] = processing_error
        page.route("**/api/recommendations/state", lambda route: route.fulfill(json=intake))
        page.goto(instance.origin + "/#flow")
        progress = page.locator("#flow-mail-progress")
        expect(progress).to_contain_text("邮件处理：本地收录 0 · 已标记 0 · 已归档 0 · 待核对 0")
        if processing_error:
            expect(progress.locator(".flow-error")).to_contain_text("邮件处理标签配置无效")
            expect(progress).to_contain_text("仍可收录推荐；未执行标记或归档")
        else:
            expect(progress).to_contain_text("未配置邮件处理标签；仍可收录推荐，不执行标记或归档")
            expect(progress.locator(".flow-error")).to_have_count(0)
        expect(page.locator("#flow-refresh-mail")).to_be_enabled()
        expect(page.locator("#flow-notice")).to_be_hidden()
        page.reload()
        expect(progress).to_contain_text("本地收录 0")
        assert not writes
        assert instance.server.application_flow_service.snapshot()["tasks"] == []


def test_unknown_mailbox_result_is_visible_without_polling_redispatch(
    portal, tmp_path, browser_page
):
    from playwright.sync_api import expect

    calls, external = [], {"labeled": False, "archived": False}

    def mailbox(_directory, *, operation, **_options):
        calls.append(operation)
        if operation == "label":
            external["labeled"] = True
        if operation == "archive":
            external["archived"] = True
            raise TimeoutError("Synthetic archive response lost")
        return {"status": "complete", **external}

    def factory(applications, root):
        return ApplicationIntakeService(
            applications,
            root,
            processed_label="Synthetic Jobs",
            reader=lambda *_a, **_k: {
                "status": "readable",
                "emails": [message()],
                "provenance": {},
            },
            mailbox=mailbox,
            fetcher=lambda *_: pytest.fail("Capture must not acquire a JD"),
            extractor=lambda *_: pytest.fail("Capture must not analyze a job"),
        )

    page = browser_page
    with _running_portal(
        portal.applications,
        portal.career,
        flow_root=tmp_path / "flow",
        flow_intake_factory=factory,
    ) as instance:
        service = instance.server.application_intake_service
        service.refresh(capture_only=True)
        captured = ready(service)
        assert captured["progress"]["mail_needs_recheck"] == 1
        before = calls.copy()
        writes = []
        page.on(
            "request",
            lambda request: writes.append(request.url) if request.method == "POST" else None,
        )
        page.clock.install()
        page.goto(instance.origin + "/#flow")
        progress = page.locator("#flow-mail-progress")
        expect(progress).to_contain_text("邮件处理：本地收录 1 · 已标记 1 · 已归档 0 · 待核对 1")
        expect(progress).to_contain_text("邮件处理结果待核对；核对前不会重复标记或归档")
        expect(progress).to_contain_text("岗位来源：已完成 0 · 失败 0 · 待核验 0")
        with page.expect_response("**/api/recommendations/state"):
            page.clock.fast_forward(1500)
        expect(progress).to_contain_text("已归档 0 · 待核对 1")
        assert calls == before
        assert not writes
        assert instance.server.application_flow_service.snapshot()["tasks"] == []
