"""Read-only, source-bound job explanations; scores never establish qualification."""

from contextlib import suppress
from copy import deepcopy

from .application_match_scoring import calculate_match_score, combined_score, fit_in_band
from .career_portal_data import STATUS_LABELS, PortalDataError
from .job_screening import job_country
from .validation.hashing import record_digest as digest

POLICY_VERSION = "preparation-policy/v1.0"

PROGRESS_LABELS = {
    "not_started": "尚未建立准备任务",
    "draft": "待分析",
    "analyzing": "正在分析",
    "analysis_ready": "分析已保存",
    "resume_generating": "正在生成简历",
    "resume_ready": "简历待审阅",
    "draft_ready": "草稿待审阅",
    "exporting": "正在导出 PDF",
    "export_failed": "PDF 导出失败，等待明确重试",
    "materials_ready": "材料已确认",
    "failed": "阶段失败，等待明确重试",
    "cancelled": "已取消",
    "stale": "输入已变化，需同步",
    "materials_stale": "联系资料已变化，材料需更新",
    "queued": "已排队",
    "filling": "正在填写",
    "needs_input": "待补充",
    "needs_recheck": "结果待核验",
    "ready_for_review": "等待人工复核",
}


def adopted_analysis(task):
    return next(
        (
            a["result"]
            for a in reversed((task or {}).get("artifacts", []))
            if a.get("stage") == "analysis"
            and a.get("adopted")
            and a.get("result", {}).get("id") == task.get("analysis_id")
        ),
        None,
    )


def _validated_information(requirement, application, library):
    from .application_information import (
        information_context,
        validate_information_references,
        validate_information_source,
    )

    support = requirement.get("information_support")
    if not isinstance(support, dict) or not library:
        return None
    try:
        references = support.get("references")
        if not isinstance(references, list) or not references:
            return None
        validate_information_references(information_context(application, library), references)
        sources = [
            source
            for source in requirement.get("sources", [])
            if source.get("confirmed_information")
        ]
        validated = []
        for source in sources:
            validate_information_source(application, library, source)
            validated.extend(source["confirmed_information"]["references"])
        if not sources or any(reference not in validated for reference in references):
            return None
        return deepcopy(support)
    except (PortalDataError, ValueError, TypeError, KeyError):
        return None


