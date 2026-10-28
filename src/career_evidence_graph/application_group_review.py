"""Immutable experience-group review versions on the existing résumé and Prism stores."""

from __future__ import annotations

import base64
import hashlib
import json
import re
from copy import deepcopy
from pathlib import Path
from uuid import uuid4

from ._vendor import job_apply_store as helper
from .application_draft import review_findings
from .application_full_latex import (
    _body,
    _contact_literals,
    _identity_header_exceptions,
    _identity_matches,
    _prose_latex,
    _validate_body,
)
from .application_prism import (
    archive_sources,
    refresh_source_snapshot,
    source_snapshot,
    validate_archive,
)
from .career_portal_data import PortalDataError
from .resume_presentation import PRESENTATION_POLICY_VERSION, validate_resume_presentation
from .validation.hashing import record_digest as digest

ENGINE_SHA256 = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
_MARKER = re.compile(r"(?m)^% TomorrowStar group ([a-f0-9]{64}) (begin|end)\n")


def _failure(
    code="resume_group_mapping_required", message="分组关系尚不能核验，请保留源和原回执。"
):
    return PortalDataError(code, message, 409)


def fixed_education_groups(draft):
    """Return documentary reuse only for validated, current-policy education."""
    if "presentation_policy" not in draft:
        return []
    if draft["presentation_policy"] != PRESENTATION_POLICY_VERSION:
        raise _failure("resume_presentation_policy_invalid", "简历内容规则版本不能核验。")
    from .application_full_latex import is_fixed_education_group

    fixed = []
    for group in draft.get("review_groups", []):
        if group.get("content_policy") == "fixed_education":
            if not is_fixed_education_group(group):
                raise _failure("resume_fixed_education_changed", "教育经历与固定来源记录不符。")
            fixed.append(group)
    return fixed


def has_unresolved_education(draft):
    """A pending or omitted education claim cannot disappear behind other reviews."""
    if "presentation_policy" not in draft:
        return False
    fixed_education_groups(draft)
    from .application_full_latex import is_fixed_education_group

    for key in ("review_groups", "omitted_groups", "verification_queue"):
        for group in draft.get(key, []):
            education = group.get("content_policy") in {
                "fixed_education",
                "education_verification_required",
            } or any(
                source.get("source_kind") == "education" for source in group.get("sources", [])
            )
            if education and (key != "review_groups" or not is_fixed_education_group(group)):
                return True
    return False


def group_review_snapshot(draft, task_inputs, receipts):
    """Bind complete current group decisions without granting PDF approval."""
    if has_unresolved_education(draft):
        raise _failure(
            "flow_education_verification_required",
            "教育经历存在来源或状态冲突，请先核对已有记录，不能导出缺失教育的岗位版本。",
        )
    groups = draft.get("review_groups", [])
    fixed = fixed_education_groups(draft)
    fixed_ids = {group["id"] for group in fixed}
    required = [group for group in groups if group["id"] not in fixed_ids]
    preview = draft.get("group_preview") or {}
    source_revision = draft.get("source_checkpoint", {}).get("source_revision")
    if (
        draft.get("origin") != "generated_latex"
        or not draft.get("group_session")
        or not groups
        or not preview
        or preview.get("source_revision") != source_revision
        or not draft.get("group_context_revision")
        or not draft.get("draft_sha256")
        or not isinstance(receipts, list)
        or len(receipts) != len(required)
        or any(not isinstance(row, dict) for row in receipts)
    ):
        raise _failure("flow_factual_review_required", "请先逐组确认当前正文、来源和责任归属。")
    indexed = {row.get("group_id"): row for row in receipts}
    if (
        len(indexed) != len(required)
        or set(indexed) != {g["id"] for g in required}
        or len({row.get("id") for row in receipts}) != len(receipts)
    ):
        raise _failure("flow_factual_review_required", "当前经历组确认范围不能核验。")
    ordered = []
    for group in required:
        row = indexed[group["id"]]
        if (
            not isinstance(row.get("id"), str)
            or not re.fullmatch(r"[a-f0-9]{32}", row["id"])
            or any(
                row.get(key) != value
                for key, value in {
                    "draft_id": draft["id"],
                    "draft_sha256": draft["draft_sha256"],
                    "input_revision": digest(task_inputs),
                    "source_revision": source_revision,
                    "preview_id": preview["id"],
                    "verified_by": "user",
                    "review_fingerprint": group.get("review_fingerprint"),
                }.items()
            )
        ):
            raise _failure("flow_factual_review_required", "经历组确认与当前版本不符，请重新核验。")
        ordered.append(deepcopy(row))
    payload = {
        "draft_id": draft["id"],
        "draft_sha256": draft["draft_sha256"],
        "input_revision": digest(task_inputs),
        "context_revision": draft["group_context_revision"],
        "source_revision": source_revision,
        "preview_id": preview["id"],
        "receipts": ordered,
    }
    if "presentation_policy" in draft:
        payload["presentation_policy"] = draft["presentation_policy"]
        payload["fixed_education"] = [
            {
                "group_id": group["id"],
                "review_fingerprint": group["review_fingerprint"],
                "source_ids": [source["source_id"] for source in group["sources"]],
                "basis": "documentary_reuse",
            }
            for group in fixed
        ]
    return payload | {"revision": digest(payload)}


