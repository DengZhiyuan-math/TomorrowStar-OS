"""Synthetic loopback journeys for explicit single-job actions; no external ATS."""

import hashlib
import json
import time
from contextlib import contextmanager
from functools import partial
from pathlib import Path
from tempfile import mkdtemp
from uuid import uuid4

import pytest
from test_application_intake import message
from test_application_intake import page as captured_page
from test_application_match import model_output, model_runner
from test_career_portal_http import _running_portal
from test_career_portal_http import portal as portal
from test_job_explanation_browser import reveal_control
from test_portal_workflow_browser import browser_page as browser_page

from career_evidence_graph._vendor.job_apply_store import atomic_write_json
from career_evidence_graph.application_intake import ApplicationIntakeService
from career_evidence_graph.application_match import analyze_job
from career_evidence_graph.application_resume import (
    ApplicationResumeStore,
    career_source_snapshot,
    draft_resume,
    resume_configuration_revision,
)
from career_evidence_graph.career_portal_data import ApplicationStore, CareerCatalog

pytestmark = pytest.mark.worker_browser


@contextmanager
def flow_portal(portal, tmp_path, *, output=None, worker=False):
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
    snapshot = career_source_snapshot(CareerCatalog(portal.career))
    calls, reads, exports = [], [], []

    def reader(directory, **kwargs):
        reads.append(kwargs)
        directory.mkdir()
        return {"status": "readable", "emails": [message()], "provenance": {}}

    def intake_factory(applications, root):
        return ApplicationIntakeService(applications, root, reader=reader, fetcher=captured_page)

    def exporter(html, pdf):
        exports.append(pdf)
        pdf.write_bytes(
            (Path(__file__).parent / "fixtures/pdf-export/current-template.pdf").read_bytes()
        )

    class LegacyResumeFixtureStore(ApplicationResumeStore):
        """Retained PDF producer double; no retired HTML implementation executes."""

        def generate_for_task(self, identifier, revision, *, source_snapshot, analysis, **options):
            application = self._task_current(identifier, source_snapshot, analysis)
            assert application["revision"] == revision
            draft = draft_resume(
                application,
                self.catalog,
                source_snapshot=source_snapshot,
                selected_source_ids=analysis["selected_source_ids"],
            )
            version = uuid4().hex
            directory = self.root / version
            directory.mkdir()
            self.exporter(None, directory / "resume.pdf")
            pdf_sha256 = hashlib.sha256(self.pdf(version)).hexdigest()
            analysis_binding = {
                "analysis_id": analysis["id"],
                **{
                    key: analysis[key]
                    for key in (
                        "jd_revision",
                        "source_snapshot_revision",
                        "configuration_revision",
                        "policy_version",
                    )
                },
            }
            # Reuse the archived legacy-PDF shape from the single-binding
            # fixtures. The production reader still verifies source/PDF identity.
            atomic_write_json(
                directory / "sources.json",
                draft
                | {
                    "pdf_sha256": pdf_sha256,
                    "generation_policy": self.configuration(),
                    "analysis_binding": analysis_binding,
                },
            )
            return {
                "id": version,
                "application_id": identifier,
                "revision": revision,
                "pdf_sha256": pdf_sha256,
                "resume_configuration_revision": resume_configuration_revision(self),
                "analysis_binding": analysis_binding,
                "items": draft["items"],
                "limitations": draft["limitations"],
                "context_count": len(draft["context"]),
            }

    def resume_factory(applications, catalog, root):
        return LegacyResumeFixtureStore(
            applications,
            catalog,
            root,
            tailorer=lambda draft, application, directory: draft | {"generation": "codex"},
            exporter=exporter,
        )

    analysis_output = model_output(snapshot)
    if output:
        analysis_output = output(analysis_output) if callable(output) else output
    with _running_portal(
        portal.applications,
        portal.career,
        flow_root=tmp_path / "flow",
        flow_intake_factory=intake_factory,
        flow_analyzer=partial(analyze_job, runner=model_runner(analysis_output, calls)),
        flow_resume_factory=resume_factory,
        worker_root=tmp_path / "worker" if worker else None,
        worker_fixtures=worker,
        worker_headless=worker,
    ) as instance:
        yield instance, {"calls": calls, "reads": reads, "exports": exports}


