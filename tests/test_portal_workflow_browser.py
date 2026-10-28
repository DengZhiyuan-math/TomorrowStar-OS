"""Synthetic loopback journeys for the overview's persistent handoff guidance."""

from __future__ import annotations

from urllib.parse import urlsplit

import pytest
from test_career_portal_http import portal as portal
from test_handoff_http import (
    SHA,
    URL,
    create_application,
    handoff_portal,
    post,
    prepare_payload,
)

from career_evidence_graph.career_portal_data import ApplicationStore

pytestmark = pytest.mark.worker_browser


def ready_readback(token):
    return {
        "claim_token": token,
        "result": "ready",
        "page_url": URL,
        "source": "Synthetic loopback screenshot",
        "fields": [{"question": "Full name", "value": "Synthetic Person"}],
        "attachment": {"filename": "approved.pdf", "sha256": SHA},
        "missing": [],
    }


@pytest.fixture
def browser_page(monkeypatch):
    from playwright.sync_api import sync_playwright

    monkeypatch.setenv("PLAYWRIGHT_BROWSERS_PATH", "0")
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True, channel="chromium")
        try:
            context = browser.new_context()
            external, errors = [], []

            def local_only(route):
                target = urlsplit(route.request.url)
                builtin_pdf = (
                    target.scheme == "chrome-extension"
                    and target.netloc == "mhjfbmdgcfjbbpaeojofohoefgiehjai"
                ) or (target.scheme == "chrome" and target.netloc == "resources")
                if target.hostname not in {"127.0.0.1", "localhost"} and not builtin_pdf:
                    external.append(route.request.url)
                    route.abort()
                else:
                    route.continue_()

            context.route("**/*", local_only)
            page = context.new_page()
            page.on("pageerror", lambda error: errors.append(str(error)))
            yield page
            assert not external
            assert not errors
        finally:
            browser.close()


def test_overview_tracks_persisted_handoff_until_manual_submission(tmp_path, browser_page):
    from playwright.sync_api import expect

    page = browser_page
    with handoff_portal(tmp_path) as instance:
        app = create_application(instance)
        page.goto(instance.origin + "/#overview")
        expect(page.locator("#workflow-state")).to_have_text("可以准备下一份申请")
        expect(page.locator('[data-workflow-step="0"]')).to_have_attribute("aria-current", "step")
        status, state = post(instance, "prepare", prepare_payload(app))
        assert status == 200, state
        task = state["active_task"]

        def refresh_and_check(label, action, step, title="Synthetic · Engineer"):
            page.locator("#refresh-button").click()
            expect(page.locator("#workflow-state")).to_have_text(label)
            expect(page.locator("#workflow-title")).to_have_text(title)
            expect(page.locator("#workflow-primary")).to_contain_text(action)
            expect(page.locator("#workflow-primary")).to_have_attribute("href", "#handoff")
            expect(page.locator("[data-workflow-step][aria-current=step]")).to_have_attribute(
                "data-workflow-step", str(step)
            )
            expect(page.locator("[data-workflow-step].is-complete")).to_have_count(step)

        refresh_and_check("等待 Codex 领取", "复制领取任务，交给 Codex", 1)
        page.locator("#workflow-primary").click()
        expect(page.locator("#view-handoff")).to_be_visible()
        expect(
            page.locator("#handoff-root").get_by_role("heading", name="待 Codex 领取", exact=True)
        ).to_be_visible()
        page.locator('[data-view="overview"]').click()

        status, state = post(
            instance,
            "claim",
            {
                "task_id": task["id"],
                "task_revision": task["revision"],
                "owner": "synthetic-codex",
            },
        )
        assert status == 200, state
        task, token = state["active_task"], state["claim_token"]
        refresh_and_check("Codex 操作中", "等待 Codex 保存回读", 2)
        status, state = post(
            instance,
            "readback",
            {
                "task_id": task["id"],
                "task_revision": task["revision"],
                **ready_readback(token),
            },
        )
        assert status == 200, state
        task = state["active_task"]
        refresh_and_check("等待你复核", "核对页面字段与批准附件", 3)
        assert instance.state()["applications"][0]["status"] == "drafting"
        for action, label, instruction, step in [
            ("review", "等待你手动提交", "在原页面提交后，回来记录", 3),
            ("submitted", "1 份申请待补回执", "查看交接与回执", 4),
        ]:
            status, state = post(
                instance,
                action,
                {
                    "task_id": task["id"],
                    "task_revision": task["revision"],
                    "acknowledge": True,
                    "source": "Synthetic human observation",
                },
            )
            assert status == 200, state
            task = next(item for item in state["tasks"] if item["id"] == task["id"])
            refresh_and_check(
                label,
                instruction,
                step,
                "提交之后，留下接收来源。" if action == "submitted" else "Synthetic · Engineer",
            )
        assert instance.state()["applications"][0]["status"] == "applied"