def qualification_for(task, application, library=None, *, analysis=None, fixed_delivery=False):
    from .application_eligibility import qualification_status, task_eligibility

    analysis = analysis if analysis is not None else adopted_analysis(task)
    if fixed_delivery:
        library = None
    normal = not fixed_delivery and bool(
        (analysis or {}).get("retrieval") or (analysis or {}).get("normal_facts_path")
    )
    trusted = fixed_delivery or (
        (analysis or {}).get("application_library_policy") == "trusted-library/v1"
    )
    if analysis is not None:
        try:
            score = (
                deepcopy(analysis["score"])
                if fixed_delivery and isinstance(analysis.get("score"), dict)
                else calculate_match_score(analysis.get("requirements"))
            )
        except (PortalDataError, TypeError, ValueError):
            score = None
        if score is None or score["lower"] is None:
            return {
                "status": "unassessed",
                "conditions": [],
                "message": "未提取到可核验要求，不能认定符合资格。",
            }
    result = (
        task_eligibility(task, bind_inputs=True)
        if task
        else {"status": "analysis_required", "conditions": []}
    )
    for condition in result["conditions"]:
        requirement = (analysis or {}).get("requirements", [])[condition["requirement_index"]]
        if normal:
            condition["judgment"] = requirement["judgment"]
        if normal and library is not None and (condition.get("resolution") or {}).get("eligible"):
            from .application_information import ADDITIONAL_LANGUAGE_FACTS, _information_projection

            basis = condition["resolution"].get("qualification_basis")
            if basis is not None:
                fact = basis.get("fact")
                facts = (
                    ADDITIONAL_LANGUAGE_FACTS if fact == "additional_language_skills" else (fact,)
                )
                if not isinstance(fact, str) or basis.get("revision") != digest(
                    _information_projection(application, library, facts, include_unconfirmed=True)
                ):
                    condition["resolution"] = None
        if library is not None and condition.get("resolution") and not normal:
            from .application_information import (
                applicable_answers,
                condition_information_binding,
                material_information_context,
            )

            current_basis = condition_information_binding(condition, application, library)
            recorded_basis = condition["resolution"].get("qualification_basis")
            if recorded_basis is not None:
                if current_basis != recorded_basis:
                    condition["resolution"] = None
            elif current_basis is not None and any(
                record.get("state") == "missing"
                for record in applicable_answers(
                    library.get("records", []),
                    current_basis["fact"],
                    material_information_context(application),
                    include_unconfirmed=True,
                )
            ):
                # Legacy statements have no per-fact basis. An explicitly withdrawn
                # applicable language fact cannot remain confirmed by that old receipt.
                condition["resolution"] = None
        if condition["judgment"] == "gap":
            condition["status"] = "conflict"
        elif condition.get("resolution"):
            condition["status"] = "supported" if condition["resolution"]["eligible"] else "conflict"
        elif trusted and condition["judgment"] == "supported":
            condition["status"] = "supported"
        else:
            condition["status"] = "needs_input"
        condition["explanation"] = (
            "原分析记录明确硬条件冲突；匹配分或人工调序不能消除该冲突。"
            if condition["judgment"] == "gap"
            else "本次用户事实说明确认不符合该硬条件；匹配分或人工调序不能消除冲突。"
            if condition["status"] == "conflict"
            else "本次用户事实说明已确认；该结论独立于文档匹配分。"
            if condition.get("resolution")
            else "文档支持不等于已确认的申请事实，请先核对通用信息库或补充说明。"
        )
        if trusted and not condition.get("resolution") and condition["judgment"] != "gap":
            condition["explanation"] = requirement["explanation"]
        framework = requirement.get("scoring_framework")
        if (
            framework
            and framework["group"]["operator"] == "any"
            and condition["status"] == "conflict"
        ):
            condition["explanation"] = (
                "该子条件存在事实不符；资格按 JD 原分组汇总，其他替代条件仍可满足。"
            )
        if normal:
            information = _validated_information(requirement, application, library)
            if information:
                condition["library"] = information
                if condition["judgment"] != "gap" and condition["status"] != "conflict":
                    condition["status"] = information["status"]
                    condition["explanation"] = information["explanation"]
        elif library is not None:
            from .application_information import condition_from_library

            country = application.get("country") or job_country(application)
            information = condition_from_library(
                {"text": condition["text"], "hard_condition": True},
                application | {"country": country} if country is not None else application,
                library,
            )
            if information:
                condition["library"] = information
                if (
                    condition["judgment"] != "gap"
                    and condition["status"] != "conflict"
                    and (
                        information["status"] != "needs_input"
                        or not condition.get("resolution")
                        or information["references"]
                    )
                ):
                    condition["status"] = information["status"]
                    condition["explanation"] = information["explanation"]
    if result["conditions"]:
        result["status"] = qualification_status(
            (analysis or {}).get("requirements", []), result["conditions"]
        )
    result["message"] = {
        "analysis_required": "请先完成岗位分析；尚无资格结论。",
        "unassessed": "未提取到可核验要求，不能认定符合资格。",
        "not_specified": "JD 未列出独立硬条件；这不代表已确认全部申请资格。",
        "supported": "本次列出的硬条件已核验支持。",
        "needs_input": "资格待补充：明确必需条件尚需适用的已确认事实。",
        "conflict": "存在硬条件冲突，保留原理由并暂停本岗简历生成。",
    }[result["status"]]
    return result


def _material_read_coverage(packet):
    reads = packet.get("source_reads", {})
    reads = reads if isinstance(reads, dict) else {}
    ranges_total = ranges_complete = sources_complete = 0
    for reading in reads.values():
        if not isinstance(reading, dict):
            continue
        ranges = reading.get("ranges", [])
        ranges = ranges if isinstance(ranges, list) else []
        ranges_total += len(ranges)
        end = 0
        valid = True
        for row in ranges:
            if (
                not isinstance(row, dict)
                or type(row.get("start")) is not int
                or type(row.get("end")) is not int
                or not 0 <= row["start"] <= end < row["end"]
                or row.get("method") not in {"complete_source", "excerpt_read"}
            ):
                valid = False
                continue
            end = row["end"]
            ranges_complete += 1
        if valid and reading.get("status") == "complete" and end == reading.get("original_chars"):
            sources_complete += 1
    total = len(set(reads) | set(packet.get("sources", {})))
    complete = packet.get("status") == "complete" and sources_complete == total
    return {
        "status": "complete" if complete else "incomplete",
        "complete": complete,
        "sources_total": total,
        "sources_complete": sources_complete,
        "ranges_total": ranges_total,
        "ranges_complete": ranges_complete,
    }


