"""Read-only evidence projection. Technical evidence never grants permission to resume."""

import hashlib
import json
import re
import time
from copy import deepcopy
from pathlib import Path

from .application_automation import validate_application_target
from .application_eligibility import task_eligibility
from .application_execution import write_admission_reason as write_admission_reason
from .application_worker import OWNED_PAGE_OBSERVATION
from .career_portal_data import PortalDataError
from .validation.hashing import record_digest as digest

# Exact legacy combinations require independently retained handoff evidence.
# No historical combination has yet been admitted to this table.
CONTROLLER_PROTOCOL = "single-job-control/v1"
VERIFIED_WORKERS = {}
CURRENT_WORKER_COMMANDS = ("observe-page", "resume", "recheck", "answer", "library", "heartbeat")


def current_packaged_worker(package, runtime, state, process):
    """A managed worker's entry check is separate from historical command admission."""
    proof = runtime.get("current_build") or {}
    return bool(
        process == "managed"
        and package.get("loaded_mapping") == "verified"
        and proof.get("protocol") == "installed-worker-start/v1"
        and proof.get("controller_protocol") == CONTROLLER_PROTOCOL
        and proof.get("manifest_revision") == package.get("startup_manifest_revision")
        and proof.get("manifest_revision") == package.get("manifest_revision")
        and proof.get("loaded_engine_revision") == runtime.get("loaded_engine_revision")
        and runtime.get("loaded_engine_revision")
        == (package.get("loaded_code") or {}).get("worker")
        and proof.get("run_id") == runtime.get("id")
        and proof.get("pid") == runtime.get("pid")
        and proof.get("batch_id") == state.get("batch_id")
        and proof.get("source_revision") == (runtime.get("source") or {}).get("sha256")
    )


def require_packaged_worker_identity(resources, expected_manifest, expected_worker, actual_worker):
    """Check the gate-frozen build binding against code actually loaded by this worker."""
    package = inspect_disk_package(resources)
    if (
        not expected_manifest
        or not expected_worker
        or not actual_worker
        or package.get("status") != "verified"
        or package.get("manifest_revision") != expected_manifest
        or (package.get("loaded_code") or {}).get("worker") != expected_worker
        or actual_worker != expected_worker
    ):
        raise PortalDataError(
            "installed_worker_identity_unverified",
            "当前执行器与本次批准的安装包未核验匹配，请保持暂停。",
            409,
        )


def inspect_disk_package(resources: Path | None) -> dict:
    result = {
        "status": "unknown",
        "manifest_revision": None,
        "matches_manifest": None,
        "signature": "not_checked",
        "loaded_mapping": "unknown",
    }
    if resources is None:
        return result
    try:
        resources = Path(resources).absolute()
        if any(path.is_symlink() for path in (resources, *resources.parents)):
            raise ValueError
        manifest_path = resources / "build-manifest.json"
        if manifest_path.is_symlink():
            raise ValueError
        raw = manifest_path.read_bytes()
        if len(raw) > 2_000_000:
            raise ValueError
        manifest = json.loads(raw)
        if manifest.get("format") != "tomorrowstar-macos-build/v1":
            raise ValueError
        files = {"system/" + key: value for key, value in manifest["engine_files"].items()}
        files.update(manifest.get("native_helpers", {}))
        files.update(manifest.get("native_tools", {}))
        driver = manifest.get("cua_driver")
        if driver:
            files[driver["path"]] = driver["sha256"]
        if not files or len(files) > 20_000:
            raise ValueError
        matches = True
        for relative, expected in files.items():
            path = resources / relative
            if (
                not relative
                or Path(relative).is_absolute()
                or ".." in Path(relative).parts
                or not re.fullmatch(r"[a-f0-9]{64}", expected)
                or any(part.is_symlink() for part in (path, *path.parents))
            ):
                raise ValueError
            matches = (
                matches
                and path.is_file()
                and hashlib.sha256(path.read_bytes()).hexdigest() == expected
            )
        if manifest_path.read_bytes() != raw:
            raise ValueError
        record = manifest.get("loaded_code")
        if record is not None:
            if (
                not isinstance(record, dict)
                or record.get("protocol") != "packaged-loaded-code/v1"
                or record.get("engine_files_revision") != digest(manifest["engine_files"])
                or not isinstance(record.get("python_runtime"), str)
                or any(
                    not isinstance(record.get(role), str)
                    or not re.fullmatch(
                        "python-loaded-code/v1:" + role + r":[a-f0-9]{64}", record[role]
                    )
                    for role in ("controller", "worker")
                )
                or not re.fullmatch(r"[a-f0-9]{64}", record.get("ui_revision", ""))
            ):
                raise ValueError
            static_prefix = "src/career_evidence_graph/portal_static/"
            expected_ui = {
                key.removeprefix(static_prefix): value
                for key, value in manifest["engine_files"].items()
                if key.startswith(static_prefix) and "/" not in key.removeprefix(static_prefix)
            }
            if not expected_ui or digest(expected_ui) != record["ui_revision"]:
                raise ValueError
        return result | {
            "status": "verified" if matches else "mismatch",
            "manifest_revision": "disk-manifest-sha256:" + hashlib.sha256(raw).hexdigest(),
            "matches_manifest": matches,
            "loaded_code": deepcopy(record),
        }
    except (OSError, ValueError, TypeError, KeyError, AttributeError):
        return result | {"status": "unavailable"}


