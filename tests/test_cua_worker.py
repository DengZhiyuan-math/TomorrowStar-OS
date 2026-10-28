"""Cua execution reuses the worker's public state and request constraints."""

import base64
import json
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from test_generic_worker import FIELDS, native_form
from worker_preview_support import advance_until

COMBOBOX = """<label>Application country *
<input role='combobox' aria-expanded='false' readonly required>
</label><div role='listbox' hidden><div role='option'>Switzerland</div></div>
<script>
const combo=document.querySelector('[role=combobox]');
const list=document.querySelector('[role=listbox]');
combo.onclick=()=>{combo.ariaExpanded='true';list.hidden=false};
document.querySelector('[role=option]').onclick=()=>{
  combo.value='Switzerland';combo.ariaExpanded='false';list.hidden=true;
};
</script>"""


def report_native(name, **facts):
    destination = os.environ.get("TS_CUA_REPORT_DIR")
    if destination:
        root = Path(destination)
        root.mkdir(parents=True, exist_ok=True)
        (root / (name + ".json")).write_text(json.dumps(facts, indent=2) + "\n")


def browser_app_state(pid):
    script = """ObjC.import('AppKit');
function run(args) {
  const app=$.NSRunningApplication.runningApplicationWithProcessIdentifier(Number(args[0]));
  return JSON.stringify({pid:Number(app.processIdentifier),active:Boolean(app.active),
    hidden:Boolean(app.hidden),
    frontmost_pid:Number($.NSWorkspace.sharedWorkspace.frontmostApplication.processIdentifier)});
} """
    return json.loads(
        subprocess.check_output(
            ["/usr/bin/osascript", "-l", "JavaScript", "-e", script, str(pid)], text=True, timeout=3
        )
    )


def page_target_id(page):
    session = page.context.new_cdp_session(page)
    try:
        return session.send("Target.getTargetInfo")["targetInfo"]["targetId"]
    finally:
        session.detach()


class SyntheticControls:
    """Boundary double: the actual native MCP path has separate opt-in coverage."""

    def __init__(self):
        self.actions = []
        self.click_route = "dom_event"
        self.reviewed = []
        self.opened = []

    def review(self, page, *, pump):
        self.reviewed.append(page)

    def new_page(self, context, *, keep_visible=False):
        self.opened.append(keep_visible)
        return context.new_page()

    def fill(self, page, question, value, *, check, pump):
        check()
        self.actions.append((question["question"], value))
        page.get_by_role("combobox").click()
        check()
        page.get_by_role("option", name=value, exact=True).click()
        return {"executor": "cua_driver", "input_route": "dom_event"}


@pytest.mark.parametrize("owned", [False, True])
def test_first_hidden_page_avoids_native_creation_animation(monkeypatch, owned):
    from contextlib import contextmanager

    from playwright.sync_api import Error

    from career_evidence_graph import cua_driver as module

    hidden = owned
    state = "normal"

    def hide(pid, **kwargs):
        nonlocal hidden
        assert pid == 42 and kwargs["launch_date"] == 1
        action = kwargs.get("action", "read")
        if action != "read":
            assert not owned, "Owned startup must not hide after creating a window"
            hidden = action == "hide"
        return {"pid": pid, "hidden": hidden, "active": False, "windows": []}

    class Session:
        def send(self, method, params=None):
            nonlocal state
            if method == "Target.getBrowserContexts":
                return {"browserContextIds": ["owned-context"]}
            if method == "Target.createTarget":
                assert hidden and params["background"] and not params["focus"]
                if owned and state == "minimized":
                    raise Error("new background tab restored a minimized native window")
                if params.get("windowState") == "minimized":
                    # Native boundary fault observed on macOS under load: a
                    # creation-time minimized window animates despite app.hidden.
                    raise Error("creation-time minimization exposed a native window")
                return {"targetId": "owned-target"}
            if method == "Browser.getWindowForTarget":
                return {"windowId": 7}
            if method == "Browser.setWindowBounds":
                assert hidden
                state = params["bounds"]["windowState"]
                return {}
            assert method == "Browser.getWindowBounds"
            return {"bounds": {"windowState": state}}

        def detach(self):
            pass

    browser = SimpleNamespace(new_browser_cdp_session=Session)
    context = SimpleNamespace(browser=browser, pages=[], new_cdp_session=lambda page: Session())
    page = SimpleNamespace(context=context, wait_for_timeout=lambda timeout: None)

    @contextmanager
    def expect_page(**kwargs):
        yield SimpleNamespace(value=page)

    context.expect_page = expect_page
    monkeypatch.setattr(module, "mac_chrome_state", hide)
    driver = module.CuaDriver(None, 42, launch_date=1, driver_owned=owned)
    assert driver.new_page(context) is page
    assert hidden and state == ("normal" if owned else "minimized")
    if owned:
        context.pages.append(page)
        assert driver.new_page(context) is page
        assert state == "normal"


