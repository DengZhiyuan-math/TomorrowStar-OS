"""Durable Codex handoffs over the existing complete-source version boundary.

Python validates and assembles. The calling Codex session owns agent execution.
No function in this module starts a model or grants factual review authority.
"""

from __future__ import annotations

import hashlib
import json
import re
from contextlib import suppress
from copy import deepcopy
from functools import wraps
from pathlib import Path

from ._vendor import job_apply_store as helper
from .application_full_latex import (
    BUSINESS_FIRST_INSTRUCTIONS,
    _application_rewrite_allowed,
    _application_usable,
    _invalid,
    generate_full_latex,
)
from .application_input_binding import configuration_current, configuration_revision
from .application_prism import archive_sources
from .career_portal_data import PortalDataError
from .validation.hashing import record_digest as digest

ENGINE_SHA256 = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
FEEDBACK_KEY = "presentation_feedback_revision"


FIXED_CONTRACT = "fixed-writing/v1"
CONTENT_CONTRACT = "content-writing/v1"
MAIN_INSTRUCTIONS = (
    "Use the fixed job brief, background judgments, inferences and delivered facts. "
    "Select and assign writing blocks; matching selections are suggestions. "
    "Own global blocks. Do not reinterpret the JD, rescore, audit credibility or write libraries."
)
WRITER_INSTRUCTIONS = (
    "Write only your assigned experience blocks from delivered facts and accepted inferences. "
    "Keep roles, numbers and status. Return used reference IDs, not a credibility report. "
    "Do not reinterpret the JD, rescore, repeat inference or change other blocks. "
    "Report missing details explicitly instead of inventing them."
)
REVIEW_INSTRUCTIONS = (
    "This is the single semantic review of newly generated wording. Trust fixed facts and "
    "accepted inferences. Check scope, plan focus, duplication, contradictions and clarity. "
    "Do not retrieve libraries, audit self-reports, reinterpret the JD or rescore. "
    "Return small located patches or return only affected experiences to their writers."
)


def _fixed(state):
    return state.get("generation_contract") in {FIXED_CONTRACT, CONTENT_CONTRACT}


def _content(state):
    return state.get("generation_contract") == CONTENT_CONTRACT


def _require_mutable(state):
    if _fixed(state) and state.get("adopted_draft"):
        raise _invalid("已采用的固定写作任务不能修改；请以当前稿明确准备新交付。")


def _fixed_inputs_revision(state):
    return digest(
        {
            key: state[key]
            for key in (
                "request",
                "payload",
                "configuration",
                "base_sha256",
                "application_snapshot",
            )
        }
    )


class _Captured(Exception):
    pass


def _directory(store, identifier):
    if not isinstance(identifier, str) or not re.fullmatch(r"[a-f0-9]{32}", identifier):
        raise _invalid("经历生成版本无效。")
    directory = store.root / identifier
    if directory.is_symlink() or directory.resolve() != directory:
        raise _invalid("经历生成目录不能重定向。")
    return directory


def _load(store, identifier):
    directory = _directory(store, identifier)
    state = json.loads(
        store._read_version_file(identifier, "experience-generation.json", 64_000_000)
    )
    request = state["request"]
    if _fixed(state):
        if state.get("fixed_inputs_revision") != _fixed_inputs_revision(state):
            raise _invalid("固定写作输入已变化，请恢复原交付或明确建立新任务。")
        plan = state.get("writing_plan")
        if plan is not None and plan.get("revision") != digest(
            {key: value for key, value in plan.items() if key != "revision"}
        ):
            raise _invalid("已交付写作计划已变化，请明确重新配置任务。")
        return directory, state
    store._task_current(
        state["application_id"],
        request["source_snapshot"],
        request["analysis"],
        state["configuration"],
    )
    inputs = request.get("task_inputs") or {}
    if inputs.get("information_library_root"):
        from pathlib import Path

        from .application_information import material_information_library, read_information_library

        application = store.applications.get_application(state["application_id"])
        library = material_information_library(
            application, read_information_library(Path(inputs["information_library_root"]))
        )
        if library.get("revision") != inputs.get("information_library_revision"):
            raise _invalid("确认资料已变化，请重新准备经历任务。")
        _validate_language_sources(state, application, library)
    if hashlib.sha256(archive_sources(request["latex_base"])).hexdigest() != state["base_sha256"]:
        raise PortalDataError("prism_source_changed", "底稿已变化，请保留片段并重新准备。", 409)
    return directory, state


def _validate_language_sources(state, application, library):
    from .application_full_latex import _language_sources

    selected = set(state["payload"]["analysis_selected_source_ids"])
    selected.update(sid for group in state.get("groups", []) for sid in group.get("source_ids", []))
    current = {source["source_id"]: source for source in _language_sources(application, library)}
    for source in state["payload"]["sources"]:
        if (
            source["source_id"] in selected
            and source.get("language_information_binding")
            and current.get(source["source_id"]) != source
        ):
            raise _invalid("已选语言资料已变化，请保留现有简历并重新准备受影响内容。")


def _save(directory, state):
    helper.atomic_write_json(directory / "experience-generation.json", state)
    return _public(state)


def _public(state):
    result = {
        key: deepcopy(state[key])
        for key in (
            "id",
            "kind",
            "status",
            "application_id",
            "analysis_binding",
            "resume_configuration_revision",
            "experiences",
            "mapping_required",
            "candidate_sha256",
            "content_revision",
            "review",
            "adopted_draft",
            "generation_contract",
            "fixed_inputs_revision",
            "writing_plan",
            "main_writer_id",
        )
        if key in state
    }
    result["completed_experience_ids"] = sorted(
        eid
        for eid, fragment in state.get("fragments", {}).items()
        if not _fixed(state) or fragment.get("status") == "complete" and not fragment.get("issues")
    )
    if _fixed(state):
        result["fragment_status"] = {
            eid: fragment["status"] for eid, fragment in state.get("fragments", {}).items()
        }
    if _content(state):
        result["material_requests"] = {
            eid: deepcopy(fragment["content_fragment"]["requests"])
            for eid, fragment in state.get("fragments", {}).items()
            if fragment.get("status") == "needs_material"
        }
    return result


def _serialized(operation):
    @wraps(operation)
    def run(store, *args, **kwargs):
        with store.applications.write_lock():
            return operation(store, *args, **kwargs)

    return run


def generation_state(store, identifier, *, task_inputs=None):
    """Read current handoff metadata without returning the complete source library."""
    state = _load(store, identifier)[1]
    if task_inputs is not None and state["request"].get("task_inputs") != task_inputs:
        raise PortalDataError(
            "resume_generation_reference_mismatch", "任务输入与已保存的写作交付不符。", 409
        )
    return _public(state)


