"""Visible recovery states on synthetic local pages; no worker or external ATS starts."""

import time
from copy import deepcopy

import pytest
from test_application_flow_browser import flow_portal, prepare_browser_worker
from test_career_portal_http import portal as portal
from test_portal_workflow_browser import browser_page as browser_page

from career_evidence_graph.application_worker import digest, start_run

pytestmark = pytest.mark.worker_browser


def test_resolved_intent_waits_for_explicit_reclaim_without_unknown_result_copy(
    portal, tmp_path, browser_page, monkeypatch
):
    from playwright.sync_api import expect

    page = browser_page
    with flow_portal(portal, tmp_path, worker=True) as (instance, _):
        service, starts = prepare_browser_worker(page, instance, monkeypatch)
        state = service.store.load()
        intent = {"action": "fill", "attempt_id": "synthetic-resolved-fill"}
        state["jobs"][0].update(
            status="needs_recheck", reason="action_result_unknown", intent=intent
        )
        service.store.save(state)
        page.locator("#flow-observe").click()
        page.get_by_label("旧动作处理结论").select_option("current_matches")
        page.get_by_label("旧动作核验来源").fill("Synthetic manual original-page inspection")
        page.get_by_role("button", name="保存旧动作核验结论").click()
        panel = page.locator("#flow-worker")
        expect(panel).to_contain_text("旧结果已核验，待明确接管")
        expect(panel).not_to_contain_text("旧动作结果尚未核验")
        expect(panel).to_contain_text("人工核验")
        expect(page.locator("#flow-worker-recheck")).to_be_enabled()
        current = service.store.load()
        assert current["control"] == "paused" and current["commands"] == []
        assert current["jobs"][0]["intent"] == intent and starts == []


@pytest.mark.parametrize(
    ("conclusions", "expected", "blocked"),
    [
        ([], "旧动作结果尚未核验", True),
        (["current_matches"], "当前结果匹配", False),
        (["not_applied"], "已核验未应用", False),
        (["manual_stop"], "未知，人工处理并停止", True),
        (["current_matches", "manual_stop"], "未知，人工处理并停止", True),
        (["manual_stop", "not_applied"], "已核验未应用", False),
    ],
)
def test_latest_same_intent_conclusion_controls_visible_recovery(
    portal, tmp_path, browser_page, monkeypatch, conclusions, expected, blocked
):
    from playwright.sync_api import expect

    page = browser_page
    with flow_portal(portal, tmp_path, worker=True) as (instance, _):
        service, starts = prepare_browser_worker(page, instance, monkeypatch)
        state = service.store.load()
        intent = {"action": "upload", "attempt_id": "synthetic-current-upload"}
        job = state["jobs"][0]
        job.update(status="needs_recheck", reason="action_result_unknown", intent=intent)
        job["action_resolutions"] = [
            {
                "intent_ref": "synthetic-previous-upload",
                "conclusion": "current_matches",
                "source": "Previous intent must not resolve current action",
                "verified_by": "user",
            },
            *[
                {
                    "intent_ref": intent["attempt_id"],
                    "conclusion": conclusion,
                    "source": "Synthetic current action manual inspection",
                    "verified_by": "user",
                }
                for conclusion in conclusions
            ],
        ]
        service.store.save(state)
        before = deepcopy(service.store.load())
        page.locator("#flow-observe").click()
        panel = page.locator("#flow-worker")
        expect(panel).to_contain_text(expected)
        expect(panel).not_to_contain_text("Previous intent must not resolve current action")
        if blocked:
            expect(page.locator("#flow-worker-recheck")).to_be_disabled()
            expect(panel).not_to_contain_text("旧结果已核验，待明确接管")
        else:
            expect(page.locator("#flow-worker-recheck")).to_be_enabled()
            expect(panel).not_to_contain_text("旧动作结果尚未核验")
        assert service.store.load() == before
        assert before["control"] == "paused" and before["commands"] == [] and starts == []