def _portal_request(instance, path, payload=None):
    method = "GET" if payload is None else "POST"
    status, _, raw = instance.request(
        method,
        path,
        body=json.dumps(payload).encode() if payload is not None else None,
        headers=instance.write_headers() if payload is not None else {},
    )
    assert status == 200, raw
    return json.loads(raw)


def _create_retained_task(instance, identifier):
    application = _portal_request(instance, f"/api/applications/{identifier}")["application"]
    task = _portal_request(
        instance,
        "/api/flow/create",
        {
            "application_id": application["id"],
            "application_revision": application["revision"],
        },
    )
    # These recovery/UI fixtures resume saved tasks from before content JSON.
    # A newly created task must keep its contract in the default application flow.
    flow = instance.server.application_flow_service
    with flow.applications.write_lock():
        state = flow._load()
        flow._task(state, task["id"]).pop("material_contract", None)
        flow._save(state)
    return flow.snapshot(task["id"])["active_task"]


def _select_retained_recommendation(instance, page):
    # Exercise a retained standalone caller through real HTTP. Current default
    # selection goes through Pipeline and cannot initialize these legacy tasks.
    _portal_request(instance, "/api/recommendations/refresh", {})
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline:
        state = _portal_request(instance, "/api/recommendations/state")
        if state["status"] == "complete":
            break
        time.sleep(0.01)
    assert state["status"] == "complete", state
    row = state["recommendations"][0]
    application = _portal_request(
        instance, "/api/recommendations/select", {"id": row["id"], "revision": row["revision"]}
    )["application"]
    _create_retained_task(instance, application["id"])
    page.goto(instance.origin + "/#flow")
    reveal_control(page, "#flow-task-list button")
    page.locator("#flow-task-list button").click()


def test_reopening_observes_and_default_admission_retains_one_queued_job(
    portal, tmp_path, browser_page
):
    from playwright.sync_api import expect

    page = browser_page
    writes = []
    page.on(
        "request", lambda request: writes.append(request.url) if request.method == "POST" else None
    )
    with flow_portal(portal, tmp_path, worker=True) as (instance, work):
        fetches = []
        intake = instance.server.application_intake_service
        original_fetch = intake.fetcher

        def fetch(url):
            fetches.append(url)
            return original_fetch(url)

        intake.fetcher = fetch
        page.goto(instance.origin + "/#flow")
        expect(page.locator("#flow-title")).to_have_text("自动申请")
        expect(page.locator("#flow-refresh-mail")).to_be_enabled()
        page.reload()
        expect(page.locator("#flow-refresh-mail")).to_be_enabled()
        assert not writes and not work["reads"] and not work["calls"]
        reveal_control(page, "#flow-refresh-mail")
        page.locator("#flow-refresh-mail").click()
        expect(page.locator(".flow-recommendation")).to_have_count(1)
        expect(page.locator(".flow-recommendation")).to_contain_text("尚未取得完整 JD")
        page.get_by_role("button", name="加入申请队列", exact=True).click()
        expect(page.get_by_role("button", name="已加入申请队列", exact=True)).to_be_disabled()
        pipeline = instance.server.application_pipeline_service
        saved = pipeline.snapshot()
        assert saved["control"] == "paused" and saved["active_task_id"] is None
        assert len(saved["items"]) == 1
        assert len(work["reads"]) == 1 and not fetches
        assert not work["calls"] and not work["exports"]
        assert instance.server.application_flow_service.snapshot()["tasks"] == []
        page.reload()
        reveal_control(page, "#flow-candidates")
        expect(page.get_by_role("button", name="已加入申请队列", exact=True)).to_be_disabled()
        assert pipeline.snapshot()["items"] == saved["items"]
        assert len(writes) == 2
        assert not work["calls"]


