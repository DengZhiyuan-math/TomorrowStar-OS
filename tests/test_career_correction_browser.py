"""Document corrections remain user edits with an inspectable history."""

import json

import pytest
from test_career_portal_http import portal as portal
from test_portal_workflow_browser import browser_page as browser_page

pytestmark = pytest.mark.worker_browser


def test_user_corrects_document_and_reopens_its_history(portal, browser_page):
    from playwright.sync_api import expect

    sources = portal.career / "sources"
    sources.mkdir()
    path = sources / "project.md"
    original = "# Synthetic project\n\nImplemented the parser.\n"
    path.write_text(original)
    identifier = portal.state()["evidence"][0]["id"]
    page = browser_page
    page.goto(portal.origin + "/#evidence")
    page.locator("#show-evidence-library").click()
    page.locator("#evidence-list .evidence-card").click()
    page.get_by_role("button", name="更正经历文档", exact=True).click()
    updated = "# Synthetic project\n\nImplemented the parser and its validation.\n"
    editor = page.get_by_label("经历文档正文", exact=True)
    editor.fill(updated)
    page.locator("#evidence-done").click()
    page.locator("#evidence-list .evidence-card").click()
    expect(editor).to_have_value(updated)
    page.get_by_role("button", name="保存事实更正", exact=True).click()
    expect(page.locator("#evidence-content")).to_contain_text("事实更正已保存")
    assert path.read_text() == updated
    _, _, raw = portal.request("GET", "/api/evidence/" + identifier)
    detail = json.loads(raw)
    assert len(detail["history"]) == 1
    assert detail["history"][0]["actor"] == "user"
    assert (portal.career / detail["history"][0]["backup"]).read_text() == original
    page.locator("#evidence-done").click()
    page.locator("#evidence-list .evidence-card").click()
    page.get_by_text("更正历史 · 1", exact=True).click()
    expect(page.locator("#evidence-content")).to_contain_text("已保存")
    expect(page.locator("#evidence-content")).to_contain_text("user")


def test_lost_correction_response_reads_saved_document_without_replay(portal, browser_page):
    from playwright.sync_api import expect

    sources = portal.career / "sources"
    sources.mkdir()
    path = sources / "project.md"
    path.write_text("# Synthetic project\n\nOriginal facts.\n")
    page = browser_page
    writes = []

    def lose_response(route):
        if route.request.method == "PATCH":
            writes.append(route.request.post_data_json)
            status, _, _ = portal.request(
                "PATCH",
                "/api/evidence/" + route.request.url.rsplit("/", 1)[-1],
                body=route.request.post_data.encode(),
                headers=portal.write_headers(),
            )
            assert status == 200
            route.abort()
        else:
            route.continue_()

    page.route("**/api/evidence/*", lose_response)
    page.goto(portal.origin + "/#evidence")
    page.locator("#show-evidence-library").click()
    page.locator("#evidence-list .evidence-card").click()
    page.get_by_role("button", name="更正经历文档", exact=True).click()
    updated = "# Synthetic project\n\nCorrected factual description.\n"
    page.get_by_label("经历文档正文", exact=True).fill(updated)
    page.get_by_role("button", name="保存事实更正", exact=True).click()
    expect(page.locator("#evidence-content")).to_contain_text("保存结果尚未核验")
    expect(page.get_by_role("button", name="保存事实更正", exact=True)).to_be_disabled()
    page.get_by_role("button", name="核验最新文档", exact=True).click()
    expect(page.locator("#evidence-content")).to_contain_text("当前正文已核验")
    assert path.read_text() == updated
    assert len(writes) == 1


def test_late_save_response_keeps_other_document_title_content_and_editor(portal, browser_page):
    from playwright.sync_api import expect

    sources = portal.career / "sources"
    sources.mkdir()
    (sources / "first.md").write_text("# First document\n\nOriginal first facts.\n")
    (sources / "second.md").write_text("# Second document\n\nSecond facts remain here.\n")
    page = browser_page
    pending = []

    def delay_saved_response(route):
        if route.request.method != "PATCH":
            route.continue_()
            return
        status, _, body = portal.request(
            "PATCH",
            "/api/evidence/" + route.request.url.rsplit("/", 1)[-1],
            body=route.request.post_data.encode(),
            headers=portal.write_headers(),
        )
        assert status == 200
        pending.append((route, body))

    page.route("**/api/evidence/*", delay_saved_response)
    page.goto(portal.origin + "/#evidence")
    page.locator("#show-evidence-library").click()
    page.locator("#evidence-list .evidence-card").filter(has_text="first").click()
    page.get_by_role("button", name="更正经历文档", exact=True).click()
    page.get_by_label("经历文档正文", exact=True).fill(
        "# First document\n\nCorrected first facts.\n"
    )
    with page.expect_request("**/api/evidence/*"):
        page.get_by_role("button", name="保存事实更正", exact=True).click()
    page.locator("#evidence-done").click()
    page.locator("#evidence-list .evidence-card").filter(has_text="second").click()
    expect(page.locator("#evidence-dialog-title")).to_have_text("Second document")
    expect(page.locator("#evidence-content")).to_contain_text("Second facts remain here.")
    assert len(pending) == 1
    route, body = pending[0]
    route.fulfill(status=200, content_type="application/json", body=body)
    expect(page.locator("#evidence-dialog-title")).to_have_text("Second document")
    expect(page.locator("#evidence-content")).to_contain_text("Second facts remain here.")
    expect(page.locator("#evidence-content")).not_to_contain_text("Corrected first facts.")
    page.get_by_role("button", name="更正经历文档", exact=True).click()
    expect(page.get_by_label("经历文档正文", exact=True)).to_have_value(
        "# Second document\n\nSecond facts remain here.\n"
    )
