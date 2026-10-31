"""Scoped JSON writing behind the existing durable experience handoff interface.

The calling session executes writers. This module fixes their factual scope,
validates their content, renders the reviewed candidate, and records review.
Legacy TeX handoffs continue through application_experience_latex.
"""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy

from pydantic import TypeAdapter

from ._vendor import job_apply_store as helper
from .application_full_latex import _invalid
from .application_resume_content import (
    WritingResult,
    apply_content_patch,
    assemble_content,
    content_revision,
    validate_content,
    validate_fragment,
    validate_plan,
    writer_schema,
)
from .application_resume_render import render_resume
from .validation.hashing import record_digest as digest

WRITER_INSTRUCTIONS = (
    "Return one experience-writing/v1 JSON object for this assignment. "
    "Write only this experience from the delivered facts and accepted inferences. "
    "Keep roles, numbers, responsibility and status. Use per-item fact_refs or inference_refs. "
    "Use needs_material with located requests for missing facts. "
    "Do not reinterpret the JD, rescore, retrieve libraries, or change another experience."
)
REVIEW_INSTRUCTIONS = (
    "Perform the single semantic review of this resume content JSON. "
    "Trust the delivered facts and accepted inferences. Check scope, focus, duplication, "
    "contradictions and clarity. Return a resume-content-patch/v1 text or links patch for "
    "small located changes, or return only affected experience IDs for substantial rewriting. "
    "Review the headline as job-specific career positioning supported by delivered facts; "
    "it must not invent employment, seniority, qualifications or proficiency. "
    "Keep protected human content, identity, education, references and attribution. "
    "Do not retrieve libraries, reinterpret the JD, rescore or write source libraries. "
    "When sibling_cover_letter is present, check factual consistency between the two "
    "new expressions. A relevant detail appearing only in one material is not by itself "
    "a conflict. Patch or request rewrites only for this resume; never edit the sibling."
)


def _save(directory, state):
    from .application_experience_latex import _save as save

    return save(directory, state)


def _plan(value):
    if not isinstance(value, dict):
        raise ValueError("writing plan must be a JSON object")
    return validate_plan(
        {key: item for key, item in value.items() if key != "revision"}
    ).model_dump(mode="json")


def _global_scopes(content):
    return {
        "headline": [content["headline"]] if content.get("headline") else [],
        "summary": content["summary"],
        "skills": content["skills"],
    }


def _headline(state, current, retained):
    previous = (retained or {}).get("headline")
    locked = "headline" in state["payload"].get("retained_protected_scopes", [])
    result = previous if locked or previous and previous["origin"] == "human" else current
    if (
        state["payload"].get("headline_required")
        and result is None
        and not (retained is not None and locked and previous is None)
    ):
        raise ValueError("this template requires job-specific career positioning")
    return deepcopy(result)