@_serialized
def prepare_generation(store, identifier, revision, **request):
    """Prepare once for identical inputs; never execute the legacy model boundary."""
    request = deepcopy(request)
    request["information_library"] = request.get("information_library") or {}
    from .application_writing import is_content_delivery

    if is_content_delivery(request.get("analysis", {})):
        # Literal identity and education belong to the frozen TeX template.
        request["information_library"] = {}
    request.setdefault("retained_draft", None)
    fixed_delivery = all(
        isinstance(request.get("analysis", {}).get(key), dict)
        for key in ("job_brief", "material_packet", "inference_result")
    )
    configuration = None if fixed_delivery else store.configuration()
    application = None
    if not fixed_delivery:
        application = store._task_current(
            identifier, request["source_snapshot"], request["analysis"], configuration
        )
        if application["revision"] != revision:
            raise PortalDataError("conflict", "岗位记录已变化，请重新读取。", 409)
    identity = digest(
        {"application_id": identifier, "request": request, "generation_contract": FIXED_CONTRACT}
        if fixed_delivery
        else {"application_id": identifier, "request": request, "configuration": configuration}
    )
    for path in sorted(store.root.glob("*/experience-generation.json")):
        if path.is_symlink() or path.parent.is_symlink():
            continue
        saved = json.loads(path.read_text())
        if saved.get("request_revision") == identity:
            _, saved = _load(store, saved["id"])
            if saved.get("adopted_draft"):
                return store.draft(saved["adopted_draft"]["id"])
            if any(path.parent.glob("automatic-authors/*/failure.json")):
                # An author call failed here; a retry builds a fresh generation from
                # current inputs instead of replaying this plan (installed MC-11).
                continue
            return _public(saved)
    if fixed_delivery:
        configuration = store.configuration()
        from .application_writing import prepare_fixed_generation

        directory, payload, application, base_sha256 = prepare_fixed_generation(
            store, identifier, revision, request
        )
    else:
        captured = {}

        def capture(_store, directory, payload):
            captured.update(directory=directory, payload=deepcopy(payload))
            raise _Captured

        with suppress(_Captured):
            generate_full_latex(store, identifier, revision, **request, output_provider=capture)
        if not captured:
            raise _invalid("未产生经历写作交接。")
        directory, payload = captured["directory"], captured["payload"]
        base_sha256 = hashlib.sha256(archive_sources(request["latex_base"])).hexdigest()
    state = {
        "id": directory.name,
        "kind": "experience_handoff",
        "status": "codex_required",
        "application_id": identifier,
        "application_revision": revision,
        "analysis_binding": payload["analysis"],
        "resume_configuration_revision": configuration_revision(configuration),
        "configuration": configuration,
        "request_revision": identity,
        "request": request,
        "payload": payload,
        "base_sha256": base_sha256,
        "mapping_required": True,
        "experiences": [],
        "fragments": {},
    }
    if fixed_delivery:
        state["generation_contract"] = (
            CONTENT_CONTRACT if payload.get("content_plan") else FIXED_CONTRACT
        )
        state["application_snapshot"] = deepcopy(application)
        state["fixed_inputs_revision"] = _fixed_inputs_revision(state)
    return _save(directory, state)


def generation_context(store, identifier):
    """Main Codex's layout context, fixed retrieved facts and source locators."""
    _, state = _load(store, identifier)
    payload = state["payload"]
    if _content(state):
        return {
            **_public(state),
            "job": deepcopy(payload["job"]),
            "job_brief": deepcopy(payload["job_brief"]),
            # Scoring groups repeat the job_brief and never guide wording.
            "requirements": [
                {key: value for key, value in row.items() if key != "scoring_framework"}
                for row in payload["requirements"]
            ],
            "content_plan": deepcopy(payload["content_plan"]),
            "headline_required": payload.get("headline_required", False),
            "retained_content": deepcopy(payload.get("retained_content")),
            "retained_source_ids": deepcopy(payload.get("retained_source_ids", [])),
            "context_only_source_ids": deepcopy(payload.get("context_only_source_ids", [])),
            "retained_protected_scopes": deepcopy(payload.get("retained_protected_scopes", [])),
            "retained_omitted_experience_ids": deepcopy(
                payload.get("retained_omitted_experience_ids", [])
            ),
            "instructions": MAIN_INSTRUCTIONS
            + " Select and order delivered assignments; write global content as JSON only."
            + " When headline_required is true, supply headline as one ContentItem with a concise"
            + " career focus aligned with the delivered job_brief (for example Quantitative"
            + " Research or Data Science), grounded in delivered fact_refs or inference_refs."
            + " It describes the application's career focus, never an invented current job title,"
            + " credential, seniority or proficiency. Do not default to AI/ML for unrelated jobs."
            + " Keep protected human headline wording or its retained omission."
            + " When headline_required is false, omit headline; the old template has no slot.",
        }
    return {
        **_public(state),
        "job": deepcopy(payload["job"]),
        "role_understanding": deepcopy(payload.get("role_understanding")),
        **({"job_brief": deepcopy(payload["job_brief"])} if payload.get("job_brief") else {}),
        **(
            {"material_packet": deepcopy(payload["material_packet"])}
            if payload.get("material_packet")
            else {}
        ),
        **(
            {"inference_result": deepcopy(payload["inference_result"])}
            if payload.get("inference_result")
            else {}
        ),
        "selection_rationale": deepcopy(payload.get("selection_rationale", [])),
        "requirements": deepcopy(payload.get("requirements", [])),
        "instructions": MAIN_INSTRUCTIONS if _fixed(state) else BUSINESS_FIRST_INSTRUCTIONS,
        "organization_plan": deepcopy(state.get("organization_plan")),
        "base": payload["base"],
        "retained_output": deepcopy(payload.get("retained_output")),
        "update_context": deepcopy(payload.get("update_context")),
        "selected_source_ids": list(payload["analysis_selected_source_ids"]),
        "sources": [_source_metadata(source) for source in payload["sources"]],
    }