@pytest.mark.parametrize("snapshot_unavailable", [False, True])
@pytest.mark.parametrize("port_during_hide", [False, True])
def test_prewindow_rejection_keeps_failure_details_before_cleanup(
    tmp_path, monkeypatch, snapshot_unavailable, port_during_hide
):
    from contextlib import contextmanager
    from io import StringIO

    from career_evidence_graph import cua_driver as module

    log = StringIO()
    owned = {"pid": 42, "launch_date": 1, "hidden": True, "active": False}
    window = {
        "pid": 42,
        "window_id": 7,
        "title": "Synthetic startup dialog",
        "is_on_screen": True,
        "bounds": {"x": 11, "y": 12, "width": 100, "height": 80},
        "layer": 0,
        "alpha": 1,
    }
    hide_attempts, window_reads, stopped = 0, 0, False
    order = []

    def launch(command, **kwargs):
        assert command[:4] == ["open", "-n", "-g", "-j"]
        profile = tmp_path / "chrome-profile"
        profile.mkdir()
        (profile / "SingletonLock").symlink_to("synthetic-42")
        if not port_during_hide:
            (profile / "DevToolsActivePort").write_text("12345\n/synthetic\n")

    def state(pid, *, launch_date=None, action="read"):
        nonlocal hide_attempts
        assert pid == 42 and launch_date in (None, 1)
        if action == "hide":
            hide_attempts += 1
            if hide_attempts == 1:
                raise module.PortalDataError("cua_visibility_unknown", "not registered", 409)
            if port_during_hide:
                (tmp_path / "chrome-profile/DevToolsActivePort").write_text("12345\n/synthetic\n")
            return dict(owned)
        if launch_date == 1 and not stopped:
            order.append("failure_appkit_read")
            last = json.loads(log.getvalue().splitlines()[-1])
            if snapshot_unavailable and last.get("stage") == "failure_appkit_requested":
                raise module.PortalDataError("cua_visibility_unknown", "read unavailable", 409)
        return {**owned, "hidden": False}

    class Client:
        def call(self, name, args):
            nonlocal window_reads
            assert name == "list_windows" and args == {"pid": 42}
            window_reads += 1
            if window_reads == 1:
                return {"windows": [window]}
            order.append("failure_windows_read")
            if snapshot_unavailable:
                raise module.PortalDataError("cua_result_unknown", "read unavailable", 409)
            return {"windows": [{**window, "is_on_screen": False}]}

    @contextmanager
    def client(*args):
        try:
            yield Client(), {"source": {"pid": 43}}
        finally:
            order.append("client_closed")

    def kill(pid, signal):
        nonlocal stopped
        assert pid == 42
        if signal == 15:
            order.append("chrome_cleanup")
            stopped = True
        elif stopped:
            raise ProcessLookupError()

    def connect(*args, **kwargs):
        pytest.fail("A rejected startup must not connect CDP or create a page")

    monkeypatch.setattr(module.subprocess, "run", launch)
    monkeypatch.setattr(module.subprocess, "check_output", lambda *a, **kw: "n127.0.0.1:12345\n")
    monkeypatch.setattr(module, "mac_chrome_state", state)
    monkeypatch.setattr(module, "managed_cua_client", client)
    monkeypatch.setattr(module.os, "kill", kill)
    with (
        pytest.raises(module.PortalDataError, match="无窗口启动出现了意外窗口") as error,
        module.managed_hidden_chrome(
            SimpleNamespace(chromium=SimpleNamespace(connect_over_cdp=connect)),
            str(tmp_path),
            Path("synthetic-driver"),
            log,
            {},
        ),
    ):
        pytest.fail("A rejected startup must not yield")
    assert error.value.code == "cua_visibility_unknown"
    records = [json.loads(line) for line in log.getvalue().splitlines()]
    events = {row["stage"]: row for row in records if row.get("event") == "cua_startup"}
    assert events["windowless_read_complete"]["windowless_before"] == [window]
    assert events["hide_unconfirmed"]["code"] == "cua_visibility_unknown"
    assert events["hide_confirmed"]["application"] == owned
    assert events["devtools_port_ready"]["pid"] == 42
    if port_during_hide:
        assert (
            events["devtools_port_ready"]["monotonic_ns"]
            >= events["hide_confirmed"]["monotonic_ns"]
        )
    assert events["windowless_rejected"]["discovery_daemon_pid"] == 43
    if snapshot_unavailable:
        assert events["failure_appkit_failed"]["code"] == "cua_visibility_unknown"
        assert events["failure_windows_failed"]["code"] == "cua_result_unknown"
    else:
        assert events["failure_appkit_complete"]["application"]["hidden"] is False
        assert events["failure_windows_complete"]["windows"][0]["is_on_screen"] is False
    assert window_reads == 2 and hide_attempts == 2 and stopped
    assert order.index("failure_windows_read") < order.index("chrome_cleanup")
    assert events["cleanup_complete"]["pid"] == 42
    assert all(row["utc_ns"] > 0 and row["elapsed_ns"] >= 0 for row in events.values())
    assert [row["monotonic_ns"] for row in records] == sorted(
        row["monotonic_ns"] for row in records
    )
    report_native(
        f"injected-prewindow-rejection-{port_during_hide}-{snapshot_unavailable}",
        evidence_kind="synthetic_native_boundary_double",
        primary_error=error.value.code,
        events=records,
        no_cdp_connection=True,
        real_ats_calls=0,
        real_model_calls=0,
    )