def _current(store, draft_id, draft_sha256, inputs):
    draft, sha = store._draft_document(draft_id)
    if (
        sha != draft_sha256
        or draft.get("origin") != "generated_latex"
        or draft.get("task_inputs") != inputs
    ):
        raise _failure("flow_draft_mismatch", "请核验当前完整LaTeX版本及任务输入。")
    if draft.get("generation_contract") in {"fixed-writing/v1", "content-writing/v1"}:
        # _draft_document has checked immutable archives and the final review.
        # Current libraries/configuration do not revoke a delivered candidate.
        return draft
    snapshot = json.loads(
        store._read_version_file(draft_id, "source-snapshot.json", 32 * 1024 * 1024)
    )
    binding = draft["analysis_binding"]
    analysis = {
        "id": binding["analysis_id"],
        "application_id": draft["application_id"],
        **{
            k: binding[k]
            for k in (
                "jd_revision",
                "source_snapshot_revision",
                "configuration_revision",
                "policy_version",
            )
        },
        "selected_source_ids": draft["selected_source_ids"],
        "requirements": [{"source_ids": draft["selected_source_ids"]}],
    }
    store._task_current(draft["application_id"], snapshot, analysis, draft["generation_policy"])
    if archive_sources(draft["base_checkpoint"]) != store._read_version_file(
        draft_id, "base-sources.json", 48_000_000
    ):
        raise _failure("flow_latex_base_changed", "原始底稿已变化，请核验输入。")
    return draft


def _all_groups(draft):
    return draft["review_groups"] + draft["omitted_groups"] + draft["verification_queue"]


def _fingerprint(group, context):
    return digest(
        {
            "context": context,
            **{
                k: group[k]
                for k in (
                    "id",
                    "title",
                    "original",
                    "rewritten",
                    "sources",
                    "attribution",
                    "disposition",
                )
            },
        }
    )


def _context(text, binding):
    prefix, _, suffix = _body(text)
    return digest(
        {
            "prefix": prefix,
            "suffix": suffix,
            "files": {k: v for k, v in binding["files"].items() if k != binding["main"]},
        }
    )


def unwrapped_group(text):
    """Remove one exact internal editor wrapper, including its packing newline."""
    marks = list(_MARKER.finditer(text))
    if (
        len(marks) == 2
        and marks[0][1] == marks[1][1]
        and marks[0][2] == "begin"
        and marks[1][2] == "end"
        and not text[: marks[0].start()].strip()
        and not text[marks[1].end() :].strip()
    ):
        inner = text[marks[0].end() : marks[1].start()]
        if inner.endswith("\n"):
            return text[: marks[0].start()] + inner[:-1] + text[marks[1].end() :]
    return text


def _marked(groups):
    return "".join(
        f"% TomorrowStar group {g['id']} begin\n"
        + unwrapped_group(g["rewritten"])
        + f"\n% TomorrowStar group {g['id']} end\n"
        for g in groups
    )