@_serialized
def configure_generation(
    store,
    identifier,
    *,
    groups=None,
    experiences=None,
    affected_group_indexes=None,
    context_impact_reason=None,
    organization_plan=None,
    writing_plan=None,
    main_writer_id=None,
):
    """Bind explicit body spans to experiences; never infer ownership from titles."""
    directory, state = _load(store, identifier)
    _require_mutable(state)
    if _content(state):
        from .application_experience_content import configure

        if groups is not None or experiences is not None or organization_plan is not None:
            raise _invalid("内容写作须使用 JSON 写作计划。")
        return configure(store, directory, state, writing_plan, main_writer_id=main_writer_id)
    payload = state["payload"]
    selected = set(payload["analysis_selected_source_ids"])
    sources = {row["source_id"]: row for row in payload["sources"]}
    if _fixed(state):
        selected = (
            {
                sid
                for row in [*groups, *experiences]
                if isinstance(row, dict) and row.get("disposition") != "omit"
                for sid in row.get("source_ids", [])
            }
            if isinstance(groups, list) and isinstance(experiences, list)
            else set()
        )
        if not selected <= set(sources):
            raise _invalid("写作只能采用本轮已交付来源。")
    update = payload.get("update_context", {})
    retained = payload.get("retained_output") or {"groups": update.get("retained_groups", [])}
    if not isinstance(groups, list) or not groups or not isinstance(experiences, list):
        raise _invalid("请提供明确的正文分组和经历来源对应。")
    if _fixed(state):
        starts = [group.get("start_line") if isinstance(group, dict) else None for group in groups]
        if any(type(start) is not int for start in starts) or starts != sorted(starts):
            raise _invalid("正文分组须按原稿位置排列；明确排序请使用写作计划。")
    # Languages are optional public library facts, selected only when this CV uses them.
    selected.update(
        sid
        for group in groups
        if isinstance(group, dict)
        for sid in group.get("source_ids", [])
        if sid in sources and sources[sid].get("language_information_binding")
    )
    if organization_plan is not None and not isinstance(organization_plan, dict):
        raise _invalid("全局写作计划须为明确的结构化对象。")
    positioning = (organization_plan or {}).get("positioning_group_indexes", [])
    if (
        not isinstance(positioning, list)
        or any(type(i) is not int or not 0 <= i < len(groups) for i in positioning)
        or len(set(positioning)) != len(positioning)
    ):
        raise _invalid("全局定位正文位置无效。")
    positioning = set(positioning)
    if positioning and (
        not isinstance(organization_plan.get("positioning_writer_id"), str)
        or not organization_plan["positioning_writer_id"].strip()
    ):
        raise _invalid("全局定位须记录实际写作者身份。")
    if positioning and not payload.get("role_understanding"):
        raise _invalid("更新全局定位前须先完成岗位业务目标分析。")
    if payload.get("role_understanding"):
        if not isinstance(organization_plan, dict) or any(
            not isinstance(organization_plan.get(key), str) or not organization_plan[key].strip()
            for key in ("summary_focus", "ordering_rationale")
        ):
            raise _invalid("请先按岗位业务目标说明摘要重点及经历排序依据。")
        for experience in experiences:
            if any(
                not isinstance(experience.get(key), str) or not experience[key].strip()
                for key in ("business_relevance", "focus")
            ) or experience.get("evidence_role") not in {"direct_domain", "transferable"}:
                raise _invalid("每段经历须说明业务关联、写作重点及直接或迁移证据角色。")
    identifiers, assigned, claimed = set(), set(), set()
    for experience in experiences:
        eid = experience.get("experience_id")
        source_ids, indexes = experience.get("source_ids"), experience.get("group_indexes")
        if (
            not isinstance(eid, str)
            or not eid.strip()
            or eid in identifiers
            or not isinstance(source_ids, list)
            or not source_ids
            or any(sid not in sources for sid in source_ids)
            or len(set(source_ids)) != len(source_ids)
            or not selected.intersection(source_ids)
            or not isinstance(indexes, list)
            or not indexes
            or any(
                type(i) is not int or not 0 <= i < len(groups) or i in assigned or i in positioning
                for i in indexes
            )
            or len(set(indexes)) != len(indexes)
        ):
            raise _invalid("经历、选中来源或正文归属存在歧义。")
        if _fixed(state) and eid in {"main", "retained"}:
            raise _invalid("经历标识不能占用全局或保留块归属。")
        if _fixed(state) and any(
            sources[sid].get("source_kind") in {"identity", "education"} for sid in source_ids
        ):
            raise _invalid("经历写作者不能拥有固定身份或学历块。")
        supporting = set()
        if state["request"].get("retained_draft"):
            for index in indexes:
                if index < len(retained["groups"]):
                    references = set(retained["groups"][index]["source_ids"])
                    if references & selected.intersection(source_ids):
                        supporting.update(references)
        if any(
            sid not in selected
            and sid not in supporting
            and sources[sid].get("source_kind") != "career_context"
            for sid in source_ids
        ):
            raise _invalid("经历、选中来源或正文归属存在歧义。")
        identifiers.add(eid)
        assigned.update(indexes)
        claimed.update(set(source_ids) & selected)
        for index in indexes:
            if not set(groups[index].get("source_ids", [])) <= set(source_ids):
                raise _invalid("经历正文引用了其他经历的来源。")
    # Selected identity/education may be fixed global groups, never writers' content.
    required = {
        sid for sid in selected if sources[sid].get("source_kind") not in {"identity", "education"}
    }
    if _fixed(state):
        claimed.update(
            sid for i in positioning for sid in groups[i].get("source_ids", []) if sid in required
        )
    if not _fixed(state) and claimed != required:
        raise _invalid("选中经历存在未分派来源。")
    from .application_full_latex import _body, _identity_facts, _identity_matches

    prefix, body, _ = _body(payload["base"])
    lines = body.splitlines(keepends=True)
    identity_sources = [
        source for source in sources.values() if source.get("source_kind") == "identity"
    ]
    identity_facts = _identity_facts(identity_sources)
    protected = set(payload.get("fixed_education_lines", []))
    # Header macros cannot be reliably classified by literal identity matching.
    # Keep the entire pre-section header outside editable positioning ownership.
    first_section = next(
        (
            i
            for i, line in enumerate(lines, 1)
            if re.match(r"\s*\\(?:section|cvsection)\*?(?:\[[^\]]*\])?\{[^{}\\]+\}", line)
        ),
        len(lines) + 1,
    )
    protected.update(range(1, first_section))
    for source in sources.values():
        if source.get("source_kind") in {"identity", "education"} and source.get(
            "retained_receipt_revision"
        ):
            protected.update(
                range(
                    source["retained_start_line"] - prefix.count("\n"),
                    source["retained_end_line"] - prefix.count("\n") + 1,
                )
            )
    covered = set()
    for index, group in enumerate(groups):
        start, end = group.get("start_line"), group.get("end_line")
        if type(start) is not int or type(end) is not int or not 1 <= start <= end <= len(lines):
            raise _invalid("正文位置无效。")
        span = set(range(start, end + 1))
        if covered & span:
            raise _invalid("正文分组重叠。")
        covered.update(span)
        if _fixed(state) and index in assigned and span & protected:
            raise _invalid("经历写作者不能修改固定身份或学历位置。")
        if index in positioning:
            references = [sources[sid] for sid in group.get("source_ids", []) if sid in sources]
            original = "".join(lines[start - 1 : end])
            if (
                span & protected
                or not references
                or not set(group["source_ids"]) <= selected
                or any(
                    source.get("source_kind") in {"identity", "education"} for source in references
                )
                or not _fixed(state)
                and (
                    any(
                        source.get("source_kind") in {"identity", "education"}
                        or source.get("source_kind") == "career_context"
                        and not source.get("application_trusted")
                        or not _application_usable(source)
                        or not _application_rewrite_allowed(source)
                        for source in references
                    )
                    or identity_sources
                    and _identity_matches(original, identity_sources)
                    or any(
                        isinstance(value, str)
                        and value in original
                        and value not in group.get("latex", "")
                        for value in identity_facts.values()
                    )
                )
            ):
                raise _invalid("全局定位只能使用已选经历证据，不能改写固定身份、学历或已接受页眉。")
        elif index not in assigned:
            if group.get("latex") != "".join(lines[start - 1 : end]):
                raise _invalid("未分派正文必须保留实际底稿。")
            references = [sources[sid] for sid in group.get("source_ids", []) if sid in sources]
            if not state["request"].get("retained_draft") and (
                not (
                    group.get("disposition") == "omit"
                    and references
                    and all(
                        source.get("source_kind") not in {"identity", "education"}
                        for source in references
                    )
                )
                and (
                    group.get("disposition") != "include"
                    or not references
                    or any(
                        source.get("source_kind") not in {"identity", "education"}
                        for source in references
                    )
                )
            ):
                raise _invalid("首次生成的未分派正文只能保留固定学历及联系信息，经历必须明确分派。")
    if covered != set(range(1, len(lines) + 1)):
        raise _invalid("正文未全部对应，不能静默省略。")
    allowed = set(
        update.get("source_affected_group_indexes", []) + update.get("pending_group_indexes", [])
    )
    if _fixed(state) and retained["groups"] and affected_group_indexes is not None:
        if not isinstance(affected_group_indexes, list) or any(
            type(i) is not int or not 0 <= i < len(groups) for i in affected_group_indexes
        ):
            raise _invalid("人工底稿须明确有限的修改块。")
        if affected_group_indexes and (
            not isinstance(context_impact_reason, str) or not context_impact_reason.strip()
        ):
            raise _invalid("请说明人工块的本次修改范围。")
        allowed.update(affected_group_indexes)
    if update.get("job_changed") or update.get("source_context_changed"):
        if not isinstance(affected_group_indexes, list) or any(
            type(i) is not int or not 0 <= i < len(groups) for i in affected_group_indexes
        ):
            raise _invalid("JD或资料上下文改变时须明确受影响正文。")
        allowed.update(affected_group_indexes)
        if not isinstance(context_impact_reason, str) or not context_impact_reason.strip():
            raise _invalid("请记录JD及新增资料的影响依据。")
    if retained["groups"]:
        if len(groups) != len(retained["groups"]):
            raise _invalid("保留人工稿的分组边界。")
        for i, (before, after) in enumerate(zip(retained["groups"], groups, strict=True)):
            if i not in allowed and before != after:
                raise _invalid("未受影响的人工文字及省略必须保留。")
    state["allowed_group_indexes"] = (
        sorted(allowed) if retained["groups"] else list(range(len(groups)))
    )
    state["context_impact_reason"] = context_impact_reason
    normalized_plan = (
        _writing_plan(state, groups, experiences, positioning, organization_plan, writing_plan)
        if _fixed(state)
        else None
    )
    previous = {row["experience_id"]: row for row in state["experiences"]}
    if _fixed(state):
        state["fragments"] = {
            eid: fragment for eid, fragment in state["fragments"].items() if eid in identifiers
        }
    configured = []
    for experience in experiences:
        item = deepcopy(experience)
        item["input_revision"] = digest(
            {
                "experience": {k: v for k, v in experience.items() if k != "input_revision"},
                "groups": [groups[i] for i in experience["group_indexes"]],
                "sources": [_fact_content(sources[sid]) for sid in experience["source_ids"]],
                "job": payload["job"],
                "role_understanding": payload.get("role_understanding"),
                **({"job_brief": payload["job_brief"]} if payload.get("job_brief") else {}),
                **(
                    {
                        "material_packet": _fact_content(
                            _scoped_material_packet(payload, experience["source_ids"])["sources"]
                        )
                    }
                    if payload.get("material_packet")
                    else {}
                ),
                **(
                    {
                        "inference_result": _fact_content(
                            _scoped_inference_result(payload, experience["source_ids"])
                        )
                    }
                    if payload.get("inference_result")
                    else {}
                ),
                "organization_plan": (
                    [
                        block
                        for block in normalized_plan["blocks"]
                        if block["owner"] == experience["experience_id"]
                    ]
                    if _fixed(state)
                    else organization_plan
                ),
                "selection_rationale": [
                    row
                    for row in payload.get("selection_rationale", [])
                    if row["source_id"] in experience["source_ids"]
                ],
                "requirements": _writer_requirements(payload, experience["source_ids"]),
            }
        )
        configured.append(item)
        if previous.get(item["experience_id"], {}).get("input_revision") != item["input_revision"]:
            state["fragments"].pop(item["experience_id"], None)
    # Recover only byte-identical factual inputs from earlier handoffs of this job.
    for path in sorted(store.root.glob("*/experience-generation.json")):
        if path.parent == directory or path.is_symlink() or path.parent.is_symlink():
            continue
        old = json.loads(path.read_text())
        if (
            old.get("application_id") != state["application_id"]
            or not _fixed(state)
            and old.get("configuration") != state["configuration"]
        ):
            continue
        for experience in configured:
            eid = experience["experience_id"]
            fragment = old.get("fragments", {}).get(eid)
            if (
                eid not in state["fragments"]
                and fragment
                and fragment["input_revision"] == experience["input_revision"]
            ):
                state["fragments"][eid] = deepcopy(fragment) | {"reused_from": old["id"]}
                state.setdefault("reads", {})[eid] = deepcopy(old.get("reads", {}).get(eid, []))
    state.update(
        groups=deepcopy(groups),
        experiences=configured,
        mapping_required=False,
        organization_plan=deepcopy(organization_plan),
    )
    if _fixed(state):
        state["writing_plan"] = normalized_plan
    state.pop("review", None)
    state.pop("candidate_sha256", None)
    return _save(directory, state)


