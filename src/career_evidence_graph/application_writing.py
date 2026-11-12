"""Fixed writing inputs, structural assembly and persistence of one reviewed candidate.

This boundary never runs a model, reads current libraries or judges resume prose.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import re
from copy import deepcopy
from uuid import uuid4

from ._vendor import job_apply_store as helper
from .application_prism import archive_sources, source_snapshot, validate_archive
from .career_portal_data import PortalDataError
from .validation.hashing import record_digest as digest

CONTRACT = "fixed-writing/v1"


def is_fixed_delivery(analysis):
    return all(
        isinstance(analysis.get(key), dict)
        for key in ("job_brief", "material_packet", "inference_result")
    )


def is_content_delivery(analysis):
    """Semantic fact deliveries use content JSON through the existing handoff."""
    return is_fixed_delivery(analysis) and any(
        isinstance(row.get("record_context"), dict) and row["record_context"].get("fact_id")
        for row in analysis["material_packet"].get("sources", {}).values()
        if isinstance(row, dict)
    )


def _fixed_source_ids(snapshot):
    """Recognize fixed documentary inputs without copying them into writing content."""
    ids = {
        row["source_id"]
        for row in snapshot.get("items", [])
        if row.get("source_kind") in {"identity", "education"}
    }
    origin = snapshot.get("profile_source")
    if origin:
        ids.add(origin["id"] + ":profile.identity")
        ids.update(
            origin["id"] + f":profile.education[{index}]"
            for index, _ in enumerate((snapshot.get("profile") or {}).get("education", []))
        )
    return ids


def _unstructured_source_ids(snapshot, packet):
    fixed_ids = _fixed_source_ids(snapshot)
    return [
        source_id
        for source_id, row in packet["sources"].items()
        if not (row.get("record_context") or {}).get("fact_id")
        and source_id not in fixed_ids
        and row.get("source_kind") not in {"confirmed_information", "career_directory"}
    ]


def _resume_source_ids(analysis, packet):
    """The sources whose experiences the résumé planner may choose from.

    2026-11-12, G-Research: Volatility Wins supported five requirements, yet the
    analysis's separate selection left it out, so the planner never saw it. An
    experience a requirement cites as evidence is a candidate too; the planner still
    keeps 3 to 5.
    """
    selected = analysis.get("selected_source_ids")
    if not selected:
        # No selection means every delivered experience is already a candidate.
        return selected
    cited = [
        sid
        for row in analysis.get("requirements", [])
        for sid in row.get("source_ids") or []
        if ((packet["sources"].get(sid) or {}).get("record_context") or {}).get("fact_id")
    ]
    return list(dict.fromkeys([*selected, *cited]))


def _content_plan(
    application, snapshot, packet, inferences, template_revision, resume_source_ids=None
):
    from .application_resume_content import validate_plan

    assignments, source_facts = {}, {}
    unresolved = [
        sid
        for sid in _unstructured_source_ids(snapshot, packet)
        if resume_source_ids is None or sid in resume_source_ids
    ]
    if unresolved:
        raise PortalDataError(
            "resume_content_material_required",
            "已交付经历尚缺结构化事实，原资料已保留：" + ", ".join(unresolved),
            409,
        )
    # With whole-library matching the packet holds every experience; the résumé writes
    # only the experiences matching selected (installed MC-11 sent all 75).
    chosen = {
        (packet["sources"].get(sid, {}).get("record_context") or {}).get("candidate_id")
        for sid in resume_source_ids or []
    } - {None}
    for source_id, row in packet["sources"].items():
        context = row.get("record_context") or {}
        if not context.get("fact_id"):
            continue
        candidate, experience_id = context.get("candidate_id"), context.get("experience_id")
        if chosen and candidate not in chosen:
            continue
        if not candidate or not experience_id or row.get("candidate_id", candidate) != candidate:
            raise _invalid("经历事实须保留原经历与候选身份。")
        prefix = candidate + "::"
        facts = assignments.setdefault(
            experience_id,
            {
                "schema_version": "experience-facts/v1",
                "revision": context["content_revision"],
                "experience_id": experience_id,
                "candidate_id": candidate,
                "title": context["title"],
                **{
                    key: context.get(key)
                    for key in ("role", "organization", "start", "end", "location")
                },
                "sources": [],
                "facts": [],
            },
        )
        if (
            facts["candidate_id"] != candidate
            or facts["revision"] != context["content_revision"]
            or any(
                facts[key] != context.get(key)
                for key in ("title", "role", "organization", "start", "end", "location")
            )
        ):
            raise _invalid("经历事实不能混用身份或内容版本。")
        definitions = {entry["id"]: entry["locator"] for entry in context.get("sources", [])}
        for reference in context["source_refs"]:
            declaration = {
                "id": prefix + reference,
                "locator": definitions.get(reference, row["source_name"] + "#" + row["locator"]),
            }
            if declaration not in facts["sources"]:
                facts["sources"].append(declaration)
        fact_id = prefix + context["fact_id"]
        facts["facts"].append(
            {
                "id": fact_id,
                "text": row["text"],
                "source_refs": [prefix + reference for reference in context["source_refs"]],
                **{key: context[key] for key in ("responsibility", "status", "scope")},
            }
        )
        source_facts[source_id] = (candidate, fact_id)
    scoped_inferences = {facts["candidate_id"]: [] for facts in assignments.values()}
    for index, conclusion in enumerate(inferences["requirements"]):
        if conclusion.get("relation") != "supports":
            continue
        references = [source_facts.get(row["source_id"]) for row in conclusion.get("facts", [])]
        if not references or any(reference is None for reference in references):
            continue
        candidates = {reference[0] for reference in references}
        if len(candidates) != 1:
            continue
        candidate = next(iter(candidates))
        scoped_inferences[candidate].append(
            {
                "id": "inference:" + str(index) + ":" + conclusion["requirement_id"],
                "candidate_id": candidate,
                "text": conclusion["basis"]
                + " Expression scope: "
                + conclusion["expression_scope"],
                "fact_refs": list(dict.fromkeys(reference[1] for reference in references)),
            }
        )
    plan = {
        "schema_version": "resume-template-plan/v1",
        "application_id": application["id"],
        "template_revision": template_revision,
        "summary": [],
        "skills": [],
        "assignments": [],
    }
    for facts in assignments.values():
        derived = scoped_inferences[facts["candidate_id"]]
        assignment = {
            "schema_version": "experience-assignment/v1",
            "experience_id": facts["experience_id"],
            "candidate_id": facts["candidate_id"],
            "experience": facts,
            "inferences": derived,
            "allowed_fact_refs": [row["id"] for row in facts["facts"]],
            "allowed_inference_refs": [row["id"] for row in derived],
            "writing_requirements": [
                "Write in English. Preserve recorded responsibility, status and scope."
            ],
        }
        assignment["assignment_revision"] = digest(assignment)
        plan["assignments"].append(assignment)
    try:
        return validate_plan(plan).model_dump(mode="json")
    except ValueError as error:
        raise _invalid("内容写作需要固定模板及可定位的结构化经历事实。") from error


def _invalid(message="固定写作交付或正文结构不能核验。"):
    return PortalDataError("resume_model_invalid", message, 409)


def _checked_revision(value):
    return value.get("revision") == digest({k: v for k, v in value.items() if k != "revision"})


def fixed_education_lines(body, sources):
    """Locate already documented education independently of a model's source labels."""
    from .application_full_latex import (
        _education_lines,
        _prose_latex,
        _retained_education_text,
    )

    def contains_record(text, source):
        try:
            record = json.loads(source["text"])
            values = [record.get(key) for key in ("degree", "institution", "period")]
            if not all(isinstance(value, str) for value in values) or not all(values[:2]):
                return False
        except (KeyError, TypeError, ValueError, AttributeError):
            return False

        def words(value):
            return " " + " ".join(re.findall(r"\w+", _prose_latex(value).casefold())) + " "

        visible = words(text)
        # This locates existing documentary fields. Additional entries/content
        # in the same section do not negate a location or approve new wording.
        return all(words(value) in visible for value in values if value.strip())

    protected = set(_education_lines(body))
    headings = list(re.finditer(r"\\(?:section|cvsection)\*?(?:\[[^\]]*\])?\{[^{}\n]+\}", body))
    for index, heading in enumerate(headings):
        end = headings[index + 1].start() if index + 1 < len(headings) else len(body)
        chunk = body[heading.start() : end]
        if any(
            (_retained_education_text(source) or "\0") in chunk
            or contains_record(body[heading.end() : end], source)
            for source in sources
            if source.get("source_kind") == "education"
        ):
            protected.update(
                range(body[: heading.start()].count("\n") + 1, len(body[:end].splitlines()) + 1)
            )
    return protected