def _parse(text, catalog):
    _, body, _ = _body(text)
    marks = list(_MARKER.finditer(body))
    if not marks or len(marks) % 2:
        raise _failure()
    groups, seen, end = [], set(), 0
    for begin, finish in zip(marks[::2], marks[1::2], strict=True):
        identifier = begin[1]
        if (
            begin[2] != "begin"
            or finish[2] != "end"
            or identifier != finish[1]
            or identifier in seen
            or identifier not in catalog
            or body[end : begin.start()].strip()
        ):
            raise _failure()
        content = body[begin.end() : finish.start()]
        if not content.endswith("\n"):
            raise _failure()
        group = deepcopy(catalog[identifier])
        group["rewritten"] = content[:-1]
        group["disposition"] = "include"
        group["review_status"] = "review_required"
        group["review_findings"] = review_findings(group["original"], group["rewritten"])
        groups.append(group)
        seen.add(identifier)
        end = finish.end()
    if body[end:].strip():
        raise _failure()
    return groups


def _retained_identity_headers(draft, original=None, *, store=None):
    """Recompute header scope from the bound base; never trust an edit's own label."""
    if draft.get("pending_merge"):
        from .application_full_latex import planned_base_source

        if store is None:
            raise _failure("resume_draft_invalid", "合并底稿来源不能核验，请保留当前源。")
        original = planned_base_source(store, draft, original)
    elif original is None:
        original = validate_archive(
            archive_sources(draft["base_checkpoint"]), draft["base_checkpoint"]
        ).decode("utf-8")
    _, body, _ = _body(original)
    lines = body.splitlines(keepends=True)
    first_section = re.search(r"\\(?:section|cvsection)\*?(?:\[[^\]]*\])?\{", body)
    header_end = body[: first_section.start()].count("\n") if first_section else 0
    retained = {}
    for group in draft["review_groups"]:
        start, end = group.get("start_line"), group.get("end_line")
        if (
            type(start) is int
            and type(end) is int
            and 1 <= start <= end <= header_end
            and "".join(lines[start - 1 : end]) == group["original"]
            and any(
                _identity_header_exceptions(
                    group["original"], group["rewritten"], group["sources"], is_header=True
                )
            )
        ):
            retained[group["id"]] = group
    return retained


def _supported(group, retained_headers=None):
    from .application_full_latex import is_fixed_education_group

    sources = group["sources"]
    if not sources or any(
        not s.get("resume_eligible")
        or s.get("attribution") in {None, "", "Unknown", "Editorial statement; review required"}
        for s in sources
    ):
        return False
    if all(
        s.get("source_kind") in {"identity", "education", "career_context"} for s in sources
    ) and not _identity_matches(group["rewritten"], sources):
        return False
    retained = (retained_headers or {}).get(group["id"])
    retained_header = retained is not None and all(
        (
            unwrapped_group(group[key]) == unwrapped_group(retained[key])
            if key == "rewritten"
            else group.get(key) == retained.get(key)
        )
        for key in ("original", "rewritten", "sources", "start_line", "end_line")
    )
    if (
        any(not s.get("rewrite_allowed", True) for s in sources)
        and unwrapped_group(group["rewritten"]) != unwrapped_group(group["original"])
        and not retained_header
        and not is_fixed_education_group(group)
    ):
        return False
    evidence = " ".join(
        s.get("text", "") + " " + s.get("title", "") + " " + s.get("boundaries", "")
        for s in sources
    )
    prose = _prose_latex(group["rewritten"])
    if retained_header:
        evidence, _ = _contact_literals(evidence)
        prose, _ = _contact_literals(prose)
    return not any(
        check["added"]
        for check in review_findings(evidence, prose)["checks"]
        if check["category"] in {"numbers", "dates"}
    )