@pytest.mark.parametrize("version", ["0.35.2", "0.35.4"])
def test_incompatible_background_attach_stops_before_launch(tmp_path, monkeypatch, version):
    from career_evidence_graph import cua_driver as module

    # This contract covers the external-driver checkout path, including package replays.
    monkeypatch.setattr(module, "__file__", __file__)
    driver = tmp_path / "synthetic-cua-driver"
    driver.write_bytes(b"Synthetic driver; never executed")
    original_path = module.Path
    monkeypatch.setattr(module.sys, "platform", "darwin")
    monkeypatch.setattr(
        module,
        "Path",
        lambda *parts: (
            driver
            if str(original_path(*parts)) == "/Applications/CuaDriver.app/Contents/MacOS/cua-driver"
            else original_path(*parts)
        ),
    )
    monkeypatch.setattr(
        module.subprocess,
        "check_output",
        lambda *a, **k: json.dumps({"binary_version": version}).encode(),
    )

    def unexpected_launch(*args, **kwargs):
        pytest.fail("Known incompatible background attachment launched a browser")

    monkeypatch.setattr(module, "managed_hidden_chrome", unexpected_launch)
    monkeypatch.setattr(module, "managed_cua_client", unexpected_launch)
    with (
        pytest.raises(module.PortalDataError) as error,
        module.managed_cua_browser(None, tmp_path),
    ):
        pytest.fail("Known incompatible background attachment was admitted")
    assert error.value.code == "cua_background_unavailable"
    assert version in str(error.value)
    record = json.loads((tmp_path / "cua-runtime.json").read_text())
    assert record["admission"] == "background_unavailable"
    assert record["version"] == version and record["closed"] is True
    assert not {"pid", "socket", "session", "daemon_pid", "profile"} & record.keys()
    assert not (tmp_path / "cua.log").exists()


def test_startup_attaches_only_the_new_hidden_worker_browser(tmp_path, monkeypatch):
    from contextlib import contextmanager

    from career_evidence_graph import cua_driver as module

    monkeypatch.setattr(module, "__file__", __file__)
    calls = []
    driver = tmp_path / "synthetic-cua-driver"
    driver.write_bytes(b"Synthetic driver; never executed")
    original_path, original_tempdir = module.Path, module.tempfile.TemporaryDirectory
    monkeypatch.setattr(module.sys, "platform", "darwin")
    monkeypatch.setattr(
        module,
        "Path",
        lambda *parts: (
            driver
            if str(original_path(*parts)) == "/Applications/CuaDriver.app/Contents/MacOS/cua-driver"
            else original_path(*parts)
        ),
    )
    monkeypatch.setattr(
        module.tempfile, "TemporaryDirectory", lambda **kw: original_tempdir(dir=tmp_path)
    )

    @contextmanager
    def hidden_chrome(*args, **kwargs):
        yield SimpleNamespace(), {"pid": 42, "window_id": 7, "launch_date": 1, "hidden": True}

    class Client:
        session = "synthetic-session"

        def __init__(self, *args, **kwargs):
            pass

        def call(self, name, args, **kwargs):
            calls.append((name, args))
            if name == "check_permissions":
                return {"accessibility": True, "screen_recording": True, "source": {"pid": 43}}
            if name == "list_windows":
                return {"windows": [{"pid": 42, "window_id": 7}]}
            if name == "get_browser_state":
                return {
                    "binding_quality": "exact",
                    "endpoint_access_class": "existing_profile_approved",
                    "mutation_allowed": True,
                    "target_id": "owned-target",
                    "tabs": [{"tab_id": "owned-tab", "url": "https://later.example.test/job"}],
                }
            assert name == "browser_prepare"
            assert args == {"pid": 42, "window_id": 7, "strategy": {"kind": "existing_profile"}}
            return {
                "prepared": True,
                "prepared_pid": 42,
                "action": "attached_existing_profile",
                "attachment": {"kind": "existing_profile"},
                "side_effects": {},
            }

        def close(self):
            pass

    def run(command, **kwargs):
        socket = Path(command[command.index("--socket") + 1])
        if "stop" in command:
            socket.unlink(missing_ok=True)
        else:
            assert "--grant" not in command
            socket.touch()
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(module, "managed_hidden_chrome", hidden_chrome, raising=False)
    monkeypatch.setattr(module, "CuaMcpClient", Client)
    monkeypatch.setattr(module.subprocess, "run", run)
    monkeypatch.setattr(
        module.subprocess, "check_output", lambda *a, **k: b'{"binary_version":"test"}'
    )
    with module.managed_cua_browser(None, tmp_path) as (_context, cua):
        assert cua.pid == 42
        cua._bind("https://later.example.test/job", lambda: None)
        monkeypatch.setattr(module.time, "monotonic", lambda: float("inf"))
        cua._bind("https://later.example.test/job", lambda: None)
        cua.client.failed = True
        with pytest.raises(module.PortalDataError, match="Cua") as error:
            cua._bind("https://unapproved.example.test/job", lambda: None)
        assert error.value.code == "cua_result_unknown"
    assert sum(name == "browser_prepare" for name, _ in calls) == 3
    manifest = json.loads((tmp_path / "cua-runtime.json").read_text())["capability_manifest"]
    assert manifest["resources"]["browser"]["existing_profiles"] == [{"pid": 42, "window_id": 7}]
    assert "profiles" not in manifest["resources"]["browser"]
    assert "https://later.example.test" in manifest["resources"]["browser"]["origins"]
    assert manifest["expires_after"] == "24h"


