"""Fixed, offline diagnostic run by the native App; never request TCC grants."""

from __future__ import annotations

import base64
import ctypes
import hashlib
import json
import os
import plistlib
import signal
import subprocess
import sys
import tempfile
import time
from copy import deepcopy
from pathlib import Path


def observe_page_matrix(context, driver, page, root):
    """Fixed synthetic fault cases through the actual retained-page command handler."""
    from playwright.sync_api import Error

    from career_evidence_graph.application_worker import WorkerService, WorkerStore, start_run
    from career_evidence_graph.application_worker_browser import ApplicationRunner
    from career_evidence_graph.career_portal_data import ApplicationStore, PortalDataError
    from career_evidence_graph.validation.hashing import record_digest as digest

    apps = root / "observation-applications"
    apps.mkdir(mode=0o700)
    service = WorkerService(
        ApplicationStore(apps), root / "observation-worker", live=True, generic=True, cua=True
    )
    app = service.store.applications.create_application(
        {
            "company": "Synthetic",
            "role_title": "Observation diagnostic",
            "status": "drafting",
            "url": "https://synthetic.invalid/check",
            "application_strategy": "batch",
        }
    )
    service.request(
        "prepare",
        {
            "jobs": [
                {
                    "application_id": app["id"],
                    "revision": app["revision"],
                    "country": "CHE",
                    "filename": "synthetic.pdf",
                    "file_base64": base64.b64encode(b"%PDF-1.4 synthetic observation").decode(),
                }
            ]
        },
    )
    run_id = start_run(service.store)
    runner = ApplicationRunner(service.store, context, cua=driver)
    original_client = driver.client
    original_pages = len(context.pages)
    decoy = driver.new_page(context)
    decoy.set_content('<title>Decoy tab</title><input value="wrong page">')
    runner.pages[app["id"]] = page
    runner.page_ids[page] = "native-original-page"
    runner.page_ids[decoy] = "native-decoy-page"
    original_answer = {
        "key": "one-use",
        "question": "email",
        "value": "old@example.invalid",
        "scope": {"application_id": app["id"]},
        "state": "confirmed",
    }

    def setup():
        page.set_content("""<title>Owned native original</title><form>
            <label>Email <input id="email" type="email" value="wrong" required></label>
            <label>CV <input id="resume" type="file"></label>
            <input type="password" value="never expose"><button>Submit</button></form>""")
        page.locator("#resume").set_input_files(
            {"name": "synthetic.pdf", "mimeType": "application/pdf", "buffer": b"synthetic-file"}
        )
        page.evaluate("""() => {
            window.originalFile=document.querySelector('#resume').files[0];
            window.events=[];window.mutations=[];
            for(const event of ['input','change','invalid','focus','submit'])
                document.addEventListener(event,()=>window.events.push(event),true);
            new MutationObserver(rows=>window.mutations.push(...rows.map(x=>x.type)))
                .observe(document,{subtree:true,childList:true,attributes:true,characterData:true});
            const native=Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').get;
            Object.defineProperty(document.querySelector('#email'),'value',{configurable:true,get(){
                window.events.push('page_value_getter');
                fetch('https://synthetic.invalid/forbidden',{method:'POST'});
                return native.call(this);
            }});
        }""")
        state = service.store.load()
        state["runtime"]["observed_at"] = time.time()
        job = state["jobs"][0]
        job.update(
            status="needs_recheck",
            reason="action_result_unknown",
            intent={
                "action": "fill",
                "attempt_id": "synthetic-unresolved",
                "run_id": run_id,
                "page_id": "native-original-page",
                "field_id": "email",
                "answer_ref": {
                    "key": "one-use",
                    "revision": digest(original_answer),
                    "fact": "email",
                },
            },
            page_observation={
                "run_id": run_id,
                "page_id": "native-original-page",
                "event": "observed",
                "at": time.time(),
            },
        )
        job.pop("owned_page_inspection", None)
        service.store.save(state)

    def capture(expected, case):
        state = service.store.load()
        state["runtime"]["observed_at"] = time.time()
        state["jobs"][0]["page_observation"]["at"] = time.time()
        service.store.save(state)
        before = deepcopy(state["jobs"][0])
        transports_before = deepcopy(runner.transports)
        binding = service.snapshot()["jobs"][0]["page_inspection_target"]
        service.request("observe-page", {"application_id": app["id"], "binding": binding})
        state = service.store.load()
        runner.commands(state)
        current = state["jobs"][0]
        receipt = current.pop("owned_page_inspection")
        save(root / ("observation-" + case + ".json"), receipt)
        before.pop("owned_page_inspection", None)
        assert receipt["status"] == expected, (case, receipt)
        failure_reasons = {
            "replaced-page": {"page_observation_owner_lost"},
            "closed-page": {"page_observation_owner_lost"},
            "transport-exit": {"page_observation_owner_lost"},
            "owner-binding": {"cua_owner_unknown"},
            "field-drift": {"page_observation_changed"},
            "document-drift": {"page_observation_changed", "page_observation_failed"},
        }
        if expected == "failed":
            assert receipt["reason"] in failure_reasons[case], (case, receipt)
        assert current == before and state["control"] == "paused"
        assert runner.transports == transports_before
        assert driver.client is original_client
        if expected == "failed":
            assert "data" not in receipt and "screenshot" not in receipt
        service.store.save(state)
        return receipt

    setup()
    positive = capture("captured", "positive")
    assert positive["binding"]["page_id"] == "native-original-page"
    assert positive["data"]["title"] == "Owned native original"
    fields = {field["id"]: field for field in positive["data"]["fields"] if field["id"]}
    assert fields["email"]["value"] == "wrong" and fields["email"]["valid"] is False
    assert fields["resume"]["files"] == [
        {"name": "synthetic.pdf", "size": 14, "type": "application/pdf"}
    ]
    assert "never expose" not in json.dumps(positive)
    assert page.evaluate("() => [window.events,window.mutations]") == [[], []]
    assert page.evaluate("window.originalFile===document.querySelector('#resume').files[0]")
    assert len(context.pages) == original_pages + 1
    before = service.store.path.read_bytes()
    wrong = dict(positive["binding"], page_id="native-decoy-page")
    try:
        service.request("observe-page", {"application_id": app["id"], "binding": wrong})
    except PortalDataError as error:
        assert error.code == "page_observation_unavailable"
    else:
        raise AssertionError("Decoy page binding was accepted")
    assert service.store.path.read_bytes() == before
    runner.pages[app["id"]] = decoy
    capture("failed", "replaced-page")
    runner.pages[app["id"]] = page
    original_window = driver.window_id
    try:
        driver.window_id = -1
        capture("failed", "owner-binding")
    finally:
        driver.window_id = original_window
    original_screenshot = page.screenshot
    for change in ("field", "document"):

        def interrupted(*, _change=change, **kwargs):
            screenshot = original_screenshot(**kwargs)
            if _change == "field":
                page.evaluate(
                    "Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')"
                    ".set.call(document.querySelector('#email'),'changed')"
                )
            else:
                page.set_content("<title>Replacement document</title>")
            return screenshot

        try:
            page.screenshot = interrupted
            capture("failed", change + "-drift")
        finally:
            page.screenshot = original_screenshot
        setup()
    # Close only a declared diagnostic case Page. Never replace a lost real Page.
    runner.pages[app["id"]] = decoy
    state = service.store.load()
    state["jobs"][0]["page_observation"]["page_id"] = "native-decoy-page"
    service.store.save(state)
    decoy.close()
    capture("failed", "closed-page")
    runner.pages[app["id"]] = page
    setup()
    # Actual browser requests, retained only in this fixed diagnostic checkpoint.
    # The first POST is denied; a later public GET must not release that stop.
    for source in ("telemetry", "autosave"):
        runner.blocked_pages.pop(page, None)
        setup()
        before = service.store.load()["jobs"][0]
        before_count = len(before["observations"])
        if source == "telemetry":
            page.evaluate("""async () => {
                await fetch('https://synthetic.invalid/telemetry',{
                    method:'POST',body:'synthetic body'}).catch(()=>{});
            }""")
            try:
                page.goto("https://synthetic.invalid/check")
            except Error as error:
                # Permitted does not mean delivered: offline mode blocks the read.
                assert "ERR_INTERNET_DISCONNECTED" in str(error)
        else:
            page.evaluate("""() => {
                const email=document.querySelector('#email');delete email.value;
                email.addEventListener('input',()=>{
                    window.autosave=fetch('https://synthetic.invalid/autosave',{
                        method:'POST',body:'synthetic body'}).catch(()=>{});
                });
            }""")
            page.locator("#email").fill("new@example.invalid")
            page.evaluate("async () => await window.autosave")
        try:
            runner.observe(page, before)
        except PortalDataError as error:
            assert error.code == "unverified_send_path"
        else:
            raise AssertionError("Unknown request did not stop readback")
        runner.persist(service.store.load())
        after = WorkerStore(service.store.applications, service.store.root, live=True).load()[
            "jobs"
        ][0]
        rows = after["observations"][before_count:]
        requests = [row for row in rows if row.get("action") == "request_diagnostic"]
        stopped = [row for row in rows if row.get("action") == "readback_diagnostic"]
        assert [row["method"] for row in requests] == (
            ["POST", "GET"] if source == "telemetry" else ["POST"]
        )
        assert [row["stage"] for row in requests] == (
            ["request_blocked", "request_permitted"]
            if source == "telemetry"
            else ["request_blocked"]
        )
        assert requests[0]["dispatch"] == "not_sent" and requests[0]["caused_stop"] is True
        if source == "telemetry":
            assert requests[1]["dispatch"] == "unknown"
            assert requests[0]["sequence"] < requests[1]["sequence"]
        else:
            assert page.locator("#email").input_value() == "new@example.invalid"
            assert page.evaluate("window.originalFile===document.querySelector('#resume').files[0]")
        assert stopped[0]["request_id"] == requests[0]["request_id"]
        assert all(row["intent"] == before["intent"] for row in requests + stopped)
        assert all(row["page_id"] == "native-original-page" for row in requests + stopped)
        assert all(row["run_id"] == run_id for row in requests + stopped)
        assert all(row["attempt_id"] == "synthetic-unresolved" for row in requests + stopped)
        assert all(row["field_id"] == "email" for row in requests + stopped)
        assert all(row["batch_id"] == runner.batch_id for row in requests + stopped)
        assert after["intent"] == before["intent"] and not runner.verified_intents(after)
        assert "synthetic body" not in json.dumps(rows)
        save(root / ("request-diagnostics-" + source + ".json"), rows)
        if source == "autosave":
            # A new local preference cannot settle the old input or prove remote save.
            runner.temporary[app["id"]] = {
                "email": {**original_answer, "value": "new@example.invalid"}
            }
            temporary_before = deepcopy(runner.temporary)
            library_before = deepcopy(service.store.library())
            inspection = capture("captured", "autosave-local-readback")
            email = next(field for field in inspection["data"]["fields"] if field["id"] == "email")
            assert email["value"] == "new@example.invalid" and email["valid"] is True
            assert email["value"] != original_answer["value"]
            assert inspection["data"]["remote_save_verified"] is False
            current = WorkerStore(service.store.applications, service.store.root, live=True).load()[
                "jobs"
            ][0]
            assert current["intent"] == before["intent"]
            assert current["intent"]["answer_ref"]["revision"] == digest(original_answer)
            assert current["answer_refs"] == before["answer_refs"]
            assert not current.get("action_resolutions") and not runner.verified_intents(current)
            assert runner.temporary == temporary_before
            assert service.store.library() == library_before
            assert runner.blocked_pages[page] == "unverified_send_path"
            assert page.evaluate("window.originalFile===document.querySelector('#resume').files[0]")
            save(
                root / "request-diagnostics-original-input-binding.json",
                {
                    "original_answer": original_answer,
                    "original_intent": current["intent"],
                    "visible_matches_original_input": False,
                    "visible_matches_new_preference": True,
                    "action_resolutions_created": False,
                    "original_intent_retained": True,
                    "remote_save_verified": False,
                },
            )
    # Reset only the deliberate synthetic stop before the unrelated transport case.
    runner.blocked_pages.pop(page, None)
    setup()
    # Stall the owned daemon only while closing its own MCP proxy, so the Page
    # stays live and the transport-exit guard is tested independently of Page loss.
    runtime = json.loads((root / "synthetic-worker/cua-runtime.json").read_text())
    daemon_pid = runtime["daemon_pid"]
    assert responsible(daemon_pid) == os.getppid()

    def daemon_generation():
        return subprocess.run(
            ["/bin/ps", "-p", str(daemon_pid), "-o", "lstart=,command="],
            capture_output=True,
            text=True,
            timeout=2,
            check=True,
        ).stdout

    generation = daemon_generation()
    assert "cua-driver" in generation and " serve " in generation
    try:
        os.kill(daemon_pid, signal.SIGSTOP)
        original_client.process.terminate()
        original_client.process.wait(timeout=3)
        assert not page.is_closed()
        capture("failed", "transport-exit")
    finally:
        assert daemon_generation() == generation and responsible(daemon_pid) == os.getppid()
        os.kill(daemon_pid, signal.SIGCONT)
    return {
        "native_owned_page_observation_matrix": True,
        "nonempty_file_and_unknown_intent_preserved": True,
        "page_events_and_mutations_during_observation": False,
        "wrong_binding_replaced_closed_and_drift_rejected": True,
        "actual_transport_exit_rejected_without_replacement": True,
        "actual_denied_post_later_get_and_readback_link_persisted": True,
    }