def test_analysis_materials_and_explicit_regeneration_keep_manual_confirmation(
    portal, tmp_path, browser_page
):
    from playwright.sync_api import expect

    def uncertain_requirement(output):
        output["requirements"].append(
            {
                "text": "Rust",
                "importance": "preferred",
                "judgment": "unknown",
                "hard_condition": False,
                "explanation": "No available Rust evidence.",
                "source_ids": [],
                "citations": [],
                "claim_scope": "unknown",
            }
        )
        return output

    page = browser_page
    with flow_portal(portal, tmp_path, output=uncertain_requirement) as (instance, work):
        _select_retained_recommendation(instance, page)
        reveal_control(page, "#flow-start-analysis")
        page.locator("#flow-start-analysis").click()
        expect(page.locator("#flow-analysis")).to_contain_text("已支持 75/100")
        expect(page.locator("#flow-analysis")).to_contain_text("可能 75–100")
        expect(page.locator("#flow-analysis")).to_contain_text("证据覆盖 75%")
        expect(page.locator("#flow-analysis")).to_contain_text("必需项 3 · 加分项 1 · 部分支持 0.5")
        expect(page.locator("#flow-analysis")).to_contain_text("未知不代表能力不足")
        expect(page.locator("#flow-analysis")).to_contain_text("历史参考尚不可用")
        assert not work["exports"]
        reveal_control(page, "#flow-start-resume")
        page.locator("#flow-start-resume").click()
        expect(page.locator("#flow-pdf-link")).to_be_visible()
        expect(page.locator("#flow-materials")).to_contain_text("No GPU training claim.")
        expect(page.locator("#flow-confirm-materials")).to_have_count(0)
        expect(page.locator("#flow-reviewed-pdf")).to_have_count(0)
        expect(page.locator("#flow-task")).to_contain_text("PDF 已生成")
        page.reload()
        expect(page.locator("#flow-pdf-link")).to_be_visible()
        saved = instance.server.application_flow_service.snapshot()["active_task"]
        first_pdf = saved["resume_id"]
        assert saved["materials_confirmed"] is False and saved["worker_ref"] is None
        reveal_control(page, "#flow-regenerate-resume")
        page.locator("#flow-regenerate-resume").click()
        page.locator("#confirmation-continue").click()
        expect(page.locator("#flow-reviewed-pdf")).to_have_count(0)
        expect(page.locator("#flow-confirm-materials")).to_have_count(0)
        expect(page.locator("#flow-pdf-link")).not_to_have_attribute(
            "href", f"/api/flow/resumes/{first_pdf}/pdf"
        )
        current = instance.server.application_flow_service.snapshot()["active_task"]
        assert current["materials_confirmed"] is False
        assert current["resume_id"] != first_pdf and len(work["exports"]) == 2


def test_hard_condition_clarification_keeps_input_and_never_changes_match_score(
    portal, tmp_path, browser_page
):
    from playwright.sync_api import expect

    def hard_condition(output):
        output["requirements"].append(
            {
                "text": "Work permit",
                "importance": "required",
                "judgment": "unknown",
                "hard_condition": True,
                "explanation": "Applicant fact is unknown.",
                "source_ids": [],
                "citations": [],
                "claim_scope": "unknown",
            }
        )
        return output

    page = browser_page
    with flow_portal(portal, tmp_path, output=hard_condition) as (instance, work):
        _select_retained_recommendation(instance, page)
        reveal_control(page, "#flow-start-analysis")
        page.locator("#flow-start-analysis").click()
        expect(page.locator("#flow-analysis")).to_contain_text("资格信息尚不明确，继续准备")
        fact = page.get_by_label("Work permit · 事实说明")
        reveal_control(page, '[aria-label="Work permit · 事实说明"]')
        fact.fill("Synthetic fact: I do not have the required permit.")
        page.locator("#flow-observe").click()
        expect(fact).to_have_value("Synthetic fact: I do not have the required permit.")
        page.get_by_label("Work permit · 是否符合").select_option("false")
        page.get_by_role("button", name="保存硬条件说明").click()
        expect(page.locator("#flow-analysis")).to_contain_text("存在硬条件冲突")
        expect(page.locator("#flow-analysis")).to_contain_text("已支持 50/100")
        expect(page.locator("#flow-analysis")).to_contain_text("可能 50–100")
        task = instance.server.application_flow_service.snapshot()["active_task"]
        assert task["hard_condition_resolutions"][0]["eligible"] is False
        assert task["worker_ref"] is None and not work["exports"]