def _allowed_refs(payload, source_ids):
    assigned = set(source_ids)
    refs = set(assigned)
    for inference in payload.get("inference_result", {}).get("requirements", []):
        facts = inference.get("facts", [])
        refs.update(fact["id"] for fact in facts if fact.get("source_id") in assigned)
        if facts and {fact["source_id"] for fact in facts} <= assigned:
            refs.add(inference["requirement_id"])
    return sorted(refs)


def _writing_plan(state, groups, experiences, positioning, organization_plan, proposed):
    if proposed is not None and not isinstance(proposed, dict):
        raise _invalid("写作计划须为结构化对象。")
    proposed = proposed or {}
    provided = proposed.get("blocks", [])
    if not isinstance(provided, list) or any(not isinstance(row, dict) for row in provided):
        raise _invalid("写作块计划无效。")
    overrides = {row.get("group_index"): row for row in provided}
    if len(overrides) != len(provided) or any(
        type(i) is not int or not 0 <= i < len(groups) for i in overrides
    ):
        raise _invalid("写作块计划存在重复或未知位置。")
    blocks = []
    for index, group in enumerate(groups):
        experience = next((row for row in experiences if index in row["group_indexes"]), None)
        owner = (
            experience["experience_id"]
            if experience
            else "main"
            if index in positioning
            else "retained"
        )
        override = overrides.get(index, {})
        block_id = "block-" + digest({"start": group["start_line"], "end": group["end_line"]})[:16]
        if override.get("owner", owner) != owner or override.get("block_id", block_id) != block_id:
            raise _invalid("写作块归属或标识与已分派正文不符。")
        focus = override.get(
            "focus",
            (experience or {}).get("focus")
            or (organization_plan or {}).get("summary_focus")
            or "Preserve the allocated block.",
        )
        length = override.get(
            "length",
            (experience or {}).get("length") or "Use only the allocated block; keep concise.",
        )
        if any(not isinstance(value, str) or not value.strip() for value in (focus, length)):
            raise _invalid("写作块须说明重点与篇幅。")
        blocks.append(
            {
                "block_id": block_id,
                "group_index": index,
                "owner": owner,
                "order": index,
                "focus": focus,
                "length": length,
                "allowed_refs": _allowed_refs(
                    state["payload"], (experience or group)["source_ids"]
                ),
            }
        )
    order = proposed.get("block_order", [row["block_id"] for row in blocks])
    if (
        not isinstance(order, list)
        or len(order) != len(blocks)
        or set(order) != {row["block_id"] for row in blocks}
    ):
        raise _invalid("写作计划顺序须恰好包含所有正文块。")
    for block in blocks:
        block["order"] = order.index(block["block_id"])
        if (
            block["owner"] == "retained"
            or state["request"].get("retained_draft")
            and block["group_index"] not in state["allowed_group_indexes"]
        ) and block["order"] != block["group_index"]:
            raise _invalid("固定及未授权人工块须保留原顺序。")
    result = {"schema_version": FIXED_CONTRACT, "blocks": blocks, "block_order": order}
    result["revision"] = digest(result)
    return result


def _scoped_material_packet(payload, source_ids):
    packet = payload["material_packet"]
    scoped = {
        "schema_version": packet["schema_version"],
        "parent_revision": packet["revision"],
        "scope_revision": packet["scope_revision"],
        "sources": {
            sid: deepcopy(row) for sid, row in packet["sources"].items() if sid in source_ids
        },
        "source_reads": {
            sid: deepcopy(row) for sid, row in packet["source_reads"].items() if sid in source_ids
        },
    }
    scoped["revision"] = digest(scoped)
    return scoped


def _inference_sources(inference):
    return {fact["source_id"] for fact in inference.get("facts", [])}


def _writer_requirements(payload, source_ids):
    assigned = set(source_ids)
    rows = []
    for row in payload.get("requirements", []):
        references = set(row.get("source_ids", []))
        if not references & assigned:
            continue
        if "inference" in row:
            # A cross-source conclusion cannot survive as a truncated inference.
            references |= _inference_sources(row["inference"])
            references.update(source["source_id"] for source in row.get("sources", []))
            references.update(source["source_id"] for source in row.get("citations", []))
            if not references <= assigned:
                continue
        rows.append(deepcopy(row))
    return rows


def _scoped_inference_result(payload, source_ids):
    result = payload["inference_result"]
    assigned = set(source_ids)
    scoped = {
        key: deepcopy(result[key])
        for key in ("schema_version", "policy", "job_brief_revision")
        if key in result
    }
    scoped["source_ids"] = sorted(assigned)
    scoped["requirements"] = [
        deepcopy(row)
        for row in result["requirements"]
        if _inference_sources(row) and _inference_sources(row) <= assigned
    ]
    # Parent packet/result revisions include unrelated experiences. Bind this
    # handoff to its complete local conclusions without carrying those revisions.
    scoped["revision"] = digest(scoped)
    return scoped