@pytest.mark.parametrize("mismatch", [None, "answer", "field", "page", "run", "queue"])
def test_queued_correction_program_readback_and_review_have_separate_evidence(
    portal, tmp_path, browser_page, monkeypatch, mismatch
):
    from playwright.sync_api import expect

    page = browser_page
    with flow_portal(portal, tmp_path, worker=True) as (instance, _):
        service, starts = prepare_browser_worker(page, instance, monkeypatch)
        run_id = start_run(service.store)
        state = service.store.load()
        job = state["jobs"][0]
        now = time.time()
        binding = {
            "application_id": job["application_id"],
            "run_id": run_id,
            "page_id": "synthetic-readback-page",
            "field_id": "synthetic-email",
        }
        correction = {
            "id": "synthetic-readback-correction",
            "value": "new@example.invalid",
            "binding": binding,
        }
        answer = {
            "key": "one-use",
            "question": "email",
            "value": correction["value"],
            "scope": {"application_id": job["application_id"]},
            "state": "confirmed",
        }
        reference = {"key": "one-use", "revision": digest(answer), "fact": "email"}
        job["email_corrections"] = [correction]
        job["page_observation"] = {
            "run_id": run_id,
            "page_id": binding["page_id"],
            "event": "observed",
            "at": now,
        }
        job["page_open"] = True
        queued = {
            "action": "email_correction_queued",
            "correction_id": correction["id"],
            "binding": deepcopy(binding),
            "at": now,
        }
        fill = {
            "action": "fill",
            "verified": True,
            "field_id": binding["field_id"],
            "run_id": run_id,
            "at": now + 0.01,
            "intent": {
                "action": "fill",
                "field_id": binding["field_id"],
                "fact": "email",
                "run_id": run_id,
                "page_id": binding["page_id"],
                "answer_ref": reference,
            },
        }
        if mismatch == "answer":
            fill["intent"]["answer_ref"] = reference | {"revision": "0" * 64}
        if mismatch == "field":
            fill["field_id"] = "other-field"
        if mismatch == "page":
            fill["intent"]["page_id"] = "other-page"
        if mismatch == "run":
            fill["run_id"] = "other-run"
        job["answer_refs"] = [reference | {"field_id": binding["field_id"]}]
        job["observations"].extend([fill] if mismatch == "queue" else [queued, fill])
        service.store.save(state)
        before = deepcopy(service.store.load())
        writes = []
        page.on(
            "request",
            lambda request: writes.append(request.url) if request.method == "POST" else None,
        )
        page.locator("#flow-observe").click()
        panel = page.locator("#flow-worker")
        email = page.locator("#flow-email-correction")
        if mismatch is None:
            expect(email).to_contain_text("程序字段回读记录：此邮箱更正曾核验匹配")
            expect(email).to_contain_text("曾排入本岗位一次性答案队列")
        else:
            expect(email).not_to_contain_text("此邮箱更正曾核验匹配")
        expect(panel).not_to_contain_text("个必填项已核验服务端保存")
        assert writes == [] and starts == [] and service.store.load() == before
        job.update(status="ready_for_review", intent=None, reason="")
        service.store.save(state)
        page.locator("#flow-observe").click()
        expect(panel).to_contain_text("尚未取得与当前批准 PDF 一致的完整保存证据")
        job["observations"].append(
            {
                "action": "draft_transport_verified",
                "server_readback": True,
                "resume_sha256": job["file_sha256"],
                "required_field_count": 3,
            }
        )
        service.store.save(state)
        complete = deepcopy(service.store.load())
        page.locator("#flow-observe").click()
        expect(panel).to_contain_text("3 个必填项已核验服务端保存，批准的 PDF 已挂接")
        if mismatch is None:
            expect(email).to_contain_text("此邮箱更正曾核验匹配")
        expect(email).not_to_contain_text("尚未回读")
        expect(email).not_to_contain_text("从未应用")
        assert writes == [] and starts == [] and service.store.load() == complete


def test_email_local_save_and_historical_queue_are_not_field_or_attachment_success(
    portal, tmp_path, browser_page, monkeypatch
):
    from playwright.sync_api import expect

    page = browser_page
    with flow_portal(portal, tmp_path, worker=True) as (instance, _):
        service, starts = prepare_browser_worker(page, instance, monkeypatch)
        state = service.store.load()
        job = state["jobs"][0]
        binding = {
            "application_id": job["application_id"],
            "run_id": "synthetic-run",
            "page_id": "synthetic-page",
            "field_id": "synthetic-email",
        }
        job["email_corrections"] = [
            {"id": "synthetic-correction", "value": "new@example.invalid", "binding": binding}
        ]
        service.store.save(state)
        page.locator("#flow-observe").click()
        section = page.locator("#flow-email-correction")
        expect(section).to_contain_text("仅保存在本地，尚未排入填写器")
        job["observations"].append(
            {"action": "email_correction_queued", "correction_id": "synthetic-correction"}
        )
        service.store.save(state)
        before = deepcopy(service.store.load())
        page.locator("#flow-observe").click()
        expect(section).to_contain_text("曾排入本岗位一次性答案队列")
        expect(section).to_contain_text("排队记录不证明字段已回读、附件已核验或已进入原页复核阶段")
        expect(section).not_to_contain_text("尚未排入填写器")
        assert service.store.load() == before
        assert before["control"] == "paused" and before["commands"] == [] and starts == []
