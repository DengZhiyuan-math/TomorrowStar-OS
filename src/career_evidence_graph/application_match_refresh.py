"""Append normal-pipeline match versions without replacing application materials."""

from __future__ import annotations

import hashlib
import json
import os
import re
from copy import deepcopy
from datetime import UTC, datetime
from threading import Lock

from ._vendor import job_apply_store as helper
from .application_career_library import _read as _read_private_file
from .application_information import information_context
from .application_input_binding import revision_matches
from .application_match import match_configuration_revision
from .application_match_scoring import calculate_match_score
from .career_portal_data import PortalDataError
from .codex_cli import CodexCLIError, _parse_jsonl, build_codex_exec_argv
from .validation.hashing import record_digest as digest
from .validation.models import CodexCLIConfig, CodexCLIResult

_VALIDATION_FAILURES = {"match_model_invalid", "retrieval_invalid"}
_READING_BUDGET_FAILURE = "retrieval_execution_incomplete"
_STOPPED_DISPATCH = "flow_preparation_stopped"
_READING_FAILURE_PROOFS = {
    "reconciled_reading_budget",
    "reconciled_reading_argv_capacity",
    "reconciled_reading_output_limit",
}
_MAX_ARTIFACT_BYTES = 64_000_000
_ACTIVE_CALLBACKS = set()
_ACTIVE_LOCK = Lock()


def _root_key(flow):
    root = flow.root.stat()
    return root.st_dev, root.st_ino


def match_refresh_running(flow, *, other_than=None):
    """Read physical callback ownership without changing saved requests or outcomes."""
    root = _root_key(flow)
    with _ACTIVE_LOCK:
        requests = [request for directory, request in _ACTIVE_CALLBACKS if directory == root]
    return (
        bool(requests)
        if other_than is None
        else any(
            _read(flow.root / "match-refreshes" / request / "intent.json").get("task_id")
            != other_than
            for request in requests
        )
    )


def require_no_other_match_refresh(flow, task_id):
    if match_refresh_running(flow, other_than=task_id):
        raise PortalDataError(
            "match_refresh_other_job_running", "原岗位匹配仍在执行，其他岗位须等待其返回。", 409
        )


def _sha(raw):
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def _require(value, message):
    if not value:
        raise PortalDataError("match_refresh_invalid", message, 409)


def _read(path):
    try:
        value = json.loads(_read_private_file(path, _MAX_ARTIFACT_BYTES))
        _require(isinstance(value, dict), "重新核验记录须为对象。")
        return value
    except (OSError, ValueError, TypeError) as error:
        raise PortalDataError("match_refresh_invalid", "重新核验记录不能读取。", 409) from error


def _artifact_hashes(directory):
    result, total = [], 0
    for path in sorted(directory.rglob("*.json")):
        if path == directory / "failure.json":
            continue
        raw = _read_private_file(path, _MAX_ARTIFACT_BYTES)
        total += len(raw)
        _require(
            total <= _MAX_ARTIFACT_BYTES and len(result) < 10_000, "核验记录超出完整校验范围。"
        )
        result.append({"path": str(path.relative_to(directory)), "sha256": _sha(raw)})
    return result