def test_job_handoff_keeps_new_preparation_while_overview_opens_historical_receipt(
    tmp_path, browser_page
):
    from playwright.sync_api import expect

    page = browser_page
    with handoff_portal(tmp_path) as instance:
        original = create_application(instance)
        status, state = post(instance, "prepare", prepare_payload(original))
        assert status == 200, state
        task = state["active_task"]
        status, state = post(
            instance,
            "claim",
            {
                "task_id": task["id"],
                "task_revision": task["revision"],
                "owner": "synthetic-codex",
            },
        )
        assert status == 200, state
        for action, evidence in [
            ("readback", ready_readback(state["claim_token"])),
            ("review", {"acknowledge": True, "source": "Synthetic human review"}),
            ("submitted", {"acknowledge": True, "source": "Synthetic human submission"}),
        ]:
            task = state["active_task"]
            status, state = post(
                instance,
                action,
                {"task_id": task["id"], "task_revision": task["revision"], **evidence},
            )
            assert status == 200, state
        historical = state["tasks"][0]
        assert historical["status"] == "submitted"
        assert state["active_task"] is None

        page.goto(instance.origin + "/#applications")
        new_app = ApplicationStore(instance.applications).create_application(
            {"company": "Next Synthetic", "role_title": "Engineer"}
        )
        page.reload()
        dialog = page.locator("#application-dialog")
        page.get_by_role("button", name="查看 Next Synthetic Engineer", exact=True).click()
        dialog.locator("#application-corrections > summary").click()
        dialog.locator("#open-codex-handoff").click()
        root = page.locator("#handoff-root")
        expect(page.locator("#view-handoff")).to_be_visible()
        expect(root.get_by_role("heading", name="准备单岗位任务", exact=True)).to_be_visible()
        expect(root.get_by_label("查看交接任务", exact=True)).to_have_value("")
        expect(root.get_by_label("已保存岗位", exact=True)).to_have_value(new_app["id"])

        page.locator('[data-view="overview"]').click()
        expect(page.locator("#workflow-state")).to_have_text("1 份申请待补回执")
        page.locator("#workflow-primary").click()
        expect(root.get_by_label("查看交接任务", exact=True)).to_have_value(historical["id"])
        expect(
            root.get_by_role("heading", name="你已确认提交，等待回执", exact=True)
        ).to_be_visible()
        expect(root.get_by_label("人工操作", exact=True)).to_have_value("receipt")


@pytest.mark.parametrize("response", ["http-error", "invalid-state"])
def test_overview_discards_progress_when_handoff_readback_is_unverified(
    tmp_path, browser_page, response
):
    from playwright.sync_api import expect

    page = browser_page
    with handoff_portal(tmp_path) as instance:
        app = create_application(instance)
        status, state = post(instance, "prepare", prepare_payload(app))
        assert status == 200, state
        page.goto(instance.origin + "/#overview")
        expect(page.locator("#workflow-state")).to_have_text("等待 Codex 领取")
        expect(page.locator("[data-workflow-step].is-complete")).to_have_count(1)

        def fail_readback(route):
            if response == "http-error":
                route.fulfill(status=503, json={"message": "Synthetic unavailable state"})
            else:
                route.fulfill(json={"enabled": True, "tasks": []})

        page.route("**/api/handoff/state", fail_readback)
        page.locator("#refresh-button").click()
        expect(page.locator("#workflow-state")).to_have_text("交接状态待核验")
        expect(page.locator("#workflow-primary")).to_contain_text("核对交接记录")
        expect(page.locator("[data-workflow-step].is-complete")).to_have_count(0)
        expect(page.locator("[data-workflow-step][aria-current=step]")).to_have_count(0)
        page.locator("#workflow-primary").click()
        expect(page.locator("#view-handoff")).to_be_visible()
        expect(
            page.locator("#handoff-root").get_by_role("button", name="保存人工确认", exact=True)
        ).to_be_disabled()
        page.unroute("**/api/handoff/state", fail_readback)
        page.locator("#handoff-root").get_by_role("button", name="刷新交接记录").click()
        page.locator('[data-view="overview"]').click()
        expect(page.locator("#workflow-state")).to_have_text("等待 Codex 领取")
        expect(page.locator("[data-workflow-step].is-complete")).to_have_count(1)


def test_disabled_handoff_guides_connection_without_claiming_an_empty_queue(portal, browser_page):
    from playwright.sync_api import expect

    create_application(portal)
    page = browser_page
    page.goto(portal.origin + "/#overview")
    expect(page.locator("#workflow-state")).to_have_text("交接尚未连接")
    expect(page.locator("#workflow-primary")).to_contain_text("查看连接说明")
    expect(page.locator("[data-workflow-step].is-complete")).to_have_count(0)
    expect(page.locator("[data-workflow-step][aria-current=step]")).to_have_count(0)
    page.locator("#workflow-primary").click()
    expect(page.locator("#view-handoff")).to_be_visible()
    expect(page.locator("#handoff-root").get_by_role("status")).to_contain_text(
        "尚未启用 Codex 交接"
    )
    expect(
        page.locator("#handoff-root").get_by_role("button", name="冻结资料并准备交接")
    ).to_have_count(0)
