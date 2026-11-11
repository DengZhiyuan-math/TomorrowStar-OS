"""Read-only material and legacy-executor checks for the single-job worker."""

from __future__ import annotations

import hashlib
import json
import re
from contextlib import contextmanager
from contextvars import ContextVar
from copy import deepcopy
from pathlib import Path

from .application_automation import validate_application_target
from .application_flow_store import assemble
from .application_input_binding import bound_revision, same_revision, task_configuration_current
from .career_portal_data import CareerCatalog, PortalDataError

# 2026-11-03: these result keys are projected when a saved export or draft is read,
# not recorded facts. `used_source_ids` is computed from the draft items since
# 07d8abdb (older adoptions recorded []), so lineage skips it; the draft and PDF
# hashes still bind the items. A draft's `resume_configuration_revision` is
# re-derived as `cfg2:` since 4f5ac854 and is compared with `same_revision`.
READ_TIME_RESULT_KEYS = frozenset({"preview_url", "used_source_ids"})


# flow.json keeps every task's stage results inline (`artifacts[*].result`, about
# 9 MB per job that reaches materials_ready) plus one task's full prior copy during
# a material update: a real job reached 37 MB (2026-10-31) and 21 tasks reached
# 72.7 MB (2026-11-05). The bound still refuses unbounded local records.
def _read(path: Path, *, expected_sha256=None, maximum_bytes=256_000_000) -> dict:
    if (
        any(part.is_symlink() for part in (path, *path.parents))
        or path.stat().st_size > maximum_bytes
    ):
        raise ValueError("unsafe record")
    raw = path.read_bytes()
    if len(raw) > maximum_bytes or (
        expected_sha256 is not None and hashlib.sha256(raw).hexdigest() != expected_sha256
    ):
        raise ValueError("changed record")
    value = json.loads(raw.decode("utf-8"))
    if not isinstance(value, dict):
        raise ValueError("invalid record")
    return value


def valid_send_approval(task, flow_root=None, *, require_active=False):
    """Keep direct user approval distinct from an exact once-authorized workflow."""
    from .application_information import COUNTRIES
    from .validation.hashing import record_digest as digest

    approval = task.get("send_approval") or {}
    if approval.get("confirmed") is not True or any(
        approval.get(key) != task.get(key)
        for key in ("resume_id", "resume_sha256", "analysis_id", "inputs")
    ):
        return False
    if approval.get("verified_by") == "user":
        return approval.get("authorization") is None
    if (
        approval.get("verified_by") != "workflow_policy"
        or approval.get("actor") != "system"
        or approval.get("human_reviewed") is not False
        or flow_root is None
    ):
        return False
    try:
        policy = _read(Path(flow_root) / "pipeline.json")
        receipt = approval["authorization"]
        grant = policy["authorization"]
        valid = (
            policy.get("schemaVersion") == 1
            and policy.get("protocol") == "application-pipeline/v1"
            and policy.get("policy_version") == "email-to-manual-submit/v1"
            and policy.get("revision")
            == digest({key: value for key, value in policy.items() if key != "revision"})
            and isinstance(receipt, dict)
            and receipt == policy.get("transmission_authorization")
            and receipt.get("policy_version") == policy["policy_version"]
            and grant.get("verified_by") == "user"
            and grant.get("scope") == "this_email_cycle"
            and grant.get("existing_facts") is True
            and grant.get("generated_pdf") is True
            and grant.get("final_submit") == "manual"
            and receipt.get("authorization_id") == grant.get("id")
            and isinstance(grant.get("id"), str)
            and bool(grant["id"])
            and receipt.get("pipeline_id") == policy.get("id")
            and receipt.get("intake_run_id") == policy.get("intake_run_id")
            and receipt.get("task_id") == task.get("id") == policy.get("active_task_id")
            and receipt.get("country") == approval.get("country") in COUNTRIES
            and receipt.get("job_url") == approval.get("job_url")
            and any(
                row.get("task_id") == task.get("id")
                and row.get("application_id") == task.get("application_id")
                and row.get("status") == "matched"
                for row in policy["items"]
            )
            and all(
                receipt.get(key) == task.get(key)
                for key in (
                    "application_id",
                    "analysis_id",
                    "job_binding",
                    "inputs",
                    "resume_id",
                    "resume_sha256",
                )
            )
        )
        return bool(valid and (not require_active or policy.get("control") == "running"))
    except (OSError, ValueError, TypeError, KeyError, AttributeError):
        return False


