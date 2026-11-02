"""Hard-condition eligibility: applicant clarifications beside the documentary score."""

from __future__ import annotations

from copy import deepcopy

from .application_input_binding import analysis_input_binding, resolution_input_revision
from .validation.hashing import record_digest as digest


def qualification_status(requirements, conditions):
    """Aggregate effective child facts using the retained original group relation."""
    if any("scoring_framework" in row for row in requirements):
        from .application_match_scoring import calculate_match_score

        effective = deepcopy(requirements)
        for condition in conditions:
            effective[condition["requirement_index"]]["judgment"] = {
                "supported": "supported",
                "conflict": "gap",
                "needs_input": "unknown",
            }[condition["status"]]
        return calculate_match_score(effective)["eligibility"]
    statuses = {row["status"] for row in conditions}
    return (
        "conflict"
        if "conflict" in statuses
        else "needs_input"
        if "needs_input" in statuses
        else "supported"
        if conditions
        else "not_specified"
    )


def task_eligibility(task: dict, *, bind_inputs=False) -> dict:
    """Keep applicant clarifications separate from the documentary match score."""
    analysis = next(
        (
            row["result"]
            for row in reversed(task.get("artifacts", []))
            if row.get("stage") == "analysis"
            and row.get("adopted")
            and row.get("result", {}).get("id") == task.get("analysis_id")
        ),
        None,
    )
    if analysis is None:
        return {"status": "analysis_required", "conditions": []}
    conditions = []
    analysis_revisions = set()
    if bind_inputs:
        projection = analysis_input_binding(task["inputs"])
        analysis_revisions.add(digest(projection))
        if "qualification_information_revision" in task["inputs"]:
            analysis_revisions.add(
                digest(
                    projection
                    | {
                        "qualification_information_revision": task["inputs"][
                            "qualification_information_revision"
                        ]
                    }
                )
            )
    for index, requirement in enumerate(analysis.get("requirements", [])):
        if not requirement.get("hard_condition"):
            continue
        resolution = next(
            (
                row
                for row in reversed(task.get("hard_condition_resolutions", []))
                if row.get("analysis_id") == task["analysis_id"]
                and type(row.get("requirement_index")) is int
                and row["requirement_index"] == index
                and row.get("confirmed") is True
                and row.get("verified_by") == "user"
                and type(row.get("eligible")) is bool
                and isinstance(row.get("source"), str)
                and bool(row["source"].strip())
                and (
                    not bind_inputs
                    or (
                        row["analysis_input_revision"] in analysis_revisions
                        if "analysis_input_revision" in row
                        else row.get("input_revision") == resolution_input_revision(task["inputs"])
                    )
                )
            ),
            None,
        )
        judgment = requirement.get("judgment")
        status = (
            "conflict"
            if judgment == "gap"
            else ("supported" if resolution["eligible"] else "conflict")
            if resolution
            else "supported"
            if judgment == "supported"
            else "needs_input"
        )
        conditions.append(
            {
                "requirement_index": index,
                "text": requirement["text"],
                "judgment": judgment,
                "status": status,
                "resolution": deepcopy(resolution),
            }
        )
    return {
        "status": qualification_status(analysis.get("requirements", []), conditions),
        "conditions": conditions,
    }
