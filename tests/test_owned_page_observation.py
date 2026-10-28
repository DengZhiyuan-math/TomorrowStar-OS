"""Read-only observations of the retained worker Page, using synthetic records."""

import base64
from copy import deepcopy
from types import SimpleNamespace

import pytest
from test_worker_stability import retained_live_page as _retained_live_page

from career_evidence_graph.career_portal_data import PortalDataError

retained_live_page = _retained_live_page


def test_paused_unknown_action_can_request_original_page_observation(retained_live_page):
    server, identifier = retained_live_page
    before = deepcopy(server.store.load())
    page = before["jobs"][0]["page_observation"]
    binding = {
        "batch_id": before["batch_id"],
        "run_id": page["run_id"],
        "page_id": page["page_id"],
    }

    result = server.request("observe-page", {"application_id": identifier, "binding": binding})

    persisted = server.store.load()
    current = persisted["jobs"][0]
    receipt = result["jobs"][0]["owned_page_inspection"]
    assert receipt["status"] == "pending"
    assert receipt["binding"] == binding
    assert persisted["commands"] == [
        {
            "action": "observe-page",
            "id": identifier,
            "binding": binding,
            "request_id": receipt["request_id"],
        }
    ]
    current.pop("owned_page_inspection")
    assert current == before["jobs"][0]
    assert persisted["control"] == "paused"
    assert persisted["runtime"] == before["runtime"]


def test_lost_ui_lease_does_not_block_readonly_request_to_retained_worker(retained_live_page):
    server, identifier = retained_live_page
    state = server.store.load()
    state["worker_error"] = "control_connection_lost"
    server.store.save(state)
    target = {
        "batch_id": state["batch_id"],
        "run_id": state["runtime"]["id"],
        "page_id": state["jobs"][0]["page_observation"]["page_id"],
    }

    result = server.request("observe-page", {"application_id": identifier, "binding": target})

    assert result["jobs"][0]["owned_page_inspection"]["status"] == "pending"
    assert result["worker_error"] == "control_connection_lost"
    assert result["control"] == "paused"


@pytest.mark.parametrize(
    "change",
    [
        "legacy",
        "running",
        "cancelled",
        "wrong_run",
        "wrong_page",
        "stale",
        "stale_page",
        "future_page",
        "stop_marker",
        "terminal_error",
    ],
)
def test_observation_rejects_incompatible_or_changed_owner_without_side_effects(
    retained_live_page, change
):
    server, identifier = retained_live_page
    state = server.store.load()
    page = state["jobs"][0]["page_observation"]
    binding = {"batch_id": state["batch_id"], "run_id": page["run_id"], "page_id": page["page_id"]}
    if change == "legacy":
        state["runtime"].pop("capabilities", None)
    elif change in {"running", "cancelled"}:
        state["control"] = change
    elif change == "stale":
        state["runtime"]["observed_at"] -= 6
    elif change in {"stale_page", "future_page"}:
        page["at"] += -6 if change == "stale_page" else 1
    elif change == "stop_marker":
        server.store.block_storage()
    elif change == "terminal_error":
        state["worker_error"] = "worker_stopped"
    else:
        binding["run_id" if change == "wrong_run" else "page_id"] = "another-owner"
    server.store.save(state)
    before = server.store.path.read_bytes()
    with pytest.raises(PortalDataError, match="原执行器"):
        server.request("observe-page", {"application_id": identifier, "binding": binding})
    assert server.store.path.read_bytes() == before


@pytest.mark.parametrize("change", [None, "expired", "different_run", "different_page", "running"])
def test_cached_screenshot_never_inherits_freshness_from_new_runtime(retained_live_page, change):
    server, _ = retained_live_page
    state = server.store.load()
    target = server.snapshot()["jobs"][0]["page_inspection_target"]
    receipt = {
        "status": "captured",
        "request_id": "synthetic-capture",
        "binding": target,
        "at": state["runtime"]["observed_at"],
        "worker_source": state["runtime"]["source"]["sha256"],
    }
    state["jobs"][0]["owned_page_inspection"] = receipt
    if change == "expired":
        receipt["at"] -= 10
    elif change in {"different_run", "different_page"}:
        receipt["binding"]["run_id" if change == "different_run" else "page_id"] = "old-owner"
    elif change == "running":
        state["control"] = "running"
    server.store.save(state)
    before = server.store.path.read_bytes()

    current = server.snapshot()["jobs"][0]

    assert current["owned_page_inspection_state"] == ("current" if change is None else "historical")
    assert server.store.path.read_bytes() == before


def test_expired_original_cua_owner_stops_before_reading_or_replacing_page(retained_live_page):
    from career_evidence_graph.application_worker_browser import ApplicationRunner
    from career_evidence_graph.cua_driver import CuaDriver

    server, identifier = retained_live_page
    calls = []
    client = SimpleNamespace(failed=False, process=SimpleNamespace(poll=lambda: None))

    def call(name, arguments, **kwargs):
        calls.append((name, arguments))
        return {"status": "expired"}

    client.call = call
    cua = CuaDriver(client, 42, window_id=7, driver_owned=True)
    context = SimpleNamespace(browser=SimpleNamespace(is_connected=lambda: True))

    class Page:
        url = "https://synthetic.invalid/original"

        def is_closed(self):
            return False

        def evaluate_handle(self, *_):
            pytest.fail("An expired owner must stop before any Page reads")

    page = Page()
    page.context = context
    runner = ApplicationRunner(server.store, None, cua=cua)
    runner.context = context
    runner.pages[identifier] = page
    runner.page_ids[page] = "synthetic-retained-page"
    target = server.snapshot()["jobs"][0]["page_inspection_target"]
    server.request("observe-page", {"application_id": identifier, "binding": target})
    state = server.store.load()
    before = deepcopy(state["jobs"][0])

    runner.commands(state)

    current = state["jobs"][0]
    receipt = current.pop("owned_page_inspection")
    before.pop("owned_page_inspection")
    assert receipt["status"] == "failed"
    assert current == before and state["control"] == "paused"
    assert calls == [("get_browser_state", {"pid": 42, "window_id": 7})]
    assert runner.cua is cua and runner.pages[identifier] is page