def test_lost_admission_keeps_other_queued_work_available_and_reads_back_without_replay(
    portal, tmp_path, browser_page
):
    from playwright.sync_api import expect

    page = browser_page
    writes = []
    page.on(
        "request", lambda request: writes.append(request.url) if request.method == "POST" else None
    )
    with flow_portal(portal, tmp_path, worker=True) as (instance, work):
        app = ApplicationStore(instance.applications).create_application(
            {
                "company": "Earlier queued",
                "role_title": "Engineer",
                "job_description": "Synthetic earlier work",
            }
        )
        saved = _portal_request(
            instance,
            "/api/pipeline/admit",
            {
                "request_id": "earlier-queued-job",
                "application_id": app["id"],
                "application_revision": app["revision"],
            },
        )
        original = saved["items"][0]
        admissions = []
        before_admission = _portal_request(instance, "/api/pipeline/state")
        readback = {"released": False, "stale_reads": 0}

        def retained_readback(route):
            if readback["released"]:
                route.continue_()
            else:
                if admissions:
                    readback["stale_reads"] += 1
                route.fulfill(
                    status=200,
                    content_type="application/json",
                    body=json.dumps(before_admission),
                    headers={"X-Synthetic-Admission-Readback": "post-admit-retained"}
                    if admissions
                    else {},
                )

        page.route("**/api/pipeline/state", retained_readback)
        page.goto(instance.origin + "/#flow")
        reveal_control(page, "#flow-refresh-mail")
        page.locator("#flow-refresh-mail").click()
        expect(page.locator(".flow-recommendation")).to_have_count(1)

        def lose_receipt(route):
            admissions.append(route.request.post_data_json)
            response = route.fetch()
            assert response.status == 200, response.text()
            route.abort()

        page.route("**/api/pipeline/admit", lose_receipt)
        with page.expect_response(
            lambda response: (
                response.url == instance.origin + "/api/pipeline/state"
                and response.headers.get("x-synthetic-admission-readback") == "post-admit-retained"
            )
        ):
            page.get_by_role("button", name="加入申请队列", exact=True).click()
        expect(page.locator("#flow-notice")).to_contain_text("操作结果尚未核验")
        expect(page.locator("#flow-pipeline-start")).to_be_enabled()
        assert readback["stale_reads"] >= 1
        readback["released"] = True
        page.locator("#flow-observe").click()
        expect(page.get_by_role("button", name="已加入申请队列", exact=True)).to_be_disabled()
        expect(page.locator("#flow-pipeline-start")).to_be_enabled()
        current = instance.server.application_pipeline_service.snapshot()
        assert current["items"][0] == original and len(current["items"]) == 2
        assert current["control"] == "paused" and current["active_task_id"] is None
        assert current["admission_requests"][-1] == admissions[0]
        assert len(admissions) == 1 and len(writes) == 2
        assert len(instance.state()["applications"]) == 1
        assert instance.server.application_flow_service.snapshot()["tasks"] == []
        assert not work["calls"] and not work["exports"]


def test_saved_manual_jd_works_without_url_and_sync_is_an_explicit_invalidation(
    portal, tmp_path, browser_page
):
    from playwright.sync_api import expect

    page = browser_page
    with flow_portal(portal, tmp_path) as (instance, work):
        job = ApplicationStore(instance.applications).create_application(
            {
                "company": "Manual Synthetic",
                "role_title": "Engineer",
                "job_description": "Use Python.",
            }
        )
        page.goto(instance.origin + "/#applications")
        page.get_by_role("button", name="查看 Manual Synthetic Engineer").click()
        expect(page.locator("#open-application-flow")).to_be_enabled()
        page.locator("#application-corrections > summary").click()
        page.locator("#application-jd-editor > summary").click()
        page.locator('[name="job_description"]').fill("Use Python. Full synthetic requirements.")
        page.locator("#open-application-flow").click()
        expect(page.locator("#flow-entry-notice")).to_contain_text("请先保存修改")
        assert not instance.server.application_flow_service.snapshot()["tasks"]
        page.locator("#save-application").click()
        expect(page.locator("#application-dialog")).not_to_be_visible()
        _create_retained_task(instance, job["id"])
        page.get_by_role("button", name="查看 Manual Synthetic Engineer").click()
        page.locator("#open-application-flow").click()
        reveal_control(page, "#flow-start-analysis")
        page.locator("#flow-start-analysis").click()
        expect(page.locator("#flow-analysis")).to_contain_text("已支持 100/100")
        calls = len(work["calls"])
        source = instance.career / "contributions/python.md"
        source.write_text(source.read_text() + "\nA new synthetic source fact.\n")
        reveal_control(page, "#flow-sync-inputs")
        expect(page.locator("#flow-sync-inputs")).to_be_visible()
        page.locator("#flow-sync-inputs").click()
        page.locator("#confirmation-continue").click()
        expect(page.locator("#flow-start-analysis")).to_be_enabled()
        expect(page.locator("#flow-analysis")).to_have_count(0)
        assert len(work["calls"]) == calls
        task = instance.server.application_flow_service.snapshot()["active_task"]
        assert task["application_id"] == job["id"] and task["analysis_id"] is None
        reveal_control(page, "#flow-cancel")
        page.locator("#flow-cancel").click()
        page.locator("#confirmation-continue").click()
        expect(page.locator("#flow-task")).to_contain_text("任务已取消")


