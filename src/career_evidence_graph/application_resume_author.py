"""Execute the existing JSON resume handoff with durable, independently scoped calls."""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

from ._vendor import job_apply_store as helper
from .application_resume_content import (
    ContentPatch,
    PatchExpectedValueMismatch,
    validate_plan,
    writer_schema,
)
from .career_portal_data import PortalDataError
from .codex_cli import run_codex_exec
from .material_author import author_call, record_rejection
from .validation.hashing import record_digest as digest


def _failure(code, message):
    return PortalDataError(code, message, 409)


def _selected_view(context):
    """The previous plan as the planner may reuse it: only the user's chosen experiences.

    2026-11-16 (Roche): the user swapped Prism Local for GSD Core; the planner saw the old
    plan with Prism Local and copied its headline/summary references, and every retry
    was refused. Global lines citing an unchosen experience are left out.
    """
    chosen = set((context.get("user_selection") or {}).get("experiences") or [])
    plan = context.get("writing_plan")
    if not chosen or not isinstance(plan, dict):
        return context

    def owned(item):
        return all(
            ref.split("::", 1)[0] in chosen
            for ref in [*item.get("fact_refs", []), *item.get("inference_refs", [])]
        )

    view = plan | {
        "assignments": [
            row for row in plan.get("assignments", []) if row["candidate_id"] in chosen
        ],
        **{
            key: [item for item in plan.get(key) or [] if owned(item)]
            for key in ("summary", "skills")
        },
    }
    if isinstance(plan.get("headline"), dict) and not owned(plan["headline"]):
        view["headline"] = None
    return context | {"writing_plan": view}


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