def map_loaded_package(startup_package, current_package, controller):
    """Relate frozen startup code to its measured build record; never relabel it."""
    result = deepcopy(current_package)
    record = startup_package.get("loaded_code")
    result["startup_manifest_revision"] = startup_package.get("manifest_revision")
    # A measured startup manifest still defines the disk boundary even when it
    # predates loaded-code records. Do not downgrade later drift to unknown.
    if (
        startup_package.get("status") == "verified"
        and startup_package.get("manifest_revision")
        and (
            current_package.get("status") != "verified"
            or current_package.get("manifest_revision") != startup_package["manifest_revision"]
            or current_package.get("loaded_code") != record
        )
    ):
        return result | {
            "status": "mismatch",
            "loaded_mapping": "mismatch",
            "mapping_reason": "disk_package_changed_since_startup",
        }
    if not isinstance(record, dict):
        return result | {
            "loaded_mapping": "unknown",
            "mapping_reason": "build_loaded_record_missing",
        }
    if startup_package.get("status") != "verified":
        return result | {
            "loaded_mapping": "unknown",
            "mapping_reason": "startup_package_unverified",
        }
    if controller.get("loaded_engine_revision") is None:
        return result | {
            "loaded_mapping": "unknown",
            "mapping_reason": "controller_loaded_identity_unknown",
        }
    if (
        controller.get("loaded_engine_revision") != record["controller"]
        or controller.get("ui_revision") != record["ui_revision"]
    ):
        return result | {
            "status": "mismatch",
            "loaded_mapping": "mismatch",
            "mapping_reason": "loaded_controller_build_mismatch",
        }
    return result | {"loaded_mapping": "verified", "mapping_reason": "measured_engine_roles_only"}