def prepare_browser_worker(page, instance, monkeypatch, *, prepare=True):
    import json
    import time

    from playwright.sync_api import expect

    service = instance.server.worker_service
    starts = []
    monkeypatch.setattr(service.store, "single_validator", lambda *args, **kwargs: None)
    monkeypatch.setattr(service, "spawn", lambda: starts.append("spawn"))
    application = ApplicationStore(instance.applications).create_application(
        {
            "company": "Single Synthetic",
            "role_title": "Engineer",
            "job_description": "Use Python.",
            "url": "https://jobs.lever.co/synthetic/11111111-1111-4111-8111-111111111111",
        }
    )

    # Build an explicit legacy task through its public standalone API. Default
    # job selection now admits to Pipeline and no longer starts manual stages.
    def post(action, payload):
        status, _, raw = instance.request(
            "POST",
            f"/api/flow/{action}",
            body=json.dumps(payload).encode(),
            headers=instance.write_headers(),
        )
        assert status == 200, raw
        return json.loads(raw)

    task = _create_retained_task(instance, application["id"])
    for stage, expected_status in (("analysis", "analysis_ready"), ("resume", "resume_ready")):
        post("start", {"task_id": task["id"], "task_revision": task["revision"], "stage": stage})
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            status, _, raw = instance.request("GET", f"/api/flow/{task['id']}")
            assert status == 200, raw
            task = json.loads(raw)["active_task"]
            assert task["stages"][stage]["status"] != "failed", task["stages"][stage]
            if task["status"] == expected_status:
                break
            time.sleep(0.01)
        assert task["status"] == expected_status, task
    page.goto(instance.origin + "/#flow")
    reveal_control(page, "#flow-task-list button")
    page.locator("#flow-task-list button").click()
    expect(page.locator("#flow-pdf-link")).to_be_visible()
    expect(page.locator("#flow-confirm-materials")).to_have_count(0)
    if not prepare:
        return service, starts
    page.locator("#flow-worker-diagnostics > summary").click()
    expect(page.locator("#flow-prepare-worker")).to_be_visible()
    expect(page.locator("#flow-prepare-worker")).to_be_disabled()
    page.get_by_label("此岗位的申请国家").select_option("CHE")
    page.locator("#flow-send-confirmed").check()
    page.locator("#flow-prepare-worker").click()
    expect(page.locator("#flow-worker-resume")).to_be_enabled()
    return service, starts


def test_worker_preparation_needs_separate_send_approval_and_explicit_start(
    portal, tmp_path, browser_page, monkeypatch
):
    from playwright.sync_api import expect

    page = browser_page
    with flow_portal(portal, tmp_path, worker=True) as (instance, work):
        service, starts = prepare_browser_worker(page, instance, monkeypatch)
        expect(page.locator("#flow-worker")).to_contain_text("已准备 · 等待开始填写")
        assert service.snapshot()["control"] == "paused" and starts == []
        job = service.snapshot()["jobs"][0]
        task = instance.server.application_flow_service.snapshot()["active_task"]
        assert job["single_binding"]["resume_sha256"] == task["resume_sha256"]
        page.locator("#flow-worker-resume").click()
        expect(page.locator("#flow-worker")).to_contain_text("填写运行中")
        assert starts == ["spawn"]
        page.locator("#flow-worker-pause").click()
        expect(page.locator("#flow-worker")).to_contain_text("填写已暂停")
        assert starts == ["spawn"]