def _completed_calls(directory, *, proof=None):
    """Unknown or incomplete calls cannot be converted into a known parser failure."""
    phases = [
        (path.parent, "model-result.json", "match-schema.json", "context-input.json")
        for path in directory.glob("analysis/evaluation-*/context-input.json")
    ]
    phases.extend(
        (path.parent, "result.json", "schema.json", "prompt.json")
        for path in directory.glob("analysis/retrieval/*/page-*/prompt.json")
    )
    phases.extend(
        (path.parent, "result.json", "schema.json", "prompt.json")
        for path in directory.glob("analysis/material-packet-*/source-*/prompt.json")
    )
    phases.extend(
        (path.parent, "job-brief-result.json", "job-brief-schema.json", path.name)
        for path in directory.glob("analysis/job-brief/job-brief-prompt.json")
    )
    excluded = None
    method = (proof or {}).get("method")
    if method == "local_dispatch_refused":
        intent = _read(directory / "intent.json")
        receipt = _read(directory / "analysis" / "dispatch-stopped.json")
        _require(
            receipt.get("schema_version") == "analysis-dispatch-stopped/v1"
            and receipt.get("request_revision") == digest(intent)
            and receipt.get("new_call_dispatched") is False
            and receipt.get("revision")
            == digest({key: value for key, value in receipt.items() if key != "revision"})
            and proof.get("receipt_revision") == receipt["revision"],
            "本地停止派发回执不能核验。",
        )
        schema = receipt.get("undispatched_schema")
        if schema is None:
            _require(not phases, "已有调用请求，不能仅凭 Adapter 停止证明解除未知。")
        else:
            refused = [
                row
                for row in phases
                if str((row[0] / row[2]).relative_to(directory / "analysis")) == schema
            ]
            _require(len(refused) == 1, "停止派发须唯一对应已保存的调用请求。")
            folder, result_name, _, prompt_name = refused[0]
            result = _read(folder / result_name)
            _require(
                result
                == {
                    "status": "failed",
                    "error_type": "_CallNotAdmitted",
                    "raw_stdout_jsonl": "",
                    "redacted_stderr": "",
                },
                "被阻止的调用回执含未知结果，不能解除待核对状态。",
            )
            excluded = folder / prompt_name
    if method in {"reconciled_reading_argv_capacity", "reconciled_reading_output_limit"}:
        relative = proof.get(
            "failed_prompt"
            if method == "reconciled_reading_output_limit"
            else "undispatched_prompt",
            "",
        )
        _require(
            isinstance(relative, str)
            and re.fullmatch(
                r"analysis/material-packet-[1-9][0-9]*/source-[0-9]{4,}-page-[0-9]{4,}/prompt.json",
                relative,
            ),
            "已知失败调用的定位不能核验。",
        )
        excluded = directory / relative
        _require(
            sum(folder / prompt_name == excluded for folder, _, _, prompt_name in phases) == 1,
            "已知失败调用须唯一对应已保存的资料读取请求。",
        )
        if method == "reconciled_reading_output_limit":
            _terminal_output_limit_page(excluded.parent)
        else:
            _undispatched_argv_page(excluded.parent)
    for folder, result_name, schema_name, prompt_name in phases:
        if folder / prompt_name == excluded:
            continue
        try:
            result = CodexCLIResult.model_validate(_read(folder / result_name))
            _require(result.exit_code == 0, "原模型调用未正常完成。")
            prompt = _read(folder / prompt_name)["prompt"]
            schema_raw = _read_private_file(folder / schema_name, _MAX_ARTIFACT_BYTES)
            _, structured = _parse_jsonl(result.raw_stdout_jsonl)
            _require(
                isinstance(prompt, str)
                and result.prompt_hash == _sha(prompt.encode("utf-8"))
                and result.output_schema_hash == _sha(schema_raw)
                and digest(structured) == digest(result.structured_result),
                "原模型调用的输入、格式或原始输出不一致。",
            )
        except (OSError, ValueError, TypeError, KeyError, CodexCLIError) as error:
            raise PortalDataError(
                "match_refresh_unknown", "原模型调用尚不能确认为已完成，未解除待核对状态。", 409
            ) from error
    return len(phases) - int(excluded is not None)


def _failure_current(directory, intent):
    path = directory / "failure.json"
    if not path.exists():
        return None
    outcome = _read(path)
    _require(
        outcome.get("schema_version") == "match-refresh-failure/v1"
        and outcome.get("status") == "known_failed"
        and (
            outcome.get("error_code") in _VALIDATION_FAILURES
            or outcome.get("error_code") == _STOPPED_DISPATCH
            and outcome.get("proof", {}).get("method") == "local_dispatch_refused"
            or outcome.get("error_code") == _READING_BUDGET_FAILURE
            and outcome.get("proof", {}).get("method") in _READING_FAILURE_PROOFS
        )
        and outcome.get("request_id") == intent.get("id")
        and outcome.get("intent_revision") == digest(intent)
        and outcome.get("revision")
        == digest({key: value for key, value in outcome.items() if key != "revision"})
        and outcome.get("artifacts") == _artifact_hashes(directory)
        and not (directory / "analysis" / "analysis.json").exists(),
        "已确认失败的原始记录已变化，须先核对，不能重放。",
    )
    return outcome


def _record_failure(directory, intent, code, proof, *, expected_artifacts=None):
    existing = _failure_current(directory, intent)
    if existing:
        return existing
    _require(
        code in _VALIDATION_FAILURES
        or code == _STOPPED_DISPATCH
        and proof.get("method") == "local_dispatch_refused"
        or code == _READING_BUDGET_FAILURE
        and proof.get("method") in _READING_FAILURE_PROOFS,
        "此错误尚不能确认为已知失败。",
    )
    _require(
        not (directory / "analysis" / "analysis.json").exists(), "已有完整结果，不能标记为失败。"
    )
    artifacts = _artifact_hashes(directory)
    _require(
        expected_artifacts is None or expected_artifacts == artifacts,
        "核验期间原始结果已变化，保留待核对状态。",
    )
    completed = _completed_calls(directory, proof=proof)
    _require(artifacts == _artifact_hashes(directory), "校验期间原始记录已变化。")
    outcome = {
        "schema_version": "match-refresh-failure/v1",
        "status": "known_failed",
        "request_id": intent["id"],
        "intent_revision": digest(intent),
        "configuration_revision": intent.get("configuration_revision"),
        "error_code": code,
        "proof": proof,
        "completed_calls": completed,
        "artifacts": artifacts,
        "recorded_at": datetime.now(UTC).isoformat(),
    }
    outcome["revision"] = digest(outcome)
    helper.atomic_write_json(directory / "failure.json", outcome)
    return outcome