@pytest.mark.worker_browser
def test_cua_combobox_uses_existing_intent_and_reaches_manual_review(tmp_path, monkeypatch):
    from test_generic_worker import URL
    from test_hosted_ats import PDF

    html = "<form>" + FIELDS + COMBOBOX + "<button type='submit'>Submit</button></form>"
    with native_form(tmp_path, monkeypatch, html) as (service, runner, job, posts):
        controls = SyntheticControls()
        runner.cua = controls
        service.request("cancel", {"controller": "synthetic-controller"})
        records = [
            service.store.applications.get_application(job["application_id"]),
            service.store.applications.create_application(
                {
                    "company": "Synthetic",
                    "role_title": "Engineer",
                    "status": "drafting",
                    "url": URL.replace("42", "43"),
                    "application_strategy": "batch",
                }
            ),
        ]
        service.request(
            "prepare",
            {
                "jobs": [
                    {
                        "application_id": r["id"],
                        "revision": r["revision"],
                        "country": "CHE",
                        "filename": "resume.pdf",
                        "file_base64": base64.b64encode(PDF).decode(),
                    }
                    for r in records
                ]
            },
        )
        service.request("resume", {"controller": "synthetic-controller"})
        job = service.store.load()["jobs"][0]
        service.store.answers.put_answer(
            {
                "question": "Application country",
                "value": "Switzerland",
                "scope": {},
                "state": "confirmed",
            }
        )
        runner.tick()
        second = service.store.load()["jobs"][1]
        runner.pages[second["application_id"]].close()
        advance_until(
            service,
            runner,
            lambda row: row["status"] == "ready_for_review",
            application_id=job["application_id"],
        )
        current = service.store.load()["jobs"][0]
        assert current["status"] == "ready_for_review", current["reason"]
        assert current["intent"] is None
        assert current["handed_off"] is False
        assert controls.actions == [("Application country", "Switzerland")]
        fill = next(o for o in current["observations"] if o.get("executor") == "cua_driver")
        assert fill["verified"] is True
        assert fill["intent"]["answer_ref"]["key"] != "one-use"
        assert fill["intent"]["attempt_id"]
        assert fill["input_route"] == "dom_event"
        assert runner.pages[job["application_id"]] not in runner.handed_off_pages
        assert posts == []
        page = runner.pages[job["application_id"]]
        page.evaluate("window.originalFile=document.querySelector('[type=file]').files[0]")
        assert controls.reviewed == []
        service.request("review", {"application_id": job["application_id"]})
        runner.tick()
        assert controls.reviewed == [page]
        assert runner.pages[job["application_id"]] is page
        assert page.evaluate("originalFile===document.querySelector('[type=file]').files[0]")
        assert service.store.load()["jobs"][0]["handoff"]["status"] == "complete"
        assert posts == []
        service.request(
            "recheck", {"application_id": second["application_id"], "acknowledge": True}
        )
        for _ in range(8):
            runner.tick()
        assert controls.opened == [False, False]
        assert runner.pages[job["application_id"]] is page
        assert page.evaluate("originalFile===document.querySelector('[type=file]').files[0]")
        assert service.store.load()["jobs"][1]["status"] == "needs_recheck"
        assert service.store.load()["jobs"][1]["reason"] == "page_changed"


