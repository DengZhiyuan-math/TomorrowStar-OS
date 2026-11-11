"""Information entry saves locally at completion without repeated confirmation."""

import pytest
from test_application_flow_browser import flow_portal, prepare_browser_worker
from test_career_portal_http import portal as portal
from test_portal_workflow_browser import browser_page as browser_page

pytestmark = pytest.mark.worker_browser


def show_questions(page, instance, monkeypatch):
    from playwright.sync_api import expect

    service, starts = prepare_browser_worker(page, instance, monkeypatch)
    state = service.store.load()
    state["jobs"][0].update(
        status="needs_input",
        questions=[
            {"id": "name", "question": "Full name", "options": []},
            {"id": "start", "question": "Start date", "options": []},
            {"id": "country", "question": "Country", "options": ["CHE", "USA"]},
        ],
    )
    service.store.save(state)
    page.locator("#flow-observe").click()
    expect(page.get_by_label("Full name · 补充信息")).to_be_visible()
    return service, starts


def test_completed_input_saves_library_without_a_second_confirmation(
    portal, tmp_path, browser_page, monkeypatch
):
    from playwright.sync_api import expect

    page = browser_page
    with flow_portal(portal, tmp_path, worker=True) as (instance, _):
        service, starts = show_questions(page, instance, monkeypatch)
        writes = []
        page.on(
            "request",
            lambda request: (
                writes.append(request.post_data_json)
                if request.method == "POST" and request.url.endswith("/worker-action")
                else None
            ),
        )
        expect(page.get_by_role("button", name="确认当前岗位答案")).to_have_count(0)
        answer = page.get_by_label("Full name · 补充信息")
        expect(answer.locator("..")).to_contain_text("基本信息，可跨岗位复用")
        expect(page.get_by_label("Start date · 补充信息").locator("..")).to_contain_text("仅此岗位")
        answer.fill("   ")
        page.get_by_label("Start date · 补充信息").click()
        assert writes == []
        answer.fill("Synthetic Person")
        assert writes == []
        page.get_by_label("Start date · 补充信息").click()
        expect(page.locator("#flow-notice")).to_contain_text("已自动保存到信息库")
        assert len(writes) == 1 and writes[0]["operation"] == "answer"
        assert writes[0]["payload"]["only_this"] is False
        assert service.store.library()[0]["value"] == "Synthetic Person"
        assert service.store.load()["control"] == "paused" and starts == []
        page.get_by_label("Country · 补充信息").select_option("CHE")
        expect(page.locator("#flow-notice")).to_contain_text("已自动保存到信息库")
        expect(page.get_by_label("Country · 补充信息")).to_have_count(0)
        assert [row["operation"] for row in writes] == ["answer", "answer"]
        assert service.store.load()["control"] == "paused" and starts == []


def test_busy_save_preserves_updated_value_and_next_completed_answer(
    portal, tmp_path, browser_page, monkeypatch
):
    from playwright.sync_api import expect

    page = browser_page
    with flow_portal(portal, tmp_path, worker=True) as (instance, _):
        service, starts = show_questions(page, instance, monkeypatch)
        held, writes = [], []

        def save(route):
            writes.append(route.request.post_data_json)
            response = route.fetch()
            if len(writes) == 1:
                held.append((route, response))
            else:
                route.fulfill(response=response)

        page.route("**/api/flow/worker-action", save)
        name = page.get_by_label("Full name · 补充信息")
        date = page.get_by_label("Start date · 补充信息")
        name.fill("Synthetic First")
        date.click()
        expect(page.locator("#flow-root")).to_have_attribute("aria-busy", "true")
        expect(name).to_be_disabled()
        date.fill("2026-10-01")
        page.get_by_label("Country · 补充信息").click()
        date.fill("2026-11-01")
        page.get_by_label("Country · 补充信息").click()
        assert len(writes) == 1
        held[0][0].fulfill(response=held[0][1])
        expect(page.get_by_label("Start date · 补充信息")).to_have_count(0)
        assert [row["payload"]["value"] for row in writes] == ["Synthetic First", "2026-11-01"]
        values = {row["value"] for row in service.store.library()}
        assert "Synthetic First" in values and "2026-11-01" in values
        assert "2026-10-01" not in values
        assert service.store.load()["control"] == "paused" and starts == []


@pytest.mark.parametrize("outcome", ["disconnect", "server_error", "conflict"])
def test_failed_answer_write_preserves_draft_and_never_retries_on_readback(
    portal, tmp_path, browser_page, monkeypatch, outcome
):
    from playwright.sync_api import expect

    page = browser_page
    with flow_portal(portal, tmp_path, worker=True) as (instance, _):
        service, starts = show_questions(page, instance, monkeypatch)
        writes = []

        def unknown(route):
            writes.append(route.request.post_data_json)
            if outcome == "disconnect":
                route.abort("failed")
            else:
                route.fulfill(
                    status=409 if outcome == "conflict" else 500,
                    json={"error": {"message": "Synthetic save failure"}},
                )

        page.route("**/api/flow/worker-action", unknown)
        answer = page.get_by_label("Full name · 补充信息")
        answer.fill("Synthetic Unknown")
        page.get_by_label("Start date · 补充信息").click()
        expect(page.locator("#flow-notice")).to_contain_text(
            "输入已保留" if outcome == "conflict" else "操作结果尚未核验"
        )
        expect(answer).to_have_value("Synthetic Unknown")
        page.locator("#flow-observe").click()
        expect(page.locator("#flow-notice")).to_contain_text("已读取持久状态")
        answer.click()
        page.get_by_label("Start date · 补充信息").click()
        page.locator("#flow-observe").click()
        assert len(writes) == 1 and not service.store.library()
        expect(answer).to_have_value("Synthetic Unknown")
        assert service.store.load()["control"] == "paused" and starts == []


