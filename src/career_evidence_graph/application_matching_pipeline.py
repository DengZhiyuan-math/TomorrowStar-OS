"""Normal requirement-driven evidence reads with separate material and match bindings."""

from __future__ import annotations

import hashlib
import os
from copy import deepcopy
from pathlib import Path
from uuid import uuid4

from ._vendor import job_apply_store as helper
from .application_information import (
    information_source_snapshot,
    validate_information_source,
)
from .application_input_binding import same_configuration
from .application_job_brief import (
    brief_requirements,
    create_job_brief,
    validate_job_brief,
)
from .application_match_scoring import route_for_score
from .application_retrieval import plan_retrieval
from .application_storage import private_root
from .career_portal_data import PortalDataError
from .validation.hashing import record_digest as digest

ENGINE_SHA256 = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()


def _read_saved(path):
    if ".." in path.parts or any(part.is_symlink() for part in (path, *path.parents)):
        raise PortalDataError("match_resume_invalid", "原分析恢复记录不可用。", 409)
    try:
        return helper.read_json_object(path, "analysis recovery")
    except (OSError, ValueError) as error:
        raise PortalDataError("match_resume_invalid", "原分析恢复记录不能核验。", 409) from error


def known_reading_failure(directory, saved):
    """The saved reading phase ended in a proven size refusal, not an unknown call."""
    from .application_material_packet import known_budget_failure

    # A resumed attempt keeps its recovered reading origin but writes its own packet.
    number = saved.get("round_number")
    origin = directory / f"material-packet-{number}"
    return bool(
        saved.get("phase") == "reading"
        and type(number) is int
        and number > 0
        and not origin.is_symlink()
        and known_budget_failure(origin)
    )


def _answered_evaluation(saved):
    """The saved evaluation call returned a complete answer, accepted or rejected."""
    origin = saved.get("evaluation_origin")
    if saved.get("phase") not in {"evaluation", "evaluated"} or not isinstance(origin, str):
        return False
    try:
        result = _read_saved(Path(origin) / "model-result.json")
    except (PortalDataError, helper.StoreError):
        return False
    return result.get("status") != "failed" and result.get("exit_code") == 0


def _same_upstream_binding(saved, binding):
    previous = saved.get("binding")
    if previous == binding:
        return True
    if not isinstance(previous, dict):
        return False
    upstream_same = {k: v for k, v in previous.items() if k != "configuration"} == {
        k: v for k, v in binding.items() if k != "configuration"
    }
    # Engine and Codex executable fields are provenance (input binding Module):
    # an App rebuild or CLI update never decides whether saved phases are reusable.
    configuration_same = same_configuration(
        previous.get("configuration"), binding.get("configuration")
    )
    if (
        saved.get("phase") == "brief"
        and not saved.get("brief")
        and isinstance(saved.get("brief_origin"), str)
        and (Path(saved["brief_origin"]) / "validation-failure.json").is_file()
    ):
        # A rejected JD reading reuses nothing; its next call runs under the current
        # configuration, and the brief itself re-checks the recorded rejection.
        return upstream_same
    if (
        saved.get("phase") == "planning"
        and saved.get("planner_kind") == "followup"
        and saved.get("planner_pending") is True
    ):
        # A pending follow-up repair reuses accepted evaluations only after its
        # recorded planner failure is re-validated.
        return (
            upstream_same
            and configuration_same
            and (_known_invalid_followup(saved) or _recorded_failed_followup(saved))
        )
    if upstream_same and configuration_same:
        return True
    known_invalid_evaluation = saved.get("phase") == "evaluation" and saved.get(
        "evaluation_error"
    ) in {"match_model_invalid", "match_inference_invalid", "retrieval_execution_incomplete"}
    if (
        saved.get("phase") not in {"selected", "reading"}
        and not known_invalid_evaluation
        or saved.get("evaluations")
        or saved.get("evaluation_origin")
        and not known_invalid_evaluation
        or not isinstance(previous.get("configuration"), dict)
        or not upstream_same
    ):
        return False
    # No accepted evaluation is reused. Exact JD, facts, information and model
    # settings still bind upstream receipts after a pre-evaluation repair or a
    # known invalid evaluator output; unknown evaluator calls remain blocked.
    return same_configuration(
        {k: v for k, v in previous["configuration"].items() if k != "context_limits"},
        {k: v for k, v in binding["configuration"].items() if k != "context_limits"},
    )