def _retained_structure_scopes(store, draft, content):
    """Keep the adopted human list structure across subsequent generations."""
    sections = {"summary": content["summary"], "skills": content["skills"]}
    if content["schema_version"] == "resume-template-content/v1":
        sections["headline"] = [content["headline"]] if content.get("headline") else []
    sections.update({row["id"]: row["items"] for row in content["experiences"]})
    inherited = draft.get("retained_protected_scopes", [])
    if (
        not isinstance(inherited, list)
        or any(not isinstance(scope, str) for scope in inherited)
        or len(inherited) != len(set(inherited))
    ):
        raise _invalid("人工列表保护范围不能核验。")
    scopes = set(inherited) & sections.keys()
    reference = draft.get("parent_content_ref")
    reconciliation = draft.get("content_reconciliation") or {}
    if reference and reconciliation.get("status") in {"mapped", "unchanged"}:
        parent, actual_sha = store._draft_document(reference["draft_id"])
        previous = parent.get("resume_content") or {}
        if (
            actual_sha != reference["draft_sha256"]
            or previous.get("revision") != reference["content_revision"]
        ):
            raise _invalid("人工列表的原内容版本不能核验。")
        baseline = {"summary": previous["summary"], "skills": previous["skills"]}
        if previous.get("schema_version") == "resume-template-content/v1":
            baseline["headline"] = [previous["headline"]] if previous.get("headline") else []
        baseline.update({row["id"]: row["items"] for row in previous["experiences"]})
        for scope, items in sections.items():
            if scope in baseline and [item["id"] for item in items] != [
                item["id"] for item in baseline[scope]
            ]:
                scopes.add(scope)
    return sorted(scopes)


