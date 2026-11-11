"""Explicit native browser fixtures remain isolated and never contact an employer."""

import base64
import hashlib
import json
import os
import select
import socket
import subprocess
import sys
import time
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import urlsplit

import pytest
from test_installed_preparation_mode import preparation_launch_executable as _launch_executable
from test_installed_preparation_mode import request, stop_backend
from worker_preview_support import advance_until

preparation_launch_executable = _launch_executable

CHECKOUT = Path(__file__).resolve().parents[1]
GENERATOR = CHECKOUT / "scripts/create_synthetic_flow.py"
SYNTHETIC_PDF = b"%PDF-1.4 synthetic only"


def create_browser(root, scenario="dom"):
    return subprocess.run(
        [sys.executable, "-B", str(GENERATOR), "--browser", scenario, str(root)],
        capture_output=True,
        text=True,
        timeout=10,
    )


def test_generator_creates_a_separate_fixed_browser_identity_without_starting_work(tmp_path):
    from career_evidence_graph.career_portal_data import ApplicationStore

    root = tmp_path / "browser fixture"
    result = create_browser(root)
    assert result.returncode == 0, result.stderr
    marker = json.loads((root / "synthetic-flow.json").read_text())
    assert marker == {
        "schemaVersion": 1,
        "purpose": "browser-synthetic",
        "codex_sha256": hashlib.sha256((root / "codex-fixture").read_bytes()).hexdigest(),
    }
    assert json.loads((root / "browser-fixture.json").read_text()) == {
        "schemaVersion": 1,
        "scenario": "dom",
    }
    app = ApplicationStore(root / "applications").list_applications()[0]
    assert app["url"] == "https://careers.example.test/jobs/browser-synthetic"
    assert app["company"] == "Synthetic Employer" and app["role_title"] == "Software Engineer"
    assert app["job_description"] == "Python\nunit tests"
    assert list((root / "runtime/single-job-worker").iterdir()) == []
    assert list((root / "runtime/single-job-flow").iterdir()) == []


def test_native_browser_mode_has_an_explicit_isolated_entry(
    tmp_path, preparation_launch_executable
):
    root = tmp_path / "browser fixture"
    assert create_browser(root).returncode == 0
    result = subprocess.run(
        [str(preparation_launch_executable), "--synthetic-browser", str(root)],
        capture_output=True,
        text=True,
        timeout=5,
    )
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == {
        "config": str(root / "portal.json"),
        "arguments": ["--synthetic-browser", str(root)],
        "flowTitle": "单岗位申请",
        "windowTitle": "TomorrowStar · 合成浏览器验收",
        "canSave": False,
        "external": False,
        "loopback": True,
    }


def test_backend_exposes_only_the_isolated_synthetic_browser_worker(tmp_path):
    root = tmp_path / "browser fixture"
    assert create_browser(root).returncode == 0
    unrelated = tmp_path / "unrelated home"
    unrelated.mkdir()
    process = subprocess.Popen(
        [
            sys.executable,
            "-I",
            "-B",
            "-u",
            str(CHECKOUT / "macos/server.py"),
            "--synthetic-browser",
            str(root),
        ],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=os.environ
        | {
            "HOME": str(unrelated),
            "OPENAI_API_KEY": "synthetic-must-clear",
            "TOMORROWSTAR_CODEX_EXECUTABLE": "/invalid/formal-cli",
        },
    )
    try:
        assert select.select([process.stdout], [], [], 8)[0]
        line = process.stdout.readline()
        assert line, process.stderr.read()
        ready = json.loads(line)
        assert ready["status"] == "ready", ready
        assert ready["capabilities"] == {
            "codex": True,
            "flow": True,
            "worker": True,
            "synthetic": True,
        }
        address = urlsplit(ready["url"])
        status, flow = request(address, "GET", "/api/flow/state")
        assert status == 200 and flow["capabilities"]["worker"] is True
        assert flow["tasks"] == [] and flow["worker"]["enabled"] is False
        state = json.loads((root / "runtime/single-job-worker/run.json").read_text())
        assert state["jobs"] == [] and state["worker_pid"] is None
        assert state["mode"] == "live" and state["generic_enabled"]
        assert list(unrelated.iterdir()) == []
        assert not (root / "runtime/single-job-worker/cua-runtime.json").exists()
        assert not (root / "runtime/single-job-worker/worker.log").exists()
    finally:
        stop_backend(process)


