"""Synthetic native-proof faults can deny, never manufacture a host grant."""

import importlib.util
import json
import os
import sys
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

import pytest
from test_application_readiness import native_fixture

from career_evidence_graph.application_readiness import project_native_host


@pytest.fixture
def native_faults(monkeypatch):
    monkeypatch.setattr(sys, "path", sys.path.copy())
    source = Path(__file__).parents[1] / "macos/server.py"
    spec = importlib.util.spec_from_file_location("synthetic_native_fault_server", source)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    binding, actual = native_fixture()
    actual.update(session_open=True, instance_binding=deepcopy(binding), invalidation_epoch=0)
    return module, binding, actual


def test_synthetic_fault_denies_one_grant_without_mutating_actual_snapshot(tmp_path, native_faults):
    module, binding, actual = native_faults
    before = deepcopy(actual)
    (tmp_path / "native-proof-fault.json").write_text('{"fault":"accessibility"}')
    snapshot = module.synthetic_native_proof_snapshot(lambda: actual, tmp_path)
    denied = snapshot()
    assert denied["accessibility"] is False and denied["screen_recording"] is True
    assert project_native_host(denied, binding, 1001)["state"] == "blocked"
    assert actual == before


def test_write_locked_fault_waits_for_explicit_locked_snapshot(tmp_path, native_faults, capsys):
    module, _, actual = native_faults
    (tmp_path / "native-proof-fault.json").write_text(
        json.dumps(
            {"fault": "accessibility", "phase": "write-locked", "token": "synthetic-lock-token"}
        )
    )
    snapshot = module.synthetic_native_proof_snapshot(lambda: actual, tmp_path)
    assert snapshot() is actual and snapshot() is actual
    assert capsys.readouterr().out == ""
    assert snapshot.write_locked_snapshot()["accessibility"] is False
    event = json.loads(capsys.readouterr().out)
    assert event == {
        "event": "synthetic_native_proof_fault",
        "phase": "write-locked",
        "token": "synthetic-lock-token",
        "fault": "accessibility",
    }
    assert actual["accessibility"] is True


def test_prepare_does_not_read_native_fault_and_explicit_locked_diagnostic_still_runs(
    tmp_path, native_faults, monkeypatch, capsys
):
    from test_installed_write_admission_http import (
        business_bytes,
        installed_portal,
        post,
        prepare_payload,
    )

    module, _, _ = native_faults
    with installed_portal(tmp_path, monkeypatch) as (portal, task, options, starts):
        root = tmp_path / "fault-control"
        root.mkdir()
        (root / "native-proof-fault.json").write_text(
            json.dumps(
                {
                    "fault": "accessibility",
                    "phase": "write-locked",
                    "token": "actual-post-lock-token",
                }
            )
        )
        original = options["native_host_identity"]
        fault = module.synthetic_native_proof_snapshot(original, root)
        locked_reads = []

        def locked_read():
            assert portal.server.application_flow_service.applications._write_descriptor is not None
            locked_reads.append(True)
            return fault.write_locked_snapshot()

        monkeypatch.setattr(original, "write_locked_snapshot", locked_read, raising=False)
        status, result = post(portal, "prepare-worker", prepare_payload(task))
        assert status == 200 and result["status"] == "queued"
        state = portal.server.worker_service.store.load()
        assert state["control"] == "paused" and not state.get("runtime")
        assert state["jobs"][0]["application_id"] == task["application_id"]
        assert state["jobs"][0]["file_sha256"] == task["resume_sha256"]
        assert locked_reads == [] and starts == []
        before_diagnostic = business_bytes(portal)
        with portal.server.application_flow_service.applications.write_lock():
            assert original.write_locked_snapshot()["accessibility"] is False
        assert business_bytes(portal) == before_diagnostic
        assert locked_reads == [True]
        event = json.loads(capsys.readouterr().out)
        assert event["phase"] == "write-locked" and event["token"] == "actual-post-lock-token"