def _fixed_education_unchanged(draft, text):
    fixed = fixed_education_groups(draft)
    if not fixed:
        return
    body = _body(text)[1]
    for group in fixed:
        begin = f"% TomorrowStar group {group['id']} begin\n"
        end = f"% TomorrowStar group {group['id']} end\n"
        if (
            body.count(begin) != 1
            or body.count(end) != 1
            or body.partition(begin)[2].partition(end)[0]
            != unwrapped_group(group["rewritten"]) + "\n"
        ):
            raise _failure(
                "resume_fixed_education_changed", "教育经历固定复用已有记录，不能按岗位改写或删除。"
            )


def _groups_for_source(draft, text, binding, *, retained_headers=None, store=None):
    _fixed_education_unchanged(draft, text)
    validate_resume_presentation(_prose_latex(_body(text)[1]))
    catalog = {g["id"]: g for g in _all_groups(draft)}
    included = _parse(text, catalog)
    if retained_headers is None:
        retained_headers = _retained_identity_headers(draft, store=store)
    if not included or any(
        not g["rewritten"].strip() or not _supported(g, retained_headers) for g in included
    ):
        raise _failure(
            "resume_group_verification_required", "编辑内容仍需来源或责任核对，暂不进入新正文。"
        )
    _validate_body("".join(g["rewritten"] for g in included), draft["latex_source"])
    present = {g["id"] for g in included}
    omitted, queue = [], []
    for group in _all_groups(draft):
        if group["id"] in present:
            continue
        group = deepcopy(group)
        if group["disposition"] == "verify":
            queue.append(group)
        else:
            group["disposition"] = "omit"
            if group["id"] in {g["id"] for g in draft["review_groups"]}:
                group["reason"] = "Removed from this editor version; original retained"
            omitted.append(group)
    context = _context(text, binding)
    for group in included + omitted + queue:
        group["review_fingerprint"] = _fingerprint(group, context)
    old = {g["id"]: g for g in draft["review_groups"]}
    unchanged = [
        g["id"]
        for g in included
        if draft.get("group_context_revision") == context
        and old.get(g["id"], {}).get("review_fingerprint") == g["review_fingerprint"]
    ]
    return {
        "review_groups": included,
        "omitted_groups": omitted,
        "verification_queue": queue,
        "group_context_revision": context,
        "verified_unchanged_group_ids": unchanged,
    }


def _write_project(directory, archive, binding, text):
    project = directory / "project"
    project.mkdir(mode=0o700)
    for name, encoded in json.loads(archive).items():
        relative = Path(name)
        if relative.is_absolute() or ".." in relative.parts:
            raise _failure()
        path = project / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("xb") as stream:
            stream.write(
                text.encode("utf-8")
                if name == binding["main"]
                else base64.b64decode(encoded, validate=True)
            )
        path.chmod(0o600)
    return source_snapshot(project, binding["main"], source_policy="generated-latex-project/v1")


def _save(store, parent, text, archive, binding, *, session=None, preview=None, plan=None):
    identifier = uuid4().hex
    directory = store.root / identifier
    directory.mkdir(mode=0o700)
    if session is None:
        checkpoint = _write_project(directory, archive, binding, text)
        archive = archive_sources(checkpoint)
        session = {
            "id": identifier,
            "project_root": checkpoint["project_root"],
            "main": checkpoint["main"],
            "root_draft_id": parent.get("group_session", {}).get("root_draft_id", parent["id"]),
        }
    else:
        checkpoint = binding
    if preview is not None:
        preview = deepcopy(preview) | {
            "preview_url": f"/api/flow/group-previews/{identifier}/{preview['id']}/pdf"
        }
    plan = plan or _groups_for_source(parent, text, checkpoint, store=store)
    for name in ("base-sources.json", "source-snapshot.json"):
        raw = store._read_version_file(
            parent["id"], name, 48_000_000 if name == "base-sources.json" else 32 * 1024 * 1024
        )
        (directory / name).write_bytes(raw)
        (directory / name).chmod(0o600)
    (directory / "latex-sources.json").write_bytes(archive)
    (directory / "latex-sources.json").chmod(0o600)
    draft = (
        deepcopy(parent)
        | plan
        | {
            "id": identifier,
            "latex_source": text,
            "group_session": session,
            "group_parent_id": parent["id"],
            "group_preview": preview,
            "source_checkpoint": deepcopy(checkpoint)
            | {"archive_sha256": hashlib.sha256(archive).hexdigest()},
            "factual_review": "pending",
        }
    )
    helper.atomic_write_json(directory / "draft.json", draft)
    helper.atomic_write_json(
        directory / "draft-integrity.json",
        {
            "schemaVersion": 1,
            "id": identifier,
            "sha256": hashlib.sha256((directory / "draft.json").read_bytes()).hexdigest(),
        },
    )
    return store.draft(identifier)