def _requirements(report):
    try:
        return [
            {
                key: deepcopy(row[key])
                for key in ("text", "importance", "hard_condition", "scoring_framework")
                if key in row
            }
            for row in report["requirements"]
        ]
    except (KeyError, TypeError) as error:
        raise PortalDataError("match_refresh_invalid", "原岗位要求不能核验。", 409) from error


def _guard(flow, task):
    from .application_input_binding import latest_preparation_task

    if flow.preparation_only:
        latest = latest_preparation_task(flow._load()["tasks"], task["application_id"])
        _require(latest is not None and latest["id"] == task["id"], "当前岗位已有更新的任务。")
    _require(
        task["status"] not in {"cancelled", "queued", "filling", "needs_recheck"},
        "当前任务须先核对原执行结果。",
    )
    _require(
        not any(
            stage.get("status") in {"queued", "running", "needs_recheck", "unknown"}
            for stage in task["stages"].values()
        ),
        "当前阶段执行结果尚未核对。",
    )
    flow._group_guard_change(task)


def _guard_pending(parent, task):
    """A different request ID cannot replace an unreconciled model operation."""
    if not parent.exists():
        return
    adopted = {receipt["id"] for receipt in task.get("match_rechecks", [])}
    for directory in parent.iterdir():
        if directory.name in adopted or not re.fullmatch(r"[a-f0-9]{32}", directory.name):
            continue
        path = directory / "intent.json"
        if not path.exists():
            continue
        intent = _read(path)
        if intent.get("task_id") == task["id"] and intent.get("method") == "normal_analysis":
            if _failure_current(directory, intent):
                continue
            raise PortalDataError(
                "match_refresh_unknown",
                "当前任务仍有未核对的重新核验请求，请先接续原请求；未重放模型调用。",
                409,
            )


def _binding(flow, task, application):
    from .application_explanations import adopted_analysis
    from .application_input_binding import job_input_revision

    original = adopted_analysis(task)
    _require(original is not None, "须保留原岗位分析。")
    _require(
        job_input_revision(application) == task["job_binding"],
        "岗位要求已变化，不能沿用原岗位要求重新核验。",
    )
    library = flow.information_provider() if flow.information_provider else {}
    connected = library.get("career_library", {})
    _require(connected.get("status") == "available", "完整经历库暂不可用。")
    return (
        {
            "task_id": task["id"],
            "application_id": application["id"],
            "base_analysis_id": task["analysis_id"],
            "base_analysis_revision": digest(original),
            "job_binding": job_input_revision(application),
            "library_revision": connected.get("revision"),
            "information_context_revision": information_context(application, library)["revision"],
            "configuration_revision": match_configuration_revision(),
        },
        original,
        library,
    )


def _report_current(flow, application, original, library, report):
    _require(isinstance(report, dict), "分析结果格式不能核验。")
    _require(
        report.get("configuration_revision") == match_configuration_revision(),
        "重新核验的分析引擎配置已变化。",
    )
    job = {
        key: application.get(key, "")
        for key in ("company", "role_title", "location", "job_description")
    }
    _require(
        report.get("application_id") == application["id"]
        and report.get("application_revision") == application["revision"]
        and report.get("jd_revision") == digest(job)
        and _requirements(report) == _requirements(original),
        "新核验与当前岗位或原岗位要求不符。",
    )
    if original.get("job_brief") is not None:
        _require(report.get("job_brief") == original["job_brief"], "重新核验不能改变固定岗位说明。")
    selected = report.get("retrieval", {}).get("selected_candidate_ids")
    _require(
        isinstance(selected, list)
        and all(isinstance(key, str) for key in selected)
        and len(set(selected)) == len(selected),
        "实际读取的经历范围不能核验。",
    )
    _require(callable(flow.recheck_source_provider), "完整经历来源尚未连接。")
    snapshot = flow.recheck_source_provider(application["id"], selected)
    _require(
        snapshot.get("revision")
        == digest({key: value for key, value in snapshot.items() if key != "revision"})
        and snapshot.get("revision") == report.get("source_snapshot_revision"),
        "实际读取的职业来源已变化。",
    )
    _require(
        information_context(application, library)["revision"]
        == report.get("information_context_revision"),
        "适用的已确认信息已变化。",
    )