@pytest.mark.worker_browser
def test_cua_review_failure_keeps_send_guard(tmp_path, monkeypatch):
    from career_evidence_graph.career_portal_data import PortalDataError

    with native_form(tmp_path, monkeypatch, "<form>" + FIELDS + "</form>") as (
        service,
        runner,
        job,
        posts,
    ):

        class UnboundControls(SyntheticControls):
            def review(self, page, *, pump):
                raise PortalDataError("cua_binding_ambiguous", "Synthetic refusal", 409)

        runner.cua = UnboundControls()
        advance_until(service, runner, lambda row: row["status"] == "ready_for_review")
        page = runner.pages[job["application_id"]]
        service.request("review", {"application_id": job["application_id"]})
        runner.tick()
        current = service.store.load()["jobs"][0]
        assert current["handoff"]["status"] == "unknown"
        assert current["status"] == "needs_recheck"
        assert current["reason"] == "cua_binding_ambiguous"
        assert page not in runner.handed_off_pages
        page.evaluate("fetch('/submit',{method:'POST',body:'synthetic'}).catch(()=>{})")
        runner.pump()
        assert posts == []
        assert runner.blocked_pages[page] == "unverified_send_path"


@pytest.mark.worker_browser
@pytest.mark.parametrize(
    "change,reason",
    [
        ("answer", "answer_changed"),
        ("pause", "cua_action_invalidated"),
        # A cloned owned marker is rejected before comparing the retained node.
        ("replace", "unsupported_structure"),
        ("file", "file_changed"),
    ],
)
def test_cua_rechecks_authority_between_native_actions(tmp_path, monkeypatch, change, reason):
    html = "<form>" + FIELDS + COMBOBOX + "</form>"
    with native_form(tmp_path, monkeypatch, html) as (service, runner, job, posts):
        service.store.answers.put_answer(
            {
                "question": "Application country",
                "value": "Switzerland",
                "scope": {},
                "state": "confirmed",
            }
        )

        class ChangedControls(SyntheticControls):
            def fill(self, page, question, value, *, check, pump):
                check()
                self.actions.append("open")
                page.get_by_role("combobox").click()
                if change == "answer":
                    service.store.answers.put_answer(
                        {
                            "question": "Application country",
                            "value": "Denmark",
                            "scope": {},
                            "state": "confirmed",
                        }
                    )
                elif change == "pause":
                    service.request("pause", {"controller": "synthetic-controller"})
                elif change == "replace":
                    page.get_by_role("combobox").evaluate("(e)=>e.replaceWith(e.cloneNode(true))")
                else:
                    Path(job["file_path"]).write_bytes(b"%PDF-1.4 changed synthetic file")
                check()
                self.actions.append("choose")
                page.get_by_role("option", name=value, exact=True).click()

        controls = ChangedControls()
        runner.cua = controls
        advance_until(service, runner, lambda row: row["status"] == "needs_recheck")
        current = service.store.load()["jobs"][0]
        assert current["status"] == "needs_recheck"
        assert current["reason"] == reason
        assert current["intent"]["action"] == "fill"
        assert controls.actions == ["open"]
        assert runner.pages[job["application_id"]].get_by_role("combobox").input_value() == ""
        assert not any(o.get("executor") == "cua_driver" for o in current["observations"])
        assert posts == []


@pytest.mark.worker_browser
def test_cua_continues_without_reacquiring_the_expanded_control(tmp_path, monkeypatch):
    from playwright.sync_api import Locator, TimeoutError

    original = Locator.element_handle

    def stalled_adoption(locator, *args, **kwargs):
        # External Playwright boundary fault. The attached node remains unchanged;
        # a new utility-to-main handle transfer after native expansion would stall.
        if (
            "data-ts-worker-field" in str(locator)
            and locator.get_attribute("aria-expanded") == "true"
        ):
            raise TimeoutError("Locator.element_handle: Timeout 4000ms exceeded (adoption stalled)")
        return original(locator, *args, **kwargs)

    monkeypatch.setattr(Locator, "element_handle", stalled_adoption)
    with native_form(tmp_path, monkeypatch, "<form>" + FIELDS + COMBOBOX + "</form>") as (
        service,
        runner,
        job,
        posts,
    ):
        service.store.answers.put_answer(
            {
                "question": "Application country",
                "value": "Switzerland",
                "scope": {},
                "state": "confirmed",
            }
        )
        runner.cua = SyntheticControls()
        advance_until(service, runner, lambda row: row["status"] == "ready_for_review")
        current = service.store.load()["jobs"][0]
        assert current["status"] == "ready_for_review"
        assert current["intent"] is None
        assert (
            runner.pages[job["application_id"]].get_by_role("combobox").input_value()
            == "Switzerland"
        )
        assert any(o.get("executor") == "cua_driver" for o in current["observations"])
        assert posts == []