def test_fixed_transport_requires_the_live_guard_and_never_continues_network(tmp_path):
    from career_evidence_graph.application_worker_fixtures import install_browser_fixture

    root = tmp_path / "browser fixture"
    assert create_browser(root).returncode == 0
    routes, sockets, events = [], [], []
    context = SimpleNamespace(
        route=lambda pattern, callback: routes.append(callback),
        route_web_socket=lambda pattern, callback: sockets.append(callback),
    )
    permitted = True

    def live_guard(route):
        events.append("live_guard")
        route.continue_() if permitted else route.abort("blockedbyclient")

    runner = SimpleNamespace(_live_guard=live_guard)
    install_browser_fixture(context, runner, root)

    def dispatch(method="GET", url="https://careers.example.test/jobs/browser-synthetic"):
        result = []
        route = SimpleNamespace(
            request=SimpleNamespace(method=method, url=url),
            fulfill=lambda **payload: result.append(("fulfill", payload)),
            abort=lambda reason: result.append(("abort", reason)),
            continue_=lambda: (_ for _ in ()).throw(AssertionError("Real network continuation")),
        )
        routes[-1](route)
        return result

    response = dispatch()
    assert events == ["live_guard"] and response[0][0] == "fulfill"
    assert "Manual acceptance checkpoint" in response[0][1]["body"]
    permitted = False
    assert dispatch()[0][0] == "abort"
    permitted = True
    assert dispatch("POST")[0][0] == "abort"
    assert dispatch(url="https://example.com/private")[0][0] == "abort"
    assert (
        dispatch(url="https://careers.example.test/jobs/browser-synthetic?other=1")[0][0] == "abort"
    )


def test_synthetic_socket_stays_local_without_synchronous_close_in_a_route_callback(tmp_path):
    from career_evidence_graph.application_worker_browser import ApplicationRunner
    from career_evidence_graph.application_worker_fixtures import (
        install_browser_fixture,
        isolate_browser_fixture,
    )

    root = tmp_path / "browser fixture"
    assert create_browser(root).returncode == 0
    callbacks, messages = [], []
    context = SimpleNamespace(
        route=lambda *args: None,
        route_web_socket=lambda pattern, callback: callbacks.append(callback),
    )
    runner = SimpleNamespace(_live_guard=lambda route: None, handed_off_pages={"handed-off"})
    isolate_browser_fixture(context)
    install_browser_fixture(context, runner, root)
    socket = SimpleNamespace(
        close=lambda: pytest.fail("Sync close inside route callback blocks the dispatcher"),
        connect_to_server=lambda: pytest.fail("Synthetic socket connected to a server"),
        on_message=lambda callback: messages.append(callback),
    )
    for callback in callbacks:
        callback(socket)
    ApplicationRunner._websocket_guard(runner, "handed-off", socket)
    assert len(messages) == 3
    assert all(callback("synthetic discarded message") is None for callback in messages)


def test_worker_cli_validates_the_mode_before_reaching_owned_browser_start(tmp_path, monkeypatch):
    from career_evidence_graph import application_worker_browser as browser
    from career_evidence_graph.application_worker import WorkerService
    from career_evidence_graph.career_portal_data import ApplicationStore

    root = tmp_path / "browser fixture"
    assert create_browser(root).returncode == 0
    WorkerService(
        ApplicationStore(root / "applications"),
        root / "runtime/single-job-worker",
        live=True,
        generic=True,
        cua=True,
        cua_click_route="dom_event",
        synthetic_browser_root=root,
    )

    @contextmanager
    def playwright_boundary():
        assert os.environ["HOME"] == str(root / "home")
        assert os.environ["TMPDIR"] == str(root / "tmp")
        assert os.environ["TOMORROWSTAR_CODEX_EXECUTABLE"] == str(root / "codex-fixture")
        assert "OPENAI_API_KEY" not in os.environ
        assert "PYTHONPATH" not in os.environ
        yield None

    def boundary(playwright, worker_root, **options):
        assert worker_root == root / "runtime/single-job-worker"
        assert options["synthetic_keychain"] is True
        raise RuntimeError("Owned browser boundary reached without starting a browser")

    monkeypatch.setattr(browser, "sync_playwright", playwright_boundary)
    monkeypatch.setattr(browser, "managed_cua_browser", boundary)
    monkeypatch.setattr(
        browser.os,
        "environ",
        dict(os.environ)
        | {
            "OPENAI_API_KEY": "synthetic",
            "PYTHONPATH": "/unrelated/source",
            "TOMORROWSTAR_CODEX_EXECUTABLE": "/invalid/formal-cli",
        },
    )
    arguments = [
        "--applications",
        str(root / "applications"),
        "--runtime",
        str(root / "runtime/single-job-worker"),
        "--live",
        "--cua",
        "--cua-click-route",
        "dom_event",
        "--synthetic-browser",
        str(root),
    ]
    with pytest.raises(RuntimeError, match="Owned browser boundary reached"):
        browser.main(arguments)