def _recheck_result(report):
    # Decided 2026-10-31: a recheck may overturn an earlier gap; both come from the same
    # model and rules, and the recheck reads the same confirmed information.
    result = deepcopy(report)
    result["score"] = calculate_match_score(result["requirements"])
    return result


def _selection_failure(directory, intent, original):
    """Prove the old, completed evaluator result fails the generic selection contract."""
    from .application_match import _ModelOutput

    completed = _completed_calls(directory)
    evaluations = sorted(
        (
            path
            for path in (directory / "analysis").glob("evaluation-*")
            if re.fullmatch(r"evaluation-[1-9][0-9]*", path.name)
        ),
        key=lambda path: int(path.name.split("-")[-1]),
    )
    _require(completed and evaluations, "尚无可独立核对的完整模型结果。")
    evaluation = evaluations[-1]
    _require(
        not (evaluation / "analysis.json").exists(), "该评估已有完整结果，不能作为格式失败处理。"
    )
    inputs = _read(evaluation / "input.json")
    snapshot = _read(evaluation / "source-snapshot.json")
    context = _read(evaluation / "context-input.json")
    schema = _read(evaluation / "match-schema.json")
    result = _read(evaluation / "model-result.json")
    try:
        prompt_context = json.loads(context["prompt"].rsplit("\n", 1)[-1])
        output = _ModelOutput.model_validate(result["structured_result"]).model_dump()
    except (ValueError, KeyError, TypeError, AttributeError) as error:
        raise PortalDataError(
            "match_refresh_invalid", "尚不能证明原结果属于选材对应关系校验失败。", 409
        ) from error
    _require(
        inputs.get("application_id") == intent.get("application_id")
        and digest(inputs.get("job")) == intent.get("job_binding")
        and revision_matches(inputs.get("configuration"), intent.get("configuration_revision"))
        and snapshot.get("revision")
        == digest({key: value for key, value in snapshot.items() if key != "revision"})
        and snapshot.get("revision") == inputs.get("source_snapshot_revision")
        and prompt_context.get("job") == inputs.get("job")
        and prompt_context.get("match_requirements") == _requirements(original)
        and schema == _ModelOutput.model_json_schema(),
        "原评估的输入、岗位要求、格式或引擎绑定不能核验。",
    )
    selected = list(dict.fromkeys(output["selected_source_ids"]))
    _require(
        [row["source_id"] for row in output["selection_rationale"]] != selected,
        "原结果未触发选材对应关系校验失败，保留待核对状态。",
    )
    return {
        "method": "reconciled_selection_contract",
        "evaluation": str(evaluation.relative_to(directory)),
        "input_revision": digest(inputs),
        "model_result_revision": digest(result),
    }


def _reading_page_binding(page):
    """Verify saved prompt, schema, source context and still-unread exact ranges."""
    from .application_material_packet import _reading_prompt, _reading_spans
    from .application_material_sources import model_sources

    packet = _read(page.parent / "material-packet.json")
    prompt = _read(page / "prompt.json").get("prompt")
    _require(isinstance(prompt, str) and bool(prompt.strip()), "原读取请求为空。")
    context, schema = _read(page / "context.json"), _read(page / "schema.json")
    configuration = _read(page.parent.parent / "analysis-progress.json")["binding"]["configuration"]
    config = CodexCLIConfig(
        schema_version="codex-cli-config/v1",
        workspace=page,
        output_schema=page / "schema.json",
        drift_limitation_reason="Verify saved failed reading input only.",
    )
    _require(
        configuration.get("requested_model") == config.requested_model
        and configuration.get("reasoning_effort") == config.reasoning_effort
        and configuration.get("sandbox") == config.sandbox,
        "原请求的固定 CLI 参数不能核验。",
    )
    complete = schema.get("title") == "_SourceReading"
    _require(
        schema.get("title") in {"_SourceReading", "_Reading"}
        and prompt == _reading_prompt(context, complete_sources=complete),
        "原读取请求的原文和格式不一致。",
    )
    inputs = _read(page.parent / "input.json")
    _require(
        all(context.get(key) == value for key, value in inputs.items() if key != "sources"),
        "原读取请求与读取作用域不一致。",
    )
    supplied = context.get("source_ranges", [context])
    sources = inputs.get("sources", {})
    _require(
        isinstance(supplied, list)
        and bool(supplied)
        and all(row.get("source", {}).get("source_id") in sources for row in supplied),
        "原读取请求的来源不能核验。",
    )
    projection = model_sources(sources[row["source"]["source_id"]] for row in supplied)
    for row, metadata in zip(supplied, projection["sources"], strict=True):
        identifier = row["source"]["source_id"]
        source, chunk = sources[identifier], row.get("range", {})
        start, end = chunk.get("start"), chunk.get("end")
        _require(
            type(start) is int
            and type(end) is int
            and 0 <= start < end <= len(source["text"])
            and chunk.get("digest") == digest(source["text"][start:end])
            and row["source"] == {key: value for key, value in metadata.items() if key != "text"}
            and (
                row.get("text") == source["text"][start:end]
                if complete
                else row.get("spans") == _reading_spans(source, chunk, paragraphs=True)
            )
            and not any(
                all(saved.get(key) == chunk[key] for key in ("start", "end", "digest"))
                for saved in packet.get("source_reads", {}).get(identifier, {}).get("ranges", [])
            ),
            "原读取请求的原文范围不一致，或该范围已有读取回执。",
        )
    return prompt, config, configuration


