"""Source-bound matching reviews that retain completed application materials."""

import json
import re
from copy import deepcopy
from datetime import UTC, datetime

from .application_information import _read_document
from .application_match_scoring import calculate_match_score
from .application_material_sources import quoted_source as _quoted_source
from .application_material_sources import source_records as _sources
from .career_portal_data import PortalDataError
from .validation.hashing import record_digest as digest


def attach_match_recheck(flow, task_id, task_revision, analysis_id, library_revision):
    from .application_explanations import adopted_analysis
    from .application_flow import job_input_revision

    def require(value, message):
        if not value:
            raise PortalDataError("match_recheck_invalid", message, 409)

    require(
        isinstance(analysis_id, str) and re.fullmatch(r"[a-f0-9]{32}", analysis_id),
        "复核标识不能核验。",
    )
    path = flow.root / "match-rechecks" / analysis_id / "review.json"
    try:
        review = json.loads(_read_document(path).raw)
    except (OSError, ValueError, TypeError) as error:
        raise PortalDataError("match_recheck_invalid", "复核记录不能读取。", 409) from error
    with flow.applications.write_lock():
        flow._writable()
        state = flow._load()
        task = flow._task(state, task_id)
        existing = next((r for r in task.get("match_rechecks", []) if r["id"] == analysis_id), None)
        if existing:
            require(existing["review_revision"] == digest(review), "已有复核标识的内容已变化。")
            return deepcopy(task)
        state, task = flow._checked(task_id, task_revision, allow_existing_handoff=True)
        require(task["status"] != "cancelled", "已取消任务不能接回新复核。")
        require(
            task["status"] not in {"queued", "filling", "needs_recheck"},
            "填写执行或结果未决时须先核对原任务。",
        )
        require(
            not any(
                s.get("status") in {"queued", "running", "needs_recheck"}
                for s in task["stages"].values()
            ),
            "先核对当前未决阶段。",
        )
        flow._group_guard_change(task)
        application = flow._fresh(task, stage="analysis")
        original = adopted_analysis(task)
        require(original is not None, "须保留原岗位分析。")
        library = flow.information_provider() if flow.information_provider else {}
        connected = library.get("career_library", {})
        require(
            connected.get("status") == "available"
            and connected.get("revision") == library_revision,
            "经历库来源已变化或暂不可用。",
        )
        require(callable(flow.recheck_source_provider), "经历库来源尚未连接。")
        snapshot = flow.recheck_source_provider(application["id"])
        require(
            snapshot.get("revision")
            == digest({k: v for k, v in snapshot.items() if k != "revision"}),
            "复核来源快照不能核验。",
        )
        expected = {
            "schema_version": "match-recheck/v1",
            "application_id": application["id"],
            "task_id": task["id"],
            "base_analysis_id": task["analysis_id"],
            "base_analysis_revision": digest(original),
            "job_binding": job_input_revision(application),
            "library_revision": library_revision,
            "source_snapshot_revision": snapshot["revision"],
            "reviewer": "codex",
        }
        require(
            isinstance(review, dict) and all(review.get(k) == v for k, v in expected.items()),
            "复核与当前岗位、原分析或来源版本不符。",
        )
        amendments = review.get("amendments")
        require(
            isinstance(amendments, list) and 0 < len(amendments) <= len(original["requirements"]),
            "复核要求列表不能核验。",
        )
        sources = _sources(snapshot)
        result, seen = deepcopy(original), set()
        for amendment in amendments:
            require(isinstance(amendment, dict), "复核要求格式不能核验。")
            index = amendment.get("requirement_index")
            require(
                type(index) is int
                and 0 <= index < len(result["requirements"])
                and index not in seen,
                "复核要求定位不能核验。",
            )
            seen.add(index)
            old = original["requirements"][index]
            require(amendment.get("requirement_text") == old["text"], "复核不能替换 JD 要求。")
            judgment = amendment.get("judgment")
            require(
                judgment in {"supported", "partial", "unknown"} and old["judgment"] != "gap",
                "复核不能消除已知冲突。",
            )
            explanation = amendment.get("explanation")
            require(
                isinstance(explanation, str) and 0 < len(explanation.strip()) <= 4000,
                "复核须保留具体依据。",
            )
            citations = amendment.get("citations")
            require(
                isinstance(citations, list) and 0 < len(citations) <= 20,
                "复核须引用已读取的具体来源。",
            )
            quoted = []
            for citation in citations:
                require(
                    isinstance(citation, dict) and isinstance(citation.get("quote"), str),
                    "复核引用格式不能核验。",
                )
                require(isinstance(citation.get("source_id"), str), "复核来源标识不能核验。")
                source = sources.get(citation.get("source_id"))
                require(
                    source is not None and source["available"] and source["match_eligible"],
                    "复核引用的来源不可用。",
                )
                anchored = _quoted_source(source, citation["quote"])
                require(not anchored.get("planned_only"), "计划或否定语境不能作为已完成经历证据。")
                quoted.append(anchored)
            result["requirements"][index] = {
                **{
                    k: v
                    for k, v in old.items()
                    if k not in {"citation_warning", "gap_review_required"}
                },
                "judgment": judgment,
                "claim_scope": "documentary",
                "explanation": explanation,
                "sources": quoted,
                "source_ids": list(dict.fromkeys(s["source_id"] for s in quoted)),
                "citations": [{"source_id": s["source_id"], "quote": s["quote"]} for s in quoted],
                "previous_reason": deepcopy(old),
                "review_method": "codex_source_review",
            }
        result["score"] = calculate_match_score(result["requirements"])
        result["match_recheck_id"] = analysis_id
        receipt = {
            "id": analysis_id,
            "review_revision": digest(review),
            "base_analysis_id": task["analysis_id"],
            "base_analysis_revision": digest(original),
            "job_binding": task["job_binding"],
            "library_revision": library_revision,
            "source_snapshot_revision": snapshot["revision"],
            "reviewer": "codex",
            "reviewed_at": datetime.now(UTC).isoformat(),
            "result": result,
        }
        from ._vendor import job_apply_store as helper

        helper.atomic_write_json(path.parent / "validated-source-snapshot.json", snapshot)
        task.setdefault("match_rechecks", []).append(receipt)
        flow._save(state)
        return deepcopy(task)