def test_ordinary_worker_never_requests_the_synthetic_keychain(tmp_path, monkeypatch):
    from career_evidence_graph import application_worker_browser as browser
    from career_evidence_graph.application_worker import WorkerService
    from career_evidence_graph.career_portal_data import ApplicationStore

    applications, runtime = tmp_path / "applications", tmp_path / "runtime"
    applications.mkdir()
    WorkerService(ApplicationStore(applications), runtime, live=True, cua=True)

    @contextmanager
    def playwright_boundary():
        yield None

    def boundary(playwright, worker_root, **options):
        assert options["synthetic_keychain"] is False
        raise RuntimeError("Ordinary browser boundary reached without starting a browser")

    monkeypatch.setenv("CUA_E2E_USE_MOCK_KEYCHAIN", "1")
    monkeypatch.setattr(browser, "sync_playwright", playwright_boundary)
    monkeypatch.setattr(browser, "managed_cua_browser", boundary)
    with pytest.raises(RuntimeError, match="Ordinary browser boundary reached"):
        browser.main(
            ["--applications", str(applications), "--runtime", str(runtime), "--live", "--cua"]
        )


def test_synthetic_child_admits_retained_legacy_single_binding_before_browser_start(
    tmp_path, monkeypatch
):
    from legacy_full_latex_support import LegacyFullLatexFixtureStore

    from career_evidence_graph import application_worker_browser as browser
    from career_evidence_graph.career_portal import create_server

    root = tmp_path / "browser fixture"
    assert create_browser(root).returncode == 0
    monkeypatch.setattr(
        browser.os,
        "environ",
        {
            "PATH": "/usr/bin:/bin:/usr/sbin:/sbin",
            "LANG": "en_US.UTF-8",
            "HOME": str(root / "home"),
            "TMPDIR": str(root / "tmp"),
            "TOMORROWSTAR_CODEX_EXECUTABLE": str(root / "codex-fixture"),
        },
    )

    def resume_factory(applications, catalog, directory):
        raw = (CHECKOUT / "tests/fixtures/pdf-export/current-template.pdf").read_bytes()
        return LegacyFullLatexFixtureStore(
            applications,
            catalog,
            directory,
            prism_client=SimpleNamespace(
                configuration=lambda: {"synthetic": "latex-compiler-boundary"},
                compile=lambda binding: {
                    "build": {"main": binding["main"], "exit": 0, "pdf_updated": True},
                    "pdf": raw,
                },
            ),
        )

    server = create_server(
        root / "applications",
        root / "career",
        write_admission_policy="development",
        flow_root=root / "runtime/single-job-flow",
        worker_root=root / "runtime/single-job-worker",
        worker_live=True,
        worker_generic=True,
        worker_cua=True,
        worker_cua_click_route="dom_event",
        worker_synthetic_browser_root=root,
        flow_resume_factory=resume_factory,
    )
    try:
        flow = server.application_flow_service
        app = server.worker_service.store.applications.list_applications()[0]
        task = flow.create(app["id"], app["revision"])
        # This browser-binding fixture resumes a saved pre-JSON task.
        # New tasks retain their content contract and cannot use this producer.
        with flow.applications.write_lock():
            state = flow._load()
            flow._task(state, task["id"]).pop("material_contract", None)
            flow._save(state)
        task = flow.snapshot()["active_task"]
        for stage, expected in [
            ("analysis", "analysis_ready"),
            ("resume", "draft_ready"),
            ("export", "materials_ready"),
        ]:
            if stage == "resume":
                task = flow.prepare_automatic_materials(
                    task["id"], task["revision"], str(root / "latex-base"), "main.tex"
                )
            flow.start(task["id"], task["revision"], stage)
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline:
                task = flow.snapshot()["active_task"]
                if task["status"] == expected:
                    break
                assert task["stages"][stage]["status"] != "failed", task["stages"][stage]
                time.sleep(0.005)
            assert task["status"] == expected
        flow.prepare_worker(task["id"], task["revision"], "CHE", True)
        flow_root = root / "runtime/single-job-flow"
        preserved = {path: path.read_bytes() for path in flow_root.rglob("*") if path.is_file()}

        def boundary():
            assert os.environ["TOMORROWSTAR_CODEX_EXECUTABLE"] == str(root / "codex-fixture")
            raise RuntimeError("Default single binding admitted before browser start")

        monkeypatch.setattr(browser, "sync_playwright", boundary)
        monkeypatch.setenv("TOMORROWSTAR_CODEX_EXECUTABLE", "/invalid/formal-cli")
        with pytest.raises(RuntimeError, match="Default single binding admitted"):
            browser.main(
                [
                    "--applications",
                    str(root / "applications"),
                    "--runtime",
                    str(root / "runtime/single-job-worker"),
                    "--single-flow-root",
                    str(flow_root),
                    "--live",
                    "--cua",
                    "--cua-click-route",
                    "dom_event",
                    "--synthetic-browser",
                    str(root),
                ]
            )
        assert all(path.read_bytes() == raw for path, raw in preserved.items())
    finally:
        server.server_close()