def _resume_coverage(task, requirements, resume_sources=None):
    identifiers = {
        (task or {}).get("draft_id"),
        (task or {}).get("resume_id"),
        (task or {}).get("stages", {}).get("resume", {}).get("artifact_id"),
    } - {None}
    material = next(
        (
            row.get("result", {})
            for row in reversed((task or {}).get("artifacts", []))
            if row.get("adopted")
            and row.get("stage") in {"resume", "export"}
            and row.get("result", {}).get("id") in identifiers
        ),
        None,
    )
    result = {
        "status": "not_generated" if material is None else "unavailable",
        "requirements_total": len(requirements),
        "requirements_used": None,
        "percent": None,
        "used_source_ids": [],
    }
    if material is None:
        return result
    used = material.get("used_source_ids")
    if not used and resume_sources is not None:
        # Results saved before 2026-10-31 recorded no sources for template content.
        with suppress(PortalDataError, OSError, ValueError, KeyError, TypeError):
            # An export result names its PDF; the sources belong to the task's draft.
            used = resume_sources((task or {}).get("draft_id") or material.get("id"))
    if not isinstance(used, list) or any(not isinstance(sid, str) for sid in used):
        return result
    used = set(used)
    covered = sum(
        bool(used & {source.get("source_id") for source in row.get("sources", [])})
        for row in requirements
    )
    return result | {
        "status": "generated",
        "requirements_used": covered,
        "percent": round(100 * covered / len(requirements), 2) if requirements else None,
        "used_source_ids": sorted(used),
    }


def _short_basis(row):
    inference = row.get("inference", {})
    expected = {
        "supports": "supported",
        "partial_support": "partial",
        "contradicts": "gap",
        "unresolved": "unknown",
    }.get(inference.get("relation"))
    return (
        inference.get("basis") or row.get("explanation", "")
        if expected == row.get("judgment")
        else row.get("explanation", "")
    )


def _business_summary(brief, requirements):
    understanding = brief.get("role_understanding", {})
    groups = []
    for group in brief.get("groups", []):
        rows = [
            row
            for row in requirements
            if row.get("scoring_framework", {}).get("group", {}).get("id") == group.get("id")
        ]
        groups.append(
            {
                "id": group.get("id"),
                "label": group.get("label"),
                "supported": list(
                    dict.fromkeys(
                        _short_basis(row) for row in rows if row.get("judgment") == "supported"
                    )
                ),
                "concerns": [
                    {
                        "judgment": row.get("judgment", "unknown"),
                        "basis": _short_basis(row),
                    }
                    for row in rows
                    if row.get("judgment") != "supported"
                ],
            }
        )
    return {
        "business_object": brief.get("business_object"),
        "business_objective": understanding.get("business_objective"),
        "work_outputs": deepcopy(understanding.get("work_outputs", [])),
        "groups": groups,
    }


