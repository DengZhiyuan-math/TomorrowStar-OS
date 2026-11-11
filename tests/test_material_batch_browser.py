"""Finite material batches use current controls and preserve per-job checkpoints.

These journeys do not revive retired raw-HTML generation or its review button.
Complete generated-LaTeX review/export transitions are also exercised in
reviewed_latex_pdf_flow and material_batch_http.
"""

import json
import sys

import pytest
from latex_browser_support import review_all_groups
from test_application_intake import message
from test_application_intake import page as job_page
from test_application_resume import task_resume as task_resume
from test_automatic_material_editor_browser import serving
from test_automatic_material_reuse_edit import complete_portal as complete_portal
from test_career_portal_http import Portal
from test_career_portal_http import portal as portal
from test_full_latex_generation import full_latex as full_latex
from test_job_explanation_browser import explanation_portal, reveal_control
from test_pdf_export_browser import assert_automatic_binding
from test_pdf_export_http import create_authorized_latex
from test_portal_workflow_browser import browser_page as browser_page
from test_preparation_entry import snapshot

from career_evidence_graph.career_portal_data import ApplicationStore, PortalDataError

pytestmark = pytest.mark.worker_browser


@pytest.fixture(autouse=True)
def isolated_model_context(tmp_path, monkeypatch):
    codex_home = tmp_path / "synthetic-codex-home"
    codex_home.mkdir()
    monkeypatch.setenv("CODEX_HOME", str(codex_home))
    monkeypatch.setenv("TOMORROWSTAR_CODEX_EXECUTABLE", sys.executable)
    monkeypatch.delenv("CODEX_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)


def create_jobs(applications, companies):
    return [
        applications.create_application(
            {
                "company": company,
                "role_title": "Engineer",
                "job_description": "Build Python services.",
            }
        )
        for company in companies
    ]


def choose_jobs(page, jobs):
    """Open the real per-job settings, then check only the requested selections."""
    for job in jobs:
        choice = page.locator(
            f'#flow-job-management details[data-application-id="{job["id"]}"]'
        ).locator('input[type="checkbox"]')
        reveal_control(page, choice)
        choice.check()


def create_batch(page):
    page.locator("#flow-batch-create").click()
    reveal_control(page, "#flow-batch-resume")
    return page.locator("#flow-material-batch")


def test_explicit_finite_selection_saves_paused_batch_without_running_work(
    portal, tmp_path, browser_page
):
    from playwright.sync_api import expect

    jobs = create_jobs(
        ApplicationStore(portal.applications),
        ["First Company", "Second Company", "Unselected Company"],
    )
    page = browser_page
    with explanation_portal(portal, tmp_path) as (active, work):
        page.goto(active.origin + "/#flow")
        reveal_control(page, "#flow-batch-create")
        expect(page.locator("#flow-batch-create")).to_be_disabled()
        choose_jobs(page, jobs[:2])
        batch = create_batch(page)
        expect(batch).to_contain_text("材料批次已暂停")
        for company in ("First Company", "Second Company"):
            expect(batch).to_contain_text(company)
        expect(batch).not_to_contain_text("Unselected Company")
        assert not work["calls"] and not work["exports"]
        assert snapshot(active)["tasks"] == []
        page.reload()
        page.locator("#flow-observe").click()
        reveal_control(page, "#flow-batch-resume")
        expect(batch).to_contain_text("材料批次已暂停")
        assert snapshot(active)["tasks"] == []
        assert not work["calls"] and not work["exports"]


@pytest.mark.parametrize("complete_portal", [{"preparation_only": True}], indirect=True)
def test_retained_latex_batch_waits_for_application_record_before_the_next(
    complete_portal, browser_page
):
    from playwright.sync_api import expect

    server, store, task, calls = complete_portal
    first = store.applications.get_application(task["application_id"])
    next_job = create_jobs(store.applications, ["Synthetic Next"])[0]
    before = len(calls)
    page = browser_page
    with serving(server):
        active = Portal(server, store.applications.root, store.catalog.root)
        page.goto(active.origin + "/#flow")
        choose_jobs(page, [first, next_job])
        batch = create_batch(page)
        page.locator("#flow-batch-resume").click()
        expect(batch).to_contain_text("等待投递结果记录；真实申请继续暂停")
        expect(page.locator("#flow-pdf-link")).to_have_attribute(
            "href", f"/api/flow/resumes/{task['resume_id']}/pdf"
        )
        expect(page.locator("#flow-batch-resume")).to_be_disabled()
        page.reload()
        page.locator("#flow-observe").click()
        state = snapshot(active)
        assert state["active_task"] == task
        assert_automatic_binding(state["active_task"])
        assert len(state["tasks"]) == 1
        assert sum(bool(item["task_id"]) for item in state["preparation_batch"]["items"]) == 1
        assert len(calls) == before and len(store.prism_client.calls) == 1
        assert server.worker_service is None
        for selector in ("#flow-worker", "#flow-confirm-materials", "#flow-reviewed-pdf"):
            expect(page.locator(selector)).to_have_count(0)


@pytest.mark.parametrize(
    "complete_portal", [{"preparation_only": True, "stop_before_export": True}], indirect=True
)
def test_manual_pending_order_and_pause_preserve_retained_latex_draft_across_reload(
    complete_portal, browser_page
):
    from playwright.sync_api import expect

    server, store, task, calls = complete_portal
    first = store.applications.get_application(task["application_id"])
    jobs = [first, *create_jobs(store.applications, ["Beta Company", "Gamma Company"])]
    saved_draft = store.draft(task["draft_id"])
    before = len(calls)
    page = browser_page
    with serving(server):
        active = Portal(server, store.applications.root, store.catalog.root)
        page.goto(active.origin + "/#flow")
        choose_jobs(page, jobs)
        batch = create_batch(page)
        rows = batch.locator("[data-batch-item]")
        expect(rows).to_have_count(3)
        initial = rows.locator("h3").all_text_contents()
        rows.last.get_by_role("button", name="上移", exact=True).click()
        expect(rows.nth(1).locator("h3")).to_have_text(initial[2])
        expect(rows.nth(2).locator("h3")).to_have_text(initial[1])
        page.locator("#flow-batch-resume").click()
        expect(batch).to_contain_text("等待草稿审阅")
        page.locator("#flow-batch-pause").click()
        expect(batch).to_contain_text("材料批次已暂停")
        expect(rows.first.get_by_role("button", name="下移", exact=True)).to_be_disabled()
        page.reload()
        page.locator("#flow-observe").click()
        reveal_control(page, "#flow-batch-resume")
        expect(batch).to_contain_text("材料批次已暂停")
        assert snapshot(active)["active_task"] == task
        assert store.draft(task["draft_id"]) == saved_draft
        assert len(calls) == before and store.prism_client.calls == []
        page.locator("#flow-batch-cancel").click()
        expect(batch).to_contain_text("材料批次已取消")
        cancelled = snapshot(active)["active_task"]
        assert cancelled["status"] == "cancelled"
        assert {
            key: value for key, value in cancelled.items() if key not in {"status", "revision"}
        } == {key: value for key, value in task.items() if key not in {"status", "revision"}}
        assert store.draft(task["draft_id"]) == saved_draft
        assert len(calls) == before and store.prism_client.calls == []


def test_json_delivery_failure_and_missing_qualification_keep_reasons_and_manual_retry(
    portal, tmp_path, browser_page
):
    from playwright.sync_api import expect

    jobs = create_jobs(
        ApplicationStore(portal.applications), ["Failure Company", "Missing Company"]
    )
    missing_permit = {
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
        portal, tmp_path, extra_requirements={"Missing Company": [missing_permit]}
    ) as (active, work):
        page.goto(active.origin + "/#flow")
        choose_jobs(page, jobs)
        batch = create_batch(page)
        page.locator("#flow-batch-resume").click()
        rows = batch.locator("[data-batch-item]")
        failure = rows.filter(has=page.get_by_role("heading", name="Failure Company · Engineer"))
        missing = rows.filter(has=page.get_by_role("heading", name="Missing Company · Engineer"))
        expect(failure).to_contain_text("待处理 · 手动重试")
        expect(failure).to_contain_text("resume_content_material_required")
        expect(missing).to_contain_text("待补充 · 手动重试")
        expect(missing).to_contain_text("必需资格待补充")
        expect(batch).to_contain_text("材料批次已暂停")
        state = snapshot(active)
        task = next(row for row in state["tasks"] if row["application_id"] == jobs[0]["id"])
        assert task["material_contract"] == "content-writing/v1"
        assert task["stages"]["resume"]["error_code"] == "resume_content_material_required"
        before = len(work["calls"])
        assert before == 4 and work["exports"] == []
        assert sum(call[-1] == "--version" for call in work["calls"]) == 2
        executions = [call for call in work["calls"] if "exec" in call]
        assert [
            json.loads(call[-1].rsplit("\n", 1)[1])["job"]["company"] for call in executions
        ] == ["Failure Company", "Missing Company"]
        page.reload()
        page.locator("#flow-observe").click()
        reveal_control(page, "#flow-batch-resume")
        expect(failure).to_contain_text("待处理 · 手动重试")
        assert len(work["calls"]) == before
        failure.get_by_role("button", name="重试该岗", exact=True).click()
        expect(failure).to_contain_text("等待处理")
        page.locator("#flow-batch-resume").click()
        expect(failure).to_contain_text("待处理 · 手动重试")
        expect(missing).to_contain_text("待补充 · 手动重试")
        again = next(row for row in snapshot(active)["tasks"] if row["id"] == task["id"])
        assert again["stages"]["resume"]["error_code"] == "resume_content_material_required"
        assert not again.get("draft_id") and not again.get("resume_id")
        assert len(work["calls"]) == before and work["exports"] == []


@pytest.mark.parametrize(
    "complete_portal",
    [
        {
            "preparation_only": True,
            "grouped_review": True,
            "stop_before_export": True,
        }
    ],
    indirect=True,
)
def test_unknown_grouped_latex_export_stops_batch_until_recheck_then_waits_for_application_record(
    complete_portal, browser_page
):
    from playwright.sync_api import expect

    server, store, initial, calls = complete_portal
    first_job = store.applications.get_application(initial["application_id"])
    jobs = [first_job, *create_jobs(store.applications, ["Synthetic Next"])]
    exports = []
    original = store.export_for_draft

    def unknown(*args, **kwargs):
        exports.append(kwargs["export_id"])
        original(*args, **kwargs)
        raise PortalDataError("resume_export_needs_recheck", "Synthetic lost response.", 503)

    store.export_for_draft = unknown
    page = browser_page
    with serving(server):
        active = Portal(server, store.applications.root, store.catalog.root)
        page.goto(active.origin + "/#flow")
        review_all_groups(page)
        call_count = len(calls)
        choose_jobs(page, jobs)
        batch = create_batch(page)
        page.locator("#flow-batch-resume").click()
        expect(batch).to_contain_text("材料批次结果待核验")
        expect(page.locator("#flow-recheck-export")).to_be_visible()
        expect(page.locator("#flow-batch-cancel")).to_be_disabled()
        expect(batch.get_by_role("button", name="重试该岗", exact=True)).to_have_count(0)
        unknown_task = snapshot(active)["active_task"]
        assert exports == [unknown_task["stages"]["export"]["attempt_id"]]
        assert unknown_task["stages"]["export"]["status"] == "needs_recheck"
        page.reload()
        page.locator("#flow-observe").click()
        reveal_control(page, "#flow-batch-resume")
        resume = page.locator("#flow-batch-resume")
        expect(resume).to_have_text("核验后继续材料批次")
        resume.click()
        expect(page.locator("#flow-notice")).to_contain_text("核验")
        expect(batch).to_contain_text("材料批次结果待核验")
        assert len(exports) == 1 and store.group_prism_client.calls == ["compile"]
        assert store.prism_client.calls == [] and len(calls) == call_count
        reveal_control(page, "#flow-recheck-export")
        page.locator("#flow-recheck-export").click()
        expect(page.locator("#flow-pdf-link")).to_be_visible()
        recovered = snapshot(active)["active_task"]
        assert recovered["resume_id"] == unknown_task["stages"]["export"]["attempt_id"]
        assert_automatic_binding(recovered)
        # The completed material does not authorize another application.
        expect(batch).to_contain_text("等待投递结果记录")
        expect(resume).to_be_disabled()
        state = snapshot(active)
        assert state["preparation_batch"]["control"] == "paused"
        assert len(state["tasks"]) == 1
        assert sum(bool(item["task_id"]) for item in state["preparation_batch"]["items"]) == 1
        assert len(exports) == 1 and store.group_prism_client.calls == ["compile"]
        assert store.prism_client.calls == [] and len(calls) == call_count
        assert server.worker_service is None


@pytest.mark.parametrize("complete_portal", [{"preparation_only": True}], indirect=True)
def test_batch_keeps_completed_latex_jd_draft_and_pdf_with_its_task(complete_portal, browser_page):
    from playwright.sync_api import expect

    server, store, first, calls = complete_portal
    applications = server.application_flow_service.applications
    assert store.applications.root == applications.root
    store.applications = applications
    first_job = store.applications.get_application(first["application_id"])
    next_job = create_jobs(store.applications, ["Second Company"])[0]
    count = len(calls)
    page = browser_page
    with serving(server):
        active = Portal(server, store.applications.root, store.catalog.root)
        second = create_authorized_latex(active, next_job)
        page.goto(active.origin + "/#flow")
        choose_jobs(page, [first_job, next_job])
        batch = create_batch(page)
        page.locator("#flow-batch-resume").click()
        expect(batch).to_contain_text("等待投递结果记录")
        rows = batch.locator("[data-batch-item]")
        first_row = rows.filter(has=page.locator(f'[data-batch-task="{first["id"]}"]'))
        first_row.get_by_text("核对本岗 JD、来源与材料版本", exact=True).click()
        for value in (
            first["job_description"],
            first["inputs"]["jd_revision"],
            first["inputs"]["sources_revision"],
            first["draft_id"],
            first["draft_sha256"],
            first["resume_id"],
            first["resume_sha256"],
        ):
            expect(first_row).to_contain_text(value)
        expect(first_row).not_to_contain_text(second["draft_id"])
        assert_automatic_binding(snapshot(active)["active_task"])
        next_row = rows.filter(has=page.get_by_role("heading", name="Second Company · Engineer"))
        expect(next_row.locator("[data-batch-task]")).to_have_count(0)
        expect(next_row).not_to_contain_text(first["draft_id"])
        reveal_control(page, page.locator("#flow-task-list button").first)
        page.locator("#flow-task-list button").filter(has_text="Second Company").click()
        expect(page.locator("#flow-pdf-link")).to_have_count(0)
        reveal_control(page, "#flow-draft")
        expect(page.locator("#flow-draft")).to_contain_text(second["draft_id"])
        first_row.get_by_role("button", name="打开此岗任务", exact=True).click()
        expect(page.locator("#flow-pdf-link")).to_have_attribute(
            "href", f"/api/flow/resumes/{first['resume_id']}/pdf"
        )
        assert (
            store.draft(first["draft_id"])["source_checkpoint"]
            != store.draft(second["draft_id"])["source_checkpoint"]
        )
        assert len(calls) == count and len(store.prism_client.calls) == 1
        assert not server.application_flow_service.task_snapshot(second["id"])["resume_id"]
        assert server.worker_service is None


def test_gmail_batch_reuses_captured_jd_and_requires_current_json_delivery(
    portal, tmp_path, browser_page
):
    from playwright.sync_api import expect

    page, posts = browser_page, []
    page.on(
        "request", lambda request: posts.append(request.url) if request.method == "POST" else None
    )
    with explanation_portal(portal, tmp_path) as (active, work):
        reads, captures = [], []

        def reader(directory, **options):
            reads.append(options)
            return {
                "status": "readable",
                "emails": [message()],
                "provenance": {"source": "synthetic"},
            }

        def fetcher(url):
            captures.append(url)
            return job_page(url)

        intake = active.server.application_intake_service
        intake.reader, intake.fetcher = reader, fetcher
        page.goto(active.origin + "/#flow")
        assert not reads and not captures and not work["calls"]
        reveal_control(page, "#flow-refresh-mail")
        page.locator("#flow-refresh-mail").click()
        candidates = page.locator("#flow-candidates")
        expect(candidates).to_contain_text("Synthetic Labs")
        expect(candidates.get_by_role("button", name="打开已有申请任务")).to_be_enabled()
        applications = ApplicationStore(portal.applications)
        jobs = applications.list_applications()
        recommendation = intake.snapshot()["recommendations"][0]
        assert len(jobs) == 1 and recommendation["selection_status"] == "saved"
        assert jobs[0]["id"] == recommendation["existing_application"]["id"]
        assert jobs[0]["job_description"] == recommendation["job_description"]
        assert snapshot(active)["tasks"] == [] and not work["calls"] and not work["exports"]
        choice = page.locator("#flow-recommendation-management").locator(
            f'[data-recommendation-settings="{recommendation["id"]}"] input[type="checkbox"]'
        )
        reveal_control(page, choice)
        choice.check()
        batch = create_batch(page)
        expect(batch).to_contain_text("材料批次已暂停")
        assert len(reads) == len(captures) == 1 and not work["calls"]
        page.locator("#flow-batch-resume").click()
        expect(batch).to_contain_text("待处理 · 手动重试")
        state = snapshot(active)
        task = state["active_task"]
        assert task["application_id"] == jobs[0]["id"]
        assert task["job_description"] == recommendation["job_description"]
        assert task["material_contract"] == "content-writing/v1"
        assert task["stages"]["resume"]["error_code"] == "resume_content_material_required"
        assert not task.get("draft_id") and not task.get("resume_id")
        assert len(reads) == len(captures) == len(state["tasks"]) == 1
        assert len(work["calls"]) == 2
        assert sum(call[-1] == "--version" for call in work["calls"]) == 1
        executions = [call for call in work["calls"] if "exec" in call]
        assert len(executions) == 1
        assert (
            json.loads(executions[0][-1].rsplit("\n", 1)[1])["job"]["company"] == "Synthetic Labs"
        )
        assert work["exports"] == [] and len(applications.list_applications()) == 1
        assert applications.get_application(jobs[0]["id"])["status"] == "drafting"
        assert active.server.worker_service is None
        expect(page.locator("#flow-worker")).to_have_count(0)
        assert not any(
            "/worker/" in url or url.endswith(("/prepare-worker", "/worker-action"))
            for url in posts
        )