def prepare(store, draft_id, draft_sha256, *, task_inputs):
    draft = _current(store, draft_id, draft_sha256, task_inputs)
    if draft.get("generation_contract") == "content-writing/v1":
        raise _failure(
            "resume_content_edit_required",
            "内容版本不能使用旧 TeX 分组编辑；请沿用当前完整文档编辑入口。",
        )
    if draft.get("group_session"):
        return store.draft(draft_id)
    archive = store._read_version_file(draft_id, "latex-sources.json", 48_000_000)
    text = validate_archive(archive, draft["source_checkpoint"]).decode("utf-8")
    prefix, _, suffix = _body(text)
    marked = prefix + _marked(draft["review_groups"]) + suffix
    return _save(store, draft, marked, archive, draft["source_checkpoint"])


def _preview_store(store, draft):
    from .application_prism_review import PrismReviewStore

    session = draft["group_session"]
    if not re.fullmatch(r"[a-f0-9]{32}", session["id"]):
        raise _failure()
    return PrismReviewStore(
        store.root / session["id"] / "group-previews",
        client=getattr(store, "group_prism_client", None),
        pdf_inspector=store.pdf_inspector,
        binding_provider=lambda: refresh_source_snapshot(draft["source_checkpoint"]),
    )


def state(store, draft_id):
    draft, _ = store._draft_document(draft_id)
    if not draft.get("group_session"):
        return {
            "status": "not_prepared",
            "live_source_revision": None,
            "pending_attempt_id": None,
            "latest": None,
        }
    return _preview_store(store, draft).state()


def _preview(store, draft, identifier):
    receipts = _preview_store(store, draft)
    version = receipts.version(identifier)
    binding = version.pop("binding")
    session = draft["group_session"]
    if any(binding[key] != session[key] for key in ("project_root", "main")):
        raise _failure()
    preview = version | {
        "latex_source": receipts.source(identifier).decode("utf-8"),
        "preview_url": f"/api/flow/group-previews/{draft['id']}/{identifier}/pdf",
    }
    return preview, binding, receipts.archive(identifier)


def _bounded_editor(draft, text, binding):
    prefix, body, suffix = _body(text)
    old_prefix, _, old_suffix = _body(draft["latex_source"])
    if (
        prefix != old_prefix
        or suffix != old_suffix
        or {k: v for k, v in binding["files"].items() if k != binding["main"]}
        != {k: v for k, v in draft["source_checkpoint"]["files"].items() if k != binding["main"]}
    ):
        raise _failure(
            "resume_group_layout_changed",
            "本次审核仅支持正文编辑；版式、宏或附属文件变化须先单独核验。",
        )
    _validate_body(body, draft["latex_source"])
    if "presentation_policy" in draft:
        validate_resume_presentation(_prose_latex(body))
        _fixed_education_unchanged(draft, text)