def writer_context(store, identifier, experience_id):
    _, state = _load(store, identifier)
    if _content(state):
        from .application_experience_content import writer_context as content_context

        return content_context(state, experience_id)
    experience = next(
        (x for x in state["experiences"] if x["experience_id"] == experience_id), None
    )
    if experience is None:
        raise _invalid("经历未分派。")
    return {
        **deepcopy(experience),
        "job": deepcopy(state["payload"]["job"]),
        "role_understanding": deepcopy(state["payload"].get("role_understanding")),
        **(
            {"job_brief": deepcopy(state["payload"]["job_brief"])}
            if state["payload"].get("job_brief")
            else {}
        ),
        **(
            {"material_packet": _scoped_material_packet(state["payload"], experience["source_ids"])}
            if state["payload"].get("material_packet")
            else {}
        ),
        **(
            {
                "inference_result": _scoped_inference_result(
                    state["payload"], experience["source_ids"]
                )
            }
            if state["payload"].get("inference_result")
            else {}
        ),
        "organization_plan": deepcopy(state.get("organization_plan")),
        "selection_rationale": [
            deepcopy(row)
            for row in state["payload"].get("selection_rationale", [])
            if row["source_id"] in experience["source_ids"]
        ],
        "requirements": _writer_requirements(state["payload"], experience["source_ids"]),
        "instructions": WRITER_INSTRUCTIONS if _fixed(state) else BUSINESS_FIRST_INSTRUCTIONS,
        **(
            {
                "writing_plan": {
                    "blocks": [
                        deepcopy(block)
                        for block in state["writing_plan"]["blocks"]
                        if block["owner"] == experience_id
                    ]
                },
                "allowed_refs": _allowed_refs(state["payload"], experience["source_ids"]),
            }
            if _fixed(state)
            else {}
        ),
        "groups": [deepcopy(state["groups"][i]) for i in experience["group_indexes"]],
        "previous_fragment": deepcopy(state["fragments"].get(experience_id)),
        "sources": [
            _source_metadata(source)
            for source in state["payload"]["sources"]
            if source["source_id"] in experience["source_ids"]
        ],
    }


@_serialized
def read_source(
    store, identifier, experience_id, source_id, *, offset=0, limit=16000, field="text"
):
    """Read an explicitly assigned source in bounded, non-truncated ranges."""
    directory, state = _load(store, identifier)
    if _content(state):
        raise _invalid("内容写作已经交付完整经历 JSON，无需再次读取来源。")
    context = writer_context(store, identifier, experience_id)
    if (
        source_id not in context["source_ids"]
        or type(offset) is not int
        or offset < 0
        or type(limit) is not int
        or not 1 <= limit <= 32000
        or field not in {"text", "boundaries"}
    ):
        raise _invalid("来源或读取范围不属于此经历。")
    source = next(row for row in state["payload"]["sources"] if row["source_id"] == source_id)
    text = source.get(field, "")
    if offset > len(text):
        raise _invalid("来源读取位置超出范围。")
    read = {
        "source_id": source_id,
        "offset": offset,
        "end": min(offset + limit, len(text)),
        "source_revision": source["source_revision"],
    }
    if field != "text":
        read["field"] = field
    state.setdefault("reads", {}).setdefault(experience_id, []).append(read)
    _save(directory, state)
    return {
        **_source_metadata(source),
        **read,
        "text": text[offset : offset + limit],
        "total": len(text),
        "complete": offset + limit >= len(text),
    }


@_serialized
def submit_fragment(
    store,
    identifier,
    experience_id,
    *,
    input_revision,
    groups=None,
    source_notes=None,
    issues=None,
    writer_id,
    status="complete",
    used_refs=None,
    block_id=None,
    latex_fragment=None,
    content_fragment=None,
):
    directory, state = _load(store, identifier)
    _require_mutable(state)
    context = writer_context(store, identifier, experience_id)
    if (
        input_revision != context["input_revision"]
        or not isinstance(writer_id, str)
        or not writer_id.strip()
    ):
        raise _invalid("片段输入已变化或缺写作者记录。")
    if _content(state):
        from .application_experience_content import submit

        if (
            any(
                value is not None
                for value in (groups, latex_fragment, block_id, source_notes, used_refs, issues)
            )
            or status != "complete"
        ):
            raise _invalid("内容写作者只能提交经历 JSON。")
        return submit(directory, state, context, content_fragment, writer_id)
    if _fixed(state):
        return _submit_fixed_fragment(
            store,
            directory,
            state,
            context,
            experience_id,
            input_revision=input_revision,
            groups=groups,
            issues=issues,
            writer_id=writer_id,
            status=status,
            used_refs=used_refs,
            block_id=block_id,
            latex_fragment=latex_fragment,
        )
    if not isinstance(source_notes, list) or not source_notes or not isinstance(issues, list):
        raise _invalid("片段须保留来源说明和未决问题。")
    reads = state.get("reads", {}).get(experience_id, [])
    for note in source_notes:
        if (
            not isinstance(note, dict)
            or note.get("source_id") not in context["source_ids"]
            or not isinstance(note.get("reason"), str)
            or not note["reason"].strip()
            or note.get("read") not in reads
            or note["read"]["source_id"] != note["source_id"]
        ):
            raise _invalid("来源说明须对应实际读取范围。")
    if not isinstance(groups, list) or len(groups) != len(context["groups"]):
        raise _invalid("片段不能增加或遗漏正文分组。")
    for index, original, group in zip(
        context["group_indexes"], context["groups"], groups, strict=True
    ):
        if index not in state["allowed_group_indexes"] and original != group:
            raise _invalid("未受影响的人工文字必须保留。")
        if (
            not isinstance(group, dict)
            or (group.get("start_line"), group.get("end_line"))
            != (original["start_line"], original["end_line"])
            or not set(group.get("source_ids", [])) <= set(context["source_ids"])
        ):
            raise _invalid("片段位置或来源不符。")
        if re.search(
            r"\\(?:documentclass|usepackage|input|include|begin\{document|end\{document)",
            group.get("latex", ""),
        ):
            raise _invalid("写作者只能交回正文片段。")
        if original.get("disposition") == "omit" and group != original:
            raise _invalid("保留人工省略，先由主 Codex 明确更新范围。")
    cited = {sid for group in groups for sid in group.get("source_ids", [])}
    if not cited <= {note["source_id"] for note in source_notes}:
        raise _invalid("每个实际引用来源都须保留读取及支持说明。")
    fragment = {
        "input_revision": input_revision,
        "groups": deepcopy(groups),
        "source_notes": deepcopy(source_notes),
        "issues": deepcopy(issues),
        "writer_id": writer_id,
    }
    state["fragments"][experience_id] = fragment
    helper.atomic_write_json(
        directory / ("fragment-" + digest(experience_id)[:16] + ".json"), fragment
    )
    state.pop("review", None)
    state.pop("candidate_sha256", None)
    return _save(directory, state)


