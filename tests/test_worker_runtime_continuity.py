"""Checkpoint durability and healthy runtime continuity with synthetic stores."""

import logging
import signal
import time
from contextlib import contextmanager
from copy import deepcopy
from types import SimpleNamespace

import pytest
from test_application_worker import job
from test_application_worker import service as _service

from career_evidence_graph._vendor import job_apply_store as helper
from career_evidence_graph.application_worker_browser import ApplicationRunner

service = _service


@pytest.mark.parametrize("failure", [OSError, ValueError, TypeError, RuntimeError])
def test_measurement_failure_keeps_saved_checkpoint_and_worker_available(
    service, monkeypatch, caplog, failure
):
    state = service.store.load()
    state["worker_error"] = "synthetic-checkpoint"

    def fail(_state):
        raise failure("synthetic measurement failure")

    monkeypatch.setattr(service.store.measurements, "track", fail)
    with caplog.at_level(logging.WARNING):
        service.store.save(state)

    assert service.store.load()["worker_error"] == "synthetic-checkpoint"
    assert service.store.stop_reason() == ""
    assert not service.store.stop_path.exists()
    assert "worker_measurement_unavailable" in caplog.text


@pytest.mark.parametrize("failure", [OSError, ValueError, TypeError])
def test_checkpoint_failure_stops_worker_and_preserves_old_checkpoint(
    service, monkeypatch, failure
):
    state = service.store.load()
    service.store.save(state)
    before = service.store.path.read_bytes()
    original = helper.atomic_write_json

    def fail(path, value):
        if path == service.store.path:
            raise failure("synthetic checkpoint failure")
        return original(path, value)

    monkeypatch.setattr(helper, "atomic_write_json", fail)
    state["worker_error"] = "must-not-replace-checkpoint"
    with pytest.raises(failure):
        service.store.save(state)

    assert service.store.path.read_bytes() == before
    assert service.store.stop_reason() == "checkpoint_unavailable"
    assert service.store.stop_path.exists()


@pytest.mark.parametrize("heartbeat_age", [86400, -10])
def test_tick_keeps_running_without_ui_heartbeat_and_retains_unresolved_intent(
    service, heartbeat_age
):
    service.request("prepare", {"jobs": [job(service)]})
    service.request("resume", {"controller": "synthetic-controller"})
    state = service.store.load()
    intent = {"action": "upload", "attempt_id": "synthetic-unknown-upload"}
    state["jobs"][0].update(status="needs_recheck", reason="action_result_unknown", intent=intent)
    state["heartbeat_at"] = time.time() - heartbeat_age
    service.store.save(state)
    before = deepcopy(state["jobs"])

    ApplicationRunner(service.store, None, service.fixture_origin).tick()

    result = service.store.load()
    assert result["control"] == "running"
    assert result["worker_error"] == ""
    assert result["jobs"] == before
    assert result["commands"] == []


@pytest.mark.parametrize("explicit_resources", [False, True])
def test_installed_layout_worker_starts_without_cli_package_proofs(
    service, monkeypatch, tmp_path, explicit_resources
):
    from career_evidence_graph import application_worker_browser as browser

    resources = tmp_path / "Contents/Resources"
    runtime_root = tmp_path / "installed-runtime"
    installed_source = resources / "system/src/career_evidence_graph/application_worker_browser.py"
    monkeypatch.setattr(browser, "__file__", str(installed_source))
    monkeypatch.setattr(browser, "loaded_runtime_revision", lambda _role: "synthetic-loaded-worker")
    events = []
    context = SimpleNamespace(pages=[], set_default_timeout=lambda value: events.append(value))

    @contextmanager
    def playwright():
        yield SimpleNamespace()

    @contextmanager
    def session(_playwright, runtime, **kwargs):
        assert runtime == runtime_root
        assert kwargs["click_route"] == "trusted"
        events.append("session")
        yield context, SimpleNamespace()

    class Runner:
        def __init__(self, store, received_context, origin, *, cua):
            assert received_context is context
            assert origin == "" and cua is not None
            self.store = store
            events.append("runner")

        def tick(self):
            assert (
                self.store.load()["runtime"]["loaded_engine_revision"] == "synthetic-loaded-worker"
            )
            events.append("tick")
            signal.getsignal(signal.SIGTERM)(signal.SIGTERM, None)

        def event(self, kind):
            events.append(kind)

        def pump(self):
            events.append("pump")

    monkeypatch.setattr(browser, "sync_playwright", playwright)
    monkeypatch.setattr(browser, "managed_cua_browser", session)
    monkeypatch.setattr(browser, "ApplicationRunner", Runner)
    arguments = [
        "--applications",
        str(service.store.applications.root),
        "--runtime",
        str(runtime_root),
        "--live",
        "--cua",
    ]
    if explicit_resources:
        arguments += ["--package-resources", str(resources)]

    assert browser.main(arguments) is None
    assert events == ["session", 4000, "runner", "tick", "worker_stopped", "pump"]
    result = browser.WorkerStore(service.store.applications, runtime_root, live=True).load()
    assert result["worker_error"] == "worker_stopped"
    assert result["control"] == "paused"
    assert "current_build" not in result["runtime"]


@pytest.mark.parametrize("driver_dead", [False, True])
def test_sigterm_leaves_a_sync_call_spinning_on_a_dead_driver(
    service, monkeypatch, tmp_path, driver_dead
):
    """A dead Playwright driver never returns from a sync call; SIGTERM must still stop."""
    from career_evidence_graph import application_worker_browser as browser

    runtime_root = tmp_path / "runtime"
    fiber = SimpleNamespace(dead=False)
    context = SimpleNamespace(
        pages=[], set_default_timeout=lambda _value: None, _dispatcher_fiber=fiber
    )

    @contextmanager
    def playwright():
        yield SimpleNamespace()

    @contextmanager
    def session(_playwright, _runtime, **_kwargs):
        yield context, SimpleNamespace()

    class Runner:
        def __init__(self, store, received_context, origin, *, cua):
            self.context = received_context

        def tick(self):
            pass

        def event(self, kind):
            pass

        def pump(self):
            # The driver exits while this call waits; the call itself never returns.
            fiber.dead = driver_dead
            signal.getsignal(signal.SIGTERM)(signal.SIGTERM, None)

    monkeypatch.setattr(browser, "sync_playwright", playwright)
    monkeypatch.setattr(browser, "managed_cua_browser", session)
    monkeypatch.setattr(browser, "ApplicationRunner", Runner)
    monkeypatch.setattr(browser, "sync_login_state", lambda _root, _context, seen: seen)
    arguments = [
        "--applications",
        str(service.store.applications.root),
        "--runtime",
        str(runtime_root),
        "--live",
        "--cua",
    ]

    assert browser.main(arguments) == (2 if driver_dead else None)
    result = browser.WorkerStore(service.store.applications, runtime_root, live=True).load()
    assert result["control"] == "paused"
    assert result["worker_error"] == ("KeyboardInterrupt" if driver_dead else "worker_stopped")