def test_poll_preserves_unfinished_text_without_saving_or_duplicate_blur(
    portal, tmp_path, browser_page, monkeypatch
):
    from playwright.sync_api import expect

    page = browser_page
    with flow_portal(portal, tmp_path, worker=True) as (instance, _):
        service, starts = show_questions(page, instance, monkeypatch)
        writes = []
        page.on(
            "request",
            lambda request: (
                writes.append(request.post_data_json)
                if request.method == "POST" and request.url.endswith("/worker-action")
                else None
            ),
        )
        answer = page.get_by_label("Full name · 补充信息")
        answer.fill("Unfinished synthetic draft")
        state = service.store.load()
        state["jobs"][0]["reason"] = "synthetic-poll-change"
        service.store.save(state)
        expect(page.locator("#flow-worker")).to_contain_text("synthetic-poll-change")
        expect(answer).to_have_value("Unfinished synthetic draft")
        expect(answer).to_be_focused()
        assert writes == []
        answer.fill("Synthetic Completed")
        page.locator("#flow-title").click()
        expect(page.get_by_label("Full name · 补充信息")).to_have_count(0)
        page.locator("#flow-observe").click()
        assert len(writes) == 1 and writes[0]["payload"]["value"] == "Synthetic Completed"
        assert service.store.load()["control"] == "paused" and starts == []


def test_applied_write_with_lost_response_is_read_back_without_replay(
    portal, tmp_path, browser_page, monkeypatch
):
    from playwright.sync_api import expect

    page = browser_page
    with flow_portal(portal, tmp_path, worker=True) as (instance, _):
        service, starts = show_questions(page, instance, monkeypatch)
        writes = []

        def applied(route):
            writes.append(route.request.post_data_json)
            assert route.fetch().status == 200
            route.abort("failed")

        page.route("**/api/flow/worker-action", applied)
        page.get_by_label("Full name · 补充信息").fill("Synthetic Saved")
        page.locator("#flow-title").click()
        expect(page.locator("#flow-notice")).to_contain_text("操作结果尚未核验")
        page.locator("#flow-observe").click()
        expect(page.locator("#flow-notice")).to_contain_text("已读取持久状态")
        expect(page.get_by_label("Full name · 补充信息")).to_have_count(0)
        page.locator("#flow-observe").click()
        assert len(writes) == 1
        assert [row["value"] for row in service.store.library()] == ["Synthetic Saved"]
        assert service.store.load()["control"] == "paused" and starts == []


def test_unknown_save_stops_queued_items_with_visible_unsaved_drafts(
    portal, tmp_path, browser_page, monkeypatch
):
    from playwright.sync_api import expect

    page = browser_page
    with flow_portal(portal, tmp_path, worker=True) as (instance, _):
        service, starts = show_questions(page, instance, monkeypatch)
        held = []
        page.route("**/api/flow/worker-action", lambda route: held.append(route))
        page.get_by_label("Full name · 补充信息").fill("Synthetic Unknown")
        date = page.get_by_label("Start date · 补充信息")
        date.click()
        expect(page.locator("#flow-root")).to_have_attribute("aria-busy", "true")
        date.fill("2026-11-01")
        page.get_by_label("Country · 补充信息").click()
        expect(date.locator("..")).to_contain_text("等待自动保存")
        held[0].abort("failed")
        expect(page.locator("#flow-notice")).to_contain_text("操作结果尚未核验")
        expect(date.locator("..")).to_contain_text("尚未保存。自动保存已停止")
        expect(date).to_have_value("2026-11-01")
        page.locator("#flow-observe").click()
        expect(page.locator("#flow-notice")).to_contain_text("已读取持久状态")
        assert len(held) == 1 and not service.store.library()
        assert service.store.load()["control"] == "paused" and starts == []


def test_unknown_draft_cannot_reconcile_against_another_jobs_scoped_record(
    portal, tmp_path, browser_page, monkeypatch
):
    from playwright.sync_api import expect

    page = browser_page
    with flow_portal(portal, tmp_path, worker=True) as (instance, _):
        service, starts = show_questions(page, instance, monkeypatch)
        service.store.answers.put_answer(
            {
                "question": "Full name",
                "scope": {"application_id": "f" * 24},
                "value": "Synthetic Unknown",
                "state": "confirmed",
                "source": "user",
            }
        )
        writes = []

        def unknown(route):
            writes.append(route.request.post_data_json)
            route.abort("failed")

        page.route("**/api/flow/worker-action", unknown)
        answer = page.get_by_label("Full name · 补充信息")
        answer.fill("Synthetic Unknown")
        page.locator("#flow-title").click()
        expect(page.locator("#flow-notice")).to_contain_text("操作结果尚未核验")
        page.locator("#flow-observe").click()
        expect(page.locator("#flow-notice")).to_contain_text("已读取持久状态")
        state = service.store.load()
        state["jobs"][0]["reason"] = "synthetic-unrelated-record"
        service.store.save(state)
        expect(page.locator("#flow-worker")).to_contain_text("synthetic-unrelated-record")
        expect(answer).to_have_value("Synthetic Unknown")
        assert len(writes) == 1 and len(service.store.library()) == 1
        assert service.store.load()["control"] == "paused" and starts == []
