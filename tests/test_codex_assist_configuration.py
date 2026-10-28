"""Metadata-only Codex configuration crosses the existing worker launcher."""

import json
import os
import runpy
import sys
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace

import pytest

from career_evidence_graph.application_worker import WorkerService
from career_evidence_graph.career_portal_data import ApplicationStore


def service(tmp_path, **kwargs):
    applications = tmp_path / "applications"
    applications.mkdir()
    return WorkerService(
        ApplicationStore(applications),
        tmp_path / "worker",
        fixture_origin="http://127.0.0.1:9999",
        **kwargs,
    )


def config(tmp_path):
    executable = tmp_path / "synthetic-codex"
    executable.write_text("#!/bin/sh\nexit 0\n")
    executable.chmod(0o700)
    (tmp_path / "synthetic-home").mkdir()
    return {
        "executable": str(executable),
        "runtime": str(tmp_path / "worker" / "codex-assist"),
        "home": str(tmp_path / "synthetic-home"),
    }


def test_launcher_passes_narrow_config_without_starting_codex(tmp_path, monkeypatch):
    supplied = config(tmp_path)
    worker = service(tmp_path, codex_assist_config=supplied)
    launched = []

    def spawn(args, **kwargs):
        launched.append((args, kwargs))
        return SimpleNamespace(pid=123456789, poll=lambda: None)

    monkeypatch.setattr("career_evidence_graph.application_worker.subprocess.Popen", spawn)
    worker.spawn()
    assert len(launched) == 1
    args, options = launched[0]
    payload = json.loads(args[args.index("--codex-assist-config") + 1])
    assert {key: payload[key] for key in supplied} == supplied
    assert options["start_new_session"] is True
    assert not options.get("shell", False)
    assert "--listen" not in args


@pytest.mark.parametrize("change", [{"token": "must-not-cross"}, {"extra_args": ["exec"]}])
def test_launcher_rejects_unknown_config_fields(tmp_path, change):
    with pytest.raises(ValueError):
        service(tmp_path, codex_assist_config={**config(tmp_path), **change})


def test_launcher_rejects_runtime_outside_its_worker(tmp_path):
    supplied = config(tmp_path)
    supplied["runtime"] = str(tmp_path / "different-worker")
    with pytest.raises(ValueError):
        service(tmp_path, codex_assist_config=supplied)


def test_existing_launcher_does_not_enable_assistance(tmp_path, monkeypatch):
    worker = service(tmp_path)
    launched = []
    monkeypatch.setattr(
        "career_evidence_graph.application_worker.subprocess.Popen",
        lambda args, **kwargs: launched.append(args) or SimpleNamespace(poll=lambda: None),
    )
    worker.spawn()
    assert "--codex-assist-config" not in launched[0]


def test_backend_reuses_selected_cli_for_metadata_only_configuration(tmp_path, monkeypatch):
    from test_macos_portal import synthetic_native_root

    root = synthetic_native_root(tmp_path)
    # The backend retains its selected CLI in the environment; restore it at teardown.
    monkeypatch.setenv("TOMORROWSTAR_CODEX_EXECUTABLE", str(root / "codex-fixture"))
    monkeypatch.setenv("HOME", str(tmp_path))
    # The backend publishes its dedicated Codex home in the environment; restore it at teardown.
    monkeypatch.setenv("TOMORROWSTAR_CODEX_HOME", "replaced-by-backend")
    backend = runpy.run_path(str(Path(__file__).parents[1] / "macos/server.py"))
    namespace = backend["main"].__globals__
    observed = {}

    def inspect_server(*args, **kwargs):
        observed.update(kwargs)
        return SimpleNamespace(
            server_port=12345, application_flow_service=object(), worker_service=object()
        )

    monkeypatch.setitem(namespace, "create_server", inspect_server)
    monkeypatch.setitem(
        namespace, "find_codex_executable", lambda configured: str(root / "codex-fixture")
    )
    monkeypatch.setitem(namespace, "serve_with_parent_pipe", lambda *args, **kwargs: None)
    signed_in = []
    monkeypatch.setitem(namespace, "require_codex_sign_in", lambda *args: signed_in.append(args))
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "server.py",
            "--applications",
            str(root / "applications"),
            "--career-workspace",
            str(root / "career"),
            "--single-job-flow",
            "--codex-assist",
        ],
    )
    assert backend["main"]() == 0
    supplied = observed["worker_codex_assist_config"]
    assert supplied["executable"] == str(root / "codex-fixture")
    # MC-21: a dedicated Codex home shared with model calls, never the user's own HOME.
    dedicated = tmp_path / "Library/Application Support/TomorrowStar/codex-home"
    assert supplied["home"] == str(dedicated) and dedicated.is_dir()
    assert os.environ["TOMORROWSTAR_CODEX_HOME"] == str(dedicated)
    assert signed_in == [(str(root / "codex-fixture"), dedicated)]
    assert supplied["runtime"] == str(observed["worker_root"] / "codex-assist")