def _recorded_failed_followup(saved):
    """The pending follow-up planner call ended in a failure this App recorded.

    2026-11-08, Keyrock: a follow-up page timed out; after an App rebuild only
    provenance differed, yet resumption required a validation-failure marker.
    """
    if not (
        saved.get("phase") == "planning"
        and saved.get("planner_kind") == "followup"
        and saved.get("planner_pending") is True
        and isinstance(saved.get("planner_origin"), str)
    ):
        return False
    pages = sorted(Path(saved["planner_origin"]).glob("page-*"))
    if not pages:
        return False
    try:
        result = _read_saved(pages[-1] / "result.json")
    except (PortalDataError, helper.StoreError):
        return False
    return result.get("status") == "failed" and result.get("error_type") in {
        "CodexCLIError",
        "TimeoutExpired",
        "OSError",
    }


def _known_invalid_followup(saved):
    """Only a complete, bound validation failure permits a planner repair."""
    from .codex_cli import CodexCLIError, output_validation_marker, validate_recorded_result

    if not (
        saved.get("phase") == "planning"
        and saved.get("planner_kind") == "followup"
        and saved.get("planner_pending") is True
        and saved.get("evaluations")
        and saved.get("evaluation_origin")
        and saved.get("evaluation_error") is None
        and isinstance(saved.get("planner_origin"), str)
    ):
        return False
    for marker_path in sorted(Path(saved["planner_origin"]).glob("page-*/validation-failure.json")):
        page = marker_path.parent
        marker = _read_saved(marker_path)
        prompt = _read_saved(page / "prompt.json")
        _read_saved(page / "schema.json")
        try:
            result = validate_recorded_result(
                _read_saved(page / "result.json"),
                prompt=prompt.get("prompt"),
                output_schema=page / "schema.json",
            )
        except (ValueError, CodexCLIError):
            return False
        return (
            isinstance(prompt.get("prompt"), str)
            and prompt.get("sha256") == digest(prompt["prompt"])
            and marker
            == output_validation_marker(
                result, prompt["prompt"], page / "schema.json", "retrieval_invalid"
            )
        )
    return False