def save(path, value):
    with path.open("x") as stream:
        json.dump(value, stream, indent=2)
        stream.write("\n")


def responsible(pid):
    function = ctypes.CDLL(None).responsibility_get_pid_responsible_for_pid
    function.argtypes = [ctypes.c_int]
    function.restype = ctypes.c_int
    return function(pid)


def process_executable(pid):
    function = ctypes.CDLL("/usr/lib/libproc.dylib").proc_pidpath
    function.argtypes = [ctypes.c_int, ctypes.c_void_p, ctypes.c_uint32]
    function.restype = ctypes.c_int
    buffer = ctypes.create_string_buffer(4096)
    if function(pid, buffer, len(buffer)) <= 0:
        raise OSError("Native process executable unavailable.")
    return os.fsdecode(buffer.value)


def host_identity(resources, native_pid):
    """Derive the current responsible native host from OS paths, never a caller claim."""
    assert type(native_pid) is int and native_pid > 0
    assert os.getppid() == native_pid
    assert responsible(native_pid) == native_pid
    python_responsible = responsible(os.getpid())
    assert python_responsible == native_pid
    executable = Path(process_executable(native_pid))
    assert executable.is_absolute() and executable.resolve(strict=True) == executable
    assert executable.is_file()
    contents = executable.parent.parent
    assert executable.parent.name == "MacOS" and contents.name == "Contents"
    assert contents.parent.suffix == ".app" and resources == contents / "Resources"
    info_path = contents / "Info.plist"
    assert info_path.is_file() and not info_path.is_symlink()
    info = plistlib.loads(info_path.read_bytes())
    assert isinstance(info.get("CFBundleIdentifier"), str) and info["CFBundleIdentifier"]
    assert info["CFBundleExecutable"] == executable.name
    return {
        "native_pid": native_pid,
        "python_pid": os.getpid(),
        "python_responsible_pid": python_responsible,
        "bundle_id": info["CFBundleIdentifier"],
        "executable": str(executable),
    }