def capture(
    store, draft_id, draft_sha256, *, task_inputs, expected_source_revision, reconcile=False
):
    draft = _current(store, draft_id, draft_sha256, task_inputs)
    if not draft.get("group_session"):
        raise _failure("flow_group_session_required", "请先建立分组审阅版本。")
    receipts = _preview_store(store, draft)
    current = receipts.state()
    if reconcile:
        captured = receipts.reconcile()
    else:
        if current["pending_attempt_id"]:
            raise _failure("prism_review_needs_recheck", "请先核验已有读取尝试。")
        if (
            expected_source_revision != current["live_source_revision"]
            or not expected_source_revision
        ):
            raise _failure("prism_source_changed", "LaTeX 源已变化，请重新读取当前源版本。")
        # File-reading commands must be rejected before invoking the compiler.
        binding = receipts.binding()
        raw_source = validate_archive(archive_sources(binding), binding).decode("utf-8")
        _bounded_editor(draft, raw_source, binding)
        validate_resume_presentation(_prose_latex(_body(raw_source)[1]))
        if current["latest"] and current["latest"]["source_revision"] == expected_source_revision:
            captured = current
        else:
            captured = receipts.capture(expected_source_revision)
    latest = captured["latest"]
    if not latest:
        raise _failure("prism_review_needs_recheck", "尚无可回读的同源预览。")
    preview, binding, archive = _preview(store, draft, latest["id"])
    _current(store, draft_id, draft_sha256, task_inputs)
    if receipts.binding() != binding:
        raise _failure("prism_review_needs_recheck", "预览后的源已变化，请保留回执核验。")
    _bounded_editor(draft, preview["latex_source"], binding)
    try:
        plan = _groups_for_source(draft, preview["latex_source"], binding, store=store)
    except PortalDataError as error:
        return {
            "status": "mapping_required",
            "draft": None,
            "preview": preview,
            "mapping_error": str(error),
        }
    if (draft.get("group_preview") or {}).get("id") == latest["id"]:
        result = store.draft(draft_id)
    else:
        result = _save(
            store,
            draft,
            preview["latex_source"],
            archive,
            binding,
            session=draft["group_session"],
            preview=preview,
            plan=plan,
        )
    return {
        "status": "ready",
        "draft": result,
        "preview": result["group_preview"],
        "verified_unchanged_group_ids": result["verified_unchanged_group_ids"],
    }


def preview_pdf(store, draft_id, preview_id):
    draft, _ = store._draft_document(draft_id)
    _preview(store, draft, preview_id)
    return _preview_store(store, draft).pdf(preview_id)


def edit(store, draft_id, draft_sha256, *, task_inputs, payload):
    draft = _current(store, draft_id, draft_sha256, task_inputs)
    if not draft.get("group_session"):
        raise _failure("flow_group_session_required", "请先建立分组审阅版本。")
    current = _preview_store(store, draft).state()
    if current["pending_attempt_id"]:
        raise _failure("prism_review_needs_recheck", "请先核验已有读取尝试。")
    if current["live_source_revision"] != draft["source_checkpoint"]["source_revision"]:
        raise _failure("prism_source_changed", "编辑器源已变化，请先读取并核验，保留当前编辑。")
    if (
        not isinstance(payload, dict)
        or set(payload) - {"group_id", "title", "latex", "source_ids", "disposition"}
        or not isinstance(payload.get("title"), str)
        or not 1 <= len(payload["title"].strip()) <= 500
        or not isinstance(payload.get("latex"), str)
        or not payload["latex"].strip()
        or len(payload["latex"].encode("utf-8")) > 4_000_000
        or payload.get("disposition", "include") not in {"include", "omit"}
        or not isinstance(payload.get("source_ids"), list)
        or any(not isinstance(x, str) for x in payload["source_ids"])
        or len(set(payload["source_ids"])) != len(payload["source_ids"])
    ):
        raise _failure("resume_group_edit_invalid", "请核验经历标题、正文、来源及采用状态。")
    sources = {s["source_id"]: s for s in draft["generation_sources"]}
    if any(identifier not in sources for identifier in payload["source_ids"]):
        raise _failure("resume_group_edit_invalid", "来源必须来自本岗既有资料快照。")
    catalog = {g["id"]: deepcopy(g) for g in _all_groups(draft)}
    identifier = payload.get("group_id")
    if identifier is not None and identifier not in catalog:
        raise _failure("resume_group_edit_invalid", "经历组不能核验。")
    if identifier in {group["id"] for group in fixed_education_groups(draft)}:
        raise _failure(
            "resume_fixed_education_changed",
            "教育经历固定复用已有记录，无需岗位改写或重复事实确认。",
        )
    references = [deepcopy(sources[x]) for x in payload["source_ids"]]
    if identifier is None:
        identifier = digest({"new_group": uuid4().hex})
        catalog[identifier] = {
            "id": identifier,
            "original": "\n".join(s["text"] for s in references),
            "original_locator": {
                "kind": "added_from_sources",
                "source_ids": list(payload["source_ids"]),
            },
        }
    group = catalog[identifier]
    group.update(
        title=payload["title"],
        rewritten=payload["latex"],
        sources=references,
        attribution=[s["attribution"] for s in references],
        disposition=payload.get("disposition", "include"),
        review_status="review_required",
        reason="Explicit group edit; original retained",
        review_findings=review_findings(group["original"], payload["latex"]),
    )
    retained_headers = _retained_identity_headers(draft, store=store)
    if not _supported(group, retained_headers):
        group.update(
            disposition="verify",
            reason="source_or_attribution_unresolved: edited statement requires verification",
        )
    validate_resume_presentation(_prose_latex(payload["latex"]))
    _validate_body(payload["latex"], draft["latex_source"])
    # Keep adopted order and append explicit restorations/new groups at the end.
    ordered = [catalog[g["id"]] for g in draft["review_groups"]]
    if identifier not in {g["id"] for g in ordered}:
        ordered.append(group)
    included = [g for g in ordered if g["disposition"] == "include"]
    if not included:
        raise _failure("resume_group_edit_invalid", "完整简历至少保留一个已核验来源组。")
    prefix, _, suffix = _body(draft["latex_source"])
    text = prefix + _marked(included) + suffix
    updated = deepcopy(draft)
    updated.update(
        review_groups=included,
        omitted_groups=[g for g in catalog.values() if g["disposition"] == "omit"],
        verification_queue=[g for g in catalog.values() if g["disposition"] == "verify"],
    )
    plan = _groups_for_source(
        updated, text, draft["source_checkpoint"], retained_headers=retained_headers, store=store
    )
    # Compare with the actual prior draft, not the edited intermediary.
    prior = {g["id"]: g for g in draft["review_groups"]}
    plan["verified_unchanged_group_ids"] = [
        g["id"]
        for g in plan["review_groups"]
        if prior.get(g["id"], {}).get("review_fingerprint") == g["review_fingerprint"]
    ]
    archive = store._read_version_file(draft_id, "latex-sources.json", 48_000_000)
    return _save(store, draft, text, archive, draft["source_checkpoint"], plan=plan)