def _submit_fixed_fragment(
    store,
    directory,
    state,
    context,
    experience_id,
    *,
    input_revision,
    groups,
    issues,
    writer_id,
    status,
    used_refs,
    block_id,
    latex_fragment,
):
    if (
        any(
            eid != experience_id and fragment["writer_id"] == writer_id
            for eid, fragment in state["fragments"].items()
        )
        or (state.get("organization_plan") or {}).get("positioning_writer_id") == writer_id
    ):
        raise _invalid("每段经历须有独立写作者，不能兼任其他经历或全局块。")
    if status not in ("complete", "missing_details", "failed") or not isinstance(issues, list):
        raise _invalid("片段须说明完成状态与缺项。")
    allowed = set(context["allowed_refs"])
    if (
        not isinstance(used_refs, list)
        or any(not isinstance(ref, str) or ref not in allowed for ref in used_refs)
        or len(set(used_refs)) != len(used_refs)
    ):
        raise _invalid("使用引用须属于本经历已交付输入。")
    if status == "complete" and issues or status != "complete" and not issues:
        raise _invalid("完成片段不能有未决问题；失败或缺项须明确说明。")
    blocks = context["writing_plan"]["blocks"]
    if block_id is not None and (len(blocks) != 1 or block_id != blocks[0]["block_id"]):
        raise _invalid("片段标识须对应唯一分派块。")
    if latex_fragment is not None:
        if groups is not None or len(blocks) != 1 or block_id != blocks[0]["block_id"]:
            raise _invalid("单块片段须对应唯一分派块。")
        groups = [deepcopy(context["groups"][0]) | {"latex": latex_fragment}]
    if groups is None and status != "complete":
        groups = deepcopy(context["groups"])
    if not isinstance(groups, list) or len(groups) != len(context["groups"]):
        raise _invalid("片段不能增加或遗漏正文分组。")
    for index, original, group in zip(
        context["group_indexes"], context["groups"], groups, strict=True
    ):
        if (
            not isinstance(group, dict)
            or not isinstance(group.get("latex"), str)
            or (group.get("start_line"), group.get("end_line"))
            != (original["start_line"], original["end_line"])
            or not set(group.get("source_ids", [])) <= set(context["source_ids"])
        ):
            raise _invalid("片段位置或来源不符。")
        if (
            index not in state["allowed_group_indexes"]
            and group != original
            or original.get("disposition") == "omit"
            and group != original
        ):
            raise _invalid("保留人工文字及省略。")
        if re.search(
            r"\\(?:documentclass|usepackage|input|include|begin\{document|end\{document)",
            group["latex"],
        ):
            raise _invalid("写作者只能交回正文片段。")
    fragment = {
        "input_revision": input_revision,
        "status": status,
        "used_refs": deepcopy(used_refs),
        "groups": deepcopy(groups),
        "issues": deepcopy(issues),
        "writer_id": writer_id,
        "block_ids": [row["block_id"] for row in blocks],
    }
    fragment["revision"] = digest(fragment)
    state["fragments"][experience_id] = fragment
    helper.atomic_write_json(
        directory / ("fragment-" + digest(experience_id)[:16] + ".json"), fragment
    )
    state.pop("review", None)
    state.pop("candidate_sha256", None)
    return _save(directory, state)


def _output(state):
    if _content(state):
        from .application_experience_content import output

        return output(state)
    if state["mapping_required"]:
        raise _invalid("先核验经历及正文对应。")
    groups = deepcopy(state["groups"])
    for experience in state["experiences"]:
        fragment = state["fragments"].get(experience["experience_id"])
        if (
            not fragment
            or fragment["input_revision"] != experience["input_revision"]
            or fragment["issues"]
            or _fixed(state)
            and fragment.get("status") != "complete"
        ):
            raise _invalid("经历片段缺失、失败或仍有未决问题，不能静默省略。")
        for index, group in zip(experience["group_indexes"], fragment["groups"], strict=True):
            groups[index] = group
    positioning = (state.get("organization_plan") or {}).get("positioning_group_indexes", [])
    cited = {sid for index in positioning for sid in groups[index].get("source_ids", [])}
    supported = {
        note["source_id"]
        for fragment in state["fragments"].values()
        for note in fragment.get("source_notes", [])
        if note["read"].get("field", "text") == "text"
        and note["read"]["end"] > note["read"]["offset"]
    }
    if not _fixed(state) and not cited <= supported:
        raise _invalid("全局定位引用须有经历写作者已核验的读取及支持说明。")
    output = {"groups": groups, "limitations": []}
    if state["payload"].get("update_context"):
        output["affected_group_indexes"] = state["allowed_group_indexes"]
        output["context_impact_reason"] = (
            state.get("context_impact_reason")
            or "Affected source groups mapped explicitly by Codex"
        )
    return output


def _generate(store, state, observer):
    return generate_full_latex(
        store,
        state["application_id"],
        store.applications.get_application(state["application_id"])["revision"],
        **state["request"],
        output_provider=lambda *_args: _output(state),
        plan_observer=observer,
        allow_retained_source_selection=True,
    )


@_serialized
def assemble_generation(store, identifier):
    directory, state = _load(store, identifier)
    _require_mutable(state)
    if _content(state):
        from .application_experience_content import assemble

        return assemble(store, directory, state)
    if _fixed(state):
        return _assemble_fixed(store, directory, state)
    captured = {}

    def capture(plan):
        captured.update(plan)
        raise _Captured

    with suppress(_Captured):
        _generate(store, state, capture)
    if not captured or captured["verification_queue"]:
        raise _invalid("组装稿仍有无法核验的正文。")
    latex = captured["latex_source"]
    candidate = hashlib.sha256(latex.encode()).hexdigest()
    helper.atomic_write_json(directory / "assembled-plan.json", captured)
    path = directory / "candidate-main.tex"
    path.write_text(latex)
    path.chmod(0o600)
    if state.get("candidate_sha256") != candidate:
        state.pop("review", None)
    state.update(candidate_sha256=candidate, status="review_required")
    return {
        **_save(directory, state),
        "latex_source": latex,
        "job": state["payload"]["job"],
        "fragments": deepcopy(state["fragments"]),
    }


def _assemble_fixed(store, directory, state):
    from .application_writing import assemble_fixed_plan

    payload = deepcopy(state["payload"]) | {"writing_plan": deepcopy(state["writing_plan"])}
    plan = assemble_fixed_plan(payload, _output(state))
    plan["block_versions"] = {
        block["block_id"]: {
            "owner": block["owner"],
            "input_revision": next(
                (
                    row["input_revision"]
                    for row in state["experiences"]
                    if row["experience_id"] == block["owner"]
                ),
                state["writing_plan"]["revision"],
            ),
            "fragment_revision": state["fragments"].get(block["owner"], {}).get("revision"),
        }
        for block in state["writing_plan"]["blocks"]
    }
    latex = plan["latex_source"]
    candidate = hashlib.sha256(latex.encode()).hexdigest()
    helper.atomic_write_json(directory / "assembled-plan.json", plan)
    path = directory / "candidate-main.tex"
    path.write_text(latex)
    path.chmod(0o600)
    if state.get("candidate_sha256") != candidate:
        state.pop("review", None)
    state.update(candidate_sha256=candidate, status="review_required")
    return {
        **_save(directory, state),
        "latex_source": latex,
        "job": deepcopy(state["payload"]["job"]),
        "fragments": deepcopy(state["fragments"]),
    }


@_serialized
def review_generation(
    store,
    identifier,
    *,
    candidate_sha256,
    reviewer_id,
    passed,
    issues,
    business_alignment=None,
    patches=None,
    rewrite_experience_ids=None,
    content_patch=None,
):
    directory, state = _load(store, identifier)
    _require_mutable(state)
    actual = hashlib.sha256((directory / "candidate-main.tex").read_bytes()).hexdigest()
    if (
        candidate_sha256 != state.get("candidate_sha256")
        or actual != candidate_sha256
        or type(passed) is not bool
        or not isinstance(issues, list)
        or passed
        and issues
        or not passed
        and not issues
        or not isinstance(reviewer_id, str)
        or not reviewer_id.strip()
    ):
        raise _invalid("终审须对应当前组装稿并记录具体问题。")
    if (
        any(fragment["writer_id"] == reviewer_id for fragment in state["fragments"].values())
        or (state.get("organization_plan") or {}).get("positioning_writer_id") == reviewer_id
        or state.get("main_writer_id") == reviewer_id
    ):
        raise _invalid("终审者须独立于经历写作者。")
    if _content(state):
        from .application_experience_content import review

        if patches is not None:
            raise _invalid("内容终审须使用 JSON 字段补丁。")
        return review(
            store,
            directory,
            state,
            candidate_sha256=candidate_sha256,
            reviewer_id=reviewer_id,
            passed=passed,
            issues=issues,
            content_patch=content_patch,
            rewrite_experience_ids=rewrite_experience_ids,
        )
    if _fixed(state):
        return _review_fixed(
            store,
            directory,
            state,
            candidate_sha256=candidate_sha256,
            reviewer_id=reviewer_id,
            passed=passed,
            issues=issues,
            patches=patches,
            rewrite_experience_ids=rewrite_experience_ids,
        )
    if state["payload"].get("role_understanding") and (
        not isinstance(business_alignment, str) or not business_alignment.strip()
    ):
        raise _invalid("终审须说明整份简历的业务目标、选材排序及方法定位是否一致。")
    review = {
        "candidate_sha256": candidate_sha256,
        "reviewer_id": reviewer_id,
        "passed": passed,
        "issues": deepcopy(issues),
        "input_revision": digest(_output(state)),
        "business_alignment": business_alignment,
    }
    state["review"] = review
    history = directory / "experience-reviews.jsonl"
    with history.open("a") as stream:
        stream.write(json.dumps(review, ensure_ascii=False) + "\n")
    history.chmod(0o600)
    return _save(directory, state)