def verify_native_identity(resources, native):
    identity = host_identity(resources, native["pid"])
    assert type(native["responsible_pid"]) is int
    assert native["responsible_pid"] == identity["native_pid"]
    assert native["executable"] == identity["executable"]
    assert native["bundle_id"] == identity["bundle_id"]
    assert all(type(native[key]) is bool for key in ("active", "accessibility", "screen_recording"))
    assert type(native["windows"]) is int and native["windows"] >= 0
    return identity


def probe_host_permissions(resources, root, native, *, cancelled=None, register_process=None):
    """One separate read-only permission daemon; never the retained worker's client."""
    from career_evidence_graph import cua_driver as cua

    result = verify_native_identity(resources, native)
    started = time.monotonic()
    deadline = started + 10

    def remaining():
        now = time.monotonic()
        if cancelled is not None and cancelled.is_set() or not started <= now < deadline:
            raise TimeoutError("Permission check stopped or timed out.")
        return deadline - now

    remaining()
    driver = resources / "cua-driver/cua-driver"
    assert not driver.is_symlink()
    result["driver_sha256"] = hashlib.sha256(driver.read_bytes()).hexdigest()
    assert result["driver_sha256"] == cua._OWNED_DRIVER_SHA256
    assert "TS_CUA_DRIVER_BINARY" not in os.environ
    env = {
        **os.environ,
        "CUA_DRIVER_RS_HOME": str(root / "probe-home"),
        "CUA_DRIVER_RS_TELEMETRY_ENABLED": "0",
        "DO_NOT_TRACK": "1",
    }
    # This separate bounded daemon grants only two read-only tools. The
    # subsequent browser probe uses the unchanged production manager.
    with tempfile.TemporaryDirectory(prefix="ts-host-check-", dir="/private/tmp") as temporary:
        socket = str(Path(temporary) / "driver.sock")
        manifest = Path(temporary) / "scope.json"
        save(
            manifest,
            {
                "version": 3,
                "allow": {"tools": ["check_permissions", "end_session"]},
                "expires_after": "5m",
                "idle_timeout": "1m",
            },
        )
        with (root / "permission-mcp.log").open("x") as log:
            backend = subprocess.Popen(
                [
                    str(driver),
                    "serve",
                    "--embedded",
                    "--socket",
                    socket,
                    "--permission-mode",
                    "bounded",
                    "--capability-manifest",
                    str(manifest),
                    "--approve-capability-manifest",
                    "--no-overlay",
                    "--no-permissions-gate",
                    "--pid-file",
                    str(Path(temporary) / "driver.pid"),
                ],
                env=env,
                stdout=log,
                stderr=log,
            )
            client = None
            try:
                if register_process is not None:
                    register_process(backend)
                while not Path(socket).exists():
                    assert backend.poll() is None
                    time.sleep(min(0.05, remaining()))
                result["daemon_pid"] = backend.pid
                result["daemon_responsible_pid"] = responsible(backend.pid)
                assert result["daemon_responsible_pid"] == native["pid"]
                client = cua.CuaMcpClient(
                    [str(driver), "mcp", "--embedded", "--socket", socket],
                    log,
                    env=env,
                    timeout=remaining() / 3,
                )
                if register_process is not None:
                    register_process(client.process)
                result["proxy_pid"] = client.process.pid
                result["proxy_responsible_pid"] = responsible(client.process.pid)
                assert result["proxy_responsible_pid"] == native["pid"]
                client.timeout = remaining()
                permissions = client.call("check_permissions", {"prompt": False}, owner=True)
                remaining()
                result["permission_checked_at"] = time.time()
                save(root / "mcp-permissions.json", permissions)
                assert permissions["source"]["pid"] == backend.pid
                assert permissions["source"]["attribution"] == "host"
                assert permissions["direct_capture_status"] == "not_checked"
                assert all(
                    type(permissions[key]) is bool and permissions[key] == native[key]
                    for key in ("accessibility", "screen_recording")
                )
                result["native_and_embedded_permissions_match"] = True
            finally:
                try:
                    if client is not None:
                        client.timeout = min(client.timeout, 1)
                        client.close()
                        assert client.process.poll() is not None
                finally:
                    try:
                        subprocess.run(
                            [str(driver), "stop", "--socket", socket],
                            env=env,
                            stdout=log,
                            stderr=log,
                            timeout=2,
                            check=True,
                        )
                    finally:
                        try:
                            backend.wait(timeout=2)
                        except subprocess.TimeoutExpired:
                            backend.kill()
                            backend.wait(timeout=1)
    result.update(
        accessibility=native["accessibility"],
        screen_recording=native["screen_recording"],
        daemon_closed=True,
    )
    return result