@pytest.mark.parametrize(
    "fault", ["screen_recording", "nonce", "responsibility", "stale", "unknown"]
)
def test_each_controlled_fault_denies_a_verified_baseline(tmp_path, native_faults, fault):
    module, binding, actual = native_faults
    before = deepcopy(actual)
    (tmp_path / "native-proof-fault.json").write_text(json.dumps({"fault": fault}))
    denied = module.synthetic_native_proof_snapshot(lambda: actual, tmp_path)()
    assert project_native_host(denied, binding, 1001)["state"] != "verified"
    assert actual == before


@pytest.mark.parametrize("fault", [None, "none"])
def test_absent_or_none_fault_returns_actual_snapshot_unchanged(tmp_path, native_faults, fault):
    module, _, actual = native_faults
    calls = []
    if fault is not None:
        (tmp_path / "native-proof-fault.json").write_text(json.dumps({"fault": fault}))
    snapshot = module.synthetic_native_proof_snapshot(
        lambda: (calls.append(True), actual)[1], tmp_path
    )
    assert snapshot() is actual and snapshot() is actual
    assert calls == [True, True]


@pytest.mark.parametrize(
    "fault",
    ["none", "accessibility", "screen_recording", "nonce", "responsibility", "stale", "unknown"],
)
@pytest.mark.parametrize("baseline", ["missing", "unknown", "missing_permission"])
def test_fault_cannot_promote_unknown_or_missing_real_grants(
    tmp_path, native_faults, fault, baseline
):
    module, binding, actual = native_faults
    if baseline == "missing":
        actual = None
    elif baseline == "unknown":
        actual.update(state="unknown", kind="sample", daemon=None)
    else:
        actual["accessibility"] = False
    before = deepcopy(actual)
    (tmp_path / "native-proof-fault.json").write_text(json.dumps({"fault": fault}))
    denied = module.synthetic_native_proof_snapshot(lambda: actual, tmp_path)()
    assert project_native_host(denied, binding, 1001)["state"] != "verified"
    assert actual == before
    if isinstance(actual, dict) and actual.get("accessibility") is False:
        assert denied["accessibility"] is False


def test_after_first_read_denies_later_reads_until_a_new_case_token(tmp_path, native_faults):
    module, binding, actual = native_faults
    path = tmp_path / "native-proof-fault.json"
    control = {"fault": "nonce", "phase": "after-first-read", "token": "case-1"}
    path.write_text(json.dumps(control))
    snapshot = module.synthetic_native_proof_snapshot(lambda: actual, tmp_path)
    assert snapshot() is actual
    assert project_native_host(snapshot(), binding, 1001)["state"] == "blocked"
    assert project_native_host(snapshot(), binding, 1001)["state"] == "blocked"
    path.write_text(json.dumps(control | {"token": "case-2"}))
    assert snapshot() is actual
    assert project_native_host(snapshot(), binding, 1001)["state"] == "blocked"
    path.unlink()
    assert snapshot() is actual


@pytest.mark.parametrize(
    "raw",
    [
        b"{",
        b"\xff",
        b"[]",
        b'{"fault":"grant"}',
        b'{"fault":"none","accessibility":true}',
        b'{"fault":"none","fault":"accessibility"}',
        b'{"fault":[]}',
        b'{"fault":"nonce","phase":"other"}',
        b'{"fault":"nonce","phase":"after-first-read"}',
        b'{"fault":"nonce","phase":"after-first-read","token":""}',
        b'{"fault":"nonce","token":42}',
        b'{"fault":"nonce","token":"/outside/path"}',
        b'{"fault":"none"}' + b" " * 4096,
    ],
)
def test_invalid_or_oversized_control_fails_closed(tmp_path, native_faults, raw):
    module, binding, actual = native_faults
    (tmp_path / "native-proof-fault.json").write_bytes(raw)
    denied = module.synthetic_native_proof_snapshot(lambda: actual, tmp_path)()
    assert denied is None
    assert project_native_host(denied, binding, 1001)["state"] == "unknown"


