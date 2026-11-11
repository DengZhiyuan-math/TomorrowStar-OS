"""Opt-in synthetic loopback UI journeys; no ATS, models, or native Cua."""

from __future__ import annotations

import json
from urllib.parse import urlsplit

import pytest
from test_handoff_http import (
    PDF,
    SHA,
    URL,
    create_application,
    handoff_portal,
    needs_input_task,
    post,
)

pytestmark = pytest.mark.worker_browser


@pytest.mark.parametrize("receipt", ["http-error", "invalid-json", "missing-state"])
def test_handoff_ui_recovers_lost_readback_receipt_and_finishes_manual_records(
    tmp_path, monkeypatch, receipt
):
    from playwright.sync_api import expect, sync_playwright

    monkeypatch.setenv("PLAYWRIGHT_BROWSERS_PATH", "0")
    with handoff_portal(tmp_path) as portal:
        app = create_application(portal)
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True, channel="chromium")
            try:
                context = browser.new_context()
                external = []

                def local_only(route):
                    if urlsplit(route.request.url).hostname not in {"127.0.0.1", "localhost"}:
                        external.append(route.request.url)
                        route.abort()
                    else:
                        route.continue_()

                context.route("**/*", local_only)
                page = context.new_page()
                errors = []
                page.on("pageerror", lambda error: errors.append(str(error)))
                page.goto(portal.origin + "/#handoff")
                root = page.locator("#handoff-root")
                expect(root.get_by_role("button", name="冻结资料并准备交接")).to_be_visible()
                root.get_by_label("已保存岗位", exact=True).select_option(app["id"])
                root.get_by_label("已人工复核的简历 PDF", exact=True).set_input_files(
                    {"name": "approved.pdf", "mimeType": "application/pdf", "buffer": PDF}
                )
                root.get_by_role("checkbox").check()
                root.get_by_role("button", name="冻结资料并准备交接").click()
                expect(
                    root.get_by_role("heading", name="待 Codex 领取", exact=True)
                ).to_be_visible()
                status, _, raw = portal.request("GET", "/api/handoff/state")
                assert status == 200
                task = json.loads(raw)["active_task"]
                status, state = post(
                    portal,
                    "claim",
                    {
                        "task_id": task["id"],
                        "task_revision": task["revision"],
                        "owner": "synthetic-codex",
                    },
                )
                assert status == 200, state
                task, token = state["active_task"], state["claim_token"]
                root.get_by_role("button", name="刷新交接记录").click()
                expect(root.get_by_role("heading", name="Codex 操作中", exact=True)).to_be_visible()
                payload = {
                    "claim_token": token,
                    "result": "ready",
                    "page_url": URL,
                    "source": "Synthetic loopback readback screenshot",
                    "fields": [{"question": "Full name", "value": "Synthetic Person"}],
                    "attachment": {"filename": "approved.pdf", "sha256": SHA},
                    "missing": [],
                }
                root.get_by_text("手动导入 Codex 回读", exact=True).click()
                readback = root.get_by_label("Codex 回读 JSON（包含 claim_token）", exact=True)
                readback.fill(json.dumps(payload))

                def lose_saved_receipt(route):
                    response = route.fetch()
                    assert response.status == 200
                    if receipt == "http-error":
                        route.fulfill(status=503, json={"message": "Synthetic lost save receipt"})
                    elif receipt == "invalid-json":
                        route.fulfill(status=200, body="{", content_type="application/json")
                    else:
                        route.fulfill(status=200, json={"synthetic": "missing saved state"})

                page.route("**/api/handoff/readback", lose_saved_receipt)
                root.get_by_role("button", name="保存回读证据", exact=True).click()
                expect(root.get_by_role("status")).to_contain_text("操作结果尚未核验")
                expect(readback).to_have_value(json.dumps(payload))
                expect(root.get_by_role("button", name="保存回读证据", exact=True)).to_be_disabled()
                assert portal.state()["applications"][0]["status"] == "drafting"
                page.screenshot(path=str(tmp_path / "lost-readback-receipt.png"), full_page=True)
                page.unroute("**/api/handoff/readback", lose_saved_receipt)
                root.get_by_role("button", name="刷新交接记录").click()
                page.locator("#confirmation-continue").click()
                expect(root.get_by_role("heading", name="等待你复核", exact=True)).to_be_visible()
                assert portal.state()["applications"][0]["status"] == "drafting"
                for action, expected in [
                    ("review", "已复核，等待你在原页面提交"),
                    ("submitted", "你已确认提交，等待回执"),
                    ("receipt", "回执已记录"),
                ]:
                    root.get_by_label("人工操作", exact=True).select_option(action)
                    root.get_by_label("核验来源（页面、截图或本地证据路径）", exact=True).fill(
                        "Synthetic human observation"
                    )
                    if action == "receipt":
                        root.get_by_label("回执位置或编号", exact=True).fill("Synthetic receipt-42")
                    root.get_by_role("checkbox").check()
                    root.get_by_role("button", name="保存人工确认", exact=True).click()
                    expect(root.get_by_role("heading", name=expected, exact=True)).to_be_visible()
                assert portal.state()["applications"][0]["status"] == "confirmation_received"
                page.reload()
                expect(root.get_by_role("heading", name="回执已记录", exact=True)).to_be_visible()
                page.screenshot(path=str(tmp_path / "confirmed-handoff.png"), full_page=True)
                assert not external
                assert not errors
            finally:
                browser.close()