def _review_fixed(
    store,
    directory,
    state,
    *,
    candidate_sha256,
    reviewer_id,
    passed,
    issues,
    patches,
    rewrite_experience_ids,
):
    patches = [] if patches is None else patches
    rewrites = [] if rewrite_experience_ids is None else rewrite_experience_ids
    if (
        not isinstance(patches, list)
        or not isinstance(rewrites, list)
        or any(not isinstance(eid, str) for eid in rewrites)
        or len(set(rewrites)) != len(rewrites)
    ):
        raise _invalid("终审补丁或返工经历无效。")
    if state.get("final_reviewer_id", reviewer_id) != reviewer_id:
        raise _invalid("此任务须由同一终审角色接续。")
    if passed and rewrites or patches and rewrites:
        raise _invalid("实质返工须退回指定经历，不能同时采用补丁或通过。")
    known = {row["experience_id"] for row in state["experiences"]}
    if not set(rewrites) <= known:
        raise _invalid("返工只能指向当前已分派经历。")
    updated = deepcopy(state)
    blocks = {row["block_id"]: row for row in state["writing_plan"]["blocks"]}
    touched = set()
    for patch in patches:
        if not isinstance(patch, dict) or set(patch) != {"block_id", "expected_latex", "latex"}:
            raise _invalid("终审只接受定位明确的局部块补丁。")
        block = blocks.get(patch["block_id"])
        if (
            not block
            or block["block_id"] in touched
            or block["owner"] == "retained"
            or block["group_index"] not in state["allowed_group_indexes"]
        ):
            raise _invalid("终审补丁不能修改固定、人工保护或未授权块。")
        index, owner = block["group_index"], block["owner"]
        if owner == "main":
            group = updated["groups"][index]
        else:
            experience = next(row for row in state["experiences"] if row["experience_id"] == owner)
            fragment = updated["fragments"].get(owner)
            if not fragment:
                raise _invalid("终审补丁缺少对应片段。")
            group = fragment["groups"][experience["group_indexes"].index(index)]
        if (
            group["latex"] != patch["expected_latex"]
            or group.get("disposition") != "include"
            or not isinstance(patch["latex"], str)
            or not patch["latex"].strip()
        ):
            raise _invalid("终审补丁原文或块状态不符。")
        if re.search(
            r"\\(?:documentclass|usepackage|input|include|begin\{document|end\{document)",
            patch["latex"],
        ):
            raise _invalid("终审不能提交完整文档或外部文件结构。")
        group["latex"] = patch["latex"]
        if owner != "main":
            fragment["revision"] = digest(
                {key: value for key, value in fragment.items() if key != "revision"}
            )
        touched.add(block["block_id"])
    if patches:
        # Validate all changed blocks before replacing persisted candidate files.
        from .application_writing import assemble_fixed_plan

        assemble_fixed_plan(
            deepcopy(updated["payload"]) | {"writing_plan": deepcopy(updated["writing_plan"])},
            _output(updated),
        )
        _assemble_fixed(store, directory, updated)
        for owner in {blocks[bid]["owner"] for bid in touched} - {"main"}:
            helper.atomic_write_json(
                directory / ("fragment-" + digest(owner)[:16] + ".json"),
                updated["fragments"][owner],
            )
    review = {
        "candidate_sha256": updated["candidate_sha256"],
        "original_candidate_sha256": candidate_sha256,
        "reviewer_id": reviewer_id,
        "passed": passed,
        "issues": deepcopy(issues),
        "patches": deepcopy(patches),
        "rewrite_experience_ids": list(rewrites),
        "input_revision": digest(_output(updated)),
    }
    updated["review"] = review
    updated["final_reviewer_id"] = reviewer_id
    if rewrites:
        for eid in rewrites:
            updated["fragments"].pop(eid, None)
        updated.pop("candidate_sha256", None)
        updated["status"] = "writing_required"
    with (directory / "experience-reviews.jsonl").open("a") as stream:
        stream.write(json.dumps(review, ensure_ascii=False) + "\n")
    (directory / "experience-reviews.jsonl").chmod(0o600)
    return _save(directory, updated)


@_serialized
def adopt_generation(store, identifier):
    directory, state = _load(store, identifier)
    review = state.get("review", {})
    if not review.get("passed") or review.get("input_revision") != digest(_output(state)):
        raise _invalid("组装稿尚未通过当前终审。")
    if (
        hashlib.sha256((directory / "candidate-main.tex").read_bytes()).hexdigest()
        != review["candidate_sha256"]
    ):
        raise _invalid("终审后的候选文件已变化。")
    if state.get("adopted_draft"):
        draft = store.draft(state["adopted_draft"]["id"])
        if _fixed(state) and (
            draft.get("final_review", {}).get("candidate_sha256") != review["candidate_sha256"]
            or review["candidate_sha256"] != state.get("candidate_sha256")
        ):
            raise _invalid("已采用版本与当前终审候选不符，请保留已有交付并核对。")
        return draft

    if _content(state):
        from .application_resume_versions import persist_content_generation

        plan = json.loads(store._read_version_file(identifier, "assembled-plan.json", 64_000_000))
        result = persist_content_generation(store, state, plan)
        state.update(
            adopted_draft={"id": result["id"], "draft_sha256": result["draft_sha256"]},
            status="adopted",
        )
        _save(directory, state)
        return result

    if _fixed(state):
        from .application_writing import persist_fixed_generation

        plan = json.loads(store._read_version_file(identifier, "assembled-plan.json", 64_000_000))
        if hashlib.sha256(plan["latex_source"].encode()).hexdigest() != review["candidate_sha256"]:
            raise _invalid("终审后的组装计划已变化。")
        result = persist_fixed_generation(store, state, plan)
        state.update(
            adopted_draft={"id": result["id"], "draft_sha256": result["draft_sha256"]},
            status="adopted",
        )
        _save(directory, state)
        return result

    def check(plan):
        if hashlib.sha256(plan["latex_source"].encode()).hexdigest() != review["candidate_sha256"]:
            raise _invalid("终审后的正文已变化。")

    result = _generate(store, state, check)
    state.update(
        adopted_draft={"id": result["id"], "draft_sha256": result["draft_sha256"]}, status="adopted"
    )
    _save(directory, state)
    return result


def _source_metadata(source):
    return {
        "readable_fields": {key: len(source.get(key, "")) for key in ("text", "boundaries")},
        "supporting_sources": [
            {
                key: row[key]
                for key in ("source_id", "source_name", "locator", "source_revision")
                if key in row
            }
            for row in source.get("supporting_sources", [])
        ],
    } | {
        key: deepcopy(source[key])
        for key in (
            "source_id",
            "source_name",
            "source_revision",
            "source_kind",
            "application_trusted",
            "language_information_binding",
            "locator",
            "title",
            "attribution",
            "resume_eligible",
            "rewrite_allowed",
        )
        if key in source
    }