def test_native_adapter_uses_fresh_refs_and_checks_each_mutation():
    from career_evidence_graph.cua_driver import CuaDriver

    class Client:
        def __init__(self):
            self.clicks = []
            self.snapshot = 0

        def call(self, name, arguments, *, pump=None):
            if name == "list_windows":
                return {"windows": [{"pid": 42, "window_id": 7}]}
            if name == "browser_click":
                self.clicks.append(arguments)
                return {"effect": "unverifiable", "route": "dom"}
            if "pid" in arguments:
                return {
                    "binding_quality": "exact",
                    "endpoint_access_class": "driver_owned",
                    "mutation_allowed": True,
                    "target_id": "owned-target",
                    "tabs": [{"tab_id": "owned-tab", "url": "https://example.test/job"}],
                }
            self.snapshot += 1
            role = "combobox" if self.snapshot == 1 else "option"
            return {
                "target_id": "owned-target",
                "tab_id": "owned-tab",
                "page": {"url": "https://example.test/job"},
                "snapshot": {"complete": True},
                "refs": [
                    {
                        "role": role,
                        "name": "Application country *" if role == "combobox" else "Switzerland",
                        "ref": f"p{self.snapshot}:0",
                        "frame": "main",
                        "actions": ["click"],
                    }
                ],
            }

    client = Client()
    checked = []
    result = CuaDriver(client, 42, click_route="dom_event").fill(
        SimpleNamespace(url="https://example.test/job"),
        {"question": "Application country"},
        "Switzerland",
        check=lambda: checked.append(True),
        pump=lambda: None,
    )
    assert [c["ref"] for c in client.clicks] == ["p1:0", "p2:0"]
    assert all(c["input_route"] == "dom_event" for c in client.clicks)
    assert len(checked) == 2
    assert result == {"executor": "cua_driver", "input_route": "dom_event"}


def test_cua_configuration_is_explicit_and_requires_windowed_browser(tmp_path):
    from career_evidence_graph.application_worker import WorkerService
    from career_evidence_graph.career_portal_data import ApplicationStore

    apps = tmp_path / "applications"
    apps.mkdir()
    store = ApplicationStore(apps)
    service = WorkerService(store, tmp_path / "worker", cua=True, cua_click_route="dom_event")
    assert service.snapshot()["cua_enabled"] is True
    assert service.snapshot()["cua_click_route"] == "dom_event"
    with pytest.raises(ValueError, match="windowed"):
        WorkerService(store, tmp_path / "headless", cua=True, headless=True)
    with pytest.raises(ValueError, match="Cua"):
        WorkerService(store, tmp_path / "route", cua_click_route="dom_event")


@pytest.mark.parametrize(
    "restriction", ["external_profile", "heuristic", "no_mutation", "duplicate_tab"]
)
def test_native_adapter_refuses_unproven_or_ambiguous_binding(restriction):
    from career_evidence_graph.career_portal_data import PortalDataError
    from career_evidence_graph.cua_driver import CuaDriver

    calls = []

    class Client:
        def call(self, name, arguments, *, pump=None):
            calls.append(name)
            if name == "list_windows":
                return {"windows": [{"pid": 42, "window_id": 7}]}
            return {
                "binding_quality": "heuristic" if restriction == "heuristic" else "exact",
                "endpoint_access_class": "external"
                if restriction == "external_profile"
                else "driver_owned",
                "mutation_allowed": restriction != "no_mutation",
                "target_id": "owned-target",
                "tabs": [{"tab_id": "owned-tab", "url": "https://example.test/job"}]
                * (2 if restriction == "duplicate_tab" else 1),
            }

    with pytest.raises(PortalDataError) as error:
        CuaDriver(Client(), 42).fill(
            SimpleNamespace(url="https://example.test/job"),
            {"question": "Country"},
            "Switzerland",
            check=lambda: None,
            pump=lambda: None,
        )
    assert error.value.code == "cua_binding_ambiguous"
    assert "browser_click" not in calls


def test_mcp_unknown_result_does_not_dispatch_again(tmp_path):
    from career_evidence_graph.career_portal_data import PortalDataError
    from career_evidence_graph.cua_driver import CuaMcpClient

    child = tmp_path / "mcp.py"
    calls = tmp_path / "calls.jsonl"
    child.write_text("""import json,sys
for line in sys.stdin:
    r=json.loads(line)
    if 'id' not in r: continue
    if r['method']=='tools/list':
        names=['browser_prepare','get_browser_state','browser_click',
               'list_windows','end_session','check_permissions']
        result={'tools':[{'name':n} for n in names]}
    elif r['method']=='tools/call':
        with open(sys.argv[1],'a') as f: f.write(json.dumps(r['params'])+'\\n')
        continue
    else: result={}
    print(json.dumps({'jsonrpc':'2.0','id':r['id'],'result':result}),flush=True)
""")
    with (tmp_path / "stderr.log").open("w") as log:
        client = CuaMcpClient([sys.executable, "-u", str(child), str(calls)], log, timeout=1)
        try:
            for _ in range(2):
                with pytest.raises(PortalDataError) as error:
                    client.call("browser_click", {"ref": "p1:0"})
                assert error.value.code == "cua_result_unknown"
            assert len(calls.read_text().splitlines()) == 1
        finally:
            client.close()


