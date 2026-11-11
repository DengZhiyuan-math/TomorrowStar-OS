"""The displayed LaTeX and PDF share one selected immutable review version."""

import re

import pytest
from test_career_portal_http import portal as portal
from test_portal_workflow_browser import browser_page as browser_page
from test_standalone_prism_review_http import review_portal as review_portal

pytestmark = pytest.mark.worker_browser


def test_standalone_version_banner_history_and_changed_source(review_portal, browser_page):
    from playwright.sync_api import expect

    active, project, calls = review_portal
    page = browser_page
    # Chromium's bundled PDF viewer loads internal browser assets, not network sites.
    page.context.route(
        re.compile(r"^(chrome-extension://mhjfbmdgcfjbbpaeojofohoefgiehjai/|chrome://resources/)"),
        lambda route: route.continue_(),
    )
    page.goto(active.origin + "/#resume-review")
    root = page.locator("#resume-review-root")
    expect(root).to_contain_text("尚未接回审阅版本")
    expect(root).to_contain_text("真实申请继续暂停")
    root.get_by_role("button", name="读取最新 LaTeX 并核验 PDF", exact=True).click()
    expect(root.locator(".prism-review-source pre")).to_contain_text("Synthetic first version")
    first = active.server.resume_review_store.state()["latest"]
    expect(root).to_contain_text(first["id"])
    expect(root).to_contain_text(first["source_sha256"])
    expect(root).to_contain_text(first["pdf_sha256"])
    expect(root.locator("iframe")).to_have_attribute(
        "src", f"/api/resume-review/versions/{first['id']}/pdf"
    )
    expect(root).to_contain_text("待人工审阅")
    page.reload()
    expect(root.locator(".prism-review-source pre")).to_contain_text("Synthetic first version")
    assert len([call for call in calls if call[0] == "POST"]) == 1
    (project / "main.tex").write_text(
        r"\documentclass{article}\begin{document}Synthetic edited version\end{document}"
    )
    root.get_by_role("button", name="检查源文件变化", exact=True).click()
    expect(root).to_contain_text("Prism 源已变化")
    expect(root.locator(".prism-review-source pre")).to_contain_text("Synthetic first version")
    root.get_by_role("button", name="读取最新 LaTeX 并核验 PDF", exact=True).click()
    expect(root.locator(".prism-review-source pre")).to_contain_text("Synthetic edited version")
    second = active.server.resume_review_store.state()["latest"]
    assert second["id"] != first["id"]
    page.get_by_label("选择审阅版本").select_option(first["id"])
    expect(root.locator(".prism-review-source pre")).to_contain_text("Synthetic first version")
    expect(root.locator("iframe")).to_have_attribute(
        "src", f"/api/resume-review/versions/{first['id']}/pdf"
    )
    assert len([call for call in calls if call[0] == "POST"]) == 2
    assert active.server.worker_service is None
    assert active.server.application_flow_service.snapshot()["tasks"] == []


def test_saved_edits_are_detected_without_manual_check_or_pdf_reload(review_portal, browser_page):
    from playwright.sync_api import expect

    active, project, calls = review_portal
    page = browser_page
    page.context.route(
        re.compile(r"^(chrome-extension://mhjfbmdgcfjbbpaeojofohoefgiehjai/|chrome://resources/)"),
        lambda route: route.continue_(),
    )
    page.goto(active.origin + "/#resume-review")
    root = page.locator("#resume-review-root")
    root.get_by_role("button", name="读取最新 LaTeX 并核验 PDF", exact=True).click()
    expect(root.locator(".prism-review-source pre")).to_contain_text("Synthetic first version")
    first = active.server.resume_review_store.state()["latest"]
    frame = root.locator("iframe").element_handle()
    page.clock.install()
    (project / "main.tex").write_text(
        r"\documentclass{article}\begin{document}Saved by Prism\end{document}"
    )
    page.clock.fast_forward(4000)
    expect(root).to_contain_text("检测到 Prism 已保存新改动")
    assert frame.evaluate("frame => frame.isConnected")
    expect(root.locator(".prism-review-source pre")).to_contain_text("Synthetic first version")
    expect(root.locator("iframe")).to_have_attribute(
        "src", f"/api/resume-review/versions/{first['id']}/pdf"
    )
    assert len([call for call in calls if call[0] == "POST"]) == 1
    assert active.server.resume_review_store.state()["latest"]["id"] == first["id"]


