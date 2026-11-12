"""Execute the existing JSON resume handoff with durable, independently scoped calls."""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

from ._vendor import job_apply_store as helper
from .application_resume_content import ContentPatch, validate_plan, writer_schema
from .career_portal_data import PortalDataError
from .codex_cli import run_codex_exec
from .material_author import author_call, record_rejection
from .validation.hashing import record_digest as digest


def _failure(code, message):
    return PortalDataError(code, message, 409)


def _call(store, identifier, role, context, schema, runner, allow_calls, admit_call):
    """One résumé author call; see ``material_author.author_call``."""
    return author_call(
        Path(store.root) / identifier / "automatic-authors",
        store.applications.write_lock(),
        role,
        context,
        schema,
        runner,
        allow_calls=allow_calls,
        admit_call=admit_call,
    )


def _plan_choices_schema(full):
    """The planner returns only its choices; delivered assignments are never retyped."""
    properties = full["properties"]
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            **{
                key: properties[key]
                for key in ("headline", "summary", "skills")
                if key in properties
            },
            "assignments": {
                "type": "array",
                # 2026-11-10: a résumé keeps 3 to 5 experiences (the prompt says which).
                "maxItems": 5,
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "experience_id": {"type": "string"},
                        "writing_requirements": {"type": "array", "items": {"type": "string"}},
                    },
                },
            },
        },
        **({"$defs": writer_schema(full)["$defs"]} if "$defs" in full else {}),
    }


def _expanded_plan(original, choices):
    """Rebuild the full plan from delivered assignments in the planner's chosen order."""
    delivered = {row["experience_id"]: row for row in original["assignments"]}
    plan = {key: deepcopy(value) for key, value in original.items() if key != "assignments"}
    plan.update({key: deepcopy(choices[key]) for key in ("summary", "skills") if key in choices})
    if choices.get("headline") is not None:
        plan["headline"] = deepcopy(choices["headline"])
    plan["assignments"] = [
        delivered[row["experience_id"]]
        | {"writing_requirements": list(row["writing_requirements"])}
        for row in choices["assignments"]
    ]
    return plan


def repaired_global_refs(plan):
    """Correct a global reference only when it names exactly one delivered reference.

    A planner copied ``exp-X::exp-X-fact-0014`` for the delivered ``exp-X::X-fact-0014``
    (the same experience's CV lines do carry the ``exp-`` prefix; 2026-11-04). Only that
    extra prefix is removed, and only when the result is a reference of a chosen
    experience; anything else still fails validation. Returns the corrections made.
    """
    allowed = {
        kind: {ref for row in plan["assignments"] for ref in row[f"allowed_{kind}_refs"]}
        for kind in ("fact", "inference")
    }
    items = [plan["headline"]] if isinstance(plan.get("headline"), dict) else []
    items += [row for key in ("summary", "skills") for row in plan.get(key) or []]
    repairs = []
    for item in items:
        for kind in ("fact", "inference"):
            refs = item.get(f"{kind}_refs") if isinstance(item, dict) else None
            if not isinstance(refs, list):
                continue
            fixed = []
            for ref in refs:
                if isinstance(ref, str) and ref not in allowed[kind] and "::" in ref:
                    owner, local = ref.split("::", 1)
                    candidate = f"{owner}::{local.removeprefix('exp-')}"
                    if local.startswith("exp-") and candidate in allowed[kind]:
                        repairs.append({"from": ref, "to": candidate})
                        ref = candidate
                fixed.append(ref)
            item[f"{kind}_refs"] = fixed
    return repairs


def _rejected(directory, error):
    record_rejection(directory, error)
    raise _failure("resume_author_failed", "简历作者输出未通过程序核验，已保留原响应。") from error


def plan_overview(context):
    """The chosen and omitted experiences and global content the user reviews.

    2026-11-12 (user decision): a high-match, target-company or high-salary job stops
    after planning so the user confirms which experiences enter and how they are ordered.
    """

    def described(row):
        experience = row["experience"]
        return {
            "experience_id": row["experience_id"],
            "title": experience.get("title", ""),
            "role": experience.get("role"),
            "organization": experience.get("organization"),
            "start": experience.get("start"),
            "end": experience.get("end"),
        }

    plan = context["writing_plan"]
    chosen = {row["experience_id"] for row in plan["assignments"]}
    headline = plan.get("headline")
    return {
        "chosen": [
            described(row) | {"writing_requirements": list(row["writing_requirements"])}
            for row in plan["assignments"]
        ],
        "omitted": [
            described(row)
            for row in context["content_plan"]["assignments"]
            if row["experience_id"] not in chosen
        ],
        "headline": headline["text"] if isinstance(headline, dict) else None,
        "summary": [row["text"] for row in plan.get("summary") or []],
        "skills": [row["text"] for row in plan.get("skills") or []],
        "feedback": context.get("user_plan_feedback"),
    }