def test_unknown_upload_preserves_old_action_and_requires_recorded_recheck(
    portal, tmp_path, browser_page, monkeypatch
):
    from playwright.sync_api import expect

    page = browser_page
    with flow_portal(portal, tmp_path, worker=True) as (instance, work):
        service, starts = prepare_browser_worker(page, instance, monkeypatch)
        state = service.store.load()
        intent = {
            "action": "upload",
            "attempt_id": "synthetic-upload",
            "sha256": state["jobs"][0]["file_sha256"],
        }
        state["jobs"][0].update(
            status="needs_recheck", reason="upload_result_unknown", intent=intent
        )
        service.store.save(state)
        page.locator("#flow-observe").click()
        expect(page.locator("#flow-worker")).to_contain_text("上传结果尚未核验")
        expect(page.locator("#flow-worker-recheck")).to_be_disabled()
        page.get_by_label("旧动作核验来源").fill("Synthetic authoritative attachment readback")
        page.get_by_label("旧动作处理结论").select_option("current_matches")
        page.locator("#flow-observe").click()
        expect(page.get_by_label("旧动作核验来源")).to_have_value(
            "Synthetic authoritative attachment readback"
        )
        page.get_by_role("button", name="保存旧动作核验结论").click()
        expect(page.locator("#flow-worker-recheck")).to_be_enabled()
        current = service.store.load()["jobs"][0]
        assert current["intent"] == intent
        assert current["action_resolutions"][-1]["conclusion"] == "current_matches"
        assert starts == [] and service.snapshot()["control"] == "paused"
        old_select = page.get_by_label("旧动作处理结论").element_handle()
        state = service.store.load()
        state["jobs"][0]["intent"] = intent | {"attempt_id": "synthetic-next-upload"}
        service.store.save(state)
        page.locator("#flow-observe").click()
        expect(page.locator("#flow-worker")).to_contain_text("synthetic-next-upload")
        expect(page.locator("#flow-worker-recheck")).to_be_disabled()
        expect(page.get_by_label("旧动作核验来源")).to_have_value("")
        assert old_select.evaluate("e => !e.isConnected")


def test_timestamp_only_worker_polls_preserve_manual_stop_controls(
    portal, tmp_path, browser_page, monkeypatch
):
    from playwright.sync_api import expect

    page = browser_page
    with flow_portal(portal, tmp_path, worker=True) as (instance, work):
        service, starts = prepare_browser_worker(page, instance, monkeypatch)
        state = service.store.load()
        intent = {"action": "fill", "attempt_id": "synthetic-unknown-fill"}
        state["jobs"][0].update(
            status="needs_recheck",
            reason="action_result_unknown",
            intent=intent,
            page_observation={
                "run_id": "synthetic-run",
                "page_id": "synthetic-page",
                "event": "observed",
                "at": 100,
            },
        )
        service.store.save(state)
        page.locator("#flow-observe").click()
        expect(page.locator("#flow-worker")).to_contain_text("旧动作结果尚未核验")
        expect(page.locator("#flow-observe")).to_be_enabled()
        conclusion = page.get_by_label("旧动作处理结论")
        original_select = conclusion.element_handle()
        details = page.get_by_text("查看旧动作观察记录", exact=True).locator("..")
        details.locator("summary").click()
        original_details = details.element_handle()
        page.get_by_label("旧动作核验来源").fill("Synthetic unknown result; keep stopped")
        conclusion.focus()
        for timestamp in (101, 102):
            with page.expect_response(
                lambda response: (
                    response.request.method == "GET"
                    and response.url.startswith(instance.origin + "/api/flow/")
                )
            ) as observed:
                state["jobs"][0]["page_observation"]["at"] = timestamp
                service.store.save(state)
            assert observed.value.json()["worker"]["jobs"][0]["page_observation"]["at"] == timestamp
            expect(page.locator("#flow-observe")).to_be_enabled()
            assert original_select.evaluate("e => e.isConnected && document.activeElement === e")
            assert original_details.evaluate("e => e.isConnected && e.open")
        conclusion.select_option("manual_stop")
        page.get_by_role("button", name="保存旧动作核验结论").click()
        expect(page.locator("#flow-worker")).to_contain_text("未知，人工处理并停止")
        expect(page.locator("#flow-worker-recheck")).to_be_disabled()
        current = service.store.load()["jobs"][0]
        assert current["intent"] == intent
        assert current["action_resolutions"][-1]["conclusion"] == "manual_stop"
        assert starts == [] and service.snapshot()["control"] == "paused"