def prepare_fixed_generation(store, identifier, revision, request):
    """Adopt explicit upstream delivery once; subsequent work consumes these bytes."""
    from .application_full_latex import _body, _sources
    from .application_job_brief import validate_job_brief

    analysis, snapshot = deepcopy(request["analysis"]), deepcopy(request["source_snapshot"])
    brief, packet, inferences = (
        analysis[key] for key in ("job_brief", "material_packet", "inference_result")
    )
    validate_job_brief(brief, brief["job"])
    if (
        analysis.get("application_id") != identifier
        or analysis.get("jd_revision") != digest(brief["job"])
        or not _checked_revision(snapshot)
        or snapshot["revision"]
        not in {
            analysis.get("source_snapshot_revision"),
            analysis.get("input_source_snapshot_revision"),
        }
        or packet.get("status") != "complete"
        or not _checked_revision(packet)
        or not _checked_revision(inferences)
        or inferences.get("job_brief_revision") != brief["revision"]
        or inferences.get("material_packet_revision") != packet["revision"]
        or not isinstance(request.get("task_inputs"), dict)
        or not request["task_inputs"]
    ):
        raise _invalid("岗位、匹配、推断和资料包须对应同一次固定交付。")
    expected = [
        {"judgment": row["judgment"], **row["inference"]} for row in analysis["requirements"]
    ]
    if inferences.get("requirements") != expected:
        raise _invalid("匹配和固定推断结论不一致。")
    application = store.applications.get_application(identifier)
    application = {**application, **brief["job"], "revision": revision}
    content_plan = None
    retained_content = None
    retained_delivered_ids = set()
    retained_sources = {}
    content_delivery = is_content_delivery(analysis)
    if content_delivery and not request.get("latex_base"):
        raise PortalDataError(
            "resume_template_required", "请接入包含固定信息和教育的 LaTeX 模板。", 409
        )
    base = deepcopy(request["latex_base"])
    archive = archive_sources(base)
    original = validate_archive(archive, base).decode("utf-8")
    if content_delivery:
        from .application_resume_render import validate_template

        try:
            validate_template(original)
        except ValueError as error:
            raise PortalDataError(
                "resume_template_invalid",
                "固定模板须明确标记摘要、技能和经历内容插入位置；原文件已保留。",
                409,
            ) from error
        content_plan = _content_plan(
            application,
            snapshot,
            packet,
            inferences,
            digest(original),
            _resume_source_ids(analysis, packet),
        )
    retained = request.get("retained_draft")
    if retained is not None:
        saved, sha = store._draft_document(retained["id"])
        if (
            saved["application_id"] != identifier
            or content_plan is None
            and saved["latex_source"] != original
            or (retained.get("draft_sha256") and retained["draft_sha256"] != sha)
        ):
            raise _invalid("人工底稿须对应此岗位已保存的完整版本。")
        retained = deepcopy(saved)
    if retained is not None and content_plan is not None:
        from .application_resume_content import content_revision, validate_content

        if not retained.get("resume_content"):
            raise PortalDataError(
                "resume_content_manual_merge_required",
                "现有人工 TeX 尚无内容映射；原稿已保留。",
                409,
            )
        # Unrecorded edits to the old build must not be replaced using stale JSON.
        if (
            hashlib.sha256(archive_sources(retained["source_checkpoint"])).hexdigest()
            != retained["source_checkpoint"]["archive_sha256"]
        ):
            raise PortalDataError(
                "prism_source_changed", "现有人工源有未接回的修改，已保留原稿。", 409
            )
        retained_content = validate_content(retained["resume_content"]).model_dump(mode="json")
        if retained_content["schema_version"] == "resume-content/v1":
            retained_content = {
                key: value
                for key, value in retained_content.items()
                if key not in {"profile", "education", "revision"}
            }
            retained_content.update(
                schema_version="resume-template-content/v1",
                template_revision=content_plan["template_revision"],
            )
            retained_content["revision"] = content_revision(retained_content)
        retained_delivered_ids = {
            row["record_context"]["experience_id"]
            for row in retained.get("generation_sources", [])
            if (row.get("record_context") or {}).get("fact_id")
        }
        protected_scopes = _retained_structure_scopes(store, retained, retained_content)
        required_refs = {}
        sections = [(key, None, retained_content[key]) for key in ("summary", "skills")]
        if retained_content.get("headline"):
            sections.append(("headline", None, [retained_content["headline"]]))
        sections.extend(
            (row["id"], row["candidate_id"], row["items"])
            for row in retained_content["experiences"]
        )
        for scope, candidate, items in sections:
            for item in items:
                if item["origin"] == "human" or scope in protected_scopes:
                    for reference in item["fact_refs"]:
                        required_refs.setdefault(reference, set()).add(
                            (scope, candidate) if candidate else None
                        )
        delivered_refs = {
            ref for row in content_plan["assignments"] for ref in row["allowed_fact_refs"]
        }
        missing_refs = required_refs.keys() - delivered_refs
        if missing_refs:
            from .application_material_sources import source_records as delivered_sources

            # Use only native facts in the already validated upstream snapshot.
            # A P04 projection must not hide those fixed facts or become a reread.
            native = {
                key: value
                for key, value in snapshot.items()
                if key not in {"material_packet_sources", "material_packet"}
            }
            for sid, source in delivered_sources(native).items():
                context = source.get("record_context") or {}
                candidate = context.get("candidate_id")
                fact_id = context.get("fact_id")
                if not candidate or not fact_id:
                    continue
                reference = candidate + "::" + fact_id
                if (
                    reference not in missing_refs
                    or sid in packet["sources"]
                    or not source.get("available")
                    or not source.get("resume_eligible")
                    or not source.get("match_eligible")
                    or source.get("candidate_id", candidate) != candidate
                    or any(
                        expected is not None
                        and expected != (context.get("experience_id"), candidate)
                        for expected in required_refs[reference]
                    )
                ):
                    continue
                retained_sources[sid] = deepcopy(source)
            if retained_sources:
                merged = {"sources": {**packet["sources"], **retained_sources}}
                content_plan = _content_plan(
                    application,
                    snapshot,
                    merged,
                    inferences,
                    digest(original),
                    _resume_source_ids(analysis, merged),
                )
                retained_order = {
                    row["id"]: index for index, row in enumerate(retained_content["experiences"])
                }
                content_plan["assignments"].sort(
                    key=lambda row: retained_order.get(row["experience_id"], len(retained_order))
                )
    fixed = (
        []
        if content_plan is not None
        else _sources(
            snapshot,
            deepcopy(request.get("information_library") or {}),
            application,
            original=original,
            retained_draft=retained,
        )
    )
    sources = {
        s["source_id"]: s for s in fixed if s.get("source_kind") in {"identity", "education"}
    }
    fixed_ids = _fixed_source_ids(snapshot) if content_plan is not None else set()
    for sid, row in {**packet["sources"], **retained_sources}.items():
        if sid != row.get("source_id") or not isinstance(row.get("text"), str):
            raise _invalid("资料包来源标识或正文不能核验。")
        if sid in sources or sid in fixed_ids:
            continue
        source = deepcopy(row)
        source.setdefault("source_kind", "career_context")
        source.setdefault("source_name", sid)
        source.setdefault("locator", sid)
        source.setdefault("title", sid)
        source.setdefault("attribution", "Saved facts; preserve recorded responsibility")
        source.update(application_trusted=True, resume_eligible=True)
        sources[sid] = source
    # Retained fixed/manual groups remain usable even when omitted from new selection.
    for group in (retained or {}).get("review_groups", []) + (retained or {}).get(
        "omitted_groups", []
    ):
        for source in group["sources"]:
            sources.setdefault(source["source_id"], deepcopy(source))
    _, body, _ = _body(original)
    payload = {
        "job": deepcopy(brief["job"]),
        "base": original,
        "body_lines": [
            {"line_number": i, "text": line}
            for i, line in enumerate(body.splitlines(keepends=True), 1)
        ],
        "body_line_count": len(body.splitlines(keepends=True)),
        "fixed_education_lines": sorted(fixed_education_lines(body, sources.values())),
        "sources": list(sources.values()),
        "analysis": {
            "analysis_id": analysis["id"],
            **{
                k: analysis[k]
                for k in (
                    "jd_revision",
                    "source_snapshot_revision",
                    "configuration_revision",
                    "policy_version",
                )
            },
        },
        "analysis_selected_source_ids": list(analysis.get("selected_source_ids", [])),
        "role_understanding": deepcopy(brief["role_understanding"]),
        "job_brief": brief,
        "material_packet": packet,
        "inference_result": inferences,
        "selection_rationale": deepcopy(analysis.get("selection_rationale", [])),
        "requirements": deepcopy(analysis["requirements"]),
        "retained_output": None,
    }
    if retained_sources:
        payload["retained_source_ids"] = list(retained_sources)
    if content_plan is not None:
        payload["context_only_source_ids"] = [
            sid
            for sid in _unstructured_source_ids(snapshot, packet)
            if sid not in analysis.get("selected_source_ids", [])
        ]
        for key in ("base", "body_lines", "body_line_count", "fixed_education_lines"):
            payload.pop(key, None)
    if retained and content_plan is None:
        from .application_full_latex import retained_contact_plan

        # Remap the actual current chunks. Historical omitted spans belong to
        # their earlier base and must never be reintroduced into this TeX.
        if retained.get("material_version_contract") == "local-material/v1":
            # Human versions have no AI group mapping. Preserve their complete
            # body as one retained block, without inventing an experience map
            # or changing facts, contact details, wording or order.
            payload["retained_output"] = {
                "groups": [
                    {
                        "title": "Retained human source",
                        "start_line": 1,
                        "end_line": payload["body_line_count"],
                        "source_ids": [],
                        "latex": body,
                        "disposition": "include",
                        "reason": "Preserve the explicit human version in full",
                    }
                ],
                "limitations": [],
            }
        else:
            payload["retained_output"] = retained_contact_plan(
                retained, original, retained["generation_sources"]
            )
        payload["retained_omissions"] = deepcopy(
            retained.get("retained_omissions", []) + retained.get("omitted_groups", [])
        )
    if content_plan is not None:
        payload["content_plan"] = content_plan
        if "%% TOMORROWSTAR_HEADLINE %%" in original:
            payload["headline_required"] = True
        if retained_content is not None:
            payload["retained_content"] = retained_content
            payload["retained_protected_scopes"] = protected_scopes
            present = {row["id"] for row in retained_content["experiences"]}
            omitted = retained.get("retained_omitted_experience_ids", [])
            if (
                not isinstance(omitted, list)
                or any(not isinstance(eid, str) or not eid.strip() for eid in omitted)
                or len(omitted) != len(set(omitted))
            ):
                raise _invalid("已保留的经历省略记录不能核验。")
            payload["retained_omitted_experience_ids"] = sorted(
                (set(omitted) | retained_delivered_ids) - present
            )
    directory = store.root / uuid4().hex
    directory.mkdir(mode=0o700)
    helper.atomic_write_json(directory / "source-snapshot.json", snapshot)
    helper.atomic_write_json(directory / "input.json", payload)
    (directory / "base-sources.json").write_bytes(archive)
    (directory / "base-sources.json").chmod(0o600)
    project = directory / "project"
    project.mkdir(mode=0o700)
    for name, encoded in json.loads(archive).items():
        path = project / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(base64.b64decode(encoded, validate=True))
        path.chmod(0o600)
    return directory, payload, application, hashlib.sha256(archive).hexdigest()