def test_adapter_implementation_is_part_of_loaded_worker_identity(monkeypatch):
    from career_evidence_graph.application_codex_assist import CodexAdapter
    from career_evidence_graph.loaded_code import loaded_runtime_revision, measure_packaged_roles

    measure_packaged_roles()
    original = loaded_runtime_revision("worker")
    assert original is not None
    method = CodexAdapter.progress
    monkeypatch.setattr(
        method,
        "__code__",
        method.__code__.replace(co_consts=(*method.__code__.co_consts, "Synthetic adapter change")),
    )
    assert loaded_runtime_revision("worker") != original


def test_worker_constructs_and_closes_dormant_adapter_without_starting_it(tmp_path, monkeypatch):
    from career_evidence_graph import application_worker_browser as browser

    worker = service(tmp_path, codex_assist_config=config(tmp_path))
    events = []
    dormant = SimpleNamespace(closed=False)
    dormant.close = lambda: setattr(dormant, "closed", True)

    def adapter(supplied):
        assert supplied.runtime == worker.store.root / "codex-assist"
        events.append("constructed")
        return dormant

    class Runner:
        def __init__(self, *args, **kwargs):
            pass

        def tick(self):
            assert self.codex_assist is dormant
            raise KeyboardInterrupt

    @contextmanager
    def playwright():
        context = SimpleNamespace(pages=[], set_default_timeout=lambda timeout: None)
        yield SimpleNamespace(
            chromium=SimpleNamespace(launch_persistent_context=lambda *args, **kwargs: context)
        )

    monkeypatch.setattr(browser, "CodexAdapter", adapter, raising=False)
    monkeypatch.setattr(browser, "ApplicationRunner", Runner)
    monkeypatch.setattr(browser, "sync_playwright", playwright)
    result = browser.main(
        [
            "--applications",
            str(worker.store.applications.root),
            "--runtime",
            str(worker.store.root),
            "--fixture-origin",
            worker.fixture_origin,
            "--codex-assist-config",
            json.dumps(worker.codex_assist_config),
        ]
    )
    assert result == 2
    assert events == ["constructed"]
    assert dormant.closed is True


def test_assistance_rejects_a_home_with_personal_context(tmp_path):
    # MC-21: the takeover uses the same dedicated, context-free Codex home as model calls.
    from career_evidence_graph.application_codex_assist import CodexAssistConfig

    supplied = config(tmp_path)
    Path(supplied["runtime"]).mkdir(parents=True)
    assert CodexAssistConfig.from_dict(supplied).home == Path(supplied["home"]).resolve()
    with pytest.raises(ValueError):
        CodexAssistConfig.from_dict(supplied | {"home": str(Path.home())})
    (Path(supplied["home"]) / ".codex").mkdir()
    (Path(supplied["home"]) / ".codex/AGENTS.md").write_text("personal")
    with pytest.raises(ValueError):
        CodexAssistConfig.from_dict(supplied)


def test_assistance_disables_cross_run_memories():
    from career_evidence_graph.application_codex_assist import _DISABLED_FEATURES

    assert "memories" in _DISABLED_FEATURES