def test_spawn_propagates_only_the_isolated_browser_identity_and_environment(tmp_path, monkeypatch):
    from career_evidence_graph.application_worker import WorkerService
    from career_evidence_graph.career_portal_data import ApplicationStore

    root = tmp_path / "browser fixture"
    assert create_browser(root).returncode == 0
    service = WorkerService(
        ApplicationStore(root / "applications"),
        root / "runtime/single-job-worker",
        live=True,
        generic=True,
        cua=True,
        cua_click_route="dom_event",
        synthetic_browser_root=root,
    )
    calls = []
    monkeypatch.setenv("OPENAI_API_KEY", "synthetic-must-not-propagate")
    monkeypatch.setenv("HOME", str(tmp_path / "unrelated"))
    monkeypatch.setattr(
        "career_evidence_graph.application_worker.subprocess.Popen",
        lambda args, **kwargs: calls.append((args, kwargs)) or SimpleNamespace(pid=42),
    )
    service.spawn()
    arguments, options = calls[0]
    assert arguments[-2:] == ["--synthetic-browser", str(root)]
    assert "--live" in arguments and "--cua" in arguments
    assert options["env"]["HOME"] == str(root / "home")
    assert options["env"]["TMPDIR"] == str(root / "tmp")
    assert "OPENAI_API_KEY" not in options["env"]


@pytest.mark.parametrize(
    "damage",
    [
        "old-purpose",
        "paths",
        "scenario-url",
        "scenario-list",
        "extra-html",
        "cli-bytes",
        "root-link",
        "config-link",
        "runtime-link",
        "boolean-version",
    ],
)
def test_browser_contract_rejects_other_identities_and_overrides_before_work(tmp_path, damage):
    from career_evidence_graph.application_worker_fixtures import browser_fixture_configuration

    root = tmp_path / "browser fixture"
    assert create_browser(root).returncode == 0
    if damage == "old-purpose":
        path = root / "synthetic-flow.json"
        value = json.loads(path.read_text())
        value["purpose"] = "single-job-synthetic"
        path.write_text(json.dumps(value))
    elif damage == "paths":
        (root / "portal.json").write_text(
            '{"applications":"/outside","career_workspace":"/outside"}'
        )
    elif damage in {"scenario-url", "scenario-list", "extra-html", "boolean-version"}:
        value = {"schemaVersion": 1, "scenario": "dom"}
        if damage == "scenario-url":
            value["scenario"] = "https://example.com"
        elif damage == "scenario-list":
            value["scenario"] = []
        elif damage == "extra-html":
            value["html"] = "<script>fetch('/submit')</script>"
        else:
            value["schemaVersion"] = True
        (root / "browser-fixture.json").write_text(json.dumps(value))
    elif damage == "cli-bytes":
        (root / "codex-fixture").write_text("#!/bin/sh\nexit 92\n")
    elif damage == "root-link":
        link = tmp_path / "alias"
        link.symlink_to(root)
        root = link
    elif damage == "config-link":
        path = root / "portal.json"
        path.rename(root / "other.json")
        path.symlink_to(root / "other.json")
    else:
        path = root / "runtime/single-job-worker"
        path.rmdir()
        path.symlink_to(tmp_path)
    with pytest.raises(ValueError):
        browser_fixture_configuration(root)


