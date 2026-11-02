"""Run the bundled portal until its native parent closes the control pipe."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
import os
import re
import shutil
import signal
import stat
import subprocess
import sys
import tempfile
import threading
import time
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

# The installed App and the checkout use the same public engine.
root = Path(__file__).resolve().parent
system = root / "system" if (root / "system").is_dir() else root.parent
sys.path.insert(0, str(system / "src"))

from career_evidence_graph.application_pdf import NativePDFInspector  # noqa: E402
from career_evidence_graph.career_portal import create_server  # noqa: E402
from career_evidence_graph.career_portal_data import PortalDataError  # noqa: E402
from career_evidence_graph.codex_cli import (  # noqa: E402
    CODEX_HOME_ENVIRONMENT,
    CodexCLIError,
    require_codex_sign_in,
    validate_codex_executable,
    validate_codex_home,
)
from career_evidence_graph.cua_driver import reviewed_native_assistance_policy  # noqa: E402


def native_permission_tools(resources):
    spec = importlib.util.spec_from_file_location(
        "tomorrowstar_native_permissions", resources / "background_check.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class NativeHostBridge:
    """Current parent-pipe receipts only; the Web receives a pure memory snapshot."""

    def __init__(self, resources, diagnostics, nonce, *, native_pid=None, backend_pid=None):
        self.resources, self.diagnostics = Path(resources), Path(diagnostics)
        self._lock = threading.RLock()
        self._binding = None
        self._sequence = 0
        self._invalidation_epoch = 0
        self._closed = False
        self._checking = False
        self._cancelled = threading.Event()
        self._processes = []
        self._value = {
            "protocol": "current-native-host/v1",
            "scope": "current_instance",
            "state": "unknown",
            "reason": "no_current_native_host_receipt",
            "responsibility_chain": "unknown",
            "daemon": None,
        }
        if not isinstance(nonce, str) or re.fullmatch("[a-f0-9]{32}", nonce) is None:
            return
        try:
            self._tools = native_permission_tools(self.resources)
            native_pid = os.getppid() if native_pid is None else native_pid
            backend_pid = os.getpid() if backend_pid is None else backend_pid
            identity = self._tools.host_identity(self.resources, native_pid)
            assert identity["native_pid"] == native_pid
            assert identity["python_pid"] == backend_pid
            assert identity["python_responsible_pid"] == native_pid
            self._binding = {
                "launch_nonce": nonce,
                "native_pid": native_pid,
                "backend_pid": backend_pid,
                "bundle_id": identity["bundle_id"],
                "executable": identity["executable"],
            }
        except Exception:
            self._value["reason"] = "native_identity_unverified"

    @property
    def binding(self):
        return deepcopy(self._binding)

    def snapshot(self):
        with self._lock:
            result = deepcopy(self._value)
            result["session_open"] = not self._closed
            result["instance_binding"] = deepcopy(self._binding)
            result["invalidation_epoch"] = self._invalidation_epoch
        captured = result.get("captured_at")
        if (
            result.get("state") == "verified"
            and captured is not None
            and not 0 <= time.time() - captured < 30
        ):
            result.update(state="unknown", reason="native_receipt_stale")
        return result

    def receive(self, raw):
        if self._binding is None:
            return
        with self._lock:
            if self._closed:
                return
            try:
                assert len(raw) <= 4096
                frame = json.loads(raw)
                assert set(frame) == {
                    "protocol",
                    "scope",
                    "kind",
                    "sequence",
                    "captured_at",
                    "native_responsible_pid",
                    "accessibility",
                    "screen_recording",
                    "active",
                    "windows",
                    *self._binding,
                }
                assert frame["protocol"] == "current-native-host/v1"
                assert frame["scope"] == "current_instance"
                assert frame["kind"] in {"sample", "check"}
                if any(frame[key] != value for key, value in self._binding.items()):
                    self._invalidation_epoch += 1
                    self._value.update(state="blocked", reason="native_instance_mismatch")
                    return
                assert type(frame["sequence"]) is int and frame["sequence"] > self._sequence
                captured = frame["captured_at"]
                assert type(captured) in {int, float} and math.isfinite(captured)
                if not 0 <= time.time() - captured < 30:
                    self._invalidation_epoch += 1
                    # A stale incoming frame is invalid, not natural ageing of
                    # an already verified receipt. Keep a known block intact.
                    if self._value.get("state") != "blocked":
                        self._value.update(state="unknown", reason="native_receipt_invalid")
                    return
                assert type(frame["native_responsible_pid"]) is int
                assert type(frame["windows"]) is int and frame["windows"] >= 0
                assert all(
                    type(frame[key]) is bool
                    for key in ("active", "accessibility", "screen_recording")
                )
                native = {
                    "pid": frame["native_pid"],
                    "responsible_pid": frame["native_responsible_pid"],
                    **{
                        key: frame[key]
                        for key in (
                            "bundle_id",
                            "executable",
                            "active",
                            "windows",
                            "accessibility",
                            "screen_recording",
                        )
                    },
                }
                try:
                    identity = self._tools.verify_native_identity(self.resources, native)
                    assert identity["native_pid"] == self._binding["native_pid"]
                    assert identity["python_pid"] == self._binding["backend_pid"]
                    assert identity["python_responsible_pid"] == self._binding["native_pid"]
                except AssertionError:
                    self._invalidation_epoch += 1
                    self._value.update(state="blocked", reason="responsibility_chain_mismatch")
                    return
            except Exception:
                self._invalidation_epoch += 1
                self._value.update(state="unknown", reason="native_receipt_invalid")
                return
            if self._checking:
                # A newer missing grant must stop a positive in-flight result.
                if not frame["accessibility"] or not frame["screen_recording"]:
                    self._invalidation_epoch += 1
                    self._sequence = frame["sequence"]
                    self._value.update(
                        state="blocked",
                        reason="permissions_required",
                        accessibility=frame["accessibility"],
                        screen_recording=frame["screen_recording"],
                    )
                return
            # A new sample/check replaces the old permission conclusion; a
            # successful result may authorize a new grant, never revive an old one.
            self._invalidation_epoch += 1
            self._sequence = frame["sequence"]
            permitted = frame["accessibility"] and frame["screen_recording"]
            self._value = {
                "protocol": frame["protocol"],
                "scope": frame["scope"],
                "kind": frame["kind"],
                **self._binding,
                "captured_at": captured,
                "accessibility": frame["accessibility"],
                "screen_recording": frame["screen_recording"],
                "responsibility_chain": "python_verified",
                "daemon": None,
                "state": "unknown" if permitted else "blocked",
                "reason": "permission_check_required" if permitted else "permissions_required",
            }
            if frame["kind"] == "check":
                self._checking = True
                self._value.update(state="unknown", reason="permission_check_in_progress")
                threading.Thread(
                    target=self._check, args=(native, frame["sequence"]), daemon=True
                ).start()

    def _register_process(self, process):
        with self._lock:
            if not self._closed:
                self._processes.append(process)
                return
        if process.poll() is None:
            process.kill()
        raise TimeoutError("Native host closed.")

    def _check(self, native, sequence):
        try:
            directory = self.diagnostics
            assert not any(path.is_symlink() for path in (directory, *directory.parents))
            directory.mkdir(mode=0o700, parents=True, exist_ok=True)
            info = directory.stat()
            assert info.st_uid == os.getuid() and stat.S_IMODE(info.st_mode) == 0o700
            output = Path(tempfile.mkdtemp(prefix="native-host-check-", dir=directory))
            result = self._tools.probe_host_permissions(
                self.resources,
                output,
                native,
                cancelled=self._cancelled,
                register_process=self._register_process,
            )
            assert result["native_pid"] == self._binding["native_pid"]
            assert result["python_pid"] == self._binding["backend_pid"]
            assert result["python_responsible_pid"] == self._binding["native_pid"]
            assert result["daemon_responsible_pid"] == self._binding["native_pid"]
            assert result["proxy_responsible_pid"] == self._binding["native_pid"]
            assert result["native_and_embedded_permissions_match"] is True
            assert result["daemon_closed"] is True
            assert all(
                type(result[key]) is bool and result[key] == native[key]
                for key in ("accessibility", "screen_recording")
            )
            assert type(result["daemon_pid"]) is int and result["daemon_pid"] > 0
            assert type(result["proxy_pid"]) is int and result["proxy_pid"] > 0
            checked_at = result["permission_checked_at"]
            assert type(checked_at) in {int, float} and math.isfinite(checked_at)
            assert 0 <= time.time() - checked_at < 30
            permitted = result["accessibility"] and result["screen_recording"]
            update = {
                "state": "verified" if permitted else "blocked",
                "reason": "permissions_verified" if permitted else "permissions_required",
                "responsibility_chain": "verified",
                "daemon": {
                    "pid": result["daemon_pid"],
                    "responsible_pid": result["daemon_responsible_pid"],
                    "proxy_pid": result["proxy_pid"],
                    "proxy_responsible_pid": result["proxy_responsible_pid"],
                    "checked_at": checked_at,
                    "prompt": False,
                    "closed": True,
                },
            }
        except TimeoutError:
            update = {"state": "unknown", "reason": "permission_probe_timeout"}
        except AssertionError:
            update = {"state": "blocked", "reason": "permission_probe_rejected"}
        except Exception:
            update = {"state": "unknown", "reason": "permission_probe_failed"}
        with self._lock:
            self._checking = False
            self._processes.clear()
            if (
                not self._closed
                and sequence == self._sequence
                and self._value.get("reason") == "permission_check_in_progress"
            ):
                if update["state"] != "verified":
                    self._invalidation_epoch += 1
                self._value.update(update)

    def close(self):
        with self._lock:
            if self._closed:
                return
            self._closed = True
            self._invalidation_epoch += 1
            self._cancelled.set()
            self._value.update(state="unknown", reason="backend_closed")
            processes = self._processes[:]
            self._processes.clear()
        for process in processes:
            try:
                if process.poll() is None:
                    process.kill()
            except OSError:
                pass


def backend_exit_recorder(diagnostics):
    """Retain fixed lifecycle or synthetic-test metadata in the private diagnostic log."""
    log_path = None
    try:
        directory = Path(diagnostics)
        if any(path.is_symlink() for path in (directory, *directory.parents)):
            raise OSError("linked diagnostic directory")
        directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        info = directory.stat()
        if info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o700:
            raise OSError("private diagnostic directory required")
        log_path = directory / f"backend-exit-{os.getpid()}-{uuid4().hex}.jsonl"
        descriptor = os.open(log_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        os.close(descriptor)
    except OSError:
        log_path = None

    def record(event, *, reason=None, received_signal=None, phase=None, token=None, fault=None):
        if log_path is None:
            return
        row = {
            "utc": datetime.now(UTC).isoformat(),
            "pid": os.getpid(),
            "ppid": os.getppid(),
            "event": event,
        }
        if reason is not None:
            row["reason"] = reason
        if received_signal is not None:
            row["signal"] = received_signal
        if event == "synthetic_native_proof_fault":
            row.update(phase=phase, token=token, fault=fault)
        try:
            descriptor = os.open(log_path, os.O_APPEND | os.O_WRONLY | os.O_NOFOLLOW)
            try:
                os.write(descriptor, (json.dumps(row) + "\n").encode())
            finally:
                os.close(descriptor)
        except OSError:
            pass

    return record


WORKER_STOP_SECONDS = 10


def serve_with_parent_pipe(server, diagnostics, ready, *, native_bridge=None, record_event=None):
    """Keep the existing EOF shutdown contract and retain only its causal metadata."""
    record = record_event if record_event is not None else backend_exit_recorder(diagnostics)
    shutdown_reason = None
    shutdown_lock = threading.RLock()
    worker = getattr(server, "worker_service", None)
    # The worker leads its own session, so it must be stopped explicitly with the backend.
    worker_stop = threading.Thread(
        target=lambda: worker.stop_process(record, timeout=WORKER_STOP_SECONDS), daemon=True
    )

    def stop_worker():
        with shutdown_lock:
            if worker is not None and worker_stop.ident is None:
                worker_stop.start()

    def stop(reason, received_signal=None):
        nonlocal shutdown_reason
        if native_bridge is not None:
            native_bridge.close()
        if received_signal is not None:
            record("signal_received", received_signal=received_signal)
        with shutdown_lock:
            if shutdown_reason is None:
                shutdown_reason = reason
                record("backend_shutdown_requested", reason=reason)
                stop_worker()
                # HTTPServer.shutdown must run outside the serve_forever thread.
                threading.Thread(target=server.shutdown, daemon=True).start()

    def watch_parent():
        # Read raw bytes; a blocked buffered reader can abort Python finalization.
        stream = getattr(sys.stdin.buffer, "raw", sys.stdin.buffer)
        pending = bytearray()
        oversized = False
        try:
            while chunk := stream.read(1):
                if native_bridge is None:
                    continue
                if chunk == b"\n":
                    if not oversized and pending:
                        native_bridge.receive(bytes(pending))
                    pending.clear()
                    oversized = False
                elif not oversized:
                    if len(pending) < 4096:
                        pending.extend(chunk)
                    else:
                        pending.clear()
                        oversized = True
                        native_bridge.receive(b"")
        except OSError:
            stop("parent_pipe_error")
        else:
            record("parent_pipe_eof")
            stop("parent_pipe_eof")

    signal.signal(signal.SIGTERM, lambda number, frame: stop("signal", number))
    signal.signal(signal.SIGINT, lambda number, frame: stop("signal", number))
    record("backend_started")
    threading.Thread(target=watch_parent, daemon=True).start()
    completed = False
    try:
        with server:
            print(json.dumps(ready), flush=True)
            server.serve_forever(poll_interval=0.1)
        completed = True
    except BaseException:
        record("backend_exception", reason="server_exception")
        raise
    finally:
        if native_bridge is not None:
            native_bridge.close()
        stop_worker()
        if worker is not None:
            worker_stop.join(WORKER_STOP_SECONDS + 10)
        record(
            "backend_shutdown_complete" if completed else "backend_shutdown_failed",
            reason=shutdown_reason or "serve_returned",
        )


def find_codex_executable(configured: Path | None = None) -> str | None:
    selected = configured or os.environ.get("TOMORROWSTAR_CODEX_EXECUTABLE")
    if selected is not None:
        return validate_codex_executable(selected)
    candidates = [shutil.which("codex")]
    for applications in (Path.home() / "Applications", Path("/Applications")):
        candidates.extend(
            [
                applications
                / "ChatGPT.app/Contents/Resources/codex-cli/CodexCLI.app/Contents/MacOS/codex",
                applications / "Codex.app/Contents/Resources/codex",
            ]
        )
    for candidate in candidates:
        if candidate:
            try:
                return validate_codex_executable(candidate)
            except CodexCLIError:
                continue
    return None


def synthetic_workspace(
    path: Path, *, preparation: bool = False, browser: bool = False, mail: bool = False
) -> dict:
    """Read the fixed diagnostic contract before creating any runtime state."""
    if browser:
        from career_evidence_graph.application_worker_fixtures import browser_fixture_configuration

        return browser_fixture_configuration(path)
    if not path.is_absolute() or path.resolve(strict=True) != path or not path.is_dir():
        raise ValueError("synthetic-root")
    for name in ("applications", "career", "runtime", "home", "tmp") + (
        ("information-library", "latex-base")
        if mail
        else ("information-library",)
        if preparation
        else ()
    ):
        directory = path / name
        if directory.is_symlink() or not directory.is_dir():
            raise ValueError("synthetic-directory")
    for name in (
        ("material-preparation",) if preparation else ("single-job-flow", "single-job-worker")
    ):
        directory = path / "runtime" / name
        if directory.is_symlink() or (directory.exists() and not directory.is_dir()):
            raise ValueError("synthetic-runtime")
    for name in ("synthetic-flow.json", "portal.json", "codex-fixture"):
        if (path / name).is_symlink() or not (path / name).is_file():
            raise ValueError("synthetic-file")
    if any(
        (path / name).stat().st_size > 16_384 for name in ("synthetic-flow.json", "portal.json")
    ):
        raise ValueError("synthetic-metadata")
    marker = json.loads((path / "synthetic-flow.json").read_text())
    config = json.loads((path / "portal.json").read_text())
    expected = {
        "applications": str(path / "applications"),
        "career_workspace": str(path / "career"),
    }
    if mail:
        expected["preparation_root"] = str(path / "latex-base")
        if isinstance(config, dict) and "application_processed_label" in config:
            expected["application_processed_label"] = config["application_processed_label"]
    if (
        config != expected
        or not isinstance(marker, dict)
        or set(marker) != {"schemaVersion", "purpose", "codex_sha256"}
    ):
        raise ValueError("synthetic-contract")
    if (
        type(marker["schemaVersion"]) is not int
        or marker["schemaVersion"] != 1
        or marker["purpose"]
        != (
            "mail-synthetic"
            if mail
            else "preparation-synthetic"
            if preparation
            else "single-job-synthetic"
        )
    ):
        raise ValueError("synthetic-contract")
    executable = validate_codex_executable(path / "codex-fixture")
    if hashlib.sha256(Path(executable).read_bytes()).hexdigest() != marker["codex_sha256"]:
        raise ValueError("synthetic-cli")
    return expected


def no_synthetic_gmail(*_args, **_kwargs):
    raise PortalDataError("synthetic_gmail_disabled", "合成诊断模式不读取 Gmail。", 503)


def synthetic_preparation_resumes(*args, application=False):
    from career_evidence_graph.application_preparation_fixtures import (
        LITERAL_REPLAY_CACHE_KEY,
        SyntheticPrismClient,
        literal_replay_runner,
    )
    from career_evidence_graph.application_resume import ApplicationResumeStore

    client = SyntheticPrismClient(Path(args[2]).parents[2], application=application)
    if Path(args[2]) != client.projects:
        raise ValueError("synthetic-resume-root")

    class LiteralReplayStore(ApplicationResumeStore):
        # This explicit legacy replay exercises mail/material IO. Actual fixed
        # writing uses the ordinary handoff and independent subagent checks.
        def generate_for_task(self, identifier, revision, **options):
            from career_evidence_graph.application_full_latex import generate_full_latex
            from career_evidence_graph.application_information import (
                material_information_library,
                read_information_library,
            )

            options.pop("force_regenerate", None)
            options.pop("draft_only", None)
            options["information_library"] = material_information_library(
                self.applications.get_application(identifier),
                read_information_library(
                    None if application else client.root / "information-library"
                ),
            )
            return generate_full_latex(self, identifier, revision, **options)

    store = LiteralReplayStore(
        *args, prism_client=client, model_runner=literal_replay_runner(client.root)
    )
    # The fixed replay is identical across process reopen; retain input bindings.
    store._runner_cache_key = LITERAL_REPLAY_CACHE_KEY
    store.model_mode = "synthetic"
    return store


def synthetic_native_proof_snapshot(actual_snapshot, synthetic_root, *, record_event=None):
    """Deny-only test faults; never replace the native parent-pipe baseline."""
    synthetic_root = Path(synthetic_root)
    phase_lock = threading.Lock()
    phase_token, reads = None, 0

    def unique_object(pairs):
        value = dict(pairs)
        if len(value) != len(pairs):
            raise ValueError("duplicate synthetic fault fields")
        return value

    def snapshot(*, write_locked=False):
        nonlocal phase_token, reads
        actual = actual_snapshot()
        try:
            if (
                not synthetic_root.is_absolute()
                or synthetic_root.resolve(strict=True) != synthetic_root
            ):
                return None
            directory = os.open(synthetic_root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            try:
                try:
                    descriptor = os.open(
                        "native-proof-fault.json",
                        os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                        dir_fd=directory,
                    )
                except FileNotFoundError:
                    return actual
                try:
                    before = os.fstat(descriptor)
                    if (
                        not stat.S_ISREG(before.st_mode)
                        or before.st_nlink != 1
                        or before.st_uid != os.getuid()
                        or before.st_size > 4096
                    ):
                        return None
                    raw = os.read(descriptor, 4097)
                    after = os.fstat(descriptor)
                    if len(raw) > 4096 or (
                        before.st_size,
                        before.st_mtime_ns,
                        before.st_ctime_ns,
                    ) != (after.st_size, after.st_mtime_ns, after.st_ctime_ns):
                        return None
                finally:
                    os.close(descriptor)
            finally:
                os.close(directory)
            control = json.loads(raw, object_pairs_hook=unique_object)
            if (
                not isinstance(control, dict)
                or not {"fault"} <= control.keys() <= {"fault", "phase", "token"}
                or control["fault"]
                not in {
                    "none",
                    "accessibility",
                    "screen_recording",
                    "nonce",
                    "responsibility",
                    "stale",
                    "unknown",
                }
                or control.get("phase", "immediate")
                not in {"immediate", "after-first-read", "write-locked"}
                or (
                    "token" in control
                    or control.get("phase") in {"after-first-read", "write-locked"}
                )
                and (
                    not isinstance(control.get("token"), str)
                    or re.fullmatch(r"[A-Za-z0-9_-]{1,128}", control["token"]) is None
                )
            ):
                return None
        except (OSError, ValueError, TypeError):
            return None
        fault = control["fault"]
        if fault == "none":
            return actual
        if control.get("phase") == "write-locked":
            if not write_locked:
                return actual
            if record_event is not None:
                record_event(
                    "synthetic_native_proof_fault",
                    phase="write-locked",
                    token=control["token"],
                    fault=fault,
                )
            else:
                print(
                    json.dumps(
                        {
                            "event": "synthetic_native_proof_fault",
                            "phase": "write-locked",
                            "token": control["token"],
                            "fault": fault,
                        }
                    ),
                    flush=True,
                )
        if control.get("phase") == "after-first-read":
            token = (control["token"], fault)
            with phase_lock:
                if token != phase_token:
                    phase_token, reads = token, 0
                reads += 1
                if reads == 1:
                    return actual
        if not isinstance(actual, dict):
            return actual
        denied = deepcopy(actual)
        if fault in {"accessibility", "screen_recording"}:
            denied[fault] = False
        elif fault == "nonce":
            denied["launch_nonce"] = "synthetic-denied-nonce"
        elif fault == "responsibility":
            denied["responsibility_chain"] = "unknown"
        elif fault == "stale":
            denied["captured_at"] = -1
            if isinstance(denied.get("daemon"), dict):
                denied["daemon"]["checked_at"] = -1
        else:
            denied["kind"] = "sample"
        return denied

    snapshot.write_locked_snapshot = lambda: snapshot(write_locked=True)
    return snapshot


def main() -> int:
    native_nonce = os.environ.get("TOMORROWSTAR_NATIVE_LAUNCH_NONCE")
    parser = argparse.ArgumentParser()
    parser.add_argument("--applications", type=Path)
    parser.add_argument("--career-workspace", type=Path)
    parser.add_argument("--career-library-manifest", type=Path)
    parser.add_argument("--cover-letter-template", type=Path)
    parser.add_argument("--application-processed-label")
    parser.add_argument("--codex-executable", type=Path)
    parser.add_argument(
        "--codex-assist",
        action="store_true",
        help="Configure the dormant metadata-only Codex adapter; does not start a model turn.",
    )
    parser.add_argument(
        "--automatic-takeover",
        action="store_true",
        help="Let the Worker hand a page the script cannot continue to the takeover executor.",
    )
    # Unknown values stay a stated takeover reason rather than a failed launch.
    parser.add_argument("--takeover-executor", default="codex")
    # Opus scores matching beside sol with this Claude configuration (decided 2026-10-31).
    parser.add_argument("--second-opinion-claude-config", type=Path)
    parser.add_argument(
        "--information-library-root",
        type=Path,
        help="Read existing applicant information in preparation mode without starting a worker.",
    )
    parser.add_argument(
        "--worker-root",
        type=Path,
    )
    support = Path.home() / "Library/Application Support/TomorrowStar"
    parser.add_argument("--flow-root", type=Path)
    parser.add_argument(
        "--handoff-root",
        type=Path,
    )
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument(
        "--automation-lab",
        action="store_true",
        help="Explicitly enable the separate experimental automated worker.",
    )
    modes.add_argument("--codex-handoff", action="store_true")
    modes.add_argument("--synthetic-mail", type=Path)
    modes.add_argument("--synthetic-flow", type=Path)
    modes.add_argument("--synthetic-preparation", type=Path)
    modes.add_argument("--synthetic-browser", type=Path)
    modes.add_argument(
        "--single-job-flow",
        action="store_true",
        help="Explicitly enable the separate single-job application workflow.",
    )
    args = parser.parse_args()
    if args.second_opinion_claude_config is not None:
        from career_evidence_graph.application_match import configure_second_opinion
        from career_evidence_graph.application_second_opinion import ClaudeScorer

        configure_second_opinion(ClaudeScorer(args.second_opinion_claude_config))
    legacy = args.automation_lab or args.codex_handoff
    preparation_only = not (
        legacy
        or args.synthetic_flow
        or args.synthetic_browser
        or args.synthetic_mail
        or args.single_job_flow
    )
    if preparation_only and args.worker_root is not None:
        print(json.dumps({"status": "error", "code": "worker-mode-required"}), flush=True)
        return 2
    if (args.codex_assist or args.automatic_takeover) and (preparation_only or legacy):
        print(json.dumps({"status": "error", "code": "single-flow-required"}), flush=True)
        return 2
    try:
        synthetic_root = (
            args.synthetic_preparation
            or args.synthetic_flow
            or args.synthetic_browser
            or args.synthetic_mail
        )
        if synthetic_root is not None:
            if any(
                (
                    args.applications,
                    args.career_workspace,
                    args.career_library_manifest,
                    args.cover_letter_template,
                    args.worker_root,
                    args.flow_root,
                    args.handoff_root,
                    args.codex_executable,
                    args.codex_assist,
                    args.automatic_takeover,
                    args.information_library_root,
                    args.application_processed_label is not None,
                )
            ):
                raise ValueError("synthetic-overrides")
            config = synthetic_workspace(
                synthetic_root,
                preparation=args.synthetic_preparation is not None,
                browser=args.synthetic_browser is not None,
                mail=args.synthetic_mail is not None,
            )
            args.applications = Path(config["applications"])
            args.career_workspace = Path(config["career_workspace"])
            if args.synthetic_mail:
                args.application_processed_label = config.get("application_processed_label")
            support = synthetic_root / "runtime"
            executable = str(synthetic_root / "codex-fixture")
            os.environ.clear()
            os.environ.update(
                {
                    "PATH": "/usr/bin:/bin:/usr/sbin:/sbin",
                    "LANG": "en_US.UTF-8",
                    "HOME": str(synthetic_root / "home"),
                    "TMPDIR": str(synthetic_root / "tmp"),
                }
            )
        else:
            if args.applications is None or args.career_workspace is None:
                raise ValueError("workspace-required")
            if args.codex_executable is not None:
                os.environ["TOMORROWSTAR_CODEX_EXECUTABLE"] = str(args.codex_executable)
            try:
                executable = find_codex_executable(args.codex_executable)
            except CodexCLIError:
                # Retain the selected path so model steps cannot fall back to a
                # different CLI. Its absence does not prevent local data work.
                executable = None
        if executable is not None:
            os.environ["TOMORROWSTAR_CODEX_EXECUTABLE"] = executable
        # MC-21: Codex model calls and takeover use a dedicated HOME, never the user's ~/.codex.
        # Synthetic modes already run with a replaced HOME and a fixture CLI (no takeover).
        # Set even if it cannot be created: model calls then stop on validation instead.
        codex_home = support / "codex-home"
        codex_home_usable = False
        if synthetic_root is None:
            os.environ[CODEX_HOME_ENVIRONMENT] = str(codex_home)
            try:
                codex_home.mkdir(mode=0o700, parents=True, exist_ok=True)
                validate_codex_home(codex_home)
                codex_home_usable = True
            except (OSError, CodexCLIError):
                pass
        intake_factory = (
            no_synthetic_gmail if args.synthetic_flow or args.synthetic_browser else None
        )
        if args.synthetic_preparation:
            from career_evidence_graph.application_preparation_fixtures import (
                create_preparation_intake,
            )

            intake_factory = create_preparation_intake
        if args.synthetic_mail:
            from career_evidence_graph.application_preparation_fixtures import create_mail_intake

            intake_factory = create_mail_intake
        runtime_root = args.flow_root or args.worker_root or args.handoff_root or support
        record_event = backend_exit_recorder(runtime_root / "diagnostics")
        native_bridge = NativeHostBridge(root, runtime_root / "diagnostics", native_nonce)
        native_snapshot = native_bridge.snapshot
        if args.synthetic_browser is not None:
            native_snapshot = synthetic_native_proof_snapshot(
                native_snapshot, args.synthetic_browser, record_event=record_event
            )
        flow_legacy_roots = tuple(
            support / name
            for name in ("application-worker", "application-automation-lab", "codex-handoff")
        )
        if args.single_job_flow and args.worker_root not in (None, support / "single-job-worker"):
            flow_legacy_roots += (support / "single-job-worker",)
        worker_root = (
            None
            if args.codex_handoff or preparation_only
            else args.worker_root
            or support
            / ("application-automation-lab" if args.automation_lab else "single-job-worker")
        )
        from career_evidence_graph.job_listing_links import configure as configure_listing_links

        # LinkedIn jobs resolve to employer pages with the login saved by 登录领英.
        configure_listing_links(worker_root)
        takeover = args.codex_assist or args.automatic_takeover
        # MC-22: automatic takeover that is on but cannot be configured says why on the job.
        takeover_unavailable_reason = None
        if args.automatic_takeover and args.takeover_executor != "codex":
            takeover = False
            takeover_unavailable_reason = f"暂不支持的接管执行者：{args.takeover_executor[:40]}"
        elif takeover and executable is None:
            takeover_unavailable_reason = "找不到 Codex 命令行"
        elif takeover and not codex_home_usable:
            takeover_unavailable_reason = f"Codex 专用目录不可用（{codex_home}）"
        elif takeover:
            # Without sign-in the takeover is not configured; model calls check on each use.
            try:
                require_codex_sign_in(executable, codex_home)
            except CodexCLIError:
                codex_home_usable = False
                takeover_unavailable_reason = (
                    "Codex 专用目录未登录；请运行 "
                    f"env -u CODEX_HOME HOME='{codex_home}' '{executable}' login"
                )
            except (OSError, subprocess.SubprocessError):
                codex_home_usable = False
                takeover_unavailable_reason = "无法核对 Codex 登录状态"
        native_policy = (
            reviewed_native_assistance_policy()
            if args.automatic_takeover and takeover_unavailable_reason is None
            else None
        )
        assist_config = (
            {
                "executable": executable,
                "runtime": str(worker_root / "codex-assist"),
                "home": str(codex_home),
            }
            | ({"native_assistance_policy": native_policy} if native_policy else {})
            if takeover and takeover_unavailable_reason is None
            else None
        )
        if not args.automatic_takeover:
            takeover_unavailable_reason = None
        synthetic_latex_base = None
        if args.synthetic_mail:
            from career_evidence_graph.application_prism import source_snapshot

            def synthetic_latex_base(_task):
                return source_snapshot(args.synthetic_mail / "latex-base", "main.tex")

        server = create_server(
            args.applications,
            args.career_workspace,
            career_library_manifest=args.career_library_manifest,
            cover_letter_template=args.cover_letter_template,
            port=0,
            package_resources=root,
            handoff_root=(args.handoff_root or support / "codex-handoff")
            if args.codex_handoff
            else None,
            worker_root=worker_root,
            **({"worker_codex_assist_config": assist_config} if assist_config else {}),
            **({"worker_native_assistance_policy": native_policy} if native_policy else {}),
            **(
                {"takeover_unavailable_reason": takeover_unavailable_reason}
                if takeover_unavailable_reason
                else {}
            ),
            flow_root=None
            if legacy
            else (
                args.flow_root
                or support / ("material-preparation" if preparation_only else "single-job-flow")
            ),
            preparation_only=preparation_only,
            resume_review_root=support / "resume-review-snapshots"
            if preparation_only and synthetic_root is None
            else None,
            resume_review_pdf_inspector=NativePDFInspector(root / "pdf-inspect")
            if synthetic_root is None
            else None,
            resume_review_config=support / "resume-review.json"
            if preparation_only and synthetic_root is None
            else None,
            resume_template_config=support / "resume-review.json"
            if synthetic_root is None
            else None,
            information_library_root=(
                args.synthetic_preparation / "information-library"
                if args.synthetic_preparation
                else args.information_library_root
                or support / "single-job-worker" / "answer-library"
            )
            if preparation_only
            else None,
            flow_intake_factory=intake_factory,
            application_processed_label=args.application_processed_label,
            flow_resume_factory=(
                (lambda *values: synthetic_preparation_resumes(*values, application=True))
                if args.synthetic_mail
                else synthetic_preparation_resumes
                if args.synthetic_preparation
                else None
            ),
            flow_legacy_roots=flow_legacy_roots if args.single_job_flow else (),
            worker_fixtures=bool(args.synthetic_flow or args.synthetic_mail),
            worker_live=not (
                preparation_only or args.codex_handoff or args.synthetic_flow or args.synthetic_mail
            ),
            worker_generic=not (
                preparation_only or args.codex_handoff or args.synthetic_flow or args.synthetic_mail
            ),
            worker_cua=not (preparation_only or args.codex_handoff or args.synthetic_mail),
            worker_cua_click_route="trusted" if args.synthetic_mail else "dom_event",
            worker_synthetic_browser_root=args.synthetic_browser,
            native_host_identity=native_snapshot,
            native_host_binding=native_bridge.binding,
            # Synthetic settings are fixed before the Pipeline starts; nothing changes later.
            resume_model_mode="synthetic"
            if args.synthetic_flow or args.synthetic_browser or args.synthetic_mail
            else None,
            flow_automatic_latex_base=synthetic_latex_base,
        )
    except CodexCLIError:
        print(json.dumps({"status": "error", "code": "codex-unavailable"}), flush=True)
        return 2
    except (ValueError, OSError):
        print(json.dumps({"status": "error", "code": "workspace-unavailable"}), flush=True)
        return 2

    view = "handoff" if args.codex_handoff else "overview" if args.automation_lab else "flow"
    serve_with_parent_pipe(
        server,
        runtime_root / "diagnostics",
        {
            "status": "ready",
            "url": f"http://127.0.0.1:{server.server_port}/#{view}",
            "capabilities": {
                "codex": executable is not None,
                "flow": server.application_flow_service is not None,
                "worker": server.worker_service is not None,
                "synthetic": bool(synthetic_root),
            },
        },
        native_bridge=native_bridge,
        record_event=record_event,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