def configure(store, directory, state, proposed, *, main_writer_id=None):
    """Select and order only delivered canonical experiences and accepted inferences."""
    try:
        original = _plan(state["payload"]["content_plan"])
        plan = _plan(original if proposed is None else proposed)
        main_writer_id = main_writer_id or state.get("main_writer_id")
        if (any(_global_scopes(plan).values()) or main_writer_id is not None) and (
            not isinstance(main_writer_id, str) or not main_writer_id.strip()
        ):
            raise ValueError("global content needs its actual writer identity")
        if main_writer_id and (
            main_writer_id == state.get("final_reviewer_id")
            or any(
                fragment["writer_id"] == main_writer_id for fragment in state["fragments"].values()
            )
        ):
            raise ValueError("global and experience writer roles must differ")
        fixed = (
            ("application_id", "template_revision")
            if "template_revision" in original
            else ("application_id", "profile", "education")
        )
        if any(plan.get(key) != original[key] for key in fixed):
            raise ValueError("fixed template or identity binding changed")
        assigned = {row["experience_id"]: row for row in original["assignments"]}
        for assignment in plan["assignments"]:
            fixed = assigned.get(assignment["experience_id"])
            if fixed is None or any(
                assignment[key] != fixed[key]
                for key in assignment
                if key not in {"writing_requirements", "assignment_revision"}
            ):
                raise ValueError("assignment exceeds delivered scope")
            assignment["assignment_revision"] = digest(
                {key: value for key, value in assignment.items() if key != "assignment_revision"}
            )
        retained = _retained(state, plan)
        _headline(state, plan.get("headline"), retained)
        # Assembly checks global references and duplicate identities as one boundary.
        placeholders = [
            {
                "schema_version": "experience-writing/v1",
                "assignment_revision": row["assignment_revision"],
                "experience_id": row["experience_id"],
                "candidate_id": row["candidate_id"],
                "status": "complete",
                "items": [
                    {
                        "id": "scope-check-" + row["experience_id"],
                        "text": "Scope check",
                        "fact_refs": row["allowed_fact_refs"][:1],
                        "inference_refs": row["allowed_inference_refs"][:1],
                    }
                ],
            }
            for row in plan["assignments"]
        ]
        assemble_content(plan, placeholders)
    except (ValueError, TypeError, KeyError) as exc:
        raise _invalid("JSON 写作计划超出本轮已交付经历、引用或固定资料。") from exc
    plan["revision"] = digest(plan)
    state["writing_plan"] = plan
    if main_writer_id is not None:
        state["main_writer_id"] = main_writer_id
    state["experiences"] = [
        {
            "experience_id": row["experience_id"],
            "candidate_id": row["candidate_id"],
            "input_revision": row["assignment_revision"],
        }
        for row in plan["assignments"]
    ]
    revisions = {row["experience_id"]: row["input_revision"] for row in state["experiences"]}
    state["fragments"] = {
        eid: fragment
        for eid, fragment in state["fragments"].items()
        if fragment["input_revision"] == revisions.get(eid)
    }
    state["mapping_required"] = False
    state["status"] = "writing_required"
    state.pop("review", None)
    state.pop("candidate_sha256", None)
    return _save(directory, state)


def writer_context(state, experience_id):
    assignment = next(
        (
            row
            for row in state.get("writing_plan", {}).get("assignments", [])
            if row["experience_id"] == experience_id
        ),
        None,
    )
    if assignment is None:
        raise _invalid("经历未分派。")
    retained = state["payload"].get("retained_content", {})
    previous_experience = next(
        (row for row in retained.get("experiences", []) if row["id"] == experience_id), None
    )
    return {
        "experience_id": experience_id,
        "candidate_id": assignment["candidate_id"],
        "input_revision": assignment["assignment_revision"],
        "assignment": deepcopy(assignment),
        "instructions": WRITER_INSTRUCTIONS,
        # Strict output makes every offered field mandatory; installed MC-11 writers
        # then claimed human provenance, which validation rightly refuses.
        "output_schema": writer_schema(TypeAdapter(WritingResult).json_schema()),
        "previous_fragment": deepcopy(state["fragments"].get(experience_id)),
        "retained_items": deepcopy((previous_experience or {}).get("items", [])),
        "retained_structure_protected": experience_id
        in state["payload"].get("retained_protected_scopes", []),
        "review_feedback": deepcopy(state.get("writer_feedback", {}).get(experience_id)),
    }


def submit(directory, state, context, response, writer_id):
    if writer_id in {state.get("main_writer_id"), state.get("final_reviewer_id")} or any(
        eid != context["experience_id"] and fragment["writer_id"] == writer_id
        for eid, fragment in state["fragments"].items()
    ):
        raise _invalid("每段经历须由独立写作者提交。")
    try:
        result = validate_fragment(response, context["assignment"])
    except (ValueError, TypeError) as exc:
        raise _invalid("经历 JSON 字段、身份、版本或逐项引用无效。") from exc
    fragment = {
        "input_revision": context["input_revision"],
        "writer_id": writer_id,
        "status": result["status"],
        "issues": deepcopy(result.get("requests", [])),
        "content_fragment": result,
    }
    fragment["revision"] = digest(fragment)
    state["fragments"][context["experience_id"]] = fragment
    if result["status"] == "complete":
        state.get("writer_feedback", {}).pop(context["experience_id"], None)
    helper.atomic_write_json(
        directory / ("fragment-" + digest(context["experience_id"])[:16] + ".json"), fragment
    )
    state.pop("review", None)
    state.pop("candidate_sha256", None)
    state.pop("content_revision", None)
    state["status"] = "writing_required"
    return _save(directory, state)