def _legacy_run_targets(applications, record: dict) -> list[str]:
    """Identify targets by current full-note bytes, without inferring an old write root."""
    from .application_automation import _job_identity

    rows = record.get("jobs")
    if type(record.get("schemaVersion")) is not int or not isinstance(rows, list) or not rows:
        raise ValueError("unverifiable legacy targets")
    targets = []
    for row in rows:
        if (
            not isinstance(row, dict)
            or not isinstance(row.get("application_id"), str)
            or not row["application_id"]
            or not isinstance(row.get("revision"), str)
            or re.fullmatch(r"[a-fA-F0-9]{64}", row["revision"]) is None
            or "intent" not in row
            or row["intent"] is not None
            and (
                not isinstance(row["intent"], dict)
                or row["intent"].get("action") not in {"open", "fill", "upload"}
            )
        ):
            raise ValueError("unverifiable legacy target")
        try:
            application = applications.get_application(row["application_id"])
            target = _job_identity(row.get("job_url"), allow_generic=True)[1]
            current = _job_identity(application.get("url"), allow_generic=True)[1]
        except PortalDataError as error:
            raise ValueError("unreadable legacy target") from error
        if (
            application["id"] != row["application_id"]
            or row["revision"].lower() != application["revision"]
            or target != current
        ):
            raise ValueError("changed legacy target")
        targets.append(target)
    return targets


def check_legacy_roots(
    applications,
    roots,
    application_id: str,
    job_url: str,
    *,
    current_root=None,
    current_owner=None,
) -> None:
    """Inspect only explicit known roots and the shared claim; never initialize a store."""
    from .application_automation import _job_identity

    try:
        claim = (
            applications.root
            / ".execution"
            / (hashlib.sha256(application_id.encode()).hexdigest() + ".json")
        )
        if claim.is_symlink() or claim.parent.is_symlink():
            raise ValueError("unsafe claim")
        if claim.exists():
            owner = _read(claim)
            if (
                owner.get("schemaVersion") != 1
                or owner.get("application_id") != application_id
                or not isinstance(owner.get("active"), bool)
                or owner.get("lane") not in {"codex", "automated"}
                or not isinstance(owner.get("owner"), str)
                or not owner["owner"]
            ):
                raise ValueError("invalid claim")
            if owner["active"] and (
                owner["owner"] != current_owner or owner["lane"] != "automated"
            ):
                raise PortalDataError(
                    "single_legacy_active", "原岗位已有执行占用，请先核验旧任务。", 409
                )
        for value in roots:
            root = Path(value)
            if any(part.is_symlink() for part in (root, *root.parents)):
                raise ValueError("unsafe legacy root")
            if root.exists() and not root.is_dir():
                raise ValueError("invalid legacy root")
            if current_root is not None and root.exists() and root.samefile(current_root):
                continue
            for filename in ("run.json", "handoff.json", "prepare-pending.json"):
                path = root / filename
                if path.is_symlink():
                    raise ValueError("unsafe legacy record")
                if not path.exists():
                    continue
                record = _read(path)
                if record.get("schemaVersion") != 1:
                    raise ValueError("unbound legacy record")
                targets = None
                target_url = _job_identity(job_url, allow_generic=True)[1]
                if filename == "run.json" and "applications_root" not in record:
                    targets = _legacy_run_targets(applications, record)
                elif record.get("applications_root") != str(applications.root):
                    raise ValueError("unbound legacy record")
                if filename == "prepare-pending.json":
                    identifiers = record.get("application_ids")
                    if (
                        not re.fullmatch(r"[a-f0-9]{32}", record.get("batch_id", ""))
                        or not isinstance(identifiers, list)
                        or not 1 <= len(identifiers) <= 20
                        or any(not isinstance(value, str) or not value for value in identifiers)
                    ):
                        raise ValueError("invalid pending preparation")
                    active = application_id in identifiers
                else:
                    if filename == "run.json" and record.get("control") not in {
                        "paused",
                        "running",
                        "cancelled",
                    }:
                        raise ValueError("invalid legacy control")
                    rows = record.get("jobs" if filename == "run.json" else "tasks")
                    if not isinstance(rows, list):
                        raise ValueError("invalid legacy records")
                    active = False
                    for index, row in enumerate(rows):
                        if (
                            not isinstance(row, dict)
                            or not isinstance(row.get("application_id"), str)
                            or not isinstance(row.get("job_url"), str)
                        ):
                            raise ValueError("unbound legacy target")
                        row_target = (
                            targets[index]
                            if targets is not None
                            else _job_identity(row["job_url"], allow_generic=True)[1]
                        )
                        if filename == "run.json":
                            if (
                                row.get("status")
                                not in {
                                    "queued",
                                    "filling",
                                    "needs_input",
                                    "needs_recheck",
                                    "ready_for_review",
                                    "cancelled",
                                }
                                or not isinstance(row.get("page_open"), bool)
                                or "intent" not in row
                            ):
                                raise ValueError("invalid legacy job")
                            pending = (
                                row["status"] != "cancelled"
                                or row["page_open"]
                                or row["intent"] is not None
                            )
                        else:
                            if not isinstance(row.get("active"), bool):
                                raise ValueError("invalid legacy handoff")
                            pending = (
                                row["active"]
                                or row.get("release_pending")
                                or row.get("reservation_pending")
                                or row.get("pending_sync")
                            )
                        if pending and (
                            row["application_id"] == application_id or row_target == target_url
                        ):
                            active = True
                if active:
                    raise PortalDataError(
                        "single_legacy_active",
                        "原岗位有未完成任务、页面或准备记录，请先核验。",
                        409,
                    )
    except PortalDataError:
        raise
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as error:
        raise PortalDataError(
            "single_legacy_invalid", "旧执行记录不能核验，请保留原件后检查。", 409
        ) from error