def _resume_evaluation(
    application,
    evaluation,
    original,
    destination,
    runner,
    known_failure,
    on_dispatch,
    *,
    revalidate_recorded=False,
):
    """Adopt saved output first; an unacknowledged model call is never replayed."""
    from .application_match import _analyze_loaded_job, _known_failed_model_result, reuse_analysis
    from .codex_cli import CodexCLIError, validate_recorded_result
    from .validation.models import CodexCLIResult

    if (original / "analysis.json").exists():
        report = _read_saved(original / "analysis.json")
        # A follow-up repair re-validates the recorded response instead of adopting
        # the completed report, even when only provenance changed since.
        reused = (
            None
            if revalidate_recorded
            else reuse_analysis(application, evaluation, report, original, destination)
        )
        if reused is not None:
            return reused
        if not revalidate_recorded or _read_saved(original / "source-snapshot.json") != evaluation:
            raise PortalDataError("match_resume_invalid", "已完成评估输入不能核验。", 409)
    result_path = original / "model-result.json"
    if result_path.exists():
        result = _read_saved(result_path)
        inputs = _read_saved(original / "input.json")
        if (
            inputs.get("application_id") != application["id"]
            or inputs.get("job")
            != {
                key: application.get(key, "")
                for key in ("company", "role_title", "location", "job_description")
            }
            or _read_saved(original / "source-snapshot.json") != evaluation
            or inputs.get("source_snapshot_revision") != evaluation.get("revision")
        ):
            raise PortalDataError("match_resume_invalid", "原评估调用输入不能核验。", 409)
        if result.get("status") == "failed":
            if not _known_failed_model_result(original, result):
                raise PortalDataError(
                    "match_result_needs_recheck",
                    "原评估调用结果未明，请先核对，未重复模型请求。",
                    409,
                )
        else:
            try:
                saved = validate_recorded_result(
                    CodexCLIResult.model_validate(result),
                    prompt=_read_saved(original / "context-input.json")["prompt"],
                    output_schema=original / "match-schema.json",
                )
            except (ValueError, CodexCLIError) as error:
                raise PortalDataError(
                    "match_resume_invalid", "原模型响应不能核验。", 409
                ) from error

            if known_failure:
                on_dispatch()
                return _analyze_loaded_job(application, evaluation, destination, runner=runner)

            def recorded(config, prompt, **kwargs):
                try:
                    return validate_recorded_result(
                        saved, prompt=prompt, output_schema=config.output_schema
                    )
                except CodexCLIError as error:
                    raise PortalDataError(
                        "match_resume_invalid", "原模型响应与输入不符。", 409
                    ) from error

            report = _analyze_loaded_job(application, evaluation, destination, runner=recorded)
            if revalidate_recorded:
                helper.atomic_write_json(
                    destination / "recorded-response-revalidation.json",
                    {
                        "schema_version": "recorded-evaluation-revalidation/v1",
                        "original_directory": str(original),
                        "result_revision": digest(saved.model_dump(mode="json")),
                        "model_called": False,
                    },
                )
            return report
    elif any(
        (original / name).exists() or (original / name).is_symlink()
        for name in ("context-input.json", "match-schema.json")
    ):
        raise PortalDataError(
            "match_result_needs_recheck", "原评估调用结果未明，请先核对，未重复模型请求。", 409
        )
    # No prompt was saved, so no evaluation call went out (2026-11-08: UBS's
    # context-size refusal); a new call is the first one.
    on_dispatch()
    return _analyze_loaded_job(application, evaluation, destination, runner=runner)


def _required(rows):
    return [
        {
            key: deepcopy(row[key])
            for key in ("text", "importance", "hard_condition", "scoring_framework")
            if key in row
        }
        for row in rows
    ]


def _bind_information(application, library, requirements):
    for requirement in requirements:
        confirmed = [s for s in requirement["sources"] if s.get("confirmed_information")]
        references = []
        for source in confirmed:
            validate_information_source(application, library, source)
            for ref in source["confirmed_information"]["references"]:
                if ref not in references:
                    references.append(ref)
        if references:
            requirement["information_support"] = {
                "fact": "confirmed_information",
                "status": "supported" if requirement["judgment"] == "supported" else "needs_input",
                "references": references,
                "explanation": requirement["explanation"],
            }


def _read_complete(snapshot, directory, phase):
    library = snapshot.get("career_library", {})
    failures = library.get("unavailable_sources", [])
    if library.get("status") == "unavailable" or failures:
        helper.atomic_write_json(
            directory / "retrieval-execution.json",
            {"status": "execution_incomplete", "phase": phase, "failures": failures},
        )
        raise PortalDataError(
            "retrieval_execution_incomplete", "必要资料尚未完整读取，未生成匹配分。", 409
        )


