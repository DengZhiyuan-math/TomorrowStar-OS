"""Synthetic Gmail paging and per-job source recovery through the local UI."""

import re
import sys
import threading

import pytest
from test_application_intake import message
from test_application_intake import page as captured_page
from test_career_portal_http import _running_portal
from test_career_portal_http import portal as portal
from test_job_explanation_browser import reveal_control
from test_portal_workflow_browser import browser_page as browser_page

from career_evidence_graph.application_intake import ApplicationIntakeService
from career_evidence_graph.career_portal_data import PortalDataError

pytestmark = pytest.mark.worker_browser


@pytest.fixture(autouse=True)
def isolated_model_context(tmp_path, monkeypatch):
    codex_home = tmp_path / "synthetic-codex-home"
    codex_home.mkdir()
    monkeypatch.setenv("CODEX_HOME", str(codex_home))
    monkeypatch.setenv("TOMORROWSTAR_CODEX_EXECUTABLE", sys.executable)
    monkeypatch.delenv("CODEX_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)


def test_two_pages_keep_duplicates_and_recover_a_disconnected_continuation(
    portal, tmp_path, browser_page
):
    from playwright.sync_api import expect

    reads, fetches, writes = [], [], []
    first_url = "https://www.linkedin.com/jobs/view/10001"
    second_url = "https://www.linkedin.com/jobs/view/10002"

    def reader(directory, **options):
        reads.append(options)
        directory.mkdir()
        if len(reads) == 2:
            return {"status": "unavailable", "emails": [], "provenance": {}}
        first_page = options["page_token"] is None
        return {
            "status": "readable",
            "emails": [message("mail-one", [first_url])]
            if first_page
            else [
                message("mail-one", [first_url]),
                message("mail-two", [first_url, second_url]),
            ],
            "provenance": {
                "next_page_token": "synthetic-page-two" if first_page else None,
                "has_more": first_page,
            },
        }

    def fetcher(url):
        fetches.append(url)
        return captured_page(url) | {
            "capture_id": "capture-" + url.rsplit("/", 1)[-1],
            "captured_at": "2026-10-17T10:00:00Z",
        }

    def intake_factory(applications, root):
        return ApplicationIntakeService(applications, root, reader=reader, fetcher=fetcher)

    page = browser_page
    page.on(
        "request",
        lambda request: writes.append(request.post_data_json) if request.method == "POST" else None,
    )
    with _running_portal(
        portal.applications,
        portal.career,
        flow_root=tmp_path / "preparation",
        preparation_only=True,
        flow_intake_factory=intake_factory,
    ) as instance:
        page.goto(instance.origin + "/#flow")
        reveal_control(page, "#flow-refresh-mail")
        after = page.get_by_label("读取起始日期（UTC，含）")
        before = page.get_by_label("读取截止日期（UTC，不含）")
        after.fill("2026-10-01")
        before.fill("2026-10-08")
        page.locator("#flow-refresh-mail").click()
        progress = page.locator("#flow-mail-progress")
        expect(progress).to_contain_text("2026-10-01 — 2026-10-08 (UTC)")
        expect(progress).to_contain_text("已读取 1 页 · 1 封邮件")
        expect(progress).to_contain_text("仍有后续页")
        expect(page.locator("#flow-mail-status")).to_contain_text("部分推荐")
        expect(page.locator("#flow-candidates .flow-recommendation")).to_have_count(1)
        continuation = page.locator("#flow-continue-mail")
        expect(continuation).to_be_enabled()
        before.fill("2026-10-09")
        continuation.click()
        expect(page.locator("#flow-notice")).to_contain_text("时间范围已变化")
        expect(before).to_have_value("2026-10-09")
        assert len(reads) == 1
        before.fill("2026-10-08")
        continuation.click()
        expect(page.locator("#flow-mail-status")).to_contain_text("邮件连接暂不可用")
        expect(progress).to_contain_text("已读取 1 页 · 1 封邮件")
        expect(progress).not_to_contain_text("已读完")
        expect(page.locator("#flow-mail-status")).not_to_contain_text("没有找到")
        expect(continuation).to_be_enabled()
        continuation.click()
        expect(progress).to_contain_text("已读取 2 页 · 2 封邮件")
        expect(page.locator("#flow-candidates .flow-recommendation")).to_have_count(2)
        expect(page.locator("#flow-mail-status")).to_contain_text("推荐岗位已载入")
        expect(continuation).to_be_disabled()
        expect(after).to_have_value("2026-10-01")
        expect(before).to_have_value("2026-10-08")
        assert [read["page_token"] for read in reads] == [
            None,
            "synthetic-page-two",
            "synthetic-page-two",
        ]
        assert fetches == [first_url, second_url]
        assert all(set(row) <= {"after", "before", "revision"} for row in writes)
        assert instance.server.application_flow_service.snapshot()["tasks"] == []


def test_sources_are_acquired_retried_and_reconciled_one_job_at_a_time(
    portal, tmp_path, browser_page, monkeypatch
):
    from playwright.sync_api import expect

    from career_evidence_graph._vendor import job_apply_store as helper

    urls = [
        f"https://www.linkedin.com/jobs/view/{identifier}" for identifier in (10001, 10002, 10003)
    ]
    names = dict(zip(urls, ("Synthetic A", "Synthetic B", "Synthetic C"), strict=True))
    fetches = []
    entered, release = threading.Event(), threading.Event()

    def full_source(url):
        return captured_page(url) | {
            "capture_id": "source-" + url.rsplit("/", 1)[-1],
            "captured_at": "2026-10-17T10:00:00Z",
            "job_fields": {"title": "Engineer", "company": names[url], "location": "Zurich"},
            "body_text": f"{names[url]} complete JD. Build Python services; German C1 required.",
        }

    def fetcher(url):
        fetches.append(url)
        if url == urls[0]:
            entered.set()
            assert release.wait(10)
        if url == urls[1] and fetches.count(url) == 1:
            return captured_page(url, status="login_required", completeness="unknown") | {
                "capture_id": "synthetic-login-wall",
                "job_fields": {},
                "body_text": "Sign in to view this job",
                "error_code": "synthetic_login_required",
                "captured_at": "2026-10-17T10:00:00Z",
            }
        return full_source(url)

    def intake_factory(applications, root):
        return ApplicationIntakeService(
            applications,
            root,
            reader=lambda *_args, **_kwargs: pytest.fail("Unexpected Gmail read"),
            fetcher=fetcher,
        )

    page = browser_page
    with _running_portal(
        portal.applications,
        portal.career,
        flow_root=tmp_path / "preparation",
        preparation_only=True,
        flow_intake_factory=intake_factory,
    ) as instance:
        intake = instance.server.application_intake_service
        store = intake.store
        rows = store.import_messages(
            [message("three-roles", urls)],
            [
                {
                    "message_id": "three-roles",
                    "url": url,
                    "company": names[url],
                    "role_title": "Engineer",
                    "jd_completeness": "unknown",
                }
                for url in urls
            ],
        )["recommendations"]
        unknown = rows[2]
        attempt = store.begin_acquisition(unknown["id"], unknown["revision"])
        original_write = helper.atomic_write_json

        def unknown_save(path, payload):
            original_write(path, payload)
            if path.name == "recommendations.json":
                raise OSError("Synthetic save completed with unknown acknowledgement")

        with monkeypatch.context() as isolated:
            isolated.setattr(helper, "atomic_write_json", unknown_save)
            with pytest.raises(PortalDataError):
                store.finish_acquisition(unknown["id"], attempt["attempt_id"], full_source(urls[2]))
        page.goto(instance.origin + "/#flow")
        reveal_control(page, "#flow-refresh-mail")
        first = page.locator("#flow-candidates .flow-recommendation").filter(
            has=page.get_by_role("heading", name="Synthetic A · Engineer", exact=True)
        )
        second = page.locator("#flow-candidates .flow-recommendation").filter(
            has=page.get_by_role("heading", name="Synthetic B · Engineer", exact=True)
        )
        third = page.locator("#flow-candidates .flow-recommendation").filter(
            has=page.get_by_role("heading", name="Synthetic C · Engineer", exact=True)
        )
        expect(first.get_by_role("button", name="取得完整 JD", exact=True)).to_be_visible()
        expect(
            third.get_by_role("button", name=re.compile("选择此岗位|打开已有申请任务"), exact=True)
        ).to_be_disabled()
        expect(third.get_by_role("button", name="核验已保存取源结果", exact=True)).to_be_enabled()
        expect(third.get_by_role("button", name="取得完整 JD", exact=True)).to_have_count(0)
        expect(third.get_by_role("button", name="重试取得 JD", exact=True)).to_have_count(0)
        try:
            first.get_by_role("button", name="取得完整 JD", exact=True).click()
            assert entered.wait(1)
            expect(first.get_by_role("button", name="取得完整 JD", exact=True)).to_be_disabled()
            expect(second.get_by_role("button", name="取得完整 JD", exact=True)).to_be_disabled()
            expect(
                third.get_by_role("button", name="核验已保存取源结果", exact=True)
            ).to_be_disabled()
            expect(page.locator("#flow-refresh-mail")).to_be_disabled()
            expect(page.locator("#flow-continue-mail")).to_be_disabled()
        finally:
            release.set()
        expect(first).to_contain_text("完整 JD")
        expect(
            first.get_by_role("button", name=re.compile("选择此岗位|打开已有申请任务"), exact=True)
        ).to_be_enabled()
        first_sources = page.locator("#flow-recommendation-management > details").filter(
            has_text="Synthetic A · Engineer"
        )
        reveal_control(page, first_sources.locator(":scope > summary"))
        first_sources.get_by_text("邮件与 JD 来源", exact=True).click()
        expect(first_sources).to_contain_text("Synthetic A complete JD.")
        expect(first_sources).to_contain_text("2026-10-17T10:00:00Z")
        expect(first_sources).to_contain_text("JD 完整性：full")
        expect(first_sources.get_by_role("link", name="查看原岗位 ↗")).to_have_attribute(
            "href", urls[0]
        )
        expect(first.get_by_role("button", name="取得完整 JD", exact=True)).to_have_count(0)
        second.get_by_role("button", name="取得完整 JD", exact=True).click()
        second_sources = page.locator("#flow-recommendation-management > details").filter(
            has_text="Synthetic B · Engineer"
        )
        reveal_control(page, second_sources.locator(":scope > summary"))
        expect(second_sources).to_contain_text("synthetic_login_required")
        expect(second).to_contain_text("需要登录原岗位页面")
        expect(
            second.get_by_role("button", name=re.compile("选择此岗位|打开已有申请任务"), exact=True)
        ).to_be_disabled()
        second.get_by_role("button", name="重试取得 JD", exact=True).click()
        expect(
            second.get_by_role("button", name=re.compile("选择此岗位|打开已有申请任务"), exact=True)
        ).to_be_enabled()
        expect(second_sources).to_contain_text("Synthetic B complete JD.")
        third.get_by_role("button", name="核验已保存取源结果", exact=True).click()
        expect(
            third.get_by_role("button", name=re.compile("选择此岗位|打开已有申请任务"), exact=True)
        ).to_be_enabled()
        expect(third.get_by_role("button", name="核验已保存取源结果", exact=True)).to_have_count(0)
        assert fetches == [urls[0], urls[1], urls[1]]
        assert instance.server.application_flow_service.snapshot()["tasks"] == []
        assert {row["company"] for row in instance.state()["applications"]} == {
            "Synthetic A",
            "Synthetic B",
        }


def test_changed_mail_account_requires_new_refresh_and_exposes_no_account_identity(
    portal, tmp_path, browser_page
):
    from playwright.sync_api import expect

    reads = []

    def reader(directory, **options):
        reads.append(options)
        directory.mkdir()
        if len(reads) == 1:
            return {
                "status": "no_matches",
                "emails": [],
                "provenance": {
                    "next_page_token": "second-page",
                    "has_more": True,
                    "mailbox_identity": "a" * 64,
                },
            }
        return {
            "status": "unavailable",
            "emails": [],
            "provenance": {},
            "reason": "gmail_account_changed",
        }

    def intake_factory(applications, root):
        return ApplicationIntakeService(
            applications,
            root,
            reader=reader,
            fetcher=lambda *_args: pytest.fail("Unexpected source fetch"),
        )

    page = browser_page
    with _running_portal(
        portal.applications,
        portal.career,
        flow_root=tmp_path / "preparation",
        preparation_only=True,
        flow_intake_factory=intake_factory,
    ) as instance:
        page.goto(instance.origin + "/#flow")
        reveal_control(page, "#flow-refresh-mail")
        page.locator("#flow-refresh-mail").click()
        expect(page.locator("#flow-mail-progress")).to_contain_text("本读取范围账号已核验")
        page.locator("#flow-continue-mail").click()
        expect(page.locator("#flow-mail-status")).to_contain_text("邮箱账号已变化，请重新刷新推荐")
        expect(page.locator("#flow-continue-mail")).to_be_disabled()
        expect(page.locator("#flow-refresh-mail")).to_be_enabled()
        expect(page.locator("body")).not_to_contain_text("a" * 64)
        expect(page.locator("body")).not_to_contain_text("second-page")
        assert len(reads) == 2