def validate(store, draft):
    if draft["factual_review"] != "pending" or draft["items"] != []:
        raise ValueError("Grouped source is pending factual review")
    original = None
    for name, key in (
        ("base-sources.json", "base_checkpoint"),
        ("latex-sources.json", "source_checkpoint"),
    ):
        raw = store._read_version_file(draft["id"], name, 48_000_000)
        if hashlib.sha256(raw).hexdigest() != draft[key]["archive_sha256"]:
            raise ValueError("Grouped source archive changed")
        main = validate_archive(raw, draft[key]).decode("utf-8")
        if key == "base_checkpoint":
            original = main
        if key == "source_checkpoint" and main != draft["latex_source"]:
            raise ValueError("Grouped source bytes differ")
    session = draft["group_session"]
    if (
        not isinstance(session, dict)
        or set(session) != {"id", "project_root", "main", "root_draft_id"}
        or any(not re.fullmatch(r"[a-f0-9]{32}", session[k]) for k in ("id", "root_draft_id"))
        or session["root_draft_id"] == draft["id"]
        or Path(session["project_root"]) != store.root / session["id"] / "project"
    ):
        raise ValueError("Grouped session changed")
    root_raw = json.loads(
        store._read_version_file(session["root_draft_id"], "draft.json", 2 * 1024 * 1024)
    )
    if root_raw.get("group_session") or root_raw.get("origin") != "generated_latex":
        raise ValueError("Grouped generation root changed")
    root, _ = store._draft_document(session["root_draft_id"])
    for key in (
        "application_id",
        "task_inputs",
        "base_checkpoint",
        "analysis_binding",
        "generation_sources",
        "generation_policy",
        "selected_source_ids",
        "information_library_revision",
        "resume_configuration_revision",
        "presentation_policy",
        "pending_merge",
        "omitted_source_mapping",
    ):
        if draft.get(key) != root.get(key):
            raise ValueError("Grouped provenance changed")
    root_fixed = {group["id"]: group for group in fixed_education_groups(root)}
    current_fixed = {group["id"]: group for group in fixed_education_groups(draft)}
    if set(current_fixed) != set(root_fixed) or any(
        any(
            (
                unwrapped_group(group[key]) != unwrapped_group(root_fixed[identifier][key])
                if key == "rewritten"
                else group.get(key) != root_fixed[identifier].get(key)
            )
            for key in (
                "title",
                "original",
                "rewritten",
                "sources",
                "attribution",
                "disposition",
                "content_policy",
            )
        )
        for identifier, group in current_fixed.items()
    ):
        raise ValueError("Fixed documented education changed")
    sources = {s["source_id"]: s for s in root["generation_sources"]}
    originals = {g["id"]: g for g in _all_groups(root)}
    all_groups = _all_groups(draft)
    identifiers = [g["id"] for g in all_groups]
    if (
        len(set(identifiers)) != len(identifiers)
        or not set(originals) <= set(identifiers)
        or any(not isinstance(i, str) or not re.fullmatch(r"[a-f0-9]{64}", i) for i in identifiers)
    ):
        raise ValueError("Grouped identity or original coverage changed")
    for group in all_groups:
        if group["id"] in originals:
            if any(
                group.get(key) != originals[group["id"]].get(key)
                for key in ("original", "start_line", "end_line", "content_policy")
            ):
                raise ValueError("Grouped original changed")
        else:
            locator = group["original_locator"]
            if (
                locator["kind"] != "added_from_sources"
                or not isinstance(locator["source_ids"], list)
                or any(i not in sources for i in locator["source_ids"])
                or group["original"] != "\n".join(sources[i]["text"] for i in locator["source_ids"])
            ):
                raise ValueError("Added group original changed")
        if (
            not isinstance(group["title"], str)
            or not group["title"].strip()
            or group["review_status"] != "review_required"
            or any(s != sources.get(s["source_id"]) for s in group["sources"])
            or len({s["source_id"] for s in group["sources"]}) != len(group["sources"])
            or group["attribution"] != [s["attribution"] for s in group["sources"]]
        ):
            raise ValueError("Grouped sources or responsibility changed")
    for key, disposition in (
        ("review_groups", "include"),
        ("omitted_groups", "omit"),
        ("verification_queue", "verify"),
    ):
        if any(g["disposition"] != disposition for g in draft[key]):
            raise ValueError("Grouped disposition changed")
    if (
        session["project_root"] != draft["source_checkpoint"]["project_root"]
        or session["main"] != draft["source_checkpoint"]["main"]
    ):
        raise ValueError("Grouped project changed")
    if (
        _context(draft["latex_source"], draft["source_checkpoint"])
        != draft["group_context_revision"]
    ):
        raise ValueError("Grouped context changed")
    _bounded_editor(root, draft["latex_source"], draft["source_checkpoint"])
    parsed = _parse(draft["latex_source"], {g["id"]: g for g in _all_groups(draft)})
    if [g["id"] for g in parsed] != [g["id"] for g in draft["review_groups"]]:
        raise ValueError("Grouped coverage changed")
    for group in _all_groups(draft):
        if group.get("review_fingerprint") != _fingerprint(group, draft["group_context_revision"]):
            raise ValueError("Grouped content changed")
    retained_headers = _retained_identity_headers(root, original, store=store)
    if any(
        a["rewritten"] != b["rewritten"] or not _supported(b, retained_headers)
        for a, b in zip(parsed, draft["review_groups"], strict=True)
    ):
        raise ValueError("Unverified body group")
    preview = draft.get("group_preview")
    if preview is not None:
        actual, binding, archive = _preview(store, draft, preview["id"])
        if (
            actual != preview
            or binding
            != {k: v for k, v in draft["source_checkpoint"].items() if k != "archive_sha256"}
            or hashlib.sha256(archive).hexdigest() != draft["source_checkpoint"]["archive_sha256"]
            or actual["latex_source"] != draft["latex_source"]
        ):
            raise ValueError("Grouped preview binding changed")