def project_native_host(receipt, binding, now):
    result = {"state": "unknown", "reason": "no_current_native_host_receipt"}
    if not isinstance(receipt, dict) or not isinstance(binding, dict):
        return result
    result.update(
        {
            key: receipt.get(key)
            for key in (
                "captured_at",
                "accessibility",
                "screen_recording",
                "scope",
                "kind",
            )
        }
    )
    result["identity_state"] = "unverified"
    result.update(
        {key: receipt.get(key) for key in ("bundle_id", "executable", "native_pid", "backend_pid")}
    )
    result["instance_binding"] = {
        key: receipt.get(key)
        for key in ("launch_nonce", "native_pid", "backend_pid", "bundle_id", "executable")
    }
    result["responsibility_chain"] = receipt.get("responsibility_chain", "unknown")
    result["session_open"] = receipt.get("session_open")
    result["invalidation_epoch"] = receipt.get("invalidation_epoch")
    result["bridge_binding_verified"] = receipt.get("instance_binding") == binding
    if receipt.get("protocol") != "current-native-host/v1":
        return result | {"reason": "native_protocol_unknown"}
    if receipt.get("scope") != "current_instance":
        return result | {"reason": "not_current_native_instance"}
    if any(
        not binding.get(key) or receipt.get(key) != binding[key]
        for key in ("launch_nonce", "native_pid", "backend_pid", "bundle_id", "executable")
    ):
        return result | {"state": "blocked", "reason": "native_instance_mismatch"}
    if (
        not isinstance(receipt.get("captured_at"), (int, float))
        or not 0 <= now - receipt["captured_at"] < 30
    ):
        return result | {"reason": "native_receipt_stale"}
    result["identity_state"] = "binding_verified"
    if receipt.get("state") == "blocked" and receipt.get("reason") in {
        "responsibility_chain_mismatch",
        "permission_probe_rejected",
        "native_instance_mismatch",
    }:
        return result | {"state": "blocked", "reason": receipt["reason"]}
    if receipt.get("accessibility") is False or receipt.get("screen_recording") is False:
        return result | {"state": "blocked", "reason": "native_permission_missing"}
    if receipt.get("kind") != "check":
        return result | {"reason": "permission_check_required"}
    daemon = receipt.get("daemon") or {}
    if not isinstance(daemon, dict):
        return result | {"reason": "native_responsibility_unverified"}
    result["daemon"] = deepcopy(daemon)
    if (
        receipt.get("state") == "verified"
        and receipt.get("accessibility") is True
        and receipt.get("screen_recording") is True
        and receipt.get("responsibility_chain") == "verified"
        and daemon.get("prompt") is False
        and daemon.get("closed") is True
        and type(daemon.get("pid")) is int
        and daemon["pid"] > 0
        and type(daemon.get("proxy_pid")) is int
        and daemon["proxy_pid"] > 0
        and daemon.get("responsible_pid") == binding.get("native_pid")
        and daemon.get("proxy_responsible_pid") == binding.get("native_pid")
        and isinstance(daemon.get("checked_at"), (int, float))
        and 0 <= now - daemon["checked_at"] < 30
    ):
        return result | {"state": "verified", "reason": "current_native_host_verified"}
    return result | {"reason": "native_responsibility_unverified"}