def _undispatched_argv_page(page):
    """Prove one exec failure without treating an unreceipted model call as safe."""
    failure = _read(page.parent / "material-packet.json").get("failure", {})
    failed_exec = re.fullmatch(
        r"\[Errno 7\] Argument list too long: '([^\n]+)'", failure.get("message", "")
    )
    _require(
        failure.get("error_type") == "OSError" and failed_exec is not None,
        "原失败尚不能证明为操作系统拒绝启动。",
    )
    result = _read(page / "result.json")
    limit = os.sysconf("SC_ARG_MAX")
    _require(
        result
        == {
            "status": "failed",
            "error_type": "OSError",
            "raw_stdout_jsonl": "",
            "redacted_stderr": "",
        }
        and isinstance(limit, int)
        and limit > 0,
        "原请求未证明超出系统参数上限，或已有可能执行的输出。",
    )
    prompt, config, configuration = _reading_page_binding(page)
    _require(
        failed_exec[1]
        == (configuration.get("resolved_executable") or configuration.get("executable")),
        "原请求的可执行程序不能核验。",
    )
    argv = build_codex_exec_argv(config, prompt, allow_non_repository=True)
    argv[0] = failed_exec[1]
    # Older launches lack the MC-21 isolation flags before --model; omit them from the bound.
    argv = argv[:2] + argv[argv.index("--model") :]
    # The actual immutable schema copy had a longer path; omit environment and
    # pointer overhead so this bound cannot overstate the failed launch size.
    minimum_argv_bytes = sum(len(os.fsencode(argument)) + 1 for argument in argv)
    _require(minimum_argv_bytes > limit, "原完整参数尚不能证明超出系统上限。")
    return {
        "prompt_bytes": len(prompt.encode("utf-8")),
        "minimum_argv_bytes": minimum_argv_bytes,
        "argv_limit": limit,
    }


def _terminal_output_limit_page(page):
    """Accept one fully observed failed turn, never a partial or unknown result."""
    failure = _read(page.parent / "material-packet.json").get("failure")
    result = _read(page / "result.json")
    _require(
        failure
        == {"error_type": "CodexCLIError", "message": "Codex exec failed with exit code 1: "}
        and set(result) == {"status", "error_type", "raw_stdout_jsonl", "redacted_stderr"}
        and result.get("status") == "failed"
        and result.get("error_type") == "CodexCLIError"
        and result.get("redacted_stderr") == ""
        and isinstance(result.get("raw_stdout_jsonl"), str),
        "原读取调用尚不能确认为完整的输出上限失败。",
    )
    try:
        events = [
            json.loads(line) for line in result["raw_stdout_jsonl"].splitlines() if line.strip()
        ]
    except (ValueError, TypeError) as error:
        raise PortalDataError("match_refresh_invalid", "原调用事件不能核验。", 409) from error
    message = "Incomplete response returned, reason: max_output_tokens"
    _require(
        len(events) == 4
        and all(isinstance(event, dict) for event in events)
        and set(events[0]) == {"type", "thread_id"}
        and events[0].get("type") == "thread.started"
        and isinstance(events[0].get("thread_id"), str)
        and bool(events[0]["thread_id"].strip())
        and events[1] == {"type": "turn.started"}
        and events[2] == {"type": "error", "message": message}
        and events[3] == {"type": "turn.failed", "error": {"message": message}},
        "原调用须完整终止于明确的输出上限错误，不能有助手输出或其他事件。",
    )
    _reading_page_binding(page)
    return {"terminal_failed_calls": 1, "native_failure_revision": digest(result)}