def _discovery_with_bodies(snapshot, source_loader, directory):
    """A failed or title-only index is a read lead, never a negative relevance verdict."""
    result = deepcopy(snapshot)
    records = result["career_library"]["records"]
    fallback = [row["candidate_id"] for row in records if row.get("requires_body_discovery")]
    if not fallback:
        return result
    bodies = source_loader(fallback)
    _read_complete(bodies, directory, "index_body_fallback")
    if bodies.get("career_library", {}).get("records") != snapshot["career_library"]["records"]:
        raise PortalDataError("match_sources_changed", "目录回退读取期间来源已变化。", 409)
    for record in records:
        if record["candidate_id"] not in fallback:
            continue
        sources = [
            item
            for item in bodies["items"]
            if item.get("candidate_id") == record["candidate_id"]
            and not item.get("locator", "").startswith("/records/")
        ]
        if not sources:
            helper.atomic_write_json(
                directory / "retrieval-execution.json",
                {
                    "status": "execution_incomplete",
                    "phase": "index_body_fallback",
                    "candidate_id": record["candidate_id"],
                },
            )
            raise PortalDataError(
                "retrieval_execution_incomplete", "目录缺少可读取正文，未判为不相关。", 409
            )
        record["body_discovery"] = [
            {key: item[key] for key in ("source_id", "source_revision", "text")} for item in sources
        ]
        record["discovery_status"] = "body_fallback_read"
    result.pop("revision", None)
    result["revision"] = digest(result)
    helper.atomic_write_json(
        directory / "index-body-fallback.json",
        {
            "status": "complete",
            "candidate_ids": fallback,
            "source_snapshot_revision": bodies["revision"],
        },
    )
    return result


def _whole_library_plan(application, binding_snapshot, source_loader, library, stable):
    """Select every experience when the whole library fits one matching call."""
    from .application_input_limits import context_limits
    from .application_material_packet import packet_size
    from .application_material_sources import source_records

    records = binding_snapshot["career_library"]["records"]
    every = [row["candidate_id"] for row in records]
    whole = information_source_snapshot(application, library, source_loader(every))
    for item in whole["items"]:
        item["application_trusted"] = True
    if packet_size(source_records(whole)) > context_limits()["material_context_bytes"]:
        return None
    return {
        "policy_version": "whole-library/v1",
        "status": "complete",
        "requirements": stable,
        "selected_candidate_ids": every,
        "coverage": {"total_records": len(records), "mode": "whole_library"},
    }


