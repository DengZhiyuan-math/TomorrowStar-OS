"""Owner health must remain proven until an original-page capture completes."""

from copy import deepcopy
from types import SimpleNamespace

import pytest
from test_worker_stability import retained_live_page as retained_live_page

from career_evidence_graph.application_worker_browser import ApplicationRunner
from career_evidence_graph.cua_driver import CuaDriver


@pytest.mark.worker_browser
@pytest.mark.parametrize("expires", [False, True])
def test_capture_checks_original_owner_after_screenshot(retained_live_page, monkeypatch, expires):
    from playwright.sync_api import sync_playwright

    server, identifier = retained_live_page
    owner_expired = False
    calls = []

    def call(name, arguments, **kwargs):
        calls.append((name, arguments))
        return (
            {"status": "expired"}
            if owner_expired
            else {
                "status": "ok",
                "binding_quality": "exact",
                "endpoint_access_class": "driver_owned",
                "target_id": "synthetic-original-owner",
            }
        )

    client = SimpleNamespace(failed=False, process=SimpleNamespace(poll=lambda: None), call=call)
    cua = CuaDriver(client, 42, window_id=7, driver_owned=True)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            context = browser.new_context()
            page = context.new_page()
            page.set_content('<title>Original</title><input value="unchanged">')
            runner = ApplicationRunner(server.store, context, cua=cua)
            runner.pages[identifier] = page
            runner.page_ids[page] = "synthetic-retained-page"
            screenshot = page._impl_obj.screenshot
            screenshot_calls = []

            async def captured(**kwargs):
                nonlocal owner_expired
                screenshot_calls.append(kwargs.copy())
                result = await screenshot(**kwargs)
                owner_expired = expires
                return result

            monkeypatch.setattr(page._impl_obj, "screenshot", captured)
            binding = server.snapshot()["jobs"][0]["page_inspection_target"]
            server.request("observe-page", {"application_id": identifier, "binding": binding})
            state = server.store.load()
            before = deepcopy(state["jobs"][0])

            runner.commands(state)

            assert screenshot_calls == [
                {
                    "type": "png",
                    "timeout": 2000,
                    "animations": "allow",
                    "caret": "initial",
                    "scale": "css",
                }
            ]
            current = state["jobs"][0]
            receipt = current.pop("owned_page_inspection")
            before.pop("owned_page_inspection")
            assert receipt["status"] == ("failed" if expires else "captured")
            if expires:
                assert "data" not in receipt and "screenshot" not in receipt
                assert receipt["reason"] == "cua_owner_unknown"
            assert current == before
            assert state["control"] == "paused"
            assert runner.cua is cua and cua.client is client
            assert runner.pages[identifier] is page
            assert page.locator("input").input_value() == "unchanged"
            assert calls == [("get_browser_state", {"pid": 42, "window_id": 7})] * 2
        finally:
            browser.close()