def _material_information_inputs(app, task, information_library_root):
    """Read only current material contact facts, including historical-binding guards."""
    expected = {}
    if "information_library_revision" in task["inputs"]:
        from .application_information import (
            material_information_library,
            read_information_library,
        )

        declared = task["inputs"].get("information_library_root")
        if (
            information_library_root is not None
            and declared is not None
            and str(information_library_root) != declared
        ):
            raise ValueError("information library root changed")
        selected = information_library_root if information_library_root is not None else declared
        expected["information_library_revision"] = material_information_library(
            app, read_information_library(Path(selected) if selected is not None else None)
        )["revision"]
        if "information_library_root" in task["inputs"]:
            expected["information_library_root"] = str(selected) if selected is not None else None
    else:
        from .application_information import (
            CONTACT_FACTS,
            applicable_answers,
            material_information_context,
            read_information_library,
        )

        library = read_information_library(information_library_root)
        current_contacts = {
            fact: applicable_answers(
                library.get("records", []), fact, material_information_context(app)
            )
            for fact in CONTACT_FACTS
        }
        if library.get("status") == "unavailable":
            raise ValueError("historical contact sources unavailable")
        if any(current_contacts.values()):
            # Unbound historical content cannot establish that a new job-specific
            # contact correction was already present. Preserve its bytes but wait
            # before another transmission rather than silently adopting new facts.
            raise ValueError("historical materials lack current contact binding")
    return expected