def _plan_choices_schema(full, *, reply=False, count=5):
    """The planner returns only its choices; delivered assignments are never retyped.

    With the user's feedback it also answers that feedback in user_reply (2026-11-12).
    """
    properties = full["properties"]
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            **({"user_reply": {"type": "string"}} if reply else {}),
            **{
                key: properties[key]
                for key in ("headline", "summary", "skills")
                if key in properties
            },
            "assignments": {
                "type": "array",
                # 2026-11-10: a résumé keeps 3 to 5 experiences (the prompt says which);
                # the user's own selection may keep more (2026-11-12).
                "maxItems": max(5, count),
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


def _expanded_plan(original, choices, *, fixed=False, kept=None):
    """Rebuild the full plan from delivered assignments in the planner's chosen order.

    With the user's own selection every delivered assignment stays in its delivered
    order; the planner only writes the points (2026-11-12).
    """
    delivered = {row["experience_id"]: row for row in original["assignments"]}
    plan = {key: deepcopy(value) for key, value in original.items() if key != "assignments"}
    plan.update({key: deepcopy(choices[key]) for key in ("summary", "skills") if key in choices})
    if choices.get("headline") is not None:
        plan["headline"] = deepcopy(choices["headline"])
    written = {row["experience_id"]: row["writing_requirements"] for row in choices["assignments"]}
    written.update(kept or {})
    order = list(delivered) if fixed else list(written)
    plan["assignments"] = [
        delivered[eid]
        | {"writing_requirements": list(written.get(eid, delivered[eid]["writing_requirements"]))}
        for eid in order
    ]
    return plan


def _require_points(plan, kept=None):
    """Each planned experience needs a job-specific point beyond the fixed writer instruction.

    2026-11-15 (G-Research): after the user's selection the planner returned only the
    delivered default, and the points review showed every experience empty.
    """
    from .application_writing import DEFAULT_WRITING_REQUIREMENT

    empty = [
        row["experience_id"]
        for row in plan["assignments"]
        if row["experience_id"] not in (kept or {})
        and not any(
            text.strip() and text != DEFAULT_WRITING_REQUIREMENT
            for text in row["writing_requirements"]
        )
    ]
    if empty:
        raise ValueError(
            "writing_requirements must give each kept experience at least one job-specific"
            " point beyond the default instruction; missing for " + ", ".join(empty)
        )


def _one_edit(a, b):
    if a == b or abs(len(a) - len(b)) > 1:
        return False
    if len(a) == len(b):
        return sum(x != y for x, y in zip(a, b, strict=True)) == 1
    short, long = sorted((a, b), key=len)
    return any(long[:i] + long[i + 1 :] == short for i in range(len(long)))


def repaired_experience_ids(choices, experience_ids):
    """Correct an experience ID the planner miscopied by one character.

    2026-11-18 (mobilezone): ``exp-7ebeb094eceebcce`` came back as
    ``exp-7ebeb094eceebce`` in both answers, which were refused. In experience IDs
    and references only, a hex ID absent from the delivered ones that is one edit
    from exactly one of them is replaced; anything else still fails validation.
    Returns the corrections made.
    """
    import re

    known = {eid.removeprefix("exp-") for eid in experience_ids}
    repairs = {}

    def fix(text):
        def replace(match):
            token = match.group(0)
            near = [] if token in known else [h for h in known if _one_edit(token, h)]
            if len(near) != 1:
                return token
            repairs[token] = near[0]
            return near[0]

        return re.sub(r"[0-9a-f]{8,}", replace, text) if isinstance(text, str) else text

    def walk(value):
        if isinstance(value, list):
            for item in value:
                walk(item)
        elif isinstance(value, dict):
            for key, item in value.items():
                if key == "experience_id":
                    value[key] = fix(item)
                elif key.endswith("_refs") and isinstance(item, list):
                    value[key] = [fix(ref) for ref in item]
                else:
                    walk(item)

    walk(choices)
    return [{"from": old, "to": new} for old, new in repairs.items()]


def _ref_key(ref):
    """A reference's identity without its typography: ``exp-`` prefixes, a repeated
    owner, case and surrounding space (2026-11-24: the planner both added and dropped
    ``exp-`` and repeated the owner, rejecting whole résumés)."""
    parts = [part.strip().casefold().removeprefix("exp-") for part in ref.split("::")]
    parts = [part for part in parts if part]
    if not parts:
        return None
    owner, local = (parts[0], parts[-1]) if len(parts) > 1 else (None, parts[0])
    if owner and local.startswith(owner + "-"):
        local = local[len(owner) + 1 :]
    return owner, local


def repaired_refs(refs, allowed):
    """Each reference that names exactly one allowed reference by its key, and the
    corrections made; anything else is kept for validation to refuse."""
    keys = {}
    for ref in allowed:
        if (key := _ref_key(ref)) is not None:
            keys.setdefault(key, set()).add(ref)
    fixed, repairs = [], []
    for ref in refs:
        if isinstance(ref, str) and ref not in allowed and (key := _ref_key(ref)):
            names = keys.get(key, set())
            if key[0] is None:
                names = {
                    name
                    for (owner, local), group in keys.items()
                    if key[1] in {local, f"{owner}-{local}"}
                    for name in group
                }
            if len(names) == 1:
                (name,) = names
                repairs.append({"from": ref, "to": name})
                ref = name
        if not (isinstance(ref, str) and ref in fixed):
            # Two spellings of one reference are one citation, not a duplicate.
            fixed.append(ref)
    return fixed, repairs


def repaired_global_refs(plan):
    """Correct a global reference only when it names exactly one delivered reference.

    2026-11-04 and 2026-11-24: the planner wrote ``exp-X::exp-X-fact``, ``exp-X::X-fact``
    and ``exp-X::exp-X::fact`` for delivered references. Only typography differs;
    a reference that matches no delivered one, or several, still fails validation.
    Returns the corrections made.
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
            item[f"{kind}_refs"], made = repaired_refs(refs, allowed[kind])
            repairs += made
    return repairs


def _rejected(directory, error):
    record_rejection(directory, error)
    raise _failure("resume_author_failed", "简历作者输出未通过程序核验，已保留原响应。") from error


def plan_overview(context):
    """The chosen and omitted experiences and global content the user reviews.

    2026-11-12 (user decision): a high-match, target-company or high-salary job stops
    after planning so the user confirms which experiences enter and how they are ordered.
    """
    from .application_writing import DEFAULT_WRITING_REQUIREMENT

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
            described(row)
            | {
                # The fixed writer instruction says nothing to the user (2026-11-12).
                "writing_requirements": [
                    text
                    for text in row["writing_requirements"]
                    if text != DEFAULT_WRITING_REQUIREMENT
                ]
            }
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
        "reply": (context.get("previous_user_reply") or {}).get("text"),
        "feedback": (
            [feedback]
            if isinstance(feedback := context.get("user_plan_feedback"), str)
            else list(feedback or [])
        ),
    }


def _execute_content_generation(
    store,
    identifier,
    *,
    runner=None,
    allow_calls=True,
    admit_call=None,
    review_plan=None,
    review_wording=None,
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
        schema = _plan_choices_schema(
            type(validate_plan(original)).model_json_schema(),
            reply="user_plan_feedback" in context,
            count=len(original["assignments"]),
        )
        # A refused plan is asked once more with the reason before the job stops.
        for attempt in range(2):
            choices, main_writer, call = _call(
                store,
                identifier,
                "plan",
                _selected_view(context),
                schema,
                runner,
                allow_calls,
                admit_call,
            )
            try:
                slips = repaired_experience_ids(
                    choices, [row["experience_id"] for row in original["assignments"]]
                )
                if slips:
                    helper.atomic_write_json(call / "id-repairs.json", {"repairs": slips})
                    print("resume_plan_experience_id_repaired: " + json.dumps(slips), flush=True)
                plan = _expanded_plan(
                    original,
                    choices,
                    fixed=bool(context.get("user_selection")),
                    kept=context.get("kept_points"),
                )
                _require_points(plan, context.get("kept_points"))
                repairs = repaired_global_refs(plan)
                if repairs:
                    helper.atomic_write_json(call / "reference-repairs.json", {"repairs": repairs})
                    print("resume_plan_reference_repaired: " + json.dumps(repairs), flush=True)
                generation.configure_generation(
                    store, identifier, writing_plan=plan, main_writer_id=main_writer
                )
                if isinstance(choices.get("user_reply"), str) and choices["user_reply"].strip():
                    generation.set_plan_reply(store, identifier, choices["user_reply"].strip())
                break
            except (PortalDataError, ValueError, TypeError, KeyError) as error:
                if attempt:
                    _rejected(call, error)
                record_rejection(call, error)
    if allow_calls and review_plan is not None:
        current = generation.generation_state(store, identifier)
        plan = current["writing_plan"]
        # 2026-11-12 (user decision): a high-value job's user first checks each
        # requirement's evidence and picks the experiences; review_plan(None) says
        # whether that choice is needed.
        if not current.get("user_selection") and not review_plan(None):
            raise _failure("resume_plan_review_required", "简历证据与选材等你确认。")
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
        # 2026-11-12 (user decision): a high-value job's drafted bullets wait for the
        # user before the résumé is assembled, reviewed and generated.
        if (
            allow_calls
            and review_wording is not None
            and review_wording()
            and not generation.wording_is_approved(store, identifier)
        ):
            raise _failure("resume_wording_review_required", "简历表述等你确认。")
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
        for attempt in range(2):
            response, reviewer, call = _call(
                store, identifier, "review", review, schema, runner, allow_calls, admit_call
            )
            try:
                if not isinstance(response, dict) or set(response) != set(schema["required"]):
                    raise ValueError("review response fields do not match")
                # Preserve the independent reviewer identity across local rewrites.
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
                break
            except (PortalDataError, ValueError, TypeError, KeyError) as error:
                if (
                    attempt
                    or not allow_calls
                    or not isinstance(error.__cause__, PatchExpectedValueMismatch)
                ):
                    _rejected(call, error)
                record_rejection(call, error)
        if reviewed.get("review", {}).get("passed"):
            return generation.adopt_generation(store, identifier)
        if not response.get("rewrite_experience_ids"):
            raise _failure("resume_author_failed", "简历终审要求修改，原稿与问题已保留。")
    raise _failure("resume_author_failed", "简历局部返工尚未通过终审，已保留完成经历。")


def execute_content_generation(
    store,
    identifier,
    *,
    runner=None,
    allow_calls=True,
    admit_call=None,
    review_plan=None,
    review_wording=None,
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
            review_wording=review_wording,
        )
    except PortalDataError:
        raise
    except Exception as error:
        raise _failure(
            "resume_author_needs_recheck", "简历作者或本地保存结果尚未核验，原回执已保留。"
        ) from error