def output(state):
    if state["mapping_required"]:
        raise _invalid("请先分派 JSON 经历写作任务。")
    try:
        content = assemble_content(
            _plan(state["writing_plan"]),
            [fragment["content_fragment"] for fragment in state["fragments"].values()],
        )
        retained = _retained(state, _plan(state["writing_plan"]))
        headline = _headline(state, content.get("headline"), retained)
        if headline:
            content["headline"] = headline
        else:
            content.pop("headline", None)
        if retained:
            scopes = set(state["payload"].get("retained_protected_scopes", []))
            for key in ("summary", "skills"):
                content[key] = _retain_items(content[key], retained[key], locked=key in scopes)
            by_id = {row["id"]: row for row in content["experiences"]}
            for experience in retained["experiences"]:
                if experience["id"] in by_id:
                    current = by_id[experience["id"]]
                    current["items"] = _retain_items(
                        current["items"], experience["items"], locked=experience["id"] in scopes
                    )
            content["revision"] = content_revision(content)
            validate_content(content)
    except (ValueError, TypeError, KeyError) as exc:
        raise _invalid("经历 JSON 缺失、需补充资料或版本不符，不能静默省略。") from exc
    return {"resume_content": content}


def _retain_items(current, previous, *, locked=False):
    if locked:
        return deepcopy(previous)
    protected = [(index, item) for index, item in enumerate(previous) if item["origin"] == "human"]
    ids = {item["id"] for _, item in protected}
    result = [item for item in current if item["id"] not in ids]
    for index, item in protected:
        if index > len(result):
            raise ValueError("protected human item position cannot be removed")
        result.insert(index, deepcopy(item))
    return result


def _retained(state, plan):
    selected = [row["experience_id"] for row in plan["assignments"]]
    if set(selected) & set(state["payload"].get("retained_omitted_experience_ids", [])):
        raise ValueError("retained omission cannot be restored by a writer")
    previous = state["payload"].get("retained_content")
    if previous is None:
        return None
    previous = validate_content(previous).model_dump(mode="json")
    if previous["application_id"] != plan["application_id"] or (
        "template_revision" in plan
        and previous.get("template_revision") != plan["template_revision"]
    ):
        raise ValueError("retained content belongs to another application or template")
    scopes = state["payload"].get("retained_protected_scopes", [])
    supported = set(_global_scopes(previous)) | {row["id"] for row in previous["experiences"]}
    if (
        not isinstance(scopes, list)
        or any(not isinstance(scope, str) for scope in scopes)
        or len(scopes) != len(set(scopes))
        or not set(scopes) <= supported
    ):
        raise ValueError("retained structure scope is invalid")
    existing = [row["id"] for row in previous["experiences"] if row["id"] in selected]
    if [eid for eid in selected if eid in existing] != existing:
        raise ValueError("retained experience order cannot change")
    protected_experiences = {
        row["id"]
        for row in previous["experiences"]
        if any(item["origin"] == "human" for item in row["items"])
    }
    protected_experiences.update(set(scopes) - set(_global_scopes(previous)))
    if not protected_experiences <= set(selected):
        raise ValueError("retained human experience cannot be omitted")
    assignments = {row["experience_id"]: row for row in plan["assignments"]}
    all_facts = {ref for row in assignments.values() for ref in row["allowed_fact_refs"]}
    all_inferences = {ref for row in assignments.values() for ref in row["allowed_inference_refs"]}
    for key, items in _global_scopes(previous).items():
        for item in items:
            if (item["origin"] == "human" or key in scopes) and (
                not set(item["fact_refs"]) <= all_facts
                or not set(item["inference_refs"]) <= all_inferences
            ):
                raise ValueError("retained global references are no longer assigned")
    for row in previous["experiences"]:
        assignment = assignments.get(row["id"])
        if assignment is None:
            continue
        for item in row["items"]:
            if (item["origin"] == "human" or row["id"] in scopes) and (
                not set(item["fact_refs"]) <= set(assignment["allowed_fact_refs"])
                or not set(item["inference_refs"]) <= set(assignment["allowed_inference_refs"])
            ):
                raise ValueError("retained experience references changed scope")
    return previous


