"""Pure candidate comparison, conserved framework scores and match routing.

This module performs no source reads, model calls or workflow transitions.
"""

from __future__ import annotations

import re
import unicodedata
from copy import deepcopy
from fractions import Fraction

from .career_portal_data import PortalDataError


def _invalid():
    # Preserve the historical framework error contract exposed by job_brief.
    return PortalDataError("job_brief_invalid", "岗位解读或评分框架不能核验。", 409)


def normalize_requirements(requirements):
    if not isinstance(requirements, list):
        raise PortalDataError("match_model_invalid", "岗位要求格式不能核验。", 409)
    distinct = {}
    for requirement in requirements:
        if (
            not isinstance(requirement, dict)
            or not isinstance(requirement.get("text"), str)
            or not requirement["text"].strip()
            or not isinstance(requirement.get("importance"), str)
            or requirement["importance"] not in {"required", "preferred"}
            or not isinstance(requirement.get("judgment"), str)
            or requirement["judgment"] not in {"supported", "partial", "gap", "unknown"}
            or type(requirement.get("hard_condition")) is not bool
        ):
            raise PortalDataError("match_model_invalid", "岗位要求格式不能核验。", 409)
        key = re.sub(
            r"\s+", " ", unicodedata.normalize("NFKC", requirement["text"]).casefold()
        ).strip(" .;。")
        if not key:
            raise PortalDataError("match_model_invalid", "岗位要求格式不能核验。", 409)
        if key in distinct:
            existing = distinct[key]
            if existing["judgment"] != requirement["judgment"]:
                raise PortalDataError(
                    "match_requirement_conflict", "重复岗位要求的判断冲突，请重新分析。", 409
                )
            if requirement["importance"] == "required":
                existing["importance"] = "required"
            existing["hard_condition"] |= requirement["hard_condition"]
            if "source_ids" in existing or "source_ids" in requirement:
                existing["source_ids"] = list(
                    dict.fromkeys(
                        [*existing.get("source_ids", []), *requirement.get("source_ids", [])]
                    )
                )
            if "citations" in existing or "citations" in requirement:
                for citation in requirement.get("citations", []):
                    if citation not in existing.setdefault("citations", []):
                        existing["citations"].append(deepcopy(citation))
        else:
            distinct[key] = deepcopy(requirement)
    return list(distinct.values())


def calculate_match_score(requirements: list[dict]) -> dict:
    """Calculate legacy or fixed-framework match intervals without changing qualifications."""
    if any("scoring_framework" in row for row in requirements):
        return calculate_framework_score(requirements)
    requirements = normalize_requirements(requirements)
    total = sum(3 if row["importance"] == "required" else 1 for row in requirements)
    unknown = sum(
        (3 if row["importance"] == "required" else 1)
        for row in requirements
        if row["judgment"] == "unknown"
    )
    supported = sum(
        (3 if row["importance"] == "required" else 1)
        * {"supported": 1, "partial": 0.5, "gap": 0, "unknown": 0}[row["judgment"]]
        for row in requirements
    )
    hard = {row["judgment"] for row in requirements if row["hard_condition"]}
    eligibility = "not_specified"
    if hard:
        eligibility = (
            "conflict"
            if "gap" in hard
            else "needs_input"
            if hard & {"unknown", "partial"}
            else "supported"
        )
    return {
        "lower": 100 * supported / total if total else None,
        "upper": 100 * (supported + unknown) / total if total else None,
        "coverage": 100 * (total - unknown) / total if total else None,
        "eligibility": eligibility,
    }