def test_worker_question_keeps_draft_and_saves_only_current_job_without_resuming(
    portal, tmp_path, browser_page, monkeypatch
):
    from playwright.sync_api import expect

    page = browser_page
    with flow_portal(portal, tmp_path, worker=True) as (instance, work):
        service, starts = prepare_browser_worker(page, instance, monkeypatch)
        state = service.store.load()
        state["jobs"][0].update(
            status="needs_input",
            questions=[{"id": "start", "question": "Start date", "options": []}],
        )
        service.store.save(state)
        page.locator("#flow-observe").click()
        expect(page.get_by_label("Start date · 补充信息")).to_be_visible()
        answer = page.get_by_label("Start date · 补充信息")
        answer.fill("2026-11-01")
        page.locator("#flow-observe").click()
        expect(answer).to_have_value("2026-11-01")
        page.locator("#flow-title").click()
        expect(page.locator("#flow-notice")).to_contain_text("已自动保存到信息库")
        assert service.store.library()[0]["value"] == "2026-11-01"
        assert service.store.load()["commands"][-1]["action"] == "answers-changed"
        assert service.snapshot()["control"] == "paused" and starts == []


def test_missing_required_diploma_accepts_real_file_and_keeps_filling_paused(
    portal, tmp_path, browser_page, monkeypatch
):
    from pathlib import Path

    from playwright.sync_api import expect

    page = browser_page
    with flow_portal(portal, tmp_path, worker=True) as (instance, work):
        service, starts = prepare_browser_worker(page, instance, monkeypatch)
        state = service.store.load()
        state["jobs"][0].update(
            status="needs_input",
            materials=[
                {
                    "field_id": "diploma",
                    "draft_path": "documents.diploma",
                    "kind": "diploma",
                    "question": "Degree certificate",
                    "required": True,
                    "status": "needs_input",
                }
            ],
        )
        service.store.save(state)
        page.locator("#flow-observe").click()
        upload = page.get_by_label("Degree certificate · 提供真实附件", exact=True)
        expect(upload).to_be_visible()
        fixture = Path(__file__).parent / "fixtures/pdf-export/current-template.pdf"
        upload.set_input_files(fixture)
        page.get_by_role("button", name="保存真实附件", exact=True).click()
        expect(page.locator("#flow-notice")).to_contain_text("真实附件已保存")
        expect(page.locator("#flow-worker")).to_contain_text("current-template.pdf")
        material = service.store.load()["jobs"][0]["materials"][0]
        assert material["status"] == "ready" and material["actor"] == "user"
        assert Path(material["file_path"]).read_bytes() == fixture.read_bytes()
        assert service.store.load()["control"] == "paused" and starts == []


def test_changed_worker_poll_preserves_focused_manual_source_draft(
    portal, tmp_path, browser_page, monkeypatch
):
    from playwright.sync_api import expect

    page = browser_page
    with flow_portal(portal, tmp_path, worker=True) as (instance, work):
        service, _ = prepare_browser_worker(page, instance, monkeypatch)
        state = service.store.load()
        state["jobs"][0].update(
            status="needs_recheck",
            reason="action_result_unknown",
            intent={"action": "fill", "attempt_id": "synthetic-manual-draft"},
        )
        service.store.save(state)
        page.locator("#flow-observe").click()
        source = page.get_by_label("旧动作核验来源", exact=True)
        expect(source).to_be_visible()
        source.fill("A factual observation still being edited")
        source.evaluate("element => element.setSelectionRange(10, 16)")
        state["jobs"][0]["reason"] = "draft_result_unknown"
        service.store.save(state)
        expect(page.locator("#flow-worker")).to_contain_text("草稿保存结果尚未核验")
        expect(source).to_have_value("A factual observation still being edited")
        expect(source).to_be_focused()
        assert source.evaluate("element => [element.selectionStart, element.selectionEnd]") == [
            10,
            16,
        ]


