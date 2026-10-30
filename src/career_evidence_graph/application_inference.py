"""Bind one matching inference to fixed requirements and already quoted facts.

These checks establish structure, provenance and deterministic calculations. They
do not establish that a semantic inference is correct.
"""

from __future__ import annotations

import re
import unicodedata
from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from .career_portal_data import PortalDataError
from .validation.hashing import record_digest as digest


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class _ElapsedMonths(_Strict):
    kind: Literal["elapsed_months_at_least"]
    start_date: str
    end_date: str
    threshold_quote: str = Field(min_length=1)


class _DateOnOrBefore(_Strict):
    kind: Literal["date_on_or_before"]
    subject_date: str
    cutoff_date: str


class Inference(_Strict):
    """Model-supplied reasoning; fact references and results are program-owned."""

    requirement_id: str = Field(min_length=1)
    type: Literal["direct", "deterministic", "semantic"]
    relation: Literal["supports", "partial_support", "contradicts", "unresolved"]
    basis: str = Field(min_length=1, max_length=2000)
    expression_scope: str = Field(max_length=4000)
    calculation: _ElapsedMonths | _DateOnOrBefore | None


_RELATIONS = {
    "supported": "supports",
    "partial": "partial_support",
    "gap": "contradicts",
    "unknown": "unresolved",
}
_ISO_DATE = re.compile(r"(?<!\d)\d{4}-\d{2}-\d{2}(?!\d)")
# Digits joined to letters name things (ROS2, EC2, 3D), they do not state a quantity
# (installed MC-11, 2026-10-31).
_NUMBER = re.compile(r"(?<![A-Za-z])\d+(?:[.,]\d+)*%?(?![A-Za-z])")
_LEVEL = re.compile(r"(?<![A-Za-z0-9])(?:CEFR\s*)?[ABC][12](?![A-Za-z0-9])", re.I)
_DURATION_UNIT = r"(?:years?|months?|年|个月|月)"
_DURATION = re.compile(rf"(?<![A-Za-z0-9_.,+\-−–—/~～])([1-9]\d*)\s*({_DURATION_UNIT})", re.I)
_UNSUPPORTED_DURATION = re.compile(
    rf"(?:[+\-−]\s*\d+|\d+(?:\s*[.,]\s*\d+)+|"
    rf"\d+(?:\s*{_DURATION_UNIT})?\s*(?:[-–—−/~～]|to\b|through\b|至|到)"
    rf"\s*\d+(?:\s*[.,]\s*\d+)?)\s*{_DURATION_UNIT}",
    re.I,
)
_PENDING_EDUCATION = re.compile(
    r"expected\s+graduation|anticipated\s+graduation|graduation\s+expected|"
    r"degree\s+in[- ]progress|currently\s+pursuing|在读|预计.{0,12}毕业|尚未毕业",
    re.I,
)
_AWARDED_EDUCATION = re.compile(
    r"^\s*graduated\b|\b(?:I|applicant|candidate)\s+(?:has\s+|have\s+)?graduated\b|"
    r"\bdegree\s+(?:was\s+|has\s+been\s+)?awarded\b|"
    r"\b(?:earned|completed)\s+(?:a\s+|the\s+|my\s+)?(?:degree|PhD|doctorate)\b|"
    r"已毕业|已获得.{0,12}学位|毕业于",
    re.I,
)


def _invalid(message="匹配推断或事实引用不能核验。"):
    return PortalDataError("match_inference_invalid", message, 409)


def _fact_references(sources):
    facts = []
    for source in sources:
        if not isinstance(source, dict):
            raise _invalid()
        fact = {
            key: source.get(key)
            for key in ("source_id", "source_revision", "quote_start", "quote_end", "quote")
        }
        if (
            not isinstance(fact["source_id"], str)
            or not fact["source_id"]
            or not isinstance(fact["source_revision"], str)
            or not fact["source_revision"]
            or not isinstance(fact["quote"], str)
            or not fact["quote"].strip()
            or type(fact["quote_start"]) is not int
            or type(fact["quote_end"]) is not int
            or fact["quote_start"] < 0
            or fact["quote_end"] <= fact["quote_start"]
            or fact["quote_end"] - fact["quote_start"] != len(fact["quote"])
        ):
            raise _invalid()
        fact = {"id": "fact-" + digest(fact), **fact}
        if fact not in facts:
            facts.append(fact)
    return facts


def _atom_for(template, brief):
    try:
        requirement_id = template["scoring_framework"]["requirement_id"]
        matches = [
            atom
            for group in brief["groups"]
            for atom in group["requirements"]
            if atom["id"] == requirement_id
        ]
        if len(matches) != 1 or matches[0]["text"] != template["text"]:
            raise _invalid("推断要求未绑定固定岗位说明。")
        return matches[0]
    except (KeyError, TypeError) as error:
        raise _invalid("推断要求未绑定固定岗位说明。") from error


def _date(value):
    if not isinstance(value, str) or _ISO_DATE.fullmatch(value) is None:
        raise _invalid("日期计算只接受原文明示的完整 ISO 日期。")
    try:
        return date.fromisoformat(value)
    except ValueError as error:
        raise _invalid("日期计算包含无效日期。") from error