def calculate_framework_score(rows):
    """Compute conservative intervals with all/any business-group semantics."""
    from .application_job_brief import FRAMEWORK, validate_framework_groups

    try:
        if not rows:
            raise _invalid()
        metadata = rows[0]["scoring_framework"]
        expected_ids = metadata["group_ids"]
        groups = {}
        seen = {}
        for row in rows:
            meta = row["scoring_framework"]
            if (
                set(meta)
                != {
                    "protocol",
                    "revision",
                    "group_ids",
                    "group",
                    "requirement_id",
                    "weight_numerator",
                    "weight_denominator",
                }
                or meta["protocol"] != FRAMEWORK
            ):
                raise _invalid()
            if meta["revision"] != metadata["revision"] or meta["group_ids"] != expected_ids:
                raise _invalid()
            group = meta["group"]
            group_id = group["id"]
            if group_id in groups and groups[group_id] != group:
                raise _invalid()
            groups[group_id] = group
            atom = next(
                item for item in group["requirements"] if item["id"] == meta["requirement_id"]
            )
            if (row["text"], row["importance"], row["hard_condition"]) != (
                atom["text"],
                group["importance"],
                group["hard_condition"],
            ) or meta["requirement_id"] in seen:
                raise _invalid()
            if row["judgment"] not in {"supported", "gap", "partial", "unknown"}:
                raise _invalid()
            seen[meta["requirement_id"]] = row["judgment"]
        ordered = [groups[group_id] for group_id in expected_ids]
        if len(set(expected_ids)) != len(expected_ids) or set(groups) != set(expected_ids):
            raise _invalid()
        validate_framework_groups(ordered, revision=metadata["revision"])
        total = sum(group["weight"] for group in ordered)
        expected_atoms = {atom["id"] for group in ordered for atom in group["requirements"]}
        if set(seen) != expected_atoms:
            raise _invalid()
        for row in rows:
            meta = row["scoring_framework"]
            group = meta["group"]
            if (meta["weight_numerator"], meta["weight_denominator"]) != (
                100 * group["weight"],
                total * len(group["requirements"]),
            ):
                raise _invalid()
        lower = upper = Fraction(0)
        hard = []
        for group in ordered:
            # Partial support is a completed judgment worth half (decided 2026-10-31);
            # only unknown keeps the whole [0, 1] interval.
            half = Fraction(1, 2)
            values = [
                {
                    "supported": (1, 1),
                    "gap": (0, 0),
                    "partial": (half, half),
                }.get(seen[atom["id"]], (0, 1))
                for atom in group["requirements"]
            ]
            if group["alternatives"] is not None:
                clauses = [[values[index] for index in clause] for clause in group["alternatives"]]
                low, high = (
                    max(
                        Fraction(sum(value[index] for value in clause), len(clause))
                        for clause in clauses
                    )
                    for index in (0, 1)
                )
                eligibility = (
                    "supported"
                    if any(all(value == (1, 1) for value in clause) for clause in clauses)
                    else "conflict"
                    if all(any(value == (0, 0) for value in clause) for clause in clauses)
                    else "needs_input"
                )
            elif group["operator"] == "all":
                low = Fraction(sum(value[0] for value in values), len(values))
                high = Fraction(sum(value[1] for value in values), len(values))
                eligibility = (
                    "conflict"
                    if any(value == (0, 0) for value in values)
                    else (
                        "supported" if all(value == (1, 1) for value in values) else "needs_input"
                    )
                )
            elif group["operator"] == "any":
                low, high = (Fraction(max(value[index] for value in values)) for index in (0, 1))
                eligibility = (
                    "supported" if low == 1 else "conflict" if high == 0 else "needs_input"
                )
            else:
                raise _invalid()
            lower += 100 * group["weight"] * low / total
            upper += 100 * group["weight"] * high / total
            if group["hard_condition"]:
                hard.append(eligibility)
        return {
            "lower": float(lower),
            "upper": float(upper),
            "coverage": float(100 - (upper - lower)),
            "eligibility": "conflict"
            if "conflict" in hard
            else "needs_input"
            if "needs_input" in hard
            else "supported"
            if hard
            else "not_specified",
        }
    except (KeyError, TypeError, ValueError, StopIteration, ZeroDivisionError) as error:
        if isinstance(error, PortalDataError):
            raise
        raise _invalid() from error


def route_for_score(score):
    """Preserve no automatic numeric skip; uncertainty and hard conflicts stay distinct."""
    if score["eligibility"] == "conflict":
        route = "hold"
    elif score["eligibility"] == "needs_input" or score["lower"] != score["upper"]:
        route = "needs_input"
    else:
        route = "matched"
    return {"route": route, "auto_skip": False}
