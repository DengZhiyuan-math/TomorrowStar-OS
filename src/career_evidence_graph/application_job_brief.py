"""One durable JD-only interpretation and conserved business-group framework.

Historical scoring imports remain aliases; candidate comparison owns scoring.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import unicodedata
from copy import deepcopy
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from . import model_call
from ._vendor import job_apply_store as helper
from .application_information import _read_document as _read_bounded_document
from .application_match_scoring import (
    calculate_framework_score as calculate_framework_score,
)
from .application_match_scoring import (
    route_for_score as route_for_score,
)
from .application_storage import private_root
from .career_portal_data import PortalDataError
from .codex_cli import CodexCLIError, run_codex_exec
from .codex_cli import output_validation_marker as _output_validation_marker
from .validation.hashing import record_digest as digest
from .validation.models import CodexCLIConfig

PROTOCOL = "application-job-brief/v1"
FRAMEWORK = "business-group-framework/v1"


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class _Requirement(_Strict):
    text: str = Field(min_length=1, max_length=2000)
    jd_quote: str = Field(min_length=1)


class _Role(_Strict):
    business_objective: str = Field(min_length=1)
    work_outputs: list[str] = Field(min_length=1)
    methods_role: str = Field(min_length=1)

    @field_validator("business_objective", "methods_role", "work_outputs")
    @classmethod
    def _strip_text(cls, value):
        return [item.strip() for item in value] if isinstance(value, list) else value.strip()


class _Group(_Strict):
    label: str = Field(min_length=1)
    jd_quote: str = Field(min_length=1)
    operator: Literal["all", "any"]
    alternatives: list[list[int]] | None = None
    importance: Literal["required", "preferred"]
    hard_condition: bool
    weight: int = Field(ge=1, le=100)
    weight_reason: str = Field(min_length=1)
    requirements: list[_Requirement] = Field(min_length=1)


class _Output(_Strict):
    business_object: str = Field(min_length=1)
    role_understanding: _Role
    groups: list[_Group] = Field(min_length=1)


def _invalid(message="岗位解读或评分框架不能核验。"):
    return PortalDataError("job_brief_invalid", message, 409)


def _normalized(text):
    text = " ".join(unicodedata.normalize("NFKC", text).casefold().split())
    # Internal decimals, operators, and token boundaries change requirement meaning.
    return text.rstrip(" .,;:!?。；：，！？")


def _job(application):
    job = {
        key: application.get(key, "")
        for key in ("company", "role_title", "location", "job_description")
    }
    if (
        not all(isinstance(value, str) for value in job.values())
        or not job["job_description"].strip()
    ):
        raise _invalid("岗位全文缺失或格式错误。")
    if len(job["job_description"].encode("utf-8")) > 48000:
        raise _invalid("岗位全文超过解读输入上限。")
    return job


def _quote_span(quote, jd, start=0):
    """Where a quote occurs in the JD from ``start``, restoring only case and whitespace."""
    if quote.strip():
        index = jd.find(quote, start)
        if index >= 0:
            return index, index + len(quote)
    parts = quote.split()
    if not parts:
        return None
    # A captured LinkedIn JD renders some colons as "{{:}}" (2026-11-04: every
    # "Label: duty" bullet); a quote's plain colon still names that passage.
    pattern = r"\s+".join(re.escape(part).replace(":", r"(?::|\{\{:\}\})") for part in parts)
    # A new tolerant match must not truncate words, decimal numbers or operators.
    pattern = (
        r"(?<![\w+#*/<>=&|%^~\u2010-\u2015\u2212-])(?<!\w\.)(?<!\d,)"
        + pattern
        + r"(?![\w+#*/<>=&|%^~\u2010-\u2015\u2212-]|\.\w|,\d)"
    )
    match = re.compile(pattern, re.IGNORECASE).search(jd, start)
    return match.span() if match else None


def _literal_jd_quote(quote, jd):
    """The literal JD passage a quote names; retain exact matches and source spans.

    A quote that elides words with "..." (2026-11-04: "a Master's ... in Computer
    Science") becomes the whole passage from its first to its last piece, when the
    pieces occur in order within one paragraph.
    """
    span = _quote_span(quote, jd)
    pieces = [piece.strip() for piece in re.split(r"\.\.\.|\u2026", quote) if piece.strip()]
    if span is None and len(pieces) > 1:
        spans, start = [], 0
        for piece in pieces:
            found = _quote_span(piece, jd, start)
            if found is None:
                break
            spans.append(found)
            start = found[1]
        else:
            if "\n" not in jd[spans[0][0] : spans[-1][1]]:
                span = (spans[0][0], spans[-1][1])
    if span is None:
        raise _invalid("岗位引用必须来自岗位全文。")
    return jd[span[0] : span[1]]


def _literal_group_quote(quote, jd):
    """A group may summarize separate JD passages, one per line; each stays literal."""
    try:
        return _literal_jd_quote(quote, jd)
    except PortalDataError:
        return "\n".join(_literal_jd_quote(part, jd) for part in quote.split("\n") if part.strip())


def _canonical_groups(output, jd):
    """Collapse exact normalized duplicates; semantic merging belongs to interpretation."""
    groups = {}
    atom_owners = {}
    for source in output["groups"]:
        group = deepcopy(source)
        if not group["label"].strip() or not group["weight_reason"].strip():
            raise _invalid()
        quote = group["jd_quote"]
        if not quote.strip() or (
            quote not in jd and not all(part and part in jd for part in quote.split("\n"))
        ):
            raise _invalid("岗位分组引用必须来自岗位全文。")
        atoms = {}
        original_keys = []
        for atom in group.pop("requirements"):
            key = _normalized(atom["text"])
            if not key or not atom["jd_quote"].strip() or atom["jd_quote"] not in jd:
                raise _invalid("岗位要求引用必须来自岗位全文。")
            atoms.setdefault(key, atom)
            original_keys.append(key)
        alternatives = _canonical_alternatives(group, original_keys, list(atoms))
        group["alternatives"] = alternatives
        signature = {
            "atoms": sorted(atoms),
            "operator": group["operator"],
            "alternatives": None
            if alternatives is None
            else sorted(sorted(list(atoms)[index] for index in clause) for clause in alternatives),
            "importance": group["importance"],
            "hard_condition": group["hard_condition"],
        }
        group_id = "group-" + digest(signature)[:24]
        if group_id in groups:
            if groups[group_id]["weight"] != group["weight"]:
                raise _invalid("重复业务分组的权重不一致。")
            continue
        if any(key in atom_owners for key in atoms):
            raise _invalid("不同业务分组包含重复要求，会重复计分。")
        group["id"] = group_id
        group["requirements"] = [
            atom | {"id": "req-" + digest([group_id, key])[:24]} for key, atom in atoms.items()
        ]
        groups[group_id] = group
        atom_owners.update(dict.fromkeys(atoms, group_id))
    return list(groups.values())


def _canonical_alternatives(group, original_keys, atom_keys):
    """A bounded disjunction of conjunctions preserves nested eligibility without a tree DSL."""
    source = group.get("alternatives")
    if source is None:
        return None
    if group["operator"] != "any" or not source:
        raise _invalid("复合条件必须使用非空 OR 分支。")
    indexes = {key: index for index, key in enumerate(atom_keys)}
    clauses = []
    for clause in source:
        if not clause or any(
            type(index) is not int or not 0 <= index < len(original_keys) for index in clause
        ):
            raise _invalid("复合条件引用了无效要求。")
        canonical = sorted({indexes[original_keys[index]] for index in clause})
        if canonical not in clauses:
            clauses.append(canonical)
    if set().union(*(set(clause) for clause in clauses)) != set(range(len(atom_keys))):
        raise _invalid("复合条件包含未使用的原子要求。")
    if any(set(left) < set(right) for left in clauses for right in clauses):
        raise _invalid("复合条件包含被其他分支包含的冗余分支。")
    return clauses


def _framework_revision(groups):
    return digest({"protocol": FRAMEWORK, "groups": groups})


def validate_job_brief(brief, application=None):
    """Validate JD binding, canonical groups, and the entire immutable artifact hash."""
    try:
        if not isinstance(brief, dict) or set(brief) != {
            "schema_version",
            "job",
            "job_revision",
            "business_object",
            "role_understanding",
            "groups",
            "framework_revision",
            "revision",
        }:
            raise _invalid()
        if brief["schema_version"] != PROTOCOL or brief["revision"] != digest(
            {key: value for key, value in brief.items() if key != "revision"}
        ):
            raise _invalid()
        job = _job(brief["job"])
        if job != brief["job"] or digest(job) != brief["job_revision"]:
            raise _invalid()
        if application is not None and job != _job(application):
            raise _invalid("岗位全文已变化，需要新的岗位解读。")
        plain_groups = [
            {key: value for key, value in group.items() if key != "id"}
            | {
                "requirements": [
                    {key: value for key, value in atom.items() if key != "id"}
                    for atom in group["requirements"]
                ]
            }
            for group in brief["groups"]
        ]
        output = _Output.model_validate(
            {
                "business_object": brief["business_object"],
                "role_understanding": brief["role_understanding"],
                "groups": plain_groups,
            }
        ).model_dump()
        groups = _canonical_groups(output, job["job_description"])
        if groups != brief["groups"] or _framework_revision(groups) != brief["framework_revision"]:
            raise _invalid()
        role = output["role_understanding"]
        if role != brief["role_understanding"]:
            raise _invalid("岗位说明文本未规范化。")
        if any(
            not item.strip()
            for item in [
                output["business_object"],
                role["business_objective"],
                role["methods_role"],
                *role["work_outputs"],
            ]
        ):
            raise _invalid()
        return brief
    except (KeyError, TypeError, ValueError, ValidationError) as error:
        if isinstance(error, PortalDataError):
            raise
        raise _invalid() from error


def validate_framework_groups(groups, *, revision):
    """Validate one immutable JD framework without candidate judgments or routing."""
    ordered = groups
    if _framework_revision(ordered) != revision:
        raise _invalid()
    plain = [
        {key: value for key, value in group.items() if key != "id"}
        | {
            "requirements": [
                {key: value for key, value in atom.items() if key != "id"}
                for atom in group["requirements"]
            ]
        }
        for group in ordered
    ]
    validated = [_Group.model_validate(group).model_dump() for group in plain]
    quotes = "\n".join(
        [group["jd_quote"] for group in validated]
        + [atom["jd_quote"] for group in validated for atom in group["requirements"]]
    )
    if _canonical_groups({"groups": validated}, quotes) != ordered:
        raise _invalid()


def find_saved_job_brief(application, analysis_root):
    """Find a completed exact-job interpretation without replaying analysis or calling a model."""
    job = _job(application)
    root = Path(analysis_root).expanduser()
    try:
        if ".." in root.parts or any(part.is_symlink() for part in (root, *root.parents)):
            raise ValueError("Unsafe saved job brief root")
        if not root.exists():
            return None
        paths = []
        for directory in root.iterdir():
            path = directory / "job-brief" / "job-brief.json"
            if path.exists() or path.is_symlink():
                if any(part.is_symlink() for part in (path, *path.parents)):
                    raise ValueError("Unsafe saved job brief path")
                paths.append(path)
        paths.sort(key=lambda path: (path.stat().st_mtime_ns, str(path)), reverse=True)
        for path in paths:
            try:
                brief = json.loads(_read_bounded_document(path).raw)
            except (ValueError, RecursionError):
                brief = None
            if isinstance(brief, dict) and (
                brief.get("job") == job or brief.get("job_revision") == digest(job)
            ):
                return validate_job_brief(brief, application), path
            attempt_path = path.parent / "attempt.json"
            if attempt_path.exists() or attempt_path.is_symlink():
                attempt = json.loads(_read_bounded_document(attempt_path).raw)
                if (
                    not isinstance(attempt, dict)
                    or set(attempt) != {"job_revision", "schema_version"}
                    or attempt.get("schema_version") != PROTOCOL
                    or attempt.get("job_revision") == digest(job)
                ):
                    raise _invalid("原岗位解读记录已损坏，未重新调用模型。")
            elif brief is None:
                raise _invalid("原岗位解读记录不能核验所属岗位。")
        return None
    except (OSError, ValueError, RecursionError) as error:
        if isinstance(error, PortalDataError):
            raise
        raise _invalid("原岗位解读记录不能安全核验。") from error


def create_job_brief(
    application,
    directory,
    *,
    runner=run_codex_exec,
    environment=None,
    resume_from=None,
    on_dispatch=None,
):
    """Publish once; an unfinished or failed destination never silently calls again."""
    job = _job(application)
    directory = Path(directory).expanduser()
    try:
        if ".." in directory.parts or any(
            part.is_symlink() for part in (directory, *directory.parents)
        ):
            raise ValueError("Job brief paths cannot traverse symbolic links")
        directory = private_root(directory.parent) / directory.name
        if directory.is_symlink():
            raise ValueError("Job brief directory cannot be a symlink")
        directory.mkdir(mode=0o700, exist_ok=True)
    except (OSError, ValueError) as error:
        raise PortalDataError(
            "job_brief_directory_invalid", "岗位解读必须保存在私有目录。", 409
        ) from error
    brief_path = directory / "job-brief.json"
    if brief_path.exists() or brief_path.is_symlink():
        try:
            return validate_job_brief(
                json.loads(_read_bounded_document(brief_path).raw), application
            )
        except (OSError, ValueError) as error:
            if isinstance(error, PortalDataError):
                raise
            raise _invalid() from error
    if resume_from is not None:
        previous = Path(resume_from).expanduser()
        previous_brief = previous / "job-brief.json"
        if previous_brief.exists() or previous_brief.is_symlink():
            try:
                brief = validate_job_brief(
                    json.loads(_read_bounded_document(previous_brief).raw), application
                )
            except (OSError, ValueError) as error:
                if isinstance(error, PortalDataError):
                    raise
                raise _invalid() from error
            helper.atomic_write_json(brief_path, brief)
            return brief
        previous_attempt = previous / "attempt.json"
        if previous_attempt.exists() or previous_attempt.is_symlink():
            try:
                attempt = json.loads(_read_bounded_document(previous_attempt).raw)
                if attempt != {"job_revision": digest(job), "schema_version": PROTOCOL}:
                    raise _invalid("原岗位解读输入已变化。")
            except (OSError, ValueError) as error:
                if isinstance(error, PortalDataError):
                    raise
                raise _invalid() from error
        # Checked before this attempt saves anything, so neither an unknown call nor a
        # damaged record is copied into it.
        try:
            model_call.earlier_answer(previous, model_call.JOB_BRIEF)
        except model_call.UnknownCall as error:
            raise PortalDataError(
                "match_result_needs_recheck", "原岗位解读结果未知，须先核对原调用。", 409
            ) from error
        except model_call.DamagedRecord as error:
            raise _invalid("原岗位解读调用记录不能核验。") from error
    if (directory / "job-brief-result.json").exists():
        raise PortalDataError(
            "job_brief_attempt_exists", "此目录已有岗位解读结果，请使用新版本目录。", 409
        )
    # Exclusive claim precedes all calls. A crash preserves an inspectable failed attempt.
    try:
        with (directory / "attempt.json").open("x", encoding="utf-8") as handle:
            json.dump({"job_revision": digest(job), "schema_version": PROTOCOL}, handle)
    except FileExistsError as error:
        raise PortalDataError(
            "job_brief_attempt_exists", "此目录已有岗位解读尝试，请保留原件并使用新版本目录。", 409
        ) from error
    schema_path = directory / "job-brief-schema.json"
    helper.atomic_write_json(schema_path, _Output.model_json_schema())
    helper.atomic_write_json(
        directory / "job-brief-input.json", {"schema_version": PROTOCOL, "job": job}
    )
    prompt = (
        "Interpret this complete job description exactly once, using only this JD. "
        "Do not read applicant, career library or other files; do not assess a candidate. "
        "Explain business_object and role_understanding (business_objective, work_outputs, "
        "methods_role). Business purpose and actual outputs take priority over keyword lists. "
        "Preserve unknown goals or outputs when the full JD leaves them unspecified; "
        "do not invent an industry, goal or duty from a title, employer or isolated keyword. "
        "Cover every requirement the JD states, in its duties and in its qualifications "
        "(education, knowledge, skills, tools, experience and personal qualities): never "
        "drop a stated requirement because it seems minor or overlaps a duty. "
        "Group requirements by actual business responsibility and merge only semantic "
        "duplicates. Keep each condition as one requirement, including a condition that "
        "can be met in alternative ways (for example a Master's or PhD, or Python or Java): "
        "its text keeps "
        "the alternatives and matching judges whether any is met. Split only distinct "
        "capabilities that are each needed; each required language level is its own "
        "requirement (German C1 and English B2 are two), so one unmet level is never "
        "judged partial. A language level is never a hard_condition: it is a scored "
        "requirement. Use operator all and leave alternatives null. "
        "Copy every jd_quote literally from the full JD as one continuous passage, such as "
        "the whole sentence or bullet; never shorten a quote or join pieces with ellipses. "
        "Propose integer weight 1..100 and weight_reason per business group; the program "
        "normalizes group weights to 100 and divides each group equally among its children. "
        "Required/preferred is descriptive, with no fixed 3:1 ratio. Mark hard_condition "
        "only for an explicit non-negotiable employment eligibility or credential condition, "
        "such as work authorization or an awarded degree. "
        "Ordinary duties and technical experience are not hard conditions merely because "
        "they are listed as required. Do not invent profit, live trading, "
        "financial performance or other eligibility gates. Do not judge applicant evidence. "
        "Return only the schema-constrained object.\nJOB:\n" + json.dumps(job, ensure_ascii=False)
    )
    helper.atomic_write_json(directory / "job-brief-prompt.json", {"prompt": prompt})
    config = CodexCLIConfig(
        schema_version="codex-cli-config/v1",
        workspace=directory,
        output_schema=schema_path,
        drift_limitation_reason="Unpinned comparison alias; raw response and uncertainty retained.",
    )
    try:
        # An earlier attempt's answer to this identical question is adopted without a call.
        result = model_call.send(
            directory,
            model_call.JOB_BRIEF,
            runner,
            config,
            prompt,
            previous=None if resume_from is None else Path(resume_from).expanduser(),
            before_send=on_dispatch,
            timeout_seconds=180,
            allow_non_repository=True,
            environment=dict(os.environ) if environment is None else environment,
        )
    except model_call.UnknownCall as error:
        raise PortalDataError(
            "match_result_needs_recheck", "原岗位解读结果未明，未重复模型请求。", 409
        ) from error
    except model_call.DamagedRecord as error:
        raise _invalid("原岗位解读调用记录不能核验。") from error
    except (CodexCLIError, OSError, subprocess.TimeoutExpired) as error:
        raise PortalDataError(
            model_call.failure_code(error, "job_brief_unavailable"),
            "岗位解读未完成，请检查模型服务后创建新版本。",
            503,
        ) from error
    try:
        output = _Output.model_validate(result.structured_result).model_dump()
        for group in output["groups"]:
            if len(group["requirements"]) == 1:
                # One requirement has no OR branches; its alternatives live in its text
                # (2026-11-08: UBS's one-requirement degree group came back as "any"
                # with an out-of-range branch on two attempts, rejecting the brief).
                group.update(operator="all", alternatives=None)
            group["jd_quote"] = _literal_group_quote(group["jd_quote"], job["job_description"])
            for item in group["requirements"]:
                item["jd_quote"] = _literal_jd_quote(item["jd_quote"], job["job_description"])
        groups = _canonical_groups(output, job["job_description"])
        brief = {
            "schema_version": PROTOCOL,
            "job": job,
            "job_revision": digest(job),
            "business_object": output["business_object"],
            "role_understanding": output["role_understanding"],
            "groups": groups,
            "framework_revision": _framework_revision(groups),
        }
        brief["revision"] = digest(brief)
        validate_job_brief(brief, application)
    except (ValidationError, TypeError, ValueError) as error:
        marker = _output_validation_marker(result, prompt, schema_path, "job_brief_invalid")
        if marker is not None:
            helper.atomic_write_json(directory / "validation-failure.json", marker)
        if isinstance(error, PortalDataError):
            raise
        raise _invalid() from error
    helper.atomic_write_json(brief_path, brief)
    return brief


def brief_requirements(brief):
    """Flatten the framework while retaining enough data to reject partial scoring."""
    validate_job_brief(brief)
    groups = brief["groups"]
    total = sum(group["weight"] for group in groups)
    return [
        {
            "text": atom["text"],
            "importance": group["importance"],
            "hard_condition": group["hard_condition"],
            "scoring_framework": {
                "protocol": FRAMEWORK,
                "revision": brief["framework_revision"],
                "group_ids": [item["id"] for item in groups],
                "group": deepcopy(group),
                "requirement_id": atom["id"],
                "weight_numerator": 100 * group["weight"],
                "weight_denominator": total * len(group["requirements"]),
            },
        }
        for group in groups
        for atom in group["requirements"]
    ]