def _cited_date(value, facts):
    parsed = _date(value)
    if not any(value in _ISO_DATE.findall(fact["quote"]) for fact in facts):
        raise _invalid("日期计算输入不在事实引文内。")
    return parsed


def _calculate(calculation, atom, facts):
    if calculation["kind"] == "elapsed_months_at_least":
        start = _cited_date(calculation["start_date"], facts)
        end = _cited_date(calculation["end_date"], facts)
        if end < start:
            raise _invalid("经历结束日期早于开始日期。")
        threshold = calculation["threshold_quote"]
        match = _DURATION.fullmatch(threshold)
        if match is None or threshold not in atom["jd_quote"]:
            raise _invalid("年限阈值必须来自该固定岗位要求原文。")
        # A substring such as '2 years' must not match the tail of '12 years'.
        unsupported = list(_UNSUPPORTED_DURATION.finditer(atom["jd_quote"]))
        durations = list(_DURATION.finditer(atom["jd_quote"]))
        # Composite, alternative and repeated durations require interpretation.
        # This calculator accepts one explicit integer threshold only.
        if len(durations) != 1 or unsupported:
            raise _invalid("复合或多个年限不能截取为一个整数阈值。")
        if durations[0].group() != threshold:
            raise _invalid("年限阈值与岗位要求不一致。")
        threshold_months = int(match[1]) * (
            12 if match[2].lower() in {"year", "years", "年"} else 1
        )
        months = (end.year - start.year) * 12 + end.month - start.month
        months -= end.day < start.day
        result = {
            "elapsed_months": months,
            "threshold_months": threshold_months,
            "satisfied": months >= threshold_months,
        }
    else:
        subject = _cited_date(calculation["subject_date"], facts)
        cutoff = _date(calculation["cutoff_date"])
        if calculation["cutoff_date"] not in _ISO_DATE.findall(atom["jd_quote"]):
            raise _invalid("截止日期必须来自该固定岗位要求原文。")
        result = {"satisfied": subject <= cutoff}
    return {**calculation, "result": result}


def _number_tokens(text):
    # Preserve full dates as tokens so a new date cannot be assembled from old digits.
    text = unicodedata.normalize("NFKC", text)
    dates = set(_ISO_DATE.findall(text))
    return dates | set(_NUMBER.findall(_ISO_DATE.sub("", text)))


def _check_expression(expression, facts, calculation):
    cited = "\n".join(fact["quote"] for fact in facts)
    allowed_numbers = _number_tokens(cited)
    if calculation is not None:
        allowed_numbers |= _number_tokens(
            " ".join(str(value) for key, value in calculation.items() if key != "result")
        )
        allowed_numbers |= {
            str(value) for value in calculation["result"].values() if type(value) is int
        }
    if not _number_tokens(expression) <= allowed_numbers:
        raise _invalid("可用表达包含没有事实或程序计算支持的精确数字。")
    levels = {
        re.sub(r"^CEFR\s*", "", item, flags=re.I).upper() for item in _LEVEL.findall(expression)
    }
    allowed_levels = {
        re.sub(r"^CEFR\s*", "", item, flags=re.I).upper() for item in _LEVEL.findall(cited)
    }
    if not levels <= allowed_levels:
        raise _invalid("可用表达包含事实未记录的精确语言等级。")


def validate_inference(row, template, brief):
    """Validate one conclusion without changing its judgment or numeric weight."""
    try:
        inference = Inference.model_validate(row["inference"]).model_dump(mode="json")
    except (KeyError, TypeError, ValidationError) as error:
        raise _invalid() from error
    atom = _atom_for(template, brief)
    if (
        inference["requirement_id"] != atom["id"]
        or _RELATIONS.get(row.get("judgment")) != inference["relation"]
        or not inference["basis"].strip()
    ):
        raise _invalid("推断的要求 ID、判断和关系不一致。")
    sources = row.get("sources", [])
    if not isinstance(sources, list):
        raise _invalid()
    facts = _fact_references(sources)
    if row["judgment"] != "unknown" and not facts:
        raise _invalid("推断结论缺少已核验的事实引文。")
    if row["judgment"] == "unknown" and inference["expression_scope"].strip():
        raise _invalid("未知结论不能产生雇主可用断言。")
    if row.get("claim_scope") == "personal_completed" and any(
        source.get("planned_only")
        or source.get("attribution") != "User"
        or source.get("design_only")
        or source.get("documentary_only")
        or source.get("match_eligible") is False
        or source.get("rewrite_allowed") is False
        for source in sources
    ):
        raise _invalid("推断不能将计划、团队、他人或设计升级为个人完成。")
    if any(
        _PENDING_EDUCATION.search(source["quote"]) for source in sources
    ) and _AWARDED_EDUCATION.search(inference["expression_scope"]):
        raise _invalid("预计毕业或在读记录不能表达为已经毕业或获得学位。")
    calculation = inference["calculation"]
    if (inference["type"] == "deterministic") != (calculation is not None):
        raise _invalid("确定性推导必须使用程序计算输入。")
    if calculation is not None:
        calculation = _calculate(calculation, atom, facts)
        expected = "supported" if calculation["result"]["satisfied"] else "gap"
        if row["judgment"] != expected:
            raise _invalid("模型判断与程序计算结果不一致。")
    _check_expression(inference["expression_scope"], facts, calculation)
    return {**inference, "facts": facts, "calculation": calculation}
