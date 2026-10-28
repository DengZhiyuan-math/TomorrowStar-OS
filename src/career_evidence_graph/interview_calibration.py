"""Compare frozen interview observations without producing personal assessments."""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from .audit.decision import validate_boundary_decision
from .audit.models import AuditQuestion, BoundaryDecision
from .domain.models import MASTERY_ANCHORS
from .validation.models import StrictModel


class CalibrationCase(StrictModel):
    case_id: str
    question: AuditQuestion
    answer: str
    inspected_context: str
    expected_route: Literal["capability", "request-context", "attribution"]
    expected_outcome: Literal["established", "incomplete", "attribution-signal"] | None
    expected_anchor_id: str | None


class CalibrationObservation(StrictModel):
    case_id: str
    route: Literal["capability", "request-context", "attribution"]
    boundary: BoundaryDecision | None
    supported_anchor_id: str | None
    rationale: str = Field(min_length=1)


def evaluate_calibration(
    cases: tuple[CalibrationCase, ...],
    attempts: tuple[tuple[CalibrationObservation, ...], ...],
) -> dict[str, object]:
    """Require exact case coverage and retain every mismatch and unstable result."""
    if len(attempts) != 3 or len({c.case_id for c in cases}) != len(cases):
        raise ValueError("calibration requires three attempts and unique cases")
    anchors = {a.anchor_id: a.inclusive_range[0] for a in MASTERY_ANCHORS}
    results = []
    for sequence, observations in enumerate(attempts, 1):
        by_id = {o.case_id: o for o in observations}
        if len(by_id) != len(observations) or set(by_id) != {c.case_id for c in cases}:
            raise ValueError("calibration observations must cover the exact frozen cases")
        for case in cases:
            observation = by_id[case.case_id]
            if (
                observation.supported_anchor_id is not None
                and observation.supported_anchor_id not in anchors
            ):
                raise ValueError("calibration uses an unknown mastery anchor")
            if observation.boundary is not None:
                validate_boundary_decision(
                    observation.boundary, question=case.question, answer=case.answer
                )
            actual_outcome = observation.boundary.outcome if observation.boundary else None
            failures = []
            if observation.route != case.expected_route:
                failures.append("answer-route-mismatch")
            if actual_outcome != case.expected_outcome:
                failures.append("capability-boundary-mismatch")
            if observation.supported_anchor_id != case.expected_anchor_id:
                failures.append("anchor-mismatch")
            critical = (
                case.expected_route == "request-context"
                and observation.boundary is not None
                or case.expected_outcome != "established"
                and actual_outcome == "established"
                or case.expected_anchor_id is None
                and observation.supported_anchor_id is not None
                or case.expected_anchor_id is not None
                and observation.supported_anchor_id is not None
                and anchors[observation.supported_anchor_id] > anchors[case.expected_anchor_id]
            )
            results.append(
                {
                    "attempt": sequence,
                    "case_id": case.case_id,
                    "route": observation.route,
                    "outcome": actual_outcome,
                    "anchor": observation.supported_anchor_id,
                    "failures": failures,
                    "critical": bool(critical),
                }
            )
    unstable = [
        c.case_id
        for c in cases
        if len(
            {(r["route"], r["outcome"], r["anchor"]) for r in results if r["case_id"] == c.case_id}
        )
        != 1
    ]
    return {
        "authority": "synthetic-model-trial-only",
        "passed": not unstable and not any(r["failures"] for r in results),
        "results": results,
        "unstable_cases": unstable,
        "critical_failure_count": sum(r["critical"] for r in results),
        "personal_scoring_authorized": False,
    }
