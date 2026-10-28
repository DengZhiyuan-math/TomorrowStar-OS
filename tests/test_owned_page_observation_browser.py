"""App observation controls against an isolated original Page; no external site."""

import time
from copy import deepcopy

import pytest
from test_application_flow_browser import flow_portal, prepare_browser_worker
from test_career_portal_http import portal as portal
from test_portal_workflow_browser import browser_page as browser_page

from career_evidence_graph.application_worker import start_run
from career_evidence_graph.application_worker_browser import ApplicationRunner

pytestmark = pytest.mark.worker_browser


def test_app_requests_original_page_readback_while_unknown_action_stays_paused(
    portal, tmp_path, browser_page, monkeypatch
):
    from playwright.sync_api import expect

    page = browser_page
    with flow_portal(portal, tmp_path, worker=True) as (instance, _):
        service, starts = prepare_browser_worker(page, instance, monkeypatch)
        run_id = start_run(service.store)
        state = service.store.load()
        job = state["jobs"][0]
        job.update(
            status="needs_recheck",
            reason="action_result_unknown",
            intent={"action": "fill", "attempt_id": "synthetic-unresolved-fill"},
            page_observation={
                "run_id": run_id,
                "page_id": "owned-page",
                "event": "observed",
                "at": time.time(),
            },
        )
        service.store.save(state)
        owned = page.context.new_page()
        owned.set_content(
            "<title>Exact original page</title><label>Email "
            '<input id="email" type="email" value="saved@example.invalid"></label>'
        )
        runner = ApplicationRunner(service.store, page.context)
        runner.pages[job["application_id"]] = owned
        runner.page_ids[owned] = "owned-page"
        page.locator("#flow-observe").click()
        before = deepcopy(service.store.load())
        assert page.locator("#flow-worker-observe-page").count() == 1

        page.locator("#flow-worker-observe-page").click()

        expect(page.locator("#flow-page-inspection")).to_contain_text("等候所属执行器只读回读")
        state = service.store.load()
        runner.commands(state)
        service.store.save(state)
        page.locator("#flow-observe").click()
        section = page.locator("#flow-page-inspection")
        expect(section).to_contain_text("Exact original page")
        expect(section).to_contain_text("saved@example.invalid")
        expect(section).to_contain_text("不能证明远端草稿已保存")
        expect(section.locator("img")).to_be_visible()
        current = service.store.load()
        current["jobs"][0].pop("owned_page_inspection")
        assert current == before
        assert starts == []