def verify_material_lineage(
    applications,
    flow_root: Path,
    career_root: Path,
    task: dict,
    *,
    resume_store=None,
    analysis_adapter="default",
    pdf_sha256=None,
    information_library_root=None,
) -> dict:
    """Read saved analysis and adopted material bytes; never write or run a provider."""
    from .application_flow import local_materials
    from .application_input_binding import analysis_input_binding, job_input_revision
    from .application_match import POLICY_VERSION
    from .validation.hashing import record_digest as digest

    try:
        root = Path(flow_root)
        app = applications.get_application(task["application_id"])
        pdf_sha256 = task["resume_sha256"] if pdf_sha256 is None else pdf_sha256
        # Delivered material is bound to its saved inputs and adopted artifacts.
        # P03's read snapshot is distinct from the complete input directory.
        delivered = local_materials(task)
        expected = (
            task["inputs"]
            if delivered
            else {
                "jd_revision": job_input_revision(app),
                # Library revisions are provenance, not freshness (APP-04, 2026-11-01).
                "sources_revision": task["inputs"]["sources_revision"],
                # Completed adopted bytes retain the exact configurations recorded at adoption.
                **{
                    key: task["inputs"][key]
                    for key in (
                        "analysis_configuration_revision",
                        "resume_configuration_revision",
                        "historical_benchmark_revision",
                    )
                },
                **_material_information_inputs(app, task, information_library_root),
                **{
                    key: task["inputs"][key]
                    for key in ("information_library_revision",)
                    if key in task["inputs"]
                },
            }
        )
        if task["inputs"] != expected:
            raise ValueError("inputs changed")
        analysis_id, resume_id = task["analysis_id"], task["resume_id"]
        if any(not re.fullmatch(r"[a-f0-9]{32}", value) for value in (analysis_id, resume_id)):
            raise ValueError("invalid version")
        report = _read(root / "analyses" / analysis_id / "analysis.json")
        artifact = next(
            row
            for row in reversed(task["artifacts"])
            if row.get("stage") == "analysis"
            and row.get("adopted") is True
            and row["result"].get("id") == analysis_id
        )
        if any(artifact["result"].get(key) != value for key, value in report.items()) or (
            analysis_input_binding(artifact["inputs"]) != analysis_input_binding(expected)
        ):
            raise ValueError("analysis changed")
        if (
            report.get("id") != analysis_id
            or report.get("application_id") != task["application_id"]
            or report.get("jd_revision") != task["job_binding"]
            or (
                report.get("input_source_snapshot_revision", report.get("source_snapshot_revision"))
                if delivered
                else report.get("source_snapshot_revision")
            )
            != expected["sources_revision"]
            or not delivered
            and not same_revision(
                expected["analysis_configuration_revision"],
                bound_revision(
                    {"engine": report.get("configuration_revision"), "adapter": analysis_adapter}
                ),
            )
            or not delivered
            and report.get("policy_version") != POLICY_VERSION
        ):
            raise ValueError("analysis not current")
        analysis_binding = {
            "analysis_id": analysis_id,
            **{
                key: report[key]
                for key in (
                    "jd_revision",
                    "source_snapshot_revision",
                    "configuration_revision",
                    "policy_version",
                )
            },
        }
        if task.get("pdf_reuse"):
            from .application_pdf_reuse import verify_reuse
            from .application_resume import ApplicationResumeStore

            resume_root = root / "resumes"
            if not resume_root.is_dir() or any(
                part.is_symlink() for part in (resume_root, *resume_root.parents)
            ):
                raise ValueError("unsafe reuse root")
            store = resume_store or ApplicationResumeStore(
                applications, CareerCatalog(Path(career_root)), resume_root
            )
            if store.root != resume_root:
                raise ValueError("different reuse store")
            reused = _read(resume_root / resume_id / "reuse.json")
            adopted = next(
                row
                for row in reversed(task["artifacts"])
                if row.get("stage") == "resume"
                and row.get("adopted") is True
                and row["result"].get("id") == resume_id
            )
            if (
                adopted.get("result") != reused
                or adopted.get("inputs") != expected
                or reused.get("reuse_binding") != task["pdf_reuse"]
                or reused.get("pdf_sha256") != task["resume_sha256"]
                or reused.get("pdf_sha256") != pdf_sha256
            ):
                raise ValueError("reused PDF not adopted")
            verify_reuse(
                store, task, reused, assemble(root, _read(root / "flow.json"), read=_read)["tasks"]
            )
            return reused
        if task.get("automatic_materials") is True:
            from .application_resume import ApplicationResumeStore

            resume_root = root / "resumes"
            if not resume_root.is_dir() or any(
                part.is_symlink() for part in (resume_root, *resume_root.parents)
            ):
                raise ValueError("unsafe export root")
            store = resume_store or ApplicationResumeStore(
                applications, CareerCatalog(Path(career_root)), resume_root
            )
            if store.root != resume_root:
                raise ValueError("different export store")
            saved = store.read_export(resume_id)
            saved_draft = store.draft(task["draft_id"])
            export_artifact = next(
                row
                for row in reversed(task["artifacts"])
                if row.get("stage") == "export"
                and row.get("adopted") is True
                and row["result"].get("id") == resume_id
            )
            draft_artifact = next(
                row
                for row in reversed(task["artifacts"])
                if row.get("stage") == "resume"
                and row.get("adopted") is True
                and row["result"].get("id") == task["draft_id"]
            )
            binding = task.get("material_binding") or {}
            if (
                task["stages"].get("export", {}).get("status") != "complete"
                or task["stages"]["export"].get("artifact_id") != resume_id
                or task["stages"]["export"].get("attempt_id") != resume_id
                or saved.get("automatic_materials") is not True
                or (
                    saved.get("origin", saved_draft.get("origin"))
                    if delivered
                    else saved.get("origin")
                )
                not in ({"generated_latex", "existing_latex"} if delivered else {"generated_latex"})
                or (
                    saved.get("analysis_binding", saved_draft.get("analysis_binding"))
                    if delivered
                    else saved.get("analysis_binding")
                )
                != (saved_draft.get("analysis_binding") if delivered else analysis_binding)
                or saved.get("task_inputs") != expected
                or saved.get("application_id") != task["application_id"]
                or saved.get("draft_id") != task.get("draft_id")
                or saved.get("draft_sha256") != task.get("draft_sha256")
                or saved.get("pdf_sha256") != task["resume_sha256"]
                or saved.get("pdf_sha256") != pdf_sha256
                or saved.get("resume_configuration_revision")
                != expected["resume_configuration_revision"]
                or export_artifact.get("inputs") != expected
                or draft_artifact.get("inputs") != expected
                or any(
                    export_artifact["result"].get(key) != value
                    for key, value in saved.items()
                    if key not in READ_TIME_RESULT_KEYS
                )
                or any(
                    not same_revision(draft_artifact["result"].get(key), value)
                    if key == "resume_configuration_revision"
                    else draft_artifact["result"].get(key) != value
                    for key, value in saved_draft.items()
                    if key not in READ_TIME_RESULT_KEYS
                )
                or binding.get("actor") != "system"
                or binding.get("human_reviewed") is not False
                or binding.get("scope") != "current_pdf_materials"
                or binding.get("resume_id") != resume_id
                or binding.get("pdf_sha256") != pdf_sha256
                or binding.get("input_revision") != digest(expected)
                or binding.get("draft_id") != task["draft_id"]
                or binding.get("draft_sha256") != task["draft_sha256"]
            ):
                raise ValueError("automatic export not adopted")
            return saved
        draft = _read(root / "resumes" / resume_id / "sources.json")
        resume_artifact = next(
            row
            for row in reversed(task["artifacts"])
            if row.get("stage") == "resume"
            and row.get("adopted") is True
            and row["result"].get("id") == resume_id
        )
        if (
            resume_artifact.get("inputs") != expected
            or resume_artifact["result"].get("analysis_binding") != analysis_binding
            or resume_artifact["result"].get("pdf_sha256") != task["resume_sha256"]
            or resume_artifact["result"].get("application_id") != task["application_id"]
        ):
            raise ValueError("resume not adopted")
        pdf = root / "resumes" / resume_id / "resume.pdf"
        if any(part.is_symlink() for part in (pdf, *pdf.parents)):
            raise ValueError("unsafe PDF")
        raw = pdf.read_bytes()
        sha = hashlib.sha256(raw).hexdigest()
        if (
            draft.get("application_id") != task["application_id"]
            or draft.get("analysis_binding") != analysis_binding
            or not task_configuration_current(
                expected["resume_configuration_revision"], draft.get("generation_policy")
            )
            or not 1 <= len(raw) <= 700_000
            or not raw.startswith(b"%PDF-")
            or draft.get("pdf_sha256") != sha
            or task["resume_sha256"] != sha
            or pdf_sha256 != sha
        ):
            raise ValueError("PDF binding changed")
        return resume_artifact["result"]
    except PortalDataError:
        raise
    except (OSError, ValueError, KeyError, TypeError, AttributeError, StopIteration) as error:
        raise PortalDataError(
            "single_binding_invalid", "单岗位材料来源已改变，请保留原件并核验。", 409
        ) from error


