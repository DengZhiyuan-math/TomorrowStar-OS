"""Metadata-only Codex configuration crosses the existing worker launcher."""

import json
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
    assert backend["main"]() == 0
    supplied = observed["worker_codex_assist_config"]
    assert supplied["executable"] == str(root / "codex-fixture")
    assert supplied["home"] == str(tmp_path)
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