@pytest.mark.parametrize("damage", ["payload", "interpreter", "flags"])
def test_re_signed_cli_cannot_replace_source_owned_replay_or_its_interpreter(tmp_path, damage):
    from career_evidence_graph.application_worker_fixtures import browser_fixture_configuration

    root = tmp_path / "browser fixture"
    assert create_browser(root).returncode == 0
    executable = root / "codex-fixture"
    script = executable.read_text()
    if damage == "payload":
        script = script.replace("import json\n", "import json\nraise SystemExit(92)\n", 1)
    elif damage == "interpreter":
        script = script.replace(sys.executable, "/bin/sh", 1)
    else:
        script = script.replace(" -I -B ", " -B ", 1)
    assert script != executable.read_text()
    executable.write_text(script)
    marker_path = root / "synthetic-flow.json"
    marker = json.loads(marker_path.read_text())
    marker["codex_sha256"] = hashlib.sha256(executable.read_bytes()).hexdigest()
    marker_path.write_text(json.dumps(marker))
    with pytest.raises(ValueError):
        browser_fixture_configuration(root)


@contextmanager
def synthetic_runner(tmp_path, monkeypatch, scenario):
    from playwright.sync_api import sync_playwright

    from career_evidence_graph.application_worker import WorkerService, start_run
    from career_evidence_graph.application_worker_browser import ApplicationRunner
    from career_evidence_graph.application_worker_fixtures import (
        install_browser_fixture,
        isolate_browser_fixture,
    )
    from career_evidence_graph.career_portal_data import ApplicationStore

    monkeypatch.setenv("PLAYWRIGHT_BROWSERS_PATH", "0")
    root = tmp_path / "browser fixture"
    assert create_browser(root, scenario).returncode == 0
    apps = ApplicationStore(root / "applications")
    app = apps.list_applications()[0]
    app = apps.update_application(
        app["id"], {"status": "drafting", "application_strategy": "batch"}, app["revision"]
    )
    service = WorkerService(
        apps,
        root / "runtime/single-job-worker",
        live=True,
        generic=True,
        cua=True,
        cua_click_route="dom_event",
        synthetic_browser_root=root,
    )
    monkeypatch.setattr(service, "spawn", lambda: None)
    service.request(
        "prepare",
        {
            "jobs": [
                {
                    "application_id": app["id"],
                    "revision": app["revision"],
                    "country": "CHE",
                    "filename": "synthetic.pdf",
                    "file_base64": base64.b64encode(SYNTHETIC_PDF).decode(),
                }
            ]
        },
    )
    for question, value in (
        ("Full name", "Synthetic Person"),
        ("Email", "synthetic@example.invalid"),
        ("Application country", "Switzerland"),
    ):
        service.store.answers.put_answer(
            {"question": question, "value": value, "scope": {}, "state": "confirmed"}
        )
    start_run(service.store)
    service.request("resume", {"controller": "synthetic-browser-test"})

    class CuaBoundary:
        click_route = "dom_event"

        def new_page(self, context, **kwargs):
            return context.new_page()

        def fill(self, *args, **kwargs):
            raise AssertionError("Fixture must not dispatch Cua filling")

        def review(self, page, **kwargs):
            pass

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(
            headless=True,
            channel="chromium",
            env=os.environ | {"HOME": str(root / "home"), "TMPDIR": str(root / "tmp")},
        )
        try:
            context = browser.new_context(service_workers="block", offline=True)
            context.set_default_timeout(3000)
            isolate_browser_fixture(context)
            runner = ApplicationRunner(service.store, context, cua=CuaBoundary())
            install_browser_fixture(context, runner, root)
            yield service, runner, context
        finally:
            browser.close()


def assert_synthetic_resume(page, job):
    control = page.locator("input[type=file]")
    assert control.evaluate("e=>e.files.length") == 1
    assert control.evaluate("e=>e.files[0].name") == job["filename"]
    raw = bytes(
        control.evaluate("async e=>Array.from(new Uint8Array(await e.files[0].arrayBuffer()))")
    )
    assert raw == SYNTHETIC_PDF
    assert hashlib.sha256(raw).hexdigest() == job["file_sha256"]