def project_readiness(
    *,
    controller,
    package,
    state,
    task,
    job,
    inputs,
    native_host,
    page_target,
    process,
    storage_error,
    changed,
    now,
    flow_root=None,
):
    from .application_single_binding import valid_send_approval

    runtime = (state or {}).get("runtime") or {}
    source = runtime.get("source") or {}
    last_error = (state or {}).get("worker_error", "")
    if not isinstance(last_error, str) or not re.fullmatch(r"[A-Za-z0-9_]{0,80}", last_error):
        last_error = "unclassified_worker_error"
    worker_state = (
        "exited"
        if process == "exited"
        else "missing"
        if not runtime
        else "current"
        if 0 <= now - runtime.get("observed_at", 0) < 6
        else "stale"
    )
    worker = {
        "state": worker_state,
        "run_id": runtime.get("id"),
        "pid": runtime.get("pid"),
        "startup_source_revision": source.get("sha256"),
        "loaded_engine_revision": runtime.get("loaded_engine_revision"),
        "capabilities": deepcopy(runtime.get("capabilities", [])),
        "last_error": last_error,
        "process": process,
        "package_mapping": (
            "verified"
            if package.get("loaded_mapping") == "verified"
            and runtime.get("loaded_engine_revision")
            == (package.get("loaded_code") or {}).get("worker")
            else "different"
            if package.get("loaded_mapping") == "verified" and runtime.get("loaded_engine_revision")
            else "unknown"
        ),
        "observed_control": (state or {}).get("control"),
    }
    receipt = (job or {}).get("owned_page_inspection") or {}
    fresh = bool(
        receipt.get("status") == "captured"
        and page_target
        and receipt.get("binding") == page_target
        and receipt.get("worker_source") == source.get("sha256")
        and 0 <= now - receipt.get("at", 0) < 10
        and process != "exited"
        and not changed
    )
    owner = receipt.get("owner") or {}
    owner_state = owner.get("status", "unknown") if fresh else "unknown"
    owner_ok = (
        owner_state == "accepted"
        and type(owner.get("pid")) is int
        and owner["pid"] > 0
        and type(owner.get("window_id")) is int
        and owner["window_id"] > 0
        and isinstance(owner.get("observed_at"), (int, float))
        and 0 <= now - owner["observed_at"] < 10
        and owner.get("driver_version") is not None
    ) or (
        owner_state == "not_used"
        and owner.get("transport") == "retained-playwright"
        and (state or {}).get("cua_enabled") is False
    )
    page = {
        "state": "current" if fresh and owner_ok else "historical" if receipt else "unknown",
        "binding": receipt.get("binding"),
        "owner": {**deepcopy(owner), "status": owner_state if fresh else "unknown"},
        "observed_at": receipt.get("at"),
        "remote_save_verified": False,
    }
    tuple_key = (
        CONTROLLER_PROTOCOL,
        runtime.get("loaded_engine_revision"),
        source.get("sha256"),
    )
    current_build = current_packaged_worker(package, runtime, state or {}, process)
    evidence = (
        {
            "commands": CURRENT_WORKER_COMMANDS,
            "basis": ["current measured package and executed worker entry protocol"],
        }
        if current_build
        else VERIFIED_WORKERS.get(tuple_key)
    )
    observe = bool(
        page_target
        and OWNED_PAGE_OBSERVATION in runtime.get("capabilities", ())
        and (state or {}).get("control") == "paused"
        and worker_state == "current"
        and last_error in {"", "control_connection_lost"}
    )
    compatibility = {
        "controller_protocol": CONTROLLER_PROTOCOL,
        "state": "verified" if evidence else "unknown",
        "kind": "current_package"
        if current_build
        else "historical_exact"
        if evidence
        else "unknown",
        "commands": {
            "read_state": "supported",
            "observe_page": "supported" if observe else "unknown",
            **{
                command: "supported"
                if evidence and command in evidence.get("commands", ())
                else "unknown"
                for command in CURRENT_WORKER_COMMANDS
                if command != "observe-page"
            },
        },
        "basis": deepcopy((evidence or {}).get("basis", [])),
    }
    reasons = []
    if changed:
        inputs = inputs | {"state": "state_changed"}
        reasons.append("state_changed_during_read")
    if package["status"] != "verified":
        reasons.append("disk_package_unverified")
    if package.get("loaded_mapping") != "verified":
        reasons.append("loaded_package_mapping_unknown")
    if (
        controller.get("source_matches_disk") is not True
        or controller.get("ui_matches_disk") is not True
    ):
        reasons.append("controller_disk_drift")
    if native_host["state"] != "verified":
        reasons.append(native_host["reason"])
    if worker_state != "current":
        reasons.append("worker_" + worker_state)
    if not runtime.get("loaded_engine_revision"):
        reasons.append("worker_loaded_identity_unknown")
    if not evidence:
        reasons.append("worker_compatibility_unknown")
    if inputs["state"] != "current":
        reasons.append("inputs_" + inputs["state"])
    if page["state"] != "current":
        reasons.append("owned_page_evidence_required")
    if storage_error:
        reasons.append("worker_storage_stopped")
    if last_error:
        reasons.append("worker_error_retained")
    if (state or {}).get("control") == "running":
        reasons.append("worker_control_not_paused")
    if (state or {}).get("commands"):
        reasons.append("pending_worker_commands")
    if (task or {}).get("status") == "cancelled" or (job or {}).get("status") == "cancelled":
        reasons.append("cancelled_state_retained")
    if (job or {}).get("intent"):
        reasons.append("unresolved_action_retained")
    inputs = inputs | {
        "qualification": task_eligibility(task).get("status") if task else "unknown",
        "materials_confirmed": (task or {}).get("materials_confirmed") is True,
        "send_scope_confirmed": bool(
            task and valid_send_approval(task, flow_root, require_active=True)
        ),
    }
    if not inputs["materials_confirmed"] and inputs.get("materials_current") is not True:
        reasons.append("current_material_binding_required")
    if inputs["qualification"] not in {"supported", "not_specified", "needs_input"}:
        reasons.append("qualification_unverified")
    if not inputs["send_scope_confirmed"]:
        reasons.append("send_scope_unverified")
    blocked = bool(
        changed
        or storage_error
        or last_error
        or process == "exited"
        or package["status"] == "mismatch"
        or native_host["state"] == "blocked"
        or inputs["state"] == "stale"
    )
    return {
        "schemaVersion": 1,
        "protocol": "installed-readiness/v1",
        "checked_at": now,
        "status": "blocked" if blocked else "unknown" if reasons else "verified_paused",
        "controller": deepcopy(controller),
        "package": package,
        "worker": worker,
        "native_host": native_host,
        "page": page,
        "inputs": inputs,
        "compatibility": compatibility,
        "user_stop": {"state": "paused", "requires_explicit_resume": True},
        "reasons": reasons,
        "decision": {
            "can_fill": False,
            "can_observe_page": observe and not changed and not storage_error,
            "user_control": "paused",
        },
    }