def assemble(store, directory, state, *, capture_sibling=True):
    content = output(state)["resume_content"]
    try:
        from .application_resume_versions import _content_template

        template = _content_template(store, state)
        rendered = render_resume(content, template=template)
    except ValueError as exc:
        raise _invalid("内容 JSON 无法由固定模板安全渲染。") from exc
    plan = {
        "latex_source": rendered.tex,
        "resume_content": content,
        "template_revision": rendered.template_revision,
        "renderer_revision": rendered.renderer_revision,
        "item_ranges": {key: list(value) for key, value in rendered.ranges.items()},
        "review_groups": [],
        "omitted_groups": [],
        "verification_queue": [],
        "limitations": [],
        "block_mapping": [],
    }
    helper.atomic_write_json(directory / "assembled-plan.json", plan)
    helper.atomic_write_json(directory / "resume-content.json", content)
    path = directory / "candidate-main.tex"
    path.write_text(rendered.tex)
    path.chmod(0o600)
    candidate = hashlib.sha256(rendered.tex.encode()).hexdigest()
    if state.get("candidate_sha256") != candidate:
        state.pop("review", None)
    provider = getattr(store, "cover_letter_provider", None)
    if capture_sibling and provider is not None:
        sibling = provider(
            state["application_id"], state.get("analysis_binding", {}).get("analysis_id")
        )
        if sibling is None:
            state.pop("sibling_cover_letter", None)
        else:
            from .application_cover_letter import validate_letter

            try:
                sibling = validate_letter(sibling)
                if sibling["application_id"] != state["application_id"]:
                    raise ValueError("sibling letter belongs to another application")
            except (ValueError, TypeError, KeyError) as exc:
                raise _invalid("同岗求职信版本不能核验，保留两份原稿。") from exc
            state["sibling_cover_letter"] = sibling
    state.update(
        candidate_sha256=candidate,
        content_revision=content["revision"],
        status="review_required",
    )
    return {
        **_save(directory, state),
        **plan,
        "fragments": deepcopy(state["fragments"]),
    }


def review_context(state):
    return {
        "id": state["id"],
        "generation_contract": state["generation_contract"],
        "candidate_sha256": state["candidate_sha256"],
        "resume_content": output(state)["resume_content"],
        "retained_protected_scopes": deepcopy(
            state["payload"].get("retained_protected_scopes", [])
        ),
        "writing_plan": deepcopy(state["writing_plan"]),
        "instructions": REVIEW_INSTRUCTIONS,
        "job_brief": deepcopy(state["payload"].get("job_brief")),
        "inference_result": deepcopy(state["payload"].get("inference_result")),
        **(
            {"sibling_cover_letter": deepcopy(state["sibling_cover_letter"])}
            if state.get("sibling_cover_letter") is not None
            else {}
        ),
    }