@pytest.mark.worker_browser
@pytest.mark.parametrize(
    "scenario,status,fills",
    [
        ("dom", "needs_input", 3),
        pytest.param("manual", "needs_input", 2, id="manual-color-kept-at-checkpoint"),
        ("unknown", "needs_recheck", 2),
    ],
)
def test_fixed_browser_scenarios_keep_exact_selection_and_safe_answer_stops(
    tmp_path, monkeypatch, scenario, status, fills
):
    with synthetic_runner(tmp_path, monkeypatch, scenario) as (service, runner, context):
        job = advance_until(service, runner, lambda row: row["status"] == status)
        assert job["status"] == status, job["reason"]
        verified = [
            o for o in job["observations"] if o.get("action") == "fill" and o.get("verified")
        ]
        assert len(verified) == fills
        assert not any(o.get("action") == "upload" for o in job["observations"])
        page = runner.pages[job["application_id"]]
        assert page.locator("input[name=untouched]").input_value() == "Preserve this value"
        assert page.locator("input[name=checkpoint]").input_value() == ""
        assert_synthetic_resume(page, job)
        assert page.evaluate("window.syntheticSubmitAttempts") == 0
        actions = page.evaluate("window.syntheticBrowserActions")
        assert actions == ([] if scenario == "manual" else ["open", "choose"])
        if scenario == "manual":
            assert job["reason"] == "missing_answers"
            assert [row["question"] for row in job["questions"]] == ["Manual acceptance checkpoint"]
            color = next(
                row
                for row in job["form_state"]["snapshot"]["fields"]
                if row["question"] == "Application country"
            )
            assert color["type"] == "color" and color["value"] == "#000000"
            difference = job["form_state"]["differences"]
            assert len(difference) == 1
            assert difference[0]["current_value"] == "#000000"
            assert difference[0]["proposed_value"] == "Switzerland"
            assert page.locator("input[type=color]").input_value() == "#000000"
        if scenario == "unknown":
            assert job["intent"]["action"] == "fill"
        else:
            assert job["intent"] is None
        runner.tick()
        runner.pump()
        assert page.evaluate("window.syntheticBrowserActions") == actions


@pytest.mark.worker_browser
def test_handoff_cannot_open_synthetic_http_or_websocket_network_bypasses(tmp_path, monkeypatch):
    from playwright.sync_api import Route, WebSocketRoute

    with synthetic_runner(tmp_path, monkeypatch, "dom") as (service, runner, context):
        job = advance_until(service, runner, lambda row: row["status"] == "needs_input")
        assert job["status"] == "needs_input"
        service.request("review", {"application_id": job["application_id"], "acknowledge": True})
        runner.tick()
        page = runner.pages[job["application_id"]]
        current = service.store.load()["jobs"][0]
        assert current["handoff"]["status"] == "complete"
        assert page in runner.handed_off_pages
        fills = [o for o in current["observations"] if o.get("action") == "fill"]
        attempts = []

        def forbidden(*args, **kwargs):
            attempts.append("network_connection_attempt")

        monkeypatch.setattr(WebSocketRoute, "connect_to_server", forbidden)
        monkeypatch.setattr(Route, "continue_", forbidden)
        failures = []
        page.on("requestfailed", lambda request: failures.append(request.failure))
        with socket.socket() as sink:
            sink.bind(("127.0.0.1", 0))
            sink.listen(8)
            port = sink.getsockname()[1]
            result = page.evaluate(
                """async port => {
              const abort=new AbortController();
              const ws=new WebSocket(`wss://127.0.0.1:${port}/blocked`);
              let opened=false;
              try {return await Promise.race([
                Promise.all([fetch(`https://127.0.0.1:${port}/blocked`,{signal:abort.signal})
                  .then(()=>false).catch(()=>true),new Promise(resolve=>{
                    ws.onopen=()=>{
                      opened=true;ws.send('discard this synthetic message');ws.close();};
                    ws.onclose=()=>resolve({opened,closed:true});
                    ws.onerror=()=>resolve({opened,error:true});})])
                  .then(([http,socket])=>({http,socket})),
                new Promise(resolve=>setTimeout(()=>resolve({timeout:true}),2000))]);
              } finally {abort.abort();ws.close();}}""",
                port,
            )
            sink.settimeout(0.01)
            with pytest.raises(TimeoutError):
                sink.accept()
        assert result == {"http": True, "socket": {"opened": True, "closed": True}}
        assert attempts == []
        assert any("BLOCKED_BY_CLIENT" in failure for failure in failures)
        assert_synthetic_resume(page, job)
        assert page.evaluate("window.syntheticSubmitAttempts") == 0
        assert runner.pages[job["application_id"]] is page and page.context is context
        current = service.store.load()["jobs"][0]
        assert fills == [o for o in current["observations"] if o.get("action") == "fill"]