def test_auto_check_retains_selected_history_and_one_click_reads_latest(
    review_portal, browser_page
):
    from playwright.sync_api import expect

    active, project, calls = review_portal
    page = browser_page
    page.context.route(
        re.compile(r"^(chrome-extension://mhjfbmdgcfjbbpaeojofohoefgiehjai/|chrome://resources/)"),
        lambda route: route.continue_(),
    )
    page.goto(active.origin + "/#resume-review")
    root = page.locator("#resume-review-root")
    root.get_by_role("button", name="读取最新 LaTeX 并核验 PDF", exact=True).click()
    expect(root.locator(".prism-review-source pre")).to_contain_text("Synthetic first version")
    first = active.server.resume_review_store.state()["latest"]
    (project / "main.tex").write_text("Synthetic second saved version")
    root.get_by_role("button", name="读取最新 LaTeX 并核验 PDF", exact=True).click()
    expect(root.locator(".prism-review-source pre")).to_contain_text(
        "Synthetic second saved version"
    )
    page.get_by_label("选择审阅版本").select_option(first["id"])
    expect(root.locator(".prism-review-source pre")).to_contain_text("Synthetic first version")
    frame = root.locator("iframe").element_handle()
    page.clock.install()
    (project / "main.tex").write_text("Synthetic third saved version")
    page.clock.fast_forward(4000)
    expect(root).to_contain_text("检测到 Prism 已保存新改动")
    expect(page.get_by_label("选择审阅版本")).to_have_value(first["id"])
    assert frame.evaluate("frame => frame.isConnected")
    assert len(active.server.resume_review_store.state()["versions"]) == 2
    assert len([call for call in calls if call[0] == "POST"]) == 2


def test_failed_auto_check_preserves_pdf_and_recovers_without_manual_action(
    review_portal, browser_page
):
    from playwright.sync_api import expect

    active, project, calls = review_portal
    page = browser_page
    page.context.route(
        re.compile(r"^(chrome-extension://mhjfbmdgcfjbbpaeojofohoefgiehjai/|chrome://resources/)"),
        lambda route: route.continue_(),
    )
    page.goto(active.origin + "/#resume-review")
    root = page.locator("#resume-review-root")
    root.get_by_role("button", name="读取最新 LaTeX 并核验 PDF", exact=True).click()
    expect(root.locator(".prism-review-source pre")).to_contain_text("Synthetic first version")
    frame = root.locator("iframe").element_handle()
    failures = []

    def fail_once(route):
        if not failures:
            failures.append(True)
            route.fulfill(
                status=503,
                content_type="application/json",
                body='{"message":"Synthetic disconnection"}',
            )
        else:
            route.continue_()

    page.route("**/api/resume-review/state", fail_once)
    page.clock.install()
    page.clock.fast_forward(4000)
    expect(root).to_contain_text("自动检查暂不可用")
    assert frame.evaluate("frame => frame.isConnected")
    (project / "main.tex").write_text("Synthetic change after connection recovery")
    page.clock.fast_forward(4000)
    expect(root).to_contain_text("检测到 Prism 已保存新改动")
    expect(root).not_to_contain_text("自动检查暂不可用")
    assert frame.evaluate("frame => frame.isConnected")
    assert len([call for call in calls if call[0] == "POST"]) == 1
    assert len(active.server.resume_review_store.state()["versions"]) == 1