def check_single_qualification(task, application, information_root, country):
    """Validate qualification and report whether an adopted fixed delivery owns it."""
    from .application_eligibility import task_eligibility
    from .application_explanations import adopted_analysis, qualification_for
    from .application_information import (
        information_context,
        read_information_library,
        validate_information_references,
    )
    from .application_job_brief import validate_job_brief
    from .application_writing import is_fixed_delivery

    # A task's declared library is authoritative. Never combine it with legacy answers.
    selected_root = (task.get("inputs") or {}).get("information_library_root") or information_root
    library = read_information_library(Path(selected_root) if selected_root is not None else None)
    scoped = application | {"country": country}
    analysis = adopted_analysis(task) or {}
    fixed = is_fixed_delivery(analysis)
    declared_fixed = any(
        key in analysis for key in ("job_brief", "material_packet", "inference_result")
    ) or (
        task.get("material_contract") in {"fixed-writing/v1", "content-writing/v1"}
        or (task.get("experience_handoff") or {}).get("generation_contract")
        in {"fixed-writing/v1", "content-writing/v1"}
    )
    if declared_fixed and not fixed:
        raise PortalDataError(
            "single_binding_invalid", "已声明的固定岗位交付不完整，请保留原资料核验。", 409
        )
    if fixed:
        validate_job_brief(analysis["job_brief"])
        # Validate only citations actually used by P04. An unrelated fact may change
        # the full context hash without changing this delivery's cited facts.
        references = []
        for requirement in analysis.get("requirements", []):
            support = requirement.get("information_support") or {}
            references.extend(support.get("references", []))
            for source in requirement.get("sources", []):
                references.extend((source.get("confirmed_information") or {}).get("references", []))
        if references:
            try:
                validate_information_references(information_context(scoped, library), references)
            except PortalDataError as error:
                raise PortalDataError(
                    "single_eligibility_required",
                    "岗位分析引用的确认事实已变更、冲突或失效，请先核对。",
                    409,
                ) from error
    current_qualification = qualification_for(task, scoped, library)
    if (
        task_eligibility(task)["status"] not in {"supported", "not_specified", "needs_input"}
        or current_qualification["status"] == "conflict"
    ):
        raise PortalDataError("single_eligibility_required", "请先核对岗位硬条件与必要资格。", 409)
    return fixed