def _other_reading_unreceipted(origin, packet, proved_failed):
    """Exclude only the separately proved failed page from the receipt audit."""
    for prompt in origin.glob("source-*/prompt.json"):
        if prompt == proved_failed:
            continue
        context = _read(prompt.with_name("context.json"))
        for row in context.get("source_ranges", [context]):
            ranges = (
                packet.get("source_reads", {}).get(row["source"]["source_id"], {}).get("ranges", [])
            )
            if not any(
                all(saved.get(key) == row["range"][key] for key in ("start", "end", "digest"))
                for saved in ranges
            ):
                return True
    return False


def _reading_budget_failure(directory, intent, original):
    """Prove a saved reading capacity failure with no unknown calls."""
    from .application_material_packet import _unreceipted_reading, packet_size
    from .application_material_sources import source_records

    progress = _read(directory / "analysis" / "analysis-progress.json")
    binding = progress.get("binding", {})
    _require(
        progress.get("schema_version") == "application-analysis-progress/v1"
        and progress.get("phase") == "reading"
        and progress.get("revision")
        == digest({key: value for key, value in progress.items() if key != "revision"})
        and not progress.get("evaluations")
        and not progress.get("evaluation_origin")
        and progress.get("stable") == _requirements(original)
        and binding.get("application_id") == intent["application_id"]
        and digest(binding.get("job")) == intent["job_binding"]
        and revision_matches(binding.get("configuration"), intent["configuration_revision"]),
        "原读取阶段、岗位要求或输入绑定不能核验。",
    )
    number = progress.get("round_number")
    _require(type(number) is int and number > 0, "原资料读取轮次不能核验。")
    origin = directory / "analysis" / f"material-packet-{number}"
    _require(progress.get("reading_origin") == str(origin), "原读取目录不能核验。")
    packet = _read(origin / "material-packet.json")
    evaluation = progress.get("evaluation", {})
    inputs = _read(origin / "input.json")
    scope = {key: value for key, value in inputs.items() if key != "sources"}
    _require(
        packet.get("status") == "failed"
        and packet.get("revision")
        == digest({key: value for key, value in packet.items() if key != "revision"})
        and not packet.get("pending_call")
        and evaluation.get("revision")
        == digest({key: value for key, value in evaluation.items() if key != "revision"})
        and packet.get("snapshot_revision") == evaluation.get("revision")
        and inputs.get("sources") == source_records(evaluation)
        and packet.get("scope_revision") == digest(scope)
        and scope.get("job") == binding.get("job")
        and scope.get("requirements") == progress["stable"]
        and packet.get("context_limits") == binding.get("configuration", {}).get("context_limits"),
        "原读取尚不能证明为已保存全部调用结果后的容量失败。",
    )
    proof = {
        "method": "reconciled_reading_budget",
        "progress_revision": progress["revision"],
        "packet_revision": packet["revision"],
        "reading_directory": str(origin.relative_to(directory)),
    }
    if packet.get("failure") == {
        "error_type": "ValueError",
        "message": "Relevant evidence exceeds the complete packet budget",
    }:
        _require(
            packet_size(packet.get("sources", {}))
            > packet.get("context_limits", {}).get("material_context_bytes", float("inf"))
            and not _unreceipted_reading(origin, packet),
            "原容量失败或其他调用回执尚不能核验。",
        )
        return proof
    failed = [
        prompt
        for prompt in origin.glob("source-*/prompt.json")
        if _read(prompt.with_name("result.json")).get("status") == "failed"
    ]
    _require(len(failed) == 1, "须唯一定位已保存的失败读取请求。")
    prompt = failed[0]
    output_limit = packet.get("failure", {}).get("error_type") == "CodexCLIError"
    details = (
        _terminal_output_limit_page(prompt.parent)
        if output_limit
        else _undispatched_argv_page(prompt.parent)
    )
    _require(
        not _other_reading_unreceipted(origin, packet, prompt), "其他资料读取调用结果仍未核对。"
    )
    return (
        proof
        | details
        | {
            "method": "reconciled_reading_output_limit"
            if output_limit
            else "reconciled_reading_argv_capacity",
            "failed_prompt" if output_limit else "undispatched_prompt": str(
                prompt.relative_to(directory)
            ),
        }
    )


def _resume_predecessor(parent, request_id, binding):
    _require(
        isinstance(request_id, str) and re.fullmatch(r"[a-f0-9]{32}", request_id),
        "接续请求标识不能核验。",
    )
    directory = parent / request_id
    intent = _read(directory / "intent.json")
    outcome = _failure_current(directory, intent)
    _require(
        intent.get("id") == request_id
        and intent.get("method") == "normal_analysis"
        and all(
            intent.get(key) == value
            for key, value in binding.items()
            if key != "configuration_revision"
        )
        and outcome is not None
        and (
            outcome.get("error_code") == _READING_BUDGET_FAILURE
            and outcome.get("proof", {}).get("method") in _READING_FAILURE_PROOFS
            or outcome.get("error_code") == _STOPPED_DISPATCH
            and outcome.get("proof", {}).get("method") == "local_dispatch_refused"
        ),
        "只有同一岗位及当前资料下已核验的读取容量失败或本地停止派发才能接续。",
    )
    return directory / "analysis", outcome["revision"]