@pytest.mark.worker_browser
def test_original_owner_observes_exact_page_without_mutations_or_events(retained_live_page):
    from playwright.sync_api import sync_playwright

    from career_evidence_graph.application_worker_browser import ApplicationRunner

    server, identifier = retained_live_page
    with sync_playwright() as playwright:
        first = playwright.chromium.launch(headless=True)
        second = playwright.chromium.launch(headless=True)
        try:
            context = first.new_context()
            owned = context.new_page()
            owned.set_content("""<title>Owned original</title><form>
                <label>Email <input id="email" type="email" value="wrong" required></label>
                <label>CV <input id="resume" type="file"></label>
                <input type="password" value="never expose">
                <button>Submit</button></form>""")
            owned.locator("#resume").set_input_files(
                {"name": "synthetic-cv.pdf", "mimeType": "application/pdf", "buffer": b"synthetic"}
            )
            owned.evaluate("""() => {
                window.events=[]; window.mutations=[];
                for(const e of ['input','change','invalid','focus','submit'])
                    document.addEventListener(e,()=>window.events.push(e),true);
                new MutationObserver(rows=>window.mutations.push(...rows.map(x=>x.type)))
                    .observe(document,{subtree:true,childList:true,attributes:true,characterData:true});
                const native=Object.getOwnPropertyDescriptor(
                    HTMLInputElement.prototype,'value').get;
                Object.defineProperty(document.querySelector('#email'),'value',{get(){
                    window.events.push('page_value_getter');
                    document.querySelector('form').setAttribute('data-getter-side-effect','yes');
                    fetch('https://synthetic.invalid/forbidden',{method:'POST',body:'synthetic'});
                    return native.call(this);
                }});
            }""")
            decoy = context.new_page()
            decoy.set_content('<title>Decoy tab</title><input value="wrong tab">')
            other = second.new_page()
            other.set_content('<title>Other browser</title><input value="wrong browser">')
            runner = ApplicationRunner(server.store, context)
            runner.pages[identifier] = owned
            runner.page_ids[owned] = "synthetic-retained-page"
            before = deepcopy(server.store.load())
            binding = server.snapshot()["jobs"][0]["page_inspection_target"]
            server.request("observe-page", {"application_id": identifier, "binding": binding})
            state = server.store.load()

            runner.commands(state)

            current = state["jobs"][0]
            receipt = current.pop("owned_page_inspection")
            assert receipt["status"] == "captured"
            assert receipt["binding"] == binding
            assert receipt["data"]["title"] == "Owned original"
            fields = {f["id"]: f for f in receipt["data"]["fields"] if f["id"]}
            assert fields["email"]["value"] == "wrong"
            assert fields["email"]["valid"] is False
            assert fields["resume"]["files"] == [
                {"name": "synthetic-cv.pdf", "size": 9, "type": "application/pdf"}
            ]
            assert "never expose" not in str(receipt)
            assert base64.b64decode(receipt["screenshot"]["base64"]).startswith(
                b"\x89PNG\r\n\x1a\n"
            )
            assert owned.evaluate("() => [window.events,window.mutations]") == [[], []]
            assert current == before["jobs"][0]
            assert state["control"] == "paused"
            assert runner.pages[identifier] is owned
            assert context.pages == [owned, decoy]
        finally:
            first.close()
            second.close()


@pytest.mark.worker_browser
@pytest.mark.parametrize("change", ["document", "field", "connection"])
def test_mid_capture_changes_discard_observation_without_resolving_intent(
    retained_live_page, monkeypatch, change
):
    from playwright.sync_api import sync_playwright

    from career_evidence_graph.application_worker_browser import ApplicationRunner

    server, identifier = retained_live_page
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            context = browser.new_context()
            page = context.new_page()
            page.set_content('<input value="before">')
            runner = ApplicationRunner(server.store, context)
            runner.pages[identifier] = page
            runner.page_ids[page] = "synthetic-retained-page"
            screenshot = page._impl_obj.screenshot
            screenshot_calls = []

            async def interrupted(**kwargs):
                screenshot_calls.append(kwargs.copy())
                if change == "document":
                    await page._impl_obj.goto("about:blank")
                    await page._impl_obj.set_content('<input value="before">')
                elif change == "field":
                    await page._impl_obj.locator("input").fill("changed during capture")
                else:
                    runner.event("browser_disconnected")
                return await screenshot(**kwargs)

            monkeypatch.setattr(page._impl_obj, "screenshot", interrupted)
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
            assert receipt["status"] == "failed"
            assert "data" not in receipt and "screenshot" not in receipt
            assert current == before
            assert state["control"] == "paused"
        finally:
            browser.close()