def assemble_fixed_plan(payload, output):
    """Check ownership/spans/structure; factual interpretation belongs to final review."""
    from .application_full_latex import _body, _validate_body

    prefix, body, suffix = _body(payload["base"])
    lines = body.splitlines(keepends=True)
    sources = {s["source_id"]: s for s in payload["sources"]}
    groups, covered = [], set()
    for row in output["groups"]:
        start, end = row.get("start_line"), row.get("end_line")
        ids, latex = row.get("source_ids"), row.get("latex")
        if (
            type(start) is not int
            or type(end) is not int
            or not 1 <= start <= end <= len(lines)
            or not isinstance(ids, list)
            or any(sid not in sources for sid in ids)
            or len(set(ids)) != len(ids)
            or not isinstance(latex, str)
            or row.get("disposition") not in {"include", "omit"}
            or not isinstance(row.get("title"), str)
            or not row["title"].strip()
            or not isinstance(row.get("reason"), str)
            or not row["reason"].strip()
        ):
            raise _invalid()
        span = set(range(start, end + 1))
        if span & covered:
            raise _invalid("正文块重叠。")
        covered |= span
        original = "".join(lines[start - 1 : end])
        groups.append(
            {
                "id": digest({"start": start, "end": end, "original": original}),
                "title": row["title"],
                "start_line": start,
                "end_line": end,
                "original": original,
                "rewritten": latex,
                "sources": [deepcopy(sources[s]) for s in ids],
                "attribution": [sources[s].get("attribution", "Unknown") for s in ids],
                "reason": row["reason"],
                "disposition": row["disposition"],
                "review_status": "review_required",
                "review_findings": {},
            }
        )
    if covered != set(range(1, len(lines) + 1)):
        raise _invalid("正文块未完整覆盖底稿。")
    if [g["start_line"] for g in groups] != sorted(g["start_line"] for g in groups):
        raise _invalid("正文块须按底稿位置登记，排序只能由写作计划指定。")
    protected = fixed_education_lines(body, sources.values())
    first_section = next(
        (i for i, line in enumerate(lines, 1) if re.match(r"\s*\\(?:section|cvsection)\*?", line)),
        len(lines) + 1,
    )
    protected.update(range(1, first_section))
    for group in groups:
        if set(range(group["start_line"], group["end_line"] + 1)) & protected and (
            group["rewritten"] != group["original"] or group["disposition"] != "include"
        ):
            raise _invalid("固定页眉和学历原文必须保留。")
    plan = payload["writing_plan"]
    blocks = {b["block_id"]: b for b in plan["blocks"]}
    order = plan["block_order"]
    if len(order) != len(groups) or set(order) != set(blocks):
        raise _invalid("写作计划未覆盖全部正文块。")
    for position, bid in enumerate(order):
        block = blocks[bid]
        index = block["group_index"]
        if type(index) is not int or not 0 <= index < len(groups):
            raise _invalid("正文块位置无效。")
        if block["owner"] == "retained" and position != index:
            raise _invalid("固定和人工保留块不能被重新排序。")
    if len({block["group_index"] for block in blocks.values()}) != len(groups):
        raise _invalid("正文块归属重复。")
    ordered = [groups[blocks[bid]["group_index"]] for bid in order]
    included = [g for g in ordered if g["disposition"] == "include"]
    text = "".join(g["rewritten"] for g in included)
    _validate_body(text, payload["base"])
    if not included:
        raise _invalid("不能生成空正文。")
    latex = prefix + text + suffix
    _body(latex)
    return {
        "latex_source": latex,
        "review_groups": included,
        "omitted_groups": [g for g in ordered if g["disposition"] == "omit"],
        "verification_queue": [],
        "limitations": deepcopy(output.get("limitations", [])),
        "block_mapping": [
            {
                "block_id": bid,
                "group_id": groups[blocks[bid]["group_index"]]["id"],
                "owner": blocks[bid]["owner"],
            }
            for bid in order
        ],
    }