def reconcile_failed_match_refresh(flow, task_id, task_revision, request_id):
    """Classify a saved, completed malformed result without calling the model again."""
    _require(
        isinstance(request_id, str) and re.fullmatch(r"[a-f0-9]{32}", request_id),
        "重新核验请求标识不能核验。",
    )
    directory = flow.root / "match-refreshes" / request_id
    with flow.applications.write_lock():
        state, task = flow._checked(task_id, task_revision, allow_existing_handoff=True)
        _guard(flow, task)
        application = flow.applications.get_application(task["application_id"])
        binding, original, _ = _binding(flow, task, application)
        _require(
            not any(receipt["id"] == request_id for receipt in task.get("match_rechecks", [])),
            "原请求已有采纳记录，不能标记为失败。",
        )
        intent = _read(directory / "intent.json")
        _require(
            intent.get("id") == request_id
            and intent.get("method") == "normal_analysis"
            and all(
                intent.get(key) == binding[key]
                for key in (
                    "task_id",
                    "application_id",
                    "base_analysis_id",
                    "base_analysis_revision",
                    "job_binding",
                )
            ),
            "原请求不属于当前任务及原岗位分析。",
        )
        with _ACTIVE_LOCK:
            _require(
                (_root_key(flow), request_id) not in _ACTIVE_CALLBACKS,
                "原请求仍在执行，不能解除待核对状态。",
            )
        existing = _failure_current(directory, intent)
        if existing:
            return existing
        artifacts = _artifact_hashes(directory)
        reading = directory / "analysis" / "analysis-progress.json"
        if reading.exists() and _read(reading).get("phase") == "reading":
            proof = _reading_budget_failure(directory, intent, original)
            code = _READING_BUDGET_FAILURE
        else:
            proof = _selection_failure(directory, intent, original)
            code = "match_model_invalid"
        return _record_failure(directory, intent, code, proof, expected_artifacts=artifacts)