@pytest.mark.parametrize("override", ["single_flow_root", "single_career_root", "legacy_roots"])
def test_synthetic_service_rejects_other_single_job_contexts(tmp_path, override):
    from career_evidence_graph.application_worker import WorkerService
    from career_evidence_graph.career_portal_data import ApplicationStore

    root = tmp_path / "browser fixture"
    assert create_browser(root).returncode == 0
    outside = tmp_path / "outside"
    value = [outside] if override == "legacy_roots" else outside
    with pytest.raises(ValueError):
        WorkerService(
            ApplicationStore(root / "applications"),
            root / "runtime/single-job-worker",
            live=True,
            generic=True,
            cua=True,
            cua_click_route="dom_event",
            synthetic_browser_root=root,
            **{override: value},
        )
    assert not outside.exists()


@pytest.mark.parametrize("damage", ["missing", "relative", "equals", "mixed", "config", "linked"])
def test_native_browser_mode_never_falls_back_to_the_ordinary_workspace(
    tmp_path, preparation_launch_executable, damage
):
    root = tmp_path / "browser fixture"
    assert create_browser(root).returncode == 0
    arguments = ["--synthetic-browser", str(root)]
    if damage == "missing":
        arguments.pop()
    elif damage == "relative":
        arguments[-1] = root.name
    elif damage == "equals":
        arguments = ["--synthetic-browser=" + str(root)]
    elif damage == "mixed":
        arguments += ["--synthetic-flow", str(root)]
    elif damage == "config":
        arguments += ["--config", str(root / "portal.json")]
    else:
        link = tmp_path / "alias"
        link.symlink_to(root)
        arguments[-1] = str(link)
    result = subprocess.run(
        [str(preparation_launch_executable), *arguments], capture_output=True, text=True, timeout=5
    )
    assert result.returncode == 2 and not result.stdout


@pytest.mark.parametrize(
    "override", ["--applications", "--worker-root", "--flow-root", "--codex-executable"]
)
def test_backend_browser_mode_rejects_root_and_provider_overrides(tmp_path, override):
    root = tmp_path / "browser fixture"
    assert create_browser(root).returncode == 0
    outside = tmp_path / "outside"
    result = subprocess.run(
        [
            sys.executable,
            "-I",
            "-B",
            str(CHECKOUT / "macos/server.py"),
            "--synthetic-browser",
            str(root),
            override,
            str(outside),
        ],
        capture_output=True,
        text=True,
        timeout=5,
    )
    assert result.returncode == 2
    assert json.loads(result.stdout) == {"status": "error", "code": "workspace-unavailable"}
    assert not outside.exists()


@pytest.mark.parametrize(
    "override", ["applications", "runtime", "single-flow-root", "headless", "no-cua"]
)
def test_child_cli_rejects_synthetic_overrides_before_starting_any_browser(
    tmp_path, monkeypatch, override
):
    from career_evidence_graph import application_worker_browser as browser

    root = tmp_path / "browser fixture"
    assert create_browser(root).returncode == 0
    outside = tmp_path / "outside"
    arguments = [
        "--applications",
        str(root / "applications"),
        "--runtime",
        str(root / "runtime/single-job-worker"),
        "--live",
        "--cua",
        "--cua-click-route",
        "dom_event",
        "--synthetic-browser",
        str(root),
    ]
    if override in {"applications", "runtime"}:
        arguments[arguments.index("--" + override) + 1] = str(outside)
    elif override == "single-flow-root":
        arguments += ["--single-flow-root", str(outside)]
    elif override == "headless":
        arguments += ["--headless"]
    else:
        arguments.remove("--cua")
    monkeypatch.setattr(
        browser, "sync_playwright", lambda: pytest.fail("Invalid mode reached a browser")
    )
    with pytest.raises(SystemExit) as error:
        browser.main(arguments)
    assert error.value.code == 2 and not outside.exists()