@pytest.mark.parametrize("kind", ["symlink", "dangling", "hardlink", "directory", "fifo"])
def test_linked_or_special_control_is_not_read(tmp_path, native_faults, kind):
    module, _, actual = native_faults
    path = tmp_path / "native-proof-fault.json"
    target = tmp_path / "outside.json"
    target.write_text('{"fault":"none"}')
    if kind == "symlink":
        path.symlink_to(target)
    elif kind == "dangling":
        path.symlink_to(tmp_path / "absent.json")
    elif kind == "hardlink":
        os.link(target, path)
    elif kind == "directory":
        path.mkdir()
    else:
        os.mkfifo(path)
    assert module.synthetic_native_proof_snapshot(lambda: actual, tmp_path)() is None


def test_control_changed_during_bounded_read_fails_closed(tmp_path, native_faults, monkeypatch):
    module, _, actual = native_faults
    path = tmp_path / "native-proof-fault.json"
    path.write_text('{"fault":"none"}')
    read = os.read

    def concurrent_write(descriptor, limit):
        result = read(descriptor, limit)
        path.write_text('{"fault":"none"} ')
        return result

    monkeypatch.setattr(module.os, "read", concurrent_write)
    assert module.synthetic_native_proof_snapshot(lambda: actual, tmp_path)() is None


@pytest.mark.parametrize(
    "mode",
    [
        "ordinary",
        "--single-job-flow",
        "--synthetic-flow",
        "--synthetic-preparation",
        "--synthetic-browser",
    ],
)
def test_only_explicit_browser_mode_wraps_native_snapshot(
    tmp_path, native_faults, monkeypatch, mode
):
    module, _, actual = native_faults
    calls, options = [], []

    def actual_snapshot():
        return actual

    def wrapped_snapshot():
        return None

    class StopBeforeServing(RuntimeError):
        pass

    def create(*_args, **kwargs):
        options.append(kwargs)
        raise StopBeforeServing

    def wrap(snapshot, root, *, record_event):
        assert callable(record_event)
        calls.append((snapshot, root))
        return wrapped_snapshot

    monkeypatch.setattr(module.os, "environ", dict(os.environ))
    monkeypatch.setattr(module, "find_codex_executable", lambda *_args: None)
    monkeypatch.setattr(
        module,
        "synthetic_workspace",
        lambda *_args, **_kwargs: {
            "applications": str(tmp_path / "applications"),
            "career_workspace": str(tmp_path / "career"),
        },
    )
    monkeypatch.setattr(
        module,
        "NativeHostBridge",
        lambda *_args: SimpleNamespace(binding={}, snapshot=actual_snapshot),
    )
    monkeypatch.setattr(module, "synthetic_native_proof_snapshot", wrap)
    monkeypatch.setattr(module, "create_server", create)
    arguments = (
        [mode, str(tmp_path)]
        if mode.startswith("--synthetic-")
        else [
            "--applications",
            str(tmp_path / "applications"),
            "--career-workspace",
            str(tmp_path / "career"),
        ]
        + ([] if mode == "ordinary" else [mode])
    )
    monkeypatch.setattr(sys, "argv", ["server.py", *arguments])
    with pytest.raises(StopBeforeServing):
        module.main()
    if mode == "--synthetic-browser":
        assert calls == [(actual_snapshot, tmp_path)]
        assert options[0]["native_host_identity"] is wrapped_snapshot
    else:
        assert calls == []
        assert options[0]["native_host_identity"] is actual_snapshot