def test_backend_keeps_running_without_takeover_when_the_codex_home_is_rejected(
    tmp_path, monkeypatch
):
    from test_macos_portal import synthetic_native_root

    root = synthetic_native_root(tmp_path)
    monkeypatch.setenv("TOMORROWSTAR_CODEX_EXECUTABLE", str(root / "codex-fixture"))
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("TOMORROWSTAR_CODEX_HOME", "replaced-by-backend")
    dedicated = tmp_path / "Library/Application Support/TomorrowStar/codex-home"
    dedicated.mkdir(parents=True)
    (dedicated / "AGENTS.md").write_text("personal")
    backend = runpy.run_path(str(Path(__file__).parents[1] / "macos/server.py"))
    namespace = backend["main"].__globals__
    observed = {}

    def inspect_server(*args, **kwargs):
        observed.update(kwargs)
        return SimpleNamespace(
            server_port=12345, application_flow_service=object(), worker_service=object()
        )

    monkeypatch.setitem(namespace, "create_server", inspect_server)
    monkeypatch.setitem(
        namespace, "find_codex_executable", lambda configured: str(root / "codex-fixture")
    )
    monkeypatch.setitem(namespace, "serve_with_parent_pipe", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "server.py",
            "--applications",
            str(root / "applications"),
            "--career-workspace",
            str(root / "career"),
            "--single-job-flow",
            "--codex-assist",
        ],
    )
    # The takeover is unavailable, model calls stop on the same check; no fallback home.
    assert backend["main"]() == 0
    assert "worker_codex_assist_config" not in observed and "worker_root" in observed
    assert os.environ["TOMORROWSTAR_CODEX_HOME"] == str(dedicated)


def test_backend_does_not_configure_takeover_for_a_signed_out_codex_home(tmp_path, monkeypatch):
    from test_macos_portal import synthetic_native_root

    from career_evidence_graph.codex_cli import CodexCLIError

    root = synthetic_native_root(tmp_path)
    monkeypatch.setenv("TOMORROWSTAR_CODEX_EXECUTABLE", str(root / "codex-fixture"))
    monkeypatch.setenv("HOME", str(tmp_path))
    backend = runpy.run_path(str(Path(__file__).parents[1] / "macos/server.py"))
    namespace = backend["main"].__globals__
    observed = {}

    def inspect_server(*args, **kwargs):
        observed.update(kwargs)
        return SimpleNamespace(
            server_port=12345, application_flow_service=object(), worker_service=object()
        )

    def signed_out(*args):
        raise CodexCLIError("dedicated Codex home is not signed in")

    monkeypatch.setitem(namespace, "create_server", inspect_server)
    monkeypatch.setitem(
        namespace, "find_codex_executable", lambda configured: str(root / "codex-fixture")
    )
    monkeypatch.setitem(namespace, "serve_with_parent_pipe", lambda *args, **kwargs: None)
    monkeypatch.setitem(namespace, "require_codex_sign_in", signed_out)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "server.py",
            "--applications",
            str(root / "applications"),
            "--career-workspace",
            str(root / "career"),
            "--single-job-flow",
            "--codex-assist",
        ],
    )
    assert backend["main"]() == 0
    assert "worker_codex_assist_config" not in observed and "worker_root" in observed


def test_sign_in_check_names_the_actual_executable(tmp_path):
    from career_evidence_graph.codex_cli import CodexCLIError, require_codex_sign_in

    home = tmp_path / "codex-home"
    home.mkdir()
    executable = tmp_path / "bundled" / "codex"
    executable.parent.mkdir()
    executable.write_text("#!/bin/sh\necho 'Not logged in' >&2\nexit 1\n")
    executable.chmod(0o700)
    with pytest.raises(CodexCLIError, match="not signed in") as raised:
        require_codex_sign_in(str(executable), home)
    assert f"HOME='{home.resolve()}' '{executable}' login" in str(raised.value)
    assert "Not logged in" in raised.value.redacted_stderr
