"""Synthetic saved-job explanations keep match, qualification and progress separate."""

import sys
from contextlib import contextmanager

import pytest
from test_application_match import model_output, model_runner
from test_career_portal_http import _running_portal
from test_career_portal_http import portal as portal
from test_portal_workflow_browser import browser_page as browser_page

from career_evidence_graph.application_intake import ApplicationIntakeService
from career_evidence_graph.application_match import analyze_job
from career_evidence_graph.application_resume import ApplicationResumeStore
from career_evidence_graph.career_portal_data import ApplicationStore

pytestmark = pytest.mark.worker_browser


@pytest.fixture(autouse=True)
def isolated_model_context(tmp_path, monkeypatch):
    codex_home = tmp_path / "synthetic-codex-home"
    codex_home.mkdir()
    monkeypatch.setenv("CODEX_HOME", str(codex_home))
    monkeypatch.setenv("TOMORROWSTAR_CODEX_EXECUTABLE", sys.executable)
    monkeypatch.delenv("CODEX_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)


@contextmanager
def explanation_portal(portal, tmp_path, *, extra_requirements=None, information_library_root=None):
    contributions = portal.career / "contributions"
    contributions.mkdir()
    (contributions / "python.md").write_text(
        "# Synthetic Python service\n\n## Scope\nImplemented a Python service.\n\n"
        "## Responsibility attribution\n| Work | Owner |\n| --- | --- |\n"
        "| Implementation | User |\n\n## Boundaries\nNo GPU training claim.\n"
    )
    sources = portal.career / "sources"
    sources.mkdir()
    (sources / "profile.json").write_text('{"name":"Synthetic Person"}')
    calls, exports = [], []

    def analyzer(application, snapshot, directory):
        output = model_output(snapshot)
        extra = (
            extra_requirements(application, snapshot)
            if callable(extra_requirements)
            else (extra_requirements or {}).get(application["company"], [])
        )
        output["requirements"].extend(extra)
        return analyze_job(application, snapshot, directory, runner=model_runner(output, calls))

    def exporter(html, pdf):
        exports.append(pdf)
        pdf.write_bytes(b"%PDF-1.4 Synthetic loopback document")

    def resume_factory(applications, catalog, root):
        return ApplicationResumeStore(
            applications,
            catalog,
            root,
            tailorer=lambda draft, application, directory: draft | {"generation": "codex"},
            exporter=exporter,
        )

    def intake_factory(applications, root):
        return ApplicationIntakeService(
            applications,
            root,
            reader=lambda *_args, **_kwargs: pytest.fail("Unexpected Gmail read"),
            fetcher=lambda *_args, **_kwargs: pytest.fail("Unexpected source fetch"),
        )

    with _running_portal(
        portal.applications,
        portal.career,
        preparation_only=True,
        flow_root=tmp_path / "preparation",
        flow_analyzer=analyzer,
        flow_resume_factory=resume_factory,
        flow_intake_factory=intake_factory,
        information_library_root=information_library_root,
    ) as instance:
        yield instance, {"calls": calls, "exports": exports}


def reveal_control(page, selector):
    from playwright.sync_api import expect

    expect(page.locator("#flow-root")).to_have_attribute("aria-busy", "false")
    target = page.locator(selector) if isinstance(selector, str) else selector
    target.wait_for(state="attached")
    page.wait_for_load_state("networkidle")
    for details in target.locator("xpath=ancestor::details").all():
        if details.get_attribute("open") is None:
            details.locator(":scope > summary").click()


def select_saved_job(page, button):
    from playwright.sync_api import expect

    open_internal_management(page)
    title = button.locator("xpath=ancestor::article[1]").locator("h3").inner_text()
    button.click()
    expect(page.locator("#flow-task .flow-job-title")).to_have_text(title)
    expect(page.locator("#flow-root")).to_have_attribute("aria-busy", "false")
    page.wait_for_load_state("networkidle")


def open_internal_management(page):
    details = page.locator("#flow-internal-management")
    if details.get_attribute("open") is None:
        details.locator(":scope > summary").click()


def open_analysis_details(page):
    open_internal_management(page)
    system = page.locator("#flow-system-details")
    if system.get_attribute("open") is None:
        system.locator(":scope > summary").click()
    overview = page.locator("#flow-fit-details")
    if overview.get_attribute("open") is None:
        overview.locator(":scope > summary").click()
    details = page.locator("#flow-analysis-details")
    if details.get_attribute("open") is None:
        details.locator(":scope > summary").click()


def test_only_current_job_shows_compact_overview_and_details_are_closed_on_reopen(
    portal, tmp_path, browser_page
):
    from playwright.sync_api import expect

    ApplicationStore(portal.applications).create_application(
        {
            "company": "Synthetic",
            "role_title": "Python Engineer",
            "job_description": "Build Python services.",
        }
    )
    page = browser_page
    page.set_viewport_size({"width": 1280, "height": 800})
    with explanation_portal(portal, tmp_path) as (instance, work):
        page.goto(instance.origin + "/#flow")
        saved = page.locator("#flow-saved-jobs")
        expect(saved.locator(".flow-fit-overview, .flow-explanation")).to_have_count(0)
        open_internal_management(page)
        select_saved_job(page, saved.get_by_role("button", name="选择已有岗位"))
        reveal_control(page, "#flow-start-analysis")
        page.locator("#flow-start-analysis").click()
        detail = page.locator("#flow-explanation")
        reveal_control(page, "#flow-explanation")
        expect(page.get_by_role("region", name="岗位匹配概览")).to_have_count(1)
        expect(detail.get_by_role("heading", name="岗位适配概览")).to_be_visible()
        expect(detail.locator(".flow-fit-list").first).to_contain_text("编程与工程")
        expect(detail.locator("#flow-fit-score")).to_be_visible()
        expect(detail.locator("#flow-fit-score")).to_contain_text("100/100")
        expect(detail.locator("#flow-fit-score-legend")).not_to_be_visible()
        expanded = detail.locator("details.flow-fit-details")
        expect(expanded).not_to_have_attribute("open", "")
        expect(detail.get_by_role("heading", name="匹配分", exact=True)).not_to_be_visible()
        expect(detail.get_by_text("preparation-policy/v1.0", exact=False)).not_to_be_visible()
        expect(detail.locator("blockquote").first).not_to_be_visible()
        expect(saved).not_to_contain_text("Documentary implementation evidence.")
        expect(saved).not_to_contain_text("资格结论")
        page.evaluate("scrollTo(0, 0)")
        page.screenshot(path="/private/tmp/fit-overview-synthetic.png")
        box = detail.bounding_box()
        assert box and box["y"] >= 0 and box["height"] <= 650 and box["y"] + box["height"] <= 800
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
        expanded.locator(":scope > summary").click()
        for text in (
            "100/100",
            "Documentary implementation evidence.",
            "No GPU training claim.",
        ):
            expect(detail).to_contain_text(text)
        expect(detail.locator("blockquote").first).to_be_visible()
        expect(page.locator("#flow-start-resume")).to_be_enabled()
        page.reload()
        reveal_control(page, "#flow-explanation")
        expect(page.get_by_role("region", name="岗位匹配概览")).to_have_count(1)
        expect(page.locator("#flow-explanation details.flow-fit-details")).not_to_have_attribute(
            "open", ""
        )
        expect(page.locator("#flow-saved-jobs")).not_to_contain_text(
            "Documentary implementation evidence."
        )
        assert len(instance.server.application_flow_service.snapshot()["tasks"]) == 1
        assert work["calls"] and not work["exports"]


def test_fixed_framework_overview_does_not_report_legacy_weights_or_block_satisfied_or_group(
    portal, tmp_path, browser_page
):
    from playwright.sync_api import expect

    ApplicationStore(portal.applications).create_application(
        {
            "company": "Synthetic",
            "role_title": "Python Engineer",
            "job_description": "Build Python services.",
        }
    )
    page = browser_page

    def fixed_overview(route):
        response = route.fetch()
        payload = response.json()
        explanation = payload.get("active_explanation")
        if explanation and explanation.get("score"):
            # Exercise the saved presentation projection; scoring is tested through Python APIs.
            explanation["reasons"][0]["scoring_framework"] = {
                "protocol": "business-group-framework/v1"
            }
            explanation["qualification"] = {
                "status": "supported",
                "conditions": [{"text": "Alternative credential", "status": "conflict"}],
            }
        route.fulfill(response=response, json=payload)

    with explanation_portal(portal, tmp_path) as (instance, _work):
        page.route("**/api/flow/**", fixed_overview)
        page.goto(instance.origin + "/#flow")
        open_internal_management(page)
        select_saved_job(
            page, page.locator("#flow-saved-jobs").get_by_role("button", name="选择已有岗位")
        )
        reveal_control(page, "#flow-start-analysis")
        page.locator("#flow-start-analysis").click()
        reveal_control(page, "#flow-explanation")
        overview = page.locator("#flow-explanation")
        expect(overview.locator("#flow-fit-score-legend")).to_contain_text("固定业务组权重")
        expect(overview.locator("#flow-fit-score-legend")).not_to_contain_text("×3")
        expect(overview.locator("#flow-fit-score-legend")).not_to_contain_text("半分")
        expect(overview.locator(".flow-fit-status")).to_have_text("硬条件已确认支持")
        expect(overview.locator(".flow-fit-conflicts")).to_contain_text("资格按原组关系汇总")
        expect(overview.locator(".flow-fit-conflicts")).not_to_contain_text("需先处理")


def test_manual_order_keeps_unknown_and_conflicting_qualifications_and_sources(
    portal, tmp_path, browser_page
):
    from playwright.sync_api import expect

    applications = ApplicationStore(portal.applications)
    for company in ("Unknown Company", "Conflict Company"):
        applications.create_application(
            {
                "company": company,
                "role_title": "Engineer",
                "job_description": "Build Python services. A work permit is required.",
            }
        )
    requirement = {
        "text": "Work permit",
        "importance": "required",
        "judgment": "unknown",
        "hard_condition": True,
        "explanation": "Applicant fact is unknown.",
        "source_ids": [],
        "citations": [],
        "claim_scope": "unknown",
    }
    page = browser_page
    with explanation_portal(
        portal,
        tmp_path,
        extra_requirements={
            company: [requirement] for company in ("Unknown Company", "Conflict Company")
        },
    ) as (instance, work):
        page.goto(instance.origin + "/#flow")
        cards = page.locator("#flow-saved-jobs .flow-recommendation")
        unknown = cards.filter(
            has=page.get_by_role("heading", name="Unknown Company · Engineer", exact=True)
        )
        conflict = cards.filter(
            has=page.get_by_role("heading", name="Conflict Company · Engineer", exact=True)
        )
        open_internal_management(page)
        select_saved_job(page, unknown.get_by_role("button", name="选择已有岗位"))
        reveal_control(page, "#flow-start-analysis")
        page.locator("#flow-start-analysis").click()
        expect(page.locator("#flow-explanation .flow-fit-status")).to_have_text("资格信息待核对")
        expect(page.locator("#flow-start-resume")).to_be_disabled()
        open_internal_management(page)
        select_saved_job(page, conflict.get_by_role("button", name="选择已有岗位"))
        reveal_control(page, "#flow-start-analysis")
        page.locator("#flow-start-analysis").click()
        expect(page.locator("#flow-explanation .flow-fit-status")).to_have_text("资格信息待核对")
        open_analysis_details(page)
        page.get_by_label("Work permit · 事实说明").fill(
            "Synthetic fact: I do not have this permit."
        )
        page.get_by_label("Work permit · 是否符合").select_option("false")
        page.get_by_role("button", name="保存硬条件说明").click()
        expect(page.locator("#flow-explanation .flow-fit-status")).to_have_text("存在硬条件冲突")
        expect(page.locator("#flow-start-resume")).to_be_disabled()
        before = instance.server.application_flow_service.snapshot()["active_task"]
        first_title = cards.first.locator("h3").inner_text()
        move_down = first_title == "Conflict Company · Engineer"
        open_internal_management(page)
        settings = page.locator("#flow-job-management .flow-job-settings").filter(
            has_text="Conflict Company · Engineer"
        )
        settings.locator(":scope > summary").click()
        move = settings.get_by_role(
            "button", name="下移岗位" if move_down else "上移岗位", exact=True
        )
        expect(move).to_be_enabled()
        move.click()
        expect(cards.nth(1 if move_down else 0)).to_contain_text("Conflict Company · Engineer")
        detail = page.locator("#flow-explanation")
        expect(detail.locator(".flow-fit-conflicts")).to_contain_text("硬条件冲突")
        for card in (unknown, conflict):
            expect(card).not_to_contain_text("Applicant fact is unknown.")
            expect(card).not_to_contain_text("No GPU training claim.")
        reveal_control(page, "#flow-explanation .flow-fit-details")
        detail.locator(".flow-fit-details > summary").click()
        expect(detail).to_contain_text("已支持 50/100")
        expect(detail).to_contain_text("可能 50–100")
        expect(detail).to_contain_text("Synthetic fact: I do not have this permit.")
        after = instance.server.application_flow_service.snapshot()["active_task"]
        assert after["id"] == before["id"] and after["analysis_id"] == before["analysis_id"]
        assert not work["exports"]
        page.reload()
        expect(cards.nth(1 if move_down else 0)).to_contain_text("Conflict Company · Engineer")
        expect(page.locator("#flow-explanation .flow-fit-status")).to_have_text("存在硬条件冲突")
        open_internal_management(page)
        select_saved_job(page, unknown.get_by_role("button", name="选择已有岗位"))
        expect(page.locator("#flow-explanation .flow-fit-status")).to_have_text("资格信息待核对")


def test_changed_jd_marks_only_its_explanation_historical_without_restarting_other_jobs(
    portal, tmp_path, browser_page
):
    from playwright.sync_api import expect

    applications = ApplicationStore(portal.applications)
    jobs = [
        applications.create_application(
            {
                "company": company,
                "role_title": "Engineer",
                "job_description": "Build Python services.",
            }
        )
        for company in ("Synthetic A", "Synthetic B")
    ]
    page = browser_page
    with explanation_portal(portal, tmp_path) as (instance, work):
        page.goto(instance.origin + "/#flow")
        cards = page.locator("#flow-saved-jobs .flow-recommendation")
        first = cards.filter(
            has=page.get_by_role("heading", name="Synthetic A · Engineer", exact=True)
        )
        second = cards.filter(
            has=page.get_by_role("heading", name="Synthetic B · Engineer", exact=True)
        )
        for card in (first, second):
            open_internal_management(page)
            select_saved_job(page, card.get_by_role("button", name="选择已有岗位"))
            reveal_control(page, "#flow-start-analysis")
            page.locator("#flow-start-analysis").click()
            expect(page.locator("#flow-explanation")).to_contain_text("已支持 100/100")
        before = instance.server.application_flow_service.snapshot()["active_task"]
        calls = len(work["calls"])
        applications.update_application(
            jobs[0]["id"], {"job_description": "Build Rust services."}, jobs[0]["revision"]
        )
        page.locator("#refresh-button").click()
        open_internal_management(page)
        page.locator("#flow-task-list button").filter(has_text="Synthetic A").click()
        expect(page.locator("#flow-explanation")).to_contain_text("历史分析：资料已变化")
        reveal_control(page, "#flow-explanation .flow-fit-details")
        page.locator("#flow-explanation .flow-fit-details > summary").click()
        expect(page.locator("#flow-explanation")).to_contain_text("已支持 100/100")
        expect(page.locator("#flow-explanation")).to_contain_text(
            "Documentary implementation evidence."
        )
        open_internal_management(page)
        select_saved_job(page, second.get_by_role("button", name="选择已有岗位"))
        expect(second).not_to_contain_text("历史结果")
        expect(page.locator("#flow-explanation")).not_to_contain_text("历史结果")
        after = instance.server.application_flow_service.snapshot()["active_task"]
        assert after["id"] == before["id"] and after["analysis_id"] == before["analysis_id"]
        assert len(work["calls"]) == calls and not work["exports"]
        page.reload()
        open_internal_management(page)
        page.locator("#flow-task-list button").filter(has_text="Synthetic A").click()
        expect(page.locator("#flow-explanation")).to_contain_text("历史分析：资料已变化")
        expect(second).not_to_contain_text("历史结果")


def test_documentary_hard_condition_still_requires_explicit_applicant_fact(
    portal, tmp_path, browser_page
):
    from playwright.sync_api import expect

    ApplicationStore(portal.applications).create_application(
        {
            "company": "Synthetic",
            "role_title": "Engineer",
            "job_description": "Build Python services. A work permit is required.",
        }
    )

    def documentary_requirement(application, snapshot):
        return [
            model_output(snapshot)["requirements"][0]
            | {
                "text": "Work permit",
                "hard_condition": True,
            }
        ]

    page = browser_page
    with explanation_portal(portal, tmp_path, extra_requirements=documentary_requirement) as (
        _instance,
        work,
    ):
        page.goto(_instance.origin + "/#flow")
        open_internal_management(page)
        select_saved_job(
            page, page.locator("#flow-saved-jobs").get_by_role("button", name="选择已有岗位")
        )
        reveal_control(page, "#flow-start-analysis")
        page.locator("#flow-start-analysis").click()
        detail = page.locator("#flow-explanation")
        expect(detail).to_contain_text("已支持 100/100")
        expect(detail).to_contain_text("资格待补充")
        expect(page.locator("#flow-start-resume")).to_be_disabled()
        fact = page.get_by_label("Work permit · 事实说明")
        open_analysis_details(page)
        expect(fact).to_be_visible()
        fact.fill("Synthetic user fact: I hold the applicable work permit.")
        page.get_by_label("Work permit · 是否符合").select_option("true")
        page.get_by_role("button", name="保存硬条件说明").click()
        expect(detail).to_contain_text("资格已确认支持")
        expect(detail).to_contain_text("已支持 100/100")
        expect(page.locator("#flow-start-resume")).to_be_enabled()
        if page.locator("#flow-analysis-details").get_attribute("open") is None:
            open_analysis_details(page)
        page.get_by_label("Work permit · 是否符合").select_option("false")
        fact.fill("Synthetic correction: I do not hold this permit.")
        page.get_by_role("button", name="保存硬条件说明").click()
        expect(detail.locator(".flow-fit-count.flow-fit-gap strong")).to_have_text("1")
        expect(detail.locator(".flow-fit-count.flow-fit-supported strong")).to_have_text("1")
        expect(detail.locator(".flow-explanation")).to_contain_text("Synthetic correction")
        expect(page.locator("#flow-start-resume")).to_be_disabled()
        assert not work["exports"]


def test_mixed_requirements_distinguish_unknown_from_gap_and_keep_last_conflict_reachable(
    portal, tmp_path, browser_page
):
    from playwright.sync_api import expect

    ApplicationStore(portal.applications).create_application(
        {
            "company": "Synthetic Mixed",
            "role_title": "Engineer",
            "job_description": "Synthetic requirements.",
        }
    )

    def mixed_requirements(application, snapshot):
        supported = model_output(snapshot)["requirements"][0]
        return [
            supported | {"text": "Partially evidenced skill", "judgment": "partial"},
            supported | {"text": "Unconfirmed gap proposal", "judgment": "gap"},
            supported
            | {
                "text": "Unverifiable supported proposal",
                "citations": [
                    {
                        "source_id": supported["source_ids"][0],
                        "quote": "Absent synthetic quotation.",
                    }
                ],
            },
            *[
                {
                    "text": f"Unverified hard condition {index}",
                    "importance": "required",
                    "judgment": "unknown",
                    "hard_condition": True,
                    "explanation": "No applicable applicant fact is recorded.",
                    "source_ids": [],
                    "citations": [],
                    "claim_scope": "unknown",
                }
                for index in range(12)
            ],
        ]

    page = browser_page
    page.set_viewport_size({"width": 1280, "height": 800})
    with explanation_portal(portal, tmp_path, extra_requirements=mixed_requirements) as (
        instance,
        work,
    ):
        page.goto(instance.origin + "/#flow")
        open_internal_management(page)
        select_saved_job(page, page.get_by_role("button", name="选择已有岗位"))
        reveal_control(page, "#flow-start-analysis")
        page.locator("#flow-start-analysis").click()
        detail = page.locator("#flow-explanation")
        for category, count in (("supported", 1), ("partial", 1), ("gap", 0), ("unknown", 14)):
            expect(detail.locator(f".flow-fit-count.flow-fit-{category} strong")).to_have_text(
                str(count)
            )
        expect(detail.locator(".flow-fit-status")).to_have_text("资格信息待核对")
        expect(detail.locator(".flow-fit-note").filter(has_text="不代表不符合")).to_contain_text(
            "不代表不符合"
        )
        expect(detail.locator(".flow-fit-list li")).to_have_count(4)
        reveal_control(page, "#flow-explanation .flow-fit-details")
        detail.locator(".flow-fit-details > summary").click()
        invalid = detail.locator(".flow-requirement").filter(
            has_text="Unverifiable supported proposal"
        )
        expect(invalid).to_contain_text("资料未知")
        expect(invalid).to_contain_text("这项引用暂不能支持匹配判断")
        reveal_control(page, "#flow-explanation .flow-fit-details")
        detail.locator(".flow-fit-details > summary").click()
        page.evaluate("scrollTo(0, 0)")
        box = detail.bounding_box()
        assert box and box["y"] >= 0 and box["height"] <= 650 and box["y"] + box["height"] <= 800
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
        open_analysis_details(page)
        page.get_by_label("Unverified hard condition 11 · 事实说明").fill(
            "Synthetic confirmed conflict."
        )
        page.get_by_label("Unverified hard condition 11 · 是否符合").select_option("false")
        page.get_by_label("Unverified hard condition 11 · 事实说明").locator(
            "xpath=ancestor::form"
        ).get_by_role("button", name="保存硬条件说明").click()
        expect(detail.locator(".flow-fit-status")).to_have_text("存在硬条件冲突")
        expect(detail.locator(".flow-explanation")).to_contain_text("Unverified hard condition 11")
        expect(detail.locator(".flow-fit-count.flow-fit-unknown strong")).to_have_text("13")
        expect(detail.locator(".flow-fit-count.flow-fit-gap strong")).to_have_text("1")
        expect(page.locator("#flow-start-resume")).to_be_disabled()
        for index in range(6, 11):
            if page.locator("#flow-analysis-details").get_attribute("open") is None:
                open_analysis_details(page)
            fact = page.get_by_label(f"Unverified hard condition {index} · 事实说明")
            fact.fill(f"Synthetic confirmed conflict {index}.")
            page.get_by_label(f"Unverified hard condition {index} · 是否符合").select_option(
                "false"
            )
            fact.locator("xpath=ancestor::form").get_by_role(
                "button", name="保存硬条件说明"
            ).click()
            expect(detail.locator(".flow-fit-count.flow-fit-gap strong")).to_have_text(
                str(index - 4)
            )
            expect(page.locator("#flow-root")).to_have_attribute("aria-busy", "false")
            expect(detail.locator(".flow-explanation")).to_contain_text(
                f"Unverified hard condition {index}"
            )
        conflicts = detail.locator(".flow-fit-conflicts")
        expect(conflicts.locator("strong")).to_contain_text("6 项硬条件冲突")
        expect(conflicts).to_contain_text("其他岗位要求")
        expect(detail.locator("#flow-fit-details")).to_have_attribute("open", "")
        for index in range(6, 12):
            expect(detail.locator(".flow-explanation")).to_contain_text(
                f"Unverified hard condition {index}"
            )
        expect(detail.locator(".flow-fit-count.flow-fit-gap strong")).to_have_text("6")
        expect(detail.locator(".flow-fit-count.flow-fit-unknown strong")).to_have_text("8")
        assert not work["exports"]