def review_context(store, identifier):
    directory, state = _load(store, identifier)
    raw = (directory / "candidate-main.tex").read_bytes()
    if hashlib.sha256(raw).hexdigest() != state.get("candidate_sha256"):
        raise _invalid("终审稿已变化，请重新组装。")
    if _content(state):
        from .application_experience_content import review_context as content_review_context

        return content_review_context(state)
    update = state["payload"].get("update_context", {})
    retained = state["payload"].get("retained_output") or {
        "groups": update.get("retained_groups", state["groups"])
    }
    actual = _output(state)["groups"]
    return {
        **_public(state),
        "latex_source": raw.decode(),
        "job": deepcopy(state["payload"]["job"]),
        "role_understanding": deepcopy(state["payload"].get("role_understanding")),
        **(
            {"job_brief": deepcopy(state["payload"]["job_brief"])}
            if state["payload"].get("job_brief")
            else {}
        ),
        **(
            {"material_packet": deepcopy(state["payload"]["material_packet"])}
            if state["payload"].get("material_packet")
            else {}
        ),
        **(
            {"inference_result": deepcopy(state["payload"]["inference_result"])}
            if state["payload"].get("inference_result")
            else {}
        ),
        "organization_plan": deepcopy(state.get("organization_plan")),
        "selection_rationale": deepcopy(state["payload"].get("selection_rationale", [])),
        "requirements": deepcopy(state["payload"].get("requirements", [])),
        "instructions": REVIEW_INSTRUCTIONS if _fixed(state) else BUSINESS_FIRST_INSTRUCTIONS,
        "fragments": deepcopy(state["fragments"]),
        "manual_source": deepcopy(
            (state["request"].get("retained_draft") or {}).get("manual_source")
        ),
        "omissions": [
            {
                key: deepcopy(group[key])
                for key in ("title", "original", "rewritten", "reason")
                if key in group
            }
            for group in (
                state["payload"].get("retained_omissions", [])
                if _fixed(state)
                else (state["request"].get("retained_draft") or {}).get("omitted_groups", [])
            )
        ],
        "groups": deepcopy(state["groups"]),
        "source_selections": [
            {
                "group_index": index,
                "title": group["title"],
                "original_source_ids": deepcopy(before["source_ids"]),
                "actual_source_ids": deepcopy(group["source_ids"]),
                "original_sources": [
                    deepcopy(source)
                    for source in state["payload"]["sources"]
                    if source["source_id"] in before["source_ids"]
                ],
                "disposition": group["disposition"],
                "reason": group["reason"],
            }
            for index, (before, group) in enumerate(zip(retained["groups"], actual, strict=True))
        ],
    }


def _fact_content(value):
    if isinstance(value, dict):
        return {key: _fact_content(item) for key, item in value.items() if key != "source_revision"}
    if isinstance(value, list):
        return [_fact_content(item) for item in value]
    return value


def _existing_mismatch():
    return PortalDataError(
        "flow_existing_materials_mismatch",
        "已有终稿与原岗位或人工底稿不符，请保留记录并核验。",
        409,
    )


def read_completed(store, task, generation_id, export_id):
    """Read and validate immutable provenance; this function starts no operation."""
    from .application_prism import PrismClient

    _, generation = _load(store, generation_id)
    if generation.get("status") != "adopted" or not generation.get("adopted_draft"):
        raise _existing_mismatch()
    draft = adopt_generation(store, generation_id)
    request = generation["request"]
    retained = request.get("retained_draft") or {}
    prior = next(
        (
            row["result"]
            for row in reversed(task["artifacts"])
            if row.get("stage") == "resume"
            and row.get("adopted")
            and row.get("result", {}).get("kind") == "draft"
            and row["result"].get("origin") == "generated_latex"
            and row["result"].get("id") != draft["id"]
        ),
        None,
    )
    analysis = next(
        (
            row["result"]
            for row in reversed(task["artifacts"])
            if row.get("stage") == "analysis"
            and row.get("adopted")
            and row.get("result", {}).get("id") == task.get("analysis_id")
        ),
        None,
    )
    expected_inputs = deepcopy(task["inputs"])
    supplied_inputs = draft.get("task_inputs", {})
    feedback = supplied_inputs.get(FEEDBACK_KEY)
    if feedback is not None:
        if not isinstance(feedback, str) or re.fullmatch(r"[a-f0-9]{64}", feedback) is None:
            raise _existing_mismatch()
        if FEEDBACK_KEY in expected_inputs and expected_inputs[FEEDBACK_KEY] != feedback:
            raise _existing_mismatch()
        expected_inputs[FEEDBACK_KEY] = feedback
    if (
        analysis is None
        or request.get("analysis") != analysis
        or generation.get("application_id") != task["application_id"]
        or draft.get("application_id") != task["application_id"]
        or draft.get("analysis_binding", {}).get("analysis_id") != task["analysis_id"]
        or draft.get("analysis_binding", {}).get("jd_revision") != task["job_binding"]
        or draft.get("kind") != "draft"
        or draft.get("origin") != "generated_latex"
        or draft.get("verification_queue")
        or supplied_inputs != expected_inputs
        or request.get("task_inputs") != supplied_inputs
        or draft.get("base_checkpoint")
        != (
            request.get("latex_base")
            if prior is not None
            else {**request["latex_base"], "archive_sha256": generation["base_sha256"]}
        )
        or generation["adopted_draft"] != {"id": draft["id"], "draft_sha256": draft["draft_sha256"]}
        or hashlib.sha256(draft["latex_source"].encode()).hexdigest()
        != generation["review"]["candidate_sha256"]
    ):
        raise _existing_mismatch()
    if prior is not None:
        if (
            retained.get("id") != prior.get("id")
            or retained.get("draft_sha256") != prior.get("draft_sha256")
            or retained.get("source_checkpoint") != prior.get("source_checkpoint")
            or request.get("latex_base") != prior.get("source_checkpoint")
            or store.draft(prior["id"]) != retained
            or hashlib.sha256(archive_sources(prior["source_checkpoint"])).hexdigest()
            != prior["source_checkpoint"]["archive_sha256"]
        ):
            raise _existing_mismatch()
    else:
        _first_generation_lineage(task, request, draft, generation_id, export_id)
    store._current_export_draft(draft["id"], draft["draft_sha256"], supplied_inputs)
    if (
        hashlib.sha256(archive_sources(draft["source_checkpoint"])).hexdigest()
        != draft["source_checkpoint"]["archive_sha256"]
    ):
        raise _existing_mismatch()
    exported = store.read_export(export_id)
    if (
        exported.get("automatic_materials") is not True
        or exported.get("application_id") != task["application_id"]
        or exported.get("draft_id") != draft["id"]
        or exported.get("draft_sha256") != draft["draft_sha256"]
        or exported.get("task_inputs") != supplied_inputs
        or exported.get("source_checkpoint") != draft.get("source_checkpoint")
        or exported.get("analysis_binding") != draft.get("analysis_binding")
        or not configuration_current(
            exported.get("export_configuration_revision"),
            (store.prism_client or PrismClient()).configuration(),
        )
    ):
        raise _existing_mismatch()
    return {
        "generation": generation,
        "draft": draft,
        "export": exported,
        "lineage": "retained_draft" if prior is not None else "initial_generation",
    }


def _first_generation_lineage(task, request, draft, generation_id, export_id):
    """An initial attachment cannot replace any existing editor/material binding."""
    receipt = next(
        (
            row
            for row in task.get("material_reconnections", [])
            if row.get("generation_id") == generation_id and row.get("export_id") == export_id
        ),
        None,
    )
    before = receipt["previous"] if receipt else task
    if (
        request.get("retained_draft") is not None
        or (receipt and receipt.get("lineage") != "initial_generation")
        or any(
            before.get(key)
            for key in (
                "draft_id",
                "draft_sha256",
                "resume_id",
                "resume_sha256",
                "manual_source",
                "manual_latex_base",
                "source_checkpoint",
                "base_checkpoint",
                "prism",
                "experience_handoff",
            )
        )
        or any(before["stages"].get(stage, {}).get("artifact_id") for stage in ("resume", "export"))
        or (before.get("latex_base") and before["latex_base"] != request.get("latex_base"))
        or task.get("manual_source")
        or task.get("manual_latex_base")
        or any(
            row.get("stage") in {"resume", "export"}
            and row.get("adopted")
            and (not receipt or row.get("result", {}).get("id") not in {draft["id"], export_id})
            for row in task["artifacts"]
        )
    ):
        raise _existing_mismatch()