def persist_fixed_generation(store, state, plan):
    """Save the reviewed assembled bytes once, without regenerating them."""
    review = state.get("review") or {}
    if (
        not review.get("passed")
        or review.get("candidate_sha256")
        != hashlib.sha256(plan["latex_source"].encode()).hexdigest()
    ):
        raise _invalid("保存稿须绑定唯一终审通过的候选版本。")
    directory = store.root / state["id"]
    base = state["request"]["latex_base"]
    archive = store._read_version_file(state["id"], "base-sources.json", 48_000_000)
    if hashlib.sha256(archive).hexdigest() != state["base_sha256"]:
        raise _invalid("底稿归档已变化。")
    project = directory / "project"
    before = source_snapshot(project, base["main"], source_policy="generated-latex-project/v1")
    if archive_sources(before) != archive:
        raise _invalid("候选保存位置已被编辑，请保留人工版本。")
    temporary = directory / "reviewed-main.tex"
    temporary.write_text(plan["latex_source"])
    temporary.chmod(0o600)
    os.replace(temporary, project / base["main"])
    checkpoint = source_snapshot(project, base["main"], source_policy="generated-latex-project/v1")
    generated = archive_sources(checkpoint)
    (directory / "latex-sources.json").write_bytes(generated)
    (directory / "latex-sources.json").chmod(0o600)
    payload = state["payload"]
    draft = {
        **deepcopy(plan),
        "id": state["id"],
        "origin": "generated_latex",
        "generation_contract": CONTRACT,
        "writing_plan": deepcopy(state["writing_plan"]),
        "final_review": deepcopy(state["review"]),
        "retained_omissions": deepcopy(state["payload"].get("retained_omissions", [])),
        "factual_review": "pending",
        "review_status": "review_required",
        "language": "en",
        "preparation_policy": "preparation-policy/v1.0",
        "application_id": state["application_id"],
        "application_revision": state["application_revision"],
        "task_inputs": deepcopy(state["request"]["task_inputs"]),
        "analysis_binding": deepcopy(payload["analysis"]),
        "job_context": deepcopy(payload["job"]),
        "generation_policy": deepcopy(state["configuration"]),
        "model_mode": store.model_mode,
        "information_library_revision": (state["request"].get("information_library") or {}).get(
            "revision"
        ),
        "base_checkpoint": {**base, "archive_sha256": state["base_sha256"]},
        "source_checkpoint": {
            **checkpoint,
            "archive_sha256": hashlib.sha256(generated).hexdigest(),
        },
        "generation_sources": deepcopy(payload["sources"]),
        "items": [],
        "context": [],
        "selected_source_ids": list(payload["analysis_selected_source_ids"]),
        "limitations": deepcopy(plan["limitations"]),
    }
    helper.atomic_write_json(directory / "draft.json", draft)
    helper.atomic_write_json(
        directory / "draft-integrity.json",
        {
            "schemaVersion": 1,
            "id": state["id"],
            "sha256": hashlib.sha256((directory / "draft.json").read_bytes()).hexdigest(),
        },
    )
    return store.draft(state["id"])