def test_explicit_locked_fault_is_durable_and_prepare_does_not_log_a_native_diagnostic(
    tmp_path, native_faults, monkeypatch, capsys
):
    from test_installed_write_admission_http import (
        business_bytes,
        installed_portal,
        post,
        prepare_payload,
    )

    module, _, _ = native_faults
    with installed_portal(tmp_path, monkeypatch) as (portal, task, options, starts):
        root = tmp_path / "fault-control"
        root.mkdir()
        diagnostics = root / "runtime/diagnostics"
        record = module.backend_exit_recorder(diagnostics)
        (root / "native-proof-fault.json").write_text(
            json.dumps({"fault": "accessibility", "phase": "write-locked", "token": "durable-lock"})
        )
        original = options["native_host_identity"]

        def record_locked(event, **details):
            assert portal.server.application_flow_service.applications._write_descriptor is not None
            record(event, **details)

        fault = module.synthetic_native_proof_snapshot(original, root, record_event=record_locked)
        monkeypatch.setattr(
            original, "write_locked_snapshot", fault.write_locked_snapshot, raising=False
        )
        status, _, _ = portal.request("GET", "/api/flow/readiness/" + task["id"])
        assert status == 200 and fault()["accessibility"] is True
        logs = list(diagnostics.glob("backend-exit-*.jsonl"))
        assert len(logs) == 1 and logs[0].read_bytes() == b""
        status, result = post(portal, "prepare-worker", prepare_payload(task))
        assert status == 200 and result["status"] == "queued"
        state = portal.server.worker_service.store.load()
        assert state["control"] == "paused" and not state.get("runtime")
        assert state["jobs"][0]["application_id"] == task["application_id"]
        assert state["jobs"][0]["file_sha256"] == task["resume_sha256"]
        assert logs[0].read_bytes() == b"" and starts == []
        before_diagnostic = business_bytes(portal)
        with portal.server.application_flow_service.applications.write_lock():
            assert original.write_locked_snapshot()["accessibility"] is False
        assert business_bytes(portal) == before_diagnostic
        # Reopen independently after the explicit diagnostic; stdout is not evidence.
        with logs[0].open() as saved:
            events = [json.loads(line) for line in saved]
        assert len(events) == 1
        event = events[0]
        assert {key: event[key] for key in ("event", "phase", "token", "fault")} == {
            "event": "synthetic_native_proof_fault",
            "phase": "write-locked",
            "token": "durable-lock",
            "fault": "accessibility",
        }
        assert event["pid"] == os.getpid() and event["ppid"] == os.getppid()
        assert event["utc"].endswith("+00:00")
        assert logs[0].stat().st_mode & 0o777 == 0o600
        assert diagnostics.stat().st_mode & 0o777 == 0o700
        assert capsys.readouterr().out == ""


def test_failed_explicit_locked_diagnostic_keeps_the_prepared_business_state(
    tmp_path, native_faults, monkeypatch
):
    from test_installed_write_admission_http import (
        business_bytes,
        installed_portal,
        post,
        prepare_payload,
    )

    module, _, _ = native_faults
    with installed_portal(tmp_path, monkeypatch) as (portal, task, options, starts):
        root = tmp_path / "fault-control"
        root.mkdir()
        (root / "native-proof-fault.json").write_text(
            json.dumps({"fault": "accessibility", "phase": "write-locked", "token": "failed-log"})
        )
        original = options["native_host_identity"]
        reached = []

        def unavailable_event(*_args, **_kwargs):
            assert portal.server.application_flow_service.applications._write_descriptor is not None
            reached.append(True)
            raise OSError("Synthetic diagnostic sink unavailable")

        fault = module.synthetic_native_proof_snapshot(
            original, root, record_event=unavailable_event
        )
        monkeypatch.setattr(
            original, "write_locked_snapshot", fault.write_locked_snapshot, raising=False
        )
        status, result = post(portal, "prepare-worker", prepare_payload(task))
        assert status == 200 and result["status"] == "queued"
        state = portal.server.worker_service.store.load()
        assert state["control"] == "paused" and not state.get("runtime")
        assert state["jobs"][0]["application_id"] == task["application_id"]
        assert state["jobs"][0]["file_sha256"] == task["resume_sha256"]
        assert reached == [] and starts == []
        before_diagnostic = business_bytes(portal)
        with (
            portal.server.application_flow_service.applications.write_lock(),
            pytest.raises(OSError, match="Synthetic diagnostic sink unavailable"),
        ):
            original.write_locked_snapshot()
        assert reached == [True] and business_bytes(portal) == before_diagnostic
        assert starts == []
        assert original.receipt["accessibility"] is True