@pytest.mark.worker_browser
@pytest.mark.skipif(
    os.environ.get("TS_CUA_NATIVE_TEST") != "1", reason="Explicit native Cua opt-in"
)
@pytest.mark.parametrize("mode", ["review", "blocked_send", "ambiguous_option", "later_batch"])
def test_installed_cua_runs_worker_on_isolated_synthetic_form(
    tmp_path, monkeypatch, mode, native_cua_case
):
    from contextlib import nullcontext

    from test_generic_worker import URL
    from test_hosted_ats import prepare

    from career_evidence_graph.application_worker import WorkerService
    from career_evidence_graph.application_worker_browser import ApplicationRunner
    from career_evidence_graph.career_portal_data import ApplicationStore

    apps = tmp_path / "applications"
    apps.mkdir()
    service = WorkerService(ApplicationStore(apps), tmp_path / "worker", live=True, generic=True)
    monkeypatch.setattr(service, "spawn", lambda: None)
    job = prepare(service, URL.replace("careers.", "later.") if mode == "later_batch" else URL)
    for question, value in [
        ("Full name", "Synthetic Person"),
        ("Email", "synthetic@example.invalid"),
        ("Application country", "Switzerland"),
    ]:
        service.store.answers.put_answer(
            {
                "question": question,
                "value": value,
                "scope": {},
                "state": "confirmed",
            }
        )
    service.request("resume", {"controller": "synthetic-controller"})
    combo = COMBOBOX
    if mode == "blocked_send":
        combo = combo.replace(
            "combo.value='Switzerland';",
            "fetch('/submit',{method:'POST',body:'synthetic'}).catch(()=>{});combo.value='Switzerland';",
        )
    if mode == "ambiguous_option":
        combo = combo.replace(
            "<div role='option'>Switzerland</div>",
            "<div role='option'>Switzerland</div><div role='option'>Switzerland</div>",
        )
    html = "<title>Synthetic Careers</title><h1>Engineer</h1><form>" + FIELDS + combo + "</form>"
    native_context, cua = native_cua_case
    with nullcontext(native_context) as context:
        context.set_offline(True)
        runner = ApplicationRunner(service.store, context, cua=cua)
        posts = []
        blocked = []

        def intercept(route):
            class Route:
                request = route.request

                def fetch(self, **options):
                    assert options == {"max_redirects": 0, "max_retries": 0, "timeout": 10000}
                    if self.request.method != "GET":
                        posts.append(self.request.method)
                    return SimpleNamespace(status=200, dispose=lambda: None)

                def fulfill(self, *, response):
                    route.fulfill(status=response.status, body=html, content_type="text/html")

                def abort(self, reason):
                    if self.request.method == "POST":
                        blocked.append(self.request.url)
                    route.abort(reason)

            runner._live_guard(Route())

        context.route("**/*", intercept)
        visibility = []
        for _ in range(8):
            runner.tick()
            visibility.append(
                {
                    **cua.window_state(runner.pages[job["application_id"]]),
                    **browser_app_state(cua.pid),
                }
            )
        report_native("visibility-" + mode, samples=visibility)
        assert all(
            v["windowState"] == "minimized" and v["hidden"] and not v["active"] for v in visibility
        )
        assert not any(
            w["is_on_screen"] for w in cua.client.call("list_windows", {"pid": cua.pid})["windows"]
        )
        current = service.store.load()["jobs"][0]
        if mode in {"review", "later_batch"}:
            assert current["status"] == "ready_for_review", current["reason"]
            assert current["intent"] is None
            assert any(o.get("executor") == "cua_driver" for o in current["observations"])
        else:
            assert current["status"] == "needs_recheck", current["reason"]
            assert current["reason"] == (
                "unverified_send_path" if mode == "blocked_send" else "cua_control_ambiguous"
            )
            assert current["intent"]["action"] == "fill"
            assert not any(o.get("executor") == "cua_driver" for o in current["observations"])
            runner.tick()
            assert service.store.load()["jobs"][0]["intent"] == current["intent"]
        assert current["handed_off"] is False
        assert runner.pages[job["application_id"]] not in runner.handed_off_pages
        assert posts == []
        assert len(blocked) == (1 if mode == "blocked_send" else 0)
        if mode == "review":
            page = runner.pages[job["application_id"]]
            page.evaluate("window.originalFile=document.querySelector('[type=file]').files[0]")
            original_target = page_target_id(page)
            service.request("review", {"application_id": job["application_id"]})
            runner.tick()
            try:
                assert service.store.load()["jobs"][0]["handoff"]["status"] == "complete"
                assert cua.window_state(page)["windowState"] == "normal"
                assert not browser_app_state(cua.pid)["hidden"]
                assert runner.pages[job["application_id"]] is page
                cua._bind(page.url, runner.pump)
                assert page_target_id(page) == original_target
                assert any(
                    w["is_on_screen"]
                    for w in cua.client.call("list_windows", {"pid": cua.pid})["windows"]
                )
                assert page.evaluate(
                    "originalFile===document.querySelector('[type=file]').files[0]"
                )
                assert page.get_by_role("combobox").input_value() == "Switzerland"
                assert posts == []
            finally:
                cua.window_state(page, state="minimized")
                from career_evidence_graph.cua_driver import mac_chrome_state

                mac_chrome_state(cua.pid, launch_date=cua.launch_date, action="hide")
        report_native(
            "native-" + mode,
            status=current["status"],
            reason=current["reason"],
            allowed_posts=len(posts),
            blocked_posts=len(blocked),
            automatic_final_submits=0,
            cua_fill_verified=any(
                o.get("executor") == "cua_driver" for o in current["observations"]
            ),
            unknown_intent_retained=current["intent"] is not None,
            real_ats_calls=0,
            model_calls=0,
            tool_runtime="CuaDriver native MCP",
            hidden_samples=visibility,
            manual_review_show_count=1 if mode == "review" else 0,
            same_page_and_file_preserved=mode == "review",
        )


