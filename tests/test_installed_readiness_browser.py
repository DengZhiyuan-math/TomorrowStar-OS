"""Readiness evidence stays separate from application actions on loopback pages."""

import time
from copy import deepcopy

import pytest
from test_application_flow_browser import flow_portal, prepare_browser_worker
from test_career_portal_http import portal as portal
from test_portal_workflow_browser import browser_page as browser_page

pytestmark = pytest.mark.worker_browser


def readiness_receipt(task_revision):
    return {
        "schemaVersion": 1,
        "protocol": "installed-readiness/v1",
        "status": "unknown",
        "checked_at": time.time(),
        "controller": {"loaded_engine_revision": "python-loaded-code/v1:controller:synthetic"},
        "package": {"status": "unknown", "signature": "not_checked"},
        "worker": {
            "state": "exited",
            "loaded_engine_revision": None,
            "startup_source_revision": "synthetic-startup-source",
            "last_error": "PortalDataError",
        },
        "native_host": {"state": "unknown", "reason": "native_evidence_missing"},
        "page": {"state": "historical", "owner": {"status": "unknown"}},
        "inputs": {"state": "current", "task_revision": task_revision},
        "compatibility": {
            "state": "unknown",
            "commands": {"read_state": "supported", "observe_page": "unknown", "resume": "unknown"},
        },
        "user_stop": {"state": "paused", "requires_explicit_resume": True},
        "reasons": ["native_evidence_missing", "worker_exited"],
        "decision": {"can_fill": False, "can_observe_page": False, "user_control": "paused"},
    }


def test_explicit_readiness_get_shows_unknown_identity_without_resuming(
    portal, tmp_path, browser_page, monkeypatch
):
    from playwright.sync_api import expect

    page = browser_page
    with flow_portal(portal, tmp_path, worker=True) as (instance, _):
        service, starts = prepare_browser_worker(page, instance, monkeypatch)
        before = deepcopy(service.store.load())
        requests = []
        revision = instance.server.application_flow_service.snapshot()["tasks"][0]["revision"]
        receipt = readiness_receipt(revision)

        def answer(route):
            requests.append(route.request.method)
            route.fulfill(json=receipt)

        page.route("**/api/flow/readiness/*", answer)
        writes = []
        page.on(
            "request",
            lambda request: writes.append(request.url) if request.method == "POST" else None,
        )
        button = page.locator("#flow-check-runtime-readiness")
        expect(button).to_be_visible(timeout=2000)
        assert requests == []
        with page.expect_response("**/api/flow/readiness/*"):
            button.click()
        panel = page.locator("#flow-runtime-readiness")
        expect(panel).to_contain_text("尚未核验完整，保持暂停")
        expect(panel).to_contain_text("执行器已退出")
        expect(panel).to_contain_text("实际加载版本：未报告")
        expect(panel).to_contain_text("synthetic-startup-source")
        expect(panel).to_contain_text("native_evidence_missing")
        expect(panel).to_contain_text("兼容性未核验")
        expect(panel).to_contain_text("本次核验只读，不恢复填写或确认材料")
        assert requests == ["GET"] and writes == [] and starts == []
        assert service.store.load() == before
        page.set_viewport_size({"width": 390, "height": 844})
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")


@pytest.mark.parametrize("offset", [-30, 60])
def test_old_or_future_positive_readiness_is_never_current(
    portal, tmp_path, browser_page, monkeypatch, offset
):
    from playwright.sync_api import expect

    page = browser_page
    with flow_portal(portal, tmp_path, worker=True) as (instance, _):
        service, starts = prepare_browser_worker(page, instance, monkeypatch)
        before = deepcopy(service.store.load())
        revision = instance.server.application_flow_service.snapshot()["tasks"][0]["revision"]
        receipt = readiness_receipt(revision) | {
            "status": "verified_paused",
            "checked_at": time.time() + offset,
        }
        page.route("**/api/flow/readiness/*", lambda route: route.fulfill(json=receipt))
        page.locator("#flow-check-runtime-readiness").click()
        panel = page.locator("#flow-runtime-readiness")
        expect(panel).to_contain_text("历史核验；不能作为当前就绪依据")
        expect(panel).not_to_contain_text("技术核验通过，保持暂停")
        assert starts == [] and service.store.load() == before


def test_task_binding_change_invalidates_a_positive_readiness_receipt(
    portal, tmp_path, browser_page, monkeypatch
):
    from playwright.sync_api import expect

    page = browser_page
    with flow_portal(portal, tmp_path, worker=True) as (instance, _):
        service, starts = prepare_browser_worker(page, instance, monkeypatch)
        before = deepcopy(service.store.load())
        revision = instance.server.application_flow_service.snapshot()["tasks"][0]["revision"]
        receipt = readiness_receipt(revision) | {"status": "verified_paused"}
        page.route("**/api/flow/readiness/*", lambda route: route.fulfill(json=receipt))
        page.locator("#flow-check-runtime-readiness").click()
        panel = page.locator("#flow-runtime-readiness")
        expect(panel).to_contain_text("技术核验通过，保持暂停")
        changed = instance.server.application_flow_service.snapshot()
        task = changed["active_task"]
        task["revision"] = "synthetic-successor-task-revision"
        page.route("**/api/flow/" + task["id"], lambda route: route.fulfill(json=changed))
        page.locator("#flow-observe").click()
        expect(panel).to_contain_text("历史核验；不能作为当前就绪依据")
        expect(panel).not_to_contain_text("技术核验通过，保持暂停")
        assert starts == [] and service.store.load() == before


@pytest.mark.parametrize("changed", ["task", "run"])
def test_positive_server_receipt_for_another_binding_is_historical_without_refresh(
    portal, tmp_path, browser_page, monkeypatch, changed
):
    from playwright.sync_api import expect

    page = browser_page
    with flow_portal(portal, tmp_path, worker=True) as (instance, _):
        service, starts = prepare_browser_worker(page, instance, monkeypatch)
        before = deepcopy(service.store.load())
        revision = instance.server.application_flow_service.snapshot()["tasks"][0]["revision"]
        receipt = readiness_receipt(revision) | {"status": "verified_paused"}
        if changed == "task":
            receipt["inputs"]["task_revision"] = "another-task-revision"
        else:
            receipt["worker"]["run_id"] = "another-worker-run"
        page.route("**/api/flow/readiness/*", lambda route: route.fulfill(json=receipt))
        page.locator("#flow-check-runtime-readiness").click()
        panel = page.locator("#flow-runtime-readiness")
        expect(panel).to_contain_text("历史核验；不能作为当前就绪依据")
        expect(panel).not_to_contain_text("技术核验通过，保持暂停")
        assert starts == [] and service.store.load() == before