def check_single_binding(
    applications,
    flow_root: Path,
    career_root: Path,
    job: dict,
    batch_id: str,
    *,
    allow_unbound: bool = False,
    legacy_roots=(),
    worker_root=None,
    material_required=True,
) -> bool:
    """Verify saved local material bindings or legacy current inputs, without writes."""
    # Lazy imports preserve the existing flow -> worker -> resume dependency order.
    from .application_automation import _job_identity
    from .application_execution import automated_owner
    from .application_flow import local_materials
    from .application_input_binding import job_input_revision
    from .validation.hashing import record_digest as digest

    try:
        root = Path(flow_root)
        binding = job["single_binding"]
        if (
            not isinstance(binding, dict)
            or binding.get("schemaVersion") != 1
            or not re.fullmatch(r"[a-f0-9]{32}", binding.get("task_id", ""))
            or binding.get("country") != job["country"]
            or binding.get("send_confirmed") is not True
            or job.get("send_confirmed") is not True
            or _job_identity(binding.get("job_url"), allow_generic=True)[1] != job["job_url"]
        ):
            raise ValueError("invalid binding")
        state = assemble(root, _read(root / "flow.json"), read=_read)
        if state.get("schemaVersion") != 1 or state.get("applications_root") != str(
            applications.root
        ):
            raise ValueError("unbound flow")
        task = next(task for task in state["tasks"] if task["id"] == binding["task_id"])
        if task["revision"] != digest(
            {key: value for key, value in task.items() if key != "revision"}
        ):
            raise ValueError("changed task")
        update = task.get("material_update") or {}
        if update and update.get("status") not in {"bound", "complete"}:
            raise ValueError("material update is paused or its local journal is incomplete")
        if update.get("status") == "bound":
            journal = _read(root / "material-updates" / (update["id"] + ".json"))
            if (
                journal.get("status") != "bound"
                or journal.get("id") != update["id"]
                or journal.get("revision")
                != digest({k: v for k, v in journal.items() if k != "revision"})
                or (job.get("material_update") or {}).get("id") != update["id"]
            ):
                raise ValueError("material update journal is incomplete")
        if (
            task["application_id"] != job["application_id"]
            or task["materials_confirmed"] is not True
        ):
            raise ValueError("unconfirmed materials")
        if task["status"] not in {
            "materials_ready",
            "queued",
            "filling",
            "needs_input",
            "needs_recheck",
            "ready_for_review",
        }:
            raise ValueError("inactive task")
        for key in ("job_binding", "inputs", "analysis_id", "resume_id", "resume_sha256"):
            if binding.get(key) != task[key]:
                raise ValueError("stale binding")
        if binding.get("hard_condition_resolutions", []) != task.get(
            "hard_condition_resolutions", []
        ):
            raise ValueError("eligibility changed")
        approval = task.get("send_approval", {})
        if (
            not valid_send_approval(task, root)
            or approval.get("country") != job["country"]
            or _job_identity(approval.get("job_url"), allow_generic=True)[1] != job["job_url"]
            or any(
                approval.get(key) != task[key]
                for key in ("analysis_id", "resume_id", "resume_sha256", "inputs")
            )
        ):
            raise ValueError("send approval changed")
        reference = task.get("worker_ref")
        if allow_unbound:
            if reference is not None:
                raise ValueError("worker already bound")
        elif (
            not isinstance(reference, dict)
            or reference.get("batch_id") != batch_id
            or reference.get("job_id") != job["application_id"]
        ):
            raise ValueError("worker not bound")
        app = applications.get_application(job["application_id"])
        if (
            not local_materials(task)
            and job_input_revision(app) != task["job_binding"]
            or _job_identity(app["url"], allow_generic=True)[1] != job["job_url"]
        ):
            raise ValueError("job changed")
        current_owner = (
            automated_owner(worker_root, batch_id, job["application_id"])
            if worker_root is not None and not allow_unbound
            else None
        )
        if allow_unbound and worker_root is not None and (Path(worker_root) / "run.json").exists():
            published = _read(Path(worker_root) / "run.json")
            published_jobs = published.get("jobs", [])
            expected_context = {
                "applications_root": str(applications.root),
                "flow_root": str(flow_root),
                "career_root": str(career_root),
                "legacy_roots": [str(path) for path in legacy_roots],
            }
            if (
                published.get("schemaVersion") == 1
                and published.get("applications_root") == str(applications.root)
                and published.get("batch_id") == batch_id
                and published.get("control") == "paused"
                and published.get("single_context") == expected_context
                and published.get("worker_pid") is None
                and len(published_jobs) == 1
                and published_jobs[0].get("application_id") == job["application_id"]
                and published_jobs[0].get("single_binding") == binding
                and published_jobs[0].get("status") == "queued"
                and published_jobs[0].get("page_open") is False
                and published_jobs[0].get("intent") is None
                and published_jobs[0].get("file_sha256") == job["file_sha256"]
            ):
                current_owner = automated_owner(worker_root, batch_id, job["application_id"])
        check_legacy_roots(
            applications,
            legacy_roots,
            job["application_id"],
            job["job_url"],
            current_root=worker_root,
            current_owner=current_owner,
        )
        information_root = (
            Path(task["inputs"]["information_library_root"])
            if task["inputs"].get("information_library_root")
            else Path(worker_root) / "answer-library"
            if worker_root is not None
            else None
        )
        if material_required:
            verify_material_lineage(
                applications,
                flow_root,
                career_root,
                task,
                pdf_sha256=job["file_sha256"],
                information_library_root=information_root,
            )
        # A contact correction no longer pauses sending the adopted PDF (APP-04,
        # 2026-11-01); the user regenerates materials explicitly when wanted.
        return check_single_qualification(task, app, information_root, job["country"])
    except PortalDataError:
        raise
    except (OSError, ValueError, KeyError, TypeError, AttributeError, StopIteration) as error:
        raise PortalDataError(
            "single_binding_invalid", "单岗位材料或执行绑定已改变，请保留原页面并核验。", 409
        ) from error


