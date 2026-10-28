"""Native capabilities must attest the exact retained CDP Page, never a URL guess."""

from copy import deepcopy
from types import SimpleNamespace

import pytest
from owned_cdp_fake import OwnedCDPFake

from career_evidence_graph.career_portal_data import PortalDataError
from career_evidence_graph.cua_driver import CuaDriver


@pytest.fixture
def native_page(monkeypatch, request):
    import career_evidence_graph.cua_driver as module

    identity = {
        "pid": 42,
        "uid": 501,
        "started_seconds": 1_700_000_000,
        "started_microseconds": 20,
        "executable": "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    }
    state = {
        "status": "ok",
        "binding_quality": "exact",
        "endpoint_access_class": "driver_owned",
        "target_id": "native-target",
        "binding_generation": 3,
        "process_fingerprint": {"pid": 42, "start_time": 777, "executable": identity["executable"]},
        "tabs": [
            {
                "tab_id": "native-tab",
                "cdp_target_id": "owned-cdp",
                "tab_generation": 8,
                "url": "https://same.invalid",
            }
        ],
    }
    calls = []

    def call(name, arguments, **kwargs):
        calls.append((name, arguments))
        return deepcopy(state)

    client = SimpleNamespace(failed=False, process=SimpleNamespace(poll=lambda: None), call=call)
    driver = CuaDriver(client, 42, window_id=7, driver_owned=True)

    class Session:
        def send(self, method):
            calls.append((method, None))
            assert method == "Target.getTargetInfo"
            return {"targetInfo": {"targetId": "owned-cdp"}}

        def detach(self):
            calls.append(("detach", None))

    page = SimpleNamespace(
        context=SimpleNamespace(new_cdp_session=lambda _: Session()), is_closed=lambda: False
    )
    request.addfinalizer(OwnedCDPFake(page).close)
    monkeypatch.setattr(module, "process_identity", lambda pid: deepcopy(identity))
    return driver, page, state, calls, identity


def test_native_scope_matches_cdp_target_and_native_generation(native_page):
    driver, page, state, calls, identity = native_page
    result = driver.native_page_scope(page, pump=lambda: None)
    assert result == {
        "target_id": "native-target",
        "tab_id": "native-tab",
        "cdp_target_id": "owned-cdp",
        "binding_generation": 3,
        "tab_generation": 8,
        "process_fingerprint": state["process_fingerprint"],
        "process_identity": identity,
    }
    assert [name for name, _ in calls].count("Target.getTargetInfo") == 2
    assert [name for name, _ in calls].count("get_browser_state") == 1
    assert not {"screenshot", "Runtime.evaluate", "browser_prepare"} & {name for name, _ in calls}


@pytest.mark.parametrize(
    "change",
    [
        "same_url_other_page",
        "duplicate",
        "missing_target",
        "missing_tab_generation",
        "missing_binding_generation",
        "wrong_pid",
        "missing_start",
        "missing_exe",
    ],
)
def test_native_scope_refuses_ambiguous_or_unattested_original_page(native_page, change):
    driver, page, state, calls, _ = native_page
    if change == "same_url_other_page":
        state["tabs"][0]["cdp_target_id"] = "other-cdp"
    elif change == "duplicate":
        state["tabs"].append(deepcopy(state["tabs"][0]))
    elif change == "missing_target":
        state["target_id"] = ""
    elif change == "missing_tab_generation":
        state["tabs"][0].pop("tab_generation")
    elif change == "missing_binding_generation":
        state.pop("binding_generation")
    elif change == "wrong_pid":
        state["process_fingerprint"]["pid"] = 43
    elif change == "missing_start":
        state["process_fingerprint"]["start_time"] = None
    elif change == "missing_exe":
        state["process_fingerprint"]["executable"] = None
    with pytest.raises(PortalDataError) as error:
        driver.native_page_scope(page, pump=lambda: None)
    assert error.value.code == "cua_page_unverified"
