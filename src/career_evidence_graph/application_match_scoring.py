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


# Decided 2026-10-31: the model scores each requirement inside its judgment's band and
# the program keeps the score there, so randomness cannot cross a band.
FIT_BANDS = {"supported": (75, 100), "partial": (30, 75), "unknown": (0, 15), "gap": (0, 0)}
_UNREAD = {"context_not_fully_read", "source_unavailable"}


def fit_in_band(judgment, fit):
    """Clamp a model fit score to its judgment's band, in steps of 5; None when absent."""
    if type(fit) is not int or judgment not in FIT_BANDS:
        return None
    low, high = FIT_BANDS[judgment]
    return min(high, max(low, 5 * round(fit / 5)))


def _item_interval(row):
    """One requirement's [low, high] share of its full weight."""
    judgment = row["judgment"]
    if row.get("citation_warning"):
        # An execution failure is not evidence of absence: keep what the model proposed.
        proposed = fit_in_band(row.get("proposed_judgment"), row.get("proposed_fit_score"))
        return (Fraction(0), Fraction(100 if proposed is None else proposed, 100))
    fit = fit_in_band(judgment, row.get("fit_score"))
    if fit is None or judgment == "unknown" and row.get("evidence_state") in _UNREAD:
        # Analyses saved before fit scores: partial counts half, unknown keeps [0, 1].
        half = Fraction(1, 2)
        return {"supported": (1, 1), "gap": (0, 0), "partial": (half, half)}.get(judgment, (0, 1))
    return (Fraction(fit, 100), Fraction(fit, 100))


def _group_interval(group, rows):
    """A group's interval: OR of AND branches, all as the mean, any as the best."""
    if group["alternatives"] is not None:
        return tuple(
            max(
                Fraction(sum(rows[i][index] for i in clause), len(clause))
                for clause in group["alternatives"]
            )
            for index in (0, 1)
        )
    if group["operator"] == "all":
        return tuple(Fraction(sum(row[index] for row in rows), len(rows)) for index in (0, 1))
    return tuple(Fraction(max(row[index] for row in rows)) for index in (0, 1))


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
        intervals = {}
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
            intervals[meta["requirement_id"]] = _item_interval(row)
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
            # Eligibility reads the judgments; the score reads each item's interval.
            values = [
                {"supported": (1, 1), "gap": (0, 0)}.get(seen[atom["id"]], (0, 1))
                for atom in group["requirements"]
            ]
            scored = [intervals[atom["id"]] for atom in group["requirements"]]
            if group["alternatives"] is not None:
                clauses = [[values[index] for index in clause] for clause in group["alternatives"]]
                eligibility = (
                    "supported"
                    if any(all(value == (1, 1) for value in clause) for clause in clauses)
                    else "conflict"
                    if all(any(value == (0, 0) for value in clause) for clause in clauses)
                    else "needs_input"
                )
            elif group["operator"] == "all":
                eligibility = (
                    "conflict"
                    if any(value == (0, 0) for value in values)
                    else (
                        "supported" if all(value == (1, 1) for value in values) else "needs_input"
                    )
                )
            elif group["operator"] == "any":
                eligibility = (
                    "supported"
                    if (1, 1) in values
                    else "conflict"
                    if all(value == (0, 0) for value in values)
                    else "needs_input"
                )
            else:
                raise _invalid()
            low, high = _group_interval(group, scored)
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


def combined_score(primary, analysis, requirements):
    """Average the primary and second-opinion scores; flag review when they differ too much.

    Decided 2026-10-31: sol scores, Opus scores beside it, and a gap above REVIEW_GAP
    points sends the job to the user's review. Without a complete second opinion the
    primary score stands alone.
    """
    from .application_second_opinion import REVIEW_GAP

    second = (analysis or {}).get("second_opinion") or {}
    if primary is None or second.get("status") != "complete":
        return primary, None
    try:
        rows = [
            {key: row[key] for key in ("text", "importance", "hard_condition", "scoring_framework")}
            | {"judgment": other["judgment"], "fit_score": other.get("fit_score")}
            for row, other in zip(requirements, second["requirements"], strict=True)
        ]
        other = calculate_match_score(rows)
    except (PortalDataError, KeyError, TypeError, ValueError):
        return primary, None

    def middle(score):
        return (score["lower"] + score["upper"]) / 2

    lower = (primary["lower"] + other["lower"]) / 2
    upper = (primary["upper"] + other["upper"]) / 2
    gap = abs(middle(primary) - middle(other))
    differing = [
        index
        for index, (row, mine) in enumerate(zip(rows, requirements, strict=True))
        if row["judgment"] != mine["judgment"]
        or abs(
            (fit_in_band(row["judgment"], row["fit_score"]) or 0)
            - (fit_in_band(mine["judgment"], mine.get("fit_score")) or 0)
        )
        >= 25
    ]
    return primary | {"lower": lower, "upper": upper, "coverage": 100 - (upper - lower)}, {
        "primary": primary,
        "second": other,
        "second_model": second.get("model"),
        "gap": gap,
        "needs_review": gap > REVIEW_GAP,
        "differing_requirements": differing,
    }


# Decided 2026-10-31: below 20 skip, 20-60 autonomous, 60-80 the user approves before
# materials, 80 and above precision adjustment. Within 5 points of a line the more
# involved tier applies (a 4-job test moved dual scores by 3-7 points), and the upper
# bound is read, so uncertainty also leans toward the user.
def score_tier(score, *, needs_review=False):
    if score is None or score.get("upper") is None:
        return "approve"
    upper = score["upper"]
    tier = (
        "manual" if upper >= 75 else "approve" if upper >= 55 else "auto" if upper >= 15 else "skip"
    )
    if needs_review and tier in {"auto", "skip"}:
        tier = "approve"
    return tier