def read_delivered_material_inputs(applications, flow_root, job, *, delivery_reader=None):
    """Read the adopted P04 job and source archive, without current career-library access.

    The live composition can also resolve its existing writing handoff. A separately
    launched worker uses the same checksummed task, analysis and source archives.
    """
    from .application_input_binding import analysis_input_binding
    from .application_job_brief import validate_job_brief
    from .validation.hashing import record_digest as digest

    try:
        root = Path(flow_root)
        binding = job["single_binding"]
        flow = assemble(root, _read(root / "flow.json"), read=_read)
        if flow.get("schemaVersion") != 1 or flow.get("applications_root") != str(
            applications.root
        ):
            raise ValueError("unbound flow")
        task = next(row for row in flow["tasks"] if row["id"] == binding["task_id"])
        if (
            task.get("revision") != digest({k: v for k, v in task.items() if k != "revision"})
            or task.get("application_id") != job["application_id"]
            or any(
                binding.get(k) != task.get(k)
                for k in ("job_binding", "inputs", "analysis_id", "resume_id", "resume_sha256")
            )
        ):
            raise ValueError("changed task binding")
        analysis_id = task["analysis_id"]
        if not isinstance(analysis_id, str) or re.fullmatch(r"[a-f0-9]{32}", analysis_id) is None:
            raise ValueError("invalid analysis id")
        adopted = next(
            row
            for row in reversed(task["artifacts"])
            if row.get("stage") == "analysis"
            and row.get("adopted") is True
            and row.get("result", {}).get("id") == analysis_id
        )
        directory = root / "analyses" / analysis_id
        analysis = _read(directory / "analysis.json")
        if (
            any(adopted["result"].get(k) != v for k, v in analysis.items())
            or analysis.get("id") != analysis_id
            or analysis.get("application_id") != task["application_id"]
            or analysis.get("jd_revision") != task["job_binding"]
            or analysis.get(
                "input_source_snapshot_revision", analysis.get("source_snapshot_revision")
            )
            != task["inputs"]["sources_revision"]
            or analysis_input_binding(adopted["inputs"]) != analysis_input_binding(task["inputs"])
        ):
            raise ValueError("changed adopted analysis")
        brief = validate_job_brief(analysis["job_brief"])
        if not all(
            isinstance(analysis.get(k), dict) for k in ("material_packet", "inference_result")
        ):
            raise ValueError("missing fixed delivery")
        if delivery_reader is not None:
            delivery = delivery_reader(task)
            if not isinstance(delivery, dict) or delivery.get("analysis") != adopted["result"]:
                raise ValueError("different fixed delivery")
        sources = _read(directory / "source-snapshot.json")
        if (
            sources.get("revision") != analysis.get("source_snapshot_revision")
            or sources.get("revision")
            != digest({k: v for k, v in sources.items() if k != "revision"})
            or not isinstance(sources.get("items"), list)
        ):
            raise ValueError("changed delivered sources")
        result = {"application": {"id": task["application_id"], **brief["job"]}, "sources": sources}
        from .application_cover_letter import letter_branch

        letter = letter_branch(task)
        if letter is not None:
            # Material consumers read the letter stage and its adopted row as one branch.
            result["cover_letter"] = letter
            result["material_packet"] = deepcopy(analysis["material_packet"])
            if "material_consistency" in task:
                result["material_consistency"] = deepcopy(task["material_consistency"])
        return result
    except (OSError, ValueError, KeyError, TypeError, StopIteration, PortalDataError) as error:
        raise PortalDataError(
            "single_material_sources_invalid",
            "本岗位已采用的资料交付不能核验，请保留原稿并恢复固定交付。",
            409,
        ) from error


# The target one write preflight selected, for its own Worker preparation call only.
_PREPARATION_TARGET = ContextVar("application_preparation_target", default=None)