def run(root, *, permission_only=False):
    resources = Path(__file__).resolve().parent
    sys.path.insert(0, str(resources / "system/src"))
    from career_evidence_graph import cua_driver as cua

    native = json.loads((root / "native-tcc.json").read_text())
    result = {
        "status": "failed",
        "native_pid": native["pid"],
        "python_pid": os.getpid(),
        "python_responsible_pid": responsible(os.getpid()),
        "real_ATS": 0,
        "uploads": 0,
        "submits": 0,
        "permission_prompts": 0,
    }
    try:
        # The legacy background diagnostic still requires its own zero-window host.
        assert type(native["windows"]) is int and native["windows"] == 0
        assert native["active"] is False
        result.update(probe_host_permissions(resources, root, native))
        if permission_only:
            result.update(
                mode="permission-only",
                status="passed"
                if native["accessibility"] and native["screen_recording"]
                else "permissions_required",
                accessibility=native["accessibility"],
                screen_recording=native["screen_recording"],
                browser_prepare_sent=False,
            )
            save(root / "background-result.json", result)
            print(json.dumps(result), flush=True)
            return 0
        from playwright.sync_api import sync_playwright

        worker = root / "synthetic-worker"
        worker.mkdir(mode=0o700)
        permitted = native["accessibility"] and native["screen_recording"]
        try:
            with (
                sync_playwright() as playwright,
                cua.managed_cua_browser(
                    playwright,
                    worker,
                    click_route="dom_event",
                    origins=["https://synthetic.invalid"],
                    synthetic_keychain=True,
                ) as (context, driver),
            ):
                assert permitted
                context.set_offline(True)

                def offline(route):
                    if (
                        route.request.url == "https://synthetic.invalid/check"
                        and route.request.method == "GET"
                    ):
                        route.fulfill(
                            status=200,
                            content_type="text/html",
                            body=(
                                "<title>Synthetic host check</title>"
                                '<input type="file"><button>Example</button>'
                            ),
                        )
                    else:
                        route.abort()

                context.route("**/*", offline)
                page = driver.new_page(context)
                page.goto("https://synthetic.invalid/check")
                attachment = root / "synthetic.txt"
                attachment.write_text("Synthetic diagnostic attachment\n")
                page.locator("input").set_input_files(str(attachment))
                page.evaluate("window.originalFile=document.querySelector('input').files[0]")
                target = context.new_cdp_session(page)
                identity = target.send("Target.getTargetInfo")["targetInfo"]["targetId"]
                target.detach()

                def pump():
                    page.wait_for_timeout(0)

                binding = driver._bind(page.url, pump)
                state = driver.client.call(
                    "get_browser_state", {**binding, "snapshot_format": "semantic_v2"}, pump=pump
                )
                assert state["snapshot"]["complete"]
                original = driver.client
                driver.ensure_scope(page.url, force=True)
                assert driver.client is original and not page.is_closed()
                assert page.evaluate(
                    "window.originalFile===document.querySelector('input').files[0]"
                )
                target = context.new_cdp_session(page)
                assert target.send("Target.getTargetInfo")["targetInfo"]["targetId"] == identity
                target.detach()
                result.update(original_page_and_attachment_preserved=True, scope_refreshed=True)
                result.update(observe_page_matrix(context, driver, page, root))
        except cua.PortalDataError as error:
            result["browser_error_code"] = error.code
            if permitted or error.code != "cua_permissions_required":
                raise
            assert not list((worker / "cua-profiles").glob("isolated-*"))
            result.update(status="permissions_required", browser_prepare_sent=False)
        else:
            result["status"] = "passed"
    except Exception as error:
        result.update(error=type(error).__name__, message=str(error), cause=repr(error.__cause__))
    save(root / "background-result.json", result)
    print(json.dumps(result), flush=True)
    return 0 if result["status"] in {"passed", "permissions_required"} else 1


if __name__ == "__main__":
    permission_only = len(sys.argv) == 3 and sys.argv[1] == "--permission-only"
    if not permission_only and len(sys.argv) != 2:
        raise SystemExit(2)
    destination = Path(sys.argv[-1])
    if (
        not destination.is_dir()
        or destination.is_symlink()
        or destination.stat().st_uid != os.getuid()
        or destination.stat().st_mode & 0o777 != 0o700
        or destination.absolute() != destination.resolve()
    ):
        print("private diagnostic directory required", file=sys.stderr)
        raise SystemExit(2)
    raise SystemExit(run(destination, permission_only=permission_only))