def review(
    store,
    directory,
    state,
    *,
    candidate_sha256,
    reviewer_id,
    passed,
    issues,
    content_patch,
    rewrite_experience_ids,
):
    rewrites = [] if rewrite_experience_ids is None else rewrite_experience_ids
    if (
        not isinstance(rewrites, list)
        or any(not isinstance(eid, str) for eid in rewrites)
        or len(set(rewrites)) != len(rewrites)
        or not set(rewrites) <= {row["experience_id"] for row in state["experiences"]}
        or rewrites
        and (passed or content_patch is not None)
    ):
        raise _invalid("实质返工只能退回已分派经历，不能同时采用补丁或通过。")
    if state.get("final_reviewer_id", reviewer_id) != reviewer_id:
        raise _invalid("此任务须由同一终审角色接续。")
    updated = deepcopy(state)
    content = output(updated)["resume_content"]
    if content_patch is not None:
        items = [item for scope in _global_scopes(content).values() for item in scope]
        for experience in content["experiences"]:
            items += experience["items"]
        protected_scopes = set(state["payload"].get("retained_protected_scopes", []))
        protected_ids = {
            item["id"]
            for scope, scope_items in {
                **_global_scopes(content),
                **{row["id"]: row["items"] for row in content["experiences"]},
            }.items()
            if scope in protected_scopes
            for item in scope_items
        }
        try:
            patched = apply_content_patch(
                content,
                content_patch,
                allowed_targets=[
                    {"item_id": item["id"], "fields": ["text", "links"]}
                    for item in items
                    if item["origin"] == "ai"
                    and not item["protected"]
                    and item["id"] not in protected_ids
                ],
            )
        except (ValueError, TypeError) as exc:
            raise _invalid("内容终审补丁超出允许字段、人工保护或原文版本不符。") from exc
        updated["writing_plan"].update(
            summary=[deepcopy(item) for item in patched["summary"] if item["origin"] == "ai"],
            skills=[deepcopy(item) for item in patched["skills"] if item["origin"] == "ai"],
        )
        if patched.get("headline") and patched["headline"]["origin"] == "ai":
            updated["writing_plan"]["headline"] = deepcopy(patched["headline"])
        updated["writing_plan"]["revision"] = digest(
            {key: value for key, value in updated["writing_plan"].items() if key != "revision"}
        )
        for experience in patched["experiences"]:
            fragment = updated["fragments"][experience["id"]]
            patch_items = {
                item["id"]: item for item in experience["items"] if item["origin"] == "ai"
            }
            fragment["content_fragment"]["items"] = [
                deepcopy(patch_items.get(item["id"], item))
                for item in fragment["content_fragment"]["items"]
            ]
            fragment["revision"] = digest(
                {key: value for key, value in fragment.items() if key != "revision"}
            )
        # Revalidate the complete content before replacing candidate files.
        content = output(updated)["resume_content"]
        assemble(store, directory, updated, capture_sibling=False)
        for eid, fragment in updated["fragments"].items():
            helper.atomic_write_json(
                directory / ("fragment-" + digest(eid)[:16] + ".json"), fragment
            )
    review_result = {
        "candidate_sha256": updated["candidate_sha256"],
        "original_candidate_sha256": candidate_sha256,
        "content_revision": content["revision"],
        "reviewer_id": reviewer_id,
        "passed": passed,
        "issues": deepcopy(issues),
        "content_patch": deepcopy(content_patch),
        "rewrite_experience_ids": list(rewrites),
        "input_revision": digest(output(updated)),
        **(
            {"sibling_cover_letter_revision": updated["sibling_cover_letter"]["revision"]}
            if updated.get("sibling_cover_letter") is not None
            else {}
        ),
    }
    updated.update(review=review_result, final_reviewer_id=reviewer_id)
    if rewrites:
        for eid in rewrites:
            updated["fragments"].pop(eid)
            updated.setdefault("writer_feedback", {})[eid] = {
                "reviewer_id": reviewer_id,
                "candidate_sha256": candidate_sha256,
                "issues": deepcopy(issues),
            }
        updated.pop("candidate_sha256", None)
        updated.pop("content_revision", None)
        updated["status"] = "writing_required"
    history = directory / "experience-reviews.jsonl"
    with history.open("a") as stream:
        stream.write(json.dumps(review_result, ensure_ascii=False) + "\n")
    history.chmod(0o600)
    return _save(directory, updated)