def preflight_target(applications, worker, application):
    """The preflight-selected target, else a fresh target check for this application."""
    selected = _PREPARATION_TARGET.get()
    return (
        deepcopy(selected["target"])
        if selected
        else validate_application_target(
            applications, application["id"], application["revision"], allow_generic=worker.generic
        )
    )


@contextmanager
def write_preflight(
    flow,
    stage,
    task_id=None,
    task_revision=None,
    *,
    worker=None,
    career_root=None,
    legacy_roots=(),
    resumes=None,
    **request,
):
    """Check the current job, materials and Worker before preparing its filling."""
    if stage != "prepare" or worker is None:
        yield
        return
    from .application_execution import automated_owner
    from .application_flow import stat_tokens

    applications = flow.applications
    # Duplicate scanning must not starve the current worker's application lock.
    task = flow.read_checked_task(task_id, task_revision)
    application = applications.get_application(task["application_id"])
    scanned_applications = stat_tokens(applications._paths())
    target = validate_application_target(
        applications, application["id"], application["revision"], allow_generic=worker.generic
    )
    with applications.write_lock():
        task = flow.writable_task(task_id, task_revision)
        current = flow.check_inputs_current(task)
        if current["revision"] != target["revision"]:
            raise PortalDataError("conflict", "当前岗位在准备期间已变化，请保留原进度。", 409)
        if scanned_applications != stat_tokens(applications._paths()):
            raise PortalDataError("conflict", "投递记录在准备期间已变化，请重新核对目标。", 409)
        country = request.get("country")
        verifier = flow.callbacks.get("verify_materials")
        if task.get("materials_confirmed") and verifier:
            verifier(deepcopy(task))
        verify_material_lineage(
            applications,
            flow.root,
            career_root,
            task,
            resume_store=resumes,
            analysis_adapter=flow.analysis.adapter_revision,
            information_library_root=flow.information_library_root,
        )
        try:
            fixed_qualification = check_single_qualification(
                task,
                current,
                flow.information_library_root or worker.store.root / "answer-library",
                country,
            )
        except PortalDataError as error:
            if error.code != "single_eligibility_required":
                raise
            raise PortalDataError(
                "flow_eligibility_required", "资格存在冲突或评估尚未取得，不能启动填写。", 409
            ) from error
        if not fixed_qualification:
            worker.store.check_language_requirement(current, country=country)
        if worker.store.stop_reason():
            raise PortalDataError("checkpoint_unavailable", "填写记录保存失败，请先核验。", 409)
        state = worker.store.load()
        worker.store.check_generic_enabled({"platform": target["platform"]}, state)
        pending = worker.store.root / "prepare-pending.json"
        if pending.exists() or pending.is_symlink():
            raise PortalDataError("prepare_needs_recheck", "原准备结果尚未核验，请保留记录。", 409)
        matching = next(
            (
                row
                for row in state["jobs"]
                if row.get("workflow") == "single"
                and (row.get("single_binding") or {}).get("task_id") == task["id"]
            ),
            None,
        )
        if matching is None:
            worker.check_new_current_job(state)
        elif any(
            row.get("status") != "cancelled" or row.get("page_open") or row.get("intent")
            for row in state["jobs"]
        ):
            if (
                matching is None
                or state["control"] != "paused"
                or matching["status"] != "queued"
                or matching.get("page_open")
                or matching.get("intent")
                or matching.get("handed_off")
                or matching.get("country") != country
            ):
                raise PortalDataError("flow_worker_mismatch", "已有原页或执行进度，请先核验。", 409)
            worker.store.check_single(matching, state, allow_unbound=not task.get("worker_ref"))
            if (
                hashlib.sha256(Path(matching["file_path"]).read_bytes()).hexdigest()
                != matching["file_sha256"]
            ):
                raise PortalDataError("file_changed", "已选附件已变化，请保留原材料并核验。", 409)
        check_legacy_roots(
            applications,
            legacy_roots,
            task["application_id"],
            current["url"],
            current_root=worker.store.root,
            current_owner=automated_owner(
                worker.store.root, state["batch_id"], task["application_id"]
            )
            if matching
            else None,
        )
        token = _PREPARATION_TARGET.set({"task_id": task_id, "target": target, "country": country})
        try:
            yield
        finally:
            _PREPARATION_TARGET.reset(token)


def validate_write_preflight(flow, stage):
    """Re-read the target selected by the active write preflight, if any."""
    selected = _PREPARATION_TARGET.get()
    if stage != "prepare" or not selected:
        return False
    with flow.applications.write_lock():
        _, task = flow.witness(selected["task_id"])
        application = flow.applications.get_application(task["application_id"])
        if application["revision"] != selected["target"]["revision"]:
            raise PortalDataError("conflict", "当前岗位在准备期间已变化，请保留原进度。", 409)
        return {
            "task": task,
            "target": deepcopy(selected["target"]),
            "country": selected["country"],
        }