class ReadinessProbe:
    """Read-only readiness projection over the assembled owners; it grants no write."""

    def __init__(
        self,
        *,
        applications,
        evidence,
        flow=None,
        resumes=None,
        worker=None,
        static_root: Path,
        static_files: dict,
        controller_boot: dict,
        controller_files: dict,
        package_resources: Path | None = None,
        native_host_identity=None,
        native_host_binding: dict | None = None,
        information_library_root: Path | None = None,
        legacy_roots=(),
        preparation_only=False,
    ):
        self.applications = applications
        self.evidence = evidence
        self.flow = flow
        self.resumes = resumes
        self.worker = worker
        self.static_root = static_root
        self.static_files = static_files
        self.controller_boot = controller_boot
        self.controller_files = controller_files
        self.package_resources = package_resources
        self.package_boot = inspect_disk_package(package_resources)
        self.native_host_identity = native_host_identity
        self.native_binding = deepcopy(native_host_binding)
        self.information_library_root = information_library_root
        self.legacy_roots = legacy_roots
        self.preparation_only = preparation_only

    def capture_write_state(self, task_id):
        flow, worker = self.flow, self.worker
        with self.applications.write_lock():
            saved, task = flow.witness(task_id) if flow else ({}, None)
            application = (
                self.applications.get_application(task["application_id"]) if task else None
            )
            state = deepcopy(worker.store.load()) if worker else {}
            return saved, task, application, state

    def write_configuration(self):
        from .application_match import match_configuration_revision
        from .application_resume import resume_configuration_revision

        flow, resumes, worker = self.flow, self.resumes, self.worker
        return (
            match_configuration_revision() if flow else None,
            resume_configuration_revision(resumes) if resumes else None,
            tuple(
                flow.callbacks.get(key)
                for key in (
                    "analysis",
                    "resume",
                    "verify_materials",
                    "verify_automation_authorization",
                )
            )
            if flow
            else (),
            tuple(getattr(resumes, key, None) for key in ("tailorer", "model_runner", "exporter")),
            tuple(
                getattr(worker, key, None)
                for key in (
                    "live",
                    "generic",
                    "cua",
                    "headless",
                    "cua_click_route",
                    "fixture_origin",
                    "cdp_port",
                    "synthetic_browser_root",
                )
            ),
            deepcopy(worker.packaged_startup_identity) if worker else None,
            worker.store.single_context()
            if worker and worker.store.single_flow_root is not None
            else None,
            worker.store.single_validator if worker else None,
            worker.store.single_material_source_provider if worker else None,
        )

    @staticmethod
    def write_state_token(captured, stage):
        saved, task, application, state = deepcopy(captured)
        progress = stage in {"answer", "library", "heartbeat"}
        state.pop("worker_heartbeat", None)
        runtime = state.get("runtime") or {}
        runtime.pop("observed_at", None)
        if progress:
            state.pop("heartbeat_at", None)
            if application:
                application = {
                    key: application.get(key)
                    for key in (
                        "id",
                        "company",
                        "role_title",
                        "location",
                        "job_description",
                        "url",
                        "status",
                    )
                }
            for row in saved.get("tasks", ()):
                if task and row["id"] == task["id"]:
                    row.pop("revision", None)
                    row["status"] = "cancelled" if row["status"] == "cancelled" else "active"
                    reference = row.get("worker_ref")
                    if reference:
                        for key in ("status", "reason", "page_open", "handed_off"):
                            reference.pop(key, None)
            if task:
                task = next(row for row in saved["tasks"] if row["id"] == task["id"])
        for row in state.get("jobs", ()):
            page = row.get("page_observation")
            if page:
                page.pop("at", None)
            if progress:
                intent = row.get("intent")
                if intent and (
                    intent.get("action") not in {"open", "fill", "upload"}
                    or intent.get("run_id") != runtime.get("id")
                    or intent.get("input_refs")
                    != {"revision": row.get("revision"), "file_sha256": row.get("file_sha256")}
                    or intent.get("action") != "open"
                    and intent.get("page_id") != (page or {}).get("page_id")
                ):
                    return ("invalid_running_intent", digest(captured))
                for key in (
                    "revision",
                    "observations",
                    "questions",
                    "answer_refs",
                    "intent",
                    "page_open",
                    "page_observation",
                    "pending_sync",
                    "pending_status",
                ):
                    row.pop(key, None)
                if row.get("status") in {"queued", "filling", "needs_input", "ready_for_review"}:
                    row["status"] = "active"
        return digest((saved, task, application, state))

    def __call__(self, task_id=None, *, _with_witness=False, _write_stage=None, _country=None):
        from .application_flow import stat_tokens
        from .application_input_binding import (
            job_input_revision,
            latest_preparation_task,
            retained_configuration_inputs,
        )

        applications, evidence, flow = self.applications, self.evidence, self.flow
        resumes, worker = self.resumes, self.worker
        package_resources = self.package_resources
        information_library_root = self.information_library_root

        def capture():
            return self.capture_write_state(task_id)

        before = capture()
        saved, task, application, state = before
        job = next(
            (
                row
                for row in state.get("jobs", [])
                if task and row["application_id"] == task["application_id"]
            ),
            None,
        )

        def file_tokens():
            paths = {path for path, _kind in evidence._paths()}
            paths.update((evidence.root, *(evidence.root / folder for folder in evidence._KINDS)))
            paths.add(evidence.root / ".tomorrowstar-match-history" / "current.json")
            paths.update(self.controller_files)
            if task and task.get("resume_id") and resumes:
                paths.update((resumes.root / task["resume_id"]).rglob("*"))
                paths.add(
                    applications.root
                    / ".execution"
                    / (hashlib.sha256(task["application_id"].encode()).hexdigest() + ".json")
                )
            if _with_witness:
                paths.update(applications._paths())
                paths.add(applications.root)
                for legacy in self.legacy_roots:
                    paths.update(
                        Path(legacy) / name
                        for name in ("run.json", "handoff.json", "prepare-pending.json")
                    )
            if information_library_root:
                paths.update(
                    Path(information_library_root) / name
                    for name in ("answers.json", "profile.json")
                )
            if package_resources:
                manifest = Path(package_resources) / "build-manifest.json"
                paths.add(manifest)
                try:
                    built = json.loads(manifest.read_bytes())
                    paths.update(
                        Path(package_resources) / "system" / key for key in built["engine_files"]
                    )
                    for group in ("native_helpers", "native_tools"):
                        paths.update(Path(package_resources) / key for key in built.get(group, {}))
                    if built.get("cua_driver"):
                        paths.add(Path(package_resources) / built["cua_driver"]["path"])
                except (OSError, ValueError, TypeError, KeyError):
                    pass
            worker_root = None
            if worker:
                facts = worker.readiness_facts(state, job)
                worker_root = facts["root"]
                paths.update(facts["paths"])
                if job and job.get("file_path"):
                    paths.add(Path(job["file_path"]))
            # Directory tokens detect new source entries without a scan in a write lock.
            paths.update(
                path.parent for path in tuple(paths) if not worker or path.parent != worker_root
            )
            return stat_tokens(paths)

        first_file_tokens = file_tokens()
        configuration = self.write_configuration() if _with_witness else None
        inputs = {
            "state": "unknown",
            "task_revision": (task or {}).get("revision"),
            "input_revision": digest(task["inputs"]) if task else None,
        }
        admission_target = None
        if task:
            try:
                observed = flow.input_provider(task["application_id"])
                fresh = (
                    retained_configuration_inputs(task, observed["inputs"]) == task["inputs"]
                    and job_input_revision(application) == task["job_binding"]
                )
                if self.preparation_only:
                    latest = latest_preparation_task(saved["tasks"], task["application_id"])
                    fresh = (
                        fresh
                        and latest is not None
                        and latest["id"] == task["id"]
                        and latest.get("input_epoch", 0) == task.get("input_epoch", 0)
                    )
                if task.get("latex_base"):
                    flow.verify_latex_base(task)
                if task.get("materials_confirmed") or task.get("status") == "resume_ready":
                    flow.verify_materials(task)
                    inputs["materials_current"] = True
                if task.get("worker_ref"):
                    flow.callbacks["worker_reference"](task)
                if _with_witness and job:
                    fixed_qualification = (
                        worker.store.check_single(
                            job, state, allow_unbound=not task.get("worker_ref")
                        )
                        is True
                    )
                elif _with_witness and worker:
                    from .application_single_binding import (
                        check_single_qualification,
                        verify_material_lineage,
                    )

                    verify_material_lineage(
                        applications,
                        flow.root,
                        evidence.root,
                        task,
                        resume_store=resumes,
                        analysis_adapter=flow.analysis.adapter_revision,
                        information_library_root=information_library_root,
                    )
                    fixed_qualification = check_single_qualification(
                        task,
                        application,
                        information_library_root or worker.store.root / "answer-library",
                        _country,
                    )
                if _with_witness and worker:
                    if worker.live and not fixed_qualification:
                        worker.store.check_language_requirement(
                            application, country=job["country"] if job else _country
                        )
                    from .application_execution import automated_owner
                    from .application_single_binding import check_legacy_roots

                    check_legacy_roots(
                        applications,
                        self.legacy_roots,
                        task["application_id"],
                        application["url"],
                        current_root=worker.store.root,
                        current_owner=automated_owner(
                            worker.store.root, state["batch_id"], task["application_id"]
                        )
                        if job
                        else None,
                    )
                    admission_target = validate_application_target(
                        applications,
                        task["application_id"],
                        job["revision"]
                        if job and _write_stage == "resume"
                        else application["revision"],
                        allow_generic=worker.generic,
                    )
                    if job:
                        worker.store.check_generic_enabled(job, state)
                        if admission_target["job_url"] != job["job_url"]:
                            raise ValueError("worker target changed")
                        if (
                            hashlib.sha256(Path(job["file_path"]).read_bytes()).hexdigest()
                            != job["file_sha256"]
                        ):
                            raise ValueError("worker attachment changed")
                inputs["state"] = "current" if fresh else "stale"
            except (OSError, PortalDataError, ValueError, TypeError, KeyError):
                inputs["state"] = "unknown"
        controller = deepcopy(self.controller_boot)
        try:
            controller["source_matches_disk"] = all(
                path.is_file() and hashlib.sha256(path.read_bytes()).hexdigest() == expected
                for path, expected in self.controller_files.items()
            )
            controller["ui_matches_disk"] = {
                path.name: path.read_bytes()
                for path in self.static_root.iterdir()
                if path.is_file()
            } == self.static_files
        except OSError:
            controller.update(source_matches_disk=None, ui_matches_disk=None)
        package = map_loaded_package(
            self.package_boot, inspect_disk_package(package_resources), self.controller_boot
        )
        now = time.time()
        facts = (
            worker.readiness_facts(state, job)
            if worker
            else {"pending_prepare": False, "owned_process_alive": False, "process": "unknown"}
        )
        inputs["pending_prepare"] = facts["pending_prepare"]
        inputs["owned_process_alive"] = facts["owned_process_alive"]
        try:
            receipt = (
                self.native_host_identity()
                if callable(self.native_host_identity)
                else deepcopy(self.native_host_identity)
            )
        except (OSError, ValueError, TypeError):
            receipt = None
        native = project_native_host(receipt, self.native_binding, now)
        target = facts.get("page_target") if job else None
        changed = (
            self.write_state_token(before, _write_stage)
            != self.write_state_token(capture(), _write_stage)
            if _with_witness
            else digest(before) != digest(capture())
        ) or first_file_tokens != file_tokens()
        result = project_readiness(
            controller=controller,
            package=package,
            state=state | {"cua_enabled": worker.cua if worker else None},
            task=task,
            job=job,
            inputs=inputs,
            native_host=native,
            page_target=target,
            process=facts["process"],
            storage_error=worker.store.stop_reason() if worker else "",
            changed=changed,
            now=now,
            flow_root=flow.root if flow else None,
        )
        if _with_witness:
            return result, {
                "before": before,
                "files": first_file_tokens,
                "configuration": configuration,
                "native": deepcopy(receipt),
                "task_id": task_id,
                "target": admission_target,
            }
        return result