def analyze_with_retrieval(
    application,
    binding_snapshot,
    directory,
    *,
    runner,
    source_loader,
    information_library,
    requirements=None,
    matching_only=False,
    job_brief=None,
    resume_from=None,
):
    from .application_match import _analyze_loaded_job, match_configuration

    directory = Path(directory).expanduser()
    try:
        directory = private_root(directory.parent) / directory.name
        directory.mkdir(mode=0o700)
    except (ValueError, OSError) as error:
        raise PortalDataError(
            "match_directory_exists", "分析目录须为新的私有目录。", 409
        ) from error
    if binding_snapshot.get("revision") != digest(
        {k: v for k, v in binding_snapshot.items() if k != "revision"}
    ):
        raise PortalDataError("match_snapshot_invalid", "分析输入版本不能核验。", 409)
    _read_complete(binding_snapshot, directory, "directory")
    library = information_library or {"status": "unconfigured", "records": []}
    discovery = information_source_snapshot(application, library, binding_snapshot)
    canonical = bool(binding_snapshot.get("career_library", {}).get("canonical_sources"))
    if canonical and not callable(source_loader):
        raise PortalDataError(
            "retrieval_loader_missing", "完整经历目录尚未连接正式来源读取器。", 409
        )
    environment = dict(os.environ)
    binding = {
        "application_id": application["id"],
        "job": {
            key: application.get(key, "")
            for key in ("company", "role_title", "location", "job_description")
        },
        "sources_revision": binding_snapshot["revision"],
        "configuration": match_configuration(environment),
        "information_revision": discovery["information_context"]["revision"],
        "requirements": requirements,
        "matching_only": matching_only,
        "job_brief_revision": (job_brief or {}).get("revision"),
    }
    previous_directory = Path(resume_from).expanduser().absolute() if resume_from else None
    saved = {}
    revalidate_recorded = False
    if previous_directory is not None:
        saved = _read_saved(previous_directory / "analysis-progress.json")
        if not isinstance(saved.get("binding"), dict):
            raise PortalDataError("match_resume_invalid", "原分析绑定不能核验。", 409)
        supplied_revision = saved.get("binding", {}).get("job_brief_revision")
        if job_brief is None and supplied_revision is not None:
            restored_brief = validate_job_brief(saved.get("brief"), application)
            if restored_brief["revision"] != supplied_revision:
                raise PortalDataError("match_resume_invalid", "原岗位解读绑定不能核验。", 409)
            binding["job_brief_revision"] = supplied_revision
        if (
            saved.get("schema_version") != "application-analysis-progress/v1"
            or saved.get("phase")
            not in {"brief", "planning", "selected", "reading", "evaluation", "evaluated"}
            or saved.get("revision") != digest({k: v for k, v in saved.items() if k != "revision"})
            or not _same_upstream_binding(saved, binding)
        ):
            if not (
                _answered_evaluation(saved) or known_reading_failure(previous_directory, saved)
            ):
                raise PortalDataError("match_resume_invalid", "原分析与本轮输入不符，未复用。", 409)
            # A proven size refusal or a complete saved answer hides no result; changed
            # inputs or an App update are analysed from the start (installed MC-11).
            previous_directory, saved = None, {}
            binding["job_brief_revision"] = (job_brief or {}).get("revision")
        revalidate_recorded = bool(saved) and (
            saved["binding"]["configuration"] != binding["configuration"]
            and _known_invalid_followup(saved)
        )

    def checkpoint(phase, **values):
        saved.update(
            values, phase=phase, binding=binding, schema_version="application-analysis-progress/v1"
        )
        saved.pop("revision", None)
        saved["revision"] = digest(saved)
        helper.atomic_write_json(directory / "analysis-progress.json", saved)

    plans = deepcopy(saved.get("plans", []))
    evaluations = deepcopy(saved.get("evaluations", []))
    selected = list(saved.get("selected", []))
    packet = deepcopy(saved.get("packet"))
    if not saved:
        checkpoint("brief", brief_origin=str(directory / "job-brief"))
    # Legacy refreshes retain their existing framework. New analyses interpret
    # the JD before seeing applicant facts or the experience directory.
    if saved.get("brief"):
        brief = validate_job_brief(saved["brief"], application)
    elif job_brief is not None:
        brief = validate_job_brief(job_brief, application)
        helper.atomic_write_json(directory / "job-brief" / "job-brief.json", brief)
    elif requirements is None:
        try:
            brief = create_job_brief(
                application,
                directory / "job-brief",
                runner=runner,
                environment=environment,
                resume_from=Path(saved["brief_origin"]) if previous_directory is not None else None,
                on_dispatch=lambda: checkpoint("brief", brief_origin=str(directory / "job-brief")),
            )
        except Exception:
            if (directory / "job-brief/validation-failure.json").is_file():
                checkpoint("brief", brief_origin=str(directory / "job-brief"))
            raise
    else:
        brief = None
    stable = saved.get("stable") or (
        brief_requirements(brief) if brief is not None else _required(requirements)
    )
    if brief is not None and requirements is not None and _required(requirements) != stable:
        raise PortalDataError("job_brief_invalid", "原要求与固定岗位说明不一致。", 409)
    checkpoint(
        "planning" if saved["phase"] == "brief" else saved["phase"], brief=brief, stable=stable
    )
    if saved.get("discovery") is not None:
        discovery = deepcopy(saved["discovery"])
    elif canonical:
        discovery = _discovery_with_bodies(discovery, source_loader, directory)
    checkpoint(saved.get("phase", "planning"), brief=brief, stable=stable, discovery=discovery)

    def retrieve(kind, unknown=None, already=None):
        invocation = uuid4().hex
        destination = directory / "retrieval" / invocation
        origin = (
            Path(saved["planner_origin"])
            if previous_directory is not None
            and saved.get("planner_pending")
            and saved.get("planner_kind") == kind
            else None
        )
        checkpoint(
            "planning",
            planner_kind=kind,
            planner_pending=True,
            planner_origin=str(origin or destination),
        )
        try:
            return plan_retrieval(
                application,
                discovery,
                directory / "retrieval",
                runner=runner,
                environment=environment,
                requirements=stable,
                job_brief=brief,
                unknown_requirements=unknown,
                selected_candidate_ids=already,
                invocation_id=invocation,
                resume_from=origin,
                on_dispatch=lambda: checkpoint("planning", planner_origin=str(destination)),
            )
        except Exception:
            if any(destination.glob("page-*/validation-failure.json")):
                checkpoint("planning", planner_origin=str(destination))
            raise

    if canonical and not plans:
        plan = _whole_library_plan(
            application, binding_snapshot, source_loader, library, stable
        ) or retrieve("initial")
        stable = stable if stable is not None else plan["requirements"]
        plans.append(plan)
        selected = list(plan["selected_candidate_ids"])
        checkpoint("selected", plans=plans, selected=selected, stable=stable, planner_pending=False)
    while True:
        phase = (
            "evaluated"
            if saved["phase"] == "planning" and saved.get("planner_kind") == "followup"
            else saved["phase"]
        )
        restored = phase in {"reading", "evaluation", "evaluated"}
        career = (
            deepcopy(saved["career"])
            if restored
            else (source_loader(selected) if canonical else deepcopy(binding_snapshot))
        )
        if restored and canonical and source_loader(selected) != career:
            raise PortalDataError(
                "match_sources_changed", "恢复前已选资料变化，未采用旧读取结果。", 409
            )
        if career.get("revision") != digest({k: v for k, v in career.items() if k != "revision"}):
            raise PortalDataError("match_snapshot_invalid", "已选来源不能核验。", 409)
        if canonical and (
            career.get("career_library", {}).get("revision")
            != binding_snapshot["career_library"].get("revision")
            or career.get("career_library", {}).get("records")
            != binding_snapshot["career_library"].get("records")
            or set(
                career.get("career_library", {}).get(
                    "requested_candidate_ids",
                    career.get("career_library", {}).get("selected_candidate_ids", []),
                )
            )
            != set(selected)
        ):
            raise PortalDataError(
                "match_sources_changed", "检索期间完整经历目录已变化，未采用混合版本。", 409
            )
        _read_complete(career, directory, "selected_bodies")
        evaluation = (
            deepcopy(saved["evaluation"])
            if restored
            else information_source_snapshot(application, library, career)
        )
        evaluation["application_library_policy"] = "trusted-library/v1"
        for item in evaluation["items"]:
            item["application_trusted"] = True
            if item.get("source_kind") != "confirmed_information":
                item["resume_eligible"] = True
                item.setdefault(
                    "boundaries", "Preserve the recorded role, project status and facts."
                )

        if matching_only:
            evaluation["matching_only"] = True
        if stable is not None:
            evaluation["match_requirements"] = stable
        if brief is not None:
            evaluation["job_brief"] = brief
        evaluation["retrieval_coverage"] = {
            "index_candidates": len(binding_snapshot.get("career_library", {}).get("records", [])),
            "selected_candidate_ids": selected,
            "source_reads": career.get("career_library", {}).get("source_reads", []),
            "unavailable_sources": career.get("career_library", {}).get("unavailable_sources", []),
        }
        evaluation.pop("revision", None)
        evaluation["revision"] = digest(evaluation)
        from .application_material_packet import prepare_material_packet

        round_number = saved["round_number"] if restored else len(evaluations) + 1
        if phase not in {"evaluation", "evaluated"}:
            packet_directory = directory / f"material-packet-{round_number}"
            reading_origin = None
            if restored and previous_directory is not None:
                reading_origin = Path(
                    saved.get("reading_origin", str(previous_directory / packet_directory.name))
                )
                partial = reading_origin / "material-packet.json"
                if partial.exists():
                    packet = _read_saved(partial)
            checkpoint(
                "reading",
                career=career,
                evaluation=evaluation,
                packet=packet,
                plans=plans,
                evaluations=evaluations,
                selected=selected,
                stable=stable,
                round_number=round_number,
                reading_origin=str(reading_origin or packet_directory),
            )

            def dispatched(packet_directory=packet_directory):
                if saved.get("reading_origin") != str(packet_directory):
                    checkpoint("reading", reading_origin=str(packet_directory))

            evaluation, packet = prepare_material_packet(
                application,
                evaluation,
                packet_directory,
                runner=runner,
                job_brief=brief,
                requirements=stable,
                previous=packet,
                resume_from=reading_origin,
                on_dispatch=dispatched,
            )
            checkpoint(
                "evaluation",
                career=career,
                evaluation=evaluation,
                packet=packet,
                evaluation_error=None,
            )
        attempt = directory / f"evaluation-{round_number}"
        origin = (
            Path(saved["evaluation_origin"])
            if phase in {"evaluation", "evaluated"} and saved.get("evaluation_origin")
            else (previous_directory / attempt.name if restored else attempt)
        )
        checkpoint("evaluation", evaluation_origin=str(origin))

        def dispatch_evaluation(attempt=attempt):
            checkpoint("evaluation", evaluation_origin=str(attempt), evaluation_error=None)

        try:
            if restored and phase in {"evaluation", "evaluated"}:
                report = _resume_evaluation(
                    application,
                    evaluation,
                    origin,
                    attempt,
                    runner,
                    saved.get("evaluation_error")
                    in {
                        "match_model_invalid",
                        "match_inference_invalid",
                        "retrieval_execution_incomplete",
                    },
                    dispatch_evaluation,
                    revalidate_recorded=revalidate_recorded,
                )
            else:
                dispatch_evaluation()
                report = _analyze_loaded_job(application, evaluation, attempt, runner=runner)
        except Exception as error:
            checkpoint(
                "evaluation",
                evaluation_error=getattr(error, "code", "flow_stage_failed"),
                evaluation_origin=str(attempt if attempt.exists() else origin),
            )
            raise
        _bind_information(application, library, report["requirements"])
        helper.atomic_write_json(attempt / "analysis.json", report)
        completed = {
            "directory": attempt.name,
            "revision": digest(report),
            "analysis_directory": str(directory),
        }
        if len(evaluations) == round_number:
            evaluations[-1] = completed
        else:
            evaluations.append(completed)
        stable = stable if stable is not None else _required(report["requirements"])
        checkpoint(
            "evaluated",
            evaluations=evaluations,
            stable=stable,
            evaluation_error=None,
            evaluation_origin=str(attempt),
        )
        unresolved = [
            index
            for index, row in enumerate(report["requirements"])
            if row["judgment"] in {"unknown", "partial"}
        ]
        if not canonical or not unresolved:
            break
        if saved.get("followup_exhausted"):
            break
        candidate_ids = {
            row["candidate_id"] for row in binding_snapshot["career_library"]["records"]
        }
        read_candidate_ids = {
            row["candidate_id"]
            for row in career.get("career_library", {}).get("source_reads", [])
            if row.get("status") in {"read", "read_identity", "read_whole_document"}
        }
        if not candidate_ids - read_candidate_ids:
            break
        try:
            plan = retrieve(
                "followup",
                unresolved,
                career.get("career_library", {}).get("selected_candidate_ids", selected),
            )
        except PortalDataError as error:
            if error.code != "retrieval_model_failed":
                raise
            # A follow-up only seeks more evidence for a completed evaluation. Keyrock
            # and Mistral (2026-11-08) each had one follow-up page that never answered,
            # even with 360 s, and the whole analysis failed; keep the last report.
            checkpoint("evaluated", planner_pending=False, followup_exhausted=True)
            break
        plans.append(plan)
        checkpoint(
            "evaluated",
            plans=plans,
            planner_pending=False,
            followup_exhausted=not plan["selected_candidate_ids"],
        )
        if not plan["selected_candidate_ids"]:
            break
        selected.extend(plan["selected_candidate_ids"])
        checkpoint(
            "selected", plans=plans, selected=selected, packet=packet, followup_exhausted=False
        )
    # Re-read selected captures after model work. A changed file cannot become adopted evidence.
    if canonical and source_loader(selected) != career:
        raise PortalDataError(
            "match_sources_changed", "分析期间来源已变化，保留结果后重新核验。", 409
        )
    selected_sources = {item["source_id"] for item in career["items"] if item.get("candidate_id")}
    consumed_sources = set(report["coverage"].get("included_source_ids", []))
    coverage = {
        "selected_context_complete": packet["status"] == "complete",
        "selected_source_count": len(selected_sources),
        "consumed_selected_source_count": len(selected_sources & consumed_sources),
        "index_status": "searched" if canonical else "not_configured",
        "indexed_candidates": len(binding_snapshot.get("career_library", {}).get("records", [])),
        "selected_candidate_ids": selected,
        "read_candidate_ids": career.get("career_library", {}).get(
            "selected_candidate_ids", selected
        ),
        "plans": plans,
        "evaluations": evaluations,
        "source_reads": career.get("career_library", {}).get("source_reads", []),
        "context_status": "partial" if report["coverage"]["truncated"] else "complete",
        "unread_source_ids": report["coverage"].get("omitted_source_ids", []),
        "unread_source_ranges": report["coverage"].get("truncated_sources", []),
        "information_context_revision": evaluation["information_context"]["revision"],
        "status": "retrieved" if packet["sources"] else "information_insufficient",
        "material_packet_revision": packet["revision"],
        "material_reads": packet["source_reads"],
        "requirement_coverage": [
            {
                "requirement_index": index,
                "status": "retrieved" if row["source_ids"] else "information_insufficient",
            }
            for index, row in enumerate(report["requirements"])
        ],
    }
    unavailable = career.get("career_library", {}).get("unavailable_sources", [])
    for row in report["requirements"]:
        if row["judgment"] in {"unknown", "partial"}:
            row["evidence_state"] = (
                "source_unavailable"
                if unavailable
                else "context_not_fully_read"
                if report["coverage"]["truncated"]
                else "searched_evidence_insufficient"
            )
    result = {
        **report,
        "id": directory.name,
        "matching_only": matching_only,
        "application_library_policy": "trusted-library/v1",
        "source_snapshot_revision": career["revision"],
        "input_source_snapshot_revision": binding_snapshot["revision"],
        "selected_read_snapshot_revision": evaluation["revision"],
        "information_context_revision": evaluation["information_context"]["revision"],
        "retrieval": coverage,
        "material_packet": packet,
        **(
            {"job_brief": brief, "match_route": route_for_score(report["score"])}
            if brief is not None
            else {}
        ),
    }
    job = {
        key: application.get(key, "")
        for key in ("company", "role_title", "location", "job_description")
    }
    helper.atomic_write_json(
        directory / "input.json",
        {
            "application_id": application["id"],
            "application_revision": application["revision"],
            "job": job,
            "source_snapshot_revision": binding_snapshot["revision"],
            "configuration": match_configuration(environment),
        },
    )
    helper.atomic_write_json(directory / "binding-source-snapshot.json", binding_snapshot)
    helper.atomic_write_json(directory / "source-snapshot.json", career)
    helper.atomic_write_json(directory / "selected-read-snapshot.json", evaluation)
    helper.atomic_write_json(directory / "retrieval.json", coverage)
    helper.atomic_write_json(directory / "material-packet.json", packet)
    helper.atomic_write_json(directory / "analysis.json", result)
    return result