def test_unknown_answer_for_viewed_task_does_not_lock_other_pipeline_job(
    portal, tmp_path, browser_page, monkeypatch
):
    from playwright.sync_api import expect

    page = browser_page
    pipeline = {
        "enabled": True,
        "id": "another-pipeline",
        "control": "paused",
        "status": "needs_input",
        "current_recommendation_id": "another-recommendation",
        "items": [{"recommendation_id": "another-recommendation", "application_id": "other-job"}],
    }
    with flow_portal(portal, tmp_path, worker=True) as (instance, work):
        service, _ = prepare_browser_worker(page, instance, monkeypatch)
        page.route("**/api/pipeline/state", lambda route: route.fulfill(json=pipeline))
        state = service.store.load()
        state["jobs"][0].update(
            status="needs_input",
            questions=[{"id": "start", "question": "Start date", "options": []}],
        )
        service.store.save(state)
        page.locator("#flow-observe").click()
        answer = page.get_by_label("Start date · 补充信息", exact=True)
        expect(answer).to_be_visible()
        page.route("**/api/flow/worker-action", lambda route: route.abort())
        answer.fill("2026-11-01")
        page.locator("#flow-title").click()
        expect(page.locator("#flow-notice")).to_contain_text("尚未核验")
        expect(page.locator("#flow-pipeline-start")).to_be_enabled()
        assert not service.store.library()


def test_ready_for_review_shows_verified_attachment_and_hands_off_without_submit(
    portal, tmp_path, browser_page, monkeypatch
):
    from playwright.sync_api import expect

    page = browser_page
    page.set_viewport_size({"width": 1440, "height": 1000})
    with flow_portal(portal, tmp_path, worker=True) as (instance, work):
        service, starts = prepare_browser_worker(page, instance, monkeypatch)
        state = service.store.load()
        job = state["jobs"][0]
        job.update(status="ready_for_review", page_open=True)
        job["observations"].append(
            {
                "action": "draft_transport_verified",
                "server_readback": True,
                "resume_sha256": job["file_sha256"],
                "required_field_count": 3,
            }
        )
        service.store.save(state)
        page.locator("#flow-observe").click()
        expect(page.locator("#flow-worker")).to_contain_text("3 个必填项已核验服务端保存")
        page.locator("#flow-worker-review").click()
        expect(page.locator("#flow-worker")).to_contain_text("人工交接尚未核验")
        saved = service.store.load()
        assert saved["commands"][-1]["action"] == "review"
        assert saved["jobs"][0]["manual_submission"] is None and starts == []
        captures = Path(mkdtemp(prefix="tomorrowstar-flow-ui-"))
        page.locator(".topbar").scroll_into_view_if_needed()
        page.locator("#flow-observe").focus()
        page.screenshot(path=str(captures / "flow-desktop.png"), full_page=True)
        page.set_viewport_size({"width": 390, "height": 844})
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
        page.locator(".topbar").scroll_into_view_if_needed()
        page.screenshot(path=str(captures / "flow-mobile.png"), full_page=True)
        print(f"Synthetic UI screenshots: {captures}")


def test_reopen_pauses_own_controller_and_never_resumes_from_observation(
    portal, tmp_path, browser_page, monkeypatch
):
    from playwright.sync_api import expect

    page = browser_page
    operations = []

    def remember(request):
        if request.method == "POST" and request.url.endswith("/api/flow/worker-action"):
            operations.append(request.post_data_json)

    page.on("request", remember)
    with flow_portal(portal, tmp_path, worker=True) as (instance, work):
        service, starts = prepare_browser_worker(page, instance, monkeypatch)
        page.locator("#flow-worker-resume").click()
        expect(page.locator("#flow-worker")).to_contain_text("填写运行中")
        controller = service.snapshot()["controller"]
        assert operations[0]["operation"] == "resume"
        operations.clear()
        page.reload()
        expect(page.locator("#flow-worker")).to_contain_text("填写已暂停")
        page.locator("#flow-observe").click()
        expect(page.locator("#flow-worker-resume")).to_be_enabled()
        # Chromium can deliver pagehide keepalive without a page request event.
        assert [item["operation"] for item in operations] in ([], ["pause"])
        assert all(item["payload"]["controller"] == controller for item in operations)
        assert service.store.load()["control"] == "paused"
        assert service.snapshot()["controller"] == controller
        assert starts == ["spawn"]