def refresh_match(flow, task_id, task_revision, request_id, *, resume_request_id=None):
    """Run once, reconcile known output, and append one source-bound match receipt."""
    _require(
        isinstance(request_id, str) and re.fullmatch(r"[a-f0-9]{32}", request_id),
        "重新核验请求标识不能核验。",
    )
    parent = flow.root / "match-refreshes"
    _require(not parent.is_symlink(), "重新核验目录不能使用符号链接。")
    directory = parent / request_id
    report_path = directory / "analysis" / "analysis.json"
    resume_from = None
    with flow.applications.write_lock():
        flow._writable()
        state = flow._load()
        task = flow._task(state, task_id)
        existing = next(
            (row for row in task.get("match_rechecks", []) if row["id"] == request_id), None
        )
        if existing:
            _require(existing.get("method") == "normal_analysis", "该标识已有其他复核记录。")
            intent, report = _read(directory / "intent.json"), _read(report_path)
            _guard(flow, task)
            application = flow.applications.get_application(task["application_id"])
            binding, original, library = _binding(flow, task, application)
            if resume_request_id is not None:
                _, predecessor_revision = _resume_predecessor(parent, resume_request_id, binding)
                _require(
                    intent.get("resume_failure_revision") == predecessor_revision,
                    "已接续的原失败记录已变化。",
                )
            _require(
                all(intent.get(key) == value for key, value in binding.items())
                and intent.get("id") == request_id
                and intent.get("method") == "normal_analysis"
                and intent.get("resume_request_id") == resume_request_id
                and all(existing.get(key) == value for key, value in binding.items())
                and existing.get("intent_revision") == digest(intent)
                and existing.get("review_revision") == digest(report)
                and existing.get("source_snapshot_revision")
                == report.get("source_snapshot_revision"),
                "已有重新核验记录或适用来源已变化。",
            )
            _report_current(flow, application, original, library, report)
            _require(
                digest(existing.get("result")) == digest(_recheck_result(report)),
                "已有重新核验结论与保存结果不同。",
            )
            return deepcopy(task)
        state, task = flow._checked(task_id, task_revision, allow_existing_handoff=True)
        _guard(flow, task)
        application = flow.applications.get_application(task["application_id"])
        binding, original, library = _binding(flow, task, application)
        if resume_request_id is not None:
            _require(resume_request_id != request_id, "接续须使用新的请求标识。")
            resume_from, resume_revision = _resume_predecessor(parent, resume_request_id, binding)
        if directory.exists():
            intent = _read(directory / "intent.json")
            _require(
                all(intent.get(key) == value for key, value in binding.items())
                and intent.get("id") == request_id
                and intent.get("method") == "normal_analysis"
                and intent.get("task_revision") == task_revision,
                "原核验请求与当前任务或资料已不同。",
            )
            _require(
                intent.get("resume_request_id") == resume_request_id
                and (
                    resume_from is None or intent.get("resume_failure_revision") == resume_revision
                ),
                "接续来源与原请求不同。",
            )
            if _failure_current(directory, intent):
                raise PortalDataError(
                    "match_refresh_failed",
                    "原核验已确认失败，记录已保留；请发起新的重新核验请求。",
                    409,
                )
            if not report_path.exists():
                raise PortalDataError(
                    "match_refresh_unknown", "原核验请求结果尚未核对，未重放模型调用。", 409
                )
            report = _read(report_path)
            run = False
        else:
            flow._check_other_execution_pending(state, task)
            _guard_pending(parent, task)
            _require(callable(flow.callbacks.get("refresh_match")), "正常重新核验链路尚未连接。")
            parent.mkdir(mode=0o700, exist_ok=True)
            directory.mkdir(mode=0o700)
            intent = {
                **binding,
                "id": request_id,
                "method": "normal_analysis",
                "task_revision": task_revision,
                "created_at": datetime.now(UTC).isoformat(),
            }
            if resume_from is not None:
                intent.update(
                    resume_request_id=resume_request_id,
                    resume_failure_revision=resume_revision,
                )
            helper.atomic_write_json(directory / "intent.json", intent)
            run = True
        original_requirements = _requirements(original)
        if run:
            # Reserve under the admission lock before Skip can release this job.
            active_key = (_root_key(flow), request_id)
            with _ACTIVE_LOCK:
                _ACTIVE_CALLBACKS.add(active_key)
    if run:
        try:
            returned = flow.callbacks["refresh_match"](
                deepcopy(application),
                original_requirements,
                directory / "analysis",
                **(
                    {"job_brief": deepcopy(original["job_brief"])}
                    if original.get("job_brief") is not None
                    else {}
                ),
                **({"resume_from": resume_from} if resume_from is not None else {}),
            )
            report = _read(report_path)
            _require(digest(returned) == digest(report), "分析返回值与保存结果不同。")
        except PortalDataError as error:
            if error.code in _VALIDATION_FAILURES or error.code == _STOPPED_DISPATCH:
                try:
                    with flow.applications.write_lock():
                        _require(_read(directory / "intent.json") == intent, "原核验请求已变化。")
                        proof = {"method": "caught_validation_error"}
                        if error.code == _STOPPED_DISPATCH:
                            proof = {
                                "method": "local_dispatch_refused",
                                "receipt_revision": _read(
                                    directory / "analysis" / "dispatch-stopped.json"
                                ).get("revision"),
                            }
                        _record_failure(directory, intent, error.code, proof)
                except (OSError, PortalDataError):
                    # Keep an incomplete operation unknown; never mask the original error.
                    pass
            raise
        finally:
            with _ACTIVE_LOCK:
                _ACTIVE_CALLBACKS.discard(active_key)
    with flow.applications.write_lock():
        state, task = flow._checked(task_id, task_revision, allow_existing_handoff=True)
        _guard(flow, task)
        application = flow.applications.get_application(task["application_id"])
        current_binding, original, library = _binding(flow, task, application)
        _require(current_binding == binding, "重新核验期间岗位或资料已变化。")
        _require(_read(directory / "intent.json") == intent, "原核验请求记录已变化。")
        if resume_request_id is not None:
            _, predecessor_revision = _resume_predecessor(parent, resume_request_id, binding)
            _require(
                intent.get("resume_failure_revision") == predecessor_revision,
                "接续期间原失败记录已变化。",
            )
        _require(digest(_read(report_path)) == digest(report), "分析保存结果已变化。")
        _report_current(flow, application, original, library, report)
        result = _recheck_result(report)
        receipt = {
            **binding,
            "id": request_id,
            "method": "normal_analysis",
            "intent_revision": digest(intent),
            "review_revision": digest(report),
            "source_snapshot_revision": report["source_snapshot_revision"],
            "reviewed_at": datetime.now(UTC).isoformat(),
            "reviewer": "codex_normal_pipeline",
            "result": result,
        }
        task.setdefault("match_rechecks", []).append(receipt)
        flow._save(state)
        return deepcopy(task)