@pytest.fixture(scope="module")
def resident_cua(tmp_path_factory):
    from playwright.sync_api import sync_playwright

    from career_evidence_graph.career_portal_data import PortalDataError
    from career_evidence_graph.cua_driver import mac_chrome_state, managed_cua_browser

    root = tmp_path_factory.mktemp("resident-cua")
    with (
        sync_playwright() as playwright,
        managed_cua_browser(
            playwright, root, click_route="dom_event", origins=["https://careers.example.test"]
        ) as (context, cua),
    ):
        record = json.loads((root / "cua-runtime.json").read_text())
        assert record["startup_target_count"] == 0
        assert not any(w["is_on_screen"] for w in record["startup_windows"])
        assert mac_chrome_state(cua.pid, launch_date=cua.launch_date)["hidden"]
        refused = []
        for target in [
            {"pid": 1, "window_id": cua.window_id},
            {"pid": cua.pid, "window_id": cua.window_id + 1000000},
        ]:
            with pytest.raises(PortalDataError) as error:
                cua.client.call("get_browser_state", target)
            assert error.value.code == "cua_refused"
            refused.append(target)
        report_native("startup", **record, rejected_targets=refused)
        yield context, cua
    record = json.loads((root / "cua-runtime.json").read_text())
    assert record["closed"] is True
    report_native("resident-runtime", **record)


@pytest.fixture
def native_cua_case(resident_cua):
    context, cua = resident_cua
    anchor = context.pages[0]
    try:
        yield context, cua
    finally:
        context.unroute("**/*")
        for page in context.pages:
            if page is not anchor:
                page.close()


@pytest.mark.worker_browser
@pytest.mark.skipif(
    os.environ.get("TS_CUA_NATIVE_TEST") != "1", reason="Explicit native Cua opt-in"
)
def test_cua_worker_process_stops_its_private_runtime(tmp_path):
    from worker_preview_support import running_preview, stop_worker

    with running_preview(tmp_path, 1, cua=True) as preview:
        preview.seed(
            "Will you now or in the future require visa sponsorship?", "No", {"country": "CHE"}
        )
        preview.prepare(["CHE"])
        preview.post("resume", controller=preview.controller)
        state = preview.wait(lambda s: s["jobs"][0]["status"] == "ready_for_review")
        assert len(preview.events()["uploads"]) == 1
        assert preview.events()["submissions"] == []
        assert state["cua_enabled"] is True
        assert "src/career_evidence_graph/cua_driver.py" in state["runtime"]["source"]["files"]
        stop_worker(preview)
        record = json.loads((preview.store.root / "cua-runtime.json").read_text())
        try:
            assert record["closed"] is True
            assert not Path(record["socket"]).exists()
            assert record["startup_target_count"] == 0
            assert not any(w["is_on_screen"] for w in record["startup_windows"])
            for pid in [record["pid"], record["daemon_pid"], record["discovery_daemon_pid"]]:
                assert subprocess.run(["ps", "-p", str(pid)], capture_output=True).returncode != 0
            report_native(
                "native-process",
                **record,
                startup_source=state["runtime"]["source"],
                uploads=len(preview.events()["uploads"]),
                automatic_final_submits=len(preview.events()["submissions"]),
                real_ats_calls=0,
                model_calls=0,
            )
        finally:
            if not record["closed"]:
                subprocess.run(
                    [
                        "/Applications/CuaDriver.app/Contents/MacOS/cua-driver",
                        "stop",
                        "--socket",
                        record["socket"],
                    ],
                    check=True,
                    timeout=10,
                )