def normal_analysis_current(report, application, library, source_provider):
    """Re-read the exact selected source range and applicable facts before reuse."""
    from .application_information import information_context

    if not application or not callable(source_provider):
        return False
    try:
        selected = report["retrieval"]["selected_candidate_ids"]
        if (
            not isinstance(selected, list)
            or not all(isinstance(key, str) for key in selected)
            or len(set(selected)) != len(selected)
            or report.get("information_context_revision")
            != information_context(application, library or {})["revision"]
        ):
            return False
        snapshot = (
            source_provider(application["id"])
            if report["retrieval"].get("index_status") == "not_configured"
            else source_provider(application["id"], selected)
        )
        return snapshot.get("revision") == digest(
            {key: value for key, value in snapshot.items() if key != "revision"}
        ) and snapshot.get("revision") == report.get("source_snapshot_revision")
    except (KeyError, TypeError, ValueError, OSError, PortalDataError):
        return False


def latest_fixed_recheck(task):
    """The latest normal recheck of a job whose materials are fixed, for display only.

    Decided 2026-10-31: the card shows it; qualification and execution keep the
    analysis the materials were made with.
    """
    rows = [
        row
        for row in (task or {}).get("match_rechecks", [])
        if row.get("method") == "normal_analysis"
    ]
    latest = rows[-1] if rows else {}
    if (
        latest.get("result")
        and latest.get("base_analysis_id") == task.get("analysis_id")
        and latest.get("job_binding") == task.get("job_binding")
    ):
        return latest
    return None


def current_match_recheck(task, library, *, application=None, source_provider=None):
    """Use a review only while its original analysis and connected source version remain current."""
    connected = (library or {}).get("career_library", {})
    if not task or connected.get("status") != "available":
        return None
    from .application_explanations import adopted_analysis

    original = adopted_analysis(task)
    for receipt in reversed(task.get("match_rechecks", [])):
        if (
            receipt["base_analysis_id"] == task.get("analysis_id")
            and receipt["base_analysis_revision"] == digest(original)
            and receipt["job_binding"] == task.get("job_binding")
            and receipt["library_revision"] == connected.get("revision")
        ):
            if receipt.get("method") == "normal_analysis" and (
                receipt.get("information_context_revision")
                != receipt.get("result", {}).get("information_context_revision")
                or not normal_analysis_current(
                    receipt.get("result", {}), application, library, source_provider
                )
            ):
                # Never resurrect an older manual amendment after a normal refresh
                # has become stale. Preserve all receipts as history instead.
                return None
            return receipt
        if receipt.get("method") == "normal_analysis":
            return None
    return None