def validate_fixed_draft(store, draft):
    """Validate archived bytes and the single review receipt; no live source lookups."""
    archives = {}
    for name, key in (
        ("base-sources.json", "base_checkpoint"),
        ("latex-sources.json", "source_checkpoint"),
    ):
        raw = store._read_version_file(draft["id"], name, 48_000_000)
        if hashlib.sha256(raw).hexdigest() != draft[key]["archive_sha256"]:
            raise ValueError("Fixed archive changed")
        archives[key] = validate_archive(raw, draft[key]).decode()
    review = draft["final_review"]
    if (
        not review.get("passed")
        or review.get("candidate_sha256")
        != hashlib.sha256(archives["source_checkpoint"].encode()).hexdigest()
    ):
        raise ValueError("Fixed final review differs from candidate")
    if archives["source_checkpoint"] != draft["latex_source"]:
        raise ValueError("Fixed candidate bytes differ")
    groups = draft["review_groups"] + draft["omitted_groups"]
    mapping = {r["group_id"]: r["block_id"] for r in draft["block_mapping"]}
    by_block = {mapping[g["id"]]: g for g in groups}
    plan = draft["writing_plan"]
    indexed = [None] * len(groups)
    for block in plan["blocks"]:
        g = by_block[block["block_id"]]
        indexed[block["group_index"]] = {
            "title": g["title"],
            "start_line": g["start_line"],
            "end_line": g["end_line"],
            "source_ids": [s["source_id"] for s in g["sources"]],
            "latex": g["rewritten"],
            "disposition": g["disposition"],
            "reason": g["reason"],
        }
    rebuilt = assemble_fixed_plan(
        {
            "base": archives["base_checkpoint"],
            "sources": draft["generation_sources"],
            "writing_plan": plan,
        },
        {"groups": indexed, "limitations": draft["limitations"]},
    )
    for key in (
        "latex_source",
        "review_groups",
        "omitted_groups",
        "verification_queue",
        "block_mapping",
    ):
        if rebuilt[key] != draft[key]:
            raise ValueError("Fixed assembly differs")
    if draft["base_checkpoint"]["main"] != draft["source_checkpoint"]["main"] or {
        k: v
        for k, v in draft["base_checkpoint"]["files"].items()
        if k != draft["base_checkpoint"]["main"]
    } != {
        k: v
        for k, v in draft["source_checkpoint"]["files"].items()
        if k != draft["source_checkpoint"]["main"]
    }:
        raise ValueError("Fixed ancillary files changed")