def _execute_content_generation(
    store, identifier, *, runner=None, allow_calls=True, admit_call=None, review_plan=None
):
    """Run missing authors, then the existing semantic review and adoption Interfaces.

    Model calls run outside the application lock. Completed scoped fragments and
    reviewed candidates are reused. Receipt-only reconciliation starts no models.
    """
    from . import application_experience_latex as generation

    runner = runner or run_codex_exec
    context = generation.generation_context(store, identifier)
    if context.get("generation_contract") != "content-writing/v1":
        raise _failure("resume_author_failed", "自动作者仅支持已交付的 JSON 内容契约。")
    if context.get("adopted_draft"):
        return generation.adopt_generation(store, identifier)
    if context.get("mapping_required"):
        original = context["content_plan"]
        schema = _plan_choices_schema(type(validate_plan(original)).model_json_schema())
        choices, main_writer, call = _call(
            store, identifier, "plan", context, schema, runner, allow_calls, admit_call
        )
        try:
            plan = _expanded_plan(original, choices)
            repairs = repaired_global_refs(plan)
            if repairs:
                helper.atomic_write_json(call / "reference-repairs.json", {"repairs": repairs})
                print("resume_plan_reference_repaired: " + json.dumps(repairs), flush=True)
            generation.configure_generation(
                store, identifier, writing_plan=plan, main_writer_id=main_writer
            )
        except (PortalDataError, ValueError, TypeError, KeyError) as error:
            _rejected(call, error)
    if allow_calls and review_plan is not None:
        plan = generation.generation_state(store, identifier)["writing_plan"]
        if not review_plan(plan):
            raise _failure("resume_plan_review_required", "简历选材和结构等你确认。")
    for _ in range(3):
        state = generation.generation_state(store, identifier)
        for experience in state["experiences"]:
            eid = experience["experience_id"]
            if eid in state["completed_experience_ids"]:
                continue
            if state.get("fragment_status", {}).get(eid) == "needs_material":
                raise _failure("resume_author_material_required", "简历经历需要补充重要事实。")
            scoped = generation.writer_context(store, identifier, eid)
            response, writer, call = _call(
                store,
                identifier,
                "experience-" + digest(eid)[:16],
                scoped,
                scoped["output_schema"],
                runner,
                allow_calls,
                admit_call,
            )
            try:
                submitted = generation.submit_fragment(
                    store,
                    identifier,
                    eid,
                    input_revision=scoped["input_revision"],
                    writer_id=writer,
                    content_fragment=response,
                )
            except (PortalDataError, ValueError, TypeError, KeyError) as error:
                _rejected(call, error)
            if submitted.get("fragment_status", {}).get(eid) == "needs_material":
                raise _failure("resume_author_material_required", "简历经历需要补充重要事实。")
        state = generation.generation_state(store, identifier)
        if state.get("review", {}).get("passed"):
            return generation.adopt_generation(store, identifier)
        generation.assemble_generation(store, identifier)
        review = generation.review_context(store, identifier)
        patch_schema = ContentPatch.model_json_schema()
        definitions = patch_schema.pop("$defs", {})
        schema = {
            "type": "object",
            "additionalProperties": False,
            "$defs": definitions,
            "properties": {
                "passed": {"type": "boolean"},
                "issues": {"type": "array", "items": {"type": "string"}},
                "content_patch": {"anyOf": [patch_schema, {"type": "null"}]},
                "rewrite_experience_ids": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["passed", "issues", "content_patch", "rewrite_experience_ids"],
        }
        response, reviewer, call = _call(
            store, identifier, "review", review, schema, runner, allow_calls, admit_call
        )
        try:
            if not isinstance(response, dict) or set(response) != set(schema["required"]):
                raise ValueError("review response fields do not match")
            # Preserve one reviewer identity through local rewrites and patches; the
            # generation keeps it as final_reviewer_id (2026-11-08: finnova's second review
            # sent a new id and was refused).
            reviewer = (
                state.get("final_reviewer_id")
                or state.get("review", {}).get("reviewer_id")
                or reviewer
            )
            reviewed = generation.review_generation(
                store,
                identifier,
                candidate_sha256=review["candidate_sha256"],
                reviewer_id=reviewer,
                **response,
            )
        except (PortalDataError, ValueError, TypeError, KeyError) as error:
            _rejected(call, error)
        if reviewed.get("review", {}).get("passed"):
            return generation.adopt_generation(store, identifier)
        if not response.get("rewrite_experience_ids"):
            raise _failure("resume_author_failed", "简历终审要求修改，原稿与问题已保留。")
    raise _failure("resume_author_failed", "简历局部返工尚未通过终审，已保留完成经历。")


def execute_content_generation(
    store, identifier, *, runner=None, allow_calls=True, admit_call=None, review_plan=None
):
    """Execute or reconcile the existing content handoff; finished calls never repeat."""
    try:
        return _execute_content_generation(
            store,
            identifier,
            runner=runner,
            allow_calls=allow_calls,
            admit_call=admit_call,
            review_plan=review_plan,
        )
    except PortalDataError:
        raise
    except Exception as error:
        raise _failure(
            "resume_author_needs_recheck", "简历作者或本地保存结果尚未核验，原回执已保留。"
        ) from error