def job_explanation(
    application,
    task=None,
    *,
    current_inputs,
    library=None,
    source_provider=None,
    policy_version=POLICY_VERSION,
    fixed_delivery=False,
    resume_sources=None,
):
    from .application_input_binding import (
        job_input_revision,
        retained_configuration_inputs,
        reusable,
    )

    saved_inputs = task["inputs"] if task else {}
    if task:
        current_inputs = retained_configuration_inputs(task, current_inputs)
    analysis = adopted_analysis(task)
    requirements = deepcopy((analysis or {}).get("requirements", []))
    from .application_match_recheck import (
        current_match_recheck,
        latest_fixed_recheck,
        normal_analysis_current,
    )

    recheck = (
        latest_fixed_recheck(task)
        if fixed_delivery
        else current_match_recheck(
            task, library, application=application, source_provider=source_provider
        )
    )
    if recheck:
        requirements = deepcopy(recheck["result"]["requirements"])
    effective_analysis = recheck["result"] if recheck else analysis
    normal_refresh = bool(
        not fixed_delivery
        and (task or {}).get("match_rechecks")
        and task["match_rechecks"][-1].get("method") == "normal_analysis"
    )
    normal = not fixed_delivery and (
        bool((effective_analysis or {}).get("retrieval")) or normal_refresh
    )
    if fixed_delivery:
        library = None
    normal_stale = bool(
        normal
        and not normal_analysis_current(
            effective_analysis or {}, application, library, source_provider
        )
    )
    if normal_refresh:
        from .application_match import match_configuration_revision

        normal_stale = normal_stale or (
            (effective_analysis or {}).get("configuration_revision")
            != match_configuration_revision()
            or (effective_analysis or {}).get("jd_revision") != job_input_revision(application)
        )
    if normal:
        for requirement in requirements:
            if normal_stale or (
                requirement.get("information_support")
                and not _validated_information(requirement, application, library)
            ):
                if requirement["judgment"] != "gap":
                    requirement["judgment"] = "unknown"
                    requirement["explanation"] = (
                        "适用的确认信息已变化，须重新核验；保留原分析历史。"
                    )
                requirement.pop("information_support", None)
    try:
        # Saved verdicts are rescored with the current rule (decided 2026-10-31), so a
        # rule change also shows on jobs whose materials are already fixed.
        score = calculate_match_score(requirements) if analysis else None
    except (PortalDataError, KeyError, TypeError, ValueError):
        score = None
        requirements = []
    documentary_score = (
        calculate_match_score(analysis["requirements"]) if recheck else deepcopy(score)
    )
    qualification = qualification_for(
        task,
        application,
        library,
        # Fixed materials keep the qualification execution uses; a recheck is display only.
        analysis=analysis
        if fixed_delivery
        else {**effective_analysis, "requirements": requirements, "normal_facts_path": normal}
        if effective_analysis
        else None,
        fixed_delivery=fixed_delivery,
    )
    conflicted_conditions = {
        row["requirement_index"]
        for row in qualification["conditions"]
        if row.get("status") == "conflict"
    }
    factual_rechecks = []
    if normal:
        for index, requirement in enumerate(requirements):
            information = _validated_information(requirement, application, library)
            if information:
                requirement["library"] = information
                factual_rechecks.append({"requirement_index": index, **deepcopy(information)})
    elif library is not None and score is not None:
        from .application_information import condition_from_library, material_information_context

        for index, requirement in enumerate(requirements):
            information = condition_from_library(
                requirement, material_information_context(application), library
            )
            if information and information.get("fact") in {
                "education_student_status",
                "education_quantitative_degree",
                "internship_availability",
                "language_english_fluent",
                "additional_language_skills",
            }:
                requirement["library"] = information
                factual_rechecks.append({"requirement_index": index, **deepcopy(information)})
                if (
                    information["status"] == "supported"
                    and requirement["judgment"] != "gap"
                    and index not in conflicted_conditions
                ):
                    requirement["documentary_reason"] = deepcopy(requirement)
                    if requirement.get("citation_warning"):
                        requirement["documentary_citation_warning"] = requirement.pop(
                            "citation_warning"
                        )
                    requirement["documentary_judgment"] = requirement["judgment"]
                    requirement["documentary_explanation"] = requirement.get("explanation")
                    requirement["judgment"] = "supported"
                    requirement["explanation"] = information["explanation"]
        score = calculate_match_score(requirements)
    fresh = task is None or (
        task["job_binding"] == job_input_revision(application)
        and (
            bool(recheck) and not normal_stale
            if normal_refresh
            else reusable("analysis", saved_inputs, current_inputs).reusable
        )
    )
    materials_fresh = fresh and (
        task is None or reusable("materials", saved_inputs, current_inputs).reusable
    )
    status = "not_started" if task is None else task["status"] if fresh else "stale"
    if (
        fresh
        and not materials_fresh
        and status in {"draft_ready", "resume_ready", "materials_ready"}
    ):
        status = "materials_stale"
    preferences = {
        key: application.get(key, "")
        for key in ("personal_priority", "target_company", "compensation_priority")
    }
    preferences["unknown"] = [
        label
        for key, label in (
            ("target_company", "company"),
            ("compensation_priority", "salary"),
            ("personal_priority", "personal_priority"),
        )
        if not preferences[key]
    ]
    # Decided 2026-10-31: sol and Opus scores are averaged; a large gap needs review.
    score, model_scores = combined_score(score, effective_analysis, requirements)
    for requirement in requirements:
        # The card shows the in-band fit the score used, not the model's raw number.
        fit = fit_in_band(requirement.get("judgment"), requirement.get("fit_score"))
        if fit is not None and not requirement.get("citation_warning"):
            requirement["fit"] = fit
    result = {
        "application_id": application["id"],
        "task_id": (task or {}).get("id"),
        "policy_version": policy_version,
        "match_policy_version": "documentary-match/v1",
        "fresh": fresh,
        "materials_fresh": materials_fresh,
        "score": score,
        "model_scores": model_scores,
        "documentary_score": documentary_score,
        "match_recheck_stale": not fixed_delivery
        and (normal_stale or bool((task or {}).get("match_rechecks") and not recheck)),
        "match_recheck": {
            key: recheck[key]
            for key in ("id", "library_revision", "source_snapshot_revision", "reviewed_at")
        }
        if recheck
        else None,
        "score_basis": "documentary-and-confirmed-facts/v1"
        if factual_rechecks
        else "documentary-match/v1",
        "factual_rechecks": factual_rechecks,
        "qualification": qualification,
        "progress": {
            "status": status,
            "label": "草稿审阅已记录"
            if status == "draft_ready"
            and ((task or {}).get("draft_review") or {}).get("status") == "reviewed"
            else PROGRESS_LABELS.get(status, "状态待核验"),
            "application_status": application.get("status"),
            "application_label": STATUS_LABELS.get(application.get("status"), "原记录状态待核验"),
        },
        "reasons": requirements,
        "preferences": preferences,
        "input_binding": {
            "job_revision": (task or {}).get("job_binding"),
            "inputs": deepcopy((task or {}).get("inputs", {})),
            "analysis_id": (analysis or {}).get("id"),
        },
        "limitations": [
            *(analysis or {}).get("limitations", []),
            "匹配分、资格和偏好分别呈现；不代表 Skill 掌握程度、录用概率或投递许可。",
            "已确认信息按来源、适用范围和当前版本复用；未确认或存在冲突的记录保留待核验。",
            "偏好展示来自当前岗位记录；未将信息库的自由格式偏好推断成硬限制。",
        ],
    }
    if fresh and not materials_fresh:
        result["limitations"].insert(0, "当前分析已核验；已保存材料仍绑定原输入版本，旧 PDF 保留。")
    if not fresh:
        result["limitations"].insert(0, "输入版本已变化；旧分析仅供历史查看，请同步最新输入。")
        result["qualification"] = result["qualification"] | {
            "historical_status": result["qualification"]["status"],
            "status": "conflict"
            if result["qualification"]["status"] == "conflict"
            else "needs_input",
            "message": "资格结论对应旧输入，仅供历史查看；请同步后重新核验。",
        }
    if (effective_analysis or {}).get("job_brief") and (effective_analysis or {}).get(
        "material_packet"
    ):
        result["business_summary"] = _business_summary(
            effective_analysis["job_brief"], requirements
        )
        result["match_score"] = (
            {
                "kind": "single" if score["lower"] == score["upper"] else "interval",
                "lower": score["lower"],
                "upper": score["upper"],
                "display": f"{score['lower']:g}/100"
                if score["lower"] == score["upper"]
                else f"{score['lower']:g}–{score['upper']:g}/100",
            }
            if score and score["lower"] is not None and score["upper"] is not None
            else None
        )
        result["score_coverage_label"] = "分数确定度"
        result["material_read_coverage"] = _material_read_coverage(
            effective_analysis["material_packet"]
        )
        result["resume_coverage"] = _resume_coverage(task, requirements, resume_sources)
    result["revision"] = digest(result)
    return result