def test_dirty_application_cannot_prepare_stale_handoff(tmp_path, monkeypatch):
    from playwright.sync_api import expect, sync_playwright

    monkeypatch.setenv("PLAYWRIGHT_BROWSERS_PATH", "0")
    with handoff_portal(tmp_path) as portal:
        create_application(portal)
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True, channel="chromium")
            try:
                page = browser.new_page()
                page.route(
                    "**/*",
                    lambda route: (
                        route.continue_()
                        if urlsplit(route.request.url).hostname == "127.0.0.1"
                        else route.abort()
                    ),
                )
                page.goto(portal.origin + "/#applications")
                page.get_by_role("button", name="查看 Synthetic Engineer", exact=True).click()
                dialog = page.locator("#application-dialog")
                dialog.locator("#application-corrections > summary").click()
                dialog.locator('[name="role_title"]').fill("Unsaved changed role")
                dialog.get_by_role("button", name="进入持久 Codex 交接 →", exact=True).click()
                expect(dialog.locator("#automation-notice")).to_contain_text("请先保存岗位修改")
                expect(dialog).to_be_visible()
                status, _, raw = portal.request("GET", "/api/handoff/state")
                assert status == 200
                assert json.loads(raw)["tasks"] == []
            finally:
                browser.close()


def test_task_switch_requires_explicit_discard_and_keeps_task_binding(tmp_path, monkeypatch):
    from playwright.sync_api import expect, sync_playwright
    from test_handoff_http import prepare_payload

    monkeypatch.setenv("PLAYWRIGHT_BROWSERS_PATH", "0")
    with handoff_portal(tmp_path) as portal:
        app = create_application(portal)
        status, state = post(portal, "prepare", prepare_payload(app))
        assert status == 200, state
        previous = state["active_task"]
        status, state = post(
            portal,
            "release",
            {
                "task_id": previous["id"],
                "task_revision": previous["revision"],
                "acknowledge": True,
                "source": "No page started; previous executor stopped",
            },
        )
        assert status == 200, state
        status, state = post(portal, "prepare", prepare_payload(app))
        assert status == 200, state
        current = state["active_task"]
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True, channel="chromium")
            try:
                page = browser.new_page()
                page.route(
                    "**/*",
                    lambda route: (
                        route.continue_()
                        if urlsplit(route.request.url).hostname == "127.0.0.1"
                        else route.abort()
                    ),
                )
                page.goto(portal.origin + "/#handoff")
                root = page.locator("#handoff-root")
                source = root.get_by_label("核验来源（页面、截图或本地证据路径）", exact=True)
                source.fill("Unsaved evidence for the current task")
                selector = root.get_by_label("查看交接任务", exact=True)
                selector.select_option(previous["id"])
                confirmation = page.locator("#confirmation-dialog")
                expect(confirmation).to_be_visible()
                confirmation.get_by_role("button", name="保留输入", exact=True).click()
                expect(selector).to_have_value(current["id"])
                expect(source).to_have_value("Unsaved evidence for the current task")
                selector.select_option(previous["id"])
                page.locator("#confirmation-continue").click()
                expect(root.get_by_role("heading", name="已停止", exact=True)).to_be_visible()
                expect(
                    root.get_by_label("核验来源（页面、截图或本地证据路径）", exact=True)
                ).to_have_count(0)
                status, _, raw = portal.request("GET", "/api/handoff/state")
                assert status == 200
                assert json.loads(raw)["active_task"]["id"] == current["id"]
                assert json.loads(raw)["active_task"]["status"] == "prepared"
            finally:
                browser.close()


@pytest.mark.parametrize("status", ["submitted", "confirmed", "cancelled"])
def test_release_recovery_routes_submitted_tasks_through_note_sync(tmp_path, monkeypatch, status):
    from playwright.sync_api import expect, sync_playwright
    from test_handoff_http import prepare_payload

    monkeypatch.setenv("PLAYWRIGHT_BROWSERS_PATH", "0")
    with handoff_portal(tmp_path) as portal:
        app = create_application(portal)
        code, snapshot = post(portal, "prepare", prepare_payload(app))
        assert code == 200, snapshot
        task = snapshot["tasks"][0]
        task.update(
            status=status,
            release_pending=True,
            pending_sync=None if status == "cancelled" else {"status": "applied"},
        )
        snapshot["active_task"] = task
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True, channel="chromium")
            try:
                page = browser.new_page()
                page.route(
                    "**/*",
                    lambda route: (
                        route.continue_()
                        if urlsplit(route.request.url).hostname == "127.0.0.1"
                        else route.abort()
                    ),
                )
                page.route("**/api/handoff/state", lambda route: route.fulfill(json=snapshot))
                page.goto(portal.origin + "/#handoff")
                root = page.locator("#handoff-root")
                if status == "cancelled":
                    expect(root.get_by_label("人工操作", exact=True)).to_have_value("release")
                    expect(root.get_by_role("option", name="核验并完成操作权释放")).to_have_count(1)
                    expect(root.get_by_role("button", name="核对并重试同步")).to_have_count(0)
                else:
                    expect(root.get_by_role("button", name="核对并重试同步")).to_be_visible()
                    expect(root.get_by_label("人工操作", exact=True)).to_have_count(0)
                    expect(
                        root.get_by_label("保留原笔记，结束此次同步（已核验）", exact=True)
                    ).to_be_visible()
            finally:
                browser.close()


def test_needs_input_answer_is_saved_before_human_resolution(tmp_path, monkeypatch):
    from playwright.sync_api import expect, sync_playwright

    monkeypatch.setenv("PLAYWRIGHT_BROWSERS_PATH", "0")
    with handoff_portal(tmp_path) as portal:
        app, task, token = needs_input_task(portal)
        initial_readback = task["readbacks"][0]
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True, channel="chromium")
            try:
                page = browser.new_page()
                page.route(
                    "**/*",
                    lambda route: (
                        route.continue_()
                        if urlsplit(route.request.url).hostname == "127.0.0.1"
                        else route.abort()
                    ),
                )
                page.goto(portal.origin + "/#handoff")
                root = page.locator("#handoff-root")
                expect(
                    root.get_by_role("heading", name="等待已确认答案", exact=True)
                ).to_be_visible()
                root.get_by_label("网站问题", exact=True).fill("Notice period")
                root.get_by_label("已确认答案", exact=True).fill("One month")
                root.get_by_label("我确认答案准确，仅限此岗位。", exact=True).check()
                root.get_by_role("button", name="保存答案", exact=True).click()
                expect(
                    root.get_by_role("heading", name="结果未知，先核验原页面", exact=True)
                ).to_be_visible()
                status, _, raw = portal.request("GET", "/api/handoff/state")
                assert status == 200
                saved = json.loads(raw)
                assert saved["active_task"]["status"] == "needs_recheck"
                assert saved["active_task"]["reason"] == "answer_changed"
                assert saved["active_task"]["readbacks"][0] == initial_readback
                answer = next(item for item in saved["library"] if item["value"] == "One month")
                assert answer["scope"] == {"application_id": app["id"]}
                assert answer["state"] == "confirmed"
                page.screenshot(
                    path=str(tmp_path / "answer-saved-needs-recheck.png"), full_page=True
                )
                root.get_by_label("人工操作", exact=True).select_option("resolve")
                root.get_by_label("核验来源（页面、截图或本地证据路径）", exact=True).fill(
                    "Synthetic human checked original form after adopting answer"
                )
                root.get_by_label("未知结果核验结论", exact=True).select_option("current_matches")
                root.get_by_label(
                    "我已亲自核验；如释放任务，我已停止操作并处置原页面。"
                    "此按钮只保存记录，不会点击招聘网站 Submit。",
                    exact=True,
                ).check()
                root.get_by_role("button", name="保存人工确认", exact=True).click()
                expect(root.get_by_role("heading", name="Codex 操作中", exact=True)).to_be_visible()
                payload = {
                    "claim_token": token,
                    "result": "ready",
                    "page_url": URL,
                    "source": "Synthetic second complete field readback",
                    "fields": [
                        {"question": "Full name", "value": "Synthetic Person"},
                        {"question": "Notice period", "value": "One month"},
                    ],
                    "attachment": {"filename": "approved.pdf", "sha256": SHA},
                    "missing": [],
                }
                root.get_by_text("手动导入 Codex 回读", exact=True).click()
                root.get_by_label("Codex 回读 JSON（包含 claim_token）", exact=True).fill(
                    json.dumps(payload)
                )
                root.get_by_role("button", name="保存回读证据", exact=True).click()
                expect(root.get_by_role("heading", name="等待你复核", exact=True)).to_be_visible()
                status, _, raw = portal.request("GET", "/api/handoff/state")
                assert status == 200
                saved = json.loads(raw)["active_task"]
                assert saved["readbacks"][0] == initial_readback
                assert len(saved["readbacks"]) == 2
                assert any(answer["value"] == "One month" for answer in saved["answers"])
                assert portal.state()["applications"][0]["status"] == "drafting"
                page.screenshot(
                    path=str(tmp_path / "answer-resolved-ready-for-review.png"), full_page=True
                )
            finally:
                browser.close()
